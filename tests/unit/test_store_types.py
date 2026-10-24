"""Store type contracts and portable plan serialization."""

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

from imgwtools.datasets import archive_files
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWError,
    IMGWProjectError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWStoreError,
)
from imgwtools.store.types import (
    CatalogReport,
    CommandOption,
    CommandResult,
    DataCommand,
    DownloadItem,
    DownloadReport,
    Meta,
    Notice,
    OperationResult,
    Page,
    PlanItem,
    PMaXTPStoreResult,
    Progress,
    Project,
    ProjectFile,
    ProjectReport,
    ProjectTask,
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
        CatalogReport("unchanged", None, 0, 0, 0, ()),
        Page((1, 2), 2, None, 0),
        DownloadItem(
            "archive:pl.imgw.hydro_daily:2023/codz_2023.zip",
            "https://example.invalid/codz_2023.zip",
            "downloaded",
            Path("/tmp/out/codz_2023.zip"),
            None,
            None,
        ),
        DownloadReport(Path("/tmp/out"), (), False),
        CommandResult("store info", False, "ok", None, ()),
        PMaXTPStoreResult("unchanged", None, None, None, None),
        ProjectReport({}, (), False),
        Meta(
            "imgw-meta/1",
            "pl.imgw.hydro_daily",
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
    with pytest.raises(IMGWDataError, match="does not match the dataset registry"):
        StorePlan.from_json(path)


class _Station(BaseModel):
    station_code: str
    measured_at: datetime


def test_to_json_relativizes_paths_below_root_only(tmp_path):
    root = tmp_path / "store"
    outside = tmp_path / "out" / "codz_2023.zip"
    result = DownloadReport(
        root,
        (
            DownloadItem(
                "archive:pl.imgw.hydro_daily:2023/codz_2023.zip",
                "https://example.invalid/codz_2023.zip",
                "downloaded",
                root / "archives" / "codz_2023.zip",
                None,
                None,
            ),
            DownloadItem(
                "archive:pl.imgw.hydro_daily:2024/codz_2024.zip",
                "https://example.invalid/codz_2024.zip",
                "failed",
                outside,
                f"Nie można zapisać {root}/archives/x.zip ani {root}2/y",
                "io_error",
            ),
        ),
        False,
    )
    notice = Notice("info", "license_terms", f"Magazyn {root}")
    envelope = CommandResult("archive download", False, "partial", result, (notice,))

    local = envelope.to_json(root=root)

    assert list(local) == ["schema", "command", "check", "status", "result", "notices"]
    assert local["schema"] == "imgw-result/1"
    assert local["result"] == {
        "output": str(root),
        "items": [
            {
                "slot": "archive:pl.imgw.hydro_daily:2023/codz_2023.zip",
                "url": "https://example.invalid/codz_2023.zip",
                "status": "downloaded",
                "path": "archives/codz_2023.zip",
                "error": None,
                "error_code": None,
            },
            {
                "slot": "archive:pl.imgw.hydro_daily:2024/codz_2024.zip",
                "url": "https://example.invalid/codz_2024.zip",
                "status": "failed",
                "path": str(outside),
                "error": f"Nie można zapisać {root}/archives/x.zip ani {root}2/y",
                "error_code": "io_error",
            },
        ],
        "cancelled": False,
    }
    assert local["notices"] == [
        {"level": "info", "code": "license_terms", "text": f"Magazyn {root}"}
    ]

    served = envelope.to_json(root=root, server=True)

    assert served["result"]["output"] == "."
    assert served["result"]["items"][0]["path"] == "archives/codz_2023.zip"
    assert served["result"]["items"][1]["error"] == (
        f"Nie można zapisać archives/x.zip ani {root}2/y"
    )
    assert served["notices"][0]["text"] == "Magazyn ."
    json.dumps(served)


def test_to_json_writes_project_pins_relative_to_the_store_in_any_working_directory(
    tmp_path, monkeypatch
):
    store = tmp_path / "magazyn"
    pin = Path(
        "series/versions/hydro_daily/2024-04-24_6aaf54cd/stations/150160180.parquet"
    )
    task = ProjectTask(
        "dobowe",
        "store sync",
        {"datasets": ["pl.imgw.hydro_daily"], "years": [2022]},
        None,
        datetime(2026, 10, 18, 20, 0, tzinfo=UTC),
        "3.0.0",
        (ProjectFile("station_series", pin, "0" * 64, "150160180"),),
    )
    project = Project(tmp_path / "projekt", store, (task,))
    envelope = CommandResult("project set-store", False, "ok", project, ())
    documents = []
    for directory in (tmp_path, store):
        directory.mkdir(exist_ok=True)
        monkeypatch.chdir(directory)
        documents.append(envelope.to_json())

    assert documents[0] == documents[1]
    result = documents[0]["result"]
    assert result["store_dir"] == str(store)
    assert result["tasks"][0]["files"][0]["path"] == pin.as_posix()


def test_to_json_writes_a_plan_as_its_imgw_plan_document(tmp_path):
    plan = _plan(tmp_path)
    envelope = CommandResult("store check", True, "ok", plan, ())
    saved = json.loads(plan.to_json(tmp_path / "plan.json").read_text())

    local = envelope.to_json(root=tmp_path)["result"]
    served = envelope.to_json(root=tmp_path, server=True)["result"]

    assert local == saved
    assert served == {**saved, "root": "."}
    (tmp_path / "result.json").write_text(json.dumps(local))
    assert StorePlan.from_json(tmp_path / "result.json") == plan


def test_to_json_server_mode_keeps_the_root_inside_urls_and_other_paths():
    text = (
        "Plik https://danepubliczne.imgw.pl/data/a.zip do /data/a.zip, nie /srv/data/b"
    )
    envelope = CommandResult("datasets files", False, "ok", text, ())

    served = envelope.to_json(root="/data", server=True)

    assert served["result"] == (
        "Plik https://danepubliczne.imgw.pl/data/a.zip do a.zip, nie /srv/data/b"
    )


def test_to_json_converts_dates_tuples_dataclasses_and_models(tmp_path):
    warsaw = timezone(timedelta(hours=2))
    result = Page(
        (
            _Station(
                station_code="150000001",
                measured_at=datetime(2026, 10, 17, 14, 30, tzinfo=warsaw),
            ),
            {"day": date(2026, 1, 5), "naive": datetime(2026, 1, 5, 6, 0)},
            ("a", ("b", 1)),
        ),
        total=7,
        limit=3,
        offset=0,
    )
    document = CommandResult("stations find", False, "ok", result, ()).to_json(
        root=tmp_path
    )

    assert document["result"] == {
        "items": [
            {"station_code": "150000001", "measured_at": "2026-10-17T12:30:00Z"},
            {"day": "2026-01-05", "naive": "2026-01-05T06:00:00Z"},
            ["a", ["b", 1]],
        ],
        "total": 7,
        "limit": 3,
        "offset": 0,
    }


def test_to_json_rejects_values_without_json_form():
    envelope = CommandResult("store info", False, "ok", object(), ())

    with pytest.raises(TypeError, match="JSON"):
        envelope.to_json()


def test_new_fields_have_defaults_and_catalog_constructs():
    operation = OperationResult("archive:x", "created", None, None)
    option = CommandOption("root", "path", True, "--root", (), "Katalog magazynu")
    command = DataCommand(
        "store info", "Opis", (option,), "store_info", None, "object", "GET"
    )

    assert (operation.task, operation.error_code) == (None, None)
    assert OperationResult(None, "failed", None, "Błąd").slot is None
    assert StoreEntry("problem", None, None, None, "missing", "Brak").slot is None
    assert (option.default, option.aliases, option.items, option.rest) == (
        None,
        (),
        None,
        "param",
    )
    assert (option.minimum, option.maximum, option.pattern) == (None, None, None)
    assert (command.requires, command.one_of, command.rules) == ({}, (), ())


def test_chmi_fields_default_so_3_0_constructors_keep_working():
    version = VersionResult("unchanged", Path("/s/a.json"), "a" * 64, "2026-05-21")
    (archive,) = archive_files("pl.imgw.hydro_daily", years=[2024])
    item = PlanItem(archive, "current", None, None, None, None, None, None)
    plan = StorePlan("imgw-plan/1", Path("/s"), datetime.now(UTC), (item,), {})

    assert (version.observed_sha256, version.observation) == (None, None)
    assert (item.station_code, item.signal, item.remote_listed_at) == (
        None,
        "head",
        None,
    )
    assert (item.local_observation, plan.requests) == (None, None)
    assert StoreInfo(Path("/s"), True, None, True, {}, ()).providers == ()
    assert StoreEntry("problem", None, None, None, "x", "Brak").provider is None
    assert CatalogReport("created", None, 0, 0, 0, ()).provider == "IMGW-PIB"


def _chmi_plan(tmp_path):
    (archive,) = archive_files(
        "cz.chmi.hydro_daily", stations=["0-203-1-900001"], years=[2025]
    )
    item = PlanItem(
        archive,
        "current",
        Path("archives/versions/hydrology/x.json"),
        "a" * 64,
        None,
        None,
        21647,
        None,
        station_code="0-203-1-900001",
        signal="listing",
        remote_listed_at="2026-05-21T11:19Z",
        local_observation=Path("archives/versions/hydrology/observations/o.json"),
    )
    return StorePlan(
        "imgw-plan/1",
        tmp_path,
        datetime(2026, 10, 19, tzinfo=UTC),
        (item,),
        {"chmi_hydro_daily": "current"},
        requests={"made": 1, "planned": 0},
    )


def test_plan_of_chmi_files_keeps_station_listing_signal_and_requests(tmp_path):
    plan = _chmi_plan(tmp_path)
    path = plan.to_json(tmp_path / "plan.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    (row,) = payload["items"]
    assert payload["requests"] == {"made": 1, "planned": 0}
    assert {
        key: row[key] for key in ("station_code", "signal", "remote_listed_at")
    } == {
        "station_code": "0-203-1-900001",
        "signal": "listing",
        "remote_listed_at": "2026-05-21T11:19Z",
    }
    assert row["local_observation"] == "archives/versions/hydrology/observations/o.json"
    loaded = StorePlan.from_json(path)
    assert loaded == plan
    assert loaded.items[0].archive.station_code == "0-203-1-900001"
    assert loaded.items[0].archive.period_end == date(2025, 12, 31)


def test_plan_without_the_chmi_fields_reads_with_defaults(tmp_path):
    plan = _plan(tmp_path)
    path = plan.to_json(tmp_path / "plan.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["requests"]
    for row in payload["items"]:
        for key in ("station_code", "signal", "remote_listed_at", "local_observation"):
            del row[key]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert StorePlan.from_json(path) == plan


@pytest.mark.parametrize(
    ("change", "text"),
    [
        (lambda d: d["items"][0].update(signal="ftp"), "Unknown signal"),
        (lambda d: d.update(requests={"made": -1}), "requests"),
        (
            lambda d: d["items"][0].update(station_code="0-203-1-900002"),
            "Unknown source path",
        ),
        (
            lambda d: d["items"][0].update(server_path="hydrology/x/y.json"),
            "Unknown source path",
        ),
    ],
)
def test_plan_with_invalid_chmi_fields_is_a_data_error(tmp_path, change, text):
    path = _chmi_plan(tmp_path).to_json(tmp_path / "plan.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    change(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(IMGWDataError, match=text):
        StorePlan.from_json(path)


def test_types_do_not_import_pyarrow():
    code = (
        "import sys, imgwtools._jsonable, imgwtools.store.types; "
        "sys.exit('pyarrow' in sys.modules)"
    )

    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
