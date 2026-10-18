"""Immutable archive publication in the versioned IMGW store."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import socket
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any

from imgwtools._version import __version__
from imgwtools.datasets import ArchiveFile, get_dataset
from imgwtools.exceptions import (
    IMGWStoreConflictError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    Progress,
    ProgressHook,
    StoreHandle,
    VersionResult,
)

_MARKER = "imgw-store.json"
_ATTRIBUTION_CODE = "license_terms"
# Trees directly under a store root written only by IMGWTools; the reader reports
# anything unexpected there, so the Kartograf probe does not walk into them.
_MANAGED_TREES = frozenset({"archives", "series", "stations", "pmaxtp", ".incoming"})


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
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_publish(staged_dir: Path, target_dir: Path) -> None:
    """Rename a whole directory, refusing replacement even of an empty directory."""
    if not sys.platform.startswith("linux"):
        raise IMGWStoreConflictError(
            "System plików nie zapewnia atomowego zapisu bez zastąpienia celu"
        )
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise IMGWStoreConflictError(
            "Brak atomowego renameat2 bez zastępowania wersji"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    source = os.fsencode(staged_dir)
    destination = os.fsencode(target_dir)
    if renameat2(-100, source, -100, destination, 1) != 0:  # RENAME_NOREPLACE
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, os.strerror(code), str(target_dir))
        raise IMGWStoreConflictError(
            f"Nie można atomowo opublikować wersji: {os.strerror(code)}"
        )
    _fsync_dir(target_dir.parent)


def _safe_root(root: PathArg) -> Path:
    supplied = Path(root).expanduser().absolute()
    if ".." in supplied.parts:
        raise IMGWValidationError("Ścieżka magazynu nie może zawierać '..'")
    for part in (supplied, *supplied.parents):
        if part.is_symlink():
            raise IMGWStoreError(f"Dowiązanie symboliczne w ścieżce magazynu: {part}")
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
            raise IMGWStoreError(
                f"Magazyn IMGW jest już przodkiem katalogu: {ancestor}"
            )
        output = _kartograf_project(ancestor / "kartograf-project.json")
        if output is not None and _overlaps(path, output):
            raise IMGWStoreError(f"Ścieżka koliduje z magazynem Kartografa: {output}")
        versions = ancestor / "versions"
        if versions.is_dir() and _has_kartograf_meta(versions):
            raise IMGWStoreError(f"Ścieżka koliduje z wersjami Kartografa: {versions}")
    if path.is_dir():
        store_root = (path / _MARKER).exists()
        for base, dirs, files in os.walk(path, followlinks=False):
            folder = Path(base)
            if folder != path and _MARKER in files:
                _marker(folder / _MARKER)
                raise IMGWStoreError(f"Zagnieżdżony magazyn IMGW: {folder}")
            if "kartograf-project.json" in files:
                output = _kartograf_project(folder / "kartograf-project.json")
                if output is not None and _overlaps(path, output):
                    raise IMGWStoreError(
                        f"Ścieżka koliduje z magazynem Kartografa: {output}"
                    )
            if folder.name == "versions" and _has_kartograf_meta(folder):
                raise IMGWStoreError(
                    f"Ścieżka koliduje z wersjami Kartografa: {folder}"
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
            raise IMGWStoreError(f"Dowiązanie w wersjach: {sidecar}")
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
            raise IMGWStoreError(f"Dowiązanie w ścieżce slotu: {path}")
    return result


def init_store(root: PathArg, /, *, created_at: datetime | None = None) -> StoreHandle:
    """
    Create a new store marker only in an empty, non-conflicting directory.

    The marker ``imgw-store.json`` is published atomically and never replaces
    a competing marker. If the root already holds a marker (including one
    created concurrently), the existing store is opened instead.

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
        If the root path contains a symbolic link, the directory is not empty
        and has no marker, it overlaps another IMGW store or a Kartograf
        store, a relevant marker is unreadable, the existing marker is not
        a supported store, or the file system cannot create the hard link
        used to publish the marker atomically (e.g. SMB, FAT).
    """
    path = _safe_root(root)
    _check_kartograf(path)
    marker = path / _MARKER
    if marker.exists():
        return open_store(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise IMGWStoreError(f"Katalog nie jest pustym magazynem IMGW: {path}")
    path.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {
        "schema": "imgw-store/1",
        "created_by": f"imgwtools {__version__}",
    }
    if created_at is not None:
        payload["created_at"] = _utc(created_at)
    temporary = path / f".{_MARKER}.{uuid.uuid4().hex}.tmp"
    try:
        _write_json(temporary, payload)
        try:
            os.link(
                temporary, marker
            )  # exclusive publication; never replace a competing marker
        except FileExistsError:
            return open_store(path)
        except OSError as exc:
            raise IMGWStoreError(
                "System plików nie obsługuje atomowego zapisu znacznika magazynu "
                f"(dowiązanie twarde): {path} ({exc.strerror})"
            ) from exc
        _fsync_dir(path)
    finally:
        temporary.unlink(missing_ok=True)
    return StoreHandle(path, "imgw-store/1")


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
        raise IMGWStoreError(f"Brak znacznika lub nieobsługiwany magazyn IMGW: {path}")
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


def _existing(slot: Path, name: str) -> list[tuple[Path, dict[str, Any]]]:
    if not slot.exists():
        return []
    entries = []
    for directory in sorted(slot.iterdir()):
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
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IMGWStoreConflictError(
                f"Uszkodzona wersja archiwum: {directory}"
            ) from exc
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
    content with a different HTTP signal on the same day gets a stable
    ``+<8 hex>`` suffix.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    archive : ArchiveFile
        Archive descriptor; its ``server_path`` must lie in the dataset's
        server directory and end with ``.zip`` or ``.csv``.
    response : DownloadResult
        Downloaded bytes and HTTP headers (``ETag``, ``Last-Modified``).
    on_progress : ProgressHook or None, optional
        Called once with a ``created`` progress event after publication.
    on_notice : NoticeHook or None, optional
        Called with a ``leftover_incoming`` warning for every abandoned
        staging directory removed from ``.incoming`` and with the
        ``license_terms`` notice after publication.
    cancel : Cancel or None, optional
        Polled before and after staging; returning ``True`` aborts the write.

    Returns
    -------
    VersionResult
        ``status`` is ``"created"`` for new content, ``"relabeled"`` for
        already stored content with a new HTTP signal, or ``"unchanged"``
        when content and signal match an existing version.

    Raises
    ------
    IMGWValidationError
        If the dataset is unknown, the server path does not match the
        dataset or has a disallowed extension, the path is unsafe, or the
        ``Last-Modified`` header is invalid.
    IMGWStoreError
        If the root is not a supported store, a path contains a symbolic
        link, the store overlaps a Kartograf store, or the write is
        cancelled.
    IMGWStoreConflictError
        If an existing version in the slot is corrupted (including a sidecar
        without ``extra.http``), the version directory collides with
        different content, or the file system cannot publish atomically
        without replacement.
    """
    handle = open_store(root.root if isinstance(root, StoreHandle) else root)
    path = handle.root
    _check_kartograf(path)
    descriptor = get_dataset(archive.dataset)
    _validate_slot(path, f"archives/versions/{archive.server_path}")
    relative = PurePosixPath(archive.server_path)
    if descriptor.server_dir is None or not archive.server_path.startswith(
        descriptor.server_dir + "/"
    ):
        raise IMGWValidationError(f"Ścieżka nie odpowiada zbiorowi {archive.dataset}")
    if relative.suffix.lower() not in (".zip", ".csv"):
        raise IMGWValidationError(f"Niedozwolony typ archiwum: {relative}")
    slot = _validate_slot(
        path, f"archives/versions/{relative.parent.as_posix()}/{relative.stem}"
    )
    if cancel is not None and cancel():
        raise IMGWStoreError("Anulowano zapis archiwum")
    incoming = path / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming, on_notice=on_notice)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    staging.mkdir()
    filename = relative.name
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
        same = [
            (old_file, old_meta, _archive_signal(old_file.parent, old_meta))
            for old_file, old_meta in _existing(slot, filename)
        ]
        same = [entry for entry in same if entry[1]["sha256"] == sha]
        for old_file, old_meta, old_signal in same:
            if not any(signal) or signal == old_signal:
                old_version = old_meta["extra"]["version"]["label"]
                return VersionResult("unchanged", old_file, sha, old_version)
        matching = bool(same)
        if any(
            old_meta["extra"]["version"]["label"] == label
            or old_meta["extra"]["version"]["label"].startswith(label + "+")
            for _, old_meta, _ in same
        ):
            label += "+" + hashlib.sha256(_canonical(signal)).hexdigest()[:8]
        if cancel is not None and cancel():
            raise IMGWStoreError("Anulowano zapis archiwum")
        meta = {
            "schema": "imgw-meta/1",
            "producer": "imgwtools",
            "producer_version": __version__,
            "dataset": archive.dataset,
            "country": "PL",
            "provider": "IMGW-PIB",
            "request": {
                "server_path": archive.server_path,
                "year": archive.year,
                "month": archive.month,
            },
            "license": asdict(descriptor.license),
            "downloaded_at": stamp,
            "sha256": sha,
            "size_bytes": len(response.data),
            "extra": {
                "version": {"label": label, "label_source": label_source},
                "period": {
                    "year": archive.year,
                    "month": archive.month,
                    "param": archive.param,
                    "year_type": archive.year_type,
                    "start": archive.period_start.isoformat()
                    if archive.period_start
                    else None,
                    "end": archive.period_end.isoformat()
                    if archive.period_end
                    else None,
                },
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
        _validate_slot(
            path,
            f"archives/versions/{relative.parent.as_posix()}/{relative.stem}/{label}_{sha[:8]}",
        )
        target = slot / f"{label}_{sha[:8]}"
        try:
            _atomic_publish(staging, target)
        except FileExistsError as exc:
            for old_file, old_meta in _existing(slot, filename):
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
                    f"{descriptor.license.attribution}. Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.",
                )
            )
        return VersionResult(
            "relabeled" if matching else "created", target / filename, sha, label
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)
