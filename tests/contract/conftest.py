"""Fixtures of the offline contract suite: no network, frozen clock, recorded IMGW.

The three interfaces run in this process: Python through ``run_command``, the
``imgw`` CLI through Click's runner and REST through the FastAPI test client.
"""

import importlib
import socket
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from typer.testing import CliRunner, Result

from imgwtools.api.main import app as rest_app
from imgwtools.cli.main import app as cli_app
from imgwtools.config import settings
from imgwtools.testing import build_fixture_store
from tests.contract.support import FakeImgw

FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
WRITE_TOKEN = "kontrakt-token"
# Modules that stamp versions and plans with the current time.
_CLOCKED = (
    "imgwtools.store.writer",
    "imgwtools.store.series",
    "imgwtools.store.catalog",
    "imgwtools.store.sync",
    "imgwtools.store.pmaxtp",
    "imgwtools.commands",
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real connection fails the test; recorded answers come through respx."""

    def refuse(*args, **kwargs):
        raise AssertionError("połączenie sieciowe w teście kontraktu offline")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def no_imgw_root(monkeypatch):
    """The developer's IMGW_ROOT must not reach the commands under test."""
    monkeypatch.delenv("IMGW_ROOT", raising=False)


@pytest.fixture
def frozen(monkeypatch):
    """Freeze the clock of every module that stamps versions and plans."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in _CLOCKED:
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)
    return FROZEN_AT


@pytest.fixture
def imgw():
    """Recorded IMGW server; unpublished URLs are refused by respx."""
    with respx.mock(assert_all_called=False) as router:
        yield FakeImgw(router)


@pytest.fixture(scope="session")
def fixture_root(tmp_path_factory):
    """``complete`` store of ``imgwtools.testing`` built once; tests copy it to mutate."""
    return build_fixture_store(tmp_path_factory.mktemp("contract") / "store").root


@pytest.fixture
def server(monkeypatch):
    """REST server settings: no store root, writes disabled, default page size."""
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
def writable(server, monkeypatch):
    """Store writes enabled on the server; the headers carry the write token."""
    monkeypatch.setattr(server, "store_writes_enabled", True)
    monkeypatch.setattr(server, "store_write_token", SecretStr(WRITE_TOKEN))
    return {"X-API-Key": WRITE_TOKEN}


@pytest.fixture
def rest(server):
    """REST API in process; server errors are answered, not re-raised."""
    return TestClient(rest_app, raise_server_exceptions=False)


@pytest.fixture
def cli() -> Callable[..., Result]:
    """``imgw`` in process: the Click result of the given arguments."""
    runner = CliRunner()

    def invoke(*args: object) -> Result:
        return runner.invoke(cli_app, [str(arg) for arg in args])

    return invoke
