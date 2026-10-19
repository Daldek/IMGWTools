"""
Exceptions and the closed error-code registry of IMGWTools.

Every :class:`IMGWError` carries a machine-readable ``code`` from
:data:`ERROR_CODES`, a Polish human-readable ``detail`` and JSON-compatible
``details``. Each class has a default code; a raise site may pass another
registered code with ``code=``. The registry maps every code to its Polish
and English title, CLI exit code and HTTP status (spec §13.5), so the CLI,
REST and web adapters report the same error the same way.
"""

from __future__ import annotations

import copy
import errno
import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal

ErrorCode = Literal[
    "validation_error",
    "not_found",
    "conflict",
    "source_unavailable",
    "missing_dependency",
    "data_error",
    "store_unavailable",
    "io_error",
    "cancelled",
    "forbidden",
    "method_not_allowed",
    "internal_error",
]


@dataclass(frozen=True)
class ErrorSpec:
    """
    Registry entry describing one error code.

    Attributes
    ----------
    code : ErrorCode
        Machine-readable error code.
    title : str
        Short Polish title (``title`` of an RFC 9457 problem document).
    exit_code : int or None
        CLI exit code, or ``None`` when the CLI never reports this code.
    http_status : int or None
        HTTP status, or ``None`` when REST never reports this code.
    title_en : str
        Short English title, chosen instead of ``title`` for English
        (``Accept-Language`` of REST, ``command_schema(lang="en")``).
    """

    code: ErrorCode
    title: str
    exit_code: int | None
    http_status: int | None
    title_en: str


ERROR_CODES: Mapping[ErrorCode, ErrorSpec] = MappingProxyType(
    {
        spec.code: spec
        for spec in (
            ErrorSpec(
                "validation_error",
                "Nieprawidłowe dane wejściowe",
                2,
                400,
                title_en="Invalid input",
            ),
            ErrorSpec("not_found", "Nie znaleziono", 3, 404, title_en="Not found"),
            ErrorSpec("conflict", "Konflikt stanu", 4, 409, title_en="State conflict"),
            ErrorSpec(
                "source_unavailable",
                "Źródło danych niedostępne",
                5,
                502,
                title_en="Data source unavailable",
            ),
            ErrorSpec(
                "missing_dependency",
                "Brak opcjonalnej zależności",
                6,
                503,
                title_en="Missing optional dependency",
            ),
            ErrorSpec(
                "data_error", "Niepoprawne dane", 7, 500, title_en="Invalid data"
            ),
            ErrorSpec(
                "store_unavailable",
                "Magazyn niedostępny",
                8,
                503,
                title_en="Store unavailable",
            ),
            ErrorSpec(
                "io_error", "Błąd systemu plików", 9, 500, title_en="File system error"
            ),
            ErrorSpec(
                "cancelled",
                "Operację anulowano",
                130,
                None,
                title_en="Operation cancelled",
            ),
            ErrorSpec(
                "forbidden",
                "Brak uprawnień do zapisu",
                None,
                403,
                title_en="Write not permitted",
            ),
            ErrorSpec(
                "method_not_allowed",
                "Niedozwolona metoda HTTP",
                None,
                405,
                title_en="HTTP method not allowed",
            ),
            ErrorSpec(
                "internal_error", "Błąd wewnętrzny", 1, 500, title_en="Internal error"
            ),
        )
    }
)
"""Closed registry of error codes (spec §13.5), keyed by code."""


class IMGWError(Exception):
    """
    Base exception for all IMGWTools errors.

    Parameters
    ----------
    message : str
        Polish human-readable description; becomes ``detail`` and ``str(exc)``.
    code : ErrorCode or None, optional
        Error code from :data:`ERROR_CODES`; ``None`` selects the class
        default (:attr:`default_code`).
    details : Mapping[str, object] or None, optional
        JSON-compatible context (e.g. ``option``, ``value``, ``allowed``);
        stored as an independent deep copy.

    Attributes
    ----------
    default_code : ErrorCode
        Code used when the raise site does not pass ``code``.
    code : ErrorCode
        Registered error code of this instance.
    detail : str
        The message, equal to ``str(exc)``.
    details : Mapping[str, object]
        Copy of the given context; empty when none was given.

    Raises
    ------
    ValueError
        If ``code`` is not a key of :data:`ERROR_CODES`.
    """

    default_code: ClassVar[ErrorCode] = "internal_error"

    code: ErrorCode
    detail: str
    details: Mapping[str, object]

    def __init__(
        self,
        message: str,
        /,
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        resolved = self.default_code if code is None else code
        if resolved not in ERROR_CODES:
            raise ValueError(
                f"Nieznany kod błędu {resolved!r}; dozwolone: {', '.join(ERROR_CODES)}"
            )
        super().__init__(message)
        self.code = resolved
        self.detail = message
        self.details = copy.deepcopy(dict(details or {}))


class IMGWConnectionError(IMGWError):
    """
    Connection to a data provider's server failed (timeout, network, HTTP 4xx/5xx).

    Default code: ``source_unavailable``.
    """

    default_code: ClassVar[ErrorCode] = "source_unavailable"


class IMGWDataError(IMGWError):
    """
    Provider data or a stored version is invalid (format, SHA, size, JSON, CSV, ZIP).

    Default code: ``data_error``; a stored file the system cannot read is
    raised by `io_error` with ``code="io_error"``.
    """

    default_code: ClassVar[ErrorCode] = "data_error"


class IMGWValidationError(IMGWError):
    """
    Invalid input: options, values, combinations or unsafe paths.

    Default code: ``validation_error``.
    """

    default_code: ClassVar[ErrorCode] = "validation_error"


class IMGWStoreError(IMGWError):
    """
    Store root without a supported marker or schema.

    Default code: ``store_unavailable``; missing versions, sidecars, files,
    station lists, cells or series are raised with ``code="not_found"``.
    """

    default_code: ClassVar[ErrorCode] = "store_unavailable"


class IMGWStoreConflictError(IMGWStoreError):
    """
    Version collision, race, busy lock or a refused publication.

    Default code: ``conflict``.
    """

    default_code: ClassVar[ErrorCode] = "conflict"


class IMGWStoreDependencyError(IMGWStoreError):
    """
    Optional Parquet dependency ``pyarrow>=15`` is missing.

    Default code: ``missing_dependency``.

    Parameters
    ----------
    message : str, optional
        Polish description; defaults to the install instruction.
    code : ErrorCode or None, optional
        Error code overriding ``missing_dependency``.
    details : Mapping[str, object] or None, optional
        JSON-compatible context.
    """

    default_code: ClassVar[ErrorCode] = "missing_dependency"

    def __init__(
        self,
        message: str = "Zainstaluj dodatek: pip install imgwtools[store]",
        /,
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


class IMGWProjectError(IMGWError):
    """
    Invalid project manifest, lock or pinned version.

    Default code: ``validation_error``; a missing manifest is raised with
    ``code="not_found"``.
    """

    default_code: ClassVar[ErrorCode] = "validation_error"


class IMGWCancelledError(IMGWError):
    """
    Operation interrupted by ``cancel`` or Ctrl+C without a partial report.

    Default code: ``cancelled``.
    """

    default_code: ClassVar[ErrorCode] = "cancelled"


_OS_REASONS = {
    errno.EACCES: "brak uprawnień",
    errno.EPERM: "operacja niedozwolona",
    errno.ENOENT: "nie ma takiego pliku ani katalogu",
    errno.ENOTDIR: "element ścieżki nie jest katalogiem",
    errno.EISDIR: "ścieżka jest katalogiem",
    errno.EEXIST: "plik już istnieje",
    errno.ENOSPC: "brak miejsca na urządzeniu",
    errno.EROFS: "system plików tylko do odczytu",
}


def describe_os_error(exc: OSError, /) -> tuple[str, dict[str, object]]:
    """
    Describe a file-system error as an ``io_error`` (spec §13.5).

    The CLI error line, the REST problem document and `io_error` share this
    text, so every interface reports the same file-system error alike.

    Parameters
    ----------
    exc : OSError
        File-system error.

    Returns
    -------
    tuple[str, dict[str, object]]
        Polish ``detail`` (``Błąd systemu plików: <reason>[: <path>]``, the
        reason in Polish for common ``errno`` values) and ``details`` with
        ``path`` when the error names a file.
    """
    reason = _OS_REASONS.get(exc.errno or 0) or exc.strerror or str(exc)
    target = exc.filename
    if target is None:
        return f"Błąd systemu plików: {reason}", {}
    path = (
        os.fsdecode(target)
        if isinstance(target, str | bytes | os.PathLike)
        else str(target)
    )
    return f"Błąd systemu plików: {reason}: {path}", {"path": path}


def io_error(exc: OSError, /) -> IMGWDataError:
    """
    Error of a stored file the system cannot read (permissions, I/O).

    Read sites of the store raise it instead of folding the `OSError` into
    ``data_error``; being an `IMGWDataError`, it ends a per-item operation
    like a damaged version does.

    Parameters
    ----------
    exc : OSError
        Error of the read; raise the result ``from exc``.

    Returns
    -------
    IMGWDataError
        Error with ``code="io_error"`` and the text of `describe_os_error`.
    """
    detail, details = describe_os_error(exc)
    return IMGWDataError(detail, code="io_error", details=details)
