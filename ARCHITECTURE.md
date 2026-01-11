# IMGWTools — Architecture

## 1. Architecture Model

System consists of three main components:

1. **Backend (FastAPI)**
   - URL generation for IMGW data downloads
   - Proxy for real-time IMGW API data
   - REST API for external integrations
   - Rate limiting via Nginx

2. **Frontend Web (GUI)**
   - HTMX + Jinja2 templates
   - Interactive forms for data downloads
   - Station listings and search
   - Interactive map with Leaflet.js

3. **CLI**
   - Local client using core library directly
   - Data downloading to local filesystem
   - API key management

4. **Database Cache** (optional)
   - SQLite-based caching for hydrological data
   - Lazy loading - data fetched on first query
   - Enabled via `IMGW_DB_ENABLED=true`

---

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         IMGW Public API                          │
│              (danepubliczne.imgw.pl, hydro.imgw.pl)              │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTP requests
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      IMGWTools Backend                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    FastAPI Application                     │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │   │
│  │  │ API Routes │  │ Web Routes │  │   URL Builder      │  │   │
│  │  │ /api/v1/*  │  │   /*       │  │   (core module)    │  │   │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │   │
│  │                                   ┌────────────────────┐  │   │
│  │                                   │   DB Cache (opt)   │  │   │
│  │                                   │   (SQLite hydro)   │  │   │
│  │                                   └────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▲                                   │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                        Nginx                              │   │
│  │              (reverse proxy, HTTPS, rate limiting)        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTPS
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │   CLI   │          │ Web GUI │          │ API     │
   │ (local) │          │ Browser │          │ Clients │
   └─────────┘          └─────────┘          └─────────┘
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

### Technologies (Not Implemented)
- ~~Redis (cache)~~ - not needed for general caching
- ~~PostgreSQL~~ - SQLite sufficient for optional local cache

### Optional: SQLite Cache
- **Purpose**: Cache hydrological data locally for repeated queries
- **Activation**: `IMGW_DB_ENABLED=true`
- **Location**: `IMGW_DB_PATH` (default: `./data/imgw_hydro.db`)
- **Mode**: Lazy loading - data fetched from IMGW on first access

### Key Design Principle
**No data storage on server by default.** The backend only:
1. Generates URLs pointing to IMGW servers
2. Proxies real-time API requests to IMGW
3. Returns results directly to client

---

## 4. REST API

### Implemented Features
- Hydro/Meteo station listings
- Real-time data from IMGW API
- Download URL generation (single and batch)
- PMAXTP data access
- OpenAPI/Swagger documentation (`/docs`)
- Health check endpoint

### Security (Current State)
- Rate limiting via Nginx (`limit_req_zone`)
- CORS middleware configured
- GZip compression enabled

### Security (Planned, Not Implemented)
- ~~API key validation middleware~~ - keys managed but not enforced
- ~~Per-key rate limiting~~ - only nginx-level limiting

---

## 5. Web GUI Layer

### Technologies (Implemented)
- **HTMX** - dynamic updates without full page reloads
- **Jinja2** - server-side templating
- **Leaflet.js** - interactive maps
- **Vanilla CSS** - styling

### Available Pages
- `/` - Dashboard
- `/download` - Download forms (hydro, meteo, PMAXTP)
- `/stations` - Station listings with search
- `/map` - Interactive map with station markers

---

## 6. CLI Layer

### Technologies
- **Typer** - CLI framework
- **Rich** - terminal formatting and progress bars
- **HTTPX** - HTTP client

### Architecture
CLI uses core library (`url_builder.py`) directly for URL generation and downloads data straight from IMGW servers. It does NOT communicate through the REST API.

---

## 7. Database Layer (Optional)

SQLite-based cache for hydrological data. Disabled by default.

### Architecture
```
┌─────────────────────────────────────────────────┐
│                 Cache Manager                    │
│   (downloads from IMGW, parses ZIP, imports)    │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│                  Repository                      │
│     (CRUD operations, queries, batch insert)    │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│                   SQLite DB                      │
│  ┌──────────────┐ ┌──────────────────────────┐  │
│  │ hydro_stations│ │ hydro_daily/monthly/semi │  │
│  └──────────────┘ └──────────────────────────┘  │
│  ┌──────────────────────────────────────────┐   │
│  │           cached_ranges                   │   │
│  │    (tracks which data has been cached)    │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Data Tables
| Table | Description |
|-------|-------------|
| `hydro_stations` | Station metadata (code, name, river, coordinates) |
| `hydro_daily` | Daily measurements (water level, flow, temperature) |
| `hydro_monthly` | Monthly aggregates (min/mean/max) |
| `hydro_semi_annual` | Semi-annual/annual extrema |
| `cached_ranges` | Tracks which year/month combinations are cached |

### Lazy Loading Flow
1. User queries data for station X, years 2020-2023
2. System checks `cached_ranges` for each year
3. Missing years: download ZIP from IMGW → parse CSV → insert
4. Query data from local SQLite → return results

### CSV Parsing Notes
- Encoding: CP1250 (Polish Windows)
- Delimiter: Semicolon (`;`)
- Missing data codes: `9999` (H), `99999.999` (Q), `99.9` (T)
- Hydrological year: Nov 1 - Oct 31

---

## 8. Data Formats

### Input (from IMGW)
- ZIP archives with CSV files
- JSON from real-time API

### Output (to clients)
- JSON (all API responses)
- Generated URLs (for direct IMGW downloads)

### Potential GIS Integration
- Station coordinates available in API responses
- Map visualization implemented with Leaflet
- ~~WFS/WMS integration~~ - not implemented

---

## 9. Scaling Considerations

Current architecture is simple and mostly stateless:
- No session state
- Optional SQLite database (local cache only)
- No distributed cache layer

Scaling options if needed:
- Horizontal scaling of FastAPI instances behind Nginx
- CDN for static files
- SQLite DB per instance (each instance has its own cache)
- Add Redis for shared caching across instances

---

## 10. CI/CD

### Recommended Setup
- pytest for automated testing
- ruff for linting (PEP8 compliance)
- GitHub Actions for CI pipeline
- Docker for deployment

---

## 11. File Structure

```
IMGWTools/
├── src/imgwtools/
│   ├── api/              # REST API
│   │   ├── main.py       # FastAPI app
│   │   ├── routes/       # Endpoint handlers
│   │   └── schemas.py    # Pydantic models
│   ├── cli/              # CLI commands
│   │   ├── main.py       # Entry point
│   │   ├── fetch.py      # Download commands
│   │   ├── list_cmd.py   # Listing commands
│   │   ├── admin.py      # API key management
│   │   └── db.py         # Database management
│   ├── db/               # SQLite cache (optional)
│   │   ├── connection.py # Connection manager
│   │   ├── schema.py     # DDL and migrations
│   │   ├── models.py     # Pydantic models
│   │   ├── repository.py # Data access layer
│   │   ├── cache_manager.py # Lazy loading
│   │   └── parsers.py    # CSV parsing
│   ├── core/             # Core logic
│   │   ├── url_builder.py    # URL generation
│   │   ├── imgw_api.py       # Legacy API
│   │   ├── imgw_datastore.py # Legacy downloader
│   │   └── imgw_spatial.py   # Spatial utils
│   ├── web/              # Web GUI
│   │   ├── app.py        # HTMX routes
│   │   ├── templates/    # Jinja2 templates
│   │   └── static/       # CSS, JS
│   └── config.py         # Settings
├── docker/               # Docker configuration
├── tests/                # Test files
└── pyproject.toml        # Project configuration
```
