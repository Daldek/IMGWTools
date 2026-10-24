"""Export of stored archive versions: golden lines, one plain file, conflicts, cancellation."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from imgwtools.datasets import archive_files
from imgwtools.exceptions import (
    IMGWCancelledError,
    IMGWError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.models import NormalizedRecord
from imgwtools.store import export_archive, init_store, write_archive

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
# Golden files: output of the former ``imgw store read`` command, saved before the change.
GOLDEN_DIR = FIXTURES.parent / "export_golden"
GOLDEN = {
    "hydro_daily_2024": ("pl.imgw.hydro_daily", [2024], None),
    "meteo_precip_daily_2001_01": ("pl.imgw.meteo_precip_daily", [2001], [1]),
    "hydro_semiannual_2024": ("pl.imgw.hydro_semiannual", [2024], None),
}


def stored(root, name):
    """Store the fixture archive of a golden case; return its version directory."""
    dataset, years, months = GOLDEN[name]
    archive = archive_files(dataset, years=years, months=months)[0]
    data = (FIXTURES / "archives" / archive.server_path).read_bytes()
    response = DownloadResult(data, archive.url, None, None, len(data))
    return write_archive(root, archive=archive, response=response).path.parent


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


@pytest.mark.parametrize("format", ["csv", "jsonl"])
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_lines_and_file_equal_the_former_store_read_output(
    root, tmp_path, name, format
):
    golden = (GOLDEN_DIR / f"store_read_{name}.{format}").read_bytes()
    version = stored(root, name)
    assert "".join(export_archive(version, format=format)).encode("utf-8") == golden

    report = export_archive(version, format=format, output=tmp_path / f"out.{format}")

    target = tmp_path / f"out.{format}"
    assert report.output == target and target.read_bytes() == golden
    assert [(f.path, f.size_bytes, f.sha256, f.status) for f in report.files] == [
        (target, len(golden), hashlib.sha256(golden).hexdigest(), "written")
    ]


def test_jsonl_objects_carry_the_normalized_record_fields(root):
    version = stored(root, "hydro_semiannual_2024")
    objects = [json.loads(line) for line in export_archive(version, format="jsonl")]
    fields = [field.name for field in dataclasses.fields(NormalizedRecord)]
    assert objects and all(list(item) == fields for item in objects)


def test_version_relative_to_root_and_license_terms_before_the_first_line(root):
    version = stored(root, "hydro_daily_2024")
    events = []
    lines = export_archive(
        version.relative_to(root),
        root=root,
        on_notice=lambda notice: events.append(notice.code),
        on_progress=lambda progress: events.append(progress.current),
    )
    assert events == ["license_terms"]
    assert "".join(lines) == "".join(export_archive(version))
    assert events == ["license_terms", 3]


def test_an_existing_output_is_a_conflict_that_force_replaces(root, tmp_path):
    version = stored(root, "hydro_daily_2024")
    target, neighbour = tmp_path / "out.csv", tmp_path / "other.csv"
    target.write_bytes(b"previous")
    neighbour.write_bytes(b"mine")

    with pytest.raises(IMGWError) as error:
        export_archive(version, output=target)

    assert error.value.code == "conflict"
    assert error.value.details == {"reason": "output_exists", "paths": [str(target)]}
    assert target.read_bytes() == b"previous"

    report = export_archive(version, output=target, force=True)

    assert [file.status for file in report.files] == ["replaced"]
    assert target.read_bytes() == "".join(export_archive(version)).encode("utf-8")
    assert neighbour.read_bytes() == b"mine"
    # No staging directory is left beside the output.
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "other.csv",
        "out.csv",
        "store",
    ]


def test_an_output_in_a_store_of_any_tool_is_a_conflict_without_writing(root, tmp_path):
    version = stored(root, "hydro_daily_2024")
    foreign = tmp_path / "kartograf"
    foreign.mkdir()
    (foreign / "kartograf-store.json").write_text("{}", encoding="utf-8")

    for target in (version.parent / "export.csv", foreign / "deeper" / "export.csv"):
        with pytest.raises(IMGWError) as error:
            export_archive(version, output=target)

        assert error.value.code == "conflict"
        assert error.value.details == {
            "reason": "output_in_store",
            "paths": [str(target)],
        }
        # An export has no store mode: the hint says so instead of naming --root.
        assert "--root" not in error.value.detail
        assert not target.exists()
    assert not (version.parent / ".imgw-incoming").exists()
    assert not (foreign / "deeper").exists()


def test_a_missing_directory_is_created_and_a_directory_is_no_file(root, tmp_path):
    version = stored(root, "hydro_daily_2024")

    report = export_archive(version, output=tmp_path / "new" / "deeper" / "out.csv")

    assert report.output.is_file()
    with pytest.raises(IMGWValidationError) as error:
        export_archive(version, output=tmp_path)
    assert error.value.details["option"] == "output"


def test_force_without_output_has_nothing_to_replace(root):
    version = stored(root, "hydro_daily_2024")

    with pytest.raises(IMGWValidationError) as error:
        export_archive(version, force=True)

    assert error.value.details == {"option": "output"}


def test_unknown_format_lists_the_allowed_ones(root):
    version = stored(root, "hydro_daily_2024")
    with pytest.raises(IMGWValidationError) as error:
        export_archive(version, format="parquet")
    assert error.value.details["allowed"] == ["csv", "jsonl"]


def test_missing_version_is_not_found(root):
    with pytest.raises(IMGWStoreError) as error:
        export_archive(root / "archives" / "missing.zip")
    assert error.value.code == "not_found"


def test_cancel_leaves_the_target_untouched_without_staging_files(root, tmp_path):
    version = stored(root, "meteo_precip_daily_2001_01")
    target = tmp_path / "out.csv"
    target.write_bytes(b"previous")
    calls = []

    def cancel_on_second_check():
        calls.append(None)
        return len(calls) >= 2

    for cancel in (lambda: True, cancel_on_second_check):
        with pytest.raises(IMGWCancelledError) as error:
            export_archive(version, output=target, force=True, cancel=cancel)
        assert error.value.code == "cancelled"
    assert len(calls) == 2
    assert target.read_bytes() == b"previous"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out.csv", "store"]
    with pytest.raises(IMGWCancelledError):
        export_archive(version, cancel=lambda: True)
