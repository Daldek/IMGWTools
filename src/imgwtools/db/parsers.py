"""
Parsers for IMGW hydrological data CSV files.

Handles parsing CSV files from IMGW ZIP archives with proper encoding
(CP1250) and missing data detection.
"""

import csv
import io
from collections.abc import Iterator
from zipfile import ZipFile

__all__ = [
    "IMGW_ENCODING",
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
]

from imgwtools.db.models import (
    EXTREMUM_MAP,
    MISSING_FLOW,
    MISSING_TEMP,
    MISSING_WATER_LEVEL,
    PERIOD_MAP,
    HydroDailyRecord,
    HydroMonthlyRecord,
    HydroSemiAnnualRecord,
    HydroStation,
    hydro_to_calendar_date,
)

# Default encoding for IMGW CSV files
IMGW_ENCODING = "cp1250"


def _safe_float(value: str, missing_value: float) -> float | None:
    """
    Parse float value, returning None for missing data.

    Args:
        value: String value to parse.
        missing_value: Value that indicates missing data.

    Returns:
        Parsed float or None if empty/missing.
    """
    if not value or not value.strip():
        return None

    try:
        f = float(value.strip())
        # Check if it's a missing data indicator
        if abs(f - missing_value) < 0.001:
            return None
        return f
    except ValueError:
        return None


def _safe_int(value: str) -> int | None:
    """Parse integer value, returning None if invalid."""
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def parse_daily_csv(
    content: str | bytes,
    encoding: str = IMGW_ENCODING,
) -> Iterator[tuple[HydroStation, HydroDailyRecord]]:
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
    9. Temperatura wody [°C]
    10. Miesiac kalendarzowy

    Args:
        content: CSV content as string or bytes.
        encoding: Character encoding (default CP1250).

    Yields:
        Tuples of (station, daily_record).
    """
    if isinstance(content, bytes):
        content = content.decode(encoding)

    # IMGW CSV files use semicolon as delimiter
    reader = csv.reader(io.StringIO(content), delimiter=";")

    for row in reader:
        if len(row) < 9:
            continue

        try:
            station_code = row[0].strip().strip('"')
            station_name = row[1].strip().strip('"')
            river_name = row[2].strip().strip('"') if len(row) > 2 else None

            hydro_year = _safe_int(row[3])
            hydro_month = _safe_int(row[4])
            day = _safe_int(row[5])

            if not all([hydro_year, hydro_month, day]):
                continue

            water_level = _safe_float(row[6], MISSING_WATER_LEVEL)
            flow = _safe_float(row[7], MISSING_FLOW)
            water_temp = _safe_float(row[8], MISSING_TEMP)

            calendar_month = _safe_int(row[9]) if len(row) > 9 else None

            # Calculate measurement date
            try:
                date_obj = hydro_to_calendar_date(hydro_year, hydro_month, day)
                measurement_date = date_obj.isoformat()
            except (ValueError, KeyError):
                measurement_date = None

            station = HydroStation(
                station_code=station_code,
                station_name=station_name,
                river_name=river_name,
            )

            record = HydroDailyRecord(
                station_code=station_code,
                hydro_year=hydro_year,
                hydro_month=hydro_month,
                day=day,
                calendar_month=calendar_month,
                water_level_cm=water_level,
                flow_m3s=flow,
                water_temp_c=water_temp,
                measurement_date=measurement_date,
            )

            yield station, record

        except (IndexError, ValueError):
            # Skip malformed rows
            continue


def parse_monthly_csv(
    content: str | bytes,
    encoding: str = IMGW_ENCODING,
) -> Iterator[tuple[HydroStation, HydroMonthlyRecord]]:
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
    9. Temperatura wody [°C]
    10. Miesiac kalendarzowy

    Args:
        content: CSV content as string or bytes.
        encoding: Character encoding (default CP1250).

    Yields:
        Tuples of (station, monthly_record).
    """
    if isinstance(content, bytes):
        content = content.decode(encoding)

    # IMGW CSV files use semicolon as delimiter
    reader = csv.reader(io.StringIO(content), delimiter=";")

    for row in reader:
        if len(row) < 9:
            continue

        try:
            station_code = row[0].strip().strip('"')
            station_name = row[1].strip().strip('"')
            river_name = row[2].strip().strip('"') if len(row) > 2 else None

            hydro_year = _safe_int(row[3])
            hydro_month = _safe_int(row[4])
            extremum_code = _safe_int(row[5])

            if not all([hydro_year, hydro_month, extremum_code]):
                continue

            extremum = EXTREMUM_MAP.get(extremum_code, "mean")

            water_level = _safe_float(row[6], MISSING_WATER_LEVEL)
            flow = _safe_float(row[7], MISSING_FLOW)
            water_temp = _safe_float(row[8], MISSING_TEMP)

            calendar_month = _safe_int(row[9]) if len(row) > 9 else None

            station = HydroStation(
                station_code=station_code,
                station_name=station_name,
                river_name=river_name,
            )

            record = HydroMonthlyRecord(
                station_code=station_code,
                hydro_year=hydro_year,
                hydro_month=hydro_month,
                calendar_month=calendar_month,
                extremum=extremum,
                water_level_cm=water_level,
                flow_m3s=flow,
                water_temp_c=water_temp,
            )

            yield station, record

        except (IndexError, ValueError):
            continue


def parse_semi_annual_csv(
    content: str | bytes,
    encoding: str = IMGW_ENCODING,
) -> Iterator[tuple[HydroStation, HydroSemiAnnualRecord]]:
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

    Args:
        content: CSV content as string or bytes.
        encoding: Character encoding (default CP1250).

    Yields:
        Tuples of (station, semi_annual_record).
    """
    if isinstance(content, bytes):
        content = content.decode(encoding)

    # IMGW CSV files use semicolon as delimiter
    reader = csv.reader(io.StringIO(content), delimiter=";")

    for row in reader:
        if len(row) < 8:
            continue

        try:
            station_code = row[0].strip().strip('"')
            station_name = row[1].strip().strip('"')
            river_name = row[2].strip().strip('"') if len(row) > 2 else None

            hydro_year = _safe_int(row[3])
            period_code = _safe_int(row[4])
            param = row[5].strip().strip('"').upper() if len(row) > 5 else None
            extremum_code = _safe_int(row[6])

            if not all([hydro_year, period_code, param, extremum_code]):
                continue

            period = PERIOD_MAP.get(period_code, "annual")
            extremum = EXTREMUM_MAP.get(extremum_code, "mean")

            # Determine missing value based on param type
            if param == "H":
                missing = MISSING_WATER_LEVEL
            elif param == "Q":
                missing = MISSING_FLOW
            else:  # T
                missing = MISSING_TEMP

            value = _safe_float(row[7], missing)

            # Parse extremum dates if available
            extremum_start_date = None
            extremum_end_date = None

            if len(row) >= 13:
                start_parts = [_safe_int(row[i]) for i in range(8, 13)]
                if all(p is not None for p in start_parts[:3]):
                    extremum_start_date = f"{start_parts[0]:04d}-{start_parts[1]:02d}-{start_parts[2]:02d}"
                    if start_parts[3] is not None and start_parts[4] is not None:
                        extremum_start_date += f" {start_parts[3]:02d}:{start_parts[4]:02d}"

            if len(row) >= 18:
                end_parts = [_safe_int(row[i]) for i in range(13, 18)]
                if all(p is not None for p in end_parts[:3]):
                    extremum_end_date = f"{end_parts[0]:04d}-{end_parts[1]:02d}-{end_parts[2]:02d}"
                    if end_parts[3] is not None and end_parts[4] is not None:
                        extremum_end_date += f" {end_parts[3]:02d}:{end_parts[4]:02d}"

            station = HydroStation(
                station_code=station_code,
                station_name=station_name,
                river_name=river_name,
            )

            record = HydroSemiAnnualRecord(
                station_code=station_code,
                hydro_year=hydro_year,
                period=period,
                param=param,
                extremum=extremum,
                value=value,
                extremum_start_date=extremum_start_date,
                extremum_end_date=extremum_end_date,
            )

            yield station, record

        except (IndexError, ValueError):
            continue


def parse_zip_file(
    zip_data: bytes,
    interval: str,
) -> Iterator[tuple[HydroStation, HydroDailyRecord | HydroMonthlyRecord | HydroSemiAnnualRecord]]:
    """
    Parse hydrological data from ZIP file.

    Args:
        zip_data: ZIP file content as bytes.
        interval: Data interval ('dobowe', 'miesieczne', 'polroczne').

    Yields:
        Tuples of (station, record).
    """
    parser_map = {
        "dobowe": parse_daily_csv,
        "miesieczne": parse_monthly_csv,
        "polroczne": parse_semi_annual_csv,
        "polroczne_i_roczne": parse_semi_annual_csv,
    }

    parser = parser_map.get(interval)
    if not parser:
        raise ValueError(f"Unknown interval: {interval}")

    with ZipFile(io.BytesIO(zip_data)) as zf:
        for name in zf.namelist():
            if name.endswith(".csv"):
                with zf.open(name) as f:
                    content = f.read()
                    yield from parser(content)


def parse_stations_csv(
    content: str | bytes,
    encoding: str = IMGW_ENCODING,
) -> Iterator[HydroStation]:
    """
    Parse station list CSV.

    CSV format (from lista_stacji_hydro.csv):
    1. ID
    2. Nazwa stacji
    3. Rzeka (ID cieku) - format: "Odra (1)"
    4. Kod (optional)

    Args:
        content: CSV content as string or bytes.
        encoding: Character encoding (default CP1250).

    Yields:
        HydroStation objects.
    """
    import re

    if isinstance(content, bytes):
        content = content.decode(encoding)

    reader = csv.reader(io.StringIO(content))

    for row in reader:
        if len(row) < 2:
            continue

        try:
            station_code = row[0].strip().strip('"')
            station_name = row[1].strip().strip('"')

            river_name = None
            if len(row) > 2:
                river_raw = row[2].strip().strip('"')
                # Parse "Odra (1)" format
                match = re.match(r"^(.+?)\s*\(\d+\)$", river_raw)
                if match:
                    river_name = match.group(1).strip()
                else:
                    river_name = river_raw

            yield HydroStation(
                station_code=station_code,
                station_name=station_name,
                river_name=river_name,
            )

        except (IndexError, ValueError):
            continue
