"""Offline scenarios for the cell-keyed PMAXTP store (recorded HTTP only)."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.store import init_store
from imgwtools.store.pmaxtp import check_pmaxtp, read_pmaxtp, sync_pmaxtp

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDINGS = {
    item["case"]: item
    for item in json.loads((FIXTURES / "recordings.json").read_text(encoding="utf-8"))["interactions"]
}
FIRST = RECORDINGS["pmaxtp_pot_first"]
SAME_CELL = RECORDINGS["pmaxtp_pot_same_cell"]
AMP = RECORDINGS["pmaxtp_amp"]


def recorded(router, entry, payload=None):
    return router.get(entry["url"]).mock(
        return_value=httpx.Response(entry["status"], json=entry["json"] if payload is None else payload)
    )


def tree(root: Path):
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in root.rglob("*")}


@pytest.fixture
def store(tmp_path):
    return init_store(tmp_path / "store")


def test_cell_key_comes_from_api_response(store):
    notices = []
    with respx.mock as router:
        route = recorded(router, FIRST)
        result = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01, on_notice=notices.append)
    assert route.call_count == 1
    assert (result.status, result.ind_x, result.ind_y) == ("created", 751, 317)
    relative = result.version.relative_to(store.root)
    assert relative.parts[:4] == ("pmaxtp", "versions", "POT", "751_317")
    raw = result.version.read_bytes()
    assert relative.parent.name.endswith("_" + hashlib.sha256(raw).hexdigest()[:8])
    cell = json.loads(raw)
    assert cell == {
        "schema": "imgw-pmaxtp/1", "method": "POT", "ind_x": 751, "ind_y": 317,
        "center": {"lon": 21.007098333333, "lat": 52.234416666667},
        "data": {"ks": {"15": {"50": 13.34}}, "sg": {"15": {"50": 14.1}}, "rb": {"15": {"50": 0.3}}},
    }
    meta = json.loads(result.version.with_name("cell.json.meta.json").read_text(encoding="utf-8"))
    assert meta["dataset"] == "pl.imgw.pmaxtp" and meta["sha256"] == hashlib.sha256(raw).hexdigest()
    assert meta["request"]["ind_x"] == 751 and meta["request"]["latitude"] == 52.23
    assert meta["extra"]["derived"] == "pmaxtp"
    assert meta["extra"]["version"]["label_source"] == "downloaded"
    assert "przetworzone" in meta["license"]["attribution"]
    assert result.result.data.get_precipitation(15, 50) == 13.34
    assert result.result.latitude == 52.23
    assert any(n.code == "license_terms" for n in notices)


def test_second_point_in_same_cell_reuses_version_and_amp_is_separate(store):
    with respx.mock as router:
        recorded(router, FIRST)
        recorded(router, SAME_CELL)
        recorded(router, AMP)
        first = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
        second = sync_pmaxtp(store, method="POT", latitude=52.2301, longitude=21.0101)
        amp = sync_pmaxtp(store, method="AMP", latitude=52.23, longitude=21.01)
    assert second.status == "unchanged" and second.version == first.version
    assert second.result.latitude == 52.2301
    assert len(list(first.version.parents[1].iterdir())) == 1
    assert amp.status == "created"
    assert amp.version.relative_to(store.root).parts[:4] == ("pmaxtp", "versions", "AMP", "751_317")
    assert amp.result.data.get_precipitation(15, 50) == 12.8


def test_mismatched_user_indices_and_empty_data_create_nothing(store):
    empty = {**FIRST["json"], "data": {}}
    no_index = {**FIRST["json"], "point": {k: v for k, v in FIRST["json"]["point"].items() if k != "indX"}}
    outside = RECORDINGS["pmaxtp_outside_grid"]
    with respx.mock as router:
        route = recorded(router, FIRST)
        recorded(router, outside)
        with pytest.raises(IMGWValidationError, match="751_317"):
            sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01, ind_x=750, ind_y=317)
        with pytest.raises(IMGWValidationError):
            sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01, ind_x=751)
        with pytest.raises(IMGWDataError, match="błąd"):
            sync_pmaxtp(store, method="POT", latitude=54.9, longitude=23.9)
        for payload in (empty, no_index):
            route.mock(return_value=httpx.Response(200, json=payload))
            with pytest.raises(IMGWDataError):
                sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
        assert not (store.root / "pmaxtp").exists()
        route.mock(return_value=httpx.Response(200, json=FIRST["json"]))
        matched = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01, ind_x=751, ind_y=317)
    assert matched.status == "created"


def test_check_pmaxtp_makes_no_request_and_writes_nothing(store):
    with respx.mock as router:  # unmocked requests raise
        before = tree(store.root)
        plan = check_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
        assert [a.status for a in plan.actions] == ["unverifiable"] and plan.items == ()
        plan = check_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01, ind_x=751, ind_y=317)
        assert plan.actions[0].status == "unverifiable" and "brak lokalnej wersji" in plan.actions[0].detail
        assert tree(store.root) == before
        route = recorded(router, FIRST)
        created = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
        after = tree(store.root)
        plan = check_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01, ind_x=751, ind_y=317)
        assert route.call_count == 1
    assert plan.actions[0].status == "unverifiable"
    assert created.version.relative_to(store.root).as_posix() in plan.actions[0].detail
    assert tree(store.root) == after
    with pytest.raises(IMGWValidationError):
        check_pmaxtp(store, method="XYZ", latitude=52.23, longitude=21.01)


def test_read_pmaxtp_offline_current_and_explicit_version(store):
    changed = {**FIRST["json"], "data": {"ks": {"15": {"50": 20.0}}, "sg": {"15": {"50": 21.0}}, "rb": {"15": {"50": 0.5}}}}
    with respx.mock as router:
        route = recorded(router, FIRST)
        old = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
        route.mock(return_value=httpx.Response(200, json=changed))
        new = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
    assert new.status == "created" and new.version != old.version
    with respx.mock:  # offline: any HTTP request would fail
        current = read_pmaxtp(store.root, method="POT", ind_x=751, ind_y=317)
        previous = read_pmaxtp(store, method="POT", ind_x=751, ind_y=317, version=old.version.parent.relative_to(store.root))
        assert current.data.get_precipitation(15, 50) == 20.0
        assert previous.data.get_precipitation(15, 50) == 13.34
        assert (current.latitude, current.longitude) == (52.234416666667, 21.007098333333)
        with pytest.raises(IMGWStoreError):
            read_pmaxtp(store, method="AMP", ind_x=751, ind_y=317)
        with pytest.raises(IMGWValidationError):
            read_pmaxtp(store, method="POT", ind_x=1, ind_y=2, version=old.version)
