"""Export and reading of ČHMÚ series and archives (spec 2026-10-18 §6.5, §8).

Meteo exports carry ``<V>_quality`` and ``<V>_source_flag``, every export the
ČHMÚ attribution (source and processed form) and the ČHMÚ license notice.
Synthetic §13.2 fixture files only.
"""

import csv
import json
from datetime import date

import pytest

from imgwtools.models import Measurement
from imgwtools.store import (
    build_series,
    export_archive,
    export_series,
    init_store,
    read_series,
)
from tests.unit.test_store_series_chmi import store_hydro, store_meteo
from tests.unit.test_store_sync_chmi import FULL, H1_2023, H1_2024, HYDRO, METEO, S1

SOURCE = (
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, "
    "licencja CC BY 4.0"
)
PROCESSED = "Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)"
TERMS = (
    f"{SOURCE}. {PROCESSED}. The CC BY 4.0 licence permits copying, changes and "
    "commercial use provided that the author ČHMÚ is credited, the licence is given "
    "and the changes are marked."
)
METEO_VARIABLES = ("P", "Tmean", "Tmax", "Tmin")


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


def table(lines):
    """Header and data rows of exported CSV lines."""
    rows = list(csv.reader("".join(lines).splitlines()))
    return rows[0], rows[1:]


def test_meteo_series_export_has_quality_columns_and_the_chmi_attribution(root):
    store_meteo(root)
    version = build_series(root, dataset=METEO).version
    notices = []

    header, rows = table(export_series(version, station=FULL, on_notice=notices.append))

    assert header == [
        "date",
        "year",
        *(
            column
            for name, unit in zip(
                METEO_VARIABLES, ("mm", "degC", "degC", "degC"), strict=True
            )
            for column in (
                f"{name} [{unit}]",
                f"{name}_flag",
                f"{name}_quality",
                f"{name}_source_flag",
            )
        ),
        "attribution_source",
        "attribution_processed",
    ]
    assert [(notice.code, notice.text) for notice in notices] == [
        ("license_terms", TERMS)
    ]
    by_day = {row[0]: row for row in rows}
    assert rows[0][-2:] == [SOURCE, PROCESSED]
    assert all(row[-2:] == ["", ""] for row in rows[1:])
    assert rows[0][:6] == ["2023-10-20", "2023", "0.0", "no_phenomenon", "0", ""]
    assert by_day["2023-10-22"][2:6] == ["0.0", "value", "0", "T"]
    assert by_day["2023-10-26"][2:6] == ["", "missing", "4", ""]
    # Days of the Tmax block without rows: no value, quality or source flag.
    assert by_day["2023-10-30"][10:14] == ["", "missing", "", ""]
    # ČHMÚ series are calendar; the hydrological year starts on 1 XI.
    assert by_day["2023-11-01"][1] == "2023"
    _, hydrological = table(
        export_series(version, station=FULL, year_type="hydrological", variables=["P"])
    )
    assert [
        row[:2] for row in hydrological if row[0] in ("2023-10-31", "2023-11-01")
    ] == [
        ["2023-10-31", "2023"],
        ["2023-11-01", "2024"],
    ]

    records = {item.date: item for item in read_series(version, station=FULL)}
    assert records[date(2023, 10, 22)].measurements["P"] == Measurement(
        0.0, "value", 0, "T"
    )
    assert records[date(2023, 10, 25)].measurements["P"] == Measurement(
        0.7, "value", 1, None
    )


def test_hydro_series_export_has_no_quality_columns_in_both_year_types(root):
    store_hydro(root, H1_2023, H1_2024)
    version = build_series(root, dataset=HYDRO).version
    window = {"start": date(2023, 10, 31), "end": date(2023, 11, 1)}

    header, calendar = table(
        export_series(version, station=S1, variables=["H", "Q"], **window)
    )
    _, hydrological = table(
        export_series(
            version,
            station=S1,
            variables=["H", "Q"],
            year_type="hydrological",
            **window,
        )
    )

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
    assert [row[:2] for row in calendar] == [
        ["2023-10-31", "2023"],
        ["2023-11-01", "2023"],
    ]
    assert [row[:2] for row in hydrological] == [
        ["2023-10-31", "2023"],
        ["2023-11-01", "2024"],
    ]
    assert calendar[0][-2:] == [SOURCE, PROCESSED]
    assert all(
        measurement.quality is None and measurement.source_flag is None
        for item in read_series(version, station=S1)
        for measurement in item.measurements.values()
    )


def test_meteo_archive_export_adds_quality_and_source_flag(root):
    sra = next(
        item for item in store_meteo(root) if item.path.name.endswith(f"{FULL}-SRA.csv")
    )
    notices = []

    header, rows = table(export_archive(sra.path, on_notice=notices.append))
    objects = [json.loads(line) for line in export_archive(sra.path, format="jsonl")]

    assert header == [
        "station_code",
        "dataset",
        "date",
        "hydro_year",
        "period",
        *(
            f"{name}{suffix}"
            for name, unit in zip(
                METEO_VARIABLES, ("mm", "degC", "degC", "degC"), strict=True
            )
            for suffix in (f" [{unit}]", "_flag", "_quality", "_source_flag")
        ),
    ]
    by_day = {row[2]: row for row in rows}
    assert by_day["2023-10-22"] == [
        FULL,
        METEO,
        "2023-10-22",
        "2023",
        "",
        "0.0",
        "value",
        "0",
        "T",
        *[""] * 12,
    ]
    assert by_day["2023-11-01"][3] == "2024"
    assert [(notice.code, notice.text) for notice in notices] == [
        ("license_terms", TERMS)
    ]
    assert objects[2]["measurements"] == {
        "P": {"value": 0.0, "flag": "value", "quality": 0, "source_flag": "T"}
    }
    assert objects[6]["measurements"]["P"] == {
        "value": None,
        "flag": "missing",
        "quality": 4,
        "source_flag": None,
    }


def test_hydro_archive_export_keeps_value_and_flag_only(root):
    (version,) = store_hydro(root, H1_2023)
    notices = []

    header, rows = table(export_archive(version.path, on_notice=notices.append))
    objects = [
        json.loads(line) for line in export_archive(version.path, format="jsonl")
    ]

    assert header == [
        "station_code",
        "dataset",
        "date",
        "hydro_year",
        "period",
        "H [cm]",
        "H_flag",
        "Q [m3/s]",
        "Q_flag",
        "T [degC]",
        "T_flag",
    ]
    assert len(rows) == 365 and rows[0][:5] == [S1, HYDRO, "2023-01-01", "2023", ""]
    assert all(
        set(value) == {"value", "flag"}
        for item in objects
        for value in item["measurements"].values()
    )
    assert [(notice.code, notice.text) for notice in notices] == [
        ("license_terms", TERMS)
    ]
