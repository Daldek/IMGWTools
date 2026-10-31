# CLAUDE.md

Instructions for Claude Code (claude.ai/code) working in this repository. Reference material lives in `docs/` (section 5).

## 1. Project

IMGWTools (`imgwtools` on PyPI, v3.0.0, profiles `tool` and `app`) is a Python library, CLI (`imgw`), REST API, MCP server and Web GUI for public hydro-meteorological data of IMGW-PIB (Poland) and, since 3.0.0, ČHMÚ (Czechia), with an optional versioned local store of the source archives. Python, CLI, REST and MCP are generated from one command catalog (`imgwtools.commands`, ADR-002); the Web GUI calls public functions only. Overview: [README.md](README.md); architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 2. Critical rules

- Write only where the user says: `--output-dir` (plain files), `--root`, `IMGW_ROOT` or the default store `<data_dir>/imgw` (DEV-19.2, ADR-007); a server writes only to its configured `IMGW_ROOT`, never to the default. No database.
- Never add hand-written commands to the CLI, REST or MCP adapters: they are generated from `command_schema()` (`cli/_dispatch.py`, `api/routes/commands.py`, `mcp/_tools.py`). A command goes into `_CATALOG` in `commands.py`, calls exactly one public function and takes its texts (`help`, `description`, `rules`) from `imgwtools.messages.commands`.
- Never edit `AGENTS.md` and `llms.txt` by hand: they are derived from the catalog. A change of catalog texts, of the dataset/provider/error registries or of the templates in `src/imgwtools/_data/agents/` regenerates both in the same change (commands in section 3); `tests/unit/test_agent_guide.py` compares the bytes.
- Keep the contract Python = CLI = REST = MCP (`tests/contract/`); one option name per parameter, one envelope `imgw-result/1`, one error registry `ERROR_CODES`.
- Never run tests with the global Python (a non-editable `imgwtools` there shadows `src/`): use `uv run`.
- `IMGW_STORE_WRITE_TOKEN` is a credential: environment only, never from a file, never printed.
- Text for a person (an error `detail`, a notice, a progress or plan line, a printed line, a command description or option help) is never inline: it is an entry of `imgwtools.messages.<area>` (`Text(en, pl)`, English first) rendered by `message("<area>.<name>", value=…)` (ADR-006); `tests/unit/test_messages.py` checks both languages, the call sites and that no Polish literal is left outside the catalog.
- Every functional change updates the Markdown docs, docstrings and OpenAPI where affected; no change without tests.
- Approvals (DEV-3.3): without the author's approval in the current session never merge a pull request, create or move tags, publish a release, force-push a shared branch or rewrite the history of `master`/`slave` (to become `main`/`develop`). A change of a public interface or across more than one module starts with a plan approved by the author (DEV-17.4).
- Change only this repository (DEV-17.5); a need in another project is a GitHub issue there labelled `request`.
- Commits: English Conventional Commits, no AI attribution lines (`scripts/check-commits.sh`).
- Document budgets (DOC-1.7): `CLAUDE.md` 200 lines, `docs/PROGRESS.md` 300, `README.md` 400; reference material goes to `docs/`, history to `docs/HISTORY.md`.

## 3. Environment and commands

```bash
uv sync --locked                                   # development environment (.venv, uv.lock)
scripts/gate.sh                                    # gate: ruff format --check, ruff check, mypy, pytest + coverage (offline), commit check
uv run pytest tests/unit/test_models.py -v         # one test file (add -k <expr> for one test)
uv run pytest tests/live -m live                   # live tests (network, outside the gate)
imgw server --reload                               # REST API + Web GUI
imgw config show --json                            # every setting with its source
imgw commands guide --format agents --output AGENTS.md --force   # regenerate AGENTS.md (English)
imgw commands guide --format llms --output llms.txt --force      # regenerate llms.txt (English)
```

Extras: `imgwtools[cli|api|store|mcp|pandas|full]` (install lines in the README). Settings (`IMGW_*`, `NOGAT_*`, `nogat.toml`): [docs/CODEBASE.md](docs/CODEBASE.md) section "Versioned Store → Configuration". Test layout and markers: [docs/TESTING.md](docs/TESTING.md).

## 4. Code map

```
src/imgwtools/
├── __init__.py, fetch.py, models.py, stations.py, datasets.py, urls.py, parsers.py   # PUBLIC API (single __all__)
├── commands.py           # command catalog (30 commands), run_command, command_schema
├── agent_guide.py        # AGENTS.md / llms.txt generator, MCP instructions
├── coverage.py, exceptions.py (ERROR_CODES), testing.py, config.py, reference_data.py
├── messages/             # message catalog: English text with a Polish variant per key (ADR-006)
├── _parsing/             # IMGW-PIB and ČHMÚ file parsers
├── _data/                # borders, agents/ templates, packaged fixtures
├── store/                # versioned store: writer, sync, series, catalog, pmaxtp, reader, export
├── api/                  # FastAPI REST (routes generated from the catalog)   [imgwtools[api]]
├── cli/                  # Typer CLI (_dispatch.py = only catalog adapter)    [imgwtools[cli]]
├── mcp/                  # MCP adapter (stdio and /mcp)                       [imgwtools[mcp]]
└── web/                  # Web GUI (HTMX + Jinja2)
tests/{unit,contract,live}  AGENTS.md, llms.txt (derived)  docker/  scripts/  docs/
```

Full tree with module descriptions: [docs/CODEBASE.md](docs/CODEBASE.md) ("Package Tree").

## 5. Documentation map

| Task | Read |
|---|---|
| What the project is, install, quick start | [README.md](README.md) |
| Usage of every interface, long command listings, store schemas | [docs/USAGE.md](docs/USAGE.md) |
| Architecture, layers, store layout, CI/CD | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Public API, command catalog, option and error tables, data sources and formats, configuration variables, deployment | [docs/CODEBASE.md](docs/CODEBASE.md) |
| Running tests, test layout, markers | [docs/TESTING.md](docs/TESTING.md), plan in [docs/TEST_PLAN.md](docs/TEST_PLAN.md) |
| Product goals and requirements | [docs/PRD.md](docs/PRD.md) |
| Why a design was chosen (ADR-001..008) | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Current state, next steps, open questions | [docs/PROGRESS.md](docs/PROGRESS.md) |
| Release history, closed backlog, cross-project analysis | [docs/HISTORY.md](docs/HISTORY.md) |
| What changed in a release, breaking list, migration tables | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| Code style, naming, errors, docstrings | [docs/RULES.md](docs/RULES.md), [docs/DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md) |
| Contributor licence | [docs/CLA.md](docs/CLA.md) |
| Obserwator (planned rename of the observer tool) | [docs/OBSERWATOR_SPEC.md](docs/OBSERWATOR_SPEC.md), [docs/OBSERWATOR_RESEARCH.md](docs/OBSERWATOR_RESEARCH.md) |
| Plans, specs and research behind 3.0.0 | `docs/superpowers/` (plans, specs, research) |
| Using the tool as an agent (not developing it) | `AGENTS.md`, `llms.txt` (derived, never edited by hand) |

## 6. Session workflow

1. Start (DEV-17.1): read this file and [docs/PROGRESS.md](docs/PROGRESS.md), run `git status` and `git log --oneline -10`, confirm the branch, list open GitHub issues labelled `request`.
2. Plan a change of a public interface or across several modules and get it approved (DEV-17.4); record decisions with alternatives as ADRs in [docs/DECISIONS.md](docs/DECISIONS.md).
3. Work on a topic branch (`feature/*`, `hotfix/*`); commit in this repository (DEV-3.5).
4. Before the last commit: `scripts/gate.sh` green, [docs/CHANGELOG.md](docs/CHANGELOG.md) and [docs/PROGRESS.md](docs/PROGRESS.md) updated (DEV-17.3).

## 7. Cross-project context

IMGWTools is a tool of the Nogat ecosystem; its entry (interfaces, provided contracts `imgw-store/1`, `imgw-meta/1`, ..., data sources) is `IMGWTools` in [ecosystem.yaml](https://github.com/Daldek/Nogat/blob/main/ecosystem.yaml). Hydrolog has no package dependency on it (it reads the CSV of `imgw series export`); Hydrograf and Hydraulik call `fetch_pmaxtp`; Kartograf is a neighbour. Store consumers: **Archiwista** (public read API only; IMGW-PIB and ČHMÚ through the same adapter, `provider` fields, read-only `kind="observation"` entries; it owns the projects that pin store versions, `archiwista-project/1`, ADR-008) and **Retman** (command catalog: `command_schema` — English by default, `lang="pl"` for Polish — `x-imgw.writes`/`network`, `validate_command`, `format_command`, `check_command`, `run_command`). What a consumer changes for the data output (ADR-007): [docs/CHANGELOG.md](docs/CHANGELOG.md), "Migration guide: data output". Cross-project analysis: [docs/HISTORY.md](docs/HISTORY.md).

## Deviations

Deviations from the Nogat standard (DEV-1.2), one line each.

- DEV-7.3: `tests/` is checked by mypy with the `tests.*` override of `pyproject.toml` (`disallow_untyped_defs`, `disallow_incomplete_defs`, `disallow_untyped_calls`, `disallow_untyped_decorators`, `check_untyped_defs` off): the test functions and fixtures are not annotated. `src/` is `strict` without overrides, except `pyarrow` (no type information: `ignore_missing_imports`).
- DEV-19.5, DEV-19.6: the two files of `imgw pmaxtp sync --output-dir` are named by the cell indices of the answer, so only a call that gives `--ind-x` and `--ind-y` is refused before the request; any other is checked after the one small answer and before the first file is written (ADR-007 D3).
