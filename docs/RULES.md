# IMGWTools — Zasady pracy i standardy

## 1. Styl i jakość kodu
- styl: **PEP8**
- docstringi: **NumPy Style** (wymuszane przez reguły `D` w ruff, `convention = "numpy"`)
- linting/formatowanie: **ruff** (`ruff check`, `ruff format` — całe repozytorium)
- typowanie: **typing** (obowiązkowe)

---

## 2. Testy
- **testy jednostkowe i kontraktowe** — wymagane, stan: 1377 testów w `tests/unit` i `tests/contract` (2026-10-18), wszystkie offline
- **testy na żywo** — 42 testy w `tests/live` (35 komend × Python/CLI/REST na serwerach IMGW), uruchamiane wyłącznie z `IMGW_LIVE=1`
- pokrycie: ostatni pomiar **93%** (2026-10-18, przed zmianami ADR-002), cel docelowy **80%**
- zmiana katalogu komend, CLI, REST lub web musi utrzymać kontrakt Python = CLI = REST (`tests/contract/test_interface_contract.py`)
- nie merge'ujemy PR bez testów

---

## 3. Workflow Git
Branch'e:
- `master` — stabilne wydania
- `slave` — główna gałąź rozwojowa
- `feature/*` — nowe funkcje
- `hotfix/*` — poprawki krytyczne

Commit:
- znaczący opis w języku polskim lub angielskim
- brak commitów typu "fix" bez kontekstu

---

## 4. Dokumentacja
Każda zmiana funkcjonalna musi:
- aktualizować dokumentację Markdown,
- aktualizować komentarze i docstringi,
- aktualizować OpenAPI (jeśli dotyczy).

---

## 5. Integracja z Claude Code
Projekt używa **Claude Code** (claude.ai/code) do wspomagania developmentu.

Konfiguracja:
- `CLAUDE.md` w katalogu głównym — automatycznie ładowany przez Claude Code
- Zawiera instrukcje, komendy, strukturę projektu

Claude Code pomaga w:
- generowaniu i modyfikacji kodu,
- aktualizacji dokumentacji,
- utrzymaniu spójności projektu.

---

## 6. Code Review
- min. 1 osoba review (jeśli zespół > 1)
- sprawdzenie testów
- sprawdzenie dokumentacji

---

## 7. Licencja
Projekt **Open Source**, licencja MIT.
