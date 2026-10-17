"""Offline, read-only access to the versioned IMGW store (no network, writes, or locks)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable, Iterator, Mapping
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from imgwtools.datasets import License, datasets, get_dataset
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store.catalog import (
    CATALOG_FILE,
    CATALOG_SLOT,
    RootArg,
    _newest_downloaded,
    _signal_time,
    _timestamp,
)
from imgwtools.store.pmaxtp import CELL_FILE, CELL_SCHEMA
from imgwtools.store.series import _FLAGS, SERIES_SCHEMA, _pyarrow
from imgwtools.store.types import (
    Meta,
    PathArg,
    SeriesIndex,
    StationCoverage,
    StationFeature,
    StationSeriesIndex,
    StoreEntry,
    StoreHandle,
    StoreInfo,
)
from imgwtools.store.writer import _MARKER, _safe_root, _validate_slot

STORE_SCHEMA = "imgw-store/1"
META_SCHEMA = "imgw-meta/1"
SERIES_FILE = "series.json"
CONTRACTS: Mapping[str, str] = {
    "store": STORE_SCHEMA,
    "meta": META_SCHEMA,
    "series": SERIES_SCHEMA,
    "plan": "imgw-plan/1",
    "project": "imgw-project/1",
    "pmaxtp": CELL_SCHEMA,
}

EntryKind = Literal["archive", "series", "catalog", "pmaxtp", "problem"]
_KINDS: tuple[EntryKind, ...] = ("archive", "series", "catalog", "pmaxtp", "problem")
_STALE_SECONDS = 24 * 60 * 60
_SIDECAR = ".meta.json"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[0-9]{9}$")
_VERSION_DIR = re.compile(r"^.+_[0-9a-f]{8}$")
_CELL = re.compile(r"^[0-9]+_[0-9]+$")
_PARQUET = re.compile(r"^stations/[0-9]{9}\.parquet$")
_LABEL_SOURCES = ("last_modified", "downloaded", "inputs")
_PERIODS = ("winter", "summer", "annual")
_SCALARS = (str, int, float, bool, type(None))


class _Invalid(Exception):
    """A store object that cannot be read as a version; ``code`` is the problem code."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code


# --------------------------------------------------------------------------
# Store marker
# --------------------------------------------------------------------------


def _inspect(path: Path) -> tuple[StoreInfo, str | None]:
    """Store state and the problem code of an unusable store (``None`` when supported)."""
    contracts = dict(CONTRACTS)

    def unusable(
        code: str, text: str, *, schema: str | None = None
    ) -> tuple[StoreInfo, str]:
        return StoreInfo(path, path.exists(), schema, False, contracts, (text,)), code

    if not path.exists():
        return unusable("missing_store", f"Katalog magazynu nie istnieje: {path}")
    marker = path / _MARKER
    if marker.is_symlink() or not marker.is_file():
        return unusable(
            "missing_marker",
            f"Brak znacznika {_MARKER}: {path} nie jest magazynem IMGW",
        )
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return unusable("invalid_marker", f"Nieczytelny znacznik {marker}: {exc}")
    schema = payload.get("schema") if isinstance(payload, dict) else None
    if not isinstance(schema, str):
        return unusable("invalid_marker", f"Znacznik {marker} nie ma pola schema")
    if schema != STORE_SCHEMA:
        return unusable(
            "unsupported_store",
            f"Nieobsługiwana wersja magazynu {schema}; ta wersja imgwtools obsługuje {STORE_SCHEMA}",
            schema=schema,
        )
    created_by = payload.get("created_by")
    if not isinstance(created_by, str) or not created_by:
        return unusable(
            "invalid_marker",
            f"Znacznik {marker} nie ma poprawnego pola created_by",
            schema=schema,
        )
    return StoreInfo(path, True, schema, True, contracts, ()), None


def store_info(root: PathArg, /) -> StoreInfo:
    """
    Describe a store root without raising for an unknown or missing marker.

    An unknown store schema (e.g. ``imgw-store/2``), a missing or unreadable
    marker and a marker without ``created_by`` all yield ``supported=False``
    with the reason in ``problems`` instead of an exception.

    Parameters
    ----------
    root : str or os.PathLike
        Store root directory; made absolute before inspection.

    Returns
    -------
    StoreInfo
        Existence of the root, marker schema, support flag, the contract
        versions supported by this library and the detected problems.

    Raises
    ------
    IMGWValidationError
        If the root path contains ``..``.
    IMGWStoreError
        If a component of the root path is a symbolic link.
    """
    return _inspect(_safe_root(root))[0]


def _open(root: RootArg) -> Path:
    info, _ = _inspect(_safe_root(root.root if isinstance(root, StoreHandle) else root))
    if not info.supported:
        raise IMGWStoreError("; ".join(info.problems))
    return info.root


# --------------------------------------------------------------------------
# Sidecars
# --------------------------------------------------------------------------


def _text(payload: Mapping[str, Any], key: str, *, const: str | None = None) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise _Invalid("invalid_meta", f"pole {key} musi być niepustym tekstem")
    if const is not None and value != const:
        raise _Invalid("invalid_meta", f"pole {key} musi mieć wartość {const}")
    return value


def _object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise _Invalid("invalid_meta", f"pole {key} musi być obiektem")
    return value


def _parse_meta(payload: object) -> Meta:
    """Validate the required ``imgw-meta/1`` fields; additional fields are tolerated."""
    if not isinstance(payload, dict):
        raise _Invalid("invalid_meta", "sidecar nie jest obiektem JSON")
    schema = payload.get("schema")
    if not isinstance(schema, str):
        raise _Invalid("invalid_meta", "brak pola schema")
    if schema != META_SCHEMA:
        raise _Invalid("unknown_schema", f"nieobsługiwany schemat sidecara {schema}")
    _text(payload, "producer", const="imgwtools")
    _text(payload, "producer_version")
    dataset = _text(payload, "dataset")
    _text(payload, "country", const="PL")
    _text(payload, "provider", const="IMGW-PIB")
    request = _object(payload, "request")
    license_ = _object(payload, "license")
    extra = _object(payload, "extra")
    _text(license_, "id", const="IMGW-PIB")
    attribution = _text(license_, "attribution")
    url = _text(license_, "url")
    sha = payload.get("sha256")
    if not isinstance(sha, str) or not _SHA.match(sha):
        raise _Invalid(
            "invalid_meta", "pole sha256 musi mieć 64 małe cyfry szesnastkowe"
        )
    size = payload.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise _Invalid(
            "invalid_meta", "pole size_bytes musi być nieujemną liczbą całkowitą"
        )
    try:
        downloaded_at = _timestamp(_text(payload, "downloaded_at"))
    except ValueError as exc:
        raise _Invalid("invalid_meta", "pole downloaded_at nie jest datą ISO") from exc
    if downloaded_at.tzinfo is None:
        raise _Invalid("invalid_meta", "pole downloaded_at musi mieć strefę czasową")
    version = _object(extra, "version")
    _text(version, "label")
    if version.get("label_source") not in _LABEL_SOURCES:
        raise _Invalid(
            "invalid_meta",
            f"pole label_source musi być jednym z {', '.join(_LABEL_SOURCES)}",
        )
    return Meta(
        schema,
        dataset,
        sha,
        size,
        downloaded_at,
        License("IMGW-PIB", attribution, url),
        request,
        extra,
    )


def _load_meta(sidecar: Path) -> Meta:
    if sidecar.is_symlink():
        raise _Invalid(
            "symlink", f"dowiązanie symboliczne zamiast sidecara {sidecar.name}"
        )
    try:
        text = sidecar.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _Invalid("missing_sidecar", f"brak sidecara {sidecar.name}") from exc
    except OSError as exc:
        raise _Invalid(
            "unreadable", f"nieczytelny sidecar {sidecar.name}: {exc}"
        ) from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise _Invalid(
            "invalid_json", f"uszkodzony JSON sidecara {sidecar.name}: {exc}"
        ) from exc
    return _parse_meta(payload)


def read_meta(path: PathArg, /) -> Meta:
    """
    Read the sidecar of a data file (or the ``*.meta.json`` itself).

    Required ``imgw-meta/1`` fields are validated; additional fields are
    tolerated.

    Parameters
    ----------
    path : str or os.PathLike
        Main data file of a version or its ``<file>.meta.json`` sidecar.

    Returns
    -------
    Meta
        Parsed sidecar metadata.

    Raises
    ------
    IMGWStoreError
        If the sidecar does not exist.
    IMGWDataError
        If the sidecar is a symbolic link, unreadable, not valid JSON or does
        not satisfy ``imgw-meta/1``.
    """
    given = Path(path)
    sidecar = (
        given
        if given.name.endswith(_SIDECAR)
        else given.with_name(given.name + _SIDECAR)
    )
    try:
        return _load_meta(sidecar)
    except _Invalid as exc:
        if exc.code == "missing_sidecar":
            raise IMGWStoreError(f"Brak sidecara {sidecar}") from exc
        raise IMGWDataError(f"Nieprawidłowy sidecar {sidecar}: {exc}") from exc


# --------------------------------------------------------------------------
# Versions and scan
# --------------------------------------------------------------------------


def _check_version(
    directory: Path, name: str, *, subdirs: tuple[str, ...] = ()
) -> tuple[Path, Meta]:
    """Validate one published version directory; ``name`` is the expected main file."""
    if directory.is_symlink():
        raise _Invalid("symlink", "dowiązanie symboliczne zamiast katalogu wersji")
    files: set[str] = set()
    for child in directory.iterdir():
        if child.is_symlink():
            raise _Invalid("symlink", f"dowiązanie symboliczne w wersji: {child.name}")
        if child.is_dir():
            if child.name not in subdirs:
                raise _Invalid(
                    "unknown_entry", f"nieznany katalog w wersji: {child.name}"
                )
        else:
            files.add(child.name)
    if name not in files and name + _SIDECAR in files:
        raise _Invalid("missing_file", f"brak pliku głównego {name}")
    unexpected = sorted(files - {name, name + _SIDECAR})
    if unexpected:
        raise _Invalid(
            "unknown_entry", f"nieznane pliki w wersji: {', '.join(unexpected)}"
        )
    if name not in files:
        raise _Invalid("missing_file", f"brak pliku głównego {name}")
    main = directory / name
    meta = _load_meta(directory / (name + _SIDECAR))
    label = cast("Mapping[str, Any]", meta.extra["version"])["label"]
    if directory.name != f"{label}_{meta.sha256[:8]}":
        raise _Invalid(
            "invalid_meta",
            f"nazwa katalogu wersji nie odpowiada etykiecie {label} i sumie sidecara",
        )
    if main.stat().st_size != meta.size_bytes:
        raise _Invalid(
            "size_mismatch", f"rozmiar {name} różni się od size_bytes w sidecarze"
        )
    return main, meta


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _problem(slot: str, path: Path, code: str, text: str) -> StoreEntry:
    return StoreEntry("problem", slot, path, None, code, text)


def _unknown(root: Path, path: Path) -> StoreEntry:
    return _problem(
        _relative(root, path),
        path,
        "unknown_entry",
        f"Nieznany element magazynu: {_relative(root, path)}",
    )


def _entry(
    root: Path, kind: EntryKind, slot: str, directory: Path, name: str, **options: Any
) -> StoreEntry:
    try:
        main, meta = _check_version(directory, name, **options)
        server_path = slot.removeprefix("archive:")
        if (
            kind == "archive"
            and meta.request.get("server_path", server_path) != server_path
        ):
            raise _Invalid(
                "invalid_meta",
                "request.server_path w sidecarze nie odpowiada ścieżce wersji",
            )
    except _Invalid as exc:
        return _problem(
            slot, directory, exc.code, f"Wersja {_relative(root, directory)}: {exc}"
        )
    except OSError as exc:
        return _problem(
            slot, directory, "unreadable", f"Wersja {_relative(root, directory)}: {exc}"
        )
    return StoreEntry(kind, slot, main, meta, None, None)


def _archive_slot(base: Path, directory: Path) -> str:
    """``archive:<server_path>`` of a version directory, named after its (possibly orphaned) main file."""
    names = sorted(
        item.name.removesuffix(_SIDECAR)
        for item in directory.iterdir()
        if not item.is_dir()
    )
    slot_dir = directory.parent
    name = next(
        (item for item in names if PurePosixPath(item).stem == slot_dir.name),
        slot_dir.name,
    )
    return f"archive:{slot_dir.parent.relative_to(base).as_posix()}/{name}"


def _directories(root: Path, path: Path) -> Iterator[Path | StoreEntry]:
    """Children of a structural directory; files and links there are problems."""
    for child in sorted(path.iterdir()):
        if child.is_symlink():
            yield _problem(
                _relative(root, child),
                child,
                "symlink",
                f"Dowiązanie symboliczne w magazynie: {_relative(root, child)}",
            )
        elif not child.is_dir():
            yield _unknown(root, child)
        else:
            yield child


def _versions_dir(root: Path, top: Path) -> Iterator[Path | StoreEntry]:
    """``<top>/versions`` is the only allowed child of a kind directory."""
    for child in _directories(root, top):
        if isinstance(child, StoreEntry):
            yield child
        elif child.name != "versions":
            yield _unknown(root, child)
        else:
            yield child


def _scan_archives(root: Path, base: Path, directory: Path) -> Iterator[StoreEntry]:
    for child in _directories(root, directory):
        if isinstance(child, StoreEntry):
            yield child
            continue
        has_files = any(
            not item.is_dir() or item.is_symlink() for item in child.iterdir()
        )
        if has_files or _VERSION_DIR.match(child.name):
            if len(child.relative_to(base).parts) < 3:
                yield _unknown(root, child)
            else:
                slot = _archive_slot(base, child)
                yield _entry(root, "archive", slot, child, PurePosixPath(slot).name)
        else:
            yield from _scan_archives(root, base, child)


def _series_slugs() -> set[str]:
    return {
        item.slug
        for item in datasets()
        if item.time_unit in ("day", "month", "half_year")
    }


def _scan_kind(root: Path, top: Path) -> Iterator[StoreEntry]:
    for versions in _versions_dir(root, top):
        if isinstance(versions, StoreEntry):
            yield versions
        elif top.name == "archives":
            yield from _scan_archives(root, versions, versions)
        elif top.name == "stations":
            for version in _directories(root, versions):
                yield (
                    version
                    if isinstance(version, StoreEntry)
                    else _entry(
                        root, "catalog", "catalog:stations", version, CATALOG_FILE
                    )
                )
        elif top.name == "series":
            for slug in _directories(root, versions):
                if isinstance(slug, StoreEntry) or slug.name not in _series_slugs():
                    yield slug if isinstance(slug, StoreEntry) else _unknown(root, slug)
                    continue
                for version in _directories(root, slug):
                    yield (
                        version
                        if isinstance(version, StoreEntry)
                        else _entry(
                            root,
                            "series",
                            f"series:{slug.name}",
                            version,
                            SERIES_FILE,
                            subdirs=("stations",),
                        )
                    )
        else:
            for method in _directories(root, versions):
                if isinstance(method, StoreEntry) or method.name not in ("POT", "AMP"):
                    yield (
                        method
                        if isinstance(method, StoreEntry)
                        else _unknown(root, method)
                    )
                    continue
                for cell in _directories(root, method):
                    if isinstance(cell, StoreEntry) or not _CELL.match(cell.name):
                        yield (
                            cell
                            if isinstance(cell, StoreEntry)
                            else _unknown(root, cell)
                        )
                        continue
                    for version in _directories(root, cell):
                        yield (
                            version
                            if isinstance(version, StoreEntry)
                            else _entry(
                                root,
                                "pmaxtp",
                                f"pmaxtp:{method.name}:{cell.name}",
                                version,
                                CELL_FILE,
                            )
                        )


def _scan(root: Path) -> Iterator[StoreEntry]:
    info, code = _inspect(root)
    if code is not None:
        for text in info.problems:
            yield _problem("store", root / _MARKER, code, text)
        return
    cutoff = time.time() - _STALE_SECONDS
    for child in sorted(root.iterdir()):
        if child.name == _MARKER:
            continue
        if child.is_symlink():
            yield _problem(
                child.name,
                child,
                "symlink",
                f"Dowiązanie symboliczne w magazynie: {child.name}",
            )
        elif child.name == ".incoming" and child.is_dir():
            # Young staging directories are private to a running writer, never versions.
            for staging in sorted(child.iterdir()):
                if staging.lstat().st_mtime < cutoff:
                    relative = _relative(root, staging)
                    yield _problem(
                        relative,
                        staging,
                        "stale_incoming",
                        f"Porzucony staging starszy niż 24 h: {relative}",
                    )
        elif (
            child.name in ("archives", "stations", "series", "pmaxtp")
            and child.is_dir()
        ):
            yield from _scan_kind(root, child)
        else:
            yield _unknown(root, child)


def iter_store(root: RootArg, /, *, kind: str | None = None) -> Iterator[StoreEntry]:
    """
    Scan every published version and every problem offline, without writing anything.

    Unknown directories, missing sidecars, corrupted JSON, unknown schemas,
    size mismatches and ``.incoming`` stagings older than 24 hours are
    reported as separate ``StoreEntry(kind="problem")`` entries; younger
    stagings are private and are not versions. Files are not hashed during
    the scan (only their size is compared with ``size_bytes``).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    kind : {"archive", "series", "catalog", "pmaxtp", "problem"} or None, optional
        Return only entries of this kind; ``None`` returns all entries.

    Returns
    -------
    Iterator[StoreEntry]
        Lazily scanned published versions and problems.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is not a known entry kind or the root path contains ``..``.
    IMGWStoreError
        If a component of the root path is a symbolic link.
    """
    if kind is not None and kind not in _KINDS:
        raise IMGWValidationError(
            f"Nieznany rodzaj wpisu magazynu: {kind!r}; dozwolone {', '.join(_KINDS)}"
        )
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    return (entry for entry in _scan(path) if kind is None or entry.kind == kind)


def _slot_location(
    root: Path, slot: str
) -> tuple[EntryKind, Path, str, tuple[str, ...]]:
    kind, _, rest = slot.partition(":")
    if kind == "archive" and rest:
        relative = PurePosixPath(rest)
        directory = _validate_slot(
            root, f"archives/versions/{relative.parent.as_posix()}/{relative.stem}"
        )
        if relative.parent == PurePosixPath("."):
            raise IMGWValidationError(f"Niepełna ścieżka archiwum w slocie: {slot}")
        return "archive", directory, relative.name, ()
    if kind == "series" and rest in _series_slugs():
        return (
            "series",
            _validate_slot(root, f"series/versions/{rest}"),
            SERIES_FILE,
            ("stations",),
        )
    if slot == "catalog:stations":
        return "catalog", _validate_slot(root, CATALOG_SLOT), CATALOG_FILE, ()
    method, _, cell = rest.partition(":")
    if kind == "pmaxtp" and method in ("POT", "AMP") and _CELL.match(cell):
        return (
            "pmaxtp",
            _validate_slot(root, f"pmaxtp/versions/{method}/{cell}"),
            CELL_FILE,
            (),
        )
    raise IMGWValidationError(
        f"Nieprawidłowy slot {slot!r}; oczekiwano archive:<server_path>, series:<slug>, "
        "catalog:stations lub pmaxtp:<POT|AMP>:<indX>_<indY>"
    )


def current_version(root: RootArg, /, *, slot: str) -> StoreEntry | None:
    """
    Current published version of a slot; a broken version in the slot is an error.

    Archive versions are ordered by ``Last-Modified``, then ``downloaded_at``,
    then path; derived versions (series, catalog, PMAXTP) by
    ``downloaded_at``, then path. Staging directories are never returned.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    slot : str
        Slot identifier: ``archive:<server_path>``, ``series:<slug>``,
        ``catalog:stations`` or ``pmaxtp:<POT|AMP>:<indX>_<indY>``.

    Returns
    -------
    StoreEntry or None
        Entry of the current version, or ``None`` if the slot has no
        versions.

    Raises
    ------
    IMGWStoreError
        If the root is not a supported store or a slot path component is a
        symbolic link.
    IMGWValidationError
        If ``slot`` is malformed or the root path contains ``..``.
    IMGWDataError
        If any version in the slot is broken (an older version is never
        silently selected instead).
    """
    path = _open(root)
    kind, directory, name, subdirs = _slot_location(path, slot)
    if not directory.is_dir():
        return None
    versions: list[tuple[Path, dict[str, Any]]] = []
    entries: dict[Path, StoreEntry] = {}
    for version in sorted(directory.iterdir()):
        entry = (
            _entry(path, kind, slot, version, name, subdirs=subdirs)
            if version.is_dir()
            else _unknown(path, version)
        )
        if entry.kind == "problem" or entry.meta is None or entry.version is None:
            raise IMGWDataError(f"Uszkodzona wersja w slocie {slot}: {entry.problem}")
        meta = entry.meta
        versions.append(
            (
                entry.version,
                {"downloaded_at": meta.downloaded_at.isoformat(), "extra": meta.extra},
            )
        )
        entries[entry.version] = entry
    if kind == "archive":
        current = max(
            versions,
            key=lambda item: (
                _signal_time(item[1]),
                _timestamp(item[1]["downloaded_at"]),
                item[0].as_posix(),
            ),
            default=None,
        )
    else:
        current = _newest_downloaded(versions)
    return entries[current[0]] if current is not None else None


# --------------------------------------------------------------------------
# Catalog and series
# --------------------------------------------------------------------------


def _main_file(version: PathArg, name: str) -> Path:
    path = Path(version).expanduser()
    if path.is_dir():
        path = path / name
    if path.name != name:
        raise IMGWValidationError(
            f"Wersja musi wskazywać katalog wersji albo plik {name}: {version}"
        )
    return path


def _verified(path: Path) -> bytes:
    """Bytes of a version's main file, verified against its sidecar."""
    if path.is_symlink():
        raise IMGWDataError(f"Dowiązanie symboliczne zamiast pliku wersji: {path}")
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise IMGWStoreError(f"Brak pliku wersji: {path}") from exc
    except OSError as exc:
        raise IMGWDataError(f"Nie można odczytać {path}: {exc}") from exc
    meta = read_meta(path)
    if hashlib.sha256(data).hexdigest() != meta.sha256 or len(data) != meta.size_bytes:
        raise IMGWDataError(
            f"Suma kontrolna {path.name} nie zgadza się z sidecarem: {path}"
        )
    return data


def _json(path: Path) -> Any:
    try:
        return json.loads(_verified(path))
    except ValueError as exc:
        raise IMGWDataError(f"Uszkodzony JSON {path}: {exc}") from exc


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("współrzędna nie jest liczbą")
    return float(value)


def read_catalog(version: PathArg, /) -> tuple[StationFeature, ...]:
    """
    Every station of a catalog version, including stations without geometry.

    The ``stations.geojson`` bytes are verified against the SHA-256 and size
    recorded in the sidecar.

    Parameters
    ----------
    version : str or os.PathLike
        Catalog version directory or its ``stations.geojson`` file.

    Returns
    -------
    tuple of StationFeature
        Stations in file order; ``geometry`` is ``None`` for stations without
        a location.

    Raises
    ------
    IMGWValidationError
        If ``version`` points to neither a version directory nor
        ``stations.geojson``.
    IMGWStoreError
        If the catalog file or its sidecar does not exist.
    IMGWDataError
        If the file is unreadable, a symbolic link, does not match its
        sidecar, or is not a valid station FeatureCollection.
    """
    path = _main_file(version, CATALOG_FILE)
    document = _json(path)
    result: list[StationFeature] = []
    try:
        if (
            not isinstance(document, dict)
            or document.get("type") != "FeatureCollection"
        ):
            raise ValueError("oczekiwano FeatureCollection")
        features = document["features"]
        if not isinstance(features, list):
            raise ValueError("features musi być listą")
        for feature in features:
            code = feature["id"]
            if (
                feature["type"] != "Feature"
                or not isinstance(code, str)
                or not _CODE.match(code)
            ):
                raise ValueError(f"nieprawidłowy obiekt stacji {code!r}")
            properties = feature["properties"]
            if not isinstance(properties, dict) or not all(
                isinstance(value, _SCALARS) for value in properties.values()
            ):
                raise ValueError(
                    f"właściwości stacji {code} muszą być wartościami prostymi"
                )
            if properties.get("station_code", code) != code:
                raise ValueError(f"station_code stacji {code} różni się od id")
            geometry = feature["geometry"]
            point: tuple[float, float] | None = None
            if geometry is not None:
                coordinates = geometry["coordinates"]
                if (
                    geometry["type"] != "Point"
                    or not isinstance(coordinates, list)
                    or len(coordinates) != 2
                ):
                    raise ValueError(
                        f"geometria stacji {code} musi być punktem [lon, lat]"
                    )
                point = (_number(coordinates[0]), _number(coordinates[1]))
            result.append(StationFeature(code, point, properties))
    except (KeyError, TypeError, ValueError) as exc:
        raise IMGWDataError(f"Nieprawidłowy katalog stacji {path}: {exc}") from exc
    return tuple(result)


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError(f"data musi być tekstem ISO: {value!r}")
    return date.fromisoformat(value)


def _span(value: object) -> tuple[date, date]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("przedział musi być parą dat")
    start, end = _date(value[0]), _date(value[1])
    if start > end:
        raise ValueError(f"przedział {start}–{end} ma odwróconą kolejność")
    return start, end


def _count(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} musi być liczbą całkowitą ≥ {minimum}")
    return value


def _coverage(code: str, key: str, value: Any) -> StationCoverage:
    variable, _, period = key.partition("@")
    if period and period not in _PERIODS:
        raise ValueError(f"nieznany okres zmiennej {key}")
    unit = value["unit"]
    if not isinstance(unit, str):
        raise ValueError(f"jednostka zmiennej {key} musi być tekstem")
    first = None if value["first"] is None else _date(value["first"])
    last = None if value["last"] is None else _date(value["last"])
    gaps = value["gaps"]
    if not isinstance(gaps, list):
        raise ValueError(f"gaps zmiennej {key} musi być listą")
    return StationCoverage(
        code,
        variable,
        unit,
        cast("Literal['winter', 'summer', 'annual'] | None", period or None),
        first,
        last,
        _count(value["with_value"], "with_value"),
        _count(value["accumulated"], "accumulated"),
        tuple(_span(gap) for gap in gaps),
    )


def read_series_index(version: PathArg, /) -> SeriesIndex:
    """
    Validate ``series.json`` and its Parquet paths without pyarrow or reading Parquet bytes.

    The ``series.json`` bytes are verified against the sidecar; each station
    Parquet file must exist as a regular file, but its contents are not read.

    Parameters
    ----------
    version : str or os.PathLike
        Series version directory or its ``series.json`` file.

    Returns
    -------
    SeriesIndex
        Dataset, year type, periods and per-station Parquet index.

    Raises
    ------
    IMGWValidationError
        If ``version`` points to neither a version directory nor
        ``series.json``.
    IMGWStoreError
        If ``series.json`` or its sidecar does not exist.
    IMGWDataError
        If the file is unreadable, a symbolic link, does not match its
        sidecar, or is not a valid ``imgw-series/1`` index (including missing
        Parquet files).
    """
    path = _main_file(version, SERIES_FILE)
    document = _json(path)
    try:
        if not isinstance(document, dict):
            raise ValueError("series.json nie jest obiektem")
        if document.get("schema") != SERIES_SCHEMA:
            raise ValueError(f"nieobsługiwany schemat {document.get('schema')!r}")
        dataset = document["dataset"]
        descriptor = get_dataset(dataset) if isinstance(dataset, str) else None
        if descriptor is None or descriptor.slug not in _series_slugs():
            raise ValueError(f"zbiór {dataset!r} nie tworzy szeregów")
        year_type = document["year_type"]
        if year_type not in ("hydrological", "calendar"):
            raise ValueError(f"nieznany year_type {year_type!r}")
        periods = tuple(_span(item) for item in document["periods"])
        raw_stations = document["stations"]
        if not isinstance(raw_stations, dict):
            raise ValueError("stations musi być obiektem")
        stations: dict[str, StationSeriesIndex] = {}
        for code, entry in raw_stations.items():
            if not _CODE.match(code):
                raise ValueError(f"nieprawidłowy kod stacji {code!r}")
            file, sha = entry["file"], entry["sha256"]
            if not isinstance(file, str) or not _PARQUET.match(file):
                raise ValueError(
                    f"nieprawidłowa ścieżka Parquet stacji {code}: {file!r}"
                )
            if not isinstance(sha, str) or not _SHA.match(sha):
                raise ValueError(f"nieprawidłowa suma Parquet stacji {code}")
            parquet = path.parent / file
            if parquet.is_symlink() or not parquet.is_file():
                raise ValueError(f"brak pliku {file}")
            variables = entry["variables"]
            if not isinstance(variables, dict):
                raise ValueError(f"variables stacji {code} musi być obiektem")
            stations[code] = StationSeriesIndex(
                Path(file),
                sha,
                _count(entry["rows"], "rows", minimum=1),
                {key: _coverage(code, key, value) for key, value in variables.items()},
            )
    except (IMGWValidationError, KeyError, TypeError, ValueError) as exc:
        raise IMGWDataError(f"Nieprawidłowy spis szeregu {path}: {exc}") from exc
    return SeriesIndex(SERIES_SCHEMA, dataset, year_type, periods, stations)


def read_series(
    version: PathArg,
    /,
    *,
    station: str,
    variables: Iterable[str],
    start: date | None = None,
    end: date | None = None,
) -> Iterator[NormalizedRecord]:
    """
    Values and flags of one station between ``start`` and ``end`` (inclusive, period start date).

    Arguments, the series index and the SHA-256 of the station Parquet file
    are validated before the iterator is returned. For monthly and
    half-year series the range filter applies to the period start
    (``date``). Days or months filled in by the builder are returned with
    the ``missing`` flag.

    Parameters
    ----------
    version : str or os.PathLike
        Series version directory or its ``series.json`` file.
    station : str
        Nine-digit station code present in the series.
    variables : Iterable[str]
        Non-empty collection of dataset variable names; duplicates are
        merged, a single string is rejected.
    start : datetime.date or None, optional
        First period start date to include; ``None`` means no lower bound.
    end : datetime.date or None, optional
        Last period start date to include; ``None`` means no upper bound.

    Returns
    -------
    Iterator[NormalizedRecord]
        Records of the station in Parquet row order.

    Raises
    ------
    IMGWValidationError
        If ``version`` is not a series version, the station is not in the
        series, ``variables`` is empty, a string or contains unknown names,
        a bound is not a ``date`` or ``start`` is later than ``end``.
    IMGWStoreError
        If ``series.json`` or its sidecar does not exist.
    IMGWStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    IMGWDataError
        If the index or Parquet file is unreadable, corrupted or does not
        match its checksum or metadata.
    """
    path = _main_file(version, SERIES_FILE)
    index = read_series_index(path)
    if station not in index.stations:
        raise IMGWValidationError(
            f"Stacja {station!r} nie występuje w szeregu {index.dataset}"
        )
    if isinstance(variables, str):
        raise IMGWValidationError(
            "variables musi być listą nazw zmiennych, nie pojedynczym tekstem"
        )
    names = tuple(dict.fromkeys(variables))
    descriptor = get_dataset(index.dataset)
    unknown = [name for name in names if name not in descriptor.variables]
    if not names or unknown:
        raise IMGWValidationError(
            f"Nieznane zmienne {', '.join(map(str, unknown)) or '(brak)'}; dostępne: {', '.join(descriptor.variables)}"
        )
    for bound in (start, end):
        if bound is not None and (
            not isinstance(bound, date) or isinstance(bound, datetime)
        ):
            raise IMGWValidationError(f"Granica zakresu musi być datą: {bound!r}")
    if start is not None and end is not None and start > end:
        raise IMGWValidationError(
            f"Początek zakresu {start} jest późniejszy niż koniec {end}"
        )
    pa, pq = _pyarrow()
    entry = index.stations[station]
    parquet = path.parent / entry.file
    try:
        data = parquet.read_bytes()
    except OSError as exc:
        raise IMGWDataError(f"Nie można odczytać {parquet}: {exc}") from exc
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        raise IMGWDataError(
            f"Suma kontrolna Parquet stacji {station} nie zgadza się ze spisem: {parquet}"
        )
    half_year = descriptor.time_unit == "half_year"
    columns = ["date", "hydro_year", *(["period"] if half_year else [])]
    for name in names:
        columns += [
            f"{name}_value",
            f"{name}_flag",
            *([f"{name}_start", f"{name}_end"] if half_year else []),
        ]
    try:
        table = pq.read_table(pa.BufferReader(data), columns=columns)
        metadata = table.schema.metadata or {}
        if (
            metadata.get(b"imgw_schema") != SERIES_SCHEMA.encode()
            or metadata.get(b"dataset") != index.dataset.encode()
        ):
            raise ValueError("metadane Parquet nie odpowiadają spisowi")
        if table.num_rows != entry.rows:
            raise ValueError(
                f"liczba wierszy {table.num_rows} różni się od spisu ({entry.rows})"
            )
        rows = table.to_pylist()
    except (pa.ArrowException, ValueError) as exc:
        raise IMGWDataError(
            f"Nieprawidłowy Parquet stacji {station} ({parquet}): {exc}"
        ) from exc
    return _records(
        rows,
        station=station,
        dataset=index.dataset,
        names=names,
        half_year=half_year,
        start=start,
        end=end,
    )


def _records(
    rows: list[dict[str, Any]],
    *,
    station: str,
    dataset: str,
    names: tuple[str, ...],
    half_year: bool,
    start: date | None,
    end: date | None,
) -> Iterator[NormalizedRecord]:
    for row in rows:
        day = row["date"]
        if (start is not None and day < start) or (end is not None and day > end):
            continue
        measurements: dict[str, Measurement] = {}
        for name in names:
            value, flag = row[f"{name}_value"], row[f"{name}_flag"]
            if flag not in _FLAGS or (value is None) != (flag == "missing"):
                raise IMGWDataError(
                    f"Niespójna flaga {flag!r} zmiennej {name} stacji {station} z {day}"
                )
            measurements[name] = Measurement(value, flag)
        extrema = (
            {name: (row[f"{name}_start"], row[f"{name}_end"]) for name in names}
            if half_year
            else {}
        )
        yield NormalizedRecord(
            station,
            dataset,
            day,
            row["hydro_year"],
            row["period"] if half_year else None,
            measurements,
            extrema_dates=extrema,
        )
