# IMGWTools

> Biblioteka Pythona, CLI, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: wersjonowany magazyn archiwów i szeregów stacji, dane bieżące i PMAXTP. <!-- imgw:summary -->

<!-- imgw:rules -->

- Wynik: koperta JSON `imgw-result/1` z polem `status` (`ok`, `partial`, `failed`, `cancelled`; kody wyjścia CLI 0, 10, 11, 130).
- Błąd: `{"code", "detail", "details"}` w ostatniej linii stderr CLI albo `application/problem+json` w REST; kody z zamkniętego rejestru, np. `validation_error` = 2 / 400.
- Zbiory: pełne klucze `<kraj>.<dostawca>.<zbiór>`, np. `pl.imgw.hydro_daily`, `cz.chmi.hydro_daily`; kody stacji: IMGW-PIB 9 cyfr, ČHMÚ identyfikator WIGOS.
- Opis komend: `imgw commands list` (spis) i `imgw commands schema` (opcje) albo `GET /api/v1/commands/list` i `/schema`; narzędzia MCP `imgw_commands_list` i `imgw_commands_schema`; przewodnik w całości po polsku: `imgw commands guide --lang pl` albo `GET /api/v1/commands/guide?lang=pl`.

## Dokumentacja

- [AGENTS.md](https://raw.githubusercontent.com/Daldek/IMGWTools/master/AGENTS.md): przewodnik dla agentów po angielsku (po polsku: `imgw commands guide --lang pl`) — komendy, zbiory, flagi, kody błędów, przepływy, czego nie robić
- [README.md](https://raw.githubusercontent.com/Daldek/IMGWTools/master/README.md): instalacja i przykłady Python, CLI, REST, MCP
- [Architektura](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/ARCHITECTURE.md): moduły, magazyn, przepływ danych
- [Zmiany](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/CHANGELOG.md): zmiany i migracja z 2.x

## Optional

- [Rejestr decyzji](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/DECISIONS.md): ADR-001–ADR-004
