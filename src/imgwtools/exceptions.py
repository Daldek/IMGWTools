"""
Exceptions and the closed error-code registry of IMGWTools.

Every :class:`IMGWError` carries a machine-readable ``code`` from
:data:`ERROR_CODES`, a human-readable ``detail`` and JSON-compatible
``details``. The ``detail`` is English; a text from the message catalog
(`imgwtools.messages`) can be rendered in Polish with `IMGWError.localized`.
Each class has a default code; a raise site may pass another registered code
with ``code=``. The registry maps every code to its title, CLI exit code and
HTTP status (spec §13.5), so the CLI, REST and web adapters report the same
error the same way.
"""

from __future__ import annotations

import copy
import errno
import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal

from imgwtools.messages import Lang, Message, localize, message

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
    "unsupported",
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
    title : Message
        Short English title (``title`` of an RFC 9457 problem document);
        ``title.localized("pl")`` is the Polish one.
    exit_code : int or None
        CLI exit code, or ``None`` when the CLI never reports this code
        (``method_not_allowed``).
    http_status : int or None
        HTTP status, or ``None`` when REST never reports this code.
    """

    code: ErrorCode
    title: Message
    exit_code: int | None
    http_status: int | None


ERROR_CODES: Mapping[ErrorCode, ErrorSpec] = MappingProxyType(
    {
        spec.code: spec
        for spec in (
            ErrorSpec(
                "validation_error", message("errors.title_validation_error"), 2, 400
            ),
            ErrorSpec("not_found", message("errors.title_not_found"), 3, 404),
            ErrorSpec("conflict", message("errors.title_conflict"), 4, 409),
            ErrorSpec(
                "source_unavailable", message("errors.title_source_unavailable"), 5, 502
            ),
            ErrorSpec(
                "missing_dependency", message("errors.title_missing_dependency"), 6, 503
            ),
            ErrorSpec("data_error", message("errors.title_data_error"), 7, 500),
            ErrorSpec(
                "store_unavailable", message("errors.title_store_unavailable"), 8, 503
            ),
            ErrorSpec("io_error", message("errors.title_io_error"), 9, 500),
            ErrorSpec("cancelled", message("errors.title_cancelled"), 130, None),
            ErrorSpec("forbidden", message("errors.title_forbidden"), 12, 403),
            ErrorSpec("unsupported", message("errors.title_unsupported"), 15, 422),
            ErrorSpec(
                "method_not_allowed",
                message("errors.title_method_not_allowed"),
                None,
                405,
            ),
            ErrorSpec("internal_error", message("errors.title_internal_error"), 1, 500),
        )
    }
)
"""Closed registry of error codes (spec §13.5), keyed by code."""


class IMGWError(Exception):
    """
    Base exception for all IMGWTools errors.

    Parameters
    ----------
    detail : str
        English human-readable description; becomes ``detail`` and ``str(exc)``.
        Pass a catalog `imgwtools.messages.Message` for a text that has a
        Polish variant (`localized`); a plain string stays as it is.
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
        The description, equal to ``str(exc)``.
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
        detail: str,
        /,
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        resolved = self.default_code if code is None else code
        if resolved not in ERROR_CODES:
            raise ValueError(
                f"Unknown error code {resolved!r}; allowed: {', '.join(ERROR_CODES)}"
            )
        super().__init__(detail)
        self.code = resolved
        self.detail = detail
        self.details = copy.deepcopy(dict(details or {}))

    def localized(self, lang: Lang) -> str:
        """
        Return the ``detail`` in ``lang``.

        Parameters
        ----------
        lang : {"en", "pl"}
            Language of the caller (``Accept-Language`` of REST, the language of
            an MCP server or of the web GUI).

        Returns
        -------
        str
            A catalog message rendered in ``lang``; any other ``detail`` as it is.
        """
        return localize(self.detail, lang)


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
    detail : str, optional
        English description; defaults to the install instruction.
    code : ErrorCode or None, optional
        Error code overriding ``missing_dependency``.
    details : Mapping[str, object] or None, optional
        JSON-compatible context.
    """

    default_code: ClassVar[ErrorCode] = "missing_dependency"

    def __init__(
        self,
        detail: str = message("errors.store_extra"),
        /,
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(detail, code=code, details=details)


class IMGWCancelledError(IMGWError):
    """
    Operation interrupted by ``cancel`` or Ctrl+C without a partial report.

    Default code: ``cancelled``.
    """

    default_code: ClassVar[ErrorCode] = "cancelled"


# Catalog key of the reason of the common ``errno`` values.
_OS_REASONS = {
    errno.EACCES: "errors.os_permission_denied",
    errno.EPERM: "errors.os_not_permitted",
    errno.ENOENT: "errors.os_no_such_file",
    errno.ENOTDIR: "errors.os_not_a_directory",
    errno.EISDIR: "errors.os_is_a_directory",
    errno.EEXIST: "errors.os_file_exists",
    errno.ENOSPC: "errors.os_no_space",
    errno.EROFS: "errors.os_read_only",
}


def describe_os_error(exc: OSError, /) -> tuple[Message, dict[str, object]]:
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
    tuple[Message, dict[str, object]]
        English ``detail`` (``File system error: <reason>[: <path>]``, the
        reason from the catalog for common ``errno`` values, the system's text
        otherwise) and ``details`` with ``path`` when the error names a file.
    """
    known = _OS_REASONS.get(exc.errno or 0)
    reason = message(known) if known else exc.strerror or str(exc)
    target = exc.filename
    if target is None:
        return message("errors.file_system", reason=reason), {}
    path = (
        os.fsdecode(target)
        if isinstance(target, str | bytes | os.PathLike)
        else str(target)
    )
    return message("errors.file_system_path", reason=reason, path=path), {"path": path}


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
