"""Both languages of the catalog texts (spec 2026-10-19 §3.3, §4.1, §9; ADR-006)."""

import json
from typing import Any

import pytest

from imgwtools.commands import command_schema, data_commands, validate_command
from imgwtools.datasets import datasets
from imgwtools.exceptions import IMGWValidationError
from imgwtools.messages import Message, localize


def without_texts(schema: dict[str, Any]) -> dict[str, Any]:
    """A command schema without the texts of its language."""
    copy: dict[str, Any] = json.loads(json.dumps(schema))
    del copy["description"]
    for prop in copy["properties"].values():
        del prop["description"]
    del copy["x-imgw"]["rules"]
    return copy


def structure(document: dict[str, Any]) -> dict[str, Any]:
    """The catalog document without the texts of its language and its ``lang``."""
    copy: dict[str, Any] = json.loads(json.dumps(document))
    del copy["lang"]
    copy["groups"] = list(copy["groups"])
    copy["commands"] = [without_texts(schema) for schema in copy["commands"]]
    for error in copy["errors"]:
        del error["title"]
    return copy


def texts(document: dict[str, Any]) -> list[str]:
    """Every text of the catalog document in its language."""
    found = list(document["groups"].values())
    for schema in document["commands"]:
        found.append(schema["description"])
        found += [prop["description"] for prop in schema["properties"].values()]
        found += schema["x-imgw"]["rules"]
    return found + [error["title"] for error in document["errors"]]


def ambiguous(pairs: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Texts translated in more than one way, in either direction."""
    found: dict[str, set[str]] = {}
    for polish, english in pairs:
        found.setdefault(f"pl:{polish}", set()).add(english)
        found.setdefault(f"en:{english}", set()).add(polish)
    return {text: variants for text, variants in found.items() if len(variants) > 1}


def assert_translated(text: object, where: object) -> None:
    """A catalog message whose Polish variant differs from its English text."""
    assert isinstance(text, Message), where
    assert localize(text, "pl") not in ("", str(text)), where


def test_every_text_of_the_catalog_and_registries_is_a_message_with_both_languages():
    for spec in data_commands():
        assert_translated(spec.description, spec.name)
        for rule in spec.rules:
            assert_translated(rule, spec.name)
        for option in spec.options:
            assert_translated(option.help, (spec.name, option.name))
    for descriptor in datasets():
        assert_translated(descriptor.title, descriptor.key)
    polish, english = command_schema(lang="pl")["groups"], command_schema()["groups"]
    assert all(english[name] not in ("", text) for name, text in polish.items())


def test_option_help_and_rules_translate_one_to_one():
    # A text that two entries translate differently would be one of them mistyped.
    specs = data_commands()
    helps = [
        (localize(o.help, "pl"), str(o.help)) for spec in specs for o in spec.options
    ]
    rules = [(localize(r, "pl"), str(r)) for spec in specs for r in spec.rules]
    assert ambiguous(helps) == {}
    assert ambiguous(rules) == {}


def test_english_catalog_differs_from_the_polish_one_only_in_texts():
    polish, english = command_schema(lang="pl"), command_schema(lang="en")

    assert (polish["lang"], english["lang"]) == ("pl", "en")
    assert structure(english) == structure(polish)
    assert set(texts(english)).isdisjoint(texts(polish))
    for schema in polish["commands"]:
        single = command_schema(schema["title"], lang="en")
        assert without_texts(single) == without_texts(schema)
        assert single == next(
            other for other in english["commands"] if other["title"] == schema["title"]
        )


@pytest.mark.parametrize("lang", ["de", "EN", ""])
def test_language_outside_pl_and_en_is_a_validation_error(lang):
    for call in (
        lambda: command_schema(lang=lang),
        lambda: validate_command("commands schema", options={"lang": lang}),
    ):
        with pytest.raises(IMGWValidationError) as error:
            call()
        assert error.value.details["option"] == "lang"
        assert error.value.details["allowed"] == ["en", "pl"]
