"""
Exceptions and the closed error-code registry of IMGWTools.

Every :class:`IMGWError` carries a machine-readable ``code`` from
:data:`ERROR_CODES`, a Polish human-readable ``detail`` and JSON-compatible
``details``. Each class has a default code; a raise site may pass another
registered code with ``code=``. The registry maps every code to its Polish
title, CLI exit code and HTTP status (spec §13.5), so the CLI, REST and web
adapters report the same error the same way.
"""

from __future__ import annotations

import copy
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
    """

    code: ErrorCode
    title: str
    exit_code: int | None
    http_status: int | None


ERROR_CODES: Mapping[ErrorCode, ErrorSpec] = MappingProxyType(
    {
        spec.code: spec
        for spec in (
            ErrorSpec("validation_error", "Nieprawidłowe dane wejściowe", 2, 400),
            ErrorSpec("not_found", "Nie znaleziono", 3, 404),
            ErrorSpec("conflict", "Konflikt stanu", 4, 409),
            ErrorSpec("source_unavailable", "Źródło IMGW niedostępne", 5, 502),
            ErrorSpec("missing_dependency", "Brak opcjonalnej zależności", 6, 503),
            ErrorSpec("data_error", "Niepoprawne dane", 7, 500),
            ErrorSpec("store_unavailable", "Magazyn niedostępny", 8, 503),
            ErrorSpec("io_error", "Błąd systemu plików", 9, 500),
            ErrorSpec("cancelled", "Operację anulowano", 130, None),
            ErrorSpec("forbidden", "Brak uprawnień do zapisu", None, 403),
            ErrorSpec("method_not_allowed", "Niedozwolona metoda HTTP", None, 405),
            ErrorSpec("internal_error", "Błąd wewnętrzny", 1, 500),
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
    Connection to IMGW servers failed (timeout, network error, HTTP 4xx/5xx).

    Default code: ``source_unavailable``.
    """

    default_code: ClassVar[ErrorCode] = "source_unavailable"


class IMGWDataError(IMGWError):
    """
    IMGW data or a stored version is invalid (format, SHA, size, JSON, CSV, ZIP).

    Default code: ``data_error``.
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
    Version collision, race, busy lock or no atomic-write guarantee.

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
