"""Offline tests for find_stations and fetch_hydro_states (respx-mocked HTTP)."""

import pytest
import respx

from imgwtools.datasets import station_source_files
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.stations import (
    HYDRO_MAP_API_URL,
    fetch_hydro_states,
    fetch_hydro_states_async,
    find_stations,
    find_stations_async,
)
from imgwtools.store import init_store
from imgwtools.testing import build_fixture_store

HYDRO_URL, METEO_URL = (file.url for file in station_source_files())
HYDRO_CSV = (
    '"150190340","ŁÓDŹ ZACHÓD","Ner (18)","1"\n'
    '"149190310","RABA GÓRNA","Raba (2138)","2"\n'
    '"149190300","SAN ESCOBAR","Łódka (2139)",""\n'
)
METEO_CSV = (
    '"251190470","ŁÓDŹ WSCHÓD","LW"\n'
    '"249190310","RABA GÓRNA","GR"\n'
    '"249190310","RABA GÓRNA","GR2"\n'
)
MAP_PAYLOAD = {
    "stations": [
        {
            "id": 149190310,
            "n": "RABA GÓRNA",
            "rzeka": "Raba",
            "la": 49.61,
            "lo": 20.05,
            "s": "high",
        },
        {"id": "149190311", "n": "SAN ESCOBAR", "la": "brak", "lo": 20.1},
        {"n": "BEZ KODU", "la": 50.0, "lo": 20.0},
        {"id": "149190312", "n": "ŻABIE", "s": "low"},
    ]
}


@pytest.fixture
def lists(respx_mock):
    """Serve both live station lists in CP1250."""
    return (
        respx_mock.get(HYDRO_URL).respond(content=HYDRO_CSV.encode("cp1250")),
        respx_mock.get(METEO_URL).respond(content=METEO_CSV.encode("cp1250")),
    )


def _rows(stations):
    return [(s.kind, s.station_code, s.name) for s in stations]


# --------------------------------------------------------------------------
# find_stations, live lists
# --------------------------------------------------------------------------


def test_find_stations_without_query_returns_both_lists_in_order(lists):
    stations = find_stations(provider="IMGW-PIB")

    assert _rows(stations) == [
        ("hydro", "150190340", "ŁÓDŹ ZACHÓD"),
        ("hydro", "149190310", "RABA GÓRNA"),
        ("hydro", "149190300", "SAN ESCOBAR"),
        ("meteo", "251190470", "ŁÓDŹ WSCHÓD"),
        ("meteo", "249190310", "RABA GÓRNA"),
        ("meteo", "249190310", "RABA GÓRNA"),
    ]
    assert [s.short_code for s in stations[-2:]] == ["GR", "GR2"]
    assert all(s.latitude is None and s.longitude is None for s in stations)
    assert (stations[1].river, stations[1].hydrographic_code) == ("Raba", "2138")


@pytest.mark.parametrize(
    "query, expected",
    [
        # Name without Polish characters, any case.
        ("lodz", [("hydro", "150190340"), ("meteo", "251190470")]),
        ("  ŁÓDŹ ", [("hydro", "150190340"), ("meteo", "251190470")]),
        # River fragment (Ner) and river with Polish characters (Łódka).
        ("ner", [("hydro", "150190340")]),
        ("lodka", [("hydro", "149190300")]),
        # Code prefix; ordered by name, not by code.
        ("1491903", [("hydro", "149190310"), ("hydro", "149190300")]),
        # A code fragment that is not a prefix does not match.
        ("9190", []),
    ],
)
def test_find_stations_matches_name_river_and_code_prefix(lists, query, expected):
    stations = find_stations(query=query, provider="IMGW-PIB")
    assert [(s.kind, s.station_code) for s in stations] == expected


async def test_find_stations_kind_requests_only_its_list(respx_mock):
    meteo = respx_mock.get(METEO_URL).respond(content=METEO_CSV.encode("cp1250"))

    stations = find_stations(kind="meteo", query="raba", provider="IMGW-PIB")

    assert _rows(stations) == [("meteo", "249190310", "RABA GÓRNA")] * 2
    assert (
        await find_stations_async(kind="meteo", query="raba", provider="IMGW-PIB")
        == stations
    )
    assert meteo.call_count == 2


@pytest.mark.parametrize(
    "kwargs, option",
    [
        ({"kind": "synop"}, "kind"),
        ({"source": "archive"}, "source"),
        ({"source": "store"}, "root"),
        ({"root": "data/store"}, "root"),
        ({"query": "   "}, "query"),
    ],
)
async def test_find_stations_invalid_options_are_validation_errors(
    respx_mock, kwargs, option
):
    with pytest.raises(IMGWValidationError) as error:
        find_stations(**kwargs)
    with pytest.raises(IMGWValidationError):
        await find_stations_async(**kwargs)

    assert error.value.code == "validation_error"
    assert error.value.details["option"] == option
    assert not respx_mock.calls


# --------------------------------------------------------------------------
# find_stations, stored lists
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_store(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("fixture") / "store").root


async def test_find_stations_store_reads_catalog_coordinates_offline(fixture_store):
    with respx.mock(assert_all_called=False) as router:
        stations = find_stations(source="store", root=fixture_store)
        async_stations = await find_stations_async(source="store", root=fixture_store)

    assert not router.calls
    assert async_stations == stations
    located = {
        s.station_code: (s.latitude, s.longitude)
        for s in stations
        if s.latitude is not None
    }
    assert located == {"149190310": (49.7, 20.1), "123750000": (52.23, 21.01)}
    # Catalog features with geometry=null leave the coordinates empty.
    unlocated = {s.station_code for s in stations if s.latitude is None}
    assert {"149190311", "149190312", "123760000"} <= unlocated
    assert [s.kind for s in stations] == sorted(
        (s.kind for s in stations), key=("hydro", "meteo").index
    )


def test_find_stations_store_filters_like_live(fixture_store):
    with respx.mock(assert_all_called=False) as router:
        stations = find_stations(
            kind="hydro", query="bez miejsca", root=fixture_store, source="store"
        )

    assert not router.calls
    assert [(s.station_code, s.latitude) for s in stations] == [("149190312", None)]


def test_find_stations_store_without_lists_is_store_error(tmp_path):
    root = init_store(tmp_path / "store").root
    with pytest.raises(IMGWStoreError, match="listy stacji"):
        find_stations(source="store", root=root)


# --------------------------------------------------------------------------
# fetch_hydro_states
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, only_main", [({}, "false"), ({"main_only": True}, "true")]
)
async def test_fetch_hydro_states_sends_headers_and_main_only(
    respx_mock, kwargs, only_main
):
    route = respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD)

    states = fetch_hydro_states(**kwargs)
    assert await fetch_hydro_states_async(**kwargs) == states

    for call in route.calls:
        request = call.request
        assert request.url.params["onlyMainStations"] == only_main
        assert request.headers["Referer"] == "https://hydro.imgw.pl/"
        assert request.headers["User-Agent"].startswith("IMGWTools/")


def test_fetch_hydro_states_reads_river_and_skips_invalid_stations(respx_mock):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD)

    states = fetch_hydro_states()

    assert [s.model_dump() for s in states] == [
        {
            "station_code": "149190310",
            "name": "RABA GÓRNA",
            "river": "Raba",
            "latitude": 49.61,
            "longitude": 20.05,
            "water_state": "high",
        },
        {
            "station_code": "149190312",
            "name": "ŻABIE",
            "river": None,
            "latitude": None,
            "longitude": None,
            "water_state": "low",
        },
    ]


@pytest.mark.parametrize(
    "payload, expected",
    [
        (MAP_PAYLOAD["stations"][:1], ["149190310"]),
        ({"numOfAlarmStates": 0}, []),
    ],
)
def test_fetch_hydro_states_accepts_list_and_empty_wrapper(
    respx_mock, payload, expected
):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json=payload)
    assert [s.station_code for s in fetch_hydro_states()] == expected


def test_fetch_hydro_states_rejects_non_list_stations(respx_mock):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json={"stations": "brak"})
    with pytest.raises(IMGWDataError, match="oczekiwano listy stacji"):
        fetch_hydro_states()
