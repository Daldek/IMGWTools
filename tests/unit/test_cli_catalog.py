"""``imgw`` generated from the command catalog (spec §13.10): envelope, errors, flags."""

import functools
import importlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
import typer
from typer.testing import CliRunner

from imgwtools import store
from imgwtools.cli import _dispatch
from imgwtools.cli.main import app
from imgwtools.commands import (
    check_command,
    command_schema,
    data_commands,
    format_command,
    run_command,
    validate_command,
)
from imgwtools.config import settings
from imgwtools.exceptions import ERROR_CODES, IMGWError
from imgwtools.store.types import CommandResult, Notice, SeriesReport, SyncReport
from imgwtools.testing import build_fixture_store
from imgwtools.urls import IMGW_API_URL
from tests.contract.support import (
    DAILY,
    H2023,
    H2024,
    NEW,
    PRECIP,
    RABA,
    V1,
    V3,
    FakeImgw,
    archive_bytes,
    snapshot,
    stamps,
    violations,
)
from tests.unit.test_commands import SAMPLES

RUNNER = CliRunner()
SPECS = {spec.name: spec for spec in data_commands()}
CATALOG = command_schema()
EXIT_CODES = CATALOG["exit_codes"]
FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
O2001 = f"archive:{PRECIP}:2001/2001_01_o.zip"
INSTALLED = Path(sys.executable).with_name("imgw")
# Last stderr line of a failed command (spec §13.5).
CLI_ERROR = {
    "type": "object",
    "required": ["code", "detail", "details"],
    "properties": {
        "code": {
            "enum": [
                "validation_error",
                "not_found",
                "conflict",
                "source_unavailable",
                "missing_dependency",
                "data_error",
                "store_unavailable",
                "io_error",
                "cancelled",
                "forbidden",
                "internal_error",
            ]
        },
        "detail": {"type": "string", "minLength": 1},
        "details": {"type": "object"},
    },
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def no_store_root(monkeypatch):
    """The developer's IMGW_STORE_ROOT and IMGW_LANG must not reach the commands."""
    monkeypatch.delenv("IMGW_STORE_ROOT", raising=False)
    monkeypatch.delenv("IMGW_LANG", raising=False)


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("cli") / "store").root


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=False) as router:
        yield FakeImgw(router)


@pytest.fixture
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("komenda nie może używać sieci")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in (
        "imgwtools.store.writer",
        "imgwtools.store.series",
        "imgwtools.store.catalog",
        "imgwtools.store.sync",
        "imgwtools.store.pmaxtp",
        "imgwtools.commands",
    ):
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)


def invoke(*args, env=None):
    return RUNNER.invoke(app, [str(arg) for arg in args], env=env)


def envelope(result):
    """The one-line envelope printed on stdout by a successful command."""
    assert result.exit_code == 0, result.output
    assert result.stdout.endswith("\n") and result.stdout.count("\n") == 1
    return json.loads(result.stdout)


def error_line(result, code):
    """The JSON error line ending stderr of a failed command with an empty stdout."""
    assert result.stdout == ""
    document = json.loads(result.stderr.splitlines()[-1])
    assert violations(document, CLI_ERROR) == []
    assert document["code"] == code, document
    assert result.exit_code == ERROR_CODES[code].exit_code
    return document


def click_command(name):
    command = typer.main.get_command(app)
    for word in name.split():
        command = command.commands[word]
    return command


def argv(command, options, *, aliases=False):
    """CLI words of ``options``: canonical flags, or short aliases with list items
    given as repeated flags."""
    spec = SPECS[command]
    flags = {option.flag: option for option in spec.options}
    flags |= {f"--no-{o.flag[2:]}": o for o in spec.options if o.type == "bool"}
    words = shlex.split(format_command(command, options=options))[3:]
    args = command.split()
    while words:
        flag = words.pop(0)
        option = flags[flag]
        if option.type == "bool":
            args.append(flag)
            continue
        value = words.pop(0)
        if not aliases:
            args += [flag, value]
            continue
        name = option.aliases[0] if option.aliases else flag
        for item in value.split(",") if option.type == "list" else [value]:
            args += [name, item]
    return args


def raising(monkeypatch, module, name, error):
    original = getattr(module, name)

    @functools.wraps(original)
    def fake(*args, **kwargs):
        raise error

    monkeypatch.setattr(module, name, fake)


def run_installed(*args, lang=None, **kwargs):
    """
    The installed ``imgw`` in its own process, without IMGW_STORE_ROOT or network.

    ``lang`` is the IMGW_LANG of the process (unset by default).
    """
    command = [str(INSTALLED)] if INSTALLED.exists() else [sys.executable, "-m"]
    if not INSTALLED.exists():
        command.append("imgwtools.cli.main")
    dead = "http://127.0.0.1:9"
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("IMGW_STORE_ROOT", "IMGW_LANG")
    }
    env |= {"HTTP_PROXY": dead, "HTTPS_PROXY": dead, "NO_PROXY": ""}
    if lang is not None:
        env["IMGW_LANG"] = lang
    return subprocess.run(
        [*command, *map(str, args)], env=env, timeout=120, check=False, **kwargs
    )


def shown(text):
    """Rendered help as one line of words (rich wraps lines and draws borders)."""
    return " ".join(text.replace("│", " ").split())


def tree(command, path=("imgw",)):
    """Words and Click command of every command of the ``imgw`` tree."""
    yield path, command
    for name, sub in getattr(command, "commands", {}).items():
        yield from tree(sub, (*path, name))


# --- rejestracja, help i flagi ---------------------------------------------------------------


def test_cli_catalog_registers_every_group_and_command_of_the_catalog():
    root = typer.main.get_command(app)
    for group, description in CATALOG["groups"].items():
        assert root.commands[group].help == description
        assert list(click_command(group).commands) == [
            spec.name.split(" ", 1)[1]
            for spec in data_commands()
            if spec.name.split()[0] == group
        ]
    shown = " ".join(invoke("--help").output.replace("│", " ").split())
    for group, description in CATALOG["groups"].items():
        assert f"{group} {description}" in shown


@pytest.mark.parametrize("spec", data_commands(), ids=lambda spec: spec.name)
def test_cli_catalog_command_help_and_flags_are_the_catalog(spec):
    command = click_command(spec.name)
    assert command.help == spec.description
    params = {param.name: param for param in command.params}
    reserved = {"schema"} | ({"check"} if spec.check is not None else set())
    assert set(params) == {option.name for option in spec.options} | reserved
    for option in spec.options:
        param = params[option.name]
        assert param.opts == [option.flag, *option.aliases]
        assert param.help == option.help
        if option.type == "bool":
            negative = [f"--no-{option.flag[2:]}"] if option.default is True else []
            assert param.secondary_opts == negative
        assert (param.envvar == "IMGW_STORE_ROOT") == (option.name == "root")
    shown = " ".join(invoke(*spec.name.split(), "--help").output.split())
    assert spec.description in shown
    assert ("Opcje wymagane" in shown) == any(o.required for o in spec.options)


@pytest.mark.parametrize(("command", "options"), SAMPLES)
def test_cli_catalog_passes_the_given_option_text_to_the_dispatcher(
    monkeypatch, command, options
):
    calls = []

    def dispatcher(check):
        def dispatch(name, /, *, options, on_progress, on_notice, cancel):
            calls.append((name, check, options))
            return CommandResult(name, check, "ok", None, ())

        return dispatch

    monkeypatch.setattr(_dispatch, "run_command", dispatcher(False))
    monkeypatch.setattr(_dispatch, "check_command", dispatcher(True))
    variants = [
        (argv(command, options), False),
        (argv(command, options, aliases=True), False),
    ]
    if SPECS[command].check is not None:
        variants.append(([*argv(command, options), "--check"], True))
    for args, check in variants:
        result = invoke(*args)
        assert result.exit_code == 0, (args, result.output)
        name, checked, passed = calls.pop()
        assert (name, checked) == (command, check)
        # Click validates nothing: the raw text of each given option reaches the catalog.
        assert all(
            isinstance(value, str | bool)
            or all(isinstance(item, str) for item in value)
            for value in passed.values()
        )
        assert validate_command(command, options=passed) == validate_command(
            command, options=options
        )


@pytest.mark.parametrize("spec", data_commands(), ids=lambda spec: spec.name)
def test_cli_catalog_schema_flag_prints_the_commands_schema_envelope(spec):
    # Without the required options: a run would fail validation instead of printing.
    printed = invoke(*spec.name.split(), "--schema")
    expected = invoke("commands", "schema", "--command", spec.name)
    assert printed.stdout == expected.stdout
    assert envelope(printed)["result"] == json.loads(
        json.dumps(command_schema(spec.name))
    )


# --- język: IMGW_LANG i --lang ---------------------------------------------------------------


def test_cli_help_of_every_command_is_polish_by_default():
    for path, _ in tree(typer.main.get_command(app)):
        text = shown(invoke(*path[1:], "--help").output)
        assert f"Użycie: {' '.join(path)} [OPCJE]" in text, path
        assert "Pokaż pomoc i zakończ." in text, path
        for english in ("Usage:", "Show this message", "[OPTIONS]", "COMMAND", "ARGS"):
            assert english not in text, path
    store_sync = shown(invoke("store", "sync", "--help").output)
    for element in (
        "Opcje wymagane",
        "─ Opcje ─",
        "[zmienna środowiskowa: IMGW_STORE_ROOT]",
        "ŚCIEŻKA",
    ):
        assert element in store_sync
    listed = shown(invoke("--help").output)
    assert "─ Komendy ─" in listed
    assert "Użycie: imgw [OPCJE] KOMENDA [ARGUMENTY]..." in listed
    assert "─ Argumenty ─" in shown(invoke("admin", "delete", "--help").output)


def test_cli_help_follows_imgw_lang_en():
    spec = SPECS["store sync"]

    printed = run_installed(
        "store", "sync", "--help", lang="en", capture_output=True, text=True
    )
    listed = run_installed("--help", lang="en", capture_output=True, text=True)

    assert printed.returncode == 0, printed.stderr
    text = shown(printed.stdout)
    assert spec.description_en in text
    for option in spec.options:
        assert option.help_en in text, option.name
    for element in (
        "Usage: imgw store sync [OPTIONS]",
        "─ Options ─",
        "─ Required options ─",
        "Show this message and exit.",
        "[env var: IMGW_STORE_ROOT]",
        "PATH",
    ):
        assert element in text
    for word in ("Użycie", "Opcje", "Pokaż", "zmienna"):
        assert word not in text
    roots = shown(listed.stdout)
    assert "─ Commands ─" in roots
    assert "Usage: imgw [OPTIONS] COMMAND [ARGS]..." in roots
    for group, description in command_schema(lang="en")["groups"].items():
        assert f"{group} {description}" in roots


def test_cli_imgw_lang_outside_pl_and_en_ends_every_call_with_validation_error(
    monkeypatch,
):
    result = run_installed("datasets", "list", lang="de", capture_output=True)
    assert (result.returncode, result.stdout) == (2, b"")
    line = json.loads(result.stderr.decode("utf-8").splitlines()[-1])
    assert line["code"] == "validation_error"
    assert line["details"] == {
        "option": "IMGW_LANG",
        "value": "de",
        "allowed": ["en", "pl"],
    }
    # The language is checked before Click parses anything, help included.
    monkeypatch.setattr(settings, "lang", "english")
    for args in (("--help",), ("version",), ("admin", "keys"), ("store", "info")):
        document = error_line(invoke(*args), "validation_error")
        assert document["details"]["option"] == "IMGW_LANG"


def test_cli_lang_flag_and_imgw_lang_choose_the_commands_schema_language():
    english = json.loads(json.dumps(command_schema(lang="en")))
    polish = json.loads(json.dumps(command_schema()))

    assert envelope(invoke("commands", "schema", "--lang", "en"))["result"] == english
    by_variable = invoke("commands", "schema", env={"IMGW_LANG": "en"})
    assert envelope(by_variable)["result"] == english
    flag_first = invoke("commands", "schema", "--lang", "pl", env={"IMGW_LANG": "en"})
    assert envelope(flag_first)["result"] == polish
    flag = run_installed("store", "sync", "--schema", lang="en", capture_output=True)
    assert flag.returncode == 0, flag.stderr
    assert json.loads(flag.stdout)["result"] == json.loads(
        json.dumps(command_schema("store sync", lang="en"))
    )


# --- wyjście ---------------------------------------------------------------------------------


def test_cli_catalog_object_and_list_commands_print_the_run_command_envelope(
    fixture_root, offline
):
    root = fixture_root
    cases = [
        (("store", "info", "--root", root), "store info", {"root": root}),
        (
            ("store", "scan", "-r", root, "-k", "archive", "--limit", 2, "--offset", 1),
            "store scan",
            {"root": root, "kind": "archive", "limit": 2, "offset": 1},
        ),
        (
            (
                "series",
                "read",
                "-r",
                root,
                "-d",
                "hydro/dobowe",
                "-s",
                RABA,
                "--variables",
                "H",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-03",
            ),
            "series read",
            {
                "root": root,
                "dataset": DAILY,
                "station": RABA,
                "variables": ["H"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            },
        ),  # fmt: skip
        (("datasets", "list", "-k", "meteo"), "datasets list", {"kind": "meteo"}),
    ]
    for args, command, options in cases:
        expected = run_command(command, options=options).to_json(
            root=options.get("root")
        )
        assert envelope(invoke(*args)) == expected


def test_cli_catalog_series_build_prints_the_envelope_of_the_same_run(
    tmp_path, fixture_root, frozen
):
    cli_root, api_root = tmp_path / "cli", tmp_path / "api"
    shutil.copytree(fixture_root, cli_root)
    shutil.copytree(fixture_root, api_root)
    printed = envelope(invoke("series", "build", "-r", cli_root, "-d", PRECIP))
    expected = run_command(
        "series build", options={"root": api_root, "dataset": PRECIP}
    ).to_json(root=api_root)
    assert printed == expected
    assert printed["result"]["status"] == "created"
    assert snapshot(cli_root) == snapshot(api_root)


def test_cli_catalog_check_flag_prints_the_plan_without_writing(
    tmp_path, fixture_root, offline, frozen
):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    before = stamps(root)
    printed = envelope(invoke("series", "build", "-r", root, "-d", PRECIP, "--check"))
    assert stamps(root) == before
    expected = check_command("series build", options={"root": root, "dataset": PRECIP})
    assert printed == expected.to_json(root=root)
    assert (printed["check"], printed["result"]["schema"]) == (True, "imgw-plan/1")


def test_cli_catalog_streams_print_only_the_data_lines(tmp_path, fixture_root, offline):
    version = store.current_version(fixture_root, slot=O2001).version
    cases = [
        (("store", "export", "--version", version), store.export_archive(version)),
        (
            ("store", "export", "--version", version, "-f", "jsonl"),
            store.export_archive(version, format="jsonl"),
        ),
        (
            ("series", "export", "-r", fixture_root, "-d", DAILY, "-s", RABA),
            store.export_series(root=fixture_root, dataset=DAILY, station=RABA),
        ),
    ]
    for args, lines in cases:
        result = invoke(*args)
        assert result.exit_code == 0, result.output
        # stdout_bytes: Result.stdout folds the CSV CRLF row ends to LF.
        assert result.stdout_bytes == "".join(lines).encode("utf-8")
        assert b"imgw-result/1" not in result.stdout_bytes
        assert "Informacja: Źródłem pochodzenia danych jest" in result.stderr
    target = tmp_path / "opad.csv"
    printed = envelope(invoke("store", "export", "--version", version, "-p", target))
    assert printed["result"] == str(target)
    assert target.read_bytes() == "".join(store.export_archive(version)).encode()


def test_cli_catalog_prints_each_distinct_notice_once(monkeypatch, tmp_path):
    received = []
    original = store.sync_store

    @functools.wraps(original)
    def sync_store(root, /, *, on_notice, **kwargs):
        for level, code, text in (
            ("info", "license_terms", "Licencja IMGW-PIB"),
            ("info", "license_terms", "Licencja IMGW-PIB"),
            ("info", "license_terms", "Inny tekst"),
            ("warning", "other", "Licencja IMGW-PIB"),
        ):
            received.append(Notice(level, code, text))
            on_notice(received[-1])
        return SyncReport((), (), cancelled=False)

    monkeypatch.setattr(store, "sync_store", sync_store)
    result = invoke("store", "sync", "-r", tmp_path, "-d", DAILY, "-y", 2024)
    assert len(received) == 4
    assert len(envelope(result)["notices"]) == 3
    assert result.stderr.count("Informacja: Licencja IMGW-PIB") == 1
    assert result.stderr.count("Informacja: Inny tekst") == 1
    assert result.stderr.count("Ostrzeżenie: Licencja IMGW-PIB") == 1


# --- --root z IMGW_STORE_ROOT ----------------------------------------------------------------


def test_cli_catalog_root_falls_back_to_imgw_store_root(
    monkeypatch, tmp_path, fixture_root, offline
):
    env = {"IMGW_STORE_ROOT": str(fixture_root)}
    info = run_command("store info", options={"root": fixture_root})
    assert envelope(invoke("store", "info", env=env)) == info.to_json(root=fixture_root)
    other = tmp_path / "inny"
    flagged = envelope(invoke("store", "info", "-r", other, env=env))
    assert flagged["result"]["root"] == str(other)
    found = run_command(
        "stations find",
        options={"source": "store", "root": fixture_root, "query": "raba"},
    )
    printed = invoke("stations", "find", "--source", "store", "-q", "raba", env=env)
    assert envelope(printed) == found.to_json(root=fixture_root)
    calls = []

    def dispatch(name, /, *, options, on_progress, on_notice, cancel):
        calls.append(options)
        return CommandResult(name, False, "ok", None, ())

    monkeypatch.setattr(_dispatch, "run_command", dispatch)
    # A live search rejects root, so the environment default does not apply to it.
    assert invoke("stations", "find", "-q", "raba", env=env).exit_code == 0
    assert calls == [{"query": "raba"}]


# --- błędy i kody wyjścia --------------------------------------------------------------------


def _validation(tmp_path, root, router, monkeypatch):
    return ["pmaxtp", "fetch", "--latitude", "1", "--longitude", "1"]


def _not_found(tmp_path, root, router, monkeypatch):
    return ["pmaxtp", "read", "-r", root, "--ind-x", "1", "--ind-y", "1"]


def _conflict(tmp_path, root, router, monkeypatch):
    busy = tmp_path / "zajety"
    busy.mkdir()
    (busy / "notatki.txt").write_text("nie magazyn", encoding="utf-8")
    return ["store", "init", "-r", busy]


def _source_unavailable(tmp_path, root, router, monkeypatch):
    router.get(f"{IMGW_API_URL}/hydro").mock(return_value=httpx.Response(503))
    return ["current", "hydro"]


def _missing_dependency(tmp_path, root, router, monkeypatch):
    copy = tmp_path / "store"
    shutil.copytree(root, copy)
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    return ["series", "build", "-r", copy, "-d", PRECIP]


def _data_error(tmp_path, root, router, monkeypatch):
    copy = tmp_path / "store"
    shutil.copytree(root, copy)
    version = store.current_version(copy, slot=O2001).version
    version.write_bytes(b"uszkodzone archiwum")
    return ["store", "export", "--version", version]


def _store_unavailable(tmp_path, root, router, monkeypatch):
    return ["series", "build", "-r", tmp_path, "-d", DAILY]


def _io_error(tmp_path, root, router, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("użytkownik root pomija prawa dostępu do katalogów")
    locked = tmp_path / "tylko-odczyt"
    locked.mkdir()
    locked.chmod(0o555)
    return [
        "datasets",
        "download",
        "-d",
        "hydro/dobowe",
        "-y",
        2024,
        "-o",
        locked / "x",
    ]


def _forbidden(tmp_path, root, router, monkeypatch):
    # No CLI path refuses a write itself; a refusal raised below reaches exit 12.
    refusal = IMGWError(
        "Write refused", code="forbidden", details={"reason": "writes_disabled"}
    )
    raising(monkeypatch, store, "store_info", refusal)
    return ["store", "info", "-r", root]


def _internal_error(tmp_path, root, router, monkeypatch):
    raising(monkeypatch, store, "store_info", RuntimeError("awaria testowa"))
    return ["store", "info", "-r", root]


ERRORS = {
    "validation_error": _validation,
    "not_found": _not_found,
    "conflict": _conflict,
    "source_unavailable": _source_unavailable,
    "missing_dependency": _missing_dependency,
    "data_error": _data_error,
    "store_unavailable": _store_unavailable,
    "io_error": _io_error,
    "forbidden": _forbidden,
    "internal_error": _internal_error,
}


@pytest.mark.parametrize(("code", "case"), ERRORS.items(), ids=list(ERRORS))
def test_cli_catalog_error_leaves_stdout_empty_and_ends_stderr_with_json(
    code, case, tmp_path, fixture_root, monkeypatch
):
    with respx.mock(assert_all_called=False) as router:
        args = case(tmp_path, fixture_root, router, monkeypatch)
        result = invoke(*args)
    error_line(result, code)


@pytest.mark.parametrize(
    ("args", "option"),
    [
        (("datasets", "list", "--colour", "red"), "colour"),
        (("store", "check", "-r", "/r", "-d", DAILY, "-y", 2024, "--check"), "check"),
        (("datasets", "files", "-d", DAILY, "--years"), "years"),
        (("store", "sync", "--series=tak"), "series"),
        (("stor",), None),
        (("store",), None),
        ((), None),
        (("store", "info", "nadmiarowy"), None),
    ],
    ids=str,
)
def test_cli_catalog_click_syntax_error_is_a_validation_error_line(args, option):
    document = error_line(invoke(*args), "validation_error")
    assert document["details"].get("option") == option
    assert document["details"]["click"]


def test_cli_catalog_unknown_flag_is_reported_in_polish():
    document = error_line(
        invoke("datasets", "list", "--colour", "red"), "validation_error"
    )
    assert document["detail"].startswith(
        "Nieznana opcja --colour komendy imgw datasets list"
    )
    assert document["details"]["click"] == "No such option: --colour"


@pytest.mark.parametrize(
    ("failing", "status"), [((H2024,), "partial"), ((H2023, H2024), "failed")]
)
def test_cli_catalog_sync_with_failed_items_prints_the_envelope_and_exits_10_or_11(
    tmp_path, imgw, failing, status
):
    root = tmp_path / "store"
    store.init_store(root)
    imgw.publish(H2023, V1, archive_bytes(H2023))
    imgw.publish(H2024, V3, NEW)
    for archive in failing:
        imgw.router.get(archive.url).mock(return_value=httpx.Response(500))
    result = invoke(
        "store", "sync", "-r", root, "-d", DAILY, "-y", "2023-2024", "--no-series"
    )
    assert (
        result.exit_code == EXIT_CODES[status] == {"partial": 10, "failed": 11}[status]
    )
    printed = json.loads(result.stdout)
    assert printed["status"] == status
    failed = [item for item in printed["result"]["items"] if item["status"] == "failed"]
    assert [item["error_code"] for item in failed] == ["source_unavailable"] * len(
        failing
    )


def test_cli_catalog_first_ctrl_c_prints_the_partial_report_and_exits_130(
    monkeypatch, tmp_path
):
    seen = []
    original = store.build_series

    @functools.wraps(original)
    def build_series(root, /, *, dataset, on_progress, on_notice, cancel):
        before = cancel()
        signal.raise_signal(signal.SIGINT)
        seen.append((before, cancel()))
        return SeriesReport("cancelled", None, 0, (), ())

    monkeypatch.setattr(store, "build_series", build_series)
    handler = signal.getsignal(signal.SIGINT)
    result = invoke("series", "build", "-r", tmp_path, "-d", DAILY)
    assert seen == [(False, True)]
    assert result.exit_code == EXIT_CODES["cancelled"] == 130
    printed = json.loads(result.stdout)
    assert (printed["status"], printed["result"]["status"]) == (
        "cancelled",
        "cancelled",
    )
    assert "Ostrzeżenie: Przerwanie (Ctrl+C)" in result.stderr
    assert signal.getsignal(signal.SIGINT) is handler


def test_cli_catalog_second_ctrl_c_aborts_with_the_cancelled_error_line(
    monkeypatch, tmp_path
):
    original = store.build_series

    @functools.wraps(original)
    def build_series(root, /, **kwargs):
        signal.raise_signal(signal.SIGINT)
        signal.raise_signal(signal.SIGINT)
        raise AssertionError("drugie Ctrl+C musi przerwać operację")

    monkeypatch.setattr(store, "build_series", build_series)
    result = invoke("series", "build", "-r", tmp_path, "-d", DAILY)
    error_line(result, "cancelled")


# --- zainstalowany imgw ----------------------------------------------------------------------


def test_cli_catalog_installed_imgw_reports_the_error_line_of_the_spec():
    result = run_installed(
        "pmaxtp", "fetch", "--latitude", "1", "--longitude", "1", capture_output=True
    )
    assert (result.returncode, result.stdout) == (2, b"")
    assert result.stderr.decode("utf-8").splitlines()[-1] == (
        '{"code":"validation_error","detail":"Latitude 1.0 is outside Poland '
        '(49.0–55.0)","details":{"option":"latitude","value":1.0}}'
    )
    unknown = run_installed("store", "info", "--colour", "red", capture_output=True)
    assert unknown.returncode == 2
    assert json.loads(unknown.stderr.splitlines()[-1])["code"] == "validation_error"


def test_cli_catalog_installed_imgw_prints_the_envelope_of_run_command():
    result = run_installed(
        "datasets", "list", "-k", "meteo", "--limit", 2, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    expected = run_command("datasets list", options={"kind": "meteo", "limit": 2})
    assert json.loads(result.stdout) == expected.to_json()


def test_cli_catalog_installed_imgw_stream_ends_quietly_when_the_reader_leaves(
    fixture_root,
):
    version = store.current_version(
        fixture_root, slot=f"archive:{DAILY}:2024/codz_2024.zip"
    ).version
    reader, writer = os.pipe()
    os.close(reader)  # like ``| head`` that already exited: every write gets EPIPE
    try:
        result = run_installed(
            "store", "export", "--version", version, stdout=writer,
            stderr=subprocess.PIPE, text=True,
        )  # fmt: skip
    finally:
        os.close(writer)
    assert result.returncode == 0, result.stderr
    assert all(
        line.startswith(("Informacja:", "[")) for line in result.stderr.splitlines()
    )
