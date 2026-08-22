# DEVELOPMENT_STANDARDS.md - Standardy Kodowania

## IMGWTools - Biblioteka danych IMGW

**Wersja:** 1.1
**Data:** 2026-08-22

---

## 1. Nazewnictwo

### 1.1 Python

```python
# Zmienne i funkcje: snake_case
station_id = "149180020"
water_level_cm = 150

def fetch_hydro_current(station_id: str | None = None) -> list[HydroCurrentData]:
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
| `fetch_*` | Pobieranie danych z API | `fetch_hydro_current()` |
| `download_*` | Pobieranie archiwów (ZIP) | `download_hydro_data()` |
| `list_*` | Listowanie zasobów | `list_hydro_stations()` |
| `build_*_url` | Generowanie URL | `build_hydro_url()` |
| `parse_*` | Parsowanie danych | `parse_daily_csv()` |
| `*Data` | Model danych | `HydroCurrentData` |
| `*Result` | Wynik z metadanymi | `PMaXTPResult` |
| `*Error` | Wyjątek | `IMGWConnectionError` |

---

## 2. Formatowanie

### 2.1 Ruff (88 znaków)

```python
# Maksymalna długość linii: 88 znaków
# Wcięcia: 4 spacje
# Formatter: ruff format

# DOBRZE
def build_hydro_url(
    interval: str,
    year: int,
    month: int | None = None,
    param: str | None = None,
) -> str:
    pass

# ŹLE (za długa linia)
def build_hydro_url(interval: str, year: int, month: int | None = None, param: str | None = None) -> str:
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
    station_id: str | None = None,
    *,
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
    method: Literal["POT", "AMP"] = "POT",
    *,
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
    station_id : str
        IMGW station identifier.
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
    >>> data = fetch_hydro_current(station_id="149180020")[0]
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
│   ├── test_models.py      # Modele danych
│   ├── test_fetch.py       # Funkcje fetch_*
│   ├── test_parsers.py     # Parsery CSV (separator/kodowanie/cudzysłowy)
│   ├── test_stations.py    # Funkcje list_*
│   └── test_urls.py        # Funkcje build_*_url
└── conftest.py             # Shared fixtures

# Planowane (jeszcze nieutworzone):
# tests/integration/test_api.py  - testy endpointów API
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

def test_build_hydro_url_daily_with_month():
    """Test daily hydro URL generation with month parameter."""
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

Stan faktyczny: **23%** (zmierzone 2026-08-22, 109 testów).
Cel docelowy: **80%** - bramka `--cov-fail-under` nie jest jeszcze włączona
w konfiguracji projektu.

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
from imgwtools.core.url_builder import build_pmaxtp_url
```

---

## 8. Error Handling

### 8.1 Hierarchia wyjątków

```python
# imgwtools/exceptions.py

class IMGWError(Exception):
    """Base exception for IMGWTools."""
    pass

class IMGWConnectionError(IMGWError):
    """Connection or timeout error."""
    pass

class IMGWDataError(IMGWError):
    """Data parsing or format error."""
    pass

class IMGWValidationError(IMGWError):
    """Input validation error."""
    pass
```

### 8.2 Walidacja na wejściu

```python
def fetch_pmaxtp(
    latitude: float,
    longitude: float,
    method: Literal["POT", "AMP"] = "POT",
) -> PMaXTPResult:
    """Fetch PMAXTP data."""
    # Walidacja współrzędnych (Polska: lat 49-55, lon 14-24.5)
    if not (49.0 <= latitude <= 55.0 and 14.0 <= longitude <= 24.5):
        raise IMGWValidationError(
            f"Coordinates ({latitude}, {longitude}) are outside Poland"
        )

    if method not in ("POT", "AMP"):
        raise IMGWValidationError(f"Invalid method: {method}")

    # ...
```

---

## 9. Komendy

```bash
# Testy
pytest tests/ -v

# Testy z pokryciem
pytest tests/ --cov=imgwtools --cov-report=html

# Formatowanie
ruff format src/imgwtools/

# Sprawdzenie formatowania
ruff format src/imgwtools/ --check

# Linting
ruff check src/imgwtools/

# Type checking (config: [tool.pyright] w pyproject.toml)
npx pyright src/imgwtools/
```

---

## 10. Checklist przed commitem

- [ ] Testy przechodzą (`pytest`)
- [ ] Pokrycie nie spada (`pytest --cov`; stan 23%, cel docelowy 80%)
- [ ] Formatowanie OK (`ruff format --check`)
- [ ] Linting OK (`ruff check`)
- [ ] Type hints OK (`pyright`)
- [ ] Docstrings NumPy dla publicznych funkcji/klas (wymuszane przez ruff `D`)
- [ ] PROGRESS.md zaktualizowany

---

**Wersja dokumentu:** 1.1
**Data ostatniej aktualizacji:** 2026-08-22
