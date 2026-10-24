"""
Entry point of the ``imgw`` command line.

The groups ``datasets``, ``stations``, ``current``, ``pmaxtp``, ``store``,
``series``, ``project`` and ``commands`` are generated from the command catalog
by `imgwtools.cli._dispatch` (spec §13.10); ``imgw version``, ``imgw server``,
``imgw mcp`` and ``imgw admin`` stay outside the catalog. Examples::

    imgw datasets download -d hydro/dobowe -y 2023 -m 1
    imgw stations find -k hydro -q raba --limit 20
    imgw store sync --root /dane/imgw -d pl.imgw.hydro_daily -y 2024
    imgw series summary --root /dane/imgw -d pl.imgw.hydro_daily -s 149190310
    imgw commands schema --command "store sync"
    imgw mcp --allow-writes
    imgw admin create --name "User1"

``imgw mcp`` serves the catalog to AI agents over MCP on stdin and stdout
(spec 2026-10-19 §6.2): the SDK of the ``mcp`` extra is imported only by that
command, which writes nothing to stdout, the channel of the protocol.
"""

from typing import cast

import typer
from rich.console import Console

from imgwtools._version import __version__
from imgwtools.cli import admin, config_cmd
from imgwtools.cli._dispatch import (
    _HELP,
    _LANG,
    ImgwCommand,
    ImgwGroup,
    _error_line,
    register_catalog,
)
from imgwtools.config import settings
from imgwtools.exceptions import IMGWError
from imgwtools.messages import Lang, message

app = typer.Typer(
    name="imgw",
    help=message("cli.app_help", lang=_LANG),
    add_completion=False,
    cls=ImgwGroup,
)

# Console for rich output
console = Console()

register_catalog(app)
app.add_typer(admin.app, name="admin", help=message("cli.admin_group_help", lang=_LANG))
app.add_typer(config_cmd.app, name="config")


@app.command(cls=ImgwCommand, help=message("cli.version_help", lang=_LANG))
def version() -> None:
    """Print the version of the program."""
    console.print(f"[bold]IMGWTools[/bold] v{__version__}")


@app.command(cls=ImgwCommand, help=message("cli.server_help", lang=_LANG))
def server(
    host: str = typer.Option(
        settings.host,
        metavar=message("cli.metavar_address", lang=_LANG),
        help=message("cli.server_host_help", lang=_LANG),
    ),
    port: int = typer.Option(
        settings.port,
        metavar=_HELP.metavars["int"],
        help=message("cli.server_port_help", lang=_LANG),
    ),
    reload: bool = typer.Option(
        False, help=message("cli.server_reload_help", lang=_LANG)
    ),
) -> None:
    """Start the API server: REST, the web GUI and /mcp (with IMGW_MCP_ENABLED=true)."""
    import uvicorn

    console.print(
        message("cli.server_starting", lang=_LANG, host=host, port=port),
        style="bold green",
        markup=False,
    )
    uvicorn.run(
        "imgwtools.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command(cls=ImgwCommand, help=message("cli.mcp_help", lang=_LANG))
def mcp(
    allow_writes: bool = typer.Option(
        settings.mcp_allow_writes,
        "--allow-writes/--no-allow-writes",
        help=message("cli.mcp_allow_writes_help", lang=_LANG),
    ),
    lang: str = typer.Option(
        "pl",
        "--lang",
        envvar="IMGW_LANG",
        metavar="pl|en",
        help=message("cli.mcp_lang_help", lang=_LANG),
    ),
) -> None:
    """
    Run the MCP server for AI agents on the standard input and output.

    The tools of the server are the catalog commands. Without --allow-writes the
    server does not write: the writing commands return an imgw-plan/1 plan.
    """
    try:
        from imgwtools.mcp.server import run_stdio
    except ImportError:
        raise typer.Exit(
            _error_line("missing_dependency", message("cli.mcp_needs_extra"), {})
        ) from None
    try:
        run_stdio(allow_writes=allow_writes, lang=cast(Lang, lang))
    except IMGWError as exc:  # --lang outside pl and en
        raise typer.Exit(_error_line(exc.code, exc.detail, exc.details)) from None


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
