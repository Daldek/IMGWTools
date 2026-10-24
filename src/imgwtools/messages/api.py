"""Messages of ``api/errors.py``, ``api/main.py``, ``api/routes/commands.py``, ``api/schemas.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "server_sets_option_imgw_store": Text(
        "The server sets the option {name} (IMGW_STORE_ROOT); remove it from the "
        "request",
        "Opcję {name} ustawia serwer (IMGW_STORE_ROOT); usuń ją z żądania",
    ),
    "option_command_available_only_locally": Text(
        "The option {name} of the command {name_2} is available only locally (CLI "
        "and Python), not in REST",
        "Opcja {name} komendy {name_2} jest dostępna wyłącznie lokalnie (CLI i "
        "Python), nie w REST",
    ),
    "unknown_query_parameter_options_command": Text(
        "Unknown query parameter {name!r}: the options of the command {name_2} are "
        "given in the JSON body, only check in the query",
        "Nieznany parametr zapytania {name!r}: opcje komendy {name_2} podaje się w "
        "ciele JSON, a w zapytaniu wyłącznie check",
    ),
    "unknown_parameter_command_available": Text(
        "Unknown parameter {name!r} of the command {name_2}; available: {allowed}",
        "Nieznany parametr {name!r} komendy {name_2}; dostępne: {allowed}",
    ),
    "parameter_given_more_than_once": Text(
        "The parameter {name} is given more than once",
        "Parametr {name} podano więcej niż raz",
    ),
    "parameter_check_given_once_value": Text(
        "The parameter check is given once, with the value true or false: {values}",
        "Parametr check podaje się raz, z wartością true albo false: {values}",
    ),
    "writing_store_over_rest_disabled": Text(
        "Writing to the store over REST is disabled (IMGW_STORE_WRITES_ENABLED)",
        "Zapis do magazynu przez REST jest wyłączony (IMGW_STORE_WRITES_ENABLED)",
    ),
    "writing_store_needs_configured_imgw": Text(
        "Writing to the store needs a configured IMGW_STORE_WRITE_TOKEN",
        "Zapis do magazynu wymaga skonfigurowanego IMGW_STORE_WRITE_TOKEN",
    ),
    "missing_invalid_x_api_key": Text(
        "A missing or invalid X-API-Key header",
        "Brak lub niepoprawny nagłówek X-API-Key",
    ),
    "store_not_configured_set_imgw": Text(
        "The store is not configured: set IMGW_STORE_ROOT to the absolute path of "
        "the store on the server",
        "Magazyn nie jest skonfigurowany: ustaw IMGW_STORE_ROOT na bezwzględną "
        "ścieżkę magazynu na serwerze",
    ),
    "imgw_store_root_must_absolute": Text(
        "IMGW_STORE_ROOT must be an absolute path",
        "IMGW_STORE_ROOT musi być ścieżką bezwzględną",
    ),
    "invalid_imgw_store_root": Text(
        "Invalid IMGW_STORE_ROOT: {detail}",
        "Niepoprawny IMGW_STORE_ROOT: {detail}",
    ),
    "version_must_path_relative_store": Text(
        "The version must be a path relative to the store, without '..', '\\' and "
        "empty segments: {text!r}",
        "Wersja musi być ścieżką względną do magazynu, bez '..', '\\' i pustych "
        "segmentów: {text!r}",
    ),
    "version_command_must_lie_under": Text(
        "The version of the command {name} must lie under {kind}/versions/ of the "
        "store: {text!r}",
        "Wersja komendy {name} musi leżeć pod {kind}/versions/ magazynu: {text!r}",
    ),
    "version_must_not_lead_through": Text(
        "The version must not lead through a link: {text!r}",
        "Wersja nie może prowadzić przez dowiązanie: {text!r}",
    ),
    "no_version_store": Text(
        "No version in the store: {text}",
        "Brak wersji w magazynie: {text}",
    ),
    "server_does_not_provide_user": Text(
        "The server does not provide user location files: IMGW_USER_LOCATIONS_DIR "
        "must name an existing absolute directory",
        "Serwer nie udostępnia plików położeń użytkownika: IMGW_USER_LOCATIONS_DIR "
        "musi wskazywać istniejący katalog bezwzględny",
    ),
    "give_only_name_location_file": Text(
        "Give only the name of a location file from IMGW_USER_LOCATIONS_DIR: {name!r}",
        "Podaj samą nazwę pliku położeń z IMGW_USER_LOCATIONS_DIR: {name!r}",
    ),
    "location_file_must_not_link": Text(
        "A location file must not be a link: {name!r}",
        "Plik położeń nie może być dowiązaniem: {name!r}",
    ),
    "no_location_file": Text(
        "No location file: {name}",
        "Brak pliku położeń: {name}",
    ),
    "temporary_directory_server_lies_imgw": Text(
        "The temporary directory of the server lies in the IMGW_STORE_ROOT store; "
        "change TMPDIR",
        "Katalog tymczasowy serwera leży w magazynie IMGW_STORE_ROOT; zmień TMPDIR",
    ),
    "plan_concerns_another_store_than": Text(
        'The plan concerns another store than IMGW_STORE_ROOT (root must be ".")',
        'Plan dotyczy innego magazynu niż IMGW_STORE_ROOT (root musi być ".")',
    ),
    "invalid_imgw_plan_1_plan": Text(
        "Invalid imgw-plan/1 plan: {detail}",
        "Niepoprawny plan imgw-plan/1: {detail}",
    ),
    "option_limit_may_most_imgw": Text(
        "The option limit may be at most {maximum} (IMGW_API_MAX_LIMIT): {limit}",
        "Opcja limit może wynosić co najwyżej {maximum} (IMGW_API_MAX_LIMIT): {limit}",
    ),
    "operation_was_interrupted_without_report": Text(
        "The operation was interrupted without a report; REST does not pass "
        "cancellation on",
        "Operację przerwano bez raportu; REST nie przekazuje anulowania",
    ),
    "store_unavailable": Text(
        "The store at IMGW_STORE_ROOT is unavailable: {problems}",
        "Magazyn pod IMGW_STORE_ROOT jest niedostępny: {problems}",
    ),
    "invalid_parameters_or_body": Text(
        "Invalid parameters or request body",
        "Niepoprawne parametry lub ciało żądania",
    ),
    "unexpected_server_error": Text(
        "Unexpected error of the IMGWTools server; the details are in the server log",
        "Nieoczekiwany błąd serwera IMGWTools; szczegóły w dzienniku serwera",
    ),
    "unknown_route": Text("Unknown route", "Nieznana trasa"),
    "method_not_allowed": Text(
        "The method {method} is not allowed for {path}",
        "Metoda {method} jest niedozwolona dla {path}",
    ),
}
