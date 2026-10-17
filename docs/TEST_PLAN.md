# Plan przebudowy testów IMGWTools (cel: >= 80% pokrycia)

Stan na: 2026-08-22, gałąź `slave`, v2.2.0, HEAD `c89bb68`.
Środowisko: wyłącznie `.venv/bin/python` (globalny python ma nieaktualny pakiet).
Zainstalowane w `.venv`: pytest 9.0, pytest-cov 7.0, pytest-asyncio 1.3 (`asyncio_mode = "auto"`),
**respx 0.23** (jest w `[dev]`, dotąd nieużywany), fastapi 0.128 + starlette (TestClient), typer 0.21
(CliRunner), pandas 2.3, pydantic-settings 2.12. Wszystkie extras `[api,cli,db,pandas]` są dostępne.

Komendy bazowe:

```
.venv/bin/python -m pytest -q --cov=imgwtools --cov-report=term-missing
.venv/bin/ruff check src/ tests/
npx -y pyright src/imgwtools/
```

---

## 1. Stan wyjściowy

Własny przebieg: **109 testów, 2586 instrukcji, 1994 nieobjętych, 23% TOTAL**. Ruff: czysto.

| Moduł | Stmts | Miss | % | Kluczowe luki (linie z `term-missing`) |
|---|---:|---:|---:|---|
| `__init__.py`, `_version.py`, `exceptions.py`, `parsers.py`, `urls.py` | 21 | 0 | 100 | – |
| `core/url_builder.py` | 105 | 7 | 93 | 150 (`zjaw_` m=13), 158 (brak miesiąca <2023), 170 (brak param), 176/270 (nieznany interwał), 267 (brak miesiąca meteo 2001+), 365 (gałąź HYDRO w `get_available_years` – patrz pułapka 4) |
| `models.py` | 97 | 11 | 89 | 129-149 `to_dataframe`, 300-301 `_safe_int` błędna wartość |
| `db/models.py` | 73 | 9 | 88 | 175-185 `is_missing_value` |
| `db/parsers.py` | 176 | 39 | 78 | 64-65/71 błędne liczby, 204/296/405 krótkie wiersze, 216/308 brak roku/miesiąca, 228-229 zła data, 337-338/474-475 wiersz uszkodzony, 425-429 `H`/`Q` w półrocznych, 508 nieznany interwał ZIP, **543-575 `parse_stations_csv` (0%)** |
| `stations.py` | 138 | 56 | 59 | wszystkie wersje `*_async`, `list_meteo_stations`, gałęzie błędów HTTP |
| `fetch.py` | 223 | 122 | 45 | błędy `HTTPStatusError`/`HTTPError`, `IMGWDataError`, wszystkie `*_async` poza `fetch_pmaxtp_async`, `download_meteo_data_async`, `fetch_warnings` z dict |
| `config.py` | 24 | 24 | 0 | nic nie importuje `settings` w testach |
| `db/__init__.py` | 34 | 31 | 9 | `__getattr__` leniwe importy |
| `db/connection.py`, `db/schema.py`, `db/repository.py`, `db/cache_manager.py` | 376 | 376 | 0 | cała warstwa SQLite |
| `api/main.py`, `api/schemas.py`, `api/routes/*` | 415 | 415 | 0 | całe REST API |
| `cli/main.py`, `cli/fetch.py`, `cli/list_cmd.py`, `cli/admin.py`, `cli/db.py` | 655 | 655 | 0 | całe CLI |
| `web/app.py` | 173 | 173 | 0 | trasy HTMX/Jinja |
| `reference_data.py` | 76 | 76 | 0 | skrypt pobierający dane referencyjne |
| **RAZEM** | **2586** | **1994** | **23** | |

Istniejące pliki: `tests/conftest.py` (fixtury JSON/CSV), `tests/unit/test_{models,fetch,parsers,stations,urls}.py`.
`tests/integration/` pusty. Mockowanie sieci: `unittest.mock.patch("imgwtools.fetch.httpx.Client")` z ręcznie
budowanym `MagicMock` (ok. 10 linii boilerplate na test).

### Rzeczy zweryfikowane w kodzie, które testy MUSZĄ utrwalić (pułapki)

1. **Dryf formatu archiwów** – `db/parsers.py`: `_detect_delimiter` (78-105), `_decode_content` (108-134, BOM > cp1250 > utf-8),
   `_iter_rows` (137-161, zewnętrzne cudzysłowy 2024), kody braków `MISSING_WATER_LEVEL=9999`, `MISSING_FLOW=99999.999`,
   `MISSING_TEMP=99.9` (`db/models.py:103-105`), rok hydrologiczny `HYDRO_TO_CALENDAR_MONTH` (`db/models.py:120-133`,
   miesiące 1-2 = poprzedni rok kalendarzowy, `hydro_to_calendar_date` 136-160), wiodąca spacja w kodzie stacji
   (`row[0].strip().strip('"')`, `db/parsers.py:207`). **Nieobjęte**: `parse_stations_csv` (518-575), ZIP z wieloma
   plikami / bez `.csv` / pusty / uszkodzony (`ZipFile` rzuca `BadZipFile` – nieopakowany w `IMGWDataError`), nieznany interwał (508).
2. **Układ URL meteo** – `core/url_builder.py:75-112` (`_get_meteo_folder`: >2000 rok, opad `1950_1955` gdy <=1955, synop `1960_1965`
   gdy <=1965, siatka `((y-1951)//5)*5+1951`), `build_meteo_url` 235-249 (terminowe opad -> `ValueError`, synop dobowe/terminowe ->
   `ValueError` "per-station", synop <1960), 257-270 (miesięczne = jeden plik na folder; dobowe/terminowe roczne do 2000, miesięczne
   od 2001 z wymaganym `month`), 280 (`month=None` w wyniku dla lat <=2000). Hydro 147-176: `zjaw_{rok}.zip` dla `month=13`
   (każdy rok), `codz_{rok}.zip` od 2023 (miesiąc ignorowany w nazwie, ale echo w `DownloadURL.month`), `codz_{rok}_{mm}.zip` przed 2023
   (brak miesiąca -> `ValueError`), `mies_{rok}.zip`, `polr_{T|Q|H}_{rok}.zip` (brak `param` -> `ValueError`).
3. **Dwie klasy `HydroStation`** – `stations.py:39-70` (pola `station_id`, `name`, `river`; aliasy `station_code`, `station_name`,
   `river_name`; `populate_by_name=True`; `river` wyciągany z `"Odra (1)"` regexem w 320) vs `db/models.py:13-24`
   (`station_code`, `station_name`, `river_name`, bez aliasów). Obie akceptują `station_code=`/`station_name=` w konstruktorze,
   ale atrybut odczytu różni się (`.name` vs `.station_name`).
4. **`get_available_years`** – `core/url_builder.py:344-368`: parametr `interval` nieużywany, obie gałęzie zwracają `(1951, rok_bieżący)`.
   `tests/unit/test_urls.py:238` i `:247` przekazują stringi `"hydro"`/`"meteo"`; `"hydro" == DataType.HYDRO` jest `False`
   (wartość enuma to `"dane_hydrologiczne"`), więc oba testy trafiają w gałąź meteo i linia 365 nigdy nie jest wykonana.
5. **PMAXTP** – `models.py:39-111`: klucze to stringi `"15"`/`"50"`, gettery zwracają `None` dla braków; `fetch.py:42-62`
   granice 49-55 / 14-24.5 (inkluzywne), `IMGWValidationError`; `validate_coords=False` (125-126) omija walidację.
6. **Placeholder w API** – `api/routes/hydro.py:38-45` i `api/routes/meteo.py:33-38` zwracają 2 stacje na sztywno (`# TODO`).
7. **CLI** – `cli/main.py:36-39` `version` czyta `__version__` z `_version.py`; `cli/list_cmd.py:102-107` `datasets` liczy zakres z
   `get_available_years`; teksty `--help` z docstringów (ASCII).
8. **DB** – `db/schema.py` (`UNIQUE(...)` + `INSERT OR IGNORE` w `repository.py:245/347/453`, `schema_version`, `init_db(force)` zwraca
   `False` gdy aktualna), `db/connection.py:52-56` `RuntimeError` gdy `settings.db_enabled` jest `False`, 58-62 `FileNotFoundError`
   przy `readonly=True` bez pliku. `cached_ranges` obsługiwane przez `is_range_cached`/`mark_range_cached` (482-553).
9. **Kodowanie** – `IMGW_ENCODING = "cp1250"` w dwóch miejscach (`stations.py:34`, `db/parsers.py:36`), reeksport w `parsers.py`.
10. **Config** – `config.py`: `env_prefix="IMGW_"`, `data_dir=./data`, `db_path=./data/imgw_hydro.db`, `db_enabled=False`,
    `env_file=".env"` (w repo nie ma `.env`; jest `.env.example`). **Uwaga:** w katalogu roboczym istnieje `data/imgw_hydro.db`
    (nieśledzony) – testy DB muszą zawsze nadpisywać `settings.db_path` na `tmp_path`, inaczej zapiszą do prawdziwej bazy.

### Błędy w kodzie znalezione podczas analizy (NIE naprawiać w ramach tego planu – zgłosić jako follow-up)

- `db/repository.py:616-630` `clear_cache` sumuje `conn.total_changes` (licznik skumulowany od otwarcia połączenia), więc
  zwracana liczba jest zawyżona (sprawdzone: 3 usunięte wiersze -> zwraca 10). Test ma asertować **opróżnienie tabel**, nie wartość.
- `api/routes/hydro.py:69,105` i `meteo.py:134` czytają `nazwa_stacji`, a IMGW API (i `models.py:192`) używa `stacja` ->
  `station_name` w odpowiedzi API jest zawsze `""`. Test pinuje aktualne zachowanie z komentarzem `# TODO: klucz 'stacja'`.
- Zahardkodowane granice lat w API: `schemas.py:97,108` (`le=2024`), `routes/hydro.py:185-186,245-248`, `routes/meteo.py:204-205`,
  `routes/download.py:40-70` (`year_range=(…, 2023)`), `download.py:85,155-156`. Ta sama klasa regresji, co naprawiona w `c89bb68`.
- `api/main.py:35` `API_VERSION = "1.0.0"` (vs `__version__ = "2.2.0"`); `schemas.py:HealthCheck.version` domyślnie `"1.0.0"`.
- `cli/fetch.py:150` dla dobowych <2023 bez `--month` pobiera `range(1, 14)` (13 = zjawiska) – zamierzone, ale nieudokumentowane w `--help`.
- `db/parsers.py:510` `ZipFile` na uszkodzonych bajtach rzuca `zipfile.BadZipFile`, nie `IMGWDataError` (docstring `exceptions.py` obiecuje
  „Corrupted ZIP files”). Test pinuje `BadZipFile`.

---

## 2. Cel i arytmetyka

Cel: **>= 80% TOTAL** z `--cov=imgwtools`. Poniżej realistyczne cele per moduł (kolumna „cel” = liczba instrukcji, które plan pokrywa)
oraz wariant pesymistyczny.

| Moduł | Stmts | Pokryte dziś | Cel (stmts) | Cel % | Uwagi / koszt |
|---|---:|---:|---:|---:|---|
| `__init__`, `_version`, `exceptions`, `parsers`, `urls` | 21 | 21 | 21 | 100 | importy |
| `core/url_builder.py` | 105 | 98 | 105 | 100 | 7 linii = 6 testów błędów |
| `models.py` | 97 | 86 | 97 | 100 | `to_dataframe` (pandas jest), `_safe_int` |
| `db/models.py` | 73 | 64 | 73 | 100 | `is_missing_value`, `hydro_to_calendar_date` |
| `db/parsers.py` | 176 | 137 | 168 | 95 | `parse_stations_csv`, ZIP, wiersze uszkodzone |
| `stations.py` | 138 | 82 | 130 | 94 | respx: sync+async, błędy |
| `fetch.py` | 223 | 101 | 205 | 92 | respx: 12 funkcji, 3 klasy błędów |
| `config.py` | 24 | 0 | 24 | 100 | `monkeypatch.setenv` |
| `db/__init__.py` | 34 | 3 | 34 | 100 | pętla po `__all__` + `AttributeError` |
| `db/connection.py` | 41 | 0 | 39 | 95 | tmp SQLite |
| `db/schema.py` | 48 | 0 | 46 | 96 | |
| `db/repository.py` | 164 | 0 | 150 | 91 | wszystkie 4 gałęzie `is_range_cached` |
| `db/cache_manager.py` | 123 | 0 | 105 | 85 | respx + ZIP builder |
| `api/schemas.py` | 118 | 0 | 118 | 100 | sam import |
| `api/main.py` | 33 | 0 | 28 | 85 | `run_server`/`__main__` poza zakresem |
| `api/routes/download.py` | 61 | 0 | 55 | 90 | |
| `api/routes/hydro.py` | 102 | 0 | 85 | 83 | `/data` z cache = fixture DB + respx |
| `api/routes/meteo.py` | 71 | 0 | 62 | 87 | |
| `api/routes/pmaxtp.py` | 30 | 0 | 27 | 90 | |
| `web/app.py` | 173 | 0 | 150 | 87 | TestClient + respx; szablony renderują się |
| `cli/main.py` | 22 | 0 | 17 | 77 | `server` (uvicorn) i `__main__` poza zakresem |
| `cli/list_cmd.py` | 72 | 0 | 62 | 86 | CSV w `tmp_path` |
| `cli/admin.py` | 96 | 0 | 82 | 85 | `api_keys_file` w `tmp_path` |
| `cli/fetch.py` | 215 | 0 | 170 | 79 | respx także dla `httpx.stream` |
| `cli/db.py` | 250 | 0 | 190 | 76 | najdroższy moduł; `query` z tabelą i `--output` |
| `reference_data.py` | 76 | 0 | 60 | 79 | respx dla CSV/JSON/listingów HTML |
| **RAZEM** | **2586** | **592** | **2303** | **89** | |

**Dowód**: 2303 / 2586 = **89,1%**. Wariant pesymistyczny (CLI `db` 150, CLI `fetch` 140, `web` 120, `reference_data` 40,
`routes/hydro` 70 – łącznie -135): 2168 / 2586 = **83,8%**. Oba warianty powyżej progu, z marginesem na pominięcie
najdroższych ścieżek (np. `cli/db.py query` z tabelą miesięczną).

Jeśli właściciel zgodzi się na wykluczenia z sekcji 6 (bloki `__main__`, `run_server`, `cli server`, `reference_data.main`),
mianownik spada o ok. 20 instrukcji – bez wpływu na decyzję.

---

## 3. Infrastruktura testowa

### 3.1 Strategia mockowania sieci: `respx`

Decyzja: **nowe testy używają `respx`** (fixture `respx_mock` z wtyczki pytest respx – sprawdzone, że jest zarejestrowana).
Uzasadnienie:
- jest już w `[dev]` (`pyproject.toml`), zero nowych zależności;
- mockuje transport httpx, więc działa jednocześnie dla `httpx.Client`, `httpx.AsyncClient` i `httpx.stream`
  (`cli/fetch.py:44`) – parytet sync/async testuje się tym samym routem;
- test to 3 linie zamiast 10 linii `MagicMock` z `__enter__/__exit__`;
- domyślnie `assert_all_mocked=True`: każde nieprzewidziane żądanie sieciowe kończy się błędem -> gwarancja „zero prawdziwej sieci”.

Istniejące 109 testów z `patch("…httpx.Client")` **zostają bez zmian** (działają równolegle z respx). Jedyna poprawka: `test_urls.py:238,247`.

Wzorzec (AAA, jeden test = jedno zachowanie):

```python
def test_fetch_hydro_current_maps_http_500_to_connection_error(respx_mock):
    respx_mock.get(f"{IMGW_API_URL}/hydro").respond(500)

    with pytest.raises(IMGWConnectionError):
        fetch_hydro_current()
```

### 3.2 Nowe fixtury w `tests/conftest.py`

| Fixture | Zakres | Co robi |
|---|---|---|
| `daily_csv_rows` / `monthly_csv_rows` / `semi_annual_csv_rows` | module | stałe z `test_parsers.py` (przenieść do conftest, test_parsers importuje z conftest lub zostawić duplikat 3 stałych – rekomendacja: przenieść, bo potrzebne w testach DB/CLI/API) |
| `make_zip` | function | `make_zip({"codz_2023.csv": bytes}) -> bytes` – builder ZIP w pamięci (`zipfile.ZipFile(io.BytesIO())`) |
| `hydro_daily_zip` | function | `make_zip` z 2-3 wierszami dobowymi 2023 (UTF-8 BOM, `;`), w tym kody braków `9999` i `99.9` |
| `hydro_monthly_zip`, `hydro_semi_annual_zip` | function | analogicznie |
| `tmp_db` | function | `monkeypatch.setattr(settings, "db_enabled", True)`; `monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")`; `monkeypatch.setattr(repository, "_repository", None)` i `cache_manager._cache_manager = None`; zwraca ścieżkę. **Nie** woła `init_db` (testy `schema` chcą pustego pliku) |
| `db_ready` | function | `tmp_db` + `init_db()`; zwraca `HydroRepository()` |
| `tmp_data_dir` | function | `monkeypatch.setattr(settings, "data_dir", tmp_path)` (CLI `list stations`, `reference_data`) |
| `api_client` | module | `fastapi.testclient.TestClient(imgwtools.api.main.app)` – import jest bezpieczny (katalog `web/static` istnieje) |
| `cli` | module | `typer.testing.CliRunner()`; testy wołają `cli.invoke(app, [...])` na `imgwtools.cli.main.app` |
| `hydro_api_url` itd. | – | niepotrzebne; używać stałych `IMGW_API_URL`, `IMGW_PMAXTP_URL`, `HYDRO_STATIONS_CSV_URL`, `HYDRO_MAP_API_URL` z kodu |

`settings` to jeden obiekt (`imgwtools.config.settings`) importowany przez `db/connection.py`, `cli/db.py`, `cli/admin.py`,
`api/routes/hydro.py` (lokalny import) – `monkeypatch.setattr` na instancji działa wszędzie (pydantic nie ma `validate_assignment`).

### 3.3 Markery i konfiguracja

- `pyproject.toml` `[tool.pytest.ini_options]`: dodać `markers = ["integration: testy z prawdziwa siecia IMGW (domyslnie pominiete)"]`
  i `addopts = "-m 'not integration'"`. Integracje uruchamia się jawnie `-m integration`. **Rekomendacja: nie dodawać żadnych testów
  integracyjnych w tym planie** (katalog `tests/integration/` zostaje pusty z `__init__.py`) – serwer IMGW jest niestabilny, a wszystkie
  pułapki formatu są odtworzone w fixturach.
- Krok końcowy (sekcja 5, faza 6): `--cov-fail-under=80` w `addopts`.
- Opcjonalnie (decyzja właściciela, sekcja 6): `[tool.coverage.report] exclude_also = ["if __name__ == .__main__.:", "if TYPE_CHECKING:"]`.

### 3.4 Zasady pisania

- Nazwy `test_<funkcja>_<scenariusz>` jak w `DEVELOPMENT_STANDARDS.md` 5.2; bez klas testowych w nowych plikach (płaskie funkcje, jak w `test_parsers.py`).
- Ruff `E/W/F/I/B/UP/C4` obowiązuje w `tests/**` (wyłączone tylko `D`) – sortowanie importów, brak nieużywanych importów.
- ASCII w źródłach; polskie znaki w testach tylko w fixturach kodowania (jak dziś `Ławica`).
- Brak `time.sleep`, brak prawdziwych plików poza `tmp_path`, brak globalnego stanu bez `monkeypatch`.

---

## 4. Plan per moduł

Format: `test_nazwa` – co asertuje [pułapka/klasa błędu] (fixture).

### 4.1 `tests/unit/test_urls.py` – POPRAWKA istniejących testów

- `test_hydro_daily_years` (linia 238): zamienić `"hydro"` na `DataType.HYDRO` (+ import). Powód: string nigdy nie jest równy
  enumowi, test przechodził przez gałąź meteo – fałszywie zielony. [pułapka 4]
- `test_meteo_years` (247): `"meteo"` -> `DataType.METEO`.

### 4.2 `tests/unit/test_url_builder.py` (nowy; domyka 7 linii + pinuje granice)

- `test_build_hydro_url_daily_before_2023_without_month_raises` – `ValueError` "Month is required" (158). [boundary 2022]
- `test_build_hydro_url_daily_2022_december_filename` – `codz_2022_12.zip`. [boundary miesiąc 12]
- `test_build_hydro_url_daily_2023_ignores_month_in_filename_but_echoes_it` – `codz_2023.zip`, `result.month == 6`. [boundary 2023]
- `test_build_hydro_url_phenomena_month_13_any_year` – `zjaw_2024.zip` dla `month=13` także >= 2023 (150).
- `test_build_hydro_url_semi_annual_without_param_raises` – (170).
- `test_build_hydro_url_unknown_interval_raises` – przekazać `MeteoInterval.HOURLY` (176; str-enum inna wartość).
- `test_build_meteo_url_daily_2001_without_month_raises` – (267). [boundary 2001]
- `test_build_meteo_url_daily_2000_is_yearly_file_and_month_is_none` – `2000_k.zip`, folder `1996_2000`, `result.month is None` nawet gdy podano `month=5` (280). [boundary 2000]
- `test_build_meteo_url_unknown_interval_raises` – przekazać `HydroInterval.SEMI_ANNUAL` (270).
- `test_get_meteo_folder_grid` – `pytest.mark.parametrize`: (1951,k)->`1951_1955`, (1955,k)->`1951_1955`, (1956,k)->`1956_1960`,
  (1950,o)->`1950_1955`, (1956,o)->`1956_1960`, (1965,s)->`1960_1965`, (1966,s)->`1966_1970`, (2000,k)->`1996_2000`, (2001,k)->`2001`. [pułapka 2]
- `test_build_meteo_url_hourly_klimat_2000_yearly` – terminowe klimat 2000 -> `2000_k.zip` (gałąź `year <= 2000` dla HOURLY).
- `test_get_available_years_hydro_starts_1951_and_ends_current_year` – `DataType.HYDRO` (365). [pułapka 4]
- `test_get_available_years_ignores_interval_argument_current_behaviour` – wynik identyczny dla `"dobowe"`, `"terminowe"`, `""`;
  komentarz, że to pinowanie stanu, nie specyfikacja. [pułapka 4]
- `test_get_available_years_meteo_returns_1951_current_behaviour` – pin.
- `test_build_pmaxtp_url_method_letter` – `P`/`A` w ścieżce (już jest w test_urls – pominąć, jeśli duplikat).

### 4.3 `tests/unit/test_models.py` (uzupełnienie)

- `test_pmaxtp_to_dataframe_columns_and_rows` – kolumny `duration, probability, ks_mm, sg_mm, rb_mm`, `sg_mm` `None` gdy brak w `sg` (129-149) (`pmaxtp_api_response`).
- `test_pmaxtp_to_dataframe_empty_data` – pusty DataFrame.
- `test_safe_int_invalid_string_returns_none` – `_safe_int("abc")` (300-301).
- `test_safe_float_none_and_invalid` – `None`, `"n/a"`.
- `test_pmaxtp_keys_are_plain_strings_without_prefix` – `"15" in data.ks`, `"t15" not in data.ks`. [pułapka 5]

### 4.4 `tests/unit/test_db_models.py` (nowy)

- `test_hydro_to_calendar_date_month_1_is_november_previous_year` – (2023,1,1) -> 2022-11-01. [pułapka 1, boundary]
- `test_hydro_to_calendar_date_month_2_is_december_previous_year`.
- `test_hydro_to_calendar_date_month_3_is_january_same_year`.
- `test_hydro_to_calendar_date_month_12_is_october`.
- `test_hydro_to_calendar_date_invalid_month_raises_keyerror` – 13.
- `test_hydro_to_calendar_date_invalid_day_raises_valueerror` – 30 lutego.
- `test_is_missing_value_level_flow_temp_and_none` – parametrize: (9999,"level")->True, (99999.999,"flow")->True, (99.9,"temp")->True,
  (None,"x")->True, (12.5,"level")->False, (1.0,"other")->False (175-185). [kody braków]
- `test_db_hydro_station_uses_station_name_attribute` – `db.models.HydroStation(...).station_name`; brak `.name` (`AttributeError`). [pułapka 3]
- `test_daily_record_rejects_hydro_month_13` – `ValidationError`.

### 4.5 `tests/unit/test_stations.py` (uzupełnienie; nowe testy z respx)

- `test_public_hydro_station_exposes_name_and_aliases` – `HydroStation(station_code=…, station_name=…)` -> `.name`, `.station_id`;
  `HydroStation(station_id=…, name=…)` też działa (`populate_by_name`). [pułapka 3]
- `test_parse_hydro_stations_csv_strips_leading_space_in_quoted_code` – `'" 123456789","X","Odra (1)"'` -> `"123456789"`. [pułapka 1]
- `test_parse_hydro_stations_csv_river_without_suffix_kept_verbatim`.
- `test_list_hydro_stations_decodes_cp1250` (respx: `HYDRO_STATIONS_CSV_URL`, content `"…Ławica (1)".encode("cp1250")`) -> `river == "Ławica"`. [pułapka 9]
- `test_list_hydro_stations_http_404_raises_connection_error` (respx `.respond(404)`). [mapowanie wyjątków]
- `test_list_hydro_stations_async_equals_sync` (respx; `await`). [parytet]
- `test_list_meteo_stations_parses_rows` + `test_list_meteo_stations_async_equals_sync`.
- `test_list_meteo_stations_timeout_raises_connection_error` (`side_effect=httpx.ConnectTimeout`).
- `test_get_hydro_stations_with_coords_sends_only_main_stations_param` – `include_all=False` -> `onlyMainStations=true` w `respx_mock.calls.last.request.url`.
- `test_get_hydro_stations_with_coords_async_equals_sync`.
- `test_get_hydro_stations_with_coords_http_error_raises_connection_error`.
- `test_parse_map_stations_response_skips_malformed_item` – element bez `id` typu `None` w liście (gałąź `except` 387).

### 4.6 `tests/unit/test_fetch.py` (uzupełnienie; respx)

- `test_fetch_pmaxtp_boundary_coordinates_are_valid` – parametrize 4 rogi: (49.0,14.0), (55.0,24.5), (49.0,24.5), (55.0,14.0) – nie rzuca (respx 200). [boundary]
- `test_fetch_pmaxtp_just_outside_bounds_raises` – 48.999 / 55.001 / 13.999 / 24.501.
- `test_fetch_pmaxtp_validate_coords_false_bypasses_check` – (0,0) z respx 200 -> wynik. [pułapka 5]
- `test_fetch_pmaxtp_http_500_raises_connection_error_with_status` – komunikat zawiera `500` (138-141).
- `test_fetch_pmaxtp_connect_error_raises_connection_error` – `side_effect=httpx.ConnectError` (142-143).
- `test_fetch_pmaxtp_invalid_json_raises_data_error` – `respond(content=b"<html>")` -> `json()` rzuca -> **uwaga**: `response.json()` jest w bloku
  `try` z `httpx`-owymi wyjątkami, `json.JSONDecodeError` nie jest `httpx.HTTPError`, więc wyleci surowy `JSONDecodeError`, nie `IMGWDataError`.
  Test pinuje aktualne zachowanie (`pytest.raises(ValueError)`) z komentarzem – kandydat na follow-up. [mapowanie wyjątków]
- `test_fetch_pmaxtp_bad_structure_raises_data_error` – `respond(json={"data": {"ks": "not-a-dict"}})` -> `IMGWDataError` (152-153).
- `test_fetch_pmaxtp_async_equals_sync` – ten sam route, porównanie `model_dump()`. [parytet]
- `test_fetch_pmaxtp_async_http_error_raises_connection_error`.
- `test_fetch_hydro_current_http_error_raises_connection_error`, `test_fetch_hydro_current_bad_item_raises_data_error`
  (`respond(json=[None])`), `test_fetch_hydro_current_async_equals_sync`.
- `test_fetch_synop_async_filters_by_name`, `test_fetch_synop_http_error_raises_connection_error`, `test_fetch_synop_bad_item_raises_data_error`.
- `test_fetch_warnings_single_dict_is_wrapped`, `test_fetch_warnings_none_response_returns_empty`, `test_fetch_warnings_async_equals_sync`,
  `test_fetch_warnings_http_error_raises_connection_error`.
- `test_download_hydro_data_builds_url_from_params` – `respx_mock.get(url).respond(content=b"PK")`; asercja na wywołanym URL (`codz_2022_06.zip`).
- `test_download_hydro_data_http_404_raises_connection_error_with_url` – komunikat zawiera URL (553-556).
- `test_download_hydro_data_timeout_raises_connection_error`, `test_download_hydro_data_async_equals_sync`.
- `test_download_hydro_data_invalid_interval_raises_value_error` – `"tygodniowe"` -> `ValueError` z `HydroInterval(...)`.
- `test_download_meteo_data_hourly_opad_raises_value_error` – przekazuje `ValueError` z buildera (nie `IMGWConnectionError`).
- `test_download_meteo_data_http_404_raises_connection_error`, `test_download_meteo_data_async_equals_sync`.

### 4.7 `tests/unit/test_parsers.py` (uzupełnienie)

- `test_parse_stations_csv_bytes_cp1250_and_river_suffix` – bajty cp1250, `"Ławica (1)"` -> `river_name == "Ławica"` (543-575). [pułapka 1, 9]
- `test_parse_stations_csv_river_without_suffix_kept`, `test_parse_stations_csv_skips_short_rows`, `test_parse_stations_csv_str_input`.
- `test_parse_zip_file_unknown_interval_raises_value_error` (508).
- `test_parse_zip_file_reads_only_csv_members` – ZIP z `readme.txt` + `codz.csv` (`make_zip`).
- `test_parse_zip_file_multiple_csv_members_concatenated`.
- `test_parse_zip_file_empty_archive_yields_nothing`.
- `test_parse_zip_file_corrupt_bytes_raises_badzipfile` – pin `zipfile.BadZipFile` (patrz lista błędów).
- `test_parse_daily_csv_missing_codes_become_none` – wiersz z `9999`, `99999.999`, `99.9` -> trzy `None`. [kody braków]
- `test_parse_daily_csv_skips_rows_with_fewer_than_9_columns` (204), `test_parse_daily_csv_skips_row_without_year` (216),
  `test_parse_daily_csv_invalid_date_sets_measurement_date_none` – dzień 31 w miesiącu hydrologicznym 4 (luty) (228-229).
- `test_parse_daily_csv_hydro_month_1_maps_to_november_previous_year` – `measurement_date == "2022-11-01"` dla (2023,1,1). [pułapka 1]
- `test_parse_monthly_csv_unknown_extremum_defaults_to_mean` (310), `test_parse_monthly_csv_skips_short_rows` (296).
- `test_parse_semi_annual_csv_h_uses_level_missing_code` i `_q_uses_flow_missing_code` (425-427).
- `test_parse_semi_annual_csv_mean_has_no_dates` – 8 kolumn -> `extremum_start_date is None`.
- `test_parse_semi_annual_csv_unknown_period_defaults_to_annual`.
- `test_safe_float_non_numeric_returns_none`, `test_safe_int_non_numeric_returns_none` (64-65, 71).

### 4.8 `tests/unit/test_config.py` (nowy)

- `test_settings_defaults` – `db_enabled False`, `db_path == Path("data/imgw_hydro.db")`, `data_dir == Path("data")`, `port 8000`, `env development`. [pułapka 10]
- `test_settings_reads_imgw_prefixed_env` – `monkeypatch.setenv("IMGW_DB_ENABLED","true")`, `IMGW_DB_PATH`, `IMGW_PORT` -> nowa instancja `Settings()`.
- `test_settings_ignores_unprefixed_env` – `DB_ENABLED=true` nie wpływa.
- `test_settings_station_file_paths_follow_data_dir` – `hydro_stations_file`, `meteo_stations_file`.
- `test_settings_is_production` – `IMGW_ENV=production`.
- `test_settings_invalid_log_level_raises` – `ValidationError`.

### 4.9 `tests/unit/test_db_connection.py` (nowy)

- `test_get_db_connection_raises_when_disabled` – `settings.db_enabled=False` -> `RuntimeError` z tekstem `IMGW_DB_ENABLED`. [pułapka 8]
- `test_get_db_connection_readonly_missing_file_raises_file_not_found` (`tmp_db`).
- `test_get_db_connection_creates_parent_directory` – `db_path = tmp_path/"sub"/"x.db"`.
- `test_get_db_connection_sets_row_factory_and_foreign_keys` – `PRAGMA foreign_keys` == 1, `conn.row_factory is sqlite3.Row`.
- `test_get_db_connection_write_uses_wal` – `PRAGMA journal_mode` == `wal`.
- `test_get_transaction_commits_on_success`, `test_get_transaction_rolls_back_on_exception`.
- `test_db_exists_false_then_true`.

### 4.10 `tests/unit/test_db_schema.py` (nowy)

- `test_init_db_creates_tables_and_version_1` – `get_schema_version() == CURRENT_VERSION`, tabele w `sqlite_master`. [pułapka 8]
- `test_init_db_second_call_returns_false` – idempotencja.
- `test_init_db_force_drops_data` – wstaw stację, `init_db(force=True)`, `get_table_counts()["hydro_stations"] == 0`.
- `test_get_schema_version_without_file_returns_0`, `test_get_schema_version_without_table_returns_0` (pusty plik sqlite).
- `test_get_table_counts_all_five_tables`, `test_get_cached_years_groups_by_interval` (`mark_range_cached` x3, nieznany interwał pomijany).

### 4.11 `tests/unit/test_db_repository.py` (nowy; fixture `db_ready`)

- `test_upsert_station_insert_then_update_keeps_coords_when_new_is_null` – `COALESCE` (114-117).
- `test_get_stations_search_matches_name_or_river`, `test_get_stations_limit_offset`, `test_get_station_missing_returns_none`.
- `test_insert_daily_batch_ignores_duplicates` – dwa razy ten sam wsad -> count w tabeli bez zmian; drugi zwrot `0`. [idempotencja, UNIQUE]
- `test_insert_daily_batch_empty_returns_0` (+ monthly, semi_annual – parametrize po metodzie).
- `test_get_daily_data_filters_station_years_and_dates` – `start_date`/`end_date`.
- `test_get_daily_data_joins_station_name` – `station_name` z `hydro_stations`, `None` gdy brak stacji (LEFT JOIN).
- `test_get_monthly_data_filters_extremum`, `test_get_semi_annual_data_filters_param_and_period`.
- `test_insert_semi_annual_batch_collapses_plateau_duplicates` – 3 rekordy o tym samym `(station, year, period, param, extremum)` -> 1 wiersz
  (dokumentowane w `parsers.py:391-394`).
- `test_is_range_cached_four_key_shapes` – parametrize: (month None, param None), (month 5), (param "Q"), (month 5, param "Q"). [cached_ranges]
- `test_mark_range_cached_replaces_existing` – `INSERT OR REPLACE`, `record_count` nadpisany.
- `test_get_cached_ranges_filter_by_interval_and_order`.
- `test_clear_cache_by_interval_empties_only_that_table_and_ranges`, `test_clear_cache_all_empties_everything` – asercje na `get_table_counts()`,
  **nie** na zwracanej liczbie (błąd w `total_changes`, patrz sekcja 1).
- `test_get_repository_is_singleton`.

### 4.12 `tests/unit/test_db_cache_manager.py` (nowy; `db_ready` + respx + `make_zip`)

- `test_ensure_data_cached_downloads_parses_and_marks_range` – respx na `…/dobowe/2023/codz_2023.zip` -> `True`; `hydro_daily == 2`,
  `cached_ranges == 1`, `source_file == "codz_2023.zip"`. [lazy loading]
- `test_ensure_data_cached_second_call_is_noop` – `False`, `respx_mock.calls.call_count == 1`. [idempotencja]
- `test_ensure_data_cached_unknown_interval_raises`.
- `test_ensure_data_cached_before_2023_uses_monthly_url` – `codz_2022_06.zip` wywołany. [boundary]
- `test_ensure_data_cached_http_404_propagates_httpx_error` – `httpx.HTTPStatusError` (docstring obiecuje httpx, nie IMGW*). [mapowanie]
- `test_ensure_data_cached_reports_progress_three_times` – lista wywołań callbacka.
- `test_import_zip_data_is_idempotent` – powtórny import zwraca 0, tabela bez zmian.
- `test_import_zip_data_semi_annual_and_monthly_go_to_right_tables` (parametrize 2 zipy).
- `test_cache_year_range_daily_pre_2023_iterates_12_months` – respx z wildcardem `codz_2022_*.zip`; wynik `{2022: n}`; błędy miesięcy pomijane (`except Exception: continue`).
- `test_cache_year_range_single_file_per_year_and_already_cached_gives_0`.
- `test_cache_year_range_failed_year_gives_0` – respx 500.
- `test_refresh_stations_upserts_from_csv` – respx na `HYDRO_STATIONS_CSV_URL` (cp1250) -> `count`, `get_station("123456789").river_name == "Ławica"`. [pułapka 9]
- `test_get_daily_monthly_semi_annual_data_delegate_to_repo` – po imporcie, bez sieci.
- `test_get_cache_manager_is_singleton`.

### 4.13 `tests/unit/test_db_init.py` (nowy, mały)

- `test_db_lazy_attributes_resolve` – `for name in imgwtools.db.__all__: getattr(imgwtools.db, name)` jest callable/klasą (45-85).
- `test_db_unknown_attribute_raises_attribute_error`.

### 4.14 `tests/unit/test_api_system.py` (nowy; `api_client`)

- `test_health_returns_ok` – 200, `{"status":"ok","version":API_VERSION}`.
- `test_api_info_lists_four_endpoints`.
- `test_openapi_schema_builds` – `GET /openapi.json` 200 (łapie błędy `response_model`/Pydantic dla wszystkich tras naraz – tani i mocny).

### 4.15 `tests/unit/test_api_hydro.py`

- `test_list_hydro_stations_shape` – 200, `count == len(stations)`, każdy element ma `id/name/river`; **bez asercji na nazwy**;
  komentarz `# Placeholder (TODO w routes/hydro.py:38) - test pinuje schemat, nie dane`. [pułapka 6]
- `test_list_hydro_stations_offset_beyond_count_gives_empty_list_and_total_count`.
- `test_list_hydro_stations_rejects_limit_0` – 422.
- `test_get_hydro_station_404_when_imgw_returns_empty` (respx `[]`), `test_get_hydro_station_502_on_http_error`,
  `test_get_hydro_station_maps_fields` (`rzeka`, `lat`, `lon`).
- `test_current_hydro_maps_fields_and_wraps_dict` (respx dict) – **pin** `station_name == ""` z komentarzem o `nazwa_stacji`/`stacja`.
- `test_current_hydro_empty_list`, `test_current_hydro_502_on_connection_error`.
- `test_download_url_daily_2023`, `test_download_url_daily_2022_without_month_400`, `test_download_url_semi_annual_without_param_400`,
  `test_download_url_year_2025_rejected_422` – pin `le=2024` (+ komentarz follow-up).
- `test_download_urls_daily_2022_2023_counts_13` – 12 + 1. [boundary 2022/2023]
- `test_download_urls_start_gt_end_400`, `test_download_urls_semi_annual_with_param`.
- `test_hydro_data_400_when_cache_disabled` (`settings.db_enabled=False`).
- `test_hydro_data_invalid_interval_400`, `test_hydro_data_start_gt_end_400`.
- `test_hydro_data_daily_from_cache` – `tmp_db` + respx `codz_2023.zip` -> 200, `source == "cache"`, `count == 2`, `station_name` z CSV. [lazy loading end-to-end]
- `test_hydro_data_monthly_from_cache` – respx `mies_2023.zip`.
- `test_hydro_data_500_when_download_fails` – respx 500 -> `HTTPException 500` ("Error fetching data").

### 4.16 `tests/unit/test_api_meteo.py`

- `test_list_meteo_stations_shape_not_names` [pułapka 6], `test_synop_maps_fields_and_filters_none_values` (respx; `stacja` działa tutaj),
  `test_synop_empty_response`, `test_synop_502_on_error`, `test_current_meteo_maps_fields`, `test_current_meteo_502_on_error`.
- `test_download_url_monthly_synop_2023`, `test_download_url_hourly_opad_400`, `test_download_url_daily_synop_400_per_station`,
  `test_download_url_year_2000_rejected_422` (pin `ge=2001`).
- `test_download_urls_daily_klimat_two_years_gives_24`, `test_download_urls_skips_invalid_combo_returns_0` (terminowe/opad), `test_download_urls_start_gt_end_400`.

### 4.17 `tests/unit/test_api_download.py`

- `test_datasets_lists_six_with_year_ranges` – 6 pozycji, `year_range` to para int (pin `(…,2023)` z komentarzem follow-up).
- `test_url_hydro_daily`, `test_url_meteo_requires_subtype_400`, `test_url_meteo_monthly_opad_1975_folder_1971_1975`, `test_url_invalid_interval_400`
  (`HydroInterval("x")` -> `ValueError` -> 400), `test_url_hydro_semi_annual_param_T`.
- `test_urls_hydro_daily_2022_2023_counts_13`, `test_urls_meteo_daily_2000_2001_counts_13` (1 roczny + 12) [boundary 2000/2001],
  `test_urls_meteo_without_subtype_raises_400` – **uwaga**: `HTTPException` rzucony w `try … except ValueError` przechodzi (nie jest `ValueError`), 400.
- `test_urls_year_out_of_range_400` – `start_year=1951`, `end_year=2024` ok; `DataType` liczony przez `get_available_years` – skoro zwraca bieżący rok,
  a `le=2024`, walidator 400 nie jest osiągalny dla `end_year`; osiągalny dla `start_year < 1951`? `ge=1951` też blokuje -> gałąź 158-162 **nieosiągalna**.
  Nie testować; odnotować w sekcji 6.

### 4.18 `tests/unit/test_api_pmaxtp.py`

- `test_methods_lists_pot_and_amp`, `test_url_returns_pmaxtp_url_with_4_decimals`, `test_url_latitude_outside_poland_422` (schemat `ge/le`),
  `test_data_proxies_imgw_json` (respx), `test_data_504_on_timeout`, `test_data_passes_through_imgw_status_code` (respx 403 -> 403), `test_data_502_on_connect_error`.

### 4.19 `tests/unit/test_web.py` (`api_client`; trasy Jinja)

- `test_static_pages_render_200` – parametrize `/`, `/download`, `/download/hydro`, `/download/meteo`, `/download/pmaxtp`, `/stations`, `/map`;
  `text/html`, `title` w treści.
- `test_generate_hydro_urls_daily_2022_2023_13_links` (form POST), `test_generate_hydro_urls_semi_annual_without_param_gives_3_per_year`,
  `test_generate_hydro_urls_invalid_interval_shows_error`, `test_generate_hydro_urls_daily_2022_without_month_ok` (miesiące generowane w pętli).
- `test_generate_meteo_urls_monthly_1996_2000_deduplicates_to_one_link` – 5 lat -> 1 URL (253-261). [pułapka 2]
- `test_generate_meteo_urls_hourly_opad_reports_error_per_year`, `test_generate_meteo_urls_invalid_subtype_error`.
- `test_generate_pmaxtp_renders_result` (respx), `test_generate_pmaxtp_http_error_renders_error_partial`, `test_generate_pmaxtp_invalid_method_error`.
- `test_hydro_stations_partial_search_and_limit` (respx cp1250), `test_hydro_stations_partial_error_on_http_failure`,
  `test_meteo_stations_partial_search`, `test_meteo_stations_partial_error`.
- `test_map_stations_filters_missing_coords_and_builds_summary` (respx JSON), `test_map_stations_error_returns_empty_list_with_error`.

### 4.20 `tests/unit/test_cli_main.py` (`cli`)

- `test_all_help_screens_exit_0` – parametrize: `--help`, `version --help`, `server --help`, `fetch --help`, `fetch hydro --help`, `fetch meteo --help`,
  `fetch current --help`, `fetch pmaxtp --help`, `fetch warnings --help`, `list --help`, `list stations --help`, `list datasets --help`, `list intervals --help`,
  `admin --help`, `admin keys/create/revoke/delete/stats --help`, `db --help`, `db init/status/cache/clear/vacuum/stations/query --help`. [pułapka 7; Typer wiring]
- `test_version_prints_package_version` – `__version__` w output, nie `1.0.0`. [regresja]
- `test_server_command_delegates_to_uvicorn` – `monkeypatch.setattr("uvicorn.run", fake)`; asercja argumentów (host/port/reload). Pokrywa linie bez startu serwera.

### 4.21 `tests/unit/test_cli_list.py`

- `test_list_datasets_uses_current_year` – output zawiera `f"1951-{datetime.now().year}"`. [pułapka 7]
- `test_list_datasets_filter_hydro_hides_meteo`, `test_list_intervals_prints_sections`.
- `test_list_stations_hydro_reads_csv_from_data_dir` (`tmp_data_dir` + zapis `hydro_stations_names.csv` z nagłówkiem `id,name,river`),
  `test_list_stations_search_filters`, `test_list_stations_meteo_two_columns`, `test_list_stations_missing_file_exit_1`,
  `test_list_stations_invalid_type_exit_1`, `test_list_stations_unreadable_file_exit_1` (plik binarny).

### 4.22 `tests/unit/test_cli_admin.py` (`monkeypatch.setattr(settings, "api_keys_file", tmp_path/"keys.json")`)

- `test_keys_empty_message`, `test_create_writes_key_file_and_prints_key`, `test_keys_lists_created_key_truncated_id`,
  `test_revoke_by_prefix_sets_inactive`, `test_revoke_unknown_exit_1`, `test_delete_force_removes`, `test_delete_without_force_abort_on_n` (`input="n\n"`, exit 1),
  `test_delete_confirm_y_removes`, `test_delete_unknown_exit_1`, `test_stats_all_and_filtered`, `test_stats_empty_message`.

### 4.23 `tests/unit/test_cli_fetch.py` (`cli` + respx + `tmp_path`)

- `test_fetch_hydro_daily_2023_downloads_one_file` – respx `codz_2023.zip` -> plik w `tmp_path`, „Pobrano: 1”.
- `test_fetch_hydro_daily_2022_month_6_single_file`, `test_fetch_hydro_daily_2022_without_month_downloads_13_files` (wildcard respx; 12 + `zjaw_2022.zip`).
- `test_fetch_hydro_year_range_semi_annual_without_param_downloads_3_per_year` – `--year 2020-2021 --interval polroczne_i_roczne` -> 6.
- `test_fetch_hydro_skips_existing_file` – plik istnieje -> „pomijam”, 0 pobrań. [idempotencja]
- `test_fetch_hydro_http_404_counts_as_not_downloaded` (respx 404; `download_file` zwraca False, exit 0).
- `test_fetch_hydro_invalid_interval_exit_1`.
- `test_fetch_meteo_monthly_synop_2023`, `test_fetch_meteo_daily_klimat_2000_yearly_file` [boundary], `test_fetch_meteo_hourly_opad_counts_failure`,
  `test_fetch_meteo_invalid_subtype_exit_1`.
- `test_fetch_current_hydro_prints_json` (respx), `test_fetch_current_output_file_written_utf8` (JSON z `ł`), `test_fetch_current_invalid_type_exit_1`,
  `test_fetch_current_http_error_exit_1`.
- `test_fetch_pmaxtp_writes_output`, `test_fetch_pmaxtp_invalid_method_exit_1`, `test_fetch_pmaxtp_http_error_exit_1`
  (uwaga: CLI nie waliduje granic Polski – pin w komentarzu).
- `test_fetch_warnings_meteo_prints`, `test_fetch_warnings_invalid_type_exit_1`, `test_fetch_warnings_http_error_exit_1`.

### 4.24 `tests/unit/test_cli_db.py` (`cli` + `tmp_db` + respx)

- `test_db_commands_exit_1_when_disabled` – parametrize `init/status/cache/clear/vacuum/stations/query` z minimalnymi argami; komunikat `IMGW_DB_ENABLED`. [pułapka 8]
- `test_db_init_creates_file`, `test_db_init_second_run_says_exists`, `test_db_init_force_recreates`.
- `test_db_status_without_file_hint`, `test_db_status_empty_db_shows_zero_counts`, `test_db_status_after_cache_lists_years`.
- `test_format_year_ranges` – parametrize `[2015,2016,2017,2020,2022,2023]` -> `"2015-2017, 2020, 2022-2023"`, `[]` -> `""`, `[2020]` -> `"2020"`.
- `test_db_cache_daily_2023_prints_summary` (respx), `test_db_cache_start_gt_end_exit_1`, `test_db_cache_invalid_interval_exit_1`,
  `test_db_cache_polroczne_without_param_exit_1`, `test_db_cache_invalid_param_exit_1`, `test_db_cache_initializes_db_if_missing`.
- `test_db_clear_force_all`, `test_db_clear_invalid_interval_exit_1`, `test_db_clear_without_force_prompt_n_cancels`, `test_db_clear_without_file_message`.
- `test_db_vacuum_runs`, `test_db_vacuum_without_file_message`.
- `test_db_stations_empty_hint`, `test_db_stations_refresh_then_lists` (respx CSV), `test_db_stations_search_no_match_message`.
- `test_db_query_daily_prints_table` (respx), `test_db_query_output_csv_written`, `test_db_query_no_data_message`, `test_db_query_monthly_table`.

### 4.25 `tests/unit/test_reference_data.py` (respx + `tmp_data_dir`)

- `test_fetch_stations_writes_three_csv_files` – respx: `HYDRO_STATIONS_CSV_URL`, `METEO_STATIONS_CSV_URL`, `HYDRO_MAP_API_URL`; nagłówki `id,name,river` / `id,name` / `id,X,Y`;
  stacja bez współrzędnych pominięta w `locations`.
- `test_meteo_format_files_parses_listing_and_dedupes` – respx `respond(text='<a href="k_d_format.txt">…')` dla 9 kombinacji, 404 dla `terminowe/opad`.
- `test_fetch_descriptions_writes_files_and_skips_404`.
- `test_main_returns_1_on_connection_error` (respx `side_effect=httpx.ConnectError`) i `test_main_returns_0_happy_path` (`capsys` – „Done.”).

### Podsumowanie liczby testów

Orientacyjnie ~230 nowych testów (razem ~340). Przy obecnym czasie 0,3 s/109 testów i sqlite w `tmp_path` spodziewany czas < 10 s.

---

## 5. Kolejność wdrożenia (fazy = osobne commity, każdy zielony)

| Faza | Zakres | Commit (temat) | Oczekiwane pokrycie po fazie |
|---|---|---|---|
| 0 | Poprawka `test_urls.py:238,247`; fixtury w `conftest.py` (`make_zip`, `tmp_db`, `db_ready`, `tmp_data_dir`, `api_client`, `cli`); markery w `pyproject.toml` | `test: poprawka testow get_available_years i wspolne fixtury (respx, sqlite, TestClient, CliRunner)` | 23% (+1 linia) |
| 1 | `test_url_builder.py`, uzupełnienia `test_models.py`, `test_db_models.py`, `test_parsers.py`, `test_stations.py`, `test_fetch.py`, `test_config.py` | `test: pelne pokrycie url_builder, modeli, parserow, stacji i fetch przez respx` | ~32% (592+239=831/2586) |
| 2 | `test_db_connection.py`, `test_db_schema.py`, `test_db_repository.py`, `test_db_cache_manager.py`, `test_db_init.py` | `test: warstwa db na tymczasowym SQLite z mockowanym pobieraniem` | ~46% (1202/2586) |
| 3 | `test_api_system.py`, `test_api_hydro.py`, `test_api_meteo.py`, `test_api_download.py`, `test_api_pmaxtp.py` | `test: endpointy REST API przez TestClient bez sieci` | ~61% (1577/2586) |
| 4 | `test_web.py` | `test: trasy web HTMX/Jinja renderuja sie z mockowanymi danymi` | ~67% (1727/2586) |
| 5 | `test_cli_main.py`, `test_cli_list.py`, `test_cli_admin.py`, `test_cli_fetch.py`, `test_cli_db.py` | `test: CLI przez CliRunner - help, kody wyjscia, fetch, admin, db` | ~87% (2248/2586) |
| 6 | `test_reference_data.py`; `--cov-fail-under=80` w `addopts`; aktualizacja liczb w `README.md` i `docs/DEVELOPMENT_STANDARDS.md` (5.1, 5.4, 10) | `test: reference_data z mockami oraz prog pokrycia 80 procent` | ~89% (2308/2586) |

Każda faza: `pytest -q --cov…` zielone, `ruff check src/ tests/` czyste, `pyright src/imgwtools/` bez zmian (testy nie są sprawdzane pyrightem).
Fazy 3 i 5 są największe – można je podzielić na dwa commity (hydro+system / meteo+download+pmaxtp; main+list+admin / fetch+db), jeśli przegląd ma być wygodniejszy.

---

## 6. Ryzyka i decyzje do potwierdzenia przez właściciela

1. **respx jako standard nowych testów** (jest w `[dev]`, nie dotykamy 109 istniejących testów z `MagicMock`). Alternatywa: `httpx.MockTransport` –
   wymagałaby wstrzykiwania transportu do `httpx.Client(...)` w kodzie produkcyjnym, czego nie chcemy. **Rekomendacja: respx.**
2. **`get_available_years`** – plan pinuje obecne zachowanie (ignorowany `interval`, 1951 dla meteo) w testach o jawnych nazwach `*_current_behaviour`.
   Follow-up (osobny `fix:`): usunąć parametr `interval` lub go użyć (np. synop od 1960), ewentualnie przyjąć też `"hydro"/"meteo"` jako string.
   Do decyzji: pin vs. naprawa przed testami.
3. **Placeholder `/stations`** (pułapka 6) – testy asertują kształt (`StationList`, `count`, `limit/offset`), nie nazwy. Follow-up: czytać z `settings.hydro_stations_file`
   jak `imgw list stations`.
4. **Błędy znalezione** (sekcja 1: `clear_cache` licznik, `nazwa_stacji` vs `stacja`, `le=2024`/`(…,2023)` w API, `API_VERSION 1.0.0`, `BadZipFile` zamiast
   `IMGWDataError`, `JSONDecodeError` w `fetch_*`) – plan **pinuje** aktualne zachowanie z komentarzem `# TODO`, żeby naprawa była świadomą zmianą testu.
   Do decyzji: które naprawić przed fazą 3 (wtedy test od razu asertuje poprawne zachowanie).
5. **Wykluczenia z pokrycia** – propozycja minimalna: `[tool.coverage.report] exclude_also = ["if __name__ == .__main__.:", "if TYPE_CHECKING:"]`
   (4 bloki `__main__`, 3 bloki `TYPE_CHECKING`). `run_server()` w `api/main.py` i `server` w `cli/main.py` pokrywamy przez monkeypatch `uvicorn.run`
   zamiast wykluczać. `reference_data.main()` testowany przez respx + `capsys`. **Nie** wykluczamy żadnych modułów w całości – arytmetyka sekcji 2 działa bez wykluczeń.
6. **Nieosiągalna gałąź** `api/routes/download.py:158-162` (walidacja zakresu lat po `Query(ge=1951, le=2024)` – nigdy nie zadziała, dopóki `get_available_years`
   zwraca `(1951, rok_bieżący)`). Zostaje niepokryta (5 linii) – albo usunąć w follow-up.
7. **Plik `data/imgw_hydro.db` w katalogu roboczym** – fixture `tmp_db` zawsze przestawia `settings.db_path`; dodatkowo proponuję w `conftest.py` autouse-fixture,
   która ustawia `settings.db_enabled=False` i `db_path=tmp_path/"unused.db"` dla wszystkich testów (ochrona przed przypadkowym zapisem do prawdziwej bazy).
   Do potwierdzenia.
8. **Przeniesienie stałych CSV z `test_parsers.py` do `conftest.py`** – lekka zmiana istniejącego pliku (import zamiast definicji). Alternatywa: zostawić
   duplikat trzech wierszy w conftest. Rekomendacja: przenieść.
9. **`--cov-fail-under=80` w `addopts`** – włączyć dopiero w fazie 6; przy `addopts` z `-m 'not integration'` upewnić się, że `pytest -m integration` nadal
   działa (jawny `-m` nadpisuje).
10. **Testy integracyjne z prawdziwym IMGW** – nie dodajemy (marker zarezerwowany). Jeśli właściciel chce smoke-testu URL-i (HEAD na `codz_2023.zip`),
    dodać jeden plik `tests/integration/test_imgw_live.py` z `@pytest.mark.integration` – poza arytmetyką pokrycia.
11. **Czas i rozmiar** – ~230 testów w 20 plikach; przy regule „jeden test = jedno zachowanie” pliki CLI (`test_cli_db.py`, `test_cli_fetch.py`) będą
    największe (~25 testów). Akceptowalne? Alternatywa: skrócić `cli/db.py` do ścieżek szczęśliwych + walidacji (pokrycie ~65%, TOTAL wciąż ~85%).

---

## 7. Definition of done

```
.venv/bin/python -m pytest -q --cov=imgwtools --cov-report=term-missing
# oczekiwane: wszystkie testy passed (>= 109 starych + nowe), TOTAL >= 80% (plan: ~89%),
# brak ostrzezen o nieobsluzonych zadaniach HTTP (respx assert_all_mocked),
# zadne 'Missing' w core/url_builder.py, models.py, db/models.py, config.py, api/schemas.py

.venv/bin/python -m pytest -q                      # po fazie 6: przechodzi prog --cov-fail-under=80
.venv/bin/python -m pytest -q -m integration       # "no tests ran" (brak testow integracyjnych) lub tylko opt-in
.venv/bin/ruff check src/ tests/                   # All checks passed!
.venv/bin/ruff format --check src/ tests/          # bez zmian
npx -y pyright src/imgwtools/                      # 0 errors (bez zmian wzgledem HEAD)
git status                                         # zmiany tylko w tests/, pyproject.toml, README.md, docs/ (zadne w src/ poza ewentualnymi follow-upami z sekcji 6)
```

Dodatkowo: w `README.md` (sekcja o testach) i `docs/DEVELOPMENT_STANDARDS.md` 5.1/5.4/10 zaktualizować liczbę testów i procent;
w `docs/PROGRESS.md` wpis o osiągnięciu progu.
