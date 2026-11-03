# Obserwator - Progress Tracker

Current state of the project (Nogat standard 1.0, DOC-6.1). Release history, cross-project analysis, closed backlog items and working notes: [docs/HISTORY.md](HISTORY.md). Full list of changes: [CHANGELOG.md](CHANGELOG.md).

## Status

| Field | Value |
|------|---------|
| **Version** | 3.0.0 |
| **Date** | 2026-11-03 |
| **Working branch** | `develop` (formerly `slave`, ECO-008). On 2026-11-03 the finished `feature/archiwista-projects` stack `0e0bc3a` (tree as after the green gate `8cd6844c`) was merged into it (`--no-ff`, the author's decision, without a pull request): projects moved to Archiwista and `command_for_version` (ADR-008), data output (`feature/data-output`, ADR-007), Nogat standard 1.0 (`chore/nogat-2.1`), Archiwista compatibility fixes (`fix/archiwista-compat-2`), and earlier `feature/chmi-agents` (ADR-003, ADR-004) and `feature/versioned-store` (ADR-001, ADR-002); these branches were deleted locally and on GitHub. Remaining: `main` (releases, v2.1.1); `fix/archiwista-compat` — superseded by `fix/archiwista-compat-2` (`e77a6f9` and `c280088` cherry-picked over), but `e9d8886` (publication without hard links, rejected in favour of `cb6af4f`) and `2e78eb6` are not in any other branch, so its deletion awaits the author's decision; the local `backup/versioned-store-master-base` `7263212` (a copy of `feature/versioned-store` from before the rework, 8 commits not present elsewhere, not on GitHub) — also the author's decision. Next: merge `develop` → `main` and tag 3.0.0 with the author's approval |
| **Python** | >=3.12 |

| Component | State | Notes |
|-----------|------|-------|
| Versioned data store (ADR-001) | done (3.0.0) | local, rebuildable store index: planned (ADR-001 D2) |
| Single command catalog, CLI and REST (ADR-002) | done (3.0.0) | CLI and REST generated from the catalog |
| ČHMÚ provider (ADR-003) | done (3.0.0) | questions to ČHMÚ and Archiwista confirmations: open (below) |
| AI agent support, MCP server (ADR-004) | done (3.0.0) | agent surfaces in English (ADR-006): done, entry in [HISTORY.md](HISTORY.md) |
| Web GUI (HTMX + Jinja2) | done | ČHMÚ data and GeoJSON layer: planned |
| API key enforcement, per-key limits | planned | backlog in "Next" |
| Compliance with Nogat standard 1.0 (`chore/nogat-2.1`, merged into `develop`) | in progress | done and to do: below and in "Next" |
| Data output: plain mode, store, default root (ADR-007, DEV §19) | done (`develop`) | code, tests and documents finished; for consumers: [CHANGELOG "Migration guide: data output"](CHANGELOG.md) |
| Store reading: Archiwista's requests of 2026-10-25 (ADR-007 erratum) | done (`develop`) | `StoreInfo.problem_codes`, `Meta.producer` and `Meta.producer_version`, `iter_store(skip_versions=)` with `StoreEntry.skipped` (incremental scan, Python only) and a marker without `created_by` readable by the reader; all optional in `/1`, details in [CHANGELOG "Unreleased"](CHANGELOG.md). Archiwista after the pin change: codes instead of text matching, `producer*` from `Meta` instead of the `PACKAGE` constant, `known_versions` as `skip_versions`; requests to Nogat remain (registry edge) |
| Write refusals: directory inside the store and a root with foreign files (ADR-007 erratum, Nogat decisions R1 and R2) | done (`develop`) | `output_dir` inside the store rejected before the first request with `details.paths` = the directory (store only below it: the target path); `--check` lists `not_empty` like `nested_store` as a single root `conflict` action, and reports `store_unavailable` and an unreadable marker (`data_error`) as an error; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| MCP server: buffered `print` on stdout after the client disconnects (final integration run 2026-10-25, F1) | done (`develop`) | `run_stdio` flushes the stdout buffer before the SDK restores descriptor 1, so the text goes to stderr and not to the client (as in Hydrolog and Kartograf); a test in `tests/unit/test_mcp_stdio.py` runs `obserwator mcp` without `PYTHONUNBUFFERED`; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Command line as a call: `parse_command` and `format_command(..., run=)` (Archiwista's request, AGI-2.1, ADR-002 erratum) | done (`develop`) | `parse_command(line)` reads an `obserwator` line with CLI flags into `CommandCall(command, options, run)` (options are the strings the CLI passes to `run_command`; `run` = `{"check": True}` for `--check`); `format_command` writes `--check` via `run`; names, shapes and errors as in Kartograf; the contract test `tests/contract/test_command_lines.py` reads back the line of every example; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Example calls in the catalog (AGI-2.2, ADR-002 erratum) | done (`develop`) | every command has `x-obserwator.examples` (`{call, result}`): a canonical `obserwator` line and an excerpt of the result; the contract test `tests/contract/test_command_lines.py` checks that `format_command(*parse_command(call)) == call` and that `validate_command` accepts the options; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Projects moved to Archiwista (ADR-008; Nogat plan [`2026-10-31-archiwista-projects.md`](https://github.com/Daldek/Nogat/blob/main/docs/plans/2026-10-31-archiwista-projects.md), step 3, items 1–2) | done (`develop`) | removed without aliases: the `project` group (8 commands; the catalog has 30), the project functions, types and exception, the manifest contract, `OperationResult.task` and the `restored_by_content` status; the store, the read API, `content_sha256`/`content_form` in sidecars and the observation registry remain; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Command of a saved version `command_for_version` (ADR-008 D5; Nogat plan 2026-10-31, step 3, item 3) | done (`develop`) | from the sidecar and the store layout, offline: IMGW-PIB and ČHMÚ archives → `store sync`, station lists and catalogs → `store catalog`, series → `series build`, PMAXTP → `pmaxtp sync`; refusal `unsupported`/`command_not_rebuildable` (new Nogat registry code, exit 15, HTTP 422), `not_found`, `data_error`; test `tests/unit/test_command_for_version.py`; Archiwista (pin `8cd6844c`) uses it to check and restore the IMGW pins; Retman also pins `8cd6844c` (both pins are in `develop`) |
| The tool is called Obserwator (ADR-009, Nogat ECO-057; Nogat plan [`2026-11-03-imgwtools-to-obserwator.md`](https://github.com/Daldek/Nogat/blob/main/docs/plans/2026-11-03-imgwtools-to-obserwator.md), step 2) | done (`feature/obserwator`) | distribution, import package and command `obserwator`, `OBSERWATOR_<KEY>`, `[obserwator]`, `<data_dir>/obserwator`, `obserwator-<kind>/1`, `obserwator-store.json`, MCP tools `obserwator_*`, `x-obserwator*`, `ObserwatorError`; no alias (ECO-056); the name map and migration lines: [CHANGELOG "The tool is called Obserwator"](CHANGELOG.md); the GitHub repository keeps its name until the author renames it (plan step 5) |
| CI with an ubuntu/macos/windows matrix | done (`develop`) | `ci.yml` from the Nogat template: the gate on ubuntu, macOS and Windows with Python 3.12 (required) and 3.15 (reported), and `pip-audit`; first green run 2026-11-03 (`feature/ci`, run 41714582095) after Windows fixes (UTF-8 and LF output, a pipe closed by its reader, the agent guide, hard links, the reference CSV) and test fixes for CI terminals and paths |

### Compliance with Nogat standard 1.0 (`chore/nogat-2.1`)

**Done:** pyright → mypy `strict` (ECO-010; tests without annotations are a DEV-7.3 deviation in `CLAUDE.md`), `scripts/gate.sh` + `check-commits.sh`, `uv.lock`, the `live` marker instead of `IMGW_LIVE=1`, coverage ≥ 80% (DEV-7.5), CI/Dependabot from the Nogat templates (they work after the branch rename), `forbidden` with exit code 12 (ERR §4), erratum to ADR-001 D1 (hard links), MCP prefix `obserwator_` = the catalog `operation_id` = the OpenAPI `operationId`, the full set of MCP annotations with `idempotentHint`, the `commands list` command (ECO-018, AGI-5.2, AGI-5.4, AGI-5.9, AGI-6.2; ADR-004 erratum of 2026-10-24); user environment DEV-18: `nogat.toml` via `tomllib`, `NOGAT_*`, `cache_dir`, `IMGW_DATA_DIR` → `OBSERWATOR_REFERENCE_DIR` (breaking change), `obserwator config show --json`, 18 variables in README and `.env.example` (ADR-005).

**Done (document budgets, DOC-1.7):** `CLAUDE.md` 96 lines (budget 200), `README.md` 221 (400), `docs/PROGRESS.md` 191 (300; history in [HISTORY.md](HISTORY.md)) — as of 2026-10-31, `AGENTS.md` 174 lines and 16.0 KiB in both languages (200 lines and 16 KiB), `llms.txt` 2,810 characters before the first list of links (8,000); the `AGENTS.md` and `llms.txt` budgets are guarded by `tests/unit/test_agent_guide.py`, the rest are limits for review. Content moved out of `CLAUDE.md` and `README.md` lives in `docs/CODEBASE.md`, `docs/TESTING.md` and `docs/USAGE.md`. The "unusable `nogat.toml`" error has `details.reason = "invalid_config"` (the cause text in the message), and a file not in UTF-8 ends with `validation_error` (test `test_environment.py`).

## Next

Dependency order; unfinished work first. The backlog is the single source of truth for things to do — add new tasks only here (consolidation 2026-08-02: the former "Planned"/"Implemented" sections and section 11 of `PRD.md`).

1. **Documentation in English (ECO-005, phase 3) — translated 2026-11-03;** `docs/DEVELOPMENT_STANDARDS.md` removed in favour of the Nogat standard (DEV-1.3), the CHANGELOG folded into one `[Unreleased]` against v2.1.1. Open: facts that the budget moves left in two places — the project tree (README ↔ `CODEBASE.md` "Package Tree"), test instructions (README ↔ `TESTING.md`), "Source data structure" (`USAGE.md`) ↔ "Data Structure" (`CODEBASE.md`), the store layout (`CODEBASE.md` ↔ `ARCHITECTURE.md` §8) — still to be merged; the README summary (400 characters, DOC-1.7) and the DOC-2.1 section order have not been checked. `docs/superpowers/` (specs and plans of 3.0.0) stays Polish.
2. **Consumers after the pin changes (ADR-005 D2, ADR-006, ADR-007, ADR-008):** Retman switched to `IMGW_REFERENCE_DIR` and the data output mode names and pins `8cd6844c` with a green gate; Archiwista has an IMGW adapter and pins `8cd6844c`. List of changes for further consumers: [CHANGELOG "Migration guide: data output"](CHANGELOG.md).
3. **Consumers after the rename (ADR-009; Nogat plan 2026-11-03, steps 3–4):** Archiwista, Retman, Hydraulik and Hydrolog pin the rename commit and rename imports, commands, variables, ids and identifiers; Kartograf (frozen) names `obserwator-store.json` in `STORE_MARKERS`; Hydrograf keeps its pin and imports of `imgwtools` until after its v0.5.0. Then the author renames the GitHub repository (step 5) and the URLs follow.
4. **Data output — open:** review by the author. The smoke test with the real network passed on 2026-11-03 (release audit, code of `0045bac`): IMGW-PIB and ČHMÚ `datasets download` with `output_dir` through Python, CLI, REST and MCP; `obserwator store sync … -o` and `obserwator pmaxtp sync … -o`; an existing file refused with `conflict` (exit 4, `output_exists`) and replaced with `--force`. No live test covers plain mode yet.

Further open backlog items (priority in the text):

### Features

- [ ] API key enforcement — middleware validating the `X-API-Key` header. `docs/CODEBASE.md` (section "Cloud & Deployment Details") notes that keys are managed by the CLI (`obserwator admin`) but not enforced on API requests — this is a missing security layer, not a new feature. Priority: high.
- [ ] Per-key rate limiting — tracking and limiting requests per API key. Depends on API key enforcement. Priority: medium.
- [ ] GeoJSON in REST/GUI — the versioned `stations.geojson` catalog exists since 3.0.0 (`build_catalog`, `read_catalog`); missing are a catalog command that reads it (and therefore a REST route) and a layer on the Web GUI map. Priority: medium.
- [ ] Data charts — time series visualisation. A possible pattern: the hydro-dane repo approach — min/avg/max aggregates with validation of a full hydrological year and export to compact static JSON files. Priority: low.
- [ ] CSV export in REST/GUI for data without a store — since 3.0.0 `export_series`/`obserwator series export`/`GET /api/v1/series/export` export series from the store; there is no on-demand export without a store. Priority: low.
- [ ] Request logging — tracking API usage for analytics. Priority: low.
- [ ] Redis caching layer — cache for frequently fetched data. Priority: low.

- [ ] Better KS/SG/RB naming in `PMaXTPData` — property aliases and a `get_design_precipitation()` method; details in the section "TODO: Improve PMaXTPData readability" below. Priority: medium.
- [ ] Native PMAXTP grid in `fetch_pmaxtp` — since 3.0.0 the PMAXTP store (`sync_pmaxtp`/`read_pmaxtp`) keys cells by the `indX/indY` indices from the response and stores the cell centre in `cell.json`, but the `PMaXTPResult` from `fetch_pmaxtp` still has no `point` fields, and there are no cell conversion/iteration functions either; details in the section "TODO: Native PMAXTP grid" below. Reported from Hydrograf (2026-09-28). Priority: high.
- [ ] ČHMÚ data in the Web GUI — the forms and the search support IMGW-PIB only (`datasets(provider="IMGW-PIB")`); ČHMÚ files are per station, so the form needs a station picker (ČHMÚ spec §9.3). Priority: low.

### AI agent support (after 3.0.0, ADR-004)

- [ ] Filter MCP tools by group or provider (`--groups`, `--provider`, `data_commands(provider=…)`), if the context cost of the tool list (about 42 KB) turns out to be a problem (ADR-004, question 4). Priority: low.
- [ ] A limit on network calls of the MCP server on stdio (today only the library's sequential requests) and writing through MCP over HTTP with authorisation (ADR-004, questions 5–6). Priority: low.

### Versioned store (after 3.0.0)

- [ ] Local, rebuildable store index (ADR-001 D2: outside the 3.0.0 release; never as the source of truth). Priority: low.
- [ ] A request to IMGW-PIB for an official list of station coordinates (ADR-001 Q6) and confirmation of the meaning of the hydrographic code and the `river_order` ordering (Q4, Q5) — until then no interpretation. Priority: medium.
- [ ] Extending the store with further datasets (monthly/hourly meteo, synop) — D6 limits 3.0.0 to Archiwista's five datasets and PMAXTP. Priority: low.
- [ ] Questions to ČHMÚ (chmi@chmi.cz; ADR-003, questions 5–10): the time zone of `historical` timestamps and the definition of the HD/QD day, the official hydrological year, whether regenerations preserve bytes and whether a corrections register exists, continuity of `historical_csv`, the meaning of `WGS_ELE`, `RICKM`, `HA`, `QA`, `CEVT`, `PRF_ID`, the full `FLAG` dictionary. Priority: medium.
- [ ] Archiwista confirmations (ADR-003, questions 11–15): `stations[<code>].periods` in coverage labels, distinguishing `relabeled`/`unchanged` by content in IMGW-16, missing content fields as `null`, `kind="observation"` entries read-only (`restored_by_content`/`content_match` from IMGW-19 were dropped together with projects, ADR-008). Priority: medium.
- [ ] The rest of `docs/OBSERWATOR_SPEC.md` (the rename itself is done in 3.0.0, ADR-009): the provider layer and the English API, now without the SQLite cache (replaced by the store); the ČHMÚ provider is described by ADR-003 (item above). Priority: low.

### TODO: Improve PMaXTPData readability (KS/SG/RB)

**Context:** The abbreviations KS, SG, RB in the PMAXTP API response can be confusing. It is easy to mistake the upper confidence bound (SG) for the actual quantile value (KS), which leads to wrong hydrological calculations.

| Symbol | Meaning | Use |
|--------|-----------|--------------|
| **KS** | Quantiles (point estimate) | Design value (default) |
| **SG** | Upper confidence bound | Conservative calculations |
| **RB** | Estimation errors | Uncertainty analysis |

#### Proposed changes

**1. Aliases for better readability:**
```python
@property
def quantiles(self) -> dict:
    """Alias for ks (precipitation quantiles)."""
    return self.ks

@property
def upper_bounds(self) -> dict:
    """Alias for sg (upper confidence bounds)."""
    return self.sg

@property
def errors(self) -> dict:
    """Alias for rb (estimation errors)."""
    return self.rb
```

**2. A method for the design value with a conservative option:**
```python
def get_design_precipitation(
    self,
    duration_minutes: int,
    probability_percent: int,
    conservative: bool = False
) -> float | None:
    """Get design precipitation value for engineering design.

    Args:
        duration_minutes: Duration in minutes
        probability_percent: Probability in percent
        conservative: If True, return upper confidence bound (SG)
                     If False, return quantile estimate (KS) - default

    Returns:
        Precipitation [mm] for engineering design
    """
    if conservative:
        return self.get_confidence_bound(duration_minutes, probability_percent)
    return self.get_precipitation(duration_minutes, probability_percent)
```

**3. Extend the README** with a table of the KS/SG/RB meanings.

**Note:** The existing `get_precipitation()` method already returns the correct value (KS), but direct access to the attributes `data.ks`, `data.sg`, `data.rb` can lead to mistakes.

---

### TODO: Native PMAXTP grid

**Context:** investigation from Hydrograf (2026-09-28, ~60 requests to `https://powietrze.imgw.pl/tpmax-api/point/P/KS/{lat}/{lon}`). The point endpoint assigns the request to the nearest cell centre of a regular grid and returns that cell's parameters, which Obserwator does not expose today. Without them the client does not know which cell it fetched — dense sampling queries the same cell many times, sparse sampling skips cells (Hydrograf's 2 km grid skipped ~80% of the cells).

#### Raw response

```json
{
  "point": {"lon": "21.0100", "lat": "52.2300", "name": "", "method": "POT",
            "dataLon": 21.007098333333, "dataLat": 52.234416666667,
            "indX": 751, "indY": 317, "recalcualted": true},
  "data": {"ks": {...}, "rb": {...}, "sg": {...}}
}
```

- `dataLon`/`dataLat` — cell centre (WGS84), `indX`/`indY` — cell indices.
- `recalcualted` (a typo on the IMGW side) — meaning unknown; the field is absent from responses outside the data coverage.
- Outside Poland: the indices and the centre are returned, but with `data: {}` and an additional `error` key.

#### Grid parameters (measured)

| Parameter | Value |
|---|---|
| System | regular grid in WGS84 degrees (EPSG:4326) |
| Step | Δlon = 0.01001°, Δlat = 0.01° (~680 m × 1110 m at 52°N, ~0.75 km²) |
| Cell centre | `lon = 13.489588333 + 0.01001 · indX`, `lat = 55.404416667 − 0.01 · indY` (indY grows southwards) |
| Point assignment | to the nearest cell centre (checked at cell boundaries) |

Verified on the points (52.23, 21.01) → (751, 317), (50.0, 19.0) → (550, 540), (54.0, 15.0) → (151, 140), (49.3, 14.2) → (71, 610, outside the data coverage). Steps and origin agree in all four.

#### Data range

The response contains **16 durations × 27 probabilities** for each of the `ks`/`sg`/`rb` arrays:
- durations [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440, 2160, 2880, 4320,
- probabilities [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5, 99.9.

#### Proposed changes

1. `PMaXTPResult` — add the fields from the `point` block: `cell_lat`, `cell_lon`, `ind_x`, `ind_y` (and `has_data: bool` based on `error`/empty `data`); keep the raw response (e.g. `raw: dict`) for archiving on the client side.
2. Grid constants and conversion functions: `pmaxtp_cell_for(lat, lon) -> (ind_x, ind_y)`, `pmaxtp_cell_center(ind_x, ind_y) -> (lat, lon)`, `pmaxtp_cells_in_bbox(bbox) -> Iterator[(ind_x, ind_y)]` — fetching "one cell = one request for its centre".
3. A contract test on a saved response (fixture) — verifying the grid steps and origin and the 16 × 27 keys (today `PMaXTPData` knows the 27 probabilities from the 2026-09-28 measurement, without a response saved in a fixture).

## Open questions

Decisions waiting for the author (remove once resolved):

- [ ] Owner's decision: whether the public server enables `/mcp` (`OBSERWATOR_MCP_ENABLED`) — ADR-004, open question 2. Priority: medium.

**For the author (outside the agent's reach):** branch/tag rulesets, Dependabot security updates, `SECURITY.md` and private vulnerability reporting (DEV-3.6, DEV-13.7); the CLA text. Done on 2026-11-03: the branches renamed `master`/`slave` → `main`/`develop` on GitHub (rename API; `main` is the default branch) and locally, with the links in the docs and `llms.*` (ECO-008); the history and author identities rewritten (phase 1).

---

**Last updated:** 2026-11-03
