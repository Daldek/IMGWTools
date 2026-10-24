"""Command catalog (spec §13.3, §13.6): 37 commands, validation, envelope, paging, checks."""

import functools
import importlib
import inspect
import shlex
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools import fetch, store
from imgwtools import project as project_api
from imgwtools.commands import (
    check_command,
    data_commands,
    format_command,
    run_command,
    validate_command,
)
from imgwtools.datasets import archive_files, datasets
from imgwtools.exceptions import IMGWCancelledError, IMGWValidationError
from imgwtools.project import add_project_task, download_project, init_project
from imgwtools.store.types import (
    CatalogReport,
    DownloadItem,
    DownloadReport,
    Notice,
    OperationResult,
    Page,
    PlanAction,
    PMaXTPStoreResult,
    ProjectReport,
    SeriesReport,
    StorePlan,
)
from imgwtools.testing import build_fixture_store
from tests.contract.support import (
    H2023,
    H2024,
    NEW,
    V1,
    V3,
    FakeImgw,
    archive_bytes,
    sha256,
    stamps,
)

DAILY = "pl.imgw.hydro_daily"
SEMIANNUAL = "pl.imgw.hydro_semiannual"
RABA = "149190310"
ROOT = "/data/imgw"
SPEC_COMMANDS = [
    "datasets list",
    "datasets files",
    "datasets download",
    "datasets providers",
    "stations find",
    "current hydro",
    "current meteo",
    "current synop",
    "current warnings",
    "current hydro-states",
    "pmaxtp fetch",
    "pmaxtp url",
    "pmaxtp check",
    "pmaxtp sync",
    "pmaxtp read",
    "store init",
    "store info",
    "store scan",
    "store check",
    "store sync",
    "store catalog",
    "store export",
    "series build",
    "series select",
    "series read",
    "series summary",
    "series export",
    "project init",
    "project add",
    "project remove",
    "project set-store",
    "project download",
    "project check",
    "project status",
    "project verify",
    "commands list",
    "commands schema",
    "commands guide",
]
PUBLIC_MODULES = (
    "imgwtools.datasets",
    "imgwtools.fetch",
    "imgwtools.stations",
    "imgwtools.urls",
    "imgwtools.store",
    "imgwtools.project",
    "imgwtools.commands",
    "imgwtools.agent_guide",
)
# Valid options of every command in their JSON form (keys, numbers, arrays).
VALID: dict[str, list[dict[str, object]]] = {
    "datasets list": [{}, {"kind": "hydro", "limit": 5, "offset": 1}],
    "datasets files": [
        {"dataset": DAILY, "years": [2020, "2022-2023"], "months": [1, 2]},
        {"dataset": SEMIANNUAL, "years": [2024], "params": ["H", "Q"]},
    ],
    "datasets download": [
        {
            "dataset": "pl.imgw.meteo_synop_monthly",
            "years": [1998],
            "output": "/tmp/pobrane dane",
        }
    ],
    "stations find": [
        {"kind": "hydro", "query": "raba", "limit": 20},
        {"source": "store", "root": ROOT},
    ],
    "current hydro": [{"station": RABA}],
    "current meteo": [{}],
    "current synop": [{"station": "12375", "station_name": "Warszawa"}],
    "current warnings": [{"kind": "meteo"}],
    "current hydro-states": [{"main_only": True}],
    "pmaxtp fetch": [{"latitude": 52.23, "longitude": 21.01, "method": "AMP"}],
    "pmaxtp url": [{"latitude": 49.0, "longitude": 24.5}],
    "pmaxtp check": [
        {
            "root": ROOT,
            "latitude": 52.23,
            "longitude": 21.01,
            "ind_x": 751,
            "ind_y": 317,
        }
    ],
    "pmaxtp sync": [{"root": ROOT, "latitude": 52.23, "longitude": 21.01}],
    "pmaxtp read": [
        {
            "root": ROOT,
            "ind_x": 751,
            "ind_y": 317,
            "version": "pmaxtp/versions/POT/751_317/v/cell.json",
        }
    ],
    "store init": [{"root": "/data/imgw store"}],
    "store info": [{"root": ROOT}],
    "store scan": [{"root": ROOT, "kind": "problem", "offset": 0}],
    "store check": [
        {
            "root": ROOT,
            "datasets": [DAILY, "pl.imgw.meteo_precip_daily"],
            "years": ["2023-2025"],
            "months": [1],
            "plan": "/tmp/plan 1.json",
        }
    ],
    "store sync": [
        {"root": ROOT, "plan": "/tmp/plan.json", "series": False},
        {"root": ROOT, "datasets": [DAILY], "years": [2024]},
    ],
    "store catalog": [{"root": ROOT, "user_locations": "/tmp/moje położenia.csv"}],
    "store export": [
        {
            "version": "archives/versions/a/codz_2024/v/codz_2024.zip",
            "root": ROOT,
            "format": "jsonl",
            "path": "/tmp/codz.jsonl",
        }
    ],
    "series build": [{"root": ROOT, "dataset": DAILY}],
    "series select": [
        {
            "root": ROOT,
            "dataset": DAILY,
            "stations": [RABA, "150160180"],
            "variables": ["H"],
            "years": [2020, "2022-2023"],
            "year_type": "calendar",
        }
    ],
    "series read": [
        {
            "root": ROOT,
            "dataset": DAILY,
            "station": RABA,
            "variables": ["Q"],
            "start": "2024-01-01",
            "end": "2024-01-31",
            "limit": 10,
        },
        {"version": "/data/imgw/series/versions/hydro_daily/v", "station": RABA},
    ],
    "series summary": [
        {"root": ROOT, "dataset": DAILY, "stations": [RABA]},
        {"version": "series/versions/hydro_daily/v/series.json", "root": ROOT},
    ],
    "series export": [
        {
            "root": ROOT,
            "dataset": SEMIANNUAL,
            "station": RABA,
            "year_type": "hydrological",
            "format": "csv",
            "path": "/tmp/eksport.csv",
        }
    ],
    "project init": [{"project_dir": "/tmp/proj", "store_dir": "../store"}],
    "project add": [
        {
            "project_dir": "/tmp/proj",
            "name": "wisla-1",
            "command": "series select",
            "options": {"dataset": DAILY, "stations": [RABA], "years": [2024]},
            "geometry": "obszar.geojson",
        },
        {
            "project_dir": "/tmp/proj",
            "name": "cell",
            "command": "pmaxtp sync",
            "options": {"latitude": 52.23, "longitude": 21.01},
        },
    ],
    "project remove": [{"project_dir": "/tmp/proj", "name": "wisla-1"}],
    "project set-store": [{"project_dir": "/tmp/proj", "store_dir": "/mnt/imgw"}],
    "project download": [
        {
            "project_dir": "/tmp/proj",
            "tasks": ["a", "b"],
            "plan": "/tmp/plan.json",
            "update": "upgrade",
        }
    ],
    "project check": [
        {"project_dir": "/tmp/proj", "tasks": ["a"], "plan": "/tmp/plan.json"}
    ],
    "project status": [{"project_dir": "/tmp/proj"}],
    "project verify": [{"project_dir": "/tmp/proj", "tasks": ["a"]}],
    "commands list": [{}, {"lang": "en"}],
    "commands schema": [{}, {"command": "stations find"}],
    "commands guide": [{}, {"format": "llms", "lang": "en", "path": "/tmp/llms.txt"}],
}
SAMPLES = [(command, options) for command, cases in VALID.items() for options in cases]
# Invalid options rejected by validate_command and command_schema alike, with the
# option reported in ``details.option``.
INVALID: dict[str, list[tuple[dict[str, object], str]]] = {
    "datasets list": [({"kind": "both"}, "kind"), ({"limit": 0}, "limit")],
    "datasets files": [
        ({"dataset": "pl.imgw.pmaxtp", "years": [2024]}, "dataset"),
        ({"dataset": DAILY, "years": [2024], "stations": ["1491"]}, "stations"),
        ({"dataset": DAILY, "years": [2024], "months": [13]}, "months"),
    ],
    "datasets download": [
        ({"dataset": DAILY, "years": [2024], "colour": "red"}, "colour")
    ],
    "stations find": [
        ({"query": "raba", "offset": -1}, "offset"),
        ({"source": "archive"}, "source"),
    ],
    "current hydro": [({"station": "12345"}, "station")],
    "current meteo": [({"station": "abc"}, "station")],
    "current synop": [({"station": RABA}, "station")],
    "current warnings": [({"kind": "fire"}, "kind")],
    "current hydro-states": [({"main_only": "yes"}, "main_only")],
    "pmaxtp fetch": [
        ({"latitude": 1.0, "longitude": 21.0}, "latitude"),
        ({"latitude": 52.2}, "longitude"),
    ],
    "pmaxtp url": [
        ({"latitude": 52.2, "longitude": 30.0}, "longitude"),
        ({"latitude": 52.2, "longitude": 21.0, "method": "XYZ"}, "method"),
    ],
    "pmaxtp check": [
        ({"root": ROOT, "latitude": 52.2, "longitude": 21.0, "ind_x": 1}, "ind_y")
    ],
    "pmaxtp sync": [
        ({"root": ROOT, "latitude": 52.2, "longitude": 21.0, "ind_y": 1}, "ind_x")
    ],
    "pmaxtp read": [
        ({"root": ROOT, "ind_x": -1, "ind_y": 2}, "ind_x"),
        ({"root": ROOT, "ind_x": 1}, "ind_y"),
    ],
    "store init": [({}, "root")],
    "store info": [({"root": ROOT, "dataset": DAILY}, "dataset")],
    "store scan": [({"root": ROOT, "kind": "everything"}, "kind")],
    "store check": [
        (
            {"root": ROOT, "datasets": ["pl.imgw.hydro_phenomena"], "years": [2024]},
            "datasets",
        ),
        ({"root": ROOT, "datasets": [DAILY], "stations": ["1491"]}, "stations"),
    ],
    "store sync": [
        ({"root": ROOT}, "plan"),
        (
            {"root": ROOT, "plan": "/tmp/p.json", "datasets": [DAILY], "years": [2024]},
            "datasets",
        ),
    ],
    "store catalog": [({"user_locations": "/tmp/x.csv"}, "root")],
    "store export": [
        ({"version": "/v", "format": "parquet"}, "format"),
        ({"root": ROOT}, "version"),
    ],
    "series build": [({"root": ROOT, "dataset": "pl.imgw.hydro_stations"}, "dataset")],
    "series select": [
        ({"root": ROOT, "dataset": DAILY, "stations": ["1491"]}, "stations"),
        ({"root": ROOT, "dataset": DAILY}, "stations"),
    ],
    "series read": [
        ({"root": ROOT, "dataset": DAILY, "version": "/v", "station": RABA}, "dataset"),
        ({"station": RABA}, "version"),
        (
            {"root": ROOT, "dataset": DAILY, "station": RABA, "start": "2024-13-01"},
            "start",
        ),
    ],
    "series summary": [({"root": ROOT}, "version")],
    "series export": [
        ({"root": ROOT, "dataset": DAILY, "station": RABA, "format": "jsonl"}, "format")
    ],
    "project init": [({"project_dir": "/tmp/p"}, "store_dir")],
    "project add": [
        (
            {
                "project_dir": "/p",
                "name": "Zły",
                "command": "series select",
                "options": {},
            },
            "name",
        ),
        (
            {
                "project_dir": "/p",
                "name": "t",
                "command": "project init",
                "options": {},
            },
            "command",
        ),
    ],
    "project remove": [({"project_dir": "/p"}, "name")],
    "project set-store": [({"store_dir": "/s"}, "project_dir")],
    "project download": [({"project_dir": "/p", "update": "latest"}, "update")],
    "project check": [({"project_dir": "/p", "tasks": ["Zła nazwa"]}, "tasks")],
    "project status": [({"project_dir": "/p", "plan": "/tmp/x"}, "plan")],
    "project verify": [({}, "project_dir")],
    "commands list": [({"lang": "de"}, "lang")],
    "commands schema": [({"command": "store delete"}, "command")],
    "commands guide": [({"format": "html"}, "format"), ({"lang": "de"}, "lang")],
}
REJECTED = [
    (command, options, option)
    for command, cases in INVALID.items()
    for options, option in cases
]
FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
# Pins of download_project for the scenario below, recorded before ADR-002 U08; the
# catalog bytes carry meteo_kind of the fixture's meteo stations (ADR-001 errata
# 2026-10-19).
PINS_BEFORE = {
    "raba": [
        ("series", "series/versions/hydro_daily/2026-10-19_9a64f921/series.json"),
        (
            "station_series",
            "series/versions/hydro_daily/2026-10-19_9a64f921/stations/149190310.parquet",
        ),
        (
            "input",
            "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/"
            "2026-10-19_b6a19f65/codz_2024.zip",
        ),
    ],
    "cell": [("input", "pmaxtp/versions/POT/751_317/2026-10-20_2c009f3c/cell.json")],
    "catalog": [("catalog", "stations/versions/2026-10-20_daea7dd5/stations.geojson")],
}
PINS_BEFORE["sync"] = PINS_BEFORE["build"] = [
    *PINS_BEFORE["raba"][:2],
    (
        "station_series",
        "series/versions/hydro_daily/2026-10-19_9a64f921/stations/149190311.parquet",
    ),
    PINS_BEFORE["raba"][2],
]


def parse(text):
    """Map a formatted command line back to option names, as the CLI adapter does."""
    words = shlex.split(text)
    assert words[0] == "imgw"
    (command,) = [c for c in data_commands() if words[1:3] == c.name.split()]
    flags = {}
    for option in command.options:
        for flag in (option.flag, *option.aliases):
            flags[flag] = (option, True)
        flags[f"--no-{option.flag[2:]}"] = (option, False)
    options, rest = {}, words[3:]
    while rest:
        option, value = flags[rest.pop(0)]
        options[option.name] = value if option.type == "bool" else rest.pop(0)
    return command.name, options


def returning(monkeypatch, module, name, value):
    """Replace a public function (keeping its signature) by one returning or raising."""
    original = getattr(module, name)

    @functools.wraps(original)
    def fake(*args, **kwargs):
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(module, name, fake)


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("commands") / "store").root


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=False) as router:
        yield FakeImgw(router)


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in (
        "imgwtools.store.writer",
        "imgwtools.store.series",
        "imgwtools.store.catalog",
        "imgwtools.store.sync",
        "imgwtools.store.pmaxtp",
        "imgwtools.commands",
        "imgwtools.project",
    ):
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)


def test_every_command_calls_a_public_function_named_by_its_options():
    commands = data_commands()
    assert [command.name for command in commands] == SPEC_COMMANDS
    for command in commands:
        modules = [importlib.import_module(name) for name in PUBLIC_MODULES]
        found = [m for m in modules if callable(getattr(m, command.function, None))]
        assert found and not command.function.startswith("_"), command.name
        parameters = inspect.signature(getattr(found[0], command.function)).parameters
        names = [option.name for option in command.options]
        paged = {"limit", "offset"} <= set(names)
        assert paged == (command.result == "list"), command.name
        assert set(names) - {"limit", "offset"} <= set(parameters), command.name
        if command.check not in (None, "check_command"):
            assert any(callable(getattr(m, command.check, None)) for m in modules)


def test_each_option_name_has_one_type_and_each_short_alias_one_meaning():
    types, aliases = {}, {}
    for command in data_commands():
        for option in command.options:
            assert option.flag == "--" + option.name.replace("_", "-")
            types.setdefault(option.name, set()).add((option.type, option.items))
            for alias in option.aliases:
                aliases.setdefault(alias, set()).add(option.name)
    assert {name: len(found) for name, found in types.items() if len(found) > 1} == {}
    assert aliases == {
        "-r": {"root"},
        "-d": {"dataset", "datasets"},
        "-k": {"kind"},
        "-q": {"query"},
        "-s": {"station", "stations"},
        "-y": {"years"},
        "-m": {"months"},
        "-o": {"output"},
        "-p": {"path"},
        "-f": {"format"},
        "--lat": {"latitude"},
        "--lon": {"longitude"},
    }


@pytest.mark.parametrize(("command", "options"), SAMPLES)
def test_format_command_reparses_to_identical_options(command, options):
    text = format_command(command, options=options)
    name, parsed = parse(text)
    assert name == command
    assert validate_command(command, options=parsed) == validate_command(
        command, options=options
    )
    assert format_command(command, options=parsed) == text


def test_format_command_quotes_and_writes_bools_as_flags():
    assert (
        format_command("store info", options={"root": "/a b/s"})
        == "imgw store info --root '/a b/s'"
    )
    assert format_command(
        "store sync", options={"root": "/s", "plan": "/p.json", "series": True}
    ) == ("imgw store sync --root /s --plan /p.json")
    assert format_command(
        "store sync", options={"root": "/s", "plan": "/p.json", "series": False}
    ) == ("imgw store sync --root /s --plan /p.json --no-series")
    assert (
        format_command("current hydro-states", options={"main_only": "true"})
        == "imgw current hydro-states --main-only"
    )


def test_validate_command_normalizes_aliases_numbers_dates_years_and_paths(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert validate_command(
        "datasets files",
        options={
            "dataset": "hydro/dobowe",
            "years": "2023,2021-2022",
            "months": ["2", 1],
        },
    ) == {"dataset": DAILY, "years": (2021, 2022, 2023), "months": (1, 2)}
    for years, expected in (
        (2024, (2024,)),
        ("2020-2023", (2020, 2021, 2022, 2023)),
        ("2020,2022", (2020, 2022)),
        ([2020, "2022-2023"], (2020, 2022, 2023)),
    ):
        options = {"root": "s", "datasets": "hydro_daily", "years": years}
        assert validate_command("store check", options=options)["years"] == expected
    assert validate_command(
        "pmaxtp fetch", options={"latitude": " 52.23", "longitude": 21}
    ) == {"latitude": 52.23, "longitude": 21.0}
    assert validate_command(
        "series read",
        options={
            "root": "store",
            "dataset": "hydro/dobowe",
            "station": RABA,
            "variables": "Q,H,Q",
            "start": "2024-01-01",
            "end": date(2024, 2, 1),
        },
    ) == {
        "root": tmp_path / "store",
        "dataset": DAILY,
        "station": RABA,
        "variables": ("Q", "H"),
        "start": date(2024, 1, 1),
        "end": date(2024, 2, 1),
    }
    exported = validate_command(
        "store export", options={"version": "archives/versions/x", "root": "store"}
    )
    assert exported["version"] == tmp_path / "store" / "archives" / "versions" / "x"
    assert validate_command(
        "project init", options={"project_dir": "p", "store_dir": "../store"}
    ) == {"project_dir": tmp_path / "p", "store_dir": Path("../store")}
    assert validate_command(
        "store sync", options={"root": "s", "plan": "p.json", "series": True}
    ) == {"root": tmp_path / "s", "plan": tmp_path / "p.json"}
    assert (
        validate_command(
            "store sync", options={"root": "s", "plan": "p.json", "series": "false"}
        )["series"]
        is False
    )
    added = validate_command(
        "project add",
        options={
            "project_dir": "p",
            "name": "t",
            "command": "series select",
            "options": '{"dataset": "hydro/dobowe", "stations": "149190310", '
            '"years": "2020-2021"}',
        },
    )
    assert added["options"] == {
        "dataset": DAILY,
        "stations": (RABA,),
        "years": (2020, 2021),
    }


@pytest.mark.parametrize(
    ("command", "options", "option"),
    [
        ("store delete", {"root": "/s"}, "command"),
        ("datasets files", {"dataset": "meteo/dobowe/synop", "years": 2024}, "dataset"),
        ("datasets files", {"dataset": DAILY, "years": 1900}, "years"),
        (
            "datasets download",
            {"dataset": DAILY, "years": 2024, "params": "H"},
            "params",
        ),
        (
            "store check",
            {"root": "/s", "datasets": DAILY, "years": "2024-2020"},
            "years",
        ),
        ("store sync", {"root": "/s", "plan": "p.json", "months": 1}, "months"),
        ("store sync", {"root": "/s", "plan": "p.json", "series": "nie"}, "series"),
        ("stations find", {"root": "/s"}, "root"),
        ("stations find", {"source": "store"}, "root"),
        ("stations find", {"query": "   "}, "query"),
        ("pmaxtp fetch", {"latitude": "abc", "longitude": 21.0}, "latitude"),
        (
            "pmaxtp sync",
            {"root": "/s", "latitude": 52.2, "longitude": 13.9},
            "longitude",
        ),
        (
            "series select",
            {"root": "/s", "dataset": DAILY, "stations": RABA, "variables": "Tmax"},
            "variables",
        ),
        (
            "series select",
            {
                "root": "/s",
                "dataset": SEMIANNUAL,
                "stations": RABA,
                "year_type": "calendar",
            },
            "year_type",
        ),
        (
            "series read",
            {
                "root": "/s",
                "dataset": DAILY,
                "station": RABA,
                "start": "2024-02-01",
                "end": "2024-01-01",
            },
            "end",
        ),
        (
            "series read",
            {
                "root": "/s",
                "dataset": DAILY,
                "station": RABA,
                "start": "2024-01-01T00:00",
            },
            "start",
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "store info",
                "options": {},
                "geometry": "obszar.geojson",
            },
            "geometry",
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "series select",
                "options": {"dataset": DAILY, "stations": RABA},
            },
            "options",
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "series select",
                "options": {
                    "root": "/s",
                    "dataset": DAILY,
                    "stations": RABA,
                    "years": 1,
                },
            },
            "options",
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "store info",
                "options": "[1]",
            },
            "options",
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "store sync",
                "options": {"dataset": [DAILY], "years": 2024},
            },
            "options",
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "pmaxtp sync",
                "options": {"lat": 52.2, "lon": 21.0},
            },
            "options",
        ),
    ],
)
def test_validate_command_rejects_invalid_options_naming_the_option(
    command, options, option
):
    with pytest.raises(IMGWValidationError) as error:
        validate_command(command, options=options)
    assert error.value.code == "validation_error"
    assert error.value.details["option"] == option


def test_export_path_inside_a_store_is_rejected_offline(fixture_root):
    version = store.current_version(
        fixture_root, slot="archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
    ).version
    for command, options in (
        ("store export", {"version": version, "path": fixture_root / "x.csv"}),
        (
            "series export",
            {
                "root": fixture_root,
                "dataset": DAILY,
                "station": RABA,
                "path": fixture_root / "series" / "x.csv",
            },
        ),
    ):
        with pytest.raises(IMGWValidationError) as error:
            validate_command(command, options=options)
        assert error.value.details["option"] == "path"


def test_list_commands_page_after_counting_the_function_items(fixture_root):
    every = tuple(store.iter_store(fixture_root))
    assert len(every) > 3

    def scan(**paging):
        return run_command("store scan", options={"root": fixture_root, **paging})

    assert scan(limit=2, offset=1).result == Page(every[1:3], len(every), 2, 1)
    assert scan(offset=1).result == Page(every[1:], len(every), None, 1)
    assert scan(offset=len(every) + 5).result == Page(
        (), len(every), None, len(every) + 5
    )
    meteo = datasets(kind="meteo")
    page = run_command("datasets list", options={"kind": "meteo", "limit": 2}).result
    assert page == Page(meteo[:2], len(meteo), 2, 0)
    with pytest.raises(IMGWValidationError) as error:
        scan(limit=0)
    assert error.value.details["option"] == "limit"


def test_store_sync_envelope_keeps_distinct_notices_while_hooks_get_all(tmp_path, imgw):
    root = tmp_path / "store"
    store.init_store(root)
    imgw.publish(H2023, V1, archive_bytes(H2023))
    imgw.publish(H2024, V3, NEW)
    progress, notices = [], []
    result = run_command(
        "store sync",
        options={"root": root, "datasets": "hydro/dobowe", "years": "2023-2024"},
        on_progress=progress.append,
        on_notice=notices.append,
        cancel=lambda: False,
    )
    assert (result.command, result.check, result.status) == ("store sync", False, "ok")
    assert [item.status for item in result.result.items] == ["created", "created"]
    assert len(notices) > len(result.notices)
    assert result.notices == tuple(dict.fromkeys(notices))
    assert "license_terms" in {notice.code for notice in result.notices}


@pytest.mark.parametrize(
    ("failing", "status"), [((H2024,), "partial"), ((H2023, H2024), "failed")]
)
def test_store_sync_with_failed_items_is_partial_or_failed(
    tmp_path, imgw, failing, status
):
    root = tmp_path / "store"
    store.init_store(root)
    imgw.publish(H2023, V1, archive_bytes(H2023))
    imgw.publish(H2024, V3, NEW)
    for archive in failing:
        imgw.router.get(archive.url).mock(return_value=httpx.Response(500))
    result = run_command(
        "store sync",
        options={
            "root": root,
            "datasets": DAILY,
            "years": [2023, 2024],
            "series": False,
        },
    )
    assert result.status == status
    assert sum(item.status == "failed" for item in result.result.items) == len(failing)


def test_cancelled_sync_report_gives_a_cancelled_envelope(tmp_path, imgw):
    root = tmp_path / "store"
    store.init_store(root)
    imgw.publish(H2024, V3, NEW)
    result = run_command(
        "store sync",
        options={"root": root, "datasets": DAILY, "years": 2024},
        cancel=lambda: True,
    )
    assert result.status == "cancelled" and result.result.cancelled


def _download(*statuses, cancelled=False):
    items = tuple(
        DownloadItem(f"archive:{DAILY}:2024/{n}.zip", "https://x", s, None, None, None)
        for n, s in enumerate(statuses)
    )
    return DownloadReport(Path("/o"), items, cancelled)


def _plan(*statuses):
    actions = tuple(PlanAction("store check", s, "") for s in statuses)
    return StorePlan("imgw-plan/1", Path("/s"), FROZEN_AT, (), {}, actions)


def _project(tasks, *files, cancelled=False):
    results = tuple(OperationResult(None, s, None, None) for s in files)
    return ProjectReport(tasks, results, cancelled)


ARCHIVES = {"dataset": DAILY, "years": 2024}
STATUS_CASES = [
    (
        "datasets download",
        ARCHIVES,
        fetch,
        "download_archives",
        _download("downloaded", "failed"),
        "partial",
    ),
    (
        "datasets download",
        ARCHIVES,
        fetch,
        "download_archives",
        _download("failed", "failed"),
        "failed",
    ),
    (
        "datasets download",
        ARCHIVES,
        fetch,
        "download_archives",
        _download("downloaded", "cancelled", cancelled=True),
        "cancelled",
    ),
    (
        "store check",
        {"root": "/s", "datasets": DAILY, "years": 2024},
        store,
        "check_store",
        _plan("current", "check_failed"),
        "partial",
    ),
    (
        "store check",
        {"root": "/s", "datasets": DAILY, "years": 2024},
        store,
        "check_store",
        _plan("missing", "newer"),
        "ok",
    ),
    (
        "project download",
        {"project_dir": "/p"},
        project_api,
        "download_project",
        _project({"a": "failed", "b": "current"}),
        "partial",
    ),
    (
        "project download",
        {"project_dir": "/p"},
        project_api,
        "download_project",
        _project({"a": "failed"}, "failed"),
        "failed",
    ),
    (
        "project download",
        {"project_dir": "/p"},
        project_api,
        "download_project",
        _project({"a": "upgraded"}, "created", "stale_plan"),
        "partial",
    ),
    (
        "project download",
        {"project_dir": "/p"},
        project_api,
        "download_project",
        _project({"a": "cancelled"}, cancelled=True),
        "cancelled",
    ),
    (
        "series build",
        {"root": "/s", "dataset": DAILY},
        store,
        "build_series",
        SeriesReport("failed", None, 0, (), ("x",)),
        "failed",
    ),
    (
        "series build",
        {"root": "/s", "dataset": DAILY},
        store,
        "build_series",
        SeriesReport("cancelled", None, 0, (), ()),
        "cancelled",
    ),
    (
        "series build",
        {"root": "/s", "dataset": DAILY},
        store,
        "build_series",
        SeriesReport("reused", Path("/s/v"), 1, (), ()),
        "ok",
    ),
    (
        "store catalog",
        {"root": "/s"},
        store,
        "build_catalog",
        CatalogReport("failed", None, 0, 0, 0, ("x",)),
        "failed",
    ),
    (
        "pmaxtp sync",
        {"root": "/s", "latitude": 52.2, "longitude": 21.0},
        store,
        "sync_pmaxtp",
        PMaXTPStoreResult("cancelled", None, None, None, None),
        "cancelled",
    ),
]


@pytest.mark.parametrize(
    ("command", "options", "module", "function", "report", "status"), STATUS_CASES
)
def test_run_command_status_follows_the_report(
    monkeypatch, command, options, module, function, report, status
):
    returning(monkeypatch, module, function, report)
    result = run_command(command, options=options)
    assert (result.status, result.result) == (status, report)


def test_cancelled_error_gives_cancelled_envelope_with_notices_before_it(monkeypatch):
    notice = Notice("info", "license_terms", "Źródło: IMGW-PIB")
    original = store.export_series

    @functools.wraps(original)
    def export(*args, on_notice=None, **kwargs):
        on_notice(notice)
        on_notice(notice)
        raise IMGWCancelledError("Anulowano eksport")

    monkeypatch.setattr(store, "export_series", export)
    seen = []
    result = run_command(
        "series export",
        options={"root": "/s", "dataset": DAILY, "station": RABA},
        on_notice=seen.append,
    )
    assert (result.status, result.result, result.notices) == (
        "cancelled",
        None,
        (notice,),
    )
    assert seen == [notice, notice]


def test_check_command_of_every_command_fetches_no_content_and_writes_nothing(
    tmp_path, fixture_root
):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    project = tmp_path / "project"
    init_project(project, store_dir=root)
    add_project_task(
        project,
        name="raba",
        command="series select",
        options={"dataset": DAILY, "stations": [RABA], "years": [2024]},
    )
    version = store.current_version(
        root, slot="archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
    ).version
    point = {"latitude": 52.23, "longitude": 21.01}
    options = {
        "datasets list": {"kind": "hydro"},
        "datasets files": {"dataset": DAILY, "years": 2024},
        "datasets download": {
            "dataset": DAILY,
            "years": 2024,
            "output": tmp_path / "out",
        },
        "datasets providers": {},
        "stations find": {"source": "store", "root": root},
        "current hydro": {},
        "current meteo": {"station": RABA},
        "current synop": {"station": "12375"},
        "current warnings": {},
        "current hydro-states": {"main_only": True},
        "pmaxtp fetch": point,
        "pmaxtp url": point,
        "pmaxtp check": {"root": root, **point},
        "pmaxtp sync": {"root": root, **point},
        "pmaxtp read": {"root": root, "ind_x": 751, "ind_y": 317},
        "store init": {"root": tmp_path / "new"},
        "store info": {"root": root},
        "store scan": {"root": root, "limit": 1},
        "store check": {
            "root": root,
            "datasets": DAILY,
            "years": 2024,
            "plan": tmp_path / "plan.json",
        },
        "store sync": {"root": root, "datasets": DAILY, "years": 2024},
        "store catalog": {"root": root},
        "store export": {"version": version, "path": tmp_path / "archive.csv"},
        "series build": {"root": root, "dataset": DAILY},
        "series select": {"root": root, "dataset": DAILY, "stations": RABA},
        "series read": {"root": root, "dataset": DAILY, "station": RABA},
        "series summary": {"root": root, "dataset": DAILY},
        "series export": {
            "root": root,
            "dataset": DAILY,
            "station": RABA,
            "path": tmp_path / "series.csv",
        },
        "project init": {"project_dir": tmp_path / "other", "store_dir": root},
        "project add": {
            "project_dir": project,
            "name": "info",
            "command": "store info",
            "options": {},
        },
        "project remove": {"project_dir": project, "name": "raba"},
        "project set-store": {"project_dir": project, "store_dir": root},
        "project download": {"project_dir": project},
        "project check": {"project_dir": project, "plan": tmp_path / "plan.json"},
        "project status": {"project_dir": project},
        "project verify": {"project_dir": project},
        "commands list": {"lang": "en"},
        "commands schema": {"command": "store sync"},
        "commands guide": {"format": "llms", "path": tmp_path / "llms.txt"},
    }
    assert list(options) == SPEC_COMMANDS
    untouched = stamps(tmp_path)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        imgw = FakeImgw(router)
        imgw.publish(H2024, V3, NEW)
        imgw.publish_catalog_sources()
        for command, values in options.items():
            result = check_command(command, options=values)
            assert (result.command, result.check, result.status) == (
                command,
                True,
                "ok",
            ), result.result
            assert isinstance(result.result, StorePlan)
        assert imgw.downloads() == []
    assert stamps(tmp_path) == untouched


def test_check_of_datasets_download_plans_each_server_path(tmp_path):
    output = tmp_path / "out"
    files = archive_files(SEMIANNUAL, years=2024, params="H,Q")
    existing = output.joinpath(*files[0].server_path.split("/"))
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"PK")
    plan = check_command(
        "datasets download",
        options={
            "dataset": SEMIANNUAL,
            "years": 2024,
            "params": "H,Q",
            "output": output,
        },
    ).result
    assert plan.root == output
    assert [
        (action.status, action.detail.split(" → ")[0]) for action in plan.actions
    ] == [
        ("unverifiable", files[0].url),
        ("missing", files[1].url),
    ]


def test_check_of_store_sync_with_a_plan_returns_it_for_the_same_store(
    tmp_path, fixture_root
):
    saved = StorePlan("imgw-plan/1", fixture_root, FROZEN_AT, (), {}).to_json(
        tmp_path / "plan.json"
    )
    plan = check_command(
        "store sync", options={"root": fixture_root, "plan": saved}
    ).result
    assert plan == StorePlan.from_json(saved)
    with pytest.raises(IMGWValidationError) as error:
        check_command("store sync", options={"root": tmp_path, "plan": saved})
    assert error.value.details["option"] == "plan"


def test_project_check_writes_its_plan_only_outside_the_store(tmp_path, fixture_root):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    project = tmp_path / "project"
    init_project(project, store_dir=root)
    target = tmp_path / "plan.json"
    result = run_command(
        "project check", options={"project_dir": project, "plan": target}
    )
    assert result.status == "ok"
    assert StorePlan.from_json(target) == result.result
    inside = root / "plan.json"
    with pytest.raises(IMGWValidationError) as error:
        run_command("project check", options={"project_dir": project, "plan": inside})
    assert error.value.details["option"] == "plan" and not inside.exists()


def test_download_project_pins_the_same_files_as_before_the_catalog(
    tmp_path, imgw, frozen
):
    root = build_fixture_store(tmp_path / "store").root
    project = tmp_path / "project"
    imgw.publish(H2024, V3, NEW)
    imgw.publish_catalog_sources()
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    init_project(project, store_dir="../store")
    tasks = {
        "raba": (
            "series select",
            {"dataset": DAILY, "stations": [RABA], "years": [2024]},
        ),
        "sync": ("store sync", {"datasets": [DAILY], "years": [2024]}),
        "build": ("series build", {"dataset": DAILY}),
        "cell": ("pmaxtp sync", {"latitude": 52.23, "longitude": 21.01}),
        "catalog": ("store catalog", {}),
    }
    for name, (command, options) in tasks.items():
        add_project_task(project, name=name, command=command, options=options)
    report = download_project(project)
    assert report.tasks == dict.fromkeys(tasks, "current")
    pinned = {
        task.name: [(pin.role, pin.path.as_posix()) for pin in task.files]
        for task in project_api.open_project(project).tasks
    }
    assert pinned == PINS_BEFORE
    assert all(
        sha256(root / pin.path) == pin.sha256
        for task in project_api.open_project(project).tasks
        for pin in task.files
    )


def test_failed_download_of_a_datasets_download_task_fails_the_task(tmp_path, imgw):
    root = tmp_path / "store"
    store.init_store(root)
    project = tmp_path / "project"
    init_project(project, store_dir=root)
    add_project_task(
        project,
        name="pobranie",
        command="datasets download",
        options={"dataset": SEMIANNUAL, "years": 2024, "params": "H,Q"},
    )
    stored, missing = archive_files(SEMIANNUAL, years=2024, params="H,Q")
    imgw.publish(stored, V1, archive_bytes(H2023))
    imgw.router.get(missing.url).mock(return_value=httpx.Response(404))
    report = download_project(project)
    assert report.tasks == {"pobranie": "failed"}
    assert [result.status for result in report.files] == ["failed"]
    downloaded = project / "data" / "downloaded"
    assert downloaded.joinpath(*stored.server_path.split("/")).is_file()
