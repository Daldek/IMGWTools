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

from imgwtools.datasets import archive_files
from imgwtools.exceptions import (
    IMGWCancelledError,
    IMGWStoreConflictError,
    IMGWStoreError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store import init_store, open_store, write_archive, writer

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVE = archive_files("pl.imgw.hydro_daily", years=[2024])[0]
DATA = (FIXTURES / "archives" / ARCHIVE.server_path).read_bytes()


def response(*, etag='"hydro-v1"', modified="Sat, 17 Oct 2026 12:00:00 GMT", data=DATA):
    return DownloadResult(data, ARCHIVE.url, etag, modified, len(data))


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


def test_no_atomic_rename_is_explicit(tmp_path, monkeypatch):
    root = init_store(tmp_path / "store")
    monkeypatch.setattr(writer.sys, "platform", "unsupported")
    with pytest.raises(IMGWStoreConflictError, match="atomowego"):
        write_archive(root, archive=ARCHIVE, response=response())
    assert not list((root.root / "archives").rglob("*.zip"))


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


def test_marker_without_hard_links_is_store_error(tmp_path, monkeypatch):
    def refuse(source, target):
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(writer.os, "link", refuse)
    path = tmp_path / "store"
    with pytest.raises(IMGWStoreError, match="dowiązanie twarde") as error:
        init_store(path)
    assert error.value.code == "conflict"
    assert not (path / "imgw-store.json").exists()
    assert not list(path.glob(".imgw-store.json.*.tmp"))
