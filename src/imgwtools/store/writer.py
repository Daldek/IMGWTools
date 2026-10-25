"""Immutable archive publication in the versioned IMGW store."""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import shutil
import socket
import time
import uuid
from collections.abc import Callable, Collection, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

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
from imgwtools.messages import message, reason
from imgwtools.output import STORE_MARKERS, FileResult, store_below
from imgwtools.store.content import CONTENT_FORMS, content_sha256
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    Observation,
    PathArg,
    PlanAction,
    Progress,
    ProgressHook,
    StoreHandle,
    StorePlan,
    VersionResult,
)

_MARKER = "imgw-store.json"
_ATTRIBUTION_CODE = "license_terms"
_CONTENT_CODE = "content_unchanged"
# Trees directly under a store root written only by IMGWTools; the reader reports
# anything unexpected there, so the Kartograf probe does not walk into them.
_MANAGED_TREES = frozenset({"archives", "series", "stations", "pmaxtp", ".incoming"})
_NESTED = {"reason": "nested_store"}
_NOT_EMPTY = {"reason": "not_empty"}
# Server state kept in the default root: not store content (DEV-19.13).
_STATE_FILES = frozenset({"api_keys.json"})
# Trees whose presence is the layout of an IMGW store (without its staging directory).
_LAYOUT_TREES = frozenset({"archives", "series", "stations", "pmaxtp"})
OBSERVATION_SCHEMA = "imgw-observation/1"
# Observation register of an archive slot, beside its version directories.
_OBSERVATIONS = "observations"
_SEEN_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
# File types each provider publishes as archives.
_SUFFIXES = {"IMGW-PIB": (".zip", ".csv"), "CHMI": (".json", ".csv")}
# Provider whose archive sidecars keep the 3.0.0 layout: no station_code or
# param in request and no station_code in extra.period (the same bytes).
_COUNTRY_LAYOUT = "IMGW-PIB"


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


# os.link failures meaning "this file system cannot hard link" (as Kartograf D22).
_NO_HARDLINK = frozenset(
    {
        errno.EPERM,
        errno.EOPNOTSUPP,
        getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
        errno.EXDEV,
        errno.EMLINK,
    }
)


def _fsync_dir(path: Path) -> None:
    """
    ``fsync`` a directory entry where the system supports it.

    Windows cannot open a directory for ``fsync`` (NTFS journals its
    metadata) and some file systems refuse the call; both are skipped, as in
    Kartograf.
    """
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in (
            errno.EINVAL,
            errno.ENOTSUP,
            errno.EOPNOTSUPP,
            errno.EBADF,
        ):
            raise
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_file(
    path: Path, status: Literal["new", "unchanged", "relabeled"]
) -> FileResult:
    """
    The ``files[]`` entry of a stored version (DEV-19.19).

    The size and the SHA-256 are those the sidecar recorded when the file was
    written, so nothing is read or hashed again.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path of the version's main file.
    status : {"new", "unchanged", "relabeled"}
        The version status of the result.

    Returns
    -------
    FileResult
        ``path``, ``size_bytes``, ``sha256`` and ``status``.

    Raises
    ------
    IMGWDataError
        If the sidecar lacks the size or the hash.
    """
    sidecar = path.with_name(f"{path.name}.meta.json")
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        return FileResult(path, int(meta["size_bytes"]), str(meta["sha256"]), status)
    except OSError as exc:
        raise io_error(exc) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise IMGWDataError(
            message("writer.sidecar_without_size_or_hash", sidecar=sidecar)
        ) from exc


def _link(source: Path, target: Path) -> None:
    """
    Publish ``source`` under ``target`` by a hard link, never replacing an entry.

    Raises
    ------
    FileExistsError
        If ``target`` exists.
    IMGWStoreConflictError
        If the file system has no hard links (``details.reason`` ``not_atomic``).
    """
    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except (OSError, NotImplementedError) as exc:
        if isinstance(exc, NotImplementedError) or exc.errno in _NO_HARDLINK:
            raise IMGWStoreConflictError(
                message("writer.store_needs_file_system_hard", target=target),
                details={"reason": "not_atomic"},
            ) from exc
        raise


def _make_dir(path: Path, made: list[Path]) -> None:
    """Create ``path`` or accept an existing real directory; record what was created."""
    try:
        path.mkdir()
    except FileExistsError:
        if path.is_symlink() or not path.is_dir():
            raise FileExistsError(
                errno.EEXIST, os.strerror(errno.EEXIST), str(path)
            ) from None
    else:
        made.append(path)


def _publish_dir(staging: Path, target: Path, sidecar: str) -> None:
    """
    Publish a staged version into ``target`` by hard links, the sidecar last.

    Every staged file other than ``sidecar`` is linked first (``stations/``
    included); then ``sidecar``, the main file's ``*.meta.json``, commits the
    version: a version directory without it is not a version but an
    interrupted publication (the scan reports it as ``missing_sidecar``).
    ``os.link`` never replaces an entry, so concurrent writers of the same
    content end in one version, and a file already present with the same
    bytes is kept, which completes an interrupted publication. This is the
    publication model of Kartograf (its D18, D21, D22): it needs a file
    system with hard links (ext4, APFS, NTFS, SMB shares that support them;
    not FAT or exFAT), not an OS-specific no-replace rename.

    On failure (``KeyboardInterrupt`` included) no file is removed from
    ``target``: a concurrent writer of the same bytes may already have kept
    a data file linked here and committed its own sidecar. The linked data
    files stay as an interrupted publication that the next write of the
    same content completes; directories created by this call are removed
    only while empty. A linked sidecar is never removed (that version is
    committed with all its data files); an unlinked one stays in
    ``staging``, which the caller removes.

    Parameters
    ----------
    staging : pathlib.Path
        Private staging directory with every file of the version, flushed and
        fsynced.
    target : pathlib.Path
        Version directory ``<slot>/<label>_<sha8>``.
    sidecar : str
        Name of the main file's sidecar inside ``staging``.

    Raises
    ------
    FileExistsError
        If ``target`` is not a directory, already holds a committed sidecar,
        or holds other bytes under a staged name; the caller decides between
        an unchanged version and a collision.
    IMGWStoreConflictError
        If the file system has no hard links (``details.reason`` ``not_atomic``).
    """
    data = sorted(
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file() and path.relative_to(staging).as_posix() != sidecar
    )
    directories = sorted({(target / name).parent for name in data} | {target})
    committed = target / sidecar
    made: list[Path] = []
    try:
        if committed.exists() or committed.is_symlink():
            # A committed version is never extended (e.g. by a newer attachment).
            raise FileExistsError(
                errno.EEXIST, os.strerror(errno.EEXIST), str(committed)
            )
        for directory in directories:
            _make_dir(directory, made)
        for name in data:
            source, destination = staging / name, target / name
            try:
                _link(source, destination)
            except FileExistsError:
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or _sha256_file(destination) != _sha256_file(source)
                ):
                    raise
        for directory in directories:
            _fsync_dir(directory)
        _link(staging / sidecar, committed)
    except BaseException:
        # Linked files may already belong to another writer's committed version;
        # only directories created here go, and rmdir refuses non-empty ones.
        for directory in reversed(made):
            with contextlib.suppress(OSError):
                directory.rmdir()
        raise
    _fsync_dir(target)
    _fsync_dir(target.parent)


def _safe_root(root: PathArg) -> Path:
    supplied = Path(root).expanduser().absolute()
    if ".." in supplied.parts:
        raise IMGWValidationError(message("writer.store_path_must_not_contain"))
    for part in (supplied, *supplied.parents):
        if part.is_symlink():
            raise IMGWStoreError(
                message("writer.symbolic_link_store_path", part=part),
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
            raise ValueError("invalid schema")
        return schema
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise IMGWDataError(
            message("writer.unreadable_marker", path=path),
            details={"reason": "invalid_marker"},
        ) from exc


def _nested_problem(path: Path) -> str | None:
    """
    Say why a root would nest a store in another store (DEV-19.14), or None.

    The check looks at the marker file names of every tool (``STORE_MARKERS``),
    so it needs nothing from Kartograf: in the ancestors of the root, at the
    root (the marker of another tool) and below it, where the managed trees of
    this store are not entered.
    """
    for ancestor in path.parents:
        for name in STORE_MARKERS:
            if (ancestor / name).is_file():
                return message(
                    "writer.store_inside_another_store", ancestor=ancestor, marker=name
                )
    foreign = next(
        (name for name in STORE_MARKERS if name != _MARKER and (path / name).is_file()),
        None,
    )
    if foreign is not None:
        return message("writer.root_holds_another_store", path=path, marker=foreign)
    below = store_below(
        path, skip=_MANAGED_TREES if (path / _MARKER).is_file() else frozenset()
    )
    if below is not None:
        found = next(name for name in STORE_MARKERS if (below / name).is_file())
        return message("writer.store_below_the_root", folder=below, marker=found)
    return None


def _check_nested(path: Path) -> None:
    """Refuse a root that would nest a store in another store (DEV-19.14)."""
    problem = _nested_problem(path)
    if problem is not None:
        raise IMGWStoreConflictError(problem, details=_NESTED)


def _refusal(path: Path) -> tuple[Literal["nested_store", "not_empty"], str] | None:
    """
    Say why a write turns a root away with ``conflict``, or None (DEV-19.10).

    Two roots are refused: one that would nest a store in another store
    (``nested_store``) and one that holds other files and is no store
    (``not_empty``: no marker, no layout of a store, something else inside, or
    no directory at all). The layout of a store without its marker is no
    ``conflict`` (``store_unavailable``, ``no_marker``).

    Raises
    ------
    IMGWDataError
        If the marker of the root is unreadable.
    """
    problem = _nested_problem(path)
    if problem is not None:
        return "nested_store", problem
    if (
        _marker(path / _MARKER) is None
        and not _has_layout(path)
        and path.exists()
        and (not path.is_dir() or _foreign_content(path))
    ):
        return "not_empty", message("writer.directory_not_empty_imgw_store", path=path)
    return None


def refuse_root(root: PathArg | StoreHandle) -> Path:
    """
    Refuse a root that a write turns away with ``conflict`` (DEV-19.10, DEV-19.14).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.

    Returns
    -------
    pathlib.Path
        The absolute root.

    Raises
    ------
    IMGWValidationError
        If the root path contains ``..``.
    IMGWStoreError
        If the root path contains a symbolic link.
    IMGWDataError
        If the marker of the root is unreadable (``details.reason``
        ``invalid_marker``).
    IMGWStoreConflictError
        If the root nests a store (``details.reason`` ``nested_store``) or
        holds other files and is no store (``not_empty``).
    """
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    refusal = _refusal(path)
    if refusal is not None:
        raise IMGWStoreConflictError(refusal[1], details={"reason": refusal[0]})
    return path


def root_conflict_plan(command: str, root: PathArg | StoreHandle) -> StorePlan | None:
    """
    Plan the refusal of a root that a write turns away with ``conflict``, or None.

    The run of every command that writes a store refuses such a root
    (`refuse_root`); the plan shows the same refusal as one ``conflict`` action
    for the root instead of failing, like a plain plan does for an output
    directory in a store (DEV-19.10, DEV-19.14). It is a successful result and
    nothing else is checked, so no request is made. A root that is no
    ``conflict`` is not handled here: the layout of a store without its marker
    (``store_unavailable``, ``no_marker``) is raised by the caller's own check
    and an unreadable marker is raised here.

    Parameters
    ----------
    command : str
        Name of the command the action refers to, e.g. ``"series build"``.
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.

    Returns
    -------
    StorePlan or None
        Plan with the one ``conflict`` action (``path`` the root, ``reason``
        ``nested_store`` or ``not_empty``), or None when the root is neither.

    Raises
    ------
    IMGWValidationError
        If the root path contains ``..``.
    IMGWStoreError
        If the root path contains a symbolic link.
    IMGWDataError
        If the marker of the root is unreadable (``details.reason``
        ``invalid_marker``).
    """
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    refusal = _refusal(path)
    if refusal is None:
        return None
    action = PlanAction(
        command,
        "unverifiable",
        refusal[1],
        action="conflict",
        path=path,
        reason=refusal[0],
    )
    return StorePlan("imgw-plan/1", path, datetime.now(UTC), (), {}, (action,))


def _has_layout(path: Path) -> bool:
    """Whether the root holds a tree of an IMGW store (with or without a marker)."""
    return any((path / name).is_dir() for name in _LAYOUT_TREES)


def _foreign_content(path: Path) -> bool:
    """Whether a root holds anything but the state files of the server."""
    return any(entry.name not in _STATE_FILES for entry in path.iterdir())


def _unmarked(path: Path) -> IMGWStoreError:
    """The layout of a store without its marker: ``imgw store init`` verifies it."""
    return IMGWStoreError(
        message("writer.layout_without_marker", path=path),
        details={"reason": "no_marker"},
    )


def _verify_layout(path: Path) -> None:
    """Verify the layout of a root without a marker before one is written (DEV-19.13)."""
    problems: list[str] = []
    known = _LAYOUT_TREES | _STATE_FILES | {".incoming"}
    for entry in sorted(path.iterdir()):
        if entry.name not in known:
            problems.append(message("writer.unexpected_root_entry", name=entry.name))
    for name in sorted(_LAYOUT_TREES):
        tree = path / name
        if tree.is_symlink() or (tree.exists() and not tree.is_dir()):
            problems.append(message("writer.layout_tree_not_directory", name=name))
            continue
        for sidecar in tree.rglob("*.meta.json") if tree.is_dir() else ():
            try:
                schema = json.loads(sidecar.read_text(encoding="utf-8")).get("schema")
            except (OSError, ValueError, AttributeError):
                schema = None
            if sidecar.is_symlink() or schema != "imgw-meta/1":
                problems.append(
                    message(
                        "writer.foreign_sidecar",
                        sidecar=sidecar.relative_to(path).as_posix(),
                    )
                )
    if problems:
        raise IMGWDataError(
            message("writer.layout_not_imgw_store", path=path, count=len(problems)),
            details={
                "reason": "invalid_layout",
                "problems": [str(problem) for problem in problems[:20]],
            },
        )


def _validate_slot(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if (
        not parts
        or any(p in (".", "..", "") for p in parts)
        or relative.startswith("/")
        or "\\" in relative
    ):
        raise IMGWValidationError(
            message("writer.unsafe_archive_path", relative=relative)
        )
    result = root.joinpath(*parts)
    for path in (result, *result.parents):
        if path == root.parent:
            break
        if path.is_symlink():
            raise IMGWStoreError(
                message("writer.link_slot_path", path=path), code="validation_error"
            )
    return result


def init_store(root: PathArg, /, *, created_at: datetime | None = None) -> StoreHandle:
    """
    Write the marker of a store: ``imgw store init`` (DEV-19.13).

    A new, missing or empty root (the state file ``api_keys.json`` of the
    server does not count) gets the marker ``imgw-store.json`` with the fields
    ``schema``, ``tool``, ``created_at``, ``producer_version`` and
    ``created_by``. A root that has the layout of a store (``archives/``,
    ``series/``, ``stations/`` or ``pmaxtp/``) but no marker is verified first
    (every sidecar is ``imgw-meta/1``, nothing foreign lies beside the trees)
    and then marked. The marker is published atomically by a hard link and
    never replaces a competing marker; like every write to the store, this
    needs a file system with hard links. If the root already holds a marker
    (including one created concurrently), the existing store is opened.

    Parameters
    ----------
    root : str or os.PathLike
        Store root directory; created (with parents) if it does not exist.
    created_at : datetime.datetime or None, optional
        Timezone-aware creation time recorded in the marker as UTC; the
        current time by default.

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
    IMGWDataError
        If the layout of a root without a marker is not that of an IMGW store
        (``details.reason`` ``invalid_layout``, ``details.problems``).
    IMGWStoreConflictError
        If the directory holds other files and no layout, it is nested in or
        contains another store (``details.reason`` ``nested_store``) or the file
        system cannot create the hard link used to publish the marker (e.g.
        FAT, exFAT, some NAS or FUSE file systems, the macOS SMB client;
        ``details.reason`` ``not_atomic``); code ``conflict``.
    """
    path = _safe_root(root)
    _check_nested(path)
    marker = path / _MARKER
    if marker.exists():
        return open_store(path)
    if path.exists():
        if not path.is_dir():
            raise IMGWStoreConflictError(
                message("writer.directory_not_empty_imgw_store", path=path),
                details=_NOT_EMPTY,
            )
        if _has_layout(path):
            _verify_layout(path)
        elif _foreign_content(path):
            raise IMGWStoreConflictError(
                message("writer.directory_not_empty_imgw_store", path=path),
                details=_NOT_EMPTY,
            )
    path.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {
        "schema": "imgw-store/1",
        "tool": "imgw",
        "created_at": _utc(created_at or datetime.now(UTC)),
        "producer_version": __version__,
        "created_by": f"imgwtools {__version__}",
    }
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
            raise IMGWStoreConflictError(
                message(
                    "writer.file_system_does_not_support",
                    path=path,
                    strerror=exc.strerror,
                ),
                details={"reason": "not_atomic"},
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
    if _marker(path / _MARKER) is None and _has_layout(path):
        raise _unmarked(path)
    if _marker(path / _MARKER) != "imgw-store/1":
        raise IMGWStoreError(
            message("writer.no_marker_unsupported_imgw_store", path=path),
            details={"reason": "unsupported"},
        )
    return StoreHandle(path, "imgw-store/1")


def _complete_marker(handle: StoreHandle) -> None:
    """Add the fields of DEV-19.12 that an older marker lacks (a root file, not a version)."""
    marker = handle.root / _MARKER
    payload = json.loads(marker.read_text(encoding="utf-8"))
    wanted = {
        "tool": "imgw",
        "producer_version": __version__,
        "created_at": _utc(datetime.fromtimestamp(marker.stat().st_mtime, UTC)),
    }
    missing = {key: value for key, value in wanted.items() if key not in payload}
    if not missing:
        return
    temporary = marker.with_name(f".{_MARKER}.{uuid.uuid4().hex}.tmp")
    try:
        _write_json(temporary, {**payload, **missing})
        os.replace(temporary, marker)
        _fsync_dir(handle.root)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_store(root: PathArg | StoreHandle) -> StoreHandle:
    """
    Open the store at ``root`` for a write; the first write creates the marker.

    The root must not nest a store. A root with a marker is opened (an older
    marker gains the fields of DEV-19.12); a new or empty root gets its marker
    now, as `init_store` writes it (DEV-19.13); a root with the layout of a
    store and no marker is ``store_unavailable``, and ``imgw store init``
    verifies it.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.

    Returns
    -------
    StoreHandle
        Handle of the store, which exists and has its marker.

    Raises
    ------
    IMGWStoreError
        If the layout has no marker (``details.reason`` ``no_marker``) or the
        marker is not a supported store.
    IMGWStoreConflictError
        If the root nests a store or holds foreign files and no layout.
    """
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    _check_nested(path)
    if (path / _MARKER).exists():
        handle = open_store(path)
        _complete_marker(handle)
        return handle
    if _has_layout(path):
        raise _unmarked(path)
    return init_store(path)


def lenient_store(root: PathArg | StoreHandle) -> StoreHandle:
    """
    Open the store at ``root`` for a plan or a read of derived data; nothing is created.

    A missing or empty root is an empty store (every file of a plan is new); a
    root with a layout and no marker is ``store_unavailable`` with the hint to
    run ``imgw store init``.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.

    Returns
    -------
    StoreHandle
        Handle of the store, which need not exist yet.

    Raises
    ------
    IMGWStoreError
        If the root is another kind of directory or its marker is unsupported.
    """
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    if (path / _MARKER).exists():
        return open_store(path)
    if _has_layout(path):
        raise _unmarked(path)
    if path.exists() and (not path.is_dir() or _foreign_content(path)):
        return open_store(path)  # raises: not an IMGW store
    return StoreHandle(path, "imgw-store/1")


def _utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise IMGWValidationError(message("writer.date_must_have_time_zone"))
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
                    message("writer.abandoned_staging_removed", name=child.name),
                )
            )


def _existing(
    slot: Path, name: str, *, archive: bool = False, skip: Collection[str] = ()
) -> list[tuple[Path, dict[str, Any]]]:
    """
    Every committed version of a slot with its sidecar, verified by SHA-256.

    A version directory without the main file's sidecar is an interrupted
    publication, not a version (`_publish_dir`), and is skipped.

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
        If an element of the slot is neither a readable, consistent version
        nor an interrupted publication.
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
            raise IMGWStoreConflictError(
                message("writer.invalid_archive_version", directory=directory)
            )
        meta_path = directory / f"{name}.meta.json"
        if not meta_path.exists() and not meta_path.is_symlink():
            continue
        try:
            source = directory / name
            if source.is_symlink() or meta_path.is_symlink():
                raise ValueError("link in the version")
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
                raise ValueError("inconsistent checksum, schema or label")
        except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
            raise IMGWStoreConflictError(
                message("writer.corrupt_archive_version", directory=directory)
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
        raise IMGWStoreConflictError(
            message("writer.corrupt_archive_version", directory=version)
        )
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
    ``.incoming`` directory and published by a hard link, which never
    replaces a file; the register directory is created when needed. A file
    of the same name (the same signal seen on the same day) is kept
    unchanged and returned.

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
        kind, or the file system has no hard links (``details.reason``
        ``not_atomic``).
    IMGWCancelledError
        If ``cancel`` returns ``True`` before publication.
    """
    if not _is_seen_at(observation.seen_at):
        raise IMGWValidationError(
            message(
                "writer.observation_time_must_have_form", seen_at=observation.seen_at
            )
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
            raise IMGWCancelledError(message("writer.observation_write_cancelled"))
        try:
            register.mkdir()
        except FileExistsError:
            if not _is_register(register):
                raise IMGWStoreConflictError(
                    message(
                        "writer.observation_register_not_directory", register=register
                    )
                ) from None
        else:
            _fsync_dir(register.parent)
        try:
            _link(staging / name, target)
        except FileExistsError:
            # The same signal on the same day is already recorded; keep that file.
            if target.is_symlink() or not target.is_file():
                raise IMGWStoreConflictError(
                    message("writer.observation_file_collision", target=target)
                ) from None
        else:
            _fsync_dir(register)
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
            message(
                "writer.file_does_not_meet_content",
                filename=filename,
                form=form,
                exc=reason(exc),
            )
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
            else message("writer.no_observation_reference")
        )
        on_notice(
            Notice(
                "info",
                _CONTENT_CODE,
                message(
                    "writer.content_unchanged",
                    slot=slot,
                    sha=sha,
                    form=form,
                    content_sha256=meta.content_sha256,
                    current=current.relative_to(root).as_posix(),
                    sha256=meta.sha256,
                    recorded=recorded,
                ),
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
    ``.incoming`` and published into the version directory
    ``<label>_<sha8>`` by hard links, the sidecar last (`_publish_dir`):
    nothing is ever replaced, and a version is complete once its sidecar
    exists. The label is the UTC date of ``Last-Modified`` (or of the
    download when absent); identical bytes with a different HTTP signal on
    the same day get a stable ``+<8 hex>`` suffix. Country, provider and
    license of the sidecar come from the provider registry.

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
        Called once with a ``new`` progress event after publication.
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
        ``status`` is ``"new"`` for new content, ``"relabeled"`` for
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
        content, or the file system has no hard links (``details.reason``
        ``not_atomic``).
    IMGWCancelledError
        If ``cancel`` returns ``True`` before publication.
    """
    handle = prepare_store(root)
    path = handle.root
    descriptor = get_dataset(archive.dataset)
    provider = get_provider(descriptor.provider)
    _validate_slot(path, f"archives/versions/{archive.server_path}")
    relative = PurePosixPath(archive.server_path)
    if descriptor.server_dir is None or not archive.server_path.startswith(
        descriptor.server_dir + "/"
    ):
        raise IMGWValidationError(
            message("writer.path_does_not_belong_dataset", dataset=archive.dataset)
        )
    if relative.suffix.lower() not in _SUFFIXES.get(provider.id, ()):
        raise IMGWValidationError(
            message("writer.disallowed_type_archive", relative=relative)
        )
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
        raise IMGWCancelledError(message("writer.archive_write_cancelled"))
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
                    message("writer.invalid_last_modified_header")
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
            raise IMGWCancelledError(message("writer.archive_write_cancelled"))
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
            _publish_dir(staging, target, f"{filename}.meta.json")
        except FileExistsError as exc:
            for old_file, old_meta in _existing(slot, filename, archive=True):
                if (
                    old_file.parent == target
                    and old_meta["sha256"] == sha
                    and signal == _archive_signal(old_file.parent, old_meta)
                ):
                    return VersionResult("unchanged", old_file, sha, label)
            raise IMGWStoreConflictError(
                message("writer.version_directory_collision", target=target)
            ) from exc
        if on_progress is not None:
            on_progress(
                Progress(
                    1,
                    1,
                    "archive",
                    "new",
                    message("writer.archive_written", filename=filename),
                )
            )
        if on_notice is not None:
            on_notice(
                Notice(
                    "info",
                    _ATTRIBUTION_CODE,
                    provider.license_notice(),
                )
            )
        return VersionResult(
            "relabeled" if matching else "new", target / filename, sha, label
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)
