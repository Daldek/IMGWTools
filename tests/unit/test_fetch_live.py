"""Offline tests for live IMGW reads and archive downloads (respx-mocked HTTP)."""

import io
import json
import zipfile

import httpx
import pytest

from imgwtools.datasets import station_source_files
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
    fetch_meteo_current,
    fetch_meteo_current_async,
    fetch_pmaxtp,
    fetch_pmaxtp_async,
    fetch_synop,
    fetch_synop_async,
    fetch_warnings,
    fetch_warnings_async,
)
from imgwtools.models import PMaXTPData, PMaXTPResult
from imgwtools.stations import (
    fetch_hydro_states,
    fetch_hydro_states_async,
    find_stations,
    find_stations_async,
)

API = "https://danepubliczne.imgw.pl/api/data"
PMAXTP = "https://powietrze.imgw.pl/tpmax-api/point"
MAP = "https://hydro-back.imgw.pl/map/stations/hydrologic"
HYDRO_LIST_URL = station_source_files()[0].url
ARCHIVE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
HYDRO_POLR_Q = f"{ARCHIVE}/dane_hydrologiczne/polroczne_i_roczne/2020/polr_Q_2020.zip"
HYDRO_DAILY = f"{ARCHIVE}/dane_hydrologiczne/dobowe/2020/codz_2020_03.zip"
METEO_MONTHLY = f"{ARCHIVE}/dane_meteorologiczne/miesieczne/klimat/2023/2023_m_k.zip"

HYDRO_ITEMS = [
    {
        "id_stacji": "149190310",
        "stacja": "SAN ESCOBAR",
        "rzeka": "Raba",
        "wojewodztwo": "małopolskie",
        "lon": "20.0500",
        "lat": "49.6100",
        "stan_wody": "212",
        "stan_wody_data_pomiaru": "2026-10-18 06:00:00",
        "przeplyw": "12.3",
        "przeplyw_data": "2026-10-18 06:10:00",
    },
    {"id_stacji": "149190311", "stacja": "RABA GÓRNA", "stan_wody": "brak"},
]
METEO_ITEMS = [
    {
        "kod_stacji": "249190310",
        "nazwa_stacji": "SAN ESCOBAR",
        "lon": "18.919167",
        "lat": "49.995556",
        "temperatura_powietrza": "10.4",
        "temperatura_powietrza_data": "2026-10-18 16:10:00",
        "wiatr_srednia_predkosc": "3.2",
        "wilgotnosc_wzgledna": "81.5",
        "opad_10min": "0.2",
    },
    {"kod_stacji": "249190311", "nazwa_stacji": "RABA GÓRNA", "opad_10min": None},
]
SYNOP_ITEMS = [
    {"id_stacji": "12999", "stacja": "SAN ESCOBAR", "temperatura": "7.5"},
    {"id_stacji": "12998", "stacja": "Raba Górna", "temperatura": "-1.0"},
]
HYDRO_WARNINGS = [
    {
        "numer": "21",
        "zdarzenie": "Wezbranie",
        "stopień": "1",
        "data_od": "2026-10-18 08:00:00",
        "data_do": "2026-10-20 08:00:00",
        "przebieg": "Wzrost stanów wody na Rabie",
        "obszary": [{"wojewodztwo": "małopolskie", "opis": "Raba"}],
    }
]
METEO_WARNINGS = [
    {
        "id": "77",
        "nazwa_zdarzenia": "Silny wiatr",
        "stopien": "2",
        "obowiazuje_od": "2026-10-18 06:00:00",
        "tresc": "Porywy do 90 km/h",
        "teryt": ["1261"],
    }
]


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dane.csv", "149190310,SAN ESCOBAR\n")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Common contract of every live read
# --------------------------------------------------------------------------

# (sync, async, keyword arguments, requested URL, successful JSON body or CSV bytes)
LIVE_READS = [
    (fetch_hydro_current, fetch_hydro_current_async, {}, f"{API}/hydro", HYDRO_ITEMS),
    (fetch_meteo_current, fetch_meteo_current_async, {}, f"{API}/meteo", METEO_ITEMS),
    (fetch_synop, fetch_synop_async, {}, f"{API}/synop", SYNOP_ITEMS),
    (
        fetch_warnings,
        fetch_warnings_async,
        {"kind": "hydro"},
        f"{API}/warningshydro",
        HYDRO_WARNINGS,
    ),
    (
        fetch_pmaxtp,
        fetch_pmaxtp_async,
        {"latitude": 52.0, "longitude": 20.0},
        f"{PMAXTP}/P/KS/52.0000/20.0000",
        {"data": {"ks": {"15": {"50": 4.2}}}},
    ),
    (
        fetch_hydro_states,
        fetch_hydro_states_async,
        {},
        f"{MAP}?onlyMainStations=false",
        {"stations": [{"id": "149190310", "n": "SAN ESCOBAR", "s": "low"}]},
    ),
    (
        find_stations,
        find_stations_async,
        {"kind": "hydro"},
        HYDRO_LIST_URL,
        '"149190310","SAN ESCOBAR","Raba (2138)"\n'.encode("cp1250"),
    ),
]
LIVE_IDS = [read[0].__name__ for read in LIVE_READS]


def _respond(body: object) -> httpx.Response:
    if isinstance(body, bytes):
        return httpx.Response(200, content=body)
    return httpx.Response(200, json=body)


@pytest.mark.parametrize(
    "mock, reason, status",
    [
        ({"side_effect": httpx.ReadTimeout}, "timeout", None),
        ({"side_effect": httpx.ConnectError}, "network", None),
        ({"return_value": httpx.Response(503, text="przerwa")}, "http_status", 503),
    ],
    ids=["timeout", "network", "http_status"],
)
@pytest.mark.parametrize(
    "sync, asynchronous, kwargs, url, body", LIVE_READS, ids=LIVE_IDS
)
async def test_live_read_failure_is_source_unavailable_with_url_and_reason(
    respx_mock, sync, asynchronous, kwargs, url, body, mock, reason, status
):
    respx_mock.get(url).mock(**mock)
    with pytest.raises(IMGWConnectionError) as sync_error:
        sync(**kwargs)
    with pytest.raises(IMGWConnectionError) as async_error:
        await asynchronous(**kwargs)

    expected = {"url": url, "reason": reason}
    if status is not None:
        expected["status"] = status
    for error in (sync_error.value, async_error.value):
        assert error.code == "source_unavailable"
        assert error.details == expected
        assert url in error.detail


@pytest.mark.parametrize(
    "sync, asynchronous, kwargs, url, body", LIVE_READS, ids=LIVE_IDS
)
async def test_live_read_async_twin_returns_identical_result(
    respx_mock, sync, asynchronous, kwargs, url, body
):
    respx_mock.get(url).mock(side_effect=lambda _: _respond(body))
    result = sync(**kwargs)
    assert result
    assert await asynchronous(**kwargs) == result


@pytest.mark.parametrize(
    "sync, asynchronous, kwargs, url, body",
    [read for read in LIVE_READS if not isinstance(read[4], bytes)],
    ids=[read[0].__name__ for read in LIVE_READS if not isinstance(read[4], bytes)],
)
async def test_live_read_non_json_body_is_data_error(
    respx_mock, sync, asynchronous, kwargs, url, body
):
    respx_mock.get(url).respond(200, text="<html>przerwa</html>")
    with pytest.raises(IMGWDataError, match="Niepoprawna odpowiedź JSON"):
        sync(**kwargs)
    with pytest.raises(IMGWDataError, match="Niepoprawna odpowiedź JSON"):
        await asynchronous(**kwargs)


@pytest.mark.parametrize(
    "function, url",
    [
        (fetch_hydro_current, f"{API}/hydro"),
        (fetch_meteo_current, f"{API}/meteo"),
        (fetch_synop, f"{API}/synop"),
    ],
)
@pytest.mark.parametrize("body", [["149190310"], 42])
def test_current_reads_reject_non_record_bodies(respx_mock, function, url, body):
    respx_mock.get(url).respond(json=body)
    with pytest.raises(IMGWDataError, match="oczekiwano listy obiektów"):
        function()


# --------------------------------------------------------------------------
# PMAXTP
# --------------------------------------------------------------------------


async def test_fetch_pmaxtp_amp_result_is_unchanged(respx_mock, pmaxtp_api_response):
    respx_mock.get(f"{PMAXTP}/A/KS/52.2300/21.0100").respond(json=pmaxtp_api_response)
    expected = PMaXTPResult(
        method="AMP",
        latitude=52.23,
        longitude=21.01,
        data=PMaXTPData.from_api_response(pmaxtp_api_response),
    )

    assert fetch_pmaxtp(52.23, 21.01, method="AMP") == expected
    assert await fetch_pmaxtp_async(52.23, 21.01, method="AMP") == expected


def test_fetch_pmaxtp_method_is_keyword_only(respx_mock):
    with pytest.raises(TypeError):
        fetch_pmaxtp(52.23, 21.01, "AMP")  # type: ignore[misc]
    assert not respx_mock.calls


def test_fetch_pmaxtp_unknown_method_is_validation_error(respx_mock):
    with pytest.raises(IMGWValidationError) as error:
        fetch_pmaxtp(52.23, 21.01, method="MAX")  # type: ignore[arg-type]
    assert error.value.details == {"option": "method", "allowed": ["POT", "AMP"]}
    assert not respx_mock.calls


@pytest.mark.parametrize("latitude", [49.0, 55.0])
def test_fetch_pmaxtp_latitude_bounds_are_inclusive(respx_mock, latitude):
    route = respx_mock.get(f"{PMAXTP}/P/KS/{latitude:.4f}/20.0000").respond(
        json={"data": {"ks": {"15": {"50": 4.2}}}}
    )
    result = fetch_pmaxtp(latitude, 20.0)
    assert route.called
    assert result.data.get_precipitation(15, 50) == 4.2


@pytest.mark.parametrize(
    "latitude, longitude, word, option, value",
    [
        (48.99, 20.0, "Szerokość", "latitude", 48.99),
        (52.0, 24.51, "Długość", "longitude", 24.51),
        (52.0, 13.99, "Długość", "longitude", 13.99),
    ],
)
async def test_fetch_pmaxtp_rejects_coords_outside_poland_before_request(
    respx_mock, latitude, longitude, word, option, value
):
    with pytest.raises(IMGWValidationError, match=word) as error:
        fetch_pmaxtp(latitude, longitude)
    with pytest.raises(IMGWValidationError, match=word):
        await fetch_pmaxtp_async(latitude, longitude)
    assert error.value.details == {"option": option, "value": value}
    assert not respx_mock.calls


def test_fetch_pmaxtp_outside_box_matches_sync_pmaxtp(tmp_path):
    from imgwtools.store import init_store, sync_pmaxtp

    with pytest.raises(IMGWValidationError) as live:
        fetch_pmaxtp(40.0, 21.01)
    with pytest.raises(IMGWValidationError) as stored:
        sync_pmaxtp(
            init_store(tmp_path / "store"), method="POT", latitude=40.0, longitude=21.01
        )
    assert str(live.value) == str(stored.value)


def test_fetch_pmaxtp_validate_coords_false_sends_request(respx_mock):
    route = respx_mock.get(f"{PMAXTP}/A/KS/40.0000/10.0000").respond(
        json={"data": {"ks": {"15": {"50": 1.5}}}}
    )
    result = fetch_pmaxtp(40.0, 10.0, method="AMP", validate_coords=False)
    assert route.called
    assert result.data.get_precipitation(15, 50) == 1.5


@pytest.mark.parametrize(
    "payload, exception, message",
    [
        (
            {"data": {}, "error": "Brak pliku, pradopodobnie poza obszarem PL"},
            IMGWValidationError,
            "poza siatką PMAXTP",
        ),
        ({"data": {}, "error": "Awaria"}, IMGWDataError, "Awaria"),
        ({"data": {}}, IMGWDataError, "bez danych"),
        ({"data": {"ks": "zle"}}, IMGWDataError, "Niepoprawna odpowiedź PMAXTP"),
    ],
)
async def test_fetch_pmaxtp_error_bodies_are_not_results(
    respx_mock, payload, exception, message
):
    respx_mock.get(f"{PMAXTP}/P/KS/54.7104/20.4522").respond(json=payload)
    with pytest.raises(exception, match=message):
        fetch_pmaxtp(54.7104, 20.4522)
    with pytest.raises(exception, match=message):
        await fetch_pmaxtp_async(54.7104, 20.4522)


# --------------------------------------------------------------------------
# Hydro and meteo current data
# --------------------------------------------------------------------------


def test_fetch_hydro_current_reads_station_code_and_coordinates(respx_mock):
    respx_mock.get(f"{API}/hydro").respond(json=HYDRO_ITEMS)
    first, second = fetch_hydro_current()
    assert (first.station_code, first.latitude, first.longitude) == (
        "149190310",
        49.61,
        20.05,
    )
    assert (first.province, first.flow_m3s, first.flow_date) == (
        "małopolskie",
        12.3,
        "2026-10-18 06:10:00",
    )
    assert (second.station_code, second.latitude, second.water_level_cm) == (
        "149190311",
        None,
        None,
    )


async def test_fetch_hydro_current_station_targets_station_endpoint(respx_mock):
    respx_mock.get(f"{API}/hydro/id/149190310").respond(json=HYDRO_ITEMS[:1])
    assert [s.station_code for s in fetch_hydro_current(station="149190310")] == [
        "149190310"
    ]
    result = await fetch_hydro_current_async(station="149190310")
    assert [s.station_code for s in result] == ["149190310"]


def test_fetch_meteo_current_maps_fields_and_missing_values(respx_mock):
    respx_mock.get(f"{API}/meteo").respond(json=METEO_ITEMS)
    full, sparse = fetch_meteo_current()
    assert full.model_dump() == {
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
    assert sparse.station_code == "249190311"
    assert (
        sparse.latitude,
        sparse.air_temp_c,
        sparse.wind_speed_ms,
        sparse.humidity_percent,
        sparse.precipitation_10min_mm,
    ) == (None, None, None, None, None)


async def test_fetch_meteo_current_station_targets_station_endpoint(respx_mock):
    respx_mock.get(f"{API}/meteo/id/249190311").respond(json=METEO_ITEMS[1:])
    [station] = await fetch_meteo_current_async(station="249190311")
    assert station.station_name == "RABA GÓRNA"


# --------------------------------------------------------------------------
# Synop
# --------------------------------------------------------------------------


async def test_fetch_synop_station_wraps_single_object(respx_mock):
    respx_mock.get(f"{API}/synop/id/12999").respond(json=SYNOP_ITEMS[0])
    [station] = fetch_synop(station="12999")
    assert (station.station_code, station.temperature_c) == ("12999", 7.5)
    assert await fetch_synop_async(station="12999") == [station]


async def test_fetch_synop_filters_by_name_case_insensitive(respx_mock):
    respx_mock.get(f"{API}/synop").respond(json=SYNOP_ITEMS)
    assert [s.station_code for s in fetch_synop(station_name="raba")] == ["12998"]
    assert await fetch_synop_async(station_name="RABA") == fetch_synop(
        station_name="raba"
    )
    assert fetch_synop(station_name="Atlantyda") == []


# --------------------------------------------------------------------------
# Warnings
# --------------------------------------------------------------------------


async def test_fetch_warnings_combines_hydro_and_meteo_with_kind(respx_mock):
    respx_mock.get(f"{API}/warningshydro").respond(json=HYDRO_WARNINGS)
    respx_mock.get(f"{API}/warningsmeteo").respond(json=METEO_WARNINGS)

    warnings = fetch_warnings()

    assert [(w.kind, w.id, w.event, w.level, w.region) for w in warnings] == [
        ("hydro", "21", "Wezbranie", 1, "małopolskie"),
        ("meteo", "77", "Silny wiatr", 2, "1261"),
    ]
    assert await fetch_warnings_async() == warnings


@pytest.mark.parametrize(
    "body",
    [
        {"message": "Brak ostrzeżeń meteorologicznych"},
        {"status": False, "message": "Brak danych"},
        [],
        None,
    ],
)
def test_fetch_warnings_without_warnings_is_empty(respx_mock, body):
    route = respx_mock.get(f"{API}/warningsmeteo").respond(
        content=json.dumps(body).encode()
    )
    assert fetch_warnings(kind="meteo") == []
    assert route.call_count == 1


async def test_fetch_warnings_unknown_kind_is_validation_error(respx_mock):
    with pytest.raises(IMGWValidationError) as error:
        fetch_warnings(kind="synop")  # type: ignore[arg-type]
    with pytest.raises(IMGWValidationError):
        await fetch_warnings_async(kind="synop")  # type: ignore[arg-type]
    assert error.value.details == {"option": "kind", "allowed": ["hydro", "meteo"]}
    assert not respx_mock.calls


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
