"""
List command for displaying stations and datasets.
"""


import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Listowanie stacji i zbiorow danych")
console = Console()


@app.command("stations")
def list_stations(
    data_type: str = typer.Option(
        "hydro",
        "--type", "-t",
        help="Typ stacji: hydro lub meteo",
    ),
    limit: int = typer.Option(
        50,
        "--limit", "-l",
        help="Maksymalna liczba wynikow",
    ),
    search: str | None = typer.Option(
        None,
        "--search", "-s",
        help="Szukaj po nazwie",
    ),
):
    """
    Lista stacji pomiarowych.

    Przykłady:
        imgw list stations --type hydro
        imgw list stations --type meteo --search Warszawa
    """
    import pandas as pd

    from imgwtools.config import settings

    if data_type == "hydro":
        csv_file = settings.hydro_stations_file
    elif data_type == "meteo":
        csv_file = settings.meteo_stations_file
    else:
        console.print(f"[red]Nieprawidlowy typ: {data_type}[/red]")
        raise typer.Exit(1)

    if not csv_file.exists():
        console.print(f"[yellow]Plik {csv_file} nie istnieje[/yellow]")
        console.print("Pobierz dane stacji lub skonfiguruj IMGW_DATA_DIR")
        raise typer.Exit(1)

    try:
        df = pd.read_csv(csv_file, encoding="utf-8")
    except Exception as e:
        console.print(f"[red]Blad odczytu pliku: {e}[/red]")
        raise typer.Exit(1)

    # Filter by search term
    if search:
        mask = df.iloc[:, 1].str.contains(search, case=False, na=False)
        df = df[mask]

    # Limit results
    df = df.head(limit)

    # Display table
    table = Table(title=f"Stacje {data_type}")
    table.add_column("ID", style="cyan")
    table.add_column("Nazwa", style="green")
    if data_type == "hydro":
        table.add_column("Rzeka", style="blue")

    for _, row in df.iterrows():
        if data_type == "hydro":
            table.add_row(str(row.iloc[0]), str(row.iloc[1]), str(row.iloc[2]) if len(row) > 2 else "")
        else:
            table.add_row(str(row.iloc[0]), str(row.iloc[1]))

    console.print(table)
    console.print(f"\nWyswietlono {len(df)} z {limit} wynikow")


@app.command("datasets")
def list_datasets(
    data_type: str | None = typer.Option(
        None,
        "--type", "-t",
        help="Filtruj po typie: hydro lub meteo",
    ),
):
    """
    Lista dostepnych zbiorow danych.

    Przykłady:
        imgw list datasets
        imgw list datasets --type hydro
    """
    table = Table(title="Dostepne zbiory danych")
    table.add_column("Typ", style="cyan")
    table.add_column("Interwal", style="green")
    table.add_column("Zakres lat", style="blue")
    table.add_column("Opis")

    datasets = [
        ("hydro", "dobowe", "1951-2023", "Dobowe dane hydrologiczne"),
        ("hydro", "miesieczne", "1951-2023", "Miesieczne dane hydrologiczne"),
        ("hydro", "polroczne_i_roczne", "1951-2023", "Polroczne/roczne dane (T, Q, H)"),
        ("meteo", "dobowe", "2001-2023", "Dobowe dane meteorologiczne"),
        ("meteo", "miesieczne", "2001-2023", "Miesieczne dane meteorologiczne"),
        ("meteo", "terminowe", "2001-2023", "Terminowe dane (co godzine)"),
    ]

    for d_type, interval, years, desc in datasets:
        if data_type is None or data_type == d_type:
            table.add_row(d_type, interval, years, desc)

    console.print(table)


@app.command("intervals")
def list_intervals():
    """
    Lista dostepnych interwalow danych.
    """
    console.print("[bold]Interwaly danych hydrologicznych:[/bold]")
    console.print("  - dobowe: dane dzienne (H, Q, T)")
    console.print("  - miesieczne: dane miesieczne")
    console.print("  - polroczne_i_roczne: dane polroczne i roczne")
    console.print()
    console.print("[bold]Interwaly danych meteorologicznych:[/bold]")
    console.print("  - dobowe: dane dzienne")
    console.print("  - miesieczne: dane miesieczne")
    console.print("  - terminowe: dane terminowe (co godzine)")
    console.print()
    console.print("[bold]Podtypy danych meteorologicznych:[/bold]")
    console.print("  - klimat: dane klimatyczne")
    console.print("  - opad: dane opadowe")
    console.print("  - synop: dane synoptyczne")
