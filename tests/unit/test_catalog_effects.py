"""Effects declared by the catalog (spec 2026-10-19 §3.2, §9): network, writes, twins.

Every contract case (``CASES`` of ``tests/contract/test_interface_contract.py``)
runs through ``run_command``: a command declaring ``network=False`` sends no
request, a command declaring ``writes="none"`` leaves the store and the working
directory as they were, a command declaring ``writes="add"`` keeps every
existing file, and every option declaring a write creates (or replaces) its
file. The declarations are the §3.2 table, published in ``x-imgw``.
"""

import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest
import respx

from imgwtools import init_project, init_store, run_command, sync_pmaxtp
from imgwtools.commands import command_schema, data_commands
from imgwtools.testing import build_fixture_store
from tests.contract.support import H2024, NEW, V3, FakeImgw, snapshot, stamps
from tests.contract.test_interface_contract import CASES, Case, resolved, rooted

SPECS = {spec.name: spec for spec in data_commands()}
# MCP tool names (AGI-5.2): the project prefix and at most 48 characters of [a-z0-9_].
TOOL_NAME = re.compile(r"imgw_[a-z0-9_]{1,43}")
# Spec 2026-10-19 §3.2: command → (writes, network, writing options).
EFFECTS = {
    "datasets list": ("none", False, {}),
    "datasets files": ("none", False, {}),
    "datasets download": ("add", True, {"output_dir": "add", "force": "replace"}),
    "datasets providers": ("none", False, {}),
    "stations find": ("none", True, {}),
    "current hydro": ("none", True, {}),
    "current meteo": ("none", True, {}),
    "current synop": ("none", True, {}),
    "current warnings": ("none", True, {}),
    "current hydro-states": ("none", True, {}),
    "pmaxtp fetch": ("none", True, {}),
    "pmaxtp url": ("none", False, {}),
    "pmaxtp check": ("none", False, {}),
    "pmaxtp sync": ("add", True, {"output_dir": "add", "force": "replace"}),
    "pmaxtp read": ("none", False, {}),
    "store init": ("add", False, {}),
    "store info": ("none", False, {}),
    "store scan": ("none", False, {}),
    "store check": ("none", True, {"plan": "replace"}),
    "store sync": ("add", True, {"output_dir": "add", "force": "replace"}),
    "store catalog": ("add", True, {}),
    "store export": ("none", False, {"path": "replace"}),
    "series build": ("add", False, {}),
    "series select": ("none", False, {}),
    "series read": ("none", False, {}),
    "series summary": ("none", False, {}),
    "series export": ("none", False, {"path": "replace"}),
    "project init": ("add", False, {}),
    "project add": ("add", False, {}),
    "project remove": ("replace", False, {}),
    "project set-store": ("replace", False, {}),
    "project download": ("replace", True, {}),
    "project check": ("none", True, {"plan": "replace"}),
    "project status": ("none", False, {}),
    "project verify": ("none", False, {}),
    "commands list": ("none", False, {}),
    "commands schema": ("none", False, {}),
    "commands guide": ("none", False, {"path": "replace"}),
}
# Writing options of local commands (without a contract case); the plain ones are
# held by tests/unit/test_plain_output.py.
LOCAL_WRITES = {
    ("project check", "plan"),
    ("datasets download", "output_dir"),
    ("datasets download", "force"),
    ("store sync", "output_dir"),
    ("store sync", "force"),
    ("pmaxtp sync", "output_dir"),
    ("pmaxtp sync", "force"),
}


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("effects") / "store").root


@pytest.fixture(scope="module")
def served_root(tmp_path_factory, fixture_root):
    """The fixture store plus a PMAXTP cell, as served to the contract cases."""
    root = tmp_path_factory.mktemp("served") / "store"
    shutil.copytree(fixture_root, root)
    with respx.mock(assert_all_called=False) as router:
        FakeImgw(router).publish_pmaxtp("pmaxtp_pot_first")
        sync_pmaxtp(root, latitude=52.23, longitude=21.01)
    return root


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Empty working directory of the commands: relative defaults land here."""
    directory = tmp_path / "workdir"
    directory.mkdir()
    monkeypatch.chdir(directory)
    return directory


@pytest.fixture
def recorded():
    """Recorded sources of every contract case; any other request fails the test."""
    with respx.mock(assert_all_called=False) as router:
        imgw = FakeImgw(router)
        imgw.publish(H2024, V3, NEW)
        imgw.publish_catalog_sources()
        imgw.publish_live()
        imgw.publish_pmaxtp("pmaxtp_pot_first", "pmaxtp_amp")
        yield imgw


def case_root(case: Case, target: Path, served: Path, fixture: Path) -> Path | None:
    """A fresh store of the case at ``target`` (``None`` for a case without root)."""
    if case.store is None:
        return None
    if case.store == "empty":
        return init_store(target).root
    shutil.copytree(served if case.store == "served" else fixture, target)
    return target


def run(command: str, options: dict[str, object], root: Path | None) -> str:
    """Run a case through Python, reading a stream to its end; return the status."""
    outcome = run_command(command, options=rooted(resolved(options, root), root))
    if SPECS[command].result == "stream" and "path" not in options:
        "".join(cast(Iterable[str], outcome.result))
    return outcome.status


def cases_of(predicate) -> list[Any]:
    """Contract cases of the commands meeting ``predicate``, one test each."""
    return [
        pytest.param(command, case, id=f"{command} #{index}")
        for command, cases in CASES.items()
        if predicate(SPECS[command])
        for index, case in enumerate(cases, start=1)
    ]


def writing_cases() -> list[tuple[str, Case, str]]:
    """The first case of a contract command with each of its writing options."""
    return [
        (command, cases[0], option.name)
        for command, cases in CASES.items()
        for option in SPECS[command].options
        if option.writes != "none"
        and option.type == "path"
        and option.name != "output_dir"
    ]


def test_catalog_declares_the_effects_of_spec_section_3_2():
    commands = command_schema()["commands"]
    assert {
        schema["title"]: (
            schema["x-imgw"]["writes"],
            schema["x-imgw"]["network"],
            {
                name: prop["x-imgw-writes"]
                for name, prop in schema["properties"].items()
                if "x-imgw-writes" in prop
            },
        )
        for schema in commands
    } == EFFECTS
    names = [schema["x-imgw"]["operation_id"] for schema in commands]
    assert names == [
        "imgw_" + schema["title"].replace(" ", "_").replace("-", "_")
        for schema in commands
    ]
    assert len(set(names)) == len(names)
    assert all(TOOL_NAME.fullmatch(name) for name in names)
    assert all(isinstance(schema["x-imgw"]["idempotent"], bool) for schema in commands)


def test_every_write_can_be_planned_by_a_check_twin():
    for spec in data_commands():
        if spec.writes != "none":
            assert spec.check is not None, spec.name
        for option in spec.options:
            if option.writes != "none":
                # A check itself (store check, project check) plans by running.
                is_check = spec.function.startswith("check_")
                assert spec.check is not None or is_check, (spec.name, option.name)


@pytest.mark.parametrize(("command", "case"), cases_of(lambda spec: not spec.network))
def test_offline_commands_send_no_request(
    command, case, tmp_path, served_root, fixture_root, workdir
):
    root = case_root(case, tmp_path / "store", served_root, fixture_root)
    with respx.mock(assert_all_called=False) as router:
        anything = router.route().respond(503)
        status = run(command, case.options, root)
    assert status == "ok"
    assert anything.call_count == 0


@pytest.mark.parametrize(("command", "case"), cases_of(lambda s: s.writes == "none"))
def test_reading_commands_leave_the_store_and_working_directory_unchanged(
    command, case, tmp_path, served_root, fixture_root, workdir, recorded
):
    root = case_root(case, tmp_path / "store", served_root, fixture_root)
    trees = [workdir, *([root] if root is not None else [])]
    before = [(snapshot(tree), stamps(tree)) for tree in trees]

    assert run(command, case.options, root) == "ok"

    assert [(snapshot(tree), stamps(tree)) for tree in trees] == before


@pytest.mark.parametrize(("command", "case"), cases_of(lambda s: s.writes == "add"))
def test_adding_commands_keep_every_existing_file(
    command, case, tmp_path, served_root, fixture_root, workdir, recorded
):
    root = case_root(case, tmp_path / "store", served_root, fixture_root)
    assert root is not None
    files = {path: digest for path, digest in snapshot(root).items() if digest}
    touched = {path: stamp for path, stamp in stamps(root).items() if path in files}

    assert run(command, case.options, root) == "ok"

    after, times = snapshot(root), stamps(root)
    assert {path: after.get(path) for path in files} == files
    assert {path: times.get(path) for path in touched} == touched


def test_every_writing_option_has_a_case():
    covered = {(command, option) for command, _, option in writing_cases()}
    assert covered | LOCAL_WRITES == {
        (spec.name, option.name)
        for spec in data_commands()
        for option in spec.options
        if option.writes != "none"
    }


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
@pytest.mark.parametrize(
    ("command", "case", "option"),
    [pytest.param(*row, id=f"{row[0]} {row[2]}") for row in writing_cases()],
)
def test_a_writing_option_writes_its_file(
    command, case, option, existing, tmp_path, served_root, fixture_root, recorded
):
    root = case_root(case, tmp_path / "store", served_root, fixture_root)
    target = tmp_path / "out" / f"{option}.txt"
    target.parent.mkdir()
    if existing:  # "replace": an existing file is overwritten
        target.write_text("stara treść\n", encoding="utf-8")

    assert run(command, {**case.options, option: target}, root) == "ok"

    assert target.is_file()
    assert target.read_text(encoding="utf-8") != "stara treść\n"


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_project_check_writes_its_plan_file(existing, tmp_path, workdir):
    project = init_project(tmp_path / "projekt", store_dir="../magazyn").path
    target = tmp_path / "plan.json"
    if existing:
        target.write_text("{}\n", encoding="utf-8")
    with respx.mock(assert_all_called=False) as router:
        anything = router.route().respond(503)
        outcome = run_command(
            "project check", options={"project_dir": project, "plan": target}
        )

    assert outcome.status == "ok"
    assert target.read_text(encoding="utf-8") != "{}\n"
    assert anything.call_count == 0  # a project without tasks asks no source
