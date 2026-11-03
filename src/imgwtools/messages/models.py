"""Messages of ``models.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "pandas_required": Text(
        "The method to_dataframe() needs the package pandas; install the extra: "
        "pip install imgwtools[pandas]",
        "Metoda to_dataframe() wymaga pakietu pandas. "
        "Zainstaluj dodatek: pip install imgwtools[pandas]",
    ),
    "unknown_pmaxtp_probability_allowed": Text(
        "Unknown PMAXTP probability [%]: {probability!r}; allowed: {allowed}",
        "Nieznane prawdopodobieństwo PMAXTP [%]: {probability!r}; dozwolone: {allowed}",
    ),
}
