# Plan: wersjonowany magazyn IMGWTools 3.0.0

**Data:** 2026-10-17  
**Spec:** `../specs/2026-10-17-versioned-store-design.md`; decyzje `docs/DECISIONS.md` ADR-001  
**Cel:** IMGW-1..IMGW-14 + PMAXTP per komórka, jedno publiczne API dla CLI/REST/Archiwisty/Retmana; brak SQLite. Dokument jest instrukcją wdrożenia, nie deklaracją wykonania.

## Zasady pracy

- Przed implementacją przeczytać spec; podpisy typów i nazwy kontraktów są zamrożone w §2–11. W razie rzeczywistej sprzeczności rozstrzygnąć jawnie w spec/ADR **przed** równoległą zmianą API, nie budować własnych adapterów.
- Zadania **w obrębie jednej fali mają rozłączne ścieżki plików** (również testów); zależność zadania wskazuje ID zakończonych zadań wcześniejszych fal. Może być wiele osób na falę, z wyłączną własnością wskazanych plików. Jedyny integrator scala importy na końcu, nie kilka agentów naraz.
- Każdy task pisze testy scenariuszowe i wykonuje tylko swoje testy/małą próbę lokalną; pełny `pytest`, lint i typecheck uruchomić jednokrotnie po scaleniu, w T25. Testy offline, nagrane HTTP, brak stałego pobierania żywych roczników; live jako osobny świadomie uruchamiany zestaw.
- Przeniesienie parserów jest czystym przeniesieniem niezbędnych funkcji + rozszerzeniem; **bez shimów** `imgwtools.db`, bez alternatywnej implementacji CLI downloadera. Nie usuwać lokalnych baz danych użytkownika; usuwać jedynie kod cache.
- Nowe funkcje API zachowują R1 (keyword-only poza pierwszym obiektem), R2 (check twin), R3–R12, polskie komunikaty, brak niejawnej sieci w odczycie. `imgwtools.__all__` i podpisy zebrane w T23; przedtem moduły mogą działać przez ścieżki modułowe.

| Fala | Taski (równoległe w wierszu) | Wspólny efekt |
|---|---|---|
| 0 | T01–T06 | Kontrakty, pliki/URL, HTTP, parsery, stacje, fixtury źródłowe |
| 1 | T07–T10 | Writer + pokrycie + płaski CLI + REST linków |
| 2 | T11–T14 | Katalog, sync/plan, Parquet, PMAXTP (niezależne moduły) |
| 3 | T15–T16 | API odczytu i publiczny builder katalogu testowego |
| 4 | T17–T18 | Eksport i katalog komend |
| 5 | T19 | Manifest projektów i check/verify/download |
| 6 | T20–T21 | CLI grup danych/projektu oraz bezpieczne REST magazynu |
| 7 | T22–T23 | Usunięcie DB i integracja eksportów pakietu |
| 8 | T24 | CHANGELOG/dokumentacja/wydanie 3.0.0 |
| 9 | T25 | Końcowy test kontraktu i pełna bramka offline |

### Fala 0 — niezależne fundamenty

**T01 — Rejestr źródeł i zgodne URL-e.**  
**Pliki (wyłączna własność):** utwórz `src/imgwtools/datasets.py`, zmodyfikuj `src/imgwtools/core/url_builder.py`, `src/imgwtools/urls.py`, `tests/unit/test_urls.py`; utwórz `tests/unit/test_datasets.py`.  
**Zależy od:** —.  
**Test akceptacji:** `archive_files` bez sieci: hydro 2022 12 ZIP, 2024 1 ZIP; meteo klimat/opad 1950/1951–2000 roczny, 2001 miesięczny; H/Q/T półroczne jako 3 ZIP; stacje CSV z dokładną ścieżką na serwerze; duplikaty lat/miesięcy bez duplikatu fizycznej paczki; niedozwolony zbiór → walidacja; istniejące funkcje URL zwracają dotychczasowe ścieżki również dla kombinacji poza magazynem. Utrzymać klucze `pl.imgw.*` i slugi z §2, bez drugiej tabeli.

**T02 — `DownloadResult` z tych samych odpowiedzi HTTP.**  
**Pliki:** zmodyfikuj `src/imgwtools/fetch.py`, `tests/unit/test_fetch.py`.  
**Zależy od:** — (opis pól i podpisów jest w spec).  
**Test akceptacji:** nagrany GET hydro/meteo sync+async daje identyczne `data`, URL, ETag, Last-Modified, Content-Length; brak nagłówka = `None`; błędny HTTP/timeout ma konkretny wyjątek; `fetch_pmaxtp` i `fetch_pmaxtp_async` pozostają bez zmiany podpisu/wyniku.

**T03 — Parsery i flagi poza DB.**  
**Pliki:** utwórz `src/imgwtools/_parsing/__init__.py`, `src/imgwtools/_parsing/common.py`, `src/imgwtools/_parsing/hydro.py`, `src/imgwtools/_parsing/meteo.py`; zmodyfikuj `src/imgwtools/parsers.py`, `src/imgwtools/models.py`, `tests/unit/test_parsers.py`, `tests/unit/test_models.py` (stare `imgwtools.db.*` w testach zastąpić publicznymi importami).  
**Zależy od:** — (T01 i T03 współdzielą wyłącznie podpisy opisane w spec).  
**Test akceptacji:** te same rekordy hydro z CP1250/UTF-8 BOM/quoted lines, miesięczny min/mean/max, półroczny 13/14/15; meteo k_d i o_d roczne/miesięczne, status 8=`missing`, 9=`no_phenomenon`, opad zbiorczy=`accumulated`; 29 II i brak Q przy H; błędny rekord zawiera ZIP/CSV i numer linii. `db/models.py`, `db/parsers.py` pozostają do skasowania T22, ale żaden nowy import do nich nie trafia.

**T04 — Stacje: zachowanie atrybutów wejścia.**  
**Pliki:** zmodyfikuj `src/imgwtools/stations.py`, `tests/unit/test_stations.py`.  
**Zależy od:** —.  
**Test akceptacji:** czwarta kolumna listy hydro (`river_order`) i kod z nawiasu (`hydrographic_code`) są zachowane jako liczba/tekst; realne pole `rzeka` w odpowiedzi API mapy zamiast nieistniejącego `riverName`; stary publiczny `HydroStation` i `MeteoStation` działają; żadnego odpytywania mapy w ścieżce `build_catalog` (T11).

**T05 — Syntetyczne źródła i zapisane interakcje.**  
**Pliki:** utwórz `tests/fixtures/store/` (małe archiwa hydro w obu układach, mies/polr, meteo k_d/o_d roczne i miesięczne, CSV list, tekstowe nagrania listing/HEAD/GET/API hydro/meteo/PMAXTP), `tests/unit/test_store_fixtures.py`; nie twórz jeszcze `testing.py`.  
**Zależy od:** —.  
**Test akceptacji:** archiwa są poprawnymi ZIP, sumy i daty nagrań są stałe, roczniki/formaty/statusy z §12 występują; testy nie wykonują połączeń sieciowych; żadne pełne rzeczywiste archiwum ani dane poufne nie trafiają do pakietu.

**T06 — Typy i hierarchia błędów.**  
**Pliki:** utwórz `src/imgwtools/store/types.py`, `tests/unit/test_store_types.py`; zmodyfikuj `src/imgwtools/exceptions.py`.  
**Zależy od:** —.  
**Test akceptacji:** niezmienne `Progress`, `Notice`, `StoreInfo`, `StoreEntry`, `VersionResult`, `PlanItem`, `StorePlan`, `SyncReport`, `SeriesReport`, `CatalogReport`, `PMaXTPStoreResult`, `ProjectReport`, `Meta` zgodne z podpisami §2–10; pola `cancelled` i `to_json/from_json` planu mają spójną reprezentację; dodatkowe pola przy odczycie `/1` tolerowane tam, gdzie dopuszcza spec; wszystkie nowe wyjątki dziedziczą z `IMGWError`, z komunikatami PL. Żaden import pyarrow w tym module.

### Fala 1 — jeden writer, niezależne czyste obliczenia i adaptery

**T07 — Znacznik, atomowy zapis i sidecar.**  
**Pliki:** utwórz `src/imgwtools/store/__init__.py`, `src/imgwtools/store/writer.py`, `tests/unit/test_store_writer.py`.  
**Zależy od:** T01, T02, T05, T06.  
**Test akceptacji:** `init_store/open_store/write_archive` z fixtury T05: pełny hash, sidecar i ścieżka slotu; wyścig dwóch zapisów, brak zastąpienia nawet pustego katalogu docelowego, wyraźna odmowa nieatomowego FS, `fsync`, przerwanie/wyjątek bez widocznej połowicznej wersji, usunięcie tylko `.incoming >24h`, powtórka i relabel pod nowym sygnałem jako kopia z `nlink==1`. Test osobny root nested z markerami Kartografa bez jego importu.

**T08 — Pokrycie jako funkcja czysta.**  
**Pliki:** utwórz `src/imgwtools/coverage.py`, `tests/unit/test_coverage.py`.  
**Zależy od:** T03, T06.  
**Test akceptacji:** osobne listy Q/H/T i P/Tmax, daty/luki/accumulated liczone ręcznie; 0 i suma zbiorcza liczą się jako wartości, brak doby jako luka; brak miesiąca archiwalnego daje `unknown` w `periods`, a nie luka; granica 31 X/1 XI, 29 II oraz okresy 13/14/15; seria bez wartości zachowuje wpis z `first/last=null`.

**T09 — Płaskie `imgw fetch` bez kolizji i częściowego pliku.**  
**Pliki:** zmodyfikuj `src/imgwtools/cli/fetch.py`, utwórz `tests/unit/test_cli_fetch_store.py`.  
**Zależy od:** T01, T02, T05.  
**Test akceptacji:** CLI woła wyłącznie publiczne `archive_files`/`download_*`; `--output` ma podkatalogi serwera i dwa identyczne basename z różnych ścieżek współistnieją; awaria po części GET zostawia najwyżej `.part`, ponowny fetch nie zgłasza „już istnieje”; istniejące fetch current/pmaxtp/warnings działają.

**T10 — REST obecnych URL-i na jednym rejestrze.**  
**Pliki:** zmodyfikuj `src/imgwtools/api/routes/download.py`, `src/imgwtools/api/routes/meteo.py`, utwórz `tests/unit/test_api_download_registry.py`.  
**Zależy od:** T01.  
**Test akceptacji:** ścieżki hydro/meteo dla wspieranych zbiorów odzwierciedlają `archive_files`, schemat odpowiedzi generowanych URL-i nie zmienia się, niedozwolona kombinacja jest błędem klienta; zero GET archiwów i zero zapisu w tym zadaniu. `api/routes/hydro.py` należy do T22, nie dotykać go tu.

### Fala 2 — niezależne produkty tego samego writera

**T11 — Wersjonowany katalog stacji.**  
**Pliki:** utwórz `src/imgwtools/store/catalog.py`, `src/imgwtools/_data/poland_border_wgs84.geojson` (własny zasób polygonu z istniejącego `data/shp/polska.*`, dołączony do wheel), `tests/unit/test_store_catalog.py`.
**Zależy od:** T01, T04, T05, T07.  
**Test akceptacji:** komplet kodów hydro+meteo także historycznych i `geometry:null`, CSV list zapisane najpierw jako archiwa; API > statyczny > user, niepoprawny punkt `0,0`/poza Polską z powodem, punkty przy granicy sprawdzone z polygonem bez pyproj/pyshp/GDAL w runtime, niepewność 2 vs 4 miejsca, prefiks kodu hydrograficznego; GeoJSON RFC 7946 i źródła/SHA w sidecarze; identyczna treść następnego dnia → `unchanged`; `check_catalog` nie pobiera treści i nie pisze; brak zależności od hydro-back.

**T12 — Sygnały HEAD, plan i synchronizacja.**  
**Pliki:** utwórz `src/imgwtools/store/sync.py`, `tests/unit/test_store_sync.py`.  
**Zależy od:** T01, T02, T05, T07.  
**Test akceptacji:** listing+HEAD bez GET/zapisu w `check_store`; statusy pięciu rodzajów, brak porównywalnego nagłówka i błąd jawne, Content-Length tylko informacyjne; round-trip `imgw-plan/1`; nagłówek zmieniony po check daje `stale_plan` bez GET; nowy hash nowa wersja, ten sam hash pod nowym sygnałem `relabeled`, `cancel` raportuje wykonane pozycje bez częściowej wersji. `series=True` wywołuje API T13 wyłącznie po kompletnych wejściach; integrację tej ścieżki testuje T25 po zamknięciu całej fali.

**T13 — Migawki szeregów i check bliźniaczy.**  
**Pliki:** utwórz `src/imgwtools/store/series.py`, `tests/unit/test_store_series.py`.  
**Zależy od:** T03, T05, T07, T08.  
**Test akceptacji:** `check_series` offline, `build_series` Parquet ze stacjami z lukami/bez współrzędnych i pustą zmienną; każda doba (także 29 II), hydro_year meteo i hydro, miesięczne i półrocza/rok; `series.json` pełne SHA i coverage, source_files dokładne wejścia; drugi build `reused` bez otwarcia writera Parquet, anulowanie bez nowej wersji; bez `pyarrow` błąd z instrukcją instalacji (import rdzenia bez pyarrow).

**T14 — Magazyn PMAXTP per komórka.**  
**Pliki:** utwórz `src/imgwtools/store/pmaxtp.py`, `tests/unit/test_store_pmaxtp.py`.  
**Zależy od:** T02, T05, T07.  
**Test akceptacji:** indeksy `indX/indY` wyłącznie z nagranej odpowiedzi API, różne punkty tej samej komórki/method reuse bez nowej wersji, AMP oddzielne, błędne indeksy użytkownika i puste data nie tworzą katalogu, `check_pmaxtp` bez GET → `unverifiable`; `read_pmaxtp` offline; nie zmieniać `fetch_pmaxtp`.

### Fala 3 — odczyt i fixture builder

**T15 — Publiczne funkcje odczytu.**  
**Pliki:** utwórz `src/imgwtools/store/reader.py`, `tests/unit/test_store_reader.py`.  
**Zależy od:** T07, T11–T14.  
**Test akceptacji:** `store_info/iter_store/read_meta/current_version/read_catalog/read_series_index/read_series/read_pmaxtp` na katalogu `chmod read-only`; brak sieci/zapisu/locków, wersja `imgw-store/2` odczytana jako nieobsługiwana i zgłoszona w skanie, nieznane pola `/1` tolerowane, sidecar uszkodzony/brakujący i stary `.incoming` jako problemy, znane wersje i zakres `start/end` zgodne z rekordami parsera. Jeśli `read_pmaxtp` jest implementowane w T14, T15 wyłącznie testuje jego współdziałanie bez edycji `store/pmaxtp.py`.

**T16 — Publiczny budowniczy magazynu testowego.**  
**Pliki:** utwórz `src/imgwtools/testing.py`, `tests/unit/test_fixture_builder.py`; uzupełnij wyłącznie `tests/fixtures/store/` w osobnych nowych nazwach plików (T05 zakończone).  
**Zależy od:** T05, T07, T11–T14.  
**Test akceptacji:** `build_fixture_store(root,variant=…)` importowalne z wheel przez `importlib.resources`, używa rzeczywistych publicznych `init_store/write_archive/build_series/build_catalog`, ma znane warianty `complete/corrupt/unknown_schema`; dwa wywołania na świeżych root dają równoważne listy wersji po zamrożeniu czasu, żądania HTTP nagrane; brak internetu.

### Fala 4 — interfejs użytkowy API

**T17 — Eksport szeregów CSV.**  
**Pliki:** utwórz `src/imgwtools/store/export.py`, `tests/unit/test_series_export.py`.  
**Zależy od:** T13, T15.  
**Test akceptacji:** `csv.DictReader` odczytuje pierwszy wiersz nagłówka z jednostkami, obie formuły tylko w pierwszym wierszu danych, 366 dni bez pominięcia braków, flagi 0/accumulated; jawne `year_type` granicy XI dla hydro i meteo, default wg spisu, półrocze/calendar odrzucone; przerwanie `.part` nie nadpisuje starego eksportu.

**T18 — Katalog komend i identyczny dispatcher.**  
**Pliki:** utwórz `src/imgwtools/commands.py`, `tests/unit/test_commands.py`.  
**Zależy od:** T11–T15.  
**Test akceptacji:** każda komenda wymieniona w §10 z opcjami i polskim help, walidacja bez sieci odrzuca nieznany klucz/wybór, `format_command` po ponownym sparsowaniu daje identyczne opcje, `check_command` zero zapisów/GET danych, `run_command` dokładnie jedno publiczne API na działanie i te same struktury `Progress/Notice` co funkcje bezpośrednie. `series export` może importować T17 po zakończeniu całej fali — żeby utrzymać rozłączność plików i brak zależności w tej samej fali, testy tej komendy uruchomić w T20; tutaj dopuszczalne wyłącznie zarejestrowanie celu wywołania w dispatch bez jego wykonywania do T17.

### Fala 5 — zadania projektu

**T19 — Manifest `imgw-project/1`.**  
**Pliki:** utwórz `src/imgwtools/project.py`, `tests/unit/test_project.py`.  
**Zależy od:** T11–T18.  
**Test akceptacji:** init/open/add/remove/set-store/download/check/status/verify, dwa manifesty obok bez dotykania Kartografa, walidacja opcji i ścieżek (także `..` i symlink), SHA geometrii i jawna lista stacji po wyborze, przeniesienie magazynu, odtworzenie tylko identycznych SHA, dopiero upgrade zmienia piny, wyścig dwóch zadań przez `mkdir` lock + scalanie, lock nieprzejmowany; `check_project` używa `imgw-plan/1` i nie zapisuje.

### Fala 6 — adaptery, bez duplikowania reguł

**T20 — CLI magazynu, szeregów, PMAXTP i projektu.**  
**Pliki:** utwórz `src/imgwtools/cli/store.py`, `src/imgwtools/cli/series.py`, `src/imgwtools/cli/pmaxtp.py`, `src/imgwtools/cli/project.py`, `tests/unit/test_cli_store_project.py`; zmodyfikuj `src/imgwtools/cli/main.py` (rejestracja nowych grup; starej `db` jeszcze nie usuwaj: T22).  
**Zależy od:** T01–T19.  
**Test akceptacji:** `imgw store …`, `series …`, `project …`, `pmaxtp …` z §10 wywołują publiczne API z tymi samymi opcjami, `--help` = opisy katalogu, plan poza root, cancel/notice PL; wyjścia katalogów i SHA identyczne z Python API przy stałym zegarze; `imgw series export` również działa przez dispatcher T18/T17, bez prywatnego fetch.

**T21 — REST magazynu za jawną konfiguracją.**  
**Pliki:** utwórz `src/imgwtools/api/routes/store.py`, `tests/unit/test_api_store.py`; zmodyfikuj `src/imgwtools/api/main.py`, `src/imgwtools/api/schemas.py`.  
**Zależy od:** T11–T19.  
**Test akceptacji:** GET info/entries/index/series offline przy `IMGW_STORE_ROOT`, brak konfiguracji = 503 wyłącznie dla tras magazynu, POST zapisu wyłączone domyślnie = 403, włączone przez `IMGW_STORE_WRITES_ENABLED=true` **i** `IMGW_STORE_WRITE_TOKEN` wymagają `X-API-Key` porównanego w stałym czasie. `POST /store/check` nie pisze do root, eksport CSV nie pozostawia pliku tymczasowego. Wersja i katalog CSV użytkownika są ograniczone do root/`IMGW_USER_LOCATIONS_DIR`, nigdy arbitralna ścieżka od klienta; REST mapuje te same publiczne funkcje. URL builder i live API nie tracą dotychczasowej odpowiedzi. Nie dotykać `api/routes/hydro.py` — DB zniknie w T22.

### Fala 7 — integracja końcowa (pliki rozłączne)

**T22 — Usunięcie starego cache SQLite (clean cutover).**  
**Pliki:** usuń `src/imgwtools/db/__init__.py`, `db/cache_manager.py`, `db/connection.py`, `db/schema.py`, `db/repository.py`, `db/models.py`, `db/parsers.py`, `src/imgwtools/cli/db.py`; zmodyfikuj `src/imgwtools/cli/main.py`, `src/imgwtools/api/routes/hydro.py`, `src/imgwtools/config.py`, `pyproject.toml` (tylko extras: usuń `db`, `full` uwzględnia `store`, dodaj `pyarrow>=15`; **wersja pozostaje do T24**).  
**Zależy od:** T03, T20, T21.  
**Test akceptacji:** `imgw db` nie jest komendą, brak endpointu `/api/v1/hydro/data`, brak `IMGW_DB_*`, DB extras i importów `imgwtools.db`; nowe odczyty i parsery działają bez starego pakietu, lokalne pliki `.db` użytkownika nie są modyfikowane; bieżący/live endpoint hydro pozostaje. Nie doklejać shimów.

**T23 — Jedna lista publicznych eksportów.**  
**Pliki:** zmodyfikuj `src/imgwtools/__init__.py`, `src/imgwtools/store/__init__.py`; utwórz `tests/unit/test_public_store_api.py`.  
**Zależy od:** T15–T19 (może współbiec z T22: **inny zestaw plików**).  
**Test akceptacji:** wszystkie publiczne funkcje/typy §2–10 i wyjątki figurują w `__all__` i mają rzeczywiste implementacje; import `imgwtools` bez `pyarrow` i bez `db` działa; sygnatury nowych metod keyword-only jak R1, istniejące fetch/live importy pozostają (poza jawną zmianą `DownloadResult`).

### Fala 8 — historia i dokumentacja wydania

**T24 — Wersja 3.0.0, CHANGELOG, dokumentacja.**  
**Pliki:** utwórz `docs/CHANGELOG.md`; zmodyfikuj `pyproject.toml` (**po T22**, ustaw 3.0.0), `src/imgwtools/_version.py`, `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`, opcjonalnie `docs/PRD.md` jeśli opisuje usunięty DB (wtedy task ma wyłączną własność tego pliku).  
**Zależy od:** T22, T23.  
**Test akceptacji:** `imgw version` zwraca 3.0.0 (naprawić hardcoded string w `src/imgwtools/cli/main.py` **w T22**, żeby czytał `__version__`, a nie modyfikować ten plik tutaj); CHANGELOG zawiera `BREAKING` (bytes→DownloadResult, usunięcie DB/CLI/REST/settings), instalację `[store]`, strukturę i politykę IMGW-13; dokumenty nie twierdzą, że serwer *zawsze* nie zapisuje danych — domyślnie generuje URL, zapis po jawnej konfiguracji. Historycznych decyzji ADR nie przeredagowywać.

### Fala 9 — ostatnia bramka kontraktu

**T25 — Końcowy zestaw kontraktowy i integracja.**  
**Pliki:** utwórz `tests/contract/test_versioned_store.py`, `tests/contract/test_cli_api_parity.py`, `tests/contract/test_project_contract.py` (istniejące testy zmieniać tylko jeśli faktycznie przestały wyrażać obowiązujący kontrakt; odpowiedni owner T01–T24 naprawia wcześniej); dołączyć fixtury wyłącznie w nowych plikach `tests/fixtures/store/contract_*`.  
**Zależy od:** T01–T24.  
**Test akceptacji:** offline budowa katalogu publicznym `imgwtools.testing`, kontrola JSON Schemas §11 i `sha256`, read-only scan nieznanego schematu oraz problemów, state machine HEAD→plan→stale/sync→series→coverage→catalog→CSV→projekt→verify/restore; rzeczywisty `imgw store check|sync`, `imgw series build|export` i `imgw project …` na lokalnych nagraniach dają te same ścieżki/SHA co API; anulowanie i współbieżność; brak zależności na sieć. **Po scaleniu wszystkich fal raz** `.venv/bin/python -m pytest`, `.venv/bin/ruff check src/ tests/`, `npx -y pyright src/imgwtools/` i smoke CLI/API + REST odczytu, naprawić każdy realny problem do zamknięcia. Testy live uruchamiać świadomie oddzielnie, nie jako warunek lokalnej bramki.
