"""
Station search and current states of hydrological stations.

`find_stations` searches the station lists of the data providers (IMGW-PIB
and ČHMÚ), live or from a versioned store; `fetch_hydro_states` reads the
locations and current water states of hydrological stations from the
hydro.imgw.pl map API.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from imgwtools._parsing.chmi import iter_stations, parse_listing
from imgwtools._parsing.stations import parse_stations_csv
from imgwtools._version import __version__
from imgwtools.datasets import (
    ProviderDescriptor,
    get_provider,
    providers,
    station_source_files,
)
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.fetch import (
    _IDENTIFY,
    DEFAULT_TIMEOUT,
    _get,
    _get_async,
    _json_payload,
)
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
# The newest dated file of a listed directory, as plans name it.
_NEWEST = "meta1-<RRRRMMDD>.json"


# ============================================================================
# Station search
# ============================================================================


def _normalize(text: str) -> str:
    """
    Casefolded text without diacritics (``"ŁÓDŹ"`` -> ``"lodz"``).

    Polish ``ł`` becomes ``l`` (it has no decomposition); Czech letters
    decompose, so ``"Špindlerův"`` becomes ``"spindleruv"``.
    """
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


def _owners(provider: str | None) -> tuple[ProviderDescriptor, ...]:
    """Providers of a search: every provider for None, else the named one."""
    return providers() if provider is None else (get_provider(provider),)


def _matching(
    entries: Iterable[StationListEntry], query: str | None
) -> tuple[StationListEntry, ...]:
    """Stations matching ``query``, by provider, family, normalized name and code."""
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
    rank = {owner.id: index for index, owner in enumerate(providers())}
    order = {family: index for index, family in enumerate(_KINDS)}
    return tuple(
        sorted(
            rows,
            key=lambda entry: (
                rank[entry.provider],
                order[entry.kind],
                _normalize(entry.name),
                entry.station_code,
            ),
        )
    )


@dataclass(frozen=True)
class _LiveSource:
    """
    Live station list of one provider and family.

    ``listing`` marks the URL of a directory listing whose newest
    ``meta1-<YYYYMMDD>.json`` is the list (ČHMÚ meteo ``now`` metadata).
    """

    provider: ProviderDescriptor
    kind: Literal["hydro", "meteo"]
    url: str
    listing: bool = False


def _live_sources(
    kinds: Sequence[Literal["hydro", "meteo"]],
    owners: Iterable[ProviderDescriptor],
) -> list[_LiveSource]:
    """Live station list of each provider and family, in search order."""
    # The current ČHMÚ metadata, as the first source of its catalog (§7.2).
    from imgwtools.store.catalog import _CHMI_HYDRO_NOW, _CHMI_METEO_NOW_DIR

    sources: list[_LiveSource] = []
    for owner in owners:
        if owner.id == "CHMI":
            hydro = _LiveSource(owner, "hydro", owner.base_url + _CHMI_HYDRO_NOW)
            meteo = _LiveSource(
                owner, "meteo", owner.base_url + _CHMI_METEO_NOW_DIR, listing=True
            )
        else:
            hydro_list, meteo_list = station_source_files(provider=owner.id)
            hydro = _LiveSource(owner, "hydro", hydro_list.url)
            meteo = _LiveSource(owner, "meteo", meteo_list.url)
        sources.extend(hydro if family == "hydro" else meteo for family in kinds)
    return sources


def _live_urls(
    kinds: Sequence[Literal["hydro", "meteo"]],
    owners: Iterable[ProviderDescriptor],
) -> list[str]:
    """URLs a live search reads, the newest file of a listing as a pattern (plans)."""
    urls: list[str] = []
    for source in _live_sources(kinds, owners):
        urls.append(source.url)
        if source.listing:
            urls.append(source.url + _NEWEST)
    return urls


def _identity(source: _LiveSource) -> tuple[Mapping[str, str] | None, str]:
    """Request headers and the server name of errors (ČHMÚ requests name the library)."""
    if source.provider.id == "CHMI":
        return _IDENTIFY, source.provider.short_name
    return None, "IMGW"


def _newest(source: _LiveSource, content: bytes) -> str:
    """URL of the newest ``meta1-<YYYYMMDD>.json`` in the listing of ``source``."""
    from imgwtools.store.catalog import _CHMI_METEO_NOW_FILE

    names = sorted(
        entry.name
        for entry in parse_listing(content, url=source.url)
        if _CHMI_METEO_NOW_FILE.fullmatch(entry.name)
    )
    if not names:
        raise IMGWDataError(
            f"Nieczytelny listing {source.url}: brak pliku {_NEWEST}",
            details={"url": source.url},
        )
    return source.url + names[-1]


def _parsed(source: _LiveSource, content: bytes, url: str) -> list[StationListEntry]:
    """Stations of a live list: an IMGW-PIB CSV or ČHMÚ metadata JSON."""
    if source.provider.id == "CHMI":
        return list(iter_stations(content, kind=source.kind, filename=url))
    return list(parse_stations_csv(content, kind=source.kind))


def _read_live(source: _LiveSource, timeout: float) -> list[StationListEntry]:
    """Stations of one live list (one GET; a listed directory adds its listing)."""
    headers, name = _identity(source)
    url = source.url
    if source.listing:
        listing = _get(url, timeout=timeout, headers=headers, source=name)
        url = _newest(source, listing.content)
    response = _get(url, timeout=timeout, headers=headers, source=name)
    return _parsed(source, response.content, url)


async def _read_live_async(
    source: _LiveSource, timeout: float
) -> list[StationListEntry]:
    """Async twin of `_read_live`."""
    headers, name = _identity(source)
    url = source.url
    if source.listing:
        listing = await _get_async(url, timeout=timeout, headers=headers, source=name)
        url = _newest(source, listing.content)
    response = await _get_async(url, timeout=timeout, headers=headers, source=name)
    return _parsed(source, response.content, url)


def _located(
    root: RootArg, owner: ProviderDescriptor, entries: list[StationListEntry]
) -> list[StationListEntry]:
    """Entries located by the provider's current station catalog, when it has one."""
    from imgwtools.store import read_catalog

    try:
        features = read_catalog(root=root, provider=owner.id)
    except IMGWStoreError as exc:
        if exc.code != "not_found":
            raise
        return entries  # without a catalog the coordinates of the list stay
    points = {feature.station_code: feature.geometry for feature in features}
    located: list[StationListEntry] = []
    for entry in entries:
        if entry.station_code not in points:
            located.append(entry)
            continue
        point = points[entry.station_code]
        located.append(
            replace(
                entry,
                longitude=None if point is None else point[0],
                latitude=None if point is None else point[1],
            )
        )
    return located


def _stored(
    root: RootArg,
    kinds: Sequence[Literal["hydro", "meteo"]],
    owners: Sequence[ProviderDescriptor],
    *,
    explicit: bool,
) -> list[StationListEntry]:
    """
    Stored station lists of the providers, located by their current catalogs.

    A provider without any stored list is skipped unless it was named
    (``explicit``); a provider holding only some of the lists, or a store
    without the lists of all searched providers, is ``not_found``.
    """
    from imgwtools.store import read_station_list

    found: list[StationListEntry] = []
    absent: IMGWStoreError | None = None
    read = False
    for owner in owners:
        entries: list[StationListEntry] = []
        missing: list[IMGWStoreError] = []
        for family in kinds:
            try:
                entries.extend(read_station_list(root, kind=family, provider=owner.id))
            except IMGWStoreError as exc:
                if exc.code != "not_found":
                    raise
                missing.append(exc)
        if missing and (explicit or len(missing) < len(kinds)):
            raise missing[0]
        if missing:
            absent = absent or missing[0]
            continue
        read = True
        found.extend(_located(root, owner, entries))
    if not read and absent is not None:
        raise absent
    return found


def find_stations(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    query: str | None = None,
    source: Literal["live", "store"] = "live",
    root: RootArg | None = None,
    provider: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StationListEntry, ...]:
    """
    Find stations of IMGW-PIB and ČHMÚ by name, river or code prefix.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Station family; None searches both lists.
    query : str or None, optional
        Text matched case- and diacritic-insensitively (``"lodz"`` finds
        ``"ŁÓDŹ"``, ``"spindleruv"`` finds ``"Špindlerův Mlýn"``) as a
        fragment of the station name or river, or as a prefix of the
        station code. None returns every station.
    source : {"live", "store"}, optional
        ``"live"`` downloads the current lists of each provider: the
        IMGW-PIB station list CSV of each family (one GET per family) and
        the ČHMÚ metadata ``hydrology/now/metadata/meta1.json`` and the
        newest ``meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json``
        (its directory listing, then the file). ``"store"`` reads the
        current stored lists offline.
    root : str, os.PathLike or StoreHandle, optional
        Store root; required with ``source="store"`` and not allowed with
        ``source="live"``.
    provider : str or None, optional
        Provider identifier or key prefix (``"IMGW-PIB"``, ``"CHMI"``,
        ``"cz.chmi"``); None searches every provider and, with
        ``source="store"``, skips providers without stored lists.
    timeout : float, optional
        Request timeout in seconds (live source).

    Returns
    -------
    tuple of StationListEntry
        Matching stations ordered by provider (registry order), family
        (hydro, meteo), normalized name and code, each with its
        ``provider``; a code listed twice on the IMGW-PIB meteo list is
        returned for each row. Live ČHMÚ entries carry the coordinates
        published in the metadata, without validation against the country
        border; live IMGW-PIB lists have no coordinates. With
        ``source="store"`` the coordinates come from the provider's current
        station catalog (None for stations with ``geometry: null``); without
        a catalog the stored list keeps its own (none for IMGW-PIB).

    Raises
    ------
    IMGWValidationError
        If ``kind``, ``source`` or ``provider`` is unknown, ``query`` is
        blank, or ``root`` is missing with ``source="store"`` or given with
        ``source="live"``.
    IMGWConnectionError
        If a provider's server cannot be reached or answers with an HTTP
        error (``details`` ``url``, ``reason`` and, for HTTP errors,
        ``status``).
    IMGWStoreError
        If the root is not a supported store, holds no station list of any
        searched provider, or lacks a list of a named ``provider`` (code
        ``not_found``).
    IMGWDataError
        If a live list or listing, or a stored list or catalog, is malformed
        or does not match its sidecar.

    Examples
    --------
    >>> [s.name for s in find_stations(kind="hydro", query="lodz")]
    >>> find_stations(provider="CHMI", query="spindleruv")
    >>> find_stations(query="1491", source="store", root="data/store")
    """
    kinds, needle = _search_kinds(kind, query, source, root)
    owners = _owners(provider)
    if root is not None:  # validated: root is given exactly with source="store"
        stored = _stored(root, kinds, owners, explicit=provider is not None)
        return _matching(stored, needle)
    entries = [
        entry
        for live in _live_sources(kinds, owners)
        for entry in _read_live(live, timeout)
    ]
    return _matching(entries, needle)


async def find_stations_async(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    query: str | None = None,
    source: Literal["live", "store"] = "live",
    root: RootArg | None = None,
    provider: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StationListEntry, ...]:
    """
    Async version of `find_stations`, with identical arguments and result.

    See `find_stations` for full documentation.
    """
    kinds, needle = _search_kinds(kind, query, source, root)
    owners = _owners(provider)
    if root is not None:  # validated: root is given exactly with source="store"
        stored = _stored(root, kinds, owners, explicit=provider is not None)
        return _matching(stored, needle)
    entries: list[StationListEntry] = []
    for live in _live_sources(kinds, owners):
        entries.extend(await _read_live_async(live, timeout))
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
