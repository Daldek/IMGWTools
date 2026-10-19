# DEVELOPMENT_STANDARDS.md - Standardy Kodowania

## IMGWTools - Biblioteka danych IMGW

**Wersja:** 1.3
**Data:** 2026-10-19

---

## 1. Nazewnictwo

### 1.1 Python

```python
# Zmienne i funkcje: snake_case
station_code = "149180020"
water_level_cm = 150

def fetch_hydro_current(*, station: str | None = None) -> list[HydroCurrentData]:
    pass

# Klasy: PascalCase
class HydroCurrentData:
    pass

class PMaXTPResult:
    pass

# Stałe: UPPER_SNAKE_CASE
IMGW_ENCODING = "cp1250"
DEFAULT_TIMEOUT = 30
```

### 1.2 Konwencje nazewnicze

| Wzorzec | Znaczenie | Przykład |
|---------|-----------|----------|
| `fetch_*` | Odczyt na żywo z API IMGW | `fetch_hydro_current()`, `fetch_hydro_states()` |
| `find_*` | Wyszukiwanie z frazą i filtrami | `find_stations()` |
| `download_*` | Pobieranie archiwów (bajty albo pliki) | `download_archives()`, `download_hydro_data()` |
| `archive_files`, `datasets`, `get_dataset` | Rejestr zbiorów (offline) | `archive_files("hydro/dobowe", years=2023)` |
| `build_*_url` | URL endpointu API (nie archiwum) | `build_pmaxtp_url()`, `build_api_url()` |
| `check_*` | Bliźniak operacji zapisu: plan bez zapisu i bez GET treści | `check_store()` |
| `sync_*`, `build_*`, `init_*` | Zapis do magazynu | `sync_store()`, `build_series()` |
| `read_*`, `select_*`, `summarize_*`, `export_*` | Odczyt magazynu (offline) | `read_series()`, `summarize_series()` |
| `parse_*` | Parsowanie danych | `parse_daily_csv()` |
| `*Data` | Model danych | `HydroCurrentData` |
| `*Result`, `*Report` | Wynik z metadanymi, raport operacji | `PMaXTPResult`, `SyncReport` |
| `*Error` | Wyjątek | `IMGWConnectionError` |

### 1.3 Nazwy opcji (ADR-002, spec §13.1–§13.2)

- Nazwa opcji = nazwa parametru funkcji = pole JSON (query/ciało REST, wyniki); flaga CLI =
  `--` + nazwa z `_` zamienionym na `-`. Jedna nazwa ma w całym katalogu jedno znaczenie i jeden typ.
- `station` — jeden kod stacji (argument), `stations` — lista kodów, `station_code` — pole
  wyniku; kod stacji to zawsze `str` (9 cyfr IMGW-PIB albo identyfikator WIGOS ČHMÚ według
  `STATION_CODE_PATTERN`; gramatykę sprawdza się według dostawcy zbioru).
- `provider` — identyfikator dostawcy z rejestru (`IMGW-PIB`, `CHMI`); w funkcjach i komendach
  listowych brak = wszyscy dostawcy, w funkcjach jednego obiektu (`build_catalog`,
  `read_station_list`) domyślnie `IMGW-PIB`. Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`.
- `dataset` (jeden zbiór) / `datasets` (lista) przyjmują klucz, slug albo alias legacy;
  wyniki i sloty podają zawsze pełny klucz (`pl.imgw.hydro_daily`).
- `years`/`months` przyjmują `YearsArg`/`MonthsArg` (`2024`, `"2020-2023"`, `"2020,2022"`,
  listy); jedyny parser to `parse_years`/`parse_months` z `imgwtools.datasets`.
- `latitude`/`longitude` (nie `lat`/`lon`; CLI ma aliasy `--lat`/`--lon`), `kind`, `query`,
  `root`, `path` (plik wynikowy), `output` (katalog), `method` (PMAXTP, domyślnie `"POT"`).
- Pierwszy obiekt (`root`, `version`, `dataset`, `command`) może być pozycyjny; wszystkie dalsze
  argumenty są keyword-only.
- Nowa operacja to nowa komenda katalogu (`commands._CATALOG`) wywołująca dokładnie jedną
  funkcję z `imgwtools.__all__`; CLI, REST i narzędzia MCP powstają z katalogu, bez ręcznych
  komend, tras i narzędzi.
- Teksty dla człowieka (komunikaty, `detail`, pomoc) są domyślnie po polsku; kody, nazwy
  i docstringi po angielsku (ADR-004 D3).
- Teksty katalogu i rejestrów mają wariant angielski: opis komendy (`description_en`), pomoc
  opcji (`help_en`), reguły (`rules_en`, te same pozycje co `rules`), opisy grup
  (`_GROUPS_EN`), tytuły błędów (`ErrorSpec.title_en`) i zbiorów (`DatasetDescriptor.title_en`).
  Nowy tekst katalogu dodaje się zawsze w parze polski + angielski (testy wymagają
  niepustego wariantu i jednoznacznego odwzorowania pomocy PL ↔ EN). Język wybiera się
  jawnie (`lang`, `IMGW_LANG`, `Accept-Language`, `imgw mcp --lang`); bez wariantu
  angielskiego zostają `detail`, `Notice.text`, postęp, CSV, web GUI i OpenAPI. Język nie
  zmienia kontraktu (te same właściwości, typy i reguły w obu schematach).
- Komenda deklaruje skutki: `DataCommand.writes` (`none`/`add`/`replace`), `network`
  i `CommandOption.writes` opcji zapisującej; komenda zapisująca ma bliźniaka `check`.
- Zmiana tekstów katalogu, rejestru zbiorów, dostawców albo kodów błędów lub szablonów
  `src/imgwtools/_data/agents/` regeneruje w tej samej zmianie pliki pochodne `AGENTS.md`
  i `llms.txt` (`imgw commands guide --format agents|llms --lang pl --path …`); test dryfu
  porównuje bajty.

---

## 2. Formatowanie

### 2.1 Ruff (88 znaków)

```python
# Maksymalna długość linii: 88 znaków
# Wcięcia: 4 spacje
# Formatter: ruff format

# DOBRZE
def archive_files(
    dataset: str,
    /,
    *,
    years: YearsArg,
    months: MonthsArg | None = None,
) -> tuple[ArchiveFile, ...]:
    pass

# ŹLE (za długa linia)
def archive_files(dataset: str, /, *, years: YearsArg, months: MonthsArg | None = None) -> tuple[ArchiveFile, ...]:
    pass
```

### 2.2 Importy

```python
# Kolejność: stdlib → third-party → local
# Alfabetycznie w grupach
# Puste linie między grupami

from pathlib import Path

import httpx
from pydantic import BaseModel

from imgwtools.models import HydroCurrentData
from imgwtools.exceptions import IMGWError
```

---

## 3. Type Hints

### 3.1 Wymagane wszędzie

```python
def fetch_hydro_current(
    *,
    station: str | None = None,
    timeout: float = 30.0,
) -> list[HydroCurrentData]:
    """Fetch current hydro data."""
    pass

class PMaXTPData:
    # Zagnieżdżone słowniki: {czas_trwania: {prawdopodobieństwo: wartość}}
    ks: dict[str, dict[str, float]]  # Kwantyle opadu [mm]
    sg: dict[str, dict[str, float]]  # Górne granice przedziału ufności [mm]
    rb: dict[str, dict[str, float]]  # Błędy estymacji [mm]
```

### 3.2 Python 3.12+ style

```python
# Używaj nowoczesnej składni (bez `from __future__ import annotations`)
def process(items: list[str]) -> dict[str, int]:
    pass

# Union type z |
def get_station(id: str | int | None = None) -> Station | None:
    pass
```

---

## 4. Docstrings (NumPy Style, English)

### 4.1 Funkcje

```python
def fetch_pmaxtp(
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
    timeout: float = DEFAULT_TIMEOUT,
    validate_coords: bool = True,
) -> PMaXTPResult:
    """
    Fetch PMAXTP precipitation data for given coordinates.

    Parameters
    ----------
    latitude : float
        Latitude in WGS84 (49.0 - 55.0 for Poland).
    longitude : float
        Longitude in WGS84 (14.0 - 24.5 for Poland).
    method : {"POT", "AMP"}, optional
        Calculation method, by default "POT".
    timeout : float, optional
        Request timeout in seconds.
    validate_coords : bool, optional
        Whether to validate coordinates are within Poland.

    Returns
    -------
    PMaXTPResult
        PMAXTP data with precipitation quantiles.

    Raises
    ------
    IMGWValidationError
        If coordinates are outside Poland.
    IMGWConnectionError
        If connection to IMGW API fails.

    Examples
    --------
    >>> result = fetch_pmaxtp(52.23, 21.01)
    >>> precip = result.data.get_precipitation(15, 50)
    """
    pass
```

### 4.2 Klasy

```python
class HydroCurrentData:
    """
    Current hydrological measurement data.

    Parameters
    ----------
    station_code : str
        IMGW station code (nine digits).
    station_name : str
        Station name.
    water_level_cm : float or None
        Water level in centimeters.
    flow_m3s : float or None
        Flow in m3/s.

    Attributes
    ----------
    water_level_date : str or None
        Date and time of the water level measurement.

    Examples
    --------
    >>> data = fetch_hydro_current(station="149180020")[0]
    >>> print(f"{data.station_name}: {data.water_level_cm} cm")
    """
    pass
```

---

## 5. Testowanie

### 5.1 Struktura testów

```
tests/
├── unit/
│   ├── test_models.py, test_fetch.py, test_fetch_live.py   # Modele, fetch_* (respx)
│   ├── test_parsers.py, test_parsing_chmi.py   # Parsery IMGW-PIB (separator/kodowanie/cudzysłowy) i ČHMÚ
│   ├── test_stations*.py    # find_stations (IMGW-PIB, ČHMÚ)
│   ├── test_urls.py         # build_pmaxtp_url, build_api_url
│   ├── test_datasets*.py    # Rejestr dostawców i zbiorów, archive_files
│   ├── test_store_*.py      # Magazyn wersjonowany (także *_chmi, content)
│   ├── test_commands*.py, test_command_schema.py   # Katalog komend
│   ├── test_catalog_effects.py, test_catalog_i18n.py  # Skutki komend, opisy angielskie
│   ├── test_agent_guide.py  # AGENTS.md i llms.txt (test dryfu)
│   ├── test_mcp_*.py        # Serwer MCP (narzędzia, wywołania, stdio, /mcp)
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py  # Adaptery CLI, REST i web
│   └── test_public_store_api.py                   # __all__ = spec §13.12 + ČHMÚ + agent_guide
├── contract/                # Kontrakt magazynu, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19)
├── live/                    # Regresja na żywo IMGW-PIB i ČHMÚ (tylko z IMGW_LIVE=1)
├── fixtures/                # Syntetyczne archiwa, listingi, nagrania, złote eksporty
└── conftest.py              # Shared fixtures
```

### 5.2 Nazewnictwo testów

```python
# test_<moduł>_<funkcja>_<scenariusz>

def test_fetch_pmaxtp_valid_coordinates():
    """Test PMAXTP fetch for valid Polish coordinates."""
    pass

def test_fetch_pmaxtp_outside_poland_raises():
    """Test that coordinates outside Poland raise validation error."""
    pass

def test_archive_files_daily_with_month():
    """Test daily hydro archive files for a selected month."""
    pass
```

### 5.3 AAA Pattern

```python
def test_pmaxtp_get_precipitation():
    # Arrange
    data = PMaXTPData(
        ks={"15": {"50": 10.0}},
        sg={"15": {"50": 12.0}},
        rb={"15": {"50": 1.0}},
    )

    # Act
    result = data.get_precipitation(15, 50)

    # Assert
    assert result == 10.0
```

### 5.4 Pokrycie

Stan faktyczny: **2208 testów** (2026-10-19, `pytest --collect-only`; 2129 offline, 79 na żywo z `IMGW_LIVE=1`); ostatni pomiar
pokrycia: **93%** (2026-10-18, 998 testów, przed zmianami ADR-002). Cel docelowy: **80%**
— bramka `--cov-fail-under` nie jest jeszcze włączona w konfiguracji projektu.

```bash
pytest tests/ --cov=imgwtools --cov-report=html

# Docelowo, po osiągnięciu progu:
# pytest tests/ --cov=imgwtools --cov-report=html --cov-fail-under=80
```

---

## 6. Git Workflow

### 6.1 Branching

```
master        # Stabilna wersja (wydania)
slave         # Aktywny rozwój (DOMYŚLNA GAŁĄŹ ROBOCZA)
feature/*     # Nowe funkcjonalności
hotfix/*      # Pilne poprawki błędów
```

**WAŻNE:** Cały rozwój kodu odbywa się na gałęzi `slave`.
Gałąź `master` otrzymuje tylko merge z `slave` przy wydaniach.

### 6.2 Tagowanie

```bash
# Tworzenie tagu wersji
git tag -a v2.2.0 -m "Release v2.2.0: licencja, dane referencyjne, usunięcie legacy"
git push origin v2.2.0
```

### 6.3 Conventional Commits

```bash
# Format
<type>(<scope>): <description>

# Typy
feat     # Nowa funkcjonalność
fix      # Poprawka błędu
docs     # Dokumentacja
test     # Testy
refactor # Refaktoryzacja
chore    # Inne (config, deps)

# Przykłady
feat(api): add GeoJSON export endpoint
fix(fetch): handle timeout in hydro_current
docs(readme): update installation instructions
test(models): add tests for PMaXTPData
```

---

## 7. Struktura modułów

### 7.1 Public API w `__init__.py`

```python
# imgwtools/__init__.py
"""IMGWTools - Python library for IMGW public data."""

from imgwtools.fetch import (
    fetch_pmaxtp,
    fetch_hydro_current,
    fetch_synop,
    fetch_warnings,
)
from imgwtools.models import (
    PMaXTPData,
    PMaXTPResult,
    HydroCurrentData,
)
from imgwtools.exceptions import (
    IMGWError,
    IMGWConnectionError,
)

__all__ = [
    "fetch_pmaxtp",
    "fetch_hydro_current",
    # ...
]
```

### 7.2 Eksportuj tylko publiczne API

```python
# DOBRZE - import z głównego modułu
from imgwtools import fetch_pmaxtp, PMaXTPData

# Unikaj - import z wewnętrznego modułu
from imgwtools._jsonable import jsonable
```

---

## 8. Error Handling

### 8.1 Hierarchia wyjątków i kody

Każdy `IMGWError` ma `code` z zamkniętego rejestru `ERROR_CODES` (`imgwtools.exceptions`,
spec §13.5), polski komunikat (`detail` = `str(e)`) i `details` zgodne z JSON. Klasa ma kod
domyślny; miejsce zgłoszenia może podać inny zarejestrowany kod przez `code=`. Rejestr
mapuje kod na tytuł, kod wyjścia CLI i status HTTP — adaptery nie mają własnych map.

| Klasa | Kod domyślny | Typowe inne kody |
|---|---|---|
| `IMGWError` | `internal_error` | — |
| `IMGWValidationError` | `validation_error` | — |
| `IMGWConnectionError` | `source_unavailable` | — |
| `IMGWDataError` | `data_error` | `io_error` (nieczytelny plik) |
| `IMGWStoreError` | `store_unavailable` | `not_found` (brak wersji, sidecara, szeregu), `validation_error` (dowiązanie w ścieżce) |
| `IMGWStoreConflictError` | `conflict` | `details.reason`: `path_conflict`, `not_atomic`, `locked`, … |
| `IMGWStoreDependencyError` | `missing_dependency` | — |
| `IMGWProjectError` | `validation_error` | `not_found`, `conflict`, `io_error` |
| `IMGWCancelledError` | `cancelled` | — |

Zasady:

- Rejestr jest zamknięty: nie dodawaj kodów; wybierz istniejący i doprecyzuj go w `details`
  (`reason`).
- Błąd opcji zawsze ma `details.option` (nazwa opcji, §1.3), a gdy to pomaga — `value`
  i `allowed`.
- Błędy sieci przechodzą przez wspólne `_source_error` (`details`: `url`, `reason`
  `timeout|network|http_status`, `status`); nie zgłaszaj surowych wyjątków `httpx`.
- Anulowanie (`cancel()`) zgłasza `IMGWCancelledError`, nigdy `IMGWStoreError`.
- Porażka jednej pozycji długiej operacji (`sync_store`, `download_archives`, projekt) to wpis
  raportu ze `status="failed"` i `error_code`, nie wyjątek; koperta dostaje `partial`/`failed`.
- `OSError` przy zapisie/odczycie plików kończy się kodem `io_error` (polski powód,
  `details.path`).

### 8.2 Walidacja na wejściu

```python
def _validate_poland_coords(latitude: float, longitude: float) -> None:
    """Validate that coordinates are numbers within the Poland bounds box."""
    for option, name, value, low, high in (
        ("latitude", "Szerokość", latitude, POLAND_LAT_MIN, POLAND_LAT_MAX),
        ("longitude", "Długość", longitude, POLAND_LON_MIN, POLAND_LON_MAX),
    ):
        if not low <= value <= high:
            raise IMGWValidationError(
                f"{name} geograficzna {value!r} poza zakresem Polski ({low}–{high})",
                details={"option": option, "value": value},
            )
```

Opcje komend waliduje jedno miejsce — `validate_command` (typy, wzorce, wyliczenia, reguły
`x-imgw.rules`); funkcje publiczne sprawdzają swoje argumenty tymi samymi komunikatami.

---

## 9. Komendy

```bash
# Testy (zawsze przez venv projektu)
.venv/bin/python -m pytest

# Testy z pokryciem
.venv/bin/python -m pytest --cov=imgwtools --cov-report=html

# Formatowanie
.venv/bin/ruff format src/ tests/

# Sprawdzenie formatowania
.venv/bin/ruff format --check src/ tests/

# Linting
.venv/bin/ruff check src/ tests/

# Type checking (config: [tool.pyright] w pyproject.toml)
npx -y pyright src/imgwtools/
```

---

## 10. Checklist przed commitem

- [ ] Testy przechodzą (`pytest`)
- [ ] Pokrycie nie spada (`pytest --cov`; ostatni pomiar 93%, cel docelowy 80%)
- [ ] Formatowanie OK (`ruff format --check`)
- [ ] Linting OK (`ruff check`)
- [ ] Type hints OK (`pyright`)
- [ ] Docstrings NumPy dla publicznych funkcji/klas (wymuszane przez ruff `D`)
- [ ] PROGRESS.md zaktualizowany

---

**Wersja dokumentu:** 1.3
**Data ostatniej aktualizacji:** 2026-10-19
