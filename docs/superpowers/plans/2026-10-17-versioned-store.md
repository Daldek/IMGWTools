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
**Pliki:** utwórz `src/imgwtools/store/catalog.py`, `src/imgwtools/_data/poland_border_wgs84.geojson` (obrys Polski z Natural Earth 1:10m Admin 0, domena publiczna, dołączony do wheel; dane IMGW-PIB i `data/shp` nie trafiają do repozytorium, plik statyczny położeń czytany z `settings.data_dir`), `tests/unit/test_store_catalog.py`.
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

## ADR-002 — jeden katalog komend i spójne interfejsy (U01–U16)

**Data:** 2026-10-18  
**Decyzje:** `docs/DECISIONS.md` ADR-002; **kontrakt:** spec §13 (ma pierwszeństwo przed §1–§12)  
**Cel:** 35 komend katalogu jako jedyne źródło operacji; CLI i REST generowane z katalogu, web wyłącznie przez publiczne API; kody błędów, koperta `imgw-result/1`, `find_stations`, `command_schema`, stronicowanie i `summarize_series`. Całość w 3.0.0, bez aliasów i shimów. Dokument jest instrukcją wdrożenia, nie deklaracją wykonania.

### Zasady pracy (uzupełnienie)

- Obowiązują zasady z początku planu: rozłączne pliki w fali (także testy), w tasku tylko własne testy, pełna bramka raz na końcu (U16). W fali pracują najwyżej dwa równoległe taski.
- Nazwy, typy, kody, sloty i podpisy są zamrożone w spec §13; rzeczywista sprzeczność → najpierw errata w §13 i ADR-002, potem kod.
- Kontrakt-first w obrębie fali: task może zarejestrować wywołanie funkcji z §13.8, którą właściciel kończy w tej samej fali, ale testy tej ścieżki wykonuje task następnej fali (wzorzec T17/T18).
- Każdy task nadaje kody błędów z §13.5 w posiadanych modułach (`code=` przy zgłoszeniu) i przepisuje testy, które wyrażały stary kontrakt, zamiast przypinać stare zachowanie.
- „Tylko miejsca wywołań” = minimalna zmiana wywołania (nowa postać slotu, nazwa pola lub argumentu) w pliku, którego logika należy do taska innej fali.
- Do U13 stary kod może istnieć obok nowego wyłącznie wewnątrz gałęzi; stan po U16 nie ma aliasów, stubów ani martwych modułów.

| Fala | Taski (równolegle) | Zakres |
|---|---|---|
| 10 | U01, U02 | rejestr kodów błędów; typy koperty, stronicowania, pobierania i katalogu |
| 11 | U03, U04 | rejestr 13 zbiorów z aliasami i selektorami; odczyty live, nowe modele, `find_stations` |
| 12 | U05, U06 | sloty, wersje, `select_series`, `summarize_series`; pobieranie płaskie, CSV położeń, PMAXTP, pomocnicze URL |
| 13 | U07, U08 | eksport archiwów i szeregów; katalog 35 komend, koperta, stronicowanie, `command_schema` |
| 14 | U09, U10 | CLI z katalogu; REST z katalogu i problem+json |
| 15 | U11, U12 | projekt w nowych konwencjach; web na publicznym API |
| 16 | U13, U14 | usunięcie legacy i jedna lista eksportów; kontrakt międzyinterfejsowy |
| 17 | U15, U16 | dokumentacja wydania; bramka końcowa i pełna regresja live |

### Fala 10 — fundamenty modelu błędów i koperty

**U01 — Rejestr kodów błędów.**  
**Pliki (wyłączna własność):** zmodyfikuj `src/imgwtools/exceptions.py`; w `src/imgwtools/__init__.py` usuń eksport `IMGWPlanStaleError` i dodaj `IMGWCancelledError`, `ERROR_CODES`, `ErrorSpec`, `ErrorCode`; w `src/imgwtools/api/routes/store.py` usuń wyłącznie gałąź `IMGWPlanStaleError` w `_status`; utwórz `tests/unit/test_exceptions.py`.  
**Zależy od:** —.  
**Test akceptacji:** każda klasa ma kod domyślny z §13.5, a `code=` go nadpisuje; kod spoza rejestru → `ValueError`; `str(exc) == exc.detail`, a `details` jest niezależną kopią; `pickle` i `copy.deepcopy` zachowują `code`, `detail` i `details` (wyjątek przechodzi przez `multiprocessing`); `ERROR_CODES` ma dokładnie 12 kodów z kodami wyjścia i statusami z tabeli §13.5, a kody wyjścia błędów są parami różne i różne od 0/10/11 koperty (130 jest wspólne z kopertą `cancelled` celowo); `IMGWStoreDependencyError()` zachowuje komunikat instalacji i ma `missing_dependency`.

**U02 — Typy koperty, stronicowania i katalogu.**  
**Pliki:** zmodyfikuj `src/imgwtools/store/types.py`, `tests/unit/test_store_types.py`; utwórz `src/imgwtools/_jsonable.py` (jedna serializacja JSON dla CLI, REST i `CommandResult.to_json`).  
**Zależy od:** —.  
**Test akceptacji:** `CommandResult.to_json(root=R)` daje dokument `imgw-result/1` (§13.6): ścieżka pod R → POSIX względna, poza R → bezwzględna, `server=True` → root `"."` i przedrostek R usunięty z tekstów; `datetime` → ISO z `Z`, `date` → `YYYY-MM-DD`, krotki → listy, dataclass i modele pydantic → pola; `Page`, `DownloadItem` i `DownloadReport` są niemutowalne; `OperationResult`, `CommandOption` i `DataCommand` z nowymi polami (§13.9) mają wartości domyślne, więc obecny katalog i raporty konstruują się bez zmian; `StoreEntry.slot` przyjmuje `None`; moduły nie importują pyarrow.

### Fala 11 — rejestr i odczyty live

**U03 — Rejestr 13 zbiorów, aliasy i selektory.**  
**Pliki:** `src/imgwtools/datasets.py` (pola deskryptora, pięć zbiorów tylko do pobrania, `get_dataset` z aliasami, `datasets(kind=)`, `archive_files(..., params=)`, publiczne `YearsArg`/`MonthsArg` i ich parser, z którego korzystają potem katalog i magazyn), `tests/unit/test_datasets.py`.  
**Zależy od:** U01.  
**Test akceptacji:** 13 deskryptorów z polami §13.4; `get_dataset` zwraca ten sam deskryptor dla klucza, sluga i aliasu legacy, a nieznana wartość → `validation_error` z `details.allowed`; `archive_files` pięciu zbiorów tylko do pobrania daje złote URL-e zapisane dosłownie w teście (wygenerowane raz z jeszcze istniejących `build_hydro_url`/`build_meteo_url`: `zjaw_2023`, miesięczne k/o/s dla 1955, 1995 i 2023 z deduplikacją lat jednego folderu, terminowe klimat 1995 i 2001-01); `2024`, `"2020-2023"`, `"2020,2022"` i `[2020, "2022-2023"]` jako `years` dają te same pliki co odpowiadające im listy liczb; `params` zawęża zbiór półroczny i jest odrzucane w innych; aliasy synop dobowe/terminowe i terminowe opad → `validation_error` z powodem; `datasets(kind="meteo")` zawiera wyłącznie meteo.

**U04 — Odczyty live i wyszukiwanie stacji.**  
**Pliki:** `src/imgwtools/fetch.py` (wyłącznie funkcje live: `fetch_hydro_current`, `fetch_meteo_current`, `fetch_synop`, `fetch_warnings`, `fetch_pmaxtp` i warianty `_async`), `src/imgwtools/models.py`, `src/imgwtools/stations.py`, `src/imgwtools/reference_data.py` (przejście na `find_stations`/`fetch_hydro_states`; nagłówki plików bez zmian), `src/imgwtools/__init__.py`, `tests/unit/test_fetch.py` (klasy testów funkcji live), `tests/unit/test_fetch_live.py`, `tests/unit/test_models.py`, `tests/unit/test_stations.py`, `tests/unit/test_stations_extra.py`, `tests/unit/test_reference_data.py`.  
**Zależy od:** U01.  
**Test akceptacji (nagrane odpowiedzi `respx`):** modele mają `station_code`, a `HydroCurrentData` także `latitude`/`longitude` z `lat`/`lon` API; `fetch_meteo_current` mapuje `kod_stacji`, `temperatura_powietrza`, `wiatr_srednia_predkosc`, `wilgotnosc_wzgledna`, `opad_10min`, a brak pola daje `None`; `fetch_warnings()` łączy ostrzeżenia hydro i meteo z polem `kind`; `fetch_pmaxtp(52.23, 21.01, method="AMP")` zwraca ten sam `PMaXTPResult` co przed zmianą; `find_stations` live: `query="lodz"` znajduje „ŁÓDŹ…”, działa dopasowanie rzeki i prefiksu kodu, kolejność `kind` → nazwa → kod, `kind=None` = obie listy; `source="store"` na `build_fixture_store` bez żadnego HTTP zwraca współrzędne z katalogu i `None` dla `geometry=null`; `source="store"` bez `root` → `validation_error`, magazyn bez listy → `IMGWStoreError` (kod `not_found` nadaje U05); `fetch_hydro_states` czyta pole `rzeka`; awaria sieci każdej funkcji live ma `code="source_unavailable"` oraz `details.url` i `details.reason`; warianty async dają identyczne wyniki.

### Fala 12 — magazyn: tożsamość, pobieranie, położenia

**U05 — Sloty, wersje i odczyt szeregów.**  
**Pliki:** `src/imgwtools/store/reader.py`, `src/imgwtools/store/sync.py`, `src/imgwtools/store/series.py`, `src/imgwtools/store/writer.py`, `src/imgwtools/coverage.py`, `src/imgwtools/store/types.py`, `src/imgwtools/store/__init__.py`; tylko miejsca wywołań `current_version`/`StationCoverage` w `src/imgwtools/commands.py`, `src/imgwtools/project.py`, `src/imgwtools/stations.py`, `src/imgwtools/api/routes/store.py`; testy `tests/unit/test_store_reader.py`, `test_store_sync.py`, `test_store_series.py`, `test_store_writer.py`, `test_store_archive_read.py`, `test_coverage.py`, `test_store_types.py` oraz wyłącznie asercje slotów w `tests/unit/test_commands.py`, `tests/unit/test_project.py`, `tests/unit/test_api_store.py`, `tests/contract/test_versioned_store.py`.  
**Zależy od:** U01, U02, U03.  
**Test akceptacji:** na `build_fixture_store` każdy slot wersji z `iter_store` zwraca w `current_version` swoją bieżącą wersję, a slot z `SyncReport.items` dla tego samego pliku jest identyczny z wpisem skanu (gramatyka §13.7); dawne postaci slotów → `validation_error` z opisem gramatyki; problem bez wersji ma `slot=None`; `read_series(variables=None)` zwraca wszystkie zmienne, `version` względna z `root` = bezwzględna, `root`+`dataset` = bieżąca wersja, oba albo żadne → `validation_error`; `summarize_series` przy zablokowanym imporcie `pyarrow` zwraca pokrycie równe spisowi `series.json`, filtruje `stations`/`variables`, a nieznana stacja → `validation_error`; `select_series` ma semantykę dawnego `series select`; `check_store(..., plan=PLIK)` zapisuje plan poza root, w root → `validation_error`; `years="2023-2024"` działa w `check_store`/`sync_store`; kody: brak wersji, sidecara lub listy stacji → `not_found`, nieobsługiwany root → `store_unavailable`, `init_store` w niepustym katalogu i magazyn zagnieżdżony → `conflict`, dowiązanie w ścieżce → `validation_error`, anulowanie `write_archive` → `IMGWCancelledError`.

**U06 — Pobieranie płaskie, położenia, PMAXTP i pomocnicze URL.**  
**Pliki:** `src/imgwtools/fetch.py` (`download_archives`, `download_hydro_data`/`download_meteo_data` przez rejestr, wywołania pomocników URL), `src/imgwtools/core/url_builder.py` i `src/imgwtools/urls.py` (`build_pmaxtp_url(latitude, longitude, *, method)`, `build_api_url(endpoint, *, station, station_name)`), `src/imgwtools/store/catalog.py`, `src/imgwtools/store/pmaxtp.py`, `src/imgwtools/reference_data.py` (nagłówek `station_code,latitude,longitude`), `src/imgwtools/testing.py`; tylko miejsca wywołań pomocników URL w `src/imgwtools/api/routes/hydro.py`, `meteo.py`, `pmaxtp.py`, `src/imgwtools/cli/fetch.py`, `src/imgwtools/web/app.py`; fixtury położeń w `tests/fixtures/store/` i ich kopia w `src/imgwtools/_data/fixtures/`; testy `tests/unit/test_fetch.py` (pobieranie), utwórz `tests/unit/test_download_archives.py`, zmodyfikuj `test_store_catalog.py`, `test_store_pmaxtp.py`, `test_fixture_builder.py`, `test_store_fixtures.py`, `test_urls.py`, `test_reference_data.py`, a w `test_api_live_routes.py` i `test_web_app.py` wyłącznie wywołania.  
**Zależy od:** U01–U04.  
**Test akceptacji:** `download_archives` na nagranym serwerze zapisuje `<output>/<server_path>` przez `.part`; plik z błędem HTTP daje pozycję `failed` z `error_code="source_unavailable"`, pozostałe `downloaded`, bez wyjątku; anulowanie między plikami → `cancelled=true` i brak niepełnego pliku; `license_terms` raz; sloty pozycji według §13.7; `download_hydro_data("dobowe", 2023, 13)` i `download_meteo_data("miesieczne", "synop", 1995)` trafiają w te same URL-e co przed zmianą; `build_catalog` czyta `station_code,latitude,longitude[,source]` dla pliku statycznego i użytkownika, stary nagłówek → `validation_error` z instrukcją `python -m imgwtools.reference_data`, a `reference_data` zapisuje nowy nagłówek z szerokością przed długością; `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp` bez `method` używają `POT`; brak komórki → `not_found`; `build_pmaxtp_url(52.23, 21.01, method="AMP")` daje ten sam URL co przed zmianą.

### Fala 13 — eksport i katalog komend

**U07 — Eksport archiwów i szeregów.**  
**Pliki:** `src/imgwtools/store/export.py`, `tests/unit/test_series_export.py`; utwórz `tests/unit/test_store_export.py`.  
**Zależy od:** U01, U02, U05.  
**Test akceptacji:** `export_archive(v, format="csv")` daje linie identyczne z dotychczasowym wyjściem `imgw store read` dla fixtury (złoty plik zapisany przed zmianą), `jsonl` — pola `NormalizedRecord`; `path` w magazynie → `validation_error`, poza nim atomowy plik; `export_series` bez `path` daje linie bajtowo równe plikowi zapisanemu z `path`; `start`/`end` działają włącznie (miesiąc i półrocze według daty początku); `variables=None` = wszystkie zmienne; `root`+`dataset` = bieżąca wersja; anulowanie → `IMGWCancelledError`, plik docelowy nietknięty, bez `.part`; pusty szereg → `data_error`; `license_terms` przed pierwszą linią.

**U08 — Katalog komend, koperta, stronicowanie i schemat.**  
**Pliki:** `src/imgwtools/commands.py`; w `src/imgwtools/project.py` wyłącznie konsumpcja `CommandResult` i nowe nazwy opcji zadań; `tests/unit/test_commands.py`; utwórz `tests/unit/test_command_schema.py`; zmodyfikuj `tests/contract/support.py` (walidator kontraktowy: `anyOf`, `oneOf`, `items`, `required`, `dependentRequired`, `additionalProperties`).  
**Zależy od:** U01–U06; z U07 wyłącznie podpisy §13.8 (testy `store export`/`series export` wykonują U09, U10 i U14).  
**Test akceptacji:** każda z 35 komend wskazuje istniejącą funkcję publiczną (w module `imgwtools.*`; komplet w `imgwtools.__all__` domyka U13), a jej opcje (bez `limit`/`offset`) są parametrami tej funkcji o tych samych nazwach (`inspect.signature`); `validate_command` zamienia aliasy zbiorów na klucze, tekst współrzędnych na `float`, daty na `date` i każdą postać `years` na krotkę liczb, a nieznaną opcję odrzuca z `details.option`; `format_command` → ponowne sparsowanie → `validate_command` daje identyczne opcje dla przykładowych opcji każdej komendy; przykładowe poprawne i błędne opcje każdej komendy są tak samo oceniane przez `command_schema(c)` (walidator kontraktowy) i `validate_command`; `command_schema()` to dokument `imgw-commands/1` z 35 schematami, grupami i rejestrem błędów; `run_command` zwraca `CommandResult` ze statusem z tabeli §13.6 na raportach z fixtur (jedna pozycja `failed` → `partial`, wszystkie → `failed`, anulowanie → `cancelled`) i komunikatami bez powtórzeń przy pełnych hookach; `limit`/`offset` → `Page` z `total`, `limit=0` → `validation_error`; `check_command` każdej komendy działa bez sieci (ścisły `respx`) i bez zapisu (porównanie drzewa katalogów); `download_project` przypina te same pliki co przed zmianą.

### Fala 14 — adaptery generowane z katalogu

**U09 — CLI z katalogu.**  
**Pliki:** `src/imgwtools/cli/_dispatch.py`, `src/imgwtools/cli/main.py`; usuń `src/imgwtools/cli/fetch.py`, `cli/list_cmd.py`, `cli/store.py`, `cli/series.py`, `cli/pmaxtp.py`, `cli/project.py`; testy `tests/unit/test_cli_fetch_live.py`, `test_cli_fetch_store.py`, `test_cli_list.py`, `test_cli_store_project.py` zastąp nowym `tests/unit/test_cli_catalog.py`; zmodyfikuj `tests/unit/test_cli_main.py`.  
**Zależy od:** U07, U08.  
**Test akceptacji (`CliRunner` i zainstalowany `imgw`):** stdout komendy obiektowej i listowej = `run_command(...).to_json(root)` dla tych samych opcji, a strumień nie zawiera koperty; macierz błędów — zła szerokość (2), brak wersji (3), `store init` w niepustym katalogu (4), awaria źródła z `respx` (5), zablokowany `pyarrow` (6), uszkodzona fixtura (7), katalog bez znacznika (8), katalog wyjściowy bez prawa zapisu (9): pusty stdout, ostatnia linia stderr to JSON z właściwym kodem; synchronizacja z jedną nieudaną pozycją → koperta na stdout i kod 10, wszystkie nieudane → 11; Ctrl+C → raport częściowy i 130; nieznana flaga → JSON `validation_error` i kod 2; `--check` tylko przy komendach z bliźniakiem; `--schema` = wynik `imgw commands schema --command …`; `--root` z `IMGW_STORE_ROOT`; aliasy §13.2 działają.

**U10 — REST z katalogu i problem+json.**  
**Pliki:** `src/imgwtools/api/main.py`, `src/imgwtools/api/schemas.py` (zostaje `HealthCheck`); utwórz `src/imgwtools/api/routes/commands.py` i `src/imgwtools/api/errors.py`; usuń `src/imgwtools/api/routes/hydro.py`, `meteo.py`, `download.py`, `pmaxtp.py`, `store.py`; zmodyfikuj `src/imgwtools/config.py` (`api_max_limit`, env `IMGW_API_MAX_LIMIT`); testy `tests/unit/test_api_download_registry.py`, `test_api_live_routes.py`, `test_api_store.py` zastąp nowym `tests/unit/test_api_commands.py`; zmodyfikuj `tests/unit/test_api_main.py`.  
**Zależy od:** U07, U08.  
**Test akceptacji (`TestClient`, nagrane IMGW, fixtura magazynu):** każda komenda z metodą odpowiada pod `/api/v1/<grupa>/<nazwa>` kopertą równą `run_command(...).to_json(root, server=True)`; problem+json z `instance` i kodem dla: walidacji katalogu i złego typu w ciele (400), nieznanej trasy (404), złej metody (405), braku `IMGW_STORE_ROOT` (503 `store_unavailable`, `reason=not_configured`), wyłączonego zapisu i złego tokenu (403 `forbidden`), awarii źródła (502), braku pyarrow (503); `?check=true` na każdym POST zwraca plan bez zapisu i bez tokenu; sync z pozycją `stale_plan` → 200, `status=partial`, raport w `result`; po synchronizacji `notices` zawiera `license_terms`; `limit` domyślnie i najwyżej `IMGW_API_MAX_LIMIT`, większy → 400; `store export`/`series export` zwracają strumień równy stdout CLI z nagłówkami `X-IMGW-Status`/`X-IMGW-Notices`; `version` bezwzględna, z `..`, przez dowiązanie lub spoza właściwego `*/versions/` → 400, nieistniejąca → 404; `root`, `path` lub `output` w żądaniu → 400; żadna odpowiedź nie zawiera bezwzględnej ścieżki serwera.

### Fala 15 — projekt i web

**U11 — Projekt w nowych konwencjach.**  
**Pliki:** `src/imgwtools/project.py`, `src/imgwtools/store/types.py` (`ProjectFile.station_code`), `tests/unit/test_project.py`, `tests/contract/test_project_contract.py`.  
**Zależy od:** U05, U08.  
**Test akceptacji:** manifest z `files[].station_code` przechodzi zapis, odczyt i walidację §11.6, a klucz `station` jest odrzucany; `ProjectReport.files` mają slot §13.7 i pole `task`, błąd całego zadania ma `slot=None`, a pozycje błędów — `error_code`; brak manifestu → `not_found`, zajęta blokada → `conflict` z `details.owner`, nieczytelny manifest → `io_error`, niepoprawna treść → `validation_error`; opcje zadań mają nazwy §13.2 (stare `lat`, `dataset` w `store sync` i `no_series` są odrzucane); scenariusz init → add → check → download → status → verify przypina te same pliki co przed zmianą.

**U12 — Web na publicznym API.**  
**Pliki:** `src/imgwtools/web/app.py`, `src/imgwtools/web/templates/**`, `src/imgwtools/web/static/**`, `tests/unit/test_web_app.py`.  
**Zależy od:** U03, U04, U08, U10.  
**Test akceptacji:** punkt PMAXTP poza siatką (nagrane API) renderuje `partials/error.html` z `validation_error` i polskim `detail` zamiast pustej strony wyniku; wyszukiwanie stacji `lodz` daje te same stacje i stronicowanie co `stations find`; formularz pobierania oferuje 10 zbiorów archiwalnych z rejestru i generuje te same URL-e co `archive_files`; mapa ładuje markery z `GET /api/v1/current/hydro-states`; awaria źródła w dowolnym widoku → ten sam fragment z `source_unavailable`.

### Fala 16 — sprzątanie i kontrakt

**U13 — Usunięcie legacy i jedna lista eksportów.**  
**Pliki:** `src/imgwtools/core/url_builder.py`, `src/imgwtools/urls.py`, `src/imgwtools/__init__.py`, `src/imgwtools/store/__init__.py`, `src/imgwtools/config.py` (usunięcie `hydro_stations_csv`/`meteo_stations_csv`), `src/imgwtools/reference_data.py` (bez plików `*_stations_names.csv`), `tests/unit/test_urls.py`, `tests/unit/test_public_store_api.py`, `tests/unit/test_reference_data.py`.  
**Zależy od:** U01–U12.  
**Test akceptacji:** `imgwtools.__all__` = §13.12: każda nazwa jest importowalna i zaimplementowana, a nazw z listy usuniętych nie ma w pakiecie (także w `imgwtools.urls`); `import imgwtools` nie ładuje `pyarrow`, `fastapi` ani `typer`; `python -m imgwtools.reference_data` (nagrane HTTP) zapisuje wyłącznie plik położeń i opisy formatów.

**U14 — Kontrakt międzyinterfejsowy.**  
**Pliki:** `tests/contract/test_cli_api_parity.py`, `tests/contract/conftest.py`, `tests/fixtures/store/contract_schemas.json` (dopisz `imgw-result/1` i problem+json); utwórz `tests/contract/test_interface_contract.py` oraz w razie potrzeby nowe `tests/fixtures/store/contract_*`.  
**Zależy od:** U01–U12.  
**Test akceptacji:** dla każdej komendy z trasą REST na fixturze i nagraniach Python (`run_command(...).to_json`), stdout CLI i ciało REST są równe po kanonicznym zrzucie JSON (REST z root `"."`); dla każdego kodu z rejestru scenariusz wyzwalający w każdym interfejsie, który ten kod zgłasza, daje ten sam `code`, kod wyjścia i status z §13.5; każda koperta i każde ciało błędu spełniają schematy §13.5–§13.6; ten sam `limit`/`offset` daje te same `items` i `total` w trzech interfejsach; slot z wyniku dowolnej komendy działa w `current_version`, a `version` z odpowiedzi REST działa jako `--version` CLI z `--root`; zero ruchu sieciowego poza nagraniami.

### Fala 17 — wydanie

**U15 — Dokumentacja wydania.**  
**Pliki:** `docs/CHANGELOG.md`, `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`, `docs/DEVELOPMENT_STANDARDS.md` (konwencje nazw i obsługa błędów), `docs/PRD.md` (jeśli opisuje usunięte komendy lub trasy).  
**Zależy od:** U01–U14; wynik U16 dopisuje do `docs/PROGRESS.md` po jego zakończeniu (jedyna zależność wewnątrz fali, bez wspólnych plików).  
**Test akceptacji:** sekcja BREAKING w CHANGELOG 3.0.0 obejmuje każdy wiersz §13.11 (pogrupowany), a „Dodane” — kody błędów, `find_stations`, `command_schema`, stronicowanie i `summarize_series`; tabele komend i tras w README i CLAUDE.md zgadzają się z wynikiem `imgw commands schema` (jednorazowy skrypt porównujący, bez trwałego testu); każdy przykład komendy i kodu z README uruchomiony raz (offline na fixturze albo live) daje opisany wynik; historyczne wpisy ADR bez przeredagowania.

**U16 — Bramka końcowa i pełna regresja live.**  
**Pliki:** na czas fali wyłączna własność `src/**` i `tests/**` do napraw (U15 zmienia wyłącznie dokumentację); utwórz `tests/live/__init__.py` i `tests/live/test_interfaces_live.py` (pomijany bez `IMGW_LIVE=1`).  
**Zależy od:** U01–U14.  
**Test akceptacji:** po scaleniu raz `.venv/bin/python -m pytest`, `.venv/bin/ruff check src/ tests/` i `npx -y pyright src/imgwtools/` bez błędów; `IMGW_LIVE=1 .venv/bin/python -m pytest tests/live` na prawdziwych serwerach IMGW w świeżym magazynie tymczasowym wykonuje każdą z 35 komend przez Python, zainstalowany `imgw` i REST (`imgw server` na localhost) na małych wyborach (jeden rocznik, jedna stacja, jedna komórka, `--limit`): koperty mają zgodne `status`, klucze, sloty i ścieżki (dane bieżące porównywane strukturą); błędy na żywo — współrzędne poza Polską, punkt poza siatką PMAXTP, nieistniejąca wersja, nieobsługiwany root — dają ten sam kod, kod wyjścia i status HTTP; każde znalezisko naprawione z testem regresyjnym offline; raport przebiegu (data, wersje, czasy, różnice) trafia do U15.
