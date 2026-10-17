"""Fetch command for downloading IMGW data."""

import os
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx
import typer
from rich.console import Console

from imgwtools.core.url_builder import (
    IMGW_PUBLIC_DATA_URL,
    PMaXTPMethod,
    build_api_url,
    build_pmaxtp_url,
)
from imgwtools.datasets import ArchiveFile, archive_files
from imgwtools.exceptions import IMGWError, IMGWValidationError
from imgwtools.fetch import DownloadResult, download_hydro_data, download_meteo_data

app = typer.Typer(help="Pobieranie danych z IMGW")
console = Console()


def _years(text: str) -> range:
    try:
        bounds = text.split("-")
        if len(bounds) not in (1, 2):
            raise ValueError
        start, end = int(bounds[0]), int(bounds[-1])
        if end < start:
            raise ValueError
        return range(start, end + 1)
    except ValueError as exc:
        raise IMGWValidationError(f"Nieprawidłowy zakres lat: {text}") from exc


def _server_path(url: str) -> str:
    """Resolve legacy archive paths from the successful download URL."""
    parsed = urlsplit(url)
    base = urlsplit(IMGW_PUBLIC_DATA_URL)
    if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        raise IMGWValidationError(f"Nieznany serwer IMGW: {url}")
    prefix = base.path.rstrip("/") + "/"
    path = unquote(parsed.path)
    if not path.startswith(prefix):
        raise IMGWValidationError(f"Nieznana ścieżka IMGW: {url}")
    return path[len(prefix) :]


def _save_archive(output: Path, server_path: str, result: DownloadResult) -> Path:
    """Write a validated download to a unique part file, then publish it."""
    relative = PurePosixPath(server_path)
    if (
        not server_path
        or relative.is_absolute()
        or any(part in (".", "..", "") for part in server_path.split("/"))
        or "\\" in server_path
        or relative.suffix != ".zip"
    ):
        raise IMGWValidationError(f"Niebezpieczna ścieżka archiwum: {server_path}")
    destination = output.joinpath(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    try:
        with part.open("xb") as stream:
            stream.write(result.data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)
    console.print(f"[green]Pobrano: {destination}[/green]")
    return destination


def _download_hydro(archive: ArchiveFile, interval: str, output: Path) -> None:
    year, param = archive.year, archive.param
    if (
        year is None
        or interval not in ("dobowe", "miesieczne", "polroczne_i_roczne")
        or (param is not None and param not in ("T", "Q", "H"))
    ):
        raise IMGWValidationError(f"Nieobsługiwane archiwum: {archive.server_path}")
    result = download_hydro_data(interval, year, archive.month, param)
    _save_archive(output, archive.server_path, result)


@app.command("hydro")
def fetch_hydro(
    interval: str = typer.Option(
        "polroczne_i_roczne",
        "--interval",
        "-i",
        help="Interwal: dobowe, miesieczne, polroczne_i_roczne",
    ),
    year: str = typer.Option(
        ...,
        "--year",
        "-y",
        help="Rok lub zakres lat (np. 2020 lub 2020-2023)",
    ),
    month: int | None = typer.Option(
        None,
        "--month",
        "-m",
        help="Miesiac (1-12) dla danych dobowych, 13 dla zjawisk",
    ),
    param: str | None = typer.Option(
        None,
        "--param",
        "-p",
        help="Parametr dla polrocznych: T, Q, H",
    ),
    output: Path = typer.Option(
        Path("./data/downloaded"),
        "--output",
        "-o",
        help="Katalog wyjsciowy",
    ),
):
    """
    Pobierz dane hydrologiczne z IMGW.

    Przyklady:
        imgw fetch hydro --interval dobowe --year 2023 --month 1
        imgw fetch hydro --interval polroczne_i_roczne --year 2020-2023 --param Q
    """
    dataset = {
        "dobowe": "pl.imgw.hydro_daily",
        "miesieczne": "pl.imgw.hydro_monthly",
        "polroczne_i_roczne": "pl.imgw.hydro_semiannual",
    }.get(interval)
    if dataset is None or (
        param is not None
        and (interval != "polroczne_i_roczne" or param not in ("H", "Q", "T"))
    ):
        console.print("[red]Nieprawidłowy interwał lub parametr hydrologiczny[/red]")
        raise typer.Exit(1)
    try:
        files = archive_files(
            dataset, years=_years(year), months=(month,) if month is not None else None
        )
    except IMGWValidationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if param is not None:
        files = tuple(file for file in files if file.param == param)
    downloaded = 0
    failed = 0
    for archive in files:
        try:
            _download_hydro(archive, interval, output)
            downloaded += 1
        except (IMGWError, ValueError, OSError) as exc:
            console.print(f"[red]Nie pobrano {archive.server_path}: {exc}[/red]")
            failed += 1
    console.print(f"[bold green]Pobrano: {downloaded} plików[/bold green]")
    if failed:
        console.print(f"[yellow]Niepowodzenia: {failed}[/yellow]")


@app.command("meteo")
def fetch_meteo(
    interval: str = typer.Option(
        "miesieczne",
        "--interval",
        "-i",
        help="Interwal: dobowe, miesieczne, terminowe",
    ),
    subtype: str = typer.Option(
        "synop",
        "--subtype",
        "-s",
        help="Podtyp: klimat, opad, synop",
    ),
    year: str = typer.Option(
        ...,
        "--year",
        "-y",
        help="Rok lub zakres lat (np. 2020 lub 2020-2023)",
    ),
    month: int | None = typer.Option(
        None,
        "--month",
        "-m",
        help="Miesiac (1-12)",
    ),
    output: Path = typer.Option(
        Path("./data/downloaded"),
        "--output",
        "-o",
        help="Katalog wyjsciowy",
    ),
):
    """
    Pobierz dane meteorologiczne z IMGW.

    Przyklady:
        imgw fetch meteo --interval dobowe --subtype klimat --year 2023 --month 1
        imgw fetch meteo --interval miesieczne --subtype synop --year 2020-2023
    """
    if interval not in ("dobowe", "miesieczne", "terminowe") or subtype not in (
        "klimat",
        "opad",
        "synop",
    ):
        console.print("[red]Nieprawidłowy interwał lub podtyp meteorologiczny[/red]")
        raise typer.Exit(1)
    if (interval == "terminowe" and subtype == "opad") or (
        interval in ("dobowe", "terminowe") and subtype == "synop"
    ):
        console.print(
            "[red]Ten rodzaj archiwum nie jest publikowany jako plik zbiorczy IMGW[/red]"
        )
        raise typer.Exit(1)
    try:
        years = _years(year)
        if interval == "dobowe":
            key = (
                f"pl.imgw.meteo_{'climate' if subtype == 'klimat' else 'precip'}_daily"
            )
            files = archive_files(
                key, years=years, months=(month,) if month is not None else None
            )
            jobs = (
                (archive.year, archive.month, archive.server_path) for archive in files
            )
        else:
            if month is not None and not 1 <= month <= 12:
                raise IMGWValidationError(f"Nieprawidłowy miesiąc: {month}")
            jobs = (
                (y, m, None)
                for y in years
                for m in (
                    range(1, 13)
                    if interval == "terminowe" and y >= 2001 and month is None
                    else (month,)
                    if interval == "terminowe" and y >= 2001
                    else (None,)
                )
            )
    except IMGWValidationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    downloaded = 0
    failed = 0
    for y, m, server_path in jobs:
        try:
            if y is None:
                raise IMGWValidationError(f"Brak roku archiwum: {server_path}")
            result = download_meteo_data(interval, subtype, y, m)
            _save_archive(output, server_path or _server_path(result.url), result)
            downloaded += 1
        except (IMGWError, ValueError, OSError) as exc:
            console.print(f"[red]Nie pobrano danych {y}/{m}: {exc}[/red]")
            failed += 1
    console.print(f"[bold green]Pobrano: {downloaded} plików[/bold green]")
    if failed:
        console.print(f"[yellow]Niepowodzenia: {failed}[/yellow]")


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
