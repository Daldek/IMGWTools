"""
Data fetching functions for IMGW public data.

Provides both synchronous and asynchronous versions of all fetch functions.
Data is fetched directly from IMGW servers - nothing is stored locally.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from zipfile import BadZipFile, ZipFile

import httpx
from pydantic import ValidationError

from imgwtools._version import __version__
from imgwtools.datasets import (
    ArchiveFile,
    MonthsArg,
    ProviderDescriptor,
    YearsArg,
    archive_files,
    get_dataset,
    get_provider,
)
from imgwtools.exceptions import (
    IMGWCancelledError,
    IMGWConnectionError,
    IMGWDataError,
    IMGWError,
    IMGWValidationError,
)
from imgwtools.messages import message, reason
from imgwtools.models import (
    HydroCurrentData,
    MeteoCurrentData,
    PMaXTPData,
    PMaXTPResult,
    SynopData,
    WarningData,
)
from imgwtools.output import (
    FileResult,
    Staging,
    plan_plain,
    refuse,
    refuse_directory,
    resolve_target,
)
from imgwtools.urls import build_api_url, build_pmaxtp_url

if TYPE_CHECKING:
    from imgwtools.store.types import (
        Cancel,
        DownloadItem,
        DownloadReport,
        NoticeHook,
        PathArg,
        ProgressHook,
    )

# Poland coordinate bounds
POLAND_LAT_MIN = 49.0
POLAND_LAT_MAX = 55.0
POLAND_LON_MIN = 14.0
POLAND_LON_MAX = 24.5

DEFAULT_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 120.0

UNPUBLISHED = message("common.unpublished")
"""Error text of a candidate file the provider does not publish (HTTP 404/410)."""

# Requests for per-station files (ČHMÚ) identify the library (spec 2026-10-18
# §4.5); IMGW-PIB archive traffic keeps the default headers of 3.0.0.
_IDENTIFY = {"User-Agent": f"imgwtools/{__version__}"}
_NOT_PUBLISHED = (404, 410)


@dataclass(frozen=True)
class DownloadResult:
    """Archive bytes and provenance from a single HTTP GET."""

    data: bytes
    url: str
    etag: str | None
    last_modified: str | None
    content_length: int | None


def _download_result(
    response: httpx.Response, *, zipped: bool = True
) -> DownloadResult:
    data = response.content
    if zipped:
        try:
            ZipFile(BytesIO(data)).close()
        except BadZipFile as exc:
            raise IMGWDataError(
                message("fetch.invalid_zip_archive_from", url=response.url)
            ) from exc
    length = response.headers.get("Content-Length")
    try:
        content_length = int(length) if length is not None else None
    except ValueError as exc:
        raise IMGWDataError(
            message("fetch.invalid_content_length_header", length=length)
        ) from exc
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
        raise IMGWDataError(
            message("fetch.invalid_json_response_from", url=response.url)
        ) from exc


def _source_error(
    exc: httpx.HTTPError, url: str, *, source: str = "IMGW"
) -> IMGWConnectionError:
    """
    Map a failed request to a provider's server to ``source_unavailable``.

    Parameters
    ----------
    exc : httpx.HTTPError
        Timeout, network error or HTTP 4xx/5xx status of the request.
    url : str
        Requested URL, reported in ``details["url"]``.
    source : str, optional
        Name of the provider in the message, e.g. ``"ČHMÚ"``.

    Returns
    -------
    IMGWConnectionError
        Error with ``details`` ``url``, ``reason`` (``timeout``, ``network``
        or ``http_status``) and, for an HTTP status, ``status``.
    """
    if isinstance(exc, httpx.TimeoutException):
        return IMGWConnectionError(
            message("fetch.timeout_waiting_server", source=source, url=url),
            details={"url": url, "reason": "timeout"},
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return IMGWConnectionError(
            message(
                "fetch.server_returned_http", source=source, status=status, url=url
            ),
            details={"url": url, "reason": "http_status", "status": status},
        )
    return IMGWConnectionError(
        message(
            "fetch.connection_error_server", source=source, exc=reason(exc), url=url
        ),
        details={"url": url, "reason": "network"},
    )


def _get(
    url: str,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    source: str = "IMGW",
) -> httpx.Response:
    """GET a URL of the ``source`` provider; failures become ``source_unavailable``."""
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
    return response


async def _get_async(
    url: str,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    source: str = "IMGW",
) -> httpx.Response:
    """Async twin of `_get`."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
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
            message("fetch.unexpected_response_from_list_objects", url=url)
        )
    try:
        return [parse(cast(dict[str, Any], item)) for item in items]
    except (ValidationError, TypeError, ValueError) as exc:
        raise IMGWDataError(
            message("fetch.invalid_record_response_from", url=url, exc=reason(exc))
        ) from exc


def _validate_poland_coords(latitude: float, longitude: float) -> None:
    """Validate that coordinates are numbers within the Poland bounds box."""
    for option, name, value, low, high in (
        (
            "latitude",
            message("fetch.latitude"),
            latitude,
            POLAND_LAT_MIN,
            POLAND_LAT_MAX,
        ),
        (
            "longitude",
            message("fetch.longitude"),
            longitude,
            POLAND_LON_MIN,
            POLAND_LON_MAX,
        ),
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
                message(
                    "fetch.outside_poland", name=name, value=value, low=low, high=high
                ),
                details=details,
            )


# ============================================================================
# PMAXTP (Probabilistic Maximum Precipitation)
# ============================================================================

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
            message(
                "fetch.point_lies_outside_pmaxtp_grid",
                latitude=latitude,
                longitude=longitude,
                error=error,
            )
        )
    raise IMGWDataError(message("fetch.pmaxtp_api_returned_error", error=error))


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
        raise IMGWDataError(
            message("fetch.invalid_pmaxtp_response", exc=reason(exc))
        ) from exc
    if not result.data.ks:
        raise IMGWDataError(message("fetch.pmaxtp_response_has_no_data"))
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

    PMAXTP provides precipitation quantiles for 16 durations and 27 probabilities,
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
    Durations [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440,
    2160, 2880, 4320. Probabilities [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3,
    0.5, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5,
    99.9. `PMaXTPData.get_precipitation` takes a probability as a number (``0.01``,
    ``50``) and refuses a number that is not in this list.
    """
    if validate_coords:
        _validate_poland_coords(latitude, longitude)
    url = build_pmaxtp_url(latitude, longitude, method=method)
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
    url = build_pmaxtp_url(latitude, longitude, method=method)
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
    url = build_api_url("hydro", station=station)
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
    url = build_api_url("hydro", station=station)
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
    url = build_api_url("meteo", station=station)
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
    url = build_api_url("meteo", station=station)
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
    url = build_api_url("synop", station=station)
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
    url = build_api_url("synop", station=station)
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
            message("fetch.unknown_kind_warnings_allowed_hydro", kind=kind),
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


def _archive_slot(archive: ArchiveFile) -> str:
    """
    Return the slot of an IMGW archive or station list file (spec §13.7).

    Parameters
    ----------
    archive : ArchiveFile
        File from the dataset registry.

    Returns
    -------
    str
        ``archive:<dataset key>:<server_path without the dataset server_dir>``,
        e.g. ``archive:pl.imgw.hydro_daily:2024/codz_2024.zip``.
    """
    server_dir = get_dataset(archive.dataset).server_dir
    selector = archive.server_path.removeprefix(f"{server_dir}/")
    return f"archive:{archive.dataset}:{selector}"


def _single_archive(
    files: tuple[ArchiveFile, ...], *, option: Literal["month", "param"]
) -> ArchiveFile:
    """Return the only archive selected by 2.1.1 download arguments."""
    if len(files) == 1:
        return files[0]
    if option == "param":
        text = message("fetch.archive_needs_parameter_t_q", dataset=files[0].dataset)
    else:
        text = message(
            "fetch.archive_published_monthly_files_give",
            dataset=files[0].dataset,
            year=files[0].year,
        )
    raise IMGWValidationError(text, details={"option": option})


def _legacy_year(year: object) -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        raise IMGWValidationError(
            message("fetch.year_must_integer", year=year),
            details={"option": "year", "value": str(year)},
        )
    return year


def _hydro_archive(
    interval: str, year: int, month: int | None, param: str | None
) -> ArchiveFile:
    """Registry archive of the 2.1.1 `download_hydro_data` arguments."""
    year = _legacy_year(year)
    if interval == "dobowe" and month == 13:
        return archive_files("pl.imgw.hydro_phenomena", years=year)[0]
    descriptor = get_dataset(f"hydro/{interval}")
    semiannual = descriptor.key == "pl.imgw.hydro_semiannual"
    files = archive_files(
        descriptor.key,
        years=year,
        months=month,
        params=[cast(Literal["H", "Q", "T"], param)] if semiannual and param else None,
    )
    return _single_archive(files, option="param" if semiannual else "month")


def _meteo_archive(
    interval: str, subtype: str, year: int, month: int | None
) -> ArchiveFile:
    """Registry archive of the 2.1.1 `download_meteo_data` arguments."""
    year = _legacy_year(year)
    descriptor = get_dataset(f"meteo/{interval}/{subtype}")
    files = archive_files(descriptor.key, years=year, months=month)
    return _single_archive(files, option="month")


def _archive_response(
    client: httpx.Client, url: str, *, source: str = "IMGW", zipped: bool = True
) -> DownloadResult:
    """
    GET one source file; HTTP failures become ``source_unavailable``.

    Parameters
    ----------
    client : httpx.Client
        Client of the download.
    url : str
        URL of the file.
    source : str, optional
        Name of the provider in error messages.
    zipped : bool, optional
        Whether the bytes must form a ZIP archive (IMGW-PIB); per-station
        ČHMÚ files (JSON, CSV) are taken as they are.

    Returns
    -------
    DownloadResult
        Original bytes and response headers.

    Raises
    ------
    IMGWConnectionError
        If the request fails (``details`` ``url``, ``reason`` and, for an
        HTTP error, ``status``).
    IMGWDataError
        If ``zipped`` bytes are no ZIP archive or ``Content-Length`` is
        invalid.
    """
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
    return _download_result(response, zipped=zipped)


async def _archive_response_async(
    client: httpx.AsyncClient, url: str
) -> DownloadResult:
    """Async twin of `_archive_response`."""
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url) from exc
    return _download_result(response)


def download_hydro_data(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int,
    month: int | None = None,
    param: Literal["T", "Q", "H"] | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Download one hydrological archive as ZIP bytes.

    The file is resolved through the dataset registry (`archive_files`): the
    interval is the legacy alias ``hydro/<interval>`` and ``dobowe`` with
    ``month=13`` selects ``pl.imgw.hydro_phenomena`` (``zjaw_<year>.zip``).
    Use `parse_zip_file` to extract and parse the data.

    Parameters
    ----------
    interval : {"dobowe", "miesieczne", "polroczne_i_roczne"}
        Data interval: daily, monthly or semi-annual/annual.
    year : int
        Hydrological year (from 1951).
    month : int or None, optional
        Hydrological month 1-12 (1 = November), required for daily data
        before 2023; 13 selects the daily phenomena archive.
    param : {"T", "Q", "H"} or None, optional
        Parameter of semi-annual data, required there: "T" (temperature),
        "Q" (flow) or "H" (water level).
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    DownloadResult
        Original ZIP bytes and response headers.

    Raises
    ------
    IMGWValidationError
        If the interval is unknown, the year or month is invalid, or a
        required month or parameter is missing (``details["option"]``).
    IMGWConnectionError
        If the download fails (``source_unavailable``; ``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If the downloaded data is not a ZIP archive.

    Examples
    --------
    >>> response = download_hydro_data("dobowe", 2023)
    >>> from imgwtools import parse_zip_file
    >>> for station, record in parse_zip_file(response.data, "dobowe"):
    ...     print(f"{station.station_name}: {record.water_level_cm} cm")
    """
    archive = _hydro_archive(interval, year, month, param)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        return _archive_response(client, archive.url)


async def download_hydro_data_async(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int,
    month: int | None = None,
    param: Literal["T", "Q", "H"] | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Async version of `download_hydro_data`, with identical arguments and result.

    See `download_hydro_data` for full documentation.
    """
    archive = _hydro_archive(interval, year, month, param)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await _archive_response_async(client, archive.url)


def download_meteo_data(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"],
    year: int,
    month: int | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Download one meteorological archive as ZIP bytes.

    The file is resolved through the dataset registry (`archive_files`) from
    the legacy alias ``meteo/<interval>/<subtype>``; a monthly archive covers
    the whole folder (five years until 2000) containing ``year``.

    Parameters
    ----------
    interval : {"dobowe", "miesieczne", "terminowe"}
        Data interval: daily, monthly or hourly.
    subtype : {"klimat", "opad", "synop"}
        Data subtype: climate, precipitation or synoptic.
    year : int
        Calendar year.
    month : int or None, optional
        Month 1-12, required for daily and hourly data from 2001.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    DownloadResult
        Original ZIP bytes and response headers.

    Raises
    ------
    IMGWValidationError
        If the combination is not published as a single archive (daily or
        hourly synop, hourly precipitation; ``details["reason"]``), the year
        or month is invalid, or a required month is missing.
    IMGWConnectionError
        If the download fails (``source_unavailable``; ``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If the downloaded data is not a ZIP archive.

    Examples
    --------
    >>> response = download_meteo_data("miesieczne", "opad", 2023)
    >>> response.data[:2]
    b'PK'
    """
    archive = _meteo_archive(interval, subtype, year, month)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        return _archive_response(client, archive.url)


async def download_meteo_data_async(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"],
    year: int,
    month: int | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Async version of `download_meteo_data`, with identical arguments and result.

    See `download_meteo_data` for full documentation.
    """
    archive = _meteo_archive(interval, subtype, year, month)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await _archive_response_async(client, archive.url)


_STREAM_CHUNK = 1 << 16
"""Size of the pieces a plain download is read, hashed and written in."""


def _origin(archive: ArchiveFile) -> tuple[ProviderDescriptor, bool]:
    """Provider of an archive and whether its files are per station (ČHMÚ)."""
    descriptor = get_dataset(archive.dataset)
    return get_provider(descriptor.provider), descriptor.archive_scope != "country"


def _stage(
    client: httpx.Client,
    archive: ArchiveFile,
    staging: Staging,
    *,
    source: str,
    zipped: bool,
) -> tuple[Path, int, str]:
    """
    GET one source file straight into the staging directory (DEV-19.7).

    The bytes are hashed while they stream to the staged file; an archive that
    must be a ZIP is verified there, before it is moved into place.

    Returns
    -------
    tuple of (pathlib.Path, int, str)
        The staged file, its size and its SHA-256.

    Raises
    ------
    IMGWConnectionError
        If the request fails (``source_unavailable``).
    IMGWDataError
        If ``zipped`` bytes are no ZIP archive.
    """
    try:
        with client.stream("GET", archive.url) as response:
            response.raise_for_status()
            staged, size, sha256 = staging.write(response.iter_bytes(_STREAM_CHUNK))
    except httpx.HTTPError as exc:
        raise _source_error(exc, archive.url, source=source) from exc
    if zipped:
        try:
            ZipFile(staged).close()
        except BadZipFile as exc:
            staged.unlink(missing_ok=True)
            raise IMGWDataError(
                message("fetch.invalid_zip_archive_from", url=archive.url)
            ) from exc
    return staged, size, sha256


def _download_loop(
    files: Sequence[ArchiveFile],
    save: Callable[[httpx.Client, ArchiveFile], FileResult],
    *,
    timeout: float,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[DownloadItem], list[FileResult]]:
    """
    Download every archive with ``save`` and report each file as an item.

    A failed file becomes a ``failed`` item and the others are still
    downloaded; a ČHMÚ candidate the server answers with HTTP 404 or 410 is a
    successful ``not_published`` item; ``cancel`` is polled before every file.
    """
    # store.types is imported lazily: the imgwtools.store package imports this module.
    from imgwtools.store.types import DownloadItem, Notice, Progress

    items: list[DownloadItem] = []
    written: list[FileResult] = []
    licensed: set[str] = set()
    listed = any(_origin(archive)[1] for archive in files)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=_IDENTIFY if listed else None,
    ) as client:
        for index, archive in enumerate(files):
            if cancel is not None and cancel():
                items.extend(
                    DownloadItem(
                        _archive_slot(rest), rest.url, "cancelled", None, None, None
                    )
                    for rest in files[index:]
                )
                break
            provider, per_station = _origin(archive)
            slot = _archive_slot(archive)
            try:
                result = save(client, archive)
            except IMGWCancelledError:
                items.extend(
                    DownloadItem(
                        _archive_slot(rest), rest.url, "cancelled", None, None, None
                    )
                    for rest in files[index:]
                )
                break
            except IMGWError as exc:
                if per_station and exc.details.get("status") in _NOT_PUBLISHED:
                    item = DownloadItem(
                        slot, archive.url, "not_published", None, UNPUBLISHED, None
                    )
                else:
                    item = DownloadItem(
                        slot, archive.url, "failed", None, exc.detail, exc.code
                    )
            except OSError as exc:
                item = DownloadItem(
                    slot,
                    archive.url,
                    "failed",
                    None,
                    message(
                        "fetch.cannot_save_archive",
                        path=archive.server_path,
                        exc=reason(exc),
                    ),
                    "io_error",
                )
            else:
                written.append(result)
                item = DownloadItem(
                    slot, archive.url, "downloaded", result.path, None, None
                )
            items.append(item)
            if on_progress is not None:
                on_progress(
                    Progress(
                        index + 1,
                        len(files),
                        "archive",
                        item.status,
                        message(
                            "fetch.archive_downloaded", server_path=archive.server_path
                        )
                        if item.path is not None
                        else message(
                            "fetch.archive_not_downloaded",
                            server_path=archive.server_path,
                            error=item.error,
                        ),
                    )
                )
            if item.path is not None and provider.id not in licensed:
                licensed.add(provider.id)
                if on_notice is not None:
                    on_notice(
                        Notice("info", "license_terms", provider.license_notice())
                    )
    return items, written


def _download_plain(
    files: Sequence[ArchiveFile],
    directory: Path,
    *,
    force: bool,
    timeout: float,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[DownloadItem], list[FileResult]]:
    """
    Write the archives as ordinary files below ``directory`` (DEV-19.5 to DEV-19.9).

    The names are the server paths. The output directory is checked first
    (`refuse_directory`), then the full target list, both before the first
    request (`plan_plain`, `refuse`); each file is streamed to the staging
    directory, verified and moved into place with ``os.replace``.

    Raises
    ------
    IMGWError
        ``conflict`` (``output_in_store`` with the directory as the path for a
        directory that is or lies in a store; ``duplicate_output_name``,
        ``output_in_store`` for a target that would enter a store below the
        directory, ``output_exists``) before anything is requested or written.
    OSError
        If the output directory cannot be created.
    """
    refuse_directory(directory)
    refuse(
        plan_plain(directory, [archive.server_path for archive in files], force=force)
    )
    with Staging(directory) as staging:

        def save(client: httpx.Client, archive: ArchiveFile) -> FileResult:
            provider, per_station = _origin(archive)
            staged, size, sha256 = _stage(
                client,
                archive,
                staging,
                source=provider.short_name if per_station else "IMGW",
                zipped=not per_station,
            )
            target = directory.joinpath(*archive.server_path.split("/"))
            return staging.commit(staged, target, size, sha256)

        return _download_loop(
            files,
            save,
            timeout=timeout,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )


def _download_store(
    files: Sequence[ArchiveFile],
    root: Path,
    *,
    timeout: float,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[DownloadItem], list[FileResult]]:
    """
    Publish the archives as versions in the store at ``root`` (``write_archive``).

    Every file is fetched (there is no freshness check) and gets the status of
    its version: ``new``, ``unchanged`` or ``relabeled``.

    Raises
    ------
    IMGWStoreError
        If ``root`` is no usable store (the layout has no marker).
    IMGWStoreConflictError
        If the root nests a store or holds foreign files.
    """
    # The writer imports this module, so it is imported lazily.
    from imgwtools.store.types import Notice
    from imgwtools.store.writer import prepare_store, write_archive

    handle = prepare_store(root)

    def forward(notice: Notice) -> None:
        # The license notice is sent once per provider by the loop.
        if on_notice is not None and notice.code != "license_terms":
            on_notice(notice)

    def save(client: httpx.Client, archive: ArchiveFile) -> FileResult:
        provider, per_station = _origin(archive)
        response = _archive_response(
            client,
            archive.url,
            source=provider.short_name if per_station else "IMGW",
            zipped=not per_station,
        )
        version = write_archive(
            handle, archive=archive, response=response, on_notice=forward, cancel=cancel
        )
        return FileResult(
            version.path, version.path.stat().st_size, version.sha256, version.status
        )

    return _download_loop(
        files,
        save,
        timeout=timeout,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )


def download_archives(
    dataset: str,
    /,
    *,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    params: Iterable[Literal["H", "Q", "T"]] | None = None,
    stations: Iterable[str] | None = None,
    output_dir: PathArg | None = None,
    root: PathArg | None = None,
    force: bool = False,
    timeout: float = DOWNLOAD_TIMEOUT,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> DownloadReport:
    """
    Download the source files of a dataset as plain files or into the store.

    With ``output_dir`` (plain mode, DEV-19.1) every file of `archive_files`
    is written as ``<output_dir>/<server_path>``: before the first request the
    full list of targets is checked and an existing target without ``force``,
    a duplicate name or a directory that is, or lies in, a store is a
    ``conflict`` that lists every path; each file is streamed to
    ``<output_dir>/.imgw-incoming/<host>_<pid>_<token>/``, hashed while it
    streams, verified and moved into place with ``os.replace``, so an
    interrupted download leaves no partial file. Without ``output_dir`` the
    files are published as versions in the store at ``root`` (the default
    root when ``root`` is not given: ``IMGW_ROOT``, ``[imgw] root`` of
    ``nogat.toml`` or ``<data_dir>/imgw``); only the datasets of the store
    are accepted. A failed file becomes a ``failed`` item and the remaining
    files are still downloaded. ČHMÚ files are candidates that are fetched
    without a listing (spec 2026-10-18 §4.4): a candidate the server answers
    with HTTP 404 or 410 is a successful ``not_published`` item.

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of one of the twelve archive datasets.
    years : YearsArg or None, optional
        Archive years: a number, a range ``"a-b"``, a list ``"a,b"`` or an
        iterable of these. Required except for ``cz.chmi.meteo_daily``, which
        rejects it.
    months : MonthsArg or None, optional
        Months 1-12 of physically monthly files; None selects all months.
        Rejected for ČHMÚ datasets.
    params : iterable of {"H", "Q", "T"} or None, optional
        Parameters of ``pl.imgw.hydro_semiannual``; None selects all three.
    stations : iterable of str or None, optional
        ČHMÚ station codes (WIGOS identifiers); required for ČHMÚ datasets
        and rejected for IMGW-PIB datasets.
    output_dir : str or os.PathLike or None, optional
        Plain mode: directory of the files, created when missing. Excludes
        ``root``.
    root : str or os.PathLike or None, optional
        Store mode: root of the store; None (with no ``output_dir``) is the
        default root.
    force : bool, optional
        Plain mode: replace existing target files (each atomically, nothing
        else is deleted). Store mode: the files are fetched again anyway and
        a version is never overwritten, so it changes nothing.
    timeout : float, optional
        Request timeout in seconds, per file.
    on_progress : ProgressHook or None, optional
        Called after every file with status ``downloaded``,
        ``not_published`` or ``failed``.
    on_notice : NoticeHook or None, optional
        Receives the ``license_terms`` notice of the provider once, after the
        first downloaded file.
    cancel : Cancel or None, optional
        Polled before every file; returning ``True`` stops the download and
        reports the remaining files as ``cancelled``.

    Returns
    -------
    DownloadReport
        The mode, the absolute ``output_dir`` or ``root``, one item per file
        in download order (the §13.7 slot, URL, status, written path and, for
        a failed file, the error text and code: ``source_unavailable``,
        ``data_error`` or ``io_error``; a ``not_published`` item has no path,
        the error ``"not published"`` and no code) and ``files``: the files
        written with their size, SHA-256 and status (``written`` or
        ``replaced`` in plain mode, ``new``, ``unchanged`` or ``relabeled``
        in store mode).

    Raises
    ------
    IMGWValidationError
        If the dataset, years, months, params or stations are invalid
        (``details["option"]``); if both ``output_dir`` and ``root`` are
        given (``details["reason"]="exclusive_options"``); or if a store
        download names a dataset outside the store
        (``details["reason"]="not_in_store"``).
    IMGWError
        ``conflict`` in plain mode before any request: an output directory that
        is or lies in a store (``output_in_store``, ``details["paths"]`` is the
        directory), then an existing target without ``force``
        (``output_exists``), duplicate names (``duplicate_output_name``) or a
        target that would enter a store below the directory
        (``output_in_store``); ``details["paths"]`` lists every such path. In
        store mode ``store_unavailable`` (a layout without a marker) or
        ``conflict`` (a nested store, ``nested_store``, or a root with other
        files, ``not_empty``).
    OSError
        If the output directory cannot be created.

    Examples
    --------
    >>> report = download_archives(
    ...     "meteo/miesieczne/synop", years=1998, output_dir="data/synop"
    ... )
    >>> [item.status for item in report.items]
    ['downloaded']
    >>> [file.status for file in report.files]
    ['written']
    """
    files = archive_files(
        dataset, years=years, months=months, params=params, stations=stations
    )
    descriptor = get_dataset(dataset)
    target = resolve_target(output_dir=output_dir, root=root)
    # store.types is imported lazily: the imgwtools.store package imports this module.
    from imgwtools.store.types import DownloadReport

    if target.mode == "plain":
        items, written = _download_plain(
            files,
            target.path,
            force=force,
            timeout=timeout,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
        directory, store = target.path, None
    else:
        if not descriptor.in_store:
            raise IMGWValidationError(
                message("fetch.not_in_store", dataset=descriptor.key),
                details={
                    "option": "dataset",
                    "value": descriptor.key,
                    "reason": "not_in_store",
                },
            )
        items, written = _download_store(
            files,
            target.path,
            timeout=timeout,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
        directory, store = None, target.path
    cancelled = any(item.status == "cancelled" for item in items)
    return DownloadReport(
        target.mode, directory, store, tuple(items), tuple(written), cancelled
    )
