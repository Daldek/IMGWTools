"""MCP tool list (spec 2026-10-19 §6.3–§6.4, §9 "Lista narzędzi MCP").

Every server mode is listed through the SDK client in memory (``Client(server)``);
the expectations come from the input schemas of the catalog (names, order, options, required
groups, effects, texts), never from a written-down list.
"""

import re
from typing import Any

import pytest

pytest.importorskip("mcp")

import httpx
from mcp import Client

from obserwator.config import Settings, settings
from obserwator.exceptions import ObserwatorValidationError
from obserwator.mcp._tools import Mode
from obserwator.mcp.server import create_server, http_app
from tests.contract.support import input_schemas

STDIO = ("read", "write")
# Tools are fixed by mode and page maximum: list each server once.
_LISTINGS: dict[tuple[str, int], list[dict[str, Any]]] = {}


async def listing(mode: Mode) -> list[dict[str, Any]]:
    """Tools of a server without OBSERWATOR_ROOT as JSON (``tools/list`` on the wire)."""
    key = (mode, settings.api_max_limit)
    if key not in _LISTINGS:
        async with Client(create_server(mode=mode)) as client:
            tools = (await client.list_tools()).tools
        _LISTINGS[key] = [
            tool.model_dump(mode="json", by_alias=True, exclude_none=True)
            for tool in tools
        ]
    return _LISTINGS[key]


def catalog() -> list[dict[str, Any]]:
    return input_schemas(lang="en")


def by_command(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {tool["_meta"]["obserwator/command"]: tool for tool in tools}


def keywords(value: object) -> set[str]:
    """Every key of every mapping in ``value``, at any depth."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keywords(item)}
    if isinstance(value, list):
        return {key for item in value for key in keywords(item)}
    return set()


def removed(schema: dict[str, Any], mode: str) -> set[str]:
    """Options a mode does not offer (spec §6.4 p. 2)."""
    if mode == "read":
        return {
            name
            for name, prop in schema["properties"].items()
            if "x-obserwator-writes" in prop
        }
    if mode == "http":
        rest = schema["x-obserwator"]["rest"]
        return set(rest["server_options"]) | set(rest["local_options"])
    return set()


@pytest.fixture(autouse=True)
def no_obserwator_root(monkeypatch):
    """Servers of these tests have no OBSERWATOR_ROOT unless a test sets one."""
    monkeypatch.delenv("OBSERWATOR_ROOT", raising=False)
    monkeypatch.setattr(settings, "api_max_limit", 1000)


# --------------------------------------------------------------------------
# Names, order and texts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", STDIO)
async def test_stdio_tools_are_every_catalog_command_in_catalog_order(mode):
    tools = await listing(mode)

    assert [tool["name"] for tool in tools] == [
        schema["x-obserwator"]["operation_id"] for schema in catalog()
    ]
    for tool, schema in zip(tools, catalog(), strict=True):
        command = schema["x-obserwator"]["command"]
        assert tool["title"] == f"obserwator {command}"
        assert tool["_meta"] == {"obserwator/command": command}


async def test_http_tools_are_the_commands_with_a_rest_route():
    tools = await listing("http")

    assert [tool["name"] for tool in tools] == [
        schema["x-obserwator"]["operation_id"]
        for schema in catalog()
        if schema["x-obserwator"]["rest"] is not None
    ]


@pytest.mark.parametrize("mode", [*STDIO, "http"])
async def test_texts_are_english(mode):
    tools = by_command(await listing(mode))

    for schema in catalog():
        meta = schema["x-obserwator"]
        tool = tools.get(meta["command"])
        if tool is None:
            continue
        paragraphs = tool["description"].split("\n\n")
        assert paragraphs[0] == schema["description"]
        if meta["rules"]:
            heading, *rules = paragraphs[1].split("\n")
            assert heading == "Rules:"
            assert rules == [f"- {rule}" for rule in meta["rules"]]
        # The sentence of the mode ends the description of a writing command.
        assert len(paragraphs) == 1 + bool(meta["rules"]) + (meta["writes"] != "none")
        for name, prop in tool["inputSchema"]["properties"].items():
            if name in schema["properties"] and mode != "http":
                assert prop["description"].startswith(
                    schema["properties"][name]["description"]
                )


async def test_mode_sentence_tells_whether_a_writing_command_plans_or_writes():
    read = by_command(await listing("read"))
    write = by_command(await listing("write"))

    for schema in catalog():
        command = schema["x-obserwator"]["command"]
        if schema["x-obserwator"]["writes"] == "none":
            continue
        planning = read[command]["description"].split("\n\n")[-1]
        writing = write[command]["description"].split("\n\n")[-1]
        assert "obserwator-plan/1" in planning and "check=false" in writing
        assert planning != writing


# --------------------------------------------------------------------------
# Input schemas (spec §6.4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [*STDIO, "http"])
async def test_input_schema_is_the_command_schema_of_the_offered_options(mode):
    tools = by_command(await listing(mode))

    for schema in catalog():
        tool = tools.get(schema["x-obserwator"]["command"])
        if tool is None:
            continue
        given = tool["inputSchema"]
        offered = [
            name for name in schema["properties"] if name not in removed(schema, mode)
        ]
        twin = "check" in given["properties"]
        assert list(given["properties"]) == offered + ["check"] * twin
        assert not {key for key in keywords(given) if key.startswith("x-obserwator")}
        assert {"$schema", "title", "description", "x-obserwator"}.isdisjoint(given)
        assert given["type"] == "object"
        assert given["additionalProperties"] is False
        assert given.get("required", []) == [
            name for name in schema.get("required", []) if name in offered
        ]
        for name in offered:
            expected = {
                key: value
                for key, value in schema["properties"][name].items()
                if not key.startswith("x-obserwator")
            }
            prop = given["properties"][name]
            if name == "root" and mode != "http":  # the note of the default store
                prop = {
                    **prop,
                    "description": re.sub(
                        r"; default( with [^:]+)?: the MCP server's store$",
                        "",
                        prop["description"],
                    ),
                }
            if mode == "http" and name in ("version", "plan", "user_locations"):
                continue  # as the REST route takes it (next test)
            if name == "limit":
                expected.update(default=50, maximum=settings.api_max_limit)
            assert prop == expected, (schema["x-obserwator"]["command"], name)


async def test_http_options_are_those_of_the_rest_route():
    tools = by_command(await listing("http"))

    plan = tools["store sync"]["inputSchema"]["properties"]["plan"]
    assert plan["type"] == "object"  # an obserwator-plan/1 object, not a server file
    for tool in tools.values():
        names = set(tool["inputSchema"]["properties"])
        assert not names & {"root", "output", "output_dir", "force"}
        if "version" in names:
            version = tool["inputSchema"]["properties"]["version"]
            assert "/versions/" in version["description"]  # relative to the store


async def test_removed_options_leave_the_required_groups():
    tools = by_command(await listing("http"))

    # series read: version | dataset+root → version | dataset (spec §6.4 p. 3)
    assert tools["series read"]["inputSchema"]["oneOf"] == [
        {"required": ["version"]},
        {"required": ["dataset"]},
    ]
    for tool in tools.values():
        given = tool["inputSchema"]
        names = set(given["properties"])
        assert set(given.get("required", [])) <= names
        for group in given.get("oneOf", []):
            assert group["required"] and set(group["required"]) <= names
        for key, group in given.get("dependentRequired", {}).items():
            assert key in names and group and set(group) <= names


@pytest.mark.parametrize("mode", STDIO)
async def test_obserwator_root_makes_root_optional_on_stdio(
    mode, monkeypatch, tmp_path
):
    plain = {tool["name"]: tool["inputSchema"] for tool in await listing(mode)}
    monkeypatch.setenv("OBSERWATOR_ROOT", str(tmp_path))
    async with Client(create_server(mode=mode)) as client:
        rooted = {
            tool.name: tool.input_schema for tool in (await client.list_tools()).tools
        }

    commands = {schema["x-obserwator"]["operation_id"]: schema for schema in catalog()}
    for name, given in rooted.items():
        if "root" not in given["properties"]:
            assert given == plain[name]
            continue
        assert "root" not in given.get("required", [])
        for group in given.get("oneOf", []):
            assert "root" not in group["required"]
        description = given["properties"]["root"]["description"]
        assert description.startswith(plain[name]["properties"]["root"]["description"])
        assert description.endswith("the MCP server's store")
        when = commands[name]["x-obserwator"]["command"] == "stations find"
        assert ("source=store" in description.rsplit(";", 1)[1]) is when
    assert rooted["obserwator_series_read"]["oneOf"] == [
        {"required": ["version"]},
        {"required": ["dataset"]},
    ]


async def test_list_pages_follow_obserwator_api_max_limit(monkeypatch):
    monkeypatch.setattr(settings, "api_max_limit", 20)

    tools = by_command(await listing("read"))

    for schema in catalog():
        tool = tools[schema["x-obserwator"]["command"]]
        limit = tool["inputSchema"]["properties"].get("limit")
        if schema["x-obserwator"]["result"] == "list":
            assert (limit["default"], limit["maximum"]) == (20, 20)
        else:
            assert limit is None


async def test_lang_option_defaults_to_english():
    tools = await listing("read")

    with_lang = [tool for tool in tools if "lang" in tool["inputSchema"]["properties"]]
    assert [tool["name"] for tool in with_lang] == [
        "obserwator_commands_list",
        "obserwator_commands_schema",
        "obserwator_commands_guide",
    ]
    for tool in with_lang:
        assert tool["inputSchema"]["properties"]["lang"]["default"] == "en"


# --------------------------------------------------------------------------
# check and annotations (spec §6.3, §6.4 p. 6)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", STDIO)
async def test_check_exists_exactly_for_commands_with_a_twin(mode):
    tools = by_command(await listing(mode))

    for schema in catalog():
        meta = schema["x-obserwator"]
        check = tools[meta["command"]]["inputSchema"]["properties"].get("check")
        if meta["check"] is None:
            assert check is None, meta["command"]
        elif meta["writes"] == "none":
            assert (check["type"], check["default"]) == ("boolean", False)
        elif mode == "read":
            assert (check["const"], check["default"]) == (True, True)
            assert "type" not in check
        else:
            assert (check["type"], check["default"]) == ("boolean", True)


async def test_http_plans_only_through_post_routes():
    tools = by_command(await listing("http"))

    for schema in catalog():
        meta = schema["x-obserwator"]
        if meta["rest"] is None:
            continue
        check = tools[meta["command"]]["inputSchema"]["properties"].get("check")
        if meta["rest"]["method"] == "POST":
            assert (check["const"], check["default"]) == (True, True)
        else:
            assert check is None  # GET routes have no ?check=true


@pytest.mark.parametrize("mode", [*STDIO, "http"])
async def test_annotations_follow_the_effects_of_the_catalog(mode):
    tools = by_command(await listing(mode))

    for schema in catalog():
        meta = schema["x-obserwator"]
        tool = tools.get(meta["command"])
        if tool is None:
            continue
        properties = tool["inputSchema"]["properties"]
        writing = [
            prop["x-obserwator-writes"]
            for name, prop in schema["properties"].items()
            if "x-obserwator-writes" in prop and name in properties
        ]
        fixed = properties.get("check", {}).get("const") is True
        writable = (meta["writes"] != "none" and not fixed) or bool(writing)
        expected = {
            "title": f"obserwator {meta['command']}",
            "readOnlyHint": not writable,
            "destructiveHint": writable
            and (meta["writes"] == "replace" or "replace" in writing),
            "idempotentHint": meta["idempotent"],
            "openWorldHint": meta["network"],
        }
        assert tool["annotations"] == expected, meta["command"]
    if mode != "write":  # a server without writes offers no write at all
        assert all(tool["annotations"]["readOnlyHint"] for tool in tools.values())


async def test_store_sync_of_a_server_without_writes_matches_spec_example(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OBSERWATOR_ROOT", str(tmp_path))
    async with Client(create_server(mode="read")) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    tool = tools["obserwator_store_sync"].model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    given = tool["inputSchema"]
    assert tool["title"] == "obserwator store sync"
    assert list(given["properties"]) == [
        "root",
        "plan",
        "datasets",
        "years",
        "months",
        "stations",
        "series",
        "check",
    ]
    assert given["properties"]["root"]["description"].endswith(
        "; default: the MCP server's store"
    )
    assert given["oneOf"] == [{"required": ["plan"]}, {"required": ["datasets"]}]
    assert "required" not in given
    assert tool["annotations"] == {
        "title": "obserwator store sync",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
    assert tool["description"].endswith(
        "The MCP server runs without writes: a call returns the obserwator-plan/1 plan (check)."
    )


# --------------------------------------------------------------------------
# Server configuration
# --------------------------------------------------------------------------


def test_unknown_mode_is_a_validation_error():
    with pytest.raises(ObserwatorValidationError) as caught:
        create_server(mode="admin")

    assert caught.value.details["option"] == "mode"
    assert caught.value.details["value"] == "admin"


def test_allowed_hosts_are_comma_separated(monkeypatch):
    monkeypatch.setenv(
        "OBSERWATOR_MCP_ALLOWED_HOSTS", "mcp.example.com, api.example.com:8443,"
    )

    assert Settings(_env_file=None).mcp_allowed_hosts == [
        "mcp.example.com",
        "api.example.com:8443",
    ]
    monkeypatch.delenv("OBSERWATOR_MCP_ALLOWED_HOSTS")
    assert Settings(_env_file=None).mcp_allowed_hosts == ["127.0.0.1", "localhost"]


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


async def post_initialize(app, host: str, **headers: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=f"http://{host}"
    ) as http:
        return await http.post(
            "/mcp",
            json=INITIALIZE,
            headers={"Accept": "application/json, text/event-stream", **headers},
        )


@pytest.mark.parametrize(
    ("allowed", "host", "status"),
    [
        (None, "127.0.0.1:8000", 200),
        (None, "localhost", 200),
        (None, "localhost:3000", 200),
        (None, "mcp.example.com", 421),
        (["mcp.example.com"], "mcp.example.com:443", 200),
        (["mcp.example.com"], "localhost:8000", 421),
    ],
)
async def test_http_app_answers_only_the_allowed_hosts_with_any_port(
    allowed, host, status, monkeypatch
):
    if allowed is not None:
        monkeypatch.setattr(settings, "mcp_allowed_hosts", allowed)
    app = http_app()

    async with app.router.lifespan_context(app):
        answered = await post_initialize(app, host)
        foreign = await post_initialize(app, host, Origin="https://example.org")

    assert answered.status_code == status
    if status == 200:
        assert '"serverInfo"' in answered.text
        assert foreign.status_code == 403  # browser clients are not served
