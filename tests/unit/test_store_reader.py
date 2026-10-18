"""Offline, read-only store access: scan, sidecars, current versions, catalog, series, PMAXTP."""

import hashlib
import json
import os
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools._parsing import normalize_archive
from imgwtools.datasets import archive_files, station_source_files
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWStoreDependencyError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store import (
    build_catalog,
    build_series,
    current_version,
    init_store,
    iter_store,
    read_catalog,
    read_meta,
    read_pmaxtp,
    read_series,
    read_series_index,
    store_info,
    sync_pmaxtp,
    write_archive,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDINGS = {
    item["case"]: item
    for item in json.loads((FIXTURES / "recordings.json").read_text(encoding="utf-8"))[
        "interactions"
    ]
}
SIGNAL = ('"v1"', "Sat, 17 Oct 2026 12:00:00 GMT")
DAILY = "pl.imgw.hydro_daily"
HALF = "pl.imgw.hydro_semiannual"
STATION = "149190310"
DAILY_2024 = "archive:dane_hydrologiczne/dobowe/2024/codz_2024.zip"


def store_archives(root, dataset, years, months=None, *, signal=SIGNAL):
    written = []
    for archive in archive_files(dataset, years=years, months=months):
        source = FIXTURES / "archives" / archive.server_path
        if source.exists():
            content = source.read_bytes()
            response = DownloadResult(
                content, archive.url, signal[0], signal[1], len(content)
            )
            written.append(write_archive(root, archive=archive, response=response))
    return written


def record_catalog_sources(router):
    headers = {"ETag": '"list-v1"', "Last-Modified": SIGNAL[1]}
    for archive in station_source_files():
        body = (FIXTURES / "archives" / archive.server_path).read_bytes()
        router.get(archive.url).mock(
            return_value=httpx.Response(200, content=body, headers=headers)
        )
    for case in ("hydro_current", "meteo_current"):
        router.get(RECORDINGS[case]["url"]).mock(
            return_value=httpx.Response(200, json=RECORDINGS[case]["json"])
        )
    pmaxtp = RECORDINGS["pmaxtp_pot_first"]
    router.get(pmaxtp["url"]).mock(
        return_value=httpx.Response(pmaxtp["status"], json=pmaxtp["json"])
    )


def tree(root):
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


def set_read_only(root, read_only):
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            path.chmod(0o555 if read_only else 0o755)
        else:
            path.chmod(0o444 if read_only else 0o644)


def parser_records(dataset, server_path):
    (archive,) = [
        item
        for item in archive_files(dataset, years=[2024])
        if item.server_path == server_path
    ]
    return list(
        normalize_archive(
            archive, data=(FIXTURES / "archives" / server_path).read_bytes()
        )
    )


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    """A store with archives, three series, a catalog and a PMAXTP cell, then made read-only."""
    root = init_store(tmp_path_factory.mktemp("reader") / "store").root
    store_archives(root, DAILY, [2023, 2024])
    store_archives(root, "pl.imgw.hydro_monthly", [2024])
    store_archives(root, HALF, [2024])
    reports = {
        dataset: build_series(root, dataset=dataset)
        for dataset in (DAILY, "pl.imgw.hydro_monthly", HALF)
    }
    with respx.mock(assert_all_called=False) as router:
        record_catalog_sources(router)
        catalog = build_catalog(root)
        cell = sync_pmaxtp(root, method="POT", latitude=52.23, longitude=21.01)
    set_read_only(root, True)
    yield root, reports, catalog, cell
    set_read_only(root, False)


@pytest.fixture
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("odczyt magazynu nie może używać sieci")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


def test_every_reader_works_on_read_only_store_without_writes_or_network(
    complete, offline
):
    root, reports, catalog, cell = complete
    before = tree(root)

    info = store_info(root)
    assert (info.exists, info.schema, info.supported, info.problems) == (
        True,
        "imgw-store/1",
        True,
        (),
    )
    assert (
        info.contracts["series"] == "imgw-series/1"
        and info.contracts["pmaxtp"] == "imgw-pmaxtp/1"
    )

    entries = list(iter_store(root))
    assert [entry for entry in entries if entry.kind == "problem"] == []
    slots = {entry.slot: entry for entry in entries}
    assert {entry.kind for entry in entries} == {
        "archive",
        "series",
        "catalog",
        "pmaxtp",
    }
    assert {
        "series:hydro_daily",
        "series:hydro_monthly",
        "series:hydro_semiannual",
        "catalog:stations",
        "pmaxtp:POT:751_317",
        DAILY_2024,
        "archive:dane_hydrologiczne/lista_stacji_hydro.csv",
    } <= set(slots)
    assert (
        len(entries) == 13
    )  # 2 daily + 1 monthly + 3 semi-annual + 2 station lists, 3 series, catalog, cell
    assert [entry.slot for entry in iter_store(root, kind="series")] == [
        "series:hydro_daily",
        "series:hydro_monthly",
        "series:hydro_semiannual",
    ]

    assert (
        current_version(root, slot="series:hydro_daily").version
        == reports[DAILY].version
    )
    assert current_version(root, slot="catalog:stations").version == catalog.version
    pmaxtp_entry = current_version(root, slot="pmaxtp:POT:751_317")
    assert (
        pmaxtp_entry.version == cell.version
        and pmaxtp_entry.meta.dataset == "pl.imgw.pmaxtp"
    )
    archive_entry = current_version(root, slot=DAILY_2024)
    assert archive_entry == slots[DAILY_2024]
    assert (
        read_meta(archive_entry.version)
        == read_meta(f"{archive_entry.version}.meta.json")
        == archive_entry.meta
    )

    features = read_catalog(catalog.version)
    assert len(features) == catalog.station_count
    assert (
        sum(feature.geometry is None for feature in features)
        == catalog.without_location
    )
    assert read_catalog(catalog.version.parent) == features

    index = read_series_index(reports[DAILY].version)
    assert index.dataset == DAILY and index.year_type == "hydrological"
    records = list(
        read_series(reports[DAILY].version, station=STATION, variables=["H", "Q"])
    )
    assert len(records) == index.stations[STATION].rows

    # read_pmaxtp (T14) interoperates with the version returned by current_version.
    stored = read_pmaxtp(root, method="POT", ind_x=751, ind_y=317)
    assert (
        read_pmaxtp(
            root, method="POT", ind_x=751, ind_y=317, version=pmaxtp_entry.version
        )
        == stored
    )
    assert stored.data.get_precipitation(15, 50) == 13.34

    assert tree(root) == before


def test_series_range_matches_parser_records(complete, offline):
    root, reports, _, _ = complete
    parsed = {
        r.date: r
        for r in parser_records(DAILY, "dane_hydrologiczne/dobowe/2024/codz_2024.zip")
        if r.station_code == STATION
    }
    days = sorted(parsed)
    start, end = days[0], days[-1]
    records = list(
        read_series(
            reports[DAILY].version,
            station=STATION,
            variables=("H", "Q", "T"),
            start=start,
            end=end,
        )
    )
    # Inclusive bounds, continuous calendar between them, parser values/flags at every parsed day.
    assert [r.date for r in records] == [
        start + timedelta(days=n) for n in range((end - start).days + 1)
    ]
    by_day = {r.date: r for r in records}
    assert all(by_day[day].measurements == parsed[day].measurements for day in days)
    assert all(
        by_day[day].hydro_year == parsed[day].hydro_year and by_day[day].period is None
        for day in days
    )
    assert all(
        r.measurements["H"].flag == "missing" for r in records if r.date not in parsed
    )

    later = start + timedelta(days=1)
    only_h = list(
        read_series(
            reports[DAILY].version,
            station=STATION,
            variables=["H"],
            start=later,
            end=later,
        )
    )
    assert [(r.date, set(r.measurements)) for r in only_h] == [(later, {"H"})]
    tail = list(
        read_series(reports[DAILY].version, station=STATION, variables=["H"], start=end)
    )
    assert [r.date for r in tail] == [end]
    assert (
        list(
            read_series(
                reports[DAILY].version,
                station=STATION,
                variables=["H"],
                start=date(1990, 1, 1),
                end=date(1990, 1, 2),
            )
        )
        == []
    )


def test_half_year_filter_uses_period_start_and_keeps_extrema(complete, offline):
    root, reports, _, _ = complete
    summer = list(
        read_series(
            reports[HALF].version,
            station=STATION,
            variables=["H_max"],
            start=date(2024, 5, 1),
            end=date(2024, 5, 1),
        )
    )
    assert [(r.date, r.period, r.hydro_year) for r in summer] == [
        (date(2024, 5, 1), "summer", 2024)
    ]
    whole = list(
        read_series(reports[HALF].version, station=STATION, variables=["H_max"])
    )
    assert [r.period for r in whole] == ["winter", "summer", "annual"]
    parsed = {
        (r.date, r.period): r
        for r in parser_records(
            HALF, "dane_hydrologiczne/polroczne_i_roczne/2024/polr_H_2024.zip"
        )
        if r.station_code == STATION and "H_max" in r.measurements
    }
    assert parsed
    for record in whole:
        source = parsed[(record.date, record.period)]
        assert record.measurements["H_max"] == source.measurements["H_max"]
        assert record.extrema_dates["H_max"] == source.extrema_dates["H_max"]


def test_series_index_needs_no_pyarrow_but_series_does(complete, monkeypatch):
    _, reports, _, _ = complete
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    index = read_series_index(reports[DAILY].version.parent)
    assert index.stations[STATION].file == Path(f"stations/{STATION}.parquet")
    coverage = index.stations["149190311"].variables["Q"]
    assert (coverage.first, coverage.with_value, coverage.period) == (None, 0, None)
    with pytest.raises(IMGWStoreDependencyError):
        read_series(reports[DAILY].version, station=STATION, variables=["H"])


def test_series_validation_and_tampered_parquet(root):
    store_archives(root, DAILY, [2024])
    version = build_series(root, dataset=DAILY).version
    for kwargs in (
        {"station": "000000000", "variables": ["H"]},
        {"station": STATION, "variables": ["Tmax"]},
        {"station": STATION, "variables": "H"},
        {"station": STATION, "variables": []},
        {
            "station": STATION,
            "variables": ["H"],
            "start": date(2024, 2, 1),
            "end": date(2024, 1, 1),
        },
    ):
        with pytest.raises(IMGWValidationError):
            read_series(version, **kwargs)
    with pytest.raises(IMGWValidationError):
        read_series_index(version.with_name("other.json"))

    parquet = version.parent / "stations" / f"{STATION}.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"\0")
    with pytest.raises(IMGWDataError, match="Suma kontrolna"):
        read_series(version, station=STATION, variables=["H"])
    parquet.unlink()
    with pytest.raises(IMGWDataError, match="brak pliku"):
        read_series_index(version)

    index = json.loads(version.read_text(encoding="utf-8"))
    index["schema"] = "imgw-series/2"
    version.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(IMGWDataError, match="Suma kontrolna"):
        read_series_index(version)


def test_unknown_series_schema_is_a_scan_problem_not_a_version(root, offline):
    store_archives(root, DAILY, [2024])
    version = build_series(root, dataset=DAILY).version
    sidecar = json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))
    later = version.parent.with_name(f"2099-01-01_{sidecar['sha256'][:8]}")
    shutil.copytree(version.parent, later)
    sidecar["extra"]["version"]["label"] = "2099-01-01"
    sidecar["downloaded_at"] = "2099-01-01T00:00:00+00:00"
    sidecar["extra"]["series_schema"] = "imgw-series/2"
    (later / f"{version.name}.meta.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )

    problems = {
        (entry.version, entry.problem_code)
        for entry in iter_store(root, kind="problem")
    }
    assert problems == {(later, "unknown_schema")}
    assert [entry.version for entry in iter_store(root, kind="series")] == [version]
    with pytest.raises(IMGWDataError, match="nieobsługiwany schemat szeregu"):
        current_version(root, slot="series:hydro_daily")


def test_catalog_is_verified_against_sidecar(complete, tmp_path):
    _, _, catalog, _ = complete
    copy = tmp_path / "copy"
    shutil.copytree(catalog.version.parent, copy)
    (copy / "stations.geojson").chmod(0o644)
    data = json.loads((copy / "stations.geojson").read_text(encoding="utf-8"))
    data["features"] = data["features"][:1]
    (copy / "stations.geojson").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(IMGWDataError, match="Suma kontrolna"):
        read_catalog(copy)


def test_scan_reports_problems_and_tolerates_additional_fields(root, offline):
    written = store_archives(root, DAILY, [2022, 2023, 2024], [1])
    newest = next(entry for entry in written if entry.path.name == "codz_2024.zip")
    oldest = next(entry for entry in written if entry.path.name == "codz_2022_01.zip")
    middle = next(entry for entry in written if entry.path.name == "codz_2023.zip")

    sidecar = Path(f"{newest.path}.meta.json")
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    meta["future_field"] = {"x": 1}
    meta["extra"]["future"] = True
    sidecar.write_text(json.dumps(meta), encoding="utf-8")

    no_sidecar = newest.path.parent.with_name("2026-01-01_deadbeef")
    no_sidecar.mkdir()
    shutil.copy(newest.path, no_sidecar / newest.path.name)
    missing_field = newest.path.parent.with_name("2026-01-02_cafebabe")
    shutil.copytree(newest.path.parent, missing_field)
    broken = json.loads(
        (missing_field / "codz_2024.zip.meta.json").read_text(encoding="utf-8")
    )
    del broken["size_bytes"]
    (missing_field / "codz_2024.zip.meta.json").write_text(
        json.dumps(broken), encoding="utf-8"
    )

    Path(f"{middle.path}.meta.json").write_text("{broken", encoding="utf-8")
    old_meta = json.loads(Path(f"{oldest.path}.meta.json").read_text(encoding="utf-8"))
    old_meta["schema"] = "imgw-meta/2"
    Path(f"{oldest.path}.meta.json").write_text(json.dumps(old_meta), encoding="utf-8")

    (root / "junk").mkdir()
    stale, young = root / ".incoming" / "host_1_old", root / ".incoming" / "host_2_new"
    stale.mkdir()
    young.mkdir()
    day_ago = time.time() - 25 * 3600
    os.utime(stale, (day_ago, day_ago))
    before = tree(root)

    problems = {
        (entry.slot, entry.problem_code) for entry in iter_store(root, kind="problem")
    }
    assert problems == {
        (DAILY_2024, "missing_sidecar"),
        (DAILY_2024, "invalid_meta"),
        ("archive:dane_hydrologiczne/dobowe/2023/codz_2023.zip", "invalid_json"),
        ("archive:dane_hydrologiczne/dobowe/2022/codz_2022_01.zip", "unknown_schema"),
        ("junk", "unknown_entry"),
        (".incoming/host_1_old", "stale_incoming"),
    }
    assert all(entry.problem for entry in iter_store(root, kind="problem"))
    (valid,) = iter_store(root, kind="archive")
    assert valid.version == newest.path and valid.meta.extra["future"] is True
    assert read_meta(newest.path).sha256 == newest.sha256

    with pytest.raises(IMGWDataError, match="Uszkodzona wersja"):
        current_version(root, slot=DAILY_2024)
    with pytest.raises(IMGWDataError, match="unknown_schema|nieobsługiwany schemat"):
        read_meta(oldest.path)
    with pytest.raises(IMGWStoreError, match="Brak sidecara"):
        read_meta(no_sidecar / "codz_2024.zip")
    with pytest.raises(IMGWValidationError):
        list(iter_store(root, kind="archives"))
    assert tree(root) == before


def test_current_version_follows_last_modified_rule(root):
    (archive,) = archive_files(DAILY, years=[2024])
    changed = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()
    newer = write_archive(
        root,
        archive=archive,
        response=DownloadResult(
            changed,
            archive.url,
            '"v2"',
            "Mon, 19 Oct 2026 12:00:00 GMT",
            len(changed),
        ),
    )
    store_archives(root, DAILY, [2024])  # downloaded later, but published earlier
    entry = current_version(root, slot=DAILY_2024)
    assert (
        entry.kind == "archive"
        and entry.version == newer.path
        and entry.meta.sha256 == newer.sha256
    )
    assert current_version(root, slot="series:hydro_daily") is None
    assert (
        current_version(
            root, slot="archive:dane_hydrologiczne/dobowe/2030/codz_2030.zip"
        )
        is None
    )
    for slot in (
        "series:unknown",
        "catalog:other",
        "pmaxtp:XYZ:1_2",
        "archive:../x.zip",
        "archive:codz.zip",
        "foo",
    ):
        with pytest.raises(IMGWValidationError):
            current_version(root, slot=slot)


def test_unknown_store_version_is_reported_not_raised(tmp_path):
    future = tmp_path / "future"
    future.mkdir()
    (future / "imgw-store.json").write_text(
        '{"schema":"imgw-store/2","created_by":"imgwtools 9"}', encoding="utf-8"
    )
    info = store_info(future)
    assert (info.exists, info.schema, info.supported) == (True, "imgw-store/2", False)
    assert "imgw-store/2" in info.problems[0]
    (problem,) = iter_store(future)
    assert (problem.kind, problem.problem_code) == ("problem", "unsupported_store")
    with pytest.raises(IMGWStoreError):
        current_version(future, slot="catalog:stations")

    missing = store_info(tmp_path / "absent")
    assert (missing.exists, missing.schema, missing.supported) == (False, None, False)
    assert not (tmp_path / "absent").exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert [entry.problem_code for entry in iter_store(empty)] == ["missing_marker"]
    assert list(empty.iterdir()) == []


def test_read_meta_rejects_wrong_required_field_types(root):
    (written,) = store_archives(root, DAILY, [2024])
    sidecar = Path(f"{written.path}.meta.json")
    original = json.loads(sidecar.read_text(encoding="utf-8"))
    assert read_meta(sidecar).license.id == "IMGW-PIB"
    for key, value in (
        ("sha256", "X" * 64),
        ("size_bytes", "12"),
        ("downloaded_at", "wczoraj"),
        ("request", []),
    ):
        sidecar.write_text(json.dumps({**original, key: value}), encoding="utf-8")
        with pytest.raises(IMGWDataError):
            read_meta(written.path)
    assert hashlib.sha256(written.path.read_bytes()).hexdigest() == written.sha256
