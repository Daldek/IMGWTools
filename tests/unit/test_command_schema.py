"""command_schema (spec §13.8): JSON Schema 2020-12 of every command and imgw-commands/1."""

import json

import pytest

from imgwtools import __version__
from imgwtools._jsonable import jsonable
from imgwtools.commands import command_schema, validate_command
from imgwtools.datasets import datasets
from imgwtools.exceptions import ERROR_CODES, IMGWValidationError
from tests.contract.support import violations
from tests.unit.test_commands import REJECTED, SAMPLES, SPEC_COMMANDS

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ARCHIVE_KEYS = [d.key for d in datasets() if d.first_year is not None]
SERIES_KEYS = [
    d.key
    for d in datasets()
    if d.in_store and d.time_unit in ("day", "month", "half_year")
]


def test_catalog_document_lists_35_schemas_groups_errors_and_exit_codes():
    document = command_schema()
    assert json.loads(json.dumps(document)) == document
    assert (document["schema"], document["version"], document["result_schema"]) == (
        "imgw-commands/1",
        __version__,
        "imgw-result/1",
    )
    assert [schema["title"] for schema in document["commands"]] == SPEC_COMMANDS
    assert list(document["groups"]) == list(
        dict.fromkeys(name.split()[0] for name in SPEC_COMMANDS)
    )
    assert document["errors"] == [
        {
            "code": spec.code,
            "title": spec.title,
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
    for schema in document["commands"]:
        assert command_schema(schema["title"]) == schema


def test_unknown_command_is_a_validation_error_listing_the_commands():
    with pytest.raises(IMGWValidationError) as error:
        command_schema("store delete")
    assert error.value.details["option"] == "command"
    assert error.value.details["allowed"] == SPEC_COMMANDS


def test_option_types_rules_and_interfaces_map_to_the_schema():
    find = command_schema("stations find")
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
        "root": {"type": "string", "x-imgw-type": "path"},
        "limit": {"type": "integer", "minimum": 1},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
    }
    meta = {key: value for key, value in find["x-imgw"].items() if key != "rules"}
    assert meta == {
        "command": "stations find",
        "group": "stations",
        "function": "find_stations",
        "check": "check_command",
        "result": "list",
        "result_type": "StationListEntry",
        "cli": {
            "command": "imgw stations find",
            "flags": {
                "kind": ["--kind", "-k"],
                "query": ["--query", "-q"],
                "source": ["--source"],
                "root": ["--root", "-r"],
                "limit": ["--limit"],
                "offset": ["--offset"],
            },
        },
        "rest": {
            "method": "GET",
            "path": "/api/v1/stations/find",
            "server_options": ["root"],
            "local_options": [],
        },
    }
    check = command_schema("store check")
    assert check["required"] == ["root", "datasets", "years"]
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
    sync = command_schema("pmaxtp sync")
    assert sync["dependentRequired"] == {"ind_x": ["ind_y"], "ind_y": ["ind_x"]}
    assert sync["properties"]["latitude"]["minimum"] == 49.0
    assert sync["x-imgw"]["rest"]["method"] == "POST"
    store_sync = command_schema("store sync")
    assert store_sync["oneOf"] == [
        {"required": ["plan"]},
        {"required": ["datasets", "years"]},
    ]
    assert store_sync["properties"]["series"]["default"] is True
    assert store_sync["x-imgw"]["cli"]["flags"]["series"] == ["--series", "--no-series"]
    read = command_schema("series read")
    assert read["properties"]["start"]["format"] == "date"
    assert read["oneOf"] == [
        {"required": ["version"]},
        {"required": ["dataset", "root"]},
    ]
    assert (
        command_schema("datasets files")["properties"]["dataset"]["enum"]
        == ARCHIVE_KEYS
    )


def test_rest_routes_cover_exactly_the_non_local_commands():
    commands = command_schema()["commands"]
    local = [schema["title"] for schema in commands if schema["x-imgw"]["rest"] is None]
    assert local == [
        "datasets download",
        "store init",
        "project init",
        "project add",
        "project remove",
        "project set-store",
        "project download",
        "project check",
        "project status",
        "project verify",
    ]
    posts = [
        schema["title"]
        for schema in commands
        if (schema["x-imgw"]["rest"] or {}).get("method") == "POST"
    ]
    assert posts == ["pmaxtp sync", "store sync", "store catalog", "series build"]


@pytest.mark.parametrize(("command", "options"), SAMPLES)
def test_valid_options_pass_both_the_schema_and_validate_command(command, options):
    schema = command_schema(command)
    assert violations(options, schema) == []
    normalized = validate_command(command, options=options)
    assert violations(jsonable(normalized), schema) == []


@pytest.mark.parametrize(("command", "options", "option"), REJECTED)
def test_invalid_options_fail_both_the_schema_and_validate_command(
    command, options, option
):
    assert violations(options, command_schema(command)) != []
    with pytest.raises(IMGWValidationError) as error:
        validate_command(command, options=options)
    assert error.value.details["option"] == option
