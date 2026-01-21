"""
Module: url_builder

Builds URLs for IMGW public data resources.
This is the core module for generating direct download links to IMGW servers.
"""

from dataclasses import dataclass
from enum import Enum


class DataType(str, Enum):
    """Type of IMGW data."""
    HYDRO = "dane_hydrologiczne"
    METEO = "dane_meteorologiczne"


class HydroInterval(str, Enum):
    """Interval for hydrological data."""
    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    SEMI_ANNUAL = "polroczne_i_roczne"


class MeteoInterval(str, Enum):
    """Interval for meteorological data."""
    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    HOURLY = "terminowe"


class MeteoSubtype(str, Enum):
    """Subtype of meteorological data."""
    CLIMATE = "klimat"
    PRECIPITATION = "opad"
    SYNOP = "synop"


class HydroParam(str, Enum):
    """Parameter for semi-annual/annual hydrological data."""
    TEMPERATURE = "T"
    FLOW = "Q"
    DEPTH = "H"


class PMaXTPMethod(str, Enum):
    """Method for PMAXTP data."""
    POT = "POT"  # Peak Over Threshold
    AMP = "AMP"  # Annual Max Precipitation


@dataclass
class DownloadURL:
    """Result of URL building."""
    url: str
    filename: str
    data_type: str
    interval: str
    year: int
    month: int | None = None


# Base URLs for IMGW services
IMGW_PUBLIC_DATA_URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
IMGW_API_URL = "https://danepubliczne.imgw.pl/api/data"
IMGW_PMAXTP_URL = "https://powietrze.imgw.pl/tpmax-api/point"


def _get_meteo_folder(year: int) -> str:
    """
    Get folder name for meteorological data.

    For years 1951-2000: returns 5-year range folder (e.g., "1951_1955", "1956_1960")
    For years 2001+: returns year as string (e.g., "2023")

    Args:
        year: Year of data

    Returns:
        Folder name for the given year
    """
    if year <= 2000:
        # Calculate 5-year range: 1951-1955, 1956-1960, ..., 1996-2000
        # Start years: 1951, 1956, 1961, ..., 1996
        start_year = ((year - 1951) // 5) * 5 + 1951
        end_year = start_year + 4
        return f"{start_year}_{end_year}"
    else:
        return str(year)


def build_hydro_url(
    interval: HydroInterval,
    year: int,
    month: int | None = None,
    param: HydroParam | None = None,
) -> DownloadURL:
    """
    Build URL for hydrological data download.

    Args:
        interval: Data interval (daily, monthly, semi-annual)
        year: Hydrological year (1951-2023)
        month: Month number (1-12 for daily, 13 for phenomena). Required for daily.
        param: Parameter (T, Q, H). Required for semi-annual.

    Returns:
        DownloadURL with direct link to IMGW server.

    Raises:
        ValueError: If required parameters are missing.
    """
    base = f"{IMGW_PUBLIC_DATA_URL}/{DataType.HYDRO.value}"

    if interval == HydroInterval.DAILY:
        if month == 13:
            # Phenomena data - always yearly file
            filename = f"zjaw_{year}.zip"
        elif year >= 2023:
            # From 2023: single file per year (no monthly split)
            # Month parameter is ignored for year >= 2023
            filename = f"codz_{year}.zip"
        else:
            # Before 2023: monthly files
            if month is None:
                raise ValueError("Month is required for daily data before 2023")
            month_str = f"{month:02d}"
            filename = f"codz_{year}_{month_str}.zip"

        url = f"{base}/{interval.value}/{year}/{filename}"

    elif interval == HydroInterval.MONTHLY:
        filename = f"mies_{year}.zip"
        url = f"{base}/{interval.value}/{year}/{filename}"

    elif interval == HydroInterval.SEMI_ANNUAL:
        if param is None:
            raise ValueError("Parameter (T, Q, H) is required for semi-annual data")

        filename = f"polr_{param.value}_{year}.zip"
        url = f"{base}/{interval.value}/{year}/{filename}"

    else:
        raise ValueError(f"Unknown interval: {interval}")

    return DownloadURL(
        url=url,
        filename=filename,
        data_type=DataType.HYDRO.value,
        interval=interval.value,
        year=year,
        month=month,
    )


def build_meteo_url(
    interval: MeteoInterval,
    subtype: MeteoSubtype,
    year: int,
    month: int | None = None,
) -> DownloadURL:
    """
    Build URL for meteorological data download.

    Args:
        interval: Data interval (daily, monthly, hourly)
        subtype: Data subtype (climate, precipitation, synop)
        year: Year (1951-current)
        month: Month number (1-12). Required for daily/hourly data from 2001+.

    Returns:
        DownloadURL with direct link to IMGW server.

    Raises:
        ValueError: If required parameters are missing.

    Note:
        For years 1951-2000: data in 5-year folders, yearly files (no monthly split).
        For years 2001+: data in yearly folders, monthly files.
    """
    base = f"{IMGW_PUBLIC_DATA_URL}/{DataType.METEO.value}"

    # Get subtype abbreviation
    subtype_abbr = subtype.value[0]  # k, o, s

    # Get folder name (5-year range for 1951-2000, year for 2001+)
    folder = _get_meteo_folder(year)

    if year <= 2000:
        # 1951-2000: yearly files in 5-year folders (no monthly split)
        filename = f"{year}_{subtype_abbr}.zip"
    elif interval == MeteoInterval.DAILY:
        # 2001+: monthly files
        if month is None:
            raise ValueError("Month is required for daily data from 2001+")
        month_str = f"{month:02d}"
        filename = f"{year}_{month_str}_{subtype_abbr}.zip"

    elif interval == MeteoInterval.MONTHLY:
        filename = f"{year}_m_{subtype_abbr}.zip"

    elif interval == MeteoInterval.HOURLY:
        if month is None:
            raise ValueError("Month is required for hourly data from 2001+")
        month_str = f"{month:02d}"
        filename = f"{year}_{month_str}_{subtype_abbr}.zip"

    else:
        raise ValueError(f"Unknown interval: {interval}")

    url = f"{base}/{interval.value}/{subtype.value}/{folder}/{filename}"

    return DownloadURL(
        url=url,
        filename=filename,
        data_type=DataType.METEO.value,
        interval=interval.value,
        year=year,
        month=month if year > 2000 else None,
    )


def build_pmaxtp_url(
    method: PMaXTPMethod,
    latitude: float,
    longitude: float,
) -> str:
    """
    Build URL for PMAXTP (probabilistic max precipitation) API.

    Args:
        method: Calculation method (POT or AMP)
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees

    Returns:
        URL for PMAXTP API endpoint.
    """
    lat_str = f"{latitude:.4f}"
    lon_str = f"{longitude:.4f}"

    return f"{IMGW_PMAXTP_URL}/{method.value[0]}/KS/{lat_str}/{lon_str}"


def build_api_url(
    endpoint: str,
    station_id: str | None = None,
    station_name: str | None = None,
) -> str:
    """
    Build URL for IMGW real-time API.

    Args:
        endpoint: API endpoint (hydro, synop, meteo, warnings/hydro, warnings/meteo)
        station_id: Station ID (optional)
        station_name: Station name (optional, for synop)

    Returns:
        URL for IMGW API endpoint.
    """
    url = f"{IMGW_API_URL}/{endpoint}"

    if station_id:
        url += f"/id/{station_id}"
    elif station_name:
        url += f"/station/{station_name}"

    return url


def get_available_years(data_type: DataType, interval: str) -> tuple[int, int]:
    """
    Get the range of available years for a given data type and interval.

    Args:
        data_type: Type of data (hydro or meteo)
        interval: Data interval

    Returns:
        Tuple of (start_year, end_year)
    """
    import datetime
    current_year = datetime.datetime.now().year

    if data_type == DataType.HYDRO:
        return (1951, current_year)
    else:
        # Meteo data available from 1951 (in 5-year folders until 2000)
        return (1951, current_year)
