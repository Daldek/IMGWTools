"""Guide for AI agents (spec 2026-10-19 §5, §9): AGENTS.md, llms.txt, commands guide."""

import json
import re
import shlex
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from imgwtools import agent_guide, init_store
from imgwtools.agent_guide import _FLOWS, _PRINCIPLES, _instructions, _render, _Symbol
from imgwtools.api.main import app as rest_app
from imgwtools.cli.main import app as cli_app
from imgwtools.commands import check_command, command_schema, validate_command
from imgwtools.datasets import datasets
from imgwtools.exceptions import ERROR_CODES, IMGWValidationError
from tests.unit.test_commands import parse

REPOSITORY = Path(__file__).resolve().parents[2]
GUIDES = {"AGENTS.md": "agents", "llms.txt": "llms"}
RUNNER = CliRunner()
# Fictional values of the flow symbols (spec 2026-10-19 §9): Polish and English names.
FICTIONAL = {
    "KOD_STACJI": "123456789",
    "STATION_CODE": "123456789",
    "KOD_WIGOS": "0-203-1-900001",
    "WIGOS_ID": "0-203-1-900001",
}
PROJECT_SYMBOLS = ("PROJEKT", "PROJECT")


@pytest.fixture(autouse=True)
def no_environment(monkeypatch):
    """The developer's IMGW_LANG and IMGW_STORE_ROOT must not reach the commands."""
    monkeypatch.delenv("IMGW_LANG", raising=False)
    monkeypatch.delenv("IMGW_STORE_ROOT", raising=False)


def text(format: str = "agents", lang: str = "pl") -> str:
    return "".join(agent_guide(format=format, lang=lang))


def rows(markdown: str) -> list[list[str]]:
    """Cells of every table row of ``markdown`` (separator rows included)."""
    return [
        re.split(r"(?<!\\) \| ", line[2:-2])
        for line in markdown.splitlines()
        if line.startswith("| ") and line.endswith(" |")
    ]


def section(markdown: str, heading: str) -> str:
    """Text of the ``## heading`` section, up to the next ``## `` heading."""
    start = markdown.index(f"\n## {heading}\n")
    end = markdown.find("\n## ", start + 1)
    return markdown[start : None if end < 0 else end]


# --------------------------------------------------------------------------
# Derived files of the repository
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "format"), GUIDES.items())
def test_repository_guides_are_the_bytes_of_the_generator(name, format):
    expected = text(format).encode("utf-8")

    assert (REPOSITORY / name).read_bytes() == expected, (
        f"{name} różni się od generatora; zregeneruj plik: imgw commands guide "
        f"--format {format} --lang pl --path {name}"
    )


def test_guide_does_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    first = {(f, lang): text(f, lang) for f in GUIDES.values() for lang in ("pl", "en")}
    monkeypatch.chdir(tmp_path)

    again = {key: text(*key) for key in first}

    assert again == first
    assert not any(str(tmp_path) in guide for guide in again.values())
    assert not any("<!-- imgw:" in guide for guide in again.values())


# --------------------------------------------------------------------------
# Content generated from the catalog and the registries
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_guide_lists_every_command_dataset_error_status_and_alias(lang):
    guide = text("agents", lang)
    document = command_schema(lang=lang)
    tables = [cells for cells in rows(guide) if cells[0].startswith("`")]
    flags = [
        alias
        for schema in document["commands"]
        for names in schema["x-imgw"]["cli"]["flags"].values()
        for alias in names[1:]
        if not alias.startswith("--no-")
    ]

    commands = [cells[0] for cells in tables if len(cells) == 7]
    assert commands == [f"`{schema['title']}`" for schema in document["commands"]]
    keys = [cells[0] for cells in tables if len(cells) == 10]
    assert keys == [f"`{descriptor.key}`" for descriptor in datasets()]
    errors = {tuple(cells) for cells in tables if len(cells) == 4}
    for spec in ERROR_CODES.values():
        title = spec.title_en if lang == "en" else spec.title
        exit_code = "—" if spec.exit_code is None else str(spec.exit_code)
        status = "—" if spec.http_status is None else str(spec.http_status)
        assert (f"`{spec.code}`", title, exit_code, status) in errors
    statuses = {tuple(cells[:2]) for cells in tables if len(cells) == 3}
    for status, code in document["exit_codes"].items():
        assert (f"`{status}`", str(code)) in statuses
    aliases = {cells[0] for cells in tables if len(cells) == 2}
    assert aliases == {f"`{alias}`" for alias in flags}
    for group, title in document["groups"].items():
        assert f"### `{group}` — {title}\n" in guide


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_guides_carry_the_rules_shared_with_the_mcp_instructions(lang):
    rules = [english if lang == "en" else polish for polish, english in _PRINCIPLES]
    expected = "\n".join(f"{n}. {rule}" for n, rule in enumerate(rules, start=1))

    for format in GUIDES.values():
        assert f"\n{expected}\n" in text(format, lang)


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_every_flow_command_of_the_guide_validates_with_fictional_values(
    lang, tmp_path
):
    heading = "Typical flows" if lang == "en" else "Typowe przepływy"
    flows = section(text("agents", lang), heading)
    lines = re.findall(r"^\d+\. `(imgw [^`]+)`", flows, flags=re.MULTILINE)

    assert len(lines) == sum(
        step.command is not None for flow in _FLOWS for step in flow.steps
    )
    for line in lines:
        for symbol, value in FICTIONAL.items():
            line = line.replace(symbol, value)
        for symbol in PROJECT_SYMBOLS:
            line = line.replace(symbol, shlex.quote(str(tmp_path / "projekt")))
        words = shlex.split(line)
        command, options = parse(shlex.join(w for w in words if w != "--check"))
        validate_command(command, options=options)


def test_flow_steps_name_only_known_symbols():
    def symbols(value):
        if isinstance(value, _Symbol):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from symbols(item)
        elif isinstance(value, list):
            for item in value:
                yield from symbols(item)

    used = {s for flow in _FLOWS for step in flow.steps for s in symbols(step.options)}

    assert {(s.pl, s.en) for s in used} == {
        ("KOD_STACJI", "STATION_CODE"),
        ("KOD_WIGOS", "WIGOS_ID"),
        ("PROJEKT", "PROJECT"),
    }


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_llms_txt_has_the_llms_txt_structure(lang):
    lines = text("llms", lang).splitlines()
    headings = [n for n, line in enumerate(lines) if line.startswith("#")]

    assert lines[0] == "# IMGWTools"
    assert next(line for line in lines[1:] if line).startswith("> ")
    assert all(lines[n].startswith("## ") for n in headings[1:])
    assert lines[headings[-1]] == "## Optional"
    for start, end in zip(headings[1:], [*headings[2:], len(lines)], strict=True):
        items = [line for line in lines[start + 1 : end] if line]
        assert items, lines[start]
        assert all(
            re.fullmatch(r"- \[[^\]]+\]\(https://[^)\s]+\)(: .+)?", item)
            for item in items
        ), items


# --------------------------------------------------------------------------
# commands guide in Python, CLI and REST
# --------------------------------------------------------------------------


def test_commands_guide_gives_the_same_bytes_in_python_cli_and_rest():
    expected = text("llms").encode("utf-8")

    printed = RUNNER.invoke(cli_app, ["commands", "guide", "--format", "llms"])
    answered = TestClient(rest_app).get(
        "/api/v1/commands/guide", params={"format": "llms"}
    )

    assert printed.exit_code == 0, printed.output
    assert printed.stdout_bytes == expected
    assert answered.status_code == 200
    assert answered.content == expected
    assert answered.headers["content-type"] == "text/markdown; charset=utf-8"
    assert answered.headers["content-disposition"] == 'attachment; filename="llms.txt"'
    assert (answered.headers["x-imgw-status"], answered.headers["x-imgw-notices"]) == (
        "ok",
        "[]",
    )


def test_rest_guide_follows_accept_language_as_agents_md():
    answered = TestClient(rest_app).get(
        "/api/v1/commands/guide", headers={"Accept-Language": "en-GB, pl;q=0.5"}
    )

    assert answered.content == text("agents", "en").encode("utf-8")
    assert answered.headers["content-disposition"] == (
        'attachment; filename="AGENTS.md"'
    )
    assert answered.headers["content-language"] == "en"
    assert "accept-language" in answered.headers["vary"].lower()


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_path_writes_the_guide_and_check_only_plans_it(existing, tmp_path):
    target = tmp_path / "AGENTS.md"
    if existing:
        target.write_text("stara treść\n", encoding="utf-8")
    args = ["commands", "guide", "--lang", "en", "--path", str(target)]

    planned = RUNNER.invoke(cli_app, [*args, "--check"])
    untouched = target.read_bytes() if existing else target.exists()
    written = RUNNER.invoke(cli_app, args)

    plan = json.loads(planned.stdout)
    assert (plan["check"], plan["status"]) == (True, "ok")
    replaced = " (istniejący plik zostanie zastąpiony)" if existing else ""
    assert plan["result"]["actions"] == [
        {
            "command": "commands guide",
            "status": "current",
            "detail": f"Przewodnik agents (en) → {target}{replaced}",
        }
    ]
    assert untouched == ("stara treść\n".encode() if existing else False)
    envelope = json.loads(written.stdout)
    assert (envelope["status"], envelope["result"]) == ("ok", str(target))
    assert target.read_bytes() == text("agents", "en").encode("utf-8")
    assert [path.name for path in tmp_path.iterdir()] == ["AGENTS.md"]  # no .part


def test_guide_without_path_plans_the_standard_output():
    plan = check_command("commands guide", options={"format": "llms"}).result

    assert [(action.status, action.detail) for action in plan.actions] == [
        ("current", "Przewodnik llms (pl) → standardowe wyjście")
    ]


def test_path_in_a_store_a_missing_directory_or_a_directory_is_refused(tmp_path):
    store = init_store(tmp_path / "magazyn").root
    before = sorted(store.rglob("*"))

    for path in (store / "AGENTS.md", tmp_path / "brak" / "AGENTS.md", tmp_path):
        with pytest.raises(IMGWValidationError) as error:
            agent_guide(path=path)
        assert error.value.details["option"] == "path"
    assert sorted(store.rglob("*")) == before


@pytest.mark.parametrize(
    ("options", "option"), [({"format": "html"}, "format"), ({"lang": "de"}, "lang")]
)
def test_unknown_format_or_language_is_a_validation_error(options, option):
    with pytest.raises(IMGWValidationError) as error:
        agent_guide(**options)

    assert error.value.details["option"] == option


# --------------------------------------------------------------------------
# Templates and MCP instructions
# --------------------------------------------------------------------------


def test_render_replaces_markers_and_rejects_unknown_or_repeated_blocks():
    blocks = {"one": lambda: "1.0", "many": lambda: "a\nb"}

    assert _render("v<!-- imgw:one -->\n<!-- imgw:many -->\nend\n", blocks) == [
        "v1.0\n",
        "a\n",
        "b\n",
        "end\n",
    ]
    for template in (
        "<!-- imgw:nothing -->\n",
        "<!-- imgw:one -->\n<!-- imgw:one -->\n",
        "x <!-- imgw:many -->\n",
    ):
        with pytest.raises(ValueError):
            _render(template, blocks)


@pytest.mark.parametrize("lang", ["pl", "en"])
@pytest.mark.parametrize("mode", ["read", "write", "http"])
def test_instructions_hold_the_rules_and_the_mode_below_2_kib(lang, mode, tmp_path):
    workdir, root = tmp_path / "praca", tmp_path / "magazyn"

    with_store = _instructions(lang=lang, mode=mode, workdir=workdir, root=root)
    without = _instructions(lang=lang, mode=mode, workdir=workdir, root=None)

    for instructions in (with_store, without):
        assert len(instructions.encode("utf-8")) < 2048
        for polish, english in _PRINCIPLES:
            assert (english if lang == "en" else polish) in instructions
        assert "`commands_guide`" in instructions and "50" in instructions
    assert with_store != without
    shown = mode != "http"  # REST never names the server's directories
    assert (str(workdir) in with_store, str(root) in with_store) == (shown, shown)
    modes = {
        _instructions(lang=lang, mode=other, workdir=None, root=None)
        for other in ("read", "write", "http")
    }
    assert len(modes) == 3
