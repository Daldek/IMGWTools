"""
RFC 9457 problem documents of the REST API (spec §13.5, ADR-002 D7).

Every error answer of the application is an ``application/problem+json``
document with ``type``, ``title``, ``status``, ``detail``, ``instance``,
``code`` and ``details``: library errors by their ``code``, pydantic request
validation (400 ``validation_error``), unknown routes (404 ``not_found``),
wrong methods (405 ``method_not_allowed``), file-system errors (``io_error``)
and program errors (``internal_error``). Code, title and HTTP status come from
the error registry `ERROR_CODES`, so REST reports an error exactly as the CLI
and the web GUI do. The title and the detail of a catalog message are in the
language of ``Accept-Language`` (`accept_language`, English by default, AGI-6.4);
any other detail stays as the raiser wrote it. Texts and details never contain absolute
server paths (rule T21): `hide_server_paths` writes them relative to the server
directory that contains them.
"""

import tempfile
from collections.abc import Callable, Coroutine, Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from imgwtools._jsonable import jsonable
from imgwtools.config import settings
from imgwtools.exceptions import ERROR_CODES, ErrorCode, IMGWError, describe_os_error
from imgwtools.messages import LANGS, Lang, localize, message

__all__ = [
    "EXCEPTION_HANDLERS",
    "PROBLEM_MEDIA_TYPE",
    "PROBLEM_RESPONSES",
    "PROBLEM_SCHEMA",
    "accept_language",
    "hide_server_paths",
    "problem_response",
]

PROBLEM_MEDIA_TYPE = "application/problem+json"
"""Media type of every error answer."""

PROBLEM_SCHEMA: dict[str, object] = {
    "title": "problem+json IMGWTools",
    "type": "object",
    "required": ["type", "title", "status", "detail", "code", "details"],
    "properties": {
        "type": {"type": "string", "pattern": "^urn:imgwtools:error:[a-z_]+$"},
        "title": {"type": "string", "minLength": 1},
        "status": {"type": "integer", "minimum": 400, "maximum": 599},
        "detail": {"type": "string", "minLength": 1},
        "instance": {"type": "string"},
        "code": {
            "enum": [code for code, spec in ERROR_CODES.items() if spec.http_status]
        },
        "details": {"type": "object"},
    },
    "additionalProperties": False,
}
"""JSON Schema of a problem document (spec §13.5), published in OpenAPI."""

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    "4XX": {
        "description": "Request error: validation (400), no permission to write "
        "(403), no object or route (404), method not allowed (405), conflict (409)",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA}},
    },
    "5XX": {
        "description": "Server error: invalid data or file system (500), the IMGW "
        "source unavailable (502), the store unavailable or a missing dependency (503)",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA}},
    },
}
"""OpenAPI error answers of every catalog route (they replace FastAPI's 422)."""

# Statuses raised by routing, static files or FastAPI itself.
_HTTP_CODES: dict[int, ErrorCode] = {
    400: "validation_error",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    502: "source_unavailable",
}
_VALIDATION_DETAIL = message("api.invalid_parameters_or_body")
_INTERNAL_DETAIL = message("api.unexpected_server_error")


def _weight(parameters: list[str]) -> float | None:
    """``q`` of an ``Accept-Language`` item: 1 without it, None when malformed."""
    for parameter in parameters:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "q":
            try:
                weight = float(value.strip())
            except ValueError:
                return None
            return weight if 0.0 <= weight <= 1.0 else None
    return 1.0


def accept_language(header: str | None, /) -> Lang:
    """
    Choose the catalog language of an ``Accept-Language`` header.

    Items are separated by commas and weighted by ``q`` (1 without it,
    RFC 9110 §12.5.4); a language range matches by its first subtag
    (``en-GB`` → ``en``). The highest positive weight among ``pl`` and ``en``
    wins, the item listed first on a tie. The header is only a hint: no
    header, no matching item and malformed items give English (AGI-6.4,
    AGI-9.2), never an error.

    Parameters
    ----------
    header : str or None
        Value of the ``Accept-Language`` request header, or None.

    Returns
    -------
    {"pl", "en"}
        Language of the texts of the answer.
    """
    chosen: Lang = "en"
    best = 0.0
    for item in (header or "").split(","):
        tag, *parameters = item.split(";")
        primary = tag.strip().lower().split("-", 1)[0]
        weight = _weight(parameters) if primary in LANGS else None
        if weight is not None and weight > best:
            chosen, best = cast(Lang, primary), weight
    return chosen


def _working_directory() -> Path | None:
    try:
        return Path.cwd()
    except OSError:  # working directory removed under the running server
        return None


def _server_directories() -> list[Path]:
    """Absolute server directories hidden in answers, the most nested first."""
    working = _working_directory()
    found: dict[str, Path] = {}
    for directory in (
        settings.store_root,
        settings.user_locations_dir,
        settings.reference_dir,
        settings.data_dir,
        settings.cache_dir,
        Path(tempfile.gettempdir()),
        working,
    ):
        if directory is None or (working is None and not directory.is_absolute()):
            continue
        absolute = directory if working is None else working / directory
        found.setdefault(str(absolute), absolute)
    return sorted(found.values(), key=lambda path: len(str(path)), reverse=True)


def hide_server_paths(value: object) -> object:
    """
    Rewrite absolute server paths in a JSON value as paths relative to them.

    The hidden directories are ``IMGW_STORE_ROOT``, ``IMGW_USER_LOCATIONS_DIR``,
    ``IMGW_REFERENCE_DIR``, ``IMGW_DATA_DIR``, ``IMGW_CACHE_DIR``, the temporary
    directory and the working directory of the server process (also in their
    resolved form). The most nested
    directory is rewritten first, so ``<dir>/x`` becomes ``x`` and a bare
    ``<dir>`` becomes ``.``, as in the envelope of `CommandResult.to_json`
    with ``server=True``.

    Parameters
    ----------
    value : object
        JSON-compatible value (envelope, problem detail or details).

    Returns
    -------
    object
        The same structure with every text rewritten.
    """
    for directory in _server_directories():
        value = jsonable(value, root=directory, server=True)
    return value


def problem_response(
    request: Request,
    code: ErrorCode,
    detail: str,
    details: Mapping[str, object] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """
    Build the ``application/problem+json`` answer of an error code.

    Parameters
    ----------
    request : Request
        Failed request; its path becomes ``instance``.
    code : ErrorCode
        Registered error code. A code without an HTTP status (``cancelled``:
        REST never cancels) is answered as ``internal_error``.
    detail : str
        Description of this occurrence (a catalog message is rendered in the
        language of the request); the registry title when empty.
    details : Mapping[str, object] or None, optional
        JSON-compatible context (``option``, ``reason``, ``errors``, ...).
    headers : Mapping[str, str] or None, optional
        Extra response headers, e.g. ``Allow`` of a 405 answer.

    Returns
    -------
    JSONResponse
        Problem document with the registry status, title (in the language
        `accept_language` of the request chooses) and ``type``
        ``urn:imgwtools:error:<code>``; texts without absolute server paths.
        ``Content-Language`` names the language of the title and detail and ``Vary``
        includes ``Accept-Language``.
    """
    spec = ERROR_CODES[code]
    if spec.http_status is None:
        spec = ERROR_CODES["internal_error"]
    status = cast(int, spec.http_status)
    language = accept_language(request.headers.get("accept-language"))
    title = localize(spec.title, language)
    body = {
        "type": f"urn:imgwtools:error:{spec.code}",
        "title": title,
        "status": status,
        "detail": cast(str, hide_server_paths(localize(detail, language))) or title,
        "instance": request.url.path,
        "code": spec.code,
        "details": hide_server_paths(dict(details or {})),
    }
    response = JSONResponse(
        body,
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=dict(headers) if headers else None,
    )
    response.headers["Content-Language"] = language
    response.headers.add_vary_header("Accept-Language")
    return response


def _option(location: tuple[int | str, ...]) -> str:
    """Option named by a pydantic error location (``("body", "latitude", ...)``)."""
    if len(location) > 1 and isinstance(location[1], str):
        return location[1]
    return str(location[0]) if location else "body"


async def _imgw_error(request: Request, exc: IMGWError) -> Response:
    return problem_response(request, exc.code, exc.detail, exc.details)


async def _validation_error(request: Request, exc: RequestValidationError) -> Response:
    errors = [
        {"option": _option(tuple(error["loc"])), "message": str(error["msg"])}
        for error in exc.errors()
    ]
    return problem_response(
        request, "validation_error", _VALIDATION_DETAIL, {"errors": errors}
    )


async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
    status = exc.status_code
    code = _HTTP_CODES.get(
        status, "validation_error" if status < 500 else "internal_error"
    )
    detail: str
    if status == 404 and exc.detail == HTTPStatus.NOT_FOUND.phrase:
        detail = message("api.unknown_route")
    elif status == 405:
        detail = message(
            "api.method_not_allowed", method=request.method, path=request.url.path
        )
    else:
        detail = str(exc.detail)
    return problem_response(request, code, detail, headers=exc.headers)


async def _os_error(request: Request, exc: OSError) -> Response:
    return problem_response(request, "io_error", *describe_os_error(exc))


async def _internal_error(request: Request, exc: Exception) -> Response:
    return problem_response(request, "internal_error", _INTERNAL_DETAIL)


EXCEPTION_HANDLERS: dict[
    int | type[Exception], Callable[[Request, Any], Coroutine[Any, Any, Response]]
] = {
    IMGWError: _imgw_error,
    RequestValidationError: _validation_error,
    HTTPException: _http_error,
    StarletteHTTPException: _http_error,
    OSError: _os_error,
    Exception: _internal_error,
}
"""Exception handlers of the application (``FastAPI(exception_handlers=...)``)."""
