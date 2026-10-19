# IMGWTools — guide for agents (version <!-- imgw:version -->)

> Generated from the command catalog: `imgw commands guide --format agents --lang en`.
> Do not edit by hand. The repository keeps the Polish guide (`AGENTS.md`); this English one is generated on demand.

## What IMGWTools is

IMGWTools is a Python library, the `imgw` CLI, a REST API and an MCP server for public hydrological and meteorological data: archives, current data and PMAXTP probable maximum precipitation. Archives go into a versioned store — a plain directory whose versions never change and are identified by SHA-256 — from which station series are read offline. Every interface is generated from one command catalog, so all of them share the option names, validation, result envelope and error codes. <!-- imgw:summary -->

<!-- imgw:providers -->

## Rules: check → run → read

<!-- imgw:rules -->

## Interfaces

| Interface | Discovery | Plan | Result | Error |
|---|---|---|---|---|
| Python | `command_schema()`, `data_commands()` | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `imgw commands schema`, `--schema` | `--check` | one-line JSON envelope on stdout; exit code | last stderr line `{"code", "detail", "details"}`; exit code from the registry |
| REST `/api/v1` | `GET /api/v1/commands/schema` | `?check=true` (POST) | 200 + envelope (`status` in the body) | `application/problem+json` |
| MCP | `tools/list` | `check: true` | `structuredContent` = envelope | `isError: true` + `{"code", "title", "detail", "details"}` |

One command in every interface: CLI `imgw <group> <command> --option value` (flag = `--` + the option name with `-` instead of `_`); Python `run_command("<group> <command>", options={"option": value})` or the function of the "Function" column of the command tables with the same arguments; REST `/api/v1/<group>/<command>` (GET: query parameters, lists as a repeated parameter; POST: JSON body); MCP — the tool `<x-imgw.operation_id>` (the command name with the space and `-` replaced by `_`, e.g. `store_sync`, `current_hydro_states`) with the options as arguments.

- **REST:** the server sets the store root (`IMGW_STORE_ROOT`; a request gives no `root`), `version` is relative to the server's store, local options (e.g. `path`) do not exist; writing (POST without `?check=true`) must be enabled on the server and needs the token in the `X-API-Key` header.
- **MCP:** `imgw mcp` (stdio, extra `imgwtools[mcp]`) starts without writes — writing commands have `check` fixed to `true` and return a plan; the user enables writes (`imgw mcp --allow-writes`), and even then `check` is `true` by default. The `/mcp` endpoint of the REST server (`IMGW_MCP_ENABLED=true`) covers the commands with a REST route, reading and planning only.

## Envelope, statuses and errors

A command returns the `imgw-result/1` envelope: `{"schema": "imgw-result/1", "command", "check", "status", "result", "notices"}`, where `notices` is a list of `{"level", "code", "text"}` (each notice once, e.g. `license_terms`). List commands have a page `{"items", "total", "limit", "offset"}` as `result`, and a check (`check`) an `imgw-plan/1` plan with `items[].status` and `actions[].status`. Stream commands (result "text lines" in the command tables) without `path` give only the data lines: the CLI writes them to stdout, REST answers with an attachment whose status and notices are in the `X-IMGW-Status` and `X-IMGW-Notices` headers. REST answers 200 for `partial` and `failed` too — the `status` in the body decides.

<!-- imgw:statuses -->

An error has a code from a closed registry, the same in Python (`IMGWError.code`), the CLI (last stderr line and exit code), REST (problem+json and HTTP status) and MCP (`isError`); `details.option` names the wrong option, and `—` marks an interface that never reports the code.

<!-- imgw:errors -->

## Datasets

A dataset key reads `<country>.<provider>.<dataset>`; a slug (`hydro_daily`) and a legacy alias (`hydro/dobowe`) are accepted on input only — results and store slots always name the full key.

<!-- imgw:datasets -->

- `stations` (WIGOS identifiers) is required for `cz.chmi.*` and not allowed for `pl.imgw.*` in `datasets files`, `datasets download`, `store check` and `store sync`; one call covers datasets of one kind: country archives `pl.imgw.*` or station files `cz.chmi.*`.
- `years`: required in `datasets files` and `datasets download` (except `cz.chmi.meteo_daily`) and for `pl.imgw.*` in `store check` and `store sync`; optional there for `cz.chmi.hydro_daily` (none = the published years); never allowed for `cz.chmi.meteo_daily` (its files cover the whole history of a station) and not earlier than the "First year".
- `months` only for `pl.imgw.*`; `params` (`H`, `Q`, `T`) only for `pl.imgw.hydro_semiannual`.
- Datasets outside the store ("In store" = `no`) support only `datasets files` and `datasets download`; station lists enter the store through `store catalog`, PMAXTP through `pmaxtp sync`.
- The IMGW-PIB hydrological year runs from 1 November to 31 October (`year_type`: `hydrological` or `calendar`).

## Commands

The table of each group gives the command, the Python function and the result type, the options in catalog order (`*` — required, `=` — default value), the effect of a run (`read`; `network` — connects to the source; `write` — only new files, versions or tasks; `write (may overwrite)` — may replace an existing file; an option before a colon writes a file when given), the `check` twin (`itself` — the command is a check, `—` — none) and the REST method (`—` — a local command without a route). The full option schema: `imgw commands schema --command "<command>" --lang en`.

<!-- imgw:commands -->

## Flags and values

<!-- imgw:flags -->

## Typical flows

The commands are in the form of `format_command` (years expanded to a list; `--years 2010-2020` works the same). Replace the upper-case symbols (`STATION_CODE`, `WIGOS_ID`, `PROJECT`) with the values of earlier steps; in another interface use the mapping of the "Interfaces" section.

<!-- imgw:flows -->

## What not to do

1. Do not build or crawl IMGW-PIB and ČHMÚ server URLs by hand — use `datasets files`, `datasets download`, `store sync`.
2. Do not decide on the Polish `detail` or the help text — decide by `code`, `status`, the exit code and the JSON fields.
3. Exit codes 10 and 11 are not program failures — read the envelope (`items[].status`, `error_code`).
4. Do not run writes (`store sync`, `series build`, `datasets download`, `project download`) without a plan and the user's consent; in MCP the user, not the agent, enables the write mode.
5. Do not guess a station or a dataset: with several `stations find` hits, ask; check with `series summary` that a dataset has the station.
6. Do not edit, move or delete store files (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — the store only grows, and SHA-256 identifies a version.
7. Do not download "just in case": narrow `years`, `months` and `stations`; IMGW-PIB archives cover the whole country, ČHMÚ files single stations.
8. `stations` is required for `cz.chmi.*` and not allowed for `pl.imgw.*`; do not mix providers in one call with `stations`; `years` is not allowed for `cz.chmi.meteo_daily`.
9. Do not expect ČHMÚ operational data (`now`, `recent`), IMGW-PIB daily synoptic archives or PMAXTP outside Poland — they are not supported.
10. Read long lists in pages (`limit`, `offset`); do not load CSV exports into the context — use `series read` or `series export --path`.
11. Do not poll `current …` in a loop — it is a live API; keep the result.
12. Pass the `license_terms` notice and the attribution on to the user (IMGW-PIB: terms of the purpose of use; ČHMÚ: CC BY 4.0).
13. Point `version` only below `*/versions/` of the store, without `..`; over REST and MCP over HTTP — relative to the server's store.
14. Read only the last JSON line of the CLI stderr; progress and notices are for humans.
15. Do not edit `AGENTS.md` or `llms.txt` by hand — regenerate them with the command of the header.

## Working on the repository code

This file is about using IMGWTools. Code changes follow `CLAUDE.md`, `docs/DEVELOPMENT_STANDARDS.md` and `docs/RULES.md` (architecture: `docs/ARCHITECTURE.md`, decisions: `docs/DECISIONS.md`). Gate: `.venv/bin/python -m pytest`, `.venv/bin/ruff check src/ tests/`, `.venv/bin/ruff format --check src/ tests/`, `.venv/bin/pyright src/imgwtools/`. A change of the command catalog, of the dataset, provider or error registry, or of the templates `src/imgwtools/_data/agents/` regenerates `AGENTS.md` and `llms.txt` in the same change: `imgw commands guide --format agents --lang pl --path AGENTS.md` and `imgw commands guide --format llms --lang pl --path llms.txt` (a test compares the bytes of the files with the generator).
