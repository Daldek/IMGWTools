"""Guide for AI agents (spec 2026-10-19 §5, §9): AGENTS.md, llms.txt, commands guide."""

import hashlib
import json
import re
import shlex
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from imgwtools import agent_guide, init_store
from imgwtools.agent_guide import (
    _EFFECTS,
    _FLOWS,
    _PRINCIPLES,
    GuideFormat,
    _instructions,
    _render,
    _Symbol,
)
from imgwtools.api.main import app as rest_app
from imgwtools.cli.main import app as cli_app
from imgwtools.commands import (
    check_command,
    command_schema,
    list_commands,
    parse_command,
    validate_command,
)
from imgwtools.datasets import datasets, providers
from imgwtools.exceptions import ERROR_CODES, IMGWError, IMGWValidationError
from imgwtools.messages import Lang, message

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
    """The developer's IMGW_LANG and IMGW_ROOT must not reach the commands."""
    monkeypatch.delenv("IMGW_LANG", raising=False)
    monkeypatch.delenv("IMGW_ROOT", raising=False)


def text(format: GuideFormat = "agents", lang: Lang = "en") -> str:
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
        f"{name} differs from the generator; regenerate it: imgw commands guide "
        f"--format {format} --output {name} --force"
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
def test_guide_lists_every_command_once_in_the_class_of_its_effect(lang):
    commands = section(text("agents", lang), "Commands" if lang == "en" else "Komendy")
    placed: dict[str, str] = {}
    heading = ""
    for line in commands.splitlines():
        if line.startswith("**"):
            heading = line.strip("*")
        elif found := re.match(r"- `([^`]+)` — ", line):
            assert found[1] not in placed, found[1]
            placed[found[1]] = heading

    listed = list_commands(lang=lang)["commands"]
    assert sorted(placed) == sorted(item["command"] for item in listed)
    for item in listed:
        effect = item["writes"] if item["writes"] != "none" else "read"
        if effect == "read" and item["network"]:
            effect = "network"
        assert placed[item["command"]] == message(_EFFECTS[effect], lang=lang)


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_guide_lists_the_datasets_providers_statuses_and_error_codes(lang):
    guide = text("agents", lang)
    document = command_schema(lang=lang)
    held = section(guide, "Datasets" if lang == "en" else "Zbiory danych")
    envelope = section(
        guide,
        "Envelope, statuses and errors" if lang == "en" else "Koperta, statusy i błędy",
    )

    keys = [cells[0] for cells in rows(held) if cells[0].startswith("`")]
    assert keys == [
        f"`{descriptor.key}`" for descriptor in datasets() if descriptor.in_store
    ]
    for descriptor in datasets():
        assert f"`{descriptor.key}`" in held
    statuses = {
        tuple(cells[:2]) for cells in rows(envelope) if cells[0].startswith("`")
    }
    for status, code in document["exit_codes"].items():
        assert (f"`{status}`", str(code)) in statuses
    for spec in ERROR_CODES.values():
        exit_code = "—" if spec.exit_code is None else spec.exit_code
        http_status = "—" if spec.http_status is None else spec.http_status
        assert f"`{spec.code}` ({exit_code}/{http_status})" in envelope
    for owner in providers():
        assert f"`{owner.key_prefix}.*`" in guide
        assert owner.station_code_pattern in guide


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_agents_md_stays_within_its_budget(lang):
    """DOC-1.7: 200 lines and 16 KiB, in both languages (the file is generated)."""
    guide = text("agents", lang)

    assert len(guide.splitlines()) <= 200
    assert len(guide.encode("utf-8")) <= 16 * 1024


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_llms_txt_states_its_essentials_within_the_budget_before_the_links(lang):
    """DOC-1.7: 8,000 characters before the first link list."""
    lines = text("llms", lang).splitlines()
    first_list = next(n for n, line in enumerate(lines) if line.startswith("- ["))

    assert len("\n".join(lines[:first_list])) <= 8000


@pytest.mark.parametrize(
    ("lang", "last"),
    [
        ("en", "Developing this repository? Read CLAUDE.md."),
        ("pl", "Rozwijasz to repozytorium? Przeczytaj CLAUDE.md."),
    ],
)
def test_agents_md_ends_with_the_pointer_to_claude_md(lang, last):
    """DOC-4.2: the last line serves agents that read AGENTS.md in the repository."""
    assert text("agents", lang).splitlines()[-1] == last


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_guides_carry_the_rules_shared_with_the_mcp_instructions(lang):
    rules = [message(key, lang=lang) for key in _PRINCIPLES]
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
        call = parse_command(line)
        validate_command(call.command, options=call.options)


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

    assert {(s.name("pl"), s.name("en")) for s in used} == {
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
def test_output_writes_the_guide_and_check_only_plans_it(existing, tmp_path):
    target = tmp_path / "AGENTS.md"
    if existing:
        target.write_text("stara treść\n", encoding="utf-8")
    args = ["commands", "guide", "--lang", "en", "--output", str(target)]
    if existing:
        args.append("--force")

    planned = RUNNER.invoke(cli_app, [*args, "--check"])
    untouched = target.read_bytes() if existing else target.exists()
    written = RUNNER.invoke(cli_app, args)

    plan = json.loads(planned.stdout)
    assert (plan["check"], plan["status"]) == (True, "ok")
    [action] = plan["result"]["actions"]
    assert (action["action"], action["path"], action["status"]) == (
        ("replace", str(target), "unverifiable")
        if existing
        else ("write", str(target), "missing")
    )
    assert action["detail"] == (
        f"Write the guide agents (en) to {target}"
        + (", replacing the existing file" if existing else "")
    )
    assert untouched == ("stara treść\n".encode() if existing else False)
    guide = text("agents", "en").encode("utf-8")
    envelope = json.loads(written.stdout)
    assert (envelope["status"], envelope["result"]) == (
        "ok",
        {
            "output": str(target),
            "files": [
                {
                    "path": str(target),
                    "size_bytes": len(guide),
                    "sha256": hashlib.sha256(guide).hexdigest(),
                    "status": "replaced" if existing else "written",
                }
            ],
        },
    )
    assert target.read_bytes() == guide
    assert [path.name for path in tmp_path.iterdir()] == ["AGENTS.md"]  # no staging


def test_an_existing_guide_file_is_a_conflict_the_plan_reports_and_the_run_refuses(
    tmp_path,
):
    target = tmp_path / "AGENTS.md"
    target.write_text("stara treść\n", encoding="utf-8")
    args = ["commands", "guide", "--lang", "en", "--output", str(target)]

    planned = RUNNER.invoke(cli_app, [*args, "--check"])
    refused = RUNNER.invoke(cli_app, args)

    [action] = json.loads(planned.stdout)["result"]["actions"]
    assert (planned.exit_code, action["action"], action["reason"]) == (
        0,
        "conflict",
        "output_exists",
    )
    assert refused.exit_code == 4
    error = json.loads(refused.stderr.strip().splitlines()[-1])
    assert (error["code"], error["details"]) == (
        "conflict",
        {"reason": "output_exists", "paths": [str(target)]},
    )
    assert target.read_text(encoding="utf-8") == "stara treść\n"


def test_guide_without_output_plans_the_standard_output():
    plan = check_command("commands guide", options={"format": "llms"}).result

    assert [(action.status, action.detail) for action in plan.actions] == [
        ("current", "Guide llms (en) → the standard output")
    ]


def test_the_guide_goes_outside_every_store_and_into_a_file_that_is_no_directory(
    tmp_path,
):
    store = init_store(tmp_path / "magazyn").root
    before = sorted(store.rglob("*"))

    with pytest.raises(IMGWError) as error:
        agent_guide(output=store / "AGENTS.md")
    assert (error.value.code, error.value.details["reason"]) == (
        "conflict",
        "output_in_store",
    )
    with pytest.raises(IMGWValidationError) as error:
        agent_guide(output=tmp_path)
    assert error.value.details["option"] == "output"
    assert sorted(store.rglob("*")) == before

    report = agent_guide(output=tmp_path / "brak" / "AGENTS.md")  # created
    assert report.output.is_file()


def test_force_without_output_is_refused_by_the_catalog_and_the_function():
    for call in (
        lambda: agent_guide(force=True),
        lambda: validate_command("commands guide", options={"force": True}),
    ):
        with pytest.raises(IMGWValidationError) as error:
            call()
        assert error.value.details["option"] == "output"


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


@pytest.mark.parametrize("mode", ["read", "write", "http"])
def test_instructions_are_english_and_hold_the_rules_and_the_mode_below_2_kib(
    mode, tmp_path
):
    workdir, root = tmp_path / "praca", tmp_path / "magazyn"

    with_store = _instructions(mode=mode, workdir=workdir, root=root)
    without = _instructions(mode=mode, workdir=workdir, root=None)

    for instructions in (with_store, without):
        assert len(instructions.encode("utf-8")) < 2048
        for key in _PRINCIPLES:
            assert message(key) in instructions
        assert "`imgw_commands_guide`" in instructions and "50" in instructions
        assert instructions.startswith("Rules of IMGWTools:")
    assert with_store != without
    shown = mode != "http"  # REST never names the server's directories
    assert (str(workdir) in with_store, str(root) in with_store) == (shown, shown)
    modes = {
        _instructions(mode=other, workdir=None, root=None)
        for other in ("read", "write", "http")
    }
    assert len(modes) == 3
