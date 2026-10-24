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
    "source_point_rejected": Text(
        "{code}: the source point {source} ({lon}, {lat}) was rejected — {verdict}",
        "{code}: odrzucono punkt źródła {source} ({lon}, {lat}) — {verdict}",
    ),
    "no_comparable_signal_download": Text(
        "{server_path}: no comparable ETag/Last-Modified signal; the file is "
        "downloaded and its SHA-256 compared",
        "{server_path}: brak porównywalnego sygnału ETag/Last-Modified; pobieranie i "
        "porównanie sumy SHA-256",
    ),
    "location_row_invalid_code": Text(
        "Row {line}: invalid station code '{code}' in the location file",
        "Wiersz {line}: niepoprawny kod stacji '{code}' w pliku położeń",
    ),
    "location_row_repeated_code": Text(
        "Row {line}: repeated station code {code} in the location file",
        "Wiersz {line}: powtórzony kod stacji {code} w pliku położeń",
    ),
    "series_index_invalid_code": Text(
        "Series index {relative}: skipped an invalid station code '{code}'",
        "Indeks szeregu {relative}: pominięto niepoprawny kod stacji '{code}'",
    ),
    "list_invalid_code": Text(
        "List {kind}: skipped an invalid station code '{code}'",
        "Lista {kind}: pominięto niepoprawny kod stacji '{code}'",
    ),
    "list_repeated_code": Text(
        "List {kind}: repeated station code {code} ({list_row_text} and "
        "{list_row_text_2}); the catalog uses the first row",
        "Lista {kind}: powtórzony kod stacji {code} ({list_row_text} oraz "
        "{list_row_text_2}); katalog używa pierwszego wiersza",
    ),
    "short_code": Text(
        "short code {short_code}",
        "kod krótki {short_code}",
    ),
    "api_invalid_code": Text(
        "API {api_kind}: skipped an invalid station code '{code}'",
        "API {api_kind}: pominięto niepoprawny kod stacji '{code}'",
    ),
    "user_locations_unknown_codes": Text(
        "User location file: {count} codes outside the lists, APIs, static file and "
        "series (e.g. {unknown}); the user file only completes locations",
        "Plik położeń użytkownika: {count} kodów spoza list, API, pliku statycznego "
        "i szeregów (np. {unknown}); plik użytkownika uzupełnia tylko położenia",
    ),
    "source_invalid_code": Text(
        "Source {source}: skipped an invalid station code '{code}'",
        "Źródło {source}: pominięto niepoprawny kod stacji '{code}'",
    ),
    "source_repeated_code": Text(
        "Source {source}: repeated station code {code}; the catalog uses the first row",
        "Źródło {source}: powtórzony kod stacji {code}; katalog używa pierwszego "
        "wiersza",
    ),
    "user_locations_unknown_codes_chmi": Text(
        "User location file: {count} codes outside the ČHMÚ metadata and series "
        "(e.g. {unknown}); the user file only completes locations",
        "Plik położeń użytkownika: {count} kodów spoza metadanych ČHMÚ i szeregów "
        "(np. {unknown}); plik użytkownika uzupełnia tylko położenia",
    ),
    "no_stable_signal_public_api": Text(
        "the public API gives no stable freshness signal",
        "publiczne API nie udostępnia stabilnego sygnału aktualności",
    ),
    "metadata_envelope_hourly": Text(
        "the metadata envelope changes every hour, even without a change of the data",
        "koperta metadanych zmienia się co godzinę, także bez zmiany danych",
    ),
    "metadata_envelope_daily": Text(
        "the metadata envelope changes every day, even without a change of the data",
        "koperta metadanych zmienia się codziennie, także bez zmiany danych",
    ),
    "metadata_new_file_daily": Text(
        "a new metadata file every day; the newest is named by the directory listing",
        "nowy plik metadanych codziennie; najnowszy wskazuje listing katalogu",
    ),
    "no_comparable_signal": Text(
        "no comparable ETag/Last-Modified signal",
        "brak porównywalnego sygnału ETag/Last-Modified",
    ),
    "check_needs_download": Text(
        "{url}: {reason}; the check needs a download",
        "{url}: {reason}; sprawdzenie wymaga pobrania",
    ),
    "cannot_check_without_download": Text(
        "Cannot check the freshness of {url} without a download",
        "Nie można sprawdzić aktualności {url} bez pobrania",
    ),
    "missing_file": Text(
        "missing file {path}",
        "brak pliku {path}",
    ),
    "location_file_detail": Text(
        "location file {source}: {detail}",
        "plik położeń {source}: {detail}",
    ),
    "codes_stations": Text(
        "{count} station codes",
        "{count} kodów stacji",
    ),
    "codes_outside_catalog": Text(
        "{count} codes outside the catalog (e.g. {absent})",
        "{count} kodów spoza katalogu (np. {absent})",
    ),
    "stations_other_meteo_kind": Text(
        "{count} stations with another meteo_kind (e.g. {changed})",
        "{count} stacji z innym meteo_kind (np. {changed})",
    ),
    "codes_stations_in_catalog": Text(
        "{count} station codes in the catalog",
        "{count} kodów stacji w katalogu",
    ),
    "series_indexes": Text(
        "series indexes: {series_detail}",
        "indeksy szeregów: {series_detail}",
    ),
    "checked_catalog_sources": Text(
        "Checked the sources of the station catalog",
        "Sprawdzono źródła katalogu stacji",
    ),
    "location_from_source": Text(
        "Location from {source}: {number} stations",
        "Położenie z {source}: {number} stacji",
    ),
    "user_file_sources": Text(
        "Sources in the user file: {labels}",
        "Źródła w pliku użytkownika: {labels}",
    ),
    "location_conflicts": Text(
        "{count} stations with valid source locations that differ by more than their "
        "uncertainty (chosen by source precedence): {conflicts}",
        "{count} stacji z poprawnymi położeniami źródeł różniącymi się bardziej niż "
        "ich niepewność (wybrano według pierwszeństwa źródeł): {conflicts}",
    ),
    "series_only_stations": Text(
        "{count} stations only from series indexes (historical, active=false): "
        "{series_only}",
        "{count} stacji wyłącznie z indeksów szeregów (historyczne, active=false): "
        "{series_only}",
    ),
    "stations_without_location": Text(
        "{without} stations without a location (geometry=null)",
        "{without} stacji bez położenia (geometry=null)",
    ),
    "catalog_unchanged": Text(
        "Station catalog unchanged",
        "Katalog stacji bez zmian",
    ),
    "catalog_published": Text(
        "Station catalog: {name}",
        "Katalog stacji: {name}",
    ),
    "list_progress": Text(
        "Station list {server_path}",
        "Lista stacji {server_path}",
    ),
    "url_downloaded": Text(
        "Downloaded {url}",
        "Pobrano {url}",
    ),
    "no_static_locations": Text(
        "No local location file {static_path}; the static source was skipped (python "
        "-m imgwtools.reference_data downloads the IMGW-PIB data)",
        "Brak lokalnego pliku położeń {static_path}; źródło static pominięte (dane "
        "IMGW-PIB pobiera python -m imgwtools.reference_data)",
    ),
    "catalog_built": Text(
        "Built the catalog of {count} stations",
        "Zbudowano katalog {count} stacji",
    ),
    "source_checked": Text(
        "Checked {server_path}",
        "Sprawdzono {server_path}",
    ),
    "station_catalog_version": Text(
        "station catalog: {version}",
        "katalog stacji: {version}",
    ),
    "no_version": Text(
        "no version",
        "brak wersji",
    ),
}
