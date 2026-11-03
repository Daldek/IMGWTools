# IMGWTools — Testing

Test layout, markers and how to run the tests, moved out of [CLAUDE.md](../CLAUDE.md) (Nogat standard 1.0, DOC-3.2). Test strategy and plan: [TEST_PLAN.md](TEST_PLAN.md).

The project includes unit and contract tests for the public API, CLI, REST, MCP and web GUI; all run offline (`respx` mocks or packaged recordings).

## Running Tests

Run tests and checks through uv (`uv sync --locked` first): the global Python may have an
older non-editable `imgwtools` installed, which shadows the local `src/`.

```bash
# The gate (DEV-7.6): ruff format --check, ruff check, mypy, pytest + coverage, commit step
scripts/gate.sh

# Run all offline tests (live tests are deselected by the default marker expression)
uv run pytest

# Run with coverage (the gate enforces fail_under = 80)
uv run pytest --cov=imgwtools

# Run specific test file
uv run pytest tests/unit/test_models.py -v

# Lint and types
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
```

## Test Structure

|File|Tests|Description|
|---|---|---|
|`tests/conftest.py`|-|Shared fixtures; autouse `isolated_reference_dir` (`settings.reference_dir` in a temporary directory)|
|`tests/unit/test_public_store_api.py`|182|`__all__` == spec §13.12 + ČHMÚ + `agent_guide`, removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|142|CLI generated from the catalog: envelope, errors, exit codes, streams, help languages|
|`tests/unit/test_api_commands.py`|150|REST routes from the catalog, problem+json, write guard, refused request options, `Accept-Language`|
|`tests/unit/test_command_schema.py`|93|`command_schema`, `imgw-commands/1`|
|`tests/unit/test_commands.py`|51|Catalog, validation, `run_command`/`check_command`, paging|
|`tests/unit/test_command_for_version.py`|19|`command_for_version` on `complete_pl_cz` and a PMAXTP cell: the call of each family, its line read back, its offline plan of the same file; refusals `unsupported`, `not_found`, `data_error`, `validation_error`|
|`tests/unit/test_fetch_live.py`|66|Live functions with `respx`|
|`tests/unit/test_datasets.py`|59|Registry, aliases, `archive_files`, `YearsArg`|
|`tests/unit/test_parsers.py`|50|Hydro/meteo/station-list parsers|
|`tests/unit/test_exceptions.py`|49|`ERROR_CODES`, codes and details, file-system errors|
|`tests/unit/test_messages.py`|11|Message catalog: both languages, call sites against entries, Polish literals left|
|`tests/unit/test_store_*.py` (IMGW), `test_series_export.py`|316|Store writer, sync, series, catalog, pmaxtp, reader, incremental scan, export, types, fixtures, marker (`test_store_marker.py`)|
|`tests/unit/test_*_chmi.py`, `test_parsing_chmi.py`, `test_store_content.py`|351|ČHMÚ: parsers, registry, listing sync, catalog, series, export, commands, stations, content form|
|`tests/unit/test_catalog_effects.py`, `test_catalog_i18n.py`, `test_agent_guide.py`, `test_mcp_*.py`|182|Agents: effects = behavior, English texts, guide drift test, MCP tools/calls/stdio/HTTP|
|`tests/unit/test_web_app.py`|45|Web GUI|
|`tests/unit/test_cli_interrupt.py` (with `interrupt_driver.py`)|6|SIGINT and SIGTERM of real plain writes (`datasets download -o`, `store export --output`): exit codes, no staging directory, old target whole|
|`tests/unit/test_output.py`, `test_plain_output.py`|36|Plain output (ADR-007): target list, conflicts, staging and its cleanup, `files[]`, `--check` plan|
|`tests/unit/test_default_root.py`, `test_environment.py`|43|Default root and its source (`IMGW_ROOT`, `nogat.toml`, `<data_dir>/imgw`), REST and MCP write refusals, `nogat.toml` settings|
|`tests/unit/test_library_install.py`|3|Wheel built from the checkout, installed without extras into a fresh `uv` venv: `import imgwtools` and `list_commands` run (marker `slow`, ~2 s, in the gate)|
|`tests/unit/` other files|214|fetch, models, stations, urls, coverage, download_archives, fixture builder, reference data, CLI admin/main, API main|
|`tests/contract/test_interface_contract.py`|82|Python = CLI = REST for all 28 REST commands, error matrix, paging|
|`tests/contract/test_command_lines.py`|161|Every example call of the catalog: `parse_command` reads its line, `validate_command` accepts it, `format_command` writes the same line|
|`tests/contract/test_chmi_contract.py`|63|IMGW-15..19 on `complete_pl_cz`; Python = CLI = REST = MCP for ČHMÚ runs|
|`tests/contract/test_mcp_contract.py`, `test_mcp_http_contract.py`|85|MCP (stdio, `/mcp`) = Python = CLI = REST for every contract case and error code|
|`tests/contract/` other files|12|Store contract (sidecar core of every kind of version), CLI = API parity|
|`tests/live/test_interfaces_live.py`|45|Live IMGW-PIB: 30 commands × Python/`imgw`/REST, 6 live errors, MCP leg (`-k imgw_mcp`, 8 commands); marker `live`|
|`tests/live/test_chmi_live.py`|22|Live ČHMÚ (opendata.chmi.cz) through Python/CLI/REST/MCP with a request log; marker `live`|

**Total: 2538 tests** (`pytest --collect-only`, 2026-10-31): 2471 offline, 67 live (`uv run pytest tests/live -m live`; JSON report via `IMGW_LIVE_REPORT=<file>`). The counts of the rows above were recounted the same day with `pytest --collect-only -q`.

## Tests (from README)

Test instructions from the README (moved unchanged).

The project includes unit and contract tests for the public API, CLI, REST, MCP and Web GUI. All run offline: the network is mocked (`respx`) or replayed from recordings in `tests/fixtures/store/`.

### Running the tests

```bash
# Gate: ruff format --check, ruff check, mypy, pytest with coverage (offline), commit check
scripts/gate.sh

# All offline tests (`live` tests are skipped by default)
uv run pytest

# With code coverage
uv run pytest --cov=imgwtools
```

### Test structure

```
tests/
├── conftest.py              # Shared fixtures; autouse isolated_reference_dir (settings.reference_dir in tmp)
├── fixtures/store/          # Synthetic archives, listings and recorded HTTP responses of IMGW-PIB and ČHMÚ (fictional stations)
├── fixtures/export_golden/  # Golden files of archive export (CSV with CRLF, JSONL)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets*.py, test_coverage*.py, test_download_archives*.py, test_parsing_chmi.py
│   ├── test_store_*.py, test_series_export.py          # store: writer, sync, series, catalog, pmaxtp, reader, export, content
│   ├── test_fixture_builder*.py                        # imgwtools.testing (complete, complete_pl_cz)
│   ├── test_commands*.py, test_command_schema.py       # command catalog, command_schema
│   ├── test_catalog_effects.py, test_catalog_i18n.py   # command effects, English descriptions
│   ├── test_agent_guide.py                             # AGENTS.md and llms.txt (drift test)
│   ├── test_mcp_*.py                                   # MCP server: tools, calls, stdio, /mcp
│   ├── test_exceptions.py                              # error code registry
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py   # CLI, REST and Web GUI
│   ├── test_reference_data.py                          # python -m imgwtools.reference_data
│   └── test_public_store_api.py                        # public exports contract
├── contract/                # store contract, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19)
└── live/                    # live regression (marker `live`, outside the gate): IMGW-PIB 30 commands × Python/CLI/REST + MCP; ČHMÚ
```

**Total: 2513 tests** (`pytest --collect-only`, 2026-10-31): 2446 offline and 67 live (marker `live`, run explicitly with `-m live`):

```bash
uv run pytest tests/live/test_interfaces_live.py -m live   # IMGW-PIB: 45 tests
uv run pytest tests/live -m live -k imgw_mcp               # the MCP leg only (imgw mcp)
uv run pytest tests/live/test_chmi_live.py -m live         # ČHMÚ: 22 tests, approx. 31 MB
```

JSON report of a run: `IMGW_LIVE_REPORT=<file>`; the ČHMÚ test writes a request log of each interface (Python, CLI, REST, MCP) and reports the number of requests and bytes (`-s`).
