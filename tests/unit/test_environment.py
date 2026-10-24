"""User environment (DEV-18): ``nogat.toml``, ``NOGAT_*``, directories, ``imgw config show``."""

import json
import os
from pathlib import Path

import platformdirs
import pytest
from typer.testing import CliRunner

from imgwtools import _environment as environment
from imgwtools.cli import main as cli_main
from imgwtools.config import Settings, check_config, environment_report
from imgwtools.exceptions import IMGWValidationError

RUNNER = CliRunner()


@pytest.fixture(autouse=True)
def user_environment(tmp_path, monkeypatch):
    """No IMGW_/NOGAT_ variable, ``.env`` or user ``nogat.toml`` of the machine."""
    for name in list(os.environ):
        if name.startswith(("IMGW_", "NOGAT_")):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    monkeypatch.setattr(
        platformdirs, "user_config_path", lambda *a, **k: home / "config"
    )
    monkeypatch.setattr(platformdirs, "user_data_path", lambda *a, **k: home / "data")
    monkeypatch.setattr(platformdirs, "user_cache_path", lambda *a, **k: home / "cache")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


def write_config(tmp_path: Path, monkeypatch, text: str) -> Path:
    path = tmp_path / "custom" / "nogat.toml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))
    return path


def source_of(key):
    entry = environment_report()["keys"][key]
    return entry["value"], entry["source"], entry["name"]


def test_a_shared_key_comes_from_the_first_layer_of_dev_18_1(tmp_path, monkeypatch):
    write_config(
        tmp_path,
        monkeypatch,
        '[nogat]\ndata_dir = "/nogat-file"\n\n[imgw]\ndata_dir = "/imgw-file"\n',
    )
    (Path.cwd() / ".env").write_text("IMGW_DATA_DIR=/dotenv\n", encoding="utf-8")
    monkeypatch.setenv("NOGAT_DATA_DIR", "/nogat-env")
    monkeypatch.setenv("IMGW_DATA_DIR", "/imgw-env")

    expected = [
        ("/imgw-env", "env", "IMGW_DATA_DIR"),
        ("/dotenv", "dotenv", "IMGW_DATA_DIR"),
        ("/nogat-env", "env", "NOGAT_DATA_DIR"),
        ("/imgw-file", "file", "[imgw]"),
        ("/nogat-file", "file", "[nogat]"),
    ]
    for value, source, name in expected:
        assert source_of("data_dir") == (value, source, name)
        assert str(Settings().data_dir) == value
        # Drop the layer that won, so the next one shows.
        if source == "env":
            monkeypatch.delenv(name)
        elif source == "dotenv":
            (Path.cwd() / ".env").unlink()
        else:
            path = Path(os.environ["NOGAT_CONFIG"])
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    f'data_dir = "{value}"', "x = 1"
                ),
                encoding="utf-8",
            )
    assert source_of("data_dir")[1:] == ("default", None)
    assert Settings().data_dir == environment.default_data_dir()


def test_the_nogat_section_holds_only_the_shared_keys(tmp_path, monkeypatch):
    write_config(
        tmp_path,
        monkeypatch,
        '[nogat]\nlang = "en"\nhost = "ignored"\n\n[kartograf]\nlang = "de"\n\n'
        '[imgw]\nhost = "127.0.0.1"\nport = 9000\n',
    )

    settings = Settings()

    assert (settings.lang, settings.host, settings.port) == ("en", "127.0.0.1", 9000)
    assert source_of("lang")[1:] == ("file", "[nogat]")
    assert source_of("port")[1:] == ("file", "[imgw]")


def test_credentials_come_from_the_environment_only(tmp_path, monkeypatch):
    write_config(
        tmp_path,
        monkeypatch,
        '[imgw]\nstore_write_token = "from-file"\nport = 1\nfoo = 2\n',
    )

    missing = environment_report()
    assert Settings().store_write_token is None
    assert missing["credentials"] == {"IMGW_STORE_WRITE_TOKEN": "missing"}
    assert "store_write_token" not in missing["keys"]
    assert missing["config_file"]["ignored"] == [
        {"key": "store_write_token", "reason": "credential"},
        {"key": "foo", "reason": "unknown"},
    ]

    monkeypatch.setenv("IMGW_STORE_WRITE_TOKEN", "from-env")
    present = environment_report()
    assert present["credentials"] == {"IMGW_STORE_WRITE_TOKEN": "present"}
    assert "from-env" not in json.dumps(present) and "from-file" not in json.dumps(
        present
    )


def test_directories_stay_out_of_the_working_directory(user_environment, monkeypatch):
    home = user_environment
    settings = Settings()

    assert settings.data_dir == home / "data"
    assert settings.cache_dir == home / "cache"
    assert settings.reference_dir == home / "cache" / "imgw" / "reference"
    assert settings.api_keys_file == home / "data" / "imgw" / "api_keys.json"
    assert environment.reference_dir() == settings.reference_dir

    monkeypatch.setenv("NOGAT_CACHE_DIR", "/elsewhere")  # the shared key moves it
    assert Settings().reference_dir == Path("/elsewhere/imgw/reference")
    assert environment.reference_dir() == Path("/elsewhere/imgw/reference")
    monkeypatch.setenv("IMGW_REFERENCE_DIR", "/reference")
    assert Settings().reference_dir == Path("/reference")
    assert environment.reference_dir() == Path("/reference")


def test_a_file_that_cannot_be_used_is_reported_and_not_applied(tmp_path, monkeypatch):
    assert environment.config_file().error is None  # the default file may be absent
    check_config()

    path = write_config(tmp_path, monkeypatch, "[imgw\nport = 1\n")
    assert Settings().port == 8000
    reported = environment_report()["config_file"]
    assert reported["error"].startswith("invalid TOML") and reported["exists"]
    with pytest.raises(IMGWValidationError) as caught:
        check_config()
    assert caught.value.code == "validation_error"
    assert "invalid TOML" in caught.value.detail  # the cause is in the message
    assert caught.value.details == {
        "option": "NOGAT_CONFIG",
        "path": str(path),
        "reason": "invalid_config",  # snake_case, the same for every cause
    }

    monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "missing.toml"))
    assert environment.config_file().error == "the file does not exist"


@pytest.mark.parametrize(
    "content",
    [
        b'[imgw]\nlang = "za\xbf\xf3\xb3\xe6"\n',
        b"\xff\xfe[\x00i\x00m\x00g\x00w\x00]\x00",
    ],
    ids=["cp1250-text", "utf-16"],
)
def test_a_file_that_is_not_utf_8_is_reported_like_any_unusable_file(
    content, tmp_path, monkeypatch
):
    path = write_config(tmp_path, monkeypatch, "")
    path.write_bytes(content)
    cause = "cannot read the file: not UTF-8 text"

    assert environment.config_file().error == cause
    assert Settings().port == 8000  # nothing of the file is applied
    with pytest.raises(IMGWValidationError) as caught:
        check_config()
    assert cause in caught.value.detail
    assert caught.value.details == {
        "option": "NOGAT_CONFIG",
        "path": str(path),
        "reason": "invalid_config",
    }

    version = RUNNER.invoke(cli_main.app, ["version"])
    shown = RUNNER.invoke(cli_main.app, ["config", "show", "--json"])
    assert version.exit_code == 2
    error = json.loads(version.stderr.splitlines()[-1])
    assert error["code"] == "validation_error"
    assert error["details"]["reason"] == "invalid_config"
    assert cause in error["detail"]
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["config_file"]["error"] == cause


def test_imgw_stops_on_an_unusable_file_but_config_show_still_reports_it(
    tmp_path, monkeypatch
):
    write_config(tmp_path, monkeypatch, "not toml")

    version = RUNNER.invoke(cli_main.app, ["version"])
    shown = RUNNER.invoke(cli_main.app, ["config", "show", "--json"])

    assert version.exit_code == 2
    error = json.loads(version.stderr.splitlines()[-1])
    assert error["code"] == "validation_error"
    assert error["details"]["reason"] == "invalid_config"
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["config_file"]["error"].startswith("invalid TOML")


def test_config_show_json_gives_every_key_its_source_and_the_store_size(
    tmp_path, monkeypatch
):
    root = tmp_path / "store"
    (root / "versions").mkdir(parents=True)
    (root / "a.bin").write_bytes(b"x" * 100)
    os.link(root / "a.bin", root / "versions" / "b.bin")  # one file, two names
    (root / "c.txt").write_bytes(b"y" * 7)
    monkeypatch.setenv("IMGW_ROOT", str(root))
    monkeypatch.setenv("IMGW_PORT", "9001")

    result = RUNNER.invoke(cli_main.app, ["config", "show", "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)  # exactly one document
    assert (report["schema"], report["tool"]) == ("imgw-config/1", "imgw")
    assert report["keys"]["port"] == {
        "value": 9001,
        "source": "env",
        "name": "IMGW_PORT",
    }
    assert report["keys"]["host"]["source"] == "default"
    assert all(
        {"value", "source", "name"} <= set(entry) for entry in report["keys"].values()
    )
    assert report["store"] == {
        "root": str(root),
        "source": "env",
        "name": "IMGW_ROOT",
        "exists": True,
        "size_bytes": 107,
    }


def test_config_show_without_json_is_text_and_a_missing_store_has_no_size(monkeypatch):
    monkeypatch.setenv(
        "IMGW_LANG", "en"
    )  # help and text follow the CLI language at import

    result = RUNNER.invoke(cli_main.app, ["config", "show"])

    assert result.exit_code == 0, result.output
    assert "data_dir = " in result.stdout and "IMGW_STORE_WRITE_TOKEN" in result.stdout
    assert environment_report()["store"]["size_bytes"] is None
