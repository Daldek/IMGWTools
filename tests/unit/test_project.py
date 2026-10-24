"""Projekt imgw-project/1 (§10.1): ścisły manifest, blokada mkdir, scalanie per zadanie, piny."""

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools import project as project_module
from imgwtools._version import __version__
from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWProjectError, IMGWValidationError
from imgwtools.project import (
    LOCK_NAME,
    PROJECT_FILE,
    add_project_task,
    check_project,
    download_project,
    get_project_status,
    init_project,
    open_project,
    remove_project_task,
    set_project_store,
    verify_project,
)
from imgwtools.store import current_version, init_store
from imgwtools.store.types import Project, ProjectFile, StorePlan
from imgwtools.testing import build_fixture_store
from imgwtools.urls import IMGW_PUBLIC_DATA_URL
from tests.contract.support import schema_errors

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
DAILY = "pl.imgw.hydro_daily"
RABA, BEZ_Q = "149190310", "149190311"
H2024 = archive_files(DAILY, years=[2024])[0]
OLD = (FIXTURES / "archives" / H2024.server_path).read_bytes()
NEW = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()
V1 = {"ETag": '"hydro-v1"', "Last-Modified": "Sat, 17 Oct 2026 12:00:00 GMT"}
V2 = {"ETag": '"hydro-v2"', "Last-Modified": "Sun, 18 Oct 2026 12:00:00 GMT"}
V3 = {"ETag": '"hydro-v3"', "Last-Modified": "Mon, 19 Oct 2026 12:00:00 GMT"}
SELECT = {
    "dataset": DAILY,
    "stations": [RABA],
    "variables": ["H", "Q"],
    "years": [2024],
    "year_type": "hydrological",
}
# Obejmuje Rabę Górną (hydro, 20.1/49.7) i Warszawę (meteo, 21.01/52.23).
AREA = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[19.9, 49.5], [21.5, 49.5], [21.5, 52.5], [19.9, 52.5], [19.9, 49.5]],
        ],
    },
}
PIN = {
    "role": "input",
    "sha256": "0" * 64,
    "path": "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/2026-10-17_688646cd/codz_2024.zip",
}


class Imgw:
    """Serwer IMGW odpowiadający na listing, HEAD i GET ``codz_2024.zip``."""

    def __init__(self, mock):
        mock.get(f"{IMGW_PUBLIC_DATA_URL}/dane_hydrologiczne/dobowe/2024/").mock(
            return_value=httpx.Response(
                200, text='<a href="codz_2024.zip">codz_2024.zip</a>'
            )
        )
        self.head = mock.head(H2024.url)
        self.get = mock.get(H2024.url)
        self.publish(V1, OLD)

    def publish(self, headers, content):
        self.head.mock(
            return_value=httpx.Response(
                200, headers={**headers, "Content-Length": str(len(content))}
            )
        )
        self.get.mock(
            return_value=httpx.Response(200, headers=headers, content=content)
        )

    @property
    def calls(self):
        return self.head.call_count, self.get.call_count


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=False) as mock:
        yield Imgw(mock)


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("project") / "store").root


@pytest.fixture
def pinned(tmp_path, imgw):
    """Projekt ``tmp/project`` z przypiętym zadaniem ``raba``; magazyn ``tmp/store``."""
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    add_project_task(project, name="raba", command="series select", options=SELECT)
    assert download_project(project).tasks == {"raba": "current"}
    return project


def manifest(project):
    return json.loads((project / PROJECT_FILE).read_text(encoding="utf-8"))


def write(project, document):
    (project / PROJECT_FILE).write_text(json.dumps(document), encoding="utf-8")


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


def flip_last_byte(path):
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(bytes(data))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_init_writes_canonical_manifest_and_is_idempotent_for_the_same_store(
    tmp_path, fixture_root
):
    project = tmp_path / "project"
    created = init_project(project, store_dir="../store")

    assert (
        project / PROJECT_FILE
    ).read_bytes() == b'{"schema":"imgw-project/1","store_dir":"../store","tasks":[]}\n'
    assert (
        created == open_project(project) == Project(project, tmp_path / "store", (), {})
    )
    before = snapshot(project)
    assert init_project(project, store_dir=tmp_path / "store") == created
    assert snapshot(project) == before
    with pytest.raises(IMGWProjectError, match="set_project_store"):
        init_project(project, store_dir=fixture_root)

    absolute = init_project(tmp_path / "other", store_dir=fixture_root)
    assert absolute.store_dir == fixture_root and manifest(tmp_path / "other")[
        "store_dir"
    ] == str(fixture_root)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("x")
    with pytest.raises(IMGWProjectError, match="is not a supported IMGW store"):
        init_project(tmp_path / "third", store_dir=foreign)
    store = init_store(tmp_path / "own").root
    with pytest.raises(IMGWProjectError, match="must not lie in the store"):
        init_project(store / "project", store_dir=store)
    assert not (tmp_path / "third").exists() and not (store / "project").exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(note=1), "unknown keys 'note'"),
        (lambda d: d["tasks"][0].update(note=1), "tasks\\[0\\]: unknown keys 'note'"),
        (
            lambda d: d["tasks"][0]["files"][0].update(size=1),
            "files\\[0\\]: unknown keys 'size'",
        ),
        (lambda d: d.update(schema="imgw-project/2"), "imgw-project/2"),
        (lambda d: d.update(extensions=[]), "extensions"),
        (lambda d: d["tasks"][0].update(name="Raba"), "the task name"),
        (lambda d: d["tasks"][0].update(command="store init"), "store init"),
        (lambda d: d["tasks"][0]["options"].update(root="/x"), "root"),
        (lambda d: d["tasks"][0]["options"].update(stations=["12345"]), "9 cyfr"),
        (
            lambda d: d["tasks"][0]["options"].pop("year_type"),
            "explicit options: year_type",
        ),
        (
            lambda d: d["tasks"][0]["options"].update(geometry="../obszar.geojson"),
            r"'\.\.'",
        ),
        (
            lambda d: d["tasks"][0].update(
                geometry_sha256={"obszar.geojson": "0" * 64}
            ),
            "geometry_sha256",
        ),
        (
            lambda d: d["tasks"][0].update(pinned_at=None),
            "pinned_at and imgwtools_version",
        ),
        (
            lambda d: d["tasks"][0].update(pinned_at="2026-10-17T12:00:00"),
            "time zone",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(
                path="archives/versions/../../imgw-store.json"
            ),
            r"'\.\.'",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(path="/etc/passwd"),
            "relative POSIX path",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(path="imgw-store.json"),
            "versions",
        ),
        (lambda d: d["tasks"][0]["files"][0].update(sha256="ABC"), "SHA-256"),
        (
            lambda d: d["tasks"][0]["files"][0].update(role="station_series"),
            "station_code",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(station=RABA),
            "unknown keys 'station'",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(
                path=PIN["path"].replace("codz_2024/", "codz_2023/")
            ),
            "with a slot of",
        ),
        (lambda d: d["tasks"][0]["files"].append(dict(PIN)), "a repeated path"),
        (
            lambda d: d["tasks"][0]["files"][0].update(content_sha256="1" * 64),
            "together or not at all",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(content_form="chmi-json/1"),
            "together or not at all",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(
                content_sha256="1" * 63, content_form="chmi-json/1"
            ),
            r"files\[0\]\.content_sha256",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(
                content_sha256="1" * 64, content_form=""
            ),
            r"files\[0\]\.content_form",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(station_code="0-203-1-cb900003"),
            "WIGOS",
        ),
        (
            lambda d: d["tasks"][0]["files"][0].update(station_code="12345678"),
            "WIGOS",
        ),
        (lambda d: d["tasks"].append(dict(d["tasks"][0])), "a repeated task name"),
    ],
)
def test_open_project_rejects_unknown_keys_bad_values_and_unsafe_paths(
    tmp_path, mutate, message
):
    project = tmp_path / "project"
    project.mkdir()
    task = {
        "name": "raba",
        "command": "series select",
        "options": dict(SELECT),
        "pinned_at": "2026-10-17T12:00:00Z",
        "imgwtools_version": "3.0.0",
        "files": [dict(PIN)],
    }
    document = {"schema": "imgw-project/1", "store_dir": "../store", "tasks": [task]}
    write(project, document)
    assert open_project(project).tasks[0].pinned_at == datetime(
        2026, 10, 17, 12, tzinfo=UTC
    )

    mutate(document)
    write(project, document)
    with pytest.raises(IMGWProjectError, match=message):
        open_project(project)


def test_open_project_rejects_duplicate_json_keys_and_non_finite_numbers(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / PROJECT_FILE).write_text(
        '{"schema":"imgw-project/1","store_dir":"s","store_dir":"t","tasks":[]}'
    )
    with pytest.raises(IMGWProjectError, match="a repeated key"):
        open_project(project)
    (project / PROJECT_FILE).write_text(
        '{"schema":"imgw-project/1","store_dir":"s","tasks":[],"extensions":{"x":NaN}}'
    )
    with pytest.raises(IMGWProjectError, match="NaN"):
        open_project(project)


def test_wigos_station_pins_and_content_fields_survive_a_manifest_rewrite(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    content_pin = {**PIN, "content_sha256": "1" * 64, "content_form": "chmi-json/1"}
    station_pin = {
        "role": "station_series",
        "path": "series/versions/hydro_daily/2026-10-17_00000000/stations/"
        "0-203-1-CB900003.parquet",
        "sha256": "0" * 64,
        "station_code": "0-203-1-CB900003",
    }
    task = {
        "name": "raba",
        "command": "series select",
        "options": dict(SELECT),
        "pinned_at": "2026-10-17T12:00:00Z",
        "imgwtools_version": "3.0.0",
        "files": [content_pin, station_pin],
    }
    write(
        project, {"schema": "imgw-project/1", "store_dir": "../store", "tasks": [task]}
    )
    assert schema_errors(manifest(project), "imgw-project/1") == []

    (opened,) = open_project(project).tasks
    assert [
        (pin.station_code, pin.content_sha256, pin.content_form) for pin in opened.files
    ] == [(None, "1" * 64, "chmi-json/1"), ("0-203-1-CB900003", None, None)]
    add_project_task(project, name="druga", command="series select", options=SELECT)
    assert manifest(project)["tasks"][0]["files"] == [content_pin, station_pin]
    assert open_project(project).tasks[0] == opened

    for pin in ({**PIN, "content_sha256": "1" * 64}, {**PIN, "content_form": "x"}):
        assert schema_errors(
            {
                "schema": "imgw-project/1",
                "store_dir": "s",
                "tasks": [{**task, "files": [pin]}],
            },
            "imgw-project/1",
        )
        write(
            project,
            {
                "schema": "imgw-project/1",
                "store_dir": "../store",
                "tasks": [{**task, "files": [pin]}],
            },
        )
        with pytest.raises(IMGWProjectError) as error:
            open_project(project)
        assert error.value.code == "validation_error"


def test_symlinks_in_pinned_and_project_paths_are_rejected(tmp_path, fixture_root):
    store = tmp_path / "store"
    shutil.copytree(fixture_root, store)
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    (store / "archives" / "versions" / "link").symlink_to(
        store / "archives" / "versions" / "dane_hydrologiczne"
    )
    document = manifest(project)
    document["tasks"] = [
        {
            "name": "raba",
            "command": "series select",
            "options": SELECT,
            "pinned_at": None,
            "imgwtools_version": None,
            "files": [
                {**PIN, "path": PIN["path"].replace("dane_hydrologiczne", "link")}
            ],
        }
    ]
    write(project, document)
    with pytest.raises(IMGWProjectError, match="A symbolic link"):
        open_project(project)

    document["tasks"] = []
    write(project, document)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "obszar.geojson").write_text(json.dumps(AREA))
    (project / "obszary").symlink_to(elsewhere)
    options = {"dataset": DAILY, "years": [2024]}
    for geometry, message in [
        ("obszary/obszar.geojson", "A symbolic link"),
        (elsewhere / "obszar.geojson", "must lie in the directory"),
        ("../elsewhere/obszar.geojson", r"'\.\.'"),
    ]:
        with pytest.raises(IMGWValidationError, match=message):
            add_project_task(
                project,
                name="obszar",
                command="series select",
                options=options,
                geometry=geometry,
            )
    assert open_project(project).tasks == ()


def test_add_materializes_explicit_options_and_writes_keep_extensions(
    tmp_path, fixture_root
):
    project = tmp_path / "project"
    init_project(project, store_dir=fixture_root)
    document = manifest(project)
    document["extensions"] = {"hydrograf": {"warstwa": "raba"}}
    write(project, document)

    added = add_project_task(
        project,
        name="raba",
        command="series select",
        options={"dataset": DAILY, "stations": RABA, "years": "2023-2024"},
    )
    (task,) = added.tasks
    assert task.options == {
        "dataset": DAILY,
        "stations": [RABA],
        "variables": ["H", "Q", "T"],
        "years": [2023, 2024],
        "year_type": "hydrological",
    }
    assert (
        task.pinned_at,
        task.imgwtools_version,
        task.geometry_sha256,
        task.files,
    ) == (None, None, None, ())
    add_project_task(project, name="info", command="store info", options={})
    assert manifest(project)["extensions"] == {"hydrograf": {"warstwa": "raba"}}

    before = (project / PROJECT_FILE).read_bytes()
    with pytest.raises(IMGWProjectError, match="already exists"):
        add_project_task(project, name="raba", command="store info", options={})
    for name, command, options in [
        ("bez-lat", "series select", {"dataset": DAILY, "stations": RABA}),
        ("Zla", "store info", {}),
        ("proj", "project init", {}),
        (
            "zly-kod",
            "series select",
            {"dataset": DAILY, "stations": "123", "years": 2024},
        ),
        ("z-root", "store info", {"root": "/x"}),
    ]:
        with pytest.raises(IMGWValidationError):
            add_project_task(project, name=name, command=command, options=options)
    assert (project / PROJECT_FILE).read_bytes() == before

    assert [task.name for task in remove_project_task(project, name="raba").tasks] == [
        "info"
    ]
    with pytest.raises(IMGWProjectError, match="No task"):
        remove_project_task(project, name="raba")
    assert open_project(project).extensions == {"hydrograf": {"warstwa": "raba"}}


def test_area_selection_hashes_geometry_and_stores_an_explicit_station_list(
    tmp_path, fixture_root
):
    project = tmp_path / "project"
    init_project(project, store_dir=fixture_root)
    area = project / "obszary" / "raba.geojson"
    area.parent.mkdir()
    area.write_text(json.dumps(AREA))

    # Bez położenia (BEZ_Q) stację wybiera się po kodzie; Warszawa (meteo) nie należy do zbioru hydro.
    added = add_project_task(
        project,
        name="raba",
        command="series select",
        options={"dataset": DAILY, "stations": [BEZ_Q], "years": [2024]},
        geometry=area,
    )
    (task,) = added.tasks
    catalog = current_version(fixture_root, slot="catalog:pl.imgw.stations")
    assert task.options["stations"] == [RABA, BEZ_Q]
    assert task.options["geometry"] == "obszary/raba.geojson"
    assert task.geometry_sha256 == {"obszary/raba.geojson": sha(area.read_bytes())}
    assert task.files == (
        ProjectFile(
            "catalog", catalog.version.relative_to(fixture_root), catalog.meta.sha256
        ),
    )
    assert get_project_status(project).tasks == {"raba": "unpinned"}

    (project / "obszar.geojson").write_text(json.dumps(AREA))
    area.write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[15, 52], [15.1, 52], [15.1, 52.1], [15, 52]]],
            }
        )
    )
    assert open_project(project).tasks == added.tasks  # wybór zmaterializowany raz
    meteo = add_project_task(
        project,
        name="opad",
        command="series select",
        options={"dataset": "pl.imgw.meteo_precip_daily", "years": [2001]},
        geometry="obszar.geojson",
    )
    assert meteo.tasks[-1].options["stations"] == ["123750000"]
    with pytest.raises(IMGWValidationError, match="covered no station"):
        add_project_task(
            project,
            name="pusty",
            command="series select",
            options={"dataset": DAILY, "years": [2024]},
            geometry=area,
        )
    (project / "zly.geojson").write_text('{"type": "Point", "coordinates": [20, 50]}')
    with pytest.raises(IMGWValidationError, match="Polygon"):
        add_project_task(
            project,
            name="punkt",
            command="series select",
            options={"dataset": DAILY, "years": [2024]},
            geometry="zly.geojson",
        )
    with pytest.raises(IMGWValidationError, match="series select"):
        add_project_task(
            project,
            name="info",
            command="store info",
            options={},
            geometry="zly.geojson",
        )


def test_download_pins_selection_and_status_verify_detect_changes(pinned):
    store = pinned.parent / "store"
    (task,) = open_project(pinned).tasks
    series, station, archive = task.files

    assert task.pinned_at is not None and task.imgwtools_version == __version__
    assert [pin.role for pin in task.files] == ["series", "station_series", "input"]
    assert station.station_code == RABA
    assert station.path.parent.parent == series.path.parent
    assert archive.sha256 == sha(OLD) and archive.path.parts[:2] == (
        "archives",
        "versions",
    )
    assert all(sha((store / pin.path).read_bytes()) == pin.sha256 for pin in task.files)
    assert (
        get_project_status(pinned).tasks
        == verify_project(pinned).tasks
        == {"raba": "current"}
    )
    report = verify_project(pinned)
    assert [(result.slot, result.task) for result in report.files] == [
        (f"series:{DAILY}", "raba"),
        (f"series:{DAILY}:{RABA}", "raba"),
        (f"archive:{DAILY}:2024/codz_2024.zip", "raba"),
    ]
    for result in (report.files[0], report.files[2]):
        entry = current_version(store, slot=result.slot)
        assert entry is not None and entry.version == result.version

    flip_last_byte(store / station.path)  # ten sam rozmiar: tylko pełne SHA to wykrywa
    assert get_project_status(pinned).tasks == {"raba": "current"}
    notices = []
    report = verify_project(pinned, on_notice=notices.append)
    assert report.tasks == {"raba": "changed"} and [
        notice.code for notice in notices
    ] == ["pin_mismatch"]
    assert [(result.status, result.error_code) for result in report.files] == [
        ("unchanged", None),
        ("failed", "data_error"),
        ("unchanged", None),
    ]
    (store / series.path).unlink()
    status = get_project_status(pinned)
    assert status.tasks == {"raba": "missing"}
    assert (status.files[0].slot, status.files[0].error_code) == (
        f"series:{DAILY}",
        "not_found",
    )


def test_check_writes_nothing_and_only_upgrade_changes_pins(pinned, imgw):
    store = pinned.parent / "store"
    pins = open_project(pinned).tasks[0].files
    imgw.publish(V3, NEW)
    before, gets = snapshot(pinned.parent), imgw.get.call_count

    plan = check_project(pinned)
    assert plan.schema == "imgw-plan/1" and plan.root == store
    assert [(action.command, action.status) for action in plan.actions] == [
        ("project download", "newer")
    ]
    assert [(item.archive.server_path, item.status) for item in plan.items] == [
        (H2024.server_path, "newer")
    ]
    assert snapshot(pinned.parent) == before and imgw.get.call_count == gets

    calls = imgw.calls
    assert download_project(pinned).tasks == {"raba": "current"}
    assert imgw.calls == calls and snapshot(pinned.parent) == before

    report = download_project(pinned, update="upgrade", plan=plan)
    assert report.tasks == {"raba": "upgraded"}
    (task,) = open_project(pinned).tasks
    assert {pin.role for pin in task.files} == {"series", "station_series", "input"}
    assert next(pin for pin in task.files if pin.role == "input").sha256 == sha(NEW)
    assert not set(task.files) & set(pins) and all(
        (store / pin.path).is_file() for pin in pins
    )
    assert verify_project(pinned).tasks == {"raba": "current"}


def test_upgrade_with_a_stale_plan_fails_and_keeps_pins(pinned, imgw, tmp_path):
    imgw.publish(V3, NEW)
    plan_file = check_project(pinned).to_json(tmp_path / "plan.json")
    imgw.publish(V2, OLD)  # serwer zmienił się po sprawdzeniu
    before = (pinned / PROJECT_FILE).read_bytes()

    report = download_project(pinned, update="upgrade", plan=plan_file)
    assert report.tasks == {"raba": "failed"}
    ((stale),) = report.files
    assert (stale.slot, stale.status, stale.task, stale.error_code) == (
        f"archive:{DAILY}:2024/codz_2024.zip",
        "stale_plan",
        "raba",
        None,
    )
    assert (pinned / PROJECT_FILE).read_bytes() == before
    foreign = StorePlan("imgw-plan/1", tmp_path / "inny", datetime.now(UTC), (), {})
    with pytest.raises(IMGWValidationError, match="another store") as error:
        download_project(pinned, plan=foreign)
    assert error.value.details["option"] == "plan"
    with pytest.raises(IMGWProjectError, match="Unknown project tasks") as error:
        download_project(pinned, tasks=["brak"])
    assert (error.value.code, error.value.details) == (
        "not_found",
        {"option": "tasks", "value": ["brak"]},
    )


def test_restore_recreates_only_identical_bytes_and_never_repins(pinned, imgw):
    store = pinned.parent / "store"
    before = (pinned / PROJECT_FILE).read_bytes()
    shutil.rmtree(store)

    report = download_project(pinned)
    assert report.tasks == {"raba": "current"} and {
        result.status for result in report.files
    } == {"created"}
    assert (pinned / PROJECT_FILE).read_bytes() == before
    assert verify_project(pinned).tasks == {"raba": "current"}

    shutil.rmtree(store)
    imgw.publish(V3, NEW)  # IMGW nie ma już przypiętych bajtów
    notices = []
    report = download_project(pinned, on_notice=notices.append)
    assert report.tasks == {"raba": "failed"}
    errors = {
        result.slot.split(":")[0]: (result.error, result.error_code)
        for result in report.files
    }
    assert "inną treść" in errors["archive"][0] and errors["archive"][1] == "not_found"
    assert "przypiętych wejść" in errors["series"][0]
    assert errors["series"][1] == "not_found"
    assert {result.status for result in report.files} == {
        "failed"
    } and "task_failed" in {n.code for n in notices}
    assert (pinned / PROJECT_FILE).read_bytes() == before
    assert get_project_status(pinned).tasks == {"raba": "missing"}


def test_set_store_moves_to_a_verified_copy_and_refuses_other_stores(pinned, tmp_path):
    pins = open_project(pinned).tasks
    moved = tmp_path / "archiwum" / "imgw"
    shutil.copytree(tmp_path / "store", moved)

    project = set_project_store(pinned, store_dir="../archiwum/imgw")
    assert (
        project.store_dir == moved
        and manifest(pinned)["store_dir"] == "../archiwum/imgw"
    )
    assert project.tasks == pins and get_project_status(pinned).tasks == {
        "raba": "current"
    }

    before = (pinned / PROJECT_FILE).read_bytes()
    tampered = tmp_path / "tampered"
    shutil.copytree(moved, tampered)
    flip_last_byte(tampered / pins[0].files[1].path)
    partial = tmp_path / "partial"
    shutil.copytree(moved, partial)
    (partial / pins[0].files[1].path).unlink()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "x.txt").write_text("x")
    for store, message in [
        (partial, "brak przypiętego pliku"),
        (tampered, "SHA-256"),
        (foreign, "is not a supported IMGW store"),
    ]:
        with pytest.raises(IMGWProjectError, match=message):
            set_project_store(pinned, store_dir=store)
    assert (pinned / PROJECT_FILE).read_bytes() == before


@pytest.mark.parametrize("prepare", ["missing", "empty_dir", "initialised"])
def test_set_store_to_new_empty_store_then_download_restores_identical_pins(
    pinned, tmp_path, imgw, prepare
):
    old_store = tmp_path / "store"
    pins = open_project(pinned).tasks[0].files
    new_store = tmp_path / "nowy"
    if prepare == "empty_dir":
        new_store.mkdir()
    elif prepare == "initialised":
        init_store(new_store)
    notices = []

    project = set_project_store(pinned, store_dir="../nowy", on_notice=notices.append)

    assert project.store_dir == new_store and project.tasks[0].files == pins
    assert manifest(pinned)["store_dir"] == "../nowy"
    ((notice),) = notices
    assert (notice.level, notice.code) == ("warning", "pins_not_in_store")
    assert f"brak {len(pins)} przypiętych plików" in notice.text
    assert get_project_status(pinned).tasks == {"raba": "missing"}

    report = download_project(pinned)

    assert report.tasks == {"raba": "current"}
    assert {result.status for result in report.files} == {"created"}
    assert open_project(pinned).tasks[0].files == pins
    for pin in pins:
        restored = (new_store / pin.path).read_bytes()
        assert sha(restored) == pin.sha256
        assert restored == (old_store / pin.path).read_bytes()
    assert verify_project(pinned).tasks == {"raba": "current"}


def test_restore_into_empty_store_fails_explicitly_when_imgw_changed_bytes(
    pinned, tmp_path, imgw
):
    set_project_store(pinned, store_dir=tmp_path / "nowy")
    imgw.publish(V3, NEW)

    report = download_project(pinned)

    assert report.tasks == {"raba": "failed"}
    assert any("inną treść" in (result.error or "") for result in report.files)
    assert get_project_status(pinned).tasks == {"raba": "missing"}


def test_two_tasks_downloaded_concurrently_both_keep_their_pins(tmp_path, imgw):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    add_project_task(project, name="a", command="series select", options=SELECT)
    add_project_task(
        project,
        name="b",
        command="series select",
        options={**SELECT, "stations": [BEZ_Q]},
    )
    nested = []

    def other_process(progress):
        # Drugi proces przypina b, gdy pierwszy pobiera a (bez trzymania blokady).
        if progress.unit == "archive" and not nested:
            nested.append(download_project(project, tasks=["b"]))

    report = download_project(project, tasks=["a"], on_progress=other_process)
    assert nested[0].tasks == {"b": "current"} and report.tasks == {"a": "current"}
    tasks = {task.name: task for task in open_project(project).tasks}
    assert tasks["a"].pinned_at and tasks["b"].pinned_at
    assert [pin.station_code for pin in tasks["a"].files if pin.station_code] == [RABA]
    assert [pin.station_code for pin in tasks["b"].files if pin.station_code] == [BEZ_Q]
    assert not (project / LOCK_NAME).exists()


def test_conflicting_change_of_the_same_task_is_an_explicit_error(tmp_path, imgw):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    add_project_task(project, name="a", command="series select", options=SELECT)
    changed = []

    def other_process(progress):
        if progress.unit == "archive" and not changed:
            changed.append(remove_project_task(project, name="a"))
            add_project_task(
                project,
                name="a",
                command="series select",
                options={**SELECT, "stations": [BEZ_Q]},
            )

    notices = []
    report = download_project(
        project, on_progress=other_process, on_notice=notices.append
    )
    assert report.tasks == {"a": "failed"} and "Conflict" in report.files[-1].error
    conflict = report.files[-1]
    assert (conflict.slot, conflict.task, conflict.error_code) == (
        None,
        "a",
        "conflict",
    )
    assert "project_conflict" in {notice.code for notice in notices}
    (task,) = open_project(project).tasks
    assert (
        task.options["stations"] == [BEZ_Q]
        and task.pinned_at is None
        and task.files == ()
    )


def test_lock_serializes_writers_and_a_stale_lock_is_never_taken_over(
    tmp_path, fixture_root, monkeypatch
):
    project = tmp_path / "project"
    init_project(project, store_dir=fixture_root)
    with ThreadPoolExecutor(8) as pool:
        list(
            pool.map(
                lambda i: add_project_task(
                    project, name=f"t{i}", command="store info", options={}
                ),
                range(8),
            )
        )
    assert sorted(task.name for task in open_project(project).tasks) == [
        f"t{i}" for i in range(8)
    ]

    lock = project / LOCK_NAME
    lock.mkdir()  # pozostałość przerwanego procesu
    (lock / "owner").write_text("stacja-robocza pid 4242\n", encoding="utf-8")
    before = (project / PROJECT_FILE).read_bytes()
    monkeypatch.setattr(project_module, "LOCK_TIMEOUT_S", 0.2)
    with pytest.raises(IMGWProjectError, match="is locked") as error:
        remove_project_task(project, name="t0")
    assert error.value.code == "conflict"
    assert error.value.details == {
        "reason": "locked",
        "owner": "stacja-robocza pid 4242",
    }
    assert lock.is_dir() and (project / PROJECT_FILE).read_bytes() == before
    shutil.rmtree(lock)
    assert len(remove_project_task(project, name="t0").tasks) == 7


def test_project_beside_kartograf_manifest_touches_only_its_own_file(
    tmp_path, fixture_root
):
    project = tmp_path / "project"
    project.mkdir()
    kartograf = project / "kartograf-project.json"
    kartograf.write_text(
        '{"schema":"kartograf-project/1","output_dir":"kartograf","tasks":[]}\n'
    )
    before = (kartograf.stat().st_mtime_ns, kartograf.read_bytes())

    init_project(project, store_dir=fixture_root)
    add_project_task(project, name="info", command="store info", options={})
    add_project_task(
        project,
        name="raba",
        command="series select",
        options={"dataset": DAILY, "stations": RABA, "years": 2024},
    )
    assert [
        action.status for action in check_project(project, tasks=["info"]).actions
    ] == ["current", "missing"]
    get_project_status(project)
    verify_project(project)
    remove_project_task(project, name="info")

    assert (kartograf.stat().st_mtime_ns, kartograf.read_bytes()) == before
    assert sorted(path.name for path in project.iterdir()) == [
        "imgw-project.json",
        "kartograf-project.json",
    ]


def test_cancel_before_work_leaves_store_manifest_and_network_untouched(tmp_path, imgw):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    add_project_task(project, name="a", command="series select", options=SELECT)
    before = snapshot(tmp_path)

    report = download_project(project, cancel=lambda: True)
    assert report.cancelled and report.tasks == {"a": "cancelled"}
    plan = check_project(project, cancel=lambda: True)
    assert plan.cancelled and [action.status for action in plan.actions] == [
        "unverifiable"
    ]
    assert imgw.calls == (0, 0) and snapshot(tmp_path) == before


def test_station_files_are_pinned_under_station_code(pinned, fixture_root):
    (task,) = manifest(pinned)["tasks"]
    (station,) = [pin for pin in task["files"] if pin["role"] == "station_series"]
    assert station["station_code"] == RABA and "station" not in station

    add_project_task(pinned, name="info", command="store info", options={})
    assert manifest(pinned)["tasks"][0]["files"] == task["files"]  # zapis bez zmian

    document = manifest(pinned)
    for pin in document["tasks"][0]["files"]:
        if "station_code" in pin:
            pin["station"] = pin.pop("station_code")  # dawna nazwa pola
    write(pinned, document)
    with pytest.raises(IMGWProjectError, match="unknown keys 'station'") as error:
        open_project(pinned)
    assert error.value.code == "validation_error"


def test_manifest_and_task_errors_carry_section_13_5_codes(tmp_path, fixture_root):
    project = tmp_path / "project"
    with pytest.raises(IMGWProjectError, match="No project manifest") as error:
        open_project(project)
    assert (error.value.code, error.value.details) == (
        "not_found",
        {"option": "project_dir"},
    )
    project.mkdir()
    (project / PROJECT_FILE).mkdir()  # nieczytelny manifest
    with pytest.raises(
        IMGWProjectError, match="Cannot read the project manifest"
    ) as error:
        open_project(project)
    assert error.value.code == "io_error"
    (project / PROJECT_FILE).rmdir()
    for content in ("{", '{"schema":"imgw-project/2","store_dir":"s","tasks":[]}'):
        (project / PROJECT_FILE).write_text(content, encoding="utf-8")
        with pytest.raises(IMGWProjectError) as error:
            open_project(project)
        assert error.value.code == "validation_error"
    (project / PROJECT_FILE).write_bytes(b"\xff\xfe")
    with pytest.raises(IMGWProjectError, match="UTF-8") as error:
        open_project(project)
    assert error.value.code == "validation_error"
    (project / PROJECT_FILE).unlink()

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("x")
    with pytest.raises(
        IMGWProjectError, match="is not a supported IMGW store"
    ) as error:
        init_project(project, store_dir=foreign)
    assert (error.value.code, error.value.details) == (
        "store_unavailable",
        {"option": "store_dir", "reason": "unsupported"},
    )
    store = init_store(tmp_path / "own").root
    with pytest.raises(IMGWProjectError, match="must not lie in the store") as error:
        init_project(store / "project", store_dir=store)
    assert error.value.code == "validation_error"

    init_project(project, store_dir=fixture_root)
    with pytest.raises(IMGWProjectError, match="set_project_store") as error:
        init_project(project, store_dir=store)
    assert error.value.code == "conflict"
    add_project_task(project, name="info", command="store info", options={})
    with pytest.raises(IMGWProjectError, match="already exists") as error:
        add_project_task(project, name="info", command="store info", options={})
    assert (error.value.code, error.value.details) == (
        "conflict",
        {"option": "name", "value": "info"},
    )
    with pytest.raises(IMGWProjectError, match="No task") as error:
        remove_project_task(project, name="brak")
    assert (error.value.code, error.value.details) == (
        "not_found",
        {"option": "name", "value": "brak"},
    )
    with pytest.raises(IMGWProjectError) as error:
        get_project_status(project, tasks=["info", "brak"])
    assert (error.value.code, error.value.details["value"]) == ("not_found", ["brak"])


@pytest.mark.parametrize(
    ("command", "old", "new", "option"),
    [
        (
            "pmaxtp sync",
            {"lat": 52.23, "lon": 21.01},
            {"latitude": 52.23, "longitude": 21.01},
            "lat",
        ),
        (
            "store sync",
            {"dataset": [DAILY], "years": [2024]},
            {"datasets": [DAILY], "years": [2024]},
            "dataset",
        ),
        (
            "store sync",
            {"datasets": [DAILY], "years": [2024], "no_series": True},
            {"datasets": [DAILY], "years": [2024], "series": False},
            "no_series",
        ),
    ],
)
def test_task_options_use_only_the_section_13_2_names(
    tmp_path, fixture_root, command, old, new, option
):
    project = tmp_path / "project"
    init_project(project, store_dir=fixture_root)
    with pytest.raises(
        IMGWValidationError, match=f"Unknown option '{option}'"
    ) as error:
        add_project_task(project, name="zadanie", command=command, options=old)
    assert error.value.details["option"] == "options"  # flaga --options komendy

    document = manifest(project)
    document["tasks"] = [
        {
            "name": "zadanie",
            "command": command,
            "options": old,
            "pinned_at": None,
            "imgwtools_version": None,
            "files": [],
        }
    ]
    write(project, document)
    with pytest.raises(IMGWProjectError, match="options") as error:
        open_project(project)
    assert (error.value.code, error.value.details["option"]) == (
        "validation_error",
        option,
    )

    document["tasks"] = []
    write(project, document)
    (task,) = add_project_task(
        project, name="zadanie", command=command, options=new
    ).tasks
    assert task.options == new


def test_failed_archive_of_a_download_task_has_its_slot_and_code(tmp_path, imgw):
    project = tmp_path / "project"
    init_project(project, store_dir="../store")
    add_project_task(
        project,
        name="pobierz",
        command="datasets download",
        options={"dataset": DAILY, "years": [2024]},
    )
    imgw.get.mock(return_value=httpx.Response(503))

    report = download_project(project)

    assert report.tasks == {"pobierz": "failed"}
    ((item),) = report.files
    assert (item.slot, item.task, item.status, item.error_code) == (
        f"archive:{DAILY}:2024/codz_2024.zip",
        "pobierz",
        "failed",
        "source_unavailable",
    )
