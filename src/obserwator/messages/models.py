"""Messages of ``models.py``."""

from obserwator.messages import Text

MESSAGES = {
    "pandas_required": Text(
        "The method to_dataframe() needs the package pandas; install the extra: "
        "pip install obserwator[pandas]",
        "Metoda to_dataframe() wymaga pakietu pandas. "
        "Zainstaluj dodatek: pip install obserwator[pandas]",
    ),
    "unknown_pmaxtp_probability_allowed": Text(
        "Unknown PMAXTP probability [%]: {probability!r}; allowed: {allowed}",
        "Nieznane prawdopodobieństwo PMAXTP [%]: {probability!r}; dozwolone: {allowed}",
    ),
}
