"""Hydrological archive CSV parsers and normalization, without database dependencies."""

import csv
import io
import re
from collections.abc import Iterator
from datetime import date, datetime
from typing import Literal, overload

from imgwtools._parsing.common import (
    EXTREMUM_MAP,
    IMGW_ENCODING,
    MISSING_FLOW,
    MISSING_TEMP,
    MISSING_WATER_LEVEL,
    PERIOD_MAP,
    _decode_content,
    _detect_delimiter,
    _iter_rows,
    _safe_float,
    _safe_int,
    archive_csv_members,
    hydro_to_calendar_date,
)
from imgwtools.exceptions import IMGWDataError
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
    minimum = 8 if interval == "polroczne_i_roczne" else 9
    for number, row in _rows(content, encoding):
        if not any(field.strip() for field in row):
            continue
        if len(row) < minimum or _safe_int(row[3]) is None:
            if strict and row[0].strip().isdigit():
                raise IMGWDataError(f"Błędny rekord {filename}, wiersz {number}")
            continue  # existing hydro API ignores header and malformed legacy rows
        try:
            station, year = _base(row)
            code = station.station_code
            if strict and not re.fullmatch(r"\d{9}", code):
                raise ValueError("Niepoprawny kod stacji")
            if interval == "polroczne_i_roczne":
                period = PERIOD_MAP[int(row[4])]
                param = row[5].strip().strip('"').upper()
                if param not in {"H", "Q", "T"}:
                    raise ValueError("Nieznany parametr")
                extremum = EXTREMUM_MAP[int(row[6])]
                sentinel = {
                    "H": MISSING_WATER_LEVEL,
                    "Q": MISSING_FLOW,
                    "T": MISSING_TEMP,
                }[param]
                dates = []
                for offset in (8, 13):
                    parts = [_safe_int(value) for value in row[offset : offset + 5]]
                    if len(parts) < 3 or any(part is None for part in parts[:3]):
                        dates.append(None)
                    else:
                        value = f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
                        if (
                            len(parts) >= 5
                            and parts[3] is not None
                            and parts[4] is not None
                        ):
                            value += f" {parts[3]:02d}:{parts[4]:02d}"
                        datetime.fromisoformat(value)
                        dates.append(value)
                if strict and row[7].strip():
                    float(row[7])
                value = (
                    None
                    if row[7].strip() == "99999.999"
                    else _safe_float(row[7], sentinel)
                )
                record = HydroSemiAnnualRecord(
                    station_code=code,
                    hydro_year=year,
                    period=period,
                    param=param,
                    extremum=extremum,
                    value=value,
                    extremum_start_date=dates[0],
                    extremum_end_date=dates[1],
                )
            else:
                month = int(row[4])
                calendar_month = _safe_int(row[9]) if len(row) > 9 else None
                if strict:
                    for raw in row[6:9]:
                        if raw.strip():
                            float(raw)
                kwargs = {
                    "station_code": code,
                    "hydro_year": year,
                    "hydro_month": month,
                    "calendar_month": calendar_month,
                    "water_level_cm": _safe_float(row[6], MISSING_WATER_LEVEL),
                    "flow_m3s": _safe_float(row[7], MISSING_FLOW),
                    "water_temp_c": _safe_float(row[8], MISSING_TEMP),
                }
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
                    f"Błędny rekord {filename}, wiersz {number}: {exc}"
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

    CSV columns (18):
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

    Notes
    -----
    IMGW logs an extremum separately for every measurement interval in
    which it occurred, so a plateau (a peak or low that persists across
    several readings) yields multiple records sharing the same ``value``
    and differing only in ``extremum_start_date``. These are faithful,
    distinct source rows and are intentionally not deduplicated here.
    For example station ``150150070`` (Jelenia Gora), ``hydro_year=2023``,
    ``period='winter'``, ``extremum='max'``, ``value=40.0`` appears three
    times with ``extremum_start_date`` 2023-04-15 06:10, 06:30 and 06:50.

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
    """
    if interval not in {"dobowe", "miesieczne", "polroczne", "polroczne_i_roczne"}:
        raise ValueError(f"Nieznany interwał: {interval}")
    interval = "polroczne_i_roczne" if interval == "polroczne" else interval
    for _, content in archive_csv_members(zip_data):
        yield from _parse(content, interval)


def parse_stations_csv(
    content: str | bytes, encoding: str = IMGW_ENCODING
) -> Iterator[HydroArchiveStation]:
    """
    Parse station list CSV.

    CSV format (from lista_stacji_hydro.csv):
    1. ID
    2. Nazwa stacji
    3. Rzeka (kod hydrograficzny) - format: "Odra (1)"
    4. Kolejnosc (optional, kept as ``river_order``)

    Parameters
    ----------
    content : str or bytes
        CSV content.
    encoding : str, optional
        Character encoding used when ``content`` is bytes (default CP1250).

    Yields
    ------
    HydroArchiveStation
        Station parsed from a CSV row.
    """
    text = content if isinstance(content, str) else _decode_content(content, encoding)
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        raw_river = row[2].strip() if len(row) > 2 else ""
        match = re.match(r"^(.+?)\s*\((\d+)\)$", raw_river)
        order = row[3].strip() if len(row) > 3 else ""
        yield HydroArchiveStation(
            station_code=row[0].strip().strip('"'),
            station_name=row[1].strip().strip('"'),
            river_name=match.group(1).strip() if match else raw_river or None,
            hydrographic_code=match.group(2) if match else None,
            river_order=int(order) if order.isdecimal() else None,
        )


def _measurement(value: float | None) -> Measurement:
    return Measurement(value, "missing" if value is None else "value")


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
        one monthly variable receives two different values.
    """
    interval = {
        "pl.imgw.hydro_daily": "dobowe",
        "pl.imgw.hydro_monthly": "miesieczne",
        "pl.imgw.hydro_semiannual": "polroczne_i_roczne",
    }[dataset]
    monthly: dict[tuple[str, date], NormalizedRecord] = {}
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
                            f"Sprzeczne wartości {column} w {archive_name}/{member}"
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
                start_date = (
                    datetime.fromisoformat(record.extremum_start_date)
                    if record.extremum_start_date
                    else None
                )
                end_date = (
                    datetime.fromisoformat(record.extremum_end_date)
                    if record.extremum_end_date
                    else None
                )
                yield NormalizedRecord(
                    station.station_code,
                    dataset,
                    start,
                    record.hydro_year,
                    period,
                    {column: _measurement(record.value)},
                    extrema_dates={column: (start_date, end_date)},
                )
    yield from monthly.values()
