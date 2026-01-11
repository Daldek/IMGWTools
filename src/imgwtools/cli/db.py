"""
Database management CLI commands.

Commands for initializing, managing, and querying the SQLite cache
for hydrological data.
"""

import asyncio

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from imgwtools.config import settings

app = typer.Typer(help="Zarzadzanie baza danych cache")
console = Console()


def check_db_enabled() -> None:
    """Check if database is enabled and raise error if not."""
    if not settings.db_enabled:
        console.print(
            "[bold red]Blad:[/bold red] Baza danych nie jest wlaczona.\n"
            "Ustaw IMGW_DB_ENABLED=true w pliku .env lub zmiennych srodowiskowych."
        )
        raise typer.Exit(1)


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Wymus ponowne utworzenie tabel"),
):
    """
    Inicjalizacja bazy danych.

    Tworzy wszystkie tabele i indeksy. Uzyj --force aby usunac istniejace dane.
    """
    check_db_enabled()

    from imgwtools.db import db_exists, init_db

    if db_exists() and not force:
        console.print(
            f"[yellow]Baza danych juz istnieje:[/yellow] {settings.db_path}\n"
            "Uzyj --force aby wymusic ponowne utworzenie."
        )
        return

    with console.status("[bold green]Inicjalizacja bazy danych..."):
        created = init_db(force=force)

    if created:
        console.print(f"[bold green]Utworzono baze danych:[/bold green] {settings.db_path}")
    else:
        console.print("[green]Baza danych jest aktualna.[/green]")


@app.command()
def status():
    """
    Wyswietl status bazy danych.

    Pokazuje rozmiar, liczbe rekordow i zakres zcache'owanych lat.
    """
    check_db_enabled()

    from imgwtools.db import (
        db_exists,
        get_cached_years,
        get_schema_version,
        get_table_counts,
    )

    if not db_exists():
        console.print(
            "[yellow]Baza danych nie istnieje.[/yellow]\n"
            f"Uruchom 'imgw db init' aby utworzyc: {settings.db_path}"
        )
        return

    # Get database info
    version = get_schema_version()
    counts = get_table_counts()
    cached_years = get_cached_years()

    # Get file size
    db_size = settings.db_path.stat().st_size
    if db_size < 1024:
        size_str = f"{db_size} B"
    elif db_size < 1024 * 1024:
        size_str = f"{db_size / 1024:.1f} KB"
    else:
        size_str = f"{db_size / (1024 * 1024):.1f} MB"

    # Display status
    console.print(f"\n[bold]Baza danych:[/bold] {settings.db_path}")
    console.print(f"[bold]Rozmiar:[/bold] {size_str}")
    console.print(f"[bold]Wersja schematu:[/bold] {version}")

    # Record counts table
    table = Table(title="Liczba rekordow")
    table.add_column("Tabela", style="cyan")
    table.add_column("Rekordy", justify="right", style="green")

    for table_name, count in counts.items():
        table.add_row(table_name, f"{count:,}")

    console.print(table)

    # Cached years
    if any(years for years in cached_years.values()):
        console.print("\n[bold]Zcache'owane lata:[/bold]")
        for interval, years in cached_years.items():
            if years:
                years_str = _format_year_ranges(years)
                console.print(f"  {interval}: {years_str}")
    else:
        console.print("\n[yellow]Brak zcache'owanych danych.[/yellow]")
        console.print("Uzyj 'imgw db cache --years 2020-2023' aby pobrac dane.")


def _format_year_ranges(years: list[int]) -> str:
    """Format list of years into ranges (e.g., '2015-2018, 2020, 2022-2023')."""
    if not years:
        return ""

    years = sorted(years)
    ranges = []
    start = years[0]
    end = years[0]

    for year in years[1:]:
        if year == end + 1:
            end = year
        else:
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            start = end = year

    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{end}")

    return ", ".join(ranges)


@app.command()
def cache(
    years: str = typer.Option(..., "--years", "-y", help="Zakres lat (np. 2020-2023 lub 2020)"),
    interval: str = typer.Option(
        "dobowe",
        "--interval", "-i",
        help="Interwal danych: dobowe, miesieczne, polroczne"
    ),
    param: str | None = typer.Option(
        None,
        "--param", "-p",
        help="Parametr dla danych polrocznych: H, Q, T"
    ),
):
    """
    Pobierz i zcache'uj dane dla zakresu lat.

    Przyklad: imgw db cache --years 2020-2023 --interval dobowe
    """
    check_db_enabled()

    from imgwtools.db import db_exists, get_cache_manager, init_db

    # Parse year range
    if "-" in years:
        parts = years.split("-")
        start_year = int(parts[0])
        end_year = int(parts[1])
    else:
        start_year = end_year = int(years)

    if start_year > end_year:
        console.print("[red]Blad: Rok poczatkowy musi byc <= rok koncowy[/red]")
        raise typer.Exit(1)

    # Validate interval
    valid_intervals = ["dobowe", "miesieczne", "polroczne"]
    if interval not in valid_intervals:
        console.print(f"[red]Blad: Nieprawidlowy interwal. Dozwolone: {', '.join(valid_intervals)}[/red]")
        raise typer.Exit(1)

    # Validate param for semi-annual
    if interval == "polroczne" and not param:
        console.print("[red]Blad: Parametr --param (H, Q lub T) jest wymagany dla danych polrocznych[/red]")
        raise typer.Exit(1)

    if param and param.upper() not in ["H", "Q", "T"]:
        console.print("[red]Blad: Parametr musi byc H, Q lub T[/red]")
        raise typer.Exit(1)

    # Initialize DB if needed
    if not db_exists():
        with console.status("[bold green]Inicjalizacja bazy danych..."):
            init_db()

    # Run async cache operation
    async def run_cache():
        manager = get_cache_manager()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Cache'owanie danych {interval} {start_year}-{end_year}...",
                total=None,
            )

            def progress_callback(msg: str, current: int, total: int):
                progress.update(task, description=f"{msg}")

            results = await manager.cache_year_range(
                interval=interval,
                start_year=start_year,
                end_year=end_year,
                param=param.upper() if param else None,
                progress_callback=progress_callback,
            )

        return results

    results = asyncio.run(run_cache())

    # Summary
    total_records = sum(results.values())
    console.print(f"\n[bold green]Zcache'owano {total_records:,} rekordow[/bold green]")

    if total_records > 0:
        table = Table(title="Podsumowanie")
        table.add_column("Rok", style="cyan")
        table.add_column("Rekordy", justify="right", style="green")

        for year, count in sorted(results.items()):
            if count > 0:
                table.add_row(str(year), f"{count:,}")

        console.print(table)


@app.command()
def clear(
    interval: str | None = typer.Option(
        None,
        "--interval", "-i",
        help="Wyczysc tylko dane dla danego interwalu"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Nie pytaj o potwierdzenie"),
):
    """
    Wyczysc zcache'owane dane.

    Uzyj --interval aby wyczysc tylko dane dla konkretnego interwalu.
    """
    check_db_enabled()

    from imgwtools.db import db_exists, get_repository

    if not db_exists():
        console.print("[yellow]Baza danych nie istnieje.[/yellow]")
        return

    if interval:
        valid_intervals = ["dobowe", "miesieczne", "polroczne"]
        if interval not in valid_intervals:
            console.print(f"[red]Blad: Nieprawidlowy interwal. Dozwolone: {', '.join(valid_intervals)}[/red]")
            raise typer.Exit(1)
        msg = f"dane {interval}"
    else:
        msg = "wszystkie dane"

    if not force:
        confirm = typer.confirm(f"Czy na pewno chcesz usunac {msg}?")
        if not confirm:
            console.print("[yellow]Anulowano.[/yellow]")
            return

    repo = get_repository()
    deleted = repo.clear_cache(interval)

    console.print(f"[green]Usunieto {deleted:,} rekordow.[/green]")


@app.command()
def vacuum():
    """
    Optymalizuj baze danych.

    Uruchamia VACUUM aby odzyskac miejsce po usunietych danych.
    """
    check_db_enabled()

    from imgwtools.db import db_exists, get_db_connection

    if not db_exists():
        console.print("[yellow]Baza danych nie istnieje.[/yellow]")
        return

    # Get size before
    size_before = settings.db_path.stat().st_size

    with console.status("[bold green]Optymalizacja bazy danych..."):
        with get_db_connection() as conn:
            conn.execute("VACUUM")

    # Get size after
    size_after = settings.db_path.stat().st_size
    saved = size_before - size_after

    if saved > 0:
        if saved < 1024:
            saved_str = f"{saved} B"
        elif saved < 1024 * 1024:
            saved_str = f"{saved / 1024:.1f} KB"
        else:
            saved_str = f"{saved / (1024 * 1024):.1f} MB"
        console.print(f"[green]Odzyskano {saved_str} miejsca.[/green]")
    else:
        console.print("[green]Baza danych jest juz zoptymalizowana.[/green]")


@app.command()
def stations(
    search: str | None = typer.Option(None, "--search", "-s", help="Szukaj po nazwie"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maksymalna liczba wynikow"),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Odswiez liste z IMGW"),
):
    """
    Wyswietl liste stacji z cache.

    Uzyj --refresh aby pobrac aktualna liste z IMGW.
    """
    check_db_enabled()

    from imgwtools.db import db_exists, get_cache_manager, get_repository, init_db

    if not db_exists():
        init_db()

    if refresh:
        async def run_refresh():
            manager = get_cache_manager()
            with console.status("[bold green]Pobieranie listy stacji..."):
                return await manager.refresh_stations()

        count = asyncio.run(run_refresh())
        console.print(f"[green]Zaktualizowano {count} stacji.[/green]\n")

    repo = get_repository()
    stations_list = repo.get_stations(search=search, limit=limit)

    if not stations_list:
        if search:
            console.print(f"[yellow]Nie znaleziono stacji pasujacych do '{search}'[/yellow]")
        else:
            console.print("[yellow]Brak stacji w cache. Uzyj --refresh aby pobrac.[/yellow]")
        return

    table = Table(title=f"Stacje hydrologiczne ({len(stations_list)})")
    table.add_column("Kod", style="cyan")
    table.add_column("Nazwa", style="green")
    table.add_column("Rzeka", style="blue")

    for station in stations_list:
        table.add_row(
            station.station_code,
            station.station_name,
            station.river_name or "-",
        )

    console.print(table)


@app.command()
def query(
    station: str = typer.Option(..., "--station", "-s", help="Kod stacji"),
    years: str = typer.Option(..., "--years", "-y", help="Zakres lat (np. 2020-2023)"),
    interval: str = typer.Option(
        "dobowe",
        "--interval", "-i",
        help="Interwal: dobowe, miesieczne, polroczne"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Zapisz do pliku CSV"),
):
    """
    Zapytaj o dane dla stacji i zakresu lat.

    Automatycznie pobiera brakujace dane z IMGW (lazy loading).
    """
    check_db_enabled()

    from imgwtools.db import db_exists, get_cache_manager, init_db

    # Parse year range
    if "-" in years:
        parts = years.split("-")
        start_year = int(parts[0])
        end_year = int(parts[1])
    else:
        start_year = end_year = int(years)

    if not db_exists():
        init_db()

    async def run_query():
        manager = get_cache_manager()

        # Ensure data is cached (lazy loading)
        with console.status("[bold green]Sprawdzanie i pobieranie danych..."):
            for year in range(start_year, end_year + 1):
                if interval == "dobowe" and year < 2023:
                    for month in range(1, 13):
                        await manager.ensure_data_cached(interval, year, month)
                else:
                    await manager.ensure_data_cached(interval, year)

        # Query data
        if interval == "dobowe":
            return manager.get_daily_data(station, start_year, end_year)
        elif interval == "miesieczne":
            return manager.get_monthly_data(station, start_year, end_year)
        else:
            return manager.get_semi_annual_data(station, start_year, end_year)

    records = asyncio.run(run_query())

    if not records:
        console.print(f"[yellow]Brak danych dla stacji {station} w latach {start_year}-{end_year}[/yellow]")
        return

    # Output to file or table
    if output:
        import csv
        with open(output, "w", newline="", encoding="utf-8") as f:
            if records:
                writer = csv.DictWriter(f, fieldnames=records[0].model_dump().keys())
                writer.writeheader()
                for r in records:
                    writer.writerow(r.model_dump())
        console.print(f"[green]Zapisano {len(records)} rekordow do {output}[/green]")
    else:
        # Display first 20 records in table
        table = Table(title=f"Dane dla stacji {station} ({len(records)} rekordow)")

        if interval == "dobowe":
            table.add_column("Data", style="cyan")
            table.add_column("Stan [cm]", justify="right")
            table.add_column("Przeplyw [m3/s]", justify="right")
            table.add_column("Temp [°C]", justify="right")

            for r in records[:20]:
                table.add_row(
                    r.measurement_date or "-",
                    f"{r.water_level_cm:.0f}" if r.water_level_cm else "-",
                    f"{r.flow_m3s:.3f}" if r.flow_m3s else "-",
                    f"{r.water_temp_c:.1f}" if r.water_temp_c else "-",
                )
        elif interval == "miesieczne":
            table.add_column("Rok", style="cyan")
            table.add_column("Miesiac", justify="right")
            table.add_column("Ekstremum")
            table.add_column("Stan [cm]", justify="right")
            table.add_column("Przeplyw [m3/s]", justify="right")

            for r in records[:20]:
                table.add_row(
                    str(r.hydro_year),
                    str(r.hydro_month),
                    r.extremum,
                    f"{r.water_level_cm:.0f}" if r.water_level_cm else "-",
                    f"{r.flow_m3s:.3f}" if r.flow_m3s else "-",
                )

        console.print(table)

        if len(records) > 20:
            console.print(f"\n[dim]Pokazano 20 z {len(records)} rekordow. Uzyj --output aby zapisac wszystkie.[/dim]")
