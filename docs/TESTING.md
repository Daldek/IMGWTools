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
|`tests/unit/test_public_store_api.py`|180|`__all__` == spec §13.12 + ČHMÚ + `agent_guide`, removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|141|CLI generated from the catalog: envelope, errors, exit codes, streams, help languages|
|`tests/unit/test_api_commands.py`|150|REST routes from the catalog, problem+json, write guard, refused request options, `Accept-Language`|
|`tests/unit/test_command_schema.py`|93|`command_schema`, `imgw-commands/1`|
|`tests/unit/test_commands.py`|51|Catalog, validation, `run_command`/`check_command`, paging|
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
|`tests/contract/test_interface_contract.py`|81|Python = CLI = REST for all 28 REST commands, error matrix, paging|
|`tests/contract/test_command_lines.py`|161|Every example call of the catalog: `parse_command` reads its line, `validate_command` accepts it, `format_command` writes the same line|
|`tests/contract/test_chmi_contract.py`|63|IMGW-15..19 on `complete_pl_cz`; Python = CLI = REST = MCP for ČHMÚ runs|
|`tests/contract/test_mcp_contract.py`, `test_mcp_http_contract.py`|83|MCP (stdio, `/mcp`) = Python = CLI = REST for every contract case and error code|
|`tests/contract/` other files|12|Store contract (sidecar core of every kind of version), CLI = API parity|
|`tests/live/test_interfaces_live.py`|45|Live IMGW-PIB: 30 commands × Python/`imgw`/REST, 6 live errors, MCP leg (`-k imgw_mcp`, 8 commands); marker `live`|
|`tests/live/test_chmi_live.py`|22|Live ČHMÚ (opendata.chmi.cz) through Python/CLI/REST/MCP with a request log; marker `live`|

**Total: 2513 tests** (`pytest --collect-only`, 2026-10-31): 2446 offline, 67 live (`uv run pytest tests/live -m live`; JSON report via `IMGW_LIVE_REPORT=<file>`). The counts of the rows above were recounted the same day with `pytest --collect-only -q`.

## Testy (z README)

Instrukcje testów z README (po polsku, bez zmian).

Projekt zawiera testy jednostkowe i kontraktowe publicznego API, CLI, REST, MCP i Web GUI. Wszystkie działają offline: sieć jest mockowana (`respx`) albo odtwarzana z nagrań w `tests/fixtures/store/`.

### Uruchamianie testów

```bash
# Bramka: ruff format --check, ruff check, mypy, pytest z pokryciem (offline), kontrola commitów
scripts/gate.sh

# Wszystkie testy offline (testy `live` są domyślnie pomijane)
uv run pytest

# Z pokryciem kodu
uv run pytest --cov=imgwtools
```

### Struktura testów

```
tests/
├── conftest.py              # Wspólne fixtures; autouse isolated_reference_dir (settings.reference_dir w tmp)
├── fixtures/store/          # Syntetyczne archiwa, listingi i nagrane odpowiedzi HTTP IMGW-PIB i ČHMÚ (fikcyjne stacje)
├── fixtures/export_golden/  # Złote pliki eksportu archiwów (CSV z CRLF, JSONL)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets*.py, test_coverage*.py, test_download_archives*.py, test_parsing_chmi.py
│   ├── test_store_*.py, test_series_export.py          # magazyn: writer, sync, series, catalog, pmaxtp, reader, export, content
│   ├── test_fixture_builder*.py                        # imgwtools.testing (complete, complete_pl_cz)
│   ├── test_commands*.py, test_command_schema.py       # katalog komend, command_schema
│   ├── test_catalog_effects.py, test_catalog_i18n.py   # skutki komend, opisy angielskie
│   ├── test_agent_guide.py                             # AGENTS.md i llms.txt (test dryfu)
│   ├── test_mcp_*.py                                   # serwer MCP: narzędzia, wywołania, stdio, /mcp
│   ├── test_exceptions.py                              # rejestr kodów błędów
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py   # CLI, REST i Web GUI
│   ├── test_reference_data.py                          # python -m imgwtools.reference_data
│   └── test_public_store_api.py                        # kontrakt eksportów publicznych
├── contract/                # kontrakt magazynu, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19)
└── live/                    # regresja na żywo (znacznik `live`, poza bramką): IMGW-PIB 30 komend × Python/CLI/REST + MCP; ČHMÚ
```

**Łącznie: 2513 testów** (`pytest --collect-only`, 2026-10-31): 2446 offline i 67 na żywo (znacznik `live`, uruchamiane jawnie `-m live`):

```bash
uv run pytest tests/live/test_interfaces_live.py -m live   # IMGW-PIB: 45 testów
uv run pytest tests/live -m live -k imgw_mcp               # sama noga MCP (imgw mcp)
uv run pytest tests/live/test_chmi_live.py -m live         # ČHMÚ: 22 testy, ok. 31 MB
```

Raport JSON przebiegu: `IMGW_LIVE_REPORT=<plik>`; test ČHMÚ zapisuje dziennik żądań każdego interfejsu (Python, CLI, REST, MCP) i podaje liczbę żądań i bajtów (`-s`).
