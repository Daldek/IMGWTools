"""Live-data REST routes (hydro, meteo, PMAXTP) with IMGW mocked at the httpx level."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from imgwtools.api.main import app
from imgwtools.core.url_builder import IMGW_API_URL, IMGW_PMAXTP_URL

STATION = "149190310"
HYDRO_ROW = {
    "id_stacji": STATION,
    "stacja": "Raba Górna",
    "rzeka": "Raba",
    "wojewodztwo": "małopolskie",
    "lon": "20.1000",
    "lat": "49.7000",
    "stan_wody": "123",
    "stan_wody_data_pomiaru": "2026-10-18 06:50:00",
    "temperatura_wody": "7.5",
    "przeplyw": "2.48",
}
METEO_ROW = {
    "kod_stacji": "249190310",
    "nazwa_stacji": "SAN ESCOBAR",
    "lon": "20.1000",
    "lat": "49.7000",
    "temperatura_powietrza": "11.2",
    "temperatura_powietrza_data": "2026-10-18 07:00:00",
    "wiatr_srednia_predkosc": "3.4",
    "wiatr_kierunek": "270",
    "wilgotnosc_wzgledna": "81.5",
    "opad_10min": "0.2",
}
SYNOP_ROW = {
    "id_stacji": "12999",
    "stacja": "SAN ESCOBAR",
    "data_pomiaru": "2026-10-18",
    "godzina_pomiaru": "7",
    "temperatura": "-1.5",
    "predkosc_wiatru": "4",
    "kierunek_wiatru": "180",
    "wilgotnosc_wzgledna": "92.1",
    "suma_opadu": "0",
    "cisnienie": "1013.4",
}
PMAXTP_POT = f"{IMGW_PMAXTP_URL}/P/KS/52.2300/21.0100"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=True) as mock:
        yield mock


# --------------------------------------------------------------------------
# /api/v1/hydro
# --------------------------------------------------------------------------


def test_api_hydro_stations_paginates_with_total_count(client):
    full = client.get("/api/v1/hydro/stations").json()
    page = client.get("/api/v1/hydro/stations", params={"limit": 1, "offset": 1})
    assert page.status_code == 200
    assert page.json() == {"stations": full["stations"][1:2], "count": full["count"]}
    beyond = client.get("/api/v1/hydro/stations", params={"offset": full["count"]})
    assert beyond.json() == {"stations": [], "count": full["count"]}


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"limit": "abc"}]
)
def test_api_hydro_stations_rejects_out_of_range_paging(client, params):
    assert client.get("/api/v1/hydro/stations", params=params).status_code == 422


def test_api_hydro_station_maps_imgw_row_to_station(client, imgw):
    imgw.get(f"{IMGW_API_URL}/hydro/id/{STATION}").respond(json=[HYDRO_ROW])
    response = client.get(f"/api/v1/hydro/stations/{STATION}")
    assert response.status_code == 200
    assert response.json() == {
        "id": STATION,
        "name": "Raba Górna",
        "river": "Raba",
        "latitude": 49.7,
        "longitude": 20.1,
    }


def test_api_hydro_station_without_coordinates_has_null_position(client, imgw):
    row = {"id_stacji": STATION, "stacja": "Raba Górna", "rzeka": "Raba"}
    imgw.get(f"{IMGW_API_URL}/hydro/id/{STATION}").respond(json=row)
    body = client.get(f"/api/v1/hydro/stations/{STATION}").json()
    assert (body["name"], body["latitude"], body["longitude"]) == (
        "Raba Górna",
        None,
        None,
    )


@pytest.mark.parametrize(
    "upstream",
    [
        httpx.Response(200, json=[]),
        httpx.Response(
            404, json={"status": False, "message": "Station could not be found"}
        ),
    ],
)
def test_api_hydro_station_unknown_is_404(client, imgw, upstream):
    imgw.get(f"{IMGW_API_URL}/hydro/id/999999999").mock(return_value=upstream)
    response = client.get("/api/v1/hydro/stations/999999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Station not found"}


@pytest.mark.parametrize(
    "upstream,detail",
    [
        (httpx.Response(500, text="awaria"), "IMGW API error"),
        (httpx.ConnectError("odmowa"), "IMGW API error: odmowa"),
        (httpx.Response(200, text="<html>"), "Niepoprawna odpowiedź JSON z API IMGW"),
    ],
)
def test_api_hydro_station_upstream_failure_is_502(client, imgw, upstream, detail):
    route = imgw.get(f"{IMGW_API_URL}/hydro/id/{STATION}")
    if isinstance(upstream, Exception):
        route.mock(side_effect=upstream)
    else:
        route.mock(return_value=upstream)
    response = client.get(f"/api/v1/hydro/stations/{STATION}")
    assert response.status_code == 502
    assert response.json()["detail"].startswith(detail)


def test_api_hydro_current_maps_all_rows_and_missing_values(client, imgw):
    sparse = {"id_stacji": "149190311", "stacja": "SAN ESCOBAR", "stan_wody": None}
    imgw.get(f"{IMGW_API_URL}/hydro").respond(json=[HYDRO_ROW, sparse])
    response = client.get("/api/v1/hydro/current")
    assert response.status_code == 200
    assert response.json() == [
        {
            "station_id": STATION,
            "station_name": "Raba Górna",
            "river": "Raba",
            "province": "małopolskie",
            "water_level": 123.0,
            "water_level_date": "2026-10-18 06:50:00",
            "flow": 2.48,
            "temperature": 7.5,
            "latitude": 49.7,
            "longitude": 20.1,
        },
        {
            "station_id": "149190311",
            "station_name": "SAN ESCOBAR",
            "river": None,
            "province": None,
            "water_level": None,
            "water_level_date": None,
            "flow": None,
            "temperature": None,
            "latitude": None,
            "longitude": None,
        },
    ]


def test_api_hydro_current_station_filter_queries_single_station(client, imgw):
    imgw.get(f"{IMGW_API_URL}/hydro/id/{STATION}").respond(json=HYDRO_ROW)
    response = client.get("/api/v1/hydro/current", params={"station_id": STATION})
    assert [row["station_id"] for row in response.json()] == [STATION]


def test_api_hydro_current_empty_upstream_is_empty_list(client, imgw):
    imgw.get(f"{IMGW_API_URL}/hydro").respond(json=[])
    response = client.get("/api/v1/hydro/current")
    assert (response.status_code, response.json()) == (200, [])


@pytest.mark.parametrize(
    "upstream,detail",
    [
        (httpx.ReadTimeout("zbyt wolno"), "IMGW API error: zbyt wolno"),
        (httpx.Response(200, text="nie-json"), "Niepoprawna odpowiedź JSON z API IMGW"),
        (
            httpx.Response(200, json=[{**HYDRO_ROW, "stan_wody": "brak"}]),
            "Niepoprawna odpowiedź JSON z API IMGW",
        ),
    ],
)
def test_api_hydro_current_upstream_failure_is_502(client, imgw, upstream, detail):
    route = imgw.get(f"{IMGW_API_URL}/hydro")
    if isinstance(upstream, Exception):
        route.mock(side_effect=upstream)
    else:
        route.mock(return_value=upstream)
    response = client.get("/api/v1/hydro/current")
    assert response.status_code == 502
    assert response.json()["detail"] == detail


@pytest.mark.parametrize(
    "payload,filename,month",
    [
        ({"interval": "dobowe", "year": 2022, "month": 3}, "codz_2022_03.zip", 3),
        ({"interval": "dobowe", "year": 2023}, "codz_2023.zip", None),
        ({"interval": "dobowe", "year": 2025}, "codz_2025.zip", None),
        ({"interval": "dobowe", "year": 2022, "month": 13}, "zjaw_2022.zip", 13),
        ({"interval": "miesieczne", "year": 1951}, "mies_1951.zip", None),
        (
            {"interval": "polroczne_i_roczne", "year": 2024, "param": "Q"},
            "polr_Q_2024.zip",
            None,
        ),
    ],
)
def test_api_hydro_download_url_points_to_imgw_archive(
    client, payload, filename, month
):
    response = client.post("/api/v1/hydro/download-url", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == filename
    assert body["url"].startswith("https://danepubliczne.imgw.pl/data/")
    assert body["url"].endswith(f"/{filename}")
    assert (body["data_type"], body["interval"], body["year"], body["month"]) == (
        "dane_hydrologiczne",
        payload["interval"],
        payload["year"],
        month,
    )


@pytest.mark.parametrize(
    "payload,detail",
    [
        (
            {"interval": "dobowe", "year": 2022},
            "Month is required for daily data before 2023",
        ),
        (
            {"interval": "polroczne_i_roczne", "year": 2024},
            "Parameter (T, Q, H) is required for semi-annual data",
        ),
        ({"interval": "miesieczne", "year": 2024, "param": "T"}, "Unknown parameter"),
    ],
)
def test_api_hydro_download_url_invalid_combination_is_400(client, payload, detail):
    response = client.post("/api/v1/hydro/download-url", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"].startswith(detail)


@pytest.mark.parametrize(
    "payload",
    [
        {"interval": "godzinowe", "year": 2022},
        {"interval": "miesieczne", "year": 1950},
        {"interval": "miesieczne", "year": 10000},
        {"interval": "dobowe", "year": 2022, "month": 0},
        {"interval": "dobowe", "year": 2022, "month": 14},
        {"interval": "polroczne_i_roczne", "year": 2022, "param": "X"},
        {"interval": "miesieczne"},
    ],
)
def test_api_hydro_download_url_schema_violation_is_422(client, payload):
    assert client.post("/api/v1/hydro/download-url", json=payload).status_code == 422


def test_api_hydro_download_urls_daily_spans_monthly_and_yearly_layout(client):
    response = client.post(
        "/api/v1/hydro/download-urls",
        params={"interval": "dobowe", "start_year": 2022, "end_year": 2023},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["urls"]) == 13
    assert [item["filename"] for item in body["urls"]] == [
        *(f"codz_2022_{month:02d}.zip" for month in range(1, 13)),
        "codz_2023.zip",
    ]
    assert [item["month"] for item in body["urls"]] == [*range(1, 13), None]


@pytest.mark.parametrize(
    "params,filenames",
    [
        (
            {"interval": "miesieczne", "start_year": 2020, "end_year": 2021},
            ["mies_2020.zip", "mies_2021.zip"],
        ),
        (
            {
                "interval": "polroczne_i_roczne",
                "start_year": 2020,
                "end_year": 2021,
                "param": "H",
            },
            ["polr_H_2020.zip", "polr_H_2021.zip"],
        ),
    ],
)
def test_api_hydro_download_urls_one_file_per_year(client, params, filenames):
    body = client.post("/api/v1/hydro/download-urls", params=params).json()
    assert [item["filename"] for item in body["urls"]] == filenames
    assert [item["year"] for item in body["urls"]] == [2020, 2021]


def test_api_hydro_download_urls_accepts_years_after_2024(client):
    response = client.post(
        "/api/v1/hydro/download-urls",
        params={"interval": "dobowe", "start_year": 2024, "end_year": 2025},
    )
    assert response.status_code == 200
    assert [item["filename"] for item in response.json()["urls"]] == [
        "codz_2024.zip",
        "codz_2025.zip",
    ]
    assert response.json()["urls"][1]["url"].endswith("/dobowe/2025/codz_2025.zip")


def test_api_hydro_download_urls_start_after_end_is_400(client):
    response = client.post(
        "/api/v1/hydro/download-urls",
        params={"interval": "miesieczne", "start_year": 2021, "end_year": 2020},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "start_year must be <= end_year"}


@pytest.mark.parametrize(
    "params",
    [
        {"interval": "miesieczne", "start_year": 1950, "end_year": 1951},
        {"interval": "miesieczne", "start_year": 2020, "end_year": 10000},
        {"interval": "roczne", "start_year": 2020, "end_year": 2020},
        {"interval": "miesieczne", "start_year": 2020},
    ],
)
def test_api_hydro_download_urls_schema_violation_is_422(client, params):
    assert client.post("/api/v1/hydro/download-urls", params=params).status_code == 422


def test_api_hydro_removed_db_endpoint_is_404(client):
    assert client.get("/api/v1/hydro/data").status_code == 404


# --------------------------------------------------------------------------
# /api/v1/meteo
# --------------------------------------------------------------------------


def test_api_meteo_stations_paginates_with_total_count(client):
    full = client.get("/api/v1/meteo/stations").json()
    page = client.get("/api/v1/meteo/stations", params={"limit": 1})
    assert page.json() == {"stations": full["stations"][:1], "count": full["count"]}
    assert client.get("/api/v1/meteo/stations", params={"limit": 0}).status_code == 422


@pytest.mark.parametrize(
    "params,path",
    [
        ({}, "/synop"),
        ({"station_id": "12999"}, "/synop/id/12999"),
        ({"station_name": "sanescobar"}, "/synop/station/sanescobar"),
        ({"station_id": "12999", "station_name": "x"}, "/synop/id/12999"),
    ],
)
def test_api_meteo_synop_maps_rows_and_filters(client, imgw, params, path):
    imgw.get(f"{IMGW_API_URL}{path}").respond(json=SYNOP_ROW)
    response = client.get("/api/v1/meteo/synop", params=params)
    assert response.status_code == 200
    assert response.json() == [
        {
            "station_id": "12999",
            "station_name": "SAN ESCOBAR",
            "temperature": -1.5,
            "wind_speed": 4.0,
            "wind_direction": 180,
            "humidity": 92.1,
            "precipitation": 0.0,
            "pressure": 1013.4,
            "measurement_date": "2026-10-18",
        }
    ]


def test_api_meteo_synop_empty_upstream_is_empty_list(client, imgw):
    imgw.get(f"{IMGW_API_URL}/synop").respond(json=[])
    assert client.get("/api/v1/meteo/synop").json() == []


@pytest.mark.parametrize(
    "upstream,detail",
    [
        (httpx.Response(503, text="przerwa"), "IMGW API error"),
        (httpx.Response(200, text="<html>"), "Niepoprawna odpowiedź JSON z API IMGW"),
    ],
)
def test_api_meteo_synop_upstream_failure_is_502(client, imgw, upstream, detail):
    imgw.get(f"{IMGW_API_URL}/synop").mock(return_value=upstream)
    response = client.get("/api/v1/meteo/synop")
    assert response.status_code == 502
    assert response.json()["detail"].startswith(detail)


def test_api_meteo_current_maps_imgw_meteo_fields(client, imgw):
    sparse = {"kod_stacji": "249190311", "nazwa_stacji": "Raba Górna"}
    imgw.get(f"{IMGW_API_URL}/meteo").respond(json=[METEO_ROW, sparse])
    response = client.get("/api/v1/meteo/current")
    assert response.status_code == 200
    assert response.json() == [
        {
            "station_id": "249190310",
            "station_name": "SAN ESCOBAR",
            "temperature": 11.2,
            "wind_speed": 3.4,
            "wind_direction": None,
            "humidity": 81.5,
            "precipitation": 0.2,
            "pressure": None,
            "measurement_date": "2026-10-18 07:00:00",
        },
        {
            "station_id": "249190311",
            "station_name": "Raba Górna",
            "temperature": None,
            "wind_speed": None,
            "wind_direction": None,
            "humidity": None,
            "precipitation": None,
            "pressure": None,
            "measurement_date": None,
        },
    ]


def test_api_meteo_current_station_filter_and_empty_result(client, imgw):
    imgw.get(f"{IMGW_API_URL}/meteo/id/249190310").respond(json=[])
    response = client.get("/api/v1/meteo/current", params={"station_id": "249190310"})
    assert (response.status_code, response.json()) == (200, [])


@pytest.mark.parametrize(
    "upstream,detail",
    [
        (httpx.ConnectTimeout("brak sieci"), "IMGW API error: brak sieci"),
        (httpx.Response(200, text="<html>"), "Niepoprawna odpowiedź JSON z API IMGW"),
    ],
)
def test_api_meteo_current_upstream_failure_is_502(client, imgw, upstream, detail):
    route = imgw.get(f"{IMGW_API_URL}/meteo")
    if isinstance(upstream, Exception):
        route.mock(side_effect=upstream)
    else:
        route.mock(return_value=upstream)
    response = client.get("/api/v1/meteo/current")
    assert response.status_code == 502
    assert response.json()["detail"] == detail


def test_api_meteo_download_url_monthly_synop_uses_folder_file(client):
    response = client.post(
        "/api/v1/meteo/download-url",
        json={"interval": "miesieczne", "subtype": "synop", "year": 1998},
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "1996_2000_m_s.zip"
    assert response.json()["url"].endswith(
        "/miesieczne/synop/1996_2000/1996_2000_m_s.zip"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"interval": "terminowe", "subtype": "opad", "year": 2020, "month": 1},
        {"interval": "dobowe", "subtype": "synop", "year": 2020, "month": 1},
        {"interval": "dobowe", "subtype": "klimat", "year": 2020},
    ],
)
def test_api_meteo_download_url_unsupported_combination_is_400(client, payload):
    response = client.post("/api/v1/meteo/download-url", json=payload)
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Nieprawidłowa kombinacja typu, interwału, podtypu, parametru "
        "lub roku archiwum IMGW"
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"interval": "dobowe", "subtype": "klimat", "year": 1949},
        {"interval": "dobowe", "subtype": "klimat", "year": 2020, "month": 13},
        {"interval": "dobowe", "subtype": "grad", "year": 2020},
    ],
)
def test_api_meteo_download_url_schema_violation_is_422(client, payload):
    assert client.post("/api/v1/meteo/download-url", json=payload).status_code == 422


def test_api_meteo_download_urls_monthly_range_one_file_per_year(client):
    response = client.post(
        "/api/v1/meteo/download-urls",
        params={
            "interval": "miesieczne",
            "subtype": "klimat",
            "start_year": 2021,
            "end_year": 2022,
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [item["filename"] for item in response.json()["urls"]] == [
        "2021_m_k.zip",
        "2022_m_k.zip",
    ]


def test_api_meteo_download_urls_start_after_end_is_400(client):
    response = client.post(
        "/api/v1/meteo/download-urls",
        params={
            "interval": "miesieczne",
            "subtype": "klimat",
            "start_year": 2022,
            "end_year": 2021,
        },
    )
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Rok początkowy nie może przekraczać końcowego"
    }


# --------------------------------------------------------------------------
# /api/v1/pmaxtp
# --------------------------------------------------------------------------


def test_api_pmaxtp_methods_lists_pot_and_amp(client):
    response = client.get("/api/v1/pmaxtp/methods")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["methods"]] == ["POT", "AMP"]


@pytest.mark.parametrize(
    "method,lat,lon,url",
    [
        ("POT", 52.23, 21.01, PMAXTP_POT),
        ("AMP", 49.0, 14.0, f"{IMGW_PMAXTP_URL}/A/KS/49.0000/14.0000"),
        ("POT", 55.0, 24.5, f"{IMGW_PMAXTP_URL}/P/KS/55.0000/24.5000"),
    ],
)
def test_api_pmaxtp_url_builds_point_url_within_poland(client, method, lat, lon, url):
    response = client.post(
        "/api/v1/pmaxtp/url",
        json={"method": method, "latitude": lat, "longitude": lon},
    )
    assert response.status_code == 200
    assert response.json() == {
        "url": url,
        "method": method,
        "latitude": lat,
        "longitude": lon,
    }


@pytest.mark.parametrize("endpoint", ["/api/v1/pmaxtp/url", "/api/v1/pmaxtp/data"])
@pytest.mark.parametrize(
    "payload",
    [
        {"method": "POT", "latitude": 48.99, "longitude": 21.0},
        {"method": "POT", "latitude": 55.01, "longitude": 21.0},
        {"method": "POT", "latitude": 52.0, "longitude": 13.99},
        {"method": "POT", "latitude": 52.0, "longitude": 24.51},
        {"method": "MAX", "latitude": 52.0, "longitude": 21.0},
    ],
)
def test_api_pmaxtp_rejects_point_outside_poland_or_unknown_method(
    client, endpoint, payload
):
    with respx.mock(assert_all_mocked=True):
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422


def test_api_pmaxtp_data_returns_quantile_tables(client, imgw, pmaxtp_api_response):
    imgw.get(PMAXTP_POT).respond(json=pmaxtp_api_response)
    response = client.post(
        "/api/v1/pmaxtp/data",
        json={"method": "POT", "latitude": 52.23, "longitude": 21.01},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["method"], body["latitude"], body["longitude"]) == (
        "POT",
        52.23,
        21.01,
    )
    assert set(body["data"]["data"]) == {"ks", "sg", "rb"}
    assert body["data"]["data"]["ks"]["15"]["10"] == 8.6


@pytest.mark.parametrize(
    "upstream,status,detail",
    [
        (
            httpx.Response(
                200,
                json={
                    "data": {},
                    "error": "undefined: lat 54.9000, lon: 23.9000, type: KS",
                },
            ),
            502,
            "API PMAXTP zwróciło błąd: undefined: lat 54.9000",
        ),
        (httpx.Response(503, text="serwis niedostępny"), 503, "IMGW API error: serwis"),
        (httpx.Response(404, text="brak punktu"), 404, "IMGW API error: brak punktu"),
        (httpx.ReadTimeout("zbyt wolno"), 504, "IMGW API timeout - sprobuj ponownie"),
        (httpx.ConnectError("odmowa"), 502, "IMGW API connection error: odmowa"),
        (httpx.Response(200, text="<html>"), 502, "Niepoprawna odpowiedź JSON z API"),
    ],
)
def test_api_pmaxtp_data_upstream_failure_is_mapped(
    client, imgw, upstream, status, detail
):
    route = imgw.get(f"{IMGW_PMAXTP_URL}/P/KS/54.9000/23.9000")
    if isinstance(upstream, Exception):
        route.mock(side_effect=upstream)
    else:
        route.mock(return_value=upstream)
    response = client.post(
        "/api/v1/pmaxtp/data",
        json={"method": "POT", "latitude": 54.9, "longitude": 23.9},
    )
    assert response.status_code == status
    assert response.json()["detail"].startswith(detail)
