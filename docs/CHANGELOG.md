# Changelog — IMGWTools

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [SemVer](https://semver.org/). Every change of the public API and of the store schemas
(`imgw-*/N`) is recorded in this file (ADR-001, policy IMGW-13).

## [Unreleased]

Changes since 2.1.1, to be released as 3.0.0. A versioned store of IMGW data replaces the optional
SQLite cache (ADR-001), and Python, the CLI, REST and the web GUI use one command catalog with one
result envelope and one registry of error codes (ADR-002). The second provider beside IMGW-PIB is
the Czech ČHMÚ (opendata.chmi.cz, ADR-003): the `cz.chmi.*` datasets in the same contracts, store
and commands; the value domains of the `/1` contracts were opened before the tag (C01). AI agents
get the guide `AGENTS.md`/`llms.txt`, English descriptions of the catalog, effect metadata of the
commands and an MCP server (ADR-004). Later work brings the repository in line with the Nogat
standard 1.0 (then the draft 2.1): the user environment (ADR-005), the message catalog and English
machine output (ADR-006), data output in plain mode and in the store with a default root
(ADR-007), and projects moved to Archiwista (ADR-008). The registry has 17 datasets of two
providers, and the catalog 30 commands. Decisions: `docs/DECISIONS.md`; contracts:
`docs/superpowers/specs/2026-10-17-versioned-store-design.md` (§13: consistency of the interfaces,
§13.11: full migration tables), `2026-10-18-chmi-provider-design.md` (ČHMÚ) and
`2026-10-19-agent-support-design.md` (agents). The release has no aliases or shims of old names.
The versions 2.2.0 (2026-08-22) and 3.0.0 (2026-10-19) of earlier drafts of this file were never
tagged; their changes are part of this section.

### Breaking changes and migration from 2.1.1

What a caller of 2.1.1 changes; no alias or shim keeps an old name. Writing data (`--output-dir`,
`--root`, `--output` and the default store) is described in "Migration guide: data output" at the
end of this section.

#### Python — data functions

| Old | New |
|---|---|
| `fetch_hydro_current(station_id=…)` (+`_async`) | `fetch_hydro_current(*, station=…)`; `HydroCurrentData.station_id` → `station_code`, new `latitude`, `longitude` |
| `fetch_synop(station_id=…, station_name=…)` (+`_async`) | `fetch_synop(*, station=…, station_name=…)`; `SynopData.station_id` → `station_code` |
| `fetch_warnings(warning_type="hydro")` (+`_async`) | `fetch_warnings(*, kind=None)` (none = both families); `WarningData.warning_type` → `kind`, new `event` |
| `fetch_pmaxtp(lat, lon, "AMP")` | `fetch_pmaxtp(lat, lon, method="AMP")`; a call with a named `method` is unchanged |
| `list_hydro_stations()`, `list_meteo_stations()` (+`_async`) → `HydroStation`, `MeteoStation` | `find_stations(kind="hydro")` / `find_stations(kind="meteo")` (+`find_stations_async`) → `StationListEntry` (`station_id` → `station_code`) |
| `get_hydro_stations_with_coords(include_all=True)` (+`_async`) | `fetch_hydro_states(main_only=False)` (+`_async`) → `HydroState` |
| `build_hydro_url(HydroInterval.DAILY, 2023)` | `archive_files("hydro/dobowe", years=2023)[0].url` (or the key `pl.imgw.hydro_daily`) |
| `build_hydro_url(HydroInterval.DAILY, 2023, month=13)` | `archive_files("pl.imgw.hydro_phenomena", years=2023)[0].url` |
| `build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 1995)` | `archive_files("meteo/miesieczne/synop", years=1995)[0].url` |
| `get_available_years(DataType.HYDRO, "dobowe")` | `get_dataset("hydro/dobowe").first_year` (no upper bound) |
| `DownloadURL` | `ArchiveFile` |
| `DataType`, `HydroInterval`, `HydroParam`, `MeteoInterval`, `MeteoSubtype` | dataset keys and aliases (`str`), `params` `H\|Q\|T` |
| `PMaXTPMethod` | `Literal["POT", "AMP"]` |
| `build_pmaxtp_url(method, latitude, longitude)` | `build_pmaxtp_url(latitude, longitude, *, method="POT")` |
| `build_api_url(endpoint, station_id=…, station_name=…)` | `build_api_url(endpoint, *, station=…, station_name=…)` |
| `IMGWError(message)` | `IMGWError(detail, *, code=…, details=…)`; a call with the text only is unchanged |
| `download_hydro_data`, `download_meteo_data` (+`_async`) → `bytes` | → `DownloadResult` (`data` = the exact bytes, `url`, `etag`, `last_modified`, `content_length`); the arguments are unchanged, migration: `download_hydro_data("dobowe", 2023).data`; an answer that is no ZIP → `IMGWDataError`; a missing month/parameter → `IMGWValidationError` with `details.option` |
| `parse_zip_file` → `zipfile.BadZipFile` for a damaged archive | `IMGWDataError`; the ZIP is read with limits on the number and size of its files and without unsafe paths |
| `parse_stations_csv(data)` → `HydroStation` (`imgwtools.db.models`) | `parse_stations_csv(data, kind="hydro"\|"meteo")` → `StationListEntry` (`kind`, `station_code`, `name`; hydro `river`, `hydrographic_code`, `river_order`; meteo `short_code`); `.station_name`/`.river_name` → `.name`/`.river`; the meteo list is not read with the hydro layout (its third column is `short_code`) |

Removed from `imgwtools` (also from `imgwtools.urls`), without replacements of the same name:
`HydroStation`, `MeteoStation`, `list_hydro_stations`, `list_hydro_stations_async`,
`list_meteo_stations`, `list_meteo_stations_async`, `get_hydro_stations_with_coords`,
`get_hydro_stations_with_coords_async`, `build_hydro_url`, `build_meteo_url`,
`get_available_years`, `DownloadURL`, `DataType`, `HydroInterval`, `HydroParam`,
`MeteoInterval`, `MeteoSubtype`, `PMaXTPMethod`; the module `imgwtools.core` (`url_builder`)
— the URL constants and `build_pmaxtp_url`/`build_api_url` are in `imgwtools.urls`.

#### Legacy modules and the `[spatial]` extra

- **The extra `[spatial]` became `[pandas]`.** `pip install imgwtools[spatial]` no longer works;
  the dependencies `pyproj`/`pyshp` are dropped.
- **`core/imgw_spatial.py` is removed** (the class `StationMap`, outside the public API, without a
  replacement).
- **`core/imgw_api.py` is removed** (DEPRECATED since 2.0.0). Replacements: `HYDRO` →
  `fetch_hydro_current()`, `SYNOP` → `fetch_synop()`, `METEO` → `fetch_synop()` /
  `fetch_hydro_current()`, `WARNINGS` → `fetch_warnings()`, `PMAXTPAPI` → `fetch_pmaxtp()`.
- **`core/imgw_datastore.py` is removed**: instead of `DataDownloader` use `download_hydro_data()`
  or `download_meteo_data()`.

#### Removed SQLite cache (ADR-001)

- the package `imgwtools.db` (`cache_manager`, `connection`, `schema`, `repository`, `models`,
  `parsers`): the hydro parsers are still in `imgwtools.parsers`, the archive models
  (`HydroArchiveStation`, `HydroDailyRecord`, …) in `imgwtools.models`;
- the CLI command `imgw db …` (`init`, `status`, `stations`, `cache`, `query`, `clear`, `vacuum`);
- the REST endpoint `GET /api/v1/hydro/data`;
- the settings `IMGW_DB_ENABLED` and `IMGW_DB_PATH`;
- the install extra `imgwtools[db]`.

Existing `.db` files are neither deleted nor migrated: download the data again into the store
(`imgw store sync`).

#### CLI

| Old | New |
|---|---|
| `imgw fetch hydro -i dobowe -y 2023 -m 1 [-p H] [-o DIR]` | `imgw datasets download -d hydro/dobowe -y 2023 -m 1 [--params H] [-o DIR]` (`-d` required, no default interval); `-o` (`--output-dir`) writes plain files in the path layout of the IMGW server through the `.imgw-incoming/` directory and `os.replace`, and an existing file needs `--force` |
| `imgw fetch meteo -i miesieczne -s synop -y 2023 [-o DIR]` | `imgw datasets download -d meteo/miesieczne/synop -y 2023 [-o DIR]` |
| `imgw fetch current hydro\|meteo\|synop [-s ID] [-o FILE]` | `imgw current hydro\|meteo\|synop [-s CODE]` (to save: `> FILE`) |
| `imgw fetch pmaxtp -m AMP --lat … --lon … [-o FILE]` | `imgw pmaxtp fetch --method AMP --lat … --lon …` |
| `imgw fetch warnings -t meteo [-o FILE]` | `imgw current warnings -k meteo` |
| `imgw list stations -t hydro -s Warsz -l 50` | `imgw stations find -k hydro -q Warsz --limit 50` |
| `imgw list datasets [-t hydro]` | `imgw datasets list [-k hydro]` |
| `imgw list intervals` | `imgw datasets list` (the field `legacy_alias`) |
| stdout: the raw result, absolute paths | the envelope `imgw-result/1` on one line, paths in the store relative to the root |
| an error: `Błąd: …` on stderr (legacy commands: stdout), exit code 1 | JSON `{"code", "detail", "details"}` on the last line of stderr, the exit code from the error registry; a `partial`/`failed` result → 10/11, cancellation 130 |

#### REST

| Old | New |
|---|---|
| `GET /api/v1/hydro/stations`, `GET /api/v1/meteo/stations` (stubs), `GET /api/v1/hydro/stations/{station_id}` | `GET /api/v1/stations/find?kind=…&query=…` |
| `GET /api/v1/hydro/current?station_id=` | `GET /api/v1/current/hydro?station=` |
| `GET /api/v1/meteo/current?station_id=` | `GET /api/v1/current/meteo?station=` |
| `GET /api/v1/meteo/synop?station_id=&station_name=` | `GET /api/v1/current/synop?station=&station_name=` |
| — | `GET /api/v1/current/warnings`, `GET /api/v1/current/hydro-states` |
| `POST /api/v1/hydro/download-url`, `/hydro/download-urls`, `/meteo/download-url`, `/meteo/download-urls`; `GET /api/v1/download/url`, `/download/urls` | `GET /api/v1/datasets/files?dataset=…&years=…&months=…&params=…` |
| `GET /api/v1/download/datasets` | `GET /api/v1/datasets/list` |
| `GET /api/v1/pmaxtp/methods` | `GET /api/v1/commands/schema?command=pmaxtp%20fetch` (the `method` enumeration with its description) |
| `POST /api/v1/pmaxtp/url` | `GET /api/v1/pmaxtp/url` |
| `POST /api/v1/pmaxtp/data` (the raw IMGW answer) | `GET /api/v1/pmaxtp/fetch` (`PMaXTPResult`) |
| `GET /map/stations` (web) | `GET /api/v1/current/hydro-states` |
| errors `{"detail": …}`, 422 with a pydantic list | `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`); validation always 400 |

Web: the routes `/download/archives` + `POST /download/files`, `/stations/find` and the catalog
route `GET /api/v1/current/hydro-states` replace `/download/hydro|meteo[/generate]`,
`/stations/hydro|meteo` and `/map/stations`.

#### Fields and files

| Old | New |
|---|---|
| REST `Station.id`, `HydroStation.station_id`, `HydroCurrentData.station_id`, `SynopData.station_id` | `station_code` |
| REST `DownloadURLResponse{url, filename, data_type, interval, year, month}` | `ArchiveFile{dataset, server_path, url, year, month, param, year_type, period_start, period_end}` |
| REST `HydroCurrentData{water_level, flow, temperature}` | the library model `{water_level_cm, flow_m3s, water_temp_c, …}` |
| REST `MeteoCurrentData{temperature, wind_speed, humidity, precipitation}` | `MeteoCurrentData{air_temp_c, wind_speed_ms, humidity_percent, precipitation_10min_mm, …}` or `SynopData` |
| `WarningData.warning_type`, REST `WarningData.type` | `kind` |
| `data/hydro_stations_locations.csv` `id,X,Y` | `station_code,latitude,longitude` (run `python -m imgwtools.reference_data` again; the old header → `validation_error` with an instruction) |
| `data/hydro_stations_names.csv`, `data/meteo_stations_names.csv` and `Settings.hydro_stations_file`/`meteo_stations_file` | removed (only `imgw list stations` read them) |
| `IMGW_DATA_DIR` (`Settings.data_dir`, default `./data`) as the directory of the reference data | `IMGW_REFERENCE_DIR` (default `<cache_dir>/imgw/reference`); `IMGW_DATA_DIR` is the user data directory, the parent of the stores (see Changed) |
| `IMGW_API_KEYS_FILE` with the default `./api_keys.json` | the default `<data_dir>/imgw/api_keys.json` |

#### Installation

- **`imgwtools[full]`** covers `store` (`pyarrow>=15`) and `mcp` beside `api`, `cli`, `pandas`.
- The new extra **`imgwtools[mcp]`** = `imgwtools[cli]` + `mcp>=2.3,<3` (the MCP server, ADR-004).

### Added

- **`command_for_version(version, *, root=None)` (ADR-008, Nogat ECO-054, plan 2026-10-31 step 3):**
  the data command that fetches a stored version again, rebuilt offline and read-only from its
  sidecar (`imgw-meta/1`) and the store layout, as the `CommandCall` that `parse_command` reads
  from the canonical line of `format_command` (options as texts, `root` the absolute store root,
  empty `run`), so `format_command`, `check_command` and `run_command` take it. `version` is the
  version directory, its main file (`StoreEntry.version`), its sidecar, the PMAXTP `response.json`
  or a station file of a series version, relative to `root` (default `store_root()`); the main
  file need not exist, so Archiwista can restore a pin whose data are gone. IMGW-PIB archives give
  `store sync --datasets <key> --years <year>` (`--months` of a monthly file), ČHMÚ archives
  `store sync --datasets <key> --stations <code>` (`--years` of a hydrological file), station
  lists and catalogs `store catalog --provider <provider>`, series versions `series build
  --dataset <key>` and PMAXTP cells `pmaxtp sync` of their point, method and cell. The call is
  the narrowest that selects the version's file; it may cover files beside it (the `H`, `Q`, `T`
  files of a half-year, every element of a ČHMÚ meteorological station). Refused, never guessed:
  a catalog built with a user's coordinates file (only its name is recorded), a sidecar without a
  field the call needs, a file `store sync` does not select (`unsupported`,
  `details.reason="command_not_rebuildable"`, the text says how to pin it instead); a missing
  version or sidecar is `not_found`, an invalid or contradicting sidecar `data_error`, a path that
  is no version `validation_error` (`details.option="version"`). Python only: no catalog command.
- **Error code `unsupported` (exit 15, HTTP 422; Nogat ERR registry):** "Not supported" /
  "Nieobsługiwane", a valid request outside what the tool can do; `command_for_version` is its
  first user. `ERROR_CODES`, the CLI, REST (problem+json, OpenAPI `4XX`), MCP, `contract_schemas.json`
  (`problem+json`, `cli-error`) and the error tables of `AGENTS.md` carry it.
- **`parse_command(line)` and `format_command(..., run=)` (AGI-2.1, request of Archiwista):**
  `parse_command` reads an `imgw` command line, a text or its words with or without the leading
  `imgw`, into `CommandCall(command, options, run)`, so a pasted line becomes a call. The flags are
  those the CLI has for the catalog command (`x-imgw.cli.flags`, and `--check` of a command with a
  check twin), read as the CLI reads them: `--root=/data`, `-r/data`, a list flag repeated, the
  last value of another flag, `--` at the end. The options are the texts the CLI passes to
  `run_command`, nothing validated (`validate_command` does that), and `run` is `{"check": True}`
  for `--check`. A mistake of the line (no command or one outside the catalog, `--help` or
  `--schema`, an unknown flag, a flag without its value, a switch with one, a word that is no flag)
  is `validation_error` with `details.reason` `usage`, `details.option` for a wrong flag and
  `details.command` once the line named a command. `format_command(command, /, *, options,
  run=None)` writes `--check` last for `run={"check": True}`; another flag of a run, a value that
  is not a boolean or `--check` of a command without it is `validation_error` naming it. The agent
  guide writes its planned steps with it (the guides do not change). The names, shapes and errors
  are Kartograf's (`parse_command`, `format_command(..., run=)`, `CommandCall`); IMGWTools keeps its
  keyword-only options (R1), so `format_command(command, options=..., run=...)` calls both. A
  contract test (`tests/contract/test_command_lines.py`) writes the line of every example call
  (each catalog command, the ČHMÚ calls, with `--check` where a command has it), reads it back and
  writes the same line again, so a tool that exchanges `imgw` lines compares them as text.
- **Example calls in the catalog (AGI-2.2):** every command of `command_schema` has
  `x-imgw.examples`, at least one `{call, result}`: a complete `imgw` line and an excerpt of the
  `result` of its envelope (41 examples for the 30 commands, with `--check`, the ČHMÚ datasets
  and plain `--output-dir` among them). Each call is the canonical line of `format_command`
  (AGI-2.1): `format_command` writes the call that `parse_command` reads from it as the same line,
  and `validate_command` accepts its options. A contract test holds this for every example (also
  under another default root) and every excerpt to fields of the command's result type. The MCP
  tool descriptions, `commands list` and the agent guides do not change.
- **`store_root()` (DEV-19.2):** `imgwtools.store_root()` (also `imgwtools.config.store_root`) is the
  public read-only accessor of the default store root: `StoreRoot(root, source, name,
  marker_exists)` with the absolute root of a command without `--root`, the layer that gave it
  (`default`, `env`, `dotenv`, `file`) and whether `imgw-store.json` is a file in it. It lists and
  measures nothing (`imgw config show` measures the size); Kartograf has the same function. It
  replaces `imgwtools.config.default_root()`, which returned the bare path (use `.root`).
- **`commands list` (AGI-5.9):** a new catalog command and the public `list_commands(*, lang)`
  return the catalog summary `imgw-command-list/1`: per command its name, `operation_id`,
  group, one-sentence summary, effects (`writes`, `network`, `idempotent`), check twin, result
  shape and REST route. It is the first discovery step before `commands schema`; the MCP tool is
  `imgw_commands_list`, the REST route `GET /api/v1/commands/list`, the CLI
  `imgw commands list`.
- **`nogat.toml` (DEV-18.1):** every setting also comes from `[imgw]` (any setting) and `[nogat]`
  (the shared keys `data_dir`, `cache_dir`, `lang`) of the user's `nogat.toml` (`NOGAT_CONFIG` names
  another file), read with `tomllib`; `NOGAT_DATA_DIR`, `NOGAT_CACHE_DIR` and `NOGAT_LANG` are the shared
  variables. Order: option, `IMGW_<KEY>`, `.env`, `NOGAT_<KEY>`, `[imgw]`, `[nogat]`, default. The
  file never gives the credential `IMGW_STORE_WRITE_TOKEN`; an unusable file ends every `imgw`
  call and the REST startup with `validation_error`.
- **`cache_dir` (DEV-18.2):** `IMGW_CACHE_DIR` (default `platformdirs.user_cache_path("nogat")`),
  home of the reference data (`<cache_dir>/imgw/reference`).
- **`imgw config show [--json]` (DEV-18.6):** document `imgw-config/1` with every setting, its value
  and source, each credential as `present` or `missing`, and the store root with its source and
  size (hard-linked files counted once). README and `.env.example` list all 18 `IMGW_*` variables.
- **Message catalog (AGI-9.1, AGI-9.2, DEV-2.3, ADR-006):** `imgwtools.messages` holds the texts
  for a person in English with a Polish variant (`Text(en, pl)` under the key `<area>.<name>` in
  `imgwtools.messages.<area>`). `message(key, lang="en", **values)` renders one as a `Message`: a
  `str` that remembers its key and values, so the adapter of a caller who asked for Polish
  renders it again (`localize(text, lang)`, `IMGWError.localized(lang)`,
  `CommandResult.to_json(lang=)`, `jsonable(..., lang=)`) instead of parsing text.
  `tests/unit/test_messages.py` checks both languages of every entry, every `message("…")` call
  against its entry, unused entries and Polish literals outside the catalog.
- **`StoreInfo.problem_codes` (request of Archiwista):** every text of `StoreInfo.problems` has its
  machine-readable code at the same index: `missing_store`, `missing_marker`, `invalid_marker` or
  `unsupported_store`, the codes `iter_store` already gives the entry of the same problem
  (`StoreEntry.problem_code`). A consumer decides by the code and shows the text. The field is
  optional (default `()`), so `imgw-store/1` and the constructor of `StoreInfo` do not change; it is
  part of the document of `store info` in every interface.
- **`Meta.producer` and `Meta.producer_version` (DEV-19.16, request of Archiwista):** the typed
  sidecar that `read_meta`, `iter_store` (`StoreEntry.meta`) and `current_version` return keeps the
  two fields of the sidecar core that the reader validated and dropped. They are what the sidecar
  says: `producer` is `imgwtools` (the only name a reader accepts) and `producer_version` the version
  of the package that wrote the version, so a version written by an earlier release keeps its older
  number and the running package never stands in for it. `imgw-meta/1` has required both from the
  start, so a sidecar without one is still `invalid_meta`, refused and not filled in. The fields are
  optional (defaults `"imgwtools"` and `None`), so `imgw-meta/1` and the constructor of `Meta` do
  not change.
- **`iter_store(skip_versions=)` and `StoreEntry.skipped` (request of Archiwista):** an incremental
  scan. A consumer that keeps what it has read passes the versions it knows, the path of each
  version directory relative to the root (with `/`) mapped to the names of its data files
  (`{"archives/versions/…/<label>_<sha8>": ("codz_2024.zip",)}`; the shape of
  `ScanScope.known_versions` of Archiwista and of `skip_versions` of Kartograf), and gets each back
  as an entry with `skipped=True` and `meta=None` (`kind`, `slot`, `version` and `provider` as
  always), without its directory being listed, its sidecar read or its file measured. The scan
  still lists the slots, so a new version, a problem and a version that is gone show as in a full
  scan; the caller vouches for what it names, so a known version that has broken since is not
  seen. An observation of an archive slot is still checked against the content fields of the
  version it names, which reads that one sidecar. `skip_versions` is a parameter of the Python
  function only (`store scan` takes no list of known versions); a value that is not a mapping of
  paths to collections of plain file names is `validation_error` with `details.option` set to
  `skip_versions`. `StoreEntry.skipped` is optional (default `False`).
- **Versioned store** (`imgwtools.store`, re-exported in `imgwtools`): immutable, append-only
  versions of the IMGW archives, kept 1:1, with a sidecar `*.meta.json` (SHA-256, size, HTTP
  headers, IMGW-PIB license), published from the `.incoming/` staging with hard links that never
  replace a target, with the sidecar of the main file linked last (it commits the version;
  Kartograf's model), and detection of nested stores of IMGWTools and Kartograf by their markers,
  without importing Kartograf (see Changed). Functions: `init_store`, `open_store`, `write_archive`,
  `check_store`/`sync_store` (listing + `HEAD`, plan `imgw-plan/1`, items `stale_plan`),
  `check_series`/`build_series` (Parquet per station), `check_catalog`/`build_catalog`
  (`stations.geojson`, the Natural Earth outline of Poland in the package),
  `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp` (PMAXTP per grid cell; beside `cell.json`, the raw
  API answer byte for byte as `response.json`, described in `extra.response` of the sidecar), and
  the readers `store_info`, `iter_store`, `read_meta`, `current_version`, `read_catalog`,
  `read_series_index`, `read_series`.
- **Reading station lists and archives from the store (offline, SHA-256)**:
  `read_station_list(root, kind="hydro"|"meteo")` → a tuple of `StationListEntry` of the current
  version of the list; `read_archive(version)` → the `NormalizedRecord` records of a stored
  archive version (a station-list version is refused with a pointer to `read_station_list`).
- **Series and export**: `select_series` (the choice of a series version for stations, variables
  and years), `summarize_series` (coverage per station × variable with gaps; `series summary`),
  `export_series` (CSV with units and the IMGW-PIB attribution) and `export_archive` (CSV or JSONL
  of one archive version; `store export`): with `output` they write one plain file (see Changed),
  without it they return an iterator of ready lines (a stream in the CLI and REST).
- **Registry of providers and datasets** `imgwtools.datasets`: `datasets(*, kind=None,
  provider=None)`, `get_dataset()` (a key, slug or legacy alias), `archive_files()`,
  `station_source_files()`, `DatasetDescriptor`, `ArchiveFile`, `License`, `YearsArg`/`MonthsArg`
  (`2024`, `"2020-2023"`, `"2020,2022"`, lists). 17 descriptors: 13 of IMGW-PIB — five archive
  datasets of the store (`pl.imgw.hydro_daily`, `pl.imgw.hydro_monthly`,
  `pl.imgw.hydro_semiannual`, `pl.imgw.meteo_climate_daily`, `pl.imgw.meteo_precip_daily`), the
  station lists (`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`), PMAXTP (`pl.imgw.pmaxtp`)
  and five download-only datasets (`pl.imgw.hydro_phenomena`, `pl.imgw.meteo_climate_monthly`,
  `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`, `pl.imgw.meteo_climate_terms`)
  — and 4 of ČHMÚ (`cz.chmi.*`, "ČHMÚ provider" below).
- **`download_archives(dataset, /, *, years, months, params, stations, output_dir, root, force)`**
  → `DownloadReport`/`DownloadItem` (slot, URL, status, path, `error_code`): plain files in the
  server-path layout of the provider or versions in the store (see Changed), and the
  `license_terms` notice after the download.
- **Live data**: `find_stations`/`find_stations_async` (station lists live or from the store,
  `source="live"|"store"`, `provider`: IMGW-PIB, ČHMÚ or both; a search that ignores case and
  diacritics), `fetch_meteo_current`/`_async` → `MeteoCurrentData`, `fetch_hydro_states`/`_async`
  → `HydroState` (coordinates and water level from `hydro-back.imgw.pl`); warnings from the
  `warningshydro`/`warningsmeteo` endpoints (`WarningData.event`); `StationListEntry` with
  optional `latitude`/`longitude`.
- **Error codes**: the closed registry `ERROR_CODES` (`ErrorCode`, `ErrorSpec`: title, CLI exit
  code, HTTP status): `validation_error` (2/400), `not_found` (3/404), `conflict` (4/409),
  `source_unavailable` (5/502), `missing_dependency` (6/503), `data_error` (7/500),
  `store_unavailable` (8/503), `io_error` (9/500), `cancelled` (130), `forbidden` (12/403),
  `unsupported` (15/422), `method_not_allowed` (405), `internal_error` (1/500). Every `IMGWError`
  has `code` and `details` (e.g. `option`, `allowed`, `reason`); new `IMGWCancelledError`.
- **Command catalog** `imgwtools.commands`: 30 commands in the groups `datasets`, `stations`,
  `current`, `pmaxtp`, `store`, `series` and `commands` (27 of ADR-002, `datasets providers` of
  ADR-003, `commands guide` of ADR-004 and `commands list` of AGI-5.9);
  `command_schema(command=None)` (the JSON Schema of the options + `x-imgw`: function, check twin,
  result type, CLI flags, REST route, rules; the document `imgw-commands/1` with the error and exit
  codes), `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command` →
  `CommandResult` (the envelope `imgw-result/1`: `status` `ok|partial|failed|cancelled`, `result`,
  `notices` without repetitions). **Pagination**: 12 list commands return `Page` (`items`,
  `total`, `limit`, `offset`) with the options `limit`/`offset`.
- **CLI** generated from the catalog (`cli/_dispatch.py`): the JSON envelope on stdout, the
  streams of `store export`/`series export`, an error as JSON on stderr, exit codes from the
  registry, `--check` on the commands with a twin, `--schema` on every command, an optional
  `--root` (the default root, see Changed), lists comma-separated or as a repeated flag; Ctrl+C
  cancels between files (130).
- **REST** generated from the catalog (`/api/v1/<group>/<command>`, 28 routes; `GET /api/v1`
  lists the routes): the same envelope as the CLI, `application/problem+json`, `?check=true` on
  `POST`, `limit` by default and at most `IMGW_API_MAX_LIMIT` (1000). The store commands work only
  on the server's absolute `IMGW_ROOT` (503 without it); a write needs
  `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` and the `X-API-Key` header; the
  user's coordinates CSV comes only from `IMGW_USER_LOCATIONS_DIR`. Answers do not reveal server
  directories (paths relative to the root, also in texts).
- **Web GUI** only on the public API: the archive form from the registry (10 IMGW-PIB datasets),
  the station search with pagination, the map from `GET /api/v1/current/hydro-states`, errors as a
  fragment with the `IMGWError` code; the footer shows the current package version.
- **Meteo parsers and normalization**: `parse_meteo_climate_daily`, `parse_meteo_precip_daily`,
  `normalize_archive`, `NormalizedRecord` records with the flags
  `value|missing|no_phenomenon|accumulated`; `summarize_coverage` (coverage per station ×
  variable, gaps).
- **Open value domains of the `/1` contracts (ADR-003, C01)**, the base of the ČHMÚ provider
  without changing the IMGW bytes: the dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`
  (`imgw-meta/1`, `imgw-series/1`), `country` `^[A-Z]{2}$`, `provider` and `license.id` as any
  non-empty text (`License.id: str`), the station code as 9 IMGW digits or a WIGOS identifier
  (`imgwtools.datasets.STATION_CODE_PATTERN`; in the keys and files of `series.json` and
  `stations.geojson` and in the options `station`/`stations` of the catalog, while
  `current hydro|meteo` still take only the 9 IMGW digits), and the `location_source` values of
  ČHMÚ in `stations.geojson`. The sidecar of a dataset known to the registry must have the
  `country` and `provider` of the registry (otherwise `invalid_meta`); a valid key of an unknown
  dataset gives `unknown_entry`.
- **Canonical content** (ADR-003 D17): the optional fields `content_sha256` (64 hex) and
  `content_form`, always together, in the sidecar `imgw-meta/1` (`Meta.content_sha256`,
  `Meta.content_form`); one field without the other → `invalid_meta`. The IMGW datasets do not
  write them.
- **Dataset key convention (IMGW-20, ADR-001 errata 2026-10-18)**: the pattern
  `imgwtools.datasets.DATASET_KEY_PATTERN` (tested on the whole registry and on
  `pl.imgw.stations`), published keys never change, and the table of renamed keys
  `DATASET_KEY_ALIASES` (old → current key; empty in 3.0.0, every entry recorded in this
  changelog) with `resolve_dataset_key`; `get_dataset` and the store readers accept the keys of
  the table. Beside the raw `dataset`, `read_meta` returns the field `Meta.dataset_key` (also in
  the CLI/REST envelopes): the current key, or `null` for a valid but unknown key, without an
  exception and without `invalid_meta` in the scan.
- **Observation register `imgw-observation/1`** (ADR-003 D18): the `observations/` directory in an
  archive slot (files `<YYYY-MM-DD>_<sha8>.json`) is no version: `current_version`, `read_meta`,
  the series readers and the choice of a slot's version in `write_archive`, `build_catalog` and
  `build_series` skip it; `iter_store` returns valid observations as
  `StoreEntry(kind="observation", observation=Observation(…))` and invalid ones as problems
  (`unknown_entry`, `symlink`, `unreadable`, `invalid_json`, `unknown_schema`, `invalid_meta`);
  `store scan --kind observation`; `store_info().contracts["observation"]`. `write_archive` writes
  observations in the slots of the datasets with a canonical form (ČHMÚ, below).
- **`imgwtools.testing`**: `build_fixture_store`, a public offline builder of a test store (the
  variants `complete`, `complete_pl_cz`, `corrupt`, `unknown_schema`) with recorded answers;
  `fixture_files()`: archives, listings and recordings (also `contract_recordings.json` with the
  answers of the live endpoints, and `chmi_recordings.json`, `chmi_catalog_recordings.json`,
  `chmi_builder_recordings.json`) and `contract_schemas.json` (JSON Schemas with example documents
  of the store, `imgw-result/1`, `problem+json` and `cli-error`) for consumers (Archiwista,
  Retman).
- **Exceptions**: `IMGWStoreError`, `IMGWStoreConflictError`, `IMGWStoreDependencyError` (with the
  instruction `pip install imgwtools[store]`), `IMGWCancelledError`.
- **Extra** `imgwtools[store]` = `pyarrow>=15` (only the Parquet paths; importing the core needs
  neither pyarrow nor fastapi nor typer).

#### ČHMÚ provider (ADR-003, C02–C09)

- **Provider registry**: `ProviderDescriptor` (`id`, `short_name`, `name`, `country`,
  `key_prefix`, `base_url`, `license`, `processed_attribution`, `notice`,
  `station_code_pattern`, `datasets`), `providers()` and `get_provider(id | key_prefix)` (an
  unknown provider → `validation_error` with `details.allowed`); the providers `IMGW-PIB` (PL,
  `pl.imgw`) and `CHMI` (CZ, `cz.chmi`, display name "ČHMÚ", license CC BY 4.0 with
  `License.terms_url`). `station_source_files(provider=…)`, `STATION_CODE_PATTERN` (9 IMGW-PIB
  digits or a WIGOS identifier). In `imgwtools.__all__`: `ProviderDescriptor`, `providers`,
  `get_provider`, `STATION_CODE_PATTERN`, `parse_chmi_hydro_daily`, `parse_chmi_meteo_daily`,
  `parse_chmi_stations`.
- **`cz.chmi.*` datasets**: `cz.chmi.hydro_daily` (H [cm], Q [m3/s], T [°C]; one JSON file per
  station and calendar year, from 1887), `cz.chmi.meteo_daily` (P [mm], Tmean, Tmax, Tmin [°C]
  from `historical_csv`; four CSV files per station — SRA, T, TMA, TMI — with the whole history
  of the station), and the station lists `cz.chmi.hydro_stations` and `cz.chmi.meteo_stations`
  (`historical/metadata/meta1.json`). `DatasetDescriptor` + `provider`, `archive_scope`
  (`country|station_year|station_element`), `variable_notes` (the conventions of the day and of
  the observation times), `measurement_fields`, `content_form`, `volatile_fields`,
  `update_signal="listing"`; `ArchiveFile.station_code`. `archive_files(…, stations=[…])`:
  candidates station × year (hydro) or four files per station (meteo, without `years`); `months`
  and `params` only for IMGW-PIB. A ČHMÚ station code is the WIGOS identifier from the file names
  (e.g. `0-203-1-001000`).
- **Freshness from the listing**: `check_store`/`sync_store(…, stations=…)` for `cz.chmi.*` make
  one GET of the listing of the server directory per dataset (meteo: `precipitation/` and
  `temperature/`) instead of a HEAD of every file; `current|newer|missing` come from the pair
  (listing time to the minute, size) against the reference signal of the slot; a station × year
  pair outside the listing → `unverifiable` with `error="not published"`, a station without files
  → a plan action; `years` is optional for hydro (none = the published years) and forbidden for
  meteo; one call covers the national IMGW-PIB archives or the ČHMÚ station files. The plan
  `imgw-plan/1` has the new item fields `station_code`, `signal` (`listing`|`head`),
  `remote_listed_at`, `local_observation` and the field `requests` (`made`, `planned`; also for
  IMGW-PIB); `sync_store` makes a HEAD before the GET (a change since the plan or 404/410 →
  `stale_plan`). Requests to ČHMÚ carry `User-Agent: imgwtools/<version>` and run one at a time.
- **Canonical content and observations**: the form `chmi-json/1` (JSON without the keys
  `zaznamID` and `datumVytvoreni`, serialized by RFC 8785/JCS) for `cz.chmi.hydro_daily` and the
  ČHMÚ station lists: `write_archive` writes `content_sha256`/`content_form` into the sidecar, and
  other bytes with the same content as the current version give `unchanged` without a new version,
  with the notice `content_unchanged` (`info`) and, for a new signal, the file
  `observations/<YYYY-MM-DD>_<sha8>.json` (`VersionResult.observed_sha256`,
  `VersionResult.observation`), so the next `check_store` gives `current` without a download;
  bytes that do not match the form → `data_error` without a write. ČHMÚ sidecars: `country`,
  `provider` and `license` from the registry, `request.station_code`/`param`,
  `extra.period.station_code`; `read_meta` → `Meta.provider`, `Meta.country`. The IMGW sidecars
  are byte-for-byte unchanged.
- **ČHMÚ station catalog**: `build_catalog`/`check_catalog(…, provider="CHMI")` →
  `stations/versions/chmi_stations/<label>_<sha8>/stations.geojson`, slot
  `catalog:cz.chmi.stations`. The sources in order of precedence:
  `hydrology/now/metadata/meta1.json`, `meta3.json` and the archive `cz.chmi.hydro_stations`; the
  newest `meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json` and the archive
  `cz.chmi.meteo_stations`; the user's file and the ČHMÚ series indexes. SPA thresholds in the
  additive property `thresholds` (`drought`, `spa1`–`spa3`, `q50`: the 50-year water level or
  discharge), `hydrographic_code` = `HLGP4`, `active` = presence in the `now` list, the outline of
  Czechia from Natural Earth in the package (`czechia_border_wgs84.geojson`), the notice
  `location_conflict`. `read_catalog(root=…, provider=…)`, `read_station_list(…, provider=…)`,
  `iter_store(…, provider=…)`, `StoreInfo.providers`, `StoreEntry.provider`,
  `StationFeature.provider`, `StationListEntry.provider`, `CatalogReport.provider`. The IMGW-PIB
  catalog of a store with ČHMÚ data is byte-for-byte the same.
- **Series, quality and flags**: `build_series` for `cz.chmi.*`
  (`series/versions/chmi_hydro_daily/`, `chmi_meteo_daily/`) with a continuous calendar per
  station; `series.json` + `stations[<code>].periods` (the periods known per station: the years of
  the hydro files held, the row range of the meteo files), `StationSeriesIndex.periods`,
  `summarize_coverage(…, station_periods=…)`: a year without a file (e.g. an unpublished one) is
  unknown, not a gap. Meteo: the ČHMÚ `QUALITY` (0–5) and `FLAG` verbatim in
  `Measurement.quality`/`source_flag`, in the Parquet columns `<V>_quality` (`int8`) and
  `<V>_source_flag`, in the CSV of `export_series`/`export_archive` and in JSONL; a precipitation
  trace (`FLAG` `T`, 0.0) = `value`, `0.0` without a flag = `no_phenomenon`; values are not
  corrected by their quality. The Parquet metadata `variable_notes`; the attribution of the series
  sidecars and of the exports by provider (ČHMÚ: the source formula and "Dane ČHMÚ zostały
  przetworzone (normalizacja i zmiana formatu)", in English "ČHMÚ data were processed
  (normalization and change of format)"); `extra.source_files[]` with the content fields of the
  hydro inputs.
- **Commands and options**: `datasets providers` (`providers`, `GET /api/v1/datasets/providers`),
  `--provider` in `datasets list`, `stations find`, `store scan` and `store catalog`,
  `--stations`/`-s` in `datasets files|download` and `store check|sync`, the rules of the datasets
  in `x-imgw.rules`; `data_commands(provider=…)` (the view of one provider). Live, `find_stations`
  reads the ČHMÚ `now` metadata (the coordinates of the source; "spindleruv" finds "Špindlerův
  Mlýn"), and in the store the lists and catalogs of the providers. `download_archives(…,
  stations=…)`: a ČHMÚ file that is not published (404/410) → the item `not_published` (a
  success). `series *` take the `cz.chmi.*` datasets and WIGOS codes (`series select` checks the
  code grammar of the dataset's provider, and a year outside the periods of the series, also an
  unpublished one, gives `validation_error`); `current *` and `pmaxtp *` stay IMGW-PIB only.

#### AI agent support (ADR-004, A01–A05)

- **English descriptions and language**: the catalog has English texts (descriptions and rules
  of the commands, help of the options, descriptions of the groups, titles of the errors and of the
  datasets), now entries of the message catalog with a Polish variant (see Changed);
  `command_schema(command=None, /, *, lang=…)` and the `lang` option of `commands schema` and
  `commands guide` (the document `imgw-commands/1` with the field `lang`). CLI: `IMGW_LANG=pl|en`
  sets the command help, the group descriptions and the Typer/Click elements. REST: `lang` from
  the query, else the `Accept-Language` header, else English; the answers carry
  `Content-Language`. The language does not change the contract: the schemas of both languages
  differ only in their texts.
- **Effect metadata**: `DataCommand.writes` (`none|add|replace`), `DataCommand.network`,
  `CommandOption.writes`, `DataCommand.env_root_when` (the shared rule of the default `root` of
  the CLI and MCP); in the schema `x-imgw.writes`, `x-imgw.network`, `x-imgw.operation_id` (the
  REST `operationId` and the name of the MCP tool) and `x-imgw-writes` of the writing options.
  Every writing command has a `check` twin.
- **Guide**: `agent_guide(*, format="agents"|"llms", lang="en", output=None, force=False)` (in
  `imgwtools.__all__`) and the command `commands guide` (`GET /api/v1/commands/guide`, a
  `text/markdown` stream); the derived files `AGENTS.md` and `llms.txt` (llms.txt v2) in the root
  of the repository, generated from the catalog, the registries and the templates in
  `src/imgwtools/_data/agents/` and guarded by a drift test; `GET /llms.txt` of the REST server in
  the language of `Accept-Language`.
- **MCP server**: the extra `imgwtools[mcp]` and the command
  `imgw mcp [--allow-writes] [--allow-dir DIR]` (stdio; the variable `IMGW_MCP_ALLOW_WRITES`;
  without the extra, the line `missing_dependency`, exit code 6). A tool is a catalog command (the
  name `x-imgw.operation_id`, the input schema from `command_schema`, the annotations
  `readOnlyHint`, `destructiveHint`, `openWorldHint`); by default it only reads and plans: the
  writing commands have `check` fixed to `true`, and a write needs `--allow-writes` and
  `check: false` (otherwise `forbidden`, `details.reason="writes_disabled"`). `structuredContent`
  = the envelope `imgw-result/1`, an error = `{code, title, detail, details}` with `isError`,
  lists of 50 by default, streams up to 256 KiB, progress and cancellation; `root` as in the CLI
  (the default root; `--allow-dir` bounds the paths, see Changed). The endpoint `/mcp` (Streamable
  HTTP) in `imgw server` with `IMGW_MCP_ENABLED=true` (`IMGW_MCP_ALLOWED_HOSTS`): the tools of the
  REST routes called in the process, read and plan only (a POST always with `?check=true`);
  `docker/nginx.conf` has `location = /mcp`.
- **Message tidiness**: Polish texts with Polish characters in the help and messages of
  `imgw admin` (the metavariables `IDENTYFIKATOR`, `TEKST`, `LICZBA`), the help of `imgw version`
  and `imgw server` (`ADRES`, `LICZBA`), the Typer/Click help elements ("Opcje", "Użycie:",
  `[OPCJE]`, `KOMENDA [ARGUMENTY]...`, "Przerwano."), the output of
  `python -m imgwtools.reference_data` (the IMGW-PIB attribution from the registry) and the header
  of the wget script in the web GUI; the HTML pages of the web GUI no longer belong to
  `/openapi.json`.

#### Store behaviour

- `build_catalog` checks the stored station lists (`lista_stacji_hydro.csv`, `wykaz_stacji.csv`)
  by `HEAD`, as `check_catalog` does: a changed list (another ETag/Last-Modified) or one without a
  comparable signal is downloaded and written by `write_archive` before the catalog is built
  (identical bytes → `unchanged`), so the next build clears a `newer` reported by
  `check_catalog`.
- The station catalog keeps the codes known only from the local static file
  `hydro_stations_locations.csv` (a `hydro` entry without a name, `active=false`, location
  `static`); codes known only from the user's file go to `problems` (that file only supplements
  locations).
- The IMGW-PIB station catalog gives the `meteo_kind` of a meteorological station from the
  current series: `climate` for a station in the series of `pl.imgw.meteo_climate_daily`,
  otherwise `precipitation` for one in the series of `pl.imgw.meteo_precip_daily`, and `null`
  without such a series (ČHMÚ always `null`); `check_catalog` reports a change of `meteo_kind` as
  `newer` in the action of the series indexes (ADR-001, errata 2026-10-19).
- `summarize_coverage` and `series.json`: in the monthly and semi-annual datasets, a month or
  period of an archive held in which a station is missing (while other stations are present) is a
  gap in `gaps`, like the days in the daily datasets; for the half-year, a unit counts as held per
  variable (separate archives `polr_H/Q/T`).
- `build_series` returns `unchanged` only for the current series version; when an archive returns
  to an earlier content, a new version is made and becomes current.
- `write_archive`: an earlier HTTP signal that returns with the same bytes (ETag E1→E2→E1) gives
  `unchanged`, not another version `+<8 hex>`; a version whose sidecar has no `extra.http` gives
  `IMGWStoreConflictError`.
- Cleaning `.incoming/` (staging older than 24 h) tolerates a concurrent removal by another
  process and reports every removed directory through `on_notice` with the code
  `leftover_incoming` (`write_archive`, `build_series`, `build_catalog`, `sync_pmaxtp`).
- The check for nested stores before a write does not enter the store's own trees (`archives/`,
  `series/`, `stations/`, `pmaxtp/`, `.incoming/`), so the cost of a write does not grow with the
  number of versions.
- The store needs a file system with hard links, like the store of Kartograf (its ADR-036):
  versions, observations and the marker `imgw-store.json` are published by `os.link`, which never
  replaces a target, so writing works on Linux, macOS and Windows (ext4, APFS, NTFS, an SMB share
  with hard links). A file system without them (FAT, exFAT, some NAS and FUSE, the macOS SMB
  client) gives `IMGWStoreConflictError` (`details.reason="not_atomic"`) in `init_store` and in
  every write; reading needs no links. The `fsync` of a directory is skipped on Windows and on file
  systems that do not support it (ADR-001, errata 2026-10-19).
- A version directory without the sidecar of its main file is an interrupted publication, not a
  version: `current_version` and writes skip it, `iter_store` reports it as `missing_sidecar`
  (also when the main file is missing), and the next write of the same content under the same
  label completes it. An error or Ctrl+C during a publication does not delete the linked data
  files (a concurrent write of the same bytes may have taken them over and committed them with its
  own sidecar): the interrupted publication stays, and only the empty directories this write
  created go. The label of a station catalog is its build date, and that of PMAXTP and of an
  archive without `Last-Modified` the download date (UTC): an interrupted publication that neither
  a retry on another day nor a write of other content completes is removed by hand (the whole
  directory `<label>_<sha8>/` without a sidecar) while no write to the store runs.
- `iter_store` reports a series version with an unsupported `extra.series_schema` (e.g.
  `imgw-series/2`) as the problem `unknown_schema`; `current_version` for such a slot ends with
  `IMGWDataError`.
- Security: `StorePlan.from_json` (also for a plan passed to `POST /api/v1/store/sync`) refuses
  items whose `url` differs from the address in the dataset registry, so HEAD/GET requests reach
  only the IMGW servers.
- `export_series` and `export_archive` create files with permissions that follow the umask (e.g.
  0644); an `output` inside a store → `conflict` (`output_in_store`, see Changed).

#### Schemas and version policy (IMGW-13)

| Schema | File |
|---|---|
| `imgw-store/1` | `<root>/imgw-store.json` — the store marker |
| `imgw-meta/1` | `<file>.meta.json` — the sidecar of every version (optionally `content_sha256` + `content_form`) |
| `imgw-series/1` | `series.json` — the index of a Parquet series (+ Parquet metadata) |
| `imgw-plan/1` | `plan.json` — a freshness plan outside the store |
| `imgw-pmaxtp/1` | `cell.json` — the IMGWTools extension for a PMAXTP cell |
| `imgw-observation/1` | `observations/<YYYY-MM-DD>_<sha8>.json` — the register of signal observations in an archive slot |
| `imgw-result/1` | the result envelope of `run_command`/`check_command`, the CLI stdout and the REST body |
| `imgw-commands/1` | the document of `command_schema()` |
| `imgw-command-list/1` | the document of `list_commands()` |
| `imgw-config/1` | the document of `imgw config show --json` |

Every schema has its own counter `/N`, independent of the package version. Within `/1` only
optional fields are added; readers tolerate additional fields in the store files. An incompatible
change needs `/2`, a period in which both `/1` and `/2` are read, and separate contract tests; old
code does not write to an unknown marker. `store_info` reports an unsupported version
(`supported=False`), and the scan reports a problem and does not parse the files of an unknown
schema. In the 3.x line, public read functions do not disappear and the semantics of `/1` do not
change. The value domains of `/1` (dataset key, country, provider, license, station code,
`location_source`) are open to further providers (see the open value domains above).

Additive fields of the ČHMÚ provider and of the agent support (without a new `/N`):
`imgw-meta/1` — `request.station_code`, `request.param`, `extra.period.station_code`,
`license.terms_url` (written only when set); `imgw-series/1` — `stations[<code>].periods`, the
Parquet columns `<V>_quality`/`<V>_source_flag` and the metadata `variable_notes` (only for
datasets with `measurement_fields` or notes); `stations.geojson` — the property `thresholds`
(ČHMÚ hydro); `imgw-plan/1` — `station_code`, `signal`, `remote_listed_at`, `local_observation`
of the items and `requests` of the plan; `imgw-commands/1` — `lang`, `x-imgw.writes`,
`x-imgw.network`, `x-imgw.operation_id` and `x-imgw-writes`. IMGW-PIB files written by this
release have the same bytes as without the ČHMÚ provider.

#### Tests

- The store contract in `tests/contract/` (offline: HEAD → plan → sync → series → catalog →
  CSV, with the JSON Schemas of §11 shipped in the package).
- The cross-interface contract `tests/contract/test_interface_contract.py`: for all 28 REST
  commands the envelope of `run_command` = the CLI stdout = the REST body, streams byte for byte,
  writes into fresh stores leave identical trees, `?check=true` = `--check` = `check_command`, the
  matrix of 13 error codes (exit code, HTTP status, title, the schemas `cli-error` and
  `problem+json`), pagination windows.
- The MCP contract: `tests/contract/test_mcp_contract.py` (stdio: every contract case, the POST
  plans, the local commands and every CLI error code: MCP = Python = CLI) and
  `tests/contract/test_mcp_http_contract.py` (`/mcp` = REST for every case and error scenario
  except `method_not_allowed`).
- The ČHMÚ contract `tests/contract/test_chmi_contract.py`: every row of the criteria IMGW-15..19
  on `complete_pl_cz` and the recordings, the parity of Python/CLI/REST/MCP for 30 ČHMÚ runs (the
  same envelopes, requests and SHA-256 sums of the trees), 7 `--check` twins, 1 local command and
  4 refused selections; no traffic outside the recordings.
- Unit tests of the ČHMÚ provider (`test_*_chmi.py`, `test_parsing_chmi.py`,
  `test_store_content.py`) and of the agent support (`test_agent_guide.py` with the drift test of
  `AGENTS.md` and `llms.txt`, `test_catalog_effects.py`: declared effects = behaviour,
  `test_catalog_i18n.py`, `test_mcp_tools.py`, `test_mcp_calls.py`, `test_mcp_http.py`,
  `test_mcp_stdio.py`).
- The live regression `tests/live/test_interfaces_live.py` (the marker `live`, a JSON report
  through `IMGW_LIVE_REPORT`): every catalog command through Python, the installed `imgw` and REST
  (`imgw server`) on the IMGW-PIB servers in a fresh store, 6 live errors and the MCP leg
  (`-k imgw_mcp`: one `imgw mcp` process, the 8 network commands that do not write).
  `tests/live/test_chmi_live.py`: the ČHMÚ provider on opendata.chmi.cz (the stations
  `0-203-1-001000` and `0-203-0-11799`) through Python, the CLI, REST and MCP, with a request log
  of every interface.

### Changed

- **Breaking — projects move to Archiwista (ADR-008, Nogat ECO-054, ECO-020):** IMGWTools keeps no
  projects any more; Archiwista owns them (`archiwista-project/1`) and pins store versions by the
  `sha256` and `content_sha256` that the store already records. Removed without aliases: the
  catalog group `project` and its eight commands `project init`, `project add`, `project remove`,
  `project set-store`, `project download`, `project check`, `project status` and `project verify`
  (CLI, REST, MCP; the catalog has 30 commands and 41 example calls); the functions
  `init_project`, `open_project`, `add_project_task`, `remove_project_task`, `set_project_store`,
  `download_project`, `check_project`, `get_project_status`, `verify_project` and the module
  `imgwtools.project`; the types `Project`, `ProjectFile`, `ProjectTask` and `ProjectReport`; the
  exception `IMGWProjectError`; the constant `PROJECT_FILE` (`imgw-project.json`); the contract
  `imgw-project/1` (schema and example in `contract_schemas.json`) and the key `project` of
  `StoreInfo.contracts`; the field `OperationResult.task` and the item status
  `restored_by_content`, so the items of `imgw-result/1` carry no `task`; the message area
  `imgwtools.messages.project`; the flow "Reproducible project" of `AGENTS.md` and `llms.txt`.
  Unchanged: the store and its read API, `content_sha256` and `content_form` in the sidecars
  (`imgw-meta/1`), the observation register (`imgw-observation/1`), `run_command`,
  `check_command`, the read-only `series select` and `imgwtools.testing`. Projects were never
  released, so existing `imgw-project.json` manifests are not migrated (Nogat plan decision D4).
  Migration: keep a project in Archiwista; the command of a stored version comes from
  `command_for_version` (Added).
- **Breaking — `IMGW_DATA_DIR` no longer names the reference data (DEV-18.2):** `IMGW_DATA_DIR`
  (`data_dir`) is now the user data directory (`platformdirs.user_data_path("nogat")` by default),
  the parent of the stores (`<data_dir>/imgw`) and of the server state. The directory of the
  IMGW-PIB reference data (`hydro_stations_locations.csv`, `desc/`) is `IMGW_REFERENCE_DIR`
  (`reference_dir`, `settings.reference_dir`) and defaults to `<cache_dir>/imgw/reference` instead of
  `./data` in the working directory. Migration: set `IMGW_REFERENCE_DIR` where `IMGW_DATA_DIR` held
  the reference data (Retman exports it as its `reference_data_dir`), or run
  `python -m imgwtools.reference_data` again. `IMGW_API_KEYS_FILE` defaults to
  `<data_dir>/imgw/api_keys.json` instead of `./api_keys.json`. A `.env` or exported
  `IMGW_DATA_DIR=./data` left over from 2.x now moves the stores' parent directory.
- `imgw server` takes `--host` and `--port` defaults from `IMGW_HOST` and `IMGW_PORT`;
  `imgw mcp --allow-writes` defaults from `IMGW_MCP_ALLOW_WRITES` (and `[imgw] mcp_allow_writes`) and
  gained `--no-allow-writes`; an empty `IMGW_*` variable counts as unset. `pydantic>=2.10` and
  `pydantic-settings>=2.7` are the minimum versions; `platformdirs>=4` is a new core dependency.
- **Breaking — MCP tool names and OpenAPI `operationId` start with `imgw_` (ECO-018, AGI-5.2,
  AGI-6.2):** `x-imgw.operation_id` is `imgw_<group>_<verb>` (`imgw_store_sync`,
  `imgw_current_hydro_states`), the one name of the REST `operationId`, the MCP tool and the
  guide; routes outside the catalog get `imgw_system_<function>` instead of FastAPI's generated
  ids. Migration: replace `store_sync` by `imgw_store_sync` in MCP clients and OpenAPI
  generators (no alias keeps the old names). The command names (`store sync`), CLI flags,
  REST paths and schema names of the OpenAPI components are unchanged.
- **MCP annotations (AGI-5.4):** every tool carries `title`, `readOnlyHint`, `destructiveHint`
  (now `false` instead of absent on a read-only tool), `idempotentHint` and `openWorldHint`.
  `idempotentHint` comes from the new catalog field `DataCommand.idempotent` (`x-imgw.idempotent`,
  true for every command: a repeated call finds the versions and files it already wrote).
- The first sentence of seven command descriptions is shortened to at most 100 characters
  (DOC-1.7), because it is the `summary` of `commands list`.
- **Development tooling (ECO-010, DEV-6.3, DEV-7.6, DEV-10.1):** mypy `strict` over `src/`
  and `tests/` replaces pyright (per-module deviations are listed in `CLAUDE.md`);
  `scripts/gate.sh` and `scripts/check-commits.sh` (templates of the Nogat standard) run
  `ruff format --check`, `ruff check` (the rule set now includes `SIM`), mypy, pytest with an
  80 % coverage floor and the commit check; `uv.lock` is committed and the environment is
  `uv sync --locked`. The `dev` extra became the `dev` dependency group, so
  `pip install -e ".[dev]"` no longer exists. The marker `live` replaces `IMGW_LIVE=1` for the
  tests against real servers: the gate deselects them, `pytest -m live` runs them.
- **CI (DEV-7.7, DEV-13.6):** `ci.yml` (the gate on Linux, macOS and Windows, a dependency
  audit), `live.yml` (weekly `live` tests) and `dependabot.yml` (GitHub Actions), copied
  from the Nogat templates; they trigger on `main` and `develop`.
- **`forbidden` has the CLI exit code 12 (ERR §2):** the registry code for a refused write or a
  path outside the allowed directories had no exit code (REST 403 and MCP only); it now
  exits 12 like in every tool of the ecosystem, and `command_schema()["errors"]`,
  `AGENTS.md` and the tables of the docs show it. Only `method_not_allowed` stays REST-only.
- **`AGENTS.md` and `llms.txt` within their budgets (DOC-1.7, DOC-4.2):** the generated guide is
  at most 200 lines and 16 KiB in both languages (it was 262 lines and 29 KB) and ends with
  "Developing this repository? Read CLAUDE.md."; it states when to use the tool and when not, and
  how to install it. The command section is an index of one line per command grouped by effect
  (read, network, write, overwrite; `imgw commands schema` serves the options), the dataset table
  lists the datasets of the store and one line the others, the flows and the flag notes are
  shorter, and the stale developer gate commands (pyright) are gone. A contract test holds both
  budgets and the 8,000 characters of `llms.txt` before its first link list.
- **Breaking — `ErrorSpec.title_en` is gone (AGI-9.2):** `ErrorSpec.title` is the English title as
  a catalog message; `title.localized("pl")` is the Polish one. `command_schema`, REST, MCP and
  the web GUI render it in the language of their caller. The first argument of `IMGWError` is
  named `detail`. `Lang` and `LANGS` are exported by `imgwtools.messages` instead of
  `imgwtools.commands`, and `LANGS` is `("en", "pl")` (the order of `details.allowed` of a
  refused language). Migration: `spec.title_en` → `spec.title`, the former Polish `spec.title`
  → `spec.title.localized("pl")`.
- **Breaking — `DatasetDescriptor.title_en` is gone (AGI-9.2):** `DatasetDescriptor.title` is the
  English title as a catalog message (`messages/datasets.py`); `localize(title, "pl")` is the
  Polish one, and `datasets list` renders it in the language of its caller. The `variable_notes`
  of the ČHMÚ datasets are English catalog messages, so the `variable_notes` of the Parquet
  metadata of `series.json` is English now (the Polish wording was written before the first
  release; a series built earlier keeps its Polish notes and is not rewritten). The web GUI
  shows the Polish titles as before. Migration: `descriptor.title_en` → `descriptor.title`, the
  former Polish `descriptor.title` → `localize(descriptor.title, "pl")`.
- **Breaking — `help_en`, `description_en` and `rules_en` of the catalog are gone (AGI-9.1, ADR-006):**
  `CommandOption.help`, `DataCommand.description` and `DataCommand.rules` hold the English catalog
  `Message` (the texts of `commands.py` are the entries of `messages/commands.py`, 143 of them,
  English first) and `CommandOption.help_en`, `DataCommand.description_en` and
  `DataCommand.rules_en` are removed without an alias. `command_schema`, `list_commands` and the
  CLI help render the language asked for (`localize(text, "pl")` is the Polish text); the documents
  of both languages are byte-identical to the ones before. The last Polish literals left the code:
  the message guard has no pending files any more and fails on any Polish string outside
  `imgwtools.messages`. Migration: `option.help_en` → `option.help`, the former Polish
  `option.help` → `localize(option.help, "pl")` (the same for `description` and `rules`).
- **Breaking — `IMGW_STORE_ROOT` is `IMGW_ROOT` and the store has a default location (DEV-19.2,
  ADR-007 D2, D9):** the variable is renamed without an alias, `Settings.store_root` is
  `Settings.root` and `root` in `[imgw]` of `nogat.toml` sets it too. A command without `--root`
  uses the store at `IMGW_ROOT`, `[imgw] root` or `<data_dir>/imgw` (`imgwtools.store_root()`):
  `root` is optional in every store command and `validate_command` fills it in (not for a command
  given a `version`, not for `stations find` unless `source=store`), so the `--root` of the CLI no
  longer reads an environment variable of its own. `imgw config show --json`
  reports `store.root` with its source, whether it exists and its size. The REST server still writes
  only to its configured `IMGW_ROOT`, never to the default. `imgw mcp` has `--allow-dir DIR`
  (repeatable): every path option and the default root must lie inside an allowed directory
  (`forbidden`, `details.reason="outside_allowed_dirs"`) and a write without any directory is
  `forbidden` (`no_allowed_dir`), while a plan needs none. Migration: rename `IMGW_STORE_ROOT`; pass
  `--allow-dir` to `imgw mcp --allow-writes`.
- **Breaking — the store status `created` is `new` (DEV-19.19, ADR-007 D7):** `VersionResult`,
  `OperationResult`, `SeriesReport`, `CatalogReport`, `PMaXTPStoreResult` and the fixture builder
  say `new` where they said `created`, and a series version built from the same inputs is
  `unchanged` (it was `reused`); `relabeled` stays. The
  statuses of plain files, `written` and `replaced`, come with plain mode. Migration:
  `status == "created"` → `"new"`, and `"reused"` → `"unchanged"` for a series.
- **Breaking — the store marker, the first write and nested stores (DEV-19.12 to DEV-19.14,
  ADR-007 D5, D6):** `imgw-store.json` always has `schema`, `tool` (`imgw`), `created_at` and
  `producer_version` besides `created_by` (an older marker gains the missing fields on the next
  write). The first write into an empty or new root creates it (`write_archive`, `sync_pmaxtp`,
  `build_catalog` and so `store sync`); only `api_keys.json` of the server may lie in an empty
  root. A root with `archives/`, `series/`, `stations/` or `pmaxtp/` and no marker is
  `store_unavailable` (`details.reason="no_marker"`, hint `imgw store init --root <path>`), and
  `init_store` / `imgw store init` verifies the layout (every sidecar `imgw-meta/1`, nothing
  foreign beside the trees, else `data_error` with `details.reason="invalid_layout"`) before it
  writes the marker. A directory with other files and no layout is `conflict`
  (`details.reason="not_empty"`, it was `path_conflict`). A store never nests: before a write the
  command looks for `kartograf-store.json` and `imgw-store.json` in the ancestors of the root, at
  the root and below it, and a nested store is `conflict` with `details.reason="nested_store"`; the
  old probe of Kartograf by `kartograf-project.json` and `kartograf-meta/1` sidecars is gone. Plans
  (`check_store`, `check_series`, `check_catalog`, `check_pmaxtp`) treat a new or empty root as an
  empty store and create nothing. The module `imgwtools.output` (marker names, the check of a plain
  target list, the staging directory with SIGTERM handling, `FileResult`) is added for the plain
  mode that follows.
- **Breaking — `datasets download` writes plain files with `--output-dir` or the store
  (DEV-19.1, DEV-19.5 to DEV-19.11, DEV-19.19, ADR-007 D1, D3, D4, D5, D7):** `download_archives(...,
  output=)` and the CLI `--output`/`-o` (default `./data/downloaded`) are gone without an alias:
  `output_dir` (`--output-dir`, `-o`) writes ordinary files named like the server paths
  (`<dir>/<server_path>`), `root` (`--root`) publishes versions in the store, and a call with
  neither goes to the store at the default root. The two exclude each other (`validation_error`,
  `details.reason="exclusive_options"`, `details.options`). A plain write checks the whole target
  list before the first request: an existing target without `--force` is `conflict`
  (`output_exists`), duplicate names `duplicate_output_name`, a directory that is or lies in a
  store of IMGWTools or Kartograf `output_in_store` (hint `--root`); `details.paths` lists every
  path and nothing is written. Files stream into `<dir>/.imgw-incoming/<host>_<pid>_<token>/`,
  are hashed while they stream, verified (ZIP) and moved with `os.replace` (the staging directory
  goes on success, error, SIGINT and SIGTERM; leftovers older than 24 hours go with the next
  run), so no `.part` file is left beside a target and no hard link is needed (FAT, exFAT, SMB).
  `--force` replaces existing targets and deletes nothing else; in the store it fetches again and
  never overwrites a version. A store download takes the seven store datasets only
  (`details.reason="not_in_store"` otherwise, hint `--output-dir`). `DownloadReport` is `mode`,
  `output_dir`, `root`, `items`, `files` and `cancelled`: `files[]` is `{path, size_bytes,
  sha256, status}` with `written` or `replaced` (plain) and `new`, `unchanged` or `relabeled`
  (store). `--check` plans each target as `write`, `replace` (with `--force`) or `conflict`
  (`PlanAction.action`, `path`, `reason`; the plan is `ok` and exits 0 whatever it lists, only
  the real run fails). The command schema publishes `x-imgw-path-role` (`input`, `output`,
  `root`) of every path option,
  `x-imgw-store-only` of an option and `x-imgw.exclusive` and `x-imgw.store_only` of a command;
  the CLI prints the paths of every result relative to the validated root, the default root
  included. Migration: `--output DIR` → `--output-dir DIR`; `output=` → `output_dir=`; read
  `report.output_dir`, `report.files[].path` and `status`.
- **`store sync` and `pmaxtp sync` write plain files too; the options that act on versions are
  store-only (DEV-19.9, DEV-19.17, DEV-19.18, DEV-19.19, ADR-007 D3, D7, D8):** `sync_store`,
  `sync_pmaxtp` and `check_pmaxtp` take `output_dir` and `force` and an optional `root` (the
  default root when neither is given). `store sync --output-dir` writes the selected archives
  as `<dir>/<server_path>` with the rules of `datasets download` (preflight, staging,
  `--force`, `output_in_store`) and with no freshness check, no plan and no series; ČHMÚ station
  files need `--years` there (`details.reason="years_required_in_plain_mode"`). `pmaxtp sync
  --output-dir` writes `<METHOD>/<indX>_<indY>/cell.json` and the raw `response.json`: the names
  come from the answer, so only a call that gives `--ind-x` and `--ind-y` refuses before the
  request. `plan` and `series` of `store sync` are store-only: with `output_dir` they are
  `validation_error` with `details.reason="store_only_option"`; `store init`, `store catalog` and
  `series build` have no plain mode and say so in their rules (`x-imgw.store_only`). In the store
  `store sync --force` fetches
  every selected archive again (a version is never overwritten). `SyncReport`, `SeriesReport`,
  `CatalogReport` and `PMaXTPStoreResult` list `files[]` (`{path, size_bytes, sha256, status}`
  from the sidecar, statuses `new`, `unchanged`, `relabeled`; `written` and `replaced` for plain
  files); `imgwtools.FileResult` is exported. The plain `--check` plan of both commands is
  `write`, `replace` or `conflict` per target.
- **Breaking — the exports write one plain file with `--output` (DEV-19.1, DEV-19.5 to DEV-19.11,
  DEV-19.19, ADR-007 D1, D3, D7):** `export_archive`, `export_series` and `agent_guide` (the
  commands `store export`, `series export` and `commands guide`) take `output` and `force` instead of
  `path`; the CLI `--path` and `-p` are gone without an alias (`--output` has no short form).
  Without `output` they still return the lines (stdout, REST attachment, MCP text). With it the one
  target is checked before anything is read for it: an existing file without `--force` is
  `conflict` (`details.reason="output_exists"`), a file in a store of IMGWTools or Kartograf
  `conflict` (`output_in_store`; it was a `validation_error` rule of the catalog, and the hint says
  to choose a file outside every store, because an export has no store mode), `details.paths`
  names the file; a directory is `validation_error` (`details.option="output"`); a missing
  directory is created. The lines stream through `<dir>/.imgw-incoming/<host>_<pid>_<token>/`
  (the directory that holds the file), are hashed while they are written and the file moves
  into place with `os.replace`, so no `.part` file is left and an interrupted export leaves
  the target as it was. The result is the new `imgwtools.OutputReport` (`output`, `files[]` of
  `{path, size_bytes, sha256, status}` with `written` or `replaced`); the envelope `result` is
  that object where it was the path string. `force` needs `output` (`validation_error`,
  `details.option="output"`, `dependentRequired` in the schema). `--check` plans the file as
  `write`, `replace` (with `--force`) or `conflict` (a plan with a conflict is `ok`, only the run
  fails). The schema marks `output` `x-imgw-writes: add` and `force` `replace`
  (`x-imgw-path-role: output` for the file); both are local options, so REST takes neither. An
  MCP server writes `output` only inside `--allow-dir` (`forbidden`, `outside_allowed_dirs`) and
  not at all without a directory (`no_allowed_dir`; it was possible for an export file and
  for the `plan` file of `store check`). `AGENTS.md` and `llms.txt` are regenerated with
  `imgw commands guide --format agents --output AGENTS.md --force`; two sentences of the guide
  that repeated other lines were dropped to keep it within 16 KiB. Migration: `path=` →
  `output=` (plus `force=True` to replace a file), `--path F` → `--output F`, the returned
  `Path` → `report.output`, the envelope `result` `"<path>"` → `{"output", "files"}`.
- File-system errors (`describe_os_error`, `io_error`) and the default text of
  `IMGWStoreDependencyError` are English; `IMGWError.localized("pl")` gives the Polish text.
- **Breaking — the `detail` of every error is English (AGI-9.2, ADR-006):** every raise site of
  `IMGWError` and its subclasses (and of the validators whose text another message embeds) gives
  a catalog message (`imgwtools.messages.<area>`, about 570 entries) instead of an inline Polish
  sentence, so `str(exc)`, `exc.detail`, the `--json` error line, the plan and item errors of
  a failed unit and every caller of the library read the same English text. `details` stay
  unchanged. Polish is `exc.localized("pl")`; REST (`Accept-Language: pl`) and the web GUI render
  both the `title` and the `detail` in the language of their caller (the `detail` used to stay
  Polish next to an English `title`). `imgwtools.messages.reason(exc)` gives the catalog message
  an exception carries, so a message that embeds a caught error stays translatable. Migration:
  tests and clients that matched Polish `detail` text match the English text or
  `exc.detail.key`.
- The text of a cancelled plan item and of a cancelled version write is English (`cancelled`, "The
  write of the archive was cancelled"); the plan item error `anulowano` became `cancelled`.
- **Breaking — notices, progress lines and plan lines are English (AGI-9.2, ADR-006):** the
  `text` of every `Notice`, the `message` of every `Progress`, the `detail` of every `PlanAction`,
  the `error` of a plan item or a result item and the problems of a catalog or series report are
  catalog messages (more entries in `imgwtools.messages.<area>`), English by default;
  `Message.localized("pl")` gives the Polish
  text. The `license_terms` notice is the
  attribution followed by the translated notice of the provider (`ProviderDescriptor.license_notice`);
  the attribution formulas themselves and the official name of IMGW-PIB keep their wording in every
  language (`imgwtools.messages.legal`), because sidecars, series, catalogs and CSV exports persist them.
  The error of an unpublished ČHMÚ file is `not published` (it was `nieopublikowany`; Retman
  and Archiwista compare it) and the server errors of a check begin `Timed out waiting for`,
  `HTTP error`, `Connection error to`; `check_failed` items of a saved plan are classified by
  that English text. Migration: match `not published` and the English texts, or the language-free
  `Message.key` of an item that has one.
- **Breaking — the `detail` of the CLI error line is English (AGI-9.2, ADR-006):** the last line of
  stderr was Polish for a syntax error (unknown option or command, a missing option or value), an
  interrupt, a program error and `IMGW_LANG` outside `pl` and `en`; it is English whatever
  `IMGW_LANG` says, like the envelope on stdout. The human-readable output follows `IMGW_LANG`
  (`pl` by default): the help, the progress lines, the notice lines and their labels (`Informacja`
  or `Info`), `imgw admin`, `imgw config show` and `python -m imgwtools.reference_data`; their texts
  are catalog messages (`imgwtools.messages.cli`, `imgwtools.messages.reference`), and
  `imgwtools.config.human_language()` is the one reader of the setting. Migration: clients that
  matched the Polish `detail` of a usage error match the English text or `details.option`.
- **Breaking — the MCP server speaks English only (AGI-9.2, ADR-006):** `imgw mcp --lang` and the
  `lang` argument of `create_server`, `run_stdio` and `http_app` are removed, and `IMGW_LANG` no
  longer reaches the server or `/mcp` (the REST server stopped refusing an `IMGW_LANG` outside
  `pl` and `en` for `/mcp`; the CLI still refuses it). The tool descriptions and rules, the
  instructions and the error documents (`title`, `detail`) are English; `/mcp` asks its REST route
  for `Accept-Language: en`; the `lang` argument of the three description tools defaults to `en`
  (an explicit `lang: "pl"` still gives Polish texts). `docker-compose.yml` no longer passes
  `IMGW_LANG` to the server. Migration: drop `--lang` and `IMGW_LANG` from MCP client
  configurations.
- **Breaking — the description commands default to English (AGI-9.2, ADR-006):**
  `command_schema()`, `list_commands()`, `agent_guide()` and the `lang` option of `commands list`,
  `commands schema` and `commands guide` default to `en` in Python and the CLI (REST answers
  follow `Accept-Language`, English without it). `IMGW_LANG` is no longer the default of
  `--lang`: it keeps the language of the CLI help and human lines, and `imgw <command> --schema`
  prints the English schema. The committed `AGENTS.md` (175 lines, 16,174 bytes) and `llms.txt` are
  English, and `--lang pl` generates the Polish guide (16,262 bytes). The guide's own texts (column
  titles, effect classes, flow titles and notes, the rules shared with the MCP instructions, the
  value syntax of the flags) are catalog messages (`imgwtools.messages.agent_guide`, 52
  entries) instead of Polish and English literals in `agent_guide.py`. Migration: pass `lang="pl"`
  or `--lang pl` where the Polish descriptions were meant; regenerate the guide files with
  `imgw commands guide --format agents --output AGENTS.md --force` (and `--format llms --output llms.txt --force`).
- **Breaking — REST answers in English by default and the OpenAPI document is English (AGI-6.4,
  AGI-9.2, ADR-006):** without `Accept-Language`, or with one that names neither `en` nor `pl`, a
  REST answer is English: the `title` and `detail` of problem+json, the notices, the texts of
  failed items and plan actions, and the `lang` of the three description commands (it was Polish).
  `Accept-Language: pl` gives Polish. The language now decides every command answer, not only
  those of commands with a `lang` option: the notices and item texts of the JSON envelope and the
  `X-IMGW-Notices` header of an export are rendered in it, every command answer has
  `Content-Language`, and `Vary: Accept-Language` when the header (not `?lang=`) decided. The
  texts of the generated routes (summaries, descriptions, options, rules, tags, responses) come
  from the English catalog, and the field descriptions of the result models (`models.py`, 47
  texts, they feed the OpenAPI schemas) are English, so `/openapi.json`, `/docs` and `/redoc`
  are English. The `to_dataframe()` error without pandas is the catalog message
  `models.pandas_required`. The `api/*` and `models.py` modules leave the pending files of the
  message guard. Migration: REST clients that relied on the Polish default send
  `Accept-Language: pl`.
- By default the server still only generates URLs to IMGW; data reach the disk only on the user's
  command (`--output-dir`, `--output`, `--root`, `IMGW_ROOT` or the default store
  `<data_dir>/imgw`) or in the `IMGW_ROOT` configured on the server.
- The archive URLs (library, CLI, REST, web) come only from the registry `archive_files`, without
  a hard-coded upper bound of the year.
- The hydro station list keeps `river_order` (the fourth column of the CSV) and
  `hydrographic_code`.
- License texts come from the provider registry: the `license_terms` notice and the attributions
  of sidecars, series, the catalog and CSV exports (IMGW-PIB: the wording is unchanged; ČHMÚ:
  CC BY 4.0 with the mark of processing); download errors name the provider.
- The web GUI stays with the IMGW-PIB datasets: the archive form shows
  `datasets(provider="IMGW-PIB")`, and the station search asks `provider="IMGW-PIB"`.
- `imgw --help`, the OpenAPI description and the `datasets` group ("Registry of providers and
  datasets: list, files and download") name both providers; `imgw --help` lists `imgw mcp`.
- A manual CLA process (`docs/CLA.md`, `CONTRIBUTING.md`, `CONTRIBUTORS.md`, the pull request
  template).
- The module `imgwtools.reference_data` (`python -m imgwtools.reference_data`); the IMGW data are
  removed from the repository.
- License metadata following PEP 639 (`license = "MIT"`, `license-files`).
- A README section on the data sources and the IMGW-PIB attribution.
- NumPy docstrings in all of `src/`, enforced by the ruff `D` rules; `ruff format` over the whole
  repository.
- `imgw version` reads `__version__`.

### Fixed

- **`import imgwtools` without an extra:** `imgwtools.config` imports `pydantic-settings` and
  `import imgwtools` reaches it (`agent_guide` → `commands` → `config`), but the package listed
  the dependency only in the `api` and `cli` extras, so `pip install imgwtools` and
  `imgwtools[store]` failed with `ModuleNotFoundError: pydantic_settings`. `pydantic-settings>=2.7`
  is a core dependency now (removed from the extras). The fallback that read the reference
  directory without it (`_environment.reference_dir()` in `store/catalog.py`) is gone; a test
  installs the built wheel without extras into a fresh venv and calls a public function.
- **`--check` and a nested store (DEV-19.10, DEV-19.14):** `imgw datasets download --root <dir in
  another tool's store> --check` planned the download as `missing` while the run refused it with
  `conflict` (`nested_store`); the plans of `store init`, `store sync`, `pmaxtp sync`, `series
  build` and `store catalog` had the same gap, and the plans of `store sync` and `store catalog`
  even sent requests, and the plans of `store sync`, `pmaxtp sync`, `series
  build` and `store catalog` raised `store_unavailable` for a root that holds another tool's store
  or a store below it. Each plan
  now lists one action `conflict` with `reason="nested_store"`, the root as `path` and status
  `unverifiable`; the plan is `ok` (exit 0), like the plain plan for `output_in_store`, and nothing
  is requested. `PlanAction.reason` gains `nested_store`; a saved plan keeps the action.
- **A root with other files, `--check` and the run (DEV-19.10, ADR-007 erratum):** the plan of
  every store write listed a root that holds other files and is no store (or is a file) as
  `check_failed`, or raised `store_unavailable`, while the run of `datasets download`, `store init`,
  `store sync`, `series build`, `store catalog` and `pmaxtp sync` refused it with `conflict`
  (`not_empty`; `store sync` and `series build` said `store_unavailable`). `not_empty` is a
  `conflict` of the root like `nested_store` now: the plan lists one action `conflict` with
  `reason="not_empty"` (`PlanAction.reason` gains it), the plan is `ok` and asks nothing, and
  every run refuses the root with `conflict` before any request. These are not conflicts and the
  plan raises them as errors, `datasets download --check` included (it turned them into a
  `check_failed` action): a root with the layout and no marker is `store_unavailable`
  (`no_marker`), and an unreadable marker (invalid JSON, no `schema`) is `data_error`
  (`details.reason="invalid_marker"`; the writer said `store_unavailable`), in the plan and the
  run; the reader keeps its `invalid_marker` problem code.
- **A plain output directory in a store is refused by the directory (DEV-19.6, DEV-19.11, ADR-007
  erratum):** the run of `datasets download`, `store sync` and `pmaxtp sync` listed every target of
  an `output_dir` that is or lies in a store in `details.paths`, and `pmaxtp sync` without cell
  indices asked for the cell first. The directory is checked before any request now:
  `details.paths` is the output directory (`details.reason="output_in_store"`). A store found only
  below the directory, in a subdirectory a target would enter, is still reported by the path of
  each such target, and so is the file of an export (`output`); the `--check` plan keeps one
  `conflict` action per target.
- **`py.typed` (DEV-7.4):** the package declared `Typing :: Typed` but shipped no PEP 561 marker, so
  mypy treated `import imgwtools` in a consumer as untyped (`module is installed, but missing
  library stubs or py.typed marker`). `src/imgwtools/py.typed` is part of the wheel now; a test
  checks the built wheel for it and type-checks a consumer snippet with strict mypy against the
  installed package, without `ignore_missing_imports`.
- **A marker without `created_by` (DEV-19.12, ADR-007 erratum):** `store_info`, `iter_store` and
  `current_version` refused a marker that lacks a `created_by` text (`invalid_marker`), although
  `open_store` opened it and DEV-19.12 asks of a marker only `schema`, `tool`, `created_at` and
  `producer_version`; a store the writer had completed (it adds those three fields, never
  `created_by`) could not be read. The reader needs only `schema` now, exactly like `open_store`
  (a test holds the two to the same markers); `created_by` stays in the marker `init_store` writes
  but is an optional field in the packaged `imgw-store/1` schema, and the message
  `reader.marker_has_no_valid_created` is gone. A reader only accepts more: the contract stays
  `imgw-store/1`.
- **`PMaXTPData` takes fractional probabilities and refuses unpublished ones (request of
  Hydrograf):** `get_precipitation`, `get_confidence_bound` and `get_estimation_error` were
  annotated `probability_percent: int`, but the tables hold 27 probabilities from `"0.01"` to
  `"99.9"` (`"98.5"`, `"99.5"`) and the key was `str(value)`: a caller that asked for 0.01 to 98.5
  had to silence the type checker, `1.0` looked for the key `"1.0"`, and a number the tables never
  had (`999`, a typo, `0.5` meant as `50`) read as an absent value, `None`. The parameter is a
  `float` (an `int` is one): `50` and `50.0` are the key `"50"`, `0.01` and `98.5` are found, and a
  probability that is not one of the 27 published ones (also `nan`, a `bool` or a text) is
  `validation_error` (`IMGWValidationError`) with `details.option="probability_percent"`,
  `details.value` and `details.allowed`, the 27 percentages as numbers, which the message lists
  too. A published probability that the data lacks, or a duration that it lacks, is still `None`.
  A caller that relied on `None` for a probability that is not published gets the error now. The
  docstrings of `PMaXTPData` and `fetch_pmaxtp` give the 16 durations and the 27 probabilities
  (they said 7 and 6).
- **`imgw mcp` sends nothing but protocol messages on stdout, also when the client leaves (the
  stdio transport of MCP):** while the server serves, the SDK points file descriptor 1 at
  stderr, so a `print` in a command goes there; but a client starts the server without
  `PYTHONUNBUFFERED`, so stdout is block-buffered, and the text that Python still held was
  flushed at exit, after the SDK had restored the descriptor: a line that is no JSON-RPC message
  reached the client. `run_stdio` flushes stdout before the SDK restores it, as Hydrolog and
  Kartograf do, and the text goes to stderr (found by the final integration run of the data
  output). A test starts `imgw mcp` without `PYTHONUNBUFFERED` with a command that prints.
- `API_VERSION` of REST (`/health`, `/api/v1`, OpenAPI) equals `__version__` instead of the
  constant `1.0.0`; the web footer and the `app.js` log no longer show a fixed `v1.0.0`.
- The current data read the actual fields of the IMGW API (`stacja`, `kod_stacji`,
  `temperatura_powietrza`, `wiatr_srednia_predkosc`, `wilgotnosc_wzgledna`, `opad_10min`), so
  station names and measurements are no longer empty; `HydroCurrentData` reads the current keys
  `wojewodztwo` and `przeplyw_data` (before, `province` and `flow_date` were always `None`).
- Invalid JSON from the IMGW API: `fetch_*` raise `IMGWDataError` (`data_error`) instead of a raw
  `JSONDecodeError`.
- `read_meta` refuses a sidecar whose `dataset` field does not match the key pattern of the
  registry (spec §11.2).
- `fetch_pmaxtp`/`fetch_pmaxtp_async` no longer return empty `ks/sg/rb` tables as a success: an
  answer with an `error` field or without the `ks` table raises an exception. A point inside the
  coordinate frame but outside the PMAXTP grid (e.g. Kaliningrad, Lviv, the Baltic; the API
  answers "Brak pliku, pradopodobnie poza obszarem PL", no file, probably outside Poland) gives
  `IMGWValidationError`, also in `sync_pmaxtp` (CLI 2, REST 400); other API errors stay
  `IMGWDataError`, network errors `IMGWConnectionError`. Coordinates outside Poland are refused
  before the request is sent.
- `fetch_pmaxtp` and `fetch_pmaxtp_async` report coordinates outside Poland with the same message
  as `sync_pmaxtp`/`check_pmaxtp` (e.g. "Latitude 40.0 is outside Poland (49.0–55.0)").
- The same notice (code and text) goes into the envelope and to the CLI stderr once per command
  (e.g. `license_terms` while hundreds of archives sync); the `on_notice` hooks of Python still
  get every notice.
- REST also hides the directory of the reference data (`IMGW_REFERENCE_DIR`; e.g. a missing
  locations file in `POST /api/v1/store/catalog`) in its texts (`problems`, `detail`, `error`),
  not only `IMGW_ROOT` and `IMGW_USER_LOCATIONS_DIR`.
- The station catalog reports in `problems` a code repeated in the station list (in
  `wykaz_stacji.csv` IMGW lists three meteo stations twice, with different short codes) and uses
  the first row; before, the last row won without a trace.
- `pl.imgw.meteo_climate_daily`: `normalize_archive`, `read_archive` and `build_series` read only
  the files `k_d_<period>.csv` (`o_d_<period>.csv` for precipitation). Before, they also matched
  `k_d_t_*.csv`, present in every climate package of 1951–2025, and 330 of 350 archives failed
  with "Za mało kolumn" (too few columns).
- `pl.imgw.hydro_semiannual`: the layout of the date columns of `polr_*` is recognized per file —
  16 columns (1951–2022: year, month, day, hour without minutes), 17 with a repeated hydrological
  year (1997), 2023 with an undescribed field after the date and trimmed empty columns
  (17/19/20), 18 from 2024; a mixed or unknown layout is `IMGWDataError`. Before, 145 of 225
  archives failed, and in the others the end date of an extremum was always empty. Now all 225
  archives of 1951–2025 give the end date wherever IMGW publishes it; the date has the precision
  of the publication (a missing day or month → the start of the unit, hour 24 → midnight of the
  next day, day 31 in a shorter month → its last day).
- `pl.imgw.hydro_semiannual`: the min/max rows that IMGW repeats for successive occurrences of an
  extremum (the same value, other dates) no longer stop the build of a series ("Sprzeczne daty
  ekstremum": contradicting extremum dates). `normalize_archive` merges them into one record
  with the earliest start, the latest end and the number of rows in the new field
  `NormalizedRecord.extrema_occurrences`; Parquet gets the additive column `<V>_occurrences`
  (`int32`, `imgw-series/1`), and `read_series`, the CSV export, `export_archive` (`store export`)
  and `series read` give `<V>_occurrences` / `extrema_occurrences`. Different values of the same
  key are still a data error.
- The meteo parsers skip a first row made of column codes (e.g. `kansp,kapost,…` in
  `o_d_08_2025.csv`; before: "Niepoprawny kod stacji", invalid station code); every other bad
  row still gives `IMGWDataError` with the line number.
- `build_series` no longer holds the values of all stations in memory: the verified records go to
  compressed temporary files per station outside the store (`TMPDIR`), and the stations are
  assembled and written one after another. The peak RSS for the full years 1950–2025:
  `meteo_precip_daily` (26.6 million records) 0.85 GB instead of 9.0 GB, `hydro_daily` 0.41 GB
  instead of 6.8 GB; `series.json` and the Parquet files are byte-for-byte unchanged.
- `build_catalog` also takes every station code of the current `series.json` indexes of all
  datasets: stations known only from the archives (e.g. closed gauges and the conventional IMGW
  code `123456789` of `mies_1997`) go into `stations.geojson` as historical (`active=false`,
  `geometry=null`, `location_missing_reason="none"`), counted in the new field
  `CatalogReport.from_series`, with the notice `series_station` and `series` entries in
  `extra.catalog[]` of the sidecar; `check_catalog` reports `newer` when a series code is missing
  from the catalog. The catalog version changes only when the content changes.
- `imgw store export … | head` and `imgw series export … | head` end with exit code 0 and no
  message when the reader closes the pipe.
- An unreadable version (e.g. a `PermissionError` on `series.json` or a Parquet file) gives
  `io_error` instead of `data_error`/`conflict`, with the same content (the reason,
  `details.path`) in the CLI and REST.
- The Docker image builds: the base is `python:3.12-slim` instead of `python:3.11-slim` (the
  package needs Python ≥ 3.12), there is no `COPY data/` (the directory is not in the
  repository), `pyproject.toml`, `README.md`, `LICENSE` and `src/` are copied, `.[api,mcp]` is
  installed, and one uvicorn process runs. `docker/docker-compose.yml` has no obsolete `version`
  key and takes `IMGW_MCP_ENABLED` and `IMGW_MCP_ALLOWED_HOSTS` from the environment of
  `docker compose`.

### Migration guide: data output (ADR-007, DEV §19)

What a caller of IMGWTools (Python, `imgw`, REST, MCP) or a reader of its files has to change. The
entries above give the reasons and every detail; this is the list to follow. The names are those of
the unreleased 3.0.0, so no earlier release has to keep working and no alias exists.

**The three targets (DEV-19.1, DEV-19.2).** `output_dir` (`--output-dir`, `-o`) writes plain files,
`root` (`--root`, `-r`) writes the versioned store, `output` (`--output`, no short form) writes the one
file of an export; `--force` replaces existing plain files. `output_dir` and `root` exclude each other
(`validation_error`, `exclusive_options`). A writing command given neither writes the store at the first
of `--root`, `IMGW_ROOT`, `[imgw] root` of `nogat.toml` and `<data_dir>/imgw` (`imgw config show --json`
names it and its source), never into the working directory. A REST server writes only to its own
`IMGW_ROOT`, with writes enabled and the token, and takes no `root`, `output_dir`, `output` or `force` in
a request; `imgw mcp` writes only inside its `--allow-dir` directories and with `--allow-writes`.

| Old | New |
|---|---|
| `IMGW_STORE_ROOT`, `Settings.store_root` | `IMGW_ROOT`, `Settings.root`; `root` is optional in every store command (default store) |
| `IMGW_DATA_DIR` as the directory of the reference data | `IMGW_REFERENCE_DIR` (`IMGW_DATA_DIR` is the user data directory) |
| `download_archives(output=DIR)`, `datasets download --output/-o DIR` (default `./data/downloaded`) | `output_dir=DIR`, `--output-dir/-o DIR` for plain files; `root=`, `--root` for versions in the store; neither: the default store |
| `DownloadReport.output` | `DownloadReport.mode` (`plain`/`store`), `.output_dir` or `.root`, `.files` |
| `export_archive`, `export_series`, `agent_guide` with `path=F`; `--path F`, `-p F` | `output=F` (`force=True` over an existing file); `--output F` (`--force`) |
| their `Path` result; envelope `result` `"<path>"` | `OutputReport` (`.output`, `.files`); `{"output": …, "files": […]}` |
| status `created`; series status `reused` | `new`; `unchanged` |
| `.part` files beside the targets | staging directory `<dir>/.imgw-incoming/<host>_<pid>_<token>/`, removed after every run (success, error, SIGINT, SIGTERM) |
| `imgw-store.json` with `schema`, `created_by` | also `tool` (`imgw`), `created_at`, `producer_version`, always; the first write creates it, `imgw store init` only verifies the layout |
| nested stores found by `kartograf-project.json` and `kartograf-meta/1` sidecars | by the marker names `kartograf-store.json` and `imgw-store.json` only |
| `imgw mcp --allow-writes` alone | needs `--allow-dir DIR` (repeatable) for any write and for any `output`, `output_dir` or `plan` file |

**Results (DEV-19.19).** Every writing command lists `files[]` = `{path, size_bytes, sha256, status}`
with `written` or `replaced` (plain) and `new`, `unchanged` or `relabeled` (store); `sha256` is computed
while the file is written. `items[]` keep the per-unit outcomes (`DownloadItem`: `downloaded`,
`not_published`, `failed`, `cancelled`; a plain `store sync` item is `new` for a written file).
`--check` plans each plain target as `write`, `replace` (with `--force`) or `conflict`
(`PlanAction.action`, `path`, `reason`); a plan with conflicts is `ok` (exit 0), only the run fails.

**Errors** (codes of the registry; `details.reason` is the new precision):

| Code (CLI exit) | `details.reason` | When |
|---|---|---|
| `conflict` (4) | `output_exists` | a plain target exists and there is no `--force`; `details.paths` lists every such file |
| `conflict` (4) | `duplicate_output_name` | two targets of one request have one name; `details.paths` |
| `conflict` (4) | `output_in_store` | the output directory is or lies in a store of IMGWTools or Kartograf (`details.paths` is the directory, before any request); a target that would enter a store below the directory, or the file of an export, is reported by its own path |
| `conflict` (4) | `nested_store` | the root lies in, holds or nests a store of any tool |
| `conflict` (4) | `not_empty` | a store write or `store init` into a directory with other files and no layout (was `path_conflict`), or into a file |
| `store_unavailable` (8) | `no_marker` | a root that has the layout and no marker; hint `imgw store init --root <path>` |
| `data_error` (7) | `invalid_layout` | `store init` found a foreign or invalid file |
| `data_error` (7) | `invalid_marker` | the marker of the root is unreadable (invalid JSON, no `schema`); it was `store_unavailable` in the writer |
| `validation_error` (2) | `exclusive_options` | `output_dir` with `root` (`details.option` is `root`, `details.options` both) |
| `validation_error` (2) | `store_only_option` | `plan` or `series` of `store sync` with `output_dir` |
| `validation_error` (2) | `not_in_store` | a store download of a dataset that has no place in the store (hint `--output-dir`) |
| `validation_error` (2) | `years_required_in_plain_mode` | plain `store sync` of ČHMÚ station files without `years` |
| `forbidden` (12) | `no_allowed_dir`, `outside_allowed_dirs` | an MCP write without `--allow-dir`, or outside it |

An `output` that is a directory, a `force` without `output` and a plain `output_dir` that is a file are
`validation_error` with `details.option`.

**Unchanged.** `fetch_pmaxtp`, `download_hydro_data`, `download_meteo_data` and every reader
(`read_*`, `iter_store`, `current_version`, `store_info`); the store layout and the schemas
`imgw-meta/1` (its sidecar already has the core of DEV-19.16, held by a contract test),
`imgw-series/1`, `imgw-pmaxtp/1`, `imgw-observation/1`; the envelope `imgw-result/1`, `imgw-plan/1`
(only the optional `action`, `path`, `reason` are new), the error registry and exit codes, the REST
routes and `operationId`s, the MCP tool names.

**Per consumer** (checkouts of 2026-10-25):

- **Retman** (`src/retman/tools/imgwtools/`): `calls.py:226-228` and `calls_archives.py:271-272` give
  `path` to an export: pass `output` (add `force` only where a step may repeat in one result folder);
  `calls_archives.py:90-91` gives `output` (a directory) to `datasets download`: pass `output_dir`;
  `client.py:235-240` and `:272` look for `path` and take the export result as a string: use `output`
  and `result["output"]` (or `files[0]["path"]`); `describe.py:717` and `describe_archives.py:104-125`
  match `created` and `reused`: match `new` and `unchanged`; `client.py:62-71` exports
  `IMGW_DATA_DIR` for the reference data: `IMGW_REFERENCE_DIR`; `client.py:101` keeps passing `root`,
  which is optional now (a default store exists), so `store_dir` need not stay required. Retman sets no
  `IMGW_STORE_ROOT`.
- **Archiwista:** no IMGW adapter yet (only `adapter/kartograf`). When `adapter/imgw` is written: read the
  marker fields `tool`, `created_at`, `producer_version` beside `created_by`; let `probe` follow DEV-19.12
  and DEV-19.13 (a layout without a marker is `store_unavailable`, `no_marker`); statuses are `new`,
  `unchanged`, `relabeled` (a series is `unchanged`, not `reused`). `docs/IMGWTOOLS_REQUIREMENTS.md`
  (IMGW-5 and IMGW-7: lines 715-717, 747, 826-865, 1320-1363, 1528-1551; the marker: 26, 386-448) and
  `docs/SPEC.md` §12.7 still quote the old marker and `created`/`reused`. `imgwtools.testing` and the
  packaged `contract_schemas.json` carry the new marker.
- **Hydrolog:** no package dependency (the registry says `file`, `imgw-series-csv`), and the CSV of
  `series export` is unchanged. Its documents already name `imgw series export … --output FILE`
  (`docs/INTEGRATION.md:391`, `docs/USAGE.md:665-678`, `AGENTS.md:139`, `src/hydrolog/agent_guide.py:217`,
  `README.md:21,256`): that name is real now, so item 3 of its PROGRESS can be closed. Add `--force` to
  the example where the file may exist and read `files[].path` of the `--json` result.
- **Hydraulik, Hydrograf:** only `fetch_pmaxtp(latitude, longitude, method=…)` (Hydraulik
  `src/hydraulik/data.py:347` in the proof-of-concept worktree, pin `v2.1.1`; Hydrograf
  `backend/scripts/preprocess_precipitation.py:169` and `analyze_watershed.py:348`, pin `v2.1.0`),
  unchanged and compatible with the 3.0.0 signature: change the pin to the 3.0.0 tag when it exists.
  Neither reads the store or uses the names above.

## [2.1.1] — 2026-07-06

- Hydro archive parsers: automatic detection of the separator, the encoding (UTF-8 with BOM) and
  quoted rows.
- Meteo URLs follow the actual layout of the IMGW server.
- Compatibility with pyright; documentation audit.

Older releases: `docs/HISTORY.md` (section "Released versions").
