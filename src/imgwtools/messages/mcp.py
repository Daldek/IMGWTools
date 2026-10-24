"""Messages of ``mcp/_calls.py``, ``mcp/_tools.py``, ``mcp/server.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "internal_error": Text(
        "The MCP server failed internally; details are in the server log",
        "Błąd wewnętrzny serwera MCP; szczegóły w dzienniku serwera",
    ),
    "result_exceeds_256_kib_narrow": Text(
        "The result exceeds 256 KiB; narrow the selection, read series read in pages "
        "or write a file with the option path",
        "Wynik przekracza 256 KiB; zawęź wybór, czytaj stronami series read albo "
        "zapisz plik opcją path",
    ),
    "user_enables_writes_imgw_mcp": Text(
        "the user enables writes: imgw mcp --allow-writes or "
        "IMGW_MCP_ALLOW_WRITES=true",
        "zapis włącza użytkownik: imgw mcp --allow-writes albo "
        "IMGW_MCP_ALLOW_WRITES=true",
    ),
    "command_returns_only_imgw_plan": Text(
        "the command {name} returns only an imgw-plan/1 plan (check=true)",
        "komenda {name} zwraca wyłącznie plan imgw-plan/1 (check=true)",
    ),
    "option_command_writes_file": Text(
        "the option {option} of the command {name} writes a file",
        "opcja {option} komendy {name} zapisuje plik",
    ),
    "writing_over_http_does_not": Text(
        "writing over HTTP does not exist",
        "zapis przez HTTP nie istnieje",
    ),
    "mcp_server_runs_without_writes": Text(
        "The MCP server runs without writes: {what}; {how}",
        "Serwer MCP działa bez zapisu: {what}; {how}",
    ),
    "argument_check_must_true_false": Text(
        "The argument check must be true or false: {value!r}",
        "Argument check musi mieć wartość logiczną true albo false: {value!r}",
    ),
    "option_limit_may_most_imgw": Text(
        "The option limit may be at most {maximum} (IMGW_API_MAX_LIMIT): {limit}",
        "Opcja limit może wynosić co najwyżej {maximum} (IMGW_API_MAX_LIMIT): {limit}",
    ),
    "invalid_value_option_allowed": Text(
        "Invalid value {value!r} of the option {name}; allowed: {allowed}",
        "Nieprawidłowa wartość {value!r} opcji {name}; dozwolone: {allowed}",
    ),
    "unknown_tool": Text("Unknown tool: {name}", "Nieznane narzędzie: {name}"),
}
