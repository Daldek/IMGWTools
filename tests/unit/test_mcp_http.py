"""MCP over Streamable HTTP in the REST application (spec 2026-10-19 §6.2, §6.9, §9).

``imgw server`` serves ``/mcp`` only with ``IMGW_MCP_ENABLED=true`` and the ``mcp``
extra: these tests import the REST application again under the settings of the
test, run its lifespan (which runs the session manager of the SDK) and talk to
``/mcp`` with the SDK client in process (ASGI, no network). The parity of every
contract case with REST is in ``tests/contract/test_mcp_http_contract.py``.
"""

import functools
import importlib
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any

import pytest

pytest.importorskip("mcp")

import anyio
import httpx
import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

import imgwtools.api
import imgwtools.api.main
from imgwtools import ERROR_CODES
from imgwtools.config import settings
from imgwtools.exceptions import IMGWValidationError
from imgwtools.mcp._calls import STREAM_LIMIT
from imgwtools.mcp.server import create_server
from tests.contract.support import command_document

HOST = "127.0.0.1:8000"
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
# Tools with a REST route, in catalog order (spec §6.3, mode http).
ROUTES = [
    schema["x-imgw"]["operation_id"]
    for schema in command_document()["commands"]
    if schema["x-imgw"]["rest"] is not None
]


# The module of agent_guide (the package exports the function under its name).
GUIDE = importlib.import_module("imgwtools.agent_guide")


@pytest.fixture(autouse=True)
def server(monkeypatch):
    """A REST server without a store, MCP off, Polish, default hosts and page."""
    for name, value in (
        ("store_root", None),
        ("store_writes_enabled", False),
        ("api_max_limit", 1000),
        ("lang", "pl"),
        ("mcp_enabled", False),
        ("mcp_allowed_hosts", ["127.0.0.1", "localhost"]),
    ):
        monkeypatch.setattr(settings, name, value)
    return settings


def reimported(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """``imgwtools.api.main`` imported anew under the current settings."""
    monkeypatch.setattr(imgwtools.api, "main", imgwtools.api.main)
    monkeypatch.delitem(sys.modules, "imgwtools.api.main")
    return importlib.import_module("imgwtools.api.main")


def enabled(monkeypatch: pytest.MonkeyPatch, *, lang: str = "pl") -> FastAPI:
    """The REST application of a server with ``IMGW_MCP_ENABLED=true``."""
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "lang", lang)
    app: FastAPI = reimported(monkeypatch).app
    return app


@asynccontextmanager
async def connected(app: FastAPI, *, mode: str = "auto") -> AsyncIterator[Client]:
    """SDK client of ``/mcp`` of ``app`` running in its lifespan (ASGI, no network)."""
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=f"http://{HOST}"
        ) as http,
        Client(
            streamable_http_client(f"http://{HOST}/mcp", http_client=http), mode=mode
        ) as client,
    ):
        yield client


def dumped(tools) -> list[dict[str, Any]]:
    return [
        tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in tools
    ]


def compact(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def error_of(result) -> dict[str, Any]:
    """The error document of a tool result (text = structured content)."""
    assert result.is_error is True
    assert result.content[0].text == compact(result.structured_content)
    document: dict[str, Any] = result.structured_content
    return document


async def post_initialize(app: FastAPI, host: str, **headers: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=f"http://{host}"
    ) as http:
        return await http.post(
            "/mcp",
            json=INITIALIZE,
            headers={"Accept": "application/json, text/event-stream", **headers},
        )


# --------------------------------------------------------------------------
# /mcp of imgw server: tools, language, lifespan
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "client_mode"), [("pl", "auto"), ("pl", "legacy"), ("en", "auto")]
)
async def test_mcp_serves_the_rest_routes_as_tools_in_the_language_of_imgw_lang(
    lang, client_mode, monkeypatch
):
    app = enabled(monkeypatch, lang=lang)
    async with Client(create_server(mode="http", lang=lang)) as memory:
        expected = (await memory.list_tools()).tools

    async with connected(app, mode=client_mode) as client:
        tools = (await client.list_tools()).tools
        answered = await client.call_tool("datasets_providers", {})

    assert [tool.name for tool in tools] == ROUTES
    assert dumped(tools) == dumped(expected)
    rest = TestClient(app).get("/api/v1/datasets/providers", params={"limit": 50})
    assert answered.is_error is False
    assert answered.structured_content == rest.json()
    assert answered.content[0].text == rest.text


async def test_a_problem_of_rest_is_the_error_result_in_the_server_language(
    monkeypatch,
):
    app = enabled(monkeypatch, lang="en")
    arguments = {"latitude": "1", "longitude": 21.01}

    async with connected(app) as client:
        result = await client.call_tool("pmaxtp_fetch", arguments)

    problem = TestClient(app).get(
        "/api/v1/pmaxtp/fetch", params=arguments, headers={"Accept-Language": "en"}
    )
    assert problem.status_code == 400
    body = problem.json()
    assert error_of(result) == {
        key: body[key] for key in ("code", "title", "detail", "details")
    }
    assert body["title"] == ERROR_CODES["validation_error"].title_en


# --------------------------------------------------------------------------
# Plans only; server and local options stay with REST
# --------------------------------------------------------------------------


async def test_a_write_through_http_is_forbidden(monkeypatch):
    app = enabled(monkeypatch)

    async with connected(app) as client:
        result = await client.call_tool(
            "store_sync",
            {"datasets": ["pl.imgw.hydro_daily"], "years": [2024], "check": False},
        )

    document = error_of(result)
    assert document["code"] == "forbidden"
    assert document["details"] == {"reason": "writes_disabled", "option": "check"}


@pytest.mark.parametrize(
    ("tool", "arguments", "option"),
    [
        ("store_info", {"root": "/srv/imgw"}, "root"),
        ("store_export", {"version": "archives/x.zip", "path": "wynik.csv"}, "path"),
    ],
)
async def test_server_and_local_options_are_refused_by_rest(
    tool, arguments, option, monkeypatch
):
    app = enabled(monkeypatch)

    async with connected(app) as client:
        result = await client.call_tool(tool, arguments)

    document = error_of(result)
    assert (document["code"], document["details"]["option"]) == (
        "validation_error",
        option,
    )


async def test_a_stream_over_256_kib_is_refused_and_rest_stops_producing_it(
    monkeypatch,
):
    app = enabled(monkeypatch)
    produced = {"lines": 0}
    original = GUIDE.agent_guide

    @functools.wraps(original)
    def endless(*args, **kwargs):
        def lines():
            while True:
                produced["lines"] += 1
                yield "x" * 1023 + "\n"

        return lines()

    monkeypatch.setattr(GUIDE, "agent_guide", endless)

    with anyio.fail_after(60):  # an endless stream nobody stops never answers
        async with connected(app) as client:
            result = await client.call_tool("commands_guide", {})

    document = error_of(result)
    assert document["code"] == "validation_error"
    assert document["details"] == {"maximum_bytes": STREAM_LIMIT}
    assert produced["lines"] < 2 * STREAM_LIMIT // 1024


# --------------------------------------------------------------------------
# Transport security and the switch
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("allowed", "host", "status"),
    [
        (None, HOST, 200),
        (None, "dane.example.pl", 421),
        (["dane.example.pl"], "dane.example.pl:443", 200),
    ],
)
async def test_mcp_answers_only_the_allowed_hosts(allowed, host, status, monkeypatch):
    if allowed is not None:
        monkeypatch.setattr(settings, "mcp_allowed_hosts", allowed)
    app = enabled(monkeypatch)

    async with app.router.lifespan_context(app):
        answered = await post_initialize(app, host)
        browser = await post_initialize(app, host, Origin="https://example.org")

    assert answered.status_code == status
    if status == 200:
        assert browser.status_code == 403  # browser clients are not served


def test_without_imgw_mcp_enabled_mcp_is_an_unknown_route(monkeypatch):
    app = reimported(monkeypatch).app

    with TestClient(app) as client:
        response = client.post("/mcp", json=INITIALIZE)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


def test_without_the_mcp_extra_an_enabled_mcp_is_an_unknown_route_and_a_warning(
    monkeypatch, caplog
):
    monkeypatch.setitem(sys.modules, "mcp", None)  # the extra is not installed
    for name in [name for name in sys.modules if name.startswith("imgwtools.mcp.")]:
        monkeypatch.delitem(sys.modules, name)

    with caplog.at_level(logging.WARNING, logger="imgwtools.api.main"):
        app = enabled(monkeypatch)
    with TestClient(app) as client:
        response = client.post("/mcp", json=INITIALIZE)

    assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert "pip install imgwtools[mcp]" in caplog.text


def test_an_enabled_mcp_refuses_imgw_lang_outside_pl_and_en(monkeypatch):
    with pytest.raises(IMGWValidationError) as caught:
        enabled(monkeypatch, lang="de")

    assert caught.value.details == {
        "option": "IMGW_LANG",
        "value": "de",
        "allowed": ["pl", "en"],
    }
