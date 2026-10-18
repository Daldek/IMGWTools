"""Offline tests for ``python -m imgwtools.reference_data``."""

import runpy
import warnings

import httpx
import pytest

from imgwtools import reference_data
from imgwtools.datasets import station_source_files
from imgwtools.stations import HYDRO_MAP_API_URL

HYDRO_STATIONS_CSV_URL, METEO_STATIONS_CSV_URL = (
    file.url for file in station_source_files()
)

BASE = reference_data.DESC_BASE
METEO = f"{BASE}/dane_meteorologiczne"
CODZ, ZJAW, MIES, POLR = (f"{BASE}/{rel}" for rel in reference_data.HYDRO_DESC)

HYDRO_CSV = '"149190310","RABA GÓRNA","Raba (2138)"\n"149190311","ŻABIE",""\n'
METEO_CSV = '"249190310","SAN ESCOBAR"\n'
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
        HYDRO_STATIONS_CSV_URL: httpx.Response(200, content=HYDRO_CSV.encode("cp1250")),
        METEO_STATIONS_CSV_URL: httpx.Response(200, content=METEO_CSV.encode("cp1250")),
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
    respx_mock, isolated_data_dir, capsys
):
    requested = _serve(respx_mock, _sources())

    assert reference_data.main() == 0

    out = capsys.readouterr().out
    assert str(isolated_data_dir) in out
    assert reference_data.ATTRIBUTION in out
    assert (
        "skipped: dane_hydrologiczne/dobowe/ZJAW_publiczne_format.txt: HTTP 404" in out
    )
    assert "skipped: k_d_t_format.txt: HTTP 500" in out
    assert (isolated_data_dir / "hydro_stations_names.csv").read_text(
        encoding="utf-8"
    ).splitlines() == [
        "id,name,river",
        "149190310,RABA GÓRNA,Raba",
        "149190311,ŻABIE,",
    ]
    assert (isolated_data_dir / "meteo_stations_names.csv").read_text(
        encoding="utf-8"
    ).splitlines() == ["id,name", "249190310,SAN ESCOBAR"]
    # X = longitude, Y = latitude; stations without coordinates are omitted.
    assert (isolated_data_dir / "hydro_stations_locations.csv").read_text(
        encoding="utf-8"
    ).splitlines() == ["id,X,Y", "149190310,20.05,49.61"]

    desc = isolated_data_dir / "desc"
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
    assert {
        f"{METEO}/{interval}/{subtype}/"
        for interval in reference_data.METEO_INTERVALS
        for subtype in reference_data.METEO_SUBTYPES
    } <= set(requested)


def test_reference_data_main_rerun_overwrites_stale_files(
    respx_mock, isolated_data_dir
):
    stale = isolated_data_dir / "hydro_stations_locations.csv"
    stale.write_text("id,X,Y\n999,0,0\n", encoding="utf-8")
    _serve(respx_mock, _sources())

    assert reference_data.main() == 0
    first = {p: p.read_bytes() for p in isolated_data_dir.rglob("*") if p.is_file()}
    assert reference_data.main() == 0
    second = {p: p.read_bytes() for p in isolated_data_dir.rglob("*") if p.is_file()}

    assert first == second
    assert stale.read_text(encoding="utf-8").splitlines() == [
        "id,X,Y",
        "149190310,20.05,49.61",
    ]


def test_reference_data_main_station_failure_keeps_previous_file(
    respx_mock, isolated_data_dir, capsys
):
    previous = isolated_data_dir / "hydro_stations_locations.csv"
    previous.write_text("id,X,Y\n149190310,20.0,49.0\n", encoding="utf-8")
    sources = _sources()
    sources[HYDRO_MAP_API_URL] = httpx.Response(503)
    _serve(respx_mock, sources)

    assert reference_data.main() == 1

    captured = capsys.readouterr()
    assert "Error fetching data:" in captured.err
    assert "Done." not in captured.out
    assert previous.read_text(encoding="utf-8") == "id,X,Y\n149190310,20.0,49.0\n"
    assert not (isolated_data_dir / "desc").exists()


def test_reference_data_main_invalid_map_json_reports_error(
    respx_mock, isolated_data_dir, capsys
):
    sources = _sources()
    sources[HYDRO_MAP_API_URL] = httpx.Response(200, text="<html>przerwa</html>")
    _serve(respx_mock, sources)

    assert reference_data.main() == 1

    assert "Niepoprawna odpowiedź JSON" in capsys.readouterr().err
    assert not (isolated_data_dir / "hydro_stations_locations.csv").exists()


def test_reference_data_main_connection_error_in_descriptions_returns_1(
    respx_mock, isolated_data_dir, capsys
):
    sources = _sources()
    sources[MIES] = httpx.ConnectError("brak sieci")
    _serve(respx_mock, sources)

    assert reference_data.main() == 1

    assert "Error fetching data: brak sieci" in capsys.readouterr().err
    assert (isolated_data_dir / "meteo_stations_names.csv").is_file()
    assert not (isolated_data_dir / "desc" / "dane_meteorologiczne").exists()


@pytest.mark.parametrize("fail, code", [(False, 0), (True, 1)])
def test_reference_data_run_as_module_exits_with_main_status(
    respx_mock, isolated_data_dir, fail, code
):
    sources = _sources()
    if fail:
        sources[HYDRO_STATIONS_CSV_URL] = httpx.Response(500)
    _serve(respx_mock, sources)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("imgwtools.reference_data", run_name="__main__")

    assert exit_info.value.code == code
    assert (isolated_data_dir / "hydro_stations_names.csv").exists() is not fail
