"""Offline behavioral tests for immutable store publication."""

import errno
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from imgwtools._version import __version__
from imgwtools.datasets import archive_files
from imgwtools.exceptions import (
    IMGWCancelledError,
    IMGWStoreConflictError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store import (
    current_version,
    init_store,
    iter_store,
    open_store,
    write_archive,
    writer,
)
from imgwtools.store.types import Observation

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVE = archive_files("pl.imgw.hydro_daily", years=[2024])[0]
DATA = (FIXTURES / "archives" / ARCHIVE.server_path).read_bytes()
CHANGED = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()
DAILY_2024 = "archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
# Observation example of spec 2026-10-18 §3.2 (arbitrary sums).
OBSERVATION = {
    "schema": "imgw-observation/1",
    "producer": "imgwtools",
    "producer_version": "3.1.0",
    "dataset": "cz.chmi.hydro_daily",
    "seen_at": "2026-10-19T06:00:00Z",
    "url": "https://opendata.chmi.cz/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2025.json",
    "last_modified": "Mon, 19 Oct 2026 03:12:44 GMT",
    "etag": '"6ad58aac-54c6"',
    "size_bytes": 21702,
    "sha256": "2" * 64,
    "content_sha256": "1" * 64,
    "content_form": "chmi-json/1",
    "same_content_as": "2026-05-21_00000000",
}
CHMI_SLOT = "archives/versions/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2025"


def response(*, etag='"hydro-v1"', modified="Sat, 17 Oct 2026 12:00:00 GMT", data=DATA):
    return DownloadResult(data, ARCHIVE.url, etag, modified, len(data))


def test_archive_provenance_relabel_and_unchanged(tmp_path):
    handle = init_store(
        tmp_path / "store", created_at=datetime(2026, 10, 17, tzinfo=UTC)
    )
    assert open_store(handle.root) == handle
    first = write_archive(handle, archive=ARCHIVE, response=response())
    assert first.status == "new"
    assert first.path.relative_to(handle.root).as_posix() == (
        f"archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/"
        f"2026-10-17_{first.sha256[:8]}/codz_2024.zip"
    )
    assert first.path.read_bytes() == DATA
    meta = json.loads(first.path.with_name(first.path.name + ".meta.json").read_text())
    assert meta["schema"] == "imgw-meta/1"
    assert meta["sha256"] == hashlib.sha256(DATA).hexdigest()
    assert meta["size_bytes"] == len(DATA)
    assert meta["extra"]["http"]["etag"] == '"hydro-v1"'
    assert meta["extra"]["period"]["year_type"] == "hydrological"
    assert meta["license"]["id"] == "IMGW-PIB"
    assert (
        write_archive(handle, archive=ARCHIVE, response=response()).status
        == "unchanged"
    )
    second = write_archive(
        handle,
        archive=ARCHIVE,
        response=response(etag='"hydro-v2"', modified="Sun, 18 Oct 2026 12:00:00 GMT"),
    )
    assert second.status == "relabeled"
    assert (
        second.path != first.path
        and second.path.read_bytes() == first.path.read_bytes()
    )
    assert first.path.stat().st_nlink == second.path.stat().st_nlink == 1
    assert (
        write_archive(
            handle, archive=ARCHIVE, response=response(etag=None, modified=None)
        ).status
        == "unchanged"
    )


def test_same_day_distinct_signals_and_concurrent_writers(tmp_path):
    root = init_store(tmp_path / "store")
    one = write_archive(root, archive=ARCHIVE, response=response())
    two = write_archive(root, archive=ARCHIVE, response=response(etag='"second"'))
    assert two.status == "relabeled" and "+" in two.label
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda _: write_archive(
                    root, archive=ARCHIVE, response=response(etag='"third"')
                ),
                range(2),
            )
        )
    assert {item.status for item in outcomes} == {"relabeled", "unchanged"}
    assert len({one.path, two.path, outcomes[0].path}) == 3


def _version_dir(root):
    sha8 = hashlib.sha256(DATA).hexdigest()[:8]
    return (
        root.root
        / "archives/versions"
        / Path(ARCHIVE.server_path).parent
        / "codz_2024"
        / f"2026-10-17_{sha8}"
    )


def test_interrupted_publication_is_no_version_and_is_completed(tmp_path):
    root = init_store(tmp_path / "store")
    target = _version_dir(root)
    target.mkdir(parents=True)
    (target / "codz_2024.zip").write_bytes(DATA)  # data linked, sidecar never was
    assert current_version(root, slot=DAILY_2024) is None
    assert [e.problem_code for e in iter_store(root, kind="problem")] == [
        "missing_sidecar"
    ]
    written = write_archive(root, archive=ARCHIVE, response=response())
    assert (written.status, written.path) == ("new", target / "codz_2024.zip")
    assert list(iter_store(root, kind="problem")) == []
    assert current_version(root, slot=DAILY_2024).version == written.path


def test_interrupted_publication_with_other_bytes_is_never_replaced(tmp_path):
    root = init_store(tmp_path / "store")
    target = _version_dir(root)
    target.mkdir(parents=True)
    (target / "codz_2024.zip").write_bytes(CHANGED)
    with pytest.raises(IMGWStoreConflictError, match="collision"):
        write_archive(root, archive=ARCHIVE, response=response())
    assert [p.name for p in target.iterdir()] == ["codz_2024.zip"]
    assert (target / "codz_2024.zip").read_bytes() == CHANGED


@pytest.mark.parametrize(
    "failure",
    [OSError(errno.EIO, os.strerror(errno.EIO)), KeyboardInterrupt()],
    ids=["eio", "keyboard_interrupt"],
)
def test_failed_commit_keeps_files_a_concurrent_writer_committed(
    tmp_path, monkeypatch, failure
):
    root = init_store(tmp_path / "store")
    target = _version_dir(root)
    real_link = os.link
    first_commit = True
    concurrent = []

    def link(source, destination):
        nonlocal first_commit
        if first_commit and Path(destination).name.endswith(".meta.json"):
            first_commit = False
            # Writer A has linked codz_2024.zip; writer B (same bytes) keeps that
            # file and commits its sidecar before A's own commit fails.
            concurrent.append(write_archive(root, archive=ARCHIVE, response=response()))
            raise failure
        return real_link(source, destination)

    monkeypatch.setattr(writer.os, "link", link)
    with pytest.raises(type(failure)):
        write_archive(root, archive=ARCHIVE, response=response())
    [winner] = concurrent
    assert (winner.status, winner.path) == ("new", target / "codz_2024.zip")
    assert sorted(path.name for path in target.iterdir()) == [
        "codz_2024.zip",
        "codz_2024.zip.meta.json",
    ]
    assert winner.path.read_bytes() == DATA
    assert list(iter_store(root, kind="problem")) == []
    assert current_version(root, slot=DAILY_2024).version == winner.path
    assert list((root.root / ".incoming").iterdir()) == []


def test_file_system_without_hard_links_is_explicit(tmp_path, monkeypatch):
    root = init_store(tmp_path / "store")

    def no_links(source, target):
        raise OSError(errno.EXDEV, os.strerror(errno.EXDEV))

    monkeypatch.setattr(writer.os, "link", no_links)
    with pytest.raises(IMGWStoreConflictError, match="hard links") as error:
        write_archive(root, archive=ARCHIVE, response=response())
    assert error.value.details == {"reason": "not_atomic"}
    assert not list((root.root / "archives").rglob("*.zip"))
    assert not list((root.root / ".incoming").iterdir())


def test_abort_cleanup_and_fsync(tmp_path, monkeypatch):
    root = init_store(tmp_path / "store")
    incoming = root.root / ".incoming"
    incoming.mkdir()
    old = incoming / "old"
    new = incoming / "new"
    old.mkdir()
    new.mkdir()
    elapsed = time.time() - 25 * 3600
    os.utime(old, (elapsed, elapsed))
    fsynced = []
    original = writer.os.fsync

    def record(fd):
        fsynced.append(fd)
        return original(fd)

    monkeypatch.setattr(writer.os, "fsync", record)
    with pytest.raises(IMGWCancelledError, match="cancelled"):
        write_archive(root, archive=ARCHIVE, response=response(), cancel=lambda: True)
    assert old.exists()  # no operation began, so nothing was cleaned
    write_archive(root, archive=ARCHIVE, response=response())
    assert not old.exists() and new.exists()
    assert (
        len(fsynced) >= 4
    )  # marker, archive, sidecar, stage directory, published parent


def test_sidecar_failure_cannot_publish_half_version(tmp_path, monkeypatch):
    root = init_store(tmp_path / "store")
    original = writer._write_json

    def fail_sidecar(path, value):
        if path.name.endswith(".meta.json"):
            raise OSError("przerwany zapis")
        return original(path, value)

    monkeypatch.setattr(writer, "_write_json", fail_sidecar)
    with pytest.raises(OSError, match="przerwany"):
        write_archive(root, archive=ARCHIVE, response=response())
    assert not list(root.root.rglob("codz_2024.zip"))
    assert not list((root.root / ".incoming").iterdir())


def test_nested_kartograf_detection_by_marker_name_without_import(tmp_path):
    foreign = tmp_path / "kartograf"
    foreign.mkdir()
    (foreign / "kartograf-store.json").write_text('{"schema": "kartograf-store/1"}')
    with pytest.raises(IMGWStoreConflictError, match="kartograf-store.json") as inside:
        init_store(foreign / "results" / "imgw")
    assert inside.value.details == {"reason": "nested_store"}
    assert init_store(tmp_path / "separate").root.exists()
    other = tmp_path / "outer"
    (other / "child").mkdir(parents=True)
    (other / "child" / "kartograf-store.json").write_text("{}")
    with pytest.raises(IMGWStoreConflictError, match="kartograf-store.json"):
        init_store(other)
    # The sidecars and manifests of the old probe are no marker: nothing nests.
    legacy = tmp_path / "legacy"
    (legacy / "versions" / "item").mkdir(parents=True)
    (legacy / "kartograf-project.json").write_text('{"output_dir": "results"}')
    (legacy / "versions" / "item" / "sample.meta.json").write_text(
        '{"schema":"kartograf-meta/1"}'
    )
    assert init_store(legacy / "results" / "imgw").root.exists()


def test_foreign_or_nested_store_and_path_escape(tmp_path):
    root = init_store(tmp_path / "store")
    with pytest.raises(IMGWStoreError) as inside:
        init_store(root.root / "nested")
    with pytest.raises(IMGWStoreError) as around:
        init_store(tmp_path)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "notes.txt").write_text("x")
    with pytest.raises(IMGWStoreError, match="not an empty IMGW store") as not_empty:
        init_store(busy)
    for error, reason in (
        (inside, "nested_store"),
        (around, "nested_store"),
        (not_empty, "not_empty"),
    ):
        assert error.value.code == "conflict"
        assert error.value.details == {"reason": reason}
    unsafe = replace(ARCHIVE, server_path="dane_hydrologiczne/dobowe/../escape.zip")
    with pytest.raises(Exception, match="unsafe archive path"):
        write_archive(root, archive=unsafe, response=response())


def test_symbolic_link_in_store_path_is_a_validation_error(tmp_path):
    init_store(tmp_path / "real")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    for call in (
        lambda: init_store(tmp_path / "link" / "inner"),
        lambda: open_store(tmp_path / "link"),
    ):
        with pytest.raises(IMGWStoreError, match="symbolic link") as error:
            call()
        assert error.value.code == "validation_error"


def test_identical_signal_after_relabel_is_unchanged(tmp_path):
    root = init_store(tmp_path / "store")
    first = write_archive(root, archive=ARCHIVE, response=response(etag='"e1"'))
    second = write_archive(root, archive=ARCHIVE, response=response(etag='"e2"'))
    third = write_archive(root, archive=ARCHIVE, response=response(etag='"e1"'))
    assert [first.status, second.status, third.status] == [
        "new",
        "relabeled",
        "unchanged",
    ]
    assert third.path == first.path and third.label == first.label
    assert len(list(first.path.parent.parent.iterdir())) == 2


def test_archive_sidecar_without_http_is_conflict(tmp_path):
    root = init_store(tmp_path / "store")
    first = write_archive(root, archive=ARCHIVE, response=response())
    sidecar = first.path.with_name(first.path.name + ".meta.json")
    meta = json.loads(sidecar.read_text())
    del meta["extra"]["http"]
    sidecar.write_text(json.dumps(meta))
    with pytest.raises(IMGWStoreConflictError, match="A corrupt archive version"):
        write_archive(root, archive=ARCHIVE, response=response())


def _stale_incoming(root):
    incoming = root.root / ".incoming"
    incoming.mkdir()
    old = incoming / "old"
    new = incoming / "new"
    (old / "partial").mkdir(parents=True)
    new.mkdir()
    elapsed = time.time() - 25 * 3600
    os.utime(old, (elapsed, elapsed))
    return old, new


def test_stale_staging_removed_with_notice(tmp_path):
    root = init_store(tmp_path / "store")
    old, new = _stale_incoming(root)
    notices = []
    write_archive(root, archive=ARCHIVE, response=response(), on_notice=notices.append)
    assert not old.exists() and new.exists()
    leftovers = [item for item in notices if item.code == "leftover_incoming"]
    assert len(leftovers) == 1
    assert leftovers[0].level == "warning" and ".incoming/old" in leftovers[0].text


def test_stale_staging_removed_concurrently_does_not_abort(tmp_path, monkeypatch):
    root = init_store(tmp_path / "store")
    old, _ = _stale_incoming(root)
    original = writer.shutil.rmtree
    notices = []

    def raced(path, *args, **kwargs):
        if Path(path) == old:
            original(path)  # another writer removes the stale staging first
        return original(path, *args, **kwargs)

    monkeypatch.setattr(writer.shutil, "rmtree", raced)
    result = write_archive(
        root, archive=ARCHIVE, response=response(), on_notice=notices.append
    )
    assert result.status == "new" and not old.exists()
    assert not [item for item in notices if item.code == "leftover_incoming"]


def test_corrupt_sidecar_in_other_slot_does_not_block_writes(tmp_path):
    root = init_store(tmp_path / "store")
    other = archive_files("pl.imgw.hydro_daily", years=[2023])[0]
    data = (FIXTURES / "archives" / other.server_path).read_bytes()
    written = write_archive(
        root,
        archive=other,
        response=DownloadResult(data, other.url, '"x"', None, len(data)),
    )
    written.path.with_name(written.path.name + ".meta.json").write_text("{")
    assert write_archive(root, archive=ARCHIVE, response=response()).status == ("new")


def test_a_kartograf_store_inside_a_store_is_detected_before_a_write(tmp_path):
    root = init_store(tmp_path / "store")
    foreign = root.root / "foreign"
    foreign.mkdir()
    (foreign / "kartograf-store.json").write_text('{"schema": "kartograf-store/1"}')
    with pytest.raises(IMGWStoreConflictError, match="kartograf-store.json") as error:
        write_archive(root, archive=ARCHIVE, response=response())
    assert error.value.details == {"reason": "nested_store"}
    assert not list(root.root.rglob("codz_2024.zip"))


def test_marker_without_hard_links_is_store_error(tmp_path, monkeypatch):
    def refuse(source, target):
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(writer.os, "link", refuse)
    path = tmp_path / "store"
    with pytest.raises(IMGWStoreError, match="a hard link") as error:
        init_store(path)
    assert error.value.code == "conflict"
    assert not (path / "imgw-store.json").exists()
    assert not list(path.glob(".imgw-store.json.*.tmp"))


def test_publish_observation_writes_the_spec_example_once_without_traces(tmp_path):
    root = init_store(tmp_path / "store").root
    (root / CHMI_SLOT).mkdir(parents=True)
    observation = Observation(
        **{
            key: value
            for key, value in OBSERVATION.items()
            if key not in ("schema", "producer", "producer_version")
        }
    )

    path = writer._publish_observation(root, slot=CHMI_SLOT, observation=observation)
    assert path == root / CHMI_SLOT / "observations" / "2026-10-19_19106605.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        **OBSERVATION,
        "producer_version": __version__,
    }
    assert list((root / ".incoming").iterdir()) == []

    # The same signal on the same day: the existing file stays byte for byte.
    written = path.read_bytes()
    later = replace(observation, seen_at="2026-10-19T18:30:00Z", sha256="3" * 64)
    assert writer._publish_observation(root, slot=CHMI_SLOT, observation=later) == path
    assert path.read_bytes() == written

    # Cancelled before the rename: no file, no new register, no staging left.
    fresh = CHMI_SLOT.replace("001000", "900002")
    (root / fresh).mkdir()
    for slot, item in (
        (CHMI_SLOT, replace(observation, etag='"inny"')),
        (fresh, observation),
    ):
        with pytest.raises(IMGWCancelledError):
            writer._publish_observation(
                root, slot=slot, observation=item, cancel=lambda: True
            )
    assert list(path.parent.iterdir()) == [path]
    assert list((root / fresh).iterdir()) == []
    assert list((root / ".incoming").iterdir()) == []
    with pytest.raises(IMGWValidationError, match="YYYY-MM-DDTHH:MM:SSZ"):
        writer._publish_observation(
            root,
            slot=fresh,
            observation=replace(observation, seen_at="2026-10-19T06:00:00.5Z"),
        )
    assert list((root / fresh).iterdir()) == []


def test_write_archive_results_ignore_the_observation_register_of_the_slot(tmp_path):
    steps = (
        response(),
        response(etag='"hydro-v2"', modified="Sun, 18 Oct 2026 12:00:00 GMT"),
        response(
            etag='"hydro-v3"', modified="Mon, 19 Oct 2026 12:00:00 GMT", data=CHANGED
        ),
        response(etag='"hydro-v2"', modified="Sun, 18 Oct 2026 12:00:00 GMT"),
    )
    results = {}
    for name in ("plain", "observed"):
        root = init_store(tmp_path / name).root
        first = write_archive(root, archive=ARCHIVE, response=response())
        if name == "observed":
            register = first.path.parent.parent / "observations"
            register.mkdir()
            (register / "2026-10-19_00000000.json").write_text("{}", encoding="utf-8")
        outcomes = [
            first,
            *(write_archive(root, archive=ARCHIVE, response=step) for step in steps),
        ]
        results[name] = [
            (item.status, item.path.relative_to(root), item.sha256, item.label)
            for item in outcomes
        ]
    assert results["observed"] == results["plain"]
    assert [status for status, *_ in results["plain"]] == [
        "new",
        "unchanged",
        "relabeled",
        "new",
        "unchanged",
    ]
