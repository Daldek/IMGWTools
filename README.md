# IMGWTools - Narzędzie do pobierania danych IMGW

Narzędzie do pobierania danych publicznych z Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB). Dane pochodzą z serwisu [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/).

Obsługuje również dane z modeli probabilistycznych opadów maksymalnych (PMAXTP) z serwisu [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

1. **Trzy interfejsy dostępu**:
   - **CLI** - narzędzie linii poleceń do pobierania danych
   - **REST API** - FastAPI z dokumentacją OpenAPI/Swagger
   - **Web GUI** - interfejs webowy z mapą interaktywną

2. **Pobieranie danych**:
   - Aktualne dane meteorologiczne i hydrologiczne przez API IMGW
   - Historyczne dane archiwalne (ZIP/CSV)
   - Ostrzeżenia hydrologiczne i meteorologiczne
   - Dane PMAXTP (opady maksymalne prawdopodobne)

3. **Kluczowa zasada**:
   - Dane NIE są przechowywane na serwerze (domyślnie)
   - Generowane są bezpośrednie linki do serwerów IMGW

4. **Opcjonalne cache'owanie** (dane hydrologiczne):
   - SQLite database dla danych historycznych
   - Lazy loading - dane pobierane przy pierwszym zapytaniu
   - Włączane przez `IMGW_DB_ENABLED=true`

---

## Instalacja

```bash
# Klonowanie repozytorium
git clone https://github.com/Daldek/IMGWTools.git
cd IMGWTools

# Utworzenie środowiska wirtualnego
python3 -m venv .venv
source .venv/bin/activate

# Instalacja pakietu
pip install -e ".[dev]"
```

---

## Szybki start

### CLI

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
