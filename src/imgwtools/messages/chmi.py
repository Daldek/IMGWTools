"""Messages of ``_parsing/chmi.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "invalid_utf_8_encoding_byte": Text(
        "Invalid UTF-8 encoding in {filename} (byte {start})",
        "Niepoprawne kodowanie UTF-8 w {filename} (bajt {start})",
    ),
    "repeated_key": Text(
        "a repeated key {key!r}",
        "powtórzony klucz {key!r}",
    ),
    "disallowed_constant": Text(
        "a disallowed constant {name}",
        "niedozwolona stała {name}",
    ),
    "invalid_json_line_column": Text(
        "Invalid JSON in {filename}: {msg} (line {lineno}, column {colno})",
        "Niepoprawny JSON w {filename}: {msg} (wiersz {lineno}, kolumna {colno})",
    ),
    "invalid_json": Text(
        "Invalid JSON in {filename}: {exc}",
        "Niepoprawny JSON w {filename}: {exc}",
    ),
    "invalid_hm_file": Text(
        "Invalid ČHMÚ file {filename}, {location}: {reason}",
        "Błędny plik ČHMÚ {filename}, {location}: {reason}",
    ),
    "invalid_record_row": Text(
        "Invalid record {filename}, row {line}: {reason}",
        "Błędny rekord {filename}, wiersz {line}: {reason}",
    ),
    "file_name_not_hm_file": Text(
        "The file name {filename!r} is not a ČHMÚ {expected} file",
        "Nazwa pliku {filename!r} nie jest plikiem ČHMÚ {expected}",
    ),
    "root_value_not_object": Text(
        "the root value is not an object",
        "wartość główna nie jest obiektem",
    ),
    "no_station_code_text": Text(
        "no station code (text)",
        "brak kodu stacji (tekst)",
    ),
    "code_does_not_match_file": Text(
        "the code {obj_id!r} does not match the file name ({code})",
        "kod {obj_id!r} niezgodny z nazwą pliku ({code})",
    ),
    "no_list_series": Text(
        "no list of series",
        "brak listy szeregów",
    ),
    "series_not_object": Text(
        "a series is not an object",
        "szereg nie jest obiektem",
    ),
    "unknown_series_allowed": Text(
        "unknown series {con!r} (allowed {hydro_codes})",
        "nieznany szereg {con!r} (dozwolone {hydro_codes})",
    ),
    "unit_series_expected": Text(
        "the unit {unit!r} of the series {con}; expected {expected}",
        "jednostka {unit!r} szeregu {con}; oczekiwano {expected}",
    ),
    "no_unit_text": Text(
        "no unit (text)",
        "brak jednostki (tekst)",
    ),
    "no_data_table": Text(
        "no data table",
        "brak tabeli danych",
    ),
    "header_expected_dt_val": Text(
        "the header {header!r}; expected 'DT,VAL'",
        "nagłówek {header!r}; oczekiwano 'DT,VAL'",
    ),
    "no_list_rows": Text(
        "no list of rows",
        "brak listy wierszy",
    ),
    "row_not_pair_dt_val": Text(
        "a row is not a pair [DT, VAL]",
        "wiersz nie jest parą [DT, VAL]",
    ),
    "time_not_iso_8601_utc": Text(
        "the time {row!r} is not an ISO 8601 UTC time with 'Z'",
        "czas {row!r} nie jest czasem ISO 8601 UTC z 'Z'",
    ),
    "date_outside_year_file": Text(
        "the date {day} is outside the year of the file {year}",
        "data {day} spoza roku pliku {year}",
    ),
    "value_not_number": Text(
        "the value {row!r} is not a number",
        "wartość {row!r} nie jest liczbą",
    ),
    "repeated_date_variable_has_different": Text(
        "the repeated date {day} of the variable {variable} has a different value",
        "powtórzona data {day} zmiennej {variable} z inną wartością",
    ),
    "quality_not_number": Text(
        "QUALITY {raw_quality!r} is not a number",
        "QUALITY {raw_quality!r} nie jest liczbą",
    ),
    "quality_not_integer": Text(
        "QUALITY {raw_quality!r} is not an integer",
        "QUALITY {raw_quality!r} nie jest liczbą całkowitą",
    ),
    "value_not_number_2": Text(
        "VALUE {raw_value!r} is not a number",
        "VALUE {raw_value!r} nie jest liczbą",
    ),
    "header_expected": Text(
        "the header {shown!r}; expected {csv_header}",
        "nagłówek {shown!r}; oczekiwano {csv_header}",
    ),
    "columns_expected_7_eighth_empty": Text(
        "{count} columns; expected 7 (the eighth is empty)",
        "{count} kolumn; oczekiwano 7 (ósma pusta)",
    ),
    "station_does_not_match_file": Text(
        "STATION {station!r} does not match the file name ({code})",
        "STATION {station!r} niezgodny z nazwą pliku ({code})",
    ),
    "element_does_not_match_file": Text(
        "ELEMENT {row_element!r} does not match the file name ({element})",
        "ELEMENT {row_element!r} niezgodny z nazwą pliku ({element})",
    ),
    "dt_not_utc_date": Text(
        "DT {moment!r} is not a UTC date",
        "DT {moment!r} nie jest datą UTC",
    ),
    "timefunc_dt_not_allowed_element": Text(
        "TIMEFUNC {row_timefunc!r} with DT {moment!r} is not allowed for the element "
        "{element}",
        "TIMEFUNC {row_timefunc!r} z DT {moment!r} niedozwolone dla elementu {element}",
    ),
    "repeated_date_has_different_value": Text(
        "the repeated date {day} has a different value",
        "powtórzona data {day} z inną wartością",
    ),
    "unreadable_csv": Text(
        "an unreadable CSV: {exc}",
        "nieczytelny CSV: {exc}",
    ),
    "not_text": Text(
        "{value!r} is not a text",
        "{value!r} nie jest tekstem",
    ),
    "not_number": Text(
        "{value!r} is not a number",
        "{value!r} nie jest liczbą",
    ),
    "not_iso_8601_utc_time": Text(
        "{value!r} is not an ISO 8601 UTC time with 'Z'",
        "{value!r} nie jest czasem ISO 8601 UTC z 'Z'",
    ),
    "header_not_list_distinct_column": Text(
        "the header {header!r} is not a list of distinct column names",
        "nagłówek {header!r} nie jest listą różnych nazw kolumn",
    ),
    "row_has_fields_header_has": Text(
        "a row has {size} fields; the header has {count} columns",
        "wiersz ma {size} pól; nagłówek ma {count} kolumn",
    ),
    "invalid_hm_metadata": Text(
        "Invalid ČHMÚ metadata {filename}, {location}: {reason}",
        "Błędne metadane ČHMÚ {filename}, {location}: {reason}",
    ),
    "empty_station_code": Text(
        "an empty station code",
        "pusty kod stacji",
    ),
    "no_start_period": Text(
        "no start of the period",
        "brak początku okresu",
    ),
    "unknown_kind_station_list_allowed": Text(
        "Unknown kind of station list: {kind!r}; allowed hydro, meteo",
        "Nieznany rodzaj listy stacji: {kind!r}; dozwolone hydro, meteo",
    ),
    "unreadable_listing_row": Text(
        "Unreadable listing {url}, row {line}: {reason}",
        "Nieczytelny listing {url}, wiersz {line}: {reason}",
    ),
    "unreadable_listing_invalid_utf_8": Text(
        "Unreadable listing {url}: invalid UTF-8 encoding (byte {start})",
        "Nieczytelny listing {url}: niepoprawne kodowanie UTF-8 (bajt {start})",
    ),
    "row_without_time_size": Text(
        "a row without a time or size",
        "wiersz bez czasu lub rozmiaru",
    ),
    "size_does_not_match_kind": Text(
        "the size {size!r} does not match the kind of entry {href!r}",
        "rozmiar {size!r} niezgodny z rodzajem wpisu {href!r}",
    ),
    "invalid_modification_time": Text(
        "an invalid modification time",
        "niepoprawny czas modyfikacji",
    ),
    "invalid_name": Text(
        "an invalid name {href!r}",
        "niepoprawna nazwa {href!r}",
    ),
    "repeated_name": Text(
        "a repeated name {name!r}",
        "powtórzona nazwa {name!r}",
    ),
    "unreadable_listing_no_file_directory": Text(
        "Unreadable listing {url}: no file and directory rows",
        "Nieczytelny listing {url}: brak wierszy plików i katalogów",
    ),
    "coordinate_out_of_range": Text(
        "the coordinate {value} is out of range",
        "współrzędna {value} poza zakresem",
    ),
    "station_metadata_label": Text(
        "station metadata ({kind})",
        "metadane stacji ({kind})",
    ),
    "missing_columns": Text(
        "missing columns {columns}",
        "brak kolumn {columns}",
    ),
}
