"""Messages of ``commands.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "unknown_command_available": Text(
        "Unknown command {command!r}; available: {available}",
        "Nieznana komenda {command!r}; dostępne: {available}",
    ),
    "option_must_boolean_true_false": Text(
        "The option {name} must be a boolean, true or false: {value!r}",
        "Opcja {name} musi mieć wartość logiczną true albo false: {value!r}",
    ),
    "option_must_least": Text(
        "The option {name} must be at least {minimum:g}: {number}",
        "Opcja {name} musi wynosić co najmniej {minimum:g}: {number}",
    ),
    "option_must_most": Text(
        "The option {name} must be at most {maximum:g}: {number}",
        "Opcja {name} musi wynosić co najwyżej {maximum:g}: {number}",
    ),
    "option_must_integer": Text(
        "The option {name} must be an integer: {value!r}",
        "Opcja {name} musi być liczbą całkowitą: {value!r}",
    ),
    "option_must_finite_number": Text(
        "The option {name} must be a finite number: {value!r}",
        "Opcja {name} musi być skończoną liczbą: {value!r}",
    ),
    "option_needs_non_empty_text": Text(
        "The option {name} needs a non-empty text: {value!r}",
        "Opcja {name} wymaga niepustego tekstu: {value!r}",
    ),
    "option_expected": Text(
        "The option {name}: expected {expected}: {text!r}",
        "Opcja {name}: oczekiwano {expected}: {text!r}",
    ),
    "option_needs_iso_date_yyyy": Text(
        "The option {name} needs an ISO date YYYY-MM-DD: {value!r}",
        "Opcja {name} wymaga daty ISO RRRR-MM-DD: {value!r}",
    ),
    "option_needs_path": Text(
        "The option {name} needs a path: {value!r}",
        "Opcja {name} wymaga ścieżki: {value!r}",
    ),
    "invalid_value_option_allowed": Text(
        "Invalid value {text!r} of the option {name}; allowed: {choices}",
        "Nieprawidłowa wartość {text!r} opcji {name}; dozwolone: {choices}",
    ),
    "option_needs_one_values": Text(
        "The option {name} needs one of the values {choices}: {value!r}",
        "Opcja {name} wymaga jednej z wartości {choices}: {value!r}",
    ),
    "option_must_list_values": Text(
        "The option {name} must be a list of values: {value!r}",
        "Opcja {name} musi być listą wartości: {value!r}",
    ),
    "option_needs_text_values": Text(
        "The option {name} needs text values: {item!r}",
        "Opcja {name} wymaga wartości tekstowych: {item!r}",
    ),
    "option_needs_non_empty_list": Text(
        "The option {name} needs a non-empty list of values",
        "Opcja {name} wymaga niepustej listy wartości",
    ),
    "option_must_json_object": Text(
        "The option {name} must be a JSON object: {exc}",
        "Opcja {name} musi być obiektem JSON: {exc}",
    ),
    "option_must_json_object_2": Text(
        "The option {name} must be a JSON object: {value!r}",
        "Opcja {name} musi być obiektem JSON: {value!r}",
    ),
    "result_file_must_lie_outside": Text(
        "The result file must lie outside the IMGW store ({store}): {path}",
        "Plik wyniku musi leżeć poza magazynem IMGW ({store}): {path}",
    ),
    "semi_annual_series_supports_only": Text(
        "A semi-annual series supports only the hydrological year",
        "Szereg półroczny obsługuje wyłącznie rok hydrologiczny",
    ),
    "imgw_plan_1_plan_excludes": Text(
        "An imgw-plan/1 plan excludes the options datasets, years, months and stations",
        "Plan imgw-plan/1 wyklucza opcje datasets, years, months i stations",
    ),
    "station_codes_outside_grammar_dataset": Text(
        "Station codes outside the {short_name} grammar of the dataset {key}: "
        "{foreign}; expected {station_code_pattern}",
        "Kody stacji spoza gramatyki {short_name} zbioru {key}: {foreign}; "
        "oczekiwano {station_code_pattern}",
    ),
    "start_range_later_than_end": Text(
        "The start of the range {start} is later than its end {end}",
        "Początek zakresu {start} jest późniejszy niż koniec {end}",
    ),
    "selection_area_geometry_applies_only": Text(
        "Selection by area (geometry) applies only to series select tasks",
        "Wybór obszarem (geometry) dotyczy wyłącznie zadań series select",
    ),
    "options_task": Text(
        "The options of the task {command}: {detail}",
        "Opcje zadania {command}: {detail}",
    ),
    "series_select_task_project_needs": Text(
        "A series select task of a project needs the option years given explicitly",
        "Zadanie series select w projekcie wymaga jawnej opcji years",
    ),
    "options_command_must_mapping_name": Text(
        "The options of the command {name} must be a mapping of name → value",
        "Opcje komendy {name} muszą być mapowaniem nazwa → wartość",
    ),
    "unknown_option_command_available": Text(
        "Unknown option {key!r} of the command {name}; available: {known}",
        "Nieznana opcja {key!r} komendy {name}; dostępne: {known}",
    ),
    "project_task_does_not_give": Text(
        "A project task does not give root: the store comes from the store_dir of "
        "the project",
        "Zadanie projektu nie podaje root: magazyn wynika ze store_dir projektu",
    ),
    "missing_required_option_command": Text(
        "Missing the required option {name} ({flag}) of the command {name_2}",
        "Brak wymaganej opcji {name} ({flag}) komendy {name_2}",
    ),
    "option_command_also_needs": Text(
        "The option {key} of the command {name} also needs {missing}",
        "Opcja {key} komendy {name} wymaga także {missing}",
    ),
    "command_needs_exactly_one_group": Text(
        "The command {name} needs exactly one group of options: {first} or {second}",
        "Komenda {name} wymaga dokładnie jednej grupy opcji: {first} albo {second}",
    ),
    "plan_concerns_another_store": Text(
        "The plan concerns another store: {root}",
        "Plan dotyczy innego magazynu: {root}",
    ),
    "live_read": Text(
        "Live read {url} (no write; the freshness is known only after the download)",
        "Odczyt na żywo {url} (bez zapisu; aktualność znana dopiero po pobraniu)",
    ),
    "datasets_registry": Text(
        "Dataset registry (offline): {count}",
        "Rejestr zbiorów (offline): {count}",
    ),
    "providers_registry": Text(
        "Provider registry (offline): {count}",
        "Rejestr dostawców (offline): {count}",
    ),
    "archive_files": Text(
        "Archive files of the dataset {dataset} (offline, no download): {count}",
        "Pliki archiwów zbioru {dataset} (offline, bez pobierania): {count}",
    ),
    "read_station_lists": Text(
        "Read the station lists of the store {root}",
        "Odczyt list stacji z magazynu {root}",
    ),
    "not_imgw_store": Text(
        "The directory {root} is not an IMGW store",
        "Katalog {root} nie jest magazynem IMGW",
    ),
    "read_cell": Text(
        "Read the cell {cell} from {found}",
        "Odczyt komórki {cell} z {found}",
    ),
    "no_stored_cell": Text(
        "No stored PMAXTP cell {cell}",
        "Brak zapisanej komórki PMAXTP {cell}",
    ),
    "store_exists": Text(
        "The IMGW store already exists: {root}",
        "Magazyn IMGW już istnieje: {root}",
    ),
    "not_empty_store": Text(
        "The directory {root} is not an empty IMGW store",
        "Katalog {root} nie jest pustym magazynem IMGW",
    ),
    "read_only_operation": Text(
        "Read-only operation: {root}",
        "Operacja tylko do odczytu: {root}",
    ),
    "series_selection": Text(
        "{version}: stations {stations}; variables {variables}; years {years} "
        "({year_type})",
        "{version}: stacje {stations}; zmienne {variables}; lata {years} ({year_type})",
    ),
    "read_series": Text(
        "Read the series {path} (offline)",
        "Odczyt szeregu {path} (offline)",
    ),
    "manifest_exists": Text(
        "The project manifest already exists: {manifest}",
        "Manifest projektu już istnieje: {manifest}",
    ),
    "no_manifest": Text(
        "No project manifest {manifest}",
        "Brak manifestu projektu {manifest}",
    ),
    "commands_catalog_description": Text(
        "Description of the command catalog imgw-commands/1 (offline)",
        "Opis katalogu komend imgw-commands/1 (offline)",
    ),
    "pmaxtp_url": Text(
        "PMAXTP API URL (offline): {pmaxtp_url}",
        "Adres API PMAXTP (offline): {pmaxtp_url}",
    ),
    "marker_will_be_created": Text(
        "The marker {store_marker} will be created in {root}",
        "Zostanie utworzony znacznik {store_marker} w {root}",
    ),
    "manifest_will_be_created": Text(
        "The project manifest {manifest} will be created",
        "Zostanie utworzony manifest {manifest}",
    ),
    "manifest_will_be_updated": Text(
        "The project manifest {manifest} will be updated",
        "Zostanie zaktualizowany manifest {manifest}",
    ),
    "command_list_description": Text(
        "Command list imgw-command-list/1 (offline)",
        "Spis komend imgw-command-list/1 (offline)",
    ),
    "download_writes": Text(
        "Download {url} to {target}",
        "Pobranie {url} do {target}",
    ),
    "download_replaces": Text(
        "Download {url} to {target}, replacing the existing file",
        "Pobranie {url} do {target}, istniejący plik zostanie zastąpiony",
    ),
    "export_to_stdout": Text(
        "Export {what} to the standard output",
        "Eksport {what} na standardowe wyjście",
    ),
    "export_to_file": Text(
        "Export {what} to {path}",
        "Eksport {what} do {path}",
    ),
    "export_replaces": Text(
        "Export {what} to {path}, replacing the existing file",
        "Eksport {what} do {path}, istniejący plik zostanie zastąpiony",
    ),
    "export_records": Text(
        "the records of {version} ({format})",
        "rekordów {version} ({format})",
    ),
    "export_station_series": Text(
        "the series of the station {station} from {path}",
        "szeregu stacji {station} z {path}",
    ),
    "standard_output": Text(
        "the standard output",
        "standardowe wyjście",
    ),
    "target_replaced": Text(
        "{path} (an existing file is replaced)",
        "{path} (istniejący plik zostanie zastąpiony)",
    ),
    "guide_plan": Text(
        "Guide {format} ({language}) → {target}",
        "Przewodnik {format} ({language}) → {target}",
    ),
    "root_help": Text(
        "IMGW store directory (CLI: defaults to $IMGW_STORE_ROOT)",
        "Katalog magazynu IMGW (CLI: domyślnie $IMGW_STORE_ROOT)",
    ),
    "project_dir_help": Text(
        "Project directory with the imgw-project.json manifest",
        "Katalog projektu z manifestem imgw-project.json",
    ),
    "store_dir_help": Text(
        "IMGW store directory of the project; a relative path is resolved against "
        "the project directory",
        "Katalog magazynu IMGW projektu; ścieżka względna liczona wobec katalogu "
        "projektu",
    ),
    "archive_dataset_help": Text(
        "Archive dataset: key, slug or legacy alias, e.g. pl.imgw.hydro_daily, "
        "hydro/dobowe or cz.chmi.hydro_daily",
        "Zbiór archiwalny: klucz, slug albo alias legacy, np. pl.imgw.hydro_daily, "
        "hydro/dobowe albo cz.chmi.hydro_daily",
    ),
    "series_dataset_help": Text(
        "Series dataset: key, slug or legacy alias, e.g. pl.imgw.hydro_daily",
        "Zbiór szeregów: klucz, slug albo alias legacy, np. pl.imgw.hydro_daily",
    ),
    "datasets_help": Text(
        "Comma-separated store datasets: key, slug or legacy alias; datasets of one "
        "kind: pl.imgw.* or cz.chmi.*",
        "Zbiory magazynu rozdzielone przecinkami: klucz, slug albo alias legacy; "
        "zbiory jednego rodzaju: pl.imgw.* albo cz.chmi.*",
    ),
    "family_help": Text(
        "Kind: hydro or meteo; none = both families",
        "Rodzaj: hydro albo meteo; brak = obie rodziny",
    ),
    "years_help": Text(
        "Years: numbers or ranges, e.g. 2023-2025 or 2020,2022",
        "Roczniki: liczby lub zakresy, np. 2023-2025 albo 2020,2022",
    ),
    "archive_years_help": Text(
        "Years: numbers or ranges, e.g. 2023-2025 or 2020,2022; required except for "
        "cz.chmi.meteo_daily (not allowed there)",
        "Roczniki: liczby lub zakresy, np. 2023-2025 albo 2020,2022; wymagane poza "
        "cz.chmi.meteo_daily (tam niedozwolone)",
    ),
    "store_years_help": Text(
        "Years: numbers or ranges, e.g. 2023-2025 or 2020,2022; required for "
        "pl.imgw.*, optional for cz.chmi.hydro_daily (none = the published years), "
        "not allowed for cz.chmi.meteo_daily",
        "Roczniki: liczby lub zakresy, np. 2023-2025 albo 2020,2022; wymagane dla "
        "pl.imgw.*, opcjonalne dla cz.chmi.hydro_daily (brak = lata opublikowane), "
        "niedozwolone dla cz.chmi.meteo_daily",
    ),
    "months_help": Text(
        "Comma-separated months 1–12 (default: all); pl.imgw.* datasets only",
        "Miesiące 1–12 rozdzielone przecinkami (domyślnie wszystkie); tylko zbiory "
        "pl.imgw.*",
    ),
    "params_help": Text(
        "Semi-annual parameters H, Q, T (pl.imgw.hydro_semiannual only; default: all)",
        "Parametry półroczne H, Q, T (tylko pl.imgw.hydro_semiannual; domyślnie "
        "wszystkie)",
    ),
    "output_help": Text(
        "Download directory mirroring the server paths (default: ./data/downloaded)",
        "Katalog pobierania odzwierciedlający ścieżki serwera (domyślnie "
        "./data/downloaded)",
    ),
    "station_option_help": Text(
        "Station code (9 digits of IMGW-PIB or a WIGOS identifier)",
        "Kod stacji (9 cyfr IMGW-PIB albo identyfikator WIGOS)",
    ),
    "stations_help": Text(
        "Comma-separated station codes (9 digits of IMGW-PIB or WIGOS identifiers)",
        "Kody stacji (9 cyfr IMGW-PIB albo identyfikatory WIGOS) rozdzielone "
        "przecinkami",
    ),
    "archive_stations_help": Text(
        "Comma-separated ČHMÚ station codes (WIGOS identifiers, e.g. "
        "0-203-1-001000); required for cz.chmi.* datasets, not allowed for pl.imgw.*",
        "Kody stacji ČHMÚ (identyfikatory WIGOS, np. 0-203-1-001000) rozdzielone "
        "przecinkami; wymagane dla zbiorów cz.chmi.*, niedozwolone dla pl.imgw.*",
    ),
    "provider_help": Text(
        "Data provider: IMGW-PIB or CHMI (ČHMÚ); none = all providers",
        "Dostawca danych: IMGW-PIB albo CHMI (ČHMÚ); brak = wszyscy dostawcy",
    ),
    "variables_help": Text(
        "Comma-separated dataset variables, e.g. H,Q (default: all)",
        "Zmienne zbioru rozdzielone przecinkami, np. H,Q (domyślnie wszystkie)",
    ),
    "year_type_help": Text(
        "Year type: hydrological (November–October) or calendar; default from "
        "series.json",
        "Rodzaj roku: hydrological (XI–X) albo calendar; domyślnie według series.json",
    ),
    "start_help": Text(
        "First day of the record range (ISO YYYY-MM-DD, inclusive)",
        "Pierwszy dzień zakresu rekordów (ISO RRRR-MM-DD, włącznie)",
    ),
    "end_help": Text(
        "Last day of the record range (ISO YYYY-MM-DD, inclusive)",
        "Ostatni dzień zakresu rekordów (ISO RRRR-MM-DD, włącznie)",
    ),
    "latitude_help": Text(
        "WGS84 latitude of the point (49.0–55.0)",
        "Szerokość geograficzna punktu WGS84 (49,0–55,0)",
    ),
    "longitude_help": Text(
        "WGS84 longitude of the point (14.0–24.5)",
        "Długość geograficzna punktu WGS84 (14,0–24,5)",
    ),
    "method_help": Text(
        "PMAXTP method: POT or AMP",
        "Metoda PMAXTP: POT albo AMP",
    ),
    "ind_x_help": Text(
        "X index of the PMAXTP grid cell (together with --ind-y)",
        "Indeks X komórki siatki PMAXTP (razem z --ind-y)",
    ),
    "ind_y_help": Text(
        "Y index of the PMAXTP grid cell (together with --ind-x)",
        "Indeks Y komórki siatki PMAXTP (razem z --ind-x)",
    ),
    "series_version_help": Text(
        "Series version: version directory, series.json or sidecar; absolute or "
        "relative to root (instead of dataset)",
        "Wersja szeregu: katalog wersji, series.json albo sidecar; bezwzględna albo "
        "względna do root (zamiast dataset)",
    ),
    "series_root_help": Text(
        "Store directory: base of a relative version or store of the current version "
        "of the dataset (with dataset)",
        "Katalog magazynu: podstawa względnej wersji albo magazyn bieżącej wersji "
        "zbioru (z dataset)",
    ),
    "path_help": Text(
        "Result file outside the store, in an existing directory (default: standard "
        "output)",
        "Plik wyniku poza magazynem, w istniejącym katalogu (domyślnie standardowe "
        "wyjście)",
    ),
    "plan_file_help": Text(
        "File to write the imgw-plan/1 plan to, outside the store",
        "Plik planu imgw-plan/1 do zapisania poza magazynem",
    ),
    "tasks_help": Text(
        "Comma-separated names of project tasks (default: all)",
        "Nazwy zadań projektu rozdzielone przecinkami (domyślnie wszystkie)",
    ),
    "task_name_option_help": Text(
        "Task name: 1–64 characters a-z, 0-9, _ or -, starting with a letter or digit",
        "Nazwa zadania: 1–64 znaki a-z, 0-9, _ lub -, na początku litera lub cyfra",
    ),
    "language_help": Text(
        "Language of the descriptions: en (default) or pl (REST: by Accept-Language)",
        "Język opisów: en (domyślnie) albo pl (REST: według Accept-Language)",
    ),
    "limit_help": Text(
        "Page size",
        "Rozmiar strony",
    ),
    "offset_help": Text(
        "Start of the page",
        "Początek strony",
    ),
    "commands_guide_description": Text(
        "Generate the guide for AI agents: AGENTS.md or llms.txt, in Polish or "
        "English. It is rendered from the command catalog and the registries.",
        "Wygeneruj przewodnik dla agentów AI: AGENTS.md albo llms.txt, po polsku "
        "albo angielsku. Powstaje z katalogu komend i rejestrów.",
    ),
    "datasets_list_description": Text(
        "List the datasets of the registry: keys, providers, legacy aliases, "
        "variables and first year.",
        "Wypisz zbiory z rejestru: klucze, dostawców, aliasy legacy, zmienne i "
        "pierwszy rocznik.",
    ),
    "datasets_files_description": Text(
        "List the source files of a dataset for given years or stations (offline, no "
        "download).",
        "Wypisz pliki źródłowe zbioru dla wybranych roczników albo stacji (offline, "
        "bez pobierania).",
    ),
    "datasets_download_description": Text(
        "Download the source files of a dataset to a directory mirroring the "
        "provider's server paths.",
        "Pobierz pliki źródłowe zbioru do katalogu odzwierciedlającego ścieżki "
        "serwera dostawcy.",
    ),
    "datasets_providers_description": Text(
        "List the data providers: identifiers, countries, licenses, station code "
        "patterns, datasets.",
        "Wypisz dostawców danych z rejestru: identyfikatory, kraje, licencje, wzorce "
        "kodów stacji i zbiory.",
    ),
    "stations_find_description": Text(
        "Find IMGW-PIB and ČHMÚ stations by name, river or code prefix.",
        "Znajdź stacje IMGW-PIB i ČHMÚ po nazwie, rzece albo prefiksie kodu.",
    ),
    "stations_find_rule_1": Text(
        "root is required with source=store and not allowed with source=live",
        "root jest wymagany przy source=store i niedozwolony przy source=live",
    ),
    "stations_find_rule_2": Text(
        "source=store without provider skips the providers without a saved station "
        "list; with an explicit provider a missing list is a not_found error",
        "source=store bez provider pomija dostawców bez zapisanej listy stacji; przy "
        "jawnym provider brak listy to błąd not_found",
    ),
    "current_hydro_description": Text(
        "Fetch current hydrological data from the IMGW API.",
        "Pobierz bieżące dane hydrologiczne z API IMGW.",
    ),
    "current_meteo_description": Text(
        "Fetch current meteorological data from the IMGW API.",
        "Pobierz bieżące dane meteorologiczne z API IMGW.",
    ),
    "current_synop_description": Text(
        "Fetch current synoptic data from the IMGW API.",
        "Pobierz bieżące dane synoptyczne z API IMGW.",
    ),
    "current_warnings_description": Text(
        "Fetch the current IMGW hydrological and meteorological warnings.",
        "Pobierz bieżące ostrzeżenia hydrologiczne i meteorologiczne IMGW.",
    ),
    "current_hydro_states_description": Text(
        "Fetch the water states of hydrological stations with coordinates "
        "(hydro.imgw.pl map).",
        "Pobierz stany wód stacji hydrologicznych ze współrzędnymi (mapa "
        "hydro.imgw.pl).",
    ),
    "pmaxtp_fetch_description": Text(
        "Fetch the PMAXTP maximum precipitation of a point (live, without saving).",
        "Pobierz opady maksymalne PMAXTP dla punktu (na żywo, bez zapisu).",
    ),
    "pmaxtp_url_description": Text(
        "Build the PMAXTP API URL of a point (offline, without downloading).",
        "Zbuduj adres URL API PMAXTP dla punktu (offline, bez pobierania).",
    ),
    "pmaxtp_check_description": Text(
        "Check the PMAXTP cell in the store without downloading data.",
        "Sprawdź komórkę PMAXTP w magazynie bez pobierania danych.",
    ),
    "pmaxtp_sync_description": Text(
        "Download the PMAXTP cell of a point and save it as a version in the store.",
        "Pobierz komórkę PMAXTP dla punktu i zapisz ją jako wersję w magazynie.",
    ),
    "pmaxtp_read_description": Text(
        "Read a saved PMAXTP cell from the store (offline).",
        "Odczytaj zapisaną komórkę PMAXTP z magazynu (offline).",
    ),
    "store_init_description": Text(
        "Create an empty IMGW store (imgw-store.json marker) in the given directory.",
        "Utwórz pusty magazyn IMGW (znacznik imgw-store.json) we wskazanym katalogu.",
    ),
    "store_info_description": Text(
        "Show the state of an IMGW store and the supported contracts (offline, "
        "without writing).",
        "Pokaż stan magazynu IMGW i obsługiwane kontrakty (offline, bez zapisu).",
    ),
    "store_scan_description": Text(
        "List the versions and problems of an IMGW store (offline, without writing).",
        "Wypisz wersje i problemy magazynu IMGW (offline, bez zapisu).",
    ),
    "store_check_description": Text(
        "Check the freshness of the dataset archives without downloading data. "
        "Sources: listing and HEAD (IMGW-PIB), the server listing alone (ČHMÚ).",
        "Sprawdź aktualność archiwów zbiorów bez pobierania danych. Źródła: listing "
        "i HEAD (IMGW-PIB), sam listing serwera (ČHMÚ).",
    ),
    "store_check_rule_1": Text(
        "plan written only outside the store, in an existing directory",
        "plan zapisywany wyłącznie poza magazynem, w istniejącym katalogu",
    ),
    "store_sync_description": Text(
        "Download new or missing archives into the store, by plan or by datasets and "
        "stations.",
        "Pobierz nowe lub brakujące archiwa do magazynu według planu albo wyboru "
        "zbiorów i stacji.",
    ),
    "store_sync_rule_1": Text(
        "plan excludes datasets, years, months and stations",
        "plan wyklucza datasets, years, months i stations",
    ),
    "store_catalog_description": Text(
        "Build the versioned station catalog stations.geojson of one provider.",
        "Zbuduj wersjonowany katalog stacji stations.geojson jednego dostawcy.",
    ),
    "store_export_description": Text(
        "Export the records of one archive version as CSV or JSONL (offline, SHA-256 "
        "verified).",
        "Wyeksportuj rekordy jednej wersji archiwum jako CSV albo JSONL (offline, z "
        "weryfikacją SHA-256).",
    ),
    "series_build_description": Text(
        "Build the Parquet series of a dataset from the current archive versions of "
        "the store.",
        "Zbuduj szereg Parquet zbioru z bieżących wersji archiwów magazynu.",
    ),
    "series_select_description": Text(
        "Select stations, variables and years of the current series (without "
        "writing; an input of a project).",
        "Wybierz stacje, zmienne i lata z bieżącego szeregu (bez zapisu; wejście "
        "projektu).",
    ),
    "series_select_rule_1": Text(
        "stations and years only of the current series",
        "stacje i roczniki wyłącznie z bieżącego szeregu",
    ),
    "series_select_rule_2": Text(
        "stations codes in the grammar of the dataset's provider (IMGW-PIB: 9 "
        "digits, ČHMÚ: a WIGOS identifier)",
        "kody stations według gramatyki dostawcy zbioru (IMGW-PIB: 9 cyfr, ČHMÚ: "
        "identyfikator WIGOS)",
    ),
    "series_read_description": Text(
        "Read the values and flags of one station's series from the store.",
        "Odczytaj wartości i flagi szeregu jednej stacji z magazynu.",
    ),
    "series_summary_description": Text(
        "Show the coverage of stations and variables of a series from series.json "
        "(without pyarrow).",
        "Pokaż pokrycie stacji i zmiennych szeregu ze spisu series.json (bez pyarrow).",
    ),
    "series_export_description": Text(
        "Export the series of one station as CSV with the attribution of the data "
        "provider.",
        "Wyeksportuj szereg jednej stacji jako CSV z atrybucją dostawcy danych.",
    ),
    "project_init_description": Text(
        "Create the imgw-project.json manifest of a project pointing to a store.",
        "Utwórz manifest projektu imgw-project.json wskazujący magazyn.",
    ),
    "project_add_description": Text(
        "Add a task to the project manifest.",
        "Dodaj zadanie do manifestu projektu.",
    ),
    "project_add_rule_1": Text(
        "geometry only for series select tasks",
        "geometry wyłącznie dla zadań series select",
    ),
    "project_add_rule_2": Text(
        "a series select task requires an explicit years option",
        "zadanie series select wymaga jawnej opcji years",
    ),
    "project_remove_description": Text(
        "Remove a task from the project manifest.",
        "Usuń zadanie z manifestu projektu.",
    ),
    "project_set_store_description": Text(
        "Point the project to a new store directory after verifying the pinned files.",
        "Wskaż nowy katalog magazynu projektu po weryfikacji przypiętych plików.",
    ),
    "project_download_description": Text(
        "Download and pin the data of the project tasks.",
        "Pobierz i przypnij dane zadań projektu.",
    ),
    "project_check_description": Text(
        "Check the freshness of the data of the project tasks without writing to the "
        "store.",
        "Sprawdź aktualność danych zadań projektu bez zapisu do magazynu.",
    ),
    "project_status_description": Text(
        "Show the state of the pinned files of the project tasks (offline).",
        "Pokaż stan przypiętych plików zadań projektu (offline).",
    ),
    "project_verify_description": Text(
        "Verify the SHA-256 sums of the pinned files of a project (offline).",
        "Zweryfikuj sumy SHA-256 przypiętych plików projektu (offline).",
    ),
    "commands_list_description": Text(
        "List the catalog commands: tool names, effects and routes. Start here, then "
        "get the options of one command with commands schema.",
        "Wypisz komendy katalogu: nazwy narzędzi, skutki i trasy. Zacznij tutaj, a "
        "opcje jednej komendy pobierz przez commands schema.",
    ),
    "commands_schema_description": Text(
        "Show the JSON Schema of the options of a command or the whole "
        "imgw-commands/1 command catalog.",
        "Pokaż schemat JSON opcji komendy albo cały katalog komend imgw-commands/1.",
    ),
    "commands_guide_format_help": Text(
        "Guide format: agents (AGENTS.md) or llms (llms.txt)",
        "Format przewodnika: agents (AGENTS.md) albo llms (llms.txt)",
    ),
    "datasets_list_family_help": Text(
        "Dataset family: hydro or meteo; none = all",
        "Rodzina zbiorów: hydro albo meteo; brak = wszystkie",
    ),
    "datasets_list_provider_help": Text(
        "Dataset provider: IMGW-PIB or CHMI (ČHMÚ); none = all providers",
        "Dostawca zbiorów: IMGW-PIB albo CHMI (ČHMÚ); brak = wszyscy dostawcy",
    ),
    "stations_find_family_help": Text(
        "Station kind; none = both families",
        "Rodzaj stacji; brak = obie rodziny",
    ),
    "stations_find_query_help": Text(
        "Fragment of the name or river, or a code prefix",
        "Fragment nazwy lub rzeki albo prefiks kodu",
    ),
    "stations_find_source_help": Text(
        "live: the providers' station lists, live; store: station lists and catalogs "
        "saved in the store",
        "live: listy stacji dostawców na żywo; store: listy i katalogi stacji "
        "zapisane w magazynie",
    ),
    "stations_find_root_help": Text(
        "Store directory (required with source=store)",
        "Katalog magazynu (wymagany przy source=store)",
    ),
    "stations_find_provider_help": Text(
        "Station provider: IMGW-PIB or CHMI (ČHMÚ); none = all providers",
        "Dostawca stacji: IMGW-PIB albo CHMI (ČHMÚ); brak = wszyscy dostawcy",
    ),
    "current_hydro_station_option_help": Text(
        "Station code (9 digits); none = all stations",
        "Kod stacji (9 cyfr); brak = wszystkie stacje",
    ),
    "current_synop_station_option_help": Text(
        "Synoptic station code (5 digits); none = all stations",
        "Kod stacji synoptycznej (5 cyfr); brak = wszystkie stacje",
    ),
    "current_synop_station_name_help": Text(
        "Fragment of the synoptic station name (case-insensitive)",
        "Fragment nazwy stacji synoptycznej (bez wielkości liter)",
    ),
    "current_warnings_family_help": Text(
        "Warning kind: hydro or meteo; none = both",
        "Rodzaj ostrzeżeń: hydro albo meteo; brak = oba",
    ),
    "current_hydro_states_main_only_help": Text(
        "Main stations only",
        "Tylko stacje główne",
    ),
    "pmaxtp_read_ind_x_help": Text(
        "X index of the PMAXTP grid cell",
        "Indeks X komórki siatki PMAXTP",
    ),
    "pmaxtp_read_ind_y_help": Text(
        "Y index of the PMAXTP grid cell",
        "Indeks Y komórki siatki PMAXTP",
    ),
    "pmaxtp_read_version_help": Text(
        "Cell version: version directory or cell.json; absolute or relative to root "
        "(default: the current one)",
        "Wersja komórki: katalog wersji albo cell.json; bezwzględna albo względna do "
        "root (domyślnie bieżąca)",
    ),
    "store_scan_kind_help": Text(
        "Entry kind: archive, series, catalog, pmaxtp, observation or problem; none "
        "= all",
        "Rodzaj wpisów: archive, series, catalog, pmaxtp, observation albo problem; "
        "brak = wszystkie",
    ),
    "store_scan_provider_help": Text(
        "Entry provider: IMGW-PIB or CHMI (ČHMÚ); none = all providers (problems "
        "without a slot always)",
        "Dostawca wpisów: IMGW-PIB albo CHMI (ČHMÚ); brak = wszyscy dostawcy "
        "(problemy bez slotu zawsze)",
    ),
    "store_sync_plan_help": Text(
        "imgw-plan/1 plan file of the store check command (instead of datasets, "
        "years, months and stations)",
        "Plik planu imgw-plan/1 z komendy store check (zamiast datasets, years, "
        "months i stations)",
    ),
    "store_sync_series_help": Text(
        "Build the series of the datasets after the synchronization (--no-series "
        "disables it)",
        "Buduj szeregi zbiorów po synchronizacji (--no-series wyłącza)",
    ),
    "store_catalog_provider_help": Text(
        "Catalog provider: IMGW-PIB or CHMI (ČHMÚ); one catalog version of one "
        "provider per call",
        "Dostawca katalogu: IMGW-PIB albo CHMI (ČHMÚ); jedna wersja katalogu jednego "
        "dostawcy na wywołanie",
    ),
    "store_catalog_user_locations_help": Text(
        "User's UTF-8 CSV file with the columns "
        "station_code,latitude,longitude[,source]",
        "Plik CSV UTF-8 użytkownika z kolumnami "
        "station_code,latitude,longitude[,source]",
    ),
    "store_export_version_help": Text(
        "Archive version: version directory, archive file or sidecar; absolute or "
        "relative to root",
        "Wersja archiwum: katalog wersji, plik archiwum albo sidecar; bezwzględna "
        "albo względna do root",
    ),
    "store_export_root_help": Text(
        "Store directory: base of the version",
        "Katalog magazynu: podstawa wersji",
    ),
    "store_export_format_help": Text(
        "Result format: csv or jsonl",
        "Format wyniku: csv albo jsonl",
    ),
    "series_select_years_help": Text(
        "Years: numbers or ranges (default: all years of the series)",
        "Roczniki: liczby lub zakresy (domyślnie wszystkie lata szeregu)",
    ),
    "series_summary_stations_help": Text(
        "Comma-separated station codes (9 digits of IMGW-PIB or WIGOS identifiers; "
        "default: all)",
        "Kody stacji (9 cyfr IMGW-PIB albo identyfikatory WIGOS) rozdzielone "
        "przecinkami (domyślnie wszystkie)",
    ),
    "series_export_format_help": Text(
        "Export format (csv only)",
        "Format eksportu (tylko csv)",
    ),
    "project_add_command_help": Text(
        "Catalog command of the task, e.g. series select",
        "Komenda zadania z katalogu, np. series select",
    ),
    "project_add_options_help": Text(
        "Options of the task command as a JSON object (without root: the store "
        "follows from the project)",
        "Opcje komendy zadania jako obiekt JSON (bez root: magazyn wynika z projektu)",
    ),
    "project_add_geometry_help": Text(
        "GeoJSON file of the station selection area in the project directory (series "
        "select only)",
        "Plik GeoJSON obszaru wyboru stacji w katalogu projektu (tylko series select)",
    ),
    "project_remove_task_name_option_help": Text(
        "Name of the task to remove",
        "Nazwa usuwanego zadania",
    ),
    "project_set_store_store_dir_help": Text(
        "New IMGW store directory of the project",
        "Nowy katalog magazynu IMGW projektu",
    ),
    "project_download_plan_help": Text(
        "imgw-plan/1 plan file of the project check command",
        "Plik planu imgw-plan/1 z komendy project check",
    ),
    "project_download_update_help": Text(
        "Mode: pinned (restore the pinned versions) or upgrade (change the pins)",
        "Tryb: pinned (odtwórz przypięte wersje) albo upgrade (zmień piny)",
    ),
    "commands_schema_command_help": Text(
        "Name of a catalog command; none = the whole imgw-commands/1 catalog",
        "Nazwa komendy katalogu; brak = cały katalog imgw-commands/1",
    ),
    "pattern_station": Text(
        "station code of 9 digits (IMGW-PIB) or a WIGOS identifier, e.g. "
        "0-203-1-001000",
        "kod stacji z 9 cyfr (IMGW-PIB) albo identyfikator WIGOS, np. 0-203-1-001000",
    ),
    "pattern_imgw_station": Text(
        "IMGW-PIB station code of 9 digits",
        "kod stacji IMGW-PIB z 9 cyfr",
    ),
    "pattern_synop_station": Text(
        "synoptic station code of 5 digits",
        "kod stacji synoptycznej z 5 cyfr",
    ),
    "pattern_task_pattern": Text(
        "task name of 1–64 characters a-z, 0-9, _ or -, starting with a letter or a "
        "digit",
        "nazwa zadania z 1–64 znaków a-z, 0-9, _ lub -, zaczynająca się literą lub "
        "cyfrą",
    ),
    "group_datasets": Text(
        "Registry of providers and datasets: list, files and download",
        "Rejestr dostawców i zbiorów: lista, pliki i pobieranie",
    ),
    "group_stations": Text(
        "Station search",
        "Wyszukiwanie stacji",
    ),
    "group_current": Text(
        "Current data from the IMGW API",
        "Dane bieżące z API IMGW",
    ),
    "group_pmaxtp": Text(
        "PMAXTP maximum precipitation",
        "Opady maksymalne PMAXTP",
    ),
    "group_store": Text(
        "Versioned store",
        "Wersjonowany magazyn",
    ),
    "group_series": Text(
        "Station series",
        "Szeregi stacji",
    ),
    "group_project": Text(
        "imgw-project/1 projects",
        "Projekty imgw-project/1",
    ),
    "group_commands": Text(
        "Description of the command catalog",
        "Opis katalogu komend",
    ),
    "stations_rule": Text(
        "stations required for cz.chmi.* datasets and not allowed for pl.imgw.*; "
        "codes in the grammar of the dataset's provider",
        "stations wymagane dla zbiorów cz.chmi.* i niedozwolone dla pl.imgw.*; kody "
        "według gramatyki dostawcy zbioru",
    ),
    "months_rule": Text(
        "months only for pl.imgw.* datasets",
        "months wyłącznie dla zbiorów pl.imgw.*",
    ),
    "variables_rule": Text(
        "variables only from the variables of the dataset",
        "variables wyłącznie ze zmiennych zbioru",
    ),
    "start_rule": Text(
        "start not later than end",
        "start nie później niż end",
    ),
    "half_year_rule": Text(
        "a semi-annual series only with year_type=hydrological",
        "szereg półroczny wyłącznie z year_type=hydrological",
    ),
    "path_rule": Text(
        "path inside the store is not allowed",
        "path wewnątrz magazynu jest niedozwolona",
    ),
    "archive_rule_1": Text(
        "years not earlier than the first year of the dataset (first_year)",
        "roczniki nie wcześniejsze niż pierwszy rocznik zbioru (first_year)",
    ),
    "archive_rule_2": Text(
        "years required except for cz.chmi.meteo_daily, whose files cover the whole "
        "history of a station (years not allowed there)",
        "years wymagane poza cz.chmi.meteo_daily, którego pliki obejmują całą "
        "historię stacji (tam years niedozwolone)",
    ),
    "archive_rule_3": Text(
        "params only for pl.imgw.hydro_semiannual",
        "params wyłącznie dla pl.imgw.hydro_semiannual",
    ),
    "store_rule_1": Text(
        "datasets of one kind: country archives pl.imgw.* or station files cz.chmi.*",
        "zbiory jednego rodzaju: archiwa krajowe pl.imgw.* albo pliki stacji cz.chmi.*",
    ),
    "store_rule_2": Text(
        "years not earlier than the first year of each dataset",
        "roczniki nie wcześniejsze niż pierwszy rocznik każdego zbioru",
    ),
    "store_rule_3": Text(
        "years required for pl.imgw.* datasets, optional for cz.chmi.hydro_daily "
        "(none = the years published in the station listing) and not allowed for "
        "cz.chmi.meteo_daily",
        "years wymagane dla zbiorów pl.imgw.*, opcjonalne dla cz.chmi.hydro_daily "
        "(brak = lata opublikowane w listingu stacji) i niedozwolone dla "
        "cz.chmi.meteo_daily",
    ),
    "series_rule_1": Text(
        "exactly one of: version or root+dataset (the current series version of the "
        "dataset)",
        "dokładnie jedno z: version albo root+dataset (bieżąca wersja szeregu zbioru)",
    ),
    "pattern_default": Text("pattern {pattern}", "wzorzec {pattern}"),
}
