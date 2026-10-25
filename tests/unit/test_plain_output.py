"""Plain mode and store mode of the writing commands (DEV §19, ADR-007).

``datasets download`` writes ordinary files with ``output_dir`` or versions into
the store with ``root`` (the default root when neither is given); the plain
rules are the preflight with every offending path, the staging directory, the
atomic ``os.replace``, ``force``, the refusal of a store as output and the
``files[]`` of the result.
"""

import errno
import hashlib
import os
from pathlib import Path

import pytest

from imgwtools import (
    check_command,
    init_store,
    run_command,
    sync_pmaxtp,
    sync_store,
    validate_command,
)
from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWError, IMGWValidationError
from imgwtools.fetch import download_archives
from imgwtools.testing import build_fixture_store
from tests.contract.support import V1, FakeImgw

ARCHIVES = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
SEMIANNUAL = "pl.imgw.hydro_semiannual"
PHENOMENA = "pl.imgw.hydro_phenomena"
FILES = archive_files(SEMIANNUAL, years=2024)  # polr_H, polr_Q, polr_T


def record(respx_mock, files=FILES):
    """Answer every file of ``files`` with its fixture archive."""
    for archive in files:
        body = ARCHIVES / FILES[0].server_path
        respx_mock.get(archive.url).respond(content=body.read_bytes())


def names(directory: Path) -> list[str]:
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    )


@pytest.fixture
def home(monkeypatch, tmp_path):
    """No IMGW_ROOT, an empty nogat.toml and a data directory of the test."""
    for name in ("IMGW_ROOT", "NOGAT_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "nogat.toml"))
    monkeypatch.setenv("IMGW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# Plain mode: files, preflight, force
# --------------------------------------------------------------------------


def test_a_plain_download_lists_what_it_wrote_with_the_hash_of_the_bytes(
    respx_mock, tmp_path
):
    record(respx_mock)
    report = download_archives(SEMIANNUAL, years=2024, output_dir=tmp_path / "out")

    assert (report.mode, report.root) == ("plain", None)
    assert report.output_dir == tmp_path / "out"
    assert [file.path for file in report.files] == [item.path for item in report.items]
    for file in report.files:
        data = file.path.read_bytes()
        assert (file.size_bytes, file.sha256, file.status) == (
            len(data),
            hashlib.sha256(data).hexdigest(),
            "written",
        )
    # Ordinary files only: no sidecar, no staging directory left behind.
    assert names(tmp_path / "out") == sorted(a.server_path for a in FILES)
    assert not (tmp_path / "out" / ".imgw-incoming").exists()


def test_an_existing_target_refuses_the_whole_call_before_any_request(
    respx_mock, tmp_path
):
    record(respx_mock)
    out = tmp_path / "out"
    download_archives(SEMIANNUAL, years=2024, params=["Q"], output_dir=out)
    before = names(out)
    requests = respx_mock.calls.call_count

    with pytest.raises(IMGWError) as error:
        download_archives(SEMIANNUAL, years=2024, output_dir=out)

    assert error.value.code == "conflict"
    assert error.value.details["reason"] == "output_exists"
    assert error.value.details["paths"] == [str(out / FILES[1].server_path)]
    assert respx_mock.calls.call_count == requests  # not a byte was transferred
    assert names(out) == before


def test_force_replaces_the_existing_targets_and_deletes_nothing_else(
    respx_mock, tmp_path
):
    record(respx_mock)
    out = tmp_path / "out"
    first = download_archives(SEMIANNUAL, years=2024, params=["Q"], output_dir=out)
    other = out / "notes.txt"
    other.write_text("mine", encoding="utf-8")
    first.files[0].path.write_bytes(b"stale")

    report = download_archives(SEMIANNUAL, years=2024, output_dir=out, force=True)

    assert [file.status for file in report.files] == ["written", "replaced", "written"]
    assert first.files[0].path.read_bytes() != b"stale"
    assert other.read_text(encoding="utf-8") == "mine"


def test_a_directory_that_is_or_lies_in_a_store_is_refused_before_any_request(
    respx_mock, tmp_path
):
    record(respx_mock)
    store = tmp_path / "store"
    download_archives(SEMIANNUAL, years=2024, root=store)
    requests = respx_mock.calls.call_count

    for output in (store, store / "archives"):
        with pytest.raises(IMGWError) as error:
            download_archives(SEMIANNUAL, years=2024, output_dir=output)
        assert error.value.code == "conflict"
        assert error.value.details == {
            "reason": "output_in_store",
            "paths": [str(output)],  # the directory, not each of its targets
        }
        assert "--root" in error.value.detail
    assert respx_mock.calls.call_count == requests
    assert not (store / ".imgw-incoming").exists()


def test_a_pmaxtp_sync_into_a_store_is_refused_before_the_request_that_names_the_cell(
    respx_mock, tmp_path
):
    store = tmp_path / "store"
    init_store(store)

    # No indices are given, so the names come from the answer: the directory is refused first.
    with pytest.raises(IMGWError) as error:
        sync_pmaxtp(output_dir=store / "plain", latitude=52.0, longitude=20.0)

    assert error.value.details == {
        "reason": "output_in_store",
        "paths": [str(store / "plain")],
    }
    assert respx_mock.calls.call_count == 0


def test_a_marker_of_kartograf_counts_as_a_store_too(respx_mock, tmp_path):
    record(respx_mock)
    foreign = tmp_path / "kartograf"
    foreign.mkdir()
    (foreign / "kartograf-store.json").write_text("{}", encoding="utf-8")

    with pytest.raises(IMGWError) as error:
        download_archives(SEMIANNUAL, years=2024, output_dir=foreign / "plain")

    assert error.value.details["reason"] == "output_in_store"
    assert not (foreign / "plain").exists()


def test_plain_download_needs_no_hard_links(respx_mock, tmp_path, monkeypatch):
    # FAT, exFAT and SMB cannot link: the plain mode never calls os.link.
    def refuse(*args, **kwargs):
        raise OSError(errno.EPERM, "hard links are not supported")

    monkeypatch.setattr(os, "link", refuse)
    record(respx_mock)

    report = download_archives(SEMIANNUAL, years=2024, output_dir=tmp_path / "fat")

    assert [file.status for file in report.files] == ["written"] * 3


def test_a_cancelled_download_leaves_no_staging_directory(respx_mock, tmp_path):
    record(respx_mock)
    answers = iter([False, True])

    report = download_archives(
        SEMIANNUAL,
        years=2024,
        output_dir=tmp_path / "out",
        cancel=lambda: next(answers),
    )

    assert report.cancelled is True
    assert [file.status for file in report.files] == ["written"]
    assert not (tmp_path / "out" / ".imgw-incoming").exists()


# --------------------------------------------------------------------------
# One target at a time, and the store as the default
# --------------------------------------------------------------------------


def test_output_dir_and_root_exclude_each_other(tmp_path):
    for call in (
        lambda: download_archives(
            SEMIANNUAL, years=2024, output_dir=tmp_path / "a", root=tmp_path / "b"
        ),
        lambda: validate_command(
            "datasets download",
            options={
                "dataset": SEMIANNUAL,
                "years": 2024,
                "output_dir": tmp_path / "a",
                "root": tmp_path / "b",
            },
        ),
    ):
        with pytest.raises(IMGWValidationError) as error:
            call()
        assert error.value.details["reason"] == "exclusive_options"
        assert error.value.details["options"] == ["output_dir", "root"]
        assert error.value.details["option"] == "root"
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


def test_without_a_target_the_download_goes_to_the_store_of_the_default_root(
    respx_mock, home
):
    record(respx_mock)

    outcome = run_command(
        "datasets download", options={"dataset": SEMIANNUAL, "years": 2024}
    )

    root = home / "data" / "imgw"
    assert outcome.status == "ok"
    assert (outcome.result.mode, outcome.result.root) == ("store", root)
    assert (root / "imgw-store.json").is_file()
    assert {file.status for file in outcome.result.files} == {"new"}
    assert all(file.path.is_relative_to(root) for file in outcome.result.files)
    assert not (home / "data").joinpath("imgw", ".imgw-incoming").exists()


def test_a_store_download_reports_versions_and_never_overwrites(respx_mock, tmp_path):
    record(respx_mock)
    root = tmp_path / "store"

    first = download_archives(SEMIANNUAL, years=2024, root=root)
    second = download_archives(SEMIANNUAL, years=2024, root=root, force=True)

    assert [file.status for file in first.files] == ["new"] * 3
    assert [file.status for file in second.files] == ["unchanged"] * 3
    assert [f.path for f in second.files] == [f.path for f in first.files]
    for file in first.files:
        assert file.sha256 == hashlib.sha256(file.path.read_bytes()).hexdigest()
        assert file.size_bytes == file.path.stat().st_size


def test_a_dataset_that_is_download_only_has_no_place_in_the_store(
    respx_mock, tmp_path
):
    (archive,) = archive_files(PHENOMENA, years=2024)
    respx_mock.get(archive.url).respond(
        content=(ARCHIVES / FILES[0].server_path).read_bytes()
    )
    options = {"dataset": PHENOMENA, "years": 2024}

    with pytest.raises(IMGWValidationError) as error:
        run_command("datasets download", options={**options, "root": tmp_path / "s"})
    assert error.value.details["reason"] == "not_in_store"
    assert error.value.details["option"] == "dataset"
    assert "--output-dir" in error.value.detail
    assert not (tmp_path / "s").exists()

    outcome = run_command(
        "datasets download", options={**options, "output_dir": tmp_path / "plain"}
    )
    assert outcome.status == "ok"
    assert [file.status for file in outcome.result.files] == ["written"]


# --------------------------------------------------------------------------
# store sync and pmaxtp sync in plain mode
# --------------------------------------------------------------------------


def test_a_plain_sync_writes_the_selected_archives_without_a_freshness_check(
    respx_mock, tmp_path
):
    record(respx_mock)  # a HEAD request would be "not mocked" and fail the test
    options = {"datasets": SEMIANNUAL, "years": 2024, "output_dir": tmp_path / "out"}

    outcome = run_command("store sync", options=options)

    assert outcome.status == "ok"
    assert [item.status for item in outcome.result.items] == ["new"] * 3
    assert [file.status for file in outcome.result.files] == ["written"] * 3
    assert outcome.result.series == ()
    assert names(tmp_path / "out") == sorted(a.server_path for a in FILES)

    with pytest.raises(IMGWError) as error:
        run_command("store sync", options=options)
    assert error.value.details["reason"] == "output_exists"
    assert len(error.value.details["paths"]) == 3

    forced = run_command("store sync", options={**options, "force": True})
    assert [file.status for file in forced.result.files] == ["replaced"] * 3
    plan = check_command("store sync", options=options)
    assert plan.status == "ok"
    assert {action.action for action in plan.result.actions} == {"conflict"}


@pytest.mark.parametrize("option", ["plan", "series"])
def test_options_that_act_on_versions_name_root_when_given_with_output_dir(
    option, tmp_path
):
    values = {"plan": tmp_path / "plan.json", "series": False}
    options = {"datasets": SEMIANNUAL, "years": 2024, "output_dir": tmp_path / "out"}
    options[option] = values[option]
    if option == "plan":
        del options["datasets"], options["years"]

    with pytest.raises(IMGWValidationError) as error:
        validate_command("store sync", options=options)
    assert error.value.details["reason"] == "store_only_option"
    assert error.value.details["option"] == option

    with pytest.raises(IMGWValidationError) as direct:
        sync_store(
            output_dir=tmp_path / "out",
            datasets=[SEMIANNUAL],
            years=2024,
            **{option: values[option]},
        )
    assert direct.value.details["reason"] == "store_only_option"
    assert not (tmp_path / "out").exists()


def test_a_task_of_a_project_takes_no_output_dir(tmp_path):
    with pytest.raises(IMGWValidationError) as error:
        validate_command(
            "project add",
            options={
                "project_dir": tmp_path,
                "name": "pobranie",
                "command": "datasets download",
                "options": {"dataset": SEMIANNUAL, "years": 2024, "output_dir": "x"},
            },
        )
    assert error.value.details["reason"] == "store_only_option"
    assert error.value.details["option"] == "options"


def test_a_plain_pmaxtp_sync_writes_the_cell_and_the_raw_answer(respx_mock, tmp_path):
    FakeImgw(respx_mock).publish_pmaxtp("pmaxtp_pot_first")
    out = tmp_path / "out"
    point = {"latitude": 52.23, "longitude": 21.01}

    plan = check_command("pmaxtp sync", options={**point, "output_dir": out})
    assert [(a.status, a.action) for a in plan.result.actions] == [
        ("unverifiable", None)
    ]

    result = sync_pmaxtp(output_dir=out, **point)

    assert result.status == "new"
    assert names(out) == ["POT/751_317/cell.json", "POT/751_317/response.json"]
    assert [file.path for file in result.files] == [
        out / "POT/751_317/cell.json",
        out / "POT/751_317/response.json",
    ]
    for file in result.files:
        data = file.path.read_bytes()
        assert (file.size_bytes, file.sha256, file.status) == (
            len(data),
            hashlib.sha256(data).hexdigest(),
            "written",
        )
    assert not (out / ".imgw-incoming").exists()

    known = {**point, "ind_x": 751, "ind_y": 317, "output_dir": out}
    planned = check_command("pmaxtp sync", options=known)
    assert {a.action for a in planned.result.actions} == {"conflict"}
    with pytest.raises(IMGWError) as error:
        sync_pmaxtp(output_dir=out, ind_x=751, ind_y=317, **point)
    assert error.value.details["reason"] == "output_exists"
    assert len(error.value.details["paths"]) == 2
    forced = sync_pmaxtp(output_dir=out, force=True, **point)
    assert [file.status for file in forced.files] == ["replaced", "replaced"]


# --------------------------------------------------------------------------
# files[] of the store reports
# --------------------------------------------------------------------------


def test_the_store_reports_list_their_versions_as_files(respx_mock, tmp_path):
    FakeImgw(respx_mock).publish_pmaxtp("pmaxtp_pot_first")
    root = build_fixture_store(tmp_path / "store").root
    point = {"latitude": 52.23, "longitude": 21.01}

    first = sync_pmaxtp(root, **point)
    again = sync_pmaxtp(root, **point)
    series = run_command(
        "series build", options={"root": root, "dataset": "pl.imgw.hydro_daily"}
    )

    assert [f.status for f in first.files] == ["new"]
    assert [f.status for f in again.files] == ["unchanged"]
    assert first.files[0].path == first.version == again.files[0].path
    (file,) = series.result.files
    assert file.path == series.result.version
    assert file.status == series.result.status
    assert file.sha256 == hashlib.sha256(file.path.read_bytes()).hexdigest()
    assert file.size_bytes == file.path.stat().st_size


def test_a_store_sync_without_a_target_uses_the_default_root(home, respx_mock):
    init_store(home / "data" / "imgw")
    imgw = FakeImgw(respx_mock)
    for archive in FILES:
        imgw.publish(archive, V1, (ARCHIVES / archive.server_path).read_bytes())

    outcome = run_command(
        "store sync", options={"datasets": SEMIANNUAL, "years": 2024, "series": False}
    )

    assert outcome.status == "ok"
    assert {file.status for file in outcome.result.files} == {"new"}
    assert all(
        file.path.is_relative_to(home / "data" / "imgw")
        for file in outcome.result.files
    )
