"""
IMGWTools CLI - main entry point.

Usage:
    imgw fetch hydro --interval dobowe --year 2023 --output ./data
    imgw fetch meteo --interval miesieczne --year 2023 --subtype klimat
    imgw list stations --type hydro
    imgw admin keys create --name "User1"
"""

import typer
from rich.console import Console

from imgwtools.cli import fetch, list_cmd, admin, db

# Create main app
app = typer.Typer(
    name="imgw",
    help="Narzedzie do pobierania danych publicznych z IMGW-PIB",
    add_completion=False,
)

# Console for rich output
console = Console()

# Add subcommands
app.add_typer(fetch.app, name="fetch", help="Pobieranie danych")
app.add_typer(list_cmd.app, name="list", help="Listowanie stacji i zbiorow danych")
app.add_typer(admin.app, name="admin", help="Administracja (klucze API)")
app.add_typer(db.app, name="db", help="Zarzadzanie baza danych cache")


@app.command()
def version():
    """Wyswietl wersje programu."""
    console.print("[bold]IMGWTools[/bold] v1.0.0")


@app.command()
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
