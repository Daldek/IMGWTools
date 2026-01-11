"""
Web GUI application using HTMX + Jinja2.

This module provides a web interface for generating download URLs
and browsing IMGW data.
"""

from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from imgwtools.core.url_builder import (
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    PMaXTPMethod,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    build_api_url,
)

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Router for web GUI
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page - dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "IMGWTools - Pobieranie danych IMGW",
        },
    )


@router.get("/download", response_class=HTMLResponse)
async def download_page(request: Request):
    """Download page with forms."""
    return templates.TemplateResponse(
        "download/index.html",
        {
            "request": request,
            "title": "Pobieranie danych",
        },
    )


@router.get("/download/hydro", response_class=HTMLResponse)
async def download_hydro_page(request: Request):
    """Hydrological data download form."""
    return templates.TemplateResponse(
        "download/hydro.html",
        {
            "request": request,
            "title": "Dane hydrologiczne",
            "intervals": [
                ("dobowe", "Dobowe"),
                ("miesieczne", "Miesięczne"),
                ("polroczne_i_roczne", "Półroczne i roczne"),
            ],
            "params": [
                ("Q", "Przepływ (Q)"),
                ("H", "Stan wody (H)"),
                ("T", "Temperatura (T)"),
            ],
        },
    )


@router.post("/download/hydro/generate", response_class=HTMLResponse)
async def generate_hydro_urls(
    request: Request,
    interval: str = Form(...),
    start_year: int = Form(...),
    end_year: int = Form(...),
    param: Optional[str] = Form(None),
):
    """Generate hydro download URLs (HTMX partial)."""
    urls = []
    errors = []

    try:
        hydro_interval = HydroInterval(interval)
        hydro_param = HydroParam(param) if param else None

        for year in range(start_year, end_year + 1):
            try:
                if hydro_interval == HydroInterval.DAILY:
                    if year >= 2023:
                        # From 2023: single file per year
                        result = build_hydro_url(hydro_interval, year)
                        urls.append({
                            "url": result.url,
                            "filename": result.filename,
                            "year": year,
                        })
                    else:
                        # Before 2023: monthly files
                        for month in range(1, 13):
                            result = build_hydro_url(hydro_interval, year, month)
                            urls.append({
                                "url": result.url,
                                "filename": result.filename,
                                "year": year,
                                "month": month,
                            })
                elif hydro_interval == HydroInterval.SEMI_ANNUAL:
                    if hydro_param:
                        result = build_hydro_url(hydro_interval, year, param=hydro_param)
                        urls.append({
                            "url": result.url,
                            "filename": result.filename,
                            "year": year,
                        })
                    else:
                        for p in [HydroParam.FLOW, HydroParam.DEPTH, HydroParam.TEMPERATURE]:
                            result = build_hydro_url(hydro_interval, year, param=p)
                            urls.append({
                                "url": result.url,
                                "filename": result.filename,
                                "year": year,
                                "param": p.value,
                            })
                else:
                    result = build_hydro_url(hydro_interval, year)
                    urls.append({
                        "url": result.url,
                        "filename": result.filename,
                        "year": year,
                    })
            except ValueError as e:
                errors.append(f"Rok {year}: {e}")

    except ValueError as e:
        errors.append(str(e))

    return templates.TemplateResponse(
        "partials/download_links.html",
        {
            "request": request,
            "urls": urls,
            "errors": errors,
            "count": len(urls),
        },
    )


@router.get("/download/meteo", response_class=HTMLResponse)
async def download_meteo_page(request: Request):
    """Meteorological data download form."""
    return templates.TemplateResponse(
        "download/meteo.html",
        {
            "request": request,
            "title": "Dane meteorologiczne",
            "intervals": [
                ("dobowe", "Dobowe"),
                ("miesieczne", "Miesięczne"),
                ("terminowe", "Terminowe (godzinowe)"),
            ],
            "subtypes": [
                ("klimat", "Klimat"),
                ("opad", "Opad"),
                ("synop", "Synop"),
            ],
        },
    )


@router.post("/download/meteo/generate", response_class=HTMLResponse)
async def generate_meteo_urls(
    request: Request,
    interval: str = Form(...),
    subtype: str = Form(...),
    start_year: int = Form(...),
    end_year: int = Form(...),
):
    """Generate meteo download URLs (HTMX partial)."""
    urls = []
    errors = []

    try:
        meteo_interval = MeteoInterval(interval)
        meteo_subtype = MeteoSubtype(subtype)

        for year in range(start_year, end_year + 1):
            try:
                if year <= 2000:
                    # 1951-2000: yearly files (no monthly split)
                    result = build_meteo_url(meteo_interval, meteo_subtype, year)
                    urls.append({
                        "url": result.url,
                        "filename": result.filename,
                        "year": year,
                    })
                elif meteo_interval in [MeteoInterval.DAILY, MeteoInterval.HOURLY]:
                    # 2001+: monthly files
                    for month in range(1, 13):
                        result = build_meteo_url(meteo_interval, meteo_subtype, year, month)
                        urls.append({
                            "url": result.url,
                            "filename": result.filename,
                            "year": year,
                            "month": month,
                        })
                else:
                    result = build_meteo_url(meteo_interval, meteo_subtype, year)
                    urls.append({
                        "url": result.url,
                        "filename": result.filename,
                        "year": year,
                    })
            except ValueError as e:
                errors.append(f"Rok {year}: {e}")

    except ValueError as e:
        errors.append(str(e))

    return templates.TemplateResponse(
        "partials/download_links.html",
        {
            "request": request,
            "urls": urls,
            "errors": errors,
            "count": len(urls),
        },
    )


@router.get("/download/pmaxtp", response_class=HTMLResponse)
async def download_pmaxtp_page(request: Request):
    """PMAXTP data download form."""
    return templates.TemplateResponse(
        "download/pmaxtp.html",
        {
            "request": request,
            "title": "Opady maksymalne (PMAXTP)",
            "methods": [
                ("POT", "Peak Over Threshold"),
                ("AMP", "Annual Max Precipitation"),
            ],
        },
    )


@router.post("/download/pmaxtp/generate", response_class=HTMLResponse)
async def generate_pmaxtp_url(
    request: Request,
    method: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
):
    """Generate PMAXTP URL and fetch data (HTMX partial)."""
    try:
        pmaxtp_method = PMaXTPMethod(method)
        url = build_pmaxtp_url(pmaxtp_method, latitude, longitude)

        # Fetch data from IMGW
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        return templates.TemplateResponse(
            "partials/pmaxtp_result.html",
            {
                "request": request,
                "url": url,
                "method": method,
                "latitude": latitude,
                "longitude": longitude,
                "data": data,
            },
        )

    except httpx.HTTPError as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "error": f"Błąd pobierania danych: {e}",
            },
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "error": str(e),
            },
        )


@router.get("/stations", response_class=HTMLResponse)
async def stations_page(request: Request):
    """Stations list page."""
    return templates.TemplateResponse(
        "stations/list.html",
        {
            "request": request,
            "title": "Lista stacji",
        },
    )


@router.get("/stations/hydro", response_class=HTMLResponse)
async def hydro_stations_partial(
    request: Request,
    search: Optional[str] = Query(None),
    limit: int = Query(50),
):
    """
    Hydrological stations list (HTMX partial).

    Fetches station data from IMGW CSV file (CP1250 encoding).
    CSV format: ID, name, river (hydro_id), code
    Links to station pages: https://hydro.imgw.pl/#/station/hydro/{id}
    """
    csv_url = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/lista_stacji_hydro.csv"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(csv_url, timeout=30.0)
            response.raise_for_status()
            content = response.content.decode("cp1250")

        import csv
        import io
        import re

        stations = []
        reader = csv.reader(io.StringIO(content))
        for row in reader:
            if len(row) >= 3:
                river_raw = row[2].strip('"')
                # Extract river name and hydro ID from "Odra (1)" format
                match = re.match(r'^(.+?)\s*\((\d+)\)$', river_raw)
                if match:
                    river_name = match.group(1).strip()
                    river_id = match.group(2)
                else:
                    river_name = river_raw
                    river_id = None

                station = {
                    "id": row[0].strip().strip('"'),
                    "name": row[1].strip('"'),
                    "river": river_name,
                    "river_id": river_id,
                }
                if search:
                    if search.lower() in station["name"].lower() or search.lower() in station["river"].lower():
                        stations.append(station)
                else:
                    stations.append(station)

        stations = stations[:limit]

        return templates.TemplateResponse(
            "partials/station_table.html",
            {
                "request": request,
                "stations": stations,
                "data_type": "hydro",
                "count": len(stations),
            },
        )

    except httpx.HTTPError as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "error": f"Błąd pobierania stacji: {e}",
            },
        )


@router.get("/stations/meteo", response_class=HTMLResponse)
async def meteo_stations_partial(
    request: Request,
    search: Optional[str] = Query(None),
    limit: int = Query(50),
):
    """
    Meteorological stations list (HTMX partial).

    Fetches station data from IMGW CSV file (CP1250 encoding).
    CSV format: ID, name, code
    Links to station pages: https://hydro.imgw.pl/#/station/meteo/{id}
    """
    csv_url = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/wykaz_stacji.csv"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(csv_url, timeout=30.0)
            response.raise_for_status()
            content = response.content.decode("cp1250")

        import csv
        import io

        stations = []
        reader = csv.reader(io.StringIO(content))
        for row in reader:
            if len(row) >= 2:
                station = {
                    "id": row[0].strip('"'),
                    "name": row[1].strip('"'),
                }
                if search:
                    if search.lower() in station["name"].lower():
                        stations.append(station)
                else:
                    stations.append(station)

        stations = stations[:limit]

        return templates.TemplateResponse(
            "partials/station_table.html",
            {
                "request": request,
                "stations": stations,
                "data_type": "meteo",
                "count": len(stations),
            },
        )

    except httpx.HTTPError as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "error": f"Błąd pobierania stacji: {e}",
            },
        )


@router.get("/map", response_class=HTMLResponse)
async def map_page(request: Request):
    """Map page with station locations."""
    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "title": "Mapa stacji",
        },
    )


@router.get("/map/stations")
async def map_stations_data(request: Request):
    """
    Get hydro stations data for map (JSON response for Leaflet).

    Fetches real-time data from IMGW API: https://danepubliczne.imgw.pl/api/data/hydro
    Returns station ID, name, river, coordinates (lat/lon), and current water level.
    """
    url = build_api_url("hydro")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        stations = []
        for item in data:
            if item.get("lat") and item.get("lon"):
                stations.append({
                    "id": item.get("id_stacji", ""),
                    "name": item.get("stacja", ""),
                    "river": item.get("rzeka", ""),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "water_level": item.get("stan_wody"),
                })

        return {"stations": stations}

    except httpx.HTTPError:
        return {"stations": [], "error": "Błąd pobierania danych"}
