# Spec: wersjonowany magazyn danych IMGW

**Data:** 2026-10-17  
**Status:** zaakceptowane decyzje ADR-001; kontrakt implementacji 3.0.0  
**Plan:** `../plans/2026-10-17-versioned-store.md`  
**Źródła normatywne:** `docs/DECISIONS.md` ADR-001, `Archiwista/docs/SPEC.md` 4.8.1–4.8.5 i 12.7–12.9, `Archiwista/docs/wymagania-imgwtools.md` R1–R12/IMGW-1..14, opisy IMGW w `data/desc/`. W razie konfliktu z historyczną, niezaimplementowaną specyfikacją `2026-08-02-unified-data-pipeline-design.md` obowiązuje ten dokument: **bez SQLite, pięć zbiorów archiwalnych + PMAXTP, bez shimów DB**.

## 1. Granice i organizacja kodu

Producentem danych i jedynym piszącym do katalogu IMGW jest IMGWTools; konsument czyta wyłącznie publiczne API. Korzeń magazynu jest jawnie wskazany i absolutyzowany na wejściu; nie ma domyślnego `./data`, połączenia z katalogiem Kartografa, plików ani indeksu Archiwisty w magazynie. Bieżące hydro, synop, ostrzeżenia i `fetch_pmaxtp` pozostają live-only i nie zmieniają kontraktu. API serwera pozostaje domyślnie generatorem URL; zapis do magazynu na serwerze tylko po jawnej konfiguracji uprawnionego katalogu.

Proponowany **podział własności** (każdy publiczny symbol dodatkowo re-eksportowany przez `imgwtools.__all__`):

```text
src/imgwtools/
  datasets.py               DatasetDescriptor, registry, archive_files, station_source_files
  core/url_builder.py        dotychczasowe URL-e; reguły layoutu delegowane do datasets
  fetch.py                  DownloadResult + aktualne fetch_*/download_* (bez drugiej ścieżki GET)
  parsers.py                PUBLIC: zachowane importy hydro, nowe parse_meteo_* i normalize_archive
  _parsing/hydro.py         przeniesione funkcje hydro z db/parsers.py
  _parsing/meteo.py         k_d/o_d; dekodowanie, walidacja, flagi
  _parsing/common.py        dekoder CP1250/BOM, csv, daty hydrologiczne, kody braków
  coverage.py              czyste summarize_coverage
  store/__init__.py         re-eksport publicznych funkcji magazynu
  store/types.py            StoreInfo, StoreEntry, Meta, Progress, Notice, raporty
  store/writer.py           init_store/open_store/write_archive, wyłączny atomowy commit
  store/catalog.py          check_catalog, build_catalog; pakowany obrys Polski WGS84
  store/reader.py           store_info, iter_store, read_meta, current_version, read_series_index/read_series/read_catalog
  store/sync.py             check_store, sync_store, imgw-plan/1
  store/series.py           check_series, build_series
  store/export.py           export_series, CSV i atomowy plik wynikowy
  store/pmaxtp.py           check_pmaxtp, sync_pmaxtp, read_pmaxtp
  commands.py              data_commands/validate/format/run/check_command
  project.py               imgw-project/1, zarządzanie zadaniami
  testing.py               publiczny build_fixture_store (wyłącznie fixtury offline)
  cli/store.py,series.py,pmaxtp.py,project.py  adaptery CLI funkcji publicznych
  api/routes/store.py      jawne operacje magazynu REST; istniejące URL-e bez zmiany
```

Przy cutover usuwamy całe `src/imgwtools/db/` (`cache_manager`, `connection`, `schema`, `repository`, `models`, `parsers`, `__init__`), `src/imgwtools/cli/db.py`, DB-only endpoint `/api/v1/hydro/data`, `IMGW_DB_ENABLED`, `IMGW_DB_PATH`, `imgwtools[db]`. Odczyt tekstów parserów pozostaje w `imgwtools.parsers`, modele archiwalne i pomocnicze stałe/datowanie poza DB; bez re-eksportu `imgwtools.db.*`. Nie usuwamy plików SQLite użytkownika automatycznie. Instalacja: `imgwtools` — lekki rdzeń; `imgwtools[store] = pyarrow>=15`; `full` obejmuje `store`, `api`, `cli`, `spatial`. Import rdzenia nie importuje pyarrow. Wyjątek `IMGWStoreDependencyError` z instrukcją `pip install imgwtools[store]` tylko przy ścieżce Parquet.

## 2. Słownik typów i podpisy API

`PathArg = str | os.PathLike[str]`; `RootArg = PathArg | StoreHandle`; daty ISO UTC (`Z`), ścieżki relatywne POSIX, kod stacji dokładnie 9 cyfr jako **str**. `root` oraz identyfikator obiektu wskazany jako pierwszy (`version`, `records`, `command`) mogą być pozycyjne; wszystkie dalsze argumenty są keyword-only (R1). Klasy danych niemutowalne, polskie błędy i komunikaty. Pełna lista funkcji i typów poniżej jest eksportowana w `imgwtools.__all__`; kod konsumenta nie musi importować modułów prywatnych.

```python
@dataclass(frozen=True)
class Progress:
    current: int; total: int; unit: str; status: str; message: str
@dataclass(frozen=True)
class Notice:
    level: Literal["info", "warning", "error"]; code: str; text: str
ProgressHook = Callable[[Progress], None]
NoticeHook = Callable[[Notice], None]
Cancel = Callable[[], bool]

@dataclass(frozen=True)
class License:
    id: Literal["IMGW-PIB"]; attribution: str; url: str

@dataclass(frozen=True)
class DatasetDescriptor:
    key: str                     # pl.imgw.hydro_daily, itd.
    slug: str                    # hydro_daily, itd.
    server_dir: str | None       # np. dane_hydrologiczne/dobowe; PMAXTP None
    parser: str | None           # zarejestrowana funkcja publiczna, PMAXTP None
    variables: Mapping[str, str] # kod -> jednostka: H:cm, Q:m3/s itd.
    time_unit: Literal["day", "month", "half_year", "station_list", "cell"]
    year_type: Literal["hydrological", "calendar", "none"]
    update_signal: Literal["http", "none"]
    license: License
@dataclass(frozen=True)
class ArchiveFile:
    dataset: str; server_path: str; url: str
    year: int | None; month: int | None; param: str | None
    year_type: Literal["hydrological", "calendar", "none"]
    period_start: date | None; period_end: date | None
@dataclass(frozen=True)
class DownloadResult:
    data: bytes; url: str; etag: str | None
    last_modified: str | None; content_length: int | None

def datasets() -> tuple[DatasetDescriptor, ...]: ...
def get_dataset(dataset: str, /) -> DatasetDescriptor: ...
def archive_files(dataset: str, /, *, years: Iterable[int],
                  months: Iterable[int] | None = None) -> tuple[ArchiveFile, ...]: ...
def station_source_files() -> tuple[ArchiveFile, ArchiveFile]: ...
# D7: zachowane argumenty wcześniejszych funkcji, nowy typ wyniku:
def download_hydro_data(interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
                        year: int, month: int | None = None,
                        param: Literal["T", "Q", "H"] | None = None,
                        *, timeout: float = 120.0) -> DownloadResult: ...
async def download_hydro_data_async(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int, month: int | None = None, param: Literal["T", "Q", "H"] | None = None,
    *, timeout: float = 120.0) -> DownloadResult: ...
def download_meteo_data(interval: Literal["dobowe", "miesieczne", "terminowe"],
                        subtype: Literal["klimat", "opad", "synop"], year: int,
                        month: int | None = None, *, timeout: float = 120.0) -> DownloadResult: ...
async def download_meteo_data_async(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"], year: int,
    month: int | None = None, *, timeout: float = 120.0) -> DownloadResult: ...
```

Istniejące publiczne `download_*` zachowują dotychczasowe pozycje parametrów dla kompatybilności podpisu wejściowego; **nowe** funkcje są keyword-only po pierwszym obiekcie. W `DownloadResult.data` dokładne bajty odpowiedzi, nagłówki z tego samego GET (`Content-Length` int albo `None`, brak `ETag`/`Last-Modified` = `None`, bez zgadywania); HTTP 4xx/5xx, timeout i błędny ZIP = odpowiedni `IMGWError`. Url-builder starego API zachowuje swój zakres (także miesięczne/terminowe meteo poza rejestrem magazynu), lecz dla wspieranych pięciu zbiorów reguły i walidacja pochodzą z rejestru, nie z duplikowanej tabeli.

### 2.1 Rejestr i generator plików

| `key` / slug | `server_dir`; zmienne [jednostka] | Interwał/rok; `archive_files` |
|---|---|---|
| `pl.imgw.hydro_daily` / `hydro_daily` | `dane_hydrologiczne/dobowe`; H cm, Q m3/s, T degC | `day/hydrological`; <2023: 12 × `<year>/codz_<year>_<mm>.zip`; >=2023: `<year>/codz_<year>.zip` |
| `pl.imgw.hydro_monthly` / `hydro_monthly` | `dane_hydrologiczne/miesieczne`; H/Q/T × min/mean/max | `month/hydrological`; `<year>/mies_<year>.zip` |
| `pl.imgw.hydro_semiannual` / `hydro_semiannual` | `dane_hydrologiczne/polroczne_i_roczne`; H/Q/T × min/mean/max | `half_year/hydrological`; 3 × `<year>/polr_<H|Q|T>_<year>.zip`; zawiera 13=zima,14=lato,15=rok |
| `pl.imgw.meteo_climate_daily` / `meteo_climate_daily` | `dane_meteorologiczne/dobowe/klimat`; Tmax/Tmin/Tmean/Tground degC, P mm, snow_cover cm | `day/calendar`; 1951–2000: `<five-year-folder>/<year>_k.zip`; 2001+: `<year>/<year>_<mm>_k.zip` |
| `pl.imgw.meteo_precip_daily` / `meteo_precip_daily` | `dane_meteorologiczne/dobowe/opad`; P mm, snow_cover/fresh_snow cm | `day/calendar`; 1950–2000: `1950_1955/1950_o.zip` itd., od 1956 standardowe foldery 5-letnie; 2001+: `<year>/<year>_<mm>_o.zip` |
| `pl.imgw.hydro_stations` / `hydro_stations` | `dane_hydrologiczne`; bez zmiennych | `station_list/none`; `lista_stacji_hydro.csv`, źródło `station_source_files()`, bez lat |
| `pl.imgw.meteo_stations` / `meteo_stations` | `dane_meteorologiczne`; bez zmiennych | `station_list/none`; `wykaz_stacji.csv`, źródło `station_source_files()`, bez lat |
| `pl.imgw.pmaxtp` / `pmaxtp` | brak katalogu archiwów; ks/sg/rb mm | `cell/none`; metoda `POT` lub `AMP`, `archive_files` odrzuca |

Dolna granica rocznika: hydro/klimat 1951, opad 1950; **nie ograniczamy górnej granicy bieżącym rokiem**, aby generator offline nie dezaktualizował się i mógł nazwać przyszły rok hydrologiczny. Istnienie publikacji ustala wyłącznie serwer w `check_store`. `months` filtruje tylko fizycznie miesięczne pliki; podanie `months` dla rocznego ZIP (np. 2024 hydro lub 1995 meteo) zwraca jedną paczkę, nigdy 12 duplikatów. Miesiące hydro to wskaźniki 1=XI roku `year-1`, 2=XII `year-1`, 3=I `year`, …, 12=X `year`. `period_start/end` wyznacza rzeczywisty okres publikacji (uwzględnia 29 II). Deduplikacja lat/miesięcy, sortowanie `year`, `param`, `month`, `server_path`. Niedozwolona kombinacja → `IMGWValidationError`, nie pusty generator. `server_path` zaczyna się od `dane_hydrologiczne/` albo `dane_meteorologiczne/` i jest względny do `…/dane_pomiarowo_obserwacyjne/`; `url` buduje się przez dołączenie do publicznego bazowego URL.

`datasets()` zawiera pięć zbiorów pomiarowych, dwie pomocnicze listy stacji oraz PMAXTP; `get_dataset` i `archive_files` przyjmują **tylko pełne klucze** `pl.imgw.*`, a slug jest użyty wyłącznie w ścieżce serii. `station_source_files()` generuje z tych samych dwóch deskryptorów `dane_hydrologiczne/lista_stacji_hydro.csv` i `dane_meteorologiczne/wykaz_stacji.csv`, `year=None`, `year_type="none"`; nie tworzy szeregów. `archive_files` dla deskryptora `station_list`/`cell` odrzuca roczniki, zamiast udawać puste archiwa. Listy CSV zapisuje `write_archive` według identycznych reguł jak ZIP.

## 3. Magazyn, wersje i atomowość

```text
<root>/imgw-store.json
  archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/2025-08-28_<sha8>/codz_2024.zip
                                                                      codz_2024.zip.meta.json
  stations/versions/<label>_<sha8>/stations.geojson[.meta.json]
  series/versions/hydro_daily/<label>_<sha8>/series.json[.meta.json]
                                                  stations/149190310.parquet
  pmaxtp/versions/POT/751_317/<label>_<sha8>/cell.json[.meta.json]
  .incoming/<hostname>_<pid>_<random-token>/...
```

`<sha8>` = pierwsze osiem małych cyfr hex **pełnego SHA-256 pliku głównego** (series: `series.json`). Spis serii haszuje pliki stacji, bez własnego hasha i bez `downloaded_at`, co eliminuje cykl sum. Etykiety: archiwum `YYYY-MM-DD` z `Last-Modified` w UTC albo `downloaded_at` UTC; jeśli różne sygnały HTTP dają ten sam dzień **i** SHA, do etykiety dołącza się stabilne `+<8 hex SHA-256(canonical etag,last_modified)>` (nowy sygnał, nowy katalog). Gdy identyczny sygnał i treść: `unchanged`. Brak sygnału (`ETag`, `Last-Modified`) i identyczne bajty: `unchanged`; różna treść tej samej daty może mieć ten sam label, ale inne `sha8` i jest nową wersją. Pełny SHA potwierdza tożsamość; kolizja nazwy po skróceniu → `IMGWStoreConflictError`, nigdy nadpisanie. Katalog identyczny następnego dnia: `unchanged` niezależnie od etykiety. Seria: label = najpóźniejsza data `Last-Modified` wejść albo data budowy, `label_source="inputs"`; seria jest `reused`, jeśli ten sam zbiór uporządkowanych par `(ścieżka slotu, pełny sha256)` i schema, bez ponownego zapisu Parquet, także po samym relabelingu archiwum. PMAXTP: label = dzień pobrania (`downloaded`), identyczny `cell.json` = `unchanged`; brak HTTP signal. Bieżąca wersja archiwum = najnowszy czas `Last-Modified` (pełny timestamp w sidecarze; w razie braku — `downloaded_at`; remis według `downloaded_at`, potem leksykograficzna ścieżka); seria = najnowsze `downloaded_at`; katalog i komórka = najnowsze `downloaded_at`, przy remisie leksykograficzna ścieżka. Bieżącą serię oznacza się `outdated`, gdy jej zestaw pełnych SHA wejść nie zgadza się z bieżącymi slotami archiwów.

```python
@dataclass(frozen=True)
class StoreHandle: root: Path; schema: Literal["imgw-store/1"]
@dataclass(frozen=True)
class StoreInfo:
    root: Path; exists: bool; schema: str | None; supported: bool
    contracts: Mapping[str, str] # store/meta/series/plan/project + pmaxtp cell
    problems: tuple[str, ...]
@dataclass(frozen=True)
class VersionResult:
    status: Literal["created", "unchanged", "relabeled", "reused"]
    path: Path; sha256: str; label: str

def init_store(root: PathArg, /, *, created_at: datetime | None = None) -> StoreHandle: ...
def open_store(root: PathArg, /) -> StoreHandle: ...  # read-only, nie tworzy katalogu

def write_archive(root: RootArg, /, *, archive: ArchiveFile, response: DownloadResult,
                  on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> VersionResult: ...
```

`init_store` tworzy tylko pusty/istniejący zgodny katalog i znacznik atomowo (odmowa w niepustym obcym katalogu); `open_store` wymaga znanego znacznika. Przed zapisem sprawdza się realne ścieżki przodków/istniejących potomków; rozpoznanie katalogu Kartografa bez importu po `kartograf-project.json` wskazującym właśnie dany katalog `output_dir` albo po `versions/` z sidecarem o `schema: kartograf-meta/1`; rozpoznanie IMGW po `imgw-store.json`. Sam manifest projektu obok magazynu bez wskazania na niego **nie** jest znacznikiem magazynu Kartografa. Nieczytelny znacznik przy istotnej ścieżce → błąd przed zapisem. Zakaz root IMGW wewnątrz root Kartografa i root Kartografa wewnątrz root IMGW; żadna warstwa nie zakłada importu Kartografa. Symlinki/`..` w ścieżkach slotu, ucieczka z korzenia i nieistniejący punkt montowania → błąd.

**Publikacja:** unikalne `.incoming/<host>_<pid>_<token>` na tym samym systemie plików; strumieniowo zapisać oryginalne bajty i policzyć SHA w tym samym przebiegu (gdy `DownloadResult.data` już w pamięci — jeden przebieg po bajtach). Przy serii gotowy lokalnie Parquet skopiować do stagingu, nie zostawiać pyarrow tmp w `root`. Wyliczyć kanoniczne JSON, SHA i rozmiary; obok głównego pliku utworzyć `*.meta.json`; `flush/fsync` każdego pliku i katalogu stagingowego. Publikować **cały katalog wersji** pojedynczą operacją rename **bez możliwości zastąpienia istniejącego celu** (`renameat2(RENAME_NOREPLACE)` na wspieranym POSIX, odpowiednik no-replace na innych systemach). Samo `os.rename` nie daje tej gwarancji przy istniejącym pustym katalogu i nie jest dopuszczalnym fallbackiem; jeśli filesystem/SMB nie zapewnia semantyki, jawny `IMGWStoreConflictError` przed publikacją. Po sukcesie `fsync` katalogu nadrzędnego; przy wyścigu drugi proces weryfikuje pełny hash i wynosi `unchanged` lub błąd, nie podmienia pliku. Anulowanie/wyjątek pozostawia najwyżej prywatny staging; następny **zapis** sprząta tylko katalogi `.incoming/` starsze niż 24 h. Żadnego automatycznego czyszczenia wersji. Płaski `imgw fetch` poza magazynem zapisuje przez unikalny `<name>.part` i `os.replace` po walidacji, zachowuje **pełną ścieżkę** `ArchiveFile.server_path` w `--output`; przerwany `.part` nigdy nie jest wynikiem, brak pominięcia przy kolizji nazw.

## 4. Sidecar i licencja

Każdy główny plik wersji (ZIP/CSV listy, `series.json`, `stations.geojson`, `cell.json`) ma niezmienny `<plik>.meta.json`. Wspólna koperta `schema`, `producer`, `producer_version`, `dataset`, `country`, `provider`, `request`, `license`, `downloaded_at`, `sha256`, `size_bytes`, `extra`. `license.id="IMGW-PIB"`, `url="https://danepubliczne.imgw.pl/regulations"`; archiwa/katalog: **„Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy”**, szeregi/CSV/PMAXTP normalizowane: ta formuła oraz **„Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone”** (§5 ust. 3/4). `extra.version={label,label_source}`; archiwum `extra.http` (`url`, `etag`, `last_modified`, `content_length`) i `extra.period` (`year`,`month`,`param`,`year_type`,`start`,`end`); seria `extra.derived="series"`, `extra.series_schema="imgw-series/1"`, `extra.source_files[]` z dokładną ścieżką *wersji*, nazwą, SHA i etykietą; katalog `extra.catalog[]` ma URL źródła, `fetched_at`, `count`, SHA odpowiedzi, bez utrwalania całej odpowiedzi live; komórka `extra.derived="pmaxtp"` i `request` z metodą/indeksami/żądanym punktem. Sumy w sidecarze odnoszą się wyłącznie do głównego pliku; `series.json` zawiera sumy każdego Parquet. Atrybucję pokazuje również `on_notice` z informacją o przeznaczeniu prywatnym/badawczym, warunkach dla innych zastosowań i wyjątku wysokiej wartości bez niepotwierdzonej kwalifikacji konkretnego zbioru.

## 5. Aktualność i plan `imgw-plan/1`

```python
@dataclass(frozen=True)
class PlanItem:
    archive: ArchiveFile; status: Literal["current", "newer", "missing",
                                     "unverifiable", "check_failed"]
    local_path: Path | None; local_sha256: str | None
    remote_etag: str | None; remote_last_modified: str | None
    content_length: int | None; error: str | None
@dataclass(frozen=True)
class PlanAction:
    command: str; status: Literal["current", "newer", "missing", "unverifiable", "check_failed"]
    detail: str                                  # działania niearchiwalne: CSV, projekt, katalog
@dataclass(frozen=True)
class StorePlan:
    schema: Literal["imgw-plan/1"]; root: Path; checked_at: datetime
    items: tuple[PlanItem, ...]
    series_state: Mapping[str, Literal["current", "outdated", "missing"]]
    actions: tuple[PlanAction, ...] = ()
    cancelled: bool = False
    def to_json(self, path: PathArg, /) -> Path: ...
    @classmethod
    def from_json(cls, path: PathArg, /) -> StorePlan: ...
@dataclass(frozen=True)
class OperationResult:
    slot: str
    status: Literal["created", "relabeled", "unchanged", "reused",
                    "failed", "stale_plan", "cancelled"]
    version: Path | None; error: str | None
@dataclass(frozen=True)
class SyncReport:
    items: tuple[OperationResult, ...]; series: tuple[SeriesReport, ...]; cancelled: bool

def check_store(root: RootArg, /, *, datasets: Iterable[str], years: Iterable[int],
                months: Iterable[int] | None = None,
                on_progress: ProgressHook | None = None,
                on_notice: NoticeHook | None = None,
                cancel: Cancel | None = None) -> StorePlan: ...
def sync_store(root: RootArg, /, *, datasets: Iterable[str] | None = None,
               years: Iterable[int] | None = None, months: Iterable[int] | None = None,
               plan: StorePlan | PathArg | None = None, series: bool = True,
               on_progress: ProgressHook | None = None,
               on_notice: NoticeHook | None = None,
               cancel: Cancel | None = None) -> SyncReport: ...
```

`check_store` działa na już utworzonym korzeniu, *nie pisze* nawet stagingu: wylicza pliki offline, sprawdza listing katalogów u IMGW dla opublikowanych lat i `HEAD` dla każdego istniejącego pliku, zero GET archiwum. Nie zakłada, że bieżący rok jest dostępny. `current` = lokalne wersje i zgodny dostępny sygnał (porównujemy oba obecne nagłówki), `newer` = inny ETag lub Last-Modified, `missing` = opublikowany plik bez lokalnej wersji, `unverifiable` = żaden porównywalny sygnał, `check_failed` = błąd HTTP/listingu; nieopublikowany rok widoczny w planie jako pozycja `unverifiable` z powodem „nieopublikowany” bez GET. `Content-Length` służy jedynie szacunkowi, nigdy decyzji o zmianie. Seria `outdated` gdy brakujące lub różne pełne hashe wejść, `missing` gdy brak serii. `cancel` → częściowy plan z dotąd sprawdzonymi pozycjami i `cancelled=true` (także w JSON), jawnie oznaczone niewykonane pozycje `unverifiable` z powodem „anulowano”.

`sync_store(plan=…)` nie łączy selektorów `datasets/years/months` z planem (oba naraz = walidacja błędna); bez planu wywołuje `check_store` z podanymi selektorami. Przed każdym GET wykonuje `HEAD` i porównuje sygnały planu; gdy się zmieniły, wynik pozycji `stale_plan`, bez pobierania tej pozycji. Nieznany sygnał → jawny `unverifiable`, pobranie możliwe wyłącznie przy świadomym `sync_store` bez planu (`on_notice`), po GET deduplikacja według SHA; żadne `check_failed` nie jest pobierane. `GET` nie służy testowi aktualności planu. Wyniki per slot: `created`, `relabeled`, `unchanged`, `reused`, `failed`, `stale_plan`, `cancelled`; wyjątek błędu pojedynczego pliku jest zachowany w raporcie. `series=True` buduje tylko z kompletnego skutecznie zsynchronizowanego zestawu wybranych okresów i bieżących archiwów (nie z nieudanych pozycji), `False` pozostawia serię `outdated`. Serializacja planu przez `StorePlan.to_json(path)` i `StorePlan.from_json(path)` UTF-8; plan jest poza magazynem, nigdy mutowalnym plikiem wewnątrz root.

Rozstrzygnięcia implementacji (T12): „opublikowany” = nazwa pliku w listingu katalogu nadrzędnego; listing 404/410, brak nazwy w listingu albo HEAD 404/410 → `unverifiable` z `error="nieopublikowany"` (bez HEAD/GET), inny błąd listingu/HEAD → `check_failed`. `PlanItem.local_path` jest względne do root (bieżąca wersja slotu wg §3). `series_state` w `check_store` = stan lokalny (§3), lecz `current` zmienia się w `outdated`, gdy plan zawiera dla zbioru pozycje `newer`/`missing`. `OperationResult.slot` = `archives/versions/<katalog>/<stem>`, `version` = bezwzględna ścieżka pliku głównego. Bez pobierania: `current` → `unchanged`; `nieopublikowany` → `unchanged` z `version=None`, `error="nieopublikowany"` (nie blokuje serii); `unverifiable` z planu → `unchanged` z ostrzeżeniem `source_unverifiable`; pozycje „anulowano” → `cancelled`. Gdy zbiór ma pozycje `failed`/`stale_plan`/`cancelled`, `build_series` nie jest wywoływane, a `SyncReport.series` zawiera `SeriesReport` `failed` (lub `cancelled`) z listą slotów w `problems`; błąd `IMGWError` budowy (np. brak pyarrow) również trafia do raportu jako `failed`.

## 6. Parsery i rekordy z flagami

```python
Flag = Literal["value", "missing", "no_phenomenon", "accumulated"]
@dataclass(frozen=True)
class Measurement:
    value: float | None
    flag: Flag
@dataclass(frozen=True)
class NormalizedRecord:
    station_code: str; dataset: str; date: date        # start jednostki, kalendarz
    hydro_year: int; period: Literal["winter", "summer", "annual"] | None
    measurements: Mapping[str, Measurement]           # kolumny fizycznie obecne w wejściu
    attributes: Mapping[str, str | None] = field(default_factory=dict)
    extrema_dates: Mapping[str, tuple[datetime | None, datetime | None]] = field(default_factory=dict)

def parse_meteo_climate_daily(content: bytes | str, /, *, filename: str) -> Iterator[NormalizedRecord]: ...
def parse_meteo_precip_daily(content: bytes | str, /, *, filename: str) -> Iterator[NormalizedRecord]: ...
def normalize_archive(archive: ArchiveFile, /, *, data: bytes) -> Iterator[NormalizedRecord]: ...
# Dotychczasowe parse_daily_csv, parse_monthly_csv, parse_semi_annual_csv,
# parse_zip_file, parse_stations_csv, IMGW_ENCODING w imgwtools.parsers nadal dostępne.
```

Funkcje starych parserów hydro pozostają importowalne; normalizacja adaptuje ich rekordy do `NormalizedRecord` (bez zmiany starych modeli hydro tylko dla zgodności). Rekord hydro miesięczny agreguje trzy wskaźniki ekstremum do kolumn `H_min/H_mean/H_max`, `Q_*`, `T_*` jednego miesiąca; półroczne parametry z trzech różnych archiwów scala dopiero builder w jeden wiersz stacji × okres × rok, a `measurements` parsera zawiera tylko kolumny fizycznie obecne w danym ZIP. Nieobecne kolumny w wynikowej migawce stają się `None/missing`; konflikt dwóch **podanych** wartości tej samej kolumny nie jest ignorowany. `extrema_dates` wiąże daty od/do z nazwą konkretnej kolumny, np. `Q_max`. ZIP czytany z limitem liczby/rozmiaru plików i bez rozpakowywania ścieżek: bez path traversal/zip bomb; rozpoznanie CP1250, UTF-8 z BOM, `,`/`;`, podwójnie cytowanych całych linii i wierszy nagłówków **per plik**; nieprzetwarzalny rekord = `IMGWDataError` z nazwą ZIP/CSV i numerem linii, a nie pusty wynik. Kod stacji zawsze tekst; duplikat `(stacja, zbiór, data, period, kolumna)` o różnych wartościach/flagach = jawny błąd danych, nie „first wins”.

| Opis `data/desc/` | Kolejność i zasady normalizacji |
|---|---|
| `dane_hydrologiczne/codz_info.txt` | kod, nazwa, rzeka, rok hydro, miesiąc hydro, dzień, H, Q, T, miesiąc kalendarzowy. XI/XII = poprzedni rok kalendarzowy; H `9999`, Q `99999.999`, T `99.9` oraz brak dnia → `None/missing` **osobno dla każdej wielkości**. |
| `mies_info.txt` | jak hydro, zamiast dnia wskaźnik 1=min, 2=mean, 3=max; kolumny `H_min`, `H_mean`, `H_max`, `Q_*`, `T_*` mają własne flagi, datą jednostki jest pierwszy dzień miesiąca. Brak wartości nie jest zerem. |
| `polr_info.txt` | kod, nazwa, rzeka, rok hydro, okres 13=zima XI–IV, 14=lato V–X, 15=rok XI–X; H/Q/T, ekstremum min/mean/max, wartość, daty/godziny od–do. `99999.999` = brak. Każda para okres × param × ekstremum z osobną wartością/flagą i datami ekstremum; średnia bez dat może mieć `None`. |
| `dane_meteorologiczne/k_d_format.txt` | kod, nazwa, rok/miesiąc/dzień, kolejno wartość+status: Tmax, Tmin, Tmean, Tground, P, typ opadu, wysokość pokrywy śnieżnej+status. Status 8: `None/missing`; 9: `0/no_phenomenon`, a nie brak. Typ opadu `S`/`W`/pusty zachować jako osobny atrybut rekordu, bez tworzenia liczby. |
| `o_d_format.txt` | kod, nazwa, rok/miesiąc/dzień, P+status, typ opadu, snow_cover+status, fresh_snow+status, gatunek śniegu+status, rodzaj pokrywy+status. Kody klasyfikacji zachować jako tekst/metadane, status 8/9 stosować per wartość; brak dnia w **istniejącym** miesiącu P=`0/no_phenomenon`, brak całego miesiąca P=`None/missing`. |

Jakościowe atrybuty meteo w `attributes` (`precip_type`, `snow_species`, `snow_cover_type`) nie trafiają do numerycznych `variables`. Suma dobowa P poprzedzona dniami statusu 8, oznaczona przez IMGW jako zbiorcza (opis `o_d_format.txt`), dostaje `accumulated`, a poprzednie dni pozostają `missing`; brak podstaw do przypisania jej poszczególnym dniom. Nie nadpisujemy ręcznie wartości hydro niezwiązanych z brakującą Q. Granica roku hydro 31 X / 1 XI i 29 II testowana dla hydro **i** meteo. Parser wybiera prawdziwe pliki `k_d`/`o_d` ZIP, nie inne pliki `*_t`/`*_m` w paczce; rozróżnia roczne do 2000 i miesięczne od 2001, nie wnioskuje zakresu tylko z brakujących wierszy.

## 7. Pokrycie i Parquet `imgw-series/1`

```python
@dataclass(frozen=True)
class StationCoverage:
    station: str; variable: str; unit: str
    period: Literal["winter", "summer", "annual"] | None
    first: date | None; last: date | None
    with_value: int; accumulated: int
    gaps: tuple[tuple[date, date], ...]

def summarize_coverage(records: Iterable[NormalizedRecord], /, *,
                       dataset: str) -> list[StationCoverage]: ...
@dataclass(frozen=True)
class SeriesReport:
    status: Literal["created", "reused", "cancelled", "failed"]
    version: Path | None; stations: int; source_files: tuple[Path, ...]
    problems: tuple[str, ...]
def check_series(root: RootArg, /, *, dataset: str,
                 on_progress: ProgressHook | None = None,
                 on_notice: NoticeHook | None = None,
                 cancel: Cancel | None = None) -> StorePlan: ...
def build_series(root: RootArg, /, *, dataset: str,
                 on_progress: ProgressHook | None = None,
                 on_notice: NoticeHook | None = None,
                 cancel: Cancel | None = None) -> SeriesReport: ...
```

Pokrycie liczone per **stacja × zmienna**, włącznie ze zmienną bez wartości (first/last `null`, `with_value=0`), nie jedna etykieta na stację. Dla hydro półrocznego/rocznego osobno per `period`; w `series.json` klucz `variables` ma np. `Q_min@winter`, `Q_min@summer`, `Q_min@annual`, nie sumę trzech nakładających się okresów. `gaps`: maksymalne domknięte przedziały znanych jednostek bez wartości **między** pierwszą i ostatnią wartością; brak na początku/końcu znanej serii ujawniają `periods` i first/last, nie ukrywają jako „nieznane”. `no_phenomenon=0` i `accumulated` liczą się jako wartość (ta ostatnia zwiększa `accumulated`). `periods` to unia dokładnych okresów **posiadanych archiwów wejściowych**, nie „od min do max” po rekordach. Brak całego niepobranego ZIP = jednostki nieznane, nie luki; brak w posiadanym ZIP = luki. Dla doby okresy i luki w dniach, dla miesiąca ISO pierwszy/ostatni dzień miesiąca, dla półrocza/roku zapis dat granicznych 13/14/15 z rozdzielnym pokryciem `period` (nigdy nie traktować 15=rok jako trzeciego półrocza). IMGWTools nie liczy etykiet interfejsu („ciągły”, „luki …”).

`build_series` czyta dokładnie bieżące wersje archiwów danego zbioru, buduje migawkę wszystkich napotkanych stacji (także bez geometrii, z przerwami, z samym H bez Q); jeśli choć jedno wejście błędne, nie publikuje niepełnej migawki. Zanim zacznie kosztowną budowę, porównuje uporządkowany manifest `(slot, pełny sha256)` i schema z już istniejącymi wersjami; przy tym samym stanie zwraca `reused`, **nie** wywołuje writerów Parquet. Parquet wymaga `pyarrow>=15`, deterministyczny wybór typów: `date: date32`, `hydro_year: int32`, `*_value: float64 (nullable)`, `*_flag: dictionary<string>` z wartościami `value|missing|no_phenomenon|accumulated`; null wartości tylko z flagą `missing`. W metadanych schematu UTF-8 `imgw_schema=imgw-series/1`, `dataset`, `units` jako kanoniczny JSON z kodem→jednostką. W każdym zbiorze jest `hydro_year`; w meteo też, nawet przy kalendarzowej numeracji ZIP-ów.

- Doba: `date` każdego dnia od pierwszego do ostatniego **rekordu stacji** (w tym dni brakujące w posiadanych archiwach), `hydro_year`, pary `H_value/H_flag`, `Q_…`, `T_…` albo `Tmax`, `Tmin`, `Tmean`, `Tground`, `P`, `snow_cover`, `fresh_snow` zależnie od deskryptora; brak zmiennej u stacji = kolumna null/missing, bez filtrowania stacji.
- Miesiąc: `date` = pierwszy dzień kalendarzowego miesiąca, `hydro_year`, 9 par `H_min/H_mean/H_max`, `Q_*`, `T_*`; wiersz na miesiąc.
- Półrocze/rok: `date` = początek okresu, `hydro_year`, `period: dictionary<string>` w zbiorze `winter|summer|annual`, dziewięć par H/Q/T × min/mean/max i odpowiadające im opcjonalne `*_start`/`*_end: timestamp[us]` dla dat ekstremów; 3 wiersze (zima, lato, rok) na rok hydro w wejściu, bez pozornej interpolacji nieopublikowanych danych.

`series.json` zawiera `stations[code].file` względne do katalogu danej wersji, `sha256` każdego Parquet, `rows`, `variables` z `unit,first,last,with_value,accumulated,gaps` oraz `periods` wspólne dla zbioru. `year_type` oznacza **numerację ZIP**, nie rodzaj lat widoku: hydro hydrological, meteo calendar; obliczanie `calendar`/`hydrological` w `read_series`/eksport z `date`, lecz dla half_year tylko hydrological. `series.json` jest kanonicznym JSON UTF-8 z LF, `sort_keys=True`, krótkimi separatorami, bez zmiennej daty budowy: te same wejścia → te same bajty. Timestamps budowy tylko w sidecarze.

Rozstrzygnięcia implementacji (T13): `SeriesReport.version` = ścieżka `series.json`, `source_files` = bezwzględne ścieżki wersji wejść (dla `reused` — wejścia zapisane w sidecarze ponownie użytej wersji). `periods` to unia okresów wejść ze scaleniem przyległych przedziałów. Szereg miesięczny ma wiersz dla każdego miesiąca od pierwszego do ostatniego rekordu stacji (jak doba), półroczny — trzy wiersze na każdy rok hydrologiczny stacji. `hydro_year` liczy builder z `date` (XI–X) dla wszystkich zbiorów. Słowniki `*_flag`/`period` mają stały zestaw wartości i indeksy `int8`. Identyczny `series.json` z innego manifestu wejść (np. przepakowany ZIP) dostaje etykietę `<label>+<8 hex SHA-256 manifestu>` zamiast kolizji. `check_series` zwraca pozycje bieżących wejść (`current`, sygnały HTTP z sidecara) i akcję `series build` o statusie `current`/`newer` (outdated)/`missing`; nieczytelne wersje jako akcje `check_failed`.

## 8. Katalog stacji `stations.geojson`

```python
@dataclass(frozen=True)
class CatalogReport:
    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None; station_count: int; without_location: int
    problems: tuple[str, ...]
def check_catalog(root: RootArg, /, *, user_locations: PathArg | None = None,
                  on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> StorePlan: ...
def build_catalog(root: RootArg, /, *, user_locations: PathArg | None = None,
                  on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> CatalogReport: ...
```

Katalog bierze dwie listy CSV z `station_source_files()` (przy braku wersji w magazynie pobiera je i **najpierw** zapisuje przez `write_archive`), odpowiedzi publicznych `api/data/hydro` i `api/data/meteo`, opcjonalny lokalny plik statyczny `hydro_stations_locations.csv` z `settings.data_dir` (domyślnie `./data`; zapisuje go `python -m imgwtools.reference_data`, bo dane IMGW-PIB nie są dołączane do repozytorium ani wheel) i opcjonalny CSV UTF-8 użytkownika `station_code,lon,lat,source`. Pierwszeństwo położenia: API → plik statyczny → plik użytkownika; zły punkt z wyższego źródła nie blokuje poprawnego niższego. API mapy `hydro-back.imgw.pl` nie jest wywoływane przez katalog. Skan obejmuje wszystkie kody źródeł, nawet historyczne; brak pola API = null.

`0,0`, błędne liczby i punkty poza Polską → `geometry=null` oraz `location_missing_reason` (`zero`, `none`, `outside_country`), bez zgadywania z kodu stacji. Rzeczywistą granicę (nie prostokąt) dostarcza mały dołączony do wheel zasób `src/imgwtools/_data/poland_border_wgs84.geojson`: niezmieniony pierścień Polski (`ADM0_A3=POL`, 1332 wierzchołki) z Natural Earth 1:10m Cultural Vectors v5.1.2, Admin 0 – Countries (domena publiczna; źródło i licencja w `properties` obiektu), niepochodzący z danych IMGW ani z usuniętego z repozytorium `data/shp`; runtime czyta go ze stdlib (`importlib.resources`) i wykonuje point-in-polygon bez GDAL, pyproj ani pyshp. Generalizacja skali 1:10m sięga ok. 1 km, dlatego punkt poza obrysem, ale nie dalej niż `BORDER_TOLERANCE_M` = 1500 m od jego krawędzi, uznajemy za położony w kraju. Pomiar 2026-10-17 na 2956 rzeczywistych punktach stacji (dawny plik statyczny oraz bieżące `api/data/hydro` i `api/data/meteo`): ścisły test z obrysem Natural Earth odrzucał 30 punktów (wodowskazy na Odrze i Bugu, wybrzeże, Tatry), wszystkie najwyżej 968 m od linii; poprzedni obrys z `data/shp` odrzucał 11, najwyżej 610 m od linii. Ceną jest akceptacja punktów tuż za graniczną rzeką (np. Frankfurt nad Odrą, Czeski Cieszyn); zamienione lon/lat i punkty dalsze niż tolerancja nadal dają `outside_country`. Zmiana zasobu wymaga świadomego testu punktów przy granicy. Współrzędne danych traktujemy jak EPSG:4326 (IMGW nie deklaruje CRS), kolejność `[lon,lat]`. Niepewność = max(150 m, połowa kroku zaokrąglenia źródła w metrach na szerokości stacji); 2 miejsca ~550 m, 4 miejsca 150 m.

`river` z pola `rzeka` publicznego API; poprawka starego helpera API mapy `riverName` w `stations.py` jest niezależną regresją, nie źródłem katalogu. `hydrographic_code` to tekst z nawiasu nazwy rzeki CSV, `river_order` pochodzi z jej czwartej kolumny bez przypisywania znaczenia hydrologicznego. `active` = obecna w publicznym API w dniu pobrania, inna = historyczna. Data pobrania i źródła są **tylko w sidecarze** (`extra.catalog[]`), bez `catalog_date` w GeoJSON: ponowne identyczne źródła dają te same bajty i ten sam SHA. Każdy użyty (i odrzucony niepoprawny) punkt/source jest zgłaszany w raporcie lub komunikatach; odpowiedzi API z danymi bieżącymi nie są składowane.

`station_code`, `kind` (`hydro|meteo`), `meteo_kind` (`climate|precipitation|null`), `name`, `river`, `hydrographic_code`, `river_order`, `location_source` (`api_hydro|api_meteo|static|user|null`), `location_uncertainty_m`, `location_missing_reason` (`none|zero|outside_country|null`), `active`, `established_year`, `gauge_zero_m`, `river_km`, `elevation_m`. `geometry` Point/null, `id` = kod stacji, obie listy jako kompletna suma kodów (użycie jednego kodu w dwóch rodzinach = błąd danych), sortowane po `station_code`, brak położenia **nie** wyklucza. `check_catalog` porównuje sygnały źródeł i lokalny plik bez pobierania ciała; same publiczne API list stacji może nie mieć stabilnego ETag — status `unverifiable`, nigdy ukryte GET w `check_*`. `build_catalog` pobiera potrzebne odpowiedzi, tworzy katalog, zapisuje SHA odpowiedzi źródeł w sidecarze; identyczna treść daje `unchanged` bez nowej wersji nawet następnego dnia.

**Rozstrzygnięcia implementacji (T11):** plik statyczny nie jest pakowany — dane IMGW-PIB nie trafiają do repozytorium ani wheel (gałąź `slave`, v2.2.0). `build_catalog` i `check_catalog` czytają `settings.data_dir/hydro_stations_locations.csv` (kolumny `id,X,Y` = lon/lat, format `python -m imgwtools.reference_data`; bez `pydantic-settings` katalog z `IMGW_DATA_DIR`, domyślnie `data`). Brak pliku nie jest błędem, ale nie jest cichy: raport dostaje problem (komunikat `catalog_problem` ze wskazaniem `reference_data`), a wpis `static` w `extra.catalog[]` ma `available: false`, `count: 0`, `sha256: null`; obecny plik daje `available: true` i `file` = sama nazwa pliku (bez lokalnej ścieżki). `check_catalog` porównuje SHA pliku albo jego brak z wpisem w sidecarze (`newer`, gdy plik pojawił się, zniknął lub zmienił treść). Pola API: hydro `id_stacji/stacja/rzeka/lon/lat/rok_zalozenia_stacji/rzedna_zerawodowskazu/kilometr_biegu_rzeki`, meteo `kod_stacji/nazwa_stacji/lon/lat/rok_zalozenia_stacji/wysokosc_npm`; `river` = API `rzeka`, dla stacji historycznej nazwa rzeki z listy CSV. `meteo_kind` = `null`, bo żadne źródło katalogu nie rozróżnia stacji klimatycznych i opadowych (bez zgadywania z kodu). Gdy żaden kandydat nie jest poprawny, `location_missing_reason` = powód pierwszego odrzuconego kandydata w kolejności pierwszeństwa, a bez kandydatów `none`; niepewność liczona z liczby miejsc dziesiętnych publikacji (max z połowy kroku szerokości i długości, min. 150 m). Obrys granicy: Natural Earth 1:10m bez upraszczania, z tolerancją 1500 m od krawędzi (wyżej). Sidecar katalogu ma `dataset="pl.imgw.stations"`, `extra.derived="catalog"`, `extra.catalog[]` = `{source,url,file,fetched_at,count,sha256}` dla `hydro_stations`, `meteo_stations` (ścieżka wersji archiwum), `api_hydro`, `api_meteo`, `static` (dodatkowo `available`), `user`. Błędy źródeł (HTTP, JSON, kod w dwóch rodzinach) są zgłaszane wyjątkiem `IMGWConnectionError`/`IMGWDataError`, a nie statusem `failed`. `check_catalog` zwraca `items` (HEAD dwóch list) i `actions` (`store catalog`: API `unverifiable`, pliki położeń przez SHA w sidecarze, stan katalogu). Kody `on_notice`: `license_terms`, `location_rejected`, `location_source`, `station_without_location`, `catalog_problem`, `source_unverifiable`.

## 9. Odczyt, eksport, PMAXTP

```python
@dataclass(frozen=True)
class StoreEntry:
    kind: Literal["archive", "series", "catalog", "pmaxtp", "problem"]
    slot: str; version: Path | None; meta: Meta | None
    problem_code: str | None; problem: str | None
@dataclass(frozen=True)
class Meta:
    schema: str; dataset: str; sha256: str; size_bytes: int
    downloaded_at: datetime; license: License; request: Mapping[str, object]
    extra: Mapping[str, object]                 # nieznane dodatkowe pola zachowane
@dataclass(frozen=True)
class StationFeature:
    station_code: str
    geometry: tuple[float, float] | None             # lon, lat; None = bez położenia
    properties: Mapping[str, str | int | float | bool | None]  # pola §8
@dataclass(frozen=True)
class StationSeriesIndex:
    file: Path                                   # względna do katalogu wersji
    sha256: str; rows: int
    variables: Mapping[str, StationCoverage]    # osobno zmienna/okres
@dataclass(frozen=True)
class SeriesIndex:
    schema: Literal["imgw-series/1"]; dataset: str
    year_type: Literal["hydrological", "calendar"]
    periods: tuple[tuple[date, date], ...]
    stations: Mapping[str, StationSeriesIndex]

def store_info(root: PathArg, /) -> StoreInfo: ...
def iter_store(root: RootArg, /, *, kind: str | None = None) -> Iterator[StoreEntry]: ...
def read_meta(path: PathArg, /) -> Meta: ...  # path = plik danych LUB *.meta.json
def current_version(root: RootArg, /, *, slot: str) -> StoreEntry | None: ...
def read_catalog(version: PathArg, /) -> tuple[StationFeature, ...]: ...
def read_series_index(version: PathArg, /) -> SeriesIndex: ...
def read_series(version: PathArg, /, *, station: str, variables: Iterable[str],
                start: date | None = None, end: date | None = None) -> Iterator[NormalizedRecord]: ...
def export_series(version: PathArg, /, *, station: str, path: PathArg,
                  variables: Iterable[str], year_type: Literal["hydrological", "calendar"] | None = None,
                  format: Literal["csv"] = "csv", on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> Path: ...
```

`store_info` na nieznanym `imgw-store/2` zwraca `supported=False` + wersję bez rzucania; `open_store`/zapis odmawiają. `iter_store` działa offline, bez tworzenia czegokolwiek, raportuje osobne `StoreEntry(kind="problem")` dla nieznanych katalogów, braku sidecara, uszkodzonych JSON, nieznanego schematu i `.incoming` starszego niż 24 h; młodsze stagingi są prywatne i nie są wersjami. Toleruje **dodatkowe** pola w `/1`, ale nie brak/zły typ pól wymaganych. `current_version(root,slot=...)` przyjmuje slot `archive:<server_path>`, `series:<slug>`, `catalog:stations`, `pmaxtp:<method>:<indX>_<indY>`; nie zwraca stagingu. `read_series_index` czyta tylko JSON i działa bez pyarrow, waliduje schemat i ścieżki Parquet bez czytania ich bajtów. `read_series` waliduje istnienie/SHA potrzebnego Parquet, zwraca wartości i flagi po datach włącznie; dla miesięcy i półroczy filtr dotyczy okresu (`date` początku), wynik nie zmienia publikacji. `read_catalog` zwraca także stacje z `geometry=null`.

**Rozstrzygnięcia implementacji (T15):** `StoreInfo.exists` = istnieje katalog `root`; `contracts` to zawsze obsługiwane przez bibliotekę wersje (`store`, `meta`, `series`, `plan`, `project`, `pmaxtp`); `supported=False` również przy braku/nieczytelnym znaczniku lub braku `created_by`. Ta sama ocena obowiązuje `iter_store` (zgłasza jako problem slotu `store`) i `current_version` (`IMGWStoreError`). `StoreEntry.version` = ścieżka pliku głównego (jak `VersionResult.path`), dla problemu — ścieżka wadliwego elementu; `slot` problemu = slot wersji albo ścieżka względna. Kody problemów: `missing_store`, `missing_marker`, `invalid_marker`, `unsupported_store`, `unknown_entry`, `symlink`, `missing_sidecar`, `missing_file`, `unreadable`, `invalid_json`, `unknown_schema`, `invalid_meta` (brak/zły typ pola wymaganego, katalog ≠ `<label>_<sha8>`, `request.server_path` ≠ ścieżka), `size_mismatch`, `stale_incoming`. Skan nie haszuje plików (tylko rozmiar vs `size_bytes`); SHA sprawdzają `read_catalog`/`read_series_index` (plik główny vs sidecar) i `read_series` (Parquet vs spis). `Meta.extra` = obiekt `extra` sidecara; dodatkowe pola najwyższego poziomu są ignorowane. `current_version`: archiwum wg Last-Modified → `downloaded_at` → ścieżka, wersje pochodne wg `downloaded_at` → ścieżka; uszkodzona wersja w slocie → `IMGWDataError` (bez cichego wyboru starszej), brak slotu → `None`. `read_meta`: brak sidecara → `IMGWStoreError`, zła treść → `IMGWDataError`. `read_series` waliduje argumenty, spis i SHA przed zwróceniem iteratora; `variables` to niepusta kolekcja zmiennych deskryptora (pojedynczy tekst odrzucany), dni/miesiące uzupełnione przez builder wracają jako `missing`, a dla półrocza `extrema_dates` zawiera każdą żądaną zmienną.

Eksport CSV: jeden wiersz nagłówka `date,year,<V> [<unit>],<V>_flag,…,attribution_source,attribution_processed`, UTF-8 bez BOM, przecinek, kropka dziesiętna, daty ISO, brak = pusta komórka + `missing`; jednostki w nagłówku i tekst formuł §5 dosłownie w **pierwszym wierszu danych** dwóch kolumn atrybucji (w następnych puste), żeby `csv.DictReader`, Excel i QGIS odczytały plik bez komentarzy. Dla miesięcznych/półrocznych dodatkowa kolumna `period` dla półrocza/roku i kolumny dat ekstremów. `year` = rok z `date` albo `hydro_year`, `None` wybiera `series.json.year_type`; half_year/calendar = błąd walidacji. Eksport istniejącego, ale pustego szeregu odrzuca czytelnym błędem, by nie utracić formuł; zapis do unikalnego `.part`, `fsync`, `os.replace`, po anulowaniu plik docelowy pozostaje nietknięty. Każdy znany dzień z brakami pozostaje w wierszach.

**Rozstrzygnięcia implementacji (T17):** kolumna `period` oraz `<V>_start`/`<V>_end` (ISO, puste przy braku) występują tylko dla `half_year`; szereg miesięczny ma wyłącznie `date` (pierwszy dzień miesiąca) i `year`. Wartości w najkrótszym zapisie dziesiętnym bez wykładnika (`150.0`, `0.0`), flagi jako nazwy (`value`, `missing`, `no_phenomenon`, `accumulated`); powtórzone zmienne scalane, kolejność jak w `variables`. `attribution_source` = formuła źródła, `attribution_processed` = formuła przetworzenia. Separator wierszy CSV `\r\n` (RFC 4180). Ścieżka docelowa musi wskazywać plik w istniejącym katalogu (bez tworzenia katalogów) → inaczej `IMGWValidationError`; `.part` jest ukrytym plikiem obok celu (`.<nazwa>.*.part`), usuwany przy każdym błędzie. Anulowanie (sprawdzane przed zapisem, co 256 wierszy i przed `os.replace`) zgłasza `IMGWStoreError` jak `write_archive`; `Progress(unit="row")` co 256 wierszy i na końcu, po sukcesie `Notice("info","license_terms")` z obiema formułami. Pusty szereg → `IMGWDataError`.

```python
@dataclass(frozen=True)
class PMaXTPStoreResult:
    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None; ind_x: int | None; ind_y: int | None
    result: PMaXTPResult | None

def check_pmaxtp(root: RootArg, /, *, method: Literal["POT", "AMP"],
                  latitude: float, longitude: float,
                  ind_x: int | None = None, ind_y: int | None = None,
                  on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> StorePlan: ...
def sync_pmaxtp(root: RootArg, /, *, method: Literal["POT", "AMP"],
                 latitude: float, longitude: float,
                 ind_x: int | None = None, ind_y: int | None = None,
                 on_progress: ProgressHook | None = None,
                 on_notice: NoticeHook | None = None,
                 cancel: Cancel | None = None) -> PMaXTPStoreResult: ...
def read_pmaxtp(root: RootArg, /, *, method: Literal["POT", "AMP"],
                 ind_x: int, ind_y: int, version: PathArg | None = None) -> PMaXTPResult: ...
```

PMAXTP endpoint `point/<P|A>/KS/{latitude:.4f}/{longitude:.4f}` zwraca `point.indX/indY`, `point.dataLon/dataLat` (środek komórki) i `data.ks/sg/rb`. **Autorytatywny klucz = indeksy z odpowiedzi**, bez zgadywania po krokach siatki; jeśli podano `ind_x/ind_y` i odpowiedź się różni, błąd bez zapisu. `sync_pmaxtp` pobiera odpowiedź jeden raz i zachowuje niezmienione `fetch_pmaxtp`; `cell.json` to kanoniczne `{"schema":"imgw-pmaxtp/1","method":"POT","ind_x":751,"ind_y":317,"center":{"lon":21.007098333333,"lat":52.234416666667},"data":{"ks":{"15":{"50":13.34}},"sg":{"15":{"50":14.1}},"rb":{"15":{"50":0.3}}}}`, bez żądanych współrzędnych (dwa punkty tej samej komórki → ten sam SHA). Puste `data`, brak indeksu albo `error` = `IMGWDataError`, a nie „pusta komórka”. `check_pmaxtp` nigdy nie pobiera treści: bez indeksów plan `unverifiable` (endpoint nie ma HEAD gwarantującego sygnał), z indeksami informuje o lokalnym istnieniu i aktualności `unverifiable`; plan nie upoważnia do założenia, że dane są najnowsze. PMAXTP ma niezmienny sidecar `imgw-meta/1`, label downloaded, kopię przy zmianie treści; `read_pmaxtp` jest offline i nie wymaga pyarrow.

**Rozstrzygnięcia implementacji (T14):** odpowiedź z `error`, bez `point.indX/indY`, bez `dataLon/dataLat` albo z pustym `data`/tabelą → `IMGWDataError`; indeksy podane przez użytkownika niezgodne z odpowiedzią → `IMGWValidationError`; w obu przypadkach nic nie jest zapisywane. Sidecar komórki: `dataset="pl.imgw.pmaxtp"`, `license.attribution` = obie formuły §4 połączone kropką, `request` = metoda, indeksy, żądany punkt i URL. `read_pmaxtp(version=…)` przyjmuje katalog wersji lub `cell.json` (względnie do root albo bezwzględnie), weryfikuje SHA z sidecarem; `PMaXTPResult.latitude/longitude` z odczytu to środek komórki. `check_pmaxtp` zwraca jedną `PlanAction("pmaxtp sync","unverifiable",…)` z informacją o lokalnej wersji. Brak zapisanej komórki przy odczycie → `IMGWStoreError`.

## 10. Katalog komend, CLI, REST i projekt

```python
@dataclass(frozen=True)
class CommandOption:
    name: str; type: Literal["str", "int", "path", "bool", "list", "choice"]
    required: bool; flag: str; choices: tuple[str, ...]; help: str
@dataclass(frozen=True)
class DataCommand:
    name: str; description: str; options: tuple[CommandOption, ...]
@dataclass(frozen=True)
class SeriesSelection:
    dataset: str; version: Path; stations: tuple[str, ...]
    variables: tuple[str, ...]; years: tuple[int, ...]
    year_type: Literal["hydrological", "calendar"]

def data_commands() -> tuple[DataCommand, ...]: ...
def validate_command(command: str, /, *, options: Mapping[str, object]) -> dict[str, object]: ...
def format_command(command: str, /, *, options: Mapping[str, object]) -> str: ...
def check_command(command: str, /, *, options: Mapping[str, object],
                  on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> StorePlan: ...
def run_command(command: str, /, *, options: Mapping[str, object],
                on_progress: ProgressHook | None = None,
                on_notice: NoticeHook | None = None,
                cancel: Cancel | None = None) -> StoreHandle | StoreInfo | tuple[StoreEntry, ...] | StorePlan | SyncReport | SeriesReport | SeriesSelection | CatalogReport | PMaXTPStoreResult | PMaXTPResult | Project | ProjectReport | Path: ...
```

Katalog danych obejmuje **każdą** komendę czytającą lub piszącą dane: `store init|info|scan|check|sync|catalog`, `series build|export|select`, `pmaxtp check|sync|read`, `project init|add|remove|set-store|download|check|status|verify`, istniejące `fetch hydro|meteo` (pozostałe live-only fetch/list/admin poza katalogiem działań magazynu). Opisy po polsku odpowiadają `--help`; nazwy opcji Python `snake_case`, CLI `--kebab-case`, root `--root`, dataset `--dataset`, roczniki `--years`, stacje `--stations`, zakres `--start/--end`, metoda `--method`, `--lat/--lon`, plan `--plan`. `validate_command` bez sieci odrzuca obce komendy/opcje i wartości; `format_command` stabilnie cytuje przez `shlex.quote`, nie tworzy ukrytych opcji, plan może być zapisany do wskazanej ścieżki poza magazynem. `check_command` dla `store sync` używa `check_store`, dla `series build` `check_series`, dla `store catalog` `check_catalog`, dla `project download` `check_project`, dla `pmaxtp sync` `check_pmaxtp`; dla eksportu i małych zapisów manifestu daje `StorePlan.actions` z przewidywanymi ścieżkami i wynikami walidacji, bez mutacji lub GET treści. Operacje czysto odczytowe również mają reprezentację `PlanAction`, więc `run_command`/`check_command` przyjmują identyczne opcje; nie są potrzebne osobne bliźniaki dla komend read-only. Jeden mechanizm dispatch publicznych API, CLI **nigdy** nie implementuje własnego GET. Zewnętrzny odbiorca Retman weryfikuje np. `dataset`, `stations`, `variables`, zakres i `format="csv"` przez katalog/walidator; nie importujemy Retmana. `on_progress` w długich operacjach ma jednostkę, bieżącą/łączną liczbę, status i tekst; `on_notice` ma level/code/tekst PL identyczny jak CLI; `cancel` sprawdza się między plikami/stacjami, daje raport częściowy i żadnego częściowego katalogu wersji.

**Rozstrzygnięcia implementacji (T18):** `imgwtools.commands`. Flaga `--check` CLI to `check_command` danej komendy, nie opcja katalogu. Opcje `list` w CLI są rozdzielane przecinkami (Python przyjmuje też sekwencję lub pojedynczą liczbę), roczniki przyjmują zakresy `a-b`; `validate_command` zwraca znormalizowany słownik w kolejności katalogu (`Path`, krotki, roczniki/miesiące posortowane, stacje/zmienne bez duplikatów) i pomija `None` oraz fałszywe flagi `bool`, dlatego `format_command` → ponowne sparsowanie → `validate_command` daje identyczne opcje. Brak typu float w `CommandOption`: `lat`/`lon` mają typ `str` i normalizują się do `float` w granicach Polski. `store check|sync` mają opcję `dataset` typu `list` (→ `datasets=`); `store check --plan` zapisuje plan wyłącznie poza root. `project add --options` to obiekt JSON opcji komendy zadania, walidowany tą samą funkcją bez `root` (magazyn wynika ze `store_dir`); dozwolone komendy zadań: katalog bez `store init` i `project *`. `fetch hydro|meteo` zachowują istniejące opcje `--interval/--year/--month/--param|--subtype/--output` (domyślne jak w CLI), pobierają przez publiczne `download_*`, zapisują `<output>/<server_path>` przez `.part`, nieudany plik = `Notice("error","download_failed")` bez przerywania, wynik = katalog wyjściowy. `check_command` dla komend bez własnego `check_*`: `store init` wg `store_info` (`current`/`missing`/`check_failed`), odczyty (`store info|scan`, `project status|verify`) `current`, `series select` `current`/`missing`/`check_failed`, `series export` `missing`/`newer` (nadpisanie)/`check_failed` po walidacji spisu, `pmaxtp read` `current`/`missing`, zapisy manifestu `project init` `missing`/`current`, `project add|remove|set-store` `newer`/`check_failed` (brak manifestu), `fetch *` jedna akcja na plik (`missing`/`unverifiable` gdy plik lokalny istnieje); `store sync --plan` zwraca wczytany plan po sprawdzeniu root. `StorePlan.root` takich planów = root magazynu, katalog projektu, katalog wyjściowy albo magazyn zawierający wersję eksportu. `series select` zwraca `SeriesSelection.version` = `series.json` bieżącej wersji, domyślnie wszystkie zmienne zbioru i wszystkie lata okresów szeregu wg `year_type` (domyślnie z `series.json`); stacja lub rok spoza szeregu → `IMGWValidationError`.

| CLI | Publiczne API | Uwagi |
|---|---|---|
| `imgw store init --root …` / `info --root …` / `scan --root …` | `init_store` / `store_info` / `iter_store` | `info`,`scan` offline |
| `imgw store check --root … --dataset … --years 2023-2025 --plan plan.json` | `check_store` + `StorePlan.to_json` | HEAD i listing; plan poza magazynem |
| `imgw store sync --root … --plan plan.json [--no-series]` | `sync_store` | bez planu `--dataset`, `--years` |
| `imgw store catalog --root … [--user-locations …]` | `build_catalog` | `--check` → `check_catalog` |
| `imgw series build --root … --dataset …` / `export --version … --station … --path … --variables …` | `build_series` / `export_series` | `--check` analogicznie |
| `imgw series select --root … --dataset … --stations …` | `current_version` + walidowany wybór | komenda bez zapisu; wejście projektu |
| `imgw pmaxtp check|sync --root … --method POT --lat … --lon …` / `read --root … --method POT --ind-x … --ind-y …` | `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp` | nie mylić z `imgw fetch pmaxtp` live |
| `imgw project init|add|remove|set-store|download|check|status|verify …` | funkcje `project.py` | brak dotykania manifestu Kartografa |
| istniejące `imgw fetch hydro|meteo` | `archive_files` + publiczne `download_*` | `--output` odzwierciedla `server_path`, `.part`; inne istniejące CLI zostają |

REST: istniejące `/api/v1/hydro|meteo|download|pmaxtp` URL-e zachowują odpowiedzi, `/api/v1/hydro/data` DB-only znika (breaking). Dodajemy `GET /api/v1/store/info`, `GET /api/v1/store/entries`, `POST /api/v1/store/check`, `POST /api/v1/store/sync`, `POST /api/v1/store/catalog`, `POST /api/v1/series/build`, `GET /api/v1/series/index`, `GET /api/v1/series/{station}`, `POST /api/v1/series/export`, `POST /api/v1/pmaxtp/store/sync`. Odczyt i zapis bazują na publicznych funkcjach. Wszystkie te trasy korzystają tylko z **serwerowego, absolutnego** `IMGW_STORE_ROOT`; brak ustawienia → 503 dla tras store, generator URL i live pozostają dostępne. Klient nie podaje root ani absolutnej ścieżki; `version` w query/body jest ścieżką względną do root pod `versions/`, walidowaną przed odczytem. Żaden plik magazynu nie jest zapisywany domyślnie przez REST.

`GET info` = pola `StoreInfo`; `GET entries?kind=…` = lista `StoreEntry`, także `problem`; `GET series/index?version=…` = `SeriesIndex`; `GET series/{station}?version=…&variables=Q,H&start=…&end=…` = lista rekordów wartości/flag; identyczne zasady jak Python API. `POST store/check` i `POST store/sync` przyjmują `{"datasets":["pl.imgw.hydro_daily"],"years":[2024],"months":null}`; sync może zamiast selektorów przyjąć `{"plan":<obiekt imgw-plan/1>,"series":true}`. `POST store/catalog` przyjmuje opcjonalnie wyłącznie nazwę **wcześniej umieszczonego na serwerze** pliku współrzędnych w skonfigurowanym katalogu, nie arbitralną ścieżkę klienta; `POST series/build` przyjmuje `{"dataset":"pl.imgw.hydro_daily"}`; `POST pmaxtp/store/sync` przyjmuje `{"method":"POT","latitude":52.23,"longitude":21.01}`. `POST series/export` przyjmuje `{"version":"series/versions/…/series.json","station":"149190310","variables":["Q"],"year_type":"hydrological"}` i zwraca `text/csv; charset=utf-8` jako załącznik z pliku tymczasowego poza magazynem, usuwanego po odpowiedzi; nie akceptuje ścieżki wyjścia od klienta.

Katalog dopuszczonych CSV użytkownika dla REST określa wyłącznie serwerowe absolutne `IMGW_USER_LOCATIONS_DIR` (domyślnie brak = bez tej opcji); przyjmowany basename bez separatorów i bez symlinków. Python API/CLI mogą wskazać jawny plik przez `user_locations`.

Wywołania **piszące** wymagają jednocześnie `IMGW_STORE_WRITES_ENABLED=true` (domyślnie false), skonfigurowanego niepustego `IMGW_STORE_WRITE_TOKEN` po stronie serwera oraz nagłówka `X-API-Key` porównanego w stałym czasie; brak któregoś → 403, brak ważnego root → 503. Nie korzystamy z dotąd niewdrożonego middleware kluczy administracyjnych. Serwer publiczny dodatkowo wymaga HTTPS i limitów żądań reverse proxy. `POST /store/check` sam nie pisze do root i jest dostępny przy wyłączonych zapisach, ale wymaga root; `series/export` zapisuje tymczasowo poza root, więc traktujemy go jako zapis dla kontroli uprawnień. Operacja POST zwraca pełny raport po zakończeniu, **nigdy** fikcyjne „202 ukończone”; długie zadania konsumenci uruchamiają przez Python API w swoim workerze. Błędy: walidacja 400/422, brak wersji 404, nieaktualny plan 409, sieć źródła 502, brak pyarrow 503; JSON `{"code":"…","detail":"… po polsku"}`.

### 10.1 `imgw-project/1` (własny manifest obok Kartografa)

```python
@dataclass(frozen=True)
class ProjectFile:
    role: Literal["series", "station_series", "catalog", "input"]
    path: Path; sha256: str; station: str | None = None
@dataclass(frozen=True)
class ProjectTask:
    name: str; command: str; options: Mapping[str, object]
    geometry_sha256: Mapping[str, str] | None
    pinned_at: datetime | None; imgwtools_version: str | None
    files: tuple[ProjectFile, ...]
@dataclass(frozen=True)
class ProjectReport:
    tasks: Mapping[str, Literal["unpinned", "current", "missing", "changed",
                                "upgraded", "failed", "cancelled"]]
    files: tuple[OperationResult, ...]; cancelled: bool
@dataclass(frozen=True)
class Project:
    path: Path; store_dir: Path; tasks: tuple[ProjectTask, ...]
    extensions: Mapping[str, object] = field(default_factory=dict)
def init_project(project_dir: PathArg, /, *, store_dir: PathArg) -> Project: ...
def open_project(project_dir: PathArg, /) -> Project: ...
def set_project_store(project_dir: PathArg, /, *, store_dir: PathArg) -> Project: ...
def add_project_task(project_dir: PathArg, /, *, name: str, command: str,
                     options: Mapping[str, object], geometry: PathArg | None = None) -> Project: ...
def remove_project_task(project_dir: PathArg, /, *, name: str) -> Project: ...
def check_project(project_dir: PathArg, /, *, tasks: Iterable[str] | None = None,
                  on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> StorePlan: ...
def download_project(project_dir: PathArg, /, *, tasks: Iterable[str] | None = None,
                     plan: StorePlan | PathArg | None = None,
                     update: Literal["pinned", "upgrade"] = "pinned",
                     on_progress: ProgressHook | None = None,
                     on_notice: NoticeHook | None = None,
                     cancel: Cancel | None = None) -> ProjectReport: ...
def get_project_status(project_dir: PathArg, /, *, tasks: Iterable[str] | None = None) -> ProjectReport: ...
def verify_project(project_dir: PathArg, /, *, tasks: Iterable[str] | None = None,
                   on_progress: ProgressHook | None = None,
                   on_notice: NoticeHook | None = None,
                   cancel: Cancel | None = None) -> ProjectReport: ...
```

`imgw-project.json` ma `schema`, `store_dir`, `tasks[]`: `name` 1–64 `[a-z0-9][a-z0-9_-]*` unikalny; `command` z katalogu, przede wszystkim `series select`; `options` z jawnym `dataset`, `stations` (lista 9-cyfrowych kodów), `variables`, `years`, `year_type`, opcjonalnie `geometry` (ścieżka zapisanego wyboru); `geometry_sha256` przy wyborze z obszaru; `pinned_at`, `imgwtools_version`, `files[]` z rolą `series|station_series|catalog|input`, `path` wersji względną do `store_dir`, pełnym `sha256`, opcjonalnym `station`. Żadnych sygnałów sieci ani danych źródłowych w manifeście. `store_dir` podane względnie zapisuje się względnie do projektu, bezwzględne zostaje bezwzględne; istniejący root ma znacznik IMGW, a `set_project_store` weryfikuje cel i zgodność istniejących pinów bez cichego przepięcia. Geometrię SHA haszuje się przed zapisaniem wyboru obszarem, wybór stacji jest materializowany raz z konkretnej wersji katalogu; brak stacji bez położenia może być wybrany po kodzie. `open_project` ściśle waliduje klucze, typy, opcje i ścieżki bez `..`/symlinków/ucieczki z root (różnie niż tolerancyjny `read_meta`), bez połączenia z siecią. W manifeście po pierwszym przypięciu `pinned_at` i `imgwtools_version` nie są null; `files` nie zmieniają się przy odtwarzaniu tych samych SHA. `download_project` domyślnie nie przepina istniejących zadań; brakujące wersje odtwarza wyłącznie przy identycznym pełnym SHA, w przeciwnym razie błąd pozycji i nie zmienia pinów. `update="upgrade"` wymaga świeżego check/plan i przepina **całe zadanie** tylko po pełnym sukcesie; brak dostępu do starych bajtów nie usprawiedliwia zastąpienia. `check_project` bez zapisu/GET treści, `status` sprawdza istnienie/rozmiar offline, `verify` oblicza pełne SHA i zgodność sidecarów offline. Projekt z dwoma manifestami: IMGWTools dotyka jedynie `imgw-project.json`.

Wyjątek od tolerancyjnego czytania plików `/1`: projekt odrzuca nieznane klucze strukturalne w każdym obiekcie (IMGW-14). Opcjonalne przyszłe pola bez zmiany major wolno wprowadzić **tylko** pod top-level `extensions: {…}`; nieznane wpisy w tej mapie są ignorowane semantycznie, ale zachowywane przy ponownym zapisie. Nowy klucz poza mapą wymaga `imgw-project/2`; pełna walidacja ścieżek i `options` obowiązuje zawsze.

Manifest zapisuje się jako kanoniczny JSON z LF przez tymczasowy plik+`fsync`+`os.replace`, pod krótką blokadą `.imgw-project.lock` utworzoną wyłącznym `mkdir` na czas odczyt–scalenie per zadanie–zapis; nie trzymamy locka podczas sieci/budowy Parquet, zastanej blokady nie przejmujemy automatycznie. Dwa procesy aktualizujące różne zadania kończą z obiema zmianami; konflikt modyfikacji tego samego zadania = jawny błąd.

**Rozstrzygnięcia implementacji (T19):** `imgwtools.project`. `Project.path` = bezwzględny katalog projektu, `Project.store_dir` = znormalizowana ścieżka bezwzględna; względny `store_dir` (argument i manifest) liczy się wobec katalogu projektu. Istniejący `store_dir` musi być obsługiwanym magazynem IMGW albo pustym katalogiem, a katalog projektu nie może leżeć w magazynie. `init_project` na istniejącym manifeście z tym samym magazynem zwraca go bez zapisu (inny magazyn → `IMGWProjectError`, zmiana przez `set_project_store`). `ProjectTask.options` = postać manifestu: listy JSON i ścieżki względne POSIX (`version` wobec magazynu, `geometry`/`path`/`output`/`plan`/`user_locations` wobec katalogu projektu; bez `..`, `.`, `\` i dowiązań; domyślne `output` komend `fetch` także wobec projektu). `series select` zapisuje jawnie `dataset, stations, variables, years, year_type`: `years` jest wymagane przy dodaniu (`validate_command("project add")`), brakujące `variables` = wszystkie zmienne zbioru, `year_type` = numeracja ZIP zbioru. `geometry` (plik w katalogu projektu, GeoJSON Polygon/MultiPolygon/Feature/FeatureCollection w WGS84; dozwolony tylko dla `series select`, wtedy `stations` opcjonalne) wybiera stacje rodziny zbioru (hydro/meteo) z położeniem w obszarze z bieżącej wersji `stations.geojson`; wynik sumuje się z kodami podanymi jawnie w posortowaną listę, `geometry_sha256 = {<options.geometry>: <SHA-256 bajtów użytych do wyboru>}`, a wersja katalogu zostaje od razu przypięta jako plik `catalog` (zadanie pozostaje nieprzypięte: `pinned_at=null`). Pin wskazuje zawsze plik wersji `<archives|series|stations|pmaxtp>/versions/…`, `station` jest wymagane dla `station_series`, `pinned_at` i `imgwtools_version` są oba null albo oba ustawione; JSON z powtórzonym kluczem lub NaN jest odrzucany. Blokada czeka do `LOCK_TIMEOUT_S = 5` s (ponawianie co 50 ms), potem `IMGWProjectError` z właścicielem z pliku `owner` (host, pid, czas). Scalanie: pod blokadą zadanie w manifeście porównuje się ze stanem z chwili odczytu — identyczne z nowym = bez zapisu, inne niż przy odczycie albo usunięte = `failed` z kodem `project_conflict`. `download_project` dla zadania nieprzypiętego lub `update="upgrade"`: `series select` synchronizuje roczniki archiwów pokrywające wybrane lata (przy innej numeracji ZIP także rocznik sąsiedni) przez `sync_store` — z `plan` wyłącznie pozycje tych archiwów (brak pozycji = błąd zadania, nieaktualne = `stale_plan`) — potem `build_series` zbioru i walidowany wybór; pozostałe komendy przez `run_command` z `root=store_dir`, przypinając wersje wskazane w wyniku (`SyncReport` → `input` i szeregi, `SeriesReport` → szereg ze wszystkimi stacjami, `CatalogReport` → `catalog`, `PMaXTPStoreResult` → `input`; wyniki bez wersji magazynu nie mają plików, a `plan` ich nie dotyczy). Piny `series select`: `series` (`series.json`), `station_series` wybranych stacji, `input` = `extra.source_files` sidecara szeregu oraz zachowany `catalog` wyboru obszarem. Pierwsze przypięcie daje `current`, upgrade z innymi plikami `upgraded`, z identycznymi `current` bez zapisu; `pinned_at` w UTC z dokładnością do sekundy, `imgwtools_version` = wersja pakietu. Tryb `pinned` dla zadania przypiętego nie łączy się z siecią, gdy wszystkie pliki są obecne; brakujące archiwum pobiera ponownie i uznaje za odtworzone wyłącznie przy identycznym SHA pod przypiętą ścieżką, brakujący szereg buduje wyłącznie, gdy bieżące wersje archiwów zbioru są dokładnie przypiętymi wejściami; wersji katalogu i komórek PMAXTP (etykieta z dnia pobrania) nie odtwarza. `set_project_store` przed zapisem oblicza pełne SHA każdego przypiętego pliku (także `catalog` zadań nieprzypiętych) w nowym magazynie. `ProjectReport.files`: `slot` = `<zadanie>:<ścieżka względem magazynu>` (błąd operacji: `<zadanie>:<slot operacji>`, błąd całego zadania: `<zadanie>:imgw-project.json`), `unchanged` = plik zgodny, `created` = utworzony lub odtworzony, `failed`/`stale_plan`/`cancelled` z `error`. `get_project_status` sprawdza istnienie oraz rozmiar i SHA zapisane w sidecarze (bez haszowania; Parquet stacji — istnienie), `verify_project` dodatkowo pełne SHA i spis `series.json` dla plików stacji; status zadania `changed` ma pierwszeństwo przed `missing`, nieprzypięte = `unpinned`. `check_project`: `StorePlan.root` = magazyn, `series select` → `check_store` roczników zadania, pozostałe → `check_command`; na zadanie jedna akcja `project download`: `check_failed` (błąd sprawdzenia albo zmieniony pin), `missing` (nieprzypięte, brak pinów albo magazynu), `newer` (nowsze/brakujące dane — zmienia je dopiero upgrade), `unverifiable`, `current`. Kody `on_notice`: `task_failed`, `project_conflict`, `pin_mismatch`; `Progress(unit="task")` w download/check, `unit="file"` w verify.

## 11. JSON Schemas i pliki przykładowe

Norma zapisu: JSON UTF-8, LF, full SHA = 64 małe cyfry hex, brak nieznanej wersji w czytniku `/1`. Schematy niżej to JSON Schema Draft 2020-12 (zapisane w specyfikacji; implementacja może użyć pydantic zamiast dodatkowej zależności `jsonschema`). `additionalProperties:true` w danych magazynu umożliwia addytywne rozszerzenia, **false** w instrukcji projektu. W przykładach `"000…"` poniżej użyto pełnej 64-znakowej wartości umownej; przykład **nie** służy jako fixtura sum kontrolnych.

### 11.1 `imgw-store.json` — `imgw-store/1`

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["schema","created_by"],"properties":{"schema":{"const":"imgw-store/1"},"created_by":{"type":"string","minLength":1}},"additionalProperties":true}
```

```json
{"schema":"imgw-store/1","created_by":"imgwtools 3.0.0"}
```

### 11.2 `<file>.meta.json` — `imgw-meta/1`

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["schema","producer","producer_version","dataset","country","provider","request","license","downloaded_at","sha256","size_bytes","extra"],"properties":{"schema":{"const":"imgw-meta/1"},"producer":{"const":"imgwtools"},"producer_version":{"type":"string"},"dataset":{"type":"string","pattern":"^pl\\.imgw\\.[a-z_]+$"},"country":{"const":"PL"},"provider":{"const":"IMGW-PIB"},"request":{"type":"object"},"license":{"type":"object","required":["id","attribution","url"],"properties":{"id":{"const":"IMGW-PIB"},"attribution":{"type":"string","minLength":1},"url":{"type":"string","format":"uri"}},"additionalProperties":true},"downloaded_at":{"type":"string","format":"date-time"},"sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"size_bytes":{"type":"integer","minimum":0},"extra":{"type":"object","required":["version"],"properties":{"version":{"type":"object","required":["label","label_source"],"properties":{"label":{"type":"string","minLength":1},"label_source":{"enum":["last_modified","downloaded","inputs"]}},"additionalProperties":true},"http":{"type":"object","properties":{"url":{"type":"string"},"etag":{"type":["string","null"]},"last_modified":{"type":["string","null"]},"content_length":{"type":["integer","null"]}}},"source_files":{"type":"array","items":{"type":"object","required":["name","file","sha256","label"],"properties":{"name":{"type":"string"},"file":{"type":"string"},"sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"label":{"type":"string"}}}},"catalog":{"type":"array"}},"additionalProperties":true}},"additionalProperties":true}
```

```json
{"schema":"imgw-meta/1","producer":"imgwtools","producer_version":"3.0.0","dataset":"pl.imgw.hydro_daily","country":"PL","provider":"IMGW-PIB","request":{"server_path":"dane_hydrologiczne/dobowe/2024/codz_2024.zip","year":2024,"month":null},"license":{"id":"IMGW-PIB","attribution":"Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy","url":"https://danepubliczne.imgw.pl/regulations"},"downloaded_at":"2026-10-17T12:00:00Z","sha256":"0000000000000000000000000000000000000000000000000000000000000000","size_bytes":42,"extra":{"version":{"label":"2025-08-28","label_source":"last_modified"},"period":{"year":2024,"month":null,"param":null,"year_type":"hydrological","start":"2023-11-01","end":"2024-10-31"},"http":{"url":"https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/dobowe/2024/codz_2024.zip","etag":"\"abc\"","last_modified":"Thu, 28 Aug 2025 12:00:00 GMT","content_length":42}}}
```

### 11.3 `series.json` — `imgw-series/1`

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["schema","dataset","year_type","periods","stations"],"properties":{"schema":{"const":"imgw-series/1"},"dataset":{"type":"string","pattern":"^pl\\.imgw\\."},"year_type":{"enum":["hydrological","calendar"]},"periods":{"type":"array","items":{"type":"array","prefixItems":[{"type":"string","format":"date"},{"type":"string","format":"date"}],"minItems":2,"maxItems":2}},"stations":{"type":"object","patternProperties":{"^[0-9]{9}$":{"type":"object","required":["file","sha256","rows","variables"],"properties":{"file":{"type":"string","pattern":"^stations/[0-9]{9}\\.parquet$"},"sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"rows":{"type":"integer","minimum":1},"variables":{"type":"object","additionalProperties":{"type":"object","required":["unit","first","last","with_value","accumulated","gaps"],"properties":{"unit":{"type":"string"},"first":{"type":["string","null"],"format":"date"},"last":{"type":["string","null"],"format":"date"},"with_value":{"type":"integer","minimum":0},"accumulated":{"type":"integer","minimum":0},"gaps":{"type":"array","items":{"type":"array","prefixItems":[{"type":"string","format":"date"},{"type":"string","format":"date"}],"minItems":2,"maxItems":2}}},"additionalProperties":true}}},"additionalProperties":true}},"additionalProperties":false}},"additionalProperties":true}
```

```json
{"schema":"imgw-series/1","dataset":"pl.imgw.hydro_daily","year_type":"hydrological","periods":[["2023-11-01","2024-10-31"]],"stations":{"149190310":{"file":"stations/149190310.parquet","sha256":"0000000000000000000000000000000000000000000000000000000000000000","rows":366,"variables":{"H":{"unit":"cm","first":"2023-11-01","last":"2024-10-31","with_value":365,"accumulated":0,"gaps":[["2024-02-29","2024-02-29"]]},"Q":{"unit":"m3/s","first":null,"last":null,"with_value":0,"accumulated":0,"gaps":[]}}}}}
```

### 11.4 `stations.geojson` — RFC 7946 FeatureCollection

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["type","features"],"properties":{"type":{"const":"FeatureCollection"},"features":{"type":"array","items":{"type":"object","required":["type","id","geometry","properties"],"properties":{"type":{"const":"Feature"},"id":{"type":"string","pattern":"^[0-9]{9}$"},"geometry":{"oneOf":[{"type":"null"},{"type":"object","required":["type","coordinates"],"properties":{"type":{"const":"Point"},"coordinates":{"type":"array","prefixItems":[{"type":"number"},{"type":"number"}],"minItems":2,"maxItems":2}}}]},"properties":{"type":"object","required":["station_code","kind","meteo_kind","name","river","hydrographic_code","river_order","location_source","location_uncertainty_m","location_missing_reason","active","established_year","gauge_zero_m","river_km","elevation_m"],"properties":{"station_code":{"type":"string","pattern":"^[0-9]{9}$"},"kind":{"enum":["hydro","meteo"]},"meteo_kind":{"enum":["climate","precipitation",null]},"name":{"type":"string"},"river":{"type":["string","null"]},"hydrographic_code":{"type":["string","null"]},"river_order":{"type":["integer","null"]},"location_source":{"enum":["api_hydro","api_meteo","static","user",null]},"location_uncertainty_m":{"type":["number","null"],"minimum":0},"location_missing_reason":{"enum":["none","zero","outside_country",null]},"active":{"type":"boolean"},"established_year":{"type":["integer","null"]},"gauge_zero_m":{"type":["number","null"]},"river_km":{"type":["number","null"]},"elevation_m":{"type":["number","null"]}},"additionalProperties":true}},"additionalProperties":true}}},"additionalProperties":true}
```

```json
{"type":"FeatureCollection","features":[{"type":"Feature","id":"149190310","geometry":null,"properties":{"station_code":"149190310","kind":"hydro","meteo_kind":null,"name":"Raba","river":"Raba","hydrographic_code":"2138","river_order":1,"location_source":null,"location_uncertainty_m":null,"location_missing_reason":"zero","active":true,"established_year":null,"gauge_zero_m":null,"river_km":null,"elevation_m":null}}]}
```

### 11.5 `plan.json` — `imgw-plan/1` (plik użytkownika poza magazynem)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schema", "root", "checked_at", "cancelled", "items", "series_state"],
  "properties": {
    "schema": {"const": "imgw-plan/1"},
    "root": {"type": "string"},
    "checked_at": {"type": "string", "format": "date-time"},
    "cancelled": {"type": "boolean"},
    "items": {"type": "array", "items": {
      "type": "object",
      "required": ["dataset", "server_path", "url", "year", "month", "param", "year_type", "status", "local_path", "local_sha256", "remote_etag", "remote_last_modified", "content_length", "error"],
      "properties": {
        "dataset": {"type": "string"},
        "server_path": {"type": "string"},
        "url": {"type": "string"},
        "year": {"type": ["integer", "null"]},
        "month": {"type": ["integer", "null"]},
        "param": {"type": ["string", "null"]},
        "year_type": {"enum": ["hydrological", "calendar", "none"]},
        "status": {"enum": ["current", "newer", "missing", "unverifiable", "check_failed"]},
        "local_path": {"type": ["string", "null"]},
        "local_sha256": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
        "remote_etag": {"type": ["string", "null"]},
        "remote_last_modified": {"type": ["string", "null"]},
        "content_length": {"type": ["integer", "null"]},
        "error": {"type": ["string", "null"]}
      },
      "additionalProperties": true
    }},
    "series_state": {"type": "object", "additionalProperties": {"enum": ["current", "outdated", "missing"]}},
    "actions": {"type": "array", "items": {
      "type": "object", "required": ["command", "status", "detail"],
      "properties": {
        "command": {"type": "string"},
        "status": {"enum": ["current", "newer", "missing", "unverifiable", "check_failed"]},
        "detail": {"type": "string"}
      },
      "additionalProperties": true
    }}
  },
  "additionalProperties": true
}
```

```json
{"schema":"imgw-plan/1","root":"/srv/imgw","checked_at":"2026-10-17T12:00:00Z","cancelled":false,"items":[{"dataset":"pl.imgw.hydro_daily","server_path":"dane_hydrologiczne/dobowe/2024/codz_2024.zip","url":"https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/dobowe/2024/codz_2024.zip","year":2024,"month":null,"param":null,"year_type":"hydrological","status":"newer","local_path":"archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/2025-08-28_00000000/codz_2024.zip","local_sha256":"0000000000000000000000000000000000000000000000000000000000000000","remote_etag":"\"new\"","remote_last_modified":"Sat, 17 Oct 2026 10:00:00 GMT","content_length":42,"error":null}],"series_state":{"hydro_daily":"outdated"},"actions":[]}
```

### 11.6 `imgw-project.json` — `imgw-project/1`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schema", "store_dir", "tasks"],
  "properties": {
    "schema": {"const": "imgw-project/1"},
    "store_dir": {"type": "string", "minLength": 1},
    "extensions": {"type": "object", "additionalProperties": true},
    "tasks": {"type": "array", "items": {
      "type": "object",
      "required": ["name", "command", "options", "pinned_at", "imgwtools_version", "files"],
      "properties": {
        "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
        "command": {"type": "string"},
        "options": {"type": "object"},
        "geometry_sha256": {"type": "object", "additionalProperties": {"type": "string", "pattern": "^[0-9a-f]{64}$"}},
        "pinned_at": {"type": ["string", "null"], "format": "date-time"},
        "imgwtools_version": {"type": ["string", "null"]},
        "files": {"type": "array", "items": {
          "type": "object", "required": ["role", "path", "sha256"],
          "properties": {
            "role": {"enum": ["series", "station_series", "catalog", "input"]},
            "path": {"type": "string", "minLength": 1},
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "station": {"type": "string", "pattern": "^[0-9]{9}$"}
          },
          "additionalProperties": false
        }}
      },
      "additionalProperties": false
    }}
  },
  "additionalProperties": false
}
```

```json
{"schema":"imgw-project/1","store_dir":"../imgw-store","tasks":[{"name":"raba-q","command":"series select","options":{"dataset":"pl.imgw.hydro_daily","stations":["149190310"],"variables":["Q"],"years":[2023,2024],"year_type":"hydrological"},"pinned_at":null,"imgwtools_version":null,"files":[]}]}
```

### 11.7 `cell.json` — `imgw-pmaxtp/1` (rozszerzenie IMGWTools)

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["schema","method","ind_x","ind_y","center","data"],"properties":{"schema":{"const":"imgw-pmaxtp/1"},"method":{"enum":["POT","AMP"]},"ind_x":{"type":"integer","minimum":0},"ind_y":{"type":"integer","minimum":0},"center":{"type":"object","required":["lon","lat"],"properties":{"lon":{"type":"number"},"lat":{"type":"number"}},"additionalProperties":false},"data":{"type":"object","required":["ks","sg","rb"],"properties":{"ks":{"$ref":"#/$defs/table"},"sg":{"$ref":"#/$defs/table"},"rb":{"$ref":"#/$defs/table"}},"additionalProperties":false}},"$defs":{"table":{"type":"object","minProperties":1,"additionalProperties":{"type":"object","minProperties":1,"additionalProperties":{"type":"number"}}}},"additionalProperties":true}
```

```json
{"schema":"imgw-pmaxtp/1","method":"POT","ind_x":751,"ind_y":317,"center":{"lon":21.007098333333,"lat":52.234416666667},"data":{"ks":{"15":{"50":13.34}},"sg":{"15":{"50":14.1}},"rb":{"15":{"50":0.3}}}}
```

## 12. Wyjątki, testy i kryteria zamknięcia

Podklasy publiczne: `IMGWStoreError` (zły/nieobsługiwany root), `IMGWStoreConflictError` (kolizja/race/nieatomowy FS), `IMGWStoreDependencyError` (brak pyarrow), `IMGWPlanStaleError` (nieaktualny plan jako wynik per slot, tylko przy atomowej operacji bez raportu jako wyjątek), `IMGWProjectError` (walidacja/lock/piny) — wszystkie pod `IMGWError`; walidacja wyborów `IMGWValidationError`, nieczytelne archiwa `IMGWDataError`, HTTP `IMGWConnectionError`. Skan offline zgłasza problemy jako `StoreEntry`, nie maskuje ich. `on_notice` kodowane identyfikatory (`license_terms`, `source_unverifiable`, `stale_plan`, `archive_failed`, `station_without_location`, `leftover_incoming`), tekst PL; wszystkie wyjątki publiczne mają polskie komunikaty.

Fixtury: małe ZIP-y z każdej odmiany (`codz_<y>_<m>` 2022, roczny 2023 UTF-8 BOM/średnik, 2024 CP1250/linia cytowana, `mies`, `polr_H/Q/T`, meteo `1995_k/o` roczne + `2001_01_k/o` miesięczne), zmienne status 8/9, opad zbiorczy, puste miesiące, 29 II, granica XI, H obecne przy braku Q, brak punktu, 0,0 i poza krajem. Nagrania `respx` obejmują listing i HEAD/GET, ETag i Last-Modified, brak nagłówków, nieistniejący rocznik, zmieniony HEAD po planie, awarię sieci, indeksy komórki PMAXTP i dwa punkty w jednej komórce. Materiał do publikacji fixtur ma być licencyjnie odpowiedni (krótkie dane syntetyczne i zanonimizowane nagłówki), nie całe rzeczywiste roczniki. `imgwtools.testing.build_fixture_store(root, *, variant: Literal["complete","corrupt","unknown_schema"]="complete") -> StoreHandle` buduje **publicznym writerem** katalog bez internetu, z zapisanym starym/nowszym/relabelowanym ZIP, bieżącą i nieaktualną serią oraz katalogiem z `geometry=null`; warianty dodają uszkodzony sidecar i nieznaną wersję do testu odczytu. Pakiet udostępnia fixtury przez `importlib.resources`; testy kontraktu konsumenta nie kopiują prywatnej implementacji parserów. Świadome testy `live` są osobne, nigdy w domyślnej bramce offline.

Realizacja `imgwtools.testing`: fixtury leżą w pakiecie pod `imgwtools/_data/fixtures/` (kopia 1:1 `tests/fixtures/store/`, pilnowana testem), dostępne publicznie przez `fixture_files() -> Traversable`. `build_fixture_store` wymaga pustego/nieistniejącego `root` (inaczej `IMGWStoreError`; nieznany wariant `IMGWValidationError`) i wymaga `pyarrow`. Podczas budowy synchroniczny `httpx.HTTPTransport` jest podmieniany (pod blokadą procesu) na odtwarzanie nagrań `recordings.json` + `builder_recordings.json` w ustalonej kolejności; nienagrane żądanie = błąd połączenia, niewykorzystane nagranie = `IMGWDataError`. `complete`: `codz_2024.zip` w wersjach `2026-10-17` (v1) → `2026-10-18` (te same bajty, `relabeled`) → `2026-10-19` (nowe bajty, bieżąca); dwie serie `hydro_daily` (starsza z v1, bieżąca z v3); seria `meteo_precip_daily` z `2001_01_o` nieaktualna po dopisaniu `1995_o`; obie listy stacji i katalog z `geometry=null`. `corrupt` obcina sidecar wersji v1; `unknown_schema` dodaje `series/versions/hydro_daily/2026-10-20_<sha8>/` z `imgw-meta/2` i `imgw-series/2`. Przy zamrożonym zegarze dwie budowy dają identyczne bajty wszystkich plików.

| Wymaganie | Kryterium akceptacji kontraktu (testy zachowania, nie tylko importy) |
|---|---|
| IMGW-1 | inicjalizacja/odmowa obcego/nested root, niezmienne stare pliki i brak linków, wersja bieżąca według reguły |
| IMGW-2 | wstrzyknięty wyjątek/anulowanie/race: brak połowicznej wersji; `.part` płaskiego fetch nie jest wynikiem, >24 h sprzątane |
| IMGW-3 | sumy i pochodzenie w każdym sidecarze, właściwe licencje, metadata bez pól Archiwisty |
| IMGW-4 | 12 przed 2023, jedna paczka po 2023, meteo roczne/miesięczne, bez kolizji serwerowych ścieżek, CSV list też ma wersję |
| IMGW-5 | `check_store` tylko HEAD/listing, plan JSON round-trip, `stale_plan`, relabel przy tym samym SHA, seria po zmianie wejść |
| IMGW-6 | wszystkie kody braków, 8/9, suma zbiorcza, CP1250/BOM/cytowania, błędny rekord zgłoszony, nie połknięty |
| IMGW-7 | Parquet wszystkich stacji, kalendarz ciągły, 29 II/XI, dokładny manifest wejść, `reused` bez ponownej budowy |
| IMGW-8 | pokrycie Q niezależne od H, pełne przerwy, znane okresy vs nieznane roczniki, brak zjawiska i opad zbiorczy |
| IMGW-9 | komplet stacji z/bez lokalizacji, pochodzenie/niepewność, `hydrographic_code` string, prefiks i czwarta kolumna |
| IMGW-10 | offline/read-only probe/sweep/read JSON+Parquet, problemy struktur i nieznane schematy, bez GET przy skanie |
| IMGW-11 | każda komenda katalogu i CLI wywołuje ten sam API; porównanie katalogów (sumy/sidecary przy stałym zegarze), postęp i cancel |
| IMGW-12 | CSV round-trip `csv.DictReader`, obie formuły bez komentarzy, puste komórki/flag i poprawny rok dla hydro/meteo |
| IMGW-13 | nieznane dodatkowe pola w `/1`, odmowa nieznanego major przy zapisie, skan problemu bez parsowania, fixtury publiczne |
| IMGW-14 | dwa manifesty obok, status/verify/check, wyścig dwóch zadań i konflikt, odtworzenie pinów tylko przy identycznym SHA |

Bramka końcowa: zestaw offline na `imgwtools.testing` plus testy integracyjne CLI/API/REST w konfiguracji bez dostępu do internetu; jednorazowe uruchomienie prawdziwego `imgw store …` i odczytu przez publiczne API z lokalnej syntetycznej paczki potwierdza przejście end-to-end. Po wdrożeniu: CHANGELOG/README/ARCHITECTURE/PROGRESS/CLAUDE z 3.0.0 i BREAKING, usunięcie `db`, aktualizacja wszystkich wywołań i testów, bez stubów i aliasów DB.
