# IMGWTools — Architecture

## 1. Architecture Model

System consists of six main components:

1. **Python Library** (v3.0.0)
   - `pip install imgwtools` for integration with external projects
   - Sync and async functions for live data and archive downloads (`DownloadResult`, `download_archives`)
   - Provider registry (`IMGW-PIB`, `CHMI` — ČHMÚ, ADR-003) and dataset registry (17 descriptors: 13 `pl.imgw.*`, 4 `cz.chmi.*`, with slugs and legacy aliases), IMGW-PIB and ČHMÚ parsers with value flags
   - Command catalog (`imgwtools.commands`): 38 commands, one envelope `imgw-result/1`, one error registry `ERROR_CODES` (ADR-002); Polish texts with an English variant, declared effects (`writes`, `network`, `idempotent`) and the agent guide `agent_guide` (ADR-004)
   - Minimal dependencies (httpx, pydantic)

2. **Versioned Store** [Parquet: `imgwtools[store]`]
   - Append-only, immutable versions of IMGW-PIB and ČHMÚ archives with provenance sidecars
   - Derived products: Parquet station series, `stations.geojson` per provider, PMAXTP cells
   - Explicit root only (no default location); readable offline, also from network shares
   - Decision records: `docs/DECISIONS.md` (ADR-001 store, ADR-002 interfaces, ADR-003 ČHMÚ provider and open `/1` domains, ADR-004 agent support); contracts: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`, `2026-10-18-chmi-provider-design.md`, `2026-10-19-agent-support-design.md`

3. **Backend (FastAPI)** [optional: `imgwtools[api]`]
   - Routes `/api/v1/<group>/<command>` generated from the command catalog (28 commands; local-only commands have no route)
   - URL generation for IMGW-PIB and ČHMÚ downloads and live IMGW data
   - Store commands only with an explicit server-side `IMGW_ROOT`
   - Errors as `application/problem+json`; language negotiation (`Accept-Language`, English by default); `GET /llms.txt`; optional MCP endpoint `/mcp`; rate limiting via Nginx

4. **MCP Server** [optional: `imgwtools[mcp]`]
   - `imgw mcp` (stdio) and `/mcp` (Streamable HTTP inside the REST app); tools generated from the command catalog
   - Read and plan only by default; writes only with `--allow-writes` and `check: false` (stdio)

5. **Frontend Web (GUI)**
   - HTMX + Jinja2 templates, handlers calling public functions only (IMGW-PIB datasets only)
   - Archive link and PMAXTP forms
   - Station search with paging
   - Interactive map with Leaflet.js

6. **CLI** [optional: `imgwtools[cli]`]
   - Local client using the library directly (never through the REST API)
   - Groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `project`, `commands` generated from the command catalog; help in Polish or English (`IMGW_LANG`)
   - `imgw mcp`, `imgw server`, API key management (`imgw admin`)

---

## 2. Component Diagram

```
┌──────────────────────────────────────┐ ┌──────────────────────────────────┐
│            IMGW-PIB                  │ │              ČHMÚ                │
│ danepubliczne.imgw.pl, hydro.imgw.pl,│ │ opendata.chmi.cz (historical,    │
│ hydro-back.imgw.pl, klimat.imgw.pl   │ │ historical_csv, metadata, now)   │
└──────────────────────────────────────┘ └──────────────────────────────────┘
                              ▲            ▲
                              │ HTTP (URL generation, live proxy, listing/HEAD/GET
                              │ for the store; one request at a time)
┌─────────────────────────────────────────────────────────────────┐
│                       imgwtools (library)                        │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │ urls       │ │ fetch /    │ │ datasets     │ │ parsers    │  │
│  │            │ │ stations   │ │ (providers,  │ │ (_parsing) │  │
│  │            │ │            │ │  registry)   │ │            │  │
│  └────────────┘ └────────────┘ └──────────────┘ └────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ store/: writer · content · sync · series · catalog ·      │   │
│  │         pmaxtp · reader · export        project.py        │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ commands.py: catalog · validate · run/check · schema      │   │
│  │ agent_guide.py: AGENTS.md / llms.txt                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        ▲               ▲               ▲               ▲               ▲
        │               │               │               │               │
   ┌─────────┐   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐
   │   CLI   │   │  FastAPI   │  │ MCP stdio  │  │ Archiwista │  │    Retman    │
   │ (local) │   │ + Web GUI  │  │ (imgw mcp) │  │ (read API) │  │ (run_command)│
   └─────────┘   │ + /mcp     │  └────────────┘  └────────────┘  └──────────────┘
                 └────────────┘        ▲
                       ▲               │ stdio (MCP client: editor, chat app)
                       │ HTTPS (Nginx: reverse proxy, rate limiting)
                 Browsers / API clients / MCP clients over HTTP
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
1. Generates URLs pointing to IMGW-PIB and ČHMÚ servers
2. Proxies real-time API requests to IMGW-PIB
3. Returns results directly to the client

Data is written only after explicit configuration: an absolute `IMGW_ROOT` enables store commands (otherwise 503 `store_unavailable`), and writes additionally need `IMGW_STORE_WRITES_ENABLED=true`, a non-empty `IMGW_STORE_WRITE_TOKEN` and a matching `X-API-Key` header (otherwise 403 `forbidden`). Locally, the CLI writes only to an explicit `--output` directory or `--root` store.

---

## 4. REST API

### Implemented Features
- Routes generated from `command_schema()` (`x-imgw.rest`) by `api/routes/commands.py`: `GET` for reads (options in the query; lists comma-separated or repeated), `POST` for `store sync`, `store catalog`, `series build`, `pmaxtp sync` (options in a JSON body; `?check=true` returns the plan without writing)
- Response body = `CommandResult.to_json(root, server=True, lang=)`, identical to the CLI envelope except hidden server paths and the language of the texts; list commands page with `limit` (default/maximum `IMGW_API_MAX_LIMIT`) and `offset`; `store export`/`series export` stream CSV/JSONL with `X-IMGW-Notices`/`X-IMGW-Status` headers
- Errors: `api/errors.py` turns every `IMGWError`, request validation error, HTTP error, `OSError` and unexpected exception into `application/problem+json` with `code`, `details` and the status of `ERROR_CODES` (validation always 400)
- `GET /api/v1` (name, version, schema route, catalog routes), `GET /health`, `GET /llms.txt` (agent guide in the language of `Accept-Language`, English by default), OpenAPI/Swagger documentation (`/docs`, English; HTML pages are not part of it)
- Language (AGI-6.4, AGI-9.2): the texts of an answer (notices, item and plan texts, the `title` and `detail` of problem+json) follow `?lang=` of a command with the option `lang` (`commands list`, `commands schema`, `commands guide`), else `Accept-Language` (RFC 9110 weights, first subtag), else English; every command answer has `Content-Language`, and `Vary: Accept-Language` when the header decided
- Optional `/mcp` (MCP Streamable HTTP, `IMGW_MCP_ENABLED=true`): the SDK session manager runs in the app lifespan, tools call the REST routes in process (section 7)

### Security (Current State)
- Rate limiting via Nginx (`limit_req_zone`)
- CORS middleware configured
- GZip compression enabled
- Store routes: server-side root only (clients never pass a root or absolute path; `version` is confined to `*/versions/` under the root, no `..`, symlinks rejected), write token compared in constant time, unknown/server-only/local options rejected (400 `validation_error`); answers hide server directories (root, `IMGW_USER_LOCATIONS_DIR`, `IMGW_DATA_DIR`, TMPDIR, CWD)
- `/mcp`: off by default (`IMGW_MCP_ENABLED`), read and plan only (POST routes always with `?check=true`, so the write token is never used), `Host` restricted to `IMGW_MCP_ALLOWED_HOSTS`, browser origins refused by the SDK (403); nginx `location = /mcp` shares the `api_limit` zone

### Security (Planned, Not Implemented)
- ~~API key validation middleware~~ - keys managed but not enforced (store writes use their own token)
- ~~Per-key rate limiting~~ - only nginx-level limiting
- ~~MCP writes over HTTP with authorization~~ - out of 3.0.0 (ADR-004 open question)

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
| `/download/archives` | GET | Archive form (10 IMGW-PIB registry archive datasets, `<optgroup>` per kind) |
| `/download/files` | POST | Archive links partial (`archive_files`) |
| `/download/pmaxtp` | GET | PMAXTP form |
| `/download/pmaxtp/generate` | POST | PMAXTP tables (CSV/XLSX/JSON export) via `fetch_pmaxtp_async` |
| `/stations` | GET | Station search page |
| `/stations/find` | GET | Station search partial (HTMX, `run_command("stations find")` with paging) |
| `/map` | GET | Interactive map; markers from `GET /api/v1/current/hydro-states` |

Every `IMGWError` renders `partials/error.html` (code, detail, option) with the status of `ERROR_CODES`; `static/js/app.js` lets HTMX swap 4xx/5xx partials and renders problem+json on the map. The GUI covers IMGW-PIB only (`datasets(provider="IMGW-PIB")`, station search with `provider="IMGW-PIB"`); ČHMÚ per-station files need a station list the forms do not have.

---

## 6. CLI Layer

### Technologies
- **Typer** (Click) - CLI framework; catalog groups via a custom Click group
- **Rich** - terminal formatting (`version`, `server`, `mcp`, `admin`)
- **HTTPX** - HTTP client

### Architecture
The CLI uses the library directly and downloads data straight from IMGW-PIB and ČHMÚ servers; it does NOT communicate through the REST API. All catalog groups (`datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `project`, `commands`) are generated from `command_schema()` by `cli/_dispatch.py` (`ImgwGroup` + `register_catalog`): help texts and flags come from the catalog, raw option text goes to `run_command` (or `check_command` for `--check`), `--schema` prints the command schema. stdout is the one-line JSON envelope `imgw-result/1` (streams for `store export`/`series export`/`commands guide` without `--path`), notices go to stderr once, errors are a JSON line `{"code", "detail", "details"}` on stderr with the exit code of `ERROR_CODES` (envelope status: `partial` 10, `failed` 11, `cancelled` 130). The CLI therefore has no validation or business rules of its own — CLI = Python API = REST = MCP (`tests/contract/test_interface_contract.py`, `test_mcp_contract.py`). `IMGW_LANG=pl|en` picks the help language once at import (catalog texts, group descriptions and the Typer/Click elements such as „Opcje”/„Options”, „Użycie:”/„Usage:”, `[OPCJE]`, „Przerwano.”) and the default of `--lang`; an invalid value ends every `imgw` call with a `validation_error` line (exit 2). `imgw version`, `imgw server`, `imgw mcp` and `imgw admin` stay outside the catalog (Polish help).

---

## 7. MCP Server Layer

### Technologies
- Official MCP SDK `mcp>=2.3,<3` (low-level `Server`), extra `imgwtools[mcp]` = `[cli]` + `mcp`; the core never imports it

### Architecture
`src/imgwtools/mcp/` is the fourth adapter of the command catalog (ADR-004 D6–D9), outside `imgwtools.__all__`:
- `_tools.py` — one tool per catalog command: name `x-imgw.operation_id` (`imgw_<group>_<verb>`, ECO-018), title `imgw <command>`, description with rules, input schema from `command_schema(name, lang=)` (without `$schema`, `title`, `x-imgw`), annotations `title`, `readOnlyHint`, `destructiveHint` (`replace`; false when read-only), `idempotentHint` (`idempotent`), `openWorldHint` (`network`); list commands get `limit` default 50.
- `_calls.py` — stdio: `check_command`/`run_command` in a worker thread with `on_progress` → `notifications/progress`, `on_notice` → envelope and `cancel` ← request cancellation; http: the same request a REST client would send, dispatched in process to `imgwtools.api.main:app` (POST always with `?check=true`, `Accept-Language` = server language).
- `server.py` — `create_server(*, mode, lang)`, `run_stdio(*, allow_writes, lang)` (used by `imgw mcp`), `http_app(*, lang)` (route `/mcp` added to the REST app when `IMGW_MCP_ENABLED=true`; hosts from `IMGW_MCP_ALLOWED_HOSTS`).

| Mode | Start | Tools | Writes |
|---|---|---|---|
| `read` (default) | `imgw mcp` | 38 | none: writing commands have `check` fixed `true` (plan `imgw-plan/1`), writing options removed |
| `write` | `imgw mcp --allow-writes` / `IMGW_MCP_ALLOW_WRITES=true` | 38 | `check` defaults to `true`; writes with `check: false` |
| `http` | `imgw server` + `IMGW_MCP_ENABLED=true` → `/mcp` | 28 (commands with a REST route) | none (REST rules: server root, `version` under `*/versions/`, hidden server paths) |

Results: `structuredContent` = envelope `imgw-result/1` (the CLI stdout bytes also as text), `isError=false` for every envelope; errors `isError=true` with `{code, title, detail, details}` (`OSError` → `io_error`, other exceptions → `internal_error`; refused write → `forbidden`, `details.reason="writes_disabled"`). Streams up to 256 KiB as text with `result={format, bytes, lines}`. The server speaks English only (AGI-9.2: tool descriptions, instructions, error documents; `IMGW_LANG` does not reach it), so the tool list does not depend on the connection or the user's setting; Polish text is only an explicit `lang: "pl"` argument of `imgw_commands_list`, `imgw_commands_schema` and `imgw_commands_guide`.

---

## 8. Versioned Store Layer

### Layers
1. **Source archives** — IMGW-PIB ZIP/CSV and ČHMÚ JSON/CSV bytes 1:1 under their server path (station lists are archives too).
2. **Derived products** — Parquet series per dataset/station (`imgw-series/1`), `stations.geojson` catalog per provider, PMAXTP `cell.json` (`imgw-pmaxtp/1`).
3. A rebuildable local index is out of scope; no `.db` file is ever part of the store.

### Layout
```text
<root>/imgw-store.json                                  # imgw-store/1 marker
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<stem>/observations/  # imgw-observation/1 signal register (read-only for consumers)
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json                 # IMGW-PIB catalog
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson + .meta.json   # ČHMÚ catalog
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/<host>_<pid>_<token>/                       # staging; leftovers >24 h cleaned
```

- `<sha8>` = first 8 hex digits of the full SHA-256 of the main file; labels come from `Last-Modified` (UTC) or download time.
- Every main file has an immutable `imgw-meta/1` sidecar: producer/version, dataset, country and provider (from the registry), request, provider license and attribution, `downloaded_at`, `sha256`, `size_bytes`, HTTP signals; ČHMÚ datasets with a canonical content form add `content_sha256`/`content_form`.
- Append-only: no overwrite and no `latest` path; hard links only move staged files into a version (after publication each stored file has one name, a relabeled version is a copy). The current version is computed by `current_version(root, slot=...)` with slots `archive:<key>:<file>`, `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>` (spec §13.7); `observations/` is never a version candidate. A new HTTP signal with identical bytes is `relabeled` (a copy), identical signal and bytes are `unchanged`; for datasets with a content form (`chmi-json/1`: ČHMÚ hydro files and station lists, JSON without the regenerated envelope keys, RFC 8785) other bytes with the current version's `content_sha256` are `unchanged` (notice `content_unchanged`) and a new source signal is written once to `observations/` (ADR-003 D17, D18).
- Publication (the Kartograf model, ADR-001 erratum 2026-10-19): write into a unique `.incoming/` staging directory and `fsync`, then hard-link (`os.link`, never replaces a target) every file into `<label>_<sha8>/`, the main file's sidecar last — it commits the version. A version directory without that sidecar is an interrupted publication: skipped by `current_version` and writers, reported by `iter_store` as `missing_sidecar`, completed by the next write of the same content under the same label. A failure or Ctrl+C during publication never removes a linked data file (a concurrent writer of the same bytes may have kept it and committed its own sidecar), so it leaves an interrupted publication; only empty directories created by that write are removed, and a linked sidecar is never removed. Versions are never cleaned automatically: the catalog label is the build date, PMAXTP and archives without `Last-Modified` use the download date (UTC), so an interrupted publication that is not repeated with the same content under the same label (e.g. a catalog rebuilt the next day) stays and is removed by hand — the whole `<label>_<sha8>/` directory without the sidecar, while no write to the store runs.
- File system: the store needs hard links, the same requirement as Kartograf's store (its ADR-036 D18, D21, D22) — versions, observations and the `imgw-store.json` marker are all published by `os.link`. Works on Linux, macOS and Windows (ext4, APFS, NTFS, SMB shares with hard links); a file system without them (FAT, exFAT, some NAS/FUSE, the macOS SMB client) is refused by `init_store` and every write with `IMGWStoreConflictError` (`details.reason="not_atomic"`); reading needs no hard links. Directory `fsync` is skipped on Windows and where the file system does not support it.
- `stations.geojson` of IMGW-PIB: `meteo_kind` of a meteorological station is `climate` when the current `pl.imgw.meteo_climate_daily` series holds it, otherwise `precipitation` when the current `pl.imgw.meteo_precip_daily` series does, else `null` (always `null` for ČHMÚ); `check_catalog` reports the series action as `newer` when it differs from the catalog.
- Kartograf stores are recognized by marker names/schema strings without importing Kartograf; nesting IMGW and Kartograf roots is refused.

### Flow
```
check_store  ── IMGW-PIB: listing + HEAD; ČHMÚ: one directory listing (no HEAD/GET) ──▶ StorePlan (imgw-plan/1, saved outside the store)
sync_store   ── HEAD again; changed → stale_plan; GET only new/missing ──▶ archive versions (ČHMÚ: content_unchanged + observation)
build_series ── current archive versions → Parquet snapshot (reused if the current series version has the same inputs); ČHMÚ: per-station periods
build_catalog── one provider: station lists (re-validated with HEAD; changed/unverifiable lists archived via write_archive first) + public metadata (+ static/user locations, series indexes) → stations.geojson
read_*       ── offline, read-only; problems reported as StoreEntry(kind="problem"), observations as kind="observation"
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

Within `/1` only optional fields are added; readers tolerate extra fields in store files, while the project manifest is validated strictly (future optional data only under `extensions`). A breaking change requires `/2` with a transition period reading both. Unknown versions are reported (`store_info(...).supported is False`, scan problems) and never parsed or written by old code. Before the 3.0.0 tag the `/1` value domains were opened for further providers (ADR-003 D2, task C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, `provider`/`license.id` any non-empty text, station codes 9-digit IMGW or WIGOS (`STATION_CODE_PATTERN`), ČHMÚ `location_source` values; a sidecar of a known dataset must still match the registry's country and provider. The ČHMÚ provider (same release) only adds optional fields: sidecar `request.station_code`/`param`, `extra.period.station_code`, `license.terms_url`; series `stations[<code>].periods`, Parquet `<V>_quality`/`<V>_source_flag`; catalog `thresholds`; plan items `station_code`/`signal`/`remote_listed_at`/`local_observation` and plan `requests`. ADR-004 adds `lang`, `x-imgw.writes`/`network`/`operation_id` and `x-imgw-writes` to `imgw-commands/1`. IMGW files keep identical bytes.

### Integrations
- **Archiwista** consumes the store only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`), for both providers (`provider` on entries, catalogs and stations; `read_catalog(root=, provider=)`). IMGWTools is the only writer; no Archiwista files or indexes live in the store. `iter_store` also returns read-only `kind="observation"` entries. Offline fixtures: `imgwtools.testing.build_fixture_store` (`complete`, `complete_pl_cz`, …), `fixture_files()` (archives, listings, recordings, contract schemas).
- **Retman** runs data actions as a handler via the public command catalog (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`), getting the same options, validation, envelope, error codes, progress and notices as the CLI and REST; English descriptions from `command_schema(lang="en")`, effects from `x-imgw.writes`/`x-imgw.network`.
- **AI agents** read `AGENTS.md`/`llms.txt` (derived from the catalog by `agent_guide`) and call the MCP tools or any other interface.
- **Projects** (`imgw-project.json`, `imgw-project/1`) pin store versions by SHA-256 next to (not inside) Kartograf project manifests.

### CSV Parsing Notes
IMGW-PIB archives are inconsistent between years; parsers auto-detect the format per file:
- Encoding: CP1250 for most archives, UTF-8 with BOM for the 2023 daily archive (auto-detected)
- Delimiter: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023), auto-detected
- Quoting: 2024 daily/monthly files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped)
- Missing data codes: `9999` (H), `99999.999` (Q), `99.9` (T); meteo status 8 = `missing`, 9 = `no_phenomenon`; accumulated precipitation = `accumulated`
- Hydrological year: Nov 1 - Oct 31
- ZIP reading with member count/size limits and no path traversal; unreadable ZIP → `IMGWDataError`

ČHMÚ files (`_parsing/chmi.py`): hydro JSON `{"objID", "tsList"}` (`HD`/`QD`/`TD` → H/Q/T, `PD` skipped, `null` → `missing`, missing row = no record), meteo CSV `STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY` (term rows of `T` skipped; `QUALITY` → `quality`, `FLAG` → `source_flag`; `0.0` without flag → `no_phenomenon`, trace `T` → `value`), metadata JSON located by column names (meteo `GEOGR1` = longitude, hydro `GEOGR1` = latitude; numbers read as `Decimal`), nginx listings (name from `href`, UTC minute, size). Errors → `IMGWDataError` with file name and place.

---

## 9. Data Formats

### Input (from the sources)
- IMGW-PIB: ZIP archives with CSV files; JSON from the real-time API and PMAXTP
- ČHMÚ: JSON per station and year (hydro), CSV per station and element (meteo), JSON metadata with an envelope, nginx directory listings (HTML)

### Output (to clients)
- JSON envelope `imgw-result/1` (CLI stdout, REST body, MCP `structuredContent`); errors as CLI JSON line, `application/problem+json` or MCP tool error
- Generated URLs (for direct IMGW-PIB and ČHMÚ downloads)
- Store products: Parquet series, GeoJSON (RFC 7946) station catalogs, CSV export with units and the provider's attribution (IMGW-PIB terms or ČHMÚ CC BY 4.0), JSONL archive export
- Agent guide: `AGENTS.md` and `llms.txt` (markdown, `text/markdown` in REST)

### GIS Integration
- `stations.geojson` with WGS84 points per provider (stations without a valid location keep `geometry: null` and a reason; ČHMÚ hydro stations carry SPA `thresholds`)
- Map visualization implemented with Leaflet
- ~~WFS/WMS integration~~ - not implemented

---

## 10. Scaling Considerations

The service is stateless by default:
- No session state
- No database
- The optional store is a plain directory (local disk or network share) with append-only versions; concurrent writers are safe thanks to unique staging and no-replace publication
- MCP sessions over HTTP live in the uvicorn process, so `/mcp` needs one worker per instance (the Docker image runs one)

Scaling options if needed:
- Horizontal scaling of FastAPI instances behind Nginx
- CDN for static files
- Shared read-only store root for several API instances (writes through one configured instance)

---

## 11. CI/CD

**Quality gate:** `scripts/gate.sh` (template `standards/ci/gate.sh` of the Nogat
standard, DEV-7.6) runs, in order and stopping at the first failure: `ruff format
--check`, `ruff check`, mypy (`strict`, over `src/` and `tests/`), one pytest call
over `tests/` with coverage (offline, `-m "not live"`, floor 80%) and the commit
step `scripts/check-commits.sh` (identity, Conventional Commits, no AI
attribution). The environment is `uv.lock` (`uv sync --locked`).

**CI:** GitHub Actions run the gate on Linux, macOS and Windows
(`.github/workflows/ci.yml`, DEV-7.7), the `live` tests weekly
(`.github/workflows/live.yml`), and Dependabot updates the Actions
(`.github/dependabot.yml`). Templates: `standards/ci/` of the Nogat standard. They
trigger on `main` and `develop`, so they start working once the branches are renamed.

**Deployment:** Docker (`docker/`).

---

## 12. File Structure

```
IMGWTools/
├── src/imgwtools/
│   ├── __init__.py       # PUBLIC API entry point (single __all__)
│   ├── _version.py       # Version (3.0.0)
│   ├── fetch.py          # PUBLIC: fetch_* (live), download_archives, download_* -> DownloadResult
│   ├── models.py         # PUBLIC: Data models incl. NormalizedRecord, Measurement
│   ├── stations.py       # PUBLIC: find_stations (IMGW-PIB and ČHMÚ)
│   ├── exceptions.py     # PUBLIC: Custom exceptions + ERROR_CODES (title as a catalog message)
│   ├── messages/         # Message catalog: message(), Message, localize(), Text(en, pl) per area (ADR-006)
│   ├── urls.py           # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
│   ├── parsers.py        # PUBLIC: Parser re-exports (IMGW-PIB hydro/meteo, ČHMÚ, station lists)
│   ├── datasets.py       # PUBLIC: Provider and dataset registry, archive_files, YearsArg/MonthsArg
│   ├── coverage.py       # PUBLIC: summarize_coverage
│   ├── commands.py       # PUBLIC: Command catalog, command_schema, run_command
│   ├── agent_guide.py    # PUBLIC: agent_guide (AGENTS.md, llms.txt), MCP instructions
│   ├── project.py        # PUBLIC: imgw-project/1
│   ├── testing.py        # PUBLIC: build_fixture_store, fixture_files
│   ├── _jsonable.py      # Single JSON converter (envelope, relative paths)
│   ├── reference_data.py # Fetch IMGW-PIB reference data into data/
│   ├── config.py         # Settings
│   ├── _data/            # Poland and Czechia borders (Natural Earth), agents/ templates, packaged fixtures, recordings, contract schemas
│   ├── _parsing/         # common.py, hydro.py, meteo.py, stations.py, chmi.py
│   ├── store/            # types, writer, content, sync, series, catalog, pmaxtp, reader, export
│   ├── api/              # REST API [optional]
│   │   ├── main.py       # FastAPI app (/health, /api/v1, /llms.txt, /mcp, web, static)
│   │   ├── routes/commands.py  # Routes generated from the command catalog
│   │   ├── errors.py     # problem+json handlers, hide_server_paths, Accept-Language
│   │   └── schemas.py    # HealthCheck
│   ├── cli/              # CLI [optional]
│   │   ├── main.py       # Entry point (version, server, mcp, admin, catalog groups)
│   │   ├── _dispatch.py  # Catalog-driven command generation (only adapter), IMGW_LANG
│   │   └── admin.py      # API key management
│   ├── mcp/              # MCP server [optional: imgwtools[mcp]]: _tools, _calls, server
│   └── web/              # Web GUI
│       ├── app.py        # HTMX routes
│       ├── templates/    # Jinja2 templates
│       └── static/       # CSS, JS
├── AGENTS.md, llms.txt   # Agent guide — derived from the catalog (imgw commands guide)
├── docker/               # Docker configuration (Python 3.12 image with .[api,mcp], compose, nginx with /mcp)
├── tests/                # Tests (unit, contract, live; fixtures/store with synthetic IMGW-PIB and ČHMÚ archives, recordings; fixtures/export_golden)
└── pyproject.toml        # Project configuration
```
