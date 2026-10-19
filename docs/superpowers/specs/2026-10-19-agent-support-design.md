# Spec: wsparcie agentów AI w IMGWTools 3.0.0

**Data:** 2026-10-19  
**Status:** proponowana z ADR-004 (`docs/DECISIONS.md`); zakres i wydanie przesądziła decyzja właściciela przekazana 2026-10-19: przewodnik dla agentów (`AGENTS.md`, `llms.txt`), opisy angielskie katalogu, serwer MCP i porządek komunikatów legacy wchodzą do 3.0.0 razem z kodem dostawcy ČHMÚ (C02–C10)  
**ADR:** ADR-004 (D1–D12); ramy: ADR-002 (jeden katalog komend, koperta `imgw-result/1`, rejestr kodów błędów), ADR-003 (ČHMÚ; katalog 36 komend po C07)  
**Plan:** §11 (A01–A06), start po C07

Dokument jest kontraktem implementacji, nie deklaracją wykonania. Nazwy, pola, reguły i podpisy są zamrożone tutaj; rzeczywista sprzeczność → najpierw errata w tym dokumencie i w ADR-004, potem kod. Teksty dla człowieka w przykładach są wzorcowe, ostateczne brzmienie ustala task.

## 0. Źródła i oznaczenia

- **Kod:** gałąź `feature/chmi-agents`, commit `d8cb11c` (2026-10-19), przed C02–C10. Numery linii w §1.1 i §7 dotyczą tego commita; pliki zmieniane później przez taski C mają przesunięte linie, więc miejsca wyszukuje się po cytowanym tekście.
- **Pomiary [V] 2026-10-19:** `command_schema()` dla 35 komend = 45 697 B zwartego JSON; schematy opcji bez `$schema`, `title` i `x-imgw` (postać narzędzi MCP) = 26 367 B; pomoc CLI z Typer 0.27.3 i Click 8.5.0 (`imgw --help`, `imgw store sync --help`); OpenAPI aplikacji REST (`/openapi.json`) przed zmianami C02.
- **MCP:** specyfikacja 2026-07-28, rozdział *Tools* (nazwy narzędzi, adnotacje, `structuredContent`, błędy wykonania); SDK `mcp` z PyPI — wersja 2.3.0 z 2026-10-02 (`requires_python >=3.10`), informacje o wydaniu v2.0.0 z 2026-07-28 i dokumentacja `py.sdk.modelcontextprotocol.io` (*What's new in v2*, *The low-level Server*, *Tools*, *Add to an existing app*).
- **Konwencje plików:** llms.txt v2 (llmstxt.org, zmiana 2026-08-10); AGENTS.md (agents.md, format otwarty pod opieką Agentic AI Foundation).
- **Konsumenci:** Retman `docs/ARCHITECTURE.md` 3.2 (adaptery, manifest, handler), 4.1–4.3 (manifest), 8.1 (zbiór poleceń, „ściągnij opady z poznania”); Archiwista `docs/SPEC.md` 5.2 (decyzje technologiczne: „MCP jako dodatkowe wejście … po v1.0”), 7 (asystent), 12.7 (IMGW-11).
- Oznaczenia: **[V]** zweryfikowane (kod, pomiar, dokumentacja z datą), **[I]** wniosek, **[U]** otwarte — do potwierdzenia w tasku.

## 1. Zakres i granice

**W zakresie** (ADR-002 D14 wymieniał te pozycje jako poza zakresem; ADR-004 je realizuje):

1. **Przewodnik dla agentów** — `AGENTS.md` i `llms.txt` generowane z katalogu komend (`command_schema()`), więc nie mogą się rozjechać z kodem (§5).
2. **Opisy angielskie** — `help_en`, `description_en`, `rules_en` w katalogu, angielskie tytuły grup, błędów i zbiorów; wybór języka w Pythonie, CLI, REST i MCP; polski pozostaje domyślny (§4).
3. **Serwer MCP** — dodatek `imgwtools[mcp]`, narzędzia generowane z katalogu, domyślnie tylko odczyt i plan (`check`), zapis wyłącznie po jawnej fladze albo zmiennej środowiskowej, transport stdio i opcjonalnie Streamable HTTP w serwerze REST (§6).
4. **Porządek komunikatów legacy** — teksty bez polskich znaków i angielskie komunikaty dla człowieka, z dokładną listą miejsc (§7).

Każdy mechanizm jest ogólny: komendy i opcje ČHMÚ dodawane w C07 (`datasets providers`, `provider`, `stations`) oraz każda przyszła komenda trafiają do przewodnika, narzędzi MCP i opisów bez zmian w adapterach.

**Poza zakresem:** tłumaczenie `detail` wyjątków, `Notice.text`, komunikatów postępu, nagłówków i atrybucji CSV, wartości danych, web GUI i dokumentu OpenAPI; zasoby (`resources`) i podpowiedzi (`prompts`) MCP; zapis przez MCP po HTTP i autoryzacja MCP (OAuth); filtrowanie narzędzi MCP według grup lub dostawcy; kod Retmana i Archiwisty.

### 1.1 Stan wyjściowy [V]

| Obszar | Stan w `d8cb11c` |
|---|---|
| Katalog | 35 komend w 8 grupach (`data_commands()`); C07 dodaje `datasets providers` (36). Teksty dla człowieka wyłącznie po polsku: `CommandOption.help`, `DataCommand.description`, `DataCommand.rules`, `commands._GROUPS`, `ErrorSpec.title`, `DatasetDescriptor.title`. Brak informacji, czy komenda zapisuje albo łączy się z siecią. |
| `command_schema` | JSON Schema 2020-12 z `x-imgw` (funkcja, CLI, REST, bliźniak, typ wyniku, reguły); brak parametru języka. |
| CLI | Pomoc z katalogu po polsku, ale elementy Typer/Click po angielsku: „Options”, „Commands”, „Show this message and exit.”, „Usage:”, „[env var: …]”. Reguła domyślnego `root` dla `stations find` jest prywatną stałą `_ROOT_WHEN` w `cli/_dispatch.py:50`. |
| REST | Brak negocjacji języka. OpenAPI zawiera 9 tras stron HTML (`/`, `/download…`, `/stations…`, `/map`) z angielskimi podsumowaniami i opisami. `operationId` liczy `_Route.operation_id` w `api/routes/commands.py:182–183`. |
| Agenci | Brak `AGENTS.md`, `llms.txt` i serwera MCP; jedyną maszynową mapą jest `imgw commands schema` / `GET /api/v1/commands/schema`. |

## 2. Zasady wspólne

1. **Jedno źródło.** Przewodnik, narzędzia MCP, pomoc CLI i REST czytają komendy, opcje, reguły, skutki i teksty z katalogu (`data_commands()`, `command_schema()`) i rejestrów (`datasets()`, `providers()`, `ERROR_CODES`). Nigdzie nie powstaje druga lista komend ani druga walidacja: wartości normalizuje wyłącznie `validate_command` (spec 2026-10-17 §13.1 p. 3).
2. **Polski domyślnie.** Angielski jest wariantem tekstów katalogu i rejestrów wybieranym jawnie (§4). Identyfikatory, wartości wyliczeń, kody i pola JSON się nie zmieniają.
3. **Bez nowych kontraktów.** Rejestr kodów błędów pozostaje zamknięty (MCP używa istniejących kodów, w tym `forbidden`). Kontrakty magazynu się nie zmieniają; `imgw-commands/1` i `imgw-result/1` dostają wyłącznie pola addytywne (polityka IMGW-13).
4. **Agent domyślnie nie zapisuje.** Serwer MCP startuje bez prawa zapisu; komendy zapisujące zwracają wtedy plan `imgw-plan/1`. Nawet z włączonym zapisem pierwszym krokiem jest plan.
5. **Generyczność.** Oczekiwania testów (lista narzędzi, zawartość przewodnika) liczy się z katalogu, nie z przepisanych list.
6. **Pliki pochodne.** `AGENTS.md` i `llms.txt` są wynikiem generatora; zmiana katalogu, rejestru albo szablonu przewodnika regeneruje oba pliki w tej samej zmianie (§5.8).

## 3. Katalog: metadane dla agentów

### 3.1 Typy (addytywnie wobec spec 2026-10-17 §13.9 i spec ČHMÚ §9.4)

```python
Lang = Literal["pl", "en"]                  # imgwtools.commands.LANGS = ("pl", "en")
Writes = Literal["none", "add", "replace"]

# CommandOption       + help_en: str = ""          # niepusty dla każdej opcji katalogu (test)
#                     + writes: Writes = "none"    # podanie opcji zapisuje plik (np. path, plan w check)
# DataCommand         + description_en: str = ""
#                     + rules_en: tuple[str, ...] = ()        # ta sama liczba i kolejność co rules
#                     + writes: Writes = "none"               # skutek uruchomienia (nie check)
#                     + network: bool = False                 # łączy się z serwerem źródła dla jakiejkolwiek wartości opcji
#                     + env_root_when: Mapping[str, str] = {} # root z IMGW_STORE_ROOT tylko przy tych wartościach opcji;
#                                                             # pusta mapa = zawsze; zastępuje _ROOT_WHEN z cli/_dispatch.py
# ErrorSpec           + title_en: str
# DatasetDescriptor   + title_en: str = ""
# Settings (A01)      + lang: str = "pl"                      # IMGW_LANG; walidowane w miejscu użycia (§4.2)
# Settings (A05)      + mcp_enabled: bool = False             # IMGW_MCP_ENABLED
#                     + mcp_allowed_hosts: list[str] = ["127.0.0.1", "localhost"]   # IMGW_MCP_ALLOWED_HOSTS, po przecinku

def command_schema(command: str | None = None, /, *, lang: Lang = "pl") -> dict[str, object]: ...
def agent_guide(*, format: Literal["agents", "llms"] = "agents", lang: Lang = "pl",
                path: PathArg | None = None) -> Iterator[str] | Path: ...      # A02; imgwtools.__all__
```

Znaczenie `writes`: `none` — bez zmian plików i magazynu; `add` — wyłącznie nowe pliki, wersje, manifest albo zadanie (magazyn jest tylko przyrostowy, ADR-001 D1, więc relabeling z kopią to też `add`); `replace` — może nadpisać albo usunąć istniejącą treść użytkownika (manifest, plik wyniku, plik w katalogu pobierania). Pola mają wartości domyślne, więc obecne konstruktory działają bez zmian.

### 3.2 Skutki komend

Wartości dla A01; skutki deklarowane w katalogu sprawdza zachowanie (§9). Opcja zapisująca to opcja z `CommandOption.writes ≠ none`; ta sama nazwa opcji może mieć inny skutek w innej komendzie (`plan` zapisuje w `store check|project check`, a czyta w `store sync|project download`, spec 2026-10-17 §13.2).

| Komenda | `writes` | `network` | Opcje zapisujące | Uwagi |
|---|---|---|---|---|
| `datasets list` | `none` | nie | — | |
| `datasets files` | `none` | nie | — | URL-e offline |
| `datasets download` | `replace` | tak | — | pliki w `output` przez `os.replace` [V `fetch.py:911–923`] |
| `datasets providers` (C07) | `none` | nie | — | |
| `stations find` | `none` | tak | — | `source=store` bez sieci; `env_root_when={"source": "store"}` |
| `current hydro`, `current meteo`, `current synop`, `current warnings`, `current hydro-states` | `none` | tak | — | API na żywo IMGW |
| `pmaxtp fetch` | `none` | tak | — | |
| `pmaxtp url` | `none` | nie | — | |
| `pmaxtp check` | `none` | nie | — | bez żądań HTTP [V docstring `check_pmaxtp`] |
| `pmaxtp sync` | `add` | tak | — | |
| `pmaxtp read` | `none` | nie | — | |
| `store init` | `add` | nie | — | |
| `store info`, `store scan` | `none` | nie | — | |
| `store check` | `none` | tak | `plan` (`replace`) | listing i HEAD |
| `store sync` | `add` | tak | — | |
| `store catalog` | `add` | tak | — | |
| `store export` | `none` | nie | `path` (`replace`) | [V `store/export.py:192`] |
| `series build` | `add` | nie | — | |
| `series select`, `series read`, `series summary` | `none` | nie | — | |
| `series export` | `none` | nie | `path` (`replace`) | |
| `project init` | `add` | nie | — | |
| `project add` | `add` | nie | — | dopisuje zadanie (atomowy zapis manifestu) |
| `project remove`, `project set-store` | `replace` | nie | — | zmieniają istniejący manifest |
| `project download` | `replace` | tak | — | przypina i przy `update=upgrade` przepina piny; magazyn przyrostowo |
| `project check` | `none` | tak | `plan` (`replace`) | listing i HEAD [V docstring `check_project`] |
| `project status` | `none` | nie | — | bez haszowania [V docstring `get_project_status`] |
| `project verify` | `none` | nie | — | |
| `commands schema` | `none` | nie | — | |
| `commands guide` (A02) | `none` | nie | `path` (`replace`) | |

Niezmiennik (test A01): każda komenda z `writes ≠ none` ma bliźniaka `check` (`DataCommand.check ≠ None`), a każda opcja zapisująca należy do komendy z bliźniakiem albo do komendy, która sama jest sprawdzeniem (`store check`, `project check`). Dzięki temu MCP zawsze może zaproponować plan zamiast zapisu.

### 3.3 `command_schema` i `imgw-commands/1`

- Nowy parametr `lang` (domyślnie `"pl"`); dokument `imgw-commands/1` dostaje pole `"lang"`. W wybranym języku są: `description` komendy, `description` każdej właściwości, `x-imgw.rules`, `groups` i `errors[].title`.
- `x-imgw` każdej komendy dostaje `writes`, `network` i `operation_id` (= nazwa komendy ze spacją i `-` zamienionymi na `_`, np. `current_hydro_states`). `operation_id` jest jedynym miejscem tej reguły: czyta je REST (`operationId`, dziś liczony w `api/routes/commands.py:182–183`), adapter MCP (nazwa narzędzia) i przewodnik.
- Właściwość opcji zapisującej dostaje `"x-imgw-writes": "add" | "replace"` (obok istniejącego `x-imgw-type: path`).
- Dla `lang="pl"` teksty są identyczne jak dziś; dochodzą wyłącznie pola addytywne.
- Komenda `commands schema` dostaje opcję `lang` (`choice` `pl|en`, domyślnie `pl`; CLI: zmienna `IMGW_LANG` jako domyślna wartość flagi `--lang`; REST: domyślnie język z `Accept-Language`, §4.2).
- Niezmiennik (test A01): `command_schema(lang="en")` i `command_schema()` różnią się wyłącznie tekstami (opisy, reguły, tytuły grup i błędów, pole `lang`); właściwości, typy, `enum`, `pattern`, granice, `required`, `oneOf`, `dependentRequired` i nietekstowe pola `x-imgw` są równe. Język nie zmienia kontraktu.

### 3.4 Komenda `commands guide` (37.)

| Komenda | Funkcja | REST | Check | Wynik | Opcje |
|---|---|---|---|---|---|
| `commands guide` | `agent_guide` | `GET /api/v1/commands/guide` | `check_command` | strumień `text/markdown` albo `Path` | `format=agents` (`agents\|llms`), `lang=pl` (`pl\|en`), `path` |

- `format` zachowuje znaczenie z §13.2 spec 2026-10-17 („format strumienia wyniku”) i dostaje w tej komendzie wartości `agents|llms` (domyślnie `agents`). `path` = opcja `_PATH` (lokalna, w REST nieobecna; `writes="replace"`).
- Bez `path` funkcja zwraca iterator linii zakończonych `\n` (jak `store export` i `series export`); CLI pisze je na stdout, REST odpowiada `text/markdown; charset=utf-8` z `Content-Disposition: attachment; filename="AGENTS.md"` albo `"llms.txt"` oraz nagłówkami `X-IMGW-Status` i `X-IMGW-Notices` (spec 2026-10-17 §13.6). Z `path` wynik jest kopertą z `result` = ścieżka pliku.
- Bliźniak `check_command` daje plan z jedną akcją `PlanAction("commands guide", "current", "Przewodnik <format> (<lang>) → <ścieżka albo stdout>")`; `writes="none"`, `network=False`, bez reguł.
- Katalog liczy 37 komend (35 z ADR-002, `datasets providers` z ADR-003 D13, `commands guide` z ADR-004).

### 3.5 Reguła domyślnego `root`

CLI i serwer MCP w trybie stdio uzupełniają brakujący `root` wartością `IMGW_STORE_ROOT` dla każdej komendy z opcją `root`, gdy opcje spełniają `DataCommand.env_root_when` (pusta mapa = zawsze). Jedyna dzisiejsza wartość niepusta: `stations find` → `{"source": "store"}` (wyszukiwanie live odrzuca `root`, spec 2026-10-17 §13.10, nota U09). Zachowanie CLI się nie zmienia; reguła przechodzi z prywatnej stałej CLI do katalogu, więc oba adaptery stosują tę samą.

## 4. Opisy angielskie (pkt 6)

### 4.1 Teksty

| Element | Pole polskie | Pole angielskie | Właściciel |
|---|---|---|---|
| Opis komendy | `DataCommand.description` | `DataCommand.description_en` | A01 (37. komenda: A02) |
| Reguły komendy | `DataCommand.rules` | `DataCommand.rules_en` | A01 |
| Pomoc opcji | `CommandOption.help` | `CommandOption.help_en` | A01 |
| Opis grupy | `commands._GROUPS` | `commands._GROUPS_EN` | A01 |
| Tytuł błędu | `ErrorSpec.title` | `ErrorSpec.title_en` | A01 |
| Tytuł zbioru | `DatasetDescriptor.title` | `DatasetDescriptor.title_en` | A01 |

Zasady redakcji: ten sam zakres informacji co tekst polski; tryb rozkazujący w opisach komend (jak w polskich); identyfikatory, flagi, klucze i jednostki bez zmian, w odwrotnych apostrofach tak jak w tekście polskim. Słownik terminów: magazyn → *store*; zbiór → *dataset*; rocznik → *year*; szereg → *series*; stacja → *station*; koperta → *envelope*; przypięcie → *pin*; wersja → *version*; dostawca → *provider*; katalog stacji → *station catalog*; zadanie projektu → *project task*; sprawdzenie (check) → *check*.

Kompletność i spójność (testy A01): każdy tekst angielski jest niepusty, `rules_en` ma tyle pozycji co `rules`, a odwzorowanie tekstów pomocy polski ↔ angielski jest wzajemnie jednoznaczne w całym katalogu (dwie opcje o tej samej pomocy polskiej mają tę samą angielską i odwrotnie). Ostatni warunek wykrywa nadpisanie `help` w `replace(...)` bez nadpisania `help_en`.

### 4.2 Wybór języka

| Interfejs | Sposób | Domyślnie | Uwagi |
|---|---|---|---|
| Python | `command_schema(lang=)`, `agent_guide(lang=)`; `data_commands()` zwraca obiekty z oboma tekstami | `pl` | |
| CLI | `IMGW_LANG` (`Settings.lang`) — pomoc komend, opisy grup, elementy pomocy Typer/Click (§4.3) i domyślna wartość flagi `--lang` w `commands schema` i `commands guide` | `pl` | Wartość spoza `pl\|en` → każde wywołanie `imgw` kończy się linią błędu `validation_error` (`details.option="IMGW_LANG"`, `details.allowed=["pl","en"]`), kod 2. `--schema` przy komendzie używa języka z `IMGW_LANG`. |
| REST | opcja `lang` z zapytania > nagłówek `Accept-Language` > `pl` | `pl` | Reguła ogólna adaptera: każda komenda z opcją `lang` bez tej opcji w zapytaniu dostaje język z nagłówka. Problem+json: `title` w języku z nagłówka (z rejestru), `detail` po polsku. Odpowiedzi negocjowane mają `Content-Language` i `Vary: Accept-Language`. `IMGW_LANG` nie zmienia REST. |
| MCP | `imgw mcp --lang pl\|en` (domyślnie `IMGW_LANG`); HTTP: `IMGW_LANG` procesu serwera | `pl` | Lista narzędzi nie może zależeć od połączenia (MCP 2026-07-28 *Tools*), więc język ustala konfiguracja serwera, nie nagłówek żądania. |
| Web GUI | — | `pl` | bez zmian |

`Accept-Language` (RFC 9110 §12.5.4): elementy po przecinku, wagi `q` (brak = 1), dopasowanie po pierwszym podtagu (`en-GB` → `en`), wybór najwyższej wagi spośród `pl` i `en`, przy remisie — pierwszy na liście; brak dopasowania albo nagłówka → `pl`. Nagłówek jest wskazówką, więc nie daje błędu.

### 4.3 Pomoc CLI poza katalogiem

Elementy pomocy pochodzące z Typer/Click są w języku `IMGW_LANG`; po polsku: „Opcje” (`OPTIONS_PANEL_TITLE`), „Komendy” (`COMMANDS_PANEL_TITLE`), „Argumenty” (`ARGUMENTS_PANEL_TITLE`), „Pokaż pomoc i zakończ.” (opis `--help`), „Użycie:” (przedrostek linii użycia), „[zmienna środowiskowa: {}]” (`ENVVAR_STRING`), „[domyślnie: {}]” (`DEFAULT_STRING`), „[wymagane]” (`REQUIRED_LONG_STRING`); po angielsku — wartości Typer/Click. Panele „Opcje wymagane”/„Opcje”, metawartości (`LICZBA`, `LISTA`, `ŚCIEŻKA` …) i opisy `--check`/`--schema` z `cli/_dispatch.py` dostają warianty angielskie. Mechanizm: stałe `typer.rich_utils` ustawiane raz przy imporcie adaptera CLI oraz nadpisanie opisu opcji pomocy i przedrostka użycia w klasach `ImgwGroup` i `_CatalogCommand` (oraz w komendach spoza katalogu przez `cls=`) [U: nazwy stałych sprawdzone dla Typer 0.27.3; A01 potwierdza mechanizm `get_help_option` i `get_usage` na zainstalowanym Click].

### 4.4 Czego nie tłumaczymy

`detail` wyjątków, `Notice.text`, `Progress.message`, `variable_notes`, nagłówki i atrybucje CSV, wartości danych (np. `water_state`), web GUI, dokument OpenAPI, linia błędu CLI (nie ma `title`) oraz pomoc komend spoza katalogu (`imgw version|server|admin|mcp` — tylko po polsku). Agent anglojęzyczny dostaje kod i angielski `title`, a `detail` po polsku (`details` są strukturalne). Ewentualne tłumaczenie treści wykonania to osobna decyzja (§10, pytanie 2).

## 5. Przewodnik: `AGENTS.md` i `llms.txt` (pkt 4)

### 5.1 Generator i szablony

- Moduł `src/imgwtools/agent_guide.py` (rdzeń pakietu, bez dodatkowych zależności): publiczna funkcja `agent_guide` (§3.1) oraz wewnętrzna `_instructions(*, lang, mode, workdir, root) -> str` dla serwera MCP (§6.4).
- Szablony w `src/imgwtools/_data/agents/`: `agents.pl.md`, `agents.en.md`, `llms.pl.md`, `llms.en.md` — zwykły markdown pisany ręcznie, z liniami-znacznikami bloków generowanych w postaci `<!-- imgw:<blok> -->`. Generator zastępuje każdą taką linię blokiem; reszta szablonu przechodzi bez zmian (bez silnika szablonów: Jinja2 należy do dodatku `api`, a `string.Template` wymagałby ucieczek `$` w tekście). Nieznany znacznik albo blok użyty dwa razy to błąd programu wykrywany testem.
- Wynik jest deterministyczny: kolejność katalogu i rejestrów, brak dat i ścieżek lokalnych; jedyną zmienną jest wersja pakietu (`__version__`), więc podbicie wersji wymusza regenerację (§5.8).
- Pliki w repozytorium: `AGENTS.md` = `agent_guide(format="agents", lang="pl")`, `llms.txt` = `agent_guide(format="llms", lang="pl")`, oba w katalogu głównym, UTF-8, końce linii LF. Wersje angielskie powstają na żądanie (`imgw commands guide --lang en`), bez osobnych plików w repozytorium.

### 5.2 `AGENTS.md` — struktura

Konwencja agents.md służy agentom pracującym w repozytorium; ten plik obsługuje dwa przypadki: agenta, który **używa** IMGWTools (główna treść), i agenta, który **zmienia** kod (ostatnia sekcja odsyła do `CLAUDE.md` i standardów, bez ich powielania).

```markdown
# IMGWTools — przewodnik dla agentów (wersja <!-- imgw:version -->)

> Plik generowany z katalogu komend: `imgw commands guide --format agents --path AGENTS.md`.
> Nie edytuj ręcznie. Wersja angielska: `imgw commands guide --lang en`.

## Czym jest IMGWTools
(3–4 zdania: dane publiczne, magazyn wersjonowany offline, cztery interfejsy, jeden katalog)
<!-- imgw:providers -->

## Zasady: sprawdź → uruchom → przeczytaj
(5 punktów, §5.4)

## Interfejsy
(tabela Python / CLI / REST / MCP i reguła nazw narzędzi MCP)

## Koperta, statusy i błędy
<!-- imgw:statuses -->
<!-- imgw:errors -->

## Zbiory danych
<!-- imgw:datasets -->
(reguły opcji stations, years, months, params; aliasy legacy tylko na wejściu)

## Komendy
<!-- imgw:commands -->

## Flagi i wartości
<!-- imgw:flags -->

## Typowe przepływy
<!-- imgw:flows -->

## Czego nie robić
(lista §5.6)

## Praca nad kodem repozytorium
(→ CLAUDE.md, docs/DEVELOPMENT_STANDARDS.md, docs/RULES.md; bramka: .venv/bin/python -m pytest,
.venv/bin/ruff check src/ tests/, pyright; AGENTS.md i llms.txt regeneruje komenda z nagłówka)
```

### 5.3 Bloki generowane

| Blok | Źródło | Treść |
|---|---|---|
| `version` | `__version__` | numer wersji |
| `providers` | `providers()` | tabela: identyfikator, nazwa wyświetlana, kraj, przedrostek kluczy, licencja, wzorzec kodu stacji |
| `statuses` | `command_schema()["exit_codes"]` | statusy koperty `ok`, `partial`, `failed`, `cancelled` z kodami wyjścia 0, 10, 11, 130 i znaczeniem |
| `errors` | `ERROR_CODES` | kod, tytuł (w języku przewodnika), kod wyjścia CLI, status HTTP |
| `datasets` | `datasets()` | klucz, dostawca, rodzaj, jednostka czasu, zmienne, pierwszy rocznik, `in_store`, `archive_scope`, alias legacy, tytuł w języku przewodnika — także `cz.chmi.*` |
| `commands` | `command_schema(lang=)` | komenda, funkcja, opcje (wymagane z `*`, domyślne z `=`), skutek (`odczyt`, `sieć`, `zapis`, `zapis z nadpisaniem` z `writes`/`network`), bliźniak `check` (`—`, nazwa albo `sama`), metoda REST albo `—` |
| `flags` | `x-imgw.cli.flags` całego katalogu | aliasy krótkie z jednym znaczeniem (`-r` root, `-d` dataset(s), …), listy po przecinku albo powtórzona flaga, `--x/--no-x`, daty ISO, `years` `a-b`, opcja `--options` jako tekst JSON, zmienne `IMGW_STORE_ROOT`, `IMGW_LANG` |
| `flows` | dane przepływów w `agent_guide.py` (§5.4) | kroki renderowane przez `format_command` |
| `summary` (llms) | katalog i rejestry | liczba komend, grup, zbiorów i dostawców, wersja |

### 5.4 Zasady i przepływy

**Zasady (blok ręczny, ten sam w `AGENTS.md`, `llms.txt` i instrukcjach MCP):**

1. **Poznaj komendę:** `imgw commands schema [--command …] [--lang en]`, `imgw <grupa> <komenda> --schema`, `GET /api/v1/commands/schema`, w MCP `tools/list`. Opcje to właściwości JSON Schema; reguły nieopisane schematem są w `x-imgw.rules`, skutki w `x-imgw.writes` i `x-imgw.network`.
2. **Sprawdź bez zapisu:** `--check` (CLI), `?check=true` (REST, POST), `check: true` (MCP; domyślne dla komend zapisujących), `check_command()` (Python) → plan `imgw-plan/1` bez zapisu i bez pobierania treści. `store check` i `project check` same są sprawdzeniem. Przy dużym planie zapytaj użytkownika.
3. **Uruchom:** bez `check`; czytaj `status` koperty, nie tylko kod wyjścia.
4. **Czytaj offline:** `store info`, `store scan`, `series summary`, `series read` (`limit`/`offset`), `pmaxtp read` — bez ponownego pobierania.
5. **Decyduj po kodach:** `code`, `status`, `items[].status`, `error_code`; tekst `detail` jest dla człowieka.

**Przepływy** są danymi w module (`Flow(title_pl, title_en, steps=(Step(command, options, note_pl, note_en), …))`), renderowanymi przez `format_command`, więc składnia poleceń jest zawsze zgodna z katalogiem. Wartości zależne od wyniku wcześniejszego kroku są symbolami pisanymi wielkimi literami (`KOD_STACJI`, `KOD_WIGOS`, `PROJEKT`), które test podmienia na wartości fikcyjne (`123456789`, `0-203-1-900001`, katalog tymczasowy) i sprawdza `validate_command`. Przepływ w CLI wystarcza, bo tabela „Interfejsy” podaje odwzorowanie: Python `run_command("<komenda>", options={…})`, REST `/api/v1/<grupa>/<komenda>`, MCP narzędzie `<x-imgw.operation_id>` z argumentami = opcjami.

| # | Przepływ | Kroki |
|---|---|---|
| 1 | **Opady dobowe ze stacji Poznań, 2010–2020** (przypadek Retmana „ściągnij opady z poznania”) | (1) `stations find --kind meteo --query poznan` — kilka trafień → zapytaj użytkownika, nie wybieraj sam; (2) wybór zbioru: `pl.imgw.meteo_precip_daily` (stacje opadowe, `P`) albo `pl.imgw.meteo_climate_daily` (stacje klimatyczne, `P` i temperatury) — lista stacji IMGW nie mówi, w której sieci jest stacja, a dobowe archiwa synoptyczne są plikami per stacja i nie są obsługiwane; (3) `store check --root /dane/imgw --datasets pl.imgw.meteo_precip_daily --years 2010-2020` — plan: liczba plików i bajtów; archiwa IMGW obejmują cały kraj, więc podaj użytkownikowi rozmiar; (4) `store sync` z tymi samymi opcjami (szeregi budują się same, `--series` domyślnie); (5) `series summary --root /dane/imgw --dataset pl.imgw.meteo_precip_daily --stations KOD_STACJI` — brak stacji w spisie → powtórz 3–5 z `pl.imgw.meteo_climate_daily`; brak w obu → powiedz użytkownikowi, że obsługiwane zbiory nie mają danych tej stacji w tym okresie (np. stacja synoptyczna albo nieczynna), zamiast podstawiać inną stację; (6) `series read … --station KOD_STACJI --variables P --start 2010-01-01 --end 2020-12-31 --limit 500` (kolejne strony `--offset`) albo plik: `series export … --path opady.csv` (CSV z jednostkami, flagami i atrybucją w pierwszym wierszu). |
| 2 | Stan wody teraz | `current hydro --station KOD_STACJI`; mapa stanów: `current hydro-states --main-only` |
| 3 | Opad maksymalny prawdopodobny dla punktu | `pmaxtp fetch --latitude 52.23 --longitude 21.01` (metoda `POT` domyślnie); do magazynu: `pmaxtp sync --root /dane/imgw --latitude 52.23 --longitude 21.01 --check`, potem bez `--check` |
| 4 | Przepływy dobowe stacji czeskiej (ČHMÚ) | `stations find --provider CHMI --kind hydro --query spindleruv` → kod WIGOS; `store check --root /dane/imgw --datasets cz.chmi.hydro_daily --stations KOD_WIGOS --years 2020-2025`; `store sync` z tymi samymi opcjami; `series read --root /dane/imgw --dataset cz.chmi.hydro_daily --station KOD_WIGOS --variables Q --limit 500` |
| 5 | Odtwarzalny projekt | `project init --project-dir PROJEKT --store-dir ../magazyn`; `project add --project-dir PROJEKT --name opady --command "series select" --options '{"dataset": "pl.imgw.meteo_precip_daily", "stations": ["KOD_STACJI"], "years": "2010-2020"}'`; `project download --project-dir PROJEKT --check`, potem bez `--check`; `project verify --project-dir PROJEKT` |

Przepływ 4 używa opcji `provider` i `stations` z C07; przewodnik powstaje po C07, więc kroki przechodzą `validate_command`.

### 5.5 Interfejsy (blok ręczny)

| Interfejs | Odkrycie | Plan | Wynik | Błąd |
|---|---|---|---|---|
| Python | `command_schema()`, `data_commands()` | `check_command(…)` | `CommandResult` (`to_json()`) | `IMGWError` (`code`, `detail`, `details`) |
| CLI `imgw` | `imgw commands schema`, `--schema` | `--check` | koperta JSON w jednej linii stdout; kod wyjścia | ostatnia linia stderr `{"code","detail","details"}`; kod z rejestru |
| REST `/api/v1` | `GET /api/v1/commands/schema` | `?check=true` (POST) | 200 + koperta (`status` w treści) | `application/problem+json` |
| MCP | `tools/list` | `check: true` | `structuredContent` = koperta | `isError: true` + `{"code","title","detail","details"}` |

### 5.6 Czego nie robić (blok ręczny)

1. Nie buduj URL-i serwerów IMGW-PIB i ČHMÚ ręcznie ani ich nie przeszukuj — `datasets files`, `datasets download`, `store sync`.
2. Nie podejmuj decyzji na podstawie polskiego `detail` ani tekstu pomocy — decyduj po `code`, `status`, kodzie wyjścia i polach JSON.
3. Kody wyjścia 10 i 11 nie oznaczają awarii programu — przeczytaj kopertę (`items[].status`, `error_code`).
4. Nie uruchamiaj zapisu (`store sync`, `series build`, `datasets download`, `project download`) bez planu i zgody użytkownika; w MCP tryb zapisu włącza użytkownik, nie agent.
5. Nie zgaduj stacji ani zbioru: przy kilku trafieniach `stations find` zapytaj; obecność stacji w zbiorze sprawdź `series summary`.
6. Nie edytuj, nie przenoś i nie usuwaj plików magazynu (`archives/`, `series/`, `stations/`, `pmaxtp/`, `observations/`, `.incoming/`) — magazyn jest tylko przyrostowy, tożsamością wersji jest SHA-256.
7. Nie pobieraj „na zapas”: zawężaj `years`, `months` i `stations`; archiwa IMGW-PIB obejmują cały kraj, pliki ČHMÚ — pojedyncze stacje.
8. `stations` jest wymagane dla `cz.chmi.*` i zabronione dla `pl.imgw.*`; nie mieszaj dostawców w jednym wywołaniu ze `stations`; `years` jest zabronione dla `cz.chmi.meteo_daily`.
9. Nie oczekuj danych operacyjnych ČHMÚ (`now`, `recent`), dobowych archiwów synoptycznych IMGW ani PMAXTP poza Polską — nie są obsługiwane.
10. Długie listy czytaj stronami (`limit`, `offset`); nie wczytuj eksportów CSV do kontekstu — `series read` albo `series export --path`.
11. Nie odpytuj `current …` w pętli — to API na żywo; zachowaj wynik.
12. Przekaż użytkownikowi komunikat `license_terms` i atrybucję (IMGW-PIB: warunki celu użycia; ČHMÚ: CC BY 4.0).
13. `version` wskazuj wyłącznie pod `*/versions/` magazynu, bez `..`; w REST i MCP przez HTTP — względnie do magazynu serwera.
14. Ze stderr CLI czytaj tylko ostatnią linię JSON; postęp i komunikaty są dla człowieka.
15. Nie edytuj `AGENTS.md` ani `llms.txt` ręcznie — regeneruj je komendą z nagłówka.

### 5.7 `llms.txt`

Format llms.txt v2: H1 z nazwą, cytat z podsumowaniem, sekcje bez nagłówków, potem sekcje H2 z listami odnośników `- [nazwa](url): opis`, na końcu `## Optional`. Odnośniki prowadzą do surowych plików markdown gałęzi `master` (wydania), np. `https://raw.githubusercontent.com/Daldek/IMGWTools/master/AGENTS.md`. Wzór (`lang="pl"`; liczby i wersja z bloku `summary`):

```markdown
# IMGWTools

> Biblioteka Pythona, CLI, REST API i serwer MCP do danych publicznych IMGW-PIB (Polska) i ČHMÚ (Czechy): 17 zbiorów dwóch dostawców, wersjonowany magazyn archiwów i szeregów stacji, dane bieżące i PMAXTP. Wersja 3.0.0; jeden katalog 37 komend w 8 grupach dla wszystkich interfejsów.

- Cykl pracy: sprawdź (`--check`, `?check=true`, MCP `check: true`) → uruchom → czytaj offline (`store scan`, `series summary`, `series read`).
- Wynik: koperta JSON `imgw-result/1` z polem `status` (`ok`, `partial`, `failed`, `cancelled`; kody wyjścia CLI 0, 10, 11, 130).
- Błąd: `{"code", "detail", "details"}` w ostatniej linii stderr CLI albo `application/problem+json` w REST; kody z zamkniętego rejestru, np. `validation_error` = 2 / 400.
- Zbiory: pełne klucze `<kraj>.<dostawca>.<zbiór>`, np. `pl.imgw.hydro_daily`, `cz.chmi.hydro_daily`; kody stacji: IMGW-PIB 9 cyfr, ČHMÚ identyfikator WIGOS.
- Opis komend: `imgw commands schema` albo `GET /api/v1/commands/schema`; ten przewodnik w całości: `imgw commands guide`.

## Dokumentacja

- [AGENTS.md](https://raw.githubusercontent.com/Daldek/IMGWTools/master/AGENTS.md): przewodnik dla agentów — komendy, zbiory, flagi, kody błędów, przepływy, czego nie robić
- [README.md](https://raw.githubusercontent.com/Daldek/IMGWTools/master/README.md): instalacja i przykłady Python, CLI, REST, MCP
- [Architektura](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/ARCHITECTURE.md): moduły, magazyn, przepływ danych
- [Zmiany](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/CHANGELOG.md): zmiany i migracja z 2.x

## Optional

- [Rejestr decyzji](https://raw.githubusercontent.com/Daldek/IMGWTools/master/docs/DECISIONS.md): ADR-001–ADR-004
```

### 5.8 Dystrybucja i dryf

- **Repozytorium:** `AGENTS.md`, `llms.txt` w katalogu głównym (pliki pochodne).
- **Pakiet:** `imgw commands guide [--format llms] [--lang en] [--path …]`, `agent_guide()`; `GET /api/v1/commands/guide`.
- **Serwer REST:** `GET /llms.txt` (poza katalogiem, jak `/health`; A05) — treść `agent_guide(format="llms")` w języku z `Accept-Language`, `text/markdown; charset=utf-8`, bez `Content-Disposition`.
- **MCP:** instrukcje serwera (`instructions`) = blok „Zasady” + linie trybu z `_instructions` (§6.4); pełny przewodnik — narzędzie `commands_guide`.
- **Dryf:** test A02 porównuje bajty `AGENTS.md` i `llms.txt` z generatorem; komunikat porażki podaje polecenie regeneracji. Reguła ADR-004 D4: każda zmiana katalogu, rejestru zbiorów lub dostawców, rejestru błędów albo szablonu przewodnika regeneruje oba pliki w tej samej zmianie — także w taskach C po A02.

## 6. Serwer MCP (pkt 7)

### 6.1 Ocena SDK

| Wariant | Ocena |
|---|---|
| **`mcp` 2.x, niskopoziomowy `Server`** — wybrany | Oficjalne SDK; 2.3.0 z 2026-10-02, Python ≥3.10 [V]. Jeden `Server` obsługuje rewizję 2026-07-28 i klientów z ery 2025 przez stdio i Streamable HTTP [V informacje o wydaniu v2.0.0]. `Tool.input_schema` to dowolny słownik JSON Schema 2020-12 — dokładnie schemat z katalogu; SDK go ogłasza, ale nie stosuje [V *The low-level Server*], więc jedynym walidatorem pozostaje `validate_command` z polskim `detail` i `details.option`. Wyjątek z handlera staje się zanonimizowanym błędem protokołu −32603, więc błędy dla modelu zwracamy jako `CallToolResult(is_error=True)` [V]. `Client(server)` łączy się w pamięci — testy bez podprocesu [V]. `streamable_http_app()` daje aplikację Starlette do zamontowania, z listą dozwolonych hostów (`TransportSecuritySettings`; domyślnie tylko localhost, inne → 421) [V *Add to an existing app*]. |
| `mcp` 2.x, `MCPServer` (dawny `FastMCP`) z dekoratorami | Schemat z sygnatur funkcji: wymagałby generowania funkcji Pythona dla każdej komendy, a walidacja pydantic przed handlerem daje angielskie komunikaty i drugą walidację obok `validate_command`. Odrzucony. |
| `mcp` 1.x | Od 2026-07-28 w trybie utrzymania (wyłącznie poprawki bezpieczeństwa) [V]. Odrzucony. |
| Zewnętrzny `fastmcp` | Dodatkowa warstwa nad oficjalnym SDK bez potrzebnej tu funkcji. Odrzucony. |
| Własny JSON-RPC na stdio | Dwie ery protokołu (uzgadnianie wersji, `server/discover`), utwardzenie stdio i transport HTTP do utrzymania samodzielnie. Odrzucony. |

Koszt: `mcp` 2.3.0 wymaga m.in. `anyio`, `httpx2`, `jsonschema`, `mcp-types`, `opentelemetry-api`, `pydantic>=2.12`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, `starlette`, `uvicorn` [V PyPI] — dlatego wyłącznie jako dodatek; rdzeń nadal wymaga tylko `httpx` i `pydantic`. Nowsze 2.x mogą zmieniać API pomocnicze (2.0 → 2.3 w ok. dwa miesiące), stąd przypięcie `<3` i testy w pamięci; nazwy pomocników stdio i menedżera sesji potwierdza A03 na zainstalowanej wersji [U].

### 6.2 Układ, zależności i uruchamianie

```text
src/imgwtools/mcp/            # adapter MCP (dodatek imgwtools[mcp]); nie eksportowany w imgwtools.__all__
├── __init__.py               # opis modułu
├── _tools.py                 # narzędzia z katalogu: nazwa, opis, schemat, adnotacje (tryby §6.3)
├── _calls.py                 # wywołanie: stdio (check_command/run_command), http (trasy REST w procesie)
└── server.py                 # create_server(*, mode, lang), run_stdio(*, allow_writes, lang), http_app(*, lang)
```

- `pyproject.toml`: `mcp = ["imgwtools[cli]", "mcp>=2.3,<3"]`; `full = ["imgwtools[api,cli,mcp,pandas,store]"]` (więc także `dev`).
- `imgw mcp [--allow-writes] [--lang pl|en]` — komenda spoza katalogu, jak `imgw server` (ADR-004 D6). `--allow-writes` ma zmienną `IMGW_MCP_ALLOW_WRITES` (`true|false`), `--lang` — `IMGW_LANG`. Moduł MCP jest importowany dopiero w tej komendzie; bez dodatku linia błędu `missing_dependency` („Serwer MCP wymaga dodatku: pip install imgwtools[mcp]”), kod 6. Komenda nie pisze nic na stdout (stdout należy do protokołu; SDK dodatkowo przekierowuje stdout na stderr w trakcie pracy [V]).
- Streamable HTTP: montaż `/mcp` w `imgwtools.api.main:app`, gdy `IMGW_MCP_ENABLED=true` i dodatek jest zainstalowany; bez tego `/mcp` → 404 problem+json. Menedżer sesji SDK wchodzi w lifespan aplikacji REST (zamontowana aplikacja nie uruchamia własnego [V]); `IMGW_MCP_ALLOWED_HOSTS` → `TransportSecuritySettings(allowed_hosts=…)`.

### 6.3 Tryby i lista narzędzi

| Tryb | Uruchomienie | Narzędzia | Zapis | `root` i ścieżki |
|---|---|---|---|---|
| `read` (domyślny) | `imgw mcp` | każda komenda katalogu (37) | brak: komenda z `writes ≠ none` ma `check` stałe `true`; opcje zapisujące są usunięte ze schematu | jak w CLI: argument `root` albo `IMGW_STORE_ROOT` (§3.5); ścieżki względne liczone od katalogu roboczego serwera |
| `write` | `imgw mcp --allow-writes` albo `IMGW_MCP_ALLOW_WRITES=true` | każda komenda (37) | `check` domyślnie `true` dla komend z `writes ≠ none`; zapis przy `check: false` | jak wyżej |
| `http` | `imgw server` z `IMGW_MCP_ENABLED=true` → `/mcp` | komendy z trasą REST (`x-imgw.rest ≠ null`) | brak: komendy POST tylko z `check` stałym `true` (REST `?check=true`) | jak REST: magazyn serwera, wyłącznie opcje `rest="param"`, `version` względna do magazynu |

Lista jest deterministyczna (kolejność katalogu) i stała dla danego uruchomienia; zmienia się tylko z konfiguracją serwera (MCP 2026-07-28 *Tools*: lista nie może zależeć od połączenia). Lista narzędzi nie jest stronicowana.

### 6.4 Narzędzie z komendy

- **Nazwa:** `x-imgw.operation_id` (`store_sync`, `current_hydro_states`) — dozwolone znaki MCP (`A-Za-z0-9_-.`, ≤128) [V]; ta sama co `operationId` w REST. Bez przedrostka: klient łączący wiele serwerów rozróżnia narzędzia nazwą serwera (zalecenie specyfikacji).
- **Tytuł:** `imgw <komenda>`.
- **Opis:** `description` w języku serwera; gdy są reguły — akapit „Reguły:” z punktami `x-imgw.rules`; dla komendy zapisującej — zdanie trybu: `read`/`http` „Serwer MCP działa bez zapisu: wywołanie zwraca plan imgw-plan/1 (check).”, `write` „Domyślnie check=true (plan); zapis wymaga check=false.”
- **Schemat wejścia** (z `command_schema(name, lang=lang)`):
  1. usunąć `$schema` (MCP przyjmuje domyślnie 2020-12), `title` i `x-imgw`; usunąć słowa `x-imgw-*` z właściwości (zwykły JSON Schema dla klientów o ścisłych schematach; charakter ścieżki zostaje w opisie);
  2. usunąć opcje niedostępne w trybie: `http` — opcje z `rest ≠ "param"` (schemat opcji jak w REST, łącznie z `plan` `store sync` jako obiektem `imgw-plan/1`, czyli funkcja schematu opcji adaptera REST); `read` — opcje zapisujące;
  3. poprawić `required`, `dependentRequired` i `oneOf` po usunięciu: usunięte nazwy wypadają z grup, puste i powtórzone grupy znikają, a `oneOf` z pustą alternatywą znika (np. `series read` w `http`: `[version] | [dataset]`);
  4. stdio z ustawionym `IMGW_STORE_ROOT`: `root` znika z `required`, a jego opis kończy się „domyślnie: magazyn serwera MCP”;
  5. komendy listowe: `limit` dostaje `"default": 50` i `"maximum"` = `IMGW_API_MAX_LIMIT`;
  6. komendy z bliźniakiem (`x-imgw.check ≠ null`): właściwość `check` — `{"type": "boolean", "default": <writes ≠ none>, "description": …}`, a w trybach bez zapisu dla komendy zapisującej `{"const": true, "default": true, …}`; komendy, które same są sprawdzeniem, i odczyty bez bliźniaka nie mają `check`;
  7. opcja `lang` (`commands schema`, `commands guide`) ma `default` = język serwera.
- **Adnotacje:** `read_only_hint` = schemat narzędzia nie pozwala zapisać (`writes = none` i brak opcji zapisujących albo `check` stałe `true`); `destructive_hint` (tylko gdy zapis możliwy) = `writes = replace` albo dostępna opcja z `replace`; `open_world_hint` = `network`; `idempotent_hint` pominięte (domyślnie `false`). Adnotacje są wskazówkami dla klienta, nie zabezpieczeniem (specyfikacja MCP).
- **`_meta`:** `{"imgwtools/command": "<komenda>"}`.
- **Instrukcje serwera:** `_instructions(lang=…, mode=…, workdir=…, root=…)` = blok „Zasady” z §5.4, tryb (bez zapisu / zapis z `check: false` / HTTP), katalog roboczy, domyślny magazyn (`IMGW_STORE_ROOT` albo brak), domyślny rozmiar strony i wskazanie narzędzia `commands_guide`; poniżej 2 KiB.

Przykład (`read`, `lang="pl"`, ustawione `IMGW_STORE_ROOT`, stan przed C07; po C07 dochodzi `stations`):

```json
{
  "name": "store_sync",
  "title": "imgw store sync",
  "description": "Pobierz nowe lub brakujące archiwa IMGW do magazynu według planu albo wyboru zbiorów.\n\nReguły:\n- plan wyklucza datasets, years i months\n- roczniki nie wcześniejsze niż pierwszy rocznik każdego zbioru\n\nSerwer MCP działa bez zapisu: wywołanie zwraca plan imgw-plan/1 (check).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "root": {"type": "string", "description": "Katalog magazynu IMGW (CLI: domyślnie $IMGW_STORE_ROOT); domyślnie: magazyn serwera MCP"},
      "plan": {"type": "string", "description": "Plik planu imgw-plan/1 z komendy store check (zamiast datasets, years i months)"},
      "datasets": {"type": "array", "items": {"enum": ["pl.imgw.hydro_daily", "…"]}, "minItems": 1, "description": "…"},
      "years": {"type": "array", "items": {"anyOf": ["…"]}, "minItems": 1, "description": "…"},
      "months": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 12}, "minItems": 1, "description": "…"},
      "series": {"type": "boolean", "default": true, "description": "Buduj szeregi zbiorów po synchronizacji (--no-series wyłącza)"},
      "check": {"const": true, "default": true, "description": "Tylko plan imgw-plan/1 bez zapisu i bez pobierania (serwer bez zapisu)"}
    },
    "oneOf": [{"required": ["plan"]}, {"required": ["datasets", "years"]}],
    "additionalProperties": false
  },
  "annotations": {"readOnlyHint": true, "openWorldHint": true},
  "_meta": {"imgwtools/command": "store sync"}
}
```

### 6.5 Wywołanie

1. Nieznana nazwa → błąd protokołu JSON-RPC −32602 (`MCPError(INVALID_PARAMS, …)`), zgodnie ze specyfikacją.
2. `arguments` niebędące obiektem → błąd wykonania `validation_error`.
3. Argument będący opcją komendy, ale usunięty w tym trybie: opcja zapisująca albo `check: false` przy stałym `check` → `forbidden` z `details.reason="writes_disabled"` i `details.option`; w `http` — odpowiedź REST (400 `validation_error`, jak dziś dla opcji serwerowych i lokalnych). Nieznane opcje odrzuca `validate_command`.
4. `check` jest zdejmowany z opcji; komendy listowe bez `limit` dostają 50.
5. stdio: `root` według §3.5; wywołanie `check_command` albo `run_command` w wątku roboczym (anyio) z hakami `on_progress` (§6.8), `on_notice` (koperta deduplikuje) i `cancel`.
6. `http`: przekazanie do trasy REST w tym samym procesie (§6.9).

### 6.6 Wynik

- **Komendy obiektowe i listowe:** `structuredContent` = koperta `imgw-result/1` — w stdio `CommandResult.to_json(root=<root z opcji>)` jak w CLI, w `http` treść odpowiedzi REST; `content` = jeden `TextContent` z tym samym dokumentem w zwartym JSON (`ensure_ascii=False`, separatory `,` i `:`), czyli bajty linii stdout CLI bez końcowego `\n` (specyfikacja zaleca tekstową kopię `structuredContent`); `isError=false` dla każdej koperty, także `partial` i `failed` — jak REST 200 z polem `status`.
- **Strumienie** (`store export`, `series export`, `commands guide` bez `path`): `content` = tekst danych do 256 KiB (262 144 B w UTF-8), `structuredContent` = koperta z `result` = `{"format": <format>, "bytes": <n>, "lines": <k>}` (status i komunikaty jak w nagłówkach `X-IMGW-Status`/`X-IMGW-Notices` REST); większy strumień → przerwanie odczytu i błąd `validation_error` („Wynik przekracza 256 KiB; zawęź wybór, czytaj stronami series read albo zapisz plik opcją path”) z `details.maximum_bytes`. Odczyt strumienia nie ma skutków, więc przerwanie niczego nie zostawia. Z `path` (tylko `write`) — zwykła koperta ze ścieżką pliku.
- **Bez `outputSchema`:** `result` ma typ zależny od komendy, a błędy i strumienie mają inny kształt niż koperta; klient SDK sprawdza `structuredContent` względem zadeklarowanego `outputSchema` i zgłasza wyjątek przy niezgodności [V *The low-level Server*], a czy pomija to sprawdzenie przy `isError`, nie wiadomo [U]. Schemat koperty jest w `imgw-commands/1` (`result_schema`) i w przewodniku.

Przykład (`datasets_list`, `{"kind": "hydro", "limit": 1}`; skrócone; `total` po C07 = 5 zbiorów hydro IMGW-PIB i 2 ČHMÚ):

```json
{"content": [{"type": "text", "text": "{\"schema\":\"imgw-result/1\",\"command\":\"datasets list\",\"check\":false,\"status\":\"ok\",\"result\":{\"items\":[…],\"total\":7,\"limit\":1,\"offset\":0},\"notices\":[]}"}],
 "structuredContent": {"schema": "imgw-result/1", "command": "datasets list", "check": false, "status": "ok",
                       "result": {"items": ["…"], "total": 7, "limit": 1, "offset": 0}, "notices": []},
 "isError": false}
```

### 6.7 Błędy

- `IMGWError` → `isError=true`; `structuredContent` i tekst = `{"code", "title", "detail", "details"}`: `code`, `detail`, `details` jak w linii błędu CLI (spec 2026-10-17 §13.5), `title` z rejestru w języku serwera.
- `OSError` → `io_error` (`describe_os_error`, ten sam polski powód i `details.path` co CLI i REST); każdy inny wyjątek → `internal_error` z ogólnym `detail` („Błąd wewnętrzny serwera MCP; szczegóły w dzienniku serwera”), a ślad stosu na stderr.
- `IMGWCancelledError` bez anulowania przez klienta → `cancelled`; żądanie anulowane przez klienta nie dostaje odpowiedzi (zachowanie SDK [V]).
- `http`: problem+json z REST → ten sam dokument (`code`, `title`, `detail`, `details`).
- Brak nowych kodów; odmowa zapisu używa `forbidden` z rejestru (dziś tylko REST).

```json
{"code": "validation_error", "title": "Nieprawidłowe dane wejściowe",
 "detail": "Szerokość geograficzna 1.0 poza zakresem Polski (49.0–55.0)", "details": {"option": "latitude", "value": 1.0}}
```

### 6.8 Postęp, anulowanie, współbieżność

- **Postęp:** `Progress` z haka `on_progress` → `notifications/progress` (`progress` = `current`, `total`, `message` = tekst jak w CLI `[bieżący/łączny] …`) wyłącznie, gdy żądanie niesie `progressToken`; wysyłka z wątku roboczego przez pętlę zdarzeń anyio. Komunikaty `on_notice` trafiają do koperty (MCP-owe logowanie jest wycofywane, SEP-2577 [V]).
- **Anulowanie:** anulowanie żądania (`notifications/cancelled` albo przekroczony czas klienta) ustawia zdarzenie zwracane przez `cancel`; funkcja kończy pracę między plikami (R5, ADR-001 D9) z raportem częściowym albo `IMGWCancelledError`. Handler czeka na zakończenie wątku, więc magazyn pozostaje spójny (zapis atomowy, ADR-001).
- **Współbieżność:** każde wywołanie we własnym wątku; równoległe zapisy chronią gwarancje magazynu i blokady manifestu (ADR-001, `conflict`); brak globalnej blokady adaptera.

### 6.9 Streamable HTTP jako fasada REST

- Narzędzia trybu `http` odpowiadają trasom REST. Wywołanie budowane jest jak żądanie klienta REST i wysyłane do aplikacji `imgwtools.api.main:app` w tym samym procesie (transport ASGI, bez sieci): GET z parametrami zapytania (listy jako powtórzony parametr), POST z ciałem JSON i zawsze `?check=true`; nagłówek `Accept-Language` = język serwera MCP.
- Dzięki temu obowiązują bez drugiej implementacji wszystkie reguły serwera REST: root z `IMGW_STORE_ROOT` (503 `store_unavailable`), `version` pod `*/versions/`, plik `user_locations` z `IMGW_USER_LOCATIONS_DIR`, plan jako obiekt, `IMGW_API_MAX_LIMIT`, ukrywanie katalogów serwera (T21) i problem+json.
- Zapis przez HTTP nie istnieje w 3.0.0 (POST zawsze z `?check=true`), więc MCP nie korzysta z `IMGW_STORE_WRITE_TOKEN`.
- Odpowiedź 200 JSON → §6.6; strumień → §6.6 (status i komunikaty z nagłówków `X-IMGW-Status`, `X-IMGW-Notices`); problem+json → §6.7.
- Wdrożenie (A05): `location /mcp` w `docker/nginx.conf` z `limit_req` strefy `api_limit`, `proxy_http_version 1.1`, `proxy_buffering off` i dłuższym `proxy_read_timeout`; `IMGW_MCP_ENABLED` i `IMGW_MCP_ALLOWED_HOSTS` w `docker/docker-compose.yml`; obraz instaluje `.[api,mcp]`. Przy okazji A05 usuwa dwie usterki obrazu, które uniemożliwiają jego zbudowanie z pakietem 3.0.0 [V `docker/Dockerfile`]: bazę `python:3.11-slim` przy `requires-python >=3.12` i `COPY data/ data/` mimo braku katalogu `data/` w repozytorium.

### 6.10 Bezpieczeństwo

- **stdio:** granicą zaufania jest konto użytkownika — jak przy CLI. Zapis jest domyślnie wyłączony i włącza go użytkownik (flaga albo zmienna w konfiguracji klienta), nie model; nawet wtedy domyślnym wynikiem komendy zapisującej jest plan. Brak narzędzi usuwających dane; magazyn jest tylko przyrostowy, a narzędzia `replace` mają `destructiveHint`.
- **Wstrzyknięcie poleceń przez dane** (nazwy stacji, treści ostrzeżeń, komunikaty): wyniki są danymi; tryb `read` ogranicza skutek do odczytu, zapis wymaga decyzji użytkownika i `check: false`.
- **HTTP:** tylko odczyt i plan; reguły REST (§6.9); lista dozwolonych hostów SDK (obcy `Host` → 421 [V]); limit `nginx` dla `/mcp`; klienci przeglądarkowi nieobsługiwani w 3.0.0: IMGWTools przekazuje SDK wyłącznie `allowed_hosts`, więc pochodzenia (`Origin`) zostają przy domyślnej, najwęższej liście SDK, a pochodzenie spoza listy SDK odrzuca kodem 403 [V *Add to an existing app*].
- **Etykieta sieciowa:** `openWorldHint` przy komendach sieciowych, reguła 11 przewodnika, żądania sekwencyjne biblioteki; po HTTP — limit `nginx`. Specyfikacja MCP wymaga ograniczania wywołań po stronie serwera: dla HTTP spełnia to `nginx`; dla stdio (lokalny proces jednego użytkownika) ograniczeniem są żądania sekwencyjne biblioteki (§10, pytanie 4).
- Wyniki narzędzi nie zawierają sekretów (token zapisu REST nie jest używany).

### 6.11 Konfiguracja klientów (przykłady do README)

```json
{
  "mcpServers": {
    "imgwtools": {
      "command": "imgw",
      "args": ["mcp"],
      "env": {"IMGW_STORE_ROOT": "/dane/imgw"}
    }
  }
}
```

Bez instalacji w systemie: `"command": "uvx", "args": ["--from", "imgwtools[mcp]", "imgw", "mcp"]`. Zapis: `"args": ["mcp", "--allow-writes"]`. Po angielsku: `"args": ["mcp", "--lang", "en"]`. HTTP na serwerze: `IMGW_MCP_ENABLED=true IMGW_STORE_ROOT=/srv/imgw imgw server` → `http://127.0.0.1:8000/mcp`; za `nginx` dodatkowo `IMGW_MCP_ALLOWED_HOSTS=<publiczna nazwa hosta>`.

## 7. Porządek komunikatów legacy (pkt 8)

### 7.1 Metoda

Skan `src/imgwtools/**` w `d8cb11c`, powtarzany przez A04 po C08 (taski ČHMÚ dodają teksty):

1. AST: literały `str` poza docstringami modułów, klas i funkcji; osobno docstringi komend Typer i tras FastAPI (są pomocą CLI i opisami OpenAPI) oraz argumenty `help=`, `description=`, `summary=`, `title=`.
2. Szablony HTML (tekst i atrybuty `title`, `placeholder`, `alt`, `aria-label`) i napisy w `web/static/js/app.js`.
3. Polskie słowa bez znaków diakrytycznych: forma ASCII słowa z polskimi znakami występującego w `docs/**/*.md`, która sama nie jest słowem tego słownika (wyklucza np. „opcja”, „nazwa”, „litera”), plus ręczny przegląd słów spoza słownika.
4. Komunikaty angielskie: co najmniej dwa angielskie słowa funkcyjne i ≥30% słów angielskich.
5. Wyrenderowana pomoc CLI (`imgw --help`, `imgw <komenda> --help`) i `/openapi.json` — teksty bibliotek.
6. Ręczna klasyfikacja: „do poprawy” (§7.2) albo „zostaje” (§7.3). Skanu nie utrwala się testem (test treści źródła); poprawki aktualizują istniejące testy, które przypinają stare teksty.

### 7.2 Do poprawy (33 pozycje)

| # | Miejsce (`d8cb11c`) | Obecnie | Zmiana | Task |
|---|---|---|---|---|
| 1 | `cli/admin.py:73` (pomoc `--limit`) | „Limit zapytan na godzine” | „Limit zapytań na godzinę” | A04 |
| 2 | `cli/admin.py:77,79` (docstring = pomoc `admin create`) | „Utworz nowy klucz API.”, „Przyklad:” | „Utwórz nowy klucz API.”, „Przykład:” | A04 |
| 3 | `cli/admin.py:103` | „{limit} req/h” | „{limit} zapytań/h” | A04 |
| 4 | `cli/admin.py:106` | „Zapisz ten klucz - nie bedzie mozna go odczytac ponownie!” | „Zapisz ten klucz – nie będzie można go odczytać ponownie!” | A04 |
| 5 | `cli/admin.py:114` | „ID klucza do uniewaznienia (wystarczy poczatek)” | „Identyfikator klucza do unieważnienia (wystarczy początek)” | A04 |
| 6 | `cli/admin.py:118,120` | „Uniewazni klucz API.”, „Przyklad:” | „Unieważnij klucz API.”, „Przykład:” | A04 |
| 7 | `cli/admin.py:130` | „Klucz … zostal uniewazniony” | „Klucz … został unieważniony” | A04; test `test_cli_admin.py:137` |
| 8 | `cli/admin.py:144` | „ID klucza do usuniecia (wystarczy poczatek)” | „Identyfikator klucza do usunięcia (wystarczy początek)” | A04 |
| 9 | `cli/admin.py:150` | „Usun bez potwierdzenia” | „Usuń bez potwierdzenia” | A04 |
| 10 | `cli/admin.py:154,156` | „Usun klucz API.”, „Przyklad:” | „Usuń klucz API.”, „Przykład:” | A04 |
| 11 | `cli/admin.py:172` | „Usunac klucz …?” | „Usunąć klucz …?” | A04 |
| 12 | `cli/admin.py:179` | „Klucz … zostal usuniety” | „Klucz … został usunięty” | A04; test `test_cli_admin.py:169` |
| 13 | `cli/admin.py:190,192` | „Statystyki uzycia kluczy API.”, „Przyklad:” | „Statystyki użycia kluczy API.”, „Przykład:” | A04 |
| 14 | `cli/admin.py:206` (kolumna tabeli) | „Zapytan” | „Zapytania” | A04 |
| 15 | `cli/main.py:44` (pomoc `imgw version`) | „Wyswietl wersje programu.” | „Wyświetl wersję programu.” | A05 |
| 16 | `cli/main.py:50–51` (pomoc `imgw server`) | „Host do nasluchu”, „Port do nasluchu” | „Adres nasłuchu”, „Port nasłuchu” | A05 |
| 17 | `cli/main.py:52` | „Auto-reload przy zmianach” | „Przeładuj serwer po zmianie kodu (tryb deweloperski)” | A05 |
| 18 | `models.py:114` (`PMaXTPData.sg`) | „Gorne granice przedzialu ufnosci [mm]” | „Górne granice przedziału ufności [mm]” | A04 |
| 19 | `models.py:118` (`PMaXTPData.rb`) | „Bledy estymacji kwantyli [mm]” | „Błędy estymacji kwantyli [mm]” | A04 |
| 20 | `models.py:201–204` (`PMaXTPData.to_dataframe`) | „pandas is required for to_dataframe(). Install with: pip install imgwtools[pandas]” | „Metoda to_dataframe() wymaga pakietu pandas. Zainstaluj dodatek: pip install imgwtools[pandas]” | A04 |
| 21 | `models.py:224–227` (`PMaXTPResult`, 4 pola) | „Calculation method (POT or AMP)”, „Latitude in decimal degrees”, „Longitude in decimal degrees”, „Precipitation data” | opisy polskie („Metoda obliczeń: POT albo AMP”, „Szerokość geograficzna punktu (WGS84)”, …) | A04 |
| 22 | `models.py:237–256` (`HydroCurrentData`, 14 pól) | angielskie, m.in. „Province (wojewodztwo)”, „Overgrowth code” | polskie, m.in. „Województwo”, „Kod zarastania” | A04 |
| 23 | `models.py:299–314` (`MeteoCurrentData`, 9 pól) | angielskie | polskie | A04 |
| 24 | `models.py:353–372` (`SynopData`, 12 pól) | angielskie | polskie | A04 |
| 25 | `models.py:414–422` (`WarningData`, 9 pól) | angielskie | polskie | A04 |
| 26 | `models.py:468–475` (`HydroState`, 6 pól) | angielskie, m.in. „Water state (alarm, warning, high, medium, low, ...)” | polskie (wartości `water_state` bez zmian) | A04 |
| 27 | `reference_data.py:43–46` (`ATTRIBUTION`) | „Zrodlem pochodzenia danych jest … - Panstwowy Instytut Badawczy” | formuła z rejestru (`License.attribution` IMGW-PIB: „Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy”), bez kopii tekstu | A04 |
| 28 | `reference_data.py:59,70,100,109,111,119,125,126,127,133,136` | „({count} rows)”, „Hydrological station coordinates:”, „Format descriptions (hydro):”, „skipped: …”, „Format descriptions (meteo):”, „Fetching reference data into: …”, „Data is subject to IMGW-PIB's terms of use.”, „Required attribution: …”, „Error fetching data: …”, „Done. All data fetched from IMGW-PIB and written to …” | „({count} wierszy)”, „Współrzędne stacji hydrologicznych:”, „Opisy formatów (hydro):”, „pominięto: …”, „Opisy formatów (meteo):”, „Pobieranie danych referencyjnych do: …”, „Dane podlegają warunkom korzystania IMGW-PIB.”, „Wymagana atrybucja: …”, „Błąd pobierania danych: …”, „Gotowe: dane IMGW-PIB zapisano w …” | A04; testy `test_reference_data.py:79,146,176` |
| 29 | `api/main.py:90–93` (`GET /health`) | docstring „Health check endpoint.”, podsumowanie OpenAPI „Health Check” | „Stan serwera i wersja pakietu.”, `summary` „Stan serwera” | A05 |
| 30 | `api/main.py:96–98` (`GET /api/v1`) | „List the catalog routes of the API.”, podsumowanie „Api Info” | „Lista tras katalogu komend.”, `summary` „Trasy API” | A05 |
| 31 | `api/schemas.py:7` (`HealthCheck`, opis schematu w OpenAPI) | „Health check response.” | „Odpowiedź GET /health: stan serwera i wersja pakietu.” | A05 |
| 32 | `web/app.py:44` (router stron HTML) | 9 tras HTML w OpenAPI z podsumowaniami „Index”, „Download Page”, … i opisami z docstringów („Render the dashboard.”) | router stron z `include_in_schema=False` (strony nie są API; docstringi zostają jako dokumentacja kodu) | A04 |
| 33 | pomoc CLI z Typer/Click (poza repozytorium) | „Options”, „Commands”, „Arguments”, „Show this message and exit.”, „Usage:”, „[env var: …]”, „[default: …]”, „[required]” | §4.3 | A01 |

Opisy pól modeli (poz. 18–26) są widoczne w OpenAPI jako schematy `result` tras REST; zmiana nie dotyczy nazw ani wartości pól.

### 7.3 Zostaje

| Kategoria | Przykłady (`d8cb11c`) | Powód |
|---|---|---|
| Klucze API IMGW i kolumny źródeł | `models.py:277–286, 335–341, 393–402, 450–456` (`wojewodztwo`, `przeplyw`, `tresc`, `stopien`, `obowiazuje_od`, `prawdopodobienstwo`, `cisnienie`, …); `store/catalog.py:651–669` (`rzeka`, `nazwa_stacji`, `rok_zalozenia_stacji`, `rzedna_zerawodowskazu`, `wysokosc_npm`) | identyfikatory zewnętrzne, muszą odpowiadać źródłu |
| Ścieżki serwera IMGW, słowa interwałów, aliasy legacy | `datasets.py` (`dane_hydrologiczne/miesieczne`, `polroczne_i_roczne`, `hydro/miesieczne`), `fetch.py:761–894`, `_parsing/hydro.py:209–568`, `store/sync.py:378–381`, `reference_data.py:33–41` | ścieżki na serwerze i wejście legacy (ADR-002 D4, D14) |
| Docstringi i komentarze | m.in. nazwy kolumn CSV IMGW w docstringach `_parsing/hydro.py:310,343,376` | dokumentacja kodu po angielsku (DEVELOPMENT_STANDARDS §4), nie trafia do użytkownika |
| Oryginały bibliotek w `details` | `details.click` (CLI), `details.errors[].message` (pydantic w REST) | spec 2026-10-17 §13.5: oryginał obok polskiego `detail` |
| Nazwy metod PMAXTP | `web/app.py:47–50`; `templates/index.html:32–33`, `download/pmaxtp.html:54,63`, `partials/pmaxtp_result.html:122` („Peak Over Threshold”, „Annual Max Precipitation”) | nazwy własne metod obok polskich opisów; testy `test_web_app.py:99,263,297` |
| Dziennik konsoli przeglądarki | `web/static/js/app.js:49,66,86` (`console.error(...)`) | dziennik deweloperski, nie komunikat dla użytkownika |
| Kody, wartości wyliczeń, identyfikatory | `data_error`, `stale_plan`, `station_list`, … | ADR-002 D2 |

## 8. Konsumenci

**Retman** (`Retman/docs/ARCHITECTURE.md` 3.2–4.3) — bez zmian wymaganych w Retmanie i bez kodu dla Retmana w IMGWTools: narzędzia „nic nie wiedzą o Retmanie” (3.2.1), więc przewodnik, opisy i MCP są ogólne. Retman korzysta z publicznego katalogu (`docs/ARCHITECTURE.md` IMGWTools: handler przez `run_command`); 3.0.0 daje mu dodatkowo:

- `command_schema(lang="en")` — angielskie opisy do pola `description` manifestu (3.2.3: opis po angielsku dla programistów), `enum` → `options`, `minimum`/`maximum` → `range`, `required`; kontrola rozjazdów (`retman-scaffold --check`) może porównywać manifest z `imgw-commands/1` zamiast z docstringami;
- `x-imgw.writes` i `x-imgw.network` — informacja do planu („pobierze dane”, „zapisze pliki”);
- `format_command` — odtwarzalne polecenie `imgw …` do dziennika projektu (5.4, ślad audytowy);
- przypadek „ściągnij opady z poznania” (8.1, `expect_clarify: ["period"]`) prowadzi przepływ 1 (§5.4): `find_stations(kind="meteo", query="poznan")` do rozstrzygnięcia stacji, plan przed zapisem, wynik jako plik w katalogu wyników handlera (`series export --path <output_dir>/…`; reguła handlera „zapis tylko do `output_dir`”, 3.2.4), magazyn jako zewnętrzna konfiguracja (`root`).

Retman nie jest klientem MCP (backendy basal i zgodne z API OpenAI) i nie potrzebuje serwera MCP.

**Archiwista** (`Archiwista/docs/SPEC.md`) — bez zmian. Czyta magazyn API odczytu i katalog (`data_commands`, `validate_command`, `format_command`, `run_command`, `check_command`; IMGW-10, IMGW-11), a jej asystent ma własne narzędzia z operacji API Archiwisty; MCP rozważa jako wejście po v1.0 (SPEC 5.2). Kontrakty magazynu bez zmian; `imgw-commands/1` i typy katalogu tylko addytywnie; polskie opisy domyślnie, więc kryterium IMGW-11 („opis po polsku równy `--help`”) obowiązuje bez zmian przy domyślnym `IMGW_LANG`. Nowe pole `title_en` w wynikach `datasets list` jest addytywne.

**Hydrograf, Hydrolog, Kartograf** — bez zmian: `fetch_pmaxtp` i modele zachowują podpisy i pola, a zmieniają się wyłącznie opisy pól (§7.2).

## 9. Testy

Zasady: offline, nagrania `respx` i magazyn z `build_fixture_store`, stacje fikcyjne (`123456789`, `0-203-1-900001`); oczekiwania liczone z katalogu; bez testów treści źródła; zmiany brzmienia aktualizują wyłącznie istniejące przypięcia; testy MCP z `pytest.importorskip("mcp")` (dodatek jest w `dev`).

| Obszar | Testy | Task |
|---|---|---|
| Opisy angielskie | kompletność i spójność (§4.1); `command_schema(lang="en")` strukturalnie równe polskiemu (§3.3); `lang` spoza `pl\|en` → `validation_error` z `details.allowed` | A01 |
| Skutki | dla każdego przypadku kontraktu (`tests/contract/test_interface_contract.py` `CASES`) komendy z `network=false` — zero żądań HTTP (`respx` bez tras); komendy z `writes="none"` bez opcji zapisującej — drzewa root i katalogu roboczego bez zmian; przypadek z opcją zapisującą tworzy plik; niezmiennik bliźniaka (§3.2) | A01 |
| Język w CLI i REST | `IMGW_LANG=en` — pomoc komendy, panele, `--help`, „Usage”; domyślnie polskie; `IMGW_LANG=de` → linia `validation_error`, kod 2; `--lang en` i zmienna jako domyślna; `Accept-Language` (wagi, podtagi, brak dopasowania, pierwszeństwo `?lang=`), `Content-Language`, `Vary`; problem+json z angielskim `title` i polskim `detail` | A01 |
| Reguła root | `stations find` w CLI bez zmian (istniejące testy) przy regule z katalogu | A01 |
| Przewodnik | bajty `AGENTS.md` i `llms.txt` = generator (z poleceniem regeneracji w komunikacie); przewodnik `pl` i `en` wymienia każdą komendę, każdy klucz zbioru (z `cz.chmi.*`), każdy kod błędu z kodem wyjścia i statusem HTTP, każdy status koperty i każdy alias krótki; każdy krok przepływu przechodzi `validate_command` po podstawieniu symboli; struktura `llms.txt` (H1, cytat, H2 z listami `- [nazwa](https://…)`, `## Optional` na końcu); `commands guide` w Pythonie, CLI i REST daje te same bajty (przypadki w `CASES`) | A02 |
| Lista narzędzi MCP | dla `read` i `write`: nazwy = `operation_id` wszystkich komend w kolejności katalogu; schematy = przekształcenie §6.4 schematu komendy; `check` wtedy i tylko wtedy, gdy `x-imgw.check`; w `read` komendy zapisujące mają `check` stałe i nie mają opcji zapisujących; adnotacje z §6.4; `lang="en"` → opisy angielskie | A03 |
| Wywołania MCP | każda komenda z `CASES` (komendy z trasą REST) oraz komendy lokalne na magazynie testowym i nagraniach (`store init`, `datasets download`, `project init`, `project add`, `project status`, `project verify`): `structuredContent` = koperta Pythona = stdout CLI; komenda zapisująca bez `check` → plan i magazyn bez zmian; `check: false` w `read` → `forbidden`/`writes_disabled`; `write`: `store_init` z `check: false` = CLI; każdy scenariusz kodów błędów kontraktu → `isError` i dokument zgodny z linią CLI; strumień `commands_guide` = `agent_guide()`; strumień ponad 256 KiB → `validation_error`; domyślny `limit` 50 i maksimum; anulowanie ustawia `cancel` i nie zostawia wersji częściowych; postęp przy `progressToken`; nieznane narzędzie → −32602 | A03 |
| MCP stdio i HTTP | podproces `imgw mcp` przez klienta SDK (lista narzędzi, `datasets_list`); bez dodatku → `missing_dependency`, kod 6; `/mcp`: narzędzia = trasy REST, treść REST = `structuredContent` dla każdego przypadku REST, problem+json → `isError`, obcy `Host` → 421, wyłączone → 404; `GET /llms.txt` = `agent_guide(format="llms")` (także `Accept-Language: en`) | A05 |
| Na żywo | `IMGW_LIVE=1`: noga MCP stdio w `tests/live/test_interfaces_live.py` dla komend odczytu na żywo, zgodność z Pythonem | A05 |
| Komunikaty | zaktualizowane przypięcia (`test_cli_admin.py`, `test_reference_data.py`); atrybucja wypisywana przez `reference_data` = formuła z rejestru; OpenAPI bez tras stron HTML, strony nadal działają | A04 |

## 10. Ryzyka i pytania otwarte

| Ryzyko | Skutek | Ograniczenie |
|---|---|---|
| Zmiany API SDK `mcp` w 2.x | adapter przestaje działać po aktualizacji | przypięcie `>=2.3,<3`, niskopoziomowy `Server` (jawny kontrakt), testy w pamięci i podproces stdio |
| Rozmiar listy narzędzi | ok. 26 KB schematów dla 35 komend [V], dla 37 z opisami więcej; koszt kontekstu modelu | jedno źródło opisów bez powtórzeń; filtr grup lub dostawcy — pytanie 3 |
| Agent ignoruje plan i zapisuje | niechciane pobrania | domyślnie `read`; `check` domyślnie `true`; zapis włącza użytkownik; `destructiveHint` dla `replace` |
| Polski `detail` dla agentów anglojęzycznych | słabsze samodzielne poprawki wywołań | stabilne `code` i `details.option`, angielski `title`; pytanie 2 |
| Dryf `AGENTS.md` | przewodnik niezgodny z kodem | test bajtowy i reguła regeneracji w tej samej zmianie |
| Obciążenie źródeł przez pętle agentów | spowolnienia, blokady IMGW/ČHMÚ | reguła 11 przewodnika, `openWorldHint`, `nginx` dla HTTP, żądania sekwencyjne biblioteki |
| Stałe Typer są API półpublicznym | pomoc CLI wraca do angielskiego po aktualizacji Typer | test pomocy w obu językach (A01) |

**Pytania otwarte:**

1. **Do właściciela:** zatwierdzenie D1–D12 ADR-004 (status „Proponowana”).
2. Czy w kolejnym wydaniu tłumaczyć treści wykonania (`detail`, `Notice.text`) — dziś tylko tytuły i opisy katalogu.
3. Czy dodać filtr narzędzi MCP (`--groups`, `--provider` z `data_commands(provider=…)`, ADR-003 D13) po zebraniu doświadczeń z kosztem kontekstu.
4. Czy serwer stdio ma własny limit wywołań sieciowych na minutę (dziś tylko żądania sekwencyjne).
5. Zapis przez MCP po HTTP z autoryzacją (token albo OAuth MCP) — po 3.0.0.
6. Czy publiczny serwer właściciela ma włączyć `/mcp` (`IMGW_MCP_ENABLED`) — decyzja wdrożeniowa.

## 11. Plan wdrożenia (A01–A06)

**Zasady pracy:** jak w §16 spec ČHMÚ — zadania jednej fali mają rozłączne pliki (także testy), w fali pracują najwyżej dwa taski, każdy task pisze tylko własne testy i uruchamia wyłącznie je oraz `ruff check`/`ruff format --check`/pyright na własnych plikach. Kontrakt-first w obrębie fali: task może użyć podpisu z tego dokumentu, który kończy inny task tej samej fali; testy tej ścieżki wykonuje następna fala. Pełna bramka (`.venv/bin/python -m pytest`, `.venv/bin/ruff check src/ tests/`, `.venv/bin/pyright src/imgwtools/`) raz — w C09, który startuje po A3. Pliki pochodne `AGENTS.md` i `llms.txt` należą do A02, a po nim regeneruje je każdy task zmieniający katalog, rejestry lub szablony (§5.8), także C09 i C10.

| Fala | Taski (równolegle) | Zakres | Start |
|---|---|---|---|
| C4 + A1 | C08 ‖ A01 | projekty i magazyn testowy PL + CZ ‖ katalog: opisy angielskie, skutki, język, reguła root | po C07 (fala C3) |
| A2 | A02 ‖ A03 | przewodnik, `commands guide`, `AGENTS.md`, `llms.txt` ‖ adapter MCP | po C08 i A01 |
| A3 | A04 ‖ A05 | komunikaty legacy ‖ `imgw mcp`, `/mcp`, `GET /llms.txt`, wdrożenie | po A2 |
| C5 | C09 ‖ C10 | kontrakt IMGW-15..19, test na żywo i pełna bramka (obejmuje A01–A05) ‖ dokumentacja ČHMÚ | po A3 |
| A4 | A06 | dokumentacja wsparcia agentów, erraty ADR-002 i ADR-003 | po C10 |

Wariant awaryjny (C09 nie może czekać): fale A2–A3 po C5, a A05 kończy się pełną bramką; A06 jak wyżej.

### Fala C4 + A1

**A01 — Katalog dla agentów: opisy angielskie, skutki, język.**  
**Pliki (wyłączna własność w fali):** `src/imgwtools/store/types.py` (wyłącznie pola `CommandOption` i `DataCommand` z §3.1), `src/imgwtools/commands.py` (teksty angielskie wszystkich 36 komend, opcji, reguł i grup; `writes`, `network`, `env_root_when`; `command_schema(lang=)`, opcja `lang` komendy `commands schema`, pola `x-imgw`), `src/imgwtools/exceptions.py` (`ErrorSpec.title_en` i wartości), `src/imgwtools/datasets.py` (wyłącznie `DatasetDescriptor.title_en` i wartości 17 deskryptorów), `src/imgwtools/config.py` (`Settings.lang`), `src/imgwtools/cli/_dispatch.py` (`IMGW_LANG`, pomoc w obu językach, §4.3, reguła root z katalogu zamiast `_ROOT_WHEN`), `src/imgwtools/api/routes/commands.py` (`Accept-Language` → domyślne `lang`, `Content-Language`, `Vary`, `operationId` z `x-imgw.operation_id`), `src/imgwtools/api/errors.py` (`title` problemu według `Accept-Language`); zmodyfikuj `tests/unit/test_command_schema.py`, `tests/unit/test_cli_catalog.py`, `tests/unit/test_api_commands.py`, `tests/unit/test_exceptions.py`; utwórz `tests/unit/test_catalog_i18n.py`, `tests/unit/test_catalog_effects.py`.  
**Zależy od:** C07 (katalog 36 komend z opcjami ČHMÚ), C02 (deskryptory i dostawcy).  
**Test akceptacji:** każda komenda ma niepusty `description_en` i `rules_en` o liczności `rules`, każda opcja niepusty `help_en`, każda grupa, kod błędu i zbiór — tekst angielski; odwzorowanie pomocy polski ↔ angielski jest wzajemnie jednoznaczne; `command_schema(lang="en")` różni się od domyślnego wyłącznie tekstami; `x-imgw` ma `writes`, `network`, `operation_id` zgodne z §3.2, a opcje zapisujące — `x-imgw-writes`; niezmiennik bliźniaka; testy skutków z §9 przechodzą dla wszystkich przypadków kontraktu; `IMGW_LANG=en imgw store sync --help` pokazuje teksty angielskie, a bez zmiennej — polskie, z „Opcje”, „Komendy”, „Pokaż pomoc i zakończ.” i „Użycie:”; `IMGW_LANG=de imgw datasets list` kończy się `validation_error` (kod 2); `imgw commands schema --lang en` i `IMGW_LANG=en imgw commands schema` dają dokument angielski; REST negocjuje język według §4.2 (wagi, podtagi, `?lang=` przed nagłówkiem, `de` → `pl`) z `Content-Language` i `Vary`, a problem+json ma angielski `title` przy polskim `detail`; OpenAPI ma te same `operationId`; koperty i schematy domyślne bez zmian poza polami addytywnymi (istniejące testy kontraktu bez zmian wyników).

**Uzupełnienie (2026-10-19, A01)** — rozstrzygnięcia punktów [U] i luk, bez zmiany kontraktu:

- Pomoc CLI (§4.3): Typer 0.27.3 ma własną kopię Click (`typer._click`); opis `--help` ustawia nadpisane `get_help_option`, a przedrostek „Użycie:” — nadpisane `format_usage` (linia użycia powstaje w `format_usage`, nie w `get_usage`). Klasy adaptera: `ImgwGroup` (korzeń), `ImgwSubgroup` (grupy), `ImgwCommand` (komendy; po niej dziedziczy `_CatalogCommand`); komendy spoza katalogu dostają je przez `cls=` w `cli/main.py` i `cli/admin.py` — tak samo przyszłe `imgw mcp` (A05). Metawartości linii użycia z Click (`[OPTIONS]`, `COMMAND [ARGS]...`) zostają, bo §4.3 ich nie wymienia (do ponownego skanu A04).
- Język pomocy CLI ustala się raz, przy imporcie adaptera (`Settings.lang`); wartość spoza `pl|en` sprawdza `ImgwGroup.make_context` przed parsowaniem, więc błąd kończy każde wywołanie (także `--help`, `version`, `admin`). Domyślną wartość `--lang` daje Click przez `envvar` `IMGW_LANG` (jak `--root`); `--schema` używa języka pomocy.
- REST: `Content-Language` ma każda odpowiedź komendy z opcją `lang` (język po normalizacji), `Vary: Accept-Language` — tylko gdy język przyszedł z nagłówka (bez `?lang=`). Każdy problem+json ma `Content-Language` języka `title` (język odbiorcy, RFC 9110 §8.5) i `Vary: Accept-Language`. Nagłówek interpretuje `imgwtools.api.errors.accept_language` (do użycia także w `GET /llms.txt`, A05); pozycje z wagą spoza 0–1 albo nieczytelną są pomijane.
- Reguły w `commands._command` są parami (polski, angielski), więc `rules` i `rules_en` nie mogą się rozjechać; opcja `lang` to `commands._LANGUAGE` (do ponownego użycia w `commands guide`, A02), plik planu `store check` i `project check` — `commands._PLAN_FILE` (`writes="replace"`).
- `series select` dostał regułę C08 (gramatyka kodów `stations` według dostawcy zbioru) z wariantem angielskim.

### Fala A2

**A02 — Przewodnik: `agent_guide`, `commands guide`, `AGENTS.md`, `llms.txt`.**  
**Pliki:** utwórz `src/imgwtools/agent_guide.py`, `src/imgwtools/_data/agents/agents.pl.md`, `agents.en.md`, `llms.pl.md`, `llms.en.md`, `AGENTS.md`, `llms.txt`, `tests/unit/test_agent_guide.py`; zmodyfikuj `src/imgwtools/commands.py` (wyłącznie komenda `commands guide`: wpis katalogu z tekstami obu języków, bliźniak, `_MODULES`), `src/imgwtools/__init__.py` (eksport `agent_guide`), `src/imgwtools/api/routes/commands.py` (wyłącznie typ i nazwa pliku strumienia dla `format=agents|llms`), `tests/contract/test_interface_contract.py` (wyłącznie `CASES` dla `commands guide` i przypadek `lang` w `commands schema`), istniejące testy z liczbą komend katalogu (36 → 37, m.in. `tests/unit/test_commands_chmi.py`).  
**Zależy od:** A01.  
**Test akceptacji:** testy przewodnika z §9; katalog ma 37 komend; `imgw commands guide --format llms` = `GET /api/v1/commands/guide?format=llms` (`text/markdown; charset=utf-8`, `Content-Disposition` z `llms.txt`) = `agent_guide(format="llms")`; `--path` zapisuje plik, `--check` daje plan bez zapisu; `_instructions` zwraca blok „Zasady” i linie trybu w obu językach, poniżej 2 KiB.

**Errata (2026-10-19, A02):** §3.4 „bez reguł” → `commands guide` ma regułę „path wewnątrz magazynu jest niedozwolona” (`x-imgw.rules` i walidacja w `validate_command`, jak `store export` i `series export`). §3.4 daje komendzie opcję `_PATH`, której pomoc brzmi „Plik wyniku poza magazynem, w istniejącym katalogu”; bez reguły schemat i pomoc mówiłyby co innego niż zachowanie, a przewodnik zapisany w magazynie byłby obcym plikiem w katalogu tylko przyrostowym (ADR-001 D1). `agent_guide(path=…)` sprawdza cel jak eksporty (istniejący katalog, cel nie jest katalogiem, poza magazynem) i zapisuje go atomowo przez ukryty plik `.part`. Wpis w ADR-004 „Erraty”.

**Uzupełnienie (2026-10-19, A02)** — rozstrzygnięcia luk, bez zmiany kontraktu:

- Bloki szablonów: poza tabelą §5.3 jest blok `rules` (zasady §5.4 z danych modułu, `agent_guide._PRINCIPLES`), wspólny dla `AGENTS.md`, `llms.txt` (sekcja bez nagłówka po cytacie zamiast punktu „Cykl pracy” wzoru §5.7) i `_instructions`. Znacznik w całej linii przyjmuje blok wielowierszowy, znacznik wewnątrz linii — jednowierszowy (`version` w H1, `summary` na końcu akapitu); nieznany blok, blok użyty dwa razy i blok wielowierszowy wewnątrz linii to `ValueError` (błąd programu), wykrywany testem renderowania wszystkich szablonów.
- Blok `commands`: tabela na grupę (nagłówek `### <grupa> — <opis grupy>`) z kolumnami §5.3 oraz opisem komendy i typem wyniku (`Page[T]` dla list, „strumień linii” dla strumieni); `oneOf` i `dependentRequired` jako dopisek w kolumnie opcji; w kolumnie check `sama` oznacza komendę bez bliźniaka, której funkcja to `check_*`.
- Przepływy: `format_command` waliduje opcje i zamienia ścieżki na bezwzględne, więc generator podstawia za symbole wartości zastępcze (`123456789`, `0-203-1-900001`, `/PROJEKT`), formatuje i przywraca symbole. Symbole mają nazwy w języku przewodnika (`KOD_STACJI`/`STATION_CODE`, `KOD_WIGOS`/`WIGOS_ID`, `PROJEKT`/`PROJECT`), ścieżki przykładów są bezwzględne (`/dane/imgw`, `/dane/wyniki/opady.csv`), więc wynik nie zależy od katalogu roboczego; roczniki mają postać z `format_command` (lista), co przewodnik objaśnia; `--check` jest polem kroku, nie opcją. Test waliduje każde polecenie wydrukowane w przewodniku po podstawieniu wartości fikcyjnych.
- Plan `check_command`: `PlanAction("commands guide", "current", "Przewodnik <format> (<lang>) → <ścieżka>")`, bez `path` — „→ standardowe wyjście”, z dopiskiem „(istniejący plik zostanie zastąpiony)”, gdy cel istnieje.
- `_instructions(*, lang, mode, workdir, root)`: `workdir` i `root` typu `PathArg | None`; tryb `http` nie pokazuje katalogów serwera (tylko to, czy serwer ma magazyn). Domyślny rozmiar strony MCP to `agent_guide._PAGE_SIZE` (50) — jedno źródło dla instrukcji i adaptera A03. Instrukcje mają ok. 1,4–1,5 KiB.
- REST: `_MEDIA_TYPES` zna `agents` i `llms` (`text/markdown; charset=utf-8`), nazwa załącznika wynika z `format` (`AGENTS.md`, `llms.txt`), a brakujący `format` strumienia przyjmuje wartość domyślną z katalogu.
- Zmiany poza listą plików (konieczne): `.gitignore` — wyjątek `!/llms.txt` od wzorca `*.txt`, bez którego plik pochodny nie trafiłby do repozytorium; `tests/contract/test_interface_contract.py` `assert_alike` — `license_terms` wymagane wyłącznie w strumieniach eksportu danych (funkcje `export_*`), bo przewodnik nie niesie licencji danych; `tests/unit/test_public_store_api.py` (`agent_guide` w `__all__`); liczby 36 → 37 także w `tests/unit/test_commands.py`, `test_command_schema.py`, `test_api_commands.py` (27 tras REST) i `test_catalog_effects.py` (`EFFECTS`). `tests/live/test_interfaces_live.py` (A05, C09) nie ma przypadku `commands guide` ani `datasets providers`, więc jego test pokrycia katalogu wymaga dopisania przed najbliższym przebiegiem `IMGW_LIVE=1`.

**A03 — Serwer MCP: adapter.**  
**Pliki:** utwórz `src/imgwtools/mcp/__init__.py`, `src/imgwtools/mcp/_tools.py`, `src/imgwtools/mcp/_calls.py`, `src/imgwtools/mcp/server.py`, `tests/unit/test_mcp_tools.py`, `tests/unit/test_mcp_calls.py`, `tests/contract/test_mcp_contract.py` (przypadki importowane z `tests/contract/test_interface_contract.py`); zmodyfikuj `pyproject.toml` (dodatek `mcp`, `full`); zainstaluj dodatek w `.venv` (`pip install -e ".[dev]"`).  
**Zależy od:** A01; z A02 kontrakt-first wyłącznie `_instructions` i komenda `commands guide`.  
**Test akceptacji:** testy „Lista narzędzi MCP” i „Wywołania MCP” z §9 na kliencie SDK w pamięci (`Client(server)`) dla trybów `read` i `write`, w obu językach; tryb `http` w tym tasku tylko jako lista i schematy (wywołania — A05); ruff i pyright czyste na `src/imgwtools/mcp/`.

**Errata (2026-10-19, A03):** (1) §6.5 p. 2 „`arguments` niebędące obiektem → błąd wykonania `validation_error`” → błąd protokołu JSON-RPC −32602 („Invalid request parameters”): SDK `mcp` 2.3.0 waliduje parametry `tools/call` modelem `CallToolRequestParams` (`arguments: dict | None`) przed handlerem, więc handler nie dostaje innej wartości [V surowe żądanie JSON-RPC]; brak `arguments` = `{}`. (2) §6.4 p. 6 w trybie `http`: `check` mają wyłącznie narzędzia tras POST (stałe `true`); trasy GET nie przyjmują `?check=true` (REST odrzuca parametr `check`), więc narzędzia GET nie mają `check` mimo bliźniaka. Wpis w ADR-004 „Erraty”.

**Uzupełnienie (2026-10-19, A03)** — rozstrzygnięcia punktów [U] i luk, bez zmiany kontraktu:

- SDK `mcp` 2.3.0 [V zainstalowana wersja]: niskopoziomowy `Server(name, version=, title=, instructions=, on_list_tools=, on_call_tool=)` (handlery w konstruktorze); stdio: `mcp.server.stdio.stdio_server()` + `Server.run(read, write, server.create_initialization_options())` — na czas pracy fd 1 wskazuje stderr; HTTP: `Server.streamable_http_app(transport_security=TransportSecuritySettings(allowed_hosts=…))` z trasą `/mcp` i lifespanem `session_manager.run()`; postęp: `ctx.session.report_progress(progress, total, message)` (bez `progressToken` nic nie wysyła); nieznane narzędzie: `MCPError(INVALID_PARAMS, …)`. `Client(server)` domyślnie wywołuje serwer w procesie bezpośrednio (rewizja 2026-07-28), `Client(server, mode="legacy")` — przez JSON-RPC w pamięci (2025-11-25); testy postępu używają obu. Klient SDK nie sprawdza `outputSchema` dla wyniku z `isError` (rozstrzyga [U] z §6.6).
- Anulowanie: SDK anuluje zakres handlera (`notifications/cancelled` albo czas klienta); wątku roboczego nie da się przerwać, więc handler ustawia zdarzenie haka `cancel`, czeka na koniec wątku i dopiero wtedy zgłasza anulowanie — żądanie anulowane nie dostaje odpowiedzi także przy wywołaniu bezpośrednim, w którym SDK oddałoby wynik. `sync_store` nie zaczyna kolejnego archiwum, a `write_archive` nie zapisuje archiwum pobieranego w chwili anulowania (brak wersji częściowych).
- `root` (stdio): `IMGW_STORE_ROOT` z `os.environ` jak w CLI (pusta wartość = brak), czytany raz przy tworzeniu serwera. Poza `required` znika także z grup `oneOf` i `dependentRequired` (np. `series read`: `[version] | [dataset]`), a opis kończy się „; domyślnie: magazyn serwera MCP”, przy `env_root_when` — „; domyślnie przy source=store: magazyn serwera MCP”.
- Schemat wejścia nie ma `description` najwyższego poziomu (jest opisem narzędzia), jak w przykładzie §6.4. Strona listy: domyślnie `min(50, IMGW_API_MAX_LIMIT)` (`agent_guide._PAGE_SIZE`); `limit` ponad maksimum (po `validate_command`, tylko przy uruchomieniu) → `validation_error` z tekstem REST i `details.maximum`.
- Argument `null` = brak (jak w `validate_command`): nie zastępuje wartości domyślnych i nie jest odmową zapisu. `check` przyjmuje wartość logiczną albo tekst `true`/`false` (jak REST `?check=`), inna wartość → `validation_error` z `details.option="check"`; w narzędziu bez `check` argument trafia do `validate_command` (nieznana opcja). Odmowa zapisu: `forbidden`, `details={"reason": "writes_disabled", "option": <opcja albo check>}`, `detail` po polsku z poleceniem włączenia zapisu (stdio) albo informacją, że zapis przez HTTP nie istnieje.
- Strumień: `result.format` = podany albo domyślny z katalogu, `lines` = liczba znaków `\n` (+1 dla ostatniej linii bez `\n`), `notices` = komunikaty koperty w chwili zwrócenia strumienia (jak `X-IMGW-Notices` REST).
- Tryb `http`: schematy opcji z funkcji adaptera REST (`_option_schema`) z tekstami właściwości w języku serwera; dopiski REST (`version`, `user_locations`, `plan`) zostają po polsku także dla `lang="en"` (OpenAPI nie jest tłumaczone, §4.4); `limit` jak w stdio (strona MCP).
- Zmiany planu (decyzja koordynatora 2026-10-19): A03 dodaje `Settings.mcp_enabled` i `Settings.mcp_allowed_hosts` (`IMGW_MCP_ALLOWED_HOSTS` po przecinku, `NoDecode`) oraz `http_app(*, lang)` — każdy host listy dopuszczony z dowolnym portem i bez (`h`, `h:*`; SDK porównuje `Host` dokładnie), nagłówek `Origin` → 403 (pusta lista SDK); a także wywołania trybu `http` w `_calls.py` (bez nich lista `http` nie miałaby wywołań): żądanie ASGI do `imgwtools.api.main:app` w procesie (GET: lista jako powtórzony parametr, `true`/`false`, obiekt jako tekst JSON, `null` pominięte; POST: ciało JSON i `?check=true`; `Accept-Language` = język serwera), odczyt strumienia przerywa po 256 KiB komunikat `http.disconnect` (REST przestaje generować strumień), problem+json → dokument błędu, `check: false` → `forbidden`/`writes_disabled`, opcje serwerowe i lokalne odrzuca REST (400). Testy wywołań `http`, montaż `/mcp` i lifespan zostają w A05.

### Fala A3

**A04 — Porządek komunikatów legacy.**  
**Pliki:** `src/imgwtools/cli/admin.py`, `src/imgwtools/models.py` (wyłącznie opisy pól i komunikat `to_dataframe`), `src/imgwtools/reference_data.py`, `src/imgwtools/web/app.py` (wyłącznie `include_in_schema=False` routera stron); zmodyfikuj `tests/unit/test_cli_admin.py`, `tests/unit/test_reference_data.py`, a `tests/unit/test_api_commands.py` wyłącznie wtedy, gdy wylicza trasy OpenAPI stron.  
**Zależy od:** C08 (fala), C07 (`web/app.py`), C03 (`models.py`).  
**Test akceptacji:** każda pozycja A04 z §7.2 poprawiona; testy z przypięciami przechodzą z nowym brzmieniem („został unieważniony”, „został usunięty”, „pominięto: …”, „Błąd pobierania danych: …”); atrybucja wypisywana przez `python -m imgwtools.reference_data` jest równa formule IMGW-PIB z rejestru; `/openapi.json` nie zawiera tras stron HTML, a strony renderują się jak dotąd; ponowny skan §7.1 na stanie po C08 nie znajduje nowych pozycji poza §7.3 albo dopisuje je do §7.2 erratą i poprawia (wynik w `docs/PROGRESS.md` przez A06).

**Errata (2026-10-19, A04):** ponowny skan §7.1 na stanie po C08 i A01–A03 (`src/imgwtools/**`, szablony, `app.js`, szablony przewodnika, wyrenderowana pomoc wszystkich komend CLI, `/openapi.json`) — (1) §7.2 dostaje pozycje 34–37, poprawione: **34** `cli/admin.py` (`admin stats`, `revoke`, `delete`, `create`): pomoc „ID klucza (opcjonalne)” → „Identyfikator klucza (opcjonalnie)”, metawartość argumentów `key_id` → `IDENTYFIKATOR`, znaczniki typów Typer `<str>`/`<int>` opcji `--name`/`--limit` → `TEKST`/`LICZBA` (A04); **35** pomoc CLI z Click poza listą §4.3: symbole linii użycia `[OPTIONS]` i `COMMAND [ARGS]...` → „[OPCJE]” i „KOMENDA [ARGUMENTY]...”, komunikat przerwania „Aborted.” (`typer.rich_utils.ABORTED_TEXT`, np. odmowa w `imgw admin delete`) → „Przerwano.”; po angielsku wartości Click (A04, `cli/_dispatch.py` — §4.3 dostaje te trzy elementy); **36** `web/templates/partials/download_links.html:74` (nagłówek skryptu wget pobieranego przez użytkownika) „# IMGWTools - wget download script” → „# IMGWTools – skrypt pobierania plików IMGW-PIB (wget)” (A04); **37** `cli/main.py` (`imgw server`): znaczniki `<str>`/`<int>` opcji `--host`/`--port` → metawartości polskie (A05, przekazane koordynatorowi). (2) §7.3 „Docstringi i komentarze … nie trafia do użytkownika” jest nieścisłe: docstringi publicznych typów wyników (`ArchiveFile`, `StoreInfo`, `HydroCurrentData`, …) są opisami schematów `components` w `/openapi.json`. Zostają po angielsku (DEVELOPMENT_STANDARDS §4: ta sama dokumentacja co `help()`; dokument OpenAPI nie jest tłumaczony, §4.4); tak samo tytuły pól tworzone przez pydantic z nazw (`Valid From`, `Error Code`) i opisy domyślne FastAPI („Successful Response”). §7.3 dostaje też: znacznik typu Typer `<str>` przy argumentach pozycyjnych `imgw admin` (Typer nie ma ustawienia, a metawartość jest już polska), podpowiedź Click `[y/N]` pytania `typer.confirm` (odpowiedzi `y`/`n` przyjmuje Click) i dziennik konsoli `templates/map.html:246` (jak `app.js`). Brak innych nowych pozycji: słowa bez znaków diakrytycznych w literałach to poprawne słowa polskie albo klucze źródeł (`zachmurzenie_ogolne`), angielskie literały to warianty `*_en`, docstringi stałych i wyrażenia regularne.

**Uzupełnienie (2026-10-19, A04)** — rozstrzygnięcia luk, bez zmiany kontraktu:

- `ATTRIBUTION` w `reference_data.py` to `get_provider("IMGW-PIB").license.attribution` (bez kopii tekstu); test porównuje linię „Wymagana atrybucja: …” z rejestrem.
- Test „strony poza OpenAPI” jest w `tests/unit/test_web_app.py` (każda trasa routera stron nieobecna w `/openapi.json`; przed zmianą nie przechodzi), bo `test_api_commands.py` liczy tylko trasy `/api/v1/`. Przypięcia pomocy CLI (`[OPCJE]`, `KOMENDA [ARGUMENTY]...` i ich angielskie odpowiedniki) w `tests/unit/test_cli_catalog.py`.
- Opisy pól modeli (poz. 18–26) używają jednostek `[°C]`, `[m³/s]`, `[°]`, `[oktanty]`; wartości `water_state` są w opisie bez tłumaczenia.
- Pliki spoza listy A04 (decyzja koordynatora i pozycje 35–36 erraty): `src/imgwtools/cli/_dispatch.py` (`_HelpTexts.options_metavar`, `commands_metavar`, `aborted`; linia użycia podmienia symbole Click w `_write_usage`), `src/imgwtools/web/templates/partials/download_links.html`, `tests/unit/test_cli_catalog.py`, `tests/unit/test_web_app.py`.

**A05 — Udostępnienie: `imgw mcp`, `/mcp`, `GET /llms.txt`, wdrożenie.**  
**Pliki:** `src/imgwtools/cli/main.py` (komenda `imgw mcp`; pozycje 15–17 z §7.2), `src/imgwtools/api/main.py` (montaż `/mcp` i lifespan, `GET /llms.txt`, pozycje 29–30), `src/imgwtools/api/schemas.py` (pozycja 31), `src/imgwtools/config.py` (`mcp_enabled`, `mcp_allowed_hosts`), `src/imgwtools/mcp/_calls.py` (wyłącznie wywołania trybu `http`), `docker/Dockerfile`, `docker/docker-compose.yml`, `docker/nginx.conf`; zmodyfikuj `tests/unit/test_cli_main.py`, `tests/unit/test_api_main.py`, `tests/live/test_interfaces_live.py` (noga MCP stdio); utwórz `tests/unit/test_mcp_stdio.py`, `tests/unit/test_mcp_http.py`, `tests/contract/test_mcp_http_contract.py`.  
**Zależy od:** A02, A03.  
**Test akceptacji:** testy „MCP stdio i HTTP” z §9; `imgw mcp --allow-writes` (i `IMGW_MCP_ALLOW_WRITES=true`) daje narzędzia zapisu z `check` domyślnie `true`; `/health` i `/api/v1` mają polskie podsumowania i opisy w OpenAPI; `docker compose -f docker/docker-compose.yml config` przechodzi, a obraz buduje się z `.[api,mcp]` na Pythonie 3.12 (jednorazowo, gdy Docker jest dostępny; wynik w notatkach); przebieg `IMGW_LIVE=1` nogi MCP raz na serwerach IMGW.

**Uzupełnienie (2026-10-19, A05)** — rozstrzygnięcia luk, bez zmiany kontraktu:

- `imgw mcp` (`cli/main.py`, `cls=ImgwCommand`): `--allow-writes` ze zmienną `IMGW_MCP_ALLOW_WRITES` (wartości logiczne Click: `true|false`, `1|0`, `yes|no`, `on|off`; inna wartość → `validation_error`, kod 2) i `--lang` (metawartość `pl|en`, domyślnie `IMGW_LANG` przez `envvar` Click, jak w `commands schema`). Najpierw import `imgwtools.mcp.server` — każdy `ImportError` (brak dodatku albo niezgodne SDK) to linia `missing_dependency` bez `details`, kod 6 — potem `run_stdio`; język spoza `pl|en` odrzuca `create_server` (`validation_error`, `details`: `option="lang"`, `value`, `allowed`), zanim serwer przeczyta stdin. Koniec stdin (klient zamyka połączenie) → kod 0 bez bajtu na stdout; Ctrl+C → kod 130 bez komunikatu.
- Pomoc `imgw server`: metawartości `ADRES` i `LICZBA` (pozycja 37 erraty A04); opis komendy wymienia `/mcp` („Uruchom serwer API: REST, web GUI i /mcp (przy IMGW_MCP_ENABLED=true).”).
- `api/main.py`: aplikację `/mcp` tworzy raz przy imporcie `_mcp_app()` (`http_app(lang=…)` z `IMGW_LANG` po `strip()`); do routera REST trafia wyłącznie jej trasa `/mcp` (`app.router.routes.extend(…)`, poza OpenAPI), a lifespan aplikacji REST uruchamia jej menedżera sesji. `IMGW_MCP_ENABLED=true` bez dodatku → ostrzeżenie w dzienniku `imgwtools.api.main` i 404 `not_found`; `IMGW_MCP_ENABLED=true` z `IMGW_LANG` spoza `pl|en` → `IMGWValidationError` przy imporcie aplikacji (`details.option="IMGW_LANG"`), więc serwer się nie uruchamia — jak `imgw server`, który kończy się wtedy linią błędu (§4.2); bez MCP REST nadal pomija `IMGW_LANG`.
- `GET /llms.txt`: `text/markdown; charset=utf-8`, `Content-Language` i `Vary: Accept-Language`, bez `Content-Disposition`; trasa jest w OpenAPI w grupie `System` (podsumowanie „Przewodnik llms.txt”), a opis API wymienia `GET /llms.txt` i `/mcp`.
- Zmiany poza listą A05 nie były potrzebne; decyzją koordynatora opis API w OpenAPI („API danych publicznych IMGW-PIB i ČHMÚ…”, „linki do serwerów IMGW-PIB i ČHMÚ”) i opis `imgw --help` („Narzędzie do pobierania danych publicznych IMGW-PIB i ČHMÚ.”) wymieniają obu dostawców 3.0.0; teksty nie mają wariantów angielskich (OpenAPI i pomoc korzenia CLI są tylko po polsku, §4.4).
- Wdrożenie: `docker/Dockerfile` — `python:3.12-slim`, `COPY pyproject.toml README.md LICENSE` (hatchling wymaga pliku z `license-files`) i `src/`, `pip install ".[api,mcp]"`, bez `COPY data/`, jeden proces uvicorn (sesje MCP żyją w procesie); `docker/docker-compose.yml` — bez przestarzałego klucza `version`, `IMGW_MCP_ENABLED` (domyślnie `false`), `IMGW_MCP_ALLOWED_HOSTS` (domyślnie `127.0.0.1,localhost`) i `IMGW_LANG` (domyślnie `pl`) z otoczenia `docker compose`; `docker/nginx.conf` — `location = /mcp` (dokładna ścieżka trasy SDK) z `limit_req zone=api_limit burst=20 nodelay`, `Host $host` (publiczna nazwa hosta należy więc do `IMGW_MCP_ALLOWED_HOSTS`), `proxy_buffering off`, `proxy_cache off` i `proxy_read_timeout 3600s`; ten sam blok, zakomentowany, w szablonie HTTPS.
- Testy: `tests/unit/test_mcp_http.py` importuje `imgwtools.api.main` ponownie pod ustawieniami testu (moduł i atrybut pakietu przywraca `monkeypatch`), a klient SDK łączy się z `/mcp` przez `httpx2.ASGITransport` w lifespanie tej aplikacji (tryby klienta `auto` i `legacy`); `tests/contract/test_mcp_http_contract.py` porównuje z REST każdy przypadek `CASES` (POST z `?check=true`, lista bez `limit` = strona 50, te same żądania do nagrań) i każdy scenariusz błędu kontraktu poza `method_not_allowed` (narzędzie nie wysyła innej metody niż trasa). Noga MCP na żywo to osobny test (`-k imgw_mcp`): jeden proces `imgw mcp` na przebieg, komendy z `writes = none` i `network` (9 komend, 10 przypadków), Python i narzędzie z tymi samymi opcjami (z `root`), katalogi bez zmian.
- Sprawdzenia jednorazowe (2026-10-19): `docker compose -f docker/docker-compose.yml config` — bez błędów; obraz z `.[api,mcp]` zbudowany (Python 3.12.15, imgwtools 3.0.0), a kontener z `IMGW_MCP_ENABLED=true` odpowiada na `/health`, `GET /llms.txt` (`Accept-Language: en`) i `initialize` na `/mcp`; `nginx -t` z nowym plikiem — bez błędów; `IMGW_LIVE=1` nogi MCP — 10 z 10 przypadków zgodnych z Pythonem (tolerowane wyłącznie `checked_at`), przypadki `datasets providers` i `commands guide` zgodne w Pythonie, CLI i REST.

### Fala A4

**A06 — Dokumentacja wsparcia agentów.**  
**Pliki:** `docs/CHANGELOG.md`, `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`, `docs/DEVELOPMENT_STANDARDS.md` (§1.3: teksty polskie domyślnie, angielski wariant katalogu; liczba testów), `docs/RULES.md` (liczba testów), `docs/DECISIONS.md` (datowane erraty ADR-002 D1, D2, D14 i ADR-003 D13 według sekcji „Wpływ” ADR-004; status ADR-004 po zatwierdzeniu), `docs/superpowers/specs/2026-10-17-versioned-store-design.md` (noty `[ADR-004]` w §13.1 p. 5, §13.2, §13.3, §13.5, §13.9, §13.10), `docs/superpowers/specs/2026-10-18-chmi-provider-design.md` (nota `[ADR-004]` w §9.3: 37 komend); regeneracja `AGENTS.md` i `llms.txt`, jeśli test dryfu tego wymaga.  
**Zależy od:** C10 (te same pliki dokumentacji), A05.  
**Test akceptacji:** CHANGELOG 3.0.0 („Dodane”) obejmuje dodatek `imgwtools[mcp]`, `imgw mcp`, `/mcp`, `GET /llms.txt`, `commands guide` i `agent_guide`, `lang`, `Accept-Language`, `IMGW_LANG`, opisy angielskie, metadane skutków i porządek komunikatów; README ma sekcję o agentach (konfiguracja klienta MCP z §6.11, odesłanie do `AGENTS.md`), a jej przykłady uruchomiono raz; tabele komend w README i `CLAUDE.md` zgadzają się z `imgw commands schema` (skrypt jednorazowy); test dryfu przechodzi; historyczne wpisy ADR bez przeredagowania (wyłącznie erraty).
