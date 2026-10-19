"""Application-level behavior of the FastAPI app: system routes, middleware, server."""

import runpy
import sys

import pytest
import uvicorn
from fastapi.testclient import TestClient

import imgwtools
from imgwtools.api.main import app, run_server
from imgwtools.config import settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    return calls


def test_api_main_health_reports_package_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": imgwtools.__version__}


def test_api_main_info_names_the_api_and_links_the_catalog_schema(client):
    response = client.get("/api/v1")
    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["version"]) == ("IMGWTools API", imgwtools.__version__)
    schema = client.get(body["schema"])
    assert schema.json()["result"]["schema"] == "imgw-commands/1"
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["version"] == imgwtools.__version__


def test_api_main_cors_preflight_allows_any_origin(client):
    response = client.options(
        "/api/v1/stations/find",
        headers={
            "Origin": "https://raba.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://raba.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


def test_api_main_cors_simple_request_echoes_origin(client):
    response = client.get("/health", headers={"Origin": "https://raba.example"})
    assert response.headers["access-control-allow-origin"] == "https://raba.example"
    assert "access-control-allow-origin" not in client.get("/health").headers


def test_api_main_gzip_applies_only_above_threshold(client):
    large = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    small = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert large.headers["content-encoding"] == "gzip"
    assert "content-encoding" not in small.headers


@pytest.mark.parametrize(
    "path,content_type",
    [("/static/css/style.css", "text/css"), ("/static/js/app.js", "javascript")],
)
def test_api_main_serves_static_assets(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


def test_api_main_unknown_static_file_is_404(client):
    assert client.get("/static/css/brak.css").status_code == 404


@pytest.mark.parametrize("env,reload", [("development", True), ("production", False)])
def test_api_main_run_server_uses_settings(monkeypatch, uvicorn_calls, env, reload):
    monkeypatch.setattr(settings, "env", env)
    monkeypatch.setattr(settings, "host", "127.0.0.5")
    monkeypatch.setattr(settings, "port", 8123)
    run_server()
    assert uvicorn_calls == [
        (
            ("imgwtools.api.main:app",),
            {"host": "127.0.0.5", "port": 8123, "reload": reload},
        )
    ]


def test_api_main_module_entrypoint_starts_server(monkeypatch, uvicorn_calls):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.delitem(sys.modules, "imgwtools.api.main")
    runpy.run_module("imgwtools.api.main", run_name="__main__")
    assert [args for args, _ in uvicorn_calls] == [("imgwtools.api.main:app",)]
