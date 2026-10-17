"""Public parsers for IMGW archive files and normalized measurements.

Examples
--------
>>> from imgwtools import download_hydro_data, parse_zip_file
>>> response = download_hydro_data("dobowe", 2023)
>>> for station, record in parse_zip_file(response.data, "dobowe"):
...     print(f"{station.station_name}: {record.water_level_cm} cm")
"""

from imgwtools._parsing import normalize_archive
from imgwtools._parsing.common import IMGW_ENCODING
from imgwtools._parsing.hydro import (
    parse_daily_csv,
    parse_monthly_csv,
    parse_semi_annual_csv,
    parse_stations_csv,
    parse_zip_file,
)
from imgwtools._parsing.meteo import parse_meteo_climate_daily, parse_meteo_precip_daily

__all__ = [
    "IMGW_ENCODING",
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
    "parse_meteo_climate_daily",
    "parse_meteo_precip_daily",
    "normalize_archive",
]
