"""
Station search and current states of hydrological stations.

`find_stations` searches the IMGW station lists, live or from a versioned
store; `fetch_hydro_states` reads the locations and current water states of
hydrological stations from the hydro.imgw.pl map API.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from imgwtools._parsing.stations import parse_stations_csv
from imgwtools._version import __version__
from imgwtools.datasets import station_source_files
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.fetch import DEFAULT_TIMEOUT, _get, _get_async, _json_payload
from imgwtools.models import HydroState, StationListEntry

if TYPE_CHECKING:
    from imgwtools.store.catalog import RootArg

HYDRO_MAP_API_URL = "https://hydro-back.imgw.pl/map/stations/hydrologic"
_MAP_HEADERS = {
    "User-Agent": f"IMGWTools/{__version__}",
    "Referer": "https://hydro.imgw.pl/",
}
_KINDS: tuple[Literal["hydro", "meteo"], ...] = ("hydro", "meteo")
_SOURCES = ("live", "store")
_CATALOG_SLOT = "catalog:stations"


# ============================================================================
# Station search
# ============================================================================


def _normalize(text: str) -> str:
    """Casefolded text without Polish diacritics (``"ŁÓDŹ"`` -> ``"lodz"``)."""
    folded = unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
    return "".join(char for char in folded if not unicodedata.combining(char))


def _search_kinds(
    kind: str | None, query: str | None, source: str, root: object
) -> tuple[tuple[Literal["hydro", "meteo"], ...], str | None]:
    """Validate the search options; return the families and stripped query."""
    if kind is not None and kind not in _KINDS:
        raise IMGWValidationError(
            f"Nieznany rodzaj stacji: {kind!r}; dozwolone hydro, meteo",
            details={"option": "kind", "allowed": list(_KINDS)},
        )
    if source not in _SOURCES:
        raise IMGWValidationError(
            f"Nieznane źródło listy stacji: {source!r}; dozwolone live, store",
            details={"option": "source", "allowed": list(_SOURCES)},
        )
    if source == "store" and root is None:
        raise IMGWValidationError(
            "Wyszukiwanie w magazynie (source=store) wymaga katalogu magazynu root",
            details={"option": "root"},
        )
    if source == "live" and root is not None:
        raise IMGWValidationError(
            "Katalog magazynu root jest dozwolony tylko przy source=store",
            details={"option": "root"},
        )
    needle = None
    if query is not None:
        needle = query.strip()
        if not needle:
            raise IMGWValidationError(
                "Fraza wyszukiwania stacji nie może być pusta",
                details={"option": "query"},
            )
    kinds = _KINDS if kind is None else (kind,)
    return kinds, needle


def _matching(
    entries: Iterable[StationListEntry], query: str | None
) -> tuple[StationListEntry, ...]:
    """Stations matching ``query``, ordered by family, normalized name and code."""
    rows = list(entries)
    if query is not None:
        needle = _normalize(query)
        rows = [
            entry
            for entry in rows
            if needle in _normalize(entry.name)
            or (entry.river is not None and needle in _normalize(entry.river))
            or entry.station_code.startswith(query)
        ]
    order = {family: index for index, family in enumerate(_KINDS)}
    return tuple(
        sorted(
            rows,
            key=lambda entry: (
                order[entry.kind],
                _normalize(entry.name),
                entry.station_code,
            ),
        )
    )


def _live_sources(
    kinds: Iterable[Literal["hydro", "meteo"]],
) -> list[tuple[Literal["hydro", "meteo"], str]]:
    """Station list URL of each requested family."""
    urls = dict(zip(_KINDS, (file.url for file in station_source_files()), strict=True))
    return [(family, urls[family]) for family in kinds]


def _stored(
    root: RootArg, kinds: Iterable[Literal["hydro", "meteo"]]
) -> list[StationListEntry]:
    """Stored station lists with coordinates from the current station catalog."""
    from imgwtools.store import current_version, read_catalog, read_station_list

    entries = [
        entry for family in kinds for entry in read_station_list(root, kind=family)
    ]
    catalog = current_version(root, slot=_CATALOG_SLOT)
    if catalog is None or catalog.version is None:
        return entries
    points = {
        feature.station_code: feature.geometry
        for feature in read_catalog(catalog.version)
        if feature.geometry is not None
    }
    located: list[StationListEntry] = []
    for entry in entries:
        point = points.get(entry.station_code)
        located.append(
            entry
            if point is None
            else replace(entry, longitude=point[0], latitude=point[1])
        )
    return located


def find_stations(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    query: str | None = None,
    source: Literal["live", "store"] = "live",
    root: RootArg | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StationListEntry, ...]:
    """
    Find IMGW stations by name, river or code prefix.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Station family; None searches both lists.
    query : str or None, optional
        Text matched case- and diacritic-insensitively (``"lodz"`` finds
        ``"ŁÓDŹ"``) as a fragment of the station name or river, or as a
        prefix of the station code. None returns every station.
    source : {"live", "store"}, optional
        ``"live"`` downloads the IMGW station list CSV of each family (one
        GET per family); ``"store"`` reads the current stored lists offline.
    root : str, os.PathLike or StoreHandle, optional
        Store root; required with ``source="store"`` and not allowed with
        ``source="live"``.
    timeout : float, optional
        Request timeout in seconds (live source).

    Returns
    -------
    tuple of StationListEntry
        Matching stations ordered by family (hydro, meteo), normalized name
        and code; a code listed twice on the meteo list is returned for each
        row. With ``source="store"`` ``latitude``/``longitude`` come from the
        current station catalog (None without a catalog or for stations with
        ``geometry: null``); live lists have no coordinates.

    Raises
    ------
    IMGWValidationError
        If ``kind`` or ``source`` is unknown, ``query`` is blank, or ``root``
        is missing with ``source="store"`` or given with ``source="live"``.
    IMGWConnectionError
        If an IMGW server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    IMGWStoreError
        If the root is not a supported store or holds no station list.
    IMGWDataError
        If a stored list or catalog does not match its sidecar.

    Examples
    --------
    >>> [s.name for s in find_stations(kind="hydro", query="lodz")]
    >>> find_stations(query="1491", source="store", root="data/store")
    """
    kinds, needle = _search_kinds(kind, query, source, root)
    if root is not None:  # validated: root is given exactly with source="store"
        return _matching(_stored(root, kinds), needle)
    entries = [
        entry
        for family, url in _live_sources(kinds)
        for entry in parse_stations_csv(_get(url, timeout=timeout).content, kind=family)
    ]
    return _matching(entries, needle)


async def find_stations_async(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    query: str | None = None,
    source: Literal["live", "store"] = "live",
    root: RootArg | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StationListEntry, ...]:
    """
    Async version of `find_stations`, with identical arguments and result.

    See `find_stations` for full documentation.
    """
    kinds, needle = _search_kinds(kind, query, source, root)
    if root is not None:  # validated: root is given exactly with source="store"
        return _matching(_stored(root, kinds), needle)
    entries: list[StationListEntry] = []
    for family, url in _live_sources(kinds):
        response = await _get_async(url, timeout=timeout)
        entries.extend(parse_stations_csv(response.content, kind=family))
    return _matching(entries, needle)


# ============================================================================
# Hydrological station states (hydro.imgw.pl map)
# ============================================================================


def _map_url(main_only: bool) -> str:
    return f"{HYDRO_MAP_API_URL}?onlyMainStations={'true' if main_only else 'false'}"


def _hydro_states(payload: Any, url: str) -> list[HydroState]:
    """
    Parse the map API answer; stations without a code or with invalid values are skipped.

    The API uses short keys: ``id`` code, ``n`` name, ``la``/``lo``
    coordinates, ``s`` water state; ``rzeka`` is the river name.
    """
    items = payload.get("stations", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise IMGWDataError(f"Nieoczekiwana odpowiedź z {url}: oczekiwano listy stacji")
    states: list[HydroState] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            states.append(
                HydroState(
                    station_code=str(item["id"]),
                    name=item.get("n", item.get("name", "")),
                    river=item.get("rzeka"),
                    latitude=item.get("la", item.get("lat")),
                    longitude=item.get("lo", item.get("lon")),
                    water_state=item.get("s", item.get("waterStateStatus")),
                )
            )
        except ValidationError:
            continue
    return states


def fetch_hydro_states(
    *,
    main_only: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroState]:
    """
    Fetch locations and current water states of hydrological stations.

    Reads the map API of https://hydro.imgw.pl (``hydro-back.imgw.pl``),
    which requires the ``Referer`` and ``User-Agent`` headers sent here.

    Parameters
    ----------
    main_only : bool, optional
        If True, only main stations; by default all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of HydroState
        Stations in API order; a station without a code or with invalid
        values is skipped, missing coordinates or state are None.

    Raises
    ------
    IMGWConnectionError
        If the server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    IMGWDataError
        If the response is not JSON or holds no station list.

    Examples
    --------
    >>> alarmed = [s for s in fetch_hydro_states() if s.water_state == "alarm"]
    """
    url = _map_url(main_only)
    response = _get(url, timeout=timeout, headers=_MAP_HEADERS)
    return _hydro_states(_json_payload(response), url)


async def fetch_hydro_states_async(
    *,
    main_only: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroState]:
    """
    Async version of `fetch_hydro_states`, with identical arguments and result.

    See `fetch_hydro_states` for full documentation.
    """
    url = _map_url(main_only)
    response = await _get_async(url, timeout=timeout, headers=_MAP_HEADERS)
    return _hydro_states(_json_payload(response), url)
