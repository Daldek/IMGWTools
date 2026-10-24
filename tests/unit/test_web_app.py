import json
import re

import httpx
import pytest
import respx
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from imgwtools import archive_files, run_command, station_source_files
from imgwtools.api.main import app
from imgwtools.store.types import Page
from imgwtools.web.app import router as web_router

HYDRO_BASE = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne"
)
METEO_BASE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne"
HYDRO_LIST_URL, METEO_LIST_URL = (file.url for file in station_source_files())
MAP_URL = "https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false"
PMAXTP_POT_URL = "https://powietrze.imgw.pl/tpmax-api/point/P/KS/50.0600/19.9400"
PMAXTP_FORM = {"method": "POT", "latitude": "50.06", "longitude": "19.94"}

# Spec §13.4 and spec 2026-10-18 §9.3: the archive datasets of IMGW-PIB (no station
# lists, PMAXTP or ČHMÚ datasets: the GUI form has no station field).
ARCHIVE_DATASETS = {
    "pl.imgw.hydro_daily",
    "pl.imgw.hydro_monthly",
    "pl.imgw.hydro_semiannual",
    "pl.imgw.hydro_phenomena",
    "pl.imgw.meteo_climate_daily",
    "pl.imgw.meteo_precip_daily",
    "pl.imgw.meteo_climate_monthly",
    "pl.imgw.meteo_precip_monthly",
    "pl.imgw.meteo_synop_monthly",
    "pl.imgw.meteo_climate_terms",
}

HYDRO_CSV = (
    '"150190340","ŁÓDŹ ZACHÓD","Ner (18)","1"\n'
    '"149190310","RABA GÓRNA","Raba (2138)","2"\n'
    '"149190300","SAN ESCOBAR","Łódka (2139)",""\n'
)
METEO_CSV = '"251190470","ŁÓDŹ WSCHÓD","LW"\n"249190310","RABA GÓRNA","GR"\n'


@pytest.fixture
def client():
    return TestClient(app)


def _links(html: str) -> list[str]:
    return re.findall(r'<a href="([^"]+)" target="_blank" role="button"', html)


def _station_codes(html: str) -> list[str]:
    return re.findall(r"<td><code>([0-9]{9})</code></td>", html)


def _stations_find(**options: object) -> list[str]:
    """Station codes of the ``stations find`` page for the same options."""
    page = run_command(
        "stations find", options={"provider": "IMGW-PIB", **options}
    ).result
    assert isinstance(page, Page)
    return [entry.station_code for entry in page.items]


def _assert_error_partial(response, status: int, code: str, *texts: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("text/html")
    assert f'<article class="error" data-code="{code}">' in response.text
    for text in texts:
        assert text in response.text


# --- Static pages -----------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "labels"),
    [
        (
            "/",
            ["<h1>IMGWTools</h1>", "Wybierz typ danych", 'href="/download/archives"'],
        ),
        ("/download", ["<h1>Pobieranie danych</h1>", 'href="/download/archives"']),
        (
            "/download/archives",
            [
                "<h1>Dane archiwalne</h1>",
                'hx-post="/download/files"',
                '<optgroup label="Dane hydrologiczne">',
                '<option value="pl.imgw.hydro_semiannual">'
                "Dane hydrologiczne półroczne i roczne</option>",
                '<input type="checkbox" name="params" value="Q">',
            ],
        ),
        (
            "/download/pmaxtp",
            [
                "<h1>Opady maksymalne (PMAXTP)</h1>",
                'hx-post="/download/pmaxtp/generate"',
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
    response = client.get("/download/archives")

    assert "<title>Dane archiwalne | IMGWTools</title>" in response.text


def test_web_app_pages_stay_out_of_the_openapi_document(client):
    pages = {route.path for route in web_router.routes if isinstance(route, APIRoute)}
    documented = set(client.get("/openapi.json").json()["paths"])

    assert {"/", "/download/files", "/stations/find", "/map"} <= pages
    assert not pages & documented
    assert "/api/v1/stations/find" in documented


@pytest.mark.parametrize(
    "path", ["/map/stations", "/download/hydro", "/download/meteo", "/stations/hydro"]
)
def test_web_app_pre_registry_routes_are_gone(client, path):
    assert client.get(path).status_code == 404


# --- Archive download links (registry) ----------------------------------------


def test_web_app_download_form_offers_the_ten_archive_datasets(client):
    html = client.get("/download/archives").text

    offered = re.findall(r'<option value="([^"]+)">', html)
    assert len(offered) == 10
    assert set(offered) == ARCHIVE_DATASETS


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        (
            {"dataset": "pl.imgw.hydro_daily", "years": "2022-2023", "months": "1,12"},
            {"years": "2022-2023", "months": "1,12"},
        ),
        (
            {"dataset": "pl.imgw.meteo_synop_monthly", "years": "1996-2001"},
            {"years": "1996-2001"},
        ),
        (
            {"dataset": "pl.imgw.meteo_climate_terms", "years": "2000,2001"},
            {"years": "2000,2001"},
        ),
        (
            {"dataset": "pl.imgw.hydro_phenomena", "years": "2020"},
            {"years": "2020"},
        ),
    ],
)
def test_web_app_download_links_equal_archive_files(client, form, expected):
    response = client.post("/download/files", data=form)

    assert response.status_code == 200
    urls = [file.url for file in archive_files(form["dataset"], **expected)]
    assert _links(response.text) == urls
    assert f"Wygenerowane linki ({len(urls)})" in response.text
    # The textarea used for "copy all" / wget script carries every URL
    assert "".join(f"{url}\n" for url in urls) in response.text


def test_web_app_download_links_golden_urls_and_columns(client):
    daily = client.post(
        "/download/files",
        data={"dataset": "pl.imgw.hydro_daily", "years": "2022-2023", "months": "2"},
    )
    synop = client.post(
        "/download/files",
        data={"dataset": "pl.imgw.meteo_synop_monthly", "years": "1999-2001"},
    )

    assert _links(daily.text) == [
        f"{HYDRO_BASE}/dobowe/2022/codz_2022_02.zip",
        f"{HYDRO_BASE}/dobowe/2023/codz_2023.zip",
    ]
    assert "<th>Miesiąc</th>" in daily.text
    assert "<th>Parametr</th>" not in daily.text
    assert "2021-12-01 – 2021-12-31" in daily.text  # hydrological month 2 = December
    assert _links(synop.text) == [
        f"{METEO_BASE}/miesieczne/synop/1996_2000/1996_2000_m_s.zip",
        f"{METEO_BASE}/miesieczne/synop/2001/2001_m_s.zip",
    ]
    assert "<th>Miesiąc</th>" not in synop.text


def test_web_app_download_semi_annual_checked_params_only(client):
    response = client.post(
        "/download/files",
        data={
            "dataset": "pl.imgw.hydro_semiannual",
            "years": "2020",
            "params": ["T", "H"],
        },
    )

    assert _links(response.text) == [
        f"{HYDRO_BASE}/polroczne_i_roczne/2020/polr_{param}_2020.zip"
        for param in ("H", "T")
    ]
    assert "<th>Parametr</th>" in response.text


@pytest.mark.parametrize(
    ("form", "texts"),
    [
        (  # was a pydantic 422 before ADR-002
            {"dataset": "pl.imgw.hydro_monthly", "years": "dwa tysiące"},
            ["Nieprawidłowy rok lub zakres lat w opcji years", "<code>years</code>"],
        ),
        (
            {"dataset": "pl.imgw.hydro_monthly", "years": "1950-1951"},
            ["minimalny rok: 1951"],
        ),
        (
            {"dataset": "pl.imgw.hydro_monthly", "years": "2020", "params": ["H"]},
            [
                "dotyczy wyłącznie zbioru pl.imgw.hydro_semiannual",
                "<code>params</code>",
            ],
        ),
        (
            {"dataset": "pl.imgw.hydro_daily", "years": "2020", "months": "13"},
            ["Miesiące muszą należeć do zakresu 1–12", "<code>months</code>"],
        ),
        ({"dataset": "meteo/dobowe/synop", "years": "2020"}, ["<code>dataset</code>"]),
        ({"dataset": "pl.imgw.pmaxtp", "years": "2020"}, ["nie udostępnia archiwów"]),
        # Missing field (formerly 422 for a missing subtype)
        ({"years": "2020"}, ["Nieznany zbiór IMGW", "<code>dataset</code>"]),
    ],
)
def test_web_app_download_invalid_input_renders_validation_error(client, form, texts):
    response = client.post("/download/files", data=form)

    _assert_error_partial(
        response, 400, "validation_error", "Nieprawidłowe dane wejściowe", *texts
    )
    assert _links(response.text) == []


# --- PMAXTP -----------------------------------------------------------------


def test_web_app_pmaxtp_renders_tables_and_embeds_result_for_export(
    client, pmaxtp_api_response
):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(PMAXTP_POT_URL).respond(json=pmaxtp_api_response)
        response = client.post("/download/pmaxtp/generate", data=PMAXTP_FORM)

    assert route.call_count == 1
    assert response.status_code == 200
    html = response.text
    assert "Wyniki PMAXTP" in html
    assert "POT (Peak Over Threshold)" in html
    assert "50.06°N, 19.94°E" in html
    for table_id in ("table-ks", "table-sg", "table-rb"):
        assert f'id="{table_id}"' in html
    assert "Kwantyle opadu maksymalnego [mm]" in html
    assert "Górne granice przedziału ufności [mm]" in html
    assert "Błędy estymacji kwantyli [mm]" in html
    # Formatted quantile (ks, 60 min, p=1%) and missing probability rendered as "-"
    assert "<td>28.40</td>" in html
    assert "<td>-</td>" in html
    for label in ("Pobierz CSV", "Pobierz XLSX", "Pobierz JSON"):
        assert label in html
    embedded = re.search(r"const pmaxtpData = (.+);\n", html)
    assert embedded is not None
    data = json.loads(embedded.group(1))
    assert (data["method"], data["latitude"], data["longitude"]) == (
        "POT",
        50.06,
        19.94,
    )
    assert data["data"]["ks"]["60"]["1"] == 28.4
    assert data["data"]["sg"] == pmaxtp_api_response["data"]["sg"]


def test_web_app_pmaxtp_amp_uses_amp_endpoint_and_skips_missing_tables(client):
    amp_url = "https://powietrze.imgw.pl/tpmax-api/point/A/KS/50.0600/19.9400"
    payload = {"data": {"ks": {"5": {"1": 9.876}}}}
    with respx.mock(assert_all_called=True) as mock:
        mock.get(amp_url).respond(json=payload)
        response = client.post(
            "/download/pmaxtp/generate", data={**PMAXTP_FORM, "method": "AMP"}
        )

    html = response.text
    assert "AMP (Annual Max Precipitation)" in html
    assert "<td>9.88</td>" in html
    assert 'id="table-ks"' in html
    assert 'id="table-sg"' not in html
    assert 'id="table-rb"' not in html


def test_web_app_pmaxtp_point_outside_grid_renders_validation_error(client):
    recorded = {"data": {}, "error": "Brak pliku, pradopodobnie poza obszarem PL"}
    with respx.mock(assert_all_called=True) as mock:
        mock.get(PMAXTP_POT_URL).respond(json=recorded)
        response = client.post("/download/pmaxtp/generate", data=PMAXTP_FORM)

    _assert_error_partial(
        response,
        400,
        "validation_error",
        "Punkt 50.06, 19.94 leży poza siatką PMAXTP IMGW-PIB",
    )
    assert "Wyniki PMAXTP" not in response.text


@pytest.mark.parametrize(
    ("form", "texts"),
    [
        (  # was a pydantic 422 before ADR-002
            {**PMAXTP_FORM, "latitude": "północ"},
            ["latitude musi być skończoną liczbą", "<code>latitude</code>"],
        ),
        ({**PMAXTP_FORM, "method": "XYZ"}, ["XYZ", "<code>method</code>"]),
        ({**PMAXTP_FORM, "latitude": "1"}, ["poza zakresem Polski"]),
        ({"method": "POT", "longitude": "19.94"}, ["<code>latitude</code>"]),
    ],
)
def test_web_app_pmaxtp_invalid_input_renders_error_without_request(
    client, form, texts
):
    with respx.mock(assert_all_mocked=True) as mock:
        response = client.post("/download/pmaxtp/generate", data=form)
        assert mock.calls.call_count == 0

    _assert_error_partial(response, 400, "validation_error", *texts)
    assert "Wyniki PMAXTP" not in response.text


@pytest.mark.parametrize(
    "upstream",
    [httpx.Response(503), httpx.ConnectError("brak sieci")],
    ids=["http_503", "network"],
)
def test_web_app_pmaxtp_source_failure_renders_source_unavailable(client, upstream):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(PMAXTP_POT_URL)
        if isinstance(upstream, httpx.Response):
            route.mock(return_value=upstream)
        else:
            route.mock(side_effect=upstream)
        response = client.post("/download/pmaxtp/generate", data=PMAXTP_FORM)

    _assert_error_partial(
        response, 502, "source_unavailable", "Źródło danych niedostępne"
    )


# --- Station search (stations find) ----------------------------------------------


@pytest.fixture
def station_lists(respx_mock):
    return (
        respx_mock.get(HYDRO_LIST_URL).respond(content=HYDRO_CSV.encode("cp1250")),
        respx_mock.get(METEO_LIST_URL).respond(content=METEO_CSV.encode("cp1250")),
    )


def test_web_app_station_search_equals_stations_find(client, station_lists):
    response = client.get("/stations/find", params={"query": "lodz"})

    assert response.status_code == 200
    assert _station_codes(response.text) == _stations_find(query="lodz")
    assert _station_codes(response.text) == ["150190340", "251190470"]
    assert "(1–2 z 2)" in response.text
    assert "<td>ŁÓDŹ ZACHÓD</td>" in response.text
    assert "<td>Ner</td>" in response.text
    assert "<td><code>18</code></td>" in response.text  # hydrographic code
    assert "https://hydro.imgw.pl/#/station/hydro/150190340" in response.text
    assert "https://hydro.imgw.pl/#/station/meteo/251190470" in response.text


def test_web_app_station_search_pages_like_stations_find(client, station_lists):
    first = client.get("/stations/find", params={"query": "lodz", "limit": "1"})
    next_url = re.search(r'hx-get="([^"]+)"[^>]*>\s*Następne', first.text)
    assert next_url is not None
    second = client.get(next_url.group(1).replace("&amp;", "&"))

    for offset, response in enumerate((first, second)):
        expected = _stations_find(query="lodz", limit=1, offset=offset)
        assert _station_codes(response.text) == expected
        assert f"({offset + 1}–{offset + 1} z 2)" in response.text
    assert "Poprzednie" not in first.text
    assert "Następne" not in second.text
    assert 'hx-get="/stations/find?query=lodz&amp;limit=1&amp;offset=0"' in second.text


def test_web_app_station_search_kind_limits_to_one_list(client, respx_mock):
    meteo = respx_mock.get(METEO_LIST_URL).respond(content=METEO_CSV.encode("cp1250"))

    response = client.get("/stations/find", params={"kind": "meteo"})

    assert meteo.call_count == 1
    assert "Stacje meteorologiczne" in response.text
    assert _station_codes(response.text) == ["251190470", "249190310"]  # by name
    assert "<th>Rzeka</th>" not in response.text


def test_web_app_station_search_without_match_shows_empty_message(
    client, station_lists
):
    response = client.get("/stations/find", params={"query": "Atlantyda"})

    assert "(0 z 0)" in response.text
    assert "Brak stacji spełniających kryteria wyszukiwania." in response.text


@pytest.mark.parametrize(
    ("params", "option"),
    [
        ({"limit": "dużo"}, "limit"),
        ({"kind": "opad"}, "kind"),
        ({"offset": "-1"}, "offset"),
    ],
)
def test_web_app_station_search_invalid_option_renders_validation_error(
    client, params, option
):
    with respx.mock(assert_all_mocked=True) as mock:
        response = client.get("/stations/find", params=params)
        assert mock.calls.call_count == 0

    _assert_error_partial(response, 400, "validation_error", f"<code>{option}</code>")


def test_web_app_station_search_source_failure_renders_source_unavailable(
    client, respx_mock
):
    respx_mock.get(HYDRO_LIST_URL).respond(500)

    response = client.get("/stations/find", params={"kind": "hydro"})

    _assert_error_partial(response, 502, "source_unavailable", HYDRO_LIST_URL)


# --- Map data (GET /api/v1/current/hydro-states) ----------------------------------


def test_web_app_map_source_route_serves_marker_fields_with_paging(client):
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
        ]
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get(MAP_URL).respond(json=upstream)
        response = client.get("/api/v1/current/hydro-states", params={"offset": 1})

    assert response.status_code == 200
    page = response.json()["result"]
    assert (page["total"], page["offset"]) == (2, 1)
    assert page["items"] == [
        {
            "station_code": "149190320",
            "name": "Raba Górna",
            "river": None,
            "latitude": 50.1,
            "longitude": 19.2,
            "water_state": None,
        }
    ]


def test_web_app_map_source_failure_is_problem_with_code_title_detail(client):
    with respx.mock(assert_all_called=True) as mock:
        mock.get(MAP_URL).respond(502)
        response = client.get("/api/v1/current/hydro-states")

    assert response.status_code == 502
    problem = response.json()
    assert problem["code"] == "source_unavailable"
    assert problem["title"] == "Data source unavailable"
    assert problem["detail"]
