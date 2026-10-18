"""
Unit tests for the archive downloads of imgwtools.fetch.

Live reads are covered by test_fetch_live.py.
"""

from pathlib import Path

import httpx
import pytest

from imgwtools.exceptions import IMGWConnectionError, IMGWDataError
from imgwtools.fetch import (
    DownloadResult,
    download_hydro_data,
    download_hydro_data_async,
    download_meteo_data,
    download_meteo_data_async,
)

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
