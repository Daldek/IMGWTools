"""Offline, read-only access to the versioned IMGW store (no network, writes, or locks)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from imgwtools._parsing import normalize_archive
from imgwtools._parsing.chmi import iter_stations
from imgwtools._parsing.stations import parse_stations_csv
from imgwtools.datasets import (
    _CATALOG_DATASETS,
    DATASET_KEY_PATTERN,
    STATION_CODE_PATTERN,
    ArchiveFile,
    DatasetDescriptor,
    License,
    YearsArg,
    _archive_from_path,
    datasets,
    get_dataset,
    get_provider,
    parse_years,
    providers,
    resolve_dataset_key,
    station_source_files,
)
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWStoreError,
    IMGWValidationError,
    io_error,
)
from imgwtools.models import Measurement, NormalizedRecord, StationListEntry
from imgwtools.store.catalog import (
    _CATALOG_DIRS,
    _NESTED_CATALOGS,
    CATALOG_FILE,
    RootArg,
    _newest_downloaded,
    _signal_time,
    _timestamp,
)
from imgwtools.store.pmaxtp import CELL_FILE, CELL_SCHEMA, RESPONSE_FILE
from imgwtools.store.series import (
    _FLAGS,
    SERIES_SCHEMA,
    _pyarrow,
    _series_descriptor,
)
from imgwtools.store.types import (
    Meta,
    Observation,
    PathArg,
    SeriesIndex,
    SeriesSelection,
    StationCoverage,
    StationFeature,
    StationSeriesIndex,
    StoreEntry,
    StoreHandle,
    StoreInfo,
)
from imgwtools.store.writer import (
    _MARKER,
    _OBSERVATIONS,
    OBSERVATION_SCHEMA,
    _is_register,
    _is_seen_at,
    _observation_name,
    _safe_root,
    _validate_slot,
)

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
    "observation": OBSERVATION_SCHEMA,
}

EntryKind = Literal["archive", "series", "catalog", "pmaxtp", "observation", "problem"]
_KINDS: tuple[EntryKind, ...] = (
    "archive",
    "series",
    "catalog",
    "pmaxtp",
    "observation",
    "problem",
)
_STALE_SECONDS = 24 * 60 * 60
_SIDECAR = ".meta.json"
_SHA = re.compile(r"^[0-9a-f]{64}$")
# Dataset key <country>.<provider>.<name> of any provider (ADR-003 D1, IMGW-20).
_DATASET = re.compile(DATASET_KEY_PATTERN)
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_CODE = re.compile(STATION_CODE_PATTERN)
_VERSION_DIR = re.compile(r"^.+_[0-9a-f]{8}$")
_CELL = re.compile(r"^[0-9]+_[0-9]+$")
_PARQUET = re.compile(
    rf"^stations/{STATION_CODE_PATTERN.removeprefix('^').removesuffix('$')}\.parquet$"
)
_OBSERVATION_FILE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9a-f]{8}\.json$")
_SAME_CONTENT = re.compile(r"^[^/]+_[0-9a-f]{8}$")
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
        info = StoreInfo(
            path, path.exists(), schema, False, contracts, (text,), providers()
        )
        return info, code

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
    return StoreInfo(path, True, schema, True, contracts, (), providers()), None


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
        versions supported by this library, the detected problems and the
        data providers the library knows (``providers()``, registry order).

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
        raise IMGWStoreError(
            "; ".join(info.problems), details={"reason": "unsupported"}
        )
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


def _registry_origin(dataset: str) -> tuple[str, str] | None:
    """``(country, provider)`` the registry gives ``dataset``; None for an unknown key."""
    key = resolve_dataset_key(dataset)
    if key is None:
        return None
    # Every registry key starts with its provider's key prefix (ADR-003 D1).
    provider = get_provider(key.rsplit(".", 1)[0])
    return provider.country, provider.id


def _content_fields(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """``content_sha256`` and ``content_form``: both absent (None) or both valid."""
    present = [key for key in ("content_sha256", "content_form") if key in payload]
    if not present:
        return None, None
    if len(present) == 1:
        raise _Invalid(
            "invalid_meta",
            "pola content_sha256 i content_form występują razem albo wcale",
        )
    digest = payload["content_sha256"]
    if not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise _Invalid(
            "invalid_meta", "pole content_sha256 musi mieć 64 małe cyfry szesnastkowe"
        )
    return digest, _text(payload, "content_form")


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
    if not _DATASET.fullmatch(dataset):
        raise _Invalid(
            "invalid_meta",
            "pole dataset musi być kluczem zbioru <kraj>.<dostawca>.<nazwa>",
        )
    country = _text(payload, "country")
    if not _COUNTRY.fullmatch(country):
        raise _Invalid(
            "invalid_meta", "pole country musi być kodem kraju z dwóch wielkich liter"
        )
    provider = _text(payload, "provider")
    origin = _registry_origin(dataset)
    if origin is not None and (country, provider) != origin:
        raise _Invalid(
            "invalid_meta",
            f"zbiór {dataset} ma w rejestrze country {origin[0]} i provider {origin[1]}",
        )
    request = _object(payload, "request")
    license_ = _object(payload, "license")
    extra = _object(payload, "extra")
    license_id = _text(license_, "id")
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
    content_sha256, content_form = _content_fields(payload)
    terms_url = license_.get("terms_url")
    return Meta(
        schema,
        dataset,
        resolve_dataset_key(dataset),
        sha,
        size,
        downloaded_at,
        License(
            license_id,
            attribution,
            url,
            terms_url if isinstance(terms_url, str) and terms_url else None,
        ),
        request,
        extra,
        content_sha256,
        content_form,
        provider=provider,
        country=country,
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
        If the sidecar is a symbolic link, not valid JSON or does not satisfy
        ``imgw-meta/1``; with code ``io_error`` (``details.path``) if the
        system cannot read it.
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
            raise IMGWStoreError(f"Brak sidecara {sidecar}", code="not_found") from exc
        if isinstance(exc.__cause__, OSError):
            raise io_error(exc.__cause__) from exc.__cause__
        raise IMGWDataError(f"Nieprawidłowy sidecar {sidecar}: {exc}") from exc


# --------------------------------------------------------------------------
# Versions and scan
# --------------------------------------------------------------------------


def _check_version(
    directory: Path,
    name: str,
    *,
    subdirs: tuple[str, ...] = (),
    attachments: tuple[str, ...] = (),
) -> tuple[Path, Meta]:
    """
    Validate one published version directory; ``name`` is the expected main file.

    An attachment (e.g. the raw PMAXTP ``response.json``) has no sidecar of its
    own: it is allowed only when ``extra.response`` of the main sidecar
    describes it (``name``, ``sha256``, ``size_bytes``), and then it must exist
    with that size. Versions without the description and without the file are
    valid (written before attachments existed).
    """
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
    if name + _SIDECAR not in files:
        # The sidecar is published last and commits the version (Kartograf D18).
        raise _Invalid(
            "missing_sidecar",
            f"brak sidecara {name}{_SIDECAR} (niedokończona publikacja wersji)",
        )
    if name not in files:
        raise _Invalid("missing_file", f"brak pliku głównego {name}")
    unexpected = sorted(files - {name, name + _SIDECAR, *attachments})
    if unexpected:
        raise _Invalid(
            "unknown_entry", f"nieznane pliki w wersji: {', '.join(unexpected)}"
        )
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
    for attachment in attachments:
        _check_attachment(directory, attachment, meta, present=attachment in files)
    return main, meta


def _check_attachment(directory: Path, name: str, meta: Meta, *, present: bool) -> None:
    """Validate an attachment against ``extra.response`` of the main sidecar (no hashing)."""
    info = meta.extra.get("response")
    if info is None:
        if present:
            raise _Invalid(
                "unknown_entry", f"plik {name} bez opisu extra.response w sidecarze"
            )
        return
    if not isinstance(info, Mapping):
        raise _Invalid("invalid_meta", "pole extra.response musi być obiektem")
    size = info.get("size_bytes")
    sha = info.get("sha256")
    if (
        info.get("name") != name
        or not isinstance(sha, str)
        or not _SHA.match(sha)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise _Invalid(
            "invalid_meta",
            f"pole extra.response musi mieć name={name}, sha256 i size_bytes",
        )
    if not present:
        raise _Invalid("missing_file", f"brak pliku {name} opisanego w sidecarze")
    if (directory / name).stat().st_size != size:
        raise _Invalid(
            "size_mismatch", f"rozmiar {name} różni się od extra.response w sidecarze"
        )


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _slot_provider(slot: str | None) -> str | None:
    """Provider of the dataset named by a slot; None without a slot or a known key."""
    key = (slot or "").partition(":")[2].partition(":")[0]
    origin = _registry_origin(key) if key else None
    return None if origin is None else origin[1]


def _problem(slot: str | None, path: Path, code: str, text: str) -> StoreEntry:
    return StoreEntry(
        "problem", slot, path, None, code, text, provider=_slot_provider(slot)
    )


def _unknown(root: Path, path: Path) -> StoreEntry:
    return _problem(
        None,
        path,
        "unknown_entry",
        f"Nieznany element magazynu: {_relative(root, path)}",
    )


def _entry(
    root: Path,
    kind: EntryKind,
    slot: str,
    directory: Path,
    name: str,
    *,
    server_path: str | None = None,
    strict: bool = False,
    **options: Any,
) -> StoreEntry:
    """
    Entry of one version directory; a broken version becomes a problem entry.

    With ``strict`` a version the system cannot read raises `io_error`
    instead (readers of one slot; a scan reports it as ``unreadable``).
    """
    try:
        main, meta = _check_version(directory, name, **options)
        if (
            server_path is not None
            and meta.request.get("server_path", server_path) != server_path
        ):
            raise _Invalid(
                "invalid_meta",
                "request.server_path w sidecarze nie odpowiada ścieżce wersji",
            )
        if kind == "catalog" and meta.dataset_key != slot.split(":")[1]:
            raise _Invalid(
                "invalid_meta",
                f"zbiór {meta.dataset} sidecara nie odpowiada slotowi {slot}",
            )
        if kind == "series":
            series_schema = meta.extra.get("series_schema")
            if not isinstance(series_schema, str):
                raise _Invalid(
                    "invalid_meta", "pole extra.series_schema musi być tekstem"
                )
            if series_schema != SERIES_SCHEMA:
                raise _Invalid(
                    "unknown_schema", f"nieobsługiwany schemat szeregu {series_schema}"
                )
    except _Invalid as exc:
        if strict and exc.code == "unreadable" and isinstance(exc.__cause__, OSError):
            raise io_error(exc.__cause__) from exc.__cause__
        return _problem(
            slot, directory, exc.code, f"Wersja {_relative(root, directory)}: {exc}"
        )
    except OSError as exc:
        if strict:
            raise io_error(exc) from exc
        return _problem(
            slot, directory, "unreadable", f"Wersja {_relative(root, directory)}: {exc}"
        )
    return StoreEntry(kind, slot, main, meta, None, None, provider=_slot_provider(slot))


# --------------------------------------------------------------------------
# Observation register (ADR-003 D18)
# --------------------------------------------------------------------------


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    """A required field holding a non-empty text or null."""
    if key not in payload:
        raise _Invalid("invalid_meta", f"brak pola {key}")
    value = payload[key]
    if value is not None and (not isinstance(value, str) or not value):
        raise _Invalid(
            "invalid_meta", f"pole {key} musi być niepustym tekstem albo null"
        )
    return value


def _digest(payload: Mapping[str, Any], key: str) -> str:
    """A required SHA-256 hex digest field."""
    value = payload.get(key)
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise _Invalid(
            "invalid_meta", f"pole {key} musi mieć 64 małe cyfry szesnastkowe"
        )
    return value


def _parse_observation(payload: object) -> Observation:
    """Validate the ``imgw-observation/1`` fields; additional fields are tolerated."""
    if not isinstance(payload, dict):
        raise _Invalid("invalid_meta", "obserwacja nie jest obiektem JSON")
    schema = payload.get("schema")
    if not isinstance(schema, str):
        raise _Invalid("invalid_meta", "brak pola schema")
    if schema != OBSERVATION_SCHEMA:
        raise _Invalid("unknown_schema", f"nieobsługiwany schemat obserwacji {schema}")
    _text(payload, "producer")
    _text(payload, "producer_version")
    dataset = _text(payload, "dataset")
    if not _DATASET.fullmatch(dataset):
        raise _Invalid(
            "invalid_meta",
            "pole dataset musi być kluczem zbioru <kraj>.<dostawca>.<nazwa>",
        )
    seen_at = payload.get("seen_at")
    if not isinstance(seen_at, str) or not _is_seen_at(seen_at):
        raise _Invalid(
            "invalid_meta", "pole seen_at musi być czasem UTC RRRR-MM-DDTGG:MM:SSZ"
        )
    url = _text(payload, "url")
    last_modified = _optional_text(payload, "last_modified")
    etag = _optional_text(payload, "etag")
    size = payload.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise _Invalid(
            "invalid_meta", "pole size_bytes musi być nieujemną liczbą całkowitą"
        )
    sha = _digest(payload, "sha256")
    content_sha256 = _digest(payload, "content_sha256")
    content_form = _text(payload, "content_form")
    same = payload.get("same_content_as")
    if not isinstance(same, str) or not _SAME_CONTENT.fullmatch(same):
        raise _Invalid(
            "invalid_meta",
            "pole same_content_as musi być nazwą katalogu wersji <etykieta>_<sha8>",
        )
    return Observation(
        dataset,
        seen_at,
        url,
        last_modified,
        etag,
        size,
        sha,
        content_sha256,
        content_form,
        same,
    )


def _load_observation(path: Path) -> Observation:
    """Read and parse one observation file of a register."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _Invalid(
            "unreadable", f"nieczytelna obserwacja {path.name}: {exc}"
        ) from exc
    try:
        payload = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise _Invalid(
            "invalid_json", f"uszkodzony JSON obserwacji {path.name}: {exc}"
        ) from exc
    return _parse_observation(payload)


def _check_observation(
    path: Path, observation: Observation, dataset: str, versions: Mapping[str, Meta]
) -> None:
    """
    Check an observation against its file name and its archive slot.

    The name must follow ``seen_at`` and the signal, ``dataset`` must be the
    slot's, and ``same_content_as`` must name a valid version of the slot
    (``versions``: directory name → sidecar) with equal content fields.
    """
    expected = _observation_name(observation)
    if not path.name.startswith(f"{observation.seen_at[:10]}_"):
        raise _Invalid(
            "invalid_meta",
            f"nazwa {path.name} nie odpowiada dacie seen_at {observation.seen_at}",
        )
    if path.name != expected:
        raise _Invalid(
            "invalid_meta",
            f"nazwa {path.name} nie odpowiada sygnałowi obserwacji (oczekiwano {expected})",
        )
    if resolve_dataset_key(observation.dataset) != dataset:
        raise _Invalid(
            "invalid_meta",
            f"pole dataset {observation.dataset} różni się od zbioru slotu {dataset}",
        )
    meta = versions.get(observation.same_content_as)
    if meta is None:
        raise _Invalid(
            "invalid_meta",
            f"same_content_as {observation.same_content_as} nie wskazuje poprawnej "
            "wersji w slocie",
        )
    if (meta.content_sha256, meta.content_form) != (
        observation.content_sha256,
        observation.content_form,
    ):
        raise _Invalid(
            "invalid_meta",
            f"pola treści różnią się od pól wersji {observation.same_content_as}",
        )


def _scan_register(
    root: Path, register: Path, slot: str, versions: Mapping[str, Meta]
) -> Iterator[StoreEntry]:
    """
    Observations and problems of the register ``observations/`` of an archive slot.

    ``versions`` maps the directory names of the slot's valid versions to their
    sidecars. Files are not hashed.
    """
    dataset = slot.split(":")[1]
    for child in sorted(register.iterdir()):
        relative = _relative(root, child)
        if child.is_symlink():
            yield _problem(
                slot,
                child,
                "symlink",
                f"Dowiązanie symboliczne w rejestrze obserwacji: {relative}",
            )
        elif not child.is_file() or not _OBSERVATION_FILE.fullmatch(child.name):
            yield _unknown(root, child)
        else:
            try:
                observation = _load_observation(child)
                _check_observation(child, observation, dataset, versions)
            except _Invalid as exc:
                yield _problem(slot, child, exc.code, f"Obserwacja {relative}: {exc}")
            else:
                yield StoreEntry(
                    "observation",
                    slot,
                    child,
                    None,
                    None,
                    None,
                    observation,
                    provider=_slot_provider(slot),
                )


# --------------------------------------------------------------------------
# Slots (spec §13.7)
# --------------------------------------------------------------------------

_SLOT_GRAMMAR = (
    "archive:<klucz>:<ścieżka>, series:<klucz>, catalog:<klucz katalogu> "
    f"({', '.join(_CATALOG_DATASETS.values())}) "
    "albo pmaxtp:pl.imgw.pmaxtp:<POT|AMP>/<indX>_<indY>"
)
_PMAXTP_KEY = "pl.imgw.pmaxtp"


def _archive_descriptors() -> list[DatasetDescriptor]:
    """Stored archive datasets, longest server directory first."""
    return sorted(
        (item for item in datasets() if item.in_store and item.server_dir is not None),
        key=lambda item: -len(item.server_dir or ""),
    )


def _archive_slot(server_path: str) -> str | None:
    """
    Slot ``archive:<key>:<selector>`` of a stored server path.

    The owning dataset is the stored one with the longest matching server
    directory. Station lists accept only their published file name, other
    datasets a selector with a folder; any other path has no slot.
    """
    descriptor = next(
        (
            item
            for item in _archive_descriptors()
            if server_path.startswith(f"{item.server_dir}/")
        ),
        None,
    )
    if descriptor is None:
        return None
    selector = server_path.removeprefix(f"{descriptor.server_dir}/")
    if descriptor.time_unit == "station_list":
        names = {
            PurePosixPath(item.server_path).name
            for item in station_source_files(provider=descriptor.provider)
            if item.dataset == descriptor.key
        }
        valid = selector in names
    elif descriptor.archive_scope != "country":
        # Per-station files follow the file-name grammar of the dataset.
        valid = _archive_from_path(descriptor.key, server_path) is not None
    else:
        valid = "/" in selector
    if not valid or ":" in selector:
        return None
    return f"archive:{descriptor.key}:{selector}"


def _scanned_archive_slot(base: Path, directory: Path) -> tuple[str, str] | None:
    """Slot and server path of a version directory, named after its (possibly orphaned) main file."""
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
    server_path = f"{slot_dir.parent.relative_to(base).as_posix()}/{name}"
    slot = _archive_slot(server_path)
    return None if slot is None else (slot, server_path)


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
    """
    Archive versions, observations and problems below ``directory``.

    A directory ``observations`` is recognized before the version-directory
    rule: beside versions of exactly one slot it is that slot's observation
    register (ADR-003 D18), anywhere else an unknown element.
    """
    register: Path | None = None
    slots: set[str] = set()
    versions: dict[str, Meta] = {}
    for child in _directories(root, directory):
        if isinstance(child, StoreEntry):
            yield child
            continue
        if child.name == _OBSERVATIONS:
            register = child
            continue
        has_files = any(
            not item.is_dir() or item.is_symlink() for item in child.iterdir()
        )
        if has_files or _VERSION_DIR.match(child.name):
            found = (
                _scanned_archive_slot(base, child)
                if len(child.relative_to(base).parts) >= 3
                else None
            )
            if found is None:
                yield _unknown(root, child)
            else:
                slot, server_path = found
                entry = _entry(
                    root,
                    "archive",
                    slot,
                    child,
                    PurePosixPath(server_path).name,
                    server_path=server_path,
                )
                slots.add(slot)
                if entry.meta is not None:
                    versions[child.name] = entry.meta
                yield entry
        else:
            yield from _scan_archives(root, base, child)
    if register is not None:
        if len(slots) == 1:
            yield from _scan_register(root, register, slots.pop(), versions)
        else:
            yield _unknown(root, register)


def _series_datasets() -> dict[str, DatasetDescriptor]:
    """Datasets with derived series, keyed by their store directory slug."""
    return {
        item.slug: item
        for item in datasets()
        if item.in_store and item.time_unit in ("day", "month", "half_year")
    }


def _derived_entry(
    root: Path,
    version: Path | StoreEntry,
    kind: EntryKind,
    slot: str,
    name: str,
    **options: Any,
) -> StoreEntry:
    """Entry of a series, catalog or PMAXTP slot child; only archives have a register."""
    if isinstance(version, StoreEntry):
        return version
    if version.name == _OBSERVATIONS:
        return _unknown(root, version)
    return _entry(root, kind, slot, version, name, **options)


def _scan_catalogs(root: Path, versions: Path) -> Iterator[StoreEntry]:
    """
    Station catalog versions and problems below ``stations/versions/``.

    A directory named ``<label>_<sha8>`` (or holding files) is a version of the
    IMGW-PIB catalog; a directory named after the slug of another provider's
    catalog holds the versions of that catalog (ADR-003 D5); any other
    directory is an unknown element.
    """
    for child in _directories(root, versions):
        if isinstance(child, StoreEntry):
            yield child
        elif child.name in _NESTED_CATALOGS:
            slot = f"catalog:{_CATALOG_DATASETS[_NESTED_CATALOGS[child.name]]}"
            for version in _directories(root, child):
                yield _derived_entry(root, version, "catalog", slot, CATALOG_FILE)
        elif _VERSION_DIR.match(child.name) or any(
            not item.is_dir() or item.is_symlink() for item in child.iterdir()
        ):
            yield _derived_entry(
                root,
                child,
                "catalog",
                f"catalog:{_CATALOG_DATASETS['IMGW-PIB']}",
                CATALOG_FILE,
            )
        else:
            yield _unknown(root, child)


def _scan_kind(root: Path, top: Path) -> Iterator[StoreEntry]:
    for versions in _versions_dir(root, top):
        if isinstance(versions, StoreEntry):
            yield versions
        elif top.name == "archives":
            yield from _scan_archives(root, versions, versions)
        elif top.name == "stations":
            yield from _scan_catalogs(root, versions)
        elif top.name == "series":
            series = _series_datasets()
            for slug in _directories(root, versions):
                if isinstance(slug, StoreEntry) or slug.name not in series:
                    yield slug if isinstance(slug, StoreEntry) else _unknown(root, slug)
                    continue
                for version in _directories(root, slug):
                    yield _derived_entry(
                        root,
                        version,
                        "series",
                        f"series:{series[slug.name].key}",
                        SERIES_FILE,
                        subdirs=("stations",),
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
                        yield _derived_entry(
                            root,
                            version,
                            "pmaxtp",
                            f"pmaxtp:{_PMAXTP_KEY}:{method.name}/{cell.name}",
                            CELL_FILE,
                            attachments=(RESPONSE_FILE,),
                        )


def _scan(root: Path) -> Iterator[StoreEntry]:
    info, code = _inspect(root)
    if code is not None:
        for text in info.problems:
            yield _problem(None, root / _MARKER, code, text)
        return
    cutoff = time.time() - _STALE_SECONDS
    for child in sorted(root.iterdir()):
        if child.name == _MARKER:
            continue
        if child.is_symlink():
            yield _problem(
                None,
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
                        None,
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


def iter_store(
    root: RootArg, /, *, kind: str | None = None, provider: str | None = None
) -> Iterator[StoreEntry]:
    """
    Scan every published version, observation and problem offline, without writing.

    Unknown directories, missing sidecars, corrupted JSON, unknown schemas
    (of the sidecar or, for series, of ``extra.series_schema``), size
    mismatches and ``.incoming`` stagings older than 24 hours are
    reported as separate ``StoreEntry(kind="problem")`` entries; younger
    stagings are private and are not versions. Files are not hashed during
    the scan (only their size is compared with ``size_bytes``). Each valid
    file of the observation register ``observations/`` of an archive slot
    is a ``StoreEntry(kind="observation")`` (never a version); a broken one
    is a problem with the slot. Every entry names the provider of its
    slot's dataset in ``StoreEntry.provider`` (None for a problem without a
    slot).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    kind : {"archive", "series", "catalog", "pmaxtp", "observation", "problem"} or None, optional
        Return only entries of this kind; ``None`` returns all entries.
    provider : str or None, optional
        Return only the entries of this provider (``ProviderDescriptor.id`` or
        key prefix) and the problems without a slot; ``None`` returns the
        entries of all providers.

    Returns
    -------
    Iterator[StoreEntry]
        Lazily scanned published versions, observations and problems.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is not a known entry kind, ``provider`` names no provider
        or the root path contains ``..``.
    IMGWStoreError
        If a component of the root path is a symbolic link.
    """
    if kind is not None and kind not in _KINDS:
        raise IMGWValidationError(
            f"Nieznany rodzaj wpisu magazynu: {kind!r}; dozwolone {', '.join(_KINDS)}"
        )
    owner = None if provider is None else get_provider(provider).id
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    return (
        entry
        for entry in _scan(path)
        if (kind is None or entry.kind == kind)
        and (owner is None or entry.provider in (owner, None))
    )


def _invalid_slot(slot: object, reason: str) -> IMGWValidationError:
    return IMGWValidationError(
        f"Nieprawidłowy slot {slot!r}: {reason}; oczekiwano {_SLOT_GRAMMAR}",
        details={"option": "slot", "value": slot if isinstance(slot, str) else None},
    )


def _slot_location(
    root: Path, slot: str
) -> tuple[EntryKind, Path, str, dict[str, Any]]:
    """Kind, slot directory, main file name and `_entry` options of a §13.7 slot."""
    if not isinstance(slot, str):
        raise _invalid_slot(slot, "slot musi być tekstem")
    kind, _, rest = slot.partition(":")
    key, has_selector, selector = rest.partition(":")
    if kind == "archive":
        descriptor = next(
            (item for item in _archive_descriptors() if item.key == key), None
        )
        if descriptor is None:
            raise _invalid_slot(slot, f"{key!r} nie jest kluczem zbioru archiwów")
        server_path = f"{descriptor.server_dir}/{selector}"
        if not has_selector or _archive_slot(server_path) != slot:
            raise _invalid_slot(
                slot, f"nieprawidłowa ścieżka pliku zbioru {descriptor.key}"
            )
        relative = PurePosixPath(server_path)
        directory = _validate_slot(
            root, f"archives/versions/{relative.parent.as_posix()}/{relative.stem}"
        )
        return "archive", directory, relative.name, {"server_path": server_path}
    if has_selector:
        cell = re.fullmatch(r"(POT|AMP)/([0-9]+_[0-9]+)", selector)
        if kind != "pmaxtp" or key != _PMAXTP_KEY or cell is None:
            raise _invalid_slot(slot, "nieoczekiwany selektor")
        return (
            "pmaxtp",
            _validate_slot(root, f"pmaxtp/versions/{cell[1]}/{cell[2]}"),
            CELL_FILE,
            {"attachments": (RESPONSE_FILE,)},
        )
    series = {item.key: item for item in _series_datasets().values()}
    if kind == "series" and key in series:
        return (
            "series",
            _validate_slot(root, f"series/versions/{series[key].slug}"),
            SERIES_FILE,
            {"subdirs": ("stations",)},
        )
    owner = next(
        (owner for owner, catalog in _CATALOG_DATASETS.items() if catalog == key),
        None,
    )
    if kind == "catalog" and owner is not None:
        return "catalog", _validate_slot(root, _CATALOG_DIRS[owner]), CATALOG_FILE, {}
    raise _invalid_slot(slot, "nieznany rodzaj lub klucz")


def current_version(root: RootArg, /, *, slot: str) -> StoreEntry | None:
    """
    Current published version of a slot; a broken version in the slot is an error.

    A version directory without the main file's sidecar is an interrupted
    publication, not a version: it is skipped here (``iter_store`` reports it
    as ``missing_sidecar``), and the next write of the same content
    completes it.

    Archive versions are ordered by ``Last-Modified``, then ``downloaded_at``,
    then path; derived versions (series, catalog, PMAXTP) by
    ``downloaded_at``, then path. Staging directories are never returned, and
    the observation register ``observations/`` of an archive slot is not a
    version.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    slot : str
        Slot in the §13.7 grammar: ``archive:<key>:<server path without the
        dataset server directory>`` (e.g.
        ``archive:pl.imgw.hydro_daily:2024/codz_2024.zip``),
        ``series:<key>``, ``catalog:<catalog key>`` (``catalog:pl.imgw.stations``,
        ``catalog:cz.chmi.stations``) or
        ``pmaxtp:pl.imgw.pmaxtp:<POT|AMP>/<indX>_<indY>``. Station selectors
        of series slots exist only in project pins and are rejected here.

    Returns
    -------
    StoreEntry or None
        Entry of the current version, or ``None`` if the slot has no
        versions.

    Raises
    ------
    IMGWStoreError
        If the root is not a supported store (code ``store_unavailable``) or
        a root or slot path component is a symbolic link (code
        ``validation_error``).
    IMGWValidationError
        If ``slot`` does not follow the grammar (including the pre-3.0.0
        forms ``archive:<server_path>``, ``series:<slug>``,
        ``catalog:stations`` and ``pmaxtp:<M>:<x>_<y>``); the message
        describes the grammar. Also if the root path contains ``..``.
    IMGWDataError
        If any version in the slot is broken (an older version is never
        silently selected instead); with code ``io_error``
        (``details.path``) if the system cannot read one.
    """
    path = _open(root)
    kind, directory, name, options = _slot_location(path, slot)
    if not directory.is_dir():
        return None
    versions: list[tuple[Path, dict[str, Any]]] = []
    entries: dict[Path, StoreEntry] = {}
    # Catalogs of other providers lie in named directories of the IMGW-PIB slot.
    imgw_catalog = slot == f"catalog:{_CATALOG_DATASETS['IMGW-PIB']}"
    nested = _NESTED_CATALOGS if imgw_catalog else {}
    for version in sorted(directory.iterdir()):
        if (kind == "archive" and _is_register(version)) or (
            version.name in nested and version.is_dir() and not version.is_symlink()
        ):
            continue
        entry = (
            _entry(path, kind, slot, version, name, strict=True, **options)
            if version.is_dir()
            else _unknown(path, version)
        )
        if entry.kind == "problem" and entry.problem_code == "missing_sidecar":
            continue
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


@dataclass(frozen=True)
class _Reference:
    """
    Reference signal of an archive slot (ADR-003 D18).

    Attributes
    ----------
    version : StoreEntry
        Current version of the slot.
    url, etag, last_modified : str or None
        Signal of the newest observation of the current version, or without
        one the version's ``extra.http``.
    size_bytes : int
        Size of the observed bytes, or of the version's main file.
    observation : Path or None
        Observation giving the signal; None when it is the version's own.
    """

    version: StoreEntry
    url: str | None
    etag: str | None
    last_modified: str | None
    size_bytes: int
    observation: Path | None


def _reference_signal(root: RootArg, /, *, slot: str) -> _Reference | None:
    """
    Signal the next download of an archive slot is compared with (ADR-003 D18).

    The newest observation of the current version (by ``seen_at``, then file
    name) gives the signal; observations of older versions are history. Without
    such an observation the signal is the version's ``extra.http`` and
    ``size_bytes``, exactly as in a slot without a register.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    slot : str
        Archive slot ``archive:<key>:<selector>``.

    Returns
    -------
    _Reference or None
        Reference signal with the current version; None for a slot without
        versions.

    Raises
    ------
    IMGWValidationError
        If ``slot`` is not an archive slot of the grammar.
    IMGWDataError
        If a version of the slot is broken (as `current_version`), an
        observation of the current version is broken or contradicts it, or a
        register file cannot be told apart from such an observation; with
        code ``io_error`` if the system cannot read one.
    """
    if not slot.startswith("archive:"):
        raise _invalid_slot(slot, "sygnał odniesienia ma wyłącznie slot archiwum")
    entry = current_version(root, slot=slot)
    if entry is None or entry.version is None or entry.meta is None:
        return None
    current = entry.version.parent
    register = current.parent / _OBSERVATIONS
    newest: tuple[tuple[str, str], Observation, Path] | None = None
    for child in sorted(register.iterdir()) if _is_register(register) else ():
        if not _OBSERVATION_FILE.fullmatch(child.name) or not (
            child.is_symlink() or child.is_file()
        ):
            continue
        try:
            if child.is_symlink():
                raise _Invalid("symlink", "dowiązanie symboliczne zamiast obserwacji")
            observation = _load_observation(child)
            if observation.same_content_as != current.name:
                continue
            _check_observation(
                child, observation, slot.split(":")[1], {current.name: entry.meta}
            )
        except _Invalid as exc:
            if exc.code == "unreadable" and isinstance(exc.__cause__, OSError):
                raise io_error(exc.__cause__) from exc.__cause__
            raise IMGWDataError(
                f"Uszkodzona obserwacja w slocie {slot}: {child.name}: {exc}"
            ) from exc
        order = (observation.seen_at, child.name)
        if newest is None or order > newest[0]:
            newest = (order, observation, child)
    if newest is not None:
        _, observation, path = newest
        return _Reference(
            entry,
            observation.url,
            observation.etag,
            observation.last_modified,
            observation.size_bytes,
            path,
        )
    http = entry.meta.extra.get("http")
    signal: Mapping[str, object] = http if isinstance(http, Mapping) else {}
    texts: list[str | None] = []
    for key in ("url", "etag", "last_modified"):
        value = signal.get(key)
        if value is not None and not isinstance(value, str):
            raise IMGWDataError(
                f"Uszkodzona wersja w slocie {slot}: extra.http.{key} musi być "
                "tekstem albo null"
            )
        texts.append(value)
    url, etag, last_modified = texts
    return _Reference(entry, url, etag, last_modified, entry.meta.size_bytes, None)


# --------------------------------------------------------------------------
# Catalog and series
# --------------------------------------------------------------------------


def _main_file(version: PathArg, name: str) -> Path:
    path = Path(version).expanduser()
    if path.is_dir():
        path = path / name
    elif path.name == name + _SIDECAR:
        path = path.with_name(name)
    if path.name != name:
        raise IMGWValidationError(
            f"Wersja musi wskazywać katalog wersji, plik {name} albo jego sidecar: {version}",
            details={"option": "version"},
        )
    return path


def _verified(path: Path) -> bytes:
    """Bytes of a version's main file, verified against its sidecar."""
    if path.is_symlink():
        raise IMGWDataError(f"Dowiązanie symboliczne zamiast pliku wersji: {path}")
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise IMGWStoreError(f"Brak pliku wersji: {path}", code="not_found") from exc
    except OSError as exc:
        raise io_error(exc) from exc
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


def _plain(value: object, *, depth: int = 0) -> bool:
    """Whether a property is a scalar or, ``depth`` levels deep, an object of such values."""
    if isinstance(value, _SCALARS):
        return True
    return (
        depth > 0
        and isinstance(value, dict)
        and all(_plain(item, depth=depth - 1) for item in value.values())
    )


def _catalog_features(path: Path) -> tuple[StationFeature, ...]:
    """Stations of one catalog version, with the provider of its sidecar."""
    document = _json(path)
    provider = read_meta(path).provider
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
                or not _CODE.fullmatch(code)
            ):
                raise ValueError(f"nieprawidłowy obiekt stacji {code!r}")
            properties = feature["properties"]
            # ČHMÚ hydro stations carry the SPA thresholds as an object (§7.4).
            if not isinstance(properties, dict) or not all(
                _plain(value, depth=2 if key == "thresholds" else 0)
                for key, value in properties.items()
            ):
                raise ValueError(
                    f"właściwości stacji {code} muszą być wartościami prostymi "
                    "(thresholds: obiektem progów)"
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
            result.append(StationFeature(code, point, properties, provider))
    except (KeyError, TypeError, ValueError) as exc:
        raise IMGWDataError(f"Nieprawidłowy katalog stacji {path}: {exc}") from exc
    return tuple(result)


def read_catalog(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    provider: str | None = None,
) -> tuple[StationFeature, ...]:
    """
    Every station of a catalog version or of the current catalogs of a store.

    Stations without geometry are included. The ``stations.geojson`` bytes are
    verified against the SHA-256 and size recorded in the sidecar, and
    ``StationFeature.provider`` comes from the sidecar. ČHMÚ hydro stations
    carry their SPA thresholds as the object ``properties["thresholds"]``.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Catalog version directory or its ``stations.geojson`` file.
    root : str, os.PathLike, StoreHandle or None, optional
        Store whose current catalog of every provider is read, in registry
        order; exactly one of ``version`` and ``root`` is required.
    provider : str or None, optional
        With ``root``: read only the current catalog of this provider
        (``ProviderDescriptor.id`` or key prefix); None reads the catalog of
        every provider and skips providers without one.

    Returns
    -------
    tuple of StationFeature
        With ``version``: stations in file order. With ``root``: the stations
        of each provider's catalog in registry order, each catalog sorted by
        ``station_code``. ``geometry`` is ``None`` for stations without a
        location.

    Raises
    ------
    IMGWValidationError
        If not exactly one of ``version`` and ``root`` is given, ``provider``
        is given with ``version`` or names no provider, or ``version`` points
        to neither a version directory nor ``stations.geojson``.
    IMGWStoreError
        If the catalog file or its sidecar does not exist, the root is not a
        supported store (code ``store_unavailable``), or the store holds no
        catalog of an explicitly given ``provider`` (code ``not_found``).
    IMGWDataError
        If a catalog version is broken, the file is a symbolic link, does not
        match its sidecar, or is not a valid station FeatureCollection; with
        code ``io_error`` (``details.path``) if the system cannot read it.
    """
    if version is not None and root is None:
        if provider is not None:
            raise IMGWValidationError(
                "Opcja provider wybiera bieżący katalog magazynu i wymaga root "
                "zamiast version",
                details={"option": "provider", "value": provider},
            )
        return _catalog_features(_main_file(version, CATALOG_FILE))
    if root is None or version is not None:
        raise IMGWValidationError(
            "Podaj dokładnie jedno z: version (wersja katalogu) albo root "
            "(bieżące katalogi stacji magazynu)",
            details={"option": "version" if root is None else "root"},
        )
    owners = providers() if provider is None else (get_provider(provider),)
    result: list[StationFeature] = []
    for owner in owners:
        key = _CATALOG_DATASETS[owner.id]
        entry = current_version(root, slot=f"catalog:{key}")
        if entry is None or entry.version is None:
            if provider is not None:
                raise IMGWStoreError(
                    f"Magazyn nie zawiera katalogu stacji {owner.short_name} ({key}); "
                    f"buduje go imgw store catalog --provider {owner.id}",
                    code="not_found",
                )
            continue
        stations = _catalog_features(entry.version)
        result.extend(sorted(stations, key=lambda station: station.station_code))
    return tuple(result)


# --------------------------------------------------------------------------
# Archives and station lists
# --------------------------------------------------------------------------


def _station_lists(provider: str = "IMGW-PIB") -> dict[str, ArchiveFile]:
    """Station list source of each kind of a provider, keyed ``"hydro"`` / ``"meteo"``."""
    return dict(
        zip(("hydro", "meteo"), station_source_files(provider=provider), strict=True)
    )


def read_station_list(
    root: RootArg,
    /,
    *,
    kind: Literal["hydro", "meteo"],
    provider: str = "IMGW-PIB",
) -> tuple[StationListEntry, ...]:
    """
    Stations of the current stored station list of one family (offline).

    Reads the current version of the provider's list dataset
    (``pl.imgw.hydro_stations``/``pl.imgw.meteo_stations`` for IMGW-PIB,
    ``cz.chmi.hydro_stations``/``cz.chmi.meteo_stations`` — the historical
    ``meta1.json`` — for ČHMÚ), verifies its bytes against the SHA-256 and
    size of the sidecar and parses it with
    :func:`imgwtools.parsers.parse_stations_csv` or
    :func:`imgwtools.parsers.parse_chmi_stations`. Lists are stored by
    :func:`build_catalog` (``imgw store catalog``).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    kind : {"hydro", "meteo"}
        Station family of the list.
    provider : str, optional
        Provider of the list (``ProviderDescriptor.id`` or key prefix),
        ``"IMGW-PIB"`` by default.

    Returns
    -------
    tuple of StationListEntry
        Stations in file order, each with ``kind`` and ``provider`` set;
        hydro-only fields are ``None`` for meteorological stations. A code
        listed twice by IMGW (e.g. a meteo station with two short codes) is
        returned twice; `build_catalog` reports such codes in its
        ``problems``. A ČHMÚ list gives one entry per code (meteo: the
        location period with the latest ``BEGIN_DATE``).

    Raises
    ------
    IMGWValidationError
        If ``kind`` is neither ``"hydro"`` nor ``"meteo"``, or ``provider``
        names no provider.
    IMGWStoreError
        If the root is not a supported store (code ``store_unavailable``) or
        the store holds no version of the list (code ``not_found``).
    IMGWDataError
        If a version of the list is broken, or the current list does not
        match its sidecar or cannot be parsed.
    """
    owner = get_provider(provider)
    lists = _station_lists(owner.id)
    if kind not in lists:
        raise IMGWValidationError(
            f"Nieznany rodzaj listy stacji: {kind!r}; dozwolone hydro, meteo",
            details={"option": "kind", "value": kind, "allowed": list(lists)},
        )
    source = lists[kind]
    entry = current_version(root, slot=str(_archive_slot(source.server_path)))
    if entry is None or entry.version is None or entry.meta is None:
        hint = (
            "build_catalog, imgw store catalog"
            if owner.id == "IMGW-PIB"
            else f"build_catalog(root, provider={owner.id!r}), imgw store catalog "
            f"--provider {owner.id}"
        )
        raise IMGWStoreError(
            f"Magazyn nie zawiera listy stacji {source.dataset}; zapisuje ją "
            f"budowa katalogu stacji ({hint})",
            code="not_found",
        )
    if entry.meta.dataset_key != source.dataset:
        raise IMGWDataError(
            f"Wersja {entry.version} należy do zbioru {entry.meta.dataset}, "
            f"a nie {source.dataset}"
        )
    data = _verified(entry.version)
    if get_dataset(source.dataset).parser == "parse_chmi_stations":
        return tuple(iter_stations(data, kind=kind, filename=str(entry.version)))
    return tuple(parse_stations_csv(data, kind=kind))


def _archive_main(version: PathArg) -> Path:
    """Main file of an archive version given as its directory, file or sidecar."""
    path = Path(version).expanduser()
    if path.is_dir():
        sidecars = sorted(
            child.name for child in path.iterdir() if child.name.endswith(_SIDECAR)
        )
        if len(sidecars) != 1:
            raise IMGWValidationError(
                f"Katalog {version} nie jest katalogiem wersji archiwum "
                "(oczekiwano dokładnie jednego sidecara)"
            )
        return path / sidecars[0].removesuffix(_SIDECAR)
    if path.name.endswith(_SIDECAR):
        return path.with_name(path.name.removesuffix(_SIDECAR))
    return path


def read_archive(version: PathArg, /) -> Iterator[NormalizedRecord]:
    """
    Normalized records of one stored archive version (offline).

    The archive is identified by its sidecar: ``dataset`` and
    ``request.server_path`` are resolved to the registry `ArchiveFile`, the
    stored bytes are verified against the sidecar SHA-256 and size, and the
    dataset parser (:func:`imgwtools.parsers.normalize_archive`) is applied.
    Validation and verification happen before the iterator is returned;
    parsing is lazy.

    Parameters
    ----------
    version : str or os.PathLike
        Archive version directory, its main file or its sidecar.

    Returns
    -------
    Iterator of NormalizedRecord
        Records exactly as produced by ``normalize_archive`` for the stored
        bytes.

    Raises
    ------
    IMGWValidationError
        If ``version`` is not an archive version (e.g. a series, catalog or
        PMAXTP version, or a directory without exactly one sidecar), or is a
        station list version (read it with :func:`read_station_list`).
    IMGWStoreError
        If the archive file or its sidecar does not exist.
    IMGWDataError
        If the sidecar is invalid or does not describe a registry archive,
        or the file does not match its sidecar; while iterating, if the
        archive content is malformed.
    """
    main = _archive_main(version)
    meta = read_meta(main)
    server_path = meta.request.get("server_path")
    descriptor = next((d for d in datasets() if d.key == meta.dataset_key), None)
    if not isinstance(server_path, str) or descriptor is None:
        raise IMGWValidationError(
            f"{main} nie jest wersją archiwum (zbiór {meta.dataset}); szeregi "
            "czyta read_series, katalog read_catalog, komórki PMAXTP read_pmaxtp"
        )
    if descriptor.time_unit == "station_list":
        kind = next(
            k
            for k, a in _station_lists(descriptor.provider).items()
            if a.dataset == descriptor.key
        )
        option = (
            ""
            if descriptor.provider == "IMGW-PIB"
            else f", provider={descriptor.provider!r}"
        )
        raise IMGWValidationError(
            f"{main} jest wersją listy stacji {meta.dataset}; listy stacji czyta "
            f"read_station_list(root, kind={kind!r}{option})"
        )
    if PurePosixPath(server_path).name != main.name:
        raise IMGWDataError(
            f"Plik {main.name} nie odpowiada request.server_path {server_path} sidecara"
        )
    archive = _archive_from_path(descriptor.key, server_path)
    mismatch = (
        None
        if archive is None
        else next(
            (
                key
                for key in ("year", "month", "station_code", "param")
                if key in meta.request and meta.request[key] != getattr(archive, key)
            ),
            None,
        )
    )
    if archive is None or mismatch is not None:
        reason = (
            f"ścieżka {server_path} nie należy do zbioru {descriptor.key}"
            if archive is None
            else f"request.{mismatch} nie odpowiada ścieżce {server_path}"
        )
        raise IMGWDataError(f"Sidecar {main} nie opisuje archiwum: {reason}")
    return normalize_archive(archive, data=_verified(main))


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


def _station_periods(code: str, value: object) -> tuple[tuple[date, date], ...] | None:
    """Known periods of one station: ascending, non-overlapping ranges, or None."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"periods stacji {code} musi być listą przedziałów")
    spans = tuple(_span(item) for item in value)
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        if start <= end:
            raise ValueError(
                f"periods stacji {code} nie są rosnącymi, rozłącznymi przedziałami"
            )
    return spans


def read_series_index(version: PathArg, /) -> SeriesIndex:
    """
    Validate ``series.json`` and its Parquet paths without pyarrow or reading Parquet bytes.

    The ``series.json`` bytes are verified against the sidecar; each station
    Parquet file must exist as a regular file, but its contents are not read.
    The known periods of a station (``stations[<code>].periods``, written for
    datasets of per-station files, ADR-003 D10) must be ascending,
    non-overlapping date ranges when present.

    Parameters
    ----------
    version : str or os.PathLike
        Series version directory or its ``series.json`` file.

    Returns
    -------
    SeriesIndex
        Dataset, year type, periods and per-station Parquet index (with the
        station periods, or None when the index has none).

    Raises
    ------
    IMGWValidationError
        If ``version`` points to neither a version directory nor
        ``series.json``.
    IMGWStoreError
        If ``series.json`` or its sidecar does not exist.
    IMGWDataError
        If the file is a symbolic link, does not match its sidecar, or is
        not a valid ``imgw-series/1`` index (including missing Parquet
        files); with code ``io_error`` (``details.path``) if the system
        cannot read it.
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
        if descriptor is None or descriptor.slug not in _series_datasets():
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
            if not _CODE.fullmatch(code):
                raise ValueError(f"nieprawidłowy kod stacji {code!r}")
            file, sha = entry["file"], entry["sha256"]
            if not isinstance(file, str) or not _PARQUET.fullmatch(file):
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
                _station_periods(code, entry.get("periods")),
            )
    except (IMGWValidationError, KeyError, TypeError, ValueError) as exc:
        raise IMGWDataError(f"Nieprawidłowy spis szeregu {path}: {exc}") from exc
    return SeriesIndex(SERIES_SCHEMA, dataset, year_type, periods, stations)


def _series_path(
    version: PathArg | None, *, root: RootArg | None, dataset: str | None
) -> Path:
    """
    ``series.json`` of a series version given explicitly or as the current one.

    ``version`` is absolute or relative to ``root`` (to the working
    directory without ``root``); ``root`` with ``dataset`` selects the
    current version of the dataset series. Giving ``version`` together with
    ``dataset``, or neither, is a validation error.
    """
    if (version is None) == (dataset is None):
        raise IMGWValidationError(
            "Wskaż wersję szeregu (version) albo magazyn i zbiór (root i dataset), "
            "nie oba naraz ani żadne",
            details={"option": "version"},
        )
    if version is not None:
        if root is None:
            return _main_file(version, SERIES_FILE)
        return _main_file(_open(root) / Path(version).expanduser(), SERIES_FILE)
    if root is None:
        raise IMGWValidationError(
            "Zbiór (dataset) wskazuje bieżącą wersję szeregu wyłącznie razem z "
            "magazynem (root)",
            details={"option": "root"},
        )
    descriptor = _series_descriptor(str(dataset))
    entry = current_version(root, slot=f"series:{descriptor.key}")
    if entry is None or entry.version is None:
        raise IMGWStoreError(
            f"Brak szeregu {descriptor.key} w magazynie; najpierw uruchom series build",
            code="not_found",
        )
    return entry.version


def _variables(
    variables: Iterable[str] | None, descriptor: DatasetDescriptor
) -> tuple[str, ...]:
    """Validated dataset variables without duplicates; ``None`` means all of them."""
    if variables is None:
        return tuple(descriptor.variables)
    if isinstance(variables, str):
        raise IMGWValidationError(
            "variables musi być listą nazw zmiennych, nie pojedynczym tekstem",
            details={"option": "variables", "value": variables},
        )
    names = tuple(dict.fromkeys(variables))
    unknown = [name for name in names if name not in descriptor.variables]
    if not names or unknown:
        raise IMGWValidationError(
            f"Nieznane zmienne {', '.join(map(str, unknown)) or '(brak)'}; dostępne: {', '.join(descriptor.variables)}",
            details={
                "option": "variables",
                "value": unknown,
                "allowed": list(descriptor.variables),
            },
        )
    return names


def _stations(stations: Iterable[str]) -> tuple[str, ...]:
    """Non-empty station codes (``STATION_CODE_PATTERN``) without duplicates, in order."""
    if isinstance(stations, str) or not isinstance(stations, Iterable):
        raise IMGWValidationError(
            "stations musi być listą kodów stacji, nie pojedynczym tekstem",
            details={"option": "stations", "value": str(stations)},
        )
    codes = tuple(dict.fromkeys(stations))
    invalid = [str(code) for code in codes if not _CODE.fullmatch(str(code))]
    if not codes or invalid:
        raise IMGWValidationError(
            f"Nieprawidłowe kody stacji {', '.join(invalid) or '(brak)'}; "
            "oczekiwano co najmniej jednego kodu z 9 cyfr (IMGW-PIB) albo "
            "identyfikatora WIGOS",
            details={"option": "stations", "value": invalid},
        )
    return codes


def _outside(codes: Iterable[str], index: SeriesIndex) -> None:
    missing = [code for code in codes if code not in index.stations]
    if missing:
        raise IMGWValidationError(
            f"Stacje spoza szeregu {index.dataset}: {', '.join(missing)}",
            details={"option": "stations", "value": missing},
        )


def read_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Iterator[NormalizedRecord]:
    """
    Values and flags of one station between ``start`` and ``end`` (inclusive, period start date).

    Arguments, the series index and the SHA-256 of the station Parquet file
    are validated before the iterator is returned. For monthly and
    half-year series the range filter applies to the period start
    (``date``). Days or months filled in by the builder are returned with
    the ``missing`` flag. Half-year records carry ``extrema_dates`` and, for
    units with IMGW rows, ``extrema_occurrences`` (``<V>_occurrences``).
    Measurements of datasets with measurement fields (ČHMÚ meteo) carry
    ``quality`` and ``source_flag`` from the ``<V>_quality`` and
    ``<V>_source_flag`` columns; elsewhere both are None.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Series version directory, its ``series.json`` or its sidecar;
        absolute or relative to ``root`` (to the working directory without
        ``root``). Mutually exclusive with ``dataset``.
    root : str, os.PathLike, StoreHandle or None, optional
        Store root: the base of a relative ``version``, or with ``dataset``
        the store whose current series version is read.
    dataset : str or None, optional
        Series dataset (key, slug or legacy alias) whose current version in
        ``root`` is read.
    station : str
        Station code (``STATION_CODE_PATTERN``) present in the series.
    variables : Iterable[str] or None, optional
        Dataset variable names; duplicates are merged, a single string or an
        empty collection is rejected. ``None`` (default) means every variable
        of the dataset.
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
        If both or neither of ``version`` and ``dataset`` are given,
        ``dataset`` lacks ``root`` or does not produce series, ``version`` is
        not a series version, the station is not in the series,
        ``variables`` is empty, a string or contains unknown names, a bound
        is not a ``date`` or ``start`` is later than ``end``.
    IMGWStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store (code
        ``store_unavailable``).
    IMGWStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    IMGWDataError
        If the index or Parquet file is corrupted or does not match its
        checksum or metadata; with code ``io_error`` (``details.path``) if
        the system cannot read it.
    """
    path = _series_path(version, root=root, dataset=dataset)
    index = read_series_index(path)
    if station not in index.stations:
        raise IMGWValidationError(
            f"Stacja {station!r} nie występuje w szeregu {index.dataset}",
            details={"option": "station", "value": station},
        )
    descriptor = get_dataset(index.dataset)
    names = _variables(variables, descriptor)
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
    except FileNotFoundError as exc:
        raise IMGWDataError(
            f"Brak pliku Parquet stacji {station} ze spisu: {parquet}"
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        raise IMGWDataError(
            f"Suma kontrolna Parquet stacji {station} nie zgadza się ze spisem: {parquet}"
        )
    half_year = descriptor.time_unit == "half_year"
    columns = ["date", "hydro_year", *(["period"] if half_year else [])]
    try:
        # ``<V>_occurrences`` is an additive imgw-series/1 column; older files lack it.
        present = set(pq.read_schema(pa.BufferReader(data)).names)
        for name in names:
            columns += [f"{name}_value", f"{name}_flag"]
            columns += [f"{name}_{field}" for field in descriptor.measurement_fields]
            if half_year:
                columns += [f"{name}_start", f"{name}_end"]
                if f"{name}_occurrences" in present:
                    columns.append(f"{name}_occurrences")
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
        fields=descriptor.measurement_fields,
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
    fields: tuple[str, ...],
    half_year: bool,
    start: date | None,
    end: date | None,
) -> Iterator[NormalizedRecord]:
    with_quality, with_source_flag = "quality" in fields, "source_flag" in fields
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
            quality = row[f"{name}_quality"] if with_quality else None
            source_flag = row[f"{name}_source_flag"] if with_source_flag else None
            if not (quality is None or type(quality) is int) or not (
                source_flag is None or isinstance(source_flag, str)
            ):
                raise IMGWDataError(
                    f"Niepoprawna jakość lub flaga źródła zmiennej {name} stacji "
                    f"{station} z {day}"
                )
            measurements[name] = Measurement(value, flag, quality, source_flag)
        extrema = (
            {name: (row[f"{name}_start"], row[f"{name}_end"]) for name in names}
            if half_year
            else {}
        )
        occurrences = {
            name: count
            for name in names
            if (count := row.get(f"{name}_occurrences")) is not None
        }
        yield NormalizedRecord(
            station,
            dataset,
            day,
            row["hydro_year"],
            row["period"] if half_year else None,
            measurements,
            extrema_dates=extrema,
            extrema_occurrences=occurrences,
        )


def summarize_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    stations: Iterable[str] | None = None,
    variables: Iterable[str] | None = None,
) -> tuple[StationCoverage, ...]:
    """
    Coverage of a series version read only from its ``series.json`` (no pyarrow).

    The index bytes are verified against the sidecar and every station
    Parquet file must exist, but Parquet contents are not read.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Series version directory, its ``series.json`` or its sidecar;
        absolute or relative to ``root`` (to the working directory without
        ``root``). Mutually exclusive with ``dataset``.
    root : str, os.PathLike, StoreHandle or None, optional
        Store root: the base of a relative ``version``, or with ``dataset``
        the store whose current series version is summarized.
    dataset : str or None, optional
        Series dataset (key, slug or legacy alias) whose current version in
        ``root`` is summarized.
    stations : Iterable[str] or None, optional
        Station codes (``STATION_CODE_PATTERN``) in the series; ``None``
        (default) means every station.
    variables : Iterable[str] or None, optional
        Dataset variable names; ``None`` (default) means every variable.

    Returns
    -------
    tuple of StationCoverage
        One row per station × variable (× half-year period) ordered by
        station code, then variable in dataset order, then period
        (``winter``, ``summer``, ``annual``).

    Raises
    ------
    IMGWValidationError
        If both or neither of ``version`` and ``dataset`` are given,
        ``dataset`` lacks ``root`` or does not produce series, ``version`` is
        not a series version, a station code is malformed or not in the
        series, or a variable is unknown.
    IMGWStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store (code
        ``store_unavailable``).
    IMGWDataError
        If the index does not match its sidecar or is not a valid
        ``imgw-series/1`` index; with code ``io_error`` (``details.path``)
        if the system cannot read it.
    """
    index = read_series_index(_series_path(version, root=root, dataset=dataset))
    descriptor = get_dataset(index.dataset)
    names = set(_variables(variables, descriptor))
    if stations is None:
        codes = tuple(sorted(index.stations))
    else:
        codes = tuple(sorted(_stations(stations)))
        _outside(codes, index)
    order = {
        name: number
        for number, name in enumerate(descriptor.variables)
        if name in names
    }
    periods: dict[str | None, int] = {
        None: 0,
        **{period: number for number, period in enumerate(_PERIODS)},
    }
    return tuple(
        coverage
        for code in codes
        for coverage in sorted(
            (
                item
                for item in index.stations[code].variables.values()
                if item.variable in order
            ),
            key=lambda item: (order[item.variable], periods[item.period]),
        )
    )


def _period_years(periods: Iterable[tuple[date, date]], year_type: str) -> set[int]:
    """Years (hydrological or calendar) touched by the published periods."""

    def year(day: date) -> int:
        return (
            day.year + 1
            if year_type == "hydrological" and day.month >= 11
            else day.year
        )

    return {
        number for start, end in periods for number in range(year(start), year(end) + 1)
    }


def select_series(
    root: RootArg,
    /,
    *,
    dataset: str,
    stations: Iterable[str],
    variables: Iterable[str] | None = None,
    years: YearsArg | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
) -> SeriesSelection:
    """
    Validate a selection of stations, variables and years from the current series.

    Nothing is written; the selection is the input of a project task
    (``series select``). The current series version of ``dataset`` in
    ``root`` must contain every selected station and every selected year.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    dataset : str
        Series dataset (key, slug or legacy alias).
    stations : Iterable[str]
        Non-empty station codes (``STATION_CODE_PATTERN``); duplicates are
        merged, order is kept.
    variables : Iterable[str] or None, optional
        Dataset variable names; ``None`` (default) means every variable.
    years : YearsArg or None, optional
        Years (``2024``, ``"2020-2023"``, ``"2020,2022"`` or a collection of
        such items); ``None`` (default) means every year of the series.
    year_type : {"hydrological", "calendar"} or None, optional
        Year numbering of ``years``; ``None`` (default) means the numbering of
        the series. Half-year series accept only ``"hydrological"``.

    Returns
    -------
    SeriesSelection
        Full dataset key, ``series.json`` of the current version, stations,
        variables, sorted years and the year type.

    Raises
    ------
    IMGWValidationError
        If the dataset does not produce series, a station code is malformed
        or not in the series, a variable is unknown, ``years`` is invalid or
        outside the series, or ``year_type`` is unknown or ``"calendar"`` for
        a half-year series.
    IMGWStoreError
        If the dataset has no series in the store (code ``not_found``) or the
        root is not a supported store (code ``store_unavailable``).
    IMGWDataError
        If the current series index is broken.
    """
    descriptor = _series_descriptor(dataset)
    codes = _stations(stations)
    names = _variables(variables, descriptor)
    if year_type is not None and year_type not in ("hydrological", "calendar"):
        raise IMGWValidationError(
            f"Nieznany rodzaj roku {year_type!r}; dozwolone hydrological, calendar",
            details={
                "option": "year_type",
                "value": str(year_type),
                "allowed": ["hydrological", "calendar"],
            },
        )
    if descriptor.time_unit == "half_year" and year_type == "calendar":
        raise IMGWValidationError(
            "Szereg półroczny obsługuje wyłącznie rok hydrologiczny",
            details={"option": "year_type", "value": year_type},
        )
    selected = parse_years(years) if years is not None else None
    path = _series_path(None, root=root, dataset=descriptor.key)
    index = read_series_index(path)
    _outside(codes, index)
    kind = year_type or index.year_type
    available = _period_years(index.periods, kind)
    chosen = selected if selected is not None else tuple(sorted(available))
    outside = [year for year in chosen if year not in available]
    if outside:
        raise IMGWValidationError(
            f"Lata spoza szeregu {descriptor.key} ({kind}): {', '.join(map(str, outside))}",
            details={"option": "years", "value": outside},
        )
    return SeriesSelection(descriptor.key, path, codes, names, chosen, kind)
