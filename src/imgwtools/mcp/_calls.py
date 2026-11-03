"""
Calls of the MCP tools (spec 2026-10-19 §6.5–§6.9).

The arguments of a tool are the options of its catalog command; only
`validate_command` normalizes them. stdio (modes ``read`` and ``write``): the
``check`` argument chooses `check_command` over `run_command`, a list command
without ``limit`` gets the default page (a larger ``limit`` than
``IMGW_API_MAX_LIMIT`` is refused), a command without ``root`` gets
the default store root (`validate_command`), a path outside the ``--allow-dir``
directories and a write without any are ``forbidden`` (DEV-19.3, AGI-5.8) and a
command with ``lang`` English. The command runs in a worker thread: progress is
sent as ``notifications/progress`` (only to a request that asked for it) and a
cancellation of the request reaches the command through ``cancel``; the thread
always finishes, so the store stays consistent, and a cancelled request gets no
answer. A server without writes refuses a writing option and ``check: false``
with ``forbidden`` (``details.reason="writes_disabled"``). http: the REST route
of the command answers in this process (ASGI, no network): GET with query
parameters, POST with a JSON body and always ``?check=true``, in English
(``Accept-Language: en``); REST itself refuses server and local options.

An envelope ``imgw-result/1`` is ``structuredContent`` and, as compact JSON,
the only text content (the CLI stdout line without its line end); a stream
(``store export``, ``series export``, ``commands guide`` without ``output``) is its
text, at most 256 KiB, with an envelope whose result is ``{format, bytes,
lines}``. An error is ``isError`` with ``{code, title, detail, details}``:
``code``, ``detail`` and ``details`` as in the CLI error line, ``title`` from the
registry, all in English (AGI-9.2), ``internal_error`` for a program error (its
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

from imgwtools.commands import check_command, run_command, validate_command
from imgwtools.exceptions import (
    ERROR_CODES,
    ErrorCode,
    IMGWError,
    IMGWValidationError,
    describe_os_error,
)
from imgwtools.mcp._tools import CatalogTool
from imgwtools.messages import localize, message
from imgwtools.store.types import CommandResult, Progress

__all__ = ["STREAM_LIMIT", "Report", "call_tool"]

STREAM_LIMIT = 262_144
"""Largest stream answered as text content: 256 KiB of UTF-8 (spec §6.6)."""

Report = Callable[[float, float | None, str | None], Coroutine[Any, Any, None]]
"""Progress of the request: ``(progress, total, message)``."""

_LOG = logging.getLogger(__name__)
_INTERNAL = message("mcp.internal_error")
_TOO_LARGE = message("mcp.result_exceeds_256_kib_narrow")
_ENABLE_WRITES = message("mcp.user_enables_writes_imgw_mcp")


# --- results ---------------------------------------------------------------------------------


def _json(document: object) -> str:
    """Compact JSON of a document, as the CLI prints it."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=str)


def _answer(document: dict[str, Any], text: str | None = None) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(text=_json(document) if text is None else text)],
        structured_content=document,
    )


def _error(code: ErrorCode, detail: str, details: object) -> types.CallToolResult:
    """Error document of spec §6.7, in English like the CLI error line."""
    spec = ERROR_CODES[code]
    text = _json(
        {
            "code": code,
            "title": localize(spec.title, "en"),
            "detail": localize(detail, "en") or localize(spec.title, "en"),
            "details": details,
        }
    )
    return types.CallToolResult(
        content=[types.TextContent(text=text)],
        structured_content=json.loads(text),
        is_error=True,
    )


def _failure(exc: Exception) -> types.CallToolResult:
    """Error result of an exception (the CLI error line with a title)."""
    if isinstance(exc, IMGWError):
        return _error(exc.code, exc.detail, dict(exc.details))
    if isinstance(exc, OSError):
        detail, details = describe_os_error(exc)
        return _error("io_error", detail, details)
    traceback.print_exception(exc, file=sys.stderr)
    return _error("internal_error", _INTERNAL, {})


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


# --- arguments -------------------------------------------------------------------------------


def _writes_disabled(tool: CatalogTool, option: str) -> IMGWError:
    if option == "check":
        what = message("mcp.command_returns_only_imgw_plan", name=tool.command.name)
    else:
        what = message(
            "mcp.option_command_writes_file", option=option, name=tool.command.name
        )
    how = (
        message("mcp.writing_over_http_does_not")
        if tool.mode == "http"
        else _ENABLE_WRITES
    )
    return IMGWError(
        message("mcp.mcp_server_runs_without_writes", what=what, how=how),
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
        message("mcp.argument_check_must_true_false", value=value),
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


def _confine(
    tool: CatalogTool,
    normalized: Mapping[str, object],
    check: bool,
    allow_dirs: tuple[Path, ...],
) -> None:
    """
    Keep the paths of a call inside the ``--allow-dir`` directories (DEV-19.3).

    Without a directory a writing command, or a command given a writing option
    (``output`` of an export), may only plan; with directories every path
    option, the default root included, must lie inside one of them.
    """
    spec = tool.command
    if not allow_dirs:
        writes = spec.writes != "none" or any(
            option.writes != "none" and option.name in normalized
            for option in spec.options
        )
        if not check and writes:
            raise IMGWError(
                message("mcp.write_needs_allow_dir", name=spec.name),
                code="forbidden",
                details={"reason": "no_allowed_dir", "option": "check"},
            )
        return
    for option in spec.options:
        value = normalized.get(option.name)
        if option.type != "path" or not isinstance(value, Path):
            continue
        if not any(value.resolve().is_relative_to(allowed) for allowed in allow_dirs):
            raise IMGWError(
                message(
                    "mcp.path_outside_allowed_dirs",
                    option=option.name,
                    path=value,
                    allowed=", ".join(str(allowed) for allowed in allow_dirs),
                ),
                code="forbidden",
                details={
                    "reason": "outside_allowed_dirs",
                    "option": option.name,
                    "value": str(value),
                    "allowed": [str(allowed) for allowed in allow_dirs],
                },
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
    return options, check


def _page_limit(tool: CatalogTool, options: Mapping[str, object]) -> None:
    """Refuse a page larger than ``IMGW_API_MAX_LIMIT`` (spec §6.4 p. 5)."""
    limit = options.get("limit")
    if tool.limit is None or not isinstance(limit, int):
        return
    maximum = tool.limit[1]
    if limit > maximum:
        raise IMGWValidationError(
            message("mcp.option_limit_may_most_imgw", maximum=maximum, limit=limit),
            details={"option": "limit", "value": limit, "maximum": maximum},
        )


# --- stdio -----------------------------------------------------------------------------------


def _run(
    tool: CatalogTool,
    options: Mapping[str, object],
    check: bool,
    report: Report,
    cancelled: threading.Event,
    allow_dirs: tuple[Path, ...] = (),
) -> types.CallToolResult:
    """Run (``check``: plan) the command in a worker thread; never raise."""

    def progress(update: Progress) -> None:
        text = update.message or f"{update.unit}: {update.status}"
        message = f"[{update.current}/{update.total}] {text}"
        try:
            anyio.from_thread.run(report, update.current, update.total, message)
        except Exception:  # progress is a hint: its loss never stops the command
            _LOG.debug("Progress did not reach the MCP client", exc_info=True)

    name = tool.command.name
    try:
        normalized = validate_command(name, options=options)
        _confine(tool, normalized, check, allow_dirs)
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
        return _failure(exc)


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
    method: str, path: str, query: str, body: bytes, limit: int | None
) -> tuple[int, dict[str, str], bytes, bool]:
    """
    Request to the REST application of this process.

    Returns the status, the headers (lower-case names), the body and whether
    the reading stopped at ``limit`` bytes (the client leaves the response,
    so the streamed result is not produced further).
    """
    from imgwtools.api.main import app  # the REST app of this server (api extra)

    headers = [(b"host", b"imgwtools"), (b"accept-language", b"en")]
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
        method, path, query, body, STREAM_LIMIT if stream else None
    )
    media = headers.get("content-type", "")
    if media.startswith("application/problem+json"):
        problem = json.loads(data)
        return _error(problem["code"], problem["detail"], problem["details"])
    if status != 200:
        raise RuntimeError(f"The REST route {method} {path} answered {status} {media}")
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


# --- entry point -----------------------------------------------------------------------------


async def call_tool(
    tool: CatalogTool,
    arguments: Mapping[str, Any],
    *,
    report: Report,
    allow_dirs: tuple[Path, ...] = (),
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
    allow_dirs : tuple of pathlib.Path, optional
        Resolved ``--allow-dir`` directories of the server (DEV-19.3).

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
        return _failure(exc)

    def work(cancelled: threading.Event) -> types.CallToolResult:
        return _run(tool, options, check, report, cancelled, allow_dirs)

    return await _in_thread(work)
