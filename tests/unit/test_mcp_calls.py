"""MCP tool calls on stdio servers (spec 2026-10-19 §6.5–§6.8, §9 "Wywołania MCP").

The SDK client talks to the server in memory (``Client(server)``); commands run on
a copy of the fixture store against recorded IMGW answers. Parity of every
contract case with Python and the CLI lives in ``tests/contract/test_mcp_contract.py``.
"""

import functools
import importlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

import anyio
import httpx
import respx
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from mcp.types import INVALID_PARAMS, jsonrpc_message_adapter

from imgwtools import (
    ERROR_CODES,
    agent_guide,
    check_command,
    command_schema,
    current_version,
    init_store,
    iter_store,
    store,
    validate_command,
)
from imgwtools.config import settings
from imgwtools.exceptions import IMGWValidationError
from imgwtools.mcp._calls import STREAM_LIMIT
from imgwtools.mcp._tools import Mode
from imgwtools.mcp.server import create_server
from imgwtools.testing import build_fixture_store
from tests.contract.support import (
    DAILY,
    H2023,
    H2024,
    NEW,
    PRECIP,
    V3,
    FakeImgw,
    archive_bytes,
    stamps,
)

H2023_SIGNAL = {
    "ETag": '"hydro-2023"',
    "Last-Modified": "Mon, 05 Jan 2026 10:00:00 GMT",
}


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("mcp") / "store").root


@pytest.fixture
def root(tmp_path, fixture_root):
    """A copy of the fixture store for one test."""
    target = tmp_path / "store"
    shutil.copytree(fixture_root, target)
    return target


@pytest.fixture(autouse=True)
def server_settings(monkeypatch):
    """No IMGW_ROOT and the default page maximum unless a test sets them."""
    monkeypatch.delenv("IMGW_ROOT", raising=False)
    monkeypatch.setattr(settings, "api_max_limit", 1000)


@pytest.fixture
def imgw():
    """IMGW with the 2023 and 2024 daily hydro archives; other URLs fail the test."""
    with respx.mock(assert_all_called=False) as router:
        fake = FakeImgw(router)
        fake.publish(H2023, H2023_SIGNAL, archive_bytes(H2023))
        fake.publish(H2024, V3, NEW)
        yield fake


async def call(tool: str, arguments: dict[str, Any], *, mode: Mode = "read"):
    async with Client(create_server(mode=mode, allow_dirs=(Path("/"),))) as client:
        return await client.call_tool(tool, arguments)


def compact(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def error_of(result) -> dict[str, Any]:
    """The error document of a tool result (text = structured content)."""
    assert result.is_error is True
    assert result.content[0].text == compact(result.structured_content)
    document: dict[str, Any] = result.structured_content
    return document


SYNC = {"datasets": [DAILY], "years": "2023-2024"}


# --------------------------------------------------------------------------
# Plans instead of writes (spec §6.3, §6.5 p. 3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["read", "write"])
async def test_a_writing_command_returns_its_plan_and_leaves_the_store(
    mode, root, imgw
):
    before = stamps(root)

    result = await call("imgw_store_sync", {"root": str(root), **SYNC}, mode=mode)

    envelope = result.structured_content
    assert result.is_error is False
    assert result.content[0].text == compact(envelope)
    assert (envelope["command"], envelope["check"]) == ("store sync", True)
    assert envelope["result"]["schema"] == "imgw-plan/1"
    planned = check_command("store sync", options={"root": root, **SYNC})
    assert envelope["result"]["items"] == planned.to_json(root=root)["result"]["items"]
    assert stamps(root) == before
    assert imgw.downloads() == []


@pytest.mark.parametrize(
    ("tool", "arguments", "option"),
    [
        ("imgw_store_sync", {**SYNC, "check": False}, "check"),
        ("imgw_store_sync", {**SYNC, "output_dir": "plain"}, "output_dir"),
        (
            "imgw_datasets_download",
            {"dataset": DAILY, "years": "2024", "output_dir": "plain"},
            "output_dir",
        ),
        ("imgw_store_check", {**SYNC, "plan": "plan.json"}, "plan"),
        (
            "imgw_series_export",
            {"dataset": DAILY, "station": "149190310", "output": "x.csv"},
            "output",
        ),
        (
            "imgw_store_export",
            {"version": "archives/versions/x", "force": True},
            "force",
        ),
    ],
    ids=[
        "check-false",
        "sync-output-dir",
        "download-output-dir",
        "store-check-plan",
        "export-output",
        "export-force",
    ],
)
async def test_a_server_without_writes_forbids_every_write(
    tool, arguments, option, root, imgw, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    before = stamps(root)

    result = await call(tool, {"root": str(root), **arguments})

    document = error_of(result)
    spec = ERROR_CODES["forbidden"]
    assert document["code"] == "forbidden"
    assert document["title"] == spec.title
    assert document["details"] == {"reason": "writes_disabled", "option": option}
    assert stamps(root) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["store"]
    assert imgw.requests("GET") == imgw.requests("HEAD") == []


async def test_check_is_a_boolean(root):
    result = await call("imgw_store_sync", {"root": str(root), **SYNC, "check": "tak"})

    document = error_of(result)
    assert document["code"] == "validation_error"
    assert document["details"]["option"] == "check"


async def test_null_arguments_are_absent(root, imgw):
    planned = await call("imgw_store_check", {"root": str(root), **SYNC, "plan": None})
    paged = await call("imgw_datasets_list", {"limit": None})

    assert planned.is_error is False
    assert paged.structured_content["result"]["limit"] == 50


# --------------------------------------------------------------------------
# Defaults of the server: page, root, language (spec §3.5, §6.4–§6.5)
# --------------------------------------------------------------------------


async def test_list_commands_page_by_50_and_at_most_imgw_api_max_limit(monkeypatch):
    whole = (await call("imgw_datasets_list", {})).structured_content["result"]
    monkeypatch.setattr(settings, "api_max_limit", 5)
    small = (await call("imgw_datasets_list", {})).structured_content["result"]
    above = await call("imgw_datasets_list", {"limit": 6})

    assert (whole["limit"], len(whole["items"])) == (50, whole["total"])
    assert (small["limit"], len(small["items"]), small["total"]) == (
        5,
        5,
        whole["total"],
    )
    document = error_of(above)
    assert document["code"] == "validation_error"
    assert document["details"] == {"option": "limit", "value": 6, "maximum": 5}


async def test_imgw_root_fills_an_absent_root(root, monkeypatch):
    monkeypatch.setenv("IMGW_ROOT", str(root))

    info = await call("imgw_store_info", {})
    found = await call("imgw_stations_find", {"source": "store", "query": "1491"})
    live = await call("imgw_stations_find", {"query": "raba", "check": True})

    assert info.structured_content["result"]["root"] == str(root)
    assert found.is_error is False and found.structured_content["result"]["total"] > 0
    # A live search takes no root (env_root_when): its plan names the live list.
    assert live.is_error is False
    assert live.structured_content["result"]["actions"][0]["status"] == "unverifiable"


async def test_lang_option_defaults_to_english():
    result = await call("imgw_commands_schema", {"command": "store info"})

    schema = result.structured_content["result"]
    assert schema == command_schema("store info", lang="en")


# --------------------------------------------------------------------------
# Streams (spec §6.6)
# --------------------------------------------------------------------------


async def test_commands_guide_stream_is_the_english_agent_guide_text():
    result = await call("imgw_commands_guide", {})

    text = "".join(agent_guide(lang="en"))
    assert result.is_error is False
    assert result.content[0].text == text
    assert result.structured_content == {
        "schema": "imgw-result/1",
        "command": "commands guide",
        "check": False,
        "status": "ok",
        "result": {
            "format": "agents",
            "bytes": len(text.encode("utf-8")),
            "lines": text.count("\n"),
        },
        "notices": [],
    }


async def test_a_stream_over_256_kib_is_refused_and_no_longer_read(root, monkeypatch):
    archive = current_version(root, slot=f"archive:{PRECIP}:2001/2001_01_o.zip").version
    produced = {"lines": 0, "closed": False}
    original = store.export_archive

    @functools.wraps(original)
    def endless(*args, **kwargs):
        def lines():
            try:
                while True:
                    produced["lines"] += 1
                    yield "x" * 1023 + "\n"
            finally:
                produced["closed"] = True

        return lines()

    monkeypatch.setattr(store, "export_archive", endless)

    result = await call("imgw_store_export", {"version": str(archive)})

    document = error_of(result)
    assert document["code"] == "validation_error"
    assert document["details"] == {"maximum_bytes": STREAM_LIMIT}
    assert produced == {"lines": STREAM_LIMIT // 1024 + 1, "closed": True}


# --------------------------------------------------------------------------
# Progress and cancellation (spec §6.8)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("client_mode", ["auto", "legacy"])
async def test_progress_reaches_a_client_that_asked_for_it(client_mode, root, imgw):
    expected = []
    check_command(
        "store sync",
        options={"root": root, **SYNC},
        on_progress=lambda p: expected.append(
            (p.current, p.total, f"[{p.current}/{p.total}] {p.message}")
        ),
    )
    received = []

    async def progress(value, total, message):
        received.append((value, total, message))

    async with Client(create_server(), mode=client_mode) as client:
        silent = await client.call_tool("imgw_store_sync", {"root": str(root), **SYNC})
        reported = await client.call_tool(
            "imgw_store_sync", {"root": str(root), **SYNC}, progress_callback=progress
        )

    assert silent.is_error is reported.is_error is False
    assert len(expected) == 2
    assert received == expected


async def test_a_cancelled_call_reaches_cancel_and_leaves_no_partial_version(
    tmp_path, imgw, monkeypatch
):
    root = init_store(tmp_path / "store").root
    files = sorted(path for path in root.rglob("*") if path.is_file())
    seen = {}
    original = store.sync_store

    @functools.wraps(original)
    def spy(*args, **kwargs):
        seen["cancel"] = kwargs["cancel"]
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "sync_store", spy)
    downloading = threading.Event()

    def held(request):
        downloading.set()
        deadline = time.monotonic() + 10
        while not seen["cancel"]():  # the download ends after the cancellation
            assert time.monotonic() < deadline, "cancel nie dotarło do sync_store"
            time.sleep(0.01)
        content = archive_bytes(H2023)
        headers = {**H2023_SIGNAL, "Content-Length": str(len(content))}
        return httpx.Response(200, headers=headers, content=content)

    imgw.router.get(H2023.url).mock(side_effect=held)
    arguments = {"root": str(root), **SYNC, "check": False}

    async with (
        Client(create_server(mode="write", allow_dirs=(Path("/"),))) as client,
        anyio.create_task_group() as group,
    ):
        group.start_soon(client.call_tool, "imgw_store_sync", arguments)
        assert await anyio.to_thread.run_sync(downloading.wait, 10)
        group.cancel_scope.cancel()

    assert seen["cancel"]() is True
    assert H2024.url not in imgw.requests("GET")  # stopped before the next archive
    # The archive downloaded during the cancellation is not stored either.
    assert list(iter_store(root)) == []
    assert sorted(path for path in root.rglob("*") if path.is_file()) == files


# --------------------------------------------------------------------------
# Errors (spec §6.5 p. 1, §6.7)
# --------------------------------------------------------------------------


async def test_an_unknown_tool_is_a_protocol_error():
    async with Client(create_server()) as client:
        with pytest.raises(MCPError) as caught:
            await client.call_tool("imgw_store_delete", {})

    assert caught.value.code == INVALID_PARAMS


async def test_arguments_other_than_an_object_are_a_protocol_error():
    # Erratum A03 of spec §6.5 p. 2: the SDK refuses them before the tool runs.
    server = create_server()
    to_server, from_client = anyio.create_memory_object_stream(4)
    to_client, from_server = anyio.create_memory_object_stream(4)

    async def send(message: dict) -> None:
        await to_server.send(
            SessionMessage(jsonrpc_message_adapter.validate_python(message))
        )

    async with anyio.create_task_group() as group:
        options = server.create_initialization_options()
        group.start_soon(server.run, from_client, to_client, options)
        await send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        await from_server.receive()
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        answers = []
        for number, value in enumerate([[1, 2], "datasets", 7], start=2):
            params = {"name": "imgw_datasets_list", "arguments": value}
            await send(
                {
                    "jsonrpc": "2.0",
                    "id": number,
                    "method": "tools/call",
                    "params": params,
                }
            )
            answers.append((await from_server.receive()).message.model_dump())
        group.cancel_scope.cancel()

    assert [answer["error"]["code"] for answer in answers] == [INVALID_PARAMS] * 3


async def test_an_error_is_the_english_cli_document():
    options = {"latitude": "1", "longitude": 21.01}
    with pytest.raises(IMGWValidationError) as raised:
        validate_command("pmaxtp fetch", options=options)

    result = await call("imgw_pmaxtp_fetch", options)

    spec = ERROR_CODES["validation_error"]
    assert error_of(result) == {
        "code": "validation_error",
        "title": spec.title,
        "detail": raised.value.detail,
        "details": dict(raised.value.details),
    }


async def test_a_program_error_is_an_internal_error_with_its_trace_on_stderr(
    monkeypatch, capsys
):
    registry = importlib.import_module("imgwtools.datasets")
    original = registry.datasets

    @functools.wraps(original)
    def broken(*args, **kwargs):
        raise RuntimeError("błąd programu w rejestrze")

    monkeypatch.setattr(registry, "datasets", broken)

    result = await call("imgw_datasets_list", {})

    document = error_of(result)
    assert (document["code"], document["details"]) == ("internal_error", {})
    assert "błąd programu" not in document["detail"]
    assert "RuntimeError: błąd programu w rejestrze" in capsys.readouterr().err
