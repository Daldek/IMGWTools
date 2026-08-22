# IMGWTools - Progress Tracker

## Aktualny Status

| Pole | Wartość |
|------|---------|
| **Wersja** | 2.1.1 |
| **Data** | 2026-07-06 |
| **Gałąź robocza** | slave (scalona do master) |
| **Python** | >=3.12 |

---

## Wydane wersje

| Wersja | Data | Zakres |
|--------|------|--------|
| v2.1.1 | 2026-07 | Parsery: auto-detekcja separatora/kodowania (UTF-8 BOM)/cudzysłowów; URL-e meteo zgodne z serwerem IMGW; zgodność z pyright; audyt dokumentacji |
| v2.1.0 | 2026-01 | Python 3.12+, modernizacja kodu (ruff fix), DEVELOPMENT_STANDARDS.md |
| v2.0.1 | 2026-01 | Fix import error (lazy load db module) |
| v2.0.0 | 2026-01 | Refaktoring API, nowa architektura |
| v1.0.0 | 2025-xx | Pierwsze stabilne wydanie |

---

## v2.1.1 — szczegóły wydania (2026-07-06)

### 🐛 Bugfix: obsługa niespójnych formatów archiwów IMGW w parserach (2026-07-05)

Archiwalne pliki CSV IMGW (`dane_hydrologiczne`) różnią się formatem między rocznikami w **trzech** aspektach. Parsery w `src/imgwtools/db/parsers.py` zakładały jeden format (średnik + CP1250), przez co większość roczników nie parsowała się wcale. Wszystkie trzy problemy naprawione:

1. **Separator** — większość roczników używa przecinka z cudzysłowami, część (np. 2023) średnika; niektóre pliki mają dodatkowy wiersz nagłówka z kodami kolumn. Zahardkodowany `delimiter=";"` powodował, że `parse_zip_file` **po cichu zwracał 0 rekordów** dla roczników przecinkowych. → helper `_detect_delimiter()` (per plik, z pierwszej niepustej linii; remis → średnik).
2. **Kodowanie** — standardem jest CP1250, ale `codz_2023.zip` (dobowe, plik roczny) jest w **UTF-8 z BOM**; parser rzucał `UnicodeDecodeError`. → helper `_decode_content()` (BOM → `utf-8-sig`; potem próba żądanego kodowania z fallbackiem UTF-8).
3. **Cudzysłowy** — w plikach dobowych i miesięcznych **2024** każda linia jest opakowana w zewnętrzny cudzysłów z podwojonymi cudzysłowami wewnątrz (`"149180020,CHAŁUPKI,...,""2024"",..."`), więc `csv.reader` widział jedno pole i parser po cichu zwracał 0 rekordów. → helper `_iter_rows()` (wiersz jednopolowy zawierający separator jest parsowany ponownie).

Wiodąca spacja w kodzie stacji i wiersz nagłówka są obsługiwane przez istniejące zabezpieczenia (`_safe_int`, `.strip().strip('"')`).

**Testy:** `tests/unit/test_parsers.py` — 28 testów (separator, kodowanie, cudzysłowy, end-to-end przez `parse_zip_file`). Po tej poprawce pakiet liczył 103 testy; docelowo dla całego wydania v2.1.1 jest ich **109** (patrz poprawka URL-i meteo niżej). `ruff check src/ tests/` i `ruff format --check` (zmienione pliki) — czysto; przy okazji naprawiono 13 zastanych błędów lint w starych plikach testowych (nieużywane importy, sortowanie importów).

**Weryfikacja na danych rzeczywistych (2026-07-05, liczby rekordów):**

| Plik | Format | Przed (2.1.0) | Po poprawce |
|------|--------|---------------|-------------|
| polr_Q_2020 | przecinek, CP1250 | 0 | 6007 |
| polr_Q_2023 | średnik, CP1250 | 6014 | 6014 |
| polr_Q_2024 | przecinek, CP1250, nagłówek | 0 | 6198 |
| mies_2019–2022 | przecinek, CP1250 | 0 | 29 802 – 30 171/rok |
| mies_2023 | średnik, CP1250 | 29 805 | 29 805 |
| mies_2024 | przecinek, CP1250, **linie w cudzysłowach** | 0 | 32 408 |
| codz_2020_01, codz_2022_06 | przecinek, CP1250 | 0 | 24 913 / 24 881 |
| codz_2023 | średnik, **UTF-8 z BOM** | `UnicodeDecodeError` | 301 994 |
| codz_2024 | przecinek, CP1250, **linie w cudzysłowach** | 0 | 326 845 |

**Pozostałe zmiany w ramach przygotowania wydania:**
- wersja podbita do **2.1.1** (`_version.py`, `pyproject.toml`); zaktualizowano `CLAUDE.md` (wersja, testy, notki o formacie CSV) i `README.md` (notka o formacie, liczby testów, pokrycie `db/parsers.py` 78%),
- `.gitignore`: dodano `.coverage`, `dist/`, `.python-version`, pliki bazy SQLite,
- naprawiono zastane błędy lint w `tests/` (ruff --fix).

**Status:** wydane w **v2.1.1** (patch — poprawki błędów, bez zmian publicznego API).

### 🔧 Typowanie: zgodność z Pylance/pyright (2026-07-05)

Pylance w VSC zgłaszał błędy w `db/parsers.py` (i szerzej). Weryfikacja `pyright` (silnik Pylance) na venv projektu potwierdziła: **136 błędów** w `src/`. Po poprawkach: **0 błędów**.

- **`Field(None, ...)` → `Field(default=None, ...)`** w 46 polach modeli pydantic (`models.py`, `db/models.py`, `api/schemas.py`, `stations.py`). Pyright nie rozpoznaje pozycyjnego defaultu przy przeciążeniach `Field` w pydantic 2.12 — pola opcjonalne wyglądały na wymagane (błędy „Arguments missing for parameters latitude, longitude"). Zmiana bez wpływu na runtime.
- **`db/parsers.py`**: jawne zawężanie typów — `not isinstance(content, str)` (obsługuje też bytearray/memoryview lepiej niż stary wariant), warunki `or` zamiast `all([...])` (pyright nie zawęża przez `all`). Usunięte błędy `int | None` i `memoryview.lstrip`.
- **`db/__init__.py`**: importy pod `TYPE_CHECKING` dla nazw ładowanych leniwie przez `__getattr__` — Pylance widzi symbole i podpowiada, runtime bez zmian (lazy loading zachowany).
- **`cli/db.py`**: zawężanie `isinstance` w gałęziach wyświetlania rekordów; **`api/routes/hydro.py`**: adnotacja `list[HydroDailyDataPoint | HydroMonthlyDataPoint]` dla `data_points` (inwariancja list).
- **`pyproject.toml`**: nowa sekcja `[tool.pyright]` (venvPath/venv + ignore dla legacy core); **`.vscode/settings.json`** ze wskazaniem interpretera `.venv` (bez niego Pylance analizuje pakiet ze starego globalnego pyenv 2.0.1).

**TODO (osobne zadanie, poza v2.1.1):** legacy moduły `core/imgw_api.py` (DEPRECATED), `core/imgw_datastore.py` mają martwe importy (`wget`, płaski `import imgw_api`); `core/imgw_spatial.py` usunięty 2026-08-22 i realne błędy Optional — są wyłączone z analizy pyright w `pyproject.toml`; docelowo do usunięcia w wydaniu minor.

### 🐛 Bugfix: URL-e meteo niezgodne z rzeczywistą strukturą serwera IMGW (2026-07-05)

Weryfikacja funkcjonalna GUI (serwer uruchomiony lokalnie, wszystkie trasy + formularze + statyki) wykazała, że strony, mapa, lista stacji i PMAXTP działają, ale **`build_meteo_url` generował martwe linki (404)** — struktura plików meteo na serwerze IMGW różni się od opisanej w dokumentacji. Zweryfikowano listingi katalogów na żywo:

| Interwał | Podtyp | Rzeczywiste pliki | Poprzednio generowane |
|---|---|---|---|
| miesieczne (k/o/s) | ≤2000 | **jeden plik na folder 5-letni** `{folder}_m_{x}.zip` | `{rok}_{x}.zip` → 404 |
| dobowe/terminowe | klimat, opad | `{rok}_{x}.zip` (≤2000), `{rok}_{mm}_{x}.zip` (2001+) | ✓ poprawne |
| dobowe/terminowe | synop | **pliki per stacja** `{folder}_{kod}_s.zip` | `{rok}_{mm}_s.zip` → 404 |
| terminowe | opad | **zbiór nie istnieje** | `{rok}_{mm}_o.zip` → 404 |

Dodatkowo siatki folderów 5-letnich różnią się na starcie per podtyp: klimat `1951_1955`, opad `1950_1955`, synop `1960_1965` (folder 6-letni).

**Poprawka (`core/url_builder.py`):**
- `_get_meteo_folder(year, subtype)` — siatka folderów zależna od podtypu,
- miesieczne: nazwa pliku `{folder}_m_{x}.zip` (obejmuje oba okresy),
- synop dobowe/terminowe, terminowe opad, synop <1960 → czytelny `ValueError` zamiast martwego linku (GUI pokazuje komunikat w liście błędów),
- GUI (`web/app.py`): deduplikacja linków (lata ≤2000 mapują się na wspólny plik 5-letni).

**Weryfikacja:** 6 nowych wzorców URL sprawdzonych HEAD-em na serwerach IMGW — wszystkie **200 OK** (m.in. `1996_2000_m_s.zip`, `1950_1955_m_o.zip`, `1960_1965_m_s.zip`). Formularz GUI: poprawne linki + komunikat błędu dla synop dobowych. Testy: `test_urls.py` 22→28 (**pełny pakiet: 109 passed**). Zaktualizowano opisy struktury meteo w README.md i CLAUDE.md.

### 📚 Audyt dokumentacji przed wydaniem (2026-07-05)

Pełny przegląd dokumentacji względem kodu (subagent + weryfikacja ręczna). Ujednolicono pod v2.1.1:
- wersja 2.1.1 wszędzie (usunięto zalegające 2.0.0 w `ARCHITECTURE.md`, 1.0.0 w `PRD.md`),
- liczba testów **109** i status testów spójne między README/CLAUDE/PRD/DEVELOPMENT_STANDARDS,
- `ARCHITECTURE.md` — zaktualizowana sekcja parsowania CSV (auto-detekcja separatora/kodowania/cudzysłowów),
- `README.md` — poprawione źródło danych mapy (`hydro-back.imgw.pl/map/stations/hydrologic`, wcześniej błędnie `danepubliczne.imgw.pl/api/data/hydro`),
- type checker `mypy` → `pyright` w `DEVELOPMENT_STANDARDS.md` i sekcji „Komendy”; próg pokrycia ujednolicony na 80% (`RULES.md`/`PRD.md`/`DEVELOPMENT_STANDARDS.md`); dodano `test_parsers.py` i gałąź `slave` do odpowiednich list.

**Stan końcowy v2.1.1:** 109 passed, `ruff check` czysto, `pyright` 0 błędów.

### 🚀 Finalizacja wydania (2026-07-06)

- Usunięto sekcję `[tool.mypy]` i zależność `mypy>=1.6` z `pyproject.toml` — projekt używa wyłącznie **pyright** (`[tool.pyright]`).
- Zbudowano świeże artefakty `dist/` dla **2.1.1** (`python -m build`, backend hatchling); usunięto stare koła 2.0.1.
- Zmiany scalone z gałęzi `slave` do `master`.

---

## Cross-Project Analysis (2026-01-21)

Przeprowadzono analizę integracji 4 repozytoriów: **Hydrograf**, **Hydrolog**, **Kartograf**, **IMGWTools**.

### Mapa zależności

```
HYDROGRAF (główna aplikacja)
    ├── IMGWTools (dane IMGW) ← TEN PROJEKT
    ├── Kartograf (dane GIS)
    └── Hydrolog (obliczenia hydrologiczne)
            ├── IMGWTools (wymagany) ← TEN PROJEKT
            └── Kartograf (opcjonalny)
```

### Rola IMGWTools

IMGWTools jest **biblioteką bazową** używaną przez:
- **Hydrograf** - bezpośrednio (dane IMGW, PMAXTP)
- **Hydrolog** - jako wymagana zależność (dane opadowe dla obliczeń hydrologicznych)

### Problemy wykryte w IMGWTools

| Problem | Status | Priorytet |
|---------|--------|-----------|
| Python `>=3.11` (inne projekty `>=3.12`) | ✅ Naprawione (v2.1.0) | - |
| Używa `ruff` (inne używają `black+flake8`) | 🟡 Informacyjnie | NISKI |
| Używa `hatchling` (inne używają `setuptools`) | 🟡 Informacyjnie | NISKI |
| Brak DEVELOPMENT_STANDARDS.md | ✅ Naprawione (v2.1.0) | - |

### Standardy kodu - porównanie

| Aspekt | IMGWTools | Hydrolog | Kartograf | Zgodność |
|--------|-----------|----------|-----------|----------|
| Python | >=3.12 | >=3.12 | >=3.12 | ✅ |
| Line length | 88 | 88 | 88 | ✅ |
| Formatter | ruff | black | black | ⚠️ |
| Build | hatchling | setuptools | setuptools | ⚠️ |

### Rekomendacje

1. ~~**[ROZWAŻYĆ]** Podnieść Python do `>=3.12` dla spójności z innymi projektami~~ ✅ Zrobione (v2.1.0)
2. ~~**[BACKLOG]** Utworzyć DEVELOPMENT_STANDARDS.md (skopiować format z Hydrolog)~~ ✅ Zrobione (v2.1.0)
3. **[INFO]** Używanie `ruff` zamiast `black+flake8` jest OK (nowoczesne podejście)

### Pełna dokumentacja

Szczegółowa analiza cross-project: `Hydrograf/docs/CROSS_PROJECT_ANALYSIS.md`

---

## Funkcjonalności

### Zaimplementowane

- ✅ CLI (`imgw` command)
- ✅ REST API (FastAPI)
- ✅ Web GUI (HTMX + Jinja2)
- ✅ PMAXTP data
- ✅ Current hydro/meteo/synop data
- ✅ Archive data download
- ✅ Warnings
- ✅ SQLite cache (optional)

### Planowane

- 📋 API key enforcement
- 📋 Per-key rate limiting
- 📋 GeoJSON export
- 📋 Data charts
- 📋 **Lepsze nazewnictwo KS/SG/RB w PMaXTPData** (patrz sekcja poniżej)

---

## TODO: Poprawa czytelności PMaXTPData (KS/SG/RB)

**Kontekst:** Skróty KS, SG, RB w odpowiedzi API PMAXTP mogą być mylące. Łatwo pomylić górną granicę przedziału ufności (SG) z właściwą wartością kwantyla (KS), co prowadzi do błędnych obliczeń hydrologicznych.

| Symbol | Znaczenie | Zastosowanie |
|--------|-----------|--------------|
| **KS** | Kwantyle (estymata punktowa) | Wartość projektowa (domyślna) |
| **SG** | Górna granica przedziału ufności | Obliczenia konserwatywne |
| **RB** | Błędy estymacji | Analiza niepewności |

### Propozycje zmian

**1. Aliasy dla lepszej czytelności:**
```python
@property
def quantiles(self) -> dict:
    """Alias for ks (precipitation quantiles)."""
    return self.ks

@property
def upper_bounds(self) -> dict:
    """Alias for sg (upper confidence bounds)."""
    return self.sg

@property
def errors(self) -> dict:
    """Alias for rb (estimation errors)."""
    return self.rb
```

**2. Metoda dla wartości projektowej z opcją konserwatywną:**
```python
def get_design_precipitation(
    self,
    duration_minutes: int,
    probability_percent: int,
    conservative: bool = False
) -> float | None:
    """Get design precipitation value for engineering design.

    Args:
        duration_minutes: Duration in minutes
        probability_percent: Probability in percent
        conservative: If True, return upper confidence bound (SG)
                     If False, return quantile estimate (KS) - default

    Returns:
        Precipitation [mm] for engineering design
    """
    if conservative:
        return self.get_confidence_bound(duration_minutes, probability_percent)
    return self.get_precipitation(duration_minutes, probability_percent)
```

**3. Rozszerzenie README** z tabelą znaczeń KS/SG/RB.

**Uwaga:** Istniejąca metoda `get_precipitation()` już zwraca prawidłową wartość (KS), ale bezpośredni dostęp do atrybutów `data.ks`, `data.sg`, `data.rb` może prowadzić do pomyłek.

---

## Komendy

```bash
# Aktywacja środowiska
source .venv/bin/activate

# Testy
pytest tests/ -v

# Linting
ruff check src/imgwtools/
ruff format src/imgwtools/

# Type checking (config: [tool.pyright] w pyproject.toml)
npx pyright src/imgwtools/
```

---

## Git workflow

- **master** - główna gałąź (stabilna)
- **slave** - gałąź rozwojowa (obecnie = master)

---

**Ostatnia aktualizacja:** 2026-07-05
