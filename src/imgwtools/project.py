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
from typing import Any, Literal, cast

from imgwtools import commands
from imgwtools._version import __version__
from imgwtools.datasets import (
    _CATALOG_DATASETS,
    CATALOG_DATASET,
    STATION_CODE_PATTERN,
    ArchiveFile,
    DatasetDescriptor,
    _archive_from_path,
    archive_files,
    get_dataset,
    get_provider,
    providers,
)
from imgwtools.exceptions import (
    ErrorCode,
    IMGWDataError,
    IMGWError,
    IMGWProjectError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import UNPUBLISHED
from imgwtools.messages import message, reason
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
from imgwtools.store.catalog import _NESTED_CATALOGS, CATALOG_FILE, _Border
from imgwtools.store.content import CONTENT_FORMS, content_sha256
from imgwtools.store.pmaxtp import CELL_FILE
from imgwtools.store.reader import (
    _CELL,
    _PMAXTP_KEY,
    SERIES_FILE,
    _archive_slot,
    _series_datasets,
)
from imgwtools.store.sync import CANCELLED, _download, _plan_target
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
    "unpinned",
    "current",
    "content_match",
    "missing",
    "changed",
    "upgraded",
    "failed",
    "cancelled",
]
# content_match: the pinned path is gone, but the current version of its slot carries
# the pinned content (ADR-003 D14) — never reported silently as current.
PinState = Literal["current", "content_match", "missing", "changed"]
Hooks = Mapping[str, Any]
_ResultStatus = Literal[
    "new",
    "relabeled",
    "unchanged",
    "restored_by_content",
    "failed",
    "stale_plan",
    "cancelled",
]
_PlanStatus = Literal["current", "newer", "missing", "unverifiable", "check_failed"]

_SELECT = "series select"
# Opcje zadania series select zapisane w manifeście zawsze jawnie.
_EXPLICIT = ("dataset", "stations", "variables", "years", "year_type")
_ROLES = ("series", "station_series", "catalog", "input")
_TOP_KEYS = (("schema", "store_dir", "tasks"), ("extensions",))
_TASK_KEYS = (
    ("name", "command", "options", "pinned_at", "imgwtools_version", "files"),
    ("geometry_sha256",),
)
_FILE_KEYS = (
    ("role", "path", "sha256"),
    ("station_code", "content_sha256", "content_form"),
)
_SHA = re.compile(r"[0-9a-f]{64}")
_STATION = re.compile(STATION_CODE_PATTERN)
_DRIVE = re.compile(r"[A-Za-z]:")
_MATCHED = "pin_restored_by_content"
_DONE = ("new", "relabeled", "unchanged")
_SERIES_UNITS = ("day", "month", "half_year")
_SEVERITY = {"current": 0, "outdated": 1, "missing": 2}
_UPGRADE = message("project.upgrade_hint")
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
    if pin.station_code is not None:
        data["station_code"] = pin.station_code
    # Pola treści mają wyłącznie piny zbiorów z formą kanoniczną; nigdy null.
    if pin.content_sha256 is not None:
        data["content_sha256"] = pin.content_sha256
    if pin.content_form is not None:
        data["content_form"] = pin.content_form
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


def _pin_slot(path: Path, station_code: str | None) -> str | None:
    """
    Slot (spec §13.7) of a pinned version file, or None for any other path.

    Archives map their server path through the store registry, series files
    of a station carry the station selector ``series:<key>:<station_code>``.
    """
    parts = path.as_posix().split("/")
    kind = parts[0]
    if kind == "archives" and len(parts) >= 6 and parts[1] == "versions":
        if Path(parts[-1]).stem != parts[-3]:
            return None
        return _archive_slot("/".join((*parts[2:-3], parts[-1])))
    if kind == "series" and len(parts) in (5, 6) and parts[1] == "versions":
        descriptor = _series_datasets().get(parts[2])
        if descriptor is None:
            return None
        if len(parts) == 5 and parts[4] == SERIES_FILE:
            return f"series:{descriptor.key}"
        if (
            len(parts) == 6
            and station_code is not None
            and parts[4:] == ["stations", f"{station_code}.parquet"]
        ):
            return f"series:{descriptor.key}:{station_code}"
        return None
    if kind == "stations" and parts[1:2] == ["versions"] and parts[-1] == CATALOG_FILE:
        # The IMGW-PIB catalog keeps the 3.0.0 layout; another provider's catalog
        # lies in its slug directory (``stations/versions/chmi_stations/…``).
        if len(parts) == 4 and parts[2] not in _NESTED_CATALOGS:
            return f"catalog:{CATALOG_DATASET}"
        if len(parts) == 5 and parts[2] in _NESTED_CATALOGS:
            return f"catalog:{_CATALOG_DATASETS[_NESTED_CATALOGS[parts[2]]]}"
        return None
    if (
        kind == "pmaxtp"
        and len(parts) == 6
        and parts[1] == "versions"
        and parts[2] in ("POT", "AMP")
        and _CELL.match(parts[3])
        and parts[5] == CELL_FILE
    ):
        return f"pmaxtp:{_PMAXTP_KEY}:{parts[2]}/{parts[3]}"
    return None


# --- walidacja -------------------------------------------------------------------------------


def _invalid(
    where: str, problem: str, details: Mapping[str, object] | None = None
) -> IMGWProjectError:
    return IMGWProjectError(
        f"{PROJECT_FILE}: {where}: {problem}"
        if where
        else f"{PROJECT_FILE}: {problem}",
        details=details,
    )


def _object(
    value: object, keys: tuple[tuple[str, ...], tuple[str, ...]], where: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(where, message("project.json_object_was_expected"))
    required, optional = keys
    unknown = [
        repr(key) for key in value if key not in required and key not in optional
    ]
    if unknown:
        raise _invalid(
            where,
            message(
                "project.unknown_keys_extras_only_extensions",
                unknown=", ".join(unknown),
            ),
        )
    missing = [key for key in required if key not in value]
    if missing:
        raise _invalid(
            where, message("project.missing_keys", missing=", ".join(missing))
        )
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
        raise IMGWValidationError(
            message("project.must_relative_posix_path", name=name, value=value),
            details={"option": name},
        )
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise IMGWValidationError(
            message("project.must_not_contain_empty_segments", name=name, text=text),
            details={"option": name, "value": text},
        )
    path = base.joinpath(*parts)
    for step in (path, *path.parents):
        if step == base:
            break
        if step.is_symlink():
            raise IMGWValidationError(
                message("project.symbolic_link_path", name=name, step=step),
                details={"option": name, "value": text},
            )
    return text


def _input_relative(value: PathArg, base: Path, name: str) -> str:
    """Ścieżka z wywołania: względna wobec ``base`` albo bezwzględna wewnątrz ``base``."""
    path = Path(os.fspath(value))
    if path.is_absolute():
        if ".." in path.parts:
            raise IMGWValidationError(
                message("project.must_not_contain", name=name, value=value),
                details={"option": name},
            )
        try:
            path = path.relative_to(base)
        except ValueError:
            raise IMGWValidationError(
                message(
                    "project.must_lie_directory", name=name, base=base, value=value
                ),
                details={"option": name},
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
        raise IMGWValidationError(
            message("project.options_task_must_json_object"),
            details={"option": "options"},
        )
    options = dict(raw)
    area = "geometry" in options
    geometry = options.pop("geometry", None)
    normalized = commands._validate(command, options, task=True)
    result = _options_json(command, normalized, directory, root, inputs=False)
    if command == _SELECT:
        missing = [name for name in _EXPLICIT if name not in normalized]
        if missing:
            raise IMGWValidationError(
                message(
                    "project.series_select_task_needs_explicit",
                    missing=", ".join(missing),
                ),
                details={"option": missing[0]},
            )
    if area:
        if command != _SELECT:
            raise IMGWValidationError(
                message("project.option_geometry_applies_only_series"),
                details={"option": "geometry"},
            )
        result["geometry"] = _relative(geometry, directory, "geometry")
    return result


def _moment(value: object, where: str) -> datetime | None:
    if value is None:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError(message("project.iso_8601_text_was_expected"))
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(where, message("project.invalid_date", exc=reason(exc))) from exc
    if moment.tzinfo is None:
        raise _invalid(where, message("project.date_must_contain_time_zone"))
    return moment.astimezone(UTC)


def _parse_file(raw: object, where: str, root: Path) -> ProjectFile:
    data = _object(raw, _FILE_KEYS, where)
    role = data["role"]
    if role not in _ROLES:
        raise _invalid(
            f"{where}.role",
            message("project.unknown_role_allowed", role=role, roles=", ".join(_ROLES)),
        )
    try:
        path = _relative(data["path"], root, "path")
    except IMGWValidationError as exc:
        raise _invalid(f"{where}.path", reason(exc)) from exc
    sha = data["sha256"]
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise _invalid(f"{where}.sha256", message("project.full_sha_256_was_expected"))
    station = data.get("station_code")
    if "station_code" in data and (
        not isinstance(station, str) or not _STATION.fullmatch(station)
    ):
        raise _invalid(
            f"{where}.station_code",
            message("project.station_code_must_have_9", station=station),
        )
    if role == "station_series" and station is None:
        raise _invalid(where, message("project.station_series_file_needs_station"))
    if _pin_slot(Path(path), station) is None:
        raise _invalid(
            f"{where}.path",
            message("project.file_published_store_version_kind", path=path),
        )
    content, form = data.get("content_sha256"), data.get("content_form")
    if ("content_sha256" in data) != ("content_form" in data):
        raise _invalid(where, message("project.fields_content_sha256_content_form"))
    if "content_sha256" in data and (
        not isinstance(content, str) or not _SHA.fullmatch(content)
    ):
        raise _invalid(
            f"{where}.content_sha256",
            message("project.full_sha_256_was_expected"),
        )
    if "content_form" in data and (not isinstance(form, str) or not form):
        raise _invalid(
            f"{where}.content_form", message("project.non_empty_form_identifier_was")
        )
    return ProjectFile(role, Path(path), sha, station, content, form)


def _parse_task(raw: object, where: str, directory: Path, root: Path) -> ProjectTask:
    data = _object(raw, _TASK_KEYS, where)
    name, command = data["name"], data["command"]
    if not isinstance(name, str) or not commands._TASK_NAME.fullmatch(name):
        raise _invalid(
            f"{where}.name",
            message("project.task_name_1_64_characters", name=name),
        )
    if command not in commands._TASK_COMMANDS:
        raise _invalid(
            f"{where}.command",
            message("project.command_cannot_project_task", command=command),
        )
    try:
        options = _stored_options(command, data["options"], directory, root)
    except IMGWValidationError as exc:
        raise _invalid(f"{where}.options", reason(exc), exc.details) from exc
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
                message("project.expected_options_geometry_sha_256"),
            )
    elif geometry is not None:
        raise _invalid(where, message("project.selection_area_options_geometry_needs"))
    pinned_at = _moment(data["pinned_at"], f"{where}.pinned_at")
    version = data["imgwtools_version"]
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise _invalid(
            f"{where}.imgwtools_version", message("project.non_empty_text_null_was")
        )
    if (pinned_at is None) != (version is None):
        raise _invalid(
            where,
            message("project.pinned_imgwtools_version_both_null"),
        )
    if not isinstance(data["files"], list):
        raise _invalid(f"{where}.files", message("project.list_files_was_expected"))
    pins = tuple(
        _parse_file(entry, f"{where}.files[{index}]", root)
        for index, entry in enumerate(data["files"])
    )
    if len({pin.path for pin in pins}) != len(pins):
        raise _invalid(f"{where}.files", message("project.repeated_path_pinned_file"))
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
            message(
                "project.project_directory_must_not_lie", directory=directory, root=root
            ),
            details={"option": "project_dir"},
        )
    if not root.exists() and not root.is_symlink():
        return
    if root.is_dir() and not root.is_symlink() and not any(root.iterdir()):
        return
    try:
        info = store_info(root)
    except IMGWError as exc:
        raise IMGWProjectError(
            message("project.invalid_store_directory", root=root, exc=reason(exc)),
            code=exc.code,
            details={"option": "store_dir", **exc.details},
        ) from exc
    if not info.supported:
        raise IMGWProjectError(
            message(
                "project.directory_not_supported_imgw_store",
                root=root,
                problems="; ".join(info.problems),
            ),
            code="store_unavailable",
            details={"option": "store_dir", "reason": "unsupported"},
        )


def _parse(directory: Path, document: object) -> _Manifest:
    data = _object(document, _TOP_KEYS, "")
    if data["schema"] != PROJECT_SCHEMA:
        raise _invalid(
            "schema",
            message(
                "project.unsupported_schema_this_version_imgwtools",
                schema=data["schema"],
                project_schema=PROJECT_SCHEMA,
            ),
        )
    text = data["store_dir"]
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise _invalid("store_dir", message("project.non_empty_store_path_was"))
    root = _store_root(directory, text)
    _check_store(root, directory)
    extensions = data.get("extensions", {})
    if not isinstance(extensions, dict):
        raise _invalid("extensions", message("project.json_object_was_expected"))
    if not isinstance(data["tasks"], list):
        raise _invalid("tasks", message("project.list_tasks_was_expected"))
    tasks: list[ProjectTask] = []
    for index, raw in enumerate(data["tasks"]):
        task = _parse_task(raw, f"tasks[{index}]", directory, root)
        if any(other.name == task.name for other in tasks):
            raise _invalid(
                f"tasks[{index}].name",
                message("project.repeated_task_name", name=task.name),
            )
        tasks.append(task)
    return _Manifest(Project(directory, root, tuple(tasks), dict(extensions)), text)


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(message("project.repeated_key", key=key))
        result[key] = value
    return result


def _no_constant(name: str) -> Any:
    raise ValueError(message("project.disallowed_value", name=name))


def _load(directory: Path) -> _Manifest:
    path = directory / PROJECT_FILE
    if path.is_symlink():
        raise IMGWProjectError(
            message("project.project_manifest_must_not_symbolic", path=path),
            details={"option": "project_dir"},
        )
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise IMGWProjectError(
            message("project.no_project_manifest_run_imgw", path=path),
            code="not_found",
            details={"option": "project_dir"},
        ) from None
    except OSError as exc:
        raise IMGWProjectError(
            message("project.cannot_read_project_manifest", path=path, exc=reason(exc)),
            code="io_error",
        ) from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid(
            "", message("project.manifest_not_utf_8_text", exc=reason(exc))
        ) from exc
    try:
        document = json.loads(
            text, object_pairs_hook=_unique_keys, parse_constant=_no_constant
        )
    except ValueError as exc:
        raise _invalid("", message("project.invalid_json", exc=reason(exc))) from exc
    return _parse(directory, document)


# --- blokada i atomowy zapis -----------------------------------------------------------------


def _host() -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", socket.gethostname()) or "host"


def _owner(lock: Path) -> str | None:
    try:
        return (lock / "owner").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


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
                owner = _owner(lock)
                raise IMGWProjectError(
                    message(
                        "project.manifest_locked",
                        owner=owner or message("common.unknown"),
                        lock=lock,
                    ),
                    code="conflict",
                    details={"reason": "locked", "owner": owner},
                ) from None
            time.sleep(LOCK_RETRY_S)
        except OSError as exc:
            raise IMGWProjectError(
                message(
                    "project.cannot_lock_project_manifest", lock=lock, exc=reason(exc)
                ),
                code="io_error",
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
            message(
                "project.cannot_write_project_manifest", target=target, exc=reason(exc)
            ),
            code="io_error",
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
                message("project.conflict_task_was_removed_from", name=before.name),
                code="conflict",
                details={"reason": "task_changed"},
            )
        existing = _task_json(tasks[index])
        if existing == _task_json(after):
            return None
        if existing != _task_json(before):
            raise IMGWProjectError(
                message("project.conflict_task_was_changed_another", name=before.name),
                code="conflict",
                details={"reason": "task_changed"},
            )
        tasks[index] = after
        return current.with_tasks(tasks)

    _update(directory, change)


# --- argumenty ---------------------------------------------------------------------------------


def _path_text(value: object, what: str, option: str) -> str:
    text = os.fspath(value) if isinstance(value, str | os.PathLike) else None
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise IMGWValidationError(
            message("project.needs_non_empty_path", what=what, value=value),
            details={"option": option},
        )
    return os.path.expanduser(text)


def _directory(project_dir: PathArg) -> Path:
    return Path(
        os.path.abspath(
            _path_text(project_dir, message("project.project_directory"), "project_dir")
        )
    )


def _store_argument(directory: Path, store_dir: PathArg) -> tuple[str, Path]:
    """``store_dir`` względny wobec projektu zapisuje się względnie, bezwzględny bezwzględnie."""
    path = Path(_path_text(store_dir, message("project.store_directory"), "store_dir"))
    text = str(path) if path.is_absolute() else path.as_posix()
    return text, _store_root(directory, text)


def _selected(project: Project, tasks: Iterable[str] | None) -> tuple[ProjectTask, ...]:
    if tasks is None:
        return project.tasks
    if isinstance(tasks, str | bytes) or not isinstance(tasks, Iterable):
        raise IMGWValidationError(
            message("project.parameter_tasks_must_collection_task"),
            details={"option": "tasks"},
        )
    names = list(dict.fromkeys(tasks))
    known = {task.name for task in project.tasks}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise IMGWProjectError(
            message(
                "project.unknown_project_tasks", unknown=", ".join(map(repr, unknown))
            ),
            code="not_found",
            details={"option": "tasks", "value": unknown},
        )
    return tuple(task for task in project.tasks if task.name in names)


def _store_path(root: Path, path: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        raise IMGWStoreError(
            message("project.version_lies_outside_store", path=path, root=root)
        ) from None


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
        If the store directory is unsupported (``store_unavailable``), the
        project directory lies inside the store (``validation_error``), the
        directory or manifest cannot be written (``io_error``), the manifest
        lock is held (``conflict``), or an existing manifest points at a
        different store (``conflict``; change it with `set_project_store`).
    """
    directory = _directory(project_dir)
    text, root = _store_argument(directory, store_dir)
    _check_store(root, directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IMGWProjectError(
            message(
                "project.cannot_create_project_directory",
                directory=directory,
                exc=reason(exc),
            ),
            code="io_error",
        ) from exc
    with _locked(directory):
        manifest = directory / PROJECT_FILE
        if manifest.exists() or manifest.is_symlink():
            existing = _load(directory).project
            if existing.store_dir != root:
                raise IMGWProjectError(
                    message(
                        "project.project_manifest_already_exists_points",
                        manifest=manifest,
                        store_dir=existing.store_dir,
                    ),
                    code="conflict",
                    details={"option": "store_dir"},
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
    unpinned tasks) is verified in the new store before the manifest is updated;
    an equivalent version matched only by content is not identical.
    A new, empty store (missing or empty directory, or an initialised store
    without any version) is accepted without pinned files, so that
    `download_project` restores them: archives only with identical SHA-256
    (or, for a dataset with a canonical form, the same canonical content),
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
        If the manifest is missing (``not_found``) or invalid, the new store is
        unsupported (``store_unavailable``), it is not empty and does not
        contain identical pinned files (``conflict``), the manifest changed
        during verification (``conflict``), or the manifest cannot be locked
        or written.
    """
    directory = _directory(project_dir)
    before = _load(directory)
    text, root = _store_argument(directory, store_dir)
    _check_store(root, directory)
    pins = [(task, pin) for task in before.project.tasks for pin in task.files]
    problems = [
        f"{task.name}: {pin.path.as_posix()}: {_mismatch(check)}"
        for task, pin in pins
        for check in (_inspect(root, pin, full=True),)
        if check.state != "current"
    ]
    if problems and not _empty_store(root):
        shown = "; ".join(problems[:5]) + (" …" if len(problems) > 5 else "")
        raise IMGWProjectError(
            message(
                "project.store_does_not_contain_identical",
                root=root,
                count=len(problems),
                shown=shown,
            ),
            code="conflict",
            details={"option": "store_dir"},
        )

    def change(current: _Manifest) -> _Manifest:
        if current.document() != before.document():
            raise IMGWProjectError(
                message("project.project_manifest_changed_during_verification"),
                code="conflict",
                details={"reason": "task_changed"},
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
        sources = _sources(pin for _, pin in pins)
        _notice(
            on_notice,
            "warning",
            "pins_not_in_store",
            message(
                "project.pins_not_in_store",
                root=root,
                count=len(problems),
                origin=(
                    message("project.origin_providers", sources=sources)
                    if sources
                    else message("project.origin_source")
                ),
                by_content=(
                    message("project.restored_by_content")
                    if any(pin.content_sha256 is not None for _, pin in pins)
                    else ""
                ),
                lost=(
                    message(
                        "project.catalogs_not_restored",
                        tasks=", ".join(lost),
                        upgrade=_UPGRADE,
                    )
                    if lost
                    else ""
                ),
            ),
        )
    return project


def _mismatch(check: _PinCheck) -> str:
    """Why a pin is not identical in a store (``set_project_store``)."""
    if check.state == "content_match" and check.version is not None:
        return message(
            "project.pin_missing_same_content",
            version=check.version.as_posix(),
            upgrade=_UPGRADE,
        )
    return check.error or check.state


def _sources(pins: Iterable[ProjectFile]) -> str:
    """Display names of the providers of pinned archives and series, in registry order."""
    owners: set[str] = set()
    for pin in pins:
        kind, _, rest = (_pin_slot(pin.path, pin.station_code) or "").partition(":")
        if kind in ("archive", "series"):
            owners.add(get_dataset(rest.partition(":")[0]).provider)
    names = [provider.short_name for provider in providers() if provider.id in owners]
    if len(names) == 2:
        return message("project.sources_pair", first=names[0], second=names[1])
    return ", ".join(names)


def _area(data: bytes, name: str) -> _Border:
    """Wielokąty WGS84 ``[lon, lat]`` z GeoJSON (Polygon/MultiPolygon, Feature, FeatureCollection)."""
    rings: list[list[list[float]]] = []

    def ring(value: object) -> list[list[float]]:
        if not isinstance(value, list) or len(value) < 4:
            raise ValueError(message("project.polygon_ring_needs_least_4"))
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
                raise ValueError(message("project.invalid_position", position=position))
            points.append([float(position[0]), float(position[1])])
        if points[0] != points[-1]:
            raise ValueError(message("project.polygon_ring_must_closed"))
        return points

    def geometry(value: object) -> None:
        if not isinstance(value, dict):
            raise ValueError(message("project.geometry_object_was_expected"))
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
                message(
                    "project.unsupported_geometry_expected_polygon_multipolygon",
                    kind=kind,
                )
            )
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError(message("project.empty_polygon"))
            rings.extend(ring(item) for item in polygon)

    try:
        document = json.loads(data.decode("utf-8-sig"), parse_constant=_no_constant)
        if not isinstance(document, dict):
            raise ValueError(message("project.geojson_object_was_expected"))
        if document.get("type") == "FeatureCollection":
            features = document.get("features")
            if not isinstance(features, list):
                raise ValueError(message("project.features_must_list"))
            for feature in features:
                geometry(feature.get("geometry") if isinstance(feature, dict) else None)
        else:
            geometry(
                document.get("geometry")
                if document.get("type") == "Feature"
                else document
            )
        if not rings:
            raise ValueError(message("project.no_polygons"))
        return _Border(rings)
    except (ValueError, IMGWDataError) as exc:
        raise IMGWValidationError(
            message(
                "project.area_selection_file_not_valid", name=name, exc=reason(exc)
            ),
            details={"option": "geometry", "value": name},
        ) from exc


def _area_stations(
    root: Path, descriptor: DatasetDescriptor, area: _Border
) -> tuple[ProjectFile, list[str]]:
    """
    Stations of the dataset's kind located in ``area``, from its provider's catalog.

    The current catalog version of the dataset's provider (ADR-003 D14) is
    read and returned as the ``catalog`` pin of the selection.
    """
    provider = get_provider(descriptor.provider)
    entry = current_version(
        root, slot=f"catalog:{_CATALOG_DATASETS[descriptor.provider]}"
    )
    if entry is None or entry.version is None or entry.meta is None:
        option = "" if provider.id == "IMGW-PIB" else f" --provider {provider.id}"
        raise IMGWStoreError(
            message(
                "project.no_station_catalog_store_run",
                short_name=provider.short_name,
                root=root,
                option=option,
            ),
            code="not_found",
        )
    family = descriptor.kind
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
        except FileNotFoundError:
            raise IMGWValidationError(
                message("project.no_area_selection_file", relative=relative),
                details={"option": "geometry", "value": relative},
            ) from None
        except OSError as exc:
            raise IMGWProjectError(
                message(
                    "project.cannot_read_area_selection_file",
                    relative=relative,
                    exc=reason(exc),
                ),
                code="io_error",
                details={"option": "geometry", "value": relative},
            ) from exc
        # Suma dokładnie tych bajtów, z których materializujemy wybór stacji.
        digests = {relative: hashlib.sha256(data).hexdigest()}
        catalog, codes = _area_stations(
            root, get_dataset(options["dataset"]), _area(data, relative)
        )
        options["stations"] = tuple(sorted({*options.get("stations", ()), *codes}))
        if not options["stations"]:
            raise IMGWValidationError(
                message(
                    "project.area_selection_covered_no_station",
                    relative=relative,
                    path=catalog.path.as_posix(),
                ),
                details={"option": "geometry", "value": relative},
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
        If the manifest is missing (``not_found``) or invalid, a task with this
        name already exists (``conflict``), or the manifest cannot be locked
        or written.
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
        raise _task_exists(str(request["name"]))
    task = _new_task(directory, before.store_dir, request)

    def change(current: _Manifest) -> _Manifest:
        if any(existing.name == task.name for existing in current.project.tasks):
            raise _task_exists(task.name)
        return current.with_tasks((*current.project.tasks, task))

    return _update(directory, change)


def _task_exists(name: str) -> IMGWProjectError:
    return IMGWProjectError(
        message("project.task_already_exists_project", name=name),
        code="conflict",
        details={"option": "name", "value": name},
    )


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
        If the manifest is missing or invalid, the task does not exist
        (``not_found``), or the manifest cannot be locked or written.
    """
    directory = _directory(project_dir)

    def change(current: _Manifest) -> _Manifest:
        if not any(task.name == name for task in current.project.tasks):
            raise IMGWProjectError(
                message("project.no_task_project", name=name),
                code="not_found",
                details={"option": "name", "value": name},
            )
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


@dataclass(frozen=True)
class _PinCheck:
    """
    State of one pinned file in the store.

    Attributes
    ----------
    state : {"current", "content_match", "missing", "changed"}
        ``content_match`` when the pinned path is missing but the current
        version of its slot carries the pinned content (ADR-003 D14).
    error : str or None
        Description of a mismatch.
    code : ErrorCode or None
        §13.5 code of a mismatch: ``not_found`` (missing file),
        ``data_error`` (other content), ``io_error`` (unreadable file) or the
        code of a reading error.
    version : Path or None
        Store-relative path of the equivalent version file (``content_match``,
        or an equivalent whose bytes contradict its records: ``changed``).
    sha256 : str or None
        SHA-256 of that equivalent file.
    """

    state: PinState
    error: str | None = None
    code: ErrorCode | None = None
    version: Path | None = None
    sha256: str | None = None


def _inspect(
    root: Path,
    pin: ProjectFile,
    *,
    full: bool,
    indexes: dict[Path, SeriesIndex] | None = None,
) -> _PinCheck:
    """
    Offline state of a pinned file.

    Without ``full`` the existence and the size and SHA-256 recorded in the
    sidecar are checked (a station file: existence); ``full`` hashes the file
    and checks a station file against the ``series.json`` index of its
    version. A missing file of a dataset with a canonical form may be
    matched by an equivalent version (`_equivalent`).
    """
    path = root.joinpath(*pin.path.parts)
    if path.is_symlink():
        return _PinCheck("changed", message("project.pin_symlink"), "data_error")
    if not path.exists():
        return _equivalent(root, pin, full=full, indexes=indexes) or _PinCheck(
            "missing", message("project.pin_missing_in_store"), "not_found"
        )
    if not path.is_file():
        return _PinCheck("changed", message("project.pin_not_file"), "data_error")
    try:
        if pin.role == "station_series":
            if full:
                version = path.parent.parent
                index = (indexes or {}).get(version) or read_series_index(version)
                if indexes is not None:
                    indexes[version] = index
                entry = index.stations.get(pin.station_code or "")
                if (
                    entry is None
                    or version / entry.file != path
                    or entry.sha256 != pin.sha256
                ):
                    return _PinCheck(
                        "changed",
                        message("project.pin_not_confirmed_by_index"),
                        "data_error",
                    )
        else:
            meta = read_meta(path)
            size = path.stat().st_size
            if meta.size_bytes != size:
                return _PinCheck(
                    "changed",
                    message(
                        "project.pin_size_differs",
                        size=size,
                        size_bytes=meta.size_bytes,
                    ),
                    "data_error",
                )
            if meta.sha256 != pin.sha256:
                return _PinCheck(
                    "changed",
                    message("project.pin_sidecar_other_sha256"),
                    "data_error",
                )
        if full:
            actual = _sha256(path)
            if actual != pin.sha256:
                return _PinCheck(
                    "changed",
                    message(
                        "project.pin_sha256_differs", actual=actual, sha256=pin.sha256
                    ),
                    "data_error",
                )
    except IMGWError as exc:
        return _PinCheck("changed", reason(exc), exc.code)
    except OSError as exc:
        return _PinCheck("changed", reason(exc), "io_error")
    return _PinCheck("current")


def _content_of(data: bytes, form: str | None) -> str | None:
    """Canonical content SHA-256 of bytes in a released form, or None."""
    if form is None or form not in CONTENT_FORMS:
        return None
    try:
        return content_sha256(data, form=form)
    except IMGWDataError:
        return None


def _by_content(pin: ProjectFile) -> bool:
    """
    Whether an equivalent version may stand in for the pin (ADR-003 D14).

    True for an archive pin with ``content_sha256`` and for a series or
    station file pin of a dataset with a canonical form.
    """
    kind, _, rest = (_pin_slot(pin.path, pin.station_code) or "").partition(":")
    if kind == "archive":
        return pin.content_sha256 is not None
    return (
        kind == "series"
        and get_dataset(rest.partition(":")[0]).content_form is not None
    )


def _equivalent(
    root: Path,
    pin: ProjectFile,
    *,
    full: bool,
    indexes: dict[Path, SeriesIndex] | None = None,
) -> _PinCheck | None:
    """
    Equivalent of a missing pin in the current version of its slot (ADR-003 D14).

    Only files of datasets with a canonical form have one: an archive pin
    with ``content_sha256`` is matched by the current version of its slot
    with the same bytes or the same canonical content in the pin's form, a
    ``series.json`` or station file pin by the file of the current series
    version with the pinned SHA-256. Without ``full`` the sidecar and the
    series index are trusted; ``full`` recomputes the sums from the bytes.

    Returns
    -------
    _PinCheck or None
        ``content_match`` naming the equivalent version, ``changed`` for an
        equivalent whose bytes contradict its records, or None when the slot
        offers none (also when it cannot be read).
    """
    slot = _pin_slot(pin.path, pin.station_code)
    if slot is None or not _by_content(pin):
        return None
    kind, _, rest = slot.partition(":")
    key, _, station = rest.partition(":")
    try:
        if kind == "archive":
            return _equivalent_archive(root, pin, slot, full=full)
        return _equivalent_series(root, pin, key, station, full=full, indexes=indexes)
    except (IMGWError, OSError):
        return None


def _equivalent_archive(
    root: Path, pin: ProjectFile, slot: str, *, full: bool
) -> _PinCheck | None:
    """Current archive version with the pinned bytes or canonical content."""
    entry = current_version(root, slot=slot)
    if entry is None or entry.version is None or entry.meta is None:
        return None
    meta = entry.meta
    relative = Path(_store_path(root, entry.version))
    # A form this version of the library does not know compares by bytes only.
    known = pin.content_form in CONTENT_FORMS
    claimed = meta.sha256 == pin.sha256 or (
        known
        and meta.content_form == pin.content_form
        and meta.content_sha256 == pin.content_sha256
    )
    if not full:
        return (
            _PinCheck("content_match", version=relative, sha256=meta.sha256)
            if claimed
            else None
        )
    data = entry.version.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual == meta.sha256 and (
        actual == pin.sha256
        or (known and _content_of(data, pin.content_form) == pin.content_sha256)
    ):
        return _PinCheck("content_match", version=relative, sha256=actual)
    if not claimed:
        return None
    return _PinCheck(
        "changed",
        message(
            "project.equivalent_does_not_confirm",
            relative=relative.as_posix(),
            actual=actual,
            sha256=meta.sha256,
        ),
        "data_error",
        relative,
        actual,
    )


def _equivalent_series(
    root: Path,
    pin: ProjectFile,
    key: str,
    station: str,
    *,
    full: bool,
    indexes: dict[Path, SeriesIndex] | None,
) -> _PinCheck | None:
    """File of the current series version with the pinned SHA-256."""
    entry = current_version(root, slot=f"series:{key}")
    if entry is None or entry.version is None or entry.meta is None:
        return None
    target, recorded = entry.version, entry.meta.sha256
    if station:
        version = entry.version.parent
        index = (indexes or {}).get(version) or read_series_index(version)
        if indexes is not None:
            indexes[version] = index
        found = index.stations.get(station)
        if found is None:
            return None
        target, recorded = version / found.file, found.sha256
        if target.is_symlink() or not target.is_file():
            return None
    if recorded != pin.sha256:
        return None
    relative = Path(_store_path(root, target))
    actual = _sha256(target) if full else recorded
    if actual != recorded:
        return _PinCheck(
            "changed",
            message(
                "project.equivalent_sha256_differs",
                relative=relative.as_posix(),
                actual=actual,
                sha256=pin.sha256,
            ),
            "data_error",
            relative,
            actual,
        )
    return _PinCheck("content_match", version=relative, sha256=recorded)


def _pin_result(
    task: ProjectTask,
    root: Path,
    pin: ProjectFile,
    status: _ResultStatus,
    error: str | None,
    code: ErrorCode | None = None,
    *,
    version: Path | None = None,
) -> OperationResult:
    """
    Result of a pinned file: §13.7 slot of the pin, task name in ``task``.

    ``version`` (store-relative) replaces the pinned path for a pin matched
    by an equivalent version (``restored_by_content``).
    """
    return OperationResult(
        _pin_slot(pin.path, pin.station_code),
        status,
        root.joinpath(*(version or pin.path).parts),
        error,
        task.name,
        code if status == "failed" else None,
    )


def _task_result(
    task: ProjectTask,
    status: _ResultStatus,
    error: str | None,
    code: ErrorCode | None = None,
) -> OperationResult:
    """Błąd całego zadania: bez slotu, kod tylko przy ``failed``."""
    return OperationResult(
        None, status, None, error, task.name, code if status == "failed" else None
    )


def _state(task: ProjectTask, states: Iterable[str]) -> TaskStatus:
    """Task status from pin states: changed, missing, content_match, then current."""
    found = set(states)
    if task.pinned_at is None:
        return "unpinned"
    if "changed" in found:
        return "changed"
    if "missing" in found:
        return "missing"
    return "content_match" if "content_match" in found else "current"


def _check_result(
    task: ProjectTask, root: Path, pin: ProjectFile, check: _PinCheck
) -> OperationResult:
    """Status or verification result of a pin; a content match names its equivalent."""
    if check.state == "content_match":
        return _pin_result(
            task, root, pin, "restored_by_content", None, version=check.version
        )
    return _pin_result(
        task,
        root,
        pin,
        "unchanged" if check.state == "current" else "failed",
        check.error,
        check.code,
    )


def _matched_notice(
    hook: NoticeHook | None,
    task: ProjectTask,
    pairs: Iterable[tuple[ProjectFile, _PinCheck]],
) -> None:
    """Warning ``pin_restored_by_content`` listing every pin with its equivalent."""
    described = [
        message(
            "project.pin_matched",
            path=pin.path.as_posix(),
            sha256=pin.sha256,
            version=check.version.as_posix() if check.version else "?",
            version_sha256=check.sha256,
            basis=(
                message(
                    "project.shared_content_sha256", content_sha256=pin.content_sha256
                )
                if pin.content_sha256 is not None
                else message("project.same_sha256")
            ),
        )
        for pin, check in pairs
    ]
    if described:
        _notice(
            hook,
            "warning",
            _MATCHED,
            message(
                "project.task_restored_by_content",
                name=task.name,
                count=len(described),
                described="; ".join(described),
                upgrade=_UPGRADE,
            ),
        )


def get_project_status(
    project_dir: PathArg,
    /,
    *,
    tasks: Iterable[str] | None = None,
    on_notice: NoticeHook | None = None,
) -> ProjectReport:
    """
    Report the state of pinned files offline, without hashing.

    Each pinned file is checked for existence and for the size and SHA-256 stored
    in its sidecar; station Parquet files are checked for existence only. A
    missing file of a dataset with a canonical form whose slot's current
    version carries the pinned content (archive: ``content_sha256`` in the
    sidecar; series and station file: the same SHA-256) is ``content_match``,
    never silently ``current`` (ADR-003 D14).

    Parameters
    ----------
    project_dir : str or os.PathLike
        Project directory holding the manifest.
    tasks : Iterable[str] or None, optional
        Names of the tasks to check; ``None`` means all tasks.
    on_notice : NoticeHook or None, optional
        Receives one ``warning`` notice ``pin_restored_by_content`` per task
        with content matches, naming each pin and its equivalent version.

    Returns
    -------
    ProjectReport
        Status per task (``unpinned``, ``current``, ``content_match``,
        ``missing`` or ``changed``; ``changed`` takes precedence over
        ``missing``, both over ``content_match``) and one result per pinned
        file (``unchanged``, ``restored_by_content`` with the equivalent
        version in ``version``, or ``failed`` with an error and
        ``error_code`` ``not_found``, ``data_error`` or ``io_error``).

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a path or ``tasks`` is not a collection of names.
    IMGWProjectError
        If the manifest is missing or invalid, or ``tasks`` names unknown tasks
        (``not_found``).
    """
    project = open_project(project_dir)
    root = project.store_dir
    statuses: dict[str, TaskStatus] = {}
    results: list[OperationResult] = []
    for task in _selected(project, tasks):
        checks = [(pin, _inspect(root, pin, full=False)) for pin in task.files]
        results.extend(_check_result(task, root, pin, check) for pin, check in checks)
        statuses[task.name] = _state(task, (check.state for _, check in checks))
        _matched_notice(
            on_notice,
            task,
            [(pin, check) for pin, check in checks if check.state == "content_match"],
        )
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
    index of the series version are checked. For a ``content_match`` the
    SHA-256 and the canonical content of the equivalent version are
    recomputed from its bytes.

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
        that does not match its pin and one ``warning`` notice
        ``pin_restored_by_content`` per task with content matches.
    cancel : Cancel or None, optional
        Checked before each file; once it returns true the remaining files are
        reported as ``cancelled``.

    Returns
    -------
    ProjectReport
        Status per task (``unpinned``, ``current``, ``content_match``,
        ``missing``, ``changed`` or ``cancelled``) and one result per pinned
        file (``unchanged``, ``restored_by_content``, ``failed`` or
        ``cancelled``); ``cancelled`` is true when verification was stopped.

    Raises
    ------
    IMGWValidationError
        If ``project_dir`` is not a path or ``tasks`` is not a collection of names.
    IMGWProjectError
        If the manifest is missing or invalid, or ``tasks`` names unknown tasks
        (``not_found``).
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
        checks: list[tuple[ProjectFile, _PinCheck]] = []
        for pin in task.files:
            stopped = stopped or (cancel is not None and cancel())
            if stopped:
                results.append(_pin_result(task, root, pin, "cancelled", CANCELLED))
                continue
            check = _inspect(root, pin, full=True, indexes=indexes)
            checks.append((pin, check))
            results.append(_check_result(task, root, pin, check))
            if check.state not in ("current", "content_match"):
                _notice(
                    on_notice,
                    "error",
                    "pin_mismatch",
                    f"{task.name}: {pin.path.as_posix()}: {check.error}",
                )
            done += 1
            if on_progress is not None:
                on_progress(
                    Progress(done, total, "file", check.state, pin.path.as_posix())
                )
        stopped = stopped or (not task.files and cancel is not None and cancel())
        statuses[task.name] = (
            "cancelled"
            if stopped and len(checks) < max(len(task.files), 1)
            else _state(task, (check.state for _, check in checks))
        )
        _matched_notice(
            on_notice,
            task,
            [(pin, check) for pin, check in checks if check.state == "content_match"],
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
    return options


def _archive_years(options: Mapping[str, Any]) -> tuple[int, ...]:
    """
    Archive years covering the selected years.

    Archives numbered by the other kind of year add the neighbouring year
    (a hydrological year spans two calendar years and vice versa), unless it
    precedes the dataset's first archive.
    """
    descriptor = get_dataset(options["dataset"])
    years = set(options["years"])
    # Per-station files (ČHMÚ) are enumerated for the stations of the task.
    stations = (
        {}
        if descriptor.archive_scope == "country"
        else {"stations": options["stations"]}
    )
    if options["year_type"] != descriptor.year_type:
        shift = 1 if descriptor.year_type == "hydrological" else -1
        for year in options["years"]:
            with suppress(
                IMGWValidationError
            ):  # rocznik sprzed pierwszego archiwum zbioru
                archive_files(descriptor.key, years=(year + shift,), **stations)
                years.add(year + shift)
    return tuple(sorted(years))


def _store_selectors(options: Mapping[str, Any]) -> dict[str, Any]:
    """
    Selectors of `check_store` and `sync_store` covering a selection's archives.

    Country archives (IMGW-PIB) are chosen by years; per-station files (ČHMÚ)
    by the stations of the task, station × year files also by years, whole
    history element files without them.
    """
    descriptor = get_dataset(options["dataset"])
    if descriptor.archive_scope == "country":
        return {"years": _archive_years(options)}
    selectors: dict[str, Any] = {"stations": tuple(options["stations"])}
    if descriptor.archive_scope == "station_year":
        selectors["years"] = _archive_years(options)
    return selectors


def _check_task(
    root: Path, directory: Path, task: ProjectTask, hooks: Hooks
) -> tuple[_PlanStatus, str, StorePlan | None]:
    checks = [_inspect(root, pin, full=False) for pin in task.files]
    if task.pinned_at is not None:
        _matched_notice(
            hooks["on_notice"],
            task,
            [
                (pin, check)
                for pin, check in zip(task.files, checks, strict=True)
                if check.state == "content_match"
            ],
        )
    try:
        if task.command == _SELECT:
            options = _select_options(task, root)
            plan = check_store(
                root,
                datasets=(options["dataset"],),
                **_store_selectors(options),
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
        return "check_failed", reason(exc), None
    found = [(item.status, item.error) for item in plan.items] + [
        (action.status, action.detail) for action in plan.actions
    ]
    failed = [
        detail or message("project.check_failed")
        for status, detail in found
        if status == "check_failed"
    ]
    changed = [
        f"{pin.path.as_posix()}: {check.error}"
        for pin, check in zip(task.files, checks, strict=True)
        if check.state == "changed"
    ]
    missing = [
        pin
        for pin, check in zip(task.files, checks, strict=True)
        if check.state == "missing"
    ]
    matched = sum(check.state == "content_match" for check in checks)
    if plan.cancelled:
        return "unverifiable", CANCELLED, plan
    if failed:
        return "check_failed", "; ".join(failed), plan
    if changed:
        return (
            "check_failed",
            message("project.pins_changed", changed="; ".join(changed)),
            plan,
        )
    if task.pinned_at is None:
        return (
            "missing",
            message("project.task_not_pinned"),
            plan,
        )
    if missing:
        return (
            "missing",
            message(
                "project.pins_missing",
                count=len(missing),
                by_content=(
                    message("project.or_same_content")
                    if any(_by_content(pin) for pin in missing)
                    else ""
                ),
            ),
            plan,
        )
    if any(status in ("newer", "missing") for status, _ in found):
        return (
            "newer",
            message("project.newer_or_missing", upgrade=_UPGRADE),
            plan,
        )
    if any(
        status == "unverifiable" and detail != UNPUBLISHED for status, detail in found
    ):
        return (
            "unverifiable",
            message("project.no_comparable_signal_part"),
            plan,
        )
    if matched:
        return (
            "current",
            message(
                "project.pins_current_content_match", matched=matched, upgrade=_UPGRADE
            ),
            plan,
        )
    return "current", message("project.pins_current"), plan


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
    select`` task is checked with `check_store` over the archives covering
    its selection (IMGW-PIB yearbooks; ČHMÚ files of the task's stations);
    other tasks with `check_command`. Each task adds one ``project download``
    action with status ``check_failed`` (check error or changed pin),
    ``missing`` (unpinned task, missing pins or missing store), ``newer``
    (newer or missing data, applied only by an upgrade), ``unverifiable`` or
    ``current``. A pin matched by an equivalent version (``content_match``,
    ADR-003 D14) counts as present: the action detail names the matches and
    a ``pin_restored_by_content`` warning lists them.

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
        status: _PlanStatus
        detail: str
        if cancelled:
            status, detail = "unverifiable", CANCELLED
        elif not ready:
            status, detail = (
                "missing",
                message("project.store_missing", root=root),
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
                replace(action, detail=f"{task.name}: {action.detail}")
                for action in checked.actions
            )
            cancelled = cancelled or checked.cancelled
        actions.append(PlanAction("project download", status, f"{task.name}: {detail}"))
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    len(selected),
                    "task",
                    status,
                    message("project.task_progress", name=task.name),
                )
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
            raise TypeError(f"source_files is not a list: {sources!r}")
        pins.extend(_input_pin(source) for source in sources)
    except (KeyError, TypeError) as exc:
        raise IMGWDataError(
            message("project.series_sidecar_does_not_list", version=version)
        ) from exc
    return pins


def _input_pin(source: object) -> ProjectFile:
    """
    ``input`` pin of an ``extra.source_files`` entry of a series sidecar.

    Inputs of a dataset with a canonical form carry ``content_sha256`` and
    ``content_form`` (ADR-003 D17); the pin keeps them, so it can be
    restored by content.
    """
    if not isinstance(source, Mapping):
        raise TypeError(f"a source_files entry is not an object: {source!r}")
    content, form = source.get("content_sha256"), source.get("content_form")
    if (content is None) != (form is None) or (
        content is not None
        and not (
            isinstance(content, str)
            and _SHA.fullmatch(content)
            and isinstance(form, str)
            and form
        )
    ):
        raise TypeError(f"an invalid pair content_sha256 and content_form: {source!r}")
    return ProjectFile(
        "input",
        Path(str(source["file"])),
        str(source["sha256"]),
        None,
        content,
        form,
    )


def _add_sync(
    produced: _Produced, root: Path, task: ProjectTask, report: SyncReport, *, pin: bool
) -> None:
    produced.cancelled = produced.cancelled or report.cancelled
    for item in report.items:
        if item.status not in _DONE:
            produced.cancelled = produced.cancelled or item.status == "cancelled"
            produced.failures.append(replace(item, task=task.name))
        elif item.version is not None:
            path = _store_path(root, item.version)
            produced.statuses[path] = item.status
            if pin:
                meta = read_meta(item.version)
                produced.pins.append(
                    ProjectFile(
                        "input",
                        Path(path),
                        meta.sha256,
                        None,
                        meta.content_sha256,
                        meta.content_form,
                    )
                )


def _add_series(
    produced: _Produced,
    root: Path,
    task: ProjectTask,
    report: SeriesReport,
    stations: Iterable[str] | None,
    dataset: str | None,
) -> None:
    """Wynik budowy szeregu; porażka ma slot szeregu zbioru (``None``, gdy zbiór nieznany)."""
    slot = None if dataset is None else f"series:{dataset}"
    if report.status == "cancelled":
        produced.cancelled = True
        produced.failures.append(
            OperationResult(slot, "cancelled", None, CANCELLED, task.name)
        )
    elif report.status == "failed" or report.version is None:
        produced.failures.append(
            OperationResult(
                slot,
                "failed",
                report.version,
                "; ".join(report.problems) or message("project.series_build_failed"),
                task.name,
                "data_error",
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
                task,
                "failed",
                "; ".join(problems)
                or message("project.command_failed", command=task.command),
                "data_error",
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
            message(
                "project.plan_does_not_cover_archives",
                absent=", ".join(absent[:3]),
                value=" …" if len(absent) > 3 else "",
            )
        )
    return replace(plan, items=items, series_state={}, actions=())


def _produce_select(
    root: Path, task: ProjectTask, plan: StorePlan | None, hooks: Hooks
) -> _Produced:
    """
    Run a ``series select`` task: sync, build the series, validate the selection.

    The archives covering the selection are synchronized (IMGW-PIB yearbooks;
    ČHMÚ files of the task's stations), the dataset's series is built and
    the selection is validated against it.
    """
    options = _select_options(task, root)
    dataset = options["dataset"]
    selectors = _store_selectors(options)
    if plan is None:
        report = sync_store(
            root, datasets=(dataset,), series=False, **selectors, **hooks
        )
    else:
        report = sync_store(
            root,
            plan=_subplan(plan, archive_files(dataset, **selectors)),
            series=False,
            **hooks,
        )
    produced = _Produced()
    _add_sync(produced, root, task, report, pin=False)
    if produced.cancelled or produced.failures:
        return produced
    series = build_series(root, dataset=dataset, **hooks)
    stations: tuple[str, ...] = ()
    if series.status in ("new", "unchanged") and series.version is not None:
        stations = select_series(
            root,
            dataset=dataset,
            stations=options["stations"],
            variables=options.get("variables"),
            years=options.get("years"),
            year_type=options.get("year_type"),
        ).stations
    _add_series(produced, root, task, series, stations, dataset)
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
            # Kolejność szeregów wynika z planu: zbiór jest pewny tylko przy jednym.
            names = task.options.get("datasets")
            single = names[0] if isinstance(names, list) and len(names) == 1 else None
            _add_series(produced, root, task, series, None, single)
    elif isinstance(result, SeriesReport):
        _add_series(produced, root, task, result, None, str(task.options["dataset"]))
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
            OperationResult(
                item.slot, "failed", None, item.error, task.name, item.error_code
            )
            for item in result.items
            if item.status == "failed"
        )
        for file in result.files:
            # A task runs in the project store, so every file is a version to pin.
            path = _store_path(root, file.path)
            produced.statuses[path] = cast(_ResultStatus, file.status)
            meta = read_meta(file.path)
            produced.pins.append(
                ProjectFile(
                    "input",
                    Path(path),
                    meta.sha256,
                    None,
                    meta.content_sha256,
                    meta.content_form,
                )
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
            message("project.task_reasons", name=task.name, reasons=reasons),
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
    """
    Registry archive of a pinned version file.

    ``archives/versions/<server dir>/<stem>/<version>/<file>`` maps through
    its store slot to the `ArchiveFile` of a measurement series dataset of
    any provider (IMGW-PIB yearbook or ČHMÚ station file).
    """
    parts = path.parts
    server_path = "/".join((*parts[2:-3], parts[-1]))
    slot = _archive_slot(server_path)
    descriptor = None if slot is None else get_dataset(slot.split(":")[1])
    archive = (
        _archive_from_path(descriptor.key, server_path)
        if descriptor is not None
        and descriptor.in_store
        and descriptor.time_unit in _SERIES_UNITS
        else None
    )
    if archive is None:
        raise IMGWProjectError(
            message("project.pinned_file_does_not_match", path=path.as_posix()),
            code="not_found",
        )
    return archive


# Błąd odtworzenia pliku: komunikat i kod §13.5 (``None`` przy anulowaniu).
_Failure = tuple[str, ErrorCode | None]


def _recreate_archive(root: Path, pin: ProjectFile, hooks: Hooks) -> _Failure | None:
    """
    Download a missing pinned archive again and publish it as a version.

    Success: the identical SHA-256 under the pinned path, or for a pin with
    ``content_sha256`` a current version of its slot with the pinned bytes or
    canonical content (ADR-003 D14). Other content is an error naming the
    provider; the pins never change.
    """
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
        return message("project.not_restored", key=key, exc=reason(exc)), exc.code
    written_path = _store_path(root, written.path)
    if written.sha256 == pin.sha256 and written_path == key:
        return None
    equivalent = _equivalent(root, pin, full=True)
    if equivalent is not None:
        if equivalent.state == "content_match":
            return None
        return equivalent.error or message(
            "project.not_restored_key", key=key
        ), equivalent.code
    # Bytes seen at the source: other bytes of the same content leave the
    # current version in place (``unchanged``, ADR-003 D17).
    served = written.observed_sha256 or written.sha256
    if served != pin.sha256:
        provider = get_provider(get_dataset(archive.dataset).provider)
        return (
            message(
                "project.server_other_content",
                short_name=provider.short_name,
                server_path=archive.server_path,
                served=served,
                sha256=pin.sha256,
                upgrade=_UPGRADE,
            ),
            "not_found",
        )
    return (
        message(
            "project.identical_bytes_written",
            written_path=written_path,
            key=key,
            upgrade=_UPGRADE,
        ),
        "not_found",
    )


def _inputs_match(
    root: Path,
    descriptor: DatasetDescriptor,
    inputs: Iterable[ProjectFile],
    current: Iterable[tuple[Path, str | None]],
) -> bool:
    """
    Whether the current inputs of a series are exactly its pinned inputs.

    The same versions (path and SHA-256); for a dataset with a canonical
    form the same slots, each with the pinned bytes or the pinned canonical
    content in its sidecar (ADR-003 D14).
    """
    pins = list(inputs)
    present = list(current)
    if descriptor.content_form is None:
        return {(pin.path.as_posix(), pin.sha256) for pin in pins} == {
            (path.as_posix(), sha) for path, sha in present
        }
    pinned = {pin.path.parent.parent: pin for pin in pins}
    stored = {path.parent.parent: (path, sha) for path, sha in present}
    if len(pinned) != len(pins) or pinned.keys() != stored.keys():
        return False
    for slot, pin in pinned.items():
        path, sha = stored[slot]
        if sha == pin.sha256:
            continue
        meta = read_meta(root / path)
        if pin.content_sha256 is None or (meta.content_form, meta.content_sha256) != (
            pin.content_form,
            pin.content_sha256,
        ):
            return False
    return True


def _recreate_series(
    root: Path, task: ProjectTask, slug: str, hooks: Hooks
) -> _Failure | None:
    """
    Rebuild a missing pinned series from exactly the pinned inputs.

    The current versions of the dataset's archive slots must be the pinned
    inputs (`_inputs_match`). A series of a dataset with a canonical form
    rebuilt with another SHA-256 than the pinned ``series.json`` is a
    ``data_error``; the same SHA-256 under another label is restored by
    content.
    """
    descriptor = _series_datasets().get(slug)
    if descriptor is None:
        return message("project.unknown_series_dataset", slug=slug), "not_found"
    prefix = f"archives/versions/{descriptor.server_dir}/"
    inputs = [
        pin
        for pin in task.files
        if pin.role == "input" and pin.path.as_posix().startswith(prefix)
    ]
    try:
        current = [
            (item.local_path, item.local_sha256)
            for item in check_series(root, dataset=descriptor.key).items
            if item.local_path is not None
        ]
        if not inputs or not _inputs_match(root, descriptor, inputs, current):
            return (
                message(
                    "project.current_archives_differ",
                    key=descriptor.key,
                    upgrade=_UPGRADE,
                ),
                "not_found",
            )
        report = build_series(root, dataset=descriptor.key, **hooks)
        built = read_meta(report.version).sha256 if report.version is not None else None
    except IMGWError as exc:
        return message(
            "project.series_not_restored", slug=slug, exc=reason(exc)
        ), exc.code
    if report.status == "cancelled":
        return CANCELLED, None
    if report.status == "failed":
        return (
            "; ".join(report.problems) or message("project.series_build_failed"),
            "data_error",
        )
    pinned = next(
        (
            pin
            for pin in task.files
            if pin.role == "series" and pin.path.parts[2] == slug
        ),
        None,
    )
    if (
        descriptor.content_form is not None
        and pinned is not None
        and report.version is not None
        and built != pinned.sha256
    ):
        return (
            message(
                "project.series_other_sha256",
                key=descriptor.key,
                store_path=_store_path(root, report.version),
                built=built,
                sha256=pinned.sha256,
                upgrade=_UPGRADE,
            ),
            "data_error",
        )
    return None


def _recreate(
    root: Path, task: ProjectTask, missing: Iterable[ProjectFile], hooks: Hooks
) -> tuple[dict[ProjectFile, _Failure], bool]:
    """Odtwórz brakujące wersje: archiwa (GET + SHA), potem szeregi z przypiętych wejść."""
    cancel = hooks["cancel"]
    errors: dict[ProjectFile, _Failure] = {}
    cancelled = False
    series: dict[str, list[ProjectFile]] = {}
    for pin in missing:
        kind = pin.path.parts[0]
        if kind == "series":
            series.setdefault(pin.path.parts[2], []).append(pin)
            continue
        if kind != "archives":
            errors[pin] = (
                message(
                    "project.version_cannot_restore",
                    path=pin.path.as_posix(),
                    upgrade=_UPGRADE,
                ),
                "not_found",
            )
            continue
        cancelled = cancelled or (cancel is not None and cancel())
        error = (CANCELLED, None) if cancelled else _recreate_archive(root, pin, hooks)
        if error is not None:
            errors[pin] = error
    for slug, pins in series.items():
        cancelled = cancelled or (cancel is not None and cancel())
        error = (
            (CANCELLED, None)
            if cancelled
            else _recreate_series(root, task, slug, hooks)
        )
        if error is not None:
            errors.update((pin, error) for pin in pins)
    return errors, cancelled


def _restore(root: Path, task: ProjectTask, hooks: Hooks) -> _Outcome:
    """
    ``pinned`` mode for a pinned task: the pins never change.

    Missing files are recreated (archives downloaded again, series rebuilt
    from exactly the pinned inputs) and count only when identical, or, for a
    dataset with a canonical form, when the current version of their slot
    carries the pinned content (``restored_by_content``, ADR-003 D14). Pins
    already matched by such a version need no request. A task with content
    matches is ``content_match`` and gets one ``pin_restored_by_content``
    warning.
    """
    checks = {pin: _inspect(root, pin, full=False) for pin in task.files}
    missing = [pin for pin in task.files if checks[pin].state == "missing"]
    errors, cancelled = (
        _recreate(root, task, missing, hooks) if missing else ({}, False)
    )
    results: list[OperationResult] = []
    matched: list[tuple[ProjectFile, _PinCheck]] = []
    failed = changed = False
    for pin in task.files:
        check = checks[pin]
        if check.state == "missing":
            check = _inspect(root, pin, full=True)
            if check.state == "current":
                results.append(_pin_result(task, root, pin, "new", None))
                continue
            if check.state != "content_match":
                error, code = errors.get(pin) or (check.error, check.code)
                failed = True
                results.append(
                    _pin_result(
                        task,
                        root,
                        pin,
                        "cancelled" if error == CANCELLED else "failed",
                        error,
                        code,
                    )
                )
                continue
        if check.state == "content_match":
            matched.append((pin, check))
        changed = changed or check.state == "changed"
        results.append(_check_result(task, root, pin, check))
    status: TaskStatus = (
        "cancelled"
        if cancelled
        else "failed"
        if failed
        else "changed"
        if changed
        else "content_match"
        if matched
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
            message("project.task_reasons", name=task.name, reasons=reasons),
        )
    _matched_notice(hooks["on_notice"], task, matched)
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
    pinned: ``series select`` synchronizes the archives covering the selection
    (IMGW-PIB yearbooks; ČHMÚ files of the task's stations), builds the
    dataset series and pins ``series.json``, the selected station files and
    the input archives (inputs of a dataset with a canonical form with
    ``content_sha256`` and ``content_form``); other commands run through
    `run_command` with ``root=store_dir`` and pin the versions named in their
    result. New pins replace the whole task only after full success. With
    ``update="pinned"`` an already pinned task keeps its pins: missing archives
    are downloaded again and missing series rebuilt only when the result is
    identical to the pin, or for a dataset with a canonical form when the
    current version of the slot carries the pinned content
    (``restored_by_content``, ADR-003 D14; such pins need no request in later
    runs); catalog and PMAXTP versions are not recreated. Each task result is
    merged into the current manifest under the lock; a task changed meanwhile
    by another process fails with ``project_conflict``.

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
        ``project_conflict``, one ``warning`` ``pin_restored_by_content`` per
        task with content matches and the notices of the underlying
        operations.
    cancel : Cancel or None, optional
        Checked before each task and by the underlying operations; the
        remaining tasks are reported as ``cancelled``.

    Returns
    -------
    ProjectReport
        Status per task (``current``, ``content_match``, ``upgraded``,
        ``changed``, ``failed`` or ``cancelled``) and the per-file results
        (``restored_by_content`` with the equivalent version in ``version``)
        with §13.7 slots, the task name in ``task`` and ``error_code`` of
        failed items; an error of a whole task (e.g. a ``conflict`` while
        merging) has ``slot=None``. ``cancelled`` is true when the run was
        stopped.

    Raises
    ------
    IMGWValidationError
        If ``update`` is invalid, ``plan`` concerns a different store, or
        ``project_dir``/``tasks`` are invalid.
    IMGWProjectError
        If the manifest is missing (``not_found``) or invalid, or ``tasks``
        names unknown tasks (``not_found``).
    IMGWStoreError
        If the store directory cannot be opened or initialized.
    """
    if update not in ("pinned", "upgrade"):
        raise IMGWValidationError(
            message("project.invalid_update_mode_allowed_pinned", update=update),
            details={
                "option": "update",
                "value": update,
                "allowed": ["pinned", "upgrade"],
            },
        )
    project = open_project(project_dir)
    selected = _selected(project, tasks)
    root = project.store_dir
    if plan is not None and not isinstance(plan, StorePlan):
        plan = StorePlan.from_json(plan)
    if plan is not None and Path(plan.root).expanduser().absolute() != root:
        raise IMGWValidationError(
            message(
                "project.plan_concerns_another_store_than", root=plan.root, root_2=root
            ),
            details={"option": "plan"},
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
                    on_notice,
                    "error",
                    "task_failed",
                    message("project.task_error", name=task.name, exc=reason(exc)),
                )
                outcome = _Outcome(
                    "failed", (_task_result(task, "failed", reason(exc), exc.code),)
                )
            if outcome.task is not None:
                try:
                    _commit(project.path, task, outcome.task)
                except IMGWProjectError as exc:
                    _notice(
                        on_notice,
                        "error",
                        "project_conflict",
                        message("project.task_error", name=task.name, exc=reason(exc)),
                    )
                    outcome = _Outcome(
                        "failed",
                        (
                            *outcome.files,
                            _task_result(task, "failed", reason(exc), exc.code),
                        ),
                    )
            stopped = outcome.status == "cancelled"
        statuses[task.name] = outcome.status
        results.extend(outcome.files)
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    len(selected),
                    "task",
                    outcome.status,
                    message("project.task_progress", name=task.name),
                )
            )
    return ProjectReport(statuses, tuple(results), stopped)
