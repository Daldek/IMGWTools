# IMGWTools - Progress Tracker

## Aktualny Status

| Pole | Wartość |
|------|---------|
| **Wersja** | 3.0.0 |
| **Data** | 2026-10-19 |
| **Gałąź robocza** | `feature/chmi-agents` (dostawca ČHMÚ ADR-003, wsparcie agentów AI ADR-004; wcześniej `feature/versioned-store`: magazyn ADR-001, spójne interfejsy ADR-002, otwarte dziedziny `/1` ADR-003 C01) |
| **Python** | >=3.12 |

---

## Wydane wersje

| Wersja | Data | Zakres |
|--------|------|--------|
| v3.0.0 | 2026-10 | **Wersjonowany magazyn danych** (ADR-001): `imgwtools.store`, parsery meteo, szeregi Parquet, katalog `stations.geojson`, PMAXTP per komórka, projekty `imgw-project/1`; **jeden katalog 37 komend** (ADR-002): koperta `imgw-result/1`, stronicowanie, rejestr kodów błędów, CLI i REST generowane z katalogu, problem+json; **dostawca ČHMÚ** (ADR-003): rejestr 17 zbiorów dwóch dostawców (`cz.chmi.*`), aktualność z listingu, treść kanoniczna i rejestr obserwacji, katalog stacji z progami SPA, jakość i flagi w szeregach, odtwarzanie przypięć treścią; **wsparcie agentów AI** (ADR-004): `AGENTS.md`/`llms.txt`, opisy angielskie, metadane skutków, serwer MCP (`imgw mcp`, `/mcp`), `GET /llms.txt`; **breaking:** `imgw fetch`/`imgw list` → grupy katalogu, nowe trasy REST, `station_id` → `station`/`station_code`, `download_*` → `DownloadResult`, usunięcie cache SQLite i `core/url_builder`. Szczegóły: `docs/CHANGELOG.md` |
| v2.2.0 | 2026-08 | Licencja (rok, PEP 639), ręczny proces CLA, moduł danych referencyjnych IMGW-PIB (`reference_data.py`), usunięcie danych IMGW z repo, **usunięcie legacy `core/imgw_spatial.py`** (breaking: extras `[spatial]` → `[pandas]`, `StationMap` usunięty) |
| v2.1.1 | 2026-07 | Parsery: auto-detekcja separatora/kodowania (UTF-8 BOM)/cudzysłowów; URL-e meteo zgodne z serwerem IMGW; zgodność z pyright; audyt dokumentacji |
| v2.1.0 | 2026-01 | Python 3.12+, modernizacja kodu (ruff fix), DEVELOPMENT_STANDARDS.md |
| v2.0.1 | 2026-01 | Fix import error (lazy load db module) |
| v2.0.0 | 2026-01 | Refaktoring API, nowa architektura |
| v1.0.0 | 2025-xx | Pierwsze stabilne wydanie |

---

## v3.0.0 — szczegóły wydania (2026-10-19)

Wydanie major realizujące ADR-001 (`docs/DECISIONS.md`) według planu `docs/superpowers/plans/2026-10-17-versioned-store.md` (zadania T01–T24) i kontraktu `docs/superpowers/specs/2026-10-17-versioned-store-design.md`. Pełna lista zmian: `docs/CHANGELOG.md`.

- **Fala 0 (T01–T06):** rejestr `datasets.py` (`pl.imgw.*`, `archive_files`, `station_source_files`), `DownloadResult` w `download_*`, parsery w `_parsing/` (hydro przeniesione z `db/`, nowe meteo `k_d`/`o_d` z flagami), poprawki `stations.py` (`river_order`, `hydrographic_code`, pole `rzeka`), syntetyczne archiwa i nagrania w `tests/fixtures/store/`, typy i wyjątki magazynu.
- **Fala 1 (T07–T10):** writer z atomową publikacją bez zastępowania i sidecarem `imgw-meta/1`, `summarize_coverage`, `imgw fetch` odwzorowujące ścieżki serwera, URL-e REST z rejestru.
- **Fala 2 (T11–T14):** katalog `stations.geojson` (obrys Polski Natural Earth, bez GIS w runtime), `check_store`/`sync_store` z planem `imgw-plan/1`, szeregi Parquet `imgw-series/1`, PMAXTP per komórka.
- **Fala 3 (T15–T16):** publiczne API odczytu (read-only, problemy raportowane) i `imgwtools.testing.build_fixture_store`.
- **Fala 4–5 (T17–T19):** eksport CSV z atrybucją IMGW-PIB, katalog komend `commands.py`, projekty `imgw-project/1`.
- **Fala 6 (T20–T21):** CLI `imgw store|series|pmaxtp|project` generowane z katalogu, REST magazynu za `IMGW_STORE_ROOT` i tokenem zapisu.
- **Fala 7 (T22–T24):** usunięcie cache SQLite bez shimów (pakiet `db/`, komenda CLI, `/api/v1/hydro/data`, ustawienia, dodatek), jedna lista eksportów `imgwtools.__all__`, dodatek `[store]`, wersja 3.0.0, `docs/CHANGELOG.md` i aktualizacja dokumentacji.

**Decyzja właściciela (2026-10-17):** magazyn wersjonowany wchodzi teraz, jako 3.0.0; dawna wizja „Obserwator 3.0” (`docs/OBSERWATOR_SPEC.md`) pozostaje przyszłym rozszerzeniem (zmiana nazwy, providery) i nie obejmuje już cache SQLite v2.

**Stan po ADR-001 (T25, 2026-10-18):** 998 passed (w tym kontrakt T25 w `tests/contract/`), pokrycie 93% (`pytest --cov=imgwtools`), `ruff check` czysto, `pyright` 0 błędów.

**ADR-002 — jeden katalog komend i spójne interfejsy** (plan `docs/superpowers/plans/2026-10-17-versioned-store.md`, zadania U01–U16; spec §13):

- **Fale 10–11 (U01–U04):** rejestr kodów błędów `ERROR_CODES` (`code`, `details`, `IMGWCancelledError`), typy koperty `CommandResult`/`Page` i jeden konwerter JSON; rejestr 13 zbiorów z aliasami i `YearsArg`/`MonthsArg`; funkcje na żywo ze `station`/`station_code`, `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`.
- **Fale 12–13 (U05–U08):** jedna gramatyka slotów, `select_series`, `summarize_series`, `download_archives`, PMAXTP z `method="POT"`, `export_archive`/`export_series` (plik albo strumień linii), katalog 35 komend z `command_schema` i stronicowaniem.
- **Fale 14–15 (U09–U12):** CLI i REST generowane z katalogu (koperta na stdout, JSON błędu na stderr, kody wyjścia, problem+json, `?check=true`), projekt w konwencjach ADR-002, web wyłącznie na publicznym API.
- **Fala 16 (U13–U14):** usunięcie starych builderów URL, `core/` i tras legacy; `imgwtools.__all__` zgodne z §13.12; kontrakt międzyinterfejsowy Python = CLI = REST (`tests/contract/test_interface_contract.py`).
- **C01 (ADR-003, przed tagiem):** otwarte dziedziny kontraktów `/1` (klucz zbioru, kraj, dostawca, licencja, kod WIGOS, `location_source`), `content_sha256`/`content_form`, rejestr obserwacji `imgw-observation/1`.
- **Fala 17 (U15):** dokumentacja wydania (CHANGELOG z tabelami migracji §13.11, README, CLAUDE.md, ARCHITECTURE, standardy); przykłady README uruchomione raz (Python i CLI na żywo na świeżym magazynie, odczyt na `build_fixture_store`, REST przez `imgw server`); tabele komend README i CLAUDE.md zgodne z `imgw commands schema` (skrypt jednorazowy).
- **Fala 17 (U16) — bramka końcowa i regresja na żywo:** nowy `tests/live/test_interfaces_live.py` (pomijany bez `IMGW_LIVE=1`, raport JSON przez `IMGW_LIVE_REPORT`). Przebieg 2026-10-18T21:09:34Z (178,4 s, świeży magazyn w tmpfs, `imgw server` na localhost, żądania sekwencyjne): **42 passed** — każda z 35 komend przez Python, zainstalowany `imgw` i REST zgodna (status, klucze, sloty, ścieżki, strumienie bajt w bajt, drzewa magazynu; komendy lokalne w REST → 404 `not_found`), 6 błędów na żywo zgodnych (`validation_error` 2/400, `not_found` 3/404, `store_unavailable` 8/503). Naprawa z przebiegu: względne ścieżki przypięć projektu w JSON koperty nie zależą już od katalogu roboczego (`_jsonable`). Przebiegi przerwane awarią po stronie IMGW zgłaszały ją jednakowo (`source_unavailable`, exit 5 / HTTP 502); test powtarza taki przebieg po 20 s i 60 s. Bramka: `pytest` 1377 passed, 42 skipped (live); `ruff check` i `ruff format --check` czysto; `pyright` 0 błędów. Razem 1419 testów (`pytest --collect-only`).

**ADR-003 — dostawca ČHMÚ** (spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md`, plan C01–C10 w §16; decyzją właściciela z 2026-10-19 w wydaniu 3.0.0, errata ADR-003 D16):

- **Fala C1 (C02–C03):** rejestr dostawców (`ProviderDescriptor`, `providers`, `get_provider`) i 4 deskryptory `cz.chmi.*`, `archive_files(stations=)`, typy §9.4, `write_archive` z polami dostawcy z rejestru, formą kanoniczną `chmi-json/1` (`content_sha256`), wierszem `content_unchanged` i zapisem obserwacji; parsery ČHMÚ (hydro JSON, meteo CSV, metadane, listing nginx) i syntetyczne pliki z fikcyjnymi kodami WIGOS.
- **Fala C2 (C04, C06):** aktualność z listingu katalogów (`check_store`/`sync_store` ze `stations`, pola planu `station_code`, `signal`, `remote_listed_at`, `local_observation`, `requests`), `download_archives` z `not_published`, nagrania `chmi_recordings.json`; katalog stacji ČHMÚ (`stations/versions/chmi_stations/`, progi SPA, obrys Czech), czytniki per dostawca (`iter_store`, `read_catalog`, `read_station_list`, `store_info().providers`).
- **Fala C3 (C05, C07):** szeregi ČHMÚ z okresami znanymi per stacja (`stations[<kod>].periods`, `summarize_coverage(station_periods=)`), kolumny jakości i flag w Parquet, CSV i JSONL, atrybucja dostawcy w eksportach; katalog 36 komend (`datasets providers`, opcje `provider` i `stations`, `data_commands(provider=)`), `find_stations` dla ČHMÚ, tytuł „Źródło danych niedostępne”, web wyłącznie IMGW-PIB.
- **Fala C4 (C08):** projekty z zadaniami ČHMÚ i odtwarzaniem treścią (`restored_by_content`, `content_match`, `pin_restored_by_content`, `get_project_status(on_notice=)`), magazyn testowy `build_fixture_store(variant="complete_pl_cz")`.
- **Fala C5 (C09):** kontrakt IMGW-15..19 `tests/contract/test_chmi_contract.py` (68 testów, parytet Python/CLI/REST/MCP) i test na żywo `tests/live/test_chmi_live.py` — przebieg 2026-10-19: 26 passed w 77 s, 124 żądania, 31,5 MB (stacje `0-203-1-001000`, 2024–2026 z nieopublikowanym 2026, i `0-203-0-11799`); naprawa z przebiegu: `details.value` w `series select` jako lista. Pełna bramka (obejmuje A01–A05): `pytest` 2129 passed, 79 skipped (live); `ruff check` i `ruff format --check` czysto; `pyright` 0 błędów. Regresja IMGW-PIB na żywo (`tests/live/test_interfaces_live.py`, 37 komend i noga MCP): 53 passed w 103 s.

**ADR-004 — wsparcie agentów AI** (spec `docs/superpowers/specs/2026-10-19-agent-support-design.md`, plan A01–A06 w §11):

- **Fala C4 + A1 (A01):** opisy angielskie katalogu, grup, błędów i zbiorów (`help_en`, `description_en`, `rules_en`, `title_en`), `command_schema(lang=)`, `IMGW_LANG` w CLI (także elementy Typer/Click), `Accept-Language` w REST, metadane skutków (`writes`, `network`, `operation_id`, `env_root_when`).
- **Fala A2 (A02, A03):** `agent_guide`, komenda `commands guide` (37.), pliki pochodne `AGENTS.md` i `llms.txt` z testem dryfu; adapter MCP `src/imgwtools/mcp/` (dodatek `imgwtools[mcp]`, tryby `read`/`write`/`http`).
- **Fala A3 (A04, A05):** porządek komunikatów legacy (pomoc `imgw admin`, `version`, `server`, opisy pól OpenAPI, `reference_data`, strony HTML poza OpenAPI; ponowny skan dopisał pozycje 34–37 spec §7.2 i uzupełnienia §7.3 — errata A04); `imgw mcp`, `/mcp` (`IMGW_MCP_ENABLED`, `IMGW_MCP_ALLOWED_HOSTS`), `GET /llms.txt`, obraz Dockera na Pythonie 3.12 z `.[api,mcp]` i `location = /mcp` w nginx (obraz zbudowany i sprawdzony 2026-10-19: `/health`, `/llms.txt`, `initialize` na `/mcp`).
- **Fala A4 (A06) i C10:** dokumentacja wydania (CHANGELOG, README z sekcjami ČHMÚ i agentów, CLAUDE.md, ARCHITECTURE, standardy, PRD, RULES), erraty ADR-001 i ADR-002 według sekcji „Wpływ” ADR-003 i ADR-004, errata ADR-003 D13, status ADR-004 w indeksie, noty `[ADR-003]`/`[ADR-004]` w spec 2026-10-17 §13 i `[ADR-004]` w spec 2026-10-18 §9.3, „3.1.0” → 3.0.0 w spec ČHMÚ (z kontekstem historycznym); tabele komend README i CLAUDE.md zgodne z `imgw commands schema` (skrypt jednorazowy); przykłady ČHMÚ uruchomione raz offline na `complete_pl_cz` i na żywo (opendata.chmi.cz), przykłady MCP — konfiguracja stdio (także `--allow-writes`, `--lang en`, wariant `uvx`) i `/mcp` przez HTTP — przez klienta SDK, przykład Dockera na obrazie zbudowanym przez `docker compose build`. `AGENTS.md` i `llms.txt` bez regeneracji (teksty katalogu bez zmian); test dryfu i pełny `pytest`: 2129 passed, 79 skipped (live).

## v2.2.0 — szczegóły wydania (2026-08-22)

Wydanie minor — 20 commitów na gałęzi `slave` ponad v2.1.1, w tym zmiany łamiące kompatybilność (usunięcie legacy modułów spatial, api i datastore).

- **Licencja:** poprawiony rok w `LICENSE`; metadane licencji zgodne z PEP 639 w `pyproject.toml` (`license = "MIT"`, `license-files`).
- **Proces CLA:** ręczny proces CLA — `docs/CLA.md`, `CONTRIBUTING.md`, `CONTRIBUTORS.md`, szablon PR.
- **Dane referencyjne IMGW-PIB:** dane IMGW usunięte z repozytorium (`cf72e32`); nowy moduł `src/imgwtools/reference_data.py` do pobierania ich na żądanie (`python -m imgwtools.reference_data`); `data/shp` wyłączone spod śledzenia i zignorowane.
- **README:** nowa sekcja o źródłach danych i atrybucji.
- **Parsery:** notatki dokumentacyjne o przetwarzaniu ekstremów w `parse_semi_annual_csv`.
- **Testy:** fikcyjna stacja testowa „San Escobar" (123456789) zamiast realnych danych IMGW w fixturach.
- **Breaking: usunięcie `core/imgw_spatial.py`** — legacy moduł (martwe importy, błędy pyright) usunięty; extras `[spatial]` przemianowane na `[pandas]` (zależności `pyproj`/`pyshp` porzucone). Osoby instalujące `imgwtools[spatial]` lub importujące `StationMap` muszą zaktualizować kod — funkcjonalność nie ma bezpośredniego zamiennika w tym wydaniu.
- **Breaking: usunięcie `core/imgw_api.py` i `core/imgw_datastore.py`** — klasy oznaczone jako DEPRECATED od 2.0.0 (`HYDRO`, `SYNOP`, `METEO`, `WARNINGS`, `PMAXTPAPI`, `DataDownloader`) usunięte; zamienniki w publicznym API: `fetch_hydro_current`, `fetch_synop`, `fetch_warnings`, `fetch_pmaxtp`, `download_hydro_data`, `download_meteo_data`. W `core/` pozostał wyłącznie `url_builder.py`.
- **Dokumentacja i styl kodu (2026-08-22):** `ruff format` przebiegł na całym repozytorium (19 plików); wszystkie docstringi w `src/` przepisane na konwencję NumPy, a reguły `D` (pydocstyle, `convention = "numpy"`, bez `D401`) włączone w `pyproject.toml` jako stała bramka lintu (`tests/**` zwolnione). Skorygowano `docs/DEVELOPMENT_STANDARDS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/RULES.md`, `CLAUDE.md` i `README.md` do stanu faktycznego kodu. Weryfikacja: **109 passed**, `ruff check` czysto, `ruff format --check` czysto, `pyright` 0 błędów, pokrycie **23%** (`pytest --cov=imgwtools`).

**Stan końcowy v2.2.0:** 109 passed, `ruff check` czysto, `pyright` 0 błędów (weryfikacja jak dla v2.1.1 poniżej).

**Status:** przygotowane na gałęzi `slave`, commit `release: v2.2.0`; oczekuje scalenia do `master` (bez tagowania/publikacji na tym etapie).

## v2.1.1 — szczegóły wydania (2026-07-06)

### 🐛 Bugfix: obsługa niespójnych formatów archiwów IMGW w parserach (2026-07-05)

Archiwalne pliki CSV IMGW (`dane_hydrologiczne`) różnią się formatem między rocznikami w **trzech** aspektach. Parsery w `src/imgwtools/db/parsers.py` zakładały jeden format (średnik + CP1250), przez co większość roczników nie parsowała się wcale. Wszystkie trzy problemy naprawione:

1. **Separator** — większość roczników używa przecinka z cudzysłowami, część (np. 2023) średnika; niektóre pliki mają dodatkowy wiersz nagłówka z kodami kolumn. Zahardkodowany `delimiter=";"` powodował, że `parse_zip_file` **po cichu zwracał 0 rekordów** dla roczników przecinkowych. → helper `_detect_delimiter()` (per plik, z pierwszej niepustej linii; remis → średnik).
2. **Kodowanie** — standardem jest CP1250, ale `codz_2023.zip` (dobowe, plik roczny) jest w **UTF-8 z BOM**; parser rzucał `UnicodeDecodeError`. → helper `_decode_content()` (BOM → `utf-8-sig`; potem próba żądanego kodowania z fallbackiem UTF-8).
3. **Cudzysłowy** — w plikach dobowych i miesięcznych **2024** każda linia jest opakowana w zewnętrzny cudzysłów z podwojonymi cudzysłowami wewnątrz (`"149180020,CHAŁUPKI,...,""2024"",..."`), więc `csv.reader` widział jedno pole i parser po cichu zwracał 0 rekordów. → helper `_iter_rows()` (wiersz jednopolowy zawierający separator jest parsowany ponownie).

Wiodąca spacja w kodzie stacji i wiersz nagłówka są obsługiwane przez istniejące zabezpieczenia (`_safe_int`, `.strip().strip('"')`).

**Testy:** `tests/unit/test_parsers.py` — 28 testów (separator, kodowanie, cudzysłowy, end-to-end przez `parse_zip_file`). Po tej poprawce pakiet liczył 103 testy; docelowo dla całego wydania v2.1.1 jest ich **109** (patrz poprawka URL-i meteo niżej). `ruff check src/ tests/` i `ruff format --check` (wówczas tylko dla zmienionych plików — od 2026-08-22 formatowanie obejmuje całe repozytorium) — czysto; przy okazji naprawiono 13 zastanych błędów lint w starych plikach testowych (nieużywane importy, sortowanie importów).

**Weryfikacja na danych rzeczywistych (2026-07-05, liczby rekordów):**

| Plik | Format | Przed (2.1.0) | Po poprawce |
|------|--------|---------------|-------------|
| polr_Q_2020 | przecinek, CP1250 | 0 | 6007 |
| polr_Q_2023 | średnik, CP1250 | 6014 | 6014 |
| polr_Q_2024 | przecinek, CP1250, nagłówek | 0 | 6198 |
| mies_2019–2022 | przecinek, CP1250 | 0 | 29 802 – 30 171/rok |
| mies_2023 | średnik, CP1250 | 29 805 | 29 805 |
| mies_2024 | przecinek, CP1250, **linie w cudzysłowach** | 0 | 32 408 |
| codz_2020_01, codz_2022_06 | przecinek, CP1250 | 0 | 24 913 / 24 881 |
| codz_2023 | średnik, **UTF-8 z BOM** | `UnicodeDecodeError` | 301 994 |
| codz_2024 | przecinek, CP1250, **linie w cudzysłowach** | 0 | 326 845 |

**Pozostałe zmiany w ramach przygotowania wydania:**
- wersja podbita do **2.1.1** (`_version.py`, `pyproject.toml`); zaktualizowano `CLAUDE.md` (wersja, testy, notki o formacie CSV) i `README.md` (notka o formacie, liczby testów, pokrycie `db/parsers.py` 78%),
- `.gitignore`: dodano `.coverage`, `dist/`, `.python-version`, pliki bazy SQLite,
- naprawiono zastane błędy lint w `tests/` (ruff --fix).

**Status:** wydane w **v2.1.1** (patch — poprawki błędów, bez zmian publicznego API).

### 🔧 Typowanie: zgodność z Pylance/pyright (2026-07-05)

Pylance w VSC zgłaszał błędy w `db/parsers.py` (i szerzej). Weryfikacja `pyright` (silnik Pylance) na venv projektu potwierdziła: **136 błędów** w `src/`. Po poprawkach: **0 błędów**.

- **`Field(None, ...)` → `Field(default=None, ...)`** w 46 polach modeli pydantic (`models.py`, `db/models.py`, `api/schemas.py`, `stations.py`). Pyright nie rozpoznaje pozycyjnego defaultu przy przeciążeniach `Field` w pydantic 2.12 — pola opcjonalne wyglądały na wymagane (błędy „Arguments missing for parameters latitude, longitude"). Zmiana bez wpływu na runtime.
- **`db/parsers.py`**: jawne zawężanie typów — `not isinstance(content, str)` (obsługuje też bytearray/memoryview lepiej niż stary wariant), warunki `or` zamiast `all([...])` (pyright nie zawęża przez `all`). Usunięte błędy `int | None` i `memoryview.lstrip`.
- **`db/__init__.py`**: importy pod `TYPE_CHECKING` dla nazw ładowanych leniwie przez `__getattr__` — Pylance widzi symbole i podpowiada, runtime bez zmian (lazy loading zachowany).
- **`cli/db.py`**: zawężanie `isinstance` w gałęziach wyświetlania rekordów; **`api/routes/hydro.py`**: adnotacja `list[HydroDailyDataPoint | HydroMonthlyDataPoint]` dla `data_points` (inwariancja list).
- **`pyproject.toml`**: nowa sekcja `[tool.pyright]` (venvPath/venv + ignore dla legacy core); **`.vscode/settings.json`** (lokalna konfiguracja, nieśledzona w repo) ze wskazaniem interpretera `.venv` (bez niego Pylance analizuje pakiet ze starego globalnego pyenv 2.0.1).

**Zrealizowane 2026-08-22 (v2.2.0):** legacy moduły `core/imgw_spatial.py`, `core/imgw_api.py` (DEPRECATED od 2.0.0) i `core/imgw_datastore.py` (martwy import `wget`) zostały usunięte; `[tool.pyright].ignore` nie jest już potrzebne. W `core/` pozostał wyłącznie `url_builder.py`.

### 🐛 Bugfix: URL-e meteo niezgodne z rzeczywistą strukturą serwera IMGW (2026-07-05)

Weryfikacja funkcjonalna GUI (serwer uruchomiony lokalnie, wszystkie trasy + formularze + statyki) wykazała, że strony, mapa, lista stacji i PMAXTP działają, ale **`build_meteo_url` generował martwe linki (404)** — struktura plików meteo na serwerze IMGW różni się od opisanej w dokumentacji. Zweryfikowano listingi katalogów na żywo:

| Interwał | Podtyp | Rzeczywiste pliki | Poprzednio generowane |
|---|---|---|---|
| miesieczne (k/o/s) | ≤2000 | **jeden plik na folder 5-letni** `{folder}_m_{x}.zip` | `{rok}_{x}.zip` → 404 |
| dobowe/terminowe | klimat, opad | `{rok}_{x}.zip` (≤2000), `{rok}_{mm}_{x}.zip` (2001+) | ✓ poprawne |
| dobowe/terminowe | synop | **pliki per stacja** `{folder}_{kod}_s.zip` | `{rok}_{mm}_s.zip` → 404 |
| terminowe | opad | **zbiór nie istnieje** | `{rok}_{mm}_o.zip` → 404 |

Dodatkowo siatki folderów 5-letnich różnią się na starcie per podtyp: klimat `1951_1955`, opad `1950_1955`, synop `1960_1965` (folder 6-letni).

**Poprawka (`core/url_builder.py`):**
- `_get_meteo_folder(year, subtype)` — siatka folderów zależna od podtypu,
- miesieczne: nazwa pliku `{folder}_m_{x}.zip` (obejmuje oba okresy),
- synop dobowe/terminowe, terminowe opad, synop <1960 → czytelny `ValueError` zamiast martwego linku (GUI pokazuje komunikat w liście błędów),
- GUI (`web/app.py`): deduplikacja linków (lata ≤2000 mapują się na wspólny plik 5-letni).

**Weryfikacja:** 6 nowych wzorców URL sprawdzonych HEAD-em na serwerach IMGW — wszystkie **200 OK** (m.in. `1996_2000_m_s.zip`, `1950_1955_m_o.zip`, `1960_1965_m_s.zip`). Formularz GUI: poprawne linki + komunikat błędu dla synop dobowych. Testy: `test_urls.py` 22→28 (**pełny pakiet: 109 passed**). Zaktualizowano opisy struktury meteo w README.md i CLAUDE.md.

### 📚 Audyt dokumentacji przed wydaniem (2026-07-05)

Pełny przegląd dokumentacji względem kodu (subagent + weryfikacja ręczna). Ujednolicono pod v2.1.1:
- wersja 2.1.1 wszędzie (usunięto zalegające 2.0.0 w `ARCHITECTURE.md`, 1.0.0 w `PRD.md`),
- liczba testów **109** i status testów spójne między README/CLAUDE/PRD/DEVELOPMENT_STANDARDS,
- `ARCHITECTURE.md` — zaktualizowana sekcja parsowania CSV (auto-detekcja separatora/kodowania/cudzysłowów),
- `README.md` — poprawione źródło danych mapy (`hydro-back.imgw.pl/map/stations/hydrologic`, wcześniej błędnie `danepubliczne.imgw.pl/api/data/hydro`),
- type checker `mypy` → `pyright` w `DEVELOPMENT_STANDARDS.md` i sekcji „Komendy”; próg pokrycia ujednolicony na 80% (`RULES.md`/`PRD.md`/`DEVELOPMENT_STANDARDS.md`); dodano `test_parsers.py` i gałąź `slave` do odpowiednich list.

**Stan końcowy v2.1.1:** 109 passed, `ruff check` czysto, `pyright` 0 błędów.

### 🚀 Finalizacja wydania (2026-07-06)

- Usunięto sekcję `[tool.mypy]` i zależność `mypy>=1.6` z `pyproject.toml` — projekt używa wyłącznie **pyright** (`[tool.pyright]`).
- Zbudowano świeże artefakty `dist/` dla **2.1.1** (`python -m build`, backend hatchling); usunięto stare koła 2.0.1.
- Zmiany scalone z gałęzi `slave` do `master`.

---

## Cross-Project Analysis (2026-01-21)

Przeprowadzono analizę integracji 4 repozytoriów: **Hydrograf**, **Hydrolog**, **Kartograf**, **IMGWTools**.

### Mapa zależności

```
HYDROGRAF (główna aplikacja)
    ├── IMGWTools (dane IMGW) ← TEN PROJEKT
    ├── Kartograf (dane GIS)
    └── Hydrolog (obliczenia hydrologiczne)
            ├── IMGWTools (wymagany) ← TEN PROJEKT
            └── Kartograf (opcjonalny)
```

### Rola IMGWTools

IMGWTools jest **biblioteką bazową** używaną przez:
- **Hydrograf** - bezpośrednio (dane IMGW, PMAXTP)
- **Hydrolog** - jako wymagana zależność (dane opadowe dla obliczeń hydrologicznych)

### Problemy wykryte w IMGWTools

| Problem | Status | Priorytet |
|---------|--------|-----------|
| Python `>=3.11` (inne projekty `>=3.12`) | ✅ Naprawione (v2.1.0) | - |
| Używa `ruff` (inne używają `black+flake8`) | 🟡 Informacyjnie | NISKI |
| Używa `hatchling` (inne używają `setuptools`) | 🟡 Informacyjnie | NISKI |
| Brak DEVELOPMENT_STANDARDS.md | ✅ Naprawione (v2.1.0) | - |

### Standardy kodu - porównanie

| Aspekt | IMGWTools | Hydrolog | Kartograf | Zgodność |
|--------|-----------|----------|-----------|----------|
| Python | >=3.12 | >=3.12 | >=3.12 | ✅ |
| Line length | 88 | 88 | 88 | ✅ |
| Formatter | ruff | black | black | ⚠️ |
| Build | hatchling | setuptools | setuptools | ⚠️ |

### Rekomendacje

1. ~~**[ROZWAŻYĆ]** Podnieść Python do `>=3.12` dla spójności z innymi projektami~~ ✅ Zrobione (v2.1.0)
2. ~~**[BACKLOG]** Utworzyć DEVELOPMENT_STANDARDS.md (skopiować format z Hydrolog)~~ ✅ Zrobione (v2.1.0)
3. **[INFO]** Używanie `ruff` zamiast `black+flake8` jest OK (nowoczesne podejście)

### Pełna dokumentacja

Szczegółowa analiza cross-project: `Hydrograf/docs/CROSS_PROJECT_ANALYSIS.md`

---

## Backlog

**Jedyne źródło prawdy dla rzeczy do zrobienia** (konsolidacja 2026-08-02: dawne sekcje "Planowane"/"Zaimplementowane" oraz sekcja 11 z `PRD.md`). Nowe zadania dopisuj wyłącznie tutaj.

### Funkcjonalności

- [ ] API key enforcement — middleware walidujące nagłówek `X-API-Key`. CLAUDE.md odnotowuje, że klucze są zarządzane przez CLI (`imgw admin`), ale nieegzekwowane w żądaniach API — to brakująca warstwa bezpieczeństwa, nie nowa funkcja. Priorytet: wysoki.
- [ ] Per-key rate limiting — śledzenie i limitowanie żądań per klucz API. Zależne od API key enforcement. Priorytet: średni.
- [ ] GeoJSON w REST/GUI — wersjonowany katalog `stations.geojson` istnieje od 3.0.0 (`build_catalog`, `read_catalog`); brakuje komendy katalogu odczytującej go (a więc trasy REST) i warstwy na mapie Web GUI. Priorytet: średni.
- [ ] Data charts — wizualizacja szeregów czasowych. Możliwy wzorzec: podejście repo hydro-dane — agregaty min/avg/max z walidacją pełnego roku hydrologicznego i eksport do kompaktowych statycznych JSON-ów. Priorytet: niski.
- [ ] Eksport CSV w REST/GUI dla danych bez magazynu — od 3.0.0 `export_series`/`imgw series export`/`GET /api/v1/series/export` eksportują szeregi z magazynu; brak eksportu „na żądanie” bez magazynu. Priorytet: niski.
- [ ] Request logging — śledzenie użycia API do analityki. Priorytet: niski.
- [ ] Redis caching layer — cache dla często pobieranych danych. Priorytet: niski.

- [ ] Lepsze nazewnictwo KS/SG/RB w `PMaXTPData` — aliasy właściwości i metoda `get_design_precipitation()`; szczegóły w sekcji "TODO: Poprawa czytelności PMaXTPData" poniżej. Priorytet: średni.
- [ ] Natywna siatka PMAXTP w `fetch_pmaxtp` — od 3.0.0 magazyn PMAXTP (`sync_pmaxtp`/`read_pmaxtp`) kluczuje komórki indeksami `indX/indY` z odpowiedzi i zapisuje środek komórki w `cell.json`, ale `PMaXTPResult` z `fetch_pmaxtp` nadal nie ma pól `point`, brak funkcji konwersji/iteracji komórek, a docstringi podają zakres 7×6 zamiast 16×27; szczegóły w sekcji "TODO: Natywna siatka PMAXTP" poniżej. Zgłoszone z Hydrografa (2026-09-28). Priorytet: wysoki.
- [ ] Dane ČHMÚ w Web GUI — formularze i wyszukiwarka obsługują wyłącznie IMGW-PIB (`datasets(provider="IMGW-PIB")`); pliki ČHMÚ są per stacja, więc formularz potrzebuje wyboru stacji (spec ČHMÚ §9.3). Priorytet: niski.

### Wsparcie agentów AI (po 3.0.0, ADR-004)

- [ ] Decyzja właściciela: czy publiczny serwer włącza `/mcp` (`IMGW_MCP_ENABLED`) — ADR-004, pytanie otwarte 2. Priorytet: średni.
- [ ] Tłumaczenie treści wykonania (`detail`, `Notice.text`, postęp) na angielski — dziś tylko tytuły i opisy katalogu (ADR-004, pytanie 3). Priorytet: niski.
- [ ] Filtr narzędzi MCP według grup albo dostawcy (`--groups`, `--provider`, `data_commands(provider=…)`), gdy koszt kontekstu listy narzędzi (ok. 42 KB) okaże się problemem (ADR-004, pytanie 4). Priorytet: niski.
- [ ] Limit wywołań sieciowych serwera MCP na stdio (dziś tylko żądania sekwencyjne biblioteki) i zapis przez MCP po HTTP z autoryzacją (ADR-004, pytania 5–6). Priorytet: niski.

### Magazyn wersjonowany (po 3.0.0)

- [x] T25 — końcowy zestaw kontraktowy (`tests/contract/`): offline state machine HEAD→plan→sync→series→catalog→CSV→projekt→verify/restore, parytet ścieżek/SHA CLI = API (zrobione 2026-10-18).
- [ ] Lokalny, odbudowywalny indeks magazynu (ADR-001 D2: poza wydaniem 3.0.0; nigdy jako źródło prawdy). Priorytet: niski.
- [ ] Wniosek do IMGW-PIB o oficjalny wykaz współrzędnych stacji (ADR-001 Q6) oraz potwierdzenie znaczenia kodu hydrograficznego i kolejności `river_order` (Q4, Q5) — do tego czasu bez interpretacji. Priorytet: średni.
- [ ] Rozszerzenie magazynu o kolejne zbiory (meteo miesięczne/terminowe, synop) — D6 ogranicza 3.0.0 do pięciu zbiorów Archiwisty i PMAXTP. Priorytet: niski.
- [x] **C01 przed tagiem v3.0.0:** otwarcie dziedzin kontraktów `/1` dla kolejnych dostawców (`dataset`, `country`, `provider`, `license.id`, kod stacji WIGOS, wartości `location_source`), opcjonalne pola treści kanonicznej `content_sha256` i `content_form` w `imgw-meta/1` i w `files[]` `imgw-project/1` oraz rejestr obserwacji `imgw-observation/1` (katalog `observations/` w slocie archiwum, wpisy `kind="observation"` w skanie, wewnętrzna publikacja obserwacji) — bez zmiany zachowania i bajtów IMGW (zrobione 2026-10-18, commit `889d705`; wywołanie zapisu obserwacji w `write_archive` należy do C02).
- [x] **Dostawca ČHMÚ (Czechy, opendata.chmi.cz)** — ADR-003 i spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md` (plan C02–C10), w wydaniu 3.0.0 (errata D16): `cz.chmi.hydro_daily`, `cz.chmi.meteo_daily`, listy stacji i katalog `cz.chmi.stations` z progami SPA, aktualność z listingu, treść kanoniczna `chmi-json/1` z rejestrem obserwacji, jakość i flagi ČHMÚ w szeregach, odtwarzanie przypięć treścią; kontrakt IMGW-15..19 i test na żywo (zrobione 2026-10-19, C02–C10). Spełnia wymagania Archiwisty IMGW-15..19 (v0.6 „PL + CZ”).
- [ ] Pytania do ČHMÚ (chmi@chmi.cz; ADR-003, pytania 5–10): strefa czasu znaczników `historical` i definicja doby HD/QD, oficjalny rok hydrologiczny, czy regeneracje zachowują bajty i czy istnieje rejestr korekt, ciągłość `historical_csv`, znaczenie `WGS_ELE`, `RICKM`, `HA`, `QA`, `CEVT`, `PRF_ID`, pełny słownik `FLAG`. Priorytet: średni.
- [ ] Potwierdzenia Archiwisty (ADR-003, pytania 11–15): `stations[<kod>].periods` w etykietach pokrycia, rozróżnienie `relabeled`/`unchanged` treścią w IMGW-16, `restored_by_content`/`content_match` w IMGW-19, brak pól treści jako `null`, wpisy `kind="observation"` tylko do odczytu. Priorytet: średni.
- [ ] Obserwator — przyszła zmiana nazwy (`docs/OBSERWATOR_SPEC.md`), już bez cache SQLite (zastąpiony magazynem); dostawcę ČHMÚ opisuje ADR-003 (pozycja wyżej). Priorytet: niski.

### Infrastruktura i jakość kodu

- [x] ~~Fallbackowe listy stacji zaszyte w kodzie (`api/routes/hydro.py`, `api/routes/meteo.py`)~~ — trasy usunięte w 3.0.0 (ADR-002); listy stacji daje `find_stations` z CSV IMGW.

### Zrobione (archiwum)

- [x] CLI (`imgw` command)
- [x] REST API (FastAPI)
- [x] Web GUI (HTMX + Jinja2)
- [x] PMAXTP data
- [x] Current hydro/meteo/synop data
- [x] Archive data download
- [x] Warnings
- [x] ~~SQLite cache (optional)~~ — usunięty w 3.0.0 (ADR-001 D5), zastąpiony magazynem wersjonowanym
- [x] Wersjonowany magazyn danych: archiwa 1:1 z sidecarami, plan aktualności, szeregi Parquet, katalog `stations.geojson`, PMAXTP per komórka, eksport CSV, projekty, CLI i REST (v3.0.0)
- [x] Jeden katalog komend dla Pythona, CLI i REST: koperta `imgw-result/1`, stronicowanie, rejestr kodów błędów, `command_schema`, CLI i REST generowane z katalogu, kontrakt międzyinterfejsowy (ADR-002, v3.0.0)
- [x] Dostawca ČHMÚ w rejestrze, magazynie, katalogu komend i projektach (ADR-003, v3.0.0)
- [x] Wsparcie agentów AI: `AGENTS.md`/`llms.txt`, opisy angielskie katalogu, metadane skutków, serwer MCP `imgw mcp` i `/mcp`, porządek komunikatów legacy (ADR-004, v3.0.0)
- [x] Parsery meteo dobowych `k_d`/`o_d` z flagami braków (v3.0.0)
- [x] Publiczny budowniczy magazynu testowego `imgwtools.testing` dla Archiwisty i Retmana (v3.0.0)
- [x] Podniesienie Pythona do `>=3.12` dla spójności z innymi projektami (rekomendacja cross-project, v2.1.0)
- [x] DEVELOPMENT_STANDARDS.md w formacie z Hydrolog (rekomendacja cross-project, v2.1.0)

---

## TODO: Poprawa czytelności PMaXTPData (KS/SG/RB)

**Kontekst:** Skróty KS, SG, RB w odpowiedzi API PMAXTP mogą być mylące. Łatwo pomylić górną granicę przedziału ufności (SG) z właściwą wartością kwantyla (KS), co prowadzi do błędnych obliczeń hydrologicznych.

| Symbol | Znaczenie | Zastosowanie |
|--------|-----------|--------------|
| **KS** | Kwantyle (estymata punktowa) | Wartość projektowa (domyślna) |
| **SG** | Górna granica przedziału ufności | Obliczenia konserwatywne |
| **RB** | Błędy estymacji | Analiza niepewności |

### Propozycje zmian

**1. Aliasy dla lepszej czytelności:**
```python
@property
def quantiles(self) -> dict:
    """Alias for ks (precipitation quantiles)."""
    return self.ks

@property
def upper_bounds(self) -> dict:
    """Alias for sg (upper confidence bounds)."""
    return self.sg

@property
def errors(self) -> dict:
    """Alias for rb (estimation errors)."""
    return self.rb
```

**2. Metoda dla wartości projektowej z opcją konserwatywną:**
```python
def get_design_precipitation(
    self,
    duration_minutes: int,
    probability_percent: int,
    conservative: bool = False
) -> float | None:
    """Get design precipitation value for engineering design.

    Args:
        duration_minutes: Duration in minutes
        probability_percent: Probability in percent
        conservative: If True, return upper confidence bound (SG)
                     If False, return quantile estimate (KS) - default

    Returns:
        Precipitation [mm] for engineering design
    """
    if conservative:
        return self.get_confidence_bound(duration_minutes, probability_percent)
    return self.get_precipitation(duration_minutes, probability_percent)
```

**3. Rozszerzenie README** z tabelą znaczeń KS/SG/RB.

**Uwaga:** Istniejąca metoda `get_precipitation()` już zwraca prawidłową wartość (KS), ale bezpośredni dostęp do atrybutów `data.ks`, `data.sg`, `data.rb` może prowadzić do pomyłek.

---

## TODO: Natywna siatka PMAXTP

**Kontekst:** rozpoznanie z Hydrografa (2026-09-28, ~60 zapytań do `https://powietrze.imgw.pl/tpmax-api/point/P/KS/{lat}/{lon}`). Endpoint punktowy przypisuje zapytanie do najbliższego środka komórki regularnej siatki i zwraca jej parametry, których IMGWTools obecnie nie udostępnia. Bez nich klient nie wie, którą komórkę pobrał — gęste próbkowanie odpytuje wielokrotnie tę samą komórkę, rzadkie pomija komórki (siatka Hydrografa co 2 km pomijała ~80% komórek).

### Surowa odpowiedź

```json
{
  "point": {"lon": "21.0100", "lat": "52.2300", "name": "", "method": "POT",
            "dataLon": 21.007098333333, "dataLat": 52.234416666667,
            "indX": 751, "indY": 317, "recalcualted": true},
  "data": {"ks": {...}, "rb": {...}, "sg": {...}}
}
```

- `dataLon`/`dataLat` — środek komórki (WGS84), `indX`/`indY` — indeksy komórki.
- `recalcualted` (literówka po stronie IMGW) — znaczenie nieznane; brak tego pola w odpowiedzi poza zasięgiem danych.
- Poza Polską: indeksy i środek wracają, ale `data: {}` oraz dodatkowy klucz `error`.

### Parametry siatki (zmierzone)

| Parametr | Wartość |
|---|---|
| Układ | regularna siatka w stopniach WGS84 (EPSG:4326) |
| Krok | Δlon = 0.01001°, Δlat = 0.01° (~680 m × 1110 m na 52°N, ~0,75 km²) |
| Środek komórki | `lon = 13.489588333 + 0.01001 · indX`, `lat = 55.404416667 − 0.01 · indY` (indY rośnie na południe) |
| Przypisanie punktu | do najbliższego środka komórki (sprawdzone na granicach komórek) |

Zweryfikowane na punktach (52.23, 21.01) → (751, 317), (50.0, 19.0) → (550, 540), (54.0, 15.0) → (151, 140), (49.3, 14.2) → (71, 610, poza zasięgiem danych). Kroki i początek zgodne we wszystkich czterech.

### Zakres danych

Odpowiedź zawiera **16 czasów trwania × 27 prawdopodobieństw** dla każdej z tablic `ks`/`sg`/`rb`:
- czasy [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440, 2160, 2880, 4320,
- prawdopodobieństwa [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5, 99.9.

Docstring `fetch_pmaxtp()` (`fetch.py`) i `PMaXTPData` podają nieaktualnie 7 czasów × 6 prawdopodobieństw.

### Propozycje zmian

1. `PMaXTPResult` — dodać pola z bloku `point`: `cell_lat`, `cell_lon`, `ind_x`, `ind_y` (oraz `has_data: bool` na podstawie `error`/pustego `data`); zachować surową odpowiedź (np. `raw: dict`) do archiwizacji po stronie klienta.
2. Stałe siatki i funkcje konwersji: `pmaxtp_cell_for(lat, lon) -> (ind_x, ind_y)`, `pmaxtp_cell_center(ind_x, ind_y) -> (lat, lon)`, `pmaxtp_cells_in_bbox(bbox) -> Iterator[(ind_x, ind_y)]` — pobieranie „jedna komórka = jedno zapytanie o jej środek”.
3. Poprawić dokumentację zakresu (16×27) w docstringach i README.
4. `get_precipitation(duration_minutes, probability_percent: int)` — typ `int` nie pasuje do prawdopodobieństw ułamkowych (0.01, 98.5); klucz budowany przez `str()` wymaga, by float nie był przekazywany jako np. `1.0` (→ `"1.0"`, brak dopasowania). Rozważyć normalizację klucza.
5. Test kontraktowy na zapisanej odpowiedzi (fixture) — weryfikacja kroków i początku siatki.

---

## Komendy

```bash
# Testy (zawsze przez venv projektu)
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=imgwtools

# Linting i formatowanie
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/

# Type checking (config: [tool.pyright] w pyproject.toml)
npx -y pyright src/imgwtools/

# Przewodnik dla agentów (pliki pochodne; po każdej zmianie katalogu, rejestrów albo szablonów)
imgw commands guide --format agents --lang pl --path AGENTS.md
imgw commands guide --format llms --lang pl --path llms.txt
```

---

## Git workflow

- **master** - główna gałąź (stabilna)
- **slave** - gałąź rozwojowa (v2.2.0)
- **feature/versioned-store** - magazyn wersjonowany i spójne interfejsy, wydanie 3.0.0
- **feature/chmi-agents** - dostawca ČHMÚ i wsparcie agentów AI, wydanie 3.0.0

---

**Ostatnia aktualizacja:** 2026-10-19
