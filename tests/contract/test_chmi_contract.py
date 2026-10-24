"""Contract of the ČHMÚ provider: IMGW-15..IMGW-19 on complete_pl_cz and recordings.

Spec 2026-10-18 §14 and §16 (C09). Every row of the acceptance table is a test
whose name carries the row: the ``complete_pl_cz`` store of
``imgwtools.testing`` (built at the frozen clock of the contract suite) and the
recorded ČHMÚ answers of ``chmi_recordings.json``,
``chmi_catalog_recordings.json`` and ``chmi_builder_recordings.json``. The ČHMÚ
commands answer alike in Python, ``imgw``, REST and MCP at a frozen clock
(IMGW-19 k1): canonical envelopes, the same requests to the recordings, the
same SHA-256 of every written file and the same plan of every write. No request
leaves the recordings.
"""

import csv
import importlib
import importlib.util
import io
import json
import shutil
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from imgwtools import (
    IMGWValidationError,
    add_project_task,
    build_catalog,
    build_series,
    check_catalog,
    check_store,
    current_version,
    download_project,
    export_archive,
    export_series,
    get_provider,
    init_project,
    init_store,
    iter_store,
    open_project,
    parse_chmi_stations,
    read_catalog,
    read_series_index,
    run_command,
    store_info,
    sync_store,
    verify_project,
)
from imgwtools.datasets import get_dataset
from imgwtools.testing import build_fixture_store, fixture_files
from tests.contract.conftest import _CLOCKED, FROZEN_AT
from tests.contract.support import (
    DAILY,
    H2024,
    NEW,
    RABA,
    V3,
    canonical,
    cli_words,
    command_document,
    load,
    rest_request,
    schema_errors,
    sha256,
    slots,
    snapshot,
    stamps,
    unversioned,
)
from tests.contract.test_interface_contract import (
    LABELS,
    ROUTES,
    answer,
    assert_alike,
    relative_reference_dir,  # noqa: F401 (fixture)
    rooted,
)

HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
# Fictional stations of the fixtures (spec 2026-10-18 §13.2).
S1, S2 = "0-203-1-900001", "0-203-1-900002"  # 2023-2024 / 2004 and 2006 (2005 unknown)
FULL, RAIN = "0-203-0-90001", "0-203-0-90000000002"  # four elements / SRA only
ONLY_LISTED = "0-203-1-CB900003"  # in the station metadata, no daily files
CHMI_PROVIDER = get_provider("CHMI")
SOURCE = CHMI_PROVIDER.license.attribution
PROCESSED = CHMI_PROVIDER.processed_attribution
SLOT_2023 = f"archive:{HYDRO}:H_{S1}_DQ_2023.json"
SLOT_2024 = f"archive:{HYDRO}:H_{S1}_DQ_2024.json"
DAILY_DIR = "archives/versions/hydrology/historical/data/daily"
LIST_DIR = "archives/versions/hydrology/historical/metadata/meta1"
# ČHMÚ catalog sources: lists by HEAD (stored, current), then the live metadata.
CATALOG_HEADS = (
    "hydro_stations_head",
    "meteo_stations_head",
    "hydro_now_get",
    "hydro_meta3_get",
    "meteo_now_listing",
    "meteo_now_get",
)
CATALOG_GETS = (*CATALOG_HEADS, "hydro_stations_get", "meteo_stations_get")
FIRST_900001 = (
    "hydro_listing",
    "h900001_2023_head",
    "h900001_2023_get",
    "h900001_2024_head",
    "h900001_2024_get",
)
MCP = importlib.util.find_spec("mcp") is not None
INTERFACES = ("python", "cli", "rest", "mcp") if MCP else ("python", "cli", "rest")
LOCAL_INTERFACES = ("python", "cli", "mcp") if MCP else ("python", "cli")


# --------------------------------------------------------------------------
# Recorded opendata.chmi.cz
# --------------------------------------------------------------------------


def _recorded() -> dict[str, dict[str, Any]]:
    """Every recorded ČHMÚ interaction by case; equal duplicates across files."""
    found: dict[str, dict[str, Any]] = {}
    for name in (
        "chmi_recordings.json",
        "chmi_catalog_recordings.json",
        "chmi_builder_recordings.json",
    ):
        document = json.loads(fixture_files().joinpath(name).read_text("utf-8"))
        for entry in document["interactions"]:
            found.setdefault(
                entry["case"], {**entry, "url": document["base_url"] + entry["path"]}
            )
    return found


CHMI = _recorded()


def content(case: str) -> bytes:
    """Body of a recorded answer."""
    entry = CHMI[case]
    if "listing" in entry or "variant" in entry:
        relative = entry.get("listing") or entry["variant"]
        return fixture_files().joinpath(*relative.split("/")).read_bytes()
    if "archive" in entry:
        return (
            fixture_files()
            .joinpath("archives", *entry["archive"].split("/"))
            .read_bytes()
        )
    return str(entry.get("body", "")).encode("utf-8")


class FakeChmi:
    """opendata.chmi.cz answering recorded cases; respx refuses any other request.

    A later case for the same request replaces the earlier one.
    """

    def __init__(self, router: Any) -> None:
        self.router = router

    def serve(self, *cases: str) -> None:
        for case in cases:
            entry = CHMI[case]
            route = self.router.route(method=entry["method"], url=entry["url"])
            if "exception" in entry:
                route.mock(side_effect=httpx.ConnectError("synthetyczny błąd sieci"))
                continue
            body = b"" if entry["method"] == "HEAD" else content(case)
            route.mock(
                return_value=httpx.Response(
                    entry["status"], headers=entry.get("headers"), content=body
                )
            )

    def traffic(self, start: int = 0) -> list[tuple[str, str]]:
        return [
            (call.request.method, str(call.request.url))
            for call in self.router.calls[start:]
        ]


@pytest.fixture
def chmi(imgw) -> FakeChmi:
    """Recorded ČHMÚ on the respx router of the recorded IMGW-PIB."""
    return FakeChmi(imgw.router)


# --------------------------------------------------------------------------
# Stores at the frozen clock
# --------------------------------------------------------------------------


def _frozen_build(path: Path, variant: str) -> Path:
    """``build_fixture_store`` at the frozen clock of the suite (reproducible bytes)."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    with pytest.MonkeyPatch.context() as patch:
        for name in _CLOCKED:
            patch.setattr(importlib.import_module(name), "datetime", Frozen)
        return build_fixture_store(path, variant=variant).root  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def pl_cz(tmp_path_factory) -> Path:
    """``complete_pl_cz``, read-only: tests that write take a copy."""
    return _frozen_build(tmp_path_factory.mktemp("pl_cz") / "store", "complete_pl_cz")


@pytest.fixture(scope="module")
def complete(tmp_path_factory) -> Path:
    """``complete`` (IMGW-PIB only) at the same frozen clock."""
    return _frozen_build(tmp_path_factory.mktemp("complete") / "store", "complete")


def copy_of(store: Path, target: Path) -> Path:
    shutil.copytree(store, target)
    return target


def relative(root: Path, path: Path | None) -> str | None:
    return None if path is None else path.relative_to(root).as_posix()


def version_of(root: Path, slot: str) -> Path:
    entry = current_version(root, slot=slot)
    assert entry is not None and entry.version is not None, slot
    return entry.version


def sidecars(root: Path) -> dict[Path, dict[str, Any]]:
    """Sidecars of the ČHMÚ versions of a store."""
    found = {path: load(path) for path in sorted(root.rglob("*.meta.json"))}
    return {path: meta for path, meta in found.items() if meta["provider"] == "CHMI"}


def statuses(items: Iterator[Any] | tuple[Any, ...]) -> list[str]:
    return [item.status for item in items]


# --------------------------------------------------------------------------
# IMGW-15: contracts, scan and providers
# --------------------------------------------------------------------------


def test_imgw_15_chmi_documents_meet_the_1_contracts_and_imgw_bytes_stay(
    pl_cz, complete, tmp_path, chmi, frozen
):
    assert schema_errors(load(pl_cz / "imgw-store.json"), "imgw-store/1") == []
    contracts = {"series.json": "imgw-series/1", "stations.geojson": "stations.geojson"}
    found = sidecars(pl_cz)
    # 12 archives, 2 station lists, 3 series versions and the catalog.
    assert len(found) == 18
    for sidecar, meta in found.items():
        assert schema_errors(meta, "imgw-meta/1") == [], sidecar
        main = sidecar.with_name(sidecar.name.removesuffix(".meta.json"))
        if main.name in contracts:
            assert schema_errors(load(main), contracts[main.name]) == [], main
    (observation,) = pl_cz.glob(f"{DAILY_DIR}/*/observations/*.json")
    assert schema_errors(load(observation), "imgw-observation/1") == []

    chmi.serve("hydro_listing_reserialized")
    plan = check_store(
        pl_cz, datasets=[HYDRO], stations=[S1], years=[2023], plan=tmp_path / "p.json"
    )
    assert plan.items[0].local_observation is not None
    assert schema_errors(load(tmp_path / "p.json"), "imgw-plan/1") == []

    # The IMGW-PIB part of the store is the ``complete`` store, byte for byte.
    both, alone = snapshot(pl_cz), snapshot(complete)
    assert {path: both[path] for path in alone} == alone
    added = sorted(set(both) - set(alone))
    assert added and all(
        path.startswith(
            (
                "archives/versions/hydrology",
                "archives/versions/meteorology",
                "series/versions/chmi_",
                "stations/versions/chmi_stations",
            )
        )
        for path in added
    )


def test_imgw_15_k1_both_providers_scan_clean_with_a_provider_on_every_entry(pl_cz):
    entries = list(iter_store(pl_cz))

    assert [entry.problem for entry in entries if entry.kind == "problem"] == []
    assert {entry.provider for entry in entries} == {"IMGW-PIB", "CHMI"}
    (seen,) = [entry for entry in entries if entry.kind == "observation"]
    assert (seen.provider, seen.slot) == ("CHMI", SLOT_2023)
    assert {
        entry.slot: entry.provider for entry in entries if entry.kind == "catalog"
    } == {
        "catalog:pl.imgw.stations": "IMGW-PIB",
        "catalog:cz.chmi.stations": "CHMI",
    }
    features = read_catalog(root=pl_cz)
    pairs = [(feature.provider, feature.station_code) for feature in features]
    assert len(pairs) == len(set(pairs))
    assert {provider for provider, _ in pairs} == {"IMGW-PIB", "CHMI"}
    # Each provider's catalog is a separate entry with its own stations.
    assert {
        feature.provider for feature in read_catalog(root=pl_cz, provider="CHMI")
    } == {"CHMI"}


def _scan(root: Path, **filters: str) -> list[tuple[object, ...]]:
    return [
        (entry.kind, entry.slot, entry.provider, relative(root, entry.version))
        for entry in iter_store(root, **filters)
    ]


def test_imgw_15_k2_a_store_without_chmi_reads_as_before(complete, pl_cz):
    assert {entry.provider for entry in iter_store(complete)} == {"IMGW-PIB"}
    assert _scan(complete) == _scan(pl_cz, provider="IMGW-PIB")
    assert store_info(complete).contracts == store_info(pl_cz).contracts
    assert read_catalog(root=complete) == read_catalog(root=pl_cz, provider="IMGW-PIB")
    assert {feature.provider for feature in read_catalog(root=complete)} == {"IMGW-PIB"}


def test_imgw_15_k3_store_info_names_the_providers_and_the_scan_filters(pl_cz):
    assert [provider.id for provider in store_info(pl_cz).providers] == [
        "IMGW-PIB",
        "CHMI",
    ]
    chmi = _scan(pl_cz, provider="CHMI")
    imgw = _scan(pl_cz, provider="IMGW-PIB")
    assert {row[2] for row in chmi} == {"CHMI"}
    assert {row[2] for row in imgw} == {"IMGW-PIB"}
    assert sorted(chmi + imgw, key=repr) == sorted(_scan(pl_cz), key=repr)
    assert Counter(row[0] for row in chmi) == {
        "archive": 14,
        "observation": 1,
        "series": 3,
        "catalog": 1,
    }


# --------------------------------------------------------------------------
# IMGW-16: freshness from the listing, versions only for new content
# --------------------------------------------------------------------------


def test_imgw_16_k1_check_states_come_from_one_listing_without_any_content(
    pl_cz, tmp_path, chmi
):
    before = stamps(pl_cz)
    chmi.serve("hydro_listing_reserialized")

    plan = check_store(pl_cz, datasets=[HYDRO], stations=[S1, S2], years="2023-2024")

    states = {
        (item.station_code, item.archive.year): (item.status, item.error)
        for item in plan.items
    }
    assert states == {
        (S1, 2023): ("current", None),  # the observation of scenario (8)
        (S1, 2024): ("newer", None),  # the listing shows the first publication
        (S2, 2023): ("unverifiable", "not published"),
        (S2, 2024): ("unverifiable", "not published"),
    }
    first = plan.items[0]
    assert first.local_observation is not None
    assert first.local_observation.parent.name == "observations"
    assert chmi.traffic() == [("GET", CHMI["hydro_listing"]["url"])]
    assert plan.requests == {"made": 1, "planned": 2}

    chmi.serve("precipitation_listing", "temperature_listing")
    start = len(chmi.router.calls)
    meteo = check_store(pl_cz, datasets=[METEO], stations=[FULL, RAIN])
    assert Counter((item.station_code, item.status) for item in meteo.items) == {
        (FULL, "current"): 4,
        (RAIN, "current"): 1,
        (RAIN, "unverifiable"): 3,
    }
    assert [method for method, _ in chmi.traffic(start)] == ["GET", "GET"]
    assert meteo.requests == {"made": 2, "planned": 0}

    empty = init_store(tmp_path / "empty").root
    chmi.serve("hydro_listing")
    start = len(chmi.router.calls)
    missing = check_store(empty, datasets=[HYDRO], stations=[S1])
    assert statuses(missing.items) == ["missing", "missing"]
    assert missing.requests == {"made": 1, "planned": 4}
    assert [method for method, _ in chmi.traffic(start)] == ["GET"]
    assert stamps(pl_cz) == before


def _versions(root: Path, slot_dir: str) -> list[str]:
    return sorted(
        path.name for path in (root / slot_dir).iterdir() if path.name != "observations"
    )


def _register(root: Path, slot_dir: str) -> list[str]:
    directory = root / slot_dir / "observations"
    return (
        sorted(path.name for path in directory.iterdir()) if directory.exists() else []
    )


def test_imgw_16_k2_a_version_only_for_new_content(pl_cz, tmp_path, chmi, frozen):
    root = copy_of(pl_cz, tmp_path / "store")
    slot_2023 = f"{DAILY_DIR}/H_{S1}_DQ_2023"
    (first,) = _versions(root, slot_2023)
    (seen,) = _register(root, slot_2023)

    # The same bytes under a new signal: a relabeled version, the series reused.
    chmi.serve(
        "hydro_listing_republished",
        "h900001_2023_republished_head",
        "h900001_2023_republished_get",
    )
    relabeled = sync_store(root, datasets=[HYDRO], stations=[S1], years=[2023])
    assert statuses(relabeled.items) == ["relabeled"]
    assert statuses(relabeled.series) == ["reused"]
    assert _versions(root, slot_2023) == sorted([first, f"2026-02-06_{first[-8:]}"])

    # Other bytes of the same canonical content: no version, one more observation.
    notices = []
    chmi.serve(
        "hydro_listing_rewritten",
        "h900001_2023_rewritten_head",
        "h900001_2023_rewritten_get",
    )
    unchanged = sync_store(
        root, datasets=[HYDRO], stations=[S1], years=[2023], on_notice=notices.append
    )
    assert statuses(unchanged.items) == ["unchanged"]
    assert [notice.code for notice in notices] == ["content_unchanged"]
    assert len(_versions(root, slot_2023)) == 2
    assert len(_register(root, slot_2023)) == 2 and seen in _register(root, slot_2023)

    # Other content (a corrected CSV, no canonical form): a new version.
    sra = (
        "archives/versions/meteorology/climate/historical_csv/data/daily/"
        f"precipitation/dly-{FULL}-SRA"
    )
    (old,) = _versions(root, sra)
    chmi.serve(
        "precipitation_listing_corrected",
        "temperature_listing",
        "m90001_SRA_corrected_head",
        "m90001_SRA_corrected_get",
    )
    corrected = sync_store(root, datasets=[METEO], stations=[FULL])
    assert statuses(corrected.items) == [
        "created",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert statuses(corrected.series) == ["created"]
    assert len(_versions(root, sra)) == 2 and old in _versions(root, sra)
    assert [
        entry.problem for entry in iter_store(root) if entry.kind == "problem"
    ] == []


@pytest.mark.parametrize("after_download", [0, 1], ids=["before-staging", "staged"])
@pytest.mark.parametrize("change", ["observation", "version"])
def test_imgw_16_k2_cancelling_a_write_leaves_no_version_and_no_observation(
    change, after_download, pl_cz, tmp_path, chmi, frozen
):
    root = copy_of(pl_cz, tmp_path / "store")
    if change == "observation":
        get = "h900001_2023_rewritten_get"
        chmi.serve("hydro_listing_rewritten", "h900001_2023_rewritten_head", get)
        selectors: dict[str, Any] = {
            "datasets": [HYDRO],
            "stations": [S1],
            "years": [2023],
        }
    else:
        get = "m90001_SRA_corrected_get"
        chmi.serve(
            "precipitation_listing_corrected",
            "temperature_listing",
            "m90001_SRA_corrected_head",
            get,
        )
        selectors = {"datasets": [METEO], "stations": [FULL]}
    url = CHMI[get]["url"]
    polls_after = []

    def cancel() -> bool:
        if not any(call.request.url == url for call in chmi.router.calls):
            return False
        polls_after.append(True)
        return bool(len(polls_after) > after_download)

    before = snapshot(root)
    report = sync_store(root, **selectors, cancel=cancel)

    assert "cancelled" in statuses(report.items) and report.cancelled
    assert statuses(report.series) == ["cancelled"]
    # Only the (empty) staging directory may differ: no version, no observation.
    after = snapshot(root)
    assert {path: digest for path, digest in after.items() if path != ".incoming"} == {
        path: digest for path, digest in before.items() if path != ".incoming"
    }
    incoming = root / ".incoming"
    assert not incoming.exists() or not any(incoming.iterdir())


def test_imgw_16_k3_the_plan_names_stations_files_sizes_and_requests(tmp_path, chmi):
    root = init_store(tmp_path / "store").root
    chmi.serve("hydro_listing")

    plan = check_store(
        root,
        datasets=[HYDRO],
        stations=[S1, S2, ONLY_LISTED],
        years=[2004, 2005, 2006, 2023, 2024],
        plan=tmp_path / "plan.json",
    )

    listed = {
        item.archive.server_path: (
            item.station_code,
            item.status,
            item.content_length,
            item.remote_listed_at,
        )
        for item in plan.items
        if item.status == "missing"
    }
    daily = "hydrology/historical/data/daily"
    assert listed == {
        f"{daily}/H_{S1}_DQ_2023.json": (S1, "missing", 23926, "2025-07-01T12:07Z"),
        f"{daily}/H_{S1}_DQ_2024.json": (S1, "missing", 21835, "2025-07-01T12:07Z"),
        f"{daily}/H_{S2}_DQ_2004.json": (S2, "missing", 13263, "2025-07-01T12:07Z"),
        f"{daily}/H_{S2}_DQ_2006.json": (S2, "missing", 21746, "2025-07-01T12:07Z"),
    }
    assert {
        (item.station_code, item.archive.year, item.error) for item in plan.items
    } >= {(S2, 2005, "not published")}
    assert [(action.command, action.status) for action in plan.actions] == [
        ("store sync", "unverifiable")
    ]
    assert ONLY_LISTED in plan.actions[0].detail
    assert plan.requests == {"made": 1, "planned": 8}
    document = load(tmp_path / "plan.json")
    assert schema_errors(document, "imgw-plan/1") == []
    assert document["requests"] == {"made": 1, "planned": 8}
    assert {item["station_code"] for item in document["items"]} >= {S1, S2}


# --------------------------------------------------------------------------
# IMGW-17: the ČHMÚ station catalog
# --------------------------------------------------------------------------

# Recorded metadata files of the catalog with their station family.
METADATA = (
    ("hydro_now_get", "hydro"),
    ("hydro_meta3_get", "hydro"),
    ("hydro_stations_get", "hydro"),
    ("meteo_now_get", "meteo"),
    ("meteo_stations_get", "meteo"),
)


def test_imgw_17_k1_every_station_of_the_chmi_metadata_is_in_the_catalog(pl_cz):
    published = {
        entry.station_code
        for case, kind in METADATA
        for entry in parse_chmi_stations(content(case), kind=kind)
    }

    features = read_catalog(root=pl_cz, provider="CHMI")

    assert {feature.station_code for feature in features} == published
    unlocated = [feature for feature in features if feature.geometry is None]
    assert unlocated and all(
        feature.properties["location_missing_reason"] is not None
        for feature in unlocated
    )


def _rows(case: str, code: str) -> dict[str, list[dict[str, object]]]:
    """Rows of a recorded metadata envelope by station code, numbers as decimals."""
    document = json.loads(content(case), parse_float=Decimal, parse_int=Decimal)
    data = document["data"]["data"]
    header = data["header"].split(",")
    rows: dict[str, list[dict[str, object]]] = {}
    for values in data["values"]:
        row = dict(zip(header, values, strict=True))
        rows.setdefault(str(row[code]), []).append(row)
    return rows


def test_imgw_17_k2_codes_stay_text_and_coordinates_equal_the_published_decimals(
    pl_cz,
):
    catalog = version_of(pl_cz, "catalog:cz.chmi.stations")
    document = json.loads(catalog.read_text("utf-8"), parse_float=Decimal)
    sources = {
        "chmi_hydro_now": (_rows("hydro_now_get", "objID"), "GEOGR1", "GEOGR2"),
        "chmi_hydro_meta3": (_rows("hydro_meta3_get", "objID"), "GEOGR1", "GEOGR2"),
        "chmi_hydro_stations": (
            _rows("hydro_stations_get", "objID"),
            "GEOGR1",
            "GEOGR2",
        ),
        # Meteo GEOGR1 is the longitude (spec §7.2).
        "chmi_meteo_now": (_rows("meteo_now_get", "WSI"), "GEOGR2", "GEOGR1"),
        "chmi_meteo_stations": (_rows("meteo_stations_get", "WSI"), "GEOGR2", "GEOGR1"),
    }
    located = 0
    for feature in document["features"]:
        properties = feature["properties"]
        assert isinstance(properties["station_code"], str)
        assert feature["id"] == properties["station_code"]
        code = properties["hydrographic_code"]
        assert code is None or isinstance(code, str)
        if feature["geometry"] is None:
            continue
        rows, latitude, longitude = sources[properties["location_source"]]
        row = max(
            rows[properties["station_code"]], key=lambda row: str(row.get("BEGIN_DATE"))
        )
        assert feature["geometry"]["coordinates"] == [row[longitude], row[latitude]]
        located += 1
    assert located >= 5
    hydro = {
        f["properties"]["station_code"]: f["properties"] for f in document["features"]
    }
    assert hydro[S1]["hydrographic_code"] == "1-05-03-0110"


def test_imgw_17_k3_a_new_metadata_envelope_creates_no_version(
    pl_cz, tmp_path, chmi, frozen
):
    root = copy_of(pl_cz, tmp_path / "store")
    catalog = version_of(root, "catalog:cz.chmi.stations")
    (listed,) = _versions(root, LIST_DIR)
    chmi.serve(
        "hydro_stations_regenerated_head",
        "hydro_stations_regenerated_get",
        "meteo_stations_head",
        "hydro_now_regenerated_get",
        "hydro_meta3_get",
        "meteo_now_listing",
        "meteo_now_get",
    )
    notices = []

    report = build_catalog(root, provider="CHMI", on_notice=notices.append)

    assert (report.status, report.version, report.provider) == (
        "unchanged",
        catalog,
        "CHMI",
    )
    assert _versions(root, LIST_DIR) == [listed]
    (seen,) = _register(root, LIST_DIR)
    observation = load(root / LIST_DIR / "observations" / seen)
    assert schema_errors(observation, "imgw-observation/1") == []
    assert observation["same_content_as"] == listed
    (unchanged,) = [notice for notice in notices if notice.code == "content_unchanged"]
    assert unchanged.level == "info"
    assert "archive:cz.chmi.hydro_stations:meta1.json" in unchanged.text

    chmi.serve("hydro_stations_regenerated_head")
    plan = check_catalog(root, provider="CHMI")
    (item,) = [
        item for item in plan.items if item.archive.dataset == "cz.chmi.hydro_stations"
    ]
    assert item.status == "current"
    assert item.local_observation == Path(LIST_DIR, "observations", seen)


# --------------------------------------------------------------------------
# IMGW-18: series and coverage, computed by hand from the stored files
# --------------------------------------------------------------------------

HYDRO_SERIES = {"HD": "H", "QD": "Q", "TD": "T"}
METEO_ELEMENTS = {"SRA": "P", "T": "Tmean", "TMA": "Tmax", "TMI": "Tmin"}


@dataclass
class Station:
    """Daily values read by hand from the current stored files of a station."""

    known: set[date] = field(default_factory=set)
    values: dict[str, dict[date, float | None]] = field(default_factory=dict)
    rows: dict[str, dict[date, dict[str, str]]] = field(default_factory=dict)


def _days(first: date, last: date) -> Iterator[date]:
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _current_files(root: Path, dataset: str, pattern: str) -> Iterator[Path]:
    """
    The current version of every slot directory matching ``pattern``.

    The slot selector of a ČHMÚ file is its path below the dataset's directory.
    """
    base = root / "archives" / "versions" / str(get_dataset(dataset).server_dir)
    suffix = ".json" if dataset == HYDRO else ".csv"
    for directory in sorted(root.glob(pattern)):
        selector = directory.relative_to(base).as_posix() + suffix
        yield version_of(root, f"archive:{dataset}:{selector}")


def hydro_by_hand(root: Path, code: str) -> Station:
    station = Station(values={name: {} for name in HYDRO_SERIES.values()})
    for path in _current_files(root, HYDRO, f"{DAILY_DIR}/H_{code}_DQ_*"):
        year = int(path.stem.rsplit("_", 1)[1])
        station.known |= set(_days(date(year, 1, 1), date(year, 12, 31)))
        for series in json.loads(path.read_bytes())["tsList"]:
            name = HYDRO_SERIES.get(series["tsConID"])
            if name is None:
                continue  # PD: suspended sediment, outside the dataset
            for moment, value in series["tsData"]["data"]["values"]:
                station.values[name][date.fromisoformat(moment[:10])] = (
                    None if value is None else float(value)
                )
    return station


def meteo_by_hand(root: Path, code: str) -> Station:
    station = Station(
        values={name: {} for name in METEO_ELEMENTS.values()},
        rows={name: {} for name in METEO_ELEMENTS.values()},
    )
    pattern = (
        "archives/versions/meteorology/climate/historical_csv/data/daily/*/"
        f"dly-{code}-*"
    )
    for path in _current_files(root, METEO, pattern):
        element = path.stem.rsplit("-", 1)[1]
        name = METEO_ELEMENTS[element]
        dates = []
        for row in csv.DictReader(io.StringIO(path.read_text("utf-8"))):
            if element == "T" and row["TIMEFUNC"] != "AVG":
                continue  # observation terms of T are not daily values
            day = date.fromisoformat(row["DT"][:10])
            dates.append(day)
            station.rows[name][day] = row
            station.values[name][day] = float(row["VALUE"]) if row["VALUE"] else None
        station.known |= set(_days(min(dates), max(dates)))
    return station


def coverage_by_hand(station: Station, name: str) -> dict[str, object]:
    """first, last, with_value and gaps of a variable (spec §6.4)."""
    valued = sorted(
        day for day, value in station.values[name].items() if value is not None
    )
    gaps: list[list[str]] = []
    if valued:
        run: list[date] = []
        for day in _days(valued[0], valued[-1]):
            if day in station.known and station.values[name].get(day) is None:
                run.append(day)
                continue
            if run:
                gaps.append([run[0].isoformat(), run[-1].isoformat()])
                run = []
    return {
        "first": valued[0].isoformat() if valued else None,
        "last": valued[-1].isoformat() if valued else None,
        "with_value": len(valued),
        "accumulated": 0,
        "gaps": gaps,
    }


BY_HAND: dict[str, tuple[Callable[[Path, str], Station], tuple[str, ...]]] = {
    HYDRO: (hydro_by_hand, (S1, S2)),
    METEO: (meteo_by_hand, (FULL, RAIN)),
}


@pytest.mark.parametrize("dataset", [HYDRO, METEO])
def test_imgw_18_k1_coverage_and_gaps_equal_a_computation_by_hand(dataset, pl_cz):
    reader, codes = BY_HAND[dataset]
    stations = {code: reader(pl_cz, code) for code in codes}
    expected = [
        {"station_code": code, "variable": name, **coverage_by_hand(station, name)}
        for code, station in sorted(stations.items())
        for name in station.values
    ]
    keys = (
        "station_code",
        "variable",
        "first",
        "last",
        "with_value",
        "accumulated",
        "gaps",
    )

    summary = run_command("series summary", options={"root": pl_cz, "dataset": dataset})
    items = summary.to_json(root=pl_cz)["result"]["items"]
    index = load(version_of(pl_cz, f"series:{dataset}"))

    assert [{key: item[key] for key in keys} for item in items] == expected
    for row in expected:
        published = index["stations"][row["station_code"]]["variables"][row["variable"]]
        assert {key: published[key] for key in keys[2:]} == {
            key: row[key] for key in keys[2:]
        }


def _hydro_year(day: date) -> int:
    return day.year + 1 if day.month >= 11 else day.year


@pytest.mark.parametrize("year_type", ["hydrological", "calendar"])
def test_imgw_18_k1_exports_follow_the_stored_values_in_both_year_types(
    year_type, pl_cz
):
    station = hydro_by_hand(pl_cz, S2)
    lines = list(
        export_series(root=pl_cz, dataset=HYDRO, station=S2, year_type=year_type)
    )
    rows = list(csv.DictReader(io.StringIO("".join(lines))))

    # 2004 and 2006 are known; 2005 (unpublished) is a calendar of missing days.
    assert [row["date"] for row in rows] == [
        day.isoformat() for day in _days(date(2004, 1, 1), date(2006, 12, 31))
    ]
    for row in rows:
        day = date.fromisoformat(row["date"])
        assert int(row["year"]) == (
            _hydro_year(day) if year_type == "hydrological" else day.year
        )
        for name, unit in (("H", "cm"), ("Q", "m3/s"), ("T", "degC")):
            value = station.values[name].get(day)
            if value is None:
                assert (row[f"{name} [{unit}]"], row[f"{name}_flag"]) == ("", "missing")
            else:
                assert float(row[f"{name} [{unit}]"]) == value
                assert row[f"{name}_flag"] == "value"
    assert (rows[0]["attribution_source"], rows[0]["attribution_processed"]) == (
        SOURCE,
        PROCESSED,
    )

    meteo = meteo_by_hand(pl_cz, FULL)
    exported = list(
        csv.DictReader(
            io.StringIO(
                "".join(
                    export_series(
                        root=pl_cz, dataset=METEO, station=FULL, year_type=year_type
                    )
                )
            )
        )
    )
    for row in exported:
        day = date.fromisoformat(row["date"])
        assert int(row["year"]) == (
            _hydro_year(day) if year_type == "hydrological" else day.year
        )
        source = meteo.rows["P"].get(day)
        if source is None or not source["VALUE"]:
            assert row["P_flag"] == "missing"
            continue
        no_rain = float(source["VALUE"]) == 0.0 and not source["FLAG"]
        flag = "no_phenomenon" if no_rain else "value"
        assert (float(row["P [mm]"]), row["P_flag"]) == (float(source["VALUE"]), flag)
        assert row["P_source_flag"] == source["FLAG"]
        quality = source["QUALITY"]
        assert row["P_quality"] == (str(int(float(quality))) if quality else "")


def test_imgw_18_k2_every_station_of_a_chmi_dataset_is_in_its_series(pl_cz):
    hydro = read_series_index(version_of(pl_cz, f"series:{HYDRO}"))
    meteo = read_series_index(version_of(pl_cz, f"series:{METEO}"))

    assert set(hydro.stations) == {S1, S2}
    assert hydro.stations[S1].periods == ((date(2023, 1, 1), date(2024, 12, 31)),)
    # The unpublished 2005 is unknown, not a gap.
    assert hydro.stations[S2].periods == (
        (date(2004, 1, 1), date(2004, 12, 31)),
        (date(2006, 1, 1), date(2006, 12, 31)),
    )
    assert set(meteo.stations) == {FULL, RAIN}
    stored = {
        entry.meta.extra["period"]["station_code"]
        for entry in iter_store(pl_cz, kind="archive", provider="CHMI")
        if entry.meta is not None and entry.meta.dataset in (HYDRO, METEO)
    }
    assert stored == set(hydro.stations) | set(meteo.stations)


def test_imgw_18_k3_the_same_inputs_reuse_the_series(pl_cz, tmp_path, chmi, frozen):
    root = copy_of(pl_cz, tmp_path / "store")
    current = {
        dataset: version_of(root, f"series:{dataset}") for dataset in (HYDRO, METEO)
    }

    built = {dataset: build_series(root, dataset=dataset) for dataset in current}

    assert {
        dataset: (report.status, report.version) for dataset, report in built.items()
    } == {dataset: ("reused", version) for dataset, version in current.items()}
    # Scenario (2): the same bytes republished — relabeled inputs, the series reused.
    chmi.serve(
        "hydro_listing_republished",
        "h900001_2023_republished_head",
        "h900001_2023_republished_get",
    )
    report = sync_store(root, datasets=[HYDRO], stations=[S1], years=[2023])
    assert statuses(report.items) == ["relabeled"]
    assert [(series.status, series.version) for series in report.series] == [
        ("reused", current[HYDRO])
    ]
    assert snapshot(root / "series") == snapshot(pl_cz / "series")


# --------------------------------------------------------------------------
# IMGW-19 k1: Python = imgw = REST = MCP for the ČHMÚ commands
# --------------------------------------------------------------------------

# Versions of the read-only store, resolved before the run.
PLACEHOLDERS = {
    "<archive>": SLOT_2024,
    "<meteo>": f"archive:{METEO}:precipitation/dly-{FULL}-SRA.csv",
    "<series>": f"series:{HYDRO}",
}
# A plan file made by check_store on the fresh store before the run.
PLAN = "<plan>"
# Fresh stores of a write, one per interface: an initialized one, a copy of
# complete_pl_cz and one without the ČHMÚ meteo series.
FRESH = ("empty", "pl_cz", "unbuilt")


@dataclass(frozen=True)
class Run:
    """
    A ČHMÚ run of a catalog command: JSON options without ``root``.

    ``store``: ``None`` = no root; ``"served"`` = the read-only
    ``complete_pl_cz``; one of ``FRESH`` = a new store for every interface.
    ``cases``: recorded ČHMÚ answers; ``plan``: selectors of the plan file;
    ``statuses``: of the report items; ``status``: of the result itself.
    """

    command: str
    options: Mapping[str, object]
    store: str | None = None
    cases: tuple[str, ...] = ()
    plan: Mapping[str, object] | None = None
    statuses: tuple[str, ...] | None = None
    status: str | None = None


RUNS = [
    Run("datasets providers", {"limit": 5}),
    Run("datasets list", {"provider": "CHMI", "limit": 10}),
    Run(
        "datasets files",
        {"dataset": HYDRO, "stations": [S2, S1], "years": "2004-2006", "limit": 10},
    ),
    Run("datasets files", {"dataset": METEO, "stations": [RAIN], "limit": 10}),
    Run(
        "stations find",
        {"provider": "CHMI", "kind": "hydro", "query": "spindleruv", "limit": 5},
        cases=("hydro_now_get",),
    ),
    Run(
        "stations find",
        {"provider": "CHMI", "query": "Ves", "limit": 5},
        cases=("hydro_now_get", "meteo_now_listing", "meteo_now_get"),
    ),
    Run(
        "stations find",
        {"provider": "CHMI", "source": "store", "query": "0-203-1", "limit": 5},
        "served",
    ),
    # Both providers of the store: IMGW-PIB first, by family, name and code.
    Run("stations find", {"source": "store", "query": "a", "limit": 8}, "served"),
    Run("store info", {}, "served"),
    Run("store scan", {"provider": "CHMI", "limit": 25}, "served"),
    Run(
        "store scan", {"provider": "CHMI", "kind": "observation", "limit": 5}, "served"
    ),
    Run(
        "store check",
        {"datasets": [HYDRO], "stations": [S1, S2], "years": "2023-2024"},
        "served",
        ("hydro_listing_reserialized",),
    ),
    Run(
        "store check",
        {"datasets": [METEO], "stations": [FULL, RAIN]},
        "served",
        ("precipitation_listing", "temperature_listing"),
    ),
    # An unreadable listing: check_failed items, no exception (spec §15).
    Run(
        "store check",
        {"datasets": [HYDRO], "stations": [S1, ONLY_LISTED]},
        "served",
        ("hydro_listing_error",),
    ),
    Run(
        "store sync",
        {"datasets": [HYDRO], "stations": [S1], "years": [2023]},
        "pl_cz",
        (
            "hydro_listing_rewritten",
            "h900001_2023_rewritten_head",
            "h900001_2023_rewritten_get",
        ),
        statuses=("unchanged",),
    ),
    Run(
        "store sync",
        {"datasets": [METEO], "stations": [RAIN]},
        "empty",
        (
            "precipitation_listing",
            "temperature_listing",
            "m90000000002_SRA_head",
            "m90000000002_SRA_get",
        ),
        statuses=("created", "unchanged", "unchanged", "unchanged"),
    ),
    Run(
        "store sync",
        {"plan": PLAN},
        "empty",
        FIRST_900001,
        plan={"datasets": [HYDRO], "stations": [S1]},
        statuses=("created", "created"),
    ),
    Run(
        "store catalog",
        {"provider": "CHMI"},
        "pl_cz",
        CATALOG_HEADS,
        status="unchanged",
    ),
    Run("store catalog", {"provider": "CHMI"}, "empty", CATALOG_GETS, status="created"),
    Run("store export", {"version": "<archive>"}, "served"),
    Run("store export", {"version": "<meteo>", "format": "jsonl"}, "served"),
    Run("series build", {"dataset": HYDRO}, "pl_cz", status="reused"),
    Run("series build", {"dataset": METEO}, "unbuilt", status="created"),
    Run(
        "series select",
        {
            "dataset": HYDRO,
            "stations": [S2],
            "years": "2004,2006",  # 2005 is unknown: outside the series
            "year_type": "calendar",
        },
        "served",
    ),
    Run(
        "series read",
        {
            "dataset": HYDRO,
            "station": S2,
            "start": "2005-12-30",
            "end": "2006-01-02",
            "limit": 10,
        },
        "served",
    ),
    Run(
        "series read",
        {
            "dataset": METEO,
            "station": FULL,
            "variables": ["P", "Tmax"],
            "limit": 5,
            "offset": 5,
        },
        "served",
    ),
    Run("series summary", {"version": "<series>", "limit": 10}, "served"),
    Run(
        "series summary", {"dataset": METEO, "stations": [FULL], "limit": 10}, "served"
    ),
    Run("series export", {"dataset": METEO, "station": FULL}, "served"),
    Run(
        "series export",
        {
            "dataset": HYDRO,
            "station": S2,
            "year_type": "hydrological",
            "start": "2004-10-30",
            "end": "2004-11-02",
        },
        "served",
    ),
]
WRITE_RUNS = [run for run in RUNS if run.store in FRESH]


def fresh(kind: str, root: Path, pl_cz: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    if kind == "empty":
        init_store(root)
        return
    shutil.copytree(pl_cz, root)
    if kind == "unbuilt":
        shutil.rmtree(root / "series" / "versions" / "chmi_meteo_daily")


def resolved(run: Run, root: Path | None, plan: Path | None) -> dict[str, object]:
    """Options with placeholders replaced: versions relative to the root, the plan."""
    options = dict(run.options)
    for name, value in run.options.items():
        if value == PLAN:
            options[name] = str(plan)
        elif isinstance(value, str) and value in PLACEHOLDERS:
            assert root is not None
            options[name] = relative(root, version_of(root, PLACEHOLDERS[value]))
    return options


def rest_options(options: Mapping[str, object]) -> dict[str, object]:
    """REST takes the plan as an ``imgw-plan/1`` object with root ``"."``."""
    if "plan" not in options:
        return dict(options)
    document = load(Path(str(options["plan"])))
    return {**options, "plan": {**document, "root": "."}}


def mcp_answer(
    command: str, options: Mapping[str, object], *, check: bool = False
) -> Any:
    """The tool of ``command`` on a fresh stdio server (writes: ``check: false``)."""
    import anyio
    from mcp import Client

    from imgwtools.mcp.server import create_server

    meta = command_document(command)["x-imgw"]
    arguments = {
        name: str(value) if isinstance(value, Path) else value
        for name, value in options.items()
    }
    writes = meta["writes"] != "none" and not check
    if writes:
        arguments["check"] = False

    async def ask() -> Any:
        async with Client(
            create_server(mode="write" if writes else "read", lang="en")
        ) as client:
            return await client.call_tool(meta["operation_id"], arguments)

    return anyio.run(ask)


def assert_mcp_alike(
    answered: Any, command: str, options, python, printed, root
) -> None:
    """MCP structured content = the Python envelope, text = the CLI line."""
    assert answered.is_error is False, answered.content[0].text
    if ROUTES[command]["result"] == "stream" and not python.check:
        # The raw bytes: Click's ``stdout`` turns CRLF into LF.
        data = printed.stdout_bytes.decode("utf-8")
        default = command_document(command)["properties"]["format"]["default"]
        assert answered.content[0].text == data
        assert answered.structured_content == {
            "schema": "imgw-result/1",
            "command": command,
            "check": False,
            "status": python.status,
            "result": {
                "format": options.get("format", default),
                "bytes": len(data.encode("utf-8")),
                "lines": data.count("\n"),
            },
            "notices": replace(python, result=None).to_json(root=root)["notices"],
        }
        return
    assert canonical(answered.structured_content) == canonical(
        python.to_json(root=root)
    )
    assert answered.content[0].text + "\n" == printed.stdout


def _id(run: Run) -> str:
    return f"{run.command}:{','.join(f'{k}={v}' for k, v in run.options.items())}"[:90]


def _ask(interface, run, options, root, *, cli, rest, writable, check=False) -> Any:
    if interface == "mcp":
        return mcp_answer(run.command, rooted(options, root), check=check)
    given = rest_options(options) if interface == "rest" else options
    return answer(
        interface,
        run.command,
        given,
        root,
        cli=cli,
        rest=rest,
        headers=writable,
        check=check,
    )


@pytest.mark.parametrize("run", RUNS, ids=_id)
def test_imgw_19_k1_chmi_commands_answer_alike_in_python_cli_rest_and_mcp(
    run,
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    pl_cz,
    chmi,
    frozen,
    relative_reference_dir,  # noqa: F811
):
    writes = run.store in FRESH
    root = tmp_path / "store" if writes else (pl_cz if run.store == "served" else None)
    monkeypatch.setattr(server, "store_root", root)
    chmi.serve(*run.cases)
    plan = None
    if run.plan is not None:
        assert root is not None and run.store is not None
        fresh(run.store, root, pl_cz)
        plan = tmp_path / "plan.json"
        check_store(root, **run.plan, plan=plan)
    options = resolved(run, root, plan)
    before = stamps(pl_cz)
    answers, requests, trees = {}, {}, {}
    for interface in INTERFACES:
        if writes:
            fresh(str(run.store), root, pl_cz)
        start = len(chmi.router.calls)
        answers[interface] = _ask(
            interface, run, options, root, cli=cli, rest=rest, writable=writable
        )
        requests[interface] = chmi.traffic(start)
        if writes:
            trees[interface] = snapshot(root)

    python, printed = answers["python"], answers["cli"]
    stream = ROUTES[run.command]["result"] == "stream"
    if MCP:
        assert_mcp_alike(answers["mcp"], run.command, options, python, printed, root)
    assert_alike(run.command, python, printed, answers["rest"], root)
    assert len({canonical(traffic) for traffic in requests.values()}) == 1
    if run.cases and not stream:
        assert requests["python"], "żadne nagranie nie zostało użyte"
    if writes:
        assert len({canonical(tree) for tree in trees.values()}) == 1
    assert stamps(pl_cz) == before
    if run.statuses is not None:
        assert tuple(statuses(python.result.items)) == run.statuses
    if run.status is not None:
        assert python.result.status == run.status
    if root is not None and not stream:
        # Every slot paired with a version names a current_version (§13.7); an
        # unpublished ČHMÚ file is a result with version null.
        document = python.to_json(root=root)
        for slot in set(slots(document)) - set(unversioned(document)):
            entry = current_version(root, slot=slot)
            assert entry is not None and entry.slot == slot, slot


@pytest.mark.parametrize("run", WRITE_RUNS, ids=_id)
def test_imgw_19_k1_chmi_writes_are_planned_alike_without_writing(
    run, cli, rest, server, monkeypatch, tmp_path, pl_cz, chmi, frozen
):
    root = tmp_path / "store"
    assert run.store is not None
    fresh(run.store, root, pl_cz)
    monkeypatch.setattr(server, "store_root", root)  # writes stay disabled
    chmi.serve(*run.cases)
    plan = None
    if run.plan is not None:
        plan = tmp_path / "plan.json"
        check_store(root, **run.plan, plan=plan)
    options = resolved(run, root, plan)
    before = stamps(root)

    answers = {
        interface: _ask(
            interface, run, options, root, cli=cli, rest=rest, writable=None, check=True
        )
        for interface in INTERFACES
    }

    python = answers["python"]
    assert python.check is True
    if MCP:
        assert answers["mcp"].structured_content["check"] is True
        assert_mcp_alike(
            answers["mcp"], run.command, options, python, answers["cli"], root
        )
    assert_alike(run.command, python, answers["cli"], answers["rest"], root)
    assert stamps(root) == before
    downloads = [
        url
        for method, url in chmi.traffic()
        if method == "GET" and not url.endswith("/") and "metadata" not in url
    ]
    assert downloads == []


# ČHMÚ selections refused before any request: the option and value of the error.
REFUSED = [
    ("store check", {"datasets": [HYDRO], "years": "2024"}, "stations", None),
    (
        "store check",
        {"datasets": [HYDRO, DAILY], "stations": [S1], "years": "2024"},
        "stations",
        None,
    ),
    ("datasets files", {"dataset": HYDRO, "stations": [RABA]}, "stations", [RABA]),
    # Regression: the codes were the Python repr "['149190310']", not a list.
    ("series select", {"dataset": HYDRO, "stations": [RABA]}, "stations", [RABA]),
]


@pytest.mark.parametrize(("command", "options", "option", "value"), REFUSED)
def test_imgw_19_k1_a_refused_chmi_selection_is_one_validation_error_everywhere(
    command, options, option, value, cli, rest, server, monkeypatch, pl_cz, chmi
):
    root = pl_cz if "root" in command_document(command)["properties"] else None
    monkeypatch.setattr(server, "store_root", root)
    with pytest.raises(IMGWValidationError) as caught:
        run_command(command, options=rooted(options, root))
    error = caught.value
    expected = canonical([error.detail, dict(error.details)])

    printed = cli(*cli_words(command, rooted(options, root)))
    line = json.loads(printed.stderr.splitlines()[-1])
    answered = rest.request(
        **rest_request(command, options), headers={"Accept-Language": "en"}
    )
    body = answered.json()

    assert (error.details["option"], error.details.get("value")) == (option, value)
    assert (printed.exit_code, printed.stdout, line["code"]) == (
        2,
        "",
        "validation_error",
    )
    assert canonical([line["detail"], line["details"]]) == expected
    assert (answered.status_code, body["code"]) == (400, "validation_error")
    assert canonical([body["detail"], body["details"]]) == expected
    if MCP:
        document = mcp_answer(command, rooted(options, root)).structured_content
        assert canonical([document["detail"], document["details"]]) == expected
    assert chmi.traffic() == []


# --------------------------------------------------------------------------
# IMGW-19 k1 (local commands) and k2: projects with IMGW-PIB and ČHMÚ tasks
# --------------------------------------------------------------------------

TASKS = (
    ("raba", "series select", {"dataset": DAILY, "stations": [RABA], "years": [2024]}),
    (
        "zapadla",
        "series select",
        {
            "dataset": HYDRO,
            "stations": [S2],
            "years": "2004,2006",  # 2005 is unknown: outside the series
            "year_type": "calendar",
        },
    ),
    ("snezka", "store sync", {"datasets": [HYDRO], "stations": [S1], "years": [2023]}),
    (
        "srazky",
        "series select",
        {
            "dataset": METEO,
            "stations": [RAIN],
            "years": [2023],
            "year_type": "calendar",
        },
    ),
)
# The GETs that give back the pinned bytes under their pinned labels.
RESTORE = (
    "h900001_2023_get",
    "h900001_2024_corrected_get",
    "h900002_2004_republished_get",
    "h900002_2006_republished_get",
    "m90001_SRA_get",
    "m90001_T_get",
    "m90001_TMA_get",
    "m90001_TMI_get",
    "m90000000002_SRA_get",
)


def pinned_project(tmp_path: Path, pl_cz: Path, imgw, chmi: FakeChmi) -> Path:
    """A project of IMGW-PIB and ČHMÚ tasks pinned to a copy of complete_pl_cz."""
    copy_of(pl_cz, tmp_path / "store")
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    for name, command, options in TASKS:
        add_project_task(project, name=name, command=command, options=options)
    imgw.publish(H2024, V3, NEW)
    # Each listing matches the stored versions of its task: the republication of
    # 900002, the base meteo listings, then the observation of 900001 2023.
    chmi.serve(
        "hydro_listing_republished", "precipitation_listing", "temperature_listing"
    )
    first = download_project(project, tasks=["raba", "zapadla", "srazky"])
    chmi.serve("hydro_listing_reserialized")
    second = download_project(project, tasks=["snezka"])
    assert {**first.tasks, **second.tasks} == dict.fromkeys(
        ("raba", "zapadla", "srazky", "snezka"), "current"
    )
    return project


def test_imgw_19_k2_an_empty_store_restores_both_providers_with_identical_sha256(
    pl_cz, tmp_path, imgw, chmi, frozen
):
    project = pinned_project(tmp_path, pl_cz, imgw, chmi)
    manifest = (project / "imgw-project.json").read_bytes()
    assert schema_errors(json.loads(manifest), "imgw-project/1") == []
    pins = [pin for task in open_project(project).tasks for pin in task.files]
    chmi_pins = [pin for pin in pins if pin.content_form is not None]
    assert chmi_pins and {pin.content_form for pin in chmi_pins} == {"chmi-json/1"}
    store = tmp_path / "store"
    shutil.rmtree(store)
    chmi.serve(*RESTORE)
    start = len(chmi.router.calls)

    report = download_project(project)

    assert report.tasks == dict.fromkeys(
        ("raba", "zapadla", "snezka", "srazky"), "current"
    )
    # Every pinned file is created once; later tasks pinning it find it there.
    created = [result.slot for result in report.files if result.status == "created"]
    assert len(created) == len(set(created))
    assert {result.status for result in report.files} == {"created", "unchanged"}
    assert all(sha256(store / pin.path) == pin.sha256 for pin in pins)
    assert (project / "imgw-project.json").read_bytes() == manifest
    assert sorted(url for _, url in chmi.traffic(start) if "chmi" in url) == sorted(
        CHMI[case]["url"] for case in RESTORE
    )

    # Scenario (9): ČHMÚ serves other bytes of the same content for 900001 2023.
    shutil.rmtree(store)
    chmi.serve("h900001_2023_reserialized_get")
    notices = []
    again = download_project(project, on_notice=notices.append)

    assert again.tasks == {
        "raba": "current",
        "zapadla": "content_match",
        "snezka": "content_match",
        "srazky": "current",
    }
    by_content = {
        result.slot for result in again.files if result.status == "restored_by_content"
    }
    assert SLOT_2023 in by_content and f"series:{HYDRO}" in by_content
    assert [
        notice.level for notice in notices if notice.code == "pin_restored_by_content"
    ] == [
        "warning",
        "warning",
    ]
    assert (project / "imgw-project.json").read_bytes() == manifest
    status = run_command("project status", options={"project_dir": project})
    assert status.status == "ok"
    assert set(status.result.tasks.values()) == {"current", "content_match"}
    assert verify_project(project).tasks == again.tasks


@dataclass(frozen=True)
class Local:
    """A local ČHMÚ command: its options and the directory it may write."""

    options: dict[str, object]
    place: Path


def _datasets_download(tmp_path: Path, pl_cz: Path, imgw, chmi: FakeChmi) -> Local:
    chmi.serve("h900002_2004_get", "h900002_2005_get", "h900002_2006_get")
    output = tmp_path / "pobrane"
    options = {
        "dataset": HYDRO,
        "stations": [S2],
        "years": "2004-2006",
        "output": output,
    }
    return Local(options, output)


def _project_add(tmp_path: Path, pl_cz: Path, imgw, chmi: FakeChmi) -> Local:
    project = tmp_path / "projekt"
    init_project(project, store_dir="../magazyn")
    options = {
        "project_dir": project,
        "name": "srazky",
        "command": "series select",
        "options": {"dataset": METEO, "stations": [FULL], "years": [2023]},
    }
    return Local(options, project)


def _pinned(tmp_path: Path, pl_cz: Path, imgw, chmi: FakeChmi) -> Local:
    work = tmp_path / "praca"
    project = pinned_project(work, pl_cz, imgw, chmi)
    # project check reads the listings of the ČHMÚ tasks again.
    chmi.serve(
        "hydro_listing_reserialized", "precipitation_listing", "temperature_listing"
    )
    return Local({"project_dir": project}, work)


LOCAL = {
    "datasets download": _datasets_download,
    "project add": _project_add,
    "project status": _pinned,
    "project verify": _pinned,
    "project check": _pinned,
}


@pytest.mark.parametrize("command", list(LOCAL))
def test_imgw_19_k1_local_chmi_commands_answer_alike_in_python_cli_and_mcp(
    command, cli, tmp_path, pl_cz, imgw, chmi, frozen
):
    local = LOCAL[command](tmp_path, pl_cz, imgw, chmi)
    template = tmp_path / "wzorzec"
    if local.place.exists():
        shutil.copytree(local.place, template)
    answers, requests, trees = {}, {}, {}
    for interface in LOCAL_INTERFACES:
        if local.place.exists():
            shutil.rmtree(local.place)
        if template.exists():
            shutil.copytree(template, local.place)
        start = len(chmi.router.calls)
        if interface == "python":
            answers[interface] = run_command(command, options=local.options)
        elif interface == "cli":
            answers[interface] = cli(*cli_words(command, local.options))
        else:
            answers[interface] = mcp_answer(command, local.options)
        requests[interface] = chmi.traffic(start)
        trees[interface] = snapshot(local.place)

    python, printed = answers["python"], answers["cli"]
    document = python.to_json()
    assert python.status == "ok", document
    assert printed.exit_code == 0, printed.output
    assert canonical(json.loads(printed.stdout)) == canonical(document)
    for notice in python.notices:
        assert printed.stderr.count(f"{LABELS[notice.level]}: {notice.text}") == 1
    if MCP:
        answered = answers["mcp"]
        assert answered.is_error is False, answered.content[0].text
        assert canonical(answered.structured_content) == canonical(document)
    assert len({canonical(traffic) for traffic in requests.values()}) == 1
    assert len({canonical(tree) for tree in trees.values()}) == 1
    if command == "datasets download":
        assert statuses(python.result.items) == [
            "downloaded",
            "not_published",
            "downloaded",
        ]


# --------------------------------------------------------------------------
# IMGW-19 k3: CC BY 4.0 and the ČHMÚ attribution everywhere
# --------------------------------------------------------------------------


def test_imgw_19_k3_every_chmi_sidecar_and_export_names_cc_by_and_chmi(pl_cz):
    for sidecar, meta in sidecars(pl_cz).items():
        license_ = meta["license"]
        assert (meta["country"], meta["provider"]) == ("CZ", "CHMI"), sidecar
        assert (license_["id"], license_["url"], license_["terms_url"]) == (
            "CC-BY-4.0",
            CHMI_PROVIDER.license.url,
            CHMI_PROVIDER.license.terms_url,
        ), sidecar
        derived = meta["extra"].get("derived")
        expected = SOURCE if derived is None else f"{SOURCE}. {PROCESSED}"
        assert license_["attribution"] == expected, sidecar

    terms = f"{SOURCE}. {PROCESSED}. {CHMI_PROVIDER.notice}"
    exported = 0
    for entry in iter_store(pl_cz, kind="archive", provider="CHMI"):
        assert entry.meta is not None and entry.version is not None
        if entry.meta.dataset not in (HYDRO, METEO):
            continue  # station lists are read by stations find
        for format_ in ("csv", "jsonl"):
            notices = []
            lines = list(
                export_archive(entry.version, format=format_, on_notice=notices.append)
            )
            assert lines, entry.version
            assert [(n.level, n.code, n.text) for n in notices] == [
                ("info", "license_terms", terms)
            ]
            exported += 1
    assert exported == 2 * 12
    for dataset, codes in ((HYDRO, (S1, S2)), (METEO, (FULL, RAIN))):
        for code in codes:
            notices = []
            rows = list(
                csv.DictReader(
                    io.StringIO(
                        "".join(
                            export_series(
                                root=pl_cz,
                                dataset=dataset,
                                station=code,
                                on_notice=notices.append,
                            )
                        )
                    )
                )
            )
            assert (
                rows[0]["attribution_source"],
                rows[0]["attribution_processed"],
            ) == (
                SOURCE,
                PROCESSED,
            )
            assert {row["attribution_source"] for row in rows[1:]} <= {""}
            assert [notice.code for notice in notices] == ["license_terms"]
