"""Admin commands for API key management."""

import json
import secrets
from datetime import datetime
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from imgwtools.cli._dispatch import _HELP, _LANG, ImgwCommand, ImgwSubgroup
from imgwtools.config import settings
from imgwtools.messages import message

app = typer.Typer(help=message("cli.admin_help", lang=_LANG), cls=ImgwSubgroup)
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


def _say(text: str, style: str | None = None, /, **values: object) -> None:
    """Print the catalog text ``text`` in the language of the CLI; values stay plain."""
    console.print(message(text, lang=_LANG, **values), style=style, markup=False)


@app.command("keys", cls=ImgwCommand, help=message("cli.admin_keys_help", lang=_LANG))
def list_keys() -> None:
    """List the API keys."""
    data = load_api_keys()
    keys = data.get("keys", [])

    if not keys:
        _say("cli.admin_no_keys", "yellow")
        return

    table = Table(title=message("cli.admin_keys_title", lang=_LANG))
    table.add_column("ID", style="cyan")
    table.add_column(message("cli.admin_column_name", lang=_LANG), style="green")
    table.add_column(message("cli.admin_column_created", lang=_LANG), style="blue")
    table.add_column(message("cli.admin_column_active", lang=_LANG), style="yellow")

    for key in keys:
        table.add_row(
            key["id"][:8] + "...",
            key["name"],
            key["created_at"],
            message(
                "cli.admin_yes" if key.get("active", True) else "cli.admin_no",
                lang=_LANG,
            ),
        )

    console.print(table)


@app.command(
    "create", cls=ImgwCommand, help=message("cli.admin_create_help", lang=_LANG)
)
def create_key(
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        metavar=_HELP.metavars["str"],
        help=message("cli.admin_name_help", lang=_LANG),
    ),
    rate_limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        metavar=_HELP.metavars["int"],
        help=message("cli.admin_limit_help", lang=_LANG),
    ),
) -> None:
    """Create a new API key (``imgw admin create --name "User1" --limit 100``)."""
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

    _say("cli.admin_key_created", "bold green")
    console.print()
    _say("cli.admin_name_line", name=name)
    _say("cli.admin_key_line", key=key_id)
    _say("cli.admin_limit_line", limit=rate_limit)
    console.print()
    _say("cli.admin_save_key", "yellow")


@app.command(
    "revoke", cls=ImgwCommand, help=message("cli.admin_revoke_help", lang=_LANG)
)
def revoke_key(
    key_id: str = typer.Argument(
        ...,
        metavar=message("cli.admin_metavar_id", lang=_LANG),
        help=message("cli.admin_revoke_id_help", lang=_LANG),
    ),
) -> None:
    """Revoke an API key (``imgw admin revoke abc123``)."""
    data = load_api_keys()

    found = False
    for key in data["keys"]:
        if key["id"].startswith(key_id):
            key["active"] = False
            found = True
            _say("cli.admin_key_revoked", "green", name=key["name"])
            break

    if not found:
        _say("cli.admin_key_not_found", "red", key_id=key_id)
        raise typer.Exit(1)

    save_api_keys(data)


@app.command(
    "delete", cls=ImgwCommand, help=message("cli.admin_delete_help", lang=_LANG)
)
def delete_key(
    key_id: str = typer.Argument(
        ...,
        metavar=message("cli.admin_metavar_id", lang=_LANG),
        help=message("cli.admin_delete_id_help", lang=_LANG),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help=message("cli.admin_force_help", lang=_LANG),
    ),
) -> None:
    """Delete an API key (``imgw admin delete abc123 --force``)."""
    data = load_api_keys()

    key_to_delete = None
    for key in data["keys"]:
        if key["id"].startswith(key_id):
            key_to_delete = key
            break

    if not key_to_delete:
        _say("cli.admin_key_not_found", "red", key_id=key_id)
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(
            message("cli.admin_confirm_delete", lang=_LANG, name=key_to_delete["name"])
        )
        if not confirm:
            raise typer.Abort()

    data["keys"].remove(key_to_delete)
    save_api_keys(data)

    _say("cli.admin_key_deleted", "green", name=key_to_delete["name"])


@app.command("stats", cls=ImgwCommand, help=message("cli.admin_stats_help", lang=_LANG))
def key_stats(
    key_id: str | None = typer.Argument(
        None,
        metavar=message("cli.admin_metavar_id", lang=_LANG),
        help=message("cli.admin_stats_id_help", lang=_LANG),
    ),
) -> None:
    """Usage statistics of the API keys (``imgw admin stats [ID]``)."""
    data = load_api_keys()
    keys = data.get("keys", [])

    if not keys:
        _say("cli.admin_no_keys", "yellow")
        return

    table = Table(title=message("cli.admin_stats_title", lang=_LANG))
    table.add_column(message("cli.admin_column_name", lang=_LANG), style="green")
    table.add_column("Limit", style="cyan")
    table.add_column(message("cli.admin_column_requests", lang=_LANG), style="blue")
    table.add_column("Status", style="yellow")

    for key in keys:
        if key_id is None or key["id"].startswith(key_id):
            status = message(
                "cli.admin_active" if key.get("active", True) else "cli.admin_inactive",
                lang=_LANG,
            )
            table.add_row(
                key["name"],
                str(key.get("rate_limit", 100)),
                str(key.get("request_count", 0)),
                status,
            )

    console.print(table)
