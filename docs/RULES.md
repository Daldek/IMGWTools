# IMGWTools — Zasady pracy i standardy

## 1. Styl i jakość kodu
- styl: **PEP8**
- docstringi: **NumPy Style**
- linting/formatowanie: **ruff**
- typowanie: **typing** (obowiązkowe)

---

## 2. Testy
- wymagane **testy jednostkowe i integracyjne**
- pokrycie min. 80%
- nie merge'ujemy PR bez testów

---

## 3. Workflow Git
Branch'e:
- `master` — stabilne wydania
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
