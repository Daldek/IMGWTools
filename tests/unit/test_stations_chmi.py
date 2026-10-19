"""find_stations for ČHMÚ: live current metadata and stored lists (spec 2026-10-18 §9.1).

Recorded answers of ``chmi_catalog_recordings.json`` only (respx refuses every
other request); synthetic stations, e.g. ``0-203-1-900001`` Špindlerův Mlýn.
"""

import httpx
import pytest
import respx

from imgwtools._version import __version__
from imgwtools.datasets import station_source_files
from imgwtools.exceptions import (
    IMGWConnectionError,
    IMGWDataError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.fetch import DownloadResult
from imgwtools.stations import find_stations, find_stations_async
from imgwtools.store import init_store, write_archive
from tests.unit.test_store_catalog_chmi import BASE_URL, CASES, body, build, serve

NOW = ("hydro_now_get", "meteo_now_listing", "meteo_now_get", "meteo_now_previous_get")
HYDRO_NOW = BASE_URL + "hydrology/now/metadata/meta1.json"
METEO_LISTING = BASE_URL + "meteorology/climate/now/metadata/"
IMGW_HYDRO, IMGW_METEO = (file.url for file in station_source_files())
IMGW_HYDRO_CSV = '"149190310","RABA GÓRNA","Raba (2138)","2"\n'
IMGW_METEO_CSV = '"249190310","RABA GÓRNA","GR"\n'


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as mocked:
        yield mocked


def traffic(router):
    return [(call.request.method, str(call.request.url)) for call in router.calls]


# --------------------------------------------------------------------------
# Live: current ČHMÚ metadata
# --------------------------------------------------------------------------


async def test_live_search_reads_the_current_metadata_and_finds_czech_names(router):
    routes = serve(router, *NOW)

    found = find_stations(provider="CHMI", query="spindleruv")

    (station,) = found
    assert (
        station.provider,
        station.kind,
        station.station_code,
        station.name,
        station.river,
    ) == ("CHMI", "hydro", "0-203-1-900001", "Špindlerův Mlýn", "Labe")
    assert (station.latitude, station.longitude) == (50.4032345, 15.6012345)
    # One GET of hydro meta1, the meteo listing and only its newest dated file.
    assert traffic(router) == [
        ("GET", HYDRO_NOW),
        ("GET", METEO_LISTING),
        ("GET", METEO_LISTING + "meta1-20261018.json"),
    ]
    assert not routes["meteo_now_previous_get"].called
    assert {call.request.headers["User-Agent"] for call in router.calls} == {
        f"imgwtools/{__version__}"
    }
    assert await find_stations_async(provider="CHMI", query="spindleruv") == found


def test_live_coordinates_are_the_published_values_without_border_check(router):
    serve(router, *NOW)

    located = {
        station.station_code: (station.latitude, station.longitude)
        for station in find_stations(provider="CHMI")
    }

    # Meteo GEOGR1 is the longitude; a station abroad and 0,0 stay as published.
    assert located["0-203-0-90001"] == (50.2147, 14.8213)
    assert located["0-20000-0-99903"] == (64.1311, -21.9405)
    assert located["0-203-1-900004"] == (0.0, 0.0)


def test_kind_reads_only_the_list_of_its_family(router):
    routes = serve(router, *NOW)

    meteo = find_stations(provider="cz.chmi", kind="meteo")

    assert [station.station_code for station in meteo] == [
        "0-203-0-90001",
        "0-20000-0-99903",
        "0-203-0-90000000002",
    ]
    assert not routes["hydro_now_get"].called


@pytest.mark.parametrize(
    ("query", "codes"),
    [
        # Code prefix of full WIGOS segments; CB900003 does not start with it.
        ("0-203-1-9000", ["0-203-1-900004", "0-203-1-900001"]),
        # River without diacritics.
        ("vymyslenka", ["0-203-1-CB900003"]),
        ("ZAPADLA", []),
    ],
)
def test_live_query_matches_names_rivers_and_code_prefixes(router, query, codes):
    serve(router, *NOW)

    found = find_stations(provider="CHMI", kind="hydro", query=query)

    assert [station.station_code for station in found] == codes


def test_without_provider_both_providers_are_searched_in_registry_order(router):
    serve(router, *NOW)
    router.get(IMGW_HYDRO).respond(content=IMGW_HYDRO_CSV.encode("cp1250"))
    router.get(IMGW_METEO).respond(content=IMGW_METEO_CSV.encode("cp1250"))

    found = find_stations(query="ra")

    # "ra" is in RABA GÓRNA (IMGW-PIB) and Srážková Lhota (ČHMÚ, without diacritics).
    assert [(s.provider, s.kind, s.station_code) for s in found] == [
        ("IMGW-PIB", "hydro", "149190310"),
        ("IMGW-PIB", "meteo", "249190310"),
        ("CHMI", "meteo", "0-203-0-90000000002"),
    ]


async def test_unreachable_chmi_source_is_source_unavailable_naming_it(router):
    serve(router, "hydro_now_outage")

    with pytest.raises(IMGWConnectionError) as error:
        find_stations(provider="CHMI", kind="hydro")
    with pytest.raises(IMGWConnectionError) as async_error:
        await find_stations_async(provider="CHMI", kind="hydro")

    for raised in (error.value, async_error.value):
        assert raised.code == "source_unavailable"
        assert raised.details == {
            "url": HYDRO_NOW,
            "reason": "http_status",
            "status": 503,
        }
        assert "ČHMÚ" in raised.detail and HYDRO_NOW in raised.detail


def test_network_error_of_the_listing_is_source_unavailable(router):
    router.get(METEO_LISTING).mock(side_effect=httpx.ConnectError("brak sieci"))

    with pytest.raises(IMGWConnectionError) as error:
        find_stations(provider="CHMI", kind="meteo")

    assert error.value.details == {"url": METEO_LISTING, "reason": "network"}


def test_listing_without_dated_metadata_is_a_data_error(router):
    listing = body("meteo_now_listing").replace(b"meta1-", b"meta5-")
    router.get(METEO_LISTING).respond(content=listing)

    with pytest.raises(IMGWDataError) as error:
        find_stations(provider="CHMI", kind="meteo")

    assert error.value.details == {"url": METEO_LISTING}


async def test_unknown_provider_is_a_validation_error_without_requests(router):
    with pytest.raises(IMGWValidationError) as error:
        find_stations(provider="SHMU")
    with pytest.raises(IMGWValidationError):
        await find_stations_async(provider="SHMU")

    assert error.value.details["option"] == "provider"
    assert not router.calls


# --------------------------------------------------------------------------
# Store: stored lists located by the provider's catalog
# --------------------------------------------------------------------------


async def test_store_search_reads_the_chmi_lists_located_by_the_chmi_catalog(
    tmp_path,
):
    store = init_store(tmp_path / "store")
    build(store)

    with respx.mock(assert_all_called=False) as offline:
        found = find_stations(
            source="store", root=store.root, provider="CHMI", query="spindleruv"
        )
        everything = find_stations(source="store", root=store.root)
        assert await find_stations_async(source="store", root=store.root) == everything

    assert not offline.calls
    (station,) = found
    # Name of the stored historical list, location of the catalog (now meta1).
    assert (station.provider, station.name) == ("CHMI", "Špindlerův Mlýn - most")
    assert (station.latitude, station.longitude) == (50.4032345, 15.6012345)
    located = {s.station_code: (s.latitude, s.longitude) for s in everything}
    # The catalog rejected the station abroad: no location, unlike the list.
    assert located["0-20000-0-99903"] == (None, None)
    # IMGW-PIB has no stored lists here, so the search skips it.
    assert {s.provider for s in everything} == {"CHMI"}


def test_store_without_lists_of_a_named_provider_is_not_found(tmp_path):
    store = init_store(tmp_path / "store")
    build(store)
    empty = init_store(tmp_path / "empty")

    with pytest.raises(IMGWStoreError) as named:
        find_stations(source="store", root=store.root, provider="IMGW-PIB")
    with pytest.raises(IMGWStoreError) as nothing:
        find_stations(source="store", root=empty.root)

    assert named.value.code == nothing.value.code == "not_found"


def test_provider_with_only_some_stored_lists_is_not_skipped(tmp_path):
    store = init_store(tmp_path / "store")
    hydro, _ = station_source_files(provider="CHMI")
    data = body("hydro_stations_get")
    headers = CASES["hydro_stations_get"]["headers"]
    write_archive(
        store,
        archive=hydro,
        response=DownloadResult(
            data, hydro.url, headers["ETag"], headers["Last-Modified"], len(data)
        ),
    )

    found = find_stations(source="store", root=store.root, kind="hydro")
    with pytest.raises(IMGWStoreError) as error:
        find_stations(source="store", root=store.root)

    # Without a catalog the stored list keeps its own coordinates.
    assert [(s.station_code, s.latitude) for s in found] == [
        ("0-203-1-900004", 49.2012345),
        ("0-203-1-900001", 50.4012345),
        ("0-203-1-900002", 49.8512345),
    ]
    assert error.value.code == "not_found"
    assert "cz.chmi.meteo_stations" in error.value.detail
