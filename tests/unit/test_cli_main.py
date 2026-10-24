"""Top-level ``imgw`` commands: version, server, mcp and the console entry point."""

import json
import sys

import pytest
from typer.testing import CliRunner

import imgwtools
from imgwtools.cli import main as cli_main

RUNNER = CliRunner()


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "uvicorn.run", lambda app, **kwargs: calls.append((app, kwargs))
    )
    return calls


def test_cli_main_version_prints_package_version():
    result = RUNNER.invoke(cli_main.app, ["version"])

    assert result.exit_code == 0, result.output
    assert f"IMGWTools v{imgwtools.__version__}" in result.output


def test_cli_main_server_defaults_start_api_on_all_interfaces(uvicorn_calls):
    result = RUNNER.invoke(cli_main.app, ["server"])

    assert result.exit_code == 0, result.output
    assert "Uruchamiam serwer na 0.0.0.0:8000" in result.output
    assert uvicorn_calls == [
        (
            "imgwtools.api.main:app",
            {"host": "0.0.0.0", "port": 8000, "reload": False},
        )
    ]


def test_cli_main_server_options_reach_uvicorn(uvicorn_calls):
    result = RUNNER.invoke(
        cli_main.app,
        ["server", "--host", "127.0.0.1", "--port", "9123", "--reload"],
    )

    assert result.exit_code == 0, result.output
    assert "Uruchamiam serwer na 127.0.0.1:9123" in result.output
    assert uvicorn_calls == [
        (
            "imgwtools.api.main:app",
            {"host": "127.0.0.1", "port": 9123, "reload": True},
        )
    ]


def test_cli_main_server_rejects_non_numeric_port_with_the_json_error_line(
    uvicorn_calls,
):
    result = RUNNER.invoke(cli_main.app, ["server", "--port", "osiem"])

    assert result.exit_code == 2
    assert result.stdout == ""
    error = json.loads(result.stderr.splitlines()[-1])
    assert (error["code"], error["details"]["option"]) == ("validation_error", "port")
    assert error["detail"].startswith("Invalid value of the option --port")
    assert uvicorn_calls == []


def test_cli_main_mcp_without_the_extra_ends_with_missing_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "mcp", None)  # imgwtools[mcp] is not installed
    for name in [name for name in sys.modules if name.startswith("imgwtools.mcp.")]:
        monkeypatch.delitem(sys.modules, name)

    result = RUNNER.invoke(cli_main.app, ["mcp"])

    assert result.exit_code == 6
    assert result.stdout == ""
    error = json.loads(result.stderr.splitlines()[-1])
    assert (error["code"], error["details"]) == ("missing_dependency", {})
    assert "pip install imgwtools[mcp]" in error["detail"]


def test_cli_main_entry_point_runs_command_from_argv(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["imgw", "version"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 0
    assert imgwtools.__version__ in capsys.readouterr().out


def test_cli_main_entry_point_unknown_command_ends_with_the_json_error_line(
    monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["imgw", "nieistniejaca-komenda"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err.splitlines()[-1])
    assert error["code"] == "validation_error"
    assert "version" in error["details"]["allowed"]
