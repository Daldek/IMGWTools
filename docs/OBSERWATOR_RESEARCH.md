# Obserwator — badanie wykonalności rozszerzenia poza IMGW

**Data badania:** 2026-08-11 · **Zakres:** Słowacja (SHMÚ), Czechy (ČHMÚ), Niemcy (DWD/WSV), Morze Bałtyckie
**Metoda:** analiza kodu IMGWTools 2.1.1 + research internetowy z weryfikacją endpointów na żywo (WebFetch).

---

## 1. Podsumowanie wykonawcze

Rozszerzenie biblioteki na kraje sąsiednie jest wykonalne, ale kraje różnią się dojrzałością otwartych danych w sposób zasadniczy:

| Kraj / obszar | Dane bieżące | Archiwa hydro | Archiwa meteo | Stacje (lat/lon) | Ostrzeżenia | Ocena ogólna |
|---|---|---|---|---|---|---|
| **Czechy (ČHMÚ)** | ✅ JSON per stacja | ✅ JSON per stacja/rok | ✅ JSON + CSV | ✅ meta1.json | ✅ CAP XML | **Bardzo dobra** — integrować w pierwszej kolejności |
| **Niemcy (DWD+WSV)** | ✅ PEGELONLINE REST | ⚠️ tylko portale landowe | ✅ DWD CDC (od 1891!) | ✅ stations.json + TXT | ✅ CAP XML + LHP | **Dobra** — z luką w archiwach hydro |
| **Słowacja (SHMÚ)** | ⚠️ tylko scraping HTML (hydro) | ❌ brak otwartych | ⚠️ tylko „recent" CSV | ⚠️ INSPIRE/metadane | ✅ Meteoalarm CAP | **Słaba** — 2–4 lata za PL/CZ, obserwować |
| **Bałtyk** | ✅ mareografy już w API IMGW(!) + SMHI/BSH/EMODnet | ⚠️ PSMSL/EMODnet | n/d | ⚠️ różne | ⚠️ różne | **Dobra** — częściowo już działa |

Kluczowe odkrycie: **polskie stacje mareograficzne (Świnoujście, Hel, Gdańsk, Kołobrzeg, Ustka, Władysławowo…) już są zwracane przez `fetch_hydro_current()`** — biblioteka „umie" dane bałtyckie, tylko ich nie eksponuje. Nie ma ich natomiast w `lista_stacji_hydro.csv`, więc obecna lista stacji ich nie widzi.

Wspólny mianownik regionu: **CAP XML jako format ostrzeżeń** (CZ, DE, SK przez Meteoalarm) oraz **model „serwer plików + przewidywalne URL-e"** (ČHMÚ, DWD, SHMÚ open data) — czyli dokładnie filozofia `url_builder.py`. Architektura koncepcyjnie przenosi się 1:1; problemem jest kod, nie koncepcja.

---

## 2. Stan obecny biblioteki (wnioski z analizy kodu)

### 2.1 Co biblioteka potrafi dziś

Trzy hardkodowane bazy URL (`url_builder.py:64-66`): archiwa `danepubliczne.imgw.pl/data/...`, API bieżące `danepubliczne.imgw.pl/api/data`, PMAXTP `powietrze.imgw.pl/tpmax-api/point`. Publiczne API: `fetch_hydro_current`, `fetch_synop`, `fetch_warnings`, `fetch_pmaxtp`, `download_hydro_data`, `download_meteo_data`, listy stacji, parsery CSV, buildery URL — wszystko wyłącznie IMGW.

### 2.2 Co jest generyczne (do reużycia bez zmian)

- **Modele bieżące** (`models.py`): pola neutralne z jednostkami w nazwach (`water_level_cm`, `flow_m3s`); cała specyfika IMGW zamknięta w `from_api_response()` — dla nowego kraju wystarczy nowy mapper.
- **Parsery CSV — mechanika**: auto-detekcja separatora, kodowania (BOM), cudzysłowów — te same problemy wystąpią w danych DWD (średniki, latin-1) i SHMÚ.
- **Warstwa SQLite** (`connection.py`), wzorzec `cached_ranges` + lazy loading.
- **Dataclass `DownloadURL`**, hierarchia wyjątków, podział na extras w `pyproject.toml`, wzorzec testów (respx + fixtury).

### 2.3 Co jest twardo związane z IMGW (do refaktoryzacji)

- `url_builder.py` — brak jakiejkolwiek abstrakcji „provider"; enumy pełnią podwójną rolę: semantyka + segment URL (`HydroInterval.DAILY = "dobowe"`).
- `fetch.py` — bbox Polski zaszyty w module, komunikaty błędów „IMGW API...", 12× powtórzony boilerplate HTTP bez wspólnego klienta/retry/User-Agent.
- **Schemat SQLite bez kolumny `provider`** — największe pojedyncze ryzyko: kody stacji SHMÚ/ČHMÚ/DWD mogą kolidować z IMGW i nadpisywać dane. Konieczna migracja do v2.
- Rok hydrologiczny XI–X jako kolumny kanoniczne (`hydro_year`/`hydro_month`) — dane morskie w ogóle go nie używają; lepiej kanonizować `measurement_date`.
- Nazwy publiczne: `IMGWError`, `IMGW_ENCODING`, prefix env `IMGW_`, CLI `imgw`, polskie stringi w sygnaturach (`interval="dobowe"`, `subtype="klimat"`).
- Dług do usunięcia przed refaktorem: `core/imgw_api.py`, `core/imgw_datastore.py`, `core/imgw_spatial.py` (~817 linii legacy, złamane importy, `wget`, ścieżki windowsowe); duplikacja parsowania stacji w 3 miejscach (`stations.py`, `db/parsers.py`, `web/app.py`); placeholdery w `api/routes/` (zahardkodowane 2 stacje); statyczne `le=2024` w schematach API.

---

## 3. Czechy — ČHMÚ (najlepszy kandydat)

Od 1.01.2025 działa ustawa 262/2024 Sb. i „Narodowa baza danych hydrometeorologicznych" = **https://opendata.chmi.cz** — statyczny serwer plików z przewidywalnymi URL-ami, **CC BY 4.0, bez rejestracji i klucza**. Model identyczny z filozofią IMGWTools.

### Hydro
- **Bieżące** (zweryfikowane na żywo): `https://opendata.chmi.cz/hydrology/now/data/{WIGOS_ID}.json` — H (cm), Q (m³/s), temperatura wody, krok 10 min, dopis co godzinę. Np. `0-203-1-001000.json`.
- **Ostatni rok**: `/hydrology/recent/`.
- **Archiwa** (zweryfikowane): `/hydrology/historical/data/daily/H_{WIGOS}_DQ_{ROK}.json` (dobowe H/Q), także `HQ` (godzinowe), `MQ` (miesięczne), `MMQ` (maksima). Czystszy format niż ZIP+CSV IMGW. Głębokość archiwum różna per stacja (404 → sondować).
- **Stacje**: `/hydrology/now/metadata/meta1.json` — nazwa, rzeka, współrzędne + **progi stopni powodziowych SPA1–3** (odpowiednik stanów ostrzegawczych/alarmowych IMGW).

### Meteo
- `/meteorology/climate/`: `now/` (10-min i 1-h JSON per stacja), `recent/` (dobowe `dly-{WSI}-{YYYYMM}.json`, miesięczne), `historical/` (pliki stacyjne za cały okres pomiarów; 10-min/1-h od 2018), `historical_csv/` (CSV per element). ID stacji = WIGOS (np. `0-20000-0-11406`).

### Ostrzeżenia
- CAP XML: `/meteorology/weather/alerts/cap/` — pliki ~1–2 MB, cały kraj (gminy ORP), CZ+EN, obejmują też hydro (SPA).

### Ograniczenia
Granulacja per stacja (brak endpointu „cały kraj naraz" jak w IMGW — pobranie stanu kraju = setki żądań); ogromne listingi katalogów (konstruować nazwy plików, nie listować); dokumentacja po czesku w PDF; drobna niespójność stref czasowych (PDF: SEČ vs faktycznie UTC w JSON).

---

## 4. Niemcy — DWD + PEGELONLINE (dobre, z jedną luką)

### PEGELONLINE (WSV) — hydro bieżące
REST API JSON (zweryfikowane): `https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json` — ~660 stacji z uuid, współrzędnymi, rzeką. Pomiary: `.../stations/{id}/W/currentmeasurement.json` (z klasyfikacją stanu `stateMnwMhw`/`stateNswHsw` — odpowiednik `water_state` z hydro-back.imgw.pl), szeregi `measurements.json?start=P15D`. Aktualizacja co 15 min, bez rejestracji, licencja otwarta (DL-DE). **Uwaga: tylko ~31 dni wstecz — to nie archiwum.**

### DWD Open Data — meteo/klimat
`https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/` — interwały od 1-minutowych po roczne, dane od **1891 r.** ZIP+CSV (średniki, braki `-999`), podział `historical/` + `recent/` (ostatnie ~500 dni, codziennie). Lista stacji w `*_Beschreibung_Stationen.txt` (stałoszerokościowy, latin-1). Licencja CC BY 4.0 / GeoNutzV, bez klucza. Haczyk dla url_buildera: nazwy plików historycznych zawierają daty serii (`tageswerte_KL_00003_18910101_20110331_hist.zip`) — trzeba raz sparsować listing katalogu (analogia do problemu synop per-station w IMGW).

### Ostrzeżenia
DWD CAP: `https://opendata.dwd.de/weather/alerts/cap/`. Powodziowe: hochwasserzentralen.de (LHP) — webservices JSON/GeoJSON (status ~1200 wodowskazów, bez wartości pomiarów; gotowy klient PyPI `de-hochwasserzentralen`).

### Główna luka: archiwa hydro
Wieloletnie archiwa stanów/przepływów (odpowiednik `codz_`/`mies_`) **nie mają źródła federalnego** — są rozproszone po 16 portalach landowych (np. GKD Bayern, gkd.bayern.de, CC BY 4.0, eksport CSV per stacja). GRDC (BfG) ma długie serie, ale research-only. Realistyczny zakres v1: DWD + PEGELONLINE + LHP; archiwa landowe jako opcjonalne pluginy (zacząć od Bawarii).

**Prior art:** biblioteka `wetterdienst` (github.com/earthobservations/wetterdienst) już implementuje DWD — warto przejrzeć przed pisaniem własnego parsera.

---

## 5. Słowacja — SHMÚ (najsłabsza, obserwować)

- **opendata.shmu.sk** (uruchomiony ~2025, wzorowany na czeskim): serwer plików CSV, **CC BY 4.0, bez klucza** — ale głównie meteo „recent" (klimat, opady, radar, jakość powietrza), **bez katalogu hydro i bez głębokiej historii**.
- **Hydro bieżące**: wyłącznie HTML na shmu.sk (`?page=1&id=hydro_vod_all`) — wymagany scraping; strona miewa awarie (całodniowa przerwa I 2026).
- **Archiwa hydro**: nieotwarte — „Modrá platforma" (mp.shmu.dcmc.sk, CKAN CC0) jest jawnie w becie: słowniki + aplikacja z danymi 2018–2023, bez udokumentowanego API. Starsze serie tylko na wniosek/odpłatnie.
- **Ostrzeżenia**: dobrze przez Meteoalarm (feeds.meteoalarm.org, ATOM/CAP, darmowe).
- **Ryzyko**: planowane docelowe REST API meteo ma wymagać rejestracji i limitów (~1000 żądań/15 min).

**Rekomendacja:** w v1 tylko moduł opendata.shmu.sk (pliki CSV) + Meteoalarm; hydro oznaczyć jako eksperymentalne lub odłożyć do czasu dojrzenia Modrej platformy.

---

## 6. Morze Bałtyckie

### Polska — częściowo już działa
- **Mareografy IMGW są w `api/data/hydro`** (zweryfikowane: Świnoujście id 153140010, `stan_wody: 524 cm`, `rzedna_zerawodowskazu: -4.915` → poziom morza; też Hel, Gdańsk, Kołobrzeg, Ustka, Władysławowo, Gdynia, Puck, stacje zalewów). Wystarczy filtr/moduł „morze" w istniejącym `fetch_hydro_current()`.
- **Ale nie ma ich w `lista_stacji_hydro.csv`** — obecna lista stacji ich nie pokazuje; brać z API bieżącego lub hydro-back.imgw.pl. Obecność mareografów w archiwach `codz_`/`mies_` — do zweryfikowania przy implementacji.
- baltyk.imgw.pl (prognozy MIKE21/SWAN, zlodzenie) — tylko HTML/obrazki, bez API. SatBałtyk, Urzędy Morskie — bez otwartego API.
- Polska **nie publikuje otwartych danych o falowaniu i zasoleniu** — tylko modele CMEMS lub boje sąsiadów.

### Zagranica (ranking dopasowania do modelu „generujemy linki")
1. **SMHI (Szwecja)**: `https://opendata-download-ocobs.smhi.se/api` — REST do CSV/JSON, parametry: poziom morza, T, zasolenie, falowanie, prądy, z pełnym archiwum (`corrected-archive`). CC BY 4.0, bez klucza. Wzorcowe.
2. **BSH (Niemcy)**: OGC API Features `https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast` — prognozy + obserwacje poziomu wody wybrzeża bałtyckiego, JSON, CC BY 4.0, bez rejestracji. Surowe pomiary niemieckich stacji bałtyckich (Kiel, Warnemünde, Sassnitz…) — przez PEGELONLINE.
3. **EMODnet Physics ERDDAP**: `https://erddap.emodnet-physics.eu/erddap/` — paneuropejskie in-situ (poziom morza NRT 5/60-min, T, S, falowanie) + PSMSL (Świnoujście od 1811 r.!); HTTP GET → CSV/JSON/NetCDF, bez rejestracji. Minus: wydajność, trzeba znać PLATFORMCODE.
4. **FMI (Finlandia)**: WFS XML — otwarte, ale format cięższy.
5. **Copernicus Marine**: najbogatsze (modele, SST, reanaliza od 1993, in-situ od 1841), ale wymaga konta i toolboxa `copernicusmarine` — nie da się wygenerować anonimowego linku. Ewentualnie opcjonalny extras `obserwator[cmems]`.
6. **IOC SLSMF**: otwarte API, ale brak polskich stacji. **HELCOM/ICES**: dane kampanijne, plikowe — nie operacyjne.

---

## 7. Rekomendowana kolejność prac

1. **Sprzątanie** — usunąć legacy `core/imgw_api.py`, `imgw_datastore.py`, `imgw_spatial.py`; skonsolidować 3× zduplikowane parsowanie stacji; naprawić placeholdery w `api/routes/`.
2. **Schemat DB v2** — kolumna `provider` we wszystkich tabelach i kluczach UNIQUE + realna migracja (warunek konieczny przed jakimkolwiek nowym krajem).
3. **Warstwa providerów** — `providers/base.py` (Protocol: `list_stations`, `fetch_current`, `fetch_warnings`, `build_archive_url`, `parse_archive` + `ProviderInfo` z bbox, kodowaniem, zakresami lat); przenieść IMGW za ten interfejs **bez zmiany publicznego API**; wspólny helper HTTP (sync/async, retry, User-Agent).
4. **Provider #1: ČHMÚ** — najlepszy stosunek wartości do wysiłku (JSON, CC BY 4.0, pełen zakres funkcji). Przy okazji: wspólny parser CAP XML (posłuży CZ, DE i Meteoalarm).
5. **Provider #2: Niemcy** — PEGELONLINE (bieżące hydro) + DWD CDC (archiwa meteo) + CAP.
6. **Moduł Bałtyk** — filtr mareografów w istniejącym API IMGW + SMHI + BSH; EMODnet jako źródło paneuropejskie.
7. **Rebranding na Obserwator** — dopiero po (3): pakiet `obserwator`, CLI `obserwator` z aliasem `imgw`, `ObserwatorError` z aliasem `IMGWError`, env `OBSERWATOR_` z fallbackiem `IMGW_`.
8. **Słowacja** — na końcu, zakres minimalny (opendata.shmu.sk + Meteoalarm), monitorować Modrą platformę.

---

## 8. Kluczowe źródła

**Czechy:** [opendata.chmi.cz](https://opendata.chmi.cz/) · [przykład hydro now](https://opendata.chmi.cz/hydrology/now/data/0-203-1-001000.json) · [archiwum dobowe 2020](https://opendata.chmi.cz/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2020.json) · [meta1.json](https://opendata.chmi.cz/hydrology/now/metadata/meta1.json) · [opis danych klimat (PDF)](https://opendata.chmi.cz/meteorology/climate/Klimatologicka_data_popis.pdf) · [CAP](https://opendata.chmi.cz/meteorology/weather/alerts/cap/)

**Niemcy:** [PEGELONLINE stations.json](https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations.json) · [DWD CDC](https://opendata.dwd.de/climate_environment/CDC/) · [DWD daily/kl historical](https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/historical/) · [DWD CAP](https://opendata.dwd.de/weather/alerts/cap/) · [LHP developers](https://www.hochwasserzentralen.de/developers/) · [GKD Bayern](https://www.gkd.bayern.de/) · [wetterdienst (prior art)](https://github.com/earthobservations/wetterdienst)

**Słowacja:** [opendata.shmu.sk](https://opendata.shmu.sk/) · [SHMÚ wodowskazy (HTML)](https://www.shmu.sk/sk/?page=1&id=hydro_vod_all) · [Modrá platforma](https://mp.shmu.dcmc.sk/) · [CKAN SHMÚ](https://opendata.shmu.dcmc.sk/en/dataset) · [Meteoalarm feeds](https://feeds.meteoalarm.org/)

**Bałtyk:** [IMGW api/data/hydro](https://danepubliczne.imgw.pl/api/data/hydro) · [SMHI ocobs](https://opendata-download-ocobs.smhi.se/api) · [BSH WaterLevelForecast](https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast) · [EMODnet ERDDAP](https://erddap.emodnet-physics.eu/erddap/) · [FMI WFS](https://opendata.fmi.fi/wfs) · [Copernicus Marine](https://data.marine.copernicus.eu) · [IOC SLSMF](https://www.ioc-sealevelmonitoring.org)
