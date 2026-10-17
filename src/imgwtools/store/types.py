"""Immutable contracts shared by store writers, readers, and commands."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from imgwtools.exceptions import IMGWDataError, IMGWValidationError

if TYPE_CHECKING:

    from imgwtools.datasets import ArchiveFile, License
    from imgwtools.models import PMaXTPResult

PathArg = str | PathLike[str]


@dataclass(frozen=True)
class Progress:
    current: int
    total: int
    unit: str
    status: str
    message: str


@dataclass(frozen=True)
class Notice:
    level: Literal["info", "warning", "error"]
    code: str
    text: str


ProgressHook = Callable[[Progress], None]
NoticeHook = Callable[[Notice], None]
Cancel = Callable[[], bool]


@dataclass(frozen=True)
class StoreHandle:
    root: Path
    schema: Literal["imgw-store/1"]


@dataclass(frozen=True)
class StoreInfo:
    root: Path
    exists: bool
    schema: str | None
    supported: bool
    contracts: Mapping[str, str]
    problems: tuple[str, ...]


@dataclass(frozen=True)
class VersionResult:
    status: Literal["created", "unchanged", "relabeled", "reused"]
    path: Path
    sha256: str
    label: str


@dataclass(frozen=True)
class PlanItem:
    archive: ArchiveFile
    status: Literal["current", "newer", "missing", "unverifiable", "check_failed"]
    local_path: Path | None
    local_sha256: str | None
    remote_etag: str | None
    remote_last_modified: str | None
    content_length: int | None
    error: str | None


@dataclass(frozen=True)
class PlanAction:
    command: str
    status: Literal["current", "newer", "missing", "unverifiable", "check_failed"]
    detail: str


@dataclass(frozen=True)
class StorePlan:
    schema: Literal["imgw-plan/1"]
    root: Path
    checked_at: datetime
    items: tuple[PlanItem, ...]
    series_state: Mapping[str, Literal["current", "outdated", "missing"]]
    actions: tuple[PlanAction, ...] = ()
    cancelled: bool = False

    def to_json(self, path: PathArg, /) -> Path:
        """Save a portable plan with relative archive paths and UTC timestamps."""
        target = Path(path)
        payload = {
            "schema": self.schema,
            "root": str(self.root),
            "checked_at": self.checked_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "cancelled": self.cancelled,
            "items": [
                {
                    "dataset": item.archive.dataset,
                    "server_path": item.archive.server_path,
                    "url": item.archive.url,
                    "year": item.archive.year,
                    "month": item.archive.month,
                    "param": item.archive.param,
                    "year_type": item.archive.year_type,
                    "status": item.status,
                    "local_path": item.local_path.as_posix() if item.local_path else None,
                    "local_sha256": item.local_sha256,
                    "remote_etag": item.remote_etag,
                    "remote_last_modified": item.remote_last_modified,
                    "content_length": item.content_length,
                    "error": item.error,
                }
                for item in self.items
            ],
            "series_state": dict(self.series_state),
            "actions": [asdict(action) for action in self.actions],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return target

    @classmethod
    def from_json(cls, path: PathArg, /) -> StorePlan:
        """Read the known fields of an imgw-plan/1 document, ignoring extensions."""
        from imgwtools.datasets import ArchiveFile, archive_files, station_source_files

        def restore_archive(row: dict[str, Any]) -> ArchiveFile:
            """Recreate omitted publication dates from the offline dataset registry."""
            if row["year"] is None:
                candidates = station_source_files()
            else:
                candidates = archive_files(
                    row["dataset"], years=(row["year"],),
                    months=(row["month"],) if row["month"] is not None else None,
                )
            source = next(
                (entry for entry in candidates if entry.server_path == row["server_path"]),
                None,
            )
            if source is None or source.year_type != row["year_type"] or source.param != row["param"]:
                raise ValueError(f"Nieznana ścieżka źródłowa: {row['server_path']}")
            return ArchiveFile(
                dataset=source.dataset, server_path=source.server_path, url=row["url"],
                year=source.year, month=source.month, param=source.param,
                year_type=source.year_type,
                period_start=source.period_start, period_end=source.period_end,
            )

        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload["schema"] != "imgw-plan/1":
                raise ValueError("Nieobsługiwana wersja planu")
            items = tuple(
                PlanItem(
                    archive=restore_archive(row),
                    status=row["status"],
                    local_path=Path(row["local_path"]) if row["local_path"] is not None else None,
                    local_sha256=row["local_sha256"],
                    remote_etag=row["remote_etag"],
                    remote_last_modified=row["remote_last_modified"],
                    content_length=row["content_length"],
                    error=row["error"],
                )
                for row in payload["items"]
            )
            return cls(
                schema="imgw-plan/1",
                root=Path(payload["root"]),
                checked_at=datetime.fromisoformat(payload["checked_at"].replace("Z", "+00:00")),
                items=items,
                series_state=payload["series_state"],
                actions=tuple(PlanAction(**{k: action[k] for k in ("command", "status", "detail")}) for action in payload.get("actions", [])),
                cancelled=payload["cancelled"],
            )
        except (OSError, ValueError, TypeError, KeyError, IMGWValidationError) as exc:
            raise IMGWDataError(f"Nie można odczytać planu IMGW: {exc}") from exc


@dataclass(frozen=True)
class OperationResult:
    slot: str
    status: Literal["created", "relabeled", "unchanged", "reused", "failed", "stale_plan", "cancelled"]
    version: Path | None
    error: str | None


@dataclass(frozen=True)
class SeriesReport:
    status: Literal["created", "reused", "cancelled", "failed"]
    version: Path | None
    stations: int
    source_files: tuple[Path, ...]
    problems: tuple[str, ...]


@dataclass(frozen=True)
class SyncReport:
    items: tuple[OperationResult, ...]
    series: tuple[SeriesReport, ...]
    cancelled: bool


@dataclass(frozen=True)
class CatalogReport:
    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None
    station_count: int
    without_location: int
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Meta:
    schema: str
    dataset: str
    sha256: str
    size_bytes: int
    downloaded_at: datetime
    license: License
    request: Mapping[str, object]
    extra: Mapping[str, object]


@dataclass(frozen=True)
class StoreEntry:
    kind: Literal["archive", "series", "catalog", "pmaxtp", "problem"]
    slot: str
    version: Path | None
    meta: Meta | None
    problem_code: str | None
    problem: str | None


@dataclass(frozen=True)
class StationFeature:
    station_code: str
    geometry: tuple[float, float] | None
    properties: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True)
class StationCoverage:
    station: str
    variable: str
    unit: str
    period: Literal["winter", "summer", "annual"] | None
    first: date | None
    last: date | None
    with_value: int
    accumulated: int
    gaps: tuple[tuple[date, date], ...]


@dataclass(frozen=True)
class StationSeriesIndex:
    file: Path
    sha256: str
    rows: int
    variables: Mapping[str, StationCoverage]


@dataclass(frozen=True)
class SeriesIndex:
    schema: Literal["imgw-series/1"]
    dataset: str
    year_type: Literal["hydrological", "calendar"]
    periods: tuple[tuple[date, date], ...]
    stations: Mapping[str, StationSeriesIndex]


@dataclass(frozen=True)
class PMaXTPStoreResult:
    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None
    ind_x: int | None
    ind_y: int | None
    result: PMaXTPResult | None


@dataclass(frozen=True)
class CommandOption:
    name: str
    type: Literal["str", "int", "path", "bool", "list", "choice"]
    required: bool
    flag: str
    choices: tuple[str, ...]
    help: str


@dataclass(frozen=True)
class DataCommand:
    name: str
    description: str
    options: tuple[CommandOption, ...]


@dataclass(frozen=True)
class SeriesSelection:
    dataset: str
    version: Path
    stations: tuple[str, ...]
    variables: tuple[str, ...]
    years: tuple[int, ...]
    year_type: Literal["hydrological", "calendar"]


@dataclass(frozen=True)
class ProjectFile:
    role: Literal["series", "station_series", "catalog", "input"]
    path: Path
    sha256: str
    station: str | None = None


@dataclass(frozen=True)
class ProjectTask:
    name: str
    command: str
    options: Mapping[str, object]
    geometry_sha256: Mapping[str, str] | None
    pinned_at: datetime | None
    imgwtools_version: str | None
    files: tuple[ProjectFile, ...]


@dataclass(frozen=True)
class ProjectReport:
    tasks: Mapping[str, Literal["unpinned", "current", "missing", "changed", "upgraded", "failed", "cancelled"]]
    files: tuple[OperationResult, ...]
    cancelled: bool


@dataclass(frozen=True)
class Project:
    path: Path
    store_dir: Path
    tasks: tuple[ProjectTask, ...]
    extensions: Mapping[str, object] = field(default_factory=dict)
