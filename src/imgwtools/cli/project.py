"""``imgw project`` group: ``imgw-project/1`` manifest commands (spec §10.1).

Commands, flags and help texts come from the data command catalog
(`imgwtools.commands.data_commands`); execution goes through `run_command`.
"""

import typer

from imgwtools.cli._dispatch import register_group

app = typer.Typer(
    help="Projekt imgw-project/1: zadania, przypięte wersje i weryfikacja",
    no_args_is_help=True,
)
register_group(app, "project")
