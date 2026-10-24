# IMGWTools — guide for agents (version <!-- imgw:version -->)

> Generated from the command catalog: `imgw commands guide --format agents`. Do not edit by hand.

## What IMGWTools is

IMGWTools is a Python library, the `imgw` CLI, a REST API and an MCP server for public hydrological and meteorological data: archives, current data and PMAXTP probable maximum precipitation. Archives go into a versioned store (a plain directory whose versions never change and are identified by SHA-256) or are written as plain files, and station series are read offline from the store.

Use it to read archive and current data of IMGW-PIB and ČHMÚ stations, to keep reproducible local copies and to get PMAXTP values. Not supported: forecasts, ČHMÚ operational data (`now`, `recent`), IMGW-PIB daily synoptic archives, PMAXTP outside Poland. Install: `pip install imgwtools[cli]` (`[mcp]` adds the MCP server, `[store]` the Parquet series).

<!-- imgw:providers -->

## Rules: check → run → read

<!-- imgw:rules -->

## Interfaces

| Interface | Plan | Result | Error |
|---|---|---|---|
| Python | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `--check` | one-line JSON envelope on stdout | last stderr line `{"code", "detail", "details"}`; exit code |
| REST `/api/v1` | `?check=true` (POST) | 200 + envelope | `application/problem+json` |
| MCP | `check: true` | `structuredContent` = envelope | `isError: true` + `{"code", "title", "detail", "details"}` |

One command in every interface: CLI `imgw <group> <command> --option value` (flag = `--` + the option name with `-` for `_`); Python `run_command("<group> <command>", options={...})`; REST `/api/v1/<group>/<command>` (GET: query parameters, POST: JSON body); MCP tool `imgw_<group>_<command>`.

- **REST:** the server sets the store root (`IMGW_ROOT`), `version` is relative to it, local options do not exist; writing (POST without `?check=true`) must be enabled on the server and needs the `X-API-Key` header.
- **MCP:** `imgw mcp` (stdio) starts without writes — writing commands return a plan (`check` fixed to `true`); the user enables writes (`--allow-writes`), and even then `check` is `true` by default. `/mcp` of the REST server (`IMGW_MCP_ENABLED=true`) reads and plans only.
- **Language:** machine output is English (this guide, the envelope, error lines, MCP, REST). Polish only on request: `--lang pl` (`commands list|schema|guide`), `lang: "pl"` (MCP), `Accept-Language: pl` (REST).

## Envelope, statuses and errors

A command returns the `imgw-result/1` envelope `{"schema", "command", "check", "status", "result", "notices"}`; `notices` is a list of `{"level", "code", "text"}` (each once, e.g. `license_terms`). List commands return a page `{"items", "total", "limit", "offset"}`, a check an `imgw-plan/1` plan. Stream commands without `output` give only data lines: the CLI writes them to stdout, REST answers with an attachment (status and notices in `X-IMGW-Status`, `X-IMGW-Notices`). REST answers 200 for `partial` and `failed` too — the `status` in the body decides.

<!-- imgw:statuses -->

An error has a code from a closed registry, the same in Python, the CLI, REST (problem+json) and MCP (`isError`); `details.option` names the wrong option. Codes with the CLI exit code and the HTTP status (`—`: never reported): <!-- imgw:errors -->.

## Datasets

A dataset key reads `<country>.<provider>.<dataset>`; a slug (`hydro_daily`) and a legacy alias (`hydro/dobowe`, see `imgw datasets list`) are accepted on input only. Datasets of the store:

<!-- imgw:datasets -->

- `stations` (WIGOS identifiers): required for `cz.chmi.*`, not allowed for `pl.imgw.*` in `datasets files`, `datasets download`, `store check` and `store sync`; one call covers datasets of one kind (`pl.imgw.*` or `cz.chmi.*`).
- `years`: required in `datasets files`, `datasets download` (except `cz.chmi.meteo_daily`) and, for `pl.imgw.*`, in `store check` and `store sync`; optional there for `cz.chmi.hydro_daily` (none = the published years); never for `cz.chmi.meteo_daily`; not before "First year". `months` only for `pl.imgw.*`, `params` only for `pl.imgw.hydro_semiannual`.

## Commands

One line per command, by effect; options, rules and per-option effects: `imgw commands schema --command "<command>"`. Marks: `[output: …]` — the option writes a file when given; `[is a check]` — the command plans itself; `[local]` — no REST route.

<!-- imgw:commands -->

## Flags and values

<!-- imgw:flags -->

## Typical flows

Replace the upper-case symbols (`STATION_CODE`, `WIGOS_ID`, `PROJECT`) with the values of earlier steps.

<!-- imgw:flows -->

## What not to do

1. Do not build or crawl IMGW-PIB and ČHMÚ server URLs by hand — use `datasets files`, `datasets download`, `store sync`.
2. Exit codes 10 and 11 are not program failures — read the envelope (`items[].status`, `error_code`).
3. Do not run writes (`store sync`, `series build`, `datasets download`, `project download`) without a plan and the user's consent.
4. Do not guess a station or a dataset: with several `stations find` hits, ask; check with `series summary` that a dataset has the station.
5. Do not edit, move or delete store files (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — the store only grows.
6. Do not download "just in case": narrow `years`, `months` and `stations`; do not mix providers in one call with `stations`.
7. Read long lists in pages (`limit`, `offset`); use `series read` or `series export --output`, not CSV in the context.
8. Do not poll `current …` in a loop — it is a live API; keep the result.
9. Pass the `license_terms` notice and the attribution on to the user (IMGW-PIB: terms of the purpose of use; ČHMÚ: CC BY 4.0).
10. Point `version` only below `*/versions/` of the store, without `..`; over REST and MCP over HTTP — relative to the server's store.

Developing this repository? Read CLAUDE.md.
