"""build_fixture_store(variant="complete_pl_cz"): the IMGW-PIB fixture plus ČHMÚ.

Spec 2026-10-18 §13.3: ČHMÚ archives in versions (first, ``relabeled``,
corrected), a slot with the observation of scenario (8), the series of both
ČHMÚ datasets and the ČHMÚ catalog, built offline from
``chmi_builder_recordings.json``. Synthetic files, fictional station codes.
"""

import hashlib
import json
import socket
from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import pytest

from imgwtools.store import (
    catalog,
    check_series,
    current_version,
    iter_store,
    read_catalog,
    series,
    writer,
)
from imgwtools.testing import build_fixture_store, fixture_files

DAILY = "archives/versions/hydrology/historical/data/daily"
HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
RESERIALIZED = "variants/H_0-203-1-900001_DQ_2023_reserialized.json"


def refuse(*args, **kwargs):
    raise AssertionError("połączenie sieciowe w teście offline")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", refuse)
        patch.setattr(socket, "create_connection", refuse)
        return build_fixture_store(
            tmp_path_factory.mktemp("pl_cz") / "store", variant="complete_pl_cz"
        ).root


def sidecars(root, slot, name):
    return {
        directory.name: json.loads(
            (directory / f"{name}.meta.json").read_text(encoding="utf-8")
        )
        for directory in sorted((root / slot).iterdir())
        if directory.name != "observations"
    }


def tree(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_chmi_archives_keep_the_versions_of_each_scenario(store):
    republished = sidecars(
        store, f"{DAILY}/H_0-203-1-900002_DQ_2004", "H_0-203-1-900002_DQ_2004.json"
    )
    first, relabeled = republished.values()
    assert first["sha256"] == relabeled["sha256"]
    assert [meta["extra"]["version"]["label"] for meta in republished.values()] == [
        "2025-07-01",
        "2026-02-06",
    ]
    corrected = sidecars(
        store, f"{DAILY}/H_0-203-1-900001_DQ_2024", "H_0-203-1-900001_DQ_2024.json"
    )
    old, new = corrected.values()
    assert old["content_sha256"] != new["content_sha256"]
    assert new["extra"]["http"]["etag"] == '"6a0eea27-554e"'
    assert {meta["content_form"] for meta in (*republished.values(), old, new)} == {
        "chmi-json/1"
    }
    (rain,) = sidecars(
        store,
        "archives/versions/meteorology/climate/historical_csv/data/daily/precipitation/"
        "dly-0-203-0-90000000002-SRA",
        "dly-0-203-0-90000000002-SRA.csv",
    ).values()
    assert "content_sha256" not in rain and rain["provider"] == "CHMI"


def test_reserialized_file_is_one_observation_beside_its_only_version(store):
    slot = f"{DAILY}/H_0-203-1-900001_DQ_2023"
    ((version, meta),) = sidecars(store, slot, "H_0-203-1-900001_DQ_2023.json").items()
    (observation,) = (store / slot / "observations").iterdir()
    seen = json.loads(observation.read_text(encoding="utf-8"))
    reserialized = fixture_files().joinpath(*RESERIALIZED.split("/")).read_bytes()

    assert seen["same_content_as"] == version
    assert seen["sha256"] == hashlib.sha256(reserialized).hexdigest() != meta["sha256"]
    assert (seen["content_sha256"], seen["content_form"]) == (
        meta["content_sha256"],
        meta["content_form"],
    )
    assert seen["last_modified"] == "Mon, 19 Oct 2026 03:12:44 GMT"
    entry = current_version(
        store, slot=f"archive:{HYDRO}:H_0-203-1-900001_DQ_2023.json"
    )
    assert entry is not None and entry.version is not None
    assert entry.version.parent.name == version


def test_chmi_series_and_catalog_are_current_and_the_scan_is_clean(store):
    assert check_series(store, dataset=HYDRO).series_state == {
        "chmi_hydro_daily": "current"
    }
    assert check_series(store, dataset=METEO).series_state == {
        "chmi_meteo_daily": "current"
    }
    hydro_series = sidecars(store, "series/versions/chmi_hydro_daily", "series.json")
    assert len(hydro_series) == 2  # before and after the correction of 900001 2024
    current = max(hydro_series.values(), key=lambda meta: meta["downloaded_at"])
    inputs = {source["name"]: source for source in current["extra"]["source_files"]}
    assert (
        inputs["H_0-203-1-900001_DQ_2024.json"]["file"]
        .split("/")[-2]
        .startswith("2026-05-21_")
    )
    assert all("content_sha256" in source for source in inputs.values())

    stations = {
        feature.station_code for feature in read_catalog(root=store, provider="CHMI")
    }
    assert {"0-203-1-900001", "0-203-1-900002", "0-203-0-90001"} <= stations
    assert {feature.provider for feature in read_catalog(root=store)} == {
        "IMGW-PIB",
        "CHMI",
    }
    entries = list(iter_store(store))
    assert [entry.problem for entry in entries if entry.kind == "problem"] == []
    assert Counter(
        (entry.kind, entry.provider) for entry in entries if entry.provider == "CHMI"
    ) == {
        ("archive", "CHMI"): 14,
        ("observation", "CHMI"): 1,
        ("series", "CHMI"): 3,
        ("catalog", "CHMI"): 1,
    }


def test_imgw_part_equals_the_complete_fixture_and_builds_are_identical(
    tmp_path, monkeypatch
):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 9, 0, tzinfo=UTC).astimezone(tz)

    for module in (writer, series, catalog):
        monkeypatch.setattr(module, "datetime", Frozen)
    complete = tree(build_fixture_store(tmp_path / "complete").root)
    first = tree(build_fixture_store(tmp_path / "a", variant="complete_pl_cz").root)
    second = tree(build_fixture_store(tmp_path / "b", variant="complete_pl_cz").root)

    assert first == second
    assert {name: first[name] for name in complete} == complete
    chmi = (
        "archives/versions/hydrology/",
        "archives/versions/meteorology/",
        "series/versions/chmi_",
        "stations/versions/chmi_stations/",
    )
    assert all(name.startswith(chmi) for name in set(first) - set(complete))


def test_builder_recordings_follow_the_nginx_signals_of_the_source():
    """ETag = "<hex mtime>-<hex size>" of Last-Modified and Content-Length (§13.1)."""
    document = json.loads(
        fixture_files().joinpath("chmi_builder_recordings.json").read_text("utf-8")
    )
    signals = [
        entry for entry in document["interactions"] if "ETag" in entry["headers"]
    ]
    assert signals
    for entry in signals:
        headers = entry["headers"]
        moment = int(parsedate_to_datetime(headers["Last-Modified"]).timestamp())
        size = int(headers["Content-Length"])
        assert headers["ETag"] == f'"{moment:x}-{size:x}"', entry["case"]
        if entry["method"] == "GET":
            relative = entry.get("variant") or f"archives/{entry['archive']}"
            assert len(fixture_files().joinpath(*relative.split("/")).read_bytes()) == (
                size
            ), entry["case"]
