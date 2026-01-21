# IMGWTools - Progress Tracker

## Aktualny Status

| Pole | Wartość |
|------|---------|
| **Wersja** | 2.1.0 |
| **Data** | 2026-01-21 |
| **Gałąź robocza** | master (=slave) |
| **Python** | >=3.12 |

---

## Wydane wersje

| Wersja | Data | Zakres |
|--------|------|--------|
| v2.1.0 | 2026-01 | Python 3.12+, modernizacja kodu (ruff fix), DEVELOPMENT_STANDARDS.md |
| v2.0.1 | 2026-01 | Fix import error (lazy load db module) |
| v2.0.0 | 2026-01 | Refaktoring API, nowa architektura |
| v1.0.0 | 2025-xx | Pierwsze stabilne wydanie |

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

# Type checking
mypy src/imgwtools/
```

---

## Git workflow

- **master** - główna gałąź (stabilna)
- **slave** - gałąź rozwojowa (obecnie = master)

---

**Ostatnia aktualizacja:** 2026-01-21
