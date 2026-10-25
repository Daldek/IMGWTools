"""
Guide for AI agents generated from the command catalog (spec 2026-10-19 §5).

`agent_guide` renders ``AGENTS.md`` (``format="agents"``) and ``llms.txt``
(``format="llms"``), in English (the default) or Polish, from the hand-written
templates in ``imgwtools/_data/agents``. Every marker ``<!-- imgw:<block> -->``
of a template is replaced by a block generated from the command catalog
(`command_schema`, `data_commands`), the registries (`providers`,
`datasets` and the error codes of the catalog document) and the data of this
module: the rules shared with the MCP server instructions, the meaning of the
envelope statuses and the typical flows, whose commands `format_command`
renders. The words of the blocks are messages of
``imgwtools.messages.agent_guide``. A marker filling a whole line takes a block
of any number of lines, a marker inside a line a one-line block; an unknown
block or a block used twice is a program error. The output depends only on the
installed package (no dates, no local paths), so ``AGENTS.md`` and ``llms.txt``
of the repository (the English guide) are derived files that the tests compare
byte for byte with the generator.

`_instructions` gives the MCP server its ``instructions``: the rules and the
lines of the server mode.
"""

import os
import re
import shlex
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, cast, overload

from imgwtools._version import __version__
from imgwtools.commands import (
    command_schema,
    data_commands,
    format_command,
    list_commands,
    validate_command,
)
from imgwtools.datasets import datasets, providers
from imgwtools.messages import Lang, message
from imgwtools.output import OutputReport
from imgwtools.store.export import _deliver, _Lines, _target
from imgwtools.store.types import PathArg

__all__ = ["GuideFormat", "agent_guide"]

GuideFormat = Literal["agents", "llms"]
# Modes of the MCP server (spec 2026-10-19 §6.3).
McpMode = Literal["read", "write", "http"]

# Default page size of the list tools of the MCP server (spec 2026-10-19 §6.4).
_PAGE_SIZE = 50
_MARKER = re.compile(r"<!--\s*imgw:(?P<name>[^\s>]*)\s*-->")
# A comma-separated run of three or more years, or the same as a JSON array.
_YEAR_RUN = re.compile(
    r"\[\d{4}(?:,\d{4}){2,}\]|(?<![\d.-])\d{4}(?:,\d{4}){2,}(?![\d.-])"
)
# Statistics of the hydrological variables (``H_min``, ``H_mean``, ``H_max``).
_STATISTICS = ("min", "mean", "max")
_DASH = "—"
# Messages (imgwtools.messages.agent_guide) of the country names of the provider
# registry.
_COUNTRIES: Mapping[str, str] = {
    "PL": "agent_guide.country_poland",
    "CZ": "agent_guide.country_czechia",
}
# Titles of the command classes by effect of a run.
_EFFECTS: Mapping[str, str] = {
    "read": "agent_guide.effect_read",
    "network": "agent_guide.effect_network",
    "add": "agent_guide.effect_add",
    "replace": "agent_guide.effect_replace",
}
# Marks of an option that writes a file (``x-imgw-writes``) and of a command.
_MARKS: Mapping[str, str] = {
    "add": "agent_guide.mark_add",
    "replace": "agent_guide.mark_replace",
    "itself": "agent_guide.mark_itself",
    "local": "agent_guide.mark_local",
}
_HEADERS: Mapping[str, tuple[str, ...]] = {
    "statuses": (
        "agent_guide.header_status",
        "agent_guide.header_exit_code",
        "agent_guide.header_meaning",
    ),
    "datasets": (
        "agent_guide.header_key",
        "agent_guide.header_variables",
        "agent_guide.header_first_year",
    ),
}
# Meaning of each envelope status (spec 2026-10-17 §13.6).
_STATUSES: Mapping[str, str] = {
    "ok": "agent_guide.status_ok",
    "partial": "agent_guide.status_partial",
    "failed": "agent_guide.status_failed",
    "cancelled": "agent_guide.status_cancelled",
}
# The rules of AGENTS.md, llms.txt and the MCP instructions (spec 2026-10-19 §5.4).
_PRINCIPLES: tuple[str, ...] = (
    "agent_guide.rule_learn_commands",
    "agent_guide.rule_check_first",
    "agent_guide.rule_run",
    "agent_guide.rule_read_offline",
    "agent_guide.rule_decide_by_codes",
)


@dataclass(frozen=True)
class _Symbol:
    """
    Value found by an earlier step of a flow.

    The guide prints the name of the symbol in its language; `format_command`
    validates the command with ``stand_in`` (an absolute path for ``path``
    symbols) in its place.
    """

    key: str  # message of its name in imgwtools.messages.agent_guide
    stand_in: str
    path: bool = False

    def name(self, lang: Lang) -> str:
        return message(self.key, lang=lang)

    def rendered(self) -> str:
        """Text of the stand-in in a line of `format_command`."""
        if not self.path:
            return self.stand_in
        return shlex.quote(os.fspath(Path(self.stand_in).absolute()))


@dataclass(frozen=True)
class _Step:
    """One step of a flow: a catalog command with a note, or a decision alone."""

    command: str | None
    options: Mapping[str, object]
    note: str  # message in imgwtools.messages.agent_guide
    check: bool = False


@dataclass(frozen=True)
class _Flow:
    """A typical task of an agent as steps rendered by `format_command`."""

    title: str  # message in imgwtools.messages.agent_guide
    steps: tuple[_Step, ...]


_STATION = _Symbol("agent_guide.symbol_station_code", "123456789")
_WIGOS = _Symbol("agent_guide.symbol_wigos_id", "0-203-1-900001")
_PROJECT = _Symbol("agent_guide.symbol_project", "/PROJECT", path=True)
_SYMBOLS = (_STATION, _WIGOS, _PROJECT)
_STORE = "/data/imgw"
_PRECIP = "pl.imgw.meteo_precip_daily"
_CHMI_HYDRO = "cz.chmi.hydro_daily"
_PRECIP_STORE = {"root": _STORE, "datasets": [_PRECIP], "years": "2010-2020"}
_PRECIP_DAYS = {
    "root": _STORE,
    "dataset": _PRECIP,
    "station": _STATION,
    "variables": ["P"],
    "start": "2010-01-01",
    "end": "2020-12-31",
}
_CHMI_STORE = {
    "root": _STORE,
    "datasets": [_CHMI_HYDRO],
    "stations": [_WIGOS],
    "years": "2020-2025",
}
_FLOWS: tuple[_Flow, ...] = (
    _Flow(
        "agent_guide.flow_precipitation_title",
        (
            _Step(
                "stations find",
                {"kind": "meteo", "query": "poznan"},
                "agent_guide.flow_precipitation_find_station",
            ),
            _Step(None, {}, "agent_guide.flow_precipitation_choose_dataset"),
            _Step("store check", _PRECIP_STORE, "agent_guide.flow_precipitation_plan"),
            _Step("store sync", _PRECIP_STORE, "agent_guide.flow_precipitation_sync"),
            _Step(
                "series summary",
                {"root": _STORE, "dataset": _PRECIP, "stations": [_STATION]},
                "agent_guide.flow_precipitation_summary",
            ),
            _Step(
                "series read",
                {**_PRECIP_DAYS, "limit": 500},
                "agent_guide.flow_next_pages",
            ),
        ),
    ),
    _Flow(
        "agent_guide.flow_czech_discharge_title",
        (
            _Step(
                "stations find",
                {"provider": "CHMI", "kind": "hydro", "query": "spindleruv"},
                "agent_guide.flow_czech_discharge_find_station",
            ),
            _Step("store check", _CHMI_STORE, "agent_guide.flow_czech_discharge_plan"),
            _Step("store sync", _CHMI_STORE, "agent_guide.flow_czech_discharge_sync"),
            _Step(
                "series read",
                {
                    "root": _STORE,
                    "dataset": _CHMI_HYDRO,
                    "station": _WIGOS,
                    "variables": ["Q"],
                    "limit": 500,
                },
                "agent_guide.flow_next_pages",
            ),
        ),
    ),
    _Flow(
        "agent_guide.flow_project_title",
        (
            _Step(
                "project init",
                {"project_dir": _PROJECT, "store_dir": "../store"},
                "agent_guide.flow_project_init",
            ),
            _Step(
                "project add",
                {
                    "project_dir": _PROJECT,
                    "name": "precipitation",
                    "command": "series select",
                    "options": {
                        "dataset": _PRECIP,
                        "stations": [_STATION],
                        "years": "2010-2020",
                    },
                },
                "agent_guide.flow_project_add_task",
            ),
            _Step(
                "project download",
                {"project_dir": _PROJECT},
                "agent_guide.flow_project_plan",
                check=True,
            ),
            _Step(
                "project download",
                {"project_dir": _PROJECT},
                "agent_guide.flow_project_download",
            ),
            _Step(
                "project verify",
                {"project_dir": _PROJECT},
                "agent_guide.flow_project_verify",
            ),
        ),
    ),
)
# Lines of the MCP instructions per server mode (spec 2026-10-19 §6.3–§6.4).
_MODES: Mapping[str, str] = {
    "read": (
        "Server mode: no writes — writing commands have `check` fixed to `true` and "
        "return an `imgw-plan/1` plan, writing options are unavailable; the user, "
        "not the agent, enables writes (`imgw mcp --allow-writes`)."
    ),
    "write": (
        "Server mode: writes enabled — writing commands return a plan by default "
        "(`check: true`); writing needs `check: false` after the user agrees."
    ),
    "http": (
        "Server mode: HTTP (REST facade) — reading and planning only (`check` fixed "
        "to `true`); the tools are only the commands with a REST route and their "
        "REST options."
    ),
}


def _code(text: object) -> str:
    return f"`{text}`"


def _code_or_dash(text: object) -> str:
    return _DASH if text is None else _code(text)


def _cell(text: str) -> str:
    """Table cell text: a pipe escaped, no line breaks."""
    return text.replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(_cell(text) for text in header) + " |",
        "|" + "---|" * len(header),
    ]
    lines += ["| " + " | ".join(_cell(text) for text in row) + " |" for row in rows]
    return "\n".join(lines)


def _header(name: str, lang: Lang) -> tuple[str, ...]:
    return tuple(message(key, lang=lang) for key in _HEADERS[name])


# --- blocks ----------------------------------------------------------------------------------


def _summary(document: Mapping[str, Any], lang: Lang) -> str:
    names = ", ".join(
        f"{owner.short_name} — {message(_COUNTRIES[owner.country], lang=lang)}"
        for owner in providers()
    )
    return message(
        "agent_guide.summary",
        lang=lang,
        version=__version__,
        providers=names,
        datasets=len(datasets()),
        commands=len(document["commands"]),
        groups=len(document["groups"]),
    )


def _principles(lang: Lang) -> str:
    return "\n".join(
        f"{number}. {message(key, lang=lang)}"
        for number, key in enumerate(_PRINCIPLES, start=1)
    )


def _providers(lang: Lang) -> str:
    lines = []
    for owner in providers():
        label = (
            _code(owner.id)
            if owner.short_name == owner.id
            else f"{_code(owner.id)} ({owner.short_name})"
        )
        lines.append(
            message(
                "agent_guide.provider_line",
                lang=lang,
                label=label,
                country=message(_COUNTRIES[owner.country], lang=lang),
                keys=_code(f"{owner.key_prefix}.*"),
                station=_code(owner.station_code_pattern),
                license=f"[{owner.license.id}]({owner.license.url})",
            )
        )
    return "\n".join(lines)


def _statuses(document: Mapping[str, Any], lang: Lang) -> str:
    rows = [
        (_code(status), str(code), message(_STATUSES[status], lang=lang))
        for status, code in document["exit_codes"].items()
    ]
    return _table(_header("statuses", lang), rows)


def _errors(document: Mapping[str, Any]) -> str:
    """Every error code with its CLI exit code and HTTP status (``—``: never)."""
    return ", ".join(
        f"{_code(error['code'])} "
        f"({_DASH if error['exit_code'] is None else error['exit_code']}/"
        f"{_DASH if error['http_status'] is None else error['http_status']})"
        for error in document["errors"]
    )


def _variables(variables: Iterable[str]) -> str:
    """Variable names as code; ``X_min``, ``X_mean`` and ``X_max`` fold into braces."""
    names = tuple(variables)
    if not names:
        return _DASH
    step = len(_STATISTICS)
    bases = tuple(name.rpartition("_")[0] for name in names[::step])
    if len(names) > step and names == tuple(
        f"{base}_{statistic}" for base in bases for statistic in _STATISTICS
    ):
        return _code(f"{{{','.join(bases)}}}_{{{','.join(_STATISTICS)}}}")
    return ", ".join(_code(name) for name in names)


def _datasets(lang: Lang) -> str:
    """The datasets of the store as a table and the others as a line of keys."""
    rows = [
        (
            _code(descriptor.key),
            _variables(descriptor.variables),
            _DASH if descriptor.first_year is None else str(descriptor.first_year),
        )
        for descriptor in datasets()
        if descriptor.in_store
    ]
    outside = ", ".join(
        _code(descriptor.key) for descriptor in datasets() if not descriptor.in_store
    )
    outside_store = message("agent_guide.outside_store", lang=lang)
    return f"{_table(_header('datasets', lang), rows)}\n\n{outside_store} {outside}."


def _notes(schema: Mapping[str, Any], lang: Lang) -> str:
    """Bracketed marks of a command: options writing a file, a check, no REST route."""
    meta = schema["x-imgw"]
    marks = [
        f"{_code(name)}: {message(_MARKS[prop['x-imgw-writes']], lang=lang)}"
        for name, prop in schema["properties"].items()
        if "x-imgw-writes" in prop
    ]
    if meta["check"] is None and meta["function"].startswith("check_"):
        marks.append(message(_MARKS["itself"], lang=lang))
    if meta["rest"] is None:
        marks.append(message(_MARKS["local"], lang=lang))
    return f" [{'; '.join(marks)}]" if marks else ""


def _commands(
    document: Mapping[str, Any], summaries: Mapping[str, str], lang: Lang
) -> str:
    """Commands by effect of a run (``read``, ``network``, ``add``, ``replace``)."""
    classes: dict[str, list[str]] = {name: [] for name in _EFFECTS}
    for schema in document["commands"]:
        meta = schema["x-imgw"]
        effect = meta["writes"] if meta["writes"] != "none" else "network"
        if effect == "network" and not meta["network"]:
            effect = "read"
        classes[effect].append(
            f"- {_code(meta['command'])} — {summaries[meta['command']]}"
            f"{_notes(schema, lang)}"
        )
    return "\n\n".join(
        f"**{message(_EFFECTS[name], lang=lang)}**\n\n" + "\n".join(lines)
        for name, lines in classes.items()
    )


def _listed(flags: Iterable[str]) -> str:
    return ", ".join(_code(flag) for flag in sorted(set(flags)))


def _flags(document: Mapping[str, Any], lang: Lang) -> str:
    """The value syntax of the flags of the catalog and the environment variables."""
    kinds: dict[str, set[str]] = {
        key: set() for key in ("list", "year", "toggle", "switch", "date")
    }
    for schema in document["commands"]:
        for name, flags in schema["x-imgw"]["cli"]["flags"].items():
            canonical, *others = flags
            prop = schema["properties"][name]
            negative = f"--no-{canonical[2:]}"
            kind = prop.get("type")
            if kind == "array":
                kinds["list"].add(canonical)
                if "anyOf" in prop["items"]:
                    kinds["year"].add(canonical)
            elif kind == "boolean":
                kinds["toggle" if negative in others else "switch"].add(canonical)
            elif prop.get("format") == "date":
                kinds["date"].add(canonical)
    toggles = ", ".join(f"`{flag}/--no-{flag[2:]}`" for flag in sorted(kinds["toggle"]))
    roots = "; ".join(
        message(
            "agent_guide.flags_root_when",
            lang=lang,
            command=_code(spec.name),
            conditions=", ".join(
                _code(f"{name}={value}") for name, value in spec.env_root_when.items()
            ),
        )
        for spec in data_commands()
        if spec.env_root_when
    )
    lines = [
        message(
            "agent_guide.flags_lists",
            lang=lang,
            lists=_listed(kinds["list"]),
            years=_listed(kinds["year"]),
            dates=_listed(kinds["date"]),
        ),
        message(
            "agent_guide.flags_switches",
            lang=lang,
            toggles=toggles,
            switches=_listed(kinds["switch"]),
        ),
        message("agent_guide.flags_environment", lang=lang, roots=roots),
    ]
    return "\n".join(lines)


def _substituted(value: object, stand_in: Callable[[_Symbol], object]) -> object:
    """``value`` with every symbol, also in lists and mappings, replaced."""
    if isinstance(value, _Symbol):
        return stand_in(value)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return {key: _substituted(item, stand_in) for key, item in mapping.items()}
    if isinstance(value, list | tuple):
        return [_substituted(item, stand_in) for item in cast(Iterable[object], value)]
    return value


def _year_range(match: re.Match[str]) -> str:
    """A run of consecutive years as ``first-last``; other runs stay as they are."""
    years = [int(year) for year in re.findall(r"\d{4}", match[0])]
    if any(
        later != earlier + 1 for earlier, later in zip(years, years[1:], strict=False)
    ):
        return match[0]
    quote = '"' if match[0].startswith("[") else ""
    return f"{quote}{years[0]}-{years[-1]}{quote}"


def _command_line(step: _Step, lang: Lang) -> str:
    """The ``imgw`` line of a step: `format_command` with the symbols put back."""
    options = cast(
        Mapping[str, object], _substituted(step.options, lambda s: s.stand_in)
    )
    run = {"check": True} if step.check else None
    line = format_command(cast(str, step.command), options=options, run=run)
    line = _YEAR_RUN.sub(_year_range, line)
    for symbol in _SYMBOLS:
        line = line.replace(symbol.rendered(), symbol.name(lang))
    return line


def _flows(lang: Lang) -> str:
    sections = []
    for number, flow in enumerate(_FLOWS, start=1):
        title = message(flow.title, lang=lang)
        lines = [f"### {number}. {title}", ""]
        for index, step in enumerate(flow.steps, start=1):
            note: str = message(step.note, lang=lang)
            if step.command is not None:
                note = f"{_code(_command_line(step, lang))} — {note}"
            lines.append(f"{index}. {note}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


# --- templates -------------------------------------------------------------------------------


def _blocks(lang: Lang) -> dict[str, Callable[[], str]]:
    """Generated blocks of the guide in ``lang`` (rendered only when used)."""
    document = command_schema(lang=lang)
    listed = cast(list[Mapping[str, str]], list_commands(lang=lang)["commands"])
    summaries = {item["command"]: item["summary"] for item in listed}
    return {
        "version": lambda: __version__,
        "summary": lambda: _summary(document, lang),
        "rules": lambda: _principles(lang),
        "providers": lambda: _providers(lang),
        "statuses": lambda: _statuses(document, lang),
        "errors": lambda: _errors(document),
        "datasets": lambda: _datasets(lang),
        "commands": lambda: _commands(document, summaries, lang),
        "flags": lambda: _flags(document, lang),
        "flows": lambda: _flows(lang),
    }


def _render(template: str, blocks: Mapping[str, Callable[[], str]]) -> list[str]:
    """
    Lines of ``template``, each ending with a newline, with every marker replaced.

    Raises
    ------
    ValueError
        If a marker names an unknown block, a block is used twice or a
        multi-line block stands inside a line (program errors of a template).
    """
    used: set[str] = set()

    def block(name: str) -> str:
        if name not in blocks:
            raise ValueError(f"Unknown guide block {name!r} in the template")
        if name in used:
            raise ValueError(f"Guide block {name!r} used twice in the template")
        used.add(name)
        return blocks[name]()

    def inline(match: re.Match[str]) -> str:
        text = block(match["name"])
        if "\n" in text:
            raise ValueError(
                f"Guide block {match['name']!r} has several lines, but the marker stands inside a template line"
            )
        return text

    lines: list[str] = []
    for line in template.removesuffix("\n").split("\n"):
        whole = _MARKER.fullmatch(line.strip())
        if whole is not None:
            lines += block(whole["name"]).split("\n")
        else:
            lines.append(_MARKER.sub(inline, line))
    return [f"{line}\n" for line in lines]


def _template(format: GuideFormat, lang: Lang) -> str:
    resource = files("imgwtools").joinpath("_data", "agents", f"{format}.{lang}.md")
    return resource.read_text(encoding="utf-8")


@overload
def agent_guide(
    *,
    format: GuideFormat = "agents",
    lang: Lang = "en",
    output: None = None,
    force: bool = False,
) -> Iterator[str]: ...


@overload
def agent_guide(
    *,
    format: GuideFormat = "agents",
    lang: Lang = "en",
    output: PathArg,
    force: bool = False,
) -> OutputReport: ...


def agent_guide(
    *,
    format: GuideFormat = "agents",
    lang: Lang = "en",
    output: PathArg | None = None,
    force: bool = False,
) -> Iterator[str] | OutputReport:
    """
    Generate the guide for AI agents from the command catalog and the registries.

    ``format="agents"`` gives ``AGENTS.md``: the rules (check → run → read),
    the interfaces, the envelope statuses and error codes, the providers and
    datasets, every command with its options and effects, the flags, typical
    flows and what not to do. ``format="llms"`` gives ``llms.txt`` (llms.txt
    v2): a summary, the rules and links to the documentation. The text depends
    only on the installed package (no dates, no local paths), so the
    repository files ``AGENTS.md`` and ``llms.txt`` equal
    ``agent_guide(format=..., lang="en")`` byte for byte.

    Parameters
    ----------
    format : {"agents", "llms"}, optional
        Guide to generate: ``AGENTS.md`` (default) or ``llms.txt``.
    lang : {"en", "pl"}, optional
        Language of the guide and of the catalog texts in it (English by
        default); identifiers, codes and keys are the same in both.
    output : str, os.PathLike or None, optional
        The one plain file to write (DEV-19.1): its directory is created when
        missing, the guide goes through ``<dir>/.imgw-incoming/`` and the file
        is moved into place with ``os.replace``. ``None`` (default) returns the
        lines instead, byte-identical to the file.
    force : bool, optional
        Replace an existing ``output`` file; without it an existing file is a
        ``conflict``. Needs ``output``.

    Returns
    -------
    Iterator of str or OutputReport
        Lines of UTF-8 markdown, each ending with a newline, without
        ``output``; with ``output`` the written file as ``output`` and
        ``files[]``.

    Raises
    ------
    IMGWValidationError
        If ``format`` or ``lang`` is not allowed, ``output`` is a directory
        or ``force`` is given without ``output`` (``details.option`` names the
        option).
    IMGWError
        Code ``conflict``: ``output`` exists and ``force`` is not given
        (``details.reason="output_exists"``) or lies in a store of any tool
        (``"output_in_store"``).
    """
    options = validate_command(
        "commands guide",
        options={"format": format, "lang": lang, "output": output, "force": force},
    )
    guide = cast(GuideFormat, options["format"])
    language = cast(Lang, options["lang"])
    target = _target(cast("Path | None", options.get("output")), force=force)
    lines = _render(_template(guide, language), _blocks(language))
    if target is None:
        return iter(lines)
    written = _Lines((), lines, total=None, label="", on_progress=None, cancel=None)
    return cast(OutputReport, _deliver(written, target=target, cancel=None, done=""))


def _instructions(
    *,
    mode: McpMode,
    workdir: PathArg | None,
    root: PathArg | None,
) -> str:
    """
    Return the ``instructions`` of the MCP server: the rules and the mode lines.

    The server speaks English only (AGI-9.2).

    Parameters
    ----------
    mode : {"read", "write", "http"}
        Server mode (spec 2026-10-19 §6.3).
    workdir : str, os.PathLike or None
        Working directory of a stdio server (base of relative paths); not
        shown in the ``http`` mode, which never names server directories.
    root : str, os.PathLike or None
        Default store root of a stdio server, or None for none; the
        ``http`` mode only tells whether the server has a store (``IMGW_ROOT``).

    Returns
    -------
    str
        Markdown text below 2 KiB in UTF-8.
    """
    lines = ["Rules of IMGWTools:", _principles("en"), "", _MODES[mode]]
    if mode == "http":
        lines.append(
            "Store: the server's store; `version` relative to it."
            if root is not None
            else "The server has no store: store commands end with `store_unavailable`."
        )
    else:
        if workdir is not None:
            lines.append(
                f"Working directory (base of relative paths): `{os.fspath(workdir)}`."
            )
        if root is not None:
            lines.append(
                "Default store (`IMGW_ROOT`, `[imgw] root` or `<data_dir>/imgw`): "
                f"`{os.fspath(root)}`."
            )
        else:
            lines.append("No default store: give `root`.")
    lines += [
        f"Lists: `limit` {_PAGE_SIZE} by default, at most `IMGW_API_MAX_LIMIT`; "
        "next pages: `offset`.",
        "Full guide (commands, datasets, error codes, flows): the "
        "`imgw_commands_guide` tool.",
    ]
    return "\n".join(lines)
