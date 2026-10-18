"""Contract of ``imgw-project/1`` (spec §10.1, §11.6, IMGW-14).

The manifest follows its strict schema exactly as ``open_project`` does; every
project command of the catalog leaves a neighbouring Kartograf manifest and its
outputs untouched; status/verify/check/restore follow the pins; concurrent
``imgw project add`` processes merge different tasks and refuse a conflict.
"""

import copy
import json
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest

from imgwtools import (
    IMGWProjectError,
    __version__,
    add_project_task,
    check_project,
    download_project,
    get_project_status,
    init_project,
    open_project,
    run_command,
    verify_project,
)
from tests.contract.support import (
    BEZ_Q,
    DAILY,
    H2024,
    NEW,
    OLD,
    RABA,
    V3,
    load,
    schema_errors,
    sha256,
    snapshot,
    stamps,
)
from tests.contract.test_cli_api_parity import run_imgw

TASK = {"dataset": DAILY, "stations": [RABA], "years": [2024]}
MANIFEST = "imgw-project.json"


def pinned_project(tmp_path, fixture_root, imgw):
    """Project ``tmp/project`` with task ``raba`` pinned in a copy of the fixture store."""
    shutil.copytree(fixture_root, tmp_path / "store")
    project = tmp_path / "project"
    imgw.publish(H2024, V3, NEW)
    init_project(project, store_dir="../store")
    add_project_task(project, name="raba", command="series select", options=TASK)
    assert download_project(project).tasks == {"raba": "current"}
    return project


def test_manifest_follows_the_strict_schema_exactly_as_the_reader(
    tmp_path, fixture_root, imgw
):
    project = pinned_project(tmp_path, fixture_root, imgw)
    document = load(project / MANIFEST)
    assert schema_errors(document, "imgw-project/1") == []
    (task,) = document["tasks"]
    assert task["pinned_at"].endswith("Z") and task["imgwtools_version"] == __version__
    assert {pin["role"] for pin in task["files"]} == {
        "series",
        "station_series",
        "input",
    }
    assert all(
        sha256(tmp_path / "store" / pin["path"]) == pin["sha256"]
        for pin in task["files"]
    )

    violations = {
        "nowy klucz główny": lambda d: d.update(archiwista={"indeks": 1}),
        "nowy klucz zadania": lambda d: d["tasks"][0].update(priority=1),
        "nowy klucz pliku": lambda d: d["tasks"][0]["files"][0].update(size=1),
        "skrócona suma": lambda d: d["tasks"][0]["files"][0].update(sha256="abc"),
        "nieznana rola": lambda d: d["tasks"][0]["files"][0].update(role="raster"),
        "zła nazwa zadania": lambda d: d["tasks"][0].update(name="Raba Górna"),
        "zła stacja pliku": lambda d: d["tasks"][0]["files"][1].update(station="1491"),
        "obca wersja schematu": lambda d: d.update(schema="imgw-project/2"),
        "pusty magazyn": lambda d: d.update(store_dir=""),
    }
    for name, mutate in violations.items():
        changed = copy.deepcopy(document)
        mutate(changed)
        (project / MANIFEST).write_text(json.dumps(changed), encoding="utf-8")
        assert schema_errors(changed, "imgw-project/1"), name
        with pytest.raises(IMGWProjectError):
            open_project(project)

    extended = copy.deepcopy(document)
    extended["extensions"] = {"retman": {"profil": "dobowy"}}
    (project / MANIFEST).write_text(json.dumps(extended), encoding="utf-8")
    assert schema_errors(extended, "imgw-project/1") == []
    assert open_project(project).extensions == {"retman": {"profil": "dobowy"}}
    add_project_task(
        project,
        name="bez-q",
        command="series select",
        options={**TASK, "stations": [BEZ_Q]},
    )
    rewritten = load(project / MANIFEST)
    assert rewritten["extensions"] == {"retman": {"profil": "dobowy"}}
    assert [task["name"] for task in rewritten["tasks"]] == ["raba", "bez-q"]
    assert schema_errors(rewritten, "imgw-project/1") == []


def test_every_project_command_leaves_a_kartograf_project_beside_it_untouched(
    tmp_path, fixture_root, imgw
):
    shutil.copytree(fixture_root, tmp_path / "store")
    imgw.publish(H2024, V3, NEW)
    project = tmp_path / "project"
    outputs = project / "kartograf" / "versions" / "2026-10-01_0123abcd"
    outputs.mkdir(parents=True)
    (project / "kartograf-project.json").write_text(
        '{"schema":"kartograf-project/1","output_dir":"kartograf"}\n', encoding="utf-8"
    )
    (outputs / "dem.tif").write_bytes(b"II*\x00kartograf")
    (outputs / "dem.tif.meta.json").write_text(
        '{"schema":"kartograf-meta/1"}\n', encoding="utf-8"
    )
    kartograf = snapshot(project)
    moved = tmp_path / "archiwum" / "imgw"
    steps = [
        ("project init", {"store_dir": "../store"}),
        ("project add", {"name": "raba", "command": "series select", "options": TASK}),
        ("project check", {"plan": tmp_path / "plan.json"}),
        ("project download", {}),
        ("project status", {}),
        ("project verify", {}),
        ("project set-store", {"store_dir": moved}),
        ("project verify", {}),
        ("project remove", {"name": "raba"}),
    ]
    results = []
    for command, options in steps:
        if command == "project set-store":
            shutil.copytree(tmp_path / "store", moved)
        results.append(
            run_command(command, options={"project_dir": project, **options})
        )
        assert {
            path: digest
            for path, digest in snapshot(project).items()
            if path != MANIFEST
        } == kartograf, command
    assert [results[index].tasks for index in (3, 4, 5, 7)] == [{"raba": "current"}] * 4
    assert load(project / MANIFEST)["store_dir"] == str(moved)
    assert open_project(project).tasks == ()
    assert schema_errors(load(tmp_path / "plan.json"), "imgw-plan/1") == []


def test_status_verify_check_and_restore_follow_the_pins(tmp_path, fixture_root, imgw):
    project = pinned_project(tmp_path, fixture_root, imgw)
    store = tmp_path / "store"
    pins = {pin.role: pin for pin in open_project(project).tasks[0].files}
    manifest = (project / MANIFEST).read_bytes()

    untouched = stamps(tmp_path)
    plan = check_project(project)
    assert [(a.command, a.status) for a in plan.actions] == [
        ("project download", "current")
    ]
    assert plan.root == store and stamps(tmp_path) == untouched
    calls = len(imgw.router.calls)
    assert download_project(project).tasks == {"raba": "current"}
    assert len(imgw.router.calls) == calls and stamps(tmp_path) == untouched
    assert imgw.downloads() == []

    station = store / pins["station_series"].path
    original = station.read_bytes()
    station.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))  # same size
    assert get_project_status(project).tasks == {"raba": "current"}
    assert verify_project(project).tasks == {"raba": "changed"}
    station.write_bytes(original)
    archive = store / pins["input"].path
    shutil.rmtree(archive.parent)
    assert (
        get_project_status(project).tasks
        == verify_project(project).tasks
        == {"raba": "missing"}
    )

    imgw.publish(H2024, V3, OLD)  # IMGW serves other bytes under the pinned signal
    report = download_project(project)
    assert report.tasks == {"raba": "failed"} and not archive.exists()
    assert (project / MANIFEST).read_bytes() == manifest

    imgw.publish(H2024, V3, NEW)
    report = download_project(project)
    assert report.tasks == {"raba": "current"}
    assert sha256(archive) == pins["input"].sha256
    assert (project / MANIFEST).read_bytes() == manifest
    assert verify_project(project).tasks == {"raba": "current"}


def test_concurrent_imgw_processes_merge_tasks_and_refuse_a_conflict(
    tmp_path, fixture_root
):
    shutil.copytree(fixture_root, tmp_path / "store")
    project = tmp_path / "project"
    init_project(project, store_dir="../store")

    def add(name, stations):
        return run_imgw(
            "project", "add", "--project-dir", project, "--name", name,
            "--command", "series select",
            "--options", json.dumps({**TASK, "stations": stations}),
            check=False,
        )  # fmt: skip

    with ThreadPoolExecutor(4) as pool:
        added = list(pool.map(add, ["a", "b", "c", "d"], [[RABA]] * 4))
    assert [result.returncode for result in added] == [0, 0, 0, 0]
    assert sorted(task.name for task in open_project(project).tasks) == list("abcd")
    with ThreadPoolExecutor(2) as pool:
        rivals = list(pool.map(add, ["x", "x"], [[RABA], [BEZ_Q]]))
    assert sorted(result.returncode for result in rivals) == [0, 1]
    (loser,) = [result for result in rivals if result.returncode == 1]
    assert "Błąd: Zadanie 'x' już istnieje w projekcie" in loser.stderr
    winner = rivals.index(next(result for result in rivals if result.returncode == 0))
    (task,) = [task for task in open_project(project).tasks if task.name == "x"]
    assert list(task.options["stations"]) == [[RABA], [BEZ_Q]][winner]
    assert not (project / ".imgw-project.lock").exists()
