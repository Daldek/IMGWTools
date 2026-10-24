"""Messages of ``reference_data.py``, the lines of ``python -m imgwtools.reference_data``."""

from imgwtools.messages import Text

MESSAGES = {
    "fetching_to": Text(
        "Fetching the reference data into: {directory}",
        "Pobieranie danych referencyjnych do: {directory}",
    ),
    "terms_of_use": Text(
        "The data are subject to the IMGW-PIB terms of use.",
        "Dane podlegają warunkom korzystania IMGW-PIB.",
    ),
    "required_attribution": Text(
        "Required attribution: {attribution}\n",
        "Wymagana atrybucja: {attribution}\n",
    ),
    "station_coordinates": Text(
        "Coordinates of the hydrological stations:",
        "Współrzędne stacji hydrologicznych:",
    ),
    "rows_written": Text("  - {path} ({count} rows)", "  - {path} ({count} wierszy)"),
    "bytes_written": Text("  - {path} ({size})", "  - {path} ({size})"),
    "format_descriptions_hydro": Text(
        "Format descriptions (hydro):", "Opisy formatów (hydro):"
    ),
    "format_descriptions_meteo": Text(
        "Format descriptions (meteo):", "Opisy formatów (meteo):"
    ),
    "skipped": Text(
        "  skipped: {name}: HTTP {status}", "  pominięto: {name}: HTTP {status}"
    ),
    "fetch_failed": Text("Download failed: {error}", "Błąd pobierania danych: {error}"),
    "done": Text(
        "\nDone: the IMGW-PIB data were written to {directory}.",
        "\nGotowe: dane IMGW-PIB zapisano w {directory}.",
    ),
}
