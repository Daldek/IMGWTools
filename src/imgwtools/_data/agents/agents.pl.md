# IMGWTools — przewodnik dla agentów (wersja <!-- imgw:version -->)

> Plik generowany z katalogu komend: `imgw commands guide --format agents --lang pl`. Nie edytuj ręcznie.

## Czym jest IMGWTools

IMGWTools to biblioteka Pythona, CLI `imgw`, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: archiwów, danych bieżących i opadów maksymalnych prawdopodobnych PMAXTP. Archiwa trafiają do wersjonowanego magazynu (zwykły katalog; wersje są niezmienne, tożsamość to SHA-256) albo jako zwykłe pliki, a z magazynu offline czyta się szeregi stacji.

Służy do odczytu archiwalnych i bieżących danych stacji IMGW-PIB i ČHMÚ, lokalnych kopii i wartości PMAXTP. Nieobsługiwane: prognozy, dane operacyjne ČHMÚ (`now`, `recent`), dobowe archiwa synoptyczne IMGW-PIB, PMAXTP poza Polską. Instalacja: `pip install imgwtools[cli]` (`[mcp]` dodaje serwer MCP, `[store]` szeregi Parquet).

<!-- imgw:providers -->

## Zasady: sprawdź → uruchom → przeczytaj

<!-- imgw:rules -->

## Interfejsy

| Interfejs | Plan | Wynik | Błąd |
|---|---|---|---|
| Python | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `--check` | koperta JSON w jednej linii stdout | ostatnia linia stderr `{"code", "detail", "details"}`; kod wyjścia |
| REST `/api/v1` | `?check=true` (POST) | 200 + koperta | `application/problem+json` |
| MCP | `check: true` | `structuredContent` = koperta | `isError: true` + `{"code", "title", "detail", "details"}` |

Ta sama komenda w każdym interfejsie: CLI `imgw <grupa> <komenda> --opcja wartość` (flaga = `--` + nazwa opcji z `-` zamiast `_`); Python `run_command("<grupa> <komenda>", options={...})`; REST `/api/v1/<grupa>/<komenda>` (GET: parametry zapytania, POST: ciało JSON); narzędzie MCP `imgw_<grupa>_<komenda>`.

- **REST:** korzeń magazynu ustawia serwer (`IMGW_ROOT`), `version` jest względna do niego, opcji lokalnych nie ma; zapis (POST bez `?check=true`) wymaga włączenia na serwerze i nagłówka `X-API-Key`.
- **MCP:** `imgw mcp` (stdio) startuje bez zapisu — komendy zapisujące zwracają plan (`check` stałe `true`); zapis włącza użytkownik (`--allow-writes`), a i wtedy `check` jest domyślnie `true`. `/mcp` serwera REST (`IMGW_MCP_ENABLED=true`) tylko czyta i planuje.
- **Język:** wynik maszynowy jest po angielsku (koperta, linie błędów, MCP, REST, domyślny przewodnik). Polski tylko na prośbę: `--lang pl` (`commands list|schema|guide`), `lang: "pl"` (MCP), `Accept-Language: pl` (REST).

## Koperta, statusy i błędy

Komenda zwraca kopertę `imgw-result/1` `{"schema", "command", "check", "status", "result", "notices"}`; `notices` to lista `{"level", "code", "text"}` (każdy raz, np. `license_terms`). Komendy listowe zwracają stronę `{"items", "total", "limit", "offset"}`, sprawdzenie — plan `imgw-plan/1`. Komendy strumieniowe bez `output` dają same linie danych: CLI pisze je na stdout, REST odpowiada załącznikiem (status i komunikaty w `X-IMGW-Status`, `X-IMGW-Notices`). REST: 200 także dla `partial` i `failed` — decyduje `status`.

<!-- imgw:statuses -->

Błąd ma kod z zamkniętego rejestru, ten sam w Pythonie, CLI, REST (problem+json) i MCP (`isError`); `details.option` wskazuje błędną opcję. Kody z kodem wyjścia CLI i statusem HTTP (`—`: nigdy nie zgłaszany): <!-- imgw:errors -->.

## Zbiory danych

Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`; slug (`hydro_daily`) i alias legacy (`hydro/dobowe`, patrz `imgw datasets list`) są przyjmowane wyłącznie na wejściu. Zbiory magazynu:

<!-- imgw:datasets -->

- `stations` (identyfikatory WIGOS): wymagane dla `cz.chmi.*`, niedozwolone dla `pl.imgw.*` w `datasets files`, `datasets download`, `store check` i `store sync`; jedno wywołanie obejmuje zbiory jednego rodzaju (`pl.imgw.*` albo `cz.chmi.*`).
- `years`: wymagane w `datasets files`, `datasets download` (poza `cz.chmi.meteo_daily`) i, dla `pl.imgw.*`, w `store check` i `store sync`; tam opcjonalne dla `cz.chmi.hydro_daily` (brak = lata opublikowane); nigdy dla `cz.chmi.meteo_daily`; nie wcześniej niż „Od roku”. `months` wyłącznie dla `pl.imgw.*`, `params` wyłącznie dla `pl.imgw.hydro_semiannual`.

## Komendy

Jedna linia na komendę, według skutku; opcje, reguły i skutki opcji: `imgw commands schema --command "<komenda>"`. Znaczniki: `[output: …]` — opcja zapisuje plik, gdy ją podasz; `[jest sprawdzeniem]` — komenda sama planuje; `[lokalna]` — bez trasy REST.

<!-- imgw:commands -->

## Flagi i wartości

<!-- imgw:flags -->

## Typowe przepływy

Symbole pisane wielkimi literami (`KOD_STACJI`, `KOD_WIGOS`) zastąp wartościami z wcześniejszych kroków.

<!-- imgw:flows -->

## Czego nie robić

1. Nie buduj URL-i serwerów IMGW-PIB i ČHMÚ ręcznie ani ich nie przeszukuj — `datasets files`, `datasets download`, `store sync`.
2. Kody wyjścia 10 i 11 nie oznaczają awarii programu — przeczytaj kopertę (`items[].status`, `error_code`).
3. Nie uruchamiaj zapisu (`store sync`, `series build`, `datasets download`) bez planu i zgody użytkownika.
4. Nie zgaduj stacji ani zbioru: przy kilku trafieniach `stations find` zapytaj; obecność stacji w zbiorze sprawdź `series summary`.
5. Nie edytuj, nie przenoś i nie usuwaj plików magazynu (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — magazyn jest tylko przyrostowy.
6. Nie pobieraj „na zapas”: zawężaj `years`, `months` i `stations`; nie mieszaj dostawców w jednym wywołaniu ze `stations`.
7. Długie listy czytaj stronami (`limit`, `offset`); używaj `series read` albo `series export --output`, nie CSV w kontekście.
8. Nie odpytuj `current …` w pętli — to API na żywo; zachowaj wynik.
9. Przekaż użytkownikowi komunikat `license_terms` i atrybucję (IMGW-PIB: warunki celu użycia; ČHMÚ: CC BY 4.0).
10. `version` wskazuj wyłącznie pod `*/versions/` magazynu, bez `..`; w REST i MCP przez HTTP — względnie do magazynu serwera.

Rozwijasz to repozytorium? Przeczytaj CLAUDE.md.
