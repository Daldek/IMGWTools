"""REST routes of the versioned store: configuration guards, confinement, parity."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from imgwtools.api.main import app
from imgwtools.api.routes import store as store_routes
from imgwtools.config import Settings, settings
from imgwtools.core.url_builder import IMGW_PUBLIC_DATA_URL
from imgwtools.datasets import archive_files
from imgwtools.store import export_series, init_store, read_series, read_series_index
from imgwtools.store.types import (
    CatalogReport,
    OperationResult,
    SeriesReport,
    SyncReport,
)
from imgwtools.testing import build_fixture_store

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDINGS = {
    row["case"]: row
    for row in json.loads((FIXTURES / "recordings.json").read_text())["interactions"]
}
HYDRO = "pl.imgw.hydro_daily"
H2024 = archive_files(HYDRO, years=[2024])[0]
TOKEN = "s3cret-token"
WRITES = [
    ("/api/v1/store/sync", {"datasets": [HYDRO], "years": [2024]}),
    ("/api/v1/store/catalog", {}),
    ("/api/v1/series/build", {"dataset": HYDRO}),
    (
        "/api/v1/series/export",
        {
            "version": "series/versions/hydro_daily/x/series.json",
            "station": "149190310",
            "variables": ["Q"],
        },
    ),
    (
        "/api/v1/pmaxtp/store/sync",
        {"method": "POT", "latitude": 52.23, "longitude": 21.01},
    ),
]


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture(autouse=True)
def unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "store_root", None)
    monkeypatch.setattr(settings, "store_writes_enabled", False)
    monkeypatch.setattr(settings, "store_write_token", None)
    monkeypatch.setattr(settings, "user_locations_dir", None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("fx") / "store").root


@pytest.fixture
def served(monkeypatch, fixture_root):
    monkeypatch.setattr(settings, "store_root", fixture_root)
    return fixture_root


@pytest.fixture
def writable(monkeypatch):
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token", SecretStr(TOKEN))
    return {"X-API-Key": TOKEN}


def series_version(root, slug="hydro_daily"):
    versions = sorted((root / "series" / "versions" / slug).iterdir())
    return versions[-1].relative_to(root).as_posix()


def test_store_settings_come_from_imgw_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("IMGW_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("IMGW_STORE_WRITES_ENABLED", "true")
    monkeypatch.setenv("IMGW_STORE_WRITE_TOKEN", TOKEN)
    monkeypatch.setenv("IMGW_USER_LOCATIONS_DIR", str(tmp_path))

    configured = Settings(_env_file=None)

    assert configured.store_root == tmp_path
    assert configured.store_writes_enabled is True
    assert configured.store_write_token is not None
    assert configured.store_write_token.get_secret_value() == TOKEN
    assert configured.user_locations_dir == tmp_path


def test_store_routes_are_documented_in_openapi(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/v1/store/info",
        "/api/v1/store/entries",
        "/api/v1/store/check",
        "/api/v1/store/sync",
        "/api/v1/store/catalog",
        "/api/v1/series/build",
        "/api/v1/series/index",
        "/api/v1/series/{station}",
        "/api/v1/series/export",
        "/api/v1/pmaxtp/store/sync",
    ):
        assert path in paths
    assert "StoreWriteToken" in response.json()["components"]["securitySchemes"]


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/v1/store/info", None),
        ("GET", "/api/v1/store/entries", None),
        ("GET", "/api/v1/series/index?version=series/versions/x/y", None),
        ("POST", "/api/v1/store/check", {"datasets": [HYDRO], "years": [2024]}),
    ],
)
@pytest.mark.parametrize("root", [None, "relative/store"])
def test_store_routes_answer_503_without_absolute_root(
    client, monkeypatch, method, path, body, root
):
    monkeypatch.setattr(settings, "store_root", None if root is None else Path(root))

    response = client.request(method, path, json=body)

    assert response.status_code == 503
    assert set(response.json()) == {"code", "detail"}
    assert "IMGW_STORE_ROOT" in response.json()["detail"]


def test_url_generator_stays_available_without_store(client):
    response = client.get("/api/v1/download/datasets")

    assert response.status_code == 200


def test_unsupported_root_is_described_but_not_operated_on(
    client, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "store_root", tmp_path)

    info = client.get("/api/v1/store/info")
    check = client.post(
        "/api/v1/store/check", json={"datasets": [HYDRO], "years": [2024]}
    )

    assert info.status_code == 200
    assert info.json()["supported"] is False
    assert info.json()["problems"]
    assert check.status_code == 503
    assert check.json()["code"] == "store_unavailable"


def test_info_and_entries_report_store_offline_with_relative_paths(client, served):
    info = client.get("/api/v1/store/info").json()
    entries = client.get("/api/v1/store/entries", params={"kind": "series"}).json()

    assert info["supported"] is True
    assert info["schema"] == "imgw-store/1"
    assert info["root"] == "."
    assert {entry["slot"] for entry in entries} == {
        "series:hydro_daily",
        "series:meteo_precip_daily",
    }
    for entry in entries:
        assert entry["version"].startswith("series/versions/")
        assert (served / entry["version"]).is_file()
        assert len(entry["meta"]["sha256"]) == 64


def test_entries_reject_unknown_kind_with_polish_error(client, served):
    response = client.get("/api/v1/store/entries", params={"kind": "bogus"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "bogus" in response.json()["detail"]


def test_series_index_and_records_match_python_api(client, served):
    version = series_version(served)
    index = read_series_index(served / version)
    station = sorted(index.stations)[0]
    expected = list(read_series(served / version, station=station, variables=["Q"]))

    body = client.get("/api/v1/series/index", params={"version": version}).json()
    records = client.get(
        f"/api/v1/series/{station}", params={"version": version, "variables": "Q"}
    ).json()
    bounded = client.get(
        f"/api/v1/series/{station}",
        params={
            "version": version,
            "variables": "Q",
            "start": expected[1].date.isoformat(),
            "end": expected[1].date.isoformat(),
        },
    ).json()

    assert body["dataset"] == HYDRO
    assert body["stations"][station]["sha256"] == index.stations[station].sha256
    assert [row["date"] for row in records] == [r.date.isoformat() for r in expected]
    assert [row["measurements"]["Q"] for row in records] == [
        {"value": r.measurements["Q"].value, "flag": r.measurements["Q"].flag}
        for r in expected
    ]
    assert [row["date"] for row in bounded] == [expected[1].date.isoformat()]


def test_series_read_rejects_station_outside_series(client, served):
    response = client.get(
        "/api/v1/series/999999999",
        params={"version": series_version(served), "variables": "Q"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    "version",
    [
        "/etc/passwd",
        "../store/series/versions/hydro_daily",
        "series/versions/../../imgw-store.json",
        "series/versions/hydro_daily/./x",
        "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024",
        "stations/versions",
        "series\\versions\\hydro_daily",
    ],
)
def test_series_version_is_confined_to_series_versions(client, served, version):
    response = client.get("/api/v1/series/index", params={"version": version})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_missing_series_version_is_404(client, served):
    response = client.get(
        "/api/v1/series/index",
        params={"version": "series/versions/hydro_daily/2000-01-01_00000000"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_series_version_through_symlink_is_rejected(client, monkeypatch, tmp_path):
    root = build_fixture_store(tmp_path / "store").root
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "series" / "versions" / "linked").symlink_to(outside)
    monkeypatch.setattr(settings, "store_root", root)

    response = client.get(
        "/api/v1/series/index", params={"version": "series/versions/linked/x"}
    )

    assert response.status_code == 400
    assert "dowiązanie" in response.json()["detail"]


def test_store_error_detail_hides_absolute_root(client, monkeypatch, tmp_path):
    root = build_fixture_store(tmp_path / "store").root
    monkeypatch.setattr(settings, "store_root", root)
    version = series_version(root)
    parquet = sorted((root / version).glob("stations/*.parquet"))[0]
    parquet.write_bytes(b"corrupted")

    response = TestClient(app, raise_server_exceptions=False).get(
        f"/api/v1/series/{parquet.stem}", params={"version": version, "variables": "Q"}
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert str(tmp_path) not in detail
    assert parquet.relative_to(root).as_posix() in detail


def test_sync_report_text_hides_absolute_root_only(
    client, empty_root, writable, monkeypatch
):
    sibling = Path(f"{empty_root}-old") / "x.zip"
    report = SyncReport(
        items=(
            OperationResult(
                "archive:x",
                "failed",
                None,
                f"Uszkodzona wersja archiwum: {empty_root / 'archives' / 'x'}; "
                f"zob. {sibling}; magazyn {empty_root}",
            ),
        ),
        series=(
            SeriesReport(
                "failed", None, 0, (), (f"Nie można odczytać {empty_root}/a.parquet",)
            ),
        ),
        cancelled=False,
    )
    monkeypatch.setattr(store_routes, "run_command", lambda command, options: report)

    body = client.post(
        "/api/v1/store/sync",
        json={"datasets": [HYDRO], "years": [2024]},
        headers=writable,
    ).json()

    assert body["items"][0]["error"] == (
        f"Uszkodzona wersja archiwum: archives/x; zob. {sibling}; magazyn ."
    )
    assert body["series"][0]["problems"] == ["Nie można odczytać a.parquet"]


def test_catalog_problems_hide_data_dir(client, empty_root, writable, monkeypatch):
    data_dir = empty_root.parent / "refdata"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    report = CatalogReport(
        "created",
        empty_root / "stations" / "versions" / "x" / "stations.geojson",
        1,
        1,
        (
            f"Brak lokalnego pliku położeń {data_dir / 'hydro_stations_locations.csv'}; "
            "stacje bez położenia",
        ),
    )
    monkeypatch.setattr(store_routes, "run_command", lambda command, options: report)

    body = client.post("/api/v1/store/catalog", json={}, headers=writable).json()

    assert body["problems"] == [
        "Brak lokalnego pliku położeń hydro_stations_locations.csv; stacje bez położenia"
    ]
    assert body["version"] == "stations/versions/x/stations.geojson"


@pytest.mark.parametrize("path,body", WRITES)
def test_writes_are_forbidden_by_default_and_leave_store_untouched(
    client, served, path, body
):
    before = tree(served)

    response = client.post(path, json=body, headers={"X-API-Key": TOKEN})

    assert response.status_code == 403
    assert response.json()["code"] == "writes_disabled"
    assert tree(served) == before


@pytest.mark.parametrize(
    "token,headers,code",
    [
        (None, {"X-API-Key": TOKEN}, "write_token_missing"),
        (SecretStr(""), {"X-API-Key": ""}, "write_token_missing"),
        (SecretStr(TOKEN), {}, "invalid_api_key"),
        (SecretStr(TOKEN), {"X-API-Key": TOKEN + "x"}, "invalid_api_key"),
        (SecretStr(TOKEN), {"X-API-Key": "ąę".encode()}, "invalid_api_key"),
    ],
)
@pytest.mark.parametrize("path,body", WRITES)
def test_enabled_writes_need_configured_token_and_matching_header(
    client, served, monkeypatch, token, headers, code, path, body
):
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token", token)

    response = client.post(path, json=body, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == code


def test_authorized_write_without_root_is_503(client, writable):
    response = client.post(
        "/api/v1/series/build", json={"dataset": HYDRO}, headers=writable
    )

    assert response.status_code == 503
    assert response.json()["code"] == "store_not_configured"


def test_authorized_series_build_returns_full_report(
    client, monkeypatch, tmp_path, writable
):
    root = build_fixture_store(tmp_path / "store").root
    monkeypatch.setattr(settings, "store_root", root)

    built = client.post(
        "/api/v1/series/build",
        json={"dataset": "pl.imgw.meteo_precip_daily"},
        headers=writable,
    )
    again = client.post(
        "/api/v1/series/build",
        json={"dataset": "pl.imgw.meteo_precip_daily"},
        headers=writable,
    )

    assert built.status_code == 200
    assert built.json()["status"] == "created"
    assert (root / built.json()["version"]).is_file()
    assert again.json()["status"] == "reused"
    assert again.json()["version"] == built.json()["version"]


def test_client_cannot_supply_root_or_output_path(client, served, writable):
    check = client.post(
        "/api/v1/store/check",
        json={"datasets": [HYDRO], "years": [2024], "root": "/tmp/other"},
    )
    export = client.post(
        "/api/v1/series/export",
        json={
            "version": series_version(served),
            "station": "149190310",
            "variables": ["Q"],
            "path": "/tmp/out.csv",
        },
        headers=writable,
    )

    assert check.status_code == 422
    assert export.status_code == 422


def test_series_export_streams_csv_and_removes_temporary_file(
    client, served, writable, monkeypatch, tmp_path
):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    version = series_version(served)
    station = sorted(read_series_index(served / version).stations)[0]
    before = tree(served)

    response = client.post(
        "/api/v1/series/export",
        json={"version": version, "station": station, "variables": ["Q"]},
        headers=writable,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    expected = export_series(
        served / version, station=station, path=tmp_path / "py.csv", variables=["Q"]
    )
    assert response.content == expected.read_bytes()
    assert list(scratch.iterdir()) == []
    assert tree(served) == before


def test_failed_series_export_removes_temporary_file(
    client, served, writable, monkeypatch, tmp_path
):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))

    response = client.post(
        "/api/v1/series/export",
        json={
            "version": series_version(served),
            "station": "999999999",
            "variables": ["Q"],
        },
        headers=writable,
    )

    assert response.status_code == 400
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    "name", ["../locations.csv", "sub/locations.csv", "..", "a\\b.csv"]
)
def test_catalog_accepts_only_basename_from_configured_directory(
    client, served, writable, monkeypatch, tmp_path, name
):
    monkeypatch.setattr(settings, "user_locations_dir", tmp_path)

    response = client.post(
        "/api/v1/store/catalog", json={"user_locations": name}, headers=writable
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_catalog_user_locations_need_server_directory_and_regular_file(
    client, served, writable, monkeypatch, tmp_path
):
    real = tmp_path / "real.csv"
    real.write_text("station_code,lon,lat,source\n", encoding="utf-8")
    (tmp_path / "link.csv").symlink_to(real)

    unconfigured = client.post(
        "/api/v1/store/catalog", json={"user_locations": "real.csv"}, headers=writable
    )
    monkeypatch.setattr(settings, "user_locations_dir", tmp_path)
    linked = client.post(
        "/api/v1/store/catalog", json={"user_locations": "link.csv"}, headers=writable
    )
    missing = client.post(
        "/api/v1/store/catalog", json={"user_locations": "none.csv"}, headers=writable
    )

    assert unconfigured.status_code == 400
    assert "IMGW_USER_LOCATIONS_DIR" in unconfigured.json()["detail"]
    assert linked.status_code == 400
    assert missing.status_code == 404


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{IMGW_PUBLIC_DATA_URL}/dane_hydrologiczne/dobowe/2024/").mock(
            return_value=httpx.Response(200, text=RECORDINGS["hydro_listing"]["body"])
        )
        yield mock


@pytest.fixture
def empty_root(monkeypatch, tmp_path):
    root = init_store(tmp_path / "store").root
    monkeypatch.setattr(settings, "store_root", root)
    return root


def test_check_returns_portable_plan_without_writing_to_root(client, empty_root, imgw):
    imgw.head(H2024.url).mock(
        return_value=httpx.Response(200, headers=RECORDINGS["hydro_head"]["headers"])
    )
    archive_get = imgw.get(H2024.url)
    before = tree(empty_root)

    response = client.post(
        "/api/v1/store/check", json={"datasets": [HYDRO], "years": [2024]}
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["schema"] == "imgw-plan/1"
    assert plan["root"] == "."
    assert [item["status"] for item in plan["items"]] == ["missing"]
    assert tree(empty_root) == before
    assert not archive_get.called


def test_sync_from_checked_plan_downloads_and_reports(
    client, empty_root, imgw, writable
):
    headers = RECORDINGS["hydro_head"]["headers"]
    imgw.head(H2024.url).mock(return_value=httpx.Response(200, headers=headers))
    imgw.get(H2024.url).mock(
        return_value=httpx.Response(
            200,
            headers=headers,
            content=(FIXTURES / "archives" / H2024.server_path).read_bytes(),
        )
    )
    plan = client.post(
        "/api/v1/store/check", json={"datasets": [HYDRO], "years": [2024]}
    ).json()

    response = client.post(
        "/api/v1/store/sync", json={"plan": plan, "series": False}, headers=writable
    )

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert item["status"] == "created"
    assert (empty_root / item["version"]).is_file()
    assert response.json()["series"] == []


def test_sync_with_changed_source_is_409_with_report(
    client, empty_root, imgw, writable
):
    head = imgw.head(H2024.url)
    head.mock(
        return_value=httpx.Response(200, headers=RECORDINGS["hydro_head"]["headers"])
    )
    plan = client.post(
        "/api/v1/store/check", json={"datasets": [HYDRO], "years": [2024]}
    ).json()
    head.mock(
        return_value=httpx.Response(
            200, headers=RECORDINGS["changed_after_check"]["headers"]
        )
    )
    archive_get = imgw.get(H2024.url)

    response = client.post(
        "/api/v1/store/sync", json={"plan": plan, "series": False}, headers=writable
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_plan"
    assert response.json()["report"]["items"][0]["status"] == "stale_plan"
    assert not archive_get.called


@pytest.mark.parametrize(
    "plan,code",
    [
        ({"schema": "imgw-plan/1", "root": "/elsewhere"}, "validation_error"),
        ({"schema": "imgw-plan/9", "root": "."}, "invalid_plan"),
    ],
)
def test_sync_rejects_foreign_or_invalid_plan(client, empty_root, writable, plan, code):
    response = client.post("/api/v1/store/sync", json={"plan": plan}, headers=writable)

    assert response.status_code == 400
    assert response.json()["code"] == code


def test_sync_rejects_plan_together_with_selectors(client, empty_root, imgw, writable):
    imgw.head(H2024.url).mock(
        return_value=httpx.Response(200, headers=RECORDINGS["hydro_head"]["headers"])
    )
    plan = client.post(
        "/api/v1/store/check", json={"datasets": [HYDRO], "years": [2024]}
    ).json()

    response = client.post(
        "/api/v1/store/sync",
        json={"plan": plan, "datasets": [HYDRO], "years": [2024]},
        headers=writable,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_pmaxtp_source_outage_is_502_without_new_version(client, empty_root, writable):
    before = tree(empty_root)
    with respx.mock() as mock:
        mock.get(RECORDINGS["pmaxtp_pot_first"]["url"]).mock(
            side_effect=httpx.ConnectTimeout("timeout")
        )
        response = client.post(
            "/api/v1/pmaxtp/store/sync",
            json={"method": "POT", "latitude": 52.23, "longitude": 21.01},
            headers=writable,
        )

    assert response.status_code == 502
    assert response.json()["code"] == "source_unavailable"
    assert tree(empty_root) == before


def test_pmaxtp_point_outside_grid_is_400_without_new_version(
    client, empty_root, writable
):
    before = tree(empty_root)
    with respx.mock() as mock:
        mock.get(RECORDINGS["pmaxtp_pot_first"]["url"]).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {},
                    "error": "Brak pliku, pradopodobnie poza obszarem PL",
                },
            )
        )
        response = client.post(
            "/api/v1/pmaxtp/store/sync",
            json={"method": "POT", "latitude": 52.23, "longitude": 21.01},
            headers=writable,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "poza siatką PMAXTP" in response.json()["detail"]
    assert tree(empty_root) == before


def test_pmaxtp_store_sync_stores_cell(client, empty_root, writable):
    recording = RECORDINGS["pmaxtp_pot_first"]
    with respx.mock(assert_all_called=True) as mock:
        mock.get(recording["url"]).mock(
            return_value=httpx.Response(200, json=recording["json"])
        )
        response = client.post(
            "/api/v1/pmaxtp/store/sync",
            json={"method": "POT", "latitude": 52.23, "longitude": 21.01},
            headers=writable,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert (body["ind_x"], body["ind_y"]) == (751, 317)
    assert body["version"].startswith("pmaxtp/versions/POT/751_317/")
    assert (empty_root / body["version"]).is_file()
    assert body["result"]["method"] == "POT"
