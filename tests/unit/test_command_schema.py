"""command_schema (obserwator-commands/1, Nogat commands-1), list_commands and the JSON
Schema 2020-12 of the options the adapters are built from (spec §13.8)."""

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from obserwator import __version__
from obserwator._jsonable import jsonable
from obserwator.api.main import app as rest_app
from obserwator.cli.main import app as cli_app
from obserwator.commands import (
    command_schema,
    data_commands,
    list_commands,
    run_command,
    validate_command,
)
from obserwator.config import settings
from obserwator.datasets import datasets
from obserwator.exceptions import ERROR_CODES, ObserwatorValidationError
from obserwator.store import init_store
from tests.contract.support import (
    canonical,
    cli_words,
    input_schema,
    rest_request,
    violations,
)
from tests.unit.test_commands import DAILY, REJECTED, ROOT, SAMPLES, SPEC_COMMANDS
from tests.unit.test_store_reader import observe, store_archives, with_content

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ARCHIVE_KEYS = [
    d.key
    for d in datasets()
    if d.server_dir is not None and d.time_unit != "station_list"
]
SERIES_KEYS = [
    d.key
    for d in datasets()
    if d.in_store and d.time_unit in ("day", "month", "half_year")
]


def test_catalog_document_lists_every_command_with_groups_errors_and_exit_codes():
    document = command_schema()
    assert json.loads(json.dumps(document)) == document
    assert (
        document["schema"],
        document["tool"],
        document["version"],
        document["lang"],
    ) == ("obserwator-commands/1", "obserwator", __version__, "en")
    assert [entry["name"] for entry in document["commands"]] == SPEC_COMMANDS
    assert list(document["groups"]) == list(
        dict.fromkeys(name.split()[0] for name in SPEC_COMMANDS)
    )
    assert document["errors"] == [
        {
            "code": spec.code,
            "title": spec.title.localized("en"),
            "exit_code": spec.exit_code,
            "http_status": spec.http_status,
        }
        for spec in ERROR_CODES.values()
    ]
    assert document["exit_codes"] == {
        "ok": 0,
        "partial": 10,
        "failed": 11,
        "cancelled": 130,
    }
    for entry in document["commands"]:
        assert command_schema(entry["name"])["commands"] == [entry]


def test_unknown_command_is_a_validation_error_listing_the_commands():
    with pytest.raises(ObserwatorValidationError) as error:
        command_schema("store delete")
    assert error.value.details["option"] == "command"
    assert error.value.details["allowed"] == SPEC_COMMANDS


def test_option_types_rules_and_interfaces_map_to_the_input_schema():
    find = input_schema("stations find")
    assert (find["$schema"], find["type"], find["additionalProperties"]) == (
        DIALECT,
        "object",
        False,
    )
    properties = {
        name: {key: value for key, value in option.items() if key != "description"}
        for name, option in find["properties"].items()
    }
    assert properties == {
        "kind": {"enum": ["hydro", "meteo"]},
        "query": {"type": "string", "minLength": 1},
        "source": {"enum": ["live", "store"], "default": "live"},
        "root": {
            "type": "string",
            "x-obserwator-type": "path",
            "x-obserwator-path-role": "root",
        },
        "limit": {"type": "integer", "minimum": 1},
        "cursor": {"type": "string", "minLength": 1},
        "provider": {"enum": ["IMGW-PIB", "CHMI"]},
    }
    meta = {
        key: value
        for key, value in find["x-obserwator"].items()
        if key not in ("rules", "examples")
    }
    assert meta == {
        "command": "stations find",
        "operation_id": "obserwator_stations_find",
        "group": "stations",
        "function": "find_stations",
        "check": "check_command",
        "result": "list",
        "result_type": "StationListEntry",
        "writes": "none",
        "network": True,
        "idempotent": True,
        "cli": {
            "command": "obserwator stations find",
            "flags": {
                "kind": ["--kind", "-k"],
                "query": ["--query", "-q"],
                "source": ["--source"],
                "root": ["--root", "-r"],
                "provider": ["--provider"],
                "limit": ["--limit"],
                "cursor": ["--cursor"],
            },
        },
        "rest": {
            "method": "GET",
            "path": "/api/v1/stations/find",
            "server_options": ["root"],
            "local_options": [],
        },
    }
    check = input_schema("store check")
    assert check["required"] == ["datasets"]
    assert check["properties"]["datasets"]["items"] == {"enum": SERIES_KEYS}
    assert check["properties"]["years"]["items"] == {
        "anyOf": [
            {"type": "integer", "minimum": 1, "maximum": 9999},
            {"type": "string", "pattern": "^[0-9]{1,4}-[0-9]{1,4}$"},
        ]
    }
    assert check["properties"]["months"]["items"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 12,
    }
    sync = input_schema("pmaxtp sync")
    assert sync["dependentRequired"] == {"ind_x": ["ind_y"], "ind_y": ["ind_x"]}
    assert sync["properties"]["latitude"]["minimum"] == 49.0
    assert sync["x-obserwator"]["rest"]["method"] == "POST"
    store_sync = input_schema("store sync")
    assert store_sync["oneOf"] == [
        {"required": ["plan"]},
        {"required": ["datasets"]},
    ]
    assert store_sync["properties"]["series"]["default"] is True
    assert store_sync["x-obserwator"]["cli"]["flags"]["series"] == [
        "--series",
        "--no-series",
    ]
    read = input_schema("series read")
    assert read["properties"]["start"]["format"] == "date"
    assert read["oneOf"] == [
        {"required": ["version"]},
        {"required": ["dataset", "root"]},
    ]
    assert (
        input_schema("datasets files")["properties"]["dataset"]["enum"] == ARCHIVE_KEYS
    )


def test_a_command_entry_maps_the_declarations_to_commands_1():
    (entry,) = command_schema("stations find")["commands"]
    options = {option["name"]: option for option in entry["options"]}

    assert options["source"] == {
        "name": "source",
        "type": "string",
        "required": False,
        "default": "live",
        "enum": [
            {"value": "live", "meaning": "The providers' station lists, read live"},
            {
                "value": "store",
                "meaning": "Station lists and catalogs saved in the store",
            },
        ],
        "description": options["source"]["description"],
        "flags": ["--source"],
    }
    assert options["root"]["path_role"] == "root"
    assert entry["result"] == {
        "schema": "obserwator-result/1",
        "cardinality": "bounded",
    }
    assert entry["effects"] == {
        "read_only": True,
        "writes": "none",
        "idempotent": True,
        "network": True,
        "destructive": False,
    }
    # --check of the command itself plans it; a planner has no twin.
    assert entry["check"] == "stations find"
    assert command_schema("pmaxtp check")["commands"][0]["check"] is None
    assert entry["i18n"]["pl"]["summary"].startswith("Znajdź stacje")


def test_the_errors_of_a_command_follow_its_effects():
    def errors(name):
        return set(command_schema(name)["commands"][0]["errors"])

    assert errors("datasets list") == {"validation_error", "internal_error"}
    assert {"source_unavailable", "conflict", "io_error", "forbidden"} <= errors(
        "store sync"
    )
    # An export reads the store and writes a file outside it: no store lock.
    assert "conflict" not in errors("store export")
    assert "store_unavailable" not in errors("current hydro")


def test_rest_routes_cover_exactly_the_non_local_commands():
    commands = command_schema()["commands"]
    local = [entry["name"] for entry in commands if entry["rest"] is None]
    assert local == ["datasets download", "store init"]
    posts = [
        entry["name"]
        for entry in commands
        if (entry["rest"] or {}).get("method") == "POST"
    ]
    assert posts == ["pmaxtp sync", "store sync", "store catalog", "series build"]


@pytest.mark.parametrize(("command", "options"), SAMPLES)
def test_valid_options_pass_both_the_schema_and_validate_command(command, options):
    schema = input_schema(command)
    assert violations(options, schema) == []
    normalized = validate_command(command, options=options)
    assert violations(jsonable(normalized), schema) == []


@pytest.mark.parametrize(("command", "options", "option"), REJECTED)
def test_invalid_options_fail_both_the_schema_and_validate_command(
    command, options, option
):
    assert violations(options, input_schema(command)) != []
    with pytest.raises(ObserwatorValidationError) as error:
        validate_command(command, options=options)
    assert error.value.details["option"] == option


def test_station_options_take_imgw_and_wigos_codes_live_readings_only_imgw():
    for command, options in (
        ("series select", {"root": ROOT, "dataset": DAILY, "stations": ["149190310"]}),
        (
            "series select",
            {
                "root": ROOT,
                "dataset": "cz.chmi.hydro_daily",
                "stations": ["0-203-1-CB900003"],
            },
        ),
        ("series read", {"root": ROOT, "dataset": DAILY, "station": "0-20000-0-11406"}),
    ):
        assert violations(options, input_schema(command)) == []
        validate_command(command, options=options)
    # The provider's grammar depends on the dataset: a rule, not the schema pattern.
    mixed = {
        "root": ROOT,
        "dataset": DAILY,
        "stations": ["149190310", "0-203-1-CB900003"],
    }
    assert violations(mixed, input_schema("series select")) == []
    with pytest.raises(ObserwatorValidationError) as error:
        validate_command("series select", options=mixed)
    assert error.value.details["option"] == "stations"
    for command, options, option in (
        (
            "series select",
            {"root": ROOT, "dataset": DAILY, "stations": ["0-203-1-cb900003"]},
            "stations",
        ),
        (
            "series select",
            {"root": ROOT, "dataset": DAILY, "stations": ["12345678"]},
            "stations",
        ),
        (
            "series read",
            {"root": ROOT, "dataset": DAILY, "station": "0-203-1-cb900003"},
            "station",
        ),
        ("current hydro", {"station": "0-203-1-001000"}, "station"),
        ("current meteo", {"station": "0-203-0-11573"}, "station"),
    ):
        assert violations(options, input_schema(command)) != []
        with pytest.raises(ObserwatorValidationError) as error:
            validate_command(command, options=options)
        assert error.value.details["option"] == option


def test_store_scan_of_observations_answers_alike_in_python_cli_and_rest(
    tmp_path, monkeypatch
):
    root = init_store(tmp_path / "store").root
    (written,) = store_archives(root, DAILY, [2024])
    with_content(written.path)
    observed = observe(written.path)
    options = {"kind": "observation", "limit": 10}
    assert "observation" in input_schema("store scan")["properties"]["kind"]["enum"]
    normalized = validate_command("store scan", options={"root": root, **options})
    assert normalized["kind"] == "observation"

    python = run_command("store scan", options={"root": root, **options})
    local = python.to_json(root=root)
    (item,) = local["result"]
    assert (item["kind"], item["slot"], item["meta"]) == (
        "observation",
        "archive:pl.imgw.hydro_daily:2024/codz_2024.zip",
        None,
    )
    assert item["version"].endswith(observed.name)
    assert item["observation"]["same_content_as"] == written.path.parent.name
    printed = CliRunner().invoke(
        cli_app, cli_words("store scan", {"root": root, **options})
    )
    assert printed.exit_code == 0, printed.output
    assert canonical(json.loads(printed.stdout)) == canonical(local)
    monkeypatch.setattr(settings, "root", root)
    answered = TestClient(rest_app).request(**rest_request("store scan", options))
    assert answered.status_code == 200, answered.text
    assert canonical(answered.json()) == canonical(
        python.to_json(root=root, server=True)
    )


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_command_list_summarizes_every_command_of_the_catalog(lang):
    document = list_commands(lang=lang)
    catalog = command_schema(lang=lang)

    assert json.loads(json.dumps(document)) == document
    assert (document["schema"], document["version"], document["lang"]) == (
        "obserwator-command-list/1",
        __version__,
        lang,
    )
    assert document["tool"] == "obserwator"
    assert document["groups"] == [
        {"name": name, "summary": summary}
        for name, summary in catalog["groups"].items()
    ]
    assert [row["name"] for row in document["commands"]] == SPEC_COMMANDS
    results = {"single": "object", "bounded": "list", "unbounded": "stream"}
    for row, entry in zip(document["commands"], catalog["commands"], strict=True):
        assert row == {
            "name": entry["name"],
            "operation_id": entry["operation_id"],
            "group": entry["group"],
            "summary": entry["summary"],
            "read_only": entry["effects"]["read_only"],
            "check": entry["check"],
            "writes": entry["effects"]["writes"],
            "network": entry["effects"]["network"],
            "idempotent": entry["effects"]["idempotent"],
            "result": results[entry["result"]["cardinality"]],
            "result_type": entry["result_type"],
            "rest": None
            if entry["rest"] is None
            else {"method": entry["rest"]["method"], "path": entry["rest"]["path"]},
        }
        # The summary is the first sentence of the description (DOC-1.7: 100).
        assert entry["description"].startswith(row["summary"])
        assert len(row["summary"]) <= 100, row["name"]


def test_command_list_stays_within_the_default_page_budget():
    # DOC-1.7: at most 20,000 characters per default page of a CLI or MCP result.
    for lang in ("pl", "en"):
        text = json.dumps(list_commands(lang=lang), ensure_ascii=False)
        assert len(text) <= 20_000


def test_command_list_rejects_a_language_outside_the_catalog():
    with pytest.raises(ObserwatorValidationError) as error:
        list_commands(lang="de")
    assert (error.value.details["option"], error.value.details["allowed"]) == (
        "lang",
        ["en", "pl"],
    )


def test_every_path_option_has_a_role_and_the_write_targets_exclude_each_other():
    paths = {
        (spec.name, option.name)
        for spec in data_commands()
        for option in spec.options
        if option.type == "path"
    }
    commands = {entry["name"]: entry for entry in command_schema()["commands"]}
    roles = {
        (name, option["name"]): option.get("path_role")
        for name, entry in commands.items()
        for option in entry["options"]
        if (name, option["name"]) in paths
    }
    assert set(roles.values()) <= {"input", "output", "root"}, roles
    download = {o["name"]: o for o in commands["datasets download"]["options"]}
    assert download["output_dir"]["path_role"] == "output"
    assert download["root"]["path_role"] == "root"
    assert download["output_dir"]["one_of"] == download["root"]["one_of"]
    assert "one_of" not in download["dataset"]
    assert commands["datasets download"]["exclusive"] == [["output_dir", "root"]]
    assert "exclusive" not in commands["datasets files"]
