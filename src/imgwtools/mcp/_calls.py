"""
Calls of the MCP tools (spec 2026-10-19 §6.5–§6.9).

The arguments of a tool are the options of its catalog command; only
`validate_command` normalizes them. stdio (modes ``read`` and ``write``): the
``check`` argument chooses `check_command` over `run_command`, a list command
without ``limit`` gets the default page (a larger ``limit`` than
``IMGW_API_MAX_LIMIT`` is refused), a command with ``root`` gets
``IMGW_STORE_ROOT`` under its ``env_root_when`` (spec §3.5) and a command with
``lang`` the server language. The command runs in a worker thread: progress is
sent as ``notifications/progress`` (only to a request that asked for it) and a
cancellation of the request reaches the command through ``cancel``; the thread
always finishes, so the store stays consistent, and a cancelled request gets no
answer. A server without writes refuses a writing option and ``check: false``
with ``forbidden`` (``details.reason="writes_disabled"``). http: the REST route
of the command answers in this process (ASGI, no network): GET with query
parameters, POST with a JSON body and always ``?check=true``, Polish or English
by ``Accept-Language`` of the server language; REST itself refuses server and
local options.

An envelope ``imgw-result/1`` is ``structuredContent`` and, as compact JSON,
the only text content (the CLI stdout line without its line end); a stream
(``store export``, ``series export``, ``commands guide`` without ``path``) is its
text, at most 256 KiB, with an envelope whose result is ``{format, bytes,
lines}``. An error is ``isError`` with ``{code, title, detail, details}``:
``code``, ``detail`` and ``details`` as in the CLI error line, ``title`` from the
registry in the server language, ``internal_error`` for a program error (its
traceback goes to stderr).
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import traceback
from collections.abc import Callable, Coroutine, Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import anyio
import anyio.from_thread
import anyio.lowlevel
import anyio.to_thread
import mcp.types as types

from imgwtools.commands import Lang, check_command, run_command, validate_command
from imgwtools.exceptions import (
    ERROR_CODES,
    ErrorCode,
    IMGWError,
    IMGWValidationError,
    describe_os_error,
)
from imgwtools.mcp._tools import CatalogTool
from imgwtools.store.types import CommandResult, Progress

__all__ = ["STREAM_LIMIT", "Report", "call_tool"]

STREAM_LIMIT = 262_144
"""Largest stream answered as text content: 256 KiB of UTF-8 (spec §6.6)."""

Report = Callable[[float, float | None, str | None], Coroutine[Any, Any, None]]
"""Progress of the request: ``(progress, total, message)``."""

_LOG = logging.getLogger(__name__)
_INTERNAL = "Błąd wewnętrzny serwera MCP; szczegóły w dzienniku serwera"
_TOO_LARGE = (
    "Wynik przekracza 256 KiB; zawęź wybór, czytaj stronami series read albo "
    "zapisz plik opcją path"
)
_ENABLE_WRITES = (
    "zapis włącza użytkownik: imgw mcp --allow-writes albo IMGW_MCP_ALLOW_WRITES=true"
)


# --- wyniki ----------------------------------------------------------------------------------


def _json(document: object) -> str:
    """Compact JSON of a document, as the CLI prints it."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=str)


def _answer(document: dict[str, Any], text: str | None = None) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(text=_json(document) if text is None else text)],
        structured_content=document,
    )


def _error(
    code: ErrorCode, detail: str, details: object, lang: Lang
) -> types.CallToolResult:
    """Error document of spec §6.7 in the server language."""
    spec = ERROR_CODES[code]
    text = _json(
        {
            "code": code,
            "title": spec.title_en if lang == "en" else spec.title,
            "detail": detail or spec.title,
            "details": details,
        }
    )
    return types.CallToolResult(
        content=[types.TextContent(text=text)],
        structured_content=json.loads(text),
        is_error=True,
    )


def _failure(exc: Exception, lang: Lang) -> types.CallToolResult:
    """Error result of an exception (the CLI error line with a title)."""
    if isinstance(exc, IMGWError):
        return _error(exc.code, exc.detail, dict(exc.details), lang)
    if isinstance(exc, OSError):
        detail, details = describe_os_error(exc)
        return _error("io_error", detail, details, lang)
    traceback.print_exception(exc, file=sys.stderr)
    return _error("internal_error", _INTERNAL, {}, lang)


def _line_count(text: str) -> int:
    return text.count("\n") + int(bool(text) and not text.endswith("\n"))


def _too_large() -> IMGWValidationError:
    return IMGWValidationError(_TOO_LARGE, details={"maximum_bytes": STREAM_LIMIT})


def _format(tool: CatalogTool, options: Mapping[str, object]) -> object:
    """Format of a stream: the given one or the catalog default."""
    if options.get("format") is not None:
        return options["format"]
    return next(
        (option.default for option in tool.command.options if option.name == "format"),
        None,
    )


def _stream(
    tool: CatalogTool,
    outcome: CommandResult[object],
    options: Mapping[str, object],
    root: Path | None,
) -> types.CallToolResult:
    """Text of a stream (at most `STREAM_LIMIT` bytes) with its envelope."""
    lines = cast(Iterator[str], outcome.result)
    chunks: list[str] = []
    size = 0
    for line in lines:
        size += len(line.encode("utf-8"))
        if size > STREAM_LIMIT:
            close = getattr(lines, "close", None)
            if callable(close):
                close()
            raise _too_large()
        chunks.append(line)
    text = "".join(chunks)
    summary = {
        "format": _format(tool, options),
        "bytes": size,
        "lines": _line_count(text),
    }
    envelope = replace(outcome, result=summary).to_json(root=root)
    return _answer(envelope, text)


# --- argumenty -------------------------------------------------------------------------------


def _writes_disabled(tool: CatalogTool, option: str) -> IMGWError:
    if option == "check":
        what = (
            f"komenda {tool.command.name} zwraca wyłącznie plan imgw-plan/1 "
            "(check=true)"
        )
    else:
        what = f"opcja {option} komendy {tool.command.name} zapisuje plik"
    how = "zapis przez HTTP nie istnieje" if tool.mode == "http" else _ENABLE_WRITES
    return IMGWError(
        f"Serwer MCP działa bez zapisu: {what}; {how}",
        code="forbidden",
        details={"reason": "writes_disabled", "option": option},
    )


def _flag(value: object) -> bool:
    """Value of the ``check`` argument: a boolean or the text true/false."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise IMGWValidationError(
        f"Argument check musi mieć wartość logiczną true albo false: {value!r}",
        details={"option": "check", "value": value, "allowed": [True, False]},
    )


def _check(tool: CatalogTool, options: dict[str, object]) -> bool:
    """Take ``check`` out of the options; refuse ``false`` when it is fixed."""
    if tool.check is None:
        return False  # no argument: a given check is an unknown option
    value = options.pop("check", None)
    check = tool.check if value is None else _flag(value)
    if tool.fixed and not check:
        raise _writes_disabled(tool, "check")
    return check


def _environment_root(tool: CatalogTool, options: Mapping[str, object]) -> bool:
    """Whether the options meet ``env_root_when`` (spec §3.5, as in the CLI)."""
    defaults = {option.name: option.default for option in tool.command.options}
    return all(
        str(options.get(name, defaults.get(name))).strip() == value
        for name, value in tool.command.env_root_when.items()
    )


def _options(
    tool: CatalogTool, arguments: Mapping[str, Any]
) -> tuple[dict[str, object], bool]:
    """Catalog options of a stdio call and whether it only plans."""
    options: dict[str, object] = dict(arguments)
    refused = next(
        (
            name
            for name, value in options.items()
            if name in tool.refused and value is not None
        ),
        None,
    )
    if refused is not None:
        raise _writes_disabled(tool, refused)
    check = _check(tool, options)
    if tool.limit is not None and options.get("limit") is None:
        options["limit"] = tool.limit[0]
    if (
        tool.root is not None
        and options.get("root") is None
        and _environment_root(tool, options)
    ):
        options["root"] = tool.root
    if options.get("lang") is None and any(
        option.name == "lang" for option in tool.command.options
    ):
        options["lang"] = tool.lang
    return options, check


def _page_limit(tool: CatalogTool, options: Mapping[str, object]) -> None:
    """Refuse a page larger than ``IMGW_API_MAX_LIMIT`` (spec §6.4 p. 5)."""
    limit = options.get("limit")
    if tool.limit is None or not isinstance(limit, int):
        return
    maximum = tool.limit[1]
    if limit > maximum:
        raise IMGWValidationError(
            f"Opcja limit może wynosić co najwyżej {maximum} (IMGW_API_MAX_LIMIT): "
            f"{limit}",
            details={"option": "limit", "value": limit, "maximum": maximum},
        )


# --- stdio -----------------------------------------------------------------------------------


def _run(
    tool: CatalogTool,
    options: Mapping[str, object],
    check: bool,
    report: Report,
    cancelled: threading.Event,
) -> types.CallToolResult:
    """Run (``check``: plan) the command in a worker thread; never raise."""

    def progress(update: Progress) -> None:
        text = update.message or f"{update.unit}: {update.status}"
        message = f"[{update.current}/{update.total}] {text}"
        try:
            anyio.from_thread.run(report, update.current, update.total, message)
        except Exception:  # progress is a hint: its loss never stops the command
            _LOG.debug("Postęp nie dotarł do klienta MCP", exc_info=True)

    name = tool.command.name
    try:
        normalized = validate_command(name, options=options)
        if not check:
            _page_limit(tool, normalized)
        dispatch = check_command if check else run_command
        outcome: CommandResult[Any] = dispatch(
            name, options=normalized, on_progress=progress, cancel=cancelled.is_set
        )
        root = normalized.get("root")
        base = root if isinstance(root, Path) else None
        if isinstance(outcome.result, Iterator):
            return _stream(tool, outcome, normalized, base)
        return _answer(outcome.to_json(root=base))
    except Exception as exc:
        return _failure(exc, tool.lang)


async def _watch(cancelled: threading.Event) -> None:
    """Set ``cancelled`` once the request is cancelled; the worker reads it."""
    try:
        await anyio.sleep_forever()
    except anyio.get_cancelled_exc_class():
        cancelled.set()
        raise


async def _in_thread(
    work: Callable[[threading.Event], types.CallToolResult],
) -> types.CallToolResult:
    """
    Run ``work`` in a worker thread to its end, forwarding a cancellation.

    The cancellation of the request sets the event given to ``work``; the
    request waits for the thread anyway (a worker thread ignores cancellation,
    so no write is cut off) and is then cancelled, so it gets no answer.
    """
    cancelled = threading.Event()
    result: types.CallToolResult | None = None
    async with anyio.create_task_group() as group:
        group.start_soon(_watch, cancelled)
        result = await anyio.to_thread.run_sync(work, cancelled)
        group.cancel_scope.cancel()
    await anyio.lowlevel.checkpoint_if_cancelled()
    assert result is not None
    return result


# --- http ------------------------------------------------------------------------------------


def _query_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Mapping | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _query(options: Mapping[str, object]) -> str:
    """Query string of a GET route: a list repeats its parameter."""
    pairs: list[tuple[str, str]] = []
    for name, value in options.items():
        if value is None:
            continue
        items = cast(list[object], value) if isinstance(value, list) else [value]
        pairs += [(name, _query_text(item)) for item in items]
    return urlencode(pairs)


async def _asgi(
    method: str, path: str, query: str, body: bytes, lang: str, limit: int | None
) -> tuple[int, dict[str, str], bytes, bool]:
    """
    Request to the REST application of this process.

    Returns the status, the headers (lower-case names), the body and whether
    the reading stopped at ``limit`` bytes (the client leaves the response,
    so the streamed result is not produced further).
    """
    from imgwtools.api.main import app  # the REST app of this server (api extra)

    headers = [(b"host", b"imgwtools"), (b"accept-language", lang.encode("ascii"))]
    if method == "POST":
        headers += [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 0),
        "server": ("imgwtools", 80),
    }
    stop = anyio.Event()
    received = False
    status = 500
    answer: dict[str, str] = {}
    chunks: list[bytes] = []
    size = 0

    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await stop.wait()
        return {"type": "http.disconnect"}

    async def send(message: Mapping[str, Any]) -> None:
        nonlocal status, size
        if message["type"] == "http.response.start":
            status = cast(int, message["status"])
            answer.update(
                (key.decode("latin-1").lower(), value.decode("latin-1"))
                for key, value in cast(list[tuple[bytes, bytes]], message["headers"])
            )
        elif message["type"] == "http.response.body" and not stop.is_set():
            chunk = cast(bytes, message.get("body", b""))
            size += len(chunk)
            if limit is not None and size > limit:
                stop.set()  # the reader leaves: the stream stops
            else:
                chunks.append(chunk)

    await app(scope, receive, send)
    return status, answer, b"".join(chunks), stop.is_set()


async def _route(
    tool: CatalogTool, arguments: Mapping[str, Any]
) -> types.CallToolResult:
    """Call of mode ``http``: the REST route answers (spec §6.9)."""
    options: dict[str, object] = dict(arguments)
    _check(tool, options)  # POST routes only plan (?check=true)
    if tool.limit is not None and options.get("limit") is None:
        options["limit"] = tool.limit[0]
    method, path = cast(tuple[str, str], tool.route)
    stream = tool.command.result == "stream"
    if method == "GET":
        query, body = _query(options), b""
    else:
        query, body = "check=true", json.dumps(options, ensure_ascii=False).encode()
    status, headers, data, stopped = await _asgi(
        method, path, query, body, tool.lang, STREAM_LIMIT if stream else None
    )
    media = headers.get("content-type", "")
    if media.startswith("application/problem+json"):
        problem = json.loads(data)
        return _error(problem["code"], problem["detail"], problem["details"], tool.lang)
    if status != 200:
        raise RuntimeError(f"Trasa REST {method} {path} odpowiedziała {status} {media}")
    if media.startswith("application/json"):
        text = data.decode("utf-8")
        return _answer(json.loads(text), text)
    if stopped:
        raise _too_large()
    text = data.decode("utf-8")
    envelope = {
        "schema": "imgw-result/1",
        "command": tool.command.name,
        "check": False,
        "status": headers["x-imgw-status"],
        "result": {
            "format": _format(tool, options),
            "bytes": len(data),
            "lines": _line_count(text),
        },
        "notices": json.loads(headers["x-imgw-notices"]),
    }
    return _answer(envelope, text)


# --- wejście ---------------------------------------------------------------------------------


async def call_tool(
    tool: CatalogTool, arguments: Mapping[str, Any], *, report: Report
) -> types.CallToolResult:
    """
    Call one tool: run its catalog command and answer with a tool result.

    Parameters
    ----------
    tool : CatalogTool
        The called tool.
    arguments : Mapping[str, Any]
        Arguments of the call (catalog options and ``check``).
    report : Report
        Progress of the request (a no-op unless the client asked for it).

    Returns
    -------
    mcp.types.CallToolResult
        The envelope, or the text of a stream with its envelope, or an error
        document with ``isError``.
    """
    try:
        if tool.mode == "http":
            return await _route(tool, arguments)
        options, check = _options(tool, arguments)
    except Exception as exc:
        return _failure(exc, tool.lang)

    def work(cancelled: threading.Event) -> types.CallToolResult:
        return _run(tool, options, check, report, cancelled)

    return await _in_thread(work)
