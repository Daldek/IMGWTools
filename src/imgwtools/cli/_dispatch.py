"""Typer adapter for the data command catalog (spec §10).

Every catalog command becomes a CLI command whose help texts are the catalog
descriptions and whose flags are the catalog ``--kebab-case`` flags. Values are
passed to `imgwtools.commands.run_command` (or `check_command` with ``--check``)
unchanged, so validation, defaults and the called public API are identical to
the Python API. Progress and notices go to stderr, the result to stdout.
"""

import inspect
import json
import os
import signal
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import FrameType
from typing import Any, cast

import typer
from pydantic import BaseModel
from rich.console import Console

from imgwtools.commands import check_command, data_commands, run_command
from imgwtools.exceptions import IMGWError
from imgwtools.store.types import CommandOption, DataCommand, Notice, Progress

__all__ = ["EXIT_CANCELLED", "EXIT_FAILED", "register_command", "register_group"]

EXIT_CANCELLED = 130
"""Exit code of a command cancelled with Ctrl+C (as for SIGINT in shells)."""
EXIT_FAILED = 1
"""Exit code of an error and of a printed result with any failed item."""
_FAILED = frozenset({"failed", "stale_plan"})

_ERR = Console(stderr=True, highlight=False, soft_wrap=True)
_LEVELS = {
    "info": ("Informacja", "cyan"),
    "warning": ("Ostrzeżenie", "yellow"),
    "error": ("Błąd", "red"),
}
_CHECK_HELP = (
    "Tylko sprawdź: wypisz plan imgw-plan/1 bez zapisu i bez pobierania danych"
)
_METAVARS = {
    "path": "ŚCIEŻKA",
    "list": "LISTA",
    "int": "LICZBA",
    "str": "TEKST",
    "choice": "WARTOŚĆ",
}
_REQUIRED_PANEL = "Opcje wymagane"
_OPTIONAL_PANEL = "Opcje"

Summary = Callable[[list[Progress]], None]


def _plain(value: object) -> object:
    """Convert a public result to JSON-compatible values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set | frozenset):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _print_progress(progress: Progress) -> None:
    text = progress.message or f"{progress.unit}: {progress.status}"
    _ERR.print(f"[{progress.current}/{progress.total}] {text}", markup=False)


def _print_notice(notice: Notice) -> None:
    label, style = _LEVELS.get(notice.level, (notice.level, "white"))
    _ERR.print(f"{label}: {notice.text}", style=style, markup=False)


def _failed(value: object) -> bool:
    """Whether a command result reports a failed or stale item, at any depth."""
    if not is_dataclass(value):
        return False
    if getattr(value, "status", None) in _FAILED:
        return True
    tasks = getattr(value, "tasks", None)
    if isinstance(tasks, Mapping) and any(state in _FAILED for state in tasks.values()):
        return True
    return any(
        _failed(item)
        for name in ("items", "series", "files")
        if isinstance(items := getattr(value, name, None), tuple)
        for item in items
    )


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
        _ERR.print(
            "Przerwanie (Ctrl+C): kończę bieżący krok i zwracam wynik częściowy; "
            "ponowne Ctrl+C przerywa natychmiast",
            style="yellow",
            markup=False,
        )

    previous = signal.signal(signal.SIGINT, handle)
    try:
        yield requested
    finally:
        signal.signal(signal.SIGINT, previous)


def _cancelled(result: object) -> bool:
    return getattr(result, "cancelled", False) is True or (
        getattr(result, "status", None) == "cancelled"
    )


def _execute(
    command: str, options: dict[str, object], *, check: bool, summary: Summary | None
) -> None:
    events: list[Progress] = []
    shown: set[tuple[str, str]] = set()

    def on_progress(progress: Progress) -> None:
        events.append(progress)
        _print_progress(progress)

    def on_notice(notice: Notice) -> None:
        # One line per distinct notice and run: a sync repeats the license terms
        # for every archive (the Python/REST hooks still receive every notice).
        if (notice.code, notice.text) not in shown:
            shown.add((notice.code, notice.text))
            _print_notice(notice)

    with _interrupt() as requested:
        try:
            dispatch = check_command if check else run_command
            result = dispatch(
                command,
                options=options,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=requested.is_set,
            )
            if isinstance(result, Iterator):
                # Text lines streamed as produced (e.g. ``store read`` without --path).
                try:
                    for line in result:
                        if requested.is_set():
                            break
                        typer.echo(line, nl=False)
                    sys.stdout.flush()
                except BrokenPipeError:
                    # Reader closed the pipe (e.g. ``| head``): it got all it wanted, so
                    # stop quietly with success; route the interpreter's final flush to
                    # devnull instead of failing again.
                    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
                    raise typer.Exit(0) from None
        except KeyboardInterrupt:
            _ERR.print("Przerwano natychmiast (Ctrl+C)", style="red", markup=False)
            raise typer.Exit(EXIT_CANCELLED) from None
        except (IMGWError, OSError) as exc:
            _ERR.print(f"Błąd: {exc}", style="red", markup=False)
            raise typer.Exit(EXIT_FAILED) from None
    if isinstance(result, Path):
        typer.echo(str(result))
    elif not isinstance(result, Iterator):
        typer.echo(json.dumps(_plain(result), ensure_ascii=False, indent=2))
    if summary is not None and not check:
        summary(events)
    if requested.is_set() or _cancelled(result):
        _ERR.print(
            "Operację anulowano (Ctrl+C); wynik jest częściowy",
            style="yellow",
            markup=False,
        )
        raise typer.Exit(EXIT_CANCELLED)
    if _failed(result) or any(event.status in _FAILED for event in events):
        _ERR.print(
            "Błąd: część pozycji zakończyła się niepowodzeniem; szczegóły w wyniku",
            style="red",
            markup=False,
        )
        raise typer.Exit(EXIT_FAILED)


def _metavar(option: CommandOption) -> str:
    choices = "|".join(option.choices)
    return choices if choices and len(choices) <= 40 else _METAVARS[option.type]


def _parameters(spec: DataCommand, short: Mapping[str, str]) -> list[inspect.Parameter]:
    parameters = []
    for option in spec.options:
        flags = (option.flag, *((short[option.name],) if option.name in short else ()))
        is_flag = option.type == "bool"
        parameters.append(
            inspect.Parameter(
                option.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=typer.Option(
                    False if is_flag else None,
                    *flags,
                    help=option.help,
                    metavar=None if is_flag else _metavar(option),
                    rich_help_panel=_REQUIRED_PANEL
                    if option.required
                    else _OPTIONAL_PANEL,
                ),
                annotation=bool if is_flag else str | None,
            )
        )
    parameters.append(
        inspect.Parameter(
            "check",
            inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(
                False, "--check", help=_CHECK_HELP, rich_help_panel=_OPTIONAL_PANEL
            ),
            annotation=bool,
        )
    )
    return parameters


def register_command(
    app: typer.Typer,
    command: str,
    /,
    *,
    short: Mapping[str, str] | None = None,
    summary: Summary | None = None,
) -> None:
    """
    Register one catalog command as a subcommand of a Typer group.

    The subcommand name is the last word of the catalog name, its help is the
    catalog description and every catalog option becomes its catalog flag with
    the catalog help. Raw option text is passed to `run_command`, or to
    `check_command` when ``--check`` is given; options left out are omitted, so
    the dispatcher applies the same defaults and validation as the Python API.

    Parameters
    ----------
    app : typer.Typer
        Group receiving the command, e.g. the ``imgw store`` group.
    command : str
        Catalog command name, e.g. ``"store sync"``.
    short : Mapping of str to str or None, optional
        Additional short flags keyed by option name (e.g. ``{"year": "-y"}``).
    summary : callable or None, optional
        Called with all progress events after a successful run, e.g. to print
        a download summary.

    Raises
    ------
    KeyError
        If ``command`` is not in the catalog.
    """
    spec = {item.name: item for item in data_commands()}[command]
    aliases = dict(short or {})

    def callback(**values: Any) -> None:
        check = bool(values.pop("check"))
        options = {
            name: value
            for name, value in values.items()
            if value is not None and value is not False
        }
        _execute(command, options, check=check, summary=summary)

    cast(Any, callback).__signature__ = inspect.Signature(_parameters(spec, aliases))
    name = command.split(" ", 1)[1]
    app.command(name, help=spec.description, short_help=spec.description)(callback)


def register_group(app: typer.Typer, group: str, /) -> None:
    """
    Register every catalog command of a group (``imgw <group> …``).

    Parameters
    ----------
    app : typer.Typer
        Group receiving the commands.
    group : str
        First word of the catalog command names, e.g. ``"series"``.
    """
    for spec in data_commands():
        if spec.name.split(" ", 1)[0] == group:
            register_command(app, spec.name)
