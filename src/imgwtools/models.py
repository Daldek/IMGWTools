"""
Public data models for IMGW data.

These models provide type-safe access to data returned by IMGW APIs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PMaXTPData(BaseModel):
    """
    PMAXTP precipitation quantiles for all durations and probabilities.

    Structure:
        ks: Precipitation quantiles [mm]
        sg: Upper confidence bounds [mm]
        rb: Estimation errors [mm]

    Each contains nested dicts: {duration: {probability: value}}
    Durations: t15, t30, t45, t60, t90, t120, t180 (minutes)
    Probabilities: p1, p2, p5, p10, p20, p50 (percent)

    Example:
        >>> data.ks["t15"]["p50"]  # 15-min precipitation, 50% probability
        23.5
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

        Args:
            duration_minutes: Duration in minutes (5, 10, 15, 30, 45, 60, 90, 120, 180, etc.)
            probability_percent: Probability in percent (1, 2, 5, 10, 20, 50, etc.)

        Returns:
            Precipitation in mm, or None if not available.

        Example:
            >>> data.get_precipitation(15, 50)
            13.34
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

        Returns:
            DataFrame with columns: duration, probability, ks_mm, sg_mm, rb_mm

        Raises:
            ImportError: If pandas is not installed.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_dataframe(). "
                "Install with: pip install imgwtools[spatial]"
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

    station_id: str = Field(description="Station identifier")
    station_name: str = Field(description="Station name")
    river: str | None = Field(None, description="River name")
    province: str | None = Field(None, description="Province (wojewodztwo)")
    water_level_cm: float | None = Field(None, description="Water level [cm]")
    water_level_date: str | None = Field(None, description="Water level measurement date")
    flow_m3s: float | None = Field(None, description="Flow [m3/s]")
    flow_date: str | None = Field(None, description="Flow measurement date")
    water_temp_c: float | None = Field(None, description="Water temperature [C]")
    water_temp_date: str | None = Field(None, description="Temperature measurement date")
    ice_phenomenon: str | None = Field(None, description="Ice phenomenon code")
    overgrowth: str | None = Field(None, description="Overgrowth code")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> HydroCurrentData:
        """Parse raw API response from IMGW hydro endpoint."""
        return cls(
            station_id=data.get("id_stacji", ""),
            station_name=data.get("stacja", ""),
            river=data.get("rzeka"),
            province=data.get("województwo"),
            water_level_cm=_safe_float(data.get("stan_wody")),
            water_level_date=data.get("stan_wody_data_pomiaru"),
            flow_m3s=_safe_float(data.get("przeplyw")),
            flow_date=data.get("przeplyw_data_pomiaru"),
            water_temp_c=_safe_float(data.get("temperatura_wody")),
            water_temp_date=data.get("temperatura_wody_data_pomiaru"),
            ice_phenomenon=data.get("zjawisko_lodowe"),
            overgrowth=data.get("zjawisko_zarastania"),
        )


class SynopData(BaseModel):
    """
    Current synoptic measurement from IMGW API.

    Data comes from: https://danepubliczne.imgw.pl/api/data/synop
    """

    station_id: str = Field(description="Station identifier")
    station_name: str = Field(description="Station name")
    measurement_date: str | None = Field(None, description="Measurement date")
    measurement_hour: int | None = Field(None, description="Measurement hour")
    temperature_c: float | None = Field(None, description="Air temperature [C]")
    wind_speed_ms: float | None = Field(None, description="Wind speed [m/s]")
    wind_direction: int | None = Field(None, description="Wind direction [degrees]")
    humidity_percent: float | None = Field(None, description="Relative humidity [%]")
    precipitation_mm: float | None = Field(None, description="Total precipitation [mm]")
    pressure_hpa: float | None = Field(None, description="Atmospheric pressure [hPa]")
    visibility_m: int | None = Field(None, description="Visibility [m]")
    cloud_cover: int | None = Field(None, description="Cloud cover [octants]")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> SynopData:
        """Parse raw API response from IMGW synop endpoint."""
        return cls(
            station_id=data.get("id_stacji", ""),
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
    Weather or hydro warning from IMGW API.

    Data comes from IMGW warnings endpoints.
    """

    id: str = Field(description="Warning identifier")
    warning_type: str = Field(description="Warning type")
    level: int | None = Field(None, description="Warning level (1-3)")
    region: str | None = Field(None, description="Affected region")
    description: str | None = Field(None, description="Warning description")
    valid_from: str | None = Field(None, description="Valid from datetime")
    valid_to: str | None = Field(None, description="Valid to datetime")
    probability: int | None = Field(None, description="Probability [%]")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> WarningData:
        """Parse raw API response from IMGW warnings endpoint."""
        return cls(
            id=str(data.get("id", "")),
            warning_type=data.get("typ", data.get("nazwa", "")),
            level=_safe_int(data.get("poziom", data.get("stopien"))),
            region=data.get("region", data.get("obszar")),
            description=data.get("opis", data.get("tresc")),
            valid_from=data.get("wazne_od", data.get("od")),
            valid_to=data.get("wazne_do", data.get("do")),
            probability=_safe_int(data.get("prawdopodobienstwo")),
        )


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
