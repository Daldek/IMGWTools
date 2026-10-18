"""``imgw store`` group: versioned IMGW store commands (spec §10).

Commands, flags and help texts come from the data command catalog
(`imgwtools.commands.data_commands`); execution goes through `run_command`.
"""

import typer

from imgwtools.cli._dispatch import register_group

app = typer.Typer(
    help="Wersjonowany magazyn danych IMGW (archiwa, katalog stacji, plan aktualności)",
    no_args_is_help=True,
)
register_group(app, "store")
