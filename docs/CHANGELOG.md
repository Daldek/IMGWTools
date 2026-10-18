# Changelog — IMGWTools

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersjonowanie
zgodne z [SemVer](https://semver.org/lang/pl/). Każda zmiana publicznego API i schematów
magazynu (`imgw-*/N`) trafia do tego pliku (ADR-001, polityka IMGW-13).

## [3.0.0] — 2026-10-18

Wersjonowany magazyn danych IMGW zastępuje opcjonalny cache SQLite (ADR-001), a Python,
CLI, REST i web korzystają z jednego katalogu 35 komend z jedną kopertą wyniku i jednym
rejestrem kodów błędów (ADR-002). Przed tagiem dziedziny kontraktów `/1` otwarto dla
kolejnych dostawców (ADR-003, C01). Decyzje: `docs/DECISIONS.md`; kontrakt:
`docs/superpowers/specs/2026-10-17-versioned-store-design.md` (§13 — spójność interfejsów,
§13.11 — pełne tabele migracji). Wydanie nie ma aliasów ani shimów starych nazw.

### BREAKING

#### Python — funkcje danych (wobec 2.2.0)

| Było | Jest |
|---|---|
| `fetch_hydro_current(station_id=…)` (+`_async`) | `fetch_hydro_current(*, station=…)`; `HydroCurrentData.station_id` → `station_code`, nowe `latitude`, `longitude` |
| `fetch_synop(station_id=…, station_name=…)` (+`_async`) | `fetch_synop(*, station=…, station_name=…)`; `SynopData.station_id` → `station_code` |
| `fetch_warnings(warning_type="hydro")` (+`_async`) | `fetch_warnings(*, kind=None)` (brak = obie rodziny); `WarningData.warning_type` → `kind`, nowe `event` |
| `fetch_pmaxtp(lat, lon, "AMP")` | `fetch_pmaxtp(lat, lon, method="AMP")`; wywołanie z nazwanym `method` bez zmian |
| `list_hydro_stations()`, `list_meteo_stations()` (+`_async`) → `HydroStation`, `MeteoStation` | `find_stations(kind="hydro")` / `find_stations(kind="meteo")` (+`find_stations_async`) → `StationListEntry` (`station_id` → `station_code`) |
| `get_hydro_stations_with_coords(include_all=True)` (+`_async`) | `fetch_hydro_states(main_only=False)` (+`_async`) → `HydroState` |
| `build_hydro_url(HydroInterval.DAILY, 2023)` | `archive_files("hydro/dobowe", years=2023)[0].url` (albo klucz `pl.imgw.hydro_daily`) |
| `build_hydro_url(HydroInterval.DAILY, 2023, month=13)` | `archive_files("pl.imgw.hydro_phenomena", years=2023)[0].url` |
| `build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 1995)` | `archive_files("meteo/miesieczne/synop", years=1995)[0].url` |
| `get_available_years(DataType.HYDRO, "dobowe")` | `get_dataset("hydro/dobowe").first_year` (górnej granicy brak) |
| `DownloadURL` | `ArchiveFile` |
| `DataType`, `HydroInterval`, `HydroParam`, `MeteoInterval`, `MeteoSubtype` | klucze i aliasy zbiorów (`str`), `params` `H\|Q\|T` |
| `PMaXTPMethod` | `Literal["POT", "AMP"]` |
| `build_pmaxtp_url(method, latitude, longitude)` | `build_pmaxtp_url(latitude, longitude, *, method="POT")` |
| `build_api_url(endpoint, station_id=…, station_name=…)` | `build_api_url(endpoint, *, station=…, station_name=…)` |
| `IMGWError(message)` | `IMGWError(message, *, code=…, details=…)`; wywołanie z samym komunikatem bez zmian |
| `download_hydro_data`, `download_meteo_data` (+`_async`) → `bytes` | → `DownloadResult` (`data` = dokładne bajty, `url`, `etag`, `last_modified`, `content_length`); argumenty bez zmian, migracja: `download_hydro_data("dobowe", 2023).data`; odpowiedź, która nie jest ZIP-em → `IMGWDataError`; brak miesiąca/parametru → `IMGWValidationError` z `details.option` |
| `parse_zip_file` → `zipfile.BadZipFile` przy uszkodzonym archiwum | `IMGWDataError`; ZIP czytany z limitami liczby/rozmiaru plików i bez niebezpiecznych ścieżek |
| `parse_stations_csv(data)` → `HydroArchiveStation` | `parse_stations_csv(data, kind="hydro"\|"meteo")` → `StationListEntry` (`kind`, `station_code`, `name`; hydro `river`, `hydrographic_code`, `river_order`; meteo `short_code`); `.station_name`/`.river_name` → `.name`/`.river`; lista meteo nie jest czytana układem hydro (trzecia kolumna to `short_code`) |
| `HydroArchiveStation.hydrographic_code`, `river_order`, `latitude`, `longitude` | usunięte (klasa opisuje wyłącznie stację z wierszy archiwów danych) |

Usunięte z `imgwtools` (także z `imgwtools.urls`), bez zamienników o tej samej nazwie:
`HydroStation`, `MeteoStation`, `list_hydro_stations`, `list_hydro_stations_async`,
`list_meteo_stations`, `list_meteo_stations_async`, `get_hydro_stations_with_coords`,
`get_hydro_stations_with_coords_async`, `build_hydro_url`, `build_meteo_url`,
`get_available_years`, `DownloadURL`, `DataType`, `HydroInterval`, `HydroParam`,
`MeteoInterval`, `MeteoSubtype`, `PMaXTPMethod`; moduł `imgwtools.core` (`url_builder`)
— stałe URL i `build_pmaxtp_url`/`build_api_url` są w `imgwtools.urls`.

#### Usunięty cache SQLite (ADR-001)

- pakiet `imgwtools.db` (`cache_manager`, `connection`, `schema`, `repository`, `models`,
  `parsers`) — parsery hydro są nadal w `imgwtools.parsers`, modele archiwalne
  (`HydroArchiveStation`, `HydroDailyRecord`, …) w `imgwtools.models`;
- komenda CLI `imgw db …` (`init`, `status`, `stations`, `cache`, `query`, `clear`, `vacuum`);
- endpoint REST `GET /api/v1/hydro/data`;
- ustawienia `IMGW_DB_ENABLED` i `IMGW_DB_PATH`;
- dodatek instalacyjny `imgwtools[db]`.

Istniejące pliki `.db` nie są usuwane ani migrowane — dane pobiera się ponownie do magazynu
(`imgw store sync`).

#### Python — wobec niewydanych wersji roboczych 3.0.0 (ADR-001, gałąź `feature/versioned-store`)

Dotyczy wyłącznie integracji pisanych na gałęzi przed ADR-002 (Archiwista, Retman).

| Było | Jest |
|---|---|
| `run_command(...)` → wynik funkcji | `CommandResult` (wynik w `.result`) |
| `check_command(...)` → `StorePlan` | `CommandResult` (`.check=True`, plan w `.result`) |
| `IMGWPlanStaleError` | usunięty; pozycja `stale_plan`, koperta `partial` |
| `IMGWStoreError` przy anulowaniu `write_archive`/`export_series` | `IMGWCancelledError` |
| `datasets()` | `datasets(*, kind=None)`; `DatasetDescriptor` z polami `kind`, `title`, `first_year`, `legacy_alias`, `in_store`; `time_unit` także `term` |
| `get_dataset(klucz)` | klucz, slug albo alias legacy |
| `archive_files(..., years: Iterable[int])` | `years: YearsArg`, `months: MonthsArg`, nowe `params` |
| `check_store`/`sync_store(..., years: Iterable[int])` | `YearsArg`/`MonthsArg`; `check_store(..., plan=PLIK)` zapisuje plan |
| `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp` z wymaganym `method` | `method="POT"` |
| `current_version(slot="archive:<server_path>")`, `series:<slug>`, `catalog:stations`, `pmaxtp:<M>:<x>_<y>` | `archive:<klucz>:<selektor>`, `series:<klucz>`, `catalog:pl.imgw.stations`, `pmaxtp:pl.imgw.pmaxtp:<METODA>/<indX>_<indY>` |
| `read_series(version, *, station, variables)` | `read_series(version=None, *, root, dataset, station, variables=None, start, end)` |
| `export_series(version, *, station, path, variables, year_type, format)` | `export_series(version=None, *, root, dataset, station, variables=None, start, end, year_type, format, path=None)` → `Path` albo iterator linii |
| `run_command("store read", …)` | `export_archive(version, *, root, format, path)`; komenda `store export` |
| `run_command("series select", …)` | `select_series(root, *, dataset, stations, variables, years, year_type)` |
| `run_command("fetch hydro" / "fetch meteo", …)` → `Path` | `download_archives(dataset, *, years, months, params, output)` → `DownloadReport` |
| `StationCoverage.station`, `ProjectFile.station` | `station_code` |
| `OperationResult(slot, status, version, error)` | + `task`, `error_code`; `slot` według nowej gramatyki |
| `StoreEntry.slot: str` | `str \| None` |
| `CommandOption` z `lat`/`lon` typu `str` | typy `float`, `date`, `object`; nowe pola opisu opcji |
| `DataCommand(name, description, options)` | + `function`, `check`, `result`, `method`, `requires`, `one_of`, `rules` |
| `init_store` na systemie plików bez dowiązań twardych → `IMGWStoreError` | `IMGWStoreConflictError` (`details.reason="not_atomic"`) |

#### CLI

| Było | Jest |
|---|---|
| `imgw fetch hydro -i dobowe -y 2023 -m 1 [-p H] [-o KAT]` | `imgw datasets download -d hydro/dobowe -y 2023 -m 1 [--params H] [-o KAT]` (`-d` wymagane, bez domyślnego interwału); `-o` odwzorowuje ścieżki serwera IMGW, zapis przez `.part` i `os.replace` |
| `imgw fetch meteo -i miesieczne -s synop -y 2023 [-o KAT]` | `imgw datasets download -d meteo/miesieczne/synop -y 2023 [-o KAT]` |
| `imgw fetch current hydro\|meteo\|synop [-s ID] [-o PLIK]` | `imgw current hydro\|meteo\|synop [-s KOD]` (zapis: `> PLIK`) |
| `imgw fetch pmaxtp -m AMP --lat … --lon … [-o PLIK]` | `imgw pmaxtp fetch --method AMP --lat … --lon …` |
| `imgw fetch warnings -t meteo [-o PLIK]` | `imgw current warnings -k meteo` |
| `imgw list stations -t hydro -s Warsz -l 50` | `imgw stations find -k hydro -q Warsz --limit 50` |
| `imgw list datasets [-t hydro]` | `imgw datasets list [-k hydro]` |
| `imgw list intervals` | `imgw datasets list` (pole `legacy_alias`) |
| `imgw store check\|sync --dataset K` | `--datasets K` albo `-d K` |
| `imgw store read …` | `imgw store export …` |
| `imgw pmaxtp check\|sync\|read --method M` (wymagane) | opcjonalne, domyślnie `POT`; `--lat`/`--lon` to aliasy `--latitude`/`--longitude` |
| `imgw series export … --path P` (wymagane) | `--path` opcjonalne (bez niego CSV na stdout) |
| `--check` przy `store check`, `pmaxtp check`, `project check` | brak |
| stdout: surowy wynik, ścieżki bezwzględne | koperta `imgw-result/1` w jednej linii, ścieżki w magazynie względne do root |
| błąd: `Błąd: …` na stderr (komendy legacy: stdout), kod 1 | JSON `{"code", "detail", "details"}` w ostatniej linii stderr, kod według rejestru błędów; wynik `partial`/`failed` → 10/11, anulowanie 130 |

#### REST

| Było | Jest |
|---|---|
| `GET /api/v1/hydro/stations`, `GET /api/v1/meteo/stations` (zaślepki), `GET /api/v1/hydro/stations/{station_id}` | `GET /api/v1/stations/find?kind=…&query=…` |
| `GET /api/v1/hydro/current?station_id=` | `GET /api/v1/current/hydro?station=` |
| `GET /api/v1/meteo/current?station_id=` | `GET /api/v1/current/meteo?station=` |
| `GET /api/v1/meteo/synop?station_id=&station_name=` | `GET /api/v1/current/synop?station=&station_name=` |
| — | `GET /api/v1/current/warnings`, `GET /api/v1/current/hydro-states` |
| `POST /api/v1/hydro/download-url`, `/hydro/download-urls`, `/meteo/download-url`, `/meteo/download-urls`; `GET /api/v1/download/url`, `/download/urls` | `GET /api/v1/datasets/files?dataset=…&years=…&months=…&params=…` |
| `GET /api/v1/download/datasets` | `GET /api/v1/datasets/list` |
| `GET /api/v1/pmaxtp/methods` | `GET /api/v1/commands/schema?command=pmaxtp%20fetch` (wyliczenie `method` z opisem) |
| `POST /api/v1/pmaxtp/url` | `GET /api/v1/pmaxtp/url` |
| `POST /api/v1/pmaxtp/data` (surowa odpowiedź IMGW) | `GET /api/v1/pmaxtp/fetch` (`PMaXTPResult`) |
| `GET /api/v1/store/entries` | `GET /api/v1/store/scan` |
| `POST /api/v1/store/check` | `GET /api/v1/store/check` |
| `POST /api/v1/store/sync` (409 `stale_plan`) | ta sama trasa; 200 + koperta `partial`; `?check=true` |
| `GET /api/v1/series/index` | `GET /api/v1/series/summary` |
| `GET /api/v1/series/{station}` | `GET /api/v1/series/read?station=…` |
| `POST /api/v1/series/export` (zapis tymczasowy, token) | `GET /api/v1/series/export` (strumień, bez tokenu) |
| `POST /api/v1/pmaxtp/store/sync` | `POST /api/v1/pmaxtp/sync` |
| — | `GET /api/v1/pmaxtp/check`, `GET /api/v1/pmaxtp/read`, `GET /api/v1/store/export`, `GET /api/v1/series/select`, `GET /api/v1/commands/schema` |
| `GET /map/stations` (web) | `GET /api/v1/current/hydro-states` |
| błędy `{"detail": …}`, 422 z listą pydantic, `{"code", "detail"}` | `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`); walidacja zawsze 400 |
| kody `store_not_configured`, `store_root_invalid`, `user_locations_invalid` (503) | `store_unavailable` + `details.reason` |
| kody `writes_disabled`, `write_token_missing`, `invalid_api_key` (403) | `forbidden` + `details.reason` |
| kody `stale_plan` (409), `store_error` (500) | koperta `partial`; `store_unavailable` albo `internal_error` |

Web: trasy `/download/hydro|meteo[/generate]`, `/stations/hydro|meteo` i `/map/stations`
zastąpiły `/download/archives` + `POST /download/files`, `/stations/find` i trasa katalogu
`GET /api/v1/current/hydro-states`.

#### Pola i pliki

| Było | Jest |
|---|---|
| REST `Station.id`, `HydroStation.station_id`, `HydroCurrentData.station_id`, `SynopData.station_id` | `station_code` |
| REST `DownloadURLResponse{url, filename, data_type, interval, year, month}` | `ArchiveFile{dataset, server_path, url, year, month, param, year_type, period_start, period_end}` |
| REST `HydroCurrentData{water_level, flow, temperature}` | model biblioteki `{water_level_cm, flow_m3s, water_temp_c, …}` |
| REST `MeteoCurrentData{temperature, wind_speed, humidity, precipitation}` | `MeteoCurrentData{air_temp_c, wind_speed_ms, humidity_percent, precipitation_10min_mm, …}` albo `SynopData` |
| `WarningData.warning_type`, REST `WarningData.type` | `kind` |
| `OperationResult.slot` `archives/versions/<katalog>/<stem>` lub `<zadanie>:<ścieżka>` | slot `archive:<klucz>:<selektor>` itd. + pole `task` |
| `StoreEntry.slot` `archive:<server_path>`, `series:<slug>`, `catalog:stations`, `pmaxtp:<M>:<x>_<y>` | nowa gramatyka slotów (jak wyżej) |
| `imgw-project.json` `files[].station` | `files[].station_code` |
| CSV użytkownika `station_code,lon,lat,source` | `station_code,latitude,longitude,source` |
| `data/hydro_stations_locations.csv` `id,X,Y` | `station_code,latitude,longitude` (ponownie `python -m imgwtools.reference_data`; stary nagłówek → `validation_error` z instrukcją) |
| `data/hydro_stations_names.csv`, `data/meteo_stations_names.csv` i `Settings.hydro_stations_file`/`meteo_stations_file` | usunięte (czytała je tylko `imgw list stations`) |

#### Instalacja

- **`imgwtools[full]`** obejmuje `store` (`pyarrow>=15`) obok `api`, `cli`, `pandas`.

### Dodane

- **Wersjonowany magazyn** (`imgwtools.store`, re-eksport w `imgwtools`): niezmienne,
  tylko przyrostowe wersje archiwów IMGW 1:1 z sidecarem `*.meta.json` (SHA-256, rozmiar,
  nagłówki HTTP, licencja IMGW-PIB), atomowa publikacja katalogu wersji (rename bez
  zastępowania), staging `.incoming/`, wykrywanie katalogów Kartografa bez jego importu.
  Funkcje: `init_store`, `open_store`, `write_archive`, `check_store`/`sync_store`
  (listing + `HEAD`, plan `imgw-plan/1`, pozycje `stale_plan`), `check_series`/`build_series`
  (Parquet per stacja), `check_catalog`/`build_catalog` (`stations.geojson`, obrys
  Polski Natural Earth w pakiecie), `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp`
  (PMAXTP per komórka siatki; obok `cell.json` surowa odpowiedź API bajt w bajt jako
  `response.json`, opisana w `extra.response` sidecara), odczyt `store_info`, `iter_store`,
  `read_meta`, `current_version`, `read_catalog`, `read_series_index`, `read_series`.
- **Odczyt list stacji i archiwów z magazynu (offline, SHA-256)**:
  `read_station_list(root, kind="hydro"|"meteo")` → krotka `StationListEntry` bieżącej
  wersji listy; `read_archive(version)` → rekordy `NormalizedRecord` zapisanej wersji
  archiwum (wersję listy stacji odrzuca z odesłaniem do `read_station_list`).
- **Szeregi i eksport**: `select_series` (wybór wersji szeregu dla stacji, zmiennych
  i roczników), `summarize_series` (pokrycie per stacja × zmienna z lukami; `series summary`),
  `export_series` (CSV z jednostkami i atrybucją IMGW-PIB) i `export_archive` (CSV albo
  JSONL jednej wersji archiwum; `store export`) — z `path` zapis przez `.part`
  i `os.replace`, bez `path` iterator gotowych linii (w CLI i REST strumień).
- **Rejestr zbiorów** `imgwtools.datasets`: `datasets(*, kind=None)`, `get_dataset()`
  (klucz, slug albo alias legacy), `archive_files()`, `station_source_files()`,
  `DatasetDescriptor`, `ArchiveFile`, `License`, `YearsArg`/`MonthsArg` (`2024`,
  `"2020-2023"`, `"2020,2022"`, listy). 13 deskryptorów: pięć zbiorów archiwalnych
  magazynu (`pl.imgw.hydro_daily`, `pl.imgw.hydro_monthly`, `pl.imgw.hydro_semiannual`,
  `pl.imgw.meteo_climate_daily`, `pl.imgw.meteo_precip_daily`), listy stacji
  (`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`), PMAXTP (`pl.imgw.pmaxtp`) i pięć
  zbiorów tylko do pobrania (`pl.imgw.hydro_phenomena`, `pl.imgw.meteo_climate_monthly`,
  `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`,
  `pl.imgw.meteo_climate_terms`).
- **`download_archives(dataset, /, *, years, months, params, output)`** →
  `DownloadReport`/`DownloadItem` (slot, URL, status, ścieżka, `error_code`): pobieranie
  płaskie w układzie ścieżek serwera IMGW, zapis przez `.part` i `os.replace`, komunikat
  `license_terms` po pobraniu.
- **Dane na żywo**: `find_stations`/`find_stations_async` (listy IMGW na żywo albo
  z magazynu, `source="live"|"store"`; wyszukiwanie bez wielkości liter i polskich znaków),
  `fetch_meteo_current`/`_async` → `MeteoCurrentData`, `fetch_hydro_states`/`_async` →
  `HydroState` (współrzędne i stan wody z `hydro-back.imgw.pl`); ostrzeżenia z endpointów
  `warningshydro`/`warningsmeteo` (`WarningData.event`); `StationListEntry` z opcjonalnymi
  `latitude`/`longitude`.
- **Kody błędów**: zamknięty rejestr `ERROR_CODES` (`ErrorCode`, `ErrorSpec`: tytuł, kod
  wyjścia CLI, status HTTP) — `validation_error` (2/400), `not_found` (3/404), `conflict`
  (4/409), `source_unavailable` (5/502), `missing_dependency` (6/503), `data_error` (7/500),
  `store_unavailable` (8/503), `io_error` (9/500), `cancelled` (130), `forbidden` (403),
  `method_not_allowed` (405), `internal_error` (1/500). Każdy `IMGWError` ma `code`
  i `details` (np. `option`, `allowed`, `reason`); nowy `IMGWCancelledError`.
- **Katalog komend** `imgwtools.commands`: 35 komend w grupach `datasets`, `stations`,
  `current`, `pmaxtp`, `store`, `series`, `project`, `commands`; `command_schema(command=None)`
  (JSON Schema opcji + `x-imgw`: funkcja, bliźniak check, typ wyniku, flagi CLI, trasa REST,
  reguły; dokument `imgw-commands/1` z kodami błędów i wyjścia), `data_commands`,
  `validate_command`, `format_command`, `check_command`, `run_command` → `CommandResult`
  (koperta `imgw-result/1`: `status` `ok|partial|failed|cancelled`, `result`, `notices`
  bez powtórzeń). **Stronicowanie**: 11 komend listowych zwraca `Page`
  (`items`, `total`, `limit`, `offset`) z opcjami `limit`/`offset`.
- **CLI** generowane z katalogu (`cli/_dispatch.py`): koperta JSON na stdout, strumienie
  `store export`/`series export`, błąd jako JSON na stderr, kody wyjścia z rejestru,
  `--check` przy komendach z bliźniakiem, `--schema` przy każdej, `--root` z
  `IMGW_STORE_ROOT`, listy po przecinku albo powtórzona flaga; Ctrl+C anuluje między
  plikami (130).
- **REST** generowane z katalogu (`/api/v1/<grupa>/<komenda>`, 25 tras; `GET /api/v1`
  wypisuje trasy): ta sama koperta co CLI, `application/problem+json`, `?check=true`
  przy `POST`, `limit` domyślnie i najwyżej `IMGW_API_MAX_LIMIT` (1000). Komendy magazynu
  wyłącznie na serwerowym, absolutnym `IMGW_STORE_ROOT` (bez niego 503); zapis wymaga
  `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` i nagłówka `X-API-Key`; CSV
  współrzędnych użytkownika tylko z `IMGW_USER_LOCATIONS_DIR`. Odpowiedzi nie ujawniają
  katalogów serwera (ścieżki względne do root, także w tekstach).
- **Web GUI** wyłącznie na publicznym API: formularz archiwów z rejestru (10 zbiorów),
  wyszukiwarka stacji ze stronicowaniem, mapa z `GET /api/v1/current/hydro-states`, błędy
  jako fragment z kodem `IMGWError`; stopka podaje bieżącą wersję pakietu.
- **Projekty** `imgwtools.project` (`imgw-project.json`): `init_project`, `open_project`,
  `set_project_store`, `add_project_task`, `remove_project_task`, `check_project`,
  `download_project`, `get_project_status`, `verify_project` — przypięcia wersji po
  SHA-256, blokada `.imgw-project.lock`.
- **Parsery meteo i normalizacja**: `parse_meteo_climate_daily`,
  `parse_meteo_precip_daily`, `normalize_archive`, rekordy `NormalizedRecord` z flagami
  `value|missing|no_phenomenon|accumulated`; `summarize_coverage` (pokrycie per stacja ×
  zmienna, luki).
- **Otwarte dziedziny kontraktów `/1` (ADR-003, C01)** — przygotowanie dostawcy ČHMÚ
  w 3.1.0 bez zmiany bajtów IMGW: klucz zbioru `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`
  (`imgw-meta/1`, `imgw-series/1`), `country` `^[A-Z]{2}$`, `provider` i `license.id`
  dowolnym niepustym tekstem (`License.id: str`), kod stacji 9 cyfr IMGW albo identyfikator
  WIGOS (`imgwtools.datasets.STATION_CODE_PATTERN`; klucze i pliki `series.json`,
  `stations.geojson`, `files[].station_code` projektu, opcje `station`/`stations`
  katalogu — `current hydro|meteo` przyjmują nadal wyłącznie 9 cyfr IMGW), wartości
  `location_source` ČHMÚ w `stations.geojson`. Sidecar zbioru znanego rejestrowi musi mieć
  `country` i `provider` z rejestru (inaczej `invalid_meta`); poprawny klucz nieznanego
  zbioru daje `unknown_entry`.
- **Treść kanoniczna** (ADR-003 D17): opcjonalne, zawsze wspólne pola `content_sha256`
  (64 hex) i `content_form` w sidecarze `imgw-meta/1` (`Meta.content_sha256`,
  `Meta.content_form`) i w pinach `imgw-project/1` (`ProjectFile`; `open_project`
  zachowuje je przy ponownym zapisie manifestu); jedno pole bez drugiego → `invalid_meta`
  (sidecar) albo `validation_error` (manifest). Zbiory IMGW ich nie zapisują.
- **Rejestr obserwacji `imgw-observation/1`** (ADR-003 D18): katalog `observations/`
  w slocie archiwum (pliki `<YYYY-MM-DD>_<sha8>.json`) nie jest wersją — `current_version`,
  `read_meta`, czytniki szeregów i projektów oraz wybór wersji slotu w `write_archive`,
  `build_catalog` i `build_series` go pomijają; `iter_store` zwraca poprawne obserwacje
  jako `StoreEntry(kind="observation", observation=Observation(…))`, a błędne jako
  problemy (`unknown_entry`, `symlink`, `unreadable`, `invalid_json`, `unknown_schema`,
  `invalid_meta`); `store scan --kind observation`;
  `store_info().contracts["observation"]`. Zapis obserwacji wchodzi z dostawcą ČHMÚ (3.1.0).
- **`imgwtools.testing`**: `build_fixture_store` — publiczny, offline budowniczy magazynu
  testowego (warianty `complete`, `corrupt`, `unknown_schema`) z nagranymi odpowiedziami;
  `fixture_files()` — archiwa, nagrania (także `contract_recordings.json` z odpowiedziami
  endpointów live) i `contract_schemas.json` (JSON Schemas z przykładami dokumentów
  magazynu, `imgw-result/1`, `problem+json` i `cli-error`) dla konsumentów (Archiwista,
  Retman).
- **Wyjątki**: `IMGWStoreError`, `IMGWStoreConflictError`, `IMGWStoreDependencyError`
  (instrukcja `pip install imgwtools[store]`), `IMGWProjectError`, `IMGWCancelledError`.
- **Dodatek** `imgwtools[store]` = `pyarrow>=15` (tylko ścieżki Parquet; import rdzenia
  nie wymaga pyarrow, fastapi ani typer).

### Zachowanie magazynu

- `build_catalog` sprawdza zapisane listy stacji (`lista_stacji_hydro.csv`,
  `wykaz_stacji.csv`) przez `HEAD` tak jak `check_catalog`: lista zmieniona (inny
  ETag/Last-Modified) lub bez porównywalnego sygnału jest pobierana i zapisywana przez
  `write_archive` przed budową katalogu (identyczne bajty → `unchanged`), więc raport
  `newer` z `check_catalog` usuwa kolejna budowa.
- Katalog stacji zachowuje kody znane wyłącznie z lokalnego pliku statycznego
  `hydro_stations_locations.csv` (wpis `hydro` bez nazwy, `active=false`, położenie
  `static`); kody wyłącznie z pliku użytkownika trafiają do `problems` (plik ten tylko
  uzupełnia położenia).
- `summarize_coverage` i `series.json`: w zbiorach miesięcznych i półrocznych
  miesiąc/okres posiadanego archiwum, w którym stacji brak (a inne stacje są), jest luką
  w `gaps` — jak dni w zbiorach dobowych; dla półrocza jednostkę uznaje się za posiadaną
  per zmienna (osobne archiwa `polr_H/Q/T`).
- `build_series` zwraca `reused` wyłącznie dla bieżącej wersji szeregu; gdy archiwum
  wróci do wcześniejszej treści, powstaje nowa wersja, która staje się bieżąca.
- `write_archive`: powrót wcześniejszego sygnału HTTP przy tych samych bajtach (ETag
  E1→E2→E1) daje `unchanged`, nie kolejną wersję `+<8 hex>`; wersja z sidecarem bez
  `extra.http` daje `IMGWStoreConflictError`.
- Sprzątanie `.incoming/` (staging starszy niż 24 h) toleruje równoległe usunięcie przez
  inny proces i zgłasza każdy usunięty katalog przez `on_notice` kodem
  `leftover_incoming` (`write_archive`, `build_series`, `build_catalog`, `sync_pmaxtp`).
- Kontrola katalogów Kartografa przed zapisem nie przegląda własnych drzew wersji
  magazynu (`archives/`, `series/`, `stations/`, `pmaxtp/`, `.incoming/`): koszt zapisu
  nie rośnie z liczbą wersji, a uszkodzony sidecar w innym slocie nie blokuje zapisów.
- `init_store` na systemie plików bez dowiązań twardych (SMB, FAT) zgłasza
  `IMGWStoreConflictError` (`details.reason="not_atomic"`) z polskim komunikatem.
- `iter_store` zgłasza wersję szeregu z nieobsługiwanym `extra.series_schema`
  (np. `imgw-series/2`) jako problem `unknown_schema`; `current_version` dla takiego
  slotu kończy się `IMGWDataError`.
- Bezpieczeństwo: `StorePlan.from_json` (także plan przekazany w
  `POST /api/v1/store/sync`) odrzuca pozycje, których `url` różni się od adresu
  z rejestru zbiorów — zapytania HEAD/GET trafiają wyłącznie na serwery IMGW.
- `export_series` i `export_archive` tworzą pliki z uprawnieniami zgodnymi z umask
  (np. 0644); ścieżka wewnątrz magazynu → `validation_error`.

### Schematy i polityka wersji (IMGW-13)

| Schemat | Plik |
|---|---|
| `imgw-store/1` | `<root>/imgw-store.json` — znacznik magazynu |
| `imgw-meta/1` | `<plik>.meta.json` — sidecar każdej wersji (opcjonalnie `content_sha256` + `content_form`) |
| `imgw-series/1` | `series.json` — spis szeregu Parquet (+ metadane Parquet) |
| `imgw-plan/1` | `plan.json` — plan aktualności poza magazynem |
| `imgw-project/1` | `imgw-project.json` — manifest projektu (opcjonalnie `content_sha256` + `content_form` pinu) |
| `imgw-pmaxtp/1` | `cell.json` — rozszerzenie IMGWTools dla komórki PMAXTP |
| `imgw-observation/1` | `observations/<YYYY-MM-DD>_<sha8>.json` — rejestr obserwacji sygnału w slocie archiwum |
| `imgw-result/1` | koperta wyniku `run_command`/`check_command`, stdout CLI i ciało REST |
| `imgw-commands/1` | dokument `command_schema()` |

Każdy schemat ma własny licznik `/N`, niezależny od wersji pakietu. W ramach `/1`
dochodzą wyłącznie pola opcjonalne; czytniki tolerują dodatkowe pola w plikach magazynu,
ale manifest projektu jest walidowany ściśle (nowe opcjonalne dane tylko w mapie
`extensions`). Zmiana niezgodna wymaga `/2`, okresu odczytu `/1` i `/2` oraz osobnych
testów kontraktu; stary kod nie zapisuje do nieznanego znacznika. `store_info` zgłasza
nieobsługiwaną wersję (`supported=False`), skan raportuje problem i nie parsuje plików
nieznanego schematu. W linii 3.x publiczne funkcje odczytu nie znikają, a semantyka `/1`
się nie zmienia. Dziedziny wartości `/1` (klucz zbioru, kraj, dostawca, licencja, kod
stacji, `location_source`) są otwarte na kolejnych dostawców — patrz „Dodane”.

### Zmienione

- Domyślnie serwer nadal tylko generuje URL-e do IMGW; dane trafiają na dysk wyłącznie
  po jawnym wskazaniu magazynu (`--root`, `IMGW_STORE_ROOT`) lub katalogu `--output`.
- URL-e archiwów (biblioteka, CLI, REST, web) wynikają wyłącznie z rejestru
  `archive_files`, bez zahardkodowanej górnej granicy roku.
- Lista stacji hydro zachowuje `river_order` (czwarta kolumna CSV) i `hydrographic_code`.

### Poprawione

- `API_VERSION` w REST (`/health`, `/api/v1`, OpenAPI) równa się `__version__` zamiast
  stałego `1.0.0`; stopka web i log `app.js` nie podają już stałego `v1.0.0`.
- Dane bieżące czytają rzeczywiste pola API IMGW (`stacja`, `kod_stacji`,
  `temperatura_powietrza`, `wiatr_srednia_predkosc`, `wilgotnosc_wzgledna`, `opad_10min`),
  więc nazwy stacji i pomiary nie są już puste; `HydroCurrentData` czyta bieżące klucze
  `wojewodztwo` i `przeplyw_data` (wcześniej `province` i `flow_date` były zawsze `None`).
- Niepoprawny JSON z API IMGW: `fetch_*` zgłaszają `IMGWDataError` (`data_error`) zamiast
  surowego `JSONDecodeError`.
- `read_meta` odrzuca sidecar z polem `dataset` spoza wzorca klucza rejestru (spec §11.2).
- `fetch_pmaxtp`/`fetch_pmaxtp_async` nie zwracają już pustych tabel `ks/sg/rb` jako
  sukcesu: odpowiedź z polem `error` lub bez tabeli `ks` daje wyjątek. Punkt w ramce
  współrzędnych, ale poza siatką PMAXTP (np. Kaliningrad, Lwów, Bałtyk; API: „Brak
  pliku, pradopodobnie poza obszarem PL”) daje `IMGWValidationError` także w `sync_pmaxtp`
  (CLI 2, REST 400); inne błędy API pozostają `IMGWDataError`, błędy sieci
  `IMGWConnectionError`. Współrzędne spoza Polski są odrzucane przed wysłaniem żądania.
- `fetch_pmaxtp` i `fetch_pmaxtp_async` zgłaszają współrzędne spoza zakresu Polski
  po polsku, tym samym komunikatem co `sync_pmaxtp`/`check_pmaxtp`
  (np. „Szerokość geograficzna 40.0 poza zakresem Polski (49.0–55.0)”).
- Jednakowy komunikat (kod i tekst) trafia do koperty i na stderr CLI raz na komendę
  (np. `license_terms` przy synchronizacji setek archiwów); hooki `on_notice` Pythona
  nadal dostają każdy komunikat.
- REST ukrywa w tekstach (`problems`, `detail`, `error`) także katalog `IMGW_DATA_DIR`
  (np. brakujący plik położeń w `POST /api/v1/store/catalog`), nie tylko
  `IMGW_STORE_ROOT` i `IMGW_USER_LOCATIONS_DIR`.
- `set_project_store` (`imgw project set-store`) przyjmuje nowy pusty magazyn (brak
  katalogu, pusty katalog, magazyn bez wersji) z ostrzeżeniem `pins_not_in_store`;
  `download_project` odtwarza wtedy przypięte pliki z identycznym SHA-256 albo zgłasza
  jawny błąd zadania. Niepusty magazyn bez identycznych pinów nadal jest odrzucany.
- Katalog stacji zgłasza w `problems` kod powtórzony na liście stacji (IMGW podaje
  w `wykaz_stacji.csv` trzy stacje meteo dwukrotnie z różnymi kodami krótkimi) i używa
  pierwszego wiersza; wcześniej ostatni wiersz wygrywał bez śladu.
- `pl.imgw.meteo_climate_daily`: `normalize_archive`, `read_archive` i `build_series`
  czytają tylko pliki `k_d_<okres>.csv` (`o_d_<okres>.csv` dla opadu). Wcześniej
  dopasowywały też `k_d_t_*.csv`, obecny w każdej paczce klimatycznej 1951–2025, i 330
  z 350 archiwów kończyło się błędem „Za mało kolumn”.
- `pl.imgw.hydro_semiannual`: układ kolumn dat `polr_*` jest rozpoznawany per plik —
  16 kolumn (1951–2022: rok, miesiąc, dzień, godzina bez minut), 17 z powtórzonym rokiem
  hydrologicznym (1997), 2023 z nieopisanym polem po dacie i obciętymi pustymi kolumnami
  (17/19/20), 18 od 2024; niejednolity lub nieznany układ to `IMGWDataError`. Wcześniej
  145 z 225 archiwów kończyło się błędem, a w pozostałych data końca ekstremum była zawsze
  pusta. Teraz wszystkie 225 archiwów 1951–2025 dają datę końca wszędzie, gdzie IMGW ją
  podaje; data ma dokładność publikacji (brak dnia lub miesiąca → początek jednostki,
  godzina 24 → północ następnego dnia, dzień 31 w krótszym miesiącu → jego ostatni dzień).
- `pl.imgw.hydro_semiannual`: wiersze min/max powtórzone przez IMGW dla kolejnych
  wystąpień ekstremum (ta sama wartość, inne daty) nie przerywają już budowy szeregu
  („Sprzeczne daty ekstremum”). `normalize_archive` scala je w jeden rekord z
  najwcześniejszym początkiem i najpóźniejszym końcem oraz liczbą wierszy w nowym polu
  `NormalizedRecord.extrema_occurrences`; Parquet dostaje addytywną kolumnę
  `<V>_occurrences` (`int32`, `imgw-series/1`), a `read_series`, eksport CSV,
  `export_archive` (`store export`) i `series read` — `<V>_occurrences`
  / `extrema_occurrences`. Różne wartości tego samego klucza nadal są błędem danych.
- Parsery meteo pomijają pierwszy wiersz złożony z kodów kolumn (np. `kansp,kapost,…`
  w `o_d_08_2025.csv`, wcześniej „Niepoprawny kod stacji”); każdy inny błędny wiersz
  nadal daje `IMGWDataError` z numerem linii.
- `build_series` nie trzyma wartości wszystkich stacji w pamięci: zweryfikowane rekordy
  trafiają do skompresowanych plików tymczasowych per stacja poza magazynem (`TMPDIR`),
  a stacje są składane i zapisywane po kolei. Szczyt RSS dla pełnych roczników 1950–2025:
  `meteo_precip_daily` (26,6 mln rekordów) 0,85 GB zamiast 9,0 GB, `hydro_daily` 0,41 GB
  zamiast 6,8 GB; `series.json` i pliki Parquet bajtowo bez zmian.
- `build_catalog` obejmuje też każdy kod stacji z bieżących indeksów `series.json`
  wszystkich zbiorów: stacje znane wyłącznie z archiwów (np. zamknięte wodowskazy
  i umowny kod IMGW `123456789` z `mies_1997`) trafiają do `stations.geojson` jako
  historyczne (`active=false`, `geometry=null`, `location_missing_reason="none"`),
  z liczbą w nowym polu `CatalogReport.from_series`, komunikatem `series_station`
  i wpisami `series` w `extra.catalog[]` sidecara; `check_catalog` zgłasza `newer`, gdy
  kodu szeregu brakuje w katalogu. Wersja katalogu zmienia się tylko przy zmianie treści.
- `imgw store export … | head` i `imgw series export … | head` kończą się kodem 0 bez
  komunikatu, gdy odbiorca zamknie potok.
- Nieczytelna wersja (np. `PermissionError` na `series.json` lub pliku Parquet) daje
  `io_error` zamiast `data_error`/`conflict`, z jednakową treścią (polski powód,
  `details.path`) w CLI i REST.
- JSON koperty (`CommandResult.to_json`, stdout CLI, ciało REST) zapisuje względne ścieżki
  wyniku — przypięcia `files[].path` w wynikach `project *` — jako względne do magazynu
  projektu, niezależnie od katalogu roboczego; wcześniej były absolutyzowane wobec
  katalogu roboczego procesu drukującego (nieistniejące ścieżki `<CWD>/series/versions/…`).

### Testy

- Kontrakt magazynu w `tests/contract/` (offline: HEAD → plan → sync → szeregi → katalog
  → CSV → projekt → verify/restore, JSON Schemas §11 dołączone do pakietu).
- Kontrakt międzyinterfejsowy `tests/contract/test_interface_contract.py`: dla wszystkich
  25 komend REST koperta `run_command` = stdout CLI = ciało REST, strumienie bajt w bajt,
  zapis do świeżych magazynów daje identyczne drzewa, `?check=true` = `--check` =
  `check_command`, macierz 12 kodów błędów (kod wyjścia, status HTTP, tytuł, schematy
  `cli-error` i `problem+json`), okna stronicowania.
- Regresja na żywo `tests/live/test_interfaces_live.py` (`IMGW_LIVE=1`, raport JSON przez
  `IMGW_LIVE_REPORT`): każda z 35 komend przez Python, zainstalowany `imgw` i REST
  (`imgw server`) na serwerach IMGW w świeżym magazynie oraz 6 błędów na żywo.
- 1419 testów (`pytest --collect-only`, 2026-10-18): 1377 offline i 42 na żywo.

## [2.2.0] — 2026-08-22

### BREAKING

- **Extras `[spatial]` → `[pandas]`.** `pip install imgwtools[spatial]` przestaje działać;
  zależności `pyproj`/`pyshp` porzucone.
- **Usunięty `core/imgw_spatial.py`** (klasa `StationMap`, poza publicznym API, bez
  zamiennika).
- **Usunięty `core/imgw_api.py`** (DEPRECATED od 2.0.0). Zamienniki: `HYDRO` →
  `fetch_hydro_current()`, `SYNOP` → `fetch_synop()`, `METEO` → `fetch_synop()` /
  `fetch_hydro_current()`, `WARNINGS` → `fetch_warnings()`, `PMAXTPAPI` → `fetch_pmaxtp()`.
- **Usunięty `core/imgw_datastore.py`** — zamiast `DataDownloader` użyj
  `download_hydro_data()` lub `download_meteo_data()`.

### Zmienione

- Ręczny proces CLA (`docs/CLA.md`, `CONTRIBUTING.md`, `CONTRIBUTORS.md`, szablon PR).
- Moduł `imgwtools.reference_data` (`python -m imgwtools.reference_data`); dane IMGW
  usunięte z repozytorium.
- Metadane licencji zgodne z PEP 639 (`license = "MIT"`, `license-files`).
- Sekcja README o źródłach danych i atrybucji IMGW-PIB.
- Docstringi NumPy w całym `src/` wymuszane regułami `D` w ruff; `ruff format` na całym
  repozytorium.
- `imgw version` czyta `__version__`; `imgw list datasets` bez zahardkodowanego roku
  końcowego.

## [2.1.1] — 2026-07-06

- Parsery archiwów hydro: auto-detekcja separatora, kodowania (UTF-8 z BOM) i wierszy
  w cudzysłowach.
- URL-e meteo zgodne z rzeczywistym układem serwera IMGW.
- Zgodność z pyright; audyt dokumentacji.

Starsze wydania: `docs/PROGRESS.md` (sekcja „Wydane wersje”).
