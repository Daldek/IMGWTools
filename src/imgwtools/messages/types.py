"""Messages of ``store/types.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "unknown_source_path": Text(
        "Unknown source path: {server_path}",
        "Nieznana ścieżka źródłowa: {server_path}",
    ),
    "url_does_not_match_dataset": Text(
        "The URL {url} does not match the dataset registry: {url_2}",
        "Adres {url} nie odpowiada rejestrowi zbiorów: {url_2}",
    ),
    "unknown_signal_plan_item": Text(
        "Unknown signal of a plan item: {signal!r}",
        "Nieznany sygnał pozycji planu: {signal!r}",
    ),
    "requests_field_plan_must_map": Text(
        "The requests field of the plan must map names to numbers ≥ 0",
        "Pole requests planu musi mapować nazwy na liczby ≥ 0",
    ),
    "unsupported_version_plan": Text(
        "Unsupported version of the plan",
        "Nieobsługiwana wersja planu",
    ),
    "cannot_read_imgw_plan": Text(
        "Cannot read the IMGW plan: {exc}",
        "Nie można odczytać planu IMGW: {exc}",
    ),
}
