# Obserwator

> Biblioteka Pythona, CLI, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: wersjonowany magazyn archiwów i szeregów stacji, dane bieżące i PMAXTP. <!-- obserwator:summary -->

<!-- obserwator:rules -->

- Wynik: koperta JSON `obserwator-result/1` (CLI: `--json`; bez niego podsumowanie dla człowieka) z polem `status` (`ok`, `partial`, `failed`, `cancelled`; kody wyjścia CLI 0, 10, 11, 130).
- Błąd: `obserwator-error/1` `{schema, code, title, message, hint?, details, exit_code, command?}` w ostatniej linii stderr CLI i w MCP `isError` albo `application/problem+json` w REST; kody z zamkniętego rejestru, np. `validation_error` = 2 / 400.
- Zbiory: pełne klucze `<kraj>.<dostawca>.<zbiór>`, np. `pl.imgw.hydro_daily`, `cz.chmi.hydro_daily`; kody stacji: IMGW-PIB 9 cyfr, ČHMÚ identyfikator WIGOS.
- Opis komend: `obserwator commands list --json` (spis) i `obserwator commands schema --json` (opcje) albo `GET /api/v1/commands/list` i `/schema`; narzędzia MCP `obserwator_commands_list` i `obserwator_commands_schema`; przewodnik w całości po polsku: `obserwator commands guide --lang pl` albo `GET /api/v1/commands/guide?lang=pl`.

## Dokumentacja

- [AGENTS.md](https://raw.githubusercontent.com/Daldek/Obserwator/main/AGENTS.md): przewodnik dla agentów po angielsku (po polsku: `obserwator commands guide --lang pl`) — komendy, zbiory, flagi, kody błędów, przepływy, czego nie robić
- [README.md](https://raw.githubusercontent.com/Daldek/Obserwator/main/README.md): instalacja i przykłady Python, CLI, REST, MCP
- [Architektura](https://raw.githubusercontent.com/Daldek/Obserwator/main/docs/ARCHITECTURE.md): moduły, magazyn, przepływ danych
- [Zmiany](https://raw.githubusercontent.com/Daldek/Obserwator/main/docs/CHANGELOG.md): zmiany i migracja z 2.x

## Optional

- [Rejestr decyzji](https://raw.githubusercontent.com/Daldek/Obserwator/main/docs/DECISIONS.md): ADR-001–ADR-009
