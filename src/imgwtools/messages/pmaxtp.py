"""Messages of ``store/pmaxtp.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "unknown_pmaxtp_method_allowed_pot": Text(
        "Unknown PMAXTP method: {method!r}; allowed POT, AMP",
        "Nieznana metoda PMAXTP: {method!r}; dozwolone POT, AMP",
    ),
    "cell_index_must_non_negative": Text(
        "The cell index {name} must be a non-negative integer: {value!r}",
        "Indeks komórki {name} musi być nieujemną liczbą całkowitą: {value!r}",
    ),
    "give_both_cell_indices_ind": Text(
        "Give both cell indices ind_x and ind_y or neither",
        "Podaj oba indeksy komórki ind_x i ind_y albo żaden",
    ),
    "pmaxtp_response_empty_invalid_table": Text(
        "PMAXTP response: an empty or invalid table {name}",
        "Odpowiedź PMAXTP: pusta lub niepoprawna tabela {name}",
    ),
    "pmaxtp_response_empty_row": Text(
        "PMAXTP response: an empty row {name}[{duration}]",
        "Odpowiedź PMAXTP: pusty wiersz {name}[{duration}]",
    ),
    "pmaxtp_response_value_not_number": Text(
        "PMAXTP response: the value {name}[{duration}][{probability}] is not a number",
        "Odpowiedź PMAXTP: wartość {name}[{duration}][{probability}] nie jest liczbą",
    ),
    "unexpected_format_pmaxtp_response": Text(
        "Unexpected format of the PMAXTP response",
        "Nieoczekiwany format odpowiedzi PMAXTP",
    ),
    "pmaxtp_response_has_no_description": Text(
        "The PMAXTP response has no description of the point",
        "Odpowiedź PMAXTP bez opisu punktu",
    ),
    "pmaxtp_response_has_no_valid": Text(
        "The PMAXTP response has no valid cell indices indX/indY",
        "Odpowiedź PMAXTP bez poprawnych indeksów komórki indX/indY",
    ),
    "pmaxtp_response_has_no_cell": Text(
        "The PMAXTP response has no cell center dataLon/dataLat",
        "Odpowiedź PMAXTP bez środka komórki dataLon/dataLat",
    ),
    "pmaxtp_response_has_no_data": Text(
        "The PMAXTP response has no data (an empty data)",
        "Odpowiedź PMAXTP bez danych (puste data)",
    ),
    "invalid_json_response_from_pmaxtp": Text(
        "Invalid JSON response from the PMAXTP API",
        "Niepoprawna odpowiedź JSON z API PMAXTP",
    ),
    "given_cell_indices_differ_from": Text(
        "The given cell indices {expected_x}_{expected_y} differ from the API "
        "response {cell_x}_{cell_y}; nothing was written",
        "Podane indeksy komórki {expected_x}_{expected_y} różnią się od odpowiedzi "
        "API {cell_x}_{cell_y}; nic nie zapisano",
    ),
    "no_stored_pmaxtp_cell": Text(
        "No stored PMAXTP cell {method} {cell_x}_{cell_y}",
        "Brak zapisanej komórki PMAXTP {method} {cell_x}_{cell_y}",
    ),
    "version_does_not_belong_cell": Text(
        "The version {version} does not belong to the cell {method} {cell_x}_{cell_y}",
        "Wersja {version} nie należy do komórki {method} {cell_x}_{cell_y}",
    ),
    "no_version_pmaxtp_cell": Text(
        "No version of the PMAXTP cell: {version}",
        "Brak wersji komórki PMAXTP: {version}",
    ),
    "unsupported_schema": Text(
        "unsupported schema {schema!r}",
        "nieobsługiwany schemat {schema!r}",
    ),
    "method_indices_do_not_match": Text(
        "the method or the indices do not match the path",
        "metoda lub indeksy niezgodne ze ścieżką",
    ),
    "corrupt_pmaxtp_cell": Text(
        "A corrupt PMAXTP cell {path}: {exc}",
        "Uszkodzona komórka PMAXTP {path}: {exc}",
    ),
}
