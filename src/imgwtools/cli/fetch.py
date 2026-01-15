"""
Fetch command for downloading IMGW data.
"""

import os
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from imgwtools.core.url_builder import (
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    PMaXTPMethod,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    build_api_url,
)

app = typer.Typer(help="Pobieranie danych z IMGW")
console = Console()


def download_file(url: str, output_path: Path, filename: str) -> bool:
    """Download a file from URL to output path."""
    output_file = output_path / filename

    if output_file.exists():
        console.print(f"[yellow]Plik {filename} juz istnieje, pomijam[/yellow]")
        return False

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Pobieranie {filename}...", total=100)

        try:
            with httpx.stream("GET", url, timeout=60.0, follow_redirects=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))

                with open(output_file, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            progress.update(task, completed=(downloaded / total) * 100)

            progress.update(task, completed=100)
            console.print(f"[green]Pobrano: {output_file}[/green]")
            return True

        except httpx.HTTPStatusError as e:
            console.print(f"[red]Blad HTTP {e.response.status_code}: {url}[/red]")
            return False
        except httpx.HTTPError as e:
            console.print(f"[red]Blad polaczenia: {e}[/red]")
            return False


@app.command("hydro")
def fetch_hydro(
    interval: str = typer.Option(
        "polroczne_i_roczne",
        "--interval", "-i",
        help="Interwal: dobowe, miesieczne, polroczne_i_roczne",
    ),
    year: str = typer.Option(
        ...,
        "--year", "-y",
        help="Rok lub zakres lat (np. 2020 lub 2020-2023)",
    ),
    month: Optional[int] = typer.Option(
        None,
        "--month", "-m",
        help="Miesiac (1-12) dla danych dobowych, 13 dla zjawisk",
    ),
    param: Optional[str] = typer.Option(
        None,
        "--param", "-p",
        help="Parametr dla polrocznych: T, Q, H",
    ),
    output: Path = typer.Option(
        Path("./data/downloaded"),
        "--output", "-o",
        help="Katalog wyjsciowy",
    ),
):
    """
    Pobierz dane hydrologiczne z IMGW.

    Przykłady:
        imgw fetch hydro --interval dobowe --year 2023 --month 1
        imgw fetch hydro --interval polroczne_i_roczne --year 2020-2023 --param Q
    """
    # Parse year range
    if "-" in year:
        start_year, end_year = map(int, year.split("-"))
    else:
        start_year = end_year = int(year)

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Convert parameters
    try:
        hydro_interval = HydroInterval(interval)
    except ValueError:
        console.print(f"[red]Nieprawidlowy interwal: {interval}[/red]")
        raise typer.Exit(1)

    hydro_param = HydroParam(param) if param else None

    console.print(f"[bold]Pobieranie danych hydrologicznych[/bold]")
    console.print(f"Interwal: {interval}")
    console.print(f"Lata: {start_year}-{end_year}")
    console.print(f"Katalog: {output}")
    console.print()

    downloaded = 0
    failed = 0

    for y in range(start_year, end_year + 1):
        if hydro_interval == HydroInterval.DAILY:
            if y >= 2023:
                # From 2023: single file per year
                try:
                    result = build_hydro_url(hydro_interval, y)
                    if download_file(result.url, output, result.filename):
                        downloaded += 1
                except ValueError as e:
                    console.print(f"[yellow]Pomijam {y}: {e}[/yellow]")
                    failed += 1
            else:
                # Before 2023: monthly files
                months = [month] if month else range(1, 14)  # 13 = phenomena
                for m in months:
                    try:
                        result = build_hydro_url(hydro_interval, y, m, hydro_param)
                        if download_file(result.url, output, result.filename):
                            downloaded += 1
                    except ValueError as e:
                        console.print(f"[yellow]Pomijam {y}/{m}: {e}[/yellow]")
                        failed += 1
        else:
            if hydro_interval == HydroInterval.SEMI_ANNUAL and not hydro_param:
                # Download all parameters
                for p in [HydroParam.FLOW, HydroParam.DEPTH, HydroParam.TEMPERATURE]:
                    try:
                        result = build_hydro_url(hydro_interval, y, param=p)
                        if download_file(result.url, output, result.filename):
                            downloaded += 1
                    except ValueError as e:
                        failed += 1
            else:
                try:
                    result = build_hydro_url(hydro_interval, y, param=hydro_param)
                    if download_file(result.url, output, result.filename):
                        downloaded += 1
                except ValueError as e:
                    console.print(f"[yellow]Pomijam {y}: {e}[/yellow]")
                    failed += 1

    console.print()
    console.print(f"[bold green]Pobrano: {downloaded} plikow[/bold green]")
    if failed:
        console.print(f"[yellow]Niepowodzenia: {failed}[/yellow]")


@app.command("meteo")
def fetch_meteo(
    interval: str = typer.Option(
        "miesieczne",
        "--interval", "-i",
        help="Interwal: dobowe, miesieczne, terminowe",
    ),
    subtype: str = typer.Option(
        "synop",
        "--subtype", "-s",
        help="Podtyp: klimat, opad, synop",
    ),
    year: str = typer.Option(
        ...,
        "--year", "-y",
        help="Rok lub zakres lat (np. 2020 lub 2020-2023)",
    ),
    month: Optional[int] = typer.Option(
        None,
        "--month", "-m",
        help="Miesiac (1-12)",
    ),
    output: Path = typer.Option(
        Path("./data/downloaded"),
        "--output", "-o",
        help="Katalog wyjsciowy",
    ),
):
    """
    Pobierz dane meteorologiczne z IMGW.

    Przykłady:
        imgw fetch meteo --interval dobowe --subtype klimat --year 2023 --month 1
        imgw fetch meteo --interval miesieczne --subtype synop --year 2020-2023
    """
    # Parse year range
    if "-" in year:
        start_year, end_year = map(int, year.split("-"))
    else:
        start_year = end_year = int(year)

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Convert parameters
    try:
        meteo_interval = MeteoInterval(interval)
        meteo_subtype = MeteoSubtype(subtype)
    except ValueError as e:
        console.print(f"[red]Nieprawidlowy parametr: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Pobieranie danych meteorologicznych[/bold]")
    console.print(f"Interwal: {interval}")
    console.print(f"Podtyp: {subtype}")
    console.print(f"Lata: {start_year}-{end_year}")
    console.print(f"Katalog: {output}")
    console.print()

    downloaded = 0
    failed = 0

    for y in range(start_year, end_year + 1):
        if y <= 2000:
            # 1951-2000: yearly files (no monthly split)
            try:
                result = build_meteo_url(meteo_interval, meteo_subtype, y)
                if download_file(result.url, output, result.filename):
                    downloaded += 1
            except ValueError as e:
                console.print(f"[yellow]Pomijam {y}: {e}[/yellow]")
                failed += 1
        elif meteo_interval in [MeteoInterval.DAILY, MeteoInterval.HOURLY]:
            # 2001+: monthly files
            months = [month] if month else range(1, 13)
            for m in months:
                try:
                    result = build_meteo_url(meteo_interval, meteo_subtype, y, m)
                    if download_file(result.url, output, result.filename):
                        downloaded += 1
                except ValueError as e:
                    failed += 1
        else:
            try:
                result = build_meteo_url(meteo_interval, meteo_subtype, y)
                if download_file(result.url, output, result.filename):
                    downloaded += 1
            except ValueError as e:
                console.print(f"[yellow]Pomijam {y}: {e}[/yellow]")
                failed += 1

    console.print()
    console.print(f"[bold green]Pobrano: {downloaded} plikow[/bold green]")
    if failed:
        console.print(f"[yellow]Niepowodzenia: {failed}[/yellow]")


@app.command("current")
def fetch_current(
    data_type: str = typer.Argument(
        ...,
        help="Typ danych: hydro, meteo, synop",
    ),
    station_id: Optional[str] = typer.Option(
        None,
        "--station", "-s",
        help="ID stacji (opcjonalne)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Plik wyjsciowy (JSON)",
    ),
):
    """
    Pobierz aktualne dane z API IMGW.

    Przykłady:
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
        "--method", "-m",
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
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Plik wyjsciowy (JSON)",
    ),
):
    """
    Pobierz dane PMAXTP (opady maksymalne prawdopodobne).

    Przykłady:
        imgw fetch pmaxtp --method POT --lat 52.2297 --lon 21.0122 --output pmaxtp.json
    """
    import json

    try:
        pmaxtp_method = PMaXTPMethod(method)
    except ValueError:
        console.print(f"[red]Nieprawidlowa metoda: {method}. Uzyj POT lub AMP.[/red]")
        raise typer.Exit(1)

    url = build_pmaxtp_url(pmaxtp_method, lat, lon)

    console.print(f"[bold]Pobieranie danych PMAXTP[/bold]")
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
        "--type", "-t",
        help="Typ ostrzezen: hydro lub meteo",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Plik wyjsciowy (JSON)",
    ),
):
    """
    Pobierz ostrzezenia z API IMGW.

    Przykłady:
        imgw fetch warnings --type hydro
        imgw fetch warnings --type meteo --output warnings.json
    """
    import json

    if warning_type not in ["hydro", "meteo"]:
        console.print(f"[red]Nieprawidlowy typ: {warning_type}. Uzyj hydro lub meteo.[/red]")
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
