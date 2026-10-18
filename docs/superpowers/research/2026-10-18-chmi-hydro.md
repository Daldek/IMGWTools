# ČHMÚ hydrology open data: live exploration (agent CzHydro)

**Date:** 2026-10-18, live window 17:08–17:26 UTC. **Base:** `B = https://opendata.chmi.cz/hydrology/`.

**How claims are marked**
- **V** = VERIFIED: I observed it live on 2026-10-18 at the URL given.
- **V-peer** = verified from a same-day capture saved by agent CzLegal under `/tmp/cz-explore/CzLegal/`.
- **U** = UNVERIFIED. Inferences are marked "U (inference)".

**Traffic:** 178 sequential requests, at least 0.4 s apart: 170 to opendata.chmi.cz, 7 to web.archive.org, 1 to www.chmi.cz. About 34 MB in total, of which 27.8 MB were directory listings. No errors other than the deliberate 404 probes.
**Samples, inventories and request log:** `/tmp/cz-explore/CzHydro/` (see §17).

---

## 1. Directory layout (URL patterns)

All entries **V**, from the nginx autoindex listings at the URLs shown.

| Path | Content |
|---|---|
| `https://opendata.chmi.cz/` | `air_quality/`, `hydrology/`, `meteorology/`. There is no licence or readme file. |
| `B` | `characteristic/ groundwater/ groundwater_quality/ historical/ now/ product/ read_me/ recent/ surface_water_quality/` and `hydrologicka_data_now_a_recent_popis.pdf` (689,544 B). |
| `B/now/data/{WIGOS}.json` | 546 files, e.g. `0-203-1-001000.json`. Size 1.5–20 KB; 6.59 MB for the whole snapshot. |
| `B/now/metadata/` | `meta1.json` (89,281 B: station list + thresholds), `meta2.json` (473 B: variable code list), `meta3.json` (269,843 B: extended station catalog). |
| `B/recent/data/{YYYYMMDD}_{WIGOS}.json` | One file per station per day. Listing by CzLegal at about 17:14 UTC (V-peer, `listing_hydrology_recent_data_.html`, 20.6 MB): 154,888 files, 2026-01-01..2026-10-17, 549 stations, 2.45 GB. |
| `B/recent/metadata/meta1-{YYYYMMDD}.json`, `meta2-{YYYYMMDD}.json` | Daily metadata snapshots. meta1: 717 files since 2024-10-21. meta2: 685 files since 2024-11-22. |
| `B/historical/data/<dir>/H_{WIGOS}_{CODE}_{YYYY}.json` | One file per station per calendar year. Ten flat directories (§5.1): `daily`=DQ, `hourly`=HQ, `monthly`=MQ, `monthly_max`=MMQ, `natural`=NATQ, `flowmeter`=OF, `measured_water_level`=OH, `measured_temperature`=OT, `morning_water_level`=OH7, `morning_temperature`=OT7. |
| `B/historical/metadata/` | `H_SCHEMA_{DQ,HQ,MQ,MMQ,NATQ,OF,OH,OH7,OT,OT7}.json` (JSON Schema 2020-12), `meta1.json` (154,554 B, 831 stations, Last-Modified 2026-02-06), `meta2.json` (16 variable codes). |
| `B/characteristic/data/` | `discharge_rating_curve/RC_{WIGOS}.json` (731 files, rewritten daily at 01:16); `hydrological_characteristic/{CHAR_MDQ,CHAR_MONQ,NY}_{WIGOS}.json` (1,217 files); `annual_peakflow/` (empty). |
| `B/product/data/` | `hydrological_yearbook/` (61 PDFs, 1.68 GB, 2004–2024 plus `2025_JH`); `gis_layer/` (`watersheds.gpkg` 705 MB, `surfacewater_monitoring_quantity.gpkg` 389 KB, …); plus `characteristic/ flash_flood/ groundwater/ report/ snow/`. |
| `B/read_me/` | `Popis_datovych_sad_historical.pdf`, `Popis_kodu_historical.pdf`, `Popis_kodu_now_a_recent.pdf`, `Popis_datovych_sad_characteristic.pdf`, `watersheds_attributies.pdf`, `Průvodce otevřenými daty hydrologie.pdf`. The last one is a single page linking to an ArcGIS StoryMap, which I did not open. |

- The year in historical file names is the calendar year. **V** (`B/read_me/Popis_datovych_sad_historical.pdf`): "RRRR v názvu datové sady označuje kalendářní rok".
- Historical directories are flat, with no per-station sub-folders: `daily/` holds 39,291 files. **V**
- The layout has changed before. A Wayback capture of `B/recent/data/` from 2024-09-21 shows a `10min/` subdirectory that no longer exists. **V** (`https://web.archive.org/web/20240921070507id_/https://opendata.chmi.cz/hydrology/recent/data/`)

## 2. Identifiers

- **Station id = WIGOS `0-203-1-{DBC}`.** DBC is "Databázové číslo stanice". **V**
  - Holds for every row of `now/metadata/meta1.json` (546), `meta3.json` (563) and `historical/metadata/meta1.json` (831). All file names use the WIGOS form.
  - DBC is 6 digits (`001000`) for most stations. There are 19 alphanumeric codes such as `CB110100`; these are stations operated by Povodí Vltavy, present in now/recent/meta3 but with no historical archive. **V**
- **Variable codes (`tsConID`)** — **V**, from `historical/metadata/meta2.json`, `now/metadata/meta2.json` and the schemas:
  - Operational (now/recent): `H` water level [CM], `Q` discharge [M3_S], `TH` water temperature [0C], `H_F` / `Q_F` model forecasts.
  - Historical:

    | Code | Meaning | Unit |
    |---|---|---|
    | `HD` / `QD` / `TD` / `PD` | daily mean water level / discharge / water temperature / suspended solids | CM / M3_S / 0C / G_M3 |
    | `HH` / `QH` | hourly mean water level / discharge | |
    | `QM` / `TM` | monthly mean discharge / water temperature | |
    | `QK` | monthly maximum (instantaneous) discharge | |
    | `QNEX` / `QNEY` | naturalised monthly discharge, including / excluding PZV influence | |
    | `HC` / `TO` | measured instantaneous water level / temperature | |
    | `HR` / `TR` | 07:00 morning readings | |
    | `QC` | flow-meter discharge | |

- **Units** are explicit per series (`"unit":"CM"|"M3_S"|"0C"|"G_M3"`), so they need not be inferred. **V**
- **Hydrographic code `HLGP4`** is "Hydrologické povodí IV. řádu". It is a hyphenated text string, `a-bb-cc-dddd`, e.g. `1-05-02-0720`. **V** (`B/read_me/Popis_kodu_historical.pdf`; `B/read_me/watersheds_attributies.pdf`: "a – Hlavní povodí (1 – Labe, 2 – Odra, 4 – Dunaj)"; the full ČHP is `a-bb-cc-dddd-e-ff-gg`).
  - Distribution in historical meta1: `1` = 449, `4` = 225, `2` = 154, empty = 3. **V**
  - Prefix filtering works per component (`1-05` is a sub-basin). U (inference from the documented hierarchy)
- **Station pages:** meta3 `WWW_CHMI` = `https://hydro.chmi.cz/hpps/pov/objekt/<seq>`. The `<seq>` is a different id from DBC. **V** (field value), page not fetched.

## 3. File formats (real samples)

### 3.1 Historical (every `historical/data/*` file)

Compact single-line JSON. **V** (`B/historical/data/daily/H_0-203-1-001000_DQ_2025.json`, 21,647 B):
```json
{"objID":"0-203-1-001000","tsList":[{"tsConID":"HD","unit":"CM","tsData":{"type":"DataCollection","data":{"header":"DT,VAL","values":[["2025-01-01T00:00:00Z",96],["2025-01-02T00:00:00Z",95],…]}}},{"tsConID":"QD","unit":"M3_S",…}]}
```
- The header is always `DT,VAL`, and each value row has exactly two items. There is no flag or quality column. **V** (all 10 `H_SCHEMA_*.json`; `values.items` has minItems = maxItems = 2)
- Only the variables a station has appear in `tsList`. A file can hold HD+QD, QD only, PD only, and so on. **V** (64 historical files parsed: 54 daily plus 10 from other directories)
- **Daily** rows are stamped `T00:00:00Z`. Exception: `PD` uses mostly `T18:00:00Z` (317 of 366 rows in `H_0-203-1-203050_DQ_2020.json`). **V**
- **Hourly**: `HH` / `QH` rows from `…T00:00:00Z` to `…T23:00:00Z`. **V** (`…/hourly/H_0-203-1-000400_HQ_2022.json`)
- **Monthly** (`QM`, `TM`, `QNEX`, `QNEY`): `DT` is the first of the month. **V**
- **Monthly max** (`QK`): `DT` is the time of the maximum, e.g. `["2025-03-29T23:20:00Z",4.82]`. **V** (`…/monthly_max/H_0-203-1-001000_MMQ_2025.json`)
- **OH / OT**: 10-minute steps, e.g. `HC` from `2021-10-20T10:10:00Z`, 10,451 rows, about 1.5 MB per full station-year. **V**
- **OF (flowmeter)**: one value per day at about 23:50Z. **V**

### 3.2 Operational (`now/data`, `recent/data`)

**V** (`B/now/data/0-203-1-001000.json`, `B/recent/data/20261017_0-203-1-001000.json`):
```json
{"objList" : [{"objID":"0-203-1-001000","tsList":[{"tsConID":"H","unit":"CM","tsData":[{"dt":"2026-10-18T00:00:00Z","value":93},{"dt":"2026-10-18T00:10:00Z","value":93},…]},{"tsConID":"Q","unit":"M3_S","tsData":[{"dt":"2026-10-18T00:00:00Z","value":0.63021},…]}]}]}
```
- The structure differs from historical: `objList` wrapper, and `tsData` is a list of `{dt,value}` objects rather than a DataCollection table. Note the space before the colon in `"objList" :`. **V**
- Forecast series appear inside the same file. Example from `B/now/data/0-203-1-004200.json`: `{"tsConID":"H_F","unit":"CM","tsData":[{"dt":"2026-10-18T05:00:00Z","value":18},…` — hourly, running to `2026-10-21T00:00:00Z`. **V**
  - Present only for `ISFORECAST=1` stations: 158 of 546. **V**
- The sampling step varies by station:
  - meta3 `SMPL_RATE` (minutes): 10 = 534 stations, 15 = 6, 60 = 5, 30 = 1, null = 17. **V**
  - `0-203-1-118300` showed 198 values by 16:25Z, i.e. a 5-minute step. **V**
- No `null` values appeared in 7 operational snapshots (6 URLs, 2,170 rows). **V** (sample)

### 3.3 Metadata files

**Envelope** — **V** (`B/now/metadata/meta1.json`):
```json
{"zaznamID":"5E2153F51CE369F4E064020820C987EB","datovyZdrojID":"hydrologie","datovyTokID":"Open.Data.Metadata","datumVytvoreni":"2026-10-18T17:00:03Z","verzeDat":"1.0","data":{"type":"DataCollection","data":{"header":"objID,DBC,STATION_NAME,STREAM_NAME,GEOGR1,GEOGR2,SPA_TYP,SPAH_DS,SPAH_UNIT,DRYH,SPA1H,SPA2H,SPA3H,SPA4H,SPAQ_DS,SPAQ_UNIT,DRYQ,SPA1Q,SPA2Q,SPA3Q,SPA4Q,ISFORECAST","values":[["0-203-1-001000","001000","Špindlerův Mlýn","Labe",50.7231692,15.5980379,"H","vodní stav","CM",90,165,200,220,297,"průtok","M3_S",0.419,19.3,39.4,54.5,137,0],…
```
- **`historical/metadata/meta1.json` header** (23 columns): `objID,DBC,STATION_NAME,STREAM_NAME,GEOGR1,GEOGR2,SPA_TYP,SPAH_DS,SPAH_UNIT,DRYH,SPA1H..SPA4H,SPAQ_DS,SPAQ_UNIT,DRYQ,SPA1Q..SPA4Q,PLO_STA,HLGP4`. **V**
- **`now/metadata/meta3.json` header** (47 columns, undocumented in `read_me`): `objID,DBC,PRF_ID,KATEGORIE,STATION_NAME,CEVT,STREAM_NAME,POB,PROVOZOVATEL,GEOGR1,GEOGR2,WGS_ELE,HLGP4,RICKM,PLO_STA,PLO_STA_PROC,HA,QA,SPA_TYP,…,SPA4Q,Q1,Q5,Q10,Q50,Q100,SPA1_CETN,SPA2_CETN,SPA3_CETN,SPA_USEK,SPA_KMISTO,POPIS_UP,SMPL_RATE,WWW_CHMI,WWW_EL`. **V**
- **Threshold semantics** — **V** (`B/read_me/Popis_kodu_historical.pdf`, `B/hydrologicka_data_now_a_recent_popis.pdf`):
  - `SPA1H..SPA3H` and `SPA1Q..SPA3Q` = "Vodní stav / Průtok úrovně 1.–3. SPA" (flood activity degree).
  - **`SPA4H`/`SPA4Q` = "Vodní stav úrovně 50letého průtoku"**: the level of the 50-year flow. This is **not** a fourth flood degree.
  - `DRYH`/`DRYQ` = drought limit.
  - `SPA_TYP` says which of H or Q defines the SPA levels: H = 522, Q = 24 in now meta1. **V**
  - Thresholds are often null, e.g. `SPA1H` null for 127 of 546. **V**
  - The SPA names (bdělost / pohotovost / ohrožení) and their mapping to IMGW warning/alarm levels are **U**.

## 4. Station metadata / catalog sources

| Source | Stations | Coordinates | Extras | Refresh |
|---|---|---|---|---|
| `now/metadata/meta1.json` | 546 (active network) | GEOGR1 = lat, GEOGR2 = lon; all present | thresholds, `ISFORECAST` | rewritten hourly at :01 (V) |
| `now/metadata/meta3.json` | 563 (546 + 17) | yes | KATEGORIE A/B/C (211/181/169), operator, `WGS_ELE`, `RICKM`, `PLO_STA`, `HA`, `QA`, Q1..Q100, `SMPL_RATE`, gauge location text | rewritten daily at about 02:03 (V) |
| `historical/metadata/meta1.json` | 831 (includes closed stations) | 7-decimal for 745 stations; none 0 or null; lat 48.6255–50.9782, lon 12.3758–18.8926 | `PLO_STA`, `HLGP4`, thresholds | last 2026-02-06 (V) |
| `characteristic/metadata/discharge_rating_curve/meta1.json` | 731 | yes | same columns as historical meta1 | daily at 01:18 (V) |
| `product/data/gis_layer/surfacewater_monitoring_quantity.gpkg` | 554 `water_gauges`, EPSG:32633 | geometry | `nm, tok_nm, plo_sta, qd/td/pd (ano/ne), id, WIGOS_ID` | 2026-01-23 (V) |

All rows **V** at the paths shown.

**Coordinate reference system.** The NKOD record for the daily dataset says `conformsTo EPSG:4326`. **V-peer** (`nkod_hydro_daily_ds.csv`)

**Set relations** (all **V**):
- All 803 daily-archive stations appear in historical meta1.
- 28 historical meta1 stations have no daily files.
- 41 stations in now meta1 have no daily archive, including the 10 CB… stations.
- 251 archive stations end before 2025 (closed).

**The sources disagree** (all **V**):
- Comparing now meta1 with historical meta1 over 506 common stations, coordinates differ:

  | Distance | Stations |
  |---|---|
  | identical | 92 |
  | < 10 m | 337 |
  | < 50 m | 64 |
  | < 200 m | 7 |
  | ≥ 200 m | 6 (max 1,631 m, `0-203-1-121000` Kosky - Hamr) |

- Names differ for 69 stations, e.g. `0-203-1-381000` "Bystřička pod nádrží" vs "VD Bystřička".
- Some thresholds differ too.

**Not published anywhere** (U, because absence cannot be proven): gauge-zero elevation, station founding year, an active/closed flag, the station's position in a list order.
- `WGS_ELE`, `HA`, `QA` and `RICKM` are not in the code PDFs. Their meanings (elevation, mean level, mean flow, river km) are **U (inference)**.

## 5. Time coverage and archive depth

### 5.1 Inventory

**V**, from full listings of every `B/historical/data/<dir>/` fetched 2026-10-18; gzip copies are saved.

| Dir (code) | Series | Files | Stations | Years | Median first year | Stations with 2025 | Total size |
|---|---|---|---|---|---|---|---|
| daily (DQ) | HD QD TD PD | 39,291 | 803 | 1887–2025 | 1961 | 552 | 604.6 MB |
| hourly (HQ) | HH QH | 12,358 | 574 | 1905–2025 | 2004 | 543 | 5.87 GB |
| monthly (MQ) | QM TM | 39,081 | 791 | 1887–2025 | 1960 | 542 | 21.8 MB |
| monthly_max (MMQ) | QK | 24,957 | 691 | 1919–2025 | 1975 | 537 | 12.2 MB |
| natural (NATQ) | QNEX QNEY | 22,929 | 675 | 1979–2025 | 1979 | 537 | 22.7 MB |
| measured_water_level (OH) | HC 10-min | 16,397 (20 junk, §15) | 624 | 1925–2025 | 1994 | 542 | 12.3 GB |
| measured_temperature (OT) | TO 10-min | 3,453 | 275 | 2004–2025 | 2011 | 209 | 4.17 GB |
| morning_water_level (OH7) | HR | 591 | 27 | 1954–1990 | 1970 | 0 | 5.8 MB |
| morning_temperature (OT7) | TR | 8,415 | 252 | 1897–2025 | 1965 | 1 | 84.7 MB |
| flowmeter (OF) | QC | 49 | 5 | 2009–2025 | 2011 | 3 | 49.1 MB |

### 5.2 Daily archive depth per station

All **V**. A per-station table is in `inventory_daily_per_station.csv`.

- First year by decade:

  | 1880s | 1890s | 1900s | 1910s | 1920s | 1930s | 1940s | 1950s | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s | 2020s |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | 1 | 2 | 5 | 40 | 54 | 55 | 75 | 149 | 104 | 83 | 62 | 66 | 46 | 38 | 23 |

- Years per station: minimum 1, median 47, maximum 139. The longest is `0-203-1-240000` Děčín (Labe), 1887–2025.
- **102 stations have whole years missing inside their span.** Examples:
  - `0-203-1-001000` Špindlerův Mlýn: 1919–1926, then 1988–2025.
  - `0-203-1-098000` Bakov nad Jizerou: 30 files across 1941–2025.
- A missing year returns 404 (`H_0-203-1-001000_DQ_1950.json` → 404 text/html, 153 B). **V**
- Many first files start on 1 November, e.g. the `…001000_DQ_1919` file runs 1919-11-01..12-31. Also `…061000_DQ_1991` HD and `…045000_DQ_2004` HD start on 11-01.
  - This points to a hydrological year of XI–X, as in Poland. **U (inference)**
- The 2025 daily data is 552 files, 14.2 MB. 2024 is 556 files, 14.4 MB. **V**

### 5.3 Per-variable coverage: H is much shorter than Q

- **V** for `0-203-1-075000` Sány (Cidlina):
  - `…DQ_1990.json` = QD only.
  - `…DQ_1995.json` = QD only.
  - `…DQ_2004.json` = QD all year plus HD and PD from 2004-11-01.
- The size pattern in the full listing (QD-only year ≈ 11 KB; HD+QD ≈ 21 KB) shows the same thing network-wide. Of 453 stations with files in 1992, 1997 and 2006, **405 have two series in 1992, one in 1997 and two in 2006**.
  - So validated daily H mostly exists only for about XI 1991–1994 and from XI 2004 onward, while Q runs continuously. **U (inference from sizes, plus 3 stations content-checked)**
- Temperature (TD) and suspended solids (PD) are rare: 3 of 45 random files each. **V** (sample)

### 5.4 Gaps within a year

- Missing days are absent rows. Examples, all **V**:
  - `…414700_DQ_2024`: HD and QD missing 2024-06-01..11-30.
  - `…199200_DQ_2022`: HD stops 2022-03-30 while QD is complete.
  - `…171000_DQ_2002`: QD has a 123-day gap.
- H and Q start on different days, e.g. `…000400_DQ_2021`: HD from 10-20, QD from 10-21. **V**

### 5.5 Operational retention

- `now` holds only the current UTC day, 00:00Z up to the latest reading. **V**
- `recent` today holds only the current calendar year (starts at `20260101_*`). `20251231_0-203-1-001000.json` and `20250101_…` both return 404. **V**
- Retention used to be longer. Wayback listings from 2025-06-18 and 2025-11-16 still begin with `20240604_*` files, so recent then held more than a year. **V** (web.archive.org captures 20250618020635 and 20251116212004)
  - When the 2024–2025 files were purged is **U**. So is whether 2025 data was briefly unavailable between the purge and the historical publication on 2026-05-21.
- `recent/metadata` snapshots are kept since 2024-10-21. **V**

## 6. Validated vs operational

- **now / recent** are operational, unvalidated data. **V** (`B/hydrologicka_data_now_a_recent_popis.pdf`):
  - "aktuálně naměřených a nevalidovaných dat … mohou být tato data zatížena chybami – ovlivněním stavebními pracemi v korytě nebo výskytem ledových jevů".
  - recent: "Tato data se následně kontrolují a validují. Po uplynutí jednoho kalendářního roku jsou postupně nahrazena daty historickými. Data … se tak mohou částečně lišit od dat historických."
  - In practice recent files are never rewritten after validation: all 154,888 have mtime = day + 1. **V-peer** (listing)
- **historical** is validated. NKOD title: "Množství povrchových vod – **ověřené údaje** – průměrné denní vodní stavy, průtoky, teploty vody a koncentrace plavenin". Its description says HD is computed "z verifikované řady měřených okamžitých vodních stavů" and QD "odvozovány z průměrných hodinových průtoků". **V-peer** (`nkod_hydro_daily_ds.csv`, dataset `https://data.gov.cz/zdroj/datové-sady/00020699/7dedcbb58e2edbea533b0b4cca445e43`)
- The legal split matches this. Law 262/2024 Sb. §2 b) "hydrometeorologické údaje" = direct network output; §2 c) "ověřené … po realizaci procesu kontroly a kontroly kvality"; §9(3) = open data. **V-peer** (`zakon_262_2024.txt`; source URL not verified by me)
- **Consistency check:** daily QD equals the mean of the 24 hourly QH values labelled 00–23Z of that date. Mean absolute difference 0.00025 m³/s, against 0.00156 for a CET-shifted day. **V** (`…000400_DQ_2021` vs `…000400_HQ_2021`, 72 days)

## 7. Update cadence and HTTP headers

| File class | ETag | Last-Modified | Content-Length | Observed cadence |
|---|---|---|---|---|
| `now/data/*.json` | yes | yes | yes | Rewritten every **20 min** (:00 / :20 / :40 seen 16:20–17:20 UTC), and only when new data arrived; laggards last updated 14:20 or 15:20. The PDF says "jedenkrát za hodinu". Latency about 10 min: written 17:20:09, last `dt` 17:10Z. **V** |
| `now/metadata/meta1,meta2` | yes | yes | yes | Hourly at about :01. A new `zaznamID` and `datumVytvoreni` every time, even when `data` is unchanged. **V** (`recent/metadata/meta1-20261016.json` vs `-20261017.json`: only those two keys differ) |
| `now/metadata/meta3` | yes | yes | yes | Daily at about 02:03 UTC. **V** |
| `recent/data/*` | yes | yes | yes | Written once, at day + 1 00:20 UTC; never rewritten. **V / V-peer** |
| `recent/metadata/*-YYYYMMDD` | yes | yes | yes | Daily at 23:01 UTC. **V** |
| `historical/data/**` | yes | yes | yes | **Annual, plus ad-hoc fixes** (below). **V** |
| `characteristic/.../RC_*` | yes | yes | yes | Daily at 01:16. **V** |
| Directory listings (autoindex) | **no** | **no** | **no** (chunked) | Entries show mtime (UTC, minute precision; matches Last-Modified) and size in bytes (matches Content-Length). **V** |

**Historical publication pattern** (all **V**, from listing mtimes):
- **2025 data**: all files in every directory are stamped 2026-05-21 (daily at 11:19, others 13:2x).
- The NKOD record states "aktualizace … jednou ročně … do konce dubna roku následujícího" (**V-peer**). The 2025 release was therefore about three weeks late.
- **Full regeneration on 2025-07-01..03**: every pre-2025 file carries those mtimes. The reason is **U**.
- **Ad-hoc fix on 2026-02-06 10:55**: 6 files of `0-203-1-456505` (2012–2017) in daily, hourly, monthly, monthly_max and natural, plus `historical/metadata/meta1.json` at 11:08.

**HTTP behaviour** (all **V** on `B/historical/data/daily/H_0-203-1-001000_DQ_2025.json`):
- **ETag is nginx-style `"<hex mtime>-<hex size>"`**: `"6a0eea27-548f"` decodes to 2026-05-21T11:19:03Z and 21,647 B. It changes on any rewrite, even when the content is identical; it is not a content hash.
- `If-None-Match` and `If-Modified-Since` → 304.
- `Range: bytes=0-99` → 206.
- No `Content-Encoding` even when gzip is requested, so the body is byte-identical to the file.
- `Content-Type: application/json` with no charset; no `Cache-Control` or `Expires`.
- `http://` → 301 to `https://`.

## 8. Sizes and request counts

All **V** (from listings):
- **Daily:** 2–33 KB per station-year (QD-only full year ≈ 11 KB; HD+QD ≈ 21.6 KB; +TD ≈ 32 KB). One country-year (2025) = 552 GETs / 14.2 MB. The full archive = 39,291 GETs / 605 MB.
- **Hourly:** about 0.5 MB per station-year; 2025 = 543 files / 275 MB.
- **OH:** about 1.5 MB per station-year.
- **now** snapshot: 546 GETs / 6.6 MB.
- **recent** day: about 545 files / about 8.6 MB.
- **Listings:** daily 5.27 MB, monthly 5.24 MB, monthly_max 3.37 MB, natural 3.12 MB, measured_water_level 2.20 MB, hourly 1.66 MB, morning_temperature 1.14 MB, recent 20.6 MB (V-peer). There is no server-side filtering, so the whole listing must be downloaded.

## 9. Encoding, numbers, time

- **Encoding:** UTF-8 without BOM. All saved JSON decodes; Czech diacritics appear, e.g. "Špindlerův Mlýn". **V**
- **Numbers:** JSON ints and floats are mixed within one series (e.g. QD: 364 floats and 1 int). H is an int in HD but a float in OH and now (e.g. `13.9`). Precision is up to 4 decimals in MQ and 5 in now Q. **V**
- **Time zone (corrects OBSERWATOR_RESEARCH):** every timestamp carries `Z`.
  - The PDF says "Je uvedeno datum a čas [SEČ a SELČ]".
  - **now/recent are true UTC** (**V**):
    - The now file written 17:20:09 UTC ends at `17:10:00Z`; CEST labels would be in the future.
    - recent day files cover 00:00Z–23:50Z and are written at 00:20 UTC.
  - **Historical** labels show no DST artefacts: 24 hourly values every day, including 2022-03-27 and 2022-10-30, with no duplicates (`…000400_HQ_2022`). **V**
    - Whether they are UTC or a fixed CET offset is **U**.

## 10. Missing values and flags

- **No flags of any kind** in any hydrology data file (historical `DT,VAL`; operational `dt/value`). **V** (schemas, plus 64 historical files and 7 operational snapshots)
  - No ice, estimated or provisional markers. Operational errors (ice, construction) go unflagged, per the PDF quote in §6.
- **Missing data = absent rows, or absent series in a file, or absent whole files.** No sentinel codes, and no nulls or malformed rows in 64 historical files (≥46,580 rows checked in the 20 saved files, plus 45 random daily files) or in 7 operational snapshots. **V** (sample)
  - Whether this holds for every file is **U**.
- **Operational outages:** no recent files exist for 2026-08-23 or 2026-08-27..29 (404 confirmed for `…_0-203-1-001000.json`). 2026-08-30 starts at 00:50Z. Nothing was backfilled. **V**

## 11. Whole-country bundles

**None for observation data.** **V**:
- All 10 historical directories were listed in full. They contain only `H_{WIGOS}_{CODE}_{YYYY}.json`, plus 20 junk OH names.
- now and recent are one file per station.
- `B`, the root, `characteristic/` and `product/` were listed; there are no zip, tar or gz files.
- The NKOD distributions for the daily dataset point only at the directories `B/historical/data/daily/`, `B/historical/metadata/` and `B/read_me/` (**V-peer**, `nkod_hydro_daily_dists.csv`).

The only country-wide artefacts are:
- the yearbook PDFs (`B/product/data/hydrological_yearbook/hydroyearbook{YYYY}.pdf`, 100–250 MB each);
- the GIS layers (`watersheds.gpkg` 705 MB, whose `dbcn` field links catchments to stations per `watersheds_attributies.pdf`; `surfacewater_monitoring_quantity.gpkg`).

## 12. Licence and attribution

- **Quote**, from `https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti` (**V**, 17:25 UTC): "Produkty Českého hydrometeorologického ústavu dostupné na těchto webových stránkách podléhají licenci Creative Commons 4.0 CC-BY. Dílo smíte sdílet a upravovat za podmínky uvedení původu (zdroje ČHMÚ)." The page links to `https://creativecommons.org/licenses/by/4.0/deed.cs`.
- **NKOD**: the hydro daily dataset's terms of use give the author licence `https://creativecommons.org/licenses/by/4.0/`. It is an EU High-Value Dataset (Reg. 2023/138). **V-peer** (`nkod_hydro_daily_dists.csv`, `nkod_hydro_daily_ds.csv`)
  - CC BY-NC-ND appears in NKOD only for a meteo station GeoPackage on geoportal.gov.cz (**V-peer**, `nkod_bync_nd.csv`), not for hydrology.
- **No licence or attribution text** exists in opendata.chmi.cz listings or in the JSON files. **V**
- The exact attribution wording a sidecar `license.attribution` should carry is **U**; it is CzLegal's scope.

## 13. Robots, rate limits, CORS

All **V**:
- `https://opendata.chmi.cz/robots.txt` → 404.
- Server: `nginx/1.22.1`.
- No rate-limit headers, no `Retry-After`, and no 429 or 503 across 170 requests (about 2 requests/s at peak; median small GET 0.23 s).
- **No CORS headers** (a GET with `Origin` returned none), so browser-side cross-origin fetches will fail.
- No authentication or keys required.

## 14. Gaps against the Archiwista contract (`Archiwista/docs/wymagania-imgwtools.md`)

| Req | What the contract needs | ČHMÚ hydro fact | Gap / implication |
|---|---|---|---|
| IMGW-1/-4 slots, `archive_files` without network | file list derivable offline; byte-for-byte storage under the server path | Slot path fits naturally: `hydrology/historical/data/daily/H_{WIGOS}_DQ_{YYYY}.json`, served uncompressed (V). | **The file set cannot be derived offline.** Station × year sets have holes (102 stations with missing years; 28 stations with no daily files; H/Q/T presence varies). Needs an inventory from listings (5.3 MB for daily; 28 MB for all historical) or a shipped snapshot. Flat directories of up to 39k files would also be flat in the store, which hurts SMB listing. |
| IMGW-3 sidecar | `license{id,attribution,url}`; `extra.http{url,etag,last_modified,content_length}` | All 4 HTTP fields present on every file (V). | Attribution formula still to be fixed (CC BY 4.0, "uvedení původu (zdroje ČHMÚ)"). `country` = CZ, `provider` = ČHMÚ. |
| IMGW-5 `check_store` via HEAD only; statuses `current/newer/missing/unverifiable` | per-file ETag / Last-Modified | Present; 304 supported (V). | 39k HEADs are impractical; use listing (mtime + size) as the signal. **Mass regenerations change every ETag** (2025-07-01), so expect a re-download of 605 MB ending in `relabeled`. A listing cannot detect a same-minute, same-size rewrite. 404 for a gap year is normal (not `check_failed`), so the inventory must separate "never published" from "failed". |
| IMGW-6 parsers / flags | no source codes in values; flags `missing` / `no_phenomenon` / `accumulated` | No sentinels, no flags (V). | Only `value` and `missing` apply (missing = absent row). Parser must coerce int/float, truncate PD 18:00Z stamps to the date, and treat MMQ `DT` as the time of the maximum. CP1250/delimiter detection is not needed (UTF-8 JSON). |
| IMGW-7 continuous calendar + `hydro_year` | one row per day from first to last record | Rows only for days with values (V). | Must densify. Files are calendar years while the hydrological year (XI–X, U inference) spans two files. Station starts on 1 Nov produce Nov–Dec-only files. |
| IMGW-8 per-variable coverage | exact gap lists per H, Q, T | Separate series per variable (V). | Feasible and necessary: H has a roughly 10-year hole (1995–X 2004) at most stations while Q is continuous (§5.3). TD is rare. |
| IMGW-9 station catalog | code as text, river, hydrographic code, list order, lon/lat or reason, active/historical, founding year, gauge zero, river km | WIGOS / DBC, name, river, lat/lon for all 831, HLGP4, PLO_STA; meta3 adds `RICKM` and `WGS_ELE` for active stations only (V). | Code is **not 9 digits**: DBC is 6 characters and some are alphanumeric (`CB…`). No list order; no founding year (only first archive year); **no gauge zero** (`WGS_ELE` semantics U). Active/closed must be derived. Coordinates are 7-decimal (150 m uncertainty floor) but **differ between sources by up to 1.6 km**, so a precedence rule is needed. Bbox does not prove "inside CZ": 4 stations are run by the Lower Austria authority (U whether located in AT). |
| IMGW-9 sources and `extra.catalog.sha256` | sha of each source response | meta1 / meta3 regenerate hourly / daily with a new `zaznamID`/`datumVytvoreni` (V). | The response sha changes every hour with no data change; content-based dedupe must ignore the envelope. |
| Dataset scope (SPEC 4.8) | hydro daily H/Q/T, monthly, semi-annual/annual | DQ: HD/QD/TD; MQ: QM, TM means only; MMQ: QK max with timestamp (V). | **No monthly H, no monthly minima, no semi-annual/annual extremes.** `CHAR_*`/`NY_*` are long-term characteristics, not equivalents. |
| R9 offline fixtures | recorded responses | Files are small JSON (V). | Easy to record; no special issues. |
| R11 nothing silently | every station / series reported with a reason | — | CB… stations (19) have no validated archive and 41 now-stations have no daily archive; report them explicitly. Operational outage days must surface as `missing`. |

## 15. Gotchas

1. The PDF says times are SEČ/SELČ, but the data is UTC (operational verified; historical has no DST shifts).
2. Calendar-year files against a XI–X hydrological year; many partial years start on 1 November.
3. Holes in station-year sets: building URLs and probing produces 404s. Use listings. The research doc's advice to "build names, don't list" fails for archives.
4. **Junk files:** 20 cumulative names such as `H_0-203-1-206200_OH_1980_1981_…_2000.json` (dated 2025-02-13, never cleaned up). Match file names strictly with `H_(0-203-1-[0-9A-Z]+)_(CODE)_(\d{4})\.json`.
5. Forecast series (`H_F`, `Q_F`) sit inside now files next to observations; filter by `tsConID`.
6. Mixed sampling steps in now (5/10/15/30/60 min).
7. Operational whole-day outages, not backfilled; retention and layout of recent changed over 2024–2026.
8. ETag is mtime + size, so bulk regenerations invalidate everything. Metadata envelopes change hourly.
9. Station metadata differs across meta1 (now), meta3, historical meta1 and the rating-curve meta1 (names, coordinates, thresholds).
10. `SPA4*` is the Q50 level, not a flood degree. Many thresholds are null.
11. Validated daily H is largely missing for 1995–X 2004; Q continues.
12. No compression, and listings run 2–20 MB each: hourly is 5.9 GB and OH 12.3 GB for a full mirror.
13. The 2025 annual release came after the NKOD-stated April deadline (2026-05-21).
14. No CORS, so a Web GUI cannot fetch client-side.
15. JSON style differs between data families (`"objList" :` with a space vs compact historical). Parse it; never pattern-match the raw text.

## 16. Open questions (all U)

- Historical timestamps: UTC or fixed CET?
- Date of the recent-year purge relative to historical publication; was there an availability gap for 2025 data in Jan–May 2026?
- Semantics of `WGS_ELE`, `HA`, `QA`, `RICKM`, `CEVT`, `PRF_ID`. Is gauge-zero elevation published anywhere?
- Can nulls or sentinels appear in any historical file (I sampled 64 of about 167k)?
- How often are past years rewritten in place (seen once, `456505`)?
- SPA degree names and their mapping to IMGW warning/alarm.
- Official definition of the ČHMÚ hydrological year.
- Required attribution text (see CzLegal).

## 17. Artifacts (`/tmp/cz-explore/CzHydro/`)

- **Raw samples:** `now_meta{1,2,3}.json`, `hist_*.json` (schemas, historical meta1/meta2), `now_0-203-1-*.json`, `recent_*.json`, 20 `H_*_{DQ,HQ,MQ,MMQ,NATQ,OF,OH,OH7,OT,OT7}_*.json`, `surfacewater_monitoring_quantity.gpkg`.
- **Docs:** PDFs from `read_me/` with `.txt` extractions.
- **Listings:** `ls_*.html(.gz)`, full gzip listings of all historical directories.
- **Inventories:** `inventory_daily_per_station.csv` (803 rows), `inventory_summary_all_datasets.json`.
- **Request log:** `request_log.json` (every request with headers).
