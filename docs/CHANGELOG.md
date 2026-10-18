# Changelog — IMGWTools

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersjonowanie
zgodne z [SemVer](https://semver.org/lang/pl/). Każda zmiana publicznego API i schematów
magazynu (`imgw-*/N`) trafia do tego pliku (ADR-001, polityka IMGW-13).

## [3.0.0] — 2026-10-18

Wersjonowany magazyn danych IMGW zastępuje opcjonalny cache SQLite. Decyzje:
`docs/DECISIONS.md` (ADR-001), kontrakt: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`.

### BREAKING

- **`download_hydro_data`, `download_meteo_data` i ich warianty `*_async` zwracają
  `DownloadResult`, nie `bytes`.** Argumenty i ich kolejność się nie zmieniają; wynik ma
  pola `data` (dokładne bajty odpowiedzi), `url`, `etag`, `last_modified`,
  `content_length` (nagłówki z tego samego GET; brak nagłówka = `None`). Migracja:
  `download_hydro_data("dobowe", 2023)` → `download_hydro_data("dobowe", 2023).data`.
  Odpowiedź, która nie jest poprawnym ZIP, kończy się `IMGWDataError`. `fetch_pmaxtp`
  i `fetch_pmaxtp_async` pozostają bez zmian.
- **Usunięty cache SQLite** (bez shimów i aliasów):
  - pakiet `imgwtools.db` (`cache_manager`, `connection`, `schema`, `repository`,
    `models`, `parsers`) — parsery hydro są nadal dostępne w `imgwtools.parsers`,
    modele archiwalne (`HydroArchiveStation`, `HydroDailyRecord`, …) w `imgwtools.models`;
  - komenda CLI `imgw db …` (`init`, `status`, `stations`, `cache`, `query`, `clear`,
    `vacuum`);
  - endpoint REST `GET /api/v1/hydro/data`;
  - ustawienia `IMGW_DB_ENABLED` i `IMGW_DB_PATH`;
  - dodatek instalacyjny `imgwtools[db]`.

  Istniejące pliki `.db` nie są usuwane ani migrowane — dane pobiera się ponownie do
  magazynu (`imgw store sync`).
- **`imgw fetch hydro|meteo`** działa przez katalog komend: `--output` odwzorowuje ścieżki
  serwera IMGW (np. `dane_hydrologiczne/dobowe/2024/codz_2024.zip`) zamiast płaskiego
  katalogu, zapis idzie przez plik `.part` i `os.replace`, a ponowne pobranie nadpisuje
  plik zamiast go pomijać. `--year` przyjmuje rok lub zakres (`2020-2023`); `--check`
  wypisuje plan bez pobierania.
- **`parse_zip_file`** zgłasza uszkodzone archiwum jako `IMGWDataError`, a nie
  `zipfile.BadZipFile`; ZIP jest czytany z limitami liczby/rozmiaru plików i bez
  niebezpiecznych ścieżek.
- **`imgwtools[full]`** obejmuje teraz `store` (`pyarrow>=15`) obok `api`, `cli`, `pandas`.

### Dodane

- **Wersjonowany magazyn** (`imgwtools.store`, re-eksport w `imgwtools`): niezmienne,
  tylko przyrostowe wersje archiwów IMGW 1:1 z sidecarem `*.meta.json` (SHA-256, rozmiar,
  nagłówki HTTP, licencja IMGW-PIB), atomowa publikacja katalogu wersji (rename bez
  zastępowania), staging `.incoming/`, wykrywanie katalogów Kartografa bez jego importu.
  Funkcje: `init_store`, `open_store`, `write_archive`, `check_store`/`sync_store`
  (listing + `HEAD`, plan `imgw-plan/1`, `stale_plan`), `check_series`/`build_series`
  (Parquet per stacja), `check_catalog`/`build_catalog` (`stations.geojson`, obrys
  Polski Natural Earth w pakiecie), `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp`
  (PMAXTP per komórka siatki), odczyt `store_info`, `iter_store`, `read_meta`,
  `current_version`, `read_catalog`, `read_series_index`, `read_series` oraz
  `export_series` (CSV z jednostkami i atrybucją IMGW-PIB).
- **Rejestr zbiorów** `imgwtools.datasets`: `datasets()`, `get_dataset()`,
  `archive_files()`, `station_source_files()`, `DatasetDescriptor`, `ArchiveFile`,
  `License`. Pięć zbiorów archiwalnych (`pl.imgw.hydro_daily`, `pl.imgw.hydro_monthly`,
  `pl.imgw.hydro_semiannual`, `pl.imgw.meteo_climate_daily`,
  `pl.imgw.meteo_precip_daily`), listy stacji (`pl.imgw.hydro_stations`,
  `pl.imgw.meteo_stations`) i PMAXTP (`pl.imgw.pmaxtp`).
- **Parsery meteo i normalizacja**: `parse_meteo_climate_daily`,
  `parse_meteo_precip_daily`, `normalize_archive`, rekordy `NormalizedRecord` z flagami
  `value|missing|no_phenomenon|accumulated`; `summarize_coverage` (pokrycie per stacja ×
  zmienna, luki).
- **Katalog komend** `imgwtools.commands` (`data_commands`, `validate_command`,
  `format_command`, `check_command`, `run_command`) — jedno źródło opcji, walidacji
  i pomocy dla CLI, REST i integracji (Retman).
- **Projekty** `imgwtools.project` (`imgw-project.json`): `init_project`, `open_project`,
  `set_project_store`, `add_project_task`, `remove_project_task`, `check_project`,
  `download_project`, `get_project_status`, `verify_project` — przypięcia wersji po
  SHA-256, blokada `.imgw-project.lock`.
- **CLI**: grupy `imgw store init|info|scan|check|sync|catalog`,
  `imgw series build|export|select`, `imgw pmaxtp check|sync|read`,
  `imgw project init|add|remove|set-store|download|check|status|verify`; flaga `--check`
  każdej komendy uruchamia jej bliźniaczy `check_*` bez zapisu; Ctrl+C anuluje między
  plikami.
- **REST** (`/api/v1/store/*`, `/api/v1/series/*`, `/api/v1/pmaxtp/store/sync`) na
  serwerowym, absolutnym `IMGW_STORE_ROOT`; bez niego trasy magazynu zwracają 503.
  Zapis wymaga jednocześnie `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN`
  i nagłówka `X-API-Key`; CSV współrzędnych użytkownika tylko z `IMGW_USER_LOCATIONS_DIR`.
- **`imgwtools.testing.build_fixture_store`** — publiczny, offline budowniczy magazynu
  testowego (warianty `complete`, `corrupt`, `unknown_schema`) z nagranymi odpowiedziami
  dla konsumentów (Archiwista, Retman).
- **Wyjątki**: `IMGWStoreError`, `IMGWStoreConflictError`, `IMGWStoreDependencyError`
  (instrukcja `pip install imgwtools[store]`), `IMGWPlanStaleError`, `IMGWProjectError`.
- **Dodatek** `imgwtools[store]` = `pyarrow>=15` (tylko ścieżki Parquet; import rdzenia
  nie wymaga pyarrow).

### Schematy i polityka wersji (IMGW-13)

| Schemat | Plik |
|---|---|
| `imgw-store/1` | `<root>/imgw-store.json` — znacznik magazynu |
| `imgw-meta/1` | `<plik>.meta.json` — sidecar każdej wersji |
| `imgw-series/1` | `series.json` — spis szeregu Parquet (+ metadane Parquet) |
| `imgw-plan/1` | `plan.json` — plan aktualności poza magazynem |
| `imgw-project/1` | `imgw-project.json` — manifest projektu |
| `imgw-pmaxtp/1` | `cell.json` — rozszerzenie IMGWTools dla komórki PMAXTP |

Każdy schemat ma własny licznik `/N`, niezależny od wersji pakietu. W ramach `/1`
dochodzą wyłącznie pola opcjonalne; czytniki tolerują dodatkowe pola w plikach magazynu,
ale manifest projektu jest walidowany ściśle (nowe opcjonalne dane tylko w mapie
`extensions`). Zmiana niezgodna wymaga `/2`, okresu odczytu `/1` i `/2` oraz osobnych
testów kontraktu; stary kod nie zapisuje do nieznanego znacznika. `store_info` zgłasza
nieobsługiwaną wersję (`supported=False`), skan raportuje problem i nie parsuje plików
nieznanego schematu. W linii 3.x publiczne funkcje odczytu nie znikają, a semantyka `/1`
się nie zmienia.

### Zmienione

- Domyślnie serwer nadal tylko generuje URL-e do IMGW; dane trafiają na dysk wyłącznie
  po jawnym wskazaniu magazynu (`--root`, `IMGW_STORE_ROOT`) lub katalogu `--output`.
- URL-e archiwów w REST (`/api/v1/download/*`, `/api/v1/meteo/download-url(s)`)
  i `imgw fetch` dla pięciu zbiorów wynikają z rejestru `archive_files`; walidacja lat
  w REST (także `/api/v1/hydro/download-url(s)`) bez zahardkodowanej górnej granicy 2024.
- `stations.py`: lista hydro zachowuje `river_order` (czwarta kolumna CSV)
  i `hydrographic_code`; `get_hydro_stations_with_coords` czyta rzekę z pola `rzeka`.

### Poprawione

- `API_VERSION` w REST (`/health`, `/api/v1`, OpenAPI) równa się `__version__` zamiast
  stałego `1.0.0`.
- REST hydro/meteo czyta rzeczywiste pola API IMGW (`stacja`, `kod_stacji`,
  `temperatura_powietrza`, `wiatr_srednia_predkosc`, `wilgotnosc_wzgledna`, `opad_10min`),
  więc nazwy stacji i pomiary synop nie są już puste; 404 z API IMGW dla stacji hydro
  daje 404 zamiast 502.
- `HydroCurrentData` czyta bieżące klucze `wojewodztwo` i `przeplyw_data` (wcześniej
  `province` i `flow_date` były zawsze `None`).
- Niepoprawny JSON z API IMGW: `fetch_*` i `get_hydro_stations_with_coords` zgłaszają
  `IMGWDataError` (zamiast surowego `JSONDecodeError`), trasy REST odpowiadają 502;
  odpowiedź PMAXTP z polem `error` daje 502.
- `imgw fetch pmaxtp` odrzuca współrzędne spoza Polski przed wysłaniem żądania;
  `imgw list stations --search` traktuje wzorzec dosłownie (znaki wyrażeń regularnych
  nie powodują już błędu).
- `read_meta` odrzuca sidecar z polem `dataset` spoza kluczy `pl.imgw.*` (spec §11.2).

### Testy

- Kontrakt magazynu w `tests/contract/` (offline: HEAD → plan → sync → szeregi → katalog
  → CSV → projekt → verify/restore, parytet ścieżek i SHA CLI = API, JSON Schemas §11);
  schematy i przykłady z §11 dołączone do pakietu
  (`imgwtools.testing.fixture_files()`, `contract_schemas.json`).

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
