"""
Live regression of the three interfaces on real IMGW servers (plan U16, spec §13).

Skipped unless ``IMGW_LIVE=1``::

    IMGW_LIVE=1 .venv/bin/python -m pytest tests/live

Every catalog command runs on a small selection (one month of one year, one
station, one PMAXTP cell, ``limit``) through ``run_command``, the installed
``imgw`` and the REST API of ``imgw server`` started on a free localhost port
with store writes enabled by a test token. The store is a fresh temporary
directory restored from snapshots before every interface, so each interface
starts from the same state; requests to IMGW run one at a time. Local commands
(no REST route) run through Python and ``imgw``, and REST must answer them 404.

Compared with the Python envelope (CLI: ``to_json(root)``, REST:
``to_json(root, server=True)``): status and exit code, every key, slot and
path, byte-identical streams with their notices, and the tree of the store and
of the other written directories after the command (a read leaves them
byte-identical). Python converts its envelope in another working directory
than the CLI and the server, so a path resolved against the working directory
shows up as a difference. Live errors — coordinates outside Poland, a point
outside the PMAXTP grid, missing versions and an unsupported root — must give
the same code, exit code and HTTP status in every interface.

The MCP leg (spec 2026-10-19 §9) starts ``imgw mcp`` once, as an MCP client
does, in the working directory of the CLI and calls the tool of every read
command that asks the live sources (``x-imgw``: ``writes`` none, ``network``)
with the options of Python, ``root`` included: the structured content must be
the Python envelope ``to_json(root)`` and the text content its JSON. Run it
alone with ``-k imgw_mcp``.

Tolerated differences, because live sources change between the calls:

- ``checked_at`` of plans: the moment of the check;
- current data (``current *``) are compared by structure: status, keys, page
  ``limit`` and ``offset`` and the keys of every item must agree, while the
  measured values, ``total`` and the number of items on the page may change.

Version labels of the station catalog and of PMAXTP cells are the dates of
their creation (UTC): a run across midnight UTC reports them as differences
and has to be repeated. A run that IMGW failed in any interface (timeout,
network or HTTP error: ``source_unavailable``, ``check_failed``) cannot be
compared, so it is repeated after 20 s and again after 60 s; the last run is
compared and the report counts the attempts.

``IMGW_LIVE_REPORT=<file>`` writes the run report (date, versions, times,
attempts, outcomes and tolerated differences of every interface) as JSON.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from imgwtools import (
    ERROR_CODES,
    CommandResult,
    IMGWError,
    __version__,
    add_project_task,
    build_catalog,
    command_schema,
    current_version,
    download_project,
    init_project,
    init_store,
    run_command,
    sync_pmaxtp,
    sync_store,
)
from imgwtools.config import settings
from tests.contract.support import (
    canonical,
    cli_words,
    envelope_errors,
    imgw_executable,
    rest_request,
    schema_errors,
    slots,
    snapshot,
    unversioned,
    version_slot,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("IMGW_LIVE") != "1",
    reason="regresja na żywo serwerów IMGW: ustaw IMGW_LIVE=1",
)

CATALOG = command_schema()
EXIT_CODES: dict[str, int] = CATALOG["exit_codes"]
SPECS: dict[str, dict[str, Any]] = {
    schema["x-imgw"]["command"]: schema["x-imgw"] for schema in CATALOG["commands"]
}
ROOTED = {
    schema["x-imgw"]["command"]
    for schema in CATALOG["commands"]
    if "root" in schema["properties"]
}
INTERFACES = ("python", "cli", "rest")
# Notice labels of the CLI stderr (spec §13.10).
LABELS = {"info": "Informacja", "warning": "Ostrzeżenie", "error": "Błąd"}
TOKEN = "token-regresji-na-zywo"
# Relative reference-data directory (missing): texts name it alike everywhere.
DATA_DIR = "dane-referencyjne"
CALL_TIMEOUT = 900.0
# Pauses before repeating a run that IMGW failed (timeout, network, HTTP error):
# its answers cannot be compared, so the whole run is repeated, at most twice.
PAUSES = (20.0, 60.0)
_SOURCE = ERROR_CODES["source_unavailable"]
# Read commands asking the live sources: the commands of the MCP leg.
MCP_READS = [
    name for name, spec in SPECS.items() if spec["writes"] == "none" and spec["network"]
]
# Default page of an MCP list tool (spec 2026-10-19 §6.4 p. 5).
MCP_PAGE = 50
# Commands that write; every other command must leave its directories intact.
WRITES = {
    "datasets download",
    "pmaxtp sync",
    "store init",
    "store sync",
    "store catalog",
    "series build",
    "project init",
    "project add",
    "project remove",
    "project set-store",
    "project download",
}

DAILY = "pl.imgw.hydro_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
PHENOMENA = "pl.imgw.hydro_phenomena"
# codz_2022_01.zip (≈145 kB) and 2022_01_o.zip (≈95 kB): hydrological month
# 1 of 2022 is November 2021.
YEAR, MONTH = 2022, 1
STATION = "150160180"  # KŁODZKO, Nysa Kłodzka
SYNOP = "12375"  # WARSZAWA-OKĘCIE
LATITUDE, LONGITUDE = 50.06, 19.94  # Kraków
ARCHIVE_SLOT = f"archive:{DAILY}:{YEAR}/codz_{YEAR}_{MONTH:02d}.zip"
SERIES_SLOT = f"series:{DAILY}"
PROJECT_DIR = "projekt"
# Store snapshots built from IMGW by the session (Case.store).
SEEDS = ("empty", "synced", "full", "pinned")
# Placeholders resolved after seeding: a working-directory path, the store root,
# versions relative to the root and the indices of the stored PMAXTP cell.
WORK = "<work>/"
PROJECT = WORK + PROJECT_DIR
ROOT, ARCHIVE, SERIES, CELL_X, CELL_Y = (
    "<root>",
    "<archive>",
    "<series>",
    "<x>",
    "<y>",
)
ABSENT = "<brak klucza>"
_MOMENT = "checked_at"
_SHOWN = 12


@dataclass(frozen=True)
class Case:
    """
    Options of one run of a command (JSON form, without ``root``).

    ``store``: snapshot restored as the store root before every interface —
    ``"empty"``, ``"synced"`` (one hydro archive and its series), ``"full"``
    (plus the station catalog, a PMAXTP cell and a meteo archive without
    series), ``"pinned"`` (after the project download), ``"absent"`` (no
    directory) or ``"plain"`` (a directory that is no store); ``None`` = no
    root. ``project``: snapshot of the project directory. ``clean``: entries of
    the working directory removed before every interface. ``live``: current
    data, compared by structure.
    """

    options: dict[str, object]
    store: str | None = None
    project: str | None = None
    clean: tuple[str, ...] = ()
    live: bool = False


@dataclass(frozen=True)
class Failure:
    """A live error: every interface must report ``code``.

    ``reason``: REST reports a server setting instead of the local text, so
    only ``details.reason`` is compared with the expectation.
    """

    command: str
    options: dict[str, object]
    code: str
    store: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PythonAnswer:
    """The envelope of ``run_command`` (streams consumed) or its exception."""

    envelope: CommandResult[Any] | None
    data: bytes | None
    error: BaseException | None


@dataclass(frozen=True)
class McpAnswer:
    """A tool result of ``imgw mcp``: structured content, text and the error flag."""

    document: dict[str, Any]
    text: str
    error: bool


@dataclass
class Round:
    """One run of a case in every interface."""

    answers: dict[str, Any] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    # Snapshots of the written directories after each interface (Live.trees).
    trees: dict[str, dict[str, dict[str, str | None]]] = field(default_factory=dict)
    # Slots of the Python answer without a version in its store (Live.unresolved).
    unresolved: list[str] = field(default_factory=list)


CASES: dict[str, list[Case]] = {
    "datasets list": [Case({"kind": "hydro", "limit": 2, "offset": 1})],
    "datasets files": [
        Case(
            {
                "dataset": "hydro/dobowe",
                "years": f"{YEAR - 1}-{YEAR}",
                "months": [MONTH],
                "limit": 1,
                "offset": 1,
            }
        )
    ],
    "datasets download": [
        Case(
            {"dataset": PHENOMENA, "years": YEAR, "output": WORK + "pobrane"},
            clean=("pobrane",),
        )
    ],
    "datasets providers": [Case({"limit": 1, "offset": 1})],
    "stations find": [
        Case({"kind": "hydro", "query": "kłodzko", "limit": 3}),
        Case({"source": "store", "query": "kłodzko", "limit": 3}, "full"),
    ],
    "current hydro": [Case({"station": STATION, "limit": 1}, live=True)],
    "current meteo": [Case({"limit": 3, "offset": 1}, live=True)],
    "current synop": [Case({"station": SYNOP, "limit": 1}, live=True)],
    "current warnings": [Case({"kind": "meteo", "limit": 2}, live=True)],
    "current hydro-states": [Case({"main_only": True, "limit": 3}, live=True)],
    "pmaxtp fetch": [Case({"latitude": LATITUDE, "longitude": LONGITUDE})],
    "pmaxtp url": [
        Case({"latitude": LATITUDE, "longitude": LONGITUDE, "method": "AMP"})
    ],
    "pmaxtp check": [Case({"latitude": LATITUDE, "longitude": LONGITUDE}, "full")],
    "pmaxtp sync": [
        Case({"latitude": LATITUDE, "longitude": LONGITUDE, "method": "POT"}, "synced")
    ],
    "pmaxtp read": [Case({"ind_x": CELL_X, "ind_y": CELL_Y}, "full")],
    "store init": [Case({}, "absent")],
    "store info": [Case({}, "full")],
    "store scan": [Case({"kind": "archive", "limit": 3, "offset": 1}, "full")],
    "store check": [
        Case({"datasets": [DAILY], "years": str(YEAR), "months": [MONTH]}, "full")
    ],
    "store sync": [
        Case(
            {"datasets": ["hydro/dobowe"], "years": [YEAR], "months": [MONTH]}, "empty"
        )
    ],
    "store catalog": [Case({}, "synced")],
    "store export": [Case({"version": ARCHIVE}, "full")],
    "series build": [Case({"dataset": PRECIP}, "full")],
    "series select": [
        Case(
            {"dataset": "hydro/dobowe", "stations": [STATION], "years": str(YEAR)},
            "full",
        )
    ],
    "series read": [
        Case(
            {
                "dataset": DAILY,
                "station": STATION,
                "variables": ["H", "Q"],
                "start": f"{YEAR - 1}-11-10",
                "limit": 5,
                "offset": 1,
            },
            "full",
        )
    ],
    "series summary": [
        Case({"version": SERIES, "stations": [STATION], "limit": 5}, "full")
    ],
    "series export": [
        Case(
            {
                "dataset": DAILY,
                "station": STATION,
                "variables": "H,Q",
                "end": f"{YEAR - 1}-11-15",
            },
            "full",
        )
    ],
    "project init": [
        Case({"project_dir": PROJECT, "store_dir": ROOT}, "full", clean=(PROJECT_DIR,))
    ],
    "project add": [
        Case(
            {
                "project_dir": PROJECT,
                "name": "komorka",
                "command": "pmaxtp read",
                "options": {"ind_x": CELL_X, "ind_y": CELL_Y},
            },
            "full",
            "p_init",
        )
    ],
    "project remove": [
        Case({"project_dir": PROJECT, "name": "komorka"}, "full", "p_tasks")
    ],
    "project set-store": [
        Case(
            {"project_dir": PROJECT, "store_dir": WORK + "nowy-magazyn"},
            "pinned",
            "p_done",
            clean=("nowy-magazyn",),
        )
    ],
    "project download": [Case({"project_dir": PROJECT}, "full", "p_tasks")],
    "project check": [Case({"project_dir": PROJECT}, "full", "p_tasks")],
    "project status": [Case({"project_dir": PROJECT}, "pinned", "p_done")],
    "project verify": [Case({"project_dir": PROJECT}, "pinned", "p_done")],
    "commands schema": [Case({"command": "store sync"})],
    "commands guide": [Case({}), Case({"format": "llms", "lang": "en"})],
}

_MONTH_DIR = f"dane_hydrologiczne/dobowe/{YEAR}/codz_{YEAR}_{MONTH:02d}"
FAILURES: dict[str, Failure] = {
    "outside_poland": Failure(
        "pmaxtp fetch", {"latitude": 60.0, "longitude": LONGITUDE}, "validation_error"
    ),
    "outside_pmaxtp_grid": Failure(
        "pmaxtp fetch", {"latitude": 54.9, "longitude": 23.9}, "validation_error"
    ),
    "missing_archive_version": Failure(
        "store export",
        {
            "version": f"archives/versions/{_MONTH_DIR}/2000-01-01_00000000/"
            f"codz_{YEAR}_{MONTH:02d}.zip"
        },
        "not_found",
        "full",
    ),
    "missing_series_version": Failure(
        "series read",
        {
            "version": "series/versions/hydro_daily/2000-01-01_00000000/series.json",
            "station": STATION,
        },
        "not_found",
        "full",
    ),
    "missing_pmaxtp_cell": Failure(
        "pmaxtp read", {"ind_x": 1, "ind_y": 1}, "not_found", "full"
    ),
    "unsupported_root": Failure(
        "series summary",
        {"dataset": DAILY},
        "store_unavailable",
        "plain",
        "unsupported",
    ),
}


# --------------------------------------------------------------------------
# Comparison of JSON answers
# --------------------------------------------------------------------------


def differences(
    left: object, right: object, path: str = "$"
) -> Iterator[tuple[str, object, object]]:
    """Paths where two JSON documents differ; a missing key is ``ABSENT``."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(left.keys() | right.keys()):
            here = f"{path}.{key}"
            if key in left and key in right:
                yield from differences(left[key], right[key], here)
            else:
                yield here, left.get(key, ABSENT), right.get(key, ABSENT)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            yield f"{path}.length", len(left), len(right)
        for index, (one, other) in enumerate(zip(left, right, strict=False)):
            yield from differences(one, other, f"{path}[{index}]")
    elif canonical(left) != canonical(right):
        yield path, left, right


def tolerance(case: Case, path: str, left: object, right: object) -> str | None:
    """Why a difference between two answers is accepted (module docstring)."""
    if ABSENT in (left, right):
        return None  # keys always agree
    if path.endswith(f".{_MOMENT}"):
        return "chwila sprawdzenia"
    if case.live and (path.startswith("$.result.items") or path == "$.result.total"):
        return "dane bieżące"
    return None


def alike(
    case: Case, expected: object, document: object
) -> tuple[list[str], list[str]]:
    """Problems and tolerated differences of an envelope against the expected one."""
    problems = envelope_errors(document)
    tolerated = []
    for path, left, right in differences(expected, document):
        reason = tolerance(case, path, left, right)
        if reason is None:
            problems.append(f"{path}: {_short(left)} ≠ {_short(right)}")
        else:
            tolerated.append(f"{path}: {reason}")
    return problems, tolerated


def _short(value: object) -> str:
    text = canonical(value)
    return text if len(text) <= 120 else text[:117] + "..."


def _capped(lines: list[str]) -> list[str]:
    if len(lines) <= _SHOWN:
        return lines
    return [*lines[:_SHOWN], f"… i {len(lines) - _SHOWN} więcej"]


def _plain(details: Mapping[str, object]) -> object:
    """``details`` of an exception as the CLI prints them."""
    return json.loads(json.dumps(dict(details), ensure_ascii=False, default=str))


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _last_line(printed: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
    lines = printed.stderr.decode("utf-8", "replace").splitlines()
    try:
        document = json.loads(lines[-1]) if lines else None
    except ValueError:
        document = None
    return document if isinstance(document, dict) else {}


def _source_failed(value: object) -> bool:
    """Whether a JSON document reports an IMGW failure of one of its items."""
    if isinstance(value, dict):
        if value.get("error_code") == _SOURCE.code:
            return True
        if value.get("status") == "check_failed":  # plan item or action: HTTP error
            return True
        return any(_source_failed(item) for item in value.values())
    if isinstance(value, list | tuple):  # tuples: dataclasses.asdict of a report
        return any(_source_failed(item) for item in value)
    return False


def _document(data: bytes) -> object:
    try:
        return json.loads(data)
    except ValueError:  # a stream or an empty answer
        return None


def unavailable(answers: Iterable[Any]) -> bool:
    """Whether IMGW failed the run of any interface (spec §13.5 source_unavailable)."""
    for answer in answers:
        if isinstance(answer, PythonAnswer):
            if isinstance(answer.error, IMGWError):
                if answer.error.code == _SOURCE.code:
                    return True
                continue
            if answer.envelope is None or answer.data is not None:
                continue
            document = answer.envelope.to_json()
        elif isinstance(answer, subprocess.CompletedProcess):
            if answer.returncode == _SOURCE.exit_code:
                return True
            document = _document(answer.stdout)
        elif isinstance(answer, McpAnswer):
            if answer.error and answer.document.get("code") == _SOURCE.code:
                return True
            document = answer.document
        else:
            if answer.status_code == _SOURCE.http_status:
                return True
            document = _document(answer.content)
        if _source_failed(document):
            return True
    return False


def _patiently[T](step: Callable[[], T]) -> T:
    """A seeding step, repeated after a pause while IMGW fails it."""
    for pause in PAUSES:
        try:
            result = step()
        except IMGWError as exc:
            if exc.code != _SOURCE.code:
                raise
        else:
            if not _source_failed(asdict(cast(Any, result))):
                return result
        time.sleep(pause)
    return step()


def _repeated(run: Callable[[], Round]) -> tuple[int, Round]:
    """The number of runs and the last run, repeated while IMGW fails any answer."""
    for attempt, pause in enumerate(PAUSES, start=1):
        ran = run()
        if not unavailable(ran.answers.values()):
            return attempt, ran
        time.sleep(pause)
    return len(PAUSES) + 1, run()


# --------------------------------------------------------------------------
# The live session: server, seeds and the three interfaces
# --------------------------------------------------------------------------


@contextmanager
def _server(base: Path, work: Path, env: Mapping[str, str]) -> Iterator[str]:
    """``imgw server`` on a free localhost port; its URL once /health answers."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    log_path = base / "imgw-server.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [*imgw_executable(), "server", "--host", "127.0.0.1", "--port", str(port)],
            cwd=work,
            env=dict(env),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"imgw server zakończył się kodem {process.returncode}: "
                        + log_path.read_text(encoding="utf-8", errors="replace")
                    )
                try:
                    if httpx.get(
                        f"{url}/health", timeout=2, trust_env=False
                    ).is_success:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError(f"imgw server nie odpowiada na {url}/health")
                time.sleep(0.25)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


class Live:
    """Fresh store, its snapshots and the three interfaces of one live run."""

    def __init__(
        self, base: Path, work: Path, env: Mapping[str, str], client: httpx.Client
    ) -> None:
        self.base = base
        self.work = work
        self.root = base / "magazyn"
        self.seeds = base / "wzorce"
        self.env = dict(env)
        self.client = client
        self.values: dict[str, object] = {}
        self.rows: list[dict[str, object]] = []

    # --- state ------------------------------------------------------------------

    @contextmanager
    def local(self) -> Iterator[None]:
        """Python runs in the working directory of the CLI and the server."""
        with pytest.MonkeyPatch.context() as patch:
            patch.chdir(self.work)
            patch.setattr(settings, "data_dir", Path(DATA_DIR))
            patch.delenv("IMGW_STORE_ROOT", raising=False)
            yield

    def save(self, name: str, source: Path) -> None:
        shutil.copytree(source, self.seeds / name, symlinks=True)

    def seed(self) -> None:
        """Snapshots of the store and of the project, built once from IMGW."""
        root, project = self.root, self.work / PROJECT_DIR
        with self.local():
            init_store(root)
            self.save("empty", root)
            synced = _patiently(
                lambda: sync_store(root, datasets=[DAILY], years=[YEAR], months=[MONTH])
            )
            assert [item.status for item in synced.items] == ["created"], synced
            assert [series.status for series in synced.series] == ["created"], synced
            self.save("synced", root)
            catalog = _patiently(lambda: build_catalog(root))
            assert catalog.status == "created", catalog
            cell = _patiently(
                lambda: sync_pmaxtp(root, latitude=LATITUDE, longitude=LONGITUDE)
            )
            assert cell.status == "created", cell
            precip = _patiently(
                lambda: sync_store(
                    root, datasets=[PRECIP], years=[YEAR], months=[MONTH], series=False
                )
            )
            assert [item.status for item in precip.items] == ["created"], precip
            self.save("full", root)
            self.values = {
                ROOT: str(root),
                ARCHIVE: current_version(root, slot=ARCHIVE_SLOT)
                .version.relative_to(root)
                .as_posix(),
                SERIES: current_version(root, slot=SERIES_SLOT)
                .version.relative_to(root)
                .as_posix(),
                CELL_X: cell.ind_x,
                CELL_Y: cell.ind_y,
            }
            init_project(project, store_dir=root)
            self.save("p_init", project)
            add_project_task(
                project,
                name="dobowe",
                command="store sync",
                options={"datasets": [DAILY], "years": str(YEAR), "months": [MONTH]},
            )
            add_project_task(
                project,
                name="komorka",
                command="pmaxtp read",
                options={"ind_x": cell.ind_x, "ind_y": cell.ind_y},
            )
            self.save("p_tasks", project)
            pinned = _patiently(lambda: download_project(project))
            assert set(pinned.tasks.values()) == {"current"}, pinned
            self.save("p_done", project)
            self.save("pinned", root)

    def resolve(self, value: object) -> object:
        if isinstance(value, str):
            if value in self.values:
                return self.values[value]
            if value.startswith(WORK):
                return str(self.work / value.removeprefix(WORK))
            return value
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve(item) for key, item in value.items()}
        return value

    def restore(self, case: Case | Failure) -> None:
        """Bring the store, project and cleaned directories to the case's start."""
        project = case.project if isinstance(case, Case) else None
        clean = case.clean if isinstance(case, Case) else ()
        for name in (*clean, PROJECT_DIR):
            _remove(self.work / name)
        if project is not None:
            shutil.copytree(
                self.seeds / project, self.work / PROJECT_DIR, symlinks=True
            )
        if case.store is None:
            return
        _remove(self.root)
        if case.store == "plain":
            self.root.mkdir()
        elif case.store != "absent":
            shutil.copytree(self.seeds / case.store, self.root, symlinks=True)

    def trees(self, case: Case) -> dict[str, dict[str, str | None]]:
        """Snapshots of the directories a case can write."""
        places = {name: self.work / name for name in case.clean}
        if case.store is not None:
            places["magazyn"] = self.root
        if case.project is not None:
            places[PROJECT_DIR] = self.work / PROJECT_DIR
        return {name: snapshot(path) for name, path in places.items() if path.exists()}

    # --- interfaces -------------------------------------------------------------

    def call(self, interface: str, command: str, options: Mapping[str, object]) -> Any:
        """The answer of one interface (Python, the installed imgw or REST)."""
        if interface == "python":
            with self.local():
                try:
                    envelope = run_command(command, options=dict(options))
                    data = None
                    if isinstance(envelope.result, Iterator):
                        data = "".join(envelope.result).encode("utf-8")
                except (IMGWError, OSError) as exc:
                    return PythonAnswer(None, None, exc)
            return PythonAnswer(envelope, data, None)
        if interface == "cli":
            return subprocess.run(
                [*imgw_executable(), *cli_words(command, options)],
                cwd=self.work,
                env=self.env,
                capture_output=True,
                timeout=CALL_TIMEOUT,
                check=False,
            )
        request = rest_request(command, options)
        return self.client.request(
            request["method"],
            request["url"],
            params=request.get("params"),
            json=request.get("json"),
            headers={"X-API-Key": TOKEN},
        )

    @staticmethod
    def outcome(answer: Any) -> str:
        if isinstance(answer, PythonAnswer):
            if answer.envelope is not None:
                return answer.envelope.status
            error = answer.error
            return error.code if isinstance(error, IMGWError) else type(error).__name__
        if isinstance(answer, subprocess.CompletedProcess):
            return f"exit {answer.returncode}"
        if isinstance(answer, McpAnswer):
            return str(answer.document.get("code" if answer.error else "status"))
        return f"HTTP {answer.status_code}"

    def record(
        self,
        kind: str,
        name: str,
        index: int,
        *,
        attempts: int,
        outcomes: Mapping[str, str],
        seconds: Mapping[str, float],
        problems: Mapping[str, list[str]],
        tolerated: Mapping[str, list[str]],
    ) -> None:
        """Add one report row per interface that answered."""
        for interface, outcome in outcomes.items():
            self.rows.append(
                {
                    "kind": kind,
                    "name": name,
                    "case": index,
                    "interface": interface,
                    "attempts": attempts,
                    "outcome": outcome,
                    "seconds": round(seconds.get(interface, 0.0), 2),
                    "problems": _capped(problems[interface]),
                    "tolerated": _capped(tolerated.get(interface, [])),
                }
            )

    # --- commands ---------------------------------------------------------------

    def run_case(self, command: str, index: int, case: Case) -> dict[str, list[str]]:
        """Run one case in every interface; problems per interface (empty: alike)."""
        options = self.resolve(case.options)
        assert isinstance(options, dict)
        rooted = case.store is not None and command in ROOTED
        local = {"root": str(self.root), **options} if rooted else options
        root = self.root if rooted else None
        served = SPECS[command]["rest"] is not None
        self.restore(case)
        before = self.trees(case)

        def run() -> Round:
            ran = Round()
            for interface in INTERFACES if served else INTERFACES[:2]:
                self.restore(case)
                started = time.monotonic()
                ran.answers[interface] = self.call(
                    interface, command, options if interface == "rest" else local
                )
                ran.seconds[interface] = time.monotonic() - started
                ran.trees[interface] = self.trees(case)
                if interface == "python" and case.store in SEEDS:
                    ran.unresolved = self.unresolved(ran.answers["python"], root)
            return ran

        attempts, ran = _repeated(run)
        problems: dict[str, list[str]] = {interface: [] for interface in INTERFACES}
        tolerated: dict[str, list[str]] = {interface: [] for interface in INTERFACES}
        problems["python"] += ran.unresolved
        self.compare(case, ran.answers, root, problems, tolerated)
        # Written files record their moments (sidecars, pins): compare the paths.
        written = {place: sorted(tree) for place, tree in ran.trees["python"].items()}
        for interface, tree in ran.trees.items():
            if command not in WRITES and tree != before:
                problems[interface].append("komenda odczytu zmieniła katalogi")
            elif {place: sorted(paths) for place, paths in tree.items()} != written:
                problems[interface].append("inne drzewo plików niż po Pythonie")
        outcomes = {name: self.outcome(answer) for name, answer in ran.answers.items()}
        if not served:
            outcomes["rest"] = self.no_route(command, problems["rest"])
        self.record(
            "command",
            command,
            index,
            attempts=attempts,
            outcomes=outcomes,
            seconds=ran.seconds,
            problems=problems,
            tolerated=tolerated,
        )
        return {name: lines for name, lines in problems.items() if lines}

    def run_mcp_case(
        self, command: str, index: int, case: Case, mcp: McpServer
    ) -> dict[str, list[str]]:
        """Run one case in Python and through the tool of ``imgw mcp``; problems."""
        options = self.resolve(case.options)
        assert isinstance(options, dict)
        rooted = case.store is not None and command in ROOTED
        local = {"root": str(self.root), **options} if rooted else dict(options)
        if SPECS[command]["result"] == "list" and "limit" not in local:
            local["limit"] = MCP_PAGE  # the page a tool takes without limit
        root = self.root if rooted else None
        self.restore(case)
        before = self.trees(case)

        def run() -> Round:
            ran = Round()
            for interface in ("python", "mcp"):
                self.restore(case)
                started = time.monotonic()
                ran.answers[interface] = (
                    self.call("python", command, local)
                    if interface == "python"
                    else mcp.call(SPECS[command]["operation_id"], local)
                )
                ran.seconds[interface] = time.monotonic() - started
                ran.trees[interface] = self.trees(case)
            return ran

        attempts, ran = _repeated(run)
        problems: dict[str, list[str]] = {"python": [], "mcp": []}
        tolerated: dict[str, list[str]] = {"python": [], "mcp": []}
        python: PythonAnswer = ran.answers["python"]
        answer: McpAnswer = ran.answers["mcp"]
        if python.envelope is None:
            problems["python"].append(f"wyjątek: {python.error!r}")
        elif answer.error:
            problems["mcp"].append(f"błąd narzędzia: {_short(answer.document)}")
        else:
            if python.envelope.status != "ok":
                problems["python"].append(f"status {python.envelope.status}")
            if json.loads(answer.text) != answer.document:
                problems["mcp"].append("tekst inny niż structuredContent")
            found, accepted = alike(
                case, python.envelope.to_json(root=root), answer.document
            )
            problems["mcp"] += found
            tolerated["mcp"] += accepted
        for interface, tree in ran.trees.items():
            if tree != before:
                problems[interface].append("komenda odczytu zmieniła katalogi")
        self.record(
            "mcp",
            command,
            index,
            attempts=attempts,
            outcomes={name: self.outcome(item) for name, item in ran.answers.items()},
            seconds=ran.seconds,
            problems=problems,
            tolerated=tolerated,
        )
        return {name: lines for name, lines in problems.items() if lines}

    def unresolved(self, answer: PythonAnswer, root: Path | None) -> list[str]:
        """
        Slots of a Python answer without a version in the store it left (§13.7).

        A result with ``version: null`` (an unpublished ČHMÚ file) names its
        slot without a version and is skipped.
        """
        if answer.envelope is None or answer.data is not None:
            return []
        missing = []
        document = answer.envelope.to_json(root=root)
        for slot in sorted(set(slots(document)) - set(unversioned(document))):
            wanted = version_slot(slot)
            try:
                entry = current_version(self.root, slot=wanted)
            except IMGWError as exc:
                missing.append(f"slot {slot}: {exc.code}")
            else:
                if entry is None or entry.slot != wanted:
                    missing.append(f"slot {slot}: brak bieżącej wersji")
        return missing

    def compare(
        self,
        case: Case,
        answers: Mapping[str, Any],
        root: Path | None,
        problems: dict[str, list[str]],
        tolerated: dict[str, list[str]],
    ) -> None:
        python: PythonAnswer = answers["python"]
        envelope = python.envelope
        if envelope is None:
            problems["python"].append(f"wyjątek: {python.error!r}")
            return
        if envelope.status != "ok":
            problems["python"].append(f"status {envelope.status}")
        if python.data is not None:
            self.compare_streams(envelope, python.data, answers, problems)
            return
        local = envelope.to_json(root=root)
        served = envelope.to_json(root=root, server=True)
        problems["python"] += envelope_errors(local)

        def same(name: str, expected: object, document: object) -> None:
            found, accepted = alike(case, expected, document)
            problems[name] += found
            tolerated[name] += accepted

        printed: subprocess.CompletedProcess[bytes] = answers["cli"]
        if printed.returncode != EXIT_CODES[envelope.status]:
            problems["cli"].append(
                f"kod wyjścia {printed.returncode}: {_last_line(printed)}"
            )
        else:
            try:
                document = json.loads(printed.stdout)
            except ValueError:
                problems["cli"].append(f"stdout to nie JSON: {printed.stdout[:200]!r}")
            else:
                same("cli", local, document)
        answered: httpx.Response | None = answers.get("rest")
        if answered is None:
            return
        if answered.status_code != 200:
            problems["rest"].append(
                f"HTTP {answered.status_code}: {answered.text[:300]}"
            )
            return
        if answered.headers["content-type"] != "application/json":
            problems["rest"].append(f"typ treści {answered.headers['content-type']}")
        same("rest", served, answered.json())
        if str(self.base) in answered.text:
            problems["rest"].append("odpowiedź pokazuje katalog serwera")

    def compare_streams(
        self,
        envelope: CommandResult[Any],
        data: bytes,
        answers: Mapping[str, Any],
        problems: dict[str, list[str]],
    ) -> None:
        notices = [
            {"level": notice.level, "code": notice.code, "text": notice.text}
            for notice in envelope.notices
        ]
        printed: subprocess.CompletedProcess[bytes] = answers["cli"]
        stderr = printed.stderr.decode("utf-8", "replace")
        if printed.returncode != 0:
            problems["cli"].append(f"kod wyjścia {printed.returncode}: {stderr[-300:]}")
        elif printed.stdout != data:
            problems["cli"].append(
                f"strumień {len(printed.stdout)} B zamiast {len(data)} B Pythona"
            )
        for notice in notices:
            line = f"{LABELS[notice['level']]}: {notice['text']}"
            if stderr.count(line) != 1:
                problems["cli"].append(f"komunikat {notice['code']} nie raz na stderr")
        answered: httpx.Response = answers["rest"]
        if answered.status_code != 200:
            problems["rest"].append(
                f"HTTP {answered.status_code}: {answered.text[:300]}"
            )
            return
        if answered.content != data:
            problems["rest"].append(
                f"strumień {len(answered.content)} B zamiast {len(data)} B Pythona"
            )
        if answered.headers.get("x-imgw-status") != envelope.status:
            problems["rest"].append(
                f"X-IMGW-Status {answered.headers.get('x-imgw-status')}"
            )
        if json.loads(answered.headers.get("x-imgw-notices", "null")) != notices:
            problems["rest"].append("X-IMGW-Notices inne niż komunikaty Pythona")

    def no_route(self, command: str, problems: list[str]) -> str:
        """A local command has no REST route: 404 not_found problem document."""
        url = "/api/v1/" + command.replace(" ", "/")
        answered = self.client.get(url)
        if answered.status_code != 404 or answered.json().get("code") != "not_found":
            problems.append(
                f"komenda lokalna ma trasę {url}: HTTP {answered.status_code}"
            )
        return f"brak trasy (HTTP {answered.status_code})"

    # --- errors -----------------------------------------------------------------

    def run_failure(self, name: str, failure: Failure) -> dict[str, list[str]]:
        """Run one live error in every interface; problems per interface."""
        spec = ERROR_CODES[failure.code]
        options = self.resolve(failure.options)
        assert isinstance(options, dict)
        local = {"root": str(self.root), **options} if failure.store else options
        self.restore(failure)

        def run() -> Round:
            ran = Round()
            for interface in INTERFACES:
                started = time.monotonic()
                ran.answers[interface] = self.call(
                    interface,
                    failure.command,
                    options if interface == "rest" else local,
                )
                ran.seconds[interface] = time.monotonic() - started
            return ran

        attempts, ran = _repeated(run)
        answers = ran.answers
        problems: dict[str, list[str]] = {interface: [] for interface in INTERFACES}

        error = answers["python"].error
        if not isinstance(error, IMGWError) or error.code != failure.code:
            problems["python"].append(f"zamiast {failure.code}: {answers['python']}")
            error = None

        printed: subprocess.CompletedProcess[bytes] = answers["cli"]
        line = _last_line(printed)
        if printed.returncode != spec.exit_code:
            problems["cli"].append(f"kod wyjścia {printed.returncode}")
        if printed.stdout:
            problems["cli"].append("niepuste stdout przy błędzie")
        problems["cli"] += schema_errors(line, "cli-error")
        if line.get("code") != failure.code:
            problems["cli"].append(f"kod {line.get('code')}")
        if error is not None and [line.get("detail"), line.get("details")] != [
            error.detail,
            _plain(error.details),
        ]:
            problems["cli"].append(f"inny opis błędu niż w Pythonie: {line}")

        answered: httpx.Response = answers["rest"]
        body = answered.json()
        if answered.status_code != spec.http_status:
            problems["rest"].append(f"HTTP {answered.status_code}")
        if answered.headers["content-type"] != "application/problem+json":
            problems["rest"].append(f"typ treści {answered.headers['content-type']}")
        problems["rest"] += schema_errors(body, "problem+json")
        if (body.get("code"), body.get("title")) != (failure.code, spec.title):
            problems["rest"].append(
                f"kod i tytuł {body.get('code')}, {body.get('title')}"
            )
        if str(self.base) in answered.text:
            problems["rest"].append("odpowiedź pokazuje katalog serwera")
        if failure.reason is not None:
            if body.get("details", {}).get("reason") != failure.reason:
                problems["rest"].append(f"details {body.get('details')}")
        elif error is not None and str(self.base) not in error.detail + canonical(
            _plain(error.details)
        ):
            if [body.get("detail"), body.get("details")] != [
                error.detail,
                _plain(error.details),
            ]:
                problems["rest"].append(f"inny opis błędu niż w Pythonie: {body}")

        self.record(
            "error",
            name,
            0,
            attempts=attempts,
            outcomes={key: self.outcome(answer) for key, answer in answers.items()},
            seconds=ran.seconds,
            problems=problems,
            tolerated={},
        )
        return {key: lines for key, lines in problems.items() if lines}

    def report(self, started: datetime, path: str) -> None:
        document = {
            "date": started.isoformat(),
            "seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
            "imgwtools": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "rows": self.rows,
        }
        Path(path).write_text(
            json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )


class McpServer:
    """``imgw mcp`` of the live run, called through the SDK client from sync tests."""

    def __init__(self, portal: Any, client: Any) -> None:
        self.portal = portal
        self.client = client

    def call(self, tool: str, arguments: Mapping[str, object]) -> McpAnswer:
        result = self.portal.call(self.client.call_tool, tool, dict(arguments))
        text = result.content[0].text if result.content else ""
        return McpAnswer(result.structured_content or {}, text, bool(result.is_error))


@pytest.fixture(scope="module")
def live(tmp_path_factory) -> Iterator[Live]:
    """Fresh temporary store, ``imgw server`` on it and the seeded snapshots."""
    started = datetime.now(UTC)
    base = tmp_path_factory.mktemp("imgw-live")
    work = base / "praca"
    work.mkdir()
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("IMGW_")
    }
    env["IMGW_DATA_DIR"] = DATA_DIR
    served = env | {
        "IMGW_STORE_ROOT": str(base / "magazyn"),
        "IMGW_STORE_WRITES_ENABLED": "true",
        "IMGW_STORE_WRITE_TOKEN": TOKEN,
    }
    with (
        _server(base, work, served) as url,
        httpx.Client(base_url=url, timeout=CALL_TIMEOUT, trust_env=False) as client,
    ):
        session = Live(base, work, env, client)
        session.seed()
        yield session
    if path := os.environ.get("IMGW_LIVE_REPORT"):
        session.report(started, path)


@pytest.fixture(scope="module")
def mcp_server(live: Live) -> Iterator[McpServer]:
    """``imgw mcp`` started once as an MCP client starts it, in the CLI's directory."""
    pytest.importorskip("mcp")
    from anyio.from_thread import start_blocking_portal
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    command, *prefix = imgw_executable()
    server = StdioServerParameters(
        command=command, args=[*prefix, "mcp"], env=live.env, cwd=live.work
    )
    with (
        (live.base / "imgw-mcp.log").open("w", encoding="utf-8") as log,
        start_blocking_portal() as portal,
        portal.wrap_async_context_manager(
            Client(stdio_client(server, errlog=log), read_timeout_seconds=CALL_TIMEOUT)
        ) as client,
    ):
        yield McpServer(portal, client)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_the_live_run_covers_every_catalog_command():
    assert list(CASES) == [
        schema["x-imgw"]["command"] for schema in CATALOG["commands"]
    ]


@pytest.mark.parametrize("command", list(CASES))
def test_every_command_answers_alike_live_in_python_imgw_and_rest(command, live):
    found = {
        f"{index}:{interface}": lines
        for index, case in enumerate(CASES[command])
        for interface, lines in live.run_case(command, index, case).items()
    }
    assert found == {}


@pytest.mark.parametrize("name", list(FAILURES))
def test_live_errors_have_the_same_code_exit_code_and_http_status(name, live):
    assert live.run_failure(name, FAILURES[name]) == {}


@pytest.mark.parametrize("command", MCP_READS)
def test_live_reads_answer_alike_in_python_and_imgw_mcp(command, live, mcp_server):
    found = {
        f"{index}:{interface}": lines
        for index, case in enumerate(CASES[command])
        for interface, lines in live.run_mcp_case(
            command, index, case, mcp_server
        ).items()
    }
    assert found == {}
