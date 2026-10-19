"""Immutable archive publication in the versioned IMGW store."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import time
import uuid
from collections.abc import Callable, Collection, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from imgwtools._version import __version__
from imgwtools.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    _license_document,
    get_dataset,
    get_provider,
)
from imgwtools.exceptions import (
    IMGWCancelledError,
    IMGWDataError,
    IMGWStoreConflictError,
    IMGWStoreError,
    IMGWValidationError,
    io_error,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store.content import CONTENT_FORMS, content_sha256
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    Observation,
    PathArg,
    Progress,
    ProgressHook,
    StoreHandle,
    VersionResult,
)

_MARKER = "imgw-store.json"
_ATTRIBUTION_CODE = "license_terms"
_CONTENT_CODE = "content_unchanged"
# Trees directly under a store root written only by IMGWTools; the reader reports
# anything unexpected there, so the Kartograf probe does not walk into them.
_MANAGED_TREES = frozenset({"archives", "series", "stations", "pmaxtp", ".incoming"})
_PATH_CONFLICT = {"reason": "path_conflict"}
OBSERVATION_SCHEMA = "imgw-observation/1"
# Observation register of an archive slot, beside its version directories.
_OBSERVATIONS = "observations"
_SEEN_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
# File types each provider publishes as archives.
_SUFFIXES = {"IMGW-PIB": (".zip", ".csv"), "CHMI": (".json", ".csv")}
# Provider whose archive sidecars keep the 3.0.0 layout: no station_code or
# param in request and no station_code in extra.period (the same bytes).
_COUNTRY_LAYOUT = "IMGW-PIB"
# On Windows os.rename never replaces an existing file or directory (MoveFileExW
# without MOVEFILE_REPLACE_EXISTING) and a directory cannot be opened to be flushed.
_WINDOWS = sys.platform == "win32"
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
# renameat2 errors of a C library or file system without RENAME_NOREPLACE.
_NO_NOREPLACE = frozenset({errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP, errno.ENOTSUP})
# link errors of file systems without hard links (e.g. SMB, FAT, exFAT).
_NO_HARD_LINKS = frozenset({errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.ENOSYS})
# Seconds a marker just created by a concurrent init_store may stay unreadable.
_MARKER_WAIT = 1.0


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    with path.open("xb") as stream:
        stream.write(_canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_dir(path: Path) -> None:
    """Flush the entries of a directory to disk (no-op on Windows, see ``_WINDOWS``)."""
    if _WINDOWS:
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _libc_renameat2() -> Callable[..., int] | None:
    """``renameat2`` of the C library on Linux (glibc 2.28+), None elsewhere."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError:
        return None
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    return renameat2


def _refusal(target: Path, error: OSError) -> Exception:
    """
    Exception for a publication the system refused.

    ``FileExistsError`` whenever ``target`` exists: network file systems
    report a rename onto an existing entry also with other codes, e.g.
    ``EACCES`` or ``ENOTEMPTY``.
    """
    if error.errno == errno.EEXIST or os.path.lexists(target):
        return FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target))
    return IMGWStoreConflictError(
        f"Nie można atomowo opublikować wersji: {error.strerror or error}"
    )


def _rename_noreplace(staged: Path, target: Path) -> bool:
    """Publish by ``renameat2(RENAME_NOREPLACE)``; False where it is unavailable."""
    renameat2 = _libc_renameat2()
    if renameat2 is None:
        return False
    source, destination = os.fsencode(staged), os.fsencode(target)
    if renameat2(_AT_FDCWD, source, _AT_FDCWD, destination, _RENAME_NOREPLACE) == 0:
        return True
    code = ctypes.get_errno()
    if code in _NO_NOREPLACE:
        return False
    error = OSError(code, os.strerror(code))
    raise _refusal(target, error) from error


def _hard_link(staged: Path, target: Path) -> bool:
    """Link ``staged`` as ``target``, never replacing it; False without hard links."""
    try:
        os.link(staged, target)
    except OSError as exc:
        if exc.errno in _NO_HARD_LINKS:
            return False
        raise
    return True


def _publish_portable(staged: Path, target: Path) -> None:
    """Publish without ``renameat2``, see :func:`_atomic_publish`."""
    try:
        if not _WINDOWS and staged.is_file() and _hard_link(staged, target):
            return  # the staged name goes away with the caller's staging directory
        if os.path.lexists(target):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target))
        os.rename(staged, target)
    except FileExistsError:
        raise
    except OSError as exc:
        raise _refusal(target, exc) from exc


def _atomic_publish(staged: Path, target: Path) -> None:
    """
    Move a staged version directory or file to ``target`` without replacing it.

    The entry appears complete in one step or not at all, so an interrupted
    publication leaves at most its staging in ``.incoming``. Linux publishes
    by ``renameat2(RENAME_NOREPLACE)``. Without it (Windows, macOS, a C
    library or file system without the flag, e.g. NFS) only operations that
    never replace an existing entry are used:

    * Windows: ``os.rename`` (``MoveFileExW`` without replacement);
    * a directory: ``os.rename`` after checking that ``target`` does not
      exist; a concurrent publication of the same target still fails,
      because no system renames a directory onto a non-empty one and a
      version directory is never empty;
    * a file: ``os.link``, or on a file system without hard links (e.g. SMB,
      FAT) ``os.rename`` after the same check — only there two simultaneous
      publications of one file name may both succeed, the later one in
      place of the earlier.

    Parameters
    ----------
    staged : pathlib.Path
        Complete directory or file in the store's ``.incoming``.
    target : pathlib.Path
        New version directory or observation file; its parent exists.

    Raises
    ------
    FileExistsError
        If ``target`` exists.
    IMGWStoreConflictError
        If the system refuses the rename for another reason.
    """
    if not _rename_noreplace(staged, target):
        _publish_portable(staged, target)
    _fsync_dir(target.parent)


def _safe_root(root: PathArg) -> Path:
    supplied = Path(root).expanduser().absolute()
    if ".." in supplied.parts:
        raise IMGWValidationError("Ścieżka magazynu nie może zawierać '..'")
    for part in (supplied, *supplied.parents):
        if part.is_symlink():
            raise IMGWStoreError(
                f"Dowiązanie symboliczne w ścieżce magazynu: {part}",
                code="validation_error",
            )
    return supplied


def _marker(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema = payload["schema"]
        if not isinstance(schema, str):
            raise ValueError("nieprawidłowy schemat")
        return schema
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise IMGWStoreError(f"Nieczytelny znacznik: {path}") from exc


def _kartograf_project(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        output = payload.get("output_dir")
        if not isinstance(output, str) or not output:
            raise ValueError("brak output_dir")
        return (path.parent / output).resolve()
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise IMGWStoreError(f"Nieczytelny manifest Kartografa: {path}") from exc


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _check_kartograf(path: Path) -> None:
    # Parent markers need not be at the requested root; an unrelated project manifest
    # beside the store is harmless unless its output points at the store. Below an
    # existing store root only foreign trees are probed: the store's own managed
    # trees (_MANAGED_TREES) are skipped so their sidecars are never parsed here.
    for ancestor in (path, *path.parents):
        if ancestor != path and (ancestor / _MARKER).exists():
            raise IMGWStoreConflictError(
                f"Magazyn IMGW jest już przodkiem katalogu: {ancestor}",
                details=_PATH_CONFLICT,
            )
        output = _kartograf_project(ancestor / "kartograf-project.json")
        if output is not None and _overlaps(path, output):
            raise IMGWStoreConflictError(
                f"Ścieżka koliduje z magazynem Kartografa: {output}",
                details=_PATH_CONFLICT,
            )
        versions = ancestor / "versions"
        if versions.is_dir() and _has_kartograf_meta(versions):
            raise IMGWStoreConflictError(
                f"Ścieżka koliduje z wersjami Kartografa: {versions}",
                details=_PATH_CONFLICT,
            )
    if path.is_dir():
        store_root = (path / _MARKER).exists()
        for base, dirs, files in os.walk(path, followlinks=False):
            folder = Path(base)
            if folder != path and _MARKER in files:
                _marker(folder / _MARKER)
                raise IMGWStoreConflictError(
                    f"Zagnieżdżony magazyn IMGW: {folder}", details=_PATH_CONFLICT
                )
            if "kartograf-project.json" in files:
                output = _kartograf_project(folder / "kartograf-project.json")
                if output is not None and _overlaps(path, output):
                    raise IMGWStoreConflictError(
                        f"Ścieżka koliduje z magazynem Kartografa: {output}",
                        details=_PATH_CONFLICT,
                    )
            if folder.name == "versions" and _has_kartograf_meta(folder):
                raise IMGWStoreConflictError(
                    f"Ścieżka koliduje z wersjami Kartografa: {folder}",
                    details=_PATH_CONFLICT,
                )
            dirs[:] = [
                name
                for name in dirs
                if not (folder / name).is_symlink()
                and not (store_root and folder == path and name in _MANAGED_TREES)
            ]


def _has_kartograf_meta(versions: Path) -> bool:
    for sidecar in versions.rglob("*.meta.json"):
        if sidecar.is_symlink():
            raise IMGWStoreConflictError(
                f"Dowiązanie w wersjach: {sidecar}", details=_PATH_CONFLICT
            )
        if _marker(sidecar) == "kartograf-meta/1":
            return True
    return False


def _validate_slot(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if (
        not parts
        or any(p in (".", "..", "") for p in parts)
        or relative.startswith("/")
        or "\\" in relative
    ):
        raise IMGWValidationError(f"Niebezpieczna ścieżka archiwum: {relative}")
    result = root.joinpath(*parts)
    for path in (result, *result.parents):
        if path == root.parent:
            break
        if path.is_symlink():
            raise IMGWStoreError(
                f"Dowiązanie w ścieżce slotu: {path}", code="validation_error"
            )
    return result


def init_store(root: PathArg, /, *, created_at: datetime | None = None) -> StoreHandle:
    """
    Create a new store marker only in an empty, non-conflicting directory.

    The marker ``imgw-store.json`` is created exclusively, so it never
    replaces a competing marker (also on file systems without hard links,
    e.g. SMB or FAT, and on Windows), then written and flushed to disk. If
    the root already holds a marker (including one created concurrently),
    the existing store is opened instead; a marker that another call has
    just created is waited for up to a second.

    Parameters
    ----------
    root : str or os.PathLike
        Store root directory; created (with parents) if it does not exist.
    created_at : datetime.datetime or None, optional
        Timezone-aware creation time recorded in the marker as UTC; omitted
        from the marker when ``None``.

    Returns
    -------
    StoreHandle
        Handle of the created or already existing store.

    Raises
    ------
    IMGWValidationError
        If the root path contains ``..`` or ``created_at`` is naive.
    IMGWStoreError
        If the root path contains a symbolic link (code ``validation_error``),
        a relevant marker is unreadable or the existing marker is not a
        supported store (code ``store_unavailable``).
    IMGWStoreConflictError
        If the directory is not empty and has no marker, it is nested in or
        contains another IMGW store, or it overlaps a Kartograf store; code
        ``conflict``.
    """
    path = _safe_root(root)
    _check_kartograf(path)
    marker = path / _MARKER
    if marker.exists():
        return _open_marked(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise IMGWStoreConflictError(
            f"Katalog nie jest pustym magazynem IMGW: {path}", details=_PATH_CONFLICT
        )
    path.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {
        "schema": "imgw-store/1",
        "created_by": f"imgwtools {__version__}",
    }
    if created_at is not None:
        payload["created_at"] = _utc(created_at)
    try:
        stream = marker.open("xb")  # exclusive: never replaces a competing marker
    except FileExistsError:
        return _open_marked(path)
    try:
        with stream:
            stream.write(_canonical(payload))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        marker.unlink(missing_ok=True)  # no incomplete marker of this call remains
        raise
    _fsync_dir(path)
    return StoreHandle(path, "imgw-store/1")


def _open_marked(path: Path) -> StoreHandle:
    """
    Open a store whose marker exists, waiting for a marker being written.

    ``init_store`` writes the marker right after creating it exclusively, so
    a concurrent call may find it empty for a moment: an unreadable marker is
    read again for up to ``_MARKER_WAIT`` seconds before it is an error.
    """
    deadline = time.monotonic() + _MARKER_WAIT
    while True:
        try:
            _marker(path / _MARKER)
        except IMGWStoreError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
        else:
            return open_store(path)


def open_store(root: PathArg, /) -> StoreHandle:
    """
    Open a known store without creating files or changing its contents.

    Parameters
    ----------
    root : str or os.PathLike
        Store root directory containing an ``imgw-store/1`` marker.

    Returns
    -------
    StoreHandle
        Handle of the opened store.

    Raises
    ------
    IMGWValidationError
        If the root path contains ``..``.
    IMGWStoreError
        If the root path contains a symbolic link or the marker is missing,
        unreadable or of an unsupported schema.
    """
    path = _safe_root(root)
    if _marker(path / _MARKER) != "imgw-store/1":
        raise IMGWStoreError(
            f"Brak znacznika lub nieobsługiwany magazyn IMGW: {path}",
            details={"reason": "unsupported"},
        )
    return StoreHandle(path, "imgw-store/1")


def _utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise IMGWValidationError("Data musi mieć strefę czasową")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _remove_stale(directory: Path) -> bool:
    """
    Remove an abandoned staging directory, tolerating a concurrent removal.

    Parameters
    ----------
    directory : pathlib.Path
        Staging directory inside ``.incoming``.

    Returns
    -------
    bool
        ``True`` if this call removed the directory, ``False`` if another
        writer removed it first.
    """
    vanished = False

    def ignore_missing(
        function: Callable[..., object], name: str, exc: BaseException
    ) -> None:
        nonlocal vanished
        if not isinstance(exc, FileNotFoundError):
            raise exc
        if Path(name) == directory:
            vanished = True

    shutil.rmtree(directory, onexc=ignore_missing)
    return not vanished


def _cleanup(incoming: Path, *, on_notice: NoticeHook | None = None) -> None:
    """
    Remove staging directories abandoned in ``.incoming`` for over 24 hours.

    Directories removed concurrently by another writer are skipped silently.

    Parameters
    ----------
    incoming : pathlib.Path
        The store's ``.incoming`` directory.
    on_notice : NoticeHook or None, optional
        Called with a ``leftover_incoming`` warning for every directory this
        call removed.
    """
    if not incoming.exists():
        return
    cutoff = time.time() - 24 * 60 * 60
    for child in incoming.iterdir():
        try:
            if (
                child.is_symlink()
                or not child.is_dir()
                or child.stat().st_mtime >= cutoff
            ):
                continue
        except FileNotFoundError:
            continue  # removed concurrently by another writer
        if _remove_stale(child) and on_notice is not None:
            on_notice(
                Notice(
                    "warning",
                    "leftover_incoming",
                    "Usunięto porzucony staging starszy niż 24 h: "
                    f".incoming/{child.name}",
                )
            )


def _existing(
    slot: Path, name: str, *, archive: bool = False, skip: Collection[str] = ()
) -> list[tuple[Path, dict[str, Any]]]:
    """
    Every version of a slot with its sidecar, verified by SHA-256.

    Parameters
    ----------
    slot : pathlib.Path
        Slot directory.
    name : str
        Main file name of the slot's versions.
    archive : bool, optional
        Whether ``slot`` is an archive slot: its observation register
        ``observations/`` is then not a version.
    skip : collection of str, optional
        Names of child directories that are not versions of the slot, e.g.
        the catalogs of other providers inside the IMGW-PIB catalog slot.

    Returns
    -------
    list of tuple
        ``(main file, sidecar)`` of every version in name order.

    Raises
    ------
    IMGWStoreConflictError
        If an element of the slot is not a readable, consistent version.
    """
    if not slot.exists():
        return []
    entries = []
    for directory in sorted(slot.iterdir()):
        if (archive and _is_register(directory)) or (
            directory.name in skip and directory.is_dir() and not directory.is_symlink()
        ):
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise IMGWStoreConflictError(f"Nieprawidłowa wersja archiwum: {directory}")
        meta_path = directory / f"{name}.meta.json"
        try:
            source = directory / name
            if source.is_symlink() or meta_path.is_symlink():
                raise ValueError("dowiązanie w wersji")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256()
            with source.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if (
                meta["schema"] != "imgw-meta/1"
                or digest.hexdigest() != meta["sha256"]
                or not isinstance(meta["extra"]["version"]["label"], str)
            ):
                raise ValueError("niespójna suma, schemat lub etykieta")
        except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
            raise IMGWStoreConflictError(
                f"Uszkodzona wersja archiwum: {directory}"
            ) from exc
        except OSError as exc:
            raise io_error(exc) from exc
        entries.append((directory / name, meta))
    return entries


def _archive_signal(version: Path, meta: dict[str, Any]) -> tuple[Any, Any]:
    """
    Return the HTTP signal recorded in an archive version's sidecar.

    Parameters
    ----------
    version : pathlib.Path
        Archive version directory (used in the error message).
    meta : dict
        Sidecar already validated by ``_existing``.

    Returns
    -------
    tuple
        ``(etag, last_modified)`` from ``extra.http``.

    Raises
    ------
    IMGWStoreConflictError
        If the sidecar has no ``extra.http`` object.
    """
    http = meta["extra"].get("http")
    if not isinstance(http, dict):
        raise IMGWStoreConflictError(f"Uszkodzona wersja archiwum: {version}")
    return http.get("etag"), http.get("last_modified")


def _is_register(path: Path) -> bool:
    """Whether ``path`` is the observation register directory of an archive slot."""
    return path.name == _OBSERVATIONS and path.is_dir() and not path.is_symlink()


def _is_seen_at(value: object) -> bool:
    """Whether ``value`` is a UTC time with whole seconds, ``YYYY-MM-DDTHH:MM:SSZ``."""
    if not isinstance(value, str) or not _SEEN_AT.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _observation_name(observation: Observation) -> str:
    """
    File name ``<YYYY-MM-DD>_<sha8>.json`` of an observation (ADR-003 D18).

    The date is the UTC day of ``seen_at``; ``<sha8>`` starts the SHA-256 of
    the signal ``{"etag", "last_modified", "size_bytes", "url"}`` written
    with sorted keys, without whitespace and without escaping non-ASCII
    characters (the JCS form of this flat object).

    Parameters
    ----------
    observation : Observation
        Observation with a valid ``seen_at``.

    Returns
    -------
    str
        File name inside ``observations/``.
    """
    signal = json.dumps(
        {
            "etag": observation.etag,
            "last_modified": observation.last_modified,
            "size_bytes": observation.size_bytes,
            "url": observation.url,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(signal.encode("utf-8")).hexdigest()[:8]
    return f"{observation.seen_at[:10]}_{digest}.json"


def _publish_observation(
    root: Path,
    *,
    slot: str,
    observation: Observation,
    cancel: Cancel | None = None,
) -> Path:
    """
    Publish an observation into ``<slot>/observations/`` without replacing a file.

    The canonical ``imgw-observation/1`` document is staged in a unique
    ``.incoming`` directory and moved by a single no-replace rename; the
    register directory is created when needed. A file of the same name (the
    same signal seen on the same day) is kept unchanged and returned.

    Parameters
    ----------
    root : pathlib.Path
        Store root.
    slot : str
        Archive slot directory relative to ``root``, e.g.
        ``"archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024"``.
    observation : Observation
        Observed signal; ``seen_at`` must be ``YYYY-MM-DDTHH:MM:SSZ``.
    cancel : Cancel or None, optional
        Polled before the register is touched; returning ``True`` aborts the
        write without leaving a file.

    Returns
    -------
    pathlib.Path
        Published or already existing observation file.

    Raises
    ------
    IMGWValidationError
        If ``seen_at`` is not a UTC time with whole seconds or the slot path
        is unsafe.
    IMGWStoreError
        If a path component is a symbolic link (code ``validation_error``).
    IMGWStoreConflictError
        If ``observations`` or the target name is not a regular entry of its
        kind, or the system refuses the rename (e.g. no write permission).
    IMGWCancelledError
        If ``cancel`` returns ``True`` before publication.
    """
    if not _is_seen_at(observation.seen_at):
        raise IMGWValidationError(
            f"Czas obserwacji musi mieć postać RRRR-MM-DDTGG:MM:SSZ: {observation.seen_at!r}"
        )
    name = _observation_name(observation)
    register = _validate_slot(root, f"{slot}/{_OBSERVATIONS}")
    target = _validate_slot(root, f"{slot}/{_OBSERVATIONS}/{name}")
    incoming = root / ".incoming"
    incoming.mkdir(exist_ok=True)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        _write_json(
            staging / name,
            {
                "schema": OBSERVATION_SCHEMA,
                "producer": "imgwtools",
                "producer_version": __version__,
                **asdict(observation),
            },
        )
        _fsync_dir(staging)
        if cancel is not None and cancel():
            raise IMGWCancelledError("Anulowano zapis obserwacji")
        try:
            register.mkdir()
        except FileExistsError:
            if not _is_register(register):
                raise IMGWStoreConflictError(
                    f"Rejestr obserwacji nie jest katalogiem: {register}"
                ) from None
        else:
            _fsync_dir(register.parent)
        try:
            _atomic_publish(staging / name, target)
        except FileExistsError:
            # The same signal on the same day is already recorded; keep that file.
            if target.is_symlink() or not target.is_file():
                raise IMGWStoreConflictError(
                    f"Kolizja pliku obserwacji: {target}"
                ) from None
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _content_of(data: bytes, *, form: str, filename: str) -> str:
    """``content_sha256`` of downloaded bytes; a form error names the file."""
    try:
        return content_sha256(data, form=form)
    except IMGWDataError as exc:
        raise IMGWDataError(
            f"Plik {filename} nie spełnia formy treści {form}: {exc}"
        ) from exc


def _content_fields(
    same: list[tuple[Path, dict[str, Any], tuple[Any, Any]]],
    *,
    content: str | None,
    form: str | None,
) -> dict[str, str]:
    """
    ``content_sha256`` and ``content_form`` of a new version's sidecar.

    A relabeled copy keeps the fields of the stored version with the same
    bytes; otherwise the fields come from the dataset's form (none without
    a form, so IMGW-PIB sidecars keep their bytes).
    """
    for _, old_meta, _ in same:
        digest, old_form = old_meta.get("content_sha256"), old_meta.get("content_form")
        if isinstance(digest, str) and isinstance(old_form, str):
            return {"content_sha256": digest, "content_form": old_form}
    if content is None or form is None:
        return {}
    return {"content_sha256": content, "content_form": form}


def _content_unchanged(
    root: Path,
    *,
    descriptor: DatasetDescriptor,
    archive: ArchiveFile,
    response: DownloadResult,
    sha: str,
    content: str,
    slot_dir: str,
    now: datetime,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> VersionResult | None:
    """
    Decide on bytes no version of a slot has, by the canonical content (§3.1).

    The bytes are compared with the current version of the slot by the form
    recorded in that version. The same content gives ``"unchanged"`` without
    a version: a signal (URL, ETag, Last-Modified, size) other than the
    slot's reference signal is recorded once as an observation (ADR-003 D18),
    and the ``content_unchanged`` notice names the slot, both SHA-256 sums,
    the common ``content_sha256`` and the observation.

    Parameters
    ----------
    root : pathlib.Path
        Store root.
    descriptor : DatasetDescriptor
        Dataset of the slot, with a canonical form.
    archive : ArchiveFile
        Downloaded file.
    response : DownloadResult
        Downloaded bytes and HTTP headers.
    sha : str
        SHA-256 of the downloaded bytes.
    content : str
        ``content_sha256`` of the bytes by the dataset's form.
    slot_dir : str
        Slot directory relative to ``root``.
    now : datetime
        Time of the download (UTC); its whole seconds become ``seen_at``.
    on_notice : NoticeHook or None
        Receives the ``content_unchanged`` notice.
    cancel : Cancel or None
        Polled before an observation is published.

    Returns
    -------
    VersionResult or None
        The ``"unchanged"`` result naming the current version, or None when
        a new version is due: other content, or a current version without
        content fields or with a form this library does not know.
    """
    # The reader imports this module, so it is imported at call time.
    from imgwtools.store.reader import _archive_slot, _reference_signal

    slot = _archive_slot(archive.server_path)
    reference = None if slot is None else _reference_signal(root, slot=slot)
    if (
        reference is None
        or reference.version.meta is None
        or reference.version.version is None
    ):
        return None
    meta = reference.version.meta
    form = meta.content_form
    if meta.content_sha256 is None or form is None or form not in CONTENT_FORMS:
        return None
    if form != descriptor.content_form:
        content = _content_of(response.data, form=form, filename=archive.server_path)
    if content != meta.content_sha256:
        return None
    current = reference.version.version
    seen = (response.url, response.etag, response.last_modified, len(response.data))
    if seen == (
        reference.url,
        reference.etag,
        reference.last_modified,
        reference.size_bytes,
    ):
        observation = reference.observation
    else:
        observation = _publish_observation(
            root,
            slot=slot_dir,
            observation=Observation(
                dataset=descriptor.key,
                seen_at=_utc(now.replace(microsecond=0)),
                url=response.url,
                last_modified=response.last_modified,
                etag=response.etag,
                size_bytes=len(response.data),
                sha256=sha,
                content_sha256=meta.content_sha256,
                content_form=form,
                same_content_as=current.parent.name,
            ),
            cancel=cancel,
        )
    if on_notice is not None:
        recorded = (
            observation.relative_to(root).as_posix()
            if observation is not None
            else "brak (sygnałem odniesienia jest bieżąca wersja)"
        )
        on_notice(
            Notice(
                "info",
                _CONTENT_CODE,
                f"Treść bez zmian w {slot}: pobrane bajty (SHA-256 {sha}) mają tę "
                f"samą treść kanoniczną {form} (content_sha256 "
                f"{meta.content_sha256}) co bieżąca wersja "
                f"{current.relative_to(root).as_posix()} (SHA-256 {meta.sha256}); "
                f"nowej wersji nie zapisano, obserwacja: {recorded}",
            )
        )
    label = cast(Mapping[str, object], meta.extra["version"])["label"]
    return VersionResult(
        "unchanged",
        current,
        meta.sha256,
        str(label),
        observed_sha256=sha,
        observation=observation,
    )


def write_archive(
    root: PathArg | StoreHandle,
    /,
    *,
    archive: ArchiveFile,
    response: DownloadResult,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> VersionResult:
    """
    Commit an archive and provenance together, without replacing existing versions.

    The original bytes and their ``*.meta.json`` sidecar are staged in
    ``.incoming`` and published as a whole version directory
    ``<label>_<sha8>`` by a single no-replace rename. The label is the UTC
    date of ``Last-Modified`` (or of the download when absent); identical
    bytes with a different HTTP signal on the same day get a stable
    ``+<8 hex>`` suffix. Country, provider and license of the sidecar come
    from the provider registry.

    For a dataset with a canonical form (``DatasetDescriptor.content_form``,
    ADR-003 D17) the sidecar also records ``content_sha256`` and
    ``content_form``, and bytes that differ from every version but carry the
    canonical content of the current version give ``"unchanged"`` without a
    version: a new source signal is recorded once in the slot's observation
    register ``observations/`` (ADR-003 D18).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    archive : ArchiveFile
        Archive descriptor; its ``server_path`` must lie in the dataset's
        server directory and end with ``.zip`` or ``.csv`` (IMGW-PIB) or
        ``.json`` or ``.csv`` (ČHMÚ).
    response : DownloadResult
        Downloaded bytes and HTTP headers (``ETag``, ``Last-Modified``).
    on_progress : ProgressHook or None, optional
        Called once with a ``created`` progress event after publication.
    on_notice : NoticeHook or None, optional
        Called with a ``leftover_incoming`` warning for every abandoned
        staging directory removed from ``.incoming``, with the
        ``license_terms`` notice of the provider after publication, and with
        the ``content_unchanged`` notice for other bytes of the same
        canonical content.
    cancel : Cancel or None, optional
        Polled before and after staging and before an observation is
        published; returning ``True`` aborts the write.

    Returns
    -------
    VersionResult
        ``status`` is ``"created"`` for new content, ``"relabeled"`` for
        already stored bytes with a new HTTP signal, or ``"unchanged"``
        when bytes and signal match an existing version or the bytes carry
        the canonical content of the current version (then ``path`` and
        ``sha256`` name the current version, ``observed_sha256`` the
        downloaded bytes and ``observation`` the recorded or reference
        observation).

    Raises
    ------
    IMGWValidationError
        If the dataset is unknown, the server path does not match the
        dataset or has a disallowed extension, the path is unsafe, or the
        ``Last-Modified`` header is invalid.
    IMGWDataError
        If the bytes of a dataset with a canonical form do not meet the form
        (nothing is written), or an observation of the current version is
        broken.
    IMGWStoreError
        If the root is not a supported store (code ``store_unavailable``) or a
        path contains a symbolic link (code ``validation_error``).
    IMGWStoreConflictError
        If the store overlaps another IMGW or a Kartograf store, an existing
        version in the slot is corrupted (including a sidecar without
        ``extra.http``), the version directory collides with different
        content, or the system refuses to publish the version (e.g. no write
        permission).
    IMGWCancelledError
        If ``cancel`` returns ``True`` before publication.
    """
    handle = open_store(root.root if isinstance(root, StoreHandle) else root)
    path = handle.root
    _check_kartograf(path)
    descriptor = get_dataset(archive.dataset)
    provider = get_provider(descriptor.provider)
    _validate_slot(path, f"archives/versions/{archive.server_path}")
    relative = PurePosixPath(archive.server_path)
    if descriptor.server_dir is None or not archive.server_path.startswith(
        descriptor.server_dir + "/"
    ):
        raise IMGWValidationError(f"Ścieżka nie odpowiada zbiorowi {archive.dataset}")
    if relative.suffix.lower() not in _SUFFIXES.get(provider.id, ()):
        raise IMGWValidationError(f"Niedozwolony typ archiwum: {relative}")
    slot_dir = f"archives/versions/{relative.parent.as_posix()}/{relative.stem}"
    slot = _validate_slot(path, slot_dir)
    filename = relative.name
    form = descriptor.content_form
    # A file that does not meet the dataset's form is rejected before any write.
    content = (
        None
        if form is None
        else _content_of(response.data, form=form, filename=archive.server_path)
    )
    if cancel is not None and cancel():
        raise IMGWCancelledError("Anulowano zapis archiwum")
    incoming = path / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming, on_notice=on_notice)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        digest = hashlib.sha256()
        with (staging / filename).open("xb") as stream:
            # Single pass through response bytes, bounded write chunks.
            view = memoryview(response.data)
            for start in range(0, len(view), 1024 * 1024):
                chunk = view[start : start + 1024 * 1024]
                stream.write(chunk)
                digest.update(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        sha = digest.hexdigest()
        now = datetime.now(UTC)
        stamp = _utc(now)
        if response.last_modified:
            try:
                published = parsedate_to_datetime(response.last_modified).astimezone(
                    UTC
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise IMGWValidationError(
                    "Nieprawidłowy nagłówek Last-Modified"
                ) from exc
            label = published.date().isoformat()
            label_source = "last_modified"
        else:
            label = now.date().isoformat()
            label_source = "downloaded"
        signal = (response.etag, response.last_modified)
        # Scan every stored copy of these bytes for an identical signal before
        # deciding on a relabel, so an older signal reappearing stays unchanged.
        versions = [
            (old_file, old_meta, _archive_signal(old_file.parent, old_meta))
            for old_file, old_meta in _existing(slot, filename, archive=True)
        ]
        same = [entry for entry in versions if entry[1]["sha256"] == sha]
        for old_file, old_meta, old_signal in same:
            if not any(signal) or signal == old_signal:
                old_version = old_meta["extra"]["version"]["label"]
                return VersionResult("unchanged", old_file, sha, old_version)
        if versions and not same and content is not None:
            kept = _content_unchanged(
                path,
                descriptor=descriptor,
                archive=archive,
                response=response,
                sha=sha,
                content=content,
                slot_dir=slot_dir,
                now=now,
                on_notice=on_notice,
                cancel=cancel,
            )
            if kept is not None:
                return kept
        matching = bool(same)
        if any(
            old_meta["extra"]["version"]["label"] == label
            or old_meta["extra"]["version"]["label"].startswith(label + "+")
            for _, old_meta, _ in same
        ):
            label += "+" + hashlib.sha256(_canonical(signal)).hexdigest()[:8]
        if cancel is not None and cancel():
            raise IMGWCancelledError("Anulowano zapis archiwum")
        request: dict[str, object] = {
            "server_path": archive.server_path,
            "year": archive.year,
            "month": archive.month,
        }
        period: dict[str, object] = {
            "year": archive.year,
            "month": archive.month,
            "param": archive.param,
            "year_type": archive.year_type,
            "start": archive.period_start.isoformat() if archive.period_start else None,
            "end": archive.period_end.isoformat() if archive.period_end else None,
        }
        if provider.id != _COUNTRY_LAYOUT:
            request.update(station_code=archive.station_code, param=archive.param)
            period["station_code"] = archive.station_code
        meta = {
            "schema": "imgw-meta/1",
            "producer": "imgwtools",
            "producer_version": __version__,
            "dataset": archive.dataset,
            "country": provider.country,
            "provider": provider.id,
            "request": request,
            "license": _license_document(provider.license),
            "downloaded_at": stamp,
            "sha256": sha,
            "size_bytes": len(response.data),
            **_content_fields(same, content=content, form=form),
            "extra": {
                "version": {"label": label, "label_source": label_source},
                "period": period,
                "http": {
                    "url": response.url,
                    "etag": response.etag,
                    "last_modified": response.last_modified,
                    "content_length": response.content_length,
                },
            },
        }
        _write_json(staging / f"{filename}.meta.json", meta)
        _fsync_dir(staging)
        slot.mkdir(parents=True, exist_ok=True)
        _validate_slot(path, f"{slot_dir}/{label}_{sha[:8]}")
        target = slot / f"{label}_{sha[:8]}"
        try:
            _atomic_publish(staging, target)
        except FileExistsError as exc:
            for old_file, old_meta in _existing(slot, filename, archive=True):
                if old_file.parent == target and old_meta["sha256"] == sha:
                    if signal == _archive_signal(old_file.parent, old_meta):
                        return VersionResult("unchanged", old_file, sha, label)
            raise IMGWStoreConflictError(f"Kolizja katalogu wersji: {target}") from exc
        if on_progress is not None:
            on_progress(
                Progress(1, 1, "archive", "created", f"Zapisano archiwum {filename}")
            )
        if on_notice is not None:
            on_notice(
                Notice(
                    "info",
                    _ATTRIBUTION_CODE,
                    f"{provider.license.attribution}. {provider.notice}",
                )
            )
        return VersionResult(
            "relabeled" if matching else "created", target / filename, sha, label
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)
