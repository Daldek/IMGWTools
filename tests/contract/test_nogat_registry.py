"""The vendored Nogat standard (``schemas/nogat/``, ERR-3): the error registry of
Obserwator agrees with Nogat's, and the vendored schemas are valid JSON Schemas."""

import jsonschema
import pytest

from obserwator.exceptions import ERROR_CODES
from tests.contract.nogat import SCHEMA_NAMES, load_registry, load_schema

REGISTRY = {entry["code"]: entry for entry in load_registry()["errors"]}


@pytest.mark.parametrize("code", list(ERROR_CODES))
def test_every_error_code_has_the_exit_code_status_and_titles_of_the_registry(code):
    spec = ERROR_CODES[code]
    entry = REGISTRY[code]

    assert (spec.exit_code, spec.http_status) == (
        entry["exit_code"],
        entry["http_status"],
    )
    assert spec.title.localized("en") == entry["title_en"]
    assert spec.title.localized("pl") == entry["title_pl"]


def test_the_envelope_exit_codes_are_the_outcomes_of_the_registry():
    from obserwator.commands import command_schema

    outcomes = {o["status"]: o["exit_code"] for o in load_registry()["outcomes"]}

    assert command_schema()["exit_codes"] == outcomes


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_vendored_schema_is_a_valid_json_schema(name):
    jsonschema.Draft202012Validator.check_schema(load_schema(name))


def test_vendored_error_schema_lists_the_registry_codes():
    codes = load_schema("error-1")["$defs"]["code"]["enum"]

    assert codes == list(REGISTRY)
