"""
Unit tests for imgwtools.models module.
"""

import pytest

from imgwtools.models import (
    PMaXTPData,
    PMaXTPResult,
    HydroCurrentData,
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

    def test_from_api_response(self, hydro_current_api_response):
        """Test parsing hydro current API response."""
        raw = hydro_current_api_response[0]
        data = HydroCurrentData.from_api_response(raw)

        assert data.station_id == "150160180"
        assert data.station_name == "Kłodzko"
        assert data.river == "Nysa Kłodzka"
        assert data.province == "dolnośląskie"
        assert data.water_level_cm == 106.0
        assert data.flow_m3s == 5.2
        assert data.water_temp_c == 4.5

    def test_from_api_response_with_nulls(self, hydro_current_api_response):
        """Test parsing response with null values."""
        raw = hydro_current_api_response[1]
        data = HydroCurrentData.from_api_response(raw)

        assert data.station_id == "151140030"
        assert data.water_level_cm == 230.0
        assert data.flow_m3s is None
        assert data.water_temp_c is None

    def test_from_api_response_invalid_values(self):
        """Test handling invalid values in response."""
        raw = {
            "id_stacji": "123",
            "stacja": "Test",
            "stan_wody": "invalid",
            "przeplyw": "not_a_number",
        }
        data = HydroCurrentData.from_api_response(raw)

        assert data.station_id == "123"
        assert data.water_level_cm is None
        assert data.flow_m3s is None


class TestSynopData:
    """Tests for SynopData model."""

    def test_from_api_response(self, synop_api_response):
        """Test parsing synop API response."""
        raw = synop_api_response[0]
        data = SynopData.from_api_response(raw)

        assert data.station_id == "12375"
        assert data.station_name == "Warszawa"
        assert data.temperature_c == 2.5
        assert data.wind_speed_ms == 3.0
        assert data.wind_direction == 180
        assert data.humidity_percent == 75.5
        assert data.precipitation_mm == 0.0
        assert data.pressure_hpa == 1015.2

    def test_from_api_response_negative_temp(self, synop_api_response):
        """Test parsing response with negative temperature."""
        raw = synop_api_response[1]
        data = SynopData.from_api_response(raw)

        assert data.station_name == "Białystok"
        assert data.temperature_c == -5.0

    def test_from_api_response_missing_fields(self):
        """Test handling missing fields in response."""
        raw = {
            "id_stacji": "12345",
            "stacja": "Test",
        }
        data = SynopData.from_api_response(raw)

        assert data.station_id == "12345"
        assert data.station_name == "Test"
        assert data.temperature_c is None
        assert data.pressure_hpa is None


class TestWarningData:
    """Tests for WarningData model."""

    def test_from_api_response(self):
        """Test parsing warning API response."""
        raw = {
            "id": "123",
            "typ": "hydro",
            "poziom": "2",
            "region": "dolnośląskie",
            "opis": "Ostrzeżenie o wzroście stanu wody",
            "wazne_od": "2024-01-15 12:00:00",
            "wazne_do": "2024-01-16 12:00:00",
            "prawdopodobienstwo": "80",
        }
        data = WarningData.from_api_response(raw)

        assert data.id == "123"
        assert data.warning_type == "hydro"
        assert data.level == 2
        assert data.region == "dolnośląskie"
        assert data.probability == 80

    def test_from_api_response_alternative_keys(self):
        """Test parsing with alternative key names."""
        raw = {
            "id": "456",
            "nazwa": "meteo",
            "stopien": "3",
            "obszar": "mazowieckie",
            "tresc": "Burze z gradem",
            "od": "2024-01-15",
            "do": "2024-01-16",
        }
        data = WarningData.from_api_response(raw)

        assert data.id == "456"
        assert data.warning_type == "meteo"
        assert data.level == 3
        assert data.region == "mazowieckie"
        assert data.description == "Burze z gradem"
