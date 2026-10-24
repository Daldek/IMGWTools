"""
Guide for AI agents generated from the command catalog (spec 2026-10-19 §5).

`agent_guide` renders ``AGENTS.md`` (``format="agents"``) and ``llms.txt``
(``format="llms"``), in Polish or English, from the hand-written templates in
``imgwtools/_data/agents``. Every marker ``<!-- imgw:<block> -->`` of a
template is replaced by a block generated from the command catalog
(`command_schema`, `data_commands`), the registries (`providers`,
`datasets` and the error codes of the catalog document) and the data of this
module: the rules shared with the MCP server instructions, the meaning of the
envelope statuses and the typical flows, whose commands `format_command`
renders. A marker filling a whole line takes a block of any number of lines,
a marker inside a line a one-line block; an unknown block or a block used
twice is a program error. The output depends only on the installed package
(no dates, no local paths), so ``AGENTS.md`` and ``llms.txt`` of the
repository are derived files that the tests compare byte for byte with the
generator.

`_instructions` gives the MCP server its ``instructions``: the rules and the
lines of the server mode.
"""

import json
import os
import re
import shlex
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, cast, overload

from imgwtools._version import __version__
from imgwtools.commands import (
    Lang,
    command_schema,
    data_commands,
    format_command,
    validate_command,
)
from imgwtools.datasets import datasets, providers
from imgwtools.store.export import _deliver, _Lines, _target
from imgwtools.store.types import PathArg

__all__ = ["GuideFormat", "agent_guide"]

GuideFormat = Literal["agents", "llms"]
# Modes of the MCP server (spec 2026-10-19 §6.3).
McpMode = Literal["read", "write", "http"]

# Default page size of the list tools of the MCP server (spec 2026-10-19 §6.4).
_PAGE_SIZE = 50
_MARKER = re.compile(r"<!--\s*imgw:(?P<name>[^\s>]*)\s*-->")
_DASH = "—"
# Country names of the country codes of the provider registry.
_COUNTRIES: Mapping[str, tuple[str, str]] = {
    "PL": ("Polska", "Poland"),
    "CZ": ("Czechy", "Czechia"),
}
# Texts of the generated blocks: (Polish, English).
_TEXTS: Mapping[str, tuple[str, str]] = {
    "read": ("odczyt", "read"),
    "network": ("sieć", "network"),
    "add": ("zapis", "write"),
    "replace": ("zapis z nadpisaniem", "write (may overwrite)"),
    "itself": ("sama", "itself"),
    "stream": ("strumień linii", "text lines"),
    "one_of": ("dokładnie jedno z:", "exactly one of:"),
    "requires": ("wymaga", "requires"),
    "yes": ("tak", "yes"),
    "no": ("nie", "no"),
}
_HEADERS: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "providers": (
        ("Dostawca", "Nazwa", "Kraj", "Klucze zbiorów", "Licencja", "Kod stacji"),
        ("Provider", "Name", "Country", "Dataset keys", "License", "Station code"),
    ),
    "statuses": (
        ("Status", "Kod wyjścia CLI", "Znaczenie"),
        ("Status", "CLI exit code", "Meaning"),
    ),
    "errors": (
        ("Kod", "Tytuł", "Kod wyjścia CLI", "HTTP"),
        ("Code", "Title", "CLI exit code", "HTTP"),
    ),
    "datasets": (
        (
            "Klucz",
            "Dostawca",
            "Rodzaj",
            "Jednostka czasu",
            "Zmienne",
            "Od roku",
            "W magazynie",
            "Zakres pliku",
            "Alias legacy",
            "Tytuł",
        ),
        (
            "Key",
            "Provider",
            "Kind",
            "Time unit",
            "Variables",
            "First year",
            "In store",
            "File scope",
            "Legacy alias",
            "Title",
        ),
    ),
    "commands": (
        ("Komenda", "Opis", "Funkcja → wynik", "Opcje", "Skutek", "Check", "REST"),
        (
            "Command",
            "Description",
            "Function → result",
            "Options",
            "Effect",
            "Check",
            "REST",
        ),
    ),
    "aliases": (("Skrót", "Flaga"), ("Alias", "Flag")),
}
# Meaning of each envelope status (spec 2026-10-17 §13.6).
_STATUSES: Mapping[str, tuple[str, str]] = {
    "ok": ("bez porażek", "no failures"),
    "partial": (
        "część pozycji nieudana — przeczytaj `items[].status` i `error_code`; "
        "pozostałe są gotowe",
        "some items failed — read `items[].status` and `error_code`; the others "
        "are done",
    ),
    "failed": (
        "żadna pozycja się nie udała (w planie: `check_failed`); koperta jest pełna",
        "no item succeeded (in a plan: `check_failed`); the envelope is complete",
    ),
    "cancelled": (
        "przerwano (Ctrl+C, anulowanie żądania); `result` częściowy albo `null`",
        "cancelled (Ctrl+C, a cancelled request); a partial `result` or `null`",
    ),
}
# The rules of AGENTS.md, llms.txt and the MCP instructions (spec 2026-10-19 §5.4).
_PRINCIPLES: tuple[tuple[str, str], ...] = (
    (
        "**Poznaj komendy:** `imgw commands list` (spis z opisem jednego zdania), "
        "potem `imgw commands schema --command … [--lang en]` albo `imgw <grupa> "
        "<komenda> --schema`; REST `GET /api/v1/commands/list` i `/schema`; w MCP "
        "`imgw_commands_list` i `imgw_commands_schema`. Opcje to właściwości JSON "
        "Schema; reguły nieopisane schematem są w `x-imgw.rules`, skutki w "
        "`x-imgw.writes`, `x-imgw.network` i `x-imgw.idempotent`.",
        "**Learn the commands:** `imgw commands list` (a one-sentence summary of "
        "each), then `imgw commands schema --command … [--lang en]` or `imgw "
        "<group> <command> --schema`; REST `GET /api/v1/commands/list` and "
        "`/schema`; in MCP `imgw_commands_list` and `imgw_commands_schema`. Options "
        "are JSON Schema properties; rules the schema does not express are in "
        "`x-imgw.rules`, effects in `x-imgw.writes`, `x-imgw.network` and "
        "`x-imgw.idempotent`.",
    ),
    (
        "**Sprawdź bez zapisu:** `--check` (CLI), `?check=true` (REST, POST), "
        "`check: true` (MCP; domyślne dla komend zapisujących), `check_command()` "
        "(Python) → plan `imgw-plan/1` bez zapisu i bez pobierania treści. "
        "`store check` i `project check` same są sprawdzeniem. Przy dużym planie "
        "zapytaj użytkownika.",
        "**Check without writing:** `--check` (CLI), `?check=true` (REST, POST), "
        "`check: true` (MCP; the default of writing commands), `check_command()` "
        "(Python) → an `imgw-plan/1` plan without writing and without downloading "
        "content. `store check` and `project check` are checks themselves. Ask the "
        "user about a large plan.",
    ),
    (
        "**Uruchom:** bez `check`; czytaj `status` koperty, nie tylko kod wyjścia.",
        "**Run:** without `check`; read the `status` of the envelope, not only the "
        "exit code.",
    ),
    (
        "**Czytaj offline:** `store info`, `store scan`, `series summary`, "
        "`series read` (`limit`/`offset`), `pmaxtp read` — bez ponownego pobierania.",
        "**Read offline:** `store info`, `store scan`, `series summary`, "
        "`series read` (`limit`/`offset`), `pmaxtp read` — without downloading "
        "again.",
    ),
    (
        "**Decyduj po kodach:** `code`, `status`, `items[].status`, `error_code`; "
        "tekst `detail` jest dla człowieka.",
        "**Decide by codes:** `code`, `status`, `items[].status`, `error_code`; the "
        "`detail` text is for humans.",
    ),
)


@dataclass(frozen=True)
class _Symbol:
    """
    Value found by an earlier step of a flow.

    The guide prints the name of the symbol in its language; `format_command`
    validates the command with ``stand_in`` (an absolute path for ``path``
    symbols) in its place.
    """

    pl: str
    en: str
    stand_in: str
    path: bool = False

    def name(self, lang: Lang) -> str:
        return self.en if lang == "en" else self.pl

    def rendered(self) -> str:
        """Text of the stand-in in a line of `format_command`."""
        if not self.path:
            return self.stand_in
        return shlex.quote(os.fspath(Path(self.stand_in).absolute()))


@dataclass(frozen=True)
class _Step:
    """One step of a flow: a catalog command with a note, or a decision alone."""

    command: str | None
    options: Mapping[str, object]
    note_pl: str
    note_en: str
    check: bool = False


@dataclass(frozen=True)
class _Flow:
    """A typical task of an agent as steps rendered by `format_command`."""

    title_pl: str
    title_en: str
    steps: tuple[_Step, ...]


_STATION = _Symbol("KOD_STACJI", "STATION_CODE", "123456789")
_WIGOS = _Symbol("KOD_WIGOS", "WIGOS_ID", "0-203-1-900001")
_PROJECT = _Symbol("PROJEKT", "PROJECT", "/PROJEKT", path=True)
_SYMBOLS = (_STATION, _WIGOS, _PROJECT)
_STORE = "/dane/imgw"
_PRECIP = "pl.imgw.meteo_precip_daily"
_CHMI_HYDRO = "cz.chmi.hydro_daily"
_POINT = {"latitude": 52.23, "longitude": 21.01}
_PRECIP_STORE = {"root": _STORE, "datasets": [_PRECIP], "years": "2010-2020"}
_PRECIP_DAYS = {
    "root": _STORE,
    "dataset": _PRECIP,
    "station": _STATION,
    "variables": ["P"],
    "start": "2010-01-01",
    "end": "2020-12-31",
}
_CHMI_STORE = {
    "root": _STORE,
    "datasets": [_CHMI_HYDRO],
    "stations": [_WIGOS],
    "years": "2020-2025",
}
_FLOWS: tuple[_Flow, ...] = (
    _Flow(
        "Opady dobowe ze stacji Poznań, 2010–2020",
        "Daily precipitation at the Poznań station, 2010–2020",
        (
            _Step(
                "stations find",
                {"kind": "meteo", "query": "poznan"},
                "kilka trafień → zapytaj użytkownika, nie wybieraj sam; kod "
                "wybranej stacji to `KOD_STACJI`.",
                "several hits → ask the user, do not choose yourself; the code of "
                "the chosen station is `STATION_CODE`.",
            ),
            _Step(
                None,
                {},
                "Wybierz zbiór: `pl.imgw.meteo_precip_daily` (stacje opadowe, `P`) "
                "albo `pl.imgw.meteo_climate_daily` (stacje klimatyczne, `P` i "
                "temperatury) — lista stacji IMGW-PIB nie mówi, w której sieci jest "
                "stacja, a dobowe archiwa synoptyczne są plikami per stacja i nie są "
                "obsługiwane.",
                "Choose the dataset: `pl.imgw.meteo_precip_daily` (precipitation "
                "stations, `P`) or `pl.imgw.meteo_climate_daily` (climate stations, "
                "`P` and temperatures) — the IMGW-PIB station list does not tell "
                "the network of a station, and the daily synoptic archives are "
                "per-station files, not supported.",
            ),
            _Step(
                "store check",
                _PRECIP_STORE,
                "plan: liczba plików i bajtów; archiwa IMGW-PIB obejmują cały kraj, "
                "więc podaj użytkownikowi rozmiar.",
                "plan: the number of files and bytes; IMGW-PIB archives cover the "
                "whole country, so tell the user the size.",
            ),
            _Step(
                "store sync",
                _PRECIP_STORE,
                "po zgodzie użytkownika; szeregi stacji budują się same "
                "(`--series` domyślnie).",
                "after the user agrees; the station series are built as well "
                "(`--series` by default).",
            ),
            _Step(
                "series summary",
                {"root": _STORE, "dataset": _PRECIP, "stations": [_STATION]},
                "brak stacji w spisie → powtórz kroki 3–5 z "
                "`pl.imgw.meteo_climate_daily`; brak w obu → powiedz użytkownikowi, "
                "że obsługiwane zbiory nie mają danych tej stacji w tym okresie (np. "
                "stacja synoptyczna albo nieczynna), zamiast podstawiać inną stację.",
                "the station is missing from the summary → repeat steps 3–5 with "
                "`pl.imgw.meteo_climate_daily`; missing from both → tell the user "
                "that the supported datasets have no data of this station in this "
                "period (e.g. a synoptic or closed station) instead of substituting "
                "another station.",
            ),
            _Step(
                "series read",
                {**_PRECIP_DAYS, "limit": 500},
                "kolejne strony: `--offset`.",
                "next pages: `--offset`.",
            ),
            _Step(
                "series export",
                {**_PRECIP_DAYS, "path": "/dane/wyniki/opady.csv"},
                "albo plik CSV: jednostki w nagłówku, flagi wartości, atrybucja w "
                "pierwszym wierszu danych.",
                "or a CSV file: units in the header, value flags, the attribution "
                "in the first data row.",
            ),
        ),
    ),
    _Flow(
        "Stan wody teraz",
        "Water level now",
        (
            _Step(
                "current hydro",
                {"station": _STATION},
                "bieżący pomiar stacji z API IMGW-PIB na żywo; zachowaj wynik "
                "zamiast odpytywać w pętli.",
                "the current reading of the station from the live IMGW-PIB API; "
                "keep the result instead of polling.",
            ),
            _Step(
                "current hydro-states",
                {"main_only": True},
                "stany wody stacji głównych ze współrzędnymi (`water_state`).",
                "water states of the main stations with coordinates (`water_state`).",
            ),
        ),
    ),
    _Flow(
        "Opad maksymalny prawdopodobny (PMAXTP) dla punktu",
        "Probable maximum precipitation (PMAXTP) for a point",
        (
            _Step(
                "pmaxtp fetch",
                _POINT,
                "metoda `POT` domyślnie (`--method AMP` — maksima roczne); punkt w "
                "Polsce.",
                "method `POT` by default (`--method AMP` — annual maxima); a point "
                "in Poland.",
            ),
            _Step(
                "pmaxtp sync",
                {"root": _STORE, **_POINT},
                "do magazynu: najpierw plan…",
                "into the store: the plan first…",
                check=True,
            ),
            _Step(
                "pmaxtp sync",
                {"root": _STORE, **_POINT},
                "…potem zapis komórki siatki po zgodzie użytkownika.",
                "…then the grid cell is written after the user agrees.",
            ),
        ),
    ),
    _Flow(
        "Przepływy dobowe stacji czeskiej (ČHMÚ)",
        "Daily discharge of a Czech station (ČHMÚ)",
        (
            _Step(
                "stations find",
                {"provider": "CHMI", "kind": "hydro", "query": "spindleruv"},
                "identyfikator WIGOS wybranej stacji to `KOD_WIGOS`.",
                "the WIGOS identifier of the chosen station is `WIGOS_ID`.",
            ),
            _Step(
                "store check",
                _CHMI_STORE,
                "plan: pliki stacji po latach.",
                "plan: the station files by year.",
            ),
            _Step(
                "store sync",
                _CHMI_STORE,
                "po zgodzie użytkownika.",
                "after the user agrees.",
            ),
            _Step(
                "series read",
                {
                    "root": _STORE,
                    "dataset": _CHMI_HYDRO,
                    "station": _WIGOS,
                    "variables": ["Q"],
                    "limit": 500,
                },
                "kolejne strony: `--offset`.",
                "next pages: `--offset`.",
            ),
        ),
    ),
    _Flow(
        "Odtwarzalny projekt",
        "Reproducible project",
        (
            _Step(
                "project init",
                {"project_dir": _PROJECT, "store_dir": "../magazyn"},
                "manifest `imgw-project.json`; `store_dir` względem katalogu projektu.",
                "the `imgw-project.json` manifest; `store_dir` relative to the "
                "project directory.",
            ),
            _Step(
                "project add",
                {
                    "project_dir": _PROJECT,
                    "name": "opady",
                    "command": "series select",
                    "options": {
                        "dataset": _PRECIP,
                        "stations": [_STATION],
                        "years": "2010-2020",
                    },
                },
                "zadanie zapamiętuje komendę i jej opcje (bez `root`).",
                "the task keeps the command and its options (without `root`).",
            ),
            _Step(
                "project download",
                {"project_dir": _PROJECT},
                "plan…",
                "the plan…",
                check=True,
            ),
            _Step(
                "project download",
                {"project_dir": _PROJECT},
                "…potem pobranie i przypięcie plików (SHA-256) po zgodzie użytkownika.",
                "…then the files are downloaded and pinned (SHA-256) after the user "
                "agrees.",
            ),
            _Step(
                "project verify",
                {"project_dir": _PROJECT},
                "sumy SHA-256 przypiętych plików (offline).",
                "the SHA-256 sums of the pinned files (offline).",
            ),
        ),
    ),
)
# Lines of the MCP instructions per server mode (spec 2026-10-19 §6.3–§6.4).
_MODES: Mapping[str, tuple[str, str]] = {
    "read": (
        "Tryb serwera: bez zapisu — komendy zapisujące mają `check` stałe `true` i "
        "zwracają plan `imgw-plan/1`, opcje zapisujące są niedostępne; zapis włącza "
        "użytkownik (`imgw mcp --allow-writes`), nie agent.",
        "Server mode: no writes — writing commands have `check` fixed to `true` and "
        "return an `imgw-plan/1` plan, writing options are unavailable; the user, "
        "not the agent, enables writes (`imgw mcp --allow-writes`).",
    ),
    "write": (
        "Tryb serwera: zapis włączony — komendy zapisujące domyślnie zwracają plan "
        "(`check: true`); zapis wymaga `check: false` po zgodzie użytkownika.",
        "Server mode: writes enabled — writing commands return a plan by default "
        "(`check: true`); writing needs `check: false` after the user agrees.",
    ),
    "http": (
        "Tryb serwera: HTTP (fasada REST) — tylko odczyt i plan (`check` stałe "
        "`true`); narzędzia mają wyłącznie komendy z trasą REST i ich opcje REST.",
        "Server mode: HTTP (REST facade) — reading and planning only (`check` fixed "
        "to `true`); the tools are only the commands with a REST route and their "
        "REST options.",
    ),
}


def _localized[T](pair: tuple[T, T], lang: Lang) -> T:
    """The English element of a (Polish, English) pair for ``en``, else the Polish."""
    return pair[1] if lang == "en" else pair[0]


def _text(key: str, lang: Lang) -> str:
    return _localized(_TEXTS[key], lang)


def _code(text: object) -> str:
    return f"`{text}`"


def _code_or_dash(text: object) -> str:
    return _DASH if text is None else _code(text)


def _cell(text: str) -> str:
    """Table cell text: a pipe escaped, no line breaks."""
    return text.replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(_cell(text) for text in header) + " |",
        "|" + "---|" * len(header),
    ]
    lines += ["| " + " | ".join(_cell(text) for text in row) + " |" for row in rows]
    return "\n".join(lines)


def _header(name: str, lang: Lang) -> tuple[str, ...]:
    return _localized(_HEADERS[name], lang)


def _counted(number: int, singular: str, plural: str) -> str:
    """``number`` with a noun in the form governed by a preceding noun or preposition."""
    return f"{number} {singular if number == 1 else plural}"


# --- bloki -----------------------------------------------------------------------------------


def _summary(document: Mapping[str, Any], lang: Lang) -> str:
    owners = providers()
    names = ", ".join(
        f"{owner.short_name} — {_localized(_COUNTRIES[owner.country], lang)}"
        for owner in owners
    )
    commands, groups = len(document["commands"]), len(document["groups"])
    if lang == "en":
        return (
            f"Version {__version__}: a registry of "
            f"{_counted(len(datasets()), 'dataset', 'datasets')} of "
            f"{_counted(len(owners), 'provider', 'providers')} ({names}) and one "
            f"catalog of {_counted(commands, 'command', 'commands')} in "
            f"{_counted(groups, 'group', 'groups')} for every interface."
        )
    return (
        f"Wersja {__version__}: rejestr {_counted(len(datasets()), 'zbioru', 'zbiorów')} "
        f"{_counted(len(owners), 'dostawcy', 'dostawców')} ({names}) i jeden katalog "
        f"{_counted(commands, 'komendy', 'komend')} w "
        f"{_counted(groups, 'grupie', 'grupach')} dla wszystkich interfejsów."
    )


def _principles(lang: Lang) -> str:
    return "\n".join(
        f"{number}. {_localized(rule, lang)}"
        for number, rule in enumerate(_PRINCIPLES, start=1)
    )


def _providers(lang: Lang) -> str:
    rows = [
        (
            _code(owner.id),
            f"{owner.short_name} ({owner.name})",
            f"{_localized(_COUNTRIES[owner.country], lang)} ({owner.country})",
            _code(f"{owner.key_prefix}.*"),
            f"[{owner.license.id}]({owner.license.url})",
            _code(owner.station_code_pattern),
        )
        for owner in providers()
    ]
    return _table(_header("providers", lang), rows)


def _statuses(document: Mapping[str, Any], lang: Lang) -> str:
    rows = [
        (_code(status), str(code), _localized(_STATUSES[status], lang))
        for status, code in document["exit_codes"].items()
    ]
    return _table(_header("statuses", lang), rows)


def _errors(document: Mapping[str, Any], lang: Lang) -> str:
    rows = [
        (
            _code(error["code"]),
            error["title"],
            _DASH if error["exit_code"] is None else str(error["exit_code"]),
            _DASH if error["http_status"] is None else str(error["http_status"]),
        )
        for error in document["errors"]
    ]
    return _table(_header("errors", lang), rows)


def _datasets(lang: Lang) -> str:
    rows = [
        (
            _code(descriptor.key),
            _code(descriptor.provider),
            _code_or_dash(descriptor.kind),
            _code(descriptor.time_unit),
            ", ".join(_code(name) for name in descriptor.variables) or _DASH,
            _DASH if descriptor.first_year is None else str(descriptor.first_year),
            _text("yes" if descriptor.in_store else "no", lang),
            _code(descriptor.archive_scope),
            _code_or_dash(descriptor.legacy_alias),
            descriptor.title_en if lang == "en" else descriptor.title,
        )
        for descriptor in datasets()
    ]
    return _table(_header("datasets", lang), rows)


def _default(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _options(schema: Mapping[str, Any], lang: Lang) -> str:
    """Options in catalog order: ``*`` required, ``=`` default; groups and pairs."""
    required = set(schema.get("required", ()))
    words = []
    for name, prop in schema["properties"].items():
        word = name + ("*" if name in required else "")
        if "default" in prop:
            word += "=" + _default(prop["default"])
        words.append(_code(word))
    notes = []
    if "oneOf" in schema:
        groups = (
            "+".join(_code(name) for name in group["required"])
            for group in schema["oneOf"]
        )
        notes.append(f"{_text('one_of', lang)} {' / '.join(groups)}")
    for name, needed in schema.get("dependentRequired", {}).items():
        notes.append(
            f"{_code(name)} {_text('requires', lang)} "
            + ", ".join(_code(other) for other in needed)
        )
    text = ", ".join(words) or _DASH
    return f"{text} ({'; '.join(notes)})" if notes else text


def _effect(schema: Mapping[str, Any], lang: Lang) -> str:
    """Effect of a run (``writes``, ``network``) and the options writing a file."""
    meta = schema["x-imgw"]
    parts = [_text("network", lang)] if meta["network"] else []
    if meta["writes"] != "none":
        parts.append(_text(meta["writes"], lang))
    writing = [
        f"{_code(name)}: {_text(prop['x-imgw-writes'], lang)}"
        for name, prop in schema["properties"].items()
        if "x-imgw-writes" in prop
    ]
    return "; ".join([", ".join(parts) or _text("read", lang), *writing])


def _result(meta: Mapping[str, Any], lang: Lang) -> str:
    if meta["result"] == "stream":
        return _text("stream", lang)
    if meta["result"] == "list":
        return _code(f"Page[{meta['result_type']}]")
    return _code(meta["result_type"])


def _twin(meta: Mapping[str, Any], lang: Lang) -> str:
    if meta["check"] is not None:
        return _code(meta["check"])
    # The checks themselves (store check, project check, pmaxtp check).
    return _text("itself", lang) if meta["function"].startswith("check_") else _DASH


def _commands(document: Mapping[str, Any], lang: Lang) -> str:
    sections = []
    for group, title in document["groups"].items():
        rows = []
        for schema in document["commands"]:
            meta = schema["x-imgw"]
            if meta["group"] != group:
                continue
            rows.append(
                (
                    _code(meta["command"]),
                    schema["description"],
                    f"{_code(meta['function'])} → {_result(meta, lang)}",
                    _options(schema, lang),
                    _effect(schema, lang),
                    _twin(meta, lang),
                    _DASH if meta["rest"] is None else meta["rest"]["method"],
                )
            )
        table = _table(_header("commands", lang), rows)
        sections.append(f"### {_code(group)} — {title}\n\n{table}")
    return "\n\n".join(sections)


def _listed(flags: Iterable[str]) -> str:
    return ", ".join(_code(flag) for flag in sorted(set(flags)))


def _flags(document: Mapping[str, Any], lang: Lang) -> str:
    """Short aliases and the value syntax of every flag of the catalog."""
    aliases: dict[str, set[str]] = {}
    kinds: dict[str, set[str]] = {
        key: set() for key in ("list", "year", "toggle", "switch", "date", "object")
    }
    for schema in document["commands"]:
        for name, flags in schema["x-imgw"]["cli"]["flags"].items():
            canonical, *others = flags
            prop = schema["properties"][name]
            negative = f"--no-{canonical[2:]}"
            for flag in others:
                if flag != negative:
                    aliases.setdefault(flag, set()).add(canonical)
            kind = prop.get("type")
            if kind == "array":
                kinds["list"].add(canonical)
                if "anyOf" in prop["items"]:
                    kinds["year"].add(canonical)
            elif kind == "boolean":
                kinds["toggle" if negative in others else "switch"].add(canonical)
            elif kind == "object":
                kinds["object"].add(canonical)
            elif prop.get("format") == "date":
                kinds["date"].add(canonical)
    table = _table(
        _header("aliases", lang),
        (
            (_code(alias), _listed(aliases[alias]))
            for alias in sorted(aliases, key=lambda flag: (flag.startswith("--"), flag))
        ),
    )
    toggles = ", ".join(f"`{flag}/--no-{flag[2:]}`" for flag in sorted(kinds["toggle"]))
    only = "only with" if lang == "en" else "tylko przy"
    roots = "; ".join(
        f"{_code(spec.name)} — {only} "
        + ", ".join(
            _code(f"{name}={value}") for name, value in spec.env_root_when.items()
        )
        for spec in data_commands()
        if spec.env_root_when
    )
    if lang == "en":
        lines = [
            f"- Lists ({_listed(kinds['list'])}): comma-separated values "
            "(`--months 1,2`) or a repeated flag (`-s A -s B`).",
            f"- Years ({_listed(kinds['year'])}): a year `2024`, a range `2020-2023`, "
            "a list `2020,2022` or ranges in a list (`2018,2020-2023`).",
            f"- Dates ({_listed(kinds['date'])}): ISO `YYYY-MM-DD`.",
            f"- Switches on by default: {toggles} (`--no-…` turns it off); the other "
            f"boolean flags ({_listed(kinds['switch'])}) take no value and turn "
            "their option on.",
            f"- JSON objects ({_listed(kinds['object'])}): one shell argument, e.g. "
            '`--options \'{"dataset": "pl.imgw.hydro_daily", "years": "2024"}\'`.',
            "- Every command: `--schema` (the option schema, nothing is run); "
            "commands with a check twin: `--check` (a plan without writing).",
            "- Environment: `IMGW_STORE_ROOT` — the default `--root` (CLI, MCP "
            f"stdio; {roots}); `IMGW_LANG` — the language of the CLI help and the "
            "default `--lang` (`pl`, `en`).",
        ]
    else:
        lines = [
            f"- Listy ({_listed(kinds['list'])}): wartości po przecinku "
            "(`--months 1,2`) albo powtórzona flaga (`-s A -s B`).",
            f"- Roczniki ({_listed(kinds['year'])}): rocznik `2024`, zakres "
            "`2020-2023`, lista `2020,2022` albo zakresy na liście "
            "(`2018,2020-2023`).",
            f"- Daty ({_listed(kinds['date'])}): ISO `RRRR-MM-DD`.",
            f"- Przełączniki domyślnie włączone: {toggles} (`--no-…` wyłącza); "
            f"pozostałe flagi logiczne ({_listed(kinds['switch'])}) nie mają "
            "wartości i włączają swoją opcję.",
            f"- Obiekty JSON ({_listed(kinds['object'])}): jeden argument powłoki, "
            'np. `--options \'{"dataset": "pl.imgw.hydro_daily", "years": "2024"}\'`.',
            "- Każda komenda: `--schema` (schemat opcji bez uruchamiania); komendy z "
            "bliźniakiem: `--check` (plan bez zapisu).",
            "- Zmienne środowiskowe: `IMGW_STORE_ROOT` — domyślne `--root` (CLI, "
            f"MCP stdio; {roots}); `IMGW_LANG` — język pomocy CLI i domyślne "
            "`--lang` (`pl`, `en`).",
        ]
    return "\n".join([table, "", *lines])


def _substituted(value: object, stand_in: Callable[[_Symbol], object]) -> object:
    """``value`` with every symbol, also in lists and mappings, replaced."""
    if isinstance(value, _Symbol):
        return stand_in(value)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return {key: _substituted(item, stand_in) for key, item in mapping.items()}
    if isinstance(value, list | tuple):
        return [_substituted(item, stand_in) for item in cast(Iterable[object], value)]
    return value


def _command_line(step: _Step, lang: Lang) -> str:
    """The ``imgw`` line of a step: `format_command` with the symbols put back."""
    options = cast(
        Mapping[str, object], _substituted(step.options, lambda s: s.stand_in)
    )
    line = format_command(cast(str, step.command), options=options)
    for symbol in _SYMBOLS:
        line = line.replace(symbol.rendered(), symbol.name(lang))
    return line + (" --check" if step.check else "")


def _flows(lang: Lang) -> str:
    sections = []
    for number, flow in enumerate(_FLOWS, start=1):
        title = flow.title_en if lang == "en" else flow.title_pl
        lines = [f"### {number}. {title}", ""]
        for index, step in enumerate(flow.steps, start=1):
            note = step.note_en if lang == "en" else step.note_pl
            if step.command is not None:
                note = f"{_code(_command_line(step, lang))} — {note}"
            lines.append(f"{index}. {note}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


# --- szablony --------------------------------------------------------------------------------


def _blocks(lang: Lang) -> dict[str, Callable[[], str]]:
    """Generated blocks of the guide in ``lang`` (rendered only when used)."""
    document = command_schema(lang=lang)
    return {
        "version": lambda: __version__,
        "summary": lambda: _summary(document, lang),
        "rules": lambda: _principles(lang),
        "providers": lambda: _providers(lang),
        "statuses": lambda: _statuses(document, lang),
        "errors": lambda: _errors(document, lang),
        "datasets": lambda: _datasets(lang),
        "commands": lambda: _commands(document, lang),
        "flags": lambda: _flags(document, lang),
        "flows": lambda: _flows(lang),
    }


def _render(template: str, blocks: Mapping[str, Callable[[], str]]) -> list[str]:
    """
    Lines of ``template``, each ending with a newline, with every marker replaced.

    Raises
    ------
    ValueError
        If a marker names an unknown block, a block is used twice or a
        multi-line block stands inside a line (program errors of a template).
    """
    used: set[str] = set()

    def block(name: str) -> str:
        if name not in blocks:
            raise ValueError(f"Nieznany blok przewodnika {name!r} w szablonie")
        if name in used:
            raise ValueError(f"Blok przewodnika {name!r} użyty w szablonie dwa razy")
        used.add(name)
        return blocks[name]()

    def inline(match: re.Match[str]) -> str:
        text = block(match["name"])
        if "\n" in text:
            raise ValueError(
                f"Blok przewodnika {match['name']!r} ma wiele linii, a znacznik stoi "
                "wewnątrz linii szablonu"
            )
        return text

    lines: list[str] = []
    for line in template.removesuffix("\n").split("\n"):
        whole = _MARKER.fullmatch(line.strip())
        if whole is not None:
            lines += block(whole["name"]).split("\n")
        else:
            lines.append(_MARKER.sub(inline, line))
    return [f"{line}\n" for line in lines]


def _template(format: GuideFormat, lang: Lang) -> str:
    resource = files("imgwtools").joinpath("_data", "agents", f"{format}.{lang}.md")
    return resource.read_text(encoding="utf-8")


@overload
def agent_guide(
    *, format: GuideFormat = "agents", lang: Lang = "pl", path: None = None
) -> Iterator[str]: ...


@overload
def agent_guide(
    *, format: GuideFormat = "agents", lang: Lang = "pl", path: PathArg
) -> Path: ...


def agent_guide(
    *,
    format: GuideFormat = "agents",
    lang: Lang = "pl",
    path: PathArg | None = None,
) -> Iterator[str] | Path:
    """
    Generate the guide for AI agents from the command catalog and the registries.

    ``format="agents"`` gives ``AGENTS.md``: the rules (check → run → read),
    the interfaces, the envelope statuses and error codes, the providers and
    datasets, every command with its options and effects, the flags, typical
    flows and what not to do. ``format="llms"`` gives ``llms.txt`` (llms.txt
    v2): a summary, the rules and links to the documentation. The text depends
    only on the installed package (no dates, no local paths), so the
    repository files ``AGENTS.md`` and ``llms.txt`` equal
    ``agent_guide(format=..., lang="pl")`` byte for byte.

    Parameters
    ----------
    format : {"agents", "llms"}, optional
        Guide to generate: ``AGENTS.md`` (default) or ``llms.txt``.
    lang : {"pl", "en"}, optional
        Language of the guide and of the catalog texts in it; identifiers,
        codes and keys are the same in both.
    path : str, os.PathLike or None, optional
        Target file in an existing directory outside every IMGW store,
        replaced atomically through a hidden ``.part`` file. ``None``
        (default) returns the lines instead, byte-identical to the file.

    Returns
    -------
    Iterator of str or pathlib.Path
        Lines of UTF-8 markdown, each ending with a newline, without ``path``; the
        absolute path of the written file with ``path``.

    Raises
    ------
    IMGWValidationError
        If ``format`` or ``lang`` is not allowed, or ``path`` is a directory,
        lies in a missing directory or inside an IMGW store
        (``details.option`` names the option).
    """
    options = validate_command(
        "commands guide", options={"format": format, "lang": lang, "path": path}
    )
    guide = cast(GuideFormat, options["format"])
    language = cast(Lang, options["lang"])
    target = None if path is None else _target(cast(Path, options["path"]))
    lines = _render(_template(guide, language), _blocks(language))
    if target is None:
        return iter(lines)
    written = _Lines((), lines, total=None, label="", on_progress=None, cancel=None)
    return cast(Path, _deliver(written, target=target, cancel=None, done=""))


def _instructions(
    *,
    lang: Lang,
    mode: McpMode,
    workdir: PathArg | None,
    root: PathArg | None,
) -> str:
    """
    Return the ``instructions`` of the MCP server: the rules and the mode lines.

    Parameters
    ----------
    lang : {"pl", "en"}
        Language of the server.
    mode : {"read", "write", "http"}
        Server mode (spec 2026-10-19 §6.3).
    workdir : str, os.PathLike or None
        Working directory of a stdio server (base of relative paths); not
        shown in the ``http`` mode, which never names server directories.
    root : str, os.PathLike or None
        Default store (``IMGW_STORE_ROOT``), or None when not set; the
        ``http`` mode only tells whether the server has a store.

    Returns
    -------
    str
        Markdown text below 2 KiB in UTF-8.
    """
    english = lang == "en"
    title = "Rules of IMGWTools:" if english else "Zasady pracy z IMGWTools:"
    lines = [title, _principles(lang), "", _localized(_MODES[mode], lang)]
    if mode == "http":
        if english:
            lines.append(
                "Store: the server's store; `version` relative to it."
                if root is not None
                else "The server has no store: store commands end with "
                "`store_unavailable`."
            )
        else:
            lines.append(
                "Magazyn: magazyn serwera; `version` względnie do niego."
                if root is not None
                else "Serwer bez magazynu: komendy magazynu kończą się "
                "`store_unavailable`."
            )
    else:
        if workdir is not None:
            label = (
                "Working directory (base of relative paths)"
                if english
                else "Katalog roboczy (podstawa ścieżek względnych)"
            )
            lines.append(f"{label}: `{os.fspath(workdir)}`.")
        if root is not None:
            label = "Default store" if english else "Domyślny magazyn"
            lines.append(f"{label} (`IMGW_STORE_ROOT`): `{os.fspath(root)}`.")
        else:
            lines.append(
                "No default store (`IMGW_STORE_ROOT` unset): give `root`."
                if english
                else "Brak domyślnego magazynu (`IMGW_STORE_ROOT`): podawaj `root`."
            )
    if english:
        lines += [
            f"Lists: `limit` {_PAGE_SIZE} by default, at most `IMGW_API_MAX_LIMIT`; "
            "next pages: `offset`.",
            "Full guide (commands, datasets, error codes, flows): the "
            "`imgw_commands_guide` tool.",
        ]
    else:
        lines += [
            f"Listy: `limit` domyślnie {_PAGE_SIZE}, najwyżej `IMGW_API_MAX_LIMIT`; "
            "kolejne strony: `offset`.",
            "Pełny przewodnik (komendy, zbiory, kody błędów, przepływy): narzędzie "
            "`imgw_commands_guide`.",
        ]
    return "\n".join(lines)
