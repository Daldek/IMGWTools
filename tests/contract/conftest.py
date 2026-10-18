"""Fixtures of the offline contract suite: no network, frozen clock, recorded IMGW."""

import importlib
import socket
from datetime import UTC, datetime

import pytest
import respx

from imgwtools.testing import build_fixture_store
from tests.contract.support import FakeImgw

FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
# Modules that stamp versions, plans and pins with the current time.
_CLOCKED = (
    "imgwtools.store.writer",
    "imgwtools.store.series",
    "imgwtools.store.catalog",
    "imgwtools.store.sync",
    "imgwtools.store.pmaxtp",
    "imgwtools.commands",
    "imgwtools.project",
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real connection fails the test; recorded answers come through respx."""

    def refuse(*args, **kwargs):
        raise AssertionError("połączenie sieciowe w teście kontraktu offline")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def frozen(monkeypatch):
    """Freeze the clock of every module that stamps versions, plans and pins."""

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
