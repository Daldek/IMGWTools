"""Versioned station catalog ``stations.geojson`` built from IMGW station sources."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import socket
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from functools import lru_cache
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import httpx

from imgwtools._parsing.stations import parse_stations_csv
from imgwtools._version import __version__
from imgwtools.datasets import (
    CATALOG_DATASET,
    ArchiveFile,
    _license_document,
    datasets,
    get_dataset,
    station_source_files,
)
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWStoreConflictError,
    IMGWValidationError,
    io_error,
)
from imgwtools.fetch import DEFAULT_TIMEOUT, DownloadResult
from imgwtools.models import StationListEntry
from imgwtools.store.series import _current_series, _series_versions
from imgwtools.store.types import (
    Cancel,
    CatalogReport,
    Notice,
    NoticeHook,
    PathArg,
    PlanAction,
    PlanItem,
    Progress,
    ProgressHook,
    StoreHandle,
    StorePlan,
)
from imgwtools.store.writer import (
    _atomic_publish,
    _canonical,
    _check_kartograf,
    _cleanup,
    _existing,
    _fsync_dir,
    _utc,
    _validate_slot,
    _write_json,
    open_store,
    write_archive,
)
from imgwtools.urls import IMGW_API_URL

RootArg = PathArg | StoreHandle

CATALOG_SLOT = "stations/versions"
CATALOG_FILE = "stations.geojson"
HYDRO_API_URL = f"{IMGW_API_URL}/hydro"
METEO_API_URL = f"{IMGW_API_URL}/meteo"
STATIC_LOCATIONS = "hydro_stations_locations.csv"
BORDER_RESOURCE = "poland_border_wgs84.geojson"
# Natural Earth 1:10m generalises the outline by up to ~1 km: every real IMGW station it
# misplaced outside Poland (Odra/Bug gauges, coast, Tatra) lay within 968 m of the line.
BORDER_TOLERANCE_M = 1500.0
LICENSE_NOTICE = "license_terms"
MIN_UNCERTAINTY_M = 150.0
_METRES_PER_DEGREE = 111_320.0
_PROPERTY_ORDER = (
    "station_code",
    "kind",
    "meteo_kind",
    "name",
    "river",
    "hydrographic_code",
    "river_order",
    "location_source",
    "location_uncertainty_m",
    "location_missing_reason",
    "active",
    "established_year",
    "gauge_zero_m",
    "river_km",
    "elevation_m",
)

MissingReason = Literal["none", "zero", "outside_country"]


# --------------------------------------------------------------------------
# Shared version publication (also used by store.pmaxtp)
# --------------------------------------------------------------------------


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _newest_downloaded(
    entries: Iterable[tuple[Path, dict[str, Any]]],
) -> tuple[Path, dict[str, Any]] | None:
    """Current derived version: newest ``downloaded_at``, ties by path."""
    return max(
        entries,
        key=lambda entry: (_timestamp(entry[1]["downloaded_at"]), entry[0].as_posix()),
        default=None,
    )


def _publish_version(
    root: Path,
    *,
    slot: str,
    name: str,
    data: bytes,
    meta: dict[str, Any],
    label: str,
    on_notice: NoticeHook | None = None,
    attachments: Mapping[str, bytes] | None = None,
) -> tuple[Path, bool]:
    """Stage ``name`` + sidecar and publish ``<slot>/<label>_<sha8>`` without replacement.

    Returns the main file path and ``True`` when a new version was created; an identical
    concurrently published version yields ``False``. ``on_notice`` receives a
    ``leftover_incoming`` warning for every removed staging directory older than 24 h.
    ``attachments`` are extra files (name → bytes) published in the same rename; the
    caller documents them in ``meta``.
    """
    sha = meta["sha256"]
    slot_dir = _validate_slot(root, slot)
    target = _validate_slot(root, f"{slot}/{label}_{sha[:8]}")
    incoming = root / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming, on_notice=on_notice)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        for file_name, content in ((name, data), *(attachments or {}).items()):
            with (staging / file_name).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        _write_json(staging / f"{name}.meta.json", meta)
        _fsync_dir(staging)
        slot_dir.mkdir(parents=True, exist_ok=True)
        try:
            _atomic_publish(staging, target)
        except FileExistsError as exc:
            for old_file, old_meta in _existing(slot_dir, name):
                if old_file.parent == target and old_meta["sha256"] == sha:
                    return old_file, False
            raise IMGWStoreConflictError(f"Kolizja katalogu wersji: {target}") from exc
        return target / name, True
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _handle(root: RootArg) -> StoreHandle:
    return open_store(root.root if isinstance(root, StoreHandle) else root)


def _cancelled(cancel: Cancel | None) -> bool:
    return cancel is not None and cancel()


# --------------------------------------------------------------------------
# Border polygon and coordinate validation
# --------------------------------------------------------------------------


def _resource(name: str) -> bytes:
    return files("imgwtools").joinpath("_data", name).read_bytes()


class _Border:
    """Even-odd point-in-polygon over latitude bands, plus distance to the outline; stdlib only."""

    _BANDS = 512

    def __init__(self, rings: list[list[list[float]]]) -> None:
        # Horizontal edges never flip the crossing test, but they count for ``near``.
        edges = [
            (x1, y1, x2, y2)
            for ring in rings
            for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False)
        ]
        if not any(y1 != y2 for _, y1, _, y2 in edges):
            raise IMGWDataError("Pusty obrys granicy Polski")
        self.min_lon = min(min(e[0], e[2]) for e in edges)
        self.max_lon = max(max(e[0], e[2]) for e in edges)
        self.min_lat = min(min(e[1], e[3]) for e in edges)
        self.max_lat = max(max(e[1], e[3]) for e in edges)
        self.step = (self.max_lat - self.min_lat) / self._BANDS
        self.bands: list[list[tuple[float, float, float, float]]] = [
            [] for _ in range(self._BANDS)
        ]
        for edge in edges:
            low, high = sorted((edge[1], edge[3]))
            for band in range(self._band(low), self._band(high) + 1):
                self.bands[band].append(edge)

    def _band(self, lat: float) -> int:
        return min(self._BANDS - 1, max(0, int((lat - self.min_lat) / self.step)))

    def contains(self, lon: float, lat: float) -> bool:
        if not (
            self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat
        ):
            return False
        inside = False
        for x1, y1, x2, y2 in self.bands[self._band(lat)]:
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (
                y2 - y1
            ):
                inside = not inside
        return inside

    def near(self, lon: float, lat: float, tolerance_m: float) -> bool:
        """Whether the point lies within ``tolerance_m`` metres of the outline (local metric approximation)."""
        reach_lat = tolerance_m / _METRES_PER_DEGREE
        if not self.min_lat - reach_lat <= lat <= self.max_lat + reach_lat:
            return False
        scale_lon = _METRES_PER_DEGREE * math.cos(math.radians(lat))
        reach_lon = tolerance_m / scale_lon
        if not self.min_lon - reach_lon <= lon <= self.max_lon + reach_lon:
            return False
        limit = tolerance_m * tolerance_m
        for band in range(self._band(lat - reach_lat), self._band(lat + reach_lat) + 1):
            for x1, y1, x2, y2 in self.bands[band]:
                ax, ay = (x1 - lon) * scale_lon, (y1 - lat) * _METRES_PER_DEGREE
                dx, dy = (x2 - x1) * scale_lon, (y2 - y1) * _METRES_PER_DEGREE
                length = dx * dx + dy * dy
                t = (
                    0.0
                    if length == 0
                    else min(1.0, max(0.0, -(ax * dx + ay * dy) / length))
                )
                if (ax + t * dx) ** 2 + (ay + t * dy) ** 2 <= limit:
                    return True
        return False


@lru_cache(maxsize=1)
def _border() -> _Border:
    document = json.loads(_resource(BORDER_RESOURCE))
    rings: list[list[list[float]]] = []
    for feature in document["features"]:
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for polygon in polygons:
            rings.extend(polygon)
    return _Border(rings)


def _number(value: object) -> tuple[float, int] | None:
    """Parse a source coordinate and the number of decimals it was published with."""
    if value is None or isinstance(value, bool):
        return None
    text = repr(value) if isinstance(value, float) else str(value).strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    if not parsed.is_finite():
        return None
    exponent = parsed.as_tuple().exponent
    return float(parsed), max(0, -exponent) if isinstance(exponent, int) else 0


def _uncertainty_m(lat: float, lon_decimals: int, lat_decimals: int) -> float:
    """max(150 m, half of the source rounding step in metres at the station latitude)."""
    lat_half = 0.5 * 10.0**-lat_decimals * _METRES_PER_DEGREE
    lon_half = (
        0.5 * 10.0**-lon_decimals * _METRES_PER_DEGREE * math.cos(math.radians(lat))
    )
    return round(max(MIN_UNCERTAINTY_M, lat_half, lon_half), 1)


def _evaluate(
    lon_raw: object, lat_raw: object
) -> tuple[tuple[float, float], float] | MissingReason:
    lon, lat = _number(lon_raw), _number(lat_raw)
    if lon is None or lat is None:
        return "none"
    if lon[0] == 0 and lat[0] == 0:
        return "zero"
    border = _border()
    if not (
        border.contains(lon[0], lat[0])
        or border.near(lon[0], lat[0], BORDER_TOLERANCE_M)
    ):
        return "outside_country"
    return (lon[0], lat[0]), _uncertainty_m(lat[0], lon[1], lat[1])


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def _http(method: str, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> httpx.Response:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url)
            response.raise_for_status()
            return response
    except httpx.TimeoutException as exc:
        raise IMGWConnectionError(f"Przekroczono czas oczekiwania na {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise IMGWConnectionError(
            f"Błąd HTTP {exc.response.status_code} dla {url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise IMGWConnectionError(f"Błąd połączenia z {url}: {exc}") from exc


def _content_length(response: httpx.Response) -> int | None:
    value = response.headers.get("Content-Length")
    try:
        return int(value) if value is not None else None
    except ValueError as exc:
        raise IMGWDataError(f"Niepoprawny nagłówek Content-Length: {value}") from exc


def _signal_time(meta: Mapping[str, Any]) -> datetime:
    http = meta["extra"].get("http")
    modified = http.get("last_modified") if isinstance(http, Mapping) else None
    if modified:
        try:
            return parsedate_to_datetime(modified).astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            pass
    return _timestamp(meta["downloaded_at"])


def _archive_slot(archive: ArchiveFile) -> str:
    relative = PurePosixPath(archive.server_path)
    return f"archives/versions/{relative.parent.as_posix()}/{relative.stem}"


def _current_archive(
    root: Path, archive: ArchiveFile
) -> tuple[Path, dict[str, Any]] | None:
    """Current archive version: newest Last-Modified, then downloaded_at, then path."""
    slot = _validate_slot(root, _archive_slot(archive))
    entries = _existing(slot, PurePosixPath(archive.server_path).name, archive=True)
    return max(
        entries,
        key=lambda entry: (
            _signal_time(entry[1]),
            _timestamp(entry[1]["downloaded_at"]),
            entry[0].as_posix(),
        ),
        default=None,
    )


def _archive_http(path: Path, meta: Mapping[str, Any]) -> Mapping[str, Any]:
    """``extra.http`` of a stored list version; a version without it is corrupted."""
    http = meta["extra"].get("http")
    if not isinstance(http, Mapping):
        raise IMGWStoreConflictError(f"Uszkodzona wersja archiwum: {path.parent}")
    return http


def _list_status(
    stored: Mapping[str, Any], etag: str | None, modified: str | None
) -> Literal["current", "newer", "unverifiable"]:
    """Compare the ``HEAD`` signals present in a response with the stored version's."""
    pairs = [
        (new, stored.get(key))
        for key, new in (("etag", etag), ("last_modified", modified))
        if new
    ]
    if not pairs:
        return "unverifiable"
    return "current" if all(new == old for new, old in pairs) else "newer"


def _station_list(
    handle: StoreHandle,
    archive: ArchiveFile,
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
) -> tuple[bytes, dict[str, Any]]:
    """Current stored list, first downloaded and archived when missing or changed.

    A stored list is re-validated with ``HEAD`` exactly as :func:`check_catalog`
    compares it: matching ETag/Last-Modified reuse it; a different signal, or none
    to compare, downloads the list and commits it with ``write_archive`` (identical
    bytes stay ``unchanged``) before the catalog reads it.
    """
    current = _current_archive(handle.root, archive)
    stale = current is None
    if current is not None:
        head = _http("HEAD", archive.url)
        status = _list_status(
            _archive_http(*current),
            head.headers.get("ETag"),
            head.headers.get("Last-Modified"),
        )
        stale = status != "current"
        if status == "unverifiable" and on_notice is not None:
            on_notice(
                Notice(
                    "warning",
                    "source_unverifiable",
                    f"{archive.server_path}: brak porównywalnego sygnału ETag/Last-Modified; "
                    "pobieranie i porównanie sumy SHA-256",
                )
            )
    if stale:
        response = _http("GET", archive.url)
        result = DownloadResult(
            data=response.content,
            url=str(response.url),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            content_length=_content_length(response),
        )
        write_archive(
            handle,
            archive=archive,
            response=result,
            on_progress=on_progress,
            on_notice=on_notice,
        )
        current = _current_archive(handle.root, archive)
    if current is None:  # pragma: no cover - write_archive always leaves a version
        raise IMGWStoreConflictError(
            f"Brak zapisanej wersji listy {archive.server_path}"
        )
    path, meta = current
    data = path.read_bytes()
    return data, {
        "source": get_dataset(archive.dataset).slug,
        "url": _archive_http(path, meta).get("url"),
        "file": path.relative_to(handle.root).as_posix(),
        "fetched_at": meta["downloaded_at"],
        "sha256": meta["sha256"],
    }


def _api(
    url: str, source: str, code_key: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    response = _http("GET", url)
    fetched_at = _utc(datetime.now(UTC))
    try:
        payload = response.json()
    except ValueError as exc:
        raise IMGWDataError(f"Niepoprawna odpowiedź JSON z {url}") from exc
    if not isinstance(payload, list) or not all(
        isinstance(row, dict) for row in payload
    ):
        raise IMGWDataError(f"Nieoczekiwany format odpowiedzi z {url}")
    rows: dict[str, dict[str, Any]] = {}
    for row in payload:
        code = str(row.get(code_key) or "").strip()
        if code:
            rows[code] = row
    return rows, {
        "source": source,
        "url": url,
        "file": None,
        "fetched_at": fetched_at,
        "count": len(rows),
        "sha256": hashlib.sha256(response.content).hexdigest(),
    }


_LOCATION_COLUMNS = ("station_code", "latitude", "longitude")


def _read_locations(
    data: bytes, *, user: bool
) -> tuple[dict[str, tuple[str, str, str | None]], list[str]]:
    """Read ``code -> (lon, lat, source label)`` from the static or user CSV.

    Both files start with ``station_code,latitude,longitude``; only the user file
    reads the optional ``source`` column.
    """
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = [name.strip() for name in reader.fieldnames or ()]
    if tuple(fields[: len(_LOCATION_COLUMNS)]) != _LOCATION_COLUMNS:
        found = ",".join(fields) or "brak"
        if user:
            raise IMGWValidationError(
                "Plik położeń użytkownika musi mieć kolumny "
                f"station_code,latitude,longitude[,source]; znaleziono {found}",
                details={"option": "user_locations", "found": fields},
            )
        raise IMGWValidationError(
            f"Lokalny plik położeń {STATIC_LOCATIONS} ma nieobsługiwany nagłówek "
            f"{found}; wymagane kolumny station_code,latitude,longitude — wygeneruj "
            "plik ponownie poleceniem python -m imgwtools.reference_data",
            details={"file": STATIC_LOCATIONS, "found": fields},
        )
    result: dict[str, tuple[str, str, str | None]] = {}
    problems: list[str] = []
    for line, row in enumerate(reader, start=2):
        row = {
            (key or "").strip(): (value or "").strip()
            for key, value in row.items()
            if key
        }
        code = row["station_code"]
        if not (len(code) == 9 and code.isdecimal()):
            problems.append(
                f"Wiersz {line}: niepoprawny kod stacji '{code}' w pliku położeń"
            )
            continue
        if code in result:
            problems.append(
                f"Wiersz {line}: powtórzony kod stacji {code} w pliku położeń"
            )
            continue
        result[code] = (
            row["longitude"],
            row["latitude"],
            (row.get("source") or None) if user else None,
        )
    return result, problems


def _optional_float(value: object) -> float | None:
    parsed = _number(value)
    return parsed[0] if parsed is not None else None


def _optional_int(value: object) -> int | None:
    parsed = _number(value)
    if parsed is None or parsed[0] != int(parsed[0]):
        return None
    return int(parsed[0])


def _series_codes(
    root: Path, problems: list[str]
) -> tuple[dict[str, set[str]], list[dict[str, Any]]]:
    """Station codes of the current series version of every dataset, by family.

    Offline: reads only the ``series.json`` index of the newest verified version
    of each series dataset; the index carries no station names or rivers. Also
    returns one ``series`` sidecar entry per index read.
    """
    codes: dict[str, set[str]] = {"hydro": set(), "meteo": set()}
    sources: list[dict[str, Any]] = []
    for descriptor in datasets():
        if not descriptor.in_store or descriptor.time_unit not in (
            "day",
            "month",
            "half_year",
        ):
            continue
        current = _current_series(_series_versions(root, descriptor))
        if current is None:
            continue
        relative = current.path.relative_to(root).as_posix()
        try:
            stations = json.loads(current.path.read_bytes())["stations"]
            if not isinstance(stations, dict):
                raise TypeError("pole stations nie jest obiektem")
        except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
            raise IMGWDataError(
                f"Nieczytelny indeks szeregu {relative}: {exc}"
            ) from exc
        except OSError as exc:
            raise io_error(exc) from exc
        family = "hydro" if descriptor.slug.startswith("hydro_") else "meteo"
        for code in stations:
            if len(code) == 9 and code.isdecimal():
                codes[family].add(code)
            else:
                problems.append(
                    f"Indeks szeregu {relative}: pominięto niepoprawny kod stacji '{code}'"
                )
        sources.append(
            {
                "source": "series",
                "dataset": descriptor.key,
                "url": None,
                "file": relative,
                "fetched_at": None,
                "count": len(stations),
                "sha256": current.meta["sha256"],
            }
        )
    return codes, sources


# --------------------------------------------------------------------------
# Catalog assembly
# --------------------------------------------------------------------------


def _feature(
    code: str,
    *,
    kind: Literal["hydro", "meteo"],
    listed: StationListEntry | None,
    api: Mapping[str, Any] | None,
    candidates: list[tuple[str, object, object]],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None]:
    geometry: dict[str, Any] | None = None
    location_source: str | None = None
    uncertainty: float | None = None
    reason: MissingReason | None = None
    first_rejection: MissingReason | None = None
    for source, lon, lat in candidates:
        verdict = _evaluate(lon, lat)
        if isinstance(verdict, str):
            if verdict != "none":
                rejections.append(
                    f"{code}: odrzucono punkt źródła {source} ({lon}, {lat}) — {verdict}"
                )
                first_rejection = first_rejection or verdict
            continue
        (point_lon, point_lat), uncertainty = verdict
        geometry = {"type": "Point", "coordinates": [point_lon, point_lat]}
        location_source = source
        break
    if geometry is None:
        reason = first_rejection or "none"
    river = (api or {}).get("rzeka") or (listed.river if listed else None)
    api_row = api or {}
    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": None,
        "name": (listed.name if listed else None)
        or str(api_row.get("stacja") or api_row.get("nazwa_stacji") or ""),
        "river": str(river) if river else None,
        "hydrographic_code": listed.hydrographic_code if listed else None,
        "river_order": listed.river_order if listed else None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        "active": api is not None,
        "established_year": _optional_int(api_row.get("rok_zalozenia_stacji")),
        "gauge_zero_m": _optional_float(api_row.get("rzedna_zerawodowskazu")),
        "river_km": _optional_float(api_row.get("kilometr_biegu_rzeki")),
        "elevation_m": _optional_float(api_row.get("wysokosc_npm")),
    }
    feature = {
        "type": "Feature",
        "id": code,
        "geometry": geometry,
        "properties": {key: properties[key] for key in _PROPERTY_ORDER},
    }
    return feature, location_source


def _list_rows(
    data: bytes, *, kind: Literal["hydro", "meteo"], problems: list[str]
) -> dict[str, StationListEntry]:
    """Rows of a station list by code; a repeated code keeps its first row."""
    rows: dict[str, StationListEntry] = {}
    for station in parse_stations_csv(data, kind=kind):
        code = station.station_code
        if not (len(code) == 9 and code.isdecimal()):
            problems.append(f"Lista {kind}: pominięto niepoprawny kod stacji '{code}'")
            continue
        first = rows.setdefault(code, station)
        if first is not station:
            # IMGW lists e.g. meteo station 252150270 twice, with two short codes.
            problems.append(
                f"Lista {kind}: powtórzony kod stacji {code} "
                f"({_list_row_text(first)} oraz {_list_row_text(station)}); "
                "katalog używa pierwszego wiersza"
            )
    return rows


def _list_row_text(station: StationListEntry) -> str:
    fields = (
        station.name,
        station.river,
        station.hydrographic_code,
        station.short_code and f"kod krótki {station.short_code}",
    )
    return ", ".join(field for field in fields if field)


def _catalog_bytes(
    *,
    lists: Mapping[str, Mapping[str, StationListEntry]],
    apis: Mapping[str, Mapping[str, Mapping[str, Any]]],
    series: Mapping[str, set[str]],
    static: Mapping[str, tuple[str, str, str | None]],
    user: Mapping[str, tuple[str, str, str | None]],
    problems: list[str],
    rejections: list[str],
) -> tuple[bytes, int, int, dict[str, int], list[str]]:
    for api_kind, api in apis.items():
        for code in api:
            if not (len(code) == 9 and code.isdecimal()):
                problems.append(
                    f"API {api_kind}: pominięto niepoprawny kod stacji '{code}'"
                )
    listed = {
        kind: {
            code
            for code in (*lists[kind], *apis[kind])
            if len(code) == 9 and code.isdecimal()
        }
        for kind in ("hydro", "meteo")
    }
    codes = {kind: listed[kind] | series[kind] for kind in ("hydro", "meteo")}
    shared = sorted(codes["hydro"] & codes["meteo"])
    if shared:
        raise IMGWDataError(
            f"Kody stacji występują jednocześnie w rodzinie hydro i meteo: {', '.join(shared[:10])}"
        )
    # The static file holds IMGW-PIB hydrological gauge coordinates, so a code known
    # only from it is still a (historical) hydro station: no code may disappear. The
    # user file only fills locations and names no station family.
    codes["hydro"] |= set(static) - codes["meteo"]
    known = codes["hydro"] | codes["meteo"]
    # Codes measured in a stored series but absent from every list, API and the
    # static file (e.g. stations closed long ago) stay as historical stations.
    series_only = sorted(
        (series["hydro"] | series["meteo"])
        - listed["hydro"]
        - listed["meteo"]
        - set(static)
    )
    unknown = sorted(set(user) - known)
    if unknown:
        problems.append(
            f"Plik położeń użytkownika: {len(unknown)} kodów spoza list, API, pliku "
            f"statycznego i szeregów (np. {unknown[0]}); plik użytkownika uzupełnia "
            "tylko położenia"
        )
    features = []
    used: dict[str, int] = {}
    without = 0
    for code in sorted(known):
        kind: Literal["hydro", "meteo"] = "hydro" if code in codes["hydro"] else "meteo"
        api = apis[kind].get(code)
        candidates: list[tuple[str, object, object]] = []
        if api is not None:
            candidates.append((f"api_{kind}", api.get("lon"), api.get("lat")))
        if code in static:
            candidates.append(("static", static[code][0], static[code][1]))
        if code in user:
            candidates.append(("user", user[code][0], user[code][1]))
        feature, source = _feature(
            code,
            kind=kind,
            listed=lists[kind].get(code),
            api=api,
            candidates=candidates,
            rejections=rejections,
        )
        if source is None:
            without += 1
        else:
            used[source] = used.get(source, 0) + 1
        features.append(feature)
    document = {"type": "FeatureCollection", "features": features}
    return _canonical(document), len(features), without, used, series_only


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def _local_source(data: bytes, *, source: str, file: str, count: int) -> dict[str, Any]:
    return {
        "source": source,
        "url": None,
        "file": file,
        "fetched_at": None,
        "count": count,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _user_file(user_locations: PathArg | None) -> tuple[Path, bytes] | None:
    if user_locations is None:
        return None
    path = Path(user_locations).expanduser()
    try:
        return path, path.read_bytes()
    except OSError as exc:
        raise IMGWValidationError(
            f"Nie można odczytać pliku położeń użytkownika: {path}"
        ) from exc


def _static_file() -> tuple[Path, bytes | None]:
    """Local IMGW-PIB coordinates ``station_code,latitude,longitude``; ``None`` when absent.

    IMGW data is not shipped with the package: ``python -m imgwtools.reference_data`` writes
    the file. Without ``pydantic-settings`` the directory comes from ``IMGW_DATA_DIR``.
    """
    try:
        from imgwtools.config import settings
    except ImportError:
        data_dir = Path(os.environ.get("IMGW_DATA_DIR", "data"))
    else:
        data_dir = settings.data_dir
    path = data_dir / STATIC_LOCATIONS
    try:
        return path, path.read_bytes()
    except FileNotFoundError:
        return path, None
    except OSError as exc:
        raise IMGWValidationError(
            f"Nie można odczytać lokalnego pliku położeń: {path}"
        ) from exc


def _current_catalog(root: Path) -> tuple[Path, dict[str, Any]] | None:
    slot = _validate_slot(root, CATALOG_SLOT)
    return _newest_downloaded(_existing(slot, CATALOG_FILE))


def _catalog_codes(path: Path, meta: Mapping[str, Any]) -> set[str]:
    """Station codes of a stored catalog version, verified against its sidecar."""
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError("SHA-256 niezgodne z sidecarem")
        return {feature["id"] for feature in json.loads(data)["features"]}
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise IMGWStoreConflictError(
            f"Uszkodzona wersja katalogu stacji {path}: {exc}"
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc


def check_catalog(
    root: RootArg,
    /,
    *,
    user_locations: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Compare catalog sources with the store using HEAD and local hashes only.

    Station lists are checked with ``HEAD``; the public station APIs expose no
    stable signal and are reported as ``unverifiable``. Location files are
    compared by SHA-256 with the entries recorded in the current catalog sidecar;
    the station codes of the current series indexes are compared with the codes
    of the current catalog. Nothing is downloaded or written.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    user_locations : str, os.PathLike or None, optional
        User CSV ``station_code,latitude,longitude[,source]`` whose SHA-256 is
        compared with the one recorded in the catalog.
    on_progress : ProgressHook or None, optional
        Called after each station list and once at the end with the overall
        catalog status.
    on_notice : NoticeHook or None, optional
        Receives a ``source_unverifiable`` warning for each public station API.
    cancel : Cancel or None, optional
        Polled before each station list; once it returns ``True`` the remaining
        lists are reported as ``unverifiable`` with error ``"anulowano"``.

    Returns
    -------
    StorePlan
        Plan with one item per station list (``current``, ``newer``, ``missing``,
        ``unverifiable`` or ``check_failed``) and ``store catalog`` actions: one
        ``unverifiable`` per public API, one per location file (``current``, or
        ``newer`` when the file appeared, disappeared or changed; ``missing``
        without a catalog), one for the series indexes (``current``, ``newer``
        when a series station code is absent from the catalog, ``missing``
        without a catalog) and a final catalog action that is ``missing``
        without a catalog, ``newer`` when any source changed, otherwise
        ``unverifiable``.

    Raises
    ------
    IMGWStoreError
        If ``root`` is not a supported IMGW store or a version path contains a
        symbolic link.
    IMGWStoreConflictError
        If a stored list or catalog version is corrupted.
    IMGWValidationError
        If a location file exists but cannot be read.
    IMGWDataError
        If a station list responds with an invalid ``Content-Length`` header, or
        a current series index is corrupted; with code ``io_error``
        (``details.path``) if the system cannot read a stored version.
    """
    handle = _handle(root)
    user = _user_file(user_locations)
    catalog = _current_catalog(handle.root)
    recorded = {
        entry.get("source"): entry.get("sha256")
        for entry in (catalog[1]["extra"].get("catalog", []) if catalog else [])
        if isinstance(entry, dict)
    }
    items: list[PlanItem] = []
    actions: list[PlanAction] = []
    sources = station_source_files()
    total = len(sources) + 2
    cancelled = False
    for index, archive in enumerate(sources, start=1):
        if _cancelled(cancel):
            cancelled = True
            items.append(
                PlanItem(
                    archive, "unverifiable", None, None, None, None, None, "anulowano"
                )
            )
            continue
        current = _current_archive(handle.root, archive)
        local_path, local_sha, old_http = (
            (current[0], current[1]["sha256"], _archive_http(*current))
            if current
            else (None, None, {})
        )
        try:
            response = _http("HEAD", archive.url)
        except IMGWConnectionError as exc:
            items.append(
                PlanItem(
                    archive,
                    "check_failed",
                    local_path,
                    local_sha,
                    None,
                    None,
                    None,
                    str(exc),
                )
            )
        else:
            etag = response.headers.get("ETag")
            modified = response.headers.get("Last-Modified")
            length = _content_length(response)
            status: Literal["current", "newer", "missing", "unverifiable"] = (
                "missing" if current is None else _list_status(old_http, etag, modified)
            )
            reason = (
                "brak porównywalnego sygnału ETag/Last-Modified"
                if status == "unverifiable"
                else None
            )
            items.append(
                PlanItem(
                    archive,
                    status,
                    local_path,
                    local_sha,
                    etag,
                    modified,
                    length,
                    reason,
                )
            )
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    total,
                    "source",
                    items[-1].status,
                    f"Sprawdzono {archive.server_path}",
                )
            )
    for url in (HYDRO_API_URL, METEO_API_URL):
        actions.append(
            PlanAction(
                "store catalog",
                "unverifiable",
                f"{url}: publiczne API nie udostępnia stabilnego sygnału aktualności; sprawdzenie wymaga pobrania",
            )
        )
        if on_notice is not None:
            on_notice(
                Notice(
                    "warning",
                    "source_unverifiable",
                    f"Nie można sprawdzić aktualności {url} bez pobrania",
                )
            )
    static_path, static_bytes = _static_file()
    local_files: list[tuple[str, bytes | None, Path]] = [
        ("static", static_bytes, static_path)
    ]
    if user is not None:
        local_files.append(("user", user[1], user[0]))
    for source, data, path in local_files:
        digest = hashlib.sha256(data).hexdigest() if data is not None else None
        if catalog is None:
            file_status: Literal["current", "newer", "missing"] = "missing"
        else:
            file_status = "current" if recorded.get(source) == digest else "newer"
        detail = (
            f"sha256 {digest}"
            if digest is not None
            else f"brak pliku {path.as_posix()}"
        )
        actions.append(
            PlanAction("store catalog", file_status, f"plik położeń {source}: {detail}")
        )
    series, _ = _series_codes(handle.root, [])
    series_codes = series["hydro"] | series["meteo"]
    if catalog is None:
        series_status: Literal["current", "newer", "missing"] = "missing"
        series_detail = f"{len(series_codes)} kodów stacji"
    else:
        absent = sorted(series_codes - _catalog_codes(*catalog))
        series_status = "newer" if absent else "current"
        series_detail = (
            f"{len(absent)} kodów spoza katalogu (np. {absent[0]})"
            if absent
            else f"{len(series_codes)} kodów stacji w katalogu"
        )
    actions.append(
        PlanAction("store catalog", series_status, f"indeksy szeregów: {series_detail}")
    )
    if catalog is None:
        overall: Literal["missing", "newer", "unverifiable"] = "missing"
    elif any(item.status in ("newer", "missing") for item in items) or any(
        action.status == "newer" for action in actions
    ):
        overall = "newer"
    else:
        overall = "unverifiable"
    actions.append(
        PlanAction(
            "store catalog",
            overall,
            f"katalog stacji: {catalog[0].relative_to(handle.root).as_posix() if catalog else 'brak wersji'}",
        )
    )
    if on_progress is not None:
        on_progress(
            Progress(
                total, total, "source", overall, "Sprawdzono źródła katalogu stacji"
            )
        )
    return StorePlan(
        schema="imgw-plan/1",
        root=handle.root,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state={},
        actions=tuple(actions),
        cancelled=cancelled,
    )


def build_catalog(
    root: RootArg,
    /,
    *,
    user_locations: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> CatalogReport:
    """
    Build ``stations.geojson`` from station lists, public APIs and location files.

    Station lists are re-validated with ``HEAD`` (as :func:`check_catalog`
    compares them): a list that is missing, has a different ETag/Last-Modified or
    no comparable signal is downloaded and stored with ``write_archive`` first,
    so the catalog always reflects the current lists; the public hydro and meteo
    APIs are always downloaded. Every code of the lists, the APIs, the static
    file and the current series indexes is kept (a code only in the static file
    is a hydro station; a code only in a series index is a historical station of
    the series family with ``geometry`` null unless the user file locates it,
    counted in ``from_series``); codes only in the user file are reported in
    ``problems``. Location precedence: API, then the local static file
    ``station_code,latitude,longitude`` (``settings.data_dir``), then the user
    CSV ``station_code,latitude,longitude[,source]``.
    A missing static file is not an error: it is reported in ``problems`` and
    recorded in the sidecar as ``available: false``. Every series index read is
    recorded in the sidecar as a ``series`` source. Identical content (same
    SHA-256) yields ``unchanged`` without a new version.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    user_locations : str, os.PathLike or None, optional
        User CSV ``station_code,latitude,longitude[,source]`` with fallback
        station locations.
    on_progress : ProgressHook or None, optional
        Called after each build step (station lists, APIs, assembly, publication).
    on_notice : NoticeHook or None, optional
        Receives catalog problems, rejected locations, location source summaries,
        a ``series_station`` summary of stations known only from series indexes,
        stations without location, ``source_unverifiable`` for a list without a
        comparable signal, writer notices of downloaded lists, a
        ``leftover_incoming`` warning for every removed staging directory older
        than 24 hours and the ``license_terms`` notice when a new version is
        created.
    cancel : Cancel or None, optional
        Polled between steps; once it returns ``True`` the build stops with a
        ``cancelled`` report and no catalog version is published.

    Returns
    -------
    CatalogReport
        Status ``created``, ``unchanged`` or ``cancelled``, the path of the
        current ``stations.geojson``, the station count, the number of stations
        without location, the number of stations known only from series indexes
        and the problems found in the sources.

    Raises
    ------
    IMGWStoreError
        If ``root`` is not a supported IMGW store or collides with a Kartograf
        store or project.
    IMGWConnectionError
        If a station list cannot be checked or downloaded, or a public API cannot
        be downloaded.
    IMGWDataError
        If an API response is not a JSON list of objects, a current series index
        is unreadable, or a station code appears in both the hydro and meteo
        families.
    IMGWValidationError
        If a location file exists but cannot be read or does not start with the
        ``station_code,latitude,longitude`` columns (the static file in the old
        ``id,X,Y`` format must be regenerated with
        ``python -m imgwtools.reference_data``); raised before any download.
    IMGWStoreConflictError
        If a stored version is corrupted or the new version cannot be published
        atomically.
    """
    handle = _handle(root)
    _check_kartograf(handle.root)
    user = _user_file(user_locations)
    # Location files are validated before any download, so a bad header writes nothing.
    static_path, static_bytes = _static_file()
    static, static_problems = (
        _read_locations(static_bytes, user=False)
        if static_bytes is not None
        else ({}, [])
    )
    user_rows, user_problems = (
        _read_locations(user[1], user=True) if user is not None else ({}, [])
    )
    total = 6

    def progress(step: int, status: str, message: str) -> None:
        if on_progress is not None:
            on_progress(Progress(step, total, "step", status, message))

    def stopped() -> CatalogReport | None:
        if _cancelled(cancel):
            return CatalogReport("cancelled", None, 0, 0, 0, ())
        return None

    sources: list[dict[str, Any]] = []
    lists: list[bytes] = []
    for step, archive in enumerate(station_source_files(), start=1):
        if (report := stopped()) is not None:
            return report
        data, source = _station_list(
            handle, archive, on_progress=None, on_notice=on_notice
        )
        lists.append(data)
        sources.append(source)
        progress(step, "done", f"Lista stacji {archive.server_path}")
    apis = []
    for step, (url, source, key) in enumerate(
        (
            (HYDRO_API_URL, "api_hydro", "id_stacji"),
            (METEO_API_URL, "api_meteo", "kod_stacji"),
        ),
        start=3,
    ):
        if (report := stopped()) is not None:
            return report
        rows, record = _api(url, source, key)
        apis.append(rows)
        sources.append(record)
        progress(step, "done", f"Pobrano {url}")
    if (report := stopped()) is not None:
        return report
    problems: list[str] = []
    rejections: list[str] = []
    parsed_lists = {
        "hydro": _list_rows(lists[0], kind="hydro", problems=problems),
        "meteo": _list_rows(lists[1], kind="meteo", problems=problems),
    }
    sources[0]["count"] = len(parsed_lists["hydro"])
    sources[1]["count"] = len(parsed_lists["meteo"])
    if static_bytes is None:
        problems.append(
            f"Brak lokalnego pliku położeń {static_path.as_posix()}; źródło static pominięte "
            "(dane IMGW-PIB pobiera python -m imgwtools.reference_data)"
        )
        sources.append(
            {
                "source": "static",
                "url": None,
                "file": STATIC_LOCATIONS,
                "fetched_at": None,
                "count": 0,
                "sha256": None,
                "available": False,
            }
        )
    else:
        problems.extend(static_problems)
        sources.append(
            _local_source(
                static_bytes, source="static", file=STATIC_LOCATIONS, count=len(static)
            )
            | {"available": True}
        )
    if user is not None:
        problems.extend(user_problems)
        sources.append(
            _local_source(
                user[1], source="user", file=user[0].name, count=len(user_rows)
            )
        )
    series, series_sources = _series_codes(handle.root, problems)
    sources.extend(series_sources)
    data, count, without, used, series_only = _catalog_bytes(
        lists=parsed_lists,
        apis={"hydro": apis[0], "meteo": apis[1]},
        series=series,
        static=static,
        user=user_rows,
        problems=problems,
        rejections=rejections,
    )
    progress(5, "done", f"Zbudowano katalog {count} stacji")
    if on_notice is not None:
        for problem in problems:
            on_notice(Notice("warning", "catalog_problem", problem))
        for rejection in rejections:
            on_notice(Notice("warning", "location_rejected", rejection))
        for source, number in sorted(used.items()):
            on_notice(
                Notice(
                    "info", "location_source", f"Położenie z {source}: {number} stacji"
                )
            )
        if user is not None:
            labels = sorted({label for _, _, label in user_rows.values() if label})
            if labels:
                on_notice(
                    Notice(
                        "info",
                        "location_source",
                        f"Źródła w pliku użytkownika: {', '.join(labels)}",
                    )
                )
        if series_only:
            on_notice(
                Notice(
                    "info",
                    "series_station",
                    f"{len(series_only)} stacji wyłącznie z indeksów szeregów "
                    f"(historyczne, active=false): {', '.join(series_only[:10])}"
                    + (" …" if len(series_only) > 10 else ""),
                )
            )
        if without:
            on_notice(
                Notice(
                    "warning",
                    "station_without_location",
                    f"{without} stacji bez położenia (geometry=null)",
                )
            )
    if (report := stopped()) is not None:
        return report
    problems.extend(rejections)
    sha = hashlib.sha256(data).hexdigest()
    current = _current_catalog(handle.root)
    if current is not None and current[1]["sha256"] == sha:
        progress(total, "unchanged", "Katalog stacji bez zmian")
        return CatalogReport(
            "unchanged", current[0], count, without, len(series_only), tuple(problems)
        )
    now = datetime.now(UTC)
    label = now.date().isoformat()
    meta = {
        "schema": "imgw-meta/1",
        "producer": "imgwtools",
        "producer_version": __version__,
        "dataset": CATALOG_DATASET,
        "country": "PL",
        "provider": "IMGW-PIB",
        "request": {"user_locations": user[0].name if user else None},
        "license": _license_document(get_dataset("pl.imgw.hydro_stations").license),
        "downloaded_at": _utc(now),
        "sha256": sha,
        "size_bytes": len(data),
        "extra": {
            "version": {"label": label, "label_source": "downloaded"},
            "derived": "catalog",
            "catalog": sources,
        },
    }
    path, created = _publish_version(
        handle.root,
        slot=CATALOG_SLOT,
        name=CATALOG_FILE,
        data=data,
        meta=meta,
        label=label,
        on_notice=on_notice,
    )
    status: Literal["created", "unchanged"] = "created" if created else "unchanged"
    progress(total, status, f"Katalog stacji: {path.parent.name}")
    if created and on_notice is not None:
        license_ = get_dataset("pl.imgw.hydro_stations").license
        on_notice(
            Notice(
                "info",
                LICENSE_NOTICE,
                f"{license_.attribution}. Do użytku prywatnego i badawczego; inne zastosowania wymagają "
                "sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.",
            )
        )
    return CatalogReport(
        status, path, count, without, len(series_only), tuple(problems)
    )
