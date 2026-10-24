"""Messages of ``fetch.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "invalid_zip_archive_from": Text(
        "Invalid ZIP archive from {url}",
        "Niepoprawne archiwum ZIP z adresu {url}",
    ),
    "invalid_content_length_header": Text(
        "Invalid Content-Length header: {length}",
        "Niepoprawny nagłówek Content-Length: {length}",
    ),
    "invalid_json_response_from": Text(
        "Invalid JSON response from {url}",
        "Niepoprawna odpowiedź JSON z {url}",
    ),
    "timeout_waiting_server": Text(
        "Timeout waiting for the {source} server: {url}",
        "Przekroczono czas oczekiwania na serwer {source}: {url}",
    ),
    "server_returned_http": Text(
        "The {source} server returned HTTP {status}: {url}",
        "Serwer {source} zwrócił HTTP {status}: {url}",
    ),
    "connection_error_server": Text(
        "Connection error to the {source} server ({exc}): {url}",
        "Błąd połączenia z serwerem {source} ({exc}): {url}",
    ),
    "unexpected_response_from_list_objects": Text(
        "Unexpected response from {url}: a list of objects was expected",
        "Nieoczekiwana odpowiedź z {url}: oczekiwano listy obiektów",
    ),
    "invalid_record_response_from": Text(
        "Invalid record in the response from {url}: {exc}",
        "Niepoprawny rekord w odpowiedzi z {url}: {exc}",
    ),
    "latitude": Text(
        "Latitude",
        "Szerokość",
    ),
    "longitude": Text(
        "Longitude",
        "Długość",
    ),
    "outside_poland": Text(
        "{name} {value!r} is outside Poland ({low}–{high})",
        "{name} geograficzna {value!r} poza zakresem Polski ({low}–{high})",
    ),
    "point_lies_outside_pmaxtp_grid": Text(
        "The point {latitude}, {longitude} lies outside the PMAXTP grid of IMGW-PIB "
        "(no data for this place); API response: {error}",
        "Punkt {latitude}, {longitude} leży poza siatką PMAXTP IMGW-PIB (brak danych "
        "dla tego miejsca); odpowiedź API: {error}",
    ),
    "pmaxtp_api_returned_error": Text(
        "The PMAXTP API returned an error: {error}",
        "API PMAXTP zwróciło błąd: {error}",
    ),
    "invalid_pmaxtp_response": Text(
        "Invalid PMAXTP response: {exc}",
        "Niepoprawna odpowiedź PMAXTP: {exc}",
    ),
    "pmaxtp_response_has_no_data": Text(
        "The PMAXTP response has no data (an empty table ks)",
        "Odpowiedź PMAXTP bez danych (pusta tabela ks)",
    ),
    "unknown_kind_warnings_allowed_hydro": Text(
        "Unknown kind of warnings: {kind!r}; allowed hydro, meteo",
        "Nieznany rodzaj ostrzeżeń: {kind!r}; dozwolone hydro, meteo",
    ),
    "archive_needs_parameter_t_q": Text(
        "The archive {dataset} needs the parameter T, Q or H",
        "Archiwum {dataset} wymaga parametru T, Q albo H",
    ),
    "archive_published_monthly_files_give": Text(
        "The archive {dataset} {year} is published in monthly files; give a month "
        "(1–12)",
        "Archiwum {dataset} {year} jest publikowane w plikach miesięcznych; podaj "
        "miesiąc (1–12)",
    ),
    "year_must_integer": Text(
        "The year must be an integer: {year!r}",
        "Rok musi być liczbą całkowitą: {year!r}",
    ),
    "cannot_save_archive": Text(
        "Cannot save {path}: {exc}",
        "Nie można zapisać {path}: {exc}",
    ),
}
