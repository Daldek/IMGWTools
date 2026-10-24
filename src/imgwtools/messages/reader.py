"""Messages of ``store/reader.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "store_directory_does_not_exist": Text(
        "The store directory does not exist: {path}",
        "Katalog magazynu nie istnieje: {path}",
    ),
    "no_marker_not_imgw_store": Text(
        "No marker {marker}: {path} is not an IMGW store",
        "Brak znacznika {marker}: {path} nie jest magazynem IMGW",
    ),
    "unreadable_marker": Text(
        "An unreadable marker {marker}: {exc}",
        "Nieczytelny znacznik {marker}: {exc}",
    ),
    "marker_has_no_schema_field": Text(
        "The marker {marker} has no schema field",
        "Znacznik {marker} nie ma pola schema",
    ),
    "unsupported_store_version_this_version": Text(
        "An unsupported store version {schema}; this version of imgwtools supports "
        "{store_schema}",
        "Nieobsługiwana wersja magazynu {schema}; ta wersja imgwtools obsługuje "
        "{store_schema}",
    ),
    "marker_has_no_valid_created": Text(
        "The marker {marker} has no valid created_by field",
        "Znacznik {marker} nie ma poprawnego pola created_by",
    ),
    "field_must_non_empty_text": Text(
        "the field {key} must be a non-empty text",
        "pole {key} musi być niepustym tekstem",
    ),
    "field_must_have_value": Text(
        "the field {key} must have the value {const}",
        "pole {key} musi mieć wartość {const}",
    ),
    "field_must_object": Text(
        "the field {key} must be an object",
        "pole {key} musi być obiektem",
    ),
    "fields_content_sha256_content_form": Text(
        "the fields content_sha256 and content_form appear together or not at all",
        "pola content_sha256 i content_form występują razem albo wcale",
    ),
    "field_content_sha256_must_have": Text(
        "the field content_sha256 must have 64 lowercase hex digits",
        "pole content_sha256 musi mieć 64 małe cyfry szesnastkowe",
    ),
    "sidecar_not_json_object": Text(
        "the sidecar is not a JSON object",
        "sidecar nie jest obiektem JSON",
    ),
    "missing_field_schema": Text(
        "a missing field schema",
        "brak pola schema",
    ),
    "unsupported_sidecar_schema": Text(
        "an unsupported sidecar schema {schema}",
        "nieobsługiwany schemat sidecara {schema}",
    ),
    "field_dataset_must_dataset_key": Text(
        "the field dataset must be a dataset key <country>.<provider>.<name>",
        "pole dataset musi być kluczem zbioru <kraj>.<dostawca>.<nazwa>",
    ),
    "field_country_must_country_code": Text(
        "the field country must be a country code of two capital letters",
        "pole country musi być kodem kraju z dwóch wielkich liter",
    ),
    "registry_gives_dataset_country_provider": Text(
        "the registry gives the dataset {dataset} the country {origin} and the "
        "provider {origin_2}",
        "zbiór {dataset} ma w rejestrze country {origin} i provider {origin_2}",
    ),
    "field_sha256_must_have_64": Text(
        "the field sha256 must have 64 lowercase hex digits",
        "pole sha256 musi mieć 64 małe cyfry szesnastkowe",
    ),
    "field_size_bytes_must_non": Text(
        "the field size_bytes must be a non-negative integer",
        "pole size_bytes musi być nieujemną liczbą całkowitą",
    ),
    "field_downloaded_not_iso_date": Text(
        "the field downloaded_at is not an ISO date",
        "pole downloaded_at nie jest datą ISO",
    ),
    "field_downloaded_must_have_time": Text(
        "the field downloaded_at must have a time zone",
        "pole downloaded_at musi mieć strefę czasową",
    ),
    "field_label_source_must_one": Text(
        "the field label_source must be one of {label_sources}",
        "pole label_source musi być jednym z {label_sources}",
    ),
    "symbolic_link_instead_sidecar": Text(
        "a symbolic link instead of the sidecar {name}",
        "dowiązanie symboliczne zamiast sidecara {name}",
    ),
    "missing_sidecar": Text(
        "a missing sidecar {name}",
        "brak sidecara {name}",
    ),
    "unreadable_sidecar": Text(
        "an unreadable sidecar {name}: {exc}",
        "nieczytelny sidecar {name}: {exc}",
    ),
    "corrupt_json_sidecar": Text(
        "corrupt JSON of the sidecar {name}: {exc}",
        "uszkodzony JSON sidecara {name}: {exc}",
    ),
    "no_sidecar": Text(
        "No sidecar {sidecar}",
        "Brak sidecara {sidecar}",
    ),
    "invalid_sidecar": Text(
        "An invalid sidecar {sidecar}: {exc}",
        "Nieprawidłowy sidecar {sidecar}: {exc}",
    ),
    "symbolic_link_instead_version_directory": Text(
        "a symbolic link instead of the version directory",
        "dowiązanie symboliczne zamiast katalogu wersji",
    ),
    "symbolic_link_version": Text(
        "a symbolic link in the version: {name}",
        "dowiązanie symboliczne w wersji: {name}",
    ),
    "unknown_directory_version": Text(
        "an unknown directory in the version: {name}",
        "nieznany katalog w wersji: {name}",
    ),
    "missing_sidecar_unfinished_publication_version": Text(
        "a missing sidecar {name}{sidecar} (an unfinished publication of the version)",
        "brak sidecara {name}{sidecar} (niedokończona publikacja wersji)",
    ),
    "missing_main_file": Text(
        "a missing main file {name}",
        "brak pliku głównego {name}",
    ),
    "unknown_files_version": Text(
        "unknown files in the version: {unexpected}",
        "nieznane pliki w wersji: {unexpected}",
    ),
    "name_version_directory_does_not": Text(
        "the name of the version directory does not match the label {label} and the "
        "sidecar checksum",
        "nazwa katalogu wersji nie odpowiada etykiecie {label} i sumie sidecara",
    ),
    "size_differs_from_size_bytes": Text(
        "the size of {name} differs from size_bytes in the sidecar",
        "rozmiar {name} różni się od size_bytes w sidecarze",
    ),
    "file_has_no_extra_response": Text(
        "the file {name} has no extra.response description in the sidecar",
        "plik {name} bez opisu extra.response w sidecarze",
    ),
    "field_extra_response_must_object": Text(
        "the field extra.response must be an object",
        "pole extra.response musi być obiektem",
    ),
    "field_extra_response_must_have": Text(
        "the field extra.response must have name={name}, sha256 and size_bytes",
        "pole extra.response musi mieć name={name}, sha256 i size_bytes",
    ),
    "missing_file_described_sidecar": Text(
        "a missing file {name} described in the sidecar",
        "brak pliku {name} opisanego w sidecarze",
    ),
    "size_differs_from_extra_response": Text(
        "the size of {name} differs from extra.response in the sidecar",
        "rozmiar {name} różni się od extra.response w sidecarze",
    ),
    "unknown_store_item": Text(
        "An unknown store item: {relative}",
        "Nieznany element magazynu: {relative}",
    ),
    "request_server_path_sidecar_does": Text(
        "request.server_path in the sidecar does not match the path of the version",
        "request.server_path w sidecarze nie odpowiada ścieżce wersji",
    ),
    "dataset_sidecar_does_not_match": Text(
        "the dataset {dataset} of the sidecar does not match the slot {slot}",
        "zbiór {dataset} sidecara nie odpowiada slotowi {slot}",
    ),
    "field_extra_series_schema_must": Text(
        "the field extra.series_schema must be a text",
        "pole extra.series_schema musi być tekstem",
    ),
    "unsupported_series_schema": Text(
        "an unsupported series schema {series_schema}",
        "nieobsługiwany schemat szeregu {series_schema}",
    ),
    "version": Text(
        "Version {relative}: {exc}",
        "Wersja {relative}: {exc}",
    ),
    "missing_field": Text(
        "a missing field {key}",
        "brak pola {key}",
    ),
    "field_must_non_empty_text_2": Text(
        "the field {key} must be a non-empty text or null",
        "pole {key} musi być niepustym tekstem albo null",
    ),
    "field_must_have_64_lowercase": Text(
        "the field {key} must have 64 lowercase hex digits",
        "pole {key} musi mieć 64 małe cyfry szesnastkowe",
    ),
    "observation_not_json_object": Text(
        "the observation is not a JSON object",
        "obserwacja nie jest obiektem JSON",
    ),
    "unsupported_observation_schema": Text(
        "an unsupported observation schema {schema}",
        "nieobsługiwany schemat obserwacji {schema}",
    ),
    "field_seen_must_utc_time": Text(
        "the field seen_at must be a UTC time YYYY-MM-DDTHH:MM:SSZ",
        "pole seen_at musi być czasem UTC RRRR-MM-DDTGG:MM:SSZ",
    ),
    "field_same_content_as_must": Text(
        "the field same_content_as must be the name of a version directory "
        "<label>_<sha8>",
        "pole same_content_as musi być nazwą katalogu wersji <etykieta>_<sha8>",
    ),
    "unreadable_observation": Text(
        "an unreadable observation {name}: {exc}",
        "nieczytelna obserwacja {name}: {exc}",
    ),
    "corrupt_json_observation": Text(
        "corrupt JSON of the observation {name}: {exc}",
        "uszkodzony JSON obserwacji {name}: {exc}",
    ),
    "name_does_not_match_date": Text(
        "the name {name} does not match the date seen_at {seen_at}",
        "nazwa {name} nie odpowiada dacie seen_at {seen_at}",
    ),
    "name_does_not_match_signal": Text(
        "the name {name} does not match the signal of the observation (expected "
        "{expected})",
        "nazwa {name} nie odpowiada sygnałowi obserwacji (oczekiwano {expected})",
    ),
    "field_dataset_differs_from_dataset": Text(
        "the field dataset {dataset} differs from the dataset of the slot {dataset_2}",
        "pole dataset {dataset} różni się od zbioru slotu {dataset_2}",
    ),
    "same_content_as_does_not": Text(
        "same_content_as {same_content_as} does not point to a valid version in the "
        "slot",
        "same_content_as {same_content_as} nie wskazuje poprawnej wersji w slocie",
    ),
    "content_fields_differ_from_fields": Text(
        "the content fields differ from the fields of the version {same_content_as}",
        "pola treści różnią się od pól wersji {same_content_as}",
    ),
    "symbolic_link_observation_register": Text(
        "A symbolic link in the observation register: {relative}",
        "Dowiązanie symboliczne w rejestrze obserwacji: {relative}",
    ),
    "observation": Text(
        "Observation {relative}: {exc}",
        "Obserwacja {relative}: {exc}",
    ),
    "archive_key_path_series_key": Text(
        "archive:<key>:<path>, series:<key>, catalog:<catalog key> ({values}) or "
        "pmaxtp:pl.imgw.pmaxtp:<POT|AMP>/<indX>_<indY>",
        "archive:<klucz>:<ścieżka>, series:<klucz>, catalog:<klucz katalogu> "
        "({values}) albo pmaxtp:pl.imgw.pmaxtp:<POT|AMP>/<indX>_<indY>",
    ),
    "symbolic_link_store": Text(
        "A symbolic link in the store: {relative}",
        "Dowiązanie symboliczne w magazynie: {relative}",
    ),
    "abandoned_staging_older_than_24": Text(
        "An abandoned staging older than 24 h: {relative}",
        "Porzucony staging starszy niż 24 h: {relative}",
    ),
    "unknown_kind_store_item_allowed": Text(
        "Unknown kind of store item: {kind!r}; allowed {kinds}",
        "Nieznany rodzaj wpisu magazynu: {kind!r}; dozwolone {kinds}",
    ),
    "invalid_slot_expected": Text(
        "Invalid slot {slot!r}: {reason}; expected {slot_grammar}",
        "Nieprawidłowy slot {slot!r}: {reason}; oczekiwano {slot_grammar}",
    ),
    "slot_must_text": Text(
        "the slot must be a text",
        "slot musi być tekstem",
    ),
    "not_key_archive_dataset": Text(
        "{key!r} is not a key of an archive dataset",
        "{key!r} nie jest kluczem zbioru archiwów",
    ),
    "invalid_file_path_dataset": Text(
        "an invalid file path of the dataset {key}",
        "nieprawidłowa ścieżka pliku zbioru {key}",
    ),
    "unexpected_selector": Text(
        "an unexpected selector",
        "nieoczekiwany selektor",
    ),
    "unknown_kind_key": Text(
        "an unknown kind or key",
        "nieznany rodzaj lub klucz",
    ),
    "corrupt_version_slot": Text(
        "A corrupt version in the slot {slot}: {problem}",
        "Uszkodzona wersja w slocie {slot}: {problem}",
    ),
    "reference_signal_exists_only_archive": Text(
        "the reference signal exists only for an archive slot",
        "sygnał odniesienia ma wyłącznie slot archiwum",
    ),
    "symbolic_link_instead_observation": Text(
        "a symbolic link instead of an observation",
        "dowiązanie symboliczne zamiast obserwacji",
    ),
    "corrupt_observation_slot": Text(
        "A corrupt observation in the slot {slot}: {name}: {exc}",
        "Uszkodzona obserwacja w slocie {slot}: {name}: {exc}",
    ),
    "corrupt_version_slot_extra_http": Text(
        "A corrupt version in the slot {slot}: extra.http.{key} must be a text or null",
        "Uszkodzona wersja w slocie {slot}: extra.http.{key} musi być tekstem albo "
        "null",
    ),
    "version_must_point_version_directory": Text(
        "The version must point to a version directory, the file {name} or its "
        "sidecar: {version}",
        "Wersja musi wskazywać katalog wersji, plik {name} albo jego sidecar: "
        "{version}",
    ),
    "symbolic_link_instead_version_file": Text(
        "A symbolic link instead of the version file: {path}",
        "Dowiązanie symboliczne zamiast pliku wersji: {path}",
    ),
    "no_version_file": Text(
        "No version file: {path}",
        "Brak pliku wersji: {path}",
    ),
    "checksum_does_not_match_sidecar": Text(
        "The checksum of {name} does not match the sidecar: {path}",
        "Suma kontrolna {name} nie zgadza się z sidecarem: {path}",
    ),
    "corrupt_json": Text(
        "Corrupt JSON {path}: {exc}",
        "Uszkodzony JSON {path}: {exc}",
    ),
    "coordinate_not_number": Text(
        "the coordinate is not a number",
        "współrzędna nie jest liczbą",
    ),
    "featurecollection_was_expected": Text(
        "a FeatureCollection was expected",
        "oczekiwano FeatureCollection",
    ),
    "features_must_list": Text(
        "features must be a list",
        "features musi być listą",
    ),
    "invalid_station_object": Text(
        "an invalid station object {code!r}",
        "nieprawidłowy obiekt stacji {code!r}",
    ),
    "properties_station_must_simple_values": Text(
        "the properties of the station {code} must be simple values (thresholds: an "
        "object of thresholds)",
        "właściwości stacji {code} muszą być wartościami prostymi (thresholds: "
        "obiektem progów)",
    ),
    "station_code_station_differs_from": Text(
        "station_code of the station {code} differs from the id",
        "station_code stacji {code} różni się od id",
    ),
    "geometry_station_must_point_lon": Text(
        "the geometry of the station {code} must be a point [lon, lat]",
        "geometria stacji {code} musi być punktem [lon, lat]",
    ),
    "invalid_station_catalog": Text(
        "An invalid station catalog {path}: {exc}",
        "Nieprawidłowy katalog stacji {path}: {exc}",
    ),
    "option_provider_selects_current_store": Text(
        "The option provider selects the current store catalog and needs root "
        "instead of version",
        "Opcja provider wybiera bieżący katalog magazynu i wymaga root zamiast version",
    ),
    "give_exactly_one_version_catalog": Text(
        "Give exactly one of: version (a catalog version) or root (the current "
        "station catalogs of the store)",
        "Podaj dokładnie jedno z: version (wersja katalogu) albo root (bieżące "
        "katalogi stacji magazynu)",
    ),
    "store_has_no_station_catalog": Text(
        "The store has no station catalog of {short_name} ({key}); build it with "
        "imgw store catalog --provider {id}",
        "Magazyn nie zawiera katalogu stacji {short_name} ({key}); buduje go imgw "
        "store catalog --provider {id}",
    ),
    "unknown_kind_station_list_allowed": Text(
        "Unknown kind of station list: {kind!r}; allowed hydro, meteo",
        "Nieznany rodzaj listy stacji: {kind!r}; dozwolone hydro, meteo",
    ),
    "store_has_no_station_list": Text(
        "The store has no station list {dataset}; building the station catalog "
        "writes it ({hint})",
        "Magazyn nie zawiera listy stacji {dataset}; zapisuje ją budowa katalogu "
        "stacji ({hint})",
    ),
    "version_belongs_dataset_not": Text(
        "The version {version} belongs to the dataset {dataset}, not {dataset_2}",
        "Wersja {version} należy do zbioru {dataset}, a nie {dataset_2}",
    ),
    "directory_not_archive_version_directory": Text(
        "The directory {version} is not an archive version directory (exactly one "
        "sidecar was expected)",
        "Katalog {version} nie jest katalogiem wersji archiwum (oczekiwano dokładnie "
        "jednego sidecara)",
    ),
    "not_archive_version_dataset_series": Text(
        "{main} is not an archive version (the dataset {dataset}); series are read "
        "by read_series, the catalog by read_catalog, PMAXTP cells by read_pmaxtp",
        "{main} nie jest wersją archiwum (zbiór {dataset}); szeregi czyta "
        "read_series, katalog read_catalog, komórki PMAXTP read_pmaxtp",
    ),
    "version_station_list_station_lists": Text(
        "{main} is a version of the station list {dataset}; station lists are read "
        "by read_station_list(root, kind={kind!r}{option})",
        "{main} jest wersją listy stacji {dataset}; listy stacji czyta "
        "read_station_list(root, kind={kind!r}{option})",
    ),
    "file_does_not_match_request": Text(
        "The file {name} does not match request.server_path {server_path} of the "
        "sidecar",
        "Plik {name} nie odpowiada request.server_path {server_path} sidecara",
    ),
    "path_does_not_belong_dataset": Text(
        "the path {server_path} does not belong to the dataset {key}",
        "ścieżka {server_path} nie należy do zbioru {key}",
    ),
    "request_does_not_match_path": Text(
        "request.{mismatch} does not match the path {server_path}",
        "request.{mismatch} nie odpowiada ścieżce {server_path}",
    ),
    "sidecar_does_not_describe_archive": Text(
        "The sidecar {main} does not describe an archive: {reason}",
        "Sidecar {main} nie opisuje archiwum: {reason}",
    ),
    "date_must_iso_text": Text(
        "the date must be an ISO text: {value!r}",
        "data musi być tekstem ISO: {value!r}",
    ),
    "range_must_pair_dates": Text(
        "the range must be a pair of dates",
        "przedział musi być parą dat",
    ),
    "range_reversed": Text(
        "the range {start}–{end} is reversed",
        "przedział {start}–{end} ma odwróconą kolejność",
    ),
    "must_integer": Text(
        "{name} must be an integer ≥ {minimum}",
        "{name} musi być liczbą całkowitą ≥ {minimum}",
    ),
    "unknown_period_variable": Text(
        "an unknown period of the variable {key}",
        "nieznany okres zmiennej {key}",
    ),
    "unit_variable_must_text": Text(
        "the unit of the variable {key} must be a text",
        "jednostka zmiennej {key} musi być tekstem",
    ),
    "gaps_variable_must_list": Text(
        "gaps of the variable {key} must be a list",
        "gaps zmiennej {key} musi być listą",
    ),
    "periods_station_must_list_ranges": Text(
        "periods of the station {code} must be a list of ranges",
        "periods stacji {code} musi być listą przedziałów",
    ),
    "periods_station_not_increasing_disjoint": Text(
        "periods of the station {code} are not increasing, disjoint ranges",
        "periods stacji {code} nie są rosnącymi, rozłącznymi przedziałami",
    ),
    "series_json_not_object": Text(
        "series.json is not an object",
        "series.json nie jest obiektem",
    ),
    "unsupported_schema": Text(
        "an unsupported schema {schema!r}",
        "nieobsługiwany schemat {schema!r}",
    ),
    "dataset_does_not_build_series": Text(
        "the dataset {dataset!r} does not build series",
        "zbiór {dataset!r} nie tworzy szeregów",
    ),
    "unknown_year_type": Text(
        "an unknown year_type {year_type!r}",
        "nieznany year_type {year_type!r}",
    ),
    "stations_must_object": Text(
        "stations must be an object",
        "stations musi być obiektem",
    ),
    "invalid_station_code": Text(
        "an invalid station code {code!r}",
        "nieprawidłowy kod stacji {code!r}",
    ),
    "invalid_parquet_path_station": Text(
        "an invalid Parquet path of the station {code}: {file!r}",
        "nieprawidłowa ścieżka Parquet stacji {code}: {file!r}",
    ),
    "invalid_parquet_checksum_station": Text(
        "an invalid Parquet checksum of the station {code}",
        "nieprawidłowa suma Parquet stacji {code}",
    ),
    "missing_file": Text(
        "a missing file {file}",
        "brak pliku {file}",
    ),
    "variables_station_must_object": Text(
        "variables of the station {code} must be an object",
        "variables stacji {code} musi być obiektem",
    ),
    "invalid_series_index": Text(
        "An invalid series index {path}: {exc}",
        "Nieprawidłowy spis szeregu {path}: {exc}",
    ),
    "give_series_version_version_store": Text(
        "Give a series version (version) or a store and a dataset (root and "
        "dataset), not both and not neither",
        "Wskaż wersję szeregu (version) albo magazyn i zbiór (root i dataset), nie "
        "oba naraz ani żadne",
    ),
    "dataset_dataset_selects_current_series": Text(
        "The dataset (dataset) selects the current series version only together with "
        "the store (root)",
        "Zbiór (dataset) wskazuje bieżącą wersję szeregu wyłącznie razem z magazynem "
        "(root)",
    ),
    "store_has_no_series_run": Text(
        "The store has no series {key}; run series build first",
        "Brak szeregu {key} w magazynie; najpierw uruchom series build",
    ),
    "variables_must_list_variable_names": Text(
        "variables must be a list of variable names, not a single text",
        "variables musi być listą nazw zmiennych, nie pojedynczym tekstem",
    ),
    "stations_must_list_station_codes": Text(
        "stations must be a list of station codes, not a single text",
        "stations musi być listą kodów stacji, nie pojedynczym tekstem",
    ),
    "stations_outside_series": Text(
        "Stations outside the series {dataset}: {missing}",
        "Stacje spoza szeregu {dataset}: {missing}",
    ),
    "station_not_series": Text(
        "The station {station!r} is not in the series {dataset}",
        "Stacja {station!r} nie występuje w szeregu {dataset}",
    ),
    "range_bound_must_date": Text(
        "The range bound must be a date: {bound!r}",
        "Granica zakresu musi być datą: {bound!r}",
    ),
    "start_range_later_than_end": Text(
        "The start of the range {start} is later than its end {end}",
        "Początek zakresu {start} jest późniejszy niż koniec {end}",
    ),
    "missing_parquet_file_station_from": Text(
        "A missing Parquet file of the station {station} from the index: {parquet}",
        "Brak pliku Parquet stacji {station} ze spisu: {parquet}",
    ),
    "parquet_checksum_station_does_not": Text(
        "The Parquet checksum of the station {station} does not match the index: "
        "{parquet}",
        "Suma kontrolna Parquet stacji {station} nie zgadza się ze spisem: {parquet}",
    ),
    "parquet_metadata_do_not_match": Text(
        "the Parquet metadata do not match the index",
        "metadane Parquet nie odpowiadają spisowi",
    ),
    "number_rows_differs_from_index": Text(
        "the number of rows {num_rows} differs from the index ({rows})",
        "liczba wierszy {num_rows} różni się od spisu ({rows})",
    ),
    "invalid_parquet_station": Text(
        "An invalid Parquet of the station {station} ({parquet}): {exc}",
        "Nieprawidłowy Parquet stacji {station} ({parquet}): {exc}",
    ),
    "inconsistent_flag_variable_station": Text(
        "An inconsistent flag {flag!r} of the variable {name} of the station "
        "{station} on {day}",
        "Niespójna flaga {flag!r} zmiennej {name} stacji {station} z {day}",
    ),
    "invalid_quality_source_flag_variable": Text(
        "An invalid quality or source flag of the variable {name} of the station "
        "{station} on {day}",
        "Niepoprawna jakość lub flaga źródła zmiennej {name} stacji {station} z {day}",
    ),
    "unknown_kind_year_allowed_hydrological": Text(
        "Unknown kind of year {year_type!r}; allowed hydrological, calendar",
        "Nieznany rodzaj roku {year_type!r}; dozwolone hydrological, calendar",
    ),
    "semi_annual_series_supports_only": Text(
        "A semi-annual series supports only the hydrological year",
        "Szereg półroczny obsługuje wyłącznie rok hydrologiczny",
    ),
    "years_outside_series": Text(
        "Years outside the series {key} ({kind}): {years}",
        "Lata spoza szeregu {key} ({kind}): {years}",
    ),
    "unknown_variables_available": Text(
        "Unknown variables {unknown}; available: {available}",
        "Nieznane zmienne {unknown}; dostępne: {available}",
    ),
    "invalid_station_codes_expected": Text(
        "Invalid station codes {codes}; expected at least one code of 9 digits "
        "(IMGW-PIB) or a WIGOS identifier",
        "Nieprawidłowe kody stacji {codes}; oczekiwano co najmniej jednego kodu "
        "z 9 cyfr (IMGW-PIB) albo identyfikatora WIGOS",
    ),
    "layout_without_marker": Text(
        "{path} has the layout of an IMGW store but no imgw-store.json marker; run "
        "imgw store init --root {path} to verify the layout and write the marker",
        "{path} ma układ magazynu IMGW, ale nie ma znacznika imgw-store.json; "
        "uruchom imgw store init --root {path}, aby sprawdzić układ i zapisać znacznik",
    ),
}
