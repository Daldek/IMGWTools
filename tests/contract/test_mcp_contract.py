"""Contract of the MCP adapter: tools answer like Python and ``imgw`` (spec 2026-10-19 §6, §9).

Every contract case of ``test_interface_contract.CASES`` (the commands with a REST
route) runs through the tool of a stdio server in the SDK's in-memory client: the
structured content is the Python envelope ``to_json(root)``, the text content the
line the CLI prints, a stream the text Python yields with an envelope of
``{format, bytes, lines}``. Writes run on a server with writes and ``check: false``
and leave the tree the CLI leaves; a server without writes answers the plan of
``--check`` and leaves the store as it was. The local commands without a REST
route follow the same rule, and every error the CLI reports is the CLI error line
with the registry title.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import anyio
from mcp import Client
from mcp.types import CallToolResult

from imgwtools import (
    ERROR_CODES,
    add_project_task,
    check_command,
    command_schema,
    download_project,
    init_project,
    run_command,
)
from imgwtools.mcp.server import create_server
from tests.contract.support import (
    DAILY,
    H2024,
    NEW,
    RABA,
    V3,
    FakeImgw,
    canonical,
    cli_words,
    envelope_errors,
    snapshot,
    stamps,
)
from tests.contract.test_interface_contract import (
    CASES,
    POST_COMMANDS,
    ROUTES,
    SCENARIOS,
    Setting,
    fresh_store,
    recorded,  # noqa: F401 (fixture)
    relative_data_dir,  # noqa: F401 (fixture)
    resolved,
    rooted,
    served_root,  # noqa: F401 (fixture)
)

# Default page of a list tool (spec 2026-10-19 §6.4 p. 5).
PAGE = 50


def arguments(options: dict[str, object]) -> dict[str, object]:
    """Options in their JSON form: paths as text."""
    return {
        name: str(value) if isinstance(value, Path) else value
        for name, value in options.items()
    }


def call(command: str, options: dict[str, object], *, mode: str) -> CallToolResult:
    """The tool of ``command`` on a fresh stdio server in mode ``mode``."""
    name = command_schema(command)["x-imgw"]["operation_id"]

    async def answer() -> CallToolResult:
        async with Client(create_server(mode=mode)) as client:
            return await client.call_tool(name, arguments(options))

    return anyio.run(answer)


def writing(command: str) -> bool:
    return command_schema(command)["x-imgw"]["writes"] != "none"


def run(command: str, options: dict[str, object]) -> CallToolResult:
    """Run the command: a writing one on a server with writes and ``check: false``."""
    if writing(command):
        return call(command, {**options, "check": False}, mode="write")
    return call(command, options, mode="read")


def assert_envelope(answered: CallToolResult, python, printed, root) -> None:
    """MCP structured content = Python envelope; MCP text = the CLI stdout line."""
    document = answered.structured_content
    assert answered.is_error is False, answered.content[0].text
    assert envelope_errors(document) == []
    assert canonical(document) == canonical(python.to_json(root=root))
    assert answered.content[0].text + "\n" == printed.stdout


def assert_stream(
    answered: CallToolResult, command: str, options, python, root
) -> None:
    """MCP text = the lines Python yields; the envelope sums them up."""
    data = "".join(python.result)
    default = command_schema(command)["properties"]["format"]["default"]
    assert answered.is_error is False, answered.content[0].text
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


# --------------------------------------------------------------------------
# Every command with a REST route: MCP = Python = CLI
# --------------------------------------------------------------------------


@pytest.mark.parametrize("command", list(ROUTES))
def test_every_rest_command_answers_alike_in_mcp_python_and_cli(
    command,
    cli,
    tmp_path,
    fixture_root,
    served_root,  # noqa: F811
    recorded,  # noqa: F811
    frozen,
    relative_data_dir,  # noqa: F811
):
    for case in CASES[command]:
        writes = case.store in ("empty", "fixture")
        if writes:
            root = tmp_path / "store"
        else:
            root = served_root if case.store == "served" else None
        options = case.options if writes else resolved(case.options, root)
        given = rooted(options, root)
        local = dict(given)
        if ROUTES[command]["result"] == "list" and "limit" not in options:
            local["limit"] = PAGE  # the page MCP takes without limit
        before = stamps(served_root)
        answers, requests, trees = {}, {}, {}
        for interface in ("python", "cli", "mcp"):
            if writes:
                fresh_store(case.store, root, fixture_root)
            start = len(recorded.router.calls)
            if interface == "python":
                answers[interface] = run_command(command, options=local)
            elif interface == "cli":
                answers[interface] = cli(*cli_words(command, local))
            else:
                answers[interface] = run(command, given)
            requests[interface] = recorded.traffic(start)
            if writes:
                trees[interface] = snapshot(root)

        python, printed, answered = answers["python"], answers["cli"], answers["mcp"]
        if ROUTES[command]["result"] == "stream":
            assert_stream(answered, command, options, python, root)
        else:
            assert_envelope(answered, python, printed, root)
        assert requests["mcp"] == requests["python"] == requests["cli"]
        if writes:
            assert trees["mcp"] == trees["python"] == trees["cli"]
        assert stamps(served_root) == before


@pytest.mark.parametrize("command", POST_COMMANDS)
def test_without_writes_a_write_is_its_plan_of_check_in_python_and_cli(
    command,
    cli,
    tmp_path,
    fixture_root,
    recorded,  # noqa: F811
    frozen,
):
    (case,) = CASES[command]
    root = tmp_path / "store"
    fresh_store(case.store, root, fixture_root)
    given = rooted(case.options, root)
    before = stamps(root)

    python = check_command(command, options=given)
    printed = cli(*cli_words(command, given), "--check")
    answered = call(command, given, mode="read")

    assert answered.structured_content["check"] is True
    assert_envelope(answered, python, printed, root)
    assert stamps(root) == before
    assert recorded.downloads() == []


# --------------------------------------------------------------------------
# Local commands without a REST route
# --------------------------------------------------------------------------

TASK = {"dataset": DAILY, "stations": [RABA], "years": [2024]}


@dataclass(frozen=True)
class Local:
    """Options of a local command, the directory it works in and its reset."""

    options: dict[str, object]
    tree: Path
    reset: Callable[[], None]


def _gone(path: Path) -> Callable[[], None]:
    def reset() -> None:
        shutil.rmtree(path, ignore_errors=True)

    return reset


def _store_init(tmp_path: Path, fixture_root: Path, imgw: FakeImgw) -> Local:
    target = tmp_path / "nowy"
    return Local({"root": target}, target, _gone(target))


def _datasets_download(tmp_path: Path, fixture_root: Path, imgw: FakeImgw) -> Local:
    imgw.publish(H2024, V3, NEW)
    output = tmp_path / "pobrane"
    options = {"dataset": "hydro/dobowe", "years": [2024], "output": output}
    return Local(options, output, _gone(output))


def _project_init(tmp_path: Path, fixture_root: Path, imgw: FakeImgw) -> Local:
    project = tmp_path / "projekt"
    options = {"project_dir": project, "store_dir": "../magazyn"}
    return Local(options, project, _gone(project))


def _project_add(tmp_path: Path, fixture_root: Path, imgw: FakeImgw) -> Local:
    project = tmp_path / "projekt"

    def reset() -> None:
        shutil.rmtree(project, ignore_errors=True)
        init_project(project, store_dir="../store")

    options = {
        "project_dir": project,
        "name": "raba",
        "command": "series select",
        "options": TASK,
    }
    return Local(options, project, reset)


def _pinned(tmp_path: Path, fixture_root: Path, imgw: FakeImgw) -> Local:
    shutil.copytree(fixture_root, tmp_path / "store")
    project = tmp_path / "project"
    imgw.publish(H2024, V3, NEW)
    init_project(project, store_dir="../store")
    add_project_task(project, name="raba", command="series select", options=TASK)
    assert download_project(project).tasks == {"raba": "current"}
    return Local({"project_dir": project}, tmp_path, lambda: None)


LOCAL = {
    "store init": _store_init,
    "datasets download": _datasets_download,
    "project init": _project_init,
    "project add": _project_add,
    "project status": _pinned,
    "project verify": _pinned,
}


@pytest.mark.parametrize("command", list(LOCAL))
def test_every_local_command_answers_alike_in_mcp_python_and_cli(
    command, cli, tmp_path, fixture_root, imgw, frozen
):
    local = LOCAL[command](tmp_path, fixture_root, imgw)
    local.reset()
    before = snapshot(local.tree)
    root = local.options.get("root")
    answers, trees = {}, {}
    for interface in ("python", "cli", "mcp"):
        local.reset()
        if interface == "python":
            answers[interface] = run_command(command, options=local.options)
        elif interface == "cli":
            answers[interface] = cli(*cli_words(command, arguments(local.options)))
        else:
            answers[interface] = run(command, local.options)
        trees[interface] = snapshot(local.tree)

    assert_envelope(answers["mcp"], answers["python"], answers["cli"], root)
    assert trees["mcp"] == trees["python"] == trees["cli"]
    assert (trees["mcp"] == before) is not writing(command)


# --------------------------------------------------------------------------
# Error codes: the CLI error line with the registry title
# --------------------------------------------------------------------------


# The CLI reports every code with an exit code (the others are REST's own).
@pytest.mark.parametrize(
    "code", [code for code, spec in ERROR_CODES.items() if spec.exit_code is not None]
)
def test_every_error_of_the_cli_is_the_same_document_in_mcp(
    code, cli, tmp_path, fixture_root, imgw, monkeypatch
):
    scenario = SCENARIOS[code](Setting(tmp_path, fixture_root, imgw, monkeypatch))
    options = rooted(scenario.options, scenario.root)

    printed = cli(*cli_words(scenario.command, options))
    answered = run(scenario.command, options)

    if code == "cancelled":  # an envelope without a report, as on CLI stdout
        assert answered.is_error is False
        assert answered.structured_content["status"] == "cancelled"
        assert answered.content[0].text + "\n" == printed.stdout
        return
    line = json.loads(printed.stderr.splitlines()[-1])
    document = answered.structured_content
    assert answered.is_error is True
    assert answered.content[0].text == json.dumps(
        document, ensure_ascii=False, separators=(",", ":")
    )
    assert document["title"] == ERROR_CODES[code].title
    assert canonical(
        [document["code"], document["detail"], document["details"]]
    ) == canonical([line["code"], line["detail"], line["details"]])
