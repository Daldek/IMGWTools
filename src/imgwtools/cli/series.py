"""``imgw series`` group: build, select and export store series (spec §10).

Commands, flags and help texts come from the data command catalog
(`imgwtools.commands.data_commands`); execution goes through `run_command`.
"""

import typer

from imgwtools.cli._dispatch import register_group

app = typer.Typer(
    help="Szeregi Parquet magazynu IMGW: budowa, wybór i eksport CSV",
    no_args_is_help=True,
)
register_group(app, "series")
