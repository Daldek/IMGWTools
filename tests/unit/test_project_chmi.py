"""Projects with ČHMÚ tasks: content pins and restoring pins by content.

Spec 2026-10-18 §12 (ADR-003 D14) and the §13.2 scenarios (8) and (9): a
project mixing IMGW-PIB and ČHMÚ tasks, replayed from ``chmi_recordings.json``
(respx) and the IMGW-PIB server of ``test_project``. Synthetic files only;
codes 0-203-1-9… and 0-203-0-9… are not published by ČHMÚ.
"""

import json
import shutil

import pytest
import respx

from imgwtools import commands
from imgwtools.exceptions import IMGWStoreError, IMGWValidationError
from imgwtools.project import (
    PROJECT_FILE,
    add_project_task,
    check_project,
    download_project,
    get_project_status,
    init_project,
    open_project,
    verify_project,
)
from imgwtools.store import init_store, read_catalog, sync_store
from imgwtools.store.content import content_sha256
from imgwtools.testing import build_fixture_store
from tests.contract.support import schema_errors
from tests.unit.test_project import NEW, OLD, SELECT, V2, V3, Imgw, flip_last_byte, sha
from tests.unit.test_store_sync_chmi import (
    CASES,
    HYDRO,
    METEO,
    RAIN,
    S1,
    S2,
    payload,
    serve,
    traffic,
)

FORM = "chmi-json/1"
SNEZKA = {"dataset": HYDRO, "stations": [S1], "years": [2023, 2024]}
SRAZKY = {"datasets": [METEO], "stations": [RAIN]}
TASKS = (
    ("raba", "series select", SELECT),
    ("snezka", "series select", {**SNEZKA, "year_type": "calendar"}),
    ("srazky", "store sync", SRAZKY),
)
LISTINGS = ("hydro_listing", "precipitation_listing", "temperature_listing")
HEADS = ("h900001_2023_head", "h900001_2024_head", "m90000000002_SRA_head")
GETS = ("h900001_2023_get", "h900001_2024_get", "m90000000002_SRA_get")
SLOT_2023 = f"archive:{HYDRO}:H_0-203-1-900001_DQ_2023.json"
SLOT_2024 = f"archive:{HYDRO}:H_0-203-1-900001_DQ_2024.json"


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def imgw(server):
    return Imgw(server)


@pytest.fixture
def pinned(tmp_path, server, imgw):
    """Project ``tmp/project`` with pinned IMGW-PIB and ČHMÚ tasks; store ``tmp/store``."""
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    for name, command, options in TASKS:
        add_project_task(project, name=name, command=command, options=options)
    serve(server, *LISTINGS, *HEADS, *GETS)
    assert download_project(project).tasks == dict.fromkeys(
        ("raba", "snezka", "srazky"), "current"
    )
    return project


def chmi_traffic(router, start=0):
    return [
        (method, path)
        for method, path in traffic(router, start)
        if not path.startswith("http")
    ]


def task_of(project, name):
    return next(task for task in open_project(project).tasks if task.name == name)


def relative(store, result):
    return result.version.relative_to(store).as_posix()


def restore_by_content(project, server):
    """Scenario (9): the store is empty and ČHMÚ serves a re-serialized 900001 2023."""
    shutil.rmtree(project.parent / "store")
    serve(server, "h900001_2023_reserialized_get", "h900001_2024_get")
    notices = []
    report = download_project(project, tasks=["snezka"], on_notice=notices.append)
    return report, notices


def test_project_with_imgw_and_chmi_tasks_goes_from_init_to_verify(
    tmp_path, server, imgw
):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    init_store(tmp_path / "store")
    for name, command, options in TASKS:
        add_project_task(project, name=name, command=command, options=options)
    serve(server, *LISTINGS, *HEADS, *GETS)

    plan = check_project(project)
    assert [action.status for action in plan.actions] == ["missing"] * 3
    assert {
        (item.archive.dataset, item.station_code, item.status) for item in plan.items
    } >= {(HYDRO, S1, "missing"), (METEO, RAIN, "missing")}
    # ČHMÚ freshness comes from the listings alone: no HEAD and no GET of a file.
    assert chmi_traffic(server) == [
        ("GET", "hydrology/historical/data/daily/"),
        ("GET", "meteorology/climate/historical_csv/data/daily/precipitation/"),
        ("GET", "meteorology/climate/historical_csv/data/daily/temperature/"),
    ]

    report = download_project(project)
    assert report.tasks == {"raba": "current", "snezka": "current", "srazky": "current"}
    document = json.loads((project / PROJECT_FILE).read_text(encoding="utf-8"))
    assert schema_errors(document, "imgw-project/1") == []
    files = {task["name"]: task["files"] for task in document["tasks"]}
    inputs = [pin for pin in files["snezka"] if pin["role"] == "input"]
    assert [(pin["content_sha256"], pin["content_form"]) for pin in inputs] == [
        (content_sha256(payload(CASES[case]), form=FORM), FORM) for case in GETS[:2]
    ]
    # IMGW-PIB pins and ČHMÚ CSV pins keep the 3.0.0 keys only.
    for name in ("raba", "srazky"):
        assert files[name] and all(
            set(pin) <= {"role", "path", "sha256", "station_code"}
            for pin in files[name]
        )
    assert {pin["role"] for pin in files["srazky"]} == {
        "series",
        "station_series",
        "input",
    }
    assert (
        get_project_status(project).tasks
        == verify_project(project).tasks
        == {"raba": "current", "snezka": "current", "srazky": "current"}
    )


def test_empty_store_restores_both_providers_with_identical_sha256(
    pinned, server, tmp_path
):
    store = tmp_path / "store"
    before = (pinned / PROJECT_FILE).read_bytes()
    pins = [pin for task in open_project(pinned).tasks for pin in task.files]
    shutil.rmtree(store)
    start = len(server.calls)

    report = download_project(pinned)

    assert report.tasks == {"raba": "current", "snezka": "current", "srazky": "current"}
    assert {result.status for result in report.files} == {"new"}
    assert all(sha((store / pin.path).read_bytes()) == pin.sha256 for pin in pins)
    assert (pinned / PROJECT_FILE).read_bytes() == before
    assert sorted(chmi_traffic(server, start)) == sorted(
        ("GET", CASES[case]["path"]) for case in GETS
    )


def test_other_bytes_of_the_same_content_restore_pins_by_content(
    pinned, server, tmp_path
):
    store = tmp_path / "store"
    before = (pinned / PROJECT_FILE).read_bytes()
    pins = task_of(pinned, "snezka").files

    report, notices = restore_by_content(pinned, server)

    assert report.tasks == {"snezka": "content_match"}
    results = {result.slot: result for result in report.files}
    assert {slot: result.status for slot, result in results.items()} == {
        f"series:{HYDRO}": "restored_by_content",
        f"series:{HYDRO}:{S1}": "restored_by_content",
        SLOT_2023: "restored_by_content",
        SLOT_2024: "new",
    }
    reserialized = payload(CASES["h900001_2023_reserialized_get"])
    equivalent = results[SLOT_2023].version
    assert equivalent.read_bytes() == reserialized
    assert equivalent.parent.name == f"2026-10-19_{sha(reserialized)[:8]}"
    series, station, pinned_2023, _ = pins
    assert equivalent.parent.name != pinned_2023.path.parent.name
    # The series is rebuilt with the same bytes under the label of the new input.
    for slot, pin in ((f"series:{HYDRO}", series), (f"series:{HYDRO}:{S1}", station)):
        assert sha(results[slot].version.read_bytes()) == pin.sha256
        assert relative(store, results[slot]) != pin.path.as_posix()
    assert (pinned / PROJECT_FILE).read_bytes() == before

    (notice,) = [
        notice for notice in notices if notice.code == "pin_restored_by_content"
    ]
    assert notice.level == "warning"
    for pin in (series, station, pinned_2023):
        assert f"{pin.path.as_posix()} (SHA-256 {pin.sha256})" in notice.text
    assert f"{relative(store, results[SLOT_2023])} (SHA-256 {sha(reserialized)})" in (
        notice.text
    )
    assert f"shared content_sha256 {pinned_2023.content_sha256}" in notice.text

    seen = []
    status = get_project_status(pinned, tasks=["snezka"], on_notice=seen.append)
    assert status.tasks == {"snezka": "content_match"}
    assert [result.version for result in status.files] == [
        result.version for result in report.files
    ]
    envelope = commands.run_command(
        "project status", options={"project_dir": pinned, "tasks": ["snezka"]}
    )
    assert envelope.status == "ok"
    assert [(notice.level, notice.code) for notice in envelope.notices] == [
        ("warning", "pin_restored_by_content")
    ]
    assert verify_project(pinned, tasks=["snezka"]).tasks == {"snezka": "content_match"}

    start = len(server.calls)
    again = download_project(pinned, tasks=["snezka"])
    assert again.tasks == {"snezka": "content_match"} and len(server.calls) == start
    assert (pinned / PROJECT_FILE).read_bytes() == before

    serve(server, "hydro_listing_reserialized")
    upgraded = download_project(pinned, tasks=["snezka"], update="upgrade")
    assert upgraded.tasks == {"snezka": "upgraded"}
    task = task_of(pinned, "snezka")
    assert {pin.path.as_posix() for pin in task.files} == {
        relative(store, result) for result in report.files
    }
    assert verify_project(pinned, tasks=["snezka"]).tasks == {"snezka": "current"}


def test_verify_recomputes_the_sums_of_an_equivalent_version(pinned, server):
    report, _ = restore_by_content(pinned, server)
    equivalent = next(
        result.version for result in report.files if result.slot == SLOT_2023
    )
    flip_last_byte(equivalent)  # the same size: only hashing the bytes finds it

    assert get_project_status(pinned, tasks=["snezka"]).tasks == {
        "snezka": "content_match"
    }
    notices = []
    verified = verify_project(pinned, tasks=["snezka"], on_notice=notices.append)
    assert verified.tasks == {"snezka": "changed"}
    (failed,) = [result for result in verified.files if result.status == "failed"]
    assert (failed.slot, failed.error_code) == (SLOT_2023, "data_error")
    assert "does not confirm the content of the pin" in failed.error
    assert "pin_mismatch" in {notice.code for notice in notices}


def test_same_bytes_under_a_new_label_restore_by_content_only_with_a_form(
    pinned, server, imgw, tmp_path
):
    store = tmp_path / "store"
    shutil.rmtree(store)
    imgw.publish(V2, OLD)  # IMGW-PIB: the pinned bytes under a newer signal
    serve(server, "h900001_2023_republished_get", "h900001_2024_republished_get")

    report = download_project(pinned, tasks=["raba", "snezka"])

    assert report.tasks == {"raba": "failed", "snezka": "content_match"}
    chmi = [result for result in report.files if result.task == "snezka"]
    assert {result.status for result in chmi} == {"restored_by_content"}
    pins = {pin.path.parent.parent.name: pin for pin in task_of(pinned, "snezka").files}
    for result in chmi:
        # Version directory with the label of the republication.
        assert any(part.startswith("2026-02-06_") for part in result.version.parts)
    archives = [result for result in chmi if result.slot.startswith("archive:")]
    assert len(archives) == 2 and all(
        sha(result.version.read_bytes())
        == pins[result.version.parent.parent.name].sha256
        for result in archives
    )
    (archive,) = [
        result
        for result in report.files
        if result.task == "raba" and result.slot.startswith("archive:")
    ]
    assert (archive.status, archive.error_code) == ("failed", "not_found")
    assert archive.error.startswith("The identical bytes were written as")


def test_other_content_at_the_source_fails_naming_the_provider(
    pinned, server, imgw, tmp_path
):
    shutil.rmtree(tmp_path / "store")
    before = (pinned / PROJECT_FILE).read_bytes()
    imgw.publish(V3, NEW)
    serve(server, "h900001_2023_get", "h900001_2024_corrected_get")
    pinned_2024 = next(
        pin
        for pin in task_of(pinned, "snezka").files
        if pin.path.name == "H_0-203-1-900001_DQ_2024.json"
    )
    corrected = sha(payload(CASES["h900001_2024_corrected_get"]))

    notices = []
    report = download_project(
        pinned, tasks=["raba", "snezka"], on_notice=notices.append
    )

    assert report.tasks == {"raba": "failed", "snezka": "failed"}
    errors = {(result.task, result.slot): result for result in report.files}
    chmi = errors[("snezka", SLOT_2024)]
    assert (chmi.status, chmi.error_code) == ("failed", "not_found")
    assert chmi.error == (
        "ČHMÚ serves other content of hydrology/historical/data/daily/"
        f"H_0-203-1-900001_DQ_2024.json (SHA-256 {corrected}) than the pinned one "
        f"({pinned_2024.sha256}); the pins are unchanged, a deliberate re-pin: "
        'update="upgrade"'
    )
    assert errors[
        ("raba", "archive:pl.imgw.hydro_daily:2024/codz_2024.zip")
    ].error.startswith("IMGW-PIB serves other content of")
    assert "pin_restored_by_content" not in {notice.code for notice in notices}
    assert (pinned / PROJECT_FILE).read_bytes() == before
    assert get_project_status(pinned, tasks=["snezka"]).tasks == {"snezka": "missing"}


def test_observation_in_the_pinned_slot_keeps_pins_and_the_current_state(
    pinned, server, tmp_path
):
    store = tmp_path / "store"
    before = (pinned / PROJECT_FILE).read_bytes()
    serve(
        server,
        "hydro_listing_reserialized",
        "h900001_2023_reserialized_head",
        "h900001_2023_reserialized_get",
    )
    synced = sync_store(
        store, datasets=[HYDRO], stations=[S1], years=[2023], series=False
    )
    assert [item.status for item in synced.items] == ["unchanged"]
    assert len(list(store.rglob("observations/*.json"))) == 1

    assert get_project_status(pinned).tasks["snezka"] == "current"
    assert verify_project(pinned).tasks["snezka"] == "current"
    start = len(server.calls)
    plan = check_project(pinned, tasks=["snezka"])
    assert [action.status for action in plan.actions] == ["current"]
    assert [item.status for item in plan.items] == ["current", "current"]
    assert plan.items[0].local_observation is not None
    assert chmi_traffic(server, start) == [("GET", "hydrology/historical/data/daily/")]
    start = len(server.calls)
    assert download_project(pinned, tasks=["snezka"]).tasks == {"snezka": "current"}
    assert len(server.calls) == start
    assert (pinned / PROJECT_FILE).read_bytes() == before


def test_hydrological_years_of_a_chmi_selection_cover_the_previous_file(
    tmp_path, server
):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    init_store(tmp_path / "store")
    add_project_task(
        project,
        name="snezka",
        command="series select",
        options={**SNEZKA, "years": [2024], "year_type": "hydrological"},
    )
    serve(server, "hydro_listing")

    plan = check_project(project)

    # Hydrological 2024 = November 2023 - October 2024: both calendar files.
    assert [(item.archive.year, item.status) for item in plan.items] == [
        (2023, "missing"),
        (2024, "missing"),
    ]


def test_store_sync_task_pins_content_fields_of_chmi_hydro_files(tmp_path, server):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    add_project_task(
        project,
        name="sazava",
        command="store sync",
        options={"datasets": [HYDRO], "stations": [S2]},
    )
    serve(
        server,
        "hydro_listing",
        *(
            f"h900002_{year}_{method}"
            for year in (2004, 2006)
            for method in ("head", "get")
        ),
    )

    assert download_project(project).tasks == {"sazava": "current"}

    inputs = [pin for pin in task_of(project, "sazava").files if pin.role == "input"]
    assert [(pin.content_sha256, pin.content_form) for pin in inputs] == [
        (content_sha256(payload(CASES[f"h900002_{year}_get"]), form=FORM), FORM)
        for year in (2004, 2006)
    ]


@pytest.fixture(scope="module")
def pl_cz(tmp_path_factory):
    return build_fixture_store(
        tmp_path_factory.mktemp("project_chmi") / "store", variant="complete_pl_cz"
    ).root


def test_area_selection_reads_the_catalog_of_the_dataset_provider(tmp_path, pl_cz):
    store = tmp_path / "store"
    shutil.copytree(pl_cz, store)
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    lon, lat = next(
        feature.geometry
        for feature in read_catalog(root=store, provider="CHMI")
        if feature.station_code == S1 and feature.geometry is not None
    )
    ring = [
        [lon - 0.01, lat - 0.01],
        [lon + 0.01, lat - 0.01],
        [lon + 0.01, lat + 0.01],
        [lon - 0.01, lat + 0.01],
        [lon - 0.01, lat - 0.01],
    ]
    (project / "area.geojson").write_text(
        json.dumps({"type": "Polygon", "coordinates": [ring]}), encoding="utf-8"
    )
    options = {"dataset": HYDRO, "years": [2023], "year_type": "calendar"}

    (task,) = add_project_task(
        project,
        name="obszar",
        command="series select",
        options=options,
        geometry="area.geojson",
    ).tasks

    assert task.options["stations"] == [S1]
    (catalog,) = task.files
    assert catalog.path.parts[:3] == ("stations", "versions", "chmi_stations")
    status = get_project_status(project)
    assert status.tasks == {"obszar": "unpinned"}
    assert [(result.slot, result.status) for result in status.files] == [
        ("catalog:cz.chmi.stations", "unchanged")
    ]

    imgw_only = build_fixture_store(tmp_path / "imgw").root
    other = tmp_path / "other"
    init_project(other, store_dir=imgw_only)
    shutil.copy(project / "area.geojson", other / "area.geojson")
    with pytest.raises(IMGWStoreError, match="--provider CHMI") as error:
        add_project_task(
            other,
            name="obszar",
            command="series select",
            options=options,
            geometry="area.geojson",
        )
    assert error.value.code == "not_found"


@pytest.mark.parametrize(
    ("dataset", "code", "provider"),
    [(HYDRO, "149190310", "ČHMÚ"), ("pl.imgw.hydro_daily", S1, "IMGW-PIB")],
)
def test_selection_task_takes_only_codes_of_the_dataset_provider(
    tmp_path, dataset, code, provider
):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    with pytest.raises(IMGWValidationError, match=f"{provider} grammar") as error:
        add_project_task(
            project,
            name="zadanie",
            command="series select",
            options={"dataset": dataset, "stations": [code], "years": [2024]},
        )
    assert error.value.details["option"] == "options"
    assert open_project(project).tasks == ()
