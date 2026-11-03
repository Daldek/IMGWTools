"""
Entry point of the ``obserwator`` command line.

The groups ``datasets``, ``stations``, ``current``, ``pmaxtp``, ``store``,
``series`` and ``commands`` are generated from the command catalog
by `obserwator.cli._dispatch` (spec §13.10); ``obserwator version``, ``obserwator server``,
``obserwator mcp`` and ``obserwator admin`` stay outside the catalog. Examples::

    obserwator datasets download -d hydro/dobowe -y 2023 -m 1
    obserwator stations find -k hydro -q raba --limit 20
    obserwator store sync --root /dane/obserwator -d pl.imgw.hydro_daily -y 2024
    obserwator series summary --root /dane/obserwator -d pl.imgw.hydro_daily -s 149190310
    obserwator commands schema --command "store sync"
    obserwator mcp --allow-writes --allow-dir /dane/obserwator
    obserwator admin create --name "User1"

``obserwator mcp`` serves the catalog to AI agents over MCP on stdin and stdout
(spec 2026-10-19 §6.2): the SDK of the ``mcp`` extra is imported only by that
command, which writes nothing to stdout, the channel of the protocol.
"""

from pathlib import Path

import typer
from rich.console import Console

from obserwator._version import __version__
from obserwator.cli import admin, config_cmd
from obserwator.cli._dispatch import (
    _HELP,
    _LANG,
    ObserwatorCommand,
    ObserwatorGroup,
    _error_line,
    register_catalog,
)
from obserwator.config import settings
from obserwator.messages import message

app = typer.Typer(
    name="obserwator",
    help=message("cli.app_help", lang=_LANG),
    add_completion=False,
    cls=ObserwatorGroup,
)

# Console for rich output
console = Console()

register_catalog(app)
app.add_typer(admin.app, name="admin", help=message("cli.admin_group_help", lang=_LANG))
app.add_typer(config_cmd.app, name="config")


@app.command(cls=ObserwatorCommand, help=message("cli.version_help", lang=_LANG))
def version() -> None:
    """Print the version of the program."""
    console.print(f"[bold]Obserwator[/bold] v{__version__}")


@app.command(cls=ObserwatorCommand, help=message("cli.server_help", lang=_LANG))
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
    """Start the API server: REST, the web GUI and /mcp (with OBSERWATOR_MCP_ENABLED=true)."""
    import uvicorn

    console.print(
        message("cli.server_starting", lang=_LANG, host=host, port=port),
        style="bold green",
        markup=False,
    )
    uvicorn.run(
        "obserwator.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command(cls=ObserwatorCommand, help=message("cli.mcp_help", lang=_LANG))
def mcp(
    allow_writes: bool = typer.Option(
        settings.mcp_allow_writes,
        "--allow-writes/--no-allow-writes",
        help=message("cli.mcp_allow_writes_help", lang=_LANG),
    ),
    allow_dir: list[Path] = typer.Option(
        [],
        "--allow-dir",
        help=message("cli.mcp_allow_dir_help", lang=_LANG),
    ),
) -> None:
    """
    Run the MCP server for AI agents on the standard input and output.

    The tools of the server are the catalog commands. Without --allow-writes the
    server does not write: the writing commands return an obserwator-plan/1 plan; with
    it they write only inside the --allow-dir directories (repeatable).
    """
    try:
        from obserwator.mcp.server import run_stdio
    except ImportError:
        raise typer.Exit(
            _error_line("missing_dependency", message("cli.mcp_needs_extra"), {})
        ) from None
    run_stdio(allow_writes=allow_writes, allow_dirs=allow_dir)


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
