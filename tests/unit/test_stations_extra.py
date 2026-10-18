"""Offline tests for station listing paths not covered by test_stations.py."""

import httpx
import pytest

from imgwtools.exceptions import IMGWConnectionError, IMGWDataError
from imgwtools.stations import (
    HYDRO_MAP_API_URL,
    HYDRO_STATIONS_CSV_URL,
    METEO_STATIONS_CSV_URL,
    _parse_hydro_stations_csv,
    _parse_map_stations_response,
    get_hydro_stations_with_coords,
    get_hydro_stations_with_coords_async,
    list_hydro_stations,
    list_hydro_stations_async,
    list_meteo_stations,
    list_meteo_stations_async,
)

METEO_CSV = '"249190310","RABA GÓRNA","GR"\n"349190310","SAN ESCOBAR","SE"\n'
HYDRO_CSV = '"149190310","RABA GÓRNA","Raba (2138)","2"\n"149190311","ŻABIE","",""\n'
MAP_PAYLOAD = {
    "stations": [
        {"id": 149190310, "n": "Raba Górna", "la": 49.61, "lo": 20.05, "s": "high"},
        {"id": "149190311", "n": "SAN ESCOBAR", "la": "brak", "lo": 20.1},
        {"id": "149190312", "n": "Żabie", "s": "low"},
    ]
}


def test_list_meteo_stations_decodes_cp1250(respx_mock):
    respx_mock.get(METEO_STATIONS_CSV_URL).respond(content=METEO_CSV.encode("cp1250"))
    stations = list_meteo_stations()
    assert [(s.station_id, s.name) for s in stations] == [
        ("249190310", "RABA GÓRNA"),
        ("349190310", "SAN ESCOBAR"),
    ]


async def test_list_meteo_stations_async_decodes_cp1250(respx_mock):
    respx_mock.get(METEO_STATIONS_CSV_URL).respond(content=METEO_CSV.encode("cp1250"))
    stations = await list_meteo_stations_async()
    assert [s.name for s in stations] == ["RABA GÓRNA", "SAN ESCOBAR"]


async def test_list_hydro_stations_async_parses_river_code_and_order(respx_mock):
    respx_mock.get(HYDRO_STATIONS_CSV_URL).respond(content=HYDRO_CSV.encode("cp1250"))
    stations = await list_hydro_stations_async()
    assert [
        (s.station_id, s.name, s.river, s.hydrographic_code, s.river_order)
        for s in stations
    ] == [
        ("149190310", "RABA GÓRNA", "Raba", "2138", 2),
        ("149190311", "ŻABIE", None, None, None),
    ]


@pytest.mark.parametrize(
    "function, url",
    [
        (list_hydro_stations, HYDRO_STATIONS_CSV_URL),
        (list_meteo_stations, METEO_STATIONS_CSV_URL),
    ],
)
@pytest.mark.parametrize(
    "mock, message",
    [
        ({"side_effect": httpx.ReadTimeout}, "Timeout fetching station list"),
        ({"return_value": httpx.Response(404)}, "Failed to fetch station list"),
        ({"side_effect": httpx.ConnectError}, "Failed to fetch station list"),
    ],
)
def test_station_csv_lists_map_http_failures(respx_mock, function, url, mock, message):
    respx_mock.get(url).mock(**mock)
    with pytest.raises(IMGWConnectionError, match=message):
        function()


@pytest.mark.parametrize(
    "function, url",
    [
        (list_hydro_stations_async, HYDRO_STATIONS_CSV_URL),
        (list_meteo_stations_async, METEO_STATIONS_CSV_URL),
    ],
)
@pytest.mark.parametrize(
    "mock, message",
    [
        ({"side_effect": httpx.ReadTimeout}, "Timeout fetching station list"),
        ({"return_value": httpx.Response(500)}, "Failed to fetch station list"),
    ],
)
async def test_station_csv_lists_async_map_http_failures(
    respx_mock, function, url, mock, message
):
    respx_mock.get(url).mock(**mock)
    with pytest.raises(IMGWConnectionError, match=message):
        await function()


def test_get_hydro_stations_with_coords_sends_required_headers(respx_mock):
    route = respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD)
    get_hydro_stations_with_coords()
    request = route.calls.last.request
    assert request.headers["Referer"] == "https://hydro.imgw.pl/"
    assert request.headers["User-Agent"].startswith("IMGWTools/")
    assert request.url.params["onlyMainStations"] == "false"


def test_get_hydro_stations_with_coords_skips_invalid_and_keeps_missing_coords(
    respx_mock,
):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD)
    stations = get_hydro_stations_with_coords()
    assert [
        (s.station_id, s.name, s.latitude, s.longitude, s.water_state) for s in stations
    ] == [
        ("149190310", "Raba Górna", 49.61, 20.05, "high"),
        ("149190312", "Żabie", None, None, "low"),
    ]


async def test_get_hydro_stations_with_coords_async_main_only(respx_mock):
    route = respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD["stations"])
    stations = await get_hydro_stations_with_coords_async(include_all=False)
    request = route.calls.last.request
    assert request.url.params["onlyMainStations"] == "true"
    assert request.headers["Referer"] == "https://hydro.imgw.pl/"
    assert [s.station_id for s in stations] == ["149190310", "149190312"]


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "Timeout fetching"),
        (
            {"return_value": httpx.Response(403)},
            IMGWConnectionError,
            "Failed to fetch stations",
        ),
        (
            {"return_value": httpx.Response(200, text="<html>blad</html>")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
    ],
)
def test_get_hydro_stations_with_coords_maps_failures(
    respx_mock, mock, exception, message
):
    respx_mock.get(HYDRO_MAP_API_URL).mock(**mock)
    with pytest.raises(exception, match=message):
        get_hydro_stations_with_coords()


@pytest.mark.parametrize(
    "mock, exception, message",
    [
        ({"side_effect": httpx.ReadTimeout}, IMGWConnectionError, "Timeout fetching"),
        ({"side_effect": httpx.ConnectError}, IMGWConnectionError, "Failed to fetch"),
        (
            {"return_value": httpx.Response(200, text="")},
            IMGWDataError,
            "Niepoprawna odpowiedź JSON",
        ),
    ],
)
async def test_get_hydro_stations_with_coords_async_maps_failures(
    respx_mock, mock, exception, message
):
    respx_mock.get(HYDRO_MAP_API_URL).mock(**mock)
    with pytest.raises(exception, match=message):
        await get_hydro_stations_with_coords_async()


def test_parse_map_stations_response_without_stations_key_is_empty():
    assert _parse_map_stations_response({"status": "ok"}) == []


def test_parse_hydro_stations_csv_skips_single_column_rows():
    stations = _parse_hydro_stations_csv('"149190310"\n\n"149190311","SAN ESCOBAR"\n')
    assert [s.station_id for s in stations] == ["149190311"]
