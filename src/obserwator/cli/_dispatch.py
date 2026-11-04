"""
The only CLI adapter: ``obserwator`` groups and commands generated from the catalog.

Every command of `obserwator.commands.data_commands` becomes ``obserwator <group>
<name>`` (spec §13.10): its help is the catalog description, its flags are the
catalog flags with their short aliases, and Click validates nothing, so the raw
text of the given options reaches `run_command` (`check_command` with
``--check``) and validation, defaults and the called public function are those
of Python and REST. ``--schema`` describes the command as ``obserwator commands
schema --command …`` does instead of running it.

``--json`` puts one ``obserwator-result/1`` envelope on stdout; without it stdout
carries a short rendering of the result for a person (`obserwator.cli._render`) in
the language of ``--lang`` (``OBSERWATOR_LANG`` by default), ending with the
notices. The data lines of a stream without ``--output`` are the same in both
modes. stderr carries progress, in ``--json`` mode every distinct notice once
and, on an error, the ``obserwator-error/1`` document (`obserwator.error_report`:
``schema, code, title, message, hint?, details, exit_code, command?``) as
compact JSON on its last line, in the human mode after one readable line. Exit
codes follow the error registry and the envelope status (spec §13.5). The first
Ctrl+C requests cancellation, the second aborts at once.

The help is in the language of ``OBSERWATOR_LANG`` (``Settings.lang``, ``pl`` by
default, chosen at import): catalog texts and the help elements of Typer and
Click (panels, ``--help``, the usage line with its ``[OPTIONS]`` and ``COMMAND
[ARGS]...`` placeholders, the environment and default markers, the abort
message); the progress and notice lines, the human rendering and the readable
error line follow ``--lang`` too. Another value of ``OBSERWATOR_LANG`` ends every
call with ``validation_error`` (spec 2026-10-19 §4.2–§4.3). The JSON error line
is English whatever the setting (AGI-9.2), as is the envelope of ``--json``;
``--lang`` of the description commands defaults to English with ``--json`` and
to the language of the call without it.
"""

import errno
import inspect
import json
import os
import signal
import sys
import threading
import traceback
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, cast

import typer
from rich.console import Console
from typer import rich_utils
from typer.core import TyperCommand, TyperGroup

from obserwator.cli._render import render
from obserwator.commands import (
    check_command,
    command_schema,
    data_commands,
    run_command,
    validate_command,
)
from obserwator.config import check_config, human_language, settings
from obserwator.error_report import error_document
from obserwator.exceptions import (
    ERROR_CODES,
    ErrorCode,
    ObserwatorError,
    describe_os_error,
)
from obserwator.messages import LANGS, Lang, Message, localize, message
from obserwator.store.types import CommandOption, DataCommand, Notice, Progress

__all__ = [
    "ObserwatorCommand",
    "ObserwatorGroup",
    "ObserwatorSubgroup",
    "register_catalog",
]

_LANG_ENV = "OBSERWATOR_LANG"


@dataclass(frozen=True)
class _HelpTexts:
    """Help texts of the CLI in one language (spec 2026-10-19 §4.3)."""

    required_panel: str
    optional_panel: str
    commands_panel: str
    arguments_panel: str
    help_option: str
    usage: str
    envvar: str
    default: str
    required: str
    options_metavar: str
    commands_metavar: str
    aborted: str
    check: str
    schema: str
    json: str
    lang: str
    metavars: Mapping[str, str]


def _help_texts(lang: Lang) -> _HelpTexts:
    """Help texts of the CLI in ``lang`` (the English ones are those of Typer and Click)."""
    return _HelpTexts(
        required_panel=message("cli.help_required_panel", lang=lang),
        optional_panel=message("cli.help_optional_panel", lang=lang),
        commands_panel=message("cli.help_commands_panel", lang=lang),
        arguments_panel=message("cli.help_arguments_panel", lang=lang),
        help_option=message("cli.help_help_option", lang=lang),
        usage=message("cli.help_usage", lang=lang),
        envvar=message("cli.help_envvar", lang=lang),
        default=message("cli.help_default", lang=lang),
        required=message("cli.help_required", lang=lang),
        options_metavar=message("cli.help_options_metavar", lang=lang),
        commands_metavar=message("cli.help_commands_metavar", lang=lang),
        aborted=message("cli.help_aborted", lang=lang),
        check=message("cli.help_check", lang=lang),
        schema=message("cli.help_schema", lang=lang),
        json=message("cli.help_json", lang=lang),
        lang=message("cli.help_lang", lang=lang),
        metavars={
            "str": message("cli.metavar_text", lang=lang),
            "int": message("cli.metavar_number", lang=lang),
            "float": message("cli.metavar_number", lang=lang),
            "date": message("cli.metavar_date", lang=lang),
            "path": message("cli.metavar_path", lang=lang),
            "choice": message("cli.metavar_value", lang=lang),
            "list": message("cli.metavar_list", lang=lang),
        },
    )


_LEVELS = {
    "info": ("cli.level_info", "cyan"),
    "warning": ("cli.level_warning", "yellow"),
}
_ERR = Console(stderr=True, highlight=False, soft_wrap=True)
# Exceptions of the Click flavour Typer runs on (its vendored copy or the click
# package), reached through the public ``typer.BadParameter``.
_click_errors = sys.modules[typer.BadParameter.__module__]


# Language of the help and of the lines printed to stderr, chosen once: an invalid
# OBSERWATOR_LANG keeps the Polish help while every call ends with the validation_error
# line (ObserwatorGroup).
_LANG: Lang = human_language() or "pl"
_HELP = _help_texts(_LANG)
rich_utils.OPTIONS_PANEL_TITLE = _HELP.optional_panel
rich_utils.COMMANDS_PANEL_TITLE = _HELP.commands_panel
rich_utils.ARGUMENTS_PANEL_TITLE = _HELP.arguments_panel
rich_utils.ENVVAR_STRING = _HELP.envvar
rich_utils.DEFAULT_STRING = _HELP.default
rich_utils.REQUIRED_LONG_STRING = _HELP.required
rich_utils.ABORTED_TEXT = _HELP.aborted
# Usage-line placeholders of Click (``Command.options_metavar``,
# ``Group.subcommand_metavar``) in the CLI language.
_USAGE_PIECES = {
    "[OPTIONS]": _HELP.options_metavar,
    "COMMAND [ARGS]...": _HELP.commands_metavar,
}


def _catalog_tables() -> tuple[dict[str, str], dict[str, int]]:
    document = command_schema(lang=_LANG)
    return (
        cast(dict[str, str], document["groups"]),
        cast(dict[str, int], document["exit_codes"]),
    )


_GROUPS, _EXIT_CODES = _catalog_tables()
_JSON_FLAG = "--json"
_LANG_FLAG = "--lang"


@dataclass(frozen=True)
class _Output:
    """How the current call prints: ``--json`` (machine) or for a person in ``lang``."""

    json: bool
    lang: Lang


# Set per call: from the words of the line before parsing (an error of the line
# itself), then from the parsed flags of a catalog command. A call outside the
# root group (a test of one command) prints for a person in the CLI language.
_OUTPUT: ContextVar[_Output] = ContextVar("obserwator_output")
_FOR_PERSON = _Output(json=False, lang=_LANG)


def _output() -> _Output:
    """The output of the current call."""
    return _OUTPUT.get(_FOR_PERSON)


def _output_of(words: Sequence[str]) -> _Output:
    """The output a command line asks for, read from its words (before ``--``)."""
    words = list(words[: words.index("--")] if "--" in words else words)
    lang = _LANG
    for index, word in enumerate(words):
        value = (
            words[index + 1] if word == _LANG_FLAG and index + 1 < len(words) else None
        )
        if word.startswith(f"{_LANG_FLAG}="):
            value = word.partition("=")[2]
        if value in LANGS:
            lang = value
    return _Output(_JSON_FLAG in words, lang)


# --- wyjście ---------------------------------------------------------------------------------


def _json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=str)


def _print_progress(progress: Progress) -> None:
    lang = _output().lang
    text = localize(progress.message, lang) or f"{progress.unit}: {progress.status}"
    _ERR.print(
        f"[{progress.current}/{progress.total}] {text}", markup=False, emoji=False
    )


def _print_notice(level: str, text: str) -> None:
    lang = _output().lang
    key, style = _LEVELS.get(level, ("", "white"))
    label = message(key, lang=lang) if key else level
    _ERR.print(
        f"{label}: {localize(text, lang)}", style=style, markup=False, emoji=False
    )


def _to_stdout(write: Callable[..., object], *args: object) -> None:
    """
    Call a write of stdout; a reader that left (``| head``) is `BrokenPipeError`.

    POSIX reports a write to a pipe whose reading end is closed as EPIPE,
    Windows as EINVAL (the code its C runtime gives ``ERROR_NO_DATA``).
    """
    try:
        write(*args)
    except OSError as exc:
        if os.name == "nt" and exc.errno == errno.EINVAL:
            raise BrokenPipeError(errno.EPIPE, os.strerror(errno.EPIPE)) from exc
        raise


def _write_lines(lines: Iterator[str]) -> None:
    """Write the data lines of a stream to stdout as UTF-8, line ends unchanged."""
    stream = typer.get_binary_stream("stdout")
    for line in lines:
        _to_stdout(stream.write, line.encode("utf-8"))
    _to_stdout(stream.flush)


def _silence_stdout() -> None:
    """Send the final stdout flush to devnull once the reader left (``| head``)."""
    with suppress(OSError, ValueError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _utf8_streams() -> None:
    """Write stdout and stderr in UTF-8 with LF line ends, as `_write_lines` does.

    On Windows the text streams default to the code page and turn a line end
    into CRLF; the envelope and the error line are the same bytes everywhere.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n")


# --- błędy -----------------------------------------------------------------------------------


def _error_line(
    code: ErrorCode,
    detail: str,
    details: Mapping[str, object],
    *,
    hint: str | None = None,
    command: str | None = None,
) -> int:
    """
    Write the ``obserwator-error/1`` line to stderr in English; return the exit code.

    Without ``--json`` one readable line in the language of the call comes first.
    """
    if ERROR_CODES[code].exit_code is None:  # REST-only code (method_not_allowed)
        code = "internal_error"
    output = _output()
    if not output.json:
        shown = error_document(
            code, detail, details, hint=hint, command=command, lang=output.lang
        )
        line = (
            message(
                "cli.human_error_hint",
                lang=output.lang,
                title=shown.title,
                message=shown.message,
                hint=shown.hint,
            )
            if shown.hint
            else message(
                "cli.human_error",
                lang=output.lang,
                title=shown.title,
                message=shown.message,
            )
        )
        _ERR.print(line, style="red", markup=False, emoji=False)
    report = error_document(code, detail, details, hint=hint, command=command)
    typer.echo(report.to_json(), err=True)
    return report.exit_code or 1


def _failure(exc: BaseException, command: str | None = None) -> int:
    """Report an exception as the JSON error line; return the exit code."""
    if isinstance(exc, KeyboardInterrupt):
        return _error_line(
            "cancelled", message("cli.stopped_at_once"), {}, command=command
        )
    if isinstance(exc, ObserwatorError):
        return _error_line(
            exc.code, exc.detail, exc.details, hint=exc.hint, command=command
        )
    if isinstance(exc, OSError):
        return _error_line("io_error", *describe_os_error(exc), command=command)
    traceback.print_exception(exc, file=sys.stderr)
    return _error_line(
        "internal_error",
        message("cli.internal_error", kind=type(exc).__name__, error=exc),
        {},
        command=command,
    )


def _option_name(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def _usage_failure(exc: Any) -> int:
    """Report a Click syntax error as ``validation_error``; return the exit code."""
    ctx = exc.ctx
    path = "obserwator" if ctx is None else ctx.command_path
    command = (
        path.split(" ", 1)[1]
        if ctx is not None and isinstance(ctx.command, _CatalogCommand)
        else None
    )
    details: dict[str, object] = {"click": exc.format_message()}
    detail: Message
    hint = message("cli.hint_help", path=path)
    if isinstance(exc, _click_errors.NoSuchOption):
        details["option"] = _option_name(exc.option_name)
        if exc.possibilities:
            similar = ", ".join(sorted(exc.possibilities))
            detail = message(
                "cli.unknown_option_similar",
                option=exc.option_name,
                path=path,
                similar=similar,
            )
            hint = message("cli.hint_similar", similar=similar, path=path)
        else:
            detail = message("cli.unknown_option", option=exc.option_name, path=path)
    elif isinstance(exc, _click_errors.BadOptionUsage):
        details["option"] = _option_name(exc.option_name)
        detail = message("cli.bad_option_usage", option=exc.option_name, path=path)
    elif isinstance(exc, _click_errors.BadParameter) and exc.param is not None:
        details["option"] = exc.param.name
        flags = "/".join(exc.param.opts)
        detail = (
            message("cli.missing_option", flags=flags, path=path)
            if isinstance(exc, _click_errors.MissingParameter)
            else message("cli.invalid_option_value", flags=flags, path=path)
        )
    elif ctx is not None and isinstance(ctx.command, TyperGroup):
        names = ctx.command.list_commands(ctx)
        details["allowed"] = names
        detail = message("cli.unknown_command", path=path, names=", ".join(names))
    else:
        detail = message("cli.invalid_call", path=path)
    return _error_line("validation_error", detail, details, hint=hint, command=command)


def _language_failure() -> int:
    """Report ``OBSERWATOR_LANG`` outside ``pl`` and ``en``; return the exit code."""
    value = settings.lang
    return _error_line(
        "validation_error",
        message(
            "cli.invalid_language_variable",
            value=value,
            variable=_LANG_ENV,
            allowed=", ".join(LANGS),
        ),
        {"option": _LANG_ENV, "value": value, "allowed": list(LANGS)},
        hint=message("cli.hint_language", variable=_LANG_ENV, allowed=", ".join(LANGS)),
    )


def _help_option(option: Any) -> Any:
    """``--help`` described in the CLI language (Click caches it per command)."""
    if option is not None:
        option.help = _HELP.help_option
    return option


def _write_usage(command: Any, ctx: Any, formatter: Any) -> None:
    """Write the usage line of ``command`` in the CLI language."""
    pieces: list[str] = command.collect_usage_pieces(ctx)
    line = " ".join(_USAGE_PIECES.get(piece, piece) for piece in pieces)
    formatter.write_usage(ctx.command_path, line, prefix=_HELP.usage)


class ObserwatorGroup(TyperGroup):
    """
    Root ``obserwator`` group: checks ``OBSERWATOR_LANG`` and reports syntax errors as JSON.

    ``OBSERWATOR_LANG`` outside ``pl`` and ``en`` ends every call, ``--help``
    included, with the ``validation_error`` line (``details.option`` is
    ``OBSERWATOR_LANG``, ``details.allowed`` the languages, exit code 2). An unknown
    flag or command, a missing option value or a missing command is the
    ``validation_error`` of spec §13.5: stdout stays empty, the last stderr
    line is the English ``obserwator-error/1`` document with the original Click
    message in ``details.click``, a ``hint`` naming ``--help`` (or the similar
    flag) and the ``command`` when it is a catalog command, and the exit code is 2. The
    help elements of Typer and Click are in the CLI language. stdout and stderr
    are written in UTF-8 whatever the locale (cp1252 and the like on Windows).
    """

    def main(self, *args: Any, **kwargs: Any) -> Any:
        """Run ``obserwator`` with stdout and stderr in UTF-8."""
        _utf8_streams()
        return super().main(*args, **kwargs)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: Any = None,
        **extra: Any,
    ) -> Any:
        """Parse the root arguments; a syntax error ends with the JSON error line."""
        _OUTPUT.set(_output_of(args))
        if human_language() is None:
            raise typer.Exit(_language_failure())
        if args[:1] != [
            "config"
        ]:  # `obserwator config show` reports the problem itself
            try:
                check_config()
            except ObserwatorError as exc:
                raise typer.Exit(_failure(exc)) from None
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

    def get_help_option(self, ctx: Any) -> Any:
        """Return the ``--help`` option described in the CLI language."""
        return _help_option(super().get_help_option(ctx))

    def format_usage(self, ctx: Any, formatter: Any) -> None:
        """Write the usage line with the prefix of the CLI language."""
        _write_usage(self, ctx, formatter)


class ObserwatorSubgroup(TyperGroup):
    """
    Group under ``obserwator`` (``typer.Typer(cls=ObserwatorSubgroup)``).

    Its ``--help`` option and usage line are in the CLI language, like those
    of the catalog groups.
    """

    def get_help_option(self, ctx: Any) -> Any:
        """Return the ``--help`` option described in the CLI language."""
        return _help_option(super().get_help_option(ctx))

    def format_usage(self, ctx: Any, formatter: Any) -> None:
        """Write the usage line with the prefix of the CLI language."""
        _write_usage(self, ctx, formatter)


class ObserwatorCommand(TyperCommand):
    """
    Command of the ``obserwator`` tree (``@app.command(cls=ObserwatorCommand)``).

    Its ``--help`` option and usage line are in the CLI language, also for
    the commands outside the catalog (``obserwator version``, ``obserwator admin …``).
    """

    def get_help_option(self, ctx: Any) -> Any:
        """Return the ``--help`` option described in the CLI language."""
        return _help_option(super().get_help_option(ctx))

    def format_usage(self, ctx: Any, formatter: Any) -> None:
        """Write the usage line with the prefix of the CLI language."""
        _write_usage(self, ctx, formatter)


class _CatalogCommand(ObserwatorCommand):
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
        _print_notice("warning", message("cli.interrupt_requested"))

    previous = signal.signal(signal.SIGINT, handle)
    try:
        yield requested
    finally:
        signal.signal(signal.SIGINT, previous)


def _run(command: str, options: dict[str, object], *, check: bool) -> int:
    """
    Run (``check``: plan) one catalog command and print it; return the exit code.

    With ``--json`` the envelope goes to stdout and every distinct notice to
    stderr at once; without it the rendering for a person ends with the
    notices, which reach stderr only before the lines of a stream or an error.
    """
    output = _output()
    shown: dict[Notice, None] = {}  # distinct notices in order of first occurrence
    live = output.json

    def on_notice(notice: Notice) -> None:
        if notice not in shown:
            shown[notice] = None
            if live:
                _print_notice(notice.level, notice.message)

    def flush_notices() -> None:
        nonlocal live
        if not live:
            live = True
            for notice in shown:
                _print_notice(notice.level, notice.message)

    with _interrupt() as requested:
        try:
            # The root of the result is the validated one, the default root included.
            root = validate_command(command, options=options).get("root")
            dispatch = check_command if check else run_command
            outcome = dispatch(
                command,
                options=options,
                on_progress=_print_progress,
                on_notice=on_notice,
                cancel=requested.is_set,
            )
            if isinstance(outcome.result, Iterator):
                flush_notices()
                _write_lines(outcome.result)
            else:
                base = root if isinstance(root, Path) else None
                envelope = outcome.to_json(root=base)
                text = (
                    _json(envelope)
                    if output.json
                    else render(envelope, outcome.notices, output.lang)
                )
                _to_stdout(typer.echo, text)
        except BrokenPipeError:
            _silence_stdout()
            return 0
        except (KeyboardInterrupt, Exception) as exc:
            flush_notices()
            return _failure(exc, command)
    return _EXIT_CODES[outcome.status]


# --- rejestracja -----------------------------------------------------------------------------


def _metavar(option: CommandOption) -> str:
    choices = "|".join(option.choices)
    return choices if choices and len(choices) <= 40 else _HELP.metavars[option.type]


def _option(option: CommandOption) -> inspect.Parameter:
    """Click option of a catalog option: raw text in, defaults left to the catalog."""
    panel = _HELP.required_panel if option.required else _HELP.optional_panel
    help_ = localize(option.help, _LANG)
    annotation: object
    if option.type == "bool" and option.default is True:
        default = typer.Option(
            None,
            f"{option.flag}/--no-{option.flag[2:]}",
            help=help_,
            rich_help_panel=panel,
        )
        annotation = bool | None
    elif option.type == "bool":
        default = typer.Option(
            False, option.flag, *option.aliases, help=help_, rich_help_panel=panel
        )
        annotation = bool
    else:
        default = typer.Option(
            None,
            option.flag,
            *option.aliases,
            help=help_,
            metavar=_metavar(option),
            rich_help_panel=panel,
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
            False, f"--{name}", help=help_, rich_help_panel=_HELP.optional_panel
        ),
        annotation=bool,
    )


def _lang_option() -> inspect.Parameter:
    """``--lang`` of a command without the catalog option ``lang`` (AGI-3.4)."""
    return inspect.Parameter(
        "lang",
        inspect.Parameter.KEYWORD_ONLY,
        default=typer.Option(
            None,
            _LANG_FLAG,
            help=_HELP.lang,
            metavar="|".join(LANGS),
            rich_help_panel=_HELP.optional_panel,
        ),
        annotation=str | None,
    )


def _has_lang_option(spec: DataCommand) -> bool:
    return any(option.name == "lang" for option in spec.options)


def _parameters(spec: DataCommand) -> list[inspect.Parameter]:
    parameters = [
        inspect.Parameter(
            "ctx", inspect.Parameter.KEYWORD_ONLY, annotation=typer.Context
        ),
        *(_option(option) for option in spec.options),
    ]
    if spec.check is not None:
        parameters.append(_flag("check", _HELP.check))
    parameters.append(_flag("json", _HELP.json))
    if not _has_lang_option(spec):
        parameters.append(_lang_option())
    parameters.append(_flag("schema", _HELP.schema))
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


def _set_output(spec: DataCommand, values: dict[str, Any]) -> int:
    """
    Take ``--json`` and ``--lang`` of a parsed call as its output; return 0.

    ``--lang`` of a command without the catalog option ``lang`` leaves
    ``values``; when it is no language the call ends with ``validation_error``
    (its exit code is returned). A catalog ``lang`` that is no language is
    left to the validation of the call.
    """
    own = _has_lang_option(spec)
    given = values.get("lang") if own else values.pop("lang")
    valid = given is None or given in LANGS
    lang = cast(Lang, given) if given and valid else _LANG
    _OUTPUT.set(_Output(bool(values.pop("json")), lang))
    if valid or own:
        return 0
    return _error_line(
        "validation_error",
        message(
            "commands.invalid_value_option_allowed",
            text=given,
            name="lang",
            choices=", ".join(LANGS),
        ),
        {"option": "lang", "value": given, "allowed": list(LANGS)},
        command=spec.name,
    )


def _call(spec: DataCommand, values: dict[str, Any]) -> int:
    """Run the parsed call (``--schema``: describe the command); return the exit code."""
    output = _output()
    check = bool(values.pop("check", False))
    # For a person the description commands describe in the language of the call.
    if values.pop("schema"):
        options: dict[str, object] = {"command": spec.name}
        if not output.json:
            options["lang"] = output.lang
        return _run("commands schema", options, check=False)
    options = _given(spec, values)
    if not output.json and _has_lang_option(spec) and spec.result != "stream":
        options.setdefault("lang", output.lang)
    return _run(spec.name, options, check=check)


def _register(group: typer.Typer, spec: DataCommand) -> None:
    def callback(ctx: typer.Context, **values: Any) -> None:
        code = _set_output(spec, values) or _call(spec, values)
        if code:
            raise typer.Exit(code)

    cast(Any, callback).__signature__ = inspect.Signature(_parameters(spec))
    name = spec.name.split(" ", 1)[1]
    description = localize(spec.description, _LANG)
    group.command(name, cls=_CatalogCommand, help=description, short_help=description)(
        callback
    )


def register_catalog(app: typer.Typer, /) -> None:
    """
    Register every catalog group and command under the ``obserwator`` application.

    Each group of the catalog (``datasets``, ``stations``, ``current``,
    ``pmaxtp``, ``store``, ``series``, ``commands``) becomes a
    subcommand group with the catalog group description as its help, holding
    every catalog command of that group. Command help is the catalog
    description in the language of ``OBSERWATOR_LANG``; options are the catalog
    flags and aliases (required ones in the "Opcje wymagane" panel, in
    English "Required options"), ``--root`` defaults to the store root of
    ``OBSERWATOR_ROOT``, ``[obserwator] root`` or ``<data_dir>/obserwator`` (only under ``env_root_when`` of the command),
    list options take comma-separated values or
    a repeated flag, ``--check`` exists only for commands with a check twin,
    ``--json`` and ``--schema`` for every command and ``--lang`` (the
    language of the human rendering) for every command, as the catalog option
    of the description commands.

    Parameters
    ----------
    app : typer.Typer
        The ``obserwator`` application, created with ``cls=ObserwatorGroup`` so that Click
        syntax errors end with the JSON error line.
    """
    groups = {
        name: typer.Typer(help=text, cls=ObserwatorSubgroup)
        for name, text in _GROUPS.items()
    }
    for spec in data_commands():
        _register(groups[spec.name.split(" ", 1)[0]], spec)
    for name, group in groups.items():
        app.add_typer(group, name=name, help=_GROUPS[name])
