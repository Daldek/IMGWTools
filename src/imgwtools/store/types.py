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
    """
    Progress update reported to an ``on_progress`` hook.

    Attributes
    ----------
    current : int
        Number of units processed so far.
    total : int
        Total number of units in the operation.
    unit : str
        Kind of unit being counted, e.g. ``"archive"``, ``"station"``,
        ``"row"``, ``"task"`` or ``"file"``.
    status : str
        Outcome or state of the current unit, e.g. ``"created"`` or
        ``"failed"``.
    message : str
        Human-readable message (in Polish).
    """

    current: int
    total: int
    unit: str
    status: str
    message: str


@dataclass(frozen=True)
class Notice:
    """
    Diagnostic message reported to an ``on_notice`` hook.

    Attributes
    ----------
    level : {"info", "warning", "error"}
        Severity of the notice.
    code : str
        Stable machine-readable identifier, e.g. ``"license_terms"`` or
        ``"source_unverifiable"``.
    text : str
        Human-readable message (in Polish).
    """

    level: Literal["info", "warning", "error"]
    code: str
    text: str


ProgressHook = Callable[[Progress], None]
NoticeHook = Callable[[Notice], None]
Cancel = Callable[[], bool]


@dataclass(frozen=True)
class StoreHandle:
    """
    Handle to an opened or initialised IMGW store.

    Attributes
    ----------
    root : Path
        Absolute path of the store root directory.
    schema : {"imgw-store/1"}
        Version of the store marker contract.
    """

    root: Path
    schema: Literal["imgw-store/1"]


@dataclass(frozen=True)
class StoreInfo:
    """
    Offline description of a store root, returned even for unsupported roots.

    Attributes
    ----------
    root : Path
        Absolute path of the inspected root directory.
    exists : bool
        Whether the root directory exists.
    schema : str or None
        Schema read from the ``imgw-store.json`` marker, or None when the
        marker is missing or unreadable.
    supported : bool
        Whether this library can open the store; False also for a missing or
        unreadable marker or a marker without ``created_by``.
    contracts : Mapping of str to str
        Contract versions supported by the library, keyed by ``store``,
        ``meta``, ``series``, ``plan``, ``project`` and ``pmaxtp``.
    problems : tuple of str
        Human-readable descriptions of detected problems.
    """

    root: Path
    exists: bool
    schema: str | None
    supported: bool
    contracts: Mapping[str, str]
    problems: tuple[str, ...]


@dataclass(frozen=True)
class VersionResult:
    """
    Outcome of writing a single version into a store slot.

    Attributes
    ----------
    status : {"created", "unchanged", "relabeled", "reused"}
        ``"created"`` for new content, ``"unchanged"`` when identical
        content and HTTP signal already exist, ``"relabeled"`` when
        identical content was published with a new HTTP signal under a new
        label, ``"reused"`` when an existing version is reused.
    path : Path
        Path of the version's main file.
    sha256 : str
        Full SHA-256 hex digest of the main file.
    label : str
        Version label (date ``YYYY-MM-DD``, optionally with a ``+<hex>``
        suffix).
    """

    status: Literal["created", "unchanged", "relabeled", "reused"]
    path: Path
    sha256: str
    label: str


@dataclass(frozen=True)
class PlanItem:
    """
    Freshness state of a single archive in a store plan.

    Attributes
    ----------
    archive : ArchiveFile
        Archive the item refers to.
    status : {"current", "newer", "missing", "unverifiable", "check_failed"}
        ``"current"`` when the local version matches the remote signal,
        ``"newer"`` when the remote ETag or Last-Modified differs,
        ``"missing"`` for a published file without a local version,
        ``"unverifiable"`` when no comparable signal exists (also for
        unpublished or cancelled items), ``"check_failed"`` on an HTTP or
        listing error.
    local_path : Path or None
        Current local version of the slot, relative to the store root, or
        None when there is none.
    local_sha256 : str or None
        Full SHA-256 of the local version, or None.
    remote_etag : str or None
        ETag reported by the server, or None.
    remote_last_modified : str or None
        Last-Modified header reported by the server, or None.
    content_length : int or None
        Content-Length reported by the server (size estimate only), or None.
    error : str or None
        Reason for an unverifiable or failed check, e.g. ``"nieopublikowany"``.
    """

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
    """
    Planned non-archive action, e.g. building a series, catalog or project.

    Attributes
    ----------
    command : str
        Name of the data command the action refers to, e.g.
        ``"series build"``.
    status : {"current", "newer", "missing", "unverifiable", "check_failed"}
        Freshness state of the action's result.
    detail : str
        Human-readable explanation (in Polish).
    """

    command: str
    status: Literal["current", "newer", "missing", "unverifiable", "check_failed"]
    detail: str


@dataclass(frozen=True)
class StorePlan:
    """
    Read-only freshness plan in the ``imgw-plan/1`` format.

    A plan is produced by the ``check_*`` functions without writing to the
    store and can be saved outside the store and passed to a later sync.

    Attributes
    ----------
    schema : {"imgw-plan/1"}
        Version of the plan contract.
    root : Path
        Root the plan was checked against (store, project or output
        directory).
    checked_at : datetime
        Time of the check.
    items : tuple of PlanItem
        Per-archive freshness states.
    series_state : Mapping of str to {"current", "outdated", "missing"}
        State of the derived series, keyed by dataset slug.
    actions : tuple of PlanAction, optional
        Planned non-archive actions.
    cancelled : bool, optional
        Whether the check was cancelled and the plan is partial.
    """

    schema: Literal["imgw-plan/1"]
    root: Path
    checked_at: datetime
    items: tuple[PlanItem, ...]
    series_state: Mapping[str, Literal["current", "outdated", "missing"]]
    actions: tuple[PlanAction, ...] = ()
    cancelled: bool = False

    def to_json(self, path: PathArg, /) -> Path:
        """
        Save the plan as a portable ``imgw-plan/1`` JSON document.

        Local archive paths are written as relative POSIX paths, timestamps
        in UTC with a ``Z`` suffix. The document is canonical UTF-8 JSON
        with sorted keys; archive publication periods are omitted and
        restored from the offline registry by `from_json`.

        Parameters
        ----------
        path : str or os.PathLike
            Target file path; an existing file is overwritten.

        Returns
        -------
        Path
            Path of the written file.
        """
        target = Path(path)
        payload = {
            "schema": self.schema,
            "root": str(self.root),
            "checked_at": self.checked_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
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
                    "local_path": item.local_path.as_posix()
                    if item.local_path
                    else None,
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
        target.write_text(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def from_json(cls, path: PathArg, /) -> StorePlan:
        """
        Read the known fields of an ``imgw-plan/1`` document.

        Unknown additional fields are ignored. Archive descriptors are
        recreated from the offline dataset registry, which also restores
        their publication periods.

        Parameters
        ----------
        path : str or os.PathLike
            Path of the plan JSON file.

        Returns
        -------
        StorePlan
            Plan restored from the document.

        Raises
        ------
        IMGWDataError
            If the file cannot be read or parsed, has an unsupported schema,
            lacks required fields, refers to an archive unknown to the
            dataset registry or gives an archive URL different from the
            registry URL.
        """
        from imgwtools.datasets import ArchiveFile, archive_files, station_source_files

        def restore_archive(row: dict[str, Any]) -> ArchiveFile:
            """Recreate omitted publication dates from the offline dataset registry."""
            if row["year"] is None:
                candidates = station_source_files()
            else:
                candidates = archive_files(
                    row["dataset"],
                    years=(row["year"],),
                    months=(row["month"],) if row["month"] is not None else None,
                )
            source = next(
                (
                    entry
                    for entry in candidates
                    if entry.server_path == row["server_path"]
                ),
                None,
            )
            if (
                source is None
                or source.year_type != row["year_type"]
                or source.param != row["param"]
            ):
                raise ValueError(f"Nieznana ścieżka źródłowa: {row['server_path']}")
            if row["url"] != source.url:
                raise ValueError(
                    f"Adres {row['url']} nie odpowiada rejestrowi zbiorów: {source.url}"
                )
            return ArchiveFile(
                dataset=source.dataset,
                server_path=source.server_path,
                url=source.url,
                year=source.year,
                month=source.month,
                param=source.param,
                year_type=source.year_type,
                period_start=source.period_start,
                period_end=source.period_end,
            )

        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload["schema"] != "imgw-plan/1":
                raise ValueError("Nieobsługiwana wersja planu")
            items = tuple(
                PlanItem(
                    archive=restore_archive(row),
                    status=row["status"],
                    local_path=Path(row["local_path"])
                    if row["local_path"] is not None
                    else None,
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
                checked_at=datetime.fromisoformat(
                    payload["checked_at"].replace("Z", "+00:00")
                ),
                items=items,
                series_state=payload["series_state"],
                actions=tuple(
                    PlanAction(
                        **{k: action[k] for k in ("command", "status", "detail")}
                    )
                    for action in payload.get("actions", [])
                ),
                cancelled=payload["cancelled"],
            )
        except (OSError, ValueError, TypeError, KeyError, IMGWValidationError) as exc:
            raise IMGWDataError(f"Nie można odczytać planu IMGW: {exc}") from exc


@dataclass(frozen=True)
class OperationResult:
    """
    Result of a single per-slot operation in a sync or project report.

    Attributes
    ----------
    slot : str
        Identifier of the processed slot, e.g.
        ``archives/versions/<directory>/<stem>``; in project reports
        ``<task>:<path relative to the store>``.
    status : {"created", "relabeled", "unchanged", "reused", "failed", "stale_plan", "cancelled"}
        Outcome of the operation; ``"stale_plan"`` means the remote signal
        changed since the plan was made and the item was not downloaded.
    version : Path or None
        Absolute path of the resulting version's main file, or None.
    error : str or None
        Error description of a failed, stale or skipped item, or None.
    """

    slot: str
    status: Literal[
        "created",
        "relabeled",
        "unchanged",
        "reused",
        "failed",
        "stale_plan",
        "cancelled",
    ]
    version: Path | None
    error: str | None


@dataclass(frozen=True)
class SeriesReport:
    """
    Result of building a derived ``imgw-series/1`` series.

    Attributes
    ----------
    status : {"created", "reused", "cancelled", "failed"}
        ``"reused"`` when an existing version was built from the same inputs
        and nothing was written.
    version : Path or None
        Path of the version's ``series.json``, or None.
    stations : int
        Number of stations in the series.
    source_files : tuple of Path
        Absolute paths of the input archive versions (for ``"reused"``, the
        inputs recorded in the reused version's sidecar).
    problems : tuple of str
        Human-readable descriptions of problems, e.g. blocking slots.
    """

    status: Literal["created", "reused", "cancelled", "failed"]
    version: Path | None
    stations: int
    source_files: tuple[Path, ...]
    problems: tuple[str, ...]


@dataclass(frozen=True)
class SyncReport:
    """
    Report of a store synchronisation.

    Attributes
    ----------
    items : tuple of OperationResult
        Per-archive outcomes.
    series : tuple of SeriesReport
        Outcomes of the series builds triggered by the sync.
    cancelled : bool
        Whether the sync was cancelled.
    """

    items: tuple[OperationResult, ...]
    series: tuple[SeriesReport, ...]
    cancelled: bool


@dataclass(frozen=True)
class CatalogReport:
    """
    Result of building the ``stations.geojson`` station catalog.

    Attributes
    ----------
    status : {"created", "unchanged", "cancelled", "failed"}
        Outcome of the build.
    version : Path or None
        Path of the version's ``stations.geojson``, or None.
    station_count : int
        Number of stations in the catalog.
    without_location : int
        Number of stations without a location (``geometry`` is null).
    problems : tuple of str
        Human-readable descriptions of problems.
    """

    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None
    station_count: int
    without_location: int
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Meta:
    """
    Parsed ``<file>.meta.json`` sidecar of a store version.

    Attributes
    ----------
    schema : str
        Sidecar schema, ``"imgw-meta/1"``.
    dataset : str
        Full dataset key, e.g. ``"pl.imgw.hydro_daily"``.
    sha256 : str
        Full SHA-256 hex digest of the main file.
    size_bytes : int
        Size of the main file in bytes.
    downloaded_at : datetime
        UTC time the version was downloaded or built.
    license : License
        License and attribution of the data.
    request : Mapping of str to object
        Request that produced the version (e.g. server path, year, month).
    extra : Mapping of str to object
        The sidecar ``extra`` object (version label, HTTP signal, period,
        sources), including unknown fields.
    """

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
    """
    Entry of an offline store scan: a version or a detected problem.

    Attributes
    ----------
    kind : {"archive", "series", "catalog", "pmaxtp", "problem"}
        Kind of the entry.
    slot : str
        Slot identifier, e.g. ``archive:<server_path>``, ``series:<slug>``,
        ``catalog:stations`` or ``pmaxtp:<method>:<indX>_<indY>``; for a
        problem, the version slot or a path relative to the root.
    version : Path or None
        Path of the version's main file; for a problem, the path of the
        faulty element.
    meta : Meta or None
        Parsed sidecar of a valid version, None for problems.
    problem_code : str or None
        Machine-readable problem code, e.g. ``"missing_sidecar"``, or None.
    problem : str or None
        Human-readable problem description (in Polish), or None.
    """

    kind: Literal["archive", "series", "catalog", "pmaxtp", "problem"]
    slot: str
    version: Path | None
    meta: Meta | None
    problem_code: str | None
    problem: str | None


@dataclass(frozen=True)
class StationFeature:
    """
    Station read from a ``stations.geojson`` catalog.

    Attributes
    ----------
    station_code : str
        Nine-digit station code.
    geometry : tuple of (float, float) or None
        Location as ``(lon, lat)`` in WGS84, or None when unknown.
    properties : Mapping of str to str, int, float, bool or None
        Catalog properties of the station (kind, name, river, location
        source, activity, etc.).
    """

    station_code: str
    geometry: tuple[float, float] | None
    properties: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True)
class StationCoverage:
    """
    Coverage of one variable at one station in a series.

    Attributes
    ----------
    station : str
        Nine-digit station code.
    variable : str
        Variable code, e.g. ``"Q"`` or ``"H_max"``.
    unit : str
        Unit of the variable, e.g. ``"m3/s"``.
    period : {"winter", "summer", "annual"} or None
        Half-year period for semi-annual data, None otherwise.
    first : date or None
        First unit with a value, or None when there is none.
    last : date or None
        Last unit with a value, or None when there is none.
    with_value : int
        Number of units with a value (including ``no_phenomenon`` and
        ``accumulated``).
    accumulated : int
        Number of units flagged ``accumulated``.
    gaps : tuple of tuple of (date, date)
        Maximal closed ranges of units without a value between ``first``
        and ``last``.
    """

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
    """
    Index entry of one station's Parquet file in ``series.json``.

    Attributes
    ----------
    file : Path
        Parquet file path relative to the series version directory.
    sha256 : str
        Full SHA-256 hex digest of the Parquet file.
    rows : int
        Number of rows in the file.
    variables : Mapping of str to StationCoverage
        Coverage per variable, kept separate per half-year period (keys such
        as ``"Q_min@winter"``).
    """

    file: Path
    sha256: str
    rows: int
    variables: Mapping[str, StationCoverage]


@dataclass(frozen=True)
class SeriesIndex:
    """
    Parsed ``series.json`` index of an ``imgw-series/1`` version.

    Attributes
    ----------
    schema : {"imgw-series/1"}
        Version of the series contract.
    dataset : str
        Full dataset key.
    year_type : {"hydrological", "calendar"}
        Year numbering of the source archives.
    periods : tuple of tuple of (date, date)
        Union of the input archives' periods, adjacent ranges merged.
    stations : Mapping of str to StationSeriesIndex
        Per-station index, keyed by station code.
    """

    schema: Literal["imgw-series/1"]
    dataset: str
    year_type: Literal["hydrological", "calendar"]
    periods: tuple[tuple[date, date], ...]
    stations: Mapping[str, StationSeriesIndex]


@dataclass(frozen=True)
class PMaXTPStoreResult:
    """
    Result of storing a PMAXTP grid cell.

    Attributes
    ----------
    status : {"created", "unchanged", "cancelled", "failed"}
        Outcome of the operation.
    version : Path or None
        Path of the version's ``cell.json``, or None.
    ind_x : int or None
        Cell X index (taken from the server response once known), or None.
    ind_y : int or None
        Cell Y index (taken from the server response once known), or None.
    result : PMaXTPResult or None
        Stored PMAXTP data, or None.
    """

    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None
    ind_x: int | None
    ind_y: int | None
    result: PMaXTPResult | None


@dataclass(frozen=True)
class CommandOption:
    """
    Option of a data command in the command catalog.

    Attributes
    ----------
    name : str
        Python option name in ``snake_case``.
    type : {"str", "int", "path", "bool", "list", "choice"}
        Value type of the option.
    required : bool
        Whether the option is required.
    flag : str
        CLI flag in ``--kebab-case``.
    choices : tuple of str
        Allowed values for ``"choice"`` options, empty otherwise.
    help : str
        Help text (in Polish).
    """

    name: str
    type: Literal["str", "int", "path", "bool", "list", "choice"]
    required: bool
    flag: str
    choices: tuple[str, ...]
    help: str


@dataclass(frozen=True)
class DataCommand:
    """
    Data command available in the CLI, REST API and projects.

    Attributes
    ----------
    name : str
        Command name, e.g. ``"store sync"``.
    description : str
        Command description (in Polish), matching ``--help``.
    options : tuple of CommandOption
        Options accepted by the command.
    """

    name: str
    description: str
    options: tuple[CommandOption, ...]


@dataclass(frozen=True)
class SeriesSelection:
    """
    Validated selection from the current series of a dataset.

    Attributes
    ----------
    dataset : str
        Full dataset key.
    version : Path
        Path of the current series version's ``series.json``.
    stations : tuple of str
        Selected station codes.
    variables : tuple of str
        Selected variable codes.
    years : tuple of int
        Selected years.
    year_type : {"hydrological", "calendar"}
        Numbering of ``years``.
    """

    dataset: str
    version: Path
    stations: tuple[str, ...]
    variables: tuple[str, ...]
    years: tuple[int, ...]
    year_type: Literal["hydrological", "calendar"]


@dataclass(frozen=True)
class ProjectFile:
    """
    File pinned by a project task.

    Attributes
    ----------
    role : {"series", "station_series", "catalog", "input"}
        Role of the file in the task.
    path : Path
        Version file path relative to the project's store directory.
    sha256 : str
        Full SHA-256 hex digest of the file.
    station : str or None, optional
        Station code; required for ``"station_series"`` files.
    """

    role: Literal["series", "station_series", "catalog", "input"]
    path: Path
    sha256: str
    station: str | None = None


@dataclass(frozen=True)
class ProjectTask:
    """
    Task stored in an ``imgw-project/1`` manifest.

    Attributes
    ----------
    name : str
        Unique task name.
    command : str
        Data command the task runs, e.g. ``"series select"``.
    options : Mapping of str to object
        Command options in manifest form (JSON lists, relative POSIX paths).
    geometry_sha256 : Mapping of str to str or None
        SHA-256 of the geometry file used for selection by area, keyed by
        its path, or None.
    pinned_at : datetime or None
        UTC time of pinning, or None for an unpinned task.
    imgwtools_version : str or None
        Package version that pinned the task, or None for an unpinned task.
    files : tuple of ProjectFile
        Pinned files.
    """

    name: str
    command: str
    options: Mapping[str, object]
    geometry_sha256: Mapping[str, str] | None
    pinned_at: datetime | None
    imgwtools_version: str | None
    files: tuple[ProjectFile, ...]


@dataclass(frozen=True)
class ProjectReport:
    """
    Report of a project download, status or verification.

    Attributes
    ----------
    tasks : Mapping of str to {"unpinned", "current", "missing", "changed", "upgraded", "failed", "cancelled"}
        State of each processed task, keyed by task name.
    files : tuple of OperationResult
        Per-file outcomes; slots are ``<task>:<path relative to the store>``.
    cancelled : bool
        Whether the operation was cancelled.
    """

    tasks: Mapping[
        str,
        Literal[
            "unpinned",
            "current",
            "missing",
            "changed",
            "upgraded",
            "failed",
            "cancelled",
        ],
    ]
    files: tuple[OperationResult, ...]
    cancelled: bool


@dataclass(frozen=True)
class Project:
    """
    Project defined by an ``imgw-project/1`` manifest.

    Attributes
    ----------
    path : Path
        Absolute project directory.
    store_dir : Path
        Normalised absolute path of the project's store.
    tasks : tuple of ProjectTask
        Tasks defined in the manifest.
    extensions : Mapping of str to object, optional
        Top-level ``extensions`` of the manifest, preserved on rewrite.
    """

    path: Path
    store_dir: Path
    tasks: tuple[ProjectTask, ...]
    extensions: Mapping[str, object] = field(default_factory=dict)
