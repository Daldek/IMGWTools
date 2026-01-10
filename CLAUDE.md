# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IMGWTools is a Python tool for downloading public data from IMGW (Polish Institute of Meteorology and Water Management). It provides three interfaces:
- **CLI** - Command-line tool for local data downloading
- **REST API** - FastAPI-based API for generating download URLs
- **Web GUI** - HTMX + Jinja2 web interface

**Key principle:** Data is NEVER stored on the server. The service generates direct links to IMGW servers, and users download data directly from IMGW.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run API server
imgw server --reload

# Run tests
pytest

# Lint code
ruff check src/

# CLI examples
imgw version                                    # Show version
imgw server --host 0.0.0.0 --port 8000         # Run API server
imgw fetch hydro -i dobowe -y 2023 -m 1        # Download daily hydro data
imgw fetch meteo -i miesieczne -s synop -y 2023 # Download monthly meteo data
imgw fetch current hydro                        # Get current hydro data from API
imgw fetch pmaxtp --lat 52.23 --lon 21.01      # Get PMAXTP data
imgw fetch warnings --type hydro               # Get hydro warnings
imgw list stations --type hydro                # List hydro stations
imgw list datasets                             # List available datasets
imgw list intervals                            # List available intervals
imgw admin keys                                # List API keys
imgw admin create --name "User1"               # Create API key
imgw admin revoke <key_id>                     # Revoke API key
imgw admin delete <key_id>                     # Delete API key
imgw admin stats                               # Show API key statistics
```

## Architecture

```
src/imgwtools/
├── api/                  # FastAPI REST API
│   ├── main.py           # App entry point
│   ├── routes/           # Endpoint handlers
│   │   ├── hydro.py      # Hydrological data
│   │   ├── meteo.py      # Meteorological data
│   │   ├── download.py   # Unified URL generation
│   │   └── pmaxtp.py     # Max precipitation
│   └── schemas.py        # Pydantic models
├── cli/                  # Typer CLI
│   ├── main.py           # Entry point (imgw command)
│   ├── fetch.py          # Download commands (hydro, meteo, current, pmaxtp, warnings)
│   ├── list_cmd.py       # Listing commands (stations, datasets, intervals)
│   └── admin.py          # API key management (keys, create, revoke, delete, stats)
├── core/                 # Core logic
│   ├── url_builder.py    # URL generation (key module!)
│   ├── imgw_api.py       # Legacy IMGW API classes
│   ├── imgw_datastore.py # Legacy downloader
│   └── imgw_spatial.py   # Spatial utilities
├── web/                  # Web GUI (HTMX + Jinja2)
│   ├── app.py            # Web routes
│   ├── templates/        # Jinja2 templates
│   └── static/           # CSS, JavaScript
└── config.py             # Settings (pydantic-settings)
```

### Key Module: `url_builder.py`

The `url_builder.py` module is the core of the application. It contains:
- `build_hydro_url()` - Generates URLs for hydrological data
- `build_meteo_url()` - Generates URLs for meteorological data
- `build_pmaxtp_url()` - Generates URLs for PMAXTP API
- `build_api_url()` - Generates URLs for IMGW real-time API

## Data Flow

```
User → CLI/API/Web → URL Builder → IMGW Servers → User's computer
                          ↓
                   (generates links only)
```

No data is stored on our server - only metadata (station lists) from local CSV files.

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
| `/methods` | GET | List available PMAXTP methods |
| `/url` | POST | Generate PMAXTP URL |
| `/data` | POST | Fetch PMAXTP data |

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
| `/stations` | Stations list page |
| `/map` | Interactive map with stations |

## CLI Commands

### Main Commands

| Command | Description |
|---------|-------------|
| `imgw version` | Show version |
| `imgw server` | Run API server (`--host`, `--port`, `--reload`) |

### Fetch Commands (`imgw fetch`)

| Command | Description |
|---------|-------------|
| `fetch hydro` | Download hydro data (`-i interval`, `-y year`, `-m month`, `-p param`, `-o output`) |
| `fetch meteo` | Download meteo data (`-i interval`, `-s subtype`, `-y year`, `-m month`, `-o output`) |
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

## IMGW Data Structure

### Hydrological data (1951-2024+)
- `dobowe` (daily):
  - Before 2023: `codz_{year}_{month:02d}.zip` (monthly files)
  - From 2023: `codz_{year}.zip` (single yearly file)
- `miesieczne` (monthly): `mies_{year}.zip`
- `polroczne_i_roczne` (semi-annual): `polr_{param}_{year}.zip` (param: T, Q, H)

### Meteorological data (1951-current)

**Years 1951-2000:**
- Folder structure: 5-year folders (e.g., `1951_1955`, `1956_1960`, ..., `1996_2000`)
- File format: `{year}_{subtype}.zip` (yearly files, no monthly split)

**Years 2001+:**
- Folder structure: yearly folders (e.g., `2023`)
- `dobowe` (daily): `{year}_{month:02d}_{subtype}.zip`
- `miesieczne` (monthly): `{year}_m_{subtype}.zip`
- `terminowe` (hourly): `{year}_{month:02d}_{subtype}.zip`

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

**Note:** API key validation middleware is not yet implemented. Keys are managed via CLI but not enforced in API requests.

### API versioning
Wszystkie endpointy pod `/api/v1/...`
