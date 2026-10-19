"""Versioned station catalogs ``stations.geojson`` of the IMGW-PIB and ČHMÚ station sources."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import socket
import uuid
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from functools import lru_cache
from importlib.resources import files
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal

import httpx

from imgwtools._parsing.chmi import (
    MetadataTable,
    parse_listing,
    read_metadata,
    station_coordinates,
    station_rows,
)
from imgwtools._parsing.stations import parse_stations_csv
from imgwtools._version import __version__
from imgwtools.datasets import (
    _CATALOG_DATASETS,
    STATION_CODE_PATTERN,
    ArchiveFile,
    License,
    ProviderDescriptor,
    _license_document,
    datasets,
    get_dataset,
    get_provider,
    station_source_files,
)
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWStoreConflictError,
    IMGWValidationError,
    io_error,
)
from imgwtools.fetch import _IDENTIFY, DEFAULT_TIMEOUT, DownloadResult
from imgwtools.models import StationListEntry
from imgwtools.store.content import content_sha256
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
    _canonical,
    _check_kartograf,
    _cleanup,
    _existing,
    _fsync_dir,
    _publish_dir,
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
# Version directory of each provider's station catalog (ADR-003 D5): the IMGW-PIB
# catalog keeps the 3.0.0 layout and the catalog of another provider lies in a
# directory named after its slug inside it (slugs start with a letter, labels with
# a digit).
_CATALOG_DIRS: Mapping[str, str] = MappingProxyType(
    {"IMGW-PIB": CATALOG_SLOT, "CHMI": f"{CATALOG_SLOT}/chmi_stations"}
)
# Slug directory under ``stations/versions/`` → provider of the catalog inside it.
_NESTED_CATALOGS: Mapping[str, str] = MappingProxyType(
    {
        PurePosixPath(directory).name: provider
        for provider, directory in _CATALOG_DIRS.items()
        if directory != CATALOG_SLOT
    }
)
HYDRO_API_URL = f"{IMGW_API_URL}/hydro"
METEO_API_URL = f"{IMGW_API_URL}/meteo"
STATIC_LOCATIONS = "hydro_stations_locations.csv"
BORDER_RESOURCE = "poland_border_wgs84.geojson"
CZECHIA_BORDER_RESOURCE = "czechia_border_wgs84.geojson"
# Country outline of each provider's station locations (Natural Earth 1:10m Admin 0).
_BORDERS: Mapping[str, str] = MappingProxyType(
    {"IMGW-PIB": BORDER_RESOURCE, "CHMI": CZECHIA_BORDER_RESOURCE}
)
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
# ČHMÚ catalog sources that are not archived (spec 2026-10-18 §7.2), relative to the
# provider's base URL: hydro now meta1 and meta3, the directory of the daily meteo
# now meta1-<YYYYMMDD>.json files.
_CHMI_HYDRO_NOW = "hydrology/now/metadata/meta1.json"
_CHMI_HYDRO_META3 = "hydrology/now/metadata/meta3.json"
_CHMI_METEO_NOW_DIR = "meteorology/climate/now/metadata/"
_CHMI_METEO_NOW_FILE = re.compile(r"^meta1-[0-9]{8}\.json$")
# Units of the SPA thresholds (SPAH_UNIT, SPAQ_UNIT) in the catalog.
_THRESHOLD_UNITS: Mapping[str, str] = MappingProxyType({"CM": "cm", "M3_S": "m3/s"})

MissingReason = Literal["none", "zero", "outside_country"]
MeteoKind = Literal["climate", "precipitation"]
# ``meteo_kind`` of an IMGW-PIB station measured in the current series of a dataset;
# a station in both series is a climate station (its programme includes precipitation).
_METEO_KINDS: Mapping[str, MeteoKind] = MappingProxyType(
    {
        "pl.imgw.meteo_climate_daily": "climate",
        "pl.imgw.meteo_precip_daily": "precipitation",
    }
)
# Location candidate ``(source, longitude, latitude)`` as published.
_Candidate = tuple[str, object, object]

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
    skip: Collection[str] = (),
) -> tuple[Path, bool]:
    """Stage ``name`` + sidecar and publish ``<slot>/<label>_<sha8>`` without replacement.

    Files are published by hard links, the sidecar last (``_publish_dir``). Returns the
    main file path and ``True`` when a new version was created; an identical
    concurrently published version yields ``False``. ``on_notice`` receives a
    ``leftover_incoming`` warning for every removed staging directory older than 24 h.
    ``attachments`` are extra files (name → bytes) published before the sidecar; the
    caller documents them in ``meta``. ``skip`` names child directories of the slot
    that are not its versions (catalogs of other providers).
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
            _publish_dir(staging, target, f"{name}.meta.json")
        except FileExistsError as exc:
            for old_file, old_meta in _existing(slot_dir, name, skip=skip):
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
            raise IMGWDataError("Pusty obrys: wielokąt nie ma krawędzi")
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


@lru_cache(maxsize=len(_BORDERS))
def _border(resource: str) -> _Border:
    document = json.loads(_resource(resource))
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
    lon_raw: object, lat_raw: object, *, border: str = BORDER_RESOURCE
) -> tuple[tuple[float, float], float] | MissingReason:
    """Point and uncertainty of a published location, or why it is rejected.

    ``border`` names the country outline resource (Poland by default).
    """
    lon, lat = _number(lon_raw), _number(lat_raw)
    if lon is None or lat is None:
        return "none"
    if lon[0] == 0 and lat[0] == 0:
        return "zero"
    outline = _border(border)
    if not (
        outline.contains(lon[0], lat[0])
        or outline.near(lon[0], lat[0], BORDER_TOLERANCE_M)
    ):
        return "outside_country"
    return (lon[0], lat[0]), _uncertainty_m(lat[0], lon[1], lat[1])


def _distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Distance of two ``(lon, lat)`` points in metres (local metric approximation)."""
    scale_lon = _METRES_PER_DEGREE * math.cos(math.radians((first[1] + second[1]) / 2))
    return math.hypot(
        (second[0] - first[0]) * scale_lon,
        (second[1] - first[1]) * _METRES_PER_DEGREE,
    )


def _locate(
    code: str,
    candidates: Sequence[_Candidate],
    *,
    border: str,
    rejections: list[str],
) -> tuple[int, tuple[float, float], float] | MissingReason:
    """
    First valid location candidate: its index, point and uncertainty.

    A rejected point of a candidate before it is reported in ``rejections``; a
    bad point of a higher source never blocks a valid lower one. Without a valid
    candidate the reason of the first rejection (or ``"none"``) is returned.
    """
    first_rejection: MissingReason | None = None
    for index, (source, lon, lat) in enumerate(candidates):
        verdict = _evaluate(lon, lat, border=border)
        if isinstance(verdict, str):
            if verdict != "none":
                rejections.append(
                    f"{code}: odrzucono punkt źródła {source} ({lon}, {lat}) — {verdict}"
                )
                first_rejection = first_rejection or verdict
            continue
        point, uncertainty = verdict
        return index, point, uncertainty
    return first_rejection or "none"


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def _http(
    method: str,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers)
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


def _headers(provider: str) -> Mapping[str, str] | None:
    """Request headers of a provider's sources: ČHMÚ requests name ``imgwtools/<version>``."""
    return _IDENTIFY if provider == "CHMI" else None


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


def _reference(
    root: Path, archive: ArchiveFile, current: tuple[Path, dict[str, Any]]
) -> tuple[Mapping[str, Any], Path | None]:
    """
    Signal a stored station list is compared with, and the observation giving it.

    The reference signal of the slot (ADR-003 D18): the newest observation of
    the current version, without one the version's ``extra.http`` (a version
    without it is corrupted). The observation path is relative to ``root``;
    None when the signal is the version's own, always for IMGW-PIB lists.
    """
    # The reader imports this module, so it is imported at call time.
    from imgwtools.store.reader import _archive_slot as slot_of
    from imgwtools.store.reader import _reference_signal

    own = _archive_http(*current)
    slot = slot_of(archive.server_path)
    reference = None if slot is None else _reference_signal(root, slot=slot)
    if reference is None or reference.observation is None:
        return own, None
    signal = {"etag": reference.etag, "last_modified": reference.last_modified}
    return signal, reference.observation.relative_to(root)


def _station_list(
    handle: StoreHandle,
    archive: ArchiveFile,
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
) -> tuple[bytes, dict[str, Any]]:
    """Current stored list, first downloaded and archived when missing or changed.

    A stored list is re-validated with ``HEAD`` exactly as :func:`check_catalog`
    compares it, against the reference signal of its slot: matching
    ETag/Last-Modified reuse it; a different signal, or none to compare,
    downloads the list and commits it with ``write_archive`` (identical bytes
    stay ``unchanged``, other bytes of a list with a canonical form and the same
    content are only observed) before the catalog reads it. The sidecar entry
    of a list with a canonical form carries its ``content_sha256``.
    """
    headers = _headers(get_dataset(archive.dataset).provider)
    current = _current_archive(handle.root, archive)
    stale = current is None
    if current is not None:
        signal, _ = _reference(handle.root, archive, current)
        head = _http("HEAD", archive.url, headers=headers)
        status = _list_status(
            signal, head.headers.get("ETag"), head.headers.get("Last-Modified")
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
        response = _http("GET", archive.url, headers=headers)
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
    record = {
        "source": get_dataset(archive.dataset).slug,
        "url": _archive_http(path, meta).get("url"),
        "file": path.relative_to(handle.root).as_posix(),
        "fetched_at": meta["downloaded_at"],
        "sha256": meta["sha256"],
    }
    if "content_sha256" in meta:
        record.update(
            content_sha256=meta["content_sha256"], content_form=meta["content_form"]
        )
    return data, record


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
    data: bytes, *, user: bool, provider: ProviderDescriptor
) -> tuple[dict[str, tuple[str, str, str | None]], list[str]]:
    """Read ``code -> (lon, lat, source label)`` from the static or user CSV.

    Both files start with ``station_code,latitude,longitude``; only the user file
    reads the optional ``source`` column. Codes of ``provider`` are read, codes of
    another provider are skipped silently and other codes are problems.
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
    own = re.compile(provider.station_code_pattern)
    known = re.compile(STATION_CODE_PATTERN)
    result: dict[str, tuple[str, str, str | None]] = {}
    problems: list[str] = []
    for line, row in enumerate(reader, start=2):
        row = {
            (key or "").strip(): (value or "").strip()
            for key, value in row.items()
            if key
        }
        code = row["station_code"]
        if not own.fullmatch(code):
            if not known.fullmatch(code):
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
    root: Path, problems: list[str], *, provider: ProviderDescriptor
) -> tuple[dict[str, set[str]], list[dict[str, Any]], dict[str, MeteoKind]]:
    """Station codes of the current series version of each provider dataset, by family.

    Offline: reads only the ``series.json`` index of the newest verified version
    of each series dataset of ``provider``; the index carries no station names
    or rivers. Also returns one ``series`` sidecar entry per index read and the
    ``meteo_kind`` of every station in a series of ``_METEO_KINDS``.
    """
    pattern = re.compile(provider.station_code_pattern)
    codes: dict[str, set[str]] = {"hydro": set(), "meteo": set()}
    kinds: dict[str, MeteoKind] = {}
    sources: list[dict[str, Any]] = []
    for descriptor in datasets(provider=provider.id):
        if (
            not descriptor.in_store
            or descriptor.kind is None
            or descriptor.time_unit not in ("day", "month", "half_year")
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
        meteo_kind = _METEO_KINDS.get(descriptor.key)
        for code in stations:
            if pattern.fullmatch(code):
                codes[descriptor.kind].add(code)
                if meteo_kind is not None and kinds.get(code) != "climate":
                    kinds[code] = meteo_kind
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
    return codes, sources, kinds


# --------------------------------------------------------------------------
# Catalog assembly
# --------------------------------------------------------------------------


def _placement(
    located: tuple[int, tuple[float, float], float] | MissingReason,
    candidates: Sequence[_Candidate],
) -> tuple[dict[str, Any] | None, str | None, float | None, MissingReason | None]:
    """GeoJSON geometry, location source, uncertainty and missing reason of a station."""
    if isinstance(located, str):
        return None, None, None, located
    index, (lon, lat), uncertainty = located
    geometry = {"type": "Point", "coordinates": [lon, lat]}
    return geometry, candidates[index][0], uncertainty, None


def _feature(
    code: str,
    *,
    kind: Literal["hydro", "meteo"],
    meteo_kind: MeteoKind | None,
    listed: StationListEntry | None,
    api: Mapping[str, Any] | None,
    candidates: list[_Candidate],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None]:
    located = _locate(code, candidates, border=BORDER_RESOURCE, rejections=rejections)
    geometry, location_source, uncertainty, reason = _placement(located, candidates)
    river = (api or {}).get("rzeka") or (listed.river if listed else None)
    api_row = api or {}
    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": meteo_kind,
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
    meteo_kinds: Mapping[str, MeteoKind],
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
            meteo_kind=meteo_kinds.get(code) if kind == "meteo" else None,
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
# ČHMÚ catalog (spec 2026-10-18 §7)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Metadata:
    """
    One ČHMÚ station metadata source of the catalog.

    Attributes
    ----------
    source : str
        Source name of the sidecar and of ``location_source``, e.g.
        ``"chmi_hydro_now"``.
    kind : {"hydro", "meteo"}
        Station family of the file.
    table : MetadataTable
        Rows of the file with columns located by name.
    rows : Mapping of str to int
        Row chosen for every valid station code.
    thresholds : bool
        Whether the SPA thresholds of the file are used (not for ``meta3``).
    """

    source: str
    kind: Literal["hydro", "meteo"]
    table: MetadataTable
    rows: Mapping[str, int]
    thresholds: bool

    def text(self, code: str, column: str) -> str | None:
        """
        Text of a station's row in a column.

        Parameters
        ----------
        code : str
            Station code.
        column : str
            Column name.

        Returns
        -------
        str or None
            The text; None without the row, the column or a value.
        """
        index = self.rows.get(code)
        if index is None or not self.table.has(column):
            return None
        return self.table.text(index, column)

    def number(self, code: str, column: str) -> int | float | None:
        """
        Number of a station's row in a column, as published.

        Parameters
        ----------
        code : str
            Station code.
        column : str
            Column name.

        Returns
        -------
        int or float or None
            An integer as is and a decimal as the float of its published
            notation; None without the row, the column or a value.

        Raises
        ------
        IMGWDataError
            If the cell is not a number or lies beyond the float range.
        """
        index = self.rows.get(code)
        if index is None or not self.table.has(column):
            return None
        value = self.table.number(index, column)
        if value is None or isinstance(value, int):
            return value
        number = float(value)
        if not math.isfinite(number):
            raise self.table.cell_error(index, column, f"liczba {value} poza zakresem")
        return number


def _metadata(
    data: bytes,
    *,
    source: str,
    kind: Literal["hydro", "meteo"],
    filename: str,
    problems: list[str],
    thresholds: bool = True,
) -> _Metadata:
    """Parse a ČHMÚ metadata file and choose one row per valid station code."""
    table = read_metadata(data, filename=filename)
    if kind == "hydro":
        table.require("objID", "STATION_NAME", "STREAM_NAME", "GEOGR1", "GEOGR2")
    else:
        table.require("WSI", "FULL_NAME", "GEOGR1", "GEOGR2")
    chosen = station_rows(table, kind=kind)
    pattern = re.compile(get_provider("CHMI").station_code_pattern)
    rows: dict[str, int] = {}
    for code, index in chosen.rows.items():
        if pattern.fullmatch(code):
            rows[code] = index
        else:
            problems.append(
                f"Źródło {source}: pominięto niepoprawny kod stacji '{code}'"
            )
    for code in chosen.duplicates:
        if code in rows:
            problems.append(
                f"Źródło {source}: powtórzony kod stacji {code}; katalog używa "
                "pierwszego wiersza"
            )
    return _Metadata(source, kind, table, rows, thresholds)


def _chmi_get(url: str, *, source: str, form: str) -> tuple[bytes, dict[str, Any]]:
    """A ČHMÚ metadata file that is not archived and its sidecar entry (count 0)."""
    response = _http("GET", url, headers=_IDENTIFY)
    data = response.content
    try:
        content = content_sha256(data, form=form)
    except IMGWDataError as exc:
        raise IMGWDataError(
            f"Niepoprawny dokument JSON {url}: {exc}", details={"url": url}
        ) from exc
    return data, {
        "source": source,
        "url": url,
        "file": None,
        "fetched_at": _utc(datetime.now(UTC)),
        "count": 0,
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_sha256": content,
        "content_form": form,
    }


def _chmi_meteo_now_url(base_url: str) -> str:
    """URL of the newest ``meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json``."""
    listing = base_url + _CHMI_METEO_NOW_DIR
    response = _http("GET", listing, headers=_IDENTIFY)
    names = sorted(
        entry.name
        for entry in parse_listing(response.content, url=listing)
        if _CHMI_METEO_NOW_FILE.fullmatch(entry.name)
    )
    if not names:
        raise IMGWDataError(
            f"Nieczytelny listing {listing}: brak pliku meta1-<RRRRMMDD>.json",
            details={"url": listing},
        )
    return listing + names[-1]


def _thresholds(source: _Metadata, code: str) -> dict[str, Any] | None:
    """
    SPA thresholds of a station's row (spec 2026-10-18 §7.4).

    ``drought`` = ``DRY*``, ``spa1``…``spa3`` = ``SPA1*``…``SPA3*`` and ``q50`` =
    ``SPA4*`` (stage or flow of the 50-year flow, not a fourth degree), numbers
    as published; None when the row has neither ``SPA_TYP`` nor a threshold.
    """
    levels: dict[str, dict[str, Any]] = {}
    present = False
    for variable in ("H", "Q"):
        values = {
            name: source.number(code, column)
            for name, column in (
                ("drought", f"DRY{variable}"),
                ("spa1", f"SPA1{variable}"),
                ("spa2", f"SPA2{variable}"),
                ("spa3", f"SPA3{variable}"),
                ("q50", f"SPA4{variable}"),
            )
        }
        present = present or any(value is not None for value in values.values())
        unit = source.text(code, f"SPA{variable}_UNIT")
        if unit is not None and unit not in _THRESHOLD_UNITS:
            raise source.table.cell_error(
                source.rows[code], f"SPA{variable}_UNIT", f"nieznana jednostka {unit!r}"
            )
        levels[variable] = {
            "unit": None if unit is None else _THRESHOLD_UNITS[unit],
            **values,
        }
    kind = source.text(code, "SPA_TYP")
    if kind is None and not present:
        return None
    return {"source": source.source, "type": kind, **levels}


def _established(source: _Metadata) -> dict[str, int]:
    """Year of the earliest ``BEGIN_DATE`` of each station of a period file."""
    table = source.table
    if not table.has("BEGIN_DATE"):
        return {}
    column = "objID" if source.kind == "hydro" else "WSI"
    first: dict[str, datetime] = {}
    for index in range(len(table.rows)):
        code = table.text(index, column)
        begin = table.timestamp(index, "BEGIN_DATE")
        if code is not None and code in source.rows and begin is not None:
            if code not in first or begin < first[code]:
                first[code] = begin
    return {code: moment.year for code, moment in first.items()}


def _chmi_feature(
    code: str,
    *,
    kind: Literal["hydro", "meteo"],
    sources: Sequence[_Metadata],
    user: Mapping[str, tuple[str, str, str | None]],
    established: Mapping[str, int],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None, bool]:
    """
    GeoJSON feature of a ČHMÚ station, its location source and a location conflict.

    ``sources`` are the metadata files of the family in precedence order (now,
    meta3, archived list): the first that gives a name, river, hydrographic
    code or thresholds wins, and the first valid point of the sources and of
    the user file locates the station. A conflict is another valid point
    farther away than the larger of both uncertainties.
    """
    candidates: list[_Candidate] = []
    owners: list[_Metadata | None] = []
    for source in sources:
        index = source.rows.get(code)
        if index is not None:
            lat, lon = station_coordinates(source.table, index, kind=kind)
            candidates.append((source.source, lon, lat))
            owners.append(source)
    if code in user:
        candidates.append(("user", user[code][0], user[code][1]))
        owners.append(None)
    located = _locate(
        code, candidates, border=CZECHIA_BORDER_RESOURCE, rejections=rejections
    )
    geometry, location_source, uncertainty, reason = _placement(located, candidates)
    conflict = False
    elevation: int | float | None = None
    if not isinstance(located, str):
        index, point, own = located
        for _, lon, lat in candidates[index + 1 :]:
            verdict = _evaluate(lon, lat, border=CZECHIA_BORDER_RESOURCE)
            if not isinstance(verdict, str) and _distance_m(point, verdict[0]) > max(
                own, verdict[1]
            ):
                conflict = True
        owner = owners[index]
        if kind == "meteo" and owner is not None:
            elevation = owner.number(code, "ELEVATION")

    def first(column: str) -> str | None:
        return next(
            (text for source in sources if (text := source.text(code, column))),
            None,
        )

    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": None,
        "name": first("STATION_NAME" if kind == "hydro" else "FULL_NAME") or "",
        "river": first("STREAM_NAME") if kind == "hydro" else None,
        "hydrographic_code": first("HLGP4") if kind == "hydro" else None,
        "river_order": None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        "active": code in sources[0].rows,
        "established_year": established.get(code) if kind == "meteo" else None,
        "gauge_zero_m": None,
        "river_km": None,
        "elevation_m": elevation,
    }
    if kind == "hydro":
        properties["thresholds"] = next(
            (
                found
                for source in sources
                if source.thresholds
                and (found := _thresholds(source, code)) is not None
            ),
            None,
        )
    feature = {
        "type": "Feature",
        "id": code,
        "geometry": geometry,
        "properties": properties,
    }
    return feature, location_source, conflict


def _chmi_catalog_bytes(
    *,
    families: Mapping[str, Sequence[_Metadata]],
    series: Mapping[str, set[str]],
    user: Mapping[str, tuple[str, str, str | None]],
    problems: list[str],
    rejections: list[str],
) -> tuple[bytes, int, int, dict[str, int], list[str], list[str]]:
    """
    Canonical ČHMÚ ``stations.geojson`` and its counts.

    Every code of the metadata files and of the current ČHMÚ series indexes is
    a station (closed and foreign ones too); codes only in the user file are
    problems.

    Returns
    -------
    tuple
        Bytes, station count, stations without location, stations per
        location source, codes known only from series and codes with a
        location conflict.
    """
    listed = {
        kind: {code for source in families[kind] for code in source.rows}
        for kind in ("hydro", "meteo")
    }
    codes = {kind: listed[kind] | series[kind] for kind in ("hydro", "meteo")}
    shared = sorted(codes["hydro"] & codes["meteo"])
    if shared:
        raise IMGWDataError(
            f"Kody stacji występują jednocześnie w rodzinie hydro i meteo: {', '.join(shared[:10])}"
        )
    known = codes["hydro"] | codes["meteo"]
    series_only = sorted(
        (series["hydro"] | series["meteo"]) - listed["hydro"] - listed["meteo"]
    )
    unknown = sorted(set(user) - known)
    if unknown:
        problems.append(
            f"Plik położeń użytkownika: {len(unknown)} kodów spoza metadanych ČHMÚ i "
            f"szeregów (np. {unknown[0]}); plik użytkownika uzupełnia tylko położenia"
        )
    established = _established(families["meteo"][-1])
    features = []
    used: dict[str, int] = {}
    without = 0
    conflicts: list[str] = []
    for code in sorted(known):
        kind: Literal["hydro", "meteo"] = "hydro" if code in codes["hydro"] else "meteo"
        feature, source, conflict = _chmi_feature(
            code,
            kind=kind,
            sources=families[kind],
            user=user,
            established=established,
            rejections=rejections,
        )
        if source is None:
            without += 1
        else:
            used[source] = used.get(source, 0) + 1
        if conflict:
            conflicts.append(code)
        features.append(feature)
    document = {"type": "FeatureCollection", "features": features}
    return _canonical(document), len(features), without, used, series_only, conflicts


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


def _skip(provider: str) -> Collection[str]:
    """Directories of other providers' catalogs inside a provider's catalog slot."""
    return _NESTED_CATALOGS.keys() if _CATALOG_DIRS[provider] == CATALOG_SLOT else ()


def _current_catalog(
    root: Path, provider: str = "IMGW-PIB"
) -> tuple[Path, dict[str, Any]] | None:
    slot = _validate_slot(root, _CATALOG_DIRS[provider])
    return _newest_downloaded(_existing(slot, CATALOG_FILE, skip=_skip(provider)))


def _catalog_meteo_kinds(path: Path, meta: Mapping[str, Any]) -> dict[str, object]:
    """``meteo_kind`` by station code of a stored catalog version, verified by SHA-256."""
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError("SHA-256 niezgodne z sidecarem")
        return {
            feature["id"]: feature["properties"]["meteo_kind"]
            for feature in json.loads(data)["features"]
        }
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise IMGWStoreConflictError(
            f"Uszkodzona wersja katalogu stacji {path}: {exc}"
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc


def _unverifiable_sources(provider: ProviderDescriptor) -> tuple[tuple[str, str], ...]:
    """Sources downloaded by every build, with the reason they have no signal."""
    if provider.id == "IMGW-PIB":
        reason = "publiczne API nie udostępnia stabilnego sygnału aktualności"
        return ((HYDRO_API_URL, reason), (METEO_API_URL, reason))
    base = provider.base_url
    return (
        (
            base + _CHMI_HYDRO_NOW,
            "koperta metadanych zmienia się co godzinę, także bez zmiany danych",
        ),
        (
            base + _CHMI_HYDRO_META3,
            "koperta metadanych zmienia się codziennie, także bez zmiany danych",
        ),
        (
            f"{base}{_CHMI_METEO_NOW_DIR}meta1-<RRRRMMDD>.json",
            "nowy plik metadanych codziennie; najnowszy wskazuje listing katalogu",
        ),
    )


def _catalog_license(provider: ProviderDescriptor) -> License:
    """
    License of a provider's catalog sidecar.

    The catalog is a processed form: under CC BY 4.0 (ČHMÚ) its attribution
    adds the provider's mark of changes (spec 2026-10-18 §7.5, §8). The
    IMGW-PIB catalog keeps the attribution of the source lists (3.0.0 bytes).
    """
    license_ = provider.license
    if provider.id == "IMGW-PIB":
        return license_
    return License(
        license_.id,
        f"{license_.attribution}. {provider.processed_attribution}",
        license_.url,
        license_.terms_url,
    )


def check_catalog(
    root: RootArg,
    /,
    *,
    provider: str = "IMGW-PIB",
    user_locations: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Compare the catalog sources of one provider with the store using HEAD and local hashes only.

    Station lists are checked with ``HEAD`` against the reference signal of
    their slot (the newest observation of the current version, otherwise its
    ``extra.http``); the sources downloaded by every build expose no stable
    signal and are reported as ``unverifiable`` without a request (IMGW-PIB:
    the public station APIs; ČHMÚ: the ``now`` metadata files, whose envelope
    is regenerated hourly or daily). Location files are compared by SHA-256
    with the entries recorded in the provider's current catalog sidecar; the
    station codes of the provider's current series indexes and the
    ``meteo_kind`` they give are compared with its current catalog. Nothing
    is downloaded or written.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    provider : str, optional
        Provider of the catalog (``ProviderDescriptor.id`` or key prefix),
        ``"IMGW-PIB"`` by default.
    user_locations : str, os.PathLike or None, optional
        User CSV ``station_code,latitude,longitude[,source]`` whose SHA-256 is
        compared with the one recorded in the catalog.
    on_progress : ProgressHook or None, optional
        Called after each station list and once at the end with the overall
        catalog status.
    on_notice : NoticeHook or None, optional
        Receives a ``source_unverifiable`` warning for each source without a
        signal.
    cancel : Cancel or None, optional
        Polled before each station list; once it returns ``True`` the remaining
        lists are reported as ``unverifiable`` with error ``"anulowano"``.

    Returns
    -------
    StorePlan
        Plan with one item per station list (``current``, ``newer``, ``missing``,
        ``unverifiable`` or ``check_failed``, also for a broken observation of
        the current version; ``local_observation`` names the observation giving
        the reference signal) and ``store catalog`` actions: one
        ``unverifiable`` per source without a signal, one per location file
        (``current``, or ``newer`` when the file appeared, disappeared or
        changed; ``missing`` without a catalog; the IMGW-PIB static file is
        always checked), one for the series indexes (``current``, ``newer``
        when a series station code is absent from the catalog or a station's
        ``meteo_kind`` differs, ``missing`` without a catalog) and a final
        catalog action that is ``missing`` without a catalog, ``newer`` when
        any source changed, otherwise ``unverifiable``.

    Raises
    ------
    IMGWValidationError
        If ``provider`` names no provider, or a location file exists but
        cannot be read.
    IMGWStoreError
        If ``root`` is not a supported IMGW store or a version path contains a
        symbolic link.
    IMGWStoreConflictError
        If a stored list or catalog version is corrupted.
    IMGWDataError
        If a station list responds with an invalid ``Content-Length`` header, or
        a current series index is corrupted; with code ``io_error``
        (``details.path``) if the system cannot read a stored version.
    """
    owner = get_provider(provider)
    handle = _handle(root)
    user = _user_file(user_locations)
    catalog = _current_catalog(handle.root, owner.id)
    recorded = {
        entry.get("source"): entry.get("sha256")
        for entry in (catalog[1]["extra"].get("catalog", []) if catalog else [])
        if isinstance(entry, dict)
    }
    items: list[PlanItem] = []
    actions: list[PlanAction] = []
    sources = station_source_files(provider=owner.id)
    headers = _headers(owner.id)
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
        local_path, local_sha = (
            (current[0], current[1]["sha256"]) if current else (None, None)
        )
        signal: Mapping[str, Any] = {}
        observation: Path | None = None
        try:
            if current is not None:
                signal, observation = _reference(handle.root, archive, current)
            response = _http("HEAD", archive.url, headers=headers)
        except (IMGWConnectionError, IMGWDataError) as exc:
            if isinstance(exc, IMGWDataError) and exc.code != "data_error":
                raise
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
                    local_observation=observation,
                )
            )
        else:
            etag = response.headers.get("ETag")
            modified = response.headers.get("Last-Modified")
            length = _content_length(response)
            status: Literal["current", "newer", "missing", "unverifiable"] = (
                "missing" if current is None else _list_status(signal, etag, modified)
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
                    local_observation=observation,
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
    for url, reason in _unverifiable_sources(owner):
        actions.append(
            PlanAction(
                "store catalog",
                "unverifiable",
                f"{url}: {reason}; sprawdzenie wymaga pobrania",
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
    local_files: list[tuple[str, bytes | None, Path]] = []
    if owner.id == "IMGW-PIB":
        static_path, static_bytes = _static_file()
        local_files.append(("static", static_bytes, static_path))
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
    series, _, meteo_kinds = _series_codes(handle.root, [], provider=owner)
    series_codes = series["hydro"] | series["meteo"]
    if catalog is None:
        series_status: Literal["current", "newer", "missing"] = "missing"
        series_detail = f"{len(series_codes)} kodów stacji"
    else:
        stored = _catalog_meteo_kinds(*catalog)
        absent = sorted(series_codes - stored.keys())
        changed = sorted(
            code for code, kind in stored.items() if kind != meteo_kinds.get(code)
        )
        series_status = "newer" if absent or changed else "current"
        if absent:
            series_detail = f"{len(absent)} kodów spoza katalogu (np. {absent[0]})"
        elif changed:
            series_detail = (
                f"{len(changed)} stacji z innym meteo_kind (np. {changed[0]})"
            )
        else:
            series_detail = f"{len(series_codes)} kodów stacji w katalogu"
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


def _catalog_notices(
    on_notice: NoticeHook | None,
    *,
    problems: Sequence[str],
    rejections: Sequence[str],
    used: Mapping[str, int],
    user_rows: Mapping[str, tuple[str, str, str | None]] | None,
    series_only: Sequence[str],
    without: int,
    conflicts: Sequence[str] = (),
) -> None:
    """Problems and location summaries of a built catalog, before its publication."""
    if on_notice is None:
        return
    for problem in problems:
        on_notice(Notice("warning", "catalog_problem", problem))
    for rejection in rejections:
        on_notice(Notice("warning", "location_rejected", rejection))
    for source, number in sorted(used.items()):
        on_notice(
            Notice("info", "location_source", f"Położenie z {source}: {number} stacji")
        )
    if user_rows is not None:
        labels = sorted({label for _, _, label in user_rows.values() if label})
        if labels:
            on_notice(
                Notice(
                    "info",
                    "location_source",
                    f"Źródła w pliku użytkownika: {', '.join(labels)}",
                )
            )
    if conflicts:
        on_notice(
            Notice(
                "info",
                "location_conflict",
                f"{len(conflicts)} stacji z poprawnymi położeniami źródeł różniącymi się "
                "bardziej niż ich niepewność (wybrano według pierwszeństwa źródeł): "
                f"{', '.join(conflicts)}",
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


@dataclass(frozen=True)
class _Build:
    """Common state of one catalog build: store, provider, user file and hooks."""

    handle: StoreHandle
    provider: ProviderDescriptor
    user: tuple[Path, bytes] | None
    total: int
    on_progress: ProgressHook | None
    on_notice: NoticeHook | None
    cancel: Cancel | None

    def progress(self, step: int, status: str, message: str) -> None:
        """
        Report a finished build step.

        Parameters
        ----------
        step : int
            Number of the step, ``1`` … ``total``.
        status : str
            Status of the step, e.g. ``"done"``.
        message : str
            Polish description of the step.
        """
        if self.on_progress is not None:
            self.on_progress(Progress(step, self.total, "step", status, message))

    def stopped(self) -> CatalogReport | None:
        """
        The ``cancelled`` report once ``cancel`` returns True.

        Returns
        -------
        CatalogReport or None
            Report without a version, or None to continue.
        """
        if _cancelled(self.cancel):
            return CatalogReport("cancelled", None, 0, 0, 0, (), self.provider.id)
        return None

    def publish(
        self,
        data: bytes,
        *,
        sources: list[dict[str, Any]],
        count: int,
        without: int,
        from_series: int,
        problems: list[str],
    ) -> CatalogReport:
        """
        Publish the catalog bytes as a new version unless the current one is equal.

        Parameters
        ----------
        data : bytes
            Canonical ``stations.geojson``.
        sources : list of dict
            ``extra.catalog`` entries of the sidecar.
        count, without, from_series : int
            Station counts of the report.
        problems : list of str
            Problems of the report.

        Returns
        -------
        CatalogReport
            ``created`` with the new version or ``unchanged`` with the
            current one.
        """
        provider = self.provider
        root = self.handle.root
        sha = hashlib.sha256(data).hexdigest()
        current = _current_catalog(root, provider.id)
        if current is not None and current[1]["sha256"] == sha:
            self.progress(self.total, "unchanged", "Katalog stacji bez zmian")
            return CatalogReport(
                "unchanged",
                current[0],
                count,
                without,
                from_series,
                tuple(problems),
                provider.id,
            )
        now = datetime.now(UTC)
        label = now.date().isoformat()
        license_ = _catalog_license(provider)
        meta = {
            "schema": "imgw-meta/1",
            "producer": "imgwtools",
            "producer_version": __version__,
            "dataset": _CATALOG_DATASETS[provider.id],
            "country": provider.country,
            "provider": provider.id,
            "request": {"user_locations": self.user[0].name if self.user else None},
            "license": _license_document(license_),
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
            root,
            slot=_CATALOG_DIRS[provider.id],
            name=CATALOG_FILE,
            data=data,
            meta=meta,
            label=label,
            on_notice=self.on_notice,
            skip=_skip(provider.id),
        )
        status: Literal["created", "unchanged"] = "created" if created else "unchanged"
        self.progress(self.total, status, f"Katalog stacji: {path.parent.name}")
        if created and self.on_notice is not None:
            self.on_notice(
                Notice(
                    "info",
                    LICENSE_NOTICE,
                    f"{license_.attribution}. {provider.notice}",
                )
            )
        return CatalogReport(
            status, path, count, without, from_series, tuple(problems), provider.id
        )


def build_catalog(
    root: RootArg,
    /,
    *,
    provider: str = "IMGW-PIB",
    user_locations: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> CatalogReport:
    """
    Build the ``stations.geojson`` catalog of one provider from its station sources.

    Station lists are re-validated with ``HEAD`` (as :func:`check_catalog`
    compares them): a list that is missing, has a different ETag/Last-Modified
    or no comparable signal is downloaded and stored with ``write_archive``
    first, so the catalog always reflects the current lists; the sources
    without a signal are always downloaded. Identical content (same SHA-256 of
    the canonical GeoJSON, whatever the envelopes of the sources) yields
    ``unchanged`` without a new version.

    IMGW-PIB (``stations/versions/<label>_<sha8>/``): every code of the lists,
    the public hydro and meteo APIs, the static file and the current series
    indexes is kept (a code only in the static file is a hydro station; a code
    only in a series index is a historical station of the series family with
    ``geometry`` null unless the user file locates it, counted in
    ``from_series``); codes only in the user file are reported in ``problems``.
    Location precedence: API, then the local static file
    ``station_code,latitude,longitude`` (``settings.data_dir``), then the user
    CSV. A missing static file is not an error: it is reported in ``problems``
    and recorded in the sidecar as ``available: false``. ``meteo_kind`` of a
    meteorological station is ``"climate"`` when the current
    ``pl.imgw.meteo_climate_daily`` series holds it, otherwise
    ``"precipitation"`` when the current ``pl.imgw.meteo_precip_daily`` series
    does, and null without such a series (also for every ČHMÚ station).

    ČHMÚ (``stations/versions/chmi_stations/<label>_<sha8>/``, spec
    2026-10-18 §7): sources in precedence order of location, name, river and
    thresholds — hydro ``hydrology/now/metadata/meta1.json``, ``meta3.json``
    (names, rivers, ``HLGP4`` and locations only) and the archived list
    ``cz.chmi.hydro_stations``; meteo the newest
    ``meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json`` (listing) and the
    archived list ``cz.chmi.meteo_stations`` (the period with the latest
    ``BEGIN_DATE``); then the user CSV. Every code of these files and of the
    current ČHMÚ series indexes is a station, also closed and foreign ones;
    points are validated against the outline of Czechia. ``active`` means
    present in the ``now`` file; hydro stations carry the SPA ``thresholds``.
    The sidecar records both sums of every metadata file and the license with
    the mark of changes.

    The user CSV ``station_code,latitude,longitude[,source]`` may hold codes of
    both providers: codes of the other provider are skipped, codes of no
    provider are problems. Every series index read is recorded in the sidecar
    as a ``series`` source.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    provider : str, optional
        Provider of the catalog (``ProviderDescriptor.id`` or key prefix),
        ``"IMGW-PIB"`` by default.
    user_locations : str, os.PathLike or None, optional
        User CSV ``station_code,latitude,longitude[,source]`` with fallback
        station locations.
    on_progress : ProgressHook or None, optional
        Called after each build step (station lists, sources, assembly,
        publication).
    on_notice : NoticeHook or None, optional
        Receives catalog problems, rejected locations, location source summaries,
        a ``location_conflict`` summary of stations whose sources disagree (ČHMÚ),
        a ``series_station`` summary of stations known only from series indexes,
        stations without location, ``source_unverifiable`` for a list without a
        comparable signal, writer notices of downloaded lists (including
        ``content_unchanged``), a ``leftover_incoming`` warning for every
        removed staging directory older than 24 hours and the provider's
        ``license_terms`` notice when a new version is created.
    cancel : Cancel or None, optional
        Polled between steps; once it returns ``True`` the build stops with a
        ``cancelled`` report and no catalog version is published.

    Returns
    -------
    CatalogReport
        Status ``created``, ``unchanged`` or ``cancelled``, the path of the
        current ``stations.geojson``, the station count, the number of stations
        without location, the number of stations known only from series indexes,
        the problems found in the sources and the provider.

    Raises
    ------
    IMGWValidationError
        If ``provider`` names no provider, or a location file exists but
        cannot be read or does not start with the
        ``station_code,latitude,longitude`` columns (the static file in the old
        ``id,X,Y`` format must be regenerated with
        ``python -m imgwtools.reference_data``); raised before any download.
    IMGWStoreError
        If ``root`` is not a supported IMGW store or collides with a Kartograf
        store or project.
    IMGWConnectionError
        If a station list cannot be checked or downloaded, or another source
        cannot be downloaded.
    IMGWDataError
        If a source is not valid (an API response that is not a JSON list of
        objects, a ČHMÚ metadata file or listing that cannot be read, an unknown
        threshold unit), a current series index or an observation of a stored
        list is unreadable, or a station code appears in both the hydro and
        meteo families.
    IMGWStoreConflictError
        If a stored version is corrupted or the new version cannot be published
        atomically.
    """
    owner = get_provider(provider)
    handle = _handle(root)
    _check_kartograf(handle.root)
    user = _user_file(user_locations)
    if owner.id == "IMGW-PIB":
        return _build_imgw(
            _Build(handle, owner, user, 6, on_progress, on_notice, cancel)
        )
    return _build_chmi(_Build(handle, owner, user, 7, on_progress, on_notice, cancel))


def _build_imgw(build: _Build) -> CatalogReport:
    """IMGW-PIB catalog from the station lists, public APIs and location files."""
    handle, owner, user = build.handle, build.provider, build.user
    # Location files are validated before any download, so a bad header writes nothing.
    static_path, static_bytes = _static_file()
    static, static_problems = (
        _read_locations(static_bytes, user=False, provider=owner)
        if static_bytes is not None
        else ({}, [])
    )
    user_rows, user_problems = (
        _read_locations(user[1], user=True, provider=owner)
        if user is not None
        else ({}, [])
    )
    sources: list[dict[str, Any]] = []
    lists: list[bytes] = []
    for step, archive in enumerate(station_source_files(provider=owner.id), start=1):
        if (report := build.stopped()) is not None:
            return report
        data, source = _station_list(
            handle, archive, on_progress=None, on_notice=build.on_notice
        )
        lists.append(data)
        sources.append(source)
        build.progress(step, "done", f"Lista stacji {archive.server_path}")
    apis = []
    for step, (url, source, key) in enumerate(
        (
            (HYDRO_API_URL, "api_hydro", "id_stacji"),
            (METEO_API_URL, "api_meteo", "kod_stacji"),
        ),
        start=3,
    ):
        if (report := build.stopped()) is not None:
            return report
        rows, record = _api(url, source, key)
        apis.append(rows)
        sources.append(record)
        build.progress(step, "done", f"Pobrano {url}")
    if (report := build.stopped()) is not None:
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
    series, series_sources, meteo_kinds = _series_codes(
        handle.root, problems, provider=owner
    )
    sources.extend(series_sources)
    data, count, without, used, series_only = _catalog_bytes(
        lists=parsed_lists,
        apis={"hydro": apis[0], "meteo": apis[1]},
        series=series,
        meteo_kinds=meteo_kinds,
        static=static,
        user=user_rows,
        problems=problems,
        rejections=rejections,
    )
    build.progress(5, "done", f"Zbudowano katalog {count} stacji")
    _catalog_notices(
        build.on_notice,
        problems=problems,
        rejections=rejections,
        used=used,
        user_rows=user_rows if user is not None else None,
        series_only=series_only,
        without=without,
    )
    if (report := build.stopped()) is not None:
        return report
    problems.extend(rejections)
    return build.publish(
        data,
        sources=sources,
        count=count,
        without=without,
        from_series=len(series_only),
        problems=problems,
    )


def _build_chmi(build: _Build) -> CatalogReport:
    """ČHMÚ catalog from the now and archived metadata files and the user file."""
    handle, owner, user = build.handle, build.provider, build.user
    # The user file is validated before any download, so a bad header writes nothing.
    user_rows, user_problems = (
        _read_locations(user[1], user=True, provider=owner)
        if user is not None
        else ({}, [])
    )
    hydro_list, meteo_list = station_source_files(provider=owner.id)
    form = get_dataset(hydro_list.dataset).content_form
    if form is None:  # pragma: no cover - registry invariant (spec §3.1)
        raise IMGWDataError(f"Zbiór {hydro_list.dataset} nie ma formy treści")
    stored: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for step, archive in enumerate((hydro_list, meteo_list), start=1):
        if (report := build.stopped()) is not None:
            return report
        stored[archive.dataset] = _station_list(
            handle, archive, on_progress=None, on_notice=build.on_notice
        )
        build.progress(step, "done", f"Lista stacji {archive.server_path}")
    fetched: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for step, (source, path) in enumerate(
        (
            ("chmi_hydro_now", _CHMI_HYDRO_NOW),
            ("chmi_hydro_meta3", _CHMI_HYDRO_META3),
            ("chmi_meteo_now", None),
        ),
        start=3,
    ):
        if (report := build.stopped()) is not None:
            return report
        url = (
            owner.base_url + path
            if path is not None
            else _chmi_meteo_now_url(owner.base_url)
        )
        fetched[source] = _chmi_get(url, source=source, form=form)
        build.progress(step, "done", f"Pobrano {url}")
    if (report := build.stopped()) is not None:
        return report
    problems: list[str] = []
    rejections: list[str] = []
    records: list[dict[str, Any]] = []

    def parse(
        data: bytes,
        record: dict[str, Any],
        *,
        kind: Literal["hydro", "meteo"],
        thresholds: bool = True,
    ) -> _Metadata:
        metadata = _metadata(
            data,
            source=record["source"],
            kind=kind,
            filename=record["url"] if record["file"] is None else record["file"],
            problems=problems,
            thresholds=thresholds,
        )
        record["count"] = len(metadata.rows)
        records.append(record)
        return metadata

    families = {
        "hydro": (
            parse(*fetched["chmi_hydro_now"], kind="hydro"),
            parse(*fetched["chmi_hydro_meta3"], kind="hydro", thresholds=False),
            parse(*stored[hydro_list.dataset], kind="hydro"),
        ),
        "meteo": (
            parse(*fetched["chmi_meteo_now"], kind="meteo"),
            parse(*stored[meteo_list.dataset], kind="meteo"),
        ),
    }
    if user is not None:
        problems.extend(user_problems)
        records.append(
            _local_source(
                user[1], source="user", file=user[0].name, count=len(user_rows)
            )
            | {"available": True}
        )
    # ČHMÚ publishes no station class: meteo_kind stays null (spec 2026-10-18 §7.3).
    series, series_sources, _ = _series_codes(handle.root, problems, provider=owner)
    records.extend(series_sources)
    data, count, without, used, series_only, conflicts = _chmi_catalog_bytes(
        families=families,
        series=series,
        user=user_rows,
        problems=problems,
        rejections=rejections,
    )
    build.progress(6, "done", f"Zbudowano katalog {count} stacji")
    _catalog_notices(
        build.on_notice,
        problems=problems,
        rejections=rejections,
        used=used,
        user_rows=user_rows if user is not None else None,
        series_only=series_only,
        without=without,
        conflicts=conflicts,
    )
    if (report := build.stopped()) is not None:
        return report
    problems.extend(rejections)
    return build.publish(
        data,
        sources=records,
        count=count,
        without=without,
        from_series=len(series_only),
        problems=problems,
    )
