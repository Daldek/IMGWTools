"""check_store and sync_store for ČHMÚ per-station files on recorded answers.

Spec 2026-10-18 §4.1-§4.3 (listing, freshness, synchronization) and the §13.2
scenarios (1)-(5) and (8), replayed from ``chmi_recordings.json`` with respx.
Synthetic files only; codes 0-203-1-9… and 0-203-0-9… are not published by
ČHMÚ.
"""

import hashlib
import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools._parsing.chmi import parse_listing
from imgwtools._version import __version__
from imgwtools.datasets import archive_files, get_provider
from imgwtools.exceptions import IMGWValidationError
from imgwtools.fetch import DownloadResult
from imgwtools.store import current_version, init_store, write_archive
from imgwtools.store import sync as sync_module
from imgwtools.store.content import content_sha256
from imgwtools.store.sync import check_store, sync_store
from imgwtools.store.types import PlanAction, SeriesReport, StorePlan
from imgwtools.urls import IMGW_PUBLIC_DATA_URL
from tests.contract.support import schema_errors

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDING = json.loads((FIXTURES / "chmi_recordings.json").read_text(encoding="utf-8"))
BASE = RECORDING["base_url"]
CASES = {entry["case"]: entry for entry in RECORDING["interactions"]}
HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
S1, S2 = "0-203-1-900001", "0-203-1-900002"
NO_FILES = "0-203-1-CB900003"  # in the station metadata only
FULL, RAIN = "0-203-0-90001", "0-203-0-90000000002"  # four elements / SRA only
H1_2023, H1_2024 = archive_files(HYDRO, stations=[S1], years=[2023, 2024])
H2_2004, H2_2005, H2_2006 = archive_files(HYDRO, stations=[S2], years="2004-2006")
DAILY = "hydrology/historical/data/daily"
FIRST = [
    f"{name}_{method}"
    for name in ("h900001_2023", "h900001_2024")
    for method in ("head", "get")
]


def payload(entry):
    if "listing" in entry:
        return (FIXTURES / entry["listing"]).read_bytes()
    if "archive" in entry:
        return (FIXTURES / "archives" / entry["archive"]).read_bytes()
    if "variant" in entry:
        return (FIXTURES / entry["variant"]).read_bytes()
    return entry.get("body", "").encode("utf-8")


def serve(router, *cases):
    """Answer each recorded case; a later case for the same request replaces it."""
    routes = []
    for case in cases:
        entry = CASES[case]
        route = router.route(method=entry["method"], url=BASE + entry["path"])
        if "exception" in entry:
            route.mock(side_effect=httpx.ConnectError("synthetyczny błąd sieci"))
        elif entry["method"] == "HEAD":
            route.mock(
                return_value=httpx.Response(entry["status"], headers=entry["headers"])
            )
        else:
            route.mock(
                return_value=httpx.Response(
                    entry["status"],
                    headers=entry.get("headers"),
                    content=payload(entry),
                )
            )
        routes.append(route)
    return routes


def store(root, archive, case, **headers):
    """Write the recorded GET bytes of ``case``, optionally under other headers."""
    entry = CASES[case]
    signal = {**entry["headers"], **headers}
    data = payload(entry)
    response = DownloadResult(
        data, archive.url, signal["ETag"], signal["Last-Modified"], len(data)
    )
    return write_archive(root, archive=archive, response=response)


def traffic(router, start=0):
    return [
        (call.request.method, str(call.request.url).removeprefix(BASE))
        for call in router.calls[start:]
    ]


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
    }


def slot_dir(root, archive):
    return (
        root
        / "archives"
        / "versions"
        / archive.server_path.removesuffix(Path(archive.server_path).suffix)
    )


def versions(root, archive):
    directory = slot_dir(root, archive)
    return sorted(
        path.name for path in directory.iterdir() if path.name != "observations"
    )


def register(root, archive):
    directory = slot_dir(root, archive) / "observations"
    return sorted(directory.iterdir()) if directory.exists() else []


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


def publish_first(root, server):
    """Scenario (1) for station 900001: both years ``missing``, then ``created``."""
    serve(server, "hydro_listing", *FIRST)
    report = sync_store(root, datasets=[HYDRO], stations=[S1], series=False)
    assert [item.status for item in report.items] == ["created", "created"]
    return report


def test_recordings_follow_the_nginx_format_of_the_source():
    """ETag = "<hex mtime>-<hex size>", HEAD = GET headers, listings match the files."""
    signals = {}
    files = [entry for entry in RECORDING["interactions"] if "sha256" in entry]
    for entry in files:
        headers, data = entry["headers"], payload(entry)
        moment = parsedate_to_datetime(headers["Last-Modified"])
        assert sha(data) == entry["sha256"]
        assert int(headers["Content-Length"]) == len(data)
        assert headers["ETag"] == f'"{int(moment.timestamp()):x}-{len(data):x}"'
        head = CASES[entry["case"].removesuffix("_get") + "_head"]
        assert (head["path"], head["headers"]) == (entry["path"], headers)
        signals.setdefault(entry["path"], set()).add(
            (moment.replace(second=0), len(data))
        )
    listings = [
        entry
        for entry in RECORDING["interactions"]
        if "listing" in entry["case"] and entry["status"] == 200
    ]
    assert len(files) == 17 and len(listings) == 10
    for entry in listings:
        assert {"ETag", "Last-Modified"}.isdisjoint(entry["headers"])
        if entry["case"].endswith(("_empty", "_foreign")):
            continue
        for row in parse_listing(payload(entry), url=BASE + entry["path"]):
            path = entry["path"] + row.name
            if path in signals:
                assert (row.modified, row.size) in signals[path], (entry["case"], path)


def test_check_reads_one_listing_and_compares_it_with_the_store(root, server):
    store(root, H1_2023, "h900001_2023_get")
    # Same bytes stored under an older signal than the listing shows.
    store(
        root,
        H2_2004,
        "h900002_2004_get",
        **{
            "ETag": f'"{int(datetime(2025, 2, 13, 9, 41, tzinfo=UTC).timestamp()):x}-33cf"',
            "Last-Modified": "Thu, 13 Feb 2025 09:41:00 GMT",
        },
    )
    before = tree(root)
    serve(server, "hydro_listing")
    archives = [
        server.route(method=method, url=archive.url)
        for archive in (H1_2023, H1_2024, H2_2004, H2_2006)
        for method in ("HEAD", "GET")
    ]
    notices, progress = [], []

    plan = check_store(
        root,
        datasets=["chmi_hydro_daily"],
        stations=[S2, NO_FILES, S1, FULL, S1],
        on_notice=notices.append,
        on_progress=progress.append,
    )

    assert traffic(server) == [("GET", f"{DAILY}/")]
    assert not any(route.called for route in archives)
    assert tree(root) == before
    assert [
        (item.station_code, item.archive.year, item.status) for item in plan.items
    ] == [
        (S1, 2023, "current"),
        (S1, 2024, "missing"),
        (S2, 2004, "newer"),
        (S2, 2006, "missing"),
    ]
    current, missing, newer, _ = plan.items
    assert {item.signal for item in plan.items} == {"listing"}
    assert (current.remote_listed_at, current.content_length) == (
        "2025-07-01T12:07Z",
        23926,
    )
    assert (current.remote_etag, current.remote_last_modified) == (None, None)
    assert current.local_path == current_version(
        root, slot=f"archive:{HYDRO}:{H1_2023.server_path.rsplit('/', 1)[1]}"
    ).version.relative_to(root)
    assert current.local_sha256 == sha(payload(CASES["h900001_2023_get"]))
    assert current.local_observation is None and current.error is None
    assert (missing.local_path, missing.content_length) == (None, 21835)
    assert (
        newer.local_path is not None and newer.remote_listed_at == "2025-07-01T12:07Z"
    )
    assert plan.actions == (
        PlanAction(
            "store sync",
            "unverifiable",
            f"stacja {FULL}: brak plików zbioru {HYDRO} u źródła",
        ),
        PlanAction(
            "store sync",
            "unverifiable",
            f"stacja {NO_FILES}: brak plików zbioru {HYDRO} u źródła",
        ),
    )
    assert [(notice.code, notice.text) for notice in notices] == [
        ("source_unverifiable", action.detail) for action in plan.actions
    ]
    assert [(event.current, event.total, event.status) for event in progress] == [
        (1, 4, "current"),
        (2, 4, "missing"),
        (3, 4, "newer"),
        (4, 4, "missing"),
    ]
    assert plan.requests == {"made": 1, "planned": 6}
    assert plan.series_state == {"chmi_hydro_daily": "missing"}
    assert not plan.cancelled


def test_requested_years_absent_from_the_listing_are_unpublished(
    root, server, monkeypatch
):
    built = []

    def fake_build(store_root, /, **kwargs):
        built.append(kwargs["dataset"])
        return SeriesReport("created", None, 2, (), ())

    monkeypatch.setattr(sync_module, "build_series", fake_build)
    serve(
        server,
        "hydro_listing",
        "h900002_2004_head",
        "h900002_2004_get",
        "h900002_2006_head",
        "h900002_2006_get",
    )
    notices = []

    plan = check_store(
        root,
        datasets=[HYDRO],
        stations=[S2, S1],
        years="2005-2006",
        on_notice=notices.append,
    )

    assert [(item.archive, item.status, item.error) for item in plan.items] == [
        (
            archive_files(HYDRO, stations=[S1], years=[2005])[0],
            "unverifiable",
            "nieopublikowany",
        ),
        (
            archive_files(HYDRO, stations=[S1], years=[2006])[0],
            "unverifiable",
            "nieopublikowany",
        ),
        (H2_2005, "unverifiable", "nieopublikowany"),
        (H2_2006, "missing", None),
    ]
    assert plan.actions == () and plan.requests == {"made": 1, "planned": 2}
    assert [notice.code for notice in notices] == ["source_unverifiable"] * 3

    report = sync_store(root, plan=plan)

    assert [
        (item.status, item.version is None, item.error) for item in report.items
    ] == [
        ("unchanged", True, "nieopublikowany"),
        ("unchanged", True, "nieopublikowany"),
        ("unchanged", True, "nieopublikowany"),
        ("created", False, None),
    ]
    assert built == [HYDRO]  # unpublished years do not block the series
    assert [entry.status for entry in report.series] == ["created"]


def test_plan_of_listing_items_round_trips_and_meets_the_contract(
    root, server, tmp_path
):
    publish_first(root, server)
    serve(server, "hydro_listing_reserialized", "h900001_2023_reserialized_head")
    serve(server, "h900001_2023_reserialized_get")
    sync_store(root, datasets=[HYDRO], stations=[S1], years=[2023], series=False)

    plan = check_store(
        root, datasets=[HYDRO], stations=[S1, NO_FILES], plan=tmp_path / "plan.json"
    )

    document = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert schema_errors(document, "imgw-plan/1") == []
    assert StorePlan.from_json(tmp_path / "plan.json") == plan
    observed, published = document["items"]
    assert {key: observed[key] for key in observed if key != "local_path"} == {
        "dataset": HYDRO,
        "server_path": H1_2023.server_path,
        "url": H1_2023.url,
        "year": 2023,
        "month": None,
        "param": None,
        "year_type": "calendar",
        "station_code": S1,
        "status": "current",
        "signal": "listing",
        "local_sha256": sha(payload(CASES["h900001_2023_get"])),
        "local_observation": register(root, H1_2023)[0].relative_to(root).as_posix(),
        "remote_etag": None,
        "remote_last_modified": None,
        "remote_listed_at": "2026-10-19T03:12Z",
        "content_length": 25595,
        "error": None,
    }
    assert (published["status"], published["local_observation"]) == ("current", None)
    assert document["requests"] == {"made": 1, "planned": 0}
    assert document["actions"] == [
        {
            "command": "store sync",
            "status": "unverifiable",
            "detail": f"stacja {NO_FILES}: brak plików zbioru {HYDRO} u źródła",
        }
    ]


def test_first_publication_heads_then_gets_and_writes_chmi_sidecars(root, server):
    serve(server, "hydro_listing", *FIRST)
    plan = check_store(root, datasets=[HYDRO], stations=[S1])
    assert [item.status for item in plan.items] == ["missing", "missing"]
    notices = []

    report = sync_store(root, plan=plan, series=False, on_notice=notices.append)

    assert traffic(server, 1) == [
        (method, H.server_path)
        for H in (H1_2023, H1_2024)
        for method in ("HEAD", "GET")
    ]
    assert {call.request.headers["User-Agent"] for call in server.calls} == {
        f"imgwtools/{__version__}"
    }
    assert [(item.slot, item.status) for item in report.items] == [
        (f"archive:{HYDRO}:H_{S1}_DQ_2023.json", "created"),
        (f"archive:{HYDRO}:H_{S1}_DQ_2024.json", "created"),
    ]
    entry = CASES["h900001_2023_get"]
    data = payload(entry)
    version = report.items[0].version
    assert version.read_bytes() == data
    meta = json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))
    assert schema_errors(meta, "imgw-meta/1") == []
    license_ = get_provider("CHMI").license
    assert {key: value for key, value in meta.items() if key != "downloaded_at"} == {
        "schema": "imgw-meta/1",
        "producer": "imgwtools",
        "producer_version": __version__,
        "dataset": HYDRO,
        "country": "CZ",
        "provider": "CHMI",
        "request": {
            "server_path": H1_2023.server_path,
            "year": 2023,
            "month": None,
            "station_code": S1,
            "param": None,
        },
        "license": {
            "id": "CC-BY-4.0",
            "attribution": license_.attribution,
            "url": license_.url,
            "terms_url": license_.terms_url,
        },
        "sha256": sha(data),
        "size_bytes": len(data),
        "content_sha256": content_sha256(data, form="chmi-json/1"),
        "content_form": "chmi-json/1",
        "extra": {
            "version": {"label": "2025-07-01", "label_source": "last_modified"},
            "period": {
                "year": 2023,
                "month": None,
                "param": None,
                "year_type": "calendar",
                "start": "2023-01-01",
                "end": "2023-12-31",
                "station_code": S1,
            },
            "http": {
                "url": H1_2023.url,
                "etag": entry["headers"]["ETag"],
                "last_modified": entry["headers"]["Last-Modified"],
                "content_length": len(data),
            },
        },
    }
    assert version.parent.name == f"2025-07-01_{sha(data)[:8]}"
    assert [notice.code for notice in notices] == ["license_terms", "license_terms"]

    start = len(server.calls)
    again = check_store(root, datasets=[HYDRO], stations=[S1])
    assert [item.status for item in again.items] == ["current", "current"]
    assert traffic(server, start) == [("GET", f"{DAILY}/")]


def test_mass_republication_of_the_same_bytes_is_relabeled(root, server):
    serve(
        server,
        "hydro_listing",
        *FIRST,
        *(
            f"h900002_{year}_{method}"
            for year in (2004, 2006)
            for method in ("head", "get")
        ),
    )
    first = sync_store(root, datasets=[HYDRO], stations=[S1, S2], series=False)
    assert [item.status for item in first.items] == ["created"] * 4
    names = ("h900001_2023", "h900001_2024", "h900002_2004", "h900002_2006")
    serve(
        server,
        "hydro_listing_republished",
        *(
            f"{name}_republished_{method}"
            for name in names
            for method in ("head", "get")
        ),
    )

    plan = check_store(root, datasets=[HYDRO], stations=[S1, S2])
    assert [item.status for item in plan.items] == ["newer"] * 4
    assert {item.remote_listed_at for item in plan.items} == {"2026-02-06T08:15Z"}
    report = sync_store(root, plan=plan, series=False)

    assert [item.status for item in report.items] == ["relabeled"] * 4
    for old, new in zip(first.items, report.items, strict=True):
        assert new.version != old.version
        assert new.version.read_bytes() == old.version.read_bytes()
        assert new.version.parent.name.startswith("2026-02-06_")
    assert [
        item.status
        for item in check_store(root, datasets=[HYDRO], stations=[S1, S2]).items
    ] == ["current"] * 4


def test_correction_creates_a_version_beside_the_untouched_one(root, server):
    first = publish_first(root, server)
    old = first.items[1].version
    old_files = {path: path.read_bytes() for path in old.parent.iterdir()}
    serve(
        server,
        "hydro_listing_corrected",
        "h900001_2024_corrected_head",
        "h900001_2024_corrected_get",
    )

    plan = check_store(root, datasets=[HYDRO], stations=[S1])
    assert [item.status for item in plan.items] == ["current", "newer"]
    report = sync_store(root, plan=plan, series=False)

    assert [item.status for item in report.items] == ["unchanged", "created"]
    corrected = report.items[1].version
    assert corrected.read_bytes() == payload(CASES["h900001_2024_corrected_get"])
    assert corrected.parent.name.startswith("2026-05-21_")
    assert {path: path.read_bytes() for path in old.parent.iterdir()} == old_files
    assert versions(root, H1_2024) == sorted([old.parent.name, corrected.parent.name])
    assert current_version(root, slot=report.items[1].slot).version == corrected


@pytest.mark.parametrize(
    ("head", "status", "code"),
    [
        ("h900001_2024_corrected_head", "stale_plan", None),
        ("h900001_2024_gone_head", "stale_plan", None),
        ("h900001_2024_resized_head", "stale_plan", None),
        ("h900001_2024_unreachable_head", "failed", "source_unavailable"),
    ],
)
def test_head_other_than_the_listing_is_stale_plan_without_get(
    root, server, tmp_path, head, status, code
):
    serve(server, "hydro_listing")
    plan = check_store(
        root, datasets=[HYDRO], stations=[S1], years=[2024], plan=tmp_path / "plan.json"
    )
    assert [item.status for item in plan.items] == ["missing"]
    (download,) = serve(server, "h900001_2024_get")
    serve(server, head)
    notices = []

    report = sync_store(
        root, plan=tmp_path / "plan.json", series=False, on_notice=notices.append
    )

    assert [(item.status, item.error_code) for item in report.items] == [(status, code)]
    assert not download.called
    assert not slot_dir(root, H1_2024).exists()
    if status == "stale_plan":
        assert [notice.code for notice in notices] == ["stale_plan"]
    else:
        assert "ČHMÚ" in report.items[0].error


@pytest.mark.parametrize(
    ("listing", "code"),
    [
        ("hydro_listing_error", "source_unavailable"),
        ("hydro_listing_empty", "data_error"),
        ("hydro_listing_foreign", "data_error"),
    ],
)
def test_unusable_listing_fails_every_item_of_its_directory(
    root, server, listing, code
):
    serve(server, listing)
    notices = []

    plan = check_store(
        root,
        datasets=[HYDRO],
        stations=[S1, S2],
        years=[2004, 2023],
        on_notice=notices.append,
    )

    assert [item.status for item in plan.items] == ["check_failed"] * 4
    assert len({item.error for item in plan.items}) == 1  # the listing's error
    assert {notice.code for notice in notices} == {"archive_failed"}
    assert plan.actions == ()
    report = sync_store(root, plan=plan, series=False)
    assert [(item.status, item.error_code) for item in report.items] == [
        ("failed", code)
    ] * 4
    assert traffic(server) == [("GET", f"{DAILY}/")]

    # Without years the files are unknown: one check_failed action per station.
    unknown = check_store(root, datasets=[HYDRO], stations=[S1, S2])
    assert unknown.items == ()
    assert [
        (action.status, action.detail.split(":")[0]) for action in unknown.actions
    ] == [
        ("check_failed", f"stacja {S1}"),
        ("check_failed", f"stacja {S2}"),
    ]
    synced = sync_store(root, datasets=[HYDRO], stations=[S1, S2])
    assert [(item.slot, item.status, item.error_code) for item in synced.items] == [
        (None, "failed", code)
    ] * 2
    assert synced.series == ()


def test_other_content_under_the_same_canonical_form_is_one_observation(root, server):
    first = publish_first(root, server)
    current = first.items[0].version
    serve(server, "hydro_listing_reserialized")
    newer = check_store(root, datasets=[HYDRO], stations=[S1], years=[2023])
    assert [item.status for item in newer.items] == ["newer"]
    serve(server, "h900001_2023_reserialized_head", "h900001_2023_reserialized_get")
    notices = []

    report = sync_store(root, plan=newer, series=False, on_notice=notices.append)

    reserialized = payload(CASES["h900001_2023_reserialized_get"])
    assert [(item.status, item.version) for item in report.items] == [
        ("unchanged", current)
    ]
    assert versions(root, H1_2023) == [current.parent.name]
    (observation,) = register(root, H1_2023)
    recorded = json.loads(observation.read_text(encoding="utf-8"))
    assert schema_errors(recorded, "imgw-observation/1") == []
    headers = CASES["h900001_2023_reserialized_get"]["headers"]
    assert {
        key: recorded[key]
        for key in ("etag", "last_modified", "size_bytes", "sha256", "same_content_as")
    } == {
        "etag": headers["ETag"],
        "last_modified": headers["Last-Modified"],
        "size_bytes": len(reserialized),
        "sha256": sha(reserialized),
        "same_content_as": current.parent.name,
    }
    (unchanged,) = [notice for notice in notices if notice.code == "content_unchanged"]
    assert unchanged.level == "info" and sha(reserialized) in unchanged.text

    start = len(server.calls)
    again = check_store(root, datasets=[HYDRO], stations=[S1], years=[2023])
    assert [item.status for item in again.items] == ["current"]
    assert again.items[0].local_observation == observation.relative_to(root)
    assert traffic(server, start) == [("GET", f"{DAILY}/")]

    repeated = sync_store(root, plan=newer, series=False)
    assert [item.status for item in repeated.items] == ["unchanged"]
    assert register(root, H1_2023) == [observation]

    serve(server, "hydro_listing_rewritten")
    later = check_store(root, datasets=[HYDRO], stations=[S1], years=[2023])
    assert [item.status for item in later.items] == ["newer"]
    assert later.items[0].local_observation == observation.relative_to(root)


def test_broken_observation_of_the_current_version_fails_only_its_item(root, server):
    publish_first(root, server)
    serve(
        server,
        "hydro_listing_reserialized",
        "h900001_2023_reserialized_head",
        "h900001_2023_reserialized_get",
    )
    sync_store(root, datasets=[HYDRO], stations=[S1], series=False)
    (observation,) = register(root, H1_2023)
    observation.write_text("{", encoding="utf-8")

    plan = check_store(root, datasets=[HYDRO], stations=[S1])

    assert [item.status for item in plan.items] == ["check_failed", "current"]
    report = sync_store(root, plan=plan, series=False)
    assert [(item.status, item.error_code) for item in report.items] == [
        ("failed", "data_error"),
        ("unchanged", None),
    ]


def test_meteo_station_has_four_files_and_missing_elements_are_unpublished(
    root, server
):
    serve(server, "precipitation_listing", "temperature_listing")
    elements = ("SRA", "T", "TMA", "TMI")
    serve(
        server,
        "m90000000002_SRA_head",
        "m90000000002_SRA_get",
        *(
            f"m90001_{element}_{method}"
            for element in elements
            for method in ("head", "get")
        ),
    )

    plan = check_store(root, datasets=[METEO], stations=[FULL, RAIN, S1])

    assert len(server.calls) == 2  # one listing per directory, no HEAD or GET
    assert [
        (item.station_code, item.archive.param, item.status) for item in plan.items
    ] == [
        (RAIN, "SRA", "missing"),
        (RAIN, "T", "unverifiable"),
        (RAIN, "TMA", "unverifiable"),
        (RAIN, "TMI", "unverifiable"),
        *((FULL, element, "missing") for element in elements),
    ]
    assert {item.error for item in plan.items[1:4]} == {"nieopublikowany"}
    assert [action.detail for action in plan.actions] == [
        f"stacja {S1}: brak plików zbioru {METEO} u źródła"
    ]
    report = sync_store(root, plan=plan, series=False)
    assert [item.status for item in report.items] == [
        "created",
        *["unchanged"] * 3,
        *["created"] * 4,
    ]
    meta = json.loads(
        Path(f"{report.items[0].version}.meta.json").read_text(encoding="utf-8")
    )
    assert "content_sha256" not in meta and "content_form" not in meta
    assert meta["request"] == {
        "server_path": plan.items[0].archive.server_path,
        "year": None,
        "month": None,
        "station_code": RAIN,
        "param": "SRA",
    }
    assert meta["extra"]["period"]["year_type"] == "none"

    # Other bytes of a CSV file (no canonical form) are a new version.
    sra = report.items[4].version
    serve(
        server,
        "precipitation_listing_corrected",
        "m90001_SRA_corrected_head",
        "m90001_SRA_corrected_get",
    )
    changed = check_store(root, datasets=[METEO], stations=[FULL])
    assert [item.status for item in changed.items] == [
        "newer",
        "current",
        "current",
        "current",
    ]
    corrected = sync_store(root, plan=changed, series=False)
    assert [item.status for item in corrected.items] == ["created", *["unchanged"] * 3]
    assert corrected.items[0].version != sra and sra.is_file()
    assert corrected.items[0].version.read_bytes() == payload(
        CASES["m90001_SRA_corrected_get"]
    )


def test_unreadable_meteo_directory_fails_only_its_elements(root, server):
    serve(server, "precipitation_listing", "temperature_listing_error")

    plan = check_store(root, datasets=[METEO], stations=[FULL, RAIN])

    assert [
        (item.station_code, item.archive.param, item.status) for item in plan.items
    ] == [
        (RAIN, "SRA", "missing"),
        (RAIN, "T", "check_failed"),
        (RAIN, "TMA", "check_failed"),
        (RAIN, "TMI", "check_failed"),
        (FULL, "SRA", "missing"),
        (FULL, "T", "check_failed"),
        (FULL, "TMA", "check_failed"),
        (FULL, "TMI", "check_failed"),
    ]
    assert plan.items[1].error.startswith("Błąd HTTP 503")


def test_cancel_before_the_listing_and_between_files(root, server):
    serve(server, "hydro_listing")
    plan = check_store(
        root, datasets=[HYDRO], stations=[S1], years=[2023, 2024], cancel=lambda: True
    )
    assert plan.cancelled and not server.calls
    assert [(item.status, item.error) for item in plan.items] == [
        ("unverifiable", "anulowano")
    ] * 2

    polls = iter([False, False, True])
    partial = check_store(
        root,
        datasets=[HYDRO],
        stations=[S1],
        years=[2023, 2024],
        cancel=lambda: next(polls, True),
    )
    assert partial.cancelled and len(server.calls) == 1
    assert [(item.status, item.error) for item in partial.items] == [
        ("missing", None),
        ("unverifiable", "anulowano"),
    ]
    serve(server, "h900001_2023_head", "h900001_2023_get")
    report = sync_store(root, plan=partial, series=False)
    assert [item.status for item in report.items] == ["created", "cancelled"]
    assert report.cancelled is True


@pytest.mark.parametrize(
    ("options", "option"),
    [
        (
            {
                "datasets": [HYDRO, "pl.imgw.hydro_daily"],
                "stations": [S1],
                "years": [2024],
            },
            "stations",
        ),
        ({"datasets": [HYDRO, "pl.imgw.hydro_daily"], "years": [2024]}, "stations"),
        ({"datasets": [HYDRO], "years": [2024]}, "stations"),
        ({"datasets": [HYDRO], "stations": ["149190310"]}, "stations"),
        ({"datasets": [HYDRO], "stations": S1}, "stations"),
        ({"datasets": [HYDRO], "stations": [S1], "years": [1886]}, "years"),
        (
            {"datasets": [HYDRO], "stations": [S1], "years": [2024], "months": [1]},
            "months",
        ),
        ({"datasets": [METEO], "stations": [FULL], "years": [2024]}, "years"),
        (
            {"datasets": ["pl.imgw.hydro_daily"], "years": [2024], "stations": [S1]},
            "stations",
        ),
        ({"datasets": ["pl.imgw.hydro_daily"]}, "years"),
    ],
)
def test_selectors_are_validated_before_any_request(root, server, options, option):
    for function in (check_store, sync_store):
        with pytest.raises(IMGWValidationError) as error:
            function(root, **options)
        assert error.value.details["option"] == option
    assert not server.calls


def test_invalid_station_code_is_named_and_plan_excludes_stations(root, server):
    with pytest.raises(IMGWValidationError) as error:
        check_store(root, datasets=[METEO], stations=[FULL, "0-203-0-ab"])
    assert error.value.details["value"] == ["0-203-0-ab"]
    plan = StorePlan("imgw-plan/1", root, datetime.now(UTC), (), {})
    with pytest.raises(IMGWValidationError):
        sync_store(root, plan=plan, stations=[S1])
    assert not server.calls


def test_imgw_plan_counts_its_listing_and_head_requests(root, server):
    (archive,) = archive_files("pl.imgw.hydro_daily", years=[2024])
    server.get(f"{IMGW_PUBLIC_DATA_URL}/dane_hydrologiczne/dobowe/2024/").respond(
        200, text='<a href="codz_2024.zip">codz_2024.zip</a>'
    )
    server.head(archive.url).respond(
        200, headers={"ETag": '"v1"', "Last-Modified": "Sat, 17 Oct 2026 12:00:00 GMT"}
    )

    plan = check_store(root, datasets=["pl.imgw.hydro_daily"], years=[2024])

    assert plan.requests == {"made": 2, "planned": 2}
    (item,) = plan.items
    assert (item.signal, item.station_code, item.remote_listed_at) == (
        "head",
        None,
        None,
    )
