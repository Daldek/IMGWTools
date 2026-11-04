# Obserwator - A tool for downloading IMGW and ČHMÚ data

A Python library and tools for downloading public data from the Institute of Meteorology and Water Management (IMGW-PIB) and, since 3.0.0, also from the Czech Hydrometeorological Institute (Český hydrometeorologický ústav, ČHMÚ). The data come from the [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/) (IMGW public data) and [ČHMÚ Open Data](https://opendata.chmi.cz/) services.

It also supports data from the probabilistic models of maximum precipitation (PMAXTP) from the [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/) service.

Until release 2.1.1 the tool was called IMGWTools (`pip install imgwtools`, command `imgw`); since 3.0.0 it is Obserwator, because IMGW-PIB is the institute whose data it reads, not the tool ([ADR-009](https://github.com/Daldek/Obserwator/blob/main/docs/DECISIONS.md#adr-009-the-tool-is-called-obserwator)). The old and new names with the migration: [changelog](https://github.com/Daldek/Obserwator/blob/main/docs/CHANGELOG.md).

---

## Features

- **Python library** - `pip install obserwator` for integration with other projects
- **CLI** - `obserwator`, commands generated from the command catalog
- **REST API** - FastAPI with OpenAPI/Swagger documentation, routes generated from the same catalog
- **MCP server** - `obserwator mcp` (extra `obserwator[mcp]`) and the `/mcp` endpoint of the REST server: the catalog commands as tools for AI agents, read-only by default
- **Web GUI** - download forms, station search and an interactive map (IMGW-PIB data)

Since 3.0.0 all interfaces use one catalog of 30 commands (`obserwator commands list`, `obserwator commands schema`): the same option name in Python, CLI (`--option-name`), REST (parameter or JSON field) and MCP (tool argument), the same validation, one result envelope `obserwator-result/1` and one error code registry (`ERROR_CODES`). Machine output (envelope, errors, notices, catalog descriptions, the guide for AI agents, the MCP server) is in English; Polish texts are available on request (`--lang pl`, `Accept-Language: pl`), while CLI help and human-readable CLI lines are in Polish (`OBSERWATOR_LANG=en` switches them to English). Guide for AI agents: [`AGENTS.md`](https://github.com/Daldek/Obserwator/blob/main/AGENTS.md) and [`llms.txt`](https://github.com/Daldek/Obserwator/blob/main/llms.txt).

**Supported data:**
- Current hydrological, meteorological and synoptic data through the IMGW API
- Historical archive data of IMGW-PIB (ZIP/CSV) and ČHMÚ (JSON/CSV per station) — a registry of 17 datasets of two providers (`pl.imgw.*`, `cz.chmi.*`)
- Hydrological and meteorological warnings
- PMAXTP data (probable maximum precipitation)
- Station lists (IMGW-PIB and ČHMÚ search) and water levels of IMGW hydro stations with coordinates

**Key principle:** the HTTP server writes nothing until the administrator sets `OBSERWATOR_ROOT` and enables writes; it generates direct links to the IMGW-PIB and ČHMÚ servers and passes current data through live. A writing command (CLI, Python) has two ways of writing and never writes to the working directory: `-o`/`--output-dir` writes plain files only, without metadata; `--root` or `OBSERWATOR_ROOT` writes to the versioned store. Without either, writes go to the store in the user data directory (`<data_dir>/obserwator`; `obserwator config show --json` shows the root and its source). A single export file: `--output FILE`.

**Versioned data store** (optional, since 3.0.0):
- immutable 1:1 versions of IMGW-PIB and ČHMÚ archives with SHA-256 checksums, HTTP headers and the license in a `*.meta.json` sidecar,
- freshness checks without downloading (IMGW-PIB: listing + `HEAD`, ČHMÚ: one listing of the server directory) and an `obserwator-plan/1` plan,
- station series in Parquet, `stations.geojson` station catalogs of both providers, PMAXTP cells, CSV/JSONL export,
- the command that downloads a stored version again, reconstructed from its sidecar (`command_for_version`, for the pins of Archiwista projects),
- readable offline from a local disk or a network share, without a database.

---

## Installation

```bash
# Library only (minimal dependencies: httpx, pydantic, pydantic-settings, platformdirs)
pip install obserwator

# With CLI
pip install obserwator[cli]

# With REST API
pip install obserwator[api]

# With the versioned store and Parquet series (pyarrow)
pip install obserwator[store]

# With DataFrame export (PMaXTPData.to_dataframe)
pip install obserwator[pandas]

# With the MCP server for AI agents (obserwator mcp; includes the CLI)
pip install obserwator[mcp]

# Full installation (CLI + API + MCP + store + pandas)
pip install obserwator[full]

# For developers (from the repository; uv, environment from uv.lock)
git clone https://github.com/Daldek/Obserwator.git
cd Obserwator
uv sync --locked
```

Writing to the versioned store requires a file system with hard links — the same as Kartograf's store (its ADR-036). Linux, macOS and Windows (ext4, APFS, NTFS) and SMB shares that support hard links work; on FAT/exFAT, some NAS and FUSE file systems, and on an SMB share mounted on macOS, `store init` and every write end with the `conflict` error (`details.reason="not_atomic"`). Reading the store does not need hard links. Writing plain files (`--output-dir`, `--output`) does not use hard links and also works on FAT/exFAT and SMB.

---

## Quick start

Full guides to each interface: [docs/USAGE.md](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md).

### Python

```python
from obserwator import fetch_pmaxtp

# Fetch data for Warsaw (method: "POT" — the default — or "AMP")
result = fetch_pmaxtp(52.23, 21.01, method="POT")
precip = result.data.get_precipitation(15, 50)
print(f"Precipitation 15 min, p=50%: {precip} mm")  # precipitation [mm] for t=15 min, p=50%
```

### CLI

```bash
obserwator datasets list -k hydro
obserwator datasets files -d hydro/dobowe -y 2023 -m 1
obserwator stations find -k hydro -q wisla --limit 5
obserwator current hydro -s 150160180
obserwator pmaxtp fetch --lat 52.23 --lon 21.01 --method AMP
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane    # plain files in the dane/ directory
obserwator store sync -d pl.imgw.hydro_monthly -y 2023              # versioned store in <data_dir>/obserwator
```

stdout is one JSON line — the `obserwator-result/1` envelope; `obserwator commands list` prints all commands of the catalog.

### REST API

```bash
obserwator server --reload  # Swagger UI: http://localhost:8000/docs
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
```

### MCP server

`obserwator mcp` (extra `obserwator[mcp]`) is an MCP server on stdio; client configuration (e.g. `mcpServers` in the settings file):

```json
{
  "mcpServers": {
    "obserwator": {
      "command": "obserwator",
      "args": ["mcp"],
      "env": {"OBSERWATOR_ROOT": "/dane/obserwator"}
    }
  }
}
```

Read-only by default (writing commands return a plan); `--allow-writes` enables writes, and only in directories given with `--allow-dir` (e.g. `"args": ["mcp", "--allow-writes", "--allow-dir", "/dane/obserwator"]`); a root outside them ends with the `forbidden` error.

---

## AI agents: AGENTS.md, llms.txt and the MCP server

An agent (an editor assistant, a chat application, a script with a language model) learns Obserwator from one source that matches the code:

- [`AGENTS.md`](https://github.com/Daldek/Obserwator/blob/main/AGENTS.md) — the guide: the "check → run → read" rule, the Python/CLI/REST/MCP mapping, the envelope and statuses, error codes, the datasets of both providers with option rules, command tables with effects, typical flows (e.g. "daily precipitation at the Poznań station", a ČHMÚ station) and a "what not to do" list;
- [`llms.txt`](https://github.com/Daldek/Obserwator/blob/main/llms.txt) — a summary following llms.txt v2 with links to the documentation; `GET /llms.txt` serves the same file;
- `obserwator commands guide [--format agents|llms] [--lang en|pl] [--output FILE] [--force]` or `agent_guide()` in Python — both files generated on the fly (English by default, `--lang pl` gives Polish); `GET /api/v1/commands/guide`.

`AGENTS.md` and `llms.txt` are derived from the command catalog, the registries and the templates in `src/obserwator/_data/agents/` — they are not edited by hand (rules for working on the code: `CLAUDE.md`).

Language, command effects and MCP server configuration (stdio and `/mcp`): [usage guide](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#ai-agents-language-command-effects-and-the-mcp-server).

---

## Configuration

A setting comes from the first of: the command-line option, the `OBSERWATOR_<KEY>` variable, the `.env` file, the `NOGAT_<KEY>` variable (shared keys `data_dir`, `cache_dir`, `lang`), the `[obserwator]` and `[nogat]` sections of the `nogat.toml` file, the default value. The most important variables: `OBSERWATOR_ROOT` (store root), `OBSERWATOR_LANG` (`pl` or `en`), `OBSERWATOR_DATA_DIR`, `OBSERWATOR_CACHE_DIR`, `OBSERWATOR_REFERENCE_DIR`, `OBSERWATOR_MCP_ENABLED`. `obserwator config show --json` prints every key with its value and source.

Full table of variables, a `nogat.toml` example and store backup: [Configuration](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#configuration).

---

## Data sources

Obserwator does not distribute IMGW-PIB or ČHMÚ data, and the server does not store them by default — every download and write is a deliberate decision of the user or administrator (`--output-dir`, `--output`, `--root`, `OBSERWATOR_ROOT`; without them the CLI and Python write to the store in the user data directory). Below is a summary of the sources used.

| Source | Operator | Terms of use |
|--------|----------|---------------------|
| Measurement and observation archive — `danepubliczne.imgw.pl/data` (hydro/meteo, ZIP/CSV) | IMGW-PIB | Free of charge for private and scientific purposes; high-value data — for any purpose; some commercial uses require an agreement; attribution is mandatory. [Terms](https://danepubliczne.imgw.pl/regulations)
| Real-time API — `danepubliczne.imgw.pl/api/data` (hydro, synop, meteo, warnings) | IMGW-PIB | As above ([terms](https://danepubliczne.imgw.pl/regulations))
| PMAXTP — `klimat.imgw.pl/opady-maksymalne` | IMGW-PIB | Citing IMGW-PIB as the source (data from the `klimat.imgw.pl/opady-maksymalne` page) and citing the monograph of the PMAXTP Project (ed. B. Ozga-Zieliński, IMGW-PIB, Warsaw 2022; monograph: Open Access, CC-BY 4.0); for processed data — a note that the data were processed; use at your own risk. [Terms](https://klimat.imgw.pl/opady-maksymalne/) |
| Station map with coordinates — `hydro-back.imgw.pl/map/stations/hydrologic` (backend of the `hydro.imgw.pl` service) | IMGW-PIB | Terms of the hydro.imgw.pl service (accepted by starting to use it); the general rule of citing IMGW-PIB as the source applies. [Terms](https://hydro.imgw.pl/#/regulamin) |
| Archives and station metadata — `opendata.chmi.cz` (`hydrology/historical`, `hydrology/now/metadata`, `meteorology/climate/historical_csv`, `meteorology/climate/historical/metadata`, `meteorology/climate/now/metadata`) | ČHMÚ (Český hydrometeorologický ústav) | License [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): copying, changes and commercial use provided that ČHMÚ is credited as the author, the license is given and changes are indicated ([ČHMÚ terms](https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti)). ČHMÚ does not prescribe a wording; Obserwator writes "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0" (data source: …, license CC BY 4.0), and for processed forms adds "Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)" (ČHMÚ data have been processed (normalization and format change)) |

The obligation to give attribution when publishing results rests with the user who downloads the data.

### Reference data (station lists, coordinates, format descriptions)

The repository **does not contain** IMGW data. Download the reference files used by the tools (station lists, coordinates, format descriptions) once — after installing the package (`pip install -e .`), without any arguments:

```bash
python -m obserwator.reference_data
```

The downloaded files go to the reference data directory (`OBSERWATOR_REFERENCE_DIR`, by default `<cache_dir>/obserwator/reference`, e.g. `~/.cache/nogat/obserwator/reference`; see "Configuration") and come from IMGW-PIB — they are subject to the IMGW-PIB terms (not the project's MIT license).

The only geographic datasets bundled with the package are the border outlines of Poland `src/obserwator/_data/poland_border_wgs84.geojson` and Czechia `src/obserwator/_data/czechia_border_wgs84.geojson` (position checks in station catalogs) from Natural Earth 1:10m Admin 0 – Countries v5.1.2 — public domain ([terms](https://www.naturalearthdata.com/about/terms-of-use/)), not IMGW-PIB or ČHMÚ data.

---

## Documentation

Usage guide ([docs/USAGE.md](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md)), sections:

- [Using as a Python library](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#using-as-a-python-library)
- [Quick start (CLI)](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#quick-start-cli)
- [REST API](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#rest-api)
- [Web GUI](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#web-gui)
- [AI agents: language, command effects and the MCP server](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#ai-agents-language-command-effects-and-the-mcp-server)
- [Source data structure](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#source-data-structure)
- [Docker](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#docker)
- [Configuration](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#configuration)
- [Versioned store (optional)](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#versioned-store-optional)
- [Changes in version 3.0.0](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#changes-in-version-300)

Other documents:

- [`CLAUDE.md`](https://github.com/Daldek/Obserwator/blob/main/CLAUDE.md) - Instructions for Claude Code
- [`docs/CODEBASE.md`](https://github.com/Daldek/Obserwator/blob/main/docs/CODEBASE.md) - Code and module reference (public API, command catalog, data formats; [project structure](https://github.com/Daldek/Obserwator/blob/main/docs/CODEBASE.md#project-structure-from-readme))
- [`docs/TESTING.md`](https://github.com/Daldek/Obserwator/blob/main/docs/TESTING.md) - Tests: layout, markers, running ([test instructions from the README](https://github.com/Daldek/Obserwator/blob/main/docs/TESTING.md#tests-from-readme))
- [`docs/CHANGELOG.md`](https://github.com/Daldek/Obserwator/blob/main/docs/CHANGELOG.md) - Change history (including BREAKING 3.0.0)
- [`docs/DECISIONS.md`](https://github.com/Daldek/Obserwator/blob/main/docs/DECISIONS.md) - Decision log (ADR-001: versioned store, ADR-002: one command catalog, ADR-003: ČHMÚ provider, ADR-004: AI agent support, ADR-005: user environment, ADR-006: message catalog, ADR-007: writing data, ADR-008: projects moved to Archiwista, ADR-009: the tool is called Obserwator)
- [`docs/ARCHITECTURE.md`](https://github.com/Daldek/Obserwator/blob/main/docs/ARCHITECTURE.md) - System architecture
- [`docs/PRD.md`](https://github.com/Daldek/Obserwator/blob/main/docs/PRD.md) - Product requirements
- [`docs/PROGRESS.md`](https://github.com/Daldek/Obserwator/blob/main/docs/PROGRESS.md) - Current status, next steps, open questions
- [`docs/HISTORY.md`](https://github.com/Daldek/Obserwator/blob/main/docs/HISTORY.md) - Release history and closed work
- [`AGENTS.md`](https://github.com/Daldek/Obserwator/blob/main/AGENTS.md), [`llms.txt`](https://github.com/Daldek/Obserwator/blob/main/llms.txt) - Guide for AI agents (generated: `obserwator commands guide`)

---

## Issues and support

Report issues in the [Issues](https://github.com/Daldek/Obserwator/issues) section.

---

## License

The project is released under the MIT license. Details in the [`LICENSE`](https://github.com/Daldek/Obserwator/blob/main/LICENSE) file.

---

## Author

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
