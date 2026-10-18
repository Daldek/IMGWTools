"""Main FastAPI application for IMGWTools REST API."""

from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from imgwtools._version import __version__
from imgwtools.api.errors import EXCEPTION_HANDLERS
from imgwtools.api.routes import commands
from imgwtools.api.schemas import HealthCheck
from imgwtools.commands import command_schema
from imgwtools.config import settings
from imgwtools.web.app import router as web_router

# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

# API metadata
API_TITLE = "IMGWTools API"
API_DESCRIPTION = """
API danych publicznych IMGW-PIB generowane z katalogu komend IMGWTools.

## Trasy

* `GET|POST /api/v1/<grupa>/<komenda>` — jedna trasa na komendę katalogu
  (`imgw <grupa> <komenda>` w CLI); lista tras: `GET /api/v1`, opis opcji:
  `GET /api/v1/commands/schema`.
* Odpowiedź: koperta `imgw-result/1` (`schema`, `command`, `check`, `status`,
  `result`, `notices`); status `partial`/`failed` też ma kod 200, więc czytaj
  pole `status`. `store export` i `series export` zwracają strumień CSV/JSONL
  z nagłówkami `X-IMGW-Status` i `X-IMGW-Notices`.
* Komendy listowe stronicują `limit` (domyślnie i najwyżej `IMGW_API_MAX_LIMIT`)
  i `offset`.
* Błędy: `application/problem+json` (RFC 9457) z polami `code` i `details`.

## Magazyn

Domyślnie dane NIE są przechowywane na serwerze: API generuje bezpośrednie
linki do serwerów IMGW i odczytuje dane bieżące na żywo. Komendy magazynu
działają wyłącznie na magazynie wskazanym przez administratora w
`IMGW_STORE_ROOT` (bez niego 503 `store_unavailable`). Zapis (POST bez
`?check=true`) jest domyślnie wyłączony (403 `forbidden`): wymaga
`IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` i nagłówka
`X-API-Key`; `?check=true` zwraca plan `imgw-plan/1` bez zapisu i bez tokenu.
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
    openapi_tags=[
        *(
            {"name": group, "description": text}
            for group, text in cast(dict[str, str], command_schema()["groups"]).items()
        ),
        {"name": "System", "description": "Stan serwera i lista tras"},
    ],
    exception_handlers=EXCEPTION_HANDLERS,
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

# Catalog routes /api/v1/<group>/<command>
app.include_router(commands.router)

# Include Web GUI router
app.include_router(web_router)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health", response_model=HealthCheck, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthCheck(status="ok", version=API_VERSION)


@app.get("/api/v1", tags=["System"])
async def api_info() -> dict[str, object]:
    """List the catalog routes of the API."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "schema": "/api/v1/commands/schema",
        "routes": commands.catalog_routes(),
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
