# IMGWTools — Usage Guide

A detailed guide to the IMGWTools interfaces (Python library, CLI, REST, Web GUI, MCP server), configuration, the versioned store and the 3.0.0 changes, moved without content changes from [README.md](../README.md) (Nogat standard 1.0, DOC-2.2). For developers: [CODEBASE.md](CODEBASE.md) (project structure) and [TESTING.md](TESTING.md) (tests).

## Contents

- [Using as a Python library](#using-as-a-python-library)
- [Quick start (CLI)](#quick-start-cli)
- [REST API](#rest-api)
- [Web GUI](#web-gui)
- [AI agents: language, command effects and the MCP server](#ai-agents-language-command-effects-and-the-mcp-server)
- [Source data structure](#source-data-structure)
- [Docker](#docker)
- [Configuration](#configuration)
- [Versioned store (optional)](#versioned-store-optional)
- [Changes in version 3.0.0](#changes-in-version-300)

## Using as a Python library

IMGWTools can be used as a library in other Python projects (e.g. HydroLOG). Functions take the first object positionally and every further argument by name; a station code is always the string `station_code` (IMGW-PIB: 9 digits, ČHMÚ: a WIGOS identifier, e.g. `0-203-1-001000`).

### PMAXTP data (probable maximum precipitation)

```python
from imgwtools import fetch_pmaxtp

# Fetch data for Warsaw (method: "POT" — the default — or "AMP")
result = fetch_pmaxtp(52.23, 21.01, method="POT")

# 15-minute precipitation with 50% probability
precip = result.data.get_precipitation(15, 50)
print(f"Precipitation 15 min, p=50%: {precip} mm")  # precipitation [mm] for t=15 min, p=50%
rare = result.data.get_precipitation(15, 0.01)  # fractional probability: a number, not a string

# Durations [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440, 2160, 2880, 4320
# Probabilities [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 40,
# 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5, 99.9 (50 and 50.0 are the same key). A number outside the list
# (e.g. 0.7) is an IMGWValidationError with the allowed values in details["allowed"]; the same applies
# to get_confidence_bound and get_estimation_error.
```

### Current data

```python
from imgwtools import fetch_hydro_current, fetch_meteo_current, fetch_synop, fetch_warnings

# All hydrological stations or one station (station = 9-digit code)
stations = fetch_hydro_current()
print(f"Number of stations: {len(stations)}")
data = fetch_hydro_current(station="150160180")
print(f"{data[0].station_name}: {data[0].water_level_cm} cm")

# Meteorological and synoptic stations
meteo = fetch_meteo_current()
warszawa = fetch_synop(station_name="Warszawa")
print(f"Temperature: {warszawa[0].temperature_c}°C")

# Warnings: kind="hydro" | "meteo"; omitted = both families
for warning in fetch_warnings(kind="hydro"):
    print(warning.kind, warning.event, warning.level, warning.valid_to)
```

### Stations

```python
from imgwtools import fetch_hydro_states, find_stations

# Search the station lists (case- and diacritics-insensitive);
# provider: "IMGW-PIB" | "CHMI", omitted = both providers
for station in find_stations(kind="hydro", query="wisla", provider="IMGW-PIB")[:5]:
    print(station.station_code, station.name, station.river)

# Water states of hydro stations with coordinates (hydro-back.imgw.pl)
states = fetch_hydro_states()
alarmed = [s for s in states if s.water_state == "alarm"]
for s in alarmed:
    print(f"{s.name}: {s.latitude}, {s.longitude}")
```

### Downloading archival data

```python
from imgwtools import archive_files, datasets, download_archives, download_hydro_data, parse_zip_file

# Dataset registry: key (pl.imgw.hydro_daily), slug (hydro_daily) or alias (hydro/dobowe)
for dataset in datasets(kind="hydro"):
    print(dataset.key, dataset.legacy_alias, dataset.first_year)

# File URLs without downloading; years: 2023 | "2020-2023" | "2020,2022" | [2020, "2022-2023"]
for file in archive_files("hydro/dobowe", years=2022, months=[1, 2]):
    print(file.server_path, file.url)

# Download plain files into a directory (output_dir) using the IMGW server path layout, without metadata;
# an existing file requires force=True, and root=... writes to the store instead of the directory
report = download_archives("hydro/miesieczne", years=2023, output_dir="dane")
for item in report.items:
    print(item.slot, item.status, item.path)

# One archive as bytes (DownloadResult) and the hydro parser
result = download_hydro_data("miesieczne", 2023)
print(result.url, result.etag, result.last_modified, result.content_length)
for station, record in parse_zip_file(result.data, "miesieczne"):
    print(station.station_code, record.hydro_year, record.hydro_month, record.flow_m3s)
    break
```

### Versioned store (requires `imgwtools[store]` for Parquet)

```python
from imgwtools import (
    build_catalog,
    check_store,
    current_version,
    export_archive,
    export_series,
    init_store,
    read_series,
    read_station_list,
    select_series,
    summarize_series,
    sync_store,
)

store = init_store("/dane/imgw")  # explicit root; without it, writing commands use <data_dir>/imgw

# 1. Check freshness without downloading archives (listing + HEAD); the plan is saved outside the store
plan = check_store(store, datasets=["pl.imgw.hydro_monthly"], years="2022-2023", plan="plan.json")

# 2. Download new/missing files according to the plan and build Parquet series (series=True)
report = sync_store(store, plan="plan.json")

# 3. Coverage and reading the current series version (offline; dataset = key, slug or alias)
for coverage in summarize_series(root=store, dataset="hydro/miesieczne", stations=["152210170"]):
    print(coverage.variable, coverage.first, coverage.last, coverage.gaps)
for record in read_series(root=store, dataset="hydro/miesieczne", station="152210170",
                          variables=["Q_mean"]):
    q = record.measurements["Q_mean"]
    print(record.date, q.value, q.flag)  # flag: value|missing|no_phenomenon|accumulated

# 4. Select a series version for a set of stations (read-only)
selection = select_series(store, dataset="pl.imgw.hydro_monthly", stations=["152210170"], years=2023)

# 5. CSV export with units and IMGW-PIB attribution (without output: a line iterator; with output: one file and an OutputReport, an existing file requires force=True)
export_series(root=store, dataset="pl.imgw.hydro_monthly", station="152210170",
              variables=["Q_mean"], output="q.csv")

# 6. Records of one stored archive version (slot = archive:<key>:<file>, SHA-256 verified)
archive = current_version(store, slot="archive:pl.imgw.hydro_monthly:2023/mies_2023.zip")
for line in export_archive(archive.version, format="jsonl"):
    print(line, end="")
    break

# 7. The stations.geojson catalog and stored station lists (a single StationListEntry type)
build_catalog(store)
for station in read_station_list(store, kind="meteo")[:3]:
    print(station.station_code, station.name, station.short_code)
```

For offline tests use `imgwtools.testing.build_fixture_store(root)` — it builds a small store from recorded responses, without internet access (fictitious stations, e.g. `149190310`); the `variant="complete_pl_cz"` variant adds ČHMÚ data (stations `0-203-1-900001`, `0-203-1-900002`, `0-203-0-90001`, `0-203-0-90000000002`, series, catalog and an observation).

### ČHMÚ data (Czechia)

ČHMÚ datasets (`cz.chmi.*`) use the same registry, store, command catalog and contracts as IMGW-PIB. ČHMÚ archives are published per station, so every operation on them requires a list of stations (`stations`, WIGOS identifiers).

```python
from imgwtools import archive_files, build_catalog, check_store, datasets, find_stations, providers, sync_store

# Providers: IMGW-PIB (pl.imgw.*, 9-digit codes) and CHMI ("ČHMÚ", cz.chmi.*, WIGOS identifiers)
for provider in providers():
    print(provider.id, provider.short_name, provider.country, provider.license.id)
print([d.key for d in datasets(provider="CHMI")])  # hydro_daily, meteo_daily, hydro_stations, meteo_stations

# A live ČHMÚ station ("now" metadata; query without Czech characters)
station = find_stations(kind="hydro", query="spindleruv", provider="CHMI")[0]
print(station.station_code, station.name, station.river)  # 0-203-1-001000 Špindlerův Mlýn Labe

# Station files offline: hydro — one JSON per station and year, meteo — 4 CSV files per station (no years)
for file in archive_files("cz.chmi.hydro_daily", stations=[station.station_code], years="2024-2025"):
    print(file.year, file.url)  # …/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2024.json
for file in archive_files("cz.chmi.meteo_daily", stations=["0-203-0-11799"]):
    print(file.param, file.server_path)  # SRA, T, TMA, TMI

# Store (store from the example above): one GET of the server directory listing instead of a HEAD per file
plan = check_store(store, datasets=["cz.chmi.hydro_daily"], stations=[station.station_code],
                   years="2024-2026")  # years optional for hydro: omitted = published years
for item in plan.items:
    print(item.archive.year, item.status, item.remote_listed_at, item.error)  # 2026 unverifiable … not published
print(plan.requests)  # {'made': 1, 'planned': 4}: HEAD+GET for the two missing files
report = sync_store(store, plan=plan)  # HEAD before GET; change since the plan → stale_plan; series chmi_hydro_daily
build_catalog(store, provider="CHMI")  # stations/versions/chmi_stations/…, catalog: catalog:cz.chmi.stations
```

Offline reading — here on the PL + CZ test store:

```python
from imgwtools import export_series, read_catalog, read_series, summarize_series
from imgwtools.testing import build_fixture_store

demo = build_fixture_store("/tmp/imgw-demo", variant="complete_pl_cz")  # fictitious stations, no internet

# ČHMÚ meteo: besides the value and flag, also ČHMÚ QUALITY (0–5) and FLAG verbatim
for record in read_series(root=demo, dataset="cz.chmi.meteo_daily", station="0-203-0-90001",
                          variables=["P"]):
    p = record.measurements["P"]
    print(record.date, p.value, p.flag, p.quality, p.source_flag)  # 2023-10-22 0.0 value 0 T (trace of precipitation)

# Coverage per station: a year without a published file (2005) is unknown, not a gap
for coverage in summarize_series(root=demo, dataset="cz.chmi.hydro_daily", stations=["0-203-1-900002"]):
    print(coverage.variable, coverage.first, coverage.last, coverage.gaps)  # Q 2004-01-01 2006-12-31 ()

# CSV: ČHMÚ quality and flag columns, ČHMÚ attribution (CC BY 4.0) in the first data row
lines = list(export_series(root=demo, dataset="cz.chmi.meteo_daily", station="0-203-0-90001",
                           variables=["P"]))
print(lines[0], end="")  # date,year,P [mm],P_flag,P_quality,P_source_flag,attribution_source,attribution_processed

# ČHMÚ station catalog: SPA thresholds (drought, spa1–spa3, q50) for water level and discharge
for feature in read_catalog(root=demo, provider="CHMI"):
    print(feature.properties["station_code"], feature.properties.get("thresholds"))
```

ČHMÚ rules and behavior:

- **Options:** `stations` is required for `cz.chmi.*` and not allowed for `pl.imgw.*`; `years` is required for `cz.chmi.hydro_daily` in `archive_files`/`datasets files|download`, optional in `check_store`/`sync_store` (omitted = years published in the station listing) and not allowed for `cz.chmi.meteo_daily` (the files cover the whole station history); `months` and `params` are for IMGW-PIB only. One `check_store`/`sync_store` call covers either IMGW-PIB national archives or ČHMÚ station files, not both at once.
- **Freshness:** `check_store` compares the time (to the minute) and size from the server listing with the version signal in the store (`current`, `newer`, `missing`); a year with no file at the source is `unverifiable` with `error="not published"` (not an error; the text is a catalog message, in Polish "nieopublikowany"), and `download_archives` gives it a `not_published` item. `now`/`recent` data, hourly data, ČHMÚ warnings and PMAXTP outside Poland are not supported; `current …` and `pmaxtp …` apply to IMGW-PIB only.
- **Versions:** ČHMÚ regenerates files in bulk. The same bytes under a new `Last-Modified` give `relabeled` (a copy, as for IMGW-PIB); different bytes with the same content (hydro JSON and station lists without the `zaznamID`/`datumVytvoreni` envelope, form `chmi-json/1`, sidecar field `content_sha256`) give `unchanged` without a new version, with the `content_unchanged` notice and an observation of the new signal in `observations/`, so the next check gives `current` without downloading.
- **Series:** `series.json` has the periods known per station (`stations[<code>].periods`); the meteo series has `<V>_quality` and `<V>_source_flag` columns, and values are not corrected based on quality. `series select` accepts only years within the series periods (a range across an unpublished year → `validation_error`).
- **Station catalog:** a separate version of the provider catalog (`build_catalog(store, provider="CHMI")`, `imgw store catalog --provider CHMI`), location from the `now` and historical metadata with a check against the Czech border outline; coordinates carry the published value (JSON does not keep trailing zeros, e.g. `50.6493690` → `50.649369`).
- **License:** CC BY 4.0; sidecars, series, the catalog and exports carry the ČHMÚ attribution (processed forms — marked as changed), and the `license_terms` notice states the license terms.

### Command catalog

Every CLI command and REST route can be called from Python with the same options; the result is a `CommandResult` (envelope `imgw-result/1`), and list commands return a `Page` (`items`, `total`, `limit`, `offset`).

```python
from imgwtools import command_schema, run_command

result = run_command("stations find", options={"kind": "hydro", "query": "wisla", "limit": 5})
print(result.status, result.result.total, [s.name for s in result.result.items])
print(result.to_json())  # dict of the JSON envelope, the same as CLI stdout and the REST body

schema = command_schema("store sync")  # JSON Schema of the options + x-imgw (function, CLI, REST, rules)
print(schema["x-imgw"]["rest"]["path"])
print(schema["x-imgw"]["writes"], schema["x-imgw"]["network"], schema["x-imgw"]["operation_id"])  # add True imgw_store_sync
print(command_schema("store sync", lang="en")["description"])  # descriptions in English, structure unchanged
```

The command that downloads a stored version again is rebuilt from its sidecar by `command_for_version` (offline, no writes; ADR-008). The result has the shape of `parse_command`, so `format_command`, `check_command` and `run_command` accept it; `root` is the absolute store root (default `store_root()`).

```python
from imgwtools import check_command, command_for_version, format_command

call = command_for_version("archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/2026-10-19_b6a19f65/codz_2024.zip",
                           root="/dane/imgw")
print(format_command(call.command, options=call.options))
# imgw store sync --root /dane/imgw --datasets pl.imgw.hydro_daily --years 2024
plan = check_command(call.command, options=call.options)  # plan for this file (listing + HEAD)
```

| Version | Command |
|---|---|
| IMGW-PIB archive | `store sync --datasets <key> --years <year>` (`--months <month>` for a monthly file) |
| ČHMÚ hydro / meteo archive | `store sync --datasets <key> --stations <code>` (hydro also `--years <year>`) |
| station list, station catalog | `store catalog --provider <provider>` |
| series version (or its station file) | `series build --dataset <key>` |
| PMAXTP cell | `pmaxtp sync --latitude --longitude --method --ind-x --ind-y` |

The command is the narrowest one that selects the version's file; it may cover neighboring files (half-year `H`, `Q` and `T`, all elements of a ČHMÚ meteo station). A version whose metadata do not rebuild the call is an `unsupported` error with `details.reason="command_not_rebuildable"` (a catalog built from a user coordinates file, a sidecar without a required field, a file that `store sync` does not select); a missing version is `not_found`, a bad sidecar is `data_error`.

### Async version

```python
import asyncio
from imgwtools import fetch_pmaxtp_async, fetch_hydro_current_async

async def main():
    # Concurrent requests
    pmaxtp, hydro = await asyncio.gather(
        fetch_pmaxtp_async(52.23, 21.01),
        fetch_hydro_current_async()
    )
    print(f"PMAXTP: {pmaxtp.data.get_precipitation(15, 50)} mm")
    print(f"Hydro stations: {len(hydro)}")

asyncio.run(main())
```

### Error handling

Every `IMGWError` has a `code` from the closed `ERROR_CODES` registry and `details` (e.g. the name of the invalid option); the same code determines the CLI exit code and the HTTP status.

```python
from imgwtools import ERROR_CODES, IMGWConnectionError, IMGWError, IMGWValidationError, fetch_pmaxtp

try:
    result = fetch_pmaxtp(40.0, 21.01)
except IMGWValidationError as e:
    print(f"Validation error: {e}", e.code, e.details)  # validation_error {'option': 'latitude', ...}
except IMGWConnectionError as e:
    print(f"Connection error: {e}")  # code source_unavailable: timeout, network error, HTTP outside 2xx
except IMGWError as e:
    spec = ERROR_CODES[e.code]
    print(spec.title, spec.exit_code, spec.http_status)
```

| Code | Meaning | CLI | HTTP |
|---|---|---|---|
| `validation_error` | Invalid input | 2 | 400 |
| `not_found` | Not found | 3 | 404 |
| `conflict` | State conflict | 4 | 409 |
| `source_unavailable` | Data source unavailable (`detail` names the provider and URL) | 5 | 502 |
| `missing_dependency` | Missing optional dependency | 6 | 503 |
| `data_error` | Invalid data | 7 | 500 |
| `store_unavailable` | Store unavailable | 8 | 503 |
| `io_error` | File system error | 9 | 500 |
| `cancelled` | Operation cancelled | 130 | — |
| `forbidden` | No write permission | 12 | 403 |
| `unsupported` | Unsupported (e.g. `command_not_rebuildable` from `command_for_version`) | 15 | 422 |
| `method_not_allowed` | HTTP method not allowed | — | 405 |
| `internal_error` | Internal error | 1 | 500 |

---

## Quick start (CLI)

```bash
# Start the API server
imgw server --reload

# Dataset registry and file URLs (without downloading)
imgw datasets list -k hydro
imgw datasets files -d hydro/dobowe -y 2023 -m 1

# Download archives into a directory (IMGW server path layout)
imgw datasets download -d hydro/miesieczne -y 2023 -o dane
imgw datasets download -d meteo/miesieczne/synop -y 2020-2023 -o dane

# Stations, current data and PMAXTP
imgw stations find -k hydro -q wisla --limit 5
imgw current hydro -s 150160180
imgw current warnings -k meteo
imgw pmaxtp fetch --lat 52.23 --lon 21.01 --method AMP

# Versioned store (root: --root, IMGW_ROOT, [imgw] root or <data_dir>/imgw)
export IMGW_ROOT=/dane/imgw
imgw store init
imgw store check -d pl.imgw.hydro_monthly -y 2022-2023 --plan plan.json
imgw store sync --plan plan.json
imgw store catalog                                    # stations.geojson
imgw store scan -k series
imgw store export --version archives/versions/<path>/<version> --format jsonl | head
imgw series summary -d hydro/miesieczne -s 152210170
imgw series export -d hydro/miesieczne -s 152210170 --variables Q_mean --output q.csv
imgw pmaxtp sync --lat 52.23 --lon 21.01

# ČHMÚ data (WIGOS station codes; -s/--stations required for cz.chmi.*)
imgw datasets providers
imgw datasets list --provider CHMI
imgw stations find -k hydro -q spindleruv --provider CHMI
imgw datasets files -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2025
imgw datasets download -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2025-2026 -o dane   # 2026: not_published
imgw store check -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2026 --plan plan-cz.json
imgw store sync --plan plan-cz.json                   # + series chmi_hydro_daily
imgw store catalog --provider CHMI                    # stations/versions/chmi_stations/…
imgw series read -d cz.chmi.hydro_daily -s 0-203-1-001000 --variables Q --limit 5
imgw store scan --provider CHMI -k observation

# AI agents: guide and descriptions (English by default), MCP server (imgwtools[mcp] extra)
imgw commands guide --format llms
imgw commands schema --command "store sync"
imgw commands schema --command "store sync" --lang pl   # descriptions in Polish
IMGW_LANG=en imgw store sync --help                      # CLI help in English
imgw mcp                                              # stdio — started by the MCP client

# Plan without writing or downloading; description of the command options
imgw store sync -d pl.imgw.hydro_monthly -y 2024 --check
imgw store sync --schema
```

Catalog commands (full list: `imgw commands list`):

| Command | Python function | `--check` | REST |
|---|---|---|---|
| `imgw datasets list` | `datasets` | — | `GET /api/v1/datasets/list` |
| `imgw datasets files` | `archive_files` | — | `GET /api/v1/datasets/files` |
| `imgw datasets download` | `download_archives` | `check_command` | — (local) |
| `imgw datasets providers` | `providers` | — | `GET /api/v1/datasets/providers` |
| `imgw stations find` | `find_stations` | `check_command` | `GET /api/v1/stations/find` |
| `imgw current hydro` | `fetch_hydro_current` | `check_command` | `GET /api/v1/current/hydro` |
| `imgw current meteo` | `fetch_meteo_current` | `check_command` | `GET /api/v1/current/meteo` |
| `imgw current synop` | `fetch_synop` | `check_command` | `GET /api/v1/current/synop` |
| `imgw current warnings` | `fetch_warnings` | `check_command` | `GET /api/v1/current/warnings` |
| `imgw current hydro-states` | `fetch_hydro_states` | `check_command` | `GET /api/v1/current/hydro-states` |
| `imgw pmaxtp fetch` | `fetch_pmaxtp` | `check_command` | `GET /api/v1/pmaxtp/fetch` |
| `imgw pmaxtp url` | `build_pmaxtp_url` | — | `GET /api/v1/pmaxtp/url` |
| `imgw pmaxtp check` | `check_pmaxtp` | self | `GET /api/v1/pmaxtp/check` |
| `imgw pmaxtp sync` | `sync_pmaxtp` | `check_pmaxtp` | `POST /api/v1/pmaxtp/sync` |
| `imgw pmaxtp read` | `read_pmaxtp` | — | `GET /api/v1/pmaxtp/read` |
| `imgw store init` | `init_store` | `check_command` | — (local) |
| `imgw store info` | `store_info` | — | `GET /api/v1/store/info` |
| `imgw store scan` | `iter_store` | — | `GET /api/v1/store/scan` |
| `imgw store check` | `check_store` | self | `GET /api/v1/store/check` |
| `imgw store sync` | `sync_store` | `check_store` | `POST /api/v1/store/sync` |
| `imgw store catalog` | `build_catalog` | `check_catalog` | `POST /api/v1/store/catalog` |
| `imgw store export` | `export_archive` | `check_command` | `GET /api/v1/store/export` |
| `imgw series build` | `build_series` | `check_series` | `POST /api/v1/series/build` |
| `imgw series select` | `select_series` | — | `GET /api/v1/series/select` |
| `imgw series read` | `read_series` | — | `GET /api/v1/series/read` |
| `imgw series summary` | `summarize_series` | — | `GET /api/v1/series/summary` |
| `imgw series export` | `export_series` | `check_command` | `GET /api/v1/series/export` |
| `imgw commands list` | `list_commands` | — | `GET /api/v1/commands/list` |
| `imgw commands schema` | `command_schema` | — | `GET /api/v1/commands/schema` |
| `imgw commands guide` | `agent_guide` | `check_command` | `GET /api/v1/commands/guide` |

Outside the catalog: `imgw version`, `imgw server`, `imgw mcp` and `imgw admin keys|create|revoke|delete|stats`.

**Options.** Flag = `--` + option name with `-` instead of `_`; short forms: `-d` dataset(s), `-y` years, `-m` months, `-s` station(s), `-k` kind, `-q` query, `-o` plain-file directory (`--output-dir`), `-r` root, `-f` format; `--lat`/`--lon` are aliases of `--latitude`/`--longitude`. Write target (DEV-19.1): `--output-dir` (`-o`) writes plain files into a directory, `--root` (`-r`) writes to the versioned store (the options are mutually exclusive; with neither of them — the store in the default root), `--output` (no short form) writes one export file, and `--force` replaces existing plain files. Lists: comma-separated values or a repeated flag. List commands have `--limit` and `--offset`. `--provider` (`IMGW-PIB` or `CHMI`) narrows `datasets list`, `stations find` and `store scan` to one provider (omitted = both) and selects the catalog in `store catalog` (default `IMGW-PIB`). `--check` (only in commands with a `--check` column) prints the plan without writing and without downloading data, `--schema` — the description of the command options without running it. Dataset-dependent rules (e.g. `--stations` for `cz.chmi.*`) are in `x-imgw.rules` of the schema. `IMGW_LANG=en` switches the CLI help and the default `--lang` to English (a value outside `pl|en` → `validation_error`, code 2).

**Output.** stdout is one JSON line — the `imgw-result/1` envelope (`schema`, `command`, `check`, `status`, `result`, `notices`); store paths are relative to the root. `store export`, `series export` and `commands guide` without `--output` print a CSV/JSONL/Markdown stream; with `--output` they write one file (an existing one requires `--force`, a file in the store is a `conflict`), and the envelope `result` is `{output, files[]}` (`files[]` = `{path, size_bytes, sha256, status}`). Progress and notices (each distinct one once, e.g. `license_terms`) go to stderr, and an error — as JSON `{"code", "detail", "details"}` on the last stderr line (stdout empty). Exit codes:

| Code | Meaning |
|---|---|
| `0` | `status` `ok` |
| `10` / `11` | `status` `partial` / `failed` (e.g. a `failed` or `stale_plan` item in `store sync`) — the full envelope is printed |
| `2`–`9`, `1` | error according to the code table (`validation_error` 2 … `io_error` 9, `internal_error` 1) |
| `130` | cancelled with Ctrl+C |

A PMAXTP point inside the coordinate frame of Poland but outside the IMGW grid (e.g. Kaliningrad, Lviv, the Baltic Sea) gives `validation_error` (CLI 2, REST 400).

**Data output.** A writing command has two ways of writing (DEV-19). `-o`/`--output-dir` writes only the files, without metadata, under the names they have in the store (`datasets download`: the provider server path layout; `pmaxtp sync`: two files named after the cell indices); the directory is created if missing. A directory that is a store (of any Nogat tool) or lies inside a store is rejected before the first request with a `conflict` error (`details.reason` = `output_in_store`, `details.paths` is that directory). Then, before the first byte, the full list of targets is built: a duplicate name, an existing file without `--force` and a target that would enter a subdirectory containing a store end with a `conflict` error (`details.reason` = `duplicate_output_name`, `output_exists`, `output_in_store`; `details.paths` lists all paths). `--check` shows a plan with `write`, `replace` (with `--force`) and `conflict` actions; in store mode a root with foreign files (`not_empty`) or a nested store (`nested_store`) is a single `conflict` action of a plan that succeeds. Files first go to `<directory>/.imgw-incoming/<host>_<pid>_<token>/` and only after checking are moved into place with `os.replace`; this directory is removed after success, an error, SIGINT and SIGTERM, and leftovers older than 24 h are removed by the next run. This works on FAT/exFAT and SMB because it does not use links. `--force` replaces only the given files and deletes nothing; in the store `--force` downloads again and gives a new version or `unchanged`. Commands whose input or output is the store (`store init`, `series build`, `store catalog`) have no `--output-dir` (the "store only" rule in their description), and `--plan` with `--output-dir` ends with `validation_error` (`store_only_option`) with a `--root` hint. Example:

```bash
imgw datasets download -d hydro/miesieczne -y 2023 -o dane --check   # plan: write/replace/conflict
imgw datasets download -d hydro/miesieczne -y 2023 -o dane           # files in dane/…, files[] with sha256
imgw datasets download -d hydro/miesieczne -y 2023 -o dane --force   # replaces existing files
imgw datasets download -d hydro/miesieczne -y 2023                   # no target: store in <data_dir>/imgw
```

## REST API

After starting the server (`imgw server`):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- `GET /api/v1` — version and list of catalog routes, `GET /health` — server status, `GET /llms.txt` — guide for agents (llms.txt) in the language from `Accept-Language` (English by default)
- `/mcp` — MCP server (Streamable HTTP) when `IMGW_MCP_ENABLED=true` (section "AI agents")

Routes are generated from the catalog: `/api/v1/<group>/<command>` (table above; local commands — `datasets download`, `store init` — have no routes). GET takes options in the query (comma-separated lists or a repeated parameter), POST — in a JSON body; `?check=true` on POST returns the plan without writing. The response is the same `imgw-result/1` envelope as in the CLI; list commands have `limit` (default and maximum `IMGW_API_MAX_LIMIT`, 1000) and `offset`. Errors: `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `details`). Language: notices, item and plan texts and the problem+json `title` and `detail` are in English, and in Polish with `Accept-Language: pl` (`q` weights per RFC 9110); commands with a `lang` option (`commands list`, `commands schema`, `commands guide`) take it from the query, and without it from the header. Every command response has `Content-Language`, and `Vary: Accept-Language` when the header decided. The OpenAPI document (`/openapi.json`) is in English.

```bash
# Current data and archive URLs
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
curl "http://localhost:8000/api/v1/datasets/files?dataset=cz.chmi.hydro_daily&stations=0-203-1-001000&years=2024"

# Command catalog and guide (in English; in Polish with Accept-Language: pl)
curl "http://localhost:8000/api/v1/commands/schema?command=store%20sync"
curl http://localhost:8000/llms.txt
curl -H "Accept-Language: pl" http://localhost:8000/llms.txt

# Store (requires IMGW_ROOT on the server; otherwise 503 not_configured)
curl http://localhost:8000/api/v1/store/info
curl "http://localhost:8000/api/v1/store/scan?kind=series"
curl "http://localhost:8000/api/v1/series/summary?dataset=pl.imgw.hydro_monthly&stations=152210170"

# Writes (IMGW_STORE_WRITES_ENABLED=true, IMGW_STORE_WRITE_TOKEN and the X-API-Key header)
curl -X POST "http://localhost:8000/api/v1/store/sync?check=true" \
    -H "X-API-Key: $IMGW_STORE_WRITE_TOKEN" -H "Content-Type: application/json" \
    -d '{"datasets": ["pl.imgw.hydro_monthly"], "years": "2024"}'
```

Store routes work only on the server-side, absolute `IMGW_ROOT` (the client does not pass a root). Writing operations additionally require `IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN` and an `X-API-Key` header with that token — they are disabled by default (403 `forbidden`). User coordinate CSV files (`user_locations`) only from the `IMGW_USER_LOCATIONS_DIR` directory.

## Web GUI

After starting the server, available at http://localhost:8000:
- `/` - Dashboard
- `/download` - Selecting data to download; `/download/archives` - links to registry dataset archives, `/download/pmaxtp` - PMAXTP tables (CSV/XLSX/JSON export)
- `/stations` - Station search (IMGW-PIB lists, pagination)
- `/map` - Map of hydro stations colored by water state (`GET /api/v1/current/hydro-states`)

Each station links to the official IMGW page: `https://hydro.imgw.pl/#/station/{type}/{id}`

The Web GUI supports IMGW-PIB datasets only (a form without a station field cannot handle per-station ČHMÚ files); ČHMÚ data are available in Python, the CLI, REST and MCP.

## AI agents: language, command effects and the MCP server

**Language.** Machine output is in English (AGI-9.2): the envelope, error `detail`, notices, plan lines, `commands list|schema|guide` descriptions (`command_schema()`, `list_commands()`, `agent_guide()`), `AGENTS.md`, `llms.txt`, the OpenAPI document, REST responses without an `Accept-Language` header and the MCP server. Polish catalog texts (command descriptions, option help, rules, groups, error and dataset titles) are available on explicit request: `lang="pl"`, `--lang pl`, `Accept-Language: pl`. `IMGW_LANG` (default `pl`) applies only to human-facing CLI text: help, progress lines and notices on stderr; the last error line and the envelope are always in English, and `IMGW_LANG` is not the default value of `--lang`. An agent decides by `code`, `status` and JSON fields; the language does not change the contract.

**Command effects.** `x-imgw.writes` (`none`, `add` — only new files and versions, `replace` — may replace a user file), `x-imgw.network` and the options' `x-imgw-writes` (e.g. `output`, `force`, `plan` in `store check`) tell what a command will do before it runs; every writing command has a plan (`--check`, `?check=true`, `check: true`).

### MCP server

`imgw mcp` (the `imgwtools[mcp]` extra: CLI + the official SDK `mcp>=2.3,<3`) is an MCP server on standard input and output. Every catalog command is a tool named `x-imgw.operation_id` (`imgw_` + command name: `imgw_store_sync`, `imgw_current_hydro_states`, …; also the REST `operationId`) with an input schema from `command_schema` and the annotations `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`; the arguments are the command options, and the only validator is `validate_command`. The `imgw_commands_list` tool returns the list of commands, `imgw_commands_schema` — the options of one command. Client configuration (e.g. `mcpServers` in the settings file):

```json
{
  "mcpServers": {
    "imgwtools": {
      "command": "imgw",
      "args": ["mcp"],
      "env": {"IMGW_ROOT": "/dane/imgw"}
    }
  }
}
```

- Without a system-wide installation: `"command": "uvx", "args": ["--from", "imgwtools[mcp]", "imgw", "mcp"]`.
- Writes: `"args": ["mcp", "--allow-writes", "--allow-dir", "/dane/imgw"]` (or `IMGW_MCP_ALLOW_WRITES=true`; `--allow-dir` can be repeated). Without `--allow-writes` the server does not write: writing commands have the `check` argument fixed to `true` and return an `imgw-plan/1` plan, and writing options (`output_dir`, `output`, `force`, `plan`) are unavailable (an attempt → `forbidden`, `details.reason="writes_disabled"`). With the flag, `check` defaults to `true` and writing requires `check: false` — the user decides about writes in the configuration, not the model. Writing without `--allow-dir` is `forbidden` (`no_allowed_dir`), and a target (`root`, `output_dir`, `output` or the default root) outside these directories is `forbidden` (`outside_allowed_dirs`).
- Language: the MCP server always speaks English (tool descriptions, instructions, error titles and `detail`; AGI-9.2), regardless of `IMGW_LANG`. There is no `--lang` option; an agent gets Polish text only on explicit request (the `lang: "pl"` argument of the `imgw_commands_list`, `imgw_commands_schema`, `imgw_commands_guide` tools).
- `root` as in the CLI: a tool argument or the server's `IMGW_ROOT`; without them the default root `<data_dir>/imgw` (must lie within `--allow-dir`); relative paths are resolved from the server's working directory (given in the server instructions).

Tool result: `structuredContent` = the `imgw-result/1` envelope (the same bytes as CLI stdout, also as text), `isError=false` also for `partial` and `failed`. Error: `isError=true` and `{"code", "title", "detail", "details"}` (`code`, `detail` and `details` as in the CLI error line, `title` from the registry, all in English). List commands without `limit` return a page of 50 items (at most `IMGW_API_MAX_LIMIT`); streams (`store export`, `series export`, `commands guide` without `output`) — text up to 256 KiB with the envelope `result={format, bytes, lines}`, larger → `validation_error` (narrow the selection, read page by page with `series read` or write a file with the `output` option; writing requires `--allow-writes` and an `--allow-dir` directory). Progress is sent as `notifications/progress`; cancelling the request stops work between files. The list of 30 tools with descriptions is about 42 KB of schemas (read-only mode).

**MCP over HTTP.** `imgw server` exposes `/mcp` (Streamable HTTP) with `IMGW_MCP_ENABLED=true`: the tools correspond to the 28 REST routes and are called as REST requests in the same process (with `Accept-Language: en`), so the server rules apply (store from `IMGW_ROOT`, `version` relative to the store, `IMGW_API_MAX_LIMIT`, hiding server directories); POST always with `?check=true` — over HTTP only reading and planning. The tools are in English, as in `imgw mcp`; `IMGW_LANG` does not affect them. Allowed `Host` headers are listed in `IMGW_MCP_ALLOWED_HOSTS` (default `127.0.0.1,localhost`); behind `nginx` add the public host name.

```bash
IMGW_MCP_ENABLED=true IMGW_ROOT=/srv/imgw imgw server   # → http://127.0.0.1:8000/mcp
```

## Source data structure

### IMGW-PIB hydrological data (1951-present)
- `dobowe`: monthly files (before 2023) or yearly files (from 2023)
- `miesieczne`: yearly files
- `polroczne_i_roczne`: yearly files with the T, Q, H parameters

> **CSV format:** IMGW archive files are inconsistent between years in three respects:
> - **separator** — most years use a comma with quotes, some (e.g. 2023) a semicolon, and some have an extra header row;
> - **encoding** — the standard is CP1250, but e.g. `codz_2023.zip` is UTF-8 with a BOM;
> - **quotes** — the 2024 daily and monthly files have whole rows wrapped in quotes (with doubled quotes inside).
>
> The parsers (`parse_zip_file`) **detect the separator, encoding and quoting variant automatically, per file**. Verified on real data for the years 2019-2024 (all intervals).

### IMGW-PIB meteorological data (1950-present)
- **up to 2000**: 5-year folders; **from 2001**: yearly folders
- **miesieczne**: one file per folder (`{folder}_m_{k|o|s}.zip`)
- **dobowe/terminowe klimat and opad**: yearly files (up to 2000) or monthly files (from 2001)
- **dobowe/terminowe synop**: per-station files (`{folder}_{code}_s.zip`) — the registry does not generate them (`validation_error`, `details.reason=per_station`; use `meteo/miesieczne/synop`)
- **terminowe opad**: the dataset does not exist on the IMGW server (`details.reason=not_published`)
- The folder grids start differently: klimat from `1951_1955`, opad from `1950_1955`, synop from `1960_1965` (structure verified on the IMGW servers, 2026-07-05)

### ČHMÚ data (opendata.chmi.cz)
- **daily hydro** (`cz.chmi.hydro_daily`): `hydrology/historical/data/daily/H_<WIGOS>_DQ_<year>.json` — one JSON file per station and calendar year (the oldest from 1887); series `HD`, `QD`, `TD` → H [cm], Q [m3/s], T [°C] (suspended sediment `PD` skipped); no measurement = no row
- **daily meteo** (`cz.chmi.meteo_daily`): `meteorology/climate/historical_csv/data/daily/precipitation/dly-<WIGOS>-SRA.csv` and `…/temperature/dly-<WIGOS>-{T,TMA,TMI}.csv` — the whole station history in the element file; P = total from the morning observation (06:00Z) of day D to the morning of D+1, Tmean = (T06 + T13 + 2·T20)/4, Tmax and Tmin — extremes of the period (D−1 20:00, D 20:00] UTC (descriptions in the dataset's `variable_notes`); `QUALITY` (0–5) and `FLAG` (e.g. `T` — trace of precipitation) kept
- **station lists**: `hydrology/historical/metadata/meta1.json` and `meteorology/climate/historical/metadata/meta1.json` (JSON with a `zaznamID`/`datumVytvoreni` envelope that changes with every generation)
- **inventory**: server directory listings (name, time to the minute, size) — one GET of the hydro listing (about 5.3 MB) replaces a HEAD of each of about 39 thousand files; the server keeps only the latest version of a file, and a year enters `historical` only with the annual publication (hydro 2025: 2026-05-21)
- Out of scope: `now`/`recent` data, hourly and 10-minute data, CAP warnings; ČHMÚ does not publish a PMAXTP equivalent

### Station data sources
- **IMGW-PIB hydro station list**: CSV from `danepubliczne.imgw.pl` (CP1250 encoding)
- **IMGW-PIB meteo station list**: CSV from `danepubliczne.imgw.pl` (CP1250 encoding)
- **Coordinates for the map**: API `hydro-back.imgw.pl/map/stations/hydrologic` (900+ stations with water state)
- **ČHMÚ stations**: JSON metadata from `opendata.chmi.cz` — current (`hydrology/now/metadata/meta1.json`, `meta3.json`, the latest `meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json`) and historical station lists; WGS84 coordinates, SPA thresholds of hydro stations

## Docker

```bash
cd docker
docker compose up -d

# With the MCP server at /mcp (read and plan only); behind nginx add the public host name
IMGW_MCP_ENABLED=true IMGW_MCP_ALLOWED_HOSTS=dane.example.pl docker compose up -d
```

The image (`python:3.12-slim`) installs `.[api,mcp]` and runs a single uvicorn process (MCP sessions live in the process). `docker-compose.yml` passes `IMGW_MCP_ENABLED` (default `false`) and `IMGW_MCP_ALLOWED_HOSTS` (default `127.0.0.1,localhost`) from the environment; `nginx.conf` has `location = /mcp` with a request limit and no buffering.

## Configuration

A setting comes from the first of: a command-line option, the `IMGW_<KEY>` variable, the same key in the `.env` file of the working directory, the `NOGAT_<KEY>` variable (only the shared keys `data_dir`, `cache_dir`, `lang`), the `[imgw]` and `[nogat]` sections of the `nogat.toml` file (in this order; `[nogat]` holds only shared keys), the default value. `nogat.toml` lies in the user configuration directory (`platformdirs.user_config_path("nogat")`, e.g. `~/.config/nogat/nogat.toml`) or at the path from `NOGAT_CONFIG`; a missing file is not an error, an unreadable or invalid file ends every `imgw` call with a `validation_error`. Credentials (`IMGW_STORE_WRITE_TOKEN`) come only from the environment, never from the file. The tool writes nothing into the working directory: stores lie under `data_dir` (`<data_dir>/imgw`), the cache under `cache_dir` (`<cache_dir>/imgw`).

```toml
[nogat]   # keys shared by all tools of the ecosystem
data_dir = "/srv/nogat/dane"
lang = "pl"

[imgw]    # any setting from the table below: variable name without IMGW_, in lower case
root = "/srv/nogat/dane/imgw"
api_max_limit = 500
```

| Variable | Key in `nogat.toml` | Default | Meaning |
|---|---|---|---|
| `IMGW_DATA_DIR` (also `NOGAT_DATA_DIR`) | `data_dir` | `nogat` user data directory (`~/.local/share/nogat`) | parent directory of the stores (`<data_dir>/imgw`) and the server state; **before 3.0.0 it meant the reference data** (see `IMGW_REFERENCE_DIR`) |
| `IMGW_CACHE_DIR` (also `NOGAT_CACHE_DIR`) | `cache_dir` | `nogat` cache directory (`~/.cache/nogat`) | cache (`<cache_dir>/imgw`) |
| `IMGW_REFERENCE_DIR` | `reference_dir` | `<cache_dir>/imgw/reference` | IMGW-PIB reference data (`python -m imgwtools.reference_data`) |
| `IMGW_LANG` (also `NOGAT_LANG`) | `lang` | `pl` | `pl` or `en`: CLI help, progress lines and notices on stderr (the last error line, the envelope and command descriptions are always in English; Polish descriptions via `--lang pl`) |
| `IMGW_ROOT` | `root` | `<data_dir>/imgw` | store root for the CLI, the library and `imgw mcp` without `--root` (also `root` in `[imgw]` of `nogat.toml`); the only store of the REST server (without it 503, never the default directory) |
| `IMGW_STORE_WRITES_ENABLED` | `store_writes_enabled` | `false` | writes over REST (POST without `?check=true`) |
| `IMGW_STORE_WRITE_TOKEN` | — (environment only) | none | write token in the `X-API-Key` header |
| `IMGW_USER_LOCATIONS_DIR` | `user_locations_dir` | none | directory of user location files for REST routes |
| `IMGW_API_MAX_LIMIT` | `api_max_limit` | `1000` | default and maximum `limit` of REST and MCP list commands |
| `IMGW_API_KEYS_FILE` | `api_keys_file` | `<data_dir>/imgw/api_keys.json` | `imgw admin` key file |
| `IMGW_RATE_LIMIT` | `rate_limit` | `100` | requests per hour (0 = no limit) |
| `IMGW_ENV` | `env` | `development` | `development` or `production` |
| `IMGW_HOST`, `IMGW_PORT` | `host`, `port` | `0.0.0.0`, `8000` | address and port of `imgw server` |
| `IMGW_LOG_LEVEL` | `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `IMGW_MCP_ENABLED` | `mcp_enabled` | `false` | `/mcp` in `imgw server` (read and plan only) |
| `IMGW_MCP_ALLOWED_HOSTS` | `mcp_allowed_hosts` | `127.0.0.1,localhost` | `Host` names served by `/mcp` |
| `IMGW_MCP_ALLOW_WRITES` | `mcp_allow_writes` | `false` | `imgw mcp` in write mode (`--allow-writes`, `--no-allow-writes`) |

`imgw config show --json` prints one `imgw-config/1` document: every key with its value and source (`default`, `env`, `dotenv`, `file` and the variable or table name), every credential variable as `present` or `missing` (without the value) and the store root with its source and size (hard-linked files counted once); without `--json` the same description as text.

**Store backup.** The store is the only place holding archive versions that IMGW-PIB or ČHMÚ have removed from their server, so they cannot be downloaded again. A backup must preserve hard links (`rsync -aH`; on Windows a tool that preserves links, not Explorer or `robocopy`) or use an export (`imgw store export`, `imgw series export`); a copy without links multiplies the store size.

## Versioned store (optional)

The store is a plain directory explicitly specified by the user (`--root`, `init_store(root)`, on the server `IMGW_ROOT`). Without the option the store lies in `<data_dir>/imgw` (DEV-19.2); there is no database; the store can be read offline from a local disk or a network share. One store holds the data of both providers. Details: `docs/DECISIONS.md` (ADR-001, ADR-003), `docs/superpowers/specs/2026-10-17-versioned-store-design.md` and `2026-10-18-chmi-provider-design.md`.

### Directory layout

```text
<root>/imgw-store.json                                  # imgw-store/1 marker
  archives/versions/<server path>/<stem>/<label>_<sha8>/<file>[.meta.json]
  archives/versions/<server path>/<stem>/observations/<date>_<sha8>.json   # observation register (ČHMÚ)
  stations/versions/<label>_<sha8>/stations.geojson[.meta.json]                 # IMGW-PIB catalog
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson[.meta.json]   # ČHMÚ catalog
  series/versions/<slug>/<label>_<sha8>/series.json[.meta.json] + stations/<code>.parquet
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json[.meta.json]
  .incoming/                                            # staging; never a version
```

Versions are immutable and append-only: no overwriting, no permanent links and no `latest` path. The current version is computed by `current_version(root, slot=...)`; slots: `archive:<key>:<file>` (e.g. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`, `archive:cz.chmi.hydro_daily:H_0-203-1-001000_DQ_2025.json`), `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>`. Every main file has a `*.meta.json` sidecar (`imgw-meta/1`) with SHA-256, size, request, HTTP headers and the provider license; sidecars of ČHMÚ archives with a canonical form also have `content_sha256`. The `observations/` directory (`imgw-observation/1`) records a new source signal when the downloaded bytes have the same content as the current version — it is not a version; `store scan --kind observation` shows it as publication history.

A write moves version files from the `.incoming/` staging area with hard links that never replace an existing file; the main file's sidecar is linked last and only it commits the version (Kartograf's model, hence the hard-link requirement — see "Installation"). A version directory without a sidecar is an interrupted publication (e.g. after a write error, Ctrl+C or a killed process): reads and writes skip it, `store scan` shows it as a `missing_sidecar` problem, and the next write of the same content under the same label completes it. The station catalog label is the build date, and for PMAXTP and an archive without `Last-Modified` — the download date (UTC): an interrupted publication that a retry with the same content and label will not complete (e.g. a catalog rebuilt the next day) must be removed manually — the whole `<label>_<sha8>/` directory without a sidecar — while no write to the store is in progress.

### Datasets

| Key | Alias | Content |
|-------|-------|-----------|
| `pl.imgw.hydro_daily` | `hydro/dobowe` | Daily hydro: H [cm], Q [m3/s], T [°C] |
| `pl.imgw.hydro_monthly` | `hydro/miesieczne` | Monthly hydro: H/Q/T × min/mean/max |
| `pl.imgw.hydro_semiannual` | `hydro/polroczne_i_roczne` | Half-yearly and yearly hydro: H/Q/T × min/mean/max with dates of extremes |
| `pl.imgw.meteo_climate_daily` | `meteo/dobowe/klimat` | Daily climate meteo: Tmax, Tmin, Tmean, Tground, P, snow cover |
| `pl.imgw.meteo_precip_daily` | `meteo/dobowe/opad` | Daily precipitation meteo: P, snow cover and fresh snow |
| `pl.imgw.hydro_stations`, `pl.imgw.meteo_stations` | — | Station lists (CSV) — input of the `stations.geojson` catalog |
| `pl.imgw.pmaxtp` | — | PMAXTP per grid cell (`POT`, `AMP`) |
| `pl.imgw.hydro_phenomena` | — | Daily hydrological phenomena (download only) |
| `pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly` | `meteo/miesieczne/klimat\|opad\|synop` | Monthly meteo (download only) |
| `pl.imgw.meteo_climate_terms` | `meteo/terminowe/klimat` | Climate meteo at observation terms (download only) |
| `cz.chmi.hydro_daily` | — | ČHMÚ daily hydro: H [cm], Q [m3/s], T [°C]; one file per station and year |
| `cz.chmi.meteo_daily` | — | ČHMÚ daily meteo: P [mm], Tmean, Tmax, Tmin [°C] with quality (`QUALITY`) and the ČHMÚ flag; 4 files per station |
| `cz.chmi.hydro_stations`, `cz.chmi.meteo_stations` | — | ČHMÚ station lists (JSON) — input of the ČHMÚ catalog |

"Download only" datasets support `datasets files|download`, but not the store. Current data, warnings and `fetch_pmaxtp` remain live queries, without the store. `datasets(provider="CHMI")` or `imgw datasets list --provider CHMI` lists the datasets of one provider, and `providers()` / `imgw datasets providers` — the providers with licenses and station code patterns.

### Schemas

`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-observation/1` (and the `imgw-pmaxtp/1` extension) have their own version counters, independent of the package version; the command result envelope is `imgw-result/1`. Within `/1` only optional fields are added; an incompatible change means `/2`. An unknown version is reported (`store_info(...).supported is False`), not guessed. The `/1` domains are open to further providers (key `<country>.<provider>.<slug>`, IMGW or WIGOS station code; ADR-003).

### Integrations

- **Archiwista** reads the store only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`, `command_for_version`), the data of both providers with the same adapter (`provider` in entries, catalogs and stations; `kind="observation"` entries read-only); IMGWTools is the only writer, and the store contains no Archiwista files. From the marker the reader requires only `schema` (as `open_store` does); every problem in `StoreInfo.problems` has a code in `problem_codes`; `Meta.producer` and `Meta.producer_version` tell which release wrote the version; `iter_store(skip_versions=…)` returns versions already known to the consumer as `skipped` entries, without listing or reading them (incremental scan, a Python-library-only parameter). Projects pinning store versions (by `sha256` and `content_sha256` from the sidecar) are kept by Archiwista (`archiwista-project/1`, ADR-008); IMGWTools has no projects of its own. Checking freshness and rebuilding a pinned version is provided by `command_for_version` (the version's command from its sidecar, `unsupported`/`command_not_rebuildable` when the metadata do not rebuild it; section "Command catalog").
- **Retman** runs actions as a handler through the public command catalog (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`) — the same options, validation, envelope and error codes as in the CLI and REST; English descriptions from `command_schema(lang="en")`, effects from `x-imgw.writes` and `x-imgw.network`.

The former optional SQLite cache was removed in 3.0.0 without migration — see `docs/CHANGELOG.md`.

## Changes in version 3.0.0

Full list with migration tables: [`docs/CHANGELOG.md`](CHANGELOG.md) (also earlier releases).

### Breaking changes

- CLI: the `datasets`, `stations`, `current` and `pmaxtp` groups replace `imgw fetch …` and `imgw list …`
  (e.g. `imgw fetch hydro -i dobowe -y 2023` → `imgw datasets download -d hydro/dobowe -y 2023`);
  stdout is the `imgw-result/1` envelope, an error is JSON on stderr, exit codes follow the error registry.
- REST: catalog routes `/api/v1/<group>/<command>` replace `/api/v1/hydro|meteo|download|pmaxtp/*`
  and `/map/stations`; errors in `application/problem+json`.
- Python: `station_id` → `station` (argument) and `station_code` (field); `list_*_stations` →
  `find_stations`, `get_hydro_stations_with_coords` → `fetch_hydro_states`,
  `build_hydro_url`/`build_meteo_url` → `archive_files`; `download_hydro_data`,
  `download_meteo_data` return `DownloadResult` instead of `bytes`.
- Removed SQLite cache: the `imgwtools.db` package, the `imgw db` commands, the
  `GET /api/v1/hydro/data` endpoint, its settings and the installation extra. The replacement is
  the versioned store (`imgwtools[store]`, `imgw store …`); `.db` files are neither deleted nor migrated.
- `parse_zip_file` reports a corrupted ZIP as `IMGWDataError`; `parse_stations_csv` requires
  `kind="hydro"|"meteo"` and returns `StationListEntry`.

### New

- Versioned store with a freshness plan, Parquet series, a GeoJSON station
  catalog, PMAXTP per cell and CSV/JSONL export.
- A single catalog of 30 commands for Python, the CLI, REST and MCP (`command_schema`, `run_command`),
  the `imgw-result/1` envelope with pagination, the `ERROR_CODES` error code registry.
- `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`, `download_archives`,
  `select_series`, `summarize_series`, `export_archive`; a registry of 17 datasets from two providers.
- ČHMÚ provider (Czechia): per-station daily hydrological and meteorological data,
  freshness from the listing, canonical content and an observation register, a station catalog with SPA thresholds,
  ČHMÚ quality and flags in series.
- AI agents: `AGENTS.md`, `llms.txt`, `imgw commands guide`, catalog descriptions in English
  (Polish on request: `--lang pl`, `Accept-Language`), command effect metadata, the `imgw mcp` MCP server and `/mcp`.
- Public test store builder `imgwtools.testing.build_fixture_store` (also the PL + CZ variant).
