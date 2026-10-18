"""
Unit tests for imgwtools.fetch module.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWValidationError,
)
from imgwtools.fetch import (
    DownloadResult,
    download_hydro_data,
    download_hydro_data_async,
    download_meteo_data,
    download_meteo_data_async,
    fetch_hydro_current,
    fetch_pmaxtp,
    fetch_pmaxtp_async,
    fetch_synop,
    fetch_warnings,
)
from imgwtools.models import HydroCurrentData, PMaXTPResult, SynopData, WarningData


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

    @pytest.mark.parametrize(
        ("payload", "expected", "match"),
        [
            (
                {"data": {}, "error": "Brak pliku, pradopodobnie poza obszarem PL"},
                IMGWValidationError,
                "poza siatką PMAXTP",
            ),
            ({"data": {}, "error": "Awaria"}, IMGWDataError, "Awaria"),
            ({"data": {}}, IMGWDataError, "bez danych"),
        ],
    )
    @patch("imgwtools.fetch.httpx.Client")
    def test_api_error_body_is_not_a_result(
        self, mock_client, payload, expected, match
    ):
        """An API error or empty body raises instead of returning empty tables."""
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        with pytest.raises(expected, match=match):
            fetch_pmaxtp(latitude=54.7104, longitude=20.4522)


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

    @pytest.mark.asyncio
    @patch("imgwtools.fetch.httpx.AsyncClient")
    async def test_outside_grid_is_validation_error(self, mock_client):
        """The async variant maps the outside-grid API error like the sync one."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {},
            "error": "Brak pliku, pradopodobnie poza obszarem PL",
        }
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = False
        mock_client.return_value = mock_client_instance

        with pytest.raises(IMGWValidationError):
            await fetch_pmaxtp_async(latitude=49.8397, longitude=24.0297)


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


STORE = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
HYDRO_ZIP = STORE / "dane_hydrologiczne/dobowe/2024/codz_2024.zip"
METEO_ZIP = STORE / "dane_meteorologiczne/dobowe/opad/2001/2001_01_o.zip"


@pytest.mark.parametrize(
    "archive,arguments",
    [
        (HYDRO_ZIP, ("dobowe", 2024)),
        (METEO_ZIP, ("dobowe", "opad", 2001, 1)),
    ],
)
@pytest.mark.asyncio
async def test_download_provenance_sync_and_async(monkeypatch, archive, arguments):
    payload = archive.read_bytes()
    headers = {
        "ETag": '"same-get"',
        "Last-Modified": "Sat, 17 Oct 2026 12:00:00 GMT",
        "Content-Length": str(len(payload)),
    }
    calls = []

    def handler(http_request):
        calls.append(str(http_request.url))
        return httpx.Response(200, content=payload, headers=headers)

    transport = httpx.MockTransport(handler)
    original_sync = httpx.Client
    original_async = httpx.AsyncClient
    monkeypatch.setattr(
        "imgwtools.fetch.httpx.Client",
        lambda **kwargs: original_sync(transport=transport, **kwargs),
    )
    monkeypatch.setattr(
        "imgwtools.fetch.httpx.AsyncClient",
        lambda **kwargs: original_async(transport=transport, **kwargs),
    )
    sync = (
        download_hydro_data(*arguments)
        if archive == HYDRO_ZIP
        else download_meteo_data(*arguments)
    )
    async_result = await (
        download_hydro_data_async(*arguments)
        if archive == HYDRO_ZIP
        else download_meteo_data_async(*arguments)
    )
    assert (
        sync
        == async_result
        == DownloadResult(
            payload, calls[0], '"same-get"', headers["Last-Modified"], len(payload)
        )
    )
    assert len(calls) == 2


@pytest.mark.parametrize(
    "headers, expected",
    [
        ({}, None),
        ({"Content-Length": "103"}, 103),
    ],
)
def test_missing_headers_remain_none(monkeypatch, headers, expected):
    original = httpx.Client
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, stream=httpx.ByteStream(HYDRO_ZIP.read_bytes()), headers=headers
        )
    )
    monkeypatch.setattr(
        "imgwtools.fetch.httpx.Client",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    result = download_hydro_data("dobowe", 2024)
    assert result.etag is result.last_modified is None
    assert result.content_length == expected


@pytest.mark.parametrize(
    "response, exception",
    [
        (httpx.Response(404), IMGWConnectionError),
        (httpx.Response(200, content=b"not a ZIP"), IMGWDataError),
    ],
)
def test_download_rejects_http_and_corrupt_archive(monkeypatch, response, exception):
    original = httpx.Client
    monkeypatch.setattr(
        "imgwtools.fetch.httpx.Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda _: response), **kwargs
        ),
    )
    with pytest.raises(exception):
        download_hydro_data("dobowe", 2024)


@pytest.mark.asyncio
async def test_async_timeout_is_connection_error(monkeypatch):
    original = httpx.AsyncClient

    def fail(request):
        raise httpx.TimeoutException("timeout", request=request)

    monkeypatch.setattr(
        "imgwtools.fetch.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(fail), **kwargs),
    )
    with pytest.raises(IMGWConnectionError, match="Przekroczono czas"):
        await download_meteo_data_async("dobowe", "opad", 2001, 1)
