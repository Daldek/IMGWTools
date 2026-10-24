# IMGWTools — Testing

Test layout, markers and how to run the tests, moved out of [CLAUDE.md](../CLAUDE.md) (Nogat standard 2.1, DOC-3.2). Test strategy and plan: [TEST_PLAN.md](TEST_PLAN.md).

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
|`tests/unit/test_public_store_api.py`|192|`__all__` == spec §13.12 + ČHMÚ + `agent_guide`, removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|155|CLI generated from the catalog: envelope, errors, exit codes, streams, help languages|
|`tests/unit/test_api_commands.py`|113|REST routes from the catalog, problem+json, write guard, `Accept-Language`|
|`tests/unit/test_command_schema.py`|102|`command_schema`, `imgw-commands/1`|
|`tests/unit/test_commands.py`|98|Catalog, validation, `run_command`/`check_command`, paging|
|`tests/unit/test_fetch_live.py`|66|Live functions with `respx`|
|`tests/unit/test_datasets.py`|59|Registry, aliases, `archive_files`, `YearsArg`|
|`tests/unit/test_project.py`|55|`imgw-project/1`|
|`tests/unit/test_parsers.py`|50|Hydro/meteo/station-list parsers|
|`tests/unit/test_exceptions.py`|50|`ERROR_CODES`, codes and details|
|`tests/unit/test_store_*.py` (IMGW), `test_series_export.py`|210|Store writer, sync, series, catalog, pmaxtp, reader, export, types, fixtures|
|`tests/unit/test_*_chmi.py`, `test_parsing_chmi.py`, `test_store_content.py`|360|ČHMÚ: parsers, registry, listing sync, catalog, series, export, commands, stations, projects, content form|
|`tests/unit/test_catalog_effects.py`, `test_catalog_i18n.py`, `test_agent_guide.py`, `test_mcp_*.py`|179|Agents: effects = behavior, English texts, guide drift test, MCP tools/calls/stdio/HTTP|
|`tests/unit/test_web_app.py`|45|Web GUI|
|`tests/unit/` other files|152|fetch, models, stations, urls, coverage, download_archives, fixture builder, reference data, CLI admin/main, API main|
|`tests/contract/test_interface_contract.py`|81|Python = CLI = REST for all 28 REST commands, error matrix, paging|
|`tests/contract/test_chmi_contract.py`|68|IMGW-15..19 on `complete_pl_cz`; Python = CLI = REST = MCP for ČHMÚ runs|
|`tests/contract/test_mcp_contract.py`, `test_mcp_http_contract.py`|87|MCP (stdio, `/mcp`) = Python = CLI = REST for every contract case and error code|
|`tests/contract/` other files|15|Store contract, CLI = API parity, project contract|
|`tests/live/test_interfaces_live.py`|54|Live IMGW-PIB: 38 commands × Python/`imgw`/REST, 6 live errors, MCP leg (`-k imgw_mcp`, 9 commands); marker `live`|
|`tests/live/test_chmi_live.py`|26|Live ČHMÚ (opendata.chmi.cz) through Python/CLI/REST/MCP with a request log; marker `live`|

**Total: 2213 tests** (`pytest --collect-only`, 2026-10-19): 2134 offline, 79 live (`uv run pytest tests/live -m live`; JSON report via `IMGW_LIVE_REPORT=<file>`).
