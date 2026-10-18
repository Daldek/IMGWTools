"""Offline tests for live IMGW fetch functions (respx-mocked HTTP)."""

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
    download_hydro_data,
    download_hydro_data_async,
    download_meteo_data,
    download_meteo_data_async,
    fetch_hydro_current,
    fetch_hydro_current_async,
    fetch_pmaxtp,
    fetch_pmaxtp_async,
    fetch_synop,
    fetch_synop_async,
    fetch_warnings,
    fetch_warnings_async,
)

API = "https://danepubliczne.imgw.pl/api/data"
PMAXTP = "https://powietrze.imgw.pl/tpmax-api/point"
ARCHIVE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
HYDRO_POLR_Q = f"{ARCHIVE}/dane_hydrologiczne/polroczne_i_roczne/2020/polr_Q_2020.zip"
HYDRO_DAILY = f"{ARCHIVE}/dane_hydrologiczne/dobowe/2020/codz_2020_03.zip"
METEO_MONTHLY = f"{ARCHIVE}/dane_meteorologiczne/miesieczne/klimat/2023/2023_m_k.zip"

HYDRO_ITEM = {
    "id_stacji": "149190310",
    "stacja": "Raba Górna",
    "rzeka": "Raba",
    "stan_wody": "212",
    "przeplyw": "brak",
}
SYNOP_ITEMS = [
    {"id_stacji": "12999", "stacja": "SAN ESCOBAR", "temperatura": "7.5"},
    {"id_stacji": "12998", "stacja": "Raba Górna", "temperatura": "-1.0"},
]


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dane.csv", "149190310,SAN ESCOBAR\n")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# PMAXTP
# --------------------------------------------------------------------------


@pytest.mark.parametrize("latitude", [49.0, 55.0])
def test_fetch_pmaxtp_latitude_bounds_are_inclusive(respx_mock, latitude):
    route = respx_mock.get(f"{PMAXTP}/P/KS/{latitude:.4f}/20.0000").respond(
        json={"data": {"ks": {"15": {"50": 4.2}}}}
    )
    result = fetch_pmaxtp(latitude, 20.0)
    assert route.called
    assert result.data.get_precipitation(15, 50) == 4.2


@pytest.mark.parametrize(
    "latitude, longitude, word",
    [(48.99, 20.0, "Latitude"), (52.0, 24.51, "Longitude"), (52.0, 13.99, "Longitude")],
)
def test_fetch_pmaxtp_rejects_coords_outside_poland_before_request(
    respx_mock, latitude, longitude, word
):
    with pytest.raises(IMGWValidationError, match=word):
        fetch_pmaxtp(latitude, longitude)
    assert not respx_mock.calls


def test_fetch_pmaxtp_validate_coords_false_sends_request(respx_mock):
    route = respx_mock.get(f"{PMAXTP}/A/KS/40.0000/10.0000").respond(json={})
    result = fetch_pmaxtp(40.0, 10.0, method="AMP", validate_coords=False)
    assert route.called
    assert result.method == "AMP"
    assert result.data.ks == {}


@pytest.mark.parametrize(
    "response, exception, message",
    [
        (
            httpx.Response(503, text="przerwa"),
            IMGWConnectionError,
            "error 503: przerwa",
        ),
        (
            httpx.Response(200, text="<html>"),
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
        (
            httpx.Response(200, json={"data": {"ks": "zle"}}),
            IMGWDataError,
            "Failed to parse PMAXTP",
        ),
    ],
)
def test_fetch_pmaxtp_maps_bad_responses(respx_mock, response, exception, message):
    respx_mock.get(f"{PMAXTP}/P/KS/52.0000/20.0000").mock(return_value=response)
    with pytest.raises(exception, match=message):
        fetch_pmaxtp(52.0, 20.0)


def test_fetch_pmaxtp_connect_error_is_connection_error(respx_mock):
    respx_mock.get(f"{PMAXTP}/P/KS/52.0000/20.0000").mock(
        side_effect=httpx.ConnectError
    )
    with pytest.raises(IMGWConnectionError, match="Connection error"):
        fetch_pmaxtp(52.0, 20.0)


async def test_fetch_pmaxtp_async_returns_parsed_result(
    respx_mock, pmaxtp_api_response
):
    respx_mock.get(f"{PMAXTP}/A/KS/50.1000/19.9000").respond(json=pmaxtp_api_response)
    result = await fetch_pmaxtp_async(50.1, 19.9, method="AMP")
    assert (result.method, result.latitude, result.longitude) == ("AMP", 50.1, 19.9)
    assert result.data.get_precipitation(60, 1) == 28.4


async def test_fetch_pmaxtp_async_rejects_coords_before_request(respx_mock):
    with pytest.raises(IMGWValidationError):
        await fetch_pmaxtp_async(56.0, 20.0)
    assert not respx_mock.calls


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Connection error"),
        (
            {"return_value": httpx.Response(404, text="brak")},
            IMGWConnectionError,
            "error 404: brak",
        ),
        (
            {"return_value": httpx.Response(200, text="nie-json")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
        (
            {"return_value": httpx.Response(200, json={"ks": [1]})},
            IMGWDataError,
            "Failed to parse PMAXTP",
        ),
    ],
)
async def test_fetch_pmaxtp_async_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(f"{PMAXTP}/P/KS/52.0000/20.0000").mock(**mock)
    with pytest.raises(exception, match=message):
        await fetch_pmaxtp_async(52.0, 20.0)


# --------------------------------------------------------------------------
# Hydro current
# --------------------------------------------------------------------------


def test_fetch_hydro_current_reads_live_api_record_keys(respx_mock):
    respx_mock.get(f"{API}/hydro").respond(
        json=[
            {
                "id_stacji": "149190310",
                "stacja": "SAN ESCOBAR",
                "rzeka": "Raba",
                "wojewodztwo": "małopolskie",
                "lon": "20.0500",
                "lat": "49.6100",
                "stan_wody": "212",
                "stan_wody_data_pomiaru": "2026-10-18 06:00:00",
                "temperatura_wody": "8.1",
                "temperatura_wody_data_pomiaru": "2026-10-18 05:00:00",
                "przeplyw": "12.3",
                "przeplyw_data": "2026-10-18 06:10:00",
                "zjawisko_lodowe": "0",
                "zjawisko_lodowe_data_pomiaru": None,
                "zjawisko_zarastania": "0",
                "zjawisko_zarastania_data_pomiaru": None,
            }
        ]
    )
    [station] = fetch_hydro_current()
    assert (station.province, station.flow_m3s, station.flow_date) == (
        "małopolskie",
        12.3,
        "2026-10-18 06:10:00",
    )


def test_fetch_hydro_current_station_id_targets_station_endpoint(respx_mock):
    respx_mock.get(f"{API}/hydro/id/149190310").respond(json=HYDRO_ITEM)
    [station] = fetch_hydro_current("149190310")
    assert station.station_name == "Raba Górna"
    assert station.water_level_cm == 212.0
    assert station.flow_m3s is None


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        (
            {"return_value": httpx.Response(500)},
            IMGWConnectionError,
            "Connection error",
        ),
        (
            {"return_value": httpx.Response(200, text="<html>")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
        (
            {"return_value": httpx.Response(200, json=["149190310"])},
            IMGWDataError,
            "Failed to parse hydro",
        ),
    ],
)
def test_fetch_hydro_current_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(f"{API}/hydro").mock(**mock)
    with pytest.raises(exception, match=message):
        fetch_hydro_current()


async def test_fetch_hydro_current_async_wraps_single_object(respx_mock):
    respx_mock.get(f"{API}/hydro/id/149190310").respond(json=HYDRO_ITEM)
    result = await fetch_hydro_current_async("149190310")
    assert [s.station_id for s in result] == ["149190310"]


async def test_fetch_hydro_current_async_returns_all_stations(
    respx_mock, hydro_current_api_response
):
    respx_mock.get(f"{API}/hydro").respond(json=hydro_current_api_response)
    result = await fetch_hydro_current_async()
    assert [s.water_level_cm for s in result] == [106.0, 230.0]


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Connection error"),
        (
            {"return_value": httpx.Response(200, text="{")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
        (
            {"return_value": httpx.Response(200, json=[1, 2])},
            IMGWDataError,
            "Failed to parse hydro",
        ),
    ],
)
async def test_fetch_hydro_current_async_maps_failures(
    respx_mock, mock, exception, message
):
    respx_mock.get(f"{API}/hydro").mock(**mock)
    with pytest.raises(exception, match=message):
        await fetch_hydro_current_async()


# --------------------------------------------------------------------------
# Synop
# --------------------------------------------------------------------------


def test_fetch_synop_station_id_targets_station_endpoint(respx_mock):
    respx_mock.get(f"{API}/synop/id/12999").respond(json=SYNOP_ITEMS[0])
    [station] = fetch_synop(station_id="12999")
    assert (station.station_name, station.temperature_c) == ("SAN ESCOBAR", 7.5)


def test_fetch_synop_name_filter_without_match_returns_empty(respx_mock):
    respx_mock.get(f"{API}/synop").respond(json=SYNOP_ITEMS)
    assert fetch_synop(station_name="Atlantyda") == []


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        (
            {"return_value": httpx.Response(502)},
            IMGWConnectionError,
            "Connection error",
        ),
        (
            {"return_value": httpx.Response(200, text="x")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
        (
            {"return_value": httpx.Response(200, json=["12999"])},
            IMGWDataError,
            "Failed to parse synop",
        ),
    ],
)
def test_fetch_synop_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(f"{API}/synop").mock(**mock)
    with pytest.raises(exception, match=message):
        fetch_synop()


async def test_fetch_synop_async_filters_by_name_case_insensitive(respx_mock):
    respx_mock.get(f"{API}/synop").respond(json=SYNOP_ITEMS)
    result = await fetch_synop_async(station_name="raba")
    assert [s.station_id for s in result] == ["12998"]


async def test_fetch_synop_async_station_id_wraps_single_object(respx_mock):
    respx_mock.get(f"{API}/synop/id/12998").respond(json=SYNOP_ITEMS[1])
    result = await fetch_synop_async(station_id="12998")
    assert [s.temperature_c for s in result] == [-1.0]


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        (
            {"return_value": httpx.Response(404)},
            IMGWConnectionError,
            "Connection error",
        ),
        (
            {"return_value": httpx.Response(200, text="x")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
        (
            {"return_value": httpx.Response(200, json=[None])},
            IMGWDataError,
            "Failed to parse synop",
        ),
    ],
)
async def test_fetch_synop_async_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(f"{API}/synop").mock(**mock)
    with pytest.raises(exception, match=message):
        await fetch_synop_async()


# --------------------------------------------------------------------------
# Warnings
# --------------------------------------------------------------------------


def test_fetch_warnings_meteo_parses_alternative_keys(respx_mock):
    respx_mock.get(f"{API}/warnings/meteo").respond(
        json=[
            {
                "id": 77,
                "nazwa": "Silny wiatr",
                "stopien": "2",
                "obszar": "SAN ESCOBAR",
                "tresc": "Porywy do 90 km/h",
                "od": "2026-10-18 06:00",
                "do": "2026-10-19 06:00",
                "prawdopodobienstwo": "80",
            }
        ]
    )
    [warning] = fetch_warnings("meteo")
    assert warning.model_dump() == {
        "id": "77",
        "warning_type": "Silny wiatr",
        "level": 2,
        "region": "SAN ESCOBAR",
        "description": "Porywy do 90 km/h",
        "valid_from": "2026-10-18 06:00",
        "valid_to": "2026-10-19 06:00",
        "probability": 80,
    }


def test_fetch_warnings_hydro_wraps_single_object(respx_mock):
    respx_mock.get(f"{API}/warnings/hydro").respond(
        json={"id": "h1", "typ": "Wezbranie", "poziom": "3", "opis": "Raba Górna"}
    )
    [warning] = fetch_warnings("hydro")
    assert (warning.id, warning.level, warning.description) == ("h1", 3, "Raba Górna")


@pytest.mark.parametrize("body", [b"null", b"{}", b"[]"])
def test_fetch_warnings_empty_payload_returns_empty_list(respx_mock, body):
    respx_mock.get(f"{API}/warnings/hydro").respond(content=body)
    assert fetch_warnings() == []


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        (
            {"return_value": httpx.Response(500)},
            IMGWConnectionError,
            "Connection error",
        ),
        (
            {"return_value": httpx.Response(200, text="<html>")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
    ],
)
def test_fetch_warnings_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(f"{API}/warnings/meteo").mock(**mock)
    with pytest.raises(exception, match=message):
        fetch_warnings("meteo")


async def test_fetch_warnings_async_parses_list_and_single_object(respx_mock):
    respx_mock.get(f"{API}/warnings/meteo").respond(
        json=[{"id": 1, "typ": "Burze", "poziom": "1"}]
    )
    respx_mock.get(f"{API}/warnings/hydro").respond(json={"id": 2, "typ": "Susza"})
    meteo = await fetch_warnings_async("meteo")
    hydro = await fetch_warnings_async("hydro")
    assert [(w.id, w.warning_type, w.level) for w in meteo + hydro] == [
        ("1", "Burze", 1),
        ("2", "Susza", None),
    ]


async def test_fetch_warnings_async_empty_payload_returns_empty_list(respx_mock):
    respx_mock.get(f"{API}/warnings/hydro").respond(json=[])
    assert await fetch_warnings_async() == []


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "timeout"),
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Connection error"),
        (
            {"return_value": httpx.Response(200, text="<html>")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
    ],
)
async def test_fetch_warnings_async_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(f"{API}/warnings/hydro").mock(**mock)
    with pytest.raises(exception, match=message):
        await fetch_warnings_async()


# --------------------------------------------------------------------------
# Archive downloads
# --------------------------------------------------------------------------


def test_download_hydro_data_semi_annual_param_selects_file(respx_mock):
    payload = _zip_bytes()
    respx_mock.get(HYDRO_POLR_Q).respond(content=payload, headers={"ETag": '"q"'})
    result = download_hydro_data("polroczne_i_roczne", 2020, param="Q")
    assert (result.data, result.url, result.etag) == (payload, HYDRO_POLR_Q, '"q"')


def test_download_hydro_data_follows_redirect_and_reports_final_url(respx_mock):
    final = "https://mirror.example/codz_2020_03.zip"
    respx_mock.get(HYDRO_DAILY).respond(302, headers={"Location": final})
    respx_mock.get(final).respond(content=_zip_bytes())
    assert download_hydro_data("dobowe", 2020, 3).url == final


def test_download_hydro_data_daily_before_2023_requires_month(respx_mock):
    with pytest.raises(ValueError, match="Month is required"):
        download_hydro_data("dobowe", 2020)
    assert not respx_mock.calls


def test_download_hydro_data_rejects_invalid_content_length(respx_mock):
    respx_mock.get(HYDRO_DAILY).mock(
        return_value=httpx.Response(
            200,
            stream=httpx.ByteStream(_zip_bytes()),
            headers={"Content-Length": "duzo"},
        )
    )
    with pytest.raises(IMGWDataError, match="Niepoprawny nagłówek Content-Length"):
        download_hydro_data("dobowe", 2020, 3)


def test_download_hydro_data_connect_error_is_polish_connection_error(respx_mock):
    respx_mock.get(HYDRO_DAILY).mock(side_effect=httpx.ConnectError)
    with pytest.raises(IMGWConnectionError, match="Błąd pobierania"):
        download_hydro_data("dobowe", 2020, 3)


def test_download_hydro_data_timeout_is_polish_connection_error(respx_mock):
    respx_mock.get(HYDRO_DAILY).mock(side_effect=httpx.ReadTimeout)
    with pytest.raises(IMGWConnectionError, match="Przekroczono czas pobierania"):
        download_hydro_data("dobowe", 2020, 3)


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "Przekroczono czas"),
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Błąd pobierania"),
        (
            {"return_value": httpx.Response(500)},
            IMGWConnectionError,
            r"Pobieranie nie powiodło się \(HTTP 500\): .*2023_m_k\.zip",
        ),
        (
            {"return_value": httpx.Response(200, content=b"<html>")},
            IMGWDataError,
            "Niepoprawne archiwum ZIP",
        ),
    ],
)
def test_download_meteo_data_maps_failures(respx_mock, mock, exception, message):
    respx_mock.get(METEO_MONTHLY).mock(**mock)
    with pytest.raises(exception, match=message):
        download_meteo_data("miesieczne", "klimat", 2023)


def test_download_meteo_data_unsupported_dataset_raises_before_request(respx_mock):
    with pytest.raises(ValueError):
        download_meteo_data("terminowe", "opad", 2023, 1)
    assert not respx_mock.calls


async def test_download_hydro_data_async_returns_headers(respx_mock):
    payload = _zip_bytes()
    respx_mock.get(HYDRO_POLR_Q).respond(
        content=payload,
        headers={"Last-Modified": "Sun, 18 Oct 2026 08:00:00 GMT", "ETag": '"x"'},
    )
    result = await download_hydro_data_async("polroczne_i_roczne", 2020, param="Q")
    assert result.data == payload
    assert result.last_modified == "Sun, 18 Oct 2026 08:00:00 GMT"
    assert result.etag == '"x"'
    assert result.content_length == len(payload)


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "Przekroczono czas"),
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Błąd pobierania"),
        (
            {"return_value": httpx.Response(404)},
            IMGWConnectionError,
            r"Pobieranie nie powiodło się \(HTTP 404\): .*codz_2020_03\.zip",
        ),
        (
            {"return_value": httpx.Response(200, content=b"PK-ale-nie-zip")},
            IMGWDataError,
            "Niepoprawne archiwum ZIP",
        ),
    ],
)
async def test_download_hydro_data_async_maps_failures(
    respx_mock, mock, exception, message
):
    respx_mock.get(HYDRO_DAILY).mock(**mock)
    with pytest.raises(exception, match=message):
        await download_hydro_data_async("dobowe", 2020, 3)


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Błąd pobierania"),
        (
            {"return_value": httpx.Response(503)},
            IMGWConnectionError,
            r"Pobieranie nie powiodło się \(HTTP 503\)",
        ),
        (
            {
                "return_value": httpx.Response(
                    200,
                    stream=httpx.ByteStream(_zip_bytes()),
                    headers={"Content-Length": "-x"},
                )
            },
            IMGWDataError,
            "Niepoprawny nagłówek Content-Length",
        ),
    ],
)
async def test_download_meteo_data_async_maps_failures(
    respx_mock, mock, exception, message
):
    respx_mock.get(METEO_MONTHLY).mock(**mock)
    with pytest.raises(exception, match=message):
        await download_meteo_data_async("miesieczne", "klimat", 2023)


async def test_download_meteo_data_async_without_headers_leaves_provenance_none(
    respx_mock,
):
    payload = _zip_bytes()
    respx_mock.get(METEO_MONTHLY).mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(payload))
    )
    result = await download_meteo_data_async("miesieczne", "klimat", 2023)
    assert result.data == payload
    assert (result.etag, result.last_modified, result.content_length) == (
        None,
        None,
        None,
    )
