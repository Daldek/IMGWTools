"""Contract: the line of every example reads back into its call (AGI-2.1).

An example is a valid call of a catalog command: the options of every command in
``tests.unit.test_commands`` and of the ČHMÚ calls in ``tests.unit.test_commands_chmi``,
each also with ``--check`` where the command has it. Its line is the one
``format_command`` writes. ``parse_command`` reads that line into the same command
and run and into options that validate to the same call, and ``format_command`` of
that call writes the same line again, so a tool that exchanges ``imgw`` lines
(Archiwista) compares them as text.
"""

import pytest

from imgwtools import data_commands, format_command, parse_command, validate_command
from tests.unit.test_commands import SAMPLES
from tests.unit.test_commands_chmi import VALID as CHMI_SAMPLES

CHECKED = {spec.name for spec in data_commands() if spec.check is not None}
EXAMPLES = [
    pytest.param(
        command, options, run, id=f"{command}#{index}{' --check' if run else ''}"
    )
    for index, (command, options) in enumerate([*SAMPLES, *CHMI_SAMPLES])
    for run in (({}, {"check": True}) if command in CHECKED else ({},))
]


def test_the_examples_cover_every_command_of_the_catalog():
    assert {param.values[0] for param in EXAMPLES} == {
        spec.name for spec in data_commands()
    }


@pytest.mark.parametrize(("command", "options", "run"), EXAMPLES)
def test_the_line_of_every_example_reads_back_into_its_call(command, options, run):
    line = format_command(command, options=options, run=run)

    call = parse_command(line)

    assert (call.command, call.run) == (command, run)
    assert validate_command(command, options=call.options) == validate_command(
        command, options=options
    )
    assert format_command(call.command, options=call.options, run=call.run) == line
