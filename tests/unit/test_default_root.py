"""The default store root (DEV-19.2) and the directories an MCP server may use (DEV-19.3)."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import respx
from mcp import Client

import imgwtools
from imgwtools import config, init_store, validate_command
from imgwtools.config import environment_report, store_root
from imgwtools.mcp.server import create_server
from tests.contract.support import DAILY, H2024, NEW, V3, FakeImgw


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """No IMGW_ROOT, an empty nogat.toml and a data directory of the test."""
    for name in ("IMGW_ROOT", "NOGAT_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "nogat.toml"))
    monkeypatch.setenv("IMGW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)


def config_file(monkeypatch, tmp_path, text):
    path = tmp_path / "nogat.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))


# --------------------------------------------------------------------------
# Resolution: --root > IMGW_ROOT > [imgw] root > <data_dir>/imgw
# --------------------------------------------------------------------------


def test_the_root_is_the_imgw_directory_of_the_data_directory_by_default(tmp_path):
    assert store_root().root == tmp_path / "data" / "imgw"


def test_the_imgw_section_of_nogat_toml_sets_the_root(monkeypatch, tmp_path):
    config_file(monkeypatch, tmp_path, f'[imgw]\nroot = "{tmp_path / "from-file"}"\n')

    assert store_root().root == tmp_path / "from-file"


def test_the_variable_wins_over_the_file(monkeypatch, tmp_path):
    config_file(monkeypatch, tmp_path, f'[imgw]\nroot = "{tmp_path / "from-file"}"\n')
    monkeypatch.setenv("IMGW_ROOT", str(tmp_path / "from-env"))

    assert store_root().root == tmp_path / "from-env"


def test_the_old_variable_is_gone(monkeypatch, tmp_path):
    monkeypatch.setenv("IMGW_STORE_ROOT", str(tmp_path / "old"))

    assert store_root().root == tmp_path / "data" / "imgw"


def test_a_relative_root_is_resolved_against_the_working_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("IMGW_ROOT", "relative/store")

    assert store_root().root == tmp_path / "relative" / "store"


def test_the_public_store_root_names_the_root_its_source_and_the_marker(
    monkeypatch, tmp_path
):
    assert imgwtools.store_root() == imgwtools.StoreRoot(
        tmp_path / "data" / "imgw", "default", None, False
    )

    config_file(monkeypatch, tmp_path, f'[imgw]\nroot = "{tmp_path / "from-file"}"\n')
    (tmp_path / "from-file").mkdir()
    (tmp_path / "from-file" / "imgw-store.json").write_text("{}", encoding="utf-8")
    assert imgwtools.store_root() == imgwtools.StoreRoot(
        tmp_path / "from-file", "file", "[imgw]", True
    )

    monkeypatch.setenv("IMGW_ROOT", str(tmp_path / "from-env"))
    assert imgwtools.store_root() == imgwtools.StoreRoot(
        tmp_path / "from-env", "env", "IMGW_ROOT", False
    )
    # the root, source and name that config show reports
    store = environment_report()["store"]
    assert (store["root"], store["source"], store["name"]) == (
        str(tmp_path / "from-env"),
        "env",
        "IMGW_ROOT",
    )


def test_the_marker_of_another_tool_is_not_the_marker_of_imgw(monkeypatch, tmp_path):
    monkeypatch.setenv("IMGW_ROOT", str(tmp_path))
    (tmp_path / "kartograf-store.json").write_text("{}", encoding="utf-8")

    assert imgwtools.store_root().marker_exists is False


def test_the_public_store_root_does_not_walk_the_tree(monkeypatch, tmp_path):
    (tmp_path / "versions").mkdir()
    monkeypatch.setenv("IMGW_ROOT", str(tmp_path))

    def walked(*args, **kwargs):
        raise AssertionError("store_root() must not read the store")

    monkeypatch.setattr(config, "_tree_size", walked)
    monkeypatch.setattr(os, "walk", walked)
    monkeypatch.setattr(os, "scandir", walked)
    monkeypatch.setattr(Path, "iterdir", walked)

    assert imgwtools.store_root().root == tmp_path


@pytest.mark.parametrize(
    ("setup", "source", "name"),
    [
        ("default", "default", None),
        ("env", "env", "IMGW_ROOT"),
        ("file", "file", "[imgw]"),
    ],
)
def test_config_show_reports_the_root_and_where_it_comes_from(
    monkeypatch, tmp_path, setup, source, name
):
    expected = tmp_path / "data" / "imgw"
    if setup == "env":
        expected = tmp_path / "from-env"
        monkeypatch.setenv("IMGW_ROOT", str(expected))
    if setup == "file":
        expected = tmp_path / "from-file"
        config_file(monkeypatch, tmp_path, f'[imgw]\nroot = "{expected}"\n')
    expected.mkdir(parents=True)
    (expected / "a.txt").write_bytes(b"abc")

    store = environment_report()["store"]

    assert store == {
        "root": str(expected),
        "source": source,
        "name": name,
        "exists": True,
        "size_bytes": 3,
    }


# --------------------------------------------------------------------------
# validate_command fills the root in
# --------------------------------------------------------------------------


def test_a_store_command_without_root_gets_the_default_root(tmp_path):
    options = validate_command("store info", options={})

    assert options == {"root": tmp_path / "data" / "imgw"}


def test_root_given_beats_the_default(tmp_path):
    options = validate_command("store info", options={"root": tmp_path / "mine"})

    assert options["root"] == tmp_path / "mine"


def test_a_live_station_search_has_no_store_but_a_store_search_has(tmp_path):
    live = validate_command("stations find", options={"query": "raba"})
    stored = validate_command(
        "stations find", options={"query": "raba", "source": "store"}
    )

    assert "root" not in live
    assert stored["root"] == tmp_path / "data" / "imgw"


def test_a_version_path_names_its_own_store():
    options = validate_command(
        "series read", options={"version": "v/series.json", "station": "149190310"}
    )

    assert "root" not in options


# --------------------------------------------------------------------------
# imgw mcp --allow-dir
# --------------------------------------------------------------------------


async def call(tool, arguments, *, allow=()):
    async with Client(create_server(mode="write", allow_dirs=allow)) as client:
        answered = await client.call_tool(tool, arguments)
    return answered.is_error, json.loads(answered.content[0].text)


async def test_a_write_without_an_allowed_directory_is_forbidden(tmp_path):
    failed, document = await call(
        "imgw_store_init", {"root": str(tmp_path / "s"), "check": False}
    )

    assert failed
    assert document["code"] == "forbidden"
    assert document["details"]["reason"] == "no_allowed_dir"
    assert not (tmp_path / "s").exists()


async def test_a_plan_needs_no_allowed_directory(tmp_path):
    failed, document = await call("imgw_store_init", {"root": str(tmp_path / "s")})

    assert not failed
    assert document["check"] is True


async def test_a_path_outside_the_allowed_directories_is_forbidden(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    failed, document = await call(
        "imgw_store_init",
        {"root": str(tmp_path / "elsewhere"), "check": False},
        allow=(allowed,),
    )

    assert failed
    assert document["code"] == "forbidden"
    assert document["details"]["reason"] == "outside_allowed_dirs"
    assert document["details"]["option"] == "root"
    assert not (tmp_path / "elsewhere").exists()


async def test_the_default_root_outside_the_allowed_directories_is_forbidden(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    failed, document = await call("imgw_store_info", {}, allow=(allowed,))

    assert failed
    assert document["details"]["reason"] == "outside_allowed_dirs"
    assert document["details"]["value"] == str(tmp_path / "data" / "imgw")


async def test_a_write_inside_an_allowed_directory_works(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    failed, document = await call(
        "imgw_store_init",
        {"root": str(allowed / "store"), "check": False},
        allow=(allowed,),
    )

    assert not failed, document
    assert (allowed / "store" / "imgw-store.json").is_file()


async def test_a_default_root_inside_an_allowed_directory_is_used(
    monkeypatch, tmp_path
):
    allowed = tmp_path / "allowed"
    monkeypatch.setenv("IMGW_ROOT", str(allowed / "default"))
    allowed.mkdir()

    failed, document = await call("imgw_store_info", {}, allow=(allowed,))

    assert not failed, document
    assert document["result"]["root"] == str(allowed / "default")


# The calls below name a place to write: a file of an export, the directory of
# plain files and the plan file of ``store check``. Tool, arguments, option.
WRITING_CALLS = ("guide", "sync", "download", "plan")


def writing_call(kind, base, store):
    out = base / "out"
    plain = {"datasets": [DAILY], "years": "2024", "check": False}
    return {
        "guide": (
            "imgw_commands_guide",
            {"output": str(out / "AGENTS.md"), "check": False},
            "output",
        ),
        "sync": (
            "imgw_store_sync",
            {**plain, "output_dir": str(out / "plain")},
            "output_dir",
        ),
        "download": (
            "imgw_datasets_download",
            {
                "dataset": DAILY,
                "years": "2024",
                "output_dir": str(out / "plain"),
                "check": False,
            },
            "output_dir",
        ),
        "plan": (
            "imgw_store_check",
            {
                "root": str(store),
                "datasets": [DAILY],
                "years": "2024",
                "plan": str(out / "plan.json"),
            },
            "plan",
        ),
    }[kind]


@pytest.mark.parametrize("kind", WRITING_CALLS)
async def test_a_target_without_an_allowed_directory_is_forbidden(kind, tmp_path):
    store = init_store(tmp_path / "store").root
    tool, arguments, _ = writing_call(kind, tmp_path, store)

    failed, document = await call(tool, arguments)

    assert failed
    assert document["code"] == "forbidden"
    assert document["details"]["reason"] == "no_allowed_dir"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", WRITING_CALLS)
async def test_a_target_outside_the_allowed_directories_is_forbidden(kind, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    store = init_store(allowed / "store").root
    tool, arguments, option = writing_call(
        kind, tmp_path, store
    )  # target: tmp_path/out

    failed, document = await call(tool, arguments, allow=(allowed,))

    assert failed
    assert document["code"] == "forbidden"
    assert document["details"]["reason"] == "outside_allowed_dirs"
    assert document["details"]["option"] == option
    assert not (tmp_path / "out").exists()


async def test_an_export_file_inside_an_allowed_directory_is_written(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tool, arguments, _ = writing_call("guide", allowed, allowed / "store")

    failed, document = await call(tool, arguments, allow=(allowed,))

    assert not failed, document
    guide = allowed / "out" / "AGENTS.md"
    assert document["result"]["output"] == str(guide)
    assert [file["status"] for file in document["result"]["files"]] == ["written"]
    assert guide.read_text(encoding="utf-8").startswith("# ")


async def test_plain_files_inside_an_allowed_directory_are_written(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tool, arguments, _ = writing_call("sync", allowed, allowed / "store")

    with respx.mock(assert_all_called=False) as router:
        FakeImgw(router).publish(H2024, V3, NEW)
        failed, document = await call(tool, arguments, allow=(allowed,))

    assert not failed, document
    assert [file["status"] for file in document["result"]["files"]] == ["written"]
    assert (allowed / "out" / "plain" / H2024.server_path).read_bytes() == NEW
    assert not (tmp_path / "data").exists()  # a plain write needs no store root


async def test_a_write_to_the_default_root_outside_the_allowed_directories_is_forbidden(
    tmp_path,
):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    failed, document = await call(
        "imgw_store_sync",
        {"datasets": [DAILY], "years": "2024", "check": False},
        allow=(allowed,),
    )

    assert failed
    assert document["code"] == "forbidden"
    assert document["details"]["reason"] == "outside_allowed_dirs"
    assert document["details"]["option"] == "root"
    assert document["details"]["value"] == str(tmp_path / "data" / "imgw")
    assert not (tmp_path / "data").exists()


def test_the_cli_offers_allow_dir():
    from typer.testing import CliRunner

    from imgwtools.cli.main import app

    result = CliRunner().invoke(app, ["mcp", "--help"])

    assert "--allow-dir" in result.output
