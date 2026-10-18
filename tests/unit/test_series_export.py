"""CSV export of one station series: header, formulas, flags, year type and atomic replacement."""

import csv
import io
import os
import stat
import zipfile
from datetime import date
from pathlib import Path

import pytest

import imgwtools.store.export as export_module
from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.fetch import DownloadResult
from imgwtools.store import (
    build_series,
    export_series,
    init_store,
    read_series_index,
    write_archive,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
DAILY = "pl.imgw.hydro_daily"
METEO = "pl.imgw.meteo_precip_daily"
HALF = "pl.imgw.hydro_semiannual"
MONTHLY = "pl.imgw.hydro_monthly"
STATION = "149190310"
METEO_STATION = "123750000"
SOURCE = "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy"
PROCESSED = "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone"


def zipped(name, lines):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "\n".join(lines).encode("cp1250"))
    return buffer.getvalue()


def store(root, dataset, years, months=None, *, content=None):
    for archive in archive_files(dataset, years=years, months=months):
        data = content[archive.server_path] if content else None
        if data is None:
            source = FIXTURES / archive.server_path
            if not source.exists():
                continue
            data = source.read_bytes()
        write_archive(
            root,
            archive=archive,
            response=DownloadResult(data, archive.url, None, None, len(data)),
        )
    return build_series(root, dataset=dataset).version


def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


@pytest.fixture
def hydro_year(root):
    """Hydrological year 2024 (2023-11-01..2024-10-31) with values only at both ends."""
    data = zipped(
        "codz_2024.csv",
        [
            f"{STATION},Raba Górna,Raba,2024,1,1,150,2.5,4.0,11",
            f"{STATION},Raba Górna,Raba,2024,12,31,160,99999.999,99.9,10",
        ],
    )
    return store(
        root,
        DAILY,
        [2024],
        content={"dane_hydrologiczne/dobowe/2024/codz_2024.zip": data},
    )


@pytest.fixture
def meteo(root):
    """January 2001 from fixtures plus 31 Oct and 1 Nov 2001 across the hydrological boundary."""
    content = {
        "dane_meteorologiczne/dobowe/opad/2001/2001_01_o.zip": None,
        "dane_meteorologiczne/dobowe/opad/2001/2001_10_o.zip": zipped(
            "o_d_2001_10.csv",
            [f"{METEO_STATION},Warszawa,2001,10,31,1.5,,S,0,9,0,9,,9,,9"],
        ),
        "dane_meteorologiczne/dobowe/opad/2001/2001_11_o.zip": zipped(
            "o_d_2001_11.csv",
            [f"{METEO_STATION},Warszawa,2001,11,1,2.5,,S,0,9,0,9,,9,,9"],
        ),
    }
    return store(root, METEO, [2001], [1, 10, 11], content=content)


def test_csv_has_units_header_formulas_once_and_every_day(hydro_year, tmp_path):
    progress, notices = [], []
    target = export_series(
        hydro_year,
        station=STATION,
        path=tmp_path / "raba.csv",
        variables=["H", "Q", "H"],
        on_progress=progress.append,
        on_notice=notices.append,
    )
    assert target == tmp_path / "raba.csv"
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"#" not in raw
    header, data = rows(target)
    assert header == [
        "date",
        "year",
        "H [cm]",
        "H_flag",
        "Q [m3/s]",
        "Q_flag",
        "attribution_source",
        "attribution_processed",
    ]
    assert len(data) == 366 == read_series_index(hydro_year).stations[STATION].rows
    assert [row["date"] for row in data] == [
        date.fromordinal(date(2023, 11, 1).toordinal() + offset).isoformat()
        for offset in range(366)
    ]
    assert (data[0]["attribution_source"], data[0]["attribution_processed"]) == (
        SOURCE,
        PROCESSED,
    )
    assert all(
        row["attribution_source"] == row["attribution_processed"] == ""
        for row in data[1:]
    )
    assert (
        data[0]["H [cm]"],
        data[0]["H_flag"],
        data[0]["Q [m3/s]"],
        data[0]["Q_flag"],
    ) == ("150.0", "value", "2.5", "value")
    assert (data[1]["H [cm]"], data[1]["H_flag"]) == ("", "missing")
    assert (data[-1]["H [cm]"], data[-1]["Q [m3/s]"], data[-1]["Q_flag"]) == (
        "160.0",
        "",
        "missing",
    )
    assert {row["year"] for row in data} == {"2024"}
    assert progress[-1].current == progress[-1].total == 366
    assert [
        (notice.code, SOURCE in notice.text and PROCESSED in notice.text)
        for notice in notices
    ] == [("license_terms", True)]


def test_explicit_year_type_switches_at_november_for_hydro(hydro_year, tmp_path):
    _, data = rows(
        export_series(
            hydro_year,
            station=STATION,
            path=tmp_path / "c.csv",
            variables=["H"],
            year_type="calendar",
        )
    )
    years = {row["date"]: row["year"] for row in data}
    assert (
        years["2023-11-01"],
        years["2023-12-31"],
        years["2024-01-01"],
        years["2024-10-31"],
    ) == ("2023", "2023", "2024", "2024")
    _, data = rows(
        export_series(
            hydro_year,
            station=STATION,
            path=tmp_path / "h.csv",
            variables=["H"],
            year_type="hydrological",
        )
    )
    assert {row["year"] for row in data} == {"2024"}


def test_meteo_defaults_to_calendar_and_keeps_zero_and_accumulated_flags(
    meteo, tmp_path
):
    assert read_series_index(meteo).year_type == "calendar"
    header, data = rows(
        export_series(
            meteo, station=METEO_STATION, path=tmp_path / "p.csv", variables=["P"]
        )
    )
    assert header == [
        "date",
        "year",
        "P [mm]",
        "P_flag",
        "attribution_source",
        "attribution_processed",
    ]
    by_date = {row["date"]: row for row in data}
    assert [
        (by_date[day]["P [mm]"], by_date[day]["P_flag"])
        for day in ("2001-01-01", "2001-01-02", "2001-01-03")
    ] == [
        ("", "missing"),
        ("9.2", "accumulated"),
        ("0.0", "no_phenomenon"),
    ]
    assert (by_date["2001-10-31"]["year"], by_date["2001-11-01"]["year"]) == (
        "2001",
        "2001",
    )
    assert by_date["2001-11-01"]["P [mm]"] == "2.5"
    _, data = rows(
        export_series(
            meteo,
            station=METEO_STATION,
            path=tmp_path / "h.csv",
            variables=["P"],
            year_type="hydrological",
        )
    )
    by_date = {row["date"]: row["year"] for row in data}
    assert (by_date["2001-01-01"], by_date["2001-10-31"], by_date["2001-11-01"]) == (
        "2001",
        "2001",
        "2002",
    )


def test_half_year_has_period_and_extrema_columns_and_rejects_calendar(root, tmp_path):
    version = store(root, HALF, [2024])
    with pytest.raises(IMGWValidationError, match="hydrologiczne"):
        export_series(
            version,
            station=STATION,
            path=tmp_path / "x.csv",
            variables=["H_max"],
            year_type="calendar",
        )
    assert not (tmp_path / "x.csv").exists()
    header, data = rows(
        export_series(
            version, station=STATION, path=tmp_path / "half.csv", variables=["H_max"]
        )
    )
    assert header == [
        "date",
        "year",
        "period",
        "H_max [cm]",
        "H_max_flag",
        "H_max_start",
        "H_max_end",
        "attribution_source",
        "attribution_processed",
    ]
    assert {row["period"] for row in data} == {"winter", "summer", "annual"}
    assert {row["year"] for row in data} == {"2024"}
    assert any(row["H_max_start"] for row in data if row["H_max_flag"] == "value")


def test_monthly_has_no_period_column(root, tmp_path):
    version = store(root, MONTHLY, [2024])
    header, data = rows(
        export_series(
            version, station=STATION, path=tmp_path / "m.csv", variables=["H_mean"]
        )
    )
    assert header == [
        "date",
        "year",
        "H_mean [cm]",
        "H_mean_flag",
        "attribution_source",
        "attribution_processed",
    ]
    assert data and all(row["date"].endswith("-01") for row in data)


@pytest.mark.parametrize(
    "options, match",
    [
        ({"format": "xlsx"}, "format"),
        ({"year_type": "fiscal"}, "year_type"),
        ({"variables": "H"}, "listą"),
        ({"variables": ["X"]}, "Nieznane zmienne"),
        ({"variables": []}, "Nieznane zmienne"),
        ({"station": "123456789"}, "nie występuje"),
    ],
)
def test_invalid_options_are_rejected_without_writing(
    hydro_year, tmp_path, options, match
):
    arguments = {
        "station": STATION,
        "path": tmp_path / "out.csv",
        "variables": ["H"],
        **options,
    }
    with pytest.raises(IMGWValidationError, match=match):
        export_series(hydro_year, **arguments)
    assert list(tmp_path.iterdir()) == [tmp_path / "store"]


def test_target_must_be_a_file_in_existing_directory(hydro_year, tmp_path):
    with pytest.raises(IMGWValidationError, match="katalog"):
        export_series(hydro_year, station=STATION, path=tmp_path, variables=["H"])
    with pytest.raises(IMGWValidationError, match="nie istnieje"):
        export_series(
            hydro_year,
            station=STATION,
            path=tmp_path / "missing" / "out.csv",
            variables=["H"],
        )


def test_empty_series_is_rejected(hydro_year, tmp_path, monkeypatch):
    monkeypatch.setattr(export_module, "read_series", lambda *args, **kwargs: iter(()))
    with pytest.raises(IMGWDataError, match="pusty"):
        export_series(
            hydro_year, station=STATION, path=tmp_path / "out.csv", variables=["H"]
        )
    assert not (tmp_path / "out.csv").exists()


def test_cancel_or_failure_leaves_previous_export_untouched(
    hydro_year, tmp_path, monkeypatch
):
    target = export_series(
        hydro_year, station=STATION, path=tmp_path / "out.csv", variables=["H"]
    )
    before = target.read_bytes()

    calls = []

    def cancel_on_second_check():
        calls.append(None)
        return len(calls) >= 2

    for cancel in (lambda: True, cancel_on_second_check):
        with pytest.raises(IMGWStoreError, match="Anulowano"):
            export_series(
                hydro_year,
                station=STATION,
                path=target,
                variables=["H", "Q"],
                cancel=cancel,
            )
        assert target.read_bytes() == before
    assert len(calls) == 2

    def broken_replace(source, destination):
        raise OSError("dysk pełny")

    monkeypatch.setattr(export_module.os, "replace", broken_replace)
    with pytest.raises(OSError, match="dysk"):
        export_series(hydro_year, station=STATION, path=target, variables=["H", "Q"])
    assert target.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out.csv", "store"]


def test_exported_file_mode_follows_umask(hydro_year, tmp_path):
    previous = os.umask(0o022)
    try:
        target = export_series(
            hydro_year, station=STATION, path=tmp_path / "out.csv", variables=["H"]
        )
    finally:
        os.umask(previous)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
