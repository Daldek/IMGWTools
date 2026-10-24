"""Message catalog: both languages of every entry, every call site, no stray Polish."""

import ast
import copy
import pickle
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

import imgwtools
from imgwtools.messages import (
    DEFAULT_LANG,
    LANGS,
    Message,
    Text,
    catalogs,
    localize,
    message,
    placeholders,
    valid_key,
)

SRC = Path(imgwtools.__file__).parent
# Polish diacritics or a few words that no English text uses.
POLISH = re.compile(
    "[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]"
    r"|\b(?:nie|brak|albo|lub|oraz|jest|dla|musi|dozwolone|nieznan\w+|niepoprawn\w+)\b",
    re.IGNORECASE,
)
SCOPES = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef

# Files that still hold Polish string literals outside the catalog. One comment line
# names an area, so the commit that migrates an area touches only its own lines.
# A file leaves the set as soon as its last Polish literal does (checked below).
_PENDING = frozenset(
    {
        # Command and dataset registries: Polish texts with an English variant beside.
        "commands.py",
        "datasets.py",
        # Agent guide and MCP server.
        "agent_guide.py",
        "mcp/_calls.py",
        "mcp/_tools.py",
        "mcp/server.py",
        # REST API.
        "api/errors.py",
        "api/main.py",
        "api/routes/commands.py",
        # CLI.
        "cli/_dispatch.py",
        "cli/admin.py",
        "cli/config_cmd.py",
        "cli/main.py",
        # Versioned store.
        "store/catalog.py",
        "store/content.py",
        "store/export.py",
        "store/pmaxtp.py",
        "store/reader.py",
        "store/series.py",
        "store/sync.py",
        "store/types.py",
        "store/writer.py",
        # Projects.
        "project.py",
        # Parsers.
        "_parsing/__init__.py",
        "_parsing/chmi.py",
        "_parsing/common.py",
        "_parsing/hydro.py",
        "_parsing/meteo.py",
        "_parsing/stations.py",
        # Other modules of the library.
        "config.py",
        "coverage.py",
        "fetch.py",
        "models.py",
        "reference_data.py",
        "stations.py",
        "testing.py",
        "urls.py",
    }
)


def sources() -> Iterator[tuple[str, ast.Module]]:
    """Every module of the package outside the catalogs, parsed."""
    for path in sorted(SRC.rglob("*.py")):
        name = path.relative_to(SRC).as_posix()
        if not name.startswith("messages/"):
            yield name, ast.parse(path.read_text(encoding="utf-8"))


def entries() -> list[tuple[str, Text]]:
    return [
        (f"{area}.{name}", text)
        for area, catalog in catalogs().items()
        for name, text in catalog.items()
    ]


def string_values(tree: ast.AST) -> Iterator[ast.Constant]:
    """String constants that are not docstrings."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, SCOPES) and node.body and isinstance(node.body[0], ast.Expr)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node


def message_calls() -> Iterator[tuple[str, ast.Call]]:
    for name, tree in sources():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "message"
            ):
                yield name, node


# --------------------------------------------------------------------------
# The catalogs
# --------------------------------------------------------------------------


def test_every_entry_has_both_languages_with_the_same_placeholders():
    problems = []
    for key, text in entries():
        if not valid_key(key):
            problems.append(f"{key}: not <area>.<name> in snake_case")
        for lang in LANGS:
            if not getattr(text, lang).strip():
                problems.append(f"{key}: empty {lang} text")
        try:
            english, polish = placeholders(text.en), placeholders(text.pl)
        except ValueError as exc:
            problems.append(f"{key}: {exc}")
            continue
        if english != polish:
            problems.append(
                f"{key}: placeholders {sorted(english)} != {sorted(polish)}"
            )
        if "lang" in english:
            problems.append(f"{key}: a placeholder is called lang")
        if text.en == text.pl:
            problems.append(f"{key}: the Polish text is the English one")
    assert not problems, "\n".join(problems)


def test_every_call_names_an_entry_and_gives_exactly_its_placeholders():
    known = dict(entries())
    problems = []
    for name, call in message_calls():
        where = f"{name}:{call.lineno}"
        first = call.args[0] if call.args else None
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue  # a key chosen at run time, e.g. from a table
        if len(call.args) > 1:
            problems.append(f"{where}: positional arguments after the key")
        if first.value not in known:
            problems.append(f"{where}: unknown key {first.value!r}")
            continue
        if any(keyword.arg is None for keyword in call.keywords):
            continue
        given = {keyword.arg for keyword in call.keywords} - {"lang"}
        wanted = placeholders(known[first.value].en)
        if given != wanted:
            problems.append(f"{where}: {first.value} wants {sorted(wanted)}")
    assert not problems, "\n".join(problems)


def test_no_entry_is_unused_and_no_key_like_literal_is_misspelled():
    literals = {
        node.value
        for _, tree in sources()
        for node in string_values(tree)
        if valid_key(node.value)
    }
    known = {key for key, _ in entries()}
    areas = set(catalogs())
    unused = sorted(known - literals)
    misspelled = sorted(
        value for value in literals - known if value.split(".")[0] in areas
    )
    assert not unused, f"entries nobody uses: {unused}"
    assert not misspelled, f"literals that look like keys of a catalog: {misspelled}"


def test_polish_literals_stay_only_in_the_catalog_and_the_pending_files():
    found = {
        name
        for name, tree in sources()
        if any(POLISH.search(node.value) for node in string_values(tree))
    }
    assert found - _PENDING == set(), "a Polish text belongs in imgwtools.messages"
    assert _PENDING - found == set(), "no Polish literal left: drop the file"


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_a_message_is_english_by_default_and_remembers_its_key_and_values():
    text = message("errors.file_system", reason="disk full")

    assert DEFAULT_LANG == "en"
    assert isinstance(text, str)
    assert text == "File system error: disk full"
    assert (text.key, text.lang, dict(text.params)) == (
        "errors.file_system",
        "en",
        {"reason": "disk full"},
    )


def test_localized_renders_the_same_key_and_values_in_the_other_language():
    text = message("errors.file_system_path", reason="x", path="/data/a")

    polish = text.localized("pl")

    assert polish == "Błąd systemu plików: x: /data/a"
    assert polish.lang == "pl"
    assert polish.localized("en") == text
    assert text.localized("en") is text


def test_a_message_among_the_values_is_rendered_in_the_language_of_its_parent():
    reason = message("errors.os_no_space")
    text = message("errors.file_system", reason=reason)

    assert text == "File system error: no space left on the device"
    assert text.localized("pl") == "Błąd systemu plików: brak miejsca na urządzeniu"


def test_operations_on_a_message_give_plain_text_but_copies_keep_it_translatable():
    text = message("errors.os_file_exists")

    assert type(f"{text}!") is str
    for clone in (
        copy.deepcopy(text),
        pickle.loads(pickle.dumps(text)),
        pickle.loads(pickle.dumps(text.localized("pl"))),
    ):
        assert isinstance(clone, Message)
        assert clone.key == text.key
        assert clone.localized("pl") == "plik już istnieje"


def test_localize_changes_only_catalog_messages():
    assert localize(message("errors.title_not_found"), "pl") == "Nie znaleziono"
    assert localize("Nie znaleziono", "en") == "Nie znaleziono"
    assert localize("plain text", "pl") == "plain text"


def test_a_wrong_key_or_language_is_a_program_error():
    with pytest.raises(KeyError):
        message("errors.no_such_message")
    with pytest.raises(KeyError):
        message("no_such_area.title")
    with pytest.raises(KeyError):
        message("errors")
    with pytest.raises(ValueError, match="allowed"):
        message("errors.title_conflict", "de")
    with pytest.raises(ValueError):
        placeholders("{0}")
    with pytest.raises(ValueError):
        placeholders("{value.name}")
    assert placeholders("{a} {b!r:>5} {{literal}}") == {"a", "b"}
