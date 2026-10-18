"""
Data fetching functions for IMGW public data.

Provides both synchronous and asynchronous versions of all fetch functions.
Data is fetched directly from IMGW servers - nothing is stored locally.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal
from zipfile import BadZipFile, ZipFile

import httpx

from imgwtools.core.url_builder import (
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    PMaXTPMethod,
    build_api_url,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
)
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWValidationError,
)
from imgwtools.models import (
    HydroCurrentData,
    PMaXTPData,
    PMaXTPResult,
    SynopData,
    WarningData,
)

if TYPE_CHECKING:
    pass

# Poland coordinate bounds
POLAND_LAT_MIN = 49.0
POLAND_LAT_MAX = 55.0
POLAND_LON_MIN = 14.0
POLAND_LON_MAX = 24.5

DEFAULT_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 120.0


@dataclass(frozen=True)
class DownloadResult:
    """Archive bytes and provenance from a single HTTP GET."""

    data: bytes
    url: str
    etag: str | None
    last_modified: str | None
    content_length: int | None


def _download_result(response: httpx.Response) -> DownloadResult:
    data = response.content
    try:
        ZipFile(BytesIO(data)).close()
    except BadZipFile as exc:
        raise IMGWDataError(
            f"Niepoprawne archiwum ZIP z adresu {response.url}"
        ) from exc
    length = response.headers.get("Content-Length")
    try:
        content_length = int(length) if length is not None else None
    except ValueError as exc:
        raise IMGWDataError(f"Niepoprawny nagłówek Content-Length: {length}") from exc
    return DownloadResult(
        data=data,
        url=str(response.url),
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        content_length=content_length,
    )


def _json_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise IMGWDataError(f"Niepoprawna odpowiedź JSON z {response.url}") from exc


def _validate_poland_coords(latitude: float, longitude: float) -> None:
    """Validate that coordinates are within Poland bounds."""
    if not (POLAND_LAT_MIN <= latitude <= POLAND_LAT_MAX):
        raise IMGWValidationError(
            f"Latitude {latitude} outside Poland bounds "
            f"({POLAND_LAT_MIN}-{POLAND_LAT_MAX})"
        )
    if not (POLAND_LON_MIN <= longitude <= POLAND_LON_MAX):
        raise IMGWValidationError(
            f"Longitude {longitude} outside Poland bounds "
            f"({POLAND_LON_MIN}-{POLAND_LON_MAX})"
        )


# ============================================================================
# PMAXTP (Probabilistic Maximum Precipitation)
# ============================================================================


def fetch_pmaxtp(
    latitude: float,
    longitude: float,
    method: Literal["POT", "AMP"] = "POT",
    *,
    timeout: float = DEFAULT_TIMEOUT,
    validate_coords: bool = True,
) -> PMaXTPResult:
    """
    Fetch PMAXTP (probabilistic maximum precipitation) data.

    PMAXTP provides precipitation quantiles for 7 durations and 6 probabilities,
    useful for hydrological modeling and flood risk assessment.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees (Poland: 49-55).
    longitude : float
        Longitude in decimal degrees (Poland: 14-24.5).
    method : {"POT", "AMP"}, optional
        Calculation method. "POT" (Peak Over Threshold) is recommended for
        most applications, "AMP" (Annual Max Precipitation) is an
        alternative method.
    timeout : float, optional
        Request timeout in seconds.
    validate_coords : bool, optional
        Whether to validate coordinates are within Poland.

    Returns
    -------
    PMaXTPResult
        Precipitation data including ks (quantiles [mm]), sg (upper
        confidence bounds [mm]) and rb (estimation errors [mm]).

    Raises
    ------
    IMGWValidationError
        If coordinates outside Poland bounds.
    IMGWConnectionError
        If connection to IMGW fails.
    IMGWDataError
        If response parsing fails.

    Examples
    --------
    >>> result = fetch_pmaxtp(52.23, 21.01, method="POT")
    >>> precip_15min_p50 = result.data.get_precipitation(15, 50)
    >>> print(f"15-min precipitation, p=50%: {precip_15min_p50} mm")

    Notes
    -----
    Data durations: 15, 30, 45, 60, 90, 120, 180 minutes.
    Probabilities: 1%, 2%, 5%, 10%, 20%, 50%.
    """
    if validate_coords:
        _validate_poland_coords(latitude, longitude)

    pmaxtp_method = PMaXTPMethod(method)
    url = build_pmaxtp_url(pmaxtp_method, latitude, longitude)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
    except httpx.HTTPStatusError as e:
        raise IMGWConnectionError(
            f"IMGW API error {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Connection error: {e}") from e

    try:
        return PMaXTPResult(
            method=method,
            latitude=latitude,
            longitude=longitude,
            data=PMaXTPData.from_api_response(raw_data),
        )
    except Exception as e:
        raise IMGWDataError(f"Failed to parse PMAXTP response: {e}") from e


async def fetch_pmaxtp_async(
    latitude: float,
    longitude: float,
    method: Literal["POT", "AMP"] = "POT",
    *,
    timeout: float = DEFAULT_TIMEOUT,
    validate_coords: bool = True,
) -> PMaXTPResult:
    """
    Async version of fetch_pmaxtp.

    See fetch_pmaxtp for full documentation.
    """
    if validate_coords:
        _validate_poland_coords(latitude, longitude)

    pmaxtp_method = PMaXTPMethod(method)
    url = build_pmaxtp_url(pmaxtp_method, latitude, longitude)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
        except httpx.HTTPStatusError as e:
            raise IMGWConnectionError(
                f"IMGW API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Connection error: {e}") from e

    try:
        return PMaXTPResult(
            method=method,
            latitude=latitude,
            longitude=longitude,
            data=PMaXTPData.from_api_response(raw_data),
        )
    except Exception as e:
        raise IMGWDataError(f"Failed to parse PMAXTP response: {e}") from e


# ============================================================================
# Real-time data (Hydro, Synop, Warnings)
# ============================================================================


def fetch_hydro_current(
    station_id: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroCurrentData]:
    """
    Fetch current hydrological data from IMGW API.

    Data includes water level, flow, and temperature for monitoring stations.

    Parameters
    ----------
    station_id : str or None, optional
        Station ID to filter results. If None, returns data for all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of HydroCurrentData
        Current measurements for the requested stations.

    Raises
    ------
    IMGWConnectionError
        If connection fails.
    IMGWDataError
        If response parsing fails.

    Examples
    --------
    >>> # Get all stations
    >>> stations = fetch_hydro_current()
    >>> print(f"Total stations: {len(stations)}")
    >>>
    >>> # Get specific station
    >>> warsaw = fetch_hydro_current(station_id="150160180")
    >>> print(f"Water level: {warsaw[0].water_level_cm} cm")
    """
    url = build_api_url("hydro", station_id=station_id)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Connection error: {e}") from e

    # API returns single object for specific station, list for all
    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    try:
        return [HydroCurrentData.from_api_response(item) for item in raw_data]
    except Exception as e:
        raise IMGWDataError(f"Failed to parse hydro response: {e}") from e


async def fetch_hydro_current_async(
    station_id: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroCurrentData]:
    """
    Async version of fetch_hydro_current.

    See fetch_hydro_current for full documentation.
    """
    url = build_api_url("hydro", station_id=station_id)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Connection error: {e}") from e

    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    try:
        return [HydroCurrentData.from_api_response(item) for item in raw_data]
    except Exception as e:
        raise IMGWDataError(f"Failed to parse hydro response: {e}") from e


def fetch_synop(
    station_id: str | None = None,
    station_name: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SynopData]:
    """
    Fetch current synoptic data from IMGW API.

    Synoptic data includes temperature, wind, humidity, precipitation, etc.

    Parameters
    ----------
    station_id : str or None, optional
        Station ID to filter results.
    station_name : str or None, optional
        Station name to filter results.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of SynopData
        Current synoptic measurements for the requested stations.

    Raises
    ------
    IMGWConnectionError
        If connection fails.
    IMGWDataError
        If response parsing fails.

    Examples
    --------
    >>> # Get all synop stations
    >>> stations = fetch_synop()
    >>>
    >>> # Get specific station by name
    >>> warszawa = fetch_synop(station_name="Warszawa")
    """
    # Note: IMGW synop API only supports station_id filter, not station_name
    # For station_name, we fetch all and filter locally
    url = build_api_url("synop", station_id=station_id)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Connection error: {e}") from e

    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    try:
        results = [SynopData.from_api_response(item) for item in raw_data]
    except Exception as e:
        raise IMGWDataError(f"Failed to parse synop response: {e}") from e

    # Filter by station_name if provided
    if station_name:
        results = [s for s in results if station_name.lower() in s.station_name.lower()]

    return results


async def fetch_synop_async(
    station_id: str | None = None,
    station_name: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SynopData]:
    """
    Async version of fetch_synop.

    See fetch_synop for full documentation.
    """
    url = build_api_url("synop", station_id=station_id)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Connection error: {e}") from e

    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    try:
        results = [SynopData.from_api_response(item) for item in raw_data]
    except Exception as e:
        raise IMGWDataError(f"Failed to parse synop response: {e}") from e

    if station_name:
        results = [s for s in results if station_name.lower() in s.station_name.lower()]

    return results


def fetch_warnings(
    warning_type: Literal["hydro", "meteo"] = "hydro",
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[WarningData]:
    """
    Fetch current weather or hydro warnings from IMGW.

    Parameters
    ----------
    warning_type : {"hydro", "meteo"}, optional
        Type of warnings to fetch.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of WarningData
        Active warnings. Empty list if there are none.

    Raises
    ------
    IMGWConnectionError
        If connection fails.
    IMGWDataError
        If the response is not valid JSON.

    Examples
    --------
    >>> warnings = fetch_warnings(warning_type="hydro")
    >>> for w in warnings:
    ...     print(f"Level {w.level}: {w.description}")
    """
    url = build_api_url(f"warnings/{warning_type}")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Connection error: {e}") from e

    if not raw_data:
        return []

    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    return [WarningData.from_api_response(item) for item in raw_data]


async def fetch_warnings_async(
    warning_type: Literal["hydro", "meteo"] = "hydro",
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[WarningData]:
    """
    Async version of fetch_warnings.

    See fetch_warnings for full documentation.
    """
    url = build_api_url(f"warnings/{warning_type}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            raw_data = _json_payload(response)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"IMGW API timeout: {e}") from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Connection error: {e}") from e

    if not raw_data:
        return []

    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    return [WarningData.from_api_response(item) for item in raw_data]


# ============================================================================
# Archive data download
# ============================================================================


def download_hydro_data(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int,
    month: int | None = None,
    param: Literal["T", "Q", "H"] | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Download hydrological archive data as ZIP bytes.

    Downloads ZIP file directly from IMGW servers containing CSV data.
    Use parse_zip_file() to extract and parse the data.

    Parameters
    ----------
    interval : {"dobowe", "miesieczne", "polroczne_i_roczne"}
        Data interval: daily, monthly or semi-annual/annual.
    year : int
        Hydrological year (1951-current).
    month : int or None, optional
        Month (1-12). Required for daily data before 2023.
    param : {"T", "Q", "H"} or None, optional
        Parameter for semi-annual data: "T" (temperature), "Q" (flow) or
        "H" (water level/depth).
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    DownloadResult
        Original ZIP bytes and response headers.

    Raises
    ------
    IMGWConnectionError
        If download fails.
    IMGWDataError
        If the downloaded data is not a ZIP archive.
    ValueError
        If required parameters are missing.

    Examples
    --------
    >>> # Download daily data for 2023
    >>> response = download_hydro_data("dobowe", 2023)
    >>>
    >>> # Parse the downloaded data
    >>> from imgwtools import parse_zip_file
    >>> for station, record in parse_zip_file(response.data, "dobowe"):
    ...     print(f"{station.station_name}: {record.water_level_cm} cm")
    """
    hydro_interval = HydroInterval(interval)
    hydro_param = HydroParam(param) if param else None

    url_info = build_hydro_url(hydro_interval, year, month, hydro_param)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url_info.url)
            response.raise_for_status()
            return _download_result(response)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"Przekroczono czas pobierania: {e}") from e
    except httpx.HTTPStatusError as e:
        raise IMGWConnectionError(
            f"Pobieranie nie powiodło się (HTTP {e.response.status_code}): {url_info.url}"
        ) from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Błąd pobierania: {e}") from e


async def download_hydro_data_async(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int,
    month: int | None = None,
    param: Literal["T", "Q", "H"] | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Async version of download_hydro_data.

    See download_hydro_data for full documentation.
    """
    hydro_interval = HydroInterval(interval)
    hydro_param = HydroParam(param) if param else None

    url_info = build_hydro_url(hydro_interval, year, month, hydro_param)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.get(url_info.url)
            response.raise_for_status()
            return _download_result(response)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"Przekroczono czas pobierania: {e}") from e
        except httpx.HTTPStatusError as e:
            raise IMGWConnectionError(
                f"Pobieranie nie powiodło się (HTTP {e.response.status_code}): {url_info.url}"
            ) from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Błąd pobierania: {e}") from e


def download_meteo_data(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"],
    year: int,
    month: int | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Download meteorological archive data as ZIP bytes.

    Downloads ZIP file directly from IMGW servers containing CSV data.

    Parameters
    ----------
    interval : {"dobowe", "miesieczne", "terminowe"}
        Data interval: daily, monthly or hourly.
    subtype : {"klimat", "opad", "synop"}
        Data subtype: climate, precipitation or synoptic.
    year : int
        Year (1951-current).
    month : int or None, optional
        Month (1-12). Required for daily/hourly data from 2001+.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    DownloadResult
        Original ZIP bytes and response headers.

    Raises
    ------
    IMGWConnectionError
        If download fails.
    IMGWDataError
        If the downloaded data is not a ZIP archive.
    ValueError
        If required parameters are missing.

    Examples
    --------
    >>> # Download monthly precipitation data
    >>> response = download_meteo_data("miesieczne", "opad", 2023)
    >>> response.data[:2]
    b'PK'
    """
    meteo_interval = MeteoInterval(interval)
    meteo_subtype = MeteoSubtype(subtype)

    url_info = build_meteo_url(meteo_interval, meteo_subtype, year, month)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url_info.url)
            response.raise_for_status()
            return _download_result(response)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"Przekroczono czas pobierania: {e}") from e
    except httpx.HTTPStatusError as e:
        raise IMGWConnectionError(
            f"Pobieranie nie powiodło się (HTTP {e.response.status_code}): {url_info.url}"
        ) from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Błąd pobierania: {e}") from e


async def download_meteo_data_async(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"],
    year: int,
    month: int | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Async version of download_meteo_data.

    See download_meteo_data for full documentation.
    """
    meteo_interval = MeteoInterval(interval)
    meteo_subtype = MeteoSubtype(subtype)

    url_info = build_meteo_url(meteo_interval, meteo_subtype, year, month)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.get(url_info.url)
            response.raise_for_status()
            return _download_result(response)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"Przekroczono czas pobierania: {e}") from e
        except httpx.HTTPStatusError as e:
            raise IMGWConnectionError(
                f"Pobieranie nie powiodło się (HTTP {e.response.status_code}): {url_info.url}"
            ) from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Błąd pobierania: {e}") from e
