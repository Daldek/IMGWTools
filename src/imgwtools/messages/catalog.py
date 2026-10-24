"""Messages of ``store/catalog.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "version_directory_collision": Text(
        "A version directory collision: {target}",
        "Kolizja katalogu wersji: {target}",
    ),
    "empty_outline_polygon_has_no": Text(
        "An empty outline: the polygon has no edges",
        "Pusty obrys: wielokąt nie ma krawędzi",
    ),
    "timeout_waiting": Text(
        "Timeout waiting for {url}",
        "Przekroczono czas oczekiwania na {url}",
    ),
    "http_error": Text(
        "HTTP error {status_code} for {url}",
        "Błąd HTTP {status_code} dla {url}",
    ),
    "connection_error": Text(
        "Connection error to {url}: {exc}",
        "Błąd połączenia z {url}: {exc}",
    ),
    "invalid_content_length_header": Text(
        "Invalid Content-Length header: {value}",
        "Niepoprawny nagłówek Content-Length: {value}",
    ),
    "corrupt_archive_version": Text(
        "A corrupt archive version: {parent}",
        "Uszkodzona wersja archiwum: {parent}",
    ),
    "no_stored_version_listing": Text(
        "No stored version of the listing {server_path}",
        "Brak zapisanej wersji listy {server_path}",
    ),
    "invalid_json_response_from": Text(
        "Invalid JSON response from {url}",
        "Niepoprawna odpowiedź JSON z {url}",
    ),
    "unexpected_format_response_from": Text(
        "Unexpected format of the response from {url}",
        "Nieoczekiwany format odpowiedzi z {url}",
    ),
    "user_location_file_must_have": Text(
        "The user location file must have the columns "
        "station_code,latitude,longitude[,source]; found {found}",
        "Plik położeń użytkownika musi mieć kolumny "
        "station_code,latitude,longitude[,source]; znaleziono {found}",
    ),
    "local_location_file_has_unsupported": Text(
        "The local location file {static_locations} has an unsupported header "
        "{found}; the columns station_code,latitude,longitude are required — "
        "generate the file again with python -m imgwtools.reference_data",
        "Lokalny plik położeń {static_locations} ma nieobsługiwany nagłówek {found}; "
        "wymagane kolumny station_code,latitude,longitude — wygeneruj plik ponownie "
        "poleceniem python -m imgwtools.reference_data",
    ),
    "field_stations_not_object": Text(
        "the field stations is not an object",
        "pole stations nie jest obiektem",
    ),
    "unreadable_series_index": Text(
        "Unreadable series index {relative}: {exc}",
        "Nieczytelny indeks szeregu {relative}: {exc}",
    ),
    "station_codes_appear_both_hydro": Text(
        "The station codes appear in both the hydro and the meteo family: {shared}",
        "Kody stacji występują jednocześnie w rodzinie hydro i meteo: {shared}",
    ),
    "number_out_range": Text(
        "the number {value} is out of range",
        "liczba {value} poza zakresem",
    ),
    "invalid_json_document": Text(
        "Invalid JSON document {url}: {exc}",
        "Niepoprawny dokument JSON {url}: {exc}",
    ),
    "unreadable_listing_no_file_meta1": Text(
        "Unreadable listing {listing}: no file meta1-<YYYYMMDD>.json",
        "Nieczytelny listing {listing}: brak pliku meta1-<RRRRMMDD>.json",
    ),
    "unknown_unit": Text(
        "unknown unit {unit!r}",
        "nieznana jednostka {unit!r}",
    ),
    "cannot_read_user_location_file": Text(
        "Cannot read the user location file: {path}",
        "Nie można odczytać pliku położeń użytkownika: {path}",
    ),
    "cannot_read_local_location_file": Text(
        "Cannot read the local location file: {path}",
        "Nie można odczytać lokalnego pliku położeń: {path}",
    ),
    "sha_256_does_not_match": Text(
        "the SHA-256 does not match the sidecar",
        "SHA-256 niezgodne z sidecarem",
    ),
    "corrupt_version_station_catalog": Text(
        "A corrupt version of the station catalog {path}: {exc}",
        "Uszkodzona wersja katalogu stacji {path}: {exc}",
    ),
    "dataset_has_no_content_form": Text(
        "The dataset {dataset} has no content form",
        "Zbiór {dataset} nie ma formy treści",
    ),
}
