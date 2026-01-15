"""
CSV parsers for IMGW data files.

This module re-exports parsing functions from db.parsers for a cleaner public API.
Use these functions to parse data downloaded from IMGW servers.

Example:
    >>> from imgwtools import download_hydro_data, parse_zip_file
    >>> zip_data = download_hydro_data("dobowe", 2023)
    >>> for station, record in parse_zip_file(zip_data, "dobowe"):
    ...     print(f"{station.name}: {record.water_level_cm} cm")
"""

from imgwtools.db.parsers import (
    IMGW_ENCODING,
    parse_daily_csv,
    parse_monthly_csv,
    parse_semi_annual_csv,
    parse_stations_csv,
    parse_zip_file,
)

__all__ = [
    "IMGW_ENCODING",
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
]
