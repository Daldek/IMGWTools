"""
Unit tests for imgwtools.models module.
"""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from imgwtools.models import (
    HydroCurrentData,
    Measurement,
    MeteoCurrentData,
    NormalizedRecord,
    PMaXTPData,
    PMaXTPResult,
    SynopData,
    WarningData,
)


class TestPMaXTPData:
    """Tests for PMaXTPData model."""

    def test_from_api_response_with_data_wrapper(self, pmaxtp_api_response):
        """Test parsing API response with 'data' wrapper."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)

        assert data.ks is not None
        assert data.sg is not None
        assert data.rb is not None
        assert "15" in data.ks
        assert "50" in data.ks["15"]

    def test_from_api_response_without_wrapper(self):
        """Test parsing API response without 'data' wrapper."""
        raw = {
            "ks": {"15": {"50": 13.34}},
            "sg": {"15": {"50": 14.0}},
            "rb": {"15": {"50": 0.5}},
        }
        data = PMaXTPData.from_api_response(raw)

        assert data.ks["15"]["50"] == 13.34

    def test_get_precipitation(self, pmaxtp_api_response):
        """Test get_precipitation method."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)

        # Test existing value
        result = data.get_precipitation(15, 50)
        assert result == 5.1

        # Test another existing value
        result = data.get_precipitation(60, 10)
        assert result == 16.5

    def test_get_precipitation_missing_duration(self, pmaxtp_api_response):
        """Test get_precipitation returns None for missing duration."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)

        result = data.get_precipitation(999, 50)
        assert result is None

    def test_get_precipitation_missing_probability(self, pmaxtp_api_response):
        """Test get_precipitation returns None for missing probability."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)

        result = data.get_precipitation(15, 999)
        assert result is None

    def test_get_confidence_bound(self, pmaxtp_api_response):
        """Test get_confidence_bound method."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)

        result = data.get_confidence_bound(15, 50)
        assert result == 5.4

    def test_get_estimation_error(self, pmaxtp_api_response):
        """Test get_estimation_error method."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)

        result = data.get_estimation_error(15, 50)
        assert result == 0.3

    def test_empty_data(self):
        """Test handling empty data."""
        data = PMaXTPData()

        assert data.ks == {}
        assert data.sg == {}
        assert data.rb == {}
        assert data.get_precipitation(15, 50) is None


class TestPMaXTPResult:
    """Tests for PMaXTPResult model."""

    def test_create_result(self, pmaxtp_api_response):
        """Test creating PMaXTPResult."""
        data = PMaXTPData.from_api_response(pmaxtp_api_response)
        result = PMaXTPResult(
            method="POT",
            latitude=52.23,
            longitude=21.01,
            data=data,
        )

        assert result.method == "POT"
        assert result.latitude == 52.23
        assert result.longitude == 21.01
        assert result.data.get_precipitation(15, 50) == 5.1


class TestHydroCurrentData:
    """Tests for HydroCurrentData model."""

    def test_reads_station_code_and_coordinates(self):
        data = HydroCurrentData.from_api_response(
            {
                "id_stacji": "149190310",
                "stacja": "SAN ESCOBAR",
                "rzeka": "Raba",
                "wojewodztwo": "małopolskie",
                "lat": "49.6100",
                "lon": "20.0500",
                "stan_wody": "212",
                "przeplyw": "12.3",
                "przeplyw_data": "2026-10-18 06:10:00",
            }
        )

        assert (data.station_code, data.station_name, data.river) == (
            "149190310",
            "SAN ESCOBAR",
            "Raba",
        )
        assert (data.latitude, data.longitude) == (49.61, 20.05)
        assert (data.water_level_cm, data.flow_m3s, data.flow_date) == (
            212.0,
            12.3,
            "2026-10-18 06:10:00",
        )

    def test_invalid_or_missing_values_are_none(self):
        data = HydroCurrentData.from_api_response(
            {"id_stacji": "149190311", "stacja": "SAN ESCOBAR", "stan_wody": "brak"}
        )

        assert data.station_code == "149190311"
        assert (data.latitude, data.longitude, data.water_level_cm) == (
            None,
            None,
            None,
        )


class TestMeteoCurrentData:
    """Tests for MeteoCurrentData model."""

    def test_maps_api_keys(self):
        data = MeteoCurrentData.from_api_response(
            {
                "kod_stacji": "249190310",
                "nazwa_stacji": "SAN ESCOBAR",
                "lat": "49.995556",
                "lon": "18.919167",
                "temperatura_powietrza": "10.4",
                "temperatura_powietrza_data": "2026-10-18 16:10:00",
                "wiatr_srednia_predkosc": "3.2",
                "wilgotnosc_wzgledna": "81.5",
                "opad_10min": "0.2",
            }
        )

        assert data.model_dump() == {
            "station_code": "249190310",
            "station_name": "SAN ESCOBAR",
            "latitude": 49.995556,
            "longitude": 18.919167,
            "air_temp_c": 10.4,
            "air_temp_date": "2026-10-18 16:10:00",
            "wind_speed_ms": 3.2,
            "humidity_percent": 81.5,
            "precipitation_10min_mm": 0.2,
        }

    def test_missing_or_null_values_are_none(self):
        data = MeteoCurrentData.from_api_response(
            {
                "kod_stacji": "249190311",
                "nazwa_stacji": "RABA GÓRNA",
                "temperatura_powietrza": None,
                "opad_10min": "0",
            }
        )

        assert (
            data.latitude,
            data.air_temp_c,
            data.air_temp_date,
            data.wind_speed_ms,
            data.humidity_percent,
            data.precipitation_10min_mm,
        ) == (None, None, None, None, None, 0.0)


class TestSynopData:
    """Tests for SynopData model."""

    def test_reads_station_code_and_values(self):
        data = SynopData.from_api_response(
            {
                "id_stacji": "12999",
                "stacja": "SAN ESCOBAR",
                "godzina_pomiaru": "12",
                "temperatura": "-5.0",
                "predkosc_wiatru": "3",
                "cisnienie": "1015.2",
            }
        )

        assert (data.station_code, data.station_name) == ("12999", "SAN ESCOBAR")
        assert (data.measurement_hour, data.temperature_c, data.wind_speed_ms) == (
            12,
            -5.0,
            3.0,
        )
        assert (data.pressure_hpa, data.humidity_percent) == (1015.2, None)


class TestWarningData:
    """Tests for WarningData model."""

    def test_meteo_record(self):
        data = WarningData.from_api_response(
            {
                "id": "77",
                "nazwa_zdarzenia": "Silny wiatr",
                "stopien": "2",
                "prawdopodobienstwo": "80",
                "obowiazuje_od": "2026-10-18 06:00:00",
                "obowiazuje_do": "2026-10-19 06:00:00",
                "tresc": "Porywy do 90 km/h",
                "teryt": ["1261", "1262"],
            },
            kind="meteo",
        )

        assert data.model_dump() == {
            "id": "77",
            "kind": "meteo",
            "event": "Silny wiatr",
            "level": 2,
            "region": "1261, 1262",
            "description": "Porywy do 90 km/h",
            "valid_from": "2026-10-18 06:00:00",
            "valid_to": "2026-10-19 06:00:00",
            "probability": 80,
        }

    def test_hydro_record(self):
        data = WarningData.from_api_response(
            {
                "numer": "21",
                "zdarzenie": "Wezbranie z przekroczeniem stanów ostrzegawczych",
                "stopień": "1",
                "data_od": "2026-10-18 08:00:00",
                "data_do": "2026-10-20 08:00:00",
                "prawdopodobienstwo": "90",
                "przebieg": "Wzrost stanów wody na Rabie",
                "obszary": [
                    {"wojewodztwo": "małopolskie", "opis": "Raba"},
                    {"wojewodztwo": "małopolskie", "opis": "Skawa"},
                    {"wojewodztwo": "śląskie", "opis": "Soła"},
                ],
            },
            kind="hydro",
        )

        assert (data.id, data.kind, data.event, data.level) == (
            "21",
            "hydro",
            "Wezbranie z przekroczeniem stanów ostrzegawczych",
            1,
        )
        assert (data.region, data.description) == (
            "małopolskie, śląskie",
            "Wzrost stanów wody na Rabie",
        )
        assert (data.valid_from, data.valid_to, data.probability) == (
            "2026-10-18 08:00:00",
            "2026-10-20 08:00:00",
            90,
        )


def test_normalized_measurement_flag_and_record_are_frozen():
    record = NormalizedRecord(
        station_code="123456789",
        dataset="pl.imgw.hydro_daily",
        date=date(2024, 2, 29),
        hydro_year=2024,
        period=None,
        measurements={
            "Q": Measurement(None, "missing"),
            "H": Measurement(12.0, "value"),
        },
    )
    assert record.measurements["Q"].value is None
    assert record.measurements["H"].value == 12.0
    with pytest.raises(FrozenInstanceError):
        record.hydro_year = 2025
    with pytest.raises(FrozenInstanceError):
        record.measurements["Q"].flag = "value"
