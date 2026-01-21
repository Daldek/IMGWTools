"""
Admin commands for API key management.
"""

import json
import secrets
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from imgwtools.config import settings

app = typer.Typer(help="Administracja kluczy API")
console = Console()


def load_api_keys() -> dict:
    """Load API keys from file."""
    if not settings.api_keys_file.exists():
        return {"keys": []}

    with open(settings.api_keys_file, encoding="utf-8") as f:
        return json.load(f)


def save_api_keys(data: dict) -> None:
    """Save API keys to file."""
    settings.api_keys_file.parent.mkdir(parents=True, exist_ok=True)

    with open(settings.api_keys_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.command("keys")
def list_keys():
    """
    Lista kluczy API.
    """
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


@app.command("create")
def create_key(
    name: str = typer.Option(
        ...,
        "--name", "-n",
        help="Nazwa klucza",
    ),
    rate_limit: int = typer.Option(
        100,
        "--limit", "-l",
        help="Limit zapytan na godzine",
    ),
):
    """
    Utworz nowy klucz API.

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
    console.print(f"[bold]Limit:[/bold] {rate_limit} req/h")
    console.print()
    console.print("[yellow]Zapisz ten klucz - nie bedzie mozna go odczytac ponownie![/yellow]")


@app.command("revoke")
def revoke_key(
    key_id: str = typer.Argument(
        ...,
        help="ID klucza do unieważnienia (wystarczy poczatek)",
    ),
):
    """
    Uniewazni klucz API.

    Przykład:
        imgw admin revoke abc123
    """
    data = load_api_keys()

    found = False
    for key in data["keys"]:
        if key["id"].startswith(key_id):
            key["active"] = False
            found = True
            console.print(f"[green]Klucz {key['name']} zostal uniewazniony[/green]")
            break

    if not found:
        console.print(f"[red]Nie znaleziono klucza: {key_id}[/red]")
        raise typer.Exit(1)

    save_api_keys(data)


@app.command("delete")
def delete_key(
    key_id: str = typer.Argument(
        ...,
        help="ID klucza do usuniecia (wystarczy poczatek)",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Usun bez potwierdzenia",
    ),
):
    """
    Usun klucz API.

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
        confirm = typer.confirm(f"Usunac klucz {key_to_delete['name']}?")
        if not confirm:
            raise typer.Abort()

    data["keys"].remove(key_to_delete)
    save_api_keys(data)

    console.print(f"[green]Klucz {key_to_delete['name']} zostal usuniety[/green]")


@app.command("stats")
def key_stats(
    key_id: str | None = typer.Argument(
        None,
        help="ID klucza (opcjonalne)",
    ),
):
    """
    Statystyki uzycia kluczy API.

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
    table.add_column("Zapytan", style="blue")
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
