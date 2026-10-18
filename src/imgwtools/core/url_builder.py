"""
Builders of URLs for IMGW public data resources.

This is the core module for generating direct download links to IMGW servers.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from imgwtools.exceptions import IMGWValidationError


class DataType(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Type of IMGW data."""

    HYDRO = "dane_hydrologiczne"
    METEO = "dane_meteorologiczne"


class HydroInterval(str, Enum):  # noqa: UP042
    """Interval for hydrological data."""

    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    SEMI_ANNUAL = "polroczne_i_roczne"


class MeteoInterval(str, Enum):  # noqa: UP042
    """Interval for meteorological data."""

    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    HOURLY = "terminowe"


class MeteoSubtype(str, Enum):  # noqa: UP042
    """Subtype of meteorological data."""

    CLIMATE = "klimat"
    PRECIPITATION = "opad"
    SYNOP = "synop"


class HydroParam(str, Enum):  # noqa: UP042
    """Parameter for semi-annual/annual hydrological data."""

    TEMPERATURE = "T"
    FLOW = "Q"
    DEPTH = "H"


class PMaXTPMethod(str, Enum):  # noqa: UP042
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
_PMAXTP_METHODS = ("POT", "AMP")


def _get_meteo_folder(year: int, subtype: MeteoSubtype) -> str:
    """
    Get folder name for meteorological data.

    For years 1951-2000: returns 5-year range folder (e.g., "1951_1955", "1956_1960")
    For years 2001+: returns year as string (e.g., "2023")

    The first folder of the grid differs per subtype on IMGW servers
    (verified against live directory listings):
    klimat starts at "1951_1955", opad at "1950_1955" and synop at
    "1960_1965" (six years); from 1966 onward all subtypes share the
    same "1966_1970", "1971_1975", ... grid.

    Parameters
    ----------
    year : int
        Year of data.
    subtype : MeteoSubtype
        Data subtype (folder grids differ before 1966).

    Returns
    -------
    str
        Folder name for the given year.
    """
    if year > 2000:
        return str(year)

    if subtype == MeteoSubtype.PRECIPITATION and year <= 1955:
        return "1950_1955"
    if subtype == MeteoSubtype.SYNOP and year <= 1965:
        return "1960_1965"

    # Standard 5-year grid: 1951-1955, 1956-1960, ..., 1996-2000
    # Start years: 1951, 1956, 1961, ..., 1996
    start_year = ((year - 1951) // 5) * 5 + 1951
    end_year = start_year + 4
    return f"{start_year}_{end_year}"


def build_hydro_url(
    interval: HydroInterval,
    year: int,
    month: int | None = None,
    param: HydroParam | None = None,
) -> DownloadURL:
    """
    Build URL for hydrological data download.

    Parameters
    ----------
    interval : HydroInterval
        Data interval (daily, monthly, semi-annual).
    year : int
        Hydrological year (1951-current).
    month : int or None, optional
        Month number (1-12 for daily, 13 for phenomena). Required for daily.
    param : HydroParam or None, optional
        Parameter (T, Q, H). Required for semi-annual.

    Returns
    -------
    DownloadURL
        Direct link to the IMGW server.

    Raises
    ------
    ValueError
        If required parameters are missing.
    """
    base = f"{IMGW_PUBLIC_DATA_URL}/{DataType.HYDRO.value}"

    if interval == HydroInterval.DAILY and month == 13:
        # Legacy phenomenon files are outside the store datasets.
        filename = f"zjaw_{year}.zip"
        url = f"{base}/{interval.value}/{year}/{filename}"
    elif interval in (
        HydroInterval.DAILY,
        HydroInterval.MONTHLY,
        HydroInterval.SEMI_ANNUAL,
    ):
        from imgwtools.datasets import archive_files
        from imgwtools.exceptions import IMGWValidationError

        if interval == HydroInterval.DAILY and year < 2023 and month is None:
            raise ValueError("Month is required for daily data before 2023")
        if interval == HydroInterval.SEMI_ANNUAL and param is None:
            raise ValueError("Parameter (T, Q, H) is required for semi-annual data")
        dataset = {
            HydroInterval.DAILY: "pl.imgw.hydro_daily",
            HydroInterval.MONTHLY: "pl.imgw.hydro_monthly",
            HydroInterval.SEMI_ANNUAL: "pl.imgw.hydro_semiannual",
        }[interval]
        try:
            files = archive_files(
                dataset, years=[year], months=[month] if month is not None else None
            )
        except IMGWValidationError as exc:
            raise ValueError(str(exc)) from exc
        archive = next(
            (item for item in files if param is None or item.param == param.value), None
        )
        if archive is None:
            raise ValueError(f"Unknown parameter: {param}")
        url = archive.url
        filename = archive.server_path.rsplit("/", 1)[-1]
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

    Parameters
    ----------
    interval : MeteoInterval
        Data interval (daily, monthly, hourly).
    subtype : MeteoSubtype
        Data subtype (climate, precipitation, synop).
    year : int
        Year (1951-current).
    month : int or None, optional
        Month number (1-12). Required for daily/hourly data from 2001+.

    Returns
    -------
    DownloadURL
        Direct link to the IMGW server.

    Raises
    ------
    ValueError
        If required parameters are missing or the requested dataset does not
        exist on IMGW servers (hourly precipitation; daily/hourly synop,
        which is published as per-station files).

    Notes
    -----
    Real IMGW folder layout (verified against live server listings):

    - monthly: one file per folder ("{folder}_m_{k|o|s}.zip") - the
      folder is a 5-year range until 2000 and the year from 2001;
    - daily/hourly klimat and opad: yearly files ("{year}_{k|o}.zip")
      until 2000, monthly files ("{year}_{month:02d}_{k|o}.zip") from 2001;
    - daily/hourly synop: per-station files ("{folder}_{station}_s.zip")
      - not supported here;
    - hourly opad: dataset does not exist.
    """
    base = f"{IMGW_PUBLIC_DATA_URL}/{DataType.METEO.value}"

    # Combinations that do not exist on IMGW servers
    if interval == MeteoInterval.HOURLY and subtype == MeteoSubtype.PRECIPITATION:
        raise ValueError(
            "Hourly (terminowe) precipitation data does not exist on IMGW servers"
        )
    if subtype == MeteoSubtype.SYNOP and interval in (
        MeteoInterval.DAILY,
        MeteoInterval.HOURLY,
    ):
        raise ValueError(
            "Daily and hourly synop archives are published as per-station files "
            "(e.g. 2023_100_s.zip); single-URL generation is not supported - "
            "use the monthly interval instead"
        )
    if subtype == MeteoSubtype.SYNOP and year < 1960:
        raise ValueError("Synop archives are available from 1960 onward")

    # Supported daily datasets use the canonical registry for layout.
    if interval == MeteoInterval.DAILY and subtype in (
        MeteoSubtype.CLIMATE,
        MeteoSubtype.PRECIPITATION,
    ):
        from imgwtools.datasets import archive_files
        from imgwtools.exceptions import IMGWValidationError

        if year >= 2001 and month is None:
            raise ValueError("Month is required for daily/hourly data from 2001+")
        dataset = (
            "pl.imgw.meteo_climate_daily"
            if subtype == MeteoSubtype.CLIMATE
            else "pl.imgw.meteo_precip_daily"
        )
        try:
            archive = archive_files(
                dataset, years=[year], months=[month] if month is not None else None
            )[0]
        except IMGWValidationError as exc:
            raise ValueError(str(exc)) from exc
        filename = archive.server_path.rsplit("/", 1)[-1]
        url = archive.url
    else:
        # Monthly/terminowe and synop URLs remain live legacy APIs.
        subtype_abbr = subtype.value[0]
        folder = _get_meteo_folder(year, subtype)
        if interval == MeteoInterval.MONTHLY:
            filename = f"{folder}_m_{subtype_abbr}.zip"
        elif year <= 2000:
            filename = f"{year}_{subtype_abbr}.zip"
        elif interval == MeteoInterval.HOURLY:
            if month is None:
                raise ValueError("Month is required for daily/hourly data from 2001+")
            filename = f"{year}_{month:02d}_{subtype_abbr}.zip"
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
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
) -> str:
    """
    Build URL for PMAXTP (probabilistic max precipitation) API.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees.
    longitude : float
        Longitude in decimal degrees.
    method : {"POT", "AMP"}, optional
        Calculation method: peaks over threshold (default) or annual maxima.

    Returns
    -------
    str
        URL for the PMAXTP API endpoint.

    Raises
    ------
    IMGWValidationError
        If ``method`` is not ``"POT"`` or ``"AMP"`` (``details`` ``option`` and
        ``allowed``).
    """
    if method not in _PMAXTP_METHODS:
        raise IMGWValidationError(
            f"Nieznana metoda PMAXTP: {method!r}; dozwolone POT, AMP",
            details={"option": "method", "allowed": list(_PMAXTP_METHODS)},
        )
    return f"{IMGW_PMAXTP_URL}/{method[0]}/KS/{latitude:.4f}/{longitude:.4f}"


def build_api_url(
    endpoint: str,
    /,
    *,
    station: str | None = None,
    station_name: str | None = None,
) -> str:
    """
    Build URL for IMGW real-time API.

    Parameters
    ----------
    endpoint : str
        API endpoint (``hydro``, ``meteo``, ``synop``, ``warningshydro``,
        ``warningsmeteo``).
    station : str or None, optional
        Station code; takes precedence over ``station_name``.
    station_name : str or None, optional
        Station name (for synop).

    Returns
    -------
    str
        URL for the IMGW API endpoint.
    """
    url = f"{IMGW_API_URL}/{endpoint}"

    if station:
        url += f"/id/{station}"
    elif station_name:
        url += f"/station/{station_name}"

    return url


def get_available_years(data_type: DataType, interval: str) -> tuple[int, int]:
    """
    Get the range of available years for a given data type and interval.

    Parameters
    ----------
    data_type : DataType
        Type of data (hydro or meteo).
    interval : str
        Data interval.

    Returns
    -------
    tuple of (int, int)
        Pair of (start_year, end_year).
    """
    import datetime

    current_year = datetime.datetime.now().year

    if data_type == DataType.HYDRO:
        return (1951, current_year)
    else:
        # Meteo data available from 1951 (in 5-year folders until 2000)
        return (1951, current_year)
