# Changelog — IMGWTools

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersjonowanie
zgodne z [SemVer](https://semver.org/lang/pl/). Każda zmiana publicznego API i schematów
magazynu (`imgw-*/N`) trafia do tego pliku (ADR-001, polityka IMGW-13).

## [3.0.0] — 2026-10-19

Wersjonowany magazyn danych IMGW zastępuje opcjonalny cache SQLite (ADR-001), a Python,
CLI, REST i web korzystają z jednego katalogu komend z jedną kopertą wyniku i jednym
rejestrem kodów błędów (ADR-002). Drugim dostawcą obok IMGW-PIB jest czeski ČHMÚ
(opendata.chmi.cz, ADR-003): zbiory `cz.chmi.*` w tych samych kontraktach, magazynie
i komendach; dziedziny kontraktów `/1` otwarto przed tagiem (C01). Agenci AI dostają
przewodnik `AGENTS.md`/`llms.txt`, angielskie opisy katalogu, metadane skutków komend
i serwer MCP (ADR-004). Rejestr liczy 17 zbiorów dwóch dostawców, a katalog — 37 komend.
Decyzje: `docs/DECISIONS.md`; kontrakty: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`
(§13 — spójność interfejsów, §13.11 — pełne tabele migracji),
`2026-10-18-chmi-provider-design.md` (ČHMÚ) i `2026-10-19-agent-support-design.md`
(agenci). Wydanie nie ma aliasów ani shimów starych nazw.

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

#### Wobec stanu gałęzi przed ADR-003 i ADR-004 (commit `d8cb11c`)

Dotyczy integracji pisanych na gałęzi przed dodaniem dostawcy ČHMÚ i wsparcia agentów.

| Było | Jest |
|---|---|
| `datasets()` → 13 deskryptorów IMGW-PIB | 17 deskryptorów, także `cz.chmi.*`; widok jednego dostawcy: `datasets(provider="IMGW-PIB")` |
| `find_stations(...)` na żywo pyta wyłącznie listy IMGW-PIB | bez `provider` pyta IMGW-PIB i ČHMÚ (metadane `now` z opendata.chmi.cz); tylko IMGW-PIB: `provider="IMGW-PIB"` (CLI `--provider IMGW-PIB`) |
| tytuł `source_unavailable` „Źródło IMGW niedostępne” | „Źródło danych niedostępne”; `detail` nazywa dostawcę i URL |
| `ErrorSpec(code, title, exit_code, http_status)` | + wymagane `title_en` |
| `command_schema()`: `years` w `required` komend `datasets files\|download` i `store check\|sync`; `oneOf` komendy `store sync` = `plan` \| `datasets`+`years` | `years` poza `required` (wymagalność zależy od zbioru, opis w `x-imgw.rules`); `oneOf` = `plan` \| `datasets` |
| `archive_files`, `download_archives`, `check_store` bez `years` → `TypeError` | `years=None` w podpisie; brak wymaganego `years` → `IMGWValidationError` (`details.option="years"`) |
| `DownloadItem.status` `downloaded\|failed\|cancelled`; pozycje i zadania `ProjectReport` bez odtworzenia treścią | nowe wartości: `not_published` (sukces pozycji pobierania), `restored_by_content` (sukces pozycji projektu), stan zadania `content_match` |
| `Measurement(value, flag)` | + `quality`, `source_flag` (`None` poza `cz.chmi.meteo_daily`) |
| błąd odtworzenia „IMGW udostępnia inną treść …” | „IMGW-PIB udostępnia inną treść …” (nazwa dostawcy z rejestru) |
| pomoc CLI z angielskimi elementami Typer/Click („Options”, „Usage:”, `[OPTIONS]`, „Aborted.”) | po polsku („Opcje”, „Użycie:”, `[OPCJE]`, „Przerwano.”), po angielsku z `IMGW_LANG=en`; `IMGW_LANG` spoza `pl\|en` → `validation_error` (kod 2) w każdym wywołaniu `imgw` |
| `/openapi.json` z trasami stron HTML web GUI | strony HTML poza dokumentem OpenAPI |

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

- **`imgwtools[full]`** obejmuje `store` (`pyarrow>=15`) i `mcp` obok `api`, `cli`, `pandas`.
- Nowy dodatek **`imgwtools[mcp]`** = `imgwtools[cli]` + `mcp>=2.3,<3` (serwer MCP, ADR-004).

### Dodane

- **Wersjonowany magazyn** (`imgwtools.store`, re-eksport w `imgwtools`): niezmienne,
  tylko przyrostowe wersje archiwów IMGW 1:1 z sidecarem `*.meta.json` (SHA-256, rozmiar,
  nagłówki HTTP, licencja IMGW-PIB), publikacja ze stagingu `.incoming/` dowiązaniami
  twardymi bez zastępowania celu, z sidecarem pliku głównego dowiązywanym na końcu
  (zatwierdza wersję; model Kartografa), wykrywanie katalogów Kartografa bez jego importu.
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
- **Rejestr dostawców i zbiorów** `imgwtools.datasets`: `datasets(*, kind=None, provider=None)`,
  `get_dataset()` (klucz, slug albo alias legacy), `archive_files()`, `station_source_files()`,
  `DatasetDescriptor`, `ArchiveFile`, `License`, `YearsArg`/`MonthsArg` (`2024`,
  `"2020-2023"`, `"2020,2022"`, listy). 17 deskryptorów: 13 IMGW-PIB — pięć zbiorów
  archiwalnych magazynu (`pl.imgw.hydro_daily`, `pl.imgw.hydro_monthly`,
  `pl.imgw.hydro_semiannual`, `pl.imgw.meteo_climate_daily`, `pl.imgw.meteo_precip_daily`),
  listy stacji (`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`), PMAXTP
  (`pl.imgw.pmaxtp`) i pięć zbiorów tylko do pobrania (`pl.imgw.hydro_phenomena`,
  `pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`,
  `pl.imgw.meteo_synop_monthly`, `pl.imgw.meteo_climate_terms`) — oraz 4 ČHMÚ
  (`cz.chmi.*`, sekcja „Dostawca ČHMÚ” niżej).
- **`download_archives(dataset, /, *, years, months, params, stations, output)`** →
  `DownloadReport`/`DownloadItem` (slot, URL, status, ścieżka, `error_code`): pobieranie
  płaskie w układzie ścieżek serwera dostawcy, zapis przez `.part` i `os.replace`, komunikat
  `license_terms` po pobraniu.
- **Dane na żywo**: `find_stations`/`find_stations_async` (listy stacji na żywo albo
  z magazynu, `source="live"|"store"`, `provider` — IMGW-PIB, ČHMÚ albo obaj; wyszukiwanie
  bez wielkości liter i znaków diakrytycznych),
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
- **Katalog komend** `imgwtools.commands`: 37 komend w grupach `datasets`, `stations`,
  `current`, `pmaxtp`, `store`, `series`, `project`, `commands` (35 z ADR-002,
  `datasets providers` z ADR-003 i `commands guide` z ADR-004); `command_schema(command=None)`
  (JSON Schema opcji + `x-imgw`: funkcja, bliźniak check, typ wyniku, flagi CLI, trasa REST,
  reguły; dokument `imgw-commands/1` z kodami błędów i wyjścia), `data_commands`,
  `validate_command`, `format_command`, `check_command`, `run_command` → `CommandResult`
  (koperta `imgw-result/1`: `status` `ok|partial|failed|cancelled`, `result`, `notices`
  bez powtórzeń). **Stronicowanie**: 12 komend listowych zwraca `Page`
  (`items`, `total`, `limit`, `offset`) z opcjami `limit`/`offset`.
- **CLI** generowane z katalogu (`cli/_dispatch.py`): koperta JSON na stdout, strumienie
  `store export`/`series export`, błąd jako JSON na stderr, kody wyjścia z rejestru,
  `--check` przy komendach z bliźniakiem, `--schema` przy każdej, `--root` z
  `IMGW_STORE_ROOT`, listy po przecinku albo powtórzona flaga; Ctrl+C anuluje między
  plikami (130).
- **REST** generowane z katalogu (`/api/v1/<grupa>/<komenda>`, 27 tras; `GET /api/v1`
  wypisuje trasy): ta sama koperta co CLI, `application/problem+json`, `?check=true`
  przy `POST`, `limit` domyślnie i najwyżej `IMGW_API_MAX_LIMIT` (1000). Komendy magazynu
  wyłącznie na serwerowym, absolutnym `IMGW_STORE_ROOT` (bez niego 503); zapis wymaga
  `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` i nagłówka `X-API-Key`; CSV
  współrzędnych użytkownika tylko z `IMGW_USER_LOCATIONS_DIR`. Odpowiedzi nie ujawniają
  katalogów serwera (ścieżki względne do root, także w tekstach).
- **Web GUI** wyłącznie na publicznym API: formularz archiwów z rejestru (10 zbiorów IMGW-PIB),
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
- **Otwarte dziedziny kontraktów `/1` (ADR-003, C01)** — podstawa dostawcy ČHMÚ bez zmiany
  bajtów IMGW: klucz zbioru `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`
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
- **Konwencja kluczy zbiorów (IMGW-20, ADR-001 errata 2026-10-18)**: wzorzec
  `imgwtools.datasets.DATASET_KEY_PATTERN` (test na całym rejestrze i na
  `pl.imgw.stations`), niezmienność opublikowanych kluczy i tabela zmienionych nazw
  `DATASET_KEY_ALIASES` (stary → bieżący klucz; pusta w 3.0.0, każdy wpis w tej historii
  zmian) z `resolve_dataset_key`; `get_dataset` i odczyty magazynu przyjmują klucze
  z tabeli. `read_meta` zwraca obok surowego `dataset` pole `Meta.dataset_key` (także
  w kopertach CLI/REST): bieżący klucz albo `null` dla poprawnego, lecz nieznanego
  klucza — bez wyjątku i bez `invalid_meta` w skanie.
- **Rejestr obserwacji `imgw-observation/1`** (ADR-003 D18): katalog `observations/`
  w slocie archiwum (pliki `<YYYY-MM-DD>_<sha8>.json`) nie jest wersją — `current_version`,
  `read_meta`, czytniki szeregów i projektów oraz wybór wersji slotu w `write_archive`,
  `build_catalog` i `build_series` go pomijają; `iter_store` zwraca poprawne obserwacje
  jako `StoreEntry(kind="observation", observation=Observation(…))`, a błędne jako
  problemy (`unknown_entry`, `symlink`, `unreadable`, `invalid_json`, `unknown_schema`,
  `invalid_meta`); `store scan --kind observation`;
  `store_info().contracts["observation"]`. Obserwacje zapisuje `write_archive` w slotach
  zbiorów z formą kanoniczną (ČHMÚ, niżej).
- **`imgwtools.testing`**: `build_fixture_store` — publiczny, offline budowniczy magazynu
  testowego (warianty `complete`, `complete_pl_cz`, `corrupt`, `unknown_schema`) z nagranymi
  odpowiedziami; `fixture_files()` — archiwa, listingi i nagrania (także
  `contract_recordings.json` z odpowiedziami endpointów live oraz `chmi_recordings.json`,
  `chmi_catalog_recordings.json`, `chmi_builder_recordings.json`) i `contract_schemas.json`
  (JSON Schemas z przykładami dokumentów magazynu, `imgw-result/1`, `problem+json`
  i `cli-error`) dla konsumentów (Archiwista, Retman).
- **Wyjątki**: `IMGWStoreError`, `IMGWStoreConflictError`, `IMGWStoreDependencyError`
  (instrukcja `pip install imgwtools[store]`), `IMGWProjectError`, `IMGWCancelledError`.
- **Dodatek** `imgwtools[store]` = `pyarrow>=15` (tylko ścieżki Parquet; import rdzenia
  nie wymaga pyarrow, fastapi ani typer).

#### Dostawca ČHMÚ (ADR-003, C02–C09)

- **Rejestr dostawców**: `ProviderDescriptor` (`id`, `short_name`, `name`, `country`,
  `key_prefix`, `base_url`, `license`, `processed_attribution`, `notice`,
  `station_code_pattern`, `datasets`), `providers()` i `get_provider(id | key_prefix)`
  (nieznany dostawca → `validation_error` z `details.allowed`); dostawcy `IMGW-PIB` (PL,
  `pl.imgw`) i `CHMI` (CZ, `cz.chmi`, nazwa wyświetlana „ČHMÚ”, licencja CC BY 4.0
  z `License.terms_url`). `station_source_files(provider=…)`, `STATION_CODE_PATTERN`
  (9 cyfr IMGW-PIB albo identyfikator WIGOS). W `imgwtools.__all__`: `ProviderDescriptor`,
  `providers`, `get_provider`, `STATION_CODE_PATTERN`, `parse_chmi_hydro_daily`,
  `parse_chmi_meteo_daily`, `parse_chmi_stations`.
- **Zbiory `cz.chmi.*`**: `cz.chmi.hydro_daily` (H [cm], Q [m3/s], T [°C]; plik JSON na
  stację i rok kalendarzowy, od 1887), `cz.chmi.meteo_daily` (P [mm], Tmean, Tmax, Tmin [°C]
  z `historical_csv`; cztery pliki CSV na stację — SRA, T, TMA, TMI — z całą historią
  stacji), listy stacji `cz.chmi.hydro_stations` i `cz.chmi.meteo_stations`
  (`historical/metadata/meta1.json`). `DatasetDescriptor` + `provider`, `archive_scope`
  (`country|station_year|station_element`), `variable_notes` (konwencje doby i terminów),
  `measurement_fields`, `content_form`, `volatile_fields`, `update_signal="listing"`;
  `ArchiveFile.station_code`. `archive_files(…, stations=[…])`: kandydaci stacja × rok
  (hydro) albo cztery pliki na stację (meteo, bez `years`); `months` i `params` wyłącznie
  dla IMGW-PIB. Kod stacji ČHMÚ to identyfikator WIGOS z nazw plików (np. `0-203-1-001000`).
- **Aktualność z listingu**: `check_store`/`sync_store(…, stations=…)` dla `cz.chmi.*` —
  jedno GET listingu katalogu serwera na zbiór (meteo: `precipitation/` i `temperature/`)
  zamiast HEAD każdego pliku; `current|newer|missing` z pary (czas listingu co do minuty,
  rozmiar) wobec sygnału odniesienia slotu; para stacja × rok spoza listingu →
  `unverifiable` z `error="nieopublikowany"`, stacja bez plików → akcja planu; `years`
  opcjonalne dla hydro (brak = lata opublikowane), zabronione dla meteo; jedno wywołanie
  obejmuje archiwa krajowe IMGW-PIB albo pliki stacji ČHMÚ. Plan `imgw-plan/1` ma nowe pola
  pozycji `station_code`, `signal` (`listing`|`head`), `remote_listed_at`,
  `local_observation` i pole `requests` (`made`, `planned`; także dla IMGW-PIB);
  `sync_store` wykonuje HEAD przed GET (zmiana od planu albo 404/410 → `stale_plan`).
  Żądania do ČHMÚ mają `User-Agent: imgwtools/<wersja>` i idą po kolei.
- **Treść kanoniczna i obserwacje**: forma `chmi-json/1` (JSON bez kluczy `zaznamID`
  i `datumVytvoreni`, zapis RFC 8785/JCS) dla `cz.chmi.hydro_daily` i list stacji ČHMÚ —
  `write_archive` zapisuje `content_sha256`/`content_form` w sidecarze, a inne bajty o tej
  samej treści co bieżąca wersja dają `unchanged` bez nowej wersji, z komunikatem
  `content_unchanged` (`info`) i — przy nowym sygnale — plikiem
  `observations/<YYYY-MM-DD>_<sha8>.json` (`VersionResult.observed_sha256`,
  `VersionResult.observation`), więc następne `check_store` daje `current` bez pobierania;
  bajty niezgodne z formą → `data_error` bez zapisu. Sidecary ČHMÚ: `country`, `provider`
  i `license` z rejestru, `request.station_code`/`param`, `extra.period.station_code`;
  `read_meta` → `Meta.provider`, `Meta.country`. Sidecary IMGW bajtowo bez zmian.
- **Katalog stacji ČHMÚ**: `build_catalog`/`check_catalog(…, provider="CHMI")` →
  `stations/versions/chmi_stations/<label>_<sha8>/stations.geojson`, slot
  `catalog:cz.chmi.stations`. Źródła w kolejności pierwszeństwa: `hydrology/now/metadata/meta1.json`,
  `meta3.json` i archiwum `cz.chmi.hydro_stations`; najnowsze
  `meteorology/climate/now/metadata/meta1-<RRRRMMDD>.json` i archiwum
  `cz.chmi.meteo_stations`; plik użytkownika i indeksy szeregów ČHMÚ. Progi SPA
  w addytywnej właściwości `thresholds` (`drought`, `spa1`–`spa3`, `q50` — stan albo
  przepływ 50-letni), `hydrographic_code` = `HLGP4`, `active` = obecność w liście `now`,
  obrys Czech z Natural Earth w pakiecie (`czechia_border_wgs84.geojson`), komunikat
  `location_conflict`. `read_catalog(root=…, provider=…)`, `read_station_list(…,
  provider=…)`, `iter_store(…, provider=…)`, `StoreInfo.providers`, `StoreEntry.provider`,
  `StationFeature.provider`, `StationListEntry.provider`, `CatalogReport.provider`. Katalog
  IMGW-PIB na magazynie z danymi ČHMÚ jest bajtowo taki sam.
- **Szeregi, jakość i flagi**: `build_series` dla `cz.chmi.*` (`series/versions/chmi_hydro_daily/`,
  `chmi_meteo_daily/`) z ciągłym kalendarzem stacji; `series.json` + `stations[<kod>].periods`
  (okresy znane per stacja: lata posiadanych plików hydro, zakres wierszy plików meteo),
  `StationSeriesIndex.periods`, `summarize_coverage(…, station_periods=…)` — rok bez
  pliku (np. nieopublikowany) jest nieznany, nie jest luką. Meteo: `QUALITY` (0–5) i `FLAG`
  ČHMÚ dosłownie w `Measurement.quality`/`source_flag`, w kolumnach Parquet `<V>_quality`
  (`int8`) i `<V>_source_flag`, w CSV `export_series`/`export_archive` i w JSONL; ślad
  opadu (`FLAG` `T`, 0.0) = `value`, `0.0` bez flagi = `no_phenomenon`; wartości nie są
  poprawiane według jakości. Metadane Parquet `variable_notes`; atrybucja sidecarów
  szeregów i eksportów według dostawcy (ČHMÚ: formuła źródła i „Dane ČHMÚ zostały
  przetworzone (normalizacja i zmiana formatu)”); `extra.source_files[]` z polami treści
  wejść hydro.
- **Komendy i opcje**: `datasets providers` (`providers`, `GET /api/v1/datasets/providers`),
  `--provider` w `datasets list`, `stations find`, `store scan` i `store catalog`,
  `--stations`/`-s` w `datasets files|download` i `store check|sync`, reguły zbiorów
  w `x-imgw.rules`; `data_commands(provider=…)` (widok jednego dostawcy). `find_stations`
  na żywo czyta dla ČHMÚ metadane `now` (współrzędne źródła; „spindleruv” znajduje
  „Špindlerův Mlýn”), a z magazynu — listy i katalogi dostawców. `download_archives(…,
  stations=…)`: plik ČHMÚ bez publikacji (404/410) → pozycja `not_published` (sukces).
  `series *` i `project *` przyjmują zbiory `cz.chmi.*` i kody WIGOS (`series select`
  sprawdza gramatykę kodów dostawcy zbioru, a rok spoza okresów szeregu, także
  nieopublikowany, daje `validation_error`); `current *` i `pmaxtp *` pozostają wyłącznie
  IMGW-PIB.
- **Projekty i odtworzenie treścią**: zadania IMGW-PIB i ČHMÚ w jednym projekcie;
  `project download` synchronizuje stacje zadania ČHMÚ; piny zbiorów z formą mają
  `content_sha256`/`content_form`. Gdy przypiętej ścieżki brak, a bieżąca wersja slotu ma
  tę samą treść kanoniczną (szereg — te same bajty pod inną etykietą), pin ma stan
  `content_match`, pozycja status `restored_by_content` z wersją równoważną, a komunikat
  `pin_restored_by_content` (`warning`) podaje obie ścieżki i sumy; manifest w trybie
  `pinned` się nie zmienia (`update="upgrade"` przepina). `get_project_status(…, on_notice=…)`.

#### Wsparcie agentów AI (ADR-004, A01–A05)

- **Opisy angielskie i język**: `help_en`, `description_en`, `rules_en`, opisy grup,
  `ErrorSpec.title_en`, `DatasetDescriptor.title_en` (pole `title_en` w `datasets list`);
  `command_schema(command=None, /, *, lang="pl"|"en")` i opcja `lang` komend
  `commands schema` i `commands guide` (dokument `imgw-commands/1` z polem `lang`;
  `imgwtools.commands.LANGS`). CLI: `IMGW_LANG=pl|en` — pomoc komend, opisy grup, elementy
  Typer/Click i domyślne `--lang`. REST: `lang` z zapytania, inaczej nagłówek
  `Accept-Language`, inaczej `pl`; odpowiedzi z `Content-Language` i `Vary: Accept-Language`,
  `title` problem+json w języku nagłówka. Polski pozostaje domyślny; `detail`,
  `Notice.text`, postęp, CSV, web GUI i OpenAPI nie są tłumaczone, a język nie zmienia
  kontraktu (schematy obu języków różnią się wyłącznie tekstami).
- **Metadane skutków**: `DataCommand.writes` (`none|add|replace`), `DataCommand.network`,
  `CommandOption.writes`, `DataCommand.env_root_when` (wspólna reguła domyślnego `root`
  CLI i MCP); w schemacie `x-imgw.writes`, `x-imgw.network`, `x-imgw.operation_id`
  (`operationId` REST i nazwa narzędzia MCP) i `x-imgw-writes` opcji zapisujących. Każda
  komenda zapisująca ma bliźniaka `check`.
- **Przewodnik**: `agent_guide(*, format="agents"|"llms", lang="pl", path=None)`
  (w `imgwtools.__all__`) i komenda `commands guide` (`GET /api/v1/commands/guide`,
  strumień `text/markdown`); pliki pochodne `AGENTS.md` i `llms.txt` (llms.txt v2)
  w katalogu głównym repozytorium, generowane z katalogu, rejestrów i szablonów
  `src/imgwtools/_data/agents/` i pilnowane testem dryfu; `GET /llms.txt` serwera REST
  w języku z `Accept-Language`.
- **Serwer MCP**: dodatek `imgwtools[mcp]` i komenda `imgw mcp [--allow-writes] [--lang pl|en]`
  (stdio; zmienne `IMGW_MCP_ALLOW_WRITES`, `IMGW_LANG`; bez dodatku linia
  `missing_dependency`, kod 6). Narzędzie = komenda katalogu (nazwa `x-imgw.operation_id`,
  schemat wejścia z `command_schema`, adnotacje `readOnlyHint`, `destructiveHint`,
  `openWorldHint`); domyślnie tylko odczyt i plan — komendy zapisujące mają `check` stałe
  `true`, zapis wyłącznie z `--allow-writes` i `check: false` (inaczej `forbidden`,
  `details.reason="writes_disabled"`). `structuredContent` = koperta `imgw-result/1`,
  błąd = `{code, title, detail, details}` z `isError`, listy domyślnie po 50, strumienie do
  256 KiB, postęp i anulowanie; `root` jak w CLI (`IMGW_STORE_ROOT`). Punkt `/mcp`
  (Streamable HTTP) w `imgw server` przy `IMGW_MCP_ENABLED=true` (`IMGW_MCP_ALLOWED_HOSTS`,
  język z `IMGW_LANG`): narzędzia tras REST wywoływanych w procesie, wyłącznie odczyt
  i plan (POST zawsze z `?check=true`); `docker/nginx.conf` ma `location = /mcp`.
- **Porządek komunikatów**: polskie teksty z polskimi znakami w pomocy i komunikatach
  `imgw admin` (metawartości `IDENTYFIKATOR`, `TEKST`, `LICZBA`), pomocy `imgw version`
  i `imgw server` (`ADRES`, `LICZBA`), elementach pomocy Typer/Click („Opcje”, „Użycie:”,
  `[OPCJE]`, `KOMENDA [ARGUMENTY]...`, „Przerwano.”), opisach pól modeli w OpenAPI,
  wyjściu `python -m imgwtools.reference_data` (atrybucja IMGW-PIB z rejestru), opisach
  `/health` i `/api/v1` oraz nagłówku skryptu wget w web GUI; strony HTML web GUI nie należą
  już do `/openapi.json`.

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
- Katalog stacji IMGW-PIB podaje `meteo_kind` stacji meteorologicznej z bieżących
  szeregów: `climate` — stacja w szeregu `pl.imgw.meteo_climate_daily`, w przeciwnym
  razie `precipitation` — w szeregu `pl.imgw.meteo_precip_daily`, bez takiego szeregu
  `null` (ČHMÚ zawsze `null`); `check_catalog` zgłasza zmianę `meteo_kind` jako `newer`
  akcji indeksów szeregów (ADR-001, errata 2026-10-19).
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
- Magazyn wymaga systemu plików z dowiązaniami twardymi, tak jak magazyn Kartografa
  (jego ADR-036): wersje, obserwacje i znacznik `imgw-store.json` są publikowane
  `os.link`, które nigdy nie zastępuje celu, więc zapis działa na Linuksie, macOS
  i Windows (ext4, APFS, NTFS, udział SMB z dowiązaniami twardymi). System plików bez
  dowiązań (FAT, exFAT, część NAS i FUSE, klient SMB macOS) daje w `init_store` i każdym
  zapisie `IMGWStoreConflictError` (`details.reason="not_atomic"`) z polskim
  komunikatem; odczyt dowiązań nie wymaga. `fsync` katalogu jest pomijany na Windows
  i na systemach plików, które go nie obsługują (ADR-001, errata 2026-10-19).
- Katalog wersji bez sidecara pliku głównego to przerwana publikacja, nie wersja:
  `current_version` i zapis go pomijają, `iter_store` zgłasza go jako `missing_sidecar`
  (także gdy brakuje pliku głównego), a następny zapis tej samej treści pod tą samą
  etykietą go uzupełnia. Błąd albo Ctrl+C w trakcie publikacji nie usuwa dowiązanych
  plików danych (mógł je przejąć równoległy zapis tych samych bajtów i zatwierdzić
  swoim sidecarem) — zostaje przerwana publikacja, a znikają tylko puste katalogi
  utworzone przez ten zapis. Etykieta katalogu stacji to data budowy, a PMAXTP
  i archiwum bez `Last-Modified` — data pobrania (UTC): przerwaną publikację, której nie
  dokończy ponowienie innego dnia ani zapis innej treści, usuwa się ręcznie (cały
  katalog `<label>_<sha8>/` bez sidecara), gdy nie trwa żaden zapis do magazynu.
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

Pola addytywne dostawcy ČHMÚ i wsparcia agentów (bez nowego `/N`): `imgw-meta/1` —
`request.station_code`, `request.param`, `extra.period.station_code`, `license.terms_url`
(zapisywane tylko, gdy ustawione); `imgw-series/1` — `stations[<kod>].periods`, kolumny
Parquet `<V>_quality`/`<V>_source_flag` i metadane `variable_notes` (tylko zbiory
z `measurement_fields` lub notami); `stations.geojson` — właściwość `thresholds` (hydro
ČHMÚ); `imgw-plan/1` — `station_code`, `signal`, `remote_listed_at`, `local_observation`
pozycji i `requests` planu; `imgw-commands/1` — `lang`, `x-imgw.writes`, `x-imgw.network`,
`x-imgw.operation_id` i `x-imgw-writes`. Pliki IMGW-PIB zapisane tym wydaniem mają te same
bajty co bez dostawcy ČHMÚ.

### Zmienione

- Domyślnie serwer nadal tylko generuje URL-e do IMGW; dane trafiają na dysk wyłącznie
  po jawnym wskazaniu magazynu (`--root`, `IMGW_STORE_ROOT`) lub katalogu `--output`.
- URL-e archiwów (biblioteka, CLI, REST, web) wynikają wyłącznie z rejestru
  `archive_files`, bez zahardkodowanej górnej granicy roku.
- Lista stacji hydro zachowuje `river_order` (czwarta kolumna CSV) i `hydrographic_code`.
- Teksty licencji z rejestru dostawcy: komunikat `license_terms`, atrybucje sidecarów,
  szeregów, katalogu i eksportów CSV (IMGW-PIB — brzmienie bez zmian, ČHMÚ — CC BY 4.0
  z oznaczeniem przetworzenia); błędy pobrania i odtworzenia nazywają dostawcę.
- Web GUI pozostaje przy zbiorach IMGW-PIB: formularz archiwów pokazuje
  `datasets(provider="IMGW-PIB")`, a wyszukiwarka stacji pyta `provider="IMGW-PIB"`.
- `imgw --help`, opis OpenAPI i grupa `datasets` („Rejestr dostawców i zbiorów: lista,
  pliki i pobieranie”) wymieniają obu dostawców; `imgw --help` wymienia `imgw mcp`.

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
- Obraz Dockera da się zbudować: baza `python:3.12-slim` zamiast `python:3.11-slim`
  (pakiet wymaga Pythona ≥ 3.12), bez `COPY data/` (katalogu nie ma w repozytorium),
  kopiowane `pyproject.toml`, `README.md`, `LICENSE` i `src/`, instalacja `.[api,mcp]`,
  jeden proces uvicorn. `docker/docker-compose.yml` bez przestarzałego klucza `version`,
  z `IMGW_MCP_ENABLED`, `IMGW_MCP_ALLOWED_HOSTS` i `IMGW_LANG` z otoczenia
  `docker compose`.

### Testy

- Kontrakt magazynu w `tests/contract/` (offline: HEAD → plan → sync → szeregi → katalog
  → CSV → projekt → verify/restore, JSON Schemas §11 dołączone do pakietu).
- Kontrakt międzyinterfejsowy `tests/contract/test_interface_contract.py`: dla wszystkich
  27 komend REST koperta `run_command` = stdout CLI = ciało REST, strumienie bajt w bajt,
  zapis do świeżych magazynów daje identyczne drzewa, `?check=true` = `--check` =
  `check_command`, macierz 12 kodów błędów (kod wyjścia, status HTTP, tytuł, schematy
  `cli-error` i `problem+json`), okna stronicowania.
- Kontrakt MCP: `tests/contract/test_mcp_contract.py` (stdio: każdy przypadek kontraktu,
  plany POST, komendy lokalne i każdy kod błędu CLI — MCP = Python = CLI)
  i `tests/contract/test_mcp_http_contract.py` (`/mcp` = REST dla każdego przypadku
  i scenariusza błędu poza `method_not_allowed`).
- Kontrakt ČHMÚ `tests/contract/test_chmi_contract.py`: każdy wiersz kryteriów IMGW-15..19
  na `complete_pl_cz` i nagraniach, parytet Python/CLI/REST/MCP dla 31 uruchomień ČHMÚ
  (te same koperty, żądania i sumy SHA-256 drzew), 7 bliźniaków `--check`, 5 komend
  lokalnych i 4 odrzucone wybory; zero ruchu poza nagraniami.
- Testy jednostkowe dostawcy ČHMÚ (`test_*_chmi.py`, `test_parsing_chmi.py`,
  `test_store_content.py`) i agentów (`test_agent_guide.py` z testem dryfu `AGENTS.md`
  i `llms.txt`, `test_catalog_effects.py` — skutki deklarowane = zachowanie,
  `test_catalog_i18n.py`, `test_mcp_tools.py`, `test_mcp_calls.py`, `test_mcp_http.py`,
  `test_mcp_stdio.py`).
- Regresja na żywo `tests/live/test_interfaces_live.py` (`IMGW_LIVE=1`, raport JSON przez
  `IMGW_LIVE_REPORT`): każda z 37 komend przez Python, zainstalowany `imgw` i REST
  (`imgw server`) na serwerach IMGW-PIB w świeżym magazynie, 6 błędów na żywo i noga MCP
  (`-k imgw_mcp`: jeden proces `imgw mcp`, 9 komend sieciowych bez zapisu); przebieg
  2026-10-19: 53 passed w 103 s. `tests/live/test_chmi_live.py` — dostawca ČHMÚ na
  opendata.chmi.cz (stacje `0-203-1-001000` i `0-203-0-11799`) przez Python, CLI, REST
  i MCP z dziennikiem żądań każdego interfejsu; przebieg 2026-10-19: 26 passed w 77 s,
  124 żądania, 31,5 MB.
- 2213 testów (`pytest --collect-only`, 2026-10-19): 2134 offline i 79 na żywo (53 IMGW-PIB,
  26 ČHMÚ).

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
