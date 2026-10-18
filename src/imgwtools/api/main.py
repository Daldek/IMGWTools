"""Main FastAPI application for IMGWTools REST API."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from imgwtools._version import __version__
from imgwtools.api.routes import download, hydro, meteo, pmaxtp, store
from imgwtools.api.schemas import HealthCheck
from imgwtools.config import settings
from imgwtools.web.app import router as web_router

# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

# API metadata
API_TITLE = "IMGWTools API"
API_DESCRIPTION = """
API do pobierania danych publicznych z IMGW-PIB.

## Funkcjonalnosci

* **Stacje** - lista stacji hydrologicznych i meteorologicznych
* **Dane biezace** - aktualne dane z API IMGW
* **Pobieranie** - generowanie linkow do pobierania danych archiwalnych
* **PMAXTP** - dane o opadach maksymalnych prawdopodobnych
* **Magazyn** - wersjonowany magazyn danych IMGW na serwerze (opcjonalny)

## Wazne

Domyslnie dane NIE sa przechowywane na serwerze. API generuje bezposrednie
linki do serwerow IMGW, skad uzytkownik pobiera dane na swoj komputer.

Trasy `/api/v1/store`, `/api/v1/series` i `/api/v1/pmaxtp/store` dzialaja
wylacznie na magazynie wskazanym przez administratora w `IMGW_STORE_ROOT`
(bez tego ustawienia zwracaja 503). Zapis jest domyslnie wylaczony (403):
wymaga `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` oraz
naglowka `X-API-Key`. Bledy tych tras: `{"code": ..., "detail": ...}`.
"""
API_VERSION = __version__

# Create FastAPI app
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(hydro.router, prefix="/api/v1/hydro", tags=["Hydrologia"])
app.include_router(meteo.router, prefix="/api/v1/meteo", tags=["Meteorologia"])
app.include_router(download.router, prefix="/api/v1/download", tags=["Pobieranie"])
app.include_router(pmaxtp.router, prefix="/api/v1/pmaxtp", tags=["PMAXTP"])
app.include_router(store.router, prefix="/api/v1/store", tags=["Magazyn"])
app.include_router(store.series_router, prefix="/api/v1/series", tags=["Magazyn"])
app.include_router(store.pmaxtp_router, prefix="/api/v1/pmaxtp/store", tags=["Magazyn"])
app.add_exception_handler(store.StoreAPIError, store.store_error_handler)

# Include Web GUI router
app.include_router(web_router)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health", response_model=HealthCheck, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthCheck(status="ok", version=API_VERSION)


@app.get("/api/v1", tags=["System"])
async def api_info():
    """API information."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "endpoints": {
            "hydro": "/api/v1/hydro",
            "meteo": "/api/v1/meteo",
            "download": "/api/v1/download",
            "pmaxtp": "/api/v1/pmaxtp",
            "store": "/api/v1/store",
            "series": "/api/v1/series",
            "pmaxtp_store": "/api/v1/pmaxtp/store",
        },
    }


def run_server():
    """Run the API server."""
    import uvicorn

    uvicorn.run(
        "imgwtools.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=not settings.is_production,
    )


if __name__ == "__main__":
    run_server()
