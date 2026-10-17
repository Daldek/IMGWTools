# Obserwator 3.0 — Specyfikacja techniczna

**Status:** Draft do review · **Data:** 2026-08-11
**Podstawa:** `docs/OBSERWATOR_RESEARCH.md` (badanie wykonalności z 2026-08-11)

---

## 1. Cel i zakres wydania 3.0

Przekształcenie `imgwtools` 2.1.1 w `obserwator` 3.0.0 — wieloźródłową bibliotekę danych hydro-meteorologicznych. Zakres pierwszego wydania:

1. Warstwa providerów (abstrakcja źródła danych) i przeniesienie IMGW za jej interfejs.
2. Drugi provider: **ČHMÚ** (Czechy, opendata.chmi.cz).
3. Pełny rebranding **bez aliasów wstecznych** — konsumenci są pod naszą kontrolą i migrują jednorazowo.
4. Publiczne API w języku **angielskim** (enumy, parametry, nazwy funkcji).
5. Aktualizacja wszystkich 4 interfejsów: biblioteka, CLI, REST API, Web GUI.

Poza zakresem 3.0 (przewidziane w architekturze, realizowane w kolejnych wydaniach): providery DE (PEGELONLINE, DWD), moduł Bałtyk, SK (opendata.shmu.sk + Meteoalarm).

### Decyzje kierunkowe (zatwierdzone przez właściciela)

| Decyzja | Wybór | Uzasadnienie |
|---|---|---|
| Kompatybilność wsteczna | **Brak** — czysty break | Kontrola nad wszystkimi konsumentami; priorytet: czystość architektury |
| Rebranding | Pełny od razu (pakiet, CLI, env, wyjątki) | Jedna nazwa wszędzie, bez okresu przejściowego |
| Język API | Angielski | Spójność przy wielu krajach; polskie stringi zostają wyłącznie jako segmenty URL wewnątrz providera IMGW |
| Wersja | 3.0.0 (SemVer — major break) | Zgodnie z PRD §10 |

---

## 2. Nazewnictwo i pakietowanie

| Element | Było (2.1.1) | Będzie (3.0.0) |
|---|---|---|
| Pakiet Python / PyPI | `imgwtools` | `obserwator` |
| Katalog źródeł | `src/imgwtools/` | `src/obserwator/` |
| Entry point CLI | `imgw` | `obserwator` |
| Prefix env | `IMGW_` | `OBSERWATOR_` |
| Wyjątki | `IMGWError`, `IMGWConnectionError`, … | `ObserwatorError`, `SourceConnectionError`, `SourceDataError`, `SourceValidationError`, `ProviderNotFoundError` |
| Plik bazy (domyślny) | `./data/imgw_hydro.db` | `./data/obserwator.db` |
| Extras | `[cli]`, `[api]`, `[db]`, `[full]` | bez zmian koncepcyjnie; providery NIE są osobnymi extras w 3.0 (rdzeń: `httpx` + `pydantic` wystarcza dla IMGW i ČHMÚ) |

Stała `IMGW_ENCODING` znika z publicznego API — kodowanie jest własnością providera (`ProviderInfo.archive_encoding`).

---

## 3. Architektura warstwy providerów

### 3.1 Struktura katalogów

```
src/obserwator/
├── __init__.py              # publiczne API (fasada + rejestr providerów)
├── _version.py
├── config.py                # pydantic-settings, env_prefix="OBSERWATOR_"
├── exceptions.py
├── models.py                # modele KANONICZNE (wspólne dla wszystkich providerów)
├── http.py                  # wspólny klient HTTP (sync+async, retry, User-Agent)
├── providers/
│   ├── __init__.py          # registry: get_provider(), list_providers()
│   ├── base.py              # DataProvider (Protocol), ProviderInfo, Capability
│   ├── imgw/
│   │   ├── __init__.py      # class ImgwProvider
│   │   ├── urls.py          # dawny url_builder.py (bez zmian logiki)
│   │   ├── mappers.py       # JSON IMGW → modele kanoniczne (dawne from_api_response)
│   │   └── parsers.py       # parsery CSV archiwów (CP1250, rok hydrologiczny)
│   └── chmi/
│       ├── __init__.py      # class ChmiProvider
│       ├── urls.py          # wzorce URL opendata.chmi.cz
│       ├── mappers.py       # JSON ČHMÚ → modele kanoniczne
│       └── metadata.py      # meta1/meta2.json → stacje, progi SPA
├── parsing/
│   ├── csv_utils.py         # _detect_delimiter, _decode_content, _iter_rows, _safe_float
│   └── cap.py               # parser CAP XML (ostrzeżenia; użyje go ČHMÚ, później DE/Meteoalarm)
├── db/                      # cache SQLite (schemat v2, patrz §7)
├── api/                     # FastAPI (patrz §9)
├── cli/                     # Typer (patrz §8)
└── web/                     # Web GUI (patrz §10)
```

Usuwane bez następcy: `core/imgw_api.py`, `core/imgw_datastore.py`, `core/imgw_spatial.py` (legacy, ~817 linii), `urls.py` i `parsers.py` jako re-eksporty na poziomie roota (zastąpione przez przestrzenie providerów).

### 3.2 Interfejs providera (`providers/base.py`)

```python
class Capability(StrEnum):
    """Zdolności providera — provider deklaruje, co potrafi."""
    CURRENT_HYDRO = "current_hydro"        # bieżące stany/przepływy
    CURRENT_WEATHER = "current_weather"    # bieżące dane meteo (d. "synop")
    ARCHIVE_HYDRO = "archive_hydro"        # archiwa hydro
    ARCHIVE_WEATHER = "archive_weather"    # archiwa meteo
    STATIONS = "stations"                  # lista stacji ze współrzędnymi
    WARNINGS = "warnings"                  # ostrzeżenia
    PMAX = "pmax"                          # opady maksymalne prawdopodobne (IMGW-only)


@dataclass(frozen=True)
class ProviderInfo:
    id: str                    # "imgw", "chmi"
    name: str                  # "IMGW-PIB", "ČHMÚ"
    country: str               # ISO 3166-1 alpha-2: "PL", "CZ"
    bbox: BBox                 # walidacja współrzędnych (zamiast stałych POLAND_*)
    capabilities: frozenset[Capability]
    license: str               # np. "CC BY 4.0"
    attribution: str           # wymagany tekst atrybucji
    archive_encoding: str      # "cp1250" (IMGW) / "utf-8" (ČHMÚ)


class DataProvider(Protocol):
    """Kontrakt providera. Metody spoza capabilities rzucają NotSupportedError."""
    info: ProviderInfo

    def list_stations(self, kind: StationKind) -> list[Station]: ...
    def fetch_current(self, kind: DataKind, station_id: str | None = None) -> list[Measurement]: ...
    def fetch_warnings(self, kind: WarningKind) -> list[Warning_]: ...
    def build_archive_urls(self, query: ArchiveQuery) -> list[DownloadURL]: ...
    def download_archive(self, query: ArchiveQuery) -> bytes: ...
    def parse_archive(self, data: bytes, query: ArchiveQuery) -> list[ArchiveRecord]: ...
    # każda metoda ma wariant async: alist_stations(), afetch_current(), ...
```

Rejestr: `providers/__init__.py` utrzymuje słownik `{id: klasa}`; `get_provider("chmi")` zwraca singleton. Rejestracja przez wpis w słowniku (bez entry_points w 3.0 — wrócimy do tego, gdy providery staną się zewnętrznymi pakietami).

### 3.3 Modele kanoniczne (`models.py`)

Zachowujemy sprawdzoną zasadę z 2.x: **pola neutralne językowo, jednostki w nazwach, cała specyfika źródła w mapperach providera**.

```python
class Station(BaseModel):
    provider: str                      # "imgw" / "chmi"
    station_id: str                    # natywne ID providera (IMGW: "153140010", ČHMÚ: WIGOS "0-203-1-001000")
    name: str
    kind: StationKind                  # HYDRO / WEATHER
    latitude: float | None
    longitude: float | None
    river: str | None = None
    elevation_m: float | None = None
    alert_levels: AlertLevels | None = None   # progi: warning/alarm (IMGW) ≙ SPA1-3 (ČHMÚ)
    water_state: str | None = None

class HydroMeasurement(BaseModel):
    provider: str
    station_id: str
    timestamp: datetime                # zawsze aware, UTC
    water_level_cm: float | None
    flow_m3s: float | None
    water_temp_c: float | None

class WeatherMeasurement(BaseModel):   # d. SynopData
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
    severity: str                      # skala CAP: Minor/Moderate/Severe/Extreme (IMGW mapowane)
    area: str
    valid_from: datetime | None
    valid_to: datetime | None
    description: str | None
```

Klucz tożsamości stacji w całym systemie: para **`(provider, station_id)`** — nigdy samo `station_id`.

### 3.4 Enumy publiczne (angielskie)

```python
class Interval(StrEnum):
    DAILY = "daily"            # IMGW: "dobowe",   ČHMÚ: DQ
    HOURLY = "hourly"          # IMGW: brak,       ČHMÚ: HQ
    MONTHLY = "monthly"        # IMGW: "miesieczne", ČHMÚ: MQ
    SEMI_ANNUAL = "semi_annual"  # IMGW: "polroczne_i_roczne", ČHMÚ: brak

class WeatherSubtype(StrEnum):
    CLIMATE = "climate"        # IMGW: "klimat" (k)
    PRECIPITATION = "precip"   # IMGW: "opad" (o)
    SYNOP = "synop"            # IMGW: "synop" (s)
```

Mapowanie enum → natywny segment URL/typ pliku jest wewnętrzną sprawą providera (`providers/imgw/urls.py`, `providers/chmi/urls.py`). Kombinacje niedostępne u danego providera → `NotSupportedError` z czytelnym komunikatem (jak dziś `ValueError` dla terminowe+opad).

### 3.5 Wspólny klient HTTP (`http.py`)

Eliminuje 12× powtórzony boilerplate z `fetch.py` 2.x:

```python
def get_json(url, *, timeout=30.0, headers=None) -> Any
def get_bytes(url, *, timeout=120.0, headers=None) -> bytes
# + warianty async; wspólne: retry (3× z backoff), User-Agent "obserwator/{version}",
# mapowanie wyjątków httpx → SourceConnectionError (z nazwą providera w komunikacie)
```

---

## 4. Publiczne API biblioteki (fasada)

Fasada w `obserwator/__init__.py` — cienka warstwa nad rejestrem providerów. Wszystkie funkcje przyjmują `provider: str = "imgw"` (IMGW pozostaje domyślny — zachowanie „polskie z urodzenia", świadoma decyzja produktowa).

```python
from obserwator import (
    # fasada
    fetch_hydro_current,      # (provider="imgw", station_id=None) -> list[HydroMeasurement]
    fetch_weather_current,    # d. fetch_synop
    fetch_warnings,           # (kind, provider="imgw") -> list[Warning_]
    fetch_pmax,               # d. fetch_pmaxtp; deleguje do providerów z Capability.PMAX
    list_stations,            # (kind, provider="imgw") -> list[Station]
    build_archive_urls,       # (ArchiveQuery) -> list[DownloadURL]
    download_archive,         # (ArchiveQuery) -> bytes
    # rejestr
    get_provider, list_providers,
    # modele, enumy, wyjątki — jak w §3
)
```

`ArchiveQuery` (pydantic) zastępuje rozproszone parametry `interval/year/month/param/subtype`:

```python
class ArchiveQuery(BaseModel):
    provider: str = "imgw"
    kind: DataKind                       # HYDRO / WEATHER
    interval: Interval
    year: int
    month: int | None = None
    station_id: str | None = None        # wymagane przez ČHMÚ (pliki per stacja), ignorowane przez IMGW
    param: HydroParam | None = None      # IMGW polroczne: T/Q/H
    subtype: WeatherSubtype | None = None
```

Walidacja krzyżowa (np. `month` wymagany dla IMGW daily <2023, `station_id` wymagany dla ČHMÚ) w walidatorach providera, nie w modelu — model tylko niesie dane.

Wszystkie funkcje sync mają odpowiedniki `a*` (async), implementowane raz — wariant sync jest wrapperem na async (`anyio`/`asyncio.run` w cienkiej warstwie), co likwiduje duplikację sync/async z 2.x.

---

## 5. Provider IMGW (`providers/imgw/`)

Przeniesienie istniejącej, przetestowanej logiki bez zmian merytorycznych:

- `urls.py` ← `core/url_builder.py` (wzorce `codz_`/`mies_`/`polr_`, foldery meteo 5-letnie, wyjątki kombinacji). Stałe URL przenoszone do modułu providera.
- `mappers.py` ← metody `from_api_response()` z `models.py` 2.x (mapowanie `id_stacji`, `stan_wody`, `przeplyw`, `województwo`…).
- `parsers.py` ← `db/parsers.py` minus generyczne helpery (te idą do `parsing/csv_utils.py`). Rok hydrologiczny (XI–X), kody braków (`9999`, `99999.999`, `99.9`), format `"Odra (1)"` — zostają tutaj jako wiedza providera.
- Stacje: trzy źródła jak dziś (CSV hydro, CSV meteo, hydro-back.imgw.pl z nagłówkiem Referer) — skonsolidowane w jednym miejscu; **duplikaty w `web/app.py` i `db/cache_manager.py` usuwane**, warstwy wołają providera.
- `ProviderInfo`: bbox Polski (49.0–55.0 / 14.0–24.5), `capabilities = {CURRENT_HYDRO, CURRENT_WEATHER, ARCHIVE_HYDRO, ARCHIVE_WEATHER, STATIONS, WARNINGS, PMAX}`, `archive_encoding="cp1250"`, atrybucja „Źródłem pochodzenia danych jest IMGW-PIB".
- Znane rozszerzenie z researchu (nie blokuje 3.0, ale warto od razu): stacje mareograficzne są w API bieżącym, lecz nie w CSV stacji — `list_stations` dla IMGW powinno łączyć oba źródła.

## 6. Provider ČHMÚ (`providers/chmi/`)

Na podstawie zweryfikowanych endpointów (research §3):

| Funkcja | Źródło | Wzorzec URL |
|---|---|---|
| `fetch_current(HYDRO, station_id)` | hydrology/now | `https://opendata.chmi.cz/hydrology/now/data/{WIGOS}.json` (10-min H/Q/T, dopis co 1 h) |
| `fetch_current(WEATHER, station_id)` | climate/now | `.../meteorology/climate/now/data/10m-{WSI}-{YYYYMMDD}.json` i `1h-…` |
| `build_archive_urls(HYDRO, daily)` | historical | `.../hydrology/historical/data/daily/H_{WIGOS}_DQ_{ROK}.json` (analogicznie `HQ`, `MQ`, `MMQ`) |
| `build_archive_urls(WEATHER, …)` | climate/historical | `dly-{WSI}.json`, `mly-{WSI}.json`, CSV per element w `historical_csv/` |
| `list_stations(HYDRO)` | metadata | `.../hydrology/now/metadata/meta1.json` (nazwa, rzeka, GEOGR1/2, progi SPA1–3 → `alert_levels`) |
| `fetch_warnings(…)` | alerts | `.../meteorology/weather/alerts/cap/alert_cap_50_*.xml` → `parsing/cap.py` |

Decyzje implementacyjne:

1. **`station_id` obowiązkowe** dla `fetch_current` i archiwów (format WIGOS) — ČHMÚ nie ma endpointu „cały kraj". Fasada NIE emuluje go pętlą po stacjach (setki żądań); jeśli użytkownik chce wiele stacji, iteruje świadomie sam lub używa cache DB.
2. **404 archiwum = `ArchiveNotAvailableError`** (podklasa `SourceDataError`) — głębokość archiwum różni się per stacja; nie sondujemy automatycznie.
3. Czasy: JSON ČHMÚ niesie sufiks `Z` — parsujemy jako UTC (rozbieżność z PDF-dokumentacją odnotowana w docstringu).
4. Ostrzeżenia CAP: pliki ~1–2 MB — parser strumieniowy (`iterparse`), zwraca `Warning_` z mapowaniem severity CAP wprost.
5. `ProviderInfo`: bbox CZ (48.5–51.1 / 12.0–18.9), licencja CC BY 4.0, atrybucja ČHMÚ, `archive_encoding="utf-8"`.
6. `parse_archive`: format ČHMÚ (JSON z tabelą `DT,VAL`) → `ArchiveRecord` — osobny, prosty parser (bez ZIP/CSV).

---

## 7. Cache SQLite — schemat v2

Cache to dane odtwarzalne — **bez ścieżki migracji z v1**: przy wykryciu schematu v1 komenda `db init --force` (lub komunikat z instrukcją) usuwa i tworzy od nowa. To świadome wykorzystanie zgody na łamanie kontraktów.

### Zmiany względem v1

1. Kolumna `provider TEXT NOT NULL` we wszystkich tabelach; wchodzi do wszystkich PK/UNIQUE/indeksów.
2. Kanoniczną osią czasu jest **`measurement_date` (data kalendarzowa, ISO)** — rok hydrologiczny (XI–X) przestaje być kolumną kanoniczną; IMGW-owe `hydro_year`/`hydro_month` zostają jako kolumny pomocnicze (nullable), wypełniane tylko przez providera IMGW. ČHMÚ ich nie używa.
3. Nazwy tabel bez prefiksu `hydro_` tam, gdzie to mylące; słownik interwałów w `cached_ranges` przechodzi na angielskie wartości enum.

```sql
stations (
    provider TEXT NOT NULL,
    station_id TEXT NOT NULL,
    kind TEXT NOT NULL,               -- hydro / weather
    name TEXT NOT NULL,
    river TEXT,
    latitude REAL, longitude REAL,
    alert_warning REAL, alert_alarm REAL,   -- progi (IMGW: ostrzegawczy/alarmowy; ČHMÚ: SPA2/SPA3)
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, station_id)
);

hydro_daily (
    provider TEXT NOT NULL,
    station_id TEXT NOT NULL,
    measurement_date TEXT NOT NULL,   -- YYYY-MM-DD, kanoniczne
    water_level_cm REAL, flow_m3s REAL, water_temp_c REAL,
    hydro_year INTEGER, hydro_month INTEGER,   -- pomocnicze, IMGW-only
    PRIMARY KEY (provider, station_id, measurement_date)
);

-- hydro_monthly, hydro_semi_annual: analogicznie (+ provider, + measurement_date/okres)

cached_ranges (
    provider TEXT NOT NULL,
    interval TEXT NOT NULL,           -- wartości Interval (EN)
    year INTEGER NOT NULL,
    month INTEGER,
    station_id TEXT,                  -- NULL dla źródeł krajowych (IMGW), wymagane dla per-stacyjnych (ČHMÚ)
    param TEXT,
    source_url TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    UNIQUE (provider, interval, year, month, station_id, param)
);

schema_version (version INTEGER NOT NULL);   -- = 2
```

`cached_ranges.station_id` rozwiązuje różnicę granulacji: IMGW cache'uje „rok kraju", ČHMÚ „rok stacji". `CacheManager.ensure_cached(query)` pyta providera o klucz zakresu (`query.cache_key()`), więc lazy loading działa identycznie dla obu modeli.

---

## 8. CLI

Entry point `obserwator`; wymiar providera jako globalna opcja `--provider/-P` (default `imgw`).

```bash
obserwator version
obserwator providers                              # NOWE: lista providerów + capabilities + licencje
obserwator server [--host] [--port] [--reload]

obserwator fetch hydro    -P chmi --station 0-203-1-001000 -i daily -y 2020 [-o out.json]
obserwator fetch weather  -P imgw -i monthly -s climate -y 2023
obserwator fetch current hydro   -P chmi --station 0-203-1-001000
obserwator fetch current weather -P imgw
obserwator fetch warnings --kind hydro -P chmi
obserwator fetch pmax --lat 52.23 --lon 21.01     # d. pmaxtp; tylko providery z Capability.PMAX

obserwator list stations --kind hydro -P chmi [--search] [--limit]
obserwator list datasets -P imgw                  # co provider oferuje (z capabilities + zakresy lat)
obserwator list intervals -P imgw

obserwator db init [--force]                      # v2; wykrywa v1 i każe użyć --force
obserwator db status                              # rozbicie per provider
obserwator db cache -P chmi --station <WIGOS> --years 2018-2023 -i daily
obserwator db query -P imgw -s 149180020 -y 2023 -i daily
obserwator db clear [-P provider] [--force]
obserwator db vacuum

obserwator admin keys|create|revoke|delete|stats  # bez zmian merytorycznych
```

Zmiany nazw: `fetch meteo` → `fetch weather`, `fetch current synop` → `fetch current weather`, `fetch pmaxtp` → `fetch pmax`, wartości `-i`/`-s` po angielsku. Teksty pomocy CLI po angielsku (spójnie z API); komunikaty mogą cytować polskie nazwy plików IMGW tam, gdzie to pomaga.

---

## 9. REST API — v2

Nowy prefiks **`/api/v2`**; `/api/v1` usuwane (konsumenci pod kontrolą). Provider jako segment ścieżki — zasoby są hierarchiczne, a capabilities różnią się między providerami:

```
GET  /api/v2/providers                                  # lista + capabilities + licencje
GET  /api/v2/{provider}/stations?kind=hydro&search=...
GET  /api/v2/{provider}/stations/{station_id}
GET  /api/v2/{provider}/current/hydro[?station_id=...]
GET  /api/v2/{provider}/current/weather[?station_id=...]
GET  /api/v2/{provider}/warnings?kind=hydro
GET  /api/v2/{provider}/archive/urls?kind=hydro&interval=daily&year=2020[&station_id=...]
GET  /api/v2/{provider}/data?...                        # z cache DB (jeśli włączony)
POST /api/v2/imgw/pmax                                  # endpoint specyficzny providera (capability PMAX)
GET  /health
```

Zasady:

1. Provider bez danej capability → **404 z problem-details** (`{"type": "not-supported", "provider": "chmi", "capability": "pmax"}`).
2. Schematy odpowiedzi = modele kanoniczne z §3.3 (jeden zestaw schematów dla wszystkich providerów; `provider` w każdym rekordzie).
3. Usuwamy placeholdery z 2.x (zahardkodowane 2 stacje w `routes/hydro.py`/`meteo.py`) — stacje zawsze z providera.
4. Zakresy lat w walidacji z `provider.get_available_years()`, nie ze statycznych `ge=1951, le=2024`.
5. OpenAPI: tagi per provider, opisy capabilities w opisie endpointu.

---

## 10. Web GUI

Zakres minimalny (GUI nie jest priorytetem 3.0, ale nie może kłamać):

1. Selektor providera (IMGW/ČHMÚ) na stronach pobierania i stacji; formularze renderują pola według capabilities (np. ČHMÚ archiwum → pole stacji obowiązkowe, brak wyboru miesiąca).
2. Strony stacji i mapa: dane przez fasadę biblioteki (usunięcie zduplikowanego parsowania CSV z `web/app.py`); markery z `provider` w popupie i atrybucją licencyjną w stopce mapy.
3. Mapa: warstwy per provider (Leaflet layer control); stan wody ČHMÚ mapowany z progów SPA na tę samą skalę kolorów co IMGW.
4. Eksporty PMAXTP bez zmian (funkcja IMGW-only, ukryta dla innych providerów).

---

## 11. Usunięcia i porządki (pełna lista)

| Co | Dlaczego |
|---|---|
| `core/imgw_api.py`, `core/imgw_datastore.py`, `core/imgw_spatial.py` | legacy, złamane importy, `wget`, ścieżki windowsowe (~817 linii) |
| Duplikaty parsowania stacji w `web/app.py`, `db/cache_manager.py` | jedna implementacja w providerze IMGW |
| Placeholdery stacji w `api/routes/` | zastąpione danymi z providera |
| Re-eksporty `urls.py`, `parsers.py` na roocie | zastąpione przestrzeniami providerów |
| Stała publiczna `IMGW_ENCODING` | własność providera |
| Statyczne `le=2024` w schematach | `get_available_years()` per provider |
| Dwie klasy `HydroStation` | jeden kanoniczny `Station` |
| `config.shapefile_path` (`polska.shp`) | martwe po usunięciu `imgw_spatial` |

---

## 12. Plan wdrożenia (etapy = osobne PR-y na `slave`)

| # | Etap | Wynik weryfikowalny |
|---|---|---|
| 1 | Porządki: usunięcie legacy `core/`, konsolidacja duplikatów | testy 2.x zielone, ruff/pyright czyste |
| 2 | `parsing/csv_utils.py` + `http.py` (wspólny klient) | testy parserów przechodzą po przeniesieniu |
| 3 | `providers/base.py` + modele kanoniczne + rejestr | testy jednostkowe interfejsu |
| 4 | Provider IMGW za interfejsem (stare publiczne API jeszcze działa wewnętrznie) | 109 testów przepisanych/zielonych |
| 5 | Rebranding: pakiet `obserwator`, CLI, env, wyjątki, fasada EN | pełny test suite + smoke test CLI |
| 6 | DB schema v2 + `cached_ranges` per stacja | testy repository + `db init/cache/query` na obu modelach granulacji |
| 7 | Provider ČHMÚ (current, archiwa, stacje, CAP) | testy na fixture'ach z prawdziwych odpowiedzi (respx) + test integracyjny (oznaczony `@network`) |
| 8 | REST API v2 + Web GUI | testy endpointów, OpenAPI kompletne |
| 9 | Dokumentacja: CLAUDE.md, README, PRD, ARCHITECTURE | spójne z kodem |

Wymagania testowe (RULES.md): pokrycie ≥ 80%; fixtures dla ČHMÚ pobrane z prawdziwych endpointów i zamrożone w `tests/fixtures/chmi/`; testy sieciowe wydzielone markerem, poza domyślnym przebiegiem CI.

---

## 13. Ryzyka i pytania otwarte

| Ryzyko / pytanie | Mitygacja / propozycja |
|---|---|
| ČHMÚ: granulacja per stacja kusi do pętli po setkach stacji | jawny brak emulacji „cały kraj" w fasadzie; dokumentacja wskazuje cache DB |
| ČHMÚ: głębokość archiwum różna per stacja (404) | `ArchiveNotAvailableError` + `db cache` toleruje braki (loguje, kontynuuje) |
| ČHMÚ: dane operacyjne niewalidowane, korekty z opóźnieniem | pole `provider` + dokumentacja; cache można odświeżyć `db clear -P chmi` |
| Niespójność stref czasowych w dok. ČHMÚ (SEČ vs UTC) | parsujemy `Z` jako UTC; test integracyjny pilnuje formatu |
| Zmiana nazwy na PyPI (`obserwator` może być zajęte) | **do sprawdzenia przed etapem 5**; fallback: `obserwator-data` |
| Repo/URL-e projektu po rebrandingu | decyzja właściciela: zmiana nazwy repo czy tylko pakietu |
| Rate limiting wobec opendata.chmi.cz | klient HTTP: limit współbieżności + jitter w `db cache` |
| Przyszłe providery DE/Bałtyk/SK | interfejs §3.2 zaprojektowany pod nie (capabilities, per-station granularity, CAP parser wspólny) — bez zmian kontraktu |

---

## 14. Definicja ukończenia 3.0

1. `pip install obserwator` + `obserwator providers` pokazuje IMGW i ČHMÚ z capabilities.
2. Wszystkie funkcje 2.x mają odpowiedniki w nowym API (tabela mapowania w README).
3. ČHMÚ: bieżące hydro, archiwa daily/monthly, stacje z progami SPA, ostrzeżenia CAP — działają i są pokryte testami.
4. Zero odwołań do nazw `imgwtools`/`IMGW_` poza providerem IMGW i dokumentacją historyczną.
5. Pokrycie testami ≥ 80%, ruff + pyright czyste, OpenAPI kompletne.

