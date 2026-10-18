"""Projekt ``imgw-project/1``: manifest zadań obok magazynu IMGW (spec §10.1).

``imgw-project.json`` jest edytowalną instrukcją walidowaną ściśle (IMGW-14): nieznane
klucze strukturalne są błędem, przyszłe dodatki trafiają wyłącznie do ``extensions``
(zachowywanego przy zapisie). Ścieżki są względne (POSIX): przypięte pliki wobec
``store_dir``, pliki projektu (``geometry``, wyjścia komend) wobec katalogu projektu —
bez ``..``, dowiązań symbolicznych i ucieczki z korzenia.

Zapis to kanoniczny JSON z LF przez plik tymczasowy, ``fsync`` i ``os.replace`` pod krótką
blokadą ``.imgw-project.lock`` (wyłączny ``mkdir``; zastanej blokady nie przejmujemy).
Sieć i budowa Parquet działają bez blokady; wynik zadania scala się per zadanie z
bieżącym manifestem, a zadanie zmienione w międzyczasie przez inny proces to jawny
konflikt. IMGWTools dotyka wyłącznie ``imgw-project.json`` — manifest Kartografa obok
pozostaje nietknięty.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from imgwtools import commands
from imgwtools._version import __version__
from imgwtools.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    archive_files,
    datasets,
    get_dataset,
)
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWError,
    IMGWProjectError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.store import (
    build_series,
    check_series,
    check_store,
    current_version,
    init_store,
    iter_store,
    open_store,
    read_catalog,
    read_meta,
    read_series_index,
    select_series,
    store_info,
    sync_store,
    write_archive,
)
from imgwtools.store.catalog import _Border
from imgwtools.store.sync import CANCELLED, UNPUBLISHED, _download, _plan_target
from imgwtools.store.types import (
    Cancel,
    CatalogReport,
    DownloadReport,
    Notice,
    NoticeHook,
    OperationResult,
    PathArg,
    PlanAction,
    PlanItem,
    PMaXTPStoreResult,
    Progress,
    ProgressHook,
    Project,
    ProjectFile,
    ProjectReport,
    ProjectTask,
    SeriesIndex,
    SeriesReport,
    StorePlan,
    SyncReport,
)
from imgwtools.store.writer import _canonical, _fsync_dir, _utc

__all__ = [
    "add_project_task",
    "check_project",
    "download_project",
    "get_project_status",
    "init_project",
    "open_project",
    "remove_project_task",
    "set_project_store",
    "verify_project",
]

PROJECT_SCHEMA = "imgw-project/1"
PROJECT_FILE = commands.PROJECT_FILE
LOCK_NAME = ".imgw-project.lock"
# Zajętą blokadę ponawiamy co LOCK_RETRY_S przez LOCK_TIMEOUT_S; potem jawny błąd, nigdy przejęcie.
LOCK_TIMEOUT_S = 5.0
LOCK_RETRY_S = 0.05

TaskStatus = Literal[
    "unpinned", "current", "missing", "changed", "upgraded", "failed", "cancelled"
]
PinState = Literal["current", "missing", "changed"]
Hooks = Mapping[str, Any]
_ResultStatus = Literal[
    "created", "relabeled", "unchanged", "reused", "failed", "stale_plan", "cancelled"
]
_PlanStatus = Literal["current", "newer", "missing", "unverifiable", "check_failed"]

_SELECT = "series select"
# Opcje zadania series select zapisane w manifeście zawsze jawnie.
_EXPLICIT = ("dataset", "stations", "variables", "years", "year_type")
_ROLES = ("series", "station_series", "catalog", "input")
# Przypięty plik to zawsze plik opublikowanej wersji: <rodzaj>/versions/…
_VERSION_KINDS = ("archives", "series", "stations", "pmaxtp")
_TOP_KEYS = (("schema", "store_dir", "tasks"), ("extensions",))
_TASK_KEYS = (
    ("name", "command", "options", "pinned_at", "imgwtools_version", "files"),
    ("geometry_sha256",),
)
_FILE_KEYS = (("role", "path", "sha256"), ("station",))
_SHA = re.compile(r"[0-9a-f]{64}")
_STATION = re.compile(r"[0-9]{9}")
_DRIVE = re.compile(r"[A-Za-z]:")
_YEAR = re.compile(r"(?<![0-9])[0-9]{4}(?![0-9])")
_DONE = ("created", "relabeled", "unchanged", "reused")
_SERIES_UNITS = ("day", "month", "half_year")
_SEVERITY = {"current": 0, "outdated": 1, "missing": 2}
_UPGRADE = 'świadome przepięcie: update="upgrade"'
_CHUNK = 1024 * 1024
_OPTIONS = {
    command.name: {option.name: option for option in command.options}
    for command in commands.data_commands()
}


# --- postać manifestu ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Manifest:
    """Zwalidowany manifest: projekt i ``store_dir`` w postaci zapisanej (względny zostaje względny)."""

    project: Project
    store_text: str

    def document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema": PROJECT_SCHEMA,
            "store_dir": self.store_text,
            "tasks": [_task_json(task) for task in self.project.tasks],
        }
        if self.project.extensions:
            document["extensions"] = dict(self.project.extensions)
        return document

    def with_tasks(self, tasks: Iterable[ProjectTask]) -> _Manifest:
        return replace(self, project=replace(self.project, tasks=tuple(tasks)))


def _file_json(pin: ProjectFile) -> dict[str, Any]:
    data: dict[str, Any] = {
        "role": pin.role,
        "path": pin.path.as_posix(),
        "sha256": pin.sha256,
    }
    if pin.station is not None:
        data["station"] = pin.station
    return data


def _task_json(task: ProjectTask) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": task.name,
        "command": task.command,
        "options": dict(task.options),
        "pinned_at": _utc(task.pinned_at) if task.pinned_at is not None else None,
        "imgwtools_version": task.imgwtools_version,
        "files": [_file_json(pin) for pin in task.files],
    }
    if task.geometry_sha256 is not None:
        data["geometry_sha256"] = dict(task.geometry_sha256)
    return data


# --- walidacja -------------------------------------------------------------------------------


def _invalid(where: str, problem: str) -> IMGWProjectError:
    return IMGWProjectError(
        f"{PROJECT_FILE}: {where}: {problem}" if where else f"{PROJECT_FILE}: {problem}"
    )


def _object(
    value: object, keys: tuple[tuple[str, ...], tuple[str, ...]], where: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(where, "oczekiwano obiektu JSON")
    required, optional = keys
    unknown = [
        repr(key) for key in value if key not in required and key not in optional
    ]
    if unknown:
        raise _invalid(
            where,
            f"nieznane klucze {', '.join(unknown)}; dodatki wyłącznie w extensions",
        )
    missing = [key for key in required if key not in value]
    if missing:
        raise _invalid(where, f"brak kluczy {', '.join(missing)}")
    return value


def _relative(value: object, base: Path, name: str) -> str:
    r"""Bezpieczna ścieżka względna POSIX w ``base``: bez ``..``, ``\`` i dowiązań symbolicznych."""
    text = value.as_posix() if isinstance(value, Path) else value
    if (
        not isinstance(text, str)
        or not text
        or "\0" in text
        or "\\" in text
        or text.startswith("/")
        or _DRIVE.match(text)
    ):
        raise IMGWValidationError(f"{name} musi być ścieżką względną POSIX: {value!r}")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise IMGWValidationError(
            f"{name} nie może zawierać '..', '.' ani pustych segmentów: {text!r}"
        )
    path = base.joinpath(*parts)
    for step in (path, *path.parents):
        if step == base:
            break
        if step.is_symlink():
            raise IMGWValidationError(
                f"Dowiązanie symboliczne w ścieżce {name}: {step}"
            )
    return text


def _input_relative(value: PathArg, base: Path, name: str) -> str:
    """Ścieżka z wywołania: względna wobec ``base`` albo bezwzględna wewnątrz ``base``."""
    path = Path(os.fspath(value))
    if path.is_absolute():
        if ".." in path.parts:
            raise IMGWValidationError(f"{name} nie może zawierać '..': {value}")
        try:
            path = path.relative_to(base)
        except ValueError:
            raise IMGWValidationError(
                f"{name} musi leżeć w katalogu {base}: {value}"
            ) from None
    return _relative(path.as_posix(), base, name)


def _options_json(
    command: str,
    normalized: Mapping[str, Any],
    directory: Path,
    root: Path,
    *,
    inputs: bool,
) -> dict[str, Any]:
    """Opcje w postaci manifestu: listy JSON, daty ISO, ścieżki względne (``version`` wobec magazynu)."""
    spec = _OPTIONS[command]
    relative = _input_relative if inputs else _relative
    result: dict[str, Any] = {}
    for name, value in normalized.items():
        if spec[name].type == "path":
            value = relative(value, root if name == "version" else directory, name)
        elif spec[name].type == "date":
            value = value.isoformat()
        result[name] = list(value) if isinstance(value, tuple) else value
    return result


def _stored_options(
    command: str, raw: object, directory: Path, root: Path
) -> dict[str, Any]:
    """Opcje zadania zapisane w manifeście: walidator katalogu komend + jawne opcje series select."""
    if not isinstance(raw, dict):
        raise IMGWValidationError("Opcje zadania muszą być obiektem JSON")
    options = dict(raw)
    area = "geometry" in options
    geometry = options.pop("geometry", None)
    normalized = commands._validate(command, options, task=True)
    result = _options_json(command, normalized, directory, root, inputs=False)
    if command == _SELECT:
        missing = [name for name in _EXPLICIT if name not in normalized]
        if missing:
            raise IMGWValidationError(
                f"Zadanie series select wymaga jawnych opcji: {', '.join(missing)}"
            )
    if area:
        if command != _SELECT:
            raise IMGWValidationError(
                "Opcja geometry dotyczy wyłącznie zadań series select"
            )
        result["geometry"] = _relative(geometry, directory, "geometry")
    return result


def _moment(value: object, where: str) -> datetime | None:
    if value is None:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError("oczekiwano tekstu ISO 8601")
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(where, f"nieprawidłowa data: {exc}") from exc
    if moment.tzinfo is None:
        raise _invalid(where, "data musi zawierać strefę czasową (UTC)")
    return moment.astimezone(UTC)


def _parse_file(raw: object, where: str, root: Path) -> ProjectFile:
    data = _object(raw, _FILE_KEYS, where)
    role = data["role"]
    if role not in _ROLES:
        raise _invalid(
            f"{where}.role", f"nieznana rola {role!r}; dozwolone: {', '.join(_ROLES)}"
        )
    try:
        path = _relative(data["path"], root, "path")
    except IMGWValidationError as exc:
        raise _invalid(f"{where}.path", str(exc)) from exc
    parts = path.split("/")
    if len(parts) < 4 or parts[0] not in _VERSION_KINDS or parts[1] != "versions":
        raise _invalid(
            f"{where}.path",
            f"oczekiwano pliku opublikowanej wersji magazynu (<rodzaj>/versions/…): {path}",
        )
    sha = data["sha256"]
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise _invalid(
            f"{where}.sha256", "oczekiwano pełnej sumy SHA-256 (64 małe cyfry hex)"
        )
    station = data.get("station")
    if "station" in data and (
        not isinstance(station, str) or not _STATION.fullmatch(station)
    ):
        raise _invalid(
            f"{where}.station", f"kod stacji musi mieć dokładnie 9 cyfr: {station!r}"
        )
    if role == "station_series" and station is None:
        raise _invalid(where, "plik station_series wymaga kodu station")
    return ProjectFile(role, Path(path), sha, station)


def _parse_task(raw: object, where: str, directory: Path, root: Path) -> ProjectTask:
    data = _object(raw, _TASK_KEYS, where)
    name, command = data["name"], data["command"]
    if not isinstance(name, str) or not commands._TASK_NAME.fullmatch(name):
        raise _invalid(
            f"{where}.name",
            f"nazwa zadania: 1–64 znaki a-z, 0-9, _ lub -, na początku litera lub cyfra: {name!r}",
        )
    if command not in commands._TASK_COMMANDS:
        raise _invalid(
            f"{where}.command", f"komenda {command!r} nie może być zadaniem projektu"
        )
    try:
        options = _stored_options(command, data["options"], directory, root)
    except IMGWValidationError as exc:
        raise _invalid(f"{where}.options", str(exc)) from exc
    geometry = options.get("geometry")
    digests = data.get("geometry_sha256")
    if "geometry_sha256" in data:
        if (
            not isinstance(digests, dict)
            or set(digests) != {geometry}
            or not all(
                isinstance(value, str) and _SHA.fullmatch(value)
                for value in digests.values()
            )
        ):
            raise _invalid(
                f"{where}.geometry_sha256",
                "oczekiwano {<options.geometry>: <SHA-256 pliku wyboru obszaru>}",
            )
    elif geometry is not None:
        raise _invalid(
            where, "wybór obszarem (options.geometry) wymaga geometry_sha256"
        )
    pinned_at = _moment(data["pinned_at"], f"{where}.pinned_at")
    version = data["imgwtools_version"]
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise _invalid(
            f"{where}.imgwtools_version", "oczekiwano niepustego tekstu albo null"
        )
    if (pinned_at is None) != (version is None):
        raise _invalid(
            where,
            "pinned_at i imgwtools_version są oba null (zadanie nieprzypięte) albo oba ustawione",
        )
    if not isinstance(data["files"], list):
        raise _invalid(f"{where}.files", "oczekiwano listy plików")
    pins = tuple(
        _parse_file(entry, f"{where}.files[{index}]", root)
        for index, entry in enumerate(data["files"])
    )
    if len({pin.path for pin in pins}) != len(pins):
        raise _invalid(f"{where}.files", "powtórzona ścieżka przypiętego pliku")
    return ProjectTask(
        name,
        command,
        options,
        dict(digests) if isinstance(digests, dict) else None,
        pinned_at,
        version,
        pins,
    )


def _store_root(directory: Path, text: str) -> Path:
    path = Path(text)
    return Path(os.path.normpath(path if path.is_absolute() else directory / path))


def _check_store(root: Path, directory: Path) -> None:
    """Projekt poza magazynem; istniejący niepusty ``store_dir`` musi być magazynem IMGW."""
    if root == directory or root in directory.parents:
        raise IMGWProjectError(
            f"Katalog projektu {directory} nie może leżeć w magazynie {root}"
        )
    if not root.exists() and not root.is_symlink():
        return
    if root.is_dir() and not root.is_symlink() and not any(root.iterdir()):
        return
    try:
        info = store_info(root)
    except IMGWError as exc:
        raise IMGWProjectError(f"Nieprawidłowy katalog magazynu {root}: {exc}") from exc
    if not info.supported:
        raise IMGWProjectError(
            f"Katalog {root} nie jest obsługiwanym magazynem IMGW: {'; '.join(info.problems)}"
        )


def _parse(directory: Path, document: object) -> _Manifest:
    data = _object(document, _TOP_KEYS, "")
    if data["schema"] != PROJECT_SCHEMA:
        raise _invalid(
            "schema",
            f"nieobsługiwany schemat {data['schema']!r}; ta wersja IMGWTools czyta {PROJECT_SCHEMA}",
        )
    text = data["store_dir"]
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise _invalid("store_dir", "oczekiwano niepustej ścieżki magazynu")
    root = _store_root(directory, text)
    _check_store(root, directory)
    extensions = data.get("extensions", {})
    if not isinstance(extensions, dict):
        raise _invalid("extensions", "oczekiwano obiektu JSON")
    if not isinstance(data["tasks"], list):
        raise _invalid("tasks", "oczekiwano listy zadań")
    tasks: list[ProjectTask] = []
    for index, raw in enumerate(data["tasks"]):
        task = _parse_task(raw, f"tasks[{index}]", directory, root)
        if any(other.name == task.name for other in tasks):
            raise _invalid(
                f"tasks[{index}].name", f"powtórzona nazwa zadania {task.name!r}"
            )
        tasks.append(task)
    return _Manifest(Project(directory, root, tuple(tasks), dict(extensions)), text)


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"powtórzony klucz {key!r}")
        result[key] = value
    return result


def _no_constant(name: str) -> Any:
    raise ValueError(f"niedozwolona wartość {name}")


def _load(directory: Path) -> _Manifest:
    path = directory / PROJECT_FILE
    if path.is_symlink():
        raise IMGWProjectError(
            f"Manifest projektu nie może być dowiązaniem symbolicznym: {path}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise IMGWProjectError(
            f"Brak manifestu projektu {path}; najpierw imgw project init"
        ) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise IMGWProjectError(
            f"Nie można odczytać manifestu projektu {path}: {exc}"
        ) from exc
    try:
        document = json.loads(
            text, object_pairs_hook=_unique_keys, parse_constant=_no_constant
        )
    except ValueError as exc:
        raise _invalid("", f"nieprawidłowy JSON: {exc}") from exc
    return _parse(directory, document)


# --- blokada i atomowy zapis -----------------------------------------------------------------


def _host() -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", socket.gethostname()) or "host"


def _owner(lock: Path) -> str:
    try:
        return f"właściciel: {(lock / 'owner').read_text(encoding='utf-8').strip()}"
    except OSError:
        return "właściciel nieznany"


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    """Krótka blokada odczyt–scalenie–zapis; zajętej nie przejmujemy."""
    lock = directory / LOCK_NAME
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    while True:
        try:
            os.mkdir(lock)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise IMGWProjectError(
                    f"Manifest projektu jest zablokowany ({_owner(lock)}); jeśli żaden proces IMGWTools "
                    f"nie pracuje na projekcie, usuń ręcznie katalog {lock}"
                ) from None
            time.sleep(LOCK_RETRY_S)
        except OSError as exc:
            raise IMGWProjectError(
                f"Nie można zablokować manifestu projektu ({lock}): {exc}"
            ) from exc
    try:
        with suppress(OSError):  # plik właściciela służy wyłącznie diagnostyce
            (lock / "owner").write_text(
                f"{_host()} pid {os.getpid()} od {_utc(datetime.now(UTC))}\n",
                encoding="utf-8",
            )
        yield
    finally:
        with suppress(OSError):
            (lock / "owner").unlink()
        with suppress(OSError):
            lock.rmdir()


def _write(directory: Path, document: Mapping[str, Any]) -> None:
    target = directory / PROJECT_FILE
    temporary = (
        directory
        / f".{PROJECT_FILE}.{_host()}_{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(_canonical(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _fsync_dir(directory)
    except OSError as exc:
        with suppress(OSError):
            temporary.unlink()
        raise IMGWProjectError(
            f"Nie można zapisać manifestu projektu {target}: {exc}"
        ) from exc
    except BaseException:
        with suppress(OSError):
            temporary.unlink()
        raise


def _update(
    directory: Path, change: Callable[[_Manifest], _Manifest | None]
) -> Project:
    """Odczyt–scalenie–zapis pod blokadą; ``change`` dostaje bieżący (świeżo odczytany) manifest."""
    with _locked(directory):
        current = _load(directory)
        changed = change(current)
        if changed is None or changed.document() == current.document():
            return current.project
        validated = _parse(directory, changed.document())
        _write(directory, validated.document())
        return validated.project


def _commit(directory: Path, before: ProjectTask, after: ProjectTask) -> None:
    """Scal jedno zadanie: zmienione od odczytu przez inny proces = konflikt bez zapisu."""

    def change(current: _Manifest) -> _Manifest | None:
        tasks = list(current.project.tasks)
        index = next(
            (index for index, task in enumerate(tasks) if task.name == before.name),
            None,
        )
        if index is None:
            raise IMGWProjectError(
                f"Konflikt: zadanie {before.name} usunięto z manifestu w trakcie pobierania; "
                "przypięć nie zapisano"
            )
        existing = _task_json(tasks[index])
        if existing == _task_json(after):
            return None
        if existing != _task_json(before):
            raise IMGWProjectError(
                f"Konflikt: zadanie {before.name} zmienił inny proces w trakcie pobierania; "
                "przypięć nie zapisano"
            )
        tasks[index] = after
        return current.with_tasks(tasks)

    _update(directory, change)


# --- argumenty ---------------------------------------------------------------------------------


def _path_text(value: object, what: str) -> str:
    text = os.fspath(value) if isinstance(value, str | os.PathLike) else None
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise IMGWValidationError(f"{what} wymaga niepustej ścieżki: {value!r}")
    return os.path.expanduser(text)


def _directory(project_dir: PathArg) -> Path:
    return Path(os.path.abspath(_path_text(project_dir, "Katalog projektu")))


def _store_argument(directory: Path, store_dir: PathArg) -> tuple[str, Path]:
    """``store_dir`` względny wobec projektu zapisuje się względnie, bezwzględny bezwzględnie."""
    path = Path(_path_text(store_dir, "Katalog magazynu"))
    text = str(path) if path.is_absolute() else path.as_posix()
    return text, _store_root(directory, text)


def _selected(project: Project, tasks: Iterable[str] | None) -> tuple[ProjectTask, ...]:
    if tasks is None:
        return project.tasks
    if isinstance(tasks, str | bytes) or not isinstance(tasks, Iterable):
        raise IMGWValidationError("Parametr tasks musi być kolekcją nazw zadań")
    names = list(dict.fromkeys(tasks))
    known = {task.name for task in project.tasks}
    unknown = [repr(name) for name in names if name not in known]
    if unknown:
        raise IMGWProjectError(f"Nieznane zadania projektu: {', '.join(unknown)}")
    return tuple(task for task in project.tasks if task.name in names)


def _store_path(root: Path, path: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        raise IMGWStoreError(f"Wersja {path} leży poza magazynem {root}") from None


def _notice(
    hook: NoticeHook | None,
    level: Literal["info", "warning", "error"],
    code: str,
    text: str,
) -> None:
    if hook is not None:
        hook(Notice(level, code, text))


# --- manifest: init/open/add/remove/set-store ------------------------------------------------


def init_project(project_dir: PathArg, /, *, store_dir: PathArg) -> Project:
    """
    Create an ``imgw-project.json`` manifest without tasks.

    A relative ``store_dir`` is resolved against the project directory and stored
    relative; an absolute one is stored absolute. The project directory is created
    when missing. An existing manifest pointing at the same store is returned
    unchanged without writing.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    store_dir : str or os.PathLike
        IMGW store directory. If it exists it must be a supported IMGW store or an
        empty directory, and the project directory must not lie inside it.

    Returns
    -------
    Project
        The created (or already existing) project.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` or ``store_dir`` is not a non-empty path.
    IMGWProjectError
        If the store directory is invalid, the project directory lies inside the
        store, the directory or manifest cannot be written, the manifest lock is
        held, or an existing manifest points at a different store (change it with
        `set_project_store`).
    """
    directory = _directory(project_dir)
    text, root = _store_argument(directory, store_dir)
    _check_store(root, directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IMGWProjectError(
            f"Nie można utworzyć katalogu projektu {directory}: {exc}"
        ) from exc
    with _locked(directory):
        manifest = directory / PROJECT_FILE
        if manifest.exists() or manifest.is_symlink():
            existing = _load(directory).project
            if existing.store_dir != root:
                raise IMGWProjectError(
                    f"Manifest projektu {manifest} już istnieje i wskazuje magazyn "
                    f"{existing.store_dir}; zmiana magazynu: set_project_store"
                )
            return existing
        created = _parse(
            directory, {"schema": PROJECT_SCHEMA, "store_dir": text, "tasks": []}
        )
        _write(directory, created.document())
        return created.project


def open_project(project_dir: PathArg, /) -> Project:
    """
    Read the project manifest offline with strict validation.

    Unknown structural keys, wrong types, invalid command options and unsafe paths
    (``..``, symbolic links, escaping the root) are rejected. Unknown entries under
    ``extensions`` are kept.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding ``imgw-project.json``.

    Returns
    -------
    Project
        The validated project with absolute ``path`` and ``store_dir``.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a non-empty path.
    IMGWProjectError
        If the manifest is missing, unreadable, a symbolic link or invalid.
    """
    return _load(_directory(project_dir)).project


def _empty_store(root: Path) -> bool:
    """Nowy magazyn: brak katalogu, pusty katalog albo magazyn bez wersji i problemów."""
    if not root.exists() or not any(root.iterdir()):
        return True
    return next(iter_store(root), None) is None


def set_project_store(
    project_dir: PathArg,
    /,
    *,
    store_dir: PathArg,
    on_notice: NoticeHook | None = None,
) -> Project:
    """
    Point the project at a different store, keeping every pin unchanged.

    The full SHA-256 of every pinned file (including the ``catalog`` pins of
    unpinned tasks) is verified in the new store before the manifest is updated.
    A new, empty store (missing or empty directory, or an initialised store
    without any version) is accepted without pinned files, so that
    `download_project` restores them: archives only with identical SHA-256,
    series only from exactly the pinned inputs, otherwise an explicit task
    error. A ``pins_not_in_store`` warning then lists what must be restored.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    store_dir : str or os.PathLike
        New store directory; relative paths are resolved against the project
        directory and stored relative.
    on_notice : NoticeHook or None, optional
        Called with the ``pins_not_in_store`` warning when the new store is
        empty and the project has pinned files.

    Returns
    -------
    Project
        The project with the new ``store_dir``.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` or ``store_dir`` is not a non-empty path.
    IMGWProjectError
        If the manifest is missing or invalid, the new store is invalid, it is
        not empty and does not contain identical pinned files, the manifest
        changed during verification, or the manifest cannot be locked or
        written.
    """
    directory = _directory(project_dir)
    before = _load(directory)
    text, root = _store_argument(directory, store_dir)
    _check_store(root, directory)
    pins = [(task, pin) for task in before.project.tasks for pin in task.files]
    problems = [
        f"{task.name}: {pin.path.as_posix()}: {error}"
        for task, pin in pins
        for state, error in (_inspect(root, pin, full=True),)
        if state != "current"
    ]
    if problems and not _empty_store(root):
        shown = "; ".join(problems[:5]) + (" …" if len(problems) > 5 else "")
        raise IMGWProjectError(
            f"Magazyn {root} nie zawiera identycznych przypiętych plików ({len(problems)}): "
            f"{shown}; manifest bez zmian"
        )

    def change(current: _Manifest) -> _Manifest:
        if current.document() != before.document():
            raise IMGWProjectError(
                "Manifest projektu zmienił się w trakcie weryfikacji magazynu; powtórz set-store"
            )
        return _Manifest(replace(current.project, store_dir=root), text)

    project = _update(directory, change)
    if problems:
        lost = sorted(
            {
                task.name
                for task, pin in pins
                if pin.role == "catalog" or pin.path.parts[0] == "pmaxtp"
            }
        )
        _notice(
            on_notice,
            "warning",
            "pins_not_in_store",
            f"Nowy magazyn {root} jest pusty: brak {len(problems)} przypiętych plików. "
            "project download odtworzy je z IMGW wyłącznie z identyczną sumą SHA-256 "
            "(szeregi z dokładnie przypiętych wejść), inaczej zgłosi błąd zadania"
            + (
                f"; katalogu stacji i komórek PMAXTP nie odtwarza (zadania: {', '.join(lost)}), "
                f"{_UPGRADE}"
                if lost
                else ""
            ),
        )
    return project


def _area(data: bytes, name: str) -> _Border:
    """Wielokąty WGS84 ``[lon, lat]`` z GeoJSON (Polygon/MultiPolygon, Feature, FeatureCollection)."""
    rings: list[list[list[float]]] = []

    def ring(value: object) -> list[list[float]]:
        if not isinstance(value, list) or len(value) < 4:
            raise ValueError("pierścień wielokąta wymaga co najmniej 4 pozycji")
        points: list[list[float]] = []
        for position in value:
            if (
                not isinstance(position, list)
                or len(position) < 2
                or not all(
                    isinstance(number, int | float)
                    and not isinstance(number, bool)
                    and math.isfinite(number)
                    for number in position[:2]
                )
            ):
                raise ValueError(f"nieprawidłowa pozycja {position!r}")
            points.append([float(position[0]), float(position[1])])
        if points[0] != points[-1]:
            raise ValueError("pierścień wielokąta musi być zamknięty")
        return points

    def geometry(value: object) -> None:
        if not isinstance(value, dict):
            raise ValueError("oczekiwano obiektu geometrii")
        kind = value.get("type")
        if kind == "GeometryCollection":
            for item in value.get("geometries") or []:
                geometry(item)
            return
        polygons = (
            [value.get("coordinates")]
            if kind == "Polygon"
            else value.get("coordinates")
        )
        if kind not in ("Polygon", "MultiPolygon") or not isinstance(polygons, list):
            raise ValueError(
                f"nieobsługiwana geometria {kind!r}; oczekiwano Polygon lub MultiPolygon"
            )
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("pusty wielokąt")
            rings.extend(ring(item) for item in polygon)

    try:
        document = json.loads(data.decode("utf-8-sig"), parse_constant=_no_constant)
        if not isinstance(document, dict):
            raise ValueError("oczekiwano obiektu GeoJSON")
        if document.get("type") == "FeatureCollection":
            features = document.get("features")
            if not isinstance(features, list):
                raise ValueError("features musi być listą")
            for feature in features:
                geometry(feature.get("geometry") if isinstance(feature, dict) else None)
        else:
            geometry(
                document.get("geometry")
                if document.get("type") == "Feature"
                else document
            )
        if not rings:
            raise ValueError("brak wielokątów")
        return _Border(rings)
    except (ValueError, IMGWDataError) as exc:
        raise IMGWValidationError(
            f"Plik wyboru obszaru {name} nie jest poprawnym wielokątem GeoJSON: {exc}"
        ) from exc


def _area_stations(
    root: Path, descriptor: DatasetDescriptor, area: _Border
) -> tuple[ProjectFile, list[str]]:
    """Stacje rodziny zbioru z położeniem w obszarze, z bieżącej wersji katalogu (przypinanej)."""
    entry = current_version(root, slot="catalog:pl.imgw.stations")
    if entry is None or entry.version is None or entry.meta is None:
        raise IMGWStoreError(
            f"Brak katalogu stacji w magazynie {root}; najpierw imgw store catalog",
            code="not_found",
        )
    family = (
        "hydro"
        if (descriptor.server_dir or "").startswith("dane_hydrologiczne")
        else "meteo"
    )
    codes = [
        feature.station_code
        for feature in read_catalog(entry.version)
        if feature.geometry is not None
        and feature.properties.get("kind") == family
        and area.contains(*feature.geometry)
    ]
    return ProjectFile(
        "catalog", Path(_store_path(root, entry.version)), entry.meta.sha256
    ), codes


def _new_task(directory: Path, root: Path, request: Mapping[str, Any]) -> ProjectTask:
    command = request["command"]
    options = dict(request["options"])
    if command == _SELECT:
        descriptor = get_dataset(options["dataset"])
        options.setdefault("variables", tuple(descriptor.variables))
        options.setdefault("year_type", descriptor.year_type)
    digests: dict[str, str] | None = None
    pins: tuple[ProjectFile, ...] = ()
    geometry = request.get("geometry")
    relative = ""
    if geometry is not None:
        relative = _input_relative(geometry, directory, "geometry")
        try:
            data = directory.joinpath(*relative.split("/")).read_bytes()
        except OSError as exc:
            raise IMGWValidationError(
                f"Nie można odczytać pliku wyboru obszaru {relative}: {exc}"
            ) from exc
        # Suma dokładnie tych bajtów, z których materializujemy wybór stacji.
        digests = {relative: hashlib.sha256(data).hexdigest()}
        catalog, codes = _area_stations(
            root, get_dataset(options["dataset"]), _area(data, relative)
        )
        options["stations"] = tuple(sorted({*options.get("stations", ()), *codes}))
        if not options["stations"]:
            raise IMGWValidationError(
                f"Wybór obszarem {relative} nie objął żadnej stacji katalogu "
                f"{catalog.path.as_posix()}"
            )
        pins = (catalog,)
    stored = _options_json(
        command,
        commands._validate(command, options, task=True),
        directory,
        root,
        inputs=True,
    )
    if geometry is not None:
        stored["geometry"] = relative
    return ProjectTask(request["name"], command, stored, digests, None, None, pins)


def add_project_task(
    project_dir: PathArg,
    /,
    *,
    name: str,
    command: str,
    options: Mapping[str, object],
    geometry: PathArg | None = None,
) -> Project:
    """
    Add an unpinned task to the project manifest.

    The task options are validated with the command catalog (without ``root``,
    which follows from ``store_dir``) and stored in manifest form. For
    ``series select`` the options ``dataset``, ``stations``, ``variables``,
    ``years`` and ``year_type`` are always stored explicitly; missing
    ``variables`` mean all dataset variables and missing ``year_type`` the ZIP
    numbering of the dataset. A ``geometry`` area selection materializes an
    explicit station list from the current ``stations.geojson`` version, records
    ``geometry_sha256`` and pins that catalog version immediately.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    name : str
        Unique task name, 1-64 characters ``[a-z0-9][a-z0-9_-]*``.
    command : str
        Catalog command of the task (any data command except ``store init`` and
        ``project *``).
    options : Mapping[str, object]
        Options of the task command, or a JSON object string.
    geometry : str or os.PathLike or None, optional
        GeoJSON file (Polygon, MultiPolygon, Feature or FeatureCollection, WGS84)
        inside the project directory selecting stations by area; only for
        ``series select``, where ``stations`` then become optional.

    Returns
    -------
    Project
        The project including the new task.

    Raises
    ------
    IMGWValidationError
        If the command, its options or the geometry file are invalid, or the area
        selection matches no catalog station.
    IMGWProjectError
        If the manifest is missing or invalid, a task with this name already
        exists, or the manifest cannot be locked or written.
    """
    directory = _directory(project_dir)
    before = _load(directory).project
    request = commands.validate_command(
        "project add",
        options={
            "project_dir": directory,
            "name": name,
            "command": command,
            "options": options,
            "geometry": geometry,
        },
    )
    if any(task.name == request["name"] for task in before.tasks):
        raise IMGWProjectError(f"Zadanie {request['name']!r} już istnieje w projekcie")
    task = _new_task(directory, before.store_dir, request)

    def change(current: _Manifest) -> _Manifest:
        if any(existing.name == task.name for existing in current.project.tasks):
            raise IMGWProjectError(f"Zadanie {task.name!r} już istnieje w projekcie")
        return current.with_tasks((*current.project.tasks, task))

    return _update(directory, change)


def remove_project_task(project_dir: PathArg, /, *, name: str) -> Project:
    """
    Remove a task from the project manifest.

    Versions in the store are left untouched.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    name : str
        Name of the task to remove.

    Returns
    -------
    Project
        The project without the task.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a non-empty path.
    IMGWProjectError
        If the manifest is missing or invalid, the task does not exist, or the
        manifest cannot be locked or written.
    """
    directory = _directory(project_dir)

    def change(current: _Manifest) -> _Manifest:
        if not any(task.name == name for task in current.project.tasks):
            raise IMGWProjectError(f"Brak zadania {name!r} w projekcie")
        return current.with_tasks(
            task for task in current.project.tasks if task.name != name
        )

    return _update(directory, change)


# --- stan przypiętych plików -----------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect(
    root: Path,
    pin: ProjectFile,
    *,
    full: bool,
    indexes: dict[Path, SeriesIndex] | None = None,
) -> tuple[PinState, str | None]:
    """Stan pliku offline: istnienie i rozmiar wg sidecara; ``full`` — pełne SHA i spis szeregu."""
    path = root.joinpath(*pin.path.parts)
    if path.is_symlink():
        return "changed", "dowiązanie symboliczne zamiast pliku wersji"
    if not path.exists():
        return "missing", "brak przypiętego pliku w magazynie"
    if not path.is_file():
        return "changed", "przypięta ścieżka nie jest plikiem"
    try:
        if pin.role == "station_series":
            if full:
                version = path.parent.parent
                index = (indexes or {}).get(version) or read_series_index(version)
                if indexes is not None:
                    indexes[version] = index
                entry = index.stations.get(pin.station or "")
                if (
                    entry is None
                    or version / entry.file != path
                    or entry.sha256 != pin.sha256
                ):
                    return (
                        "changed",
                        "spis series.json wersji nie potwierdza przypiętego pliku stacji",
                    )
        else:
            meta = read_meta(path)
            size = path.stat().st_size
            if meta.size_bytes != size:
                return (
                    "changed",
                    f"rozmiar {size} B różni się od sidecara ({meta.size_bytes} B)",
                )
            if meta.sha256 != pin.sha256:
                return "changed", "sidecar wskazuje inną sumę SHA-256 niż przypięta"
        if full:
            actual = _sha256(path)
            if actual != pin.sha256:
                return (
                    "changed",
                    f"suma SHA-256 pliku ({actual}) różni się od przypiętej ({pin.sha256})",
                )
    except (IMGWError, OSError) as exc:
        return "changed", str(exc)
    return "current", None


def _pin_result(
    task: ProjectTask,
    root: Path,
    pin: ProjectFile,
    status: _ResultStatus,
    error: str | None,
) -> OperationResult:
    return OperationResult(
        f"{task.name}:{pin.path.as_posix()}",
        status,
        root.joinpath(*pin.path.parts),
        error,
    )


def _task_result(
    task: ProjectTask, status: _ResultStatus, error: str | None
) -> OperationResult:
    return OperationResult(f"{task.name}:{PROJECT_FILE}", status, None, error)


def _state(task: ProjectTask, states: Iterable[str]) -> TaskStatus:
    found = set(states)
    if task.pinned_at is None:
        return "unpinned"
    if "changed" in found:
        return "changed"
    return "missing" if "missing" in found else "current"


def get_project_status(
    project_dir: PathArg, /, *, tasks: Iterable[str] | None = None
) -> ProjectReport:
    """
    Report the state of pinned files offline, without hashing.

    Each pinned file is checked for existence and for the size and SHA-256 stored
    in its sidecar; station Parquet files are checked for existence only.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    tasks : Iterable[str] or None, optional
        Names of the tasks to check; ``None`` means all tasks.

    Returns
    -------
    ProjectReport
        Status per task (``unpinned``, ``current``, ``missing`` or ``changed``;
        ``changed`` takes precedence over ``missing``) and one result per pinned
        file (``unchanged`` or ``failed`` with an error).

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a path or ``tasks`` is not a collection of names.
    IMGWProjectError
        If the manifest is missing or invalid, or ``tasks`` names unknown tasks.
    """
    project = open_project(project_dir)
    statuses: dict[str, TaskStatus] = {}
    results: list[OperationResult] = []
    for task in _selected(project, tasks):
        states: list[str] = []
        for pin in task.files:
            state, error = _inspect(project.store_dir, pin, full=False)
            states.append(state)
            results.append(
                _pin_result(
                    task,
                    project.store_dir,
                    pin,
                    "unchanged" if state == "current" else "failed",
                    error,
                )
            )
        statuses[task.name] = _state(task, states)
    return ProjectReport(statuses, tuple(results), False)


def verify_project(
    project_dir: PathArg,
    /,
    *,
    tasks: Iterable[str] | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> ProjectReport:
    """
    Verify pinned files offline by full SHA-256.

    In addition to `get_project_status`, the full SHA-256 of every pinned file,
    the consistency of its sidecar and, for station files, the ``series.json``
    index of the series version are checked.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    tasks : Iterable[str] or None, optional
        Names of the tasks to verify; ``None`` means all tasks.
    on_progress : ProgressHook or None, optional
        Called after each verified file with ``Progress(unit="file")``.
    on_notice : NoticeHook or None, optional
        Receives an ``error`` notice with code ``pin_mismatch`` for each file
        that does not match its pin.
    cancel : Cancel or None, optional
        Checked before each file; once it returns true the remaining files are
        reported as ``cancelled``.

    Returns
    -------
    ProjectReport
        Status per task (``unpinned``, ``current``, ``missing``, ``changed`` or
        ``cancelled``) and one result per pinned file (``unchanged``, ``failed``
        or ``cancelled``); ``cancelled`` is true when verification was stopped.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a path or ``tasks`` is not a collection of names.
    IMGWProjectError
        If the manifest is missing or invalid, or ``tasks`` names unknown tasks.
    """
    project = open_project(project_dir)
    selected = _selected(project, tasks)
    root = project.store_dir
    total = sum(len(task.files) for task in selected)
    indexes: dict[Path, SeriesIndex] = {}
    statuses: dict[str, TaskStatus] = {}
    results: list[OperationResult] = []
    done = 0
    stopped = False
    for task in selected:
        states: list[str] = []
        for pin in task.files:
            stopped = stopped or (cancel is not None and cancel())
            if stopped:
                results.append(_pin_result(task, root, pin, "cancelled", CANCELLED))
                continue
            state, error = _inspect(root, pin, full=True, indexes=indexes)
            states.append(state)
            results.append(
                _pin_result(
                    task,
                    root,
                    pin,
                    "unchanged" if state == "current" else "failed",
                    error,
                )
            )
            if state != "current":
                _notice(
                    on_notice,
                    "error",
                    "pin_mismatch",
                    f"{task.name}: {pin.path.as_posix()}: {error}",
                )
            done += 1
            if on_progress is not None:
                on_progress(Progress(done, total, "file", state, pin.path.as_posix()))
        stopped = stopped or (not task.files and cancel is not None and cancel())
        statuses[task.name] = (
            "cancelled"
            if stopped and len(states) < max(len(task.files), 1)
            else _state(task, states)
        )
    return ProjectReport(statuses, tuple(results), stopped)


# --- sprawdzenie bez zapisu --------------------------------------------------------------------


def _select_options(task: ProjectTask, root: Path) -> dict[str, Any]:
    options = {
        name: value for name, value in task.options.items() if name != "geometry"
    }
    return commands.validate_command(_SELECT, options={**options, "root": root})


def _command_options(task: ProjectTask, directory: Path, root: Path) -> dict[str, Any]:
    """Opcje uruchomienia: ścieżki projektu/magazynu jako bezwzględne, ``root`` = ``store_dir``."""
    spec = _OPTIONS[task.command]
    options: dict[str, Any] = {}
    for name, value in task.options.items():
        if spec[name].type == "path":
            value = (root if name == "version" else directory).joinpath(
                *str(value).split("/")
            )
        options[name] = value
    if "root" in spec:
        options["root"] = root
    if "output" in spec and "output" not in options:
        # Domyślny katalog datasets download liczymy względem projektu, nie bieżącego katalogu.
        options["output"] = directory / commands._DEFAULT_OUTPUT
    return options


def _archive_years(options: Mapping[str, Any]) -> tuple[int, ...]:
    """Roczniki archiwów pokrywające wybrane lata (inna numeracja ZIP = także rocznik sąsiedni)."""
    descriptor = get_dataset(options["dataset"])
    years = set(options["years"])
    if options["year_type"] != descriptor.year_type:
        shift = 1 if descriptor.year_type == "hydrological" else -1
        for year in options["years"]:
            with suppress(
                IMGWValidationError
            ):  # rocznik sprzed pierwszego archiwum zbioru
                archive_files(descriptor.key, years=(year + shift,))
                years.add(year + shift)
    return tuple(sorted(years))


def _check_task(
    root: Path, directory: Path, task: ProjectTask, hooks: Hooks
) -> tuple[_PlanStatus, str, StorePlan | None]:
    states = [_inspect(root, pin, full=False) for pin in task.files]
    try:
        if task.command == _SELECT:
            options = _select_options(task, root)
            plan = check_store(
                root,
                datasets=(options["dataset"],),
                years=_archive_years(options),
                **hooks,
            )
        else:
            checked = commands.check_command(
                task.command, options=_command_options(task, directory, root), **hooks
            ).result
            if checked is None:  # anulowanie bez planu
                return "unverifiable", CANCELLED, None
            plan = checked
    except IMGWError as exc:
        return "check_failed", str(exc), None
    found = [(item.status, item.error) for item in plan.items] + [
        (action.status, action.detail) for action in plan.actions
    ]
    failed = [
        detail or "błąd sprawdzenia"
        for status, detail in found
        if status == "check_failed"
    ]
    changed = [
        f"{pin.path.as_posix()}: {error}"
        for pin, (state, error) in zip(task.files, states, strict=True)
        if state == "changed"
    ]
    missing = sum(state == "missing" for state, _ in states)
    if plan.cancelled:
        return "unverifiable", CANCELLED, plan
    if failed:
        return "check_failed", "; ".join(failed), plan
    if changed:
        return (
            "check_failed",
            f"zmienione przypięte pliki (nie do odtworzenia): {'; '.join(changed)}",
            plan,
        )
    if task.pinned_at is None:
        return (
            "missing",
            "zadanie nieprzypięte: project download pobierze dane i przypnie pliki",
            plan,
        )
    if missing:
        return (
            "missing",
            (
                f"brak {missing} przypiętych plików; project download odtworzy je wyłącznie "
                "przy identycznym SHA-256"
            ),
            plan,
        )
    if any(status in ("newer", "missing") for status, _ in found):
        return (
            "newer",
            f"dostępne nowsze lub brakujące dane źródłowe; piny zmieni wyłącznie {_UPGRADE}",
            plan,
        )
    if any(
        status == "unverifiable" and detail != UNPUBLISHED for status, detail in found
    ):
        return (
            "unverifiable",
            "brak porównywalnego sygnału aktualności części danych",
            plan,
        )
    return "current", "przypięte pliki obecne, dane aktualne", plan


def _store_ready(root: Path) -> bool:
    try:
        return store_info(root).supported
    except IMGWError:
        return False


def check_project(
    project_dir: PathArg,
    /,
    *,
    tasks: Iterable[str] | None = None,
    plan: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan the project tasks as ``imgw-plan/1`` without writing or downloading.

    Only listings, HEAD requests and the state of pins are used. A ``series
    select`` task is checked with `check_store` over the archive years covering
    its selection; other tasks with `check_command`. Each task adds one
    ``project download`` action with status ``check_failed`` (check error or
    changed pin), ``missing`` (unpinned task, missing pins or missing store),
    ``newer`` (newer or missing data, applied only by an upgrade),
    ``unverifiable`` or ``current``.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    tasks : Iterable[str] or None, optional
        Names of the tasks to check; ``None`` means all tasks.
    plan : str, os.PathLike or None, optional
        File to save the plan to (``imgw-plan/1``, see `StorePlan.to_json`);
        it must lie outside the project store in an existing directory and is
        checked before any request.
    on_progress : ProgressHook or None, optional
        Called after each task with ``Progress(unit="task")``.
    on_notice : NoticeHook or None, optional
        Receives notices of the underlying store checks.
    cancel : Cancel or None, optional
        Checked before each task; the remaining tasks are reported as
        ``unverifiable`` and the plan as cancelled.

    Returns
    -------
    StorePlan
        Combined plan with ``root`` equal to the project store.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a path, ``tasks`` is not a collection of names
        or ``plan`` lies inside the store or in a missing directory.
    IMGWProjectError
        If the manifest is missing or invalid, or ``tasks`` names unknown tasks.
    """
    project = open_project(project_dir)
    selected = _selected(project, tasks)
    root = project.store_dir
    target = _plan_target(root, plan) if plan is not None else None
    hooks = {"on_progress": on_progress, "on_notice": on_notice, "cancel": cancel}
    ready = _store_ready(root)
    items: dict[str, PlanItem] = {}
    series_state: dict[str, Any] = {}
    actions: list[PlanAction] = []
    cancelled = False
    for index, task in enumerate(selected, start=1):
        cancelled = cancelled or (cancel is not None and cancel())
        checked: StorePlan | None = None
        if cancelled:
            status, detail = "unverifiable", CANCELLED
        elif not ready:
            status, detail = (
                "missing",
                f"magazyn {root} nie istnieje; project download utworzy go i pobierze dane",
            )
        else:
            status, detail, checked = _check_task(root, project.path, task, hooks)
        if checked is not None:
            for item in checked.items:
                items.setdefault(item.archive.server_path, item)
            for slug, state in checked.series_state.items():
                series_state[slug] = max(
                    state, series_state.get(slug, state), key=_SEVERITY.__getitem__
                )
            actions.extend(
                PlanAction(
                    action.command, action.status, f"{task.name}: {action.detail}"
                )
                for action in checked.actions
            )
            cancelled = cancelled or checked.cancelled
        actions.append(PlanAction("project download", status, f"{task.name}: {detail}"))
        if on_progress is not None:
            on_progress(
                Progress(index, len(selected), "task", status, f"Zadanie {task.name}")
            )
    result = StorePlan(
        "imgw-plan/1",
        root,
        datetime.now(UTC),
        tuple(items.values()),
        series_state,
        tuple(actions),
        cancelled,
    )
    if target is not None:
        result.to_json(target)
    return result


# --- pobieranie, przypinanie i odtwarzanie ----------------------------------------------------


@dataclass
class _Produced:
    """Wynik operacji zadania: pliki do przypięcia, statusy operacji per ścieżka, błędy."""

    pins: list[ProjectFile] = field(default_factory=list)
    statuses: dict[str, _ResultStatus] = field(default_factory=dict)
    failures: list[OperationResult] = field(default_factory=list)
    cancelled: bool = False


@dataclass(frozen=True)
class _Outcome:
    status: TaskStatus
    files: tuple[OperationResult, ...]
    task: ProjectTask | None = (
        None  # nowy stan zadania do scalenia; None = manifest bez zmian
    )


def _series_pins(
    root: Path, version: Path, stations: Iterable[str] | None
) -> list[ProjectFile]:
    """``series.json``, pliki wybranych (albo wszystkich) stacji oraz wejścia z sidecara wersji."""
    index = read_series_index(version)
    meta = read_meta(version)
    pins = [ProjectFile("series", Path(_store_path(root, version)), meta.sha256)]
    for code in index.stations if stations is None else stations:
        entry = index.stations[code]
        pins.append(
            ProjectFile(
                "station_series",
                Path(_store_path(root, version.parent / entry.file)),
                entry.sha256,
                code,
            )
        )
    try:
        sources = meta.extra["source_files"]
        if not isinstance(sources, Iterable):
            raise TypeError(f"source_files nie jest listą: {sources!r}")
        pins.extend(
            ProjectFile("input", Path(str(source["file"])), str(source["sha256"]))
            for source in sources
        )
    except (KeyError, TypeError) as exc:
        raise IMGWDataError(
            f"Sidecar szeregu {version} nie wymienia poprawnie plików wejściowych"
        ) from exc
    return pins


def _add_sync(
    produced: _Produced, root: Path, task: ProjectTask, report: SyncReport, *, pin: bool
) -> None:
    produced.cancelled = produced.cancelled or report.cancelled
    for item in report.items:
        if item.status not in _DONE:
            produced.cancelled = produced.cancelled or item.status == "cancelled"
            produced.failures.append(
                OperationResult(
                    f"{task.name}:{item.slot}", item.status, item.version, item.error
                )
            )
        elif item.version is not None:
            path = _store_path(root, item.version)
            produced.statuses[path] = item.status
            if pin:
                produced.pins.append(
                    ProjectFile("input", Path(path), read_meta(item.version).sha256)
                )


def _add_series(
    produced: _Produced,
    root: Path,
    task: ProjectTask,
    report: SeriesReport,
    stations: Iterable[str] | None,
) -> None:
    if report.status == "cancelled":
        produced.cancelled = True
        produced.failures.append(
            OperationResult(f"{task.name}:series", "cancelled", None, CANCELLED)
        )
    elif report.status == "failed" or report.version is None:
        produced.failures.append(
            OperationResult(
                f"{task.name}:series",
                "failed",
                report.version,
                "; ".join(report.problems) or "budowa szeregu nie powiodła się",
            )
        )
    else:
        pins = _series_pins(root, report.version, stations)
        produced.statuses.update(
            (pin.path.as_posix(), report.status) for pin in pins if pin.role != "input"
        )
        produced.pins.extend(pins)


def _add_version(
    produced: _Produced,
    root: Path,
    task: ProjectTask,
    role: Literal["catalog", "input"],
    status: _ResultStatus,
    version: Path | None,
    problems: Iterable[str],
) -> None:
    if status == "cancelled":
        produced.cancelled = True
        produced.failures.append(_task_result(task, "cancelled", CANCELLED))
    elif status == "failed" or version is None:
        produced.failures.append(
            _task_result(
                task, "failed", "; ".join(problems) or f"{task.command}: niepowodzenie"
            )
        )
    else:
        path = _store_path(root, version)
        produced.statuses[path] = status
        produced.pins.append(ProjectFile(role, Path(path), read_meta(version).sha256))


def _subplan(plan: StorePlan, archives: Iterable[ArchiveFile]) -> StorePlan:
    wanted = {archive.server_path for archive in archives}
    items = tuple(item for item in plan.items if item.archive.server_path in wanted)
    absent = sorted(wanted - {item.archive.server_path for item in items})
    if absent:
        raise IMGWValidationError(
            f"Plan nie obejmuje archiwów zadania ({', '.join(absent[:3])}"
            f"{' …' if len(absent) > 3 else ''}); uruchom ponownie project check"
        )
    return replace(plan, items=items, series_state={}, actions=())


def _produce_select(
    root: Path, task: ProjectTask, plan: StorePlan | None, hooks: Hooks
) -> _Produced:
    """Komenda ``series select``: synchronizacja roczników zadania, budowa szeregu zbioru, walidowany wybór."""
    options = _select_options(task, root)
    dataset = options["dataset"]
    years = _archive_years(options)
    if plan is None:
        report = sync_store(
            root, datasets=(dataset,), years=years, series=False, **hooks
        )
    else:
        report = sync_store(
            root,
            plan=_subplan(plan, archive_files(dataset, years=years)),
            series=False,
            **hooks,
        )
    produced = _Produced()
    _add_sync(produced, root, task, report, pin=False)
    if produced.cancelled or produced.failures:
        return produced
    series = build_series(root, dataset=dataset, **hooks)
    stations: tuple[str, ...] = ()
    if series.status in ("created", "reused") and series.version is not None:
        stations = select_series(
            root,
            dataset=dataset,
            stations=options["stations"],
            variables=options.get("variables"),
            years=options.get("years"),
            year_type=options.get("year_type"),
        ).stations
    _add_series(produced, root, task, series, stations)
    return produced


def _produce_command(
    root: Path, directory: Path, task: ProjectTask, hooks: Hooks
) -> _Produced:
    """Pozostałe komendy: jeden dispatcher ``run_command``; przypina wersje wskazane w wyniku."""
    result = commands.run_command(
        task.command, options=_command_options(task, directory, root), **hooks
    ).result
    produced = _Produced()
    if result is None:  # IMGWCancelledError: anulowanie bez raportu
        produced.cancelled = True
        produced.failures.append(_task_result(task, "cancelled", CANCELLED))
    elif isinstance(result, SyncReport):
        _add_sync(produced, root, task, result, pin=True)
        for series in result.series:
            _add_series(produced, root, task, series, None)
    elif isinstance(result, SeriesReport):
        _add_series(produced, root, task, result, None)
    elif isinstance(result, CatalogReport):
        _add_version(
            produced,
            root,
            task,
            "catalog",
            result.status,
            result.version,
            result.problems,
        )
    elif isinstance(result, PMaXTPStoreResult):
        _add_version(produced, root, task, "input", result.status, result.version, ())
    elif isinstance(result, DownloadReport):
        produced.cancelled = result.cancelled
        produced.failures.extend(
            _task_result(task, "failed", f"{item.url}: {item.error}")
            for item in result.items
            if item.status == "failed"
        )
    return produced


def _ordered(pins: Iterable[ProjectFile]) -> tuple[ProjectFile, ...]:
    unique: dict[str, ProjectFile] = {}
    for pin in pins:
        unique.setdefault(pin.path.as_posix(), pin)
    return tuple(
        sorted(
            unique.values(),
            key=lambda pin: (_ROLES.index(pin.role), pin.path.as_posix()),
        )
    )


def _pin(
    root: Path, directory: Path, task: ProjectTask, plan: StorePlan | None, hooks: Hooks
) -> _Outcome:
    """Pierwsze przypięcie albo upgrade: nowe piny całego zadania wyłącznie po pełnym sukcesie."""
    if task.command == _SELECT:
        produced = _produce_select(root, task, plan, hooks)
    else:
        produced = _produce_command(root, directory, task, hooks)
    if produced.cancelled:
        return _Outcome(
            "cancelled",
            tuple(produced.failures) or (_task_result(task, "cancelled", CANCELLED),),
        )
    if produced.failures:
        reasons = "; ".join(
            result.error or result.status for result in produced.failures
        )
        _notice(
            hooks["on_notice"],
            "error",
            "task_failed",
            f"Zadanie {task.name}: {reasons}; przypięcia bez zmian",
        )
        return _Outcome("failed", tuple(produced.failures))
    # Wybór obszarem materializowano raz z konkretnej wersji katalogu: jej pin zostaje.
    kept = [
        pin for pin in task.files if task.command == _SELECT and pin.role == "catalog"
    ]
    files = _ordered([*kept, *produced.pins])
    results = tuple(
        _pin_result(
            task,
            root,
            pin,
            produced.statuses.get(pin.path.as_posix(), "unchanged"),
            None,
        )
        for pin in files
    )
    if task.pinned_at is not None and set(files) == set(task.files):
        return _Outcome("current", results)
    pinned = replace(
        task,
        files=files,
        pinned_at=datetime.now(UTC).replace(microsecond=0),
        imgwtools_version=__version__,
    )
    return _Outcome(
        "upgraded" if task.pinned_at is not None else "current", results, pinned
    )


def _archive_of(path: Path) -> ArchiveFile:
    """Archiwum rejestru dla ścieżki wersji ``archives/versions/<katalog>/<stem>/<wersja>/<plik>``."""
    parts = path.parts
    server_path = "/".join((*parts[2:-3], parts[-1]))
    for descriptor in datasets():
        if (
            not descriptor.in_store
            or descriptor.time_unit not in _SERIES_UNITS
            or not server_path.startswith(f"{descriptor.server_dir}/")
        ):
            continue
        for year in sorted({int(text) for text in _YEAR.findall(server_path)}):
            try:
                candidates = archive_files(descriptor.key, years=(year,))
            except IMGWValidationError:
                continue
            for candidate in candidates:
                if candidate.server_path == server_path:
                    return candidate
    raise IMGWProjectError(
        f"Przypięty plik {path.as_posix()} nie odpowiada archiwum rejestru IMGW"
    )


def _recreate_archive(root: Path, pin: ProjectFile, hooks: Hooks) -> str | None:
    """GET archiwum i publikacja wersji; sukces tylko przy identycznym SHA pod przypiętą ścieżką."""
    key = pin.path.as_posix()
    try:
        archive = _archive_of(pin.path)
        written = write_archive(
            root,
            archive=archive,
            response=_download(archive),
            on_notice=hooks["on_notice"],
            cancel=hooks["cancel"],
        )
    except IMGWError as exc:
        return f"Nie odtworzono {key}: {exc}"
    if written.sha256 != pin.sha256:
        return (
            f"IMGW udostępnia inną treść {archive.server_path} (SHA-256 {written.sha256}) niż przypięta "
            f"({pin.sha256}); przypięcia bez zmian, {_UPGRADE}"
        )
    written_path = _store_path(root, written.path)
    if written_path != key:
        return (
            f"Identyczne bajty zapisano jako {written_path}; przypięta wersja {key} pozostaje "
            f"niedostępna, {_UPGRADE}"
        )
    return None


def _recreate_series(
    root: Path, task: ProjectTask, slug: str, hooks: Hooks
) -> str | None:
    """Szereg odtwarza się wyłącznie, gdy bieżące wersje archiwów zbioru = przypięte wejścia."""
    descriptor = next(
        (
            item
            for item in datasets()
            if item.slug == slug and item.in_store and item.time_unit in _SERIES_UNITS
        ),
        None,
    )
    if descriptor is None:
        return f"Nieznany zbiór szeregu {slug}"
    prefix = f"archives/versions/{descriptor.server_dir}/"
    pinned = {
        (pin.path.as_posix(), pin.sha256)
        for pin in task.files
        if pin.role == "input" and pin.path.as_posix().startswith(prefix)
    }
    try:
        current = {
            (item.local_path.as_posix(), item.local_sha256)
            for item in check_series(root, dataset=descriptor.key).items
            if item.local_path is not None
        }
        if not pinned or current != pinned:
            return (
                f"Bieżące wersje archiwów zbioru {descriptor.key} różnią się od przypiętych wejść szeregu; "
                f"identycznej wersji nie można zbudować, {_UPGRADE}"
            )
        report = build_series(root, dataset=descriptor.key, **hooks)
    except IMGWError as exc:
        return f"Nie odtworzono szeregu {slug}: {exc}"
    if report.status == "cancelled":
        return CANCELLED
    if report.status == "failed":
        return "; ".join(report.problems) or "budowa szeregu nie powiodła się"
    return None


def _recreate(
    root: Path, task: ProjectTask, missing: Iterable[ProjectFile], hooks: Hooks
) -> tuple[dict[ProjectFile, str], bool]:
    """Odtwórz brakujące wersje: archiwa (GET + SHA), potem szeregi z przypiętych wejść."""
    cancel = hooks["cancel"]
    errors: dict[ProjectFile, str] = {}
    cancelled = False
    series: dict[str, list[ProjectFile]] = {}
    for pin in missing:
        kind = pin.path.parts[0]
        if kind == "series":
            series.setdefault(pin.path.parts[2], []).append(pin)
            continue
        if kind != "archives":
            errors[pin] = (
                f"Wersji {pin.path.as_posix()} nie można odtworzyć: etykieta katalogu/komórki "
                f"pochodzi z dnia pobrania; {_UPGRADE}"
            )
            continue
        cancelled = cancelled or (cancel is not None and cancel())
        error = CANCELLED if cancelled else _recreate_archive(root, pin, hooks)
        if error is not None:
            errors[pin] = error
    for slug, pins in series.items():
        cancelled = cancelled or (cancel is not None and cancel())
        error = CANCELLED if cancelled else _recreate_series(root, task, slug, hooks)
        if error is not None:
            errors.update((pin, error) for pin in pins)
    return errors, cancelled


def _restore(root: Path, task: ProjectTask, hooks: Hooks) -> _Outcome:
    """Tryb ``pinned`` dla przypiętego zadania: piny bez zmian, brakujące pliki tylko identyczne."""
    states = {pin: _inspect(root, pin, full=False) for pin in task.files}
    missing = {pin for pin in task.files if states[pin][0] == "missing"}
    ordered = [pin for pin in task.files if pin in missing]
    errors, cancelled = (
        _recreate(root, task, ordered, hooks) if ordered else ({}, False)
    )
    results: list[OperationResult] = []
    failed = changed = False
    for pin in task.files:
        if pin in missing:
            state, error = _inspect(root, pin, full=True)
            if state == "current":
                results.append(_pin_result(task, root, pin, "created", None))
                continue
            error = errors.get(pin) or error
            failed = True
            results.append(
                _pin_result(
                    task,
                    root,
                    pin,
                    "cancelled" if error == CANCELLED else "failed",
                    error,
                )
            )
        else:
            state, error = states[pin]
            changed = changed or state == "changed"
            results.append(
                _pin_result(
                    task,
                    root,
                    pin,
                    "unchanged" if state == "current" else "failed",
                    error,
                )
            )
    status: TaskStatus = (
        "cancelled"
        if cancelled
        else "failed"
        if failed
        else "changed"
        if changed
        else "current"
    )
    if status in ("failed", "changed"):
        reasons = "; ".join(
            f"{result.slot}: {result.error}"
            for result in results
            if result.status == "failed"
        )
        _notice(
            hooks["on_notice"],
            "error",
            "task_failed",
            f"Zadanie {task.name}: {reasons}; przypięcia bez zmian",
        )
    return _Outcome(status, tuple(results))


def _ensure_store(root: Path) -> None:
    if root.exists() and not (root.is_dir() and not any(root.iterdir())):
        open_store(root)
    else:
        init_store(root)


def download_project(
    project_dir: PathArg,
    /,
    *,
    tasks: Iterable[str] | None = None,
    plan: StorePlan | PathArg | None = None,
    update: Literal["pinned", "upgrade"] = "pinned",
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> ProjectReport:
    """
    Download the data of project tasks and pin the resulting store versions.

    Unpinned tasks, and every task with ``update="upgrade"``, are produced and
    pinned: ``series select`` synchronizes the archive years covering the
    selection, builds the dataset series and pins ``series.json``, the selected
    station files and the input archives; other commands run through
    `run_command` with ``root=store_dir`` and pin the versions named in their
    result. New pins replace the whole task only after full success. With
    ``update="pinned"`` an already pinned task keeps its pins: missing archives
    are downloaded again and missing series rebuilt only when the result is
    identical to the pin; catalog and PMAXTP versions are not recreated. Each
    task result is merged into the current manifest under the lock; a task
    changed meanwhile by another process fails with ``project_conflict``.

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    tasks : Iterable[str] or None, optional
        Names of the tasks to download; ``None`` means all tasks.
    plan : StorePlan or str or os.PathLike or None, optional
        Fresh ``imgw-plan/1`` plan (object or JSON file) of the same store; only
        its items for the archives of a ``series select`` task are used.
    update : {"pinned", "upgrade"}, optional
        ``"pinned"`` never re-pins pinned tasks; ``"upgrade"`` re-pins whole
        tasks after full success.
    on_progress : ProgressHook or None, optional
        Called after each task with ``Progress(unit="task")`` and forwarded to
        the underlying operations.
    on_notice : NoticeHook or None, optional
        Receives ``error`` notices with codes ``task_failed`` and
        ``project_conflict`` and the notices of the underlying operations.
    cancel : Cancel or None, optional
        Checked before each task and by the underlying operations; the
        remaining tasks are reported as ``cancelled``.

    Returns
    -------
    ProjectReport
        Status per task (``current``, ``upgraded``, ``changed``, ``failed`` or
        ``cancelled``) and the per-file results; ``cancelled`` is true when the
        run was stopped.

    Raises
    ------
    IMGWValidationError
        If ``update`` is invalid, ``plan`` concerns a different store, or
        ``project_dir``/``tasks`` are invalid.
    IMGWProjectError
        If the manifest is missing or invalid, or ``tasks`` names unknown tasks.
    IMGWStoreError
        If the store directory cannot be opened or initialized.
    """
    if update not in ("pinned", "upgrade"):
        raise IMGWValidationError(
            f'Nieprawidłowy tryb update {update!r}; dozwolone: "pinned", "upgrade"'
        )
    project = open_project(project_dir)
    selected = _selected(project, tasks)
    root = project.store_dir
    if plan is not None and not isinstance(plan, StorePlan):
        plan = StorePlan.from_json(plan)
    if plan is not None and Path(plan.root).expanduser().absolute() != root:
        raise IMGWValidationError(
            f"Plan dotyczy innego magazynu ({plan.root}) niż projekt ({root})"
        )
    hooks = {"on_progress": on_progress, "on_notice": on_notice, "cancel": cancel}
    statuses: dict[str, TaskStatus] = {}
    results: list[OperationResult] = []
    stopped = False
    for index, task in enumerate(selected, start=1):
        stopped = stopped or (cancel is not None and cancel())
        if stopped:
            outcome = _Outcome(
                "cancelled", (_task_result(task, "cancelled", CANCELLED),)
            )
        else:
            if index == 1:
                _ensure_store(root)
            try:
                if task.pinned_at is None or update == "upgrade":
                    outcome = _pin(root, project.path, task, plan, hooks)
                else:
                    outcome = _restore(root, task, hooks)
            except IMGWError as exc:
                _notice(
                    on_notice, "error", "task_failed", f"Zadanie {task.name}: {exc}"
                )
                outcome = _Outcome("failed", (_task_result(task, "failed", str(exc)),))
            if outcome.task is not None:
                try:
                    _commit(project.path, task, outcome.task)
                except IMGWProjectError as exc:
                    _notice(
                        on_notice,
                        "error",
                        "project_conflict",
                        f"Zadanie {task.name}: {exc}",
                    )
                    outcome = _Outcome(
                        "failed",
                        (*outcome.files, _task_result(task, "failed", str(exc))),
                    )
            stopped = outcome.status == "cancelled"
        statuses[task.name] = outcome.status
        results.extend(outcome.files)
        if on_progress is not None:
            on_progress(
                Progress(
                    index, len(selected), "task", outcome.status, f"Zadanie {task.name}"
                )
            )
    return ProjectReport(statuses, tuple(results), stopped)
