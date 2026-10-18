"""Offline reading of stored station lists and archive versions (SHA-verified)."""

import csv
import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from imgwtools import StationListEntry, read_archive, read_station_list
from imgwtools._parsing import normalize_archive
from imgwtools.cli.main import app
from imgwtools.commands import run_command
from imgwtools.datasets import archive_files, station_source_files
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
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
    with pytest.raises(IMGWDataError, match="Suma kontrolna"):
        read_station_list(root, kind="hydro")


def test_station_list_kind_is_validated(root):
    with pytest.raises(IMGWValidationError):
        read_station_list(root, kind="synop")  # type: ignore[arg-type]


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
    with pytest.raises(IMGWDataError, match="Suma kontrolna"):
        read_archive(version.parent)


def test_read_archive_rejects_station_list_versions(root):
    version = store_file(root, METEO_LIST)
    with pytest.raises(
        IMGWValidationError, match=r"read_station_list\(root, kind='meteo'\)"
    ):
        read_archive(version.parent)


def test_store_read_cli_streams_the_same_records_as_python(root, tmp_path):
    version = store_file(root, PRECIP_2001).parent
    records = list(read_archive(version))
    printed = RUNNER.invoke(app, ["store", "read", "--version", str(version)])
    assert printed.exit_code == 0, printed.output
    # stdout_bytes: Result.stdout folds the RFC 4180 CRLF row terminators to LF.
    assert printed.stdout_bytes.decode("utf-8") == "".join(
        run_command("store read", options={"version": version})
    )
    rows = list(csv.DictReader(io.StringIO(printed.stdout)))
    assert len(rows) == len(records)
    accumulated = next(r for r in records if r.measurements["P"].flag == "accumulated")
    row = rows[records.index(accumulated)]
    assert (row["station_code"], row["date"], row["P_flag"]) == (
        accumulated.station_code,
        accumulated.date.isoformat(),
        "accumulated",
    )
    assert float(row["P [mm]"]) == accumulated.measurements["P"].value
    assert row["precip_type"] == (accumulated.attributes["precip_type"] or "")

    target = tmp_path / "out" / "opad.jsonl"
    target.parent.mkdir()
    written = RUNNER.invoke(
        app,
        [
            "store",
            "read",
            "--version",
            str(version),
            "--format",
            "jsonl",
            "--path",
            str(target),
        ],
    )
    assert written.exit_code == 0, written.output
    assert written.stdout.strip() == str(target)
    assert [p.name for p in target.parent.iterdir()] == ["opad.jsonl"]
    lines = [
        json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
    ]
    assert [(d["station_code"], d["date"], d["measurements"]["P"]) for d in lines] == [
        (
            r.station_code,
            r.date.isoformat(),
            {"value": r.measurements["P"].value, "flag": r.measurements["P"].flag},
        )
        for r in records
    ]


def test_store_read_cli_reports_station_list_version_in_polish(root):
    version = store_file(root, HYDRO_LIST).parent
    result = RUNNER.invoke(app, ["store", "read", "--version", str(version)])
    assert result.exit_code == 1
    assert "read_station_list" in result.stderr and not result.stdout
