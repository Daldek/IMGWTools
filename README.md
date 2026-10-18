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

**Kluczowa zasada:** domyślnie serwer niczego nie zapisuje — generuje bezpośrednie linki do serwerów IMGW, a dane bieżące przekazuje na żywo. Dane trafiają na dysk wyłącznie po jawnej decyzji: wskazaniu katalogu `--output`, korzenia magazynu (`--root`) albo skonfigurowaniu `IMGW_STORE_ROOT` na serwerze.

**Wersjonowany magazyn danych** (opcjonalny, od 3.0.0):
- niezmienne wersje archiwów IMGW 1:1 z sumami SHA-256, nagłówkami HTTP i licencją w sidecarze `*.meta.json`,
- sprawdzanie aktualności bez pobierania (listing + `HEAD`) i plan `imgw-plan/1`,
- szeregi stacji w Parquet, katalog stacji `stations.geojson`, komórki PMAXTP, eksport CSV,
- czytelny offline z dysku lokalnego lub udziału sieciowego, bez bazy danych.

---

## Instalacja

```bash
# Tylko biblioteka (minimalne zależności: httpx, pydantic)
pip install imgwtools

# Z CLI
pip install imgwtools[cli]

# Z REST API
pip install imgwtools[api]

# Z magazynem wersjonowanym i szeregami Parquet (pyarrow)
pip install imgwtools[store]

# Z eksportem do DataFrame (PMaXTPData.to_dataframe)
pip install imgwtools[pandas]

# Pełna instalacja (CLI + API + magazyn + pandas)
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
print(f"Opad 15-min, p=50%: {precip} mm")  # opad [mm] dla t=15 min, p=50%

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

# Pobierz dane dobowe za 2023 rok (od 3.0.0 wynik to DownloadResult, nie bytes)
result = download_hydro_data("dobowe", 2023)
print(result.url, result.etag, result.last_modified, result.content_length)

# Parsuj dane
for station, record in parse_zip_file(result.data, "dobowe"):
    print(f"{station.station_name}: {record.water_level_cm} cm ({record.measurement_date})")
```

### Magazyn wersjonowany (wymaga `imgwtools[store]` dla Parquet)

```python
from imgwtools import (
    archive_files,
    build_series,
    check_store,
    current_version,
    export_series,
    init_store,
    read_archive,
    read_series,
    read_series_index,
    read_station_list,
    sync_store,
)

store = init_store("/dane/imgw")  # jawny korzeń; brak domyślnego ./data

# 1. Sprawdź aktualność bez pobierania archiwów (listing + HEAD)
plan = check_store(store, datasets=["pl.imgw.hydro_daily"], years=[2023, 2024])
plan.to_json("plan.json")  # plik planu imgw-plan/1 poza magazynem

# 2. Pobierz nowe/brakujące pliki według planu i zbuduj szeregi Parquet
report = sync_store(store, plan=plan)

# 3. Czytaj bieżącą wersję szeregu (offline)
series = current_version(store, slot="series:hydro_daily")
index = read_series_index(series.version)  # tylko JSON, bez pyarrow
for record in read_series(series.version, station="149180020", variables=["H", "Q"]):
    q = record.measurements["Q"]
    print(record.date, q.value, q.flag)  # flag: value|missing|no_phenomenon|accumulated

# 4. Eksport CSV z jednostkami i atrybucją IMGW-PIB
export_series(series.version, station="149180020", path="q.csv", variables=["Q"])

# 5. Rekordy jednej zapisanej wersji archiwum (SHA-256 weryfikowane, parser zbioru)
(daily_2024,) = archive_files("pl.imgw.hydro_daily", years=[2024])
archive = current_version(store, slot=f"archive:{daily_2024.server_path}")
records = list(read_archive(archive.version))

# 6. Bieżąca lista stacji zbioru pl.imgw.hydro_stations / pl.imgw.meteo_stations
#    (zapisuje ją build_catalog); jeden typ StationListEntry z polem kind
for station in read_station_list(store, kind="meteo"):
    print(station.station_code, station.name, station.short_code)
```

Do testów offline służy `imgwtools.testing.build_fixture_store(root)` — buduje mały magazyn z nagranych odpowiedzi, bez internetu.

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

# Magazyn wersjonowany (jawny --root)
imgw store init --root /dane/imgw
imgw store check --root /dane/imgw --dataset pl.imgw.hydro_daily --years 2023-2024 --plan plan.json
imgw store sync --root /dane/imgw --plan plan.json
imgw store catalog --root /dane/imgw          # stations.geojson
imgw store read --version /dane/imgw/archives/versions/<ścieżka>/<wersja> --format jsonl
imgw series select --root /dane/imgw --dataset pl.imgw.hydro_daily --stations 149180020
imgw series export --version /dane/imgw/series/versions/hydro_daily/<wersja> \
    --station 149180020 --path q.csv --variables H,Q
imgw pmaxtp sync --root /dane/imgw --method POT --lat 52.23 --lon 21.01
imgw project init --project-dir ./projekt --store-dir /dane/imgw
```

Komendy `store`, `series`, `pmaxtp`, `project` oraz `fetch hydro|meteo` mają flagę `--check`, która wypisuje plan `imgw-plan/1` bez zapisu i bez pobierania danych. `imgw fetch hydro|meteo -o KATALOG` zapisuje pliki w podkatalogach odpowiadających ścieżkom na serwerze IMGW.

Wynik komend magazynu (JSON albo ścieżka) trafia na stdout, a postęp, komunikaty (każdy jednakowy raz na uruchomienie) i podsumowanie `fetch hydro|meteo` — na stderr, więc stdout można przekazać wprost do parsera JSON (także z `--check`). Kody wyjścia:

| Kod | Znaczenie |
|---|---|
| `0` | sukces |
| `1` | błąd (`Błąd: …` na stderr) albo wynik z nieudaną pozycją: `failed`/`stale_plan` w `store sync` (archiwa lub szeregi), `series build`, `store catalog`, `pmaxtp sync`, zadaniach i plikach `project download|status|verify`, plikach `fetch hydro|meteo` — pełny JSON wyniku jest mimo to wypisany |
| `130` | anulowanie Ctrl+C (wynik częściowy wypisany) |

Punkt PMAXTP w ramce współrzędnych Polski, ale poza siatką IMGW (np. Kaliningrad, Lwów, Bałtyk) daje `IMGWValidationError` (`imgw pmaxtp sync`/`imgw fetch pmaxtp`: `Błąd: …`, kod 1; REST 400). `imgw project set-store` przyjmuje nowy pusty magazyn z ostrzeżeniem `pins_not_in_store`; następne `imgw project download` odtwarza przypięte pliki tylko z identycznym SHA-256, inaczej zgłasza błąd zadania.

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

# Magazyn (wymaga IMGW_STORE_ROOT na serwerze; inaczej 503)
curl http://localhost:8000/api/v1/store/info
curl "http://localhost:8000/api/v1/store/entries?kind=series"
```

Trasy magazynu (`/api/v1/store/*`, `/api/v1/series/*`, `/api/v1/pmaxtp/store/sync`) działają tylko na serwerowym, absolutnym `IMGW_STORE_ROOT`. Operacje zapisujące wymagają dodatkowo `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` i nagłówka `X-API-Key` z tym tokenem — domyślnie są wyłączone (403).

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

> **Format CSV:** pliki archiwalne IMGW są niespójne między rocznikami w trzech aspektach:
> - **separator** — większość roczników używa przecinka z cudzysłowami, część (np. 2023) średnika, a niektóre mają dodatkowy wiersz nagłówka;
> - **kodowanie** — standardem jest CP1250, ale np. `codz_2023.zip` jest w UTF-8 z BOM;
> - **cudzysłowy** — pliki dobowe i miesięczne 2024 mają całe wiersze opakowane w cudzysłów (z podwojonymi cudzysłowami wewnątrz).
>
> Parsery (`parse_zip_file`) **wykrywają separator, kodowanie i wariant cudzysłowów automatycznie, per plik**. Zweryfikowano na danych rzeczywistych dla roczników 2019-2024 (wszystkie interwały).

### Dane meteorologiczne (1950-obecnie)
- **do 2000**: foldery 5-letnie; **od 2001**: foldery roczne
- **miesieczne**: jeden plik na folder (`{folder}_m_{k|o|s}.zip`)
- **dobowe/terminowe klimat i opad**: pliki roczne (do 2000) lub miesięczne (od 2001)
- **dobowe/terminowe synop**: pliki per stacja (`{folder}_{kod}_s.zip`) — generator URL zgłasza błąd (użyj interwału miesięcznego)
- **terminowe opad**: zbiór nie istnieje na serwerze IMGW
- Siatki folderów różnią się na starcie: klimat od `1951_1955`, opad od `1950_1955`, synop od `1960_1965` (struktura zweryfikowana na serwerach IMGW, 2026-07-05)

### Źródła danych stacji
- **Lista stacji hydro**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Lista stacji meteo**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Współrzędne dla mapy**: API `hydro-back.imgw.pl/map/stations/hydrologic` (900+ stacji ze stanem wody)

---

## Struktura projektu

```
src/imgwtools/
├── api/          # REST API (FastAPI), m.in. routes/store.py
├── cli/          # Narzędzie CLI (Typer): fetch, list, admin, store, series, pmaxtp, project
├── core/
│   └── url_builder.py  # Generowanie URL-i
├── _parsing/     # Parsery archiwów hydro/meteo (publicznie: imgwtools.parsers)
├── store/        # Magazyn wersjonowany: writer, sync, series, catalog, pmaxtp, reader, export
├── datasets.py   # Rejestr zbiorów pl.imgw.* i generator plików archiwów
├── commands.py   # Katalog komend wspólny dla CLI, REST i integracji
├── project.py    # Manifest projektu imgw-project/1
├── testing.py    # build_fixture_store — magazyn testowy offline
├── web/          # Web GUI (HTMX + Jinja2)
└── config.py     # Konfiguracja (IMGW_*)

data/             # Lokalne dane referencyjne (python -m imgwtools.reference_data), poza repozytorium
docker/           # Konfiguracja Docker
tests/            # Testy (offline; fixtury magazynu w tests/fixtures/store)
```

---

## Docker

```bash
cd docker
docker-compose up -d
```

---

## Magazyn wersjonowany (opcjonalny)

Magazyn to zwykły katalog wskazany jawnie przez użytkownika (`--root`, `init_store(root)`, na serwerze `IMGW_STORE_ROOT`). Nie ma domyślnej lokalizacji ani bazy danych; magazyn można czytać offline z dysku lokalnego lub udziału sieciowego. Szczegóły: `docs/DECISIONS.md` (ADR-001) i `docs/superpowers/specs/2026-10-17-versioned-store-design.md`.

### Układ katalogu

```text
<root>/imgw-store.json                                  # znacznik imgw-store/1
  archives/versions/<ścieżka serwera>/<stem>/<etykieta>_<sha8>/<plik>[.meta.json]
  stations/versions/<etykieta>_<sha8>/stations.geojson[.meta.json]
  series/versions/<slug>/<etykieta>_<sha8>/series.json[.meta.json] + stations/<kod>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<etykieta>_<sha8>/cell.json[.meta.json]
  .incoming/                                            # staging; nigdy nie jest wersją
```

Wersje są niezmienne i tylko dopisywane: brak nadpisywania, dowiązań i ścieżki `latest`. Bieżącą wersję wylicza `current_version(root, slot=...)`. Każdy plik główny ma sidecar `*.meta.json` (`imgw-meta/1`) z SHA-256, rozmiarem, żądaniem, nagłówkami HTTP i licencją IMGW-PIB.

### Zbiory

| Klucz | Zawartość |
|-------|-----------|
| `pl.imgw.hydro_daily` | Hydro dobowe: H [cm], Q [m3/s], T [°C] |
| `pl.imgw.hydro_monthly` | Hydro miesięczne: H/Q/T × min/mean/max |
| `pl.imgw.hydro_semiannual` | Hydro półroczne i roczne: H/Q/T × min/mean/max z datami ekstremów |
| `pl.imgw.meteo_climate_daily` | Meteo klimat dobowe: Tmax, Tmin, Tmean, Tground, P, pokrywa śnieżna |
| `pl.imgw.meteo_precip_daily` | Meteo opad dobowy: P, pokrywa i świeży śnieg |
| `pl.imgw.hydro_stations`, `pl.imgw.meteo_stations` | Listy stacji (CSV) — wejście katalogu `stations.geojson` |
| `pl.imgw.pmaxtp` | PMAXTP per komórka siatki (`POT`, `AMP`) |

Dane bieżące (hydro, synop), ostrzeżenia i `fetch_pmaxtp` pozostają zapytaniami na żywo, bez magazynu.

### Schematy

`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1` (oraz rozszerzenie `imgw-pmaxtp/1`) mają własne liczniki wersji, niezależne od wersji pakietu. W ramach `/1` dochodzą tylko pola opcjonalne; zmiana niezgodna oznacza `/2`. Nieznana wersja jest raportowana (`store_info(...).supported is False`), a nie zgadywana.

### Integracje

- **Archiwista** czyta magazyn wyłącznie publicznym API odczytu (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `read_pmaxtp`); IMGWTools jest jedynym piszącym, a w magazynie nie ma plików Archiwisty.
- **Retman** uruchamia działania jako handler przez publiczny katalog komend (`data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`) — te same opcje, walidacja i komunikaty co w CLI.

Poprzedni opcjonalny cache SQLite został usunięty w 3.0.0 bez migracji — zob. `docs/CHANGELOG.md`.

---

## Testy

Projekt zawiera testy jednostkowe i kontraktowe publicznego API, CLI i REST. Wszystkie działają offline: sieć jest mockowana (`respx`) albo odtwarzana z nagrań w `tests/fixtures/store/`.

### Uruchamianie testów

```bash
# Wszystkie testy (przez venv projektu)
.venv/bin/python -m pytest

# Z pokryciem kodu
.venv/bin/python -m pytest --cov=imgwtools
```

### Struktura testów

```
tests/
├── conftest.py              # Wspólne fixtures; autouse isolated_data_dir (settings.data_dir w tmp)
├── fixtures/store/          # Syntetyczne archiwa i nagrane odpowiedzi HTTP (fikcyjne stacje)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets.py, test_coverage.py              # rejestr zbiorów, pokrycie
│   ├── test_store_*.py, test_series_export.py          # magazyn: writer, sync, series, catalog, pmaxtp, reader
│   ├── test_fixture_builder.py                         # imgwtools.testing
│   ├── test_commands.py, test_project.py               # katalog komend, imgw-project/1
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py   # CLI, REST i Web GUI
│   ├── test_reference_data.py                          # python -m imgwtools.reference_data
│   └── test_public_store_api.py                        # kontrakt eksportów publicznych
└── contract/                                           # kontrakt magazynu, parytet CLI = API, projekt
```

**Łącznie: 998 testów, pokrycie 93%** (`pytest --cov=imgwtools`, 2026-10-18).

---

## Dokumentacja

- `CLAUDE.md` - Instrukcje dla Claude Code
- `docs/CHANGELOG.md` - Historia zmian (w tym BREAKING 3.0.0)
- `docs/DECISIONS.md` - Rejestr decyzji (ADR-001: magazyn wersjonowany)
- `docs/ARCHITECTURE.md` - Architektura systemu
- `docs/PRD.md` - Wymagania produktu
- `docs/PROGRESS.md` - Postęp i backlog

---

## Problemy i wsparcie

Zgłoś problemy w sekcji [Issues](https://github.com/Daldek/IMGWTools/issues).

---

## Źródła danych

IMGWTools nie dystrybuuje danych IMGW-PIB, a serwer domyślnie ich nie przechowuje — każde pobranie i zapis do magazynu jest świadomą decyzją użytkownika lub administratora (jawny `--output`, `--root`, `IMGW_STORE_ROOT`). Poniżej zestawienie wykorzystywanych źródeł.

| Źródło | Operator | Warunki korzystania |
|--------|----------|---------------------|
| Archiwum pomiarowo-obserwacyjne — `danepubliczne.imgw.pl/data` (hydro/meteo, ZIP/CSV) | IMGW-PIB | Nieodpłatnie do celów prywatnych i naukowych; dane o wysokiej wartości — w każdym celu; część zastosowań komercyjnych wymaga umowy; obowiązkowa atrybucja. [Regulamin](https://danepubliczne.imgw.pl/regulations)
| API czasu rzeczywistego — `danepubliczne.imgw.pl/api/data` (hydro, synop, meteo, ostrzeżenia) | IMGW-PIB | Jak wyżej ([regulamin](https://danepubliczne.imgw.pl/regulations))
| PMAXTP — `klimat.imgw.pl/opady-maksymalne` | IMGW-PIB | Wskazanie źródła IMGW-PIB (dane ze strony `klimat.imgw.pl/opady-maksymalne`) oraz cytowanie monografii Projektu PMAXTP (red. B. Ozga-Zieliński, IMGW-PIB, Warszawa 2022; monografia: Open Access, CC-BY 4.0); przy danych przetworzonych — adnotacja o przetworzeniu; korzystanie na własne ryzyko. [Regulamin](https://klimat.imgw.pl/opady-maksymalne/) |
| Mapa stacji ze współrzędnymi — `hydro-back.imgw.pl/map/stations/hydrologic` (backend serwisu `hydro.imgw.pl`) | IMGW-PIB | Regulamin serwisu hydro.imgw.pl (akceptacja przez rozpoczęcie korzystania); obowiązuje ogólna zasada wskazania źródła IMGW-PIB. [Regulamin](https://hydro.imgw.pl/#/regulamin) |

Obowiązek podania atrybucji przy publikacji wyników spoczywa na użytkowniku pobierającym dane.

### Dane referencyjne (listy stacji, współrzędne, opisy formatów)

Repozytorium **nie zawiera** danych IMGW. Pliki referencyjne używane przez narzędzia (listy stacji, współrzędne, opisy formatów) pobierz jednorazowo — po instalacji pakietu (`pip install -e .`), bez żadnych argumentów:

```bash
python -m imgwtools.reference_data
```

Pobrane pliki trafiają do `data/` i pochodzą z IMGW-PIB — podlegają warunkom IMGW-PIB (nie licencji MIT projektu).

Jedyny dołączony do pakietu zbiór geograficzny to obrys granicy Polski `src/imgwtools/_data/poland_border_wgs84.geojson` (kontrola położeń w katalogu stacji) z Natural Earth 1:10m Admin 0 – Countries v5.1.2 — domena publiczna ([warunki](https://www.naturalearthdata.com/about/terms-of-use/)), nie dane IMGW-PIB.

---

## Zmiany w wersji 3.0.0

Pełna lista: [`docs/CHANGELOG.md`](docs/CHANGELOG.md) (także wcześniejsze wydania).

### Zmiany łamiące kompatybilność

- `download_hydro_data`, `download_meteo_data` (i `*_async`) zwracają `DownloadResult`
  zamiast `bytes` — bajty archiwum są w polu `.data`, obok `url`, `etag`,
  `last_modified`, `content_length`.
- Usunięty cache SQLite: pakiet `imgwtools.db`, komendy CLI cache, endpoint
  `GET /api/v1/hydro/data`, jego ustawienia środowiskowe i dodatek instalacyjny.
  Zamiennikiem jest magazyn wersjonowany (`imgwtools[store]`, `imgw store …`).
  Istniejące pliki `.db` nie są usuwane ani migrowane.
- `imgw fetch hydro|meteo -o` zapisuje pliki w podkatalogach ścieżek serwera IMGW.
- `parse_zip_file` zgłasza uszkodzony ZIP jako `IMGWDataError`.
- `parse_stations_csv` wymaga `kind="hydro"|"meteo"` i zwraca `StationListEntry`.

### Nowe

- Magazyn wersjonowany z planem aktualności, szeregami Parquet, katalogiem stacji
  GeoJSON, PMAXTP per komórka i eksportem CSV; schematy `imgw-store/1`, `imgw-meta/1`,
  `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`.
- Parsery meteo (`parse_meteo_climate_daily`, `parse_meteo_precip_daily`,
  `normalize_archive`), rejestr zbiorów (`datasets`, `archive_files`), katalog komend
  (`run_command`) i projekty (`imgw project …`).
- Publiczny budowniczy magazynu testowego `imgwtools.testing.build_fixture_store`.
- Odczyt offline list stacji (`read_station_list`) i wersji archiwów (`read_archive`,
  `imgw store read`) z weryfikacją SHA-256.

---

## Licencja

Projekt udostępniony na licencji MIT. Szczegóły w pliku `LICENSE`.

---

## Autor

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
