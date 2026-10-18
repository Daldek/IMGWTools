"""Contract: the real CLI and REST give the same paths and SHA-256 as the Python API.

Each side runs the same scenario on identical fresh inputs in the same directory, at
a frozen clock and against the same recorded IMGW (spec §10, IMGW-11): trees, printed
results and HTTP traffic must be identical. The installed ``imgw`` executable runs
offline commands without any network, and REST answers what the readers return.
"""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from typer.testing import CliRunner

from imgwtools import (
    add_project_task,
    build_catalog,
    build_series,
    check_project,
    check_store,
    current_version,
    download_project,
    export_series,
    get_project_status,
    init_project,
    init_store,
    iter_store,
    read_pmaxtp,
    read_series,
    read_series_index,
    store_info,
    sync_pmaxtp,
    sync_store,
    verify_project,
)
from imgwtools.api.main import app as rest_app
from imgwtools.cli.main import app as cli_app
from imgwtools.config import settings
from imgwtools.testing import build_fixture_store
from tests.contract.support import (
    DAILY,
    H2024,
    NEW,
    OLD,
    PRECIP,
    RABA,
    V1,
    V2,
    V3,
    snapshot,
    stamps,
)

RUNNER = CliRunner()
TOKEN = "kontrakt-token"
TASK = {"dataset": DAILY, "stations": [RABA], "years": [2024]}
POINT = ("--method", "POT", "--lat", "52.23", "--lon", "21.01")
CELL = ("--method", "POT", "--ind-x", "751", "--ind-y", "317")


def plain(value: object, root: Path | None = None) -> object:
    """JSON form of a public result (§10, T20); REST paths are relative to ``root``."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name), root) for f in fields(value)}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): plain(item, root) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [plain(item, root) for item in value]
    if isinstance(value, Path):
        return value.relative_to(root).as_posix() if root else str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def cli(*args: object, code: int = 0) -> object:
    """Run ``imgw …`` in-process; return the printed JSON or path (§10 exit codes)."""
    result = RUNNER.invoke(cli_app, [str(arg) for arg in args])
    assert result.exit_code == code, result.output
    text = result.stdout.strip()
    return json.loads(text) if text[:1] in "{[" else text


def traffic(imgw, start: int) -> list[tuple[str, str]]:
    return [
        (call.request.method, str(call.request.url))
        for call in imgw.router.calls[start:]
    ]


def scenario_cli(work: Path, imgw) -> list[object]:
    store, project = work / "store", work / "project"
    selection = ("--root", store, "--dataset", DAILY, "--years", "2024")
    steps = [cli("store", "init", "--root", store)]
    imgw.publish(H2024, V1, OLD)
    steps.append(cli("store", "check", *selection, "--plan", work / "plan.json"))
    imgw.publish(H2024, V2, OLD)  # republished after the check: stale plan
    steps.append(
        cli("store", "sync", "--root", store, "--plan", work / "plan.json", code=1)
    )
    steps.append(cli("store", "check", *selection, "--plan", work / "fresh.json"))
    steps.append(cli("store", "sync", "--root", store, "--plan", work / "fresh.json"))
    imgw.publish(H2024, V3, NEW)
    steps.append(cli("store", "sync", *selection, "--no-series"))
    steps.append(cli("series", "build", "--root", store, "--dataset", DAILY))
    imgw.publish_catalog_sources()
    steps.append(cli("store", "catalog", "--root", store))
    series = steps[-2]["version"]
    steps.append(
        cli(
            "series",
            "export",
            "--version",
            series,
            "--station",
            RABA,
            "--path",
            work / "raba.csv",
            "--variables",
            "H,Q",
        )  # fmt: skip
    )
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    steps.append(cli("pmaxtp", "sync", "--root", store, *POINT))
    steps.append(cli("pmaxtp", "read", "--root", store, *CELL))
    dir_ = ("--project-dir", project)
    steps.append(cli("project", "init", *dir_, "--store-dir", store))
    steps.append(
        cli(
            "project",
            "add",
            *dir_,
            "--name",
            "raba",
            "--command",
            "series select",
            "--options",
            json.dumps(TASK),
        )  # fmt: skip
    )
    steps.append(cli("project", "check", *dir_))
    steps.append(cli("project", "download", *dir_))
    steps.append(cli("project", "status", *dir_))
    steps.append(cli("project", "verify", *dir_))
    return steps


def scenario_api(work: Path, imgw) -> list[object]:
    store, project = work / "store", work / "project"
    steps: list[object] = [init_store(store)]
    imgw.publish(H2024, V1, OLD)
    plan = check_store(store, datasets=[DAILY], years=[2024])
    plan.to_json(work / "plan.json")
    steps.append(plan)
    imgw.publish(H2024, V2, OLD)
    steps.append(sync_store(store, plan=work / "plan.json"))
    fresh = check_store(store, datasets=[DAILY], years=[2024])
    fresh.to_json(work / "fresh.json")
    steps.append(fresh)
    steps.append(sync_store(store, plan=work / "fresh.json"))
    imgw.publish(H2024, V3, NEW)
    steps.append(sync_store(store, datasets=[DAILY], years=[2024], series=False))
    series = build_series(store, dataset=DAILY)
    steps.append(series)
    imgw.publish_catalog_sources()
    steps.append(build_catalog(store))
    assert series.version is not None
    steps.append(
        export_series(
            series.version, station=RABA, path=work / "raba.csv", variables=["H", "Q"]
        )
    )
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    steps.append(sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01))
    steps.append(read_pmaxtp(store, method="POT", ind_x=751, ind_y=317))
    steps.append(init_project(project, store_dir=store))
    steps.append(
        add_project_task(project, name="raba", command="series select", options=TASK)
    )
    steps.append(check_project(project))
    steps.append(download_project(project))
    steps.append(get_project_status(project))
    steps.append(verify_project(project))
    return [plain(step) for step in steps]


def test_cli_scenario_writes_and_prints_what_the_python_api_does(
    tmp_path, imgw, frozen
):
    work = tmp_path / "work"
    work.mkdir()
    start = len(imgw.router.calls)
    printed = scenario_cli(work, imgw)
    cli_tree, cli_traffic = snapshot(work), traffic(imgw, start)
    shutil.rmtree(work)
    work.mkdir()
    start = len(imgw.router.calls)
    returned = scenario_api(work, imgw)

    assert printed == returned
    assert snapshot(work) == cli_tree
    assert traffic(imgw, start) == cli_traffic

    def statuses(step):
        return [item["status"] for item in step["items"]]

    check, stale, fresh, synced, newer = returned[1:6]
    assert statuses(check) == statuses(fresh) == ["missing"]
    assert (
        statuses(stale) == ["stale_plan"] and stale["series"][0]["status"] == "failed"
    )
    assert statuses(synced) == statuses(newer) == ["created"]
    assert [s["status"] for s in synced["series"]] == ["created"] and not newer[
        "series"
    ]
    assert [returned[i]["status"] for i in (6, 7, 9)] == ["created"] * 3
    assert returned[8] == str(work / "raba.csv")
    assert [action["status"] for action in returned[13]["actions"]] == ["missing"]
    assert [step["tasks"] for step in returned[14:]] == [{"raba": "current"}] * 3
    # 4 archive versions (2 × codz_2024, 2 lists), 2 series, catalog, PMAXTP cell
    assert sum(path.endswith(".meta.json") for path in cli_tree) == 8


@pytest.fixture
def rest(monkeypatch):
    monkeypatch.setattr(settings, "store_writes_enabled", False)
    monkeypatch.setattr(settings, "store_write_token", None)
    monkeypatch.setattr(settings, "user_locations_dir", None)
    return TestClient(rest_app)


def test_rest_reads_answer_what_the_readers_return(
    tmp_path, fixture_root, rest, monkeypatch, imgw, frozen
):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    monkeypatch.setattr(settings, "store_root", root)

    info = rest.get("/api/v1/store/info").json()
    assert info == {**plain(store_info(root)), "root": "."}
    entries = rest.get("/api/v1/store/entries").json()
    assert entries == plain(list(iter_store(root)), root)

    version = current_version(root, slot="series:hydro_daily").version
    relative = version.relative_to(root).parent.as_posix()
    index = read_series_index(version)
    answered = rest.get("/api/v1/series/index", params={"version": relative}).json()
    assert answered["periods"] == plain(index.periods)
    assert answered["year_type"] == index.year_type == "hydrological"
    for code, station in index.stations.items():
        remote = answered["stations"][code]
        assert (remote["file"], remote["sha256"], remote["rows"]) == (
            station.file.as_posix(),
            station.sha256,
            station.rows,
        )
        for name, coverage in station.variables.items():
            expected = dict(plain(coverage))
            del expected["station"]  # the REST coverage omits the repeated station code
            assert remote["variables"][name] == expected
    records = rest.get(
        f"/api/v1/series/{RABA}",
        params={"version": relative, "variables": "H,Q", "start": "2024-02-01"},
    ).json()
    assert records == plain(
        list(
            read_series(
                version, station=RABA, variables=["H", "Q"], start=date(2024, 2, 1)
            )
        )
    )

    imgw.publish(H2024, V3, NEW)
    before = stamps(root)
    checked = rest.post(
        "/api/v1/store/check", json={"datasets": [DAILY], "years": [2024]}
    )
    assert checked.status_code == 200 and stamps(root) == before
    expected = check_store(root, datasets=[DAILY], years=[2024])
    document = json.loads(expected.to_json(tmp_path / "plan.json").read_text("utf-8"))
    assert checked.json() == {**document, "root": "."}


def test_rest_writes_match_python_api_tree_for_tree(
    tmp_path, fixture_root, rest, monkeypatch, imgw, frozen
):
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token", SecretStr(TOKEN))
    key = {"X-API-Key": TOKEN}
    root = tmp_path / "store"
    monkeypatch.setattr(settings, "store_root", root)
    imgw.publish(H2024, V1, OLD)

    init_store(root)
    synced = rest.post(
        "/api/v1/store/sync", json={"datasets": [DAILY], "years": [2024]}, headers=key
    )
    assert synced.status_code == 200, synced.text
    built = rest.post("/api/v1/series/build", json={"dataset": DAILY}, headers=key)
    rest_tree = snapshot(root)
    shutil.rmtree(root)

    init_store(root)
    report = sync_store(root, datasets=[DAILY], years=[2024])
    reused = build_series(root, dataset=DAILY)
    assert snapshot(root) == rest_tree
    assert synced.json() == plain(report, root)
    assert built.json() == plain(reused, root) and reused.status == "reused"

    (series,) = report.series
    assert series.version is not None
    exported = rest.post(
        "/api/v1/series/export",
        json={
            "version": series.version.relative_to(root).as_posix(),
            "station": RABA,
            "variables": ["H", "Q"],
            "year_type": "hydrological",
        },
        headers=key,
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "text/csv; charset=utf-8"
    local = export_series(
        series.version,
        station=RABA,
        path=tmp_path / "raba.csv",
        variables=["H", "Q"],
        year_type="hydrological",
    )
    assert exported.content == local.read_bytes()
    assert snapshot(root) == rest_tree


def imgw_executable() -> list[str]:
    script = Path(sys.executable).with_name("imgw")
    return (
        [str(script)]
        if script.exists()
        else [sys.executable, "-m", "imgwtools.cli.main"]
    )


def run_imgw(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    """The installed ``imgw`` in a separate process whose proxies lead nowhere."""
    dead = "http://127.0.0.1:9"
    env = {
        **os.environ,
        "HTTP_PROXY": dead,
        "HTTPS_PROXY": dead,
        "ALL_PROXY": dead,
        "NO_PROXY": "",
    }
    result = subprocess.run(
        [*imgw_executable(), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def test_installed_imgw_executable_reads_offline_like_the_python_api(
    tmp_path, fixture_root, imgw
):
    corrupt = build_fixture_store(tmp_path / "corrupt", variant="corrupt").root
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    project = tmp_path / "project"
    imgw.publish(H2024, V3, NEW)
    init_project(project, store_dir=root)
    add_project_task(project, name="raba", command="series select", options=TASK)
    assert download_project(project).tasks == {"raba": "current"}
    before = stamps(root)

    info = json.loads(run_imgw("store", "info", "--root", root).stdout)
    assert info == plain(store_info(root))
    problems = run_imgw("store", "scan", "--root", corrupt, "--kind", "problem")
    assert json.loads(problems.stdout) == plain(
        list(iter_store(corrupt, kind="problem"))
    )
    version = current_version(root, slot="series:hydro_daily").version
    target = tmp_path / "raba.csv"
    exported = run_imgw(
        "series", "export", "--version", version, "--station", RABA,
        "--path", target, "--variables", "H,Q",
    )  # fmt: skip
    assert exported.stdout.strip() == str(target)
    local = export_series(
        version, station=RABA, path=tmp_path / "api.csv", variables=["H", "Q"]
    )
    assert target.read_bytes() == local.read_bytes()
    verified = json.loads(
        run_imgw("project", "verify", "--project-dir", project).stdout
    )
    assert verified == plain(verify_project(project))
    assert verified["tasks"] == {"raba": "current"}
    assert stamps(root) == before

    absent = run_imgw("store", "info", "--root", tmp_path / "brak")
    assert json.loads(absent.stdout)["exists"] is False
    refused = run_imgw(
        "store", "check", "--root", root, "--dataset", DAILY, check=False
    )
    assert refused.returncode == 1
    assert "Błąd: Brak wymaganej opcji years (--years)" in refused.stderr


def test_two_imgw_processes_building_one_series_publish_it_once(tmp_path, fixture_root):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    slot = root / "series" / "versions" / "meteo_precip_daily"
    before = {path.name for path in slot.iterdir()}

    def build(_):
        return run_imgw("series", "build", "--root", root, "--dataset", PRECIP)

    with ThreadPoolExecutor(2) as pool:
        reports = [json.loads(result.stdout) for result in pool.map(build, range(2))]
    assert sorted(report["status"] for report in reports) == ["created", "reused"]
    assert len({report["version"] for report in reports}) == 1
    (new,) = {path.name for path in slot.iterdir()} - before
    assert Path(reports[0]["version"]).parent.name == new
    assert not any((root / ".incoming").iterdir())
