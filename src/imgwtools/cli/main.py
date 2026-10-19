"""
Entry point of the ``imgw`` command line.

The groups ``datasets``, ``stations``, ``current``, ``pmaxtp``, ``store``,
``series``, ``project`` and ``commands`` are generated from the command catalog
by `imgwtools.cli._dispatch` (spec §13.10); ``imgw version``, ``imgw server``
and ``imgw admin`` stay outside the catalog. Examples::

    imgw datasets download -d hydro/dobowe -y 2023 -m 1
    imgw stations find -k hydro -q raba --limit 20
    imgw store sync --root /dane/imgw -d pl.imgw.hydro_daily -y 2024
    imgw series summary --root /dane/imgw -d pl.imgw.hydro_daily -s 149190310
    imgw commands schema --command "store sync"
    imgw admin create --name "User1"
"""

import typer
from rich.console import Console

from imgwtools._version import __version__
from imgwtools.cli import admin
from imgwtools.cli._dispatch import ImgwCommand, ImgwGroup, register_catalog

app = typer.Typer(
    name="imgw",
    help=(
        "Narzędzie do pobierania danych publicznych IMGW-PIB. Wynik komend "
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


@app.command(cls=ImgwCommand)
def version():
    """Wyswietl wersje programu."""
    console.print(f"[bold]IMGWTools[/bold] v{__version__}")


@app.command(cls=ImgwCommand)
def server(
    host: str = typer.Option("0.0.0.0", help="Host do nasluchu"),
    port: int = typer.Option(8000, help="Port do nasluchu"),
    reload: bool = typer.Option(False, help="Auto-reload przy zmianach"),
):
    """Uruchom serwer API."""
    import uvicorn

    console.print(f"[bold green]Uruchamiam serwer na {host}:{port}[/bold green]")
    uvicorn.run(
        "imgwtools.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
