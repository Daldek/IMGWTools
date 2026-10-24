"""
Plain output: ordinary files in a directory, without metadata (DEV §19, ADR-007).

Every plain write of IMGWTools (the archives of ``datasets download`` and
``store sync``, the files of ``pmaxtp sync``, the exports) goes through the
steps of this module, written once:

0. the write target is the directory ``output_dir`` (plain mode) or the store
   at ``root`` (store mode), never both, and the store at the default root
   when neither is given (`resolve_target`);
1. the target list is built before the first byte and checked as a whole
   (`plan_plain`): duplicate names are a ``conflict`` with the reason
   ``duplicate_output_name``, an existing target without ``force`` one with
   ``output_exists``, a directory that is or lies in a store one with
   ``output_in_store``; the error lists every offending path
   (`refuse`);
2. the files are written to a staging directory
   ``<dir>/.imgw-incoming/<host>_<pid>_<token>/`` on the same file system,
   hashed while they are written (`Staging.write`) and moved into place with
   ``os.replace`` (`Staging.commit`); the staging directory is removed on
   success, on error, on SIGINT and on SIGTERM, and leftovers older than 24
   hours are removed by the next run.

No sidecar, no hard link and no ``versions/`` directory: the output works on
FAT, exFAT and SMB. A store is recognised by its marker file name alone, so
nothing is imported from another tool (DEV-19.11, DEV-19.12).

An export writes exactly one file (``output``, DEV-19.1): the directory that
holds it plays the role of ``output_dir`` for the staging directory and the
store check, and the result is an `OutputReport`.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
import shutil
import signal
import socket
import threading
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType, TracebackType
from typing import Literal

from imgwtools.exceptions import IMGWError, IMGWValidationError
from imgwtools.messages import message

__all__ = [
    "STAGING",
    "STORE_MARKERS",
    "FileResult",
    "OutputReport",
    "PlanEntry",
    "Staging",
    "Target",
    "plan_plain",
    "refuse",
    "chunks_of",
    "resolve_target",
    "store_around",
    "store_below",
]

STORE_MARKERS = ("kartograf-store.json", "imgw-store.json")
"""File names that mark the root of a store of any Nogat tool (DEV-19.12)."""
STAGING = ".imgw-incoming"
"""Name of the staging directory inside the output directory (DEV-19.7)."""
_STALE_SECONDS = 24 * 60 * 60
_CHUNK = 1 << 16

Action = Literal["write", "replace", "conflict"]
Reason = Literal["duplicate_output_name", "output_exists", "output_in_store"]


@dataclass(frozen=True)
class FileResult:
    """
    One entry of ``files[]`` in the result of a writing command (DEV-19.19).

    Attributes
    ----------
    path : Path
        Absolute path of the file.
    size_bytes : int
        Size of the file in bytes.
    sha256 : str
        SHA-256 of the file, 64 lower-case hexadecimal digits, computed while
        the file was written.
    status : {"written", "replaced", "new", "unchanged", "relabeled"}
        Plain mode: ``"written"`` (a new file) or ``"replaced"`` (an existing
        file, with ``force``). Store mode: ``"new"`` (a new version),
        ``"unchanged"`` (identical content already stored) or ``"relabeled"``
        (identical bytes under a new source signal).
    """

    path: Path
    size_bytes: int
    sha256: str
    status: Literal["written", "replaced", "new", "unchanged", "relabeled"]


@dataclass(frozen=True)
class OutputReport:
    """
    Result of an export written to one file (DEV-19.1, DEV-19.19).

    Attributes
    ----------
    output : Path
        Absolute path of the file that was written.
    files : tuple of FileResult
        The written file as ``files[]``: ``written`` for a new file or
        ``replaced`` for an existing one (with ``force``).
    """

    output: Path
    files: tuple[FileResult, ...]


@dataclass(frozen=True)
class PlanEntry:
    """
    One target of a plain write and what would happen to it (DEV-19.10).

    Attributes
    ----------
    path : Path
        Absolute path of the target.
    action : {"write", "replace", "conflict"}
        ``"write"`` for a new file, ``"replace"`` for an existing file with
        ``force``, ``"conflict"`` for a target that cannot be written.
    reason : {"duplicate_output_name", "output_exists", "output_in_store"} or None
        Why the target is a conflict; None for ``write`` and ``replace``.
    """

    path: Path
    action: Action
    reason: Reason | None = None


@dataclass(frozen=True)
class Target:
    """
    Where a writing command puts its data (DEV-19.1, DEV-19.2).

    Attributes
    ----------
    mode : {"plain", "store"}
        ``"plain"``: ordinary files in ``path`` (``output_dir``);
        ``"store"``: the versioned store at ``path`` (``root``).
    path : pathlib.Path
        Absolute output directory or store root.
    """

    mode: Literal["plain", "store"]
    path: Path


def resolve_target(
    *,
    output_dir: str | os.PathLike[str] | None = None,
    root: str | os.PathLike[str] | None = None,
) -> Target:
    """
    Choose between plain files and the store (DEV-19.1, DEV-19.2).

    Parameters
    ----------
    output_dir : str or os.PathLike or None, optional
        Directory of the plain files.
    root : str or os.PathLike or None, optional
        Root of the store.

    Returns
    -------
    Target
        The plain directory when ``output_dir`` is given, else the store at
        ``root`` or, when neither is given, the store at the default root
        (``IMGW_ROOT``, ``[imgw] root`` of ``nogat.toml`` or
        ``<data_dir>/imgw``).

    Raises
    ------
    IMGWValidationError
        If both are given (``details.reason="exclusive_options"``,
        ``details.options`` lists the pair, ``details.option`` is ``root``).
    """
    if output_dir is not None and root is not None:
        raise IMGWValidationError(
            message("output.exclusive_options"),
            details={
                "option": "root",
                "reason": "exclusive_options",
                "options": ["output_dir", "root"],
            },
        )
    if output_dir is not None:
        return Target("plain", Path(output_dir).expanduser().absolute())
    if root is not None:
        return Target("store", Path(root).expanduser().absolute())
    from imgwtools.config import default_root  # config reads the environment

    return Target("store", default_root())


def store_around(path: Path) -> Path | None:
    """
    Find the store that is ``path`` or contains it.

    Parameters
    ----------
    path : pathlib.Path
        A file or directory, existing or not.

    Returns
    -------
    pathlib.Path or None
        The nearest directory (``path`` itself included) that holds a store
        marker of any tool, or None.
    """
    resolved = path.resolve()
    return next(
        (
            candidate
            for candidate in (resolved, *resolved.parents)
            if any((candidate / name).is_file() for name in STORE_MARKERS)
        ),
        None,
    )


def store_below(path: Path, *, skip: frozenset[str] = frozenset()) -> Path | None:
    """
    Find a store marker below ``path`` (a nested store).

    Parameters
    ----------
    path : pathlib.Path
        Directory to search; symbolic links are not followed.
    skip : frozenset of str, optional
        Names of the directories directly under ``path`` that are not entered
        (the managed trees of the store at ``path``).

    Returns
    -------
    pathlib.Path or None
        The first directory below ``path`` that holds a store marker, or None.
    """
    if not path.is_dir():
        return None
    for base, dirs, files in os.walk(path, followlinks=False):
        folder = Path(base)
        if folder != path and any(name in files for name in STORE_MARKERS):
            return folder
        dirs[:] = [
            name
            for name in dirs
            if not (folder / name).is_symlink()
            and not (folder == path and name in skip)
        ]
    return None


def plan_plain(
    directory: Path, relative: Sequence[str], *, force: bool
) -> list[PlanEntry]:
    """
    Check the full target list of a plain write without writing anything.

    Parameters
    ----------
    directory : pathlib.Path
        Absolute output directory (it need not exist yet).
    relative : sequence of str
        POSIX sub-path of every target below ``directory`` (the file name in
        the store, below the sub-path of its source).
    force : bool
        Replace existing targets.

    Returns
    -------
    list of PlanEntry
        One entry per target in the given order: duplicates are conflicts
        (every occurrence), then targets of a directory that is or lies in a store
        or enters a subdirectory that holds a marker, then existing targets
        without ``force``; the rest is ``write`` or ``replace``. A store
        elsewhere below ``directory`` does not matter: nothing is written into it.
    """
    in_store = store_around(directory) is not None
    counts: dict[str, int] = {}
    for name in relative:
        counts[name] = counts.get(name, 0) + 1
    entries: list[PlanEntry] = []
    for name in relative:
        path = directory.joinpath(*name.split("/"))
        if counts[name] > 1:
            entries.append(PlanEntry(path, "conflict", "duplicate_output_name"))
        elif in_store or _holds_marker(directory, name):
            entries.append(PlanEntry(path, "conflict", "output_in_store"))
        elif path.exists():
            entries.append(
                PlanEntry(path, "replace")
                if force
                else PlanEntry(path, "conflict", "output_exists")
            )
        else:
            entries.append(PlanEntry(path, "write"))
    return entries


def _holds_marker(directory: Path, name: str) -> bool:
    """Whether a directory the write would enter holds a store marker."""
    parent = directory
    for part in name.split("/")[:-1]:
        parent = parent / part
        if any((parent / marker).is_file() for marker in STORE_MARKERS):
            return True
    return False


def refuse(entries: Sequence[PlanEntry], *, single: bool = False) -> None:
    """
    Raise ``conflict`` when the plan lists a conflict (DEV-19.6, DEV-19.11).

    Parameters
    ----------
    entries : sequence of PlanEntry
        The plan of `plan_plain`.
    single : bool, optional
        The plan is the one file of an export (``output``): the texts speak of
        a file and an export is written outside every store, so the hint of a
        store target is not given (an export has no store mode, ``--root``
        names the store it reads).

    Raises
    ------
    IMGWError
        Code ``conflict``; ``details.reason`` is the first reason in the order
        ``duplicate_output_name``, ``output_in_store``, ``output_exists`` and
        ``details.paths`` lists every path with a conflict of any reason.
    """
    conflicts = [entry for entry in entries if entry.action == "conflict"]
    if not conflicts:
        return
    first = next(
        reason
        for reason in ("duplicate_output_name", "output_in_store", "output_exists")
        if any(entry.reason == reason for entry in conflicts)
    )
    paths = [str(entry.path) for entry in conflicts]
    texts = {
        "duplicate_output_name": "output.duplicate_output_name",
        "output_in_store": "output.output_file_in_store"
        if single
        else "output.output_in_store",
        "output_exists": "output.output_file_exists"
        if single
        else "output.output_exists",
    }
    raise IMGWError(
        message(texts[first], count=len(paths), first=paths[0]),
        code="conflict",
        details={"reason": first, "paths": paths},
    )


def _leftovers(staging: Path) -> None:
    """Remove staging directories of earlier runs that are over 24 hours old."""
    if not staging.is_dir():
        return
    cutoff = time.time() - _STALE_SECONDS
    for child in staging.iterdir():
        with contextlib.suppress(OSError):
            if (
                child.is_dir()
                and not child.is_symlink()
                and child.stat().st_mtime < cutoff
            ):
                shutil.rmtree(child, ignore_errors=True)


def _terminate(signum: int, frame: FrameType | None) -> None:
    """SIGTERM ends the run like an exit, so the staging directory is removed."""
    raise SystemExit(128 + signum)


class Staging:
    """
    Staging directory of one plain write (DEV-19.7).

    Used as a context manager: entering creates
    ``<directory>/.imgw-incoming/<host>_<pid>_<token>/`` (the output directory
    too, when it is missing), removes leftovers older than 24 hours and, in the
    main thread, lets SIGTERM end the run like an exit; leaving removes the
    staging directory and the ``.imgw-incoming`` directory when it is empty,
    whatever ended the block (success, an error, SIGINT, SIGTERM).

    Parameters
    ----------
    directory : pathlib.Path
        Absolute output directory (the directory that holds an ``output``
        file).
    """

    def __init__(self, directory: Path) -> None:
        """Name the staging directory of ``directory`` without creating it."""
        self.directory = directory
        self.root = directory / STAGING
        self.path = (
            self.root / f"{socket.gethostname()}_{os.getpid()}_{secrets.token_hex(4)}"
        )
        self._previous: signal.Handlers | int | None = None
        self._counter = 0

    def __enter__(self) -> Staging:
        """Create the staging directory and arm the SIGTERM handler."""
        self.directory.mkdir(parents=True, exist_ok=True)
        _leftovers(self.root)
        self.path.mkdir(parents=True)
        if threading.current_thread() is threading.main_thread():
            previous = signal.getsignal(signal.SIGTERM)
            if previous == signal.SIG_DFL:
                self._previous = previous
                signal.signal(signal.SIGTERM, _terminate)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Remove the staging directory and restore the SIGTERM handler."""
        if self._previous is not None:
            signal.signal(signal.SIGTERM, self._previous)
        shutil.rmtree(self.path, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.root.rmdir()  # only when no other run is staging beside this one

    def write(self, chunks: Iterable[bytes]) -> tuple[Path, int, str]:
        """
        Write ``chunks`` to a new staged file, hashing them as they are written.

        Parameters
        ----------
        chunks : iterable of bytes
            The content of the file.

        Returns
        -------
        tuple of (pathlib.Path, int, str)
            The staged file, its size and its SHA-256.
        """
        self._counter += 1
        staged = self.path / f"{self._counter:06d}"
        digest = hashlib.sha256()
        size = 0
        try:
            with staged.open("xb") as stream:
                for chunk in chunks:
                    digest.update(chunk)
                    size += len(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            staged.unlink(missing_ok=True)  # no partial file waits for the next run
            raise
        return staged, size, digest.hexdigest()

    def commit(self, staged: Path, target: Path, size: int, sha256: str) -> FileResult:
        """
        Move a staged file into place with ``os.replace`` (DEV-19.9).

        Parameters
        ----------
        staged : pathlib.Path
            File returned by `write`.
        target : pathlib.Path
            Absolute target; its directory is created when missing.
        size : int
            Size of the file, as returned by `write`.
        sha256 : str
            SHA-256 of the file, as returned by `write`.

        Returns
        -------
        FileResult
            ``written`` for a new target, ``replaced`` for an existing one.
        """
        replaced = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, target)
        return FileResult(target, size, sha256, "replaced" if replaced else "written")


def chunks_of(data: bytes) -> Iterator[bytes]:
    """Split ``data`` into the chunks `Staging.write` hashes one by one."""
    for start in range(0, len(data), _CHUNK):
        yield data[start : start + _CHUNK]
