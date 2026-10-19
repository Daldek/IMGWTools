"""Tests of download_archives on recorded IMGW answers (respx-mocked HTTP)."""

from pathlib import Path

import httpx
import pytest

from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWValidationError
from imgwtools.fetch import download_archives
from imgwtools.store.types import Notice, Progress

ARCHIVES = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
SEMIANNUAL = "pl.imgw.hydro_semiannual"
FILES = archive_files(SEMIANNUAL, years=2024)  # polr_H, polr_Q, polr_T


def _record(respx_mock, *, failing: str | None = None) -> None:
    for archive in FILES:
        if archive.server_path.endswith(f"{failing}_2024.zip"):
            respx_mock.get(archive.url).respond(503)
        else:
            body = (ARCHIVES / archive.server_path).read_bytes()
            respx_mock.get(archive.url).respond(content=body)


def _tree(directory: Path) -> list[str]:
    return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*"))


def test_files_land_under_server_path_with_slots(respx_mock, tmp_path):
    _record(respx_mock)
    report = download_archives(SEMIANNUAL, years="2024", output=tmp_path / "out")
    output = tmp_path / "out"
    assert report.output == output and not report.cancelled
    assert [item.slot for item in report.items] == [
        f"archive:{SEMIANNUAL}:2024/polr_{param}_2024.zip" for param in "HQT"
    ]
    for item, archive in zip(report.items, FILES, strict=True):
        assert item.status == "downloaded" and item.url == archive.url
        assert item.path == output / archive.server_path
        assert item.path.read_bytes() == (ARCHIVES / archive.server_path).read_bytes()
        assert (item.error, item.error_code) == (None, None)
    assert not [name for name in _tree(output) if name.endswith(".part")]


def test_meteo_monthly_slot_and_path_follow_the_folder(respx_mock, tmp_path):
    (archive,) = archive_files("pl.imgw.meteo_synop_monthly", years=1998)
    respx_mock.get(archive.url).respond(
        content=(ARCHIVES / FILES[0].server_path).read_bytes()
    )
    report = download_archives("meteo/miesieczne/synop", years=1998, output=tmp_path)
    (item,) = report.items
    assert item.slot == (
        "archive:pl.imgw.meteo_synop_monthly:1996_2000/1996_2000_m_s.zip"
    )
    assert item.path == (
        tmp_path / "dane_meteorologiczne/miesieczne/synop/1996_2000/1996_2000_m_s.zip"
    )


def test_daily_and_term_archives_of_one_name_never_collide(respx_mock, tmp_path):
    # dobowe/klimat and terminowe/klimat both publish 2001_01_k.zip (other bytes).
    daily, terms = "pl.imgw.meteo_climate_daily", "pl.imgw.meteo_climate_terms"
    climate = ARCHIVES / "dane_meteorologiczne" / "dobowe" / "klimat"
    bodies = {
        daily: (climate / "2001" / "2001_01_k.zip").read_bytes(),
        terms: (climate / "2004" / "2004_02_k.zip").read_bytes(),
    }
    for dataset, body in bodies.items():
        (archive,) = archive_files(dataset, years=2001, months=1)
        respx_mock.get(archive.url).respond(content=body)
    items = [
        item
        for dataset in bodies
        for item in download_archives(
            dataset, years=2001, months=1, output=tmp_path
        ).items
    ]
    assert [item.slot for item in items] == [
        f"archive:{daily}:2001/2001_01_k.zip",
        f"archive:{terms}:2001/2001_01_k.zip",
    ]
    assert [item.path.relative_to(tmp_path).as_posix() for item in items] == [
        "dane_meteorologiczne/dobowe/klimat/2001/2001_01_k.zip",
        "dane_meteorologiczne/terminowe/klimat/2001/2001_01_k.zip",
    ]
    assert [item.path.read_bytes() for item in items] == [bodies[daily], bodies[terms]]
    assert [name for name in _tree(tmp_path) if Path(name).suffix] == [
        "dane_meteorologiczne/dobowe/klimat/2001/2001_01_k.zip",
        "dane_meteorologiczne/terminowe/klimat/2001/2001_01_k.zip",
    ]


def test_http_error_fails_one_item_and_others_download(respx_mock, tmp_path):
    _record(respx_mock, failing="Q")
    report = download_archives(SEMIANNUAL, years=2024, output=tmp_path)
    assert [item.status for item in report.items] == [
        "downloaded",
        "failed",
        "downloaded",
    ]
    failed = report.items[1]
    assert failed.error_code == "source_unavailable"
    assert failed.path is None and "HTTP 503" in (failed.error or "")
    assert not (tmp_path / FILES[1].server_path).exists()
    assert report.cancelled is False


def test_corrupt_archive_is_data_error_item(respx_mock, tmp_path):
    for archive in FILES:
        respx_mock.get(archive.url).respond(content=b"<html>to nie zip</html>")
    report = download_archives(SEMIANNUAL, years=2024, params=["T"], output=tmp_path)
    (item,) = report.items
    assert (item.status, item.error_code) == ("failed", "data_error")
    assert _tree(tmp_path) == []


def test_write_failure_leaves_neither_file_nor_part(respx_mock, tmp_path, monkeypatch):
    _record(respx_mock)

    def refuse(source, target):
        raise PermissionError("brak prawa zapisu")

    monkeypatch.setattr("imgwtools.fetch.os.replace", refuse)
    report = download_archives(SEMIANNUAL, years=2024, params=["H"], output=tmp_path)
    (item,) = report.items
    assert (item.status, item.error_code, item.path) == ("failed", "io_error", None)
    assert [name for name in _tree(tmp_path) if Path(name).suffix] == []


def test_cancel_between_files_reports_rest_as_cancelled(respx_mock, tmp_path):
    _record(respx_mock)
    answers = iter([False, True])
    report = download_archives(
        SEMIANNUAL, years=2024, output=tmp_path, cancel=lambda: next(answers)
    )
    assert report.cancelled is True
    assert [item.status for item in report.items] == [
        "downloaded",
        "cancelled",
        "cancelled",
    ]
    assert all(item.path is None for item in report.items[1:])
    assert [name for name in _tree(tmp_path) if name.endswith(".zip")] == [
        FILES[0].server_path
    ]
    assert respx_mock.calls.call_count == 1


def test_license_notice_once_after_first_downloaded_file(respx_mock, tmp_path):
    _record(respx_mock, failing="H")
    events: list[object] = []
    download_archives(
        SEMIANNUAL,
        years=2024,
        output=tmp_path,
        on_progress=events.append,
        on_notice=events.append,
    )
    assert [
        event.code if isinstance(event, Notice) else event.status
        for event in events
        if isinstance(event, Notice | Progress)
    ] == ["failed", "downloaded", "license_terms", "downloaded"]


def test_no_license_notice_when_nothing_downloaded(respx_mock, tmp_path):
    for archive in FILES:
        respx_mock.get(archive.url).mock(side_effect=httpx.ConnectError)
    notices: list[Notice] = []
    report = download_archives(
        SEMIANNUAL, years=2024, output=tmp_path, on_notice=notices.append
    )
    assert {item.error_code for item in report.items} == {"source_unavailable"}
    assert notices == []


@pytest.mark.parametrize(
    "dataset, options, option",
    [
        ("pl.imgw.nieznany", {"years": 2024}, "dataset"),
        (SEMIANNUAL, {"years": "2024-x"}, "years"),
        ("pl.imgw.hydro_daily", {"years": 2024, "params": ["Q"]}, "params"),
    ],
)
def test_invalid_options_fail_before_any_request_or_directory(
    respx_mock, tmp_path, dataset, options, option
):
    with pytest.raises(IMGWValidationError) as error:
        download_archives(dataset, output=tmp_path / "out", **options)
    assert error.value.details["option"] == option
    assert not respx_mock.calls and not (tmp_path / "out").exists()
