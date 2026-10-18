# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IMGWTools is a Python library and tools for downloading public data from IMGW (Polish Institute of Meteorology and Water Management). It provides four interfaces:
- **Python Library** - `pip install imgwtools` for integration with other projects
- **CLI** - Command-line tool for local data downloading and the versioned store
- **REST API** - FastAPI-based API for generating download URLs (store routes only with explicit server configuration)
- **Web GUI** - HTMX + Jinja2 web interface

**Key principle:** By default nothing is stored on the server. The service generates direct links to IMGW servers and proxies live API data; users download data directly from IMGW. Data is written to disk only on explicit request: a CLI `--output` directory, an explicit store root (`--root`, `init_store(root)`), or a server-side `IMGW_STORE_ROOT` (store writes additionally require `IMGW_STORE_WRITES_ENABLED=true` + a write token).

**Versioned store (optional, since 3.0.0):** immutable, append-only versions of IMGW archives with SHA-256/HTTP provenance sidecars, Parquet station series, a `stations.geojson` catalog and PMAXTP cells. No database. Decision record: `docs/DECISIONS.md` (ADR-001); contract: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`.

**Version:** 3.0.0 (changes: `docs/CHANGELOG.md`)

## Installation

```bash
# Core library only (httpx, pydantic)
pip install imgwtools

# With CLI
pip install imgwtools[cli]

# With REST API server
pip install imgwtools[api]

# With versioned store Parquet support (pyarrow>=15)
pip install imgwtools[store]

# With DataFrame export (PMaXTPData.to_dataframe)
pip install imgwtools[pandas]

# Full installation (api, cli, pandas, store)
pip install imgwtools[full]

# For development
pip install -e ".[dev]"
```

Importing the core never imports pyarrow; Parquet operations without the extra raise `IMGWStoreDependencyError` with the install hint.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run API server
imgw server --reload

# Run tests / lint (always through the project venv, see Testing)
.venv/bin/python -m pytest
.venv/bin/ruff check src/ tests/

# CLI examples
imgw version                                    # Show version
imgw server --host 0.0.0.0 --port 8000         # Run API server
imgw fetch hydro -i dobowe -y 2023 -m 1        # Download daily hydro archives (mirrors server paths under -o)
imgw fetch meteo -i miesieczne -s synop -y 2023 # Download monthly meteo archives
imgw fetch current hydro                        # Get current hydro data from API
imgw fetch pmaxtp --lat 52.23 --lon 21.01      # Get PMAXTP data (live)
imgw fetch warnings --type hydro               # Get hydro warnings
imgw list stations --type hydro                # List hydro stations
imgw list datasets                             # List available datasets
imgw list intervals                            # List available intervals
imgw admin keys                                # List API keys
imgw admin create --name "User1"               # Create API key

# Versioned store (explicit --root; every command supports --check = plan only, no writes)
imgw store init --root /data/imgw
imgw store info --root /data/imgw              # offline
imgw store scan --root /data/imgw              # versions + problems, offline
imgw store check --root /data/imgw --dataset pl.imgw.hydro_daily --years 2023-2025 --plan plan.json
imgw store sync --root /data/imgw --plan plan.json [--no-series]
imgw store catalog --root /data/imgw [--user-locations locations.csv]
imgw store read --version <archive version dir|file|sidecar> [--format csv|jsonl] [--path out.csv]  # stdout without --path
imgw series build --root /data/imgw --dataset pl.imgw.hydro_daily
imgw series select --root /data/imgw --dataset pl.imgw.hydro_daily --stations 123456789
imgw series export --version <series version dir or series.json> --station 123456789 --path out.csv --variables H,Q
imgw pmaxtp sync --root /data/imgw --method POT --lat 52.23 --lon 21.01
imgw pmaxtp read --root /data/imgw --method POT --ind-x 751 --ind-y 317
imgw project init --project-dir ./proj --store-dir /data/imgw
imgw project add|remove|set-store|download|check|status|verify --project-dir ./proj ...
```

## Architecture

```
src/imgwtools/
├── __init__.py           # PUBLIC API - single __all__ (re-exports store, commands, project)
├── _version.py           # Version: 3.0.0
├── fetch.py              # PUBLIC: fetch_* (live), download_* -> DownloadResult
├── models.py             # PUBLIC: PMaXTPData, HydroCurrentData, ..., archive records, NormalizedRecord
├── stations.py           # PUBLIC: list_hydro_stations, get_hydro_stations_with_coords, ...
├── exceptions.py         # PUBLIC: IMGWError hierarchy incl. store/project errors
├── urls.py               # PUBLIC: re-exports from core/url_builder.py
├── parsers.py            # PUBLIC: hydro parsers + parse_meteo_*, normalize_archive
├── datasets.py           # PUBLIC: dataset registry (pl.imgw.*), archive_files, station_source_files
├── coverage.py           # PUBLIC: summarize_coverage (pure)
├── commands.py           # PUBLIC: data command catalog (CLI/REST/Retman share it)
├── project.py            # PUBLIC: imgw-project/1 manifest and tasks
├── testing.py            # PUBLIC: build_fixture_store (offline fixture store)
├── reference_data.py     # Fetch IMGW-PIB reference data into data/
├── config.py             # Settings (pydantic-settings, IMGW_ prefix)
├── _data/                # Packaged Poland border (Natural Earth, public domain) + store fixtures
├── _parsing/             # Internal parsers: common.py (CP1250/BOM, CSV, missing codes), hydro.py, meteo.py
├── store/                # Versioned store [Parquet needs imgwtools[store]]
│   ├── types.py          # Frozen dataclasses: StoreInfo, StorePlan, SyncReport, Meta, ...
│   ├── writer.py         # init_store/open_store/write_archive, atomic no-replace publish
│   ├── sync.py           # check_store/sync_store, imgw-plan/1
│   ├── series.py         # check_series/build_series (Parquet, imgw-series/1)
│   ├── catalog.py        # check_catalog/build_catalog (stations.geojson)
│   ├── pmaxtp.py         # check_pmaxtp/sync_pmaxtp/read_pmaxtp
│   ├── reader.py         # store_info, iter_store, read_meta, current_version, read_series*, read_catalog, read_station_list, read_archive
│   └── export.py         # export_series (CSV with IMGW-PIB attribution)
├── api/                  # FastAPI REST API [optional: imgwtools[api]]
│   ├── main.py           # App entry point
│   ├── routes/           # hydro.py, meteo.py, download.py, pmaxtp.py, store.py
│   └── schemas.py        # Pydantic models
├── cli/                  # Typer CLI [optional: imgwtools[cli]]
│   ├── main.py           # Entry point (imgw command)
│   ├── _dispatch.py      # Generates store/series/pmaxtp/project + fetch hydro|meteo from the catalog
│   ├── fetch.py, list_cmd.py, admin.py
│   └── store.py, series.py, pmaxtp.py, project.py
├── core/
│   └── url_builder.py    # URL generation (layout rules delegated to datasets.py)
└── web/                  # Web GUI (HTMX + Jinja2)
    ├── app.py            # Web routes
    ├── templates/        # Jinja2 templates
    └── static/           # CSS, JavaScript
```

### Public Library API

Everything is exposed via `from imgwtools import ...` (one `__all__`; `imgwtools.store` re-exports the same objects).

**Data Fetching Functions:**
| Function | Description |
|----------|-------------|
| `fetch_pmaxtp(lat, lon, method)` | Get PMAXTP precipitation data (live, unchanged) |
| `fetch_hydro_current(station_id)` | Get current hydro data |
| `fetch_synop(station_id, station_name)` | Get current synop data |
| `fetch_warnings(warning_type)` | Get weather/hydro warnings |
| `download_hydro_data(interval, year, month, param)` | Download hydro archive → `DownloadResult` |
| `download_meteo_data(interval, subtype, year, month)` | Download meteo archive → `DownloadResult` |
| `*_async` variants | Async versions of all of the above |

`DownloadResult(data, url, etag, last_modified, content_length)` — exact response bytes plus headers of the same GET (missing header = `None`); an invalid ZIP raises `IMGWDataError`.

**Station Functions:**
| Function | Description |
|----------|-------------|
| `list_hydro_stations()` | List stations from IMGW CSV (keeps `river_order`, `hydrographic_code`) |
| `get_hydro_stations_with_coords()` | Get stations with lat/lon from hydro-back.imgw.pl |
| `list_meteo_stations()` | List meteo stations |

**Dataset Registry and Parsers:**
| Function | Description |
|----------|-------------|
| `datasets()`, `get_dataset(key)` | `DatasetDescriptor` registry (full keys `pl.imgw.*`) |
| `archive_files(key, years=, months=)` | Offline list of `ArchiveFile` (server path, URL, period) |
| `station_source_files()` | Hydro/meteo station list CSV sources |
| `parse_zip_file`, `parse_daily_csv`, `parse_monthly_csv`, `parse_semi_annual_csv` | Hydro archive parsers |
| `parse_stations_csv(content, kind=)` | Hydro/meteo station list → `StationListEntry` (`kind`; hydro-only `river`/`hydrographic_code`/`river_order`, meteo-only `short_code`) |
| `parse_meteo_climate_daily`, `parse_meteo_precip_daily` | Meteo `k_d`/`o_d` parsers → `NormalizedRecord` |
| `normalize_archive(archive, data=)` | Any supported archive → `NormalizedRecord` with flags |
| `summarize_coverage(records, dataset=)` | Coverage per station × variable (gaps, first/last) |
| `IMGW_ENCODING` | CP1250 encoding constant |

**Versioned Store:**
| Function | Description |
|----------|-------------|
| `init_store`, `open_store`, `write_archive` | Create/open a store, publish an archive version |
| `check_store`, `sync_store` | Freshness plan (listing + HEAD, no GET) and sync per plan/selectors |
| `check_series`, `build_series` | Parquet station series snapshot per dataset |
| `check_catalog`, `build_catalog` | Versioned `stations.geojson` |
| `check_pmaxtp`, `sync_pmaxtp`, `read_pmaxtp` | PMAXTP per grid cell (`POT`/`AMP`) |
| `store_info`, `iter_store`, `read_meta`, `current_version` | Offline read/scan (problems reported, not raised) |
| `read_catalog`, `read_series_index`, `read_series`, `export_series` | Read catalog/series, CSV export |
| `read_station_list(root, kind=)` | Current stored `pl.imgw.hydro_stations`/`pl.imgw.meteo_stations` list, SHA-verified → `StationListEntry` |
| `read_archive(version)` | Records of one stored archive version (dataset + server path from the sidecar, SHA-verified, `normalize_archive`); station lists rejected |

**Commands and Projects:**
| Function | Description |
|----------|-------------|
| `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command` | Data command catalog shared by CLI, REST and Retman |
| `init_project`, `open_project`, `set_project_store`, `add_project_task`, `remove_project_task` | `imgw-project/1` manifest |
| `check_project`, `download_project`, `get_project_status`, `verify_project` | Pin, check and verify project data |

**Data Models:** `PMaXTPData`, `PMaXTPResult`, `HydroCurrentData`, `SynopData`, `WarningData`, `HydroStation`, `MeteoStation`, `Measurement`, `NormalizedRecord`, `Flag`, plus frozen store dataclasses (`StoreHandle`, `StoreInfo`, `StorePlan`, `PlanItem`, `PlanAction`, `SyncReport`, `OperationResult`, `SeriesReport`, `SeriesIndex`, `StationSeriesIndex`, `StationCoverage`, `CatalogReport`, `StationFeature`, `StoreEntry`, `Meta`, `VersionResult`, `PMaXTPStoreResult`, `Progress`, `Notice`, `Project`, `ProjectTask`, `ProjectFile`, `ProjectReport`, `DataCommand`, `CommandOption`, `SeriesSelection`).

**Exceptions:**
| Exception | Description |
|-----------|-------------|
| `IMGWError` | Base exception |
| `IMGWConnectionError` | Connection/timeout/HTTP errors |
| `IMGWDataError` | Data parsing errors (incl. invalid ZIP) |
| `IMGWValidationError` | Input validation errors (e.g., coords outside Poland) |
| `IMGWStoreError` | Store errors (unknown marker, unsafe path, ...) |
| `IMGWStoreConflictError` | Name/hash collision; never overwrites |
| `IMGWStoreDependencyError` | Missing `imgwtools[store]` for Parquet |
| `IMGWPlanStaleError` | Plan no longer matches server signals |
| `IMGWProjectError` | Project manifest errors |

### Key Module: `url_builder.py` + `datasets.py`

- `build_hydro_url()`, `build_meteo_url()`, `build_pmaxtp_url()`, `build_api_url()` keep their legacy scope (including meteo combinations outside the store).
- For the five store datasets, layout rules and validation come from the `datasets.py` registry (`archive_files`), not from a duplicated table.

### Store Layout and Schemas

```text
<root>/imgw-store.json                                  # imgw-store/1
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json   # imgw-meta/1
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet  # imgw-series/1
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + .meta.json     # imgw-pmaxtp/1
  .incoming/<host>_<pid>_<token>/                       # staging, never a version
```

Plans (`imgw-plan/1`) and project manifests (`imgw-project/1`) live outside the store. Schema counters `/N` are independent of the package version: `/1` only gains optional fields; a breaking change needs `/2` (IMGW-13). Readers tolerate extra fields in store files; the project manifest is validated strictly (future additions only under `extensions`).

Datasets: `pl.imgw.hydro_daily`, `pl.imgw.hydro_monthly`, `pl.imgw.hydro_semiannual`, `pl.imgw.meteo_climate_daily`, `pl.imgw.meteo_precip_daily`, station lists `pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`, and `pl.imgw.pmaxtp`. Current hydro/synop, warnings and `fetch_pmaxtp` stay live-only.

### Integrations

- **Archiwista** reads the store only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_series_index`, `read_series`, `read_pmaxtp`); IMGWTools is the only writer.
- **Retman** runs data actions as a handler through the public command catalog (`data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`).
- **Kartograf** stores are detected by marker names/schema strings (no import); nesting IMGW and Kartograf roots is refused.

## Data Flow

```
Default:   User → CLI/API/Web → URL Builder → IMGW Servers → User's computer
                                    (generates links only)

Store:     User/Archiwista/Retman → public API (check_* → sync_* → build_*) → <explicit root>
                                    (listing + HEAD, GET only for new/missing files)
```

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
- **Synop data**: `https://danepubliczne.imgw.pl/api/data/synop`

### Map Stations API
- **Hydro stations with coordinates**: `https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false`
  - Requires headers: `User-Agent`, `Referer: https://hydro.imgw.pl/`
  - Returns: 900+ stations with lat/lon and water state (alarm, warning, high, medium, low, etc.)
  - Not used by `build_catalog` (catalog locations: public API → local static file → user CSV)

### Station Pages
- **Hydro**: `https://hydro.imgw.pl/#/station/hydro/{station_id}`
- **Meteo**: `https://hydro.imgw.pl/#/station/meteo/{station_id}`

## API Endpoints

### Hydrological Data (`/api/v1/hydro`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stations` | GET | List hydrological stations |
| `/stations/{station_id}` | GET | Get station details |
| `/current` | GET | Current hydro data from IMGW API |
| `/download-url` | POST | Generate single download URL |
| `/download-urls` | POST | Generate multiple download URLs |

### Meteorological Data (`/api/v1/meteo`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stations` | GET | List meteorological stations |
| `/synop` | GET | Current synoptic data |
| `/current` | GET | Current meteo data from IMGW API |
| `/download-url` | POST | Generate single download URL |
| `/download-urls` | POST | Generate multiple download URLs |

### Unified Download (`/api/v1/download`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/datasets` | GET | List available datasets |
| `/url` | GET | Generate single download URL (hydro or meteo) |
| `/urls` | GET | Generate multiple download URLs |

### PMAXTP (`/api/v1/pmaxtp`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/methods` | GET | List available PMAXTP methods (POT, AMP) |
| `/url` | POST | Generate PMAXTP URL |
| `/data` | POST | Fetch PMAXTP data |

**PMAXTP response data:**
- `ks` - Kwantyle opadu maksymalnego [mm]
- `sg` - Górne granice przedziału ufności [mm]
- `rb` - Błędy estymacji kwantyli [mm]

**Web GUI exports:** CSV, XLSX (4 arkusze), JSON

### Versioned Store (`/api/v1/store`, `/api/v1/series`, `/api/v1/pmaxtp/store`)

Only on a server-side absolute `IMGW_STORE_ROOT` (unset → 503 for these routes; URL generator and live routes stay available). Paths in responses are relative to the root; clients never pass a root or absolute path.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/store/info` | GET | `StoreInfo` |
| `/api/v1/store/entries?kind=` | GET | `StoreEntry` list incl. problems |
| `/api/v1/store/check` | POST | `imgw-plan/1` (no writes; available with writes disabled) |
| `/api/v1/store/sync` | POST | Sync by selectors or plan (write) |
| `/api/v1/store/catalog` | POST | Build `stations.geojson` (write) |
| `/api/v1/series/build` | POST | Build Parquet series (write) |
| `/api/v1/series/index?version=` | GET | `SeriesIndex` |
| `/api/v1/series/{station}?version=&variables=&start=&end=` | GET | Records with values/flags |
| `/api/v1/series/export` | POST | CSV export (treated as write) |
| `/api/v1/pmaxtp/store/sync` | POST | Store a PMAXTP cell (write) |

Writes require `IMGW_STORE_WRITES_ENABLED=true`, a non-empty `IMGW_STORE_WRITE_TOKEN` and a matching `X-API-Key` header (constant-time compare); otherwise 403. User location CSVs only by basename from `IMGW_USER_LOCATIONS_DIR`.

### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1` | GET | API information |

### Web GUI Routes

| Route | Description |
|-------|-------------|
| `/` | Main dashboard |
| `/download` | Download page |
| `/download/hydro` | Hydro download form |
| `/download/meteo` | Meteo download form |
| `/download/pmaxtp` | PMAXTP download form |
| `/stations` | Stations list page (data from IMGW CSV) |
| `/stations/hydro` | Hydro stations partial (HTMX) |
| `/stations/meteo` | Meteo stations partial (HTMX) |
| `/map` | Interactive map with stations (Leaflet, color-coded by water state) |
| `/map/stations` | JSON endpoint for map markers (from hydro-back.imgw.pl, includes water state) |

## CLI Commands

### Main Commands

| Command | Description |
|---------|-------------|
| `imgw version` | Show version (`__version__`) |
| `imgw server` | Run API server (`--host`, `--port`, `--reload`) |

### Fetch Commands (`imgw fetch`)

| Command | Description |
|---------|-------------|
| `fetch hydro` | Download hydro archives (`-i interval`, `-y year or range`, `-m month`, `-p param`, `-o output`, `--check`); files mirror server paths, written via `.part` |
| `fetch meteo` | Download meteo archives (`-i interval`, `-s subtype`, `-y year or range`, `-m month`, `-o output`, `--check`) |
| `fetch current <type>` | Get current data from API (hydro/meteo/synop) |
| `fetch pmaxtp` | Get PMAXTP data (`--method`, `--lat`, `--lon`) |
| `fetch warnings` | Get warnings (`--type hydro/meteo`) |

### List Commands (`imgw list`)

| Command | Description |
|---------|-------------|
| `list stations` | List stations (`--type hydro/meteo`, `--search`, `--limit`) |
| `list datasets` | List available datasets (`--type`) |
| `list intervals` | List available intervals and subtypes |

### Admin Commands (`imgw admin`)

| Command | Description |
|---------|-------------|
| `admin keys` | List API keys |
| `admin create` | Create new API key (`--name`, `--limit`) |
| `admin revoke <id>` | Revoke API key |
| `admin delete <id>` | Delete API key (`--force`) |
| `admin stats` | Show usage statistics |

### Store, Series, PMAXTP and Project Commands

Generated from `data_commands()` by `cli/_dispatch.py`: help = catalog description (Polish), options in `--kebab-case`, list options comma-separated, years accept ranges (`2020-2023`). `--check` runs the command's `check_*` twin (prints `imgw-plan/1`, no writes, no data GET). Output: `Path` as plain text, text-line iterators (`store read` without `--path`) streamed verbatim, other results as JSON. Ctrl+C requests cancellation between files; a second Ctrl+C aborts.

| Command | Public API |
|---------|------------|
| `store init`, `store info`, `store scan` | `init_store` / `store_info` / `iter_store` |
| `store check` (`--dataset`, `--years`, `--months`, `--plan`) | `check_store` + `StorePlan.to_json` (plan outside the store) |
| `store sync` (`--plan` or `--dataset/--years`, `--no-series`) | `sync_store` |
| `store catalog` (`--user-locations`) | `build_catalog` |
| `store read` (`--version`, `--format csv\|jsonl`, `--path`) | `read_archive` (stdout without `--path`; file via `.part` + `os.replace`) |
| `series build`, `series export`, `series select` | `build_series` / `export_series` / validated selection from `current_version` |
| `pmaxtp check`, `pmaxtp sync`, `pmaxtp read` | `check_pmaxtp` / `sync_pmaxtp` / `read_pmaxtp` (not the live `fetch pmaxtp`) |
| `project init`, `add`, `remove`, `set-store`, `download`, `check`, `status`, `verify` | `project.py` functions |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `IMGW_DATA_DIR` | `./data` | Local reference data (`python -m imgwtools.reference_data`), e.g. `hydro_stations_locations.csv` |
| `IMGW_STORE_ROOT` | unset | Absolute server store root; unset → store routes 503 |
| `IMGW_STORE_WRITES_ENABLED` | `false` | Enable REST store writes |
| `IMGW_STORE_WRITE_TOKEN` | unset | Token compared with `X-API-Key` for REST writes |
| `IMGW_USER_LOCATIONS_DIR` | unset | Directory of allowed user location CSVs for REST |
| `IMGW_API_KEYS_FILE` | `./api_keys.json` | API keys managed by `imgw admin` |

## IMGW Data Structure

### Hydrological data (1951-2024+)
- `dobowe` (daily):
  - Before 2023: `codz_{year}_{month:02d}.zip` (monthly files)
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
- `dobowe`/`terminowe` synop: PER-STATION files `{folder}_{station}_s.zip` — `build_meteo_url` raises ValueError (not supported)
- `terminowe` opad: dataset does not exist — `build_meteo_url` raises ValueError

**Subtypes:** `k` (klimat), `o` (opad), `s` (synop)

### IMGW CSV Format Notes

Archive files are inconsistent between years — parsers auto-detect the format per file:

- **Encoding**: CP1250 (Polish Windows encoding) for most archives; `codz_2023.zip` is UTF-8 with BOM (auto-detected)
- **Delimiter**: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023) — auto-detected from the first line
- **Quoting**: daily/monthly 2024 files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped); some files carry a header row of column codes (skipped)
- **Missing data codes**: `9999` (water level), `99999.999` (flow), `99.9` (temperature); meteo status 8 = `missing`, 9 = `no_phenomenon` (value 0), accumulated precipitation = `accumulated`
- **Hydrological year**: November 1 - October 31 (month 1 = November)
- **ZIP safety**: member count/size limits, no path traversal; unreadable ZIP → `IMGWDataError`

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

**Note:** API key validation middleware is not yet implemented. Keys are managed via CLI but not enforced in API requests. Store write routes use their own `IMGW_STORE_WRITE_TOKEN` check, independent of these keys.

### API versioning
Wszystkie endpointy pod `/api/v1/...`

---

## Testing

All tests run offline: network is mocked with `respx` or replayed from recordings in `tests/fixtures/store/` (synthetic archives, fictional stations). The autouse fixture `isolated_data_dir` (`tests/conftest.py`) points `settings.data_dir` at an empty temp directory for every test.

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

# Lint (includes pydocstyle `D` rules, numpy convention; tests/ exempt)
.venv/bin/ruff check src/ tests/

# Format check (whole repository)
.venv/bin/ruff format --check src/ tests/

# Type check (pyright reads [tool.pyright] in pyproject.toml)
npx -y pyright src/imgwtools/
```

### Test Structure

| File | Tests | Description |
|------|-------|-------------|
| `tests/conftest.py` | - | Shared fixtures (API responses, CSV data, autouse `isolated_data_dir`) |
| `tests/unit/test_models.py` | 18 | PMaXTPData, HydroCurrentData, SynopData, WarningData |
| `tests/unit/test_fetch.py` | 23 | fetch_* and `DownloadResult` from download_* |
| `tests/unit/test_fetch_live.py` | 74 | Live fetch_* (sync/async): HTTP/JSON errors, mapping |
| `tests/unit/test_parsers.py` | 38 | Hydro/meteo parsers: delimiter/encoding/quoting, flags |
| `tests/unit/test_stations.py` | 19 | list_hydro_stations, get_hydro_stations_with_coords |
| `tests/unit/test_stations_extra.py` | 24 | Station functions: async variants, error mapping |
| `tests/unit/test_urls.py` | 35 | build_hydro_url, build_meteo_url, build_pmaxtp_url |
| `tests/unit/test_datasets.py` | 19 | Dataset registry and `archive_files` |
| `tests/unit/test_coverage.py` | 6 | `summarize_coverage` |
| `tests/unit/test_store_types.py` | 8 | Frozen store types, plan JSON, errors |
| `tests/unit/test_store_writer.py` | 8 | Atomic publish, relabel, Kartograf detection |
| `tests/unit/test_store_sync.py` | 9 | check/sync, `stale_plan`, cancellation |
| `tests/unit/test_store_series.py` | 8 | Parquet snapshots, reuse, pyarrow-less import |
| `tests/unit/test_store_catalog.py` | 13 | `stations.geojson`, location precedence, border check |
| `tests/unit/test_store_pmaxtp.py` | 5 | PMAXTP cells |
| `tests/unit/test_store_reader.py` | 10 | Read-only access, problems, unknown schemas |
| `tests/unit/test_series_export.py` | 14 | CSV export |
| `tests/unit/test_store_fixtures.py` | 7 | Synthetic archives and recordings |
| `tests/unit/test_fixture_builder.py` | 7 | `imgwtools.testing.build_fixture_store` |
| `tests/unit/test_commands.py` | 93 | Command catalog and dispatcher |
| `tests/unit/test_project.py` | 36 | `imgw-project/1` |
| `tests/unit/test_public_store_api.py` | 127 | Public exports and signatures contract |
| `tests/unit/test_cli_store_project.py` | 80 | CLI store/series/pmaxtp/project |
| `tests/unit/test_cli_fetch_store.py` | 4 | `imgw fetch hydro` / `imgw fetch meteo` |
| `tests/unit/test_cli_fetch_live.py` | 24 | `imgw fetch current`, `pmaxtp`, `warnings` |
| `tests/unit/test_cli_main.py` | 6 | `imgw version`, `imgw server`, help wiring |
| `tests/unit/test_cli_list.py` | 13 | `imgw list` |
| `tests/unit/test_cli_admin.py` | 19 | `imgw admin` |
| `tests/unit/test_api_store.py` | 73 | REST store routes |
| `tests/unit/test_api_download_registry.py` | 16 | REST URL generation on the registry |
| `tests/unit/test_api_live_routes.py` | 86 | REST hydro/meteo/download/pmaxtp routes (respx) |
| `tests/unit/test_api_main.py` | 12 | App, `/health`, `/api/v1`, OpenAPI |
| `tests/unit/test_web_app.py` | 41 | Web GUI routes |
| `tests/unit/test_reference_data.py` | 7 | `python -m imgwtools.reference_data` |
| `tests/contract/test_versioned_store.py` | 7 | Offline state machine HEAD → plan → sync → series → catalog → CSV, §11 JSON Schemas |
| `tests/contract/test_cli_api_parity.py` | 5 | Real `imgw` CLI gives the same paths/SHA as the Python API |
| `tests/contract/test_project_contract.py` | 4 | Project pin → verify → restore contract |

**Total: 998 tests, coverage 93%** (2026-10-18)

---

## Additional Documentation

Detailed project documentation is available in the `docs/` folder:

| File | Description |
|------|-------------|
| `docs/CHANGELOG.md` | Release notes (BREAKING changes, schema changes) |
| `docs/DECISIONS.md` | Decision records (ADR-001: versioned store) |
| `docs/PROGRESS.md` | Progress tracker, cross-project analysis, and backlog (single source of truth for pending work) |
| `docs/ARCHITECTURE.md` | Detailed system architecture and component diagrams |
| `docs/PRD.md` | Product Requirements Document - project goals and requirements |
| `docs/RULES.md` | Development rules and conventions |
| `docs/DEVELOPMENT_STANDARDS.md` | Code standards (NumPy docstrings, ruff, pyright, coverage) |
| `docs/TEST_PLAN.md` | Test plan |
| `docs/superpowers/specs/2026-10-17-versioned-store-design.md` | Versioned store contract (3.0.0) |

## Cross-Project Integration

IMGWTools is part of a multi-project ecosystem:

```
HYDROGRAF (main app)
    ├── IMGWTools ← THIS PROJECT
    ├── Kartograf
    └── Hydrolog → IMGWTools (required dependency)

Archiwista → IMGWTools store (public read API)
Retman     → IMGWTools command catalog (public run_command)
```

See `docs/PROGRESS.md` for cross-project analysis and integration details.
