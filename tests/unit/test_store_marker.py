"""The store marker, the first write and the nested-store check (DEV-19.12 to DEV-19.14)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from imgwtools._version import __version__
from imgwtools.commands import check_command, run_command
from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWDataError, IMGWStoreConflictError, IMGWStoreError
from imgwtools.fetch import DownloadResult
from imgwtools.project import add_project_task, check_project, init_project
from imgwtools.store import (
    check_store,
    init_store,
    open_store,
    store_info,
    write_archive,
)
from imgwtools.store.types import StorePlan
from imgwtools.store.writer import lenient_store, prepare_store

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVE = archive_files("pl.imgw.hydro_daily", years=[2024])[0]
DATA = (FIXTURES / "archives" / ARCHIVE.server_path).read_bytes()
MARKER = "imgw-store.json"


def marker(root):
    return json.loads((root / MARKER).read_text(encoding="utf-8"))


def response():
    return DownloadResult(
        DATA, ARCHIVE.url, '"v1"', "Sat, 17 Oct 2026 12:00:00 GMT", len(DATA)
    )


# --------------------------------------------------------------------------
# The marker and its first write (DEV-19.12, DEV-19.13)
# --------------------------------------------------------------------------


def test_the_marker_has_the_minimum_fields_of_the_convention(tmp_path):
    init_store(tmp_path / "s", created_at=datetime(2026, 10, 24, 8, 0, tzinfo=UTC))

    assert marker(tmp_path / "s") == {
        "schema": "imgw-store/1",
        "tool": "imgw",
        "created_at": "2026-10-24T08:00:00Z",
        "producer_version": __version__,
        "created_by": f"imgwtools {__version__}",
    }


def test_the_marker_always_has_a_creation_time(tmp_path):
    init_store(tmp_path / "s")

    assert datetime.fromisoformat(marker(tmp_path / "s")["created_at"]).tzinfo


def test_the_first_write_into_a_new_root_creates_the_marker(tmp_path):
    root = tmp_path / "new" / "deep"

    written = write_archive(root, archive=ARCHIVE, response=response())

    assert written.status == "new"
    assert marker(root)["tool"] == "imgw"
    assert store_info(root).supported
    created = marker(root)["created_at"]
    write_archive(root, archive=ARCHIVE, response=response())
    assert marker(root)["created_at"] == created


def test_a_root_with_only_the_server_state_is_still_new(tmp_path):
    root = tmp_path / "imgw"
    root.mkdir()
    (root / "api_keys.json").write_text("{}", encoding="utf-8")

    prepare_store(root)

    assert (root / MARKER).is_file()
    assert (root / "api_keys.json").read_text(encoding="utf-8") == "{}"


def test_a_root_with_other_files_is_not_taken_over(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").write_text("mine", encoding="utf-8")

    for call in (prepare_store, init_store):
        with pytest.raises(IMGWStoreConflictError) as error:
            call(tmp_path / "docs")
        assert error.value.details["reason"] == "not_empty"
    assert not (tmp_path / "docs" / MARKER).exists()


def test_an_older_marker_gains_the_missing_fields_on_the_next_write(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    (root / MARKER).write_text(
        '{"schema": "imgw-store/1", "created_by": "imgwtools 2.9"}', encoding="utf-8"
    )

    prepare_store(root)

    completed = marker(root)
    assert completed["created_by"] == "imgwtools 2.9"
    assert (completed["tool"], completed["producer_version"]) == ("imgw", __version__)
    assert completed["created_at"].endswith("Z")
    assert store_info(root).supported


def test_a_plan_opens_a_new_root_without_creating_anything(tmp_path):
    handle = lenient_store(tmp_path / "plan")

    assert handle.root == tmp_path / "plan"
    assert not (tmp_path / "plan").exists()


# --------------------------------------------------------------------------
# A layout without its marker (DEV-19.13)
# --------------------------------------------------------------------------


def layout(root, schema="imgw-meta/1"):
    version = root / "archives" / "versions" / "d" / "a" / "2026-10-17_aaaaaaaa"
    version.mkdir(parents=True)
    (version / "a.zip").write_bytes(b"x")
    (version / "a.zip.meta.json").write_text(
        json.dumps({"schema": schema}), encoding="utf-8"
    )


@pytest.mark.parametrize(
    "call", [prepare_store, lenient_store, open_store], ids=lambda call: call.__name__
)
def test_a_layout_without_a_marker_is_unavailable_with_the_hint_to_init(tmp_path, call):
    layout(tmp_path / "s")

    with pytest.raises(IMGWStoreError) as error:
        call(tmp_path / "s")

    assert error.value.code == "store_unavailable"
    assert error.value.details["reason"] == "no_marker"
    assert f"imgw store init --root {tmp_path / 's'}" in error.value.detail
    assert not (tmp_path / "s" / MARKER).exists()


def test_a_layout_without_a_marker_is_reported_by_store_info_with_the_hint(tmp_path):
    layout(tmp_path / "s")

    info = store_info(tmp_path / "s")

    assert not info.supported
    assert "imgw store init --root" in info.problems[0]


def test_store_init_verifies_the_layout_and_writes_the_marker(tmp_path):
    layout(tmp_path / "s")

    init_store(tmp_path / "s")

    assert marker(tmp_path / "s")["schema"] == "imgw-store/1"
    assert store_info(tmp_path / "s").supported


def test_store_init_refuses_a_layout_with_a_foreign_sidecar(tmp_path):
    layout(tmp_path / "s", schema="kartograf-meta/1")

    with pytest.raises(IMGWDataError) as error:
        init_store(tmp_path / "s")

    assert error.value.details["reason"] == "invalid_layout"
    assert "a.zip.meta.json" in error.value.details["problems"][0]
    assert not (tmp_path / "s" / MARKER).exists()


def test_a_kartograf_layout_is_not_an_imgw_layout(tmp_path):
    (tmp_path / "k" / "versions").mkdir(parents=True)

    with pytest.raises(IMGWStoreConflictError) as error:
        init_store(tmp_path / "k")

    assert error.value.details["reason"] == "not_empty"


# --------------------------------------------------------------------------
# No store inside a store, by marker names alone (DEV-19.14)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["imgw-store.json", "kartograf-store.json"])
def test_a_store_does_not_nest_in_a_store_of_any_tool(tmp_path, name):
    (tmp_path / "outer" / "inner").mkdir(parents=True)
    (tmp_path / "outer" / name).write_text('{"schema": "x/1"}', encoding="utf-8")

    for call in (prepare_store, init_store):
        with pytest.raises(IMGWStoreConflictError) as error:
            call(tmp_path / "outer" / "inner")
        assert error.value.details["reason"] == "nested_store"
        assert name in error.value.detail


def test_the_root_of_another_tool_is_not_an_imgw_store(tmp_path):
    root = tmp_path / "k"
    root.mkdir()
    (root / "kartograf-store.json").write_text('{"schema": "k/1"}', encoding="utf-8")

    with pytest.raises(IMGWStoreConflictError) as error:
        prepare_store(root)

    assert error.value.details["reason"] == "nested_store"
    assert "kartograf-store.json" in error.value.detail


@pytest.mark.parametrize("name", ["imgw-store.json", "kartograf-store.json"])
def test_a_root_does_not_contain_a_store_of_any_tool(tmp_path, name):
    (tmp_path / "outer" / "inner").mkdir(parents=True)
    (tmp_path / "outer" / "inner" / name).write_text("{}", encoding="utf-8")

    for call in (prepare_store, init_store):
        with pytest.raises(IMGWStoreConflictError) as error:
            call(tmp_path / "outer")
        assert error.value.details["reason"] == "nested_store"


def test_an_existing_store_may_hold_its_own_trees(tmp_path):
    root = tmp_path / "s"
    write_archive(root, archive=ARCHIVE, response=response())

    assert prepare_store(root).root == root


def test_the_plan_of_store_init_follows_the_real_run(tmp_path):
    layout(tmp_path / "good")
    layout(tmp_path / "foreign", schema="kartograf-meta/1")
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "api_keys.json").write_text("{}", encoding="utf-8")
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "notes.txt").write_text("mine", encoding="utf-8")

    states = {
        name: check_command("store init", options={"root": tmp_path / name})
        .result.actions[0]
        .status
        for name in ("good", "foreign", "empty", "busy", "missing")
    }

    assert states == {
        "good": "missing",
        "foreign": "check_failed",
        "empty": "missing",
        "busy": "check_failed",
        "missing": "missing",
    }
    assert not (tmp_path / "good" / MARKER).exists()


# --------------------------------------------------------------------------
# The plan shows the nested-store refusal of the run (DEV-19.10, DEV-19.14)
# --------------------------------------------------------------------------

DAILY = "pl.imgw.hydro_daily"
# Every command that writes a store, with the options of its store mode.
STORE_WRITES = {
    "datasets download": {"dataset": DAILY, "years": [2024]},
    "store init": {},
    "store sync": {"datasets": [DAILY], "years": [2024]},
    "pmaxtp sync": {"latitude": 52.0, "longitude": 20.0},
    "series build": {"dataset": DAILY},
    "store catalog": {},
}


def nested_root(tmp_path, where):
    """A root that would nest a store, in each of the three ways the run refuses."""
    outer = tmp_path / "outer"
    (outer / "inner").mkdir(parents=True)
    if where == "inside":
        (outer / "kartograf-store.json").write_text("{}", encoding="utf-8")
        return outer / "inner"
    if where == "another_tool":
        (outer / "kartograf-store.json").write_text("{}", encoding="utf-8")
        return outer
    (outer / "inner" / "kartograf-store.json").write_text("{}", encoding="utf-8")
    return outer


@pytest.mark.parametrize("where", ["inside", "another_tool", "below"])
@pytest.mark.parametrize("command", sorted(STORE_WRITES))
def test_the_plan_of_a_store_write_lists_the_nested_store_as_a_conflict(
    tmp_path, command, where
):
    root = nested_root(tmp_path, where)

    outcome = check_command(command, options={"root": root, **STORE_WRITES[command]})

    assert outcome.status == "ok"
    (action,) = outcome.result.actions
    assert (action.command, action.action, action.reason) == (
        command,
        "conflict",
        "nested_store",
    )
    assert (action.status, action.path, outcome.result.root) == (
        "unverifiable",
        root,
        root,
    )
    assert "kartograf-store.json" in action.detail
    assert outcome.result.items == ()
    assert not (root / MARKER).exists()


@pytest.mark.parametrize(
    "command", ["datasets download", "store init", "series build", "store catalog"]
)
def test_the_run_refuses_the_root_that_its_plan_lists_as_a_conflict(tmp_path, command):
    root = nested_root(tmp_path, "inside")

    with pytest.raises(IMGWStoreConflictError) as error:
        run_command(command, options={"root": root, **STORE_WRITES[command]})

    assert error.value.details["reason"] == "nested_store"


def test_the_plan_of_a_sync_into_a_nested_store_is_saved_without_a_request(
    tmp_path, monkeypatch
):
    root = nested_root(tmp_path, "inside")
    saved = tmp_path / "plan.json"

    def refuse(*args, **kwargs):
        raise AssertionError("the nested store is refused before any request")

    monkeypatch.setattr("imgwtools.store.sync.httpx.Client", refuse)
    plan = check_store(root, datasets=[DAILY], years=[2024], plan=saved)

    (action,) = plan.actions
    assert (action.action, action.reason) == ("conflict", "nested_store")
    assert StorePlan.from_json(saved) == plan


def test_the_plan_of_a_project_download_keeps_the_nested_store_conflict(tmp_path):
    store = tmp_path / "outer" / "store"
    init_store(store)
    (tmp_path / "outer" / "kartograf-store.json").write_text("{}", encoding="utf-8")
    project = tmp_path / "project"
    init_project(project, store_dir=store)
    add_project_task(
        project, name="daily", command="series build", options={"dataset": DAILY}
    )

    plan = check_project(project)

    assert [(a.command, a.action, a.reason) for a in plan.actions] == [
        ("series build", "conflict", "nested_store"),
        ("project download", None, None),
    ]
    assert plan.actions[0].detail.startswith("daily: ")
