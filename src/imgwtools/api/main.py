"""
Main FastAPI application for IMGWTools REST API.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from imgwtools.api.routes import hydro, meteo, download, pmaxtp
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

## Wazne

Dane NIE sa przechowywane na serwerze. API generuje bezposrednie linki
do serwerow IMGW, skad uzytkownik pobiera dane na swoj komputer.
"""
API_VERSION = "1.0.0"

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
