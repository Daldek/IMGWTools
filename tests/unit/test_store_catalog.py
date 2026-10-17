"""Offline scenarios for the versioned station catalog (recorded HTTP only)."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools.datasets import station_source_files
from imgwtools.exceptions import IMGWConnectionError, IMGWDataError
from imgwtools.store import catalog, init_store
from imgwtools.store.catalog import build_catalog, check_catalog

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDINGS = {
    item["case"]: item
    for item in json.loads((FIXTURES / "recordings.json").read_text(encoding="utf-8"))[
        "interactions"
    ]
}
HYDRO_LIST, METEO_LIST = station_source_files()
HYDRO_CSV = (FIXTURES / "archives" / HYDRO_LIST.server_path).read_bytes()
METEO_CSV = (FIXTURES / "archives" / METEO_LIST.server_path).read_bytes()
LIST_HEADERS = {"ETag": '"list-v1"', "Last-Modified": "Sat, 17 Oct 2026 12:00:00 GMT"}
PROPERTIES = {
    "station_code",
    "kind",
    "meteo_kind",
    "name",
    "river",
    "hydrographic_code",
    "river_order",
    "location_source",
    "location_uncertainty_m",
    "location_missing_reason",
    "active",
    "established_year",
    "gauge_zero_m",
    "river_km",
    "elevation_m",
}


def cp1250(*rows: str) -> bytes:
    return ("\r\n".join(rows) + "\r\n").encode("cp1250")


def mock_sources(
    router,
    *,
    hydro_csv=HYDRO_CSV,
    meteo_csv=METEO_CSV,
    hydro_api=None,
    meteo_api=None,
    list_headers=LIST_HEADERS,
):
    """Register recorded station sources; anything else (e.g. hydro-back) is unmocked."""
    routes = {}
    for name, archive, body in (
        ("hydro", HYDRO_LIST, hydro_csv),
        ("meteo", METEO_LIST, meteo_csv),
    ):
        routes[f"{name}_get"] = router.get(archive.url).mock(
            return_value=httpx.Response(200, content=body, headers=list_headers)
        )
        routes[f"{name}_head"] = router.head(archive.url).mock(
            return_value=httpx.Response(200, headers=list_headers)
        )
    for name, case, override in (
        ("hydro", "hydro_current", hydro_api),
        ("meteo", "meteo_current", meteo_api),
    ):
        entry = RECORDINGS[case]
        routes[f"{name}_api"] = router.get(entry["url"]).mock(
            return_value=httpx.Response(
                200, json=entry["json"] if override is None else override
            )
        )
    routes["hydro_back"] = router.route(host="hydro-back.imgw.pl").mock(
        return_value=httpx.Response(500)
    )
    return routes


def features(report):
    document = json.loads(report.version.read_text(encoding="utf-8"))
    return {feature["id"]: feature for feature in document["features"]}


def tree(root: Path):
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture
def store(tmp_path):
    return init_store(tmp_path / "store")


def test_lists_are_archived_first_and_all_codes_are_kept(store):
    meteo_with_history = METEO_CSV + cp1250('"250180460","ADAMOWICE","95414"')
    with respx.mock(assert_all_called=False) as router:
        routes = mock_sources(router, meteo_csv=meteo_with_history)
        routes["meteo_api"].mock(side_effect=httpx.ConnectError("brak sieci"))
        with pytest.raises(IMGWConnectionError):
            build_catalog(store)
        # Both station lists were committed as archive versions before the API failure.
        for archive in (HYDRO_LIST, METEO_LIST):
            stored = list(
                (store.root / "archives/versions").glob(
                    f"{archive.server_path.rsplit('.', 1)[0]}/*/*.csv"
                )
            )
            assert len(stored) == 1
        assert not (store.root / "stations").exists()

        routes["meteo_api"].mock(
            return_value=httpx.Response(200, json=RECORDINGS["meteo_current"]["json"])
        )
        report = build_catalog(store)
        assert (
            routes["hydro_get"].call_count == 1
        )  # stored lists are reused, not downloaded again
        assert not routes["hydro_back"].called

    found = features(report)
    assert list(found) == sorted(found)
    assert set(found) == {
        "123750000",
        "123760000",
        "149190310",
        "149190311",
        "149190312",
        "149190313",
        "250180460",
    }
    assert report.station_count == 7
    historical = found["250180460"]
    assert historical["geometry"] is None
    assert historical["properties"]["active"] is False
    assert historical["properties"]["kind"] == "meteo"
    assert historical["properties"]["name"] == "ADAMOWICE"
    api_only = found["149190313"]["properties"]
    assert api_only["name"] == "Poza krajem" and api_only["active"] is True
    assert report.without_location == sum(f["geometry"] is None for f in found.values())


def test_location_precedence_rejections_and_reasons(store, tmp_path, isolated_data_dir):
    hydro_csv = HYDRO_CSV + cp1250(
        '"150000020","STACJA API","Rzeka (1)","00010"',
        '"150000021","STACJA STATYCZNA","Rzeka (1)","00015"',
    )
    hydro_api = [
        *RECORDINGS["hydro_current"]["json"],
        {
            "id_stacji": "150000020",
            "stacja": "STACJA API",
            "rzeka": "Rzeka",
            "lon": "18.3275",
            "lat": "49.9213",
        },
    ]
    static = isolated_data_dir / "hydro_stations_locations.csv"
    static.write_text(
        "id,X,Y\n150000020,18.4000,50.0000\n150000021,18.32665589,49.95453369\n",
        encoding="utf-8",
    )
    user = tmp_path / "moje.csv"
    user.write_text(
        "station_code,lon,lat,source\n"
        "149190311,19.9512,50.0512,GPS\n"  # API point is 0,0 -> user fills the gap
        "150000021,18.5000,50.1000,ręczny\n"  # static location wins over user
        "150000020,18.5000,50.1000,ręczny\n",  # API wins over static and user
        encoding="utf-8",
    )
    notices = []
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router, hydro_csv=hydro_csv, hydro_api=hydro_api)
        report = build_catalog(store, user_locations=user, on_notice=notices.append)
    found = features(report)

    def props(code):
        return found[code]["properties"]

    assert props("150000020")["location_source"] == "api_hydro"
    assert found["150000020"]["geometry"]["coordinates"] == [18.3275, 49.9213]
    assert props("150000021")["location_source"] == "static"
    assert found["150000021"]["geometry"]["coordinates"] == [18.32665589, 49.95453369]
    assert props("149190311")["location_source"] == "user"
    assert props("149190311")["location_missing_reason"] is None
    assert found["149190311"]["geometry"]["coordinates"] == [19.9512, 50.0512]
    assert found["149190313"]["geometry"] is None
    assert props("149190313")["location_missing_reason"] == "outside_country"
    assert found["149190312"]["geometry"] is None
    assert props("149190312")["location_missing_reason"] == "none"
    assert any("149190311" in p and "zero" in p for p in report.problems)
    assert any("149190313" in p and "outside_country" in p for p in report.problems)
    codes = {notice.code for notice in notices}
    assert {
        "location_rejected",
        "location_source",
        "station_without_location",
        "license_terms",
    } <= codes
    assert any("GPS" in n.text and n.code == "location_source" for n in notices)
    sources = json.loads(
        report.version.with_name("stations.geojson.meta.json").read_text()
    )["extra"]["catalog"]
    assert {s["source"] for s in sources} >= {"user", "static"}
    assert (
        next(s for s in sources if s["source"] == "user")["sha256"]
        == hashlib.sha256(user.read_bytes()).hexdigest()
    )
    static_source = next(s for s in sources if s["source"] == "static")
    assert static_source["available"] is True and static_source["count"] == 2
    assert static_source["sha256"] == hashlib.sha256(static.read_bytes()).hexdigest()


def test_missing_static_file_is_reported_and_recorded(store, isolated_data_dir):
    notices = []
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router)
        report = build_catalog(store, on_notice=notices.append)
    assert report.status == "created"
    expected = (isolated_data_dir / "hydro_stations_locations.csv").as_posix()
    assert any(
        expected in problem and "static" in problem for problem in report.problems
    )
    assert any(
        n.code == "catalog_problem" and "reference_data" in n.text for n in notices
    )
    sources = json.loads(
        report.version.with_name("stations.geojson.meta.json").read_text()
    )["extra"]["catalog"]
    static_source = next(s for s in sources if s["source"] == "static")
    assert static_source["available"] is False
    assert static_source["sha256"] is None and static_source["count"] == 0
    assert all(
        f["properties"]["location_source"] != "static"
        for f in features(report).values()
    )


BORDER_POINTS = {
    # code: (lon, lat, accepted as located in Poland)
    "150000001": (
        14.5617,
        52.3492,
        True,
    ),  # Słubice: outside the generalised outline, within tolerance
    "150000002": (
        21.50508,
        54.390779,
        True,
    ),  # 1200 m beyond the straight border with Kaliningrad Oblast
    "150000003": (18.6320, 49.7500, True),  # Cieszyn
    "150000004": (
        21.505574,
        54.396162,
        False,
    ),  # 1800 m beyond the same border: past the 1500 m tolerance
    "150000005": (
        20.5000,
        54.7000,
        False,
    ),  # Kaliningrad: inside the old lat/lon rectangle
    "150000006": (24.0300, 49.8400, False),  # Lviv: inside the old lat/lon rectangle
    "150000007": (52.3492, 14.5617, False),  # Słubice with lon/lat swapped
}


def test_border_points_are_checked_against_polygon(store, tmp_path):
    hydro_csv = cp1250(
        *(f'"{code}","PUNKT {code}","Rzeka (1)","1"' for code in BORDER_POINTS)
    )
    user = tmp_path / "granica.csv"
    user.write_text(
        "station_code,lon,lat,source\n"
        + "".join(
            f"{code},{lon:.4f},{lat:.4f},test\n"
            for code, (lon, lat, _) in BORDER_POINTS.items()
        ),
        encoding="utf-8",
    )
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router, hydro_csv=hydro_csv, hydro_api=[])
        report = build_catalog(store, user_locations=user)
    found = features(report)
    for code, (_, _, inside) in BORDER_POINTS.items():
        assert (found[code]["geometry"] is not None) is inside, code
        expected = None if inside else "outside_country"
        assert found[code]["properties"]["location_missing_reason"] == expected, code


def test_border_check_needs_no_gis_packages():
    script = (
        "import sys\n"
        "for name in ('pyproj', 'shapefile', 'osgeo', 'shapely', 'pandas'): sys.modules[name] = None\n"
        "from imgwtools.store.catalog import _evaluate\n"
        "assert _evaluate('14.5617', '52.3492')[0] == (14.5617, 52.3492)\n"
        "assert _evaluate('21.505574', '54.396162') == 'outside_country'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert result.returncode == 0, result.stderr


def test_uncertainty_follows_published_decimals(store, tmp_path):
    hydro_csv = HYDRO_CSV + cp1250('"150000010","DWA MIEJSCA","Raba (213)","1"')
    user = tmp_path / "u.csv"
    user.write_text(
        "station_code,lon,lat,source\n149190312,19.9512,50.0512,a\n150000010,19.95,50.05,b\n",
        encoding="utf-8",
    )
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router, hydro_csv=hydro_csv)
        found = features(build_catalog(store, user_locations=user))
    assert found["149190312"]["properties"]["location_uncertainty_m"] == 150.0
    assert found["150000010"]["properties"]["location_uncertainty_m"] == pytest.approx(
        556.6, abs=0.1
    )
    assert found["123750000"]["properties"]["location_uncertainty_m"] == pytest.approx(
        556.6, abs=0.1
    )  # API 52.23
    assert found["149190312"]["geometry"]["coordinates"] == [19.9512, 50.0512]


def test_hydrographic_code_text_prefix_and_river_order(store):
    hydro_csv = HYDRO_CSV + cp1250(
        '" 150150190","PODGÓRZYN","Podgórna (16288)","01284"',
        '" 150150200","SOSNÓWKA","Sośniak (16288832)","01286"',
    )
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router, hydro_csv=hydro_csv)
        found = features(build_catalog(store))
    raba = found["149190310"]["properties"]
    assert raba["hydrographic_code"] == "213"
    assert raba["river_order"] == 12
    assert raba["river"] == "Raba"  # from the public API field "rzeka"
    tributary = found["150150200"]["properties"]
    assert (
        tributary["hydrographic_code"] == "16288832"
        and tributary["river_order"] == 1286
    )
    assert tributary["river"] == "Sośniak"  # historical station: river from the list
    assert sorted(
        code
        for code, f in found.items()
        if (f["properties"]["hydrographic_code"] or "").startswith("16288")
    ) == [
        "150150190",
        "150150200",
    ]


def test_geojson_is_rfc7946_and_sidecar_records_sources(store, isolated_data_dir):
    static = isolated_data_dir / "hydro_stations_locations.csv"
    static.write_text("id,X,Y\n149190312,19.9512,50.0512\n", encoding="utf-8")
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router)
        report = build_catalog(store)
    raw = report.version.read_bytes()
    document = json.loads(raw)
    assert report.version.relative_to(store.root).as_posix() == (
        f"stations/versions/{datetime.now(UTC).date().isoformat()}_{hashlib.sha256(raw).hexdigest()[:8]}/stations.geojson"
    )
    assert document["type"] == "FeatureCollection"
    assert set(document) == {"type", "features"}  # no crs member, no catalog date
    for feature in document["features"]:
        assert (
            feature["type"] == "Feature"
            and feature["id"] == feature["properties"]["station_code"]
        )
        assert set(feature["properties"]) == PROPERTIES
        geometry = feature["geometry"]
        assert geometry is None or (
            geometry["type"] == "Point" and len(geometry["coordinates"]) == 2
        )
    warsaw = next(f for f in document["features"] if f["id"] == "123750000")
    assert warsaw["geometry"]["coordinates"] == [21.01, 52.23]  # [lon, lat]
    assert (
        warsaw["properties"]["kind"] == "meteo"
        and warsaw["properties"]["location_source"] == "api_meteo"
    )
    meta = json.loads(
        report.version.with_name("stations.geojson.meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        meta["schema"] == "imgw-meta/1"
        and meta["sha256"] == hashlib.sha256(raw).hexdigest()
    )
    assert meta["size_bytes"] == len(raw)
    assert meta["license"]["id"] == "IMGW-PIB"
    assert meta["extra"]["version"]["label_source"] == "downloaded"
    by_source = {entry["source"]: entry for entry in meta["extra"]["catalog"]}
    assert set(by_source) == {
        "hydro_stations",
        "meteo_stations",
        "api_hydro",
        "api_meteo",
        "static",
    }
    assert (
        by_source["hydro_stations"]["sha256"] == hashlib.sha256(HYDRO_CSV).hexdigest()
    )
    assert by_source["hydro_stations"]["url"] == HYDRO_LIST.url
    assert by_source["hydro_stations"]["file"].startswith(
        "archives/versions/dane_hydrologiczne/lista_stacji_hydro/"
    )
    assert by_source["api_hydro"]["count"] == 4 and by_source["api_hydro"][
        "fetched_at"
    ].endswith("Z")
    assert all(len(entry["sha256"]) == 64 for entry in by_source.values())
    assert by_source["static"] == {
        "source": "static",
        "url": None,
        "file": "hydro_stations_locations.csv",
        "fetched_at": None,
        "count": 1,
        "sha256": hashlib.sha256(static.read_bytes()).hexdigest(),
        "available": True,
    }


def test_identical_content_next_day_is_unchanged(store, tmp_path, monkeypatch):
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router)
        first = build_catalog(store)
        sidecar = first.version.with_name("stations.geojson.meta.json").read_bytes()

        class Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(days=1)

        monkeypatch.setattr(catalog, "datetime", Tomorrow)
        second = build_catalog(store)
        assert second.status == "unchanged" and second.version == first.version
        assert (
            first.version.with_name("stations.geojson.meta.json").read_bytes()
            == sidecar
        )
        user = tmp_path / "u.csv"
        user.write_text(
            "station_code,lon,lat,source\n149190312,19.9512,50.0512,a\n",
            encoding="utf-8",
        )
        third = build_catalog(store, user_locations=user)
    assert first.status == "created" and third.status == "created"
    assert third.version.parent.name.startswith(
        (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    )
    assert len(list((store.root / "stations/versions").iterdir())) == 2


def test_check_catalog_uses_head_only_and_writes_nothing(store, tmp_path):
    with respx.mock(assert_all_called=False) as router:
        routes = mock_sources(router)
        plan = check_catalog(store)
        assert [item.status for item in plan.items] == ["missing", "missing"]
        assert plan.actions[-1].status == "missing"
        assert (
            not (store.root / ".incoming").exists()
            and not (store.root / "archives").exists()
        )
        build_catalog(store)
        get_calls = {name: route.call_count for name, route in routes.items()}
        before = tree(store.root)

        plan = check_catalog(store)
        assert [item.status for item in plan.items] == ["current", "current"]
        api_actions = [a for a in plan.actions if "api/data" in a.detail]
        assert [a.status for a in api_actions] == ["unverifiable", "unverifiable"]
        assert plan.actions[-1].status == "unverifiable"

        routes["hydro_head"].mock(
            return_value=httpx.Response(200, headers={"ETag": '"list-v2"'})
        )
        routes["meteo_head"].mock(return_value=httpx.Response(200))
        user = tmp_path / "u.csv"
        user.write_text(
            "station_code,lon,lat,source\n149190312,19.9512,50.0512,a\n",
            encoding="utf-8",
        )
        plan = check_catalog(store, user_locations=user)
        assert [item.status for item in plan.items] == ["newer", "unverifiable"]
        assert any(a.status == "newer" and "user" in a.detail for a in plan.actions)
        assert plan.actions[-1].status == "newer"

        routes["hydro_head"].mock(side_effect=httpx.ConnectError("brak sieci"))
        assert check_catalog(store).items[0].status == "check_failed"
        for name, route in routes.items():
            if not name.endswith("_head"):
                assert route.call_count == get_calls[name], name  # no GET during check
        assert not routes["hydro_back"].called
    assert tree(store.root) == before


def test_check_catalog_tracks_static_file_presence(store, isolated_data_dir):
    static = isolated_data_dir / "hydro_stations_locations.csv"

    def static_action():
        (action,) = [
            a for a in check_catalog(store).actions if "plik położeń static" in a.detail
        ]
        return action

    with respx.mock(assert_all_called=False) as router:
        mock_sources(router)
        build_catalog(store)
        absent = static_action()
        assert absent.status == "current" and "brak pliku" in absent.detail
        static.write_text("id,X,Y\n149190312,19.9512,50.0512\n", encoding="utf-8")
        assert static_action().status == "newer"
        assert build_catalog(store).status == "created"
        assert static_action().status == "current"
        static.unlink()
        assert static_action().status == "newer"


def test_code_in_both_families_is_a_data_error(store):
    meteo_api = [
        *RECORDINGS["meteo_current"]["json"],
        {"kod_stacji": "149190310", "nazwa_stacji": "X", "lat": None, "lon": None},
    ]
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router, meteo_api=meteo_api)
        with pytest.raises(IMGWDataError, match="149190310"):
            build_catalog(store)
    assert not (store.root / "stations").exists()


def test_cancel_leaves_no_catalog_version(store):
    calls = iter([False, False, False, False, True])
    with respx.mock(assert_all_called=False) as router:
        mock_sources(router)
        report = build_catalog(store, cancel=lambda: next(calls, True))
    assert report.status == "cancelled" and report.version is None
    assert not (store.root / "stations").exists()
    assert not any((store.root / ".incoming").iterdir())
