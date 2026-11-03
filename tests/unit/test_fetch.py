"""
Unit tests for the archive downloads of imgwtools.fetch (respx-mocked HTTP).

Live reads are covered by test_fetch_live.py, ``download_archives`` by
test_download_archives.py.
"""

import io
import zipfile

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
)

ARCHIVE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
HYDRO = f"{ARCHIVE}/dane_hydrologiczne"
METEO = f"{ARCHIVE}/dane_meteorologiczne"
HYDRO_DAILY = f"{HYDRO}/dobowe/2020/codz_2020_03.zip"
METEO_MONTHLY = f"{METEO}/miesieczne/klimat/2023/2023_m_k.zip"


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dane.csv", "149190310,SAN ESCOBAR\n")
    return buffer.getvalue()


# Golden URLs recorded from build_hydro_url/build_meteo_url before the registry cutover.
GOLDEN = [
    ("hydro", ("dobowe", 2023, 13), f"{HYDRO}/dobowe/2023/zjaw_2023.zip"),
    ("hydro", ("dobowe", 2022, 3), f"{HYDRO}/dobowe/2022/codz_2022_03.zip"),
    ("hydro", ("dobowe", 2024), f"{HYDRO}/dobowe/2024/codz_2024.zip"),
    ("hydro", ("miesieczne", 2024), f"{HYDRO}/miesieczne/2024/mies_2024.zip"),
    (
        "hydro",
        ("polroczne_i_roczne", 2020, None, "Q"),
        f"{HYDRO}/polroczne_i_roczne/2020/polr_Q_2020.zip",
    ),
    (
        "meteo",
        ("miesieczne", "synop", 1995),
        f"{METEO}/miesieczne/synop/1991_1995/1991_1995_m_s.zip",
    ),
    ("meteo", ("miesieczne", "klimat", 2023), METEO_MONTHLY),
    (
        "meteo",
        ("terminowe", "klimat", 2001, 1),
        f"{METEO}/terminowe/klimat/2001/2001_01_k.zip",
    ),
    ("meteo", ("dobowe", "opad", 1995), f"{METEO}/dobowe/opad/1991_1995/1995_o.zip"),
]


def _download(family, arguments):
    return (download_hydro_data if family == "hydro" else download_meteo_data)(
        *arguments
    )


def _download_async(family, arguments):
    function = (
        download_hydro_data_async if family == "hydro" else download_meteo_data_async
    )
    return function(*arguments)


@pytest.mark.parametrize("family, arguments, url", GOLDEN)
async def test_legacy_arguments_hit_the_same_urls_sync_and_async(
    respx_mock, family, arguments, url
):
    payload = _zip_bytes()
    headers = {"ETag": '"e"', "Last-Modified": "Sat, 17 Oct 2026 12:00:00 GMT"}
    route = respx_mock.get(url).respond(content=payload, headers=headers)
    expected = DownloadResult(
        payload, url, '"e"', headers["Last-Modified"], len(payload)
    )
    assert _download(family, arguments) == expected
    assert await _download_async(family, arguments) == expected
    assert route.call_count == 2


def test_missing_headers_remain_none(respx_mock):
    respx_mock.get(HYDRO_DAILY).mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(_zip_bytes()))
    )
    result = download_hydro_data("dobowe", 2020, 3)
    assert (result.etag, result.last_modified, result.content_length) == (
        None,
        None,
        None,
    )


def test_redirect_is_followed_and_final_url_reported(respx_mock):
    final = "https://mirror.example/codz_2020_03.zip"
    respx_mock.get(HYDRO_DAILY).respond(302, headers={"Location": final})
    respx_mock.get(final).respond(content=_zip_bytes())
    assert download_hydro_data("dobowe", 2020, 3).url == final


@pytest.mark.parametrize(
    "function, arguments, option",
    [
        (download_hydro_data, ("dobowe", 2020), "month"),
        (download_hydro_data, ("polroczne_i_roczne", 2020), "param"),
        (download_meteo_data, ("dobowe", "klimat", 2001), "month"),
        (download_meteo_data, ("terminowe", "klimat", 2004), "month"),
        (download_hydro_data, ("dobowe", "2020", 3), "year"),
    ],
)
def test_ambiguous_legacy_arguments_are_validation_errors(
    respx_mock, function, arguments, option
):
    with pytest.raises(IMGWValidationError) as error:
        function(*arguments)
    assert error.value.code == "validation_error"
    assert error.value.details["option"] == option
    assert not respx_mock.calls


@pytest.mark.parametrize(
    "arguments, reason",
    [
        (("terminowe", "opad", 2023, 1), "not_published"),
        (("dobowe", "synop", 2023, 1), "per_station"),
        (("terminowe", "synop", 2023, 1), "per_station"),
    ],
)
async def test_unpublished_meteo_combinations_fail_before_request(
    respx_mock, arguments, reason
):
    with pytest.raises(IMGWValidationError) as error:
        download_meteo_data(*arguments)
    assert error.value.details["reason"] == reason
    with pytest.raises(IMGWValidationError):
        await download_meteo_data_async(*arguments)
    assert not respx_mock.calls


def test_unknown_interval_lists_registry_keys(respx_mock):
    with pytest.raises(IMGWValidationError) as error:
        download_hydro_data("roczne", 2020)
    assert "pl.imgw.hydro_daily" in error.value.details["allowed"]


@pytest.mark.parametrize(
    "mock, reason, status",
    [
        ({"side_effect": httpx.ReadTimeout}, "timeout", None),
        ({"side_effect": httpx.ConnectError}, "network", None),
        ({"return_value": httpx.Response(404)}, "http_status", 404),
    ],
    ids=["timeout", "network", "http_status"],
)
async def test_download_failure_is_source_unavailable(respx_mock, mock, reason, status):
    respx_mock.get(METEO_MONTHLY).mock(**mock)
    with pytest.raises(IMGWConnectionError) as sync_error:
        download_meteo_data("miesieczne", "klimat", 2023)
    with pytest.raises(IMGWConnectionError) as async_error:
        await download_meteo_data_async("miesieczne", "klimat", 2023)
    for error in (sync_error.value, async_error.value):
        assert error.code == "source_unavailable"
        assert error.details["url"] == METEO_MONTHLY
        assert error.details["reason"] == reason
        assert error.details.get("status") == status


@pytest.mark.parametrize(
    "response, message",
    [
        (httpx.Response(200, content=b"<html>"), "Invalid ZIP archive"),
        (
            httpx.Response(
                200,
                stream=httpx.ByteStream(_zip_bytes()),
                headers={"Content-Length": "duzo"},
            ),
            "Invalid Content-Length header",
        ),
    ],
)
def test_corrupt_download_is_data_error(respx_mock, response, message):
    respx_mock.get(HYDRO_DAILY).mock(return_value=response)
    with pytest.raises(IMGWDataError, match=message) as error:
        download_hydro_data("dobowe", 2020, 3)
    assert error.value.code == "data_error"
