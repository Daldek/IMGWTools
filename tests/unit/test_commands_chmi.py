"""Command catalog for ČHMÚ (spec 2026-10-18 §9.2–§9.3): options, rules, views, parity.

ČHMÚ answers come from the recordings of ``chmi_recordings.json`` and
``chmi_catalog_recordings.json`` only; respx refuses every other request.
"""

import importlib
import json
from datetime import UTC, datetime

import pytest
import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from imgwtools import (
    ERROR_CODES,
    STATION_CODE_PATTERN,
    IMGWValidationError,
    check_command,
    command_schema,
    data_commands,
    format_command,
    providers,
    run_command,
    validate_command,
)
from imgwtools._jsonable import jsonable
from imgwtools.api.main import app as rest_app
from imgwtools.cli.main import app as cli_app
from imgwtools.config import settings
from imgwtools.store import init_store
from tests.contract.support import canonical, cli_words, rest_request, violations
from tests.unit.test_commands import parse
from tests.unit.test_store_catalog_chmi import SOURCES, build
from tests.unit.test_store_catalog_chmi import serve as serve_catalog
from tests.unit.test_store_sync_chmi import BASE, FIRST
from tests.unit.test_store_sync_chmi import serve as serve_files

HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
S1, S2 = "0-203-1-900001", "0-203-1-900002"
FULL = "0-203-0-90001"
ROOT = "/data/imgw"
HYDRO_NOW = BASE + "hydrology/now/metadata/meta1.json"
METEO_LISTING = BASE + "meteorology/climate/now/metadata/"
FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_store_root(monkeypatch):
    """The developer's IMGW_ROOT must not reach the CLI under test."""
    monkeypatch.delenv("IMGW_ROOT", raising=False)


@pytest.fixture
def server(monkeypatch):
    """REST server without a store root, writes disabled, default page size."""
    for name, value in (
        ("root", None),
        ("store_writes_enabled", False),
        ("store_write_token", None),
        ("user_locations_dir", None),
        ("api_max_limit", 1000),
    ):
        monkeypatch.setattr(settings, name, value)
    return settings


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in (
        "imgwtools.commands",
        "imgwtools.store.sync",
        "imgwtools.store.catalog",
    ):
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)


@pytest.fixture
def chmi():
    """Recorded ČHMÚ: current metadata, station lists and the daily-file listings."""
    with respx.mock(assert_all_called=False) as router:
        serve_catalog(router, *SOURCES)
        serve_files(
            router, "hydro_listing", "precipitation_listing", "temperature_listing"
        )
        yield router


# --------------------------------------------------------------------------
# Catalog and registry
# --------------------------------------------------------------------------


def test_catalog_has_38_commands_and_datasets_providers_lists_both_providers():
    assert len(data_commands()) == 38

    listed = run_command("datasets providers", options={})
    planned = check_command("datasets providers", options={})

    assert listed.status == "ok"
    assert [provider.id for provider in listed.result.items] == ["IMGW-PIB", "CHMI"]
    assert (listed.result.items, listed.result.total) == (providers(), 2)
    assert [action.status for action in planned.result.actions] == ["current"]
    chmi = run_command("datasets list", options={"provider": "CHMI"}).result
    assert [descriptor.key for descriptor in chmi.items] == [
        HYDRO,
        METEO,
        "cz.chmi.hydro_stations",
        "cz.chmi.meteo_stations",
    ]
    assert run_command("datasets list", options={}).result.total == 17


def test_command_schema_publishes_provider_stations_and_their_rules():
    for name in ("datasets list", "stations find", "store scan"):
        provider = command_schema(name)["properties"]["provider"]
        assert provider["enum"] == ["IMGW-PIB", "CHMI"]
        assert "default" not in provider
    catalog = command_schema("store catalog")["properties"]["provider"]
    assert (catalog["enum"], catalog["default"]) == (["IMGW-PIB", "CHMI"], "IMGW-PIB")
    for name in ("datasets files", "datasets download", "store check", "store sync"):
        schema = command_schema(name)
        assert schema["properties"]["stations"]["items"]["pattern"] == (
            STATION_CODE_PATTERN
        )
        assert schema["x-imgw"]["cli"]["flags"]["stations"] == ["--stations", "-s"]
        # Years depend on the dataset, so the schema leaves them to the rules.
        assert "years" not in schema.get("required", [])
        rules = schema["x-imgw"]["rules"]
        assert any("stations" in rule and "cz.chmi" in rule for rule in rules)
        assert any("years" in rule and METEO in rule for rule in rules)
    archive = command_schema("datasets files")["properties"]["dataset"]["enum"]
    assert len(archive) == 12 and {HYDRO, METEO} <= set(archive)
    meta = command_schema("datasets providers")["x-imgw"]
    assert (meta["function"], meta["result"], meta["result_type"]) == (
        "providers",
        "list",
        "ProviderDescriptor",
    )
    assert meta["rest"]["path"] == "/api/v1/datasets/providers"


def test_chmi_view_of_the_catalog_drops_imgw_only_commands_and_narrows_choices():
    view = data_commands(provider="CHMI")

    groups = {command.name.split()[0] for command in view}
    assert not groups & {"current", "pmaxtp"}
    assert len(view) == 28  # 38 without five current and five pmaxtp commands
    for command in view:
        for option in command.options:
            if option.name in ("dataset", "datasets"):
                assert option.choices
                assert all(key.startswith("cz.chmi.") for key in option.choices)
            elif option.name == "provider":
                assert (option.choices, option.required, option.default) == (
                    ("CHMI",),
                    True,
                    None,
                )
    assert data_commands(provider="cz.chmi") == view
    imgw = data_commands(provider="IMGW-PIB")
    assert [command.name for command in imgw] == [c.name for c in data_commands()]
    assert all(
        key.startswith("pl.imgw.")
        for command in imgw
        for option in command.options
        if option.name in ("dataset", "datasets")
        for key in option.choices
    )
    # The whole catalog still validates: provider stays optional there.
    assert validate_command("stations find", options={}) == {}
    with pytest.raises(IMGWValidationError) as error:
        data_commands(provider="SHMU")
    assert error.value.details["option"] == "provider"


# --------------------------------------------------------------------------
# validate_command and format_command
# --------------------------------------------------------------------------


REJECTED = [
    ("datasets files", {"dataset": HYDRO, "years": 2024}, "stations"),
    (
        "datasets files",
        {"dataset": "pl.imgw.hydro_daily", "years": 2024, "stations": [S1]},
        "stations",
    ),
    ("datasets files", {"dataset": HYDRO, "stations": [S1]}, "years"),
    ("datasets files", {"dataset": METEO, "stations": [FULL], "years": 2024}, "years"),
    (
        "datasets files",
        {"dataset": HYDRO, "stations": ["149190310"], "years": 2024},
        "stations",
    ),
    ("datasets files", {"dataset": HYDRO, "stations": [S1], "years": 1886}, "years"),
    (
        "datasets download",
        {"dataset": HYDRO, "stations": [S1], "years": 2024, "months": 1},
        "months",
    ),
    (
        "datasets download",
        {"dataset": METEO, "stations": [FULL], "params": "H"},
        "params",
    ),
    ("datasets list", {"provider": "SHMU"}, "provider"),
    ("stations find", {"provider": "chmi"}, "provider"),
    ("store scan", {"root": ROOT, "provider": "CZ"}, "provider"),
    ("store catalog", {"root": ROOT, "provider": "SHMU"}, "provider"),
    (
        "store check",
        {
            "root": ROOT,
            "datasets": [HYDRO, "pl.imgw.hydro_daily"],
            "stations": [S1],
            "years": 2024,
        },
        "stations",
    ),
    ("store check", {"root": ROOT, "datasets": [HYDRO]}, "stations"),
    (
        "store check",
        {
            "root": ROOT,
            "datasets": ["pl.imgw.hydro_daily"],
            "years": 2024,
            "stations": [S1],
        },
        "stations",
    ),
    (
        "store check",
        {"root": ROOT, "datasets": [METEO], "stations": [FULL], "years": 2024},
        "years",
    ),
    (
        "store check",
        {"root": ROOT, "datasets": [HYDRO], "stations": [S1], "months": 1},
        "months",
    ),
    (
        "store check",
        {"root": ROOT, "datasets": [METEO], "stations": ["0-203-0-ab"]},
        "stations",
    ),
    (
        "store sync",
        {"root": ROOT, "plan": "/tmp/plan.json", "stations": [S1]},
        "stations",
    ),
    ("store sync", {"root": ROOT, "datasets": [HYDRO]}, "stations"),
]


@pytest.mark.parametrize(("command", "options", "option"), REJECTED)
def test_validate_command_applies_the_rules_of_the_dataset_provider(
    command, options, option
):
    with pytest.raises(IMGWValidationError) as error:
        validate_command(command, options=options)

    assert error.value.code == "validation_error"
    assert error.value.details["option"] == option


VALID = [
    ("datasets list", {"provider": "CHMI", "kind": "hydro"}),
    (
        "datasets files",
        {"dataset": HYDRO, "stations": [S2, S1, S2], "years": "2004-2006"},
    ),
    ("datasets files", {"dataset": "chmi_meteo_daily", "stations": FULL}),
    (
        "datasets download",
        {"dataset": METEO, "stations": [FULL], "output": "/tmp/pobrane dane"},
    ),
    ("datasets providers", {"limit": 1}),
    ("stations find", {"provider": "cz.chmi", "kind": "hydro", "query": "spindleruv"}),
    ("stations find", {"provider": "CHMI", "source": "store", "root": ROOT}),
    ("store scan", {"root": ROOT, "provider": "CHMI", "kind": "archive"}),
    ("store check", {"root": ROOT, "datasets": HYDRO, "stations": [S1, S2]}),
    (
        "store check",
        {
            "root": ROOT,
            "datasets": [HYDRO],
            "stations": S1,
            "years": [2023, 2024],
            "plan": "/tmp/plan.json",
        },
    ),
    ("store check", {"root": ROOT, "datasets": METEO, "stations": FULL}),
    (
        "store sync",
        {
            "root": ROOT,
            "datasets": [HYDRO],
            "stations": [S1],
            "years": "2023-2024",
            "series": False,
        },
    ),
    ("store catalog", {"root": ROOT, "provider": "CHMI"}),
]


@pytest.mark.parametrize(("command", "options"), VALID)
def test_chmi_examples_round_trip_through_format_command(command, options):
    normalized = validate_command(command, options=options)

    text = format_command(command, options=options)
    name, parsed = parse(text)

    assert name == command
    assert validate_command(command, options=parsed) == normalized
    assert format_command(command, options=parsed) == text
    assert violations(jsonable(normalized), command_schema(command)) == []


def test_validate_command_normalizes_chmi_selectors():
    files = validate_command(
        "datasets files",
        options={
            "dataset": "chmi_hydro_daily",
            "stations": f"{S2},{S1},{S2}",
            "years": "2024",
        },
    )
    assert files == {"dataset": HYDRO, "years": (2024,), "stations": (S2, S1)}
    check = validate_command(
        "store check", options={"root": ROOT, "datasets": HYDRO, "stations": S1}
    )
    assert (check["datasets"], check["stations"], "years" in check) == (
        (HYDRO,),
        (S1,),
        False,
    )
    assert validate_command("datasets list", options={"provider": "cz.chmi"}) == {
        "provider": "CHMI"
    }


# --------------------------------------------------------------------------
# Dispatch: stations reach the functions, statuses, checks
# --------------------------------------------------------------------------


def test_store_check_and_sync_pass_stations_through_the_catalog(tmp_path):
    root = init_store(tmp_path / "store").root
    options = {"root": root, "datasets": [HYDRO], "stations": [S1], "series": False}

    with respx.mock(assert_all_called=False) as router:
        serve_files(router, "hydro_listing", *FIRST)
        planned = check_command("store sync", options=options)
        synced = run_command("store sync", options=options)

    assert planned.status == synced.status == "ok"
    assert [(item.station_code, item.status) for item in planned.result.items] == [
        (S1, "missing"),
        (S1, "missing"),
    ]
    assert [item.status for item in synced.result.items] == ["new", "new"]


def test_unpublished_files_count_as_successful_items_of_a_download(tmp_path):
    options = {
        "dataset": HYDRO,
        "stations": [S2],
        "years": "2004-2005",
        "output": tmp_path / "pobrane",
    }
    with respx.mock(assert_all_called=False) as router:
        serve_files(router, "h900002_2005_get")
        failing = f"hydrology/historical/data/daily/H_{S2}_DQ_2004.json"
        router.get(BASE + failing).respond(500)
        planned = check_command("datasets download", options=options)
        result = run_command("datasets download", options=options)
        printed = CliRunner().invoke(cli_app, cli_words("datasets download", options))

    assert [action.status for action in planned.result.actions] == ["missing"] * 2
    assert [item.status for item in result.result.items] == ["failed", "not_published"]
    # A failure beside an unpublished candidate is partial, not failed (§13.6).
    assert result.status == "partial"
    assert printed.exit_code == 10, printed.output
    assert canonical(json.loads(printed.stdout)) == canonical(result.to_json())


def test_check_of_a_live_chmi_search_names_its_sources_without_requests():
    with respx.mock(assert_all_called=False) as router:
        plan = check_command("stations find", options={"provider": "CHMI"}).result

    assert not router.calls
    assert [action.status for action in plan.actions] == ["unverifiable"] * 3
    details = " ".join(action.detail for action in plan.actions)
    assert HYDRO_NOW in details and METEO_LISTING in details


def test_source_unavailable_title_is_neutral_and_the_detail_names_chmi(server):
    assert ERROR_CODES["source_unavailable"].title == "Data source unavailable"
    with respx.mock(assert_all_called=False) as router:
        serve_catalog(router, "hydro_now_outage")
        response = TestClient(rest_app).get(
            "/api/v1/stations/find", params={"provider": "CHMI", "kind": "hydro"}
        )

    problem = response.json()
    assert response.status_code == 502
    assert (problem["code"], problem["title"]) == (
        "source_unavailable",
        "Data source unavailable",
    )
    assert "ČHMÚ" in problem["detail"]
    assert problem["details"]["url"] == HYDRO_NOW


# --------------------------------------------------------------------------
# Python = imgw = REST for the new and changed commands
# --------------------------------------------------------------------------


PARITY = [
    ("datasets providers", {"limit": 5}, False),
    ("datasets list", {"provider": "CHMI", "limit": 10}, False),
    (
        "datasets files",
        {"dataset": HYDRO, "stations": [S1, S2], "years": "2023-2024", "limit": 10},
        False,
    ),
    ("stations find", {"provider": "CHMI", "query": "spindleruv", "limit": 10}, False),
    ("stations find", {"provider": "CHMI", "source": "store", "limit": 10}, True),
    ("store scan", {"provider": "CHMI", "kind": "catalog", "limit": 10}, True),
    ("store check", {"datasets": [HYDRO], "stations": [S1, S2]}, True),
    ("store check", {"datasets": [METEO], "stations": [FULL]}, True),
]


@pytest.mark.parametrize(("command", "options", "stored"), PARITY)
def test_chmi_commands_answer_alike_in_python_cli_and_rest(
    tmp_path, monkeypatch, server, frozen, chmi, command, options, stored
):
    root = None
    if stored:
        store = init_store(tmp_path / "store")
        build(store)
        root = store.root
        monkeypatch.setattr(server, "root", root)
    local = options if root is None else {"root": root, **options}

    start = len(chmi.calls)
    python = run_command(command, options=local)
    middle = len(chmi.calls)
    printed = CliRunner().invoke(cli_app, cli_words(command, local))
    end = len(chmi.calls)
    answered = TestClient(rest_app).request(**rest_request(command, options))

    assert python.status == "ok"
    assert printed.exit_code == 0, printed.output
    assert canonical(json.loads(printed.stdout)) == canonical(python.to_json(root=root))
    assert answered.status_code == 200, answered.text
    assert canonical(answered.json()) == canonical(
        python.to_json(root=root, server=True)
    )
    requests = [
        [(c.request.method, str(c.request.url)) for c in chmi.calls[a:b]]
        for a, b in ((start, middle), (middle, end), (end, len(chmi.calls)))
    ]
    assert requests[0] == requests[1] == requests[2]


def test_store_catalog_of_chmi_is_planned_alike_in_python_cli_and_rest(
    tmp_path, monkeypatch, server, frozen, chmi
):
    root = init_store(tmp_path / "store").root
    monkeypatch.setattr(server, "root", root)
    options = {"provider": "CHMI"}

    python = check_command("store catalog", options={"root": root, **options})
    printed = CliRunner().invoke(
        cli_app, [*cli_words("store catalog", {"root": root, **options}), "--check"]
    )
    request = rest_request("store catalog", options)
    request["url"] += "?check=true"
    answered = TestClient(rest_app).request(**request)

    assert python.result.items
    assert {item.archive.dataset for item in python.result.items} == {
        "cz.chmi.hydro_stations",
        "cz.chmi.meteo_stations",
    }
    assert canonical(json.loads(printed.stdout)) == canonical(python.to_json(root=root))
    assert answered.status_code == 200, answered.text
    assert canonical(answered.json()) == canonical(
        python.to_json(root=root, server=True)
    )
    assert not list((root / "stations").glob("**/*.geojson"))
