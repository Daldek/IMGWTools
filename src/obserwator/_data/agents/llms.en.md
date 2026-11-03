# Obserwator

> Python library, CLI, REST API and MCP server for public hydrological and meteorological data: a versioned store of archives and station series, current data and PMAXTP. <!-- obserwator:summary -->

<!-- obserwator:rules -->

- Result: the JSON envelope `obserwator-result/1` with the `status` field (`ok`, `partial`, `failed`, `cancelled`; CLI exit codes 0, 10, 11, 130).
- Error: `{"code", "detail", "details"}` in the last stderr line of the CLI or `application/problem+json` in REST; codes from a closed registry, e.g. `validation_error` = 2 / 400.
- Datasets: full keys `<country>.<provider>.<dataset>`, e.g. `pl.imgw.hydro_daily`, `cz.chmi.hydro_daily`; station codes: IMGW-PIB 9 digits, ČHMÚ WIGOS identifier.
- Commands: `obserwator commands list` (summary) and `obserwator commands schema` (options), or `GET /api/v1/commands/list` and `/schema`; MCP tools `obserwator_commands_list` and `obserwator_commands_schema`; the full guide: `obserwator commands guide` or `GET /api/v1/commands/guide` (Polish: `--lang pl`, `?lang=pl`).

## Docs

- [AGENTS.md](https://raw.githubusercontent.com/Daldek/IMGWTools/main/AGENTS.md): guide for agents in English (Polish: `obserwator commands guide --lang pl`) — commands, datasets, flags, error codes, flows, what not to do
- [README.md](https://raw.githubusercontent.com/Daldek/IMGWTools/main/README.md): installation and examples for Python, CLI, REST, MCP
- [Architecture](https://raw.githubusercontent.com/Daldek/IMGWTools/main/docs/ARCHITECTURE.md): modules, store, data flow
- [Changes](https://raw.githubusercontent.com/Daldek/IMGWTools/main/docs/CHANGELOG.md): changes and migration from 2.x

## Optional

- [Decision log](https://raw.githubusercontent.com/Daldek/IMGWTools/main/docs/DECISIONS.md): ADR-001–ADR-009
