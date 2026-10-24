"""``imgw config show``: the settings in force and where each comes from (DEV-18.6)."""

from typing import Any

import typer

from imgwtools.cli._dispatch import ImgwCommand, ImgwSubgroup, _json, _localized
from imgwtools.config import environment_report

app = typer.Typer(
    help=_localized(
        "Ustawienia użytkownika: nogat.toml i zmienne środowiskowe",
        "User settings: nogat.toml and environment variables",
    ),
    cls=ImgwSubgroup,
)


def _origin(entry: dict[str, Any]) -> str:
    if entry["source"] == "default":
        return _localized("domyślnie", "default")
    return f"{entry['source']} {entry['name']}"


def _render(report: dict[str, Any]) -> str:
    """Human-readable form of the report, in the language of the CLI."""
    file = report["config_file"]
    if file["error"] is not None:
        state = f"{_localized('błąd', 'error')}: {file['error']}"
    else:
        state = (
            _localized("istnieje", "exists")
            if file["exists"]
            else _localized("brak", "absent")
        )
    lines = [
        f"{_localized('Plik ustawień', 'Settings file')}: {file['path']} ({state})",
        f"{_localized('Ustawienia', 'Settings')}:",
    ]
    for key, entry in report["keys"].items():
        lines.append(f"  {key} = {_json(entry['value'])}  [{_origin(entry)}]")
    lines.append(
        f"{_localized('Dane uwierzytelniające (tylko środowisko)', 'Credentials (environment only)')}:"
    )
    for name, state in report["credentials"].items():
        lines.append(
            f"  {name}: {_localized('ustawiony', 'present') if state == 'present' else _localized('brak', 'missing')}"
        )
    store = report["store"]
    if store["root"] is None:
        lines.append(
            f"{_localized('Magazyn', 'Store')}: {_localized('nie ustawiono', 'not set')}"
        )
    else:
        size = store["size_bytes"]
        shown = (
            _localized("brak katalogu", "no directory") if size is None else f"{size} B"
        )
        lines.append(
            f"{_localized('Magazyn', 'Store')}: {store['root']}  [{_origin(store)}]  {shown}"
        )
    return "\n".join(lines)


@app.command(
    "show",
    cls=ImgwCommand,
    help=_localized(
        "Pokaż każde ustawienie z wartością i źródłem, dane uwierzytelniające "
        "(ustawione albo brak) oraz katalog magazynu z rozmiarem.",
        "Show every setting with its value and source, the credentials (present "
        "or missing) and the store root with its size.",
    ),
)
def show(
    as_json: bool = typer.Option(
        False,
        "--json",
        help=_localized(
            "Wypisz jeden dokument JSON imgw-config/1 (bez opisów)",
            "Print one imgw-config/1 JSON document (no prose)",
        ),
    ),
) -> None:
    """Show the settings in force (``imgw-config/1`` with ``--json``)."""
    report = environment_report()
    typer.echo(_json(report) if as_json else _render(report))
