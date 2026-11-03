# Obserwator — Technical specification (future major release, working version 4.0.0)

**Status:** Draft for review · **Date:** 2026-08-11 · **Updated:** 2026-11-03 (partly superseded: §7 by ADR-001, the ČHMÚ part by ADR-003, the release of the rename by ADR-009)
**Basis:** `docs/OBSERWATOR_RESEARCH.md` (feasibility study of 2026-08-11)

> **Note (owner decision of 2026-10-17):** release **3.0.0** of the `imgwtools` package is the versioned data store according to ADR-001 (`docs/DECISIONS.md`, `docs/CHANGELOG.md`), not Obserwator. This causes two changes to this draft:
> 1. **§7 "SQLite cache — schema v2" is superseded** by the versioned store (files + sidecars, no database). The SQLite cache was removed in 3.0.0; Obserwator does not bring the database back.
> 2. **Obserwator is only a future rename and extension with providers** (provider layer, ČHMÚ, English API) in the next major release — working version 4.0.0, not 3.0.0. The store contracts (`imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`) change only according to the IMGW-13 policy (new `/N`, transition period).
>
> The remaining sections describe the state of the plan as of 2026-08-11 and need another review before implementation.

> **Note (2026-10-18, ADR-003 — proposal):** the ČHMÚ part of this draft is superseded by `docs/DECISIONS.md` ADR-003 ("ČHMÚ provider in the IMGW store") and `docs/superpowers/specs/2026-10-18-chmi-provider-design.md`. ČHMÚ enters as the second provider within the 3.x contracts (release 3.1.0, without renaming the package): in the dataset registry (`cz.chmi.*`), the store, the ADR-002 command catalog and the `IMGWError` error codes. For ČHMÚ, the following are superseded: §6 in full (kept below as a historical record with an erratum), the provider interface and registry from §3.2–§3.4 and the `provider=` facade from §4 (replaced by `ProviderDescriptor` and the `provider` option of the command catalog), the ČHMÚ commands from §8, the `/api/v2/{provider}` routes from §9, the ČHMÚ state map from §10, stage 7 from §12, the ČHMÚ risks from §13 and item 3 from §14. The ČHMÚ scope is the daily hydro archives (H, Q, T) and meteo archives (precipitation, air temperature) with the station catalog; ČHMÚ current data, CAP warnings and monthly archives are out of scope. The rename to Obserwator remains a future decision.

> **Note (2026-10-31, ADR-008):** projects moved to Archiwista (`archiwista-project/1`); the project manifest was removed from the list of contracts in item 2 above, and the `project` command group from §8. Obserwator, like IMGWTools, has no projects of its own.

> **Note (2026-11-03, ADR-009 — supersedes the rename part of item 2 of the note of 2026-10-17):** the tool is renamed Obserwator in release **3.0.0**, not in a later major release: the distribution and import package `obserwator`, the command `obserwator`, `OBSERWATOR_<KEY>`, `obserwator-<kind>/1`, `obserwator-store.json` and `ObserwatorError` with its subclasses (`ObserwatorConnectionError`, `ObserwatorDataError`, … — not the `Source*Error` names of §2), without aliases (`docs/DECISIONS.md` ADR-009, Nogat ECO-057). Only the names change; the provider layer, the English API and the other proposals of this draft stay proposals for a later release. The sections below keep the names of their day.

---

## 1. Goal and scope of the Obserwator release

Turning `imgwtools` (3.x, with the versioned store) into `obserwator` — a multi-source library of hydro-meteorological data, in the major release following 3.0.0 (working version 4.0.0). Scope of the first Obserwator release:

1. Provider layer (data source abstraction) and moving IMGW behind its interface.
2. Second provider: **ČHMÚ** (Czechia, opendata.chmi.cz).
3. Full rebranding **without backward aliases** — the consumers are under our control and migrate once.
4. Public API in **English** (enums, parameters, function names).
5. Update of all 4 interfaces: library, CLI, REST API, Web GUI.

Out of scope for this release (anticipated in the architecture, delivered in later releases): DE providers (PEGELONLINE, DWD), Baltic module, SK (opendata.shmu.sk + Meteoalarm).

### Directional decisions (approved by the owner)

| Decision | Choice | Rationale |
|---|---|---|
| Backward compatibility | **None** — clean break | Control over all consumers; priority: clean architecture |
| Rebranding | Full, at once (package, CLI, env, exceptions) | One name everywhere, no transition period |
| API language | English | Consistency across many countries; Polish strings remain only as URL segments inside the IMGW provider |
| Version | working version 4.0.0 (SemVer — major break); the number 3.0.0 was taken by the versioned store (ADR-001) | In line with PRD §10 |

---

## 2. Naming and packaging

| Element | Was (2.x/3.x) | Will be (Obserwator) |
|---|---|---|
| Python / PyPI package | `imgwtools` | `obserwator` |
| Source directory | `src/imgwtools/` | `src/obserwator/` |
| CLI entry point | `imgw` | `obserwator` |
| Env prefix | `IMGW_` | `OBSERWATOR_` |
| Exceptions | `IMGWError`, `IMGWConnectionError`, … | `ObserwatorError`, `SourceConnectionError`, `SourceDataError`, `SourceValidationError`, `ProviderNotFoundError` |
| Data storage | up to 2.2.0: SQLite database file; from 3.0.0: versioned store with an explicit root | versioned store with no conceptual changes (ADR-001); no database file |
| Extras | `[cli]`, `[api]`, `[store]`, `[pandas]`, `[full]` | conceptually unchanged; providers are NOT separate extras (core: `httpx` + `pydantic` is enough for IMGW and ČHMÚ) |

The `IMGW_ENCODING` constant disappears from the public API — the encoding is a property of the provider (`ProviderInfo.archive_encoding`).

---

## 3. Provider layer architecture

### 3.1 Directory structure

```
src/obserwator/
├── __init__.py              # public API (facade + provider registry)
├── _version.py
├── config.py                # pydantic-settings, env_prefix="OBSERWATOR_"
├── exceptions.py
├── models.py                # CANONICAL models (shared by all providers)
├── http.py                  # shared HTTP client (sync+async, retry, User-Agent)
├── providers/
│   ├── __init__.py          # registry: get_provider(), list_providers()
│   ├── base.py              # DataProvider (Protocol), ProviderInfo, Capability
│   ├── imgw/
│   │   ├── __init__.py      # class ImgwProvider
│   │   ├── urls.py          # former url_builder.py (logic unchanged)
│   │   ├── mappers.py       # IMGW JSON → canonical models (former from_api_response)
│   │   └── parsers.py       # archive CSV parsers (CP1250, hydrological year)
│   └── chmi/
│       ├── __init__.py      # class ChmiProvider
│       ├── urls.py          # opendata.chmi.cz URL patterns
│       ├── mappers.py       # ČHMÚ JSON → canonical models
│       └── metadata.py      # meta1/meta2.json → stations, SPA thresholds
├── parsing/
│   ├── csv_utils.py         # _detect_delimiter, _decode_content, _iter_rows, _safe_float
│   └── cap.py               # CAP XML parser (warnings; used by ČHMÚ, later DE/Meteoalarm)
├── store/                   # versioned store (ADR-001; replaces the former §7)
├── api/                     # FastAPI (see §9)
├── cli/                     # Typer (see §8)
└── web/                     # Web GUI (see §10)
```

Removed without a successor: `core/imgw_api.py`, `core/imgw_datastore.py`, `core/imgw_spatial.py` (legacy, ~817 lines), `urls.py` and `parsers.py` as root-level re-exports (replaced by the provider namespaces).

### 3.2 Provider interface (`providers/base.py`)

```python
class Capability(StrEnum):
    """Provider capabilities — the provider declares what it can do."""
    CURRENT_HYDRO = "current_hydro"        # current water levels/discharges
    CURRENT_WEATHER = "current_weather"    # current meteo data (formerly "synop")
    ARCHIVE_HYDRO = "archive_hydro"        # hydro archives
    ARCHIVE_WEATHER = "archive_weather"    # meteo archives
    STATIONS = "stations"                  # station list with coordinates
    WARNINGS = "warnings"                  # warnings
    PMAX = "pmax"                          # probable maximum precipitation (IMGW-only)


@dataclass(frozen=True)
class ProviderInfo:
    id: str                    # "imgw", "chmi"
    name: str                  # "IMGW-PIB", "ČHMÚ"
    country: str               # ISO 3166-1 alpha-2: "PL", "CZ"
    bbox: BBox                 # coordinate validation (instead of the POLAND_* constants)
    capabilities: frozenset[Capability]
    license: str               # e.g. "CC BY 4.0"
    attribution: str           # required attribution text
    archive_encoding: str      # "cp1250" (IMGW) / "utf-8" (ČHMÚ)


class DataProvider(Protocol):
    """Provider contract. Methods outside capabilities raise NotSupportedError."""
    info: ProviderInfo

    def list_stations(self, kind: StationKind) -> list[Station]: ...
    def fetch_current(self, kind: DataKind, station_id: str | None = None) -> list[Measurement]: ...
    def fetch_warnings(self, kind: WarningKind) -> list[Warning_]: ...
    def build_archive_urls(self, query: ArchiveQuery) -> list[DownloadURL]: ...
    def download_archive(self, query: ArchiveQuery) -> bytes: ...
    def parse_archive(self, data: bytes, query: ArchiveQuery) -> list[ArchiveRecord]: ...
    # every method has an async variant: alist_stations(), afetch_current(), ...
```

Registry: `providers/__init__.py` keeps an `{id: class}` dictionary; `get_provider("chmi")` returns a singleton. Registration is an entry in the dictionary (no entry_points in the first Obserwator release — we will come back to this when providers become external packages).

### 3.3 Canonical models (`models.py`)

We keep the proven principle from 2.x: **language-neutral fields, units in the names, all source specifics in the provider mappers**.

```python
class Station(BaseModel):
    provider: str                      # "imgw" / "chmi"
    station_id: str                    # native provider ID (IMGW: "153140010", ČHMÚ: WIGOS "0-203-1-001000")
    name: str
    kind: StationKind                  # HYDRO / WEATHER
    latitude: float | None
    longitude: float | None
    river: str | None = None
    elevation_m: float | None = None
    alert_levels: AlertLevels | None = None   # thresholds: warning/alarm (IMGW) ≙ SPA1-3 (ČHMÚ)
    water_state: str | None = None

class HydroMeasurement(BaseModel):
    provider: str
    station_id: str
    timestamp: datetime                # always aware, UTC
    water_level_cm: float | None
    flow_m3s: float | None
    water_temp_c: float | None

class WeatherMeasurement(BaseModel):   # formerly SynopData
    provider: str
    station_id: str
    timestamp: datetime
    temperature_c: float | None
    precipitation_mm: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    humidity_pct: float | None
    pressure_hpa: float | None

class Warning_(BaseModel):
    provider: str
    kind: WarningKind                  # HYDRO / WEATHER
    event: str
    severity: str                      # CAP scale: Minor/Moderate/Severe/Extreme (IMGW mapped)
    area: str
    valid_from: datetime | None
    valid_to: datetime | None
    description: str | None
```

The station identity key across the whole system is the pair **`(provider, station_id)`** — never `station_id` alone.

### 3.4 Public enums (English)

```python
class Interval(StrEnum):
    DAILY = "daily"            # IMGW: "dobowe",   ČHMÚ: DQ
    HOURLY = "hourly"          # IMGW: none,       ČHMÚ: HQ
    MONTHLY = "monthly"        # IMGW: "miesieczne", ČHMÚ: MQ
    SEMI_ANNUAL = "semi_annual"  # IMGW: "polroczne_i_roczne", ČHMÚ: none

class WeatherSubtype(StrEnum):
    CLIMATE = "climate"        # IMGW: "klimat" (k)
    PRECIPITATION = "precip"   # IMGW: "opad" (o)
    SYNOP = "synop"            # IMGW: "synop" (s)
```

Mapping an enum to the native URL segment/file type is an internal matter of the provider (`providers/imgw/urls.py`, `providers/chmi/urls.py`). Combinations unavailable at a given provider → `NotSupportedError` with a readable message (like today's `ValueError` for terminowe+opad).

### 3.5 Shared HTTP client (`http.py`)

Eliminates the boilerplate repeated 12× in the 2.x `fetch.py`:

```python
def get_json(url, *, timeout=30.0, headers=None) -> Any
def get_bytes(url, *, timeout=120.0, headers=None) -> bytes
# + async variants; shared: retry (3× with backoff), User-Agent "obserwator/{version}",
# mapping of httpx exceptions → SourceConnectionError (with the provider name in the message)
```

---

## 4. Public library API (facade)

The facade in `obserwator/__init__.py` — a thin layer over the provider registry. All functions take `provider: str = "imgw"` (IMGW stays the default — "Polish by birth" behavior, a deliberate product decision).

```python
from obserwator import (
    # facade
    fetch_hydro_current,      # (provider="imgw", station_id=None) -> list[HydroMeasurement]
    fetch_weather_current,    # formerly fetch_synop
    fetch_warnings,           # (kind, provider="imgw") -> list[Warning_]
    fetch_pmax,               # formerly fetch_pmaxtp; delegates to providers with Capability.PMAX
    list_stations,            # (kind, provider="imgw") -> list[Station]
    build_archive_urls,       # (ArchiveQuery) -> list[DownloadURL]
    download_archive,         # (ArchiveQuery) -> bytes
    # registry
    get_provider, list_providers,
    # models, enums, exceptions — as in §3
)
```

`ArchiveQuery` (pydantic) replaces the scattered `interval/year/month/param/subtype` parameters:

```python
class ArchiveQuery(BaseModel):
    provider: str = "imgw"
    kind: DataKind                       # HYDRO / WEATHER
    interval: Interval
    year: int
    month: int | None = None
    station_id: str | None = None        # required by ČHMÚ (per-station files), ignored by IMGW
    param: HydroParam | None = None      # IMGW polroczne: T/Q/H
    subtype: WeatherSubtype | None = None
```

Cross-validation (e.g. `month` required for IMGW daily <2023, `station_id` required for ČHMÚ) lives in the provider validators, not in the model — the model only carries data.

All sync functions have `a*` (async) counterparts, implemented once — the sync variant is a wrapper over the async one (`anyio`/`asyncio.run` in a thin layer), which removes the sync/async duplication of 2.x.

---

## 5. IMGW provider (`providers/imgw/`)

Moving the existing, tested logic without substantive changes:

- `urls.py` ← `core/url_builder.py` (patterns `codz_`/`mies_`/`polr_`, 5-year meteo folders, combination exceptions). URL constants move into the provider module.
- `mappers.py` ← the `from_api_response()` methods from the 2.x `models.py` (mapping of `id_stacji`, `stan_wody`, `przeplyw`, `województwo`…).
- `parsers.py` ← `_parsing/hydro.py` and `_parsing/meteo.py` (3.0.0) minus the generic helpers (those go to `parsing/csv_utils.py`). The hydrological year (XI–X), missing-value codes (`9999`, `99999.999`, `99.9`) and the `"Odra (1)"` format stay here as provider knowledge.
- Stations: three sources as today (hydro CSV, meteo CSV, hydro-back.imgw.pl with a Referer header) — consolidated in one place; **the duplicated parsing in `web/app.py` is removed**, the layers call the provider.
- `ProviderInfo`: bbox of Poland (49.0–55.0 / 14.0–24.5), `capabilities = {CURRENT_HYDRO, CURRENT_WEATHER, ARCHIVE_HYDRO, ARCHIVE_WEATHER, STATIONS, WARNINGS, PMAX}`, `archive_encoding="cp1250"`, attribution "Źródłem pochodzenia danych jest IMGW-PIB" ("The source of the data is IMGW-PIB").
- A known extension from the research (does not block the release, but worth doing right away): tide-gauge stations are in the current-data API but not in the station CSV — `list_stations` for IMGW should merge both sources.

## 6. ~~ČHMÚ provider (`providers/chmi/`)~~ (SUPERSEDED by ADR-003 — do not implement)

> **Superseded 2026-10-18** by ADR-003 and the spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md` (scope §1, registry §2, inventory from the listing §4, parsers §5, station catalog §7, license §8). The content below is a historical record of the 2026-08-11 draft. **Erratum from the live reconnaissance of opendata.chmi.cz on 2026-10-18** (facts that are wrong or incomplete in the table and decisions below; sources — spec 2026-10-18 §0):
>
> - `hydrology/now/data/{WIGOS}.json` is rewritten every 20 minutes (:00, :20, :40) when new data has arrived, not "every 1 h"; the measurement step depends on the station (5, 10, 15, 30 or 60 min); water temperature has the code `TH`; the same file contains the `H_F`/`Q_F` forecasts (158 stations).
> - The `HQ`, `MQ` and `MMQ` archives are not in `daily/`: each code has its own directory (`hourly/`, `monthly/`, `monthly_max/` …). Station years have gaps, so the inventory requires a directory listing (the research advice in §3 "construct names, do not list" does not work for archives), and a 404 means an unpublished year, not an error.
> - In `meta1.json`, `SPA4H`/`SPA4Q` are the water level or discharge corresponding to the 50-year discharge, not a fourth degree; thresholds may be empty; the assignment of SPA to IMGW warning and alarm levels (§3.3 "≙ SPA1-3", §7 "SPA2/SPA3") is unverified.
> - Time: the hydro `now` and `recent` data are in UTC (checked), and the climate PDF also states UTC; the "SEČ a SELČ" note comes from the hydrology PDF, and for the `historical` data UTC versus fixed SEČ is unconfirmed. Daily meteo data use the climatological day (precipitation from the 06 UTC term of day D, Tmax and Tmin for the 20–20 UTC period). Times in CAP carry a local offset (`+01:00`/`+02:00`).
> - CAP: type 50 files are 0.86–2.35 MB, type 70 files (HAMR drought) are 0.4–61 KB and may have no `<info>` at all; the area is described by `EMMA_ID`, not NUTS3.
> - Station metadata include foreign stations (e.g. Reykjavik, Marambio base), so the CZ rectangle is not enough to validate location.
> - The `DT,VAL` table applies only to the `historical` hydro archives; hydro `now` and `recent` have an `objList` with a list of `{dt, value}`, and meteo — `STATION,ELEMENT,…` tables.
> - Meteo JSON and the metadata files have an envelope (`zaznamID`, `datumVytvoreni`) that changes with every generation: the same data give a different SHA-256 sum.

Based on the verified endpoints (research §3):

| Function | Source | URL pattern |
|---|---|---|
| `fetch_current(HYDRO, station_id)` | hydrology/now | `https://opendata.chmi.cz/hydrology/now/data/{WIGOS}.json` (10-min H/Q/T, appended every 1 h) |
| `fetch_current(WEATHER, station_id)` | climate/now | `.../meteorology/climate/now/data/10m-{WSI}-{YYYYMMDD}.json` and `1h-…` |
| `build_archive_urls(HYDRO, daily)` | historical | `.../hydrology/historical/data/daily/H_{WIGOS}_DQ_{ROK}.json` (likewise `HQ`, `MQ`, `MMQ`) |
| `build_archive_urls(WEATHER, …)` | climate/historical | `dly-{WSI}.json`, `mly-{WSI}.json`, per-element CSV in `historical_csv/` |
| `list_stations(HYDRO)` | metadata | `.../hydrology/now/metadata/meta1.json` (name, river, GEOGR1/2, SPA1–3 thresholds → `alert_levels`) |
| `fetch_warnings(…)` | alerts | `.../meteorology/weather/alerts/cap/alert_cap_50_*.xml` → `parsing/cap.py` |

Implementation decisions:

1. **`station_id` mandatory** for `fetch_current` and archives (WIGOS format) — ČHMÚ has no "whole country" endpoint. The facade does NOT emulate it with a loop over stations (hundreds of requests); a user who wants many stations iterates deliberately themselves or syncs them to the versioned store.
2. **Archive 404 = `ArchiveNotAvailableError`** (a subclass of `SourceDataError`) — archive depth differs per station; we do not probe automatically.
3. Times: ČHMÚ JSON carries the `Z` suffix — we parse it as UTC (the discrepancy with the PDF documentation is noted in the docstring).
4. CAP warnings: files of ~1–2 MB — streaming parser (`iterparse`), returns `Warning_` with CAP severity mapped directly.
5. `ProviderInfo`: CZ bbox (48.5–51.1 / 12.0–18.9), CC BY 4.0 license, ČHMÚ attribution, `archive_encoding="utf-8"`.
6. `parse_archive`: the ČHMÚ format (JSON with a `DT,VAL` table) → `ArchiveRecord` — a separate, simple parser (no ZIP/CSV).

---

## 7. ~~SQLite cache — schema v2~~ (SUPERSEDED — do not implement)

> **Superseded 2026-10-17 by the versioned store (ADR-001, release 3.0.0).** The SQLite cache was removed in 3.0.0 without shims; data is kept by a file-based store with immutable archive versions, `imgw-meta/1` sidecars, Parquet series (`imgw-series/1`) and the `imgw-plan/1` plan. Obserwator takes over this store instead of the database. The granularity problem described below (IMGW: "country year", ČHMÚ: "station year") is solved in the store by the provider's dataset descriptor (`archive_files` with per-station files) and the server path in the slot, not by `cached_ranges`. The content below is kept only as a historical record of the 2026-08-11 draft.

The cache is reproducible data — **no migration path from v1**: when a v1 schema is detected, the `db init --force` command (or a message with instructions) deletes and recreates it. This is a deliberate use of the permission to break contracts.

### Changes compared to v1

1. A `provider TEXT NOT NULL` column in all tables; it is part of all PKs/UNIQUEs/indexes.
2. The canonical time axis is **`measurement_date` (calendar date, ISO)** — the hydrological year (XI–X) is no longer a canonical column; the IMGW-specific `hydro_year`/`hydro_month` remain as auxiliary (nullable) columns, filled only by the IMGW provider. ČHMÚ does not use them.
3. Table names without the `hydro_` prefix where it is misleading; the interval vocabulary in `cached_ranges` switches to the English enum values.

```sql
stations (
    provider TEXT NOT NULL,
    station_id TEXT NOT NULL,
    kind TEXT NOT NULL,               -- hydro / weather
    name TEXT NOT NULL,
    river TEXT,
    latitude REAL, longitude REAL,
    alert_warning REAL, alert_alarm REAL,   -- thresholds (IMGW: warning/alarm; ČHMÚ: SPA2/SPA3)
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, station_id)
);

hydro_daily (
    provider TEXT NOT NULL,
    station_id TEXT NOT NULL,
    measurement_date TEXT NOT NULL,   -- YYYY-MM-DD, canonical
    water_level_cm REAL, flow_m3s REAL, water_temp_c REAL,
    hydro_year INTEGER, hydro_month INTEGER,   -- auxiliary, IMGW-only
    PRIMARY KEY (provider, station_id, measurement_date)
);

-- hydro_monthly, hydro_semi_annual: likewise (+ provider, + measurement_date/period)

cached_ranges (
    provider TEXT NOT NULL,
    interval TEXT NOT NULL,           -- Interval values (EN)
    year INTEGER NOT NULL,
    month INTEGER,
    station_id TEXT,                  -- NULL for country-wide sources (IMGW), required for per-station ones (ČHMÚ)
    param TEXT,
    source_url TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    UNIQUE (provider, interval, year, month, station_id, param)
);

schema_version (version INTEGER NOT NULL);   -- = 2
```

`cached_ranges.station_id` resolves the granularity difference: IMGW caches a "country year", ČHMÚ a "station year". `CacheManager.ensure_cached(query)` asks the provider for the range key (`query.cache_key()`), so lazy loading works identically for both models.

---

## 8. CLI

Entry point `obserwator`; the provider dimension as a global option `--provider/-P` (default `imgw`).

```bash
obserwator version
obserwator providers                              # NEW: list of providers + capabilities + licenses
obserwator server [--host] [--port] [--reload]

obserwator fetch hydro    -P chmi --station 0-203-1-001000 -i daily -y 2020 [-o out.json]
obserwator fetch weather  -P imgw -i monthly -s climate -y 2023
obserwator fetch current hydro   -P chmi --station 0-203-1-001000
obserwator fetch current weather -P imgw
obserwator fetch warnings --kind hydro -P chmi
obserwator fetch pmax --lat 52.23 --lon 21.01     # formerly pmaxtp; only providers with Capability.PMAX

obserwator list stations --kind hydro -P chmi [--search] [--limit]
obserwator list datasets -P imgw                  # what the provider offers (from capabilities + year ranges)
obserwator list intervals -P imgw

obserwator store init|info|scan|check|sync|catalog  # versioned store (counterpart of imgw store …; the former cache commands of §7 are superseded)
obserwator series build|export|select

obserwator admin keys|create|revoke|delete|stats  # no substantive changes
```

Renames: `fetch meteo` → `fetch weather`, `fetch current synop` → `fetch current weather`, `fetch pmaxtp` → `fetch pmax`, `-i`/`-s` values in English. CLI help texts in English (consistent with the API); messages may quote Polish IMGW file names where that helps.

---

## 9. REST API — v2

New prefix **`/api/v2`**; `/api/v1` is removed (consumers under control). The provider as a path segment — the resources are hierarchical, and capabilities differ between providers:

```
GET  /api/v2/providers                                  # list + capabilities + licenses
GET  /api/v2/{provider}/stations?kind=hydro&search=...
GET  /api/v2/{provider}/stations/{station_id}
GET  /api/v2/{provider}/current/hydro[?station_id=...]
GET  /api/v2/{provider}/current/weather[?station_id=...]
GET  /api/v2/{provider}/warnings?kind=hydro
GET  /api/v2/{provider}/archive/urls?kind=hydro&interval=daily&year=2020[&station_id=...]
GET  /api/v2/{provider}/series/...                      # store read (counterpart of /api/v1/store, /api/v1/series; requires a configured root)
POST /api/v2/imgw/pmax                                  # provider-specific endpoint (capability PMAX)
GET  /health
```

Rules:

1. A provider without a given capability → **404 with problem-details** (`{"type": "not-supported", "provider": "chmi", "capability": "pmax"}`).
2. Response schemas = the canonical models from §3.3 (one set of schemas for all providers; `provider` in every record).
3. We remove the 2.x placeholders (2 hard-coded stations in `routes/hydro.py`/`meteo.py`) — stations always come from the provider.
4. Year ranges in validation come from `provider.get_available_years()`, not from the static `ge=1951, le=2024`.
5. OpenAPI: tags per provider, capability descriptions in the endpoint description.

---

## 10. Web GUI

Minimal scope (the GUI is not a priority of the Obserwator release, but it must not lie):

1. Provider selector (IMGW/ČHMÚ) on the download and station pages; forms render fields according to capabilities (e.g. ČHMÚ archive → station field mandatory, no month choice).
2. Station pages and the map: data through the library facade (removal of the duplicated CSV parsing from `web/app.py`); markers with `provider` in the popup and license attribution in the map footer.
3. Map: layers per provider (Leaflet layer control); the ČHMÚ water state mapped from the SPA thresholds onto the same color scale as IMGW.
4. PMAXTP exports unchanged (an IMGW-only feature, hidden for other providers).

---

## 11. Removals and cleanup (full list)

| What | Why |
|---|---|
| `core/imgw_api.py`, `core/imgw_datastore.py`, `core/imgw_spatial.py` | legacy, broken imports, `wget`, Windows paths (~817 lines) |
| Duplicated station parsing in `web/app.py` | one implementation in the IMGW provider |
| Station placeholders in `api/routes/` | replaced by data from the provider |
| Root-level `urls.py`, `parsers.py` re-exports | replaced by the provider namespaces |
| Public `IMGW_ENCODING` constant | a property of the provider |
| Static `le=2024` in schemas | `get_available_years()` per provider |
| Two `HydroStation` classes | one canonical `Station` |
| `config.shapefile_path` (`polska.shp`) | dead after removing `imgw_spatial` |

---

## 12. Implementation plan (stages = separate PRs to `develop` (then `slave`))

| # | Stage | Verifiable result |
|---|---|---|
| 1 | Cleanup: removal of legacy `core/`, consolidation of duplicates | 2.x tests green, ruff/pyright clean |
| 2 | `parsing/csv_utils.py` + `http.py` (shared client) | parser tests pass after the move |
| 3 | `providers/base.py` + canonical models + registry | interface unit tests |
| 4 | IMGW provider behind the interface (the old public API still works internally) | 3.x tests rewritten/green |
| 5 | Rebranding: `obserwator` package, CLI, env, exceptions, EN facade | full test suite + CLI smoke test |
| 6 | ~~DB schema v2~~ — superseded by the 3.0.0 versioned store (ADR-001); the stage covers only the provider dataset descriptors in the store registry | store contract tests (`imgw-store/1` and related) on both granularity models |
| 7 | ČHMÚ provider (current, archives, stations, CAP) | tests on fixtures from real responses (respx) + an integration test (marked `@network`) |
| 8 | REST API v2 + Web GUI | endpoint tests, complete OpenAPI |
| 9 | Documentation: CLAUDE.md, README, PRD, ARCHITECTURE | consistent with the code |

Test requirements (RULES.md): coverage ≥ 80%; ČHMÚ fixtures downloaded from the real endpoints and frozen in `tests/fixtures/chmi/`; network tests separated by a marker, outside the default CI run.

---

## 13. Risks and open questions

| Risk / question | Mitigation / proposal |
|---|---|
| ČHMÚ: per-station granularity tempts a loop over hundreds of stations | explicit absence of "whole country" emulation in the facade; the documentation points to deliberate syncing of selected stations to the store |
| ČHMÚ: archive depth differs per station (404) | `ArchiveNotAvailableError` + store sync reports gaps per file (without aborting the whole run) |
| ČHMÚ: operational data unvalidated, corrections delayed | `provider` field + documentation; a correction = a new version in the store after a signal/content change |
| Time-zone inconsistency in the ČHMÚ docs (SEČ vs UTC) | we parse `Z` as UTC; an integration test guards the format |
| Renaming on PyPI (`obserwator` may be taken) | **to be checked before stage 5**; fallback: `obserwator-data` |
| Project repo/URLs after the rebranding | owner decision: rename the repo or only the package |
| Rate limiting towards opendata.chmi.cz | HTTP client: concurrency limit + jitter in store sync |
| Future DE/Baltic/SK providers | the §3.2 interface is designed for them (capabilities, per-station granularity, shared CAP parser) — no contract change |

---

## 14. Definition of done for the Obserwator release

1. `pip install obserwator` + `obserwator providers` shows IMGW and ČHMÚ with capabilities.
2. All 2.x functions have counterparts in the new API (mapping table in the README).
3. ČHMÚ: current hydro, daily/monthly archives, stations with SPA thresholds, CAP warnings — work and are covered by tests.
4. Zero references to the names `imgwtools`/`IMGW_` outside the IMGW provider and historical documentation.
5. Test coverage ≥ 80%, ruff + pyright clean, complete OpenAPI.
