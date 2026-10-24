"""Messages of ``store/series.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "dataset_does_not_build_measurement": Text(
        "The dataset {dataset} does not build measurement series; allowed: {allowed}",
        "Zbiór {dataset} nie tworzy szeregów pomiarowych; dozwolone: {allowed}",
    ),
    "link_file_instead_version_directory": Text(
        "a link or a file instead of the version directory",
        "dowiązanie lub plik zamiast katalogu wersji",
    ),
    "unknown_schema_no_main_file": Text(
        "an unknown schema or no main file",
        "nieznany schemat lub brak pliku głównego",
    ),
    "no_checksum_label_version": Text(
        "no checksum or label of the version",
        "brak sumy lub etykiety wersji",
    ),
    "corrupt_archive_version": Text(
        "A corrupt archive version {version_dir}: {exc}",
        "Uszkodzona wersja archiwum {version_dir}: {exc}",
    ),
    "invalid_pair_content_sha256_content": Text(
        "an invalid pair content_sha256 and content_form",
        "niepoprawna para content_sha256 i content_form",
    ),
    "path_does_not_belong_dataset": Text(
        "the path {server_path} does not belong to the dataset {dataset}",
        "ścieżka {server_path} nie należy do zbioru {dataset}",
    ),
    "request_does_not_match_path": Text(
        "request.{key} does not match the path {server_path}",
        "request.{key} nie odpowiada ścieżce {server_path}",
    ),
    "version_belongs_another_dataset": Text(
        "The version {relative} belongs to another dataset",
        "Wersja {relative} należy do innego zbioru",
    ),
    "version_does_not_match_slot": Text(
        "The version {relative} does not match the slot {slot}",
        "Wersja {relative} nie odpowiada slotowi {slot}",
    ),
    "building_parquet_series_needs_package": Text(
        "Building Parquet series needs the package pyarrow>=15. {install}",
        "Budowa szeregów Parquet wymaga pakietu pyarrow>=15. {install}",
    ),
    "pyarrow_15_required_version_installed": Text(
        "pyarrow>=15 is required (version {version} is installed). {install}",
        "Wymagany pyarrow>=15 (zainstalowano {version}). {install}",
    ),
    "conflicting_values_station": Text(
        "Conflicting {variable} values of the station {code} on {day}",
        "Sprzeczne wartości {variable} stacji {code} z {day}",
    ),
    "conflicting_dates_extremum_station": Text(
        "Conflicting dates of the extremum of {variable} of the station {code}",
        "Sprzeczne daty ekstremum {variable} stacji {code}",
    ),
    "conflicting_number_occurrences_extremum_station": Text(
        "A conflicting number of occurrences of the extremum of {variable} of the "
        "station {code}",
        "Sprzeczna liczba wystąpień ekstremum {variable} stacji {code}",
    ),
    "invalid_station_code": Text(
        "An invalid station code: {code!r}",
        "Nieprawidłowy kod stacji: {code!r}",
    ),
    "unknown_variable_dataset": Text(
        "Unknown variable {variable} in the dataset {key}",
        "Nieznana zmienna {variable} w zbiorze {key}",
    ),
    "inconsistent_flag_variable_station": Text(
        "An inconsistent flag {flag} of the variable {variable} of the station {code}",
        "Niespójna flaga {flag} zmiennej {variable} stacji {code}",
    ),
    "disallowed_quality_source_flag_variable": Text(
        "A disallowed quality {quality!r} or source flag {source_flag!r} of the "
        "variable {variable} of the station {code} on {date}",
        "Niedozwolona jakość {quality!r} lub flaga źródła {source_flag!r} zmiennej "
        "{variable} stacji {code} z {date}",
    ),
    "record_station_file_station": Text(
        "A record of the station {station_code} in the file of the station {code}: "
        "{server_path}",
        "Rekord stacji {station_code} w pliku stacji {code}: {server_path}",
    ),
    "checksum_does_not_match_sidecar": Text(
        "The checksum does not match the sidecar: {relative}",
        "Suma kontrolna nie zgadza się z sidecarem: {relative}",
    ),
    "series_version_directory_collision": Text(
        "A series version directory collision: {parent}",
        "Kolizja katalogu wersji szeregu: {parent}",
    ),
}
