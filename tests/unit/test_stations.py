"""
Unit tests for imgwtools.stations module.
"""

import pytest
from unittest.mock import patch, MagicMock

from imgwtools.stations import (
    list_hydro_stations,
    list_hydro_stations_async,
    get_hydro_stations_with_coords,
    get_hydro_stations_with_coords_async,
    list_meteo_stations,
    list_meteo_stations_async,
    HydroStation,
    MeteoStation,
    _parse_hydro_stations_csv,
    _parse_meteo_stations_csv,
    _parse_map_stations_response,
)
from imgwtools.exceptions import IMGWConnectionError


class TestParseHydroStationsCsv:
    """Tests for CSV parsing of hydro stations."""

    def test_parse_basic_csv(self, hydro_stations_csv):
        """Test parsing basic hydro stations CSV."""
        stations = _parse_hydro_stations_csv(hydro_stations_csv)

        assert len(stations) == 3
        assert stations[0].station_id == "149180020"
        assert stations[0].name == "CHAŁUPKI"
        assert stations[0].river == "Odra"

    def test_parse_river_with_id_suffix(self):
        """Test parsing river name with (id) suffix."""
        csv = '"123","Station Name","Wisła (5)"'
        stations = _parse_hydro_stations_csv(csv)

        assert stations[0].river == "Wisła"

    def test_parse_empty_river(self):
        """Test parsing station without river."""
        csv = '"123","Station Name",""'
        stations = _parse_hydro_stations_csv(csv)

        assert stations[0].river is None

    def test_parse_missing_columns(self):
        """Test handling CSV with missing columns."""
        csv = '"123","Station Name"'
        stations = _parse_hydro_stations_csv(csv)

        assert len(stations) == 1
        assert stations[0].river is None

    def test_parse_empty_csv(self):
        """Test parsing empty CSV."""
        stations = _parse_hydro_stations_csv("")

        assert len(stations) == 0


class TestParseMeteoStationsCsv:
    """Tests for CSV parsing of meteo stations."""

    def test_parse_basic_csv(self):
        """Test parsing basic meteo stations CSV."""
        csv = '"12375","Warszawa"\n"12295","Białystok"'
        stations = _parse_meteo_stations_csv(csv)

        assert len(stations) == 2
        assert stations[0].station_id == "12375"
        assert stations[0].name == "Warszawa"


class TestParseMapStationsResponse:
    """Tests for parsing hydro-back.imgw.pl API response."""

    def test_parse_with_stations_wrapper(self, map_stations_api_response):
        """Test parsing response with 'stations' wrapper."""
        stations = _parse_map_stations_response(map_stations_api_response)

        assert len(stations) == 3
        assert stations[0].station_id == "150160180"
        assert stations[0].name == "Kłodzko"
        assert stations[0].latitude == 50.4333
        assert stations[0].longitude == 16.6500
        assert stations[0].water_state == "low"

    def test_parse_alarm_station(self, map_stations_api_response):
        """Test parsing station with alarm state."""
        stations = _parse_map_stations_response(map_stations_api_response)

        alarm_station = next(s for s in stations if s.water_state == "alarm")
        assert alarm_station.name == "Chałupki"

    def test_parse_list_response(self):
        """Test parsing response as direct list (without wrapper)."""
        data = [
            {"id": "123", "n": "Test", "la": 50.0, "lo": 19.0, "s": "medium"}
        ]
        stations = _parse_map_stations_response(data)

        assert len(stations) == 1
        assert stations[0].station_id == "123"

    def test_parse_with_alternative_keys(self):
        """Test parsing with long key names."""
        data = [
            {
                "id": "123",
                "name": "Test Station",
                "lat": 50.0,
                "lon": 19.0,
                "waterStateStatus": "high",
            }
        ]
        stations = _parse_map_stations_response(data)

        assert stations[0].name == "Test Station"
        assert stations[0].latitude == 50.0
        assert stations[0].water_state == "high"


class TestListHydroStations:
    """Tests for list_hydro_stations function."""

    @patch("imgwtools.stations.httpx.Client")
    def test_successful_fetch(self, mock_client, hydro_stations_csv):
        """Test successful fetch of hydro stations."""
        mock_response = MagicMock()
        mock_response.content = hydro_stations_csv.encode("cp1250")
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        stations = list_hydro_stations()

        assert len(stations) == 3
        assert isinstance(stations[0], HydroStation)

    @patch("imgwtools.stations.httpx.Client")
    def test_timeout_error(self, mock_client):
        """Test handling timeout error."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = httpx.TimeoutException("timeout")
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        with pytest.raises(IMGWConnectionError) as exc_info:
            list_hydro_stations()

        assert "Timeout" in str(exc_info.value)


class TestGetHydroStationsWithCoords:
    """Tests for get_hydro_stations_with_coords function."""

    @patch("imgwtools.stations.httpx.Client")
    def test_successful_fetch(self, mock_client, map_stations_api_response):
        """Test successful fetch of stations with coordinates."""
        mock_response = MagicMock()
        mock_response.json.return_value = map_stations_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        stations = get_hydro_stations_with_coords()

        assert len(stations) == 3
        assert stations[0].latitude is not None
        assert stations[0].longitude is not None

    @patch("imgwtools.stations.httpx.Client")
    def test_include_all_parameter(self, mock_client, map_stations_api_response):
        """Test include_all parameter is passed correctly."""
        mock_response = MagicMock()
        mock_response.json.return_value = map_stations_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        get_hydro_stations_with_coords(include_all=False)

        # Check that the correct parameter was passed
        call_args = mock_client_instance.get.call_args
        assert call_args[1]["params"]["onlyMainStations"] == "true"


class TestHydroStationModel:
    """Tests for HydroStation model."""

    def test_create_with_aliases(self):
        """Test creating HydroStation with field aliases."""
        station = HydroStation(
            station_code="123",
            station_name="Test",
            river_name="Wisła",
        )

        assert station.station_id == "123"
        assert station.name == "Test"
        assert station.river == "Wisła"

    def test_create_with_coordinates(self):
        """Test creating HydroStation with coordinates."""
        station = HydroStation(
            station_code="123",
            station_name="Test",
            latitude=50.0,
            longitude=19.0,
            water_state="alarm",
        )

        assert station.latitude == 50.0
        assert station.longitude == 19.0
        assert station.water_state == "alarm"


class TestMeteoStationModel:
    """Tests for MeteoStation model."""

    def test_create_station(self):
        """Test creating MeteoStation."""
        station = MeteoStation(
            station_id="12375",
            name="Warszawa",
        )

        assert station.station_id == "12375"
        assert station.name == "Warszawa"
