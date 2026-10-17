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
_ATTRIBUTION_CODE = "warunki_licencji"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


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
        raise IMGWStoreConflictError("System plików nie zapewnia atomowego zapisu bez zastąpienia celu")
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise IMGWStoreConflictError("Brak atomowego renameat2 bez zastępowania wersji") from exc
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    source = os.fsencode(staged_dir)
    destination = os.fsencode(target_dir)
    if renameat2(-100, source, -100, destination, 1) != 0:  # RENAME_NOREPLACE
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, os.strerror(code), str(target_dir))
        raise IMGWStoreConflictError(f"Nie można atomowo opublikować wersji: {os.strerror(code)}")
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
    # beside the store is harmless unless its output points at the store.
    for ancestor in (path, *path.parents):
        if ancestor != path and (ancestor / _MARKER).exists():
            raise IMGWStoreError(f"Magazyn IMGW jest już przodkiem katalogu: {ancestor}")
        output = _kartograf_project(ancestor / "kartograf-project.json")
        if output is not None and _overlaps(path, output):
            raise IMGWStoreError(f"Ścieżka koliduje z magazynem Kartografa: {output}")
        versions = ancestor / "versions"
        if versions.is_dir() and _has_kartograf_meta(versions):
            raise IMGWStoreError(f"Ścieżka koliduje z wersjami Kartografa: {versions}")
    if path.is_dir():
        for base, dirs, files in os.walk(path, followlinks=False):
            folder = Path(base)
            if folder != path and _MARKER in files:
                _marker(folder / _MARKER)
                raise IMGWStoreError(f"Zagnieżdżony magazyn IMGW: {folder}")
            if "kartograf-project.json" in files:
                output = _kartograf_project(folder / "kartograf-project.json")
                if output is not None and _overlaps(path, output):
                    raise IMGWStoreError(f"Ścieżka koliduje z magazynem Kartografa: {output}")
            if folder.name == "versions" and _has_kartograf_meta(folder):
                raise IMGWStoreError(f"Ścieżka koliduje z wersjami Kartografa: {folder}")
            dirs[:] = [name for name in dirs if not (folder / name).is_symlink()]


def _has_kartograf_meta(versions: Path) -> bool:
    for sidecar in versions.rglob("*.meta.json"):
        if sidecar.is_symlink():
            raise IMGWStoreError(f"Dowiązanie w wersjach: {sidecar}")
        if _marker(sidecar) == "kartograf-meta/1":
            return True
    return False


def _validate_slot(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if not parts or any(p in (".", "..", "") for p in parts) or relative.startswith("/") or "\\" in relative:
        raise IMGWValidationError(f"Niebezpieczna ścieżka archiwum: {relative}")
    result = root.joinpath(*parts)
    for path in (result, *result.parents):
        if path == root.parent:
            break
        if path.is_symlink():
            raise IMGWStoreError(f"Dowiązanie w ścieżce slotu: {path}")
    return result


def init_store(root: PathArg, /, *, created_at: datetime | None = None) -> StoreHandle:
    """Create a new store marker only in an empty, non-conflicting directory."""
    path = _safe_root(root)
    _check_kartograf(path)
    marker = path / _MARKER
    if marker.exists():
        return open_store(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise IMGWStoreError(f"Katalog nie jest pustym magazynem IMGW: {path}")
    path.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {"schema": "imgw-store/1", "created_by": f"imgwtools {__version__}"}
    if created_at is not None:
        payload["created_at"] = _utc(created_at)
    temporary = path / f".{_MARKER}.{uuid.uuid4().hex}.tmp"
    try:
        _write_json(temporary, payload)
        try:
            os.link(temporary, marker)  # exclusive publication; never replace a competing marker
        except FileExistsError:
            return open_store(path)
        _fsync_dir(path)
    finally:
        temporary.unlink(missing_ok=True)
    return StoreHandle(path, "imgw-store/1")


def open_store(root: PathArg, /) -> StoreHandle:
    """Open a known store without creating files or changing its contents."""
    path = _safe_root(root)
    if _marker(path / _MARKER) != "imgw-store/1":
        raise IMGWStoreError(f"Brak znacznika lub nieobsługiwany magazyn IMGW: {path}")
    return StoreHandle(path, "imgw-store/1")


def _utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise IMGWValidationError("Data musi mieć strefę czasową")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _cleanup(incoming: Path) -> None:
    if not incoming.exists():
        return
    cutoff = time.time() - 24 * 60 * 60
    for child in incoming.iterdir():
        if child.is_dir() and not child.is_symlink() and child.stat().st_mtime < cutoff:
            shutil.rmtree(child)


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
            if meta["schema"] != "imgw-meta/1" or digest.hexdigest() != meta["sha256"]:
                raise ValueError("niespójna suma lub schemat")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IMGWStoreConflictError(f"Uszkodzona wersja archiwum: {directory}") from exc
        entries.append((directory / name, meta))
    return entries


def write_archive(
    root: PathArg | StoreHandle, /, *, archive: ArchiveFile, response: DownloadResult,
    on_progress: ProgressHook | None = None, on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> VersionResult:
    """Commit an archive and provenance together, without replacing existing versions."""
    handle = open_store(root.root if isinstance(root, StoreHandle) else root)
    path = handle.root
    _check_kartograf(path)
    descriptor = get_dataset(archive.dataset)
    _validate_slot(path, f"archives/versions/{archive.server_path}")
    relative = PurePosixPath(archive.server_path)
    if descriptor.server_dir is None or not archive.server_path.startswith(descriptor.server_dir + "/"):
        raise IMGWValidationError(f"Ścieżka nie odpowiada zbiorowi {archive.dataset}")
    if relative.suffix.lower() not in (".zip", ".csv"):
        raise IMGWValidationError(f"Niedozwolony typ archiwum: {relative}")
    slot = _validate_slot(path, f"archives/versions/{relative.parent.as_posix()}/{relative.stem}")
    if cancel is not None and cancel():
        raise IMGWStoreError("Anulowano zapis archiwum")
    incoming = path / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    staging.mkdir()
    filename = relative.name
    try:
        digest = hashlib.sha256()
        with (staging / filename).open("xb") as stream:
            # Single pass through response bytes, bounded write chunks.
            view = memoryview(response.data)
            for start in range(0, len(view), 1024 * 1024):
                chunk = view[start:start + 1024 * 1024]
                stream.write(chunk)
                digest.update(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        sha = digest.hexdigest()
        now = datetime.now(UTC)
        stamp = _utc(now)
        if response.last_modified:
            try:
                published = parsedate_to_datetime(response.last_modified).astimezone(UTC)
            except (TypeError, ValueError, OverflowError) as exc:
                raise IMGWValidationError("Nieprawidłowy nagłówek Last-Modified") from exc
            label = published.date().isoformat()
            label_source = "last_modified"
        else:
            label = now.date().isoformat()
            label_source = "downloaded"
        signal = (response.etag, response.last_modified)
        matching = False
        for old_file, old_meta in _existing(slot, filename):
            if old_meta["sha256"] != sha:
                continue
            old_http = old_meta["extra"]["http"]
            if (not any(signal)) or signal == (old_http.get("etag"), old_http.get("last_modified")):
                old_version = old_meta["extra"]["version"]["label"]
                return VersionResult("unchanged", old_file, sha, old_version)
            matching = True
            if old_version := old_meta["extra"]["version"]["label"]:
                if old_version == label or old_version.startswith(label + "+"):
                    label += "+" + hashlib.sha256(_canonical(signal)).hexdigest()[:8]
                    break
        if cancel is not None and cancel():
            raise IMGWStoreError("Anulowano zapis archiwum")
        meta = {
            "schema": "imgw-meta/1", "producer": "imgwtools", "producer_version": __version__,
            "dataset": archive.dataset, "country": "PL", "provider": "IMGW-PIB",
            "request": {"server_path": archive.server_path, "year": archive.year, "month": archive.month},
            "license": asdict(descriptor.license), "downloaded_at": stamp,
            "sha256": sha, "size_bytes": len(response.data),
            "extra": {
                "version": {"label": label, "label_source": label_source},
                "period": {
                    "year": archive.year, "month": archive.month, "param": archive.param,
                    "year_type": archive.year_type,
                    "start": archive.period_start.isoformat() if archive.period_start else None,
                    "end": archive.period_end.isoformat() if archive.period_end else None,
                },
                "http": {"url": response.url, "etag": response.etag,
                         "last_modified": response.last_modified, "content_length": response.content_length},
            },
        }
        _write_json(staging / f"{filename}.meta.json", meta)
        _fsync_dir(staging)
        slot.mkdir(parents=True, exist_ok=True)
        _validate_slot(path, f"archives/versions/{relative.parent.as_posix()}/{relative.stem}/{label}_{sha[:8]}")
        target = slot / f"{label}_{sha[:8]}"
        try:
            _atomic_publish(staging, target)
        except FileExistsError as exc:
            for old_file, old_meta in _existing(slot, filename):
                if old_file.parent == target and old_meta["sha256"] == sha:
                    old_http = old_meta["extra"]["http"]
                    if signal == (old_http.get("etag"), old_http.get("last_modified")):
                        return VersionResult("unchanged", old_file, sha, label)
            raise IMGWStoreConflictError(f"Kolizja katalogu wersji: {target}") from exc
        if on_progress is not None:
            on_progress(Progress(1, 1, "archive", "created", f"Zapisano archiwum {filename}"))
        if on_notice is not None:
            on_notice(Notice("info", _ATTRIBUTION_CODE, f"{descriptor.license.attribution}. Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości."))
        return VersionResult("relabeled" if matching else "created", target / filename, sha, label)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
