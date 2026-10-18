# IMGWTools - Narzędzie do pobierania danych IMGW

Biblioteka Python i narzędzia do pobierania danych publicznych z Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB). Dane pochodzą z serwisu [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/).

Obsługuje również dane z modeli probabilistycznych opadów maksymalnych (PMAXTP) z serwisu [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

- **Biblioteka Python** - `pip install imgwtools` do integracji z innymi projektami
- **CLI** - `imgw`, komendy generowane z katalogu komend
- **REST API** - FastAPI z dokumentacją OpenAPI/Swagger, trasy generowane z tego samego katalogu
- **Web GUI** - formularze pobierania, wyszukiwarka stacji i mapa interaktywna

Od 3.0.0 wszystkie interfejsy korzystają z jednego katalogu 35 komend (`imgw commands schema`): ta sama nazwa opcji w Pythonie, CLI (`--nazwa-opcji`) i REST (parametr albo pole JSON), ta sama walidacja, jedna koperta wyniku `imgw-result/1` i jeden rejestr kodów błędów (`ERROR_CODES`).

**Obsługiwane dane:**
- Aktualne dane hydrologiczne, meteorologiczne i synoptyczne przez API IMGW
- Historyczne dane archiwalne (ZIP/CSV) — rejestr 13 zbiorów `pl.imgw.*`
- Ostrzeżenia hydrologiczne i meteorologiczne
- Dane PMAXTP (opady maksymalne prawdopodobne)
- Listy stacji (wyszukiwanie) i stany wody stacji hydro ze współrzędnymi

**Kluczowa zasada:** domyślnie serwer niczego nie zapisuje — generuje bezpośrednie linki do serwerów IMGW, a dane bieżące przekazuje na żywo. Dane trafiają na dysk wyłącznie po jawnej decyzji: wskazaniu katalogu `--output`, korzenia magazynu (`--root`, `IMGW_STORE_ROOT`) albo skonfigurowaniu `IMGW_STORE_ROOT` na serwerze.

**Wersjonowany magazyn danych** (opcjonalny, od 3.0.0):
- niezmienne wersje archiwów IMGW 1:1 z sumami SHA-256, nagłówkami HTTP i licencją w sidecarze `*.meta.json`,
- sprawdzanie aktualności bez pobierania (listing + `HEAD`) i plan `imgw-plan/1`,
- szeregi stacji w Parquet, katalog stacji `stations.geojson`, komórki PMAXTP, eksport CSV/JSONL,
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

IMGWTools można używać jako biblioteki w innych projektach Python (np. HydroLOG). Funkcje przyjmują pierwszy obiekt pozycyjnie, a wszystkie dalsze argumenty po nazwie; kod stacji to zawsze tekst `station_code` (9 cyfr).

### Dane PMAXTP (opady maksymalne prawdopodobne)

```python
from imgwtools import fetch_pmaxtp

# Pobierz dane dla Warszawy (method: "POT" — domyślnie — albo "AMP")
result = fetch_pmaxtp(52.23, 21.01, method="POT")

# Opad 15-minutowy z prawdopodobieństwem 50%
precip = result.data.get_precipitation(15, 50)
print(f"Opad 15-min, p=50%: {precip} mm")  # opad [mm] dla t=15 min, p=50%

# Dostępne czasy trwania: 5, 10, 15, 30, 45, 60, 90, 120, 180... minut
# Dostępne prawdopodobieństwa: 1, 2, 5, 10, 20, 50... %
```

### Dane bieżące

```python
from imgwtools import fetch_hydro_current, fetch_meteo_current, fetch_synop, fetch_warnings

# Wszystkie stacje hydrologiczne albo jedna stacja (station = kod 9 cyfr)
stations = fetch_hydro_current()
print(f"Liczba stacji: {len(stations)}")
data = fetch_hydro_current(station="150160180")
print(f"{data[0].station_name}: {data[0].water_level_cm} cm")

# Stacje meteorologiczne i synoptyczne
meteo = fetch_meteo_current()
warszawa = fetch_synop(station_name="Warszawa")
print(f"Temperatura: {warszawa[0].temperature_c}°C")

# Ostrzeżenia: kind="hydro" | "meteo"; brak = obie rodziny
for warning in fetch_warnings(kind="hydro"):
    print(warning.kind, warning.event, warning.level, warning.valid_to)
```

### Stacje

```python
from imgwtools import fetch_hydro_states, find_stations

# Wyszukiwanie na listach stacji IMGW (bez rozróżniania wielkości liter i polskich znaków)
for station in find_stations(kind="hydro", query="wisla")[:5]:
    print(station.station_code, station.name, station.river)

# Stany wody stacji hydro ze współrzędnymi (hydro-back.imgw.pl)
states = fetch_hydro_states()
alarmed = [s for s in states if s.water_state == "alarm"]
for s in alarmed:
    print(f"{s.name}: {s.latitude}, {s.longitude}")
```

### Pobieranie danych archiwalnych

```python
from imgwtools import archive_files, datasets, download_archives, download_hydro_data, parse_zip_file

# Rejestr zbiorów: klucz (pl.imgw.hydro_daily), slug (hydro_daily) albo alias (hydro/dobowe)
for dataset in datasets(kind="hydro"):
    print(dataset.key, dataset.legacy_alias, dataset.first_year)

# URL-e plików bez pobierania; years: 2023 | "2020-2023" | "2020,2022" | [2020, "2022-2023"]
for file in archive_files("hydro/dobowe", years=2022, months=[1, 2]):
    print(file.server_path, file.url)

# Pobranie do katalogu w układzie ścieżek serwera IMGW (zapis przez .part i os.replace)
report = download_archives("hydro/miesieczne", years=2023, output="dane")
for item in report.items:
    print(item.slot, item.status, item.path)

# Jedno archiwum jako bajty (DownloadResult) i parser hydro
result = download_hydro_data("miesieczne", 2023)
print(result.url, result.etag, result.last_modified, result.content_length)
for station, record in parse_zip_file(result.data, "miesieczne"):
    print(station.station_code, record.hydro_year, record.hydro_month, record.flow_m3s)
    break
```

### Magazyn wersjonowany (wymaga `imgwtools[store]` dla Parquet)

```python
from imgwtools import (
    build_catalog,
    check_store,
    current_version,
    export_archive,
    export_series,
    init_store,
    read_series,
    read_station_list,
    select_series,
    summarize_series,
    sync_store,
)

store = init_store("/dane/imgw")  # jawny korzeń; brak domyślnego ./data

# 1. Sprawdź aktualność bez pobierania archiwów (listing + HEAD); plan zapisany poza magazynem
plan = check_store(store, datasets=["pl.imgw.hydro_monthly"], years="2022-2023", plan="plan.json")

# 2. Pobierz nowe/brakujące pliki według planu i zbuduj szeregi Parquet (series=True)
report = sync_store(store, plan="plan.json")

# 3. Pokrycie i odczyt bieżącej wersji szeregu (offline; dataset = klucz, slug albo alias)
for coverage in summarize_series(root=store, dataset="hydro/miesieczne", stations=["152210170"]):
    print(coverage.variable, coverage.first, coverage.last, coverage.gaps)
for record in read_series(root=store, dataset="hydro/miesieczne", station="152210170",
                          variables=["Q_mean"]):
    q = record.measurements["Q_mean"]
    print(record.date, q.value, q.flag)  # flag: value|missing|no_phenomenon|accumulated

# 4. Wybór wersji szeregu dla zestawu stacji (wejście zadań projektu)
selection = select_series(store, dataset="pl.imgw.hydro_monthly", stations=["152210170"], years=2023)

# 5. Eksport CSV z jednostkami i atrybucją IMGW-PIB (bez path: iterator linii)
export_series(root=store, dataset="pl.imgw.hydro_monthly", station="152210170",
              variables=["Q_mean"], path="q.csv")

# 6. Rekordy jednej zapisanej wersji archiwum (slot = archive:<klucz>:<plik>, SHA-256 weryfikowane)
archive = current_version(store, slot="archive:pl.imgw.hydro_monthly:2023/mies_2023.zip")
for line in export_archive(archive.version, format="jsonl"):
    print(line, end="")
    break

# 7. Katalog stations.geojson i zapisane listy stacji (jeden typ StationListEntry)
build_catalog(store)
for station in read_station_list(store, kind="meteo")[:3]:
    print(station.station_code, station.name, station.short_code)
```

Do testów offline służy `imgwtools.testing.build_fixture_store(root)` — buduje mały magazyn z nagranych odpowiedzi, bez internetu (fikcyjne stacje, np. `149190310`).

### Katalog komend

Każdą komendę CLI i trasę REST można wywołać z Pythona tymi samymi opcjami; wynik to `CommandResult` (koperta `imgw-result/1`), a komendy listowe zwracają stronę `Page` (`items`, `total`, `limit`, `offset`).

```python
from imgwtools import command_schema, run_command

result = run_command("stations find", options={"kind": "hydro", "query": "wisla", "limit": 5})
print(result.status, result.result.total, [s.name for s in result.result.items])
print(result.to_json())  # słownik koperty JSON, taki jak stdout CLI i ciało REST

schema = command_schema("store sync")  # JSON Schema opcji + x-imgw (funkcja, CLI, REST, reguły)
print(schema["x-imgw"]["rest"]["path"])
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

Każdy `IMGWError` ma `code` z zamkniętego rejestru `ERROR_CODES` i `details` (np. nazwę błędnej opcji); ten sam kod daje kod wyjścia CLI i status HTTP.

```python
from imgwtools import ERROR_CODES, IMGWConnectionError, IMGWError, IMGWValidationError, fetch_pmaxtp

try:
    result = fetch_pmaxtp(40.0, 21.01)
except IMGWValidationError as e:
    print(f"Błąd walidacji: {e}", e.code, e.details)  # validation_error {'option': 'latitude', ...}
except IMGWConnectionError as e:
    print(f"Błąd połączenia: {e}")  # code source_unavailable: timeout, błąd sieci, HTTP spoza 2xx
except IMGWError as e:
    spec = ERROR_CODES[e.code]
    print(spec.title, spec.exit_code, spec.http_status)
```

| Kod | Znaczenie | CLI | HTTP |
|---|---|---|---|
| `validation_error` | Nieprawidłowe dane wejściowe | 2 | 400 |
| `not_found` | Nie znaleziono | 3 | 404 |
| `conflict` | Konflikt stanu | 4 | 409 |
| `source_unavailable` | Źródło IMGW niedostępne | 5 | 502 |
| `missing_dependency` | Brak opcjonalnej zależności | 6 | 503 |
| `data_error` | Niepoprawne dane | 7 | 500 |
| `store_unavailable` | Magazyn niedostępny | 8 | 503 |
| `io_error` | Błąd systemu plików | 9 | 500 |
| `cancelled` | Operację anulowano | 130 | — |
| `forbidden` | Brak uprawnień do zapisu | — | 403 |
| `method_not_allowed` | Niedozwolona metoda HTTP | — | 405 |
| `internal_error` | Błąd wewnętrzny | 1 | 500 |

---

## Szybki start (CLI)

```bash
# Uruchom serwer API
imgw server --reload

# Rejestr zbiorów i URL-e plików (bez pobierania)
imgw datasets list -k hydro
imgw datasets files -d hydro/dobowe -y 2023 -m 1

# Pobierz archiwa do katalogu (układ ścieżek serwera IMGW)
imgw datasets download -d hydro/miesieczne -y 2023 -o dane
imgw datasets download -d meteo/miesieczne/synop -y 2020-2023 -o dane

# Stacje, dane bieżące i PMAXTP
imgw stations find -k hydro -q wisla --limit 5
imgw current hydro -s 150160180
imgw current warnings -k meteo
imgw pmaxtp fetch --lat 52.23 --lon 21.01 --method AMP

# Magazyn wersjonowany (korzeń: --root albo IMGW_STORE_ROOT)
export IMGW_STORE_ROOT=/dane/imgw
imgw store init
imgw store check -d pl.imgw.hydro_monthly -y 2022-2023 --plan plan.json
imgw store sync --plan plan.json
imgw store catalog                                    # stations.geojson
imgw store scan -k series
imgw store export --version archives/versions/<ścieżka>/<wersja> --format jsonl | head
imgw series summary -d hydro/miesieczne -s 152210170
imgw series export -d hydro/miesieczne -s 152210170 --variables Q_mean > q.csv
imgw pmaxtp sync --lat 52.23 --lon 21.01
imgw project init --project-dir ./projekt --store-dir /dane/imgw

# Plan bez zapisu i bez pobierania; opis opcji komendy
imgw store sync -d pl.imgw.hydro_monthly -y 2024 --check
imgw store sync --schema
```

Komendy katalogu (pełna lista: `imgw commands schema`):

| Komenda | Funkcja Pythona | `--check` | REST |
|---|---|---|---|
| `imgw datasets list` | `datasets` | — | `GET /api/v1/datasets/list` |
| `imgw datasets files` | `archive_files` | — | `GET /api/v1/datasets/files` |
| `imgw datasets download` | `download_archives` | `check_command` | — (lokalna) |
| `imgw stations find` | `find_stations` | `check_command` | `GET /api/v1/stations/find` |
| `imgw current hydro` | `fetch_hydro_current` | `check_command` | `GET /api/v1/current/hydro` |
| `imgw current meteo` | `fetch_meteo_current` | `check_command` | `GET /api/v1/current/meteo` |
| `imgw current synop` | `fetch_synop` | `check_command` | `GET /api/v1/current/synop` |
| `imgw current warnings` | `fetch_warnings` | `check_command` | `GET /api/v1/current/warnings` |
| `imgw current hydro-states` | `fetch_hydro_states` | `check_command` | `GET /api/v1/current/hydro-states` |
| `imgw pmaxtp fetch` | `fetch_pmaxtp` | `check_command` | `GET /api/v1/pmaxtp/fetch` |
| `imgw pmaxtp url` | `build_pmaxtp_url` | — | `GET /api/v1/pmaxtp/url` |
| `imgw pmaxtp check` | `check_pmaxtp` | sama | `GET /api/v1/pmaxtp/check` |
| `imgw pmaxtp sync` | `sync_pmaxtp` | `check_pmaxtp` | `POST /api/v1/pmaxtp/sync` |
| `imgw pmaxtp read` | `read_pmaxtp` | — | `GET /api/v1/pmaxtp/read` |
| `imgw store init` | `init_store` | `check_command` | — (lokalna) |
| `imgw store info` | `store_info` | — | `GET /api/v1/store/info` |
| `imgw store scan` | `iter_store` | — | `GET /api/v1/store/scan` |
| `imgw store check` | `check_store` | sama | `GET /api/v1/store/check` |
| `imgw store sync` | `sync_store` | `check_store` | `POST /api/v1/store/sync` |
| `imgw store catalog` | `build_catalog` | `check_catalog` | `POST /api/v1/store/catalog` |
| `imgw store export` | `export_archive` | `check_command` | `GET /api/v1/store/export` |
| `imgw series build` | `build_series` | `check_series` | `POST /api/v1/series/build` |
| `imgw series select` | `select_series` | — | `GET /api/v1/series/select` |
| `imgw series read` | `read_series` | — | `GET /api/v1/series/read` |
| `imgw series summary` | `summarize_series` | — | `GET /api/v1/series/summary` |
| `imgw series export` | `export_series` | `check_command` | `GET /api/v1/series/export` |
| `imgw project init` | `init_project` | `check_command` | — (lokalna) |
| `imgw project add` | `add_project_task` | `check_command` | — (lokalna) |
| `imgw project remove` | `remove_project_task` | `check_command` | — (lokalna) |
| `imgw project set-store` | `set_project_store` | `check_command` | — (lokalna) |
| `imgw project download` | `download_project` | `check_project` | — (lokalna) |
| `imgw project check` | `check_project` | sama | — (lokalna) |
| `imgw project status` | `get_project_status` | — | — (lokalna) |
| `imgw project verify` | `verify_project` | — | — (lokalna) |
| `imgw commands schema` | `command_schema` | — | `GET /api/v1/commands/schema` |

Poza katalogiem: `imgw version`, `imgw server` i `imgw admin keys|create|revoke|delete|stats`.

**Opcje.** Flaga = `--` + nazwa opcji z `-` zamiast `_`; skróty: `-d` zbiór/zbiory, `-y` roczniki, `-m` miesiące, `-s` stacja/stacje, `-k` rodzaj, `-q` fraza, `-o` katalog wyjściowy, `-r` korzeń, `-f` format, `-p` ścieżka pliku; `--lat`/`--lon` to aliasy `--latitude`/`--longitude`. Listy: wartości po przecinku albo powtórzona flaga. Komendy listowe mają `--limit` i `--offset`. `--check` (tylko w komendach z kolumną `--check`) wypisuje plan bez zapisu i bez pobierania danych, `--schema` — opis opcji komendy bez jej uruchamiania.

**Wyjście.** stdout to jedna linia JSON — koperta `imgw-result/1` (`schema`, `command`, `check`, `status`, `result`, `notices`); ścieżki w magazynie są względne do korzenia. `store export` i `series export` bez `--path` wypisują strumień CSV/JSONL. Postęp i komunikaty (każdy jednakowy raz, np. `license_terms`) trafiają na stderr, a błąd — jako JSON `{"code", "detail", "details"}` w ostatniej linii stderr (stdout pusty). Kody wyjścia:

| Kod | Znaczenie |
|---|---|
| `0` | `status` `ok` |
| `10` / `11` | `status` `partial` / `failed` (np. pozycja `failed` lub `stale_plan` w `store sync`) — pełna koperta wypisana |
| `2`–`9`, `1` | błąd według tabeli kodów (`validation_error` 2 … `io_error` 9, `internal_error` 1) |
| `130` | anulowanie Ctrl+C |

Punkt PMAXTP w ramce współrzędnych Polski, ale poza siatką IMGW (np. Kaliningrad, Lwów, Bałtyk) daje `validation_error` (CLI 2, REST 400). `imgw project set-store` przyjmuje nowy pusty magazyn z ostrzeżeniem `pins_not_in_store`; następne `imgw project download` odtwarza przypięte pliki tylko z identycznym SHA-256, inaczej zgłasza błąd zadania.

### REST API

Po uruchomieniu serwera (`imgw server`):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- `GET /api/v1` — wersja i lista tras katalogu, `GET /health` — stan serwera

Trasy powstają z katalogu: `/api/v1/<grupa>/<komenda>` (tabela wyżej; komendy lokalne — `datasets download`, `store init`, `project …` — nie mają tras). GET przyjmuje opcje w query (listy po przecinku albo powtórzony parametr), POST — w ciele JSON; `?check=true` przy POST zwraca plan bez zapisu. Odpowiedź to ta sama koperta `imgw-result/1` co w CLI; komendy listowe mają `limit` (domyślnie i najwyżej `IMGW_API_MAX_LIMIT`, 1000) i `offset`. Błędy: `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`).

```bash
# Dane bieżące i URL-e archiwów
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"

# Magazyn (wymaga IMGW_STORE_ROOT na serwerze; inaczej 503 store_unavailable)
curl http://localhost:8000/api/v1/store/info
curl "http://localhost:8000/api/v1/store/scan?kind=series"
curl "http://localhost:8000/api/v1/series/summary?dataset=pl.imgw.hydro_monthly&stations=152210170"

# Zapis (IMGW_STORE_WRITES_ENABLED=true, IMGW_STORE_WRITE_TOKEN i nagłówek X-API-Key)
curl -X POST "http://localhost:8000/api/v1/store/sync?check=true" \
    -H "X-API-Key: $IMGW_STORE_WRITE_TOKEN" -H "Content-Type: application/json" \
    -d '{"datasets": ["pl.imgw.hydro_monthly"], "years": "2024"}'
```

Trasy magazynu działają tylko na serwerowym, absolutnym `IMGW_STORE_ROOT` (klient nie podaje korzenia). Operacje zapisujące wymagają dodatkowo `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` i nagłówka `X-API-Key` z tym tokenem — domyślnie są wyłączone (403 `forbidden`). CSV współrzędnych użytkownika (`user_locations`) tylko z katalogu `IMGW_USER_LOCATIONS_DIR`.

### Web GUI

Po uruchomieniu serwera dostępne pod http://localhost:8000:
- `/` - Dashboard
- `/download` - Wybór danych do pobrania; `/download/archives` - linki do archiwów zbiorów z rejestru, `/download/pmaxtp` - tabele PMAXTP (eksport CSV/XLSX/JSON)
- `/stations` - Wyszukiwarka stacji (listy IMGW, stronicowanie)
- `/map` - Mapa stacji hydro w kolorach stanu wody (`GET /api/v1/current/hydro-states`)

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
- **dobowe/terminowe synop**: pliki per stacja (`{folder}_{kod}_s.zip`) — rejestr ich nie generuje (`validation_error`, `details.reason=per_station`; użyj `meteo/miesieczne/synop`)
- **terminowe opad**: zbiór nie istnieje na serwerze IMGW (`details.reason=not_published`)
- Siatki folderów różnią się na starcie: klimat od `1951_1955`, opad od `1950_1955`, synop od `1960_1965` (struktura zweryfikowana na serwerach IMGW, 2026-07-05)

### Źródła danych stacji
- **Lista stacji hydro**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Lista stacji meteo**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Współrzędne dla mapy**: API `hydro-back.imgw.pl/map/stations/hydrologic` (900+ stacji ze stanem wody)

---

## Struktura projektu

```
src/imgwtools/
├── api/          # REST API (FastAPI): routes/commands.py (trasy z katalogu), errors.py (problem+json)
├── cli/          # CLI: _dispatch.py (komendy z katalogu), admin.py, main.py
├── _parsing/     # Parsery archiwów hydro/meteo i list stacji (publicznie: imgwtools.parsers)
├── store/        # Magazyn wersjonowany: writer, sync, series, catalog, pmaxtp, reader, export
├── datasets.py   # Rejestr 13 zbiorów pl.imgw.* i generator plików archiwów
├── commands.py   # Katalog 35 komend wspólny dla Pythona, CLI, REST i integracji
├── fetch.py      # Dane bieżące, PMAXTP, pobieranie archiwów
├── stations.py   # find_stations
├── urls.py       # Stałe URL IMGW, build_pmaxtp_url, build_api_url
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

Wersje są niezmienne i tylko dopisywane: brak nadpisywania, dowiązań i ścieżki `latest`. Bieżącą wersję wylicza `current_version(root, slot=...)`; sloty: `archive:<klucz>:<plik>` (np. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`), `series:<klucz>`, `catalog:pl.imgw.stations`, `pmaxtp:pl.imgw.pmaxtp:<METODA>/<indX>_<indY>`. Każdy plik główny ma sidecar `*.meta.json` (`imgw-meta/1`) z SHA-256, rozmiarem, żądaniem, nagłówkami HTTP i licencją IMGW-PIB.

### Zbiory

| Klucz | Alias | Zawartość |
|-------|-------|-----------|
| `pl.imgw.hydro_daily` | `hydro/dobowe` | Hydro dobowe: H [cm], Q [m3/s], T [°C] |
| `pl.imgw.hydro_monthly` | `hydro/miesieczne` | Hydro miesięczne: H/Q/T × min/mean/max |
| `pl.imgw.hydro_semiannual` | `hydro/polroczne_i_roczne` | Hydro półroczne i roczne: H/Q/T × min/mean/max z datami ekstremów |
| `pl.imgw.meteo_climate_daily` | `meteo/dobowe/klimat` | Meteo klimat dobowe: Tmax, Tmin, Tmean, Tground, P, pokrywa śnieżna |
| `pl.imgw.meteo_precip_daily` | `meteo/dobowe/opad` | Meteo opad dobowy: P, pokrywa i świeży śnieg |
| `pl.imgw.hydro_stations`, `pl.imgw.meteo_stations` | — | Listy stacji (CSV) — wejście katalogu `stations.geojson` |
| `pl.imgw.pmaxtp` | — | PMAXTP per komórka siatki (`POT`, `AMP`) |
| `pl.imgw.hydro_phenomena` | — | Zjawiska hydrologiczne dobowe (tylko pobieranie) |
| `pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly` | `meteo/miesieczne/klimat\|opad\|synop` | Meteo miesięczne (tylko pobieranie) |
| `pl.imgw.meteo_climate_terms` | `meteo/terminowe/klimat` | Meteo klimat terminowe (tylko pobieranie) |

Zbiory „tylko pobieranie” obsługują `datasets files|download`, ale nie magazyn. Dane bieżące, ostrzeżenia i `fetch_pmaxtp` pozostają zapytaniami na żywo, bez magazynu.

### Schematy

`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`, `imgw-observation/1` (oraz rozszerzenie `imgw-pmaxtp/1`) mają własne liczniki wersji, niezależne od wersji pakietu; koperta wyniku komend to `imgw-result/1`. W ramach `/1` dochodzą tylko pola opcjonalne; zmiana niezgodna oznacza `/2`. Nieznana wersja jest raportowana (`store_info(...).supported is False`), a nie zgadywana. Dziedziny `/1` są otwarte na kolejnych dostawców (klucz `<kraj>.<dostawca>.<slug>`, kod stacji IMGW albo WIGOS; ADR-003).

### Integracje

- **Archiwista** czyta magazyn wyłącznie publicznym API odczytu (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`); IMGWTools jest jedynym piszącym, a w magazynie nie ma plików Archiwisty.
- **Retman** uruchamia działania jako handler przez publiczny katalog komend (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`) — te same opcje, walidacja, koperta i kody błędów co w CLI i REST.

Poprzedni opcjonalny cache SQLite został usunięty w 3.0.0 bez migracji — zob. `docs/CHANGELOG.md`.

---

## Testy

Projekt zawiera testy jednostkowe i kontraktowe publicznego API, CLI, REST i Web GUI. Wszystkie działają offline: sieć jest mockowana (`respx`) albo odtwarzana z nagrań w `tests/fixtures/store/`.

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
├── fixtures/export_golden/  # Złote pliki eksportu archiwów (CSV z CRLF, JSONL)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations.py, test_urls.py
│   ├── test_datasets.py, test_coverage.py, test_download_archives.py
│   ├── test_store_*.py, test_series_export.py          # magazyn: writer, sync, series, catalog, pmaxtp, reader, export
│   ├── test_fixture_builder.py                         # imgwtools.testing
│   ├── test_commands.py, test_command_schema.py        # katalog komend, command_schema
│   ├── test_project.py, test_exceptions.py             # imgw-project/1, rejestr kodów błędów
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py   # CLI, REST i Web GUI
│   ├── test_reference_data.py                          # python -m imgwtools.reference_data
│   └── test_public_store_api.py                        # kontrakt eksportów publicznych
└── contract/                # kontrakt magazynu, zgodność Python = CLI = REST, projekt
```

**Łącznie: 1377 testów** (`pytest --collect-only`, 2026-10-18).

---

## Dokumentacja

- `CLAUDE.md` - Instrukcje dla Claude Code
- `docs/CHANGELOG.md` - Historia zmian (w tym BREAKING 3.0.0)
- `docs/DECISIONS.md` - Rejestr decyzji (ADR-001: magazyn wersjonowany, ADR-002: jeden katalog komend, ADR-003: dostawca ČHMÚ)
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

Pełna lista z tabelami migracji: [`docs/CHANGELOG.md`](docs/CHANGELOG.md) (także wcześniejsze wydania).

### Zmiany łamiące kompatybilność

- CLI: grupy `datasets`, `stations`, `current` i `pmaxtp` zastępują `imgw fetch …` i `imgw list …`
  (np. `imgw fetch hydro -i dobowe -y 2023` → `imgw datasets download -d hydro/dobowe -y 2023`);
  stdout to koperta `imgw-result/1`, błąd to JSON na stderr, kody wyjścia według rejestru błędów.
- REST: trasy katalogu `/api/v1/<grupa>/<komenda>` zastępują `/api/v1/hydro|meteo|download|pmaxtp/*`
  i `/map/stations`; błędy w `application/problem+json`.
- Python: `station_id` → `station` (argument) i `station_code` (pole); `list_*_stations` →
  `find_stations`, `get_hydro_stations_with_coords` → `fetch_hydro_states`,
  `build_hydro_url`/`build_meteo_url` → `archive_files`; `download_hydro_data`,
  `download_meteo_data` zwracają `DownloadResult` zamiast `bytes`.
- Usunięty cache SQLite: pakiet `imgwtools.db`, komendy `imgw db`, endpoint
  `GET /api/v1/hydro/data`, jego ustawienia i dodatek instalacyjny. Zamiennikiem jest
  magazyn wersjonowany (`imgwtools[store]`, `imgw store …`); pliki `.db` nie są usuwane ani migrowane.
- `parse_zip_file` zgłasza uszkodzony ZIP jako `IMGWDataError`; `parse_stations_csv` wymaga
  `kind="hydro"|"meteo"` i zwraca `StationListEntry`.

### Nowe

- Magazyn wersjonowany z planem aktualności, szeregami Parquet, katalogiem stacji
  GeoJSON, PMAXTP per komórka i eksportem CSV/JSONL.
- Jeden katalog 35 komend dla Pythona, CLI i REST (`command_schema`, `run_command`),
  koperta `imgw-result/1` ze stronicowaniem, rejestr kodów błędów `ERROR_CODES`.
- `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`, `download_archives`,
  `select_series`, `summarize_series`, `export_archive`; rejestr 13 zbiorów z aliasami.
- Projekty `imgw-project/1` z przypięciem wersji po SHA-256 i publiczny budowniczy
  magazynu testowego `imgwtools.testing.build_fixture_store`.

---

## Licencja

Projekt udostępniony na licencji MIT. Szczegóły w pliku `LICENSE`.

---

## Autor

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
