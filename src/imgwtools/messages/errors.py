"""Messages of the error registry and of file-system errors (``exceptions.py``)."""

from imgwtools.messages import Text

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
    "title_cancelled": Text("Operation cancelled", "Operację anulowano"),
    "title_forbidden": Text("Write not permitted", "Brak uprawnień do zapisu"),
    "title_unsupported": Text("Not supported", "Nieobsługiwane"),
    "title_method_not_allowed": Text(
        "HTTP method not allowed", "Niedozwolona metoda HTTP"
    ),
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
    # Default text of ``IMGWStoreDependencyError``.
    "store_extra": Text(
        "Install the extra: pip install imgwtools[store]",
        "Zainstaluj dodatek: pip install imgwtools[store]",
    ),
}
