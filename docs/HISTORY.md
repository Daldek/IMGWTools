# IMGWTools (now Obserwator) - Release history and closed work

Archive: release history, cross-project analysis, closed backlog items and working notes moved from [PROGRESS.md](PROGRESS.md) with unchanged content (Nogat standard 1.0, DOC-6.1: PROGRESS holds only the current state). Full list of changes: [CHANGELOG.md](CHANGELOG.md).

## Released versions

| Version | Date | Scope |
|--------|------|--------|
| v3.0.0 | 2026-10 | **Versioned data store** (ADR-001): `imgwtools.store`, meteo parsers, Parquet series, `stations.geojson` catalog, PMAXTP per cell, `imgw-project/1` projects; **one catalog of 37 commands** (ADR-002): `imgw-result/1` envelope, pagination, error code registry, CLI and REST generated from the catalog, problem+json; **ČHMÚ provider** (ADR-003): registry of 17 datasets from two providers (`cz.chmi.*`), freshness from the listing, canonical content and observation registry, station catalog with SPA thresholds, quality and flags in series, restoring pins by content; **AI agent support** (ADR-004): `AGENTS.md`/`llms.txt`, English descriptions, side-effect metadata, MCP server (`imgw mcp`, `/mcp`), `GET /llms.txt`; **breaking:** `imgw fetch`/`imgw list` → catalog groups, new REST routes, `station_id` → `station`/`station_code`, `download_*` → `DownloadResult`, removal of the SQLite cache and `core/url_builder`. Details: `docs/CHANGELOG.md` |
| v2.2.0 | 2026-08 | License (year, PEP 639), manual CLA process, IMGW-PIB reference data module (`reference_data.py`), removal of IMGW data from the repo, **removal of legacy `core/imgw_spatial.py`** (breaking: extras `[spatial]` → `[pandas]`, `StationMap` removed) |
| v2.1.1 | 2026-07 | Parsers: auto-detection of delimiter/encoding (UTF-8 BOM)/quotes; meteo URLs consistent with the IMGW server; pyright compatibility; documentation audit |
| v2.1.0 | 2026-01 | Python 3.12+, code modernization (ruff fix), DEVELOPMENT_STANDARDS.md (since removed; see the Nogat standard) |
| v2.0.1 | 2026-01 | Fix import error (lazy load db module) |
| v2.0.0 | 2026-01 | API refactoring, new architecture |
| v1.0.0 | 2025-xx | First stable release |

---

## v3.0.0 — release details (2026-10-19)

Major release implementing ADR-001 (`docs/DECISIONS.md`) according to the plan `docs/superpowers/plans/2026-10-17-versioned-store.md` (tasks T01–T24) and the contract `docs/superpowers/specs/2026-10-17-versioned-store-design.md`. Full list of changes: `docs/CHANGELOG.md`.

- **Wave 0 (T01–T06):** `datasets.py` registry (`pl.imgw.*`, `archive_files`, `station_source_files`), `DownloadResult` in `download_*`, parsers in `_parsing/` (hydro moved from `db/`, new meteo `k_d`/`o_d` with flags), fixes to `stations.py` (`river_order`, `hydrographic_code`, the `rzeka` field), synthetic archives and recordings in `tests/fixtures/store/`, store types and exceptions.
- **Wave 1 (T07–T10):** writer with atomic no-replace publication and the `imgw-meta/1` sidecar, `summarize_coverage`, `imgw fetch` mirroring server paths, REST URLs from the registry.
- **Wave 2 (T11–T14):** `stations.geojson` catalog (Natural Earth outline of Poland, no GIS at runtime), `check_store`/`sync_store` with the `imgw-plan/1` plan, `imgw-series/1` Parquet series, PMAXTP per cell.
- **Wave 3 (T15–T16):** public read API (read-only, problems reported) and `imgwtools.testing.build_fixture_store`.
- **Waves 4–5 (T17–T19):** CSV export with IMGW-PIB attribution, `commands.py` command catalog, `imgw-project/1` projects.
- **Wave 6 (T20–T21):** CLI `imgw store|series|pmaxtp|project` generated from the catalog, store REST behind `IMGW_STORE_ROOT` and a write token.
- **Wave 7 (T22–T24):** removal of the SQLite cache without shims (`db/` package, CLI command, `/api/v1/hydro/data`, settings, extra), a single export list `imgwtools.__all__`, the `[store]` extra, version 3.0.0, `docs/CHANGELOG.md` and documentation update.

**Owner's decision (2026-10-17):** the versioned store goes in now, as 3.0.0; the former "Obserwator 3.0" vision (`docs/OBSERWATOR_SPEC.md`) remains a future extension (renaming, providers) and no longer covers the v2 SQLite cache.

**State after ADR-001 (T25, 2026-10-18):** 998 passed (including the T25 contract in `tests/contract/`), coverage 93% (`pytest --cov=imgwtools`), `ruff check` clean, `pyright` 0 errors.

**ADR-002 — one command catalog and consistent interfaces** (plan `docs/superpowers/plans/2026-10-17-versioned-store.md`, tasks U01–U16; spec §13):

- **Waves 10–11 (U01–U04):** `ERROR_CODES` error code registry (`code`, `details`, `IMGWCancelledError`), `CommandResult`/`Page` envelope types and a single JSON converter; registry of 13 datasets with aliases and `YearsArg`/`MonthsArg`; live functions with `station`/`station_code`, `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`.
- **Waves 12–13 (U05–U08):** one slot grammar, `select_series`, `summarize_series`, `download_archives`, PMAXTP with `method="POT"`, `export_archive`/`export_series` (file or line stream), catalog of 35 commands with `command_schema` and pagination.
- **Waves 14–15 (U09–U12):** CLI and REST generated from the catalog (envelope on stdout, error JSON on stderr, exit codes, problem+json, `?check=true`), project following the ADR-002 conventions, web only on the public API.
- **Wave 16 (U13–U14):** removal of the old URL builders, `core/` and legacy routes; `imgwtools.__all__` consistent with §13.12; cross-interface contract Python = CLI = REST (`tests/contract/test_interface_contract.py`).
- **C01 (ADR-003, before the tag):** open domains of the `/1` contracts (dataset key, country, provider, license, WIGOS code, `location_source`), `content_sha256`/`content_form`, `imgw-observation/1` observation registry.
- **Wave 17 (U15):** release documentation (CHANGELOG with the §13.11 migration tables, README, CLAUDE.md, ARCHITECTURE, standards); README examples run once (Python and CLI live on a fresh store, reading on `build_fixture_store`, REST via `imgw server`); README and CLAUDE.md command tables consistent with `imgw commands schema` (one-off script).
- **Wave 17 (U16) — final gate and live regression:** new `tests/live/test_interfaces_live.py` (skipped without `IMGW_LIVE=1`, JSON report via `IMGW_LIVE_REPORT`). Run 2026-10-18T21:09:34Z (178.4 s, fresh store in tmpfs, `imgw server` on localhost, sequential requests): **42 passed** — each of the 35 commands consistent through Python, the installed `imgw` and REST (status, keys, slots, paths, streams byte for byte, store trees; local commands in REST → 404 `not_found`), 6 live errors consistent (`validation_error` 2/400, `not_found` 3/404, `store_unavailable` 8/503). Fix from the run: relative project pin paths in the envelope JSON no longer depend on the working directory (`_jsonable`). Runs interrupted by a failure on the IMGW side reported it identically (`source_unavailable`, exit 5 / HTTP 502); the test repeats such a run after 20 s and 60 s. Gate: `pytest` 1377 passed, 42 skipped (live); `ruff check` and `ruff format --check` clean; `pyright` 0 errors. 1419 tests in total (`pytest --collect-only`).

**ADR-003 — ČHMÚ provider** (spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md`, plan C01–C10 in §16; by the owner's decision of 2026-10-19 in release 3.0.0, ADR-003 erratum D16):

- **Wave C1 (C02–C03):** provider registry (`ProviderDescriptor`, `providers`, `get_provider`) and 4 `cz.chmi.*` descriptors, `archive_files(stations=)`, §9.4 types, `write_archive` with provider fields from the registry, the canonical form `chmi-json/1` (`content_sha256`), a `content_unchanged` row and observation recording; ČHMÚ parsers (hydro JSON, meteo CSV, metadata, nginx listing) and synthetic files with fictitious WIGOS codes.
- **Wave C2 (C04, C06):** freshness from the directory listing (`check_store`/`sync_store` with `stations`, plan fields `station_code`, `signal`, `remote_listed_at`, `local_observation`, `requests`), `download_archives` with `not_published`, `chmi_recordings.json` recordings; ČHMÚ station catalog (`stations/versions/chmi_stations/`, SPA thresholds, outline of Czechia), per-provider readers (`iter_store`, `read_catalog`, `read_station_list`, `store_info().providers`).
- **Wave C3 (C05, C07):** ČHMÚ series with periods known per station (`stations[<code>].periods`, `summarize_coverage(station_periods=)`), quality and flag columns in Parquet, CSV and JSONL, provider attribution in exports; catalog of 36 commands (`datasets providers`, the `provider` and `stations` options, `data_commands(provider=)`), `find_stations` for ČHMÚ, the title "Źródło danych niedostępne" ("Data source unavailable"), web IMGW-PIB only.
- **Wave C4 (C08):** projects with ČHMÚ tasks and restoring by content (`restored_by_content`, `content_match`, `pin_restored_by_content`, `get_project_status(on_notice=)`), test store `build_fixture_store(variant="complete_pl_cz")`.
- **Wave C5 (C09):** IMGW-15..19 contract `tests/contract/test_chmi_contract.py` (68 tests, Python/CLI/REST/MCP parity) and live test `tests/live/test_chmi_live.py` — run 2026-10-19: 26 passed in 77 s, 124 requests, 31.5 MB (stations `0-203-1-001000`, 2024–2026 with an unpublished 2026, and `0-203-0-11799`); fix from the run: `details.value` in `series select` as a list. Full gate (covers A01–A05): `pytest` 2129 passed, 79 skipped (live); `ruff check` and `ruff format --check` clean; `pyright` 0 errors. Live IMGW-PIB regression (`tests/live/test_interfaces_live.py`, 37 commands and the MCP leg): 53 passed in 103 s.

**ADR-004 — AI agent support** (spec `docs/superpowers/specs/2026-10-19-agent-support-design.md`, plan A01–A06 in §11):

- **Wave C4 + A1 (A01):** English descriptions of the catalog, groups, errors and datasets (`help_en`, `description_en`, `rules_en`, `title_en`), `command_schema(lang=)`, `IMGW_LANG` in the CLI (also Typer/Click elements), `Accept-Language` in REST, side-effect metadata (`writes`, `network`, `operation_id`, `env_root_when`).
- **Wave A2 (A02, A03):** `agent_guide`, the `commands guide` command (the 37th), derived files `AGENTS.md` and `llms.txt` with a drift test; MCP adapter `src/imgwtools/mcp/` (extra `imgwtools[mcp]`, modes `read`/`write`/`http`).
- **Wave A3 (A04, A05):** cleanup of legacy messages (help of `imgw admin`, `version`, `server`, OpenAPI field descriptions, `reference_data`, HTML pages outside OpenAPI; a repeated scan added items 34–37 of spec §7.2 and additions to §7.3 — erratum A04); `imgw mcp`, `/mcp` (`IMGW_MCP_ENABLED`, `IMGW_MCP_ALLOWED_HOSTS`), `GET /llms.txt`, Docker image on Python 3.12 with `.[api,mcp]` and `location = /mcp` in nginx (image built and checked 2026-10-19: `/health`, `/llms.txt`, `initialize` on `/mcp`).
- **Wave A4 (A06) and C10:** release documentation (CHANGELOG, README with ČHMÚ and agent sections, CLAUDE.md, ARCHITECTURE, standards, PRD, RULES), errata to ADR-001 and ADR-002 according to the "Impact" sections of ADR-003 and ADR-004, ADR-003 erratum D13, ADR-004 status in the index, `[ADR-003]`/`[ADR-004]` notes in spec 2026-10-17 §13 and `[ADR-004]` in spec 2026-10-18 §9.3, "3.1.0" → 3.0.0 in the ČHMÚ spec (with historical context); README and CLAUDE.md command tables consistent with `imgw commands schema` (one-off script); ČHMÚ examples run once offline on `complete_pl_cz` and live (opendata.chmi.cz), MCP examples — stdio configuration (also `--allow-writes`, `--lang en`, the `uvx` variant) and `/mcp` over HTTP — via the SDK client, Docker example on an image built with `docker compose build`. `AGENTS.md` and `llms.txt` not regenerated (catalog texts unchanged); drift test and full `pytest`: 2129 passed, 79 skipped (live).

**Compatibility fixes for Archiwista before the tag** (compatibility audit of 3.0.0 against Archiwista's requirements and review of `cb6af4f`, owner's decision 2026-10-19; branch `fix/archiwista-compat-2` from `develop` (then `slave`)):

- **Publication rollback:** after an error or Ctrl+C, `_publish_dir` no longer removes the hard-linked data files — a concurrent write of the same bytes could have taken them over and committed them with its own sidecar, and removing them left a committed version without its main file (`missing_file`, `IMGWDataError` for the slot); the interrupted publication stays, and only empty directories created by the write are removed. Regression `test_failed_commit_keeps_files_a_concurrent_writer_committed` (EIO, Ctrl+C). ADR-001 erratum 2026-10-19.
- **Hard-link requirement:** the `imgw-store.json` marker stays on `os.link`; README, ARCHITECTURE, CHANGELOG and the errata describe the requirement (FAT/exFAT, some NAS and FUSE, the macOS SMB client → `not_atomic`; the same requirement as Kartograf's store, its ADR-036) and the manual removal of an interrupted publication that a retry under the same label will not complete (station catalog, PMAXTP, an archive without `Last-Modified` retried on another day). CHANGELOG: the `[Unreleased]` section merged into `[3.0.0]`.
- **B — `meteo_kind`:** the IMGW-PIB catalog gives `climate`/`precipitation` from the current series `pl.imgw.meteo_climate_daily`/`pl.imgw.meteo_precip_daily`, `check_catalog` detects the change (cherry-pick `e77a6f9` from `fix/archiwista-compat`). ADR-001 erratum 2026-10-19.
- **D — flat download regression:** daily and sub-daily `2001_01_k.zip` in separate server paths and slots (cherry-pick `c280088`).
- Gate (offline, network blocked by a proxy): `pytest` 2134 passed, 79 skipped (live); `ruff check` and `ruff format --check src/ tests/` clean; `pyright` 0 errors.

## v2.2.0 — release details (2026-08-22)

Minor release — 20 commits on the `develop` branch on top of v2.1.1, including breaking changes (removal of the legacy spatial, api and datastore modules).

- **License:** corrected year in `LICENSE`; license metadata compliant with PEP 639 in `pyproject.toml` (`license = "MIT"`, `license-files`).
- **CLA process:** manual CLA process — `docs/CLA.md`, `CONTRIBUTING.md`, `CONTRIBUTORS.md`, PR template.
- **IMGW-PIB reference data:** IMGW data removed from the repository (`36ea672`); new module `src/imgwtools/reference_data.py` for downloading it on demand (`python -m imgwtools.reference_data`); `data/shp` untracked and ignored.
- **README:** new section on data sources and attribution.
- **Parsers:** documentation notes on extreme-value processing in `parse_semi_annual_csv`.
- **Tests:** fictitious test station "San Escobar" (123456789) instead of real IMGW data in fixtures.
- **Breaking: removal of `core/imgw_spatial.py`** — the legacy module (dead imports, pyright errors) removed; extras `[spatial]` renamed to `[pandas]` (`pyproj`/`pyshp` dependencies dropped). Anyone installing `imgwtools[spatial]` or importing `StationMap` must update their code — the functionality has no direct replacement in this release.
- **Breaking: removal of `core/imgw_api.py` and `core/imgw_datastore.py`** — classes marked DEPRECATED since 2.0.0 (`HYDRO`, `SYNOP`, `METEO`, `WARNINGS`, `PMAXTPAPI`, `DataDownloader`) removed; replacements in the public API: `fetch_hydro_current`, `fetch_synop`, `fetch_warnings`, `fetch_pmaxtp`, `download_hydro_data`, `download_meteo_data`. Only `url_builder.py` remained in `core/`.
- **Documentation and code style (2026-08-22):** `ruff format` ran over the whole repository (19 files); all docstrings in `src/` rewritten to the NumPy convention, and the `D` rules (pydocstyle, `convention = "numpy"`, without `D401`) enabled in `pyproject.toml` as a permanent lint gate (`tests/**` exempt). `docs/DEVELOPMENT_STANDARDS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/RULES.md`, `CLAUDE.md` and `README.md` corrected to the actual state of the code. Verification: **109 passed**, `ruff check` clean, `ruff format --check` clean, `pyright` 0 errors, coverage **23%** (`pytest --cov=imgwtools`).

**Final state of v2.2.0:** 109 passed, `ruff check` clean, `pyright` 0 errors (verification as for v2.1.1 below).

**Status:** prepared on the `develop` branch, commit `release: v2.2.0`; awaiting merge into `main` (then `master`) (no tagging/publishing at this stage).

## v2.1.1 — release details (2026-07-06)

### 🐛 Bugfix: handling inconsistent IMGW archive formats in the parsers (2026-07-05)

IMGW archival CSV files (`dane_hydrologiczne`) differ in format between years in **three** respects. The parsers in `src/imgwtools/db/parsers.py` assumed a single format (semicolon + CP1250), so most years did not parse at all. All three problems fixed:

1. **Delimiter** — most years use a comma with quotes, some (e.g. 2023) a semicolon; some files have an extra header row with column codes. The hardcoded `delimiter=";"` caused `parse_zip_file` to **silently return 0 records** for comma years. → helper `_detect_delimiter()` (per file, from the first non-empty line; tie → semicolon).
2. **Encoding** — CP1250 is the standard, but `codz_2023.zip` (daily, annual file) is in **UTF-8 with BOM**; the parser raised `UnicodeDecodeError`. → helper `_decode_content()` (BOM → `utf-8-sig`; then the requested encoding is tried with a UTF-8 fallback).
3. **Quotes** — in the **2024** daily and monthly files every line is wrapped in an outer quote with doubled quotes inside (`"149180020,CHAŁUPKI,...,""2024"",..."`), so `csv.reader` saw a single field and the parser silently returned 0 records. → helper `_iter_rows()` (a single-field row containing the delimiter is parsed again).

A leading space in the station code and the header row are handled by the existing safeguards (`_safe_int`, `.strip().strip('"')`).

**Tests:** `tests/unit/test_parsers.py` — 28 tests (delimiter, encoding, quotes, end-to-end via `parse_zip_file`). After this fix the suite had 103 tests; the final count for the whole v2.1.1 release is **109** (see the meteo URL fix below). `ruff check src/ tests/` and `ruff format --check` (then only for changed files — since 2026-08-22 formatting covers the whole repository) — clean; along the way 13 pre-existing lint errors in old test files were fixed (unused imports, import sorting).

**Verification on real data (2026-07-05, record counts):**

| File | Format | Before (2.1.0) | After the fix |
|------|--------|---------------|-------------|
| polr_Q_2020 | comma, CP1250 | 0 | 6007 |
| polr_Q_2023 | semicolon, CP1250 | 6014 | 6014 |
| polr_Q_2024 | comma, CP1250, header | 0 | 6198 |
| mies_2019–2022 | comma, CP1250 | 0 | 29,802 – 30,171/year |
| mies_2023 | semicolon, CP1250 | 29,805 | 29,805 |
| mies_2024 | comma, CP1250, **quoted lines** | 0 | 32,408 |
| codz_2020_01, codz_2022_06 | comma, CP1250 | 0 | 24,913 / 24,881 |
| codz_2023 | semicolon, **UTF-8 with BOM** | `UnicodeDecodeError` | 301,994 |
| codz_2024 | comma, CP1250, **quoted lines** | 0 | 326,845 |

**Other changes as part of the release preparation:**
- version bumped to **2.1.1** (`_version.py`, `pyproject.toml`); updated `CLAUDE.md` (version, tests, notes on the CSV format) and `README.md` (format note, test counts, `db/parsers.py` coverage 78%),
- `.gitignore`: added `.coverage`, `dist/`, `.python-version`, SQLite database files,
- fixed pre-existing lint errors in `tests/` (ruff --fix).

**Status:** released in **v2.1.1** (patch — bug fixes, no public API changes).

### 🔧 Typing: Pylance/pyright compatibility (2026-07-05)

Pylance in VSC reported errors in `db/parsers.py` (and more broadly). A `pyright` check (the Pylance engine) on the project venv confirmed: **136 errors** in `src/`. After the fixes: **0 errors**.

- **`Field(None, ...)` → `Field(default=None, ...)`** in 46 pydantic model fields (`models.py`, `db/models.py`, `api/schemas.py`, `stations.py`). Pyright does not recognize a positional default with the `Field` overloads in pydantic 2.12 — optional fields looked required (errors "Arguments missing for parameters latitude, longitude"). Change with no runtime impact.
- **`db/parsers.py`**: explicit type narrowing — `not isinstance(content, str)` (also handles bytearray/memoryview better than the old variant), `or` conditions instead of `all([...])` (pyright does not narrow through `all`). Removed the `int | None` and `memoryview.lstrip` errors.
- **`db/__init__.py`**: imports under `TYPE_CHECKING` for names loaded lazily via `__getattr__` — Pylance sees the symbols and offers completions, runtime unchanged (lazy loading preserved).
- **`cli/db.py`**: `isinstance` narrowing in the record display branches; **`api/routes/hydro.py`**: annotation `list[HydroDailyDataPoint | HydroMonthlyDataPoint]` for `data_points` (list invariance).
- **`pyproject.toml`**: new `[tool.pyright]` section (venvPath/venv + ignore for the legacy core); **`.vscode/settings.json`** (local configuration, not tracked in the repo) pointing to the `.venv` interpreter (without it Pylance analyzes the package from the old global pyenv 2.0.1).

**Done 2026-08-22 (v2.2.0):** the legacy modules `core/imgw_spatial.py`, `core/imgw_api.py` (DEPRECATED since 2.0.0) and `core/imgw_datastore.py` (dead `wget` import) were removed; `[tool.pyright].ignore` is no longer needed. Only `url_builder.py` remained in `core/`.

### 🐛 Bugfix: meteo URLs inconsistent with the actual IMGW server structure (2026-07-05)

Functional GUI verification (server run locally, all routes + forms + static files) showed that the pages, map, station list and PMAXTP work, but **`build_meteo_url` generated dead links (404)** — the structure of meteo files on the IMGW server differs from the one described in the documentation. Directory listings were verified live:

| Interval | Subtype | Actual files | Previously generated |
|---|---|---|---|
| miesieczne (k/o/s) | ≤2000 | **one file per 5-year folder** `{folder}_m_{x}.zip` | `{year}_{x}.zip` → 404 |
| dobowe/terminowe | climate, precipitation | `{year}_{x}.zip` (≤2000), `{year}_{mm}_{x}.zip` (2001+) | ✓ correct |
| dobowe/terminowe | synop | **per-station files** `{folder}_{code}_s.zip` | `{year}_{mm}_s.zip` → 404 |
| terminowe | precipitation | **dataset does not exist** | `{year}_{mm}_o.zip` → 404 |

Additionally, the 5-year folder grids start differently per subtype: climate `1951_1955`, precipitation `1950_1955`, synop `1960_1965` (a 6-year folder).

**Fix (`core/url_builder.py`):**
- `_get_meteo_folder(year, subtype)` — folder grid dependent on the subtype,
- miesieczne: file name `{folder}_m_{x}.zip` (covers both periods),
- synop dobowe/terminowe, terminowe precipitation, synop <1960 → a readable `ValueError` instead of a dead link (the GUI shows the message in the error list),
- GUI (`web/app.py`): link deduplication (years ≤2000 map to a shared 5-year file).

**Verification:** 6 new URL patterns checked with HEAD on the IMGW servers — all **200 OK** (incl. `1996_2000_m_s.zip`, `1950_1955_m_o.zip`, `1960_1965_m_s.zip`). GUI form: correct links + error message for daily synop. Tests: `test_urls.py` 22→28 (**full suite: 109 passed**). Updated the meteo structure descriptions in README.md and CLAUDE.md.

### 📚 Pre-release documentation audit (2026-07-05)

Full review of the documentation against the code (subagent + manual verification). Unified for v2.1.1:
- version 2.1.1 everywhere (removed the leftover 2.0.0 in `ARCHITECTURE.md`, 1.0.0 in `PRD.md`),
- test count **109** and test status consistent across README/CLAUDE/PRD/DEVELOPMENT_STANDARDS,
- `ARCHITECTURE.md` — updated CSV parsing section (auto-detection of delimiter/encoding/quotes),
- `README.md` — corrected map data source (`hydro-back.imgw.pl/map/stations/hydrologic`, previously wrongly `danepubliczne.imgw.pl/api/data/hydro`),
- type checker `mypy` → `pyright` in `DEVELOPMENT_STANDARDS.md` and in the "Commands" section; coverage threshold unified at 80% (`RULES.md`/`PRD.md`/`DEVELOPMENT_STANDARDS.md`); added `test_parsers.py` and the `develop` branch to the relevant lists.

**Final state of v2.1.1:** 109 passed, `ruff check` clean, `pyright` 0 errors.

### 🚀 Release finalization (2026-07-06)

- Removed the `[tool.mypy]` section and the `mypy>=1.6` dependency from `pyproject.toml` — the project uses **pyright** only (`[tool.pyright]`).
- Built fresh `dist/` artifacts for **2.1.1** (`python -m build`, hatchling backend); removed the old 2.0.1 wheels.
- Changes merged from the `develop` branch into `main`.

---

## Cross-Project Analysis (2026-01-21)

An integration analysis of 4 repositories was carried out: **Hydrograf**, **Hydrolog**, **Kartograf**, **IMGWTools**.

### Dependency map

```
HYDROGRAF (main application)
    ├── IMGWTools (IMGW data) ← THIS PROJECT
    ├── Kartograf (GIS data)
    └── Hydrolog (hydrological calculations)
            ├── IMGWTools (required) ← THIS PROJECT
            └── Kartograf (optional)
```

### Role of IMGWTools

IMGWTools is a **base library** used by:
- **Hydrograf** - directly (IMGW data, PMAXTP)
- **Hydrolog** - as a required dependency (precipitation data for hydrological calculations)

### Problems found in IMGWTools

| Problem | Status | Priority |
|---------|--------|-----------|
| Python `>=3.11` (other projects `>=3.12`) | ✅ Fixed (v2.1.0) | - |
| Uses `ruff` (others use `black+flake8`) | 🟡 Informational | LOW |
| Uses `hatchling` (others use `setuptools`) | 🟡 Informational | LOW |
| No DEVELOPMENT_STANDARDS.md | ✅ Fixed (v2.1.0) | - |

### Code standards - comparison

| Aspect | IMGWTools | Hydrolog | Kartograf | Compatibility |
|--------|-----------|----------|-----------|----------|
| Python | >=3.12 | >=3.12 | >=3.12 | ✅ |
| Line length | 88 | 88 | 88 | ✅ |
| Formatter | ruff | black | black | ⚠️ |
| Build | hatchling | setuptools | setuptools | ⚠️ |

### Recommendations

1. ~~**[CONSIDER]** Raise Python to `>=3.12` for consistency with other projects~~ ✅ Done (v2.1.0)
2. ~~**[BACKLOG]** Create DEVELOPMENT_STANDARDS.md (copy the format from Hydrolog)~~ ✅ Done (v2.1.0)
3. **[INFO]** Using `ruff` instead of `black+flake8` is OK (modern approach)

### Full documentation

Detailed cross-project analysis: `Hydrograf/docs/CROSS_PROJECT_ANALYSIS.md`

---

## Backlog — closed items

_Open backlog items are in [PROGRESS.md](PROGRESS.md), section "Next". Closed items moved without changes are below._

### Versioned store (after 3.0.0)

- [x] T25 — final contract suite (`tests/contract/`): offline state machine HEAD→plan→sync→series→catalog→CSV→project→verify/restore, CLI = API path/SHA parity (done 2026-10-18).
- [x] **C01 before the v3.0.0 tag:** opening the domains of the `/1` contracts to further providers (`dataset`, `country`, `provider`, `license.id`, WIGOS station code, `location_source` values), optional canonical-content fields `content_sha256` and `content_form` in `imgw-meta/1` and in `files[]` of `imgw-project/1`, and the `imgw-observation/1` observation registry (`observations/` directory in the archive slot, `kind="observation"` entries in the scan, internal publication of observations) — with no change to IMGW behavior or bytes (done 2026-10-18, commit `549795c`; calling observation recording in `write_archive` belongs to C02).
- [x] **ČHMÚ provider (Czechia, opendata.chmi.cz)** — ADR-003 and spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md` (plan C02–C10), in release 3.0.0 (erratum D16): `cz.chmi.hydro_daily`, `cz.chmi.meteo_daily`, station lists and the `cz.chmi.stations` catalog with SPA thresholds, freshness from the listing, canonical content `chmi-json/1` with the observation registry, ČHMÚ quality and flags in series, restoring pins by content; IMGW-15..19 contract and live test (done 2026-10-19, C02–C10). Meets Archiwista's requirements IMGW-15..19 (v0.6 "PL + CZ").
- [x] **Writing to the store on macOS and Windows** — version publication following Kartograf's model (hard links, the sidecar commits the version; ADR-001, erratum 2026-10-19) instead of `renameat2`, which is available only on Linux; directory `fsync` skipped on Windows (done 2026-10-19; checked on Linux, Windows simulated by refusing `os.open` on a directory).

### AI agent support (after 3.0.0)

- [x] **Agent surfaces in English (AGI-9.2, ECO-042, DEV-2.3, AGI-9.1, ADR-006)** — message catalog `imgwtools.messages` (`Text(en, pl)` under the key `<area>.<name>`, `message()`, `Message`, `localize()`, `reason()`; guard test `tests/unit/test_messages.py`), `detail` of all exceptions and item errors, notices, progress and plan lines, CLI (last stderr line in English, help and lines per `IMGW_LANG`), MCP server in English only (`imgw mcp --lang` removed), `command_schema`/`list_commands`/`agent_guide` in English by default, `AGENTS.md` and `llms.txt` in English, REST without `Accept-Language` in English (`Content-Language`, `Vary`), OpenAPI in English (model field descriptions too), dataset titles and descriptions of commands, options, rules and groups as catalog entries with English main text (`help_en`, `description_en`, `rules_en`, `title_en` removed), web GUI pages in the `web` area (the GUI stays in Polish). Done 2026-10-24 in nine commits on the `chore/nogat-2.1` branch; after the last one no Polish literal remained outside the catalog.

### Data output (after 3.0.0)

- [x] **Data output convention (ECO-051, DEV §19, ADR-007)** — branch `feature/data-output` (commits from `1dc2b61`; no push, tag or merge): three output targets with one name across the library, CLI, MCP and guide (`output_dir`/`--output-dir`/`-o` plain files, `root`/`--root` store, `output`/`--output` a single export file, `--force`), default store `<data_dir>/imgw` and `IMGW_ROOT` instead of `IMGW_STORE_ROOT`, plain mode of `datasets download`, `store sync`, `pmaxtp sync` and exports (preflight with `details.paths`, staging `.imgw-incoming/`, `os.replace`, `--force`, `--check` with `write|replace|conflict`, `files[]` with streaming SHA-256), the `imgw-store.json` marker with `tool`, `created_at` and `producer_version` created by the first write, nested stores by marker names, statuses `new`/`unchanged`, `imgw mcp --allow-dir`; tests: REST and MCP refusals (DEV-19.3), sidecar core (DEV-19.16), marker contract (DEV-19.12), SIGINT and SIGTERM through real commands (DEV-19.7); smoke `store sync` in the default root without a prior store (done 2026-10-25).

### Infrastructure and code quality

- [x] ~~Fallback station lists hardcoded in the code (`api/routes/hydro.py`, `api/routes/meteo.py`)~~ — routes removed in 3.0.0 (ADR-002); station lists come from `find_stations` using the IMGW CSV.

### Done (archive)

- [x] CLI (`imgw` command)
- [x] REST API (FastAPI)
- [x] Web GUI (HTMX + Jinja2)
- [x] PMAXTP data
- [x] Current hydro/meteo/synop data
- [x] Archive data download
- [x] Warnings
- [x] ~~SQLite cache (optional)~~ — removed in 3.0.0 (ADR-001 D5), replaced by the versioned store
- [x] Versioned data store: 1:1 archives with sidecars, freshness plan, Parquet series, `stations.geojson` catalog, PMAXTP per cell, CSV export, projects, CLI and REST (v3.0.0)
- [x] One command catalog for Python, CLI and REST: `imgw-result/1` envelope, pagination, error code registry, `command_schema`, CLI and REST generated from the catalog, cross-interface contract (ADR-002, v3.0.0)
- [x] ČHMÚ provider in the registry, store, command catalog and projects (ADR-003, v3.0.0)
- [x] AI agent support: `AGENTS.md`/`llms.txt`, English catalog descriptions, side-effect metadata, MCP server `imgw mcp` and `/mcp`, cleanup of legacy messages (ADR-004, v3.0.0)
- [x] Daily meteo parsers `k_d`/`o_d` with missing-value flags (v3.0.0)
- [x] Public test store builder `imgwtools.testing` for Archiwista and Retman (v3.0.0)
- [x] Raising Python to `>=3.12` for consistency with other projects (cross-project recommendation, v2.1.0)
- [x] DEVELOPMENT_STANDARDS.md in the Hydrolog format (cross-project recommendation, v2.1.0)


---

## Commands

```bash
# Tests (always via the project venv)
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=imgwtools

# Linting and formatting
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/

# Type checking (config: [tool.pyright] in pyproject.toml)
npx -y pyright src/imgwtools/

# Agent guide (derived files; after every change to the catalog, registries or templates)
imgw commands guide --format agents --lang pl --path AGENTS.md
imgw commands guide --format llms --lang pl --path llms.txt
```

---

## Git workflow

- **main** - default branch (stable)
- **develop** - development branch (v2.2.0)
- **feature/versioned-store** - versioned store and consistent interfaces, release 3.0.0
- **feature/chmi-agents** - ČHMÚ provider and AI agent support, release 3.0.0
