"""Freshness check (listing + HEAD) and plan-driven synchronization of archives."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from urllib.parse import unquote, urlsplit

import httpx

from imgwtools._parsing.chmi import ListingEntry, parse_listing
from imgwtools.datasets import (
    _CHMI_HYDRO_FILE,
    _CHMI_METEO_FILE,
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
    _archive_from_path,
    _parse_stations,
    archive_files,
    get_dataset,
    get_provider,
    parse_months,
    parse_years,
)
from imgwtools.datasets import datasets as registered_datasets
from imgwtools.exceptions import (
    ErrorCode,
    IMGWCancelledError,
    IMGWDataError,
    IMGWError,
    IMGWValidationError,
)
from imgwtools.fetch import (
    _IDENTIFY,
    DEFAULT_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    UNPUBLISHED,
    DownloadResult,
    _archive_response,
    _archive_slot,
    download_hydro_data,
    download_meteo_data,
)
from imgwtools.store.reader import _Reference, _reference_signal
from imgwtools.store.series import (
    SeriesState,
    _current_version,
    _root,
    _scan_inputs,
    _series_descriptor,
    _series_state,
    _Version,
    build_series,
)
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    OperationResult,
    PathArg,
    PlanAction,
    PlanItem,
    Progress,
    ProgressHook,
    SeriesReport,
    StoreHandle,
    StorePlan,
    SyncReport,
)
from imgwtools.store.writer import write_archive
from imgwtools.urls import IMGW_PUBLIC_DATA_URL

CANCELLED = "anulowano"
NO_SIGNAL = "brak porównywalnego nagłówka ETag/Last-Modified"
NO_LISTING_SIGNAL = "brak porównywalnego sygnału"

_HREF = re.compile(r"""href\s*=\s*["']([^"'#?]+)""", re.IGNORECASE)
_DONE = {"created", "relabeled", "unchanged", "reused"}
_SYNC = "store sync"
# File-name grammar of per-station archives (spec 2026-10-18 §2.3); group 1 is
# the station code.
_STATION_FILES = {
    "station_year": _CHMI_HYDRO_FILE,
    "station_element": _CHMI_METEO_FILE,
}
Status = Literal["current", "newer", "missing", "unverifiable", "check_failed"]


@dataclass(frozen=True)
class _Signal:
    etag: str | None
    last_modified: str | None
    content_length: int | None


def _listing(client: httpx.Client, directory: str) -> set[str] | None:
    """File names published in a server directory; ``None`` when the directory is absent."""
    response = client.get(f"{IMGW_PUBLIC_DATA_URL}/{directory}/")
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    return {
        PurePosixPath(unquote(urlsplit(href).path)).name
        for href in _HREF.findall(response.text)
    }


def _head(client: httpx.Client, archive: ArchiveFile) -> _Signal | None:
    """Remote HTTP signal of an archive; ``None`` when the file is not published."""
    response = client.head(archive.url)
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    length = response.headers.get("Content-Length")
    return _Signal(
        response.headers.get("ETag"),
        response.headers.get("Last-Modified"),
        int(length) if length is not None and length.isdigit() else None,
    )


# Prefixes of the server errors of a check; any other check_failed reason is a
# data error (unreadable listing or local version).
_HTTP_ERRORS = (
    "Przekroczono czas odpowiedzi serwera ",
    "Błąd HTTP ",
    "Błąd połączenia z ",
)


def _http_error(exc: Exception, *, source: str = "IMGW") -> str:
    if isinstance(exc, httpx.TimeoutException):
        return f"{_HTTP_ERRORS[0]}{source}: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{_HTTP_ERRORS[1]}{exc.response.status_code}: {exc.request.url}"
    return f"{_HTTP_ERRORS[2]}{source}: {exc}"


def _failure_code(error: str | None) -> ErrorCode:
    """Error code of a ``check_failed`` reason: provider server or data."""
    return (
        "source_unavailable"
        if error is not None and error.startswith(_HTTP_ERRORS)
        else "data_error"
    )


def _source(archive: ArchiveFile) -> str:
    """Provider name in the messages about an archive's server."""
    descriptor = get_dataset(archive.dataset)
    if descriptor.archive_scope == "country":
        return "IMGW"
    return get_provider(descriptor.provider).short_name


def _compare(local: dict[str, object], remote: _Signal) -> Status:
    """Compare every header present on both sides; Content-Length never decides."""
    pairs = [
        (local.get("etag"), remote.etag),
        (local.get("last_modified"), remote.last_modified),
    ]
    comparable = [
        (mine, theirs)
        for mine, theirs in pairs
        if mine is not None and theirs is not None
    ]
    if not comparable:
        return "unverifiable"
    return "current" if all(mine == theirs for mine, theirs in comparable) else "newer"


def _item(
    archive: ArchiveFile,
    status: Status,
    *,
    local: _Version | None = None,
    signal: _Signal | None = None,
    error: str | None = None,
) -> PlanItem:
    return PlanItem(
        archive=archive,
        status=status,
        local_path=Path(local.relative) if local is not None else None,
        local_sha256=local.sha256 if local is not None else None,
        remote_etag=signal.etag if signal else None,
        remote_last_modified=signal.last_modified if signal else None,
        content_length=signal.content_length if signal else None,
        error=error,
    )


def _minute(last_modified: str | None) -> datetime | None:
    """UTC time of a ``Last-Modified`` value truncated to the minute, or None."""
    if not last_modified:
        return None
    try:
        moment = parsedate_to_datetime(last_modified)
    except (TypeError, ValueError, OverflowError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).replace(second=0, microsecond=0)


def _listed_at(moment: datetime) -> str:
    """Listing time in the plan form ``YYYY-MM-DDTHH:MMZ``."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


@dataclass(frozen=True)
class _Listing:
    """Files of a listed server directory by name, or why the listing is unusable."""

    entries: Mapping[str, ListingEntry]
    error: str | None = None


@dataclass(frozen=True)
class _Target:
    """
    Per-station file to check against its slot.

    ``entry`` is the listing row of a published file; without it ``error``
    names the unusable listing of its directory, and neither of them means
    that the source does not publish the file.
    """

    archive: ArchiveFile
    entry: ListingEntry | None = None
    error: str | None = None


def _read_listing(client: httpx.Client, url: str, *, source: str) -> _Listing:
    """GET and parse an nginx listing; any failure is kept as the listing's error."""
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return _Listing({}, _http_error(exc, source=source))
    if response.status_code != 200:
        return _Listing({}, f"{_HTTP_ERRORS[1]}{response.status_code}: {url}")
    try:
        entries = parse_listing(response.content, url=url)
    except IMGWDataError as exc:
        return _Listing({}, str(exc))
    return _Listing({entry.name: entry for entry in entries})


def _directories(
    descriptor: DatasetDescriptor, candidates: tuple[ArchiveFile, ...] | None
) -> list[str]:
    """Server directories whose listings show the requested files of a dataset."""
    assert descriptor.server_dir is not None
    if candidates is None:
        return [descriptor.server_dir]
    return sorted(
        {PurePosixPath(archive.server_path).parent.as_posix() for archive in candidates}
    )


def _no_files(descriptor: DatasetDescriptor, code: str) -> PlanAction:
    return PlanAction(
        _SYNC,
        "unverifiable",
        f"stacja {code}: brak plików zbioru {descriptor.key} u źródła",
    )


def _station_targets(
    descriptor: DatasetDescriptor,
    codes: tuple[str, ...],
    candidates: tuple[ArchiveFile, ...] | None,
    listings: Mapping[str, _Listing],
) -> tuple[list[_Target], list[PlanAction]]:
    """
    Requested files of each station by the listings, or one action per station.

    A requested file absent from a readable listing while the station has
    other files of the dataset there is unpublished; a station without any
    file of the dataset gets one ``unverifiable`` action instead of items
    (spec 2026-10-18 §4.2, steps 5-6). A listing without any name of the
    dataset's grammar is unreadable (a changed server layout, spec §15).
    Candidates in an unreadable listing keep its error; without candidates
    (years taken from the listing) such a station gets a ``check_failed``
    action.

    Parameters
    ----------
    descriptor : DatasetDescriptor
        Per-station dataset.
    codes : tuple of str
        Requested station codes, sorted.
    candidates : tuple of ArchiveFile or None
        Offline candidates of the request, or None to take every listed file
        of the stations.
    listings : Mapping of str to _Listing
        Listing of every directory of `_directories`.

    Returns
    -------
    tuple of (list of _Target, list of PlanAction)
        Files to check (unsorted) and the station actions.
    """
    grammar = _STATION_FILES[descriptor.archive_scope]
    provider = get_provider(descriptor.provider)
    wanted = set(codes)
    listed: dict[str, dict[str, tuple[ArchiveFile, ListingEntry]]] = defaultdict(dict)
    failures: dict[str, str] = {}
    for directory in _directories(descriptor, candidates):
        listing = listings[directory]
        if listing.error is not None:
            failures[directory] = listing.error
            continue
        known = False
        for name, entry in listing.entries.items():
            match = grammar.fullmatch(name)
            if match is None:
                continue
            known = True
            if match[1] not in wanted:
                continue
            archive = _archive_from_path(descriptor.key, f"{directory}/{name}")
            if archive is not None:
                listed[match[1]][archive.server_path] = (archive, entry)
        if not known:
            failures[directory] = (
                f"Nieczytelny listing {provider.base_url}{directory}/: "
                f"brak plików zbioru {descriptor.key}"
            )
    requested: dict[str, list[ArchiveFile]] = defaultdict(list)
    for archive in candidates or ():
        requested[archive.station_code or ""].append(archive)
    targets: list[_Target] = []
    actions: list[PlanAction] = []
    for code in codes:
        files = listed.get(code, {})
        if candidates is None:
            if failures:
                actions.extend(
                    PlanAction(_SYNC, "check_failed", f"stacja {code}: {error}")
                    for error in failures.values()
                )
            elif files:
                targets.extend(
                    _Target(archive, entry) for archive, entry in files.values()
                )
            else:
                actions.append(_no_files(descriptor, code))
            continue
        if not files and not failures:
            actions.append(_no_files(descriptor, code))
            continue
        for archive in requested[code]:
            directory = PurePosixPath(archive.server_path).parent.as_posix()
            if directory in failures:
                targets.append(_Target(archive, error=failures[directory]))
            elif archive.server_path in files:
                targets.append(_Target(archive, files[archive.server_path][1]))
            else:
                targets.append(_Target(archive))
    return targets, actions


def _listed_item(
    root: Path,
    archive: ArchiveFile,
    status: Status,
    *,
    reference: _Reference | None = None,
    entry: ListingEntry | None = None,
    error: str | None = None,
) -> PlanItem:
    """Plan item of a per-station file: listing signal and the slot's reference."""
    version = reference.version.version if reference is not None else None
    meta = reference.version.meta if reference is not None else None
    observation = reference.observation if reference is not None else None
    return PlanItem(
        archive=archive,
        status=status,
        local_path=version.relative_to(root) if version is not None else None,
        local_sha256=meta.sha256 if meta is not None else None,
        remote_etag=None,
        remote_last_modified=None,
        content_length=entry.size if entry is not None else None,
        error=error,
        station_code=archive.station_code,
        signal="listing",
        remote_listed_at=_listed_at(entry.modified) if entry is not None else None,
        local_observation=observation.relative_to(root)
        if observation is not None
        else None,
    )


def _check_target(root: Path, target: _Target) -> PlanItem:
    """
    Status of a per-station file by its listing row and the slot's reference signal.

    The reference signal is the newest observation of the current version, or
    the version's own ``extra.http`` and size (ADR-003 D18). The file is
    ``current`` when the reference ``Last-Modified`` truncated to the minute
    and the reference size equal the listing's time and size.
    """
    archive = target.archive
    try:
        reference = _reference_signal(root, slot=_archive_slot(archive))
    except IMGWDataError as exc:
        return _listed_item(root, archive, "check_failed", error=str(exc))
    if target.error is not None:
        return _listed_item(
            root, archive, "check_failed", reference=reference, error=target.error
        )
    entry = target.entry
    if entry is None:
        return _listed_item(
            root, archive, "unverifiable", reference=reference, error=UNPUBLISHED
        )
    if reference is None:
        return _listed_item(root, archive, "missing", entry=entry)
    published = _minute(reference.last_modified)
    if published is None:
        return _listed_item(
            root,
            archive,
            "unverifiable",
            reference=reference,
            entry=entry,
            error=NO_LISTING_SIGNAL,
        )
    same = (published, reference.size_bytes) == (entry.modified, entry.size)
    return _listed_item(
        root,
        archive,
        "current" if same else "newer",
        reference=reference,
        entry=entry,
    )


def _announce(
    item: PlanItem,
    index: int,
    total: int,
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
) -> None:
    """Notice of an unverifiable or failed item and the progress after it."""
    if item.status == "unverifiable" and on_notice is not None:
        on_notice(
            Notice(
                "warning",
                "source_unverifiable",
                f"{item.archive.server_path}: {item.error}",
            )
        )
    elif item.status == "check_failed" and on_notice is not None:
        on_notice(
            Notice(
                "error",
                "archive_failed",
                f"{item.archive.server_path}: {item.error}",
            )
        )
    if on_progress is not None:
        on_progress(
            Progress(index, total, "archive", item.status, item.archive.server_path)
        )


def _position(
    order: Mapping[str, int], archive: ArchiveFile
) -> tuple[int, str, int, str, str]:
    """Plan order of per-station files: dataset, station, year, param, path."""
    return (
        order[archive.dataset],
        archive.station_code or "",
        archive.year or 0,
        archive.param or "",
        archive.server_path,
    )


def _check_listed(
    client: httpx.Client,
    root: Path,
    descriptors: list[DatasetDescriptor],
    codes: tuple[str, ...],
    candidates: Mapping[str, tuple[ArchiveFile, ...] | None],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[PlanItem], list[PlanAction], bool]:
    """
    Check per-station files by one listing GET per directory, without HEAD.

    Parameters
    ----------
    client : httpx.Client
        Client of the check.
    root : Path
        Store root.
    descriptors : list of DatasetDescriptor
        Per-station datasets of the request.
    codes : tuple of str
        Requested station codes, sorted.
    candidates : Mapping of str to tuple of ArchiveFile or None
        Offline candidates of each dataset; None takes the listed years.
    on_progress, on_notice : hook or None
        Hooks of `check_store`.
    cancel : Cancel or None
        Polled before every listing and every file.

    Returns
    -------
    tuple of (list of PlanItem, list of PlanAction, bool)
        Items in plan order, station actions and the cancellation flag.
    """
    order = {item.key: index for index, item in enumerate(registered_datasets())}
    ordered = sorted(descriptors, key=lambda descriptor: order[descriptor.key])
    listings: dict[str, _Listing] = {}
    for descriptor in ordered:
        provider = get_provider(descriptor.provider)
        for directory in _directories(descriptor, candidates[descriptor.key]):
            if cancel is not None and cancel():
                known = sorted(
                    (
                        archive
                        for item in ordered
                        for archive in candidates[item.key] or ()
                    ),
                    key=lambda archive: _position(order, archive),
                )
                return (
                    [
                        _listed_item(root, archive, "unverifiable", error=CANCELLED)
                        for archive in known
                    ],
                    [],
                    True,
                )
            listings[directory] = _read_listing(
                client,
                f"{provider.base_url}{directory}/",
                source=provider.short_name,
            )
    targets: list[_Target] = []
    actions: list[PlanAction] = []
    for descriptor in ordered:
        found, stations = _station_targets(
            descriptor, codes, candidates[descriptor.key], listings
        )
        targets.extend(found)
        actions.extend(stations)
    targets.sort(key=lambda target: _position(order, target.archive))
    if on_notice is not None:
        for action in actions:
            on_notice(
                Notice("warning", "source_unverifiable", action.detail)
                if action.status == "unverifiable"
                else Notice("error", "archive_failed", action.detail)
            )
    items: list[PlanItem] = []
    cancelled = False
    for index, target in enumerate(targets, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        if cancelled:
            items.append(
                _listed_item(root, target.archive, "unverifiable", error=CANCELLED)
            )
            continue
        items.append(_check_target(root, target))
        _announce(
            items[-1],
            index,
            len(targets),
            on_progress=on_progress,
            on_notice=on_notice,
        )
    return items, actions, cancelled


def _descriptors(datasets: Iterable[str]) -> list[DatasetDescriptor]:
    """Measurement series datasets of the request, without repetitions."""
    if isinstance(datasets, str):
        raise IMGWValidationError(
            "Parametr datasets musi być listą kluczy zbiorów",
            details={"option": "datasets", "value": datasets},
        )
    found: dict[str, DatasetDescriptor] = {}
    for dataset in dict.fromkeys(datasets):
        descriptor = _series_descriptor(dataset)
        found.setdefault(descriptor.key, descriptor)
    if not found:
        raise IMGWValidationError(
            "Wybierz co najmniej jeden zbiór", details={"option": "datasets"}
        )
    return list(found.values())


def _country_archives(
    descriptors: list[DatasetDescriptor],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> list[ArchiveFile]:
    """Country archives (IMGW-PIB) of the request, in the 3.0.0 order."""
    if stations is not None:
        raise IMGWValidationError(
            "Archiwa IMGW-PIB obejmują cały kraj; opcja stations dotyczy wyłącznie "
            "zbiorów stacji ČHMÚ",
            details={"option": "stations", "value": None},
        )
    if years is None:
        raise IMGWValidationError(
            "Zbiory IMGW-PIB wymagają opcji years",
            details={"option": "years", "value": None},
        )
    selected_years = parse_years(years, option="years")
    selected_months = (
        parse_months(months, option="months") if months is not None else None
    )
    result: dict[str, ArchiveFile] = {}
    for descriptor in descriptors:
        for archive in archive_files(
            descriptor.key, years=selected_years, months=selected_months
        ):
            result.setdefault(archive.server_path, archive)
    return list(result.values())


def _station_request(
    descriptors: list[DatasetDescriptor],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> tuple[tuple[str, ...], dict[str, tuple[ArchiveFile, ...] | None]]:
    """
    Station codes and offline candidates of a per-station request (ČHMÚ).

    Returns
    -------
    tuple of (tuple of str, dict)
        Sorted unique station codes and, per dataset key, the candidates of
        `archive_files` or None when the years come from the listing
        (station × year files without ``years``).
    """
    keys = ", ".join(descriptor.key for descriptor in descriptors)
    if stations is None:
        raise IMGWValidationError(
            f"Zbiory {keys} wymagają opcji stations: kodów stacji (pliki źródła "
            "obejmują pojedyncze stacje)",
            details={"option": "stations", "value": None},
        )
    if months is not None:
        raise IMGWValidationError(
            f"Opcja months nie dotyczy zbiorów {keys}: pliki stacji nie są miesięczne",
            details={"option": "months", "value": None},
        )
    codes: tuple[str, ...] = ()
    provided: Iterable[str] = stations
    candidates: dict[str, tuple[ArchiveFile, ...] | None] = {}
    for descriptor in descriptors:
        # Every dataset validates the codes by its provider's grammar.
        codes = provided = _parse_stations(provided, get_provider(descriptor.provider))
        candidates[descriptor.key] = (
            None
            if years is None and descriptor.archive_scope == "station_year"
            else archive_files(descriptor.key, years=years, stations=codes)
        )
    return codes, candidates


def _selection(
    datasets: Iterable[str],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> tuple[
    list[DatasetDescriptor],
    tuple[str, ...],
    dict[str, tuple[ArchiveFile, ...] | None],
    list[ArchiveFile],
]:
    """
    Validate the selectors of a check offline, before any request.

    Shared by `check_store` and the command catalog (``validate_command`` of
    ``store check`` and ``store sync``).

    Returns
    -------
    tuple
        The datasets without repetitions, then for per-station datasets
        (ČHMÚ) the station codes and the candidates of each dataset (see
        `_station_request`) with no archives, or for country datasets
        (IMGW-PIB) no codes, no candidates and the archives.
    """
    descriptors = _descriptors(datasets)
    per_station = {descriptor.archive_scope != "country" for descriptor in descriptors}
    if len(per_station) > 1:
        raise IMGWValidationError(
            "Jedno wywołanie obejmuje zbiory jednego rodzaju: archiwa krajowe "
            "IMGW-PIB (bez opcji stations) albo pliki stacji ČHMÚ (z opcją "
            f"stations); podano {', '.join(item.key for item in descriptors)}",
            details={"option": "stations", "value": None},
        )
    if per_station == {True}:
        codes, candidates = _station_request(descriptors, years, months, stations)
        return descriptors, codes, candidates, []
    return descriptors, (), {}, _country_archives(descriptors, years, months, stations)


def _series_states(
    root: Path, descriptors: list[DatasetDescriptor], items: list[PlanItem]
) -> dict[str, SeriesState]:
    """Series state of every dataset; ``current`` turns ``outdated`` with pending items."""
    states: dict[str, SeriesState] = {}
    for descriptor in descriptors:
        inputs, problems = _scan_inputs(root, descriptor)
        state = _series_state(root, descriptor, inputs, reliable=not problems)
        pending = any(
            item.archive.dataset == descriptor.key
            and item.status in ("newer", "missing")
            for item in items
        )
        states[descriptor.slug] = (
            "outdated" if state == "current" and pending else state
        )
    return states


def _plan_target(root: Path, plan: PathArg) -> Path:
    """Plan file to write: outside the store, in an existing directory."""
    target = Path(plan).expanduser().absolute()
    resolved, store = target.resolve(), root.resolve()
    if resolved == store or store in resolved.parents:
        raise IMGWValidationError(
            f"Plan musi być zapisany poza magazynem: {target}",
            details={"option": "plan", "value": str(target)},
        )
    if not target.parent.is_dir():
        raise IMGWValidationError(
            f"Katalog pliku planu nie istnieje: {target.parent}",
            details={"option": "plan", "value": str(target)},
        )
    return target


def check_store(
    root: PathArg | StoreHandle,
    /,
    *,
    datasets: Iterable[str],
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    stations: Iterable[str] | None = None,
    plan: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan a synchronization without downloading anything.

    Nothing is written to the store, not even staging files, and no archive is
    fetched. IMGW-PIB country archives are enumerated offline and checked with
    the listing of their parent directory and an HTTP ``HEAD`` request (a file
    is published when its name appears in the listing). ČHMÚ per-station files
    are checked with a single GET of each server directory listing, without
    any ``HEAD``: the listing's time (to the minute) and size are compared with
    the reference signal of the slot (the newest observation of its current
    version, or that version's ``Last-Modified`` and size). Per-archive errors
    are recorded in the plan, never raised.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    datasets : Iterable[str]
        Dataset keys, slugs or legacy aliases of measurement series datasets,
        either all IMGW-PIB or all ČHMÚ. A bare string is rejected.
    years : YearsArg or None, optional
        Years to check (hydrological or calendar, as defined by each dataset):
        ``2024``, ``"2020-2023"``, ``"2020,2022"`` or a collection of such
        items. Required for IMGW-PIB datasets; optional for
        ``cz.chmi.hydro_daily`` (None checks every year the listing shows for
        the stations); rejected for ``cz.chmi.meteo_daily``.
    months : MonthsArg or None, optional
        Months (1-12, same forms as ``years``) filtering physically monthly
        IMGW-PIB files only; yearly archives are returned once regardless of
        this filter. Rejected for ČHMÚ datasets.
    stations : Iterable[str] or None, optional
        ČHMÚ station codes (WIGOS identifiers); required for ČHMÚ datasets and
        rejected for IMGW-PIB datasets.
    plan : str, os.PathLike or None, optional
        File to save the plan to (``imgw-plan/1``, see `StorePlan.to_json`); it
        must lie outside the store in an existing directory.
    on_progress : ProgressHook or None, optional
        Called after each archive with its plan status.
    on_notice : NoticeHook or None, optional
        Receives a ``source_unverifiable`` warning for every ``unverifiable``
        item or action and an ``archive_failed`` error for every
        ``check_failed`` item or action.
    cancel : Cancel or None, optional
        Polled before each listing and archive; once it returns ``True`` the
        remaining archives are listed as ``unverifiable`` with error
        ``"anulowano"``.

    Returns
    -------
    StorePlan
        ``imgw-plan/1`` plan with one item per archive: ``current``,
        ``newer``, ``missing`` (published but not stored), ``unverifiable``
        (no comparable signal, ``"nieopublikowany"`` when the file is not
        published, or ``"anulowano"``) or ``check_failed`` (listing or HEAD
        error, unreadable listing, local version or observation). IMGW-PIB
        items compare every header present on both sides (``signal="head"``);
        ČHMÚ items carry ``station_code``, ``signal="listing"``, the listing
        time ``remote_listed_at``, the listing size ``content_length`` and the
        reference observation ``local_observation``, and are ordered by
        dataset, station, year, element. A ČHMÚ station without any file of a
        dataset is one ``store sync`` action (``unverifiable``, or
        ``check_failed`` when the listing of its years cannot be read).
        ``series_state`` holds the local state of each dataset's series keyed
        by slug, with ``current`` turned into ``outdated`` when the plan has
        ``newer``/``missing`` items for that dataset. ``requests`` counts the
        requests made by the check (``"made"``) and the HEAD and GET of every
        ``newer`` and ``missing`` item (``"planned"``).

    Raises
    ------
    IMGWStoreError
        If ``root`` is not a supported IMGW store or a store path contains a
        symbolic link.
    IMGWValidationError
        If ``datasets`` is a string or empty, a dataset is unknown or does not
        produce measurement series, IMGW-PIB and ČHMÚ datasets are mixed or
        ``stations`` is missing or given against the datasets (option
        ``stations``), a station code does not follow the provider's grammar,
        the years/months are missing, invalid or rejected for the datasets, or
        ``plan`` lies inside the store or in a missing directory.
    """
    path = _root(root)
    descriptors, codes, candidates, archives = _selection(
        datasets, years, months, stations
    )
    listed = descriptors[0].archive_scope != "country"
    target = _plan_target(path, plan) if plan is not None else None
    made = 0

    def count(_request: httpx.Request) -> None:
        nonlocal made
        made += 1

    with httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers=_IDENTIFY if listed else None,
        event_hooks={"request": [count]},
    ) as client:
        if listed:
            items, actions, cancelled = _check_listed(
                client,
                path,
                descriptors,
                codes,
                candidates,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
        else:
            items, cancelled = _check_country(
                client,
                path,
                archives,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
            actions = []
    result = StorePlan(
        schema="imgw-plan/1",
        root=path,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state=_series_states(path, descriptors, items),
        actions=tuple(actions),
        cancelled=cancelled,
        requests={
            "made": made,
            "planned": 2 * sum(item.status in ("newer", "missing") for item in items),
        },
    )
    if target is not None:
        result.to_json(target)
    return result


def _check_country(
    client: httpx.Client,
    root: Path,
    archives: list[ArchiveFile],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[PlanItem], bool]:
    """Check country archives by directory listings and HEAD, in request order."""
    listings: dict[str, set[str] | Exception | None] = {}
    items: list[PlanItem] = []
    cancelled = False
    for index, archive in enumerate(archives, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        if cancelled:
            items.append(_item(archive, "unverifiable", error=CANCELLED))
            continue
        items.append(_check_one(client, root, archive, listings))
        _announce(
            items[-1],
            index,
            len(archives),
            on_progress=on_progress,
            on_notice=on_notice,
        )
    return items, cancelled


def _check_one(
    client: httpx.Client,
    root: Path,
    archive: ArchiveFile,
    listings: dict[str, set[str] | Exception | None],
) -> PlanItem:
    try:
        local = _current_version(root, archive)
    except IMGWDataError as exc:
        return _item(archive, "check_failed", error=str(exc))
    directory = PurePosixPath(archive.server_path).parent.as_posix()
    if directory not in listings:
        try:
            listings[directory] = _listing(client, directory)
        except httpx.HTTPError as exc:
            listings[directory] = exc
    listing = listings[directory]
    if isinstance(listing, Exception):
        return _item(archive, "check_failed", local=local, error=_http_error(listing))
    if listing is None or PurePosixPath(archive.server_path).name not in listing:
        return _item(archive, "unverifiable", local=local, error=UNPUBLISHED)
    try:
        signal = _head(client, archive)
    except httpx.HTTPError as exc:
        return _item(archive, "check_failed", local=local, error=_http_error(exc))
    if signal is None:
        return _item(archive, "unverifiable", local=local, error=UNPUBLISHED)
    if local is None:
        return _item(archive, "missing", signal=signal)
    status = _compare(dict(local.http), signal)
    return _item(
        archive,
        status,
        local=local,
        signal=signal,
        error=NO_SIGNAL if status == "unverifiable" else None,
    )


def _download(
    archive: ArchiveFile, /, *, client: httpx.Client | None = None
) -> DownloadResult:
    """
    GET one archive for a store version.

    IMGW-PIB ZIP archives go through the 2.1.1 download functions. A
    per-station file (ČHMÚ) is taken as it is, through ``client`` when given.

    Raises
    ------
    IMGWConnectionError
        If the download fails (``source_unavailable``).
    IMGWDataError
        If an IMGW-PIB archive is no ZIP or a header is invalid.
    """
    descriptor = get_dataset(archive.dataset)
    if descriptor.archive_scope != "country":
        source = get_provider(descriptor.provider).short_name
        if client is not None:
            return _archive_response(client, archive.url, source=source, zipped=False)
        with httpx.Client(
            timeout=DOWNLOAD_TIMEOUT, follow_redirects=True, headers=_IDENTIFY
        ) as own:
            return _archive_response(own, archive.url, source=source, zipped=False)
    slug = descriptor.slug
    assert archive.year is not None
    if slug.startswith("hydro_"):
        intervals: dict[str, Literal["dobowe", "miesieczne", "polroczne_i_roczne"]] = {
            "hydro_daily": "dobowe",
            "hydro_monthly": "miesieczne",
            "hydro_semiannual": "polroczne_i_roczne",
        }
        return download_hydro_data(
            intervals[slug],
            archive.year,
            archive.month,
            cast(Literal["T", "Q", "H"] | None, archive.param),
        )
    subtype = "klimat" if slug == "meteo_climate_daily" else "opad"
    return download_meteo_data("dobowe", subtype, archive.year, archive.month)


def _result(
    item: PlanItem,
    status: Literal[
        "created",
        "relabeled",
        "unchanged",
        "reused",
        "failed",
        "stale_plan",
        "cancelled",
    ],
    *,
    version: Path | None = None,
    error: str | None = None,
    error_code: ErrorCode | None = None,
) -> OperationResult:
    return OperationResult(
        _archive_slot(item.archive), status, version, error, error_code=error_code
    )


def _stale(item: PlanItem, signal: _Signal | None) -> bool:
    """Whether the HEAD signal differs from the signal the item was planned with."""
    if signal is None:
        return True
    if item.signal == "listing":
        moment = _minute(signal.last_modified)
        return (
            moment is None
            or _listed_at(moment) != item.remote_listed_at
            or signal.content_length != item.content_length
        )
    return (signal.etag, signal.last_modified) != (
        item.remote_etag,
        item.remote_last_modified,
    )


def sync_store(
    root: PathArg | StoreHandle,
    /,
    *,
    datasets: Iterable[str] | None = None,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    stations: Iterable[str] | None = None,
    plan: StorePlan | PathArg | None = None,
    series: bool = True,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> SyncReport:
    """
    Download the archives that a plan marks as new or missing.

    Without ``plan`` the plan is built by :func:`check_store` from the given
    selectors; ``plan`` and the selectors are mutually exclusive. Before each
    download an HTTP ``HEAD`` re-validates the item: when the ETag or
    Last-Modified (IMGW-PIB), or the Last-Modified minute or Content-Length
    against the listing (ČHMÚ), differs from the plan, or the file is gone,
    the item ends as ``stale_plan`` and is not downloaded. ``check_failed``
    items are never downloaded. An ``unverifiable`` item is downloaded (then
    deduplicated by SHA-256) only in a sync without a supplied plan; from a
    supplied plan it stays ``unchanged`` with a ``source_unverifiable``
    warning. An unpublished item (``"nieopublikowany"``) stays ``unchanged``
    and does not block the series. Failures of single archives are reported
    per slot, not raised.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    datasets : Iterable[str] or None, optional
        Dataset keys, slugs or legacy aliases; required when ``plan`` is not
        given.
    years : YearsArg or None, optional
        Years to synchronize (``2024``, ``"2020-2023"``, ``"2020,2022"`` or a
        collection of such items), as in :func:`check_store`.
    months : MonthsArg or None, optional
        Months (1-12) filtering physically monthly IMGW-PIB files.
    stations : Iterable[str] or None, optional
        ČHMÚ station codes, as in :func:`check_store`.
    plan : StorePlan, str, os.PathLike or None, optional
        Plan from :func:`check_store`, or the path of its ``imgw-plan/1`` JSON file.
        Must refer to the same store root.
    series : bool, optional
        Rebuild the series of every dataset in the plan with :func:`build_series`
        once all its archives synchronized successfully. Defaults to ``True``.
    on_progress : ProgressHook or None, optional
        Called after each archive with its operation status; also forwarded to
        :func:`check_store` and :func:`build_series`.
    on_notice : NoticeHook or None, optional
        Receives warnings and errors (``stale_plan``, ``source_unverifiable``,
        ``archive_failed``) and notices of the writer (e.g.
        ``content_unchanged``) and the series builder.
    cancel : Cancel or None, optional
        Polled before each archive; once it returns ``True`` the remaining items
        and series end as ``cancelled``.

    Returns
    -------
    SyncReport
        One :class:`OperationResult` per plan item (``created``, ``relabeled``,
        ``unchanged``, ``reused``, ``failed``, ``stale_plan`` or
        ``cancelled``), then one ``failed`` result without a slot for every
        ``check_failed`` station action of the plan (a ČHMÚ listing that could
        not be read), one :class:`SeriesReport` per dataset when ``series`` is
        true (``failed`` or ``cancelled`` without building when the dataset
        has incomplete inputs) and the overall cancellation flag.

    Raises
    ------
    IMGWValidationError
        If both ``plan`` and selectors are given, ``datasets`` is missing
        without a plan, the plan refers to another store, or the selectors are
        invalid (see :func:`check_store`).
    IMGWDataError
        If the plan file cannot be read.
    IMGWStoreError
        If ``root`` is not a supported IMGW store.
    """
    path = _root(root)
    if plan is not None and any(
        option is not None for option in (datasets, years, months, stations)
    ):
        raise IMGWValidationError(
            "Podaj plan albo selektory datasets/years/months/stations, nie oba naraz"
        )
    explicit = plan is None
    if plan is None:
        if datasets is None:
            raise IMGWValidationError(
                "Bez planu wymagany jest parametr datasets",
                details={"option": "datasets", "value": None},
            )
        plan = check_store(
            path,
            datasets=datasets,
            years=years,
            months=months,
            stations=stations,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
    elif not isinstance(plan, StorePlan):
        plan = StorePlan.from_json(plan)
    if Path(plan.root).expanduser().absolute() != path:
        raise IMGWValidationError(f"Plan dotyczy innego magazynu: {plan.root}")

    def cancelled() -> bool:
        return cancel is not None and cancel()

    results: list[OperationResult] = []
    stop = False
    listed = any(item.signal == "listing" for item in plan.items)
    with httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers=_IDENTIFY if listed else None,
    ) as client:
        for index, item in enumerate(plan.items, start=1):
            stop = stop or cancelled()
            if stop:
                results.append(_result(item, "cancelled", error=CANCELLED))
                continue
            results.append(
                _sync_one(
                    client,
                    path,
                    item,
                    explicit=explicit,
                    cancel=cancel,
                    on_notice=on_notice,
                )
            )
            if on_progress is not None:
                on_progress(
                    Progress(
                        index,
                        len(plan.items),
                        "archive",
                        results[-1].status,
                        item.archive.server_path,
                    )
                )
    unchecked = [
        OperationResult(
            None,
            "failed",
            None,
            action.detail,
            error_code=_failure_code(action.detail.partition(": ")[2]),
        )
        for action in plan.actions
        if action.command == _SYNC and action.status == "check_failed"
    ]

    reports: list[SeriesReport] = []
    if series:
        for dataset in dict.fromkeys(item.archive.dataset for item in plan.items):
            outcome = [
                result
                for item, result in zip(plan.items, results, strict=True)
                if item.archive.dataset == dataset
            ]
            blocking = [
                str(result.slot) for result in outcome if result.status not in _DONE
            ]
            if stop or any(result.status == "cancelled" for result in outcome):
                reports.append(SeriesReport("cancelled", None, 0, (), (CANCELLED,)))
            elif blocking:
                reports.append(
                    SeriesReport(
                        "failed",
                        None,
                        0,
                        (),
                        (
                            f"Pominięto budowę szeregu {dataset}: niekompletne wejścia {', '.join(blocking)}",
                        ),
                    )
                )
            else:
                try:
                    reports.append(
                        build_series(
                            path,
                            dataset=dataset,
                            on_progress=on_progress,
                            on_notice=on_notice,
                            cancel=cancel,
                        )
                    )
                except IMGWError as exc:
                    reports.append(SeriesReport("failed", None, 0, (), (str(exc),)))
    was_cancelled = stop or any(result.status == "cancelled" for result in results)
    return SyncReport(
        items=(*results, *unchecked), series=tuple(reports), cancelled=was_cancelled
    )


def _sync_one(
    client: httpx.Client,
    root: Path,
    item: PlanItem,
    *,
    explicit: bool,
    cancel: Cancel | None,
    on_notice: NoticeHook | None,
) -> OperationResult:
    local = root / item.local_path if item.local_path is not None else None
    if item.status == "current":
        return _result(item, "unchanged", version=local)
    if item.status == "check_failed":
        return _result(
            item, "failed", error=item.error, error_code=_failure_code(item.error)
        )
    if item.status == "unverifiable":
        if item.error == CANCELLED:
            return _result(item, "cancelled", error=CANCELLED)
        if item.error == UNPUBLISHED:
            return _result(item, "unchanged", version=local, error=UNPUBLISHED)
        if not explicit:
            if on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "source_unverifiable",
                        f"{item.archive.server_path}: {item.error}; pominięto przy synchronizacji z planu",
                    )
                )
            return _result(item, "unchanged", version=local, error=item.error)
        if on_notice is not None:
            on_notice(
                Notice(
                    "warning",
                    "source_unverifiable",
                    f"{item.archive.server_path}: {item.error}; pobieranie i porównanie sumy SHA-256",
                )
            )
    try:
        signal = _head(client, item.archive)
    except httpx.HTTPError as exc:
        return _result(
            item,
            "failed",
            error=_http_error(exc, source=_source(item.archive)),
            error_code="source_unavailable",
        )
    if _stale(item, signal):
        message = f"{item.archive.server_path}: nagłówki serwera zmieniły się od sprawdzenia planu"
        if on_notice is not None:
            on_notice(Notice("warning", "stale_plan", message))
        return _result(item, "stale_plan", version=local, error=message)
    try:
        response = _download(item.archive, client=client)
        written = write_archive(
            root,
            archive=item.archive,
            response=response,
            on_notice=on_notice,
            cancel=cancel,
        )
    except (IMGWError, OSError) as exc:
        if isinstance(exc, IMGWCancelledError) or (cancel is not None and cancel()):
            return _result(item, "cancelled", error=CANCELLED)
        if on_notice is not None:
            on_notice(
                Notice("error", "archive_failed", f"{item.archive.server_path}: {exc}")
            )
        return _result(
            item,
            "failed",
            error=str(exc),
            error_code=exc.code if isinstance(exc, IMGWError) else "io_error",
        )
    return _result(item, written.status, version=written.path)
