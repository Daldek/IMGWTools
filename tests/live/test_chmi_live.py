"""
Live regression of the ČHMÚ provider on opendata.chmi.cz (spec 2026-10-18 §13.3, C09).

Marked ``live``; the gate leaves them out and ``-m live`` runs them::

    uv run pytest tests/live/test_chmi_live.py -m live

A small selection only: one hydrological station (``0-203-1-001000``,
Špindlerův Mlýn) with the years 2024-2026 (2026 is not published yet) and one
climate station (``0-203-0-11799``, four small CSV files). The run reuses the
machinery of ``test_interfaces_live``: a fresh temporary store restored from
snapshots before every interface, ``run_command``, the installed ``imgw`` and
the REST API of ``imgw server`` (writes enabled by a test token), answers
compared after the same tolerance rules, and ``imgw mcp`` for the reads that
ask the source (not for the hydro check, whose listing weighs 5.3 MB).

The seed reads each server listing once: the hydro check (1 listing) and the
meteo check (2 listings) are saved as plans, the project downloads its two
``series select`` tasks with these plans (HEAD and GET of each file, no
listing), and the ČHMÚ catalog is built from the live metadata. The cases then
check (the hydro listing once per interface), synchronize an empty store from
the hydro plan and from the meteo listings, rebuild the catalog, read series,
export, search stations live and in the store, download flat files (2026 →
``not_published``) and restore the pinned project into an empty store.

Every httpx request of the run — Python in this process, the CLI, the REST
server and ``imgw mcp`` in theirs (a ``sitecustomize`` on ``PYTHONPATH``) — is
written to a request log: each interface of a case must ask ČHMÚ the same
requests as Python, and the report lists the requests and bytes of every
interface (``IMGW_LIVE_REPORT=<file>`` writes it as JSON; ``-s`` prints the
totals). Requests run one at a time.
"""

import functools
import inspect
import json
import os
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from imgwtools import (
    add_project_task,
    build_catalog,
    check_store,
    current_version,
    download_project,
    init_project,
    init_store,
    iter_store,
    read_meta,
)
from imgwtools.fetch import _IDENTIFY, _archive_slot
from imgwtools.store.types import StorePlan
from tests.contract.support import imgw_executable
from tests.live.test_interfaces_live import (
    CALL_TIMEOUT,
    DATA_DIR,
    PROJECT,
    PROJECT_DIR,
    ROOT,
    ROOTED,
    TOKEN,
    WORK,
    Case,
    Live,
    McpAnswer,
    McpServer,
    PythonAnswer,
    _patiently,
    _server,
)
from tests.live.test_interfaces_live import CATALOG as COMMANDS

pytestmark = pytest.mark.live

BASE_URL = "https://opendata.chmi.cz/"
HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
STATION = "0-203-1-001000"  # Špindlerův Mlýn, Labe (spec §7.4)
METEO_STATION = "0-203-0-11799"  # SRA, T, TMA, TMI ≈ 55 kB together, 2006 only
PUBLISHED, UNPUBLISHED = (2024, 2025), 2026  # 2026 is not published before 2027
YEARS = f"{PUBLISHED[0]}-{UNPUBLISHED}"
METEO_YEARS = "2006"
HYDRO_PLAN, METEO_PLAN = "plan-hydro.json", "plan-meteo.json"
HYDRO_TASK = {
    "dataset": HYDRO,
    "stations": [STATION],
    "years": f"{PUBLISHED[0]}-{PUBLISHED[-1]}",
    "year_type": "calendar",  # the plan's files; hydrological years add a year
}
METEO_TASK = {
    "dataset": METEO,
    "stations": [METEO_STATION],
    "years": METEO_YEARS,
    "year_type": "calendar",
}
ARCHIVE_SLOT = f"archive:{HYDRO}:H_{STATION}_DQ_{PUBLISHED[-1]}.json"
METEO_SLOT = f"archive:{METEO}:precipitation/dly-{METEO_STATION}-SRA.csv"
PRECIPITATION = "meteorology/climate/historical_csv/data/daily/precipitation/"
# Placeholders resolved after seeding (versions relative to the root).
ARCHIVE, METEO_ARCHIVE, SERIES = "<archive>", "<meteo>", "<series>"
# Environment variable naming the request log of the subprocesses.
JOURNAL_ENV = "LIVE_HTTP_JOURNAL"
ATTRIBUTION = "Źródło danych: Český hydrometeorologický ústav (ČHMÚ)"
INTERFACES = ("python", "cli", "rest", "mcp")

# List commands name their page: REST pages by IMGW_API_MAX_LIMIT without a limit.
CASES: dict[str, list[Case]] = {
    "datasets list": [Case({"provider": "CHMI", "limit": 10})],
    "datasets files": [
        Case({"dataset": HYDRO, "stations": [STATION], "years": YEARS, "limit": 10}),
        Case({"dataset": METEO, "stations": [METEO_STATION], "limit": 10}),
    ],
    "datasets download": [
        Case(
            {
                "dataset": HYDRO,
                "stations": [STATION],
                "years": YEARS,
                "output": WORK + "pobrane",
            },
            clean=("pobrane",),
        )
    ],
    "datasets providers": [Case({"limit": 5})],
    "stations find": [
        Case({"provider": "CHMI", "kind": "hydro", "query": "Špindlerův", "limit": 3}),
        Case(
            {"provider": "CHMI", "source": "store", "query": STATION, "limit": 5},
            "full",
        ),
    ],
    "store info": [Case({}, "full")],
    "store scan": [Case({"provider": "CHMI", "limit": 30}, "full")],
    "store check": [
        Case({"datasets": [HYDRO], "stations": [STATION], "years": YEARS}, "full"),
        Case({"datasets": [METEO], "stations": [METEO_STATION]}, "full"),
    ],
    "store sync": [
        Case({"plan": WORK + HYDRO_PLAN}, "empty"),
        Case({"datasets": [METEO], "stations": [METEO_STATION]}, "empty"),
    ],
    "store catalog": [Case({"provider": "CHMI"}, "full")],
    "store export": [
        Case({"version": ARCHIVE}, "full"),
        Case({"version": METEO_ARCHIVE, "format": "jsonl"}, "full"),
    ],
    "series build": [Case({"dataset": HYDRO}, "full")],
    "series select": [Case({**HYDRO_TASK}, "full")],
    "series read": [
        Case(
            {"dataset": METEO, "station": METEO_STATION, "limit": 5, "offset": 1},
            "full",
        )
    ],
    "series summary": [
        Case({"version": SERIES, "stations": [STATION], "limit": 10}, "full"),
        Case({"dataset": METEO, "stations": [METEO_STATION], "limit": 10}, "full"),
    ],
    "series export": [
        Case(
            {
                "dataset": HYDRO,
                "station": STATION,
                "variables": "H,Q",
                "start": f"{PUBLISHED[0]}-12-25",
                "end": f"{PUBLISHED[-1]}-01-05",
            },
            "full",
        ),
        Case(
            {"dataset": METEO, "station": METEO_STATION, "year_type": "calendar"},
            "full",
        ),
    ],
    "project add": [
        Case(
            {
                "project_dir": PROJECT,
                "name": "temperatury",
                "command": "series select",
                "options": {**METEO_TASK, "variables": ["Tmax", "Tmin"]},
            },
            "full",
            "p_init",
        )
    ],
    "project download": [Case({"project_dir": PROJECT}, "empty", "p_done")],
    "project status": [Case({"project_dir": PROJECT}, "pinned", "p_done")],
    "project verify": [Case({"project_dir": PROJECT}, "pinned", "p_done")],
}
# Reads asking ČHMÚ through imgw mcp: the station search and the meteo check.
MCP_CASES = [("stations find", 0), ("stations find", 1), ("store check", 1)]


def _statuses(document: Mapping[str, Any], key: str = "items") -> list[str]:
    return [item["status"] for item in document["result"][key]]


def _pinned(document: Mapping[str, Any]) -> bool:
    return set(document["result"]["tasks"].values()) <= {"current", "content_match"}


# What the Python answer of a case must say (the other interfaces equal it).
EXPECTED: dict[tuple[str, int], Callable[[Mapping[str, Any]], bool]] = {
    ("datasets list", 0): lambda d: (
        [item["key"] for item in d["result"]["items"]]
        == [
            "cz.chmi.hydro_daily",
            "cz.chmi.meteo_daily",
            "cz.chmi.hydro_stations",
            "cz.chmi.meteo_stations",
        ]
    ),
    ("datasets files", 0): lambda d: (
        [item["year"] for item in d["result"]["items"]] == [*PUBLISHED, UNPUBLISHED]
    ),
    ("datasets files", 1): lambda d: d["result"]["total"] == 4,
    ("datasets download", 0): lambda d: (
        _statuses(d) == ["downloaded", "downloaded", "not_published"]
    ),
    ("stations find", 0): lambda d: (
        STATION in {item["station_code"] for item in d["result"]["items"]}
    ),
    ("stations find", 1): lambda d: (
        [(item["station_code"], item["provider"]) for item in d["result"]["items"]]
        == [(STATION, "CHMI")]
        and d["result"]["items"][0]["latitude"] is not None
    ),
    ("store info", 0): lambda d: (
        [provider["id"] for provider in d["result"]["providers"]]
        == ["IMGW-PIB", "CHMI"]
    ),
    ("store check", 0): lambda d: (
        _statuses(d) == ["current", "current", "unverifiable"]
        and d["result"]["items"][2]["error"] == "not published"
        and d["result"]["requests"] == {"made": 1, "planned": 0}
    ),
    ("store check", 1): lambda d: (
        _statuses(d) == ["current"] * 4
        and d["result"]["requests"] == {"made": 2, "planned": 0}
    ),
    ("store sync", 0): lambda d: (
        _statuses(d) == ["created", "created", "unchanged"]  # 2026 unpublished
        and _statuses(d, "series") == ["created"]
    ),
    ("store sync", 1): lambda d: (
        _statuses(d) == ["created"] * 4 and _statuses(d, "series") == ["created"]
    ),
    ("store catalog", 0): lambda d: (
        d["result"]["provider"] == "CHMI"
        and d["result"]["status"] in ("unchanged", "created")
    ),
    ("series build", 0): lambda d: d["result"]["status"] == "reused",
    ("project download", 0): lambda d: (
        _pinned(d)
        and {item["status"] for item in d["result"]["files"]}
        <= {"created", "restored_by_content"}
    ),
    ("project status", 0): _pinned,
    ("project verify", 0): _pinned,
}


# --------------------------------------------------------------------------
# Request log of every process of the run
# --------------------------------------------------------------------------


def _journal(path: str) -> tuple[Any, Any]:
    """
    Log method, URL, status and body size of every httpx request to ``path``.

    Self-contained: its source is also the ``sitecustomize`` of the CLI, the
    REST server and ``imgw mcp``. Requests to the local REST server are not
    logged. Returns the original transport methods.
    """
    import json
    import os

    import httpx

    local = ("127.0.0.1", "localhost", "testserver")
    sync = httpx.HTTPTransport.handle_request
    asynchronous = httpx.AsyncHTTPTransport.handle_async_request

    def write(request: httpx.Request, status: int, size: int) -> None:
        line = json.dumps(
            {
                "pid": os.getpid(),
                "method": request.method,
                "url": str(request.url),
                "status": status,
                "bytes": size,
            }
        )
        with open(path, "a", encoding="utf-8") as log:
            log.write(line + "\n")

    class Counted(httpx.SyncByteStream):
        def __init__(self, stream: Any, request: httpx.Request, status: int) -> None:
            self.stream, self.request, self.status = stream, request, status
            self.size, self.logged = 0, False

        def __iter__(self) -> Iterator[bytes]:
            for chunk in self.stream:
                self.size += len(chunk)
                yield chunk

        def close(self) -> None:
            try:
                self.stream.close()
            finally:
                if not self.logged:
                    self.logged = True
                    write(self.request, self.status, self.size)

    class AsyncCounted(httpx.AsyncByteStream):
        def __init__(self, stream: Any, request: httpx.Request, status: int) -> None:
            self.stream, self.request, self.status = stream, request, status
            self.size, self.logged = 0, False

        async def __aiter__(self) -> Any:
            async for chunk in self.stream:
                self.size += len(chunk)
                yield chunk

        async def aclose(self) -> None:
            try:
                await self.stream.aclose()
            finally:
                if not self.logged:
                    self.logged = True
                    write(self.request, self.status, self.size)

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        response = sync(self, request)
        if request.url.host not in local:
            response.stream = Counted(response.stream, request, response.status_code)
        return response

    async def handle_async(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        response = await asynchronous(self, request)
        if request.url.host not in local:
            response.stream = AsyncCounted(
                response.stream, request, response.status_code
            )
        return response

    # Process-wide patch, also shipped as source to the child processes' sitecustomize
    # (no monkeypatch there): a method assignment is the technique itself.
    httpx.HTTPTransport.handle_request = handle  # type: ignore[method-assign]
    httpx.AsyncHTTPTransport.handle_async_request = handle_async  # type: ignore[method-assign]
    return sync, asynchronous


# The annotations of `_journal` name these types: import them first.
SITECUSTOMIZE = (
    "from collections.abc import Iterator\nfrom typing import Any\n\n\n"
    + inspect.getsource(_journal)
    + f"\n\nimport os as _os\n\nif _os.environ.get({JOURNAL_ENV!r}):\n"
    + f"    _journal(_os.environ[{JOURNAL_ENV!r}])\n"
)


class Journal:
    """The request log: entries after a mark, as logged by every process."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.touch()

    def mark(self) -> int:
        return self.path.stat().st_size

    def since(self, mark: int) -> list[dict[str, Any]]:
        with self.path.open("rb") as log:
            log.seek(mark)
            return [json.loads(line) for line in log.read().splitlines() if line]


def _summary(entries: list[dict[str, Any]]) -> dict[str, object]:
    methods = Counter(entry["method"] for entry in entries)
    return {
        "requests": len(entries),
        "bytes": sum(entry["bytes"] for entry in entries),
        "methods": dict(sorted(methods.items())),
    }


def _asked(entries: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return sorted((entry["method"], entry["url"]) for entry in entries)


# --------------------------------------------------------------------------
# The live session
# --------------------------------------------------------------------------


class CountedMcp:
    """``imgw mcp`` whose calls keep the requests they made in the log."""

    def __init__(self, server: McpServer, session: "ChmiLive") -> None:
        self.server = server
        self.session = session

    def call(self, tool: str, arguments: Mapping[str, object]) -> McpAnswer:
        mark = self.session.journal.mark()
        answer = self.server.call(tool, arguments)
        self.session.traffic["mcp"] = self.session.journal.since(mark)
        return answer


class ChmiLive(Live):
    """The live session of ``test_interfaces_live`` seeded from ČHMÚ."""

    def __init__(
        self,
        base: Path,
        work: Path,
        env: Mapping[str, str],
        client: httpx.Client,
        journal: Journal,
    ) -> None:
        super().__init__(base, work, env, client)
        self.journal = journal
        self.plans: tuple[StorePlan, ...] = ()
        self.seeded: list[dict[str, Any]] = []
        # Requests and the last answer of each interface in the current case.
        self.traffic: dict[str, list[dict[str, Any]]] = {}
        self.answers: dict[str, Any] = {}

    def seed(self) -> None:
        """Snapshots of the store and of the project, each listing read once."""
        root, project = self.root, self.work / PROJECT_DIR
        mark = self.journal.mark()
        with self.local():
            init_store(root)
            self.save("empty", root)
            hydro = _patiently(
                lambda: check_store(
                    root,
                    datasets=[HYDRO],
                    stations=[STATION],
                    years=YEARS,
                    plan=self.work / HYDRO_PLAN,
                )
            )
            assert [(item.archive.year, item.status) for item in hydro.items] == [
                *((year, "missing") for year in PUBLISHED),
                (UNPUBLISHED, "unverifiable"),
            ], hydro
            meteo = _patiently(
                lambda: check_store(
                    root,
                    datasets=[METEO],
                    stations=[METEO_STATION],
                    plan=self.work / METEO_PLAN,
                )
            )
            assert [item.status for item in meteo.items] == ["missing"] * 4, meteo
            self.plans = (hydro, meteo)
            init_project(project, store_dir=root)
            self.save("p_init", project)
            add_project_task(
                project, name="przeplywy", command="series select", options=HYDRO_TASK
            )
            add_project_task(
                project, name="opady", command="series select", options=METEO_TASK
            )
            for name, plan in (("przeplywy", hydro), ("opady", meteo)):
                pinned = _patiently(
                    functools.partial(
                        download_project, project, tasks=[name], plan=plan
                    )
                )
                assert pinned.tasks == {name: "current"}, pinned
            self.save("p_done", project)
            self.save("pinned", root)
            catalog = _patiently(lambda: build_catalog(root, provider="CHMI"))
            assert (catalog.status, catalog.provider) == ("created", "CHMI"), catalog
            self.save("full", root)
            self.values = {
                ROOT: str(root),
                ARCHIVE: self.version(ARCHIVE_SLOT),
                METEO_ARCHIVE: self.version(METEO_SLOT),
                SERIES: self.version(f"series:{HYDRO}"),
            }
        self.seeded = self.journal.since(mark)

    def version(self, slot: str) -> str:
        entry = current_version(self.root, slot=slot)
        assert entry is not None and entry.version is not None, slot
        return entry.version.relative_to(self.root).as_posix()

    def call(self, interface: str, command: str, options: Mapping[str, object]) -> Any:
        """The answer of one interface; its ČHMÚ requests are kept per case."""
        if interface == "rest" and isinstance(options.get("plan"), str):
            # REST takes the plan as an imgw-plan/1 object with root ".".
            plan = json.loads(Path(str(options["plan"])).read_text(encoding="utf-8"))
            options = {**options, "plan": {**plan, "root": "."}}
        mark = self.journal.mark()
        answer = super().call(interface, command, options)
        self.traffic[interface] = self.journal.since(mark)
        self.answers[interface] = answer
        return answer

    def run_case(self, command: str, index: int, case: Case) -> dict[str, list[str]]:
        self.traffic, self.answers = {}, {}
        return super().run_case(command, index, case)

    def run_mcp_case(
        self, command: str, index: int, case: Case, mcp: Any
    ) -> dict[str, list[str]]:
        self.traffic, self.answers = {}, {}
        return super().run_mcp_case(command, index, case, mcp)

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
        """Rows of ``Live.record`` with the requests of each interface."""
        asked = self.traffic.get("python", [])
        for interface, entries in self.traffic.items():
            if interface != "python" and _asked(entries) != _asked(asked):
                problems[interface].append(
                    f"inne żądania niż Python: {_summary(entries)} zamiast "
                    f"{_summary(asked)}"
                )
        start = len(self.rows)
        super().record(
            kind,
            name,
            index,
            attempts=attempts,
            outcomes=outcomes,
            seconds=seconds,
            problems=problems,
            tolerated=tolerated,
        )
        for row in self.rows[start:]:
            row |= _summary(self.traffic.get(str(row["interface"]), []))

    def totals(self) -> dict[str, object]:
        """Requests and bytes of the seed and of each interface (report rows)."""
        result: dict[str, object] = {"seed": _summary(self.seeded)}
        for interface in INTERFACES:
            rows = [row for row in self.rows if row["interface"] == interface]
            result[interface] = {
                "requests": sum(cast(int, row.get("requests", 0)) for row in rows),
                "bytes": sum(cast(int, row.get("bytes", 0)) for row in rows),
            }
        result["all"] = _summary(self.journal.since(0))
        return result

    def report(self, started: datetime, path: str) -> None:
        super().report(started, path)
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        document["traffic"] = self.totals()
        Path(path).write_text(
            json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )


@pytest.fixture(scope="module")
def chmi(tmp_path_factory) -> Iterator[ChmiLive]:
    """Fresh temporary store seeded from ČHMÚ, ``imgw server`` and the request log."""
    started = datetime.now(UTC)
    base = tmp_path_factory.mktemp("chmi-live")
    work = base / "praca"
    work.mkdir()
    journal = Journal(base / "requests.jsonl")
    hook = base / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("IMGW_")
    }
    paths = [str(hook), *filter(None, [env.get("PYTHONPATH")])]
    env |= {
        "IMGW_REFERENCE_DIR": DATA_DIR,
        "PYTHONPATH": os.pathsep.join(paths),
        JOURNAL_ENV: str(journal.path),
    }
    served = env | {
        "IMGW_ROOT": str(base / "magazyn"),
        "IMGW_STORE_WRITES_ENABLED": "true",
        "IMGW_STORE_WRITE_TOKEN": TOKEN,
    }
    originals = _journal(str(journal.path))
    try:
        with (
            _server(base, work, served) as url,
            httpx.Client(base_url=url, timeout=CALL_TIMEOUT, trust_env=False) as client,
        ):
            session = ChmiLive(base, work, env, client, journal)
            session.seed()
            yield session
    finally:
        # Restores the transports patched by _journal (no monkeypatch in a fixture
        # that outlives tests, nor in the sitecustomize of the child processes).
        httpx.HTTPTransport.handle_request = originals[0]  # type: ignore[method-assign]
        httpx.AsyncHTTPTransport.handle_async_request = originals[1]  # type: ignore[method-assign]
    totals = session.totals()
    print(
        f"\nŻądania do ČHMÚ (liczba, bajty): {json.dumps(totals, ensure_ascii=False)}"
    )
    if path := os.environ.get("IMGW_LIVE_REPORT"):
        session.report(started, path)


@pytest.fixture(scope="module")
def chmi_mcp(chmi: ChmiLive) -> Iterator[CountedMcp]:
    """``imgw mcp`` started once, as an MCP client starts it, in the CLI's directory."""
    pytest.importorskip("mcp")
    from anyio.from_thread import start_blocking_portal
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    command, *prefix = imgw_executable()
    server = StdioServerParameters(
        command=command, args=[*prefix, "mcp"], env=chmi.env, cwd=chmi.work
    )
    with (
        (chmi.base / "imgw-mcp.log").open("w", encoding="utf-8") as log,
        start_blocking_portal() as portal,
        portal.wrap_async_context_manager(
            Client(stdio_client(server, errlog=log), read_timeout_seconds=CALL_TIMEOUT)
        ) as client,
    ):
        yield CountedMcp(McpServer(portal, client), chmi)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_the_chmi_run_takes_only_catalog_commands():
    names = [schema["x-imgw"]["command"] for schema in COMMANDS["commands"]]
    assert set(CASES) <= set(names)
    indices = {
        (name, index) for name, cases in CASES.items() for index in range(len(cases))
    }
    assert set(EXPECTED) <= indices and set(MCP_CASES) <= indices


@pytest.mark.parametrize("command", list(CASES))
def test_every_chmi_case_answers_alike_live_in_python_imgw_and_rest(command, chmi):
    found: dict[str, list[str]] = {}
    for index, case in enumerate(CASES[command]):
        for interface, lines in chmi.run_case(command, index, case).items():
            found[f"{index}:{interface}"] = lines
        answer = chmi.answers.get("python")
        expected = EXPECTED.get((command, index))
        if expected is None or not isinstance(answer, PythonAnswer):
            continue
        if answer.envelope is not None:
            rooted = case.store is not None and command in ROOTED
            document = answer.envelope.to_json(root=chmi.root if rooted else None)
            if not expected(document):
                found[f"{index}:oczekiwane"] = [json.dumps(document)[:3000]]
    assert found == {}


@pytest.mark.parametrize(("command", "index"), MCP_CASES)
def test_chmi_reads_answer_alike_in_python_and_imgw_mcp(command, index, chmi, chmi_mcp):
    assert chmi.run_mcp_case(command, index, CASES[command][index], chmi_mcp) == {}


def test_listing_rows_match_the_http_headers_of_the_files(chmi):
    """Listing minute and size = Last-Modified and Content-Length; ETag of both."""
    listed = [
        item for plan in chmi.plans for item in plan.items if item.status == "missing"
    ]
    assert len(listed) == 6
    full = chmi.seeds / "full"
    with httpx.Client(headers=_IDENTIFY, timeout=60, trust_env=False) as client:
        directory = client.head(f"{BASE_URL}{PRECIPITATION}")
        assert directory.status_code == 200
        assert directory.headers["content-type"].startswith("text/html")
        # nginx autoindex: no validators and no length (chunked).
        assert not {"etag", "last-modified", "content-length"} & set(directory.headers)
        for item in listed:
            head = client.head(item.archive.url)
            assert head.status_code == 200, item.archive.url
            moment = parsedate_to_datetime(head.headers["last-modified"])
            size = int(head.headers["content-length"])
            assert moment.strftime("%Y-%m-%dT%H:%MZ") == item.remote_listed_at
            assert size == item.content_length
            assert head.headers["etag"] == f'"{int(moment.timestamp()):x}-{size:x}"'
            # The stored version keeps the signal of its GET: the same headers.
            entry = current_version(full, slot=_archive_slot(item.archive))
            assert entry is not None and entry.version is not None
            http = read_meta(entry.version).extra["http"]
            assert (http["etag"], http["last_modified"]) == (
                head.headers["etag"],
                head.headers["last-modified"],
            )


def test_seeded_store_scans_clean_with_the_chmi_license_everywhere(chmi):
    full = chmi.seeds / "full"
    entries = list(iter_store(full))
    assert [entry.problem for entry in entries if entry.kind == "problem"] == []
    assert {entry.provider for entry in entries} == {"CHMI"}
    sidecars = sorted(full.rglob("*.meta.json"))
    assert len(sidecars) == 6 + 2 + 2 + 1  # files, station lists, series, catalog
    for sidecar in sidecars:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert (meta["country"], meta["provider"]) == ("CZ", "CHMI"), sidecar
        assert meta["license"]["id"] == "CC-BY-4.0", sidecar
        assert meta["license"]["attribution"].startswith(ATTRIBUTION), sidecar
