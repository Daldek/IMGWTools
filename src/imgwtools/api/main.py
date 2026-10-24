"""
Main FastAPI application of IMGWTools: catalog routes, system routes, web GUI, MCP.

The catalog routes ``/api/v1/<group>/<command>`` come from
`imgwtools.api.routes.commands`; ``GET /health`` and ``GET /api/v1`` describe the
server, ``GET /llms.txt`` is the agent guide in the llms.txt format in the
language of ``Accept-Language`` (spec 2026-10-19 §5.8). With
``IMGW_MCP_ENABLED=true`` and the ``mcp`` extra, ``/mcp`` serves the MCP server
in mode ``http`` (Streamable HTTP, spec §6.2, §6.9), in English like every MCP
server; its session manager runs in the lifespan of this application.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.applications import Starlette

from imgwtools._version import __version__
from imgwtools.agent_guide import agent_guide
from imgwtools.api.errors import EXCEPTION_HANDLERS, accept_language
from imgwtools.api.routes import commands
from imgwtools.api.schemas import HealthCheck
from imgwtools.commands import command_schema
from imgwtools.config import check_config, settings
from imgwtools.web.app import router as web_router

_LOG = logging.getLogger(__name__)

# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

# API metadata
API_TITLE = "IMGWTools API"
API_DESCRIPTION = """
API danych publicznych IMGW-PIB i ČHMÚ generowane z katalogu komend IMGWTools.

## Trasy

* `GET|POST /api/v1/<grupa>/<komenda>` — jedna trasa na komendę katalogu
  (`imgw <grupa> <komenda>` w CLI); lista tras: `GET /api/v1`, opis opcji:
  `GET /api/v1/commands/schema`.
* `GET /llms.txt` — przewodnik dla agentów AI w formacie llms.txt (język z
  nagłówka `Accept-Language`: `pl` albo `en`).
* `/mcp` — serwer MCP (Streamable HTTP) z trasami katalogu jako narzędziami,
  gdy administrator ustawi `IMGW_MCP_ENABLED=true`; zapis tylko jako plan.
* Odpowiedź: koperta `imgw-result/1` (`schema`, `command`, `check`, `status`,
  `result`, `notices`); status `partial`/`failed` też ma kod 200, więc czytaj
  pole `status`. `store export` i `series export` zwracają strumień CSV/JSONL
  z nagłówkami `X-IMGW-Status` i `X-IMGW-Notices`.
* Komendy listowe stronicują `limit` (domyślnie i najwyżej `IMGW_API_MAX_LIMIT`)
  i `offset`.
* Błędy: `application/problem+json` (RFC 9457) z polami `code` i `details`.

## Magazyn

Domyślnie dane NIE są przechowywane na serwerze: API generuje bezpośrednie
linki do serwerów IMGW-PIB i ČHMÚ, a dane bieżące odczytuje na żywo. Komendy
magazynu działają wyłącznie na magazynie wskazanym przez administratora w
`IMGW_STORE_ROOT` (bez niego 503 `store_unavailable`). Zapis (POST bez
`?check=true`) jest domyślnie wyłączony (403 `forbidden`): wymaga
`IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` i nagłówka
`X-API-Key`; `?check=true` zwraca plan `imgw-plan/1` bez zapisu i bez tokenu.
"""
API_VERSION = __version__


def _mcp_app() -> Starlette | None:
    """
    Streamable HTTP application of ``/mcp`` (spec 2026-10-19 §6.2).

    Returns
    -------
    starlette.applications.Starlette or None
        The MCP server in mode ``http``; None unless ``IMGW_MCP_ENABLED=true`` and
        the ``mcp`` extra is installed (``/mcp`` is then an unknown route: 404
        ``not_found``).
    """
    if not settings.mcp_enabled:
        return None
    try:
        from imgwtools.mcp.server import http_app
    except ImportError:
        _LOG.warning(
            "IMGW_MCP_ENABLED=true, ale serwer MCP wymaga dodatku: pip install "
            "imgwtools[mcp]; trasa /mcp nie istnieje"
        )
        return None
    return http_app()


_MCP = _mcp_app()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Check ``nogat.toml``, then run the session manager of ``/mcp`` with the app."""
    check_config()  # an unusable settings file stops the server instead of being ignored
    # A route of another application never runs its lifespan by itself.
    async with nullcontext() if _MCP is None else _MCP.router.lifespan_context(_MCP):
        yield


def _operation_id(route: APIRoute) -> str:
    """``operationId`` of a route outside the catalog: ``imgw_system_<function>``."""
    # Catalog routes name their id themselves (imgw_<group>_<verb>, AGI-6.2).
    return f"imgw_system_{route.name}"


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
        {"name": "System", "description": "Stan serwera, lista tras i przewodnik"},
    ],
    exception_handlers=EXCEPTION_HANDLERS,
    lifespan=_lifespan,
    generate_unique_id_function=_operation_id,
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

if _MCP is not None:
    # Only the /mcp route: a mount at "/" would answer unknown paths with a
    # plain 404 instead of the problem document.
    app.router.routes.extend(_MCP.routes)


@app.get("/health", response_model=HealthCheck, tags=["System"], summary="Stan serwera")
async def health_check() -> HealthCheck:
    """Stan serwera i wersja pakietu."""
    return HealthCheck(status="ok", version=API_VERSION)


@app.get("/api/v1", tags=["System"], summary="Trasy API")
async def api_info() -> dict[str, object]:
    """Lista tras katalogu komend."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "schema": "/api/v1/commands/schema",
        "routes": commands.catalog_routes(),
    }


@app.get(
    "/llms.txt",
    tags=["System"],
    summary="Przewodnik llms.txt",
    response_class=Response,
    responses={
        200: {
            "description": "Przewodnik w formacie llms.txt (markdown)",
            "content": {"text/markdown": {"schema": {"type": "string"}}},
        }
    },
)
async def llms_txt(request: Request) -> Response:
    """
    Przewodnik dla agentów AI w formacie llms.txt.

    Język wybiera nagłówek Accept-Language: pl albo en, domyślnie pl.
    """
    lang = accept_language(request.headers.get("accept-language"))
    response = Response(
        "".join(agent_guide(format="llms", lang=lang)),
        media_type="text/markdown; charset=utf-8",
    )
    response.headers["Content-Language"] = lang
    response.headers.add_vary_header("Accept-Language")
    return response


def run_server() -> None:
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
