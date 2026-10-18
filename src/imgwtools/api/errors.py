"""
RFC 9457 problem documents of the REST API (spec §13.5, ADR-002 D7).

Every error answer of the application is an ``application/problem+json``
document with ``type``, ``title``, ``status``, ``detail``, ``instance``,
``code`` and ``details``: library errors by their ``code``, pydantic request
validation (400 ``validation_error``), unknown routes (404 ``not_found``),
wrong methods (405 ``method_not_allowed``), file-system errors (``io_error``)
and program errors (``internal_error``). Code, title and HTTP status come from
the error registry `ERROR_CODES`, so REST reports an error exactly as the CLI
and the web GUI do. Texts and details never contain absolute server paths
(rule T21): `hide_server_paths` writes them relative to the server directory
that contains them.
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

__all__ = [
    "EXCEPTION_HANDLERS",
    "PROBLEM_MEDIA_TYPE",
    "PROBLEM_RESPONSES",
    "PROBLEM_SCHEMA",
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
        "description": "Błąd żądania: walidacja (400), brak uprawnień do zapisu "
        "(403), brak obiektu lub trasy (404), niedozwolona metoda (405), "
        "konflikt (409)",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA}},
    },
    "5XX": {
        "description": "Błąd serwera: niepoprawne dane lub system plików (500), "
        "źródło IMGW niedostępne (502), magazyn niedostępny lub brak "
        "zależności (503)",
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
_VALIDATION_DETAIL = "Niepoprawne parametry lub ciało żądania"
_INTERNAL_DETAIL = "Nieoczekiwany błąd serwera IMGWTools; szczegóły w dzienniku serwera"


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
        settings.data_dir,
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
    ``IMGW_DATA_DIR``, the temporary directory and the working directory of
    the server process (also in their resolved form). The most nested
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
        Polish description of this occurrence; the registry title when empty.
    details : Mapping[str, object] or None, optional
        JSON-compatible context (``option``, ``reason``, ``errors``, ...).
    headers : Mapping[str, str] or None, optional
        Extra response headers, e.g. ``Allow`` of a 405 answer.

    Returns
    -------
    JSONResponse
        Problem document with the registry status, title and ``type``
        ``urn:imgwtools:error:<code>``; texts without absolute server paths.
    """
    spec = ERROR_CODES[code]
    if spec.http_status is None:
        spec = ERROR_CODES["internal_error"]
    status = cast(int, spec.http_status)
    body = {
        "type": f"urn:imgwtools:error:{spec.code}",
        "title": spec.title,
        "status": status,
        "detail": cast(str, hide_server_paths(detail)) or spec.title,
        "instance": request.url.path,
        "code": spec.code,
        "details": hide_server_paths(dict(details or {})),
    }
    return JSONResponse(
        body,
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=dict(headers) if headers else None,
    )


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
    if status == 404 and exc.detail == HTTPStatus.NOT_FOUND.phrase:
        detail = "Nieznana trasa"
    elif status == 405:
        detail = f"Metoda {request.method} jest niedozwolona dla {request.url.path}"
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
