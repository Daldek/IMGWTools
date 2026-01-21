"""
Download URL generation routes.

This module provides a unified endpoint for generating download URLs
for both hydrological and meteorological data.
"""


from fastapi import APIRouter, HTTPException, Query

from imgwtools.api.schemas import (
    Dataset,
    DatasetList,
    DataTypeEnum,
    DownloadURLResponse,
    MultiDownloadURLResponse,
)
from imgwtools.core.url_builder import (
    DataType,
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    build_hydro_url,
    build_meteo_url,
    get_available_years,
)

router = APIRouter()


@router.get("/datasets", response_model=DatasetList)
async def list_available_datasets():
    """
    Lista dostepnych zbiorow danych.

    Zwraca informacje o typach danych, interwalach i zakresie lat.
    """
    datasets = [
        # Hydrological datasets
        Dataset(
            data_type=DataTypeEnum.HYDRO,
            interval="dobowe",
            description="Dobowe dane hydrologiczne (stan wody, przeplyw, temperatura)",
            year_range=(1951, 2023),
        ),
        Dataset(
            data_type=DataTypeEnum.HYDRO,
            interval="miesieczne",
            description="Miesieczne dane hydrologiczne",
            year_range=(1951, 2023),
        ),
        Dataset(
            data_type=DataTypeEnum.HYDRO,
            interval="polroczne_i_roczne",
            description="Polroczne i roczne dane hydrologiczne (T, Q, H)",
            year_range=(1951, 2023),
        ),
        # Meteorological datasets
        Dataset(
            data_type=DataTypeEnum.METEO,
            interval="dobowe",
            description="Dobowe dane meteorologiczne",
            year_range=(2001, 2023),
        ),
        Dataset(
            data_type=DataTypeEnum.METEO,
            interval="miesieczne",
            description="Miesieczne dane meteorologiczne",
            year_range=(2001, 2023),
        ),
        Dataset(
            data_type=DataTypeEnum.METEO,
            interval="terminowe",
            description="Terminowe dane meteorologiczne (co godzine)",
            year_range=(2001, 2023),
        ),
    ]

    return DatasetList(datasets=datasets)


@router.get("/url", response_model=DownloadURLResponse)
async def generate_download_url(
    data_type: DataTypeEnum = Query(..., description="Typ danych: hydro lub meteo"),
    interval: str = Query(..., description="Interwal: dobowe, miesieczne, polroczne_i_roczne, terminowe"),
    year: int = Query(..., ge=1951, le=2024, description="Rok"),
    month: int | None = Query(None, ge=1, le=13, description="Miesiac (1-12) lub 13 dla zjawisk"),
    param: str | None = Query(None, description="Parametr dla danych polrocznych: T, Q, H"),
    subtype: str | None = Query(None, description="Podtyp dla meteo: klimat, opad, synop"),
):
    """
    Generuj link do pobrania danych.

    Uniwersalny endpoint dla danych hydrologicznych i meteorologicznych.
    Zwraca bezposredni URL do serwera IMGW.
    """
    try:
        if data_type == DataTypeEnum.HYDRO:
            hydro_interval = HydroInterval(interval)
            hydro_param = HydroParam(param) if param else None

            result = build_hydro_url(
                interval=hydro_interval,
                year=year,
                month=month,
                param=hydro_param,
            )

        else:  # METEO
            if not subtype:
                raise HTTPException(
                    status_code=400,
                    detail="subtype is required for meteorological data",
                )

            meteo_interval = MeteoInterval(interval)
            meteo_subtype = MeteoSubtype(subtype)

            result = build_meteo_url(
                interval=meteo_interval,
                subtype=meteo_subtype,
                year=year,
                month=month,
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


@router.get("/urls", response_model=MultiDownloadURLResponse)
async def generate_download_urls(
    data_type: DataTypeEnum = Query(..., description="Typ danych: hydro lub meteo"),
    interval: str = Query(..., description="Interwal danych"),
    start_year: int = Query(..., ge=1951, le=2024, description="Rok poczatkowy"),
    end_year: int = Query(..., ge=1951, le=2024, description="Rok koncowy"),
    param: str | None = Query(None, description="Parametr dla danych polrocznych hydro: T, Q, H"),
    subtype: str | None = Query(None, description="Podtyp dla meteo: klimat, opad, synop"),
):
    """
    Generuj wiele linkow do pobrania danych.

    Zwraca liste bezposrednich URL-ow do serwera IMGW dla zakresu lat.
    """
    if start_year > end_year:
        raise HTTPException(status_code=400, detail="start_year must be <= end_year")

    # Validate year range
    min_year, max_year = get_available_years(
        DataType.HYDRO if data_type == DataTypeEnum.HYDRO else DataType.METEO,
        interval,
    )

    if start_year < min_year or end_year > max_year:
        raise HTTPException(
            status_code=400,
            detail=f"Year range for {data_type.value}/{interval} is {min_year}-{max_year}",
        )

    urls = []

    for year in range(start_year, end_year + 1):
        try:
            if data_type == DataTypeEnum.HYDRO:
                hydro_interval = HydroInterval(interval)
                hydro_param = HydroParam(param) if param else None

                if hydro_interval == HydroInterval.DAILY:
                    if year >= 2023:
                        # From 2023: single file per year
                        result = build_hydro_url(
                            interval=hydro_interval, year=year
                        )
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
                        for m in range(1, 13):
                            result = build_hydro_url(
                                interval=hydro_interval, year=year, month=m
                            )
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
                    result = build_hydro_url(
                        interval=hydro_interval, year=year, param=hydro_param
                    )
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

            else:  # METEO
                if not subtype:
                    raise HTTPException(
                        status_code=400,
                        detail="subtype is required for meteorological data",
                    )

                meteo_interval = MeteoInterval(interval)
                meteo_subtype = MeteoSubtype(subtype)

                if year <= 2000:
                    # 1951-2000: yearly files (no monthly split)
                    result = build_meteo_url(
                        interval=meteo_interval, subtype=meteo_subtype, year=year
                    )
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
                elif meteo_interval in [MeteoInterval.DAILY, MeteoInterval.HOURLY]:
                    # 2001+: generate for each month
                    for m in range(1, 13):
                        result = build_meteo_url(
                            interval=meteo_interval,
                            subtype=meteo_subtype,
                            year=year,
                            month=m,
                        )
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
                    result = build_meteo_url(
                        interval=meteo_interval, subtype=meteo_subtype, year=year
                    )
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
