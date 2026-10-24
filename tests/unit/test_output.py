"""Plain output: the target list, the staging directory and its cleanup (DEV-19.6, DEV-19.7, DEV-19.11)."""

import errno
import hashlib
import os
import signal
import socket
import time

import pytest

from imgwtools.exceptions import IMGWError
from imgwtools.output import (
    STAGING,
    STORE_MARKERS,
    Staging,
    plan_plain,
    refuse,
    store_around,
    store_below,
)


def states(entries):
    return [(entry.path.name, entry.action, entry.reason) for entry in entries]


# --------------------------------------------------------------------------
# The target list (DEV-19.6, DEV-19.9)
# --------------------------------------------------------------------------


def test_an_existing_target_is_replaced_only_with_force_and_nothing_is_written(
    tmp_path,
):
    (tmp_path / "a.zip").write_bytes(b"old")
    names = ["a.zip", "sub/b.zip"]

    assert states(plan_plain(tmp_path, names, force=False)) == [
        ("a.zip", "conflict", "output_exists"),
        ("b.zip", "write", None),
    ]
    assert states(plan_plain(tmp_path, names, force=True)) == [
        ("a.zip", "replace", None),
        ("b.zip", "write", None),
    ]
    assert (tmp_path / "a.zip").read_bytes() == b"old"
    assert not (tmp_path / "sub").exists()


def test_duplicate_names_are_conflicts_even_with_force(tmp_path):
    entries = plan_plain(tmp_path, ["x/a.zip", "x/a.zip", "b.zip"], force=True)

    assert states(entries) == [
        ("a.zip", "conflict", "duplicate_output_name"),
        ("a.zip", "conflict", "duplicate_output_name"),
        ("b.zip", "write", None),
    ]


def test_refuse_lists_every_offending_path_under_the_first_reason(tmp_path):
    (tmp_path / "a.zip").write_bytes(b"1")
    (tmp_path / "b.zip").write_bytes(b"2")
    entries = plan_plain(tmp_path, ["a.zip", "b.zip", "c.zip", "c.zip"], force=False)

    with pytest.raises(IMGWError) as error:
        refuse(entries)

    assert error.value.code == "conflict"
    assert error.value.details["reason"] == "duplicate_output_name"
    assert error.value.details["paths"] == [
        str(tmp_path / name) for name in ("a.zip", "b.zip", "c.zip", "c.zip")
    ]


def test_existing_targets_alone_are_output_exists_with_all_paths(tmp_path):
    for name in ("a.zip", "b.zip"):
        (tmp_path / name).write_bytes(b"1")

    with pytest.raises(IMGWError) as error:
        refuse(plan_plain(tmp_path, ["a.zip", "b.zip", "c.zip"], force=False))

    assert error.value.details["reason"] == "output_exists"
    assert error.value.details["paths"] == [
        str(tmp_path / n) for n in ("a.zip", "b.zip")
    ]
    assert "--force" in error.value.detail


def test_a_plan_without_conflicts_passes(tmp_path):
    refuse(plan_plain(tmp_path, ["a.zip", "sub/b.zip"], force=False))


# --------------------------------------------------------------------------
# A store is no output directory (DEV-19.11)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("marker", STORE_MARKERS)
def test_a_directory_that_is_or_lies_in_a_store_of_any_tool_is_refused(
    tmp_path, marker
):
    (tmp_path / "store" / "deep").mkdir(parents=True)
    (tmp_path / "store" / marker).write_text("{}")

    for directory in (tmp_path / "store", tmp_path / "store" / "deep" / "er"):
        entries = plan_plain(directory, ["a.zip"], force=True)
        assert states(entries) == [("a.zip", "conflict", "output_in_store")]
        with pytest.raises(IMGWError) as error:
            refuse(entries)
        assert error.value.details["reason"] == "output_in_store"
        assert "--root" in error.value.detail


def test_a_subdirectory_the_write_would_enter_must_not_hold_a_marker(tmp_path):
    (tmp_path / "out" / "inner").mkdir(parents=True)
    (tmp_path / "out" / "inner" / "imgw-store.json").write_text("{}")

    entering = plan_plain(tmp_path / "out", ["inner/x.zip"], force=False)
    beside = plan_plain(tmp_path / "out", ["other/x.zip"], force=False)

    assert states(entering) == [("x.zip", "conflict", "output_in_store")]
    assert states(beside) == [("x.zip", "write", None)]


def test_a_directory_with_a_store_elsewhere_below_it_is_a_fine_output(tmp_path):
    # <data_dir> holds the default store <data_dir>/imgw; writing files to <data_dir> is not
    # writing into that store.
    (tmp_path / "imgw").mkdir()
    (tmp_path / "imgw" / "imgw-store.json").write_text("{}")

    assert states(plan_plain(tmp_path, ["a.zip"], force=False)) == [
        ("a.zip", "write", None)
    ]
    assert store_below(tmp_path) == tmp_path / "imgw"
    assert store_around(tmp_path) is None


# --------------------------------------------------------------------------
# The staging directory (DEV-19.7, DEV-19.8)
# --------------------------------------------------------------------------


def test_a_file_is_hashed_while_it_is_written_and_moved_into_place(tmp_path):
    out = tmp_path / "out"

    with Staging(out) as staging:
        host, pid, token = staging.path.name.rsplit("_", 2)
        assert (host, pid) == (socket.gethostname(), str(os.getpid()))
        assert token and staging.path.parent == out / STAGING
        staged, size, digest = staging.write([b"ab", b"cd"])
        result = staging.commit(staged, out / "sub" / "f.bin", size, digest)

    assert (result.status, result.size_bytes) == ("written", 4)
    assert result.sha256 == hashlib.sha256(b"abcd").hexdigest()
    assert (out / "sub" / "f.bin").read_bytes() == b"abcd"
    assert not (out / STAGING).exists()
    assert sorted(path.name for path in out.iterdir()) == ["sub"]  # only data files


def test_an_existing_target_is_replaced_atomically_and_reported_replaced(tmp_path):
    (tmp_path / "f.bin").write_bytes(b"old")

    with Staging(tmp_path) as staging:
        staged, size, digest = staging.write([b"new"])
        result = staging.commit(staged, tmp_path / "f.bin", size, digest)

    assert result.status == "replaced"
    assert (tmp_path / "f.bin").read_bytes() == b"new"


def test_the_staging_directory_goes_when_the_block_fails_and_the_target_stays(tmp_path):
    (tmp_path / "f.bin").write_bytes(b"old")

    with pytest.raises(RuntimeError), Staging(tmp_path) as staging:
        staging.write([b"half"])
        raise RuntimeError("transfer failed")

    assert not (tmp_path / STAGING).exists()
    assert (tmp_path / "f.bin").read_bytes() == b"old"


def test_sigint_and_sigterm_remove_the_staging_directory(tmp_path):
    out = tmp_path / "out"
    before = signal.getsignal(signal.SIGTERM)

    with pytest.raises(KeyboardInterrupt), Staging(out) as staging:
        staging.write([b"x"])
        signal.raise_signal(signal.SIGINT)
    assert not (out / STAGING).exists()

    with pytest.raises(SystemExit) as stopped, Staging(out) as staging:
        staging.write([b"x"])
        signal.raise_signal(signal.SIGTERM)
    assert stopped.value.code == 128 + signal.SIGTERM
    assert not (out / STAGING).exists()
    assert signal.getsignal(signal.SIGTERM) == before  # the handler is put back


def test_leftovers_older_than_24_hours_are_removed_by_the_next_run(tmp_path):
    out = tmp_path / "out"
    old, fresh = out / STAGING / "host_1_dead", out / STAGING / "host_2_live"
    for leftover in (old, fresh):
        leftover.mkdir(parents=True)
        (leftover / "000001").write_bytes(b"x")
    stale = time.time() - 25 * 60 * 60
    os.utime(old, (stale, stale))

    with Staging(out):
        assert not old.exists()
        assert fresh.exists()  # the directory of a run that may be alive stays
    assert fresh.exists()


def test_plain_output_needs_no_hard_links(tmp_path, monkeypatch):
    # FAT, exFAT and SMB cannot link: the store fails there, plain output must not.
    def no_link(*args, **kwargs):
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_link)

    with Staging(tmp_path) as staging:
        staged, size, digest = staging.write([b"data"])
        result = staging.commit(staged, tmp_path / "a" / "f.bin", size, digest)

    assert result.status == "written"
    assert (tmp_path / "a" / "f.bin").read_bytes() == b"data"
