"""
Station listing and lookup functions.

Provides access to hydrological and meteorological station data from IMGW.
"""

from __future__ import annotations

import csv
import io
import re
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, Field

from imgwtools.exceptions import IMGWConnectionError

if TYPE_CHECKING:
    pass

# URLs for station data
HYDRO_STATIONS_CSV_URL = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    "dane_hydrologiczne/lista_stacji_hydro.csv"
)
METEO_STATIONS_CSV_URL = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    "dane_meteorologiczne/wykaz_stacji.csv"
)
HYDRO_MAP_API_URL = "https://hydro-back.imgw.pl/map/stations/hydrologic"

# Default encoding for IMGW CSV files
IMGW_ENCODING = "cp1250"

DEFAULT_TIMEOUT = 30.0


class HydroStation(BaseModel):
    """
    Hydrological station metadata.

    Attributes:
        station_id: Unique station identifier (kod stacji).
        name: Station name.
        river: River or lake name (optional).
        latitude: Latitude in decimal degrees (optional, from map API).
        longitude: Longitude in decimal degrees (optional, from map API).
        water_state: Current water state status (optional, from map API).
            Values: 'alarm', 'warning', 'high', 'medium', 'low', etc.
    """

    model_config = ConfigDict(populate_by_name=True)

    station_id: str = Field(alias="station_code")
    name: str = Field(alias="station_name")
    river: str | None = Field(None, alias="river_name")
    latitude: float | None = None
    longitude: float | None = None
    water_state: str | None = Field(
        None,
        description="Current state: alarm, warning, high, medium, low",
    )


class MeteoStation(BaseModel):
    """
    Meteorological station metadata.

    Attributes:
        station_id: Unique station identifier.
        name: Station name.
    """

    station_id: str
    name: str


def list_hydro_stations(
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroStation]:
    """
    List all hydrological stations from IMGW CSV.

    Returns basic station info without coordinates.
    For coordinates and water state, use get_hydro_stations_with_coords().

    Args:
        timeout: Request timeout in seconds.

    Returns:
        List of HydroStation objects.

    Raises:
        IMGWConnectionError: If connection to IMGW fails.

    Example:
        >>> stations = list_hydro_stations()
        >>> print(len(stations))  # ~900 stations
        >>> print(stations[0].name)
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(HYDRO_STATIONS_CSV_URL)
            response.raise_for_status()
            content = response.content.decode(IMGW_ENCODING)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"Timeout fetching station list: {e}") from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Failed to fetch station list: {e}") from e

    return _parse_hydro_stations_csv(content)


async def list_hydro_stations_async(
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroStation]:
    """
    Async version of list_hydro_stations.

    See list_hydro_stations for documentation.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(HYDRO_STATIONS_CSV_URL)
            response.raise_for_status()
            content = response.content.decode(IMGW_ENCODING)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"Timeout fetching station list: {e}") from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Failed to fetch station list: {e}") from e

    return _parse_hydro_stations_csv(content)


def get_hydro_stations_with_coords(
    *,
    include_all: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroStation]:
    """
    Get hydrological stations with coordinates and current water state.

    Uses hydro-back.imgw.pl API which provides lat/lon and water state.
    This is the recommended method for getting station locations.

    Args:
        include_all: If True, include secondary stations (default).
                    If False, only main stations.
        timeout: Request timeout in seconds.

    Returns:
        List of HydroStation with coordinates and water_state.

    Raises:
        IMGWConnectionError: If connection fails.

    Example:
        >>> stations = get_hydro_stations_with_coords()
        >>> alarmed = [s for s in stations if s.water_state == "alarm"]
        >>> for s in alarmed:
        ...     print(f"{s.name}: {s.latitude}, {s.longitude}")
    """
    params = {"onlyMainStations": "false" if include_all else "true"}
    headers = {
        "User-Agent": "IMGWTools/2.0",
        "Referer": "https://hydro.imgw.pl/",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(HYDRO_MAP_API_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"Timeout fetching stations: {e}") from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Failed to fetch stations: {e}") from e

    return _parse_map_stations_response(data)


async def get_hydro_stations_with_coords_async(
    *,
    include_all: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroStation]:
    """
    Async version of get_hydro_stations_with_coords.

    See get_hydro_stations_with_coords for documentation.
    """
    params = {"onlyMainStations": "false" if include_all else "true"}
    headers = {
        "User-Agent": "IMGWTools/2.0",
        "Referer": "https://hydro.imgw.pl/",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(
                HYDRO_MAP_API_URL, params=params, headers=headers
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"Timeout fetching stations: {e}") from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Failed to fetch stations: {e}") from e

    return _parse_map_stations_response(data)


def list_meteo_stations(
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MeteoStation]:
    """
    List all meteorological stations from IMGW CSV.

    Args:
        timeout: Request timeout in seconds.

    Returns:
        List of MeteoStation objects.

    Raises:
        IMGWConnectionError: If connection fails.

    Example:
        >>> stations = list_meteo_stations()
        >>> print(len(stations))
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(METEO_STATIONS_CSV_URL)
            response.raise_for_status()
            content = response.content.decode(IMGW_ENCODING)
    except httpx.TimeoutException as e:
        raise IMGWConnectionError(f"Timeout fetching station list: {e}") from e
    except httpx.HTTPError as e:
        raise IMGWConnectionError(f"Failed to fetch station list: {e}") from e

    return _parse_meteo_stations_csv(content)


async def list_meteo_stations_async(
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MeteoStation]:
    """
    Async version of list_meteo_stations.

    See list_meteo_stations for documentation.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(METEO_STATIONS_CSV_URL)
            response.raise_for_status()
            content = response.content.decode(IMGW_ENCODING)
        except httpx.TimeoutException as e:
            raise IMGWConnectionError(f"Timeout fetching station list: {e}") from e
        except httpx.HTTPError as e:
            raise IMGWConnectionError(f"Failed to fetch station list: {e}") from e

    return _parse_meteo_stations_csv(content)


def _parse_hydro_stations_csv(content: str) -> list[HydroStation]:
    """Parse hydro stations CSV content."""
    stations = []
    reader = csv.reader(io.StringIO(content))

    for row in reader:
        if len(row) < 2:
            continue

        try:
            station_id = row[0].strip().strip('"')
            name = row[1].strip().strip('"')

            river = None
            if len(row) > 2:
                river_raw = row[2].strip().strip('"')
                # Parse "Odra (1)" format - extract river name
                match = re.match(r"^(.+?)\s*\(\d+\)$", river_raw)
                if match:
                    river = match.group(1).strip()
                else:
                    river = river_raw if river_raw else None

            stations.append(
                HydroStation(
                    station_code=station_id,
                    station_name=name,
                    river_name=river,
                )
            )
        except (IndexError, ValueError):
            continue

    return stations


def _parse_meteo_stations_csv(content: str) -> list[MeteoStation]:
    """Parse meteo stations CSV content."""
    stations = []
    reader = csv.reader(io.StringIO(content))

    for row in reader:
        if len(row) < 2:
            continue

        try:
            station_id = row[0].strip().strip('"')
            name = row[1].strip().strip('"')

            stations.append(
                MeteoStation(
                    station_id=station_id,
                    name=name,
                )
            )
        except (IndexError, ValueError):
            continue

    return stations


def _parse_map_stations_response(data: dict | list) -> list[HydroStation]:
    """Parse response from hydro-back.imgw.pl map API."""
    stations = []

    # API returns {"stations": [...]} wrapper
    if isinstance(data, dict):
        station_list = data.get("stations", [])
    else:
        station_list = data

    for item in station_list:
        try:
            # API uses short keys: n=name, la=latitude, lo=longitude, s=state
            stations.append(
                HydroStation(
                    station_code=str(item.get("id", "")),
                    station_name=item.get("n", item.get("name", "")),
                    river_name=item.get("riverName"),
                    latitude=item.get("la", item.get("lat")),
                    longitude=item.get("lo", item.get("lon")),
                    water_state=item.get("s", item.get("waterStateStatus")),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    return stations
