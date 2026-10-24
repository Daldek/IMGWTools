"""Messages of the Web GUI (``web/app.py``); the GUI renders them in Polish."""

from imgwtools.messages import Text

MESSAGES = {
    "title_index": Text(
        "IMGWTools - download IMGW data",
        "IMGWTools - Pobieranie danych IMGW",
    ),
    "title_download": Text("Data download", "Pobieranie danych"),
    "title_archives": Text("Archive data", "Dane archiwalne"),
    "title_stations": Text("Station list", "Lista stacji"),
    "title_map": Text("Station map", "Mapa stacji"),
    "kind_hydro": Text("Hydrological data", "Dane hydrologiczne"),
    "kind_meteo": Text("Meteorological data", "Dane meteorologiczne"),
}
