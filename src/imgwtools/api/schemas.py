"""
Pydantic schemas for API request/response models.
"""

from enum import Enum

from pydantic import BaseModel, Field


# Enums for API
class DataTypeEnum(str, Enum):
    HYDRO = "hydro"
    METEO = "meteo"


class HydroIntervalEnum(str, Enum):
    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    SEMI_ANNUAL = "polroczne_i_roczne"


class MeteoIntervalEnum(str, Enum):
    DAILY = "dobowe"
    MONTHLY = "miesieczne"
    HOURLY = "terminowe"


class MeteoSubtypeEnum(str, Enum):
    CLIMATE = "klimat"
    PRECIPITATION = "opad"
    SYNOP = "synop"


class HydroParamEnum(str, Enum):
    TEMPERATURE = "T"
    FLOW = "Q"
    DEPTH = "H"


class PMaXTPMethodEnum(str, Enum):
    POT = "POT"
    AMP = "AMP"


# Station schemas
class Station(BaseModel):
    """Station metadata."""

    id: str = Field(..., description="Station ID")
    name: str = Field(..., description="Station name")
    river: str | None = Field(None, description="River name (for hydro stations)")
    latitude: float | None = Field(None, description="Latitude")
    longitude: float | None = Field(None, description="Longitude")


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
    year: int = Field(..., ge=1951, le=2024)
    month: int | None = Field(None, ge=1, le=13, description="Month (1-12) or 13 for phenomena")
    param: HydroParamEnum | None = Field(None, description="Parameter for semi-annual data")


class MeteoDownloadRequest(BaseModel):
    """Request to generate meteo download URL."""

    interval: MeteoIntervalEnum
    subtype: MeteoSubtypeEnum
    year: int = Field(..., ge=2001, le=2024)
    month: int | None = Field(None, ge=1, le=12)


class PMaXTPRequest(BaseModel):
    """Request for PMAXTP data."""

    method: PMaXTPMethodEnum
    latitude: float = Field(..., ge=49.0, le=55.0, description="Latitude (Poland range)")
    longitude: float = Field(..., ge=14.0, le=24.5, description="Longitude (Poland range)")


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


# Cached hydro data schemas
class HydroDailyDataPoint(BaseModel):
    """Single daily measurement from cache."""

    date: str = Field(..., description="Measurement date (YYYY-MM-DD)")
    water_level_cm: float | None = Field(None, description="Water level in cm")
    flow_m3s: float | None = Field(None, description="Discharge in m3/s")
    water_temp_c: float | None = Field(None, description="Water temperature in Celsius")


class HydroMonthlyDataPoint(BaseModel):
    """Single monthly measurement from cache."""

    year: int
    month: int
    extremum: str = Field(..., description="'min', 'mean', or 'max'")
    water_level_cm: float | None = None
    flow_m3s: float | None = None
    water_temp_c: float | None = None


class HydroDataResponse(BaseModel):
    """Response with cached hydrological data."""

    station_id: str
    station_name: str | None = None
    river: str | None = None
    interval: str
    start_year: int
    end_year: int
    data: list[HydroDailyDataPoint | HydroMonthlyDataPoint]
    count: int
    source: str = Field(..., description="'cache' or 'imgw'")
