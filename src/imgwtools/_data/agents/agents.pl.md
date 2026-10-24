# IMGWTools — przewodnik dla agentów (wersja <!-- imgw:version -->)

> Plik generowany z katalogu komend: `imgw commands guide --format agents --lang pl --path AGENTS.md`.
> Nie edytuj ręcznie. Wersja angielska: `imgw commands guide --lang en`.

## Czym jest IMGWTools

IMGWTools to biblioteka Pythona, CLI `imgw`, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: archiwów, danych bieżących i opadów maksymalnych prawdopodobnych PMAXTP. Archiwa trafiają do wersjonowanego magazynu — zwykłego katalogu, w którym wersje są niezmienne, a ich tożsamością jest SHA-256 — i z niego, offline, czyta się szeregi stacji. Wszystkie interfejsy powstają z jednego katalogu komend, więc mają te same nazwy opcji, walidację, kopertę wyniku i kody błędów. <!-- imgw:summary -->

<!-- imgw:providers -->

## Zasady: sprawdź → uruchom → przeczytaj

<!-- imgw:rules -->

## Interfejsy

| Interfejs | Odkrycie | Plan | Wynik | Błąd |
|---|---|---|---|---|
| Python | `list_commands()`, `command_schema()`, `data_commands()` | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `imgw commands list`, `imgw commands schema`, `--schema` | `--check` | koperta JSON w jednej linii stdout; kod wyjścia | ostatnia linia stderr `{"code", "detail", "details"}`; kod wyjścia z rejestru |
| REST `/api/v1` | `GET /api/v1/commands/list`, `/schema` | `?check=true` (POST) | 200 + koperta (`status` w treści) | `application/problem+json` |
| MCP | `tools/list`, `imgw_commands_list` | `check: true` | `structuredContent` = koperta | `isError: true` + `{"code", "title", "detail", "details"}` |

Ta sama komenda w każdym interfejsie: CLI `imgw <grupa> <komenda> --opcja wartość` (flaga = `--` + nazwa opcji z `-` zamiast `_`); Python `run_command("<grupa> <komenda>", options={"opcja": wartość})` albo funkcja z kolumny „Funkcja” tabel komend z tymi samymi argumentami; REST `/api/v1/<grupa>/<komenda>` (GET: parametry zapytania, listy jako powtórzony parametr; POST: ciało JSON); MCP — narzędzie `imgw_<grupa>_<komenda>` (`x-imgw.operation_id`: przedrostek `imgw_` i nazwa komendy ze spacją i `-` zamienionymi na `_`, np. `imgw_store_sync`, `imgw_current_hydro_states`; to także `operationId` REST) z argumentami = opcjami.

- **REST:** korzeń magazynu ustawia serwer (`IMGW_STORE_ROOT`; żądanie nie podaje `root`), `version` jest względna do magazynu serwera, opcji lokalnych (np. `path`) nie ma; zapis (POST bez `?check=true`) wymaga włączenia na serwerze i tokenu w nagłówku `X-API-Key`.
- **MCP:** `imgw mcp` (stdio, dodatek `imgwtools[mcp]`) startuje bez zapisu — komendy zapisujące mają `check` stałe `true` i zwracają plan; zapis włącza użytkownik (`imgw mcp --allow-writes`), a i wtedy `check` jest domyślnie `true`. Punkt `/mcp` serwera REST (`IMGW_MCP_ENABLED=true`) obejmuje komendy z trasą REST, tylko odczyt i plan.

## Koperta, statusy i błędy

Komenda zwraca kopertę `imgw-result/1`: `{"schema": "imgw-result/1", "command", "check", "status", "result", "notices"}`, gdzie `notices` to lista `{"level", "code", "text"}` (każdy komunikat raz, np. `license_terms`). Komendy listowe mają w `result` stronę `{"items", "total", "limit", "offset"}`, a sprawdzenie (`check`) — plan `imgw-plan/1` z `items[].status` i `actions[].status`. Komendy strumieniowe (wynik „strumień linii” w tabelach komend) bez `path` dają same linie danych: CLI pisze je na stdout, REST odpowiada załącznikiem ze statusem i komunikatami w nagłówkach `X-IMGW-Status` i `X-IMGW-Notices`. REST odpowiada 200 także dla `partial` i `failed` — decyduje `status` w treści.

<!-- imgw:statuses -->

Błąd ma kod z zamkniętego rejestru, ten sam w Pythonie (`IMGWError.code`), CLI (ostatnia linia stderr i kod wyjścia), REST (problem+json i status HTTP) i MCP (`isError`); `details.option` wskazuje błędną opcję, a `—` — interfejs, który danego kodu nie zgłasza.

<!-- imgw:errors -->

## Zbiory danych

Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`; slug (`hydro_daily`) i alias legacy (`hydro/dobowe`) są przyjmowane wyłącznie na wejściu — wyniki i sloty magazynu podają pełny klucz.

<!-- imgw:datasets -->

- `stations` (identyfikatory WIGOS) jest wymagane dla `cz.chmi.*` i niedozwolone dla `pl.imgw.*` w `datasets files`, `datasets download`, `store check` i `store sync`; jedno wywołanie obejmuje zbiory jednego rodzaju: archiwa krajowe `pl.imgw.*` albo pliki stacji `cz.chmi.*`.
- `years`: wymagane w `datasets files` i `datasets download` (poza `cz.chmi.meteo_daily`) oraz dla `pl.imgw.*` w `store check` i `store sync`; tam opcjonalne dla `cz.chmi.hydro_daily` (brak = lata opublikowane); zawsze niedozwolone dla `cz.chmi.meteo_daily` (pliki obejmują całą historię stacji) i nie wcześniejsze niż „Od roku”.
- `months` wyłącznie dla `pl.imgw.*`; `params` (`H`, `Q`, `T`) wyłącznie dla `pl.imgw.hydro_semiannual`.
- Zbiory spoza magazynu („W magazynie” = `nie`) obsługują tylko `datasets files` i `datasets download`; listy stacji trafiają do magazynu przez `store catalog`, PMAXTP przez `pmaxtp sync`.
- Rok hydrologiczny IMGW-PIB trwa od 1 listopada do 31 października (`year_type`: `hydrological` albo `calendar`).

## Komendy

Tabela każdej grupy podaje komendę, funkcję Pythona i typ wyniku, opcje w kolejności katalogu (`*` — wymagana, `=` — wartość domyślna), skutek uruchomienia (`odczyt`; `sieć` — łączy się ze źródłem; `zapis` — wyłącznie nowe pliki, wersje albo zadania; `zapis z nadpisaniem` — może zastąpić istniejący plik; opcja przed dwukropkiem zapisuje plik, gdy ją podasz), bliźniaka `check` (`sama` — komenda jest sprawdzeniem, `—` — brak) i metodę REST (`—` — komenda lokalna, bez trasy). Pełny schemat opcji: `imgw commands schema --command "<komenda>"`.

<!-- imgw:commands -->

## Flagi i wartości

<!-- imgw:flags -->

## Typowe przepływy

Polecenia mają postać z `format_command` (roczniki rozwinięte do listy; `--years 2010-2020` działa tak samo). Symbole pisane wielkimi literami (`KOD_STACJI`, `KOD_WIGOS`, `PROJEKT`) zastąp wartościami z wcześniejszych kroków; w innym interfejsie użyj odwzorowania z sekcji „Interfejsy”.

<!-- imgw:flows -->

## Czego nie robić

1. Nie buduj URL-i serwerów IMGW-PIB i ČHMÚ ręcznie ani ich nie przeszukuj — `datasets files`, `datasets download`, `store sync`.
2. Nie podejmuj decyzji na podstawie polskiego `detail` ani tekstu pomocy — decyduj po `code`, `status`, kodzie wyjścia i polach JSON.
3. Kody wyjścia 10 i 11 nie oznaczają awarii programu — przeczytaj kopertę (`items[].status`, `error_code`).
4. Nie uruchamiaj zapisu (`store sync`, `series build`, `datasets download`, `project download`) bez planu i zgody użytkownika; w MCP tryb zapisu włącza użytkownik, nie agent.
5. Nie zgaduj stacji ani zbioru: przy kilku trafieniach `stations find` zapytaj; obecność stacji w zbiorze sprawdź `series summary`.
6. Nie edytuj, nie przenoś i nie usuwaj plików magazynu (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — magazyn jest tylko przyrostowy, tożsamością wersji jest SHA-256.
7. Nie pobieraj „na zapas”: zawężaj `years`, `months` i `stations`; archiwa IMGW-PIB obejmują cały kraj, pliki ČHMÚ — pojedyncze stacje.
8. `stations` jest wymagane dla `cz.chmi.*` i zabronione dla `pl.imgw.*`; nie mieszaj dostawców w jednym wywołaniu ze `stations`; `years` jest zabronione dla `cz.chmi.meteo_daily`.
9. Nie oczekuj danych operacyjnych ČHMÚ (`now`, `recent`), dobowych archiwów synoptycznych IMGW-PIB ani PMAXTP poza Polską — nie są obsługiwane.
10. Długie listy czytaj stronami (`limit`, `offset`); nie wczytuj eksportów CSV do kontekstu — `series read` albo `series export --path`.
11. Nie odpytuj `current …` w pętli — to API na żywo; zachowaj wynik.
12. Przekaż użytkownikowi komunikat `license_terms` i atrybucję (IMGW-PIB: warunki celu użycia; ČHMÚ: CC BY 4.0).
13. `version` wskazuj wyłącznie pod `*/versions/` magazynu, bez `..`; w REST i MCP przez HTTP — względnie do magazynu serwera.
14. Ze stderr CLI czytaj tylko ostatnią linię JSON; postęp i komunikaty są dla człowieka.
15. Nie edytuj `AGENTS.md` ani `llms.txt` ręcznie — regeneruj je komendą z nagłówka.

## Praca nad kodem repozytorium

Ten plik opisuje używanie IMGWTools. Przy zmianach kodu obowiązują `CLAUDE.md`, `docs/DEVELOPMENT_STANDARDS.md` i `docs/RULES.md` (architektura: `docs/ARCHITECTURE.md`, decyzje: `docs/DECISIONS.md`). Bramka: `.venv/bin/python -m pytest`, `.venv/bin/ruff check src/ tests/`, `.venv/bin/ruff format --check src/ tests/`, `.venv/bin/pyright src/imgwtools/`. Zmiana katalogu komend, rejestru zbiorów, dostawców albo kodów błędów lub szablonów `src/imgwtools/_data/agents/` regeneruje `AGENTS.md` i `llms.txt` w tej samej zmianie: `imgw commands guide --format agents --lang pl --path AGENTS.md` i `imgw commands guide --format llms --lang pl --path llms.txt` (test porównuje bajty plików z generatorem).
