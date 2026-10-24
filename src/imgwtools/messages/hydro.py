"""Messages of ``_parsing/hydro.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "inconsistent_number_columns": Text(
        "An inconsistent number of columns ({widths}) in {filename}",
        "Niejednolita liczba kolumn ({widths}) w {filename}",
    ),
    "unknown_layout_semi_annual_file": Text(
        "Unknown layout of a semi-annual file ({width} columns) in {filename}",
        "Nieznany układ pliku półrocznego ({width} kolumn) w {filename}",
    ),
    "invalid_record_row": Text(
        "An invalid record {filename}, row {number}",
        "Błędny rekord {filename}, wiersz {number}",
    ),
    "invalid_station_code": Text(
        "An invalid station code",
        "Niepoprawny kod stacji",
    ),
    "unknown_parameter": Text(
        "Unknown parameter",
        "Nieznany parametr",
    ),
    "unknown_content_field": Text(
        "Unknown content of the field {field}: {content}",
        "Nieznana treść pola {field}: {content}",
    ),
    "invalid_record_row_2": Text(
        "An invalid record {filename}, row {number}: {exc}",
        "Błędny rekord {filename}, wiersz {number}: {exc}",
    ),
    "conflicting_values": Text(
        "Conflicting values of {column} in {archive_name}/{member}",
        "Sprzeczne wartości {column} w {archive_name}/{member}",
    ),
    "conflicting_values_station": Text(
        "Conflicting values of {column} of the station {station_code} ({period} "
        "{hydro_year}) in {archive_name}/{member}",
        "Sprzeczne wartości {column} stacji {station_code} ({period} {hydro_year}) w "
        "{archive_name}/{member}",
    ),
    "csv_content": Text(
        "the CSV content",
        "treści CSV",
    ),
}
