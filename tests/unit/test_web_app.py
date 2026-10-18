import json
import re

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from imgwtools.api.main import app

HYDRO_BASE = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne"
)
METEO_BASE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne"
HYDRO_STATIONS_CSV_URL = f"{HYDRO_BASE}/lista_stacji_hydro.csv"
METEO_STATIONS_CSV_URL = f"{METEO_BASE}/wykaz_stacji.csv"
MAP_URL = "https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false"
PMAXTP_POT_URL = "https://powietrze.imgw.pl/tpmax-api/point/P/KS/50.0600/19.9400"

HYDRO_CSV = (
    '149190310,"SAN ESCOBAR","Raba Górna (2137)"\n'
    '149190320,"ŻABIE DOŁY","Wisłoka Mała (2138)"\n'
    '149190330,"KRÓLEWSKI GRÓD","Strumień bez numeru"\n'
    "149190340,NIEPEŁNY\n"
)
METEO_CSV = (
    '"249190310","SAN ESCOBAR-LOTNISKO","01001"\n'
    '"249190320","ŻABIE DOŁY","01002"\n'
    '"249190330","GÓRNA ŁĄKA","01003"\n'
    '"249190340"\n'
)


@pytest.fixture
def client():
    return TestClient(app)


def _links(html: str) -> list[str]:
    return re.findall(r'<a href="([^"]+)" target="_blank" role="button"', html)


# --- Static pages -----------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "labels"),
    [
        ("/", ["<h1>IMGWTools</h1>", "Wybierz typ danych", "O projekcie"]),
        ("/download", ["<h1>Pobieranie danych</h1>", "Wybierz typ danych do pobrania"]),
        (
            "/download/hydro",
            [
                "<h1>Dane hydrologiczne</h1>",
                'hx-post="/download/hydro/generate"',
                '<option value="polroczne_i_roczne">Półroczne i roczne</option>',
                '<option value="Q">Przepływ (Q)</option>',
            ],
        ),
        (
            "/download/meteo",
            [
                "<h1>Dane meteorologiczne</h1>",
                'hx-post="/download/meteo/generate"',
                '<option value="terminowe">Terminowe (godzinowe)</option>',
                '<option value="synop">Synop</option>',
            ],
        ),
        (
            "/download/pmaxtp",
            [
                "<h1>Opady maksymalne (PMAXTP)</h1>",
                'hx-post="/download/pmaxtp/generate"',
                '<option value="POT">Peak Over Threshold</option>',
                '<option value="AMP">Annual Max Precipitation</option>',
            ],
        ),
        ("/stations", ["<h1>Lista stacji</h1>", "Przeglądaj stacje hydrologiczne"]),
        ("/map", ["<h1>Mapa stacji</h1>", "Interaktywna mapa stacji hydrologicznych"]),
    ],
)
def test_web_app_pages_render_polish_html(client, path, labels):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for label in labels:
        assert label in response.text


def test_web_app_page_title_uses_base_layout(client):
    response = client.get("/download/hydro")

    assert "<title>Dane hydrologiczne | IMGWTools</title>" in response.text


# --- Hydro URL generation ---------------------------------------------------


def test_web_app_generate_hydro_daily_before_2023_lists_twelve_monthly_files(client):
    response = client.post(
        "/download/hydro/generate",
        data={"interval": "dobowe", "start_year": "2022", "end_year": "2022"},
    )

    assert response.status_code == 200
    links = _links(response.text)
    assert links == [
        f"{HYDRO_BASE}/dobowe/2022/codz_2022_{month:02d}.zip" for month in range(1, 13)
    ]
    assert "Wygenerowane linki (12)" in response.text
    assert "<th>Miesiąc</th>" in response.text
    assert "<th>Parametr</th>" not in response.text


def test_web_app_generate_hydro_daily_switches_to_yearly_file_from_2023(client):
    response = client.post(
        "/download/hydro/generate",
        data={"interval": "dobowe", "start_year": "2022", "end_year": "2024"},
    )

    links = _links(response.text)
    assert len(links) == 14
    assert links[-2:] == [
        f"{HYDRO_BASE}/dobowe/2023/codz_2023.zip",
        f"{HYDRO_BASE}/dobowe/2024/codz_2024.zip",
    ]
    # The textarea used for "copy all" / wget script carries every URL
    assert f"{HYDRO_BASE}/dobowe/2024/codz_2024.zip\n" in response.text


def test_web_app_generate_hydro_monthly_one_file_per_year(client):
    response = client.post(
        "/download/hydro/generate",
        data={"interval": "miesieczne", "start_year": "2019", "end_year": "2020"},
    )

    assert _links(response.text) == [
        f"{HYDRO_BASE}/miesieczne/2019/mies_2019.zip",
        f"{HYDRO_BASE}/miesieczne/2020/mies_2020.zip",
    ]
    assert "<th>Miesiąc</th>" not in response.text


def test_web_app_generate_hydro_semi_annual_single_param(client):
    response = client.post(
        "/download/hydro/generate",
        data={
            "interval": "polroczne_i_roczne",
            "param": "H",
            "start_year": "2020",
            "end_year": "2020",
        },
    )

    assert _links(response.text) == [
        f"{HYDRO_BASE}/polroczne_i_roczne/2020/polr_H_2020.zip"
    ]


def test_web_app_generate_hydro_semi_annual_without_param_lists_q_h_t(client):
    response = client.post(
        "/download/hydro/generate",
        data={
            "interval": "polroczne_i_roczne",
            "param": "",
            "start_year": "2020",
            "end_year": "2020",
        },
    )

    assert _links(response.text) == [
        f"{HYDRO_BASE}/polroczne_i_roczne/2020/polr_{p}_2020.zip"
        for p in ("Q", "H", "T")
    ]
    assert "<th>Parametr</th>" in response.text


def test_web_app_generate_hydro_year_before_archive_reports_error_per_year(client):
    response = client.post(
        "/download/hydro/generate",
        data={"interval": "miesieczne", "start_year": "1950", "end_year": "1951"},
    )

    assert response.status_code == 200
    assert "Wystąpiły błędy" in response.text
    assert "Rok 1950: Nieprawidłowe roczniki zbioru" in response.text
    assert "minimalny rok: 1951" in response.text
    assert _links(response.text) == [f"{HYDRO_BASE}/miesieczne/1951/mies_1951.zip"]


def test_web_app_generate_hydro_unknown_interval_renders_error_without_links(client):
    response = client.post(
        "/download/hydro/generate",
        data={"interval": "tygodniowe", "start_year": "2020", "end_year": "2020"},
    )

    assert response.status_code == 200
    assert "Wystąpiły błędy" in response.text
    assert "tygodniowe" in response.text
    assert _links(response.text) == []
    assert "Brak wyników" not in response.text


def test_web_app_generate_hydro_reversed_range_renders_no_results(client):
    response = client.post(
        "/download/hydro/generate",
        data={"interval": "miesieczne", "start_year": "2021", "end_year": "2020"},
    )

    assert "Brak wyników dla wybranych parametrów." in response.text
    assert "Wystąpiły błędy" not in response.text


def test_web_app_generate_hydro_non_numeric_year_is_rejected(client):
    response = client.post(
        "/download/hydro/generate",
        data={
            "interval": "miesieczne",
            "start_year": "dwa tysiące",
            "end_year": "2020",
        },
    )

    assert response.status_code == 422


# --- Meteo URL generation ---------------------------------------------------


def test_web_app_generate_meteo_monthly_before_2001_deduplicates_folder_file(client):
    response = client.post(
        "/download/meteo/generate",
        data={
            "interval": "miesieczne",
            "subtype": "synop",
            "start_year": "1996",
            "end_year": "2001",
        },
    )

    assert _links(response.text) == [
        f"{METEO_BASE}/miesieczne/synop/1996_2000/1996_2000_m_s.zip",
        f"{METEO_BASE}/miesieczne/synop/2001/2001_m_s.zip",
    ]
    assert "Wygenerowane linki (2)" in response.text


def test_web_app_generate_meteo_daily_yearly_until_2000_monthly_from_2001(client):
    response = client.post(
        "/download/meteo/generate",
        data={
            "interval": "dobowe",
            "subtype": "klimat",
            "start_year": "2000",
            "end_year": "2001",
        },
    )

    links = _links(response.text)
    assert links[0] == f"{METEO_BASE}/dobowe/klimat/1996_2000/2000_k.zip"
    assert links[1:] == [
        f"{METEO_BASE}/dobowe/klimat/2001/2001_{month:02d}_k.zip"
        for month in range(1, 13)
    ]


def test_web_app_generate_meteo_hourly_climate_monthly_files(client):
    response = client.post(
        "/download/meteo/generate",
        data={
            "interval": "terminowe",
            "subtype": "klimat",
            "start_year": "2023",
            "end_year": "2023",
        },
    )

    links = _links(response.text)
    assert len(links) == 12
    assert links[1] == f"{METEO_BASE}/terminowe/klimat/2023/2023_02_k.zip"


@pytest.mark.parametrize(
    ("interval", "subtype", "message"),
    [
        ("terminowe", "opad", "does not exist on IMGW servers"),
        ("dobowe", "synop", "per-station files"),
    ],
)
def test_web_app_generate_meteo_unsupported_combination_reports_error(
    client, interval, subtype, message
):
    response = client.post(
        "/download/meteo/generate",
        data={
            "interval": interval,
            "subtype": subtype,
            "start_year": "2023",
            "end_year": "2023",
        },
    )

    assert response.status_code == 200
    assert "Wystąpiły błędy" in response.text
    assert "Rok 2023:" in response.text
    assert message in response.text
    assert _links(response.text) == []


def test_web_app_generate_meteo_unknown_subtype_renders_error(client):
    response = client.post(
        "/download/meteo/generate",
        data={
            "interval": "miesieczne",
            "subtype": "wiatr",
            "start_year": "2023",
            "end_year": "2023",
        },
    )

    assert "Wystąpiły błędy" in response.text
    assert "wiatr" in response.text
    assert _links(response.text) == []


def test_web_app_generate_meteo_missing_subtype_is_rejected(client):
    response = client.post(
        "/download/meteo/generate",
        data={"interval": "miesieczne", "start_year": "2023", "end_year": "2023"},
    )

    assert response.status_code == 422


# --- PMAXTP -----------------------------------------------------------------


def test_web_app_generate_pmaxtp_renders_tables_and_embeds_export_data(
    client, pmaxtp_api_response
):
    payload = {
        **pmaxtp_api_response,
        "point": {"dataLat": 50.06123, "dataLon": 19.93871},
    }
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(PMAXTP_POT_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        response = client.post(
            "/download/pmaxtp/generate",
            data={"method": "POT", "latitude": "50.06", "longitude": "19.94"},
        )

    assert route.call_count == 1
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Wyniki PMAXTP" in html
    assert "POT (Peak Over Threshold)" in html
    assert "50.06°N, 19.94°E" in html
    assert "50.0612°N, 19.9387°E" in html
    for table_id in ("table-ks", "table-sg", "table-rb"):
        assert f'id="{table_id}"' in html
    assert "Kwantyle opadu maksymalnego [mm]" in html
    assert "Górne granice przedziału ufności [mm]" in html
    assert "Błędy estymacji kwantyli [mm]" in html
    # Formatted quantile (ks, 60 min, p=1%) and missing probability rendered as "-"
    assert "<td>28.40</td>" in html
    assert "<td>-</td>" in html
    # Exports (CSV/XLSX/JSON) are generated client-side from the embedded JSON
    for label in ("Pobierz CSV", "Pobierz XLSX", "Pobierz JSON"):
        assert label in html
    embedded = re.search(r"const pmaxtpData = (.+);\n", html)
    assert embedded is not None
    assert json.loads(embedded.group(1)) == payload


def test_web_app_generate_pmaxtp_amp_uses_amp_endpoint_and_skips_missing_tables(client):
    amp_url = "https://powietrze.imgw.pl/tpmax-api/point/A/KS/50.0600/19.9400"
    payload = {"data": {"ks": {"5": {"1": 9.876}}}}
    with respx.mock(assert_all_called=True) as mock:
        mock.get(amp_url).mock(return_value=httpx.Response(200, json=payload))
        response = client.post(
            "/download/pmaxtp/generate",
            data={"method": "AMP", "latitude": "50.06", "longitude": "19.94"},
        )

    html = response.text
    assert "AMP (Annual Max Precipitation)" in html
    assert "<td>9.88</td>" in html
    assert 'id="table-ks"' in html
    assert 'id="table-sg"' not in html
    assert 'id="table-rb"' not in html
    assert "<dt>Lokalizacja danych (siatka)</dt>" not in html


def test_web_app_generate_pmaxtp_upstream_error_renders_error_partial(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(PMAXTP_POT_URL).mock(return_value=httpx.Response(503))
        response = client.post(
            "/download/pmaxtp/generate",
            data={"method": "POT", "latitude": "50.06", "longitude": "19.94"},
        )

    assert response.status_code == 200
    assert '<article class="error">' in response.text
    assert "Błąd pobierania danych:" in response.text
    assert "503" in response.text


def test_web_app_generate_pmaxtp_connection_error_renders_error_partial(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(PMAXTP_POT_URL).mock(side_effect=httpx.ConnectError("brak sieci"))
        response = client.post(
            "/download/pmaxtp/generate",
            data={"method": "POT", "latitude": "50.06", "longitude": "19.94"},
        )

    assert "Błąd pobierania danych: brak sieci" in response.text


def test_web_app_generate_pmaxtp_unknown_method_renders_error_without_request(client):
    with respx.mock(assert_all_mocked=True) as mock:
        response = client.post(
            "/download/pmaxtp/generate",
            data={"method": "XYZ", "latitude": "50.06", "longitude": "19.94"},
        )
        assert mock.calls.call_count == 0

    assert response.status_code == 200
    assert '<article class="error">' in response.text
    assert "XYZ" in response.text
    assert "Wyniki PMAXTP" not in response.text


def test_web_app_generate_pmaxtp_non_numeric_latitude_is_rejected(client):
    response = client.post(
        "/download/pmaxtp/generate",
        data={"method": "POT", "latitude": "północ", "longitude": "19.94"},
    )

    assert response.status_code == 422


# --- Station partials -------------------------------------------------------


@pytest.fixture
def hydro_csv_route():
    with respx.mock(assert_all_called=True) as mock:
        yield mock.get(HYDRO_STATIONS_CSV_URL).mock(
            return_value=httpx.Response(200, content=HYDRO_CSV.encode("cp1250"))
        )


@pytest.fixture
def meteo_csv_route():
    with respx.mock(assert_all_called=True) as mock:
        yield mock.get(METEO_STATIONS_CSV_URL).mock(
            return_value=httpx.Response(200, content=METEO_CSV.encode("cp1250"))
        )


def test_web_app_hydro_stations_parses_cp1250_csv_and_river_id(client, hydro_csv_route):
    response = client.get("/stations/hydro")

    assert response.status_code == 200
    html = response.text
    assert "Stacje hydrologiczne" in html
    assert "(3 wyników)" in html
    assert "<td>ŻABIE DOŁY</td>" in html
    assert "<td>Wisłoka Mała</td>" in html
    assert "<td><code>2138</code></td>" in html
    # River without "(id)" suffix keeps the full name and has no river id
    assert "<td>Strumień bez numeru</td>" in html
    assert "<td><code>-</code></td>" in html
    assert "NIEPEŁNY" not in html
    assert "https://hydro.imgw.pl/#/station/hydro/149190310" in html
    assert "<th>Rzeka</th>" in html


def test_web_app_hydro_stations_search_matches_name_or_river_case_insensitive(
    client, hydro_csv_route
):
    by_river = client.get("/stations/hydro", params={"search": "raba górna"})
    by_name = client.get("/stations/hydro", params={"search": "żabie"})

    assert "(1 wyników)" in by_river.text
    assert "SAN ESCOBAR" in by_river.text
    assert "ŻABIE DOŁY" not in by_river.text
    assert "(1 wyników)" in by_name.text
    assert "ŻABIE DOŁY" in by_name.text


def test_web_app_hydro_stations_search_without_match_shows_empty_message(
    client, hydro_csv_route
):
    response = client.get("/stations/hydro", params={"search": "Atlantyda"})

    assert "(0 wyników)" in response.text
    assert "Brak stacji spełniających kryteria wyszukiwania." in response.text


def test_web_app_hydro_stations_limit_truncates_in_file_order(client, hydro_csv_route):
    response = client.get("/stations/hydro", params={"limit": 2})

    assert "(2 wyników)" in response.text
    assert "SAN ESCOBAR" in response.text
    assert "ŻABIE DOŁY" in response.text
    assert "KRÓLEWSKI GRÓD" not in response.text


def test_web_app_hydro_stations_upstream_error_renders_error_partial(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(HYDRO_STATIONS_CSV_URL).mock(return_value=httpx.Response(500))
        response = client.get("/stations/hydro")

    assert response.status_code == 200
    assert '<article class="error">' in response.text
    assert "Błąd pobierania stacji:" in response.text


def test_web_app_meteo_stations_parses_cp1250_csv(client, meteo_csv_route):
    response = client.get("/stations/meteo")

    html = response.text
    assert response.status_code == 200
    assert "Stacje meteorologiczne" in html
    assert "(3 wyników)" in html
    assert "<td>GÓRNA ŁĄKA</td>" in html
    assert "<td><code>249190330</code></td>" in html
    assert "https://hydro.imgw.pl/#/station/meteo/249190310" in html
    assert "<th>Rzeka</th>" not in html


def test_web_app_meteo_stations_search_and_limit(client, meteo_csv_route):
    searched = client.get("/stations/meteo", params={"search": "san escobar"})
    limited = client.get("/stations/meteo", params={"limit": 1})

    assert "(1 wyników)" in searched.text
    assert "SAN ESCOBAR-LOTNISKO" in searched.text
    assert "GÓRNA ŁĄKA" not in searched.text
    assert "(1 wyników)" in limited.text
    assert "SAN ESCOBAR-LOTNISKO" in limited.text
    assert "ŻABIE DOŁY" not in limited.text


def test_web_app_meteo_stations_timeout_renders_error_partial(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(METEO_STATIONS_CSV_URL).mock(side_effect=httpx.ReadTimeout("za długo"))
        response = client.get("/stations/meteo")

    assert response.status_code == 200
    assert "Błąd pobierania stacji: za długo" in response.text


# --- Map stations JSON -------------------------------------------------------


def test_web_app_map_stations_maps_fields_and_drops_missing_coordinates(client):
    upstream = {
        "stations": [
            {
                "id": "149190310",
                "n": "San Escobar",
                "la": 49.8765,
                "lo": 18.1234,
                "s": "alarm",
            },
            {"id": "149190320", "n": "Raba Górna", "la": "50.1", "lo": "19.2"},
            {
                "id": "149190330",
                "n": "Bez współrzędnych",
                "la": None,
                "lo": 19.0,
                "s": "low",
            },
            {"id": "149190340", "n": "Bez długości", "la": 50.0, "s": "high"},
        ],
        "numOfAlarmStates": 1,
        "numOfWarningStates": 2,
        "numOfBelowStates": 3,
    }
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(MAP_URL).mock(return_value=httpx.Response(200, json=upstream))
        response = client.get("/map/stations")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "stations": [
            {
                "id": "149190310",
                "name": "San Escobar",
                "lat": 49.8765,
                "lon": 18.1234,
                "state": "alarm",
            },
            {
                "id": "149190320",
                "name": "Raba Górna",
                "lat": 50.1,
                "lon": 19.2,
                "state": "unknown",
            },
        ],
        "summary": {"total": 2, "alarm": 1, "warning": 2, "below": 3},
    }
    # hydro-back rejects requests without a browser-like Referer
    assert route.calls.last.request.headers["Referer"] == "https://hydro.imgw.pl/"


def test_web_app_map_stations_empty_payload_defaults_summary_to_zero(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(MAP_URL).mock(return_value=httpx.Response(200, json={}))
        response = client.get("/map/stations")

    assert response.json() == {
        "stations": [],
        "summary": {"total": 0, "alarm": 0, "warning": 0, "below": 0},
    }


def test_web_app_map_stations_upstream_error_returns_error_json(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(MAP_URL).mock(return_value=httpx.Response(502))
        response = client.get("/map/stations")

    assert response.status_code == 200
    body = response.json()
    assert body["stations"] == []
    assert body["error"].startswith("Błąd pobierania danych:")
    assert "502" in body["error"]
