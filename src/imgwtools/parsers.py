"""Public parsers for IMGW-PIB and ČHMÚ source files and normalized measurements.

Examples
--------
>>> from imgwtools import download_hydro_data, parse_zip_file
>>> response = download_hydro_data("dobowe", 2023)
>>> for station, record in parse_zip_file(response.data, "dobowe"):
...     print(f"{station.station_name}: {record.water_level_cm} cm")

>>> from imgwtools.parsers import parse_chmi_hydro_daily
>>> name = "H_0-203-1-001000_DQ_2025.json"
>>> for record in parse_chmi_hydro_daily(content, filename=name):
...     print(record.date, record.measurements["Q"].value)
"""

from imgwtools._parsing import normalize_archive
from imgwtools._parsing.chmi import (
    parse_chmi_hydro_daily,
    parse_chmi_meteo_daily,
    parse_chmi_stations,
)
from imgwtools._parsing.common import IMGW_ENCODING
from imgwtools._parsing.hydro import (
    parse_daily_csv,
    parse_monthly_csv,
    parse_semi_annual_csv,
    parse_zip_file,
)
from imgwtools._parsing.meteo import parse_meteo_climate_daily, parse_meteo_precip_daily
from imgwtools._parsing.stations import parse_stations_csv

__all__ = [
    "IMGW_ENCODING",
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
    "parse_meteo_climate_daily",
    "parse_meteo_precip_daily",
    "parse_chmi_hydro_daily",
    "parse_chmi_meteo_daily",
    "parse_chmi_stations",
    "normalize_archive",
]
