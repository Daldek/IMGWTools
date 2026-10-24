# IMGWTools — Codebase Reference

Code and module reference moved out of [CLAUDE.md](../CLAUDE.md) (Nogat standard 2.1, DOC-3.2): package tree, public library API, command catalog, data sources and formats, deployment, versioned store. Architecture and component diagrams: [ARCHITECTURE.md](ARCHITECTURE.md); tests: [TESTING.md](TESTING.md); task-oriented usage: [USAGE.md](USAGE.md).

## Package Tree

```
src/imgwtools/
├── __init__.py           # PUBLIC API - single __all__ (spec §13.12, ČHMÚ spec §9.1, agent_guide)
├── _version.py           # Version: 3.0.0
├── fetch.py              # PUBLIC: live data (fetch_*), PMAXTP, download_archives, download_*_data
├── models.py             # PUBLIC: Data models (PMaXTPData, HydroCurrentData, NormalizedRecord, Measurement, ...)
├── stations.py           # PUBLIC: find_stations (live lists of IMGW-PIB and ČHMÚ, or store)
├── datasets.py           # PUBLIC: Provider registry (providers, get_provider) + 17 dataset descriptors, archive_files
├── commands.py           # PUBLIC: Command catalog (38 commands, PL + EN texts, effects), run_command, command_schema, list_commands
├── agent_guide.py        # PUBLIC: agent_guide (AGENTS.md / llms.txt), MCP server instructions
├── coverage.py           # PUBLIC: summarize_coverage (per-station periods for ČHMÚ)
├── project.py            # PUBLIC: imgw-project/1 manifests (restore by content for ČHMÚ)
├── exceptions.py         # PUBLIC: IMGWError hierarchy + ERROR_CODES registry (title as a catalog message)
├── messages/             # Message catalog: message(), Message, localize(), one module of Text(en, pl) per area (ADR-006)
├── urls.py               # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
├── parsers.py            # PUBLIC: Parser re-exports (IMGW-PIB hydro/meteo, ČHMÚ, station lists)
├── testing.py            # PUBLIC: build_fixture_store (complete, complete_pl_cz, ...), fixture_files
├── _jsonable.py          # Single JSON converter (envelope, relative store paths)
├── reference_data.py     # python -m imgwtools.reference_data (data/ reference files)
├── config.py             # Settings (pydantic-settings, IMGW_*)
├── _data/                # Poland/Czechia borders (Natural Earth), agents/ guide templates, packaged fixtures
├── _parsing/             # common.py, hydro.py, meteo.py, stations.py, chmi.py (ČHMÚ files, listings, metadata)
├── store/                # Versioned store [Parquet: imgwtools[store]]
│   ├── types.py          # Dataclasses: StorePlan, CommandResult, Page, StoreEntry, ...
│   ├── writer.py         # init_store, write_archive (atomic, append-only, content_unchanged + observations)
│   ├── content.py        # Canonical content forms (chmi-json/1), content_sha256
│   ├── sync.py           # check_store, sync_store (IMGW-PIB: listing + HEAD; ČHMÚ: directory listing)
│   ├── series.py         # check_series, build_series (Parquet)
│   ├── catalog.py        # check_catalog, build_catalog (stations.geojson per provider)
│   ├── pmaxtp.py         # check_pmaxtp, sync_pmaxtp, read_pmaxtp
│   ├── reader.py         # store_info, iter_store, current_version, read_*, select/summarize_series
│   └── export.py         # export_archive, export_series (CSV/JSONL, file or line iterator)
├── api/                  # FastAPI REST API [optional: imgwtools[api]]
│   ├── main.py           # App entry point (/health, /api/v1, /llms.txt, /mcp, web router, static)
│   ├── routes/commands.py# Routes generated from command_schema() (x-imgw.rest), Accept-Language
│   ├── errors.py         # application/problem+json handlers, hide_server_paths, accept_language
│   └── schemas.py        # HealthCheck
├── cli/                  # Typer/Click CLI [optional: imgwtools[cli]]
│   ├── main.py           # Entry point (imgw command): version, server, mcp, admin + catalog groups
│   ├── _dispatch.py      # ImgwGroup + register_catalog: the only CLI adapter of the catalog (IMGW_LANG)
│   └── admin.py          # API key management
├── mcp/                  # MCP adapter [optional: imgwtools[mcp]]; not in imgwtools.__all__
│   ├── _tools.py         # Tools from the catalog (modes read/write/http, schemas, annotations)
│   ├── _calls.py         # Calls: stdio (check_command/run_command), http (REST routes in process)
│   └── server.py         # create_server, run_stdio, http_app
└── web/                  # Web GUI (HTMX + Jinja2)
    ├── app.py            # Web routes
    ├── templates/        # Jinja2 templates
    └── static/           # CSS, JavaScript

AGENTS.md, llms.txt       # Agent guide — DERIVED files: regenerate with `imgw commands guide` (drift test)
```

## CLI Examples

```bash
# CLI examples (stdout = one-line JSON envelope imgw-result/1)
imgw version                                         # Show version
imgw server --host 0.0.0.0 --port 8000               # Run API server
imgw datasets list -k hydro                          # Dataset registry
imgw datasets files -d hydro/dobowe -y 2023 -m 1     # Archive URLs (no download)
imgw datasets download -d hydro/dobowe -y 2023 -m 1 -o dane   # Download archives
imgw stations find -k hydro -q wisla --limit 20      # Search station lists
imgw current hydro -s 150160180                      # Current hydro data
imgw current warnings -k meteo                       # Warnings
imgw pmaxtp fetch --lat 52.23 --lon 21.01            # PMAXTP data (method POT)
imgw store init --root /dane/imgw                    # Versioned store
imgw store sync --root /dane/imgw -d pl.imgw.hydro_daily -y 2024 --check   # Plan only
imgw series summary --root /dane/imgw -d hydro/dobowe -s 149180020
imgw datasets providers                              # IMGW-PIB and CHMI
imgw stations find -k hydro -q spindleruv --provider CHMI   # ČHMÚ station (WIGOS id)
imgw store check --root /dane/imgw -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2025   # ČHMÚ listing check
imgw store catalog --root /dane/imgw --provider CHMI # ČHMÚ station catalog
imgw commands schema --command "store sync"          # JSON Schema of a command
imgw commands schema --command "store sync" --lang en   # Same, English texts
imgw store sync --schema                             # Same, via the command itself
imgw commands guide --format agents --lang pl --path AGENTS.md   # Regenerate AGENTS.md
imgw mcp [--allow-writes] [--lang en]                # MCP server on stdio (imgwtools[mcp])
imgw admin keys                                      # List API keys
imgw admin create --name "User1"                     # Create API key
imgw admin revoke <key_id>                           # Revoke API key
imgw admin delete <key_id>                           # Delete API key
imgw admin stats                                     # Show API key statistics
```

## Public Library API

The public API is exposed via `from imgwtools import ...` (one `__all__`, also re-exported from the defining modules). The first object argument may be positional; every further argument is keyword-only. Station codes are always `str` (`station_code`): 9 digits for IMGW-PIB, a WIGOS id for ČHMÚ (`STATION_CODE_PATTERN`).

**Live Data and Downloads:**
|Function|Description|
|---|---|
|`fetch_pmaxtp(latitude, longitude, *, method="POT")`|Get PMAXTP precipitation data (`PMaXTPResult`)|
|`fetch_hydro_current(*, station=None)`|Current hydro data (`HydroCurrentData`)|
|`fetch_meteo_current(*, station=None)`|Current meteo data (`MeteoCurrentData`)|
|`fetch_synop(*, station=None, station_name=None)`|Current synop data (`SynopData`)|
|`fetch_warnings(*, kind=None)`|Hydro/meteo warnings (`WarningData`; `None` = both)|
|`fetch_hydro_states(*, main_only=False)`|Hydro stations with coordinates and water state (`HydroState`)|
|`find_stations(*, kind=None, query=None, source="live", root=None, provider=None)`|Search IMGW-PIB and/or ČHMÚ station lists, live or from the store (`StationListEntry`)|
|`download_archives(dataset, /, *, years, months, params, stations, output)`|Download archives into a server-path tree (`DownloadReport`; ČHMÚ 404 → `not_published`)|
|`download_hydro_data(interval, year, month, param)`|One hydro archive as `DownloadResult` (bytes in `.data`)|
|`download_meteo_data(interval, subtype, year, month)`|One meteo archive as `DownloadResult`|

Every live function has an `*_async` twin with identical arguments.

**Registry and URLs:**
|Function|Description|
|---|---|
|`providers()`, `get_provider(id or key_prefix)`|Provider registry (`ProviderDescriptor`: `IMGW-PIB`, `CHMI`)|
|`datasets(*, kind=None, provider=None)`|Dataset descriptors (`DatasetDescriptor`; 17)|
|`get_dataset(dataset)`|Descriptor by key, slug or legacy alias|
|`archive_files(dataset, /, *, years=None, months=None, params=None, stations=None)`|Archive files with URLs (`ArchiveFile`; `stations` required for `cz.chmi.*`)|
|`build_pmaxtp_url(latitude, longitude, *, method="POT")`|PMAXTP API URL|
|`build_api_url(endpoint, /, *, station, station_name)`|IMGW real-time API URL|

**Versioned Store** (also in `imgwtools.store`):
|Function|Description|
|---|---|
|`init_store`, `open_store`, `store_info`, `iter_store`|Create/open/describe/scan a store|
|`check_store`, `sync_store`|Freshness plan (IMGW-PIB: listing + HEAD; ČHMÚ: one directory listing, `stations`) and download of new/missing archives|
|`check_series`, `build_series`|Parquet station series|
|`check_catalog`, `build_catalog`|`stations.geojson` catalog of one provider (`provider="IMGW-PIB"` default, `"CHMI"`)|
|`check_pmaxtp`, `sync_pmaxtp`, `read_pmaxtp`|PMAXTP grid cells|
|`current_version(root, /, *, slot)`|Current version of a slot (`archive:<key>:<file>`, `series:<key>`, ...)|
|`read_meta`, `read_archive`, `read_station_list(root, /, *, kind, provider="IMGW-PIB")`, `read_catalog(version=None, /, *, root=None, provider=None)`, `read_series_index`, `read_series`|Offline readers|
|`select_series`, `summarize_series`|Series selection and coverage|
|`export_archive`, `export_series`|CSV/JSONL export to a file or as a line iterator|

**Command Catalog:**
|Function|Description|
|---|---|
|`command_schema(command=None, /, *, lang="pl")`|JSON Schema of the catalog or one command (`x-imgw`: function, CLI, REST, rules, `writes`, `network`, `idempotent`, `operation_id`); `lang="en"` = English texts|
|`list_commands(*, lang="pl")`|Catalog summary `imgw-command-list/1`: per command the name, `operation_id`, one-sentence summary, effects, check twin, result and REST route (`imgw commands list`, MCP `imgw_commands_list`)|
|`data_commands(*, provider=None)`|Catalog entries (`DataCommand`; `provider` = view of one provider)|
|`validate_command(command, /, *, options)`|Normalized options or `IMGWValidationError` with `details.option`|
|`format_command(command, /, *, options)`|Equivalent CLI command line|
|`run_command(command, /, *, options)`|Run a command → `CommandResult` (list commands → `Page`)|
|`check_command(command, /, *, options)`|Plan of a command without side effects → `CommandResult`|
|`agent_guide(*, format="agents", lang="pl", path=None)`|Agent guide `AGENTS.md`/`llms.txt` (line iterator or file)|

**Projects:** `init_project`, `open_project`, `set_project_store`, `add_project_task`, `remove_project_task`, `check_project`, `download_project`, `get_project_status`, `verify_project`.

**Data Models:**
|Model|Description|
|---|---|
|`PMaXTPData`|Precipitation quantiles (ks, sg, rb) with `get_precipitation(duration, prob)`|
|`PMaXTPResult`|Complete PMAXTP result with metadata|
|`HydroCurrentData`, `MeteoCurrentData`, `SynopData`|Current measurements (`station_code`)|
|`WarningData`|Weather/hydro warning (`kind`, `event`, `level`, ...)|
|`HydroState`|Station with coordinates and `water_state`|
|`StationListEntry`|Station list row (`kind`, `station_code`, `name`, `provider`, ...)|
|`NormalizedRecord`, `Measurement`|Normalized archive/series record with value flags (`Measurement.quality`, `source_flag` for ČHMÚ meteo)|
|`ProviderDescriptor`|Data provider: id, names, country, key prefix, base URL, license, station code pattern, datasets|
|`CommandResult`, `Page`|Result envelope (`imgw-result/1`) and list page (`items`, `total`, `limit`, `offset`)|

**Exceptions** (every `IMGWError` has `code` from `ERROR_CODES` and `details`):
|Exception|Default code|Description|
|---|---|---|
|`IMGWError`|`internal_error`|Base exception|
|`IMGWValidationError`|`validation_error`|Input validation errors (e.g. coords outside Poland)|
|`IMGWConnectionError`|`source_unavailable`|Connection/timeout/HTTP errors|
|`IMGWDataError`|`data_error`|Data parsing errors|
|`IMGWStoreError`|`store_unavailable`|Bad/unsupported store root (`not_found` for missing versions)|
|`IMGWStoreConflictError`|`conflict`|Collisions, races, non-atomic filesystems|
|`IMGWStoreDependencyError`|`missing_dependency`|pyarrow missing|
|`IMGWProjectError`|`validation_error`|Project manifest/lock/pins|
|`IMGWCancelledError`|`cancelled`|Cancelled operation|

**Parsers:** `parse_zip_file(zip_data, interval)`, `parse_daily_csv`, `parse_monthly_csv`, `parse_semi_annual_csv`, `parse_stations_csv(content, /, *, kind)`, `parse_meteo_climate_daily`, `parse_meteo_precip_daily`, `parse_chmi_hydro_daily`, `parse_chmi_meteo_daily`, `parse_chmi_stations`, `normalize_archive`, `IMGW_ENCODING` (CP1250).

## Key Module: `commands.py`

The command catalog is the single source of options, validation, help texts and result types:
- `_CATALOG` — 38 `DataCommand` entries (spec §13.3 + `datasets providers` + `commands list` + `commands guide`), each calling exactly one public function; every text has a Polish and an English variant (`description_en`, `help_en`, `rules_en`, `_GROUPS_EN`); the first sentence of a description is the `summary` of `commands list` (at most 100 characters)
- `command_schema(lang=)` — JSON Schema per command with `x-imgw` (`function`, `check`, `result_type`, `cli.flags`, `rest.method/path/server_options/local_options`, `rules`, `writes`, `network`, `idempotent`, `operation_id`), plus `groups`, `errors`, `exit_codes`, `lang`; `operation_id` is `imgw_<group>_<verb>` (ECO-018): the MCP tool name and the REST `operationId`
- `run_command`/`check_command` — dispatch by `inspect.signature`, paging (`limit`/`offset`) for the 12 list commands, notices deduplicated in the envelope
- CLI (`cli/_dispatch.py`), REST (`api/routes/commands.py`) and MCP tools (`mcp/_tools.py`) are generated from `command_schema()`; never add hand-written commands there
- Changing catalog texts, the dataset/provider/error registries or the templates in `_data/agents/` requires regenerating `AGENTS.md` and `llms.txt` in the same change (`imgw commands guide --format agents --lang pl --path AGENTS.md`, `--format llms --lang pl --path llms.txt`); `tests/unit/test_agent_guide.py` compares the bytes

## External Data Sources

### Station Lists (CSV)
- **Hydro stations**: `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/lista_stacji_hydro.csv`
  - Format: `ID, nazwa, rzeka (id_cieku), kod`
  - Encoding: CP1250
- **Meteo stations**: `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/wykaz_stacji.csv`
  - Format: `ID, nazwa, kod`
  - Encoding: CP1250

### Real-time API
- **Hydro data**: `https://danepubliczne.imgw.pl/api/data/hydro`
- **Meteo data**: `https://danepubliczne.imgw.pl/api/data/meteo`
- **Synop data**: `https://danepubliczne.imgw.pl/api/data/synop`
- **Warnings**: `https://danepubliczne.imgw.pl/api/data/warningshydro`, `.../warningsmeteo`

### Map Stations API
- **Hydro stations with coordinates**: `https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false`
  - Requires headers: `User-Agent`, `Referer: https://hydro.imgw.pl/`
  - Returns: 900+ stations with lat/lon and water state (alarm, warning, high, medium, low, etc.)
  - Public access: `fetch_hydro_states()`, `imgw current hydro-states`, `GET /api/v1/current/hydro-states`

### Station Pages
- **Hydro**: `https://hydro.imgw.pl/#/station/hydro/{station_code}`
- **Meteo**: `https://hydro.imgw.pl/#/station/meteo/{station_code}`

### ČHMÚ (opendata.chmi.cz, ADR-003)
- **Hydro daily** (`cz.chmi.hydro_daily`): `https://opendata.chmi.cz/hydrology/historical/data/daily/H_<WIGOS>_DQ_<year>.json` — one JSON per station and calendar year (from 1887); `HD`/`QD`/`TD` → H [cm], Q [m3/s], T [°C]
- **Meteo daily** (`cz.chmi.meteo_daily`): `meteorology/climate/historical_csv/data/daily/{precipitation,temperature}/dly-<WIGOS>-{SRA,T,TMA,TMI}.csv` — four CSV files per station with the whole station history; `QUALITY` 0–5 and `FLAG` kept as `quality`/`source_flag`
- **Station lists** (`cz.chmi.hydro_stations`, `cz.chmi.meteo_stations`): `hydrology/historical/metadata/meta1.json`, `meteorology/climate/historical/metadata/meta1.json` (JSON envelope `zaznamID`/`datumVytvoreni` changes with every regeneration → canonical form `chmi-json/1`)
- **Catalog sources**: `hydrology/now/metadata/meta1.json` (SPA thresholds), `meta3.json` (`HLGP4`), newest `meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json` (directory listing); meteo `GEOGR1` = longitude, hydro `GEOGR1` = latitude
- **Inventory and freshness**: nginx directory listings (name, mtime to the minute, size): one GET instead of a HEAD per file; requests are sequential with `User-Agent: imgwtools/<version>`; license CC BY 4.0 (attribution from the registry)
- Out of scope: `now`/`recent` data, hourly data, CAP warnings, PMAXTP

## Command Catalog (CLI, REST and MCP)

CLI command = `imgw <group> <name>`; REST route = `/api/v1/<group>/<name>` (GET options in the query, POST options in a JSON body, `?check=true` on POST = plan without writing); MCP tool = `x-imgw.operation_id` (`imgw_` + name with spaces and `-` → `_`, e.g. `imgw_store_sync`; also the REST `operationId`). "Local" commands have no REST route. Check: twin function used by `--check`/`?check=true`/`check: true`; `—` = no `--check`; "self" = the command is a check.

|Command|Function|Check|REST|
|---|---|---|---|
|`datasets list`|`datasets`|—|`GET /api/v1/datasets/list`|
|`datasets files`|`archive_files`|—|`GET /api/v1/datasets/files`|
|`datasets download`|`download_archives`|`check_command`|local|
|`datasets providers`|`providers`|—|`GET /api/v1/datasets/providers`|
|`stations find`|`find_stations`|`check_command`|`GET /api/v1/stations/find`|
|`current hydro`|`fetch_hydro_current`|`check_command`|`GET /api/v1/current/hydro`|
|`current meteo`|`fetch_meteo_current`|`check_command`|`GET /api/v1/current/meteo`|
|`current synop`|`fetch_synop`|`check_command`|`GET /api/v1/current/synop`|
|`current warnings`|`fetch_warnings`|`check_command`|`GET /api/v1/current/warnings`|
|`current hydro-states`|`fetch_hydro_states`|`check_command`|`GET /api/v1/current/hydro-states`|
|`pmaxtp fetch`|`fetch_pmaxtp`|`check_command`|`GET /api/v1/pmaxtp/fetch`|
|`pmaxtp url`|`build_pmaxtp_url`|—|`GET /api/v1/pmaxtp/url`|
|`pmaxtp check`|`check_pmaxtp`|self|`GET /api/v1/pmaxtp/check`|
|`pmaxtp sync`|`sync_pmaxtp`|`check_pmaxtp`|`POST /api/v1/pmaxtp/sync`|
|`pmaxtp read`|`read_pmaxtp`|—|`GET /api/v1/pmaxtp/read`|
|`store init`|`init_store`|`check_command`|local|
|`store info`|`store_info`|—|`GET /api/v1/store/info`|
|`store scan`|`iter_store`|—|`GET /api/v1/store/scan`|
|`store check`|`check_store`|self|`GET /api/v1/store/check`|
|`store sync`|`sync_store`|`check_store`|`POST /api/v1/store/sync`|
|`store catalog`|`build_catalog`|`check_catalog`|`POST /api/v1/store/catalog`|
|`store export`|`export_archive`|`check_command`|`GET /api/v1/store/export`|
|`series build`|`build_series`|`check_series`|`POST /api/v1/series/build`|
|`series select`|`select_series`|—|`GET /api/v1/series/select`|
|`series read`|`read_series`|—|`GET /api/v1/series/read`|
|`series summary`|`summarize_series`|—|`GET /api/v1/series/summary`|
|`series export`|`export_series`|`check_command`|`GET /api/v1/series/export`|
|`project init`|`init_project`|`check_command`|local|
|`project add`|`add_project_task`|`check_command`|local|
|`project remove`|`remove_project_task`|`check_command`|local|
|`project set-store`|`set_project_store`|`check_command`|local|
|`project download`|`download_project`|`check_project`|local|
|`project check`|`check_project`|self|local|
|`project status`|`get_project_status`|—|local|
|`project verify`|`verify_project`|—|local|
|`commands list`|`list_commands`|—|`GET /api/v1/commands/list`|
|`commands schema`|`command_schema`|—|`GET /api/v1/commands/schema`|
|`commands guide`|`agent_guide`|`check_command`|`GET /api/v1/commands/guide`|

Outside the catalog: `imgw version`, `imgw server` (`--host`, `--port`, `--reload`), `imgw mcp` (`--allow-writes`, `--lang`), `imgw admin keys|create|revoke|delete|stats`, `GET /health`, `GET /api/v1` (name, version, schema route, list of catalog routes), `GET /llms.txt` (agent guide, language from `Accept-Language`), `/mcp` (MCP Streamable HTTP, only with `IMGW_MCP_ENABLED=true`) and the HTML pages.

Effects (`x-imgw.writes`/`x-imgw.network`, ADR-004 D2): `none` = no file changes, `add` = only new files/versions/tasks, `replace` = may replace a user file (`datasets download`, `project remove|set-store|download`); writing options (`x-imgw-writes`): `plan` of `store check`/`project check`, `path` of `store export`/`series export`/`commands guide`. Every writing command has a check twin.

### Options

Option name = function parameter = JSON field; CLI flag = `--` + name with `_` → `-`. Short aliases: `-d` dataset(s), `-y` years, `-m` months, `-s` station(s), `-k` kind, `-q` query, `-o` output, `-r` root, `-f` format, `-p` path; `--lat`/`--lon` alias `--latitude`/`--longitude`. Lists: comma-separated or repeated flag/parameter. `--root` reads `IMGW_STORE_ROOT` (for `stations find` only with `--source store`; rule `DataCommand.env_root_when`, shared with MCP stdio). List commands accept `--limit`/`--offset`. `--check` exists only on commands with a check twin; `--schema` prints the command's schema without running it. `--provider` (`IMGW-PIB`|`CHMI`) in `datasets list`, `stations find`, `store scan` (absent = all) and `store catalog` (default `IMGW-PIB`); `--stations`/`-s` in `datasets files|download`, `store check|sync` (required for `cz.chmi.*`, forbidden for `pl.imgw.*`; `years` dataset-dependent — see `x-imgw.rules`). `--lang pl|en` in `commands schema`/`commands guide`; `IMGW_LANG=pl|en` sets the CLI help language (incl. Typer/Click elements) and the `--lang` default (invalid value → `validation_error`, exit 2).

### Output, errors and exit codes

- CLI stdout: compact one-line JSON envelope `imgw-result/1` (`schema`, `command`, `check`, `status` ok|partial|failed|cancelled, `result`, `notices`); store paths relative to the root. `store export`/`series export` without `--path` stream CSV/JSONL bytes. Progress and notices (once per distinct notice) go to stderr.
- CLI error: stdout empty, last stderr line `{"code", "detail", "details"}`.
- REST: same envelope as the body; errors as `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`); list `limit` default/maximum `IMGW_API_MAX_LIMIT` (1000). `lang` from the query, else `Accept-Language`, else `pl`; `title` of problem+json follows `Accept-Language`; `Content-Language` and `Vary: Accept-Language` on negotiated answers.
- MCP: `structuredContent` = envelope (`isError=false` also for `partial`/`failed`); errors `isError=true` with `{code, title, detail, details}`; lists default to 50 items; streams up to 256 KiB; without `--allow-writes` writing commands return the plan (`check` fixed `true`), refused writes → `forbidden` (`details.reason="writes_disabled"`).

|Code|Title (`title` / `title_en`)|CLI exit|HTTP|
|---|---|---|---|
|`validation_error`|Nieprawidłowe dane wejściowe / Invalid input|2|400|
|`not_found`|Nie znaleziono / Not found|3|404|
|`conflict`|Konflikt stanu / State conflict|4|409|
|`source_unavailable`|Źródło danych niedostępne / Data source unavailable|5|502|
|`missing_dependency`|Brak opcjonalnej zależności / Missing optional dependency|6|503|
|`data_error`|Niepoprawne dane / Invalid data|7|500|
|`store_unavailable`|Magazyn niedostępny / Store unavailable|8|503|
|`io_error`|Błąd systemu plików / File system error|9|500|
|`cancelled`|Operację anulowano / Operation cancelled|130|—|
|`forbidden`|Brak uprawnień do zapisu / Write not permitted|12|403|
|`method_not_allowed`|Niedozwolona metoda HTTP / HTTP method not allowed|—|405|
|`internal_error`|Błąd wewnętrzny / Internal error|1|500|

Envelope status exit codes: `ok` 0, `partial` 10, `failed` 11, `cancelled` 130.

## Data Structure

### Dataset registry (17 descriptors, 2 providers)

|Key|Legacy alias|Store|
|---|---|---|
|`pl.imgw.hydro_daily`|`hydro/dobowe`|yes|
|`pl.imgw.hydro_monthly`|`hydro/miesieczne`|yes|
|`pl.imgw.hydro_semiannual`|`hydro/polroczne_i_roczne`|yes|
|`pl.imgw.meteo_climate_daily`|`meteo/dobowe/klimat`|yes|
|`pl.imgw.meteo_precip_daily`|`meteo/dobowe/opad`|yes|
|`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`|—|yes (station lists)|
|`pl.imgw.pmaxtp`|—|yes (grid cells)|
|`pl.imgw.hydro_phenomena`|— (`hydro/dobowe` with month 13)|download only|
|`pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`|`meteo/miesieczne/klimat\|opad\|synop`|download only|
|`pl.imgw.meteo_climate_terms`|`meteo/terminowe/klimat`|download only|
|`cz.chmi.hydro_daily`|—|yes (per station × calendar year, `stations` required)|
|`cz.chmi.meteo_daily`|—|yes (4 files per station: SRA, T, TMA, TMI; no `years`)|
|`cz.chmi.hydro_stations`, `cz.chmi.meteo_stations`|—|yes (station lists, canonical form `chmi-json/1`)|

`get_dataset`/`archive_files` accept the key, the slug (e.g. `hydro_daily`, `chmi_hydro_daily`) or the legacy alias; results and slots always use the full key. Archive commands (`datasets files|download`) accept 12 datasets, store/series commands 7. Descriptor fields added by ADR-003: `provider`, `archive_scope`, `variable_notes`, `measurement_fields`, `content_form`, `volatile_fields`, `update_signal="listing"`; ADR-004: `title_en`.

### IMGW-PIB hydrological data (1951-2024+)
- `dobowe` (daily):
  - Before 2023: `codz_{year}_{month:02d}.zip` (monthly files; month 13 = `zjaw_` phenomena)
  - From 2023: `codz_{year}.zip` (single yearly file)
- `miesieczne` (monthly): `mies_{year}.zip`
- `polroczne_i_roczne` (semi-annual): `polr_{param}_{year}.zip` (param: T, Q, H)

### IMGW-PIB meteorological data (1950-current)

Real IMGW layout, verified against live server listings (2026-07-05):

**Folders:** 5-year ranges until 2000 (e.g. `1996_2000`), yearly from 2001 (e.g. `2023`).
First folder differs per subtype: klimat `1951_1955`, opad `1950_1955`, synop `1960_1965` (six years); from `1966_1970` all subtypes share the same grid.

**Files per interval/subtype:**
- `miesieczne` (all subtypes): ONE file per folder — `{folder}_m_{k|o|s}.zip` (e.g. `1996_2000_m_s.zip`, `2023_m_s.zip`)
- `dobowe`/`terminowe` klimat & opad: yearly `{year}_{k|o}.zip` until 2000, monthly `{year}_{month:02d}_{k|o}.zip` from 2001
- `dobowe`/`terminowe` synop: PER-STATION files `{folder}_{station}_s.zip` — `get_dataset`/`archive_files` raise `IMGWValidationError` (`details.reason=per_station`)
- `terminowe` opad: dataset does not exist — `IMGWValidationError` (`details.reason=not_published`)

**Subtypes:** `k` (klimat), `o` (opad), `s` (synop)

## Docker Deployment

```bash
cd docker
docker compose up -d
IMGW_MCP_ENABLED=true IMGW_MCP_ALLOWED_HOSTS=dane.example.pl docker compose up -d   # with /mcp
```

Services: app (FastAPI, `python:3.12-slim`, `pip install ".[api,mcp]"`, one uvicorn process), nginx (reverse proxy, `location = /mcp` with the `api_limit` zone, no buffering). Compose passes `IMGW_MCP_ENABLED` (default `false`), `IMGW_MCP_ALLOWED_HOSTS` (default `127.0.0.1,localhost`) and `IMGW_LANG` (default `pl`). No Redis needed.

## Cloud & Deployment Details

### Deployment Model
Aplikacja hostowana na prywatnym serwerze. Komponenty:
- **Nginx** — reverse proxy + HTTPS + rate limiting
- **FastAPI (Uvicorn)** — backend API

### Rate limiting
- Nginx: `limit_req_zone` (10 req/s per IP)
- API keys support rate limits (configured per key, stored in JSON)

### Authorization (Planned)
Klucze API w pliku JSON (`api_keys.json`). Naglowek: `X-API-Key: <token>`

**Note:** API key validation middleware is not yet implemented. Keys are managed via CLI but not enforced in API requests. Store writes over REST use their own token (`IMGW_STORE_WRITE_TOKEN`, sent as `X-API-Key`).

### API versioning
Wszystkie endpointy pod `/api/v1/...`

## Versioned Store (Optional)

Explicit root only (`init_store(root)`, `--root`, `IMGW_STORE_ROOT`); readable offline, also from network shares; one store holds both providers. Writes need a file system with hard links, as Kartograf's store (its ADR-036): versions, observations and the marker are published by `os.link` from `.incoming/`, the main file's sidecar last (it commits the version); FAT/exFAT, some NAS/FUSE and the macOS SMB client → `conflict` with `details.reason="not_atomic"`. A version directory without its sidecar is an interrupted publication (`missing_sidecar`), completed by the next write of the same content under the same label, otherwise removed by hand while no write runs; a failed publication never removes linked data files. Decisions: `docs/DECISIONS.md` ADR-001, ADR-003; contracts: `docs/superpowers/specs/2026-10-17-versioned-store-design.md` (§13 = ADR-002 takes precedence) and `2026-10-18-chmi-provider-design.md` (ČHMÚ).

### Configuration

Resolution (DEV-18.1, `src/imgwtools/_environment.py` and `config.py`): command-line option, `IMGW_<KEY>` variable, the same key in `.env`, `NOGAT_<KEY>` (shared keys `data_dir`, `cache_dir`, `lang`), `[imgw]` then `[nogat]` of `nogat.toml` (user config dir, or `NOGAT_CONFIG`; read with `tomllib`, absence is no error, an unusable file is `validation_error` for every `imgw` call), default. `IMGW_STORE_WRITE_TOKEN` is a credential: environment only, never from the file, never printed. Nothing is written to the working directory. `imgw config show [--json]` reports every key with its source (`imgw-config/1`, DEV-18.6; outside the catalog, `config_cmd.py`).

|Variable|Default|Description|
|---|---|---|
|`IMGW_STORE_ROOT`|unset|Absolute store root of the REST server; CLI default for `--root`. Unset → store routes 503 `store_unavailable`|
|`IMGW_STORE_WRITES_ENABLED`|`false`|Allow REST writes (`POST` store/series/pmaxtp routes)|
|`IMGW_STORE_WRITE_TOKEN`|unset|Token required in `X-API-Key` for REST writes (else 403 `forbidden`)|
|`IMGW_USER_LOCATIONS_DIR`|unset|Directory of user location CSVs allowed in REST `user_locations`|
|`IMGW_API_MAX_LIMIT`|`1000`|Default and maximum `limit` of REST list commands|
|`IMGW_DATA_DIR`|user data dir of `nogat`|DEV-18.2 meaning since this change: parent of the stores (`<data_dir>/imgw`) and of the server state; shared key (also `NOGAT_DATA_DIR`, `[nogat] data_dir`). Until 3.0.0 it held the reference data: that is `IMGW_REFERENCE_DIR` now|
|`IMGW_REFERENCE_DIR`|`<cache_dir>/imgw/reference`|IMGW-PIB reference data (`hydro_stations_locations.csv`, `desc/`; `python -m imgwtools.reference_data`); `settings.reference_dir`|
|`IMGW_LANG`|`pl`|`pl`\|`en`: CLI help, progress and notice lines and the `--lang` default, `imgw mcp` default, language of `/mcp` tools (REST answers follow `Accept-Language`; the CLI error line and the envelope are English)|
|`IMGW_MCP_ENABLED`|`false`|Serve MCP Streamable HTTP at `/mcp` in `imgw server` (needs `imgwtools[mcp]`; read and plan only)|
|`IMGW_MCP_ALLOWED_HOSTS`|`127.0.0.1,localhost`|Allowed `Host` values of `/mcp` (comma-separated; behind nginx add the public host name)|
|`IMGW_MCP_ALLOW_WRITES`|`false`|Envvar of `imgw mcp --allow-writes`: writing tools still default to `check: true` (plan) and write only with `check: false`|
|`IMGW_CACHE_DIR`|user cache dir of `nogat`|Caches `<cache_dir>/imgw`; shared key (also `NOGAT_CACHE_DIR`, `[nogat] cache_dir`)|
|`IMGW_API_KEYS_FILE`|`<data_dir>/imgw/api_keys.json`|File of the API keys of `imgw admin`|
|`IMGW_RATE_LIMIT`|`100`|Requests per hour (0 = unlimited)|
|`IMGW_ENV`, `IMGW_HOST`, `IMGW_PORT`, `IMGW_LOG_LEVEL`|`development`, `0.0.0.0`, `8000`, `INFO`|REST server (`imgw server`); `IMGW_ENV=production` disables reload|

### Layout

```text
<root>/imgw-store.json                                  # imgw-store/1 marker
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<stem>/observations/   # imgw-observation/1 signal register (ČHMÚ datasets with a content form)
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json                # IMGW-PIB catalog
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson + .meta.json  # ČHMÚ catalog
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/                                            # staging; never a version
```

Slots (spec §13.7): `archive:<key>:<file>` (e.g. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`, `archive:cz.chmi.hydro_daily:H_0-203-1-001000_DQ_2025.json`, `archive:cz.chmi.meteo_daily:precipitation/dly-0-203-0-11573-SRA.csv`), `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>`.

ČHMÚ specifics (ADR-003): freshness from one directory listing per dataset (plan fields `station_code`, `signal`, `remote_listed_at`, `local_observation`, `requests`); a station × year missing at the source is `unverifiable` with `error="not published"` (`download_archives`: `not_published`); datasets with the content form `chmi-json/1` store `content_sha256` — other bytes with the same canonical content give `unchanged` + notice `content_unchanged` + an observation, not a new version; series of per-station datasets carry `stations[<code>].periods` (unpublished years are unknown, not gaps); meteo series add `<V>_quality`/`<V>_source_flag`; project pins of form datasets restore by content (`restored_by_content`, pin state `content_match`, warning `pin_restored_by_content`).

### Contracts (IMGW-13)

`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`, `imgw-pmaxtp/1`, `imgw-observation/1`, envelope `imgw-result/1`, `imgw-commands/1` (command schema). Each has its own `/N` counter; within `/1` only optional fields are added. `/1` domains are open to further providers (ADR-003 C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, station code `STATION_CODE_PATTERN` (9-digit IMGW or WIGOS), optional `content_sha256`/`content_form` in sidecars and project pins. Additive fields of 3.0.0 (ADR-003/004): sidecar `request.station_code`/`param`, `extra.period.station_code`, `license.terms_url`; series `stations[<code>].periods`; catalog `thresholds`; plan item `station_code`/`signal`/`remote_listed_at`/`local_observation` and plan `requests`; command schema `lang`, `x-imgw.writes`/`network`/`operation_id`, `x-imgw-writes`. IMGW-PIB files keep their bytes.

### IMGW CSV Format Notes

Archive files are inconsistent between years — parsers auto-detect the format per file:

- **Encoding**: CP1250 (Polish Windows encoding) for most archives; `codz_2023.zip` is UTF-8 with BOM (auto-detected)
- **Delimiter**: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023) — auto-detected from the first line
- **Quoting**: daily/monthly 2024 files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped); some files carry a header row of column codes (skipped)
- **Missing data codes**: `9999` (water level), `99999.999` (flow), `99.9` (temperature); meteo status 8 = `missing`, 9 = `no_phenomenon`
- **Hydrological year**: November 1 - October 31 (month 1 = November)

## Struktura projektu (z README)

Drzewo katalogów z README (po polsku, bez zmian); szczegółowe drzewo modułów: „Package Tree” wyżej.

```
src/imgwtools/
├── api/          # REST API (FastAPI): routes/commands.py (trasy z katalogu), errors.py (problem+json), main.py (/health, /api/v1, /llms.txt, /mcp)
├── cli/          # CLI: _dispatch.py (komendy z katalogu), admin.py, main.py (version, server, mcp)
├── mcp/          # Serwer MCP (dodatek imgwtools[mcp]): narzędzia z katalogu, stdio i /mcp
├── _parsing/     # Parsery archiwów IMGW-PIB i ČHMÚ, listingu i list stacji (publicznie: imgwtools.parsers)
├── _data/        # Obrysy Polski i Czech (Natural Earth), szablony przewodnika agents/, fixtury testowe
├── store/        # Magazyn wersjonowany: writer, sync, series, catalog, pmaxtp, reader, export, content
├── datasets.py   # Rejestr dostawców i 17 zbiorów (pl.imgw.*, cz.chmi.*), generator plików archiwów
├── commands.py   # Katalog 38 komend wspólny dla Pythona, CLI, REST, MCP i integracji
├── agent_guide.py # Przewodnik dla agentów (AGENTS.md, llms.txt): agent_guide, commands guide
├── fetch.py      # Dane bieżące, PMAXTP, pobieranie archiwów
├── stations.py   # find_stations (IMGW-PIB i ČHMÚ)
├── urls.py       # Stałe URL IMGW, build_pmaxtp_url, build_api_url
├── project.py    # Manifest projektu imgw-project/1
├── testing.py    # build_fixture_store — magazyn testowy offline (także PL + CZ)
├── web/          # Web GUI (HTMX + Jinja2)
└── config.py     # Konfiguracja (IMGW_*)

AGENTS.md, llms.txt  # Przewodnik dla agentów AI — pliki pochodne (imgw commands guide)

data/             # Lokalne dane referencyjne (python -m imgwtools.reference_data), poza repozytorium
docker/           # Konfiguracja Docker
tests/            # Testy (offline; fixtury magazynu w tests/fixtures/store)
```
