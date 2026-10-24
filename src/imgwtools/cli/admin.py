"""Admin commands for API key management."""

import json
import secrets
from datetime import datetime
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from imgwtools.cli._dispatch import ImgwCommand, ImgwSubgroup
from imgwtools.config import settings

app = typer.Typer(help="Administracja kluczy API", cls=ImgwSubgroup)
console = Console()


def load_api_keys() -> dict[str, Any]:
    """Load API keys from file."""
    if not settings.api_keys_file.exists():
        return {"keys": []}

    with open(settings.api_keys_file, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def save_api_keys(data: dict[str, Any]) -> None:
    """Save API keys to file."""
    settings.api_keys_file.parent.mkdir(parents=True, exist_ok=True)

    with open(settings.api_keys_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.command("keys", cls=ImgwCommand)
def list_keys() -> None:
    """Lista kluczy API."""
    data = load_api_keys()
    keys = data.get("keys", [])

    if not keys:
        console.print("[yellow]Brak zarejestrowanych kluczy API[/yellow]")
        return

    table = Table(title="Klucze API")
    table.add_column("ID", style="cyan")
    table.add_column("Nazwa", style="green")
    table.add_column("Utworzono", style="blue")
    table.add_column("Aktywny", style="yellow")

    for key in keys:
        table.add_row(
            key["id"][:8] + "...",
            key["name"],
            key["created_at"],
            "Tak" if key.get("active", True) else "Nie",
        )

    console.print(table)


@app.command("create", cls=ImgwCommand)
def create_key(
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        metavar="TEKST",
        help="Nazwa klucza",
    ),
    rate_limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        metavar="LICZBA",
        help="Limit zapytań na godzinę",
    ),
) -> None:
    """
    Utwórz nowy klucz API.

    Przykład:
        imgw admin create --name "User1" --limit 100
    """
    data = load_api_keys()

    # Generate new key
    key_id = secrets.token_urlsafe(32)

    new_key = {
        "id": key_id,
        "name": name,
        "rate_limit": rate_limit,
        "created_at": datetime.now().isoformat(),
        "active": True,
        "request_count": 0,
    }

    data["keys"].append(new_key)
    save_api_keys(data)

    console.print("[bold green]Klucz API utworzony![/bold green]")
    console.print()
    console.print(f"[bold]Nazwa:[/bold] {name}")
    console.print(f"[bold]Klucz:[/bold] {key_id}")
    console.print(f"[bold]Limit:[/bold] {rate_limit} zapytań/h")
    console.print()
    console.print(
        "[yellow]Zapisz ten klucz – nie będzie można go odczytać ponownie![/yellow]"
    )


@app.command("revoke", cls=ImgwCommand)
def revoke_key(
    key_id: str = typer.Argument(
        ...,
        metavar="IDENTYFIKATOR",
        help="Identyfikator klucza do unieważnienia (wystarczy początek)",
    ),
) -> None:
    """
    Unieważnij klucz API.

    Przykład:
        imgw admin revoke abc123
    """
    data = load_api_keys()

    found = False
    for key in data["keys"]:
        if key["id"].startswith(key_id):
            key["active"] = False
            found = True
            console.print(f"[green]Klucz {key['name']} został unieważniony[/green]")
            break

    if not found:
        console.print(f"[red]Nie znaleziono klucza: {key_id}[/red]")
        raise typer.Exit(1)

    save_api_keys(data)


@app.command("delete", cls=ImgwCommand)
def delete_key(
    key_id: str = typer.Argument(
        ...,
        metavar="IDENTYFIKATOR",
        help="Identyfikator klucza do usunięcia (wystarczy początek)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Usuń bez potwierdzenia",
    ),
) -> None:
    """
    Usuń klucz API.

    Przykład:
        imgw admin delete abc123 --force
    """
    data = load_api_keys()

    key_to_delete = None
    for key in data["keys"]:
        if key["id"].startswith(key_id):
            key_to_delete = key
            break

    if not key_to_delete:
        console.print(f"[red]Nie znaleziono klucza: {key_id}[/red]")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Usunąć klucz {key_to_delete['name']}?")
        if not confirm:
            raise typer.Abort()

    data["keys"].remove(key_to_delete)
    save_api_keys(data)

    console.print(f"[green]Klucz {key_to_delete['name']} został usunięty[/green]")


@app.command("stats", cls=ImgwCommand)
def key_stats(
    key_id: str | None = typer.Argument(
        None,
        metavar="IDENTYFIKATOR",
        help="Identyfikator klucza (opcjonalnie)",
    ),
) -> None:
    """
    Statystyki użycia kluczy API.

    Przykład:
        imgw admin stats
        imgw admin stats abc123
    """
    data = load_api_keys()
    keys = data.get("keys", [])

    if not keys:
        console.print("[yellow]Brak zarejestrowanych kluczy API[/yellow]")
        return

    table = Table(title="Statystyki kluczy API")
    table.add_column("Nazwa", style="green")
    table.add_column("Limit", style="cyan")
    table.add_column("Zapytania", style="blue")
    table.add_column("Status", style="yellow")

    for key in keys:
        if key_id is None or key["id"].startswith(key_id):
            status = "Aktywny" if key.get("active", True) else "Nieaktywny"
            table.add_row(
                key["name"],
                str(key.get("rate_limit", 100)),
                str(key.get("request_count", 0)),
                status,
            )

    console.print(table)
