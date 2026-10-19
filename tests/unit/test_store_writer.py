"""Offline behavioral tests for immutable store publication."""

import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
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
from imgwtools.store import init_store, open_store, write_archive, writer
from imgwtools.store.types import Observation

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVE = archive_files("pl.imgw.hydro_daily", years=[2024])[0]
DATA = (FIXTURES / "archives" / ARCHIVE.server_path).read_bytes()
CHANGED = (FIXTURES / "variants" / "codz_2024_changed.zip").read_bytes()
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


@pytest.mark.usefixtures("publication")
def test_archive_provenance_relabel_and_unchanged(tmp_path):
    handle = init_store(
        tmp_path / "store", created_at=datetime(2026, 10, 17, tzinfo=UTC)
    )
    assert open_store(handle.root) == handle
    first = write_archive(handle, archive=ARCHIVE, response=response())
    assert first.status == "created"
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


@pytest.mark.usefixtures("publication")
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


@pytest.mark.usefixtures("publication")
def test_existing_empty_target_never_replaced(tmp_path):
    root = init_store(tmp_path / "store")
    expected = hashlib.sha256(DATA).hexdigest()[:8]
    target = (
        root.root
        / "archives/versions"
        / Path(ARCHIVE.server_path).parent
        / "codz_2024"
        / f"2026-10-17_{expected}"
    )
    target.mkdir(parents=True)
    with pytest.raises(IMGWStoreConflictError):
        write_archive(root, archive=ARCHIVE, response=response())
    assert list(target.iterdir()) == []


def test_renameat2_without_noreplace_on_the_file_system_publishes_portably(
    tmp_path, monkeypatch
):
    calls = []

    def renameat2(*args):  # a file system without RENAME_NOREPLACE, e.g. NFS
        calls.append(args)
        ctypes.set_errno(errno.EINVAL)
        return -1

    monkeypatch.setattr(writer, "_libc_renameat2", lambda: renameat2)
    root = init_store(tmp_path / "store")
    first = write_archive(root, archive=ARCHIVE, response=response())
    second = write_archive(root, archive=ARCHIVE, response=response(etag='"v2"'))
    assert calls and (first.status, second.status) == ("created", "relabeled")
    assert first.path.read_bytes() == second.path.read_bytes() == DATA
    assert not list((root.root / ".incoming").iterdir())


def test_portable_publication_never_replaces_a_version_published_meanwhile(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(writer, "_libc_renameat2", lambda: None)
    rename = os.rename

    def raced(source, target):
        # Another writer publishes the same version between the check and the rename.
        rival = Path(source).with_name("rival")
        shutil.copytree(source, rival)
        rename(rival, target)
        raise OSError(code, os.strerror(code), str(target))

    monkeypatch.setattr(writer.os, "rename", raced)
    # A rename onto an existing directory fails with ENOTEMPTY or EEXIST (POSIX)
    # or e.g. EACCES (SMB server); the existing version always stays.
    for code in (errno.ENOTEMPTY, errno.EEXIST, errno.EACCES):
        root = init_store(tmp_path / errno.errorcode[code])
        result = write_archive(root, archive=ARCHIVE, response=response())
        assert result.status == "unchanged" and result.path.read_bytes() == DATA
        assert [path.name for path in result.path.parent.parent.iterdir()] == [
            result.path.parent.name
        ]
        assert not list((root.root / ".incoming").iterdir())

    def refused(source, target):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(target))

    monkeypatch.setattr(writer.os, "rename", refused)
    root = init_store(tmp_path / "refused")
    with pytest.raises(IMGWStoreConflictError, match="Nie można atomowo opublikować"):
        write_archive(root, archive=ARCHIVE, response=response())
    assert not list((root.root / "archives").rglob("*.zip"))
    assert not list((root.root / ".incoming").iterdir())


def test_windows_publication_renames_without_replacing_or_flushing_directories(
    tmp_path, monkeypatch
):
    rename, fsync = os.rename, os.fsync
    flushed = []

    def move_file_ex(source, target):  # os.rename on Windows never replaces
        if os.path.lexists(target):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target))
        rename(source, target)

    def record(descriptor):
        flushed.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        return fsync(descriptor)

    monkeypatch.setattr(writer, "_WINDOWS", True)
    monkeypatch.setattr(writer, "_libc_renameat2", lambda: None)
    monkeypatch.setattr(writer.os, "rename", move_file_ex)
    monkeypatch.setattr(writer.os, "fsync", record)
    root = init_store(tmp_path / "store")
    first = write_archive(root, archive=ARCHIVE, response=response())
    second = write_archive(root, archive=ARCHIVE, response=response(etag='"v2"'))
    assert (first.status, second.status) == ("created", "relabeled")
    (root.root / CHMI_SLOT).mkdir(parents=True)
    observation = Observation(
        **{
            key: value
            for key, value in OBSERVATION.items()
            if key not in ("schema", "producer", "producer_version")
        }
    )
    path = writer._publish_observation(
        root.root, slot=CHMI_SLOT, observation=observation
    )
    written = path.read_bytes()
    later = replace(observation, seen_at="2026-10-19T18:30:00Z")
    assert writer._publish_observation(
        root.root, slot=CHMI_SLOT, observation=later
    ) == (path)
    assert path.read_bytes() == written
    assert flushed and not any(flushed)  # files only: Windows cannot open directories


@pytest.mark.usefixtures("publication")
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
    with pytest.raises(IMGWCancelledError, match="Anulowano"):
        write_archive(root, archive=ARCHIVE, response=response(), cancel=lambda: True)
    assert old.exists()  # no operation began, so nothing was cleaned
    write_archive(root, archive=ARCHIVE, response=response())
    assert not old.exists() and new.exists()
    assert (
        len(fsynced) >= 4
    )  # marker, archive, sidecar, stage directory, published parent


@pytest.mark.usefixtures("publication")
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


def test_nested_kartograf_detection_without_import(tmp_path):
    foreign = tmp_path / "kartograf"
    foreign.mkdir()
    (foreign / "kartograf-project.json").write_text(
        json.dumps({"output_dir": "results"})
    )
    with pytest.raises(IMGWStoreError, match="Kartografa"):
        init_store(foreign / "results" / "imgw")
    unrelated = init_store(foreign / "separate")
    assert unrelated.root.exists()
    other = tmp_path / "nested"
    sidecar = other / "versions" / "item" / "sample.meta.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text('{"schema":"kartograf-meta/1"}')
    with pytest.raises(IMGWStoreError, match="Kartografa"):
        init_store(other / "child")
    with pytest.raises(IMGWStoreError, match="Kartografa"):
        init_store(other)


def test_foreign_or_nested_store_and_path_escape(tmp_path):
    root = init_store(tmp_path / "store")
    with pytest.raises(IMGWStoreError) as inside:
        init_store(root.root / "nested")
    with pytest.raises(IMGWStoreError) as around:
        init_store(tmp_path)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "notes.txt").write_text("x")
    with pytest.raises(IMGWStoreError, match="pustym") as not_empty:
        init_store(busy)
    for error in (inside, around, not_empty):
        assert error.value.code == "conflict"
        assert error.value.details == {"reason": "path_conflict"}
    unsafe = replace(ARCHIVE, server_path="dane_hydrologiczne/dobowe/../escape.zip")
    with pytest.raises(Exception, match="Niebezpieczna"):
        write_archive(root, archive=unsafe, response=response())


def test_symbolic_link_in_store_path_is_a_validation_error(tmp_path):
    init_store(tmp_path / "real")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    for call in (
        lambda: init_store(tmp_path / "link" / "inner"),
        lambda: open_store(tmp_path / "link"),
    ):
        with pytest.raises(IMGWStoreError, match="Dowiązanie") as error:
            call()
        assert error.value.code == "validation_error"


def test_identical_signal_after_relabel_is_unchanged(tmp_path):
    root = init_store(tmp_path / "store")
    first = write_archive(root, archive=ARCHIVE, response=response(etag='"e1"'))
    second = write_archive(root, archive=ARCHIVE, response=response(etag='"e2"'))
    third = write_archive(root, archive=ARCHIVE, response=response(etag='"e1"'))
    assert [first.status, second.status, third.status] == [
        "created",
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
    with pytest.raises(IMGWStoreConflictError, match="Uszkodzona wersja"):
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
    assert result.status == "created" and not old.exists()
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
    assert write_archive(root, archive=ARCHIVE, response=response()).status == (
        "created"
    )


def test_kartograf_versions_inside_store_still_detected(tmp_path):
    root = init_store(tmp_path / "store")
    sidecar = root.root / "foreign" / "versions" / "item" / "x.meta.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text('{"schema":"kartograf-meta/1"}')
    with pytest.raises(IMGWStoreError, match="Kartografa"):
        write_archive(root, archive=ARCHIVE, response=response())


def test_marker_is_created_exclusively_without_hard_links(tmp_path, monkeypatch):
    def refuse(source, target):
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(writer.os, "link", refuse)  # e.g. SMB, FAT
    path = tmp_path / "store"
    handle = init_store(path, created_at=datetime(2026, 10, 19, tzinfo=UTC))
    marker = path / "imgw-store.json"
    assert [item.name for item in path.iterdir()] == ["imgw-store.json"]
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "schema": "imgw-store/1",
        "created_by": f"imgwtools {__version__}",
        "created_at": "2026-10-19T00:00:00Z",
    }
    written = marker.read_bytes()
    assert init_store(path) == handle and marker.read_bytes() == written

    def fail(descriptor):
        raise OSError(errno.EIO, "Input/output error")

    interrupted = tmp_path / "interrupted"
    with monkeypatch.context() as patch:
        patch.setattr(writer.os, "fsync", fail)
        with pytest.raises(OSError, match="Input/output error"):
            init_store(interrupted)
    assert list(interrupted.iterdir()) == []  # no incomplete marker remains
    assert init_store(interrupted).root == interrupted


def test_init_waits_briefly_for_a_marker_being_written(tmp_path, monkeypatch):
    path = tmp_path / "store"
    path.mkdir()
    marker = path / "imgw-store.json"
    marker.touch()  # just created exclusively by a concurrent init_store

    def written_meanwhile(seconds):
        marker.write_text('{"schema":"imgw-store/1"}', encoding="utf-8")

    monkeypatch.setattr(writer.time, "sleep", written_meanwhile)
    assert init_store(path) == open_store(path)
    marker.write_bytes(b"")  # e.g. left by a crash between creating and writing
    monkeypatch.setattr(writer, "_MARKER_WAIT", 0.0)
    with pytest.raises(IMGWStoreError, match="Nieczytelny znacznik"):
        init_store(path)


@pytest.mark.usefixtures("publication")
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
    with pytest.raises(IMGWValidationError, match="RRRR-MM-DDTGG:MM:SSZ"):
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
        "created",
        "unchanged",
        "relabeled",
        "created",
        "unchanged",
    ]
