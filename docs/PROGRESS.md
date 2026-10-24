# IMGWTools - Progress Tracker

Stan bieżący projektu (norma Nogat 2.1, DOC-6.1). Historia wydań, analiza cross-project, zamknięte pozycje backlogu i notatki robocze: [docs/HISTORY.md](HISTORY.md). Pełna lista zmian: [CHANGELOG.md](CHANGELOG.md).

## Status

| Pole | Wartość |
|------|---------|
| **Wersja** | 3.0.0 |
| **Data** | 2026-10-19 |
| **Gałąź robocza** | `chore/nogat-2.1` (od `fix/archiwista-compat-2`: dostosowanie do standardu Nogat 2.1, bez pushu); wcześniej `fix/archiwista-compat-2` (od `slave` `0d98f3b`: poprawki zgodności z Archiwistą przed tagiem 3.0.0), `feature/chmi-agents` (dostawca ČHMÚ ADR-003, wsparcie agentów AI ADR-004) i `feature/versioned-store` (magazyn ADR-001, spójne interfejsy ADR-002, otwarte dziedziny `/1` ADR-003 C01) |
| **Python** | >=3.12 |

| Komponent | Stan | Uwagi |
|-----------|------|-------|
| Wersjonowany magazyn danych (ADR-001) | done (3.0.0) | lokalny, odbudowywalny indeks magazynu: planned (ADR-001 D2) |
| Jeden katalog komend, CLI i REST (ADR-002) | done (3.0.0) | CLI i REST generowane z katalogu |
| Dostawca ČHMÚ (ADR-003) | done (3.0.0) | pytania do ČHMÚ i potwierdzenia Archiwisty: otwarte (poniżej) |
| Wsparcie agentów AI, serwer MCP (ADR-004) | done (3.0.0) | powierzchnie agentów po angielsku: planned (Next 1) |
| Web GUI (HTMX + Jinja2) | done | dane ČHMÚ i warstwa GeoJSON: planned |
| Egzekwowanie kluczy API, limity per klucz | planned | backlog w „Next” |
| Zgodność ze standardem Nogat 2.1 (`chore/nogat-2.1`) | in progress | zrobione i do zrobienia: poniżej i w „Next” |
| CI z macierzą ubuntu/macos/windows | planned | zapis na macOS i Windows nie był uruchomiony na prawdziwym systemie |

### Zgodność ze standardem Nogat 2.1 (`chore/nogat-2.1`)

**Zrobione:** pyright → mypy `strict` (ECO-010; testy bez adnotacji to odchylenie DEV-7.3 w `CLAUDE.md`), `scripts/gate.sh` + `check-commits.sh`, `uv.lock`, znacznik `live` zamiast `IMGW_LIVE=1`, pokrycie ≥ 80 % (DEV-7.5), CI/Dependabot z szablonów Nogat (działają po zmianie nazw gałęzi), `forbidden` z kodem wyjścia 12 (ERR §4), errata przy ADR-001 D1 (hardlinki), prefiks MCP `imgw_` = `operation_id` katalogu = `operationId` OpenAPI, komplet adnotacji MCP z `idempotentHint`, komenda `commands list` (ECO-018, AGI-5.2, AGI-5.4, AGI-5.9, AGI-6.2; errata ADR-004 z 2026-10-24); środowisko użytkownika DEV-18: `nogat.toml` przez `tomllib`, `NOGAT_*`, `cache_dir`, `IMGW_DATA_DIR` → `IMGW_REFERENCE_DIR` (zmiana łamiąca), `imgw config show --json`, 18 zmiennych w README i `.env.example` (ADR-005).

## Next

Kolejność zależności; niedokończone prace pierwsze. Backlog jest jedynym źródłem prawdy dla rzeczy do zrobienia — nowe zadania dopisuj wyłącznie tutaj (konsolidacja 2026-08-02: dawne sekcje „Planowane”/„Zaimplementowane” oraz sekcja 11 z `PRD.md`).

1. **Powierzchnie agentów po angielsku (AGI-9.2, ECO-042).** Domyślnie polskie: `detail`/`Notice.text` wyjątków (ok. 320 miejsc zgłoszenia, 31 powiadomień, ok. 860 polskich literałów w `src/`), ostatnia linia stderr CLI, `Accept-Language` REST (brak nagłówka = `pl`), `imgw mcp --lang` (domyślnie `pl`), `agent_guide(lang="pl")` i zatwierdzone `AGENTS.md`/`llms.txt`, OpenAPI. Wymaga klucza tłumaczeń (DEV-2.3) i polskich tekstów jako wariantu `lang`.
2. **Budżety dokumentów (DOC-1.7):** `CLAUDE.md` 200 wierszy (jest ok. 590), `README.md` 400 (ok. 835), `AGENTS.md` 200 wierszy i 16 KiB (261 wierszy, 29 KB; generowany — test kontraktowy z budżetem), `docs/PROGRESS.md` 300 (ok. 450); `llms.txt` przed listą linków mieści się (2,6 KB z 8 000). Tłumaczenie dokumentacji na angielski (ECO-005) jest osobnym zadaniem fazy 3.
3. **Retman (migracja po zmianie pinu IMGWTools):** `retman/tools/imgwtools/client.py` eksportuje `IMGW_DATA_DIR` jako swój `reference_data_dir`; od zmiany w `chore/nogat-2.1` (ADR-005 D2, CHANGELOG „Breaking”) katalog danych referencyjnych to `IMGW_REFERENCE_DIR`, a `IMGW_DATA_DIR` jest katalogiem danych użytkownika, więc eksport trzeba przenieść na `IMGW_REFERENCE_DIR` razem ze zmianą pinu. Nowa zmienna: `IMGW_CACHE_DIR`; `config show` do użycia przez `nogat doctor`.
4. **Ścieżka zapisu (konwencja `data-output`, Z1–Z7):** osobne zadanie (`-o/--output-dir`, `--root`, `--output` zamiast `path`, domyślny magazyn w katalogu użytkownika, tryb plain, `files[]`). Przy tym zadaniu: `IMGW_STORE_ROOT` → `IMGW_ROOT` (klucz `root` w `nogat.toml`), domyślny korzeń `<data_dir>/imgw` raportowany w `imgw config show` jako `store.root`, a test „pustego” korzenia nie może liczyć `api_keys.json` (domyślnie w `<data_dir>/imgw/`) jako zawartości magazynu.

Dalsze otwarte pozycje backlogu (priorytet w tekście):

### Funkcjonalności

- [ ] API key enforcement — middleware walidujące nagłówek `X-API-Key`. `docs/CODEBASE.md` (sekcja „Cloud & Deployment Details”) odnotowuje, że klucze są zarządzane przez CLI (`imgw admin`), ale nieegzekwowane w żądaniach API — to brakująca warstwa bezpieczeństwa, nie nowa funkcja. Priorytet: wysoki.
- [ ] Per-key rate limiting — śledzenie i limitowanie żądań per klucz API. Zależne od API key enforcement. Priorytet: średni.
- [ ] GeoJSON w REST/GUI — wersjonowany katalog `stations.geojson` istnieje od 3.0.0 (`build_catalog`, `read_catalog`); brakuje komendy katalogu odczytującej go (a więc trasy REST) i warstwy na mapie Web GUI. Priorytet: średni.
- [ ] Data charts — wizualizacja szeregów czasowych. Możliwy wzorzec: podejście repo hydro-dane — agregaty min/avg/max z walidacją pełnego roku hydrologicznego i eksport do kompaktowych statycznych JSON-ów. Priorytet: niski.
- [ ] Eksport CSV w REST/GUI dla danych bez magazynu — od 3.0.0 `export_series`/`imgw series export`/`GET /api/v1/series/export` eksportują szeregi z magazynu; brak eksportu „na żądanie” bez magazynu. Priorytet: niski.
- [ ] Request logging — śledzenie użycia API do analityki. Priorytet: niski.
- [ ] Redis caching layer — cache dla często pobieranych danych. Priorytet: niski.

- [ ] Lepsze nazewnictwo KS/SG/RB w `PMaXTPData` — aliasy właściwości i metoda `get_design_precipitation()`; szczegóły w sekcji "TODO: Poprawa czytelności PMaXTPData" poniżej. Priorytet: średni.
- [ ] Natywna siatka PMAXTP w `fetch_pmaxtp` — od 3.0.0 magazyn PMAXTP (`sync_pmaxtp`/`read_pmaxtp`) kluczuje komórki indeksami `indX/indY` z odpowiedzi i zapisuje środek komórki w `cell.json`, ale `PMaXTPResult` z `fetch_pmaxtp` nadal nie ma pól `point`, brak funkcji konwersji/iteracji komórek, a docstringi podają zakres 7×6 zamiast 16×27; szczegóły w sekcji "TODO: Natywna siatka PMAXTP" poniżej. Zgłoszone z Hydrografa (2026-09-28). Priorytet: wysoki.
- [ ] Dane ČHMÚ w Web GUI — formularze i wyszukiwarka obsługują wyłącznie IMGW-PIB (`datasets(provider="IMGW-PIB")`); pliki ČHMÚ są per stacja, więc formularz potrzebuje wyboru stacji (spec ČHMÚ §9.3). Priorytet: niski.

### Wsparcie agentów AI (po 3.0.0, ADR-004)

- [ ] Tłumaczenie treści wykonania (`detail`, `Notice.text`, postęp) na angielski — dziś tylko tytuły i opisy katalogu (ADR-004, pytanie 3). Priorytet: niski.
- [ ] Filtr narzędzi MCP według grup albo dostawcy (`--groups`, `--provider`, `data_commands(provider=…)`), gdy koszt kontekstu listy narzędzi (ok. 42 KB) okaże się problemem (ADR-004, pytanie 4). Priorytet: niski.
- [ ] Limit wywołań sieciowych serwera MCP na stdio (dziś tylko żądania sekwencyjne biblioteki) i zapis przez MCP po HTTP z autoryzacją (ADR-004, pytania 5–6). Priorytet: niski.

### Magazyn wersjonowany (po 3.0.0)

- [ ] Lokalny, odbudowywalny indeks magazynu (ADR-001 D2: poza wydaniem 3.0.0; nigdy jako źródło prawdy). Priorytet: niski.
- [ ] Wniosek do IMGW-PIB o oficjalny wykaz współrzędnych stacji (ADR-001 Q6) oraz potwierdzenie znaczenia kodu hydrograficznego i kolejności `river_order` (Q4, Q5) — do tego czasu bez interpretacji. Priorytet: średni.
- [ ] Rozszerzenie magazynu o kolejne zbiory (meteo miesięczne/terminowe, synop) — D6 ogranicza 3.0.0 do pięciu zbiorów Archiwisty i PMAXTP. Priorytet: niski.
- [ ] Pytania do ČHMÚ (chmi@chmi.cz; ADR-003, pytania 5–10): strefa czasu znaczników `historical` i definicja doby HD/QD, oficjalny rok hydrologiczny, czy regeneracje zachowują bajty i czy istnieje rejestr korekt, ciągłość `historical_csv`, znaczenie `WGS_ELE`, `RICKM`, `HA`, `QA`, `CEVT`, `PRF_ID`, pełny słownik `FLAG`. Priorytet: średni.
- [ ] Potwierdzenia Archiwisty (ADR-003, pytania 11–15): `stations[<kod>].periods` w etykietach pokrycia, rozróżnienie `relabeled`/`unchanged` treścią w IMGW-16, `restored_by_content`/`content_match` w IMGW-19, brak pól treści jako `null`, wpisy `kind="observation"` tylko do odczytu. Priorytet: średni.
- [ ] Obserwator — przyszła zmiana nazwy (`docs/OBSERWATOR_SPEC.md`), już bez cache SQLite (zastąpiony magazynem); dostawcę ČHMÚ opisuje ADR-003 (pozycja wyżej). Priorytet: niski.
- [ ] CI z macierzą ubuntu/macos/windows dla `tests/unit` i `tests/contract` — zapis na macOS i Windows nie był uruchomiony na prawdziwym systemie. Priorytet: wysoki.

### TODO: Poprawa czytelności PMaXTPData (KS/SG/RB)

**Kontekst:** Skróty KS, SG, RB w odpowiedzi API PMAXTP mogą być mylące. Łatwo pomylić górną granicę przedziału ufności (SG) z właściwą wartością kwantyla (KS), co prowadzi do błędnych obliczeń hydrologicznych.

| Symbol | Znaczenie | Zastosowanie |
|--------|-----------|--------------|
| **KS** | Kwantyle (estymata punktowa) | Wartość projektowa (domyślna) |
| **SG** | Górna granica przedziału ufności | Obliczenia konserwatywne |
| **RB** | Błędy estymacji | Analiza niepewności |

#### Propozycje zmian

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

### TODO: Natywna siatka PMAXTP

**Kontekst:** rozpoznanie z Hydrografa (2026-09-28, ~60 zapytań do `https://powietrze.imgw.pl/tpmax-api/point/P/KS/{lat}/{lon}`). Endpoint punktowy przypisuje zapytanie do najbliższego środka komórki regularnej siatki i zwraca jej parametry, których IMGWTools obecnie nie udostępnia. Bez nich klient nie wie, którą komórkę pobrał — gęste próbkowanie odpytuje wielokrotnie tę samą komórkę, rzadkie pomija komórki (siatka Hydrografa co 2 km pomijała ~80% komórek).

#### Surowa odpowiedź

```json
{
  "point": {"lon": "21.0100", "lat": "52.2300", "name": "", "method": "POT",
            "dataLon": 21.007098333333, "dataLat": 52.234416666667,
            "indX": 751, "indY": 317, "recalcualted": true},
  "data": {"ks": {...}, "rb": {...}, "sg": {...}}
}
```

- `dataLon`/`dataLat` — środek komórki (WGS84), `indX`/`indY` — indeksy komórki.
- `recalcualted` (literówka po stronie IMGW) — znaczenie nieznane; brak tego pola w odpowiedzi poza zasięgiem danych.
- Poza Polską: indeksy i środek wracają, ale `data: {}` oraz dodatkowy klucz `error`.

#### Parametry siatki (zmierzone)

| Parametr | Wartość |
|---|---|
| Układ | regularna siatka w stopniach WGS84 (EPSG:4326) |
| Krok | Δlon = 0.01001°, Δlat = 0.01° (~680 m × 1110 m na 52°N, ~0,75 km²) |
| Środek komórki | `lon = 13.489588333 + 0.01001 · indX`, `lat = 55.404416667 − 0.01 · indY` (indY rośnie na południe) |
| Przypisanie punktu | do najbliższego środka komórki (sprawdzone na granicach komórek) |

Zweryfikowane na punktach (52.23, 21.01) → (751, 317), (50.0, 19.0) → (550, 540), (54.0, 15.0) → (151, 140), (49.3, 14.2) → (71, 610, poza zasięgiem danych). Kroki i początek zgodne we wszystkich czterech.

#### Zakres danych

Odpowiedź zawiera **16 czasów trwania × 27 prawdopodobieństw** dla każdej z tablic `ks`/`sg`/`rb`:
- czasy [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440, 2160, 2880, 4320,
- prawdopodobieństwa [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5, 99.9.

Docstring `fetch_pmaxtp()` (`fetch.py`) i `PMaXTPData` podają nieaktualnie 7 czasów × 6 prawdopodobieństw.

#### Propozycje zmian

1. `PMaXTPResult` — dodać pola z bloku `point`: `cell_lat`, `cell_lon`, `ind_x`, `ind_y` (oraz `has_data: bool` na podstawie `error`/pustego `data`); zachować surową odpowiedź (np. `raw: dict`) do archiwizacji po stronie klienta.
2. Stałe siatki i funkcje konwersji: `pmaxtp_cell_for(lat, lon) -> (ind_x, ind_y)`, `pmaxtp_cell_center(ind_x, ind_y) -> (lat, lon)`, `pmaxtp_cells_in_bbox(bbox) -> Iterator[(ind_x, ind_y)]` — pobieranie „jedna komórka = jedno zapytanie o jej środek”.
3. Poprawić dokumentację zakresu (16×27) w docstringach i README.
4. `get_precipitation(duration_minutes, probability_percent: int)` — typ `int` nie pasuje do prawdopodobieństw ułamkowych (0.01, 98.5); klucz budowany przez `str()` wymaga, by float nie był przekazywany jako np. `1.0` (→ `"1.0"`, brak dopasowania). Rozważyć normalizację klucza.
5. Test kontraktowy na zapisanej odpowiedzi (fixture) — weryfikacja kroków i początku siatki.

## Open questions

Decyzje czekające na autora (usuwać po rozstrzygnięciu):

- [ ] Decyzja właściciela: czy publiczny serwer włącza `/mcp` (`IMGW_MCP_ENABLED`) — ADR-004, pytanie otwarte 2. Priorytet: średni.

**Dla autora (poza zasięgiem agenta):** zmiana nazw gałęzi `master`/`slave` → `main`/`develop` i domyślna gałąź na GitHubie (ECO-008); potem odnośniki `raw.githubusercontent.com/.../master/` w `llms.txt` i szablonach `_data/agents/llms.*.md` oraz nazwy `slave` w tym pliku i w `docs/DECISIONS.md`; zestawy reguł gałęzi/tagów, Dependabot security updates, `SECURITY.md` i prywatne zgłaszanie podatności (DEV-3.6, DEV-13.7); przepisanie historii i tożsamości autorów (faza 1; w historii 58 commitów `Claude <agent@local>`); tekst CLA. Pierwszy przebieg CI będzie też pierwszym na macOS i Windows.

---

**Ostatnia aktualizacja:** 2026-10-19
