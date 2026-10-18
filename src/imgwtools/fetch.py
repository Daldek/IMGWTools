"""
Data fetching functions for IMGW public data.

Provides both synchronous and asynchronous versions of all fetch functions.
Data is fetched directly from IMGW servers - nothing is stored locally.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal, cast
from zipfile import BadZipFile, ZipFile

import httpx
from pydantic import ValidationError

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
    MeteoCurrentData,
    PMaXTPData,
    PMaXTPResult,
    SynopData,
    WarningData,
)

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


def _source_error(exc: httpx.HTTPError, url: str) -> IMGWConnectionError:
    """
    Map a failed request to an IMGW server to ``source_unavailable``.

    Parameters
    ----------
    exc : httpx.HTTPError
        Timeout, network error or HTTP 4xx/5xx status of the request.
    url : str
        Requested URL, reported in ``details["url"]``.

    Returns
    -------
    IMGWConnectionError
        Error with ``details`` ``url``, ``reason`` (``timeout``, ``network``
        or ``http_status``) and, for an HTTP status, ``status``.
    """
    if isinstance(exc, httpx.TimeoutException):
        return IMGWConnectionError(
            f"Przekroczono czas oczekiwania na serwer IMGW: {url}",
            details={"url": url, "reason": "timeout"},
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return IMGWConnectionError(
            f"Serwer IMGW zwrócił HTTP {status}: {url}",
            details={"url": url, "reason": "http_status", "status": status},
        )
    return IMGWConnectionError(
        f"Błąd połączenia z serwerem IMGW ({exc}): {url}",
        details={"url": url, "reason": "network"},
    )


def _get(
    url: str, *, timeout: float, headers: Mapping[str, str] | None = None
) -> httpx.Response:
    """GET an IMGW URL; any HTTP failure becomes ``source_unavailable``."""
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url) from exc
    return response


async def _get_async(
    url: str, *, timeout: float, headers: Mapping[str, str] | None = None
) -> httpx.Response:
    """Async twin of `_get`."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url) from exc
    return response


_NO_DATA_KEYS = frozenset({"status", "message"})
"""Keys of the IMGW API answer meaning "no data" (e.g. no meteo warnings)."""


def _records[T](
    payload: object, url: str, parse: Callable[[dict[str, Any]], T]
) -> list[T]:
    """
    Parse the records of an IMGW API answer.

    A single object is one record; ``null`` and an object with only
    ``status``/``message`` (e.g. ``{"message": "Brak ostrzeżeń ..."}``) mean
    no records.

    Parameters
    ----------
    payload : object
        Decoded JSON body.
    url : str
        Requested URL, quoted in error messages.
    parse : callable
        Parser of one record.

    Returns
    -------
    list
        Parsed records in API order.

    Raises
    ------
    IMGWDataError
        If the body is not a list of objects or a record cannot be parsed.
    """
    if payload is None or (
        isinstance(payload, dict) and payload.keys() <= _NO_DATA_KEYS
    ):
        return []
    items = [payload] if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise IMGWDataError(
            f"Nieoczekiwana odpowiedź z {url}: oczekiwano listy obiektów"
        )
    try:
        return [parse(cast(dict[str, Any], item)) for item in items]
    except (ValidationError, TypeError, ValueError) as exc:
        raise IMGWDataError(f"Niepoprawny rekord w odpowiedzi z {url}: {exc}") from exc


def _validate_poland_coords(latitude: float, longitude: float) -> None:
    """Validate that coordinates are numbers within the Poland bounds box."""
    for option, name, value, low, high in (
        ("latitude", "Szerokość", latitude, POLAND_LAT_MIN, POLAND_LAT_MAX),
        ("longitude", "Długość", longitude, POLAND_LON_MIN, POLAND_LON_MAX),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not low <= value <= high
        ):
            details: dict[str, object] = {"option": option}
            if isinstance(value, int | float | str):
                details["value"] = value
            raise IMGWValidationError(
                f"{name} geograficzna {value!r} poza zakresem Polski ({low}–{high})",
                details=details,
            )


def _pmaxtp_url(latitude: float, longitude: float, method: str) -> str:
    """Validate the PMAXTP arguments and build the API URL."""
    if method not in _PMAXTP_METHODS:
        raise IMGWValidationError(
            f"Nieznana metoda PMAXTP: {method!r}; dozwolone POT, AMP",
            details={"option": "method", "allowed": list(_PMAXTP_METHODS)},
        )
    return build_pmaxtp_url(PMaXTPMethod(method), latitude, longitude)


# ============================================================================
# PMAXTP (Probabilistic Maximum Precipitation)
# ============================================================================

_PMAXTP_METHODS = ("POT", "AMP")

_PMAXTP_OUTSIDE_GRID = ("poza obszarem", "undefined: lat")
"""Fragments of the PMAXTP API ``error`` texts for a point outside its grid."""


def _check_pmaxtp_payload(payload: object, latitude: float, longitude: float) -> None:
    """
    Reject a PMAXTP response body that reports an error instead of data.

    For points inside the coordinate box but outside its grid (e.g.
    Kaliningrad, Lviv, the Baltic Sea) the API answers HTTP 200 with empty
    ``data`` and ``"error": "Brak pliku, pradopodobnie poza obszarem PL"``
    (earlier ``"undefined: lat …, lon: …, type: KS"``).

    Parameters
    ----------
    payload : object
        Decoded JSON body of the PMAXTP API.
    latitude : float
        Requested latitude, quoted in the message.
    longitude : float
        Requested longitude, quoted in the message.

    Raises
    ------
    IMGWValidationError
        If the API reports that the point lies outside the PMAXTP grid.
    IMGWDataError
        If the API reports any other error.
    """
    if not isinstance(payload, dict) or not payload.get("error"):
        return
    error = str(payload["error"])
    if any(marker in error.lower() for marker in _PMAXTP_OUTSIDE_GRID):
        raise IMGWValidationError(
            f"Punkt {latitude}, {longitude} leży poza siatką PMAXTP IMGW-PIB "
            f"(brak danych dla tego miejsca); odpowiedź API: {error}"
        )
    raise IMGWDataError(f"API PMAXTP zwróciło błąd: {error}")


def _pmaxtp_result(
    raw_data: object,
    method: Literal["POT", "AMP"],
    latitude: float,
    longitude: float,
) -> PMaXTPResult:
    """Validate a PMAXTP response body and build the public result."""
    _check_pmaxtp_payload(raw_data, latitude, longitude)
    try:
        result = PMaXTPResult(
            method=method,
            latitude=latitude,
            longitude=longitude,
            data=PMaXTPData.from_api_response(cast(dict[str, Any], raw_data)),
        )
    except (ValidationError, AttributeError, TypeError, ValueError) as exc:
        raise IMGWDataError(f"Niepoprawna odpowiedź PMAXTP: {exc}") from exc
    if not result.data.ks:
        raise IMGWDataError("Odpowiedź PMAXTP bez danych (pusta tabela ks)")
    return result


def fetch_pmaxtp(
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
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
        If the method is unknown, coordinates are outside the Poland bounds
        or the API reports the point outside its grid (e.g. Kaliningrad,
        Lviv, the Baltic Sea).
    IMGWConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If response parsing fails, the API reports another error or the
        response has no quantile table.

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
    url = _pmaxtp_url(latitude, longitude, method)
    payload = _json_payload(_get(url, timeout=timeout))
    return _pmaxtp_result(payload, method, latitude, longitude)


async def fetch_pmaxtp_async(
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
    timeout: float = DEFAULT_TIMEOUT,
    validate_coords: bool = True,
) -> PMaXTPResult:
    """
    Async version of `fetch_pmaxtp`, with identical arguments and result.

    See `fetch_pmaxtp` for full documentation.
    """
    if validate_coords:
        _validate_poland_coords(latitude, longitude)
    url = _pmaxtp_url(latitude, longitude, method)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _pmaxtp_result(payload, method, latitude, longitude)


# ============================================================================
# Real-time data (hydro, meteo, synop, warnings)
# ============================================================================


def fetch_hydro_current(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroCurrentData]:
    """
    Fetch current hydrological data from IMGW API.

    Data includes water level, flow, water temperature and the station
    location for monitoring stations.

    Parameters
    ----------
    station : str or None, optional
        Station code; None returns data for all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of HydroCurrentData
        Current measurements for the requested stations.

    Raises
    ------
    IMGWConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error,
        including 404 for an unknown station (``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If the response is not a list of valid records.

    Examples
    --------
    >>> stations = fetch_hydro_current()
    >>> klodzko = fetch_hydro_current(station="150160180")
    >>> print(f"Water level: {klodzko[0].water_level_cm} cm")
    """
    url = build_api_url("hydro", station_id=station)
    payload = _json_payload(_get(url, timeout=timeout))
    return _records(payload, url, HydroCurrentData.from_api_response)


async def fetch_hydro_current_async(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroCurrentData]:
    """
    Async version of `fetch_hydro_current`, with identical arguments and result.

    See `fetch_hydro_current` for full documentation.
    """
    url = build_api_url("hydro", station_id=station)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _records(payload, url, HydroCurrentData.from_api_response)


def fetch_meteo_current(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MeteoCurrentData]:
    """
    Fetch current data of automatic meteorological stations from IMGW API.

    Data includes air temperature, mean wind speed, relative humidity,
    10-minute precipitation and the station location.

    Parameters
    ----------
    station : str or None, optional
        Station code; None returns data for all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of MeteoCurrentData
        Current measurements; a value the station does not report is None.

    Raises
    ------
    IMGWConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error,
        including 404 for an unknown station (``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If the response is not a list of valid records.

    Examples
    --------
    >>> [pszczyna] = fetch_meteo_current(station="249180010")
    >>> print(f"Air temperature: {pszczyna.air_temp_c} C")
    """
    url = build_api_url("meteo", station_id=station)
    payload = _json_payload(_get(url, timeout=timeout))
    return _records(payload, url, MeteoCurrentData.from_api_response)


async def fetch_meteo_current_async(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MeteoCurrentData]:
    """
    Async version of `fetch_meteo_current`, with identical arguments and result.

    See `fetch_meteo_current` for full documentation.
    """
    url = build_api_url("meteo", station_id=station)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _records(payload, url, MeteoCurrentData.from_api_response)


def _filter_synop(
    records: list[SynopData], station_name: str | None
) -> list[SynopData]:
    """Records whose station name contains ``station_name`` (case-insensitive)."""
    if not station_name:
        return records
    wanted = station_name.casefold()
    return [record for record in records if wanted in record.station_name.casefold()]


def fetch_synop(
    *,
    station: str | None = None,
    station_name: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SynopData]:
    """
    Fetch current synoptic data from IMGW API.

    Synoptic data includes temperature, wind, humidity, precipitation, etc.

    Parameters
    ----------
    station : str or None, optional
        Synoptic station code (e.g. ``"12375"``); requests only that station.
    station_name : str or None, optional
        Case-insensitive fragment of the station name, filtered locally.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of SynopData
        Current synoptic measurements for the requested stations.

    Raises
    ------
    IMGWConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error,
        including 404 for an unknown station (``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If the response is not a list of valid records.

    Examples
    --------
    >>> stations = fetch_synop()
    >>> warszawa = fetch_synop(station_name="Warszawa")
    """
    url = build_api_url("synop", station_id=station)
    payload = _json_payload(_get(url, timeout=timeout))
    return _filter_synop(
        _records(payload, url, SynopData.from_api_response), station_name
    )


async def fetch_synop_async(
    *,
    station: str | None = None,
    station_name: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SynopData]:
    """
    Async version of `fetch_synop`, with identical arguments and result.

    See `fetch_synop` for full documentation.
    """
    url = build_api_url("synop", station_id=station)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _filter_synop(
        _records(payload, url, SynopData.from_api_response), station_name
    )


_WARNING_KINDS: tuple[Literal["hydro", "meteo"], ...] = ("hydro", "meteo")


def _warning_sources(
    kind: Literal["hydro", "meteo"] | None,
) -> list[tuple[Literal["hydro", "meteo"], str]]:
    """Warning families to fetch with their endpoint URLs, hydro first."""
    if kind is not None and kind not in _WARNING_KINDS:
        raise IMGWValidationError(
            f"Nieznany rodzaj ostrzeżeń: {kind!r}; dozwolone hydro, meteo",
            details={"option": "kind", "allowed": list(_WARNING_KINDS)},
        )
    kinds = _WARNING_KINDS if kind is None else (kind,)
    return [(family, build_api_url(f"warnings{family}")) for family in kinds]


def _warning_parser(
    kind: Literal["hydro", "meteo"],
) -> Callable[[dict[str, Any]], WarningData]:
    return lambda record: WarningData.from_api_response(record, kind=kind)


def fetch_warnings(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[WarningData]:
    """
    Fetch current hydrological and/or meteorological warnings from IMGW.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Warning family; None fetches both (hydro warnings first).
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of WarningData
        Active warnings, each with its family in ``kind``. Empty list if
        there are none.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is not ``"hydro"``, ``"meteo"`` or None.
    IMGWConnectionError
        If an IMGW server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If a response is not a list of valid records.

    Examples
    --------
    >>> for warning in fetch_warnings():
    ...     print(f"{warning.kind} {warning.level}: {warning.event}")
    """
    result: list[WarningData] = []
    for family, url in _warning_sources(kind):
        payload = _json_payload(_get(url, timeout=timeout))
        result.extend(_records(payload, url, _warning_parser(family)))
    return result


async def fetch_warnings_async(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[WarningData]:
    """
    Async version of `fetch_warnings`, with identical arguments and result.

    See `fetch_warnings` for full documentation.
    """
    result: list[WarningData] = []
    for family, url in _warning_sources(kind):
        payload = _json_payload(await _get_async(url, timeout=timeout))
        result.extend(_records(payload, url, _warning_parser(family)))
    return result


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
