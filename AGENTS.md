# IMGWTools — przewodnik dla agentów (wersja 3.0.0)

> Plik generowany z katalogu komend: `imgw commands guide --format agents --lang pl`. Nie edytuj ręcznie.

## Czym jest IMGWTools

IMGWTools to biblioteka Pythona, CLI `imgw`, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: archiwów, danych bieżących i opadów maksymalnych prawdopodobnych PMAXTP. Archiwa trafiają do wersjonowanego magazynu — zwykłego katalogu, w którym wersje są niezmienne, a ich tożsamością jest SHA-256 — i z niego, offline, czyta się szeregi stacji. Wszystkie interfejsy powstają z jednego katalogu komend.

Używaj go do odczytu archiwalnych i bieżących danych stacji IMGW-PIB i ČHMÚ, do odtwarzalnych lokalnych kopii i do wartości PMAXTP. Nieobsługiwane: prognozy, dane operacyjne ČHMÚ (`now`, `recent`), dobowe archiwa synoptyczne IMGW-PIB, PMAXTP poza Polską. Instalacja: `pip install imgwtools[cli]` (`[mcp]` dodaje serwer MCP, `[store]` szeregi Parquet).

- `IMGW-PIB` — Polska: klucze `pl.imgw.*`, kod stacji `^[0-9]{9}$`, licencja [IMGW-PIB](https://danepubliczne.imgw.pl/regulations)
- `CHMI` (ČHMÚ) — Czechy: klucze `cz.chmi.*`, kod stacji `^0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}$`, licencja [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)

## Zasady: sprawdź → uruchom → przeczytaj

1. **Poznaj komendy:** `imgw commands list` (spis z opisem jednego zdania), potem `imgw commands schema --command … [--lang en]` albo `imgw <grupa> <komenda> --schema`; REST `GET /api/v1/commands/list` i `/schema`; w MCP `imgw_commands_list` i `imgw_commands_schema`. Opcje to właściwości JSON Schema; reguły nieopisane schematem są w `x-imgw.rules`, skutki w `x-imgw.writes`, `x-imgw.network` i `x-imgw.idempotent`.
2. **Sprawdź bez zapisu:** `--check` (CLI), `?check=true` (REST, POST), `check: true` (MCP; domyślne dla komend zapisujących), `check_command()` (Python) → plan `imgw-plan/1` bez zapisu i bez pobierania treści. `store check` i `project check` same są sprawdzeniem. Przy dużym planie zapytaj użytkownika.
3. **Uruchom:** bez `check`; czytaj `status` koperty, nie tylko kod wyjścia.
4. **Czytaj offline:** `store info`, `store scan`, `series summary`, `series read` (`limit`/`offset`), `pmaxtp read` — bez ponownego pobierania.
5. **Decyduj po kodach:** `code`, `status`, `items[].status`, `error_code`; tekst `detail` jest dla człowieka.

## Interfejsy

| Interfejs | Plan | Wynik | Błąd |
|---|---|---|---|
| Python | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `--check` | koperta JSON w jednej linii stdout | ostatnia linia stderr `{"code", "detail", "details"}`; kod wyjścia |
| REST `/api/v1` | `?check=true` (POST) | 200 + koperta | `application/problem+json` |
| MCP | `check: true` | `structuredContent` = koperta | `isError: true` + `{"code", "title", "detail", "details"}` |

Ta sama komenda w każdym interfejsie: CLI `imgw <grupa> <komenda> --opcja wartość` (flaga = `--` + nazwa opcji z `-` zamiast `_`); Python `run_command("<grupa> <komenda>", options={...})`; REST `/api/v1/<grupa>/<komenda>` (GET: parametry zapytania, POST: ciało JSON); narzędzie MCP `imgw_<grupa>_<komenda>`.

- **REST:** korzeń magazynu ustawia serwer (`IMGW_STORE_ROOT`), `version` jest względna do niego, opcji lokalnych nie ma; zapis (POST bez `?check=true`) wymaga włączenia na serwerze i nagłówka `X-API-Key`.
- **MCP:** `imgw mcp` (stdio) startuje bez zapisu — komendy zapisujące zwracają plan (`check` stałe `true`); zapis włącza użytkownik (`--allow-writes`), a i wtedy `check` jest domyślnie `true`. `/mcp` serwera REST (`IMGW_MCP_ENABLED=true`) tylko czyta i planuje.

## Koperta, statusy i błędy

Komenda zwraca kopertę `imgw-result/1` `{"schema", "command", "check", "status", "result", "notices"}`; `notices` to lista `{"level", "code", "text"}` (każdy raz, np. `license_terms`). Komendy listowe zwracają stronę `{"items", "total", "limit", "offset"}`, sprawdzenie — plan `imgw-plan/1`. Komendy strumieniowe bez `path` dają same linie danych: CLI pisze je na stdout, REST odpowiada załącznikiem (status i komunikaty w `X-IMGW-Status`, `X-IMGW-Notices`). REST odpowiada 200 także dla `partial` i `failed` — decyduje `status` w treści.

| Status | Kod wyjścia CLI | Znaczenie |
|---|---|---|
| `ok` | 0 | bez porażek |
| `partial` | 10 | część pozycji nieudana — przeczytaj `items[].status` i `error_code`; pozostałe są gotowe |
| `failed` | 11 | żadna pozycja się nie udała (w planie: `check_failed`); koperta jest pełna |
| `cancelled` | 130 | przerwano (Ctrl+C, anulowanie żądania); `result` częściowy albo `null` |

Błąd ma kod z zamkniętego rejestru, ten sam w Pythonie, CLI, REST (problem+json) i MCP (`isError`); `details.option` wskazuje błędną opcję. Kody z kodem wyjścia CLI i statusem HTTP (`—`: nigdy nie zgłaszany): `validation_error` (2/400), `not_found` (3/404), `conflict` (4/409), `source_unavailable` (5/502), `missing_dependency` (6/503), `data_error` (7/500), `store_unavailable` (8/503), `io_error` (9/500), `cancelled` (130/—), `forbidden` (12/403), `method_not_allowed` (—/405), `internal_error` (1/500).

## Zbiory danych

Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`; slug (`hydro_daily`) i alias legacy (`hydro/dobowe`, patrz `imgw datasets list`) są przyjmowane wyłącznie na wejściu. Zbiory magazynu:

| Klucz | Zmienne | Od roku |
|---|---|---|
| `pl.imgw.hydro_daily` | `H`, `Q`, `T` | 1951 |
| `pl.imgw.hydro_monthly` | `{H,Q,T}_{min,mean,max}` | 1951 |
| `pl.imgw.hydro_semiannual` | `{H,Q,T}_{min,mean,max}` | 1951 |
| `pl.imgw.meteo_climate_daily` | `Tmax`, `Tmin`, `Tmean`, `Tground`, `P`, `snow_cover` | 1951 |
| `pl.imgw.meteo_precip_daily` | `P`, `snow_cover`, `fresh_snow` | 1950 |
| `pl.imgw.hydro_stations` | — | — |
| `pl.imgw.meteo_stations` | — | — |
| `pl.imgw.pmaxtp` | `ks`, `sg`, `rb` | — |
| `cz.chmi.hydro_daily` | `H`, `Q`, `T` | 1887 |
| `cz.chmi.meteo_daily` | `P`, `Tmean`, `Tmax`, `Tmin` | — |
| `cz.chmi.hydro_stations` | — | — |
| `cz.chmi.meteo_stations` | — | — |

Poza magazynem (tylko `datasets files` i `datasets download`): `pl.imgw.hydro_phenomena`, `pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`, `pl.imgw.meteo_climate_terms`.

- `stations` (identyfikatory WIGOS): wymagane dla `cz.chmi.*`, niedozwolone dla `pl.imgw.*` w `datasets files`, `datasets download`, `store check` i `store sync`; jedno wywołanie obejmuje zbiory jednego rodzaju (`pl.imgw.*` albo `cz.chmi.*`).
- `years`: wymagane w `datasets files`, `datasets download` (poza `cz.chmi.meteo_daily`) i, dla `pl.imgw.*`, w `store check` i `store sync`; tam opcjonalne dla `cz.chmi.hydro_daily` (brak = lata opublikowane); nigdy dla `cz.chmi.meteo_daily`; nie wcześniej niż „Od roku”. `months` wyłącznie dla `pl.imgw.*`, `params` wyłącznie dla `pl.imgw.hydro_semiannual`.

## Komendy

Jedna linia na komendę, według skutku; opcje, reguły i skutki opcji: `imgw commands schema --command "<komenda>"`. Znaczniki: `[path: …]` — opcja zapisuje plik, gdy ją podasz; `[jest sprawdzeniem]` — komenda sama planuje; `[lokalna]` — bez trasy REST.

**Odczyt — bez sieci i bez zapisu**

- `datasets list` — Wypisz zbiory z rejestru: klucze, dostawców, aliasy legacy, zmienne i pierwszy rocznik.
- `datasets files` — Wypisz pliki źródłowe zbioru dla wybranych roczników albo stacji (offline, bez pobierania).
- `datasets providers` — Wypisz dostawców danych z rejestru: identyfikatory, kraje, licencje, wzorce kodów stacji i zbiory.
- `pmaxtp url` — Zbuduj adres URL API PMAXTP dla punktu (offline, bez pobierania).
- `pmaxtp check` — Sprawdź komórkę PMAXTP w magazynie bez pobierania danych. [jest sprawdzeniem]
- `pmaxtp read` — Odczytaj zapisaną komórkę PMAXTP z magazynu (offline).
- `store info` — Pokaż stan magazynu IMGW i obsługiwane kontrakty (offline, bez zapisu).
- `store scan` — Wypisz wersje i problemy magazynu IMGW (offline, bez zapisu).
- `store export` — Wyeksportuj rekordy jednej wersji archiwum jako CSV albo JSONL (offline, z weryfikacją SHA-256). [`path`: nadpisanie]
- `series select` — Wybierz stacje, zmienne i lata z bieżącego szeregu (bez zapisu; wejście projektu).
- `series read` — Odczytaj wartości i flagi szeregu jednej stacji z magazynu.
- `series summary` — Pokaż pokrycie stacji i zmiennych szeregu ze spisu series.json (bez pyarrow).
- `series export` — Wyeksportuj szereg jednej stacji jako CSV z atrybucją dostawcy danych. [`path`: nadpisanie]
- `project status` — Pokaż stan przypiętych plików zadań projektu (offline). [lokalna]
- `project verify` — Zweryfikuj sumy SHA-256 przypiętych plików projektu (offline). [lokalna]
- `commands list` — Wypisz komendy katalogu: nazwy narzędzi, skutki i trasy.
- `commands schema` — Pokaż schemat JSON opcji komendy albo cały katalog komend imgw-commands/1.
- `commands guide` — Wygeneruj przewodnik dla agentów AI: AGENTS.md albo llms.txt, po polsku albo angielsku. [`path`: nadpisanie]

**Sieć — łączy się ze źródłem, nic nie zapisuje**

- `stations find` — Znajdź stacje IMGW-PIB i ČHMÚ po nazwie, rzece albo prefiksie kodu.
- `current hydro` — Pobierz bieżące dane hydrologiczne z API IMGW.
- `current meteo` — Pobierz bieżące dane meteorologiczne z API IMGW.
- `current synop` — Pobierz bieżące dane synoptyczne z API IMGW.
- `current warnings` — Pobierz bieżące ostrzeżenia hydrologiczne i meteorologiczne IMGW.
- `current hydro-states` — Pobierz stany wód stacji hydrologicznych ze współrzędnymi (mapa hydro.imgw.pl).
- `pmaxtp fetch` — Pobierz opady maksymalne PMAXTP dla punktu (na żywo, bez zapisu).
- `store check` — Sprawdź aktualność archiwów zbiorów bez pobierania danych. [`plan`: nadpisanie; jest sprawdzeniem]
- `project check` — Sprawdź aktualność danych zadań projektu bez zapisu do magazynu. [`plan`: nadpisanie; jest sprawdzeniem; lokalna]

**Zapis — nowe pliki, wersje albo zadania; najpierw `--check`**

- `pmaxtp sync` — Pobierz komórkę PMAXTP dla punktu i zapisz ją jako wersję w magazynie.
- `store init` — Utwórz pusty magazyn IMGW (znacznik imgw-store.json) we wskazanym katalogu. [lokalna]
- `store sync` — Pobierz nowe lub brakujące archiwa do magazynu według planu albo wyboru zbiorów i stacji.
- `store catalog` — Zbuduj wersjonowany katalog stacji stations.geojson jednego dostawcy.
- `series build` — Zbuduj szereg Parquet zbioru z bieżących wersji archiwów magazynu.
- `project init` — Utwórz manifest projektu imgw-project.json wskazujący magazyn. [lokalna]
- `project add` — Dodaj zadanie do manifestu projektu. [lokalna]

**Nadpisanie — może zastąpić istniejący plik albo manifest; najpierw `--check`**

- `datasets download` — Pobierz pliki źródłowe zbioru do katalogu odzwierciedlającego ścieżki serwera dostawcy. [lokalna]
- `project remove` — Usuń zadanie z manifestu projektu. [lokalna]
- `project set-store` — Wskaż nowy katalog magazynu projektu po weryfikacji przypiętych plików. [lokalna]
- `project download` — Pobierz i przypnij dane zadań projektu. [lokalna]

## Flagi i wartości

- Listy (`--datasets`, `--months`, `--params`, `--stations`, `--tasks`, `--variables`, `--years`): wartości po przecinku (`--months 1,2`) albo powtórzona flaga (`-s A -s B`). Roczniki (`--years`): `2024`, `2020-2023`, `2020,2022` albo `2018,2020-2023`. Daty (`--end`, `--start`): ISO `RRRR-MM-DD`.
- Przełączniki domyślnie włączone: `--series/--no-series` (`--no-…` wyłącza); pozostałe flagi logiczne (`--main-only`) nie mają wartości i włączają swoją opcję.
- Zmienne środowiskowe: `IMGW_STORE_ROOT` — domyślne `--root` (CLI, MCP stdio; `stations find` — tylko przy `source=store`); `IMGW_LANG` — język pomocy CLI i domyślne `--lang` (`pl`, `en`).

## Typowe przepływy

Symbole pisane wielkimi literami (`KOD_STACJI`, `KOD_WIGOS`, `PROJEKT`) zastąp wartościami z wcześniejszych kroków.

### 1. Opady dobowe ze stacji Poznań, 2010–2020

1. `imgw stations find --kind meteo --query poznan` — kilka trafień → zapytaj użytkownika; kod wybranej stacji to `KOD_STACJI`.
2. Wybierz zbiór: `pl.imgw.meteo_precip_daily` (stacje opadowe, `P`) albo `pl.imgw.meteo_climate_daily` (stacje klimatyczne, `P` i temperatury) — lista stacji nie mówi, w której sieci jest stacja.
3. `imgw store check --root /dane/imgw --datasets pl.imgw.meteo_precip_daily --years 2010-2020` — plan: liczba plików i bajtów; archiwa obejmują cały kraj, więc podaj użytkownikowi rozmiar.
4. `imgw store sync --root /dane/imgw --datasets pl.imgw.meteo_precip_daily --years 2010-2020` — po zgodzie użytkownika; szeregi stacji budują się same.
5. `imgw series summary --root /dane/imgw --dataset pl.imgw.meteo_precip_daily --stations KOD_STACJI` — brak stacji → powtórz kroki 3–5 z `pl.imgw.meteo_climate_daily`; brak w obu → powiedz to użytkownikowi, nie podstawiaj innej stacji.
6. `imgw series read --root /dane/imgw --dataset pl.imgw.meteo_precip_daily --station KOD_STACJI --variables P --start 2010-01-01 --end 2020-12-31 --limit 500` — kolejne strony: `--offset`.

### 2. Przepływy dobowe stacji czeskiej (ČHMÚ)

1. `imgw stations find --kind hydro --query spindleruv --provider CHMI` — identyfikator WIGOS wybranej stacji to `KOD_WIGOS`.
2. `imgw store check --root /dane/imgw --datasets cz.chmi.hydro_daily --years 2020-2025 --stations KOD_WIGOS` — plan: pliki stacji po latach.
3. `imgw store sync --root /dane/imgw --datasets cz.chmi.hydro_daily --years 2020-2025 --stations KOD_WIGOS` — po zgodzie użytkownika.
4. `imgw series read --root /dane/imgw --dataset cz.chmi.hydro_daily --station KOD_WIGOS --variables Q --limit 500` — kolejne strony: `--offset`.

### 3. Odtwarzalny projekt

1. `imgw project init --project-dir PROJEKT --store-dir ../magazyn` — manifest `imgw-project.json`; `store_dir` względem katalogu projektu.
2. `imgw project add --project-dir PROJEKT --name opady --command 'series select' --options '{"dataset":"pl.imgw.meteo_precip_daily","stations":["KOD_STACJI"],"years":"2010-2020"}'` — zadanie zapamiętuje komendę i jej opcje (bez `root`).
3. `imgw project download --project-dir PROJEKT --check` — plan…
4. `imgw project download --project-dir PROJEKT` — …potem pobranie i przypięcie plików (SHA-256) po zgodzie użytkownika.
5. `imgw project verify --project-dir PROJEKT` — sumy SHA-256 przypiętych plików (offline).

## Czego nie robić

1. Nie buduj URL-i serwerów IMGW-PIB i ČHMÚ ręcznie ani ich nie przeszukuj — `datasets files`, `datasets download`, `store sync`.
2. Kody wyjścia 10 i 11 nie oznaczają awarii programu — przeczytaj kopertę (`items[].status`, `error_code`).
3. Nie uruchamiaj zapisu (`store sync`, `series build`, `datasets download`, `project download`) bez planu i zgody użytkownika; w MCP zapis włącza użytkownik, nie agent.
4. Nie zgaduj stacji ani zbioru: przy kilku trafieniach `stations find` zapytaj; obecność stacji w zbiorze sprawdź `series summary`.
5. Nie edytuj, nie przenoś i nie usuwaj plików magazynu (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — magazyn jest tylko przyrostowy.
6. Nie pobieraj „na zapas”: zawężaj `years`, `months` i `stations`; nie mieszaj dostawców w jednym wywołaniu ze `stations`.
7. Długie listy czytaj stronami (`limit`, `offset`); używaj `series read` albo `series export --path`, nie CSV w kontekście.
8. Nie odpytuj `current …` w pętli — to API na żywo; zachowaj wynik.
9. Przekaż użytkownikowi komunikat `license_terms` i atrybucję (IMGW-PIB: warunki celu użycia; ČHMÚ: CC BY 4.0).
10. `version` wskazuj wyłącznie pod `*/versions/` magazynu, bez `..`; w REST i MCP przez HTTP — względnie do magazynu serwera.

Rozwijasz to repozytorium? Przeczytaj CLAUDE.md.
