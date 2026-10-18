"""Offline scenarios for imgw-series/1 snapshots (check_series/build_series)."""

import gc
import hashlib
import io
import json
import math
import subprocess
import sys
import tracemalloc
import zipfile
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWStoreDependencyError, IMGWValidationError
from imgwtools.fetch import DownloadResult
from imgwtools.models import NormalizedRecord
from imgwtools.store import current_version, init_store, write_archive
from imgwtools.store import series as series_module
from imgwtools.store.series import build_series, check_series

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
HYDRO = "pl.imgw.hydro_daily"
SIGNAL = ('"v1"', "Sat, 17 Oct 2026 12:00:00 GMT")
FLAGS = {"value", "missing", "no_phenomenon", "accumulated"}


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


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
    }


def read_index(report):
    return json.loads(report.version.read_text(encoding="utf-8"))


def series_versions(root, slug="hydro_daily"):
    base = root / "series" / "versions" / slug
    return sorted(base.iterdir()) if base.exists() else []


def station_table(report, code):
    index = read_index(report)
    return pq.read_table(report.version.parent / index["stations"][code]["file"])


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("szeregi nie mogą używać sieci")

    monkeypatch.setattr(httpx.Client, "send", refuse)


def test_check_series_is_offline_read_only_and_tracks_state(root):
    written = store_archives(root, HYDRO, [2022, 2023, 2024], [1])
    before = tree(root)
    plan = check_series(root, dataset=HYDRO)
    assert tree(root) == before
    assert plan.series_state == {"hydro_daily": "missing"}
    assert [item.status for item in plan.items] == ["current"] * 3
    assert {item.local_sha256 for item in plan.items} == {
        entry.sha256 for entry in written
    }
    assert {(root / item.local_path) for item in plan.items} == {
        entry.path for entry in written
    }
    assert plan.actions[0].status == "missing"

    assert build_series(root, dataset=HYDRO).status == "created"
    assert check_series(root, dataset=HYDRO).series_state == {"hydro_daily": "current"}

    archive = archive_files(HYDRO, years=[2024])[0]
    changed = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()
    write_archive(
        root,
        archive=archive,
        response=DownloadResult(
            changed, archive.url, '"v3"', "Mon, 19 Oct 2026 12:00:00 GMT", len(changed)
        ),
    )
    outdated = check_series(root, dataset=HYDRO)
    assert outdated.series_state == {"hydro_daily": "outdated"}
    assert outdated.actions[0].status == "newer"

    cancelled = check_series(root, dataset=HYDRO, cancel=lambda: True)
    assert cancelled.cancelled and {item.error for item in cancelled.items} == {
        "anulowano"
    }


def test_daily_hydro_snapshot_covers_every_day_and_all_stations(root):
    written = store_archives(root, HYDRO, [2022, 2023, 2024], [1])
    report = build_series(root, dataset=HYDRO)
    assert report.status == "created" and report.stations == 2 and report.problems == ()
    assert set(report.source_files) == {entry.path for entry in written}
    version_dir = report.version.parent
    assert version_dir.parent == root / "series/versions/hydro_daily"

    raw = report.version.read_bytes()
    index = json.loads(raw)
    assert (
        raw
        == (
            json.dumps(index, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode()
    )
    assert version_dir.name == f"2026-10-17_{hashlib.sha256(raw).hexdigest()[:8]}"
    assert index["schema"] == "imgw-series/1" and index["year_type"] == "hydrological"
    assert index["periods"] == [
        ["2021-11-01", "2021-11-30"],
        ["2022-11-01", "2024-10-31"],
    ]
    # Stations need neither catalog nor coordinates; an all-missing variable keeps its entry.
    assert set(index["stations"]) == {"149190310", "149190311"}
    empty = index["stations"]["149190311"]["variables"]["Q"]
    assert empty == {
        "unit": "m3/s",
        "first": None,
        "last": None,
        "with_value": 0,
        "accumulated": 0,
        "gaps": [],
    }
    for code, entry in index["stations"].items():
        assert entry["file"] == f"stations/{code}.parquet"
        assert (
            hashlib.sha256((version_dir / entry["file"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )

    meta = json.loads(
        (version_dir / "series.json.meta.json").read_text(encoding="utf-8")
    )
    assert meta["sha256"] == hashlib.sha256(raw).hexdigest() and meta[
        "size_bytes"
    ] == len(raw)
    assert (
        meta["extra"]["derived"] == "series"
        and meta["extra"]["series_schema"] == "imgw-series/1"
    )
    assert meta["extra"]["version"] == {"label": "2026-10-17", "label_source": "inputs"}
    assert "zostały przetworzone" in meta["license"]["attribution"]
    assert sorted(
        (item["file"], item["sha256"], item["label"])
        for item in meta["extra"]["source_files"]
    ) == sorted(
        (entry.path.relative_to(root).as_posix(), entry.sha256, entry.label)
        for entry in written
    )

    table = station_table(report, "149190310")
    rows = table.to_pylist()
    first, last = date(2021, 11, 1), date(2024, 2, 29)
    assert [row["date"] for row in rows] == [
        first + timedelta(days=n) for n in range((last - first).days + 1)
    ]
    assert index["stations"]["149190310"]["rows"] == len(rows)
    by_day = {row["date"]: row for row in rows}
    assert by_day[date(2024, 2, 29)]["H_value"] == 154.0
    assert (
        by_day[date(2023, 10, 31)]["hydro_year"] == 2023
        and by_day[date(2023, 11, 1)]["hydro_year"] == 2024
    )
    assert (
        by_day[date(2021, 11, 2)]["Q_value"] is None
        and by_day[date(2021, 11, 2)]["H_value"] == 153.0
    )
    assert by_day[date(2022, 6, 1)]["H_flag"] == "missing"
    assert all(
        (row[f"{v}_value"] is None) == (row[f"{v}_flag"] == "missing")
        for row in rows
        for v in "HQT"
    )
    schema = table.schema
    assert (
        schema.field("date").type == pa.date32()
        and schema.field("hydro_year").type == pa.int32()
    )
    assert schema.field("H_value").type == pa.float64()
    assert (
        pa.types.is_dictionary(schema.field("H_flag").type)
        and schema.field("H_flag").type.value_type == pa.string()
    )
    assert set(table.column("H_flag").combine_chunks().dictionary.to_pylist()) == FLAGS
    assert schema.metadata[b"imgw_schema"] == b"imgw-series/1"
    assert schema.metadata[b"dataset"] == HYDRO.encode()
    assert json.loads(schema.metadata[b"units"]) == {
        "H": "cm",
        "Q": "m3/s",
        "T": "degC",
    }


def test_meteo_snapshot_has_hydrological_year_leap_day_and_accumulated(root):
    store_archives(root, "pl.imgw.meteo_climate_daily", [1995, 2004], [2])
    report = build_series(root, dataset="pl.imgw.meteo_climate_daily")
    index = read_index(report)
    assert index["year_type"] == "calendar"
    assert index["periods"] == [
        ["1995-01-01", "1995-12-31"],
        ["2004-02-01", "2004-02-29"],
    ]
    rows = {row["date"]: row for row in station_table(report, "123750000").to_pylist()}
    assert len(rows) == (date(2004, 2, 29) - date(1995, 1, 1)).days + 1
    assert (
        rows[date(1995, 10, 31)]["hydro_year"] == 1995
        and rows[date(1995, 11, 1)]["hydro_year"] == 1996
    )
    assert date(2004, 2, 29) in rows
    assert (
        rows[date(1995, 1, 1)]["P_flag"] == "no_phenomenon"
        and rows[date(1995, 1, 1)]["P_value"] == 0.0
    )

    store_archives(root, "pl.imgw.meteo_precip_daily", [2001], [1])
    precip = build_series(root, dataset="pl.imgw.meteo_precip_daily")
    station = read_index(precip)["stations"]["123750000"]
    table = station_table(precip, "123750000").to_pylist()
    assert (
        station["variables"]["P"]["accumulated"]
        == sum(row["P_flag"] == "accumulated" for row in table)
        >= 1
    )
    assert [
        column
        for column in station_table(precip, "123750000").column_names
        if column.endswith("_value")
    ] == [
        "P_value",
        "snow_cover_value",
        "fresh_snow_value",
    ]


def test_monthly_and_semiannual_snapshots(root):
    store_archives(root, "pl.imgw.hydro_monthly", [2024])
    monthly = build_series(root, dataset="pl.imgw.hydro_monthly")
    table = station_table(monthly, "149190310")
    assert [column for column in table.column_names if column.endswith("_value")] == [
        f"{v}_{s}_value" for v in "HQT" for s in ("min", "mean", "max")
    ]
    (row,) = table.to_pylist()
    assert (
        row["date"] == date(2024, 2, 1)
        and row["hydro_year"] == 2024
        and row["Q_max_value"] == 3.9
    )

    store_archives(root, "pl.imgw.hydro_semiannual", [2024])
    half = build_series(root, dataset="pl.imgw.hydro_semiannual")
    assert len(half.source_files) == 3
    index = read_index(half)
    variables = index["stations"]["149190310"]["variables"]
    assert {"Q_min@winter", "Q_min@summer", "Q_min@annual"} <= set(variables)
    assert "Q_min" not in variables
    table = station_table(half, "149190310")
    assert pa.types.is_dictionary(table.schema.field("period").type)
    assert table.schema.field("H_max_start").type == pa.timestamp("us")
    rows = table.to_pylist()
    assert [(row["period"], row["date"], row["hydro_year"]) for row in rows] == [
        ("winter", date(2023, 11, 1), 2024),
        ("summer", date(2024, 5, 1), 2024),
        ("annual", date(2023, 11, 1), 2024),
    ]
    # One row merges H, Q and T from three separate archives.
    assert all(rows[0][f"{v}_min_flag"] == "value" for v in "HQT")
    assert rows[0]["H_min_start"] == datetime(2024, 2, 29, 8, 30)


def put_csv(root, archive, name, rows, *, signal=SIGNAL):
    """Store a ZIP holding one CSV member as the current version of ``archive``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(name, rows.encode("cp1250"))
    content = buffer.getvalue()
    response = DownloadResult(content, archive.url, signal[0], signal[1], len(content))
    return write_archive(root, archive=archive, response=response)


def test_semiannual_repeated_extremum_rows_build_one_value_with_occurrences(root):
    (archive,) = [
        item
        for item in archive_files("pl.imgw.hydro_semiannual", years=[2024])
        if item.param == "H"
    ]
    rows = (
        "149190310,Raba Górna,Raba,2024,13,H,3,278,2023,12,25,6,0,2023,12,25,8,20\n"
        "149190310,Raba Górna,Raba,2024,13,H,3,278,2023,12,25,8,40,2023,12,25,8,40\n"
        "149190310,Raba Górna,Raba,2024,13,H,2,160,,,,,,,,,,\n"
    )
    put_csv(root, archive, "polr_H_2024.csv", rows)
    report = build_series(root, dataset="pl.imgw.hydro_semiannual")
    assert report.status == "created", report.problems
    table = station_table(report, "149190310")
    assert table.schema.field("H_max_occurrences").type == pa.int32()
    winter = table.to_pylist()[0]
    assert (winter["period"], winter["H_max_value"]) == ("winter", 278.0)
    assert (winter["H_max_start"], winter["H_max_end"]) == (
        datetime(2023, 12, 25, 6, 0),
        datetime(2023, 12, 25, 8, 40),
    )
    assert (winter["H_max_occurrences"], winter["H_mean_occurrences"]) == (2, 1)
    assert winter["H_min_occurrences"] is None


def test_parsing_memory_does_not_grow_with_the_dataset(root, monkeypatch):
    # 12 monthly archives x 60 stations: the old builder kept every parsed day of
    # every station in memory until all archives were read.
    for archive in archive_files(HYDRO, years=[2021]):
        assert archive.month is not None
        hydro_year = 2021 + (archive.month >= 11)
        hydro_month = (archive.month + 1) % 12 + 1
        rows = "".join(
            f'"{149190000 + code}","Raba","Raba",{hydro_year},{hydro_month},{day},'
            f"{100 + code + day},{code}.{day},5.5,{archive.month}\n"
            for code in range(60)
            for day in range(1, 29)
        )
        put_csv(root, archive, f"{Path(archive.server_path).stem}.csv", rows)
    monkeypatch.setattr(series_module, "_SPILL_ROWS", 500)
    traced: list[int] = []
    # Only blocks allocated by imgwtools code: interpreter-wide tables (e.g. the
    # interned-string dict pathlib grows) may resize at any point of a long run.
    ours = [tracemalloc.Filter(True, "*/imgwtools/*")]

    def progress(event):
        if event.unit == "archive":
            snapshot = tracemalloc.take_snapshot().filter_traces(ours)
            traced.append(sum(stat.size for stat in snapshot.statistics("filename")))

    tracemalloc.start()
    try:
        report = build_series(root, dataset=HYDRO, on_progress=progress)
    finally:
        tracemalloc.stop()
    assert report.status == "created" and report.stations == 60
    assert len(traced) == 12
    assert max(traced[1:]) - traced[1] < 512 * 1024
    table = station_table(report, "149190059")
    assert table.num_rows == 362  # 2021-01-01 .. 2021-12-28 (days 29-31 missing)
    assert table["H_value"][0].as_py() == 160.0


def test_second_build_is_reused_without_parquet_writer(root, monkeypatch):
    store_archives(root, HYDRO, [2023, 2024])
    first = build_series(root, dataset=HYDRO)

    def refuse(*args, **kwargs):
        raise AssertionError("writer Parquet nie może zostać otwarty")

    monkeypatch.setattr(pq, "write_table", refuse)
    monkeypatch.setattr(pq, "ParquetWriter", refuse)
    again = build_series(root, dataset=HYDRO)
    assert (
        again.status == "reused"
        and again.version == first.version
        and again.stations == first.stations
    )

    # Relabeling an archive (same bytes, new HTTP signal) keeps the input manifest.
    relabeled = store_archives(
        root, HYDRO, [2024], signal=('"v2"', "Sun, 18 Oct 2026 12:00:00 GMT")
    )
    assert [entry.status for entry in relabeled] == ["relabeled"]
    assert build_series(root, dataset=HYDRO).status == "reused"
    assert check_series(root, dataset=HYDRO).series_state == {"hydro_daily": "current"}
    assert len(series_versions(root)) == 1


def test_cancel_and_broken_input_publish_no_version(root):
    store_archives(root, HYDRO, [2023, 2024])
    calls = iter([False, False, True])
    assert (
        build_series(root, dataset=HYDRO, cancel=lambda: next(calls, True)).status
        == "cancelled"
    )
    station_calls = iter([False, False, False, False, True])
    progress = []
    late = build_series(
        root,
        dataset=HYDRO,
        cancel=lambda: next(station_calls, True),
        on_progress=progress.append,
    )
    assert late.status == "cancelled"
    assert [event.unit for event in progress].count("station") == 1
    assert series_versions(root) == []
    assert not any((root / ".incoming").iterdir())

    current = check_series(root, dataset=HYDRO).items[-1]
    (root / current.local_path).write_bytes(b"uszkodzone")
    notices = []
    failed = build_series(root, dataset=HYDRO, on_notice=notices.append)
    assert failed.status == "failed" and "Suma kontrolna" in failed.problems[0]
    assert failed.version is None
    assert [notice.code for notice in notices] == ["archive_failed"]
    assert series_versions(root) == []


def put_2024(root, content, etag, day):
    """Store ``codz_2024.zip`` bytes under a Last-Modified of 2026-10-``day``."""
    archive = archive_files(HYDRO, years=[2024])[0]
    modified = format_datetime(datetime(2026, 10, day, 12, tzinfo=UTC), usegmt=True)
    response = DownloadResult(content, archive.url, etag, modified, len(content))
    return write_archive(root, archive=archive, response=response)


ORIGINAL_2024 = (
    FIXTURES / "archives" / archive_files(HYDRO, years=[2024])[0].server_path
).read_bytes()
CHANGED_2024 = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()


def test_reverted_input_builds_new_current_series_instead_of_reusing_old(root):
    put_2024(root, ORIGINAL_2024, '"v1"', 17)
    first = build_series(root, dataset=HYDRO)
    put_2024(root, CHANGED_2024, '"v2"', 19)
    second = build_series(root, dataset=HYDRO)
    # IMGW republishes the earlier bytes under a new Last-Modified: a relabeled copy
    # whose input manifest equals the one of the first, now superseded, series.
    assert put_2024(root, ORIGINAL_2024, '"v3"', 30).status == "relabeled"
    third = build_series(root, dataset=HYDRO)
    assert (first.status, second.status, third.status) == ("created",) * 3
    assert third.version not in (first.version, second.version)
    assert third.version.read_bytes() == first.version.read_bytes()
    assert third.version.parent.name.startswith("2026-10-30_")
    assert (
        current_version(root, slot="series:pl.imgw.hydro_daily").version
        == third.version
    )
    assert check_series(root, dataset=HYDRO).series_state == {"hydro_daily": "current"}
    again = build_series(root, dataset=HYDRO)
    assert (again.status, again.version) == ("reused", third.version)


def test_alternating_input_under_dominating_label_keeps_series_current(root):
    # The 2023 archive's later Last-Modified labels every build, so reverted inputs
    # produce identical series.json under an already taken directory name.
    store_archives(root, HYDRO, [2023], signal=('"x"', "Tue, 01 Dec 2026 12:00:00 GMT"))
    put_2024(root, ORIGINAL_2024, '"e0"', 17)
    built = [build_series(root, dataset=HYDRO).version]
    for step in range(1, 5):
        put_2024(root, (ORIGINAL_2024, CHANGED_2024)[step % 2], f'"e{step}"', 17 + step)
        report = build_series(root, dataset=HYDRO)
        assert report.status == "created" and report.version not in built
        built.append(report.version)
        assert (
            current_version(root, slot="series:pl.imgw.hydro_daily").version
            == report.version
        )
        assert check_series(root, dataset=HYDRO).series_state == {
            "hydro_daily": "current"
        }
    assert {version.parent.name[:10] for version in built} == {"2026-12-01"}
    assert built[4].read_bytes() == built[2].read_bytes() == built[0].read_bytes()


def test_parsed_records_are_released_while_building(root):
    store_archives(root, HYDRO, [2023, 2024])
    alive = []

    def progress(event):
        if event.unit == "archive" and event.status == "parsed":
            gc.collect()
            alive.append(
                sum(isinstance(item, NormalizedRecord) for item in gc.get_objects())
            )

    assert build_series(root, dataset=HYDRO, on_progress=progress).status == "created"
    # Records are folded into per-station values as they are parsed; at most the
    # last one is still referenced, so memory never holds the dataset twice.
    assert len(alive) == 2 and max(alive) <= 1


def test_shared_measurements_keep_the_sign_of_zero(root):
    rows = "".join(
        f'"{code}","Raba","Raba",2024,2,1,152,1.5,{temperature},12\n'
        for code, temperature in (
            ("149190310", "-0.0"),
            ("149190311", "0.0"),
            ("149190312", "-0.0"),
        )
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("codz_2024.csv", rows.encode("cp1250"))
    put_2024(root, buffer.getvalue(), '"z"', 17)
    report = build_series(root, dataset=HYDRO)
    signs = {
        code: math.copysign(1.0, station_table(report, code)["T_value"][0].as_py())
        for code in ("149190310", "149190311", "149190312")
    }
    assert signs == {"149190310": -1.0, "149190311": 1.0, "149190312": -1.0}


def test_validation_and_missing_pyarrow(root, monkeypatch):
    with pytest.raises(IMGWValidationError):
        build_series(root, dataset="pl.imgw.hydro_stations")
    assert build_series(root, dataset=HYDRO).status == "failed"
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    with pytest.raises(
        IMGWStoreDependencyError, match=r"pip install imgwtools\[store\]"
    ):
        build_series(root, dataset=HYDRO)


def test_core_and_store_modules_import_without_pyarrow():
    script = (
        "import sys; sys.modules['pyarrow'] = None; sys.modules['pyarrow.parquet'] = None\n"
        "import imgwtools, imgwtools.store.series, imgwtools.store.sync\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    clean = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, imgwtools.store.series, imgwtools.store.sync; print('pyarrow' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert clean.stdout.strip() == "False"
