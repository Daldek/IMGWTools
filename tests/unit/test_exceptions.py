"""Error-code registry and the IMGWError contract (spec §13.5, §13.9)."""

import copy
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
    IMGWProjectError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWStoreError,
    IMGWValidationError,
)

# code -> (exit code, HTTP status, title), verbatim from the §13.5 table.
SPEC_TABLE = {
    "validation_error": (2, 400, "Nieprawidłowe dane wejściowe"),
    "not_found": (3, 404, "Nie znaleziono"),
    "conflict": (4, 409, "Konflikt stanu"),
    "source_unavailable": (5, 502, "Źródło danych niedostępne"),
    "missing_dependency": (6, 503, "Brak opcjonalnej zależności"),
    "data_error": (7, 500, "Niepoprawne dane"),
    "store_unavailable": (8, 503, "Magazyn niedostępny"),
    "io_error": (9, 500, "Błąd systemu plików"),
    "cancelled": (130, None, "Operację anulowano"),
    "forbidden": (12, 403, "Brak uprawnień do zapisu"),
    "method_not_allowed": (None, 405, "Niedozwolona metoda HTTP"),
    "internal_error": (1, 500, "Błąd wewnętrzny"),
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
    (IMGWProjectError, "validation_error"),
    (IMGWCancelledError, "cancelled"),
]


@pytest.mark.parametrize(("error", "code"), DEFAULT_CODES)
def test_each_class_has_its_default_code(error, code):
    assert error("Komunikat").code == code


@pytest.mark.parametrize(("error", "_default"), DEFAULT_CODES)
def test_code_argument_overrides_the_default(error, _default):
    assert error("Brak wersji", code="not_found").code == "not_found"


@pytest.mark.parametrize("code", ["stale_plan", "store_error", "NOT_FOUND", ""])
def test_unregistered_code_is_rejected(code):
    with pytest.raises(ValueError, match="Nieznany kod błędu"):
        IMGWStoreError("Brak wersji", code=code)


def test_detail_equals_str_and_details_default_to_empty():
    exc = IMGWValidationError("Szerokość geograficzna 1.0 poza zakresem Polski")

    assert exc.detail == str(exc) == "Szerokość geograficzna 1.0 poza zakresem Polski"
    assert dict(exc.details) == {}


def test_details_are_an_independent_copy():
    allowed = ["POT", "AMP"]
    given = {"option": "method", "allowed": allowed}
    exc = IMGWValidationError("Nieznana metoda", details=given)

    given["option"] = "zmienione"
    allowed.append("XXX")

    assert exc.details == {"option": "method", "allowed": ["POT", "AMP"]}


def test_message_is_positional_only_and_options_keyword_only():
    with pytest.raises(TypeError):
        IMGWError(message="Komunikat")
    with pytest.raises(TypeError):
        IMGWError("Komunikat", "not_found")


@pytest.mark.parametrize(
    "roundtrip",
    [lambda exc: pickle.loads(pickle.dumps(exc)), copy.deepcopy],
    ids=["pickle", "deepcopy"],
)
@pytest.mark.parametrize(("error", "_default"), DEFAULT_CODES)
def test_pickle_and_deepcopy_keep_code_detail_and_details(error, _default, roundtrip):
    exc = error("Brak pliku wersji", code="not_found", details={"path": "a/b.zip"})

    restored = roundtrip(exc)

    assert type(restored) is error
    assert (restored.code, restored.detail, dict(restored.details)) == (
        "not_found",
        "Brak pliku wersji",
        {"path": "a/b.zip"},
    )
    assert str(restored) == "Brak pliku wersji"


def _raise_in_worker() -> None:
    raise IMGWStoreError(
        "Brak szeregu stacji", code="not_found", details={"station_code": "999999999"}
    )


def test_error_crosses_a_process_boundary():
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
        future = pool.submit(_raise_in_worker)
        with pytest.raises(IMGWStoreError) as caught:
            future.result()

    assert caught.value.code == "not_found"
    assert caught.value.detail == "Brak szeregu stacji"
    assert caught.value.details == {"station_code": "999999999"}


def test_registry_matches_the_spec_table():
    assert set(ERROR_CODES) == set(SPEC_TABLE) == set(get_args(ErrorCode))
    assert len(ERROR_CODES) == 12
    for code, spec in ERROR_CODES.items():
        assert spec.code == code
        assert (spec.exit_code, spec.http_status, spec.title) == SPEC_TABLE[code]


def test_registry_has_a_distinct_english_title_for_every_code():
    # REST answers title_en for Accept-Language: en (spec 2026-10-19 §4.2).
    titles = [spec.title_en for spec in ERROR_CODES.values()]
    assert len(set(titles)) == len(titles)


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

    assert "pip install imgwtools[store]" in exc.detail
    assert exc.code == "missing_dependency"


def test_public_package_exports_the_registry():
    for name in ("ERROR_CODES", "ErrorSpec", "ErrorCode", "IMGWCancelledError"):
        assert name in imgwtools.__all__
        assert hasattr(imgwtools, name)
    assert "IMGWPlanStaleError" not in imgwtools.__all__
    assert not hasattr(imgwtools, "IMGWPlanStaleError")
