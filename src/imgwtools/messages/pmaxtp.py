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
    "cell_unknown_without_download": Text(
        "{method} {latitude:.4f},{longitude:.4f}: the cell is unknown without a "
        "download: the indices indX/indY come only from the API response, which "
        "gives no freshness signal",
        "{method} {latitude:.4f},{longitude:.4f}: komórka nieznana bez pobrania — "
        "indeksy indX/indY ustala wyłącznie odpowiedź API, które nie udostępnia "
        "sygnału aktualności",
    ),
    "local_version": Text(
        "local version {current}",
        "lokalna wersja {current}",
    ),
    "no_local_version": Text(
        "no local version",
        "brak lokalnej wersji",
    ),
    "cell_cannot_check": Text(
        "{method} cell {cell}_{cell_2}: {where}; the freshness cannot be checked "
        "without a download (the API gives no freshness signal)",
        "{method} komórka {cell}_{cell_2}: {where}; aktualności nie można sprawdzić "
        "bez pobrania (API nie udostępnia sygnału aktualności)",
    ),
    "cell_unchanged": Text(
        "PMAXTP cell {cell}_{cell_2} unchanged",
        "Komórka PMAXTP {cell}_{cell_2} bez zmian",
    ),
    "cell_published": Text(
        "PMAXTP cell {cell}_{cell_2}: {name}",
        "Komórka PMAXTP {cell}_{cell_2}: {name}",
    ),
    "cell_written": Text(
        "PMAXTP cell {cell}_{cell_2} written to {directory}",
        "Komórka PMAXTP {cell}_{cell_2} zapisana w {directory}",
    ),
    "plain_cell_what": Text(
        "the PMAXTP cell {method} {cell}_{cell_2}",
        "komórki PMAXTP {method} {cell}_{cell_2}",
    ),
    "plain_response_what": Text(
        "the raw answer for the PMAXTP cell {method} {cell}_{cell_2}",
        "surowej odpowiedzi dla komórki PMAXTP {method} {cell}_{cell_2}",
    ),
    "plain_cell_unknown": Text(
        "The cell of the point {latitude}, {longitude} ({method}) is known only after "
        "the request: cell.json and response.json go to {method}/<indX>_<indY>/ in "
        "{directory}",
        "Komórka punktu {latitude}, {longitude} ({method}) jest znana dopiero po "
        "żądaniu: cell.json i response.json trafią do {method}/<indX>_<indY>/ w "
        "{directory}",
    ),
}
