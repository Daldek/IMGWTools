"""Fetch command for downloading IMGW data."""

from pathlib import Path

import httpx
import typer
from rich.console import Console

from imgwtools.cli._dispatch import register_command
from imgwtools.core.url_builder import (
    PMaXTPMethod,
    build_api_url,
    build_pmaxtp_url,
)
from imgwtools.store.types import Progress

app = typer.Typer(help="Pobieranie danych z IMGW")
console = Console()


def _download_summary(events: list[Progress]) -> None:
    """Print how many archives were downloaded and how many failed."""
    downloaded = sum(event.status == "downloaded" for event in events)
    failed = sum(event.status == "failed" for event in events)
    console.print(f"[bold green]Pobrano: {downloaded} plików[/bold green]")
    if failed:
        console.print(f"[yellow]Niepowodzenia: {failed}[/yellow]")


# ``fetch hydro|meteo`` are catalog commands: same options, validation, ``.part``
# saving and public ``download_*`` calls as ``run_command`` (spec §10).
register_command(
    app,
    "fetch hydro",
    short={
        "interval": "-i",
        "year": "-y",
        "month": "-m",
        "param": "-p",
        "output": "-o",
    },
    summary=_download_summary,
)
register_command(
    app,
    "fetch meteo",
    short={
        "interval": "-i",
        "subtype": "-s",
        "year": "-y",
        "month": "-m",
        "output": "-o",
    },
    summary=_download_summary,
)


@app.command("current")
def fetch_current(
    data_type: str = typer.Argument(
        ...,
        help="Typ danych: hydro, meteo, synop",
    ),
    station_id: str | None = typer.Option(
        None,
        "--station",
        "-s",
        help="ID stacji (opcjonalne)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Plik wyjsciowy (JSON)",
    ),
):
    """
    Pobierz aktualne dane z API IMGW.

    Przyklady:
        imgw fetch current hydro
        imgw fetch current hydro --station 150160180 --output data.json
    """
    import json

    endpoints = {
        "hydro": "hydro",
        "meteo": "meteo",
        "synop": "synop",
    }

    if data_type not in endpoints:
        console.print(f"[red]Nieprawidlowy typ danych: {data_type}[/red]")
        raise typer.Exit(1)

    url = build_api_url(endpoints[data_type], station_id=station_id)

    console.print(f"[bold]Pobieranie aktualnych danych ({data_type})[/bold]")
    console.print(f"URL: {url}")
    console.print()

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

            if output:
                with open(output, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                console.print(f"[green]Zapisano do: {output}[/green]")
            else:
                console.print_json(data=data)

    except httpx.HTTPError as e:
        console.print(f"[red]Blad pobierania: {e}[/red]")
        raise typer.Exit(1)


@app.command("pmaxtp")
def fetch_pmaxtp(
    method: str = typer.Option(
        "POT",
        "--method",
        "-m",
        help="Metoda: POT lub AMP",
    ),
    lat: float = typer.Option(
        ...,
        "--lat",
        help="Szerokosc geograficzna",
    ),
    lon: float = typer.Option(
        ...,
        "--lon",
        help="Dlugosc geograficzna",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Plik wyjsciowy (JSON)",
    ),
):
    """
    Pobierz dane PMAXTP (opady maksymalne prawdopodobne).

    Przyklady:
        imgw fetch pmaxtp --method POT --lat 52.2297 --lon 21.0122 --output pmaxtp.json
    """
    import json

    try:
        pmaxtp_method = PMaXTPMethod(method)
    except ValueError:
        console.print(f"[red]Nieprawidlowa metoda: {method}. Uzyj POT lub AMP.[/red]")
        raise typer.Exit(1)

    url = build_pmaxtp_url(pmaxtp_method, lat, lon)

    console.print("[bold]Pobieranie danych PMAXTP[/bold]")
    console.print(f"Metoda: {method}")
    console.print(f"Lokalizacja: {lat}, {lon}")
    console.print(f"URL: {url}")
    console.print()

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

            if output:
                with open(output, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                console.print(f"[green]Zapisano do: {output}[/green]")
            else:
                console.print_json(data=data)

    except httpx.HTTPError as e:
        console.print(f"[red]Blad pobierania: {e}[/red]")
        raise typer.Exit(1)


@app.command("warnings")
def fetch_warnings(
    warning_type: str = typer.Option(
        "hydro",
        "--type",
        "-t",
        help="Typ ostrzezen: hydro lub meteo",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Plik wyjsciowy (JSON)",
    ),
):
    """
    Pobierz ostrzezenia z API IMGW.

    Przyklady:
        imgw fetch warnings --type hydro
        imgw fetch warnings --type meteo --output warnings.json
    """
    import json

    if warning_type not in ["hydro", "meteo"]:
        console.print(
            f"[red]Nieprawidlowy typ: {warning_type}. Uzyj hydro lub meteo.[/red]"
        )
        raise typer.Exit(1)

    url = build_api_url(f"warnings/{warning_type}")

    console.print(f"[bold]Pobieranie ostrzezen ({warning_type})[/bold]")
    console.print(f"URL: {url}")
    console.print()

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

            if output:
                with open(output, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                console.print(f"[green]Zapisano do: {output}[/green]")
            else:
                console.print_json(data=data)

    except httpx.HTTPError as e:
        console.print(f"[red]Blad pobierania: {e}[/red]")
        raise typer.Exit(1)
