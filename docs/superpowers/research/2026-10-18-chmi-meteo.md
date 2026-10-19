# ČHMÚ meteorology open data: live exploration for an IMGWTools `cz.chmi.*` provider

**Agent:** CzMeteo · **Run:** 2026-10-18, 17:08–17:28 UTC · 173 sequential HTTP requests (≥0.5 s apart), 22.9 MB downloaded in total (range reads for large files).
**Raw samples and notes:** `/tmp/cz-explore/CzMeteo/` (listings `*.html`, JSON/CSV/XML samples, `requests.log`, `summary.json`).

**Tags.** **[V]** = VERIFIED live on 2026-10-18 at the URL given (base `$O` = `https://opendata.chmi.cz`, `$C` = `$O/meteorology/climate`). **[I]** = inference from verified data. **[U]** = UNVERIFIED.

---

## 1. Directory layout (verified URL patterns)

```
$O/                               air_quality/  hydrology/  meteorology/                       [V $O/]
$O/meteorology/                   climate/ floods/ phenology/ products/ weather/              [V]
$C/Klimatologicka_data_popis.pdf  official format description (CZ), 636 186 B, LM 2025-07-28 [V]
$C/now/data/                      10m-{WSI}-{YYYYMMDD}.json, 1h-{WSI}-{YYYYMMDD}.json         [V]
$C/now/metadata/                  meta{1..4}-{YYYYMMDD}.json                                   [V]
$C/recent/data/{10min,1hour}/     day files for the current month at the root: {10m|1h}-{WSI}-{YYYYMMDD}.json
                                  MM/ (01..12, rolling 12 months): {10m|1h}-{WSI}-{YYYYMM}.json       [V 1hour root, 1hour/09, 10min/09]
$C/recent/data/daily/             dly-{WSI}-{YYYYMM}.json (current month at root; previous 12 months in MM/)  [V]
$C/recent/data/{monthly,pentadic}/ only MM/ subdirs at the root                               [V]
$C/recent/data/phenomena/         ph-{WSI}-{YYYYMM}.json (+ MM/)                               [V]
$C/recent/metadata/               meta{1..4}-{YYYYMMDD}.json (current month) + MM/meta{1..4}-{YYYYMM}.json  [V]
$C/historical/data/daily/         dly-{WSI}.json (one file per station: all elements, all years)   [V]
$C/historical/data/monthly/       mly-{WSI}.json ; yearly/ yrs-{WSI}.json ; pentadic/ ; phenomena/  [V monthly, yearly]
$C/historical/data/{10min,1hour}/ {YYYY}/ (2018..2025) / {10m|1h}-{WSI}-{YYYYMM}.json          [V]
$C/historical/metadata/           meta1.json (659 KB) meta2.json (9.66 MB) meta3.json meta4.json [V]
$C/historical_csv/data/daily/{group}/  dly-{WSI}-{ELEMENT}.csv  (one file per station × element)  [V]
     groups: air_pressure cloudiness evaporation humidity precipitation radiation snow
             soil_temperature sunshine temperature wind                                      [V]
$C/historical_csv/data/{10min,1hour,monthly,yearly,phenomena}/  per-group dirs                [V 10min]
$C/historical_csv/metadata/       meta1.csv meta2.csv meta3.csv meta4.csv                      [V]
$O/meteorology/weather/alerts/cap/       alert_cap_50_{DDHHMM}.xml, alert_cap_70_{DDHHMM}.xml   [V]
$O/meteorology/weather/alerts/metadata/  Dokumentace_CAP.pdf (CAP v1.2 profile, 2018)          [V]
$O/meteorology/products/           climate_normal_stations/ grids_CZ/ regional_averages/ yearbooks/ [V]
```

- **The PDF does not match the server [V].** The PDF documents `historical/data/10min` and `1hour` as flat `10m-{WSI}-{YYYYMMDD}.json` day files. On the server they are year directories holding **monthly** files `…-{YYYYMM}.json` (e.g. `$C/historical/data/1hour/2025/1h-0-20000-0-11406-202501.json`, 2 178 310 B).
- **Retention differs from the PDF [V].** The PDF says files in `now/data` older than 24 h are deleted. The live listing holds 3 days: 2026-10-16, -17 and -18, with 475 `10m` and 436 `1h` files per day. The PDF says metadata is kept for 10 days; `now/metadata` holds only 2 days (17 and 18).
- **Use the station catalog, not listings [V].** `historical/data/daily/` lists 1 537 files in 203 KB. `recent/data/1hour/` lists 7 424 entries in about 1 MB. `meteorology/floods/` lists more than 21 500 PNG files and exceeds 3 MB. File names should be built from the station catalog (WSI list) rather than discovered from listings.

## 2. File formats (real samples)

### 2.1 JSON envelope (all climate JSON files) [V]
```json
{"zaznamID":"e0a332f2-9c8d-5f16-022a-b3886aec5b4d","datovyZdrojID":"meteorologie",
 "datovyTokID":"Open.Data.1D","datumVytvoreni":"2026-10-18T12:43:42.969Z","verzeDat":"1.0",
 "data":{"type":"DataCollection","data":{"header":"STATION,ELEMENT,VTYPE,DT,VAL,FLAG,QUALITY","values":[ … ]}}}
```
- Source: `$C/recent/data/daily/dly-0-20000-0-11406-202610.json`.
- `datovyTokID` takes the values `Open.Data.10M`, `Open.Data.1H`, `Open.Data.1D`, `Open.Data.MLY`, `Open.Data.YRS` and `Open.Data.Metadata` [V].
- `header` is a comma-separated string. `values` is an array of row arrays.

### 2.2 Row layouts [V]
| Product | Header | Sample row |
|---|---|---|
| now/recent 10-min (`10m-…`) | `STATION,ELEMENT,DT,VAL,FLAG,QUALITY` | `["0-20000-0-11406","T","2026-10-18T00:00:00Z",7.2,"",5.0]` |
| now/recent 1-hour (`1h-…`) | same | `["0-20000-0-11406","ppp","2026-10-18T01:00:00Z",0.2,"3",5.0]` |
| daily (`dly-…`, recent + historical) | `STATION,ELEMENT,VTYPE,DT,VAL,FLAG,QUALITY` | `["0-20000-0-11406","SRA","06:00","2026-10-04T06:00:00Z",0.0,"T",0.0]` |
| monthly (`mly-…`) | `STATION,ELEMENT,YEAR,MONTH,TIMEFUNCTION,MDFUNCTION,VALUE,FLAG_REPEAT,FLAG_INTERRUPTED` | `["0-203-0-11573","F","1994","01","AVG","AVG",2.2,"",""]` |
| yearly (`yrs-…`) | `STATION,ELEMENT,YEAR,TIMEFUNCTION,MDFUNCTION,VALUE,FLAG_REPEAT,FLAG_INTERRUPTED` | `["0-203-0-11573","SRA","1994","06:00","SUM",507.9,"",""]` |
| historical_csv daily | `STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY,` (trailing comma, so 8 columns) | `0-203-0-11573,SRA,06:00,1994-01-01T06:00Z,0.2,,0.0,` |

- **Monthly and yearly aggregates [V].** `MDFUNCTION` takes the values `AVG`, `SUM`, `MAX`, `MIN`, `GE(x)`, `L(x)` and `G(x)`; the last three are day counts against a threshold. `FLAG_REPEAT` `*` and `FLAG_INTERRUPTED` `I` both occur in `yrs-0-203-0-11573.json`. Meaning: `*` = extreme repeated, `I` = interrupted series [U].
- **CSV and JSON carry the same data under different names [V].** The CSV renames `VTYPE`→`TIMEFUNC` and `VAL`→`VALUE`, drops seconds from `DT` (`…T06:00Z` vs `…T06:00:00Z`), uses LF line ends and no BOM, and is served as `application/octet-stream`. For Benešov SRA, CSV vs JSON compared 5 022 rows with 0 differences.
- Source files: `$C/historical_csv/data/daily/precipitation/dly-0-203-0-11573-SRA.csv` and `$C/historical/data/daily/dly-0-203-0-11573.json`.

### 2.3 Metadata files [V]
| File | Header | Notes |
|---|---|---|
| now `meta1-YYYYMMDD.json` | `WSI,GH_ID,FULL_NAME,GEOGR1,GEOGR2,ELEVATION,BEGIN_DATE` | 760 stations. Sample: `["0-20000-0-11406","L3CHEB01","Cheb",12.391389,50.068333,483.0,"1863-10-01T00:00:00Z"]` |
| historical `meta1.json` | `WSI,GH_ID,BEGIN_DATE,END_DATE,FULL_NAME,GEOGR1,GEOGR2,ELEVATION` | 5 539 rows, one per station location period, covering 1 611 WSI. 768 are active (`END_DATE` = `3999-12-31T23:59:00Z`). Earliest `BEGIN_DATE` is 1775-01-01 (Praha-Klementinum, `0-203-0-11514`) |
| now `meta2-…` | `OBS_TYPE,WSI,EG_EL_ABBREVIATION,NAME,UN_DESCRIPTION,HEIGHT,SCHEDULE` | 6 611 rows: 10M 4 257, 1H 2 354 |
| historical `meta2.json` | `OBS_TYPE,WSI,BEGIN_DATE,END_DATE,EG_EL_ABBREVIATION,NAME,UN_DESCRIPTION,HEIGHT,SCHEDULE` | Per station, element and period, with unit and the `SCHEDULE` (VTYPE) list. Sample: `["DLY","0-20000-0-11406","1863-10-01T00:00:00Z","1919-12-31T23:59:00Z","T","Teplota","°C",2.0,"AVG,06:00,13:00,20:00"]`. Structure read with 3 range requests; full 9.66 MB file not fetched |
| `meta3` | `EL_ABBREVIATION,FLAG,DESCRIPTION` | Flag dictionary (§9) |
| `meta4` | `FLAG2,DESCRIPTION` | Quality dictionary 0..5 (§9). Ends with a junk row `[null,null,null,null,null,null]` |

- **`GEOGR1` is longitude and `GEOGR2` is latitude [V].** Example: Cheb 12.39 / 50.07.
- **CSV metadata loses commas in names [V].** `meta1.csv` is unquoted with a trailing comma, and commas inside names became double spaces. JSON has `"Karlovy Vary, Olšová Vrata"`; CSV has `Karlovy Vary  Olšová Vrata` (`$C/historical_csv/metadata/meta1.csv`).
- **Element names and units for DLY, from historical meta2 [V]:**

  | Code | Meaning | Unit | VTYPE (schedule) |
  |---|---|---|---|
  | SRA | Srážka (precipitation) | mm | 06:00 |
  | SNO | Nový sníh (new snow) | cm | 06:00 |
  | SCE | Výška sněhu (snow depth) | cm | 06:00 |
  | SCEdif | Denní rozdíl celkové výšky sněhu (daily change in snow depth) | cm | 06:00 |
  | SVH | Vodní hodnota (snow water equivalent) | mm | 06:00 |
  | API30 | Index předchozích srážek (antecedent precipitation index) | mm | 06:00 |
  | T | Teplota (air temperature) | °C | AVG, 06:00, 13:00, 20:00 |
  | TMA / TMI | Teplota max / min | °C | 20:00 |
  | TMInoc | Teplota min, night minimum | °C | 06:00 |
  | TPM | Teplota přízemní (ground temperature) | °C | 06:00 |
  | VY | Výpar (evaporation) | mm | 06:00 |
  | SSV | Sluneční svit (sunshine) | hod | 00:00 |
  | Fmax / Dmax / Casmax | Max wind speed / its direction / time of maximum | — | 00:00 |
  | F, H, P, E, T05…T100 | Wind, humidity, pressure, vapour pressure, soil temperatures | — | AVG + terms |

### 2.4 CAP XML [V]
- **Type 50 files** (`alert_cap_50_*.xml`) carry SIVS weather warnings plus the flood blocks.
  - Header sample: identifier `2.49.0.0.203.0.CZ.261018095427.XOCZ50_OKPR_000383`, sender `chmi@chmi.cz`, `sent` `2026-10-18T11:54:27+02:00`, `msgType` `Update`, and `references` pointing to the previous message.
  - Each file is a **full-state snapshot**: every phenomenon appears, including "Žádná výstraha …" (no-warning) blocks, in both `cs` and `en-GB`. The calm-day file holds 36 `<info>` blocks; the 2026-06-28 file holds 88.
  - Areas: one `<area>` per kraj with `geocode` `CISORP` (ORP code; 206 unique) and **`EMMA_ID`**. The PDF documents `EMMAID` and NUTS3, but NUTS3 is absent.
  - Info parameters: `situation`, `eventEndingTime`, `awareness_level` (`"4; red; Extreme"`), `awareness_type` (`"5; high-temperature"`), and `eventCode` (`SIVS` → `I.3`).
  - `<effective>` and `<expires>` are present only in real warnings (e.g. expires `2026-06-29T00:00:00+02:00`).
  - Sources: `$O/meteorology/weather/alerts/cap/alert_cap_50_180954.xml` and `…/alert_cap_50_280917.xml`.
- **Type 70 files** are HAMR drought warnings: sender `ohp@chmi.cz`, `<code>HAMR</code>`, parameters `drought_in_surface_waters` / `drought_in_groundwater`. They are issued weekly on Tuesdays at 12:00 UTC (`alert_cap_70_131200.xml`). They can contain **zero `<info>` blocks** (`alert_cap_70_061200.xml`, 444 B).

## 3. Identifiers [V]
- **WSI is the station key** in every file name and in the `STATION` column. Patterns in historical meta1 (1 611 WSI):

  | Pattern | Count | Example |
  |---|---|---|
  | `0-20000-0-NNNNN` (WMO index) | 43 | `0-20000-0-11406` Cheb |
  | `0-203-0-NNNNN` | 269 | `0-203-0-11573` Benešov |
  | `0-203-0-NNNNNNNNNNN` (11 digits) | 1 298 | `0-203-0-42106052001` Hrčava |
  | `0-203-0-NNNNNNNNN` (9 digits) | 1 | `0-203-0-111040030` |

  `now/meta1` also contains a 10-digit form, `0-203-0-1080511301`.
  - The audit's "WIGOS = 9 digits" is wrong. Treat WSI as an opaque text code; it is file-name safe (digits and hyphens).
  - Meteo WSIs use issue number `0` (`-0-`); the hydro sample `0-203-1-001000` uses `-1-`. So hydro and meteo station codes should not collide [I].
- **Foreign stations exist [V].** Reykjavik `0-20000-0-04030` (lon -21.9, lat 64.1) is in `now/meta1` and in `recent/daily`. "Marambio, Base" (Antarctica) is in historical meta1. Under IMGW-9 rules both are `outside_country`.
- **`GH_ID` is ČHMÚ's internal ID** (e.g. `L3CHEB01`, `P1PKLE01`). It is **not 1:1 with WSI** [V]: 12 WSI have more than one GH_ID, and 3 GH_IDs map to 2 WSI (e.g. `C2CBUD01` → `0-203-0-11542` and `0-20000-0-11546`).
- **VTYPE / TIMEFUNC** values: `06:00`, `13:00`, `20:00` (observation terms), `AVG` (daily mean), `00:00` (whole-day values: Fmax, Dmax, Casmax, SSV) [V].

## 4. Time conventions (verified empirically)
- **Data timestamps are UTC** with a `Z` suffix in every file [V]. The climate PDF says so explicitly for `now/`: "Časy jsou v UTC" (p. 4). The earlier "PDF says SEČ" discrepancy does not appear in the climate PDF; it may come from the hydrology PDF [U].
- **Terms.** `06:00` / `13:00` / `20:00` UTC correspond to the classic 7 / 14 / 21 h SEČ (CET) terms [I]. For the 18th–19th-century records these UTC labels are nominal [U].
- **Daily mean temperature** `T`/`AVG` (DT `D T00:00Z`) = **(T06 + T13 + 2·T20) / 4**, rounded to 0.1 [V].
  - Evidence: 17/17 days, Cheb, Oct 2026 (`recent/data/daily/dly-0-20000-0-11406-202610.json`).
  - It is not the 24-hour mean: on 2026-10-17 the 10-min mean was 8.98 vs AVG 8.6.
- **TMA / TMI** (DT `D T20:00Z`) = extreme over **(D-1 20:00Z, D 20:00Z]**, attributed to the **end** day D [V].
  - Evidence: Cheb 2026-10-17. TMI 7.5 equals the minimum of 10-min TMI in that window; the calendar-day minimum is 7.2.
  - Sources: `now/data/10m-0-20000-0-11406-2026101{6,7,8}.json`.
- **SRA (precipitation) and SNO (new snow)** (DT `D T06:00Z`) = the total for the 24 h **starting** at the morning term of D. So the morning reading on D+1 is attributed to D [V].
  - Station 0-203-0-42106052001, Sept 2026: daily SRA equals the sum of 10-min `SRA10M` labelled (D 05:40Z, D+1 05:40Z] on **29/29 days exactly**.
  - The window (D-1, D] mismatched on 10+ days.
  - Sources: `recent/data/10min/09/10m-0-203-0-42106052001-202609.json` and `recent/data/daily/09/dly-…-202609.json`.
  - The 20-minute offset from 06:00Z exists at automatic stations; it is not documented [U].
- **SNO consistency check [V].** In Jan 2026, `SCE(D+1) ≈ SCE(D) + SNO(D)` (e.g. 11 + 7 → 18 and 18 + 32 → 50/51).
- **SCE (snow depth)** at DT `D T06:00Z` = state at the morning of D [V]. It equals the 10-min `SCEa` at D 06:00Z on 6/7 days and is within 1 cm on the 7th (Jan 2026, `recent/data/10min/01/…` vs `daily/01/…`).
- **Interval labels.** Hourly value at label t = Σ of 10-min values labelled t-50 … t (719/719 hours exact). Labels therefore mark the end of the interval [I from V].
- **CAP times** carry a local offset, `+01:00` or `+02:00` [V]. The type-50 file name `DDHHMM` is the UTC day and time of `sent` (`180954` ↔ `sent 11:54:27+02:00`) [V].
- **Directory listings** show GMT, to the minute, with exact byte sizes. This matches `Last-Modified` (e.g. listing `18-Oct-2026 00:01` vs header `00:01:03 GMT`) [V].

## 5. Coverage and archive depth (with evidence)
| Source | Coverage | Evidence |
|---|---|---|
| `now/data` | D-2 … D (3 days); files rewritten hourly | [V] listing `$C/now/data/` |
| `recent/data/daily` | Current month to yesterday at the root; previous 12 months in `MM/`. On 2026-10-18 `10/` = 2025-10 and `09/` = 2026-09 | [V] listings `daily/`, `daily/09/`, `daily/10/` |
| `recent/…/10min`, `1hour` | Current-month day files at the root (`1h-…-20261001` … `-20261017`); 12 monthly dirs | [V] |
| `historical/data/daily` | Full station period through **2025-12-31** | [V] Cheb tail row `2025-12-31` |
| `historical/data/{10min,1hour}` | 2018 … 2025 (year dirs) | [V] |

- **Overlap.** Oct–Dec 2025 is in both `recent` and `historical`. Cheb TMA for Oct 2025 is identical in both (31/31) [V].
- **Archive depth examples [V]:**
  - Praha-Klementinum `0-203-0-11514`: T and TMA from **1775-01-01**, SRA from **1804-05-01** (CSV range reads, `…/temperature/dly-0-203-0-11514-T.csv`).
  - Cheb: T AVG from **1863-10-01**; TMA from 1865-06-01.
- **Depth is per element and has holes.**
  - **Cheb TMA**: rows 1865-06-01…1919-12-31 and 1961-01-01…2025-12-31. 1889–1910 is present only as explicit missing rows. **1920–1960 has no rows at all**, although meta1 lists periods in 1933–38 and 1943–45, and meta2 lists DLY T/TMA from 1955 [V `histcsv_dly-0-20000-0-11406-TMA.csv`].
  - **Benešov** `0-203-0-11573`: meta1 says the station has existed since 1920-09-13, but the data runs only 1994-01-01…1998-03-31 and 2016-07-01…2025-12-31 [V].
  - **Conclusion:** neither meta1 nor meta2 periods give actual data availability. Coverage must be computed from the data.
- **Station sets disagree [V]:**
  - Historical meta1 has 1 611 WSI and the daily JSON directory has 1 537 files. **74** catalog stations have no daily file.
  - **43 active stations** (some since 2009, some since the 1870s) have `mly-` but no `dly-` historical file; e.g. `dly-0-203-0-10102001101.json` returns 404, the SRA CSV also returns 404, and `mly-…` returns 200. Their daily data exists only in `recent` (12 months).
  - 14 stations active in historical meta1 are absent from now meta1. 2 stations in now meta1 are absent from historical meta1.
  - 37 stations have current coordinates (now meta1) that differ from their latest historical period.
- **Element availability (historical_csv daily) [V]:** T 709 stations, TMA 556, TMI 555, SRA 1 531, SCE 1 278, SNO 1 268, SVH 1 149. 154 stations have T without TMA/TMI.

## 6. Update cadence and HTTP signals
- **Static files [V]:**
  - Headers present: `Content-Length`, `Last-Modified`, `ETag`, `Accept-Ranges: bytes`. `Server: nginx/1.22.1`.
  - `HEAD` works. Missing files return `404`.
  - Conditional requests work: `If-None-Match` and `If-Modified-Since` both return `304`. `Range` returns `206`.
  - No `Content-Encoding` even when `gzip`/`br` is requested, so the bytes served equal the file bytes.
  - No `Cache-Control` or `Expires`. No CORS header (`Access-Control-Allow-Origin` is absent even with an `Origin` request header).
- **ETag is just mtime and size [V].** It is nginx's `"<hex mtime>-<hex size>"`, e.g. `"6a9a9a60-3b3187"` = 2026-09-04T10:16:00Z with 3 879 303 B, exactly matching `Last-Modified` and `Content-Length`. It carries no content hash.
- **Directory listings** are chunked with no `ETag` or `Last-Modified` [V]. Per-file mtime (to the minute) and exact size are available from the listing body.
- **Observed regeneration times [V]:**

  | Product | Last regenerated (observed) |
  |---|---|
  | `historical/data/daily/*.json` (all 1 537) | 2026-09-04 |
  | `historical_csv/data/daily/**` | 2026-09-04 |
  | `historical/data/{monthly,yearly}` | 2026-05-05 (1–3 files 2026-04-16) |
  | `historical/data/{10min,1hour}/2025/` | 2026-02-13 |
  | historical `meta1.json` | 2026-02-12 |
  | historical `meta2.json` | 2026-05-26 |
  | historical `meta3/4.json` | 2024-06-21 |

  The PDF says historical files are updated "jen jednou ročně … do konce února". In practice they were regenerated in Feb, May and Sep 2026 [V].
- **`recent` cadence [V]:**
  - `dly-…` at the root: all 756 files rewritten daily around 12:3x–12:4x UTC; the content is up to yesterday.
  - `1h` day files appear the next day at about 12:20 UTC.
  - Month dirs: `09/` was written 2026-10-02 around 22:xx. `10/` (Oct 2025) was rewritten 2025-12-02. The dirs `08/` and `09/` were touched 2026-10-05.
  - This is consistent with the PDF rule "the two previous months are re-generated at the start of the month" (the PDF says the 3rd day).
  - The last day of the current month carries `QUALITY 5` (unvalidated), so values change on re-publication [V].
- **`now` cadence [V].** `10m` files are rewritten hourly at HH:02–04 UTC; the final version of day D is written at D+1 00:02. `1h` files are rewritten at HH:12–22. `now/meta*` files are written daily at 00:01–02.
- **CAP cadence [V].**
  - Type 50: event-driven, about 14–64 files per month. 730 files are present, spanning 2025-01-19 … 2026-10-18.
  - Type 70: weekly, 31 files. A name is reused only when the same `DDHHMM` recurs in a later month, which overwrites the earlier file [I].

## 7. Sizes [V]
| Set | Files | Total | Median | Max |
|---|---|---|---|---|
| historical daily JSON | 1 537 | **25.36 GB** | 10.0 MB | 149 MB (Klementinum) |
| historical_csv daily `-SRA.csv` | 1 531 | 1.72 GB | 1.02 MB | 4.2 MB |
| historical_csv daily `-T.csv` | 709 | 1.88 GB | 1.78 MB | 18.4 MB |
| historical_csv daily `-TMA.csv` / `-TMI.csv` | 556 / 555 | 0.38 / 0.38 GB | 0.45 MB | 4.8 MB |
| historical_csv daily `-SCE` / `-SNO` / `-SVH` | 1 278 / 1 268 / 1 149 | 1.35 / 1.34 / 1.03 GB | ~1 MB | 2.8 MB |
| historical monthly / yearly JSON | 1 579 / 1 567 | 2.75 GB / 212 MB | 988 KB / 77 KB | 18 MB / 1.4 MB |
| recent daily, current month (root) | 756 | 15.9 MB | 7.8 KB | 72 KB |
| recent 1hour `09/` | 435 | 102 MB | — | ~2.1 MB |
| recent 10min `09/` | 474 | 1.13 GB | 1.7 MB | 6.5 MB |
| now `10m` / `1h`, per day | 475 / 436 | ~38 MB / ~3.6 MB | 57 KB / 3 KB | — |
| CAP type 50 / type 70 | 730 / 31 | 1.2 GB total | 1.65 MB / 58 KB | 2.35 MB |

## 8. Encoding [V]
- All JSON, CSV and CAP samples are **UTF-8 without BOM**, with LF line endings. Diacritics appear in names, e.g. "Olšová Vrata".
- **`VAL` has mixed types:** a JSON number, or `""` (empty string) when missing. Meteo data never uses JSON `null`; the only `null`s are in the junk row of `meta4`.
- In historical meta1, missing coordinates and elevations are `""`: 1 row has no latitude (`0-203-0-10801028001`, 1984–1990) and 3 rows have no elevation.

## 9. Missing values, flags, quality
- **Quality dictionary (`meta4`) [V]:**

  | QUALITY | Meaning |
  |---|---|
  | 0 | Good |
  | 1 | Suspect |
  | 2 | Poor ("zatím nepoužívat", do not use yet) |
  | 3 | Estimated |
  | 4 | Missing |
  | 5 | Unknown (operational data) |

- **Missing values [V].** Represented as `VAL ""` together with `QUALITY 4.0`. Every sample has `VAL ""` exactly when `QUALITY == 4`: Benešov 8 223/8 223 rows, Cheb recent, Hrčava, Jimramov, and `now` data.
- **Two kinds of missingness [V]:**
  - Inside a station/element period block, **every calendar day has a row**; missing days are explicit rows.
  - **Between blocks there are no rows** (Cheb TMA 1920–1960; Benešov 1998-04 … 2016-06).
- **Row order is not by date [V].** The historical JSON is ordered element → period block → VTYPE (AVG first) → date. For example, after `T AVG …1919-12-31` comes `T 06:00 1863-10-01`; after `T 20:00 1919-12-31` comes `T AVG 1961-01-01`. Parsers must sort.
- **Flags (`meta3`) [V]:**
  - `SRA`: `T` = "Neměřitelné množství" (trace; VAL is 0.0) and `M` = "Úhrn mimořádně z manuálního srážkoměru".
  - `SNO`: A, N, P, R. `SCE`: A, N, P, U, Z. `SRA10M` / `SRA1H`: Z (backup gauge); `SRA1H` also has 5 and 7 (HYDROSTART). `TPM`: S, V. `ppp`: codes 0–8. `D` / `Dmax`: `V` (variable).
  - **meta3 is not exhaustive.** `SCE` flag `R` occurs 14× in Benešov data but is not listed for SCE.
- **No phenomenon [V].** Precipitation of 0.0 with no flag means no precipitation (Benešov: 2 378 days). There is no explicit "no phenomenon" status code like IMGW's "9".
- **No accumulated-sum flag exists in `meta3` [V].** Whether multi-day sums occur anywhere in the data is [U].
- **CAP "no warning"** is expressed as `severity Minor` / `certainty Unlikely` blocks [V].

## 10. Licensing and attribution
- **ČHMÚ FAQ [V]:** "Otevřená data ČHMÚ můžete využívat bezplatně při respektování licence Creative Commons BY 4.0." Source: https://www.chmi.cz/-/jak-mohu-pou%C5%BE%C3%ADvat-otev%C5%99en%C3%A1-data-%C4%8Dhm%C3%BA- (read 2026-10-18).
- **NKOD entry for the CAP dataset "Výstrahy ČHMÚ na nebezpečné hydrometeorologické jevy" [V]:**
  - Terms of use: CC BY 4.0, author "Český hydrometeorologický ústav".
  - Sui generis database rights: "Not protected". No personal data.
  - Listed as an HVD category "Weather alerts" (Implementing Regulation (EU) 2023/138).
  - Download URL: `$O/meteorology/weather/alerts/cap/`.
  - Source: https://data.gov.cz/dataset?iri=https%3A%2F%2Fdata.gov.cz%2Fzdroj%2Fdatov%C3%A9-sady%2F00020699%2F37f82af3771f8af5b52d635078a2ac17
- **No license or attribution file on the server [V].** None at the root or in the climate dirs.
- **An exact attribution formula was not found [U].** This leaves Archiwista Q17 open. Suggested wording: "Zdroj: Český hydrometeorologický ústav (ČHMÚ), opendata.chmi.cz, CC BY 4.0" [U]. CzLegal owns this question.

## 11. Rate limits, robots, terms [V]
- `$O/robots.txt` returns 404.
- No rate-limit headers and no 429 or Retry-After across 173 requests at about 1–2 requests per second.
- No published request quota was found [U].

## 12. IDF / max-precipitation analogue to PMAXTP
- **opendata.chmi.cz has no IDF or return-period product [V].**
  - `meteorology/products/` contains only `climate_normal_stations/period_1991_2020/{precipitation,temperature}`, `grids_CZ/climate_normals/period_1991_2020/{air_temperature_mean,precipitation,sunshine_duration}`, `regional_averages/{precipitation,temperature}` CSVs, and `yearbooks/` PDFs for 2020–2023 (~57–61 MB each).
  - `hydrology/product/data/flash_flood/rsraz_exp_web.json` (GeoJSON, 3.6 MB, updated at 7:05, 10:05 and 13:05 UTC) carries `P_R1`, `P_R3` and `P_R6`: "potenciálně nebezpečný úhrn srážek za 1/3/6 h [mm]". This is a dynamic soil-saturation-dependent threshold, not design rainfall (per `…/metadata/flash_flood/popis_flash_flood.pdf`).
- **The closest analogue is outside ČHMÚ: ČVUT HydroRAIN**, built in cooperation with ÚFA AV ČR and ČHMÚ (https://rain.fsv.cvut.cz/).
  - **WPS** at `https://rain1.fsv.cvut.cz/services/wps` [V]. GetCapabilities lists `d-rain6h-timedist`, `raintotal6h-timedist`, `rain6h-cn-runoff` and `soil-texture-hsg`, with AccessConstraints NONE and Fees NONE. It provides 6-hour design storms for return periods 2–100 years at a point or polygon, as CSV output. It is limited to 2 parallel processes.
  - **WMS** at `https://rain1.fsv.cvut.cz/services/wms` [V]. Layers `H_N{2,5,10,20,50,100}_24h` ("N-leté maximální denní úhrny") are **queryable="0"**, so the service gives images only and no point values.
  - **This is not a PMAXTP equivalent.** It covers 6 h and 24 h only (PMAXTP covers 5 min … 72 h), and there are no ks/sg/rb triplets.
  - License: no explicit statement on the service pages [U].

## 13. Gotchas (summary)
1. **Per-station files.**
   - Historical files are per station and span all years, so "year" is not a file dimension. The daily JSON has a 10 MB median and 25 GB in total.
   - CSV files are per element and smaller.
   - Recent files are per station and month, kept for 12 months only.
   - The same month moves from the `recent/…/` root (while current) to `MM/`, so the server path changes for the same data.
2. **The JSON envelope makes raw bytes change on every regeneration [V].** `zaznamID` (a UUID) and `datumVytvoreni` change each time. Example: `now/metadata/meta1-20261017.json` vs `-20261018.json` have identical `data`, different `zaznamID`/`datumVytvoreni`, the same size (75 509 B) and **different sha256**. CSV files have no envelope [V header].
3. Metadata coordinates are JSON floats, so trailing zeros are lost (`Doksany` lon `14.17`, lat `50.45889`). Rounding precision cannot be derived from decimal places.
4. Station metadata periods ≠ data availability. 43 active stations have no historical daily file. Some stations are foreign.
5. The PDF documents historical 10min/1hour files as daily `YYYYMMDD`; the server has year dirs with `YYYYMM` files. Real retention also differs from the PDF.
6. `VAL` is a number or `""` (mixed types). `meta4` contains a junk row of nulls.
7. CSV metadata uses no quoting; commas in names become double spaces.
8. CAP files use local time offsets. Type-70 files may have zero `<info>` blocks. The geocode is `EMMA_ID`, not `EMMAID`/NUTS3 as documented. File names `DDHHMM` can be reused in later months.
9. In daily data the precipitation and new-snow day starts in the morning (start-day attribution), while Tmax/Tmin use a 20–20 UTC window attributed to the end day. Mixing them in one "date" row needs care.

## 14. Gaps against Archiwista `wymagania-imgwtools.md` (IMGW-1..19, R1..R12)
- **IMGW-5/16 (update signals).**
  - HEAD signals exist per file: ETag, Last-Modified and Content-Length are all present [V].
  - **However, `ETag` only encodes mtime and size.** Every regeneration (seen in Feb, May and Sep 2026 for historical; daily for recent) changes both headers. Because of gotcha 2, the bytes also change.
  - As a result, `relabeled` (same sha256 under new headers) is **unreachable for JSON** and every regeneration becomes `newer`, unless the provider hashes the normalised `data` part.
  - CSV historical files have no envelope, so `relabeled` can work there.
  - A full check is large: `check_store` for all daily stations means 1 537 HEAD requests. Alternatively, one listing GET (~200 KB) gives the mtime and size of every file.
- **IMGW-4/16 (archives 1:1, `archive_files` offline).**
  - The file list depends on the WSI set, so it needs a stored station catalog; it cannot be computed from years alone.
  - "Listing of published years" has no meaning for historical files (one file holds all years).
  - A 404 for a station in the catalog is real and frequent (74 + 43 cases above), so it must map to `missing`.
- **IMGW-6/18 (flags).**
  - `missing` = `VAL ""` + `QUALITY 4`. IMGW-18's phrase "`null` ČHMÚ → brak" is wrong for meteo; the marker is the empty string `""`.
  - `no_phenomenon` = SRA 0.0 with no flag. ČHMÚ uses no explicit code.
  - The trace flag `T` (0.0) has no slot in the contract.
  - `accumulated` has no ČHMÚ counterpart (not in meta3).
  - QUALITY 1/2/3/5 (suspect, poor, estimated, unvalidated) is lost unless the contract gains a quality column. QUALITY 5 marks the last days of `recent` data.
- **IMGW-7/18 (gap-free daily calendar).**
  - The source is gap-free only inside period blocks. Between blocks, IMGWTools must synthesise `missing` rows.
  - Rows are not date-sorted.
  - Columns `date` and `hydro_year` must come from the record's `DT` with the attribution rule in §4. A naive `DT[:10]` gives the correct climatological date for SRA/SNO (start day) and TMA/TMI (end day) [V].
  - The Czech hydrological year XI–X is [U]; it belongs to the hydro domain.
- **IMGW-8/18 (per-variable coverage).**
  - Variables map to `SRA` (precipitation), `TMA` (Tmax), `TMI` (Tmin), and `T` with VTYPE `AVG` (Tmean). Optional: `SCE`, `SNO`, `SVH`.
  - Coverage must come from the data, because meta periods overstate availability (Benešov, Cheb).
  - Data published in recent only (43 stations) gives coverage of 12 months at most.
- **IMGW-9/17 (catalog).**
  - Coordinates exist in historical meta1 per period (`GEOGR1` = lon, `GEOGR2` = lat). 1 period lacks a latitude; 2 stations are outside CZ.
  - **No station "kind"** (climatological vs precipitation): derive it from meta2 or from the elements present.
  - No river field, which is fine for meteo.
  - Requirement 2, "coordinates and codes without rounding or numeric conversion", **conflicts with the JSON floats**. Read the coordinate text from `meta1.csv`, or parse JSON with `parse_float=str`.
  - Requirement 3, "same metadata content → no new version", **fails on raw bytes** because `now/meta1-YYYYMMDD.json` changes envelope bytes daily. Use historical `meta1.json`/`meta1.csv` (rarely regenerated) or a normalised hash.
  - Current positions (now meta1) differ from the latest historical period for 37 stations.
- **IMGW-14/19 (reproducible project pins).**
  - The server keeps **only the latest version**. `now` files are deleted after about 3 days, `recent` months after 12 months, CAP names get overwritten, and historical files are regenerated several times a year.
  - Re-downloading a pinned version from ČHMÚ will usually fail with "different content", so reproduction works only from a copied store.
- **IMGW-3/19 (license in sidecar).** CC BY 4.0 is verified (§10). The exact attribution formula remains [U].
- **ADR-002 dataset keys.** Natural slicing for `cz.chmi.meteo_daily`:
  - Archive slots `meteorology/climate/historical_csv/data/daily/{precipitation|temperature|snow}/dly-{WSI}-{SRA|T|TMA|TMI|…}.csv` (smaller, no envelope).
  - Plus `meteorology/climate/recent/data/daily/{MM/}dly-{WSI}-{YYYYMM}.json` for the current year.
  - This is a recommendation [I].

## 15. Corrections to prior research and audit
- "10-min/1-h historical from 2018": confirmed. The file naming is `{YYYY}/…-{YYYYMM}.json`, not daily files [V].
- "`dly-{WSI}-{YYYYMM}.json` in recent": confirmed, and those files exist only for the last 12 months [V].
- "CAP ~1–2 MB": type 50 files are 0.86–2.35 MB; type 70 files are 0.4–61 KB [V].
- "Meteo WSI = 9 digits": wrong. There are 4 or more patterns (§3) [V].
- "PDF SEČ vs UTC": the climate PDF says UTC, consistent with the data [V].

## 16. Saved samples (`/tmp/cz-explore/CzMeteo/`)
- `now_meta{1..4}-20261018.json`, `now_meta1-20261017.json`, `hist_meta1.json`, `hist_meta2_{head,chunk,tail}.json.part`, `histcsv_meta1.head.csv`
- `now_{10m,1h}-0-20000-0-11406-*.json`
- `recent_dly-0-20000-0-11406-2026{10}.json`, `recent_dly-0-20000-0-11406-202510.json`
- `recent_{dly,1h,10m}-0-203-0-42106052001-2026{09,01}.json`
- `hist_dly-0-203-0-11573.json`, `hist_dly-0-203-0-41501027001.json`, `hist_yrs-0-203-0-11573.json`
- `histcsv_dly-0-203-0-11573-{SRA,TMA}.csv`, `histcsv_dly-0-20000-0-11406-TMA.csv`
- `alert_cap_50_{180954,280917}.xml`, `alert_cap_70_{131200,061200}.xml`
- `Klimatologicka_data_popis.pdf`, `Dokumentace_CAP.pdf`, `popis_flash_flood.pdf`, `cvut_w{p,m}s_getcapabilities.xml`
- All listings (`*.html`) and `requests.log`
