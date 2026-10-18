"""
The only CLI adapter: ``imgw`` groups and commands generated from the catalog.

Every command of `imgwtools.commands.data_commands` becomes ``imgw <group>
<name>`` (spec §13.10): its help is the catalog description, its flags are the
catalog flags with their short aliases, and Click validates nothing, so the raw
text of the given options reaches `run_command` (`check_command` with
``--check``) and validation, defaults and the called public function are those
of Python and REST. ``--schema`` prints the command schema envelope of
``imgw commands schema --command …`` instead of running the command.

stdout carries one ``imgw-result/1`` envelope (only the data lines of a stream
without ``--path``); stderr carries progress, every distinct notice once and,
on an error, the JSON error line ``{"code", "detail", "details"}`` as its last
line. Exit codes follow the error registry and the envelope status (spec
§13.5). The first Ctrl+C requests cancellation, the second aborts at once.
"""

import inspect
import json
import os
import signal
import sys
import threading
import traceback
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from types import FrameType
from typing import Any, cast

import typer
from rich.console import Console
from typer.core import TyperCommand, TyperGroup

from imgwtools.commands import (
    check_command,
    command_schema,
    data_commands,
    run_command,
)
from imgwtools.exceptions import ERROR_CODES, ErrorCode, IMGWError, describe_os_error
from imgwtools.store.types import CommandOption, DataCommand, Notice, Progress

__all__ = ["ImgwGroup", "register_catalog"]

_ROOT_ENV = "IMGW_STORE_ROOT"
# Commands whose root is meaningful for one value of another option only: the
# environment default of --root applies only then (spec §13.3, stations find).
_ROOT_WHEN = {"stations find": ("source", "store")}
_REQUIRED_PANEL = "Opcje wymagane"
_OPTIONAL_PANEL = "Opcje"
_CHECK_HELP = (
    "Tylko sprawdź: wypisz plan imgw-plan/1 bez zapisu i bez pobierania danych"
)
_SCHEMA_HELP = (
    "Wypisz schemat JSON opcji tej komendy (jak imgw commands schema --command) "
    "bez jej wykonania"
)
_METAVARS = {
    "str": "TEKST",
    "int": "LICZBA",
    "float": "LICZBA",
    "date": "RRRR-MM-DD",
    "path": "ŚCIEŻKA",
    "choice": "WARTOŚĆ",
    "list": "LISTA",
    "object": "JSON",
}
_LEVELS = {
    "info": ("Informacja", "cyan"),
    "warning": ("Ostrzeżenie", "yellow"),
    "error": ("Błąd", "red"),
}
_ERR = Console(stderr=True, highlight=False, soft_wrap=True)
# Exceptions of the Click flavour Typer runs on (its vendored copy or the click
# package), reached through the public ``typer.BadParameter``.
_click_errors = sys.modules[typer.BadParameter.__module__]


def _catalog_tables() -> tuple[dict[str, str], dict[str, int]]:
    document = command_schema()
    return (
        cast(dict[str, str], document["groups"]),
        cast(dict[str, int], document["exit_codes"]),
    )


_GROUPS, _EXIT_CODES = _catalog_tables()


# --- wyjście ---------------------------------------------------------------------------------


def _json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=str)


def _print_progress(progress: Progress) -> None:
    text = progress.message or f"{progress.unit}: {progress.status}"
    _ERR.print(
        f"[{progress.current}/{progress.total}] {text}", markup=False, emoji=False
    )


def _print_notice(level: str, text: str) -> None:
    label, style = _LEVELS.get(level, (level, "white"))
    _ERR.print(f"{label}: {text}", style=style, markup=False, emoji=False)


def _write_lines(lines: Iterator[str]) -> None:
    """Write the data lines of a stream to stdout as UTF-8, line ends unchanged."""
    stream = typer.get_binary_stream("stdout")
    for line in lines:
        stream.write(line.encode("utf-8"))
    stream.flush()


def _silence_stdout() -> None:
    """Send the final stdout flush to devnull once the reader left (``| head``)."""
    with suppress(OSError, ValueError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


# --- błędy -----------------------------------------------------------------------------------


def _error_line(code: ErrorCode, detail: str, details: Mapping[str, object]) -> int:
    """Write the JSON error line of spec §13.5 to stderr; return the exit code."""
    spec = ERROR_CODES[code]
    if spec.exit_code is None:  # REST-only code (forbidden, method_not_allowed)
        spec = ERROR_CODES["internal_error"]
    document = {
        "code": spec.code,
        "detail": detail or spec.title,
        "details": dict(details),
    }
    typer.echo(_json(document), err=True)
    return spec.exit_code or 1


def _failure(exc: BaseException) -> int:
    """Report an exception as the JSON error line; return the exit code."""
    if isinstance(exc, KeyboardInterrupt):
        return _error_line(
            "cancelled", "Operację przerwano natychmiast (ponowne Ctrl+C)", {}
        )
    if isinstance(exc, IMGWError):
        return _error_line(exc.code, exc.detail, exc.details)
    if isinstance(exc, OSError):
        return _error_line("io_error", *describe_os_error(exc))
    traceback.print_exception(exc, file=sys.stderr)
    return _error_line(
        "internal_error", f"Błąd wewnętrzny programu ({type(exc).__name__}): {exc}", {}
    )


def _option_name(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def _usage_failure(exc: Any) -> int:
    """Report a Click syntax error as ``validation_error``; return the exit code."""
    ctx = exc.ctx
    path = "imgw" if ctx is None else ctx.command_path
    details: dict[str, object] = {"click": exc.format_message()}
    if isinstance(exc, _click_errors.NoSuchOption):
        details["option"] = _option_name(exc.option_name)
        detail = f"Nieznana opcja {exc.option_name} komendy {path}"
        if exc.possibilities:
            detail += f"; podobne: {', '.join(sorted(exc.possibilities))}"
    elif isinstance(exc, _click_errors.BadOptionUsage):
        details["option"] = _option_name(exc.option_name)
        detail = (
            f"Nieprawidłowe użycie opcji {exc.option_name} komendy {path}: brak "
            "wartości albo wartość przy przełączniku"
        )
    elif isinstance(exc, _click_errors.BadParameter) and exc.param is not None:
        details["option"] = exc.param.name
        flags = "/".join(exc.param.opts)
        detail = (
            f"Brak wymaganej opcji {flags} komendy {path}"
            if isinstance(exc, _click_errors.MissingParameter)
            else f"Nieprawidłowa wartość opcji {flags} komendy {path}"
        )
    elif ctx is not None and isinstance(ctx.command, TyperGroup):
        names = ctx.command.list_commands(ctx)
        details["allowed"] = names
        detail = f"Brak albo nieznana komenda po {path}; dostępne: {', '.join(names)}"
    else:
        detail = (
            f"Nieprawidłowe wywołanie {path}: komenda przyjmuje wyłącznie opcje "
            "--nazwa wartość"
        )
    return _error_line("validation_error", f"{detail} (pomoc: {path} --help)", details)


class ImgwGroup(TyperGroup):
    """
    Root ``imgw`` group reporting Click syntax errors as the JSON error line.

    An unknown flag or command, a missing option value or a missing command is
    the ``validation_error`` of spec §13.5: stdout stays empty, the last stderr
    line is ``{"code", "detail", "details"}`` with a Polish ``detail`` and the
    original Click message in ``details.click``, and the exit code is 2.
    """

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: Any = None,
        **extra: Any,
    ) -> Any:
        """Parse the root arguments; a syntax error ends with the JSON error line."""
        try:
            return super().make_context(info_name, args, parent, **extra)
        except _click_errors.UsageError as exc:
            raise typer.Exit(_usage_failure(exc)) from None

    def invoke(self, ctx: Any) -> Any:
        """Run the subcommand; a syntax error ends with the JSON error line."""
        try:
            return super().invoke(ctx)
        except _click_errors.UsageError as exc:
            raise typer.Exit(_usage_failure(exc)) from None


class _CatalogCommand(TyperCommand):
    """Catalog command whose syntax errors name it (Click omits the context)."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        """Parse the options; a syntax error carries this command's context."""
        try:
            return super().parse_args(ctx, args)
        except _click_errors.UsageError as exc:
            if exc.ctx is None:
                exc.ctx, exc.cmd = ctx, self
            raise


# --- wykonanie -------------------------------------------------------------------------------


@contextmanager
def _interrupt() -> Iterator[threading.Event]:
    """Turn the first Ctrl+C into a cancellation request, the second into abort."""
    requested = threading.Event()
    if threading.current_thread() is not threading.main_thread():
        yield requested
        return

    def handle(signum: int, frame: FrameType | None) -> None:
        if requested.is_set():
            raise KeyboardInterrupt
        requested.set()
        _print_notice(
            "warning",
            "Przerwanie (Ctrl+C): kończę bieżący krok i zwracam wynik częściowy; "
            "ponowne Ctrl+C przerywa natychmiast",
        )

    previous = signal.signal(signal.SIGINT, handle)
    try:
        yield requested
    finally:
        signal.signal(signal.SIGINT, previous)


def _run(command: str, options: dict[str, object], *, check: bool) -> int:
    """Run (``check``: plan) one catalog command and print it; return the exit code."""
    shown: set[Notice] = set()

    def on_notice(notice: Notice) -> None:
        if notice not in shown:
            shown.add(notice)
            _print_notice(notice.level, notice.text)

    root = options.get("root")
    with _interrupt() as requested:
        try:
            dispatch = check_command if check else run_command
            outcome = dispatch(
                command,
                options=options,
                on_progress=_print_progress,
                on_notice=on_notice,
                cancel=requested.is_set,
            )
            if isinstance(outcome.result, Iterator):
                _write_lines(outcome.result)
            else:
                base = Path(root).expanduser() if isinstance(root, str) else None
                typer.echo(_json(outcome.to_json(root=base)))
        except BrokenPipeError:
            _silence_stdout()
            return 0
        except (KeyboardInterrupt, Exception) as exc:
            return _failure(exc)
    return _EXIT_CODES[outcome.status]


# --- rejestracja -----------------------------------------------------------------------------


def _metavar(option: CommandOption) -> str:
    choices = "|".join(option.choices)
    return choices if choices and len(choices) <= 40 else _METAVARS[option.type]


def _option(option: CommandOption) -> inspect.Parameter:
    """Click option of a catalog option: raw text in, defaults left to the catalog."""
    panel = _REQUIRED_PANEL if option.required else _OPTIONAL_PANEL
    annotation: object
    if option.type == "bool" and option.default is True:
        default = typer.Option(
            None,
            f"{option.flag}/--no-{option.flag[2:]}",
            help=option.help,
            rich_help_panel=panel,
        )
        annotation = bool | None
    elif option.type == "bool":
        default = typer.Option(
            False, option.flag, *option.aliases, help=option.help, rich_help_panel=panel
        )
        annotation = bool
    else:
        default = typer.Option(
            None,
            option.flag,
            *option.aliases,
            help=option.help,
            metavar=_metavar(option),
            rich_help_panel=panel,
            envvar=_ROOT_ENV if option.name == "root" else None,
        )
        annotation = list[str] | None if option.type == "list" else str | None
    return inspect.Parameter(
        option.name,
        inspect.Parameter.KEYWORD_ONLY,
        default=default,
        annotation=annotation,
    )


def _flag(name: str, help_: str) -> inspect.Parameter:
    return inspect.Parameter(
        name,
        inspect.Parameter.KEYWORD_ONLY,
        default=typer.Option(
            False, f"--{name}", help=help_, rich_help_panel=_OPTIONAL_PANEL
        ),
        annotation=bool,
    )


def _parameters(spec: DataCommand) -> list[inspect.Parameter]:
    parameters = [
        inspect.Parameter(
            "ctx", inspect.Parameter.KEYWORD_ONLY, annotation=typer.Context
        ),
        *(_option(option) for option in spec.options),
    ]
    if spec.check is not None:
        parameters.append(_flag("check", _CHECK_HELP))
    parameters.append(_flag("schema", _SCHEMA_HELP))
    return parameters


def _given(spec: DataCommand, values: Mapping[str, Any]) -> dict[str, object]:
    """Options given on the command line as raw text (lists: one text per flag)."""
    options: dict[str, object] = {}
    for option in spec.options:
        value = values[option.name]
        if (
            value is None
            or (value is False and option.default is not True)
            or (isinstance(value, list) and not value)
        ):
            continue
        options[option.name] = value
    return options


def _environment_root(
    spec: DataCommand, options: dict[str, object], ctx: typer.Context
) -> None:
    """Drop a --root read from IMGW_STORE_ROOT where the command rejects root."""
    rule = _ROOT_WHEN.get(spec.name)
    origin = ctx.get_parameter_source("root") if rule is not None else None
    if rule is None or origin is None or origin.name != "ENVIRONMENT":
        return
    name, value = rule
    if str(options.get(name, "")).strip() != value:
        options.pop("root", None)


def _register(group: typer.Typer, spec: DataCommand) -> None:
    def callback(ctx: typer.Context, **values: Any) -> None:
        check = bool(values.pop("check", False))
        if values.pop("schema"):
            code = _run("commands schema", {"command": spec.name}, check=False)
        else:
            options = _given(spec, values)
            _environment_root(spec, options, ctx)
            code = _run(spec.name, options, check=check)
        if code:
            raise typer.Exit(code)

    cast(Any, callback).__signature__ = inspect.Signature(_parameters(spec))
    name = spec.name.split(" ", 1)[1]
    group.command(
        name, cls=_CatalogCommand, help=spec.description, short_help=spec.description
    )(callback)


def register_catalog(app: typer.Typer, /) -> None:
    """
    Register every catalog group and command under the ``imgw`` application.

    Each group of the catalog (``datasets``, ``stations``, ``current``,
    ``pmaxtp``, ``store``, ``series``, ``project``, ``commands``) becomes a
    subcommand group with the catalog group description as its help, holding
    every catalog command of that group. Command help is the catalog
    description; options are the catalog flags and aliases (required ones in
    the "Opcje wymagane" panel), ``--root`` falls back to
    ``$IMGW_STORE_ROOT``, list options take comma-separated values or a
    repeated flag, ``--check`` exists only for commands with a check twin and
    ``--schema`` for every command.

    Parameters
    ----------
    app : typer.Typer
        The ``imgw`` application, created with ``cls=ImgwGroup`` so that Click
        syntax errors end with the JSON error line.
    """
    groups = {name: typer.Typer(help=text) for name, text in _GROUPS.items()}
    for spec in data_commands():
        _register(groups[spec.name.split(" ", 1)[0]], spec)
    for name, group in groups.items():
        app.add_typer(group, name=name, help=_GROUPS[name])
