"""Contract: ``imgw`` prints the envelope ``run_command`` returns for every step.

A scenario of a store and a project (spec §13.3: store, series, PMAXTP, flat
download and project commands) runs twice on identical fresh inputs in the same
directory, at a frozen clock and against the same recorded IMGW: through
``run_command`` and through the ``imgw`` CLI. Every printed line is the
``imgw-result/1`` envelope ``CommandResult.to_json(root)`` of the same step, the
exit code follows its status (§13.6), trees and HTTP traffic are identical, and
every slot of a result names a version ``current_version`` finds (§13.7). The
installed ``imgw`` executable reads offline in its own process like the Python
API, and two processes building one series publish it once.
"""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from imgwtools import (
    ERROR_CODES,
    add_project_task,
    command_schema,
    current_version,
    download_project,
    init_project,
    run_command,
)
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
    canonical,
    cli_words,
    envelope_errors,
    load,
    run_imgw,
    schema_errors,
    slots,
    snapshot,
    stamps,
    version_slot,
)

EXIT_CODES = command_schema()["exit_codes"]
TASK = {"dataset": DAILY, "stations": [RABA], "years": [2024]}


def scenario(work: Path, imgw, run) -> list[dict]:
    """Store, series, PMAXTP, download and project steps; ``run`` gives envelopes."""
    store, project = work / "store", work / "project"
    selection = {"root": store, "datasets": [DAILY], "years": [2024]}
    steps = [run("store init", {"root": store})]
    imgw.publish(H2024, V1, OLD)
    steps.append(run("store check", {**selection, "plan": work / "plan.json"}))
    imgw.publish(H2024, V2, OLD)  # republished after the check: a stale plan
    steps.append(run("store sync", {"root": store, "plan": work / "plan.json"}))
    steps.append(run("store check", {**selection, "plan": work / "fresh.json"}))
    steps.append(run("store sync", {"root": store, "plan": work / "fresh.json"}))
    imgw.publish(H2024, V3, NEW)
    steps.append(run("store sync", {**selection, "series": False}))
    steps.append(run("series build", {"root": store, "dataset": DAILY}))
    imgw.publish_catalog_sources()
    steps.append(run("store catalog", {"root": store}))
    steps.append(
        run(
            "series export",
            {
                "root": store,
                "version": steps[-2]["result"]["version"],  # relative to the root
                "station": RABA,
                "path": work / "raba.csv",
                "variables": ["H", "Q"],
            },
        )
    )
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    point = {"latitude": 52.23, "longitude": 21.01, "method": "POT"}
    steps.append(run("pmaxtp sync", {"root": store, **point}))
    steps.append(run("pmaxtp read", {"root": store, "ind_x": 751, "ind_y": 317}))
    steps.append(
        run("datasets download", {"dataset": DAILY, "years": [2024], "output": work})
    )
    folder = {"project_dir": project}
    steps.append(run("project init", {**folder, "store_dir": store}))
    task = {"name": "raba", "command": "series select", "options": TASK}
    steps.append(run("project add", {**folder, **task}))
    steps.append(run("project check", folder))
    steps.append(run("project download", folder))
    steps.append(run("project status", folder))
    steps.append(run("project verify", folder))
    return steps


def test_imgw_scenario_prints_the_envelopes_of_run_command_and_writes_alike(
    tmp_path, cli, imgw, frozen
):
    work = tmp_path / "work"

    def python(command, options):
        envelope = run_command(command, options=options)
        return envelope.to_json(root=options.get("root"))

    def printed(command, options):
        result = cli(*cli_words(command, options))
        document = json.loads(result.stdout)
        assert result.exit_code == EXIT_CODES[document["status"]], result.output
        return document

    runs = []
    for run in (python, printed):
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()
        start = len(imgw.router.calls)
        steps = scenario(work, imgw, run)
        runs.append((steps, snapshot(work), imgw.traffic(start)))
    (returned, tree, traffic), (shown, cli_tree, cli_traffic) = runs

    assert [canonical(step) for step in shown] == [canonical(s) for s in returned]
    assert cli_tree == tree
    assert cli_traffic == traffic
    for step in returned:
        assert envelope_errors(step) == [], step["command"]
        for slot in slots(step["result"]):
            wanted = version_slot(slot)
            assert current_version(work / "store", slot=wanted).slot == wanted

    def statuses(step):
        return [item["status"] for item in step["result"]["items"]]

    check, stale, fresh, synced, newer = returned[1:6]
    assert statuses(check) == statuses(fresh) == ["missing"]
    # The plan file is the plan of the envelope (one imgw-plan/1 document).
    assert load(work / "fresh.json") == fresh["result"]
    assert schema_errors(fresh["result"], "imgw-plan/1") == []
    assert statuses(stale) == ["stale_plan"]
    assert stale["status"] == "failed"  # no item done: exit code 11
    assert stale["result"]["series"][0]["status"] == "failed"
    assert statuses(synced) == statuses(newer) == ["created"]
    assert [s["status"] for s in synced["result"]["series"]] == ["created"]
    assert newer["result"]["series"] == []
    assert [returned[i]["result"]["status"] for i in (6, 7, 9)] == ["created"] * 3
    assert returned[8]["result"] == str(work / "raba.csv")
    assert statuses(returned[11]) == ["downloaded"]
    assert (
        returned[11]["result"]["items"][0]["slot"]
        == f"archive:{DAILY}:2024/codz_2024.zip"
    )
    assert [a["status"] for a in returned[14]["result"]["actions"]] == ["missing"]
    assert [step["result"]["tasks"] for step in returned[15:]] == [
        {"raba": "current"}
    ] * 3
    # 4 archive versions (2 × codz_2024, 2 station lists), 2 series, catalog, cell
    assert sum(path.endswith(".meta.json") for path in tree) == 8


def test_installed_imgw_prints_the_envelopes_of_run_command_offline(
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
    target = tmp_path / "raba.csv"
    before = stamps(root)

    for command, options in (
        ("store info", {"root": root}),
        ("store info", {"root": tmp_path / "brak"}),
        ("store scan", {"root": corrupt, "kind": "problem"}),
        (
            "series export",
            {"root": root, "dataset": DAILY, "station": RABA, "path": target},
        ),
        ("project verify", {"project_dir": project}),
    ):
        printed = run_imgw(*cli_words(command, options))
        exported = target.read_bytes() if target.exists() else None
        target.unlink(missing_ok=True)

        expected = run_command(command, options=options).to_json(
            root=options.get("root")
        )

        document = json.loads(printed.stdout)
        assert printed.stdout.count("\n") == 1
        assert envelope_errors(document) == []
        assert canonical(document) == canonical(expected)
        assert exported == (target.read_bytes() if target.exists() else None)
        target.unlink(missing_ok=True)
    assert stamps(root) == before

    refused = run_imgw(
        "store", "check", "--root", root, "--datasets", DAILY, check=False
    )
    line = json.loads(refused.stderr.splitlines()[-1])
    assert (refused.returncode, refused.stdout) == (
        ERROR_CODES["validation_error"].exit_code,
        "",
    )
    assert schema_errors(line, "cli-error") == []
    assert (line["code"], line["details"]["option"]) == ("validation_error", "years")


def test_two_imgw_processes_building_one_series_publish_it_once(tmp_path, fixture_root):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    slot = root / "series" / "versions" / "meteo_precip_daily"
    before = {path.name for path in slot.iterdir()}

    def build(_):
        return run_imgw("series", "build", "--root", root, "--dataset", PRECIP)

    with ThreadPoolExecutor(2) as pool:
        envelopes = [json.loads(result.stdout) for result in pool.map(build, range(2))]

    assert [envelope_errors(envelope) for envelope in envelopes] == [[], []]
    assert [envelope["status"] for envelope in envelopes] == ["ok", "ok"]
    reports = [envelope["result"] for envelope in envelopes]
    assert sorted(report["status"] for report in reports) == ["created", "reused"]
    assert len({report["version"] for report in reports}) == 1
    (new,) = {path.name for path in slot.iterdir()} - before
    assert Path(reports[0]["version"]).parent.name == new
    assert not any((root / ".incoming").iterdir())
