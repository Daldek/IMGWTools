"""Messages of ``api/errors.py``, ``api/main.py``, ``api/routes/commands.py``, ``api/schemas.py``."""

from obserwator.messages import Text

MESSAGES = {
    "server_sets_option_obserwator_root": Text(
        "The server sets the option {name} (OBSERWATOR_ROOT); remove it from the request",
        "Opcję {name} ustawia serwer (OBSERWATOR_ROOT); usuń ją z żądania",
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
        "Writing to the store over REST is disabled (OBSERWATOR_STORE_WRITES_ENABLED)",
        "Zapis do magazynu przez REST jest wyłączony (OBSERWATOR_STORE_WRITES_ENABLED)",
    ),
    "writing_store_needs_configured_obserwator": Text(
        "Writing to the store needs a configured OBSERWATOR_STORE_WRITE_TOKEN",
        "Zapis do magazynu wymaga skonfigurowanego OBSERWATOR_STORE_WRITE_TOKEN",
    ),
    "missing_invalid_x_api_key": Text(
        "A missing or invalid X-API-Key header",
        "Brak lub niepoprawny nagłówek X-API-Key",
    ),
    "store_not_configured_set_obserwator": Text(
        "The store is not configured: set OBSERWATOR_ROOT to the absolute path of "
        "the store on the server",
        "Magazyn nie jest skonfigurowany: ustaw OBSERWATOR_ROOT na bezwzględną "
        "ścieżkę magazynu na serwerze",
    ),
    "obserwator_root_must_absolute": Text(
        "OBSERWATOR_ROOT must be an absolute path",
        "OBSERWATOR_ROOT musi być ścieżką bezwzględną",
    ),
    "invalid_obserwator_root": Text(
        "Invalid OBSERWATOR_ROOT: {detail}",
        "Niepoprawny OBSERWATOR_ROOT: {detail}",
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
        "The server does not provide user location files: OBSERWATOR_USER_LOCATIONS_DIR "
        "must name an existing absolute directory",
        "Serwer nie udostępnia plików położeń użytkownika: OBSERWATOR_USER_LOCATIONS_DIR "
        "musi wskazywać istniejący katalog bezwzględny",
    ),
    "give_only_name_location_file": Text(
        "Give only the name of a location file from OBSERWATOR_USER_LOCATIONS_DIR: {name!r}",
        "Podaj samą nazwę pliku położeń z OBSERWATOR_USER_LOCATIONS_DIR: {name!r}",
    ),
    "location_file_must_not_link": Text(
        "A location file must not be a link: {name!r}",
        "Plik położeń nie może być dowiązaniem: {name!r}",
    ),
    "no_location_file": Text(
        "No location file: {name}",
        "Brak pliku położeń: {name}",
    ),
    "temporary_directory_server_lies_obserwator": Text(
        "The temporary directory of the server lies in the OBSERWATOR_ROOT store; "
        "change TMPDIR",
        "Katalog tymczasowy serwera leży w magazynie OBSERWATOR_ROOT; zmień TMPDIR",
    ),
    "plan_concerns_another_store_than": Text(
        'The plan concerns another store than OBSERWATOR_ROOT (root must be ".")',
        'Plan dotyczy innego magazynu niż OBSERWATOR_ROOT (root musi być ".")',
    ),
    "invalid_obserwator_plan_1_plan": Text(
        "Invalid obserwator-plan/1 plan: {detail}",
        "Niepoprawny plan obserwator-plan/1: {detail}",
    ),
    "option_limit_may_most_obserwator": Text(
        "The option limit may be at most {maximum} (OBSERWATOR_API_MAX_LIMIT): {limit}",
        "Opcja limit może wynosić co najwyżej {maximum} (OBSERWATOR_API_MAX_LIMIT): {limit}",
    ),
    "operation_was_interrupted_without_report": Text(
        "The operation was interrupted without a report; REST does not pass "
        "cancellation on",
        "Operację przerwano bez raportu; REST nie przekazuje anulowania",
    ),
    "store_unavailable": Text(
        "The store at OBSERWATOR_ROOT is unavailable: {problems}",
        "Magazyn pod OBSERWATOR_ROOT jest niedostępny: {problems}",
    ),
    "invalid_parameters_or_body": Text(
        "Invalid parameters or request body",
        "Niepoprawne parametry lub ciało żądania",
    ),
    "unexpected_server_error": Text(
        "Unexpected error of the Obserwator server; the details are in the server log",
        "Nieoczekiwany błąd serwera Obserwatora; szczegóły w dzienniku serwera",
    ),
    "unknown_route": Text("Unknown route", "Nieznana trasa"),
    "method_not_allowed": Text(
        "The method {method} is not allowed for {path}",
        "Metoda {method} jest niedozwolona dla {path}",
    ),
}
