"""Pydantic schemas for API request/response models."""

import datetime as dt
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from imgwtools.models import PMaXTPResult


# Enums for API
class DataTypeEnum(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Type of IMGW dataset exposed by the API."""

    HYDRO = "hydro"
    METEO = "meteo"


class HydroIntervalEnum(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Interval for hydrological data."""

    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    SEMI_ANNUAL = "polroczne_i_roczne"


class MeteoIntervalEnum(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Interval for meteorological data."""

    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    HOURLY = "terminowe"


class MeteoSubtypeEnum(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Subtype of meteorological data."""

    CLIMATE = "klimat"
    PRECIPITATION = "opad"
    SYNOP = "synop"


class HydroParamEnum(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Parameter for semi-annual/annual hydrological data."""

    TEMPERATURE = "T"
    FLOW = "Q"
    DEPTH = "H"


class PMaXTPMethodEnum(str, Enum):  # noqa: UP042 - public enums retain legacy str() behavior
    """Method for PMAXTP data."""

    POT = "POT"
    AMP = "AMP"


# Station schemas
class Station(BaseModel):
    """Station metadata."""

    id: str = Field(..., description="Station ID")
    name: str = Field(..., description="Station name")
    river: str | None = Field(
        default=None, description="River name (for hydro stations)"
    )
    latitude: float | None = Field(default=None, description="Latitude")
    longitude: float | None = Field(default=None, description="Longitude")


class StationList(BaseModel):
    """List of stations."""

    stations: list[Station]
    count: int


# Dataset schemas
class Dataset(BaseModel):
    """Available dataset description."""

    data_type: DataTypeEnum
    interval: str
    description: str
    year_range: tuple[int, int]


class DatasetList(BaseModel):
    """List of available datasets."""

    datasets: list[Dataset]


# Download URL schemas
class HydroDownloadRequest(BaseModel):
    """Request to generate hydro download URL."""

    interval: HydroIntervalEnum
    year: int = Field(..., ge=1951, le=9999)
    month: int | None = Field(
        default=None, ge=1, le=13, description="Month (1-12) or 13 for phenomena"
    )
    param: HydroParamEnum | None = Field(
        default=None, description="Parameter for semi-annual data"
    )


class MeteoDownloadRequest(BaseModel):
    """Request to generate meteo download URL."""

    interval: MeteoIntervalEnum
    subtype: MeteoSubtypeEnum
    year: int = Field(..., ge=1950)
    month: int | None = Field(default=None, ge=1, le=12)


class PMaXTPRequest(BaseModel):
    """Request for PMAXTP data."""

    method: PMaXTPMethodEnum
    latitude: float = Field(
        ..., ge=49.0, le=55.0, description="Latitude (Poland range)"
    )
    longitude: float = Field(
        ..., ge=14.0, le=24.5, description="Longitude (Poland range)"
    )


class DownloadURLResponse(BaseModel):
    """Response with download URL."""

    url: str = Field(..., description="Direct download URL to IMGW server")
    filename: str = Field(..., description="Filename")
    data_type: str
    interval: str
    year: int
    month: int | None = None


class MultiDownloadURLResponse(BaseModel):
    """Response with multiple download URLs."""

    urls: list[DownloadURLResponse]
    count: int


# API current data schemas
class HydroCurrentData(BaseModel):
    """Current hydrological data from API."""

    station_id: str
    station_name: str
    river: str | None = None
    province: str | None = None
    water_level: float | None = None
    water_level_date: str | None = None
    flow: float | None = None
    temperature: float | None = None
    latitude: float | None = None
    longitude: float | None = None


class MeteoCurrentData(BaseModel):
    """Current meteorological data from API."""

    station_id: str
    station_name: str
    temperature: float | None = None
    wind_speed: float | None = None
    wind_direction: int | None = None
    humidity: float | None = None
    precipitation: float | None = None
    pressure: float | None = None
    measurement_date: str | None = None


class WarningData(BaseModel):
    """Weather/hydro warning data."""

    id: str
    type: str
    level: int | None = None
    region: str | None = None
    description: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


# Health check
class HealthCheck(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"


# Versioned store schemas (/api/v1/store, /api/v1/series, /api/v1/pmaxtp/store).
# Every path in these responses is a POSIX path relative to the store root.
VersionStatus = Literal["created", "unchanged", "cancelled", "failed"]
YearType = Literal["hydrological", "calendar"]


class StoreErrorResponse(BaseModel):
    """Error body of the versioned store routes."""

    code: str = Field(
        ...,
        description=(
            "Kod błędu, np. store_not_configured, writes_disabled, invalid_api_key, "
            "validation_error, not_found, stale_plan, source_unavailable, "
            "missing_dependency"
        ),
    )
    detail: str = Field(..., description="Opis błędu po polsku")


class StoreInfoResponse(BaseModel):
    """Offline description of the configured store root (fields of ``StoreInfo``)."""

    model_config = ConfigDict(populate_by_name=True)

    root: str = Field(
        ".", description="Katalog magazynu; ścieżki odpowiedzi są względne do niego"
    )
    exists: bool = Field(..., description="Czy katalog magazynu istnieje")
    schema_: str | None = Field(
        ..., alias="schema", description="Schemat znacznika, np. imgw-store/1"
    )
    supported: bool = Field(..., description="Czy biblioteka obsługuje ten magazyn")
    contracts: dict[str, str] = Field(
        ..., description="Wersje kontraktów obsługiwane przez bibliotekę"
    )
    problems: list[str] = Field(..., description="Wykryte problemy magazynu")


class StoreLicenseResponse(BaseModel):
    """License and attribution of a stored version."""

    id: str = Field(..., description="Identyfikator licencji, IMGW-PIB")
    attribution: str = Field(..., description="Wymagana formuła atrybucji")
    url: str = Field(..., description="Adres warunków korzystania z danych")


class StoreMetaResponse(BaseModel):
    """Parsed ``imgw-meta/1`` sidecar of a store version."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: str = Field(..., alias="schema", description="Schemat sidecara")
    dataset: str = Field(..., description="Klucz zbioru, np. pl.imgw.hydro_daily")
    sha256: str = Field(..., description="SHA-256 pliku głównego wersji")
    size_bytes: int = Field(..., description="Rozmiar pliku głównego w bajtach")
    downloaded_at: dt.datetime = Field(
        ..., description="Czas pobrania lub budowy (UTC)"
    )
    license: StoreLicenseResponse
    request: dict[str, Any] = Field(..., description="Żądanie, które utworzyło wersję")
    extra: dict[str, Any] = Field(
        ..., description="Etykieta wersji, sygnał HTTP, okres i źródła"
    )


class StoreEntryResponse(BaseModel):
    """Published version or detected problem of an offline store scan."""

    kind: Literal["archive", "series", "catalog", "pmaxtp", "problem"]
    slot: str = Field(..., description="Identyfikator slotu, np. series:hydro_daily")
    version: str | None = Field(
        ..., description="Plik główny wersji albo element z problemem (względnie)"
    )
    meta: StoreMetaResponse | None = None
    problem_code: str | None = None
    problem: str | None = None


class StoreSelectionRequest(BaseModel):
    """Archive selectors of ``POST /store/check``."""

    model_config = ConfigDict(extra="forbid")

    datasets: list[str] = Field(
        ..., min_length=1, description="Klucze zbiorów, np. pl.imgw.hydro_daily"
    )
    years: list[int] = Field(..., min_length=1, description="Roczniki")
    months: list[int] | None = Field(
        default=None, description="Miesiące 1–12 (domyślnie wszystkie)"
    )


class StoreSyncRequest(BaseModel):
    """Body of ``POST /store/sync``: archive selectors or a plan, never both."""

    model_config = ConfigDict(extra="forbid")

    datasets: list[str] | None = Field(default=None, description="Klucze zbiorów")
    years: list[int] | None = Field(default=None, description="Roczniki")
    months: list[int] | None = Field(default=None, description="Miesiące 1–12")
    plan: dict[str, Any] | None = Field(
        default=None,
        description="Dokument imgw-plan/1 zwrócony przez POST /store/check",
    )
    series: bool = Field(
        default=True, description="Przebuduj szeregi po udanej synchronizacji"
    )


class OperationResultResponse(BaseModel):
    """Outcome of one archive slot in a sync report."""

    slot: str
    status: Literal[
        "created",
        "relabeled",
        "unchanged",
        "reused",
        "failed",
        "stale_plan",
        "cancelled",
    ]
    version: str | None
    error: str | None


class SeriesReportResponse(BaseModel):
    """Result of building an ``imgw-series/1`` version."""

    status: Literal["created", "reused", "cancelled", "failed"]
    version: str | None = Field(..., description="Plik series.json wersji")
    stations: int
    source_files: list[str] = Field(..., description="Archiwa wejściowe szeregu")
    problems: list[str]


class SyncReportResponse(BaseModel):
    """Full report of ``POST /store/sync``."""

    items: list[OperationResultResponse]
    series: list[SeriesReportResponse]
    cancelled: bool


class StoreStalePlanResponse(StoreErrorResponse):
    """409 body of a sync whose plan no longer matches the IMGW server."""

    report: SyncReportResponse = Field(
        ..., description="Pełny raport synchronizacji (pozycje stale_plan pominięte)"
    )


class CatalogRequest(BaseModel):
    """Body of ``POST /store/catalog``."""

    model_config = ConfigDict(extra="forbid")

    user_locations: str | None = Field(
        default=None,
        description=(
            "Nazwa pliku CSV współrzędnych umieszczonego wcześniej na serwerze w "
            "katalogu IMGW_USER_LOCATIONS_DIR (bez ścieżki)"
        ),
    )


class CatalogReportResponse(BaseModel):
    """Result of building the ``stations.geojson`` catalog."""

    status: VersionStatus
    version: str | None = Field(..., description="Plik stations.geojson wersji")
    station_count: int
    without_location: int
    problems: list[str]


class SeriesBuildRequest(BaseModel):
    """Body of ``POST /series/build``."""

    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(..., description="Klucz zbioru, np. pl.imgw.hydro_daily")


class SeriesExportRequest(BaseModel):
    """Body of ``POST /series/export``; the CSV is returned, never stored."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(
        ...,
        description=(
            "Wersja szeregu względna do magazynu: series/versions/<zbiór>/<etykieta>"
            " albo jej series.json"
        ),
    )
    station: str = Field(..., description="Kod stacji (9 cyfr)")
    variables: list[str] = Field(..., min_length=1, description="Zmienne, np. Q,H")
    year_type: YearType | None = Field(
        default=None, description="Rodzaj roku; domyślnie wg spisu szeregu"
    )


class StationCoverageResponse(BaseModel):
    """Coverage of one variable at one station."""

    variable: str
    unit: str
    period: Literal["winter", "summer", "annual"] | None
    first: dt.date | None
    last: dt.date | None
    with_value: int
    accumulated: int
    gaps: list[tuple[dt.date, dt.date]]


class StationSeriesIndexResponse(BaseModel):
    """Index entry of one station Parquet file."""

    file: str = Field(..., description="Plik Parquet względny do katalogu wersji")
    sha256: str
    rows: int
    variables: dict[str, StationCoverageResponse]


class SeriesIndexResponse(BaseModel):
    """Parsed ``series.json`` of a series version (fields of ``SeriesIndex``)."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: str = Field(..., alias="schema", description="imgw-series/1")
    dataset: str
    year_type: YearType
    periods: list[tuple[dt.date, dt.date]]
    stations: dict[str, StationSeriesIndexResponse]


class MeasurementResponse(BaseModel):
    """Value and flag of one variable."""

    value: float | None
    flag: Literal["value", "missing", "no_phenomenon", "accumulated"]


class SeriesRecordResponse(BaseModel):
    """One station record of a series (fields of ``NormalizedRecord``)."""

    station_code: str
    dataset: str
    date: dt.date
    hydro_year: int
    period: Literal["winter", "summer", "annual"] | None
    measurements: dict[str, MeasurementResponse]
    attributes: dict[str, str | None]
    extrema_dates: dict[str, tuple[dt.datetime | None, dt.datetime | None]]


class PMaXTPStoreSyncRequest(BaseModel):
    """Body of ``POST /pmaxtp/store/sync``."""

    model_config = ConfigDict(extra="forbid")

    method: PMaXTPMethodEnum
    latitude: float = Field(..., description="Szerokość geograficzna (WGS84)")
    longitude: float = Field(..., description="Długość geograficzna (WGS84)")
    ind_x: int | None = Field(
        default=None, ge=0, description="Oczekiwany indeks X komórki (razem z ind_y)"
    )
    ind_y: int | None = Field(
        default=None, ge=0, description="Oczekiwany indeks Y komórki (razem z ind_x)"
    )


class PMaXTPStoreResponse(BaseModel):
    """Result of storing a PMAXTP grid cell."""

    status: VersionStatus
    version: str | None = Field(..., description="Plik cell.json wersji")
    ind_x: int | None
    ind_y: int | None
    result: PMaXTPResult | None
