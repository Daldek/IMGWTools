"""Messages of ``_parsing/__init__.py``, ``_parsing/common.py``, ``_parsing/stations.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "no_parser_archive": Text(
        "No parser for the archive: {dataset}",
        "Brak parsera archiwum: {dataset}",
    ),
    "archive_too_large": Text(
        "The archive {filename} is too large",
        "Zbyt duże archiwum {filename}",
    ),
    "path_not_allowed": Text(
        "A path not allowed in {filename}: {name}",
        "Niedozwolona ścieżka w {filename}: {name}",
    ),
    "csv_too_large": Text(
        "The CSV is too large in {filename}: {name}",
        "Zbyt duży CSV w {filename}: {name}",
    ),
    "unreadable_archive": Text(
        "Unreadable archive {filename}: {exc}",
        "Nieczytelne archiwum {filename}: {exc}",
    ),
    "unknown_kind_station_list_allowed": Text(
        "Unknown kind of station list: {kind!r}; allowed: hydro, meteo",
        "Nieznany rodzaj listy stacji: {kind!r}; dozwolone hydro, meteo",
    ),
    "zip_archive": Text(
        "ZIP archive",
        "archiwum ZIP",
    ),
}
