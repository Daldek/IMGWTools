"""
ČHMÚ (opendata.chmi.cz) parsers: daily hydro JSON, daily meteo CSV and metadata.

Formats follow the live survey of 2026-10-18 (spec 2026-10-18 §4.1 and §5):

- ``hydrology/historical/data/daily/H_<WIGOS>_DQ_<YYYY>.json`` — compact JSON
  ``{"objID", "tsList": [{"tsConID", "unit", "tsData": {"data": {"header":
  "DT,VAL", "values": [[DT, VAL], ...]}}}]}`` without an envelope;
- ``meteorology/climate/historical_csv/data/daily/<group>/dly-<WIGOS>-<EL>.csv``
  — CSV ``STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY,`` (trailing comma);
- ``.../metadata/meta1.json`` and ``meta3.json`` — envelope ``{"zaznamID",
  ..., "data": {"data": {"header": "<columns>", "values": [[...], ...]}}}``
  with columns located by name;
- nginx autoindex directory listings (HTML).

Parsing is strict: every content error raises :class:`IMGWDataError` naming
the file and the place (JSON path or CSV line); values are never filled in,
interpolated or corrected by quality.
"""

import csv
import io
import json
import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal, NoReturn
from urllib.parse import unquote

from imgwtools.datasets import _CHMI_HYDRO_FILE, _CHMI_METEO_FILE
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.messages import message, reason
from imgwtools.models import Measurement, NormalizedRecord, StationListEntry

HYDRO_DATASET = "cz.chmi.hydro_daily"
METEO_DATASET = "cz.chmi.meteo_daily"
PROVIDER = "CHMI"

ELEMENT_VARIABLES: Mapping[str, str] = {
    "SRA": "P",
    "T": "Tmean",
    "TMA": "Tmax",
    "TMI": "Tmin",
}
"""Variable of the series built from each daily ČHMÚ element file."""

# tsConID → (variable, unit required by ČHMÚ); PD (suspended solids) is checked
# structurally and skipped.
_HYDRO_SERIES = {"HD": ("H", "CM"), "QD": ("Q", "M3_S"), "TD": ("T", "0C")}
_HYDRO_CODES = ("HD", "QD", "TD", "PD")
_HYDRO_VARIABLES = ("H", "Q", "T")
# Element → (TIMEFUNC, time of DT) of its daily value; T terms are skipped.
_METEO_TIMING = {
    "SRA": ("06:00", "06:00"),
    "T": ("AVG", "00:00"),
    "TMA": ("20:00", "20:00"),
    "TMI": ("20:00", "20:00"),
}
_T_TERMS = frozenset({"06:00", "13:00", "20:00"})
_CSV_HEADER = ["STATION", "ELEMENT", "TIMEFUNC", "DT", "VALUE", "FLAG", "QUALITY"]
_ISO_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?Z"
)
_CSV_TIME = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2})(?::([0-9]{2}))?Z"
)
# Numeric CSV text: decimal notation with an optional exponent; no NaN,
# infinity, digit separators or whitespace.
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?")
_ANCHOR = re.compile(r'<a href="([^"]*)">')
_LISTING_ROW = re.compile(
    r'<a href="(?P<href>[^"]+)">.*?</a>\s+'
    r"(?P<day>[0-9]{2})-(?P<month>[A-Z][a-z]{2})-(?P<year>[0-9]{4})"
    r" (?P<hour>[0-9]{2}):(?P<minute>[0-9]{2})\s+(?P<size>[0-9]+|-)\s*"
)
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun")
        + ("Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        1,
    )
}


class _JSONContentError(ValueError):
    """Duplicate object key or non-standard constant met while decoding JSON."""


def _basename(filename: str) -> str:
    return filename.rsplit("/", 1)[-1]


def _hydro_year(day: date) -> int:
    return day.year + (day.month >= 11)


def _decode(content: bytes | str, filename: str) -> str:
    """Strict UTF-8 text without one leading BOM."""
    if isinstance(content, str):
        text = content
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IMGWDataError(
                message(
                    "chmi.invalid_utf_8_encoding_byte",
                    filename=filename,
                    start=exc.start,
                ),
                details={"file": filename, "byte": exc.start},
            ) from exc
    return text.removeprefix("\ufeff")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _JSONContentError(message("chmi.repeated_key", key=key))
        result[key] = value
    return result


def _reject_constant(name: str) -> NoReturn:
    raise _JSONContentError(message("chmi.disallowed_constant", name=name))


def _load_json(text: str, filename: str, *, decimal: bool) -> object:
    """RFC 8259 JSON: duplicate keys, ``NaN`` and ``Infinity`` are errors."""
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_keys,
            parse_constant=_reject_constant,
            parse_float=Decimal if decimal else float,
        )
    except json.JSONDecodeError as exc:
        raise IMGWDataError(
            message(
                "chmi.invalid_json_line_column",
                filename=filename,
                msg=exc.msg,
                lineno=exc.lineno,
                colno=exc.colno,
            ),
            details={"file": filename, "line": exc.lineno, "column": exc.colno},
        ) from exc
    except _JSONContentError as exc:
        raise IMGWDataError(
            message("chmi.invalid_json", filename=filename, exc=reason(exc)),
            details={"file": filename},
        ) from exc


def _json_error(filename: str, location: str, reason: str) -> IMGWDataError:
    return IMGWDataError(
        message(
            "chmi.invalid_hm_file", filename=filename, location=location, reason=reason
        ),
        details={"file": filename, "location": location},
    )


def _csv_error(filename: str, line: int, reason: str) -> IMGWDataError:
    return IMGWDataError(
        message("chmi.invalid_record_row", filename=filename, line=line, reason=reason),
        details={"file": filename, "line": line},
    )


def _utc_moment(value: object) -> datetime | None:
    """ISO 8601 UTC timestamp with ``Z`` (``YYYY-MM-DDTHH:MM[:SS[.f]]Z``)."""
    if not isinstance(value, str) or _ISO_UTC.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _filename_match(
    filename: str, pattern: re.Pattern[str], expected: str
) -> re.Match[str]:
    match = pattern.fullmatch(_basename(filename))
    if match is None:
        raise IMGWValidationError(
            message("chmi.file_name_not_hm_file", filename=filename, expected=expected),
            details={"option": "filename", "value": filename},
        )
    return match


# --------------------------------------------------------------------------
# Hydrology: H_<WIGOS>_DQ_<YYYY>.json
# --------------------------------------------------------------------------


def _hydro_measurement(value: object) -> Measurement | None:
    """Measurement of a ``VAL`` cell; None for a value that is not a number."""
    if value is None:
        return Measurement(None, "missing")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return Measurement(number, "value") if math.isfinite(number) else None


def parse_chmi_hydro_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    """
    Parse a ČHMÚ daily hydrological file into normalized records.

    The file ``H_<WIGOS>_DQ_<YYYY>.json`` holds one calendar year of one
    station: series ``HD`` (mean daily water level, ``CM``), ``QD`` (mean
    daily discharge, ``M3_S``) and ``TD`` (mean daily water temperature,
    ``0C``) become variables ``H`` [cm], ``Q`` [m3/s] and ``T`` [degC];
    ``PD`` (suspended solids) is checked structurally and skipped. The
    date of a row is the date part of its ``DT`` (``...T00:00:00Z``; the
    time, e.g. ``T18:00:00Z`` of ``PD``, is ignored). A numeric ``VAL``
    (JSON integer or float) is flagged ``"value"``, ``null`` ``"missing"``.
    Days without any row give no record: the continuous calendar is built
    with the series, never by the parser.

    Parameters
    ----------
    content : bytes or str
        File content; bytes are decoded as UTF-8 (a leading BOM is allowed).
    filename : str
        File name or server path ending with ``H_<WIGOS>_DQ_<YYYY>.json``;
        it gives the station code and the year, and names the file in errors.

    Yields
    ------
    NormalizedRecord
        One record per date with at least one of ``H``, ``Q``, ``T``, in date
        order: dataset ``"cz.chmi.hydro_daily"``, the hydrological year
        (November-October) of the date, ``period=None`` and only the
        variables present that day.

    Raises
    ------
    IMGWValidationError
        If ``filename`` does not end with a ČHMÚ daily hydrological file name.
    IMGWDataError
        If the content is not UTF-8 JSON of this format, ``objID`` differs
        from the code of ``filename``, a series is unknown or has a unit other
        than ``CM``/``M3_S``/``0C``, a row is not ``[DT, VAL]`` with an ISO
        8601 UTC time and a number or ``null``, a date lies outside the year
        of ``filename``, or one date of a variable has two different values.
        The message names the file and the JSON path.
    """
    match = _filename_match(filename, _CHMI_HYDRO_FILE, "H_<kod>_DQ_<rok>.json")
    code, year = match.group(1), int(match.group(2))
    root = _load_json(_decode(content, filename), filename, decimal=False)
    if not isinstance(root, dict):
        raise _json_error(filename, "$", message("chmi.root_value_not_object"))
    obj_id = root.get("objID")
    if not isinstance(obj_id, str):
        raise _json_error(filename, "objID", message("chmi.no_station_code_text"))
    if obj_id != code:
        raise _json_error(
            filename,
            "objID",
            message("chmi.code_does_not_match_file", obj_id=obj_id, code=code),
        )
    series = root.get("tsList")
    if not isinstance(series, list):
        raise _json_error(filename, "tsList", message("chmi.no_list_series"))
    by_day: dict[date, dict[str, Measurement]] = {}
    for index, entry in enumerate(series):
        where = f"tsList[{index}]"
        if not isinstance(entry, dict):
            raise _json_error(filename, where, message("chmi.series_not_object"))
        con = entry.get("tsConID")
        if not isinstance(con, str) or con not in _HYDRO_CODES:
            raise _json_error(
                filename,
                f"{where}.tsConID",
                message(
                    "chmi.unknown_series_allowed",
                    con=con,
                    hydro_codes=", ".join(_HYDRO_CODES),
                ),
            )
        unit = entry.get("unit")
        variable: str | None = None
        if con in _HYDRO_SERIES:
            variable, expected = _HYDRO_SERIES[con]
            if unit != expected:
                raise _json_error(
                    filename,
                    f"{where}.unit",
                    message(
                        "chmi.unit_series_expected",
                        unit=unit,
                        con=con,
                        expected=expected,
                    ),
                )
        elif not isinstance(unit, str):
            raise _json_error(filename, f"{where}.unit", message("chmi.no_unit_text"))
        data = entry.get("tsData")
        table = data.get("data") if isinstance(data, dict) else None
        if not isinstance(table, dict):
            raise _json_error(
                filename, f"{where}.tsData.data", message("chmi.no_data_table")
            )
        header = table.get("header")
        if header != "DT,VAL":
            raise _json_error(
                filename,
                f"{where}.tsData.data.header",
                message("chmi.header_expected_dt_val", header=header),
            )
        rows = table.get("values")
        if not isinstance(rows, list):
            raise _json_error(
                filename, f"{where}.tsData.data.values", message("chmi.no_list_rows")
            )
        for number, row in enumerate(rows):
            place = f"{where}.tsData.data.values[{number}]"
            if not isinstance(row, list) or len(row) != 2:
                raise _json_error(filename, place, message("chmi.row_not_pair_dt_val"))
            moment = _utc_moment(row[0])
            if moment is None:
                raise _json_error(
                    filename,
                    f"{place}[0]",
                    message("chmi.time_not_iso_8601_utc", row=row[0]),
                )
            day = moment.date()
            if day.year != year:
                raise _json_error(
                    filename,
                    f"{place}[0]",
                    message("chmi.date_outside_year_file", day=day, year=year),
                )
            measurement = _hydro_measurement(row[1])
            if measurement is None:
                raise _json_error(
                    filename,
                    f"{place}[1]",
                    message("chmi.value_not_number", row=row[1]),
                )
            if variable is None:
                continue
            values = by_day.setdefault(day, {})
            previous = values.setdefault(variable, measurement)
            if previous != measurement:
                raise _json_error(
                    filename,
                    place,
                    message(
                        "chmi.repeated_date_variable_has_different",
                        day=day,
                        variable=variable,
                    ),
                )
    for day in sorted(by_day):
        values = by_day[day]
        yield NormalizedRecord(
            code,
            HYDRO_DATASET,
            day,
            _hydro_year(day),
            None,
            {name: values[name] for name in _HYDRO_VARIABLES if name in values},
        )


# --------------------------------------------------------------------------
# Meteorology: dly-<WIGOS>-<ELEMENT>.csv
# --------------------------------------------------------------------------


def _meteo_measurement(
    variable: str, raw_value: str, raw_flag: str, raw_quality: str
) -> Measurement:
    """Measurement of one CSV row; ValueError with a Polish reason when malformed."""
    if raw_quality == "":
        quality = None
    else:
        if _NUMBER.fullmatch(raw_quality) is None:
            raise ValueError(
                message("chmi.quality_not_number", raw_quality=raw_quality)
            )
        parsed = Decimal(raw_quality)
        if parsed != parsed.to_integral_value():
            raise ValueError(
                message("chmi.quality_not_integer", raw_quality=raw_quality)
            )
        quality = int(parsed)
    source_flag = raw_flag or None
    if raw_value == "":
        return Measurement(None, "missing", quality, source_flag)
    value = float(raw_value) if _NUMBER.fullmatch(raw_value) else math.nan
    if not math.isfinite(value):
        raise ValueError(message("chmi.value_not_number_2", raw_value=raw_value))
    if variable == "P" and value == 0 and source_flag is None:
        return Measurement(0.0, "no_phenomenon", quality, None)
    return Measurement(value, "value", quality, source_flag)


def parse_chmi_meteo_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    """
    Parse a ČHMÚ daily climatological CSV into normalized records.

    The file ``dly-<WIGOS>-<ELEMENT>.csv`` (``historical_csv``) holds the
    whole history of one element of one station. Elements map to variables
    ``SRA`` → ``P`` [mm] (``TIMEFUNC`` ``06:00``, ``DT`` ``D T06:00Z``),
    ``T`` → ``Tmean`` [degC] (``AVG``, ``D T00:00Z``; the term rows
    ``06:00``, ``13:00`` and ``20:00`` are skipped), ``TMA`` → ``Tmax`` and
    ``TMI`` → ``Tmin`` [degC] (``20:00``, ``D T20:00Z``); the date is the
    date of ``DT`` (``HH:MMZ`` or ``HH:MM:SSZ``), never shifted.

    Flags: an empty ``VALUE`` is ``"missing"``; precipitation ``0.0``
    without ``FLAG`` is ``"no_phenomenon"`` (value ``0.0``); every other
    value, also the trace ``FLAG`` ``T`` (``0.0``), is ``"value"``.
    ``QUALITY`` (an integer written ``0.0`` ... ``5.0``) is kept in
    ``Measurement.quality`` and ``FLAG`` verbatim in
    ``Measurement.source_flag``, also codes unknown to ČHMÚ ``meta3``;
    neither changes the value or the flag. Rows may come in any order;
    explicit missing rows inside a block are records, and days without a
    row give no record.

    Parameters
    ----------
    content : bytes or str
        CSV content; bytes are decoded as UTF-8 (a leading BOM is allowed).
    filename : str
        File name or server path ending with ``dly-<WIGOS>-<ELEMENT>.csv``
        (element ``SRA``, ``T``, ``TMA`` or ``TMI``); it gives the station
        code and the element, and names the file in errors.

    Yields
    ------
    NormalizedRecord
        One record per date in date order: dataset ``"cz.chmi.meteo_daily"``,
        the hydrological year (November-October) of the date,
        ``period=None`` and the single variable of the file.

    Raises
    ------
    IMGWValidationError
        If ``filename`` does not end with a ČHMÚ daily element file name.
    IMGWDataError
        If the content is not UTF-8, the header is not
        ``STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY`` (with an optional
        empty eighth column), a row has a column count other than 7 or 8
        (eighth empty), ``STATION`` or ``ELEMENT`` differ from ``filename``,
        ``TIMEFUNC`` and the time of ``DT`` do not fit the element,
        ``VALUE`` is not numeric, ``QUALITY`` is not an integer, or one date
        has two different rows. The message names the file and the line.
    """
    match = _filename_match(filename, _CHMI_METEO_FILE, "dly-<kod>-<element>.csv")
    code, element = match.group(1), match.group(2)
    variable = ELEMENT_VARIABLES[element]
    timefunc, clock = _METEO_TIMING[element]
    reader = csv.reader(io.StringIO(_decode(content, filename)))
    by_day: dict[date, Measurement] = {}
    try:
        header = next(reader, None)
        if header is None or not (
            header[:7] == _CSV_HEADER and (len(header) == 7 or header[7:] == [""])
        ):
            shown = ",".join(header) if header is not None else ""
            raise _csv_error(
                filename,
                1,
                message(
                    "chmi.header_expected",
                    shown=shown,
                    csv_header=",".join(_CSV_HEADER),
                ),
            )
        for row in reader:
            line = reader.line_num
            if not row:
                continue
            if len(row) not in (7, 8) or row[7:] not in ([], [""]):
                raise _csv_error(
                    filename,
                    line,
                    message("chmi.columns_expected_7_eighth_empty", count=len(row)),
                )
            station, row_element, row_timefunc, moment = row[:4]
            if station != code:
                raise _csv_error(
                    filename,
                    line,
                    message(
                        "chmi.station_does_not_match_file", station=station, code=code
                    ),
                )
            if row_element != element:
                raise _csv_error(
                    filename,
                    line,
                    message(
                        "chmi.element_does_not_match_file",
                        row_element=row_element,
                        element=element,
                    ),
                )
            parts = _CSV_TIME.fullmatch(moment)
            try:
                day = date.fromisoformat(parts.group(1)) if parts else None
            except ValueError:
                day = None
            if parts is None or day is None:
                raise _csv_error(
                    filename, line, message("chmi.dt_not_utc_date", moment=moment)
                )
            seconds = parts.group(3)
            time = parts.group(2)
            if seconds not in (None, "00"):
                time = f"{time}:{seconds}"
            if element == "T" and row_timefunc in _T_TERMS and time == row_timefunc:
                continue
            if (row_timefunc, time) != (timefunc, clock):
                raise _csv_error(
                    filename,
                    line,
                    message(
                        "chmi.timefunc_dt_not_allowed_element",
                        row_timefunc=row_timefunc,
                        moment=moment,
                        element=element,
                    ),
                )
            try:
                measurement = _meteo_measurement(variable, *row[4:7])
            except ValueError as exc:
                raise _csv_error(filename, line, str(exc)) from exc
            previous = by_day.setdefault(day, measurement)
            if previous != measurement:
                raise _csv_error(
                    filename,
                    line,
                    message("chmi.repeated_date_has_different_value", day=day),
                )
    except csv.Error as exc:
        raise _csv_error(
            filename, reader.line_num, message("chmi.unreadable_csv", exc=reason(exc))
        ) from exc
    for day in sorted(by_day):
        yield NormalizedRecord(
            code, METEO_DATASET, day, _hydro_year(day), None, {variable: by_day[day]}
        )


# --------------------------------------------------------------------------
# Station metadata: meta1.json, meta3.json, meta1-<YYYYMMDD>.json
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MetadataTable:
    """
    Rows of one ČHMÚ metadata file, with columns located by name.

    The envelope (``zaznamID``, ``datumVytvoreni``, ...) is dropped; it
    never affects the content. Cell values are the JSON scalars of the file,
    with floats as :class:`decimal.Decimal` keeping the published notation
    (``14.170`` keeps three decimals) and integers as ``int``.

    Attributes
    ----------
    filename : str
        File name used in error messages.
    header : tuple of str
        Column names from ``data.data.header``.
    rows : tuple of tuple
        Rows of ``data.data.values``, each as long as ``header``.
    """

    filename: str
    header: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    _columns: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Index the columns by name."""
        columns = {name: index for index, name in enumerate(self.header)}
        object.__setattr__(self, "_columns", columns)

    def has(self, column: str) -> bool:
        """
        Whether the file has a column.

        Parameters
        ----------
        column : str
            Column name, e.g. ``"HLGP4"``.

        Returns
        -------
        bool
            True when ``column`` is in ``header``.
        """
        return column in self._columns

    def require(self, *columns: str) -> None:
        """
        Check that the file has every given column.

        Parameters
        ----------
        *columns : str
            Required column names.

        Raises
        ------
        IMGWDataError
            If a column is missing from the header.
        """
        missing = [column for column in columns if column not in self._columns]
        if missing:
            raise self.error(
                "data.data.header",
                message("chmi.missing_columns", columns=", ".join(missing)),
            )

    def text(self, index: int, column: str) -> str | None:
        """
        Text cell of a row; ``""`` and ``null`` are absent.

        Parameters
        ----------
        index : int
            Row index in ``rows``.
        column : str
            Column name.

        Returns
        -------
        str or None
            The text, None when empty or ``null``.

        Raises
        ------
        IMGWDataError
            If the column is missing or the cell is not a JSON string.
        """
        value = self._cell(index, column)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise self.cell_error(index, column, message("chmi.not_text", value=value))
        return value

    def number(self, index: int, column: str) -> Decimal | int | None:
        """
        Numeric cell of a row as published; ``""`` and ``null`` are absent.

        Parameters
        ----------
        index : int
            Row index in ``rows``.
        column : str
            Column name.

        Returns
        -------
        Decimal or int or None
            The number with its published notation, None when absent.

        Raises
        ------
        IMGWDataError
            If the column is missing or the cell is not a JSON number.
        """
        value = self._cell(index, column)
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, Decimal | int):
            raise self.cell_error(
                index, column, message("chmi.not_number", value=value)
            )
        return value

    def timestamp(self, index: int, column: str) -> datetime | None:
        """
        UTC timestamp cell (``YYYY-MM-DDTHH:MM:SSZ``); ``""`` and ``null`` are absent.

        Parameters
        ----------
        index : int
            Row index in ``rows``.
        column : str
            Column name, e.g. ``"BEGIN_DATE"``.

        Returns
        -------
        datetime or None
            Timezone-aware UTC time, None when absent.

        Raises
        ------
        IMGWDataError
            If the column is missing or the cell is not an ISO 8601 UTC time.
        """
        value = self.text(index, column)
        if value is None:
            return None
        moment = _utc_moment(value)
        if moment is None:
            raise self.cell_error(
                index, column, message("chmi.not_iso_8601_utc_time", value=value)
            )
        return moment

    def _cell(self, index: int, column: str) -> object:
        self.require(column)
        return self.rows[index][self._columns[column]]

    def cell_error(self, index: int, column: str, reason: str) -> IMGWDataError:
        """
        Error about one cell, naming the file, the JSON path and the column.

        Parameters
        ----------
        index : int
            Row index in ``rows``.
        column : str
            Column name (present in ``header``).
        reason : str
            Polish description of the problem.

        Returns
        -------
        IMGWDataError
            Error with ``details`` ``file`` and ``location``
            (``data.data.values[<row>][<column index>]``), to be raised.
        """
        location = f"data.data.values[{index}][{self._columns[column]}]"
        return self.error(location, f"{column}: {reason}")

    def error(self, location: str, reason: str) -> IMGWDataError:
        """
        Error about a place of the file.

        Parameters
        ----------
        location : str
            JSON path, e.g. ``data.data.values[3]``.
        reason : str
            Polish description of the problem.

        Returns
        -------
        IMGWDataError
            Error with ``details`` ``file`` and ``location``, to be raised.
        """
        return _metadata_error(self.filename, location, reason)


def read_metadata(content: bytes | str, /, *, filename: str) -> MetadataTable:
    """
    Read the table of a ČHMÚ metadata file.

    Parameters
    ----------
    content : bytes or str
        JSON content; bytes are decoded as UTF-8 (a leading BOM is allowed).
    filename : str
        File name used in error messages.

    Returns
    -------
    MetadataTable
        Header and rows of ``data.data``; floats as ``Decimal``.

    Raises
    ------
    IMGWDataError
        If the content is not UTF-8 JSON (duplicate keys and ``NaN`` are
        errors), lacks ``data.data.header``/``values``, the header has empty
        or repeated names, or a row length differs from the header.
    """
    root = _load_json(_decode(content, filename), filename, decimal=True)
    outer = root.get("data") if isinstance(root, dict) else None
    inner = outer.get("data") if isinstance(outer, dict) else None
    if not isinstance(inner, dict):
        raise _metadata_error(filename, "data.data", message("chmi.no_data_table"))
    header = inner.get("header")
    names = tuple(header.split(",")) if isinstance(header, str) else ()
    if not names or "" in names or len(set(names)) != len(names):
        raise _metadata_error(
            filename,
            "data.data.header",
            message("chmi.header_not_list_distinct_column", header=header),
        )
    values = inner.get("values")
    if not isinstance(values, list):
        raise _metadata_error(
            filename, "data.data.values", message("chmi.no_list_rows")
        )
    rows: list[tuple[object, ...]] = []
    for index, row in enumerate(values):
        if not isinstance(row, list) or len(row) != len(names):
            size = len(row) if isinstance(row, list) else "?"
            raise _metadata_error(
                filename,
                f"data.data.values[{index}]",
                message("chmi.row_has_fields_header_has", size=size, count=len(names)),
            )
        rows.append(tuple(row))
    return MetadataTable(filename, names, tuple(rows))


def _metadata_error(filename: str, location: str, reason: str) -> IMGWDataError:
    return IMGWDataError(
        message(
            "chmi.invalid_hm_metadata",
            filename=filename,
            location=location,
            reason=reason,
        ),
        details={"file": filename, "location": location},
    )


@dataclass(frozen=True)
class StationRows:
    """
    Row chosen for every station code of a metadata table.

    Attributes
    ----------
    rows : Mapping of str to int
        Station code → row index, in the order of first appearance.
    duplicates : tuple of str
        Codes repeated in the file outside the location periods of meteo
        ``historical/metadata/meta1.json``; the first row is used.
    """

    rows: Mapping[str, int]
    duplicates: tuple[str, ...]


def station_rows(
    table: MetadataTable, /, *, kind: Literal["hydro", "meteo"]
) -> StationRows:
    """
    Choose one row per station code.

    The code column is ``objID`` (hydro) or ``WSI`` (meteo). A file with an
    ``END_DATE`` column (meteo ``historical/metadata/meta1.json``) lists one
    row per location period by design: the period with the latest
    ``BEGIN_DATE`` is chosen (the first such row on a tie). In any other
    file a repeated code keeps its first row and is reported in
    ``duplicates``.

    Parameters
    ----------
    table : MetadataTable
        Metadata table.
    kind : {"hydro", "meteo"}
        Station family; selects the code column.

    Returns
    -------
    StationRows
        Chosen row of each code and the repeated codes.

    Raises
    ------
    IMGWDataError
        If the code column is missing or a code is empty, or a period row
        has no valid ``BEGIN_DATE``.
    """
    column = "objID" if kind == "hydro" else "WSI"
    table.require(column)
    periods = kind == "meteo" and table.has("END_DATE")
    chosen: dict[str, int] = {}
    begins: dict[str, datetime] = {}
    duplicates: list[str] = []
    for index in range(len(table.rows)):
        code = table.text(index, column)
        if code is None:
            raise table.cell_error(index, column, message("chmi.empty_station_code"))
        if periods:
            begin = table.timestamp(index, "BEGIN_DATE")
            if begin is None:
                raise table.cell_error(
                    index, "BEGIN_DATE", message("chmi.no_start_period")
                )
            if code not in begins or begin > begins[code]:
                chosen[code] = index
                begins[code] = begin
        elif code not in chosen:
            chosen[code] = index
        elif code not in duplicates:
            duplicates.append(code)
    return StationRows(chosen, tuple(duplicates))


def station_coordinates(
    table: MetadataTable, index: int, /, *, kind: Literal["hydro", "meteo"]
) -> tuple[Decimal | int | None, Decimal | int | None]:
    """
    Latitude and longitude of a row as published.

    ``GEOGR1``/``GEOGR2`` are latitude/longitude in hydrological files and
    longitude/latitude in meteorological files.

    Parameters
    ----------
    table : MetadataTable
        Metadata table with ``GEOGR1`` and ``GEOGR2``.
    index : int
        Row index.
    kind : {"hydro", "meteo"}
        Station family of the file.

    Returns
    -------
    tuple of (Decimal or int or None, Decimal or int or None)
        ``(latitude, longitude)``; None for ``""`` or ``null``.

    Raises
    ------
    IMGWDataError
        If a column is missing or a cell is not a number.
    """
    first, second = table.number(index, "GEOGR1"), table.number(index, "GEOGR2")
    return (first, second) if kind == "hydro" else (second, first)


def _degrees(
    table: MetadataTable, index: int, value: Decimal | int | None
) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise table.error(
            f"data.data.values[{index}]",
            message("chmi.coordinate_out_of_range", value=value),
        )
    return number


def iter_stations(
    content: bytes | str,
    /,
    *,
    kind: Literal["hydro", "meteo"],
    filename: str,
) -> Iterator[StationListEntry]:
    """
    Parse a ČHMÚ station metadata file, naming it in errors.

    Same as :func:`parse_chmi_stations`, for callers that know the file
    (store archive, live URL).

    Parameters
    ----------
    content : bytes or str
        JSON content of ``meta1.json``, ``meta3.json`` or
        ``meta1-<YYYYMMDD>.json``.
    kind : {"hydro", "meteo"}
        Station family of the file.
    filename : str
        File name or URL used in error messages.

    Yields
    ------
    StationListEntry
        One entry per station code, in the order of first appearance.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is neither ``"hydro"`` nor ``"meteo"``.
    IMGWDataError
        If the file is malformed (see :func:`read_metadata`), a required
        column is missing or a cell has the wrong type.
    """
    if kind not in ("hydro", "meteo"):
        raise IMGWValidationError(
            message("chmi.unknown_kind_station_list_allowed", kind=kind),
            details={"option": "kind", "value": kind, "allowed": ["hydro", "meteo"]},
        )
    table = read_metadata(content, filename=filename)
    if kind == "hydro":
        table.require("objID", "STATION_NAME", "STREAM_NAME", "GEOGR1", "GEOGR2")
    else:
        table.require("WSI", "FULL_NAME", "GEOGR1", "GEOGR2")
    name_column = "STATION_NAME" if kind == "hydro" else "FULL_NAME"
    hydrographic = kind == "hydro" and table.has("HLGP4")
    for code, index in station_rows(table, kind=kind).rows.items():
        latitude, longitude = station_coordinates(table, index, kind=kind)
        yield StationListEntry(
            kind,
            code,
            table.text(index, name_column) or "",
            river=table.text(index, "STREAM_NAME") if kind == "hydro" else None,
            hydrographic_code=table.text(index, "HLGP4") if hydrographic else None,
            latitude=_degrees(table, index, latitude),
            longitude=_degrees(table, index, longitude),
            provider=PROVIDER,
        )


def parse_chmi_stations(
    content: bytes | str, /, *, kind: Literal["hydro", "meteo"]
) -> Iterator[StationListEntry]:
    """
    Parse a ČHMÚ station metadata file into station list entries.

    Accepted files: hydro ``historical/metadata/meta1.json`` (dataset
    ``cz.chmi.hydro_stations``), ``now/metadata/meta1.json`` and
    ``meta3.json``; meteo ``historical/metadata/meta1.json`` (dataset
    ``cz.chmi.meteo_stations``) and ``now/metadata/meta1-<YYYYMMDD>.json``.
    Columns are located by name in the ``header`` of the envelope, whose
    other fields are ignored.

    - Hydro: code ``objID``, name ``STATION_NAME``, ``river`` =
      ``STREAM_NAME``, ``hydrographic_code`` = ``HLGP4`` as text (when the
      file has it), latitude ``GEOGR1`` and longitude ``GEOGR2``.
    - Meteo: code ``WSI``, name ``FULL_NAME``, longitude ``GEOGR1`` and
      latitude ``GEOGR2``; in ``historical/metadata/meta1.json`` (one row per
      location period) name and location come from the period with the
      latest ``BEGIN_DATE``.

    ``""`` and ``null`` cells are absent. A code repeated in one file
    (outside the meteo location periods) keeps its first row. Coordinates
    are returned as published, without validation against the country
    border; ``river_order`` and ``short_code`` are None.

    Parameters
    ----------
    content : bytes or str
        JSON content; bytes are decoded as UTF-8 (a leading BOM is allowed).
    kind : {"hydro", "meteo"}
        Station family of the file.

    Yields
    ------
    StationListEntry
        One entry per station code with ``provider="CHMI"``, in the order of
        first appearance.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is neither ``"hydro"`` nor ``"meteo"``.
    IMGWDataError
        If the content is not UTF-8 JSON with a ``data.data`` table, a
        required column is missing, a row length differs from the header or
        a cell has the wrong type.
    """
    yield from iter_stations(
        content,
        kind=kind,
        filename=message("chmi.station_metadata_label", kind=kind),
    )


# --------------------------------------------------------------------------
# Listings: nginx autoindex
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ListingEntry:
    """
    File row of an nginx autoindex directory listing.

    Attributes
    ----------
    name : str
        File name decoded from ``href`` (not the possibly shortened text).
    modified : datetime
        Modification time in UTC with minute precision (seconds zero); equal
        to the ``Last-Modified`` header truncated to the minute.
    size : int
        Exact size in bytes, equal to ``Content-Length``.
    """

    name: str
    modified: datetime
    size: int


def _listing_error(url: str, line: int, reason: str) -> IMGWDataError:
    return IMGWDataError(
        message("chmi.unreadable_listing_row", url=url, line=line, reason=reason),
        details={"url": url, "line": line},
    )


def parse_listing(html: str | bytes, /, *, url: str) -> tuple[ListingEntry, ...]:
    """
    Parse an nginx autoindex listing of a ČHMÚ directory.

    Rows have the form ``<a href="NAME">TEXT</a>   DD-Mon-YYYY HH:MM   SIZE``
    (times in UTC, size in bytes or ``-`` for a directory). The name comes
    from ``href`` after URL decoding; ``../`` and directories are skipped.

    Parameters
    ----------
    html : str or bytes
        Listing body; bytes are decoded as UTF-8.
    url : str
        Listing URL used in error messages.

    Returns
    -------
    tuple of ListingEntry
        Files in listing order.

    Raises
    ------
    IMGWDataError
        If the body has no file or directory row, a linked row lacks a valid
        time or size, a name does not decode to one path segment, or a name
        repeats.
    """
    if isinstance(html, bytes):
        try:
            html = html.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IMGWDataError(
                message(
                    "chmi.unreadable_listing_invalid_utf_8", url=url, start=exc.start
                ),
                details={"url": url, "byte": exc.start},
            ) from exc
    entries: list[ListingEntry] = []
    names: set[str] = set()
    rows = 0
    for line_number, line in enumerate(html.splitlines(), 1):
        anchor = _ANCHOR.search(line)
        if anchor is None or anchor.group(1) == "../":
            continue
        row = _LISTING_ROW.fullmatch(line, anchor.start())
        if row is None:
            raise _listing_error(
                url, line_number, message("chmi.row_without_time_size")
            )
        href, size = row.group("href"), row.group("size")
        directory = href.endswith("/")
        if directory != (size == "-"):
            raise _listing_error(
                url,
                line_number,
                message("chmi.size_does_not_match_kind", size=size, href=href),
            )
        try:
            modified = datetime(
                int(row.group("year")),
                _MONTHS[row.group("month")],
                int(row.group("day")),
                int(row.group("hour")),
                int(row.group("minute")),
                tzinfo=UTC,
            )
        except (KeyError, ValueError):
            modified = None
        if modified is None:
            raise _listing_error(
                url, line_number, message("chmi.invalid_modification_time")
            )
        rows += 1
        if directory:
            continue
        try:
            name = unquote(href, errors="strict")
        except UnicodeDecodeError:
            name = ""
        if name in ("", ".", "..") or "/" in name or "\x00" in name:
            raise _listing_error(
                url, line_number, message("chmi.invalid_name", href=href)
            )
        if name in names:
            raise _listing_error(
                url, line_number, message("chmi.repeated_name", name=name)
            )
        names.add(name)
        entries.append(ListingEntry(name, modified, int(size)))
    if rows == 0:
        raise IMGWDataError(
            message("chmi.unreadable_listing_no_file_directory", url=url),
            details={"url": url},
        )
    return tuple(entries)
