"""Messages of ``store/writer.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "store_needs_file_system_hard": Text(
        "The store needs a file system with hard links (exclusive publication "
        "without replacement): {target}",
        "Magazyn wymaga systemu plików z dowiązaniami twardymi (wyłączna publikacja "
        "bez zastąpienia): {target}",
    ),
    "store_path_must_not_contain": Text(
        "The store path must not contain '..'",
        "Ścieżka magazynu nie może zawierać '..'",
    ),
    "symbolic_link_store_path": Text(
        "A symbolic link in the store path: {part}",
        "Dowiązanie symboliczne w ścieżce magazynu: {part}",
    ),
    "unreadable_marker": Text(
        "An unreadable marker: {path}",
        "Nieczytelny znacznik: {path}",
    ),
    "store_below_the_root": Text(
        "A store lies inside the root: {folder} holds {marker}",
        "Wewnątrz korzenia leży magazyn: {folder} zawiera {marker}",
    ),
    "unsafe_archive_path": Text(
        "An unsafe archive path: {relative}",
        "Niebezpieczna ścieżka archiwum: {relative}",
    ),
    "link_slot_path": Text(
        "A link in the slot path: {path}",
        "Dowiązanie w ścieżce slotu: {path}",
    ),
    "directory_not_empty_imgw_store": Text(
        "The directory is not an empty IMGW store: {path}",
        "Katalog nie jest pustym magazynem IMGW: {path}",
    ),
    "file_system_does_not_support": Text(
        "The file system does not support atomic writing of the store marker (a hard "
        "link): {path} ({strerror})",
        "System plików nie obsługuje atomowego zapisu znacznika magazynu (dowiązanie "
        "twarde): {path} ({strerror})",
    ),
    "no_marker_unsupported_imgw_store": Text(
        "No marker or an unsupported IMGW store: {path}",
        "Brak znacznika lub nieobsługiwany magazyn IMGW: {path}",
    ),
    "date_must_have_time_zone": Text(
        "The date must have a time zone",
        "Data musi mieć strefę czasową",
    ),
    "invalid_archive_version": Text(
        "An invalid archive version: {directory}",
        "Nieprawidłowa wersja archiwum: {directory}",
    ),
    "corrupt_archive_version": Text(
        "A corrupt archive version: {directory}",
        "Uszkodzona wersja archiwum: {directory}",
    ),
    "observation_time_must_have_form": Text(
        "The observation time must have the form YYYY-MM-DDTHH:MM:SSZ: {seen_at!r}",
        "Czas obserwacji musi mieć postać RRRR-MM-DDTGG:MM:SSZ: {seen_at!r}",
    ),
    "observation_register_not_directory": Text(
        "The observation register is not a directory: {register}",
        "Rejestr obserwacji nie jest katalogiem: {register}",
    ),
    "observation_file_collision": Text(
        "An observation file collision: {target}",
        "Kolizja pliku obserwacji: {target}",
    ),
    "file_does_not_meet_content": Text(
        "The file {filename} does not meet the content form {form}: {exc}",
        "Plik {filename} nie spełnia formy treści {form}: {exc}",
    ),
    "path_does_not_belong_dataset": Text(
        "The path does not belong to the dataset {dataset}",
        "Ścieżka nie odpowiada zbiorowi {dataset}",
    ),
    "disallowed_type_archive": Text(
        "A disallowed type of archive: {relative}",
        "Niedozwolony typ archiwum: {relative}",
    ),
    "invalid_last_modified_header": Text(
        "An invalid Last-Modified header",
        "Nieprawidłowy nagłówek Last-Modified",
    ),
    "version_directory_collision": Text(
        "A version directory collision: {target}",
        "Kolizja katalogu wersji: {target}",
    ),
    "observation_write_cancelled": Text(
        "The write of the observation was cancelled",
        "Anulowano zapis obserwacji",
    ),
    "archive_write_cancelled": Text(
        "The write of the archive was cancelled",
        "Anulowano zapis archiwum",
    ),
    "abandoned_staging_removed": Text(
        "Removed an abandoned staging directory older than 24 h: .incoming/{name}",
        "Usunięto porzucony staging starszy niż 24 h: .incoming/{name}",
    ),
    "no_observation_reference": Text(
        "none (the signal of reference is the current version)",
        "brak (sygnałem odniesienia jest bieżąca wersja)",
    ),
    "content_unchanged": Text(
        "Unchanged content in {slot}: the downloaded bytes (SHA-256 {sha}) have the "
        "same canonical content {form} (content_sha256 {content_sha256}) as the "
        "current version {current} (SHA-256 {sha256}); no new version was written, "
        "observation: {recorded}",
        "Treść bez zmian w {slot}: pobrane bajty (SHA-256 {sha}) mają tę samą treść "
        "kanoniczną {form} (content_sha256 {content_sha256}) co bieżąca wersja "
        "{current} (SHA-256 {sha256}); nowej wersji nie zapisano, obserwacja: "
        "{recorded}",
    ),
    "archive_written": Text(
        "Wrote the archive {filename}",
        "Zapisano archiwum {filename}",
    ),
    "store_inside_another_store": Text(
        "The store would lie inside another store: {ancestor} holds {marker}",
        "Magazyn leżałby w innym magazynie: {ancestor} zawiera {marker}",
    ),
    "root_holds_another_store": Text(
        "The directory {path} is the store of another tool: it holds {marker}",
        "Katalog {path} jest magazynem innego narzędzia: zawiera {marker}",
    ),
    "layout_without_marker": Text(
        "{path} has the layout of an IMGW store but no imgw-store.json marker; run "
        "imgw store init --root {path} to verify the layout and write the marker",
        "{path} ma układ magazynu IMGW, ale nie ma znacznika imgw-store.json; "
        "uruchom imgw store init --root {path}, aby sprawdzić układ i zapisać znacznik",
    ),
    "layout_not_imgw_store": Text(
        "The layout of {path} is not that of an IMGW store ({count} problems; see "
        "details.problems)",
        "Układ {path} nie jest układem magazynu IMGW ({count} problemów; zob. "
        "details.problems)",
    ),
    "unexpected_root_entry": Text(
        "unexpected entry {name} beside the trees of the store",
        "nieoczekiwany wpis {name} obok drzew magazynu",
    ),
    "layout_tree_not_directory": Text(
        "{name} is not a directory", "{name} nie jest katalogiem"
    ),
    "foreign_sidecar": Text(
        "{sidecar} is not an imgw-meta/1 sidecar",
        "{sidecar} nie jest sidecarem imgw-meta/1",
    ),
    "sidecar_without_size_or_hash": Text(
        "The sidecar {sidecar} has no readable size_bytes and sha256",
        "Sidecar {sidecar} nie ma czytelnych pól size_bytes i sha256",
    ),
}
