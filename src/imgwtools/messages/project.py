"""Messages of ``project.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "json_object_was_expected": Text(
        "a JSON object was expected",
        "oczekiwano obiektu JSON",
    ),
    "unknown_keys_extras_only_extensions": Text(
        "unknown keys {unknown}; extras only in extensions",
        "nieznane klucze {unknown}; dodatki wyłącznie w extensions",
    ),
    "missing_keys": Text(
        "missing keys {missing}",
        "brak kluczy {missing}",
    ),
    "must_relative_posix_path": Text(
        "{name} must be a relative POSIX path: {value!r}",
        "{name} musi być ścieżką względną POSIX: {value!r}",
    ),
    "must_not_contain_empty_segments": Text(
        "{name} must not contain '..', '.' or empty segments: {text!r}",
        "{name} nie może zawierać '..', '.' ani pustych segmentów: {text!r}",
    ),
    "symbolic_link_path": Text(
        "A symbolic link in the path {name}: {step}",
        "Dowiązanie symboliczne w ścieżce {name}: {step}",
    ),
    "must_not_contain": Text(
        "{name} must not contain '..': {value}",
        "{name} nie może zawierać '..': {value}",
    ),
    "must_lie_directory": Text(
        "{name} must lie in the directory {base}: {value}",
        "{name} musi leżeć w katalogu {base}: {value}",
    ),
    "options_task_must_json_object": Text(
        "The options of a task must be a JSON object",
        "Opcje zadania muszą być obiektem JSON",
    ),
    "series_select_task_needs_explicit": Text(
        "A series select task needs explicit options: {missing}",
        "Zadanie series select wymaga jawnych opcji: {missing}",
    ),
    "option_geometry_applies_only_series": Text(
        "The option geometry applies only to series select tasks",
        "Opcja geometry dotyczy wyłącznie zadań series select",
    ),
    "iso_8601_text_was_expected": Text(
        "an ISO 8601 text was expected",
        "oczekiwano tekstu ISO 8601",
    ),
    "invalid_date": Text(
        "invalid date: {exc}",
        "nieprawidłowa data: {exc}",
    ),
    "date_must_contain_time_zone": Text(
        "the date must contain a time zone (UTC)",
        "data musi zawierać strefę czasową (UTC)",
    ),
    "unknown_role_allowed": Text(
        "unknown role {role!r}; allowed: {roles}",
        "nieznana rola {role!r}; dozwolone: {roles}",
    ),
    "full_sha_256_was_expected": Text(
        "a full SHA-256 was expected (64 lowercase hex digits)",
        "oczekiwano pełnej sumy SHA-256 (64 małe cyfry hex)",
    ),
    "station_code_must_have_9": Text(
        "the station code must have 9 digits (IMGW-PIB) or be a WIGOS identifier: "
        "{station!r}",
        "kod stacji musi mieć 9 cyfr (IMGW-PIB) albo postać identyfikatora WIGOS: "
        "{station!r}",
    ),
    "station_series_file_needs_station": Text(
        "a station_series file needs a station_code",
        "plik station_series wymaga kodu station_code",
    ),
    "file_published_store_version_kind": Text(
        "a file of a published store version (<kind>/versions/…) with a slot of "
        "§13.7 was expected (a station file of a series: "
        "stations/<station_code>.parquet): {path}",
        "oczekiwano pliku opublikowanej wersji magazynu (<rodzaj>/versions/…) o "
        "slocie §13.7 (plik stacji szeregu: stations/<station_code>.parquet): {path}",
    ),
    "fields_content_sha256_content_form": Text(
        "the fields content_sha256 and content_form appear together or not at all",
        "pola content_sha256 i content_form występują razem albo wcale",
    ),
    "non_empty_form_identifier_was": Text(
        "a non-empty form identifier was expected",
        "oczekiwano niepustego identyfikatora formy",
    ),
    "task_name_1_64_characters": Text(
        "the task name: 1–64 characters a-z, 0-9, _ or -, starting with a letter or "
        "digit: {name!r}",
        "nazwa zadania: 1–64 znaki a-z, 0-9, _ lub -, na początku litera lub cyfra: "
        "{name!r}",
    ),
    "command_cannot_project_task": Text(
        "the command {command!r} cannot be a project task",
        "komenda {command!r} nie może być zadaniem projektu",
    ),
    "expected_options_geometry_sha_256": Text(
        "expected {{<options.geometry>: <SHA-256 of the area selection file>}}",
        "oczekiwano {{<options.geometry>: <SHA-256 pliku wyboru obszaru>}}",
    ),
    "selection_area_options_geometry_needs": Text(
        "selection by area (options.geometry) needs geometry_sha256",
        "wybór obszarem (options.geometry) wymaga geometry_sha256",
    ),
    "non_empty_text_null_was": Text(
        "a non-empty text or null was expected",
        "oczekiwano niepustego tekstu albo null",
    ),
    "pinned_imgwtools_version_both_null": Text(
        "pinned_at and imgwtools_version are both null (an unpinned task) or both set",
        "pinned_at i imgwtools_version są oba null (zadanie nieprzypięte) albo oba "
        "ustawione",
    ),
    "list_files_was_expected": Text(
        "a list of files was expected",
        "oczekiwano listy plików",
    ),
    "repeated_path_pinned_file": Text(
        "a repeated path of a pinned file",
        "powtórzona ścieżka przypiętego pliku",
    ),
    "project_directory_must_not_lie": Text(
        "The project directory {directory} must not lie in the store {root}",
        "Katalog projektu {directory} nie może leżeć w magazynie {root}",
    ),
    "invalid_store_directory": Text(
        "Invalid store directory {root}: {exc}",
        "Nieprawidłowy katalog magazynu {root}: {exc}",
    ),
    "directory_not_supported_imgw_store": Text(
        "The directory {root} is not a supported IMGW store: {problems}",
        "Katalog {root} nie jest obsługiwanym magazynem IMGW: {problems}",
    ),
    "unsupported_schema_this_version_imgwtools": Text(
        "unsupported schema {schema!r}; this version of IMGWTools reads "
        "{project_schema}",
        "nieobsługiwany schemat {schema!r}; ta wersja IMGWTools czyta {project_schema}",
    ),
    "non_empty_store_path_was": Text(
        "a non-empty store path was expected",
        "oczekiwano niepustej ścieżki magazynu",
    ),
    "list_tasks_was_expected": Text(
        "a list of tasks was expected",
        "oczekiwano listy zadań",
    ),
    "repeated_task_name": Text(
        "a repeated task name {name!r}",
        "powtórzona nazwa zadania {name!r}",
    ),
    "repeated_key": Text(
        "a repeated key {key!r}",
        "powtórzony klucz {key!r}",
    ),
    "disallowed_value": Text(
        "a disallowed value {name}",
        "niedozwolona wartość {name}",
    ),
    "project_manifest_must_not_symbolic": Text(
        "The project manifest must not be a symbolic link: {path}",
        "Manifest projektu nie może być dowiązaniem symbolicznym: {path}",
    ),
    "no_project_manifest_run_imgw": Text(
        "No project manifest {path}; run imgw project init first",
        "Brak manifestu projektu {path}; najpierw imgw project init",
    ),
    "cannot_read_project_manifest": Text(
        "Cannot read the project manifest {path}: {exc}",
        "Nie można odczytać manifestu projektu {path}: {exc}",
    ),
    "manifest_not_utf_8_text": Text(
        "the manifest is not UTF-8 text: {exc}",
        "manifest nie jest tekstem UTF-8: {exc}",
    ),
    "invalid_json": Text(
        "invalid JSON: {exc}",
        "nieprawidłowy JSON: {exc}",
    ),
    "cannot_lock_project_manifest": Text(
        "Cannot lock the project manifest ({lock}): {exc}",
        "Nie można zablokować manifestu projektu ({lock}): {exc}",
    ),
    "cannot_write_project_manifest": Text(
        "Cannot write the project manifest {target}: {exc}",
        "Nie można zapisać manifestu projektu {target}: {exc}",
    ),
    "conflict_task_was_removed_from": Text(
        "Conflict: the task {name} was removed from the manifest during the "
        "download; the pins were not saved",
        "Konflikt: zadanie {name} usunięto z manifestu w trakcie pobierania; "
        "przypięć nie zapisano",
    ),
    "conflict_task_was_changed_another": Text(
        "Conflict: the task {name} was changed by another process during the "
        "download; the pins were not saved",
        "Konflikt: zadanie {name} zmienił inny proces w trakcie pobierania; przypięć "
        "nie zapisano",
    ),
    "needs_non_empty_path": Text(
        "{what} needs a non-empty path: {value!r}",
        "{what} wymaga niepustej ścieżki: {value!r}",
    ),
    "project_directory": Text(
        "The project directory",
        "Katalog projektu",
    ),
    "store_directory": Text(
        "The store directory",
        "Katalog magazynu",
    ),
    "parameter_tasks_must_collection_task": Text(
        "The parameter tasks must be a collection of task names",
        "Parametr tasks musi być kolekcją nazw zadań",
    ),
    "unknown_project_tasks": Text(
        "Unknown project tasks: {unknown}",
        "Nieznane zadania projektu: {unknown}",
    ),
    "version_lies_outside_store": Text(
        "The version {path} lies outside the store {root}",
        "Wersja {path} leży poza magazynem {root}",
    ),
    "cannot_create_project_directory": Text(
        "Cannot create the project directory {directory}: {exc}",
        "Nie można utworzyć katalogu projektu {directory}: {exc}",
    ),
    "project_manifest_already_exists_points": Text(
        "The project manifest {manifest} already exists and points to the store "
        "{store_dir}; change the store with set_project_store",
        "Manifest projektu {manifest} już istnieje i wskazuje magazyn {store_dir}; "
        "zmiana magazynu: set_project_store",
    ),
    "store_does_not_contain_identical": Text(
        "The store {root} does not contain the identical pinned files ({count}): "
        "{shown}; the manifest is unchanged",
        "Magazyn {root} nie zawiera identycznych przypiętych plików ({count}): "
        "{shown}; manifest bez zmian",
    ),
    "project_manifest_changed_during_verification": Text(
        "The project manifest changed during the verification of the store; repeat "
        "set-store",
        "Manifest projektu zmienił się w trakcie weryfikacji magazynu; powtórz "
        "set-store",
    ),
    "polygon_ring_needs_least_4": Text(
        "a polygon ring needs at least 4 positions",
        "pierścień wielokąta wymaga co najmniej 4 pozycji",
    ),
    "invalid_position": Text(
        "invalid position {position!r}",
        "nieprawidłowa pozycja {position!r}",
    ),
    "polygon_ring_must_closed": Text(
        "a polygon ring must be closed",
        "pierścień wielokąta musi być zamknięty",
    ),
    "geometry_object_was_expected": Text(
        "a geometry object was expected",
        "oczekiwano obiektu geometrii",
    ),
    "unsupported_geometry_expected_polygon_multipolygon": Text(
        "unsupported geometry {kind!r}; expected Polygon or MultiPolygon",
        "nieobsługiwana geometria {kind!r}; oczekiwano Polygon lub MultiPolygon",
    ),
    "empty_polygon": Text(
        "an empty polygon",
        "pusty wielokąt",
    ),
    "geojson_object_was_expected": Text(
        "a GeoJSON object was expected",
        "oczekiwano obiektu GeoJSON",
    ),
    "features_must_list": Text(
        "features must be a list",
        "features musi być listą",
    ),
    "no_polygons": Text(
        "no polygons",
        "brak wielokątów",
    ),
    "area_selection_file_not_valid": Text(
        "The area selection file {name} is not a valid GeoJSON polygon: {exc}",
        "Plik wyboru obszaru {name} nie jest poprawnym wielokątem GeoJSON: {exc}",
    ),
    "no_station_catalog_store_run": Text(
        "No station catalog of {short_name} in the store {root}; run imgw store "
        "catalog{option} first",
        "Brak katalogu stacji {short_name} w magazynie {root}; najpierw imgw store "
        "catalog{option}",
    ),
    "no_area_selection_file": Text(
        "No area selection file {relative}",
        "Brak pliku wyboru obszaru {relative}",
    ),
    "cannot_read_area_selection_file": Text(
        "Cannot read the area selection file {relative}: {exc}",
        "Nie można odczytać pliku wyboru obszaru {relative}: {exc}",
    ),
    "area_selection_covered_no_station": Text(
        "The area selection {relative} covered no station of the catalog {path}",
        "Wybór obszarem {relative} nie objął żadnej stacji katalogu {path}",
    ),
    "task_already_exists_project": Text(
        "The task {name!r} already exists in the project",
        "Zadanie {name!r} już istnieje w projekcie",
    ),
    "no_task_project": Text(
        "No task {name!r} in the project",
        "Brak zadania {name!r} w projekcie",
    ),
    "series_sidecar_does_not_list": Text(
        "The series sidecar {version} does not list its input files correctly",
        "Sidecar szeregu {version} nie wymienia poprawnie plików wejściowych",
    ),
    "plan_does_not_cover_archives": Text(
        "The plan does not cover the archives of the task ({absent}{value}); run "
        "project check again",
        "Plan nie obejmuje archiwów zadania ({absent}{value}); uruchom ponownie "
        "project check",
    ),
    "pinned_file_does_not_match": Text(
        "The pinned file {path} does not match an archive of the series dataset in "
        "the registry",
        "Przypięty plik {path} nie odpowiada archiwum zbioru szeregów z rejestru",
    ),
    "invalid_update_mode_allowed_pinned": Text(
        'Invalid update mode {update!r}; allowed: "pinned", "upgrade"',
        'Nieprawidłowy tryb update {update!r}; dozwolone: "pinned", "upgrade"',
    ),
    "plan_concerns_another_store_than": Text(
        "The plan concerns another store ({root}) than the project ({root_2})",
        "Plan dotyczy innego magazynu ({root}) niż projekt ({root_2})",
    ),
    "manifest_locked": Text(
        "The project manifest is locked (owner: {owner}); if no IMGWTools process "
        "works on the project, remove the directory {lock} by hand",
        "Manifest projektu jest zablokowany (właściciel: {owner}); jeśli żaden "
        "proces IMGWTools nie pracuje na projekcie, usuń ręcznie katalog {lock}",
    ),
    "upgrade_hint": Text(
        'a deliberate re-pin: update="upgrade"',
        'świadome przepięcie: update="upgrade"',
    ),
    "pin_missing_same_content": Text(
        "the pinned file is missing; the version {version} has the same content but "
        "is not identical ({upgrade})",
        "brak przypiętego pliku; wersja {version} ma tę samą treść, ale nie jest "
        "identyczna ({upgrade})",
    ),
    "pin_symlink": Text(
        "a symbolic link instead of the version file",
        "dowiązanie symboliczne zamiast pliku wersji",
    ),
    "pin_missing_in_store": Text(
        "the pinned file is missing in the store",
        "brak przypiętego pliku w magazynie",
    ),
    "pin_not_file": Text(
        "the pinned path is not a file",
        "przypięta ścieżka nie jest plikiem",
    ),
    "pin_not_confirmed_by_index": Text(
        "the series.json index of the version does not confirm the pinned station file",
        "spis series.json wersji nie potwierdza przypiętego pliku stacji",
    ),
    "pin_size_differs": Text(
        "the size {size} B differs from the sidecar ({size_bytes} B)",
        "rozmiar {size} B różni się od sidecara ({size_bytes} B)",
    ),
    "pin_sidecar_other_sha256": Text(
        "the sidecar names another SHA-256 than the pinned one",
        "sidecar wskazuje inną sumę SHA-256 niż przypięta",
    ),
    "pin_sha256_differs": Text(
        "the SHA-256 of the file ({actual}) differs from the pinned one ({sha256})",
        "suma SHA-256 pliku ({actual}) różni się od przypiętej ({sha256})",
    ),
    "equivalent_does_not_confirm": Text(
        "the equivalent version {relative} does not confirm the content of the pin "
        "(SHA-256 of the file {actual}, in the sidecar {sha256})",
        "wersja równoważna {relative} nie potwierdza treści pinu (SHA-256 pliku "
        "{actual}, w sidecarze {sha256})",
    ),
    "equivalent_sha256_differs": Text(
        "the equivalent version {relative}: the SHA-256 of the file ({actual}) "
        "differs from the pinned one ({sha256})",
        "wersja równoważna {relative}: suma SHA-256 pliku ({actual}) różni się od "
        "przypiętej ({sha256})",
    ),
    "task_restored_by_content": Text(
        "Task {name}: the pinned files were restored by content ({count}): "
        "{described}; the pins are unchanged, {upgrade}",
        "Zadanie {name}: przypięte pliki odtworzone treścią ({count}): {described}; "
        "przypięcia bez zmian, {upgrade}",
    ),
    "check_failed": Text(
        "check failed",
        "błąd sprawdzenia",
    ),
    "pins_changed": Text(
        "changed pinned files (not restorable): {changed}",
        "zmienione przypięte pliki (nie do odtworzenia): {changed}",
    ),
    "task_not_pinned": Text(
        "the task is not pinned: project download fetches the data and pins the files",
        "zadanie nieprzypięte: project download pobierze dane i przypnie pliki",
    ),
    "newer_or_missing": Text(
        "newer or missing source data are available; only {upgrade} changes the pins",
        "dostępne nowsze lub brakujące dane źródłowe; piny zmieni wyłącznie {upgrade}",
    ),
    "no_comparable_signal_part": Text(
        "no comparable freshness signal for part of the data",
        "brak porównywalnego sygnału aktualności części danych",
    ),
    "pins_current_content_match": Text(
        "the pinned files are present or restored by content (content_match: "
        "{matched}), the data is current; only {upgrade} changes the pins",
        "przypięte pliki obecne albo odtworzone treścią (content_match: {matched}), "
        "dane aktualne; piny zmieni wyłącznie {upgrade}",
    ),
    "pins_current": Text(
        "the pinned files are present, the data is current",
        "przypięte pliki obecne, dane aktualne",
    ),
    "store_missing": Text(
        "the store {root} does not exist; project download creates it and fetches "
        "the data",
        "magazyn {root} nie istnieje; project download utworzy go i pobierze dane",
    ),
    "series_build_failed": Text(
        "building the series failed",
        "budowa szeregu nie powiodła się",
    ),
    "task_reasons": Text(
        "Task {name}: {reasons}; the pins are unchanged",
        "Zadanie {name}: {reasons}; przypięcia bez zmian",
    ),
    "not_restored": Text(
        "Not restored {key}: {exc}",
        "Nie odtworzono {key}: {exc}",
    ),
    "not_restored_key": Text(
        "Not restored {key}",
        "Nie odtworzono {key}",
    ),
    "server_other_content": Text(
        "{short_name} serves other content of {server_path} (SHA-256 {served}) than "
        "the pinned one ({sha256}); the pins are unchanged, {upgrade}",
        "{short_name} udostępnia inną treść {server_path} (SHA-256 {served}) niż "
        "przypięta ({sha256}); przypięcia bez zmian, {upgrade}",
    ),
    "identical_bytes_written": Text(
        "The identical bytes were written as {written_path}; the pinned version "
        "{key} stays unavailable, {upgrade}",
        "Identyczne bajty zapisano jako {written_path}; przypięta wersja {key} "
        "pozostaje niedostępna, {upgrade}",
    ),
    "unknown_series_dataset": Text(
        "Unknown series dataset {slug}",
        "Nieznany zbiór szeregu {slug}",
    ),
    "current_archives_differ": Text(
        "The current versions of the archives of the dataset {key} differ from the "
        "pinned inputs of the series; an identical version cannot be built, {upgrade}",
        "Bieżące wersje archiwów zbioru {key} różnią się od przypiętych wejść "
        "szeregu; identycznej wersji nie można zbudować, {upgrade}",
    ),
    "series_not_restored": Text(
        "Not restored the series {slug}: {exc}",
        "Nie odtworzono szeregu {slug}: {exc}",
    ),
    "series_other_sha256": Text(
        "The series {key} built from the pinned inputs ({store_path}) has another "
        "SHA-256 ({built}) than the pinned one ({sha256}); the pins are unchanged, "
        "{upgrade}",
        "Szereg {key} zbudowany z przypiętych wejść ({store_path}) ma inną sumę "
        "SHA-256 ({built}) niż przypięta ({sha256}); przypięcia bez zmian, {upgrade}",
    ),
    "version_cannot_restore": Text(
        "The version {path} cannot be restored: the label of the directory or cell "
        "comes from the day of the download; {upgrade}",
        "Wersji {path} nie można odtworzyć: etykieta katalogu/komórki pochodzi z "
        "dnia pobrania; {upgrade}",
    ),
    "task_progress": Text(
        "Task {name}",
        "Zadanie {name}",
    ),
    "command_failed": Text(
        "{command}: failed",
        "{command}: niepowodzenie",
    ),
    "task_error": Text(
        "Task {name}: {exc}",
        "Zadanie {name}: {exc}",
    ),
    "pins_not_in_store": Text(
        "The new store {root} is empty: {count} pinned files are missing. project "
        "download restores them {origin} only with an identical SHA-256{by_content} "
        "(series from exactly the pinned inputs), otherwise it reports a task "
        "error{lost}",
        "Nowy magazyn {root} jest pusty: brak {count} przypiętych plików. project "
        "download odtworzy je {origin} wyłącznie z identyczną sumą "
        "SHA-256{by_content} (szeregi z dokładnie przypiętych wejść), inaczej zgłosi "
        "błąd zadania{lost}",
    ),
    "origin_providers": Text(
        "from {sources}",
        "z {sources}",
    ),
    "origin_source": Text(
        "from the source",
        "ze źródła",
    ),
    "restored_by_content": Text(
        "or, for datasets with a canonical form, with the same content "
        "(restored_by_content)",
        "albo, dla zbiorów z formą kanoniczną, z tą samą treścią (restored_by_content)",
    ),
    "catalogs_not_restored": Text(
        "; it does not restore the station catalog and the PMAXTP cells (tasks: "
        "{tasks}), {upgrade}",
        "; katalogu stacji i komórek PMAXTP nie odtwarza (zadania: {tasks}), {upgrade}",
    ),
    "sources_pair": Text(
        "{first} and {second}",
        "{first} i {second}",
    ),
    "pin_matched": Text(
        "pin {path} (SHA-256 {sha256}) → {version} (SHA-256 {version_sha256}), {basis}",
        "przypięcie {path} (SHA-256 {sha256}) → {version} (SHA-256 "
        "{version_sha256}), {basis}",
    ),
    "shared_content_sha256": Text(
        "shared content_sha256 {content_sha256}",
        "wspólne content_sha256 {content_sha256}",
    ),
    "same_sha256": Text(
        "the same SHA-256",
        "ta sama suma SHA-256",
    ),
    "pins_missing": Text(
        "{count} pinned files are missing; project download restores them only with "
        "an identical SHA-256{by_content}",
        "brak {count} przypiętych plików; project download odtworzy je wyłącznie "
        "przy identycznym SHA-256{by_content}",
    ),
    "or_same_content": Text(
        " or the same content (content_sha256)",
        " albo tej samej treści (content_sha256)",
    ),
}
