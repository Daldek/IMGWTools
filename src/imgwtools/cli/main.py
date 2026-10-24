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
    ImgwCommand,
    ImgwGroup,
    _error_line,
    register_catalog,
)
from imgwtools.commands import Lang
from imgwtools.config import settings
from imgwtools.exceptions import IMGWError

_NO_MCP = "Serwer MCP wymaga dodatku: pip install imgwtools[mcp]"

app = typer.Typer(
    name="imgw",
    help=(
        "Narzędzie do pobierania danych publicznych IMGW-PIB i ČHMÚ. Wynik komend "
        "katalogu to koperta JSON imgw-result/1 na standardowym wyjściu; błąd to "
        "JSON w ostatniej linii standardowego wyjścia błędów."
    ),
    add_completion=False,
    cls=ImgwGroup,
)

# Console for rich output
console = Console()

register_catalog(app)
app.add_typer(admin.app, name="admin", help="Administracja (klucze API)")
app.add_typer(config_cmd.app, name="config")


@app.command(cls=ImgwCommand)
def version() -> None:
    """Wyświetl wersję programu."""
    console.print(f"[bold]IMGWTools[/bold] v{__version__}")


@app.command(cls=ImgwCommand)
def server(
    host: str = typer.Option(
        settings.host, metavar="ADRES", help="Adres nasłuchu (IMGW_HOST)"
    ),
    port: int = typer.Option(
        settings.port, metavar="LICZBA", help="Port nasłuchu (IMGW_PORT)"
    ),
    reload: bool = typer.Option(
        False, help="Przeładuj serwer po zmianie kodu (tryb deweloperski)"
    ),
) -> None:
    """Uruchom serwer API: REST, web GUI i /mcp (przy IMGW_MCP_ENABLED=true)."""
    import uvicorn

    console.print(f"[bold green]Uruchamiam serwer na {host}:{port}[/bold green]")
    uvicorn.run(
        "imgwtools.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command(cls=ImgwCommand)
def mcp(
    allow_writes: bool = typer.Option(
        settings.mcp_allow_writes,
        "--allow-writes/--no-allow-writes",
        help="Zezwól na zapis (IMGW_MCP_ALLOW_WRITES): komendy zapisujące "
        "domyślnie zwracają plan (check=true), a zapisują przy check=false",
    ),
    lang: str = typer.Option(
        "pl",
        "--lang",
        envvar="IMGW_LANG",
        metavar="pl|en",
        help="Język opisów narzędzi, instrukcji i tytułów błędów",
    ),
) -> None:
    """
    Uruchom serwer MCP dla agentów AI na standardowym wejściu i wyjściu.

    Narzędzia serwera to komendy katalogu. Bez --allow-writes serwer nie
    zapisuje: komendy zapisujące zwracają plan imgw-plan/1.
    """
    try:
        from imgwtools.mcp.server import run_stdio
    except ImportError:
        raise typer.Exit(_error_line("missing_dependency", _NO_MCP, {})) from None
    try:
        run_stdio(allow_writes=allow_writes, lang=cast(Lang, lang))
    except IMGWError as exc:  # --lang outside pl and en
        raise typer.Exit(_error_line(exc.code, exc.detail, exc.details)) from None


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
