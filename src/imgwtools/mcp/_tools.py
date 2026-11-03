"""
MCP tools generated from the command catalog (spec 2026-10-19 §6.3–§6.4).

Every catalog command is one tool (mode ``http``: every command with a REST
route), in catalog order: the name is ``x-imgw.operation_id``, the title ``imgw
<command>``, the description the English catalog description, followed by the
rules and, for a writing command, the sentence of the mode (the server speaks
English only, AGI-9.2). The input schema is the command schema of
`command_schema` without ``$schema``, ``title``, ``description`` (it is the tool
description), ``x-imgw`` and the ``x-imgw-*`` keywords, and without the options
the mode does not offer (``read``: writing options; ``http``: options outside
REST, the others as the REST route takes them); ``required``,
``dependentRequired`` and ``oneOf`` keep only the offered options. A stdio
server makes ``root`` optional (it defaults to the store root), list commands page by
``limit`` (50 by default, at most ``IMGW_API_MAX_LIMIT``), ``lang`` defaults to
``en`` and commands with a check twin take a ``check`` argument, fixed to
``true`` for a writing command of a server without writes. The annotations (all
five on every tool) give the title, whether the schema allows a write
(``readOnlyHint``), whether that write may replace content (``destructiveHint``,
false for a read-only tool), whether repeating a call changes nothing more
(``idempotentHint``) and whether the command reaches a source server
(``openWorldHint``); they are hints for the client, not a safeguard.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

import mcp.types as types

from imgwtools.agent_guide import _PAGE_SIZE
from imgwtools.commands import command_schema, data_commands
from imgwtools.config import settings
from imgwtools.store.types import CommandOption, DataCommand

__all__ = ["MODES", "CatalogTool", "Mode", "catalog_tools"]

Mode = Literal["read", "write", "http"]
MODES: tuple[Mode, ...] = ("read", "write", "http")

_RULES = "Rules:"
# Sentence of a writing command: the server without writes plans, the server
# with writes plans by default (spec 2026-10-19 §6.4).
_NO_WRITES = (
    "The MCP server runs without writes: a call returns the imgw-plan/1 plan (check)."
)
_WRITES = "check=true by default (a plan); writing requires check=false."
_CHECK = "Only the imgw-plan/1 plan, without writing or downloading"
_FIXED_CHECK = f"{_CHECK} (server without writes)"
_SERVER_ROOT = "the MCP server's store"


@dataclass(frozen=True)
class CatalogTool:
    """
    MCP tool of one catalog command and what its calls need.

    Attributes
    ----------
    definition : mcp.types.Tool
        Tool announced by ``tools/list``.
    command : DataCommand
        Catalog command the tool runs.
    mode : {"read", "write", "http"}
        Mode of the server.
    check : bool or None
        Default of the ``check`` argument; None when the tool has none.
    fixed : bool
        Whether ``check`` is fixed to ``true`` (a writing command of a server
        without writes).
    refused : frozenset of str
        Writing options refused with ``forbidden`` (server without writes).
    limit : tuple of (int, int) or None
        Default and maximum ``limit`` of a list command.
    route : tuple of (str, str) or None
        Method and path of the REST route (mode ``http``).
    """

    definition: types.Tool
    command: DataCommand
    mode: Mode
    check: bool | None
    fixed: bool
    refused: frozenset[str]
    limit: tuple[int, int] | None
    route: tuple[str, str] | None


def _plain(value: object) -> Any:
    """``value`` without the ``x-imgw*`` keywords, at any depth (a copy)."""
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return {
            key: _plain(item)
            for key, item in mapping.items()
            if not key.startswith("x-imgw")
        }
    if isinstance(value, list):
        return [_plain(item) for item in cast(list[object], value)]
    return value


def _reduced(group: Sequence[str], dropped: set[str]) -> list[str]:
    return [name for name in group if name not in dropped]


def _alternatives(
    groups: Iterable[Sequence[str]], dropped: set[str]
) -> list[list[str]] | None:
    """``oneOf`` groups without ``dropped``: None when an alternative is empty."""
    result: list[list[str]] = []
    for group in groups:
        names = _reduced(group, dropped)
        if not names:
            return None
        if names not in result:
            result.append(names)
    return result


def _rest_properties(
    spec: DataCommand, schema: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Option schemas of the REST route of ``spec`` (the REST adapter's function)."""
    # REST lives in the api extra, which the http mode runs in.
    from imgwtools.api.routes import commands as rest

    route = next(route for route in rest._ROUTES if route.spec.name == spec.name)
    localized = replace(route, schema=schema)
    return {
        option.name: rest._option_schema(localized, option)
        for option in route.params
        # The MCP page of a list command (below) replaces the REST one.
        if option.name != "limit"
    }


def _root_text(spec: DataCommand) -> str:
    """Note on ``root`` of a stdio server: the default store root."""
    if not spec.env_root_when:
        return f"default: {_SERVER_ROOT}"
    condition = ", ".join(f"{key}={value}" for key, value in spec.env_root_when.items())
    return f"default with {condition}: {_SERVER_ROOT}"


def _check_kind(spec: DataCommand, mode: Mode) -> tuple[bool | None, bool]:
    """Default of the ``check`` argument (None: no argument) and whether it is fixed."""
    if spec.check is None:
        return None, False
    if mode == "http":
        # REST plans only on POST (?check=true), where every route writes.
        return (True, True) if spec.method == "POST" else (None, False)
    if spec.writes == "none":
        return False, False
    return True, mode == "read"


def _tool(
    spec: DataCommand,
    schema: Mapping[str, Any],
    *,
    mode: Mode,
) -> CatalogTool:
    meta = schema["x-imgw"]
    catalog = cast(Mapping[str, Mapping[str, Any]], schema["properties"])
    offered: list[CommandOption] = []
    refused: set[str] = set()
    for option in spec.options:
        if mode == "http" and option.rest != "param":
            continue
        if mode == "read" and option.writes != "none":
            refused.add(option.name)
            continue
        offered.append(option)
    rest = _rest_properties(spec, schema) if mode == "http" else {}
    properties: dict[str, dict[str, Any]] = {
        option.name: _plain(rest.get(option.name) or catalog[option.name])
        for option in offered
    }
    dropped = {option.name for option in spec.options} - set(properties)

    if mode != "http" and "root" in properties:
        description = properties["root"]["description"]
        properties["root"]["description"] = f"{description}; {_root_text(spec)}"
        dropped.add("root")  # given by the server when absent (spec §3.5)
    limit: tuple[int, int] | None = None
    if spec.result == "list":
        maximum = settings.api_max_limit
        limit = (min(_PAGE_SIZE, maximum), maximum)
        properties["limit"].update(default=limit[0], maximum=maximum)
    check, fixed = _check_kind(spec, mode)
    if check is not None:
        properties["check"] = (
            {"const": True, "default": True, "description": _FIXED_CHECK}
            if fixed
            else {"type": "boolean", "default": check, "description": _CHECK}
        )

    input_schema: dict[str, Any] = {"type": "object", "properties": properties}
    required = _reduced(cast(list[str], schema.get("required", [])), dropped)
    if required:
        input_schema["required"] = required
    dependent = {
        key: names
        for key, group in cast(
            Mapping[str, list[str]], schema.get("dependentRequired", {})
        ).items()
        if key in properties and (names := _reduced(group, dropped))
    }
    if dependent:
        input_schema["dependentRequired"] = dependent
    groups = [
        cast(list[str], item["required"])
        for item in cast(list[Mapping[str, Any]], schema.get("oneOf", []))
    ]
    alternatives = _alternatives(groups, dropped) if groups else None
    if alternatives:
        input_schema["oneOf"] = [{"required": names} for names in alternatives]
    input_schema["additionalProperties"] = False

    writing = [option for option in offered if option.writes != "none"]
    writable = (spec.writes != "none" and not fixed) or bool(writing)
    destructive = spec.writes == "replace" or any(
        option.writes == "replace" for option in writing
    )
    lines = [cast(str, schema["description"])]
    rules = cast(list[str], meta["rules"])
    if rules:
        lines.append("\n".join([_RULES, *(f"- {rule}" for rule in rules)]))
    if spec.writes != "none":
        lines.append(_NO_WRITES if fixed else _WRITES)
    title = f"imgw {spec.name}"
    definition = types.Tool(
        name=cast(str, meta["operation_id"]),
        title=title,
        description="\n\n".join(lines),
        input_schema=input_schema,
        annotations=types.ToolAnnotations(
            title=title,
            read_only_hint=not writable,
            destructive_hint=writable and destructive,
            idempotent_hint=spec.idempotent,
            open_world_hint=spec.network,
        ),
        _meta={"imgwtools/command": spec.name},
    )
    route = meta["rest"]
    return CatalogTool(
        definition=definition,
        command=spec,
        mode=mode,
        check=check,
        fixed=fixed,
        refused=frozenset(refused),
        limit=limit,
        route=None if mode != "http" else (route["method"], route["path"]),
    )


def catalog_tools(*, mode: Mode) -> dict[str, CatalogTool]:
    """
    Build the tools of a server mode from the command catalog.

    Parameters
    ----------
    mode : {"read", "write", "http"}
        ``read``: every command, writing ones only planning (``check`` fixed
        to ``true``) and without writing options; ``write``: every command,
        writing ones planning by default; ``http``: the commands with a REST
        route, with their REST options, POST routes only planning.

    Returns
    -------
    dict of {str : CatalogTool}
        Tools by name, in catalog order.
    """
    specs = {spec.name: spec for spec in data_commands()}
    document = command_schema(lang="en")
    tools: dict[str, CatalogTool] = {}
    for schema in cast(list[dict[str, Any]], document["commands"]):
        meta = schema["x-imgw"]
        if mode == "http" and meta["rest"] is None:
            continue
        tool = _tool(specs[meta["command"]], schema, mode=mode)
        tools[tool.definition.name] = tool
    return tools
