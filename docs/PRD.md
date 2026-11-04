# Obserwator — PRD (Product Requirements Document)

## 1. Product Goal

Obserwator is a tool for downloading, exposing, versioning and basic visualization of hydrological and meteorological data published by IMGW-PIB and, since 3.0.0, by ČHMÚ (Czech Hydrometeorological Institute, opendata.chmi.cz). The product provides:
- Python library (public API)
- CLI application
- Web GUI application
- Public REST API
- MCP server for AI agents (`obserwator mcp`, `/mcp`) and a generated agent guide (`AGENTS.md`, `llms.txt`)
- Optional versioned data store (ADR-001, `docs/DECISIONS.md`) for consumers such as Archiwista and Retman

Analytical and statistical parts (hydrological calculations, probabilistic models, statistical analyses) live in a separate repository (Hydrolog) and are out of scope for this PRD.

---

## 2. Stakeholders

- Individual users interested in IMGW data
- GIS specialists
- Developers requiring API access to data
- Downstream projects: Hydrograf, Hydrolog, Archiwista (store reader, IMGW-PIB and ČHMÚ), Retman (command handler)
- AI agents and assistants using the tools through MCP, the CLI or REST
- Service administrator (owner)

---

## 3. Functional Scope

### 3.1. Data Access

| Feature | Status | Description |
|---------|--------|-------------|
| Real-time data (IMGW API) | Implemented | Current hydro/meteo/synop data |
| Archive data (ZIP/CSV) | Implemented | Dataset registry (13 `pl.imgw.*` descriptors): URL generation and downloads into an IMGW server-path tree |
| ČHMÚ data (JSON/CSV per station) | Implemented (3.0.0) | 4 `cz.chmi.*` descriptors (daily hydro H/Q/T, daily meteo P/Tmean/Tmax/Tmin with quality and flags, station lists); freshness from directory listings; station catalog with SPA thresholds |
| PMAXTP data | Implemented | Probabilistic max precipitation (IMGW-PIB grid only) |
| Warnings | Implemented | Hydro/meteo warnings from API |
| Versioned store | Implemented (3.0.0) | Immutable archive versions with provenance (both providers), freshness plan, Parquet series, `stations.geojson` per provider, PMAXTP cells, canonical content (`content_sha256`) and the observation register for ČHMÚ |
| Projects (pins of store versions) | Moved to Archiwista (ADR-008, 2026-10-31) | Obserwator's project manifest and the `imgw project` command group are removed; Archiwista keeps projects in `archiwista-project/1` and pins versions by the store's `sha256` and `content_sha256` |

### 3.2. Interfaces

| Interface | Status | Description |
|-----------|--------|-------------|
| CLI | Implemented | `obserwator` command: catalog groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `commands` plus `version`, `server`, `mcp`, `admin`; help in Polish or English (`OBSERWATOR_LANG`) |
| Web GUI | Implemented | HTMX + Jinja2 web interface on the public library API (IMGW-PIB datasets) |
| REST API | Implemented | FastAPI with OpenAPI documentation; routes generated from the same command catalog; `Accept-Language`; `GET /llms.txt` |
| Python command catalog | Implemented (3.0.0) | 30 commands, `command_schema` and `list_commands` (Polish or English texts, declared effects), `run_command`/`check_command`, envelope `obserwator-result/1`, error registry `ERROR_CODES` |
| MCP server | Implemented (3.0.0) | `obserwator[mcp]`: `obserwator mcp` (stdio, read and plan by default, writes with `--allow-writes`) and `/mcp` in the REST server (read and plan only); tools = catalog commands |

### 3.3. Visualization

| Feature | Status | Description |
|---------|--------|-------------|
| Interactive map | Implemented | Leaflet.js with station markers |
| Station listings | Implemented | Searchable tables |
| Data charts | Not Implemented | Future enhancement |

### 3.4. Data Export

| Format | Status | Description |
|--------|--------|-------------|
| JSON | Implemented | Envelope `obserwator-result/1` (CLI stdout, REST body, MCP `structuredContent`); errors as `application/problem+json` |
| URLs | Implemented | Direct links to IMGW-PIB and ČHMÚ servers |
| CSV | Implemented | PMAXTP export in the Web GUI; station series export (`export_series`, `obserwator series export`) with units and the provider's attribution (IMGW-PIB or ČHMÚ CC BY 4.0); archive export (`export_archive`, CSV or JSONL) |
| GeoJSON | Implemented (store) | Versioned `stations.geojson` station catalogs per provider (RFC 7946); not yet exposed in REST/GUI |
| Markdown | Implemented | Agent guide `AGENTS.md`/`llms.txt` (`obserwator commands guide`, `GET /api/v1/commands/guide`, `GET /llms.txt`) |
| Parquet | Implemented (store) | Station series per dataset (`obserwator-series/1`, `obserwator[store]`) |

---

## 4. REST API — Requirements

### Implemented

| Requirement | Status |
|-------------|--------|
| OpenAPI/Swagger documentation | Implemented |
| API versioning (`/api/v1/`) | Implemented |
| Catalog routes `/api/v1/<group>/<command>` (datasets, stations, current, pmaxtp, store, series, commands) | Implemented — 28 routes generated from `command_schema()` |
| Paging of list commands (`limit`/`cursor`, maximum `OBSERWATOR_API_MAX_LIMIT`) | Implemented |
| Errors as `application/problem+json` with registry codes | Implemented |
| Health check | Implemented |
| Language negotiation (`Accept-Language`, `Content-Language`) | Implemented |
| Agent guide `GET /llms.txt` | Implemented |
| MCP Streamable HTTP `/mcp` (`OBSERWATOR_MCP_ENABLED`) | Implemented — read and plan only |
| Store commands | Implemented — only with server-side `OBSERWATOR_ROOT`; writes need `OBSERWATOR_STORE_WRITES_ENABLED` + write token |

### Not Implemented

| Requirement | Status | Notes |
|-------------|--------|-------|
| API key validation | Not Implemented | Keys managed via CLI but not enforced |
| Per-key rate limiting | Not Implemented | Only Nginx-level limiting |
| Request logging | Not Implemented | - |

---

## 5. Web GUI — Requirements

### Implemented

| Requirement | Status |
|-------------|--------|
| Fully web-based | Implemented |
| HTTPS communication | Implemented (via Nginx) |
| Download forms (archives from the dataset registry, PMAXTP) | Implemented |
| Station search with paging | Implemented |
| Interactive map | Implemented |

### Not Implemented

| Requirement | Status |
|-------------|--------|
| Data charts | Not Implemented |
| User accounts | Not Implemented |

---

## 6. CLI — Requirements

### Implemented

| Requirement | Status |
|-------------|--------|
| pip installation | Implemented |
| `obserwator datasets`, `obserwator stations`, `obserwator current` (replace `imgw fetch`/`imgw list` of 2.x) | Implemented (3.0.0, generated from the command catalog; `--provider`, `--stations` for ČHMÚ) |
| `obserwator admin` command | Implemented |
| `obserwator server` command | Implemented |
| `obserwator mcp` command (MCP server on stdio) | Implemented (3.0.0, `obserwator[mcp]`) |
| `obserwator store`, `obserwator series`, `obserwator pmaxtp`, `obserwator commands` | Implemented (3.0.0, generated from the command catalog) |
| `imgw project` | Moved to Archiwista (ADR-008, 2026-10-31) |
| `--check` (plan only, no writes), `--schema` (command schema) | Implemented |
| JSON envelope on stdout, JSON error on stderr, exit codes from the error registry | Implemented |
| `--output` flag | Implemented |
| `--station` filtering | Implemented |
| Progress bars | Implemented |

### Commands Available

```bash
# Main commands
obserwator version
obserwator server [--host] [--port] [--reload]
obserwator mcp [--allow-writes]

# Datasets, stations, live data (lists accept --limit/--cursor)
obserwator datasets list [-k hydro|meteo] [--provider IMGW-PIB|CHMI]
obserwator datasets providers
obserwator datasets files -d <dataset> [-y <years>] [-m <months>] [--params H,Q,T] [-s <stations>]
obserwator datasets download -d <dataset> [-y <years>] [-m <months>] [--params] [-s <stations>] [-o <dir>] [--check]
obserwator stations find [-k hydro|meteo] [-q <query>] [--source live|store] [--root <dir>] [--provider IMGW-PIB|CHMI]
obserwator current hydro|meteo [-s <code>]
obserwator current synop [-s <code>] [--station-name <name>]
obserwator current warnings [-k hydro|meteo]
obserwator current hydro-states [--main-only]
obserwator pmaxtp fetch|url --lat <lat> --lon <lon> [--method POT|AMP]

# Admin
obserwator admin keys
obserwator admin create --name <name> [--limit]
obserwator admin revoke <key_id>
obserwator admin delete <key_id> [--force]
obserwator admin stats [key_id]

# Versioned store (--root or OBSERWATOR_ROOT)
obserwator store init|info --root <dir>
obserwator store scan --root <dir> [-k archive|series|catalog|pmaxtp|observation|problem] [--provider IMGW-PIB|CHMI]
obserwator store check --root <dir> -d <keys> [-y <years>] [-m <months>] [-s <stations>] [--plan plan.json]
obserwator store sync --root <dir> (--plan plan.json | -d <keys> [-y <years>] [-s <stations>]) [--no-series] [--check]
obserwator store catalog --root <dir> [--provider IMGW-PIB|CHMI] [--user-locations <csv>] [--check]
obserwator store export --version <archive version> [--format csv|jsonl] [--output <file> [--force]]
obserwator series build --root <dir> -d <key> [--check]
obserwator series select --root <dir> -d <key> -s <codes> [--variables] [-y <years>] [--year-type]
obserwator series read|summary [--version <v> | --root <dir> -d <key>] -s <code(s)> [--variables]
obserwator series export [--version <v> | --root <dir> -d <key>] -s <code> [--variables] [--output <csv> [--force]]
obserwator pmaxtp check|sync --root <dir> --lat <lat> --lon <lon> [--method POT|AMP]
obserwator pmaxtp read --root <dir> --ind-x <x> --ind-y <y> [--method POT|AMP]

# Command catalog
obserwator commands list [--lang pl|en]
obserwator commands schema [--command "<group> <name>"] [--lang pl|en]
obserwator commands guide [-f agents|llms] [--lang pl|en] [--output <file> [--force]]
```

---

## 7. Non-Functional Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| No server-side data storage by default | Implemented | Core design principle: URL generation and live proxy; data is stored only with explicit configuration (`OBSERWATOR_ROOT`, CLI `--root`/`--output`) |
| PEP8 compliance | Implemented | Using ruff |
| NumPy-style docstrings | Implemented | Enforced by ruff `D` rules, numpy convention |
| Unit and contract tests | Implemented | 2446 tests in `/tests/unit` and `/tests/contract`, all offline (2026-10-31); Python = CLI = REST = MCP contract |
| Live integration tests | Implemented | 67 tests marked `live` (outside the gate, run with `-m live`): `tests/live/test_interfaces_live.py` (45: 30 commands × Python/`obserwator`/REST on real IMGW-PIB servers, live errors, MCP leg) and `tests/live/test_chmi_live.py` (22: ČHMÚ on opendata.chmi.cz) |
| API response time < 2s | Implemented | For proxied requests |
| Online documentation | Implemented | Swagger at `/docs` |

---

## 8. Out of Scope

The following are explicitly out of scope for this project:
- Advanced hydrological and statistical analyses
- Predictive models
- Machine learning
- Raster processing
- Stream data processing
- User authentication/accounts (MCP over HTTP is read-only; writes need a local `obserwator mcp --allow-writes`)

**Note:** The optional SQLite cache of 2.x was removed in 3.0.0 and replaced by the file-based versioned store (ADR-001); no database is part of the product.

---

## 9. KPIs

| KPI | Target | Current Status |
|-----|--------|----------------|
| API response time (proxied) | < 2s | Met |
| API documentation completeness | 100% | Met (Swagger) |
| Test coverage | 80% | 93% (measured 2026-10-18, before ADR-002 changes) |
| Stability (no critical bugs) | 30 days | In progress |

---

## 10. Versioning

- SemVer for API and CLI/GUI package
- Current version: 3.0.0 (release notes: `docs/CHANGELOG.md`)
- Contracts (`obserwator-store/1`, `obserwator-meta/1`, `obserwator-series/1`, `obserwator-plan/1`, `obserwator-pmaxtp/1`, `obserwator-observation/1`, `obserwator-result/1`, `obserwator-commands/1`) carry their own `/N` versions, independent of the package version (IMGW-13); ČHMÚ and agent support add only optional fields within `/1`; the project manifest contract left with the projects (ADR-008)

---

## 11. Future Enhancements (Backlog)

The backlog is maintained exclusively in `docs/PROGRESS.md` (section "Next") — the single source of truth for pending work.
