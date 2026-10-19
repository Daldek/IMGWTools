# IMGWTools

> Python library, CLI, REST API and MCP server for public hydrological and meteorological data: a versioned store of archives and station series, current data and PMAXTP. <!-- imgw:summary -->

<!-- imgw:rules -->

- Result: the JSON envelope `imgw-result/1` with the `status` field (`ok`, `partial`, `failed`, `cancelled`; CLI exit codes 0, 10, 11, 130).
- Error: `{"code", "detail", "details"}` in the last stderr line of the CLI or `application/problem+json` in REST; codes from a closed registry, e.g. `validation_error` = 2 / 400.
- Datasets: full keys `<country>.<provider>.<dataset>`, e.g. `pl.imgw.hydro_daily`, `cz.chmi.hydro_daily`; station codes: IMGW-PIB 9 digits, ČHMÚ WIGOS identifier.
- Commands: `imgw commands schema` or `GET /api/v1/commands/schema`; the full guide: `imgw commands guide --lang en` or `GET /api/v1/commands/guide?lang=en`.

## Docs

- [AGENTS.md](https://raw.githubusercontent.com/Daldek/IMGWTools/master/AGENTS.md): guide for agents in Polish (English: `imgw commands guide --lang en`) — commands, datasets, flags, error codes, flows, what not to do
- [README.md](https://raw.githubusercontent.com/Daldek/IMGWTools/master/README.md): installation and examples for Python, CLI, REST, MCP (Polish)
- [Architecture](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/ARCHITECTURE.md): modules, store, data flow (Polish)
- [Changes](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/CHANGELOG.md): changes and migration from 2.x (Polish)

## Optional

- [Decision log](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/DECISIONS.md): ADR-001–ADR-004 (Polish)
