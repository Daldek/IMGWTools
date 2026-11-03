# IMGWTools test overhaul plan (goal: >= 80% coverage)

As of: 2026-08-22, branch `develop` (then `slave`), v2.2.0, HEAD `bd90db2` (sections 1–2: baseline and historical arithmetic).
Environment: `.venv/bin/python` only (the global python has an outdated package).
Installed in `.venv`: pytest 9.0, pytest-cov 7.0, pytest-asyncio 1.3 (`asyncio_mode = "auto"`),
**respx 0.23** (it is in `[dev]`), fastapi 0.128 + starlette (TestClient), typer 0.21
(CliRunner), pandas 2.3, pydantic-settings 2.12, pyarrow (extra `[store]`). Extras `[api,cli,pandas,store]` are available.

> **Update 2026-10-18 (3.0.0, ADR-001):** the SQLite cache was removed (`db/`, `cli/db.py`, `/api/v1/hydro/data`, the
> `db_*` settings), so all planned DB-layer tests (former 4.4, 4.9–4.13, 4.24 and the `tmp_db`/`db_ready` fixtures) were replaced
> by versioned-store tests that already exist in `tests/unit/` (section 4.9). The planned `tmp_data_dir` is not
> needed: `tests/conftest.py` has the autouse fixture `isolated_data_dir`, which for **every** test sets
> `settings.data_dir` to an empty temporary directory and returns it (tests that need a reference file write it there).
> The hydro parsers moved from `db/parsers.py`/`db/models.py` to `_parsing/common.py`, `_parsing/hydro.py` and `models.py`
> (`HydroArchiveStation`, `Hydro*Record`); line numbers in section 1 refer to the 2.2.0 state.
>
> **Update 2026-10-18 (3.0.0, ADR-002):** `cli/fetch.py`, `cli/list_cmd.py` (`imgw fetch|list`), the routes
> `api/routes/hydro|meteo|download|pmaxtp|store.py` and `core/url_builder.py` were removed; the CLI and REST are generated from the command catalog
> (`cli/_dispatch.py`, `api/routes/commands.py`), CLI stdout is the `imgw-result/1` envelope, and exit codes come
> from the `ERROR_CODES` registry (not 0/1). The tests planned here for those modules were replaced by `tests/unit/test_cli_catalog.py`,
> `test_api_commands.py`, `test_command_schema.py`, `test_commands.py` and the contract
> `tests/contract/test_interface_contract.py`; URL builder tests by `test_datasets.py` (`archive_files`) and `test_urls.py`
> (`build_pmaxtp_url`, `build_api_url`). Live regression is covered by `tests/live/test_interfaces_live.py` (`IMGW_LIVE=1`). State: 1419 tests (1377 offline, 42 live; `pytest --collect-only`). Sections 1–4 remain a historical record.
>
> **Update 2026-10-19 (3.0.0, ADR-003 and ADR-004):** the ČHMÚ provider is covered by `tests/unit/test_*_chmi.py`,
> `test_parsing_chmi.py`, `test_store_content.py` and the contract `tests/contract/test_chmi_contract.py` (IMGW-15..19 on
> `build_fixture_store(variant="complete_pl_cz")`), and live by `tests/live/test_chmi_live.py`; agent support by
> `test_agent_guide.py` (the `AGENTS.md`/`llms.txt` drift test), `test_catalog_effects.py`, `test_catalog_i18n.py`,
> `test_mcp_*.py` and the contracts `tests/contract/test_mcp_contract.py` and `test_mcp_http_contract.py`. State as of 2026-10-19: 2213 tests
> (2134 offline, 79 live; `pytest --collect-only`).
>
> **Update 2026-10-25 (ADR-005, ADR-006, ADR-007):** descriptions below that mention `Settings.data_dir=./data`,
> `store_root`, writing via `.part`, `output` as the download directory or the export `path` describe the state before these decisions;
> the current names are `root` (`IMGW_ROOT`), `output_dir`, `output`, `force`, the `.imgw-incoming/` staging area and the statuses `new`/`unchanged`.
> Data output is covered by `tests/unit/test_output.py`, `test_plain_output.py`, `test_default_root.py`,
> `test_store_marker.py`, `test_cli_interrupt.py` (SIGINT and SIGTERM of real commands) and the REST and MCP write refusals in
> `test_api_commands.py` and `test_mcp_calls.py`. State: 2409 tests (2329 offline, 80 live; `docs/TESTING.md`).

Base commands:

```
.venv/bin/python -m pytest -q --cov=imgwtools --cov-report=term-missing
.venv/bin/ruff check src/ tests/
npx -y pyright src/imgwtools/
```

---

## 1. Baseline

Own run: **109 tests, 2586 statements, 1994 missed, 23% TOTAL**. Ruff: clean.

| Module | Stmts | Miss | % | Key gaps (lines from `term-missing`) |
|---|---:|---:|---:|---|
| `__init__.py`, `_version.py`, `exceptions.py`, `parsers.py`, `urls.py` | 21 | 0 | 100 | – |
| `core/url_builder.py` | 105 | 7 | 93 | 150 (`zjaw_` m=13), 158 (missing month <2023), 170 (missing param), 176/270 (unknown interval), 267 (missing meteo month 2001+), 365 (HYDRO branch in `get_available_years` – see pitfall 4) |
| `models.py` | 97 | 11 | 89 | 129-149 `to_dataframe`, 300-301 `_safe_int` invalid value |
| `db/models.py` | 73 | 9 | 88 | 175-185 `is_missing_value` |
| `db/parsers.py` | 176 | 39 | 78 | 64-65/71 invalid numbers, 204/296/405 short rows, 216/308 missing year/month, 228-229 invalid date, 337-338/474-475 corrupt row, 425-429 `H`/`Q` in semi-annual, 508 unknown ZIP interval, **543-575 `parse_stations_csv` (0%)** |
| `stations.py` | 138 | 56 | 59 | all `*_async` versions, `list_meteo_stations`, HTTP error branches |
| `fetch.py` | 223 | 122 | 45 | `HTTPStatusError`/`HTTPError` errors, `IMGWDataError`, all `*_async` except `fetch_pmaxtp_async`, `download_meteo_data_async`, `fetch_warnings` with a dict |
| `config.py` | 24 | 24 | 0 | nothing imports `settings` in tests |
| `db/__init__.py` | 34 | 31 | 9 | `__getattr__` lazy imports |
| `db/connection.py`, `db/schema.py`, `db/repository.py`, `db/cache_manager.py` | 376 | 376 | 0 | the whole SQLite layer |
| `api/main.py`, `api/schemas.py`, `api/routes/*` | 415 | 415 | 0 | the whole REST API |
| `cli/main.py`, `cli/fetch.py`, `cli/list_cmd.py`, `cli/admin.py`, `cli/db.py` | 655 | 655 | 0 | the whole CLI |
| `web/app.py` | 173 | 173 | 0 | HTMX/Jinja routes |
| `reference_data.py` | 76 | 76 | 0 | script that downloads reference data |
| **TOTAL** | **2586** | **1994** | **23** | |

Existing files: `tests/conftest.py` (JSON/CSV fixtures), `tests/unit/test_{models,fetch,parsers,stations,urls}.py`.
`tests/integration/` is empty. Network mocking: `unittest.mock.patch("imgwtools.fetch.httpx.Client")` with a hand-built
`MagicMock` (about 10 lines of boilerplate per test).

### Facts verified in the code that the tests MUST pin (pitfalls)

1. **Archive format drift** – now in `_parsing/common.py`: `_detect_delimiter`, `_decode_content` (BOM > cp1250 > utf-8),
   `_iter_rows` (outer quotes in 2024), missing-value codes `MISSING_WATER_LEVEL=9999`, `MISSING_FLOW=99999.999`,
   `MISSING_TEMP=99.9`, the hydrological year (`hydro_to_calendar_date`: months 1-2 = previous calendar year), a leading
   space in the station code. ZIP files are read by `archive_csv_members` with limits; a corrupt ZIP → `IMGWDataError` (in 2.2.0 a raw
   `BadZipFile`). An unknown interval in `parse_zip_file` → `ValueError`.
2. **Meteo URL layout** – `core/url_builder.py:75-112` (`_get_meteo_folder`: year >2000, precipitation `1950_1955` when <=1955, synop `1960_1965`
   when <=1965, grid `((y-1951)//5)*5+1951`), `build_meteo_url` 235-249 (hourly precipitation -> `ValueError`, synop daily/hourly ->
   `ValueError` "per-station", synop <1960), 257-270 (monthly = one file per folder; daily/hourly yearly up to 2000, monthly
   from 2001 with a required `month`), 280 (`month=None` in the result for years <=2000). Hydro 147-176: `zjaw_{year}.zip` for `month=13`
   (every year), `codz_{year}.zip` from 2023 (month ignored in the name but echoed in `DownloadURL.month`), `codz_{year}_{mm}.zip` before 2023
   (missing month -> `ValueError`), `mies_{year}.zip`, `polr_{T|Q|H}_{year}.zip` (missing `param` -> `ValueError`).
3. **Two station classes** – `stations.HydroStation` (fields `station_id`, `name`, `river`; aliases `station_code`, `station_name`,
   `river_name`; `populate_by_name=True`; `river` extracted from `"Odra (1)"`) vs the archive `models.HydroArchiveStation`
   (`station_code`, `station_name`, `river_name`, no aliases; in 2.2.0 `db/models.HydroStation`). Access differs
   (`.name` vs `.station_name`).
4. **`get_available_years`** – `core/url_builder.py:344-368`: the `interval` parameter is unused, both branches return `(1951, current_year)`.
   `tests/unit/test_urls.py:238` and `:247` pass the strings `"hydro"`/`"meteo"`; `"hydro" == DataType.HYDRO` is `False`
   (the enum value is `"dane_hydrologiczne"`), so both tests hit the meteo branch and line 365 is never executed.
5. **PMAXTP** – `models.py:39-111`: keys are the strings `"15"`/`"50"`, getters return `None` for missing values; `fetch.py:42-62`
   bounds 49-55 / 14-24.5 (inclusive), `IMGWValidationError`; `validate_coords=False` (125-126) bypasses validation.
6. **Placeholder in the API** – `api/routes/hydro.py:38-45` and `api/routes/meteo.py:33-38` return 2 hard-coded stations (`# TODO`).
7. **CLI** – `cli/main.py:36-39` `version` reads `__version__` from `_version.py`; `cli/list_cmd.py:102-107` `datasets` computes the range from
   `get_available_years`; `--help` texts come from docstrings (ASCII).
8. **Store (instead of DB)** – a version is published with hard links without replacing, committed by a sidecar linked last (`store/writer.py`), sidecar
   `imgw-meta/1` with the full SHA, `check_*` without writing and without a data GET, an unknown schema (`imgw-store/2`, `imgw-meta/2`)
   reported, not parsed; `pyarrow` required only on Parquet paths (`IMGWStoreDependencyError`).
9. **Encoding** – `IMGW_ENCODING = "cp1250"` in two places (`stations.py`, `_parsing/common.py`), re-exported in `parsers.py`.
10. **Config** – `config.py`: `env_prefix="IMGW_"`, `data_dir=./data`, `store_root=None`, `store_writes_enabled=False`,
    `store_write_token=None` (`SecretStr`), `user_locations_dir=None`, `env_file=".env"` (the repo has no `.env`; there is
    `.env.example`). The autouse `isolated_data_dir` protects tests from local reference data in `data/`.

### Bugs in the code found during the analysis (do NOT fix as part of this plan – report as follow-ups)

- ~~`db/repository.py:616-630` `clear_cache` overstated the counter~~ – obsolete: the DB layer was removed in 3.0.0.
- `api/routes/hydro.py:69,105` and `meteo.py:134` read `nazwa_stacji`, while the IMGW API (and `models.py:192`) uses `stacja` ->
  `station_name` in the API response is always `""`. **Fixed in 3.0.0** (the routes read `stacja`); tests assert the correct behaviour.
- Hard-coded year limits in the API: `schemas.py:97,108` (`le=2024`), `routes/hydro.py:185-186,245-248`, `routes/meteo.py:204-205`,
  `routes/download.py:40-70` (`year_range=(…, 2023)`), `download.py:85,155-156`. The same class of regression as the one fixed in `bd90db2`.
  **Fixed in 3.0.0**: URLs come from the `archive_files` registry, year validation has no upper limit of 2024.
- ~~`api/main.py:35` `API_VERSION = "1.0.0"`~~ – fixed in 3.0.0: `API_VERSION = __version__`.
- `cli/fetch.py:150` for daily data <2023 without `--month` downloads `range(1, 14)` (13 = phenomena) – intended, but undocumented in `--help`.
- ~~`db/parsers.py:510` `ZipFile` raised `zipfile.BadZipFile`~~ – fixed in 3.0.0: `parse_zip_file` and `download_*` raise
  `IMGWDataError`.

---

## 2. Goal and arithmetic

Goal: **>= 80% TOTAL** with `--cov=imgwtools`. Below are realistic per-module targets (the "Target" column = the number of statements the plan covers)
and a pessimistic variant.

> The arithmetic below refers to the 2.2.0 state (2586 statements). The `db/*` and `cli/db.py` rows do not exist since 3.0.0; the store
> modules (`store/*`, `commands.py`, `datasets.py`, `_parsing/*`) have their own tests from section 4.9, and the
> 80% threshold is measured on the current code (`pytest --cov=imgwtools`).

| Module | Stmts | Covered today | Target (stmts) | Target % | Notes / cost |
|---|---:|---:|---:|---:|---|
| `__init__`, `_version`, `exceptions`, `parsers`, `urls` | 21 | 21 | 21 | 100 | imports |
| `core/url_builder.py` | 105 | 98 | 105 | 100 | 7 lines = 6 error tests |
| `models.py` | 97 | 86 | 97 | 100 | `to_dataframe` (pandas is installed), `_safe_int` |
| `db/models.py` | 73 | 64 | 73 | 100 | `is_missing_value`, `hydro_to_calendar_date` |
| `db/parsers.py` | 176 | 137 | 168 | 95 | `parse_stations_csv`, ZIP, corrupt rows |
| `stations.py` | 138 | 82 | 130 | 94 | respx: sync+async, errors |
| `fetch.py` | 223 | 101 | 205 | 92 | respx: 12 functions, 3 error classes |
| `config.py` | 24 | 0 | 24 | 100 | `monkeypatch.setenv` |
| `db/__init__.py` | 34 | 3 | 34 | 100 | loop over `__all__` + `AttributeError` |
| `db/connection.py` | 41 | 0 | 39 | 95 | tmp SQLite |
| `db/schema.py` | 48 | 0 | 46 | 96 | |
| `db/repository.py` | 164 | 0 | 150 | 91 | all 4 branches of `is_range_cached` |
| `db/cache_manager.py` | 123 | 0 | 105 | 85 | respx + ZIP builder |
| `api/schemas.py` | 118 | 0 | 118 | 100 | import alone |
| `api/main.py` | 33 | 0 | 28 | 85 | `run_server`/`__main__` out of scope |
| `api/routes/download.py` | 61 | 0 | 55 | 90 | |
| `api/routes/hydro.py` | 102 | 0 | 85 | 83 | `/data` from cache = DB fixture + respx |
| `api/routes/meteo.py` | 71 | 0 | 62 | 87 | |
| `api/routes/pmaxtp.py` | 30 | 0 | 27 | 90 | |
| `web/app.py` | 173 | 0 | 150 | 87 | TestClient + respx; templates render |
| `cli/main.py` | 22 | 0 | 17 | 77 | `server` (uvicorn) and `__main__` out of scope |
| `cli/list_cmd.py` | 72 | 0 | 62 | 86 | CSV in `tmp_path` |
| `cli/admin.py` | 96 | 0 | 82 | 85 | `api_keys_file` in `tmp_path` |
| `cli/fetch.py` | 215 | 0 | 170 | 79 | respx also for `httpx.stream` |
| `cli/db.py` | 250 | 0 | 190 | 76 | most expensive module; `query` with a table and `--output` |
| `reference_data.py` | 76 | 0 | 60 | 79 | respx for CSV/JSON/HTML listings |
| **TOTAL** | **2586** | **592** | **2303** | **89** | |

**Proof**: 2303 / 2586 = **89.1%**. Pessimistic variant (CLI `db` 150, CLI `fetch` 140, `web` 120, `reference_data` 40,
`routes/hydro` 70 – -135 in total): 2168 / 2586 = **83.8%**. Both variants are above the threshold, with a margin for skipping
the most expensive paths (e.g. `cli/db.py query` with a monthly table).

If the owner agrees to the exclusions from section 6 (`__main__` blocks, `run_server`, `cli server`, `reference_data.main`),
the denominator drops by about 20 statements – with no effect on the decision.

---

## 3. Test infrastructure

### 3.1 Network mocking strategy: `respx`

Decision: **new tests use `respx`** (the `respx_mock` fixture from the respx pytest plugin – verified to be registered).
Rationale:
- it is already in `[dev]` (`pyproject.toml`), zero new dependencies;
- it mocks the httpx transport, so it works for `httpx.Client`, `httpx.AsyncClient` and `httpx.stream`
  (`cli/fetch.py:44`) at once – sync/async parity is tested with the same route;
- a test is 3 lines instead of 10 lines of `MagicMock` with `__enter__/__exit__`;
- `assert_all_mocked=True` by default: every unexpected network request fails -> a guarantee of "zero real network".

The existing 109 tests with `patch("…httpx.Client")` **stay unchanged** (they run alongside respx). The only fix: `test_urls.py:238,247`.

Pattern (AAA, one test = one behaviour):

```python
def test_fetch_hydro_current_maps_http_500_to_connection_error(respx_mock):
    respx_mock.get(f"{IMGW_API_URL}/hydro").respond(500)

    with pytest.raises(IMGWConnectionError):
        fetch_hydro_current()
```

### 3.2 New fixtures in `tests/conftest.py`

| Fixture | Scope | What it does |
|---|---|---|
| `daily_csv_rows` / `monthly_csv_rows` / `semi_annual_csv_rows` | module | constants from `test_parsers.py` (move them to conftest and have test_parsers import from conftest, or keep a duplicate of the 3 constants – recommendation: move, because they are needed in CLI/API tests) |
| `make_zip` | function | `make_zip({"codz_2023.csv": bytes}) -> bytes` – in-memory ZIP builder (`zipfile.ZipFile(io.BytesIO())`) |
| `hydro_daily_zip` | function | `make_zip` with 2-3 daily rows for 2023 (UTF-8 BOM, `;`), including the missing-value codes `9999` and `99.9` |
| `hydro_monthly_zip`, `hydro_semi_annual_zip` | function | likewise |
| `isolated_data_dir` (**exists**, autouse) | function | `monkeypatch.setattr(settings, "data_dir", tmp_path_factory.mktemp("data"))` for every test; returns the directory. Replaces the planned `tmp_data_dir` (CLI `list stations`, `reference_data`, the static station catalog file) |
| store fixtures (**exist**) | – | `imgwtools.testing.build_fixture_store(root, variant=…)` (variants `complete`, `corrupt`, `unknown_schema`) and the recordings/archives in `tests/fixtures/store/`; local `store`/`root`/`fixture_root` in the files `test_store_*.py`, `test_commands.py`, `test_project.py`, `test_cli_store_project.py` |
| `api_client` | module | `fastapi.testclient.TestClient(imgwtools.api.main.app)` – the import is safe (the `web/static` directory exists) |
| `cli` | module | `typer.testing.CliRunner()`; tests call `cli.invoke(app, [...])` on `imgwtools.cli.main.app` |
| `hydro_api_url` etc. | – | not needed; use the constants `IMGW_API_URL`, `IMGW_PMAXTP_URL`, `HYDRO_STATIONS_CSV_URL`, `HYDRO_MAP_API_URL` from the code |

`settings` is a single object (`imgwtools.config.settings`) imported by, among others, `cli/admin.py`, `cli/list_cmd.py`, `store/catalog.py`
and `api/routes/store.py` – `monkeypatch.setattr` on the instance works everywhere (pydantic has no `validate_assignment`).

### 3.3 Markers and configuration

- `pyproject.toml` `[tool.pytest.ini_options]`: add `markers = ["integration: tests with the real IMGW network (skipped by default)"]`
  and `addopts = "-m 'not integration'"`. Integration tests are run explicitly with `-m integration`. **Recommendation: do not add any integration
  tests in this plan** (the `tests/integration/` directory stays empty with `__init__.py`) – the IMGW server is unstable, and all
  format pitfalls are reproduced in fixtures.
- Final step (section 5, phase 6): `--cov-fail-under=80` in `addopts`.
- Optional (owner decision, section 6): `[tool.coverage.report] exclude_also = ["if __name__ == .__main__.:", "if TYPE_CHECKING:"]`.

### 3.4 Writing rules

- Names `test_<function>_<scenario>` as in DEV-10.5 of the [Nogat development standard](https://github.com/Daldek/Nogat/blob/main/standards/DEVELOPMENT_STANDARDS.md) (standard 1.0); no test classes in new files (flat functions, as in `test_parsers.py`).
- Ruff `E/W/F/I/B/UP/C4` applies to `tests/**` (only `D` is disabled) – sorted imports, no unused imports.
- ASCII in sources; Polish characters in tests only in encoding fixtures (as `Ławica` today).
- No `time.sleep`, no real files outside `tmp_path`, no global state without `monkeypatch`.

---

## 4. Per-module plan

Format: `test_name` – what it asserts [pitfall/error class] (fixture).

### 4.1 `tests/unit/test_urls.py` – FIX of existing tests

- `test_hydro_daily_years` (line 238): replace `"hydro"` with `DataType.HYDRO` (+ import). Reason: the string is never equal to
  the enum, the test went through the meteo branch – falsely green. [pitfall 4]
- `test_meteo_years` (247): `"meteo"` -> `DataType.METEO`.

### 4.2 `tests/unit/test_url_builder.py` (new; closes 7 lines + pins boundaries)

- `test_build_hydro_url_daily_before_2023_without_month_raises` – `ValueError` "Month is required" (158). [boundary 2022]
- `test_build_hydro_url_daily_2022_december_filename` – `codz_2022_12.zip`. [boundary month 12]
- `test_build_hydro_url_daily_2023_ignores_month_in_filename_but_echoes_it` – `codz_2023.zip`, `result.month == 6`. [boundary 2023]
- `test_build_hydro_url_phenomena_month_13_any_year` – `zjaw_2024.zip` for `month=13` also >= 2023 (150).
- `test_build_hydro_url_semi_annual_without_param_raises` – (170).
- `test_build_hydro_url_unknown_interval_raises` – pass `MeteoInterval.HOURLY` (176; str-enum with a different value).
- `test_build_meteo_url_daily_2001_without_month_raises` – (267). [boundary 2001]
- `test_build_meteo_url_daily_2000_is_yearly_file_and_month_is_none` – `2000_k.zip`, folder `1996_2000`, `result.month is None` even when `month=5` is given (280). [boundary 2000]
- `test_build_meteo_url_unknown_interval_raises` – pass `HydroInterval.SEMI_ANNUAL` (270).
- `test_get_meteo_folder_grid` – `pytest.mark.parametrize`: (1951,k)->`1951_1955`, (1955,k)->`1951_1955`, (1956,k)->`1956_1960`,
  (1950,o)->`1950_1955`, (1956,o)->`1956_1960`, (1965,s)->`1960_1965`, (1966,s)->`1966_1970`, (2000,k)->`1996_2000`, (2001,k)->`2001`. [pitfall 2]
- `test_build_meteo_url_hourly_klimat_2000_yearly` – hourly klimat 2000 -> `2000_k.zip` (the `year <= 2000` branch for HOURLY).
- `test_get_available_years_hydro_starts_1951_and_ends_current_year` – `DataType.HYDRO` (365). [pitfall 4]
- `test_get_available_years_ignores_interval_argument_current_behaviour` – identical result for `"dobowe"`, `"terminowe"`, `""`;
  a comment that this pins the current state, not a specification. [pitfall 4]
- `test_get_available_years_meteo_returns_1951_current_behaviour` – pin.
- `test_build_pmaxtp_url_method_letter` – `P`/`A` in the path (already in test_urls – skip if a duplicate).

### 4.3 `tests/unit/test_models.py` (additions)

- `test_pmaxtp_to_dataframe_columns_and_rows` – columns `duration, probability, ks_mm, sg_mm, rb_mm`, `sg_mm` `None` when missing from `sg` (129-149) (`pmaxtp_api_response`).
- `test_pmaxtp_to_dataframe_empty_data` – empty DataFrame.
- `test_safe_int_invalid_string_returns_none` – `_safe_int("abc")` (300-301).
- `test_safe_float_none_and_invalid` – `None`, `"n/a"`.
- `test_pmaxtp_keys_are_plain_strings_without_prefix` – `"15" in data.ks`, `"t15" not in data.ks`. [pitfall 5]

### 4.4 Hydrological dates and missing-value codes (`_parsing/common.py`; in `tests/unit/test_parsers.py`)

Formerly `test_db_models.py` – the `db/models.py` module was removed in 3.0.0; the functions are in `_parsing/common.py` (private, tested through the public parsers
or by a direct import in `test_parsers.py`):

- `test_hydro_to_calendar_date_month_1_is_november_previous_year` – (2023,1,1) -> 2022-11-01. [pitfall 1, boundary]
- `test_hydro_to_calendar_date_month_2_is_december_previous_year`, `_month_3_is_january_same_year`, `_month_12_is_october`.
- `test_hydro_to_calendar_date_invalid_month_raises_keyerror` – 13; `_invalid_day_raises_valueerror` – 30 February.
- `test_is_missing_value_level_flow_temp_and_none` – parametrize: (9999,"level")->True, (99999.999,"flow")->True, (99.9,"temp")->True,
  (None,"x")->True, (12.5,"level")->False, (1.0,"other")->False. [missing-value codes]
- `test_archive_station_uses_station_name_attribute` – `models.HydroArchiveStation(...).station_name`; no `.name` (`AttributeError`). [pitfall 3]
- `test_daily_record_rejects_hydro_month_13` – `ValidationError` (`models.HydroDailyRecord`).

### 4.5 `tests/unit/test_stations.py` (additions; new tests with respx)

- `test_public_hydro_station_exposes_name_and_aliases` – `HydroStation(station_code=…, station_name=…)` -> `.name`, `.station_id`;
  `HydroStation(station_id=…, name=…)` works too (`populate_by_name`). [pitfall 3]
- `test_parse_hydro_stations_csv_strips_leading_space_in_quoted_code` – `'" 123456789","X","Odra (1)"'` -> `"123456789"`. [pitfall 1]
- `test_parse_hydro_stations_csv_river_without_suffix_kept_verbatim`.
- `test_list_hydro_stations_decodes_cp1250` (respx: `HYDRO_STATIONS_CSV_URL`, content `"…Ławica (1)".encode("cp1250")`) -> `river == "Ławica"`. [pitfall 9]
- `test_list_hydro_stations_http_404_raises_connection_error` (respx `.respond(404)`). [exception mapping]
- `test_list_hydro_stations_async_equals_sync` (respx; `await`). [parity]
- `test_list_meteo_stations_parses_rows` + `test_list_meteo_stations_async_equals_sync`.
- `test_list_meteo_stations_timeout_raises_connection_error` (`side_effect=httpx.ConnectTimeout`).
- `test_get_hydro_stations_with_coords_sends_only_main_stations_param` – `include_all=False` -> `onlyMainStations=true` in `respx_mock.calls.last.request.url`.
- `test_get_hydro_stations_with_coords_async_equals_sync`.
- `test_get_hydro_stations_with_coords_http_error_raises_connection_error`.
- `test_parse_map_stations_response_skips_malformed_item` – an element without an `id`, of type `None`, in the list (the `except` branch 387).

### 4.6 `tests/unit/test_fetch.py` (additions; respx)

- `test_fetch_pmaxtp_boundary_coordinates_are_valid` – parametrize the 4 corners: (49.0,14.0), (55.0,24.5), (49.0,24.5), (55.0,14.0) – does not raise (respx 200). [boundary]
- `test_fetch_pmaxtp_just_outside_bounds_raises` – 48.999 / 55.001 / 13.999 / 24.501.
- `test_fetch_pmaxtp_validate_coords_false_bypasses_check` – (0,0) with respx 200 -> a result. [pitfall 5]
- `test_fetch_pmaxtp_http_500_raises_connection_error_with_status` – the message contains `500` (138-141).
- `test_fetch_pmaxtp_connect_error_raises_connection_error` – `side_effect=httpx.ConnectError` (142-143).
- `test_fetch_pmaxtp_invalid_json_raises_data_error` – `respond(content=b"<html>")` -> `json()` raises -> **note**: `response.json()` is in a
  `try` block with httpx exceptions, `json.JSONDecodeError` is not an `httpx.HTTPError`, so a raw `JSONDecodeError` escapes, not `IMGWDataError`.
  The test pins the current behaviour (`pytest.raises(ValueError)`) with a comment – a follow-up candidate. [exception mapping]
- `test_fetch_pmaxtp_bad_structure_raises_data_error` – `respond(json={"data": {"ks": "not-a-dict"}})` -> `IMGWDataError` (152-153).
- `test_fetch_pmaxtp_async_equals_sync` – the same route, comparing `model_dump()`. [parity]
- `test_fetch_pmaxtp_async_http_error_raises_connection_error`.
- `test_fetch_hydro_current_http_error_raises_connection_error`, `test_fetch_hydro_current_bad_item_raises_data_error`
  (`respond(json=[None])`), `test_fetch_hydro_current_async_equals_sync`.
- `test_fetch_synop_async_filters_by_name`, `test_fetch_synop_http_error_raises_connection_error`, `test_fetch_synop_bad_item_raises_data_error`.
- `test_fetch_warnings_single_dict_is_wrapped`, `test_fetch_warnings_none_response_returns_empty`, `test_fetch_warnings_async_equals_sync`,
  `test_fetch_warnings_http_error_raises_connection_error`.
- `test_download_hydro_data_builds_url_from_params` – `respx_mock.get(url).respond(content=b"PK")`; assertion on the requested URL (`codz_2022_06.zip`).
- `test_download_hydro_data_http_404_raises_connection_error_with_url` – the message contains the URL (553-556).
- `test_download_hydro_data_timeout_raises_connection_error`, `test_download_hydro_data_async_equals_sync`.
- `test_download_hydro_data_invalid_interval_raises_value_error` – `"tygodniowe"` -> `ValueError` from `HydroInterval(...)`.
- `test_download_meteo_data_hourly_opad_raises_value_error` – passes on the `ValueError` from the builder (not `IMGWConnectionError`).
- `test_download_meteo_data_http_404_raises_connection_error`, `test_download_meteo_data_async_equals_sync`.

### 4.7 `tests/unit/test_parsers.py` (additions)

- `test_parse_stations_csv_bytes_cp1250_and_river_suffix` – cp1250 bytes, `"Ławica (1)"` -> `river_name == "Ławica"` (543-575). [pitfall 1, 9]
- `test_parse_stations_csv_river_without_suffix_kept`, `test_parse_stations_csv_skips_short_rows`, `test_parse_stations_csv_str_input`.
- `test_parse_zip_file_unknown_interval_raises_value_error` (508).
- `test_parse_zip_file_reads_only_csv_members` – a ZIP with `readme.txt` + `codz.csv` (`make_zip`).
- `test_parse_zip_file_multiple_csv_members_concatenated`.
- `test_parse_zip_file_empty_archive_yields_nothing`.
- `test_parse_zip_file_corrupt_bytes_raises_badzipfile` – pin `zipfile.BadZipFile` (see the bug list).
- `test_parse_daily_csv_missing_codes_become_none` – a row with `9999`, `99999.999`, `99.9` -> three `None`. [missing-value codes]
- `test_parse_daily_csv_skips_rows_with_fewer_than_9_columns` (204), `test_parse_daily_csv_skips_row_without_year` (216),
  `test_parse_daily_csv_invalid_date_sets_measurement_date_none` – day 31 in hydrological month 4 (February) (228-229).
- `test_parse_daily_csv_hydro_month_1_maps_to_november_previous_year` – `measurement_date == "2022-11-01"` for (2023,1,1). [pitfall 1]
- `test_parse_monthly_csv_unknown_extremum_defaults_to_mean` (310), `test_parse_monthly_csv_skips_short_rows` (296).
- `test_parse_semi_annual_csv_h_uses_level_missing_code` and `_q_uses_flow_missing_code` (425-427).
- `test_parse_semi_annual_csv_mean_has_no_dates` – 8 columns -> `extremum_start_date is None`.
- `test_parse_semi_annual_csv_unknown_period_defaults_to_annual`.
- `test_safe_float_non_numeric_returns_none`, `test_safe_int_non_numeric_returns_none` (64-65, 71).

### 4.8 `tests/unit/test_config.py` (new)

Store settings from `IMGW_*` are already covered by `test_api_store.py::test_store_settings_come_from_imgw_environment`; the general ones remain here:

- `test_settings_defaults` – `data_dir == Path("data")`, `store_root is None`, `store_writes_enabled is False`, `store_write_token is None`,
  `user_locations_dir is None`, `port 8000`, `env development`. [pitfall 10]
- `test_settings_reads_imgw_prefixed_env` – `monkeypatch.setenv("IMGW_DATA_DIR", …)`, `IMGW_PORT` -> a new `Settings()` instance.
- `test_settings_ignores_unprefixed_env` – `PORT=1` has no effect.
- `test_settings_station_file_paths_follow_data_dir` – `hydro_stations_file`, `meteo_stations_file`.
- `test_settings_is_production` – `IMGW_ENV=production`.
- `test_settings_invalid_log_level_raises` – `ValidationError`.

### 4.9 Versioned store (replaces the former DB-layer 4.9–4.13; the tests exist)

All offline: recordings from `tests/fixtures/store/` or respx, directories in `tmp_path`, no real `data/` (autouse `isolated_data_dir`).
Public tests must not require importing Kartograf or the network.

| File | What it pins |
|---|---|
| `test_store_types.py` | immutable types, `StorePlan.to_json/from_json` (round-trip, `cancelled`, additive fields), exceptions inherit from `IMGWError`, the `pip install imgwtools[store]` instruction |
| `test_store_writer.py` | provenance and the `imgw-meta/1` sidecar, `relabeled`/`unchanged`, concurrent writers, an interrupted publication (directory without a sidecar) skipped and completed, different bytes under the same name never replaced, a failed commit (EIO, Ctrl+C) does not delete files taken over by a concurrent write, explicit refusal on a FS without hard links (`not_atomic`, also the marker), cleanup after interruption + `fsync`, detecting Kartograf without importing it, path escape |
| `test_store_sync.py` | `check_store` only listing + `HEAD` (five statuses), plan round-trip, `stale_plan` without GET, new hash = new version, the same hash under a new signal = `relabeled`, `unverifiable`/`check_failed` are not downloaded, cancellation without a half-written version, series only from complete inputs |
| `test_store_series.py` | `check_series` offline, daily/monthly/semi-annual snapshots (29 Feb, hydrological year, `accumulated`), `reused` without a Parquet writer, no pyarrow → `IMGWStoreDependencyError`, importing the core without pyarrow |
| `test_store_catalog.py` | station lists archived first, location precedence API → static (`isolated_data_dir`) → user, Poland outline without GIS, RFC 7946, `unchanged` for identical content, `check_catalog` only `HEAD`, `meteo_kind` from the current climate and precipitation series |
| `test_store_pmaxtp.py` | cell key from the response, the same cell without a new version, AMP separately, invalid indices/empty data without a write, offline read |
| `test_store_reader.py` | reading a read-only directory without network or writes, date ranges consistent with the parser, scan problems, unknown `imgw-store/2` reported, validation of `Meta` fields |
| `test_series_export.py` | CSV: header with units, attribution formulas once, every day, `year_type`, semi-annual columns, atomic write via `.part` |
| `test_datasets.py`, `test_coverage.py` | the `pl.imgw.*` registry and `archive_files` (boundaries 2000/2001, 2022/2023, 29 Feb), coverage per station × variable |
| `test_store_fixtures.py`, `test_fixture_builder.py` | fixed recordings and archives, `build_fixture_store` (variants, determinism with a frozen clock, no leak of reference data) |
| `test_commands.py` | the command catalog (offline validation, `format_command` round-trip, `check_command` without writes, one public API per action); `test_project.py` (project manifest) was removed together with projects (ADR-008) |
| `test_public_store_api.py` | a single `__all__` list, the same objects in `imgwtools.store`, frozen dataclasses, keyword-only, import without pyarrow and without `imgwtools.db` |

Final contract (T25, done 2026-10-18): `tests/contract/test_versioned_store.py`, `test_cli_api_parity.py`
– the full path HEAD→plan→sync→series→catalog→CSV, JSON Schemas §11 and CLI = API parity of paths/SHA; `test_project_contract.py` (project→verify/restore) was removed together with projects (ADR-008).

### 4.14 `tests/unit/test_api_system.py` (new; `api_client`)

- `test_health_returns_ok` – 200, `{"status":"ok","version":API_VERSION}`.
- `test_api_info_lists_four_endpoints`.
- `test_openapi_schema_builds` – `GET /openapi.json` 200 (catches `response_model`/Pydantic errors for all routes at once – cheap and strong).

### 4.15 `tests/unit/test_api_hydro.py`

- `test_list_hydro_stations_shape` – 200, `count == len(stations)`, every element has `id/name/river`; **no assertions on names**;
  comment `# Placeholder (TODO in routes/hydro.py:38) - the test pins the schema, not the data`. [pitfall 6]
- `test_list_hydro_stations_offset_beyond_count_gives_empty_list_and_total_count`.
- `test_list_hydro_stations_rejects_limit_0` – 422.
- `test_get_hydro_station_404_when_imgw_returns_empty` (respx `[]`), `test_get_hydro_station_502_on_http_error`,
  `test_get_hydro_station_maps_fields` (`rzeka`, `lat`, `lon`).
- `test_current_hydro_maps_fields_and_wraps_dict` (respx dict) – **pin** `station_name == ""` with a comment about `nazwa_stacji`/`stacja`.
- `test_current_hydro_empty_list`, `test_current_hydro_502_on_connection_error`.
- `test_download_url_daily_2023`, `test_download_url_daily_2022_without_month_400`, `test_download_url_semi_annual_without_param_400`,
  `test_download_url_year_2025_accepted` – since 3.0.0 without the upper limit of 2024.
- `test_download_urls_daily_2022_2023_counts_13` – 12 + 1. [boundary 2022/2023]
- `test_download_urls_start_gt_end_400`, `test_download_urls_semi_annual_with_param`.
- The former `GET /api/v1/hydro/data` tests (DB cache) – removed together with the endpoint in 3.0.0; the REST store routes are tested by
  `tests/unit/test_api_store.py` (503 without `IMGW_ROOT`, 403 with writes disabled/no token, `version` restricted
  to `versions/`, parity with the Python API) and `tests/unit/test_api_download_registry.py` (URLs from the registry).

### 4.16 `tests/unit/test_api_meteo.py`

- `test_list_meteo_stations_shape_not_names` [pitfall 6], `test_synop_maps_fields_and_filters_none_values` (respx; `stacja` works here),
  `test_synop_empty_response`, `test_synop_502_on_error`, `test_current_meteo_maps_fields`, `test_current_meteo_502_on_error`.
- `test_download_url_monthly_synop_2023`, `test_download_url_hourly_opad_400`, `test_download_url_daily_synop_400_per_station`,
  `test_download_url_year_2000_rejected_422` (pin `ge=2001`).
- `test_download_urls_daily_klimat_two_years_gives_24`, `test_download_urls_skips_invalid_combo_returns_0` (terminowe/opad), `test_download_urls_start_gt_end_400`.

### 4.17 `tests/unit/test_api_download.py`

- `test_datasets_lists_six_with_year_ranges` – 6 entries, `year_range` is a pair of ints (pin `(…,2023)` with a follow-up comment).
- `test_url_hydro_daily`, `test_url_meteo_requires_subtype_400`, `test_url_meteo_monthly_opad_1975_folder_1971_1975`, `test_url_invalid_interval_400`
  (`HydroInterval("x")` -> `ValueError` -> 400), `test_url_hydro_semi_annual_param_T`.
- `test_urls_hydro_daily_2022_2023_counts_13`, `test_urls_meteo_daily_2000_2001_counts_13` (1 yearly + 12) [boundary 2000/2001],
  `test_urls_meteo_without_subtype_raises_400` – **note**: an `HTTPException` raised inside `try … except ValueError` passes through (it is not a `ValueError`), 400.
- `test_urls_year_out_of_range_400` – `start_year=1951`, `end_year=2024` ok; `DataType` computed by `get_available_years` – since it returns the current year,
  and `le=2024`, the 400 validator is unreachable for `end_year`; reachable for `start_year < 1951`? `ge=1951` blocks that too -> branch 158-162 is **unreachable**.
  Do not test; record it in section 6.

### 4.18 `tests/unit/test_api_pmaxtp.py`

- `test_methods_lists_pot_and_amp`, `test_url_returns_pmaxtp_url_with_4_decimals`, `test_url_latitude_outside_poland_422` (schema `ge/le`),
  `test_data_proxies_imgw_json` (respx), `test_data_504_on_timeout`, `test_data_passes_through_imgw_status_code` (respx 403 -> 403), `test_data_502_on_connect_error`.

### 4.19 `tests/unit/test_web.py` (`api_client`; Jinja routes)

- `test_static_pages_render_200` – parametrize `/`, `/download`, `/download/hydro`, `/download/meteo`, `/download/pmaxtp`, `/stations`, `/map`;
  `text/html`, `title` in the content.
- `test_generate_hydro_urls_daily_2022_2023_13_links` (form POST), `test_generate_hydro_urls_semi_annual_without_param_gives_3_per_year`,
  `test_generate_hydro_urls_invalid_interval_shows_error`, `test_generate_hydro_urls_daily_2022_without_month_ok` (months generated in a loop).
- `test_generate_meteo_urls_monthly_1996_2000_deduplicates_to_one_link` – 5 years -> 1 URL (253-261). [pitfall 2]
- `test_generate_meteo_urls_hourly_opad_reports_error_per_year`, `test_generate_meteo_urls_invalid_subtype_error`.
- `test_generate_pmaxtp_renders_result` (respx), `test_generate_pmaxtp_http_error_renders_error_partial`, `test_generate_pmaxtp_invalid_method_error`.
- `test_hydro_stations_partial_search_and_limit` (respx cp1250), `test_hydro_stations_partial_error_on_http_failure`,
  `test_meteo_stations_partial_search`, `test_meteo_stations_partial_error`.
- `test_map_stations_filters_missing_coords_and_builds_summary` (respx JSON), `test_map_stations_error_returns_empty_list_with_error`.

### 4.20 `tests/unit/test_cli_main.py` (`cli`)

- `test_all_help_screens_exit_0` – parametrize: `--help`, `version --help`, `server --help`, `fetch --help`, `fetch hydro --help`, `fetch meteo --help`,
  `fetch current --help`, `fetch pmaxtp --help`, `fetch warnings --help`, `list --help`, `list stations --help`, `list datasets --help`, `list intervals --help`,
  `admin --help`, `admin keys/create/revoke/delete/stats --help`. The `store`, `series`, `pmaxtp` groups (help = command catalog descriptions)
  are already covered by `test_cli_store_project.py::test_help_texts_and_flags_are_the_catalog`. [pitfall 7; Typer wiring]
- `test_version_prints_package_version` – `__version__` in the output, not `1.0.0`. [regression]
- `test_server_command_delegates_to_uvicorn` – `monkeypatch.setattr("uvicorn.run", fake)`; assertion on the arguments (host/port/reload). Covers the lines without starting the server.

### 4.21 `tests/unit/test_cli_list.py`

- `test_list_datasets_uses_current_year` – the output contains `f"1951-{datetime.now().year}"`. [pitfall 7]
- `test_list_datasets_filter_hydro_hides_meteo`, `test_list_intervals_prints_sections`.
- `test_list_stations_hydro_reads_csv_from_data_dir` (autouse `isolated_data_dir` + writing `hydro_stations_names.csv` with the header `id,name,river`),
  `test_list_stations_search_filters`, `test_list_stations_meteo_two_columns`, `test_list_stations_missing_file_exit_1`,
  `test_list_stations_invalid_type_exit_1`, `test_list_stations_unreadable_file_exit_1` (binary file).

### 4.22 `tests/unit/test_cli_admin.py` (`monkeypatch.setattr(settings, "api_keys_file", tmp_path/"keys.json")`)

- `test_keys_empty_message`, `test_create_writes_key_file_and_prints_key`, `test_keys_lists_created_key_truncated_id`,
  `test_revoke_by_prefix_sets_inactive`, `test_revoke_unknown_exit_1`, `test_delete_force_removes`, `test_delete_without_force_abort_on_n` (`input="n\n"`, exit 1),
  `test_delete_confirm_y_removes`, `test_delete_unknown_exit_1`, `test_stats_all_and_filtered`, `test_stats_empty_message`.

### 4.23 `tests/unit/test_cli_fetch.py` (`cli` + respx + `tmp_path`)

Since 3.0.0 `fetch hydro|meteo` go through the command catalog (`run_command`); their contract is pinned by `test_cli_fetch_store.py`
and `test_commands.py::test_fetch_hydro_mirrors_server_paths_and_reports_failures`: files in subdirectories mirroring the server paths
(two identical basenames from different folders coexist), writing via `.part` + `os.replace` (a failure leaves no complete file
and does not block a retry), a repeated download overwrites instead of "skipping", errors of individual files as messages. Still to add:

- `test_fetch_hydro_check_prints_plan_without_download` – `--check` prints `imgw-plan/1`, zero archive GETs.
- `test_fetch_hydro_year_range_semi_annual_without_param_downloads_3_per_year` – `--year 2020-2021 --interval polroczne_i_roczne` -> 6.
- `test_fetch_hydro_invalid_interval_reports_polish_error`.
- `test_fetch_meteo_monthly_synop_2023`, `test_fetch_meteo_daily_klimat_2000_yearly_file` [boundary], `test_fetch_meteo_hourly_opad_counts_failure`,
  `test_fetch_meteo_invalid_subtype_exit_1`.
- `test_fetch_current_hydro_prints_json` (respx), `test_fetch_current_output_file_written_utf8` (JSON with `ł`), `test_fetch_current_invalid_type_exit_1`,
  `test_fetch_current_http_error_exit_1`.
- `test_fetch_pmaxtp_writes_output`, `test_fetch_pmaxtp_invalid_method_exit_1`, `test_fetch_pmaxtp_http_error_exit_1`
  (note: the CLI does not validate the Poland bounds – pin in a comment).
- `test_fetch_warnings_meteo_prints`, `test_fetch_warnings_invalid_type_exit_1`, `test_fetch_warnings_http_error_exit_1`.

### 4.24 Store CLI (`tests/unit/test_cli_store_project.py`; replaces the former `test_cli_db.py`; the tests exist)

- registration of every `store`/`series`/`pmaxtp` command, help and flags from the catalog, the same options passed to the dispatcher;
- `store init`, `series build`, `store check --plan` + `store sync`, `pmaxtp sync`, `series export` produce the same paths
  and SHA as the Python API (fixed clock);
- `--check` uses `check_command` and writes nothing; a plan inside the store is rejected with a Polish message; invalid options with a Polish message;
- Ctrl+C reports cancellation and a partial report, a second Ctrl+C aborts immediately.

### 4.25 `tests/unit/test_reference_data.py` (respx + autouse `isolated_data_dir`)

- `test_fetch_stations_writes_three_csv_files` – respx: `HYDRO_STATIONS_CSV_URL`, `METEO_STATIONS_CSV_URL`, `HYDRO_MAP_API_URL`; headers `id,name,river` / `id,name` / `id,X,Y`;
  a station without coordinates is skipped in `locations`.
- `test_meteo_format_files_parses_listing_and_dedupes` – respx `respond(text='<a href="k_d_format.txt">…')` for 9 combinations, 404 for `terminowe/opad`.
- `test_fetch_descriptions_writes_files_and_skips_404`.
- `test_main_returns_1_on_connection_error` (respx `side_effect=httpx.ConnectError`) and `test_main_returns_0_happy_path` (`capsys` – "Done.").

### Test count summary

The 2.2.0 plan assumed ~230 new tests (~340 in total). In 3.0.0 the suite has 998 tests at 93% coverage (as of 2026-10-18, including the T25 contract in `tests/contract/`), of which the tests of the store,
the command catalog, projects, the CLI and the store REST (sections 4.9 and 4.24) were written as part of ADR-001.

---

## 5. Rollout order (phases = separate commits, each green)

| Phase | Scope | Commit (subject) | Expected coverage after the phase |
|---|---|---|---|
| 0 | Fix `test_urls.py:238,247`; fixtures in `conftest.py` (`make_zip`, `api_client`, `cli`; `isolated_data_dir` already exists); markers in `pyproject.toml` | `test: fix get_available_years tests and add shared fixtures (respx, TestClient, CliRunner)` | – |
| 1 | `test_url_builder.py`, additions to `test_models.py`, `test_parsers.py` (including 4.4), `test_stations.py`, `test_fetch.py`, `test_config.py` | `test: full coverage of url_builder, models, parsers, stations and fetch via respx` | – |
| 2 | ~~DB layer~~ – replaced by the store tests (section 4.9, done in 3.0.0) | – | – |
| 3 | `test_api_system.py`, `test_api_hydro.py`, `test_api_meteo.py`, `test_api_download.py`, `test_api_pmaxtp.py` | `test: REST API endpoints via TestClient without network` | – |
| 4 | `test_web.py` | `test: HTMX/Jinja web routes render with mocked data` | – |
| 5 | `test_cli_main.py`, `test_cli_list.py`, `test_cli_admin.py`, `test_cli_fetch.py` (store CLI: section 4.24, done) | `test: CLI via CliRunner - help, exit codes, fetch, admin` | – |
| 6 | `test_reference_data.py`; `--cov-fail-under=80` in `addopts`; update the numbers in `README.md` and the [Nogat development standard](https://github.com/Daldek/Nogat/blob/main/standards/DEVELOPMENT_STANDARDS.md) (standard 1.0) | `test: reference_data with mocks and an 80 percent coverage threshold` | >= 80% |

Each phase: `pytest -q --cov…` green, `ruff check src/ tests/` clean, `pyright src/imgwtools/` unchanged (tests are not checked by pyright).
The coverage column from the 2.2.0 plan (denominator 2586) is outdated; the 80% threshold is checked on the current code. Phases 3 and 5 can be split into two commits.

---

## 6. Risks and decisions for the owner to confirm

1. **respx as the standard for new tests** (it is in `[dev]`; we do not touch the 109 existing tests with `MagicMock`). Alternative: `httpx.MockTransport` –
   it would require injecting the transport into `httpx.Client(...)` in production code, which we do not want. **Recommendation: respx.**
2. **`get_available_years`** – the plan pins the current behaviour (ignored `interval`, 1951 for meteo) in tests with explicit `*_current_behaviour` names.
   Follow-up (a separate `fix:`): remove the `interval` parameter or use it (e.g. synop from 1960), possibly also accept `"hydro"/"meteo"` as a string.
   To decide: pin vs. fix before the tests.
3. **The `/stations` placeholder** (pitfall 6) – tests assert the shape (`StationList`, `count`, `limit/offset`), not the names. Follow-up: read from `settings.hydro_stations_file`
   like `imgw list stations`.
4. **Bugs found** (section 1) – 3.0.0 fixed `nazwa_stacji` vs `stacja`, `le=2024` in the API, `API_VERSION 1.0.0`, `JSONDecodeError`
   in `fetch_*` (now `IMGWDataError`) and `BadZipFile`; `clear_cache` disappeared with the DB layer. The plan **pins** the remaining items with a `# TODO` comment, so that a fix is a deliberate test change.
   To decide: which to fix before phase 3 (then the test asserts the correct behaviour right away).
5. **Coverage exclusions** – minimal proposal: `[tool.coverage.report] exclude_also = ["if __name__ == .__main__.:", "if TYPE_CHECKING:"]`
   (4 `__main__` blocks, 3 `TYPE_CHECKING` blocks). `run_server()` in `api/main.py` and `server` in `cli/main.py` are covered by monkeypatching `uvicorn.run`
   instead of being excluded. `reference_data.main()` is tested with respx + `capsys`. We do **not** exclude any module entirely – the section 2 arithmetic works without exclusions.
6. **Unreachable branch** `api/routes/download.py:158-162` (year range validation after `Query(ge=1951, le=2024)` – it will never trigger as long as `get_available_years`
   returns `(1951, current_year)`). It stays uncovered (5 lines) – or remove it in a follow-up.
7. **Protection against local data** – resolved: the autouse `isolated_data_dir` in `tests/conftest.py` switches `settings.data_dir` to an empty
   temporary directory in every test. The SQLite database no longer exists (3.0.0); store tests create roots only in `tmp_path`.
8. **Moving the CSV constants from `test_parsers.py` to `conftest.py`** – a small change to an existing file (an import instead of a definition). Alternative: keep
   a duplicate of the three rows in conftest. Recommendation: move.
9. **`--cov-fail-under=80` in `addopts`** – enable only in phase 6; with `-m 'not integration'` in `addopts`, make sure that `pytest -m integration` still
   works (an explicit `-m` overrides it).
10. **Integration tests against the real IMGW** – we do not add them (the marker is reserved). If the owner wants a URL smoke test (HEAD on `codz_2023.zip`),
    add a single file `tests/integration/test_imgw_live.py` with `@pytest.mark.integration` – outside the coverage arithmetic.
11. **Time and size** – the store CLI/REST files (`test_cli_store_project.py`, `test_api_store.py`) and the exports contract (`test_public_store_api.py`)
    are the largest, because they parametrize every command/route/symbol; the suite runs offline in a few tens of seconds.

---

## 7. Definition of done

```
.venv/bin/python -m pytest -q --cov=imgwtools --cov-report=term-missing
# expected: all tests passed (>= 109 old + new), TOTAL >= 80% (plan: ~89%),
# no warnings about unhandled HTTP requests (respx assert_all_mocked),
# no 'Missing' in core/url_builder.py, models.py, _parsing/common.py, config.py, api/schemas.py

.venv/bin/python -m pytest -q                      # after phase 6: passes the --cov-fail-under=80 threshold
.venv/bin/python -m pytest -q -m integration       # "no tests ran" (no integration tests) or opt-in only
.venv/bin/ruff check src/ tests/                   # All checks passed!
.venv/bin/ruff format --check src/ tests/          # no changes
npx -y pyright src/imgwtools/                      # 0 errors (unchanged relative to HEAD)
git status                                         # changes only in tests/, pyproject.toml, README.md, docs/ (none in src/ except possible follow-ups from section 6)
```

Additionally: in `README.md` (the tests section) and the [Nogat development standard](https://github.com/Daldek/Nogat/blob/main/standards/DEVELOPMENT_STANDARDS.md) (standard 1.0) update the test count and percentage;
in `docs/PROGRESS.md` an entry about reaching the threshold.
