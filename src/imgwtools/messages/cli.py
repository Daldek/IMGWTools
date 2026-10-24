"""
Messages of ``cli/_dispatch.py``, ``cli/admin.py``, ``cli/config_cmd.py`` and ``cli/main.py``.

The help, the progress and notice lines, the tables and the prompts of the CLI follow
``IMGW_LANG`` (``pl`` by default); the JSON error line on the last line of stderr is
always English (AGI-9.2).
"""

from imgwtools.messages import Text

MESSAGES = {
    # Help elements of Typer and Click.
    "help_required_panel": Text("Required options", "Opcje wymagane"),
    "help_optional_panel": Text("Options", "Opcje"),
    "help_commands_panel": Text("Commands", "Komendy"),
    "help_arguments_panel": Text("Arguments", "Argumenty"),
    "help_help_option": Text("Show this message and exit.", "Pokaż pomoc i zakończ."),
    "help_usage": Text("Usage: ", "Użycie: "),
    "help_envvar": Text("[env var: {{}}]", "[zmienna środowiskowa: {{}}]"),
    "help_default": Text("[default: {{}}]", "[domyślnie: {{}}]"),
    "help_required": Text("[required]", "[wymagane]"),
    "help_options_metavar": Text("[OPTIONS]", "[OPCJE]"),
    "help_commands_metavar": Text("COMMAND [ARGS]...", "KOMENDA [ARGUMENTY]..."),
    "help_aborted": Text("Aborted.", "Przerwano."),
    "help_check": Text(
        "Check only: print the imgw-plan/1 plan without writing or downloading data",
        "Tylko sprawdź: wypisz plan imgw-plan/1 bez zapisu i bez pobierania danych",
    ),
    "help_schema": Text(
        "Print the JSON Schema of the options of this command (like imgw commands "
        "schema --command) without running it",
        "Wypisz schemat JSON opcji tej komendy (jak imgw commands schema --command) "
        "bez jej wykonania",
    ),
    "metavar_text": Text("TEXT", "TEKST"),
    "metavar_number": Text("NUMBER", "LICZBA"),
    "metavar_date": Text("YYYY-MM-DD", "RRRR-MM-DD"),
    "metavar_path": Text("PATH", "ŚCIEŻKA"),
    "metavar_value": Text("VALUE", "WARTOŚĆ"),
    "metavar_list": Text("LIST", "LISTA"),
    "metavar_address": Text("ADDRESS", "ADRES"),
    # Labels of the notices printed to stderr.
    "level_info": Text("Info", "Informacja"),
    "level_warning": Text("Warning", "Ostrzeżenie"),
    "level_error": Text("Error", "Błąd"),
    # Errors of the command line.
    "unknown_option": Text(
        "Unknown option {option} of the command {path}",
        "Nieznana opcja {option} komendy {path}",
    ),
    "unknown_option_similar": Text(
        "Unknown option {option} of the command {path}; similar: {similar}",
        "Nieznana opcja {option} komendy {path}; podobne: {similar}",
    ),
    "bad_option_usage": Text(
        "Invalid use of the option {option} of the command {path}: a value is "
        "missing or a switch has a value",
        "Nieprawidłowe użycie opcji {option} komendy {path}: brak wartości albo "
        "wartość przy przełączniku",
    ),
    "missing_option": Text(
        "Missing required option {flags} of the command {path}",
        "Brak wymaganej opcji {flags} komendy {path}",
    ),
    "invalid_option_value": Text(
        "Invalid value of the option {flags} of the command {path}",
        "Nieprawidłowa wartość opcji {flags} komendy {path}",
    ),
    "unknown_command": Text(
        "Missing or unknown command after {path}; available: {names}",
        "Brak albo nieznana komenda po {path}; dostępne: {names}",
    ),
    "invalid_call": Text(
        "Invalid call of {path}: the command takes only options in the form "
        "--name value",
        "Nieprawidłowe wywołanie {path}: komenda przyjmuje wyłącznie opcje "
        "--nazwa wartość",
    ),
    "usage_help": Text(
        "{detail} (help: {path} --help)",
        "{detail} (pomoc: {path} --help)",
    ),
    "invalid_language_variable": Text(
        "Invalid value {value!r} of the environment variable {variable}; allowed: "
        "{allowed}",
        "Nieprawidłowa wartość {value!r} zmiennej środowiskowej {variable}; "
        "dozwolone: {allowed}",
    ),
    "stopped_at_once": Text(
        "The operation was stopped at once (Ctrl+C again)",
        "Operację przerwano natychmiast (ponowne Ctrl+C)",
    ),
    "internal_error": Text(
        "Internal program error ({kind}): {error}",
        "Błąd wewnętrzny programu ({kind}): {error}",
    ),
    "interrupt_requested": Text(
        "Interrupted (Ctrl+C): finishing the current step and returning a partial "
        "result; Ctrl+C again stops at once",
        "Przerwanie (Ctrl+C): kończę bieżący krok i zwracam wynik częściowy; "
        "ponowne Ctrl+C przerywa natychmiast",
    ),
    "mcp_needs_extra": Text(
        "The MCP server needs the extra: pip install imgwtools[mcp]",
        "Serwer MCP wymaga dodatku: pip install imgwtools[mcp]",
    ),
    # Help of the commands outside the catalog.
    "app_help": Text(
        "Tool for downloading the public data of IMGW-PIB and ČHMÚ. The result of a "
        "catalog command is the JSON envelope imgw-result/1 on the standard output; "
        "an error is JSON on the last line of the standard error.",
        "Narzędzie do pobierania danych publicznych IMGW-PIB i ČHMÚ. Wynik komend "
        "katalogu to koperta JSON imgw-result/1 na standardowym wyjściu; błąd to "
        "JSON w ostatniej linii standardowego wyjścia błędów.",
    ),
    "version_help": Text(
        "Print the version of the program.", "Wyświetl wersję programu."
    ),
    "server_help": Text(
        "Start the API server: REST, the web GUI and /mcp (with "
        "IMGW_MCP_ENABLED=true).",
        "Uruchom serwer API: REST, web GUI i /mcp (przy IMGW_MCP_ENABLED=true).",
    ),
    "server_host_help": Text(
        "Listening address (IMGW_HOST)", "Adres nasłuchu (IMGW_HOST)"
    ),
    "server_port_help": Text("Listening port (IMGW_PORT)", "Port nasłuchu (IMGW_PORT)"),
    "server_reload_help": Text(
        "Reload the server when the code changes (development mode)",
        "Przeładuj serwer po zmianie kodu (tryb deweloperski)",
    ),
    "server_starting": Text(
        "Starting the server on {host}:{port}", "Uruchamiam serwer na {host}:{port}"
    ),
    "mcp_help": Text(
        "Run the MCP server for AI agents on the standard input and output.\n\n"
        "The tools of the server are the catalog commands. Without --allow-writes "
        "the server does not write: the writing commands return an imgw-plan/1 plan.",
        "Uruchom serwer MCP dla agentów AI na standardowym wejściu i wyjściu.\n\n"
        "Narzędzia serwera to komendy katalogu. Bez --allow-writes serwer nie "
        "zapisuje: komendy zapisujące zwracają plan imgw-plan/1.",
    ),
    "mcp_allow_writes_help": Text(
        "Allow writes (IMGW_MCP_ALLOW_WRITES): the writing commands return a plan "
        "(check=true) by default and write with check=false",
        "Zezwól na zapis (IMGW_MCP_ALLOW_WRITES): komendy zapisujące domyślnie "
        "zwracają plan (check=true), a zapisują przy check=false",
    ),
    # imgw admin
    "admin_help": Text("API key administration", "Administracja kluczy API"),
    "admin_group_help": Text("Administration (API keys)", "Administracja (klucze API)"),
    "admin_keys_help": Text("List the API keys.", "Lista kluczy API."),
    "admin_no_keys": Text("No API keys registered", "Brak zarejestrowanych kluczy API"),
    "admin_keys_title": Text("API keys", "Klucze API"),
    "admin_column_name": Text("Name", "Nazwa"),
    "admin_column_created": Text("Created", "Utworzono"),
    "admin_column_active": Text("Active", "Aktywny"),
    "admin_yes": Text("Yes", "Tak"),
    "admin_no": Text("No", "Nie"),
    "admin_create_help": Text(
        'Create a new API key.\n\nExample:\n    imgw admin create --name "User1" '
        "--limit 100",
        'Utwórz nowy klucz API.\n\nPrzykład:\n    imgw admin create --name "User1" '
        "--limit 100",
    ),
    "admin_name_help": Text("Name of the key", "Nazwa klucza"),
    "admin_limit_help": Text("Request limit per hour", "Limit zapytań na godzinę"),
    "admin_key_created": Text("API key created!", "Klucz API utworzony!"),
    "admin_name_line": Text("Name: {name}", "Nazwa: {name}"),
    "admin_key_line": Text("Key: {key}", "Klucz: {key}"),
    "admin_limit_line": Text("Limit: {limit} requests/h", "Limit: {limit} zapytań/h"),
    "admin_save_key": Text(
        "Save this key – it cannot be read again!",
        "Zapisz ten klucz – nie będzie można go odczytać ponownie!",
    ),
    "admin_revoke_help": Text(
        "Revoke an API key.\n\nExample:\n    imgw admin revoke abc123",
        "Unieważnij klucz API.\n\nPrzykład:\n    imgw admin revoke abc123",
    ),
    "admin_metavar_id": Text("ID", "IDENTYFIKATOR"),
    "admin_revoke_id_help": Text(
        "ID of the key to revoke (the beginning is enough)",
        "Identyfikator klucza do unieważnienia (wystarczy początek)",
    ),
    "admin_key_revoked": Text(
        "The key {name} was revoked", "Klucz {name} został unieważniony"
    ),
    "admin_key_not_found": Text(
        "Key not found: {key_id}", "Nie znaleziono klucza: {key_id}"
    ),
    "admin_delete_help": Text(
        "Delete an API key.\n\nExample:\n    imgw admin delete abc123 --force",
        "Usuń klucz API.\n\nPrzykład:\n    imgw admin delete abc123 --force",
    ),
    "admin_delete_id_help": Text(
        "ID of the key to delete (the beginning is enough)",
        "Identyfikator klucza do usunięcia (wystarczy początek)",
    ),
    "admin_force_help": Text("Delete without confirmation", "Usuń bez potwierdzenia"),
    "admin_confirm_delete": Text("Delete the key {name}?", "Usunąć klucz {name}?"),
    "admin_key_deleted": Text(
        "The key {name} was deleted", "Klucz {name} został usunięty"
    ),
    "admin_stats_help": Text(
        "Usage statistics of the API keys.\n\nExample:\n    imgw admin stats\n"
        "    imgw admin stats abc123",
        "Statystyki użycia kluczy API.\n\nPrzykład:\n    imgw admin stats\n"
        "    imgw admin stats abc123",
    ),
    "admin_stats_id_help": Text(
        "ID of the key (optional)", "Identyfikator klucza (opcjonalnie)"
    ),
    "admin_stats_title": Text("API key statistics", "Statystyki kluczy API"),
    "admin_column_requests": Text("Requests", "Zapytania"),
    "admin_active": Text("Active", "Aktywny"),
    "admin_inactive": Text("Inactive", "Nieaktywny"),
    # imgw config
    "config_help": Text(
        "User settings: nogat.toml and environment variables",
        "Ustawienia użytkownika: nogat.toml i zmienne środowiskowe",
    ),
    "config_show_help": Text(
        "Show every setting with its value and source, the credentials (present "
        "or missing) and the store root with its size.",
        "Pokaż każde ustawienie z wartością i źródłem, dane uwierzytelniające "
        "(ustawione albo brak) oraz katalog magazynu z rozmiarem.",
    ),
    "config_json_help": Text(
        "Print one imgw-config/1 JSON document (no prose)",
        "Wypisz jeden dokument JSON imgw-config/1 (bez opisów)",
    ),
    "config_default": Text("default", "domyślnie"),
    "config_file_error": Text("error", "błąd"),
    "config_file_exists": Text("exists", "istnieje"),
    "config_file_absent": Text("absent", "brak"),
    "config_file_line": Text(
        "Settings file: {path} ({state})", "Plik ustawień: {path} ({state})"
    ),
    "config_settings_title": Text("Settings:", "Ustawienia:"),
    "config_credentials_title": Text(
        "Credentials (environment only):",
        "Dane uwierzytelniające (tylko środowisko):",
    ),
    "config_credential_present": Text("present", "ustawiony"),
    "config_credential_missing": Text("missing", "brak"),
    "config_store_unset": Text("Store: not set", "Magazyn: nie ustawiono"),
    "config_store_no_directory": Text("no directory", "brak katalogu"),
    "config_store": Text(
        "Store: {root}  [{origin}]  {size}", "Magazyn: {root}  [{origin}]  {size}"
    ),
}
