"""
Pydantic schemas for API request/response models.
"""

from enum import Enum
from typing import Optional

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
    river: Optional[str] = Field(None, description="River name (for hydro stations)")
    latitude: Optional[float] = Field(None, description="Latitude")
    longitude: Optional[float] = Field(None, description="Longitude")


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
    month: Optional[int] = Field(None, ge=1, le=13, description="Month (1-12) or 13 for phenomena")
    param: Optional[HydroParamEnum] = Field(None, description="Parameter for semi-annual data")


class MeteoDownloadRequest(BaseModel):
    """Request to generate meteo download URL."""

    interval: MeteoIntervalEnum
    subtype: MeteoSubtypeEnum
    year: int = Field(..., ge=2001, le=2024)
    month: Optional[int] = Field(None, ge=1, le=12)


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
    month: Optional[int] = None


class MultiDownloadURLResponse(BaseModel):
    """Response with multiple download URLs."""

    urls: list[DownloadURLResponse]
    count: int


# API current data schemas
class HydroCurrentData(BaseModel):
    """Current hydrological data from API."""

    station_id: str
    station_name: str
    river: Optional[str] = None
    province: Optional[str] = None
    water_level: Optional[float] = None
    water_level_date: Optional[str] = None
    flow: Optional[float] = None
    temperature: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class MeteoCurrentData(BaseModel):
    """Current meteorological data from API."""

    station_id: str
    station_name: str
    temperature: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[int] = None
    humidity: Optional[float] = None
    precipitation: Optional[float] = None
    pressure: Optional[float] = None
    measurement_date: Optional[str] = None


class WarningData(BaseModel):
    """Weather/hydro warning data."""

    id: str
    type: str
    level: Optional[int] = None
    region: Optional[str] = None
    description: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


# Health check
class HealthCheck(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"


# Cached hydro data schemas
class HydroDailyDataPoint(BaseModel):
    """Single daily measurement from cache."""

    date: str = Field(..., description="Measurement date (YYYY-MM-DD)")
    water_level_cm: Optional[float] = Field(None, description="Water level in cm")
    flow_m3s: Optional[float] = Field(None, description="Discharge in m3/s")
    water_temp_c: Optional[float] = Field(None, description="Water temperature in Celsius")


class HydroMonthlyDataPoint(BaseModel):
    """Single monthly measurement from cache."""

    year: int
    month: int
    extremum: str = Field(..., description="'min', 'mean', or 'max'")
    water_level_cm: Optional[float] = None
    flow_m3s: Optional[float] = None
    water_temp_c: Optional[float] = None


class HydroDataResponse(BaseModel):
    """Response with cached hydrological data."""

    station_id: str
    station_name: Optional[str] = None
    river: Optional[str] = None
    interval: str
    start_year: int
    end_year: int
    data: list[HydroDailyDataPoint | HydroMonthlyDataPoint]
    count: int
    source: str = Field(..., description="'cache' or 'imgw'")
