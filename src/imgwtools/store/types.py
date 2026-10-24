"""Immutable contracts shared by store writers, readers, and commands."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from imgwtools._jsonable import jsonable
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.messages import DEFAULT_LANG, Lang

if TYPE_CHECKING:
    from imgwtools.datasets import ArchiveFile, License, ProviderDescriptor
    from imgwtools.exceptions import ErrorCode
    from imgwtools.models import PMaXTPResult

PathArg = str | PathLike[str]
Writes = Literal["none", "add", "replace"]


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
        ``meta``, ``series``, ``plan``, ``project``, ``pmaxtp`` and
        ``observation``.
    problems : tuple of str
        Human-readable descriptions of detected problems.
    providers : tuple of ProviderDescriptor, optional
        Data providers the library knows (identifier, display name,
        datasets, license and attribution).
    """

    root: Path
    exists: bool
    schema: str | None
    supported: bool
    contracts: Mapping[str, str]
    problems: tuple[str, ...]
    providers: tuple[ProviderDescriptor, ...] = ()


@dataclass(frozen=True)
class VersionResult:
    """
    Outcome of writing a single version into a store slot.

    Attributes
    ----------
    status : {"created", "unchanged", "relabeled", "reused"}
        ``"created"`` for new content, ``"unchanged"`` when identical
        content and HTTP signal already exist (or, for a dataset with a
        canonical form, other bytes carry the content of the current
        version), ``"relabeled"`` when identical bytes were published with a
        new HTTP signal under a new label, ``"reused"`` when an existing
        version is reused.
    path : Path
        Path of the version's main file.
    sha256 : str
        Full SHA-256 hex digest of the main file.
    label : str
        Version label (date ``YYYY-MM-DD``, optionally with a ``+<hex>``
        suffix).
    observed_sha256 : str or None, optional
        SHA-256 of the downloaded bytes when they differ from the version's
        but carry the same canonical content (``content_unchanged``); None
        otherwise.
    observation : Path or None, optional
        Observation recording the signal of those bytes (written now or the
        slot's reference observation); None otherwise, also when the
        reference signal is the current version's own.
    """

    status: Literal["created", "unchanged", "relabeled", "reused"]
    path: Path
    sha256: str
    label: str
    observed_sha256: str | None = None
    observation: Path | None = None


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
        ``"newer"`` when the remote signal differs, ``"missing"`` for a
        published file without a local version, ``"unverifiable"`` when no
        comparable signal exists (also for unpublished or cancelled items),
        ``"check_failed"`` on an HTTP or listing error.
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
        Size reported by the server (``Content-Length`` or the listing), or
        None.
    error : str or None
        Reason for an unverifiable or failed check, e.g. ``"nieopublikowany"``.
    station_code : str or None, optional
        Station of a per-station file (ČHMÚ), None for country archives.
    signal : {"head", "listing"}, optional
        Source of the remote signal: a ``HEAD`` request (IMGW-PIB) or the
        server listing of the directory (ČHMÚ).
    remote_listed_at : str or None, optional
        Modification time from the listing, ``YYYY-MM-DDTHH:MMZ``; None for
        ``"head"`` items.
    local_observation : Path or None, optional
        Observation giving the slot's reference signal, relative to the
        store root; None when the reference is the current version itself.
    """

    archive: ArchiveFile
    status: Literal["current", "newer", "missing", "unverifiable", "check_failed"]
    local_path: Path | None
    local_sha256: str | None
    remote_etag: str | None
    remote_last_modified: str | None
    content_length: int | None
    error: str | None
    station_code: str | None = None
    signal: Literal["head", "listing"] = "head"
    remote_listed_at: str | None = None
    local_observation: Path | None = None


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
    requests : Mapping of str to int or None, optional
        Requests the check made (``"made"``) and the downloads of its
        ``newer`` and ``missing`` items would make (``"planned"``, two per
        item: HEAD and GET); None when not counted.
    """

    schema: Literal["imgw-plan/1"]
    root: Path
    checked_at: datetime
    items: tuple[PlanItem, ...]
    series_state: Mapping[str, Literal["current", "outdated", "missing"]]
    actions: tuple[PlanAction, ...] = ()
    cancelled: bool = False
    requests: Mapping[str, int] | None = None

    def _document(self) -> dict[str, Any]:
        """
        Build the fields of the ``imgw-plan/1`` document (spec §11.5).

        Archive descriptors are flattened into the items without their
        publication periods (`from_json` restores them from the registry)
        and local archive and observation paths become relative POSIX texts.
        ``root`` stays a `Path` and ``checked_at`` a `datetime`, so `to_json`
        and the JSON envelope converter (``imgwtools._jsonable``) render them
        by their own rules.

        Returns
        -------
        dict of str to object
            Document fields in contract order.
        """
        return {
            "schema": self.schema,
            "root": self.root,
            "checked_at": self.checked_at,
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
                    "station_code": item.station_code,
                    "status": item.status,
                    "signal": item.signal,
                    "local_path": item.local_path.as_posix()
                    if item.local_path
                    else None,
                    "local_sha256": item.local_sha256,
                    "local_observation": item.local_observation.as_posix()
                    if item.local_observation
                    else None,
                    "remote_etag": item.remote_etag,
                    "remote_last_modified": item.remote_last_modified,
                    "remote_listed_at": item.remote_listed_at,
                    "content_length": item.content_length,
                    "error": item.error,
                }
                for item in self.items
            ],
            "series_state": dict(self.series_state),
            "actions": [asdict(action) for action in self.actions],
            "requests": dict(self.requests) if self.requests is not None else None,
        }

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
        payload = self._document()
        payload["root"] = str(self.root)
        payload["checked_at"] = (
            self.checked_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        )
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

        Unknown additional fields are ignored, and fields added after 3.0.0
        (``station_code``, ``signal``, ``remote_listed_at``,
        ``local_observation``, ``requests``) take their defaults when absent.
        Archive descriptors are recreated from the offline dataset registry,
        which also restores their publication periods.

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
            dataset registry, gives an archive URL different from the
            registry URL, or has an invalid ``signal`` or ``requests``.
        """
        from imgwtools.datasets import _archive_from_path

        def restore_archive(row: dict[str, Any]) -> ArchiveFile:
            """Recreate omitted publication dates from the offline dataset registry."""
            source = _archive_from_path(row["dataset"], row["server_path"])
            station = row.get("station_code")
            if (
                source is None
                or (source.year, source.month, source.param, source.year_type)
                != (row["year"], row["month"], row["param"], row["year_type"])
                or (station is not None and station != source.station_code)
            ):
                raise ValueError(f"Nieznana ścieżka źródłowa: {row['server_path']}")
            if row["url"] != source.url:
                raise ValueError(
                    f"Adres {row['url']} nie odpowiada rejestrowi zbiorów: {source.url}"
                )
            return source

        def restore_signal(row: dict[str, Any]) -> Literal["head", "listing"]:
            signal = row.get("signal", "head")
            if signal not in ("head", "listing"):
                raise ValueError(f"Nieznany sygnał pozycji planu: {signal!r}")
            return cast(Literal["head", "listing"], signal)

        def restore_requests(value: object) -> dict[str, int] | None:
            if value is None:
                return None
            if not isinstance(value, dict) or not all(
                isinstance(count, int) and not isinstance(count, bool) and count >= 0
                for count in value.values()
            ):
                raise ValueError("Pole requests planu musi mapować nazwy na liczby ≥ 0")
            return {str(name): count for name, count in value.items()}

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
                    station_code=row.get("station_code"),
                    signal=restore_signal(row),
                    remote_listed_at=row.get("remote_listed_at"),
                    local_observation=Path(row["local_observation"])
                    if row.get("local_observation") is not None
                    else None,
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
                requests=restore_requests(payload.get("requests")),
            )
        except (OSError, ValueError, TypeError, KeyError, IMGWValidationError) as exc:
            raise IMGWDataError(f"Nie można odczytać planu IMGW: {exc}") from exc


@dataclass(frozen=True)
class OperationResult:
    """
    Result of a single per-slot operation in a sync or project report.

    Attributes
    ----------
    slot : str or None
        Slot (spec §13.7) of the processed file, e.g.
        ``archive:pl.imgw.hydro_daily:2024/codz_2024.zip``; the project task
        name is kept separately in ``task``; None when the item has no slot
        (e.g. an error of a whole project task).
    status : {"created", "relabeled", "unchanged", "reused", "restored_by_content", "failed", "stale_plan", "cancelled"}
        Outcome of the operation; ``"stale_plan"`` means the remote signal
        changed since the plan was made and the item was not downloaded;
        ``"restored_by_content"`` means a project pin was restored by an
        equivalent version with the same canonical content (a success).
    version : Path or None
        Absolute path of the resulting version's main file, or None.
    error : str or None
        Error description of a failed, stale or skipped item, or None.
    task : str or None, optional
        Name of the project task the item belongs to, or None outside projects.
    error_code : ErrorCode or None, optional
        Error code from ``ERROR_CODES`` of a failed item, or None.
    """

    slot: str | None
    status: Literal[
        "created",
        "relabeled",
        "unchanged",
        "reused",
        "restored_by_content",
        "failed",
        "stale_plan",
        "cancelled",
    ]
    version: Path | None
    error: str | None
    task: str | None = None
    error_code: ErrorCode | None = None


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
class DownloadItem:
    """
    Outcome of downloading one archive file outside the store.

    Attributes
    ----------
    slot : str
        Slot of the archive file (§13.7 grammar), e.g.
        ``archive:pl.imgw.hydro_daily:2023/codz_2023.zip``.
    url : str
        Source URL on the provider's server.
    status : {"downloaded", "not_published", "failed", "cancelled"}
        Outcome of the download; ``"not_published"`` (a success) means the
        server answered 404 for a candidate file of a ČHMÚ dataset.
    path : Path or None
        Absolute path of the written file, or None when nothing was written.
    error : str or None
        Error description (in Polish) of a failed item (``"nieopublikowany"``
        for an unpublished one), or None.
    error_code : ErrorCode or None
        Error code from ``ERROR_CODES`` of a failed item, or None.
    """

    slot: str
    url: str
    status: Literal["downloaded", "not_published", "failed", "cancelled"]
    path: Path | None
    error: str | None
    error_code: ErrorCode | None


@dataclass(frozen=True)
class DownloadReport:
    """
    Report of downloading archive files to a plain directory.

    Attributes
    ----------
    output : Path
        Absolute target directory.
    items : tuple of DownloadItem
        Per-file outcomes in download order.
    cancelled : bool
        Whether the download was cancelled.
    """

    output: Path
    items: tuple[DownloadItem, ...]
    cancelled: bool


@dataclass(frozen=True)
class CatalogReport:
    """
    Result of building the ``stations.geojson`` station catalog of a provider.

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
    from_series : int
        Number of historical stations known only from the current series
        indexes (absent from the station lists, public APIs and static file).
    problems : tuple of str
        Human-readable descriptions of problems.
    provider : str, optional
        ``ProviderDescriptor.id`` of the catalog's provider.
    """

    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None
    station_count: int
    without_location: int
    from_series: int
    problems: tuple[str, ...]
    provider: str = "IMGW-PIB"


@dataclass(frozen=True)
class Meta:
    """
    Parsed ``<file>.meta.json`` sidecar of a store version.

    Attributes
    ----------
    schema : str
        Sidecar schema, ``"imgw-meta/1"``.
    dataset : str
        Dataset key as written in the sidecar, e.g. ``"pl.imgw.hydro_daily"``;
        never rewritten, even after the dataset is renamed.
    dataset_key : str or None
        Current key of ``dataset`` (``imgwtools.datasets.resolve_dataset_key``):
        the key itself, the new key of a renamed key, or None for a key
        IMGWTools does not know (IMGW-20).
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
    content_sha256 : str or None, optional
        SHA-256 hex digest of the canonical form of the main file; None when
        the sidecar has no content fields (every IMGW-PIB dataset).
    content_form : str or None, optional
        Identifier of the canonical form behind ``content_sha256``, e.g.
        ``"chmi-json/1"``; present exactly when ``content_sha256`` is.
    provider : str, optional
        ``provider`` field of the sidecar, e.g. ``"IMGW-PIB"`` or ``"CHMI"``.
    country : str, optional
        ``country`` field of the sidecar, e.g. ``"PL"`` or ``"CZ"``.
    """

    schema: str
    dataset: str
    dataset_key: str | None
    sha256: str
    size_bytes: int
    downloaded_at: datetime
    license: License
    request: Mapping[str, object]
    extra: Mapping[str, object]
    content_sha256: str | None = None
    content_form: str | None = None
    provider: str = "IMGW-PIB"
    country: str = "PL"


@dataclass(frozen=True)
class Observation:
    """
    Source signal recorded without a new version (``imgw-observation/1``).

    An observation lies in ``observations/`` of an archive slot: the source
    published other bytes with the same canonical content as the version
    named by ``same_content_as``, under a new signal. It is never a version.

    Attributes
    ----------
    dataset : str
        Full dataset key of the slot, e.g. ``"cz.chmi.hydro_daily"``.
    seen_at : str
        UTC time of the observation, ``YYYY-MM-DDTHH:MM:SSZ``.
    url : str
        Download URL of the observed bytes.
    last_modified : str or None
        ``Last-Modified`` header of the download, None when absent.
    etag : str or None
        ``ETag`` header of the download, None when absent.
    size_bytes : int
        Size of the observed bytes (not stored in the store).
    sha256 : str
        SHA-256 hex digest of the observed bytes.
    content_sha256 : str
        SHA-256 hex digest of their canonical form, equal to the version's.
    content_form : str
        Identifier of the canonical form, equal to the version's.
    same_content_as : str
        Directory name ``<label>_<sha8>`` of the version with that content.
    """

    dataset: str
    seen_at: str
    url: str
    last_modified: str | None
    etag: str | None
    size_bytes: int
    sha256: str
    content_sha256: str
    content_form: str
    same_content_as: str


@dataclass(frozen=True)
class StoreEntry:
    """
    Entry of an offline store scan: a version or a detected problem.

    Attributes
    ----------
    kind : {"archive", "series", "catalog", "pmaxtp", "observation", "problem"}
        Kind of the entry.
    slot : str or None
        Slot (spec §13.7), e.g.
        ``archive:pl.imgw.hydro_daily:2024/codz_2024.zip``,
        ``series:pl.imgw.hydro_daily``, ``catalog:pl.imgw.stations`` or
        ``pmaxtp:pl.imgw.pmaxtp:POT/751_317``; for an observation, the
        archive slot it belongs to; for a problem, the slot of the version
        or observation it concerns, or None when it concerns neither (e.g.
        an unknown directory, a symbolic link or a stale staging directory).
    version : Path or None
        Path of the version's main file or of the observation file; for a
        problem, the path of the faulty element.
    meta : Meta or None
        Parsed sidecar of a valid version, None for observations and
        problems.
    problem_code : str or None
        Machine-readable problem code, e.g. ``"missing_sidecar"``, or None.
    problem : str or None
        Human-readable problem description (in Polish), or None.
    observation : Observation or None, optional
        Parsed observation of an ``"observation"`` entry, None otherwise.
    provider : str or None, optional
        ``ProviderDescriptor.id`` of the slot's dataset; None for a problem
        without a slot.
    """

    kind: Literal["archive", "series", "catalog", "pmaxtp", "observation", "problem"]
    slot: str | None
    version: Path | None
    meta: Meta | None
    problem_code: str | None
    problem: str | None
    observation: Observation | None = None
    provider: str | None = None


@dataclass(frozen=True)
class StationFeature:
    """
    Station read from a ``stations.geojson`` catalog.

    Attributes
    ----------
    station_code : str
        Station code (``STATION_CODE_PATTERN``: nine IMGW-PIB digits or a
        WIGOS identifier).
    geometry : tuple of (float, float) or None
        Location as ``(lon, lat)`` in WGS84, or None when unknown.
    properties : Mapping of str to str, int, float, bool, Mapping or None
        Catalog properties of the station (kind, name, river, location
        source, activity, etc.); simple values, except the SPA thresholds of
        a ČHMÚ hydro station, ``"thresholds"``: an object (``source``,
        ``type``, ``H`` and ``Q`` with ``unit``, ``drought``, ``spa1``,
        ``spa2``, ``spa3`` and ``q50``) or None.
    provider : str, optional
        ``ProviderDescriptor.id`` of the catalog the station comes from.
    """

    station_code: str
    geometry: tuple[float, float] | None
    properties: Mapping[str, str | int | float | bool | Mapping[str, object] | None]
    provider: str = "IMGW-PIB"


@dataclass(frozen=True)
class StationCoverage:
    """
    Coverage of one variable at one station in a series.

    Attributes
    ----------
    station_code : str
        Station code (nine IMGW-PIB digits or a WIGOS identifier).
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

    station_code: str
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
    periods : tuple of tuple of (date, date) or None, optional
        Known periods of the station (per-station archives, ADR-003 D10):
        merged ranges of the station's own files; None for datasets whose
        archives cover the whole country.
    """

    file: Path
    sha256: str
    rows: int
    variables: Mapping[str, StationCoverage]
    periods: tuple[tuple[date, date], ...] | None = None


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
        Python option name in ``snake_case``, equal to the function parameter.
    type : {"str", "int", "float", "bool", "date", "path", "list", "choice", "object"}
        Value type of the option.
    required : bool
        Whether the option is required.
    flag : str
        CLI flag in ``--kebab-case``.
    choices : tuple of str
        Allowed values for ``"choice"`` options (or list items), empty otherwise.
    help : str
        Help text (in Polish).
    default : object, optional
        Default value published in the schema, or None.
    aliases : tuple of str, optional
        Short CLI aliases, e.g. ``("-y",)``.
    items : {"str", "int", "year", "choice"} or None, optional
        Item type of a ``"list"`` option, or None.
    minimum, maximum : float or None, optional
        Inclusive bounds published in the schema, or None.
    pattern : str or None, optional
        Regular expression published in the schema, or None.
    rest : {"param", "server", "local"}, optional
        REST role: request parameter, server configuration value, or absent
        from REST (local only).
    help_en : str, optional
        English help text, the same information as ``help`` (non-empty for
        every catalog option).
    writes : {"none", "add", "replace"}, optional
        Effect of giving the option: ``"add"`` writes only new files,
        ``"replace"`` may overwrite an existing file (e.g. ``path`` of an
        export or ``plan`` of ``store check``); ``"none"`` writes nothing.
    """

    name: str
    type: Literal[
        "str", "int", "float", "bool", "date", "path", "list", "choice", "object"
    ]
    required: bool
    flag: str
    choices: tuple[str, ...]
    help: str
    default: object = None
    aliases: tuple[str, ...] = ()
    items: Literal["str", "int", "year", "choice"] | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    rest: Literal["param", "server", "local"] = "param"
    help_en: str = ""
    writes: Writes = "none"


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
    function : str
        Name of the function from ``imgwtools.__all__`` the command calls.
    check : str or None
        Twin function for ``--check``, ``"check_command"``, or None.
    result : {"object", "list", "stream"}
        Result shape: one object, a ``Page`` of items, or a stream of lines.
    method : {"GET", "POST"} or None
        HTTP method of the REST endpoint, or None for a local-only command.
    requires : Mapping of str to tuple of str, optional
        Options required when the key option is given (``dependentRequired``).
    one_of : tuple of tuple of str, optional
        Alternative groups of required options (``oneOf``).
    rules : tuple of str, optional
        Other validation rules (in Polish), published as ``x-imgw.rules``.
    description_en : str, optional
        English description, the same information as ``description``.
    rules_en : tuple of str, optional
        English rules, in the order and number of ``rules``.
    writes : {"none", "add", "replace"}, optional
        Effect of a run (not of its check): ``"none"`` changes no file or
        store, ``"add"`` writes only new files, versions, a manifest or a
        task, ``"replace"`` may overwrite or remove existing user content
        (a manifest, a result file, a file of a download directory).
    network : bool, optional
        Whether a run connects to a source server for some option values.
    idempotent : bool, optional
        Whether repeating a run with the same options on the same source data
        changes nothing more (a stored version is reported ``unchanged``, a
        file is rewritten with the same bytes); the MCP ``idempotentHint``.
    env_root_when : Mapping of str to str, optional
        Option values under which an absent ``root`` comes from
        ``IMGW_STORE_ROOT`` (CLI, MCP stdio); empty means always.
    """

    name: str
    description: str
    options: tuple[CommandOption, ...]
    function: str
    check: str | None
    result: Literal["object", "list", "stream"]
    method: Literal["GET", "POST"] | None
    requires: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    one_of: tuple[tuple[str, ...], ...] = ()
    rules: tuple[str, ...] = ()
    description_en: str = ""
    rules_en: tuple[str, ...] = ()
    writes: Writes = "none"
    network: bool = False
    idempotent: bool = True
    env_root_when: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Page[T]:
    """
    One page of a list command result.

    Attributes
    ----------
    items : tuple
        Items of the slice ``[offset, offset + limit)`` in function order.
    total : int
        Number of items after the function's filters, before paging.
    limit : int or None
        Maximum page size, or None for all items from ``offset``.
    offset : int
        Index of the first returned item.
    """

    items: tuple[T, ...]
    total: int
    limit: int | None
    offset: int


@dataclass(frozen=True)
class CommandResult[T]:
    """
    Envelope of a catalog command run (``run_command``, ``check_command``).

    Attributes
    ----------
    command : str
        Command name, e.g. ``"store sync"``.
    check : bool
        Whether ``result`` is a check plan (``imgw-plan/1``).
    status : {"ok", "partial", "failed", "cancelled"}
        Overall status computed from the result.
    result : object or None
        Function result, or None for a cancellation without a report.
    notices : tuple of Notice
        Distinct notices in order of first occurrence.
    """

    command: str
    check: bool
    status: Literal["ok", "partial", "failed", "cancelled"]
    result: T | None
    notices: tuple[Notice, ...]

    def to_json(
        self,
        *,
        root: PathArg | None = None,
        server: bool = False,
        lang: Lang = DEFAULT_LANG,
    ) -> dict[str, object]:
        """
        Convert the envelope to an ``imgw-result/1`` document.

        Parameters
        ----------
        root : str or os.PathLike or None, optional
            Store root; absolute paths below it become POSIX paths relative to
            it, other absolute paths stay absolute. Relative paths of the
            result (project pins, relative to the project's store) stay
            relative in every working directory.
        server : bool, optional
            REST mode: the root is written as ``"."`` and its prefix is
            removed from every text.
        lang : {"en", "pl"}, optional
            Language of the catalog messages in the result and the notices
            (English by default, AGI-9.2).

        Returns
        -------
        dict of str to object
            JSON-compatible document with ``schema``, ``command``, ``check``,
            ``status``, ``result`` and ``notices``.
        """
        document = {
            "schema": "imgw-result/1",
            "command": self.command,
            "check": self.check,
            "status": self.status,
            "result": self.result,
            "notices": self.notices,
        }
        return cast(
            dict[str, object], jsonable(document, root=root, server=server, lang=lang)
        )


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
    station_code : str or None, optional
        Station code (``STATION_CODE_PATTERN``: nine IMGW-PIB digits or a
        WIGOS identifier); required for ``"station_series"`` files.
    content_sha256 : str or None, optional
        ``content_sha256`` of the pinned archive version (canonical form);
        None for pins of datasets without a canonical form.
    content_form : str or None, optional
        ``content_form`` of the pinned archive version; present exactly when
        ``content_sha256`` is.
    """

    role: Literal["series", "station_series", "catalog", "input"]
    path: Path
    sha256: str
    station_code: str | None = None
    content_sha256: str | None = None
    content_form: str | None = None


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
    tasks : Mapping of str to {"unpinned", "current", "content_match", "missing", "changed", "upgraded", "failed", "cancelled"}
        State of each processed task, keyed by task name; ``"content_match"``
        means every pin is current or matched by an equivalent version with
        the same canonical content (at least one), never silently current.
    files : tuple of OperationResult
        Per-file outcomes with the §13.7 slot of the pinned file (a station
        file of a series has the selector ``series:<key>:<station_code>``)
        and the task name in ``task``; an error of a whole task has
        ``slot=None``, and failed items carry ``error_code``.
    cancelled : bool
        Whether the operation was cancelled.
    """

    tasks: Mapping[
        str,
        Literal[
            "unpinned",
            "current",
            "content_match",
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
