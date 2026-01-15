# IMGWTools - Narzędzie do pobierania danych IMGW

Biblioteka Python i narzędzia do pobierania danych publicznych z Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB). Dane pochodzą z serwisu [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/).

Obsługuje również dane z modeli probabilistycznych opadów maksymalnych (PMAXTP) z serwisu [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

- **Biblioteka Python** - `pip install imgwtools` do integracji z innymi projektami
- **CLI** - narzędzie linii poleceń do pobierania danych
- **REST API** - FastAPI z dokumentacją OpenAPI/Swagger
- **Web GUI** - interfejs webowy z mapą interaktywną

**Obsługiwane dane:**
- Aktualne dane meteorologiczne i hydrologiczne przez API IMGW
- Historyczne dane archiwalne (ZIP/CSV)
- Ostrzeżenia hydrologiczne i meteorologiczne
- Dane PMAXTP (opady maksymalne prawdopodobne)
- Lista stacji z koordynatami

**Kluczowa zasada:** Dane NIE są przechowywane na serwerze (domyślnie) - generowane są bezpośrednie linki do serwerów IMGW.

**Opcjonalne cache'owanie** (dane hydrologiczne):
- SQLite database dla danych historycznych
- Lazy loading - dane pobierane przy pierwszym zapytaniu
- Włączane przez `IMGW_DB_ENABLED=true`

---

## Instalacja

```bash
# Tylko biblioteka (minimalne zależności: httpx, pydantic)
pip install imgwtools

# Z CLI
pip install imgwtools[cli]

# Z REST API
pip install imgwtools[api]

# Pełna instalacja (CLI + API + DB + spatial)
pip install imgwtools[full]

# Dla deweloperów (z repozytorium)
git clone https://github.com/Daldek/IMGWTools.git
cd IMGWTools
pip install -e ".[dev]"
```

---

## Użycie jako biblioteka Python

IMGWTools można używać jako biblioteki w innych projektach Python (np. HydroLOG).

### Dane PMAXTP (opady maksymalne prawdopodobne)

```python
from imgwtools import fetch_pmaxtp

# Pobierz dane dla Warszawy
result = fetch_pmaxtp(latitude=52.23, longitude=21.01, method="POT")

# Opad 15-minutowy z prawdopodobieństwem 50%
precip = result.data.get_precipitation(15, 50)
print(f"Opad 15-min, p=50%: {precip} mm")  # 13.34 mm

# Dostępne czasy trwania: 5, 10, 15, 30, 45, 60, 90, 120, 180... minut
# Dostępne prawdopodobieństwa: 1, 2, 5, 10, 20, 50... %
```

### Aktualne dane hydrologiczne

```python
from imgwtools import fetch_hydro_current

# Wszystkie stacje
stations = fetch_hydro_current()
print(f"Liczba stacji: {len(stations)}")

# Konkretna stacja
data = fetch_hydro_current(station_id="150160180")
print(f"Stan wody: {data[0].water_level_cm} cm")
```

### Aktualne dane synoptyczne

```python
from imgwtools import fetch_synop

# Wszystkie stacje synoptyczne
stations = fetch_synop()

# Po nazwie
warszawa = fetch_synop(station_name="Warszawa")
print(f"Temperatura: {warszawa[0].temperature_c}°C")
```

### Lista stacji z koordynatami

```python
from imgwtools import get_hydro_stations_with_coords

# Pobierz stacje z API hydro-back.imgw.pl
stations = get_hydro_stations_with_coords()
print(f"Liczba stacji: {len(stations)}")

# Filtruj stacje w stanie alarmowym
alarmed = [s for s in stations if s.water_state == "alarm"]
for s in alarmed:
    print(f"{s.name}: {s.latitude}, {s.longitude}")
```

### Pobieranie danych archiwalnych

```python
from imgwtools import download_hydro_data, parse_zip_file

# Pobierz dane dobowe za 2023 rok
zip_data = download_hydro_data("dobowe", 2023)

# Parsuj dane
for station, record in parse_zip_file(zip_data, "dobowe"):
    print(f"{station.name}: {record.water_level_cm} cm ({record.measurement_date})")
```

### Wersja asynchroniczna

```python
import asyncio
from imgwtools import fetch_pmaxtp_async, fetch_hydro_current_async

async def main():
    # Równoległe zapytania
    pmaxtp, hydro = await asyncio.gather(
        fetch_pmaxtp_async(52.23, 21.01),
        fetch_hydro_current_async()
    )
    print(f"PMAXTP: {pmaxtp.data.get_precipitation(15, 50)} mm")
    print(f"Stacje hydro: {len(hydro)}")

asyncio.run(main())
```

### Obsługa błędów

```python
from imgwtools import fetch_pmaxtp, IMGWConnectionError, IMGWValidationError

try:
    result = fetch_pmaxtp(52.23, 21.01)
except IMGWValidationError as e:
    print(f"Błąd walidacji: {e}")  # np. koordynaty poza Polską
except IMGWConnectionError as e:
    print(f"Błąd połączenia: {e}")  # np. timeout, błąd serwera
```

---

## Szybki start (CLI)

```bash
# Uruchom serwer API
imgw server --reload

# Pobierz dane hydrologiczne
imgw fetch hydro -i dobowe -y 2023

# Pobierz dane meteorologiczne
imgw fetch meteo -i miesieczne -s synop -y 2020-2023

# Pobierz aktualne dane z API
imgw fetch current hydro

# Pobierz dane PMAXTP
imgw fetch pmaxtp --lat 52.23 --lon 21.01

# Lista stacji
imgw list stations --type hydro

# Cache danych (wymaga IMGW_DB_ENABLED=true)
imgw db init                                   # Inicjalizacja bazy
imgw db stations --refresh                     # Pobranie listy stacji
imgw db cache --years 2020-2023 -i dobowe      # Cache danych dobowych
imgw db query -s 149180020 -y 2023 -i dobowe   # Zapytanie o dane
```

### REST API

Po uruchomieniu serwera (`imgw server`):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Przykłady:
```bash
# Aktualne dane hydrologiczne
curl http://localhost:8000/api/v1/hydro/current

# Generuj URL do pobrania danych
curl "http://localhost:8000/api/v1/download/url?data_type=hydro&interval=dobowe&year=2023"
```

### Web GUI

Po uruchomieniu serwera dostępne pod http://localhost:8000:
- `/` - Dashboard
- `/download` - Formularze pobierania danych
- `/stations` - Lista stacji (dane pobierane z CSV IMGW)
- `/map` - Mapa interaktywna (dane z API IMGW)

Każda stacja ma link do oficjalnej strony IMGW: `https://hydro.imgw.pl/#/station/{type}/{id}`

---

## Struktura danych IMGW

### Dane hydrologiczne (1951-obecnie)
- `dobowe`: pliki miesięczne (przed 2023) lub roczne (od 2023)
- `miesieczne`: pliki roczne
- `polroczne_i_roczne`: pliki roczne z parametrami T, Q, H

### Dane meteorologiczne (1951-obecnie)
- **1951-2000**: foldery 5-letnie, pliki roczne
- **2001+**: foldery roczne, pliki miesięczne
- Podtypy: klimat, opad, synop

### Źródła danych stacji
- **Lista stacji hydro**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Lista stacji meteo**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Współrzędne dla mapy**: API `danepubliczne.imgw.pl/api/data/hydro`

---

## Struktura projektu

```
src/imgwtools/
├── api/          # REST API (FastAPI)
├── cli/          # Narzędzie CLI (Typer)
├── core/         # Logika biznesowa
│   └── url_builder.py  # Generowanie URL-i
├── db/           # Cache SQLite (opcjonalny)
│   ├── cache_manager.py  # Lazy loading
│   ├── repository.py     # Warstwa dostępu do danych
│   └── parsers.py        # Parsery CSV z ZIP
├── web/          # Web GUI (HTMX + Jinja2)
└── config.py     # Konfiguracja

data/             # Metadane + baza SQLite (gdy włączona)
docker/           # Konfiguracja Docker
tests/            # Testy
```

---

## Docker

```bash
cd docker
docker-compose up -d
```

---

## Cache bazy danych (opcjonalny)

Dla częstych zapytań o dane historyczne można włączyć lokalną bazę SQLite.

### Konfiguracja

```bash
# W pliku .env lub zmiennych środowiskowych
IMGW_DB_ENABLED=true
IMGW_DB_PATH=./data/imgw_hydro.db  # domyślna ścieżka
```

### Użycie

```bash
# Inicjalizacja bazy
imgw db init

# Pobranie listy stacji (1300+ stacji)
imgw db stations --refresh

# Cache danych dla zakresu lat
imgw db cache --years 2020-2023 --interval dobowe

# Zapytanie o dane dla stacji
imgw db query --station 149180020 --years 2020-2023 --interval dobowe

# Export do CSV
imgw db query --station 149180020 --years 2023 --output dane.csv

# Status bazy (rozmiar, liczba rekordów)
imgw db status

# Optymalizacja bazy
imgw db vacuum
```

### Obsługiwane interwały

| Interwał | Opis | Parametry |
|----------|------|-----------|
| `dobowe` | Dane dzienne | - |
| `miesieczne` | Dane miesięczne (min/mean/max) | - |
| `polroczne` | Dane półroczne/roczne | `--param H/Q/T` |

### Lazy loading

Dane są automatycznie pobierane z IMGW przy pierwszym zapytaniu i cache'owane lokalnie. Kolejne zapytania korzystają z cache.

---

## Testy

Projekt zawiera kompleksowe testy jednostkowe dla publicznego API.

### Uruchamianie testów

```bash
# Wszystkie testy
pytest

# Z pokryciem kodu
pytest --cov=imgwtools

# Verbose
pytest -v
```

### Struktura testów

```
tests/
├── conftest.py              # Wspólne fixtures
├── unit/
│   ├── test_models.py       # Modele danych (17 testów)
│   ├── test_fetch.py        # Funkcje pobierania (19 testów)
│   ├── test_stations.py     # Funkcje stacji (17 testów)
│   └── test_urls.py         # Budowanie URL-i (22 testy)
└── integration/             # Testy integracyjne (TODO)
```

### Pokrycie

| Moduł | Pokrycie |
|-------|----------|
| `models.py` | 89% |
| `exceptions.py` | 100% |
| `urls.py` | 100% |
| `stations.py` | 59% |
| `fetch.py` | 45% |

**Łącznie: 75 testów**

---

## Dokumentacja

- `CLAUDE.md` - Instrukcje dla Claude Code
- `ARCHITECTURE.md` - Architektura systemu
- `PRD.md` - Wymagania produktu

---

## Problemy i wsparcie

Zgłoś problemy w sekcji [Issues](https://github.com/Daldek/IMGWTools/issues).

---

## Licencja

Projekt udostępniony na licencji MIT. Szczegóły w pliku `LICENSE`.

---

## Autor

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
