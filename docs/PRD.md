# IMGWTools — PRD (Product Requirements Document)

## 1. Product Goal

IMGWTools is a tool for downloading, exposing, and basic visualization of hydrological and meteorological data published by IMGW-PIB. The product provides:
- CLI application
- Web GUI application
- Public REST API

Analytical and statistical parts (hydrological calculations, probabilistic models, statistical analyses) will be separated into another repository and are out of scope for this PRD.

---

## 2. Stakeholders

- Individual users interested in IMGW data
- GIS specialists
- Developers requiring API access to data
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

### 3.2. Interfaces

| Interface | Status | Description |
|-----------|--------|-------------|
| CLI | Implemented | `imgw` command with fetch/list/admin subcommands |
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
| CSV | Not Implemented | Direct CSV export |
| GeoJSON | Not Implemented | GIS-compatible format |

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
| `--output` flag | Implemented |
| `--station` filtering | Implemented |
| Progress bars | Implemented |

### Commands Available

```bash
# Main commands
imgw version
imgw server [--host] [--port] [--reload]

# Fetch data
imgw fetch hydro -i <interval> -y <year> [-m month] [-p param] [-o output]
imgw fetch meteo -i <interval> -s <subtype> -y <year> [-m month] [-o output]
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
```

---

## 7. Non-Functional Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| No server-side data storage | Implemented | Core design principle |
| PEP8 compliance | Implemented | Using ruff |
| NumPy-style docstrings | Partial | Some modules |
| Unit tests | Partial | Basic tests in `/tests` |
| Integration tests | Not Implemented | - |
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

**Note:** Optional SQLite caching for hydrological data has been implemented (`IMGW_DB_ENABLED=true`).

---

## 9. KPIs

| KPI | Target | Current Status |
|-----|--------|----------------|
| API response time (proxied) | < 2s | Met |
| API documentation completeness | 100% | Met (Swagger) |
| Test coverage | 80% | Not measured |
| Stability (no critical bugs) | 30 days | In progress |

---

## 10. Versioning

- SemVer for API and CLI/GUI package
- Current version: 1.0.0

---

## 11. Future Enhancements (Backlog)

1. **API Key Enforcement** - Middleware to validate X-API-Key header
2. **Per-Key Rate Limiting** - Track and limit requests per API key
3. **GeoJSON Export** - Return data in GIS-compatible format
4. **Data Charts** - Visualize time series data
5. **CSV Direct Export** - Export data directly as CSV
6. **Request Logging** - Track API usage for analytics
7. **Caching Layer** - Redis cache for frequently accessed data
