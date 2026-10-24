"""Messages of ``store/content.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "unknown_content_form_allowed": Text(
        "Unknown content form {form!r}; allowed: {content_forms}",
        "Nieznana forma treści {form!r}; dozwolone: {content_forms}",
    ),
    "root_value_json_document_not": Text(
        "the root value of the JSON document is not an object",
        "wartość główna dokumentu JSON nie jest obiektem",
    ),
    "json_string_contains_unpaired_utf": Text(
        "a JSON string contains an unpaired UTF-16 surrogate",
        "napis JSON zawiera niesparowany surogat UTF-16",
    ),
    "json_document_nested_too_deeply": Text(
        "the JSON document is nested too deeply",
        "zbyt głębokie zagnieżdżenie dokumentu JSON",
    ),
    "content_not_valid_utf_8": Text(
        "the content is not valid UTF-8 (byte {start})",
        "treść nie jest poprawnym UTF-8 (bajt {start})",
    ),
    "invalid_json_line_column": Text(
        "invalid JSON: {msg} (line {lineno}, column {colno})",
        "niepoprawny JSON: {msg} (wiersz {lineno}, kolumna {colno})",
    ),
    "repeated_key_json_object": Text(
        "a repeated key {key!r} in a JSON object",
        "powtórzony klucz {key!r} w obiekcie JSON",
    ),
    "disallowed_constant_json_document": Text(
        "a disallowed constant {name} in the JSON document",
        "niedozwolona stała {name} w dokumencie JSON",
    ),
    "number_outside_ieee_754_double": Text(
        "the number {literal} is outside the IEEE 754 double range",
        "liczba {literal} poza zakresem IEEE 754 double",
    ),
}
