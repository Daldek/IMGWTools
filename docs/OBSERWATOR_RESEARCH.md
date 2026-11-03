# Obserwator — feasibility study of extending beyond IMGW

**Study date:** 2026-08-11 · **Scope:** Slovakia (SHMÚ), Czechia (ČHMÚ), Germany (DWD/WSV), Baltic Sea
**Method:** analysis of the IMGWTools 2.1.1 code + web research with live endpoint verification (WebFetch).

---

## 1. Executive summary

Extending the library to neighboring countries is feasible, but the countries differ fundamentally in the maturity of their open data:

| Country / area | Current data | Hydro archives | Meteo archives | Stations (lat/lon) | Warnings | Overall rating |
|---|---|---|---|---|---|---|
| **Czechia (ČHMÚ)** | ✅ JSON per station | ✅ JSON per station/year | ✅ JSON + CSV | ✅ meta1.json | ✅ CAP XML | **Very good** — integrate first |
| **Germany (DWD+WSV)** | ✅ PEGELONLINE REST | ⚠️ state portals only | ✅ DWD CDC (from 1891!) | ✅ stations.json + TXT | ✅ CAP XML + LHP | **Good** — with a gap in hydro archives |
| **Slovakia (SHMÚ)** | ⚠️ HTML scraping only (hydro) | ❌ no open ones | ⚠️ "recent" CSV only | ⚠️ INSPIRE/metadata | ✅ Meteoalarm CAP | **Weak** — 2–4 years behind PL/CZ, watch |
| **Baltic** | ✅ tide gauges already in the IMGW API(!) + SMHI/BSH/EMODnet | ⚠️ PSMSL/EMODnet | n/a | ⚠️ varies | ⚠️ varies | **Good** — partly works already |

Key finding: **Polish tide-gauge stations (Świnoujście, Hel, Gdańsk, Kołobrzeg, Ustka, Władysławowo…) are already returned by `fetch_hydro_current()`** — the library "knows" Baltic data, it just does not expose it. They are, however, missing from `lista_stacji_hydro.csv`, so the current station list does not see them.

Common denominator of the region: **CAP XML as the warning format** (CZ, DE, SK via Meteoalarm) and **the "file server + predictable URLs" model** (ČHMÚ, DWD, SHMÚ open data) — exactly the philosophy of `url_builder.py`. The architecture carries over conceptually 1:1; the problem is the code, not the concept.

---

## 2. Current state of the library (findings from the code analysis)

### 2.1 What the library can do today

Three hard-coded URL bases (`url_builder.py:64-66`): archives `danepubliczne.imgw.pl/data/...`, current-data API `danepubliczne.imgw.pl/api/data`, PMAXTP `powietrze.imgw.pl/tpmax-api/point`. Public API: `fetch_hydro_current`, `fetch_synop`, `fetch_warnings`, `fetch_pmaxtp`, `download_hydro_data`, `download_meteo_data`, station lists, CSV parsers, URL builders — all IMGW-only.

### 2.2 What is generic (reusable without changes)

- **Current-data models** (`models.py`): neutral fields with units in the names (`water_level_cm`, `flow_m3s`); all IMGW specifics are enclosed in `from_api_response()` — a new country needs only a new mapper.
- **CSV parsers — the mechanics**: auto-detection of the delimiter, encoding (BOM), quotes — the same problems will occur in DWD data (semicolons, latin-1) and SHMÚ data.
- **SQLite layer** (`connection.py`), the `cached_ranges` pattern + lazy loading.
- **The `DownloadURL` dataclass**, the exception hierarchy, the split into extras in `pyproject.toml`, the test pattern (respx + fixtures).

### 2.3 What is tightly bound to IMGW (to refactor)

- `url_builder.py` — no "provider" abstraction at all; the enums play a double role: semantics + URL segment (`HydroInterval.DAILY = "dobowe"`).
- `fetch.py` — the bbox of Poland hard-wired in the module, "IMGW API..." error messages, HTTP boilerplate repeated 12× without a shared client/retry/User-Agent.
- **SQLite schema without a `provider` column** — the biggest single risk: SHMÚ/ČHMÚ/DWD station codes can collide with IMGW ones and overwrite data. A migration to v2 is required.
- The XI–X hydrological year as canonical columns (`hydro_year`/`hydro_month`) — marine data does not use it at all; it is better to canonicalize `measurement_date`.
- Public names: `IMGWError`, `IMGW_ENCODING`, the `IMGW_` env prefix, the `imgw` CLI, Polish strings in signatures (`interval="dobowe"`, `subtype="klimat"`).
- Debt to remove before the refactor: `core/imgw_api.py`, `core/imgw_datastore.py`, `core/imgw_spatial.py` (~817 lines of legacy, broken imports, `wget`, Windows paths); station parsing duplicated in 3 places (`stations.py`, `db/parsers.py`, `web/app.py`); placeholders in `api/routes/` (2 hard-coded stations); static `le=2024` in the API schemas.

---

## 3. Czechia — ČHMÚ (the best candidate)

Since 1.01.2025, Act 262/2024 Sb. has been in force, and the "National Hydrometeorological Database" = **https://opendata.chmi.cz** — a static file server with predictable URLs, **CC BY 4.0, no registration or key**. The model is identical to the IMGWTools philosophy.

### Hydro
- **Current** (verified live): `https://opendata.chmi.cz/hydrology/now/data/{WIGOS_ID}.json` — H (cm), Q (m³/s), water temperature, 10-min step, appended every hour. E.g. `0-203-1-001000.json`.
- **Last year**: `/hydrology/recent/`.
- **Archives** (verified): `/hydrology/historical/data/daily/H_{WIGOS}_DQ_{ROK}.json` (daily H/Q), also `HQ` (hourly), `MQ` (monthly), `MMQ` (maxima). A cleaner format than the IMGW ZIP+CSV. Archive depth varies per station (404 → probe).
- **Stations**: `/hydrology/now/metadata/meta1.json` — name, river, coordinates + **SPA1–3 flood degree thresholds** (the counterpart of IMGW warning/alarm levels).

### Meteo
- `/meteorology/climate/`: `now/` (10-min and 1-h JSON per station), `recent/` (daily `dly-{WSI}-{YYYYMM}.json`, monthly), `historical/` (station files for the whole measurement period; 10-min/1-h from 2018), `historical_csv/` (CSV per element). Station ID = WIGOS (e.g. `0-20000-0-11406`).

### Warnings
- CAP XML: `/meteorology/weather/alerts/cap/` — files of ~1–2 MB, whole country (ORP municipalities), CZ+EN, also cover hydro (SPA).

### Limitations
Per-station granularity (no "whole country at once" endpoint as at IMGW — fetching the state of the country = hundreds of requests); huge directory listings (construct file names, do not list); documentation in Czech in PDF; a minor time-zone inconsistency (PDF: SEČ vs actually UTC in JSON).

---

## 4. Germany — DWD + PEGELONLINE (good, with one gap)

### PEGELONLINE (WSV) — current hydro
REST API JSON (verified): `https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json` — ~660 stations with uuid, coordinates, river. Measurements: `.../stations/{id}/W/currentmeasurement.json` (with the `stateMnwMhw`/`stateNswHsw` state classification — the counterpart of `water_state` from hydro-back.imgw.pl), series `measurements.json?start=P15D`. Updated every 15 min, no registration, open license (DL-DE). **Note: only ~31 days back — this is not an archive.**

### DWD Open Data — meteo/climate
`https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/` — intervals from 1-minute to annual, data from **1891**. ZIP+CSV (semicolons, missing values `-999`), split into `historical/` + `recent/` (last ~500 days, daily). Station list in `*_Beschreibung_Stationen.txt` (fixed-width, latin-1). License CC BY 4.0 / GeoNutzV, no key. A catch for the url_builder: historical file names contain the series dates (`tageswerte_KL_00003_18910101_20110331_hist.zip`) — the directory listing has to be parsed once (analogous to the per-station synop problem at IMGW).

### Warnings
DWD CAP: `https://opendata.dwd.de/weather/alerts/cap/`. Flood: hochwasserzentralen.de (LHP) — JSON/GeoJSON webservices (status of ~1200 gauges, without measured values; a ready PyPI client `de-hochwasserzentralen`).

### Main gap: hydro archives
Multi-year archives of water levels/discharges (the counterpart of `codz_`/`mies_`) **have no federal source** — they are scattered across 16 state portals (e.g. GKD Bayern, gkd.bayern.de, CC BY 4.0, CSV export per station). GRDC (BfG) has long series, but research-only. Realistic v1 scope: DWD + PEGELONLINE + LHP; state archives as optional plugins (start with Bavaria).

**Prior art:** the `wetterdienst` library (github.com/earthobservations/wetterdienst) already implements DWD — worth reviewing before writing our own parser.

---

## 5. Slovakia — SHMÚ (the weakest, watch)

- **opendata.shmu.sk** (launched ~2025, modeled on the Czech one): a CSV file server, **CC BY 4.0, no key** — but mainly "recent" meteo (climate, precipitation, radar, air quality), **no hydro catalog and no deep history**.
- **Current hydro**: only HTML on shmu.sk (`?page=1&id=hydro_vod_all`) — scraping required; the site has outages (a day-long outage in January 2026).
- **Hydro archives**: not open — "Modrá platforma" (mp.shmu.dcmc.sk, CKAN CC0) is explicitly in beta: code lists + an application with 2018–2023 data, no documented API. Older series only on request/for a fee.
- **Warnings**: well covered via Meteoalarm (feeds.meteoalarm.org, ATOM/CAP, free).
- **Risk**: the planned target meteo REST API is to require registration and limits (~1000 requests/15 min).

**Recommendation:** in v1 only the opendata.shmu.sk module (CSV files) + Meteoalarm; mark hydro as experimental or postpone it until Modrá platforma matures.

---

## 6. Baltic Sea

### Poland — partly works already
- **IMGW tide gauges are in `api/data/hydro`** (verified: Świnoujście id 153140010, `stan_wody: 524 cm`, `rzedna_zerawodowskazu: -4.915` → sea level; also Hel, Gdańsk, Kołobrzeg, Ustka, Władysławowo, Gdynia, Puck, lagoon stations). A "sea" filter/module in the existing `fetch_hydro_current()` is enough.
- **But they are not in `lista_stacji_hydro.csv`** — the current station list does not show them; take them from the current-data API or hydro-back.imgw.pl. Whether tide gauges are present in the `codz_`/`mies_` archives — to be verified during implementation.
- baltyk.imgw.pl (MIKE21/SWAN forecasts, ice cover) — HTML/images only, no API. SatBałtyk, Maritime Offices (Urzędy Morskie) — no open API.
- Poland **does not publish open data on waves and salinity** — only CMEMS models or the neighbors' buoys.

### Abroad (ranking of fit to the "we generate links" model)
1. **SMHI (Sweden)**: `https://opendata-download-ocobs.smhi.se/api` — REST to CSV/JSON, parameters: sea level, T, salinity, waves, currents, with the full archive (`corrected-archive`). CC BY 4.0, no key. Exemplary.
2. **BSH (Germany)**: OGC API Features `https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast` — forecasts + water-level observations for the Baltic coast, JSON, CC BY 4.0, no registration. Raw measurements from German Baltic stations (Kiel, Warnemünde, Sassnitz…) — via PEGELONLINE.
3. **EMODnet Physics ERDDAP**: `https://erddap.emodnet-physics.eu/erddap/` — pan-European in-situ (NRT sea level 5/60-min, T, S, waves) + PSMSL (Świnoujście since 1811!); HTTP GET → CSV/JSON/NetCDF, no registration. Downside: performance, you need to know the PLATFORMCODE.
4. **FMI (Finland)**: WFS XML — open, but a heavier format.
5. **Copernicus Marine**: the richest (models, SST, reanalysis from 1993, in-situ from 1841), but requires an account and the `copernicusmarine` toolbox — an anonymous link cannot be generated. Possibly an optional `obserwator[cmems]` extra.
6. **IOC SLSMF**: open API, but no Polish stations. **HELCOM/ICES**: campaign data, file-based — not operational.

---

## 7. Recommended order of work

1. **Cleanup** — remove the legacy `core/imgw_api.py`, `imgw_datastore.py`, `imgw_spatial.py`; consolidate the 3× duplicated station parsing; fix the placeholders in `api/routes/`.
2. **DB schema v2** — a `provider` column in all tables and UNIQUE keys + a real migration (a precondition before any new country).
3. **Provider layer** — `providers/base.py` (Protocol: `list_stations`, `fetch_current`, `fetch_warnings`, `build_archive_url`, `parse_archive` + `ProviderInfo` with bbox, encoding, year ranges); move IMGW behind this interface **without changing the public API**; a shared HTTP helper (sync/async, retry, User-Agent).
4. **Provider #1: ČHMÚ** — the best value-to-effort ratio (JSON, CC BY 4.0, full feature range). Along the way: a shared CAP XML parser (will serve CZ, DE and Meteoalarm).
5. **Provider #2: Germany** — PEGELONLINE (current hydro) + DWD CDC (meteo archives) + CAP.
6. **Baltic module** — a tide-gauge filter in the existing IMGW API + SMHI + BSH; EMODnet as the pan-European source.
7. **Rebranding to Obserwator** — only after (3): `obserwator` package, `obserwator` CLI with an `imgw` alias, `ObserwatorError` with an `IMGWError` alias, `OBSERWATOR_` env with an `IMGW_` fallback.
8. **Slovakia** — last, minimal scope (opendata.shmu.sk + Meteoalarm), monitor Modrá platforma.

---

## 8. Key sources

**Czechia:** [opendata.chmi.cz](https://opendata.chmi.cz/) · [hydro now example](https://opendata.chmi.cz/hydrology/now/data/0-203-1-001000.json) · [daily archive 2020](https://opendata.chmi.cz/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2020.json) · [meta1.json](https://opendata.chmi.cz/hydrology/now/metadata/meta1.json) · [climate data description (PDF)](https://opendata.chmi.cz/meteorology/climate/Klimatologicka_data_popis.pdf) · [CAP](https://opendata.chmi.cz/meteorology/weather/alerts/cap/)

**Germany:** [PEGELONLINE stations.json](https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json) · [DWD CDC](https://opendata.dwd.de/climate_environment/CDC/) · [DWD daily/kl historical](https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/historical/) · [DWD CAP](https://opendata.dwd.de/weather/alerts/cap/) · [LHP developers](https://www.hochwasserzentralen.de/developers/) · [GKD Bayern](https://www.gkd.bayern.de/) · [wetterdienst (prior art)](https://github.com/earthobservations/wetterdienst)

**Slovakia:** [opendata.shmu.sk](https://opendata.shmu.sk/) · [SHMÚ gauges (HTML)](https://www.shmu.sk/sk/?page=1&id=hydro_vod_all) · [Modrá platforma](https://mp.shmu.dcmc.sk/) · [CKAN SHMÚ](https://opendata.shmu.dcmc.sk/en/dataset) · [Meteoalarm feeds](https://feeds.meteoalarm.org/)

**Baltic:** [IMGW api/data/hydro](https://danepubliczne.imgw.pl/api/data/hydro) · [SMHI ocobs](https://opendata-download-ocobs.smhi.se/api) · [BSH WaterLevelForecast](https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast) · [EMODnet ERDDAP](https://erddap.emodnet-physics.eu/erddap/) · [FMI WFS](https://opendata.fmi.fi/wfs) · [Copernicus Marine](https://data.marine.copernicus.eu) · [IOC SLSMF](https://www.ioc-sealevelmonitoring.org)
