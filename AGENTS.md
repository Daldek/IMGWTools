# IMGWTools — guide for agents (version 3.0.0)

> Generated from the command catalog: `imgw commands guide --format agents`. Do not edit by hand.

## What IMGWTools is

IMGWTools is a Python library, the `imgw` CLI, a REST API and an MCP server for public hydrological and meteorological data: archives, current data and PMAXTP probable maximum precipitation. Archives go into a versioned store — a plain directory whose versions never change and are identified by SHA-256 — from which station series are read offline. All interfaces are generated from one command catalog.

Use it to read archive and current data of IMGW-PIB and ČHMÚ stations, to keep reproducible local copies and to get PMAXTP values. Not supported: forecasts, ČHMÚ operational data (`now`, `recent`), IMGW-PIB daily synoptic archives, PMAXTP outside Poland. Install: `pip install imgwtools[cli]` (`[mcp]` adds the MCP server, `[store]` the Parquet series).

- `IMGW-PIB` — Poland: keys `pl.imgw.*`, station code `^[0-9]{9}$`, license [IMGW-PIB](https://danepubliczne.imgw.pl/regulations)
- `CHMI` (ČHMÚ) — Czechia: keys `cz.chmi.*`, station code `^0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}$`, license [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)

## Rules: check → run → read

1. **Learn the commands:** `imgw commands list` (a one-sentence summary of each), then `imgw commands schema --command …` or `imgw <group> <command> --schema`; REST `GET /api/v1/commands/list` and `/schema`; in MCP `imgw_commands_list` and `imgw_commands_schema`. Options are JSON Schema properties; rules the schema does not express are in `x-imgw.rules`, effects in `x-imgw.writes`, `x-imgw.network` and `x-imgw.idempotent`.
2. **Check without writing:** `--check` (CLI), `?check=true` (REST, POST), `check: true` (MCP; the default of writing commands), `check_command()` (Python) → an `imgw-plan/1` plan without writing and without downloading content. `store check` and `project check` are checks themselves. Ask the user about a large plan.
3. **Run:** without `check`; read the `status` of the envelope, not only the exit code.
4. **Read offline:** `store info`, `store scan`, `series summary`, `series read` (`limit`/`offset`), `pmaxtp read` — without downloading again.
5. **Decide by codes:** `code`, `status`, `items[].status`, `error_code`; the `detail` text is for humans.

## Interfaces

| Interface | Plan | Result | Error |
|---|---|---|---|
| Python | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `--check` | one-line JSON envelope on stdout | last stderr line `{"code", "detail", "details"}`; exit code |
| REST `/api/v1` | `?check=true` (POST) | 200 + envelope | `application/problem+json` |
| MCP | `check: true` | `structuredContent` = envelope | `isError: true` + `{"code", "title", "detail", "details"}` |

One command in every interface: CLI `imgw <group> <command> --option value` (flag = `--` + the option name with `-` for `_`); Python `run_command("<group> <command>", options={...})`; REST `/api/v1/<group>/<command>` (GET: query parameters, POST: JSON body); MCP tool `imgw_<group>_<command>`.

- **REST:** the server sets the store root (`IMGW_STORE_ROOT`), `version` is relative to it, local options do not exist; writing (POST without `?check=true`) must be enabled on the server and needs the `X-API-Key` header.
- **MCP:** `imgw mcp` (stdio) starts without writes — writing commands return a plan (`check` fixed to `true`); the user enables writes (`--allow-writes`), and even then `check` is `true` by default. `/mcp` of the REST server (`IMGW_MCP_ENABLED=true`) reads and plans only.
- **Language:** machine output is English (this guide, the envelope, error lines, MCP, REST). Polish only on request: `--lang pl` (`commands list|schema|guide`), `lang: "pl"` (MCP), `Accept-Language: pl` (REST).

## Envelope, statuses and errors

A command returns the `imgw-result/1` envelope `{"schema", "command", "check", "status", "result", "notices"}`; `notices` is a list of `{"level", "code", "text"}` (each once, e.g. `license_terms`). List commands return a page `{"items", "total", "limit", "offset"}`, a check an `imgw-plan/1` plan. Stream commands without `path` give only data lines: the CLI writes them to stdout, REST answers with an attachment (status and notices in `X-IMGW-Status`, `X-IMGW-Notices`). REST answers 200 for `partial` and `failed` too — the `status` in the body decides.

| Status | CLI exit code | Meaning |
|---|---|---|
| `ok` | 0 | no failures |
| `partial` | 10 | some items failed — read `items[].status` and `error_code`; the others are done |
| `failed` | 11 | no item succeeded (in a plan: `check_failed`); the envelope is complete |
| `cancelled` | 130 | cancelled (Ctrl+C, a cancelled request); a partial `result` or `null` |

An error has a code from a closed registry, the same in Python, the CLI, REST (problem+json) and MCP (`isError`); `details.option` names the wrong option. Codes with the CLI exit code and the HTTP status (`—`: never reported): `validation_error` (2/400), `not_found` (3/404), `conflict` (4/409), `source_unavailable` (5/502), `missing_dependency` (6/503), `data_error` (7/500), `store_unavailable` (8/503), `io_error` (9/500), `cancelled` (130/—), `forbidden` (12/403), `method_not_allowed` (—/405), `internal_error` (1/500).

## Datasets

A dataset key reads `<country>.<provider>.<dataset>`; a slug (`hydro_daily`) and a legacy alias (`hydro/dobowe`, see `imgw datasets list`) are accepted on input only. Datasets of the store:

| Key | Variables | First year |
|---|---|---|
| `pl.imgw.hydro_daily` | `H`, `Q`, `T` | 1951 |
| `pl.imgw.hydro_monthly` | `{H,Q,T}_{min,mean,max}` | 1951 |
| `pl.imgw.hydro_semiannual` | `{H,Q,T}_{min,mean,max}` | 1951 |
| `pl.imgw.meteo_climate_daily` | `Tmax`, `Tmin`, `Tmean`, `Tground`, `P`, `snow_cover` | 1951 |
| `pl.imgw.meteo_precip_daily` | `P`, `snow_cover`, `fresh_snow` | 1950 |
| `pl.imgw.hydro_stations` | — | — |
| `pl.imgw.meteo_stations` | — | — |
| `pl.imgw.pmaxtp` | `ks`, `sg`, `rb` | — |
| `cz.chmi.hydro_daily` | `H`, `Q`, `T` | 1887 |
| `cz.chmi.meteo_daily` | `P`, `Tmean`, `Tmax`, `Tmin` | — |
| `cz.chmi.hydro_stations` | — | — |
| `cz.chmi.meteo_stations` | — | — |

Outside the store (`datasets files` and `datasets download` only): `pl.imgw.hydro_phenomena`, `pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`, `pl.imgw.meteo_climate_terms`.

- `stations` (WIGOS identifiers): required for `cz.chmi.*`, not allowed for `pl.imgw.*` in `datasets files`, `datasets download`, `store check` and `store sync`; one call covers datasets of one kind (`pl.imgw.*` or `cz.chmi.*`).
- `years`: required in `datasets files`, `datasets download` (except `cz.chmi.meteo_daily`) and, for `pl.imgw.*`, in `store check` and `store sync`; optional there for `cz.chmi.hydro_daily` (none = the published years); never for `cz.chmi.meteo_daily`; not before "First year". `months` only for `pl.imgw.*`, `params` only for `pl.imgw.hydro_semiannual`.

## Commands

One line per command, by effect; options, rules and per-option effects: `imgw commands schema --command "<command>"`. Marks: `[path: …]` — the option writes a file when given; `[is a check]` — the command plans itself; `[local]` — no REST route.

**Read — no network, no writes**

- `datasets list` — List the datasets of the registry: keys, providers, legacy aliases, variables and first year.
- `datasets files` — List the source files of a dataset for given years or stations (offline, no download).
- `datasets providers` — List the data providers: identifiers, countries, licenses, station code patterns, datasets.
- `pmaxtp url` — Build the PMAXTP API URL of a point (offline, without downloading).
- `pmaxtp check` — Check the PMAXTP cell in the store without downloading data. [is a check]
- `pmaxtp read` — Read a saved PMAXTP cell from the store (offline).
- `store info` — Show the state of an IMGW store and the supported contracts (offline, without writing).
- `store scan` — List the versions and problems of an IMGW store (offline, without writing).
- `store export` — Export the records of one archive version as CSV or JSONL (offline, SHA-256 verified). [`path`: overwrite]
- `series select` — Select stations, variables and years of the current series (without writing; an input of a project).
- `series read` — Read the values and flags of one station's series from the store.
- `series summary` — Show the coverage of stations and variables of a series from series.json (without pyarrow).
- `series export` — Export the series of one station as CSV with the attribution of the data provider. [`path`: overwrite]
- `project status` — Show the state of the pinned files of the project tasks (offline). [local]
- `project verify` — Verify the SHA-256 sums of the pinned files of a project (offline). [local]
- `commands list` — List the catalog commands: tool names, effects and routes.
- `commands schema` — Show the JSON Schema of the options of a command or the whole imgw-commands/1 command catalog.
- `commands guide` — Generate the guide for AI agents: AGENTS.md or llms.txt, in Polish or English. [`path`: overwrite]

**Network — connects to a source, writes nothing**

- `stations find` — Find IMGW-PIB and ČHMÚ stations by name, river or code prefix.
- `current hydro` — Fetch current hydrological data from the IMGW API.
- `current meteo` — Fetch current meteorological data from the IMGW API.
- `current synop` — Fetch current synoptic data from the IMGW API.
- `current warnings` — Fetch the current IMGW hydrological and meteorological warnings.
- `current hydro-states` — Fetch the water states of hydrological stations with coordinates (hydro.imgw.pl map).
- `pmaxtp fetch` — Fetch the PMAXTP maximum precipitation of a point (live, without saving).
- `store check` — Check the freshness of the dataset archives without downloading data. [`plan`: overwrite; is a check]
- `project check` — Check the freshness of the data of the project tasks without writing to the store. [`plan`: overwrite; is a check; local]

**Write — new files, versions or tasks; `--check` first**

- `pmaxtp sync` — Download the PMAXTP cell of a point and save it as a version in the store.
- `store init` — Create an empty IMGW store (imgw-store.json marker) in the given directory. [local]
- `store sync` — Download new or missing archives into the store, by plan or by datasets and stations.
- `store catalog` — Build the versioned station catalog stations.geojson of one provider.
- `series build` — Build the Parquet series of a dataset from the current archive versions of the store.
- `project init` — Create the imgw-project.json manifest of a project pointing to a store. [local]
- `project add` — Add a task to the project manifest. [local]

**Overwrite — may replace an existing file or manifest; `--check` first**

- `datasets download` — Download the source files of a dataset to a directory mirroring the provider's server paths. [local]
- `project remove` — Remove a task from the project manifest. [local]
- `project set-store` — Point the project to a new store directory after verifying the pinned files. [local]
- `project download` — Download and pin the data of the project tasks. [local]

## Flags and values

- Lists (`--datasets`, `--months`, `--params`, `--stations`, `--tasks`, `--variables`, `--years`): comma-separated values (`--months 1,2`) or a repeated flag (`-s A -s B`). Years (`--years`): `2024`, `2020-2023`, `2020,2022` or `2018,2020-2023`. Dates (`--end`, `--start`): ISO `YYYY-MM-DD`.
- Switches on by default: `--series/--no-series` (`--no-…` turns it off); the other boolean flags (`--main-only`) take no value and turn their option on.
- Environment: `IMGW_STORE_ROOT` — the default `--root` (CLI, MCP stdio; `stations find` — only with `source=store`); `IMGW_LANG` — the language of the CLI help and of the progress lines (`pl`, `en`).

## Typical flows

Replace the upper-case symbols (`STATION_CODE`, `WIGOS_ID`, `PROJECT`) with the values of earlier steps.

### 1. Daily precipitation at the Poznań station, 2010–2020

1. `imgw stations find --kind meteo --query poznan` — several hits → ask the user; the code of the chosen station is `STATION_CODE`.
2. Choose the dataset: `pl.imgw.meteo_precip_daily` (precipitation stations, `P`) or `pl.imgw.meteo_climate_daily` (climate stations, `P` and temperatures) — the station list does not tell the network of a station.
3. `imgw store check --root /data/imgw --datasets pl.imgw.meteo_precip_daily --years 2010-2020` — plan: the number of files and bytes; the archives cover the whole country, so tell the user the size.
4. `imgw store sync --root /data/imgw --datasets pl.imgw.meteo_precip_daily --years 2010-2020` — after the user agrees; the station series are built as well.
5. `imgw series summary --root /data/imgw --dataset pl.imgw.meteo_precip_daily --stations STATION_CODE` — the station is missing → repeat steps 3–5 with `pl.imgw.meteo_climate_daily`; missing from both → tell the user, do not substitute another station.
6. `imgw series read --root /data/imgw --dataset pl.imgw.meteo_precip_daily --station STATION_CODE --variables P --start 2010-01-01 --end 2020-12-31 --limit 500` — next pages: `--offset`.

### 2. Daily discharge of a Czech station (ČHMÚ)

1. `imgw stations find --kind hydro --query spindleruv --provider CHMI` — the WIGOS identifier of the chosen station is `WIGOS_ID`.
2. `imgw store check --root /data/imgw --datasets cz.chmi.hydro_daily --years 2020-2025 --stations WIGOS_ID` — plan: the station files by year.
3. `imgw store sync --root /data/imgw --datasets cz.chmi.hydro_daily --years 2020-2025 --stations WIGOS_ID` — after the user agrees.
4. `imgw series read --root /data/imgw --dataset cz.chmi.hydro_daily --station WIGOS_ID --variables Q --limit 500` — next pages: `--offset`.

### 3. Reproducible project

1. `imgw project init --project-dir PROJECT --store-dir ../store` — the `imgw-project.json` manifest; `store_dir` relative to the project directory.
2. `imgw project add --project-dir PROJECT --name precipitation --command 'series select' --options '{"dataset":"pl.imgw.meteo_precip_daily","stations":["STATION_CODE"],"years":"2010-2020"}'` — the task keeps the command and its options (without `root`).
3. `imgw project download --project-dir PROJECT --check` — the plan…
4. `imgw project download --project-dir PROJECT` — …then the files are downloaded and pinned (SHA-256) after the user agrees.
5. `imgw project verify --project-dir PROJECT` — the SHA-256 sums of the pinned files (offline).

## What not to do

1. Do not build or crawl IMGW-PIB and ČHMÚ server URLs by hand — use `datasets files`, `datasets download`, `store sync`.
2. Exit codes 10 and 11 are not program failures — read the envelope (`items[].status`, `error_code`).
3. Do not run writes (`store sync`, `series build`, `datasets download`, `project download`) without a plan and the user's consent; in MCP the user, not the agent, enables writes.
4. Do not guess a station or a dataset: with several `stations find` hits, ask; check with `series summary` that a dataset has the station.
5. Do not edit, move or delete store files (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — the store only grows.
6. Do not download "just in case": narrow `years`, `months` and `stations`; do not mix providers in one call with `stations`.
7. Read long lists in pages (`limit`, `offset`); use `series read` or `series export --path`, not CSV in the context.
8. Do not poll `current …` in a loop — it is a live API; keep the result.
9. Pass the `license_terms` notice and the attribution on to the user (IMGW-PIB: terms of the purpose of use; ČHMÚ: CC BY 4.0).
10. Point `version` only below `*/versions/` of the store, without `..`; over REST and MCP over HTTP — relative to the server's store.

Developing this repository? Read CLAUDE.md.
