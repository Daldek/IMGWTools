"""Messages of ``store/export.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "unsupported_export_format_available": Text(
        "Unsupported export format {value!r}; available: {allowed}",
        "Nieobsługiwany format eksportu {value!r}; dostępne: {allowed}",
    ),
    "export_path_points_directory": Text(
        "The export path points to a directory: {target}",
        "Ścieżka eksportu wskazuje katalog: {target}",
    ),
    "target_directory_export_does_not": Text(
        "The target directory of the export does not exist: {parent}",
        "Katalog docelowy eksportu nie istnieje: {parent}",
    ),
    "export_must_written_outside_imgw": Text(
        "The export must be written outside the IMGW store ({store}): {target}",
        "Eksport musi być zapisany poza magazynem IMGW ({store}): {target}",
    ),
    "record_station_from_has_columns": Text(
        "The record of the station {station_code} from {date} has columns outside "
        "the dataset {dataset}: {unknown}",
        "Rekord stacji {station_code} z {date} ma kolumny spoza zbioru {dataset}: "
        "{unknown}",
    ),
    "unknown_year_type_allowed": Text(
        "Unknown year_type {year_type!r}; allowed: {year_types}",
        "Nieznany year_type {year_type!r}; dozwolone: {year_types}",
    ),
    "semi_annual_annual_characteristics_have": Text(
        "Semi-annual and annual characteristics ({dataset}) have only hydrological "
        "years; year_type='calendar' is not allowed",
        "Charakterystyki półroczne i roczne ({dataset}) mają tylko lata "
        "hydrologiczne; year_type='calendar' niedozwolony",
    ),
    "series_station_empty_chosen_range": Text(
        "The series of the station {station} in {dataset} is empty in the chosen "
        "range; the export was rejected so as not to lose the attribution formulas",
        "Szereg stacji {station} w {dataset} jest pusty w wybranym zakresie; eksport "
        "odrzucono, by nie utracić formuł atrybucji",
    ),
    "cancelled": Text(
        "The export was cancelled; the target file stays untouched",
        "Anulowano eksport; plik docelowy pozostaje nietknięty",
    ),
    "station_progress": Text(
        "Station {station}",
        "Stacja {station}",
    ),
    "series_exported": Text(
        "Exported the series of the station {station}",
        "Wyeksportowano szereg stacji {station}",
    ),
    "rows_written": Text(
        "{label}: {written} rows",
        "{label}: {written} wierszy",
    ),
    "archive_progress": Text(
        "Archive {source}",
        "Archiwum {source}",
    ),
    "archive_exported": Text(
        "Exported the archive {source}",
        "Wyeksportowano archiwum {source}",
    ),
    "exported_to_file": Text(
        "{done} to {target}",
        "{done} do {target}",
    ),
}
