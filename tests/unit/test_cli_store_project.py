"""CLI groups store/series/pmaxtp/project: catalog help, one dispatcher, CLI = API (§10)."""

import hashlib
import json
import shlex
import shutil
import signal
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
import typer
from typer.testing import CliRunner

from imgwtools import commands, project, store
from imgwtools.cli import _dispatch
from imgwtools.cli.main import app
from imgwtools.commands import (
    check_command,
    data_commands,
    format_command,
    validate_command,
)
from imgwtools.core.url_builder import IMGW_PUBLIC_DATA_URL
from imgwtools.datasets import archive_files
from imgwtools.store import catalog, pmaxtp, series, sync, writer
from imgwtools.store.types import (
    Notice,
    OperationResult,
    ProjectReport,
    SeriesReport,
    SyncReport,
)
from imgwtools.testing import build_fixture_store
from tests.unit.test_commands import SAMPLES

RUNNER = CliRunner()
DAILY = "pl.imgw.hydro_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
STATION = "149190310"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDINGS = {
    row["case"]: row
    for row in json.loads((FIXTURES / "recordings.json").read_text(encoding="utf-8"))[
        "interactions"
    ]
}
H2024 = archive_files(DAILY, years=[2024])[0]
GROUPS = ("store", "series", "pmaxtp", "project")


def invoke(*args):
    return RUNNER.invoke(app, [str(arg) for arg in args])


def snapshot(root):
    """Relative path → SHA-256 of every file (``None`` for directories)."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file()
        else None
        for path in sorted(root.rglob("*"))
    }


def mtimes(root):
    return {path: path.stat().st_mtime_ns for path in sorted(root.rglob("*"))}


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("cli") / "store").root


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 9, 0, tzinfo=UTC).astimezone(tz)

    for module in (writer, series, catalog, sync, pmaxtp, commands, project):
        monkeypatch.setattr(module, "datetime", Frozen)


@pytest.fixture
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("komenda nie może używać sieci")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def imgw():
    """IMGW answering the listing, HEAD and GET of ``codz_2024.zip`` and PMAXTP."""
    headers = RECORDINGS["hydro_head"]["headers"]
    content = (FIXTURES / "archives" / H2024.server_path).read_bytes()
    first = RECORDINGS["pmaxtp_pot_first"]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{IMGW_PUBLIC_DATA_URL}/dane_hydrologiczne/dobowe/2024/").mock(
            return_value=httpx.Response(
                200, text='<a href="codz_2024.zip">codz_2024.zip</a>'
            )
        )
        mock.head(H2024.url).mock(
            return_value=httpx.Response(
                200, headers={**headers, "Content-Length": str(len(content))}
            )
        )
        mock.get(H2024.url).mock(
            return_value=httpx.Response(200, headers=headers, content=content)
        )
        mock.get(first["url"]).mock(
            return_value=httpx.Response(first["status"], json=first["json"])
        )
        yield mock


def parity(work, prepare, cli, api):
    """Run the CLI and the Python API on identical fresh inputs; return both results."""
    prepare(work)
    cli_result = cli(work)
    cli_tree = snapshot(work)
    shutil.rmtree(work)
    prepare(work)
    api_result = api(work)
    assert snapshot(work) == cli_tree and cli_tree
    return cli_result, api_result


def output_json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def click_command(name):
    group = typer.main.get_command(app)
    for word in name.split():
        group = group.commands[word]  # type: ignore[attr-defined]
    return group


@pytest.mark.parametrize(
    "spec",
    [c for c in data_commands() if c.name.split()[0] in (*GROUPS, "fetch")],
    ids=lambda c: c.name,
)
def test_help_texts_and_flags_are_the_catalog(spec):
    command = click_command(spec.name)
    assert command.help == spec.description
    params = {param.name: param for param in command.params}
    assert set(params) == {option.name for option in spec.options} | {"check"}
    for option in spec.options:
        assert params[option.name].opts[0] == option.flag
        assert params[option.name].help == option.help
    shown = " ".join(
        invoke(*spec.name.split(), "--help").output.replace("│", " ").split()
    )
    assert spec.description in shown


def test_every_store_series_pmaxtp_project_command_is_registered():
    registered = {
        f"{group} {name}"
        for group in GROUPS
        for name in click_command(group).commands  # type: ignore[attr-defined]
    }
    assert registered == {
        c.name for c in data_commands() if c.name.split()[0] in GROUPS
    }


@pytest.mark.parametrize("check", [False, True], ids=["run", "check"])
@pytest.mark.parametrize(("command", "options"), SAMPLES)
def test_cli_passes_same_options_to_the_dispatcher(
    monkeypatch, offline, command, options, check
):
    calls = []

    def dispatch(name, /, *, options, on_progress, on_notice, cancel):
        calls.append((name, options))
        return Path("/wynik")

    monkeypatch.setattr(
        _dispatch, "check_command" if check else "run_command", dispatch
    )
    argv = shlex.split(format_command(command, options=options))[1:]
    result = RUNNER.invoke(app, argv + (["--check"] if check else []))
    assert result.exit_code == 0, result.output
    ((name, passed),) = calls
    assert name == command
    assert validate_command(command, options=passed) == validate_command(
        command, options=options
    )


def test_store_init_creates_the_same_store_as_python(tmp_path, frozen):
    cli, api = parity(
        tmp_path / "work",
        lambda work: work.mkdir(),
        lambda work: output_json(invoke("store", "init", "--root", work / "store")),
        lambda work: store.init_store(work / "store"),
    )
    assert cli == {"root": str(api.root), "schema": api.schema}


def test_series_build_matches_python_byte_for_byte(tmp_path, fixture_root, frozen):
    cli, api = parity(
        tmp_path / "work",
        lambda work: shutil.copytree(fixture_root, work / "store"),
        lambda work: output_json(
            invoke("series", "build", "--root", work / "store", "--dataset", PRECIP)
        ),
        lambda work: store.build_series(work / "store", dataset=PRECIP),
    )
    assert api.status == cli["status"] == "created"
    assert cli["version"] == str(api.version)


def test_store_check_plan_and_sync_match_python(tmp_path, imgw, frozen):
    def cli(work):
        root, plan = work / "store", work / "plan.json"
        checked = invoke(
            "store", "check", "--root", root, "--dataset", DAILY, "--years", "2024",
            "--plan", plan,
        )  # fmt: skip
        assert output_json(checked)["items"][0]["status"] == "missing"
        return output_json(invoke("store", "sync", "--root", root, "--plan", plan))

    def api(work):
        root, plan = work / "store", work / "plan.json"
        store.check_store(root, datasets=[DAILY], years=[2024]).to_json(plan)
        return store.sync_store(root, plan=plan)

    cli_report, api_report = parity(
        tmp_path / "work", lambda work: store.init_store(work / "store"), cli, api
    )
    assert [item["status"] for item in cli_report["items"]] == [
        item.status for item in api_report.items
    ]
    assert [s["status"] for s in cli_report["series"]] == ["created"]


def test_pmaxtp_sync_matches_python_and_prints_polish_notices(tmp_path, imgw, frozen):
    notices = []

    def cli(work):
        result = invoke(
            "pmaxtp", "sync", "--root", work / "store", "--method", "POT",
            "--lat", "52.23", "--lon", "21.01",
        )  # fmt: skip
        return result, output_json(result)

    (result, cli_data), api = parity(
        tmp_path / "work",
        lambda work: store.init_store(work / "store"),
        cli,
        lambda work: store.sync_pmaxtp(
            work / "store",
            method="POT",
            latitude=52.23,
            longitude=21.01,
            on_notice=notices.append,
        ),
    )
    assert (cli_data["status"], cli_data["ind_x"], cli_data["ind_y"]) == (
        api.status,
        api.ind_x,
        api.ind_y,
    )
    assert notices and all(notice.text in result.stderr for notice in notices)


def test_pmaxtp_sync_point_outside_grid_exits_1_in_polish(tmp_path):
    root = store.init_store(tmp_path / "store").root
    before = snapshot(root)
    with respx.mock() as mock:
        mock.get(url__startswith="https://powietrze.imgw.pl/tpmax-api/point/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {},
                    "error": "Brak pliku, pradopodobnie poza obszarem PL",
                },
            )
        )
        result = invoke(
            "pmaxtp", "sync", "--root", root, "--method", "POT",
            "--lat", "54.7104", "--lon", "20.4522",
        )  # fmt: skip
    assert result.exit_code == 1
    assert "Błąd: Punkt 54.7104, 20.4522 leży poza siatką PMAXTP" in result.stderr
    assert not result.stdout
    assert snapshot(root) == before


def test_series_export_runs_through_dispatcher_like_python(
    tmp_path, fixture_root, offline
):
    version = store.current_version(
        fixture_root, slot="series:pl.imgw.hydro_daily"
    ).version
    before = mtimes(fixture_root)
    cli, api = parity(
        tmp_path / "work",
        lambda work: work.mkdir(),
        lambda work: invoke(
            "series",
            "export",
            "--version",
            version,
            "--station",
            STATION,
            "--path",
            work / "raba.csv",
            "--variables",
            "H,Q",
        ),  # fmt: skip
        lambda work: store.export_series(
            version, station=STATION, path=work / "raba.csv", variables=["H", "Q"]
        ),
    )
    assert cli.exit_code == 0, cli.output
    assert cli.stdout.strip() == str(api)
    assert mtimes(fixture_root) == before


def test_project_commands_write_the_same_manifest_and_pins_as_python(
    tmp_path, fixture_root, imgw, frozen
):
    task = {"dataset": DAILY, "stations": STATION, "years": "2024"}

    def cli(work):
        folder = work / "project"
        for args in (
            ("init", "--store-dir", work / "store"),
            ("add", "--name", "raba", "--command", "series select",
             "--options", json.dumps(task)),
            ("download",),
            ("verify",),
        ):  # fmt: skip
            result = invoke("project", args[0], "--project-dir", folder, *args[1:])
            assert result.exit_code == 0, result.output
        return output_json(result)

    def api(work):
        folder = work / "project"
        project.init_project(folder, store_dir=work / "store")
        project.add_project_task(
            folder, name="raba", command="series select", options=task
        )
        project.download_project(folder)
        return project.verify_project(folder)

    cli_report, api_report = parity(
        tmp_path / "work",
        lambda work: shutil.copytree(fixture_root, work / "store"),
        cli,
        api,
    )
    assert cli_report["tasks"] == dict(api_report.tasks) == {"raba": "current"}


def test_check_flag_uses_check_command_and_writes_nothing(
    tmp_path, fixture_root, offline
):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    before = mtimes(root)
    result = invoke("series", "build", "--root", root, "--dataset", PRECIP, "--check")
    plan = output_json(result)
    assert mtimes(root) == before
    expected = check_command("series build", options={"root": root, "dataset": PRECIP})
    assert plan["schema"] == "imgw-plan/1"
    assert (
        plan["series_state"]
        == dict(expected.series_state)
        == {"meteo_precip_daily": "outdated"}
    )


def test_plan_inside_store_is_rejected_in_polish_without_writing(
    tmp_path, fixture_root, offline
):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    before = mtimes(root)
    result = invoke(
        "store", "check", "--root", root, "--dataset", DAILY, "--years", "2024",
        "--plan", root / "plan.json",
    )  # fmt: skip
    assert result.exit_code == 1
    assert "Błąd: Plan imgw-plan/1 musi być zapisany poza magazynem" in result.stderr
    assert mtimes(root) == before


def test_invalid_options_are_reported_in_polish(offline):
    missing = invoke("store", "info")
    assert missing.exit_code == 1
    assert "Brak wymaganej opcji root (--root)" in missing.stderr
    wrong = invoke("pmaxtp", "read", "--root", "/r", "--method", "XYZ")
    assert wrong.exit_code == 1
    assert "Nieprawidłowa wartość 'XYZ' opcji method" in wrong.stderr


def test_ctrl_c_requests_cancel_and_reports_partial_result(monkeypatch, tmp_path):
    seen = []

    def build_series(root, /, *, dataset, on_progress, on_notice, cancel):
        before = cancel()
        signal.raise_signal(signal.SIGINT)
        seen.append((before, cancel()))
        on_notice(Notice("warning", "cancelled", "Anulowano budowę szeregu"))
        return SeriesReport("cancelled", None, 0, (), ())

    monkeypatch.setattr(store, "build_series", build_series)
    handler = signal.getsignal(signal.SIGINT)
    result = invoke("series", "build", "--root", tmp_path, "--dataset", DAILY)
    assert seen == [(False, True)]
    assert result.exit_code == _dispatch.EXIT_CANCELLED
    assert json.loads(result.stdout)["status"] == "cancelled"
    assert "Ostrzeżenie: Anulowano budowę szeregu" in result.stderr
    assert "Operację anulowano (Ctrl+C); wynik jest częściowy" in result.stderr
    assert signal.getsignal(signal.SIGINT) is handler


def test_second_ctrl_c_aborts_immediately(monkeypatch, tmp_path):
    def build_series(root, /, **kwargs):
        signal.raise_signal(signal.SIGINT)
        signal.raise_signal(signal.SIGINT)
        raise AssertionError("drugie Ctrl+C musi przerwać operację")

    monkeypatch.setattr(store, "build_series", build_series)
    result = invoke("series", "build", "--root", tmp_path, "--dataset", DAILY)
    assert result.exit_code == _dispatch.EXIT_CANCELLED
    assert "Przerwano natychmiast (Ctrl+C)" in result.stderr
    assert not result.stdout


def test_series_build_failure_prints_report_and_exits_1(monkeypatch, tmp_path):
    def build_series(root, /, **kwargs):
        return SeriesReport("failed", None, 0, (), ("Sprzeczne dane stacji",))

    monkeypatch.setattr(store, "build_series", build_series)
    result = invoke("series", "build", "--root", tmp_path, "--dataset", DAILY)
    assert result.exit_code == _dispatch.EXIT_FAILED
    assert json.loads(result.stdout)["problems"] == ["Sprzeczne dane stacji"]
    assert "część pozycji zakończyła się niepowodzeniem" in result.stderr


@pytest.mark.parametrize(
    ("items", "series_status", "code"),
    [
        (("unchanged", "failed"), "created", _dispatch.EXIT_FAILED),
        (("unchanged", "stale_plan"), "reused", _dispatch.EXIT_FAILED),
        (("created",), "failed", _dispatch.EXIT_FAILED),
        (("created", "unchanged"), "created", 0),
    ],
)
def test_store_sync_exit_code_reflects_failed_items(
    monkeypatch, tmp_path, items, series_status, code
):
    report = SyncReport(
        tuple(
            OperationResult(f"archive:{i}", s, None, None) for i, s in enumerate(items)
        ),
        (SeriesReport(series_status, None, 0, (), ()),),
        cancelled=False,
    )
    monkeypatch.setattr(store, "sync_store", lambda root, /, **kwargs: report)
    result = invoke(
        "store", "sync", "--root", tmp_path, "--dataset", DAILY, "--years", "2024"
    )
    assert result.exit_code == code, result.output
    assert [item["status"] for item in json.loads(result.stdout)["items"]] == list(
        items
    )


def test_project_download_with_failed_task_exits_1(monkeypatch, tmp_path):
    report = ProjectReport(
        {"a": "current", "b": "failed"},
        (OperationResult("b:imgw-project.json", "failed", None, "brak danych"),),
        cancelled=False,
    )
    monkeypatch.setattr(project, "download_project", lambda folder, /, **kw: report)
    result = invoke("project", "download", "--project-dir", tmp_path)
    assert result.exit_code == _dispatch.EXIT_FAILED
    assert json.loads(result.stdout)["tasks"] == {"a": "current", "b": "failed"}


def test_identical_notices_are_printed_once_per_run(monkeypatch, tmp_path):
    received = []

    def sync_store(root, /, *, on_notice, **kwargs):
        for text in ("Licencja IMGW-PIB", "Licencja IMGW-PIB", "Inny tekst"):
            notice = Notice("info", "license_terms", text)
            received.append(notice)
            on_notice(notice)
        on_notice(Notice("warning", "other", "Licencja IMGW-PIB"))
        return SyncReport((), (), cancelled=False)

    monkeypatch.setattr(store, "sync_store", sync_store)
    result = invoke(
        "store", "sync", "--root", tmp_path, "--dataset", DAILY, "--years", "2024"
    )
    assert result.exit_code == 0, result.output
    assert len(received) == 3
    assert result.stderr.count("Informacja: Licencja IMGW-PIB") == 1
    assert result.stderr.count("Informacja: Inny tekst") == 1
    assert result.stderr.count("Ostrzeżenie: Licencja IMGW-PIB") == 1
