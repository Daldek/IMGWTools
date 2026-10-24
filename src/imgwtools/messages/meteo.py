"""Messages of ``_parsing/meteo.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "invalid_value_row": Text(
        "Invalid value in {filename}, row {number}: {raw}",
        "Błędna wartość w {filename}, wiersz {number}: {raw}",
    ),
    "too_few_columns_row": Text(
        "Too few columns in {filename}, row {number}",
        "Za mało kolumn w {filename}, wiersz {number}",
    ),
    "invalid_station_code": Text(
        "Invalid station code",
        "Niepoprawny kod stacji",
    ),
    "date_outside_period_archive": Text(
        "The date is outside the period of the archive",
        "Data poza okresem archiwum",
    ),
    "repeated_day_station": Text(
        "A repeated day of the station",
        "Powtórzony dzień stacji",
    ),
    "invalid_record_row": Text(
        "Invalid record in {filename}, row {number}: {exc}",
        "Błędny rekord w {filename}, wiersz {number}: {exc}",
    ),
    "no_file": Text(
        "No {kind} file in {filename}",
        "Brak pliku {kind} w {filename}",
    ),
}
