"""
Hydrological data routes.
"""


import httpx
from fastapi import APIRouter, HTTPException, Query

from imgwtools.api.schemas import (
    DownloadURLResponse,
    HydroCurrentData,
    HydroDailyDataPoint,
    HydroDataResponse,
    HydroDownloadRequest,
    HydroMonthlyDataPoint,
    MultiDownloadURLResponse,
    Station,
    StationList,
)
from imgwtools.core.url_builder import (
    HydroInterval,
    HydroParam,
    build_api_url,
    build_hydro_url,
)

router = APIRouter()


@router.get("/stations", response_model=StationList)
async def list_hydro_stations(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Lista stacji hydrologicznych.

    Zwraca liste stacji z ID, nazwa i rzeka.
    Dane pochodza z lokalnego pliku CSV.
    """
    # TODO: Load from CSV file
    # For now, return example data
    stations = [
        Station(id="150160180", name="Warszawa", river="Wisla"),
        Station(id="150170010", name="Krakow", river="Wisla"),
    ]
    return StationList(stations=stations[offset : offset + limit], count=len(stations))


@router.get("/stations/{station_id}", response_model=Station)
async def get_hydro_station(station_id: str):
    """
    Szczegoly stacji hydrologicznej.

    Pobiera aktualne dane z API IMGW.
    """
    url = build_api_url("hydro2", station_id=station_id)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if not data:
                raise HTTPException(status_code=404, detail="Station not found")

            station_data = data[0] if isinstance(data, list) else data
            return Station(
                id=station_id,
                name=station_data.get("nazwa_stacji", ""),
                river=station_data.get("rzeka", ""),
                latitude=float(station_data.get("lat", 0)) if station_data.get("lat") else None,
                longitude=float(station_data.get("lon", 0)) if station_data.get("lon") else None,
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"IMGW API error: {str(e)}")


@router.get("/current", response_model=list[HydroCurrentData])
async def get_current_hydro_data(
    station_id: str | None = Query(None, description="Filter by station ID"),
):
    """
    Aktualne dane hydrologiczne.

    Pobiera dane bezposrednio z API IMGW.
    """
    url = build_api_url("hydro2", station_id=station_id)

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
                    HydroCurrentData(
                        station_id=item.get("id_stacji", ""),
                        station_name=item.get("nazwa_stacji", ""),
                        river=item.get("rzeka"),
                        province=item.get("wojewodztwo"),
                        water_level=float(item["stan_wody"]) if item.get("stan_wody") else None,
                        water_level_date=item.get("stan_wody_data_pomiaru"),
                        flow=float(item["przeplyw"]) if item.get("przeplyw") else None,
                        temperature=float(item["temperatura_wody"]) if item.get("temperatura_wody") else None,
                        latitude=float(item["lat"]) if item.get("lat") else None,
                        longitude=float(item["lon"]) if item.get("lon") else None,
                    )
                )

            return results

        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"IMGW API error: {str(e)}")


@router.post("/download-url", response_model=DownloadURLResponse)
async def generate_hydro_download_url(request: HydroDownloadRequest):
    """
    Generuj link do pobrania danych hydrologicznych.

    Zwraca bezposredni URL do serwera IMGW.
    Dane NIE sa przechowywane na serwerze - klient pobiera bezposrednio z IMGW.
    """
    try:
        interval = HydroInterval(request.interval.value)
        param = HydroParam(request.param.value) if request.param else None

        result = build_hydro_url(
            interval=interval,
            year=request.year,
            month=request.month,
            param=param,
        )

        return DownloadURLResponse(
            url=result.url,
            filename=result.filename,
            data_type=result.data_type,
            interval=result.interval,
            year=result.year,
            month=result.month,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/download-urls", response_model=MultiDownloadURLResponse)
async def generate_hydro_download_urls(
    interval: HydroInterval,
    start_year: int = Query(..., ge=1951, le=2024),
    end_year: int = Query(..., ge=1951, le=2024),
    param: HydroParam | None = None,
):
    """
    Generuj wiele linkow do pobrania danych hydrologicznych.

    Zwraca liste bezposrednich URL-ow do serwera IMGW dla zakresu lat.
    """
    if start_year > end_year:
        raise HTTPException(status_code=400, detail="start_year must be <= end_year")

    urls = []

    for year in range(start_year, end_year + 1):
        try:
            if interval == HydroInterval.DAILY:
                if year >= 2023:
                    # From 2023: single file per year
                    result = build_hydro_url(interval=interval, year=year)
                    urls.append(
                        DownloadURLResponse(
                            url=result.url,
                            filename=result.filename,
                            data_type=result.data_type,
                            interval=result.interval,
                            year=result.year,
                            month=result.month,
                        )
                    )
                else:
                    # Before 2023: generate for each month
                    for month in range(1, 13):
                        result = build_hydro_url(interval=interval, year=year, month=month)
                        urls.append(
                            DownloadURLResponse(
                                url=result.url,
                                filename=result.filename,
                                data_type=result.data_type,
                                interval=result.interval,
                                year=result.year,
                                month=result.month,
                            )
                        )
            else:
                result = build_hydro_url(interval=interval, year=year, param=param)
                urls.append(
                    DownloadURLResponse(
                        url=result.url,
                        filename=result.filename,
                        data_type=result.data_type,
                        interval=result.interval,
                        year=result.year,
                        month=result.month,
                    )
                )
        except ValueError:
            continue  # Skip invalid combinations

    return MultiDownloadURLResponse(urls=urls, count=len(urls))


@router.get("/data", response_model=HydroDataResponse)
async def get_hydro_data(
    station_id: str = Query(..., description="Station code"),
    start_year: int = Query(..., ge=1951, le=2024, description="Start hydrological year"),
    end_year: int = Query(..., ge=1951, le=2024, description="End hydrological year"),
    interval: str = Query("dobowe", description="Data interval: dobowe, miesieczne"),
    use_cache: bool = Query(True, description="Use DB cache if enabled"),
):
    """
    Pobierz dane hydrologiczne z cache.

    Jesli cache jest wlaczony (IMGW_DB_ENABLED=true) i use_cache=True:
    - Sprawdza czy dane sa w cache
    - Jesli nie, pobiera z IMGW i cache'uje (lazy loading)
    - Zwraca dane z cache

    Jesli cache nie jest wlaczony lub use_cache=False:
    - Zwraca URL do pobrania danych bezposrednio z IMGW
    """
    from imgwtools.config import settings

    if start_year > end_year:
        raise HTTPException(status_code=400, detail="start_year must be <= end_year")

    valid_intervals = ["dobowe", "miesieczne"]
    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Allowed: {', '.join(valid_intervals)}"
        )

    # Check if cache is enabled
    if not settings.db_enabled or not use_cache:
        raise HTTPException(
            status_code=400,
            detail="Database cache is not enabled. Set IMGW_DB_ENABLED=true or use /download-url endpoint."
        )

    try:
        from imgwtools.db import db_exists, get_cache_manager, init_db

        # Initialize DB if needed
        if not db_exists():
            init_db()

        manager = get_cache_manager()

        # Ensure data is cached (lazy loading)
        for year in range(start_year, end_year + 1):
            if interval == "dobowe" and year < 2023:
                # Before 2023: monthly files
                for month in range(1, 13):
                    await manager.ensure_data_cached(interval, year, month)
            else:
                # Single file per year
                await manager.ensure_data_cached(interval, year)

        # Query data from cache
        if interval == "dobowe":
            records = manager.get_daily_data(
                station_code=station_id,
                start_year=start_year,
                end_year=end_year,
            )

            data_points = [
                HydroDailyDataPoint(
                    date=r.measurement_date or "",
                    water_level_cm=r.water_level_cm,
                    flow_m3s=r.flow_m3s,
                    water_temp_c=r.water_temp_c,
                )
                for r in records
            ]

            station_name = records[0].station_name if records else None
            river = records[0].river_name if records else None

        else:  # miesieczne
            records = manager.get_monthly_data(
                station_code=station_id,
                start_year=start_year,
                end_year=end_year,
            )

            data_points = [
                HydroMonthlyDataPoint(
                    year=r.hydro_year,
                    month=r.hydro_month,
                    extremum=r.extremum,
                    water_level_cm=r.water_level_cm,
                    flow_m3s=r.flow_m3s,
                    water_temp_c=r.water_temp_c,
                )
                for r in records
            ]

            station_name = records[0].station_name if records else None
            river = records[0].river_name if records else None

        return HydroDataResponse(
            station_id=station_id,
            station_name=station_name,
            river=river,
            interval=interval,
            start_year=start_year,
            end_year=end_year,
            data=data_points,
            count=len(data_points),
            source="cache",
        )

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")
