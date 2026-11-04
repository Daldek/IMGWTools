"""
The human rendering of a command result: ``obserwator`` without ``--json`` (AGI-3.2).

`render` turns the JSON form of the ``obserwator-result/1`` envelope into a few
lines for a person, in the language of the call: the status with the command,
the result (the items of a list as a table of their key fields and the
``page`` line; the main fields of a document, its lists of items as tables,
work items with an error first), then the notices. One renderer serves every
command: the key fields are the first scalar fields of an item; `_COLUMNS` and
`_FIELDS` name them only where those are not the telling ones. Field names
stay the names of the document; the status, page, notice and yes/no words are
catalog messages (``obserwator.messages.cli``).
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, cast

from obserwator.messages import Lang, localize, message
from obserwator.store.types import Notice

__all__ = ["render"]

# Columns of the items of a list: by the item's ``schema``, else by the field
# holding the items. Only the columns some item has are shown.
_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "obserwator-dataset/1": ("key", "kind", "provider", "first_year", "title"),
    "obserwator-archive-file/1": ("server_path", "year", "month", "station_code"),
    "obserwator-station/1": ("station_code", "name", "river", "kind", "provider"),
    "obserwator-hydro-current/1": (
        "station_code",
        "station_name",
        "river",
        "water_level_cm",
        "water_level_date",
    ),
    "obserwator-meteo-current/1": (
        "station_code",
        "station_name",
        "air_temp_c",
        "air_temp_date",
    ),
    "obserwator-hydro-state/1": ("station_code", "name", "river", "water_state"),
    "obserwator-record/1": ("station_code", "date", "measurements"),
    "obserwator-coverage/1": (
        "station_code",
        "variable",
        "unit",
        "first",
        "last",
        "with_value",
    ),
    "commands": ("name", "summary"),
    "groups": ("name", "summary"),
    "options": ("flags", "type", "required", "default", "description"),
    "items": ("slot", "server_path", "station_code", "status", "error_code", "error"),
    "actions": ("command", "status", "detail"),
    "files": ("path", "status", "size_bytes"),
    "providers": ("id", "country", "name"),
    "examples": ("call",),
}
# Main fields of a document, by its ``schema``; any other document shows all.
_FIELDS: Mapping[str, tuple[str, ...]] = {
    "obserwator-command-list/1": ("groups", "commands"),
    "obserwator-commands/1": ("commands",),
    "obserwator-store-info/1": (
        "root",
        "exists",
        "supported",
        "store_schema",
        "problems",
        "providers",
    ),
}
# Lists of a document whose items are shown as documents, not as table rows.
_EXPANDED: frozenset[tuple[str, str]] = frozenset(
    {("obserwator-commands/1", "commands")}
)
_AUTO_COLUMNS = 5
_CELL_WIDTH = 100
_LIST_ROWS = 10  # rows of a list of work items (with a status) or of texts
_INDENT = "  "
_STATUSES: Mapping[str, str] = {
    "ok": "cli.human_status_ok",
    "partial": "cli.human_status_partial",
    "failed": "cli.human_status_failed",
    "cancelled": "cli.human_status_cancelled",
}
_LEVELS: Mapping[str, str] = {
    "info": "cli.level_info",
    "warning": "cli.level_warning",
}


def render(envelope: Mapping[str, Any], notices: Sequence[Notice], lang: Lang) -> str:
    """
    Render the envelope of a command for a person.

    Parameters
    ----------
    envelope : Mapping[str, Any]
        The JSON form of the ``obserwator-result/1`` envelope (`CommandResult.to_json`).
    notices : Sequence of Notice
        Its notices, whose messages are rendered in ``lang``.
    lang : {"en", "pl"}
        Language of the words of the rendering.

    Returns
    -------
    str
        The lines, without a trailing line end.
    """
    words = ["obserwator", envelope["command"]]
    if envelope.get("check"):
        words.append("--check")
    status = message(_STATUSES[envelope["status"]], lang=lang)
    lines = [f"{status}: {' '.join(words)}"]
    result = envelope.get("result")
    if isinstance(result, list):
        lines += _list(result, None, lang, "")
        page = envelope.get("page")
        if page is not None:
            lines.append(_page(len(result), page, lang))
    elif isinstance(result, Mapping):
        lines += _document(cast(Mapping[str, Any], result), lang, "")
    elif result is not None:
        lines.append(_cell(result, lang))
    for notice in notices:
        label = message(_LEVELS[notice.level], lang=lang)
        lines.append(f"{label}: {localize(notice.message, lang)}")
    return "\n".join(lines)


def _page(shown: int, page: Mapping[str, Any], lang: Lang) -> str:
    cursor = page.get("next_cursor")
    if page.get("truncated") and cursor:
        return message(
            "cli.human_page_more",
            lang=lang,
            shown=shown,
            total=page.get("total"),
            cursor=cursor,
        )
    return message("cli.human_page", lang=lang, shown=shown, total=page.get("total"))


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _cell(value: object, lang: Lang, width: int | None = None) -> str:
    """
    One value as one line of text, cut to ``width`` characters when given.

    A measurement (a mapping with ``value``) is its value, a mapping of plain
    values ``key=value`` pairs (of other values its keys), a list its values
    joined (a pair inside a list a range ``a–b``; mappings their count).
    """
    if value is None:
        text = "—"
    elif isinstance(value, bool):
        text = message("cli.human_yes" if value else "cli.human_no", lang=lang)
    elif isinstance(value, Mapping):
        mapping = cast(Mapping[str, Any], value)
        if "value" in mapping:
            return _cell(mapping["value"], lang, width)
        if all(_plain(item) for item in mapping.values()):
            text = ", ".join(
                f"{key}={_inner(item, lang)}" for key, item in mapping.items()
            )
        else:
            text = ", ".join(mapping)
    elif isinstance(value, list):
        items = value
        if items and isinstance(items[0], Mapping):
            text = f"[{len(items)}]"
        else:
            text = ", ".join(
                "–".join(_cell(part, lang) for part in item)
                if isinstance(item, list)
                else _cell(item, lang)
                for item in items
            )
    else:
        text = str(value)
    text = " ".join(text.split()) or "—"
    if width is None or len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _plain(value: object) -> bool:
    """A value of a ``key=value`` pair: plain, a measurement or a list of plain values."""
    if isinstance(value, Mapping):
        return "value" in value
    if isinstance(value, list):
        return all(_is_scalar(item) for item in value)
    return _is_scalar(value)


def _inner(value: object, lang: Lang) -> str:
    """The value of a ``key=value`` pair; a list in brackets."""
    text = _cell(value, lang)
    return f"[{text}]" if isinstance(value, list) and value else text


def _columns(rows: Sequence[Mapping[str, Any]], field: str | None) -> list[str]:
    """The key fields of ``rows``: those of their hint, else the first scalar fields."""
    schema = rows[0].get("schema")
    hint = _COLUMNS.get(schema) if isinstance(schema, str) else None
    if hint is None and field is not None:
        hint = _COLUMNS.get(field)
    if hint is not None:
        chosen = [name for name in hint if any(name in row for row in rows)]
        if chosen:
            return chosen
    names = [
        name
        for name, value in rows[0].items()
        if name != "schema" and _is_scalar(value)
    ][:_AUTO_COLUMNS]
    return names + [
        name
        for name in ("status", "error_code")
        if name in rows[0] and name not in names
    ]


def _table(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str], lang: Lang
) -> list[str]:
    """Rows of aligned cells under a header; only the last column is never cut."""
    last = len(columns) - 1
    cells = [list(columns)] + [
        [
            _cell(row.get(name), lang, None if index == last else _CELL_WIDTH)
            for index, name in enumerate(columns)
        ]
        for row in rows
    ]
    widths = [max(len(line[index]) for line in cells) for index in range(len(columns))]
    return [
        "  ".join(
            text.ljust(width) for text, width in zip(line, widths, strict=True)
        ).rstrip()
        for line in cells
    ]


def _failing(row: Mapping[str, Any]) -> bool:
    return bool(row.get("error_code") or row.get("error"))


def _list(
    items: Sequence[Any], field: str | None, lang: Lang, indent: str
) -> list[str]:
    """
    The lines of a list: a table of mappings, else one value per line.

    A nested list of work items (with a ``status``) or of texts shows its
    first `_LIST_ROWS` rows, work items with an error first; a top-level list
    (a page) shows every item.
    """
    if not items:
        return [indent + message("cli.human_no_items", lang=lang)]
    limit = None if field is None else _LIST_ROWS
    if isinstance(items[0], Mapping):
        rows = cast(Sequence[Mapping[str, Any]], items)
        if field is None or "status" not in rows[0]:
            limit = None
        else:
            rows = sorted(rows, key=lambda row: not _failing(row))
        lines = _table(rows[:limit], _columns(rows, field), lang)
    else:
        lines = [f"- {_cell(item, lang)}" for item in items[:limit]]
    if limit is not None and len(items) > limit:
        lines.append(
            message("cli.human_more_rows", lang=lang, count=len(items) - limit)
        )
    return [indent + line for line in lines]


def _breakdown(rows: Sequence[Any]) -> str:
    """``(new 2, failed 1)`` of work items with a status; empty for other lists."""
    if not rows or not all(
        isinstance(row, Mapping) and "status" in row for row in rows
    ):
        return ""
    counts = Counter(str(row["status"]) for row in rows)
    return (
        " (" + ", ".join(f"{status} {count}" for status, count in counts.items()) + ")"
    )


def _document(document: Mapping[str, Any], lang: Lang, indent: str) -> list[str]:
    """
    The main fields of a document, one per line.

    A list of mappings becomes a table below its name (the items of an
    `_EXPANDED` list: their fields, indented), a list of long texts one text
    per line; anything else is one line ``name: value``.
    """
    schema = document.get("schema")
    names = _FIELDS.get(schema) if isinstance(schema, str) else None
    shown = [
        name
        for name in (names if names is not None else document)
        if name in document and name != "schema"
    ]
    width = max((len(name) for name in shown), default=0) + 1
    lines: list[str] = []
    for name in shown:
        value = document[name]
        if isinstance(value, list) and value:
            items = value
            if isinstance(items[0], Mapping):
                lines.append(f"{indent}{name}: {len(items)}{_breakdown(items)}")
                if (schema, name) in _EXPANDED:
                    for item in items:
                        lines += _document(item, lang, indent + _INDENT)
                else:
                    lines += _list(items, name, lang, indent + _INDENT)
                continue
            if len(_cell(items, lang)) > _CELL_WIDTH // 2 or len(items) > _LIST_ROWS:
                lines.append(f"{indent}{name}: {len(items)}")
                lines += _list(items, name, lang, indent + _INDENT)
                continue
        lines.append(f"{indent}{(name + ':').ljust(width)} {_cell(value, lang)}")
    return lines
