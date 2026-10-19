"""Offline reading of stores holding IMGW-PIB and ČHMÚ data (spec 2026-10-18 §3, §7, §9)."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import respx

from imgwtools.datasets import archive_files, providers
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.fetch import DownloadResult
from imgwtools.parsers import (
    parse_chmi_hydro_daily,
    parse_chmi_meteo_daily,
    parse_chmi_stations,
)
from imgwtools.store import (
    current_version,
    init_store,
    iter_store,
    read_archive,
    read_catalog,
    read_station_list,
    store_info,
    write_archive,
)
from imgwtools.store.catalog import build_catalog
from imgwtools.testing import build_fixture_store
from tests.unit.test_store_catalog import mock_sources
from tests.unit.test_store_catalog_chmi import (
    ARCHIVES,
    CODES,
    LIST_SLOT,
    REGENERATED,
    body,
    build,
    serve,
)
from tests.unit.test_store_reader import DAILY, store_archives

(HYDRO_2023,) = archive_files(
    "cz.chmi.hydro_daily", stations=["0-203-1-900001"], years=[2023]
)
SRA = archive_files("cz.chmi.meteo_daily", stations=["0-203-0-90001"])[0]


def write_chmi(root, archive):
    data = (ARCHIVES / archive.server_path).read_bytes()
    response = DownloadResult(
        data, archive.url, '"v1"', "Tue, 01 Jul 2025 12:07:21 GMT", len(data)
    )
    return write_archive(root, archive=archive, response=response)


def imgw_catalog(root):
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router)
        return build_catalog(root)


def observe_regenerated_list(root):
    """Scenario 7: the regenerated historical meta1 is observed, not stored."""
    with respx.mock(assert_all_called=False) as router:
        serve(router, *REGENERATED)
        return build_catalog(root, provider="CHMI")


def test_store_info_lists_the_providers_of_the_registry(tmp_path):
    root = init_store(tmp_path / "store").root
    for path in (root, tmp_path / "brak"):
        info = store_info(path)
        assert info.providers == providers()
        assert [provider.id for provider in info.providers] == ["IMGW-PIB", "CHMI"]


def test_scan_names_the_provider_of_each_entry_and_filters_by_provider(tmp_path):
    root = init_store(tmp_path / "store").root
    store_archives(root, DAILY, [2024])
    imgw_catalog(root)
    build(root)
    observe_regenerated_list(root)
    hydro = write_chmi(root, HYDRO_2023)
    write_chmi(root, SRA)
    (hydro.path.parent / "notatka.txt").write_text("x", encoding="utf-8")
    (root / "obce").mkdir()

    entries = list(iter_store(root))
    for entry in entries:
        expected = None
        if entry.slot is not None:
            expected = "CHMI" if ":cz.chmi." in entry.slot else "IMGW-PIB"
        assert entry.provider == expected, entry
    chmi = list(iter_store(root, provider="CHMI"))
    assert chmi == [entry for entry in entries if entry.provider in ("CHMI", None)]
    assert list(iter_store(root, provider="cz.chmi")) == chmi
    assert [(entry.kind, entry.slot) for entry in chmi if entry.kind != "archive"] == [
        ("problem", "archive:cz.chmi.hydro_daily:H_0-203-1-900001_DQ_2023.json"),
        ("observation", "archive:cz.chmi.hydro_stations:meta1.json"),
        ("problem", None),
        ("catalog", "catalog:cz.chmi.stations"),
    ]
    imgw = list(iter_store(root, provider="IMGW-PIB"))
    assert {entry.provider for entry in imgw} == {"IMGW-PIB", None}
    assert [entry.slot for entry in imgw if entry.kind == "problem"] == [None]
    assert [(e.slot, e.provider) for e in iter_store(root, kind="catalog")] == [
        ("catalog:pl.imgw.stations", "IMGW-PIB"),
        ("catalog:cz.chmi.stations", "CHMI"),
    ]
    with pytest.raises(IMGWValidationError) as error:
        iter_store(root, provider="SHMU")
    assert error.value.details["allowed"] == ["IMGW-PIB", "CHMI"]


def test_provider_catalogs_lie_in_named_directories_of_the_catalog_slot(tmp_path):
    root = init_store(tmp_path / "store").root
    imgw_catalog(root)
    build(root)
    imgw = current_version(root, slot="catalog:pl.imgw.stations")
    chmi = current_version(root, slot="catalog:cz.chmi.stations")
    assert imgw is not None and chmi is not None
    assert imgw.version.parent.parent == root / "stations/versions"
    assert chmi.version.parent.parent == root / "stations/versions/chmi_stations"
    assert (imgw.provider, chmi.provider) == ("IMGW-PIB", "CHMI")
    assert (chmi.meta.dataset_key, chmi.meta.provider) == ("cz.chmi.stations", "CHMI")
    with pytest.raises(IMGWValidationError, match="cz.chmi.stations"):
        current_version(root, slot="catalog:sk.shmu.stations")

    nested = root / "stations/versions/chmi_stations"
    misplaced = nested / imgw.version.parent.name
    shutil.copytree(imgw.version.parent, misplaced)
    (nested / "observations").mkdir()
    (root / "stations/versions/obce").mkdir()
    problems = [
        (entry.slot, entry.version.relative_to(root).as_posix(), entry.problem_code)
        for entry in iter_store(root, kind="problem")
    ]
    assert problems == [
        (
            "catalog:cz.chmi.stations",
            misplaced.relative_to(root).as_posix(),
            "invalid_meta",
        ),
        (None, "stations/versions/chmi_stations/observations", "unknown_entry"),
        (None, "stations/versions/obce", "unknown_entry"),
    ]
    (root / "stations/versions/obce").rmdir()
    # Broken versions of a nested catalog never touch the IMGW-PIB catalog slot.
    assert current_version(root, slot="catalog:pl.imgw.stations") == imgw
    with pytest.raises(IMGWDataError, match="catalog:cz.chmi.stations"):
        current_version(root, slot="catalog:cz.chmi.stations")


def test_read_catalog_reads_a_version_or_the_current_catalog_of_each_provider(
    tmp_path,
):
    root = init_store(tmp_path / "store").root
    build(root)
    chmi = read_catalog(root=root)
    assert [station.station_code for station in chmi] == CODES
    assert {station.provider for station in chmi} == {"CHMI"}
    thresholds = {station.station_code: station.properties for station in chmi}
    assert thresholds["0-203-1-900001"]["thresholds"]["source"] == "chmi_hydro_now"
    assert "thresholds" not in thresholds["0-203-0-90001"]
    with pytest.raises(IMGWStoreError) as missing:
        read_catalog(root=root, provider="IMGW-PIB")
    assert missing.value.code == "not_found"

    imgw = imgw_catalog(root)
    both = read_catalog(root=root)
    assert [station.provider for station in both] == [
        "IMGW-PIB"
    ] * imgw.station_count + ["CHMI"] * len(CODES)
    assert len({(s.provider, s.station_code) for s in both}) == len(both)
    assert read_catalog(root=root, provider="CHMI") == chmi
    version = current_version(root, slot="catalog:cz.chmi.stations").version
    assert read_catalog(version) == read_catalog(version.parent) == chmi
    assert {s.provider for s in read_catalog(imgw.version)} == {"IMGW-PIB"}
    for call in (
        lambda: read_catalog(),
        lambda: read_catalog(version, root=root),
        lambda: read_catalog(root=root, provider="SHMU"),
    ):
        with pytest.raises(IMGWValidationError):
            call()
    with pytest.raises(IMGWValidationError) as error:
        read_catalog(version, provider="CHMI")
    assert error.value.details["option"] == "provider"


def test_only_the_thresholds_property_may_be_an_object(tmp_path):
    root = init_store(tmp_path / "store").root
    build(root)
    version = current_version(root, slot="catalog:cz.chmi.stations").version

    def variant(name, change):
        document = json.loads(version.read_bytes())
        change(document["features"][3]["properties"])  # 0-203-1-900001
        data = json.dumps(document).encode()
        meta = json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))
        meta.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
        target = tmp_path / name
        target.mkdir()
        (target / "stations.geojson").write_bytes(data)
        (target / "stations.geojson.meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
        return target

    without = read_catalog(variant("null", lambda p: p.update(thresholds=None)))
    assert without[3].properties["thresholds"] is None
    for name, change in (
        ("list", lambda p: p.update(thresholds=[1, 2])),
        ("deep", lambda p: p["thresholds"]["H"].update(unit={"cm": 1})),
        ("name", lambda p: p.update(name={"cs": "Špindlerův Mlýn"})),
    ):
        with pytest.raises(IMGWDataError, match="wartościami prostymi"):
            read_catalog(variant(name, change))


def test_read_station_list_reads_the_stored_chmi_metadata(tmp_path):
    root = init_store(tmp_path / "store").root
    with pytest.raises(IMGWStoreError) as missing:
        read_station_list(root, kind="hydro", provider="CHMI")
    assert missing.value.code == "not_found"
    assert "cz.chmi.hydro_stations" in str(missing.value)
    assert "--provider CHMI" in str(missing.value)

    build(root)
    hydro = read_station_list(root, kind="hydro", provider="CHMI")
    assert hydro == tuple(parse_chmi_stations(body("hydro_stations_get"), kind="hydro"))
    first = hydro[0]
    assert (
        first.station_code,
        first.name,
        first.hydrographic_code,
        first.latitude,
        first.longitude,
        first.provider,
    ) == (
        "0-203-1-900001",
        "Špindlerův Mlýn - most",
        "1-05-03-0110",
        50.4012345,
        15.6012345,
        "CHMI",
    )
    meteo = read_station_list(root, kind="meteo", provider="cz.chmi")
    assert [(s.station_code, s.name) for s in meteo] == [
        ("0-203-0-90001", "Fiktivní Ves-Horní"),
        ("0-203-0-90000000002", "Srážková Lhota"),
        ("0-20000-0-99903", "Nordvik, Base"),
    ]
    observe_regenerated_list(root)
    assert (root / LIST_SLOT / "observations").is_dir()
    assert read_station_list(root, kind="hydro", provider="CHMI") == hydro
    with pytest.raises(IMGWStoreError, match="pl.imgw.hydro_stations"):
        read_station_list(root, kind="hydro")
    with pytest.raises(IMGWValidationError):
        read_station_list(root, kind="hydro", provider="SHMU")


def test_read_archive_normalizes_chmi_versions(tmp_path):
    root = init_store(tmp_path / "store").root
    for archive, parser in (
        (HYDRO_2023, parse_chmi_hydro_daily),
        (SRA, parse_chmi_meteo_daily),
    ):
        written = write_chmi(root, archive)
        expected = list(
            parser(
                (ARCHIVES / archive.server_path).read_bytes(),
                filename=archive.server_path,
            )
        )
        assert expected
        assert list(read_archive(written.path)) == expected
        assert list(read_archive(written.path.parent)) == expected

    build(root)
    stored_list = current_version(
        root, slot="archive:cz.chmi.hydro_stations:meta1.json"
    ).version
    with pytest.raises(IMGWValidationError, match="provider='CHMI'"):
        read_archive(stored_list)

    sidecar = Path(f"{write_chmi(root, HYDRO_2023).path}.meta.json")
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    meta["request"]["station_code"] = "0-203-1-900002"
    sidecar.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(IMGWDataError, match="request.station_code"):
        read_archive(sidecar)


def test_complete_fixture_store_scans_without_problems_as_imgw(tmp_path):
    root = build_fixture_store(tmp_path / "complete").root
    entries = list(iter_store(root))
    assert entries and not [entry for entry in entries if entry.kind == "problem"]
    assert {entry.provider for entry in entries} == {"IMGW-PIB"}
    assert list(iter_store(root, provider="IMGW-PIB")) == entries
    assert list(iter_store(root, provider="CHMI")) == []
