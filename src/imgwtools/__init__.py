"""
IMGWTools - Python library for accessing IMGW public data.

IMGW (Institute of Meteorology and Water Management) provides public
hydrological and meteorological data for Poland. This library provides
easy access to that data.

Quick Start:
    >>> from imgwtools import fetch_pmaxtp, list_hydro_stations
    >>>
    >>> # Get PMAXTP data for Warsaw
    >>> result = fetch_pmaxtp(latitude=52.23, longitude=21.01)
    >>> precip = result.data.get_precipitation(15, 50)
    >>> print(f"15-min precipitation, p=50%: {precip} mm")
    >>>
    >>> # List hydro stations
    >>> stations = list_hydro_stations()
    >>> print(f"Total stations: {len(stations)}")

Features:
    - PMAXTP data (probabilistic maximum precipitation)
    - Current hydrological data (water levels, flows)
    - Current synoptic data (temperature, wind, precipitation)
    - Weather and hydro warnings
    - Archive data download (daily, monthly, semi-annual)
    - Station listings with coordinates

Installation:
    pip install imgwtools           # Core library only
    pip install imgwtools[cli]      # With CLI
    pip install imgwtools[api]      # With REST API server
    pip install imgwtools[full]     # All features
"""

from imgwtools._version import __version__

# Exceptions
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWError,
    IMGWValidationError,
)

# Fetch functions
from imgwtools.fetch import (
    download_hydro_data,
    download_hydro_data_async,
    download_meteo_data,
    download_meteo_data_async,
    fetch_hydro_current,
    fetch_hydro_current_async,
    fetch_pmaxtp,
    fetch_pmaxtp_async,
    fetch_synop,
    fetch_synop_async,
    fetch_warnings,
    fetch_warnings_async,
)

# Data models
from imgwtools.models import (
    HydroCurrentData,
    PMaXTPData,
    PMaXTPResult,
    SynopData,
    WarningData,
)

# Parsers
from imgwtools.parsers import (
    IMGW_ENCODING,
    parse_daily_csv,
    parse_monthly_csv,
    parse_semi_annual_csv,
    parse_stations_csv,
    parse_zip_file,
)

# Station functions
from imgwtools.stations import (
    HydroStation,
    MeteoStation,
    get_hydro_stations_with_coords,
    get_hydro_stations_with_coords_async,
    list_hydro_stations,
    list_hydro_stations_async,
    list_meteo_stations,
    list_meteo_stations_async,
)

# URL builders and types
from imgwtools.urls import (
    IMGW_API_URL,
    IMGW_PMAXTP_URL,
    IMGW_PUBLIC_DATA_URL,
    DataType,
    DownloadURL,
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    PMaXTPMethod,
    build_api_url,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    get_available_years,
)

__all__ = [
    # Version
    "__version__",
    # Exceptions
    "IMGWError",
    "IMGWConnectionError",
    "IMGWDataError",
    "IMGWValidationError",
    # Models
    "PMaXTPData",
    "PMaXTPResult",
    "HydroCurrentData",
    "SynopData",
    "WarningData",
    # URL builders
    "build_hydro_url",
    "build_meteo_url",
    "build_pmaxtp_url",
    "build_api_url",
    "get_available_years",
    # URL types and enums
    "DownloadURL",
    "DataType",
    "HydroInterval",
    "MeteoInterval",
    "MeteoSubtype",
    "HydroParam",
    "PMaXTPMethod",
    # URL constants
    "IMGW_PUBLIC_DATA_URL",
    "IMGW_API_URL",
    "IMGW_PMAXTP_URL",
    # Fetch functions (sync)
    "fetch_pmaxtp",
    "fetch_hydro_current",
    "fetch_synop",
    "fetch_warnings",
    "download_hydro_data",
    "download_meteo_data",
    # Fetch functions (async)
    "fetch_pmaxtp_async",
    "fetch_hydro_current_async",
    "fetch_synop_async",
    "fetch_warnings_async",
    "download_hydro_data_async",
    "download_meteo_data_async",
    # Station functions (sync)
    "list_hydro_stations",
    "list_meteo_stations",
    "get_hydro_stations_with_coords",
    # Station functions (async)
    "list_hydro_stations_async",
    "list_meteo_stations_async",
    "get_hydro_stations_with_coords_async",
    # Station types
    "HydroStation",
    "MeteoStation",
    # Parsers
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
    "IMGW_ENCODING",
]
