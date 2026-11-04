"""Messages of the error registry and of file-system errors (``exceptions.py``)."""

from obserwator.messages import Text

MESSAGES = {
    # Titles of the registry (``ERROR_CODES``; the title of a problem document).
    "title_validation_error": Text("Invalid input", "Nieprawidłowe dane wejściowe"),
    "title_not_found": Text("Not found", "Nie znaleziono"),
    "title_conflict": Text("State conflict", "Konflikt stanu"),
    "title_source_unavailable": Text(
        "Data source unavailable", "Źródło danych niedostępne"
    ),
    "title_missing_dependency": Text(
        "Missing optional dependency", "Brak opcjonalnej zależności"
    ),
    "title_data_error": Text("Invalid data", "Niepoprawne dane"),
    "title_store_unavailable": Text("Store unavailable", "Magazyn niedostępny"),
    "title_io_error": Text("File system error", "Błąd systemu plików"),
    "title_cancelled": Text("Cancelled", "Anulowano"),
    "title_forbidden": Text("Not allowed", "Operacja niedozwolona"),
    "title_unsupported": Text("Not supported", "Nieobsługiwane"),
    "title_method_not_allowed": Text("Method not allowed", "Niedozwolona metoda"),
    "title_internal_error": Text("Internal error", "Błąd wewnętrzny"),
    # File-system errors (``describe_os_error``).
    "file_system": Text("File system error: {reason}", "Błąd systemu plików: {reason}"),
    "file_system_path": Text(
        "File system error: {reason}: {path}", "Błąd systemu plików: {reason}: {path}"
    ),
    "os_permission_denied": Text("permission denied", "brak uprawnień"),
    "os_not_permitted": Text("operation not permitted", "operacja niedozwolona"),
    "os_no_such_file": Text(
        "no such file or directory", "nie ma takiego pliku ani katalogu"
    ),
    "os_not_a_directory": Text(
        "a path component is not a directory", "element ścieżki nie jest katalogiem"
    ),
    "os_is_a_directory": Text("the path is a directory", "ścieżka jest katalogiem"),
    "os_file_exists": Text("the file already exists", "plik już istnieje"),
    "os_no_space": Text("no space left on the device", "brak miejsca na urządzeniu"),
    "os_read_only": Text("read-only file system", "system plików tylko do odczytu"),
    # Default text of ``ObserwatorStoreDependencyError``.
    "store_extra": Text(
        "Install the extra: pip install obserwator[store]",
        "Zainstaluj dodatek: pip install obserwator[store]",
    ),
    # Hints of the error document (``hint``, ``obserwator.error_report``).
    "hint_allowed": Text(
        "Use {flag} with one of: {allowed}",
        "Użyj {flag} z jedną z wartości: {allowed}",
    ),
    "hint_allowed_many": Text(
        "Use {flag} with one of the values in details.allowed",
        "Użyj {flag} z jedną z wartości z details.allowed",
    ),
    "hint_unknown_option": Text(
        "Use the options of {command} only: obserwator commands schema --command "
        "'{command}' lists them",
        "Użyj tylko opcji komendy {command}: wypisuje je obserwator commands schema "
        "--command '{command}'",
    ),
    "hint_unknown_command": Text(
        "obserwator commands list names every command",
        "obserwator commands list wypisuje wszystkie komendy",
    ),
    "hint_exclusive_options": Text(
        "Give only one of {flags}",
        "Podaj tylko jedną z opcji {flags}",
    ),
    "hint_store_only_option": Text(
        "Drop {flag}, or write to the store with --root instead of --output-dir",
        "Pomiń {flag} albo zapisz do magazynu z --root zamiast --output-dir",
    ),
    "hint_not_in_store": Text(
        "Download the dataset as plain files with --output-dir",
        "Pobierz zbiór jako zwykłe pliki z --output-dir",
    ),
    "hint_output_exists": Text(
        "Add --force to replace the existing output, or choose another output path",
        "Dodaj --force, aby zastąpić istniejące wyjście, albo wybierz inną ścieżkę "
        "wyjścia",
    ),
    "hint_output_in_store": Text(
        "Choose an output path outside every store, or write to the store with "
        "--root instead of --output-dir",
        "Wybierz ścieżkę wyjścia poza każdym magazynem albo zapisz do magazynu z "
        "--root zamiast --output-dir",
    ),
    "hint_nested_store": Text(
        "Choose a --root that neither lies in another store nor holds one",
        "Wybierz --root, który nie leży w innym magazynie ani go nie zawiera",
    ),
    "hint_not_empty": Text(
        "Choose a new or empty directory as --root, or the root of an existing "
        "Obserwator store",
        "Wybierz jako --root nowy albo pusty katalog lub korzeń istniejącego "
        "magazynu Obserwatora",
    ),
    "hint_no_marker": Text(
        "Run obserwator store init with the same --root: it verifies the layout and "
        "writes the marker",
        "Uruchom obserwator store init z tym samym --root: sprawdzi układ i zapisze "
        "znacznik",
    ),
    "hint_missing_store": Text(
        "Create the store with obserwator store init --root {path}, or give --root of "
        "an existing store",
        "Utwórz magazyn: obserwator store init --root {path}, albo podaj --root "
        "istniejącego magazynu",
    ),
    "hint_writes_disabled": Text(
        "Call with check: true for the plan; a write needs the server started with "
        "obserwator mcp --allow-writes",
        "Wywołaj z check: true, aby dostać plan; zapis wymaga serwera uruchomionego "
        "przez obserwator mcp --allow-writes",
    ),
    "hint_allow_dir": Text(
        "Give a path inside a directory of --allow-dir; the user adds one with "
        "obserwator mcp --allow-dir DIR",
        "Podaj ścieżkę w katalogu z --allow-dir; użytkownik dodaje go przez "
        "obserwator mcp --allow-dir KATALOG",
    ),
    "hint_source_unavailable": Text(
        "Retry the same command later; details.url is the requested address",
        "Ponów tę samą komendę później; details.url to żądany adres",
    ),
    "hint_not_found": Text(
        "obserwator store scan lists the versions the store holds",
        "obserwator store scan wypisuje wersje zapisane w magazynie",
    ),
    "hint_series_build": Text(
        "Build it with obserwator series build --dataset {dataset}",
        "Zbuduj go: obserwator series build --dataset {dataset}",
    ),
    "hint_store_catalog": Text(
        "Build it with obserwator store catalog --provider {provider}",
        "Zbuduj go: obserwator store catalog --provider {provider}",
    ),
    "hint_pmaxtp_sync": Text(
        "Store the cell with obserwator pmaxtp sync --method {method} --ind-x {cell_x} "
        "--ind-y {cell_y}",
        "Zapisz komórkę: obserwator pmaxtp sync --method {method} --ind-x {cell_x} "
        "--ind-y {cell_y}",
    ),
}
