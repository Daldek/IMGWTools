"""Contract between interfaces: Python, ``imgw`` and REST answer every command alike.

Spec §13 (ADR-002), plan U14. Every catalog command with a REST route runs on the
fixture store against recorded IMGW answers through ``run_command``, the ``imgw``
CLI and the REST API. The CLI prints ``CommandResult.to_json(root)`` and REST
answers ``to_json(root, server=True)`` (the root as ``"."``), so the three documents
are equal after a canonical JSON dump; writes leave identical trees after identical
requests. Every registered error code is reported with the code, exit code and HTTP
status of §13.5; every envelope and error document satisfies the §13.5–§13.6
schemas of ``contract_schemas.json``; the same ``limit``/``offset`` gives the same
page everywhere; slots and versions taken from answers work in ``current_version``
and as ``imgw --version`` with ``--root``. No request leaves the recordings.
"""

import functools
import importlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import respx

from imgwtools import (
    ERROR_CODES,
    IMGWCancelledError,
    IMGWError,
    check_command,
    current_version,
    init_store,
    run_command,
    store,
    sync_pmaxtp,
)
from imgwtools.exceptions import describe_os_error
from imgwtools.messages import localize
from tests.contract.support import (
    DAILY,
    H2024,
    NEW,
    PRECIP,
    RABA,
    V3,
    FakeImgw,
    canonical,
    cli_words,
    command_document,
    current_path,
    envelope_errors,
    rest_request,
    schema_errors,
    slots,
    snapshot,
    stamps,
)

CATALOG = command_document()
EXIT_CODES = CATALOG["exit_codes"]
ROUTES = {
    schema["x-imgw"]["command"]: schema["x-imgw"]
    for schema in CATALOG["commands"]
    if schema["x-imgw"]["rest"] is not None
}
POST_COMMANDS = [
    name for name, meta in ROUTES.items() if meta["rest"]["method"] == "POST"
]
INTERFACES = ("python", "cli", "rest")
# Notice labels of the CLI stderr (spec §13.10); its lines are for a person, so they
# are in the language of IMGW_LANG, Polish by default.
LABELS = {"info": "Informacja", "warning": "Ostrzeżenie", "error": "Błąd"}


def line_of(notice):
    """The stderr line the CLI prints for a notice."""
    return f"{LABELS[notice.level]}: {localize(notice.text, 'pl')}"


# Placeholders of versions relative to the root, resolved in the served store.
ARCHIVE, SERIES = "<archive>", "<series>"
PLACEHOLDERS = {
    ARCHIVE: f"archive:{PRECIP}:2001/2001_01_o.zip",
    SERIES: f"series:{DAILY}",
}


@dataclass(frozen=True)
class Case:
    """
    Options of one run of a command (JSON form, without ``root``).

    ``store``: ``None`` = no root; ``"served"`` = the shared read-only store;
    ``"empty"`` and ``"fixture"`` = a fresh store for each interface (writes).
    """

    options: dict[str, object]
    store: str | None = None


CASES: dict[str, list[Case]] = {
    "datasets list": [Case({"kind": "hydro", "limit": 2, "offset": 1})],
    "datasets files": [
        Case(
            {
                "dataset": "hydro/dobowe",
                "years": "2021-2023",
                "months": [1, 2],
                "limit": 3,
                "offset": 1,
            }
        )
    ],
    "datasets providers": [Case({"limit": 1, "offset": 1})],
    "stations find": [
        Case({"kind": "hydro", "query": "raba", "provider": "IMGW-PIB", "limit": 2}),
        Case({"source": "store", "query": "1491", "offset": 1}, "served"),
    ],
    "current hydro": [Case({"station": RABA})],
    "current meteo": [Case({"limit": 1, "offset": 1})],
    "current synop": [Case({"station_name": "raba"})],
    "current warnings": [Case({"limit": 5})],
    "current hydro-states": [Case({"main_only": True}), Case({"offset": 1})],
    "pmaxtp fetch": [Case({"latitude": "52.23", "longitude": 21.01})],
    "pmaxtp url": [Case({"latitude": 52.23, "longitude": 21.01, "method": "AMP"})],
    "pmaxtp check": [Case({"latitude": 52.23, "longitude": 21.01}, "served")],
    "pmaxtp sync": [
        Case({"latitude": 52.23, "longitude": 21.01, "method": "POT"}, "empty")
    ],
    "pmaxtp read": [Case({"ind_x": 751, "ind_y": 317}, "served")],
    "store info": [Case({}, "served")],
    "store scan": [Case({"kind": "archive", "limit": 4, "offset": 2}, "served")],
    "store check": [Case({"datasets": [DAILY], "years": "2024"}, "served")],
    "store sync": [Case({"datasets": ["hydro/dobowe"], "years": [2024]}, "empty")],
    "store catalog": [Case({}, "empty")],
    "store export": [
        Case({"version": ARCHIVE}, "served"),
        Case({"version": ARCHIVE, "format": "jsonl"}, "served"),
    ],
    "series build": [Case({"dataset": PRECIP}, "fixture")],
    "series select": [
        Case({"dataset": "hydro/dobowe", "stations": [RABA], "years": "2024"}, "served")
    ],
    "series read": [
        Case(
            {
                "dataset": DAILY,
                "station": RABA,
                "variables": ["H", "Q"],
                "start": "2024-01-01",
                "limit": 5,
                "offset": 1,
            },
            "served",
        )
    ],
    "series summary": [Case({"version": SERIES, "stations": [RABA]}, "served")],
    "series export": [
        Case(
            {
                "dataset": DAILY,
                "station": RABA,
                "variables": "H,Q",
                "end": "2024-03-31",
            },
            "served",
        )
    ],
    "commands list": [Case({}), Case({"lang": "en"})],
    "commands schema": [
        Case({"command": "series export"}),
        Case({}),
        Case({"command": "store sync", "lang": "en"}),
    ],
    "commands guide": [Case({}), Case({"format": "llms", "lang": "en"})],
}


@pytest.fixture(scope="module")
def served_root(tmp_path_factory, fixture_root):
    """Read-only store of the read commands: the fixture store plus a PMAXTP cell."""
    root = tmp_path_factory.mktemp("served") / "store"
    shutil.copytree(fixture_root, root)
    with respx.mock(assert_all_called=False) as router:
        FakeImgw(router).publish_pmaxtp("pmaxtp_pot_first")
        sync_pmaxtp(root, latitude=52.23, longitude=21.01)
    return root


@pytest.fixture
def recorded(imgw):
    """Recorded IMGW for every command: archives, station lists, live API, PMAXTP."""
    imgw.publish(H2024, V3, NEW)
    imgw.publish_catalog_sources()
    imgw.publish_live()
    imgw.publish_pmaxtp("pmaxtp_pot_first", "pmaxtp_amp")
    return imgw


@pytest.fixture
def relative_reference_dir(monkeypatch, server):
    """Relative reference-data directory: texts name it alike in every interface."""
    monkeypatch.setattr(server, "reference_dir", Path("brak-danych-referencyjnych"))


def rooted(options: dict[str, object], root: Path | None) -> dict[str, object]:
    return dict(options) if root is None else {"root": root, **options}


def resolved(options: dict[str, object], root: Path | None) -> dict[str, object]:
    """Options with version placeholders replaced by versions relative to ``root``."""
    result = dict(options)
    for name, value in options.items():
        if isinstance(value, str) and value in PLACEHOLDERS:
            assert root is not None
            version = current_path(root, PLACEHOLDERS[value])
            result[name] = version.relative_to(root).as_posix()
    return result


def fresh_store(kind: str, root: Path, fixture_root: Path) -> None:
    """A new store at ``root``: initialised empty or copied from the fixture store."""
    if root.exists():
        shutil.rmtree(root)
    if kind == "empty":
        init_store(root)
    else:
        shutil.copytree(fixture_root, root)


def answer(interface, command, options, root, *, cli, rest, headers=None, check=False):
    """The answer of one interface: an envelope, a Click result or an HTTP response."""
    if interface == "python":
        dispatch = check_command if check else run_command
        return dispatch(command, options=rooted(options, root))
    if interface == "cli":
        flags = ["--check"] if check else []
        return cli(*cli_words(command, rooted(options, root)), *flags)
    request = rest_request(command, options)
    if check:
        request["url"] += "?check=true"
    return rest.request(**request, headers=headers)


def compact(document: object) -> str:
    """The one-line JSON the CLI prints and REST sends (spec §13.10)."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def assert_alike(command, python, printed, answered, root):
    """Python envelope = CLI stdout = REST body (canonical JSON; streams: bytes)."""
    if ROUTES[command]["result"] == "stream" and not python.check:
        data = "".join(python.result).encode("utf-8")
        assert printed.exit_code == 0, printed.output
        assert printed.stdout_bytes == data
        assert answered.status_code == 200, answered.text
        assert answered.content == data
        assert answered.headers["x-imgw-status"] == python.status == "ok"
        notices = [
            {"level": n.level, "code": n.code, "text": n.text} for n in python.notices
        ]
        assert json.loads(answered.headers["x-imgw-notices"]) == notices
        # Data exports name the license of their provider; the guide is no data.
        exported = ROUTES[command]["function"].startswith("export_")
        assert ("license_terms" in {notice["code"] for notice in notices}) == exported
        for notice in python.notices:
            assert printed.stderr.count(line_of(notice)) == 1
        return
    local = python.to_json(root=root)
    served = python.to_json(root=root, server=True)
    assert envelope_errors(local) == []
    assert envelope_errors(served) == []
    assert printed.exit_code == EXIT_CODES[python.status], printed.output
    assert printed.stdout == compact(json.loads(printed.stdout)) + "\n"
    assert canonical(json.loads(printed.stdout)) == canonical(local)
    assert answered.status_code == 200, answered.text
    assert answered.headers["content-type"] == "application/json"
    assert canonical(answered.json()) == canonical(served)
    if root is None:  # no root to write as "." in REST: the very same bytes
        assert printed.stdout_bytes == answered.content + b"\n"
    else:  # REST never shows the server's root (spec §13.1 p. 4)
        assert str(root) not in answered.text


# --------------------------------------------------------------------------
# Every command with a REST route: Python = CLI = REST
# --------------------------------------------------------------------------


@pytest.mark.parametrize("command", list(ROUTES))
def test_every_rest_command_answers_alike_in_python_cli_and_rest(
    command,
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    fixture_root,
    served_root,
    recorded,
    frozen,
    relative_reference_dir,
):
    for case in CASES[command]:
        writes = case.store in ("empty", "fixture")
        if writes:
            root = tmp_path / "store"
        else:
            root = served_root if case.store == "served" else None
        monkeypatch.setattr(server, "root", root)
        options = case.options if writes else resolved(case.options, root)
        local = options
        if ROUTES[command]["result"] == "list" and "limit" not in options:
            # REST pages by IMGW_API_MAX_LIMIT when no limit is given (spec §13.6).
            local = {"limit": server.api_max_limit, **options}
        given = {"python": local, "cli": local, "rest": options}
        before = stamps(served_root)
        answers, requests, trees = {}, {}, {}
        for interface in INTERFACES:
            if writes:
                fresh_store(case.store, root, fixture_root)
            start = len(recorded.router.calls)
            answers[interface] = answer(
                interface,
                command,
                given[interface],
                root,
                cli=cli,
                rest=rest,
                headers=writable,
            )
            requests[interface] = recorded.traffic(start)
            if writes:
                trees[interface] = snapshot(root)

        assert_alike(command, answers["python"], answers["cli"], answers["rest"], root)
        assert requests["python"] == requests["cli"] == requests["rest"]
        if writes:
            assert trees["python"] == trees["cli"] == trees["rest"]
        assert stamps(served_root) == before
        if root is not None and ROUTES[command]["result"] != "stream":
            # Every slot of an answer names a version current_version finds (§13.7).
            for slot in slots(answers["python"].to_json(root=root)):
                assert current_version(root, slot=slot).slot == slot


@pytest.mark.parametrize("command", POST_COMMANDS)
def test_every_write_is_planned_alike_by_check_in_python_cli_and_rest(
    command,
    cli,
    rest,
    server,
    monkeypatch,
    tmp_path,
    fixture_root,
    recorded,
    frozen,
    relative_reference_dir,
):
    (case,) = CASES[command]
    root = tmp_path / "store"
    fresh_store(case.store, root, fixture_root)
    monkeypatch.setattr(server, "root", root)  # writes stay disabled
    before = stamps(root)

    python, printed, answered = (
        answer(i, command, case.options, root, cli=cli, rest=rest, check=True)
        for i in INTERFACES
    )

    assert python.check is True
    assert_alike(command, python, printed, answered, root)
    assert answered.json()["result"]["root"] == "."
    assert stamps(root) == before
    assert recorded.downloads() == []


# --------------------------------------------------------------------------
# Paging: the same limit and offset give the same page (spec §13.6)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "options", "stored"),
    [
        ("datasets list", {}, False),
        ("current hydro", {}, False),
        ("store scan", {}, True),
        ("series summary", {"dataset": DAILY}, True),
    ],
)
@pytest.mark.parametrize(
    ("limit", "offset"), [(4, 0), (4, 4), (3, 9), (1, 3), (5, 20)], ids=str
)
def test_same_limit_and_offset_give_the_same_page_in_every_interface(
    command,
    options,
    stored,
    limit,
    offset,
    cli,
    rest,
    server,
    monkeypatch,
    served_root,
    recorded,
):
    root = served_root if stored else None
    monkeypatch.setattr(server, "root", root)
    window = {**options, "limit": limit, "offset": offset}
    whole = run_command(command, options=rooted(options, root))

    python, printed, answered = (
        answer(i, command, window, root, cli=cli, rest=rest) for i in INTERFACES
    )

    documents = [python.to_json(root=root), json.loads(printed.stdout), answered.json()]
    assert [envelope_errors(document) for document in documents] == [[], [], []]
    pages = [document["result"] for document in documents]
    assert len({canonical(page) for page in pages}) == 1
    (page, *_) = pages
    assert (page["total"], page["limit"], page["offset"]) == (
        whole.result.total,
        limit,
        offset,
    )
    everything = whole.to_json(root=root)["result"]["items"]
    assert page["items"] == everything[offset : offset + limit]
    assert len(everything) == whole.result.total > 3


# --------------------------------------------------------------------------
# Versions of REST answers as imgw --version with --root
# --------------------------------------------------------------------------

# Kind of a scanned version → command reading it and its other options.
READERS = {
    "archive": ("store export", {}),
    "series": ("series summary", {"limit": 50}),
    "pmaxtp": ("pmaxtp read", {"ind_x": 751, "ind_y": 317}),
}
# Station lists are read by stations find, not exported as records.
STATION_LISTS = ("pl.imgw.hydro_stations", "pl.imgw.meteo_stations")


def test_versions_answered_by_rest_work_as_imgw_version_with_root(
    cli, rest, server, monkeypatch, served_root
):
    monkeypatch.setattr(server, "root", served_root)
    read = []
    for kind, (command, extra) in READERS.items():
        scanned = rest.get("/api/v1/store/scan", params={"kind": kind}).json()
        for entry in scanned["result"]["items"]:
            if entry["slot"].split(":")[1] in STATION_LISTS:
                continue
            options = {"version": entry["version"], **extra}

            python, printed, answered = (
                answer(i, command, options, served_root, cli=cli, rest=rest)
                for i in INTERFACES
            )

            assert not Path(entry["version"]).is_absolute()
            assert_alike(command, python, printed, answered, served_root)
            read.append(entry["version"])
    assert len(read) == 9  # 5 record archives, 3 series versions, 1 PMAXTP cell


# --------------------------------------------------------------------------
# Error codes (spec §13.5): the same code, exit code and HTTP status
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """A command failing with one error code and the interfaces that report it."""

    command: str
    options: dict[str, object]
    root: Path | None = None
    interfaces: tuple[str, ...] = INTERFACES
    method: str | None = None  # HTTP method other than the route's


@dataclass(frozen=True)
class Setting:
    """What a scenario may prepare: a store copy, recorded answers, patches."""

    tmp_path: Path
    fixture_root: Path
    imgw: FakeImgw
    monkeypatch: pytest.MonkeyPatch

    def store(self) -> Path:
        root = self.tmp_path / "store"
        shutil.copytree(self.fixture_root, root)
        return root

    def raising(self, module: object, name: str, error: BaseException) -> None:
        """Public function ``name`` (signature kept for the dispatcher) raises."""
        original = getattr(module, name)

        @functools.wraps(original)
        def fake(*args, **kwargs):
            raise error

        self.monkeypatch.setattr(module, name, fake)


def _validation_error(setting: Setting) -> Scenario:
    # One validator of the library writes the detail of every interface (§13.1).
    return Scenario("pmaxtp fetch", {"latitude": "1", "longitude": "21.01"})


def _not_found(setting: Setting) -> Scenario:
    return Scenario("pmaxtp read", {"ind_x": 1, "ind_y": 1}, setting.store())


def _conflict(setting: Setting) -> Scenario:
    root = setting.store()
    (root / "notatki").mkdir()
    (root / "notatki" / "kartograf-store.json").write_text(
        json.dumps({"schema": "kartograf-store/1"}), encoding="utf-8"
    )  # a Kartograf store inside the store
    return Scenario("series build", {"dataset": PRECIP}, root)


def _source_unavailable(setting: Setting) -> Scenario:
    setting.imgw.answer("hydro_current_outage")
    return Scenario("current hydro", {})


def _missing_dependency(setting: Setting) -> Scenario:
    for name in ("pyarrow", "pyarrow.parquet"):
        setting.monkeypatch.setitem(sys.modules, name, None)
    options: dict[str, object] = {"dataset": DAILY, "station": RABA}
    return Scenario("series read", options, setting.fixture_root)


def _data_error(setting: Setting) -> Scenario:
    root = setting.store()
    series = current_path(root, f"series:{PRECIP}")
    series.write_text("{}", encoding="utf-8")  # no longer the bytes of the sidecar
    return Scenario("series summary", {"dataset": PRECIP}, root)


def _store_unavailable(setting: Setting) -> Scenario:
    root = setting.tmp_path / "nie-magazyn"
    root.mkdir()
    return Scenario("series summary", {"dataset": DAILY}, root)


def _io_error(setting: Setting) -> Scenario:
    root = setting.store()
    shutil.rmtree(root / ".incoming")
    (root / ".incoming").write_text("plik zamiast katalogu", encoding="utf-8")
    return Scenario("series build", {"dataset": PRECIP}, root)


def _cancelled(setting: Setting) -> Scenario:
    cancelled = IMGWCancelledError("Anulowano budowę szeregu")
    setting.raising(store, "build_series", cancelled)
    return Scenario("series build", {"dataset": PRECIP}, setting.store())


def _forbidden(setting: Setting) -> Scenario:
    return Scenario("series build", {"dataset": PRECIP}, setting.store(), ("rest",))


def _method_not_allowed(setting: Setting) -> Scenario:
    return Scenario("store info", {}, setting.store(), ("rest",), method="DELETE")


def _internal_error(setting: Setting) -> Scenario:
    registry = importlib.import_module("imgwtools.datasets")
    setting.raising(registry, "datasets", IMGWError("Awaria testowa rejestru zbiorów"))
    return Scenario("datasets list", {})


SCENARIOS = {
    "validation_error": _validation_error,
    "not_found": _not_found,
    "conflict": _conflict,
    "source_unavailable": _source_unavailable,
    "missing_dependency": _missing_dependency,
    "data_error": _data_error,
    "store_unavailable": _store_unavailable,
    "io_error": _io_error,
    "cancelled": _cancelled,
    "forbidden": _forbidden,
    "method_not_allowed": _method_not_allowed,
    "internal_error": _internal_error,
}


def same_text(local: object, remote: object, temporary: Path) -> None:
    """REST repeats the local text, except that it hides server directories (T21)."""
    local_text, remote_text = canonical(local), canonical(remote)
    if str(temporary) in local_text:
        assert str(temporary) not in remote_text
    else:
        assert remote_text == local_text


@pytest.mark.parametrize("code", list(ERROR_CODES))
def test_every_error_code_is_reported_alike_by_every_interface(
    code,
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    tmp_path_factory,
    fixture_root,
    imgw,
):
    spec = ERROR_CODES[code]
    scenario = SCENARIOS[code](Setting(tmp_path, fixture_root, imgw, monkeypatch))
    options = rooted(scenario.options, scenario.root)
    monkeypatch.setattr(server, "root", scenario.root)
    if code == "forbidden":
        monkeypatch.setattr(server, "store_writes_enabled", False)
    raised: BaseException | None = None

    if "python" in scenario.interfaces:
        try:
            envelope = run_command(scenario.command, options=options)
        except (IMGWError, OSError) as exc:
            raised = exc
        if code == "cancelled":  # an envelope without a report (spec §13.6)
            assert raised is None
            assert (envelope.status, envelope.result) == ("cancelled", None)
        elif code == "io_error":  # a plain OSError, mapped by every adapter
            assert isinstance(raised, OSError) and not isinstance(raised, IMGWError)
        else:
            assert isinstance(raised, IMGWError) and raised.code == code

    if "cli" in scenario.interfaces:
        printed = cli(*cli_words(scenario.command, options))
        assert printed.exit_code == spec.exit_code
        if code == "cancelled":
            assert spec.exit_code == EXIT_CODES["cancelled"]
            document = json.loads(printed.stdout)
            assert envelope_errors(document) == []
            assert document == envelope.to_json(root=scenario.root)
        else:
            assert printed.stdout == ""
            line = json.loads(printed.stderr.splitlines()[-1])
            assert schema_errors(line, "cli-error") == []
            assert line["code"] == code
            if isinstance(raised, IMGWError):
                assert canonical([line["detail"], line["details"]]) == canonical(
                    [raised.detail, dict(raised.details)]
                )

    if "rest" in scenario.interfaces:
        request = rest_request(scenario.command, scenario.options)
        if scenario.method is not None:
            request["method"] = scenario.method
        answered = rest.request(**request, headers=writable)
        # REST never cancels: a cancellation reaching it is a program error.
        reported = ERROR_CODES["internal_error" if code == "cancelled" else code]
        body = answered.json()
        assert schema_errors(body, "problem+json") == []
        assert answered.headers["content-type"] == "application/problem+json"
        assert answered.status_code == body["status"] == reported.http_status
        assert (body["code"], body["title"], body["type"], body["instance"]) == (
            reported.code,
            reported.title,
            f"urn:imgwtools:error:{reported.code}",
            request["url"],
        )
        if isinstance(raised, IMGWError):
            temporary = tmp_path_factory.getbasetemp()
            same_text(raised.detail, body["detail"], temporary)
            same_text(dict(raised.details), body["details"], temporary)


# --------------------------------------------------------------------------
# File-system errors (spec §13.5): io_error, a Polish reason and details.path
# --------------------------------------------------------------------------


def _series_index(root: Path) -> Path:
    return current_path(root, f"series:{DAILY}")


def _archive_file(root: Path) -> tuple[str, dict[str, object], Path]:
    archive = current_path(root, PLACEHOLDERS[ARCHIVE])
    return "store export", {"version": archive.relative_to(root).as_posix()}, archive


def _series_file(root: Path) -> tuple[str, dict[str, object], Path]:
    index = _series_index(root)
    return "series summary", {"version": index.relative_to(root).as_posix()}, index


def _series_sidecar(root: Path) -> tuple[str, dict[str, object], Path]:
    # Found by current_version, which never takes the version for a broken one.
    index = _series_index(root)
    return (
        "series summary",
        {"dataset": DAILY},
        index.with_name(f"{index.name}.meta.json"),
    )


def _station_parquet(root: Path) -> tuple[str, dict[str, object], Path]:
    index = _series_index(root)
    station = json.loads(index.read_text(encoding="utf-8"))["stations"][RABA]
    return (
        "series read",
        {"dataset": DAILY, "station": RABA},
        index.parent / station["file"],
    )


def _pmaxtp_cell(root: Path) -> tuple[str, dict[str, object], Path]:
    cell = current_path(root, "pmaxtp:pl.imgw.pmaxtp:POT/751_317")
    return "pmaxtp read", {"ind_x": 751, "ind_y": 317}, cell


UNREADABLE = {
    "archive-file": _archive_file,
    "series-file": _series_file,
    "series-sidecar": _series_sidecar,
    "station-parquet": _station_parquet,
    "pmaxtp-cell": _pmaxtp_cell,
}


def assert_io_error_alike(command, options, root, *, cli, rest, headers=None):
    """The library error, the CLI line and the REST problem report one io_error."""
    with pytest.raises((IMGWError, OSError)) as caught:
        run_command(command, options=rooted(options, root))
    raised = caught.value
    if isinstance(raised, IMGWError):
        assert raised.code == "io_error"
        expected = [raised.detail, dict(raised.details)]
    else:  # a plain OSError of a write, described by every adapter
        expected = list(describe_os_error(raised))
    spec = ERROR_CODES["io_error"]

    printed = cli(*cli_words(command, rooted(options, root)))
    line = json.loads(printed.stderr.splitlines()[-1])
    assert (printed.exit_code, printed.stdout, line["code"]) == (
        spec.exit_code,
        "",
        "io_error",
    )
    assert canonical([line["detail"], line["details"]]) == canonical(expected)

    answered = rest.request(**rest_request(command, options), headers=headers)
    body = answered.json()
    assert schema_errors(body, "problem+json") == []
    assert (answered.status_code, body["code"], body["title"]) == (
        spec.http_status,
        "io_error",
        spec.title,
    )
    # The CLI text with the server root hidden (paths relative to it, T21).
    assert canonical([body["detail"], body["details"]]) == canonical(expected).replace(
        f"{root}/", ""
    )
    assert str(root) not in answered.text
    return raised


@pytest.mark.parametrize("unreadable", list(UNREADABLE))
def test_an_unreadable_version_is_an_io_error_in_every_interface(
    unreadable, cli, rest, server, monkeypatch, tmp_path, served_root
):
    root = tmp_path / "store"
    shutil.copytree(served_root, root)
    command, options, target = UNREADABLE[unreadable](root)
    monkeypatch.setattr(server, "root", root)
    target.chmod(0)
    try:
        raised = assert_io_error_alike(command, options, root, cli=cli, rest=rest)
    finally:
        target.chmod(0o644)

    assert isinstance(raised, IMGWError)
    assert (raised.detail, dict(raised.details)) == (
        f"File system error: permission denied: {target}",
        {"path": str(target)},
    )


def test_a_failed_write_is_the_same_io_error_in_imgw_and_rest(
    cli, rest, writable, server, monkeypatch, tmp_path, fixture_root, imgw
):
    scenario = _io_error(Setting(tmp_path, fixture_root, imgw, monkeypatch))
    monkeypatch.setattr(server, "root", scenario.root)

    raised = assert_io_error_alike(
        scenario.command,
        scenario.options,
        scenario.root,
        cli=cli,
        rest=rest,
        headers=writable,
    )

    assert isinstance(raised, OSError) and not isinstance(raised, IMGWError)
    assert raised.filename is not None


# --------------------------------------------------------------------------
# Error documents of the adapters' own paths (spec §13.5)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "body", "code"),
    [
        ("GET", "/api/v1/nie/ma", None, "not_found"),
        (
            "POST",
            "/api/v1/pmaxtp/sync?check=true",
            {"latitude": True, "longitude": 21.01},
            "validation_error",
        ),
        ("GET", "/api/v1/datasets/list?kolor=czerwony", None, "validation_error"),
        ("GET", "/api/v1/datasets/list?limit=1001", None, "validation_error"),
        ("GET", "/api/v1/store/info", None, "store_unavailable"),
    ],
    ids=["unknown-route", "body-type", "unknown-option", "above-maximum", "no-root"],
)
def test_rest_answers_every_refused_request_with_a_problem_document(
    method, url, body, code, rest
):
    answered = rest.request(method, url, json=body)

    document = answered.json()
    spec = ERROR_CODES[code]
    assert schema_errors(document, "problem+json") == []
    assert answered.status_code == document["status"] == spec.http_status
    assert (document["code"], document["title"]) == (code, spec.title)


@pytest.mark.parametrize(
    "args",
    [
        ("datasets", "list", "--kolor", "czerwony"),
        ("datasets", "files", "--dataset", DAILY, "--years"),
        ("magazyn",),
        (),
    ],
    ids=["unknown-flag", "missing-value", "unknown-group", "no-command"],
)
def test_imgw_ends_every_syntax_error_with_a_validation_error_line(args, cli):
    printed = cli(*args)

    line = json.loads(printed.stderr.splitlines()[-1])
    assert schema_errors(line, "cli-error") == []
    assert (printed.stdout, line["code"]) == ("", "validation_error")
    assert printed.exit_code == ERROR_CODES["validation_error"].exit_code


def test_program_errors_are_internal_errors_in_imgw_and_rest(cli, rest, monkeypatch):
    registry = importlib.import_module("imgwtools.datasets")
    original = registry.datasets

    @functools.wraps(original)
    def broken(*args, **kwargs):
        raise RuntimeError("błąd programu w rejestrze")

    monkeypatch.setattr(registry, "datasets", broken)

    printed = cli("datasets", "list")
    answered = rest.get("/api/v1/datasets/list")

    spec = ERROR_CODES["internal_error"]
    line = json.loads(printed.stderr.splitlines()[-1])
    assert schema_errors(line, "cli-error") == []
    assert (printed.exit_code, line["code"]) == (spec.exit_code, "internal_error")
    body = answered.json()
    assert schema_errors(body, "problem+json") == []
    assert (answered.status_code, body["code"]) == (spec.http_status, "internal_error")
    assert "błąd programu" not in body["detail"]  # REST keeps program internals in logs
