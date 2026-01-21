# DEVELOPMENT_STANDARDS.md - Standardy Kodowania

## IMGWTools - Biblioteka danych IMGW

**Wersja:** 1.0
**Data:** 2026-01-21

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

from typing import Optional

import httpx
from pydantic import BaseModel

from imgwtools.models import HydroCurrentData
from imgwtools.exceptions import IMGWError
```

---

## 3. Type Hints

### 3.1 Wymagane wszędzie

```python
from typing import Optional

def fetch_hydro_current(
    station_id: str | None = None,
    timeout: int = 30,
) -> list[HydroCurrentData]:
    """Fetch current hydro data."""
    pass

class PMaXTPData:
    ks: list[float]  # Kwantyle opadu [mm]
    sg: list[float]  # Górne granice przedziału ufności [mm]
    rb: list[float]  # Błędy estymacji [mm]
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
    lat: float,
    lon: float,
    method: str = "POT",
) -> PMaXTPResult:
    """
    Fetch PMAXTP precipitation data for given coordinates.

    Parameters
    ----------
    lat : float
        Latitude in WGS84 (49.0 - 55.0 for Poland).
    lon : float
        Longitude in WGS84 (14.0 - 24.0 for Poland).
    method : str, optional
        Calculation method ('POT' or 'AMP'), by default 'POT'.

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
    >>> precip = result.data.get_precipitation(duration=15, probability=0.5)
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
    water_level_cm : float | None
        Water level in centimeters.
    discharge_m3s : float | None
        Discharge in m³/s.

    Attributes
    ----------
    measurement_date : datetime
        Date and time of measurement.

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
│   ├── test_stations.py    # Funkcje list_*
│   └── test_urls.py        # Funkcje build_*_url
├── integration/
│   └── test_api.py         # Testy endpointów API
└── conftest.py             # Shared fixtures
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
    data = PMaXTPData(ks=[10.0, 20.0], sg=[12.0, 24.0], rb=[1.0, 2.0])

    # Act
    result = data.get_precipitation(duration=15, probability=0.5)

    # Assert
    assert result == 10.0
```

### 5.4 Pokrycie

```bash
# Wymagane: > 70%
pytest tests/ --cov=imgwtools --cov-report=html --cov-fail-under=70
```

---

## 6. Git Workflow

### 6.1 Branching

```
master        # Stabilna wersja (wydania)
slave         # Aktywny rozwój (DOMYŚLNA GAŁĄŹ ROBOCZA)
feature/*     # Nowe funkcjonalności
fix/*         # Poprawki błędów
```

**WAŻNE:** Cały rozwój kodu odbywa się na gałęzi `slave`.
Gałąź `master` otrzymuje tylko merge z `slave` przy wydaniach.

### 6.2 Tagowanie

```bash
# Tworzenie tagu wersji
git tag -a v2.0.1 -m "Release v2.0.1: Python 3.12 compatibility"
git push origin v2.0.1
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
def fetch_pmaxtp(lat: float, lon: float, method: str = "POT") -> PMaXTPResult:
    """Fetch PMAXTP data."""
    # Walidacja współrzędnych (Polska: lat 49-55, lon 14-24)
    if not (49.0 <= lat <= 55.0 and 14.0 <= lon <= 24.0):
        raise IMGWValidationError(
            f"Coordinates ({lat}, {lon}) are outside Poland"
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

# Type checking
mypy src/imgwtools/
```

---

## 10. Checklist przed commitem

- [ ] Testy przechodzą (`pytest`)
- [ ] Pokrycie > 70% (`pytest --cov`)
- [ ] Formatowanie OK (`ruff format --check`)
- [ ] Linting OK (`ruff check`)
- [ ] Type hints OK (`mypy`)
- [ ] Docstrings dla publicznych funkcji/klas
- [ ] PROGRESS.md zaktualizowany

---

**Wersja dokumentu:** 1.0
**Data ostatniej aktualizacji:** 2026-01-21
