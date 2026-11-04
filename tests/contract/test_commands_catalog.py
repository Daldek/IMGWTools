"""``obserwator-commands/1`` follows Nogat's ``commands-1`` (AGI-2.2, AGI-2.4, D5):
the description of every command and the whole catalog validate in both languages,
within the page budget (DOC-1.7); the summary ``obserwator-command-list/1`` stays
within it too."""

import json

import pytest

from obserwator import command_schema, list_commands
from obserwator.commands import data_commands, parse_command
from obserwator.messages import LANGS
from tests.contract.nogat import validate

NAMES = [spec.name for spec in data_commands()]
# DOC-1.7: the default page of a CLI or MCP result (compact JSON, as a client gets it)
PAGE_BUDGET = 20_000


def _size(document: object) -> int:
    return len(json.dumps(document, ensure_ascii=False, separators=(",", ":")))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", NAMES)
def test_the_description_of_every_command_validates_against_commands_1(name, lang):
    document = command_schema(name, lang=lang)

    validate(document, "commands-1")
    (entry,) = document["commands"]
    assert document["schema"] == "obserwator-commands/1"
    assert entry["name"] == name
    assert _size(document) <= PAGE_BUDGET


@pytest.mark.parametrize("lang", LANGS)
def test_the_whole_catalog_validates_against_commands_1(lang):
    document = command_schema(lang=lang)

    validate(document, "commands-1")
    assert [entry["name"] for entry in document["commands"]] == NAMES


@pytest.mark.parametrize("lang", LANGS)
def test_the_list_names_every_command_within_the_page_budget(lang):
    document = list_commands(lang=lang)

    assert document["schema"] == "obserwator-command-list/1"
    assert [row["name"] for row in document["commands"]] == NAMES
    assert _size(document) <= PAGE_BUDGET


@pytest.mark.parametrize("name", NAMES)
def test_every_example_call_is_a_call_of_its_command(name):
    (entry,) = command_schema(name)["commands"]

    for example in entry["examples"]:
        assert parse_command(example["call"]).command == name


def test_the_polish_texts_are_in_i18n_in_both_languages():
    english = command_schema("store sync", lang="en")["commands"][0]
    polish = command_schema("store sync", lang="pl")["commands"][0]

    assert english["i18n"] == polish["i18n"]
    assert english["i18n"]["pl"]["description"] == polish["description"]
    assert english["description"] != polish["description"]
