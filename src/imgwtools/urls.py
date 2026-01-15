"""
URL builders for IMGW public data resources.

This module re-exports all URL building functions and types from core.url_builder
for a cleaner public API.

Example:
    >>> from imgwtools.urls import build_hydro_url, HydroInterval
    >>> url = build_hydro_url(HydroInterval.DAILY, 2023)
    >>> print(url.url)
"""

from imgwtools.core.url_builder import (
    # Constants
    IMGW_API_URL,
    IMGW_PMAXTP_URL,
    IMGW_PUBLIC_DATA_URL,
    # Enums
    DataType,
    # Types
    DownloadURL,
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    PMaXTPMethod,
    # Functions
    build_api_url,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    get_available_years,
)

__all__ = [
    # Constants
    "IMGW_PUBLIC_DATA_URL",
    "IMGW_API_URL",
    "IMGW_PMAXTP_URL",
    # Enums
    "DataType",
    "HydroInterval",
    "MeteoInterval",
    "MeteoSubtype",
    "HydroParam",
    "PMaXTPMethod",
    # Types
    "DownloadURL",
    # Functions
    "build_hydro_url",
    "build_meteo_url",
    "build_pmaxtp_url",
    "build_api_url",
    "get_available_years",
]
