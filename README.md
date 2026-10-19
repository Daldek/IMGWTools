# IMGWTools - Narzędzie do pobierania danych IMGW i ČHMÚ

Biblioteka Python i narzędzia do pobierania danych publicznych z Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB), a od 3.0.0 także z Czeskiego Instytutu Hydrometeorologicznego (Český hydrometeorologický ústav, ČHMÚ). Dane pochodzą z serwisów [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/) i [ČHMÚ Open Data](https://opendata.chmi.cz/).

Obsługuje również dane z modeli probabilistycznych opadów maksymalnych (PMAXTP) z serwisu [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

- **Biblioteka Python** - `pip install imgwtools` do integracji z innymi projektami
- **CLI** - `imgw`, komendy generowane z katalogu komend
- **REST API** - FastAPI z dokumentacją OpenAPI/Swagger, trasy generowane z tego samego katalogu
- **Serwer MCP** - `imgw mcp` (dodatek `imgwtools[mcp]`) i punkt `/mcp` serwera REST: komendy katalogu jako narzędzia dla agentów AI, domyślnie bez zapisu
- **Web GUI** - formularze pobierania, wyszukiwarka stacji i mapa interaktywna (dane IMGW-PIB)

Od 3.0.0 wszystkie interfejsy korzystają z jednego katalogu 37 komend (`imgw commands schema`): ta sama nazwa opcji w Pythonie, CLI (`--nazwa-opcji`), REST (parametr albo pole JSON) i MCP (argument narzędzia), ta sama walidacja, jedna koperta wyniku `imgw-result/1` i jeden rejestr kodów błędów (`ERROR_CODES`). Teksty są domyślnie po polsku; opisy katalogu mają wariant angielski (`IMGW_LANG=en`, `--lang en`, `Accept-Language: en`). Przewodnik dla agentów AI: [`AGENTS.md`](AGENTS.md) i [`llms.txt`](llms.txt).

**Obsługiwane dane:**
- Aktualne dane hydrologiczne, meteorologiczne i synoptyczne przez API IMGW
- Historyczne dane archiwalne IMGW-PIB (ZIP/CSV) i ČHMÚ (JSON/CSV per stacja) — rejestr 17 zbiorów dwóch dostawców (`pl.imgw.*`, `cz.chmi.*`)
- Ostrzeżenia hydrologiczne i meteorologiczne
- Dane PMAXTP (opady maksymalne prawdopodobne)
- Listy stacji (wyszukiwanie IMGW-PIB i ČHMÚ) i stany wody stacji hydro IMGW ze współrzędnymi

**Kluczowa zasada:** domyślnie serwer niczego nie zapisuje — generuje bezpośrednie linki do serwerów IMGW-PIB i ČHMÚ, a dane bieżące przekazuje na żywo. Dane trafiają na dysk wyłącznie po jawnej decyzji: wskazaniu katalogu `--output`, korzenia magazynu (`--root`, `IMGW_STORE_ROOT`) albo skonfigurowaniu `IMGW_STORE_ROOT` na serwerze.

**Wersjonowany magazyn danych** (opcjonalny, od 3.0.0):
- niezmienne wersje archiwów IMGW-PIB i ČHMÚ 1:1 z sumami SHA-256, nagłówkami HTTP i licencją w sidecarze `*.meta.json`,
- sprawdzanie aktualności bez pobierania (IMGW-PIB: listing + `HEAD`, ČHMÚ: jeden listing katalogu serwera) i plan `imgw-plan/1`,
- szeregi stacji w Parquet, katalogi stacji `stations.geojson` obu dostawców, komórki PMAXTP, eksport CSV/JSONL,
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

# Z serwerem MCP dla agentów AI (imgw mcp; zawiera CLI)
pip install imgwtools[mcp]

# Pełna instalacja (CLI + API + MCP + magazyn + pandas)
pip install imgwtools[full]

# Dla deweloperów (z repozytorium)
git clone https://github.com/Daldek/IMGWTools.git
cd IMGWTools
pip install -e ".[dev]"
```

---

## Użycie jako biblioteka Python

IMGWTools można używać jako biblioteki w innych projektach Python (np. HydroLOG). Funkcje przyjmują pierwszy obiekt pozycyjnie, a wszystkie dalsze argumenty po nazwie; kod stacji to zawsze tekst `station_code` (IMGW-PIB: 9 cyfr, ČHMÚ: identyfikator WIGOS, np. `0-203-1-001000`).

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

# Wyszukiwanie na listach stacji (bez rozróżniania wielkości liter i znaków diakrytycznych);
# provider: "IMGW-PIB" | "CHMI", brak = obaj dostawcy
for station in find_stations(kind="hydro", query="wisla", provider="IMGW-PIB")[:5]:
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

Do testów offline służy `imgwtools.testing.build_fixture_store(root)` — buduje mały magazyn z nagranych odpowiedzi, bez internetu (fikcyjne stacje, np. `149190310`); wariant `variant="complete_pl_cz"` dokłada dane ČHMÚ (stacje `0-203-1-900001`, `0-203-1-900002`, `0-203-0-90001`, `0-203-0-90000000002`, szeregi, katalog i obserwację).

### Dane ČHMÚ (Czechy)

Zbiory ČHMÚ (`cz.chmi.*`) korzystają z tego samego rejestru, magazynu, katalogu komend i kontraktów co IMGW-PIB. Archiwa ČHMÚ są publikowane per stacja, więc każda operacja na nich wymaga listy stacji (`stations`, identyfikatory WIGOS).

```python
from imgwtools import archive_files, build_catalog, check_store, datasets, find_stations, providers, sync_store

# Dostawcy: IMGW-PIB (pl.imgw.*, kody 9-cyfrowe) i CHMI („ČHMÚ”, cz.chmi.*, identyfikatory WIGOS)
for provider in providers():
    print(provider.id, provider.short_name, provider.country, provider.license.id)
print([d.key for d in datasets(provider="CHMI")])  # hydro_daily, meteo_daily, hydro_stations, meteo_stations

# Stacja ČHMÚ na żywo (metadane „now”; zapytanie bez czeskich znaków)
station = find_stations(kind="hydro", query="spindleruv", provider="CHMI")[0]
print(station.station_code, station.name, station.river)  # 0-203-1-001000 Špindlerův Mlýn Labe

# Pliki stacji offline: hydro — JSON na stację i rok, meteo — 4 pliki CSV na stację (bez years)
for file in archive_files("cz.chmi.hydro_daily", stations=[station.station_code], years="2024-2025"):
    print(file.year, file.url)  # …/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2024.json
for file in archive_files("cz.chmi.meteo_daily", stations=["0-203-0-11799"]):
    print(file.param, file.server_path)  # SRA, T, TMA, TMI

# Magazyn (store z przykładu wyżej): jedno GET listingu katalogu serwera zamiast HEAD każdego pliku
plan = check_store(store, datasets=["cz.chmi.hydro_daily"], stations=[station.station_code],
                   years="2024-2026")  # years opcjonalne dla hydro: brak = lata opublikowane
for item in plan.items:
    print(item.archive.year, item.status, item.remote_listed_at, item.error)  # 2026 unverifiable … nieopublikowany
print(plan.requests)  # {'made': 1, 'planned': 4}: HEAD+GET dla dwóch plików missing
report = sync_store(store, plan=plan)  # HEAD przed GET; zmiana od planu → stale_plan; szereg chmi_hydro_daily
build_catalog(store, provider="CHMI")  # stations/versions/chmi_stations/…, katalog: catalog:cz.chmi.stations
```

Odczyt offline — tu na magazynie testowym PL + CZ:

```python
from imgwtools import export_series, read_catalog, read_series, summarize_series
from imgwtools.testing import build_fixture_store

demo = build_fixture_store("/tmp/imgw-demo", variant="complete_pl_cz")  # fikcyjne stacje, bez internetu

# Meteo ČHMÚ: obok wartości i flagi także QUALITY (0–5) i FLAG ČHMÚ dosłownie
for record in read_series(root=demo, dataset="cz.chmi.meteo_daily", station="0-203-0-90001",
                          variables=["P"]):
    p = record.measurements["P"]
    print(record.date, p.value, p.flag, p.quality, p.source_flag)  # 2023-10-22 0.0 value 0 T (ślad opadu)

# Pokrycie per stacja: rok bez opublikowanego pliku (2005) jest nieznany, nie jest luką
for coverage in summarize_series(root=demo, dataset="cz.chmi.hydro_daily", stations=["0-203-1-900002"]):
    print(coverage.variable, coverage.first, coverage.last, coverage.gaps)  # Q 2004-01-01 2006-12-31 ()

# CSV: kolumny jakości i flag ČHMÚ, atrybucja ČHMÚ (CC BY 4.0) w pierwszym wierszu danych
lines = list(export_series(root=demo, dataset="cz.chmi.meteo_daily", station="0-203-0-90001",
                           variables=["P"]))
print(lines[0], end="")  # date,year,P [mm],P_flag,P_quality,P_source_flag,attribution_source,attribution_processed

# Katalog stacji ČHMÚ: progi SPA (drought, spa1–spa3, q50) stanu i przepływu
for feature in read_catalog(root=demo, provider="CHMI"):
    print(feature.properties["station_code"], feature.properties.get("thresholds"))
```

Reguły i zachowanie ČHMÚ:

- **Opcje:** `stations` jest wymagane dla `cz.chmi.*` i niedozwolone dla `pl.imgw.*`; `years` — wymagane dla `cz.chmi.hydro_daily` w `archive_files`/`datasets files|download`, opcjonalne w `check_store`/`sync_store` (brak = lata opublikowane w listingu stacji) i niedozwolone dla `cz.chmi.meteo_daily` (pliki obejmują całą historię stacji); `months` i `params` wyłącznie dla IMGW-PIB. Jedno wywołanie `check_store`/`sync_store` dotyczy archiwów krajowych IMGW-PIB albo plików stacji ČHMÚ, nie obu naraz.
- **Aktualność:** `check_store` porównuje czas (co do minuty) i rozmiar z listingu serwera z sygnałem wersji w magazynie (`current`, `newer`, `missing`); rok bez pliku u źródła to `unverifiable` z `error="nieopublikowany"` (nie błąd), a `download_archives` daje dla niego pozycję `not_published`. Dane `now`/`recent`, dane godzinowe, ostrzeżenia ČHMÚ i PMAXTP poza Polską nie są obsługiwane; `current …` i `pmaxtp …` dotyczą wyłącznie IMGW-PIB.
- **Wersje:** ČHMÚ regeneruje pliki masowo. Te same bajty pod nowym `Last-Modified` dają `relabeled` (kopia, jak w IMGW-PIB); inne bajty tej samej treści (JSON hydro i listy stacji bez koperty `zaznamID`/`datumVytvoreni`, forma `chmi-json/1`, pole `content_sha256` sidecara) — `unchanged` bez nowej wersji, z komunikatem `content_unchanged` i obserwacją nowego sygnału w `observations/`, więc następne sprawdzenie daje `current` bez pobierania.
- **Szeregi:** `series.json` ma okresy znane per stacja (`stations[<kod>].periods`); szereg meteo ma kolumny `<V>_quality` i `<V>_source_flag`, a wartości nie są poprawiane według jakości. `series select` przyjmuje tylko lata z okresów szeregu (zakres przez rok nieopublikowany → `validation_error`).
- **Katalog stacji:** osobna wersja katalogu dostawcy (`build_catalog(store, provider="CHMI")`, `imgw store catalog --provider CHMI`), położenie z metadanych `now` i historycznych z kontrolą obrysu Czech; współrzędne mają wartość z publikacji (JSON nie zachowuje końcowych zer zapisu, np. `50.6493690` → `50.649369`).
- **Projekty:** zadanie dotyczy jednego zbioru, więc projekt może łączyć zadania IMGW-PIB i ČHMÚ. Piny zbiorów ČHMÚ z formą kanoniczną (`cz.chmi.hydro_daily` — archiwa, szereg i pliki stacji — oraz listy stacji) odtwarzają się z identycznymi bajtami albo — gdy źródło opublikowało inne bajty tej samej treści — jako `restored_by_content` (stan pinu `content_match`, ostrzeżenie `pin_restored_by_content` z obiema ścieżkami i sumami), a manifest się nie zmienia; piny CSV meteo ČHMÚ i IMGW-PIB — wyłącznie z identycznymi bajtami.
- **Licencja:** CC BY 4.0; sidecary, szeregi, katalog i eksporty niosą atrybucję ČHMÚ (postaci przetworzone — z oznaczeniem zmian), a komunikat `license_terms` podaje warunki licencji.

### Katalog komend

Każdą komendę CLI i trasę REST można wywołać z Pythona tymi samymi opcjami; wynik to `CommandResult` (koperta `imgw-result/1`), a komendy listowe zwracają stronę `Page` (`items`, `total`, `limit`, `offset`).

```python
from imgwtools import command_schema, run_command

result = run_command("stations find", options={"kind": "hydro", "query": "wisla", "limit": 5})
print(result.status, result.result.total, [s.name for s in result.result.items])
print(result.to_json())  # słownik koperty JSON, taki jak stdout CLI i ciało REST

schema = command_schema("store sync")  # JSON Schema opcji + x-imgw (funkcja, CLI, REST, reguły)
print(schema["x-imgw"]["rest"]["path"])
print(schema["x-imgw"]["writes"], schema["x-imgw"]["network"], schema["x-imgw"]["operation_id"])  # add True store_sync
print(command_schema("store sync", lang="en")["description"])  # opisy po angielsku, struktura bez zmian
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
| `source_unavailable` | Źródło danych niedostępne (`detail` nazywa dostawcę i URL) | 5 | 502 |
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

# Dane ČHMÚ (kody stacji WIGOS; -s/--stations wymagane dla cz.chmi.*)
imgw datasets providers
imgw datasets list --provider CHMI
imgw stations find -k hydro -q spindleruv --provider CHMI
imgw datasets files -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2025
imgw datasets download -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2025-2026 -o dane   # 2026: not_published
imgw store check -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2026 --plan plan-cz.json
imgw store sync --plan plan-cz.json                   # + szereg chmi_hydro_daily
imgw store catalog --provider CHMI                    # stations/versions/chmi_stations/…
imgw series read -d cz.chmi.hydro_daily -s 0-203-1-001000 --variables Q --limit 5
imgw store scan --provider CHMI -k observation

# Agenci AI: przewodnik, opisy po angielsku, serwer MCP (dodatek imgwtools[mcp])
imgw commands guide --format llms --lang en
imgw commands schema --command "store sync" --lang en
IMGW_LANG=en imgw store sync --help
imgw mcp                                              # stdio — uruchamia go klient MCP

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
| `imgw datasets providers` | `providers` | — | `GET /api/v1/datasets/providers` |
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
| `imgw commands guide` | `agent_guide` | `check_command` | `GET /api/v1/commands/guide` |

Poza katalogiem: `imgw version`, `imgw server`, `imgw mcp` i `imgw admin keys|create|revoke|delete|stats`.

**Opcje.** Flaga = `--` + nazwa opcji z `-` zamiast `_`; skróty: `-d` zbiór/zbiory, `-y` roczniki, `-m` miesiące, `-s` stacja/stacje, `-k` rodzaj, `-q` fraza, `-o` katalog wyjściowy, `-r` korzeń, `-f` format, `-p` ścieżka pliku; `--lat`/`--lon` to aliasy `--latitude`/`--longitude`. Listy: wartości po przecinku albo powtórzona flaga. Komendy listowe mają `--limit` i `--offset`. `--provider` (`IMGW-PIB` albo `CHMI`) zawęża `datasets list`, `stations find` i `store scan` do jednego dostawcy (brak = obaj) i wybiera katalog w `store catalog` (domyślnie `IMGW-PIB`). `--check` (tylko w komendach z kolumną `--check`) wypisuje plan bez zapisu i bez pobierania danych, `--schema` — opis opcji komendy bez jej uruchamiania. Reguły zależne od zbioru (np. `--stations` dla `cz.chmi.*`) są w `x-imgw.rules` schematu. `IMGW_LANG=en` przełącza pomoc CLI i domyślne `--lang` na angielski (wartość spoza `pl|en` → `validation_error`, kod 2).

**Wyjście.** stdout to jedna linia JSON — koperta `imgw-result/1` (`schema`, `command`, `check`, `status`, `result`, `notices`); ścieżki w magazynie są względne do korzenia. `store export` i `series export` bez `--path` wypisują strumień CSV/JSONL. Postęp i komunikaty (każdy jednakowy raz, np. `license_terms`) trafiają na stderr, a błąd — jako JSON `{"code", "detail", "details"}` w ostatniej linii stderr (stdout pusty). Kody wyjścia:

| Kod | Znaczenie |
|---|---|
| `0` | `status` `ok` |
| `10` / `11` | `status` `partial` / `failed` (np. pozycja `failed` lub `stale_plan` w `store sync`) — pełna koperta wypisana |
| `2`–`9`, `1` | błąd według tabeli kodów (`validation_error` 2 … `io_error` 9, `internal_error` 1) |
| `130` | anulowanie Ctrl+C |

Punkt PMAXTP w ramce współrzędnych Polski, ale poza siatką IMGW (np. Kaliningrad, Lwów, Bałtyk) daje `validation_error` (CLI 2, REST 400). `imgw project set-store` przyjmuje nowy pusty magazyn z ostrzeżeniem `pins_not_in_store`; następne `imgw project download` odtwarza przypięte pliki z identycznym SHA-256 — a pliki ČHMÚ z formą kanoniczną także z tą samą treścią (`restored_by_content`, ostrzeżenie `pin_restored_by_content`) — inaczej zgłasza błąd zadania.

### REST API

Po uruchomieniu serwera (`imgw server`):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- `GET /api/v1` — wersja i lista tras katalogu, `GET /health` — stan serwera, `GET /llms.txt` — przewodnik dla agentów (llms.txt) w języku z `Accept-Language`
- `/mcp` — serwer MCP (Streamable HTTP), gdy `IMGW_MCP_ENABLED=true` (sekcja „Agenci AI”)

Trasy powstają z katalogu: `/api/v1/<grupa>/<komenda>` (tabela wyżej; komendy lokalne — `datasets download`, `store init`, `project …` — nie mają tras). GET przyjmuje opcje w query (listy po przecinku albo powtórzony parametr), POST — w ciele JSON; `?check=true` przy POST zwraca plan bez zapisu. Odpowiedź to ta sama koperta `imgw-result/1` co w CLI; komendy listowe mają `limit` (domyślnie i najwyżej `IMGW_API_MAX_LIMIT`, 1000) i `offset`. Błędy: `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`). Język: `commands schema` i `commands guide` biorą `lang` z zapytania, a bez niego z nagłówka `Accept-Language` (domyślnie `pl`); `title` problem+json idzie za nagłówkiem, `detail` jest po polsku, odpowiedzi mają `Content-Language` i `Vary: Accept-Language`.

```bash
# Dane bieżące i URL-e archiwów
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
curl "http://localhost:8000/api/v1/datasets/files?dataset=cz.chmi.hydro_daily&stations=0-203-1-001000&years=2024"

# Katalog komend i przewodnik po angielsku
curl -H "Accept-Language: en" "http://localhost:8000/api/v1/commands/schema?command=store%20sync"
curl -H "Accept-Language: en" http://localhost:8000/llms.txt

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
- `/stations` - Wyszukiwarka stacji (listy IMGW-PIB, stronicowanie)
- `/map` - Mapa stacji hydro w kolorach stanu wody (`GET /api/v1/current/hydro-states`)

Każda stacja ma link do oficjalnej strony IMGW: `https://hydro.imgw.pl/#/station/{type}/{id}`

Web GUI obsługuje wyłącznie zbiory IMGW-PIB (formularz bez pola stacji nie obsłuży plików ČHMÚ per stacja); dane ČHMÚ są dostępne w Pythonie, CLI, REST i MCP.

---

## Agenci AI: AGENTS.md, llms.txt i serwer MCP

Agent (asystent w edytorze, aplikacja czatu, skrypt z modelem językowym) poznaje IMGWTools z jednego źródła zgodnego z kodem:

- [`AGENTS.md`](AGENTS.md) — przewodnik: zasada „sprawdź → uruchom → przeczytaj”, odwzorowanie Python/CLI/REST/MCP, koperta i statusy, kody błędów, zbiory obu dostawców z regułami opcji, tabele komend ze skutkami, typowe przepływy (m.in. „opady dobowe ze stacji Poznań”, stacja ČHMÚ, projekt) i lista „czego nie robić”;
- [`llms.txt`](llms.txt) — skrót według llms.txt v2 z odnośnikami do dokumentacji; ten sam plik serwuje `GET /llms.txt`;
- `imgw commands guide [--format agents|llms] [--lang pl|en] [--path PLIK]` albo `agent_guide()` w Pythonie — oba pliki wygenerowane na bieżąco, także po angielsku; `GET /api/v1/commands/guide`.

`AGENTS.md` i `llms.txt` to pliki pochodne katalogu komend, rejestrów i szablonów `src/imgwtools/_data/agents/` — nie edytuje się ich ręcznie (zasady pracy nad kodem: `CLAUDE.md`).

**Język.** Domyślnie wszystko jest po polsku. Teksty katalogu (opisy komend, pomoc opcji, reguły, grupy, tytuły błędów i zbiorów) mają wariant angielski: `command_schema(lang="en")`, `--lang en`, `IMGW_LANG=en` (CLI i `imgw mcp`), `Accept-Language: en` (REST). `detail` błędów i treść komunikatów pozostają polskie; agent decyduje po `code`, `status` i polach JSON. Język nie zmienia kontraktu.

**Skutki komend.** `x-imgw.writes` (`none`, `add` — tylko nowe pliki i wersje, `replace` — może zastąpić plik użytkownika), `x-imgw.network` i `x-imgw-writes` opcji (np. `path`, `plan` w `store check`) mówią, co komenda zrobi, zanim zostanie uruchomiona; każda komenda zapisująca ma plan (`--check`, `?check=true`, `check: true`).

### Serwer MCP

`imgw mcp` (dodatek `imgwtools[mcp]`: CLI + oficjalne SDK `mcp>=2.3,<3`) to serwer MCP na standardowym wejściu i wyjściu. Każda komenda katalogu jest narzędziem o nazwie `x-imgw.operation_id` (`store_sync`, `current_hydro_states`, …) ze schematem wejścia z `command_schema`; argumenty to opcje komendy, a jedynym walidatorem jest `validate_command`. Konfiguracja klienta (np. `mcpServers` w pliku ustawień):

```json
{
  "mcpServers": {
    "imgwtools": {
      "command": "imgw",
      "args": ["mcp"],
      "env": {"IMGW_STORE_ROOT": "/dane/imgw"}
    }
  }
}
```

- Bez instalacji w systemie: `"command": "uvx", "args": ["--from", "imgwtools[mcp]", "imgw", "mcp"]`.
- Zapis: `"args": ["mcp", "--allow-writes"]` (albo `IMGW_MCP_ALLOW_WRITES=true`). Bez tej flagi serwer nie zapisuje: komendy zapisujące mają argument `check` stały `true` i zwracają plan `imgw-plan/1`, a opcje zapisujące są niedostępne (próba → `forbidden`, `details.reason="writes_disabled"`). Z flagą `check` jest domyślnie `true`, a zapis wymaga `check: false` — o zapisie decyduje użytkownik w konfiguracji, nie model.
- Po angielsku: `"args": ["mcp", "--lang", "en"]` (domyślnie `IMGW_LANG`).
- `root` jak w CLI: argument narzędzia albo `IMGW_STORE_ROOT` serwera; ścieżki względne liczą się od katalogu roboczego serwera (podanego w instrukcjach serwera).

Wynik narzędzia: `structuredContent` = koperta `imgw-result/1` (te same bajty co stdout CLI, także jako tekst), `isError=false` również dla `partial` i `failed`. Błąd: `isError=true` i `{"code", "title", "detail", "details"}` (`code`, `detail` i `details` jak w linii błędu CLI, `title` w języku serwera). Komendy listowe bez `limit` zwracają stronę 50 pozycji (najwyżej `IMGW_API_MAX_LIMIT`); strumienie (`store export`, `series export`, `commands guide` bez `path`) — tekst do 256 KiB z kopertą `result={format, bytes, lines}`, większy → `validation_error` (zawęź wybór, czytaj stronami `series read` albo zapisz plik opcją `path`). Postęp idzie jako `notifications/progress`, anulowanie żądania przerywa pracę między plikami. Lista 37 narzędzi z opisami to ok. 42 KB schematów (tryb bez zapisu, po polsku).

**MCP przez HTTP.** `imgw server` udostępnia `/mcp` (Streamable HTTP) przy `IMGW_MCP_ENABLED=true`: narzędzia odpowiadają 27 trasom REST i są wywoływane jako żądania REST w tym samym procesie, więc obowiązują reguły serwera (magazyn z `IMGW_STORE_ROOT`, `version` względna do magazynu, `IMGW_API_MAX_LIMIT`, ukrywanie katalogów serwera); POST zawsze z `?check=true` — przez HTTP tylko odczyt i plan. Język narzędzi ustala `IMGW_LANG` procesu serwera. Dozwolone nagłówki `Host` wylicza `IMGW_MCP_ALLOWED_HOSTS` (domyślnie `127.0.0.1,localhost`); za `nginx` dopisz publiczną nazwę hosta.

```bash
IMGW_MCP_ENABLED=true IMGW_STORE_ROOT=/srv/imgw imgw server   # → http://127.0.0.1:8000/mcp
```

---

## Struktura danych źródeł

### Dane hydrologiczne IMGW-PIB (1951-obecnie)
- `dobowe`: pliki miesięczne (przed 2023) lub roczne (od 2023)
- `miesieczne`: pliki roczne
- `polroczne_i_roczne`: pliki roczne z parametrami T, Q, H

> **Format CSV:** pliki archiwalne IMGW są niespójne między rocznikami w trzech aspektach:
> - **separator** — większość roczników używa przecinka z cudzysłowami, część (np. 2023) średnika, a niektóre mają dodatkowy wiersz nagłówka;
> - **kodowanie** — standardem jest CP1250, ale np. `codz_2023.zip` jest w UTF-8 z BOM;
> - **cudzysłowy** — pliki dobowe i miesięczne 2024 mają całe wiersze opakowane w cudzysłów (z podwojonymi cudzysłowami wewnątrz).
>
> Parsery (`parse_zip_file`) **wykrywają separator, kodowanie i wariant cudzysłowów automatycznie, per plik**. Zweryfikowano na danych rzeczywistych dla roczników 2019-2024 (wszystkie interwały).

### Dane meteorologiczne IMGW-PIB (1950-obecnie)
- **do 2000**: foldery 5-letnie; **od 2001**: foldery roczne
- **miesieczne**: jeden plik na folder (`{folder}_m_{k|o|s}.zip`)
- **dobowe/terminowe klimat i opad**: pliki roczne (do 2000) lub miesięczne (od 2001)
- **dobowe/terminowe synop**: pliki per stacja (`{folder}_{kod}_s.zip`) — rejestr ich nie generuje (`validation_error`, `details.reason=per_station`; użyj `meteo/miesieczne/synop`)
- **terminowe opad**: zbiór nie istnieje na serwerze IMGW (`details.reason=not_published`)
- Siatki folderów różnią się na starcie: klimat od `1951_1955`, opad od `1950_1955`, synop od `1960_1965` (struktura zweryfikowana na serwerach IMGW, 2026-07-05)

### Dane ČHMÚ (opendata.chmi.cz)
- **hydro dobowe** (`cz.chmi.hydro_daily`): `hydrology/historical/data/daily/H_<WIGOS>_DQ_<rok>.json` — plik JSON na stację i rok kalendarzowy (najstarsze z 1887); szeregi `HD`, `QD`, `TD` → H [cm], Q [m3/s], T [°C] (zawiesiny `PD` pomijane); brak pomiaru = brak wiersza
- **meteo dobowe** (`cz.chmi.meteo_daily`): `meteorology/climate/historical_csv/data/daily/precipitation/dly-<WIGOS>-SRA.csv` i `…/temperature/dly-<WIGOS>-{T,TMA,TMI}.csv` — cała historia stacji w pliku elementu; P = suma od terminu porannego (06:00Z) dnia D do porannego D+1, Tmean = (T06 + T13 + 2·T20)/4, Tmax i Tmin — ekstrema okresu (D−1 20:00, D 20:00] UTC (opisy w `variable_notes` zbioru); `QUALITY` (0–5) i `FLAG` (np. `T` — ślad opadu) zachowane
- **listy stacji**: `hydrology/historical/metadata/meta1.json` i `meteorology/climate/historical/metadata/meta1.json` (JSON z kopertą `zaznamID`/`datumVytvoreni`, zmienianą przy każdej generacji)
- **inwentarz**: listingi katalogów serwera (nazwa, czas co do minuty, rozmiar) — jedno GET listingu hydro (ok. 5,3 MB) zastępuje HEAD każdego z ok. 39 tys. plików; serwer trzyma wyłącznie najnowszą wersję pliku, a rok trafia do `historical` dopiero z publikacją roczną (hydro 2025: 2026-05-21)
- Poza zakresem: dane `now`/`recent`, godzinowe i 10-minutowe, ostrzeżenia CAP; ČHMÚ nie publikuje odpowiednika PMAXTP

### Źródła danych stacji
- **Lista stacji hydro IMGW-PIB**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Lista stacji meteo IMGW-PIB**: CSV z `danepubliczne.imgw.pl` (kodowanie CP1250)
- **Współrzędne dla mapy**: API `hydro-back.imgw.pl/map/stations/hydrologic` (900+ stacji ze stanem wody)
- **Stacje ČHMÚ**: metadane JSON z `opendata.chmi.cz` — bieżące (`hydrology/now/metadata/meta1.json`, `meta3.json`, najnowsze `meteorology/climate/now/metadata/meta1-<RRRRMMDD>.json`) i historyczne listy stacji; współrzędne WGS84, progi SPA stacji hydro

---

## Struktura projektu

```
src/imgwtools/
├── api/          # REST API (FastAPI): routes/commands.py (trasy z katalogu), errors.py (problem+json), main.py (/health, /api/v1, /llms.txt, /mcp)
├── cli/          # CLI: _dispatch.py (komendy z katalogu), admin.py, main.py (version, server, mcp)
├── mcp/          # Serwer MCP (dodatek imgwtools[mcp]): narzędzia z katalogu, stdio i /mcp
├── _parsing/     # Parsery archiwów IMGW-PIB i ČHMÚ, listingu i list stacji (publicznie: imgwtools.parsers)
├── _data/        # Obrysy Polski i Czech (Natural Earth), szablony przewodnika agents/, fixtury testowe
├── store/        # Magazyn wersjonowany: writer, sync, series, catalog, pmaxtp, reader, export, content
├── datasets.py   # Rejestr dostawców i 17 zbiorów (pl.imgw.*, cz.chmi.*), generator plików archiwów
├── commands.py   # Katalog 37 komend wspólny dla Pythona, CLI, REST, MCP i integracji
├── agent_guide.py # Przewodnik dla agentów (AGENTS.md, llms.txt): agent_guide, commands guide
├── fetch.py      # Dane bieżące, PMAXTP, pobieranie archiwów
├── stations.py   # find_stations (IMGW-PIB i ČHMÚ)
├── urls.py       # Stałe URL IMGW, build_pmaxtp_url, build_api_url
├── project.py    # Manifest projektu imgw-project/1
├── testing.py    # build_fixture_store — magazyn testowy offline (także PL + CZ)
├── web/          # Web GUI (HTMX + Jinja2)
└── config.py     # Konfiguracja (IMGW_*)

AGENTS.md, llms.txt  # Przewodnik dla agentów AI — pliki pochodne (imgw commands guide)

data/             # Lokalne dane referencyjne (python -m imgwtools.reference_data), poza repozytorium
docker/           # Konfiguracja Docker
tests/            # Testy (offline; fixtury magazynu w tests/fixtures/store)
```

---

## Docker

```bash
cd docker
docker compose up -d

# Z serwerem MCP pod /mcp (tylko odczyt i plan); za nginx dopisz publiczną nazwę hosta
IMGW_MCP_ENABLED=true IMGW_MCP_ALLOWED_HOSTS=dane.example.pl docker compose up -d
```

Obraz (`python:3.12-slim`) instaluje `.[api,mcp]` i uruchamia jeden proces uvicorn (sesje MCP żyją w procesie). `docker-compose.yml` przekazuje z otoczenia `IMGW_MCP_ENABLED` (domyślnie `false`), `IMGW_MCP_ALLOWED_HOSTS` (domyślnie `127.0.0.1,localhost`) i `IMGW_LANG` (domyślnie `pl`); `nginx.conf` ma `location = /mcp` z limitem żądań i bez buforowania.

---

## Magazyn wersjonowany (opcjonalny)

Magazyn to zwykły katalog wskazany jawnie przez użytkownika (`--root`, `init_store(root)`, na serwerze `IMGW_STORE_ROOT`). Nie ma domyślnej lokalizacji ani bazy danych; magazyn można czytać offline z dysku lokalnego lub udziału sieciowego. Zapis nie wymaga Linuksa ani dowiązań twardych — działa także na Windows, macOS i udziale SMB: wersję publikuje jedna operacja rename bez zastępowania (na Linuksie `renameat2`, gdzie indziej przenośny odpowiednik), więc pojawia się cała albo wcale. Jeden magazyn mieści dane obu dostawców. Szczegóły: `docs/DECISIONS.md` (ADR-001, ADR-003), `docs/superpowers/specs/2026-10-17-versioned-store-design.md` i `2026-10-18-chmi-provider-design.md`.

### Układ katalogu

```text
<root>/imgw-store.json                                  # znacznik imgw-store/1
  archives/versions/<ścieżka serwera>/<stem>/<etykieta>_<sha8>/<plik>[.meta.json]
  archives/versions/<ścieżka serwera>/<stem>/observations/<data>_<sha8>.json   # rejestr obserwacji (ČHMÚ)
  stations/versions/<etykieta>_<sha8>/stations.geojson[.meta.json]                 # katalog IMGW-PIB
  stations/versions/chmi_stations/<etykieta>_<sha8>/stations.geojson[.meta.json]   # katalog ČHMÚ
  series/versions/<slug>/<etykieta>_<sha8>/series.json[.meta.json] + stations/<kod>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<etykieta>_<sha8>/cell.json[.meta.json]
  .incoming/                                            # staging; nigdy nie jest wersją
```

Wersje są niezmienne i tylko dopisywane: brak nadpisywania, dowiązań i ścieżki `latest`. Bieżącą wersję wylicza `current_version(root, slot=...)`; sloty: `archive:<klucz>:<plik>` (np. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`, `archive:cz.chmi.hydro_daily:H_0-203-1-001000_DQ_2025.json`), `series:<klucz>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `pmaxtp:pl.imgw.pmaxtp:<METODA>/<indX>_<indY>`. Każdy plik główny ma sidecar `*.meta.json` (`imgw-meta/1`) z SHA-256, rozmiarem, żądaniem, nagłówkami HTTP i licencją dostawcy; sidecary archiwów ČHMÚ z formą kanoniczną mają też `content_sha256`. Katalog `observations/` (`imgw-observation/1`) zapisuje nowy sygnał źródła, gdy pobrane bajty mają tę samą treść co bieżąca wersja — nie jest wersją, `store scan --kind observation` pokazuje go jako historię publikacji.

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
| `cz.chmi.hydro_daily` | — | ČHMÚ hydro dobowe: H [cm], Q [m3/s], T [°C]; plik na stację i rok |
| `cz.chmi.meteo_daily` | — | ČHMÚ meteo dobowe: P [mm], Tmean, Tmax, Tmin [°C] z jakością (`QUALITY`) i flagą ČHMÚ; 4 pliki na stację |
| `cz.chmi.hydro_stations`, `cz.chmi.meteo_stations` | — | Listy stacji ČHMÚ (JSON) — wejście katalogu ČHMÚ |

Zbiory „tylko pobieranie” obsługują `datasets files|download`, ale nie magazyn. Dane bieżące, ostrzeżenia i `fetch_pmaxtp` pozostają zapytaniami na żywo, bez magazynu. `datasets(provider="CHMI")` albo `imgw datasets list --provider CHMI` wypisuje zbiory jednego dostawcy, a `providers()` / `imgw datasets providers` — dostawców z licencjami i wzorcami kodów stacji.

### Schematy

`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`, `imgw-observation/1` (oraz rozszerzenie `imgw-pmaxtp/1`) mają własne liczniki wersji, niezależne od wersji pakietu; koperta wyniku komend to `imgw-result/1`. W ramach `/1` dochodzą tylko pola opcjonalne; zmiana niezgodna oznacza `/2`. Nieznana wersja jest raportowana (`store_info(...).supported is False`), a nie zgadywana. Dziedziny `/1` są otwarte na kolejnych dostawców (klucz `<kraj>.<dostawca>.<slug>`, kod stacji IMGW albo WIGOS; ADR-003).

### Integracje

- **Archiwista** czyta magazyn wyłącznie publicznym API odczytu (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`), dane obu dostawców tym samym adapterem (`provider` we wpisach, katalogach i stacjach; wpisy `kind="observation"` tylko do odczytu); IMGWTools jest jedynym piszącym, a w magazynie nie ma plików Archiwisty.
- **Retman** uruchamia działania jako handler przez publiczny katalog komend (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`) — te same opcje, walidacja, koperta i kody błędów co w CLI i REST; opisy angielskie z `command_schema(lang="en")`, skutki z `x-imgw.writes` i `x-imgw.network`.

Poprzedni opcjonalny cache SQLite został usunięty w 3.0.0 bez migracji — zob. `docs/CHANGELOG.md`.

---

## Testy

Projekt zawiera testy jednostkowe i kontraktowe publicznego API, CLI, REST, MCP i Web GUI. Wszystkie działają offline: sieć jest mockowana (`respx`) albo odtwarzana z nagrań w `tests/fixtures/store/`.

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
├── conftest.py              # Wspólne fixtures; autouse isolated_data_dir (settings.data_dir w tmp); publication (ścieżki zapisu wersji)
├── fixtures/store/          # Syntetyczne archiwa, listingi i nagrane odpowiedzi HTTP IMGW-PIB i ČHMÚ (fikcyjne stacje)
├── fixtures/export_golden/  # Złote pliki eksportu archiwów (CSV z CRLF, JSONL)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets*.py, test_coverage*.py, test_download_archives*.py, test_parsing_chmi.py
│   ├── test_store_*.py, test_series_export.py          # magazyn: writer, sync, series, catalog, pmaxtp, reader, export, content
│   ├── test_fixture_builder*.py                        # imgwtools.testing (complete, complete_pl_cz)
│   ├── test_commands*.py, test_command_schema.py       # katalog komend, command_schema
│   ├── test_catalog_effects.py, test_catalog_i18n.py   # skutki komend, opisy angielskie
│   ├── test_agent_guide.py                             # AGENTS.md i llms.txt (test dryfu)
│   ├── test_mcp_*.py                                   # serwer MCP: narzędzia, wywołania, stdio, /mcp
│   ├── test_project*.py, test_exceptions.py            # imgw-project/1, rejestr kodów błędów
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py   # CLI, REST i Web GUI
│   ├── test_reference_data.py                          # python -m imgwtools.reference_data
│   └── test_public_store_api.py                        # kontrakt eksportów publicznych
├── contract/                # kontrakt magazynu, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19), projekt
└── live/                    # regresja na żywo (tylko z IMGW_LIVE=1): IMGW-PIB 37 komend × Python/CLI/REST + MCP; ČHMÚ
```

**Łącznie: 2251 testów** (`pytest --collect-only`, 2026-10-19): 2172 offline i 79 na żywo, pomijane bez `IMGW_LIVE=1`:

```bash
IMGW_LIVE=1 .venv/bin/python -m pytest tests/live/test_interfaces_live.py   # IMGW-PIB: 53 testy
IMGW_LIVE=1 .venv/bin/python -m pytest tests/live -k imgw_mcp               # sama noga MCP (imgw mcp)
IMGW_LIVE=1 .venv/bin/python -m pytest tests/live/test_chmi_live.py         # ČHMÚ: 26 testów, ok. 31 MB
```

Raport JSON przebiegu: `IMGW_LIVE_REPORT=<plik>`; test ČHMÚ zapisuje dziennik żądań każdego interfejsu (Python, CLI, REST, MCP) i podaje liczbę żądań i bajtów (`-s`).

---

## Dokumentacja

- `CLAUDE.md` - Instrukcje dla Claude Code
- `docs/CHANGELOG.md` - Historia zmian (w tym BREAKING 3.0.0)
- `docs/DECISIONS.md` - Rejestr decyzji (ADR-001: magazyn wersjonowany, ADR-002: jeden katalog komend, ADR-003: dostawca ČHMÚ, ADR-004: wsparcie agentów AI)
- `docs/ARCHITECTURE.md` - Architektura systemu
- `docs/PRD.md` - Wymagania produktu
- `docs/PROGRESS.md` - Postęp i backlog
- `AGENTS.md`, `llms.txt` - Przewodnik dla agentów AI (generowany: `imgw commands guide`)

---

## Problemy i wsparcie

Zgłoś problemy w sekcji [Issues](https://github.com/Daldek/IMGWTools/issues).

---

## Źródła danych

IMGWTools nie dystrybuuje danych IMGW-PIB ani ČHMÚ, a serwer domyślnie ich nie przechowuje — każde pobranie i zapis do magazynu jest świadomą decyzją użytkownika lub administratora (jawny `--output`, `--root`, `IMGW_STORE_ROOT`). Poniżej zestawienie wykorzystywanych źródeł.

| Źródło | Operator | Warunki korzystania |
|--------|----------|---------------------|
| Archiwum pomiarowo-obserwacyjne — `danepubliczne.imgw.pl/data` (hydro/meteo, ZIP/CSV) | IMGW-PIB | Nieodpłatnie do celów prywatnych i naukowych; dane o wysokiej wartości — w każdym celu; część zastosowań komercyjnych wymaga umowy; obowiązkowa atrybucja. [Regulamin](https://danepubliczne.imgw.pl/regulations)
| API czasu rzeczywistego — `danepubliczne.imgw.pl/api/data` (hydro, synop, meteo, ostrzeżenia) | IMGW-PIB | Jak wyżej ([regulamin](https://danepubliczne.imgw.pl/regulations))
| PMAXTP — `klimat.imgw.pl/opady-maksymalne` | IMGW-PIB | Wskazanie źródła IMGW-PIB (dane ze strony `klimat.imgw.pl/opady-maksymalne`) oraz cytowanie monografii Projektu PMAXTP (red. B. Ozga-Zieliński, IMGW-PIB, Warszawa 2022; monografia: Open Access, CC-BY 4.0); przy danych przetworzonych — adnotacja o przetworzeniu; korzystanie na własne ryzyko. [Regulamin](https://klimat.imgw.pl/opady-maksymalne/) |
| Mapa stacji ze współrzędnymi — `hydro-back.imgw.pl/map/stations/hydrologic` (backend serwisu `hydro.imgw.pl`) | IMGW-PIB | Regulamin serwisu hydro.imgw.pl (akceptacja przez rozpoczęcie korzystania); obowiązuje ogólna zasada wskazania źródła IMGW-PIB. [Regulamin](https://hydro.imgw.pl/#/regulamin) |
| Archiwa i metadane stacji — `opendata.chmi.cz` (`hydrology/historical`, `hydrology/now/metadata`, `meteorology/climate/historical_csv`, `meteorology/climate/historical/metadata`, `meteorology/climate/now/metadata`) | ČHMÚ (Český hydrometeorologický ústav) | Licencja [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): kopiowanie, zmiany i użycie komercyjne pod warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian ([warunki ČHMÚ](https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti)). ČHMÚ nie narzuca formuły; IMGWTools zapisuje „Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0”, a przy postaciach przetworzonych dodaje „Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)” |

Obowiązek podania atrybucji przy publikacji wyników spoczywa na użytkowniku pobierającym dane.

### Dane referencyjne (listy stacji, współrzędne, opisy formatów)

Repozytorium **nie zawiera** danych IMGW. Pliki referencyjne używane przez narzędzia (listy stacji, współrzędne, opisy formatów) pobierz jednorazowo — po instalacji pakietu (`pip install -e .`), bez żadnych argumentów:

```bash
python -m imgwtools.reference_data
```

Pobrane pliki trafiają do `data/` i pochodzą z IMGW-PIB — podlegają warunkom IMGW-PIB (nie licencji MIT projektu).

Jedyne dołączone do pakietu zbiory geograficzne to obrysy granic Polski `src/imgwtools/_data/poland_border_wgs84.geojson` i Czech `src/imgwtools/_data/czechia_border_wgs84.geojson` (kontrola położeń w katalogach stacji) z Natural Earth 1:10m Admin 0 – Countries v5.1.2 — domena publiczna ([warunki](https://www.naturalearthdata.com/about/terms-of-use/)), nie dane IMGW-PIB ani ČHMÚ.

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
- Jeden katalog 37 komend dla Pythona, CLI, REST i MCP (`command_schema`, `run_command`),
  koperta `imgw-result/1` ze stronicowaniem, rejestr kodów błędów `ERROR_CODES`.
- `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`, `download_archives`,
  `select_series`, `summarize_series`, `export_archive`; rejestr 17 zbiorów dwóch dostawców.
- Dostawca ČHMÚ (Czechy): dobowe dane hydrologiczne i meteorologiczne per stacja,
  aktualność z listingu, treść kanoniczna i rejestr obserwacji, katalog stacji z progami SPA,
  jakość i flagi ČHMÚ w szeregach, odtwarzanie przypięć treścią.
- Agenci AI: `AGENTS.md`, `llms.txt`, `imgw commands guide`, opisy angielskie katalogu
  (`IMGW_LANG`, `Accept-Language`), metadane skutków komend, serwer MCP `imgw mcp` i `/mcp`.
- Projekty `imgw-project/1` z przypięciem wersji po SHA-256 i publiczny budowniczy
  magazynu testowego `imgwtools.testing.build_fixture_store` (także wariant PL + CZ).

---

## Licencja

Projekt udostępniony na licencji MIT. Szczegóły w pliku `LICENSE`.

---

## Autor

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
