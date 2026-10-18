"""Versioned store REST routes behind explicit server configuration.

Every route works only on the server-side absolute ``IMGW_STORE_ROOT``; the
client never supplies a root or an absolute path. Writing routes additionally
require ``IMGW_STORE_WRITES_ENABLED=true``, a non-empty
``IMGW_STORE_WRITE_TOKEN`` and a matching ``X-API-Key`` header. Operations are
dispatched through :func:`imgwtools.commands.run_command`, i.e. the same public
functions and option validation as the CLI. Errors are returned as
``{"code": ..., "detail": ...}`` (see :class:`StoreAPIError`).
"""

from __future__ import annotations

import hmac
import json
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from starlette.background import BackgroundTask

from imgwtools.api.schemas import (
    CatalogReportResponse,
    CatalogRequest,
    MeasurementResponse,
    OperationResultResponse,
    PMaXTPStoreResponse,
    PMaXTPStoreSyncRequest,
    SeriesBuildRequest,
    SeriesExportRequest,
    SeriesIndexResponse,
    SeriesRecordResponse,
    SeriesReportResponse,
    StationCoverageResponse,
    StationSeriesIndexResponse,
    StoreEntryResponse,
    StoreErrorResponse,
    StoreInfoResponse,
    StoreLicenseResponse,
    StoreMetaResponse,
    StoreSelectionRequest,
    StoreStalePlanResponse,
    StoreSyncRequest,
    SyncReportResponse,
)
from imgwtools.commands import run_command
from imgwtools.config import settings
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWError,
    IMGWPlanStaleError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.models import NormalizedRecord
from imgwtools.store import read_series, read_series_index, store_info
from imgwtools.store.types import (
    CatalogReport,
    PMaXTPStoreResult,
    SeriesReport,
    StoreEntry,
    StoreInfo,
    StorePlan,
    SyncReport,
)

router = APIRouter()
series_router = APIRouter()
pmaxtp_router = APIRouter()

_SERIES_PREFIX = ("series", "versions")
_API_KEY = APIKeyHeader(
    name="X-API-Key",
    scheme_name="StoreWriteToken",
    description="Token zapisu magazynu (IMGW_STORE_WRITE_TOKEN serwera)",
    auto_error=False,
)

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": StoreErrorResponse, "description": "Niepoprawne parametry"},
    404: {"model": StoreErrorResponse, "description": "Brak wersji lub pliku"},
    503: {
        "model": StoreErrorResponse,
        "description": "Magazyn nieskonfigurowany/nieobsługiwany albo brak pyarrow",
    },
}
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    403: {
        "model": StoreErrorResponse,
        "description": "Zapis wyłączony albo brak/niepoprawny nagłówek X-API-Key",
    },
    409: {"model": StoreErrorResponse, "description": "Kolizja wersji w magazynie"},
    502: {"model": StoreErrorResponse, "description": "Błąd serwera źródłowego IMGW"},
}


class StoreAPIError(Exception):
    """
    Error of a store route, rendered as ``{"code": ..., "detail": ...}``.

    Parameters
    ----------
    status_code : int
        HTTP status of the response.
    code : str
        Machine-readable error code.
    detail : str
        Polish description for the user.
    extra : dict of str to object or None, optional
        Additional top-level fields of the response body.

    Attributes
    ----------
    status_code : int
        HTTP status of the response.
    code : str
        Machine-readable error code.
    detail : str
        Polish description for the user.
    extra : dict of str to object
        Additional top-level fields of the response body.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra or {}


async def store_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Render a `StoreAPIError` as its JSON response.

    Parameters
    ----------
    request : Request
        Request that failed (unused).
    exc : Exception
        The raised `StoreAPIError`.

    Returns
    -------
    JSONResponse
        ``{"code": ..., "detail": ...}`` plus extra fields, with the error status.
    """
    assert isinstance(exc, StoreAPIError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": _hide_paths(exc.detail), **exc.extra},
    )


def _status(exc: IMGWError) -> tuple[int, str]:
    """HTTP status and code of a library error raised after the root was validated."""
    if isinstance(exc, IMGWStoreDependencyError):
        return 503, "missing_dependency"
    if isinstance(exc, IMGWStoreConflictError):
        return 409, "conflict"
    if isinstance(exc, IMGWPlanStaleError):
        return 409, "stale_plan"
    if isinstance(exc, IMGWStoreError):
        return 404, "not_found"
    if isinstance(exc, IMGWValidationError):
        return 400, "validation_error"
    if isinstance(exc, IMGWConnectionError):
        return 502, "source_unavailable"
    if isinstance(exc, IMGWDataError):
        return 500, "data_error"
    return 500, "store_error"


@contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except IMGWError as exc:
        status, code = _status(exc)
        raise StoreAPIError(status, code, str(exc)) from exc


def _run[T](command: str, expected: type[T], /, **options: object) -> T:
    """Run a catalog command through the shared dispatcher (parity with the CLI)."""
    with _translate():
        result = run_command(command, options=options)
    if not isinstance(result, expected):
        raise TypeError(f"{command} zwróciło {type(result).__name__}")
    return result


# --------------------------------------------------------------------------
# Configuration guards
# --------------------------------------------------------------------------


def _unavailable(code: str, detail: str) -> StoreAPIError:
    return StoreAPIError(503, code, detail)


def _inspect_root() -> StoreInfo:
    """Offline state of the configured root; 503 when it is missing or invalid."""
    root = settings.store_root
    if root is None or not str(root).strip():
        raise _unavailable(
            "store_not_configured",
            "Magazyn nie jest skonfigurowany: ustaw IMGW_STORE_ROOT na absolutną "
            "ścieżkę magazynu na serwerze",
        )
    if not root.is_absolute():
        raise _unavailable(
            "store_root_invalid", "IMGW_STORE_ROOT musi być ścieżką absolutną"
        )
    try:
        return store_info(root)
    except IMGWError as exc:
        raise _unavailable("store_root_invalid", f"Niepoprawny IMGW_STORE_ROOT: {exc}")


def _store_root(info: StoreInfo = Depends(_inspect_root)) -> Path:
    """Root of a supported store; 503 otherwise."""
    if not info.supported:
        raise _unavailable(
            "store_unavailable",
            "Magazyn pod IMGW_STORE_ROOT jest niedostępny: " + "; ".join(info.problems),
        )
    return info.root


def _forbidden(code: str, detail: str) -> StoreAPIError:
    return StoreAPIError(403, code, detail)


def _authorize_write(api_key: str | None = Security(_API_KEY)) -> None:
    """Writes need the enabled flag, a configured token and a matching header."""
    if not settings.store_writes_enabled:
        raise _forbidden(
            "writes_disabled",
            "Zapis do magazynu przez REST jest wyłączony (IMGW_STORE_WRITES_ENABLED)",
        )
    token = settings.store_write_token
    secret = token.get_secret_value() if token is not None else ""
    if not secret:
        raise _forbidden(
            "write_token_missing",
            "Zapis do magazynu wymaga skonfigurowanego IMGW_STORE_WRITE_TOKEN",
        )
    if api_key is None or not hmac.compare_digest(
        api_key.encode("utf-8"), secret.encode("utf-8")
    ):
        raise _forbidden("invalid_api_key", "Brak lub niepoprawny nagłówek X-API-Key")


# --------------------------------------------------------------------------
# Path confinement
# --------------------------------------------------------------------------


def _invalid(detail: str) -> StoreAPIError:
    return StoreAPIError(400, "validation_error", detail)


def _inside(path: Path, parent: Path) -> bool:
    resolved, base = path.resolve(), parent.resolve()
    return resolved == base or base in resolved.parents


def _version_path(root: Path, version: str) -> Path:
    """Series version given relative to the root, confined under ``series/versions/``."""
    parts = version.split("/")
    if (
        "\\" in version
        or "\0" in version
        or PurePosixPath(version).is_absolute()
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise _invalid(
            f"Wersja musi być ścieżką względną do magazynu bez '..': {version!r}"
        )
    if len(parts) < 3 or tuple(parts[:2]) != _SERIES_PREFIX:
        raise _invalid(
            f"Wersja szeregu musi leżeć pod series/versions/ magazynu: {version!r}"
        )
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise _invalid(f"Wersja nie może prowadzić przez dowiązanie: {version!r}")
    if not path.exists():
        raise StoreAPIError(404, "not_found", f"Brak wersji w magazynie: {version}")
    if not _inside(path, root):
        raise _invalid(f"Wersja wychodzi poza magazyn: {version!r}")
    return path


def _user_locations(name: str) -> Path:
    """Basename of a CSV placed beforehand in ``IMGW_USER_LOCATIONS_DIR``."""
    directory = settings.user_locations_dir
    if directory is None:
        raise _invalid(
            "Serwer nie udostępnia plików współrzędnych (brak IMGW_USER_LOCATIONS_DIR)"
        )
    if not directory.is_absolute():
        raise _unavailable(
            "user_locations_invalid", "IMGW_USER_LOCATIONS_DIR musi być absolutny"
        )
    if (
        name in ("", ".", "..")
        or "/" in name
        or "\\" in name
        or "\0" in name
        or PurePosixPath(name).name != name
    ):
        raise _invalid(f"Podaj samą nazwę pliku współrzędnych: {name!r}")
    path = directory / name
    if path.is_symlink():
        raise _invalid(f"Plik współrzędnych nie może być dowiązaniem: {name!r}")
    if not path.is_file():
        raise StoreAPIError(404, "not_found", f"Brak pliku współrzędnych: {name}")
    return path


def _temporary(root: Path) -> Path:
    """New private temporary directory; refused when TMPDIR lies in the store."""
    if _inside(Path(tempfile.gettempdir()), root):
        raise StoreAPIError(
            500,
            "temp_inside_store",
            "Katalog tymczasowy serwera leży w magazynie; zmień TMPDIR",
        )
    return Path(tempfile.mkdtemp(prefix="imgw-rest-"))


@contextmanager
def _scratch(root: Path) -> Iterator[Path]:
    """Private temporary directory outside the store, removed on exit."""
    directory = _temporary(root)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------------
# Serialization (paths relative to the root)
# --------------------------------------------------------------------------


def _relative(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _hide_paths(text: str) -> str:
    """
    Rewrite configured server directories in free text as paths relative to them.

    Library messages name files by absolute path; REST responses expose only
    paths relative to ``IMGW_STORE_ROOT``, ``IMGW_USER_LOCATIONS_DIR`` and
    ``IMGW_DATA_DIR`` (a relative directory is matched in its resolved,
    absolute form). The longest directory is replaced first, so a directory
    nested in another one is not left half-rewritten.

    Parameters
    ----------
    text : str
        Error or problem text.

    Returns
    -------
    str
        ``text`` with ``<dir>/x`` replaced by ``x`` and a bare ``<dir>`` by ``.``.
    """
    prefixes: set[str] = set()
    for directory in (
        settings.store_root,
        settings.user_locations_dir,
        settings.data_dir,
    ):
        if directory is None:
            continue
        if directory.is_absolute():
            prefixes.add(str(directory))
        prefixes.add(str(directory.resolve()))
    prefixes.discard("/")
    for prefix in sorted(prefixes, key=len, reverse=True):
        text = re.sub(
            re.escape(prefix) + r"(?:/|(?![^\s'\"),:;]))",
            lambda match: "" if match.group().endswith("/") else ".",
            text,
        )
    return text


def _entry(root: Path, entry: StoreEntry) -> StoreEntryResponse:
    meta = entry.meta
    return StoreEntryResponse(
        kind=entry.kind,
        slot=entry.slot,
        version=_relative(root, entry.version),
        meta=None
        if meta is None
        else StoreMetaResponse(
            schema=meta.schema,
            dataset=meta.dataset,
            sha256=meta.sha256,
            size_bytes=meta.size_bytes,
            downloaded_at=meta.downloaded_at,
            license=StoreLicenseResponse(
                id=meta.license.id,
                attribution=meta.license.attribution,
                url=meta.license.url,
            ),
            request=dict(meta.request),
            extra=dict(meta.extra),
        ),
        problem_code=entry.problem_code,
        problem=None if entry.problem is None else _hide_paths(entry.problem),
    )


def _series_report(root: Path, report: SeriesReport) -> SeriesReportResponse:
    return SeriesReportResponse(
        status=report.status,
        version=_relative(root, report.version),
        stations=report.stations,
        source_files=[_relative(root, path) or "" for path in report.source_files],
        problems=[_hide_paths(problem) for problem in report.problems],
    )


def _sync_report(root: Path, report: SyncReport) -> SyncReportResponse:
    return SyncReportResponse(
        items=[
            OperationResultResponse(
                slot=item.slot,
                status=item.status,
                version=_relative(root, item.version),
                error=None if item.error is None else _hide_paths(item.error),
            )
            for item in report.items
        ],
        series=[_series_report(root, series) for series in report.series],
        cancelled=report.cancelled,
    )


def _plan_document(plan: StorePlan, root: Path) -> dict[str, Any]:
    """``imgw-plan/1`` document of `StorePlan.to_json` with the root hidden as ``.``."""
    with _scratch(root) as scratch:
        document = json.loads(plan.to_json(scratch / "plan.json").read_text("utf-8"))
    document["root"] = "."
    return document


def _plan_file(document: dict[str, Any], root: Path, scratch: Path) -> Path:
    """Write a client plan for this root into ``scratch``; 400 when it is unusable."""
    if document.get("root") not in (".", str(root)):
        raise _invalid("Plan dotyczy innego magazynu niż IMGW_STORE_ROOT")
    path = scratch / "plan.json"
    path.write_text(
        json.dumps({**document, "root": str(root)}, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        StorePlan.from_json(path)
    except IMGWDataError as exc:
        raise StoreAPIError(400, "invalid_plan", str(exc)) from exc
    return path


def _record(record: NormalizedRecord) -> SeriesRecordResponse:
    return SeriesRecordResponse(
        station_code=record.station_code,
        dataset=record.dataset,
        date=record.date,
        hydro_year=record.hydro_year,
        period=record.period,
        measurements={
            name: MeasurementResponse(value=item.value, flag=item.flag)
            for name, item in record.measurements.items()
        },
        attributes=dict(record.attributes),
        extrema_dates=dict(record.extrema_dates),
        extrema_occurrences=dict(record.extrema_occurrences),
    )


# --------------------------------------------------------------------------
# /api/v1/store
# --------------------------------------------------------------------------


@router.get(
    "/info",
    response_model=StoreInfoResponse,
    responses={503: _ERRORS[503]},
    summary="Stan magazynu",
    description="Pola StoreInfo magazynu IMGW_STORE_ROOT (offline, bez zapisu); "
    "nieobsługiwany magazyn zwraca supported=false z listą problemów.",
)
def get_store_info(info: StoreInfo = Depends(_inspect_root)) -> StoreInfoResponse:
    """
    Describe the configured store root offline.

    Parameters
    ----------
    info : StoreInfo
        State of ``IMGW_STORE_ROOT`` from `store_info`.

    Returns
    -------
    StoreInfoResponse
        Fields of `StoreInfo` with the root shown as ``"."``.
    """
    return StoreInfoResponse(
        root=".",
        exists=info.exists,
        schema=info.schema,
        supported=info.supported,
        contracts=dict(info.contracts),
        problems=[_hide_paths(problem) for problem in info.problems],
    )


@router.get(
    "/entries",
    response_model=list[StoreEntryResponse],
    responses={503: _ERRORS[503]},
    summary="Wersje i problemy magazynu",
    description="Lista StoreEntry ze skanu offline (store scan), także problemów.",
)
def list_store_entries(
    kind: str | None = Query(
        default=None,
        description="Rodzaj wpisów: archive, series, catalog, pmaxtp albo problem",
    ),
    info: StoreInfo = Depends(_inspect_root),
) -> list[StoreEntryResponse]:
    """
    Scan the configured store offline.

    Parameters
    ----------
    kind : str or None
        Return only entries of this kind; ``None`` returns all.
    info : StoreInfo
        State of ``IMGW_STORE_ROOT``.

    Returns
    -------
    list of StoreEntryResponse
        Published versions and detected problems.
    """
    entries = _run("store scan", tuple, root=info.root, kind=kind)
    return [_entry(info.root, entry) for entry in entries]


@router.post(
    "/check",
    response_model=dict[str, Any],
    responses={**_ERRORS, 502: _WRITE_ERRORS[502]},
    summary="Sprawdzenie aktualności archiwów",
    description="Plan imgw-plan/1 (listing i HEAD serwera IMGW, bez pobierania i bez "
    "zapisu do magazynu); dostępne także przy wyłączonych zapisach. Zwrócony "
    "dokument można przekazać jako plan do POST /store/sync.",
)
def check_store_route(
    request: StoreSelectionRequest, root: Path = Depends(_store_root)
) -> dict[str, Any]:
    """
    Plan the freshness of the selected archives without writing to the store.

    Parameters
    ----------
    request : StoreSelectionRequest
        Datasets, years and optional months.
    root : Path
        Supported store root.

    Returns
    -------
    dict of str to object
        ``imgw-plan/1`` document with ``root`` set to ``"."``.
    """
    plan = _run(
        "store check",
        StorePlan,
        root=root,
        dataset=request.datasets,
        years=request.years,
        months=request.months,
    )
    return _plan_document(plan, root)


@router.post(
    "/sync",
    response_model=SyncReportResponse,
    responses={
        **_WRITE_ERRORS,
        409: {
            "model": StoreStalePlanResponse,
            "description": "Plan nieaktualny (stale_plan) lub kolizja wersji",
        },
    },
    dependencies=[Depends(_authorize_write)],
    summary="Synchronizacja archiwów (zapis)",
    description="Pobiera nowe lub brakujące archiwa według selektorów albo planu z "
    "POST /store/check i zwraca pełny raport po zakończeniu. Pozycje stale_plan "
    "dają 409 z raportem.",
)
def sync_store_route(
    request: StoreSyncRequest, root: Path = Depends(_store_root)
) -> SyncReportResponse:
    """
    Synchronize archives of the configured store.

    Parameters
    ----------
    request : StoreSyncRequest
        Selectors or an ``imgw-plan/1`` document, and the series flag.
    root : Path
        Supported store root.

    Returns
    -------
    SyncReportResponse
        Full synchronization report.

    Raises
    ------
    StoreAPIError
        409 ``stale_plan`` with the report when plan items changed on the server.
    """
    options: dict[str, object] = {
        "root": root,
        "dataset": request.datasets,
        "years": request.years,
        "months": request.months,
        "no_series": not request.series,
    }
    if request.plan is None:
        report = _run("store sync", SyncReport, **options)
    else:
        with _scratch(root) as scratch:
            plan = _plan_file(request.plan, root, scratch)
            report = _run("store sync", SyncReport, **options, plan=plan)
    body = _sync_report(root, report)
    stale = sum(item.status == "stale_plan" for item in report.items)
    if stale:
        raise StoreAPIError(
            409,
            "stale_plan",
            f"Plan jest nieaktualny dla {stale} archiwów; wykonaj ponownie "
            "POST /store/check",
            extra={"report": body.model_dump(mode="json")},
        )
    return body


@router.post(
    "/catalog",
    response_model=CatalogReportResponse,
    responses=_WRITE_ERRORS,
    dependencies=[Depends(_authorize_write)],
    summary="Budowa katalogu stacji (zapis)",
    description="Buduje wersjonowany stations.geojson; opcjonalny plik współrzędnych "
    "to wyłącznie nazwa pliku z katalogu IMGW_USER_LOCATIONS_DIR serwera.",
)
def build_catalog_route(
    request: CatalogRequest, root: Path = Depends(_store_root)
) -> CatalogReportResponse:
    """
    Build the station catalog of the configured store.

    Parameters
    ----------
    request : CatalogRequest
        Optional basename of a server-side user locations CSV.
    root : Path
        Supported store root.

    Returns
    -------
    CatalogReportResponse
        Catalog build result.
    """
    locations = (
        _user_locations(request.user_locations)
        if request.user_locations is not None
        else None
    )
    report = _run("store catalog", CatalogReport, root=root, user_locations=locations)
    return CatalogReportResponse(
        status=report.status,
        version=_relative(root, report.version),
        station_count=report.station_count,
        without_location=report.without_location,
        problems=[_hide_paths(problem) for problem in report.problems],
    )


# --------------------------------------------------------------------------
# /api/v1/series
# --------------------------------------------------------------------------


@series_router.post(
    "/build",
    response_model=SeriesReportResponse,
    responses=_WRITE_ERRORS,
    dependencies=[Depends(_authorize_write)],
    summary="Budowa szeregu Parquet (zapis)",
    description="Buduje szereg zbioru z bieżących wersji archiwów magazynu.",
)
def build_series_route(
    request: SeriesBuildRequest, root: Path = Depends(_store_root)
) -> SeriesReportResponse:
    """
    Build the series of one dataset in the configured store.

    Parameters
    ----------
    request : SeriesBuildRequest
        Dataset key.
    root : Path
        Supported store root.

    Returns
    -------
    SeriesReportResponse
        Series build result.
    """
    report = _run("series build", SeriesReport, root=root, dataset=request.dataset)
    return _series_report(root, report)


@series_router.get(
    "/index",
    response_model=SeriesIndexResponse,
    responses=_ERRORS,
    summary="Spis wersji szeregu",
    description="SeriesIndex wersji series/versions/… (bez pyarrow).",
)
def get_series_index(
    version: str = Query(
        ...,
        description="Wersja względna do magazynu: series/versions/<zbiór>/<etykieta>",
    ),
    root: Path = Depends(_store_root),
) -> SeriesIndexResponse:
    """
    Read the ``series.json`` index of a series version.

    Parameters
    ----------
    version : str
        Version path relative to the store root, under ``series/versions/``.
    root : Path
        Supported store root.

    Returns
    -------
    SeriesIndexResponse
        Dataset, year type, periods and per-station index.
    """
    path = _version_path(root, version)
    with _translate():
        index = read_series_index(path)
    return SeriesIndexResponse(
        schema=index.schema,
        dataset=index.dataset,
        year_type=index.year_type,
        periods=list(index.periods),
        stations={
            code: StationSeriesIndexResponse(
                file=entry.file.as_posix(),
                sha256=entry.sha256,
                rows=entry.rows,
                variables={
                    key: StationCoverageResponse(
                        variable=coverage.variable,
                        unit=coverage.unit,
                        period=coverage.period,
                        first=coverage.first,
                        last=coverage.last,
                        with_value=coverage.with_value,
                        accumulated=coverage.accumulated,
                        gaps=list(coverage.gaps),
                    )
                    for key, coverage in entry.variables.items()
                },
            )
            for code, entry in index.stations.items()
        },
    )


@series_router.post(
    "/export",
    response_class=FileResponse,
    responses={
        **_WRITE_ERRORS,
        200: {
            "content": {"text/csv": {}},
            "description": "CSV stacji z atrybucją IMGW-PIB (załącznik)",
        },
    },
    dependencies=[Depends(_authorize_write)],
    summary="Eksport szeregu stacji do CSV",
    description="Zwraca CSV jako załącznik z pliku tymczasowego poza magazynem, "
    "usuwanego po odpowiedzi; ścieżki wyjścia od klienta nie są przyjmowane.",
)
def export_series_route(
    request: SeriesExportRequest, root: Path = Depends(_store_root)
) -> FileResponse:
    """
    Export one station of a series version as a CSV attachment.

    Parameters
    ----------
    request : SeriesExportRequest
        Version relative to the root, station, variables and year type.
    root : Path
        Supported store root.

    Returns
    -------
    FileResponse
        ``text/csv; charset=utf-8`` attachment; its temporary directory is
        removed after the response is sent.
    """
    version = _version_path(root, request.version)
    directory = _temporary(root)
    try:
        target = _run(
            "series export",
            Path,
            version=version,
            station=request.station,
            path=directory / f"{request.station}.csv",
            variables=request.variables,
            year_type=request.year_type,
        )
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return FileResponse(
        target,
        media_type="text/csv; charset=utf-8",
        filename=target.name,
        background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
    )


@series_router.get(
    "/{station}",
    response_model=list[SeriesRecordResponse],
    responses=_ERRORS,
    summary="Wartości i flagi stacji",
    description="Rekordy stacji z wersji szeregu w zakresie start–end (włącznie, "
    "data początku okresu); wymaga pyarrow.",
)
def get_series_records(
    station: str = PathParam(..., description="Kod stacji (9 cyfr)"),
    version: str = Query(
        ...,
        description="Wersja względna do magazynu: series/versions/<zbiór>/<etykieta>",
    ),
    variables: str = Query(..., description="Zmienne rozdzielone przecinkami, np. Q,H"),
    start: date | None = Query(default=None, description="Pierwsza data (ISO)"),
    end: date | None = Query(default=None, description="Ostatnia data (ISO)"),
    root: Path = Depends(_store_root),
) -> list[SeriesRecordResponse]:
    """
    Read values and flags of one station from a series version.

    Parameters
    ----------
    station : str
        Nine-digit station code.
    version : str
        Version path relative to the store root, under ``series/versions/``.
    variables : str
        Comma-separated variable names.
    start : datetime.date or None
        First period start date to include.
    end : datetime.date or None
        Last period start date to include.
    root : Path
        Supported store root.

    Returns
    -------
    list of SeriesRecordResponse
        Station records in file order.
    """
    path = _version_path(root, version)
    names = [name.strip() for name in variables.split(",") if name.strip()]
    if not names:
        raise _invalid("Podaj co najmniej jedną zmienną w parametrze variables")
    with _translate():
        return [
            _record(record)
            for record in read_series(
                path, station=station, variables=names, start=start, end=end
            )
        ]


# --------------------------------------------------------------------------
# /api/v1/pmaxtp/store
# --------------------------------------------------------------------------


@pmaxtp_router.post(
    "/sync",
    response_model=PMaXTPStoreResponse,
    responses=_WRITE_ERRORS,
    dependencies=[Depends(_authorize_write)],
    summary="Zapis komórki PMAXTP w magazynie (zapis)",
    description="Pobiera komórkę PMAXTP dla punktu i zapisuje ją jako wersję "
    "magazynu (nie mylić z /api/v1/pmaxtp/data na żywo).",
)
def sync_pmaxtp_route(
    request: PMaXTPStoreSyncRequest, root: Path = Depends(_store_root)
) -> PMaXTPStoreResponse:
    """
    Store the PMAXTP cell of a point in the configured store.

    Parameters
    ----------
    request : PMaXTPStoreSyncRequest
        Method, point and optional expected cell indices.
    root : Path
        Supported store root.

    Returns
    -------
    PMaXTPStoreResponse
        Status, version and stored PMAXTP data.
    """
    result = _run(
        "pmaxtp sync",
        PMaXTPStoreResult,
        root=root,
        method=request.method.value,
        lat=request.latitude,
        lon=request.longitude,
        ind_x=request.ind_x,
        ind_y=request.ind_y,
    )
    return PMaXTPStoreResponse(
        status=result.status,
        version=_relative(root, result.version),
        ind_x=result.ind_x,
        ind_y=result.ind_y,
        result=result.result,
    )
