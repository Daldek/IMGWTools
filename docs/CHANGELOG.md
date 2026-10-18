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
  wypisuje plan bez pobierania. Po pobraniu co najmniej jednego pliku komenda emituje
  komunikat `license_terms` z warunkami IMGW-PIB (jak zapis do magazynu).
- **`parse_zip_file`** zgłasza uszkodzone archiwum jako `IMGWDataError`, a nie
  `zipfile.BadZipFile`; ZIP jest czytany z limitami liczby/rozmiaru plików i bez
  niebezpiecznych ścieżek.
- **`imgwtools[full]`** obejmuje teraz `store` (`pyarrow>=15`) obok `api`, `cli`, `pandas`.
- **`parse_stations_csv(content, /, *, kind, encoding=…)`** wymaga `kind="hydro"|"meteo"`
  i zwraca `StationListEntry` (zamrożona dataclass: `kind`, `station_code`, `name`; tylko
  hydro `river`, `hydrographic_code`, `river_order`; tylko meteo `short_code`) zamiast
  `HydroArchiveStation`. Lista meteo nie jest już czytana układem kolumn hydro (trzecia
  kolumna to `short_code`, nie rzeka). Migracja: `parse_stations_csv(data)` →
  `parse_stations_csv(data, kind="hydro")`, `.station_name`/`.river_name` → `.name`/`.river`.
  `HydroArchiveStation` opisuje wyłącznie stację z wierszy archiwów danych (pola
  `hydrographic_code`, `river_order`, `latitude`, `longitude` usunięte).

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
- **Odczyt list stacji i archiwów z magazynu (offline, SHA-256)**:
  `read_station_list(root, kind="hydro"|"meteo")` czyta bieżącą wersję zbioru
  `pl.imgw.hydro_stations`/`pl.imgw.meteo_stations` jako krotkę `StationListEntry`;
  `read_archive(version)` zwraca rekordy `NormalizedRecord` zapisanej wersji archiwum
  (zbiór i plik z sidecara, parser zbioru), wersję listy stacji odrzuca z odesłaniem do
  `read_station_list`. CLI `imgw store read --version … [--format csv|jsonl] [--path …]`
  (katalog komend; bez `--path` na stdout, zapis przez `.part` i `os.replace`).
- `sync_pmaxtp` zapisuje dodatkowo surową odpowiedź API PMAXTP bajt w bajt jako
  `response.json` w katalogu wersji komórki; SHA-256 i rozmiar w sidecarze
  `cell.json.meta.json` (`extra.response`), tożsamość wersji nadal wyznacza SHA `cell.json`.
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
- **CLI**: grupy `imgw store init|info|scan|check|sync|catalog|read`,
  `imgw series build|export|select`, `imgw pmaxtp check|sync|read`,
  `imgw project init|add|remove|set-store|download|check|status|verify`; flaga `--check`
  każdej komendy uruchamia jej bliźniaczy `check_*` bez zapisu; Ctrl+C anuluje między
  plikami.
- **REST** (`/api/v1/store/*`, `/api/v1/series/*`, `/api/v1/pmaxtp/store/sync`) na
  serwerowym, absolutnym `IMGW_STORE_ROOT`; bez niego trasy magazynu zwracają 503.
  Zapis wymaga jednocześnie `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN`
  i nagłówka `X-API-Key`; CSV współrzędnych użytkownika tylko z `IMGW_USER_LOCATIONS_DIR`.
  Ścieżki w odpowiedziach są względne do root, także w tekstach (`detail` błędu, `error`,
  `problems`) — serwer nie ujawnia bezwzględnych katalogów.
- **`imgwtools.testing.build_fixture_store`** — publiczny, offline budowniczy magazynu
  testowego (warianty `complete`, `corrupt`, `unknown_schema`) z nagranymi odpowiedziami
  dla konsumentów (Archiwista, Retman).
- **Wyjątki**: `IMGWStoreError`, `IMGWStoreConflictError`, `IMGWStoreDependencyError`
  (instrukcja `pip install imgwtools[store]`), `IMGWPlanStaleError`, `IMGWProjectError`.
- **Dodatek** `imgwtools[store]` = `pyarrow>=15` (tylko ścieżki Parquet; import rdzenia
  nie wymaga pyarrow).

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
- `build_series` nie przechowuje wszystkich rekordów zbioru: rekordy są składane do
  wartości stacji w trakcie parsowania (jednakowe pomiary współdzielą jeden obiekt),
  a pokrycie liczone stacja po stacji — szczyt pamięci budowy niższy o ok. 57%
  (pomiar: syntetyczne archiwum dobowe, 110 tys. rekordów; 179 → 77 MiB).
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
  `IMGWStoreError` z polskim komunikatem.
- `iter_store` zgłasza wersję szeregu z nieobsługiwanym `extra.series_schema`
  (np. `imgw-series/2`) jako problem `unknown_schema`; `current_version` dla takiego
  slotu kończy się `IMGWDataError`.
- Bezpieczeństwo: `StorePlan.from_json` (także plan przekazany w
  `POST /api/v1/store/sync`) odrzuca pozycje, których `url` różni się od adresu
  z rejestru zbiorów — zapytania HEAD/GET trafiają wyłącznie na serwery IMGW.
- `export_series` tworzy plik CSV z uprawnieniami zgodnymi z umask (np. 0644).

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
  odpowiedź PMAXTP z innym polem `error` niż „poza obszarem” daje 502.
- `imgw fetch pmaxtp` odrzuca współrzędne spoza Polski przed wysłaniem żądania;
  `imgw list stations --search` traktuje wzorzec dosłownie (znaki wyrażeń regularnych
  nie powodują już błędu).
- `read_meta` odrzuca sidecar z polem `dataset` spoza kluczy `pl.imgw.*` (spec §11.2).
- `fetch_pmaxtp`/`fetch_pmaxtp_async` nie zwracają już pustych tabel `ks/sg/rb` jako
  sukcesu: odpowiedź z polem `error` lub bez tabeli `ks` daje wyjątek. Punkt w ramce
  współrzędnych, ale poza siatką PMAXTP (np. Kaliningrad, Lwów, Bałtyk; API: „Brak
  pliku, pradopodobnie poza obszarem PL”) daje `IMGWValidationError` także w `sync_pmaxtp`,
  REST 400 (`/api/v1/pmaxtp/data`, `/api/v1/pmaxtp/store/sync`; wcześniej 500)
  i komunikat `Błąd: …` z kodem 1 w `imgw fetch pmaxtp`/`imgw pmaxtp sync`; inne błędy
  API pozostają `IMGWDataError`, błędy sieci `IMGWConnectionError`.
- `imgw fetch hydro|meteo --check` wypisuje na stdout wyłącznie plan `imgw-plan/1`
  (bez mylącego „Pobrano: 0 plików”); podsumowanie pobierania trafia na stderr.
- CLI kończy się kodem 1, gdy wypisany wynik zawiera nieudaną pozycję (`failed` lub
  `stale_plan`: pozycje i szeregi `store sync`, `series build`, `store catalog`, zadania
  i pliki projektu, pliki `fetch hydro|meteo`); JSON wyniku nadal trafia na stdout,
  anulowanie zachowuje kod 130.
- CLI wypisuje każdy jednakowy komunikat (kod i tekst) raz na uruchomienie komendy
  (np. `license_terms` przy synchronizacji setek archiwów); hooki `on_notice` Pythona
  i REST nadal dostają każdy komunikat.
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
  `store read` i REST `GET /api/v1/series/{station}` — `<V>_occurrences`
  / `extrema_occurrences`. Różne wartości tego samego klucza nadal są błędem danych.
- Parsery meteo pomijają pierwszy wiersz złożony z kodów kolumn (np. `kansp,kapost,…`
  w `o_d_08_2025.csv`, wcześniej „Niepoprawny kod stacji”); każdy inny błędny wiersz
  nadal daje `IMGWDataError` z numerem linii.
- `build_series` nie trzyma wartości wszystkich stacji w pamięci: zweryfikowane rekordy
  trafiają do skompresowanych plików tymczasowych per stacja poza magazynem (`TMPDIR`),
  a stacje są składane i zapisywane po kolei. Szczyt RSS dla pełnych roczników 1950–2025:
  `meteo_precip_daily` (26,6 mln rekordów) 0,85 GB zamiast 9,0 GB, `hydro_daily` 0,41 GB
  zamiast 6,8 GB; `series.json` i pliki Parquet bajtowo bez zmian.

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
