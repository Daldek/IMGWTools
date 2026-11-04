# Obserwator — przewodnik dla agentów (wersja <!-- obserwator:version -->)

> Plik generowany z katalogu komend: `obserwator commands guide --format agents --lang pl`. Nie edytuj ręcznie.

## Czym jest Obserwator

Obserwator to biblioteka Pythona, CLI `obserwator`, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: archiwów, danych bieżących i opadów maksymalnych prawdopodobnych PMAXTP. Archiwa trafiają do wersjonowanego magazynu (zwykły katalog; wersje są niezmienne, tożsamość to SHA-256) albo jako zwykłe pliki, a z magazynu offline czyta się szeregi stacji.

Służy do odczytu archiwalnych i bieżących danych stacji IMGW-PIB i ČHMÚ, lokalnych kopii i wartości PMAXTP. Nieobsługiwane: prognozy, dane operacyjne ČHMÚ (`now`, `recent`), dobowe archiwa synoptyczne IMGW-PIB, PMAXTP poza Polską. Instalacja: `pip install obserwator[cli]` (`[mcp]` dodaje serwer MCP, `[store]` szeregi Parquet).

<!-- obserwator:providers -->

## Zasady: sprawdź → uruchom → przeczytaj

<!-- obserwator:rules -->

## Interfejsy

| Interfejs | Plan | Wynik | Błąd |
|---|---|---|---|
| Python | `check_command(…)` | `CommandResult` (`to_json()`) | `ObserwatorError` (`code`, `detail`, `hint`, `details`); `obserwator.error_report.error_report(exc).to_dict()` = dokument błędu |
| CLI `obserwator` | `--check` | `--json`: koperta JSON w jednej linii stdout (bez niego podsumowanie dla człowieka) | ostatnia linia stderr: dokument błędu `obserwator-error/1`; kod wyjścia |
| REST `/api/v1` | `?check=true` (POST) | 200 + koperta | `application/problem+json` (z `hint`) |
| MCP | `check: true` | `structuredContent` = koperta | `isError: true` + dokument błędu `obserwator-error/1` |

Ta sama komenda w każdym interfejsie: CLI `obserwator <grupa> <komenda> --opcja wartość --json` (flaga = `--` + nazwa opcji z `-` zamiast `_`); Python `run_command("<grupa> <komenda>", options={...})`; REST `/api/v1/<grupa>/<komenda>` (GET: parametry zapytania, POST: ciało JSON); narzędzie MCP `obserwator_<grupa>_<komenda>`.

- **REST:** korzeń magazynu ustawia serwer (`OBSERWATOR_ROOT`), `version` jest względna do niego, opcji lokalnych nie ma; zapis (POST bez `?check=true`) wymaga włączenia na serwerze i nagłówka `X-API-Key`.
- **MCP:** `obserwator mcp` (stdio) startuje bez zapisu — komendy zapisujące zwracają plan (`check` stałe `true`); zapis włącza użytkownik (`--allow-writes`), a i wtedy `check` jest domyślnie `true`. `/mcp` serwera REST (`OBSERWATOR_MCP_ENABLED=true`) tylko czyta i planuje.
- **Język:** wynik maszynowy jest po angielsku (koperta `--json`, linie błędów, MCP, REST, domyślny przewodnik). Polski tylko na prośbę: `--lang pl` (`commands list|schema|guide`; w pozostałych komendach język podsumowania CLI bez `--json`), `lang: "pl"` (MCP), `Accept-Language: pl` (REST).

## Koperta, statusy i błędy

Komenda zwraca kopertę `obserwator-result/1` `{"schema", "tool", "version", "command", "check", "status", "result", "notices"}`; `result` to dokument z własnym `schema` (`obserwator-<rodzaj>/1`), lista takich dokumentów albo null; `notices` to lista `{"level", "code", "message"}` (każdy raz, np. `license_terms`). Komendy listowe zwracają listę elementów jako `result` i w kopercie `page` `{"total", "next_cursor", "truncated"}`: dopóki `truncated` jest prawdą, podaj `next_cursor` jako `cursor` kolejnej strony. Sprawdzenie zwraca plan `obserwator-plan/1`. Komendy strumieniowe bez `output` dają same linie danych: CLI pisze je na stdout (z `--json` i bez), REST odpowiada załącznikiem (status i komunikaty w `X-Obserwator-Status`, `X-Obserwator-Notices`). REST: 200 także dla `partial` i `failed` — decyduje `status`.

<!-- obserwator:statuses -->

Błąd ma kod z zamkniętego rejestru, ten sam w Pythonie, CLI, REST (problem+json) i MCP (`isError`); `details.option` wskazuje błędną opcję. Kody z kodem wyjścia CLI i statusem HTTP (`—`: nigdy nie zgłaszany): <!-- obserwator:errors -->.

## Zbiory danych

Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`; slug (`hydro_daily`) i alias legacy (`hydro/dobowe`, patrz `obserwator datasets list`) są przyjmowane wyłącznie na wejściu. Zbiory magazynu:

<!-- obserwator:datasets -->

- `stations` (identyfikatory WIGOS): wymagane dla `cz.chmi.*`, niedozwolone dla `pl.imgw.*` w `datasets files`, `datasets download`, `store check` i `store sync`; jedno wywołanie obejmuje zbiory jednego rodzaju (`pl.imgw.*` albo `cz.chmi.*`).
- `years`: wymagane w `datasets files`, `datasets download` (poza `cz.chmi.meteo_daily`) i, dla `pl.imgw.*`, w `store check` i `store sync`; tam opcjonalne dla `cz.chmi.hydro_daily` (brak = lata opublikowane); nigdy dla `cz.chmi.meteo_daily`; nie wcześniej niż „Od roku”. `months` wyłącznie dla `pl.imgw.*`, `params` wyłącznie dla `pl.imgw.hydro_semiannual`.

## Komendy

Jedna linia na komendę, według skutku; opcje, reguły i skutki opcji: `obserwator commands schema --command "<komenda>" --json`. Znaczniki: `[output: …]` — opcja zapisuje plik, gdy ją podasz; `[jest sprawdzeniem]` — komenda sama planuje; `[lokalna]` — bez trasy REST.

<!-- obserwator:commands -->

## Flagi i wartości

<!-- obserwator:flags -->

## Typowe przepływy

Symbole pisane wielkimi literami (`KOD_STACJI`, `KOD_WIGOS`) zastąp wartościami z wcześniejszych kroków.

<!-- obserwator:flows -->

## Czego nie robić

1. Nie buduj URL-i serwerów IMGW-PIB i ČHMÚ ręcznie ani ich nie przeszukuj — `datasets files`, `datasets download`, `store sync`.
2. Kody wyjścia 10 i 11 nie oznaczają awarii programu — przeczytaj kopertę (`items[].status`, `error_code`).
3. Nie uruchamiaj zapisu (`store sync`, `series build`, `datasets download`) bez planu i zgody użytkownika.
4. Nie zgaduj stacji ani zbioru: przy kilku trafieniach `stations find` zapytaj; obecność stacji w zbiorze sprawdź `series summary`.
5. Nie edytuj, nie przenoś i nie usuwaj plików magazynu (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — magazyn jest tylko przyrostowy.
6. Nie pobieraj „na zapas”: zawężaj `years`, `months` i `stations`; nie mieszaj dostawców w jednym wywołaniu ze `stations`.
7. Długie listy czytaj stronami (`limit`, `cursor` = `page.next_cursor`); używaj `series read` albo `series export --output`, nie CSV w kontekście.
8. Nie odpytuj `current …` w pętli — to API na żywo; zachowaj wynik.
9. Przekaż użytkownikowi komunikat `license_terms` i atrybucję (IMGW-PIB: warunki celu użycia; ČHMÚ: CC BY 4.0).
10. `version` wskazuj wyłącznie pod `*/versions/` magazynu, bez `..`; w REST i MCP przez HTTP — względnie do magazynu serwera.

Rozwijasz to repozytorium? Przeczytaj CLAUDE.md.
