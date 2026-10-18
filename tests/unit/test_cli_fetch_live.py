"""``imgw fetch current|pmaxtp|warnings``: live IMGW API calls, mocked offline."""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from imgwtools.cli.main import app
from imgwtools.core.url_builder import IMGW_API_URL, IMGW_PMAXTP_URL

RUNNER = CliRunner()

HYDRO_PAYLOAD = [
    {
        "id_stacji": "149190310",
        "stacja": "SAN ESCOBAR",
        "rzeka": "Ławica",
        "stan_wody": "231",
    }
]
SYNOP_PAYLOAD = [{"id_stacji": "12999", "stacja": "Raba Górna", "temperatura": "4.2"}]
WARNINGS_PAYLOAD = [{"opis": "Wezbranie z przekroczeniem stanów ostrzegawczych"}]
PMAXTP_PAYLOAD = {"point": {"lat": "50.0612", "lon": "19.9372"}, "data": {"ks": {}}}


@pytest.fixture
def imgw():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.mark.parametrize(
    ("data_type", "payload"),
    [("hydro", HYDRO_PAYLOAD), ("meteo", SYNOP_PAYLOAD), ("synop", SYNOP_PAYLOAD)],
)
def test_cli_fetch_current_prints_json_from_matching_endpoint(imgw, data_type, payload):
    route = imgw.get(f"{IMGW_API_URL}/{data_type}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = RUNNER.invoke(app, ["fetch", "current", data_type])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert f"Pobieranie aktualnych danych ({data_type})" in result.output
    json_start = result.output.index("[")
    assert json.loads(result.output[json_start:]) == payload


def test_cli_fetch_current_station_option_queries_station_endpoint(imgw):
    route = imgw.get(f"{IMGW_API_URL}/hydro/id/149190310").mock(
        return_value=httpx.Response(200, json=HYDRO_PAYLOAD)
    )

    result = RUNNER.invoke(app, ["fetch", "current", "hydro", "-s", "149190310"])

    assert result.exit_code == 0, result.output
    assert route.called
    assert "SAN ESCOBAR" in result.output


def test_cli_fetch_current_output_writes_utf8_json_file(imgw, tmp_path):
    imgw.get(f"{IMGW_API_URL}/hydro").mock(
        return_value=httpx.Response(200, json=HYDRO_PAYLOAD)
    )
    target = tmp_path / "aktualne.json"

    result = RUNNER.invoke(app, ["fetch", "current", "hydro", "-o", str(target)])

    assert result.exit_code == 0, result.output
    assert "Zapisano do:" in result.output
    assert "SAN ESCOBAR" not in result.output
    text = target.read_text(encoding="utf-8")
    assert "Ławica" in text
    assert json.loads(text) == HYDRO_PAYLOAD


def test_cli_fetch_current_unknown_type_exits_1_without_request(imgw):
    route = imgw.route()

    result = RUNNER.invoke(app, ["fetch", "current", "opad"])

    assert result.exit_code == 1
    assert "Nieprawidlowy typ danych: opad" in result.output
    assert not route.called


def test_cli_fetch_current_http_error_exits_1_with_message(imgw, tmp_path):
    imgw.get(f"{IMGW_API_URL}/synop").mock(return_value=httpx.Response(503))
    target = tmp_path / "synop.json"

    result = RUNNER.invoke(app, ["fetch", "current", "synop", "-o", str(target)])

    assert result.exit_code == 1
    assert "Blad pobierania" in result.output
    assert "503" in result.output
    assert not target.exists()


def test_cli_fetch_current_connection_error_exits_1_with_message(imgw):
    imgw.get(f"{IMGW_API_URL}/hydro").mock(side_effect=httpx.ConnectError("brak sieci"))

    result = RUNNER.invoke(app, ["fetch", "current", "hydro"])

    assert result.exit_code == 1
    assert "Blad pobierania: brak sieci" in result.output


def test_cli_fetch_pmaxtp_default_method_is_pot(imgw):
    route = imgw.get(f"{IMGW_PMAXTP_URL}/P/KS/50.0612/19.9372").mock(
        return_value=httpx.Response(200, json=PMAXTP_PAYLOAD)
    )

    result = RUNNER.invoke(
        app, ["fetch", "pmaxtp", "--lat", "50.0612", "--lon", "19.9372"]
    )

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "Metoda: POT" in result.output
    assert "Lokalizacja: 50.0612, 19.9372" in result.output
    assert json.loads(result.output[result.output.index("{") :]) == PMAXTP_PAYLOAD


def test_cli_fetch_pmaxtp_amp_method_writes_output_file(imgw, tmp_path):
    route = imgw.get(f"{IMGW_PMAXTP_URL}/A/KS/52.2300/21.0100").mock(
        return_value=httpx.Response(200, json=PMAXTP_PAYLOAD)
    )
    target = tmp_path / "pmaxtp.json"

    result = RUNNER.invoke(
        app,
        ["fetch", "pmaxtp", "-m", "AMP", "--lat", "52.23", "--lon", "21.01"]
        + ["-o", str(target)],
    )

    assert result.exit_code == 0, result.output
    assert route.called
    assert "Zapisano do:" in result.output
    assert json.loads(target.read_text(encoding="utf-8")) == PMAXTP_PAYLOAD


def test_cli_fetch_pmaxtp_unknown_method_exits_1_without_request(imgw):
    route = imgw.route()

    result = RUNNER.invoke(
        app, ["fetch", "pmaxtp", "-m", "pot", "--lat", "50.06", "--lon", "19.94"]
    )

    assert result.exit_code == 1
    assert "Nieprawidlowa metoda: pot. Uzyj POT lub AMP." in result.output
    assert not route.called


@pytest.mark.parametrize(
    ("lat", "lon"),
    [("48.99", "19.94"), ("55.01", "19.94"), ("50.06", "13.99"), ("50.06", "24.51")],
)
def test_cli_fetch_pmaxtp_outside_poland_exits_1_without_request(imgw, lat, lon):
    route = imgw.route()

    result = RUNNER.invoke(app, ["fetch", "pmaxtp", "--lat", lat, "--lon", lon])

    assert result.exit_code == 1
    assert "poza obszarem Polski" in result.output
    assert not route.called


@pytest.mark.parametrize(("lat", "lon"), [("49.0", "14.0"), ("55.0", "24.5")])
def test_cli_fetch_pmaxtp_poland_bounds_are_inclusive(imgw, lat, lon):
    route = imgw.get(url__startswith=f"{IMGW_PMAXTP_URL}/P/KS/").mock(
        return_value=httpx.Response(200, json=PMAXTP_PAYLOAD)
    )

    result = RUNNER.invoke(app, ["fetch", "pmaxtp", "--lat", lat, "--lon", lon])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1


def test_cli_fetch_pmaxtp_requires_coordinates(imgw):
    result = RUNNER.invoke(app, ["fetch", "pmaxtp", "--lat", "50.06"])

    assert result.exit_code == 2


def test_cli_fetch_pmaxtp_timeout_exits_1_with_message(imgw):
    imgw.get(f"{IMGW_PMAXTP_URL}/P/KS/50.0600/19.9400").mock(
        side_effect=httpx.ReadTimeout("za długo")
    )

    result = RUNNER.invoke(app, ["fetch", "pmaxtp", "--lat", "50.06", "--lon", "19.94"])

    assert result.exit_code == 1
    assert "Blad pobierania: za długo" in result.output


@pytest.mark.parametrize("warning_type", ["hydro", "meteo"])
def test_cli_fetch_warnings_prints_json_for_type(imgw, warning_type):
    route = imgw.get(f"{IMGW_API_URL}/warnings/{warning_type}").mock(
        return_value=httpx.Response(200, json=WARNINGS_PAYLOAD)
    )

    result = RUNNER.invoke(app, ["fetch", "warnings", "--type", warning_type])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert f"Pobieranie ostrzezen ({warning_type})" in result.output
    assert json.loads(result.output[result.output.index("[") :]) == WARNINGS_PAYLOAD


def test_cli_fetch_warnings_defaults_to_hydro_and_writes_file(imgw, tmp_path):
    route = imgw.get(f"{IMGW_API_URL}/warnings/hydro").mock(
        return_value=httpx.Response(200, json=WARNINGS_PAYLOAD)
    )
    target = tmp_path / "ostrzezenia.json"

    result = RUNNER.invoke(app, ["fetch", "warnings", "-o", str(target)])

    assert result.exit_code == 0, result.output
    assert route.called
    assert "Zapisano do:" in result.output
    assert json.loads(target.read_text(encoding="utf-8")) == WARNINGS_PAYLOAD


def test_cli_fetch_warnings_unknown_type_exits_1_without_request(imgw):
    route = imgw.route()

    result = RUNNER.invoke(app, ["fetch", "warnings", "-t", "synop"])

    assert result.exit_code == 1
    assert "Nieprawidlowy typ: synop. Uzyj hydro lub meteo." in result.output
    assert not route.called


def test_cli_fetch_warnings_connection_error_exits_1_with_message(imgw):
    imgw.get(f"{IMGW_API_URL}/warnings/meteo").mock(
        side_effect=httpx.ConnectError("brak sieci")
    )

    result = RUNNER.invoke(app, ["fetch", "warnings", "-t", "meteo"])

    assert result.exit_code == 1
    assert "Blad pobierania: brak sieci" in result.output
