"""Messages of ``store/plain.py``: the targets of a plain plan (DEV-19.10)."""

from imgwtools.messages import Text

MESSAGES = {
    "write": Text(
        "Write {what} to {target}",
        "Zapis {what} do {target}",
    ),
    "replace": Text(
        "Write {what} to {target}, replacing the existing file",
        "Zapis {what} do {target}, istniejący plik zostanie zastąpiony",
    ),
    "output_exists": Text(
        "{target} exists, so {what} is not written; --force replaces it",
        "{target} istnieje, więc {what} nie zostanie zapisany; --force go zastąpi",
    ),
    "duplicate_output_name": Text(
        "{target} is the target of more than one file of this request ({what})",
        "{target} jest celem więcej niż jednego pliku tego żądania ({what})",
    ),
    "output_in_store": Text(
        "{target} is, or lies in, a store, so {what} is not written; --root writes "
        "the store",
        "{target} jest magazynem albo leży w magazynie, więc {what} nie zostanie "
        "zapisany; --root zapisuje magazyn",
    ),
}
