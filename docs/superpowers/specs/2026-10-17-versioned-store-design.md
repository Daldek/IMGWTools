# Spec: wersjonowany magazyn danych IMGW

**Data:** 2026-10-17  
**Status:** zaakceptowane decyzje ADR-001 i ADR-002; kontrakt implementacji 3.0.0; §13 (ADR-002) ma pierwszeństwo przed §1–§12  
**Plan:** `../plans/2026-10-17-versioned-store.md`  
**Źródła normatywne:** `docs/DECISIONS.md` ADR-001, `Archiwista/docs/SPEC.md` 4.8.1–4.8.5 i 12.7–12.9, `Archiwista/docs/wymagania-imgwtools.md` R1–R12/IMGW-1..14, opisy IMGW w `data/desc/`. W razie konfliktu z historyczną, niezaimplementowaną specyfikacją `2026-08-02-unified-data-pipeline-design.md` obowiązuje ten dokument: **bez SQLite, pięć zbiorów archiwalnych + PMAXTP, bez shimów DB**.

## 1. Granice i organizacja kodu

Producentem danych i jedynym piszącym do katalogu IMGW jest IMGWTools; konsument czyta wyłącznie publiczne API. Korzeń magazynu jest jawnie wskazany i absolutyzowany na wejściu; nie ma domyślnego `./data`, połączenia z katalogiem Kartografa, plików ani indeksu Archiwisty w magazynie. Bieżące hydro, synop, ostrzeżenia i `fetch_pmaxtp` pozostają live-only i nie zmieniają kontraktu. API serwera pozostaje domyślnie generatorem URL; zapis do magazynu na serwerze tylko po jawnej konfiguracji uprawnionego katalogu.

> [ADR-002] Odczyty live pozostają bez magazynu, lecz są komendami katalogu (`current …`, `pmaxtp fetch|url`) z nazwami z §13.2–§13.3.

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

> [ADR-002] CLI i REST powstają z katalogu (`cli/_dispatch.py`, `api/routes/commands.py`, §13.10): `cli/store.py`, `series.py`, `pmaxtp.py`, `project.py`, `cli/fetch.py`, `cli/list_cmd.py`, `api/routes/store.py` i trasy legacy znikają; `core/url_builder.py` zachowuje tylko `build_pmaxtp_url` i `build_api_url`, a URL-e archiwów generuje `archive_files`.

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

> [ADR-002] `DatasetDescriptor` ma dodatkowo `kind`, `title`, `first_year`, `legacy_alias`, `in_store`, a `time_unit` także `term`; `datasets(*, kind=None)`; `get_dataset` przyjmuje klucz, slug albo alias legacy; `archive_files(..., years: YearsArg, months: MonthsArg | None, params)` (§13.4, §13.8). Podpisy `download_*` bez zmian.

Istniejące publiczne `download_*` zachowują dotychczasowe pozycje parametrów dla kompatybilności podpisu wejściowego; **nowe** funkcje są keyword-only po pierwszym obiekcie. W `DownloadResult.data` dokładne bajty odpowiedzi, nagłówki z tego samego GET (`Content-Length` int albo `None`, brak `ETag`/`Last-Modified` = `None`, bez zgadywania); HTTP 4xx/5xx, timeout i błędny ZIP = odpowiedni `IMGWError`. Url-builder starego API zachowuje swój zakres (także miesięczne/terminowe meteo poza rejestrem magazynu), lecz dla wspieranych pięciu zbiorów reguły i walidacja pochodzą z rejestru, nie z duplikowanej tabeli.

> [ADR-002] Rejestr obejmuje także pięć zbiorów tylko do pobrania (§13.4); `build_hydro_url`/`build_meteo_url` usunięto, jedynym generatorem URL-i archiwów jest `archive_files`.

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

> [ADR-002] Tabelę §2.1 uzupełnia §13.4 (13 deskryptorów). `get_dataset` i `archive_files` przyjmują też slug i alias legacy, a wyniki i sloty zawsze podają pełny klucz; slug zostaje wyłącznie w nazwach katalogów magazynu.

## 3. Magazyn, wersje i atomowość

```text
<root>/imgw-store.json
  archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/2025-08-28_<sha8>/codz_2024.zip
                                                                      codz_2024.zip.meta.json
  stations/versions/<label>_<sha8>/stations.geojson[.meta.json]
  series/versions/hydro_daily/<label>_<sha8>/series.json[.meta.json]
                                                  stations/149190310.parquet
  pmaxtp/versions/POT/751_317/<label>_<sha8>/cell.json[.meta.json]
                                             response.json
  .incoming/<hostname>_<pid>_<random-token>/...
```

`<sha8>` = pierwsze osiem małych cyfr hex **pełnego SHA-256 pliku głównego** (series: `series.json`). Spis serii haszuje pliki stacji, bez własnego hasha i bez `downloaded_at`, co eliminuje cykl sum. Etykiety: archiwum `YYYY-MM-DD` z `Last-Modified` w UTC albo `downloaded_at` UTC; jeśli różne sygnały HTTP dają ten sam dzień **i** SHA, do etykiety dołącza się stabilne `+<8 hex SHA-256(canonical etag,last_modified)>` (nowy sygnał, nowy katalog). Gdy identyczny sygnał i treść (porównanie z **każdą** wersją o tym samym SHA, także po wcześniejszym relabelingu): `unchanged`. Brak sygnału (`ETag`, `Last-Modified`) i identyczne bajty: `unchanged`; różna treść tej samej daty może mieć ten sam label, ale inne `sha8` i jest nową wersją. Pełny SHA potwierdza tożsamość; kolizja nazwy po skróceniu → `IMGWStoreConflictError`, nigdy nadpisanie. Katalog identyczny następnego dnia: `unchanged` niezależnie od etykiety. Seria: label = najpóźniejsza data `Last-Modified` wejść albo data budowy, `label_source="inputs"`; seria jest `reused`, jeśli **bieżąca** wersja serii ma ten sam zbiór uporządkowanych par `(ścieżka slotu, pełny sha256)` i schema, bez ponownego zapisu Parquet, także po samym relabelingu archiwum; starsza wersja o tym samym manifeście (powrót wejścia do wcześniejszej treści) nie jest ponownie używana — budowa publikuje nową wersję, która staje się bieżąca. PMAXTP: label = dzień pobrania (`downloaded`), identyczny `cell.json` = `unchanged`; brak HTTP signal. Bieżąca wersja archiwum = najnowszy czas `Last-Modified` (pełny timestamp w sidecarze; w razie braku — `downloaded_at`; remis według `downloaded_at`, potem leksykograficzna ścieżka); seria = najnowsze `downloaded_at`; katalog i komórka = najnowsze `downloaded_at`, przy remisie leksykograficzna ścieżka. Bieżącą serię oznacza się `outdated`, gdy jej zestaw pełnych SHA wejść nie zgadza się z bieżącymi slotami archiwów.

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

`init_store` tworzy tylko pusty/istniejący zgodny katalog i znacznik atomowo (odmowa w niepustym obcym katalogu); `open_store` wymaga znanego znacznika. Przed zapisem sprawdza się realne ścieżki przodków/istniejących potomków (pod istniejącym korzeniem IMGW z pominięciem jego własnych drzew `archives/`, `series/`, `stations/`, `pmaxtp/`, `.incoming/`, które zapisuje wyłącznie IMGWTools — sidecary wersji nie są przy tym czytane); rozpoznanie katalogu Kartografa bez importu po `kartograf-project.json` wskazującym właśnie dany katalog `output_dir` albo po `versions/` z sidecarem o `schema: kartograf-meta/1`; rozpoznanie IMGW po `imgw-store.json`. Sam manifest projektu obok magazynu bez wskazania na niego **nie** jest znacznikiem magazynu Kartografa. Nieczytelny znacznik przy istotnej ścieżce → błąd przed zapisem. Zakaz root IMGW wewnątrz root Kartografa i root Kartografa wewnątrz root IMGW; żadna warstwa nie zakłada importu Kartografa. Symlinki/`..` w ścieżkach slotu, ucieczka z korzenia i nieistniejący punkt montowania → błąd. Znacznik `imgw-store.json` publikuje się dowiązaniem twardym (wyłączność bez zastąpienia); system plików bez dowiązań twardych → `IMGWStoreError` przed utworzeniem magazynu.

**Publikacja:** unikalne `.incoming/<host>_<pid>_<token>` na tym samym systemie plików; strumieniowo zapisać oryginalne bajty i policzyć SHA w tym samym przebiegu (gdy `DownloadResult.data` już w pamięci — jeden przebieg po bajtach). Przy serii gotowy lokalnie Parquet skopiować do stagingu, nie zostawiać pyarrow tmp w `root`. Wyliczyć kanoniczne JSON, SHA i rozmiary; obok głównego pliku utworzyć `*.meta.json`; `flush/fsync` każdego pliku i katalogu stagingowego. Publikować **cały katalog wersji** pojedynczą operacją rename **bez możliwości zastąpienia istniejącego celu** (`renameat2(RENAME_NOREPLACE)` na wspieranym POSIX, odpowiednik no-replace na innych systemach; wydanie 3.0.0 implementuje wyłącznie Linuksa — na innych systemach zapis kończy się jawnym `IMGWStoreConflictError` przed publikacją). Samo `os.rename` nie daje tej gwarancji przy istniejącym pustym katalogu i nie jest dopuszczalnym fallbackiem; jeśli filesystem/SMB nie zapewnia semantyki, jawny `IMGWStoreConflictError` przed publikacją. Po sukcesie `fsync` katalogu nadrzędnego; przy wyścigu drugi proces weryfikuje pełny hash i wynosi `unchanged` lub błąd, nie podmienia pliku. Anulowanie/wyjątek pozostawia najwyżej prywatny staging; następny **zapis** sprząta tylko katalogi `.incoming/` starsze niż 24 h (każdy usunięty zgłasza `on_notice` kodem `leftover_incoming`; katalog usunięty równolegle przez inny proces nie jest błędem). Żadnego automatycznego czyszczenia wersji. Płaski `imgw fetch` poza magazynem zapisuje przez unikalny `<name>.part` i `os.replace` po walidacji, zachowuje **pełną ścieżkę** `ArchiveFile.server_path` w `--output`; przerwany `.part` nigdy nie jest wynikiem, brak pominięcia przy kolizji nazw.

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

> [ADR-002] `OperationResult` ma pola `task` i `error_code`, `slot` według §13.7; `years`/`months` przyjmują `YearsArg`/`MonthsArg`; `check_store(..., plan=PLIK)` zapisuje plan poza magazynem (§13.8–§13.9).

`check_store` działa na już utworzonym korzeniu, *nie pisze* nawet stagingu: wylicza pliki offline, sprawdza listing katalogów u IMGW dla opublikowanych lat i `HEAD` dla każdego istniejącego pliku, zero GET archiwum. Nie zakłada, że bieżący rok jest dostępny. `current` = lokalne wersje i zgodny dostępny sygnał (porównujemy oba obecne nagłówki), `newer` = inny ETag lub Last-Modified, `missing` = opublikowany plik bez lokalnej wersji, `unverifiable` = żaden porównywalny sygnał, `check_failed` = błąd HTTP/listingu; nieopublikowany rok widoczny w planie jako pozycja `unverifiable` z powodem „nieopublikowany” bez GET. `Content-Length` służy jedynie szacunkowi, nigdy decyzji o zmianie. Seria `outdated` gdy brakujące lub różne pełne hashe wejść, `missing` gdy brak serii. `cancel` → częściowy plan z dotąd sprawdzonymi pozycjami i `cancelled=true` (także w JSON), jawnie oznaczone niewykonane pozycje `unverifiable` z powodem „anulowano”.

`sync_store(plan=…)` nie łączy selektorów `datasets/years/months` z planem (oba naraz = walidacja błędna); bez planu wywołuje `check_store` z podanymi selektorami. Przed każdym GET wykonuje `HEAD` i porównuje sygnały planu; gdy się zmieniły, wynik pozycji `stale_plan`, bez pobierania tej pozycji. Nieznany sygnał → jawny `unverifiable`, pobranie możliwe wyłącznie przy świadomym `sync_store` bez planu (`on_notice`), po GET deduplikacja według SHA; żadne `check_failed` nie jest pobierane. `GET` nie służy testowi aktualności planu. Wyniki per slot: `created`, `relabeled`, `unchanged`, `reused`, `failed`, `stale_plan`, `cancelled`; wyjątek błędu pojedynczego pliku jest zachowany w raporcie. `series=True` buduje tylko z kompletnego skutecznie zsynchronizowanego zestawu wybranych okresów i bieżących archiwów (nie z nieudanych pozycji), `False` pozostawia serię `outdated`. Serializacja planu przez `StorePlan.to_json(path)` i `StorePlan.from_json(path)` UTF-8; plan jest poza magazynem, nigdy mutowalnym plikiem wewnątrz root.

Rozstrzygnięcia implementacji (T12): „opublikowany” = nazwa pliku w listingu katalogu nadrzędnego; listing 404/410, brak nazwy w listingu albo HEAD 404/410 → `unverifiable` z `error="nieopublikowany"` (bez HEAD/GET), inny błąd listingu/HEAD → `check_failed`. `PlanItem.local_path` jest względne do root (bieżąca wersja slotu wg §3). `series_state` w `check_store` = stan lokalny (§3), lecz `current` zmienia się w `outdated`, gdy plan zawiera dla zbioru pozycje `newer`/`missing`. `OperationResult.slot` = `archives/versions/<katalog>/<stem>`, `version` = bezwzględna ścieżka pliku głównego. Bez pobierania: `current` → `unchanged`; `nieopublikowany` → `unchanged` z `version=None`, `error="nieopublikowany"` (nie blokuje serii); `unverifiable` z planu → `unchanged` z ostrzeżeniem `source_unverifiable`; pozycje „anulowano” → `cancelled`. Gdy zbiór ma pozycje `failed`/`stale_plan`/`cancelled`, `build_series` nie jest wywoływane, a `SyncReport.series` zawiera `SeriesReport` `failed` (lub `cancelled`) z listą slotów w `problems`; błąd `IMGWError` budowy (np. brak pyarrow) również trafia do raportu jako `failed`. `StorePlan.from_json` odtwarza `ArchiveFile` z rejestru offline, a `url` pozycji musi być równy adresowi z rejestru (inaczej `IMGWDataError`), więc plan — także przekazany przez REST — nie kieruje HEAD/GET na inne serwery.

> [ADR-002] `OperationResult.slot` = `archive:<klucz>:<selektor>` (§13.7); w JSON `version` jest względna do root.

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
    extrema_occurrences: Mapping[str, int] = field(default_factory=dict)  # wiersze IMGW scalone w wartość

def parse_meteo_climate_daily(content: bytes | str, /, *, filename: str) -> Iterator[NormalizedRecord]: ...
def parse_meteo_precip_daily(content: bytes | str, /, *, filename: str) -> Iterator[NormalizedRecord]: ...
def normalize_archive(archive: ArchiveFile, /, *, data: bytes) -> Iterator[NormalizedRecord]: ...
def parse_stations_csv(content: str | bytes, /, *, kind: Literal["hydro", "meteo"],
                       encoding: str = IMGW_ENCODING) -> Iterator[StationListEntry]: ...
# Dotychczasowe parse_daily_csv, parse_monthly_csv, parse_semi_annual_csv,
# parse_zip_file, IMGW_ENCODING w imgwtools.parsers nadal dostępne.
```

Funkcje starych parserów hydro pozostają importowalne; normalizacja adaptuje ich rekordy do `NormalizedRecord` (bez zmiany starych modeli hydro tylko dla zgodności). Rekord hydro miesięczny agreguje trzy wskaźniki ekstremum do kolumn `H_min/H_mean/H_max`, `Q_*`, `T_*` jednego miesiąca; półroczne parametry z trzech różnych archiwów scala dopiero builder w jeden wiersz stacji × okres × rok, a `measurements` parsera zawiera tylko kolumny fizycznie obecne w danym ZIP. Nieobecne kolumny w wynikowej migawce stają się `None/missing`; konflikt dwóch **podanych** wartości tej samej kolumny nie jest ignorowany. `extrema_dates` wiąże daty od/do z nazwą konkretnej kolumny, np. `Q_max`. ZIP czytany z limitem liczby/rozmiaru plików i bez rozpakowywania ścieżek: bez path traversal/zip bomb; rozpoznanie CP1250, UTF-8 z BOM, `,`/`;`, podwójnie cytowanych całych linii i wierszy nagłówków **per plik**; nieprzetwarzalny rekord = `IMGWDataError` z nazwą ZIP/CSV i numerem linii, a nie pusty wynik. Kod stacji zawsze tekst; duplikat `(stacja, zbiór, data, period, kolumna)` o różnych wartościach/flagach = jawny błąd danych, nie „first wins”.

| Opis `data/desc/` | Kolejność i zasady normalizacji |
|---|---|
| `dane_hydrologiczne/codz_info.txt` | kod, nazwa, rzeka, rok hydro, miesiąc hydro, dzień, H, Q, T, miesiąc kalendarzowy. XI/XII = poprzedni rok kalendarzowy; H `9999`, Q `99999.999`, T `99.9` oraz brak dnia → `None/missing` **osobno dla każdej wielkości**. |
| `mies_info.txt` | jak hydro, zamiast dnia wskaźnik 1=min, 2=mean, 3=max; kolumny `H_min`, `H_mean`, `H_max`, `Q_*`, `T_*` mają własne flagi, datą jednostki jest pierwszy dzień miesiąca. Brak wartości nie jest zerem. |
| `polr_info.txt` | kod, nazwa, rzeka, rok hydro, okres 13=zima XI–IV, 14=lato V–X, 15=rok XI–X; H/Q/T, ekstremum min/mean/max, wartość, daty/godziny od–do (układ kolumn zależy od rocznika, niżej). `99999.999` = brak. Każda para okres × param × ekstremum z osobną wartością/flagą i datami ekstremum — jeden rekord także wtedy, gdy IMGW powtarza wiersz dla kolejnych wystąpień; średnia bez dat może mieć `None`. |
| `dane_meteorologiczne/k_d_format.txt` | kod, nazwa, rok/miesiąc/dzień, kolejno wartość+status: Tmax, Tmin, Tmean, Tground, P, typ opadu, wysokość pokrywy śnieżnej+status. Status 8: `None/missing`; 9: `0/no_phenomenon`, a nie brak. Typ opadu `S`/`W`/pusty zachować jako osobny atrybut rekordu, bez tworzenia liczby. |
| `o_d_format.txt` | kod, nazwa, rok/miesiąc/dzień, P+status, typ opadu, snow_cover+status, fresh_snow+status, gatunek śniegu+status, rodzaj pokrywy+status. Kody klasyfikacji zachować jako tekst/metadane, status 8/9 stosować per wartość; brak dnia w **istniejącym** miesiącu P=`0/no_phenomenon`, brak całego miesiąca P=`None/missing`. |

Jakościowe atrybuty meteo w `attributes` (`precip_type`, `snow_species`, `snow_cover_type`) nie trafiają do numerycznych `variables`. Suma dobowa P poprzedzona dniami statusu 8, oznaczona przez IMGW jako zbiorcza (opis `o_d_format.txt`), dostaje `accumulated`, a poprzednie dni pozostają `missing`; brak podstaw do przypisania jej poszczególnym dniom. Nie nadpisujemy ręcznie wartości hydro niezwiązanych z brakującą Q. Granica roku hydro 31 X / 1 XI i 29 II testowana dla hydro **i** meteo. Parser wybiera prawdziwe pliki `k_d`/`o_d` ZIP — nazwa `k_d_<okres>.csv`/`o_d_<okres>.csv`, gdzie okres to grupy cyfr rozdzielone `_` (IMGW: `k_d_1995.csv`, `k_d_01_2001.csv`) — nie inne pliki `*_t`/`*_m` w paczce (każda paczka klimatyczna 1951–2025 zawiera też `k_d_t_*.csv`); rozróżnia roczne do 2000 i miesięczne od 2001, nie wnioskuje zakresu tylko z brakujących wierszy. W plikach meteo i `polr` wiersz nagłówka — pierwszy niepusty wiersz pliku złożony wyłącznie z kodów kolumn (np. `kansp,kapost,dorok,…` w `o_d_08_2025.csv`, `pskdszs,psnzwp,…` w `polr_*_2024.csv`) — jest pomijany; każdy inny wiersz niebędący rekordem danych jest błędem `IMGWDataError` z numerem linii.

**Układy `polr` i powtórzone ekstrema (3.0.0, poprawki po teście E2E 1951–2025):** układ kolumn dat rozpoznaje się per plik z liczby kolumn wierszy danych; różna liczba kolumn w jednym pliku albo nieznany układ = `IMGWDataError`. 16 kolumn (1951–2022 bez 1997): data od i do po 4 pola — rok, miesiąc, dzień, godzina (bez minut); 17 kolumn z rokiem hydrologicznym powtórzonym w polu 9 każdego wiersza (1997): po nim 2 × 4 pola; 18 kolumn (opis `POLR_publiczne_format.txt`, od 2024): 2 × 5 pól z minutą; 2023 (separator `;`): 5 pól daty od, nieopisane pole (puste albo jedna cyfra, pomijane), 5 pól daty do i drugie takie pole, z obciętymi pustymi kolumnami końcowymi (H 20, Q 19, T 17 kolumn — 17 bez powtórzonego roku). Daty mają dokładność publikacji IMGW: pola czyta się do pierwszego pustego, brakujący miesiąc lub dzień = początek opublikowanej jednostki (`1952,01,,` → `1952-01-01T00:00`), godzina bez minut → `HH:00`, godzina 24 → północ dnia następnego, dzień 29–31 poza końcem krótszego miesiąca (IMGW pisze np. `09,31`) → ostatni dzień miesiąca. IMGW powtarza wiersz min/max dla każdego wystąpienia ekstremum (ta sama wartość, inne daty; 88 449 takich grup w archiwach 1951–2025, także identyczne wiersze w plikach z dokładnością do godziny): `normalize_archive` scala je w jeden rekord stacji × rok × okres × kolumna z najwcześniejszym początkiem i najpóźniejszym końcem w `extrema_dates` oraz liczbą scalonych wierszy w `extrema_occurrences`; różne wartości tego samego klucza pozostają jawnym `IMGWDataError`. `parse_semi_annual_csv` (dotychczasowe API) zwraca wiersze bez scalania, z tymi samymi regułami dat.

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

> [ADR-002] `StationCoverage.station` → `station_code`; pokrycie wersji szeregu zwraca `summarize_series` / `series summary` (§13.8).

Pokrycie liczone per **stacja × zmienna**, włącznie ze zmienną bez wartości (first/last `null`, `with_value=0`), nie jedna etykieta na stację. Dla hydro półrocznego/rocznego osobno per `period`; w `series.json` klucz `variables` ma np. `Q_min@winter`, `Q_min@summer`, `Q_min@annual`, nie sumę trzech nakładających się okresów. `gaps`: maksymalne domknięte przedziały znanych jednostek bez wartości **między** pierwszą i ostatnią wartością; brak na początku/końcu znanej serii ujawniają `periods` i first/last, nie ukrywają jako „nieznane”. `no_phenomenon=0` i `accumulated` liczą się jako wartość (ta ostatnia zwiększa `accumulated`). `periods` to unia dokładnych okresów **posiadanych archiwów wejściowych**, nie „od min do max” po rekordach. Brak całego niepobranego ZIP = jednostki nieznane, nie luki; brak w posiadanym ZIP = luki. Posiadane jednostki rozpoznaje się z rekordów zbioru: doba i miesiąc — miesiąc kalendarzowy z rekordem dowolnej stacji; półrocze/rok — okres roku hydrologicznego z rekordem danej zmiennej (archiwa `polr_<H|Q|T>` są osobne). Stacja nieobecna w posiadanej jednostce między pierwszą i ostatnią wartością ma tam lukę — także w zbiorach miesięcznych i półrocznych; `summarize_coverage` i `build_series` liczą to tą samą funkcją. Dla doby okresy i luki w dniach, dla miesiąca ISO pierwszy/ostatni dzień miesiąca, dla półrocza/roku zapis dat granicznych 13/14/15 z rozdzielnym pokryciem `period` (nigdy nie traktować 15=rok jako trzeciego półrocza). IMGWTools nie liczy etykiet interfejsu („ciągły”, „luki …”).

`build_series` czyta dokładnie bieżące wersje archiwów danego zbioru, buduje migawkę wszystkich napotkanych stacji (także bez geometrii, z przerwami, z samym H bez Q); jeśli choć jedno wejście błędne, nie publikuje niepełnej migawki. Rekordy po walidacji (kod stacji, zmienne, flagi) trafiają w skompresowanych porcjach do tymczasowych plików per stacja poza magazynem (`tempfile`, katalog wg `TMPDIR`) i nie są przechowywane w pamięci; potem każda stacja jest składana, zapisywana do Parquet i liczona osobno, więc pamięć ogranicza kolejka rekordów i jedna stacja, a nie liczba archiwów zbioru. Sprzeczne wartości wykrywa składanie stacji; wynik jest bajtowo taki sam jak przy składaniu w pamięci (ta sama kolejność rekordów). Zanim zacznie kosztowną budowę, porównuje uporządkowany manifest `(slot, pełny sha256)` i schema z **bieżącą** wersją serii; przy tym samym stanie zwraca `reused`, **nie** wywołuje writerów Parquet. Parquet wymaga `pyarrow>=15`, deterministyczny wybór typów: `date: date32`, `hydro_year: int32`, `*_value: float64 (nullable)`, `*_flag: dictionary<string>` z wartościami `value|missing|no_phenomenon|accumulated`; null wartości tylko z flagą `missing`. W metadanych schematu UTF-8 `imgw_schema=imgw-series/1`, `dataset`, `units` jako kanoniczny JSON z kodem→jednostką. W każdym zbiorze jest `hydro_year`; w meteo też, nawet przy kalendarzowej numeracji ZIP-ów.

- Doba: `date` każdego dnia od pierwszego do ostatniego **rekordu stacji** (w tym dni brakujące w posiadanych archiwach), `hydro_year`, pary `H_value/H_flag`, `Q_…`, `T_…` albo `Tmax`, `Tmin`, `Tmean`, `Tground`, `P`, `snow_cover`, `fresh_snow` zależnie od deskryptora; brak zmiennej u stacji = kolumna null/missing, bez filtrowania stacji.
- Miesiąc: `date` = pierwszy dzień kalendarzowego miesiąca, `hydro_year`, 9 par `H_min/H_mean/H_max`, `Q_*`, `T_*`; wiersz na miesiąc.
- Półrocze/rok: `date` = początek okresu, `hydro_year`, `period: dictionary<string>` w zbiorze `winter|summer|annual`, dziewięć par H/Q/T × min/mean/max i odpowiadające im opcjonalne `*_start`/`*_end: timestamp[us]` dla dat ekstremów (przy kilku wystąpieniach najwcześniejszy początek i najpóźniejszy koniec) oraz addytywne w `imgw-series/1` `*_occurrences: int32` — liczba wierszy IMGW scalonych w wartość (null, gdy okresu nie ma w archiwach; czytniki tolerują jej brak w starszych plikach); 3 wiersze (zima, lato, rok) na rok hydro w wejściu, bez pozornej interpolacji nieopublikowanych danych.

`series.json` zawiera `stations[code].file` względne do katalogu danej wersji, `sha256` każdego Parquet, `rows`, `variables` z `unit,first,last,with_value,accumulated,gaps` oraz `periods` wspólne dla zbioru. `year_type` oznacza **numerację ZIP**, nie rodzaj lat widoku: hydro hydrological, meteo calendar; obliczanie `calendar`/`hydrological` w `read_series`/eksport z `date`, lecz dla half_year tylko hydrological. `series.json` jest kanonicznym JSON UTF-8 z LF, `sort_keys=True`, krótkimi separatorami, bez zmiennej daty budowy: te same wejścia → te same bajty. Timestamps budowy tylko w sidecarze.

Rozstrzygnięcia implementacji (T13): `SeriesReport.version` = ścieżka `series.json`, `source_files` = bezwzględne ścieżki wersji wejść (dla `reused` — wejścia zapisane w sidecarze ponownie użytej wersji). `periods` to unia okresów wejść ze scaleniem przyległych przedziałów. Szereg miesięczny ma wiersz dla każdego miesiąca od pierwszego do ostatniego rekordu stacji (jak doba), półroczny — trzy wiersze na każdy rok hydrologiczny stacji. `hydro_year` liczy builder z `date` (XI–X) dla wszystkich zbiorów. Słowniki `*_flag`/`period` mają stały zestaw wartości i indeksy `int8`. Identyczny `series.json` z innego manifestu wejść (np. przepakowany ZIP) dostaje etykietę `<label>+<8 hex SHA-256 manifestu>` zamiast kolizji; gdy nazwę zajmuje nieaktualna wersja tego samego manifestu (wielokrotny powrót wejść), kolejne próby używają `<label>+<8 hex SHA-256([manifest, n])>`, n = 2, 3, … `check_series` zwraca pozycje bieżących wejść (`current`, sygnały HTTP z sidecara) i akcję `series build` o statusie `current`/`newer` (outdated)/`missing`; nieczytelne wersje jako akcje `check_failed`.

## 8. Katalog stacji `stations.geojson`

```python
@dataclass(frozen=True)
class CatalogReport:
    status: Literal["created", "unchanged", "cancelled", "failed"]
    version: Path | None; station_count: int; without_location: int
    from_series: int                            # stacje znane wyłącznie z indeksów szeregów
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

Katalog bierze dwie listy CSV z `station_source_files()` (przy braku wersji w magazynie, innym niż zapisany sygnale `HEAD` ETag/Last-Modified albo braku porównywalnego sygnału pobiera je i **najpierw** zapisuje przez `write_archive`; identyczne bajty → `unchanged`, więc po budowie `check_catalog` widzi listy jako `current`), odpowiedzi publicznych `api/data/hydro` i `api/data/meteo`, opcjonalny lokalny plik statyczny `hydro_stations_locations.csv` z `settings.data_dir` (domyślnie `./data`; zapisuje go `python -m imgwtools.reference_data`, bo dane IMGW-PIB nie są dołączane do repozytorium ani wheel) i opcjonalny CSV UTF-8 użytkownika `station_code,lon,lat,source`. Pierwszeństwo położenia: API → plik statyczny → plik użytkownika; zły punkt z wyższego źródła nie blokuje poprawnego niższego. API mapy `hydro-back.imgw.pl` nie jest wywoływane przez katalog. Skan obejmuje wszystkie kody źródeł, nawet historyczne; brak pola API = null.

> [ADR-002] CSV użytkownika: `station_code,latitude,longitude[,source]` (§13.11).

`0,0`, błędne liczby i punkty poza Polską → `geometry=null` oraz `location_missing_reason` (`zero`, `none`, `outside_country`), bez zgadywania z kodu stacji. Rzeczywistą granicę (nie prostokąt) dostarcza mały dołączony do wheel zasób `src/imgwtools/_data/poland_border_wgs84.geojson`: niezmieniony pierścień Polski (`ADM0_A3=POL`, 1332 wierzchołki) z Natural Earth 1:10m Cultural Vectors v5.1.2, Admin 0 – Countries (domena publiczna; źródło i licencja w `properties` obiektu), niepochodzący z danych IMGW ani z usuniętego z repozytorium `data/shp`; runtime czyta go ze stdlib (`importlib.resources`) i wykonuje point-in-polygon bez GDAL, pyproj ani pyshp. Generalizacja skali 1:10m sięga ok. 1 km, dlatego punkt poza obrysem, ale nie dalej niż `BORDER_TOLERANCE_M` = 1500 m od jego krawędzi, uznajemy za położony w kraju. Pomiar 2026-10-17 na 2956 rzeczywistych punktach stacji (dawny plik statyczny oraz bieżące `api/data/hydro` i `api/data/meteo`): ścisły test z obrysem Natural Earth odrzucał 30 punktów (wodowskazy na Odrze i Bugu, wybrzeże, Tatry), wszystkie najwyżej 968 m od linii; poprzedni obrys z `data/shp` odrzucał 11, najwyżej 610 m od linii. Ceną jest akceptacja punktów tuż za graniczną rzeką (np. Frankfurt nad Odrą, Czeski Cieszyn); zamienione lon/lat i punkty dalsze niż tolerancja nadal dają `outside_country`. Zmiana zasobu wymaga świadomego testu punktów przy granicy. Współrzędne danych traktujemy jak EPSG:4326 (IMGW nie deklaruje CRS), kolejność `[lon,lat]`. Niepewność = max(150 m, połowa kroku zaokrąglenia źródła w metrach na szerokości stacji); 2 miejsca ~550 m, 4 miejsca 150 m.

`river` z pola `rzeka` publicznego API; poprawka starego helpera API mapy `riverName` w `stations.py` jest niezależną regresją, nie źródłem katalogu. `hydrographic_code` to tekst z nawiasu nazwy rzeki CSV, `river_order` pochodzi z jej czwartej kolumny bez przypisywania znaczenia hydrologicznego. `active` = obecna w publicznym API w dniu pobrania, inna = historyczna. Data pobrania i źródła są **tylko w sidecarze** (`extra.catalog[]`), bez `catalog_date` w GeoJSON: ponowne identyczne źródła dają te same bajty i ten sam SHA. Każdy użyty (i odrzucony niepoprawny) punkt/source jest zgłaszany w raporcie lub komunikatach; odpowiedzi API z danymi bieżącymi nie są składowane.

`station_code`, `kind` (`hydro|meteo`), `meteo_kind` (`climate|precipitation|null`), `name`, `river`, `hydrographic_code`, `river_order`, `location_source` (`api_hydro|api_meteo|static|user|null`), `location_uncertainty_m`, `location_missing_reason` (`none|zero|outside_country|null`), `active`, `established_year`, `gauge_zero_m`, `river_km`, `elevation_m`. `geometry` Point/null, `id` = kod stacji, listy, API, plik statyczny i bieżące indeksy szeregów jako kompletna suma kodów (użycie jednego kodu w dwóch rodzinach = błąd danych; kod wyłącznie w pliku statycznym współrzędnych wodowskazów = stacja `hydro` bez nazwy i rzeki, `active=false`; kod wyłącznie w `series.json` bieżącej wersji szeregu któregokolwiek zbioru — np. dawno zamknięte wodowskazy i umowny kod IMGW `123456789` z archiwów miesięcznych — = stacja historyczna rodziny zbioru, `active=false`, bez nazwy i rzeki, bo spis szeregu ich nie przechowuje, `geometry=null` z `location_missing_reason="none"`, o ile plik użytkownika nie poda położenia; ich liczba trafia do `CatalogReport.from_series`, a kody do komunikatu `series_station`; kody wyłącznie w pliku użytkownika trafiają do `problems`, bo ten plik tylko uzupełnia położenia), sortowane po `station_code`, brak położenia **nie** wyklucza. `check_catalog` porównuje sygnały źródeł i lokalny plik bez pobierania ciała; same publiczne API list stacji może nie mieć stabilnego ETag — status `unverifiable`, nigdy ukryte GET w `check_*`. `build_catalog` pobiera potrzebne odpowiedzi, tworzy katalog, zapisuje SHA odpowiedzi źródeł w sidecarze; identyczna treść daje `unchanged` bez nowej wersji nawet następnego dnia (także po nowej wersji szeregu bez nowych kodów stacji).

**Rozstrzygnięcia implementacji (T11):** plik statyczny nie jest pakowany — dane IMGW-PIB nie trafiają do repozytorium ani wheel (gałąź `slave`, v2.2.0). `build_catalog` i `check_catalog` czytają `settings.data_dir/hydro_stations_locations.csv` (kolumny `id,X,Y` = lon/lat, format `python -m imgwtools.reference_data`; bez `pydantic-settings` katalog z `IMGW_DATA_DIR`, domyślnie `data`). Brak pliku nie jest błędem, ale nie jest cichy: raport dostaje problem (komunikat `catalog_problem` ze wskazaniem `reference_data`), a wpis `static` w `extra.catalog[]` ma `available: false`, `count: 0`, `sha256: null`; obecny plik daje `available: true` i `file` = sama nazwa pliku (bez lokalnej ścieżki). `check_catalog` porównuje SHA pliku albo jego brak z wpisem w sidecarze (`newer`, gdy plik pojawił się, zniknął lub zmienił treść). Pola API: hydro `id_stacji/stacja/rzeka/lon/lat/rok_zalozenia_stacji/rzedna_zerawodowskazu/kilometr_biegu_rzeki`, meteo `kod_stacji/nazwa_stacji/lon/lat/rok_zalozenia_stacji/wysokosc_npm`; `river` = API `rzeka`, dla stacji historycznej nazwa rzeki z listy CSV. `meteo_kind` = `null`, bo żadne źródło katalogu nie rozróżnia stacji klimatycznych i opadowych (bez zgadywania z kodu). Gdy żaden kandydat nie jest poprawny, `location_missing_reason` = powód pierwszego odrzuconego kandydata w kolejności pierwszeństwa, a bez kandydatów `none`; niepewność liczona z liczby miejsc dziesiętnych publikacji (max z połowy kroku szerokości i długości, min. 150 m). Obrys granicy: Natural Earth 1:10m bez upraszczania, z tolerancją 1500 m od krawędzi (wyżej). Sidecar katalogu ma `dataset="pl.imgw.stations"`, `extra.derived="catalog"`, `extra.catalog[]` = `{source,url,file,fetched_at,count,sha256}` dla `hydro_stations`, `meteo_stations` (ścieżka wersji archiwum), `api_hydro`, `api_meteo`, `static` (dodatkowo `available`), `user` oraz po jednym wpisie `series` (dodatkowo `dataset`; `file` = `series.json` bieżącej wersji względem magazynu, `count` = liczba stacji spisu, `sha256` z sidecara szeregu) na każdy zbiór z wersją szeregu. Indeksy szeregów są czytane offline: bieżąca wersja = najnowsza zweryfikowana (SHA z sidecarem) wersja zbioru jak w `build_series`; nieczytelny spis bieżącej wersji = `IMGWDataError`, niepoprawny kod stacji w spisie = wpis w `problems`. Błędy źródeł (HTTP, JSON, kod w dwóch rodzinach) są zgłaszane wyjątkiem `IMGWConnectionError`/`IMGWDataError`, a nie statusem `failed`. `check_catalog` zwraca `items` (HEAD dwóch list) i `actions` (`store catalog`: API `unverifiable`, pliki położeń przez SHA w sidecarze, `indeksy szeregów` — `newer`, gdy kod stacji bieżącego szeregu nie występuje w bieżącym katalogu, inaczej `current`, bez katalogu `missing` — oraz stan katalogu). Kody `on_notice`: `license_terms`, `location_rejected`, `location_source`, `series_station`, `station_without_location`, `catalog_problem`, `source_unverifiable` (także lista bez porównywalnego sygnału pobierana w `build_catalog`), `leftover_incoming`.

> [ADR-002] Plik statyczny ma nagłówek `station_code,latitude,longitude` (zapisuje go `python -m imgwtools.reference_data`); nagłówek `id,X,Y` jest odrzucany z instrukcją ponownego wygenerowania pliku.

**Listy stacji jako zbiory (3.0.0):** zapisane wersje `pl.imgw.hydro_stations` i `pl.imgw.meteo_stations` czyta offline `read_station_list(root, /, *, kind)` (§9): bieżąca wersja slotu listy (`current_version`, uszkodzona wersja w slocie = `IMGWDataError`), weryfikacja SHA-256/rozmiaru z sidecarem, parser `parse_stations_csv(..., kind=...)`. Jeden typ wyniku `StationListEntry` (zamrożona dataclass) dla obu rodzin: `kind`, `station_code` (tekst), `name`; tylko hydro: `river`, `hydrographic_code` (tekst z nawiasu kolumny rzeki), `river_order` (czwarta kolumna); tylko meteo: `short_code` (trzecia kolumna listy meteo, tekst bez spacji) — pola drugiej rodziny są `None`. Brak zapisanej listy → `IMGWStoreError` wskazujący klucz zbioru i `build_catalog`; komunikaty i dokumentacja posługują się kluczami zbiorów, nie nazwami plików IMGW. `build_catalog` korzysta z tego samego parsera i typu; `HydroArchiveStation` opisuje wyłącznie stację z wierszy archiwów danych (`station_code`, `station_name`, `river_name`). Kod powtórzony na liście (IMGW podaje w `wykaz_stacji.csv` trzy stacje meteo dwukrotnie z różnymi kodami krótkimi) `read_station_list` zwraca w każdym wierszu w kolejności pliku, a `build_catalog` używa pierwszego wiersza i zgłasza w `problems` `Lista <rodzina>: powtórzony kod stacji <kod> (<wiersz 1> oraz <wiersz 2>); katalog używa pierwszego wiersza` — bez cichego wyboru i bez przerwania budowy.

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
def read_station_list(root: RootArg, /, *, kind: Literal["hydro", "meteo"]) -> tuple[StationListEntry, ...]: ...
def read_archive(version: PathArg, /) -> Iterator[NormalizedRecord]: ...
def read_series_index(version: PathArg, /) -> SeriesIndex: ...
def read_series(version: PathArg, /, *, station: str, variables: Iterable[str],
                start: date | None = None, end: date | None = None) -> Iterator[NormalizedRecord]: ...
def export_series(version: PathArg, /, *, station: str, path: PathArg,
                  variables: Iterable[str], year_type: Literal["hydrological", "calendar"] | None = None,
                  format: Literal["csv"] = "csv", on_progress: ProgressHook | None = None,
                  on_notice: NoticeHook | None = None,
                  cancel: Cancel | None = None) -> Path: ...
```

> [ADR-002] Zmienione podpisy `current_version` (gramatyka slotu), `read_series`, `export_series` oraz nowe `export_archive`, `select_series`, `summarize_series` — §13.7–§13.8; `StoreEntry.slot` może być `None`.

`store_info` na nieznanym `imgw-store/2` zwraca `supported=False` + wersję bez rzucania; `open_store`/zapis odmawiają. `iter_store` działa offline, bez tworzenia czegokolwiek, raportuje osobne `StoreEntry(kind="problem")` dla nieznanych katalogów, braku sidecara, uszkodzonych JSON, nieznanego schematu i `.incoming` starszego niż 24 h; młodsze stagingi są prywatne i nie są wersjami. Toleruje **dodatkowe** pola w `/1`, ale nie brak/zły typ pól wymaganych. `current_version(root,slot=...)` przyjmuje slot `archive:<server_path>`, `series:<slug>`, `catalog:stations`, `pmaxtp:<method>:<indX>_<indY>`; nie zwraca stagingu. `read_series_index` czyta tylko JSON i działa bez pyarrow, waliduje schemat i ścieżki Parquet bez czytania ich bajtów. `read_series` waliduje istnienie/SHA potrzebnego Parquet, zwraca wartości i flagi po datach włącznie; dla miesięcy i półroczy filtr dotyczy okresu (`date` początku), wynik nie zmienia publikacji. `read_catalog` zwraca także stacje z `geometry=null`.

> [ADR-002] Sloty: `archive:<klucz>:<selektor>`, `series:<klucz>`, `catalog:pl.imgw.stations`, `pmaxtp:pl.imgw.pmaxtp:<METODA>/<indX>_<indY>` (§13.7).

**Odczyt archiwum (3.0.0):** `read_archive(version)` przyjmuje katalog wersji archiwum, jej plik albo sidecar; `ArchiveFile` odtwarza z sidecara (`dataset` + `request.server_path`/`year`/`month` dopasowane do rejestru `archive_files`), nazwa pliku musi odpowiadać `server_path`, bajty są weryfikowane SHA-256 i rozmiarem **przed** zwróceniem iteratora, a rekordy daje parser zbioru `normalize_archive` (leniwie; błąd treści przy iteracji = `IMGWDataError`). Wynik jest identyczny z `normalize_archive(archive, data=<surowe bajty>)`. Wersja listy stacji → `IMGWValidationError` wskazujący `read_station_list(root, kind=…)`; wersje szeregu, katalogu i PMAXTP (brak `request.server_path` albo zbioru spoza rejestru archiwów) → `IMGWValidationError`; brak pliku lub sidecara → `IMGWStoreError`; niezgodna suma → `IMGWDataError`. Pliki IMGW pozostają na dysku bajt w bajt pod ścieżkami serwera.

**Rozstrzygnięcia implementacji (T15):** `StoreInfo.exists` = istnieje katalog `root`; `contracts` to zawsze obsługiwane przez bibliotekę wersje (`store`, `meta`, `series`, `plan`, `project`, `pmaxtp`); `supported=False` również przy braku/nieczytelnym znaczniku lub braku `created_by`. Ta sama ocena obowiązuje `iter_store` (zgłasza jako problem slotu `store`) i `current_version` (`IMGWStoreError`). `StoreEntry.version` = ścieżka pliku głównego (jak `VersionResult.path`), dla problemu — ścieżka wadliwego elementu; `slot` problemu = slot wersji albo ścieżka względna. Kody problemów: `missing_store`, `missing_marker`, `invalid_marker`, `unsupported_store`, `unknown_entry`, `symlink`, `missing_sidecar`, `missing_file`, `unreadable`, `invalid_json`, `unknown_schema` (schemat sidecara albo `extra.series_schema` szeregu spoza obsługiwanych, np. `imgw-series/2`), `invalid_meta` (brak/zły typ pola wymaganego, katalog ≠ `<label>_<sha8>`, `request.server_path` ≠ ścieżka), `size_mismatch`, `stale_incoming`. Skan nie haszuje plików (tylko rozmiar vs `size_bytes`); SHA sprawdzają `read_catalog`/`read_series_index` (plik główny vs sidecar) i `read_series` (Parquet vs spis). `Meta.extra` = obiekt `extra` sidecara; dodatkowe pola najwyższego poziomu są ignorowane. `current_version`: archiwum wg Last-Modified → `downloaded_at` → ścieżka, wersje pochodne wg `downloaded_at` → ścieżka; uszkodzona wersja w slocie → `IMGWDataError` (bez cichego wyboru starszej), brak slotu → `None`. `read_meta`: brak sidecara → `IMGWStoreError`, zła treść → `IMGWDataError`. `read_series` waliduje argumenty, spis i SHA przed zwróceniem iteratora; `variables` to niepusta kolekcja zmiennych deskryptora (pojedynczy tekst odrzucany), dni/miesiące uzupełnione przez builder wracają jako `missing`, a dla półrocza `extrema_dates` zawiera każdą żądaną zmienną.

> [ADR-002] Slot problemu = slot wersji albo `null`; brak wersji, sidecara lub pliku → kod `not_found`, nieobsługiwany root → `store_unavailable` (§13.5).

Eksport CSV: jeden wiersz nagłówka `date,year,<V> [<unit>],<V>_flag,…,attribution_source,attribution_processed`, UTF-8 bez BOM, przecinek, kropka dziesiętna, daty ISO, brak = pusta komórka + `missing`; jednostki w nagłówku i tekst formuł §5 dosłownie w **pierwszym wierszu danych** dwóch kolumn atrybucji (w następnych puste), żeby `csv.DictReader`, Excel i QGIS odczytały plik bez komentarzy. Dla miesięcznych/półrocznych dodatkowa kolumna `period` dla półrocza/roku oraz kolumny dat i liczby wystąpień ekstremów. `year` = rok z `date` albo `hydro_year`, `None` wybiera `series.json.year_type`; half_year/calendar = błąd walidacji. Eksport istniejącego, ale pustego szeregu odrzuca czytelnym błędem, by nie utracić formuł; zapis do unikalnego `.part`, `fsync`, `os.replace`, po anulowaniu plik docelowy pozostaje nietknięty. Każdy znany dzień z brakami pozostaje w wierszach.

**Rozstrzygnięcia implementacji (T17):** kolumna `period` oraz `<V>_start`/`<V>_end` (ISO, puste przy braku) i `<V>_occurrences` (liczba scalonych wierszy IMGW, pusta przy braku) występują tylko dla `half_year`; szereg miesięczny ma wyłącznie `date` (pierwszy dzień miesiąca) i `year`. Wartości w najkrótszym zapisie dziesiętnym bez wykładnika (`150.0`, `0.0`), flagi jako nazwy (`value`, `missing`, `no_phenomenon`, `accumulated`); powtórzone zmienne scalane, kolejność jak w `variables`. `attribution_source` = formuła źródła, `attribution_processed` = formuła przetworzenia. Separator wierszy CSV `\r\n` (RFC 4180). Ścieżka docelowa musi wskazywać plik w istniejącym katalogu (bez tworzenia katalogów) → inaczej `IMGWValidationError`; `.part` jest ukrytym plikiem obok celu (`.<nazwa>.<uuid>.part`, tworzonym wyłącznie przez `open("x")`, więc wynik ma uprawnienia wg umask jak pozostałe zapisy), usuwany przy każdym błędzie. Anulowanie (sprawdzane przed zapisem, co 256 wierszy i przed `os.replace`) zgłasza `IMGWStoreError` jak `write_archive`; `Progress(unit="row")` co 256 wierszy i na końcu, po sukcesie `Notice("info","license_terms")` z obiema formułami. Pusty szereg → `IMGWDataError`.

> [ADR-002] `path` eksportu jest opcjonalne (bez niego iterator linii, w CLI i REST strumień), dochodzą `start`/`end` oraz `root`/`dataset`; anulowanie zgłasza `IMGWCancelledError` (§13.8).

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

> [ADR-002] `method` ma wartość domyślną `"POT"` we wszystkich trzech funkcjach (§13.8).

PMAXTP endpoint `point/<P|A>/KS/{latitude:.4f}/{longitude:.4f}` zwraca `point.indX/indY`, `point.dataLon/dataLat` (środek komórki) i `data.ks/sg/rb`. **Autorytatywny klucz = indeksy z odpowiedzi**, bez zgadywania po krokach siatki; jeśli podano `ind_x/ind_y` i odpowiedź się różni, błąd bez zapisu. `sync_pmaxtp` pobiera odpowiedź jeden raz i zachowuje niezmienione `fetch_pmaxtp`; `cell.json` to kanoniczne `{"schema":"imgw-pmaxtp/1","method":"POT","ind_x":751,"ind_y":317,"center":{"lon":21.007098333333,"lat":52.234416666667},"data":{"ks":{"15":{"50":13.34}},"sg":{"15":{"50":14.1}},"rb":{"15":{"50":0.3}}}}`, bez żądanych współrzędnych (dwa punkty tej samej komórki → ten sam SHA). Puste `data`, brak indeksu albo `error` = wyjątek, a nie „pusta komórka”: `error` punktu poza siatką PMAXTP = `IMGWValidationError`, pozostałe = `IMGWDataError`. `check_pmaxtp` nigdy nie pobiera treści: bez indeksów plan `unverifiable` (endpoint nie ma HEAD gwarantującego sygnał), z indeksami informuje o lokalnym istnieniu i aktualności `unverifiable`; plan nie upoważnia do założenia, że dane są najnowsze. PMAXTP ma niezmienny sidecar `imgw-meta/1`, label downloaded, kopię przy zmianie treści; `read_pmaxtp` jest offline i nie wymaga pyarrow.

**Rozstrzygnięcia implementacji (T14):** odpowiedź z `error` oznaczającym punkt poza siatką PMAXTP (HTTP 200, puste `data`, tekst zawiera „poza obszarem”, np. „Brak pliku, pradopodobnie poza obszarem PL”, albo wcześniejsze „undefined: lat …”; dotyczy punktów w ramce 49–55° N, 14–24,5° E poza siatką, np. Kaliningrad, Lwów, Bałtyk) → `IMGWValidationError` w `sync_pmaxtp` i `fetch_pmaxtp`/`fetch_pmaxtp_async` (REST 400, CLI `Błąd: …` z kodem 1); `fetch_pmaxtp` bez `error`, ale z pustą tabelą `ks` → `IMGWDataError`; odpowiedź z innym `error`, bez `point.indX/indY`, bez `dataLon/dataLat` albo z pustym `data`/tabelą → `IMGWDataError`; indeksy podane przez użytkownika niezgodne z odpowiedzią → `IMGWValidationError`; w obu przypadkach nic nie jest zapisywane. Sidecar komórki: `dataset="pl.imgw.pmaxtp"`, `license.attribution` = obie formuły §4 połączone kropką, `request` = metoda, indeksy, żądany punkt i URL. `read_pmaxtp(version=…)` przyjmuje katalog wersji lub `cell.json` (względnie do root albo bezwzględnie), weryfikuje SHA z sidecarem; `PMaXTPResult.latitude/longitude` z odczytu to środek komórki. `check_pmaxtp` zwraca jedną `PlanAction("pmaxtp sync","unverifiable",…)` z informacją o lokalnej wersji. Brak zapisanej komórki przy odczycie → `IMGWStoreError`.

> [ADR-002] Kody: punkt poza siatką → `validation_error` (CLI 2, REST 400), brak komórki → `not_found` (§13.5).

**Surowa odpowiedź PMAXTP (3.0.0, addytywnie):** nowa wersja komórki zawiera obok `cell.json` niezmienione bajty odpowiedzi API (`response.json`, bajt w bajt, bez ponownego kodowania), publikowane w tym samym atomowym przemianowaniu katalogu wersji. Plik nie ma własnego sidecara (nie jest plikiem głównym, więc slot `pmaxtp:<metoda>:<indX>_<indY>`, `current_version` i tożsamość wersji = SHA `cell.json` pozostają bez zmian); opisuje go sidecar komórki w `extra.response={"name":"response.json","sha256":…,"size_bytes":…}`. Odpowiedź zawiera żądany punkt, więc drugi punkt tej samej komórki przy identycznym `cell.json` daje `unchanged` bez nowych plików, a `response.json` pozostaje odpowiedzią z pierwszego zapisu. `iter_store`/`current_version` dopuszczają `response.json` tylko w wersjach PMAXTP: opis bez pliku → `missing_file`, inny rozmiar → `size_mismatch`, plik bez opisu → `unknown_entry`, wadliwy opis → `invalid_meta`; wersje sprzed zmiany (bez opisu i pliku) są poprawne. `read_pmaxtp` czyta wyłącznie `cell.json`.

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
                cancel: Cancel | None = None) -> StoreHandle | StoreInfo | tuple[StoreEntry, ...] | StorePlan | SyncReport | SeriesReport | SeriesSelection | CatalogReport | PMaXTPStoreResult | PMaXTPResult | Project | ProjectReport | Path | Iterator[str]: ...
```

> [ADR-002] `CommandOption` i `DataCommand` mają nowe pola, a `run_command`/`check_command` zwracają `CommandResult` (§13.9).

Katalog danych obejmuje **każdą** komendę czytającą lub piszącą dane: `store init|info|scan|check|sync|catalog`, `series build|export|select`, `pmaxtp check|sync|read`, `project init|add|remove|set-store|download|check|status|verify`, istniejące `fetch hydro|meteo` (pozostałe live-only fetch/list/admin poza katalogiem działań magazynu). Opisy po polsku odpowiadają `--help`; nazwy opcji Python `snake_case`, CLI `--kebab-case`, root `--root`, dataset `--dataset`, roczniki `--years`, stacje `--stations`, zakres `--start/--end`, metoda `--method`, `--lat/--lon`, plan `--plan`. `validate_command` bez sieci odrzuca obce komendy/opcje i wartości; `format_command` stabilnie cytuje przez `shlex.quote`, nie tworzy ukrytych opcji, plan może być zapisany do wskazanej ścieżki poza magazynem. `check_command` dla `store sync` używa `check_store`, dla `series build` `check_series`, dla `store catalog` `check_catalog`, dla `project download` `check_project`, dla `pmaxtp sync` `check_pmaxtp`; dla eksportu i małych zapisów manifestu daje `StorePlan.actions` z przewidywanymi ścieżkami i wynikami walidacji, bez mutacji lub GET treści. Operacje czysto odczytowe również mają reprezentację `PlanAction`, więc `run_command`/`check_command` przyjmują identyczne opcje; nie są potrzebne osobne bliźniaki dla komend read-only. Jeden mechanizm dispatch publicznych API, CLI **nigdy** nie implementuje własnego GET. Zewnętrzny odbiorca Retman weryfikuje np. `dataset`, `stations`, `variables`, zakres i `format="csv"` przez katalog/walidator; nie importujemy Retmana. `on_progress` w długich operacjach ma jednostkę, bieżącą/łączną liczbę, status i tekst; `on_notice` ma level/code/tekst PL identyczny jak CLI; `cancel` sprawdza się między plikami/stacjami, daje raport częściowy i żadnego częściowego katalogu wersji.

> [ADR-002] Katalog obejmuje każdą operację, także live (35 komend, §13.3); nazwy i flagi: §13.2 (`--latitude`/`--longitude` z aliasami `--lat`/`--lon`, `--datasets`, `--years`, `--series/--no-series`).

**Rozstrzygnięcia implementacji (T18):** `imgwtools.commands`. Flaga `--check` CLI to `check_command` danej komendy, nie opcja katalogu. Opcje `list` w CLI są rozdzielane przecinkami (Python przyjmuje też sekwencję lub pojedynczą liczbę), roczniki przyjmują zakresy `a-b`; `validate_command` zwraca znormalizowany słownik w kolejności katalogu (`Path`, krotki, roczniki/miesiące posortowane, stacje/zmienne bez duplikatów) i pomija `None` oraz fałszywe flagi `bool`, dlatego `format_command` → ponowne sparsowanie → `validate_command` daje identyczne opcje. Brak typu float w `CommandOption`: `lat`/`lon` mają typ `str` i normalizują się do `float` w granicach Polski. `store check|sync` mają opcję `dataset` typu `list` (→ `datasets=`); `store check --plan` zapisuje plan wyłącznie poza root. `project add --options` to obiekt JSON opcji komendy zadania, walidowany tą samą funkcją bez `root` (magazyn wynika ze `store_dir`); dozwolone komendy zadań: katalog bez `store init` i `project *`. `fetch hydro|meteo` zachowują istniejące opcje `--interval/--year/--month/--param|--subtype/--output` (domyślne jak w CLI), pobierają przez publiczne `download_*`, zapisują `<output>/<server_path>` przez `.part`, nieudany plik = `Notice("error","download_failed")` bez przerywania, wynik = katalog wyjściowy. `check_command` dla komend bez własnego `check_*`: `store init` wg `store_info` (`current`/`missing`/`check_failed`), odczyty (`store info|scan`, `project status|verify`) `current`, `series select` `current`/`missing`/`check_failed`, `series export` `missing`/`newer` (nadpisanie)/`check_failed` po walidacji spisu, `pmaxtp read` `current`/`missing`, zapisy manifestu `project init` `missing`/`current`, `project add|remove|set-store` `newer`/`check_failed` (brak manifestu), `fetch *` jedna akcja na plik (`missing`/`unverifiable` gdy plik lokalny istnieje); `store sync --plan` zwraca wczytany plan po sprawdzeniu root. `StorePlan.root` takich planów = root magazynu, katalog projektu, katalog wyjściowy albo magazyn zawierający wersję eksportu. `series select` zwraca `SeriesSelection.version` = `series.json` bieżącej wersji, domyślnie wszystkie zmienne zbioru i wszystkie lata okresów szeregu wg `year_type` (domyślnie z `series.json`); stacja lub rok spoza szeregu → `IMGWValidationError`.

> [ADR-002] Typy opcji `float`, `date`, `object`; `store check|sync` mają `datasets`; `fetch hydro|meteo` zastępuje `datasets download` (`--dataset`, `--years`, `--months`, `--params`, `--output`) bez domyślnego zbioru.

**Rozstrzygnięcia implementacji (T20):** grupy `imgw store|series|pmaxtp|project` oraz `imgw fetch hydro|meteo` są generowane z `data_commands()` przez jeden adapter `imgwtools.cli._dispatch`: help komendy = `DataCommand.description`, help opcji = `CommandOption.help`, flagi = `CommandOption.flag` (dla `fetch` dodatkowo dotychczasowe skróty `-i/-y/-m/-p|-s/-o`), opcje wymagane w osobnym panelu help. CLI przekazuje do `run_command` (z `--check` do `check_command`) surowy tekst wyłącznie podanych opcji, więc walidacja, wartości domyślne i błędy po polsku pochodzą z katalogu (brak walidacji typów po stronie click). Wynik na stdout: `Path` jako sama ścieżka, pozostałe struktury jako JSON (pola dataclass, `Path` → tekst, daty ISO UTC `Z`); `Progress` (`[bieżący/łączny] komunikat`) i `Notice` (`Informacja|Ostrzeżenie|Błąd: tekst`, bez zawijania) na stderr. Jednakowy `Notice` (ten sam `code` i `text`) CLI wypisuje raz na uruchomienie komendy (np. `license_terms` przy setkach archiwów); hooki Pythona i REST dostają każdy komunikat. `fetch hydro|meteo` dopisują na stderr podsumowanie `Pobrano: N plików`/`Niepowodzenia: M`, z `--check` — wcale, więc stdout zawiera wyłącznie plan JSON. Kody wyjścia: 0 sukces, 1 `IMGWError`/`OSError` (`Błąd: …` na stderr) albo wypisany wynik z nieudaną pozycją na dowolnym poziomie — `status` `failed`/`stale_plan` wyniku, jego `items`/`series`/`files` lub wartości `tasks` (`SyncReport`, `SeriesReport`, `CatalogReport`, `PMaXTPStoreResult`, `ProjectReport`) albo `Progress` ze statusem `failed` (pliki `fetch hydro|meteo`); JSON wyniku jest wtedy wypisany na stdout, a na stderr `Błąd: część pozycji zakończyła się niepowodzeniem; szczegóły w wyniku`. 130 anulowanie (ma pierwszeństwo przed 1). Pierwsze Ctrl+C ustawia `cancel` (operacja kończy bieżący plik/stację i zwraca raport częściowy, który jest wypisywany), drugie przerywa natychmiast; poprzedni handler SIGINT jest przywracany.

> [ADR-002] stdout = koperta `imgw-result/1`; błąd = JSON na stderr; kody wyjścia z §13.5 zamiast 0/1/130; `--check` tylko przy komendach z bliźniakiem, `--schema` przy każdej (§13.10).

**Komenda `store read` (3.0.0):** katalog obejmuje także `store read --version … [--format csv|jsonl] [--path …]` → `read_archive`. Bez `--path` `run_command` zwraca iterator gotowych linii tekstu (z terminatorami), które CLI wypisuje strumieniowo na stdout (zamknięty potok, np. `| head`, kończy cicho); z `--path` zapis przez ukryty unikalny `.part` obok celu, `fsync`, `os.replace` (katalog docelowy musi istnieć, plik poza magazynem — inaczej `IMGWValidationError`), wynik = ścieżka. CSV (przecinek, wiersze CRLF): nagłówek `station_code,dataset,date,hydro_year,period`, dalej `<V> [<jednostka>],<V>_flag` dla każdej zmiennej zbioru (półroczne dodatkowo `<V>_start,<V>_end,<V>_occurrences`) i kolumny atrybutów jakościowych zbioru (meteo `precip_type` itd.); zmienna lub atrybut nieobecne w rekordzie = puste komórki. JSONL: jeden obiekt na rekord z polami `NormalizedRecord` (`measurements` jako `{"value","flag"}`, `extrema_dates` jako pary ISO, `extrema_occurrences` jako liczby). `--check` weryfikuje wersję (sidecar, SHA) bez parsowania i zwraca `PlanAction("store read", current|missing|newer|check_failed, …)`.

> [ADR-002] Komenda nazywa się `store export` i wywołuje `export_archive` (§13.3, §13.8).

| CLI | Publiczne API | Uwagi |
|---|---|---|
| `imgw store init --root …` / `info --root …` / `scan --root …` | `init_store` / `store_info` / `iter_store` | `info`,`scan` offline |
| `imgw store check --root … --dataset … --years 2023-2025 --plan plan.json` | `check_store` + `StorePlan.to_json` | HEAD i listing; plan poza magazynem |
| `imgw store sync --root … --plan plan.json [--no-series]` | `sync_store` | bez planu `--dataset`, `--years` |
| `imgw store catalog --root … [--user-locations …]` | `build_catalog` | `--check` → `check_catalog` |
| `imgw store read --version … [--format csv\|jsonl] [--path …]` | `read_archive` | offline, SHA-256; bez `--path` na stdout; listy stacji czyta `read_station_list` |
| `imgw series build --root … --dataset …` / `export --version … --station … --path … --variables …` | `build_series` / `export_series` | `--check` analogicznie |
| `imgw series select --root … --dataset … --stations …` | `current_version` + walidowany wybór | komenda bez zapisu; wejście projektu |
| `imgw pmaxtp check|sync --root … --method POT --lat … --lon …` / `read --root … --method POT --ind-x … --ind-y …` | `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp` | nie mylić z `imgw fetch pmaxtp` live |
| `imgw project init|add|remove|set-store|download|check|status|verify …` | funkcje `project.py` | brak dotykania manifestu Kartografa |
| istniejące `imgw fetch hydro|meteo` | `archive_files` + publiczne `download_*` | `--output` odzwierciedla `server_path`, `.part`; po pobraniu co najmniej jednego pliku komunikat `license_terms`; inne istniejące CLI zostają |

> [ADR-002] Tabelę zastępuje §13.3.

REST: istniejące `/api/v1/hydro|meteo|download|pmaxtp` URL-e zachowują odpowiedzi, `/api/v1/hydro/data` DB-only znika (breaking). Dodajemy `GET /api/v1/store/info`, `GET /api/v1/store/entries`, `POST /api/v1/store/check`, `POST /api/v1/store/sync`, `POST /api/v1/store/catalog`, `POST /api/v1/series/build`, `GET /api/v1/series/index`, `GET /api/v1/series/{station}`, `POST /api/v1/series/export`, `POST /api/v1/pmaxtp/store/sync`. Odczyt i zapis bazują na publicznych funkcjach. Wszystkie te trasy korzystają tylko z **serwerowego, absolutnego** `IMGW_STORE_ROOT`; brak ustawienia → 503 dla tras store, generator URL i live pozostają dostępne. Klient nie podaje root ani absolutnej ścieżki; `version` w query/body jest ścieżką względną do root pod `versions/`, walidowaną przed odczytem. Żaden plik magazynu nie jest zapisywany domyślnie przez REST.

> [ADR-002] Trasy: §13.3 i §13.10 (`/api/v1/<grupa>/<komenda>`); trasy `/api/v1/hydro|meteo|download|pmaxtp/*` usunięto.

`GET info` = pola `StoreInfo`; `GET entries?kind=…` = lista `StoreEntry`, także `problem`; `GET series/index?version=…` = `SeriesIndex`; `GET series/{station}?version=…&variables=Q,H&start=…&end=…` = lista rekordów wartości/flag; identyczne zasady jak Python API. `POST store/check` i `POST store/sync` przyjmują `{"datasets":["pl.imgw.hydro_daily"],"years":[2024],"months":null}`; sync może zamiast selektorów przyjąć `{"plan":<obiekt imgw-plan/1>,"series":true}`. `POST store/catalog` przyjmuje opcjonalnie wyłącznie nazwę **wcześniej umieszczonego na serwerze** pliku współrzędnych w skonfigurowanym katalogu, nie arbitralną ścieżkę klienta; `POST series/build` przyjmuje `{"dataset":"pl.imgw.hydro_daily"}`; `POST pmaxtp/store/sync` przyjmuje `{"method":"POT","latitude":52.23,"longitude":21.01}`. `POST series/export` przyjmuje `{"version":"series/versions/…/series.json","station":"149190310","variables":["Q"],"year_type":"hydrological"}` i zwraca `text/csv; charset=utf-8` jako załącznik z pliku tymczasowego poza magazynem, usuwanego po odpowiedzi; nie akceptuje ścieżki wyjścia od klienta.

> [ADR-002] Odpowiedzi to koperta `imgw-result/1`; `store check` → `GET`, `series/{station}` → `GET /series/read`, `series/index` → `GET /series/summary`, `series/export` → `GET` (strumień, bez tokenu), `pmaxtp/store/sync` → `POST /pmaxtp/sync`; `years` przyjmuje zakresy.

Katalog dopuszczonych CSV użytkownika dla REST określa wyłącznie serwerowe absolutne `IMGW_USER_LOCATIONS_DIR` (domyślnie brak = bez tej opcji); przyjmowany basename bez separatorów i bez symlinków. Python API/CLI mogą wskazać jawny plik przez `user_locations`.

Wywołania **piszące** wymagają jednocześnie `IMGW_STORE_WRITES_ENABLED=true` (domyślnie false), skonfigurowanego niepustego `IMGW_STORE_WRITE_TOKEN` po stronie serwera oraz nagłówka `X-API-Key` porównanego w stałym czasie; brak któregoś → 403, brak ważnego root → 503. Nie korzystamy z dotąd niewdrożonego middleware kluczy administracyjnych. Serwer publiczny dodatkowo wymaga HTTPS i limitów żądań reverse proxy. `POST /store/check` sam nie pisze do root i jest dostępny przy wyłączonych zapisach, ale wymaga root; `series/export` zapisuje tymczasowo poza root, więc traktujemy go jako zapis dla kontroli uprawnień. Operacja POST zwraca pełny raport po zakończeniu, **nigdy** fikcyjne „202 ukończone”; długie zadania konsumenci uruchamiają przez Python API w swoim workerze. Błędy: walidacja 400/422, brak wersji 404, nieaktualny plan 409, sieć źródła 502, brak pyarrow 503; JSON `{"code":"…","detail":"… po polsku"}`.

> [ADR-002] Błędy: `application/problem+json` ze statusami z §13.5 (walidacja zawsze 400); sync z pozycją `stale_plan` zwraca 200 i kopertę `partial`.

**Rozstrzygnięcia implementacji (T21):** `imgwtools.api.routes.store`; ustawienia `Settings.store_root`, `store_writes_enabled`, `store_write_token` (`SecretStr`), `user_locations_dir` (env `IMGW_STORE_ROOT`, `IMGW_STORE_WRITES_ENABLED`, `IMGW_STORE_WRITE_TOKEN`, `IMGW_USER_LOCATIONS_DIR`). Operacje magazynu idą przez `run_command` (te same opcje i walidacja co CLI), odczyt szeregu przez `read_series_index`/`read_series`. Wszystkie ścieżki w odpowiedziach są względne do root (POSIX), także w tekstach dowolnych (`detail` błędu, `error` pozycji, `problems`, `problem`): przedrostek bezwzględnego `IMGW_STORE_ROOT`, `IMGW_USER_LOCATIONS_DIR` i `IMGW_DATA_DIR` (względny katalog w postaci rozwiązanej, najdłuższy przedrostek najpierw) jest z nich usuwany, a sam katalog zastępuje `.`; `StoreInfo.root` i `root` dokumentu planu z `POST store/check` mają wartość `"."`, a sync przyjmuje plan z `root` równym `"."` (lub absolutnemu root serwera), inaczej 400. Ciała żądań odrzucają nieznane pola (422), więc klient nie poda `root` ani ścieżki wyjścia. `version` musi leżeć pod `series/versions/`, bez `..`, `\`, segmentów pustych i dowiązań po drodze; nieistniejąca → 404. `GET store/info` i `GET store/entries` są diagnostyczne: przy skonfigurowanym, lecz nieobsługiwanym root zwracają 200 (`supported=false`, problemy), pozostałe trasy 503 `store_unavailable`. Kontrola zapisu poprzedza kontrolę root (nieuprawniony klient dostaje 403, nie 503). Kody: `IMGWValidationError` 400 `validation_error`, `IMGWStoreError` 404 `not_found`, `IMGWStoreConflictError`/`IMGWPlanStaleError` 409, `IMGWConnectionError` 502 `source_unavailable`, `IMGWStoreDependencyError` 503 `missing_dependency`, `IMGWDataError` 500 `data_error`. Sync, w którym choć jedna pozycja skończyła się `stale_plan`, zwraca 409 `stale_plan` z pełnym raportem w polu `report` (pozostałe pozycje mogły zostać zapisane). `POST pmaxtp/store/sync` przyjmuje dodatkowo opcjonalne `ind_x`/`ind_y` jak CLI.

> [ADR-002] Kody `store_not_configured`, `store_root_invalid`, `user_locations_invalid` → `store_unavailable`, a `writes_disabled`, `write_token_missing`, `invalid_api_key` → `forbidden` (oba z `details.reason`); `version` może wskazywać `archives|series|pmaxtp/versions/` właściwe dla komendy.

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
def set_project_store(project_dir: PathArg, /, *, store_dir: PathArg,
                      on_notice: NoticeHook | None = None) -> Project: ...
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

> [ADR-002] `ProjectFile.station` → `station_code` (także w `imgw-project.json`, §11.6).

`imgw-project.json` ma `schema`, `store_dir`, `tasks[]`: `name` 1–64 `[a-z0-9][a-z0-9_-]*` unikalny; `command` z katalogu, przede wszystkim `series select`; `options` z jawnym `dataset`, `stations` (lista 9-cyfrowych kodów), `variables`, `years`, `year_type`, opcjonalnie `geometry` (ścieżka zapisanego wyboru); `geometry_sha256` przy wyborze z obszaru; `pinned_at`, `imgwtools_version`, `files[]` z rolą `series|station_series|catalog|input`, `path` wersji względną do `store_dir`, pełnym `sha256`, opcjonalnym `station`. Żadnych sygnałów sieci ani danych źródłowych w manifeście. `store_dir` podane względnie zapisuje się względnie do projektu, bezwzględne zostaje bezwzględne; istniejący root ma znacznik IMGW, a `set_project_store` weryfikuje cel i zgodność istniejących pinów bez cichego przepięcia. Geometrię SHA haszuje się przed zapisaniem wyboru obszarem, wybór stacji jest materializowany raz z konkretnej wersji katalogu; brak stacji bez położenia może być wybrany po kodzie. `open_project` ściśle waliduje klucze, typy, opcje i ścieżki bez `..`/symlinków/ucieczki z root (różnie niż tolerancyjny `read_meta`), bez połączenia z siecią. W manifeście po pierwszym przypięciu `pinned_at` i `imgwtools_version` nie są null; `files` nie zmieniają się przy odtwarzaniu tych samych SHA. `download_project` domyślnie nie przepina istniejących zadań; brakujące wersje odtwarza wyłącznie przy identycznym pełnym SHA, w przeciwnym razie błąd pozycji i nie zmienia pinów. `update="upgrade"` wymaga świeżego check/plan i przepina **całe zadanie** tylko po pełnym sukcesie; brak dostępu do starych bajtów nie usprawiedliwia zastąpienia. `check_project` bez zapisu/GET treści, `status` sprawdza istnienie/rozmiar offline, `verify` oblicza pełne SHA i zgodność sidecarów offline. Projekt z dwoma manifestami: IMGWTools dotyka jedynie `imgw-project.json`.

Wyjątek od tolerancyjnego czytania plików `/1`: projekt odrzuca nieznane klucze strukturalne w każdym obiekcie (IMGW-14). Opcjonalne przyszłe pola bez zmiany major wolno wprowadzić **tylko** pod top-level `extensions: {…}`; nieznane wpisy w tej mapie są ignorowane semantycznie, ale zachowywane przy ponownym zapisie. Nowy klucz poza mapą wymaga `imgw-project/2`; pełna walidacja ścieżek i `options` obowiązuje zawsze.

Manifest zapisuje się jako kanoniczny JSON z LF przez tymczasowy plik+`fsync`+`os.replace`, pod krótką blokadą `.imgw-project.lock` utworzoną wyłącznym `mkdir` na czas odczyt–scalenie per zadanie–zapis; nie trzymamy locka podczas sieci/budowy Parquet, zastanej blokady nie przejmujemy automatycznie. Dwa procesy aktualizujące różne zadania kończą z obiema zmianami; konflikt modyfikacji tego samego zadania = jawny błąd.

**Rozstrzygnięcia implementacji (T19):** `imgwtools.project`. `Project.path` = bezwzględny katalog projektu, `Project.store_dir` = znormalizowana ścieżka bezwzględna; względny `store_dir` (argument i manifest) liczy się wobec katalogu projektu. Istniejący `store_dir` musi być obsługiwanym magazynem IMGW albo pustym katalogiem, a katalog projektu nie może leżeć w magazynie. `init_project` na istniejącym manifeście z tym samym magazynem zwraca go bez zapisu (inny magazyn → `IMGWProjectError`, zmiana przez `set_project_store`). `ProjectTask.options` = postać manifestu: listy JSON i ścieżki względne POSIX (`version` wobec magazynu, `geometry`/`path`/`output`/`plan`/`user_locations` wobec katalogu projektu; bez `..`, `.`, `\` i dowiązań; domyślne `output` komend `fetch` także wobec projektu). `series select` zapisuje jawnie `dataset, stations, variables, years, year_type`: `years` jest wymagane przy dodaniu (`validate_command("project add")`), brakujące `variables` = wszystkie zmienne zbioru, `year_type` = numeracja ZIP zbioru. `geometry` (plik w katalogu projektu, GeoJSON Polygon/MultiPolygon/Feature/FeatureCollection w WGS84; dozwolony tylko dla `series select`, wtedy `stations` opcjonalne) wybiera stacje rodziny zbioru (hydro/meteo) z położeniem w obszarze z bieżącej wersji `stations.geojson`; wynik sumuje się z kodami podanymi jawnie w posortowaną listę, `geometry_sha256 = {<options.geometry>: <SHA-256 bajtów użytych do wyboru>}`, a wersja katalogu zostaje od razu przypięta jako plik `catalog` (zadanie pozostaje nieprzypięte: `pinned_at=null`). Pin wskazuje zawsze plik wersji `<archives|series|stations|pmaxtp>/versions/…`, `station` jest wymagane dla `station_series`, `pinned_at` i `imgwtools_version` są oba null albo oba ustawione; JSON z powtórzonym kluczem lub NaN jest odrzucany. Blokada czeka do `LOCK_TIMEOUT_S = 5` s (ponawianie co 50 ms), potem `IMGWProjectError` z właścicielem z pliku `owner` (host, pid, czas). Scalanie: pod blokadą zadanie w manifeście porównuje się ze stanem z chwili odczytu — identyczne z nowym = bez zapisu, inne niż przy odczycie albo usunięte = `failed` z kodem `project_conflict`. `download_project` dla zadania nieprzypiętego lub `update="upgrade"`: `series select` synchronizuje roczniki archiwów pokrywające wybrane lata (przy innej numeracji ZIP także rocznik sąsiedni) przez `sync_store` — z `plan` wyłącznie pozycje tych archiwów (brak pozycji = błąd zadania, nieaktualne = `stale_plan`) — potem `build_series` zbioru i walidowany wybór; pozostałe komendy przez `run_command` z `root=store_dir`, przypinając wersje wskazane w wyniku (`SyncReport` → `input` i szeregi, `SeriesReport` → szereg ze wszystkimi stacjami, `CatalogReport` → `catalog`, `PMaXTPStoreResult` → `input`; wyniki bez wersji magazynu nie mają plików, a `plan` ich nie dotyczy). Piny `series select`: `series` (`series.json`), `station_series` wybranych stacji, `input` = `extra.source_files` sidecara szeregu oraz zachowany `catalog` wyboru obszarem. Pierwsze przypięcie daje `current`, upgrade z innymi plikami `upgraded`, z identycznymi `current` bez zapisu; `pinned_at` w UTC z dokładnością do sekundy, `imgwtools_version` = wersja pakietu. Tryb `pinned` dla zadania przypiętego nie łączy się z siecią, gdy wszystkie pliki są obecne; brakujące archiwum pobiera ponownie i uznaje za odtworzone wyłącznie przy identycznym SHA pod przypiętą ścieżką, brakujący szereg buduje wyłącznie, gdy bieżące wersje archiwów zbioru są dokładnie przypiętymi wejściami; wersji katalogu i komórek PMAXTP (etykieta z dnia pobrania) nie odtwarza. `set_project_store` przed zapisem oblicza pełne SHA każdego przypiętego pliku (także `catalog` zadań nieprzypiętych) w nowym magazynie; niepusty magazyn bez identycznych pinów jest odrzucany bez zmiany manifestu. Wyjątek: nowy pusty magazyn (brak katalogu, pusty katalog albo magazyn bez żadnego wpisu `iter_store`) jest przyjmowany z ostrzeżeniem `on_notice` `pins_not_in_store` (liczba brakujących plików, zadania z nieodtwarzalnymi pinami `catalog`/PMAXTP), a następny `download_project` w trybie `pinned` odtwarza piny według zasad powyżej — archiwa tylko z identycznym SHA, szeregi tylko z dokładnie przypiętych wejść, inaczej jawny błąd zadania (`failed`, piny bez zmian). `ProjectReport.files`: `slot` = `<zadanie>:<ścieżka względem magazynu>` (błąd operacji: `<zadanie>:<slot operacji>`, błąd całego zadania: `<zadanie>:imgw-project.json`), `unchanged` = plik zgodny, `created` = utworzony lub odtworzony, `failed`/`stale_plan`/`cancelled` z `error`. `get_project_status` sprawdza istnienie oraz rozmiar i SHA zapisane w sidecarze (bez haszowania; Parquet stacji — istnienie), `verify_project` dodatkowo pełne SHA i spis `series.json` dla plików stacji; status zadania `changed` ma pierwszeństwo przed `missing`, nieprzypięte = `unpinned`. `check_project`: `StorePlan.root` = magazyn, `series select` → `check_store` roczników zadania, pozostałe → `check_command`; na zadanie jedna akcja `project download`: `check_failed` (błąd sprawdzenia albo zmieniony pin), `missing` (nieprzypięte, brak pinów albo magazynu), `newer` (nowsze/brakujące dane — zmienia je dopiero upgrade), `unverifiable`, `current`. Kody `on_notice`: `task_failed`, `project_conflict`, `pin_mismatch`; `Progress(unit="task")` w download/check, `unit="file"` w verify.

> [ADR-002] `ProjectReport.files[].slot` według §13.7, nazwa zadania w polu `task`; błąd całego zadania ma `slot=null`; kody błędów projektu: §13.5.

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

> [ADR-002] Pole `files[].station` nazywa się `station_code`.

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
            "station_code": {"type": "string", "pattern": "^[0-9]{9}$"}
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

> [ADR-002] `IMGWPlanStaleError` usunięto, doszedł `IMGWCancelledError`; kody błędów, kody wyjścia CLI i statusy HTTP: §13.5.

Fixtury: małe ZIP-y z każdej odmiany (`codz_<y>_<m>` 2022, roczny 2023 UTF-8 BOM/średnik, 2024 CP1250/linia cytowana, `mies`, `polr_H/Q/T`, meteo `1995_k/o` roczne + `2001_01_k/o` miesięczne), zmienne status 8/9, opad zbiorczy, puste miesiące, 29 II, granica XI, H obecne przy braku Q, brak punktu, 0,0 i poza krajem. Nagrania `respx` obejmują listing i HEAD/GET, ETag i Last-Modified, brak nagłówków, nieistniejący rocznik, zmieniony HEAD po planie, awarię sieci, indeksy komórki PMAXTP i dwa punkty w jednej komórce. Materiał do publikacji fixtur ma być licencyjnie odpowiedni (krótkie dane syntetyczne i zanonimizowane nagłówki), nie całe rzeczywiste roczniki. `imgwtools.testing.build_fixture_store(root, *, variant: Literal["complete","corrupt","unknown_schema"]="complete") -> StoreHandle` buduje **publicznym writerem** katalog bez internetu, z zapisanym starym/nowszym/relabelowanym ZIP, bieżącą i nieaktualną serią oraz katalogiem z `geometry=null`; warianty dodają uszkodzony sidecar i nieznaną wersję do testu odczytu. Pakiet udostępnia fixtury przez `importlib.resources`; testy kontraktu konsumenta nie kopiują prywatnej implementacji parserów. Świadome testy `live` są osobne, nigdy w domyślnej bramce offline.

Realizacja `imgwtools.testing`: fixtury leżą w pakiecie pod `imgwtools/_data/fixtures/` (kopia 1:1 `tests/fixtures/store/`, pilnowana testem), dostępne publicznie przez `fixture_files() -> Traversable`. `build_fixture_store` wymaga pustego/nieistniejącego `root` (inaczej `IMGWStoreError`; nieznany wariant `IMGWValidationError`) i wymaga `pyarrow`. Podczas budowy synchroniczny `httpx.HTTPTransport` jest podmieniany (pod blokadą procesu) na odtwarzanie nagrań `recordings.json` + `builder_recordings.json` w ustalonej kolejności; nienagrane żądanie = błąd połączenia, niewykorzystane nagranie = `IMGWDataError`. `complete`: `codz_2024.zip` w wersjach `2026-10-17` (v1) → `2026-10-18` (te same bajty, `relabeled`) → `2026-10-19` (nowe bajty, bieżąca); dwie serie `hydro_daily` (starsza z v1, bieżąca z v3); seria `meteo_precip_daily` z `2001_01_o` nieaktualna po dopisaniu `1995_o`; obie listy stacji i katalog z `geometry=null`, budowany bez lokalnego pliku statycznego z `settings.data_dir` (wpis `static` w sidecarze z `available: false`), więc wynik nie zależy od danych referencyjnych pobranych przez użytkownika. `corrupt` obcina sidecar wersji v1; `unknown_schema` dodaje `series/versions/hydro_daily/2026-10-20_<sha8>/` z `imgw-meta/2` i `imgw-series/2`. Przy zamrożonym zegarze dwie budowy dają identyczne bajty wszystkich plików.

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

## 13. Spójność interfejsów (ADR-002)

Sekcja normatywna od 2026-10-18 (`docs/DECISIONS.md` ADR-002) dla Pythona, CLI, REST i web; ma pierwszeństwo przed §1–§12, a zastąpione tam miejsca oznacza nota `[ADR-002]`. Całość wchodzi w 3.0.0 bez aliasów i shimów. Wartości w przykładach JSON są umowne.

### 13.1 Zasady wspólne

1. Każda operacja jest komendą `data_commands()` (§13.3) i wywołuje dokładnie jedną funkcję z `imgwtools.__all__`. CLI `imgw <grupa> <nazwa>` i REST `/api/v1/<grupa>/<nazwa>` powstają z katalogu (§13.10); web wywołuje wyłącznie funkcje publiczne. Poza katalogiem zostają: `imgw version`, `imgw server`, `imgw admin …`, `GET /health`, `GET /api/v1` i strony HTML.
2. Nazwa opcji = nazwa parametru funkcji = pole JSON (query lub ciało REST, wyniki); flaga CLI = `--` + nazwa z `_` zamienionym na `-`. Dispatcher wiąże opcje z parametrami po nazwie (`inspect.signature`), parametry tylko pozycyjne przekazuje pozycyjnie. Wspólne opcje koperty `limit`/`offset` (§13.6) obsługuje `run_command`, nie funkcja.
3. Wartości normalizuje wyłącznie `validate_command` (dla CLI, REST, projektów i `run_command`): alias zbioru → klucz, `years` → posortowane unikalne liczby, listy → krotki, tekst liczby → `int`/`float`, data ISO → `date`, ścieżki → bezwzględne (poza REST). Funkcje przyjmują te same postaci wejścia (`YearsArg`, `MonthsArg`, aliasy zbiorów), więc wywołanie bezpośrednie i przez katalog daje ten sam wynik. Każdą regułę wartości sprawdza jedno miejsce, które tworzy też komunikat: granice Polski i siatkę PMAXTP — walidator biblioteki (ten sam `detail` w Pythonie, CLI i REST), pozostałe reguły — `validate_command`; `minimum`, `maximum` i `pattern` w `CommandOption` tylko publikują te reguły w schemacie.
4. JSON (CLI, REST, `CommandResult.to_json`): daty `YYYY-MM-DD`, chwile ISO 8601 UTC z `Z`, krotki → tablice, dataclass i modele pydantic → obiekty pól, ścieżka wewnątrz magazynu → POSIX względna do root, ścieżka poza magazynem → bezwzględna (CLI i Python; REST takich nie zwraca), sam root → bezwzględny w CLI, `"."` w REST.
5. Identyfikatory, wartości wyliczeń i kody są angielskie; tekst dla człowieka (help, `title`, `detail`, `Notice.text`) jest polski i pochodzi z jednego źródła: katalogu, rejestru błędów albo wyjątku.

### 13.2 Słownik opcji

Każda opcja ma w całym katalogu jedno znaczenie i jeden typ. Kolumna REST: „parametr” = query w GET albo pole ciała w POST; „serwer” = wartość z konfiguracji serwera, której klient nie podaje; „lokalna” = brak w REST. Listy w CLI i w query: wartości po przecinku albo powtórzony parametr; w ciele JSON tablica (tekst z przecinkami też jest przyjmowany). Aliasy krótkie tworzą listę zamkniętą i każdy ma jedno znaczenie w całym CLI; `-m` nigdy nie oznacza metody.

| Opcja | Typ (elementy) | Ograniczenia i normalizacja | CLI | REST | Znaczenie |
|---|---|---|---|---|---|
| `root` | `path` | absolutyzowana; CLI domyślnie `$IMGW_STORE_ROOT` | `--root`, `-r` | serwer (`IMGW_STORE_ROOT`) | katalog magazynu |
| `project_dir` | `path` | — | `--project-dir` | lokalna | katalog z `imgw-project.json` |
| `store_dir` | `path` | względna liczona wobec katalogu projektu | `--store-dir` | lokalna | magazyn projektu |
| `version` | `path` | bezwzględna albo względna do `root` (bez `root` — do CWD); katalog wersji, plik główny lub sidecar | `--version` | parametr; wyłącznie względna do root, pod `archives\|series\|pmaxtp/versions/` właściwym dla komendy | wskazana wersja |
| `dataset` | `choice` | klucz, slug albo alias legacy (§13.4) → klucz; dozwolone zbiory w §13.3 | `--dataset`, `-d` | parametr | jeden zbiór |
| `datasets` | `list` (`choice`) | jak `dataset`, bez powtórzeń | `--datasets`, `-d` | parametr | wiele zbiorów |
| `kind` | `choice` | `hydro\|meteo`; w `store scan` `archive\|series\|catalog\|pmaxtp\|problem`; brak = wszystkie | `--kind`, `-k` | parametr | rodzaj obiektu |
| `query` | `str` | co najmniej 1 znak po przycięciu | `--query`, `-q` | parametr | szukany tekst |
| `source` | `choice` | `live\|store`, domyślnie `live` | `--source` | parametr | źródło listy stacji |
| `station` | `str` | `^[0-9]{9}$`; w `current synop` `^[0-9]{5}$` | `--station`, `-s` | parametr | jedna stacja |
| `stations` | `list` (`str`) | elementy `^[0-9]{9}$`, bez powtórzeń | `--stations`, `-s` | parametr | wiele stacji |
| `station_name` | `str` | podciąg nazwy, bez wielkości liter | `--station-name` | parametr | nazwa stacji synop |
| `variables` | `list` (`str`) | zmienne deskryptora zbioru; brak = wszystkie | `--variables` | parametr | zmienne |
| `years` | `list` (`year`) | liczba 1–9999 albo zakres `a-b`; rozwinięte, posortowane, bez powtórzeń | `--years`, `-y` | parametr | roczniki |
| `months` | `list` (`int`) | 1–12 | `--months`, `-m` | parametr | miesiące |
| `params` | `list` (`choice`) | `H\|Q\|T`, wyłącznie dla `pl.imgw.hydro_semiannual` | `--params` | parametr | parametry półroczne |
| `year_type` | `choice` | `hydrological\|calendar`; brak = według `series.json` | `--year-type` | parametr | rodzaj roku |
| `start`, `end` | `date` | ISO, włącznie, `start ≤ end`; miesiąc i półrocze według daty początku okresu | `--start`, `--end` | parametr | zakres dat rekordów |
| `plan` | `path` | `store check`, `project check`: plik do zapisania poza magazynem; `store sync`, `project download`: plik do odczytu (w Pythonie także `StorePlan`) | `--plan` | `store sync`: obiekt `imgw-plan/1` w ciele; pozostałe: lokalna | plan `imgw-plan/1` |
| `series` | `bool` | domyślnie `true` | `--series/--no-series` | parametr | budowa szeregów po synchronizacji |
| `user_locations` | `path` | CSV UTF-8 `station_code,latitude,longitude[,source]` | `--user-locations` | parametr: sama nazwa pliku z `IMGW_USER_LOCATIONS_DIR` | położenia użytkownika |
| `format` | `choice` | `csv\|jsonl` (`store export`), `csv` (`series export`); domyślnie `csv` | `--format`, `-f` | parametr | format strumienia |
| `path` | `path` | plik poza magazynem w istniejącym katalogu; brak = strumień | `--path`, `-p` | lokalna | plik wyniku |
| `output` | `path` | katalog; domyślnie `./data/downloaded` | `--output`, `-o` | lokalna | katalog pobierania |
| `latitude` | `float` | 49.0–55.0 | `--latitude`, `--lat` | parametr | szerokość WGS84 |
| `longitude` | `float` | 14.0–24.5 | `--longitude`, `--lon` | parametr | długość WGS84 |
| `method` | `choice` | `POT\|AMP`, domyślnie `POT` | `--method` | parametr | metoda PMAXTP |
| `ind_x`, `ind_y` | `int` | ≥0; w `pmaxtp check\|sync` oba albo żaden | `--ind-x`, `--ind-y` | parametr | indeksy komórki |
| `main_only` | `bool` | domyślnie `false` | `--main-only` | parametr | tylko stacje główne |
| `name` | `str` | `^[a-z0-9][a-z0-9_-]{0,63}$` | `--name` | lokalna | nazwa zadania |
| `command` | `choice` | nazwa komendy; w `project add` tylko komendy zadań (§13.3) | `--command` | parametr | komenda |
| `options` | `object` | obiekt JSON opcji komendy zadania, bez `root` | `--options` (tekst JSON) | lokalna | opcje zadania |
| `geometry` | `path` | GeoJSON w katalogu projektu, tylko dla `series select` | `--geometry` | lokalna | obszar wyboru |
| `tasks` | `list` (`str`) | nazwy zadań; brak = wszystkie | `--tasks` | lokalna | zadania projektu |
| `update` | `choice` | `pinned\|upgrade`, domyślnie `pinned` | `--update` | lokalna | tryb przypięć |
| `limit` | `int` | ≥1; brak = bez limitu; REST: domyślnie i najwyżej `IMGW_API_MAX_LIMIT` | `--limit` | parametr | rozmiar strony |
| `offset` | `int` | ≥0, domyślnie 0 | `--offset` | parametr | początek strony |

### 13.3 Komendy

35 komend; komenda CLI to `imgw` + nazwa z pierwszej kolumny. „Opcje”: `*` = wymagana, `=` = wartość domyślna, definicje w §13.2. „Check”: funkcja bliźniacza dla `--check`, `?check=true` i `check_command`; `check_command` = ogólny plan `PlanAction` (walidacja, URL-e, przewidywane ścieżki, bez GET treści i bez zapisu); „—” = komenda bez skutków ubocznych (bez `--check`; `check_command` przyjmuje ją dla zadań projektu); „sama” = komenda jest sprawdzeniem. Wynik `Page[T]` = komenda listowa z opcjami `limit` i `offset`.

| Komenda | Funkcja Pythona | REST | Check | Wynik | Opcje |
|---|---|---|---|---|---|
| `datasets list` | `datasets` | `GET /api/v1/datasets/list` | — | `Page[DatasetDescriptor]` | `kind` |
| `datasets files` | `archive_files` | `GET /api/v1/datasets/files` | — | `Page[ArchiveFile]` | `dataset*`, `years*`, `months`, `params` |
| `datasets download` | `download_archives` | — | `check_command` | `DownloadReport` | `dataset*`, `years*`, `months`, `params`, `output=./data/downloaded` |
| `stations find` | `find_stations` | `GET /api/v1/stations/find` | `check_command` | `Page[StationListEntry]` | `kind`, `query`, `source=live`, `root` |
| `current hydro` | `fetch_hydro_current` | `GET /api/v1/current/hydro` | `check_command` | `Page[HydroCurrentData]` | `station` |
| `current meteo` | `fetch_meteo_current` | `GET /api/v1/current/meteo` | `check_command` | `Page[MeteoCurrentData]` | `station` |
| `current synop` | `fetch_synop` | `GET /api/v1/current/synop` | `check_command` | `Page[SynopData]` | `station`, `station_name` |
| `current warnings` | `fetch_warnings` | `GET /api/v1/current/warnings` | `check_command` | `Page[WarningData]` | `kind` |
| `current hydro-states` | `fetch_hydro_states` | `GET /api/v1/current/hydro-states` | `check_command` | `Page[HydroState]` | `main_only=false` |
| `pmaxtp fetch` | `fetch_pmaxtp` | `GET /api/v1/pmaxtp/fetch` | `check_command` | `PMaXTPResult` | `latitude*`, `longitude*`, `method=POT` |
| `pmaxtp url` | `build_pmaxtp_url` | `GET /api/v1/pmaxtp/url` | — | `str` (URL) | `latitude*`, `longitude*`, `method=POT` |
| `pmaxtp check` | `check_pmaxtp` | `GET /api/v1/pmaxtp/check` | sama | `StorePlan` | `root*`, `latitude*`, `longitude*`, `method=POT`, `ind_x`, `ind_y` |
| `pmaxtp sync` | `sync_pmaxtp` | `POST /api/v1/pmaxtp/sync` | `check_pmaxtp` | `PMaXTPStoreResult` | `root*`, `latitude*`, `longitude*`, `method=POT`, `ind_x`, `ind_y` |
| `pmaxtp read` | `read_pmaxtp` | `GET /api/v1/pmaxtp/read` | — | `PMaXTPResult` | `root*`, `ind_x*`, `ind_y*`, `method=POT`, `version` |
| `store init` | `init_store` | — | `check_command` | `StoreHandle` | `root*` |
| `store info` | `store_info` | `GET /api/v1/store/info` | — | `StoreInfo` | `root*` |
| `store scan` | `iter_store` | `GET /api/v1/store/scan` | — | `Page[StoreEntry]` | `root*`, `kind` |
| `store check` | `check_store` | `GET /api/v1/store/check` | sama | `StorePlan` | `root*`, `datasets*`, `years*`, `months`, `plan` |
| `store sync` | `sync_store` | `POST /api/v1/store/sync` | `check_store` | `SyncReport` | `root*`, `plan` albo `datasets`+`years`, `months`, `series=true` |
| `store catalog` | `build_catalog` | `POST /api/v1/store/catalog` | `check_catalog` | `CatalogReport` | `root*`, `user_locations` |
| `store export` | `export_archive` | `GET /api/v1/store/export` | `check_command` | strumień `csv\|jsonl` albo `Path` | `version*`, `root`, `format=csv`, `path` |
| `series build` | `build_series` | `POST /api/v1/series/build` | `check_series` | `SeriesReport` | `root*`, `dataset*` |
| `series select` | `select_series` | `GET /api/v1/series/select` | — | `SeriesSelection` | `root*`, `dataset*`, `stations*`, `variables`, `years`, `year_type` |
| `series read` | `read_series` | `GET /api/v1/series/read` | — | `Page[NormalizedRecord]` | `version` albo `root`+`dataset`, `station*`, `variables`, `start`, `end` |
| `series summary` | `summarize_series` | `GET /api/v1/series/summary` | — | `Page[StationCoverage]` | `version` albo `root`+`dataset`, `stations`, `variables` |
| `series export` | `export_series` | `GET /api/v1/series/export` | `check_command` | strumień `csv` albo `Path` | `version` albo `root`+`dataset`, `station*`, `variables`, `start`, `end`, `year_type`, `format=csv`, `path` |
| `project init` | `init_project` | — | `check_command` | `Project` | `project_dir*`, `store_dir*` |
| `project add` | `add_project_task` | — | `check_command` | `Project` | `project_dir*`, `name*`, `command*`, `options*`, `geometry` |
| `project remove` | `remove_project_task` | — | `check_command` | `Project` | `project_dir*`, `name*` |
| `project set-store` | `set_project_store` | — | `check_command` | `Project` | `project_dir*`, `store_dir*` |
| `project download` | `download_project` | — | `check_project` | `ProjectReport` | `project_dir*`, `tasks`, `plan`, `update=pinned` |
| `project check` | `check_project` | — | sama | `StorePlan` | `project_dir*`, `tasks`, `plan` |
| `project status` | `get_project_status` | — | — | `ProjectReport` | `project_dir*`, `tasks` |
| `project verify` | `verify_project` | — | — | `ProjectReport` | `project_dir*`, `tasks` |
| `commands schema` | `command_schema` | `GET /api/v1/commands/schema` | — | obiekt JSON Schema albo `imgw-commands/1` | `command` |

Reguły uzupełniające (egzekwuje `validate_command`, publikuje `command_schema`):

- `datasets files|download` przyjmują 10 zbiorów archiwalnych (§13.4: wszystkie poza listami stacji i PMAXTP); `store check|sync` i komendy `series` — 5 zbiorów z `in_store=true` i `time_unit` równym `day`, `month` albo `half_year`.
- `version` albo `root`+`dataset`: dokładnie jedno z nich; `dataset` wybiera bieżącą wersję szeregu zbioru.
- `stations find`: `root` jest wymagany przy `source=store`, a przy `source=live` daje `validation_error`.
- `store sync`: `plan` wyklucza `datasets`/`years`/`months`; bez planu `datasets` i `years` są wymagane.
- `store export`, `series export`: `path` wewnątrz magazynu → `validation_error`.
- Komendy zadań projektu (`project add --command`): `store info|scan|check|sync|catalog`, `series build|select|export`, `pmaxtp check|sync|read` i `datasets download` (dawne `fetch hydro|meteo`).
- Opisy grup (help CLI, tagi OpenAPI) są częścią katalogu (pole `groups` dokumentu `imgw-commands/1`).

### 13.4 Rejestr zbiorów i aliasy

`DatasetDescriptor` (§2) ma dodatkowo `kind`, `title` (polski tytuł zbioru, np. „Dane hydrologiczne dobowe”), `first_year` (dolna granica generatora offline; górnej brak, §2.1), `legacy_alias` i `in_store`; `time_unit` przyjmuje także `term`. Rejestr ma 13 deskryptorów:

| Klucz | `kind` | `in_store` | `time_unit` / `year_type` | `first_year` | Alias legacy |
|---|---|---|---|---|---|
| `pl.imgw.hydro_daily` | `hydro` | tak | `day` / `hydrological` | 1951 | `hydro/dobowe` |
| `pl.imgw.hydro_monthly` | `hydro` | tak | `month` / `hydrological` | 1951 | `hydro/miesieczne` |
| `pl.imgw.hydro_semiannual` | `hydro` | tak | `half_year` / `hydrological` | 1951 | `hydro/polroczne_i_roczne` |
| `pl.imgw.meteo_climate_daily` | `meteo` | tak | `day` / `calendar` | 1951 | `meteo/dobowe/klimat` |
| `pl.imgw.meteo_precip_daily` | `meteo` | tak | `day` / `calendar` | 1950 | `meteo/dobowe/opad` |
| `pl.imgw.hydro_stations` | `hydro` | tak | `station_list` / `none` | — | — |
| `pl.imgw.meteo_stations` | `meteo` | tak | `station_list` / `none` | — | — |
| `pl.imgw.pmaxtp` | `null` | tak | `cell` / `none` | — | — |
| `pl.imgw.hydro_phenomena` | `hydro` | nie | `day` / `hydrological` | 1951 | — |
| `pl.imgw.meteo_climate_monthly` | `meteo` | nie | `month` / `calendar` | 1951 | `meteo/miesieczne/klimat` |
| `pl.imgw.meteo_precip_monthly` | `meteo` | nie | `month` / `calendar` | 1950 | `meteo/miesieczne/opad` |
| `pl.imgw.meteo_synop_monthly` | `meteo` | nie | `month` / `calendar` | 1960 | `meteo/miesieczne/synop` |
| `pl.imgw.meteo_climate_terms` | `meteo` | nie | `term` / `calendar` | 1951 | `meteo/terminowe/klimat` |

Zbiory tylko do pobrania (`in_store=false`; bez parsera, magazynu i szeregów):

| Klucz | `server_dir` | Pliki `archive_files` |
|---|---|---|
| `pl.imgw.hydro_phenomena` | `dane_hydrologiczne/dobowe` | `<year>/zjaw_<year>.zip` (dawne `build_hydro_url(DAILY, year, 13)`) |
| `pl.imgw.meteo_climate_monthly` | `dane_meteorologiczne/miesieczne/klimat` | `<folder>/<folder>_m_k.zip`; folder 5-letni do 2000 (`1951_1955` … `1996_2000`), od 2001 roczny; jeden plik na folder, lata tego samego folderu bez duplikatów |
| `pl.imgw.meteo_precip_monthly` | `dane_meteorologiczne/miesieczne/opad` | `<folder>/<folder>_m_o.zip`; pierwszy folder `1950_1955` |
| `pl.imgw.meteo_synop_monthly` | `dane_meteorologiczne/miesieczne/synop` | `<folder>/<folder>_m_s.zip`; pierwszy folder `1960_1965` |
| `pl.imgw.meteo_climate_terms` | `dane_meteorologiczne/terminowe/klimat` | do 2000 `<folder>/<year>_k.zip`, od 2001 `<year>/<year>_<mm>_k.zip` |

- `get_dataset(value)` rozpoznaje kolejno klucz, slug i alias legacy; nieznana wartość → `validation_error` z `details.allowed` (klucze). Wyniki i komunikaty zawsze podają klucz; slug zostaje wyłącznie w nazwach katalogów magazynu (§3 bez zmian).
- Archiwa publikowane per stacja (`meteo/dobowe/synop`, `meteo/terminowe/synop`) i nieistniejące `meteo/terminowe/opad` nie mają deskryptorów: alias → `validation_error` z `details.reason` (`per_station` \| `not_published`).
- `download_hydro_data(interval, year, month, param)` i `download_meteo_data(interval, subtype, year, month)` mapują słowa przez aliasy (`hydro/<interval>`, `meteo/<interval>/<subtype>`; `dobowe` z `month=13` → `pl.imgw.hydro_phenomena`) i pobierają plik wskazany przez `archive_files`; podpisy i `DownloadResult` bez zmian.
- `archive_files` zbiorów tylko do pobrania daje te same URL-e co usunięte `build_hydro_url`/`build_meteo_url` (złote URL-e w teście U03).
- **Rozstrzygnięcia implementacji (U03):** jeden parser wejścia `imgwtools.datasets.parse_years(value, /, *, option="years")` i `parse_months(value, /, *, option="months")` (spoza `__all__`; korzystają z nich katalog i magazyn) zwraca posortowaną krotkę bez powtórzeń, a błąd ma `details.option`; `months` nie przyjmują zakresów. `ArchiveFile` miesięcznego archiwum meteo opisuje cały folder: `year` = pierwszy rok folderu, `period_end` = 31 XII ostatniego roku folderu, `month=None`. Rocznik poniżej `first_year` → `details.minimum`. `params` (także tekst `"H,Q"`) dla innego zbioru niż półroczny → `validation_error` z `details.option="params"`. Konsumenci szeregów wybierają zbiory przez `in_store` i `time_unit ∈ {day, month, half_year}` (zbiory tylko do pobrania mają `time_unit` `day`/`month`).

### 13.5 Błędy

`IMGWError.code` należy do zamkniętego rejestru `ERROR_CODES`; każda klasa ma kod domyślny, a miejsce zgłoszenia może podać inny przez `code=`.

| Kod | Kiedy | Klasa z tym kodem domyślnym | CLI (exit) | HTTP | `title` |
|---|---|---|---|---|---|
| `validation_error` | niepoprawne opcje, wartości i kombinacje, niebezpieczne ścieżki, niepoprawna treść manifestu; pydantic `RequestValidationError`; błąd składni Click | `IMGWValidationError`, `IMGWProjectError` | 2 | 400 | Nieprawidłowe dane wejściowe |
| `not_found` | brak wersji, sidecara, pliku wersji, slotu, listy stacji, komórki, szeregu lub manifestu; nieznana trasa REST | — (jawne `code=`) | 3 | 404 | Nie znaleziono |
| `conflict` | kolizja wersji, wyścig, brak atomowego zapisu, zajęta blokada, równoległa zmiana zadania, katalog niepusty, zagnieżdżony lub kolidujący z Kartografem przy `init_store` | `IMGWStoreConflictError` | 4 | 409 | Konflikt stanu |
| `source_unavailable` | serwer IMGW: przekroczony czas, błąd sieci, HTTP 4xx/5xx | `IMGWConnectionError` | 5 | 502 | Źródło IMGW niedostępne |
| `missing_dependency` | brak `pyarrow>=15` | `IMGWStoreDependencyError` | 6 | 503 | Brak opcjonalnej zależności |
| `data_error` | niepoprawne dane IMGW albo uszkodzona wersja (SHA, rozmiar, JSON, CSV, ZIP) | `IMGWDataError` | 7 | 500 | Niepoprawne dane |
| `store_unavailable` | root bez obsługiwanego znacznika lub schematu; REST: brak lub niepoprawny `IMGW_STORE_ROOT` albo `IMGW_USER_LOCATIONS_DIR` | `IMGWStoreError` | 8 | 503 | Magazyn niedostępny |
| `io_error` | `OSError` przy odczycie lub zapisie pliku (uprawnienia, brak miejsca), nieczytelny lub niezapisywalny manifest | — (adaptery mapują każdy `OSError`) | 9 | 500 | Błąd systemu plików |
| `cancelled` | przerwanie przez `cancel` lub Ctrl+C bez raportu częściowego | `IMGWCancelledError` | 130 | — | Operację anulowano |
| `forbidden` | REST: zapis wyłączony, brak tokenu serwera, brak lub zły `X-API-Key` | — (adapter REST) | — | 403 | Brak uprawnień do zapisu |
| `method_not_allowed` | REST: metoda spoza trasy | — (adapter REST) | — | 405 | Niedozwolona metoda HTTP |
| `internal_error` | każdy inny wyjątek (błąd programu) | `IMGWError` (klasa bazowa) | 1 | 500 | Błąd wewnętrzny |

Kody wyjścia CLI dla koperty: `ok` 0, `partial` 10, `failed` 11, `cancelled` 130. REST nie przekazuje `cancel`; gdyby `cancelled` dotarł do adaptera REST, odpowiedzią jest 500 `internal_error`.

Przypisanie w miejscach zgłoszeń (gdy kod różni się od domyślnego klasy): brak wersji, sidecara, pliku, listy stacji, komórki lub szeregu (`IMGWStoreError`) i brak manifestu (`IMGWProjectError`) → `not_found`; katalog projektu w magazynie i dowiązanie w ścieżce magazynu lub slotu → `validation_error`; niepusty, zagnieżdżony albo kolidujący z Kartografem katalog przy `init_store`, system plików bez dowiązań twardych dla znacznika, zajęta blokada manifestu i konflikt zadania → `conflict`; niemożliwy odczyt lub zapis manifestu → `io_error`; nieobsługiwany magazyn jako `store_dir` → `store_unavailable`; anulowanie zapisu wersji i eksportu → `IMGWCancelledError`.

Słownik `details` (wartości JSON, wszystkie opcjonalne): `option`, `value`, `allowed` (lista), `reason` (`store_unavailable`: `not_configured`, `root_invalid`, `unsupported`, `user_locations_dir_invalid`; `forbidden`: `writes_disabled`, `write_token_missing`, `invalid_api_key`; `source_unavailable`: `timeout`, `network`, `http_status`; `conflict`: `version_collision`, `not_atomic`, `locked`, `task_changed`, `path_conflict`), `url` i `status` (odpowiedź IMGW), `path` (w REST względna do root), `owner` (właściciel blokady), `errors` (lista `{option, message}` błędów pydantic), `click` (oryginalny komunikat Click).

**CLI.** Przy błędzie stdout jest pusty; wcześniejsze linie stderr to postęp i komunikaty, ostatnia — JSON błędu:

```text
$ imgw pmaxtp fetch --latitude 1 --longitude 1
{"code":"validation_error","detail":"Szerokość geograficzna 1.0 poza zakresem Polski (49.0–55.0)","details":{"option":"latitude","value":1.0}}
$ echo $?
2
```

**REST** (każdy router, także pydantic i routing; `detail` bez bezwzględnych ścieżek serwera, reguła T21):

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{"type":"urn:imgwtools:error:validation_error","title":"Nieprawidłowe dane wejściowe","status":400,"detail":"Szerokość geograficzna 1.0 poza zakresem Polski (49.0–55.0)","instance":"/api/v1/pmaxtp/fetch","code":"validation_error","details":{"option":"latitude","value":1.0}}
```

`RequestValidationError` → 400 `validation_error`, `detail` „Niepoprawne parametry lub ciało żądania”, `details.errors` = `[{"option": "<pole>", "message": "<komunikat pydantic>"}]`; nieznana trasa → 404 `not_found` („Nieznana trasa”), zła metoda → 405 `method_not_allowed`.

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","title":"problem+json IMGWTools","type":"object","required":["type","title","status","detail","code","details"],"properties":{"type":{"type":"string","pattern":"^urn:imgwtools:error:[a-z_]+$"},"title":{"type":"string","minLength":1},"status":{"type":"integer","minimum":400,"maximum":599},"detail":{"type":"string","minLength":1},"instance":{"type":"string"},"code":{"enum":["validation_error","not_found","conflict","source_unavailable","missing_dependency","data_error","store_unavailable","io_error","forbidden","method_not_allowed","internal_error"]},"details":{"type":"object"}},"additionalProperties":false}
```

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","title":"błąd CLI IMGWTools (ostatnia linia stderr)","type":"object","required":["code","detail","details"],"properties":{"code":{"enum":["validation_error","not_found","conflict","source_unavailable","missing_dependency","data_error","store_unavailable","io_error","cancelled","internal_error"]},"detail":{"type":"string","minLength":1},"details":{"type":"object"}},"additionalProperties":false}
```

### 13.6 Koperta wyniku, statusy i stronicowanie

`run_command` i `check_command` zwracają `CommandResult`; jego postać JSON to `imgw-result/1` (licznik `/N` według polityki IMGW-13):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "imgw-result/1",
  "type": "object",
  "required": ["schema", "command", "check", "status", "result", "notices"],
  "properties": {
    "schema": {"const": "imgw-result/1"},
    "command": {"type": "string", "pattern": "^[a-z]+ [a-z][a-z-]*$"},
    "check": {"type": "boolean"},
    "status": {"enum": ["ok", "partial", "failed", "cancelled"]},
    "result": true,
    "notices": {"type": "array", "items": {"$ref": "#/$defs/notice"}}
  },
  "additionalProperties": true,
  "$defs": {
    "notice": {
      "type": "object",
      "required": ["level", "code", "text"],
      "properties": {
        "level": {"enum": ["info", "warning", "error"]},
        "code": {"type": "string", "pattern": "^[a-z_]+$"},
        "text": {"type": "string", "minLength": 1}
      },
      "additionalProperties": false
    },
    "page": {
      "type": "object",
      "required": ["items", "total", "limit", "offset"],
      "properties": {
        "items": {"type": "array"},
        "total": {"type": "integer", "minimum": 0},
        "limit": {"type": ["integer", "null"], "minimum": 1},
        "offset": {"type": "integer", "minimum": 0}
      },
      "additionalProperties": false
    }
  }
}
```

`result` komendy listowej spełnia `#/$defs/page`; `check=true` oznacza plan `imgw-plan/1` w `result` (`--check`, `?check=true`, `check_command`); `result=null` wyłącznie przy `cancelled` bez raportu.

Status wylicza jedna funkcja katalogu:

| Wynik | Porażka pozycji | Sukces pozycji | Anulowanie |
|---|---|---|---|
| `StorePlan` | pozycja lub akcja `check_failed` | pozostałe | `cancelled=true` |
| `SyncReport` | `items[].status` `failed` lub `stale_plan`; `series[].status=failed` | `created`, `relabeled`, `unchanged`, `reused` | `cancelled=true` |
| `DownloadReport` | `items[].status=failed` | `downloaded` | `cancelled=true` |
| `ProjectReport` | zadanie `failed`; `files[].status` `failed` lub `stale_plan` | pozostałe | `cancelled=true` |
| `SeriesReport`, `CatalogReport`, `PMaXTPStoreResult` | `status=failed` | pozostałe | `status=cancelled` |
| `IMGWCancelledError` z funkcji | — | — | zawsze, `result=null` |
| pozostałe wyniki | — | — | — |

Reguła: `cancelled`, jeśli zaszło anulowanie; w przeciwnym razie `ok` bez porażek, `failed`, gdy są porażki i nie ma sukcesów, a `partial` w pozostałych przypadkach. Wyniki strumieniowe mają `ok` w chwili zwrotu; błąd podczas iteracji jest wyjątkiem. `notices` zawiera każdy różny `(level, code, text)` raz, w kolejności pierwszego wystąpienia; hooki `on_notice` dostają wszystkie, a postęp nie trafia do koperty.

**Stronicowanie.** Komendy `Page[T]` mają opcje `limit` i `offset` (dodaje je katalog; widoczne w CLI, REST i schemacie). `run_command` wywołuje funkcję bez nich, liczy `total` po filtrach funkcji, a przed stronicowaniem, i zwraca `items` = wycinek `[offset, offset + limit)` w kolejności funkcji (bez `limit` — do końca); `offset ≥ total` daje pustą stronę, nie błąd. REST: brak `limit` = `IMGW_API_MAX_LIMIT` (domyślnie 1000), większy → 400 `validation_error`.

**Strumienie** (`store export`, `series export` bez `path`): CLI pisze na stdout wyłącznie linie danych, komunikaty i ewentualny błąd na stderr, a kod wyjścia liczy jak dla koperty; REST zwraca ciało `text/csv; charset=utf-8` albo `application/x-ndjson` z `Content-Disposition: attachment` i nagłówkami `X-IMGW-Status: ok` oraz `X-IMGW-Notices` (tablica komunikatów w JSON, znaki spoza ASCII jako `\uXXXX`). Komunikaty strumienia (`license_terms`) powstają przed pierwszą linią. Z `path` wynik jest zwykłą kopertą z `result` = ścieżka pliku.

Przykład `imgw store sync` z nieaktualną pozycją planu:

```json
{"schema":"imgw-result/1","command":"store sync","check":false,"status":"partial","result":{"items":[{"slot":"archive:pl.imgw.hydro_daily:2023/codz_2023.zip","status":"created","version":"archives/versions/dane_hydrologiczne/dobowe/2023/codz_2023/2024-08-28_1a2b3c4d/codz_2023.zip","error":null,"task":null,"error_code":null},{"slot":"archive:pl.imgw.hydro_daily:2024/codz_2024.zip","status":"stale_plan","version":null,"error":"…","task":null,"error_code":null}],"series":[{"status":"failed","version":null,"stations":0,"source_files":[],"problems":["archive:pl.imgw.hydro_daily:2024/codz_2024.zip: stale_plan"]}],"cancelled":false},"notices":[{"level":"info","code":"license_terms","text":"Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy …"}]}
```

### 13.7 Sloty

Slot ma postać `<kind>:<klucz>` albo `<kind>:<klucz>:<selektor>`; `<kind>` ∈ `archive`, `series`, `catalog`, `pmaxtp`; `<klucz>` pochodzi z rejestru, a dla katalogu stacji jest kluczem pochodnym `pl.imgw.stations` (jak w sidecarze, §8); selektor nie zawiera `:`, więc parser dzieli tekst na dwóch pierwszych dwukropkach.

| Rodzaj | Selektor | Przykład | Katalog slotu (bez zmian, §3) |
|---|---|---|---|
| archiwum | `server_path` bez przedrostka `server_dir/` | `archive:pl.imgw.hydro_daily:2024/codz_2024.zip` | `archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/` |
| archiwum miesięczne | jak wyżej | `archive:pl.imgw.hydro_daily:2022/codz_2022_03.zip` | `archives/versions/dane_hydrologiczne/dobowe/2022/codz_2022_03/` |
| archiwum półroczne | jak wyżej | `archive:pl.imgw.hydro_semiannual:2020/polr_Q_2020.zip` | `archives/versions/dane_hydrologiczne/polroczne_i_roczne/2020/polr_Q_2020/` |
| archiwum meteo | jak wyżej | `archive:pl.imgw.meteo_climate_daily:1991_1995/1995_k.zip` | `archives/versions/dane_meteorologiczne/dobowe/klimat/1991_1995/1995_k/` |
| lista stacji | nazwa pliku | `archive:pl.imgw.hydro_stations:lista_stacji_hydro.csv` | `archives/versions/dane_hydrologiczne/lista_stacji_hydro/` |
| szereg | brak | `series:pl.imgw.hydro_daily` | `series/versions/hydro_daily/` |
| plik stacji szeregu (tylko przypięcia projektu) | kod stacji | `series:pl.imgw.hydro_daily:149190310` | `series/versions/hydro_daily/<label>_<sha8>/stations/149190310.parquet` |
| katalog stacji | brak | `catalog:pl.imgw.stations` | `stations/versions/` |
| komórka PMAXTP | `<METODA>/<indX>_<indY>` | `pmaxtp:pl.imgw.pmaxtp:POT/751_317` | `pmaxtp/versions/POT/751_317/` |
| pobranie płaskie | jak archiwum | `archive:pl.imgw.meteo_synop_monthly:1996_2000/1996_2000_m_s.zip` | poza magazynem: `<output>/dane_meteorologiczne/miesieczne/synop/1996_2000/1996_2000_m_s.zip` |

Ten sam plik ma ten sam slot w `iter_store`, `current_version`, `SyncReport.items`, `DownloadReport.items` i `ProjectReport.files` (nazwa zadania osobno w `task`). `current_version` przyjmuje sloty archiwum, szeregu bez selektora, katalogu i komórki; selektor stacji występuje wyłącznie w przypięciach. Wpis `problem` skanu ma slot wersji, której dotyczy, albo `null` (np. nieznany katalog), a `version` = ścieżka wadliwego elementu. Dawne postaci (`archive:<server_path>`, `series:<slug>`, `catalog:stations`, `pmaxtp:<M>:<x>_<y>`, `archives/versions/…`, `<zadanie>:<ścieżka>`) → `validation_error` z opisem gramatyki.

> [ADR-002, U05] `<klucz>` slotu to wyłącznie pełny klucz rejestru (slug i alias legacy tylko na wejściu opcji `dataset`). Zbiór slotu archiwum = zbiór magazynu z najdłuższym pasującym `server_dir`; selektor listy stacji to wyłącznie opublikowana nazwa pliku, pozostałych archiwów — ścieżka z folderem; katalog wersji spoza tej reguły jest problemem `unknown_entry` ze slotem `null`, podobnie dowiązanie, porzucony staging i nieobsługiwany znacznik. `OperationResult.error_code` mają wyłącznie pozycje `failed` (`check_failed` z planu: `source_unavailable` dla błędu listingu/HEAD, `data_error` dla uszkodzonej wersji lokalnej); `stale_plan` i `cancelled` mają `null`. `summarize_series` porządkuje wiersze według kodu stacji, zmiennej w kolejności deskryptora i okresu `winter`, `summer`, `annual`; `check_store(..., plan=PLIK)` wymaga istniejącego katalogu pliku.

### 13.8 Nowe i zmienione funkcje

```python
YearsArg = int | str | Iterable[int | str]   # 2024 | "2020-2023" | "2020,2022" | [2020, "2022-2023"]
MonthsArg = int | str | Iterable[int | str]

# Rejestr i pobieranie płaskie
def datasets(*, kind: Literal["hydro", "meteo"] | None = None) -> tuple[DatasetDescriptor, ...]: ...
def get_dataset(dataset: str, /) -> DatasetDescriptor: ...          # klucz | slug | alias legacy
def archive_files(dataset: str, /, *, years: YearsArg, months: MonthsArg | None = None,
                  params: Iterable[Literal["H", "Q", "T"]] | None = None) -> tuple[ArchiveFile, ...]: ...
def download_archives(dataset: str, /, *, years: YearsArg, months: MonthsArg | None = None,
                      params: Iterable[Literal["H", "Q", "T"]] | None = None,
                      output: PathArg = "data/downloaded", timeout: float = 120.0,
                      on_progress: ProgressHook | None = None,
                      on_notice: NoticeHook | None = None,
                      cancel: Cancel | None = None) -> DownloadReport: ...

# Odczyty live; każda funkcja ma bliźniaka *_async o identycznych argumentach
def fetch_hydro_current(*, station: str | None = None,
                        timeout: float = DEFAULT_TIMEOUT) -> list[HydroCurrentData]: ...
def fetch_meteo_current(*, station: str | None = None,
                        timeout: float = DEFAULT_TIMEOUT) -> list[MeteoCurrentData]: ...
def fetch_synop(*, station: str | None = None, station_name: str | None = None,
                timeout: float = DEFAULT_TIMEOUT) -> list[SynopData]: ...
def fetch_warnings(*, kind: Literal["hydro", "meteo"] | None = None,
                   timeout: float = DEFAULT_TIMEOUT) -> list[WarningData]: ...
def fetch_hydro_states(*, main_only: bool = False,
                       timeout: float = DEFAULT_TIMEOUT) -> list[HydroState]: ...
def fetch_pmaxtp(latitude: float, longitude: float, *, method: Literal["POT", "AMP"] = "POT",
                 timeout: float = DEFAULT_TIMEOUT, validate_coords: bool = True) -> PMaXTPResult: ...
def find_stations(*, kind: Literal["hydro", "meteo"] | None = None, query: str | None = None,
                  source: Literal["live", "store"] = "live", root: RootArg | None = None,
                  timeout: float = DEFAULT_TIMEOUT) -> tuple[StationListEntry, ...]: ...
def build_pmaxtp_url(latitude: float, longitude: float, *,
                     method: Literal["POT", "AMP"] = "POT") -> str: ...
def build_api_url(endpoint: str, /, *, station: str | None = None,
                  station_name: str | None = None) -> str: ...

# Magazyn (zmiany wobec §5, §7, §9; hooki jak dotąd)
def check_store(root: RootArg, /, *, datasets: Iterable[str], years: YearsArg,
                months: MonthsArg | None = None, plan: PathArg | None = None,
                on_progress=None, on_notice=None, cancel=None) -> StorePlan: ...
def sync_store(root: RootArg, /, *, datasets: Iterable[str] | None = None,
               years: YearsArg | None = None, months: MonthsArg | None = None,
               plan: StorePlan | PathArg | None = None, series: bool = True,
               on_progress=None, on_notice=None, cancel=None) -> SyncReport: ...
def check_pmaxtp(root: RootArg, /, *, latitude: float, longitude: float,
                 method: Literal["POT", "AMP"] = "POT", ind_x: int | None = None,
                 ind_y: int | None = None, on_progress=None, on_notice=None,
                 cancel=None) -> StorePlan: ...
def sync_pmaxtp(root: RootArg, /, *, latitude: float, longitude: float,
                method: Literal["POT", "AMP"] = "POT", ind_x: int | None = None,
                ind_y: int | None = None, on_progress=None, on_notice=None,
                cancel=None) -> PMaXTPStoreResult: ...
def read_pmaxtp(root: RootArg, /, *, ind_x: int, ind_y: int,
                method: Literal["POT", "AMP"] = "POT",
                version: PathArg | None = None) -> PMaXTPResult: ...
def current_version(root: RootArg, /, *, slot: str) -> StoreEntry | None: ...   # §13.7
def select_series(root: RootArg, /, *, dataset: str, stations: Iterable[str],
                  variables: Iterable[str] | None = None, years: YearsArg | None = None,
                  year_type: Literal["hydrological", "calendar"] | None = None) -> SeriesSelection: ...
def read_series(version: PathArg | None = None, /, *, root: RootArg | None = None,
                dataset: str | None = None, station: str,
                variables: Iterable[str] | None = None, start: date | None = None,
                end: date | None = None) -> Iterator[NormalizedRecord]: ...
def summarize_series(version: PathArg | None = None, /, *, root: RootArg | None = None,
                     dataset: str | None = None, stations: Iterable[str] | None = None,
                     variables: Iterable[str] | None = None) -> tuple[StationCoverage, ...]: ...
def export_series(version: PathArg | None = None, /, *, root: RootArg | None = None,
                  dataset: str | None = None, station: str,
                  variables: Iterable[str] | None = None, start: date | None = None,
                  end: date | None = None,
                  year_type: Literal["hydrological", "calendar"] | None = None,
                  format: Literal["csv"] = "csv", path: PathArg | None = None,
                  on_progress=None, on_notice=None, cancel=None) -> Path | Iterator[str]: ...
def export_archive(version: PathArg, /, *, root: RootArg | None = None,
                   format: Literal["csv", "jsonl"] = "csv", path: PathArg | None = None,
                   on_progress=None, on_notice=None, cancel=None) -> Path | Iterator[str]: ...
def check_project(project_dir: PathArg, /, *, tasks: Iterable[str] | None = None,
                  plan: PathArg | None = None, on_progress=None, on_notice=None,
                  cancel=None) -> StorePlan: ...

# Katalog komend
def command_schema(command: str | None = None, /) -> dict[str, object]: ...
def validate_command(command: str, /, *, options: Mapping[str, object]) -> dict[str, object]: ...
def format_command(command: str, /, *, options: Mapping[str, object]) -> str: ...
def check_command(command: str, /, *, options: Mapping[str, object], on_progress=None,
                  on_notice=None, cancel=None) -> CommandResult[StorePlan]: ...
def run_command(command: str, /, *, options: Mapping[str, object], on_progress=None,
                on_notice=None, cancel=None) -> CommandResult[object]: ...
```

- **`find_stations`**: `source="live"` pobiera listy CSV IMGW (`station_source_files()`, jedno GET na rodzinę); `source="store"` czyta offline `read_station_list` i dopisuje `latitude`/`longitude` z bieżącej wersji katalogu (`read_catalog`; brak katalogu albo `geometry=null` → `None`). `query` po normalizacji (NFKD bez znaków diakrytycznych, `ł` → `l`, casefold) pasuje, gdy jest podciągiem nazwy lub rzeki albo prefiksem `station_code`. Kolejność: `kind` (hydro, meteo), znormalizowana nazwa, kod; kod powtórzony na liście meteo wraca w każdym wierszu (§8). Lista live nie ma współrzędnych (`None`).
- **`summarize_series`**: czyta wyłącznie `series.json` (SHA z sidecarem, bez pyarrow); jeden wiersz na stację × zmienną (× okres półrocza) w kolejności kod, zmienna, okres; nieznana stacja lub zmienna → `validation_error`.
- **`select_series`**: semantyka dawnej komendy `series select` (§10, T18); `SeriesSelection.version` = `series.json` bieżącej wersji.
- **`read_series`, `summarize_series`, `export_series`**: `version` (bezwzględna albo względna do `root`) albo `root` + `dataset` (bieżąca wersja szeregu zbioru); oba lub żadne → `validation_error`; `variables=None` = wszystkie zmienne zbioru.
- **`export_series`, `export_archive`**: z `path` — atomowy plik przez `.part` (§9, T17), wynik `Path`; bez `path` — iterator gotowych linii (CSV z `\r\n`, JSONL z `\n`) bajtowo równy treści pliku; `path` w magazynie → `validation_error`; anulowanie → `IMGWCancelledError`; `license_terms` przed pierwszą linią. `export_archive` zachowuje dokładnie format dawnej komendy `store read` (§10).
  [ADR-002, U07] Walidacja opcji, weryfikacja SHA i odczyt danych stacji szeregu dzieją się przed zwrotem i przed zapisem; potem `cancel` (pierwsze sprawdzenie) i `license_terms` (`on_notice` w chwili wywołania, więc trafia do koperty także przy strumieniu; treść: atrybucja zbioru + formuła „przetworzone” + warunki). `cancel` sprawdzany dalej co 256 wierszy (w trybie iteratora `IMGWCancelledError` z iteracji) i przed `os.replace`. „W magazynie” = dowolny przodek celu ze znacznikiem `imgw-store.json` (`details.option=path`); cel musi być plikiem w istniejącym katalogu; wynik `Path` bezwzględny. Archiwum bez rekordów daje zero linii (jak dawne `store read`); szereg pusty w zakresie `start`/`end` → `data_error`. Postęp: szereg co 256 wierszy i na końcu, archiwum raz na końcu (`unit=row`).
- **`download_archives`**: semantyka dawnych `fetch hydro|meteo` (§10, T18): `<output>/<server_path>` przez unikalny `.part` i `os.replace`; błąd pliku = pozycja `failed` z `error_code`, bez przerywania; `license_terms` po pierwszym udanym pliku; anulowanie między plikami.
  [ADR-002, U06] Walidacja opcji (`archive_files`) przed utworzeniem `output` i przed pierwszym żądaniem; katalog `output` powstaje na początku (błąd `OSError` = wyjątek, adapter → `io_error`); `error_code` pozycji: `source_unavailable` (HTTP/sieć/timeout, jak odczyty live), `data_error` (nie-ZIP, zły `Content-Length`), `io_error` (zapis pliku). Po anulowaniu pozostałe pliki są pozycjami `cancelled` (`path=null`). `download_hydro_data`/`download_meteo_data` wybierają plik przez rejestr (alias `hydro/<interwał>`, `meteo/<interwał>/<podtyp>`; `dobowe`+`month=13` → `pl.imgw.hydro_phenomena`); brakujący miesiąc/parametr → `validation_error` z `details.option` `month`/`param` zamiast `ValueError`. `build_pmaxtp_url` sam odrzuca nieznaną metodę (`details` `option`, `allowed`). `build_catalog` sprawdza nagłówki plików położeń przed pobraniem list (zły nagłówek nic nie zapisuje); plik użytkownika: `details.option="user_locations"`.
- **`check_store(..., plan=PLIK)`, `check_project(..., plan=PLIK)`**: zapisują plan (`StorePlan.to_json`) poza magazynem i zwracają go; plik w magazynie → `validation_error`.
- **`command_schema`**: bez argumentu → dokument `imgw-commands/1`; z nazwą → schemat jednej komendy; nieznana nazwa → `validation_error` z `details.allowed`. Mapowanie typów: `str` → `string`, `int` → `integer`, `float` → `number`, `bool` → `boolean`, `date` → `string` z `format: date`, `path` → `string` z `x-imgw-type: path`, `choice` → `enum`, `list` → `array` (`items` według `CommandOption.items`; `year` = `anyOf` liczby i wzorca `^[0-9]{1,4}-[0-9]{1,4}$`), `object` → `object`; `help` → `description`, `default` → `default`, `minimum`/`maximum`/`pattern` bez zmian; `requires` → `dependentRequired`, `one_of` → `oneOf` grup `required`, `rules` → `x-imgw.rules`. Wyliczenia zbiorów zawierają wyłącznie klucze (aliasy są wygodą wejścia, nie częścią schematu). REST dopisuje do `limit` `default` i `maximum` z `IMGW_API_MAX_LIMIT`.
  [ADR-002, U08] `validate_command`: `store_dir` i `geometry` zostają względne (wobec katalogu projektu), względna `version` → wobec `root`, pozostałe ścieżki → bezwzględne wobec CWD; wartość `bool` równa domyślnej jest pomijana (CLI wyraża ją brakiem flagi `--x`/`--no-x`), więc `format_command` → parsowanie → `validate_command` daje te same opcje. Reguły mające walidator biblioteki zgłasza ten walidator z własnym komunikatem (granice Polski, `archive_files` dla roczników i `params`, `find_stations` dla `root`/`source`, zmienne zbioru); konflikt `version`+`dataset`+`root` ma `details.option="dataset"`, a błąd opcji zadania w `project add` — `details.option="options"`. Schemat: `str` ma `minLength: 1`, `list` ma `minItems: 1` i ograniczenia elementów w `items`; `x-imgw.cli.flags` = flaga, aliasy i `--no-x` dla `bool` domyślnie prawdziwego; komenda bez trasy ma `x-imgw.rest=null`; `x-imgw.result_type` = typ elementu listy albo wyniku (`str` dla strumieni i URL, `dict` dla `commands schema`). `check_command`: komendy-sprawdzenia (`store check`, `pmaxtp check`, `project check`) działają bez zapisu pliku planu; plan ogólny — odczyty `current`, odczyty live `unverifiable` z URL-em i bez żądania, `datasets download` jedna akcja na plik (`missing`, przy istniejącym pliku `unverifiable`), `store sync --plan` zwraca wczytany plan po sprawdzeniu `root`; plan komendy bez katalogu ma `root` = CWD. `IMGWCancelledError` → koperta `cancelled` z `result=null` i komunikatami zebranymi do tej chwili. Zadanie projektu `datasets download` z nieudaną pozycją `DownloadReport` kończy się `failed` (nic nie przypina, jak dawne `fetch`).

`imgw stations find -k hydro -q raba --limit 20`:

```json
{"schema":"imgw-result/1","command":"stations find","check":false,"status":"ok","result":{"items":[{"kind":"hydro","station_code":"149190310","name":"Raba","river":"Raba","hydrographic_code":"2138","river_order":1,"short_code":null,"latitude":null,"longitude":null}],"total":1,"limit":20,"offset":0},"notices":[]}
```

`imgw series summary --root /srv/imgw -d pl.imgw.hydro_daily -s 149190310`:

```json
{"schema":"imgw-result/1","command":"series summary","check":false,"status":"ok","result":{"items":[{"station_code":"149190310","variable":"H","unit":"cm","period":null,"first":"2023-11-01","last":"2024-10-31","with_value":365,"accumulated":0,"gaps":[["2024-02-29","2024-02-29"]]},{"station_code":"149190310","variable":"Q","unit":"m3/s","period":null,"first":null,"last":null,"with_value":0,"accumulated":0,"gaps":[]}],"total":2,"limit":null,"offset":0},"notices":[]}
```

`command_schema("stations find")`:

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","title":"stations find","description":"Znajdź stacje IMGW po nazwie, rzece albo prefiksie kodu.","type":"object","properties":{"kind":{"enum":["hydro","meteo"],"description":"Rodzaj stacji; brak = obie rodziny"},"query":{"type":"string","minLength":1,"description":"Fragment nazwy lub rzeki albo prefiks kodu"},"source":{"enum":["live","store"],"default":"live","description":"live: listy IMGW na żywo; store: zapisany magazyn"},"root":{"type":"string","x-imgw-type":"path","description":"Katalog magazynu (wymagany przy source=store)"},"limit":{"type":"integer","minimum":1,"description":"Rozmiar strony"},"offset":{"type":"integer","minimum":0,"default":0,"description":"Początek strony"}},"additionalProperties":false,"x-imgw":{"command":"stations find","group":"stations","function":"find_stations","check":"check_command","result":"list","result_type":"StationListEntry","cli":{"command":"imgw stations find","flags":{"kind":["--kind","-k"],"query":["--query","-q"],"source":["--source"],"root":["--root","-r"],"limit":["--limit"],"offset":["--offset"]}},"rest":{"method":"GET","path":"/api/v1/stations/find","server_options":["root"],"local_options":[]},"rules":["root jest wymagany przy source=store i niedozwolony przy source=live"]}}
```

`command_schema()` (skrót):

```json
{"schema":"imgw-commands/1","version":"3.0.0","result_schema":"imgw-result/1","groups":{"datasets":"Rejestr zbiorów IMGW: lista, pliki i pobieranie","stations":"Wyszukiwanie stacji","current":"Dane bieżące z API IMGW","pmaxtp":"Opady maksymalne PMAXTP","store":"Wersjonowany magazyn","series":"Szeregi stacji","project":"Projekty imgw-project/1","commands":"Opis katalogu komend"},"commands":["…35 schematów jak wyżej…"],"errors":[{"code":"validation_error","title":"Nieprawidłowe dane wejściowe","exit_code":2,"http_status":400},"…"],"exit_codes":{"ok":0,"partial":10,"failed":11,"cancelled":130}}
```

`DownloadReport` (`imgw datasets download -d meteo/miesieczne/synop -y 1998`):

```json
{"output":"/home/user/data/downloaded","items":[{"slot":"archive:pl.imgw.meteo_synop_monthly:1996_2000/1996_2000_m_s.zip","url":"https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/miesieczne/synop/1996_2000/1996_2000_m_s.zip","status":"downloaded","path":"/home/user/data/downloaded/dane_meteorologiczne/miesieczne/synop/1996_2000/1996_2000_m_s.zip","error":null,"error_code":null}],"cancelled":false}
```

### 13.9 Typy katalogu, koperty i błędów

```python
ErrorCode = Literal["validation_error", "not_found", "conflict", "source_unavailable",
                    "missing_dependency", "data_error", "store_unavailable", "io_error",
                    "cancelled", "forbidden", "method_not_allowed", "internal_error"]
@dataclass(frozen=True)
class ErrorSpec:
    code: ErrorCode; title: str; exit_code: int | None; http_status: int | None
ERROR_CODES: Mapping[ErrorCode, ErrorSpec]            # dokładnie wiersze tabeli §13.5
class IMGWError(Exception):
    def __init__(self, message: str, /, *, code: ErrorCode | None = None,
                 details: Mapping[str, object] | None = None) -> None: ...
    code: ErrorCode                  # domyślnie kod klasy; spoza rejestru → ValueError
    detail: str                      # == str(exc), po polsku
    details: Mapping[str, object]    # kopia, wartości JSON; zachowane przy pickle
class IMGWCancelledError(IMGWError): ...               # code == "cancelled"

@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]; total: int; limit: int | None; offset: int
@dataclass(frozen=True)
class CommandResult(Generic[T]):
    command: str; check: bool
    status: Literal["ok", "partial", "failed", "cancelled"]
    result: T | None; notices: tuple[Notice, ...]
    def to_json(self, *, root: PathArg | None = None,
                server: bool = False) -> dict[str, object]: ...   # imgw-result/1, §13.1 p. 4
@dataclass(frozen=True)
class DownloadItem:
    slot: str; url: str; status: Literal["downloaded", "failed", "cancelled"]
    path: Path | None; error: str | None; error_code: ErrorCode | None
@dataclass(frozen=True)
class DownloadReport:
    output: Path; items: tuple[DownloadItem, ...]; cancelled: bool
@dataclass(frozen=True)
class OperationResult:
    slot: str | None
    status: Literal["created", "relabeled", "unchanged", "reused",
                    "failed", "stale_plan", "cancelled"]
    version: Path | None; error: str | None
    task: str | None = None; error_code: ErrorCode | None = None
@dataclass(frozen=True)
class CommandOption:
    name: str
    type: Literal["str", "int", "float", "bool", "date", "path", "list", "choice", "object"]
    required: bool; flag: str; choices: tuple[str, ...]; help: str
    default: object = None
    aliases: tuple[str, ...] = ()                        # np. ("-y",), ("--lat",)
    items: Literal["str", "int", "year", "choice"] | None = None   # elementy list
    minimum: float | None = None; maximum: float | None = None; pattern: str | None = None
    rest: Literal["param", "server", "local"] = "param"
@dataclass(frozen=True)
class DataCommand:
    name: str; description: str; options: tuple[CommandOption, ...]
    function: str                                        # nazwa z imgwtools.__all__
    check: str | None                                    # bliźniak, "check_command" albo None
    result: Literal["object", "list", "stream"]
    method: Literal["GET", "POST"] | None                # None = komenda lokalna, bez REST
    requires: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # → dependentRequired
    one_of: tuple[tuple[str, ...], ...] = ()             # → oneOf grup required
    rules: tuple[str, ...] = ()                          # pozostałe reguły (PL) → x-imgw.rules

# Zmiany istniejących typów:
# DatasetDescriptor   + kind, title, first_year, legacy_alias, in_store; time_unit + "term"
# StationListEntry    + latitude: float | None = None, longitude: float | None = None
# StationCoverage     station → station_code
# ProjectFile         station → station_code (imgw-project.json: files[].station_code)
# StoreEntry          slot: str | None
# HydroCurrentData    station_id → station_code; + latitude, longitude (API: lat, lon)
# SynopData           station_id → station_code
# WarningData         warning_type → kind: Literal["hydro", "meteo"]; + event (nazwa zdarzenia);
#                     [ADR-002, U04] źródła API warningshydro/warningsmeteo: id|numer, nazwa_zdarzenia|zdarzenie,
#                     stopien|stopień, obowiazuje_od|data_od, obowiazuje_do|data_do, tresc|przebieg,
#                     region = województwa z obszary albo kody teryt; {"message": …} = brak ostrzeżeń
# MeteoCurrentData z kluczy API meteo: kod_stacji, nazwa_stacji, lat, lon, temperatura_powietrza,
# temperatura_powietrza_data, wiatr_srednia_predkosc, wilgotnosc_wzgledna, opad_10min
class MeteoCurrentData(BaseModel):
    station_code: str; station_name: str; latitude: float | None; longitude: float | None
    air_temp_c: float | None; air_temp_date: str | None; wind_speed_ms: float | None
    humidity_percent: float | None; precipitation_10min_mm: float | None
class HydroState(BaseModel):             # API mapy hydro-back.imgw.pl
    station_code: str; name: str; river: str | None
    latitude: float | None; longitude: float | None; water_state: str | None
```

### 13.10 Generowanie CLI, REST i web

**CLI** (`cli/_dispatch.py` — jedyny adapter):

- Grupy i komendy powstają z `data_commands()`: help komendy = `description`, help opcji = `help`, panel „Opcje wymagane”, `imgw --help` wymienia grupy z opisami z katalogu.
- Flagi = `CommandOption.flag` + `aliases`; listy po przecinku; `bool` z domyślną prawdą → `--x/--no-x`, z domyślnym fałszem → `--x`; `--root` czyta `IMGW_STORE_ROOT`, gdy flagi brak. Click nie waliduje typów: do `run_command` trafia surowy tekst podanych opcji.
- Flagi zarezerwowane: `--check` (tylko przy `DataCommand.check` ≠ `None`; wywołuje `check_command`), `--schema` (= `imgw commands schema --command "<ta komenda>"`, bez wykonania), `--help`.
- stdout: jeden dokument JSON koperty zakończony `\n`; strumienie bez `--path` — wyłącznie linie danych. stderr: postęp `[bieżący/łączny] tekst`, komunikaty `Informacja|Ostrzeżenie|Błąd: tekst` (każdy różny raz) i — jako ostatnia linia — JSON błędu (§13.5).
- Kody wyjścia: §13.5. Pierwsze Ctrl+C ustawia `cancel` (raport częściowy na stdout, kod 130), drugie przerywa natychmiast (JSON `cancelled`, kod 130).
- Poza katalogiem i bez zmian: `imgw version`, `imgw server`, `imgw admin …`.

**REST** (`api/routes/commands.py`, `api/errors.py`):

- Jedna trasa na komendę z `method`: `/api/v1/<grupa>/<nazwa>`; tag OpenAPI = grupa, `operationId` = nazwa z `_` (`store_sync`), opis z katalogu; `GET /api/v1` wylicza trasy z katalogu.
- GET: parametry query z opcji `rest="param"`; POST: ciało z modelu `pydantic.create_model` wygenerowanego z opcji (`extra="forbid"`, typy luźne: tekst, liczba, lista, obiekt), wartości normalizuje `validate_command`. Opcje `rest="server"` (`root`) wstawia serwer, opcji `rest="local"` nie ma; podanie którejkolwiek → 400.
- `?check=true` (tylko POST) → `check_command`: bez zapisu i bez tokenu, ale z root.
- Odpowiedź: 200 + `CommandResult.to_json(root=IMGW_STORE_ROOT, server=True)` dla wyników obiektowych i listowych, strumienie według §13.6; model odpowiedzi w OpenAPI = koperta z `result` opisanym schematem typu wyniku (pydantic `TypeAdapter`).
- POST bez `?check=true` wymaga kontroli zapisu z ADR-001/T21 (`IMGW_STORE_WRITES_ENABLED=true`, `IMGW_STORE_WRITE_TOKEN`, `X-API-Key` w stałym czasie), inaczej 403 `forbidden` z `details.reason`; kontrola zapisu poprzedza kontrolę root.
- Komendy z `root` bez poprawnego `IMGW_STORE_ROOT` → 503 `store_unavailable`; `store info` i `store scan` odpowiadają diagnostycznie 200 także dla nieobsługiwanego root; `stations find` z `source=live` nie wymaga root.
- `version` wyłącznie względna do root: pod `archives/versions/` (`store export`), `series/versions/` (komendy `series`) lub `pmaxtp/versions/` (`pmaxtp read`), bez `..`, `\`, pustych segmentów i dowiązań — inaczej 400; nieistniejąca → 404. `user_locations` = sama nazwa pliku z `IMGW_USER_LOCATIONS_DIR`.
- Każdy błąd, także pydantic, 404 i 405, to problem+json (§13.5); teksty bez bezwzględnych ścieżek serwera (T21). Nowe ustawienie `IMGW_API_MAX_LIMIT` (`Settings.api_max_limit`, domyślnie 1000).

**Web**:

- Handlery wywołują wyłącznie funkcje publiczne: `run_command` (`stations find` ze stronicowaniem), `datasets`/`archive_files` (formularze i linki pobierania po kluczu zbioru), `fetch_pmaxtp_async`, `fetch_hydro_states_async`; w `web/` nie ma `httpx`, parsowania CSV ani budowania URL-i.
- Mapa czyta `GET /api/v1/current/hydro-states`; trasa `/map/stations` znika.
- Każdy `IMGWError` → `partials/error.html` z `code` i `detail`, status HTTP z rejestru (HTMX podmienia też odpowiedzi 4xx/5xx).

### 13.11 Migracja stare → nowe

**Python, wobec 2.1.1:**

| Było | Jest |
|---|---|
| `fetch_hydro_current(station_id=…)` (+`_async`) | `fetch_hydro_current(*, station=…)`; `HydroCurrentData.station_id` → `station_code`, nowe `latitude`, `longitude` |
| `fetch_synop(station_id=…, station_name=…)` (+`_async`) | `fetch_synop(*, station=…, station_name=…)`; `SynopData.station_id` → `station_code` |
| `fetch_warnings(warning_type="hydro")` (+`_async`) | `fetch_warnings(*, kind=None)` (brak = obie rodziny); `WarningData.warning_type` → `kind` |
| `fetch_pmaxtp(lat, lon, "AMP")` | `fetch_pmaxtp(lat, lon, method="AMP")`; wywołanie z nazwanym `method` bez zmian |
| — | `fetch_meteo_current(*, station=None)` (+`_async`) → `MeteoCurrentData` |
| `list_hydro_stations()`, `list_meteo_stations()` (+`_async`) → `HydroStation`, `MeteoStation` | `find_stations(kind="hydro")` / `find_stations(kind="meteo")` (+`find_stations_async`) → `StationListEntry` (`station_id` → `station_code`) |
| `get_hydro_stations_with_coords(include_all=True)` (+`_async`) | `fetch_hydro_states(main_only=False)` (+`_async`) → `HydroState` |
| `build_hydro_url(HydroInterval.DAILY, 2023)` | `archive_files("hydro/dobowe", years=2023)[0].url` (albo klucz `pl.imgw.hydro_daily`) |
| `build_hydro_url(HydroInterval.DAILY, 2023, month=13)` | `archive_files("pl.imgw.hydro_phenomena", years=2023)[0].url` |
| `build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 1995)` | `archive_files("meteo/miesieczne/synop", years=1995)[0].url` |
| `get_available_years(DataType.HYDRO, "dobowe")` | `get_dataset("hydro/dobowe").first_year` (górnej granicy brak, §2.1) |
| `DownloadURL` | `ArchiveFile` |
| `DataType`, `HydroInterval`, `HydroParam`, `MeteoInterval`, `MeteoSubtype` | klucze i aliasy zbiorów (`str`), `params` `H\|Q\|T` |
| `PMaXTPMethod` | `Literal["POT", "AMP"]` |
| `build_pmaxtp_url(method, latitude, longitude)` | `build_pmaxtp_url(latitude, longitude, *, method="POT")` |
| `build_api_url(endpoint, station_id=…, station_name=…)` | `build_api_url(endpoint, *, station=…, station_name=…)` |
| `IMGWError(message)` | `IMGWError(message, *, code=…, details=…)`; wywołanie z samym komunikatem bez zmian |

**Python, wobec niewydanego stanu 3.0.0 (ADR-001):**

| Było | Jest |
|---|---|
| `run_command(...)` → wynik funkcji | `CommandResult` (wynik w `.result`) |
| `check_command(...)` → `StorePlan` | `CommandResult` (`.check=True`, plan w `.result`) |
| `IMGWPlanStaleError` | usunięty; pozycja `stale_plan`, koperta `partial` |
| `IMGWStoreError` przy anulowaniu `write_archive`/`export_series` | `IMGWCancelledError` |
| `datasets()` | `datasets(*, kind=None)`; `DatasetDescriptor` z polami §13.4 |
| `get_dataset(klucz)` | klucz, slug albo alias legacy |
| `archive_files(..., years: Iterable[int])` | `years: YearsArg`, `months: MonthsArg`, nowe `params` |
| `check_store`/`sync_store(..., years: Iterable[int])` | `YearsArg`/`MonthsArg`; `check_store(..., plan=PLIK)` zapisuje plan |
| `check_pmaxtp`/`sync_pmaxtp`/`read_pmaxtp` z wymaganym `method` | `method="POT"` |
| `current_version(slot="archive:<server_path>")`, `series:<slug>`, `catalog:stations`, `pmaxtp:<M>:<x>_<y>` | gramatyka §13.7 |
| `read_series(version, *, station, variables)` | `read_series(version=None, *, root, dataset, station, variables=None, start, end)` |
| `export_series(version, *, station, path, variables, year_type, format)` | `export_series(version=None, *, root, dataset, station, variables=None, start, end, year_type, format, path=None)` → `Path` albo iterator linii |
| `run_command("store read", …)` | `export_archive(version, *, root, format, path)`; komenda `store export` |
| `run_command("series select", …)` | `select_series(root, *, dataset, stations, variables, years, year_type)` |
| `run_command("fetch hydro" / "fetch meteo", …)` → `Path` | `download_archives(dataset, *, years, months, params, output)` → `DownloadReport` |
| `StationCoverage.station`, `ProjectFile.station` | `station_code` |
| `OperationResult(slot, status, version, error)` | + `task`, `error_code`; `slot` według §13.7 |
| `StoreEntry.slot: str` | `str \| None` |
| `CommandOption` z `lat`/`lon` typu `str` | typy `float`, `date`, `object`; pola §13.9 |
| `DataCommand(name, description, options)` | + `function`, `check`, `result`, `method`, `requires`, `one_of`, `rules` |

**CLI:**

| Było | Jest |
|---|---|
| `imgw fetch hydro -i dobowe -y 2023 -m 1 [-p H] [-o KAT]` | `imgw datasets download -d hydro/dobowe -y 2023 -m 1 [--params H] [-o KAT]` (`-d` wymagane, bez domyślnego interwału) |
| `imgw fetch meteo -i miesieczne -s synop -y 2023 [-o KAT]` | `imgw datasets download -d meteo/miesieczne/synop -y 2023 [-o KAT]` |
| `imgw fetch current hydro\|meteo\|synop [-s ID] [-o PLIK]` | `imgw current hydro\|meteo\|synop [-s KOD]` (zapis: `> PLIK`) |
| `imgw fetch pmaxtp -m AMP --lat … --lon … [-o PLIK]` | `imgw pmaxtp fetch --method AMP --lat … --lon …` |
| `imgw fetch warnings -t meteo [-o PLIK]` | `imgw current warnings -k meteo` |
| `imgw list stations -t hydro -s Warsz -l 50` | `imgw stations find -k hydro -q Warsz --limit 50` |
| `imgw list datasets [-t hydro]` | `imgw datasets list [-k hydro]` |
| `imgw list intervals` | `imgw datasets list` (pole `legacy_alias`) |
| `imgw store check\|sync --dataset K` | `--datasets K` albo `-d K` |
| `imgw store read …` | `imgw store export …` |
| `imgw pmaxtp check\|sync\|read --method M` (wymagane) | opcjonalne, domyślnie `POT`; `--lat`/`--lon` to aliasy `--latitude`/`--longitude` |
| `imgw series export … --path P` (wymagane) | `--path` opcjonalne (bez niego CSV na stdout) |
| `--check` przy `store check`, `pmaxtp check`, `project check` | brak |
| stdout: surowy wynik, ścieżki bezwzględne | koperta `imgw-result/1`, ścieżki w magazynie względne do root |
| błąd: `Błąd: …` na stderr (komendy legacy: stdout), kod 1 | JSON na stderr, kod według §13.5; wynik `partial`/`failed` → 10/11 |

**REST:**

| Było | Jest |
|---|---|
| `GET /api/v1/hydro/stations`, `GET /api/v1/meteo/stations` (zaślepki), `GET /api/v1/hydro/stations/{station_id}` | `GET /api/v1/stations/find?kind=…&query=…` |
| `GET /api/v1/hydro/current?station_id=` | `GET /api/v1/current/hydro?station=` |
| `GET /api/v1/meteo/current?station_id=` | `GET /api/v1/current/meteo?station=` |
| `GET /api/v1/meteo/synop?station_id=&station_name=` | `GET /api/v1/current/synop?station=&station_name=` |
| — | `GET /api/v1/current/warnings`, `GET /api/v1/current/hydro-states` |
| `POST /api/v1/hydro/download-url`, `/hydro/download-urls`, `/meteo/download-url`, `/meteo/download-urls`; `GET /api/v1/download/url`, `/download/urls` | `GET /api/v1/datasets/files?dataset=…&years=…&months=…&params=…` |
| `GET /api/v1/download/datasets` | `GET /api/v1/datasets/list` |
| `GET /api/v1/pmaxtp/methods` | `GET /api/v1/commands/schema?command=pmaxtp%20fetch` (wyliczenie `method` z opisem) |
| `POST /api/v1/pmaxtp/url` | `GET /api/v1/pmaxtp/url` |
| `POST /api/v1/pmaxtp/data` (surowa odpowiedź IMGW) | `GET /api/v1/pmaxtp/fetch` (`PMaXTPResult`) |
| `GET /api/v1/store/entries` | `GET /api/v1/store/scan` |
| `POST /api/v1/store/check` | `GET /api/v1/store/check` |
| `POST /api/v1/store/sync` (409 `stale_plan`) | ta sama trasa; 200 + koperta `partial`; `?check=true` |
| `GET /api/v1/series/index` | `GET /api/v1/series/summary` |
| `GET /api/v1/series/{station}` | `GET /api/v1/series/read?station=…` |
| `POST /api/v1/series/export` (zapis tymczasowy, token) | `GET /api/v1/series/export` (strumień, bez tokenu) |
| `POST /api/v1/pmaxtp/store/sync` | `POST /api/v1/pmaxtp/sync` |
| — | `GET /api/v1/pmaxtp/check`, `GET /api/v1/pmaxtp/read`, `GET /api/v1/store/export`, `GET /api/v1/series/select`, `GET /api/v1/commands/schema` |
| `GET /map/stations` (web) | `GET /api/v1/current/hydro-states` |
| błędy `{"detail": …}`, 422 z listą pydantic, `{"code", "detail"}` | `application/problem+json` (§13.5) |
| kody `store_not_configured`, `store_root_invalid`, `user_locations_invalid` (503) | `store_unavailable` + `details.reason` |
| kody `writes_disabled`, `write_token_missing`, `invalid_api_key` (403) | `forbidden` + `details.reason` |
| kody `stale_plan` (409), `store_error` (500) | koperta `partial`; `store_unavailable` albo `internal_error` |

**Pola i pliki:**

| Było | Jest |
|---|---|
| REST `Station.id`, `HydroStation.station_id`, `HydroCurrentData.station_id`, `SynopData.station_id` | `station_code` |
| REST `DownloadURLResponse{url, filename, data_type, interval, year, month}` | `ArchiveFile{dataset, server_path, url, year, month, param, year_type, period_start, period_end}` |
| REST `HydroCurrentData{water_level, flow, temperature}` | model biblioteki `{water_level_cm, flow_m3s, water_temp_c, …}` |
| REST `MeteoCurrentData{temperature, wind_speed, humidity, precipitation}` | `MeteoCurrentData{air_temp_c, wind_speed_ms, humidity_percent, precipitation_10min_mm, …}` albo `SynopData` |
| `WarningData.warning_type`, REST `WarningData.type` | `kind` |
| `OperationResult.slot` `archives/versions/<katalog>/<stem>` lub `<zadanie>:<ścieżka>` | slot §13.7 + pole `task` |
| `StoreEntry.slot` `archive:<server_path>`, `series:<slug>`, `catalog:stations`, `pmaxtp:<M>:<x>_<y>` | slot §13.7 |
| `imgw-project.json` `files[].station` | `files[].station_code` |
| CSV użytkownika `station_code,lon,lat,source` | `station_code,latitude,longitude,source` |
| `data/hydro_stations_locations.csv` `id,X,Y` | `station_code,latitude,longitude` (ponownie `python -m imgwtools.reference_data`) |
| `data/hydro_stations_names.csv`, `data/meteo_stations_names.csv` i `Settings.hydro_stations_csv`/`meteo_stations_csv` | usunięte (czytała je tylko `imgw list stations`) |

### 13.12 Publiczne API

Dodane do `imgwtools.__all__`: `CommandResult`, `Page`, `DownloadItem`, `DownloadReport`, `ErrorCode`, `ErrorSpec`, `ERROR_CODES`, `IMGWCancelledError`, `HydroState`, `MeteoCurrentData`, `YearsArg`, `MonthsArg`, `command_schema`, `find_stations`, `find_stations_async`, `fetch_meteo_current`, `fetch_meteo_current_async`, `fetch_hydro_states`, `fetch_hydro_states_async`, `select_series`, `summarize_series`, `export_archive`, `download_archives` (funkcje magazynu także w `imgwtools.store`).

Usunięte (także z `imgwtools.urls`): `IMGWPlanStaleError`, `HydroStation`, `MeteoStation`, `list_hydro_stations`, `list_hydro_stations_async`, `list_meteo_stations`, `list_meteo_stations_async`, `get_hydro_stations_with_coords`, `get_hydro_stations_with_coords_async`, `build_hydro_url`, `build_meteo_url`, `get_available_years`, `DownloadURL`, `DataType`, `HydroInterval`, `HydroParam`, `MeteoInterval`, `MeteoSubtype`, `PMaXTPMethod`. Pozostałe nazwy bez zmian; zmienione podpisy — §13.8.
