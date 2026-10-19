# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IMGWTools is a Python library and tools for downloading public data from IMGW (Polish Institute of Meteorology and Water Management). It provides four interfaces:
- **Python Library** - `pip install imgwtools` for integration with other projects
- **CLI** - Command-line tool for local data downloading
- **REST API** - FastAPI-based API (URL generation, live data, optional server-side store)
- **Web GUI** - HTMX + Jinja2 web interface

Since 3.0.0 (ADR-002) Python, CLI and REST share **one command catalog** of 35 commands (`imgwtools.commands`, `imgw commands schema`): one option name per parameter, one validation, one result envelope `imgw-result/1` and one closed error-code registry `ERROR_CODES`. CLI groups and REST routes are generated from the catalog; the web GUI calls public functions only.

**Key principle:** Data is NEVER stored on the server by default. The service generates direct links to IMGW servers, and users download data directly from IMGW.

**Optional feature:** versioned data store (ADR-001). An explicitly chosen directory (`--root`, `IMGW_STORE_ROOT`) keeps immutable, append-only versions of IMGW archives with SHA-256 sidecars, Parquet station series, a `stations.geojson` catalog and PMAXTP cells. There is no default location and no database.

**Version:** 3.0.0

## Installation

```bash
# Core library only (httpx, pydantic)
pip install imgwtools

# With CLI
pip install imgwtools[cli]

# With REST API server
pip install imgwtools[api]

# With the versioned store's Parquet series (pyarrow)
pip install imgwtools[store]

# Full installation (api, cli, pandas, store)
pip install imgwtools[full]

# For development
pip install -e ".[dev]"
```

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run API server
imgw server --reload

# Run tests / lint (always through the project venv)
.venv/bin/python -m pytest
.venv/bin/ruff check src/ tests/

# CLI examples (stdout = one-line JSON envelope imgw-result/1)
imgw version                                         # Show version
imgw server --host 0.0.0.0 --port 8000               # Run API server
imgw datasets list -k hydro                          # Dataset registry
imgw datasets files -d hydro/dobowe -y 2023 -m 1     # Archive URLs (no download)
imgw datasets download -d hydro/dobowe -y 2023 -m 1 -o dane   # Download archives
imgw stations find -k hydro -q wisla --limit 20      # Search station lists
imgw current hydro -s 150160180                      # Current hydro data
imgw current warnings -k meteo                       # Warnings
imgw pmaxtp fetch --lat 52.23 --lon 21.01            # PMAXTP data (method POT)
imgw store init --root /dane/imgw                    # Versioned store
imgw store sync --root /dane/imgw -d pl.imgw.hydro_daily -y 2024 --check   # Plan only
imgw series summary --root /dane/imgw -d hydro/dobowe -s 149180020
imgw commands schema --command "store sync"          # JSON Schema of a command
imgw store sync --schema                             # Same, via the command itself
imgw admin keys                                      # List API keys
imgw admin create --name "User1"                     # Create API key
imgw admin revoke <key_id>                           # Revoke API key
imgw admin delete <key_id>                           # Delete API key
imgw admin stats                                     # Show API key statistics
```

## Architecture

```
src/imgwtools/
├── __init__.py           # PUBLIC API - single __all__ (spec §13.12)
├── _version.py           # Version: 3.0.0
├── fetch.py              # PUBLIC: live data (fetch_*), PMAXTP, download_archives, download_*_data
├── models.py             # PUBLIC: Data models (PMaXTPData, HydroCurrentData, NormalizedRecord, ...)
├── stations.py           # PUBLIC: find_stations (live lists or store)
├── datasets.py           # PUBLIC: Dataset registry (13 descriptors), archive_files, YearsArg/MonthsArg
├── commands.py           # PUBLIC: Command catalog (35 commands), run_command, command_schema
├── coverage.py           # PUBLIC: summarize_coverage
├── project.py            # PUBLIC: imgw-project/1 manifests
├── exceptions.py         # PUBLIC: IMGWError hierarchy + ERROR_CODES registry
├── urls.py               # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
├── parsers.py            # PUBLIC: Parser re-exports (hydro, meteo, station lists)
├── testing.py            # PUBLIC: build_fixture_store, fixture_files (offline fixtures)
├── _jsonable.py          # Single JSON converter (envelope, relative store paths)
├── reference_data.py     # python -m imgwtools.reference_data (data/ reference files)
├── config.py             # Settings (pydantic-settings, IMGW_*)
├── _data/                # Poland border (Natural Earth) + packaged fixtures/recordings/contract schemas
├── _parsing/             # common.py, hydro.py, meteo.py, stations.py
├── store/                # Versioned store [Parquet: imgwtools[store]]
│   ├── types.py          # Dataclasses: StorePlan, CommandResult, Page, StoreEntry, ...
│   ├── writer.py         # init_store, write_archive (atomic, append-only)
│   ├── sync.py           # check_store, sync_store (listing + HEAD, imgw-plan/1)
│   ├── series.py         # check_series, build_series (Parquet)
│   ├── catalog.py        # check_catalog, build_catalog (stations.geojson)
│   ├── pmaxtp.py         # check_pmaxtp, sync_pmaxtp, read_pmaxtp
│   ├── reader.py         # store_info, iter_store, current_version, read_*, select/summarize_series
│   └── export.py         # export_archive, export_series (CSV/JSONL, file or line iterator)
├── api/                  # FastAPI REST API [optional: imgwtools[api]]
│   ├── main.py           # App entry point (/health, /api/v1, web router, static)
│   ├── routes/commands.py# Routes generated from command_schema() (x-imgw.rest)
│   ├── errors.py         # application/problem+json handlers, hide_server_paths
│   └── schemas.py        # HealthCheck
├── cli/                  # Typer/Click CLI [optional: imgwtools[cli]]
│   ├── main.py           # Entry point (imgw command): version, server, admin + catalog groups
│   ├── _dispatch.py      # ImgwGroup + register_catalog: the only CLI adapter of the catalog
│   └── admin.py          # API key management
└── web/                  # Web GUI (HTMX + Jinja2)
    ├── app.py            # Web routes
    ├── templates/        # Jinja2 templates
    └── static/           # CSS, JavaScript
```

### Public Library API

The public API is exposed via `from imgwtools import ...` (one `__all__`, also re-exported from the defining modules). The first object argument may be positional; every further argument is keyword-only. Station codes are always `str` (`station_code`).

**Live Data and Downloads:**
|Function|Description|
|---|---|
|`fetch_pmaxtp(latitude, longitude, *, method="POT")`|Get PMAXTP precipitation data (`PMaXTPResult`)|
|`fetch_hydro_current(*, station=None)`|Current hydro data (`HydroCurrentData`)|
|`fetch_meteo_current(*, station=None)`|Current meteo data (`MeteoCurrentData`)|
|`fetch_synop(*, station=None, station_name=None)`|Current synop data (`SynopData`)|
|`fetch_warnings(*, kind=None)`|Hydro/meteo warnings (`WarningData`; `None` = both)|
|`fetch_hydro_states(*, main_only=False)`|Hydro stations with coordinates and water state (`HydroState`)|
|`find_stations(*, kind, query, source="live", root=None)`|Search IMGW station lists (`StationListEntry`)|
|`download_archives(dataset, /, *, years, months, params, output)`|Download archives into a server-path tree (`DownloadReport`)|
|`download_hydro_data(interval, year, month, param)`|One hydro archive as `DownloadResult` (bytes in `.data`)|
|`download_meteo_data(interval, subtype, year, month)`|One meteo archive as `DownloadResult`|

Every live function has an `*_async` twin with identical arguments.

**Registry and URLs:**
|Function|Description|
|---|---|
|`datasets(*, kind=None)`|Dataset descriptors (`DatasetDescriptor`)|
|`get_dataset(dataset)`|Descriptor by key, slug or legacy alias|
|`archive_files(dataset, /, *, years, months=None, params=None)`|Archive files with URLs (`ArchiveFile`)|
|`build_pmaxtp_url(latitude, longitude, *, method="POT")`|PMAXTP API URL|
|`build_api_url(endpoint, /, *, station, station_name)`|IMGW real-time API URL|

**Versioned Store** (also in `imgwtools.store`):
|Function|Description|
|---|---|
|`init_store`, `open_store`, `store_info`, `iter_store`|Create/open/describe/scan a store|
|`check_store`, `sync_store`|Freshness plan (listing + HEAD) and download of new/missing archives|
|`check_series`, `build_series`|Parquet station series|
|`check_catalog`, `build_catalog`|`stations.geojson` catalog|
|`check_pmaxtp`, `sync_pmaxtp`, `read_pmaxtp`|PMAXTP grid cells|
|`current_version(root, /, *, slot)`|Current version of a slot (`archive:<key>:<file>`, `series:<key>`, ...)|
|`read_meta`, `read_archive`, `read_station_list`, `read_catalog`, `read_series_index`, `read_series`|Offline readers|
|`select_series`, `summarize_series`|Series selection and coverage|
|`export_archive`, `export_series`|CSV/JSONL export to a file or as a line iterator|

**Command Catalog:**
|Function|Description|
|---|---|
|`command_schema(command=None)`|JSON Schema of the catalog or one command (`x-imgw`: function, CLI, REST, rules)|
|`data_commands()`|Catalog entries (`DataCommand`)|
|`validate_command(command, /, *, options)`|Normalized options or `IMGWValidationError` with `details.option`|
|`format_command(command, /, *, options)`|Equivalent CLI command line|
|`run_command(command, /, *, options)`|Run a command → `CommandResult` (list commands → `Page`)|
|`check_command(command, /, *, options)`|Plan of a command without side effects → `CommandResult`|

**Projects:** `init_project`, `open_project`, `set_project_store`, `add_project_task`, `remove_project_task`, `check_project`, `download_project`, `get_project_status`, `verify_project`.

**Data Models:**
|Model|Description|
|---|---|
|`PMaXTPData`|Precipitation quantiles (ks, sg, rb) with `get_precipitation(duration, prob)`|
|`PMaXTPResult`|Complete PMAXTP result with metadata|
|`HydroCurrentData`, `MeteoCurrentData`, `SynopData`|Current measurements (`station_code`)|
|`WarningData`|Weather/hydro warning (`kind`, `event`, `level`, ...)|
|`HydroState`|Station with coordinates and `water_state`|
|`StationListEntry`|Station list row (`kind`, `station_code`, `name`, ...)|
|`NormalizedRecord`, `Measurement`|Normalized archive/series record with value flags|
|`CommandResult`, `Page`|Result envelope (`imgw-result/1`) and list page (`items`, `total`, `limit`, `offset`)|

**Exceptions** (every `IMGWError` has `code` from `ERROR_CODES` and `details`):
|Exception|Default code|Description|
|---|---|---|
|`IMGWError`|`internal_error`|Base exception|
|`IMGWValidationError`|`validation_error`|Input validation errors (e.g. coords outside Poland)|
|`IMGWConnectionError`|`source_unavailable`|Connection/timeout/HTTP errors|
|`IMGWDataError`|`data_error`|Data parsing errors|
|`IMGWStoreError`|`store_unavailable`|Bad/unsupported store root (`not_found` for missing versions)|
|`IMGWStoreConflictError`|`conflict`|Collisions, races, non-atomic filesystems|
|`IMGWStoreDependencyError`|`missing_dependency`|pyarrow missing|
|`IMGWProjectError`|`validation_error`|Project manifest/lock/pins|
|`IMGWCancelledError`|`cancelled`|Cancelled operation|

**Parsers:** `parse_zip_file(zip_data, interval)`, `parse_daily_csv`, `parse_monthly_csv`, `parse_semi_annual_csv`, `parse_stations_csv(content, /, *, kind)`, `parse_meteo_climate_daily`, `parse_meteo_precip_daily`, `normalize_archive`, `IMGW_ENCODING` (CP1250).

### Key Module: `commands.py`

The command catalog is the single source of options, validation, help texts and result types:
- `_CATALOG` — 35 `DataCommand` entries (spec §13.3), each calling exactly one public function
- `command_schema()` — JSON Schema per command with `x-imgw` (`function`, `check`, `result_type`, `cli.flags`, `rest.method/path/server_options/local_options`, `rules`), plus `groups`, `errors`, `exit_codes`
- `run_command`/`check_command` — dispatch by `inspect.signature`, paging (`limit`/`offset`) for the 11 list commands, notices deduplicated in the envelope
- CLI (`cli/_dispatch.py`) and REST (`api/routes/commands.py`) are generated from `command_schema()`; never add hand-written commands there

## Data Flow

```
User → CLI/API/Web → command catalog → public functions → IMGW servers → User's computer
                                              ↓
                             (URLs only, unless an explicit --output/--root/IMGW_STORE_ROOT)
```

No data is stored on our server by default - station lists and live data are fetched directly from IMGW.

## External Data Sources

### Station Lists (CSV)
- **Hydro stations**: `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/lista_stacji_hydro.csv`
  - Format: `ID, nazwa, rzeka (id_cieku), kod`
  - Encoding: CP1250
- **Meteo stations**: `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/wykaz_stacji.csv`
  - Format: `ID, nazwa, kod`
  - Encoding: CP1250

### Real-time API
- **Hydro data**: `https://danepubliczne.imgw.pl/api/data/hydro`
- **Meteo data**: `https://danepubliczne.imgw.pl/api/data/meteo`
- **Synop data**: `https://danepubliczne.imgw.pl/api/data/synop`
- **Warnings**: `https://danepubliczne.imgw.pl/api/data/warningshydro`, `.../warningsmeteo`

### Map Stations API
- **Hydro stations with coordinates**: `https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false`
  - Requires headers: `User-Agent`, `Referer: https://hydro.imgw.pl/`
  - Returns: 900+ stations with lat/lon and water state (alarm, warning, high, medium, low, etc.)
  - Public access: `fetch_hydro_states()`, `imgw current hydro-states`, `GET /api/v1/current/hydro-states`

### Station Pages
- **Hydro**: `https://hydro.imgw.pl/#/station/hydro/{station_code}`
- **Meteo**: `https://hydro.imgw.pl/#/station/meteo/{station_code}`

## Command Catalog (CLI and REST)

CLI command = `imgw <group> <name>`; REST route = `/api/v1/<group>/<name>` (GET options in the query, POST options in a JSON body, `?check=true` on POST = plan without writing). "Local" commands have no REST route. Check: twin function used by `--check`/`?check=true`; `—` = no `--check`; "self" = the command is a check.

|Command|Function|Check|REST|
|---|---|---|---|
|`datasets list`|`datasets`|—|`GET /api/v1/datasets/list`|
|`datasets files`|`archive_files`|—|`GET /api/v1/datasets/files`|
|`datasets download`|`download_archives`|`check_command`|local|
|`stations find`|`find_stations`|`check_command`|`GET /api/v1/stations/find`|
|`current hydro`|`fetch_hydro_current`|`check_command`|`GET /api/v1/current/hydro`|
|`current meteo`|`fetch_meteo_current`|`check_command`|`GET /api/v1/current/meteo`|
|`current synop`|`fetch_synop`|`check_command`|`GET /api/v1/current/synop`|
|`current warnings`|`fetch_warnings`|`check_command`|`GET /api/v1/current/warnings`|
|`current hydro-states`|`fetch_hydro_states`|`check_command`|`GET /api/v1/current/hydro-states`|
|`pmaxtp fetch`|`fetch_pmaxtp`|`check_command`|`GET /api/v1/pmaxtp/fetch`|
|`pmaxtp url`|`build_pmaxtp_url`|—|`GET /api/v1/pmaxtp/url`|
|`pmaxtp check`|`check_pmaxtp`|self|`GET /api/v1/pmaxtp/check`|
|`pmaxtp sync`|`sync_pmaxtp`|`check_pmaxtp`|`POST /api/v1/pmaxtp/sync`|
|`pmaxtp read`|`read_pmaxtp`|—|`GET /api/v1/pmaxtp/read`|
|`store init`|`init_store`|`check_command`|local|
|`store info`|`store_info`|—|`GET /api/v1/store/info`|
|`store scan`|`iter_store`|—|`GET /api/v1/store/scan`|
|`store check`|`check_store`|self|`GET /api/v1/store/check`|
|`store sync`|`sync_store`|`check_store`|`POST /api/v1/store/sync`|
|`store catalog`|`build_catalog`|`check_catalog`|`POST /api/v1/store/catalog`|
|`store export`|`export_archive`|`check_command`|`GET /api/v1/store/export`|
|`series build`|`build_series`|`check_series`|`POST /api/v1/series/build`|
|`series select`|`select_series`|—|`GET /api/v1/series/select`|
|`series read`|`read_series`|—|`GET /api/v1/series/read`|
|`series summary`|`summarize_series`|—|`GET /api/v1/series/summary`|
|`series export`|`export_series`|`check_command`|`GET /api/v1/series/export`|
|`project init`|`init_project`|`check_command`|local|
|`project add`|`add_project_task`|`check_command`|local|
|`project remove`|`remove_project_task`|`check_command`|local|
|`project set-store`|`set_project_store`|`check_command`|local|
|`project download`|`download_project`|`check_project`|local|
|`project check`|`check_project`|self|local|
|`project status`|`get_project_status`|—|local|
|`project verify`|`verify_project`|—|local|
|`commands schema`|`command_schema`|—|`GET /api/v1/commands/schema`|

Outside the catalog: `imgw version`, `imgw server` (`--host`, `--port`, `--reload`), `imgw admin keys|create|revoke|delete|stats`, `GET /health`, `GET /api/v1` (name, version, schema route, list of catalog routes) and the HTML pages.

### Options

Option name = function parameter = JSON field; CLI flag = `--` + name with `_` → `-`. Short aliases: `-d` dataset(s), `-y` years, `-m` months, `-s` station(s), `-k` kind, `-q` query, `-o` output, `-r` root, `-f` format, `-p` path; `--lat`/`--lon` alias `--latitude`/`--longitude`. Lists: comma-separated or repeated flag/parameter. `--root` reads `IMGW_STORE_ROOT` (for `stations find` only with `--source store`). List commands accept `--limit`/`--offset`. `--check` exists only on commands with a check twin; `--schema` prints the command's schema without running it.

### Output, errors and exit codes

- CLI stdout: compact one-line JSON envelope `imgw-result/1` (`schema`, `command`, `check`, `status` ok|partial|failed|cancelled, `result`, `notices`); store paths relative to the root. `store export`/`series export` without `--path` stream CSV/JSONL bytes. Progress and notices (once per distinct notice) go to stderr.
- CLI error: stdout empty, last stderr line `{"code", "detail", "details"}`.
- REST: same envelope as the body; errors as `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`); list `limit` default/maximum `IMGW_API_MAX_LIMIT` (1000).

|Code|Title|CLI exit|HTTP|
|---|---|---|---|
|`validation_error`|Nieprawidłowe dane wejściowe|2|400|
|`not_found`|Nie znaleziono|3|404|
|`conflict`|Konflikt stanu|4|409|
|`source_unavailable`|Źródło IMGW niedostępne|5|502|
|`missing_dependency`|Brak opcjonalnej zależności|6|503|
|`data_error`|Niepoprawne dane|7|500|
|`store_unavailable`|Magazyn niedostępny|8|503|
|`io_error`|Błąd systemu plików|9|500|
|`cancelled`|Operację anulowano|130|—|
|`forbidden`|Brak uprawnień do zapisu|—|403|
|`method_not_allowed`|Niedozwolona metoda HTTP|—|405|
|`internal_error`|Błąd wewnętrzny|1|500|

Envelope status exit codes: `ok` 0, `partial` 10, `failed` 11, `cancelled` 130.

### Web GUI Routes

|Route|Description|
|---|---|
|`/`|Main dashboard|
|`/download`|Download page|
|`/download/archives`|Archive download form (10 registry archive datasets)|
|`POST /download/files`|Archive links partial (`archive_files`)|
|`/download/pmaxtp`|PMAXTP form|
|`POST /download/pmaxtp/generate`|PMAXTP tables partial (CSV, XLSX, JSON export)|
|`/stations`|Station search page|
|`/stations/find`|Station search partial (HTMX, `run_command("stations find")` with paging)|
|`/map`|Interactive map (Leaflet, color-coded by water state; data from `GET /api/v1/current/hydro-states`)|

Every `IMGWError` in a web handler renders `partials/error.html` (code, detail, option) with the HTTP status of the error registry.

## IMGW Data Structure

### Dataset registry (13 descriptors)

|Key|Legacy alias|Store|
|---|---|---|
|`pl.imgw.hydro_daily`|`hydro/dobowe`|yes|
|`pl.imgw.hydro_monthly`|`hydro/miesieczne`|yes|
|`pl.imgw.hydro_semiannual`|`hydro/polroczne_i_roczne`|yes|
|`pl.imgw.meteo_climate_daily`|`meteo/dobowe/klimat`|yes|
|`pl.imgw.meteo_precip_daily`|`meteo/dobowe/opad`|yes|
|`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`|—|yes (station lists)|
|`pl.imgw.pmaxtp`|—|yes (grid cells)|
|`pl.imgw.hydro_phenomena`|— (`hydro/dobowe` with month 13)|download only|
|`pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`|`meteo/miesieczne/klimat\|opad\|synop`|download only|
|`pl.imgw.meteo_climate_terms`|`meteo/terminowe/klimat`|download only|

`get_dataset`/`archive_files` accept the key, the slug (e.g. `hydro_daily`) or the legacy alias; results and slots always use the full key.

### Hydrological data (1951-2024+)
- `dobowe` (daily):
  - Before 2023: `codz_{year}_{month:02d}.zip` (monthly files; month 13 = `zjaw_` phenomena)
  - From 2023: `codz_{year}.zip` (single yearly file)
- `miesieczne` (monthly): `mies_{year}.zip`
- `polroczne_i_roczne` (semi-annual): `polr_{param}_{year}.zip` (param: T, Q, H)

### Meteorological data (1950-current)

Real IMGW layout, verified against live server listings (2026-07-05):

**Folders:** 5-year ranges until 2000 (e.g. `1996_2000`), yearly from 2001 (e.g. `2023`).
First folder differs per subtype: klimat `1951_1955`, opad `1950_1955`, synop `1960_1965` (six years); from `1966_1970` all subtypes share the same grid.

**Files per interval/subtype:**
- `miesieczne` (all subtypes): ONE file per folder — `{folder}_m_{k|o|s}.zip` (e.g. `1996_2000_m_s.zip`, `2023_m_s.zip`)
- `dobowe`/`terminowe` klimat & opad: yearly `{year}_{k|o}.zip` until 2000, monthly `{year}_{month:02d}_{k|o}.zip` from 2001
- `dobowe`/`terminowe` synop: PER-STATION files `{folder}_{station}_s.zip` — `get_dataset`/`archive_files` raise `IMGWValidationError` (`details.reason=per_station`)
- `terminowe` opad: dataset does not exist — `IMGWValidationError` (`details.reason=not_published`)

**Subtypes:** `k` (klimat), `o` (opad), `s` (synop)

## Docker Deployment

```bash
cd docker
docker-compose up -d
```

Services: app (FastAPI), nginx (reverse proxy). No Redis needed.

---

## Cloud & Deployment Details

### Deployment Model
Aplikacja hostowana na prywatnym serwerze. Komponenty:
- **Nginx** — reverse proxy + HTTPS + rate limiting
- **FastAPI (Uvicorn)** — backend API

### Rate limiting
- Nginx: `limit_req_zone` (10 req/s per IP)
- API keys support rate limits (configured per key, stored in JSON)

### Authorization (Planned)
Klucze API w pliku JSON (`api_keys.json`). Naglowek: `X-API-Key: <token>`

**Note:** API key validation middleware is not yet implemented. Keys are managed via CLI but not enforced in API requests. Store writes over REST use their own token (`IMGW_STORE_WRITE_TOKEN`, sent as `X-API-Key`).

### API versioning
Wszystkie endpointy pod `/api/v1/...`

---

## Versioned Store (Optional)

Explicit root only (`init_store(root)`, `--root`, `IMGW_STORE_ROOT`); readable offline, also from network shares. Decision: `docs/DECISIONS.md` ADR-001; contract: `docs/superpowers/specs/2026-10-17-versioned-store-design.md` (§13 = ADR-002 takes precedence).

### Configuration

|Variable|Default|Description|
|---|---|---|
|`IMGW_STORE_ROOT`|unset|Absolute store root of the REST server; CLI default for `--root`. Unset → store routes 503 `store_unavailable`|
|`IMGW_STORE_WRITES_ENABLED`|`false`|Allow REST writes (`POST` store/series/pmaxtp routes)|
|`IMGW_STORE_WRITE_TOKEN`|unset|Token required in `X-API-Key` for REST writes (else 403 `forbidden`)|
|`IMGW_USER_LOCATIONS_DIR`|unset|Directory of user location CSVs allowed in REST `user_locations`|
|`IMGW_API_MAX_LIMIT`|`1000`|Default and maximum `limit` of REST list commands|
|`IMGW_DATA_DIR`|`./data`|Local reference data (`python -m imgwtools.reference_data`)|

### Layout

```text
<root>/imgw-store.json                                  # imgw-store/1 marker
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<stem>/observations/   # imgw-observation/1 signal register (ADR-003, C01)
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/                                            # staging; never a version
```

Slots (spec §13.7): `archive:<key>:<file>` (e.g. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`), `series:<key>`, `catalog:pl.imgw.stations`, `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>`.

### Contracts (IMGW-13)

`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`, `imgw-pmaxtp/1`, `imgw-observation/1`, envelope `imgw-result/1`, `imgw-commands/1` (command schema). Each has its own `/N` counter; within `/1` only optional fields are added. `/1` domains are open to further providers (ADR-003 C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, station code `STATION_CODE_PATTERN` (9-digit IMGW or WIGOS), optional `content_sha256`/`content_form` in sidecars and project pins.

### IMGW CSV Format Notes

Archive files are inconsistent between years — parsers auto-detect the format per file:

- **Encoding**: CP1250 (Polish Windows encoding) for most archives; `codz_2023.zip` is UTF-8 with BOM (auto-detected)
- **Delimiter**: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023) — auto-detected from the first line
- **Quoting**: daily/monthly 2024 files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped); some files carry a header row of column codes (skipped)
- **Missing data codes**: `9999` (water level), `99999.999` (flow), `99.9` (temperature); meteo status 8 = `missing`, 9 = `no_phenomenon`
- **Hydrological year**: November 1 - October 31 (month 1 = November)

---

## Testing

The project includes unit and contract tests for the public API, CLI, REST and web GUI; all run offline (`respx` mocks or packaged recordings).

### Running Tests

Always run tests and lint through the project venv — the global (pyenv) Python has an
older non-editable `imgwtools` installed, which shadows the local `src/` and breaks
test collection.

```bash
# Run all tests
.venv/bin/python -m pytest

# Run with coverage
.venv/bin/python -m pytest --cov=imgwtools

# Run specific test file
.venv/bin/python -m pytest tests/unit/test_models.py -v

# Lint
.venv/bin/ruff check src/ tests/

# Type check (pyright reads [tool.pyright] in pyproject.toml)
npx -y pyright src/imgwtools/
```

### Test Structure

|File|Tests|Description|
|---|---|---|
|`tests/conftest.py`|-|Shared fixtures; autouse `isolated_data_dir`|
|`tests/unit/test_public_store_api.py`|179|`__all__` == spec §13.12, removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|145|CLI generated from the catalog: envelope, errors, exit codes, streams|
|`tests/unit/test_api_commands.py`|101|REST routes from the catalog, problem+json, write guard|
|`tests/unit/test_command_schema.py`|98|`command_schema`, `imgw-commands/1`|
|`tests/unit/test_commands.py`|96|Catalog, validation, `run_command`/`check_command`, paging|
|`tests/unit/test_fetch_live.py`|66|Live functions with `respx`|
|`tests/unit/test_datasets.py`|57|Registry, aliases, `archive_files`, `YearsArg`|
|`tests/unit/test_project.py`|55|`imgw-project/1`|
|`tests/unit/test_parsers.py`|50|Hydro/meteo/station-list parsers|
|`tests/unit/test_exceptions.py`|49|`ERROR_CODES`, codes and details|
|`tests/unit/test_store_*.py`, `test_series_export.py`|197|Store writer, sync, series, catalog, pmaxtp, reader, export|
|`tests/unit/test_web_app.py`|44|Web GUI|
|`tests/unit/` other files|147|fetch, models, stations, urls, coverage, download_archives, fixture builder, reference data, CLI admin/main, API main|
|`tests/contract/test_interface_contract.py`|78|Python = CLI = REST for all 25 REST commands, error matrix, paging|
|`tests/contract/` other files|15|Store contract, CLI = API parity, project contract|
|`tests/live/test_interfaces_live.py`|42|Live regression: 35 commands × Python/`imgw`/REST on real IMGW servers, live errors; skipped without `IMGW_LIVE=1`|

**Total: 1419 tests** (`pytest --collect-only`, 2026-10-18): 1377 offline, 42 live (`IMGW_LIVE=1 .venv/bin/python -m pytest tests/live`; JSON report via `IMGW_LIVE_REPORT=<file>`).

---

## Additional Documentation

Detailed project documentation is available in the `docs/` folder:

|File|Description|
|---|---|
|`docs/PROGRESS.md`|Progress tracker, cross-project analysis, and backlog (single source of truth for pending work)|
|`docs/CHANGELOG.md`|Release notes (3.0.0 BREAKING list and migration tables)|
|`docs/DECISIONS.md`|ADR-001 (versioned store), ADR-002 (one command catalog), ADR-003 (ČHMÚ provider)|
|`docs/ARCHITECTURE.md`|Detailed system architecture and component diagrams|
|`docs/PRD.md`|Product Requirements Document - project goals and requirements|
|`docs/RULES.md`|Development rules and conventions|
|`docs/DEVELOPMENT_STANDARDS.md`|Naming, error handling, docstrings, tests|

## Cross-Project Integration

IMGWTools is part of a 4-project ecosystem:

```
HYDROGRAF (main app)
    ├── IMGWTools ← THIS PROJECT
    ├── Kartograf
    └── Hydrolog → IMGWTools (required dependency)
```

Store consumers: **Archiwista** (public read API only) and **Retman** (command catalog: `command_schema`, `validate_command`, `check_command`, `run_command`). See `docs/PROGRESS.md` for cross-project analysis and integration details.
