"""Messages of ``agent_guide.py``: the words of AGENTS.md and llms.txt."""

from imgwtools.messages import Text

MESSAGES = {
    "country_poland": Text(
        "Poland",
        "Polska",
    ),
    "country_czechia": Text(
        "Czechia",
        "Czechy",
    ),
    "effect_read": Text(
        "Read — no network, no writes",
        "Odczyt — bez sieci i bez zapisu",
    ),
    "effect_network": Text(
        "Network — connects to a source, writes nothing",
        "Sieć — łączy się ze źródłem, nic nie zapisuje",
    ),
    "effect_add": Text(
        "Write — new files, versions or tasks; `--check` first",
        "Zapis — nowe pliki, wersje albo zadania; najpierw `--check`",
    ),
    "effect_replace": Text(
        "Overwrite — may replace an existing file or manifest; `--check` first",
        "Nadpisanie — może zastąpić istniejący plik albo manifest; najpierw `--check`",
    ),
    "mark_add": Text(
        "write",
        "zapis",
    ),
    "mark_replace": Text(
        "overwrite",
        "nadpisanie",
    ),
    "mark_itself": Text(
        "is a check",
        "jest sprawdzeniem",
    ),
    "mark_local": Text(
        "local",
        "lokalna",
    ),
    "outside_store": Text(
        "Outside the store (`datasets files` and `datasets download` only):",
        "Poza magazynem (tylko `datasets files` i `datasets download`):",
    ),
    "header_status": Text(
        "Status",
        "Status",
    ),
    "header_exit_code": Text(
        "CLI exit code",
        "Kod wyjścia CLI",
    ),
    "header_meaning": Text(
        "Meaning",
        "Znaczenie",
    ),
    "header_key": Text(
        "Key",
        "Klucz",
    ),
    "header_variables": Text(
        "Variables",
        "Zmienne",
    ),
    "header_first_year": Text(
        "First year",
        "Od roku",
    ),
    "status_ok": Text(
        "no failures",
        "bez porażek",
    ),
    "status_partial": Text(
        "some items failed — read `items[].status` and `error_code`; the others are "
        "done",
        "część pozycji nieudana — przeczytaj `items[].status` i `error_code`; "
        "pozostałe są gotowe",
    ),
    "status_failed": Text(
        "no item succeeded (in a plan: `check_failed`); the envelope is complete",
        "żadna pozycja się nie udała (w planie: `check_failed`); koperta jest pełna",
    ),
    "status_cancelled": Text(
        "cancelled (Ctrl+C, a cancelled request); a partial `result` or `null`",
        "przerwano (Ctrl+C, anulowanie żądania); `result` częściowy albo `null`",
    ),
    "rule_learn_commands": Text(
        "**Learn the commands:** `imgw commands list` (a one-sentence summary of "
        "each), then `imgw commands schema --command …` or `imgw <group> <command> "
        "--schema`; REST `GET /api/v1/commands/list` and `/schema`; in MCP "
        "`imgw_commands_list` and `imgw_commands_schema`. Options are JSON Schema "
        "properties; rules the schema does not express are in `x-imgw.rules`, "
        "effects in `x-imgw.writes`, `x-imgw.network` and `x-imgw.idempotent`.",
        "**Poznaj komendy:** `imgw commands list` (spis z opisem jednego zdania), "
        "potem `imgw commands schema --command …` albo `imgw <grupa> <komenda> "
        "--schema`; REST `GET /api/v1/commands/list` i `/schema`; w MCP "
        "`imgw_commands_list` i `imgw_commands_schema`. Opcje to właściwości JSON "
        "Schema; reguły nieopisane schematem są w `x-imgw.rules`, skutki w "
        "`x-imgw.writes`, `x-imgw.network` i `x-imgw.idempotent`.",
    ),
    "rule_check_first": Text(
        "**Check without writing:** `--check` (CLI), `?check=true` (REST, POST), "
        "`check: true` (MCP; the default of writing commands), `check_command()` "
        "(Python) → an `imgw-plan/1` plan without writing and without downloading "
        "content. `store check` and `project check` are checks themselves. Ask the "
        "user about a large plan.",
        "**Sprawdź bez zapisu:** `--check` (CLI), `?check=true` (REST, POST), "
        "`check: true` (MCP; domyślne dla komend zapisujących), `check_command()` "
        "(Python) → plan `imgw-plan/1` bez zapisu i bez pobierania treści. `store "
        "check` i `project check` same są sprawdzeniem. Przy dużym planie zapytaj "
        "użytkownika.",
    ),
    "rule_run": Text(
        "**Run:** without `check`; read the `status` of the envelope, not only the "
        "exit code.",
        "**Uruchom:** bez `check`; czytaj `status` koperty, nie tylko kod wyjścia.",
    ),
    "rule_read_offline": Text(
        "**Read offline:** `store info`, `store scan`, `series summary`, `series "
        "read` (`limit`/`offset`), `pmaxtp read` — without downloading again.",
        "**Czytaj offline:** `store info`, `store scan`, `series summary`, `series "
        "read` (`limit`/`offset`), `pmaxtp read` — bez ponownego pobierania.",
    ),
    "rule_decide_by_codes": Text(
        "**Decide by codes:** `code`, `status`, `items[].status`, `error_code`; the "
        "`detail` text is for humans.",
        "**Decyduj po kodach:** `code`, `status`, `items[].status`, `error_code`; "
        "tekst `detail` jest dla człowieka.",
    ),
    "symbol_station_code": Text(
        "STATION_CODE",
        "KOD_STACJI",
    ),
    "symbol_wigos_id": Text(
        "WIGOS_ID",
        "KOD_WIGOS",
    ),
    "symbol_project": Text(
        "PROJECT",
        "PROJEKT",
    ),
    "flow_precipitation_title": Text(
        "Daily precipitation at the Poznań station, 2010–2020",
        "Opady dobowe ze stacji Poznań, 2010–2020",
    ),
    "flow_precipitation_find_station": Text(
        "several hits → ask the user; the code of the chosen station is "
        "`STATION_CODE`.",
        "kilka trafień → zapytaj użytkownika; kod wybranej stacji to `KOD_STACJI`.",
    ),
    "flow_precipitation_choose_dataset": Text(
        "Choose the dataset: `pl.imgw.meteo_precip_daily` (precipitation stations, "
        "`P`) or `pl.imgw.meteo_climate_daily` (climate stations, `P` and "
        "temperatures) — the station list does not tell the network of a station.",
        "Wybierz zbiór: `pl.imgw.meteo_precip_daily` (stacje opadowe, `P`) albo "
        "`pl.imgw.meteo_climate_daily` (stacje klimatyczne, `P` i temperatury) — "
        "lista stacji nie mówi, w której sieci jest stacja.",
    ),
    "flow_precipitation_plan": Text(
        "plan: the number of files and bytes; the archives cover the whole country, "
        "so tell the user the size.",
        "plan: liczba plików i bajtów; archiwa obejmują cały kraj, więc podaj "
        "użytkownikowi rozmiar.",
    ),
    "flow_precipitation_sync": Text(
        "after the user agrees; the station series are built as well.",
        "po zgodzie użytkownika; szeregi stacji budują się same.",
    ),
    "flow_precipitation_summary": Text(
        "the station is missing → repeat steps 3–5 with "
        "`pl.imgw.meteo_climate_daily`; missing from both → tell the user, do not "
        "substitute another station.",
        "brak stacji → powtórz kroki 3–5 z `pl.imgw.meteo_climate_daily`; brak w obu "
        "→ powiedz to użytkownikowi, nie podstawiaj innej stacji.",
    ),
    "flow_czech_discharge_title": Text(
        "Daily discharge of a Czech station (ČHMÚ)",
        "Przepływy dobowe stacji czeskiej (ČHMÚ)",
    ),
    "flow_czech_discharge_find_station": Text(
        "the WIGOS identifier of the chosen station is `WIGOS_ID`.",
        "identyfikator WIGOS wybranej stacji to `KOD_WIGOS`.",
    ),
    "flow_czech_discharge_plan": Text(
        "plan: the station files by year.",
        "plan: pliki stacji po latach.",
    ),
    "flow_czech_discharge_sync": Text(
        "after the user agrees.",
        "po zgodzie użytkownika.",
    ),
    "flow_project_title": Text(
        "Reproducible project",
        "Odtwarzalny projekt",
    ),
    "flow_project_init": Text(
        "the `imgw-project.json` manifest; `store_dir` relative to the project "
        "directory.",
        "manifest `imgw-project.json`; `store_dir` względem katalogu projektu.",
    ),
    "flow_project_add_task": Text(
        "the task keeps the command and its options (without `root`).",
        "zadanie zapamiętuje komendę i jej opcje (bez `root`).",
    ),
    "flow_project_plan": Text(
        "the plan…",
        "plan…",
    ),
    "flow_project_download": Text(
        "…then the files are downloaded and pinned (SHA-256) after the user agrees.",
        "…potem pobranie i przypięcie plików (SHA-256) po zgodzie użytkownika.",
    ),
    "flow_project_verify": Text(
        "the SHA-256 sums of the pinned files (offline).",
        "sumy SHA-256 przypiętych plików (offline).",
    ),
    "flow_next_pages": Text(
        "next pages: `--offset`.",
        "kolejne strony: `--offset`.",
    ),
    "summary": Text(
        "Version {version}. Providers: {providers}. Datasets in the registry: "
        "{datasets}. Commands of the catalog shared by every interface: {commands} "
        "(groups: {groups}).",
        "Wersja {version}. Dostawcy: {providers}. Zbiory w rejestrze: {datasets}. "
        "Komendy katalogu wspólnego dla wszystkich interfejsów: {commands} (grupy: "
        "{groups}).",
    ),
    "provider_line": Text(
        "- {label} — {country}: keys {keys}, station code {station}, license {license}",
        "- {label} — {country}: klucze {keys}, kod stacji {station}, licencja "
        "{license}",
    ),
    "flags_lists": Text(
        "- Lists ({lists}): comma-separated values (`--months 1,2`) or a repeated "
        "flag (`-s A -s B`). Years ({years}): `2024`, `2020-2023`, `2020,2022` or "
        "`2018,2020-2023`. Dates ({dates}): ISO `YYYY-MM-DD`.",
        "- Listy ({lists}): wartości po przecinku (`--months 1,2`) albo powtórzona "
        "flaga (`-s A -s B`). Roczniki ({years}): `2024`, `2020-2023`, `2020,2022` "
        "albo `2018,2020-2023`. Daty ({dates}): ISO `RRRR-MM-DD`.",
    ),
    "flags_switches": Text(
        "- Switches on by default: {toggles} (`--no-…` turns it off); the other "
        "boolean flags ({switches}) take no value and turn their option on.",
        "- Przełączniki domyślnie włączone: {toggles} (`--no-…` wyłącza); pozostałe "
        "flagi logiczne ({switches}) nie mają wartości i włączają swoją opcję.",
    ),
    "flags_environment": Text(
        "- Environment: `IMGW_STORE_ROOT` — the default `--root` (CLI, MCP stdio; "
        "{roots}); `IMGW_LANG` — the language of the CLI help and of the progress "
        "lines (`pl`, `en`).",
        "- Zmienne środowiskowe: `IMGW_STORE_ROOT` — domyślne `--root` (CLI, MCP "
        "stdio; {roots}); `IMGW_LANG` — język pomocy CLI i linii postępu (`pl`, "
        "`en`).",
    ),
    "flags_root_when": Text(
        "{command} — only with {conditions}",
        "{command} — tylko przy {conditions}",
    ),
}
