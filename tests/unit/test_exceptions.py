"""Error-code registry and the IMGWError contract (spec §13.5, §13.9)."""

import copy
import errno
import multiprocessing
import pickle
from concurrent.futures import ProcessPoolExecutor
from typing import get_args

import pytest

import imgwtools
from imgwtools.exceptions import (
    ERROR_CODES,
    ErrorCode,
    IMGWCancelledError,
    IMGWConnectionError,
    IMGWDataError,
    IMGWError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWStoreError,
    IMGWValidationError,
    describe_os_error,
    io_error,
)
from imgwtools.messages import LANGS, message

# code -> (exit code, HTTP status, English title), verbatim from the §13.5 table.
SPEC_TABLE = {
    "validation_error": (2, 400, "Invalid input"),
    "not_found": (3, 404, "Not found"),
    "conflict": (4, 409, "State conflict"),
    "source_unavailable": (5, 502, "Data source unavailable"),
    "missing_dependency": (6, 503, "Missing optional dependency"),
    "data_error": (7, 500, "Invalid data"),
    "store_unavailable": (8, 503, "Store unavailable"),
    "io_error": (9, 500, "File system error"),
    "cancelled": (130, None, "Operation cancelled"),
    "forbidden": (12, 403, "Write not permitted"),
    "method_not_allowed": (None, 405, "HTTP method not allowed"),
    "internal_error": (1, 500, "Internal error"),
}
TITLES_PL = {
    "validation_error": "Nieprawidłowe dane wejściowe",
    "not_found": "Nie znaleziono",
    "conflict": "Konflikt stanu",
    "source_unavailable": "Źródło danych niedostępne",
    "missing_dependency": "Brak opcjonalnej zależności",
    "data_error": "Niepoprawne dane",
    "store_unavailable": "Magazyn niedostępny",
    "io_error": "Błąd systemu plików",
    "cancelled": "Operację anulowano",
    "forbidden": "Brak uprawnień do zapisu",
    "method_not_allowed": "Niedozwolona metoda HTTP",
    "internal_error": "Błąd wewnętrzny",
}
ENVELOPE_EXIT_CODES = {"ok": 0, "partial": 10, "failed": 11, "cancelled": 130}
DEFAULT_CODES = [
    (IMGWError, "internal_error"),
    (IMGWConnectionError, "source_unavailable"),
    (IMGWDataError, "data_error"),
    (IMGWValidationError, "validation_error"),
    (IMGWStoreError, "store_unavailable"),
    (IMGWStoreConflictError, "conflict"),
    (IMGWStoreDependencyError, "missing_dependency"),
    (IMGWCancelledError, "cancelled"),
]


@pytest.mark.parametrize(("error", "code"), DEFAULT_CODES)
def test_each_class_has_its_default_code(error, code):
    assert error("Message").code == code


@pytest.mark.parametrize(("error", "_default"), DEFAULT_CODES)
def test_code_argument_overrides_the_default(error, _default):
    assert error("No version", code="not_found").code == "not_found"


@pytest.mark.parametrize("code", ["stale_plan", "store_error", "NOT_FOUND", ""])
def test_unregistered_code_is_rejected(code):
    with pytest.raises(ValueError, match="Unknown error code"):
        IMGWStoreError("No version", code=code)


def test_detail_equals_str_and_details_default_to_empty():
    exc = IMGWValidationError("Latitude 1.0 is outside Poland")

    assert exc.detail == str(exc) == "Latitude 1.0 is outside Poland"
    assert dict(exc.details) == {}


def test_details_are_an_independent_copy():
    allowed = ["POT", "AMP"]
    given = {"option": "method", "allowed": allowed}
    exc = IMGWValidationError("Unknown method", details=given)

    given["option"] = "changed"
    allowed.append("XXX")

    assert exc.details == {"option": "method", "allowed": ["POT", "AMP"]}


def test_detail_is_positional_only_and_options_keyword_only():
    with pytest.raises(TypeError):
        IMGWError(detail="Message")
    with pytest.raises(TypeError):
        IMGWError("Message", "not_found")


@pytest.mark.parametrize(
    "roundtrip",
    [lambda exc: pickle.loads(pickle.dumps(exc)), copy.deepcopy],
    ids=["pickle", "deepcopy"],
)
@pytest.mark.parametrize(("error", "_default"), DEFAULT_CODES)
def test_pickle_and_deepcopy_keep_code_detail_and_details(error, _default, roundtrip):
    exc = error("No version file", code="not_found", details={"path": "a/b.zip"})

    restored = roundtrip(exc)

    assert type(restored) is error
    assert (restored.code, restored.detail, dict(restored.details)) == (
        "not_found",
        "No version file",
        {"path": "a/b.zip"},
    )
    assert str(restored) == "No version file"


def _raise_in_worker() -> None:
    raise IMGWStoreError(
        "No station series", code="not_found", details={"station_code": "999999999"}
    )


def test_error_crosses_a_process_boundary():
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
        future = pool.submit(_raise_in_worker)
        with pytest.raises(IMGWStoreError) as caught:
            future.result()

    assert caught.value.code == "not_found"
    assert caught.value.detail == "No station series"
    assert caught.value.details == {"station_code": "999999999"}


def test_registry_matches_the_spec_table():
    assert set(ERROR_CODES) == set(SPEC_TABLE) == set(get_args(ErrorCode))
    assert len(ERROR_CODES) == 12
    for code, spec in ERROR_CODES.items():
        assert spec.code == code
        assert (spec.exit_code, spec.http_status, spec.title) == SPEC_TABLE[code]


def test_registry_has_the_polish_variant_and_a_distinct_title_in_every_language():
    for lang in LANGS:
        titles = [spec.title.localized(lang) for spec in ERROR_CODES.values()]
        assert len(set(titles)) == len(titles)
    for code, spec in ERROR_CODES.items():
        assert spec.title.localized("pl") == TITLES_PL[code]


def test_error_exit_codes_are_distinct_and_apart_from_envelope_codes():
    exit_codes = [s.exit_code for s in ERROR_CODES.values() if s.exit_code is not None]

    assert len(exit_codes) == len(set(exit_codes))
    # 130 is shared with the "cancelled" envelope on purpose.
    clashes = set(exit_codes) & set(ENVELOPE_EXIT_CODES.values())
    assert clashes == {ERROR_CODES["cancelled"].exit_code}


def test_registry_is_read_only():
    with pytest.raises(TypeError):
        ERROR_CODES["io_error"] = ERROR_CODES["data_error"]


def test_dependency_error_keeps_install_message_and_code():
    exc = IMGWStoreDependencyError()

    assert exc.detail == "Install the extra: pip install imgwtools[store]"
    assert exc.localized("pl") == "Zainstaluj dodatek: pip install imgwtools[store]"
    assert exc.code == "missing_dependency"


def test_only_a_catalog_detail_is_translated():
    assert IMGWError("Plain text").localized("pl") == "Plain text"
    assert IMGWError(message("errors.title_conflict")).localized("pl") == (
        "Konflikt stanu"
    )


def test_a_file_system_error_is_an_io_error_described_in_both_languages():
    denied = PermissionError(errno.EACCES, "Permission denied", "/data/x")

    exc = io_error(denied)

    assert (exc.code, exc.detail, dict(exc.details)) == (
        "io_error",
        "File system error: permission denied: /data/x",
        {"path": "/data/x"},
    )
    assert exc.localized("pl") == "Błąd systemu plików: brak uprawnień: /data/x"


def test_an_unknown_errno_reports_the_text_of_the_system():
    detail, details = describe_os_error(OSError(errno.EIO, "Input/output error"))

    assert (detail, details) == ("File system error: Input/output error", {})


def test_public_package_exports_the_registry():
    for name in ("ERROR_CODES", "ErrorSpec", "ErrorCode", "IMGWCancelledError"):
        assert name in imgwtools.__all__
        assert hasattr(imgwtools, name)
    assert "IMGWPlanStaleError" not in imgwtools.__all__
    assert not hasattr(imgwtools, "IMGWPlanStaleError")
