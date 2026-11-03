"""``imgw config show``: the settings in force and where each comes from (DEV-18.6)."""

from typing import Any

import typer

from imgwtools.cli._dispatch import _LANG, ImgwCommand, ImgwSubgroup, _json
from imgwtools.config import environment_report
from imgwtools.messages import message

app = typer.Typer(help=message("cli.config_help", lang=_LANG), cls=ImgwSubgroup)


def _origin(entry: dict[str, Any]) -> str:
    if entry["source"] == "default":
        return message("cli.config_default", lang=_LANG)
    return f"{entry['source']} {entry['name']}"


def _render(report: dict[str, Any]) -> str:
    """Human-readable form of the report, in the language of the CLI."""
    file = report["config_file"]
    if file["error"] is not None:
        state = f"{message('cli.config_file_error', lang=_LANG)}: {file['error']}"
    else:
        state = message(
            "cli.config_file_exists" if file["exists"] else "cli.config_file_absent",
            lang=_LANG,
        )
    lines: list[str] = [
        message("cli.config_file_line", lang=_LANG, path=file["path"], state=state),
        message("cli.config_settings_title", lang=_LANG),
    ]
    for key, entry in report["keys"].items():
        lines.append(f"  {key} = {_json(entry['value'])}  [{_origin(entry)}]")
    lines.append(message("cli.config_credentials_title", lang=_LANG))
    for name, state in report["credentials"].items():
        shown = message(
            "cli.config_credential_present"
            if state == "present"
            else "cli.config_credential_missing",
            lang=_LANG,
        )
        lines.append(f"  {name}: {shown}")
    store = report["store"]
    if store["root"] is None:
        lines.append(message("cli.config_store_unset", lang=_LANG))
    else:
        size = store["size_bytes"]
        lines.append(
            message(
                "cli.config_store",
                lang=_LANG,
                root=store["root"],
                origin=_origin(store),
                size=(
                    message("cli.config_store_no_directory", lang=_LANG)
                    if size is None
                    else f"{size} B"
                ),
            )
        )
    return "\n".join(lines)


@app.command("show", cls=ImgwCommand, help=message("cli.config_show_help", lang=_LANG))
def show(
    as_json: bool = typer.Option(
        False,
        "--json",
        help=message("cli.config_json_help", lang=_LANG),
    ),
) -> None:
    """Show the settings in force (``imgw-config/1`` with ``--json``)."""
    report = environment_report()
    typer.echo(_json(report) if as_json else _render(report))
