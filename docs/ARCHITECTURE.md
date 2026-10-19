# IMGWTools — Architecture

## 1. Architecture Model

System consists of five main components:

1. **Python Library** (v3.0.0)
   - `pip install imgwtools` for integration with external projects
   - Sync and async functions for live data and archive downloads (`DownloadResult`, `download_archives`)
   - Dataset registry (13 `pl.imgw.*` descriptors with slugs and legacy aliases), hydro/meteo parsers with value flags
   - Command catalog (`imgwtools.commands`): 35 commands, one envelope `imgw-result/1`, one error registry `ERROR_CODES` (ADR-002)
   - Minimal dependencies (httpx, pydantic)

2. **Versioned Store** [Parquet: `imgwtools[store]`]
   - Append-only, immutable versions of IMGW archives with provenance sidecars
   - Derived products: Parquet station series, `stations.geojson`, PMAXTP cells
   - Explicit root only (no default location); readable offline, also from network shares
   - Decision records: `docs/DECISIONS.md` (ADR-001 store, ADR-002 interfaces, ADR-003 open `/1` domains); contract: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`

3. **Backend (FastAPI)** [optional: `imgwtools[api]`]
   - Routes `/api/v1/<group>/<command>` generated from the command catalog (25 commands; local-only commands have no route)
   - URL generation for IMGW data downloads and live IMGW data
   - Store commands only with an explicit server-side `IMGW_STORE_ROOT`
   - Errors as `application/problem+json`; rate limiting via Nginx

4. **Frontend Web (GUI)**
   - HTMX + Jinja2 templates, handlers calling public functions only
   - Archive link and PMAXTP forms
   - Station search with paging
   - Interactive map with Leaflet.js

5. **CLI** [optional: `imgwtools[cli]`]
   - Local client using the library directly (never through the REST API)
   - Groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `project`, `commands` generated from the command catalog
   - API key management (`imgw admin`)

---

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         IMGW Public API                          │
│    (danepubliczne.imgw.pl, hydro.imgw.pl, hydro-back.imgw.pl)   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTP (URL generation, live proxy,
                              │ listing/HEAD/GET for the store)
┌─────────────────────────────────────────────────────────────────┐
│                       imgwtools (library)                        │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │ urls       │ │ fetch /    │ │ datasets     │ │ parsers    │  │
│  │            │ │ stations   │ │ (registry)   │ │ (_parsing) │  │
│  └────────────┘ └────────────┘ └──────────────┘ └────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ store/: writer · sync · series · catalog · pmaxtp ·       │   │
│  │         reader · export        project.py                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ commands.py: catalog · validate · run/check · schema      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        ▲               ▲                ▲                ▲
        │               │                │                │
   ┌─────────┐   ┌────────────┐   ┌────────────┐   ┌──────────────┐
   │   CLI   │   │  FastAPI   │   │ Archiwista │   │    Retman    │
   │ (local) │   │ + Web GUI  │   │ (read API) │   │ (run_command)│
   └─────────┘   └────────────┘   └────────────┘   └──────────────┘
                       ▲
                       │ HTTPS (Nginx: reverse proxy, rate limiting)
                 Browsers / API clients
```

---

## 3. Backend Layer

### Technologies (Implemented)
- Python 3.12+
- FastAPI 0.100+
- HTTPX (async HTTP client)
- Pydantic v2 (validation)
- Uvicorn (ASGI server)
- Nginx (reverse proxy)

### Technologies (Not Used)
- ~~Redis (cache)~~ - not needed
- ~~SQLite / PostgreSQL~~ - the optional SQLite cache was removed in 3.0.0 (ADR-001 D5); the versioned store keeps files, not a database

### Key Design Principle
**No data storage on the server by default.** Without configuration the backend only:
1. Generates URLs pointing to IMGW servers
2. Proxies real-time API requests to IMGW
3. Returns results directly to the client

Data is written only after explicit configuration: an absolute `IMGW_STORE_ROOT` enables store commands (otherwise 503 `store_unavailable`), and writes additionally need `IMGW_STORE_WRITES_ENABLED=true`, a non-empty `IMGW_STORE_WRITE_TOKEN` and a matching `X-API-Key` header (otherwise 403 `forbidden`). Locally, the CLI writes only to an explicit `--output` directory or `--root` store.

---

## 4. REST API

### Implemented Features
- Routes generated from `command_schema()` (`x-imgw.rest`) by `api/routes/commands.py`: `GET` for reads (options in the query; lists comma-separated or repeated), `POST` for `store sync`, `store catalog`, `series build`, `pmaxtp sync` (options in a JSON body; `?check=true` returns the plan without writing)
- Response body = `CommandResult.to_json(root, server=True)`, identical to the CLI envelope except hidden server paths; list commands page with `limit` (default/maximum `IMGW_API_MAX_LIMIT`) and `offset`; `store export`/`series export` stream CSV/JSONL with `X-IMGW-Notices`/`X-IMGW-Status` headers
- Errors: `api/errors.py` turns every `IMGWError`, request validation error, HTTP error, `OSError` and unexpected exception into `application/problem+json` with `code`, `details` and the status of `ERROR_CODES` (validation always 400)
- `GET /api/v1` (name, version, schema route, catalog routes), `GET /health`, OpenAPI/Swagger documentation (`/docs`)

### Security (Current State)
- Rate limiting via Nginx (`limit_req_zone`)
- CORS middleware configured
- GZip compression enabled
- Store routes: server-side root only (clients never pass a root or absolute path; `version` is confined to `*/versions/` under the root, no `..`, symlinks rejected), write token compared in constant time, unknown/server-only/local options rejected (400 `validation_error`); answers hide server directories (root, `IMGW_USER_LOCATIONS_DIR`, `IMGW_DATA_DIR`, TMPDIR, CWD)

### Security (Planned, Not Implemented)
- ~~API key validation middleware~~ - keys managed but not enforced (store writes use their own token)
- ~~Per-key rate limiting~~ - only nginx-level limiting

---

## 5. Web GUI Layer

### Technologies (Implemented)
- **HTMX** - dynamic updates without full page reloads
- **Jinja2** - server-side templating
- **Leaflet.js** - interactive maps
- **Vanilla CSS** - styling

### Available Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Dashboard |
| `/download` | GET | Download landing page |
| `/download/archives` | GET | Archive form (10 registry archive datasets, `<optgroup>` per kind) |
| `/download/files` | POST | Archive links partial (`archive_files`) |
| `/download/pmaxtp` | GET | PMAXTP form |
| `/download/pmaxtp/generate` | POST | PMAXTP tables (CSV/XLSX/JSON export) via `fetch_pmaxtp_async` |
| `/stations` | GET | Station search page |
| `/stations/find` | GET | Station search partial (HTMX, `run_command("stations find")` with paging) |
| `/map` | GET | Interactive map; markers from `GET /api/v1/current/hydro-states` |

Every `IMGWError` renders `partials/error.html` (code, detail, option) with the status of `ERROR_CODES`; `static/js/app.js` lets HTMX swap 4xx/5xx partials and renders problem+json on the map.

---

## 6. CLI Layer

### Technologies
- **Typer** (Click) - CLI framework; catalog groups via a custom Click group
- **Rich** - terminal formatting (`version`, `server`, `admin`)
- **HTTPX** - HTTP client

### Architecture
The CLI uses the library directly and downloads data straight from IMGW servers; it does NOT communicate through the REST API. All catalog groups (`datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `project`, `commands`) are generated from `command_schema()` by `cli/_dispatch.py` (`ImgwGroup` + `register_catalog`): help texts and flags come from the catalog, raw option text goes to `run_command` (or `check_command` for `--check`), `--schema` prints the command schema. stdout is the one-line JSON envelope `imgw-result/1` (streams for `store export`/`series export` without `--path`), notices go to stderr once, errors are a JSON line `{"code", "detail", "details"}` on stderr with the exit code of `ERROR_CODES` (envelope status: `partial` 10, `failed` 11, `cancelled` 130). The CLI therefore has no validation or business rules of its own — CLI = Python API = REST (`tests/contract/test_interface_contract.py`).

---

## 7. Versioned Store Layer

### Layers
1. **Source archives** — IMGW ZIP/CSV bytes 1:1 under their server path (station lists are archives too).
2. **Derived products** — Parquet series per dataset/station (`imgw-series/1`), `stations.geojson` catalog, PMAXTP `cell.json` (`imgw-pmaxtp/1`).
3. A rebuildable local index is out of scope; no `.db` file is ever part of the store.

### Layout
```text
<root>/imgw-store.json                                  # imgw-store/1 marker
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<stem>/observations/  # imgw-observation/1 signal register (read-only for consumers)
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/<host>_<pid>_<token>/                       # staging; leftovers >24 h cleaned
```

- `<sha8>` = first 8 hex digits of the full SHA-256 of the main file; labels come from `Last-Modified` (UTC) or download time.
- Every main file has an immutable `imgw-meta/1` sidecar: producer/version, dataset, request, IMGW-PIB license and attribution, `downloaded_at`, `sha256`, `size_bytes`, HTTP signals.
- Append-only: no overwrite, hardlinks or `latest` path. The current version is computed by `current_version(root, slot=...)` with slots `archive:<key>:<file>`, `series:<key>`, `catalog:pl.imgw.stations`, `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>` (spec §13.7); `observations/` is never a version candidate. A new HTTP signal with identical bytes is `relabeled` (a copy), identical signal and bytes are `unchanged`.
- Publication: write into a unique `.incoming/` staging directory, `fsync`, then a single no-replace rename of the whole version directory (`renameat2(RENAME_NOREPLACE)` on Linux); other systems and filesystems without atomic no-replace rename are refused with an explicit `IMGWStoreConflictError`.
- Kartograf stores are recognized by marker names/schema strings without importing Kartograf; nesting IMGW and Kartograf roots is refused.

### Flow
```
check_store  ── listing + HEAD only ──▶ StorePlan (imgw-plan/1, saved outside the store)
sync_store   ── HEAD again; changed → stale_plan; GET only new/missing ──▶ archive versions
build_series ── current archive versions → Parquet snapshot (reused if the current series version has the same inputs)
build_catalog── station lists (re-validated with HEAD; changed/unverifiable lists archived via write_archive first) + public API (+ static/user locations) → stations.geojson
read_*       ── offline, read-only; problems reported as StoreEntry(kind="problem")
```

Every write operation has a `check_*` twin that never writes or GETs data; long operations accept `on_progress`, `on_notice` (Polish messages) and `cancel` (between files; cancellation never publishes a partial version).

### Schema Versioning (IMGW-13)
Contracts with their own `/N` counters, independent of the package version:

| Contract | File / use |
|---|---|
| `imgw-store/1` | `<root>/imgw-store.json` store marker |
| `imgw-meta/1` | `<file>.meta.json` sidecar of every version (optional `content_sha256` + `content_form`, always together) |
| `imgw-series/1` | `series.json` index of a Parquet series (+ Parquet metadata) |
| `imgw-plan/1` | `plan.json` freshness plan outside the store |
| `imgw-project/1` | `imgw-project.json` project manifest (optional `content_sha256`/`content_form` per pin) |
| `imgw-pmaxtp/1` | `cell.json` PMAXTP cell (IMGWTools extension) |
| `imgw-observation/1` | `observations/<YYYY-MM-DD>_<sha8>.json` signal register in an archive slot (ADR-003 D18) |
| `imgw-result/1` | result envelope of `run_command`/`check_command`, CLI stdout and REST body |
| `imgw-commands/1` | `command_schema()` document |

Within `/1` only optional fields are added; readers tolerate extra fields in store files, while the project manifest is validated strictly (future optional data only under `extensions`). A breaking change requires `/2` with a transition period reading both. Unknown versions are reported (`store_info(...).supported is False`, scan problems) and never parsed or written by old code. Before the 3.0.0 tag the `/1` value domains were opened for further providers (ADR-003 D2, task C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, `provider`/`license.id` any non-empty text, station codes 9-digit IMGW or WIGOS (`STATION_CODE_PATTERN`), ČHMÚ `location_source` values; a sidecar of a known dataset must still match the registry's country and provider. IMGW files keep identical bytes.

### Integrations
- **Archiwista** consumes the store only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`). IMGWTools is the only writer; no Archiwista files or indexes live in the store. `iter_store` also returns read-only `kind="observation"` entries. Offline fixtures: `imgwtools.testing.build_fixture_store`, `fixture_files()` (archives, recordings, contract schemas).
- **Retman** runs data actions as a handler via the public command catalog (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`), getting the same options, validation, envelope, error codes, progress and notices as the CLI and REST.
- **Projects** (`imgw-project.json`, `imgw-project/1`) pin store versions by SHA-256 next to (not inside) Kartograf project manifests.

### CSV Parsing Notes
IMGW archives are inconsistent between years; parsers auto-detect the format per file:
- Encoding: CP1250 for most archives, UTF-8 with BOM for the 2023 daily archive (auto-detected)
- Delimiter: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023), auto-detected
- Quoting: 2024 daily/monthly files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped)
- Missing data codes: `9999` (H), `99999.999` (Q), `99.9` (T); meteo status 8 = `missing`, 9 = `no_phenomenon`; accumulated precipitation = `accumulated`
- Hydrological year: Nov 1 - Oct 31
- ZIP reading with member count/size limits and no path traversal; unreadable ZIP → `IMGWDataError`

---

## 8. Data Formats

### Input (from IMGW)
- ZIP archives with CSV files
- JSON from real-time API and PMAXTP

### Output (to clients)
- JSON envelope `imgw-result/1` (CLI stdout, REST body); errors as CLI JSON line or `application/problem+json`
- Generated URLs (for direct IMGW downloads)
- Store products: Parquet series, GeoJSON (RFC 7946) station catalog, CSV export with units and IMGW-PIB attribution, JSONL archive export

### GIS Integration
- `stations.geojson` with WGS84 points (stations without a valid location keep `geometry: null` and a reason)
- Map visualization implemented with Leaflet
- ~~WFS/WMS integration~~ - not implemented

---

## 9. Scaling Considerations

The service is stateless by default:
- No session state
- No database
- The optional store is a plain directory (local disk or network share) with append-only versions; concurrent writers are safe thanks to unique staging and no-replace publication

Scaling options if needed:
- Horizontal scaling of FastAPI instances behind Nginx
- CDN for static files
- Shared read-only store root for several API instances (writes through one configured instance)

---

## 10. CI/CD

**Status: not configured.** There is no GitHub Actions workflow (or any other
CI pipeline) in the repository; tests, linting and formatting are run locally.

### Recommended Setup
- pytest for automated testing (offline; recorded IMGW responses)
- ruff for linting (PEP8 compliance) and docstring checks (numpy `D` rules)
- pyright for type checking
- GitHub Actions for CI pipeline
- Docker for deployment

---

## 11. File Structure

```
IMGWTools/
├── src/imgwtools/
│   ├── __init__.py       # PUBLIC API entry point (single __all__, spec §13.12)
│   ├── _version.py       # Version (3.0.0)
│   ├── fetch.py          # PUBLIC: fetch_* (live), download_archives, download_* -> DownloadResult
│   ├── models.py         # PUBLIC: Data models incl. NormalizedRecord
│   ├── stations.py       # PUBLIC: find_stations
│   ├── exceptions.py     # PUBLIC: Custom exceptions + ERROR_CODES
│   ├── urls.py           # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
│   ├── parsers.py        # PUBLIC: Parser re-exports (hydro, meteo, station lists)
│   ├── datasets.py       # PUBLIC: Dataset registry, archive_files, YearsArg/MonthsArg
│   ├── coverage.py       # PUBLIC: summarize_coverage
│   ├── commands.py       # PUBLIC: Command catalog, command_schema, run_command
│   ├── project.py        # PUBLIC: imgw-project/1
│   ├── testing.py        # PUBLIC: build_fixture_store, fixture_files
│   ├── _jsonable.py      # Single JSON converter (envelope, relative paths)
│   ├── reference_data.py # Fetch IMGW-PIB reference data into data/
│   ├── config.py         # Settings
│   ├── _data/            # Poland border (Natural Earth) + packaged fixtures, recordings, contract schemas
│   ├── _parsing/         # common.py, hydro.py, meteo.py, stations.py
│   ├── store/            # types, writer, sync, series, catalog, pmaxtp, reader, export
│   ├── api/              # REST API [optional]
│   │   ├── main.py       # FastAPI app (/health, /api/v1, web, static)
│   │   ├── routes/commands.py  # Routes generated from the command catalog
│   │   ├── errors.py     # problem+json handlers, hide_server_paths
│   │   └── schemas.py    # HealthCheck
│   ├── cli/              # CLI [optional]
│   │   ├── main.py       # Entry point (version, server, admin, catalog groups)
│   │   ├── _dispatch.py  # Catalog-driven command generation (only adapter)
│   │   └── admin.py      # API key management
│   └── web/              # Web GUI
│       ├── app.py        # HTMX routes
│       ├── templates/    # Jinja2 templates
│       └── static/       # CSS, JS
├── docker/               # Docker configuration
├── tests/                # Tests (unit + contract; fixtures/store with synthetic archives, fixtures/export_golden)
└── pyproject.toml        # Project configuration
```
