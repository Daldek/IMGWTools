"""
The ``obserwator-error/1`` document: an error as data (AGI-4.3).

`error_document` is the one builder of the document the CLI writes as its last
stderr line and the MCP server answers with ``isError``: the registry ``code``
with its ``title``, the ``message`` (the ``detail`` of the error), a one-line
``hint`` naming the option or command that fixes it (left out when there is
none), the ``details``, the ``exit_code`` of the registry and the catalog
``command`` when known. `error_report` builds it from an exception and
`error_hint` gives the hint alone (REST adds it to problem+json, AGI-6.3).

The hint is the one given by the raise site (``ObserwatorError(hint=...)``),
else the catalog text of ``details.reason``, else that of the code: an invalid
value with ``details.allowed`` names the option and its values, ``not_found``
names ``store scan``, ``source_unavailable`` says to retry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from obserwator.exceptions import ERROR_CODES, ErrorCode, ObserwatorError
from obserwator.messages import DEFAULT_LANG, Lang, localize, message

__all__ = [
    "ERROR_SCHEMA",
    "ErrorReport",
    "error_document",
    "error_hint",
    "error_report",
    "option_flag",
]

ERROR_SCHEMA = "obserwator-error/1"
"""``schema`` of the error document."""

_ALLOWED_SHOWN = 12
"""Most values of ``details.allowed`` a hint lists; more are left to ``details``."""

# Hint of a ``details.reason`` without placeholders.
_REASON_HINTS = {
    "output_exists": "errors.hint_output_exists",
    "output_in_store": "errors.hint_output_in_store",
    "nested_store": "errors.hint_nested_store",
    "not_empty": "errors.hint_not_empty",
    "no_marker": "errors.hint_no_marker",
    "not_in_store": "errors.hint_not_in_store",
    "writes_disabled": "errors.hint_writes_disabled",
    "no_allowed_dir": "errors.hint_allow_dir",
    "outside_allowed_dirs": "errors.hint_allow_dir",
}

# Hint of a code without a hint of its reason.
_CODE_HINTS: dict[ErrorCode, str] = {
    "not_found": "errors.hint_not_found",
    "source_unavailable": "errors.hint_source_unavailable",
}


@dataclass(frozen=True)
class ErrorReport:
    """
    The error document ``obserwator-error/1`` (AGI-4.3).

    Attributes
    ----------
    code : ErrorCode
        Registry code.
    title : str
        Registry title.
    message : str
        What happened.
    details : Mapping[str, object]
        JSON-compatible context: ``reason``, ``option``, ``value``,
        ``allowed``, ``path``, ``paths``, ...
    exit_code : int or None
        Exit code of the registry; ``None`` for a REST-only code.
    hint : str or None
        One line saying how to fix it; ``None`` when there is no hint.
    command : str or None
        Catalog command name, when known.
    """

    code: ErrorCode
    title: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)
    exit_code: int | None = None
    hint: str | None = None
    command: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the document; ``hint`` and ``command`` are left out when ``None``."""
        document: dict[str, object] = {
            "schema": ERROR_SCHEMA,
            "code": self.code,
            "title": self.title,
            "message": self.message,
        }
        if self.hint is not None:
            document["hint"] = self.hint
        document["details"] = dict(self.details)
        document["exit_code"] = self.exit_code
        if self.command is not None:
            document["command"] = self.command
        return document

    def to_json(self) -> str:
        """Return the document as compact JSON (one line, UTF-8 text)."""
        return json.dumps(
            self.to_dict(), ensure_ascii=False, separators=(",", ":"), default=str
        )


def option_flag(option: str) -> str:
    """
    CLI flag of a catalog option (``output_dir`` → ``--output-dir``).

    A name that is no catalog option (an environment variable such as
    ``OBSERWATOR_LANG``) stays as it is.
    """
    if not option.isidentifier() or option != option.lower():
        return option
    return "--" + option.replace("_", "-")


def _derived(code: ErrorCode, details: Mapping[str, object]) -> str | None:
    """The catalog hint of ``details.reason`` or of ``code``; None when none fits."""
    reason = details.get("reason")
    option = details.get("option")
    options = details.get("options")
    if isinstance(reason, str) and reason in _REASON_HINTS:
        return message(_REASON_HINTS[reason])
    if reason == "exclusive_options" and isinstance(options, list):
        return message(
            "errors.hint_exclusive_options",
            flags=", ".join(option_flag(str(name)) for name in options),
        )
    if reason == "store_only_option" and isinstance(option, str):
        return message("errors.hint_store_only_option", flag=option_flag(option))
    allowed = details.get("allowed")
    if (
        code == "validation_error"
        and isinstance(option, str)
        and "value" in details
        and isinstance(allowed, list)
        and allowed
    ):
        flag = option_flag(option)
        if len(allowed) > _ALLOWED_SHOWN:
            return message("errors.hint_allowed_many", flag=flag)
        return message(
            "errors.hint_allowed",
            flag=flag,
            allowed=", ".join(str(value) for value in allowed),
        )
    key = _CODE_HINTS.get(code)
    return message(key) if key else None


def error_hint(
    code: ErrorCode, details: Mapping[str, object], hint: str | None = None
) -> str | None:
    """
    Return the hint of an error.

    Parameters
    ----------
    code : ErrorCode
        Registry code.
    details : Mapping[str, object]
        Context of the error.
    hint : str or None, optional
        Hint of the raise site; it wins over the derived one.

    Returns
    -------
    str or None
        ``hint``, else the catalog text of ``details.reason``, else that of
        ``code``; ``None`` when no hint fits. A catalog text is a
        `obserwator.messages.Message` (English; `localize` renders it in the
        language of the channel).
    """
    return hint or _derived(code, details)


def error_document(
    code: ErrorCode,
    text: str,
    details: Mapping[str, object] | None = None,
    *,
    hint: str | None = None,
    command: str | None = None,
    lang: Lang = DEFAULT_LANG,
) -> ErrorReport:
    """
    Build the error document of one error.

    Parameters
    ----------
    code : ErrorCode
        Registry code; gives ``title`` and ``exit_code``.
    text : str
        What happened (``message``); the title when empty.
    details : Mapping[str, object] or None, optional
        Context of the error.
    hint : str or None, optional
        Hint of the raise site; ``None`` derives one (`error_hint`).
    command : str or None, optional
        Catalog command name, when known.
    lang : {"en", "pl"}, optional
        Language of ``title``, ``message`` and ``hint``: English for the CLI
        and MCP (AGI-9.2).

    Returns
    -------
    ErrorReport
        The document.
    """
    spec = ERROR_CODES[code]
    context = dict(details or {})
    title = localize(spec.title, lang)
    chosen = error_hint(code, context, hint)
    return ErrorReport(
        code=code,
        title=title,
        message=localize(text, lang) or title,
        details=context,
        exit_code=spec.exit_code,
        hint=localize(chosen, lang) if chosen else None,
        command=command,
    )


def error_report(
    exc: ObserwatorError, /, *, command: str | None = None, lang: Lang = DEFAULT_LANG
) -> ErrorReport:
    """
    Build the error document of an `ObserwatorError`.

    Parameters
    ----------
    exc : ObserwatorError
        The error: its ``code``, ``detail`` (``message``), ``details`` and ``hint``.
    command : str or None, optional
        Catalog command name, when known.
    lang : {"en", "pl"}, optional
        Language of the texts.

    Returns
    -------
    ErrorReport
        The document.
    """
    return error_document(
        exc.code, exc.detail, exc.details, hint=exc.hint, command=command, lang=lang
    )
