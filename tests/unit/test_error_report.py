"""The ``obserwator-error/1`` document and its hint (AGI-4.3)."""

import pytest

from obserwator.error_report import error_document, error_report
from obserwator.exceptions import ERROR_CODES, ObserwatorError
from obserwator.store import init_store, open_store


def test_the_document_has_the_registry_title_and_exit_code_and_leaves_out_absent_fields():
    document = error_document("data_error", "Broken sidecar", {"path": "x"}).to_dict()

    assert document == {
        "schema": "obserwator-error/1",
        "code": "data_error",
        "title": ERROR_CODES["data_error"].title,
        "message": "Broken sidecar",
        "details": {"path": "x"},
        "exit_code": ERROR_CODES["data_error"].exit_code,
    }


def test_an_empty_message_is_the_title_and_a_rest_only_code_has_no_exit_code():
    document = error_document("method_not_allowed", "", command="store info").to_dict()

    assert (document["message"], document["exit_code"], document["command"]) == (
        ERROR_CODES["method_not_allowed"].title,
        None,
        "store info",
    )


@pytest.mark.parametrize(
    ("code", "details", "hint"),
    [
        (
            "validation_error",
            {"option": "kind", "value": "x", "allowed": ["hydro", "meteo"]},
            "Use --kind with one of: hydro, meteo",
        ),
        (
            "validation_error",
            {
                "option": "year_type",
                "value": "x",
                "allowed": [str(n) for n in range(13)],
            },
            "Use --year-type with one of the values in details.allowed",
        ),
        (
            "validation_error",
            {
                "option": "root",
                "reason": "exclusive_options",
                "options": ["output_dir", "root"],
            },
            "Give only one of --output-dir, --root",
        ),
        (
            "conflict",
            {"reason": "output_exists", "paths": ["a.csv"]},
            "Add --force to replace the existing output, or choose another output path",
        ),
        (
            "source_unavailable",
            {"url": "https://example.org", "reason": "timeout"},
            "Retry the same command later; details.url is the requested address",
        ),
        ("not_found", {}, "obserwator store scan lists the versions the store holds"),
        ("validation_error", {"option": "station"}, None),
        ("data_error", {"reason": "unknown_reason"}, None),
    ],
    ids=str,
)
def test_the_hint_comes_from_the_reason_then_from_the_code(code, details, hint):
    document = error_document(code, "Something failed", details).to_dict()

    assert document.get("hint") == hint


def test_the_hint_of_the_raise_site_wins_and_follows_the_language():
    error = ObserwatorError(
        "Conflict", code="conflict", details={"reason": "output_exists"}, hint="Use -x"
    )
    polish = error_document(
        "conflict", "Konflikt", {"reason": "output_exists"}, lang="pl"
    ).to_dict()

    assert error_report(error).to_dict()["hint"] == "Use -x"
    assert (polish["title"], polish["hint"]) == (
        ERROR_CODES["conflict"].title.localized("pl"),
        (
            "Dodaj --force, aby zastąpić istniejące wyjście, albo wybierz inną "
            "ścieżkę wyjścia"
        ),
    )


def test_a_missing_store_names_store_init_with_its_root(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ObserwatorError) as raised:
        open_store(missing)

    assert error_report(raised.value).hint == (
        f"Create the store with obserwator store init --root {missing}, or give "
        "--root of an existing store"
    )


def test_a_nested_store_names_the_root_to_change(tmp_path):
    init_store(tmp_path / "outer")
    with pytest.raises(ObserwatorError) as raised:
        init_store(tmp_path / "outer" / "inner")

    assert (
        error_report(raised.value, command="store init").to_dict()["hint"]
        == "Choose a --root that neither lies in another store nor holds one"
    )
