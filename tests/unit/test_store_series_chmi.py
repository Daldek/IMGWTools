"""build_series of ČHMÚ per-station files: known periods, meteo fields, reuse.

Spec 2026-10-18 §6.1-§6.3 (calendar, per-station periods, Parquet columns and
``series.json``) and the §13.2 scenarios (1)-(3) and (8) of ``sync_store``
with ``series=True``, replayed from ``chmi_recordings.json`` with respx.
Synthetic files only; codes 0-203-1-9… and 0-203-0-9… are not published by
ČHMÚ.
"""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import respx

from imgwtools.datasets import ArchiveFile, archive_files, get_dataset
from imgwtools.fetch import DownloadResult
from imgwtools.store import current_version, init_store, write_archive
from imgwtools.store.series import build_series, check_series
from imgwtools.store.sync import check_store, sync_store
from tests.unit.test_store_sync_chmi import (
    CASES,
    FIRST,
    FULL,
    H1_2023,
    H1_2024,
    H2_2004,
    H2_2006,
    HYDRO,
    METEO,
    RAIN,
    S1,
    S2,
    payload,
    serve,
    store,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ELEMENTS = ("SRA", "T", "TMA", "TMI")
HYDRO_GETS = {
    H1_2023: "h900001_2023_get",
    H1_2024: "h900001_2024_get",
    H2_2004: "h900002_2004_get",
    H2_2006: "h900002_2006_get",
}


def _meteo_get(archive: ArchiveFile) -> str:
    code = archive.station_code
    assert code is not None
    return f"m{code.rsplit('-', 1)[1]}_{archive.param}_get"


# Station 90001 has every element, 90000000002 only precipitation.
METEO_GETS = {
    archive: _meteo_get(archive)
    for archive in archive_files(METEO, stations=[FULL, RAIN])
    if archive.station_code == FULL or archive.param == "SRA"
}
CHMI_ATTRIBUTION = (
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, "
    "licencja CC BY 4.0. Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)"
)
CHMI_LICENSE = {
    "id": "CC-BY-4.0",
    "attribution": CHMI_ATTRIBUTION,
    "url": "https://creativecommons.org/licenses/by/4.0/",
    "terms_url": "https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti",
}
# Spec 2026-10-18 §6.3 verbatim; its Parquet SHA-256 is a placeholder.
EXAMPLE_900002 = (
    '{"schema":"imgw-series/1","dataset":"cz.chmi.hydro_daily","year_type":"calendar",'
    '"periods":[["2004-01-01","2004-12-31"],["2006-01-01","2006-12-31"]],"stations":'
    '{"0-203-1-900002":{"file":"stations/0-203-1-900002.parquet","sha256":'
    '"0000000000000000000000000000000000000000000000000000000000000000","rows":1096,'
    '"periods":[["2004-01-01","2004-12-31"],["2006-01-01","2006-12-31"]],"variables":'
    '{"H":{"unit":"cm","first":"2004-11-01","last":"2006-12-31","with_value":426,'
    '"accumulated":0,"gaps":[]},"Q":{"unit":"m3/s","first":"2004-01-01","last":'
    '"2006-12-31","with_value":731,"accumulated":0,"gaps":[]},"T":{"unit":"degC",'
    '"first":null,"last":null,"with_value":0,"accumulated":0,"gaps":[]}}}}}'
)


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as router:
        yield router


def store_hydro(root, *archives):
    return [store(root, archive, HYDRO_GETS[archive]) for archive in archives]


def store_meteo(root):
    return [store(root, archive, case) for archive, case in METEO_GETS.items()]


def index_of(report):
    return json.loads(report.version.read_text(encoding="utf-8"))


def sidecar_of(report):
    return json.loads(
        (report.version.parent / "series.json.meta.json").read_text(encoding="utf-8")
    )


def station_table(report, code):
    return pq.read_table(report.version.parent / "stations" / f"{code}.parquet")


def series_versions(root, slug):
    base = root / "series" / "versions" / slug
    return sorted(path.name for path in base.iterdir()) if base.exists() else []


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
    }


def test_station_with_an_unpublished_year_matches_the_spec_example(root):
    inputs = store_hydro(root, H2_2004, H2_2006)
    notices = []

    report = build_series(root, dataset=HYDRO, on_notice=notices.append)

    assert (report.status, report.stations, report.problems) == ("new", 1, ())
    version = report.version.parent
    assert version.parent == root / "series" / "versions" / "chmi_hydro_daily"
    parquet = version / "stations" / f"{S2}.parquet"
    digest = hashlib.sha256(parquet.read_bytes()).hexdigest()
    assert index_of(report) == json.loads(EXAMPLE_900002.replace("0" * 64, digest))
    # 2005 has no file: its days are rows without values, unknown rather than gaps.
    rows = {row["date"]: row for row in station_table(report, S2).to_pylist()}
    assert list(rows) == [date(2004, 1, 1) + timedelta(days=n) for n in range(1096)]
    assert {
        (row["H_flag"], row["Q_flag"], row["T_flag"])
        for day, row in rows.items()
        if day.year == 2005
    } == {("missing", "missing", "missing")}
    assert (
        rows[date(2004, 10, 31)]["H_value"],
        rows[date(2004, 11, 1)]["H_value"],
    ) == (
        None,
        49.0,
    )

    meta = sidecar_of(report)
    assert (meta["dataset"], meta["country"], meta["provider"]) == (HYDRO, "CZ", "CHMI")
    assert meta["request"] == {"dataset": HYDRO}
    assert meta["license"] == CHMI_LICENSE
    assert meta["extra"]["version"] == {"label": "2025-07-01", "label_source": "inputs"}
    # Inputs with a canonical form carry the content sum of their own sidecars.
    assert meta["extra"]["source_files"] == [
        {
            "name": item.path.name,
            "file": item.path.relative_to(root).as_posix(),
            "sha256": item.sha256,
            "label": item.label,
            "content_sha256": inputs_meta["content_sha256"],
            "content_form": "chmi-json/1",
        }
        for item in inputs
        for inputs_meta in [
            json.loads(Path(f"{item.path}.meta.json").read_text(encoding="utf-8"))
        ]
    ]
    provider_notice = (
        "The CC BY 4.0 licence permits copying, changes and commercial use provided "
        "that the author ČHMÚ is credited, the licence is given and the changes are "
        "marked."
    )
    assert [(notice.code, notice.text) for notice in notices] == [
        ("license_terms", f"{CHMI_ATTRIBUTION}. {provider_notice}")
    ]


def test_hydro_calendar_covers_leap_day_one_missing_row_and_november(root):
    store_hydro(root, H1_2023, H1_2024, H2_2004, H2_2006)

    report = build_series(root, dataset=HYDRO)

    assert (report.status, report.stations) == ("new", 2)
    index = index_of(report)
    assert index["periods"] == [
        ["2004-01-01", "2004-12-31"],
        ["2006-01-01", "2006-12-31"],
        ["2023-01-01", "2024-12-31"],
    ]
    station = index["stations"][S1]
    assert station["periods"] == [["2023-01-01", "2024-12-31"]]
    assert station["rows"] == 731
    # 2024-06-15 has no row in the file: a one-day gap of H and Q, never a value.
    assert {name: entry["gaps"] for name, entry in station["variables"].items()} == {
        "H": [["2024-06-15", "2024-06-15"]],
        "Q": [["2024-06-15", "2024-06-15"]],
        "T": [],
    }
    assert {
        name: (entry["first"], entry["last"], entry["with_value"], entry["accumulated"])
        for name, entry in station["variables"].items()
    } == {
        "H": ("2023-01-01", "2024-12-31", 730, 0),
        "Q": ("2023-01-01", "2024-12-31", 730, 0),
        "T": ("2023-10-01", "2023-11-30", 61, 0),
    }

    table = station_table(report, S1)
    assert table.column_names == [
        "date",
        "hydro_year",
        "H_value",
        "H_flag",
        "Q_value",
        "Q_flag",
        "T_value",
        "T_flag",
    ]
    metadata = table.schema.metadata
    assert json.loads(metadata[b"units"]) == {"H": "cm", "Q": "m3/s", "T": "degC"}
    assert json.loads(metadata[b"variable_notes"]) == dict(
        get_dataset(HYDRO).variable_notes
    )
    rows = {row["date"]: row for row in table.to_pylist()}
    assert rows[date(2024, 2, 29)]["H_flag"] == "value"
    assert (rows[date(2024, 6, 15)]["H_value"], rows[date(2024, 6, 15)]["H_flag"]) == (
        None,
        "missing",
    )
    assert [
        rows[date(2023, 10, 31)]["hydro_year"],
        rows[date(2023, 11, 1)]["hydro_year"],
    ] == [
        2023,
        2024,
    ]
    assert rows[date(2024, 11, 1)]["hydro_year"] == 2025


def test_meteo_series_keeps_quality_and_source_flags_with_element_periods(root):
    store_meteo(root)

    report = build_series(root, dataset=METEO)

    assert (report.status, report.stations) == ("new", 2)
    index = index_of(report)
    assert index["year_type"] == "calendar"
    assert index["periods"] == [["2023-10-20", "2023-11-19"]]
    full, rain = index["stations"][FULL], index["stations"][RAIN]
    assert full["periods"] == [["2023-10-20", "2023-11-19"]]
    assert rain["periods"] == [["2023-10-20", "2023-10-31"]]
    # The TMA block without rows is a gap; an explicit missing row is a gap too.
    assert {name: entry["gaps"] for name, entry in full["variables"].items()} == {
        "P": [["2023-10-26", "2023-10-26"]],
        "Tmean": [],
        "Tmax": [["2023-10-30", "2023-11-07"]],
        "Tmin": [["2023-11-05", "2023-11-05"]],
    }
    assert {name: entry["with_value"] for name, entry in full["variables"].items()} == {
        "P": 30,
        "Tmean": 31,
        "Tmax": 22,
        "Tmin": 30,
    }
    assert {entry["accumulated"] for entry in full["variables"].values()} == {0}
    assert (rain["rows"], rain["variables"]["Tmax"]["first"]) == (12, None)

    table = station_table(report, FULL)
    assert table.column_names == [
        "date",
        "hydro_year",
        *(
            f"{name}_{column}"
            for name in ("P", "Tmean", "Tmax", "Tmin")
            for column in ("value", "flag", "quality", "source_flag")
        ),
    ]
    assert table.schema.field("P_quality").type == pa.int8()
    source_flag = table.schema.field("P_source_flag").type
    assert pa.types.is_dictionary(source_flag) and source_flag.value_type == pa.string()
    rows = {row["date"]: row for row in table.to_pylist()}

    def cells(day, name="P"):
        row = rows[date(2023, 10, day)]
        return tuple(
            row[f"{name}_{column}"]
            for column in ("value", "flag", "quality", "source_flag")
        )

    assert cells(20) == (0.0, "no_phenomenon", 0, None)
    assert cells(22) == (0.0, "value", 0, "T")
    assert cells(23) == (12.3, "value", 0, "M")
    assert (cells(24)[2], cells(25)[2]) == (3, 1)
    assert cells(26) == (None, "missing", 4, None)
    assert cells(27) == (1.5, "value", 0, "R")
    # Days of the TMA block without rows carry neither quality nor a source flag.
    assert cells(30, "Tmax") == (None, "missing", None, None)
    assert json.loads(table.schema.metadata[b"variable_notes"]) == dict(
        get_dataset(METEO).variable_notes
    )

    meta = sidecar_of(report)
    assert (meta["country"], meta["provider"], meta["license"]) == (
        "CZ",
        "CHMI",
        CHMI_LICENSE,
    )
    assert len(meta["extra"]["source_files"]) == 5
    assert all(
        set(entry) == {"name", "file", "sha256", "label"}
        for entry in meta["extra"]["source_files"]
    )


def test_second_build_is_reused_without_writing(root):
    store_hydro(root, H1_2023, H2_2004)
    store_meteo(root)
    first = {dataset: build_series(root, dataset=dataset) for dataset in (HYDRO, METEO)}
    before = tree(root)

    again = {dataset: build_series(root, dataset=dataset) for dataset in (HYDRO, METEO)}

    assert tree(root) == before
    for dataset, report in again.items():
        assert (report.status, report.version, report.stations) == (
            "unchanged",
            first[dataset].version,
            first[dataset].stations,
        )
    plan = check_series(root, dataset=HYDRO)
    assert plan.series_state == {"chmi_hydro_daily": "current"}
    assert [(item.station_code, item.archive.year) for item in plan.items] == [
        (S1, 2023),
        (S2, 2004),
    ]


def test_quality_outside_the_parquet_range_fails_without_a_version(root):
    archive = next(item for item in METEO_GETS if item.station_code == RAIN)
    data = payload(CASES[METEO_GETS[archive]]).replace(b",0.0,\n", b",300.0,\n", 1)
    write_archive(
        root,
        archive=archive,
        response=DownloadResult(
            data, archive.url, '"x"', "Sun, 18 Oct 2026 05:30:12 GMT", len(data)
        ),
    )
    notices = []

    report = build_series(root, dataset=METEO, on_notice=notices.append)

    assert report.status == "failed" and "300" in report.problems[0]
    assert [notice.code for notice in notices] == ["archive_failed"]
    assert series_versions(root, "chmi_meteo_daily") == []


def test_sync_reuses_the_series_after_mass_republication(root, server):
    serve(
        server,
        "hydro_listing",
        *FIRST,
        *(
            f"h900002_{year}_{method}"
            for year in (2004, 2006)
            for method in ("head", "get")
        ),
    )
    first = sync_store(root, datasets=[HYDRO], stations=[S1, S2])
    assert [item.status for item in first.items] == ["new"] * 4
    (created,) = first.series
    assert (created.status, created.stations) == ("new", 2)
    names = ("h900001_2023", "h900001_2024", "h900002_2004", "h900002_2006")
    serve(
        server,
        "hydro_listing_republished",
        *(
            f"{name}_republished_{method}"
            for name in names
            for method in ("head", "get")
        ),
    )

    report = sync_store(root, datasets=[HYDRO], stations=[S1, S2])

    assert [item.status for item in report.items] == ["relabeled"] * 4
    # Same (slot, SHA-256) pairs: the series is reused, no version is added.
    (reused,) = report.series
    assert (reused.status, reused.version) == ("unchanged", created.version)
    assert series_versions(root, "chmi_hydro_daily") == [created.version.parent.name]
    plan = check_store(root, datasets=[HYDRO], stations=[S1, S2])
    assert plan.series_state == {"chmi_hydro_daily": "current"}


def test_sync_reuses_the_series_after_reserialization(root, server):
    serve(server, "hydro_listing", *FIRST)
    first = sync_store(root, datasets=[HYDRO], stations=[S1])
    (created,) = first.series
    assert created.status == "new"
    serve(
        server,
        "hydro_listing_reserialized",
        "h900001_2023_reserialized_head",
        "h900001_2023_reserialized_get",
    )
    notices = []

    report = sync_store(root, datasets=[HYDRO], stations=[S1], on_notice=notices.append)

    assert [item.status for item in report.items] == ["unchanged", "unchanged"]
    assert "content_unchanged" in {notice.code for notice in notices}
    (reused,) = report.series
    assert (reused.status, reused.version) == ("unchanged", created.version)
    assert series_versions(root, "chmi_hydro_daily") == [created.version.parent.name]


def test_sync_builds_a_new_series_version_after_a_correction(root, server):
    serve(server, "hydro_listing", *FIRST)
    (old,) = sync_store(root, datasets=[HYDRO], stations=[S1]).series
    old_bytes = old.version.read_bytes()
    serve(
        server,
        "hydro_listing_corrected",
        "h900001_2024_corrected_head",
        "h900001_2024_corrected_get",
    )

    report = sync_store(root, datasets=[HYDRO], stations=[S1])

    assert [item.status for item in report.items] == ["unchanged", "new"]
    (new,) = report.series
    assert new.status == "new" and new.version != old.version
    assert old.version.read_bytes() == old_bytes
    assert new.version.read_bytes() != old_bytes
    assert current_version(root, slot=f"series:{HYDRO}").version == new.version


def test_sync_of_meteo_builds_once_and_rebuilds_after_new_csv_bytes(root, server):
    serve(server, "precipitation_listing", "temperature_listing")
    serve(
        server,
        "m90000000002_SRA_head",
        "m90000000002_SRA_get",
        *(
            f"m90001_{element}_{method}"
            for element in ELEMENTS
            for method in ("head", "get")
        ),
    )
    first = sync_store(root, datasets=[METEO], stations=[FULL, RAIN])
    # Elements of station 90000000002 that are not published do not block it.
    assert [item.status for item in first.items] == [
        "new",
        *["unchanged"] * 3,
        *["new"] * 4,
    ]
    (created,) = first.series
    assert (created.status, created.stations) == ("new", 2)
    assert (
        sync_store(root, datasets=[METEO], stations=[FULL, RAIN]).series[0].status
        == "unchanged"
    )
    serve(
        server,
        "precipitation_listing_corrected",
        "m90001_SRA_corrected_head",
        "m90001_SRA_corrected_get",
    )

    report = sync_store(root, datasets=[METEO], stations=[FULL])

    (rebuilt,) = report.series
    assert rebuilt.status == "new" and rebuilt.version != created.version
    rows = {row["date"]: row for row in station_table(rebuilt, FULL).to_pylist()}
    assert rows[date(2023, 10, 21)]["P_value"] == 2.6


def test_imgw_series_keep_the_layout_of_3_0_0(root):
    for archive in archive_files("pl.imgw.hydro_daily", years=[2024], months=[1]):
        content = (FIXTURES / "archives" / archive.server_path).read_bytes()
        write_archive(
            root,
            archive=archive,
            response=DownloadResult(
                content,
                archive.url,
                '"v1"',
                "Sat, 17 Oct 2026 12:00:00 GMT",
                len(content),
            ),
        )
    notices = []

    report = build_series(root, dataset="pl.imgw.hydro_daily", on_notice=notices.append)

    assert report.status == "new"
    index = index_of(report)
    assert all(
        set(entry) == {"file", "sha256", "rows", "variables"}
        for entry in index["stations"].values()
    )
    table = station_table(report, next(iter(index["stations"])))
    assert set(table.schema.metadata) == {b"imgw_schema", b"dataset", b"units"}
    assert not any(
        name.endswith(("_quality", "_source_flag")) for name in table.column_names
    )
    meta = sidecar_of(report)
    attribution = (
        "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – "
        "Państwowy Instytut Badawczy. Dane Instytutu Meteorologii i Gospodarki Wodnej – "
        "Państwowego Instytutu Badawczego zostały przetworzone"
    )
    assert (meta["country"], meta["provider"], meta["license"]) == (
        "PL",
        "IMGW-PIB",
        {
            "id": "IMGW-PIB",
            "attribution": attribution,
            "url": "https://danepubliczne.imgw.pl/regulations",
        },
    )
    assert all(
        set(entry) == {"name", "file", "sha256", "label"}
        for entry in meta["extra"]["source_files"]
    )
    assert [notice.text for notice in notices] == [
        f"{attribution}. For private and research use; other uses require checking "
        "the IMGW-PIB terms, including the exceptions for high-value data."
    ]
