"""Contract of MCP over HTTP: a ``/mcp`` tool answers what its REST route answers.

Spec 2026-10-19 §6.9 and §9 ("MCP stdio i HTTP"). The REST application of a server
with ``IMGW_MCP_ENABLED=true`` serves ``/mcp``; every case of
``test_interface_contract.CASES`` runs through REST (the FastAPI test client) and
through its tool on ``/mcp`` (the SDK client in process, ASGI). The structured
content is the REST body and the text content its text; a stream is its text with
the envelope of ``X-IMGW-Status`` and ``X-IMGW-Notices``; a POST route answers its
plan of ``?check=true`` (a server without writes) and leaves the store as it was.
Both send the same requests to the recorded sources. Every error scenario of the
REST contract gives the problem document of REST as the error result of the tool:
the same code, title, detail and details.
"""

import json

import pytest

pytest.importorskip("mcp")

from imgwtools import command_schema
from tests.contract.support import rest_request, stamps
from tests.contract.test_interface_contract import (
    CASES,
    ROUTES,
    SCENARIOS,
    Setting,
    fresh_store,
    recorded,  # noqa: F401 (fixture)
    relative_data_dir,  # noqa: F401 (fixture)
    resolved,
    served_root,  # noqa: F401 (fixture)
)
from tests.unit.test_mcp_http import connected, enabled

# Default page of a list tool (spec 2026-10-19 §6.4 p. 5).
PAGE = 50


def rest_answer(rest, command: str, options: dict[str, object]):
    """The REST answer the tool forwards: a POST route only plans (``?check=true``)."""
    request = rest_request(command, options)
    if request["method"] == "POST":
        request["url"] += "?check=true"
    return rest.request(**request)


def assert_same(answered, result, command: str, options: dict[str, object]) -> None:
    """The tool result is the REST answer (spec §6.6, §6.7, §6.9)."""
    media = answered.headers["content-type"]
    if media == "application/problem+json":
        body = answered.json()
        assert result.is_error is True
        assert result.structured_content == {
            key: body[key] for key in ("code", "title", "detail", "details")
        }
        return
    assert answered.status_code == 200, answered.text
    assert result.is_error is False, result.content[0].text
    if media == "application/json":
        assert result.structured_content == answered.json()
        assert result.content[0].text == answered.text
        return
    data = answered.content
    default = command_schema(command)["properties"]["format"]["default"]
    assert result.content[0].text == data.decode("utf-8")
    assert result.structured_content == {
        "schema": "imgw-result/1",
        "command": command,
        "check": False,
        "status": answered.headers["x-imgw-status"],
        "result": {
            "format": options.get("format", default),
            "bytes": len(data),
            "lines": data.count(b"\n"),
        },
        "notices": json.loads(answered.headers["x-imgw-notices"]),
    }


@pytest.mark.parametrize("command", list(ROUTES))
async def test_every_rest_case_is_the_answer_of_its_mcp_tool(
    command,
    rest,
    server,
    monkeypatch,
    tmp_path,
    fixture_root,
    served_root,  # noqa: F811
    recorded,  # noqa: F811
    frozen,
    relative_data_dir,  # noqa: F811
):
    app = enabled(monkeypatch)
    tool = ROUTES[command]["operation_id"]
    async with connected(app) as client:
        for case in CASES[command]:
            writes = case.store in ("empty", "fixture")
            if writes:
                root = tmp_path / "store"
            else:
                root = served_root if case.store == "served" else None
            monkeypatch.setattr(server, "store_root", root)
            options = case.options if writes else resolved(case.options, root)
            paged = dict(options)
            if ROUTES[command]["result"] == "list" and "limit" not in options:
                paged["limit"] = PAGE  # the page a tool takes without limit
            answers, requests = {}, {}
            for interface in ("rest", "mcp"):
                if writes:
                    fresh_store(case.store, root, fixture_root)
                before = None if root is None else stamps(root)
                start = len(recorded.router.calls)
                if interface == "rest":
                    answers[interface] = rest_answer(rest, command, paged)
                else:
                    answers[interface] = await client.call_tool(tool, options)
                requests[interface] = recorded.traffic(start)
                if root is not None:  # reads and plans leave the store as it was
                    assert stamps(root) == before

            assert_same(answers["rest"], answers["mcp"], command, options)
            assert requests["mcp"] == requests["rest"]


@pytest.mark.parametrize(
    "code", [code for code in SCENARIOS if code != "method_not_allowed"]
)
async def test_every_error_scenario_of_rest_is_the_answer_of_the_mcp_tool(
    code, rest, server, monkeypatch, tmp_path, fixture_root, imgw, frozen
):
    app = enabled(monkeypatch)  # before the scenario: it may break the registry
    scenario = SCENARIOS[code](Setting(tmp_path, fixture_root, imgw, monkeypatch))
    monkeypatch.setattr(server, "store_root", scenario.root)
    tool = ROUTES[scenario.command]["operation_id"]

    answered = rest_answer(rest, scenario.command, scenario.options)
    async with connected(app) as client:
        result = await client.call_tool(tool, scenario.options)

    assert_same(answered, result, scenario.command, scenario.options)
    if ROUTES[scenario.command]["rest"]["method"] == "GET":
        assert answered.json()["code"] == code  # an error, not a plan
