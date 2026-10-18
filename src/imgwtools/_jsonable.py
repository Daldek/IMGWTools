"""
Single JSON conversion of public results for the CLI, REST and ``CommandResult``.

Rules (spec §13.1 p. 4): dates as ``YYYY-MM-DD``, instants as ISO 8601 UTC with
``Z``, tuples, lists and sets as arrays, dataclasses and pydantic models as
objects of their fields, paths inside the store as POSIX paths relative to the
root, other paths as absolute paths. The root itself is absolute, or ``"."`` in
server mode, where the root prefix is also removed from free text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from os import PathLike
from pathlib import Path, PurePath

from pydantic import BaseModel

__all__ = ["jsonable"]


def jsonable(
    value: object,
    *,
    root: str | PathLike[str] | None = None,
    server: bool = False,
) -> object:
    """
    Convert a public value to plain JSON-compatible values.

    Parameters
    ----------
    value : object
        Result, dataclass, pydantic model, mapping, sequence or scalar.
    root : str or os.PathLike or None, optional
        Store root; paths below it become POSIX paths relative to it. Without a
        root every path is written as an absolute path.
    server : bool, optional
        REST mode: the root itself is written as ``"."`` and the root prefix is
        removed from every text (``<root>/x`` → ``x``, bare ``<root>`` → ``.``).

    Returns
    -------
    object
        Value built only from ``dict``, ``list``, ``str``, ``int``, ``float``,
        ``bool`` and ``None``.

    Raises
    ------
    TypeError
        If the value contains an object without a JSON representation.
    """
    base = None if root is None else Path(root).absolute()
    roots = () if base is None else tuple(dict.fromkeys((base, base.resolve())))
    pattern = _prefix_pattern(roots) if server else None
    return _convert(value, roots, server, pattern)


def _prefix_pattern(roots: tuple[Path, ...]) -> re.Pattern[str] | None:
    prefixes = sorted(
        {str(path) for path in roots if path.parent != path}, key=len, reverse=True
    )
    if not prefixes:
        return None
    alternatives = "|".join(re.escape(prefix) for prefix in prefixes)
    return re.compile(rf"(?:{alternatives})(?:[/\\]|(?![^\s'\"),:;]))")


def _convert(
    value: object,
    roots: tuple[Path, ...],
    server: bool,
    pattern: re.Pattern[str] | None,
) -> object:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if pattern is None:
            return value
        return pattern.sub(lambda m: "" if m.group()[-1] in "/\\" else ".", value)
    if isinstance(value, Enum):
        return _convert(value.value, roots, server, pattern)
    if isinstance(value, PurePath):
        return _path(Path(value), roots, server)
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return _convert(dict(value), roots, server, pattern)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _convert(getattr(value, item.name), roots, server, pattern)
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            _key(key, roots, server, pattern): _convert(item, roots, server, pattern)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [_convert(item, roots, server, pattern) for item in value]
    if isinstance(value, set | frozenset):
        items = [_convert(item, roots, server, pattern) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    raise TypeError(f"Wartości typu {type(value).__name__} nie można zapisać w JSON")


def _key(
    key: object,
    roots: tuple[Path, ...],
    server: bool,
    pattern: re.Pattern[str] | None,
) -> str:
    converted = _convert(key, roots, server, pattern)
    return converted if isinstance(converted, str) else json.dumps(converted)


def _path(path: Path, roots: tuple[Path, ...], server: bool) -> str:
    absolute = path.absolute()
    for root in roots:
        if absolute == root:
            return "." if server else str(absolute)
        if absolute.is_relative_to(root):
            return absolute.relative_to(root).as_posix()
    return str(absolute)
