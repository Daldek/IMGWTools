# IMGWTools — przewodnik dla agentów (wersja 3.0.0)

> Plik generowany z katalogu komend: `imgw commands guide --format agents --lang pl --path AGENTS.md`.
> Nie edytuj ręcznie. Wersja angielska: `imgw commands guide --lang en`.

## Czym jest IMGWTools

IMGWTools to biblioteka Pythona, CLI `imgw`, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych: archiwów, danych bieżących i opadów maksymalnych prawdopodobnych PMAXTP. Archiwa trafiają do wersjonowanego magazynu — zwykłego katalogu, w którym wersje są niezmienne, a ich tożsamością jest SHA-256 — i z niego, offline, czyta się szeregi stacji. Wszystkie interfejsy powstają z jednego katalogu komend, więc mają te same nazwy opcji, walidację, kopertę wyniku i kody błędów. Wersja 3.0.0: rejestr 17 zbiorów 2 dostawców (IMGW-PIB — Polska, ČHMÚ — Czechy) i jeden katalog 38 komend w 8 grupach dla wszystkich interfejsów.

| Dostawca | Nazwa | Kraj | Klucze zbiorów | Licencja | Kod stacji |
|---|---|---|---|---|---|
| `IMGW-PIB` | IMGW-PIB (Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy) | Polska (PL) | `pl.imgw.*` | [IMGW-PIB](https://danepubliczne.imgw.pl/regulations) | `^[0-9]{9}$` |
| `CHMI` | ČHMÚ (Český hydrometeorologický ústav) | Czechy (CZ) | `cz.chmi.*` | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | `^0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}$` |

## Zasady: sprawdź → uruchom → przeczytaj

1. **Poznaj komendy:** `imgw commands list` (spis z opisem jednego zdania), potem `imgw commands schema --command … [--lang en]` albo `imgw <grupa> <komenda> --schema`; REST `GET /api/v1/commands/list` i `/schema`; w MCP `imgw_commands_list` i `imgw_commands_schema`. Opcje to właściwości JSON Schema; reguły nieopisane schematem są w `x-imgw.rules`, skutki w `x-imgw.writes`, `x-imgw.network` i `x-imgw.idempotent`.
2. **Sprawdź bez zapisu:** `--check` (CLI), `?check=true` (REST, POST), `check: true` (MCP; domyślne dla komend zapisujących), `check_command()` (Python) → plan `imgw-plan/1` bez zapisu i bez pobierania treści. `store check` i `project check` same są sprawdzeniem. Przy dużym planie zapytaj użytkownika.
3. **Uruchom:** bez `check`; czytaj `status` koperty, nie tylko kod wyjścia.
4. **Czytaj offline:** `store info`, `store scan`, `series summary`, `series read` (`limit`/`offset`), `pmaxtp read` — bez ponownego pobierania.
5. **Decyduj po kodach:** `code`, `status`, `items[].status`, `error_code`; tekst `detail` jest dla człowieka.

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

| Status | Kod wyjścia CLI | Znaczenie |
|---|---|---|
| `ok` | 0 | bez porażek |
| `partial` | 10 | część pozycji nieudana — przeczytaj `items[].status` i `error_code`; pozostałe są gotowe |
| `failed` | 11 | żadna pozycja się nie udała (w planie: `check_failed`); koperta jest pełna |
| `cancelled` | 130 | przerwano (Ctrl+C, anulowanie żądania); `result` częściowy albo `null` |

Błąd ma kod z zamkniętego rejestru, ten sam w Pythonie (`IMGWError.code`), CLI (ostatnia linia stderr i kod wyjścia), REST (problem+json i status HTTP) i MCP (`isError`); `details.option` wskazuje błędną opcję, a `—` — interfejs, który danego kodu nie zgłasza.

| Kod | Tytuł | Kod wyjścia CLI | HTTP |
|---|---|---|---|
| `validation_error` | Nieprawidłowe dane wejściowe | 2 | 400 |
| `not_found` | Nie znaleziono | 3 | 404 |
| `conflict` | Konflikt stanu | 4 | 409 |
| `source_unavailable` | Źródło danych niedostępne | 5 | 502 |
| `missing_dependency` | Brak opcjonalnej zależności | 6 | 503 |
| `data_error` | Niepoprawne dane | 7 | 500 |
| `store_unavailable` | Magazyn niedostępny | 8 | 503 |
| `io_error` | Błąd systemu plików | 9 | 500 |
| `cancelled` | Operację anulowano | 130 | — |
| `forbidden` | Brak uprawnień do zapisu | 12 | 403 |
| `method_not_allowed` | Niedozwolona metoda HTTP | — | 405 |
| `internal_error` | Błąd wewnętrzny | 1 | 500 |

## Zbiory danych

Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`; slug (`hydro_daily`) i alias legacy (`hydro/dobowe`) są przyjmowane wyłącznie na wejściu — wyniki i sloty magazynu podają pełny klucz.

| Klucz | Dostawca | Rodzaj | Jednostka czasu | Zmienne | Od roku | W magazynie | Zakres pliku | Alias legacy | Tytuł |
|---|---|---|---|---|---|---|---|---|---|
| `pl.imgw.hydro_daily` | `IMGW-PIB` | `hydro` | `day` | `H`, `Q`, `T` | 1951 | tak | `country` | `hydro/dobowe` | Dane hydrologiczne dobowe |
| `pl.imgw.hydro_monthly` | `IMGW-PIB` | `hydro` | `month` | `H_min`, `H_mean`, `H_max`, `Q_min`, `Q_mean`, `Q_max`, `T_min`, `T_mean`, `T_max` | 1951 | tak | `country` | `hydro/miesieczne` | Dane hydrologiczne miesięczne |
| `pl.imgw.hydro_semiannual` | `IMGW-PIB` | `hydro` | `half_year` | `H_min`, `H_mean`, `H_max`, `Q_min`, `Q_mean`, `Q_max`, `T_min`, `T_mean`, `T_max` | 1951 | tak | `country` | `hydro/polroczne_i_roczne` | Dane hydrologiczne półroczne i roczne |
| `pl.imgw.meteo_climate_daily` | `IMGW-PIB` | `meteo` | `day` | `Tmax`, `Tmin`, `Tmean`, `Tground`, `P`, `snow_cover` | 1951 | tak | `country` | `meteo/dobowe/klimat` | Dane meteorologiczne dobowe ze stacji klimatycznych |
| `pl.imgw.meteo_precip_daily` | `IMGW-PIB` | `meteo` | `day` | `P`, `snow_cover`, `fresh_snow` | 1950 | tak | `country` | `meteo/dobowe/opad` | Dane meteorologiczne dobowe ze stacji opadowych |
| `pl.imgw.hydro_stations` | `IMGW-PIB` | `hydro` | `station_list` | — | — | tak | `country` | — | Lista stacji hydrologicznych |
| `pl.imgw.meteo_stations` | `IMGW-PIB` | `meteo` | `station_list` | — | — | tak | `country` | — | Lista stacji meteorologicznych |
| `pl.imgw.pmaxtp` | `IMGW-PIB` | — | `cell` | `ks`, `sg`, `rb` | — | tak | `country` | — | Opady maksymalne prawdopodobne PMAXTP |
| `pl.imgw.hydro_phenomena` | `IMGW-PIB` | `hydro` | `day` | — | 1951 | nie | `country` | — | Zjawiska hydrologiczne dobowe |
| `pl.imgw.meteo_climate_monthly` | `IMGW-PIB` | `meteo` | `month` | — | 1951 | nie | `country` | `meteo/miesieczne/klimat` | Dane meteorologiczne miesięczne ze stacji klimatycznych |
| `pl.imgw.meteo_precip_monthly` | `IMGW-PIB` | `meteo` | `month` | — | 1950 | nie | `country` | `meteo/miesieczne/opad` | Dane meteorologiczne miesięczne ze stacji opadowych |
| `pl.imgw.meteo_synop_monthly` | `IMGW-PIB` | `meteo` | `month` | — | 1960 | nie | `country` | `meteo/miesieczne/synop` | Dane meteorologiczne miesięczne ze stacji synoptycznych |
| `pl.imgw.meteo_climate_terms` | `IMGW-PIB` | `meteo` | `term` | — | 1951 | nie | `country` | `meteo/terminowe/klimat` | Dane meteorologiczne terminowe ze stacji klimatycznych |
| `cz.chmi.hydro_daily` | `CHMI` | `hydro` | `day` | `H`, `Q`, `T` | 1887 | tak | `station_year` | — | ČHMÚ — dane hydrologiczne dobowe (H, Q, T) |
| `cz.chmi.meteo_daily` | `CHMI` | `meteo` | `day` | `P`, `Tmean`, `Tmax`, `Tmin` | — | tak | `station_element` | — | ČHMÚ — dane meteorologiczne dobowe (opad, temperatura powietrza) |
| `cz.chmi.hydro_stations` | `CHMI` | `hydro` | `station_list` | — | — | tak | `country` | — | ČHMÚ — wykaz stacji hydrologicznych |
| `cz.chmi.meteo_stations` | `CHMI` | `meteo` | `station_list` | — | — | tak | `country` | — | ČHMÚ — wykaz stacji meteorologicznych |

- `stations` (identyfikatory WIGOS) jest wymagane dla `cz.chmi.*` i niedozwolone dla `pl.imgw.*` w `datasets files`, `datasets download`, `store check` i `store sync`; jedno wywołanie obejmuje zbiory jednego rodzaju: archiwa krajowe `pl.imgw.*` albo pliki stacji `cz.chmi.*`.
- `years`: wymagane w `datasets files` i `datasets download` (poza `cz.chmi.meteo_daily`) oraz dla `pl.imgw.*` w `store check` i `store sync`; tam opcjonalne dla `cz.chmi.hydro_daily` (brak = lata opublikowane); zawsze niedozwolone dla `cz.chmi.meteo_daily` (pliki obejmują całą historię stacji) i nie wcześniejsze niż „Od roku”.
- `months` wyłącznie dla `pl.imgw.*`; `params` (`H`, `Q`, `T`) wyłącznie dla `pl.imgw.hydro_semiannual`.
- Zbiory spoza magazynu („W magazynie” = `nie`) obsługują tylko `datasets files` i `datasets download`; listy stacji trafiają do magazynu przez `store catalog`, PMAXTP przez `pmaxtp sync`.
- Rok hydrologiczny IMGW-PIB trwa od 1 listopada do 31 października (`year_type`: `hydrological` albo `calendar`).

## Komendy

Tabela każdej grupy podaje komendę, funkcję Pythona i typ wyniku, opcje w kolejności katalogu (`*` — wymagana, `=` — wartość domyślna), skutek uruchomienia (`odczyt`; `sieć` — łączy się ze źródłem; `zapis` — wyłącznie nowe pliki, wersje albo zadania; `zapis z nadpisaniem` — może zastąpić istniejący plik; opcja przed dwukropkiem zapisuje plik, gdy ją podasz), bliźniaka `check` (`sama` — komenda jest sprawdzeniem, `—` — brak) i metodę REST (`—` — komenda lokalna, bez trasy). Pełny schemat opcji: `imgw commands schema --command "<komenda>"`.

### `datasets` — Rejestr dostawców i zbiorów: lista, pliki i pobieranie

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `datasets list` | Wypisz zbiory z rejestru: klucze, dostawców, aliasy legacy, zmienne i pierwszy rocznik. | `datasets` → `Page[DatasetDescriptor]` | `kind`, `provider`, `limit`, `offset=0` | odczyt | — | GET |
| `datasets files` | Wypisz pliki źródłowe zbioru dla wybranych roczników albo stacji (offline, bez pobierania). | `archive_files` → `Page[ArchiveFile]` | `dataset*`, `years`, `months`, `params`, `stations`, `limit`, `offset=0` | odczyt | — | GET |
| `datasets download` | Pobierz pliki źródłowe zbioru do katalogu odzwierciedlającego ścieżki serwera dostawcy. | `download_archives` → `DownloadReport` | `dataset*`, `years`, `months`, `params`, `stations`, `output=./data/downloaded` | sieć, zapis z nadpisaniem | `check_command` | — |
| `datasets providers` | Wypisz dostawców danych z rejestru: identyfikatory, kraje, licencje, wzorce kodów stacji i zbiory. | `providers` → `Page[ProviderDescriptor]` | `limit`, `offset=0` | odczyt | — | GET |

### `stations` — Wyszukiwanie stacji

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `stations find` | Znajdź stacje IMGW-PIB i ČHMÚ po nazwie, rzece albo prefiksie kodu. | `find_stations` → `Page[StationListEntry]` | `kind`, `query`, `source=live`, `root`, `provider`, `limit`, `offset=0` | sieć | `check_command` | GET |

### `current` — Dane bieżące z API IMGW

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `current hydro` | Pobierz bieżące dane hydrologiczne z API IMGW. | `fetch_hydro_current` → `Page[HydroCurrentData]` | `station`, `limit`, `offset=0` | sieć | `check_command` | GET |
| `current meteo` | Pobierz bieżące dane meteorologiczne z API IMGW. | `fetch_meteo_current` → `Page[MeteoCurrentData]` | `station`, `limit`, `offset=0` | sieć | `check_command` | GET |
| `current synop` | Pobierz bieżące dane synoptyczne z API IMGW. | `fetch_synop` → `Page[SynopData]` | `station`, `station_name`, `limit`, `offset=0` | sieć | `check_command` | GET |
| `current warnings` | Pobierz bieżące ostrzeżenia hydrologiczne i meteorologiczne IMGW. | `fetch_warnings` → `Page[WarningData]` | `kind`, `limit`, `offset=0` | sieć | `check_command` | GET |
| `current hydro-states` | Pobierz stany wód stacji hydrologicznych ze współrzędnymi (mapa hydro.imgw.pl). | `fetch_hydro_states` → `Page[HydroState]` | `main_only=false`, `limit`, `offset=0` | sieć | `check_command` | GET |

### `pmaxtp` — Opady maksymalne PMAXTP

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `pmaxtp fetch` | Pobierz opady maksymalne PMAXTP dla punktu (na żywo, bez zapisu). | `fetch_pmaxtp` → `PMaXTPResult` | `latitude*`, `longitude*`, `method=POT` | sieć | `check_command` | GET |
| `pmaxtp url` | Zbuduj adres URL API PMAXTP dla punktu (offline, bez pobierania). | `build_pmaxtp_url` → `str` | `latitude*`, `longitude*`, `method=POT` | odczyt | — | GET |
| `pmaxtp check` | Sprawdź komórkę PMAXTP w magazynie bez pobierania danych. | `check_pmaxtp` → `StorePlan` | `root*`, `latitude*`, `longitude*`, `method=POT`, `ind_x`, `ind_y` (`ind_x` wymaga `ind_y`; `ind_y` wymaga `ind_x`) | odczyt | sama | GET |
| `pmaxtp sync` | Pobierz komórkę PMAXTP dla punktu i zapisz ją jako wersję w magazynie. | `sync_pmaxtp` → `PMaXTPStoreResult` | `root*`, `latitude*`, `longitude*`, `method=POT`, `ind_x`, `ind_y` (`ind_x` wymaga `ind_y`; `ind_y` wymaga `ind_x`) | sieć, zapis | `check_pmaxtp` | POST |
| `pmaxtp read` | Odczytaj zapisaną komórkę PMAXTP z magazynu (offline). | `read_pmaxtp` → `PMaXTPResult` | `root*`, `ind_x*`, `ind_y*`, `method=POT`, `version` | odczyt | — | GET |

### `store` — Wersjonowany magazyn

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `store init` | Utwórz pusty magazyn IMGW (znacznik imgw-store.json) we wskazanym katalogu. | `init_store` → `StoreHandle` | `root*` | zapis | `check_command` | — |
| `store info` | Pokaż stan magazynu IMGW i obsługiwane kontrakty (offline, bez zapisu). | `store_info` → `StoreInfo` | `root*` | odczyt | — | GET |
| `store scan` | Wypisz wersje i problemy magazynu IMGW (offline, bez zapisu). | `iter_store` → `Page[StoreEntry]` | `root*`, `kind`, `provider`, `limit`, `offset=0` | odczyt | — | GET |
| `store check` | Sprawdź aktualność archiwów zbiorów bez pobierania danych. Źródła: listing i HEAD (IMGW-PIB), sam listing serwera (ČHMÚ). | `check_store` → `StorePlan` | `root*`, `datasets*`, `years`, `months`, `stations`, `plan` | sieć; `plan`: zapis z nadpisaniem | sama | GET |
| `store sync` | Pobierz nowe lub brakujące archiwa do magazynu według planu albo wyboru zbiorów i stacji. | `sync_store` → `SyncReport` | `root*`, `plan`, `datasets`, `years`, `months`, `stations`, `series=true` (dokładnie jedno z: `plan` / `datasets`) | sieć, zapis | `check_store` | POST |
| `store catalog` | Zbuduj wersjonowany katalog stacji stations.geojson jednego dostawcy. | `build_catalog` → `CatalogReport` | `root*`, `provider=IMGW-PIB`, `user_locations` | sieć, zapis | `check_catalog` | POST |
| `store export` | Wyeksportuj rekordy jednej wersji archiwum jako CSV albo JSONL (offline, z weryfikacją SHA-256). | `export_archive` → strumień linii | `version*`, `root`, `format=csv`, `path` | odczyt; `path`: zapis z nadpisaniem | `check_command` | GET |

### `series` — Szeregi stacji

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `series build` | Zbuduj szereg Parquet zbioru z bieżących wersji archiwów magazynu. | `build_series` → `SeriesReport` | `root*`, `dataset*` | zapis | `check_series` | POST |
| `series select` | Wybierz stacje, zmienne i lata z bieżącego szeregu (bez zapisu; wejście projektu). | `select_series` → `SeriesSelection` | `root*`, `dataset*`, `stations*`, `variables`, `years`, `year_type` | odczyt | — | GET |
| `series read` | Odczytaj wartości i flagi szeregu jednej stacji z magazynu. | `read_series` → `Page[NormalizedRecord]` | `version`, `root`, `dataset`, `station*`, `variables`, `start`, `end`, `limit`, `offset=0` (dokładnie jedno z: `version` / `dataset`+`root`) | odczyt | — | GET |
| `series summary` | Pokaż pokrycie stacji i zmiennych szeregu ze spisu series.json (bez pyarrow). | `summarize_series` → `Page[StationCoverage]` | `version`, `root`, `dataset`, `stations`, `variables`, `limit`, `offset=0` (dokładnie jedno z: `version` / `dataset`+`root`) | odczyt | — | GET |
| `series export` | Wyeksportuj szereg jednej stacji jako CSV z atrybucją dostawcy danych. | `export_series` → strumień linii | `version`, `root`, `dataset`, `station*`, `variables`, `start`, `end`, `year_type`, `format=csv`, `path` (dokładnie jedno z: `version` / `dataset`+`root`) | odczyt; `path`: zapis z nadpisaniem | `check_command` | GET |

### `project` — Projekty imgw-project/1

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `project init` | Utwórz manifest projektu imgw-project.json wskazujący magazyn. | `init_project` → `Project` | `project_dir*`, `store_dir*` | zapis | `check_command` | — |
| `project add` | Dodaj zadanie do manifestu projektu. | `add_project_task` → `Project` | `project_dir*`, `name*`, `command*`, `options*`, `geometry` | zapis | `check_command` | — |
| `project remove` | Usuń zadanie z manifestu projektu. | `remove_project_task` → `Project` | `project_dir*`, `name*` | zapis z nadpisaniem | `check_command` | — |
| `project set-store` | Wskaż nowy katalog magazynu projektu po weryfikacji przypiętych plików. | `set_project_store` → `Project` | `project_dir*`, `store_dir*` | zapis z nadpisaniem | `check_command` | — |
| `project download` | Pobierz i przypnij dane zadań projektu. | `download_project` → `ProjectReport` | `project_dir*`, `tasks`, `plan`, `update=pinned` | sieć, zapis z nadpisaniem | `check_project` | — |
| `project check` | Sprawdź aktualność danych zadań projektu bez zapisu do magazynu. | `check_project` → `StorePlan` | `project_dir*`, `tasks`, `plan` | sieć; `plan`: zapis z nadpisaniem | sama | — |
| `project status` | Pokaż stan przypiętych plików zadań projektu (offline). | `get_project_status` → `ProjectReport` | `project_dir*`, `tasks` | odczyt | — | — |
| `project verify` | Zweryfikuj sumy SHA-256 przypiętych plików projektu (offline). | `verify_project` → `ProjectReport` | `project_dir*`, `tasks` | odczyt | — | — |

### `commands` — Opis katalogu komend

| Komenda | Opis | Funkcja → wynik | Opcje | Skutek | Check | REST |
|---|---|---|---|---|---|---|
| `commands list` | Wypisz komendy katalogu: nazwy narzędzi, skutki i trasy. Zacznij tutaj, a opcje jednej komendy pobierz przez commands schema. | `list_commands` → `dict` | `lang=pl` | odczyt | — | GET |
| `commands schema` | Pokaż schemat JSON opcji komendy albo cały katalog komend imgw-commands/1. | `command_schema` → `dict` | `command`, `lang=pl` | odczyt | — | GET |
| `commands guide` | Wygeneruj przewodnik dla agentów AI: AGENTS.md albo llms.txt, po polsku albo angielsku. Powstaje z katalogu komend i rejestrów. | `agent_guide` → strumień linii | `format=agents`, `lang=pl`, `path` | odczyt; `path`: zapis z nadpisaniem | `check_command` | GET |

## Flagi i wartości

| Skrót | Flaga |
|---|---|
| `-d` | `--dataset`, `--datasets` |
| `-f` | `--format` |
| `-k` | `--kind` |
| `-m` | `--months` |
| `-o` | `--output` |
| `-p` | `--path` |
| `-q` | `--query` |
| `-r` | `--root` |
| `-s` | `--station`, `--stations` |
| `-y` | `--years` |
| `--lat` | `--latitude` |
| `--lon` | `--longitude` |

- Listy (`--datasets`, `--months`, `--params`, `--stations`, `--tasks`, `--variables`, `--years`): wartości po przecinku (`--months 1,2`) albo powtórzona flaga (`-s A -s B`).
- Roczniki (`--years`): rocznik `2024`, zakres `2020-2023`, lista `2020,2022` albo zakresy na liście (`2018,2020-2023`).
- Daty (`--end`, `--start`): ISO `RRRR-MM-DD`.
- Przełączniki domyślnie włączone: `--series/--no-series` (`--no-…` wyłącza); pozostałe flagi logiczne (`--main-only`) nie mają wartości i włączają swoją opcję.
- Obiekty JSON (`--options`): jeden argument powłoki, np. `--options '{"dataset": "pl.imgw.hydro_daily", "years": "2024"}'`.
- Każda komenda: `--schema` (schemat opcji bez uruchamiania); komendy z bliźniakiem: `--check` (plan bez zapisu).
- Zmienne środowiskowe: `IMGW_STORE_ROOT` — domyślne `--root` (CLI, MCP stdio; `stations find` — tylko przy `source=store`); `IMGW_LANG` — język pomocy CLI i domyślne `--lang` (`pl`, `en`).

## Typowe przepływy

Polecenia mają postać z `format_command` (roczniki rozwinięte do listy; `--years 2010-2020` działa tak samo). Symbole pisane wielkimi literami (`KOD_STACJI`, `KOD_WIGOS`, `PROJEKT`) zastąp wartościami z wcześniejszych kroków; w innym interfejsie użyj odwzorowania z sekcji „Interfejsy”.

### 1. Opady dobowe ze stacji Poznań, 2010–2020

1. `imgw stations find --kind meteo --query poznan` — kilka trafień → zapytaj użytkownika, nie wybieraj sam; kod wybranej stacji to `KOD_STACJI`.
2. Wybierz zbiór: `pl.imgw.meteo_precip_daily` (stacje opadowe, `P`) albo `pl.imgw.meteo_climate_daily` (stacje klimatyczne, `P` i temperatury) — lista stacji IMGW-PIB nie mówi, w której sieci jest stacja, a dobowe archiwa synoptyczne są plikami per stacja i nie są obsługiwane.
3. `imgw store check --root /dane/imgw --datasets pl.imgw.meteo_precip_daily --years 2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020` — plan: liczba plików i bajtów; archiwa IMGW-PIB obejmują cały kraj, więc podaj użytkownikowi rozmiar.
4. `imgw store sync --root /dane/imgw --datasets pl.imgw.meteo_precip_daily --years 2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020` — po zgodzie użytkownika; szeregi stacji budują się same (`--series` domyślnie).
5. `imgw series summary --root /dane/imgw --dataset pl.imgw.meteo_precip_daily --stations KOD_STACJI` — brak stacji w spisie → powtórz kroki 3–5 z `pl.imgw.meteo_climate_daily`; brak w obu → powiedz użytkownikowi, że obsługiwane zbiory nie mają danych tej stacji w tym okresie (np. stacja synoptyczna albo nieczynna), zamiast podstawiać inną stację.
6. `imgw series read --root /dane/imgw --dataset pl.imgw.meteo_precip_daily --station KOD_STACJI --variables P --start 2010-01-01 --end 2020-12-31 --limit 500` — kolejne strony: `--offset`.
7. `imgw series export --root /dane/imgw --dataset pl.imgw.meteo_precip_daily --station KOD_STACJI --variables P --start 2010-01-01 --end 2020-12-31 --path /dane/wyniki/opady.csv` — albo plik CSV: jednostki w nagłówku, flagi wartości, atrybucja w pierwszym wierszu danych.

### 2. Stan wody teraz

1. `imgw current hydro --station KOD_STACJI` — bieżący pomiar stacji z API IMGW-PIB na żywo; zachowaj wynik zamiast odpytywać w pętli.
2. `imgw current hydro-states --main-only` — stany wody stacji głównych ze współrzędnymi (`water_state`).

### 3. Opad maksymalny prawdopodobny (PMAXTP) dla punktu

1. `imgw pmaxtp fetch --latitude 52.23 --longitude 21.01` — metoda `POT` domyślnie (`--method AMP` — maksima roczne); punkt w Polsce.
2. `imgw pmaxtp sync --root /dane/imgw --latitude 52.23 --longitude 21.01 --check` — do magazynu: najpierw plan…
3. `imgw pmaxtp sync --root /dane/imgw --latitude 52.23 --longitude 21.01` — …potem zapis komórki siatki po zgodzie użytkownika.

### 4. Przepływy dobowe stacji czeskiej (ČHMÚ)

1. `imgw stations find --kind hydro --query spindleruv --provider CHMI` — identyfikator WIGOS wybranej stacji to `KOD_WIGOS`.
2. `imgw store check --root /dane/imgw --datasets cz.chmi.hydro_daily --years 2020,2021,2022,2023,2024,2025 --stations KOD_WIGOS` — plan: pliki stacji po latach.
3. `imgw store sync --root /dane/imgw --datasets cz.chmi.hydro_daily --years 2020,2021,2022,2023,2024,2025 --stations KOD_WIGOS` — po zgodzie użytkownika.
4. `imgw series read --root /dane/imgw --dataset cz.chmi.hydro_daily --station KOD_WIGOS --variables Q --limit 500` — kolejne strony: `--offset`.

### 5. Odtwarzalny projekt

1. `imgw project init --project-dir PROJEKT --store-dir ../magazyn` — manifest `imgw-project.json`; `store_dir` względem katalogu projektu.
2. `imgw project add --project-dir PROJEKT --name opady --command 'series select' --options '{"dataset":"pl.imgw.meteo_precip_daily","stations":["KOD_STACJI"],"years":[2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020]}'` — zadanie zapamiętuje komendę i jej opcje (bez `root`).
3. `imgw project download --project-dir PROJEKT --check` — plan…
4. `imgw project download --project-dir PROJEKT` — …potem pobranie i przypięcie plików (SHA-256) po zgodzie użytkownika.
5. `imgw project verify --project-dir PROJEKT` — sumy SHA-256 przypiętych plików (offline).

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
