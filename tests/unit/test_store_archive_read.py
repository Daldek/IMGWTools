"""Offline reading of stored station lists and archive versions (SHA-verified)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from imgwtools import StationListEntry, read_archive, read_station_list
from imgwtools._parsing import normalize_archive
from imgwtools.cli.main import app
from imgwtools.datasets import archive_files, station_source_files
from imgwtools.exceptions import (
    ERROR_CODES,
    IMGWDataError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.store import init_store, write_archive

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
OLD = "Sat, 17 Oct 2026 12:00:00 GMT"
NEW = "Sun, 18 Oct 2026 12:00:00 GMT"
HYDRO_LIST, METEO_LIST = station_source_files()
DAILY_2024 = archive_files("pl.imgw.hydro_daily", years=[2024])[0]
PRECIP_2001 = archive_files("pl.imgw.meteo_precip_daily", years=[2001], months=[1])[0]
CLIMATE_1995 = archive_files("pl.imgw.meteo_climate_daily", years=[1995])[0]
RUNNER = CliRunner()


def store_file(root, archive, content=None, *, last_modified=OLD):
    """Write fixture bytes (or ``content``) of ``archive`` into the store; return the version file."""
    data = (
        content
        if content is not None
        else (FIXTURES / "archives" / archive.server_path).read_bytes()
    )
    response = DownloadResult(data, archive.url, '"x"', last_modified, len(data))
    return write_archive(root, archive=archive, response=response).path


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


def test_station_lists_round_trip_with_kind_and_family_columns(root):
    store_file(root, HYDRO_LIST)
    store_file(root, METEO_LIST)
    hydro = read_station_list(root, kind="hydro")
    meteo = read_station_list(root, kind="meteo")
    assert hydro[0] == StationListEntry(
        "hydro", "149190310", "Raba Górna", "Raba", "213", 12, None
    )
    assert [s.station_code for s in hydro] == ["149190310", "149190311", "149190312"]
    assert meteo == (
        StationListEntry("meteo", "123750000", "Warszawa", short_code="001"),
        StationListEntry("meteo", "123760000", "Stacja Bez Miejsca", short_code="002"),
    )


def test_station_list_reads_the_current_version_not_an_older_one(root):
    original = (FIXTURES / "archives" / HYDRO_LIST.server_path).read_bytes()
    store_file(root, HYDRO_LIST, original, last_modified=OLD)
    newer = original + "149190313,Nowa,Raba (213),015\r\n".encode("cp1250")
    store_file(root, HYDRO_LIST, newer, last_modified=NEW)
    codes = [s.station_code for s in read_station_list(root, kind="hydro")]
    assert codes[-1] == "149190313" and len(codes) == 4


def test_missing_station_list_names_the_dataset_not_the_file(root):
    store_file(root, HYDRO_LIST)
    with pytest.raises(IMGWStoreError, match="pl.imgw.meteo_stations") as error:
        read_station_list(root, kind="meteo")
    assert "wykaz" not in str(error.value)


def test_station_list_with_tampered_bytes_is_rejected(root):
    version = store_file(root, HYDRO_LIST)
    data = bytearray(version.read_bytes())
    data[0] = ord("2")  # same size, different SHA-256
    version.write_bytes(bytes(data))
    with pytest.raises(IMGWDataError, match="does not match the sidecar"):
        read_station_list(root, kind="hydro")


def test_station_list_kind_is_validated(root):
    with pytest.raises(IMGWValidationError):
        read_station_list(root, kind="synop")


@pytest.mark.parametrize("archive", [DAILY_2024, PRECIP_2001, CLIMATE_1995])
@pytest.mark.parametrize("given", ["directory", "file", "sidecar"])
def test_read_archive_equals_normalize_archive_on_raw_bytes(root, archive, given):
    version = store_file(root, archive)
    raw = (FIXTURES / "archives" / archive.server_path).read_bytes()
    path = {
        "directory": version.parent,
        "file": version,
        "sidecar": version.with_name(version.name + ".meta.json"),
    }[given]
    expected = list(normalize_archive(archive, data=raw))
    assert expected and list(read_archive(path)) == expected


def test_read_archive_detects_tampering_before_iteration(root):
    version = store_file(root, DAILY_2024)
    data = bytearray(version.read_bytes())
    data[-1] ^= 0xFF
    version.write_bytes(bytes(data))
    with pytest.raises(IMGWDataError, match="does not match the sidecar"):
        read_archive(version.parent)


def test_read_archive_rejects_station_list_versions(root):
    version = store_file(root, METEO_LIST)
    with pytest.raises(
        IMGWValidationError, match=r"read_station_list\(root, kind='meteo'\)"
    ):
        read_archive(version.parent)


def test_store_export_cli_rejects_a_station_list_version_with_guidance(root):
    version = store_file(root, HYDRO_LIST).parent
    result = RUNNER.invoke(app, ["store", "export", "--version", str(version)])
    assert result.stdout == ""
    error = json.loads(result.stderr.splitlines()[-1])
    assert error["code"] == "validation_error"
    assert "read_station_list(root, kind='hydro')" in error["detail"]
    assert result.exit_code == ERROR_CODES["validation_error"].exit_code
