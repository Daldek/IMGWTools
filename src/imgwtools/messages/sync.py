"""Messages of ``store/sync.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "parameter_datasets_must_list_dataset": Text(
        "The parameter datasets must be a list of dataset keys",
        "Parametr datasets musi być listą kluczy zbiorów",
    ),
    "choose_least_one_dataset": Text(
        "Choose at least one dataset",
        "Wybierz co najmniej jeden zbiór",
    ),
    "imgw_pib_archives_cover_whole": Text(
        "The IMGW-PIB archives cover the whole country; the option stations applies "
        "only to ČHMÚ station datasets",
        "Archiwa IMGW-PIB obejmują cały kraj; opcja stations dotyczy wyłącznie "
        "zbiorów stacji ČHMÚ",
    ),
    "imgw_pib_datasets_need_option": Text(
        "The IMGW-PIB datasets need the option years",
        "Zbiory IMGW-PIB wymagają opcji years",
    ),
    "datasets_need_option_stations_station": Text(
        "The datasets {keys} need the option stations: station codes (the source "
        "files cover single stations)",
        "Zbiory {keys} wymagają opcji stations: kodów stacji (pliki źródła obejmują "
        "pojedyncze stacje)",
    ),
    "option_months_does_not_apply": Text(
        "The option months does not apply to the datasets {keys}: the station files "
        "are not monthly",
        "Opcja months nie dotyczy zbiorów {keys}: pliki stacji nie są miesięczne",
    ),
    "one_call_covers_datasets_one": Text(
        "One call covers datasets of one kind: national IMGW-PIB archives (without "
        "the option stations) or ČHMÚ station files (with the option stations); "
        "given {names}",
        "Jedno wywołanie obejmuje zbiory jednego rodzaju: archiwa krajowe IMGW-PIB "
        "(bez opcji stations) albo pliki stacji ČHMÚ (z opcją stations); podano "
        "{names}",
    ),
    "plan_must_written_outside_store": Text(
        "The plan must be written outside the store: {target}",
        "Plan musi być zapisany poza magazynem: {target}",
    ),
    "directory_plan_file_does_not": Text(
        "The directory of the plan file does not exist: {parent}",
        "Katalog pliku planu nie istnieje: {parent}",
    ),
    "give_plan_selectors_datasets_years": Text(
        "Give a plan or the selectors datasets/years/months/stations, not both",
        "Podaj plan albo selektory datasets/years/months/stations, nie oba naraz",
    ),
    "without_plan_parameter_datasets_required": Text(
        "Without a plan the parameter datasets is required",
        "Bez planu wymagany jest parametr datasets",
    ),
    "plan_concerns_another_store": Text(
        "The plan concerns another store: {root}",
        "Plan dotyczy innego magazynu: {root}",
    ),
    "no_comparable_header": Text(
        "no comparable ETag/Last-Modified header",
        "brak porównywalnego nagłówka ETag/Last-Modified",
    ),
    "no_comparable_signal": Text(
        "no comparable signal",
        "brak porównywalnego sygnału",
    ),
    "station_no_files": Text(
        "station {code}: no files of the dataset {key} at the source",
        "stacja {code}: brak plików zbioru {key} u źródła",
    ),
    "listing_without_dataset_files": Text(
        "Unreadable listing {base_url}{directory}/: no files of the dataset {key}",
        "Nieczytelny listing {base_url}{directory}/: brak plików zbioru {key}",
    ),
    "station_error": Text(
        "station {code}: {error}",
        "stacja {code}: {error}",
    ),
    "series_skipped": Text(
        "Skipped building the series {dataset}: incomplete inputs {blocking}",
        "Pominięto budowę szeregu {dataset}: niekompletne wejścia {blocking}",
    ),
    "skipped_sync_from_plan": Text(
        "{server_path}: {error}; skipped while syncing from the plan",
        "{server_path}: {error}; pominięto przy synchronizacji z planu",
    ),
    "download_and_compare": Text(
        "{server_path}: {error}; the file is downloaded and its SHA-256 compared",
        "{server_path}: {error}; pobieranie i porównanie sumy SHA-256",
    ),
    "stale_plan": Text(
        "{server_path}: the server headers changed since the plan was checked",
        "{server_path}: nagłówki serwera zmieniły się od sprawdzenia planu",
    ),
    "timeout_waiting_for_server": Text(
        "Timed out waiting for the {source} server: {reason}",
        "Przekroczono czas odpowiedzi serwera {source}: {reason}",
    ),
    "http_error": Text(
        "HTTP error {status}: {url}",
        "Błąd HTTP {status}: {url}",
    ),
    "connection_error": Text(
        "Connection error to {source}: {reason}",
        "Błąd połączenia z {source}: {reason}",
    ),
    "plain_needs_years": Text(
        "The datasets {keys} need the option years in plain mode: the store reads "
        "the years from the server listing, a plain write does not",
        "Zbiory {keys} wymagają w trybie plain opcji years: magazyn czyta lata z "
        "listingu serwera, zwykły zapis go nie używa",
    ),
    "store_only_option": Text(
        "The option {name} acts on versions of a store: it is valid only with "
        "root, not with output_dir",
        "Opcja {name} działa na wersjach magazynu: jest ważna tylko z root, nie z "
        "output_dir",
    ),
}
