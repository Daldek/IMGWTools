"""Archive URL endpoints enumerate registry files without fetching them."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imgwtools.api.routes import download, meteo
from imgwtools.datasets import archive_files


@pytest.fixture
def client(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("URL generation must not perform HTTP requests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    app = FastAPI()
    app.include_router(download.router, prefix="/api/v1/download")
    app.include_router(meteo.router, prefix="/api/v1/meteo")
    return TestClient(app)


@pytest.mark.parametrize("interval,year,dataset", [
    ("dobowe", 2022, "pl.imgw.hydro_daily"),
    ("dobowe", 2024, "pl.imgw.hydro_daily"),
    ("miesieczne", 2024, "pl.imgw.hydro_monthly"),
    ("polroczne_i_roczne", 2024, "pl.imgw.hydro_semiannual"),
])
def test_hydro_urls_follow_registry_and_retain_response_schema(client, interval, year, dataset):
    response = client.get("/api/v1/download/urls", params={
        "data_type": "hydro", "interval": interval, "start_year": year, "end_year": year,
    })
    assert response.status_code == 200
    body = response.json()
    expected = archive_files(dataset, years=(year,))
    assert body["count"] == len(expected)
    assert [item["url"] for item in body["urls"]] == [item.url for item in expected]
    assert all(set(item) == {"url", "filename", "data_type", "interval", "year", "month"} for item in body["urls"])
    assert all(item["data_type"] == "dane_hydrologiczne" for item in body["urls"])


@pytest.mark.parametrize("subtype,year", [("klimat", 1999), ("klimat", 2024), ("opad", 1950), ("opad", 2024)])
def test_both_meteo_url_endpoints_enumerate_same_registry(client, subtype, year):
    dataset = "pl.imgw.meteo_precip_daily" if subtype == "opad" else "pl.imgw.meteo_climate_daily"
    expected = [item.url for item in archive_files(dataset, years=(year,))]
    params = {"interval": "dobowe", "subtype": subtype, "start_year": year, "end_year": year}
    unified = client.get("/api/v1/download/urls", params={**params, "data_type": "meteo"})
    specialized = client.post("/api/v1/meteo/download-urls", params=params)
    assert unified.status_code == specialized.status_code == 200
    assert [item["url"] for item in unified.json()["urls"]] == expected
    assert [item["url"] for item in specialized.json()["urls"]] == expected
    assert unified.json()["count"] == specialized.json()["count"] == len(expected)


def test_single_urls_match_registry_and_keep_legacy_shape(client):
    hydro = client.get("/api/v1/download/url", params={
        "data_type": "hydro", "interval": "dobowe", "year": 2022, "month": 2,
    })
    assert hydro.status_code == 200
    assert hydro.json() == {
        "url": archive_files("pl.imgw.hydro_daily", years=(2022,), months=(2,))[0].url,
        "filename": "codz_2022_02.zip", "data_type": "dane_hydrologiczne",
        "interval": "dobowe", "year": 2022, "month": 2,
    }
    meteo = client.post("/api/v1/meteo/download-url", json={
        "interval": "dobowe", "subtype": "opad", "year": 2024, "month": 2,
    })
    assert meteo.status_code == 200
    assert meteo.json()["url"] == archive_files("pl.imgw.meteo_precip_daily", years=(2024,), months=(2,))[0].url
    assert meteo.json()["filename"] == "2024_02_o.zip"
    legacy = client.get("/api/v1/download/url", params={
        "data_type": "meteo", "interval": "miesieczne", "subtype": "synop", "year": 2024,
    })
    assert legacy.status_code == 200
    assert legacy.json()["filename"] == "2024_m_s.zip"


@pytest.mark.parametrize("year,subtype", [(1950, "opad"), (2027, "klimat")])
def test_meteo_post_accepts_supported_historical_and_future_years(client, year, subtype):
    response = client.post("/api/v1/meteo/download-url", json={
        "interval": "dobowe", "subtype": subtype, "year": year, "month": 2,
    })
    dataset = "pl.imgw.meteo_precip_daily" if subtype == "opad" else "pl.imgw.meteo_climate_daily"
    assert response.status_code == 200
    assert response.json()["url"] == archive_files(dataset, years=(year,), months=(2,))[0].url


@pytest.mark.parametrize("params", [
    {"data_type": "hydro", "interval": "polroczne_i_roczne", "year": 2024},
    {"data_type": "meteo", "interval": "dobowe", "subtype": "synop", "year": 2024, "month": 2},
    {"data_type": "meteo", "interval": "dobowe", "subtype": "opad", "year": 2024},
    {"data_type": "hydro", "interval": "dobowe", "year": 1950, "month": 1},
])
def test_invalid_single_combination_is_client_error(client, params):
    response = client.get("/api/v1/download/url", params=params)
    assert response.status_code == 400
    assert response.json()["detail"]


def test_invalid_range_does_not_return_partial_urls(client):
    response = client.get("/api/v1/download/urls", params={
        "data_type": "meteo", "interval": "dobowe", "subtype": "klimat", "start_year": 1950, "end_year": 1951,
    })
    assert response.status_code == 400
