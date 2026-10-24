"""
MCP server of IMGWTools: the commands of the catalog as tools (spec 2026-10-19 §6).

Built on the low-level ``Server`` of the official SDK (``mcp`` 2.x): the tool
schemas are exactly those of the catalog and `validate_command` stays the only
validator. Modes (spec §6.3): ``read`` (default of ``imgw mcp``) offers every
command, writing ones only as a plan, ``write`` (``imgw mcp --allow-writes``)
plans by default and writes with ``check: false``, ``http`` (``/mcp`` of ``imgw
server``) offers the REST routes, POST ones only as a plan. The tool list is
fixed for the server: language, mode and ``IMGW_STORE_ROOT`` are read once when
the server is created. The instructions of the server are the rules of the
agent guide with the lines of the mode.
"""

from __future__ import annotations

import os
from pathlib import Path

import anyio
import mcp.types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from starlette.applications import Starlette

from imgwtools._version import __version__
from imgwtools.agent_guide import _instructions
from imgwtools.config import settings
from imgwtools.exceptions import IMGWValidationError
from imgwtools.mcp._calls import call_tool
from imgwtools.mcp._tools import MODES, Mode, catalog_tools
from imgwtools.messages import LANGS, Lang

__all__ = ["create_server", "http_app", "run_stdio"]

_ROOT_ENV = "IMGW_STORE_ROOT"


def _choice(name: str, value: object, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise IMGWValidationError(
            f"Nieprawidłowa wartość {value!r} opcji {name}; dozwolone: "
            f"{', '.join(allowed)}",
            details={"option": name, "value": str(value), "allowed": list(allowed)},
        )


def create_server(*, mode: Mode = "read", lang: Lang = "pl") -> Server:
    """
    Create the MCP server of the command catalog.

    Parameters
    ----------
    mode : {"read", "write", "http"}, optional
        ``read``: every command, writing commands only plan (``check`` fixed
        to ``true``) and writing options are absent; ``write``: every command,
        writing commands plan by default and write with ``check: false``;
        ``http``: the commands with a REST route, answered by that route,
        POST routes only planning.
    lang : {"pl", "en"}, optional
        Language of the tool texts, the instructions, error titles and the
        default of ``lang`` options (``detail`` stays Polish).

    Returns
    -------
    mcp.server.Server
        Low-level SDK server with the tools of the mode in catalog order. In
        ``read`` and ``write`` an absent ``root`` is ``IMGW_STORE_ROOT`` (read
        now) under the command's ``env_root_when``, relative paths are
        relative to the current working directory.

    Raises
    ------
    IMGWValidationError
        If ``mode`` or ``lang`` is not one of the allowed values.
    """
    _choice("mode", mode, MODES)
    _choice("lang", lang, LANGS)
    if mode == "http":
        root, workdir, store = None, None, settings.store_root
    else:
        root, workdir = os.environ.get(_ROOT_ENV) or None, Path.cwd()
        store = None if root is None else Path(root)
    tools = catalog_tools(mode=mode, lang=lang, root=root)
    listing = types.ListToolsResult(tools=[tool.definition for tool in tools.values()])

    async def list_tools(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return listing  # not paged; the same list for every connection

    async def call(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        tool = tools.get(params.name)
        if tool is None:
            raise MCPError(types.INVALID_PARAMS, f"Nieznane narzędzie: {params.name}")
        return await call_tool(
            tool, params.arguments or {}, report=ctx.session.report_progress
        )

    return Server(
        "imgwtools",
        version=__version__,
        title="IMGWTools",
        instructions=_instructions(lang=lang, mode=mode, workdir=workdir, root=store),
        on_list_tools=list_tools,
        on_call_tool=call,
    )


async def _serve(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def run_stdio(*, allow_writes: bool = False, lang: Lang = "pl") -> None:
    """
    Serve MCP over stdin and stdout until the client closes the connection.

    stdout belongs to the protocol: while serving, the SDK points the process
    stdout at stderr, so nothing else reaches the client.

    Parameters
    ----------
    allow_writes : bool, optional
        Mode ``write`` instead of ``read`` (``imgw mcp --allow-writes``,
        ``IMGW_MCP_ALLOW_WRITES=true``).
    lang : {"pl", "en"}, optional
        Language of the server (``imgw mcp --lang``, default ``IMGW_LANG``).
    """
    server = create_server(mode="write" if allow_writes else "read", lang=lang)
    anyio.run(_serve, server)


def http_app(*, lang: Lang = "pl") -> Starlette:
    """
    Streamable HTTP application of the MCP server in mode ``http``.

    The endpoint is ``/mcp``; only the Host names of
    ``IMGW_MCP_ALLOWED_HOSTS`` (``Settings.mcp_allowed_hosts``) are answered,
    each with any port or none (another Host → 421), and requests with an
    ``Origin`` header are refused (403, the SDK's narrowest list).

    Parameters
    ----------
    lang : {"pl", "en"}, optional
        Language of the server (``IMGW_LANG`` of the REST server process).

    Returns
    -------
    starlette.applications.Starlette
        Application whose lifespan runs the session manager of the SDK. A
        host application that mounts it runs this lifespan in its own
        (``app.router.lifespan_context``); a mounted application's lifespan
        never runs by itself.
    """
    server = create_server(mode="http", lang=lang)
    hosts = [
        form for host in settings.mcp_allowed_hosts for form in (host, f"{host}:*")
    ]
    return server.streamable_http_app(
        transport_security=TransportSecuritySettings(allowed_hosts=hosts)
    )
