"""
Unit tests for IMGW CSV parsers.

Focus on format drift between IMGW yearly archives:

- delimiter: comma with quoted fields (2019-2022, 2024) vs semicolon
  without quotes (2023); some files carry a header row of column codes;
- encoding: CP1250 for most archives, UTF-8 with BOM for the 2023
  daily archive (``codz_2023.zip``);
- quoting: daily and monthly 2024 files wrap every line in an outer
  pair of quotes with inner quotes doubled.

The parsers must yield identical records regardless of format.
"""

import io
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from imgwtools._parsing.common import _decode_content, _detect_delimiter
from imgwtools.datasets import ArchiveFile
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.models import StationListEntry
from imgwtools.parsers import (
    normalize_archive,
    parse_daily_csv,
    parse_meteo_climate_daily,
    parse_meteo_precip_daily,
    parse_monthly_csv,
    parse_semi_annual_csv,
    parse_stations_csv,
    parse_zip_file,
)

# ---------------------------------------------------------------------------
# Sample rows for the same measurement in the two real IMGW formats.
#
# Semicolon variant (2023): no quotes, plain station code.
# Comma variant (2019-2022, 2024): quoted fields, station code padded
# with a leading space.
# ---------------------------------------------------------------------------

# Daily: kod;nazwa;rzeka;rok;mies;dzien;stan;przeplyw;temp;mies_kal
DAILY_SEMICOLON = "123456789;SAN ESCOBAR;Ławica;2020;3;15;125;47.3;6.1;1\n"
DAILY_COMMA = '" 123456789","SAN ESCOBAR","Ławica",2020,3,15,125,47.3,6.1,1\n'

# Monthly: kod;nazwa;rzeka;rok;mies;ekstremum;stan;przeplyw;temp;mies_kal
MONTHLY_SEMICOLON = "123456789;SAN ESCOBAR;Ławica;2020;3;2;125;47.3;6.1;1\n"
MONTHLY_COMMA = '" 123456789","SAN ESCOBAR","Ławica",2020,3,2,125,47.3,6.1,1\n'

# Semi-annual: kod;nazwa;rzeka;rok;polrocze;param;ekstremum;wartosc;+dates
SEMI_ANNUAL_SEMICOLON = (
    "123456789;SAN ESCOBAR;Ławica;2020;15;Q;2;234.567;2020;5;12;14;30;2020;5;12;14;30\n"
)
SEMI_ANNUAL_COMMA = (
    '" 123456789","SAN ESCOBAR","Ławica",2020,15,"Q",2,234.567,'
    "2020,5,12,14,30,2020,5,12,14,30\n"
)

# Header row of column codes as seen in the 2024 semi-annual archive.
SEMI_ANNUAL_HEADER = (
    '"pskdszs","psnzwp","psnrzj","psrh","pspdrh","pspp","psekst","pswart"\n'
)

# Daily row in the 2023 archive format: semicolon, UTF-8, Polish chars.
# The real codz_2023.csv is UTF-8 with a BOM; 99.9 is the missing-temp code.
DAILY_UTF8 = "123456789;SAN ESCOBAR;Ławica (1);2023;01;01;91;15.300;99.9;11\n"

# Rows in the 2024 daily/monthly archive format: the WHOLE line is wrapped
# in an outer pair of quotes and inner quotes are doubled, so a standard
# csv.reader sees a single field. Taken from real mies_2024.csv structure.
DAILY_WRAPPED_2024 = (
    '"123456789,SAN ESCOBAR,Ławica (1),""2024"",""01"",""15"",107,22.400,,""11"""\n'
)
MONTHLY_WRAPPED_2024 = (
    '"123456789,SAN ESCOBAR,Ławica (1),""2024"",""01"",""1"",107,22.400,,""11"""\n'
)


# ---------------------------------------------------------------------------
# _detect_delimiter
# ---------------------------------------------------------------------------


class TestDetectDelimiter:
    """Tests for the per-file delimiter detection helper."""

    def test_detect_delimiter_semicolon(self):
        """Semicolon-separated content is detected as ';'."""
        assert _detect_delimiter(SEMI_ANNUAL_SEMICOLON) == ";"

    def test_detect_delimiter_comma(self):
        """Comma-separated content is detected as ','."""
        assert _detect_delimiter(SEMI_ANNUAL_COMMA) == ","

    def test_detect_delimiter_uses_first_non_empty_line(self):
        """Leading blank lines are skipped when sampling the delimiter."""
        content = "\n\n" + DAILY_COMMA
        assert _detect_delimiter(content) == ","

    def test_detect_delimiter_empty_defaults_to_semicolon(self):
        """Empty content falls back to the historical ';' default."""
        assert _detect_delimiter("") == ";"

    def test_detect_delimiter_tie_prefers_semicolon(self):
        """On an equal count, semicolon wins (documented default)."""
        # One of each -> tie -> ';'
        assert _detect_delimiter("a;b,c") == ";"


# ---------------------------------------------------------------------------
# _decode_content
# ---------------------------------------------------------------------------


class TestDecodeContent:
    """Tests for the per-file encoding detection helper."""

    def test_decode_utf8_bom(self):
        """UTF-8 bytes with a BOM decode correctly and drop the BOM."""
        raw = DAILY_UTF8.encode("utf-8-sig")
        decoded = _decode_content(raw, "cp1250")
        assert decoded == DAILY_UTF8
        assert not decoded.startswith("\ufeff")

    def test_decode_cp1250(self):
        """CP1250 bytes with Polish characters decode via the default."""
        raw = DAILY_UTF8.encode("cp1250")
        assert _decode_content(raw, "cp1250") == DAILY_UTF8

    def test_decode_utf8_without_bom_falls_back(self):
        """UTF-8 bytes without a BOM fall back when CP1250 fails."""
        # 'Ł' is 0xC5 0x81 in UTF-8; 0x81 is undefined in CP1250.
        raw = DAILY_UTF8.encode("utf-8")
        assert _decode_content(raw, "cp1250") == DAILY_UTF8

    def test_decode_plain_ascii(self):
        """Pure ASCII decodes identically under any strategy."""
        raw = b"123456789;STACJA;Rzeka;2020;1;1;10;1.0;5.0;11\n"
        assert _decode_content(raw, "cp1250") == raw.decode("ascii")


# ---------------------------------------------------------------------------
# parse_daily_csv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(DAILY_SEMICOLON, id="semicolon"),
        pytest.param(DAILY_COMMA, id="comma-quoted"),
    ],
)
def test_parse_daily_csv_both_delimiters_equal(content):
    """Daily parser yields the same record for both IMGW formats."""
    # Act
    records = list(parse_daily_csv(content))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_code == "123456789"
    assert station.station_name == "SAN ESCOBAR"
    assert record.hydro_year == 2020
    assert record.hydro_month == 3
    assert record.day == 15
    assert record.water_level_cm == 125
    assert record.flow_m3s == 47.3
    assert record.water_temp_c == 6.1
    assert record.calendar_month == 1


def test_parse_daily_csv_formats_are_identical():
    """Comma and semicolon rows produce byte-identical records."""
    ((_, rec_semi),) = list(parse_daily_csv(DAILY_SEMICOLON))
    ((_, rec_comma),) = list(parse_daily_csv(DAILY_COMMA))
    assert rec_semi.model_dump() == rec_comma.model_dump()


def test_parse_daily_csv_utf8_bom_bytes():
    """UTF-8 bytes with a BOM (codz_2023 format) parse correctly."""
    # Arrange: encode exactly like the real 2023 daily archive
    raw = DAILY_UTF8.encode("utf-8-sig")

    # Act
    records = list(parse_daily_csv(raw))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_code == "123456789"  # no BOM residue
    assert station.station_name == "SAN ESCOBAR"  # Polish chars intact
    assert record.hydro_year == 2023
    assert record.water_level_cm == 91
    assert record.flow_m3s == 15.3
    assert record.water_temp_c is None  # 99.9 = missing-temp code


def test_parse_daily_csv_wrapped_lines_2024():
    """Fully quoted lines (codz_2024 format) are unwrapped and parsed."""
    # Act
    records = list(parse_daily_csv(DAILY_WRAPPED_2024))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_code == "123456789"
    assert station.station_name == "SAN ESCOBAR"
    assert record.hydro_year == 2024
    assert record.hydro_month == 1
    assert record.day == 15
    assert record.water_level_cm == 107
    assert record.flow_m3s == 22.4
    assert record.water_temp_c is None  # empty field
    assert record.calendar_month == 11


# ---------------------------------------------------------------------------
# parse_monthly_csv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(MONTHLY_SEMICOLON, id="semicolon"),
        pytest.param(MONTHLY_COMMA, id="comma-quoted"),
    ],
)
def test_parse_monthly_csv_both_delimiters_equal(content):
    """Monthly parser yields the same record for both IMGW formats."""
    # Act
    records = list(parse_monthly_csv(content))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_code == "123456789"
    assert record.hydro_year == 2020
    assert record.hydro_month == 3
    assert record.extremum == "mean"  # code 2 -> mean
    assert record.water_level_cm == 125
    assert record.flow_m3s == 47.3


def test_parse_monthly_csv_formats_are_identical():
    """Comma and semicolon rows produce byte-identical records."""
    ((_, rec_semi),) = list(parse_monthly_csv(MONTHLY_SEMICOLON))
    ((_, rec_comma),) = list(parse_monthly_csv(MONTHLY_COMMA))
    assert rec_semi.model_dump() == rec_comma.model_dump()


def test_parse_monthly_csv_wrapped_lines_2024():
    """Fully quoted lines (mies_2024 format) are unwrapped and parsed."""
    # Act
    records = list(parse_monthly_csv(MONTHLY_WRAPPED_2024))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_code == "123456789"
    assert record.hydro_year == 2024
    assert record.extremum == "min"  # code 1 -> min
    assert record.water_level_cm == 107
    assert record.flow_m3s == 22.4
    assert record.water_temp_c is None  # empty field


# ---------------------------------------------------------------------------
# parse_semi_annual_csv  (the format the reported bug was found in)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(SEMI_ANNUAL_SEMICOLON, id="semicolon-2023"),
        pytest.param(SEMI_ANNUAL_COMMA, id="comma-quoted-2020"),
    ],
)
def test_parse_semi_annual_csv_both_delimiters_equal(content):
    """Semi-annual parser yields the same record for both IMGW formats."""
    # Act
    records = list(parse_semi_annual_csv(content))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_code == "123456789"
    assert record.hydro_year == 2020
    assert record.period == "annual"  # code 15 -> annual
    assert record.param == "Q"
    assert record.extremum == "mean"  # code 2 -> mean
    assert record.value == 234.567
    assert record.extremum_start_date == "2020-05-12 14:30"
    assert record.extremum_end_date == "2020-05-12 14:30"


def test_parse_semi_annual_csv_formats_are_identical():
    """Comma and semicolon rows produce byte-identical records."""
    ((_, rec_semi),) = list(parse_semi_annual_csv(SEMI_ANNUAL_SEMICOLON))
    ((_, rec_comma),) = list(parse_semi_annual_csv(SEMI_ANNUAL_COMMA))
    assert rec_semi.model_dump() == rec_comma.model_dump()


def test_parse_semi_annual_csv_skips_header_row():
    """A 2024-style header row of column codes is skipped, data kept."""
    # Arrange: header line + one real data line (as in the 2024 archive)
    content = SEMI_ANNUAL_HEADER + SEMI_ANNUAL_COMMA

    # Act
    records = list(parse_semi_annual_csv(content))

    # Assert: header is dropped (non-numeric fields -> None -> skip)
    assert len(records) == 1
    _, record = records[0]
    assert record.value == 234.567
    assert record.param == "Q"


def test_parse_semi_annual_csv_leading_space_station_code():
    """Leading space in a quoted station code is stripped consistently."""
    ((_, rec_comma),) = list(parse_semi_annual_csv(SEMI_ANNUAL_COMMA))
    assert rec_comma.station_code == "123456789"  # no leading space


# ---------------------------------------------------------------------------
# parse_zip_file  (end-to-end: the entry point the bug report used)
# ---------------------------------------------------------------------------


def _make_zip(csv_name: str, csv_content: str, encoding: str = "cp1250") -> bytes:
    """Build an in-memory ZIP holding a single CSV member."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(csv_name, csv_content.encode(encoding))
    return buffer.getvalue()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(SEMI_ANNUAL_SEMICOLON, id="semicolon-2023"),
        pytest.param(SEMI_ANNUAL_COMMA, id="comma-quoted-2020"),
        pytest.param(SEMI_ANNUAL_HEADER + SEMI_ANNUAL_COMMA, id="comma-header-2024"),
    ],
)
def test_parse_zip_file_semi_annual_returns_records(content):
    """parse_zip_file returns records for every yearly archive format.

    Regression guard: previously only the semicolon (2023) archive
    parsed; comma archives (2020, 2024) silently yielded zero records.
    """
    # Arrange
    zip_bytes = _make_zip("polr_Q_2020.csv", content)

    # Act
    records = list(parse_zip_file(zip_bytes, "polroczne_i_roczne"))

    # Assert
    assert len(records) == 1
    _, record = records[0]
    assert record.param == "Q"
    assert record.value == 234.567


def test_parse_zip_file_daily_utf8_bom():
    """A codz_2023-style ZIP (UTF-8 with BOM) parses without errors.

    Regression guard: previously parse_zip_file raised
    UnicodeDecodeError because CP1250 was hardcoded.
    """
    # Arrange
    zip_bytes = _make_zip("codz_2023.csv", DAILY_UTF8, encoding="utf-8-sig")

    # Act
    records = list(parse_zip_file(zip_bytes, "dobowe"))

    # Assert
    assert len(records) == 1
    station, record = records[0]
    assert station.station_name == "SAN ESCOBAR"
    assert record.water_level_cm == 91


def test_parse_zip_file_monthly_wrapped_2024():
    """A mies_2024-style ZIP (fully quoted lines) parses correctly.

    Regression guard: previously such rows collapsed to a single
    field and parse_zip_file silently yielded zero records.
    """
    # Arrange
    zip_bytes = _make_zip("mies_2024.csv", MONTHLY_WRAPPED_2024)

    # Act
    records = list(parse_zip_file(zip_bytes, "miesieczne"))

    # Assert
    assert len(records) == 1
    _, record = records[0]
    assert record.hydro_year == 2024
    assert record.water_level_cm == 107


def _archive(dataset, path, year, month=None):
    return ArchiveFile(
        dataset,
        path,
        "https://imgw.example/" + path,
        year,
        month,
        None,
        "calendar" if "meteo" in dataset else "hydrological",
        None,
        None,
    )


def test_normalized_hydro_leap_day_missing_q_and_year_boundary():
    rows = (
        "123456789;SAN ESCOBAR;Ławica;2024;01;01;120;99999.999;5.5;11\n"
        "123456789;SAN ESCOBAR;Ławica;2024;04;29;9999;45.6;99.9;2\n"
    )
    archive = _archive("pl.imgw.hydro_daily", "dobowe/codz_2024.zip", 2024)
    records = list(normalize_archive(archive, data=_make_zip("codz_2024.csv", rows)))
    assert [r.date.isoformat() for r in records] == ["2023-11-01", "2024-02-29"]
    assert [r.hydro_year for r in records] == [2024, 2024]
    assert records[0].measurements["H"].value == 120
    assert records[0].measurements["Q"].flag == "missing"
    assert records[1].measurements["H"].flag == "missing"
    assert records[1].measurements["Q"].value == 45.6


def test_normalized_monthly_aggregates_extrema_without_losing_missing():
    rows = "".join(
        f"123456789;SAN ESCOBAR;Ławica;2024;04;{index};{level};99999.999;99.9;2\n"
        for index, level in ((1, "100"), (2, "120"), (3, "150"))
    )
    archive = _archive("pl.imgw.hydro_monthly", "miesieczne/mies_2024.zip", 2024)
    (record,) = list(normalize_archive(archive, data=_make_zip("mies_2024.csv", rows)))
    assert record.date.isoformat() == "2024-02-01"
    assert set(record.measurements) == {
        "H_min",
        "H_mean",
        "H_max",
        "Q_min",
        "Q_mean",
        "Q_max",
        "T_min",
        "T_mean",
        "T_max",
    }
    assert record.measurements["H_max"].value == 150
    assert record.measurements["Q_min"].flag == "missing"


def test_normalized_semiannual_retains_parameter_period_and_dates():
    rows = "123456789;SAN ESCOBAR;Ławica;2024;13;Q;3;123.456;2024;2;29;12;30;2024;2;29;13;00\n"
    archive = _archive("pl.imgw.hydro_semiannual", "polroczne/polr_Q_2024.zip", 2024)
    (record,) = list(
        normalize_archive(archive, data=_make_zip("polr_Q_2024.csv", rows))
    )
    assert record.period == "winter"
    assert record.date.isoformat() == "2023-11-01"
    assert set(record.measurements) == {"Q_max"}
    assert record.extrema_dates["Q_max"][0].isoformat() == "2024-02-29T12:30:00"


def test_meteo_climate_status_and_attributes():
    row = "123456789;Łódź;2024;2;29;4.1;0;-2;8;1;0;0;9;0;9;S;10;0\n"
    records = list(
        parse_meteo_climate_daily(row.encode("cp1250"), filename="k_d_2024.csv")
    )
    day = next(record for record in records if record.date.isoformat() == "2024-02-29")
    assert day.measurements["Tmin"].flag == "missing"
    assert day.measurements["Tground"].flag == "no_phenomenon"
    assert day.measurements["P"].value == 0
    assert day.attributes["precip_type"] == "S"
    assert day.hydro_year == 2024


def test_meteo_precip_missing_days_accumulation_and_absent_month():
    rows = (
        "123456789;Opad;2001;1;1;;8;W;0;9;0;9;S;0;L;0\n"
        "123456789;Opad;2001;1;2;10;0;W;4;0;2;0;S;0;L;0\n"
    )
    archive = _archive("pl.imgw.meteo_precip_daily", "2001/2001_01_o.zip", 2001, 1)
    data = _make_zip("o_d_2001_01.csv", rows)
    records = list(normalize_archive(archive, data=data))
    assert len(records) == 31
    assert [r.measurements["P"].flag for r in records[:3]] == [
        "missing",
        "accumulated",
        "no_phenomenon",
    ]
    assert records[1].measurements["P"].value == 10
    assert records[1].attributes["snow_species"] == "S"
    assert records[1].attributes["snow_cover_type"] == "L"
    annual = _archive("pl.imgw.meteo_precip_daily", "2001/2001_o.zip", 2001)
    annual_records = list(normalize_archive(annual, data=data))
    assert (
        next(r for r in annual_records if r.date.isoformat() == "2001-02-01")
        .measurements["P"]
        .flag
        == "missing"
    )
    assert len(list(parse_meteo_precip_daily(rows, filename="o_d_2001_01.csv"))) == 31
    annual_direct = list(parse_meteo_precip_daily(rows, filename="o_d_2001.csv"))
    assert len(annual_direct) == 365


def test_meteo_archive_selects_only_daily_csv_and_reports_line():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("k_m_2001.csv", "garbage")
        zf.writestr(
            "k_d_2001.csv", "123456789;Klimat;2001;11;1;2;0;0;0;1;0;0;0;0;9;S;0;9"
        )
    archive = _archive("pl.imgw.meteo_climate_daily", "2001/2001_11_k.zip", 2001, 11)
    records = list(normalize_archive(archive, data=data.getvalue()))
    assert records[0].hydro_year == 2002
    broken = _make_zip(
        "k_d_2001.csv", "123456789;Klimat;2001;2;30;2;0;0;0;1;0;0;0;0;9;S;0;9"
    )
    with pytest.raises(IMGWDataError, match=r"k_d_2001.csv, wiersz 1"):
        list(normalize_archive(archive, data=broken))


def test_recorded_daily_archives_cover_annual_monthly_and_leap_day():
    root = Path(__file__).parents[1] / "fixtures/store/archives"
    scenarios = (
        (
            "pl.imgw.hydro_daily",
            "dane_hydrologiczne/dobowe/2023/codz_2023.zip",
            2023,
            None,
            "2022-11-01",
        ),
        (
            "pl.imgw.hydro_daily",
            "dane_hydrologiczne/dobowe/2024/codz_2024.zip",
            2024,
            None,
            "2024-02-29",
        ),
        (
            "pl.imgw.meteo_climate_daily",
            "dane_meteorologiczne/dobowe/klimat/1991_1995/1995_k.zip",
            1995,
            None,
            "1995-01-01",
        ),
        (
            "pl.imgw.meteo_precip_daily",
            "dane_meteorologiczne/dobowe/opad/2004/2004_02_o.zip",
            2004,
            2,
            "2004-02-29",
        ),
    )
    for dataset, filename, year, month, expected_date in scenarios:
        records = list(
            normalize_archive(
                _archive(dataset, filename, year, month),
                data=(root / filename).read_bytes(),
            )
        )
        assert any(record.date.isoformat() == expected_date for record in records)


def test_normalized_hydro_bad_measurement_reports_member_and_line():
    archive = _archive("pl.imgw.hydro_daily", "dobowe/codz_2024.zip", 2024)
    csv = "123456789;SAN ESCOBAR;Ławica;2024;04;29;abc;45.6;5.5;2\n"
    with pytest.raises(IMGWDataError, match=r"codz_2024\.zip/codz_2024\.csv, wiersz 1"):
        list(normalize_archive(archive, data=_make_zip("codz_2024.csv", csv)))


def test_semiannual_generic_missing_sentinel():
    archive = _archive("pl.imgw.hydro_semiannual", "polr_H_2024.zip", 2024)
    row = "123456789;SAN ESCOBAR;Ławica;2024;15;H;2;99999.999\n"
    (record,) = list(normalize_archive(archive, data=_make_zip("polr_H_2024.csv", row)))
    assert record.measurements["H_mean"].flag == "missing"


# ---------------------------------------------------------------------------
# Semi-annual layouts of real IMGW years (fictional station, real column shapes)
# ---------------------------------------------------------------------------

# 1951-2022: Y,M,D,HH without minutes; an empty hour, day or month cuts the date.
SEMI_16 = (
    '" 123456789","SAN ESCOBAR","Ławica (1)","1951","13","H","3",140.000,'
    '"1951","03","19","07","1951","03","19","24"\n'
    '" 123456789","SAN ESCOBAR","Ławica (1)","1951","13","H","2",80.000,'
    '"","","","","","","",""\n'
    '" 123456789","SAN ESCOBAR","Ławica (1)","1951","14","H","1",42.000,'
    '"1951","09","29","","1951","09","31",""\n'
    '" 123456789","SAN ESCOBAR","Ławica (1)","1951","15","H","1",40.000,'
    '"1951","01","","","1951","02","",""\n'
)
# 1997: 17 columns, the hydrological year repeated before both dates.
SEMI_1997 = (
    '"123456789",SAN ESCOBAR,Ławica (1),"1997","13",H,"3",394.000,"1997",'
    '"1996","11","15","05","1996","11","15","07"\n'
    '"123456789",SAN ESCOBAR,Ławica (1),"1997","13",H,"2",191.000,"1997",,,,,,,,\n'
)
# 2023 H: 20 columns, an undocumented field (empty or "1") after each date.
SEMI_2023_H = (
    "123456789;SAN ESCOBAR;Ławica (1);2023;13;H;3;270.000;"
    "2022;12;24;11;30;;2022;12;24;11;50;\n"
    "123456789;SAN ESCOBAR;Ławica (1);2023;13;H;1;137.000;"
    "2022;12;24;14;;1;2022;12;24;14;;1\n"
    "123456789;SAN ESCOBAR;Ławica (1);2023;13;H;2;127.000;;;;;;;;;;;;\n"
)
# 2023 Q: 19 columns, the trailing undocumented field dropped.
SEMI_2023_Q = (
    "123456789;SAN ESCOBAR;Ławica (1);2023;14;Q;3;161.000;"
    "2023;05;17;20;10;;2023;05;17;20;40\n"
)
# 2023 T: 17 columns, the end date cut after the day.
SEMI_2023_T = (
    "123456789;SAN ESCOBAR;Ławica (1);2023;13;T;1;.400;2022;12;19;;;;2022;12;19\n"
    "123456789;SAN ESCOBAR;Ławica (1);2023;13;T;2;5.800;;;;;;;;;\n"
)


@pytest.mark.parametrize(
    "content, expected",
    [
        pytest.param(
            SEMI_16,
            [
                ("winter", "H", "max", "1951-03-19 07:00", "1951-03-20 00:00"),
                ("winter", "H", "mean", None, None),
                ("summer", "H", "min", "1951-09-29", "1951-09-30"),
                ("annual", "H", "min", "1951-01-01", "1951-02-01"),
            ],
            id="16-columns-1951-2022",
        ),
        pytest.param(
            SEMI_1997,
            [
                ("winter", "H", "max", "1996-11-15 05:00", "1996-11-15 07:00"),
                ("winter", "H", "mean", None, None),
            ],
            id="17-columns-1997",
        ),
        pytest.param(
            SEMI_2023_H,
            [
                ("winter", "H", "max", "2022-12-24 11:30", "2022-12-24 11:50"),
                ("winter", "H", "min", "2022-12-24 14:00", "2022-12-24 14:00"),
                ("winter", "H", "mean", None, None),
            ],
            id="20-columns-2023-H",
        ),
        pytest.param(
            SEMI_2023_Q,
            [("summer", "Q", "max", "2023-05-17 20:10", "2023-05-17 20:40")],
            id="19-columns-2023-Q",
        ),
        pytest.param(
            SEMI_2023_T,
            [
                ("winter", "T", "min", "2022-12-19", "2022-12-19"),
                ("winter", "T", "mean", None, None),
            ],
            id="17-columns-2023-T",
        ),
    ],
)
def test_semi_annual_layouts_keep_start_and_end_dates(content, expected):
    records = [record for _, record in parse_semi_annual_csv(content)]
    assert [
        (
            record.period,
            record.param,
            record.extremum,
            record.extremum_start_date,
            record.extremum_end_date,
        )
        for record in records
    ] == expected


def test_normalized_semiannual_old_layout_gives_start_and_end_datetimes():
    archive = _archive("pl.imgw.hydro_semiannual", "1951/polr_H_1951.zip", 1951)
    records = list(
        normalize_archive(archive, data=_make_zip("polr_H_1951.csv", SEMI_16))
    )
    dates = {
        (record.period, column): record.extrema_dates[column]
        for record in records
        for column in record.measurements
    }
    assert dates == {
        ("winter", "H_max"): (datetime(1951, 3, 19, 7), datetime(1951, 3, 20)),
        ("winter", "H_mean"): (None, None),
        ("summer", "H_min"): (datetime(1951, 9, 29), datetime(1951, 9, 30)),
        ("annual", "H_min"): (datetime(1951, 1, 1), datetime(1951, 2, 1)),
    }


def test_semiannual_unknown_or_mixed_column_layout_is_an_error():
    archive = _archive("pl.imgw.hydro_semiannual", "2024/polr_H_2024.zip", 2024)
    fifteen = "123456789;SAN ESCOBAR;Ławica;2024;15;H;2;100.0;;;;;;;\n"
    with pytest.raises(IMGWDataError, match=r"15 kolumn\) w .*polr_H_2024\.csv"):
        list(normalize_archive(archive, data=_make_zip("polr_H_2024.csv", fifteen)))
    mixed = SEMI_2023_T + SEMI_2023_Q
    with pytest.raises(IMGWDataError, match=r"Niejednolita liczba kolumn \(17, 19\)"):
        list(parse_semi_annual_csv(mixed))


def test_normalized_semiannual_merges_repeated_extremum_rows():
    rows = (
        "123456789;SAN ESCOBAR;Ławica;2024;13;H;3;278.000;"
        "2023;12;25;08;40;2023;12;25;08;40\n"
        "123456789;SAN ESCOBAR;Ławica;2024;13;H;3;278.000;"
        "2023;12;25;06;00;2023;12;25;08;20\n"
        "123456789;SAN ESCOBAR;Ławica;2024;13;H;3;278.000;"
        "2023;12;25;08;40;2023;12;25;08;40\n"
        "123456789;SAN ESCOBAR;Ławica;2024;13;H;2;160.000;;;;;;;;;;\n"
    )
    archive = _archive("pl.imgw.hydro_semiannual", "2024/polr_H_2024.zip", 2024)
    records = list(normalize_archive(archive, data=_make_zip("polr_H_2024.csv", rows)))
    by_column = {column: record for record in records for column in record.measurements}
    assert len(records) == 2 and set(by_column) == {"H_max", "H_mean"}
    maximum = by_column["H_max"]
    assert maximum.measurements["H_max"].value == 278
    assert maximum.extrema_dates["H_max"] == (
        datetime(2023, 12, 25, 6, 0),
        datetime(2023, 12, 25, 8, 40),
    )
    assert maximum.extrema_occurrences == {"H_max": 3}
    assert by_column["H_mean"].extrema_occurrences == {"H_mean": 1}
    conflicting = rows + (
        "123456789;SAN ESCOBAR;Ławica;2024;13;H;3;279.000;"
        "2023;12;26;01;00;2023;12;26;01;00\n"
    )
    with pytest.raises(
        IMGWDataError, match="Sprzeczne wartości H_max stacji 123456789"
    ):
        list(normalize_archive(archive, data=_make_zip("polr_H_2024.csv", conflicting)))


def test_meteo_climate_archive_ignores_k_d_t_member():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr(
            "k_d_t_01_2001.csv", "123456789,Klimat,2001,01,01,-5.7,,82,,2,,8,\n"
        )
        zf.writestr(
            "k_d_01_2001.csv", "123456789,Klimat,2001,01,01,2,0,0,0,1,0,0,0,0,9,S,0,9\n"
        )
    archive = _archive("pl.imgw.meteo_climate_daily", "2001/2001_01_k.zip", 2001, 1)
    records = list(normalize_archive(archive, data=data.getvalue()))
    assert len(records) == 31
    assert records[0].measurements["Tmax"].value == 2


def test_meteo_precip_skips_only_a_leading_header_row():
    header = (
        '"kansp","kapost","dorok","domc","dodz","dosmdb","dowsmdb","doroop",'
        '"dopksn","dowpksn","dohss","dowhss","dogats","dowgats","dorpsn","dowrpsn"\n'
    )
    row = '"123456789",OPADOWO,"2025","08","01",0.8,,W,,"9",,"8",,"8",,"8"\n'
    archive = _archive("pl.imgw.meteo_precip_daily", "2025/2025_08_o.zip", 2025, 8)
    records = list(
        normalize_archive(archive, data=_make_zip("o_d_08_2025.csv", header + row))
    )
    assert len(records) == 31
    assert records[0].measurements["P"].value == 0.8
    with pytest.raises(IMGWDataError, match=r"o_d_08_2025\.csv, wiersz 2"):
        list(
            normalize_archive(archive, data=_make_zip("o_d_08_2025.csv", row + header))
        )


def test_station_list_parser_keeps_hydrographic_fields():
    (station,) = list(
        parse_stations_csv("149190310,Raba,Raba (02138),1\n", kind="hydro")
    )
    assert station == StationListEntry(
        "hydro", "149190310", "Raba", "Raba", "02138", 1, None
    )


def test_station_list_parser_reads_meteo_columns_without_river_fields():
    content = '"123750000","Warszawa"," 375"\n"123760000","Bez Numeru",""\n'
    stations = list(parse_stations_csv(content.encode("cp1250"), kind="meteo"))
    assert stations == [
        StationListEntry("meteo", "123750000", "Warszawa", short_code="375"),
        StationListEntry("meteo", "123760000", "Bez Numeru"),
    ]


def test_station_list_parser_rejects_unknown_kind():
    with pytest.raises(IMGWValidationError):
        list(parse_stations_csv("1,A\n", kind="synop"))  # type: ignore[arg-type]
