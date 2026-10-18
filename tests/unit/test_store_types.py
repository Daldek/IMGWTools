"""Store type contracts and portable plan serialization."""

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from imgwtools.datasets import archive_files
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWError,
    IMGWPlanStaleError,
    IMGWProjectError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWStoreError,
)
from imgwtools.store.types import (
    CatalogReport,
    Meta,
    Notice,
    PlanItem,
    PMaXTPStoreResult,
    Progress,
    ProjectReport,
    SeriesReport,
    StoreEntry,
    StoreInfo,
    StorePlan,
    SyncReport,
    VersionResult,
)


@pytest.mark.parametrize(
    "error",
    [
        IMGWStoreError,
        IMGWStoreConflictError,
        IMGWStoreDependencyError,
        IMGWPlanStaleError,
        IMGWProjectError,
    ],
)
def test_store_errors_extend_imgw_error(error):
    assert issubclass(error, IMGWError)


def test_dependency_error_instructs_install():
    assert "pip install imgwtools[store]" in str(IMGWStoreDependencyError())


def test_frozen_contracts():
    objects = (
        Progress(1, 2, "plik", "trwa", "Czytanie"),
        Notice("warning", "missing", "Brak danych"),
        StoreInfo(Path("/tmp/store"), False, None, False, {}, ()),
        StoreEntry("problem", "archive:abc", None, None, "missing", "Brak"),
        VersionResult("created", Path("/tmp/zip"), "a" * 64, "2026-10-17"),
        SeriesReport("reused", None, 0, (), ()),
        SyncReport((), (), False),
        CatalogReport("unchanged", None, 0, 0, ()),
        PMaXTPStoreResult("unchanged", None, None, None, None),
        ProjectReport({}, (), False),
        Meta(
            "imgw-meta/1",
            "pl.imgw.hydro_daily",
            "a" * 64,
            1,
            datetime.now(UTC),
            None,
            {},
            {},
        ),
    )
    for value in objects:
        with pytest.raises(FrozenInstanceError):
            value.some_new_field = True


def _plan(tmp_path):
    (archive,) = archive_files("pl.imgw.hydro_daily", years=[2024])
    item = PlanItem(
        archive,
        "newer",
        Path("archives/versions/old.zip"),
        "a" * 64,
        '"new"',
        None,
        44,
        None,
    )
    return StorePlan(
        "imgw-plan/1",
        tmp_path,
        datetime(2026, 10, 17, tzinfo=UTC),
        (item,),
        {"hydro_daily": "outdated"},
        cancelled=True,
    )


def test_plan_roundtrip_cancelled_and_additive_fields(tmp_path):
    plan = _plan(tmp_path)
    archive = plan.items[0].archive
    path = plan.to_json(tmp_path / "plan.json")
    payload = json.loads(path.read_text())
    payload["future_field"] = "accepted"
    payload["items"][0]["future_field"] = "accepted"
    path.write_text(json.dumps(payload))
    loaded = StorePlan.from_json(path)
    assert loaded.cancelled is True
    assert loaded.items[0].archive.server_path == archive.server_path
    assert loaded.items[0].archive.period_start == archive.period_start
    assert loaded.items[0].archive.period_end == archive.period_end
    assert loaded.items[0].remote_etag == '"new"'
    assert loaded.series_state == {"hydro_daily": "outdated"}
    assert loaded.checked_at == plan.checked_at
    with pytest.raises(IMGWDataError, match="plan"):
        path.write_text('{"schema":"imgw-plan/2"}')
        StorePlan.from_json(path)


def test_plan_url_must_match_dataset_registry(tmp_path):
    plan = _plan(tmp_path)
    path = plan.to_json(tmp_path / "plan.json")
    assert StorePlan.from_json(path) == plan
    payload = json.loads(path.read_text())
    payload["items"][0]["url"] = "http://127.0.0.1:22/x"
    path.write_text(json.dumps(payload))
    with pytest.raises(IMGWDataError, match="nie odpowiada rejestrowi"):
        StorePlan.from_json(path)
