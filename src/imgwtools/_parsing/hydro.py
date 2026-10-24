"""Hydrological archive CSV parsers and normalization, without database dependencies."""

import calendar
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, overload

from imgwtools._parsing.common import (
    EXTREMUM_MAP,
    IMGW_ENCODING,
    MISSING_FLOW,
    MISSING_TEMP,
    MISSING_WATER_LEVEL,
    PERIOD_MAP,
    _decode_content,
    _detect_delimiter,
    _is_header_row,
    _iter_rows,
    _safe_float,
    _safe_int,
    archive_csv_members,
    hydro_to_calendar_date,
)
from imgwtools.exceptions import IMGWDataError
from imgwtools.messages import message, reason
from imgwtools.models import (
    HydroArchiveStation,
    HydroDailyRecord,
    HydroMonthlyRecord,
    HydroSemiAnnualRecord,
    Measurement,
    NormalizedRecord,
)


def _rows(content: str | bytes, encoding: str) -> Iterator[tuple[int, list[str]]]:
    text = content if isinstance(content, str) else _decode_content(content, encoding)
    yield from enumerate(_iter_rows(text.lstrip("\ufeff"), _detect_delimiter(text)), 1)


def _base(row: list[str]) -> tuple[HydroArchiveStation, int]:
    station = HydroArchiveStation(
        station_code=row[0].strip().strip('"'),
        station_name=row[1].strip().strip('"'),
        river_name=row[2].strip().strip('"'),
    )
    year = int(row[3])
    return station, year


@dataclass(frozen=True)
class _SemiAnnualLayout:
    """Positions of the extremum time fields in one IMGW ``polr`` CSV layout."""

    start: int  # first field (year) of the extremum start time
    end: int  # first field (year) of the extremum end time
    fields: int  # time fields of each date: 4 = Y,M,D,HH; 5 = Y,M,D,HH,MM
    extra: tuple[int, ...] = ()  # undocumented fields following the times (2023)


# Real polr_* layouts, keyed by the number of columns (official description
# POLR_publiczne_format.txt = 18 fields); trailing empty columns may be dropped.
_SEMI_ANNUAL_LAYOUTS = {
    8: _SemiAnnualLayout(8, 8, 0),  # no extremum time columns at all
    16: _SemiAnnualLayout(8, 12, 4),  # 1951-2022 except 1997: Y,M,D,HH twice
    17: _SemiAnnualLayout(8, 14, 5, (13,)),  # 2023 T: end time cut after the day
    18: _SemiAnnualLayout(8, 13, 5),  # 2024+: Y,M,D,HH,MM twice
    19: _SemiAnnualLayout(8, 14, 5, (13,)),  # 2023 Q: extra field after the start
    20: _SemiAnnualLayout(8, 14, 5, (13, 19)),  # 2023 H: extra field after each time
}
# 1997 (17 columns): the hydrological year repeated in field 9, then Y,M,D,HH twice.
_SEMI_ANNUAL_1997 = _SemiAnnualLayout(9, 13, 4)


def _text(cell: str) -> str:
    return cell.strip().strip('"')


def _semi_annual_layout(rows: list[list[str]], filename: str) -> _SemiAnnualLayout:
    """Detect the time-field layout of one ``polr`` file from all of its data rows."""
    widths = sorted({len(row) for row in rows})
    if len(widths) > 1:
        raise IMGWDataError(
            message(
                "hydro.inconsistent_number_columns",
                widths=", ".join(map(str, widths)),
                filename=filename,
            )
        )
    width = widths[0] if widths else 8
    if width == 17 and all(_text(row[8]) == _text(row[3]) for row in rows):
        return _SEMI_ANNUAL_1997
    layout = _SEMI_ANNUAL_LAYOUTS.get(width)
    if layout is None:
        raise IMGWDataError(
            message(
                "hydro.unknown_layout_semi_annual_file", width=width, filename=filename
            )
        )
    return layout


def _extremum_time(cells: list[str]) -> str | None:
    """
    IMGW extremum time fields as ``YYYY-MM-DD`` or ``YYYY-MM-DD HH:MM``.

    Fields are read up to the first empty one; a missing month or day is the
    first of the published unit, a day 29-31 beyond the end of a shorter month
    (IMGW writes e.g. ``09,31``) is its last day, a missing minute is ``00``
    and hour ``24`` (with minute ``00``) is the midnight ending that day.
    """
    parts: list[int] = []
    for cell in cells:
        text = _text(cell)
        if not text:
            break
        parts.append(int(text))
    if not parts:
        return None
    year, month, day = (parts + [1, 1])[:3]
    if 28 < day <= 31:
        day = min(day, calendar.monthrange(year, month)[1])
    moment = datetime(year, month, day)
    if len(parts) < 4:
        return moment.date().isoformat()
    hour, minute = (parts[3:] + [0])[:2]
    if (hour, minute) == (24, 0):
        moment += timedelta(days=1)
    else:
        moment = moment.replace(hour=hour, minute=minute)
    return moment.isoformat(sep=" ", timespec="minutes")


def _parse_semi_annual(
    content: str | bytes,
    encoding: str,
    *,
    filename: str | None,
    strict: bool,
) -> Iterator[tuple[HydroArchiveStation, HydroSemiAnnualRecord]]:
    rows: list[tuple[int, list[str]]] = []
    leading = True
    for number, row in _rows(content, encoding):
        if not any(field.strip() for field in row):
            continue
        header = leading and _is_header_row(row)
        leading = False
        if len(row) >= 8 and _safe_int(row[3]) is not None:
            rows.append((number, row))
        elif strict and not header:
            raise IMGWDataError(
                message("hydro.invalid_record_row", filename=filename, number=number)
            )
    layout = _semi_annual_layout(
        [row for _, row in rows], filename or message("hydro.csv_content")
    )
    for number, row in rows:
        try:
            station, year = _base(row)
            code = station.station_code
            if strict and not re.fullmatch(r"\d{9}", code):
                raise ValueError(message("hydro.invalid_station_code"))
            period = PERIOD_MAP[int(row[4])]
            param = row[5].strip().strip('"').upper()
            if param not in {"H", "Q", "T"}:
                raise ValueError(message("hydro.unknown_parameter"))
            extremum = EXTREMUM_MAP[int(row[6])]
            sentinel = {"H": MISSING_WATER_LEVEL, "Q": MISSING_FLOW, "T": MISSING_TEMP}[
                param
            ]
            for column in layout.extra:
                if column < len(row) and not re.fullmatch(r"\d?", _text(row[column])):
                    raise ValueError(
                        message(
                            "hydro.unknown_content_field",
                            field=column + 1,
                            content=row[column],
                        )
                    )
            start, end = (
                _extremum_time(row[offset : offset + layout.fields])
                for offset in (layout.start, layout.end)
            )
            if strict and row[7].strip():
                float(row[7])
            value = (
                None if row[7].strip() == "99999.999" else _safe_float(row[7], sentinel)
            )
        except (IndexError, ValueError, KeyError) as exc:
            if strict:
                raise IMGWDataError(
                    message(
                        "hydro.invalid_record_row_2",
                        filename=filename,
                        number=number,
                        exc=reason(exc),
                    )
                ) from exc
            continue
        yield (
            station,
            HydroSemiAnnualRecord(
                station_code=code,
                hydro_year=year,
                period=period,
                param=param,
                extremum=extremum,
                value=value,
                extremum_start_date=start,
                extremum_end_date=end,
            ),
        )


@overload
def _parse(
    content: str | bytes,
    interval: Literal["dobowe"],
    encoding: str = ...,
    *,
    filename: str | None = ...,
    strict: bool = ...,
) -> Iterator[tuple[HydroArchiveStation, HydroDailyRecord]]: ...


@overload
def _parse(
    content: str | bytes,
    interval: Literal["miesieczne"],
    encoding: str = ...,
    *,
    filename: str | None = ...,
    strict: bool = ...,
) -> Iterator[tuple[HydroArchiveStation, HydroMonthlyRecord]]: ...


@overload
def _parse(
    content: str | bytes,
    interval: Literal["polroczne_i_roczne"],
    encoding: str = ...,
    *,
    filename: str | None = ...,
    strict: bool = ...,
) -> Iterator[tuple[HydroArchiveStation, HydroSemiAnnualRecord]]: ...


@overload
def _parse(
    content: str | bytes,
    interval: str,
    encoding: str = ...,
    *,
    filename: str | None = ...,
    strict: bool = ...,
) -> Iterator[
    tuple[
        HydroArchiveStation,
        HydroDailyRecord | HydroMonthlyRecord | HydroSemiAnnualRecord,
    ]
]: ...


def _parse(
    content: str | bytes,
    interval: str,
    encoding: str = IMGW_ENCODING,
    *,
    filename: str | None = None,
    strict: bool = False,
) -> Iterator[
    tuple[
        HydroArchiveStation,
        HydroDailyRecord | HydroMonthlyRecord | HydroSemiAnnualRecord,
    ]
]:
    if interval == "polroczne_i_roczne":
        yield from _parse_semi_annual(
            content, encoding, filename=filename, strict=strict
        )
        return
    for number, row in _rows(content, encoding):
        if not any(field.strip() for field in row):
            continue
        if len(row) < 9 or _safe_int(row[3]) is None:
            if strict and row[0].strip().isdigit():
                raise IMGWDataError(
                    message(
                        "hydro.invalid_record_row", filename=filename, number=number
                    )
                )
            continue  # existing hydro API ignores header and malformed legacy rows
        try:
            station, year = _base(row)
            code = station.station_code
            if strict and not re.fullmatch(r"\d{9}", code):
                raise ValueError(message("hydro.invalid_station_code"))
            month = int(row[4])
            calendar_month = _safe_int(row[9]) if len(row) > 9 else None
            if strict:
                for raw in row[6:9]:
                    if raw.strip():
                        float(raw)
            kwargs: dict[str, Any] = {
                "station_code": code,
                "hydro_year": year,
                "hydro_month": month,
                "calendar_month": calendar_month,
                "water_level_cm": _safe_float(row[6], MISSING_WATER_LEVEL),
                "flow_m3s": _safe_float(row[7], MISSING_FLOW),
                "water_temp_c": _safe_float(row[8], MISSING_TEMP),
            }
            record: HydroDailyRecord | HydroMonthlyRecord
            if interval == "dobowe":
                day = int(row[5])
                measured = hydro_to_calendar_date(year, month, day)
                record = HydroDailyRecord(
                    **kwargs, day=day, measurement_date=measured.isoformat()
                )
            else:
                record = HydroMonthlyRecord(
                    **kwargs, extremum=EXTREMUM_MAP[int(row[5])]
                )
            yield station, record
        except (IndexError, ValueError, KeyError) as exc:
            if strict:
                raise IMGWDataError(
                    message(
                        "hydro.invalid_record_row_2",
                        filename=filename,
                        number=number,
                        exc=reason(exc),
                    )
                ) from exc


def parse_daily_csv(
    content: str | bytes, encoding: str = IMGW_ENCODING
) -> Iterator[tuple[HydroArchiveStation, HydroDailyRecord]]:
    """
    Parse daily hydrological data CSV.

    CSV columns (10):
    1. Kod stacji
    2. Nazwa stacji
    3. Nazwa rzeki/jeziora
    4. Rok hydrologiczny
    5. Wskaznik miesiaca w roku hydrologicznym
    6. Dzien
    7. Stan wody [cm]
    8. Przeplyw [m3/s]
    9. Temperatura wody [deg C]
    10. Miesiac kalendarzowy

    Parameters
    ----------
    content : str or bytes
        CSV content.
    encoding : str, optional
        Character encoding used when ``content`` is bytes (default CP1250).

    Yields
    ------
    tuple of (HydroArchiveStation, HydroDailyRecord)
        Station metadata paired with its daily record.
    """
    yield from _parse(content, "dobowe", encoding)


def parse_monthly_csv(
    content: str | bytes, encoding: str = IMGW_ENCODING
) -> Iterator[tuple[HydroArchiveStation, HydroMonthlyRecord]]:
    """
    Parse monthly hydrological data CSV.

    CSV columns (10):
    1. Kod stacji
    2. Nazwa stacji
    3. Nazwa rzeki/jeziora
    4. Rok hydrologiczny
    5. Wskaznik miesiaca w roku hydrologicznym
    6. Wskaznik ekstremum (1=min, 2=mean, 3=max)
    7. Stan wody [cm]
    8. Przeplyw [m3/s]
    9. Temperatura wody [deg C]
    10. Miesiac kalendarzowy

    Parameters
    ----------
    content : str or bytes
        CSV content.
    encoding : str, optional
        Character encoding used when ``content`` is bytes (default CP1250).

    Yields
    ------
    tuple of (HydroArchiveStation, HydroMonthlyRecord)
        Station metadata paired with its monthly record.
    """
    yield from _parse(content, "miesieczne", encoding)


def parse_semi_annual_csv(
    content: str | bytes, encoding: str = IMGW_ENCODING
) -> Iterator[tuple[HydroArchiveStation, HydroSemiAnnualRecord]]:
    """
    Parse semi-annual/annual hydrological data CSV.

    CSV columns (official 18-field layout, 2024 onward):
    1. Kod stacji
    2. Nazwa stacji
    3. Nazwa rzeki/jeziora
    4. Rok hydrologiczny
    5. Wskaznik polrocza (13=winter, 14=summer, 15=annual)
    6. Rodzaj wielkosci (H, Q, T)
    7. Wskaznik ekstremum (1=min, 2=mean, 3=max)
    8. Wartosc
    9-13. Data ekstremum od (rok, miesiac, dzien, godzina, minuta)
    14-18. Data ekstremum do (rok, miesiac, dzien, godzina, minuta)

    Older archives use other layouts, detected per file from the number of
    columns: 16 columns (1951-2022) carry year, month, day and hour without
    minutes; 1997 (17 columns) repeats the hydrological year before the
    dates; 2023 adds an undocumented field (empty or a digit, ignored) after
    each date and drops trailing empty columns (17, 19 or 20 columns). A
    leading row of column codes (2024) is skipped.

    Parameters
    ----------
    content : str or bytes
        CSV content.
    encoding : str, optional
        Character encoding used when ``content`` is bytes (default CP1250).

    Yields
    ------
    tuple of (HydroArchiveStation, HydroSemiAnnualRecord)
        Station metadata paired with its semi-annual record.

    Raises
    ------
    IMGWDataError
        If the data rows differ in their number of columns or the number of
        columns matches no known layout.

    Notes
    -----
    Extremum dates are read up to the first empty field, so they carry the
    precision published by IMGW: a missing month or day becomes the first of
    the published unit (``1952,01,,`` gives ``1952-01-01``), a day 29-31
    beyond the end of a shorter month (``09,31``) its last day, a published
    hour without minutes ``HH:00`` and hour 24 midnight of the next day.

    IMGW logs an extremum separately for every measurement interval in
    which it occurred, so a plateau (a peak or low that persists across
    several readings) yields multiple records sharing the same ``value``
    and differing only in ``extremum_start_date``. These are faithful,
    distinct source rows and are intentionally not deduplicated here
    (``normalize_archive`` merges them). For example station ``150150070``
    (Jelenia Gora), ``hydro_year=2023``, ``period='winter'``,
    ``extremum='max'``, ``value=40.0`` appears three times with
    ``extremum_start_date`` 2023-04-15 06:10, 06:30 and 06:50.

    For ``extremum='mean'`` both ``extremum_start_date`` and
    ``extremum_end_date`` are ``None`` (a half-year mean has no single
    moment of occurrence; only ``min``/``max`` carry dates), and ``value``
    may be ``None`` for missing data.

    Consumers deriving annual characteristics (WQ = annual max, NQ =
    annual min, etc.) are unaffected by plateau duplicates when using
    ``max()``/``min()``, but must deduplicate by ``(period, extremum)``
    before any ``sum``/``count``.
    """
    yield from _parse(content, "polroczne_i_roczne", encoding)


def parse_zip_file(
    zip_data: bytes, interval: str
) -> Iterator[
    tuple[
        HydroArchiveStation,
        HydroDailyRecord | HydroMonthlyRecord | HydroSemiAnnualRecord,
    ]
]:
    """
    Parse hydrological data from ZIP file.

    Parameters
    ----------
    zip_data : bytes
        ZIP file content.
    interval : str
        Data interval ('dobowe', 'miesieczne', 'polroczne' or
        'polroczne_i_roczne').

    Yields
    ------
    tuple of (HydroArchiveStation, record)
        Station metadata paired with the parsed record.

    Raises
    ------
    ValueError
        If ``interval`` is not a hydrological archive interval.
    IMGWDataError
        If a semi-annual CSV has no known column layout (see
        ``parse_semi_annual_csv``).
    """
    if interval not in {"dobowe", "miesieczne", "polroczne", "polroczne_i_roczne"}:
        raise ValueError(f"Unknown interval: {interval}")
    interval = "polroczne_i_roczne" if interval == "polroczne" else interval
    for _, content in archive_csv_members(zip_data):
        yield from _parse(content, interval)


def _measurement(value: float | None) -> Measurement:
    return Measurement(value, "missing" if value is None else "value")


def _moment(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _earliest(first: datetime | None, second: datetime | None) -> datetime | None:
    return second if first is None else first if second is None else min(first, second)


def _latest(first: datetime | None, second: datetime | None) -> datetime | None:
    return second if first is None else first if second is None else max(first, second)


@dataclass
class _SemiAnnualValue:
    """IMGW rows of one station, period and column merged into a single value."""

    period: Literal["winter", "summer", "annual"]
    start: date  # period start
    measurement: Measurement
    first: datetime | None  # earliest extremum start
    last: datetime | None  # latest extremum end
    occurrences: int = 1


def normalize_hydro_archive(
    dataset: str, archive_name: str, data: bytes
) -> Iterator[NormalizedRecord]:
    """
    Normalize a hydrological IMGW archive into common measurement records.

    Every CSV member is parsed strictly. Each value becomes a
    ``Measurement`` flagged ``"value"`` or, when absent or equal to the IMGW
    missing-data code, ``"missing"``.

    - Daily data: one record per station and day, dated with the calendar
      date, with variables ``H``, ``Q`` and ``T``.
    - Monthly data: one record per station and month, dated with the first
      day of the calendar month, with variables ``H_min``, ``H_mean``,
      ``H_max`` (and likewise for ``Q`` and ``T``) merged from the separate
      min/mean/max rows. Monthly records are yielded after all members have
      been read.
    - Semi-annual data: one record per station, period, parameter and
      extremum, dated with the period start (November 1 for winter and
      annual, May 1 for summer), carrying ``period``, a single variable such
      as ``Q_max`` and its extremum start/end datetimes in ``extrema_dates``.
      IMGW repeats a min/max row for every occurrence of the extremum; such
      rows with the same value are merged into one record with the earliest
      start, the latest end and the number of rows in
      ``extrema_occurrences``. Semi-annual records are yielded after all
      members have been read.

    Parameters
    ----------
    dataset : str
        Dataset key of the archive (``"pl.imgw.hydro_daily"``,
        ``"pl.imgw.hydro_monthly"`` or ``"pl.imgw.hydro_semiannual"``); stored
        on every yielded record.
    archive_name : str
        Archive name used in error messages.
    data : bytes
        ZIP archive content.

    Yields
    ------
    NormalizedRecord
        Normalized hydrological record.

    Raises
    ------
    KeyError
        If ``dataset`` is not a hydrological dataset key.
    IMGWDataError
        If the archive is unreadable or unsafe, a data row is malformed, or
        one monthly or semi-annual variable receives two different values.
    """
    interval = {
        "pl.imgw.hydro_daily": "dobowe",
        "pl.imgw.hydro_monthly": "miesieczne",
        "pl.imgw.hydro_semiannual": "polroczne_i_roczne",
    }[dataset]
    monthly: dict[tuple[str, date], NormalizedRecord] = {}
    semi_annual: dict[tuple[str, int, str, str], _SemiAnnualValue] = {}
    for member, content in archive_csv_members(data, filename=archive_name):
        for station, record in _parse(
            content, interval, filename=f"{archive_name}/{member}", strict=True
        ):
            if isinstance(record, HydroDailyRecord):
                measured = hydro_to_calendar_date(
                    record.hydro_year, record.hydro_month, record.day
                )
                values = {
                    key: _measurement(getattr(record, attr))
                    for key, attr in (
                        ("H", "water_level_cm"),
                        ("Q", "flow_m3s"),
                        ("T", "water_temp_c"),
                    )
                }
                yield NormalizedRecord(
                    station.station_code,
                    dataset,
                    measured,
                    record.hydro_year,
                    None,
                    values,
                )
            elif isinstance(record, HydroMonthlyRecord):
                measured = hydro_to_calendar_date(
                    record.hydro_year, record.hydro_month, 1
                )
                key = (station.station_code, measured)
                existing = monthly.get(key)
                values = dict(existing.measurements) if existing else {}
                for name, field in (
                    ("H", "water_level_cm"),
                    ("Q", "flow_m3s"),
                    ("T", "water_temp_c"),
                ):
                    column = f"{name}_{record.extremum}"
                    value = _measurement(getattr(record, field))
                    if column in values and values[column] != value:
                        raise IMGWDataError(
                            message(
                                "hydro.conflicting_values",
                                column=column,
                                archive_name=archive_name,
                                member=member,
                            )
                        )
                    values[column] = value
                monthly[key] = NormalizedRecord(
                    station.station_code,
                    dataset,
                    measured,
                    record.hydro_year,
                    None,
                    values,
                )
            else:
                starts: dict[
                    str, tuple[Literal["winter", "summer", "annual"], date]
                ] = {
                    "winter": ("winter", date(record.hydro_year - 1, 11, 1)),
                    "summer": ("summer", date(record.hydro_year, 5, 1)),
                    "annual": ("annual", date(record.hydro_year - 1, 11, 1)),
                }
                period, start = starts[record.period]
                column = f"{record.param}_{record.extremum}"
                measurement = _measurement(record.value)
                first = _moment(record.extremum_start_date)
                last = _moment(record.extremum_end_date)
                semi_key = (station.station_code, record.hydro_year, period, column)
                merged = semi_annual.get(semi_key)
                if merged is None:
                    semi_annual[semi_key] = _SemiAnnualValue(
                        period, start, measurement, first, last
                    )
                    continue
                if merged.measurement != measurement:
                    raise IMGWDataError(
                        message(
                            "hydro.conflicting_values_station",
                            column=column,
                            station_code=station.station_code,
                            period=period,
                            hydro_year=record.hydro_year,
                            archive_name=archive_name,
                            member=member,
                        )
                    )
                merged.first = _earliest(merged.first, first)
                merged.last = _latest(merged.last, last)
                merged.occurrences += 1
    yield from monthly.values()
    for (code, hydro_year, _, column), merged in semi_annual.items():
        yield NormalizedRecord(
            code,
            dataset,
            merged.start,
            hydro_year,
            merged.period,
            {column: merged.measurement},
            extrema_dates={column: (merged.first, merged.last)},
            extrema_occurrences={column: merged.occurrences},
        )
