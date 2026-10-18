"""Freshness check (listing + HEAD) and plan-driven synchronization of archives."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from urllib.parse import unquote, urlsplit

import httpx

from imgwtools.core.url_builder import IMGW_PUBLIC_DATA_URL
from imgwtools.datasets import (
    ArchiveFile,
    MonthsArg,
    YearsArg,
    archive_files,
    get_dataset,
    parse_months,
    parse_years,
)
from imgwtools.exceptions import (
    ErrorCode,
    IMGWCancelledError,
    IMGWDataError,
    IMGWError,
    IMGWValidationError,
)
from imgwtools.fetch import (
    DEFAULT_TIMEOUT,
    DownloadResult,
    _archive_slot,
    download_hydro_data,
    download_meteo_data,
)
from imgwtools.store.series import (
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
    PlanItem,
    Progress,
    ProgressHook,
    SeriesReport,
    StoreHandle,
    StorePlan,
    SyncReport,
)
from imgwtools.store.writer import write_archive

UNPUBLISHED = "nieopublikowany"
CANCELLED = "anulowano"
NO_SIGNAL = "brak porównywalnego nagłówka ETag/Last-Modified"

_HREF = re.compile(r"""href\s*=\s*["']([^"'#?]+)""", re.IGNORECASE)
_DONE = {"created", "relabeled", "unchanged", "reused"}
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


_HTTP_ERRORS = (
    "Przekroczono czas odpowiedzi serwera IMGW",
    "Błąd HTTP ",
    "Błąd połączenia z IMGW",
)


def _http_error(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return f"{_HTTP_ERRORS[0]}: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{_HTTP_ERRORS[1]}{exc.response.status_code}: {exc.request.url}"
    return f"{_HTTP_ERRORS[2]}: {exc}"


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


def _select(
    datasets: Iterable[str], years: YearsArg, months: MonthsArg | None
) -> list[ArchiveFile]:
    if isinstance(datasets, str):
        raise IMGWValidationError(
            "Parametr datasets musi być listą kluczy zbiorów",
            details={"option": "datasets", "value": datasets},
        )
    selected_years = parse_years(years, option="years")
    selected_months = (
        parse_months(months, option="months") if months is not None else None
    )
    result: dict[str, ArchiveFile] = {}
    keys = list(dict.fromkeys(datasets))
    if not keys:
        raise IMGWValidationError(
            "Wybierz co najmniej jeden zbiór", details={"option": "datasets"}
        )
    for dataset in keys:
        _series_descriptor(dataset)
        for archive in archive_files(
            dataset, years=selected_years, months=selected_months
        ):
            result.setdefault(archive.server_path, archive)
    return list(result.values())


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
    years: YearsArg,
    months: MonthsArg | None = None,
    plan: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan a synchronization without downloading anything.

    Enumerates the archives of the selected datasets offline, then checks each one
    against IMGW using only the parent directory listing and an HTTP ``HEAD``
    request; no archive is fetched and nothing is written to the store, not even
    staging files. A file is published when its name appears in the listing of its
    parent directory. Per-archive errors are recorded in the plan, never raised.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    datasets : Iterable[str]
        Dataset keys, slugs or legacy aliases of measurement series datasets. A
        bare string is rejected.
    years : YearsArg
        Years to check (hydrological or calendar, as defined by each dataset):
        ``2024``, ``"2020-2023"``, ``"2020,2022"`` or a collection of such items.
    months : MonthsArg or None, optional
        Months (1-12, same forms as ``years``) filtering physically monthly files
        only; yearly archives are returned once regardless of this filter.
    plan : str, os.PathLike or None, optional
        File to save the plan to (``imgw-plan/1``, see `StorePlan.to_json`); it
        must lie outside the store in an existing directory.
    on_progress : ProgressHook or None, optional
        Called after each archive with its plan status.
    on_notice : NoticeHook or None, optional
        Receives a ``source_unverifiable`` warning for every ``unverifiable`` item
        and an ``archive_failed`` error for every ``check_failed`` item.
    cancel : Cancel or None, optional
        Polled before each archive; once it returns ``True`` the remaining archives
        are listed as ``unverifiable`` with error ``"anulowano"``.

    Returns
    -------
    StorePlan
        ``imgw-plan/1`` plan with one item per archive: ``current`` (local version
        matches every header present on both sides), ``newer`` (different ETag or
        Last-Modified), ``missing`` (published but not stored), ``unverifiable``
        (no comparable signal, or ``"nieopublikowany"`` when the file is not
        published) or ``check_failed`` (listing/HEAD error or unreadable local
        version). ``series_state`` holds the local state of each dataset's series
        keyed by slug, with ``current`` turned into ``outdated`` when the plan has
        ``newer``/``missing`` items for that dataset.

    Raises
    ------
    IMGWStoreError
        If ``root`` is not a supported IMGW store or a store path contains a
        symbolic link.
    IMGWValidationError
        If ``datasets`` is a string or empty, a dataset is unknown or does not
        produce measurement series, the years/months are invalid, or ``plan``
        lies inside the store or in a missing directory.
    """
    path = _root(root)
    archives = _select(datasets, years, months)
    target = _plan_target(path, plan) if plan is not None else None
    listings: dict[str, set[str] | Exception | None] = {}
    items: list[PlanItem] = []
    cancelled = False
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        for index, archive in enumerate(archives, start=1):
            if not cancelled and cancel is not None and cancel():
                cancelled = True
            if cancelled:
                items.append(_item(archive, "unverifiable", error=CANCELLED))
                continue
            items.append(_check_one(client, path, archive, listings))
            item = items[-1]
            if item.status == "unverifiable" and on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "source_unverifiable",
                        f"{archive.server_path}: {item.error}",
                    )
                )
            elif item.status == "check_failed" and on_notice is not None:
                on_notice(
                    Notice(
                        "error",
                        "archive_failed",
                        f"{archive.server_path}: {item.error}",
                    )
                )
            if on_progress is not None:
                on_progress(
                    Progress(
                        index,
                        len(archives),
                        "archive",
                        item.status,
                        archive.server_path,
                    )
                )
    series_state = {}
    for dataset in dict.fromkeys(archive.dataset for archive in archives):
        descriptor = get_dataset(dataset)
        inputs, problems = _scan_inputs(path, descriptor)
        state = _series_state(path, descriptor, inputs, reliable=not problems)
        pending = any(
            item.archive.dataset == dataset and item.status in ("newer", "missing")
            for item in items
        )
        series_state[descriptor.slug] = (
            "outdated" if state == "current" and pending else state
        )
    result = StorePlan(
        schema="imgw-plan/1",
        root=path,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state=series_state,
        cancelled=cancelled,
    )
    if target is not None:
        result.to_json(target)
    return result


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


def _download(archive: ArchiveFile) -> DownloadResult:
    slug = get_dataset(archive.dataset).slug
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


def _check_failed_code(item: PlanItem) -> ErrorCode:
    """Error code of a ``check_failed`` plan item: IMGW server or local version."""
    return (
        "source_unavailable"
        if item.error is not None and item.error.startswith(_HTTP_ERRORS)
        else "data_error"
    )


def sync_store(
    root: PathArg | StoreHandle,
    /,
    *,
    datasets: Iterable[str] | None = None,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
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
    download an HTTP ``HEAD`` re-validates the item: when the ETag or Last-Modified
    differs from the plan the item ends as ``stale_plan`` and is not downloaded.
    ``check_failed`` items are never downloaded. An ``unverifiable`` item is
    downloaded (then deduplicated by SHA-256) only in a sync without a supplied
    plan; from a supplied plan it stays ``unchanged`` with a
    ``source_unverifiable`` warning. Failures of single archives are reported per
    slot, not raised.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root of an existing IMGW store.
    datasets : Iterable[str] or None, optional
        Dataset keys, slugs or legacy aliases; required, together with
        ``years``, when ``plan`` is not given.
    years : YearsArg or None, optional
        Years to synchronize (``2024``, ``"2020-2023"``, ``"2020,2022"`` or a
        collection of such items); required when ``plan`` is not given.
    months : MonthsArg or None, optional
        Months (1-12) filtering physically monthly files.
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
        ``archive_failed``) and notices of the writer and the series builder.
    cancel : Cancel or None, optional
        Polled before each archive; once it returns ``True`` the remaining items
        and series end as ``cancelled``.

    Returns
    -------
    SyncReport
        One :class:`OperationResult` per plan item (``created``, ``relabeled``,
        ``unchanged``, ``reused``, ``failed``, ``stale_plan`` or ``cancelled``),
        one :class:`SeriesReport` per dataset when ``series`` is true (``failed``
        or ``cancelled`` without building when the dataset has incomplete
        inputs) and the overall cancellation flag.

    Raises
    ------
    IMGWValidationError
        If both ``plan`` and selectors are given, ``datasets`` or ``years`` is
        missing without a plan, the plan refers to another store, or the
        selectors are invalid.
    IMGWDataError
        If the plan file cannot be read.
    IMGWStoreError
        If ``root`` is not a supported IMGW store.
    """
    path = _root(root)
    if plan is not None and (
        datasets is not None or years is not None or months is not None
    ):
        raise IMGWValidationError(
            "Podaj plan albo selektory datasets/years/months, nie oba naraz"
        )
    explicit = plan is None
    if plan is None:
        if datasets is None or years is None:
            raise IMGWValidationError(
                "Bez planu wymagane są parametry datasets i years"
            )
        plan = check_store(
            path,
            datasets=datasets,
            years=years,
            months=months,
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
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
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
        items=tuple(results), series=tuple(reports), cancelled=was_cancelled
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
            item, "failed", error=item.error, error_code=_check_failed_code(item)
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
            error=_http_error(exc),
            error_code="source_unavailable",
        )
    if signal is None or (signal.etag, signal.last_modified) != (
        item.remote_etag,
        item.remote_last_modified,
    ):
        message = f"{item.archive.server_path}: nagłówki serwera zmieniły się od sprawdzenia planu"
        if on_notice is not None:
            on_notice(Notice("warning", "stale_plan", message))
        return _result(item, "stale_plan", version=local, error=message)
    try:
        response = _download(item.archive)
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
