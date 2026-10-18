"""``imgw pmaxtp`` group: PMAXTP cells kept in the store (spec §10).

Not to be confused with the live ``imgw fetch pmaxtp``. Commands, flags and help
texts come from the data command catalog; execution goes through `run_command`.
"""

import typer

from imgwtools.cli._dispatch import register_group

app = typer.Typer(
    help="Komórki PMAXTP zapisane w magazynie IMGW (różne od live: imgw fetch pmaxtp)",
    no_args_is_help=True,
)
register_group(app, "pmaxtp")
