"""Public offline fixture store builder (imgwtools.testing)."""

import hashlib
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from imgwtools.exceptions import IMGWStoreError, IMGWValidationError
from imgwtools.store import catalog, check_series, series, writer
from imgwtools.testing import build_fixture_store, fixture_files

TESTS_FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
HYDRO_SLOT = "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("połączenie sieciowe w teście offline")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def sidecars(root: Path, slot: str, name: str) -> dict[str, dict]:
    return {
        directory.name: json.loads(
            (directory / f"{name}.meta.json").read_text(encoding="utf-8")
        )
        for directory in sorted((root / slot).iterdir())
    }


def tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_complete_store_holds_recorded_versions_series_and_catalog(tmp_path):
    handle = build_fixture_store(tmp_path / "store")
    root = handle.root
    assert handle.schema == "imgw-store/1"

    hydro = sidecars(root, HYDRO_SLOT, "codz_2024.zip")
    assert [
        (meta["extra"]["http"]["etag"], meta["extra"]["version"]["label"])
        for meta in hydro.values()
    ] == [
        ('"hydro-v1"', "2026-10-17"),
        ('"hydro-v2"', "2026-10-18"),
        ('"hydro-v3"', "2026-10-19"),
    ]
    old, relabeled, newer = hydro.values()
    assert old["sha256"] == relabeled["sha256"] != newer["sha256"]
    assert (
        newer["sha256"]
        == hashlib.sha256(
            fixture_files().joinpath("variants", "codz_2024_changed.zip").read_bytes()
        ).hexdigest()
    )

    hydro_series = sidecars(root, "series/versions/hydro_daily", "series.json")
    inputs = [
        {source["sha256"] for source in meta["extra"]["source_files"]}
        for meta in hydro_series.values()
    ]
    assert inputs == [{old["sha256"]}, {newer["sha256"]}]
    assert check_series(handle, dataset="pl.imgw.hydro_daily").series_state == {
        "hydro_daily": "current"
    }
    assert check_series(handle, dataset="pl.imgw.meteo_precip_daily").series_state == {
        "meteo_precip_daily": "outdated"
    }

    (geojson,) = (root / "stations" / "versions").glob("*/stations.geojson")
    features = {
        f["properties"]["station_code"]: f
        for f in json.loads(geojson.read_text(encoding="utf-8"))["features"]
    }
    assert features["149190312"]["geometry"] is None
    assert features["149190310"]["geometry"] is not None
    lists = [
        meta["extra"]["http"]["etag"]
        for meta in (
            *sidecars(
                root,
                "archives/versions/dane_hydrologiczne/lista_stacji_hydro",
                "lista_stacji_hydro.csv",
            ).values(),
            *sidecars(
                root,
                "archives/versions/dane_meteorologiczne/wykaz_stacji",
                "wykaz_stacji.csv",
            ).values(),
        )
    ]
    assert lists == ['"hydro-list-v1"', '"meteo-list-v1"']


def test_fresh_builds_are_identical_under_frozen_clock(tmp_path, monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 9, 0, tzinfo=UTC).astimezone(tz)

    for module in (writer, series, catalog):
        monkeypatch.setattr(module, "datetime", Frozen)
    first = tree(build_fixture_store(tmp_path / "a").root)
    second = tree(build_fixture_store(tmp_path / "b").root)
    assert first == second
    assert (
        sum(name.endswith(".meta.json") for name in first) == 11
    )  # 7 archives, 3 series, catalog


def test_local_reference_data_does_not_leak_into_fixture_catalog(
    tmp_path, isolated_data_dir
):
    static = isolated_data_dir / "hydro_stations_locations.csv"
    static.write_text(
        "station_code,latitude,longitude\n149190312,50.0512,19.9512\n",
        encoding="utf-8",
    )
    root = build_fixture_store(tmp_path / "store").root
    (geojson,) = (root / "stations" / "versions").glob("*/stations.geojson")
    features = {
        f["id"]: f for f in json.loads(geojson.read_text(encoding="utf-8"))["features"]
    }
    assert features["149190312"]["geometry"] is None
    meta = json.loads(
        geojson.with_name("stations.geojson.meta.json").read_text(encoding="utf-8")
    )
    (static_source,) = [
        entry for entry in meta["extra"]["catalog"] if entry["source"] == "static"
    ]
    assert static_source["available"] is False and static_source["sha256"] is None


def test_corrupt_variant_truncates_old_archive_sidecar(tmp_path):
    handle = build_fixture_store(tmp_path / "store", variant="corrupt")
    broken = (
        handle.root / HYDRO_SLOT / "2026-10-17_688646cd" / "codz_2024.zip.meta.json"
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(broken.read_text(encoding="utf-8"))
    plan = check_series(handle, dataset="pl.imgw.hydro_daily")
    assert plan.series_state == {"hydro_daily": "outdated"}
    assert any(
        action.status == "check_failed" and "2026-10-17_688646cd" in action.detail
        for action in plan.actions
    )


def test_unknown_schema_variant_adds_unparsed_series_version(tmp_path):
    handle = build_fixture_store(tmp_path / "store", variant="unknown_schema")
    (unknown,) = (handle.root / "series/versions/hydro_daily").glob("2026-10-20_*")
    meta = json.loads((unknown / "series.json.meta.json").read_text(encoding="utf-8"))
    assert meta["schema"] == "imgw-meta/2"
    assert (
        json.loads((unknown / "series.json").read_text(encoding="utf-8"))["schema"]
        == "imgw-series/2"
    )
    assert (
        meta["sha256"]
        == hashlib.sha256((unknown / "series.json").read_bytes()).hexdigest()
    )
    assert check_series(handle, dataset="pl.imgw.hydro_daily").series_state == {
        "hydro_daily": "current"
    }


def test_rejects_unknown_variant_and_non_empty_root(tmp_path):
    with pytest.raises(IMGWValidationError, match="wariant"):
        build_fixture_store(tmp_path / "x", variant="partial")  # type: ignore[arg-type]
    assert not (tmp_path / "x").exists()
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "file.txt").write_text("x")
    with pytest.raises(IMGWStoreError, match="pustego"):
        build_fixture_store(tmp_path / "busy")


def test_packaged_fixtures_match_test_fixture_tree():
    packaged = fixture_files()

    def walk(node, prefix=""):
        for child in node.iterdir():
            if child.is_dir():
                yield from walk(child, f"{prefix}{child.name}/")
            else:
                yield f"{prefix}{child.name}", child.read_bytes()

    shipped = dict(walk(packaged))
    local = {
        path.relative_to(TESTS_FIXTURES).as_posix(): path.read_bytes()
        for path in TESTS_FIXTURES.rglob("*")
        if path.is_file()
    }
    assert shipped == local
