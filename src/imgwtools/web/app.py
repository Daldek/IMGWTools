"""
Web GUI of IMGWTools (HTMX + Jinja2) built on the public library API.

Handlers call only public functions: `datasets` and `archive_files` (archive
download links by dataset key), `run_command` (``stations find`` with paging),
`validate_command` and `fetch_pmaxtp_async` (PMAXTP tables). The station map
reads the catalog route ``GET /api/v1/current/hydro-states`` from the browser.
Every `IMGWError` is rendered as ``partials/error.html`` with its ``code`` and
``detail`` and the HTTP status of the error registry; HTMX swaps those answers
too (``static/js/app.js``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from imgwtools import (
    ERROR_CODES,
    DatasetDescriptor,
    IMGWError,
    archive_files,
    datasets,
    fetch_pmaxtp_async,
    run_command,
    validate_command,
)
from imgwtools._version import __version__
from imgwtools.api.errors import hide_server_paths

if TYPE_CHECKING:
    from imgwtools import StationListEntry
    from imgwtools.store.types import Page

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["version"] = __version__

router = APIRouter()

_KIND_TITLES = {"hydro": "Dane hydrologiczne", "meteo": "Dane meteorologiczne"}
_PMAXTP_METHODS = (
    ("POT", "Peak Over Threshold"),
    ("AMP", "Annual Max Precipitation"),
)
_STATION_PAGE_SIZE = "50"


def _error(request: Request, error: IMGWError) -> HTMLResponse:
    """
    Render an IMGWTools error as the error partial.

    Parameters
    ----------
    request : Request
        Current request.
    error : IMGWError
        Error raised by a public function.

    Returns
    -------
    HTMLResponse
        ``partials/error.html`` with the code, its Polish title and the
        ``detail`` without absolute server paths, with the HTTP status of the
        error registry (500 for codes that REST never reports).
    """
    spec = ERROR_CODES[error.code]
    return templates.TemplateResponse(
        request,
        "partials/error.html",
        {
            "code": error.code,
            "title": spec.title,
            "detail": hide_server_paths(error.detail),
            "option": error.details.get("option"),
        },
        status_code=spec.http_status or 500,
    )


def _archive_datasets() -> tuple[DatasetDescriptor, ...]:
    """The ten archive datasets of the registry (yearly server archives)."""
    return tuple(
        descriptor
        for descriptor in datasets()
        if descriptor.first_year is not None and descriptor.server_dir is not None
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the dashboard."""
    return templates.TemplateResponse(
        request, "index.html", {"title": "IMGWTools - Pobieranie danych IMGW"}
    )


@router.get("/download", response_class=HTMLResponse)
async def download_page(request: Request) -> HTMLResponse:
    """Render the choice of downloadable data."""
    return templates.TemplateResponse(
        request, "download/index.html", {"title": "Pobieranie danych"}
    )


@router.get("/download/archives", response_class=HTMLResponse)
async def download_archives_page(request: Request) -> HTMLResponse:
    """Render the archive download form with the registry's archive datasets."""
    archives = _archive_datasets()
    groups = [
        (title, [item for item in archives if item.kind == kind])
        for kind, title in _KIND_TITLES.items()
    ]
    return templates.TemplateResponse(
        request,
        "download/archives.html",
        {"title": "Dane archiwalne", "groups": groups, "archives": archives},
    )


@router.post("/download/files", response_class=HTMLResponse)
async def download_files(
    request: Request,
    dataset: Annotated[str, Form()] = "",
    years: Annotated[str, Form()] = "",
    months: Annotated[str, Form()] = "",
    params: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """
    Render the download links of the selected archives (HTMX partial).

    Parameters
    ----------
    request : Request
        Current request.
    dataset : str
        Archive dataset key (form field).
    years : str
        Years as text: ``2023``, ``2020-2023`` or ``2019,2021`` (form field).
    months : str
        Optional months 1-12 as comma-separated text (form field).
    params : list of str or None
        Optional semi-annual parameters ``H``, ``Q``, ``T`` (form checkboxes).

    Returns
    -------
    HTMLResponse
        ``partials/download_links.html`` with the files of `archive_files`,
        or the error partial for invalid input.
    """
    try:
        files = archive_files(
            dataset,
            years=years,
            months=months or None,
            params=cast("list[Literal['H', 'Q', 'T']]", params) if params else None,
        )
    except IMGWError as error:
        return _error(request, error)
    return templates.TemplateResponse(
        request, "partials/download_links.html", {"files": files}
    )


@router.get("/download/pmaxtp", response_class=HTMLResponse)
async def download_pmaxtp_page(request: Request) -> HTMLResponse:
    """Render the PMAXTP form."""
    return templates.TemplateResponse(
        request,
        "download/pmaxtp.html",
        {"title": "Opady maksymalne (PMAXTP)", "methods": _PMAXTP_METHODS},
    )


@router.post("/download/pmaxtp/generate", response_class=HTMLResponse)
async def generate_pmaxtp(
    request: Request,
    method: Annotated[str, Form()] = "",
    latitude: Annotated[str, Form()] = "",
    longitude: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """
    Fetch PMAXTP data for a point and render its tables (HTMX partial).

    Parameters
    ----------
    request : Request
        Current request.
    method : str
        ``POT`` or ``AMP`` (form field; empty selects ``POT``).
    latitude : str
        Latitude WGS84 as text (form field).
    longitude : str
        Longitude WGS84 as text (form field).

    Returns
    -------
    HTMLResponse
        ``partials/pmaxtp_result.html``, or the error partial when the input
        is invalid, the point lies outside the PMAXTP grid or IMGW fails.
    """
    given = {"latitude": latitude, "longitude": longitude, "method": method}
    try:
        options = validate_command(
            "pmaxtp fetch",
            options={key: value for key, value in given.items() if value},
        )
        result = await fetch_pmaxtp_async(
            cast(float, options["latitude"]),
            cast(float, options["longitude"]),
            method=cast(Literal["POT", "AMP"], options.get("method", "POT")),
        )
    except IMGWError as error:
        return _error(request, error)
    return templates.TemplateResponse(
        request,
        "partials/pmaxtp_result.html",
        {"result": result, "methods": dict(_PMAXTP_METHODS)},
    )


@router.get("/stations", response_class=HTMLResponse)
async def stations_page(request: Request) -> HTMLResponse:
    """Render the station search page."""
    return templates.TemplateResponse(
        request, "stations/list.html", {"title": "Lista stacji"}
    )


@router.get("/stations/find", response_class=HTMLResponse)
def find_stations_partial(
    request: Request,
    kind: str = "",
    query: str = "",
    limit: str = _STATION_PAGE_SIZE,
    offset: str = "0",
) -> HTMLResponse:
    """
    Search IMGW station lists with ``stations find`` (HTMX partial).

    The command runs through `run_command`, so results, ordering and paging
    equal those of ``imgw stations find`` and ``GET /api/v1/stations/find``.

    Parameters
    ----------
    request : Request
        Current request.
    kind : str
        ``hydro``, ``meteo`` or empty for both station lists.
    query : str
        Station name, river or code prefix; empty lists every station.
    limit : str
        Page size as text.
    offset : str
        Index of the first station as text.

    Returns
    -------
    HTMLResponse
        ``partials/station_table.html`` with the page and links to the
        neighbouring pages, or the error partial.
    """
    given = {"kind": kind, "query": query, "limit": limit, "offset": offset}
    try:
        outcome = run_command(
            "stations find",
            options={key: value for key, value in given.items() if value},
        )
    except IMGWError as error:
        return _error(request, error)
    page = cast("Page[StationListEntry]", outcome.result)
    size = page.limit or len(page.items)

    def _page_url(start: int) -> str:
        values = {"kind": kind, "query": query, "limit": size, "offset": start}
        return "/stations/find?" + urlencode(
            {key: value for key, value in values.items() if value != ""}
        )

    end = page.offset + len(page.items)
    return templates.TemplateResponse(
        request,
        "partials/station_table.html",
        {
            "page": page,
            "kind": kind,
            "first": page.offset + 1 if page.items else 0,
            "last": end,
            "previous_url": _page_url(max(page.offset - size, 0))
            if page.offset > 0
            else None,
            "next_url": _page_url(end) if end < page.total else None,
        },
    )


@router.get("/map", response_class=HTMLResponse)
async def map_page(request: Request) -> HTMLResponse:
    """Render the station map; markers come from ``current hydro-states``."""
    return templates.TemplateResponse(request, "map.html", {"title": "Mapa stacji"})
