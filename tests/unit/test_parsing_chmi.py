"""ČHMÚ parsers (spec 2026-10-18 §4.1, §5): hydro JSON, meteo CSV, metadata, listings."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from imgwtools._parsing.chmi import (
    parse_listing,
    read_metadata,
    station_coordinates,
    station_rows,
)
from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.models import Measurement
from imgwtools.parsers import (
    normalize_archive,
    parse_chmi_hydro_daily,
    parse_chmi_meteo_daily,
    parse_chmi_stations,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVES = FIXTURES / "archives"
DAILY = "hydrology/historical/data/daily"
CSV_DAILY = "meteorology/climate/historical_csv/data/daily"
H2023 = "H_0-203-1-900001_DQ_2023.json"
H2024 = "H_0-203-1-900001_DQ_2024.json"


def fixture(path: str) -> bytes:
    return (ARCHIVES / path).read_bytes()


def by_date(records):
    return {record.date: record for record in records}


def hydro_file(*series, code="0-203-1-900001"):
    """Hydro daily JSON in the ČHMÚ layout from (tsConID, unit, rows) triples."""
    return json.dumps(
        {
            "objID": code,
            "tsList": [
                {
                    "tsConID": con,
                    "unit": unit,
                    "tsData": {
                        "type": "DataCollection",
                        "data": {"header": "DT,VAL", "values": rows},
                    },
                }
                for con, unit, rows in series
            ],
        },
        separators=(",", ":"),
    ).encode()


METEO_HEADER = "STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY,\n"
SRA_NAME = "dly-0-203-0-90001-SRA.csv"


def meteo_file(*rows: str, header: str = METEO_HEADER) -> bytes:
    return (header + "".join(row + "\n" for row in rows)).encode()


def sra(day: str, value: str = "0.0", flag: str = "", quality: str = "0.0") -> str:
    return f"0-203-0-90001,SRA,06:00,{day}T06:00Z,{value},{flag},{quality},"


def envelope(header: str, rows: str) -> bytes:
    """Metadata envelope with rows given as raw JSON (keeps number notation)."""
    return (
        '{"zaznamID":"0F0F","datovyZdrojID":"hydrologie",'
        '"datovyTokID":"Open.Data.Metadata","datumVytvoreni":"2026-10-18T17:00:03Z",'
        '"verzeDat":"1.0","data":{"type":"DataCollection","data":{"header":"'
        + header
        + '","values":['
        + rows
        + "]}}}"
    ).encode()


# --------------------------------------------------------------------------
# §5.1 hydro daily JSON
# --------------------------------------------------------------------------


def test_hydro_fixture_maps_series_to_variables_and_skips_suspended_solids():
    records = list(parse_chmi_hydro_daily(fixture(f"{DAILY}/{H2023}"), filename=H2023))
    days = by_date(records)

    assert len(records) == 365 and list(days) == sorted(days)
    first = records[0]
    assert (first.station_code, first.dataset, first.period) == (
        "0-203-1-900001",
        "cz.chmi.hydro_daily",
        None,
    )
    # HD (CM) → H, QD (M3_S) → Q; TD (0C) → T only where the file has TD rows.
    assert set(first.measurements) == {"H", "Q"}
    assert first.measurements["H"] == Measurement(58.0, "value")
    # PD rows (T18:00:00Z) of 2023-10-30..11-02 add no variable and no record.
    assert set(days[date(2023, 10, 30)].measurements) == {"H", "Q", "T"}
    # Integers and floats of one series both become float values.
    assert days[date(2023, 4, 15)].measurements["Q"] == Measurement(12.0, "value")
    assert days[date(2023, 10, 31)].measurements["T"] == Measurement(8.0, "value")


def test_hydro_fixture_leap_day_hydrological_year_and_day_without_rows():
    leap = by_date(parse_chmi_hydro_daily(fixture(f"{DAILY}/{H2024}"), filename=H2024))
    year = by_date(parse_chmi_hydro_daily(fixture(f"{DAILY}/{H2023}"), filename=H2023))

    assert set(leap[date(2024, 2, 29)].measurements) == {"H", "Q"}
    assert date(2024, 6, 15) not in leap  # no row: no record, no invented value
    assert len(leap) == 365
    assert (
        year[date(2023, 10, 31)].hydro_year,
        year[date(2023, 11, 1)].hydro_year,
    ) == (
        2023,
        2024,
    )


def test_hydro_fixture_water_level_shorter_than_discharge():
    name = "H_0-203-1-900002_DQ_2004.json"
    records = list(parse_chmi_hydro_daily(fixture(f"{DAILY}/{name}"), filename=name))

    assert len(records) == 366
    with_h = [record.date for record in records if "H" in record.measurements]
    assert (with_h[0], with_h[-1], len(with_h)) == (
        date(2004, 11, 1),
        date(2004, 12, 31),
        61,
    )
    assert all(set(record.measurements) <= {"H", "Q"} for record in records)


def test_hydro_reserialized_variant_gives_identical_records():
    variant = FIXTURES / "variants/H_0-203-1-900001_DQ_2023_reserialized.json"

    assert list(parse_chmi_hydro_daily(variant.read_bytes(), filename=H2023)) == list(
        parse_chmi_hydro_daily(fixture(f"{DAILY}/{H2023}"), filename=H2023)
    )


def test_hydro_null_is_missing_bom_allowed_and_time_of_day_ignored():
    content = b"\xef\xbb\xbf" + hydro_file(
        ("HD", "CM", [["2024-03-01T00:00:00Z", None]]),
        ("QD", "M3_S", [["2024-03-01T23:30:00Z", 1], ["2024-03-03T00:00Z", 2.5]]),
        ("PD", "G_M3", [["2024-03-02T18:00:00Z", 3.5]]),
    )

    records = list(parse_chmi_hydro_daily(content, filename=H2024))

    assert [record.date for record in records] == [date(2024, 3, 1), date(2024, 3, 3)]
    assert records[0].measurements == {
        "H": Measurement(None, "missing"),
        "Q": Measurement(1.0, "value"),
    }
    assert records[0].hydro_year == 2024


def test_hydro_duplicate_date_keeps_equal_value_and_rejects_different_one():
    same = hydro_file(
        ("QD", "M3_S", [["2024-01-05T00:00:00Z", 2], ["2024-01-05T00:00:00Z", 2.0]])
    )
    (record,) = parse_chmi_hydro_daily(same, filename=H2024)
    assert record.measurements == {"Q": Measurement(2.0, "value")}

    other = hydro_file(
        ("HD", "CM", [["2024-01-05T00:00:00Z", 90]]),
        ("HD", "CM", [["2024-01-05T00:00:00Z", 91]]),
    )
    with pytest.raises(IMGWDataError) as error:
        list(parse_chmi_hydro_daily(other, filename=H2024))
    assert error.value.details["location"] == "tsList[1].tsData.data.values[0]"


def _hydro_variant(change):
    document = json.loads(hydro_file(("HD", "CM", [["2024-01-05T00:00:00Z", 90]])))
    change(document)
    return json.dumps(document).encode()


def _with_rows(*rows):
    return _hydro_variant(
        lambda d: d["tsList"][0]["tsData"]["data"].update(values=list(rows))
    )


@pytest.mark.parametrize(
    ("content", "location"),
    [
        (
            _hydro_variant(lambda d: d["tsList"][0].update(tsConID="XD")),
            "tsList[0].tsConID",
        ),
        (_hydro_variant(lambda d: d["tsList"][0].update(unit="M")), "tsList[0].unit"),
        (_hydro_variant(lambda d: d.update(objID="0-203-1-900002")), "objID"),
        (_hydro_variant(lambda d: d.pop("objID")), "objID"),
        (_hydro_variant(lambda d: d.update(tsList={})), "tsList"),
        (
            _hydro_variant(
                lambda d: d["tsList"][0]["tsData"]["data"].update(header="DT,V")
            ),
            "tsList[0].tsData.data.header",
        ),
        (
            _hydro_variant(lambda d: d["tsList"][0].update(tsData=[])),
            "tsList[0].tsData.data",
        ),
        (
            _with_rows(["2024-01-05T00:00:00Z", 90, 1]),
            "tsList[0].tsData.data.values[0]",
        ),
        (
            _with_rows(["2024-01-05T00:00:00", 90]),
            "tsList[0].tsData.data.values[0][0]",
        ),
        (
            _with_rows(["2023-12-31T00:00:00Z", 90]),
            "tsList[0].tsData.data.values[0][0]",
        ),
        (
            _with_rows(["2024-01-05T00:00:00Z", "90"]),
            "tsList[0].tsData.data.values[0][1]",
        ),
        (
            _with_rows(["2024-01-05T00:00:00Z", True]),
            "tsList[0].tsData.data.values[0][1]",
        ),
        (b"[]", "$"),
    ],
    ids=[
        "unknown-tsConID",
        "wrong-unit",
        "objID-differs-from-name",
        "objID-missing",
        "tsList-not-a-list",
        "header",
        "tsData-not-an-object",
        "row-of-three",
        "time-without-Z",
        "date-outside-file-year",
        "text-value",
        "boolean-value",
        "root-not-an-object",
    ],
)
def test_hydro_malformed_content_names_file_and_json_path(content, location):
    with pytest.raises(IMGWDataError) as error:
        list(parse_chmi_hydro_daily(content, filename=f"{DAILY}/{H2024}"))

    assert error.value.code == "data_error"
    assert error.value.details == {"file": f"{DAILY}/{H2024}", "location": location}
    assert f"{DAILY}/{H2024}, {location}:" in str(error.value)


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        (b'{"objID": "0-203-1-900001", "tsList": [}', "line 1, column"),
        (
            b'{"objID": "0-203-1-900001", "objID": "0-203-1-900001", "tsList": []}',
            "a repeated key",
        ),
        (b'{"objID": "0-203-1-900001", "tsList": [], "x": NaN}', "NaN"),
        (b'{"objID": "0-203-1-90\xff", "tsList": []}', "UTF-8"),
    ],
    ids=["syntax", "duplicate-key", "nan", "utf8"],
)
def test_hydro_invalid_json_is_a_data_error_with_position(content, fragment):
    with pytest.raises(IMGWDataError, match=fragment) as error:
        list(parse_chmi_hydro_daily(content, filename=H2024))
    assert error.value.details["file"] == H2024


def test_hydro_rejects_a_name_that_is_not_a_daily_hydro_file():
    with pytest.raises(IMGWValidationError) as error:
        list(parse_chmi_hydro_daily(b"{}", filename="H_0-203-1-900001_HQ_2024.json"))
    assert error.value.details["option"] == "filename"


# --------------------------------------------------------------------------
# §5.2 meteo daily CSV
# --------------------------------------------------------------------------


def test_meteo_precipitation_fixture_flags_quality_and_source_flags():
    name = "dly-0-203-0-90001-SRA.csv"
    days = by_date(
        parse_chmi_meteo_daily(
            fixture(f"{CSV_DAILY}/precipitation/{name}"), filename=name
        )
    )

    def p(day: date) -> Measurement:
        measurement: Measurement = days[day].measurements["P"]
        return measurement

    assert len(days) == 31 and list(days) == sorted(days)
    assert days[date(2023, 10, 20)].dataset == "cz.chmi.meteo_daily"
    assert p(date(2023, 10, 20)) == Measurement(0.0, "no_phenomenon", 0, None)
    assert p(date(2023, 10, 21)) == Measurement(2.4, "value", 0, None)
    assert p(date(2023, 10, 22)) == Measurement(0.0, "value", 0, "T")  # trace
    assert p(date(2023, 10, 23)) == Measurement(12.3, "value", 0, "M")
    assert p(date(2023, 10, 24)) == Measurement(5.1, "value", 3, None)
    assert p(date(2023, 10, 25)) == Measurement(0.7, "value", 1, None)
    assert p(date(2023, 10, 26)) == Measurement(None, "missing", 4, None)
    assert p(date(2023, 10, 27)) == Measurement(1.5, "value", 0, "R")  # unknown flag
    assert (
        days[date(2023, 10, 31)].hydro_year,
        days[date(2023, 11, 1)].hydro_year,
    ) == (
        2023,
        2024,
    )


def test_meteo_temperature_fixture_uses_daily_mean_and_skips_terms():
    name = "dly-0-203-0-90001-T.csv"
    content = fixture(f"{CSV_DAILY}/temperature/{name}")
    records = list(parse_chmi_meteo_daily(content, filename=name))

    # 124 rows (AVG block first, then the 06/13/20 term blocks) → 31 days.
    assert len(content.decode().splitlines()) == 1 + 4 * 31
    assert len(records) == 31 and [r.date for r in records] == sorted(
        r.date for r in records
    )
    assert all(set(r.measurements) == {"Tmean"} for r in records)
    assert records[0].measurements["Tmean"] == Measurement(8.5, "value", 0, None)


def test_meteo_maximum_fixture_block_without_rows_gives_no_records():
    name = "dly-0-203-0-90001-TMA.csv"
    days = by_date(
        parse_chmi_meteo_daily(
            fixture(f"{CSV_DAILY}/temperature/{name}"), filename=name
        )
    )

    assert len(days) == 22
    assert date(2023, 10, 29) in days and date(2023, 11, 8) in days
    assert not [day for day in days if date(2023, 10, 30) <= day <= date(2023, 11, 7)]
    assert days[date(2023, 10, 20)].measurements["Tmax"].flag == "value"


def test_meteo_rows_in_any_order_seconds_bom_and_equal_duplicates():
    content = b"\xef\xbb\xbf" + meteo_file(
        sra("2023-10-22", "1.0"),
        "0-203-0-90001,SRA,06:00,2023-10-20T06:00:00Z,0.0,T,0.0,",
        sra("2023-10-21", "", quality="4.0"),
        sra("2023-10-22", "1.0"),
    )

    records = list(parse_chmi_meteo_daily(content, filename=SRA_NAME))

    assert [record.date for record in records] == [
        date(2023, 10, 20),
        date(2023, 10, 21),
        date(2023, 10, 22),
    ]
    assert [record.measurements["P"] for record in records] == [
        Measurement(0.0, "value", 0, "T"),
        Measurement(None, "missing", 4, None),
        Measurement(1.0, "value", 0, None),
    ]


def test_meteo_temperatures_are_values_even_at_zero():
    content = meteo_file(
        "0-203-0-90001,TMI,20:00,2023-10-20T20:00Z,0.0,,0.0,",
        "0-203-0-90001,TMI,20:00,2023-10-21T20:00Z,,,",
    )

    records = list(
        parse_chmi_meteo_daily(content, filename="dly-0-203-0-90001-TMI.csv")
    )

    assert [record.measurements["Tmin"] for record in records] == [
        Measurement(0.0, "value", 0, None),
        Measurement(None, "missing", None, None),
    ]


@pytest.mark.parametrize(
    ("content", "line"),
    [
        (meteo_file(header="STATION,ELEMENT,DT,VALUE,FLAG,QUALITY\n"), 1),
        (b"", 1),
        (meteo_file(sra("2023-10-20") + ","), 2),
        (meteo_file(sra("2023-10-20") + "x"), 2),
        (meteo_file(sra("2023-10-20"), sra("2023-10-21").replace("90001", "90002")), 3),
        (meteo_file(sra("2023-10-20").replace(",SRA,", ",SNO,")), 2),
        (meteo_file(sra("2023-10-20").replace(",06:00,", ",07:00,")), 2),
        (meteo_file(sra("2023-10-20").replace("T06:00Z", "T05:40Z")), 2),
        (meteo_file(sra("2023-10-20").replace("T06:00Z", "T06:00:30Z")), 2),
        (meteo_file(sra("2023-10-20").replace("T06:00Z", "")), 2),
        (meteo_file(sra("2023-02-30")), 2),
        (meteo_file(sra("2023-10-20", "abc")), 2),
        (meteo_file(sra("2023-10-20", "nan")), 2),
        (meteo_file(sra("2023-10-20", quality="1.5")), 2),
        (meteo_file(sra("2023-10-20", quality="x")), 2),
        (meteo_file(sra("2023-10-20", "1.0"), sra("2023-10-20", "1.1")), 3),
        (meteo_file(sra("2023-10-20", "1.0"), sra("2023-10-20", "1.0", "M")), 3),
    ],
    ids=[
        "header",
        "empty-file",
        "nine-columns",
        "non-empty-eighth-column",
        "station-differs-from-name",
        "element-differs-from-name",
        "wrong-timefunc",
        "time-does-not-fit-element",
        "seconds-other-than-zero",
        "dt-without-time",
        "invalid-date",
        "text-value",
        "nan-value",
        "non-integer-quality",
        "text-quality",
        "duplicate-with-other-value",
        "duplicate-with-other-flag",
    ],
)
def test_meteo_malformed_content_names_file_and_line(content, line):
    path = f"{CSV_DAILY}/precipitation/{SRA_NAME}"
    with pytest.raises(IMGWDataError) as error:
        list(parse_chmi_meteo_daily(content, filename=path))

    assert error.value.code == "data_error"
    assert error.value.details == {"file": path, "line": line}
    assert f"{path}, row {line}:" in str(error.value)


@pytest.mark.parametrize(
    ("element", "row"),
    [
        ("T", "0-203-0-90001,T,13:00,2023-10-20T06:00Z,4.1,,0.0,"),
        ("T", "0-203-0-90001,T,AVG,2023-10-20T06:00Z,4.1,,0.0,"),
        ("TMA", "0-203-0-90001,TMA,AVG,2023-10-20T00:00Z,9.1,,0.0,"),
        ("TMI", "0-203-0-90001,TMI,06:00,2023-10-20T06:00Z,1.1,,0.0,"),
    ],
)
def test_meteo_timefunc_must_fit_the_element(element, row):
    with pytest.raises(IMGWDataError, match="TIMEFUNC"):
        list(
            parse_chmi_meteo_daily(
                meteo_file(row), filename=f"dly-0-203-0-90001-{element}.csv"
            )
        )


def test_meteo_rejects_elements_outside_the_dataset():
    with pytest.raises(IMGWValidationError) as error:
        list(
            parse_chmi_meteo_daily(METEO_HEADER, filename="dly-0-203-0-90001-API30.csv")
        )
    assert error.value.details["option"] == "filename"


# --------------------------------------------------------------------------
# §5.3 station metadata
# --------------------------------------------------------------------------


def test_stations_hydro_fixture_latitude_first_and_hydrographic_code_as_text():
    entries = list(
        parse_chmi_stations(
            fixture("hydrology/historical/metadata/meta1.json"), kind="hydro"
        )
    )

    assert [entry.station_code for entry in entries] == [
        "0-203-1-900001",
        "0-203-1-900002",
        "0-203-1-900004",
    ]
    first = entries[0]
    assert (first.kind, first.provider, first.name, first.river) == (
        "hydro",
        "CHMI",
        "Špindlerův Mlýn - most",
        "Labe",
    )
    assert (first.latitude, first.longitude) == (
        50.4012345,
        15.6012345,
    )  # GEOGR1, GEOGR2
    assert first.hydrographic_code == "1-05-03-0110"
    assert entries[2].hydrographic_code is None  # HLGP4 ""
    assert all(e.river_order is None and e.short_code is None for e in entries)


def test_stations_meteo_fixture_longitude_first_and_latest_period_per_station():
    entries = {
        entry.station_code: entry
        for entry in parse_chmi_stations(
            fixture("meteorology/climate/historical/metadata/meta1.json"), kind="meteo"
        )
    }

    assert list(entries) == ["0-203-0-90001", "0-203-0-90000000002", "0-20000-0-99903"]
    station = entries["0-203-0-90001"]
    assert (station.name, station.latitude, station.longitude) == (
        "Fiktivní Ves-Horní",
        50.2147,
        14.8213,
    )
    # Periods 1970, 2000 (latest, middle row) and 1950 (no latitude): 2000 wins.
    foreign = entries["0-20000-0-99903"]
    assert (foreign.name, foreign.latitude, foreign.longitude) == (
        "Nordvik, Base",
        64.1311,
        -21.9405,
    )
    assert all(
        e.river is None and e.hydrographic_code is None for e in entries.values()
    )


def test_stations_envelope_changes_do_not_change_entries():
    now = fixture("hydrology/now/metadata/meta1.json")
    regenerated = (
        FIXTURES / "variants/hydrology_now_meta1_regenerated.json"
    ).read_bytes()
    meteo_17 = fixture("meteorology/climate/now/metadata/meta1-20261017.json")
    meteo_18 = fixture("meteorology/climate/now/metadata/meta1-20261018.json")

    assert now != regenerated and meteo_17 != meteo_18
    assert list(parse_chmi_stations(now, kind="hydro")) == list(
        parse_chmi_stations(regenerated, kind="hydro")
    )
    assert list(parse_chmi_stations(meteo_17, kind="meteo")) == list(
        parse_chmi_stations(meteo_18, kind="meteo")
    )


def test_stations_columns_are_located_by_name():
    canonical = envelope(
        "objID,STATION_NAME,STREAM_NAME,GEOGR1,GEOGR2,HLGP4",
        '["0-203-1-900001","A","R",50.1,15.2,"1-05-01-0001"]',
    )
    permuted = envelope(
        "HLGP4,GEOGR2,DBC,STREAM_NAME,GEOGR1,STATION_NAME,objID",
        '["1-05-01-0001",15.2,"900001","R",50.1,"A","0-203-1-900001"]',
    )

    assert list(parse_chmi_stations(permuted, kind="hydro")) == list(
        parse_chmi_stations(canonical, kind="hydro")
    )


def test_stations_repeated_code_keeps_first_row_and_is_reported():
    content = envelope(
        "WSI,GH_ID,FULL_NAME,GEOGR1,GEOGR2,ELEVATION,BEGIN_DATE",
        '["0-203-0-90001","A1","Prvni",14.1,50.1,300.0,"1961-01-01T00:00:00Z"],'
        '["0-203-0-90001","A2","Druha",14.2,50.2,301.0,"1999-01-01T00:00:00Z"],'
        '["0-203-0-90005","B1","Jina","",null,"","1990-01-01T00:00:00Z"]',
    )

    entries = list(parse_chmi_stations(content, kind="meteo"))

    assert [(e.station_code, e.name) for e in entries] == [
        ("0-203-0-90001", "Prvni"),
        ("0-203-0-90005", "Jina"),
    ]
    assert (entries[1].latitude, entries[1].longitude) == (None, None)
    table = read_metadata(content, filename="meta1-20261018.json")
    selection = station_rows(table, kind="meteo")
    assert dict(selection.rows) == {"0-203-0-90001": 0, "0-203-0-90005": 2}
    assert selection.duplicates == ("0-203-0-90001",)


def test_read_metadata_keeps_published_decimal_notation():
    table = read_metadata(
        envelope(
            "objID,GEOGR1,GEOGR2,DRYH,SPA1H,HLGP4",
            '["0-203-1-900001",50.7231690,15.17,90,"",null]',
        ),
        filename="meta1.json",
    )

    latitude, longitude = station_coordinates(table, 0, kind="hydro")
    assert (str(latitude), str(longitude)) == ("50.7231690", "15.17")
    assert latitude == Decimal("50.723169") and latitude.as_tuple().exponent == -7
    assert table.number(0, "DRYH") == 90 and isinstance(table.number(0, "DRYH"), int)
    assert (table.number(0, "SPA1H"), table.text(0, "HLGP4")) == (None, None)


@pytest.mark.parametrize(
    ("content", "kind", "location"),
    [
        (
            envelope(
                "objID,STATION_NAME,GEOGR1,GEOGR2", '["0-203-1-900001","A",50.1,15.2]'
            ),
            "hydro",
            "data.data.header",
        ),
        (
            envelope("WSI,FULL_NAME,GEOGR1,GEOGR2", '["0-203-0-90001","A",14.1]'),
            "meteo",
            "data.data.values[0]",
        ),
        (
            envelope("WSI,FULL_NAME,GEOGR1,GEOGR2", '[90001,"A",14.1,50.1]'),
            "meteo",
            "data.data.values[0][0]",
        ),
        (
            envelope("WSI,FULL_NAME,GEOGR1,GEOGR2", '["","A",14.1,50.1]'),
            "meteo",
            "data.data.values[0][0]",
        ),
        (
            envelope(
                "WSI,FULL_NAME,GEOGR1,GEOGR2", '["0-203-0-90001","A","14.1",50.1]'
            ),
            "meteo",
            "data.data.values[0][2]",
        ),
        (
            envelope(
                "WSI,FULL_NAME,GEOGR1,GEOGR2,WSI", '["0-203-0-90001","A",14.1,50.1,"x"]'
            ),
            "meteo",
            "data.data.header",
        ),
        (
            envelope(
                "WSI,BEGIN_DATE,END_DATE,FULL_NAME,GEOGR1,GEOGR2",
                '["0-203-0-90001","1961-01-01","3999-12-31T23:59:00Z","A",14.1,50.1]',
            ),
            "meteo",
            "data.data.values[0][1]",
        ),
        (b'{"zaznamID":"x","data":{"type":"DataCollection"}}', "hydro", "data.data"),
    ],
    ids=[
        "missing-column",
        "row-length",
        "numeric-code",
        "empty-code",
        "coordinate-as-text",
        "repeated-column",
        "period-without-utc-begin",
        "no-table",
    ],
)
def test_stations_malformed_metadata_is_a_data_error_with_place(
    content, kind, location
):
    with pytest.raises(IMGWDataError) as error:
        list(parse_chmi_stations(content, kind=kind))
    assert error.value.code == "data_error"
    assert error.value.details["location"] == location


def test_stations_reject_an_unknown_kind():
    with pytest.raises(IMGWValidationError):
        list(parse_chmi_stations(b"{}", kind="synop"))


# --------------------------------------------------------------------------
# §4.1 listings
# --------------------------------------------------------------------------

LISTING_URL = "https://opendata.chmi.cz/hydrology/read_me/"


def listing(*rows: str) -> str:
    return (
        "<html>\r\n<head><title>Index of /hydrology/read_me/</title></head>\r\n"
        "<body>\r\n<h1>Index of /hydrology/read_me/</h1><hr><pre>"
        '<a href="../">../</a>\r\n'
        + "".join(row + "\r\n" for row in rows)
        + "</pre><hr></body>\r\n</html>\r\n"
    )


def test_listing_name_from_decoded_href_time_to_the_minute_and_size():
    body = listing(
        '<a href="data/">data/</a>                                              '
        "18-Oct-2026 17:05                   -",
        '<a href="Pr%C5%AFvodce%20otev%C5%99en%C3%BDmi%20daty%20hydrologie.pdf">'
        "Průvodce otevřenými daty hydrologie.pdf</a>            10-Mar-2026 12:35"
        "              336500",
        '<a href="floods_prec24h_2024091112%2B24.png">floods_prec24h_2024091112+24.png'
        "</a>                   11-Sep-2024 12:00               81234",
        '<a href="H_0-203-1-900001_DQ_2023_2024_2025_2026_2027_2028_2029.json">'
        "H_0-203-1-900001_DQ_2023_2024_2025_2026_2027_..&gt;</a> 13-Feb-2025 09:41"
        "               45813",
    )

    entries = parse_listing(body.encode(), url=LISTING_URL)

    assert [(e.name, e.modified, e.size) for e in entries] == [
        (
            "Průvodce otevřenými daty hydrologie.pdf",
            datetime(2026, 3, 10, 12, 35, tzinfo=UTC),
            336500,
        ),
        (
            "floods_prec24h_2024091112+24.png",
            datetime(2024, 9, 11, 12, 0, tzinfo=UTC),
            81234,
        ),
        (
            "H_0-203-1-900001_DQ_2023_2024_2025_2026_2027_2028_2029.json",
            datetime(2025, 2, 13, 9, 41, tzinfo=UTC),
            45813,
        ),
    ]


@pytest.mark.parametrize(
    ("directory", "other_names"),
    [
        (DAILY, {"H_0-203-1-900001_DQ_2023_2024.json"}),
        (
            f"{CSV_DAILY}/precipitation",
            {"dly-0-203-0-90000000002-API30.csv", "dly-0-203-0-90001-API30.csv"},
        ),
        (
            f"{CSV_DAILY}/temperature",
            {"dly-0-203-0-90001-TMInoc.csv", "dly-0-203-0-90001-TPM.csv"},
        ),
        (
            "meteorology/climate/now/metadata",
            {f"meta{n}-2026101{d}.json" for n in (2, 3, 4) for d in (7, 8)},
        ),
    ],
)
def test_listing_fixtures_list_every_fixture_file_with_its_exact_size(
    directory, other_names
):
    body = (FIXTURES / "listings" / directory / "index.html").read_bytes()
    entries = parse_listing(body, url=f"https://opendata.chmi.cz/{directory}/")
    files = {path.name for path in (ARCHIVES / directory).iterdir() if path.is_file()}

    assert {entry.name for entry in entries} == files | other_names
    for entry in entries:
        assert entry.modified.second == 0 and entry.modified.tzinfo is UTC
        if entry.name in files:
            assert entry.size == len(fixture(f"{directory}/{entry.name}"))


@pytest.mark.parametrize(
    "body",
    [
        listing(),
        "<html><body><h1>404 Not Found</h1></body></html>",
        "",
    ],
    ids=["only-parent", "error-page", "empty"],
)
def test_listing_without_rows_is_a_data_error(body):
    with pytest.raises(IMGWDataError, match="no file and directory rows") as error:
        parse_listing(body, url=LISTING_URL)
    assert error.value.details == {"url": LISTING_URL}


@pytest.mark.parametrize(
    "row",
    [
        '<a href="x.json">x.json</a>',
        '<a href="x.json">x.json</a>    18-Oct-2026 17:05',
        '<a href="x.json">x.json</a>    18-Oct-2026 17:05      -',
        '<a href="x/">x/</a>    18-Oct-2026 17:05      123',
        '<a href="x.json">x.json</a>    18-Okt-2026 17:05      123',
        '<a href="x.json">x.json</a>    31-Feb-2026 17:05      123',
        '<a href="%FF.json">?.json</a>    18-Oct-2026 17:05      123',
        '<a href="a%2Fb.json">a/b.json</a>    18-Oct-2026 17:05      123',
    ],
    ids=[
        "name-only",
        "no-size",
        "file-with-directory-size",
        "directory-with-size",
        "unknown-month",
        "invalid-date",
        "invalid-utf8-name",
        "name-with-slash",
    ],
)
def test_listing_unreadable_row_is_a_data_error_with_line(row):
    with pytest.raises(IMGWDataError) as error:
        parse_listing(listing(row), url=LISTING_URL)
    assert error.value.details == {"url": LISTING_URL, "line": 5}


def test_listing_repeated_name_is_a_data_error():
    row = '<a href="x.json">x.json</a>    18-Oct-2026 17:05      123'
    with pytest.raises(IMGWDataError, match="a repeated name"):
        parse_listing(listing(row, row), url=LISTING_URL)


# --------------------------------------------------------------------------
# normalize_archive dispatch
# --------------------------------------------------------------------------


def test_normalize_archive_parses_chmi_archives_by_server_path():
    hydro = archive_files(
        "cz.chmi.hydro_daily",
        stations=["0-203-1-900001", "0-203-1-900002"],
        years=[2004, 2006, 2023, 2024],
    )
    meteo = archive_files("cz.chmi.meteo_daily", stations=["0-203-0-90001"])
    stored = [a for a in (*hydro, *meteo) if (ARCHIVES / a.server_path).is_file()]
    assert len(stored) == 8

    for archive in stored:
        data = (ARCHIVES / archive.server_path).read_bytes()
        parser = (
            parse_chmi_hydro_daily
            if archive.dataset == "cz.chmi.hydro_daily"
            else parse_chmi_meteo_daily
        )
        records = list(normalize_archive(archive, data=data))
        assert records == list(parser(data, filename=archive.server_path))
        assert {record.station_code for record in records} == {archive.station_code}


def test_normalize_archive_names_the_server_path_in_chmi_errors():
    (archive,) = archive_files(
        "cz.chmi.hydro_daily", stations=["0-203-1-900001"], years=2024
    )
    with pytest.raises(IMGWDataError) as error:
        list(normalize_archive(archive, data=hydro_file(code="0-203-1-900002")))
    assert error.value.details["file"] == archive.server_path
