# ČHMÚ open data — licensing, terms, operations (CzLegal, 2026-10-18)

Scope: licence and attribution, HVD status, robots/rate limits/User-Agent, HTTP caching headers, directory listing format, URL stability, docs and contacts. Also: how this fits the IMGWTools/Archiwista contract (ADR-001/002, Archiwista IMGW-3/5/15–19) and a proposed `license` sidecar field for `cz.chmi.*`.
Raw samples are in `/tmp/cz-explore/CzLegal/` (NKOD SPARQL CSVs, HEAD dumps, FAQ HTML, PDFs, listing excerpts). Total transfer was about 32 MB.
Tags: **V** = VERIFIED live on 2026-10-18 (URL given). **U** = UNVERIFIED. **I** = inference from verified data.

## 1. Licence

| Claim | Status | Evidence |
|---|---|---|
| All ČHMÚ open data is under **CC BY 4.0**, free of charge | V | FAQ https://www.chmi.cz/-/jak-mohu-pou%C5%BE%C3%ADvat-otev%C5%99en%C3%A1-data-%C4%8Dhm%C3%BA- : *„Otevřená data ČHMÚ můžete využívat bezplatně při respektování licence Creative Commons BY 4.0.“* (links to https://creativecommons.org/licenses/by/4.0/deed.cs). The same sentence appears on https://www.chmi.cz/o-chmu/produkty-a-sluzby/data-a-vyhodnoceni and https://www.chmi.cz/-/kde-najdu-otev%C5%99en%C3%A1-data-%C4%8Dhm%C3%BA- |
| Site-wide terms: attribution = „uvedení původu (zdroje ČHMÚ)“ | V | https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti (footer link „Vyloučení odpovědnosti a licencování“): *„Produkty Českého hydrometeorologického ústavu dostupné na těchto webových stránkách podléhají licenci Creative Commons 4.0 CC-BY. Dílo smíte sdílet a upravovat za podmínky uvedení původu (zdroje ČHMÚ).“* The same page has the disclaimer: *„Český hydrometeorologický ústav nenese právní odpovědnost za případné škody způsobené skutečným vývojem počasí a/nebo způsobeným následným užitím produktů či poskytovanými informaci…“* |
| ČHMÚ prescribes **no fixed attribution sentence** (unlike IMGW §5 ust. 3). The only requirement is crediting the source „ČHMÚ“ according to CC BY 4.0 §3(a) | V (no wording found on the pages above, in the PDFs or in NKOD) | CC BY 4.0 §3(a) itself requires: creator identification, licence notice + URI, URI of the material where practicable, and an indication of modifications |
| No English attribution wording published | V | https://en.chmi.cz/en/home has only *„These datasets are freely available to the public and considered public sector information for use, redistribution, and processing.“*, the CC BY link and a link to opendata.chmi.cz |
| NKOD per-distribution terms: authored work CC BY 4.0, database-as-work CC BY 4.0, **no sui generis database right**, no personal data, author „Český hydrometeorologický ústav“ | V | SPARQL https://data.gov.cz/sparql (property `pu:specifikace`). Summary for all ČHMÚ distributions in `nkod_license_summary.csv`: 555 CC BY 4.0 vs 8 **CC BY-NC-ND 4.0** |
| Every opendata.chmi.cz `hydrology/*` and `meteorology/climate/*` distribution in NKOD is CC BY 4.0 | V | `nkod_opendata_dists.csv` (124 rows) |
| **Exception – do NOT use:** the GIS station-network dataset „Měřící síť … stanic … k 1.06.2024“ (`https://geoportal.gov.cz/atom/CHMU/stanice_CHMU_2024_epsg4258.gpkg`, CENIA WMS/WFS) is **CC BY-NC-ND 4.0** | V | `nkod_bync_nd.csv`. Use the `meta1.json` files on opendata.chmi.cz (CC BY) for station coordinates instead |
| Commercial use allowed (CC BY has no NC clause). Paid services exist only for custom processing, data feeds and expert opinions (klima@chmi.cz, komerce@chmi.cz) | V | https://www.chmi.cz/-/mohu-z%C3%ADskat-va%C5%A1e-data-pro-sv%C5%AFj-projekt- and the data-a-vyhodnoceni page |
| Legal basis: Act 262/2024 Sb. §9(3): *„Obsah Databáze je veřejně přístupný způsobem umožňujícím dálkový přístup jako otevřená data…“*. The Databáze = opendata.chmi.cz. Its parameters are set by Decree 106/2025 Sb. and, for HVDs, by Reg. (EU) 2023/138 | V | https://www.zakonyprolidi.cz/cs/2024-262 §9. The data-a-vyhodnoceni page links to the e-sbirka copies |
| meteo station metadata (`meteorology/climate/*/metadata/`) is not listed as its own NKOD distribution. It is covered by the site-wide CC BY statement | V (absence in NKOD query) / I (coverage) | `nkod_opendata_dists.csv` contains only climate `data/` URLs |

### 1.1 High-value datasets (Reg. (EU) 2023/138)
- **V** The regulation, Art. 4(3): *„High-value datasets shall be made available for re-use under the conditions of the Creative Commons Public Domain Dedication (CC0) or, alternatively, the Creative Commons BY 4.0 licence, or any equivalent or less restrictive open licence … A requirement of attribution, giving the credit to the licensor, can additionally be required by the licensor.“* Source: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32023R0138
- **V** NKOD flags these datasets as HVD (`applicableLegislation` = eli/reg_impl/2023/138, plus `hvdCategory`):
  - `hydrology/historical/*` (daily, hourly, monthly, …), `hydrology/now`, `hydrology/recent`, groundwater and water quality → category `c_7b8fbb64` „Environmental monitoring facilities“
  - `meteorology/climate/historical/data/daily` → `c_36807466` „Climate data: validated observations“
  - `meteorology/climate/now` and `recent/*` → `c_3af3368c` „Observations data measured by weather stations“
  - GIS layers → `c_06b1eec4` „Hydrography“
- **V** Not HVD-flagged: climate `historical/data/10min|1hour|monthly|pentadic|yearly`, all `historical_csv/*` and `hydrology/characteristic/*`. They are still CC BY 4.0.
- **I** Practical consequence: the HVD flag only guarantees the licence floor. The licence is identical for HVD and non-HVD data, so IMGWTools needs no per-dataset logic. The HVD "API" requirement is met only by static files (see §5).

### 1.2 Comparison with IMGW (repo docs) → sidecar `license` for `cz.chmi.*`
IMGW, as quoted in Archiwista SPEC 4.8.5 and `src/imgwtools/datasets.py:145`, has these terms:
- the fixed formula §5 ust. 3, plus §5 ust. 4 for processed data;
- a purpose restriction: §3 ust. 2 business use needs an agreement, except HVD;
- `license.id = "IMGW-PIB"`, `url = https://danepubliczne.imgw.pl/regulations`.

ČHMÚ is a standard licence (CC BY 4.0) with no fixed wording and no purpose restriction.

Proposed values (**I**, derived from the V facts above). Czech is used, as ČHMÚ publishes only Czech wording. This mirrors how IMGW uses Polish.
```json
"license": {
  "id": "CC-BY-4.0",
  "attribution": "Zdroj dat: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licence CC BY 4.0",
  "url": "https://creativecommons.org/licenses/by/4.0/",
  "terms_url": "https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti"
}
```
- **Processed data** (series, CSV export, PMAXTP-like products): append the CC BY §3(a)(1)(B) change indication. This is the equivalent of IMGW §5 ust. 4: `"… licence CC BY 4.0. Data byla upravena (normalizace a změna formátu)."`.
- `id` uses SPDX `CC-BY-4.0`. `terms_url` is an additive field; `license.additionalProperties: true` in `src/imgwtools/_data/fixtures/contract_schemas.json` allows it.
- The `on_notice` text should **not** repeat the IMGW purpose warning („Do użytku prywatnego i badawczego…“). Suggested text: „{attribution}. Licencja CC BY 4.0 — dozwolone także użycie komercyjne; wymagane uznanie autorstwa ČHMÚ.“
- **Contract gap (V, repo):** these schema constraints would reject a ČHMÚ sidecar:
  - `contract_schemas.json` `imgw-meta/1`: `license.id` const `"IMGW-PIB"`, `dataset` pattern `^pl\.imgw\.`, `country` const `"PL"`, `provider` const `"IMGW-PIB"`;
  - `src/imgwtools/store/reader.py:216` enforces `const="IMGW-PIB"`;
  - `datasets.py:40` has `id: Literal["IMGW-PIB"]`.

  Archiwista IMGW-15 wants `dataset cz.chmi.*`, `country CZ`, `provider ČHMÚ` "additively in /1". Widening a `const` is not additive for existing strict readers, so it needs an IMGW-13 decision (`/1` widened with a reader update, or `/2`).

## 2. robots.txt, rate limits, User-Agent
- **V** `https://opendata.chmi.cz/robots.txt` → 404, so no crawl rules.
- **V** `https://www.chmi.cz/robots.txt` disallows only Meta bots, `/hledani`, `/*?*c=*` and the employee-contact pages. It does not affect opendata.
- **V** No documented rate limit was found (FAQ, PDFs, NKOD). No `X-RateLimit-*`/`Retry-After` headers. Test results:
  - 20 back-to-back HEADs → all 200;
  - 77 sequential HEADs at about 3/s → no 429/503.
- **U** Behaviour under sustained or parallel load. Recommendation: stay sequential or use 2 concurrent requests, as Archiwista plans ("2 zadania sieciowe naraz").
- **V** No User-Agent requirement: an empty UA and `python-httpx/0.27.0` both get 200. This differs from hydro-back.imgw.pl, which returns 403 without a UA.
- **V** `http://` → `301` to `https://`. HTTP/2 and HTTP/1.1 both work. Server: `nginx/1.22.1`.
- **V** No CORS headers (`Access-Control-Allow-Origin` is absent). Browser-side fetches from the Web GUI would fail; fetch server-side.

## 3. HTTP caching headers (update signal for ADR-001 / IMGW-5/16)
HEAD samples (`heads_1.txt`, `heads_dq_years.txt`), all VERIFIED 2026-10-18:

| URL | Content-Length | Last-Modified | ETag |
|---|---|---|---|
| `/hydrology/now/data/0-203-1-001000.json` | 8920 | Sun, 18 Oct 2026 17:00:08 GMT | "6ad4fb18-22d8" |
| `/hydrology/now/metadata/meta1.json` | 89281 | Sun, 18 Oct 2026 17:01:06 GMT | "6ad4fb52-15cc1" |
| `/hydrology/historical/metadata/meta1.json` | 154554 | Fri, 06 Feb 2026 11:08:02 GMT | "6985cb92-25bba" |
| `/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2020.json` | 21778 | Tue, 01 Jul 2025 12:07:09 GMT | "6863cf6d-5512" |
| `/meteorology/climate/historical/data/daily/dly-0-20000-0-11406.json` | **97687403** | Fri, 04 Sep 2026 08:33:00 GMT | "6a9a823c-5d2976b" |
| `/meteorology/climate/historical/metadata/meta1.json` | 659052 | Thu, 12 Feb 2026 18:35:45 GMT | "698e1d81-a0e6c" |
| `/hydrology/read_me/Průvodce….pdf` | 336500 | Tue, 10 Mar 2026 12:35:00 GMT | "69b00ff4-52274" |

- **V** All three headers (`Content-Length`, `Last-Modified`, `ETag`) are present on every file, plus `Accept-Ranges: bytes`. There is **no** `Cache-Control`/`Expires`.
- **V** ETag is the nginx default `"<hex mtime>-<hex size>"`: `0x6863cf6d` = 2025-07-01 12:07:09 UTC = Last-Modified, and `0x5512` = 21778 = Content-Length. It is a strong validator (no `W/`), but it reflects mtime and size, **not content**. A byte-identical re-upload changes the ETag, so a `newer` status must be confirmed by sha256. The IMGW `relabeled` logic applies.
- **V** Conditional requests work:
  - `If-None-Match: "6863cf6d-5512"` → 304;
  - `If-Modified-Since: <LM>` → 304;
  - `Range: 0-99` → 206.
- **V** **No compression:** with `Accept-Encoding: gzip` there is no `Content-Encoding` and `Content-Length` is unchanged, for JSON and for listings.
- **V** `Content-Type: application/json` has no charset. Files start with `{`, no BOM.
- **V** 404 for a missing year (e.g. `…_DQ_1800.json`) returns `text/html`, length 153. So "missing at source" = a plain 404, which maps to `missing` in IMGW-16.
- **V** Directories return no ETag/Last-Modified/Content-Length (chunked HTML). They cannot be HEAD-checked; only their contents can.

## 4. Directory listing format
- **V** nginx `autoindex`, **HTML only** (`<pre>` with `<a href>`, then `dd-Mon-yyyy HH:MM` and the size in bytes, or `-` for directories). No JSON/XML index exists. `/api` and `/api/` return 404.
- **V** Listing times are **UTC**: `now/data/` shows 17:00 and the file Last-Modified is 17:00:08 GMT; `meta1.json` shows 17:01 vs 17:01:06 GMT. Precision is minutes; sizes are exact bytes.
- **V** hrefs are URL-encoded (e.g. `Pr%C5%AFvodce%20otev%C5%99en%C3%BDmi%20daty%20hydrologie.pdf`, `floods_prec24h_2024091112%2B24.png`). Parse `href` and URL-decode it, not the display text. [I] nginx truncates display names longer than 50 chars.
- **V** Listing sizes, uncompressed because there is no gzip:

| Directory | Size | Entries | Notes |
|---|---|---|---|
| `hydrology/historical/data/daily/` | 5.27 MB | 39,291 files | all `H_<WIGOS>_DQ_<YYYY>.json`; 803 stations; years 1887–2025; 605 MB total |
| `hydrology/recent/data/` | **20.6 MB** | 154,889 entries | `YYYYMMDD_<WIGOS>.json` — avoid |
| `meteorology/climate/historical/data/daily/` | 203 KB | 1,537 files | `dly-<WIGOS>.json`, per station for the whole history; 25.4 GB total; largest 97.7 MB |
| `hydrology/now/data/` | 68 KB | 546 files | |
| `meteorology/floods/` | ~2 MB | ~27k PNGs | |

- **I** For `check_store`, one GET of `hydrology/historical/data/daily/` (5.3 MB) gives name, mtime and size for all 39k files. That replaces 39k HEADs: use the listing as the index and HEAD only the selected stations. The listing gives no ETag, but mtime+size is exactly what the nginx ETag encodes, so the ETag can be rebuilt as `"%x-%x" % (mtime_s, size)`. Minute precision makes the seconds unknown, so compare by size + minute, or HEAD the candidates.

## 5. URL stability, cadence, publication behaviour
- **V** Paths have no version component (`/{domain}/{now|recent|historical}/{data|metadata}/…`). Paths quoted in `docs/OBSERWATOR_RESEARCH.md` (2026-08-11) still resolve.
- **V** Data moves between trees over time:
  - `now/`: the current UTC day, appended hourly. The PDF https://opendata.chmi.cz/hydrology/hydrologicka_data_now_a_recent_popis.pdf says *„Postupně přidávají jedenkrát za hodinu… Po půlnoci jsou data přesunuta do adresáře /recent/“*.
  - `recent/`: unvalidated data, later replaced by historical.
  - `historical/`: the FAQ https://www.chmi.cz/-/kdy-budou-zve%C5%99ejn%C4%9Bna-data-z-posledn%C3%ADho-roku says *„po skončení kalendářního roku jsou do konce dubna roku následujícího data nahrána do adresáře Historical“*. NKOD descriptions agree: *„K pravidelné aktualizaci dat dochází jednou ročně … do konce dubna roku následujícího“* (accrualPeriodicity ANNUAL).
- **V** Actual publication was **later than promised**: the 2025 hydro daily files have Last-Modified **2026-05-21** (552 files).
- **V** **Bulk re-publication happens:**
  - 38,733 of 39,291 hydro daily files have mtime 2025-07-01 12:07 (all years, same minute);
  - all 1,537 meteo daily station files have mtime 2026-09-04;
  - station 0-203-1-001000: 1988–2024 all at 2025-07-01, 2025 at 2026-05-21.

  So Last-Modified is a publication timestamp, not a data-change date. Expect mass `newer` statuses after a republish; sha256 dedup is essential. For meteo daily, one republish = 25 GB if re-downloaded for all stations.
- **V** Archive depth example: station `0-203-1-001000` has DQ for 1988–2025 (38 files). The 1988 file is only 1945 B (partial year).
- **V** Time zone: the PDF says *„datum a čas [SEČ a SELČ]“*, but JSON timestamps carry `Z`. In `now_0-203-1-001000.json` the last value is `2026-10-18T16:40:00Z` and the file Last-Modified is 17:00:08 GMT. A CEST value labelled `Z` would be in the future, so the `Z` is real UTC (I, strong). This resolves the audit open question for `now`; the historical daily timestamps are `T00:00:00Z` day stamps.
- **V** A planned API is mentioned but does not exist yet. The data-a-vyhodnoceni page: *„…bude vybudována nezbytná infrastruktura, nástroj zajišťující propojení LKOD a NKOD spolu s API rozhraním pro automatické stahování publikovaných dat“* (NPO project). Today only static files exist.

## 6. Docs, catalogues, contacts
- **V** Docs: `https://opendata.chmi.cz/hydrology/read_me/` contains:
  - Popis_datovych_sad_historical.pdf, Popis_kodu_historical.pdf, Popis_kodu_now_a_recent.pdf, Popis_datovych_sad_characteristic.pdf, watersheds_attributies.pdf;
  - „Průvodce otevřenými daty hydrologie.pdf“ (a 1-page diagram, no text terms).

  Also `hydrology/hydrologicka_data_now_a_recent_popis.pdf`, `meteorology/climate/Klimatologicka_data_popis.pdf` and `air_quality/description_air_quality_opendata.pdf`. **None of the PDFs contain licence text** (grep of the extracted text).
- **V** JSON schemas: `https://opendata.chmi.cz/hydrology/historical/metadata/H_SCHEMA_{DQ,HQ,MQ,MMQ,NATQ,OF,OH,OH7,OT,OT7}.json`.
- **V** Catalogues:
  - NKOD https://data.gov.cz/datasets?keywords=Czech%20Hydrometeorological%20Institute ; publisher IRI `https://data.gov.cz/zdroj/poskytovatel/00020699`; 221 datasets (`nkod_chmi_datasets_2026-10-18.csv`);
  - LKOD https://lkod.cz/catalog/chmi ;
  - ISO metadata at geoportal Micka (e.g. https://geoportal.gov.cz/php/micka/record/basic/674d71e8-66bc-429b-9311-16ba0fc0a8017c for hydro daily).
- **V** Contacts:
  - general: chmi@chmi.cz, +420 222 222 215, Na Šabatce 2050/17, 143 06 Praha 4, IČO 00020699, datová schránka e37djs6;
  - data orders: klima@chmi.cz;
  - commercial: komerce@chmi.cz.

  NKOD contact points are named staff (not reproduced).

## 7. Gaps vs the Archiwista contract (wymagania-imgwtools.md IMGW-3/5/9; SPEC 4.8.6, IMGW-15..19)
1. **Sidecar constants** (V, repo): `license.id`, `dataset`, `country` and `provider` consts and the reader's `const="IMGW-PIB"` block `cz.chmi.*` (§1.2). This needs an IMGW-13 decision.
2. **Update signal** (V): ETag and Last-Modified exist for every file, so IMGW-5 statuses `current`/`newer`/`missing` map 1:1, and `unverifiable` should not occur for files. However, Last-Modified reflects bulk republishing, so `label_source: "last_modified"` labels change with no data change. Content identity must come from sha256.
3. **Request volume** (V): a country-wide check of hydro daily is 39,291 files (about 49 per station). Archiwista's risk table says "setki zapytań". Per-station HEADs are fine; for wide areas, use one listing GET (§4).
4. **Meteo daily granularity** (V): `meteorology/climate/historical/data/daily/dly-<WIGOS>.json` holds one file per station for the whole history (up to 97.7 MB), not per year. A 1:1 archive slot therefore means re-downloading the full history on every republish. All files were re-published on 2026-09-04. The SPEC 4.8.6 per-year assumption does not hold for meteo, and plan sizes must use Content-Length. (`historical_csv/` per-variable trees exist; their size was not measured — U.)
5. **Station catalogue licence** (V): use `hydrology/*/metadata/meta1.json` and `meteorology/climate/historical/metadata/meta1.json` (CC BY). Do NOT use the geoportal station GPKG/WFS (CC BY-NC-ND).
6. **Purpose notice** (V): the IMGW purpose warning must not be emitted for ČHMÚ data (commercial use allowed). IMGW-19 asks for "atrybucja wymagana przez ČHMÚ". No fixed wording exists, so IMGWTools must define it (proposal in §1.2).
7. **Year publication** (V): the "end of April" promise slipped to 21 May for 2025. `check_store` should treat a missing previous year before about June as "not yet published", not an error. This is consistent with IMGW-16's "brak pliku = missing bez błędu".
