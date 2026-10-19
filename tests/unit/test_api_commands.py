"""REST adapter generated from the command catalog (spec §13.5, §13.6, §13.10)."""

import functools
import importlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from imgwtools.api.main import app
from imgwtools.commands import check_command, command_schema, run_command
from imgwtools.config import Settings, settings
from imgwtools.exceptions import ERROR_CODES
from imgwtools.stations import HYDRO_MAP_API_URL
from imgwtools.store import current_version, init_store
from imgwtools.testing import build_fixture_store
from tests.contract.support import (
    DAILY,
    H2023,
    H2024,
    NEW,
    OLD,
    PRECIP,
    RABA,
    V1,
    V2,
    V3,
    FakeImgw,
    archive_bytes,
    schema_errors,
    stamps,
)

API = "https://danepubliczne.imgw.pl/api/data"
TOKEN = "s3cret-token"
FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
# Placeholder of the current hydro_daily series version (relative to the root).
SERIES = "<series>"
SYNOP = [{"id_stacji": "12999", "stacja": "Raba Górna", "temperatura": "7.5"}]
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
MAP = {"stations": [{"id": RABA, "n": "RABA GÓRNA", "la": 49.61, "lo": 20.05}]}
# Read commands (GET): command, query, whether the server inserts its root.
GET_CASES = [
    ("datasets list", {"kind": "hydro", "limit": "2", "offset": "1"}, False),
    (
        "datasets files",
        {"dataset": "hydro/dobowe", "years": ["2022-2023", "2024"], "months": "1,2"},
        False,
    ),
    (
        "stations find",
        {"kind": "hydro", "query": "raba", "provider": "IMGW-PIB"},
        False,
    ),
    ("stations find", {"source": "store", "query": "1491"}, True),
    ("current hydro", {}, False),
    ("current meteo", {}, False),
    ("current synop", {"station_name": "raba"}, False),
    ("current warnings", {"kind": "meteo"}, False),
    ("current hydro-states", {"main_only": "true"}, False),
    ("pmaxtp fetch", {"latitude": "52.23", "longitude": "21.01"}, False),
    ("pmaxtp url", {"latitude": "52.23", "longitude": "21.01", "method": "AMP"}, False),
    (
        "pmaxtp check",
        {"latitude": "52.23", "longitude": "21.01", "ind_x": "751", "ind_y": "317"},
        True,
    ),
    ("store info", {}, True),
    ("store scan", {"kind": "series"}, True),
    ("store check", {"datasets": DAILY, "years": "2024"}, True),
    (
        "series select",
        {"dataset": "hydro/dobowe", "stations": RABA, "years": "2024"},
        True,
    ),
    (
        "series read",
        {"dataset": DAILY, "station": RABA, "variables": "H,Q", "start": "2024-01-01"},
        True,
    ),
    ("series read", {"version": SERIES, "station": RABA, "limit": "1"}, True),
    ("series summary", {"version": SERIES, "stations": RABA}, True),
    ("commands schema", {"command": "stations find"}, False),
]
# Write commands (POST): command, body, store the command runs on.
POST_CASES = [
    ("pmaxtp sync", {"latitude": 52.23, "longitude": 21.01}, "empty"),
    ("store sync", {"datasets": ["hydro/dobowe"], "years": [2024]}, "empty"),
    ("store catalog", {}, "fixture"),
    ("series build", {"dataset": PRECIP}, "fixture"),
]


def path_of(command):
    group, name = command.split(" ", 1)
    return f"/api/v1/{group}/{name}"


def problem(response, status, code):
    """Body of a problem+json answer after checking its fixed members."""
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "details",
    }
    assert (body["type"], body["code"], body["status"]) == (
        f"urn:imgwtools:error:{code}",
        code,
        status,
    )
    assert body["title"] == ERROR_CODES[code].title
    assert body["instance"] == response.request.url.path
    assert body["detail"]
    return body


def raising(monkeypatch, module, name, error):
    """Replace a public function (keeping its signature) by one raising ``error``."""
    original = getattr(module, name)

    @functools.wraps(original)
    def fake(*args, **kwargs):
        raise error

    monkeypatch.setattr(module, name, fake)


@pytest.fixture(autouse=True)
def server(monkeypatch):
    """Unconfigured server: no store root, writes disabled, default page size."""
    for name, value in (
        ("store_root", None),
        ("store_writes_enabled", False),
        ("store_write_token", None),
        ("user_locations_dir", None),
        ("api_max_limit", 1000),
    ):
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("rest") / "store").root


@pytest.fixture
def served(monkeypatch, fixture_root):
    monkeypatch.setattr(settings, "store_root", fixture_root)
    return fixture_root


@pytest.fixture
def writable(monkeypatch):
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token", SecretStr(TOKEN))
    return {"X-API-Key": TOKEN}


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=False) as router:
        yield FakeImgw(router)


@pytest.fixture
def live(imgw):
    """Recorded IMGW for every read command: lists, live API, PMAXTP, archives."""
    imgw.publish_catalog_sources()
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    imgw.publish(H2024, V3, NEW)
    imgw.router.get(f"{API}/synop").respond(json=SYNOP)
    imgw.router.get(f"{API}/warningsmeteo").respond(json=METEO_WARNINGS)
    imgw.router.get(HYDRO_MAP_API_URL).respond(json=MAP)
    return imgw


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in (
        "imgwtools.store.writer",
        "imgwtools.store.series",
        "imgwtools.store.catalog",
        "imgwtools.store.sync",
        "imgwtools.store.pmaxtp",
        "imgwtools.commands",
    ):
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)


@pytest.fixture
def empty_root(monkeypatch, tmp_path):
    root = init_store(tmp_path / "store").root
    monkeypatch.setattr(settings, "store_root", root)
    return root


@pytest.fixture
def relative_data_dir(monkeypatch):
    """Relative reference-data directory: no absolute path in envelope texts."""
    monkeypatch.setattr(settings, "data_dir", Path("brak-danych-referencyjnych"))


def store_copy(kind, fixture_root, target):
    if kind == "empty":
        return init_store(target).root
    shutil.copytree(fixture_root, target)
    return target


def relative(entry, root):
    return entry.version.relative_to(root).as_posix()


# --------------------------------------------------------------------------
# Routes, OpenAPI and settings
# --------------------------------------------------------------------------


def test_api_routes_and_openapi_are_generated_from_the_catalog(client):
    expected = {}
    for schema in command_schema()["commands"]:
        rest = schema["x-imgw"]["rest"]
        if rest is not None:
            expected[(rest["method"], rest["path"])] = schema

    document = client.get("/openapi.json").json()
    served = {
        (method.upper(), path): operation
        for path, operations in document["paths"].items()
        if path.startswith("/api/v1/")
        for method, operation in operations.items()
    }

    assert len(expected) == 26
    assert served.keys() == expected.keys()
    assert [
        (route["method"], route["path"])
        for route in client.get("/api/v1").json()["routes"]
    ] == list(expected)
    for key, schema in expected.items():
        operation, meta = served[key], schema["x-imgw"]
        assert operation["operationId"] == meta["command"].replace(" ", "_").replace(
            "-", "_"
        )
        assert operation["tags"] == [meta["group"]]
        assert "422" not in operation["responses"]
        problem_schema = operation["responses"]["4XX"]["content"]
        assert "application/problem+json" in problem_schema
        hidden = {*meta["rest"]["server_options"], *meta["rest"]["local_options"]}
        if key[0] == "GET":
            names = {parameter["name"] for parameter in operation["parameters"]}
        else:
            body = operation["requestBody"]["content"]["application/json"]["schema"]
            names = set(
                document["components"]["schemas"][body["$ref"].split("/")[-1]][
                    "properties"
                ]
            )
            assert operation["security"] == [{"StoreWriteToken": []}]
        assert names == set(schema["properties"]) - hidden
    [limit] = [
        parameter
        for parameter in served[("GET", "/api/v1/stations/find")]["parameters"]
        if parameter["name"] == "limit"
    ]
    assert (limit["schema"]["default"], limit["schema"]["maximum"]) == (1000, 1000)
    tags = {tag["name"]: tag["description"] for tag in document["tags"]}
    assert tags.items() >= command_schema()["groups"].items()


def test_api_settings_come_from_imgw_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("IMGW_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("IMGW_STORE_WRITES_ENABLED", "true")
    monkeypatch.setenv("IMGW_STORE_WRITE_TOKEN", TOKEN)
    monkeypatch.setenv("IMGW_USER_LOCATIONS_DIR", str(tmp_path))
    monkeypatch.setenv("IMGW_API_MAX_LIMIT", "50")

    configured = Settings(_env_file=None)

    assert configured.store_root == configured.user_locations_dir == tmp_path
    assert configured.store_writes_enabled is True
    assert configured.store_write_token is not None
    assert configured.store_write_token.get_secret_value() == TOKEN
    assert configured.api_max_limit == 50
    assert Settings(_env_file=None, api_max_limit=1000).api_max_limit == 1000
    monkeypatch.setenv("IMGW_API_MAX_LIMIT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --------------------------------------------------------------------------
# Envelopes equal to run_command / check_command
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("command", "query", "rooted"), GET_CASES)
def test_api_get_route_answers_the_run_command_envelope(
    client, served, live, frozen, command, query, rooted
):
    series = relative(current_version(served, slot=f"series:{DAILY}"), served)
    query = {key: series if value == SERIES else value for key, value in query.items()}
    options = dict(query)
    if rooted:
        options["root"] = served
    if command_schema(command)["x-imgw"]["result"] == "list":
        options.setdefault("limit", 1000)

    response = client.get(path_of(command), params=query)

    assert response.status_code == 200, response.text
    expected = run_command(command, options=options).to_json(root=served, server=True)
    assert response.json() == expected
    assert str(served.parent) not in response.text
    assert str(Path.cwd()) not in response.text


@pytest.mark.parametrize(("command", "body", "kind"), POST_CASES)
def test_api_post_route_answers_the_run_command_envelope(
    client,
    monkeypatch,
    tmp_path,
    fixture_root,
    imgw,
    frozen,
    relative_data_dir,
    writable,
    command,
    body,
    kind,
):
    imgw.publish(H2024, V1, OLD)
    imgw.publish_catalog_sources()
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    rest_root = store_copy(kind, fixture_root, tmp_path / "rest")
    python_root = store_copy(kind, fixture_root, tmp_path / "python")
    monkeypatch.setattr(settings, "store_root", rest_root)

    response = client.post(path_of(command), json=body, headers=writable)

    assert response.status_code == 200, response.text
    expected = run_command(command, options={**body, "root": python_root})
    assert response.json() == expected.to_json(root=python_root, server=True)
    assert response.json()["status"] == "ok"
    assert str(tmp_path) not in response.text


def test_api_pmaxtp_read_takes_the_version_returned_by_pmaxtp_sync(
    client, empty_root, imgw, writable
):
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    synced = client.post(
        "/api/v1/pmaxtp/sync",
        json={"latitude": "52.23", "longitude": 21.01},
        headers=writable,
    ).json()["result"]
    query = {"ind_x": synced["ind_x"], "ind_y": synced["ind_y"]}

    current = client.get("/api/v1/pmaxtp/read", params=query)
    pinned = client.get(
        "/api/v1/pmaxtp/read", params={**query, "version": synced["version"]}
    )

    assert synced["version"].startswith("pmaxtp/versions/POT/751_317/")
    assert current.json() == pinned.json()
    assert pinned.json() == run_command(
        "pmaxtp read", options={**query, "root": empty_root}
    ).to_json(root=empty_root, server=True)
    assert pinned.json()["result"]["data"] == synced["result"]["data"]


@pytest.mark.parametrize(("command", "body", "kind"), POST_CASES)
def test_api_check_true_plans_every_write_without_token_or_writes(
    client,
    monkeypatch,
    tmp_path,
    fixture_root,
    imgw,
    frozen,
    relative_data_dir,
    command,
    body,
    kind,
):
    imgw.publish(H2024, V1, OLD)
    imgw.publish_catalog_sources()
    root = store_copy(kind, fixture_root, tmp_path / "store")
    monkeypatch.setattr(settings, "store_root", root)
    before = stamps(root)

    response = client.post(f"{path_of(command)}?check=true", json=body)

    assert response.status_code == 200, response.text
    document = response.json()
    assert document["check"] is True
    assert document == check_command(command, options={**body, "root": root}).to_json(
        root=root, server=True
    )
    assert document["result"]["root"] == "."
    assert schema_errors(document["result"], "imgw-plan/1") == []
    assert stamps(root) == before
    assert imgw.downloads() == []


# --------------------------------------------------------------------------
# Store sync: plan round trip, partial envelope, notices
# --------------------------------------------------------------------------


def test_api_checked_plan_syncs_and_a_stale_item_makes_the_envelope_partial(
    client, empty_root, imgw, writable
):
    imgw.publish(H2023, V1, archive_bytes(H2023))
    imgw.publish(H2024, V1, OLD)
    checked = client.get(
        "/api/v1/store/check", params={"datasets": DAILY, "years": "2023-2024"}
    ).json()
    plan = checked["result"]
    imgw.publish(H2024, V2, OLD)  # the server changed after the check

    response = client.post(
        "/api/v1/store/sync", json={"plan": plan, "series": False}, headers=writable
    )

    assert schema_errors(plan, "imgw-plan/1") == []
    assert plan["root"] == "."
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert [(item["slot"], item["status"]) for item in body["result"]["items"]] == [
        (f"archive:{DAILY}:2023/codz_2023.zip", "created"),
        (f"archive:{DAILY}:2024/codz_2024.zip", "stale_plan"),
    ]
    assert (empty_root / body["result"]["items"][0]["version"]).is_file()
    assert "license_terms" in {notice["code"] for notice in body["notices"]}
    assert H2024.url not in imgw.downloads()


@pytest.mark.parametrize(
    ("plan", "fragment"),
    [
        ({"schema": "imgw-plan/1", "root": "/elsewhere"}, "innego magazynu"),
        ({"schema": "imgw-plan/9", "root": "."}, "Niepoprawny plan"),
        (
            {"schema": "imgw-plan/1", "root": ".", "items": [{"archive": {}}]},
            "Niepoprawny plan",
        ),
    ],
)
def test_api_sync_rejects_a_foreign_or_invalid_plan(
    client, empty_root, writable, plan, fragment
):
    response = client.post("/api/v1/store/sync", json={"plan": plan}, headers=writable)

    body = problem(response, 400, "validation_error")
    assert body["details"]["option"] == "plan"
    assert fragment in body["detail"]
    assert list(Path(empty_root).rglob("*.zip")) == []


# --------------------------------------------------------------------------
# Paging and streams
# --------------------------------------------------------------------------


def test_api_list_limit_defaults_to_and_is_capped_by_the_server_maximum(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "api_max_limit", 3)

    default = client.get("/api/v1/datasets/list").json()["result"]
    last = client.get("/api/v1/datasets/list", params={"limit": 3, "offset": 16})
    above = client.get("/api/v1/datasets/list", params={"limit": 4})
    zero = client.get("/api/v1/datasets/list", params={"limit": 0})

    assert (default["limit"], default["offset"], default["total"]) == (3, 0, 17)
    assert len(default["items"]) == 3
    assert len(last.json()["result"]["items"]) == 1
    assert problem(above, 400, "validation_error")["details"] == {
        "option": "limit",
        "value": 4,
        "maximum": 3,
    }
    assert problem(zero, 400, "validation_error")["details"]["option"] == "limit"


@pytest.mark.parametrize(
    ("command", "fmt", "media_type"),
    [
        ("store export", "csv", "text/csv; charset=utf-8"),
        ("store export", "jsonl", "application/x-ndjson"),
        ("series export", "csv", "text/csv; charset=utf-8"),
    ],
)
def test_api_exports_stream_the_cli_lines_with_status_and_notice_headers(
    client, served, command, fmt, media_type
):
    if command == "store export":
        slot = f"archive:{DAILY}:2024/codz_2024.zip"
        query = {"version": relative(current_version(served, slot=slot), served)}
        filename = f"codz_2024.{fmt}"
    else:
        query = {"dataset": DAILY, "station": RABA}
        filename = f"{RABA}.csv"
    query["format"] = fmt
    expected = run_command(command, options={**query, "root": served})
    lines = "".join(expected.result)

    response = client.get(path_of(command), params=query)

    assert response.status_code == 200
    assert response.text == lines
    assert response.headers["content-type"] == media_type
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{filename}"'
    )
    assert response.headers["x-imgw-status"] == "ok"
    notices = response.headers["x-imgw-notices"]
    assert notices.isascii()
    assert json.loads(notices) == [
        {"level": n.level, "code": n.code, "text": n.text} for n in expected.notices
    ]
    assert "license_terms" in {notice["code"] for notice in json.loads(notices)}


# --------------------------------------------------------------------------
# Errors as problem+json
# --------------------------------------------------------------------------


def test_api_catalog_validation_is_400_with_the_library_detail(client):
    response = client.get(
        "/api/v1/pmaxtp/fetch", params={"latitude": "1", "longitude": "21.01"}
    )

    body = problem(response, 400, "validation_error")
    assert (
        body["detail"] == "Szerokość geograficzna 1.0 poza zakresem Polski (49.0–55.0)"
    )
    assert body["details"] == {"option": "latitude", "value": 1.0}


@pytest.mark.parametrize(
    ("body", "option"),
    [
        ({"latitude": {"lat": 52}, "longitude": 21.01}, "latitude"),
        ({"latitude": True, "longitude": 21.01}, "latitude"),
        ({"latitude": 52.23, "longitude": 21.01, "colour": "red"}, "colour"),
        ({"latitude": 52.23, "longitude": 21.01, "root": "/tmp"}, "root"),
    ],
)
def test_api_wrong_body_type_or_field_is_400_with_pydantic_errors(
    client, served, body, option
):
    response = client.post("/api/v1/pmaxtp/sync?check=true", json=body)

    details = problem(response, 400, "validation_error")["details"]
    assert details["errors"]
    assert {error["option"] for error in details["errors"]} == {option}
    assert all(error["message"] for error in details["errors"])


def test_api_unknown_route_and_wrong_method_are_problem_documents(client):
    unknown = client.get("/api/v1/nothing/here")
    wrong = client.delete("/api/v1/store/info")

    assert problem(unknown, 404, "not_found")["detail"] == "Nieznana trasa"
    problem(wrong, 405, "method_not_allowed")
    assert wrong.headers["allow"] == "GET"


@pytest.mark.parametrize(
    ("root", "reason"), [(None, "not_configured"), ("relative/store", "root_invalid")]
)
@pytest.mark.parametrize(
    ("method", "command", "query"),
    [
        ("GET", "store info", {}),
        ("GET", "series summary", {"dataset": DAILY}),
        ("GET", "stations find", {"source": "store"}),
        ("POST", "series build", {"check": "true"}),
    ],
)
def test_api_store_commands_without_a_valid_root_are_503(
    client, monkeypatch, root, reason, method, command, query
):
    monkeypatch.setattr(settings, "store_root", None if root is None else Path(root))

    response = client.request(
        method, path_of(command), params=query, json={"dataset": DAILY}
    )

    body = problem(response, 503, "store_unavailable")
    assert body["details"] == {"reason": reason}
    assert "IMGW_STORE_ROOT" in body["detail"]


def test_api_unsupported_root_is_described_only_by_store_info_and_scan(
    client, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "store_root", tmp_path)

    info = client.get("/api/v1/store/info")
    scan = client.get("/api/v1/store/scan")
    check = client.get("/api/v1/store/check", params={"datasets": DAILY, "years": 2024})

    assert info.status_code == scan.status_code == 200
    assert info.json()["result"]["supported"] is False
    assert info.json()["result"]["root"] == "."
    assert problem(check, 503, "store_unavailable")["details"] == {
        "reason": "unsupported"
    }
    assert str(tmp_path) not in info.text + check.text


def test_api_stations_find_needs_the_root_only_for_the_store_source(client, live):
    found = client.get(
        "/api/v1/stations/find", params={"query": "raba", "provider": "IMGW-PIB"}
    )
    stored = client.get("/api/v1/stations/find", params={"source": "store"})

    assert found.status_code == 200
    assert found.json()["result"]["total"] >= 1
    problem(stored, 503, "store_unavailable")


@pytest.mark.parametrize(
    ("token", "headers", "reason"),
    [
        (None, {"X-API-Key": TOKEN}, "write_token_missing"),
        (SecretStr(""), {"X-API-Key": ""}, "write_token_missing"),
        (SecretStr(TOKEN), {}, "invalid_api_key"),
        (SecretStr(TOKEN), {"X-API-Key": TOKEN + "x"}, "invalid_api_key"),
    ],
)
@pytest.mark.parametrize(("command", "body", "kind"), POST_CASES)
def test_api_writes_need_enabled_writes_and_the_matching_token(
    client, served, monkeypatch, token, headers, reason, command, body, kind
):
    before = stamps(served)
    disabled = client.post(path_of(command), json=body, headers={"X-API-Key": TOKEN})
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token", token)

    refused = client.post(path_of(command), json=body, headers=headers)

    assert problem(disabled, 403, "forbidden")["details"] == {
        "reason": "writes_disabled"
    }
    assert problem(refused, 403, "forbidden")["details"] == {"reason": reason}
    assert stamps(served) == before


def test_api_write_guard_precedes_the_root_check(client, writable):
    response = client.post(
        "/api/v1/series/build", json={"dataset": DAILY}, headers={"X-API-Key": "x"}
    )

    assert problem(response, 403, "forbidden")["details"] == {
        "reason": "invalid_api_key"
    }


def test_api_source_outage_is_502_with_the_imgw_url(client):
    with respx.mock() as router:
        router.get(f"{API}/hydro").mock(return_value=httpx.Response(500))
        response = client.get("/api/v1/current/hydro")

    details = problem(response, 502, "source_unavailable")["details"]
    assert (details["url"], details["reason"], details["status"]) == (
        f"{API}/hydro",
        "http_status",
        500,
    )


def test_api_missing_pyarrow_is_503(client, served, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)

    response = client.get(
        "/api/v1/series/read", params={"dataset": DAILY, "station": RABA}
    )

    assert "pyarrow" in problem(response, 503, "missing_dependency")["detail"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (PermissionError("Brak dostępu do /srv/imgw/x"), 500, "io_error"),
        (RuntimeError("błąd programu"), 500, "internal_error"),
    ],
)
def test_api_file_system_and_program_errors_are_problem_documents(
    monkeypatch, error, status, code
):
    raising(
        monkeypatch, importlib.import_module("imgwtools.datasets"), "datasets", error
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/datasets/list")

    body = problem(response, status, code)
    assert "błąd programu" not in body["detail"]


# --------------------------------------------------------------------------
# Server-side values: version, user locations, refused options, hidden paths
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "version", "status"),
    [
        ("series summary", "/etc/passwd", 400),
        ("series summary", "../store/series/versions/hydro_daily", 400),
        ("series summary", "series/versions/../../imgw-store.json", 400),
        ("series summary", "series/versions/hydro_daily/./x", 400),
        ("series summary", "series//versions/hydro_daily", 400),
        ("series summary", "series\\versions\\hydro_daily", 400),
        ("series summary", "series/versions", 400),
        ("series summary", "archives/versions/dane_hydrologiczne/dobowe", 400),
        ("store export", "series/versions/hydro_daily", 400),
        ("pmaxtp read", "archives/versions/dane_hydrologiczne", 400),
        ("series summary", "series/versions/hydro_daily/2000-01-01_00000000", 404),
        ("store export", "archives/versions/dane_hydrologiczne/brak", 404),
    ],
)
def test_api_version_is_confined_to_the_versions_directory_of_the_command(
    client, served, command, version, status
):
    query = {"version": version}
    if command == "pmaxtp read":
        query.update(ind_x=751, ind_y=317)

    response = client.get(path_of(command), params=query)

    code = "validation_error" if status == 400 else "not_found"
    assert problem(response, status, code)["details"] == {
        "option": "version",
        "value": version,
    }


def test_api_version_through_a_symlink_is_rejected(client, monkeypatch, tmp_path):
    root = build_fixture_store(tmp_path / "store").root
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "series" / "versions" / "linked").symlink_to(outside)
    monkeypatch.setattr(settings, "store_root", root)

    response = client.get(
        "/api/v1/series/summary", params={"version": "series/versions/linked/x"}
    )

    assert "dowiązanie" in problem(response, 400, "validation_error")["detail"]


@pytest.mark.parametrize(
    ("method", "command", "query", "body", "option"),
    [
        ("GET", "store info", {"root": "/tmp"}, None, "root"),
        ("GET", "stations find", {"root": "/tmp", "source": "store"}, None, "root"),
        (
            "GET",
            "store export",
            {"version": "archives/versions/x", "path": "/tmp/x.csv"},
            None,
            "path",
        ),
        (
            "GET",
            "store check",
            {"datasets": DAILY, "years": "2024", "plan": "/tmp/p.json"},
            None,
            "plan",
        ),
        (
            "GET",
            "datasets files",
            {"dataset": DAILY, "years": "2024", "output": "/tmp"},
            None,
            "output",
        ),
        ("GET", "datasets list", {"check": "true"}, None, "check"),
        ("GET", "datasets list", {"kind": ["hydro", "meteo"]}, None, "kind"),
        ("POST", "series build", {"dataset": DAILY, "check": "true"}, {}, "dataset"),
        ("POST", "series build", {"check": "yes"}, {"dataset": DAILY}, "check"),
    ],
)
def test_api_refuses_server_local_unknown_and_repeated_options(
    client, served, method, command, query, body, option
):
    before = stamps(served)

    response = client.request(method, path_of(command), params=query, json=body)

    assert problem(response, 400, "validation_error")["details"]["option"] == option
    assert stamps(served) == before


def test_api_catalog_user_locations_come_only_from_the_server_directory(
    client, served, imgw, monkeypatch, tmp_path
):
    imgw.publish_catalog_sources()
    locations = tmp_path / "locations"
    locations.mkdir()
    (locations / "moje.csv").write_text(
        f"station_code,latitude,longitude,source\n{RABA},49.61,20.05,gps\n",
        encoding="utf-8",
    )
    (locations / "link.csv").symlink_to(locations / "moje.csv")

    def check(name):
        return client.post(
            "/api/v1/store/catalog?check=true", json={"user_locations": name}
        )

    unconfigured = check("moje.csv")
    monkeypatch.setattr(settings, "user_locations_dir", locations)
    answers = {
        name: check(name)
        for name in ("moje.csv", "../moje.csv", "link.csv", "brak.csv")
    }

    assert problem(unconfigured, 503, "store_unavailable")["details"] == {
        "reason": "user_locations_dir_invalid"
    }
    assert answers["moje.csv"].status_code == 200
    assert answers["moje.csv"].json()["check"] is True
    for name, status, code in (
        ("../moje.csv", 400, "validation_error"),
        ("link.csv", 400, "validation_error"),
        ("brak.csv", 404, "not_found"),
    ):
        details = problem(answers[name], status, code)["details"]
        assert details == {"option": "user_locations", "value": name}
    assert str(tmp_path) not in "".join(answer.text for answer in answers.values())


def test_api_answers_hide_server_directories_in_texts(
    client, imgw, writable, monkeypatch, tmp_path, fixture_root, isolated_data_dir
):
    imgw.publish_catalog_sources()
    root = store_copy("fixture", fixture_root, tmp_path / "store")
    monkeypatch.setattr(settings, "store_root", root)

    response = client.post("/api/v1/store/catalog", json={}, headers=writable)
    missing = client.get(
        "/api/v1/store/export", params={"version": "archives/versions/brak"}
    )

    problems = response.json()["result"]["problems"]
    assert any("hydro_stations_locations.csv" in text for text in problems)
    assert str(isolated_data_dir) not in response.text
    assert str(tmp_path) not in response.text + missing.text


def test_api_hiding_a_server_directory_keeps_imgw_urls_intact(client, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", Path("/data"))

    response = client.get(
        "/api/v1/datasets/files", params={"dataset": DAILY, "years": "2024"}
    )

    [item] = response.json()["result"]["items"]
    assert item["url"] == H2024.url
    assert "/data/dane_pomiarowo_obserwacyjne/" in item["url"]
