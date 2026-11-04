"""Contract: command lines read back into their calls (AGI-2.1, AGI-2.2).

An example call of the catalog (``examples`` of `command_schema`) is a
canonical line: ``parse_command`` reads it into a call of its command whose options
pass ``validate_command``, ``format_command`` writes that call as the same line in
every environment (its POSIX paths absolute there, on Windows with the drive of the
working directory), and its result excerpt names only fields of the command's result.

A sample is a valid call of a catalog command: the options of every command in
``tests.unit.test_commands`` and of the ČHMÚ calls in ``tests.unit.test_commands_chmi``,
each also with ``--check`` where the command has it. Its line is the one
``format_command`` writes. ``parse_command`` reads that line into the same command
and run and into options that validate to the same call, and ``format_command`` of
that call writes the same line again, so a tool that exchanges ``obserwator`` lines
(Archiwista) compares them as text.
"""

import dataclasses
import re
import shlex
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

import obserwator
from obserwator import (
    data_commands,
    format_command,
    parse_command,
    validate_command,
)
from obserwator.output import OutputReport
from obserwator.store.types import StorePlan
from tests.contract.support import input_schemas
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
CATALOG = [schema["x-obserwator"] for schema in input_schemas()]
CATALOG_EXAMPLES = [
    pytest.param(meta, example, id=f"{meta['command']}#{index}")
    for meta in CATALOG
    for index, example in enumerate(meta["examples"])
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


def test_every_catalog_command_has_an_example_call():
    assert [meta["command"] for meta in CATALOG if not meta["examples"]] == []


def native(line: str) -> str:
    """``line`` with each POSIX path as `format_command` writes it here: absolute."""
    return re.sub(
        r"(?<= )/\S*", lambda path: shlex.quote(str(Path(path[0]).absolute())), line
    )


@pytest.mark.parametrize(("meta", "example"), CATALOG_EXAMPLES)
def test_every_catalog_example_call_is_a_canonical_line(
    meta, example, monkeypatch, tmp_path
):
    # The default store root differs per user: a canonical example never relies on it.
    monkeypatch.setenv("OBSERWATOR_ROOT", str(tmp_path))

    call = parse_command(example["call"])

    assert call.command == meta["command"]
    validate_command(call.command, options=call.options)
    line = format_command(call.command, options=call.options, run=call.run)
    assert line == native(example["call"])


def _fields(type_: type) -> set[str]:
    """The keys of the JSON form of a result type (``obserwator._jsonable``)."""
    named = {"schema"} if hasattr(type_, "SCHEMA") else set()
    if issubclass(type_, BaseModel):
        return named | set(type_.model_fields)
    assert dataclasses.is_dataclass(type_), type_
    return named | {field.name for field in dataclasses.fields(type_)}


def assert_document(excerpt: dict[str, Any], type_: type) -> None:
    """``excerpt`` names fields of ``type_`` and the ``schema`` of its document."""
    assert set(excerpt) <= _fields(type_)
    schema = getattr(type_, "SCHEMA", None)
    if "schema" in excerpt and schema is not None:
        assert excerpt["schema"] == schema


@pytest.mark.parametrize(("meta", "example"), CATALOG_EXAMPLES)
def test_every_catalog_example_result_names_fields_of_the_result(meta, example):
    call = parse_command(example["call"])
    excerpt = example["result"]
    item = getattr(obserwator, meta["result_type"], None)

    if call.run.get("check"):
        assert_document(excerpt, StorePlan)
    elif meta["result"] == "list":
        # The items of a page: the first one is excerpted.
        assert isinstance(excerpt, list)
        (first,) = excerpt
        assert_document(first, item)
    elif meta["result"] == "stream":
        if "output" in call.options:
            assert_document(excerpt, OutputReport)
        else:
            assert isinstance(excerpt, str)
    elif item is None:
        assert isinstance(excerpt, dict if meta["result_type"] == "dict" else str)
    else:
        assert_document(excerpt, item)
