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
}
