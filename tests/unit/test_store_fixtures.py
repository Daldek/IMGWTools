"""Synthetic archive and offline HTTP-recording contract."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

ROOT = Path(__file__).parents[1] / "fixtures" / "store"
ARCHIVES = ROOT / "archives"


def test_synthetic_archives_are_readable_and_cover_source_variants():
    archives = list(ARCHIVES.rglob("*.zip"))
    assert len(archives) == 13
    names = {file.name for file in archives}
    assert {
        "codz_2022_01.zip",
        "codz_2023.zip",
        "codz_2024.zip",
        "mies_2024.zip",
        "1995_k.zip",
        "1995_o.zip",
        "2001_01_k.zip",
        "2001_01_o.zip",
        "2004_02_k.zip",
        "2004_02_o.zip",
    } <= names
    assert {"polr_H_2024.zip", "polr_Q_2024.zip", "polr_T_2024.zip"} <= names
    for archive in archives:
        assert archive.stat().st_size < 1024
        with ZipFile(archive) as zf:
            assert len(zf.namelist()) == 1
            assert zf.testzip() is None
            assert zf.namelist()[0].endswith(".csv")

    def csv(filename):
        with ZipFile(next(ARCHIVES.rglob(filename))) as zf:
            return zf.read(zf.namelist()[0])

    assert csv("codz_2023.zip").startswith(b"\xef\xbb\xbf")
    assert b";" in csv("codz_2023.zip")
    assert b'"""149190310' in csv("codz_2024.zip")
    assert b"99999.999" in csv("codz_2024.zip")
    assert b",4,29," in csv("codz_2024.zip")
    assert b",13,H," in csv("polr_H_2024.zip")
    assert b",14,Q," in csv("polr_Q_2024.zip")
    assert b",15,T," in csv("polr_T_2024.zip")
    assert b",8," in csv("2001_01_o.zip")
    assert b",9," in csv("2001_01_o.zip")
    assert b",2,29," in csv("2004_02_o.zip")
    for csv_name in ("lista_stacji_hydro.csv", "wykaz_stacji.csv"):
        assert next(ARCHIVES.rglob(csv_name)).read_bytes().decode("cp1250")
    assert b"123750000," in next(ARCHIVES.rglob("wykaz_stacji.csv")).read_bytes()


def test_recordings_have_fixed_hashes_dates_and_distinct_http_signals():
    recording = json.loads((ROOT / "recordings.json").read_text(encoding="utf-8"))
    assert (
        datetime.fromisoformat(recording["recorded_at"].replace("Z", "+00:00")).year
        == 2026
    )
    interactions = {item["case"]: item for item in recording["interactions"]}
    assert len(interactions) == len(recording["interactions"])
    assert {
        "hydro_listing",
        "meteo_listing",
        "hydro_head",
        "hydro_get",
        "meteo_head",
        "meteo_get",
        "no_headers",
        "missing_year",
        "changed_after_check",
        "same_bytes_new_signal",
        "new_bytes_head",
        "new_bytes_get",
        "network_timeout",
        "hydro_current",
        "meteo_current",
        "pmaxtp_pot_first",
        "pmaxtp_pot_same_cell",
        "pmaxtp_amp",
    } <= interactions.keys()
    assert (
        interactions["hydro_head"]["headers"]["ETag"]
        != interactions["changed_after_check"]["headers"]["ETag"]
    )
    assert (
        interactions["pmaxtp_pot_first"]["json"]["point"]["indX"]
        == interactions["pmaxtp_pot_same_cell"]["json"]["point"]["indX"]
    )
    for case in ("hydro_get", "meteo_get", "same_bytes_new_signal", "new_bytes_get"):
        entry = interactions[case]
        data = (
            (ARCHIVES / entry["archive"]).read_bytes()
            if "archive" in entry
            else (ROOT / entry["variant"]).read_bytes()
        )
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == int(entry["headers"]["Content-Length"])
        assert (
            datetime.strptime(
                entry["headers"]["Last-Modified"], "%a, %d %b %Y %H:%M:%S GMT"
            ).year
            == 2026
        )
    assert (
        interactions["hydro_get"]["sha256"]
        == interactions["same_bytes_new_signal"]["sha256"]
    )
    assert (
        interactions["hydro_get"]["sha256"] != interactions["new_bytes_get"]["sha256"]
    )


@pytest.mark.parametrize(
    "case",
    ["hydro_head", "meteo_get", "new_bytes_get", "missing_year", "network_timeout"],
)
def test_recordings_replay_offline(case):
    recording = json.loads((ROOT / "recordings.json").read_text(encoding="utf-8"))
    entry = next(item for item in recording["interactions"] if item["case"] == case)

    def handler(request):
        assert request.method == entry["method"]
        assert str(request.url) == f"{recording['base_url']}/{entry['path']}"
        if "exception" in entry:
            raise httpx.TimeoutException("synthetic timeout", request=request)
        content = (
            (ARCHIVES / entry["archive"]).read_bytes()
            if "archive" in entry
            else (ROOT / entry["variant"]).read_bytes()
            if "variant" in entry
            else b""
        )
        return httpx.Response(
            entry["status"], headers=entry.get("headers", {}), content=content
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        url = f"{recording['base_url']}/{entry['path']}"
        if case == "network_timeout":
            with pytest.raises(httpx.TimeoutException):
                client.request(entry["method"], url)
        else:
            response = client.request(entry["method"], url)
            assert response.status_code == entry["status"]
            if case in ("meteo_get", "new_bytes_get"):
                assert hashlib.sha256(response.content).hexdigest() == entry["sha256"]
