"""Offline, read-only store access: scan, sidecars, current versions, catalog, series, PMAXTP."""

import hashlib
import importlib
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
from imgwtools.datasets import archive_files, get_dataset, station_source_files
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
    check_catalog,
    check_series,
    current_version,
    init_store,
    iter_store,
    read_archive,
    read_catalog,
    read_meta,
    read_pmaxtp,
    read_series,
    read_series_index,
    read_station_list,
    select_series,
    store_info,
    summarize_series,
    sync_pmaxtp,
    write_archive,
)
from imgwtools.store.reader import _reference_signal
from imgwtools.store.types import Observation, SeriesSelection
from tests.contract.support import schema_errors

# ``imgwtools.datasets`` as a module: the package attribute is the ``datasets`` function.
DATASETS_MODULE = importlib.import_module("imgwtools.datasets")
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
DAILY_2024 = "archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
SERIES_DAILY = "series:pl.imgw.hydro_daily"
CELL_SLOT = "pmaxtp:pl.imgw.pmaxtp:POT/751_317"
CONTENT = {"content_sha256": "1" * 64, "content_form": "chmi-json/1"}
# Fictional ČHMÚ sidecar (spec 2026-10-18 §3; codes 0-203-1-9… are not published).
CHMI_PATH = "hydrology/historical/data/daily/H_0-203-1-900001_DQ_2025.json"
CHMI_META = {
    "schema": "imgw-meta/1",
    "producer": "imgwtools",
    "producer_version": "3.1.0",
    "dataset": "cz.chmi.hydro_daily",
    "country": "CZ",
    "provider": "CHMI",
    "request": {
        "server_path": CHMI_PATH,
        "year": 2025,
        "month": None,
        "station_code": "0-203-1-900001",
        "param": None,
    },
    "license": {
        "id": "CC-BY-4.0",
        "attribution": "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), "
        "https://opendata.chmi.cz, licencja CC BY 4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
    },
    "downloaded_at": "2026-10-18T18:00:00Z",
    "sha256": hashlib.sha256(b"{}").hexdigest(),
    "size_bytes": 2,
    "extra": {
        "version": {"label": "2026-05-21", "label_source": "last_modified"},
        "http": {
            "url": f"https://opendata.chmi.cz/{CHMI_PATH}",
            "etag": '"6a0eea27-2"',
            "last_modified": "Thu, 21 May 2026 11:19:03 GMT",
            "content_length": 2,
        },
    },
}


def with_content(version):
    """Give an archive version the content fields of a dataset with a canonical form."""
    sidecar = Path(f"{version}.meta.json")
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    sidecar.write_text(json.dumps({**meta, **CONTENT}), encoding="utf-8")


def observe(version, *, seen_at="2026-10-19T06:00:00Z", etag='"v2"', **changes):
    """Write an observation of ``version`` named by spec §3.2 into its slot register."""
    meta = json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))
    document = {
        "schema": "imgw-observation/1",
        "producer": "imgwtools",
        "producer_version": "3.1.0",
        "dataset": meta["dataset"],
        "seen_at": seen_at,
        "url": meta["extra"]["http"]["url"],
        "last_modified": "Mon, 19 Oct 2026 03:12:44 GMT",
        "etag": etag,
        "size_bytes": meta["size_bytes"] + 1,
        "sha256": "2" * 64,
        "content_sha256": meta.get("content_sha256"),
        "content_form": meta.get("content_form"),
        "same_content_as": version.parent.name,
        **changes,
    }
    signal = json.dumps(
        {key: document[key] for key in ("etag", "last_modified", "size_bytes", "url")},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(signal.encode("utf-8")).hexdigest()[:8]
    path = version.parent.parent / "observations" / f"{seen_at[:10]}_{digest}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


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
        SERIES_DAILY,
        "series:pl.imgw.hydro_monthly",
        "series:pl.imgw.hydro_semiannual",
        "catalog:pl.imgw.stations",
        CELL_SLOT,
        DAILY_2024,
        "archive:pl.imgw.hydro_stations:lista_stacji_hydro.csv",
        "archive:pl.imgw.meteo_stations:wykaz_stacji.csv",
    } <= set(slots)
    assert (
        len(entries) == 13
    )  # 2 daily + 1 monthly + 3 semi-annual + 2 station lists, 3 series, catalog, cell
    assert [entry.slot for entry in iter_store(root, kind="series")] == [
        SERIES_DAILY,
        "series:pl.imgw.hydro_monthly",
        "series:pl.imgw.hydro_semiannual",
    ]
    # Every scanned slot names its own (single, hence current) version.
    for slot, entry in slots.items():
        assert current_version(root, slot=slot) == entry

    assert current_version(root, slot=SERIES_DAILY).version == reports[DAILY].version
    assert (
        current_version(root, slot="catalog:pl.imgw.stations").version
        == catalog.version
    )
    pmaxtp_entry = current_version(root, slot=CELL_SLOT)
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
        current_version(root, slot=SERIES_DAILY)


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
        ("archive:pl.imgw.hydro_daily:2023/codz_2023.zip", "invalid_json"),
        ("archive:pl.imgw.hydro_daily:2022/codz_2022_01.zip", "unknown_schema"),
        (None, "unknown_entry"),
        (None, "stale_incoming"),
    }
    assert {
        entry.version for entry in iter_store(root, kind="problem") if not entry.slot
    } == {root / "junk", stale}
    assert all(entry.problem for entry in iter_store(root, kind="problem"))
    (valid,) = iter_store(root, kind="archive")
    assert valid.version == newest.path and valid.meta.extra["future"] is True
    assert read_meta(newest.path).sha256 == newest.sha256

    with pytest.raises(IMGWDataError, match="Uszkodzona wersja"):
        current_version(root, slot=DAILY_2024)
    with pytest.raises(IMGWDataError, match="unknown_schema|nieobsługiwany schemat"):
        read_meta(oldest.path)
    with pytest.raises(IMGWStoreError, match="Brak sidecara") as missing:
        read_meta(no_sidecar / "codz_2024.zip")
    assert missing.value.code == "not_found"
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
    assert current_version(root, slot=SERIES_DAILY) is None
    assert (
        current_version(root, slot="archive:pl.imgw.hydro_daily:2030/codz_2030.zip")
        is None
    )


@pytest.mark.parametrize(
    "slot",
    [
        # Pre-3.0.0 forms.
        "archive:dane_hydrologiczne/dobowe/2024/codz_2024.zip",
        "series:hydro_daily",
        "catalog:stations",
        "pmaxtp:POT:751_317",
        "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024",
        "raba:archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024",
        # Station selectors exist only in project pins.
        "series:pl.imgw.hydro_daily:149190310",
        # Wrong key, selector or kind.
        "archive:pl.imgw.hydro_daily:codz_2024.zip",
        "archive:pl.imgw.hydro_daily",
        "archive:pl.imgw.hydro_stations:dobowe/2024/codz_2024.zip",
        "archive:pl.imgw.hydro_stations:inna_lista.csv",
        "archive:pl.imgw.hydro_phenomena:2024/zjaw_2024.zip",
        "series:pl.imgw.pmaxtp",
        "catalog:pl.imgw.stations:x",
        "pmaxtp:pl.imgw.pmaxtp:XYZ/1_2",
        "pmaxtp:pl.imgw.pmaxtp",
        "foo",
    ],
)
def test_current_version_rejects_slots_outside_the_grammar(root, slot):
    with pytest.raises(
        IMGWValidationError, match="oczekiwano archive:<klucz>"
    ) as error:
        current_version(root, slot=slot)
    assert error.value.code == "validation_error"
    assert error.value.details == {"option": "slot", "value": slot}


def test_current_version_rejects_unsafe_archive_selector(root):
    with pytest.raises(IMGWValidationError):
        current_version(root, slot="archive:pl.imgw.hydro_daily:../2024/x.zip")


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
    with pytest.raises(IMGWStoreError) as unsupported:
        current_version(future, slot="catalog:pl.imgw.stations")
    assert unsupported.value.code == "store_unavailable"

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


def test_read_series_resolves_version_or_current_series(complete, offline):
    root, reports, _, _ = complete
    version = reports[DAILY].version
    expected = list(read_series(version, station=STATION))
    assert {name for record in expected for name in record.measurements} == {
        "H",
        "Q",
        "T",
    }
    assert list(read_series(version, station=STATION, variables=["H", "Q", "T"])) == (
        expected
    )
    relative = version.relative_to(root)
    for given, kwargs in (
        (relative, {"root": root}),
        (relative.parent, {"root": root}),
        (Path(f"{version}.meta.json"), {}),
        (None, {"root": root, "dataset": DAILY}),
        (None, {"root": root, "dataset": "hydro/dobowe"}),
    ):
        args = () if given is None else (given,)
        assert list(read_series(*args, station=STATION, **kwargs)) == expected


@pytest.mark.parametrize(
    ("given", "kwargs"),
    [
        (True, {"root": True, "dataset": DAILY}),
        (True, {"dataset": DAILY}),
        (False, {}),
        (False, {"root": True}),
        (False, {"dataset": DAILY}),
        (False, {"root": True, "dataset": "pl.imgw.pmaxtp"}),
    ],
)
def test_series_readers_need_version_or_root_with_dataset(complete, given, kwargs):
    root, reports, _, _ = complete
    args = (reports[DAILY].version,) if given else ()
    options = {**kwargs, **({"root": root} if kwargs.get("root") else {})}
    with pytest.raises(IMGWValidationError):
        read_series(*args, station=STATION, **options)
    with pytest.raises(IMGWValidationError):
        summarize_series(*args, **options)


def test_missing_series_or_station_list_is_not_found(root):
    for call in (
        lambda: read_series(root=root, dataset=DAILY, station=STATION),
        lambda: summarize_series(root=root, dataset=DAILY),
        lambda: select_series(root, dataset=DAILY, stations=[STATION]),
        lambda: read_station_list(root, kind="hydro"),
    ):
        with pytest.raises(IMGWStoreError) as error:
            call()
        assert error.value.code == "not_found"


def test_summarize_series_equals_index_without_pyarrow(complete, monkeypatch):
    root, reports, _, _ = complete
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    index = read_series_index(reports[HALF].version)
    variables = list(get_dataset(HALF).variables)
    periods = ["winter", "summer", "annual"]

    summary = summarize_series(root=root, dataset=HALF)
    listed = [
        coverage
        for station in index.stations.values()
        for coverage in station.variables.values()
    ]
    assert sorted(summary, key=repr) == sorted(listed, key=repr)
    assert [(c.station_code, c.variable, c.period) for c in summary] == sorted(
        ((c.station_code, c.variable, c.period) for c in listed),
        key=lambda row: (row[0], variables.index(row[1]), periods.index(row[2])),
    )

    filtered = summarize_series(
        reports[HALF].version, stations=[STATION], variables=["Q_min", "H_max"]
    )
    assert [(c.station_code, c.variable, c.period) for c in filtered] == [
        (STATION, name, period) for name in ("H_max", "Q_min") for period in periods
    ]
    assert all(
        coverage
        == index.stations[coverage.station_code].variables[
            f"{coverage.variable}@{coverage.period}"
        ]
        for coverage in filtered
    )
    daily = read_series_index(reports[DAILY].version)
    other = max(daily.stations)
    assert other != STATION
    both = summarize_series(reports[DAILY].version, stations=[other, STATION, other])
    assert [(c.station_code, c.variable) for c in both] == [
        (code, name) for code in sorted([other, STATION]) for name in ("H", "Q", "T")
    ]
    for kwargs in (
        {"stations": ["999999999"]},
        {"stations": ["1491"]},
        {"stations": STATION},
        {"variables": ["Tmax"]},
    ):
        with pytest.raises(IMGWValidationError):
            summarize_series(reports[HALF].version, **kwargs)


def test_select_series_matches_series_select_semantics(complete, offline):
    root, reports, _, _ = complete
    index = read_series_index(reports[DAILY].version)
    hydrological = {start.year + (start.month >= 11) for start, _ in index.periods} | {
        end.year + (end.month >= 11) for _, end in index.periods
    }

    selection = select_series(root, dataset="hydro/dobowe", stations=[STATION, STATION])
    assert selection == SeriesSelection(
        DAILY,
        reports[DAILY].version,
        (STATION,),
        ("H", "Q", "T"),
        tuple(sorted(hydrological)),
        "hydrological",
    )
    explicit = select_series(
        root,
        dataset=DAILY,
        stations=[STATION],
        variables=["Q"],
        years="2023-2024",
        year_type="calendar",
    )
    assert (explicit.variables, explicit.years, explicit.year_type) == (
        ("Q",),
        (2023, 2024),
        "calendar",
    )
    for dataset, kwargs, option in (
        (DAILY, {"stations": ["999999999"]}, "stations"),
        (DAILY, {"stations": STATION}, "stations"),
        (DAILY, {"stations": [STATION], "variables": ["Tmax"]}, "variables"),
        (DAILY, {"stations": [STATION], "years": [2030]}, "years"),
        (DAILY, {"stations": [STATION], "years": "abc"}, "years"),
        (HALF, {"stations": [STATION], "year_type": "calendar"}, "year_type"),
        ("pl.imgw.pmaxtp", {"stations": [STATION]}, "dataset"),
    ):
        with pytest.raises(IMGWValidationError) as error:
            select_series(root, dataset=dataset, **kwargs)
        assert error.value.details["option"] == option


def test_chmi_sidecar_meets_the_widened_meta_contract_with_optional_content(tmp_path):
    sidecar = tmp_path / "H_0-203-1-900001_DQ_2025.json.meta.json"
    with_content = {**CHMI_META, **CONTENT}
    for document in (CHMI_META, with_content):
        assert schema_errors(document, "imgw-meta/1") == []
        sidecar.write_text(json.dumps(document), encoding="utf-8")
        meta = read_meta(sidecar)
        assert (meta.dataset, meta.license.id) == ("cz.chmi.hydro_daily", "CC-BY-4.0")
        assert (meta.content_sha256, meta.content_form) == (
            document.get("content_sha256"),
            document.get("content_form"),
        )
    for document in (
        {**CHMI_META, "content_sha256": "1" * 64},
        {**CHMI_META, "content_form": "chmi-json/1"},
        {**with_content, "content_sha256": "1" * 63 + "A"},
        {**with_content, "content_sha256": None},
        {**with_content, "content_form": ""},
    ):
        assert schema_errors(document, "imgw-meta/1")
        sidecar.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(IMGWDataError, match="content_"):
            read_meta(sidecar)


def test_scan_enforces_content_pair_and_registry_origin_of_known_datasets(
    root, offline
):
    (written,) = store_archives(root, DAILY, [2024])
    sidecar = Path(f"{written.path}.meta.json")
    original = json.loads(sidecar.read_text(encoding="utf-8"))

    def scan(document):
        sidecar.write_text(json.dumps(document), encoding="utf-8")
        return [
            (entry.kind, entry.slot, entry.problem_code) for entry in iter_store(root)
        ]

    assert scan({**original, **CONTENT}) == [("archive", DAILY_2024, None)]
    assert read_meta(written.path).content_sha256 == "1" * 64
    for document in (
        {**original, "content_sha256": "1" * 64},
        {**original, "content_form": "chmi-json/1"},
        {**original, **CONTENT, "content_sha256": "X" * 64},
    ):
        assert schema_errors(document, "imgw-meta/1")
        assert scan(document) == [("problem", DAILY_2024, "invalid_meta")]
    # The schema knows no registry: a pl.imgw.* sidecar of another provider is valid
    # JSON of imgw-meta/1, but the reader rejects it.
    for change in ({"provider": "CHMI"}, {"country": "CZ"}):
        document = {**original, **change}
        assert schema_errors(document, "imgw-meta/1") == []
        assert scan(document) == [("problem", DAILY_2024, "invalid_meta")]
        with pytest.raises(IMGWDataError, match="rejestrze"):
            read_meta(written.path)


def test_valid_sidecar_of_an_unknown_dataset_is_an_unknown_entry(root, offline):
    stem = "H_0-203-1-900001_DQ_2025"
    version = (
        root
        / "archives/versions/hydrology/historical/data/daily"
        / stem
        / f"2026-05-21_{CHMI_META['sha256'][:8]}"
    )
    version.mkdir(parents=True)
    (version / f"{stem}.json").write_bytes(b"{}")
    (version / f"{stem}.json.meta.json").write_text(
        json.dumps({**CHMI_META, **CONTENT}), encoding="utf-8"
    )
    assert read_meta(version / f"{stem}.json").content_form == "chmi-json/1"
    assert [(e.kind, e.slot, e.problem_code, e.version) for e in iter_store(root)] == [
        ("problem", None, "unknown_entry", version)
    ]


def _rewrite_dataset(version, dataset):
    """Give the sidecar of ``version`` another dataset key; return its bytes and mtime."""
    sidecar = Path(f"{version}.meta.json")
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    sidecar.write_text(json.dumps({**document, "dataset": dataset}), encoding="utf-8")
    return sidecar, (sidecar.read_bytes(), sidecar.stat().st_mtime_ns)


def test_read_meta_resolves_a_renamed_key_and_leaves_the_sidecar_untouched(
    root, offline, monkeypatch
):
    (written,) = store_archives(root, DAILY, [2024])
    sidecar, before = _rewrite_dataset(written.path, "pl.imgw.hydro_day")
    monkeypatch.setattr(
        DATASETS_MODULE, "DATASET_KEY_ALIASES", {"pl.imgw.hydro_day": DAILY}
    )

    meta = read_meta(written.path)

    assert (meta.dataset, meta.dataset_key) == ("pl.imgw.hydro_day", DAILY)
    assert [(e.kind, e.slot, e.problem_code) for e in iter_store(root)] == [
        ("archive", DAILY_2024, None)
    ]
    assert next(read_archive(written.path)).dataset == DAILY
    assert (sidecar.read_bytes(), sidecar.stat().st_mtime_ns) == before


def test_read_meta_gives_no_dataset_key_for_an_unknown_well_formed_key(root, offline):
    (written,) = store_archives(root, DAILY, [2024])
    sidecar, before = _rewrite_dataset(written.path, "pl.imgw.hydro_day")

    meta = read_meta(written.path)

    assert (meta.dataset, meta.dataset_key) == ("pl.imgw.hydro_day", None)
    assert [(e.kind, e.slot, e.problem_code) for e in iter_store(root)] == [
        ("archive", DAILY_2024, None)
    ]
    assert (sidecar.read_bytes(), sidecar.stat().st_mtime_ns) == before
    _rewrite_dataset(written.path, "pl.imgw.Hydro_day")
    with pytest.raises(IMGWDataError, match="kluczem zbioru"):
        read_meta(written.path)


def test_series_index_reads_wigos_station_codes_without_pyarrow(
    root, tmp_path, monkeypatch
):
    store_archives(root, DAILY, [2024])
    moved = tmp_path / "moved"
    shutil.copytree(build_series(root, dataset=DAILY).version.parent, moved)
    original = json.loads((moved / "series.json").read_text(encoding="utf-8"))
    sidecar = json.loads((moved / "series.json.meta.json").read_text(encoding="utf-8"))
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)

    def index_with(code):
        """``series.json`` with the station renamed to ``code``, verified by its sidecar."""
        document = json.loads(json.dumps(original))
        entry = document["stations"].pop(STATION)
        entry["file"] = f"stations/{code}.parquet"
        document["stations"][code] = entry
        shutil.copy(moved / "stations" / f"{STATION}.parquet", moved / entry["file"])
        data = json.dumps(document).encode("utf-8")
        (moved / "series.json").write_bytes(data)
        (moved / "series.json.meta.json").write_text(
            json.dumps(
                {
                    **sidecar,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }
            ),
            encoding="utf-8",
        )
        return document

    assert schema_errors(index_with("0-203-1-CB900003"), "imgw-series/1") == []
    index = read_series_index(moved)
    assert STATION not in index.stations
    assert index.stations["0-203-1-CB900003"].file == Path(
        "stations/0-203-1-CB900003.parquet"
    )
    for code in ("0-203-1-cb900003", "12345678"):
        assert schema_errors(index_with(code), "imgw-series/1")
        with pytest.raises(IMGWDataError, match="kod stacji"):
            read_series_index(moved)


def test_observation_is_a_scan_entry_of_its_archive_slot_not_a_version(root, offline):
    (written,) = store_archives(root, DAILY, [2024])
    with_content(written.path)
    before = current_version(root, slot=DAILY_2024)
    path = observe(written.path)

    assert [(e.kind, e.slot, e.version) for e in iter_store(root)] == [
        ("archive", DAILY_2024, written.path),
        ("observation", DAILY_2024, path),
    ]
    (entry,) = iter_store(root, kind="observation")
    assert (entry.meta, entry.problem_code, entry.problem) == (None, None, None)
    assert entry.observation == Observation(
        DAILY,
        "2026-10-19T06:00:00Z",
        before.meta.extra["http"]["url"],
        "Mon, 19 Oct 2026 03:12:44 GMT",
        '"v2"',
        before.meta.size_bytes + 1,
        "2" * 64,
        "1" * 64,
        "chmi-json/1",
        written.path.parent.name,
    )
    assert current_version(root, slot=DAILY_2024) == before
    assert store_info(root).contracts["observation"] == "imgw-observation/1"


def test_observation_register_reports_each_broken_element(root, tmp_path, offline):
    (written,) = store_archives(root, DAILY, [2024])
    with_content(written.path)
    valid = observe(written.path)
    register = valid.parent
    (register / "notatka.txt").write_text("x", encoding="utf-8")
    (register / "2026-10-19_aaaaaaaa.json").mkdir()
    linked = observe(written.path, etag='"v3"')
    linked.rename(tmp_path / linked.name)
    linked.symlink_to(tmp_path / linked.name)
    (register / "2026-10-19_bbbbbbbb.json").write_text("{zepsuty", encoding="utf-8")
    future = observe(written.path, etag='"v4"', schema="imgw-observation/2")
    dated = observe(written.path, etag='"v5"')
    dated = dated.rename(dated.with_name(f"2026-10-18{dated.name[10:]}"))
    signed = observe(written.path, etag='"v6"')
    signed = signed.rename(signed.with_name("2026-10-19_00000000.json"))
    orphan = observe(written.path, etag='"v7"', same_content_as="2026-01-01_deadbeef")
    other = observe(written.path, etag='"v8"', content_sha256="3" * 64)
    foreign = observe(written.path, etag='"v9"', dataset="pl.imgw.hydro_monthly")

    problems = sorted(
        (entry.version.name, entry.slot or "", entry.problem_code)
        for entry in iter_store(root, kind="problem")
    )
    assert problems == sorted(
        [
            ("notatka.txt", "", "unknown_entry"),
            ("2026-10-19_aaaaaaaa.json", "", "unknown_entry"),
            (linked.name, DAILY_2024, "symlink"),
            ("2026-10-19_bbbbbbbb.json", DAILY_2024, "invalid_json"),
            (future.name, DAILY_2024, "unknown_schema"),
            (dated.name, DAILY_2024, "invalid_meta"),
            (signed.name, DAILY_2024, "invalid_meta"),
            (orphan.name, DAILY_2024, "invalid_meta"),
            (other.name, DAILY_2024, "invalid_meta"),
            (foreign.name, DAILY_2024, "invalid_meta"),
        ]
    )
    assert [entry.version for entry in iter_store(root, kind="observation")] == [valid]
    assert current_version(root, slot=DAILY_2024).version == written.path


def test_observations_outside_an_archive_slot_register_are_unknown_entries(
    root, offline
):
    (written,) = store_archives(root, DAILY, [2024])
    misplaced = [
        written.path.parent.parent.parent / "observations",  # no versions beside it
        root / "stations" / "versions" / "observations",  # catalog slot
    ]
    for directory in misplaced:
        directory.mkdir(parents=True)
        (directory / "2026-10-19_00000000.json").write_text("{}", encoding="utf-8")
    assert sorted(
        (entry.version, entry.slot, entry.problem_code)
        for entry in iter_store(root, kind="problem")
    ) == sorted((directory, None, "unknown_entry") for directory in misplaced)


def test_reference_signal_is_the_newest_observation_of_the_current_version(
    root, offline
):
    (older,) = store_archives(root, DAILY, [2024])
    (archive,) = archive_files(DAILY, years=[2024])
    changed = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()
    signal = ('"v2"', "Mon, 19 Oct 2026 12:00:00 GMT")
    newer = write_archive(
        root,
        archive=archive,
        response=DownloadResult(changed, archive.url, *signal, len(changed)),
    )
    with_content(older.path)
    with_content(newer.path)

    reference = _reference_signal(root, slot=DAILY_2024)
    assert reference is not None
    assert (reference.version.version, reference.observation) == (newer.path, None)
    assert (
        reference.url,
        reference.etag,
        reference.last_modified,
        reference.size_bytes,
    ) == (archive.url, *signal, len(changed))

    observe(older.path, seen_at="2026-10-21T06:00:00Z", etag='"older"')
    observe(newer.path, seen_at="2026-10-19T06:00:00Z", etag='"v3"')
    latest = observe(newer.path, seen_at="2026-10-20T06:00:00Z", etag='"v4"')
    reference = _reference_signal(root, slot=DAILY_2024)
    assert reference is not None
    assert (reference.version.version, reference.observation) == (newer.path, latest)
    assert (
        reference.url,
        reference.etag,
        reference.last_modified,
        reference.size_bytes,
    ) == (archive.url, '"v4"', "Mon, 19 Oct 2026 03:12:44 GMT", len(changed) + 1)

    broken = observe(newer.path, seen_at="2026-10-22T06:00:00Z", etag='"v5"')
    broken.write_text("{zepsuty", encoding="utf-8")
    with pytest.raises(IMGWDataError, match="obserwacja"):
        _reference_signal(root, slot=DAILY_2024)
    broken.unlink()
    observe(newer.path, etag='"v6"', content_sha256="3" * 64)
    with pytest.raises(IMGWDataError, match="pola treści"):
        _reference_signal(root, slot=DAILY_2024)
    assert (
        _reference_signal(root, slot="archive:pl.imgw.hydro_daily:2030/x.zip") is None
    )


def test_registers_change_no_version_choice_of_series_or_catalog(tmp_path):
    def catalog_sources(router):
        record_catalog_sources(router)
        headers = {"ETag": '"list-v1"', "Last-Modified": SIGNAL[1]}
        for archive in station_source_files():
            router.head(archive.url).mock(
                return_value=httpx.Response(200, headers=headers)
            )

    outcomes = {}
    for name in ("plain", "observed"):
        root = init_store(tmp_path / name).root
        store_archives(root, DAILY, [2024])
        with respx.mock(assert_all_called=False) as router:
            catalog_sources(router)
            build_catalog(root)
            if name == "observed":
                for sidecar in list(root.glob("archives/versions/**/*.meta.json")):
                    register = sidecar.parent.parent / "observations"
                    register.mkdir(exist_ok=True)
                    (register / "2026-10-19_00000000.json").write_text(
                        "{}", encoding="utf-8"
                    )
            plan = check_catalog(root)
            catalog = build_catalog(root)
        series = build_series(root, dataset=DAILY)
        outcomes[name] = (
            [
                (
                    item.archive.server_path,
                    item.status,
                    item.local_path and item.local_path.relative_to(root),
                )
                for item in plan.items
            ],
            catalog.status,
            catalog.version.read_bytes(),
            series.status,
            series.version.read_bytes(),
            check_series(root, dataset=DAILY).series_state,
        )
    assert outcomes["observed"] == outcomes["plain"]
    assert outcomes["plain"][1] == "unchanged" and outcomes["plain"][3] == "created"
