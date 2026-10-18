"""Generate direct IMGW archive URLs without downloading the archives."""

from pathlib import PurePosixPath

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
)
from imgwtools.datasets import ArchiveFile, archive_files, datasets
from imgwtools.exceptions import IMGWValidationError

router = APIRouter()

_HYDRO = {
    HydroInterval.DAILY: "pl.imgw.hydro_daily",
    HydroInterval.MONTHLY: "pl.imgw.hydro_monthly",
    HydroInterval.SEMI_ANNUAL: "pl.imgw.hydro_semiannual",
}
_METEO = {
    MeteoSubtype.CLIMATE: "pl.imgw.meteo_climate_daily",
    MeteoSubtype.PRECIPITATION: "pl.imgw.meteo_precip_daily",
}


def _download_urls(
    *,
    data_type: DataTypeEnum,
    interval: str,
    years: range | tuple[int, ...],
    month: int | None = None,
    param: str | None = None,
    subtype: str | None = None,
    single: bool = False,
) -> list[DownloadURLResponse]:
    """Use the registry for supported archives and legacy builders for other URLs."""
    try:
        if data_type == DataTypeEnum.HYDRO:
            hydro_interval = HydroInterval(interval)
            if subtype is not None:
                raise ValueError("Podtyp nie dotyczy danych hydrologicznych")
            hydro_param = HydroParam(param) if param is not None else None
            if hydro_interval != HydroInterval.SEMI_ANNUAL and hydro_param is not None:
                raise ValueError("Parametr dotyczy tylko danych półrocznych")
            if (
                hydro_interval == HydroInterval.SEMI_ANNUAL
                and single
                and hydro_param is None
            ):
                raise ValueError("Podaj parametr H, Q lub T dla danych półrocznych")
            if month == 13 and hydro_interval == HydroInterval.DAILY:
                return [
                    _legacy(build_hydro_url(hydro_interval, year, month=13))
                    for year in years
                ]
            if month is not None and not 1 <= month <= 12:
                raise ValueError("Miesiąc musi należeć do zakresu 1–12")
            if (
                single
                and hydro_interval == HydroInterval.DAILY
                and years[0] < 2023
                and month is None
            ):
                raise ValueError("Podaj miesiąc danych dobowych przed 2023")
            dataset = _HYDRO[hydro_interval]
            source = archive_files(
                dataset, years=years, months=[month] if month is not None else None
            )
            source = tuple(
                item
                for item in source
                if hydro_param is None or item.param == hydro_param.value
            )
            folder = DataType.HYDRO.value
        else:
            if subtype is None:
                raise ValueError("Podaj podtyp danych meteorologicznych")
            if param is not None:
                raise ValueError("Parametr dotyczy tylko danych hydrologicznych")
            meteo_interval, meteo_subtype = (
                MeteoInterval(interval),
                MeteoSubtype(subtype),
            )
            if meteo_interval == MeteoInterval.DAILY and meteo_subtype in _METEO:
                if single and years[0] > 2000 and month is None:
                    raise ValueError("Podaj miesiąc danych dobowych od 2001")
                source = archive_files(
                    _METEO[meteo_subtype],
                    years=years,
                    months=[month] if month is not None else None,
                )
                folder = DataType.METEO.value
            else:
                if month is not None and not 1 <= month <= 12:
                    raise ValueError("Miesiąc musi należeć do zakresu 1–12")
                return [
                    _legacy(
                        build_meteo_url(
                            meteo_interval, meteo_subtype, year, month=month
                        )
                    )
                    for year in years
                ]
        return [
            DownloadURLResponse(
                url=item.url,
                filename=PurePosixPath(item.server_path).name,
                data_type=folder,
                interval=interval,
                year=_archive_year(item),
                month=month
                if single and month is not None and folder == DataType.HYDRO.value
                else item.month,
            )
            for item in source
        ]
    except IMGWValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Nieprawidłowa kombinacja typu, interwału, podtypu, parametru lub roku archiwum IMGW",
        ) from exc


def _archive_year(item: ArchiveFile) -> int:
    if item.year is None:
        raise ValueError(f"Archiwum bez roku: {item.server_path}")
    return item.year


def _legacy(result) -> DownloadURLResponse:
    return DownloadURLResponse(
        url=result.url,
        filename=result.filename,
        data_type=result.data_type,
        interval=result.interval,
        year=result.year,
        month=result.month,
    )


@router.get("/datasets", response_model=DatasetList)
async def list_available_datasets():
    """List the five archive datasets represented by the canonical registry."""
    items = []
    for descriptor in datasets():
        if not descriptor.in_store or descriptor.time_unit not in (
            "day",
            "month",
            "half_year",
        ):
            continue
        items.append(
            Dataset(
                data_type=DataTypeEnum.HYDRO
                if descriptor.key.startswith("pl.imgw.hydro_")
                else DataTypeEnum.METEO,
                interval={
                    "day": "dobowe",
                    "month": "miesieczne",
                    "half_year": "polroczne_i_roczne",
                }[descriptor.time_unit],
                description=f"Dane IMGW: {descriptor.slug}",
                year_range=(
                    1950 if descriptor.slug == "meteo_precip_daily" else 1951,
                    9999,
                ),
            )
        )
    return DatasetList(datasets=items)


@router.get("/url", response_model=DownloadURLResponse)
async def generate_download_url(
    data_type: DataTypeEnum = Query(..., description="Typ danych: hydro lub meteo"),
    interval: str = Query(..., description="Interwał danych"),
    year: int = Query(..., ge=1950, le=9999),
    month: int | None = Query(None, ge=1, le=13),
    param: str | None = Query(None),
    subtype: str | None = Query(None),
):
    """Generate one direct download URL."""
    urls = _download_urls(
        data_type=data_type,
        interval=interval,
        years=(year,),
        month=month,
        param=param,
        subtype=subtype,
        single=True,
    )
    return urls[0]


@router.get("/urls", response_model=MultiDownloadURLResponse)
async def generate_download_urls(
    data_type: DataTypeEnum = Query(...),
    interval: str = Query(...),
    start_year: int = Query(..., ge=1950, le=9999),
    end_year: int = Query(..., ge=1950, le=9999),
    param: str | None = Query(None),
    subtype: str | None = Query(None),
):
    """Generate all archive URLs for a year range without silently skipping errors."""
    if start_year > end_year:
        raise HTTPException(
            status_code=400, detail="Rok początkowy nie może przekraczać końcowego"
        )
    urls = _download_urls(
        data_type=data_type,
        interval=interval,
        years=range(start_year, end_year + 1),
        param=param,
        subtype=subtype,
    )
    return MultiDownloadURLResponse(urls=urls, count=len(urls))
