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

import pytest

from imgwtools.db.parsers import (
    _decode_content,
    _detect_delimiter,
    parse_daily_csv,
    parse_monthly_csv,
    parse_semi_annual_csv,
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
