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
- ~~Redis (cache)~~ - not needed, no server-side caching
- ~~PostgreSQL~~ - not needed, no persistent storage

### Key Design Principle
**No data storage on server.** The backend only:
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

## 7. Data Formats

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

## 8. Scaling Considerations

Current architecture is simple and stateless:
- No session state
- No database
- No cache layer

Scaling options if needed:
- Horizontal scaling of FastAPI instances behind Nginx
- CDN for static files
- Add Redis if caching becomes necessary

---

## 9. CI/CD

### Recommended Setup
- pytest for automated testing
- ruff for linting (PEP8 compliance)
- GitHub Actions for CI pipeline
- Docker for deployment

---

## 10. File Structure

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
│   │   └── admin.py      # API key management
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
