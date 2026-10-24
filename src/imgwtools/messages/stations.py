"""Messages of ``stations.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "unknown_kind_station_allowed_hydro": Text(
        "Unknown kind of station: {kind!r}; allowed: hydro, meteo",
        "Nieznany rodzaj stacji: {kind!r}; dozwolone hydro, meteo",
    ),
    "unknown_source_station_list_allowed": Text(
        "Unknown source of the station list: {source!r}; allowed: live, store",
        "Nieznane źródło listy stacji: {source!r}; dozwolone live, store",
    ),
    "search_store_source_store_needs": Text(
        "A search in the store (source=store) needs the store directory root",
        "Wyszukiwanie w magazynie (source=store) wymaga katalogu magazynu root",
    ),
    "store_directory_root_allowed_only": Text(
        "The store directory root is allowed only with source=store",
        "Katalog magazynu root jest dozwolony tylko przy source=store",
    ),
    "station_search_phrase_must_not": Text(
        "The station search phrase must not be empty",
        "Fraza wyszukiwania stacji nie może być pusta",
    ),
    "unreadable_listing_no_file": Text(
        "Unreadable listing {url}: no file {newest}",
        "Nieczytelny listing {url}: brak pliku {newest}",
    ),
    "unexpected_response_from_list_stations": Text(
        "Unexpected response from {url}: a list of stations was expected",
        "Nieoczekiwana odpowiedź z {url}: oczekiwano listy stacji",
    ),
}
