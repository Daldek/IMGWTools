"""Contract of the versioned store through the public API (spec §3–§9, §11, §12).

Offline end to end: the public ``imgwtools.testing`` store, the §11 JSON Schemas and
SHA-256 chains of every contract file, a read-only scan of unknown schemas and
problems, the HEAD → plan → stale/sync → series → coverage → catalog → CSV →
project → verify/restore state machine, cancellation and concurrent writers.
"""

import copy
import csv
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from imgwtools import (
    DownloadResult,
    IMGWCancelledError,
    IMGWDataError,
    IMGWStoreError,
    StorePlan,
    add_project_task,
    archive_files,
    build_catalog,
    build_series,
    check_catalog,
    check_pmaxtp,
    check_project,
    check_series,
    check_store,
    current_version,
    download_project,
    export_series,
    get_project_status,
    init_project,
    init_store,
    iter_store,
    normalize_archive,
    open_store,
    read_catalog,
    read_meta,
    read_series,
    read_series_index,
    store_info,
    summarize_coverage,
    sync_pmaxtp,
    sync_store,
    verify_project,
    write_archive,
)
from imgwtools.testing import build_fixture_store
from tests.contract.support import (
    DAILY,
    H2023,
    H2024,
    NEW,
    O2001,
    OLD,
    PRECIP,
    PROCESSED,
    RABA,
    SCHEMAS,
    SOURCE,
    V1,
    V2,
    V3,
    V4,
    archive_bytes,
    load,
    schema_errors,
    sha256,
    signal,
    snapshot,
    stamps,
)

ARCHIVE_SLOT = "archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
SLOT_DIR = Path("archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024")
# <label>_<sha8>: a date label (series may add "+<8 hex>") and the SHA prefix.
VERSION_DIR = re.compile(r"\d{4}-\d{2}-\d{2}(\+[0-9a-f]{8})?_[0-9a-f]{8}")


def contract_of(main: Path) -> str:
    return {
        "series.json": "imgw-series/1",
        "stations.geojson": "stations.geojson",
        "cell.json": "imgw-pmaxtp/1",
    }.get(main.name, "")


def assert_sidecar_contract(root: Path, sidecar: Path) -> dict[str, Any]:
    """Envelope §11.2, checksums of the main file, directory name and attribution §4."""
    meta: dict[str, Any] = load(sidecar)
    assert schema_errors(meta, "imgw-meta/1") == [], sidecar
    main = sidecar.with_name(sidecar.name.removesuffix(".meta.json"))
    assert (meta["sha256"], meta["size_bytes"]) == (sha256(main), main.stat().st_size)
    label = meta["extra"]["version"]["label"]
    assert main.parent.name == f"{label}_{meta['sha256'][:8]}"
    derived = meta["extra"].get("derived")
    attribution = (
        f"{SOURCE}. {PROCESSED}" if derived in ("series", "pmaxtp") else SOURCE
    )
    assert meta["license"]["attribution"] == attribution
    if main.relative_to(root).parts[0] == "archives":
        server_path = meta["request"]["server_path"]
        stem = Path(server_path).name.rsplit(".", 1)[0]
        assert main.relative_to(root) == Path(
            "archives/versions",
            Path(server_path).parent,
            stem,
            main.parent.name,
            main.name,
        )
        assert meta["extra"]["http"]["url"].endswith("/" + server_path)
        assert meta["extra"]["period"]["year_type"] in (
            "hydrological",
            "calendar",
            "none",
        )
    for source in meta["extra"].get("source_files", ()):
        archive = root / source["file"]
        assert sha256(archive) == source["sha256"] and archive.name == source["name"]
        assert (
            load(Path(f"{archive}.meta.json"))["extra"]["version"]["label"]
            == source["label"]
        )
    for source in meta["extra"].get("catalog", ()):
        if (source.get("file") or "").startswith("archives/"):
            assert sha256(root / source["file"]) == source["sha256"]
    return meta


def test_reader_enforces_required_sidecar_fields_and_tolerates_additions(
    tmp_path, fixture_root
):
    for contract, example in SCHEMAS["examples"].items():
        assert schema_errors(example, contract) == [], contract
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    entry = current_version(root, slot=ARCHIVE_SLOT)
    sidecar = Path(f"{entry.version}.meta.json")
    original = load(sidecar)

    def write(document):
        sidecar.write_text(json.dumps(document), encoding="utf-8")

    violations = {
        "brak sumy": lambda d: d.pop("sha256"),
        "suma wielkimi literami": lambda d: d.update(sha256=d["sha256"].upper()),
        "ujemny rozmiar": lambda d: d.update(size_bytes=-1),
        "rozmiar jako tekst": lambda d: d.update(size_bytes=str(d["size_bytes"])),
        "pusty identyfikator licencji": lambda d: d["license"].update(id=""),
        "brak atrybucji": lambda d: d["license"].pop("attribution"),
        "brak etykiety wersji": lambda d: d["extra"].pop("version"),
        "zgadywana etykieta": lambda d: d["extra"]["version"].update(label_source="x"),
        "obcy zbiór": lambda d: d.update(dataset="kartograf.dem"),
        "kraj spoza wzorca": lambda d: d.update(country="Polska"),
        "data bez formatu": lambda d: d.update(downloaded_at="wczoraj"),
    }
    for name, mutate in violations.items():
        document = copy.deepcopy(original)
        mutate(document)
        write(document)
        assert schema_errors(document, "imgw-meta/1"), name
        with pytest.raises(IMGWDataError):
            read_meta(entry.version)
        problems = [e.problem_code for e in iter_store(root, kind="problem")]
        assert problems == ["invalid_meta"], name

    additive = copy.deepcopy(original)
    additive["archiwista"] = {"indeks": "poza magazynem"}
    additive["extra"]["future"] = {"nowe": True}
    write(additive)
    assert schema_errors(additive, "imgw-meta/1") == []
    meta = read_meta(entry.version)
    assert meta.sha256 == original["sha256"] and meta.extra["future"] == {"nowe": True}
    assert list(iter_store(root, kind="problem")) == []

    future = copy.deepcopy(original)
    future["schema"] = "imgw-meta/2"
    write(future)
    assert schema_errors(future, "imgw-meta/1")
    assert [e.problem_code for e in iter_store(root, kind="problem")] == [
        "unknown_schema"
    ]


def test_fixture_store_files_conform_to_section_11_and_checksum_chains(fixture_root):
    root = fixture_root
    assert schema_errors(load(root / "imgw-store.json"), "imgw-store/1") == []
    sidecars = sorted(root.rglob("*.meta.json"))
    assert len(sidecars) == 11  # 7 archives, 3 series, 1 catalog
    metas = {sidecar: assert_sidecar_contract(root, sidecar) for sidecar in sidecars}

    for sidecar, meta in metas.items():
        main = sidecar.with_name(sidecar.name.removesuffix(".meta.json"))
        contract = contract_of(main)
        if not contract:
            continue
        document = load(main)
        assert schema_errors(document, contract) == [], main
        canonical = json.dumps(
            document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        assert main.read_bytes() == (canonical + "\n").encode("utf-8")
        if contract == "imgw-series/1":
            assert document["dataset"] == meta["dataset"]
            for code, station in document["stations"].items():
                parquet = main.parent / station["file"]
                assert sha256(parquet) == station["sha256"]
                assert pq.read_metadata(parquet).num_rows == station["rows"]
                schema = pq.read_schema(parquet).metadata
                assert schema[b"imgw_schema"] == b"imgw-series/1"
                assert schema[b"dataset"] == document["dataset"].encode()
                assert parquet.name == f"{code}.parquet"
        if contract == "stations.geojson":
            codes = [feature["id"] for feature in document["features"]]
            assert codes == sorted(codes) == sorted(set(codes))
            assert all(
                f["id"] == f["properties"]["station_code"] for f in document["features"]
            )
            assert any(f["geometry"] is None for f in document["features"])


def test_cell_and_plans_of_every_check_conform_to_schemas(tmp_path, fixture_root, imgw):
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    imgw.publish(H2024, V3, NEW)
    imgw.publish(O2001, signal("meteo_head"), archive_bytes(O2001))
    (h2001,) = archive_files(DAILY, years=[2001], months=[1])
    (o2024,) = archive_files(PRECIP, years=[2024], months=[1])
    imgw.unpublished(h2001, o2024)
    imgw.publish_catalog_sources()
    imgw.publish_pmaxtp("pmaxtp_pot_first", "pmaxtp_pot_same_cell")

    stored = sync_pmaxtp(root, method="POT", latitude=52.23, longitude=21.01)
    assert (stored.status, stored.ind_x, stored.ind_y) == ("created", 751, 317)
    assert schema_errors(load(stored.version), "imgw-pmaxtp/1") == []
    meta = assert_sidecar_contract(root, Path(f"{stored.version}.meta.json"))
    assert meta["request"]["method"] == "POT" and meta["extra"]["derived"] == "pmaxtp"
    again = sync_pmaxtp(root, method="POT", latitude=52.2301, longitude=21.0101)
    assert (again.status, again.version) == ("unchanged", stored.version)

    before = stamps(root)
    plans = {
        "store": check_store(
            root, datasets=[DAILY, PRECIP], years=[2001, 2024], months=[1]
        ),
        "series": check_series(root, dataset=DAILY),
        "catalog": check_catalog(root),
        "pmaxtp": check_pmaxtp(root, method="POT", latitude=52.23, longitude=21.01),
    }
    assert stamps(root) == before and imgw.downloads() == []
    for name, plan in plans.items():
        document = load(plan.to_json(tmp_path / f"{name}.json"))
        assert schema_errors(document, "imgw-plan/1") == [], name
        assert StorePlan.from_json(tmp_path / f"{name}.json") == plan
    items = {item.archive.server_path: item for item in plans["store"].items}
    assert {path: item.status for path, item in items.items()} == {
        h2001.server_path: "unverifiable",
        H2024.server_path: "current",
        O2001.server_path: "current",
        o2024.server_path: "unverifiable",
    }
    assert items[h2001.server_path].error == items[o2024.server_path].error
    assert items[h2001.server_path].error == "not published"
    assert plans["store"].series_state == {
        "hydro_daily": "current",
        "meteo_precip_daily": "outdated",
    }


def set_read_only(root: Path, read_only: bool) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            path.chmod(0o555 if read_only else 0o755)
        else:
            path.chmod(0o444 if read_only else 0o644)


def test_read_only_scan_reports_unknown_schema_and_problems_without_touching_store(
    tmp_path, fixture_root
):
    complete = tmp_path / "complete"
    shutil.copytree(fixture_root, complete)
    stale = complete / ".incoming" / "host_1_przerwany"
    stale.mkdir(parents=True)
    old = time.time() - 2 * 24 * 60 * 60
    os.utime(stale, (old, old))
    (complete / "series" / "versions" / "notatki.txt").write_text("?", encoding="utf-8")
    stores = {
        "complete": complete,
        "corrupt": build_fixture_store(tmp_path / "corrupt", variant="corrupt").root,
        "unknown": build_fixture_store(
            tmp_path / "unknown", variant="unknown_schema"
        ).root,
    }
    future = tmp_path / "future"
    future.mkdir()
    (future / "imgw-store.json").write_text(
        '{"schema":"imgw-store/2","created_by":"imgwtools 4.0.0"}\n', encoding="utf-8"
    )
    expected = {
        "complete": {"stale_incoming", "unknown_entry"},
        "corrupt": {"invalid_json"},
        "unknown": {"unknown_schema"},
    }
    broken_slots = {"corrupt": ARCHIVE_SLOT, "unknown": "series:pl.imgw.hydro_daily"}
    for root in [*stores.values(), future]:
        set_read_only(root, True)
    try:
        before = {name: stamps(root) for name, root in stores.items()}
        for name, root in stores.items():
            info = store_info(root)
            assert (info.supported, info.schema, info.problems) == (
                True,
                "imgw-store/1",
                (),
            )
            entries = list(iter_store(root))
            problems = [entry for entry in entries if entry.kind == "problem"]
            assert {entry.problem_code for entry in problems} == expected[name]
            # A problem names the slot of the broken version, or none at all.
            assert {(entry.problem_code, entry.slot) for entry in problems} <= {
                ("stale_incoming", None),
                ("unknown_entry", None),
                ("invalid_json", broken_slots.get(name)),
                ("unknown_schema", broken_slots.get(name)),
            }
            versions = [entry for entry in entries if entry.kind != "problem"]
            assert len(versions) == 11 - (name == "corrupt")
            for entry in versions:
                assert read_meta(entry.version) == entry.meta
            for slot in sorted({entry.slot for entry in versions}):
                if slot == broken_slots.get(name):
                    with pytest.raises(IMGWDataError):
                        current_version(root, slot=slot)
                    continue
                current = current_version(root, slot=slot)
                assert current is not None and current.slot == slot
                assert current in [entry for entry in versions if entry.slot == slot]
            (catalog,) = [entry for entry in versions if entry.kind == "catalog"]
            assert any(
                feature.geometry is None for feature in read_catalog(catalog.version)
            )
            for entry in versions:
                if entry.kind == "series":
                    index = read_series_index(entry.version)
                    station = sorted(index.stations)[0]
                    variable = next(iter(index.stations[station].variables))
                    rows = list(
                        read_series(
                            entry.version, station=station, variables=[variable]
                        )
                    )
                    assert len(rows) == index.stations[station].rows
            if name == "unknown":
                (problem,) = problems
                with pytest.raises(IMGWDataError):
                    read_series_index(problem.version)
        assert {name: stamps(root) for name, root in stores.items()} == before

        info = store_info(future)
        assert (info.exists, info.schema, info.supported) == (
            True,
            "imgw-store/2",
            False,
        )
        assert [(e.kind, e.problem_code) for e in iter_store(future)] == [
            ("problem", "unsupported_store")
        ]
        with pytest.raises(IMGWStoreError):
            open_store(future)
        with pytest.raises(IMGWStoreError):
            current_version(future, slot="series:pl.imgw.hydro_daily")
    finally:
        for root in [*stores.values(), future]:
            set_read_only(root, False)
    response = DownloadResult(OLD, H2024.url, V1["ETag"], V1["Last-Modified"], len(OLD))
    with pytest.raises(IMGWStoreError):
        write_archive(future, archive=H2024, response=response)
    with pytest.raises(IMGWStoreError):
        init_store(future)
    assert sorted(path.name for path in future.iterdir()) == ["imgw-store.json"]


def test_lifecycle_head_plan_stale_sync_series_catalog_csv_project_restore(
    tmp_path, imgw
):
    root = init_store(tmp_path / "store").root
    old8, new8 = sha256(OLD)[:8], sha256(NEW)[:8]

    # HEAD → plan: listing and HEAD only; nothing is downloaded or written.
    imgw.publish(H2024, V1, OLD)
    untouched = stamps(root)
    plan = check_store(root, datasets=[DAILY], years=[2024])
    (item,) = plan.items
    assert (item.status, item.remote_etag, item.local_path) == (
        "missing",
        V1["ETag"],
        None,
    )
    assert plan.series_state == {"hydro_daily": "missing"}
    assert imgw.requests("HEAD") == [H2024.url] and imgw.downloads() == []
    plan_file = plan.to_json(tmp_path / "plan.json")
    assert schema_errors(load(plan_file), "imgw-plan/1") == []
    assert StorePlan.from_json(plan_file) == plan
    assert stamps(root) == untouched

    # Stale: IMGW republished after the check → no GET, no write, series not built.
    imgw.publish(H2024, V2, OLD)
    notices = []
    report = sync_store(root, plan=plan_file, on_notice=notices.append)
    (stale,) = report.items
    assert (stale.status, stale.version) == ("stale_plan", None)
    assert "stale_plan" in {notice.code for notice in notices}
    assert [series.status for series in report.series] == ["failed"]
    assert imgw.downloads() == [] and stamps(root) == untouched

    # Sync from a fresh plan: one GET, a version named after Last-Modified and SHA.
    report = sync_store(root, plan=check_store(root, datasets=[DAILY], years=[2024]))
    (created,) = report.items
    assert created.status == "created"
    assert created.version == root / SLOT_DIR / f"2026-10-18_{old8}" / "codz_2024.zip"
    assert sha256(created.version) == sha256(OLD)
    (first,) = report.series
    assert first.status == "created" and first.source_files == (created.version,)
    assert imgw.downloads() == [H2024.url]

    # Newer bytes: the plan flags the series; sync without series leaves it outdated.
    imgw.publish(H2024, V3, NEW)
    plan = check_store(root, datasets=[DAILY], years=[2024])
    assert [item.status for item in plan.items] == ["newer"]
    assert plan.series_state == {"hydro_daily": "outdated"}
    report = sync_store(root, plan=plan, series=False)
    (newer,) = report.items
    assert newer.status == "created" and report.series == ()
    assert newer.version == root / SLOT_DIR / f"2026-10-19_{new8}" / "codz_2024.zip"
    assert check_series(root, dataset=DAILY).series_state == {"hydro_daily": "outdated"}
    series = build_series(root, dataset=DAILY)
    assert series.status == "created" and series.source_files == (newer.version,)
    assert check_series(root, dataset=DAILY).series_state == {"hydro_daily": "current"}
    assert (
        current_version(root, slot="series:pl.imgw.hydro_daily").version
        == series.version
    )
    # The sync report, the scan and current_version share one slot per file.
    assert newer.slot == ARCHIVE_SLOT
    scanned = current_version(root, slot=newer.slot)
    assert scanned.version == newer.version
    assert scanned in [
        entry for entry in iter_store(root, kind="archive") if entry.slot == newer.slot
    ]

    # Coverage: the series index equals the public coverage of the parsed archive.
    index = read_series_index(series.version)
    assert index.periods == ((H2024.period_start, H2024.period_end),)
    records = list(normalize_archive(H2024, data=NEW))
    coverage = summarize_coverage(records, dataset=DAILY)
    assert {(c.station_code, c.variable) for c in coverage} == {
        (code, variable)
        for code, station in index.stations.items()
        for variable in station.variables
    }
    for expected in coverage:
        assert (
            index.stations[expected.station_code].variables[expected.variable]
            == expected
        )
    parsed = {record.date: record for record in records if record.station_code == RABA}
    rows = list(read_series(series.version, station=RABA, variables=["H", "Q"]))
    assert len(rows) == index.stations[RABA].rows
    assert (rows[0].date, rows[-1].date) == (min(parsed), max(parsed))
    for row in rows:
        source = parsed.get(row.date)
        for variable in ("H", "Q"):
            measurement = row.measurements[variable]
            if source is None or variable not in source.measurements:
                assert (measurement.value, measurement.flag) == (None, "missing")
            else:
                assert measurement == source.measurements[variable]

    # Catalog: lists archived first, HEAD-only check, identical rebuild unchanged.
    imgw.publish_catalog_sources()
    catalog = build_catalog(root)
    assert catalog.status == "created" and catalog.without_location > 0
    features = read_catalog(catalog.version)
    assert len(features) == catalog.station_count
    assert (
        sum(feature.geometry is None for feature in features)
        == catalog.without_location
    )
    lists = {
        entry.slot
        for entry in iter_store(root, kind="archive")
        if entry.slot != ARCHIVE_SLOT
    }
    assert lists == {
        "archive:pl.imgw.hydro_stations:lista_stacji_hydro.csv",
        "archive:pl.imgw.meteo_stations:wykaz_stacji.csv",
    }
    untouched, gets = stamps(root), len(imgw.requests("GET"))
    catalog_plan = check_catalog(root)
    assert stamps(root) == untouched and len(imgw.requests("GET")) == gets
    assert {item.status for item in catalog_plan.items} == {"current"}
    assert build_catalog(root).status == "unchanged"

    # CSV: one header row with units, both formulas once, every day of the series.
    target = export_series(
        series.version, station=RABA, path=tmp_path / "raba.csv", variables=["H", "Q"]
    )
    with target.open(encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    assert list(table[0]) == [
        "date",
        "year",
        "H [cm]",
        "H_flag",
        "Q [m3/s]",
        "Q_flag",
        "attribution_source",
        "attribution_processed",
    ]
    assert (table[0]["attribution_source"], table[0]["attribution_processed"]) == (
        SOURCE,
        PROCESSED,
    )
    assert not any(
        row["attribution_source"] or row["attribution_processed"] for row in table[1:]
    )
    assert [(row["date"], row["H_flag"], row["Q_flag"]) for row in table] == [
        (row.date.isoformat(), row.measurements["H"].flag, row.measurements["Q"].flag)
        for row in rows
    ]
    assert all(row["year"] == "2024" for row in table)  # hydrological year XI–X

    # Project: check writes nothing, download pins the series and its exact inputs.
    project = tmp_path / "project"
    manifest = project / "imgw-project.json"
    init_project(project, store_dir=root)
    add_project_task(
        project,
        name="raba",
        command="series select",
        options={"dataset": DAILY, "stations": [RABA], "years": [2024]},
    )
    untouched, written = stamps(root), manifest.read_bytes()
    checked = check_project(project)
    assert [(action.command, action.status) for action in checked.actions] == [
        ("project download", "missing")
    ]
    assert stamps(root) == untouched and manifest.read_bytes() == written
    assert download_project(project).tasks == {"raba": "current"}
    document = load(manifest)
    assert schema_errors(document, "imgw-project/1") == []
    pins = {pin["role"]: pin for pin in document["tasks"][0]["files"]}
    assert pins["series"]["path"] == series.version.relative_to(root).as_posix()
    assert pins["input"]["path"] == newer.version.relative_to(root).as_posix()
    assert pins["station_series"]["station_code"] == RABA
    assert all(sha256(root / pin["path"]) == pin["sha256"] for pin in pins.values())
    assert verify_project(project).tasks == {"raba": "current"}

    # Restore: a lost pinned archive comes back only with identical bytes and path.
    pinned = manifest.read_bytes()
    shutil.rmtree(newer.version.parent)
    assert get_project_status(project).tasks == {"raba": "missing"}
    assert verify_project(project).tasks == {"raba": "missing"}
    restored = download_project(project)
    assert restored.tasks == {"raba": "current"}
    assert {result.status for result in restored.files} == {"created", "unchanged"}
    assert sha256(newer.version) == pins["input"]["sha256"]
    assert manifest.read_bytes() == pinned
    assert verify_project(project).tasks == {"raba": "current"}

    # Relabel: same bytes under a new signal → new version, series reused untouched.
    imgw.publish(H2024, V4, NEW)
    series_files = stamps(series.version.parent)
    report = sync_store(root, datasets=[DAILY], years=[2024])
    (relabeled,) = report.items
    assert relabeled.status == "relabeled"
    assert relabeled.version == root / SLOT_DIR / f"2026-10-20_{new8}" / "codz_2024.zip"
    (reused,) = report.series
    assert (reused.status, reused.version) == ("reused", series.version)
    assert stamps(series.version.parent) == series_files
    assert [action.status for action in check_project(project).actions] == ["current"]
    assert manifest.read_bytes() == pinned


def assert_no_partial_version(root: Path) -> None:
    """Every published version directory holds its main file and its sidecar."""
    for sidecar in root.rglob("*.meta.json"):
        assert sidecar.with_name(sidecar.name.removesuffix(".meta.json")).is_file()
    for directory in root.glob("*/versions/**/*"):
        if directory.is_dir() and VERSION_DIR.fullmatch(directory.name):
            assert any(directory.glob("*.meta.json")), directory


def test_cancellation_reports_done_items_and_never_publishes_partial_versions(
    tmp_path, imgw
):
    root = init_store(tmp_path / "store").root
    imgw.publish(H2023, V1, archive_bytes(H2023))
    imgw.publish(H2024, V1, OLD)

    answers = iter([False, True])
    plan = check_store(
        root, datasets=[DAILY], years=[2023, 2024], cancel=lambda: next(answers)
    )
    assert plan.cancelled
    assert [(item.status, item.error) for item in plan.items] == [
        ("missing", None),
        ("unverifiable", "cancelled"),
    ]
    document = load(plan.to_json(tmp_path / "plan.json"))
    assert (
        document["cancelled"] is True and schema_errors(document, "imgw-plan/1") == []
    )
    assert imgw.downloads() == []

    report = sync_store(root, plan=tmp_path / "plan.json")
    assert [result.status for result in report.items] == ["created", "cancelled"]
    assert report.cancelled and [s.status for s in report.series] == ["cancelled"]
    assert imgw.downloads() == [H2023.url]

    other = init_store(tmp_path / "other").root
    report = sync_store(
        other,
        datasets=[DAILY],
        years=[2023, 2024],
        cancel=lambda: H2024.url in imgw.downloads(),
    )
    assert [result.status for result in report.items] == ["created", "cancelled"]
    assert report.cancelled and report.items[1].version is None
    assert not (other / SLOT_DIR).exists() or not any((other / SLOT_DIR).iterdir())
    assert [s.status for s in report.series] == ["cancelled"]
    assert list((other / "series").glob("versions/*/*")) == []

    before = snapshot(root)
    assert build_series(root, dataset=DAILY, cancel=lambda: True).status == "cancelled"
    imgw.publish_catalog_sources()
    assert build_catalog(root, cancel=lambda: True).status == "cancelled"
    assert snapshot(root) == before
    series = build_series(root, dataset=DAILY)
    target = tmp_path / "eksport.csv"
    with pytest.raises(IMGWCancelledError):
        export_series(
            series.version,
            station=RABA,
            path=target,
            variables=["H"],
            cancel=lambda: True,
        )
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "other",
        "plan.json",
        "store",
    ]
    for store in (root, other):
        assert_no_partial_version(store)


def test_concurrent_writers_publish_each_version_once(tmp_path):
    root = init_store(tmp_path / "store").root
    response = DownloadResult(OLD, H2024.url, V1["ETag"], V1["Last-Modified"], len(OLD))
    writers = threading.Barrier(4)

    def write(_):
        writers.wait()
        return write_archive(root, archive=H2024, response=response)

    with ThreadPoolExecutor(4) as pool:
        written = list(pool.map(write, range(4)))
    assert (
        sorted(result.status for result in written) == ["created"] + ["unchanged"] * 3
    )
    assert len({result.path for result in written}) == 1
    assert [path.name for path in (root / SLOT_DIR).iterdir()] == [
        written[0].path.parent.name
    ]

    builders = threading.Barrier(3)

    def build(_):
        builders.wait()
        return build_series(root, dataset=DAILY)

    with ThreadPoolExecutor(3) as pool:
        built = list(pool.map(build, range(3)))
    assert sorted(report.status for report in built) == ["created", "reused", "reused"]
    assert len({report.version for report in built}) == 1
    assert len(list((root / "series" / "versions" / "hydro_daily").iterdir())) == 1
    assert not any((root / ".incoming").iterdir())
    assert_no_partial_version(root)
