"""Command catalog §10: offline validation, stable formatting, write-free checks, one dispatcher."""

import importlib
import json
import shlex
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from imgwtools import fetch, store
from imgwtools.commands import (
    check_command,
    data_commands,
    format_command,
    run_command,
    validate_command,
)
from imgwtools.exceptions import IMGWProjectError, IMGWValidationError
from imgwtools.fetch import DownloadResult
from imgwtools.project import (
    add_project_task,
    get_project_status,
    open_project,
    verify_project,
)
from imgwtools.store.types import Notice, SeriesSelection, StorePlan
from imgwtools.testing import build_fixture_store

DAILY = "pl.imgw.hydro_daily"
STATION = "149190310"
SPEC_COMMANDS = {
    "store init",
    "store info",
    "store scan",
    "store check",
    "store sync",
    "store catalog",
    "series build",
    "series export",
    "series select",
    "pmaxtp check",
    "pmaxtp sync",
    "pmaxtp read",
    "project init",
    "project add",
    "project remove",
    "project set-store",
    "project download",
    "project check",
    "project status",
    "project verify",
    "fetch hydro",
    "fetch meteo",
}
SAMPLES = [
    ("store init", {"root": "/data/imgw store"}),
    ("store info", {"root": "/data/imgw"}),
    ("store scan", {"root": "/data/imgw", "kind": "problem"}),
    (
        "store check",
        {
            "root": "/data/imgw",
            "dataset": f"{DAILY},pl.imgw.meteo_precip_daily",
            "years": "2023-2025",
            "months": [1, 2],
            "plan": "/tmp/plan 1.json",
        },
    ),
    ("store sync", {"root": "/data/imgw", "plan": "plan.json"}),
    (
        "store sync",
        {"root": "/data/imgw", "dataset": [DAILY], "years": [2024], "no_series": True},
    ),
    ("store catalog", {"root": "/data/imgw", "user_locations": "moje położenia.csv"}),
    ("series build", {"root": "/data/imgw", "dataset": DAILY}),
    (
        "series export",
        {
            "version": "series/versions/hydro_daily/v/series.json",
            "station": STATION,
            "path": "out dir/x.csv",
            "variables": ["H", "Q"],
            "year_type": "calendar",
            "format": "csv",
        },
    ),
    (
        "series select",
        {
            "root": "/data/imgw",
            "dataset": DAILY,
            "stations": [STATION, "150160180"],
            "variables": "H",
            "years": "2020-2022,2024",
            "year_type": "hydrological",
        },
    ),
    (
        "pmaxtp check",
        {"root": "/data/imgw", "method": "POT", "lat": "52.23", "lon": 21.01},
    ),
    (
        "pmaxtp sync",
        {
            "root": "/data/imgw",
            "method": "AMP",
            "lat": 52.23,
            "lon": 21.01,
            "ind_x": 751,
            "ind_y": "317",
        },
    ),
    (
        "pmaxtp read",
        {
            "root": "/data/imgw",
            "method": "POT",
            "ind_x": 1,
            "ind_y": 2,
            "version": "pmaxtp/v/cell.json",
        },
    ),
    ("project init", {"project_dir": "proj", "store_dir": "../store"}),
    (
        "project add",
        {
            "project_dir": "proj",
            "name": "wisla-1",
            "command": "series select",
            "geometry": "obszar.geojson",
            "options": '{"dataset": "pl.imgw.hydro_daily", "stations": "149190310", "years": "2020-2021"}',
        },
    ),
    ("project remove", {"project_dir": "proj", "name": "wisla-1"}),
    ("project set-store", {"project_dir": "proj", "store_dir": "/mnt/imgw"}),
    (
        "project download",
        {
            "project_dir": "proj",
            "tasks": "a,b",
            "plan": "plan.json",
            "update": "upgrade",
        },
    ),
    ("project check", {"project_dir": "proj", "tasks": ["a"], "plan": "plan.json"}),
    ("project status", {"project_dir": "proj"}),
    ("project verify", {"project_dir": "proj", "tasks": "a"}),
    (
        "fetch hydro",
        {
            "interval": "polroczne_i_roczne",
            "year": "2020-2021",
            "param": "Q",
            "output": "out",
        },
    ),
    (
        "fetch meteo",
        {
            "interval": "dobowe",
            "subtype": "opad",
            "year": 2001,
            "month": 3,
            "output": "out",
        },
    ),
]


def parse(text):
    """Map a formatted command line back to catalog option names, as a CLI adapter would."""
    words = shlex.split(text)
    assert words[0] == "imgw"
    (command,) = [c for c in data_commands() if words[1:3] == c.name.split()]
    flags = {option.flag: option for option in command.options}
    options, rest = {}, words[3:]
    while rest:
        option = flags[rest.pop(0)]
        options[option.name] = True if option.type == "bool" else rest.pop(0)
    return command.name, options


def tree(root):
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("commands") / "store").root


@pytest.fixture
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("komenda nie może używać sieci")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


def test_catalog_lists_every_spec_command_with_polish_help_and_kebab_flags():
    commands = data_commands()
    assert {command.name for command in commands} == SPEC_COMMANDS
    assert {name for name, _ in SAMPLES} == SPEC_COMMANDS
    for command in commands:
        assert command.description.strip()
        names = [option.name for option in command.options]
        assert len(names) == len(set(names))
        for option in command.options:
            assert option.flag == "--" + option.name.replace("_", "-")
            assert option.help.strip()
            assert bool(option.choices) == (
                option.type == "choice" or option.name == "dataset"
            )
    flags = {
        command.name: {option.flag for option in command.options}
        for command in commands
    }
    assert {"--root", "--dataset", "--years", "--plan"} <= flags["store check"]
    assert {"--root", "--dataset", "--stations"} <= flags["series select"]
    assert {"--root", "--method", "--lat", "--lon"} <= flags["pmaxtp sync"]


@pytest.mark.parametrize(("command", "options"), SAMPLES)
def test_format_command_reparses_to_identical_options(offline, command, options):
    text = format_command(command, options=options)
    name, parsed = parse(text)
    assert name == command
    assert validate_command(command, options=parsed) == validate_command(
        command, options=options
    )
    assert format_command(command, options=parsed) == text


def test_format_command_quotes_and_adds_no_hidden_options():
    assert (
        format_command("store info", options={"root": "/a b/s"})
        == "imgw store info --root '/a b/s'"
    )
    assert format_command(
        "store sync", options={"root": "/s", "plan": "p.json", "no_series": False}
    ) == ("imgw store sync --root /s --plan p.json")


def test_validate_command_normalizes_values():
    assert validate_command(
        "store check",
        options={
            "root": "s",
            "dataset": [DAILY, DAILY],
            "years": "2025,2023-2024",
            "months": ["2", 1],
        },
    ) == {
        "root": Path("s"),
        "dataset": (DAILY,),
        "years": (2023, 2024, 2025),
        "months": (1, 2),
    }
    assert validate_command(
        "pmaxtp read", options={"root": "s", "method": "AMP", "ind_x": "7", "ind_y": 8}
    ) == {
        "root": Path("s"),
        "method": "AMP",
        "ind_x": 7,
        "ind_y": 8,
    }
    added = validate_command(
        "project add",
        options={
            "project_dir": "p",
            "name": "t",
            "command": "series select",
            "options": {"dataset": DAILY, "stations": STATION, "years": "2020-2021"},
        },
    )
    assert added["options"] == {
        "dataset": DAILY,
        "stations": (STATION,),
        "years": (2020, 2021),
    }
    by_area = validate_command(
        "project add",
        options={
            "project_dir": "p",
            "name": "t",
            "command": "series select",
            "geometry": "obszar.geojson",
            "options": {"dataset": DAILY, "years": 2024},
        },
    )
    assert by_area["options"] == {"dataset": DAILY, "years": (2024,)}


@pytest.mark.parametrize(
    ("command", "options"),
    [
        ("store delete", {"root": "/s"}),
        ("store info", {"root": "/s", "dataset": DAILY}),
        ("store info", {}),
        ("store scan", {"root": "/s", "kind": "everything"}),
        ("store check", {"root": "/s", "dataset": "pl.imgw.pmaxtp", "years": 2024}),
        ("store check", {"root": "/s", "dataset": DAILY, "years": 1900}),
        (
            "store check",
            {"root": "/s", "dataset": DAILY, "years": 2024, "months": "13"},
        ),
        (
            "store check",
            {"root": "/s", "dataset": DAILY, "years": 2024, "plan": "/s/plan.json"},
        ),
        ("store sync", {"root": "/s", "plan": "p.json", "years": 2024}),
        ("store sync", {"root": "/s", "dataset": DAILY}),
        ("store sync", {"root": "/s", "plan": "p.json", "no_series": "yes"}),
        ("series select", {"root": "/s", "dataset": DAILY, "stations": "12345"}),
        (
            "series select",
            {"root": "/s", "dataset": DAILY, "stations": STATION, "variables": "Tmax"},
        ),
        (
            "series select",
            {
                "root": "/s",
                "dataset": "pl.imgw.hydro_semiannual",
                "stations": STATION,
                "year_type": "calendar",
            },
        ),
        (
            "series export",
            {
                "version": "v",
                "station": STATION,
                "path": "x.csv",
                "variables": "H",
                "format": "xlsx",
            },
        ),
        ("pmaxtp sync", {"root": "/s", "method": "POT", "lat": 40.0, "lon": 21.0}),
        ("pmaxtp sync", {"root": "/s", "method": "POT", "lat": "abc", "lon": 21.0}),
        (
            "pmaxtp sync",
            {"root": "/s", "method": "POT", "lat": 52.2, "lon": 21.0, "ind_x": 1},
        ),
        ("pmaxtp read", {"root": "/s", "method": "XYZ", "ind_x": 1, "ind_y": 2}),
        ("pmaxtp read", {"root": "/s", "method": "POT", "ind_x": -1, "ind_y": 2}),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "Zły",
                "command": "series select",
                "options": "{}",
            },
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "project init",
                "options": "{}",
            },
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "series select",
                "options": "[1]",
            },
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "series select",
                "options": {"root": "/s", "dataset": DAILY, "stations": STATION},
            },
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "series select",
                "options": {"dataset": DAILY, "stations": STATION, "colour": "red"},
            },
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "series select",
                "options": {"dataset": DAILY, "stations": STATION},
            },
        ),
        (
            "project add",
            {
                "project_dir": "p",
                "name": "t",
                "command": "store info",
                "options": "{}",
                "geometry": "obszar.geojson",
            },
        ),
        ("project download", {"project_dir": "p", "update": "latest"}),
        ("fetch hydro", {"year": "2024", "interval": "dobowe", "param": "Q"}),
        ("fetch hydro", {"year": "2024-2020"}),
        ("fetch meteo", {"year": 2023, "interval": "terminowe", "subtype": "opad"}),
        ("fetch meteo", {"year": 2023, "interval": "dobowe", "subtype": "synop"}),
    ],
)
def test_validate_command_rejects_unknown_keys_and_choices_offline(
    offline, command, options
):
    with pytest.raises(IMGWValidationError):
        validate_command(command, options=options)


def test_check_command_never_writes_or_downloads(offline, fixture_root, tmp_path):
    selection = run_command(
        "series select",
        options={"root": fixture_root, "dataset": DAILY, "stations": STATION},
    )
    plan_file = StorePlan(
        "imgw-plan/1", fixture_root, datetime.now(UTC), (), {}
    ).to_json(tmp_path / "plan.json")
    project = tmp_path / "project"
    cases = [
        ("store init", {"root": fixture_root}, "current"),
        ("store init", {"root": tmp_path / "new"}, "missing"),
        ("store info", {"root": fixture_root}, "current"),
        ("store scan", {"root": fixture_root}, "current"),
        (
            "series build",
            {"root": fixture_root, "dataset": "pl.imgw.meteo_precip_daily"},
            "newer",
        ),
        (
            "series select",
            {"root": fixture_root, "dataset": DAILY, "stations": STATION},
            "current",
        ),
        (
            "series select",
            {
                "root": fixture_root,
                "dataset": "pl.imgw.hydro_monthly",
                "stations": STATION,
            },
            "missing",
        ),
        (
            "series export",
            {
                "version": selection.version,
                "station": STATION,
                "path": tmp_path / "x.csv",
                "variables": "H,Q",
            },
            "missing",
        ),
        (
            "series export",
            {
                "version": selection.version,
                "station": "999999999",
                "path": tmp_path / "x.csv",
                "variables": "H",
            },
            "check_failed",
        ),
        (
            "pmaxtp read",
            {"root": fixture_root, "method": "POT", "ind_x": 1, "ind_y": 2},
            "missing",
        ),
        (
            "project init",
            {"project_dir": project, "store_dir": fixture_root},
            "missing",
        ),
        (
            "project add",
            {
                "project_dir": project,
                "name": "t",
                "command": "series select",
                "options": {"dataset": DAILY, "stations": STATION, "years": 2024},
            },
            "check_failed",
        ),
        ("project status", {"project_dir": project}, "current"),
        (
            "fetch hydro",
            {"interval": "dobowe", "year": 2024, "output": tmp_path / "out"},
            "missing",
        ),
        ("fetch meteo", {"year": "1996-2001", "output": tmp_path / "out"}, "missing"),
    ]
    before, outside = tree(fixture_root), tree(tmp_path)
    for command, options, status in cases:
        plan = check_command(command, options=options)
        assert plan.schema == "imgw-plan/1" and plan.root.is_absolute()
        assert {action.status for action in plan.actions} == {status}, (
            command,
            plan.actions,
        )
    meteo = check_command(
        "fetch meteo", options={"year": "1996-2001", "output": tmp_path / "out"}
    )
    assert [Path(action.detail.split(" → ")[1]).name for action in meteo.actions] == [
        "1996_2000_m_s.zip",
        "2001_m_s.zip",
    ]
    assert (
        check_command(
            "store sync", options={"root": fixture_root, "plan": plan_file}
        ).root
        == fixture_root
    )
    assert tree(fixture_root) == before and tree(tmp_path) == outside


HOOKED = object()
RUN_CASES = [
    ("store init", {"root": "/s"}, "init_store", (Path("/s"),), {}),
    ("store info", {"root": "/s"}, "store_info", (Path("/s"),), {}),
    (
        "store scan",
        {"root": "/s", "kind": "series"},
        "iter_store",
        (Path("/s"),),
        {"kind": "series"},
    ),
    (
        "store check",
        {"root": "/s", "dataset": DAILY, "years": "2023-2024"},
        "check_store",
        (Path("/s"),),
        {"datasets": (DAILY,), "years": (2023, 2024), "months": None, "hooks": HOOKED},
    ),
    (
        "store sync",
        {"root": "/s", "plan": "p.json"},
        "sync_store",
        (Path("/s"),),
        {
            "datasets": None,
            "years": None,
            "months": None,
            "plan": Path("p.json"),
            "series": True,
            "hooks": HOOKED,
        },
    ),
    (
        "store sync",
        {"root": "/s", "dataset": DAILY, "years": 2024, "no_series": True},
        "sync_store",
        (Path("/s"),),
        {
            "datasets": (DAILY,),
            "years": (2024,),
            "months": None,
            "plan": None,
            "series": False,
            "hooks": HOOKED,
        },
    ),
    (
        "store catalog",
        {"root": "/s"},
        "build_catalog",
        (Path("/s"),),
        {"user_locations": None, "hooks": HOOKED},
    ),
    (
        "series build",
        {"root": "/s", "dataset": DAILY},
        "build_series",
        (Path("/s"),),
        {"dataset": DAILY, "hooks": HOOKED},
    ),
    (
        "series export",
        {"version": "v", "station": STATION, "path": "x.csv", "variables": "H"},
        "export_series",
        (Path("v"),),
        {
            "station": STATION,
            "path": Path("x.csv"),
            "variables": ("H",),
            "year_type": None,
            "format": "csv",
            "hooks": HOOKED,
        },
    ),
    (
        "pmaxtp check",
        {"root": "/s", "method": "POT", "lat": 52.23, "lon": 21.01},
        "check_pmaxtp",
        (Path("/s"),),
        {
            "method": "POT",
            "latitude": 52.23,
            "longitude": 21.01,
            "ind_x": None,
            "ind_y": None,
            "hooks": HOOKED,
        },
    ),
    (
        "pmaxtp sync",
        {
            "root": "/s",
            "method": "AMP",
            "lat": "52.23",
            "lon": "21.01",
            "ind_x": 1,
            "ind_y": 2,
        },
        "sync_pmaxtp",
        (Path("/s"),),
        {
            "method": "AMP",
            "latitude": 52.23,
            "longitude": 21.01,
            "ind_x": 1,
            "ind_y": 2,
            "hooks": HOOKED,
        },
    ),
    (
        "pmaxtp read",
        {"root": "/s", "method": "POT", "ind_x": 1, "ind_y": 2},
        "read_pmaxtp",
        (Path("/s"),),
        {"method": "POT", "ind_x": 1, "ind_y": 2, "version": None},
    ),
    (
        "project init",
        {"project_dir": "p", "store_dir": "s"},
        "init_project",
        (Path("p"),),
        {"store_dir": Path("s")},
    ),
    (
        "project add",
        {
            "project_dir": "p",
            "name": "t",
            "command": "series select",
            "options": {"dataset": DAILY, "stations": STATION, "years": 2024},
        },
        "add_project_task",
        (Path("p"),),
        {
            "name": "t",
            "command": "series select",
            "options": {"dataset": DAILY, "stations": (STATION,), "years": (2024,)},
            "geometry": None,
        },
    ),
    (
        "project remove",
        {"project_dir": "p", "name": "t"},
        "remove_project_task",
        (Path("p"),),
        {"name": "t"},
    ),
    (
        "project set-store",
        {"project_dir": "p", "store_dir": "s"},
        "set_project_store",
        (Path("p"),),
        {"store_dir": Path("s")},
    ),
    (
        "project download",
        {"project_dir": "p", "tasks": "t"},
        "download_project",
        (Path("p"),),
        {"tasks": ("t",), "plan": None, "update": "pinned", "hooks": HOOKED},
    ),
    (
        "project check",
        {"project_dir": "p"},
        "check_project",
        (Path("p"),),
        {"tasks": None, "hooks": HOOKED},
    ),
    (
        "project status",
        {"project_dir": "p"},
        "get_project_status",
        (Path("p"),),
        {"tasks": None},
    ),
    (
        "project verify",
        {"project_dir": "p"},
        "verify_project",
        (Path("p"),),
        {"tasks": None, "hooks": HOOKED},
    ),
    (
        "fetch hydro",
        {"interval": "polroczne_i_roczne", "year": 2024, "param": "Q"},
        "download_hydro_data",
        ("polroczne_i_roczne", 2024, None, "Q"),
        {},
    ),
    (
        "fetch meteo",
        {"year": 2023},
        "download_meteo_data",
        ("miesieczne", "synop", 2023, None),
        {},
    ),
]
CHECK_CASES = [
    ("store check", {"root": "/s", "dataset": DAILY, "years": 2024}, "check_store"),
    ("store sync", {"root": "/s", "dataset": DAILY, "years": 2024}, "check_store"),
    ("store catalog", {"root": "/s"}, "check_catalog"),
    ("series build", {"root": "/s", "dataset": DAILY}, "check_series"),
    (
        "pmaxtp check",
        {"root": "/s", "method": "POT", "lat": 52.23, "lon": 21.01},
        "check_pmaxtp",
    ),
    (
        "pmaxtp sync",
        {"root": "/s", "method": "POT", "lat": 52.23, "lon": 21.01},
        "check_pmaxtp",
    ),
    ("project download", {"project_dir": "p"}, "check_project"),
    ("project check", {"project_dir": "p"}, "check_project"),
]


@pytest.fixture
def public_api(monkeypatch, tmp_path):
    """Replace every public target of the dispatcher with a recorder."""
    calls = []
    result = object()

    def recorder(module, name, value=result):
        def fake(*args, **kwargs):
            calls.append((name, args, kwargs))
            return value

        monkeypatch.setattr(module, name, fake, raising=False)

    for name in (
        "init_store",
        "store_info",
        "check_store",
        "sync_store",
        "build_catalog",
        "check_catalog",
        "build_series",
        "check_series",
        "check_pmaxtp",
        "sync_pmaxtp",
        "read_pmaxtp",
        "current_version",
        "read_series_index",
        "open_store",
        "write_archive",
        "read_series",
    ):
        recorder(store, name)
    recorder(store, "iter_store", iter(()))
    recorder(importlib.import_module("imgwtools.store.export"), "export_series")
    project = importlib.import_module("imgwtools.project")
    for name in (
        "init_project",
        "add_project_task",
        "remove_project_task",
        "set_project_store",
        "download_project",
        "check_project",
        "get_project_status",
        "verify_project",
        "open_project",
    ):
        recorder(project, name)
    download = DownloadResult(b"PK", "https://example.invalid", None, None, 2)
    for name in ("download_hydro_data", "download_meteo_data"):
        recorder(fetch, name, download)
    monkeypatch.chdir(tmp_path)
    return calls, result


@pytest.mark.parametrize(
    ("command", "options", "function", "args", "kwargs"), RUN_CASES
)
def test_run_command_calls_exactly_one_public_api_with_same_hooks(
    public_api, command, options, function, args, kwargs
):
    calls, result = public_api
    hooks = {
        "on_progress": lambda progress: None,
        "on_notice": lambda notice: None,
        "cancel": lambda: False,
    }
    returned = run_command(command, options=options, **hooks)
    expected = dict(kwargs)
    if expected.pop("hooks", None) is HOOKED:
        expected.update(hooks)
    assert calls == [(function, args, expected)]
    if not command.startswith(("fetch", "store scan")):
        assert returned is result


@pytest.mark.parametrize(("command", "options", "function"), CHECK_CASES)
def test_check_command_uses_check_function_of_the_operation(
    public_api, command, options, function
):
    calls, result = public_api
    assert check_command(command, options=options) is result
    assert [call[0] for call in calls] == [function]


def test_series_select_validates_selection_against_current_series(
    offline, fixture_root
):
    selection = run_command(
        "series select",
        options={
            "root": fixture_root,
            "dataset": DAILY,
            "stations": STATION,
            "variables": "Q",
        },
    )
    assert isinstance(selection, SeriesSelection)
    assert (
        selection.version
        == store.current_version(fixture_root, slot="series:hydro_daily").version
    )
    assert (selection.stations, selection.variables, selection.year_type) == (
        (STATION,),
        ("Q",),
        "hydrological",
    )
    assert selection.years == (2024,)
    for options in ({"stations": "999999999"}, {"stations": STATION, "years": 1990}):
        with pytest.raises(IMGWValidationError):
            run_command(
                "series select",
                options={"root": fixture_root, "dataset": DAILY, **options},
            )


def test_project_commands_run_on_a_real_manifest_like_the_python_api(
    offline, fixture_root, tmp_path
):
    project = tmp_path / "project"
    created = run_command(
        "project init", options={"project_dir": project, "store_dir": fixture_root}
    )
    assert created == open_project(project) and created.store_dir == fixture_root
    assert (
        check_command(
            "project init", options={"project_dir": project, "store_dir": fixture_root}
        )
        .actions[0]
        .status
        == "current"
    )
    added = run_command(
        "project add",
        options={
            "project_dir": project,
            "name": "raba",
            "command": "series select",
            "options": json.dumps(
                {"dataset": DAILY, "stations": STATION, "years": "2024"}
            ),
        },
    )
    assert added.tasks[0].options == {
        "dataset": DAILY,
        "stations": [STATION],
        "variables": ["H", "Q", "T"],
        "years": [2024],
        "year_type": "hydrological",
    }
    with pytest.raises(IMGWProjectError, match="już istnieje"):
        run_command(
            "project add",
            options={
                "project_dir": project,
                "name": "raba",
                "command": "store info",
                "options": "{}",
            },
        )
    add_project_task(project, name="info", command="store info", options={})
    removed = run_command(
        "project remove", options={"project_dir": project, "name": "info"}
    )
    assert [task.name for task in removed.tasks] == ["raba"]
    assert run_command(
        "project status", options={"project_dir": project}
    ) == get_project_status(project)
    assert run_command(
        "project verify", options={"project_dir": project, "tasks": "raba"}
    ) == verify_project(project, tasks=["raba"])
    assert (
        run_command(
            "project set-store",
            options={"project_dir": project, "store_dir": fixture_root},
        )
        == removed
    )


def test_series_export_reports_same_progress_and_notices_as_direct_call(
    offline, fixture_root, tmp_path
):
    from imgwtools.store.export import export_series

    version = store.current_version(fixture_root, slot="series:hydro_daily").version
    direct_events, command_events = [], []
    direct = export_series(
        version,
        station=STATION,
        path=tmp_path / "direct.csv",
        variables=["H", "Q"],
        on_progress=direct_events.append,
        on_notice=direct_events.append,
    )
    exported = run_command(
        "series export",
        options={
            "version": version,
            "station": STATION,
            "path": tmp_path / "command.csv",
            "variables": "H,Q",
        },
        on_progress=command_events.append,
        on_notice=command_events.append,
    )
    assert exported.read_bytes() == direct.read_bytes()

    def shape(events):
        return [
            (type(e).__name__, e)
            if isinstance(e, Notice)
            else (type(e).__name__, e.unit, e.status)
            for e in events
        ]

    assert shape(command_events) == shape(direct_events) and command_events


def test_fetch_hydro_mirrors_server_paths_and_reports_failures(monkeypatch, tmp_path):
    def download(interval, year, month, param):
        if param == "T":
            raise IMGWValidationError("brak archiwum")
        return DownloadResult(
            f"{param}{year}".encode(), "https://example.invalid", None, None, 5
        )

    monkeypatch.setattr(fetch, "download_hydro_data", download)
    events = []
    output = run_command(
        "fetch hydro",
        options={"year": 2024, "output": tmp_path / "out"},
        on_progress=events.append,
        on_notice=events.append,
    )
    base = output / "dane_hydrologiczne" / "polroczne_i_roczne" / "2024"
    assert {path.name: path.read_bytes() for path in base.iterdir()} == {
        "polr_H_2024.zip": b"H2024",
        "polr_Q_2024.zip": b"Q2024",
    }
    notices = [e for e in events if isinstance(e, Notice)]
    assert [e.code for e in notices] == ["download_failed", "license_terms"]
    assert "Instytut Meteorologii i Gospodarki Wodnej" in notices[-1].text
    assert [e.status for e in events if not isinstance(e, Notice)] == [
        "downloaded",
        "downloaded",
        "failed",
    ]

    cancelled = []
    run_command(
        "fetch hydro",
        options={"year": 2024, "output": tmp_path / "cancelled"},
        on_notice=cancelled.append,
        cancel=lambda: True,
    )
    assert not (tmp_path / "cancelled").exists()
    assert [notice.code for notice in cancelled] == ["cancelled"]
