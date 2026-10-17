"""Meteorological data routes."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from imgwtools.api.routes.download import _download_urls
from imgwtools.api.schemas import (
    DataTypeEnum,
    DownloadURLResponse,
    MeteoCurrentData,
    MeteoDownloadRequest,
    MultiDownloadURLResponse,
    Station,
    StationList,
)
from imgwtools.core.url_builder import MeteoInterval, MeteoSubtype, build_api_url

router = APIRouter()


@router.get("/stations", response_model=StationList)
async def list_meteo_stations(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Lista stacji meteorologicznych.

    Zwraca liste stacji z ID i nazwa.
    """
    # TODO: Load from CSV file
    stations = [
        Station(id="12375", name="Warszawa-Okecie"),
        Station(id="12566", name="Krakow-Balice"),
    ]
    return StationList(stations=stations[offset : offset + limit], count=len(stations))


@router.get("/synop", response_model=list[MeteoCurrentData])
async def get_synop_data(
    station_id: str | None = Query(None, description="Filter by station ID"),
    station_name: str | None = Query(None, description="Filter by station name"),
):
    """
    Dane synoptyczne.

    Pobiera aktualne dane synoptyczne z API IMGW.
    """
    url = build_api_url("synop", station_id=station_id, station_name=station_name)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if not data:
                return []

            results = []
            items = data if isinstance(data, list) else [data]

            for item in items:
                results.append(
                    MeteoCurrentData(
                        station_id=item.get("id_stacji", ""),
                        station_name=item.get("stacja", ""),
                        temperature=float(item["temperatura"])
                        if item.get("temperatura")
                        else None,
                        wind_speed=float(item["predkosc_wiatru"])
                        if item.get("predkosc_wiatru")
                        else None,
                        wind_direction=int(item["kierunek_wiatru"])
                        if item.get("kierunek_wiatru")
                        else None,
                        humidity=float(item["wilgotnosc_wzgledna"])
                        if item.get("wilgotnosc_wzgledna")
                        else None,
                        precipitation=float(item["suma_opadu"])
                        if item.get("suma_opadu")
                        else None,
                        pressure=float(item["cisnienie"])
                        if item.get("cisnienie")
                        else None,
                        measurement_date=item.get("data_pomiaru"),
                    )
                )

            return results

        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"IMGW API error: {str(e)}")


@router.get("/current", response_model=list[MeteoCurrentData])
async def get_current_meteo_data(
    station_id: str | None = Query(None, description="Filter by station ID"),
):
    """
    Aktualne dane meteorologiczne.

    Pobiera dane bezposrednio z API IMGW (endpoint meteo).
    """
    url = build_api_url("meteo", station_id=station_id)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if not data:
                return []

            results = []
            items = data if isinstance(data, list) else [data]

            for item in items:
                results.append(
                    MeteoCurrentData(
                        station_id=item.get("id_stacji", ""),
                        station_name=item.get("nazwa_stacji", ""),
                        temperature=float(item["temperatura"])
                        if item.get("temperatura")
                        else None,
                        wind_speed=float(item["predkosc_wiatru"])
                        if item.get("predkosc_wiatru")
                        else None,
                        humidity=float(item["wilgotnosc"])
                        if item.get("wilgotnosc")
                        else None,
                        precipitation=float(item["opad"]) if item.get("opad") else None,
                        measurement_date=item.get("data_pomiaru"),
                    )
                )

            return results

        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"IMGW API error: {str(e)}")


@router.post("/download-url", response_model=DownloadURLResponse)
async def generate_meteo_download_url(request: MeteoDownloadRequest):
    """
    Generuj link do pobrania danych meteorologicznych.

    Zwraca bezposredni URL do serwera IMGW.
    """
    return _download_urls(
        data_type=DataTypeEnum.METEO,
        interval=request.interval.value,
        subtype=request.subtype.value,
        years=(request.year,),
        month=request.month,
        single=True,
    )[0]


@router.post("/download-urls", response_model=MultiDownloadURLResponse)
async def generate_meteo_download_urls(
    interval: MeteoInterval,
    subtype: MeteoSubtype,
    start_year: int = Query(..., ge=1950, le=9999),
    end_year: int = Query(..., ge=1950, le=9999),
):
    """Generate all direct archive links in the requested year range."""
    if start_year > end_year:
        raise HTTPException(
            status_code=400, detail="Rok początkowy nie może przekraczać końcowego"
        )
    urls = _download_urls(
        data_type=DataTypeEnum.METEO,
        interval=interval.value,
        subtype=subtype.value,
        years=range(start_year, end_year + 1),
    )
    return MultiDownloadURLResponse(urls=urls, count=len(urls))
