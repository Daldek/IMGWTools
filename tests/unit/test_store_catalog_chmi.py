"""Offline scenarios of the ČHMÚ station catalog (spec 2026-10-18 §7; recorded HTTP only)."""

import hashlib
import json
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools._version import __version__
from imgwtools.datasets import archive_files, get_dataset
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store import init_store, read_meta, write_archive
from imgwtools.store.catalog import (
    CZECHIA_BORDER_RESOURCE,
    _evaluate,
    build_catalog,
    check_catalog,
)
from tests.contract.support import schema_errors
from tests.unit.test_store_catalog import mock_sources

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVES = FIXTURES / "archives"
RECORDING = json.loads(
    (FIXTURES / "chmi_catalog_recordings.json").read_text(encoding="utf-8")
)
CASES = {entry["case"]: entry for entry in RECORDING["interactions"]}
BASE_URL = RECORDING["base_url"]
SOURCES = (
    "hydro_now_get",
    "hydro_meta3_get",
    "hydro_stations_head",
    "hydro_stations_get",
    "meteo_now_listing",
    "meteo_now_get",
    "meteo_stations_head",
    "meteo_stations_get",
)
# The same sources after a regeneration of the envelopes (scenario 7 of §13.2).
REGENERATED = (
    "hydro_now_regenerated_get",
    "hydro_stations_regenerated_head",
    "hydro_stations_regenerated_get",
    *SOURCES[1:2],
    *SOURCES[4:],
)
LIST_SLOT = "archives/versions/hydrology/historical/metadata/meta1"
CODES = [
    "0-20000-0-99903",
    "0-203-0-90000000002",
    "0-203-0-90001",
    "0-203-1-900001",
    "0-203-1-900002",
    "0-203-1-900004",
    "0-203-1-CB900003",
]
CHMI_ATTRIBUTION = (
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, "
    "licencja CC BY 4.0. Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)"
)


def body(case):
    """Recorded response body of a case (a fixture file; empty without one)."""
    entry = CASES[case]
    for key, base in (
        ("archive", ARCHIVES),
        ("variant", FIXTURES),
        ("listing", FIXTURES),
    ):
        if key in entry:
            return (base / entry[key]).read_bytes()
    return b""


def serve(router, *cases, **bodies):
    """Answer the recorded cases; ``<case>=bytes`` replaces the body of a GET."""
    routes = {}
    for case in cases:
        entry = CASES[case]
        headers = dict(entry.get("headers", {}))
        content = b""
        if entry["method"] == "GET":
            content = bodies.get(case, body(case))
            if case in bodies:
                headers["Content-Length"] = str(len(content))
        routes[case] = router.route(
            method=entry["method"], url=BASE_URL + entry["path"]
        ).mock(
            return_value=httpx.Response(
                entry["status"], headers=headers, content=content
            )
        )
    return routes


def build(store, *cases, user=None, on_notice=None, cancel=None, **bodies):
    """ČHMÚ catalog of ``store`` built against the recorded sources (default: all)."""
    with respx.mock(assert_all_called=False) as router:
        serve(router, *(cases or SOURCES), **bodies)
        return build_catalog(
            store,
            provider="CHMI",
            user_locations=user,
            on_notice=on_notice,
            cancel=cancel,
        )


def features(report):
    document = json.loads(report.version.read_text(encoding="utf-8"))
    return {feature["id"]: feature for feature in document["features"]}


def sidecar(report):
    return json.loads(
        report.version.with_name("stations.geojson.meta.json").read_text(
            encoding="utf-8"
        )
    )


def plant_series(root, dataset, codes):
    """A minimal current series version of ``dataset`` whose index names ``codes``."""
    data = (
        json.dumps(
            {
                "schema": "imgw-series/1",
                "dataset": dataset,
                "stations": {code: {} for code in codes},
            }
        )
        + "\n"
    ).encode()
    sha = hashlib.sha256(data).hexdigest()
    version = (
        root / "series/versions" / get_dataset(dataset).slug / f"2026-10-19_{sha[:8]}"
    )
    version.mkdir(parents=True)
    (version / "series.json").write_bytes(data)
    meta = {
        "schema": "imgw-meta/1",
        "dataset": dataset,
        "downloaded_at": "2026-10-19T12:00:00Z",
        "sha256": sha,
        "size_bytes": len(data),
        "extra": {
            "version": {"label": "2026-10-19", "label_source": "inputs"},
            "series_schema": "imgw-series/1",
            "source_files": [],
        },
    }
    (version / "series.json.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return version


def tree(root):
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


def test_every_station_of_the_sources_is_kept_also_without_location(store):
    report = build(store)
    found = features(report)
    document = json.loads(report.version.read_bytes())

    assert list(found) == CODES
    assert (report.status, report.provider, report.station_count) == (
        "new",
        "CHMI",
        7,
    )
    assert (report.without_location, report.from_series) == (1, 0)
    assert (
        report.version.parent.parent == store.root / "stations/versions/chmi_stations"
    )
    assert not list((store.root / "stations/versions").glob("*/stations.geojson"))
    assert schema_errors(document, "stations.geojson") == []
    kinds = {code: feature["properties"]["kind"] for code, feature in found.items()}
    assert kinds == {code: "meteo" if "-0-" in code else "hydro" for code in CODES}
    for feature in found.values():
        properties = feature["properties"]
        assert (
            properties["meteo_kind"],
            properties["river_order"],
            properties["gauge_zero_m"],
            properties["river_km"],
        ) == (None, None, None, None)
        assert ("thresholds" in properties) is (properties["kind"] == "hydro")
    # Source 1 decides activity: the closed 900002 is only in historical meta1.
    assert {code for code, f in found.items() if not f["properties"]["active"]} == {
        "0-203-1-900002"
    }


def test_location_name_river_and_thresholds_follow_source_precedence(store):
    report = build(store)
    found = features(report)
    raw = report.version.read_bytes()

    spindleruv = found["0-203-1-900001"]
    assert spindleruv["geometry"] == {
        "type": "Point",
        "coordinates": [15.6012345, 50.4032345],  # now, not historical 50.4012345
    }
    properties = spindleruv["properties"]
    assert (properties["name"], properties["river"]) == ("Špindlerův Mlýn", "Labe")
    assert properties["location_source"] == "chmi_hydro_now"
    assert properties["thresholds"] == {
        "source": "chmi_hydro_now",
        "type": "H",
        "H": {
            "unit": "cm",
            "drought": 45,
            "spa1": 120,
            "spa2": 150,
            "spa3": 180,
            "q50": 230,
        },
        "Q": {
            "unit": "m3/s",
            "drought": 0.215,
            "spa1": 14.2,
            "spa2": 25.6,
            "spa3": 38.9,
            "q50": 96,
        },
    }
    assert b'"drought":45,' in raw and b'"drought":0.215,' in raw  # as published
    alphanumeric = found["0-203-1-CB900003"]["properties"]
    assert alphanumeric["name"] == "Smyšlená Ves"  # now before meta3 "… - jez"
    assert alphanumeric["hydrographic_code"] == "1-08-01-0010"  # only meta3 has it
    assert (
        alphanumeric["thresholds"]["source"],
        alphanumeric["thresholds"]["type"],
    ) == (
        "chmi_hydro_now",
        "Q",
    )
    closed = found["0-203-1-900002"]
    assert closed["geometry"]["coordinates"] == [17.2512345, 49.8512345]
    assert closed["properties"]["location_source"] == "chmi_hydro_stations"
    assert closed["properties"]["thresholds"] == {
        "source": "chmi_hydro_stations",
        "type": "Q",
        "H": dict.fromkeys(("drought", "spa1", "spa2", "spa3", "q50")) | {"unit": "cm"},
        "Q": {
            "unit": "m3/s",
            "drought": 0.12,
            "spa1": 8.4,
            "spa2": 15.1,
            "spa3": 22.8,
            "q50": 57.3,
        },
    }


def test_rejected_points_never_block_a_lower_source_and_reasons_are_kept(store):
    plant_series(store.root, "cz.chmi.hydro_daily", ["0-203-1-900005"])
    notices = []
    report = build(store, on_notice=notices.append)
    found = features(report)

    lower = found["0-203-1-900004"]
    assert lower["geometry"]["coordinates"] == [16.6012345, 49.2012345]
    assert lower["properties"]["location_source"] == "chmi_hydro_stations"
    assert lower["properties"]["location_missing_reason"] is None
    foreign = found["0-20000-0-99903"]["properties"]
    assert foreign["location_missing_reason"] == "outside_country"
    assert (foreign["location_source"], foreign["elevation_m"]) == (None, None)
    series_only = found["0-203-1-900005"]
    assert series_only["geometry"] is None
    assert series_only["properties"]["location_missing_reason"] == "none"
    assert (series_only["properties"]["active"], series_only["properties"]["kind"]) == (
        False,
        "hydro",
    )
    assert (report.from_series, report.without_location) == (1, 2)
    assert report.problems == (
        "0-20000-0-99903: the source point chmi_meteo_now (-21.9405, 64.1311) was rejected — outside_country",
        "0-20000-0-99903: the source point chmi_meteo_stations (-21.9405, 64.1311) was rejected — outside_country",
        "0-203-1-900004: the source point chmi_hydro_now (0, 0) was rejected — zero",
    )
    assert [n.text for n in notices if n.code == "location_rejected"] == list(
        report.problems
    )
    (series_notice,) = [n for n in notices if n.code == "series_station"]
    assert "0-203-1-900005" in series_notice.text

    zero = build(
        init_store(store.root.parent / "zero"),
        hydro_stations_get=body("hydro_stations_get").replace(
            b"49.2012345,16.6012345", b"0,0"
        ),
    )
    assert features(zero)["0-203-1-900004"]["geometry"] is None
    assert (
        features(zero)["0-203-1-900004"]["properties"]["location_missing_reason"]
        == "zero"
    )


def test_uncertainty_follows_the_published_decimals(store):
    found = features(build(store))
    seven = found["0-203-1-900001"]["properties"]["location_uncertainty_m"]
    two = found["0-203-0-90000000002"]["properties"]  # now meta1: 15.27, 49.85
    assert seven == 150.0
    assert two["location_uncertainty_m"] == pytest.approx(556.6, abs=0.1)
    assert found["0-203-0-90000000002"]["geometry"]["coordinates"] == [15.27, 49.85]


def test_location_conflict_names_stations_whose_valid_points_disagree(store):
    notices = []
    report = build(store, on_notice=notices.append)
    (conflict,) = [n for n in notices if n.code == "location_conflict"]
    assert conflict.level == "info"
    # now and historical meta1 of 900001 differ by 0.002° of latitude (~223 m > 150 m).
    assert conflict.text.startswith("1 stations with valid source locations ")
    assert conflict.text.endswith(": 0-203-1-900001")
    assert not any("0-203-1-900001" in problem for problem in report.problems)
    assert features(report)["0-203-1-900001"]["properties"]["location_source"] == (
        "chmi_hydro_now"
    )


def test_hydrographic_code_is_text_and_full_segment_prefix_selects(store):
    found = features(build(store))
    codes = {
        code: feature["properties"]["hydrographic_code"]
        for code, feature in found.items()
    }
    assert codes["0-203-1-900001"] == "1-05-03-0110"
    assert codes["0-203-1-900002"] == "2-01-02-0030"
    assert codes["0-203-1-900004"] is None  # "" in historical meta1
    prefix = "1-05"
    assert [
        code
        for code, value in codes.items()
        if value is not None and (value == prefix or value.startswith(prefix + "-"))
    ] == ["0-203-1-900001"]


def test_meteo_fields_come_from_now_and_the_latest_historical_period(store):
    found = features(build(store))
    current = found["0-203-0-90001"]["properties"]
    assert (current["established_year"], current["elevation_m"]) == (1961, 318.5)
    assert found["0-20000-0-99903"]["properties"]["established_year"] == 1950

    document = json.loads(body("meteo_now_get"))
    rows = document["data"]["data"]["values"]
    document["data"]["data"]["values"] = [
        row for row in rows if row[0] != "0-203-0-90001"
    ]
    historical = features(
        build(
            init_store(store.root.parent / "historical"),
            meteo_now_get=json.dumps(document, ensure_ascii=False).encode(),
        )
    )["0-203-0-90001"]
    assert historical["geometry"]["coordinates"] == [14.8213, 50.2147]
    properties = historical["properties"]
    assert (
        properties["location_source"],
        properties["name"],
        properties["active"],
        properties["elevation_m"],
    ) == ("chmi_meteo_stations", "Fiktivní Ves-Horní", False, 318.5)


def test_new_envelopes_keep_the_catalog_and_only_observe_the_list(store):
    first = build(store)
    notices = []
    with respx.mock(assert_all_called=False) as router:
        routes = serve(router, *REGENERATED)
        second = build_catalog(store, provider="CHMI", on_notice=notices.append)
    assert (second.status, second.version) == ("unchanged", first.version)
    assert routes["hydro_stations_regenerated_get"].call_count == 1
    slot = store.root / LIST_SLOT
    assert len([path for path in slot.iterdir() if path.name != "observations"]) == 1
    (observation,) = (slot / "observations").iterdir()
    (unchanged,) = [n for n in notices if n.code == "content_unchanged"]
    assert "archive:cz.chmi.hydro_stations:meta1.json" in unchanged.text
    assert not [n for n in notices if n.code == "license_terms"]

    with respx.mock(assert_all_called=False) as router:
        routes = serve(router, *REGENERATED)
        plan = check_catalog(store, provider="CHMI")
        third = build_catalog(store, provider="CHMI")
        assert routes["hydro_stations_regenerated_get"].call_count == 0
    hydro, meteo = plan.items
    assert (hydro.status, hydro.local_observation) == (
        "current",
        observation.relative_to(store.root),
    )
    assert (meteo.status, meteo.local_observation) == ("current", None)
    assert (third.status, third.version) == ("unchanged", first.version)


def test_sidecar_records_both_sums_of_every_source_and_the_chmi_license(tmp_path):
    notices = []
    first = build(init_store(tmp_path / "a"), on_notice=notices.append)
    second = build(
        init_store(tmp_path / "b"), "hydro_now_regenerated_get", *SOURCES[1:]
    )
    assert first.version.read_bytes() == second.version.read_bytes()
    meta, other = sidecar(first), sidecar(second)
    assert schema_errors(meta, "imgw-meta/1") == []
    assert (meta["dataset"], meta["country"], meta["provider"]) == (
        "cz.chmi.stations",
        "CZ",
        "CHMI",
    )
    assert meta["license"] == {
        "id": "CC-BY-4.0",
        "attribution": CHMI_ATTRIBUTION,
        "url": "https://creativecommons.org/licenses/by/4.0/",
        "terms_url": "https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti",
    }
    assert meta["extra"]["derived"] == "catalog"
    entries = {entry["source"]: entry for entry in meta["extra"]["catalog"]}
    assert list(entries) == [
        "chmi_hydro_now",
        "chmi_hydro_meta3",
        "chmi_hydro_stations",
        "chmi_meteo_now",
        "chmi_meteo_stations",
    ]
    assert {source: entry["count"] for source, entry in entries.items()} == {
        "chmi_hydro_now": 3,
        "chmi_hydro_meta3": 2,
        "chmi_hydro_stations": 3,
        "chmi_meteo_now": 3,
        "chmi_meteo_stations": 3,
    }
    assert all(entry["content_form"] == "chmi-json/1" for entry in entries.values())
    assert entries["chmi_meteo_now"]["url"] == (
        f"{BASE_URL}meteorology/climate/now/metadata/meta1-20261018.json"
    )
    for source in ("chmi_hydro_stations", "chmi_meteo_stations"):
        version = tmp_path / "a" / entries[source]["file"]
        stored = read_meta(version)
        assert (entries[source]["sha256"], entries[source]["content_sha256"]) == (
            stored.sha256,
            stored.content_sha256,
        )
    now, regenerated = entries["chmi_hydro_now"], other["extra"]["catalog"][0]
    assert regenerated["source"] == "chmi_hydro_now"
    assert now["sha256"] != regenerated["sha256"]
    assert now["content_sha256"] == regenerated["content_sha256"]
    catalog = read_meta(first.version)
    assert (catalog.dataset_key, catalog.provider, catalog.country) == (
        "cz.chmi.stations",
        "CHMI",
        "CZ",
    )
    assert notices[-1].code == "license_terms"
    assert notices[-1].text == (
        f"{CHMI_ATTRIBUTION}. The CC BY 4.0 licence permits copying, changes and "
        "commercial use provided that the author ČHMÚ is credited, the licence is given "
        "and the changes are marked."
    )


def test_user_file_locates_chmi_codes_and_skips_codes_of_the_other_provider(
    store, tmp_path
):
    plant_series(store.root, "cz.chmi.hydro_daily", ["0-203-1-900005"])
    user = tmp_path / "polozenia.csv"
    user.write_text(
        "station_code,latitude,longitude,source\n"
        "0-203-1-900005,49.5,15.5,GPS\n"
        "149190310,49.7,20.1,GPS\n"
        "0-203-1-999999,49.6,15.6,GPS\n"
        "zly-kod,49.6,15.6,GPS\n",
        encoding="utf-8",
    )
    notices = []
    report = build(store, user=user, on_notice=notices.append)
    located = features(report)["0-203-1-900005"]
    assert located["geometry"]["coordinates"] == [15.5, 49.5]
    assert located["properties"]["location_source"] == "user"
    assert report.problems[:2] == (
        "Row 5: invalid station code 'zly-kod' in the location file",
        "User location file: 1 codes outside the ČHMÚ metadata and series "
        "(e.g. 0-203-1-999999); the user file only completes locations",
    )
    assert not any("149190310" in problem for problem in report.problems)
    (entry,) = [e for e in sidecar(report)["extra"]["catalog"] if e["source"] == "user"]
    assert entry == {
        "source": "user",
        "url": None,
        "file": "polozenia.csv",
        "fetched_at": None,
        "count": 2,
        "sha256": hashlib.sha256(user.read_bytes()).hexdigest(),
        "available": True,
    }
    assert "Sources in the user file: GPS" in [
        n.text for n in notices if n.code == "location_source"
    ]


def test_imgw_catalog_is_byte_identical_with_chmi_data_in_the_store(tmp_path):
    user = tmp_path / "polozenia.csv"
    user.write_text(
        "station_code,latitude,longitude\n"
        "149190312,50.0512,19.9512\n"
        "0-203-1-900002,49.85,17.25\n"
        "zly-kod,1,1\n",
        encoding="utf-8",
    )
    outcomes = []
    for name in ("plain", "mixed"):
        store = init_store(tmp_path / name)
        if name == "mixed":
            build(store)
            plant_series(store.root, "cz.chmi.hydro_daily", ["0-203-1-900005"])
            (archive,) = archive_files(
                "cz.chmi.hydro_daily", stations=["0-203-1-900001"], years=[2023]
            )
            data = (ARCHIVES / archive.server_path).read_bytes()
            write_archive(
                store,
                archive=archive,
                response=DownloadResult(
                    data,
                    archive.url,
                    '"v1"',
                    "Tue, 01 Jul 2025 12:07:21 GMT",
                    len(data),
                ),
            )
        with respx.mock(assert_all_called=False) as router:
            mock_sources(router)
            report = build_catalog(store, user_locations=user)
            plan = check_catalog(store, user_locations=user)
        meta = sidecar(report)
        outcomes.append(
            (
                report.version.relative_to(store.root),
                report.version.read_bytes(),
                [
                    {key: value for key, value in entry.items() if key != "fetched_at"}
                    for entry in meta["extra"]["catalog"]
                ],
                (meta["dataset"], meta["country"], meta["provider"], meta["license"]),
                report.problems,
                [item.status for item in plan.items],
                plan.actions,
            )
        )
    assert outcomes[0] == outcomes[1]
    problems = outcomes[0][4]
    assert "Row 4: invalid station code 'zly-kod' in the location file" in problems
    assert not any("0-203-1" in problem for problem in problems)


def test_check_catalog_uses_head_only_and_writes_nothing(store):
    notices = []
    with respx.mock(assert_all_called=False) as router:
        routes = serve(router, *SOURCES)
        plan = check_catalog(store, provider="CHMI", on_notice=notices.append)
        assert [(item.archive.dataset, item.status) for item in plan.items] == [
            ("cz.chmi.hydro_stations", "missing"),
            ("cz.chmi.meteo_stations", "missing"),
        ]
        assert [action.status for action in plan.actions] == [
            "unverifiable",
            "unverifiable",
            "unverifiable",
            "missing",
            "missing",
        ]
        assert [n.code for n in notices] == ["source_unverifiable"] * 3
        assert not (store.root / "archives").exists()
        assert not any(
            route.called for case, route in routes.items() if case.endswith("_get")
        )
        assert not routes["meteo_now_listing"].called
        build_catalog(store, provider="CHMI")
        before = tree(store.root)
        calls = {case: route.call_count for case, route in routes.items()}
        plan = check_catalog(store, provider="CHMI")
        assert {case: route.call_count for case, route in routes.items()} == calls | {
            "hydro_stations_head": calls["hydro_stations_head"] + 1,
            "meteo_stations_head": calls["meteo_stations_head"] + 1,
        }
    assert tree(store.root) == before
    assert [item.status for item in plan.items] == ["current", "current"]
    assert [action.status for action in plan.actions][3:] == ["current", "unverifiable"]

    with respx.mock(assert_all_called=False) as router:
        serve(router, "hydro_stations_regenerated_head", "meteo_stations_head")
        changed = check_catalog(store, provider="CHMI")
    assert [item.status for item in changed.items] == ["newer", "current"]
    assert changed.actions[-1].status == "newer"


def test_broken_observation_of_a_list_fails_its_check_and_the_build(store):
    build(store)
    register = store.root / LIST_SLOT / "observations"
    register.mkdir()
    (register / "2026-10-19_00000000.json").write_text("{zepsuty", encoding="utf-8")
    with respx.mock(assert_all_called=False) as router:
        serve(router, *SOURCES)
        hydro, meteo = check_catalog(store, provider="CHMI").items
        with pytest.raises(IMGWDataError) as error:
            build_catalog(store, provider="CHMI")
    assert hydro.status == "check_failed" and "corrupt observation" in hydro.error
    assert meteo.status == "current"
    assert error.value.code == "data_error"


@pytest.mark.parametrize(
    ("change", "error", "reason"),
    [
        ({"hydro_now_get": None}, IMGWConnectionError, "HTTP error 503"),
        (
            {"hydro_meta3_get": b'{"zaznamID":"a","zaznamID":"b"}'},
            IMGWDataError,
            "a repeated key",
        ),
        (
            {
                "meteo_now_listing": b"\n".join(
                    line
                    for line in body("meteo_now_listing").split(b"\n")
                    if b"meta1-" not in line
                )
            },
            IMGWDataError,
            "no file meta1-<YYYYMMDD>.json",
        ),
        (
            {"hydro_now_get": body("hydro_now_get").replace(b'"CM"', b'"MM"')},
            IMGWDataError,
            "SPAH_UNIT: unknown unit 'MM'",
        ),
        (
            {
                "meteo_now_get": body("meteo_now_get").replace(
                    b'"0-203-0-90001"', b'"0-203-1-900001"'
                )
            },
            IMGWDataError,
            "both the hydro and the meteo family: 0-203-1-900001",
        ),
    ],
    ids=["http-503", "repeated-key", "listing-without-meta1", "unit", "two-families"],
)
def test_source_errors_publish_no_catalog(store, change, error, reason):
    cases = [case for case in SOURCES if change.get(case, b"") is not None]
    if "hydro_now_get" not in cases:
        cases.append("hydro_now_outage")
    bodies = {case: content for case, content in change.items() if content is not None}
    with pytest.raises(error, match=reason) as raised:
        build(store, *cases, **bodies)
    assert raised.value.code == (
        "source_unavailable" if error is IMGWConnectionError else "data_error"
    )
    assert not (store.root / "stations").exists()


def test_newest_meteo_now_file_is_read_and_cancel_publishes_nothing(store):
    with respx.mock(assert_all_called=False) as router:
        routes = serve(router, *SOURCES, "meteo_now_previous_get")
        polls = iter([False] * 5 + [True])
        report = build_catalog(store, provider="CHMI", cancel=lambda: next(polls))
        assert routes["meteo_now_get"].called
        assert not routes["meteo_now_previous_get"].called
        request = routes["meteo_now_get"].calls.last.request
        assert request.headers["User-Agent"] == f"imgwtools/{__version__}"
    assert (report.status, report.version, report.provider) == (
        "cancelled",
        None,
        "CHMI",
    )
    assert not (store.root / "stations").exists()


def test_provider_is_validated_and_key_prefix_names_it(store):
    for call in (build_catalog, check_catalog):
        with pytest.raises(IMGWValidationError) as error:
            call(store, provider="SHMU")
        assert error.value.details["allowed"] == ["IMGW-PIB", "CHMI"]
    with respx.mock(assert_all_called=False) as router:
        serve(router, *SOURCES)
        assert build_catalog(store, provider="cz.chmi").provider == "CHMI"


def test_czech_outline_validates_points_of_czechia_only():
    ring = json.loads(
        (
            Path(__file__).parents[2] / "src/imgwtools/_data" / CZECHIA_BORDER_RESOURCE
        ).read_text(encoding="utf-8")
    )["features"][0]["geometry"]["coordinates"][0]
    west_lon, west_lat = min(ring)

    def czech(lon, lat):
        return _evaluate(lon, lat, border=CZECHIA_BORDER_RESOURCE)

    assert czech("14.4378", "50.0755")[0] == (14.4378, 50.0755)  # Praha
    assert czech(str(west_lon - 0.005), str(west_lat)) != "outside_country"  # ~360 m
    assert czech(str(west_lon - 0.05), str(west_lat)) == "outside_country"  # ~3.6 km
    assert czech("-21.9", "64.1") == "outside_country"  # Reykjavik
    assert czech("17.0385", "51.1079") == "outside_country"  # Wrocław
    assert _evaluate("17.0385", "51.1079")[0] == (17.0385, 51.1079)  # Polish outline


def test_recordings_bodies_and_nginx_signals_agree():
    for case, entry in CASES.items():
        headers = entry.get("headers", {})
        if "ETag" not in headers:
            continue
        size = int(headers["Content-Length"])
        moment = int(parsedate_to_datetime(headers["Last-Modified"]).timestamp())
        assert headers["ETag"] == f'"{moment:x}-{size:x}"', case
        if entry["method"] == "GET":
            data = body(case)
            assert len(data) == size, case
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], case
