"""Validation against the vendored Nogat schemas (``schemas/nogat/``, D6).

``validate(document, "commands-1")`` raises when a document of Obserwator does not
follow the schema of Nogat's standard 1.0; the message lists every error with its
path, so a failing test names all of them at once.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, Literal

import jsonschema
from referencing import Registry, Resource

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas" / "nogat"
SchemaName = Literal["result-1", "error-1", "commands-1"]
SCHEMA_NAMES: tuple[SchemaName, ...] = ("result-1", "error-1", "commands-1")


def load_schema(name: SchemaName) -> dict[str, Any]:
    """The vendored schema ``name`` (``schemas/nogat/<name>.schema.json``)."""
    path = SCHEMAS_DIR / f"{name}.schema.json"
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return schema


def load_registry() -> dict[str, Any]:
    """The vendored Nogat error registry (``schemas/nogat/error_registry.json``)."""
    path = SCHEMAS_DIR / "error_registry.json"
    registry: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return registry


@cache
def _validator(name: SchemaName) -> jsonschema.Draft202012Validator:
    # The schemas refer to each other by ``$id`` (``commands-1`` lists the codes
    # of ``error-1``), so all of them are registered.
    registry: Registry[Any] = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in map(load_schema, SCHEMA_NAMES)
    )
    return jsonschema.Draft202012Validator(load_schema(name), registry=registry)


def schema_errors(document: object, name: SchemaName) -> list[str]:
    """Every violation of the schema ``name`` by ``document``, as ``path: message``."""
    return [
        f"{error.json_path}: {error.message}"
        for error in sorted(
            _validator(name).iter_errors(document), key=lambda e: e.json_path
        )
    ]


def validate(document: object, schema_name: SchemaName) -> None:
    """
    Check ``document`` (a parsed JSON document) against a vendored Nogat schema.

    Raises
    ------
    AssertionError
        Listing every violation when the document does not validate.
    """
    errors = schema_errors(document, schema_name)
    if errors:
        raise AssertionError(
            f"{len(errors)} violation(s) of {schema_name}:\n" + "\n".join(errors)
        )
