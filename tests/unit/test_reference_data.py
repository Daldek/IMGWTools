"""Offline tests for ``python -m imgwtools.reference_data``."""

import runpy
import warnings

import httpx
import pytest

from imgwtools import reference_data
from imgwtools.datasets import get_provider, station_source_files
from imgwtools.stations import HYDRO_MAP_API_URL

HYDRO_STATIONS_CSV_URL, METEO_STATIONS_CSV_URL = (
    file.url for file in station_source_files()
)

BASE = reference_data.DESC_BASE
METEO = f"{BASE}/dane_meteorologiczne"
CODZ, ZJAW, MIES, POLR = (f"{BASE}/{rel}" for rel in reference_data.HYDRO_DESC)

MAP_PAYLOAD = {
    "stations": [
        {"id": "149190310", "n": "Raba Górna", "la": 49.61, "lo": 20.05},
        {"id": "149190311", "n": "Żabie"},
    ]
}


def _listing(*names: str) -> httpx.Response:
    links = "".join(f'<a href="{name}">{name}</a>' for name in names)
    return httpx.Response(200, text=f'<a href="../">../</a>{links}')


def _sources() -> dict[str, httpx.Response | Exception]:
    return {
        HYDRO_MAP_API_URL: httpx.Response(200, json=MAP_PAYLOAD),
        CODZ: httpx.Response(200, content=b"CODZ opis\xb9"),
        ZJAW: httpx.Response(404),
        MIES: httpx.Response(200, content=b"MIES opis"),
        POLR: httpx.Response(200, content=b"POLR opis"),
        f"{METEO}/dobowe/klimat/": _listing("k_d_format.txt", "k_d_t_format.txt"),
        f"{METEO}/dobowe/klimat/k_d_format.txt": httpx.Response(200, content=b"kd"),
        f"{METEO}/dobowe/klimat/k_d_t_format.txt": httpx.Response(500),
        # Same file name in another folder: only the first occurrence is fetched.
        f"{METEO}/dobowe/opad/": _listing("k_d_format.txt", "o_d_format.txt"),
        f"{METEO}/dobowe/opad/o_d_format.txt": httpx.Response(200, content=b"od"),
        f"{METEO}/terminowe/opad/": httpx.Response(404),
    }


def _serve(respx_mock, sources: dict[str, httpx.Response | Exception]) -> list[str]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url.copy_with(query=None))
        requested.append(url)
        source = sources.get(url, httpx.Response(404))
        if isinstance(source, httpx.Response):
            return httpx.Response(
                source.status_code, content=source.content, headers=source.headers
            )
        raise source

    respx_mock.route().mock(side_effect=handler)
    return requested


def test_reference_data_main_writes_stations_and_descriptions(
    respx_mock, isolated_reference_dir, capsys
):
    requested = _serve(respx_mock, _sources())

    assert reference_data.main() == 0

    out = capsys.readouterr().out
    assert str(isolated_reference_dir) in out
    attribution = get_provider("IMGW-PIB").license.attribution
    assert f"Wymagana atrybucja: {attribution}\n" in out
    assert (
        "pominięto: dane_hydrologiczne/dobowe/ZJAW_publiczne_format.txt: HTTP 404"
        in out
    )
    assert "pominięto: k_d_t_format.txt: HTTP 500" in out
    # Only the locations file and format descriptions are written; latitude
    # before longitude; stations without coordinates are omitted.
    assert {
        path.relative_to(isolated_reference_dir).as_posix()
        for path in isolated_reference_dir.iterdir()
    } == {"hydro_stations_locations.csv", "desc"}
    assert (isolated_reference_dir / "hydro_stations_locations.csv").read_text(
        encoding="utf-8"
    ).splitlines() == ["station_code,latitude,longitude", "149190310,49.61,20.05"]

    desc = isolated_reference_dir / "desc"
    assert {
        path.relative_to(desc).as_posix(): path.read_bytes()
        for path in desc.rglob("*")
        if path.is_file()
    } == {
        "dane_hydrologiczne/CODZ_publiczne_format.txt": b"CODZ opis\xb9",
        "dane_hydrologiczne/MIES_publiczne_format.txt": b"MIES opis",
        "dane_hydrologiczne/POLR_publiczne_format.txt": b"POLR opis",
        "dane_meteorologiczne/k_d_format.txt": b"kd",
        "dane_meteorologiczne/o_d_format.txt": b"od",
    }
    assert f"{METEO}/dobowe/opad/k_d_format.txt" not in requested
    assert not {HYDRO_STATIONS_CSV_URL, METEO_STATIONS_CSV_URL} & set(requested)
    assert {
        f"{METEO}/{interval}/{subtype}/"
        for interval in reference_data.METEO_INTERVALS
        for subtype in reference_data.METEO_SUBTYPES
    } <= set(requested)


def test_reference_data_main_rerun_overwrites_stale_files(
    respx_mock, isolated_reference_dir
):
    stale = isolated_reference_dir / "hydro_stations_locations.csv"
    stale.write_text("id,X,Y\n999,0,0\n", encoding="utf-8")
    _serve(respx_mock, _sources())

    assert reference_data.main() == 0
    first = {
        p: p.read_bytes() for p in isolated_reference_dir.rglob("*") if p.is_file()
    }
    assert reference_data.main() == 0
    second = {
        p: p.read_bytes() for p in isolated_reference_dir.rglob("*") if p.is_file()
    }

    assert first == second
    assert stale.read_text(encoding="utf-8").splitlines() == [
        "station_code,latitude,longitude",
        "149190310,49.61,20.05",
    ]


def test_reference_data_main_station_failure_keeps_previous_file(
    respx_mock, isolated_reference_dir, capsys
):
    previous = isolated_reference_dir / "hydro_stations_locations.csv"
    previous.write_text(
        "station_code,latitude,longitude\n149190310,49.0,20.0\n", encoding="utf-8"
    )
    sources = _sources()
    sources[HYDRO_MAP_API_URL] = httpx.Response(503)
    _serve(respx_mock, sources)

    assert reference_data.main() == 1

    captured = capsys.readouterr()
    assert "Błąd pobierania danych:" in captured.err
    assert "Gotowe" not in captured.out
    assert previous.read_text(encoding="utf-8") == (
        "station_code,latitude,longitude\n149190310,49.0,20.0\n"
    )
    assert not (isolated_reference_dir / "desc").exists()


def test_reference_data_main_invalid_map_json_reports_error(
    respx_mock, isolated_reference_dir, capsys
):
    sources = _sources()
    sources[HYDRO_MAP_API_URL] = httpx.Response(200, text="<html>przerwa</html>")
    _serve(respx_mock, sources)

    assert reference_data.main() == 1

    assert "Invalid JSON response" in capsys.readouterr().err
    assert not (isolated_reference_dir / "hydro_stations_locations.csv").exists()


def test_reference_data_main_connection_error_in_descriptions_returns_1(
    respx_mock, isolated_reference_dir, capsys
):
    sources = _sources()
    sources[MIES] = httpx.ConnectError("brak sieci")
    _serve(respx_mock, sources)

    assert reference_data.main() == 1

    assert "Błąd pobierania danych: brak sieci" in capsys.readouterr().err
    assert (isolated_reference_dir / "hydro_stations_locations.csv").is_file()
    assert not (isolated_reference_dir / "desc" / "dane_meteorologiczne").exists()


@pytest.mark.parametrize("fail, code", [(False, 0), (True, 1)])
def test_reference_data_run_as_module_exits_with_main_status(
    respx_mock, isolated_reference_dir, fail, code
):
    sources = _sources()
    if fail:
        sources[HYDRO_MAP_API_URL] = httpx.Response(500)
    _serve(respx_mock, sources)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("imgwtools.reference_data", run_name="__main__")

    assert exit_info.value.code == code
    assert (
        isolated_reference_dir / "hydro_stations_locations.csv"
    ).exists() is not fail
