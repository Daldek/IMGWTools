"""Canonical content of archive files and its ``content_sha256`` (ADR-003 D17).

The bytes of an archive are stored 1:1 and their SHA-256 stays the identity of a
version. ``content_sha256`` is the SHA-256 of a canonical form of the same bytes;
it only decides whether other bytes carry new content (`write_archive`) and
whether a project pin can be restored by content. The registry of forms is
closed and append-only: a released form never changes, and another set of
volatile fields or another method needs a new identifier.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.messages import message


@dataclass(frozen=True)
class ContentForm:
    """
    Canonical form of an archive file.

    Attributes
    ----------
    id : str
        Identifier written as ``content_form``, e.g. ``"chmi-json/1"``.
    method : {"json-jcs"}
        Canonicalization: a JSON document without the volatile fields,
        serialized by RFC 8785 (JCS).
    volatile_fields : tuple of str
        Keys of the top-level object removed before hashing; nested fields
        are never removed.
    """

    id: str
    method: Literal["json-jcs"]
    volatile_fields: tuple[str, ...]


CONTENT_FORMS: Mapping[str, ContentForm] = MappingProxyType(
    {
        "chmi-json/1": ContentForm(
            "chmi-json/1", "json-jcs", ("zaznamID", "datumVytvoreni")
        ),
    }
)
"""Released canonical forms keyed by identifier (closed, append-only)."""


def content_sha256(data: bytes, /, *, form: str) -> str:
    """
    SHA-256 of the canonical form of archive bytes.

    The ``json-jcs`` method decodes strict UTF-8 (one leading BOM is
    dropped), parses RFC 8259 JSON with numbers as IEEE 754 doubles (like
    ``JSON.parse``), removes the form's volatile keys from the top-level
    object and serializes the rest by RFC 8785 (JCS): no whitespace, object
    keys sorted by UTF-16 code units, array order kept, minimal string
    escaping and ECMAScript number notation. Key order, whitespace, number
    spelling, string escaping and new volatile values therefore never change
    the result; any other change of a value, row or field does.

    Parameters
    ----------
    data : bytes
        Archive bytes exactly as downloaded.
    form : str
        Identifier of a form in `CONTENT_FORMS`, e.g. ``"chmi-json/1"``.

    Returns
    -------
    str
        64 lowercase hexadecimal digits.

    Raises
    ------
    IMGWValidationError
        If ``form`` is not a key of `CONTENT_FORMS`.
    IMGWDataError
        If the bytes do not meet the form: invalid UTF-8, invalid JSON, a
        repeated key in any object, ``NaN`` or ``Infinity``, a number beyond
        the double range, text after the top-level value, a top-level value
        that is not an object, or an unpaired surrogate in a string.
    """
    content_form = CONTENT_FORMS.get(form) if isinstance(form, str) else None
    if content_form is None:
        raise IMGWValidationError(
            message(
                "content.unknown_content_form_allowed",
                form=form,
                content_forms=", ".join(CONTENT_FORMS),
            ),
            details={
                "option": "form",
                "value": form if isinstance(form, str) else repr(form),
                "allowed": list(CONTENT_FORMS),
            },
        )
    document = _parse(data)
    if not isinstance(document, dict):
        raise IMGWDataError(message("content.root_value_json_document_not"))
    for key in content_form.volatile_fields:
        document.pop(key, None)
    try:
        canonical = _serialize(document).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IMGWDataError(
            message("content.json_string_contains_unpaired_utf")
        ) from exc
    except RecursionError as exc:
        raise IMGWDataError(message("content.json_document_nested_too_deeply")) from exc
    return hashlib.sha256(canonical).hexdigest()


def _parse(data: bytes) -> object:
    """Steps 1-2 of ``json-jcs``: strict UTF-8 and RFC 8259 JSON of doubles."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IMGWDataError(
            message("content.content_not_valid_utf_8", start=exc.start)
        ) from exc
    try:
        return json.loads(
            text.removeprefix("\ufeff"),
            object_pairs_hook=_unique_keys,
            parse_constant=_constant,
            parse_float=_double,
            parse_int=_double,
        )
    except json.JSONDecodeError as exc:
        raise IMGWDataError(
            message(
                "content.invalid_json_line_column",
                msg=exc.msg,
                lineno=exc.lineno,
                colno=exc.colno,
            )
        ) from exc
    except RecursionError as exc:
        raise IMGWDataError(message("content.json_document_nested_too_deeply")) from exc


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Object of a JSON document; a key repeated in one object is an error."""
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise IMGWDataError(message("content.repeated_key_json_object", key=key))
        document[key] = value
    return document


def _constant(name: str) -> float:
    """Reject the ``NaN``, ``Infinity`` and ``-Infinity`` extensions of Python."""
    raise IMGWDataError(message("content.disallowed_constant_json_document", name=name))


def _double(literal: str) -> float:
    """A JSON number as an IEEE 754 double, like ``JSON.parse``."""
    value = float(literal)
    if not math.isfinite(value):
        raise IMGWDataError(
            message("content.number_outside_ieee_754_double", literal=literal[:32])
        )
    return value


def _serialize(value: object) -> str:
    """RFC 8785 (JCS) text of a parsed value (strings, doubles, lists, dicts)."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, str):
        # ensure_ascii=False escapes exactly as JCS: \" \\ \b \f \n \r \t and
        # other U+0000-U+001F as lowercase \u00xx; everything else is literal.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return (
            "{"
            + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{_serialize(value[key])}"
                for key in keys
            )
            + "}"
        )
    raise TypeError(f"a value outside the JSON model: {type(value).__name__}")


def _number(value: float) -> str:
    """
    ECMAScript ``Number.prototype.toString`` of a finite double (RFC 8785).

    The digits are the shortest round-trip digits of ``repr``; the notation
    follows ECMA-262 Number::toString: integers up to 21 digits, decimals down
    to ``1e-6``, exponential notation otherwise, and ``-0`` written as ``0``.
    """
    if value == 0:
        return "0"
    if value < 0:
        return "-" + _number(-value)
    mantissa, _, exponent = repr(value).partition("e")
    whole, _, fraction = mantissa.partition(".")
    raw = whole + fraction
    significant = raw.lstrip("0")
    # n of ECMA-262: value = 0.<digits> x 10^n.
    point = len(whole) + int(exponent or "0") - (len(raw) - len(significant))
    digits = significant.rstrip("0")
    count = len(digits)
    if count <= point <= 21:
        return digits + "0" * (point - count)
    if 0 < point <= 21:
        return f"{digits[:point]}.{digits[point:]}"
    if -6 < point <= 0:
        return f"0.{'0' * -point}{digits}"
    power = point - 1
    sign = "+" if power >= 0 else "-"
    head = digits if count == 1 else f"{digits[0]}.{digits[1:]}"
    return f"{head}e{sign}{abs(power)}"
