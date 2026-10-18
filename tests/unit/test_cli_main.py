"""Top-level ``imgw`` commands: version, server and the console entry point."""

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


def test_cli_main_server_rejects_non_numeric_port(uvicorn_calls):
    result = RUNNER.invoke(cli_main.app, ["server", "--port", "osiem"])

    assert result.exit_code == 2
    assert uvicorn_calls == []


def test_cli_main_entry_point_runs_command_from_argv(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["imgw", "version"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 0
    assert imgwtools.__version__ in capsys.readouterr().out


def test_cli_main_entry_point_unknown_command_exits_with_usage_error(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["imgw", "nieistniejaca-komenda"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 2
