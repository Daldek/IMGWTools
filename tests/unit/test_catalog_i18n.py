"""English variant of the catalog texts (spec 2026-10-19 §3.3, §4.1, §9)."""

import json
from typing import Any

import pytest

from imgwtools.commands import command_schema, data_commands, validate_command
from imgwtools.datasets import datasets
from imgwtools.exceptions import ERROR_CODES, IMGWValidationError


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


def test_every_text_of_the_catalog_and_registries_has_an_english_variant():
    for spec in data_commands():
        assert spec.description_en not in ("", spec.description), spec.name
        assert len(spec.rules_en) == len(spec.rules), spec.name
        for polish, english in zip(spec.rules, spec.rules_en, strict=True):
            assert english not in ("", polish), spec.name
        for option in spec.options:
            assert option.help_en not in ("", option.help), (spec.name, option.name)
    for error in ERROR_CODES.values():
        assert error.title_en not in ("", error.title), error.code
    for descriptor in datasets():
        assert descriptor.title_en not in ("", descriptor.title), descriptor.key
    polish, english = command_schema()["groups"], command_schema(lang="en")["groups"]
    assert all(english[name] not in ("", text) for name, text in polish.items())


def test_option_help_and_rules_translate_one_to_one():
    # An option re-described by replace(..., help=...) without help_en would
    # keep the English text of another Polish one.
    specs = data_commands()
    helps = [(o.help, o.help_en) for spec in specs for o in spec.options]
    rules = [
        pair for spec in specs for pair in zip(spec.rules, spec.rules_en, strict=True)
    ]
    assert ambiguous(helps) == {}
    assert ambiguous(rules) == {}


def test_english_catalog_differs_from_the_polish_one_only_in_texts():
    polish, english = command_schema(), command_schema(lang="en")

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
        assert error.value.details["allowed"] == ["pl", "en"]
