"""``imgw mcp``: the MCP server over stdio in its own process (spec 2026-10-19 §6.2, §9).

The SDK client starts the installed ``imgw mcp`` the way a client configuration
does (``"command": "imgw", "args": ["mcp"]``) and talks to it over stdin and
stdout. Flags and environment variables choose the mode (IMGW_LANG is ignored: the
server speaks English): the process lists the tools of the in-memory server of that
mode and answers a call with the envelope of Python.
"""

import json
import os
import subprocess
import sys
import threading
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from typer.testing import CliRunner

from imgwtools import run_command
from imgwtools.cli import main as cli_main
from imgwtools.config import settings
from imgwtools.mcp.server import create_server
from tests.contract.support import imgw_executable

RUNNER = CliRunner()


@pytest.fixture(autouse=True)
def no_imgw_root(monkeypatch):
    """The in-memory servers have no store and the default page, like the process."""
    monkeypatch.delenv("IMGW_ROOT", raising=False)
    monkeypatch.setattr(settings, "api_max_limit", 1000)


def dumped(tools) -> list[dict[str, Any]]:
    return [
        tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in tools
    ]


@pytest.mark.parametrize(
    ("args", "env", "mode"),
    [
        pytest.param([], {}, "read", id="default"),
        pytest.param(["--allow-writes"], {}, "write", id="flags"),
        pytest.param([], {"IMGW_MCP_ALLOW_WRITES": "true"}, "write", id="environment"),
        pytest.param([], {"IMGW_LANG": "pl"}, "read", id="polish-setting-ignored"),
    ],
)
async def test_imgw_mcp_serves_the_english_tools_of_its_mode_over_stdio(
    args, env, mode, tmp_path
):
    async with Client(create_server(mode=mode)) as memory:
        expected = (await memory.list_tools()).tools
    command, *prefix = imgw_executable()
    server = StdioServerParameters(
        command=command, args=[*prefix, "mcp", *args], env=env, cwd=tmp_path
    )
    options = {"kind": "hydro", "limit": 1}

    with (tmp_path / "stderr.log").open("w+", encoding="utf-8") as log:
        async with Client(stdio_client(server, errlog=log)) as client:
            tools = (await client.list_tools()).tools
            answered = await client.call_tool("imgw_datasets_list", options)

    assert dumped(tools) == dumped(expected)
    sync = {tool.name: tool for tool in tools}["imgw_store_sync"]
    check = sync.input_schema["properties"]["check"]
    assert check["default"] is True  # a writing command plans unless check: false
    assert ("const" in check) is (mode == "read")
    envelope = run_command("datasets list", options=options).to_json()
    assert answered.is_error is False
    assert answered.structured_content == envelope
    assert answered.content[0].text == json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":")
    )


def test_imgw_mcp_ends_cleanly_without_a_byte_on_stdout_when_stdin_closes(tmp_path):
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("IMGW_")
    }

    finished = subprocess.run(
        [*imgw_executable(), "mcp"],
        input=b"",
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=120,
        check=False,
    )

    assert (finished.returncode, finished.stdout) == (0, b""), finished.stderr


NOISY_SERVER = """\
import os
import sys

import imgwtools.mcp._calls as calls
from imgwtools.cli.main import app

run_command = calls.run_command


def noisy(*args, **kwargs):
    print("STRAY PRINT")
    os.write(1, b"STRAY WRITE\\n")
    return run_command(*args, **kwargs)


calls.run_command = noisy
sys.argv = ["imgw", "mcp"]
app()
"""


def test_imgw_mcp_sends_stray_output_of_a_command_to_stderr_never_to_the_client(
    tmp_path,
):
    """A ``print`` or a write to descriptor 1 in a command adds no line to the
    protocol stream, neither while the server serves nor when it shuts down."""
    script = tmp_path / "noisy_server.py"
    script.write_text(NOISY_SERVER, encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        # clients start servers without PYTHONUNBUFFERED: stdout is block-buffered
        if not key.startswith("IMGW_") and key != "PYTHONUNBUFFERED"
    }
    process = subprocess.Popen(
        [sys.executable, str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
    )
    watchdog = threading.Timer(120, process.kill)
    watchdog.start()

    def send(message: dict[str, Any]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    try:
        assert process.stdout is not None
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            }
        )
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "imgw_datasets_list",
                    "arguments": {"kind": "hydro", "limit": 1},
                },
            }
        )
        frames = []
        for line in process.stdout:  # until the answer to the call: stdin stays open
            frames.append(json.loads(line))
            if frames[-1].get("id") == 2:
                break
        rest, errors = process.communicate(timeout=120)  # closes stdin: shutdown
    finally:
        watchdog.cancel()
        process.kill()

    assert [frame["id"] for frame in frames if "id" in frame] == [1, 2], errors
    assert frames[-1]["result"]["isError"] is False
    assert rest == ""
    assert "STRAY PRINT" in errors and "STRAY WRITE" in errors
    assert process.returncode == 0


def test_imgw_mcp_has_no_language_option():
    result = RUNNER.invoke(cli_main.app, ["mcp", "--lang", "en"])

    assert result.exit_code == 2
    assert result.stdout == ""
    error = json.loads(result.stderr.splitlines()[-1])
    assert error["code"] == "validation_error"
    assert "--lang" in error["detail"]
