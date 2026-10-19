"""download_archives for ČHMÚ candidates on recorded answers (respx).

Spec 2026-10-18 §4.4 and scenario (6) of §13.2: a candidate the server
answers with 404 is a successful ``not_published`` item. Synthetic files
only; codes 0-203-1-9… and 0-203-0-9… are not published by ČHMÚ.
"""

import json
from pathlib import Path

import httpx
import pytest

from imgwtools._version import __version__
from imgwtools.commands import _status
from imgwtools.datasets import archive_files, get_provider
from imgwtools.exceptions import IMGWValidationError
from imgwtools.fetch import download_archives
from imgwtools.store.types import Notice, Progress

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDING = json.loads((FIXTURES / "chmi_recordings.json").read_text(encoding="utf-8"))
CASES = {entry["case"]: entry for entry in RECORDING["interactions"]}
HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
S2 = "0-203-1-900002"  # 2004 and 2006 published, 2005 not
FULL, RAIN = "0-203-0-90001", "0-203-0-90000000002"  # four elements / SRA only


def body(entry):
    if "archive" in entry:
        return (FIXTURES / "archives" / entry["archive"]).read_bytes()
    return entry["body"].encode("utf-8")


def serve(router, *cases):
    for case in cases:
        entry = CASES[case]
        router.get(RECORDING["base_url"] + entry["path"]).mock(
            return_value=httpx.Response(
                entry["status"], headers=entry["headers"], content=body(entry)
            )
        )


def files(directory):
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    )


def test_unpublished_year_is_a_successful_not_published_item(respx_mock, tmp_path):
    serve(respx_mock, "h900002_2004_get", "h900002_2005_get", "h900002_2006_get")
    output = tmp_path / "out"
    events = []

    report = download_archives(
        HYDRO,
        years="2004-2006",
        stations=[S2],
        output=output,
        on_progress=events.append,
        on_notice=events.append,
    )

    candidates = archive_files(HYDRO, years="2004-2006", stations=[S2])
    assert [(item.slot, item.url) for item in report.items] == [
        (f"archive:{HYDRO}:H_{S2}_DQ_{year}.json", archive.url)
        for year, archive in zip((2004, 2005, 2006), candidates, strict=True)
    ]
    published, unpublished, later = report.items
    assert (unpublished.status, unpublished.path) == ("not_published", None)
    assert (unpublished.error, unpublished.error_code) == ("nieopublikowany", None)
    for item, case in ((published, "h900002_2004_get"), (later, "h900002_2006_get")):
        assert item.status == "downloaded"
        assert item.path == output / CASES[case]["path"]
        assert item.path.read_bytes() == body(CASES[case])  # bytes 1:1, no ZIP check
    assert files(output) == [
        CASES[case]["path"] for case in ("h900002_2004_get", "h900002_2006_get")
    ]
    assert not report.cancelled and _status(report) == "ok"
    assert [
        event.code if isinstance(event, Notice) else event.status
        for event in events
        if isinstance(event, Notice | Progress)
    ] == ["downloaded", "license_terms", "not_published", "downloaded"]
    provider = get_provider("CHMI")
    (notice,) = [event for event in events if isinstance(event, Notice)]
    assert notice.text == f"{provider.license.attribution}. {provider.notice}"
    assert {call.request.headers["User-Agent"] for call in respx_mock.calls} == {
        f"imgwtools/{__version__}"
    }


def test_meteo_station_files_are_four_elements_with_missing_ones_unpublished(
    respx_mock, tmp_path
):
    serve(
        respx_mock,
        "m90000000002_SRA_get",
        "m90000000002_T_get",
        "m90000000002_TMA_get",
        "m90000000002_TMI_get",
        *(f"m90001_{element}_get" for element in ("SRA", "T", "TMA", "TMI")),
    )

    report = download_archives(METEO, stations=[FULL, RAIN], output=tmp_path)

    assert [(item.slot.rsplit("/", 1)[1], item.status) for item in report.items] == [
        (f"dly-{RAIN}-SRA.csv", "downloaded"),
        (f"dly-{RAIN}-T.csv", "not_published"),
        (f"dly-{RAIN}-TMA.csv", "not_published"),
        (f"dly-{RAIN}-TMI.csv", "not_published"),
        *(
            (f"dly-{FULL}-{element}.csv", "downloaded")
            for element in ("SRA", "T", "TMA", "TMI")
        ),
    ]
    assert report.items[1].slot == f"archive:{METEO}:temperature/dly-{RAIN}-T.csv"
    assert len(files(tmp_path)) == 5


def test_only_404_is_unpublished_other_answers_fail_the_item(respx_mock, tmp_path):
    first, unpublished, last = archive_files(HYDRO, years="2004-2006", stations=[S2])
    respx_mock.get(first.url).respond(503)
    respx_mock.get(unpublished.url).respond(410)
    respx_mock.get(last.url).mock(side_effect=httpx.ConnectError("brak sieci"))
    notices = []

    report = download_archives(
        HYDRO,
        years="2004-2006",
        stations=[S2],
        output=tmp_path,
        on_notice=notices.append,
    )

    assert [(item.status, item.error_code) for item in report.items] == [
        ("failed", "source_unavailable"),
        ("not_published", None),
        ("failed", "source_unavailable"),
    ]
    assert report.items[0].error.startswith("Serwer ČHMÚ zwrócił HTTP 503")
    assert "ČHMÚ" in report.items[2].error
    assert files(tmp_path) == [] and notices == []


def test_cancel_reports_the_remaining_candidates(respx_mock, tmp_path):
    serve(respx_mock, "h900002_2004_get")
    answers = iter([False, True])

    report = download_archives(
        HYDRO,
        years="2004-2006",
        stations=[S2],
        output=tmp_path,
        cancel=lambda: next(answers),
    )

    assert [item.status for item in report.items] == [
        "downloaded",
        "cancelled",
        "cancelled",
    ]
    assert report.cancelled and len(respx_mock.calls) == 1


@pytest.mark.parametrize(
    ("dataset", "options", "option"),
    [
        (HYDRO, {"years": 2024}, "stations"),
        (HYDRO, {"stations": [S2]}, "years"),
        (HYDRO, {"years": 2024, "stations": ["149190310"]}, "stations"),
        (HYDRO, {"years": 2024, "stations": [S2], "months": [1]}, "months"),
        (METEO, {"stations": [FULL], "years": 2024}, "years"),
        ("pl.imgw.hydro_daily", {"years": 2024, "stations": [S2]}, "stations"),
        ("pl.imgw.hydro_daily", {}, "years"),
    ],
)
def test_invalid_options_fail_before_any_request_or_directory(
    respx_mock, tmp_path, dataset, options, option
):
    with pytest.raises(IMGWValidationError) as error:
        download_archives(dataset, output=tmp_path / "out", **options)
    assert error.value.details["option"] == option
    assert not respx_mock.calls and not (tmp_path / "out").exists()
