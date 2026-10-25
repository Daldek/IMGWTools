"""Messages of ``output.py``: plain output and its refusals (DEV-19.6, DEV-19.11)."""

from imgwtools.messages import Text

MESSAGES = {
    "exclusive_options": Text(
        "output_dir and root exclude each other: write plain files (--output-dir) "
        "or the store (--root), not both",
        "output_dir i root wykluczają się: zapisz zwykłe pliki (--output-dir) albo "
        "magazyn (--root), nie oba naraz",
    ),
    "duplicate_output_name": Text(
        "Output paths of this request share a name ({count} in conflict, the first: "
        "{first}); give each file its own name (details.paths lists them)",
        "Ścieżki wyjścia tego żądania mają wspólną nazwę ({count} w konflikcie, "
        "pierwsza: {first}); nadaj każdemu plikowi własną nazwę (details.paths je "
        "wymienia)",
    ),
    "directory_in_store": Text(
        "The output directory is, or lies in, a store ({directory}, store: {store}); "
        "use --root to write the store, or choose a directory outside every store",
        "Katalog wyjścia jest magazynem albo leży w magazynie ({directory}, magazyn: "
        "{store}); użyj --root, aby zapisać magazyn, albo wybierz katalog poza "
        "każdym magazynem",
    ),
    "output_in_store": Text(
        "Targets would enter a store ({count} in conflict, the first: {first}); use "
        "--root to write the store, or choose a directory with no store below it "
        "(details.paths lists the targets)",
        "Cele weszłyby do magazynu ({count} w konflikcie, pierwszy: {first}); użyj "
        "--root, aby zapisać magazyn, albo wybierz katalog bez magazynu pod spodem "
        "(details.paths wymienia cele)",
    ),
    "output_exists": Text(
        "Output files already exist ({count}, the first: {first}); use --force to "
        "replace them (details.paths lists them)",
        "Pliki wyjścia już istnieją ({count}, pierwszy: {first}); użyj --force, aby "
        "je zastąpić (details.paths je wymienia)",
    ),
    "output_file_exists": Text(
        "The output file already exists ({first}); use --force to replace it",
        "Plik wyjścia już istnieje ({first}); użyj --force, aby go zastąpić",
    ),
    "output_file_in_store": Text(
        "The output file lies in a store ({first}); an export is written outside "
        "every store, so choose another file",
        "Plik wyjścia leży w magazynie ({first}); eksport zapisuje się poza każdym "
        "magazynem, więc wybierz inny plik",
    ),
}
