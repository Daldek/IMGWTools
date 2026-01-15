"""
Unit tests for imgwtools.fetch module.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from imgwtools.fetch import (
    fetch_pmaxtp,
    fetch_pmaxtp_async,
    fetch_hydro_current,
    fetch_hydro_current_async,
    fetch_synop,
    fetch_synop_async,
    fetch_warnings,
    download_hydro_data,
    download_meteo_data,
)
from imgwtools.models import PMaXTPResult, HydroCurrentData, SynopData, WarningData
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWValidationError,
)


class TestFetchPmaxtp:
    """Tests for fetch_pmaxtp function."""

    @patch("imgwtools.fetch.httpx.Client")
    def test_successful_fetch(self, mock_client, pmaxtp_api_response):
        """Test successful PMAXTP data fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = pmaxtp_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_pmaxtp(latitude=52.23, longitude=21.01, method="POT")

        assert isinstance(result, PMaXTPResult)
        assert result.method == "POT"
        assert result.latitude == 52.23
        assert result.longitude == 21.01
        assert result.data.get_precipitation(15, 50) == 5.1

    @patch("imgwtools.fetch.httpx.Client")
    def test_amp_method(self, mock_client, pmaxtp_api_response):
        """Test fetch with AMP method."""
        mock_response = MagicMock()
        mock_response.json.return_value = pmaxtp_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_pmaxtp(latitude=52.23, longitude=21.01, method="AMP")

        assert result.method == "AMP"

    def test_invalid_latitude(self):
        """Test validation error for invalid latitude."""
        with pytest.raises(IMGWValidationError) as exc_info:
            fetch_pmaxtp(latitude=100.0, longitude=21.01)

        assert "latitude" in str(exc_info.value).lower()

    def test_invalid_longitude(self):
        """Test validation error for invalid longitude."""
        with pytest.raises(IMGWValidationError) as exc_info:
            fetch_pmaxtp(latitude=52.23, longitude=200.0)

        assert "longitude" in str(exc_info.value).lower()

    def test_coordinates_outside_poland(self):
        """Test validation error for coordinates outside Poland."""
        with pytest.raises(IMGWValidationError) as exc_info:
            fetch_pmaxtp(latitude=40.0, longitude=21.01)

        assert "Poland" in str(exc_info.value) or "Polska" in str(exc_info.value)

    @patch("imgwtools.fetch.httpx.Client")
    def test_timeout_error(self, mock_client):
        """Test handling of timeout error."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = httpx.TimeoutException("timeout")
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        with pytest.raises(IMGWConnectionError):
            fetch_pmaxtp(latitude=52.23, longitude=21.01)


class TestFetchPmaxtpAsync:
    """Tests for async fetch_pmaxtp_async function."""

    @pytest.mark.asyncio
    @patch("imgwtools.fetch.httpx.AsyncClient")
    async def test_successful_async_fetch(self, mock_client, pmaxtp_api_response):
        """Test successful async PMAXTP data fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = pmaxtp_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = False
        mock_client.return_value = mock_client_instance

        result = await fetch_pmaxtp_async(latitude=52.23, longitude=21.01)

        assert isinstance(result, PMaXTPResult)
        assert result.latitude == 52.23


class TestFetchHydroCurrent:
    """Tests for fetch_hydro_current function."""

    @patch("imgwtools.fetch.httpx.Client")
    def test_fetch_all_stations(self, mock_client, hydro_current_api_response):
        """Test fetching all hydro stations."""
        mock_response = MagicMock()
        mock_response.json.return_value = hydro_current_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_hydro_current()

        assert len(result) == 2
        assert all(isinstance(s, HydroCurrentData) for s in result)
        assert result[0].station_id == "150160180"

    @patch("imgwtools.fetch.httpx.Client")
    def test_fetch_single_station(self, mock_client, hydro_current_api_response):
        """Test fetching single station by ID."""
        mock_response = MagicMock()
        mock_response.json.return_value = [hydro_current_api_response[0]]
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_hydro_current(station_id="150160180")

        assert len(result) == 1
        assert result[0].station_name == "Kłodzko"

    @patch("imgwtools.fetch.httpx.Client")
    def test_single_dict_response(self, mock_client, hydro_current_api_response):
        """Test handling single dict response (not list)."""
        mock_response = MagicMock()
        # API sometimes returns single object instead of list
        mock_response.json.return_value = hydro_current_api_response[0]
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_hydro_current(station_id="150160180")

        assert len(result) == 1


class TestFetchSynop:
    """Tests for fetch_synop function."""

    @patch("imgwtools.fetch.httpx.Client")
    def test_fetch_all_stations(self, mock_client, synop_api_response):
        """Test fetching all synop stations."""
        mock_response = MagicMock()
        mock_response.json.return_value = synop_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_synop()

        assert len(result) == 2
        assert all(isinstance(s, SynopData) for s in result)

    @patch("imgwtools.fetch.httpx.Client")
    def test_filter_by_station_name(self, mock_client, synop_api_response):
        """Test filtering by station name."""
        mock_response = MagicMock()
        mock_response.json.return_value = synop_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_synop(station_name="Warszawa")

        assert len(result) == 1
        assert result[0].station_name == "Warszawa"

    @patch("imgwtools.fetch.httpx.Client")
    def test_filter_case_insensitive(self, mock_client, synop_api_response):
        """Test case-insensitive station name filtering."""
        mock_response = MagicMock()
        mock_response.json.return_value = synop_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_synop(station_name="warszawa")

        assert len(result) == 1

    @patch("imgwtools.fetch.httpx.Client")
    def test_filter_partial_match(self, mock_client, synop_api_response):
        """Test partial station name matching."""
        mock_response = MagicMock()
        mock_response.json.return_value = synop_api_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_synop(station_name="Biały")

        assert len(result) == 1
        assert "Białystok" in result[0].station_name


class TestFetchWarnings:
    """Tests for fetch_warnings function."""

    @patch("imgwtools.fetch.httpx.Client")
    def test_fetch_hydro_warnings(self, mock_client):
        """Test fetching hydro warnings."""
        warnings_response = [
            {
                "id": "123",
                "typ": "hydro",
                "poziom": "2",
                "region": "dolnośląskie",
            }
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = warnings_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_warnings(warning_type="hydro")

        assert len(result) == 1
        assert isinstance(result[0], WarningData)

    @patch("imgwtools.fetch.httpx.Client")
    def test_fetch_meteo_warnings(self, mock_client):
        """Test fetching meteo warnings."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = fetch_warnings(warning_type="meteo")

        assert result == []


class TestDownloadHydroData:
    """Tests for download_hydro_data function."""

    @patch("imgwtools.fetch.httpx.Client")
    def test_download_daily_data(self, mock_client):
        """Test downloading daily hydro data."""
        mock_response = MagicMock()
        mock_response.content = b"ZIP_CONTENT"
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = download_hydro_data("dobowe", 2023)

        assert result == b"ZIP_CONTENT"

    @patch("imgwtools.fetch.httpx.Client")
    def test_download_with_month(self, mock_client):
        """Test downloading with month parameter."""
        mock_response = MagicMock()
        mock_response.content = b"ZIP_CONTENT"
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = download_hydro_data("dobowe", 2022, month=6)

        assert result == b"ZIP_CONTENT"


class TestDownloadMeteoData:
    """Tests for download_meteo_data function."""

    @patch("imgwtools.fetch.httpx.Client")
    def test_download_monthly_synop(self, mock_client):
        """Test downloading monthly synop data."""
        mock_response = MagicMock()
        mock_response.content = b"ZIP_CONTENT"
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        result = download_meteo_data("miesieczne", "synop", 2023)

        assert result == b"ZIP_CONTENT"
