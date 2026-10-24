"""Messages of ``output.py``: plain output and its refusals (DEV-19.6, DEV-19.11)."""

from imgwtools.messages import Text

MESSAGES = {
    "duplicate_output_name": Text(
        "Output paths of this request share a name ({count} in conflict, the first: "
        "{first}); give each file its own name (details.paths lists them)",
        "Ścieżki wyjścia tego żądania mają wspólną nazwę ({count} w konflikcie, "
        "pierwsza: {first}); nadaj każdemu plikowi własną nazwę (details.paths je "
        "wymienia)",
    ),
    "output_in_store": Text(
        "The output is, or lies in, a store ({first}); use --root to write the store, "
        "or choose a directory outside every store (details.paths lists the "
        "targets)",
        "Wyjście jest magazynem albo leży w magazynie ({first}); użyj --root, aby "
        "zapisać magazyn, albo wybierz katalog poza każdym magazynem (details.paths "
        "wymienia cele)",
    ),
    "output_exists": Text(
        "Output files already exist ({count}, the first: {first}); use --force to "
        "replace them (details.paths lists them)",
        "Pliki wyjścia już istnieją ({count}, pierwszy: {first}); użyj --force, aby "
        "je zastąpić (details.paths je wymienia)",
    ),
}
