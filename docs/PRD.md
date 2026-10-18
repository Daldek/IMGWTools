# IMGWTools — PRD (Product Requirements Document)

## 1. Product Goal

IMGWTools is a tool for downloading, exposing, versioning and basic visualization of hydrological and meteorological data published by IMGW-PIB. The product provides:
- Python library (public API)
- CLI application
- Web GUI application
- Public REST API
- Optional versioned data store (ADR-001, `docs/DECISIONS.md`) for consumers such as Archiwista and Retman

Analytical and statistical parts (hydrological calculations, probabilistic models, statistical analyses) live in a separate repository (Hydrolog) and are out of scope for this PRD.

---

## 2. Stakeholders

- Individual users interested in IMGW data
- GIS specialists
- Developers requiring API access to data
- Downstream projects: Hydrograf, Hydrolog, Archiwista (store reader), Retman (command handler)
- Service administrator (owner)

---

## 3. Functional Scope

### 3.1. Data Access

| Feature | Status | Description |
|---------|--------|-------------|
| Real-time data (IMGW API) | Implemented | Current hydro/meteo/synop data |
| Archive data (ZIP/CSV) | Implemented | URL generation for IMGW archives |
| PMAXTP data | Implemented | Probabilistic max precipitation |
| Warnings | Implemented | Hydro/meteo warnings from API |
| Versioned store | Implemented (3.0.0) | Immutable archive versions with provenance, freshness plan, Parquet series, `stations.geojson`, PMAXTP cells, projects |

### 3.2. Interfaces

| Interface | Status | Description |
|-----------|--------|-------------|
| CLI | Implemented | `imgw` command with fetch/list/admin/store/series/pmaxtp/project subcommands |
| Web GUI | Implemented | HTMX + Jinja2 web interface |
| REST API | Implemented | FastAPI with OpenAPI documentation |

### 3.3. Visualization

| Feature | Status | Description |
|---------|--------|-------------|
| Interactive map | Implemented | Leaflet.js with station markers |
| Station listings | Implemented | Searchable tables |
| Data charts | Not Implemented | Future enhancement |

### 3.4. Data Export

| Format | Status | Description |
|--------|--------|-------------|
| JSON | Implemented | All API responses |
| URLs | Implemented | Direct links to IMGW servers |
| CSV | Implemented | PMAXTP export in the Web GUI; station series export (`export_series`, `imgw series export`) with units and IMGW-PIB attribution |
| GeoJSON | Implemented (store) | Versioned `stations.geojson` station catalog (RFC 7946); not yet exposed in REST/GUI |
| Parquet | Implemented (store) | Station series per dataset (`imgw-series/1`, `imgwtools[store]`) |

---

## 4. REST API — Requirements

### Implemented

| Requirement | Status |
|-------------|--------|
| OpenAPI/Swagger documentation | Implemented |
| API versioning (`/api/v1/`) | Implemented |
| Hydro data endpoints | Implemented |
| Meteo data endpoints | Implemented |
| PMAXTP endpoints | Implemented |
| Health check | Implemented |
| Store endpoints (`/api/v1/store`, `/api/v1/series`, `/api/v1/pmaxtp/store`) | Implemented — only with server-side `IMGW_STORE_ROOT`; writes need `IMGW_STORE_WRITES_ENABLED` + write token |

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
| Download forms (hydro/meteo/PMAXTP) | Implemented |
| Station listings with search | Implemented |
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
| `imgw fetch` command | Implemented |
| `imgw list` command | Implemented |
| `imgw admin` command | Implemented |
| `imgw server` command | Implemented |
| `imgw store`, `imgw series`, `imgw pmaxtp`, `imgw project` | Implemented (3.0.0, generated from the command catalog) |
| `--check` (plan only, no writes) | Implemented |
| `--output` flag | Implemented |
| `--station` filtering | Implemented |
| Progress bars | Implemented |

### Commands Available

```bash
# Main commands
imgw version
imgw server [--host] [--port] [--reload]

# Fetch data
imgw fetch hydro -i <interval> -y <year|range> [-m month] [-p param] [-o output] [--check]
imgw fetch meteo -i <interval> -s <subtype> -y <year|range> [-m month] [-o output] [--check]
imgw fetch current <type>  # hydro, meteo, synop
imgw fetch pmaxtp --lat <lat> --lon <lon> [--method POT|AMP]
imgw fetch warnings --type <hydro|meteo>

# List resources
imgw list stations --type <hydro|meteo> [--search] [--limit]
imgw list datasets [--type]
imgw list intervals

# Admin
imgw admin keys
imgw admin create --name <name> [--limit]
imgw admin revoke <key_id>
imgw admin delete <key_id> [--force]
imgw admin stats [key_id]

# Versioned store (explicit --root)
imgw store init|info|scan --root <dir>
imgw store check --root <dir> --dataset <keys> --years <range> [--months] [--plan plan.json]
imgw store sync --root <dir> (--plan plan.json | --dataset <keys> --years <range>) [--no-series]
imgw store catalog --root <dir> [--user-locations <csv>]
imgw series build --root <dir> --dataset <key>
imgw series select --root <dir> --dataset <key> --stations <codes> [--variables] [--years] [--year-type]
imgw series export --version <series version> --station <code> --path <csv> --variables <list> [--year-type]
imgw pmaxtp check|sync --root <dir> --method POT|AMP --lat <lat> --lon <lon>
imgw pmaxtp read --root <dir> --method POT|AMP --ind-x <x> --ind-y <y>
imgw project init|add|remove|set-store|download|check|status|verify --project-dir <dir> ...
```

---

## 7. Non-Functional Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| No server-side data storage by default | Implemented | Core design principle: URL generation and live proxy; data is stored only with explicit configuration (`IMGW_STORE_ROOT`, CLI `--root`/`--output`) |
| PEP8 compliance | Implemented | Using ruff |
| NumPy-style docstrings | Implemented | Enforced by ruff `D` rules, numpy convention |
| Unit tests | Implemented | 998 tests in `/tests/unit` and `/tests/contract`, all offline (2026-10-18) |
| Integration tests | Not Implemented | Planned as a separate task |
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
- User authentication/accounts

**Note:** The optional SQLite cache of 2.x was removed in 3.0.0 and replaced by the file-based versioned store (ADR-001); no database is part of the product.

---

## 9. KPIs

| KPI | Target | Current Status |
|-----|--------|----------------|
| API response time (proxied) | < 2s | Met |
| API documentation completeness | 100% | Met (Swagger) |
| Test coverage | 80% | 93% (measured 2026-10-18) |
| Stability (no critical bugs) | 30 days | In progress |

---

## 10. Versioning

- SemVer for API and CLI/GUI package
- Current version: 3.0.0 (release notes: `docs/CHANGELOG.md`)
- Store schemas (`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`) carry their own `/N` versions, independent of the package version (IMGW-13)

---

## 11. Future Enhancements (Backlog)

The backlog is maintained exclusively in `docs/PROGRESS.md` (section "Backlog") — the single source of truth for pending work.
