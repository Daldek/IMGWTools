"""Messages of ``models.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "pandas_required": Text(
        "The method to_dataframe() needs the package pandas; install the extra: "
        "pip install imgwtools[pandas]",
        "Metoda to_dataframe() wymaga pakietu pandas. "
        "Zainstaluj dodatek: pip install imgwtools[pandas]",
    ),
}
