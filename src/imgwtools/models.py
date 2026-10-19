"""
Public data models for IMGW data.

These models provide type-safe access to data returned by IMGW APIs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Flag = Literal["value", "missing", "no_phenomenon", "accumulated"]


@dataclass(frozen=True)
class Measurement:
    """
    Single measured value with its data-quality flag.

    Attributes
    ----------
    value : float or None
        Measured value; None when missing, ``0`` for ``"no_phenomenon"``.
    flag : {"value", "missing", "no_phenomenon", "accumulated"}
        ``"value"`` for a regular measurement, ``"missing"`` for no data,
        ``"no_phenomenon"`` when the phenomenon did not occur,
        ``"accumulated"`` for a sum covering preceding missing days.
    quality : int or None, optional
        ČHMÚ ``QUALITY`` code 0-5 (0 good, 1 suspect, 2 poor, 3 estimated,
        4 missing, 5 unknown), kept as published; it never changes ``value``
        or ``flag``. None when the source publishes no quality (IMGW-PIB,
        ČHMÚ hydrology) or leaves it empty.
    source_flag : str or None, optional
        ČHMÚ ``FLAG`` verbatim, also codes outside the ČHMÚ dictionary (e.g.
        ``"T"`` unmeasurable trace of precipitation, ``"M"`` manual gauge);
        None when absent.
    """

    value: float | None
    flag: Flag
    quality: int | None = None
    source_flag: str | None = None


@dataclass(frozen=True)
class NormalizedRecord:
    """
    Dataset-independent record of one station and one time unit.

    Attributes
    ----------
    station_code : str
        Station code: nine IMGW-PIB digits or a ČHMÚ WIGOS identifier
        (e.g. ``"0-203-1-001000"``).
    dataset : str
        Full dataset key, e.g. ``"pl.imgw.hydro_daily"`` or
        ``"cz.chmi.hydro_daily"``.
    date : date
        Calendar start of the time unit (day, first day of the month or
        start of the half-year period).
    hydro_year : int
        Hydrological year (November-October) of the unit.
    period : {"winter", "summer", "annual"} or None
        Half-year period for semi-annual data, None otherwise.
    measurements : Mapping of str to Measurement
        Values keyed by variable code, only for columns physically present
        in the input.
    attributes : Mapping of str to str or None, optional
        Qualitative attributes kept as text, e.g. ``"precip_type"``.
    extrema_dates : Mapping of str to tuple of (datetime or None, datetime or None), optional
        Start and end time of an extremum, keyed by variable column, e.g.
        ``"Q_max"``. When IMGW publishes several occurrences of the same
        extremum value, the earliest start and the latest end.
    extrema_occurrences : Mapping of str to int, optional
        Number of IMGW rows (occurrences of the extremum) merged into the
        value of a semi-annual column, keyed like ``extrema_dates``.
    """

    station_code: str
    dataset: str
    date: date
    hydro_year: int
    period: Literal["winter", "summer", "annual"] | None
    measurements: Mapping[str, Measurement]
    attributes: Mapping[str, str | None] = field(default_factory=dict)
    extrema_dates: Mapping[str, tuple[datetime | None, datetime | None]] = field(
        default_factory=dict
    )
    extrema_occurrences: Mapping[str, int] = field(default_factory=dict)


class PMaXTPData(BaseModel):
    """
    PMAXTP precipitation quantiles for all durations and probabilities.

    Each attribute is a nested dict of the form
    ``{duration: {probability: value}}``, where both keys are plain numbers
    written as strings: durations in minutes (e.g. "5", "10", "15", "30",
    "45", "60", "90", "120", "180") and probabilities in percent
    (e.g. "1", "2", "5", "10", "20", "50").

    Attributes
    ----------
    ks : dict of str to dict of str to float
        Precipitation quantiles [mm].
    sg : dict of str to dict of str to float
        Upper confidence bounds [mm].
    rb : dict of str to dict of str to float
        Estimation errors [mm].

    Examples
    --------
    >>> data.ks["15"]["50"]  # 15-min precipitation, 50% probability
    5.1
    """

    ks: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Kwantyle opadu maksymalnego [mm]",
    )
    sg: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Gorne granice przedzialu ufnosci [mm]",
    )
    rb: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Bledy estymacji kwantyli [mm]",
    )

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> PMaXTPData:
        """Parse raw API response into PMaXTPData."""
        # API returns data nested under "data" key
        if "data" in data:
            data = data["data"]
        return cls(
            ks=data.get("ks", {}),
            sg=data.get("sg", {}),
            rb=data.get("rb", {}),
        )

    def get_precipitation(
        self,
        duration_minutes: int,
        probability_percent: int,
    ) -> float | None:
        """
        Get precipitation value for given duration and probability.

        Parameters
        ----------
        duration_minutes : int
            Duration in minutes (5, 10, 15, 30, 45, 60, 90, 120, 180, etc.).
        probability_percent : int
            Probability in percent (1, 2, 5, 10, 20, 50, etc.).

        Returns
        -------
        float or None
            Precipitation in mm, or None if not available.

        Examples
        --------
        >>> data.get_precipitation(15, 50)
        5.1
        """
        duration_key = str(duration_minutes)
        prob_key = str(probability_percent)
        return self.ks.get(duration_key, {}).get(prob_key)

    def get_confidence_bound(
        self,
        duration_minutes: int,
        probability_percent: int,
    ) -> float | None:
        """Get upper confidence bound for given duration and probability."""
        duration_key = str(duration_minutes)
        prob_key = str(probability_percent)
        return self.sg.get(duration_key, {}).get(prob_key)

    def get_estimation_error(
        self,
        duration_minutes: int,
        probability_percent: int,
    ) -> float | None:
        """Get estimation error for given duration and probability."""
        duration_key = str(duration_minutes)
        prob_key = str(probability_percent)
        return self.rb.get(duration_key, {}).get(prob_key)

    def to_dataframe(self) -> Any:
        """
        Convert to pandas DataFrame.

        Requires pandas to be installed.

        Returns
        -------
        pandas.DataFrame
            DataFrame with columns: duration, probability, ks_mm, sg_mm, rb_mm.

        Raises
        ------
        ImportError
            If pandas is not installed.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_dataframe(). "
                "Install with: pip install imgwtools[pandas]"
            ) from e

        rows = []
        for duration, probs in self.ks.items():
            for prob, value in probs.items():
                rows.append(
                    {
                        "duration": duration,
                        "probability": prob,
                        "ks_mm": value,
                        "sg_mm": self.sg.get(duration, {}).get(prob),
                        "rb_mm": self.rb.get(duration, {}).get(prob),
                    }
                )
        return pd.DataFrame(rows)


class PMaXTPResult(BaseModel):
    """Complete PMAXTP result with metadata."""

    method: str = Field(description="Calculation method (POT or AMP)")
    latitude: float = Field(description="Latitude in decimal degrees")
    longitude: float = Field(description="Longitude in decimal degrees")
    data: PMaXTPData = Field(description="Precipitation data")


class HydroCurrentData(BaseModel):
    """
    Current hydrological measurement from IMGW API.

    Data comes from: https://danepubliczne.imgw.pl/api/data/hydro
    """

    station_code: str = Field(description="Station code")
    station_name: str = Field(description="Station name")
    river: str | None = Field(default=None, description="River name")
    province: str | None = Field(default=None, description="Province (wojewodztwo)")
    latitude: float | None = Field(default=None, description="Latitude (WGS84)")
    longitude: float | None = Field(default=None, description="Longitude (WGS84)")
    water_level_cm: float | None = Field(default=None, description="Water level [cm]")
    water_level_date: str | None = Field(
        default=None, description="Water level measurement date"
    )
    flow_m3s: float | None = Field(default=None, description="Flow [m3/s]")
    flow_date: str | None = Field(default=None, description="Flow measurement date")
    water_temp_c: float | None = Field(
        default=None, description="Water temperature [C]"
    )
    water_temp_date: str | None = Field(
        default=None, description="Temperature measurement date"
    )
    ice_phenomenon: str | None = Field(default=None, description="Ice phenomenon code")
    overgrowth: str | None = Field(default=None, description="Overgrowth code")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> HydroCurrentData:
        """
        Parse one record of the IMGW hydro endpoint.

        Parameters
        ----------
        data : dict
            Record with the API keys (``id_stacji``, ``stacja``, ``lat``,
            ``lon``, ``stan_wody``, ...).

        Returns
        -------
        HydroCurrentData
            Parsed measurement; unparsable numbers become None.
        """
        return cls(
            station_code=data.get("id_stacji", ""),
            station_name=data.get("stacja", ""),
            river=data.get("rzeka"),
            province=data.get("wojewodztwo", data.get("województwo")),
            latitude=_safe_float(data.get("lat")),
            longitude=_safe_float(data.get("lon")),
            water_level_cm=_safe_float(data.get("stan_wody")),
            water_level_date=data.get("stan_wody_data_pomiaru"),
            flow_m3s=_safe_float(data.get("przeplyw")),
            flow_date=data.get("przeplyw_data", data.get("przeplyw_data_pomiaru")),
            water_temp_c=_safe_float(data.get("temperatura_wody")),
            water_temp_date=data.get("temperatura_wody_data_pomiaru"),
            ice_phenomenon=data.get("zjawisko_lodowe"),
            overgrowth=data.get("zjawisko_zarastania"),
        )


class MeteoCurrentData(BaseModel):
    """
    Current measurement of an automatic meteorological station from IMGW API.

    Data comes from: https://danepubliczne.imgw.pl/api/data/meteo
    """

    station_code: str = Field(description="Station code")
    station_name: str = Field(description="Station name")
    latitude: float | None = Field(default=None, description="Latitude (WGS84)")
    longitude: float | None = Field(default=None, description="Longitude (WGS84)")
    air_temp_c: float | None = Field(default=None, description="Air temperature [C]")
    air_temp_date: str | None = Field(
        default=None, description="Air temperature measurement date"
    )
    wind_speed_ms: float | None = Field(
        default=None, description="Mean wind speed [m/s]"
    )
    humidity_percent: float | None = Field(
        default=None, description="Relative humidity [%]"
    )
    precipitation_10min_mm: float | None = Field(
        default=None, description="Precipitation over the last 10 minutes [mm]"
    )

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> MeteoCurrentData:
        """
        Parse one record of the IMGW meteo endpoint.

        Parameters
        ----------
        data : dict
            Record with the API keys (``kod_stacji``, ``nazwa_stacji``,
            ``lat``, ``lon``, ``temperatura_powietrza``, ...).

        Returns
        -------
        MeteoCurrentData
            Parsed measurement; a missing or unparsable value is None.
        """
        return cls(
            station_code=data.get("kod_stacji", ""),
            station_name=data.get("nazwa_stacji", ""),
            latitude=_safe_float(data.get("lat")),
            longitude=_safe_float(data.get("lon")),
            air_temp_c=_safe_float(data.get("temperatura_powietrza")),
            air_temp_date=data.get("temperatura_powietrza_data"),
            wind_speed_ms=_safe_float(data.get("wiatr_srednia_predkosc")),
            humidity_percent=_safe_float(data.get("wilgotnosc_wzgledna")),
            precipitation_10min_mm=_safe_float(data.get("opad_10min")),
        )


class SynopData(BaseModel):
    """
    Current synoptic measurement from IMGW API.

    Data comes from: https://danepubliczne.imgw.pl/api/data/synop
    """

    station_code: str = Field(description="Station code")
    station_name: str = Field(description="Station name")
    measurement_date: str | None = Field(default=None, description="Measurement date")
    measurement_hour: int | None = Field(default=None, description="Measurement hour")
    temperature_c: float | None = Field(default=None, description="Air temperature [C]")
    wind_speed_ms: float | None = Field(default=None, description="Wind speed [m/s]")
    wind_direction: int | None = Field(
        default=None, description="Wind direction [degrees]"
    )
    humidity_percent: float | None = Field(
        default=None, description="Relative humidity [%]"
    )
    precipitation_mm: float | None = Field(
        default=None, description="Total precipitation [mm]"
    )
    pressure_hpa: float | None = Field(
        default=None, description="Atmospheric pressure [hPa]"
    )
    visibility_m: int | None = Field(default=None, description="Visibility [m]")
    cloud_cover: int | None = Field(default=None, description="Cloud cover [octants]")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> SynopData:
        """
        Parse one record of the IMGW synop endpoint.

        Parameters
        ----------
        data : dict
            Record with the API keys (``id_stacji``, ``stacja``,
            ``temperatura``, ...).

        Returns
        -------
        SynopData
            Parsed measurement; unparsable numbers become None.
        """
        return cls(
            station_code=data.get("id_stacji", ""),
            station_name=data.get("stacja", ""),
            measurement_date=data.get("data_pomiaru"),
            measurement_hour=_safe_int(data.get("godzina_pomiaru")),
            temperature_c=_safe_float(data.get("temperatura")),
            wind_speed_ms=_safe_float(data.get("predkosc_wiatru")),
            wind_direction=_safe_int(data.get("kierunek_wiatru")),
            humidity_percent=_safe_float(data.get("wilgotnosc_wzgledna")),
            precipitation_mm=_safe_float(data.get("suma_opadu")),
            pressure_hpa=_safe_float(data.get("cisnienie")),
            visibility_m=_safe_int(data.get("widzialnosc")),
            cloud_cover=_safe_int(data.get("zachmurzenie_ogolne")),
        )


class WarningData(BaseModel):
    """
    Hydrological or meteorological warning from IMGW API.

    Data comes from: https://danepubliczne.imgw.pl/api/data/warningshydro
    and https://danepubliczne.imgw.pl/api/data/warningsmeteo
    """

    id: str = Field(description="Warning identifier (meteo id, hydro number)")
    kind: Literal["hydro", "meteo"] = Field(description="Warning family")
    event: str | None = Field(default=None, description="Event name")
    level: int | None = Field(default=None, description="Warning level")
    region: str | None = Field(default=None, description="Affected area")
    description: str | None = Field(default=None, description="Warning text")
    valid_from: str | None = Field(default=None, description="Valid from datetime")
    valid_to: str | None = Field(default=None, description="Valid to datetime")
    probability: int | None = Field(default=None, description="Probability [%]")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], *, kind: Literal["hydro", "meteo"]
    ) -> WarningData:
        """
        Parse one record of an IMGW warnings endpoint.

        Parameters
        ----------
        data : dict
            Record of ``warningsmeteo`` (``id``, ``nazwa_zdarzenia``,
            ``stopien``, ``obowiazuje_od``, ``tresc``, ``teryt``, ...) or
            ``warningshydro`` (``numer``, ``zdarzenie``, ``stopień``,
            ``data_od``, ``przebieg``, ``obszary``, ...).
        kind : {"hydro", "meteo"}
            Family of the endpoint the record comes from.

        Returns
        -------
        WarningData
            Parsed warning; the area is the comma-separated list of
            provinces (hydro) or TERYT codes (meteo).
        """
        return cls(
            id=str(data.get("id", data.get("numer", ""))),
            kind=kind,
            event=data.get("nazwa_zdarzenia", data.get("zdarzenie")),
            level=_safe_int(data.get("stopien", data.get("stopień"))),
            region=_warning_region(data),
            description=data.get("tresc", data.get("przebieg")),
            valid_from=data.get("obowiazuje_od", data.get("data_od")),
            valid_to=data.get("obowiazuje_do", data.get("data_do")),
            probability=_safe_int(data.get("prawdopodobienstwo")),
        )


class HydroState(BaseModel):
    """
    Hydrological station with its location and current water state.

    Data comes from the map API of https://hydro.imgw.pl
    (``hydro-back.imgw.pl/map/stations/hydrologic``).
    """

    station_code: str = Field(description="Station code")
    name: str = Field(description="Station name")
    river: str | None = Field(default=None, description="River name")
    latitude: float | None = Field(default=None, description="Latitude (WGS84)")
    longitude: float | None = Field(default=None, description="Longitude (WGS84)")
    water_state: str | None = Field(
        default=None,
        description="Water state (alarm, warning, high, medium, low, ...)",
    )


def _warning_region(data: Mapping[str, Any]) -> str | None:
    """Comma-separated provinces of ``obszary`` or TERYT codes of ``teryt``."""
    areas = data.get("obszary")
    if isinstance(areas, list):
        names = [
            str(area["wojewodztwo"])
            for area in areas
            if isinstance(area, dict) and area.get("wojewodztwo")
        ]
        return ", ".join(dict.fromkeys(names)) or None
    codes = data.get("teryt")
    if isinstance(codes, list):
        return ", ".join(str(code) for code in codes) or None
    return None


def _safe_float(value: Any) -> float | None:
    """Safely convert to float, returning None for invalid values."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int | None:
    """Safely convert to int, returning None for invalid values."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class StationListEntry:
    """
    One station of a provider station list (hydrological or meteorological).

    Attributes
    ----------
    kind : {"hydro", "meteo"}
        Station family of the list the row comes from.
    station_code : str
        Station code as text, kept verbatim (nine IMGW-PIB digits or a
        ČHMÚ WIGOS identifier).
    name : str
        Station name.
    river : str or None
        Hydro only: river name without the IMGW hydrographic code suffix;
        ČHMÚ ``STREAM_NAME``.
    hydrographic_code : str or None
        Hydro only: IMGW hydrographic code from the parentheses of the river
        column or ČHMÚ ``HLGP4`` (e.g. ``"1-05-02-0720"``), kept as text
        (leading zeros preserved).
    river_order : int or None
        Hydro only: fourth column of the IMGW list, without assigned
        hydrological meaning; None for ČHMÚ.
    short_code : str or None
        Meteo only: third column of the IMGW list (short station number),
        kept as text without surrounding whitespace; None for ČHMÚ.
    latitude : float or None
        Latitude (WGS84): for IMGW-PIB from the stored station catalog (None
        for live lists, stations without a location or a store without a
        catalog); for ČHMÚ as published in the station metadata, without
        validation against the country border.
    longitude : float or None
        Longitude (WGS84), as ``latitude``.
    provider : str, optional
        Provider identifier of the list: ``"IMGW-PIB"`` (default) or
        ``"CHMI"``.
    """

    kind: Literal["hydro", "meteo"]
    station_code: str
    name: str
    river: str | None = None
    hydrographic_code: str | None = None
    river_order: int | None = None
    short_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    provider: str = "IMGW-PIB"


class HydroArchiveStation(BaseModel):
    """Station metadata found in hydrological archive data CSV files."""

    station_code: str
    station_name: str
    river_name: str | None = None


class HydroDailyRecord(BaseModel):
    """
    Daily hydrological measurement from an IMGW archive CSV.

    Attributes
    ----------
    station_code : str
        Station code.
    station_name : str or None
        Station name.
    river_name : str or None
        River name.
    hydro_year : int
        Hydrological year (November-October).
    hydro_month : int
        Hydrological month 1-12 (1 = November, 12 = October).
    day : int
        Day of the month (1-31).
    calendar_month : int or None
        Calendar month 1-12 from the archive, if present.
    water_level_cm : float or None
        Water level [cm]; None when missing.
    flow_m3s : float or None
        Flow [m3/s]; None when missing.
    water_temp_c : float or None
        Water temperature [degC]; None when missing.
    measurement_date : str or None
        Calendar date in ISO format, None if it cannot be determined.
    """

    station_code: str
    station_name: str | None = None
    river_name: str | None = None
    hydro_year: int
    hydro_month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    calendar_month: int | None = Field(default=None, ge=1, le=12)
    water_level_cm: float | None = None
    flow_m3s: float | None = None
    water_temp_c: float | None = None
    measurement_date: str | None = None


class HydroMonthlyRecord(BaseModel):
    """
    Monthly hydrological extremum from an IMGW archive CSV.

    Attributes
    ----------
    station_code : str
        Station code.
    station_name : str or None
        Station name.
    river_name : str or None
        River name.
    hydro_year : int
        Hydrological year (November-October).
    hydro_month : int
        Hydrological month 1-12 (1 = November, 12 = October).
    calendar_month : int or None
        Calendar month 1-12 from the archive, if present.
    extremum : str
        Statistic of the values: ``"min"``, ``"mean"`` or ``"max"``.
    water_level_cm : float or None
        Water level [cm]; None when missing.
    flow_m3s : float or None
        Flow [m3/s]; None when missing.
    water_temp_c : float or None
        Water temperature [degC]; None when missing.
    """

    station_code: str
    station_name: str | None = None
    river_name: str | None = None
    hydro_year: int
    hydro_month: int = Field(ge=1, le=12)
    calendar_month: int | None = Field(default=None, ge=1, le=12)
    extremum: str
    water_level_cm: float | None = None
    flow_m3s: float | None = None
    water_temp_c: float | None = None


class HydroSemiAnnualRecord(BaseModel):
    """
    Semi-annual or annual hydrological extremum from an IMGW archive CSV.

    Attributes
    ----------
    station_code : str
        Station code.
    station_name : str or None
        Station name.
    river_name : str or None
        River name.
    hydro_year : int
        Hydrological year (November-October).
    period : str
        ``"winter"`` (November-April), ``"summer"`` (May-October) or
        ``"annual"`` (whole hydrological year).
    param : str
        Parameter: ``"H"`` (water level), ``"Q"`` (flow) or ``"T"`` (water
        temperature).
    extremum : str
        Statistic of the value: ``"min"``, ``"mean"`` or ``"max"``.
    value : float or None
        Value of the statistic; None when missing.
    extremum_start_date : str or None
        Start of the extremum as ``YYYY-MM-DD`` with ``HH:MM`` when IMGW
        publishes the hour; a month or day missing in the source is the first
        of the published unit. None for means or when unknown.
    extremum_end_date : str or None
        End of the extremum in the same format; None for means or when
        unknown.
    """

    station_code: str
    station_name: str | None = None
    river_name: str | None = None
    hydro_year: int
    period: str
    param: str
    extremum: str
    value: float | None = None
    extremum_start_date: str | None = None
    extremum_end_date: str | None = None
