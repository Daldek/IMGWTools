"""
Pydantic models for database records.

These models represent data structures for hydrological measurements
and station metadata stored in the SQLite cache.
"""

from datetime import date

from pydantic import BaseModel, Field


class HydroStation(BaseModel):
    """Hydrological station metadata."""

    station_code: str = Field(..., description="Station code (e.g., '150160180')")
    station_name: str = Field(..., description="Station name")
    river_name: str | None = Field(None, description="River or lake name")
    latitude: float | None = Field(None, description="Latitude in decimal degrees")
    longitude: float | None = Field(None, description="Longitude in decimal degrees")


class HydroDailyRecord(BaseModel):
    """Daily hydrological measurement record."""

    station_code: str
    station_name: str | None = None
    river_name: str | None = None
    hydro_year: int = Field(..., description="Hydrological year (Nov-Oct)")
    hydro_month: int = Field(..., ge=1, le=12, description="Month in hydro year (1=Nov, 12=Oct)")
    day: int = Field(..., ge=1, le=31)
    calendar_month: int | None = Field(None, ge=1, le=12)
    water_level_cm: float | None = Field(None, description="Water level in cm")
    flow_m3s: float | None = Field(None, description="Discharge in m3/s")
    water_temp_c: float | None = Field(None, description="Water temperature in Celsius")
    measurement_date: str | None = Field(None, description="Date in YYYY-MM-DD format")


class HydroMonthlyRecord(BaseModel):
    """Monthly hydrological measurement record."""

    station_code: str
    station_name: str | None = None
    river_name: str | None = None
    hydro_year: int
    hydro_month: int = Field(..., ge=1, le=12)
    calendar_month: int | None = Field(None, ge=1, le=12)
    extremum: str = Field(..., description="'min', 'mean', or 'max'")
    water_level_cm: float | None = None
    flow_m3s: float | None = None
    water_temp_c: float | None = None


class HydroSemiAnnualRecord(BaseModel):
    """Semi-annual or annual hydrological measurement record."""

    station_code: str
    station_name: str | None = None
    river_name: str | None = None
    hydro_year: int
    period: str = Field(..., description="'winter', 'summer', or 'annual'")
    param: str = Field(..., description="'H' (level), 'Q' (flow), or 'T' (temp)")
    extremum: str = Field(..., description="'min', 'mean', or 'max'")
    value: float | None = None
    extremum_start_date: str | None = None
    extremum_end_date: str | None = None


class CachedRange(BaseModel):
    """Record of cached data range."""

    id: int | None = None
    interval: str = Field(..., description="'dobowe', 'miesieczne', or 'polroczne'")
    year: int
    month: int | None = None
    param: str | None = None
    source_file: str
    cached_at: str
    record_count: int | None = None


# Constants for missing data detection
MISSING_WATER_LEVEL = 9999
MISSING_FLOW = 99999.999
MISSING_TEMP = 99.9

# Mapping for extremum indicator
EXTREMUM_MAP = {
    1: "min",
    2: "mean",
    3: "max",
}

# Mapping for period indicator (semi-annual data)
PERIOD_MAP = {
    13: "winter",  # Nov 1 - Apr 30
    14: "summer",  # May 1 - Oct 31
    15: "annual",  # Full hydrological year
}

# Mapping for hydro month to calendar month
# Hydro year starts in November (month 1 = November)
HYDRO_TO_CALENDAR_MONTH = {
    1: 11,   # November
    2: 12,   # December
    3: 1,    # January
    4: 2,    # February
    5: 3,    # March
    6: 4,    # April
    7: 5,    # May
    8: 6,    # June
    9: 7,    # July
    10: 8,   # August
    11: 9,   # September
    12: 10,  # October
}


def hydro_to_calendar_date(hydro_year: int, hydro_month: int, day: int) -> date:
    """
    Convert hydrological date to calendar date.

    Args:
        hydro_year: Hydrological year (e.g., 2020 means Nov 2019 - Oct 2020)
        hydro_month: Month in hydro year (1=Nov, 12=Oct)
        day: Day of month

    Returns:
        Calendar date.
    """
    calendar_month = HYDRO_TO_CALENDAR_MONTH[hydro_month]

    # Determine calendar year
    # Months 1-2 (Nov-Dec) belong to previous calendar year
    if hydro_month <= 2:
        calendar_year = hydro_year - 1
    else:
        calendar_year = hydro_year

    return date(calendar_year, calendar_month, day)


def is_missing_value(value: float | None, value_type: str) -> bool:
    """
    Check if a value represents missing data.

    Args:
        value: The value to check.
        value_type: Type of measurement ('level', 'flow', or 'temp').

    Returns:
        True if the value indicates missing data.
    """
    if value is None:
        return True

    if value_type == "level":
        return value == MISSING_WATER_LEVEL
    elif value_type == "flow":
        return abs(value - MISSING_FLOW) < 0.001
    elif value_type == "temp":
        return abs(value - MISSING_TEMP) < 0.01

    return False
