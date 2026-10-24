"""Messages of ``testing.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "checksum_recording_does_not_match": Text(
        "The checksum of the recording {case} does not match the fixture file",
        "Suma nagrania {case} nie zgadza się z plikiem fixtury",
    ),
    "recorded_responses_were_not_used": Text(
        "The recorded responses were not used: {left}",
        "Nie wykorzystano nagranych odpowiedzi: {left}",
    ),
    "fixture_step_ended_status_expected": Text(
        "Fixture: step {step} ended with the status {status}, expected {expected}",
        "Fixtura: krok {step} zakończył się statusem {status}, oczekiwano {expected}",
    ),
    "unknown_fixture_variant_allowed": Text(
        "Unknown fixture variant: {variant!r}; allowed: {allowed}",
        "Nieznany wariant fixtury: {variant!r}; dozwolone: {allowed}",
    ),
    "fixture_store_needs_empty_directory": Text(
        "The fixture store needs an empty directory: {path}",
        "Magazyn fixtury wymaga pustego katalogu: {path}",
    ),
    "fixture_station_catalog_has_no": Text(
        "Fixture: the station catalog has no station with geometry=null",
        "Fixtura: katalog stacji bez stacji z geometry=null",
    ),
    "no_recorded_response": Text(
        "No recorded response for {method} {url}",
        "Brak nagranej odpowiedzi dla {method} {url}",
    ),
}
