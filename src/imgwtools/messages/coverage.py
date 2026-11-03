"""Messages of ``coverage.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "station_periods_must_dict_station": Text(
        "station_periods must be a dict: station code → date ranges",
        "station_periods musi być słownikiem: kod stacji → przedziały dat",
    ),
    "invalid_periods_station_station_periods": Text(
        "Invalid periods of the station {code!r} in station_periods: pairs (start, "
        "end) of datetime.date with the start not later than the end were expected",
        "Nieprawidłowe okresy stacji {code!r} w station_periods: oczekiwano par "
        "(początek, koniec) typu datetime.date, z początkiem nie późniejszym niż "
        "koniec",
    ),
    "dataset_has_no_measurement_series": Text(
        "The dataset {dataset} has no measurement series",
        "Zbiór {dataset} nie zawiera szeregu pomiarowego",
    ),
    "dataset_has_nationwide_archives_station": Text(
        "The dataset {dataset} has nationwide archives; the station periods "
        "(station_periods) apply only to datasets with station files",
        "Zbiór {dataset} ma archiwa całego kraju; okresy stacji (station_periods) "
        "dotyczą wyłącznie zbiorów z plikami stacji",
    ),
    "record_dataset_does_not_belong": Text(
        "A record of the dataset {record_dataset} does not belong to "
        "{expected_dataset}",
        "Rekord zbioru {record_dataset} nie należy do {expected_dataset}",
    ),
    "unknown_variable_dataset": Text(
        "Unknown variable {variable} in the dataset {dataset}",
        "Nieznana zmienna {variable} w zbiorze {dataset}",
    ),
    "conflicting_values_station": Text(
        "Conflicting {variable} values of the station {station_code} on {date}",
        "Sprzeczne wartości {variable} stacji {station_code} z {date}",
    ),
}
