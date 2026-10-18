"""
Catalog of the 35 data commands and the single dispatcher of public functions.

``data_commands`` describes every operation of IMGWTools (spec §13.3). Each
command calls exactly one public function whose parameters carry the option
names; the CLI, the REST API, the web GUI and projects use `validate_command`,
`format_command`, `check_command`, `run_command` and `command_schema` instead
of their own validation, HTTP requests or option lists. `run_command` and
`check_command` return the ``imgw-result/1`` envelope `CommandResult`.
"""

import importlib
import inspect
import json
import math
import os
import re
import shlex
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

from imgwtools import fetch as _fetch
from imgwtools import stations as _stations
from imgwtools import store as _store
from imgwtools._version import __version__
from imgwtools.core.url_builder import build_api_url, build_pmaxtp_url
from imgwtools.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
    archive_files,
    datasets,
    get_dataset,
    parse_months,
    parse_years,
)
from imgwtools.exceptions import (
    ERROR_CODES,
    IMGWCancelledError,
    IMGWError,
    IMGWValidationError,
)
from imgwtools.store import reader as _reader
from imgwtools.store.types import (
    Cancel,
    CatalogReport,
    CommandOption,
    CommandResult,
    DataCommand,
    DownloadReport,
    Notice,
    NoticeHook,
    Page,
    PlanAction,
    PMaXTPStoreResult,
    ProgressHook,
    ProjectReport,
    SeriesReport,
    StorePlan,
    SyncReport,
)

__all__ = [
    "check_command",
    "command_schema",
    "data_commands",
    "format_command",
    "run_command",
    "validate_command",
]

Options = dict[str, Any]
Hooks = dict[str, Any]
Status = Literal["ok", "partial", "failed", "cancelled"]
OptionType = Literal[
    "str", "int", "float", "bool", "date", "path", "list", "choice", "object"
]
ItemType = Literal["str", "int", "year", "choice"]
Checker = Callable[[Options, Hooks], StorePlan]
Rule = Callable[[Options, bool], None]

PROJECT_FILE = "imgw-project.json"
_STORE_MARKER = "imgw-store.json"
# Default download directory; projects resolve it against the project directory.
_DEFAULT_OUTPUT = Path("data/downloaded")
_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_RANGE = "^[0-9]{1,4}-[0-9]{1,4}$"
_STATION = "^[0-9]{9}$"
_SYNOP_STATION = "^[0-9]{5}$"
_TASK_PATTERN = "^[a-z0-9][a-z0-9_-]{0,63}$"
_TASK_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_PATTERN_TEXT = {
    _STATION: "kod stacji z 9 cyfr",
    _SYNOP_STATION: "kod stacji synoptycznej z 5 cyfr",
    _TASK_PATTERN: "nazwa zadania z 1–64 znaków a-z, 0-9, _ lub -, "
    "zaczynająca się literą lub cyfrą",
}
_INTEGER = re.compile(r"-?[0-9]+")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_KINDS = ("hydro", "meteo")
_YEAR_TYPES = ("hydrological", "calendar")
_ARCHIVE_DATASETS = tuple(
    d.key for d in datasets() if d.first_year is not None and d.server_dir is not None
)
_SERIES_DATASETS = tuple(
    d.key
    for d in datasets()
    if d.in_store and d.time_unit in ("day", "month", "half_year")
)
# Commands a project task may store in the manifest (spec §13.3).
_TASK_COMMANDS = (
    "store info",
    "store scan",
    "store check",
    "store sync",
    "store catalog",
    "series build",
    "series select",
    "series export",
    "pmaxtp check",
    "pmaxtp sync",
    "pmaxtp read",
    "datasets download",
)
# Options of paths relative to the project directory, kept as given.
_PROJECT_PATHS = ("store_dir", "geometry")
_DONE = ("created", "relabeled", "unchanged", "reused")
_EXIT_CODES = {"ok": 0, "partial": 10, "failed": 11, "cancelled": 130}
_GROUPS = {
    "datasets": "Rejestr zbiorów IMGW: lista, pliki i pobieranie",
    "stations": "Wyszukiwanie stacji",
    "current": "Dane bieżące z API IMGW",
    "pmaxtp": "Opady maksymalne PMAXTP",
    "store": "Wersjonowany magazyn",
    "series": "Szeregi stacji",
    "project": "Projekty imgw-project/1",
    "commands": "Opis katalogu komend",
}
_STORE_FUNCTIONS = (
    "check_pmaxtp",
    "sync_pmaxtp",
    "read_pmaxtp",
    "init_store",
    "store_info",
    "iter_store",
    "check_store",
    "sync_store",
    "build_catalog",
    "check_catalog",
    "export_archive",
    "build_series",
    "check_series",
    "select_series",
    "read_series",
    "summarize_series",
    "export_series",
)
_PROJECT_FUNCTIONS = (
    "init_project",
    "add_project_task",
    "remove_project_task",
    "set_project_store",
    "download_project",
    "check_project",
    "get_project_status",
    "verify_project",
)
# Public module of every function the catalog dispatches to (resolved per call).
_MODULES = {
    "datasets": "imgwtools.datasets",
    "archive_files": "imgwtools.datasets",
    "download_archives": "imgwtools.fetch",
    "fetch_hydro_current": "imgwtools.fetch",
    "fetch_meteo_current": "imgwtools.fetch",
    "fetch_synop": "imgwtools.fetch",
    "fetch_warnings": "imgwtools.fetch",
    "fetch_pmaxtp": "imgwtools.fetch",
    "find_stations": "imgwtools.stations",
    "fetch_hydro_states": "imgwtools.stations",
    "build_pmaxtp_url": "imgwtools.urls",
    **dict.fromkeys(_STORE_FUNCTIONS, "imgwtools.store"),
    **dict.fromkeys(_PROJECT_FUNCTIONS, "imgwtools.project"),
    "command_schema": "imgwtools.commands",
}


# --- katalog ---------------------------------------------------------------------------------


def _option(
    name: str,
    type_: OptionType,
    help_: str,
    *,
    required: bool = False,
    choices: Iterable[str] = (),
    default: object = None,
    aliases: tuple[str, ...] = (),
    items: ItemType | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    pattern: str | None = None,
    rest: Literal["param", "server", "local"] = "param",
) -> CommandOption:
    return CommandOption(
        name,
        type_,
        required,
        "--" + name.replace("_", "-"),
        tuple(choices),
        help_,
        default=default,
        aliases=aliases,
        items=items,
        minimum=minimum,
        maximum=maximum,
        pattern=pattern,
        rest=rest,
    )


def _command(
    name: str,
    description: str,
    options: Iterable[CommandOption],
    *,
    function: str,
    result_type: str,
    check: str | None = None,
    result: Literal["object", "list", "stream"] = "object",
    method: Literal["GET", "POST"] | None = None,
    requires: Mapping[str, tuple[str, ...]] | None = None,
    one_of: tuple[tuple[str, ...], ...] = (),
    rules: tuple[str, ...] = (),
) -> tuple[DataCommand, str]:
    listed = (*options, _LIMIT, _OFFSET) if result == "list" else tuple(options)
    command = DataCommand(
        name,
        description,
        listed,
        function=function,
        check=check,
        result=result,
        method=method,
        requires=dict(requires or {}),
        one_of=one_of,
        rules=rules,
    )
    return command, result_type


_ROOT = _option(
    "root",
    "path",
    "Katalog magazynu IMGW (CLI: domyślnie $IMGW_STORE_ROOT)",
    required=True,
    aliases=("-r",),
    rest="server",
)
_PROJECT_DIR = _option(
    "project_dir",
    "path",
    "Katalog projektu z manifestem imgw-project.json",
    required=True,
    rest="local",
)
_STORE_DIR = _option(
    "store_dir",
    "path",
    "Katalog magazynu IMGW projektu; ścieżka względna liczona wobec katalogu projektu",
    required=True,
    rest="local",
)
_ARCHIVE_DATASET = _option(
    "dataset",
    "choice",
    "Zbiór archiwalny: klucz, slug albo alias legacy, np. pl.imgw.hydro_daily "
    "albo hydro/dobowe",
    required=True,
    choices=_ARCHIVE_DATASETS,
    aliases=("-d",),
)
_SERIES_DATASET = _option(
    "dataset",
    "choice",
    "Zbiór szeregów: klucz, slug albo alias legacy, np. pl.imgw.hydro_daily",
    choices=_SERIES_DATASETS,
    aliases=("-d",),
)
_DATASETS = _option(
    "datasets",
    "list",
    "Zbiory magazynu rozdzielone przecinkami: klucz, slug albo alias legacy",
    choices=_SERIES_DATASETS,
    items="choice",
    aliases=("-d",),
)
_FAMILY = _option(
    "kind",
    "choice",
    "Rodzaj: hydro albo meteo; brak = obie rodziny",
    choices=_KINDS,
    aliases=("-k",),
)
_YEARS = _option(
    "years",
    "list",
    "Roczniki: liczby lub zakresy, np. 2023-2025 albo 2020,2022",
    items="year",
    minimum=1,
    maximum=9999,
    aliases=("-y",),
)
_MONTHS = _option(
    "months",
    "list",
    "Miesiące 1–12 rozdzielone przecinkami (domyślnie wszystkie)",
    items="int",
    minimum=1,
    maximum=12,
    aliases=("-m",),
)
_PARAMS = _option(
    "params",
    "list",
    "Parametry półroczne H, Q, T (tylko pl.imgw.hydro_semiannual; domyślnie wszystkie)",
    choices=("H", "Q", "T"),
    items="choice",
)
_OUTPUT = _option(
    "output",
    "path",
    "Katalog pobierania odzwierciedlający ścieżki serwera (domyślnie ./data/downloaded)",
    default="./data/downloaded",
    aliases=("-o",),
    rest="local",
)
_STATION_OPTION = _option(
    "station",
    "str",
    "Kod stacji (9 cyfr)",
    pattern=_STATION,
    aliases=("-s",),
)
_STATIONS = _option(
    "stations",
    "list",
    "Kody stacji (9 cyfr) rozdzielone przecinkami",
    items="str",
    pattern=_STATION,
    aliases=("-s",),
)
_VARIABLES = _option(
    "variables",
    "list",
    "Zmienne zbioru rozdzielone przecinkami, np. H,Q (domyślnie wszystkie)",
    items="str",
)
_YEAR_TYPE = _option(
    "year_type",
    "choice",
    "Rodzaj roku: hydrological (XI–X) albo calendar; domyślnie według series.json",
    choices=_YEAR_TYPES,
)
_START = _option(
    "start", "date", "Pierwszy dzień zakresu rekordów (ISO RRRR-MM-DD, włącznie)"
)
_END = _option(
    "end", "date", "Ostatni dzień zakresu rekordów (ISO RRRR-MM-DD, włącznie)"
)
_LATITUDE = _option(
    "latitude",
    "float",
    "Szerokość geograficzna punktu WGS84 (49,0–55,0)",
    required=True,
    minimum=49.0,
    maximum=55.0,
    aliases=("--lat",),
)
_LONGITUDE = _option(
    "longitude",
    "float",
    "Długość geograficzna punktu WGS84 (14,0–24,5)",
    required=True,
    minimum=14.0,
    maximum=24.5,
    aliases=("--lon",),
)
_METHOD = _option(
    "method",
    "choice",
    "Metoda PMAXTP: POT albo AMP",
    choices=("POT", "AMP"),
    default="POT",
)
_IND_X = _option(
    "ind_x", "int", "Indeks X komórki siatki PMAXTP (razem z --ind-y)", minimum=0
)
_IND_Y = _option(
    "ind_y", "int", "Indeks Y komórki siatki PMAXTP (razem z --ind-x)", minimum=0
)
_SERIES_VERSION = _option(
    "version",
    "path",
    "Wersja szeregu: katalog wersji, series.json albo sidecar; bezwzględna albo "
    "względna do root (zamiast dataset)",
)
_SERIES_ROOT = replace(
    _ROOT,
    required=False,
    help="Katalog magazynu: podstawa względnej wersji albo magazyn bieżącej wersji "
    "zbioru (z dataset)",
)
_PATH = _option(
    "path",
    "path",
    "Plik wyniku poza magazynem, w istniejącym katalogu (domyślnie standardowe wyjście)",
    aliases=("-p",),
    rest="local",
)
_TASKS = _option(
    "tasks",
    "list",
    "Nazwy zadań projektu rozdzielone przecinkami (domyślnie wszystkie)",
    items="str",
    pattern=_TASK_PATTERN,
    rest="local",
)
_TASK_NAME_OPTION = _option(
    "name",
    "str",
    "Nazwa zadania: 1–64 znaki a-z, 0-9, _ lub -, na początku litera lub cyfra",
    required=True,
    pattern=_TASK_PATTERN,
    rest="local",
)
_LIMIT = _option("limit", "int", "Rozmiar strony", minimum=1)
_OFFSET = _option("offset", "int", "Początek strony", minimum=0, default=0)
_CELL_PAIR = {"ind_x": ("ind_y",), "ind_y": ("ind_x",)}
# The conflicting option of version+dataset+root is reported as dataset.
_VERSION_OR_DATASET = (("version",), ("dataset", "root"))
_ARCHIVE_RULES = (
    "roczniki nie wcześniejsze niż pierwszy rocznik zbioru (first_year)",
    "params wyłącznie dla pl.imgw.hydro_semiannual",
)
_SERIES_RULES = (
    "dokładnie jedno z: version albo root+dataset (bieżąca wersja szeregu zbioru)",
    "variables wyłącznie ze zmiennych zbioru",
)

_CATALOG: tuple[tuple[DataCommand, str], ...] = (
    _command(
        "datasets list",
        "Wypisz zbiory IMGW z rejestru: klucze, aliasy legacy, zmienne i pierwszy "
        "rocznik.",
        (replace(_FAMILY, help="Rodzina zbiorów: hydro albo meteo; brak = wszystkie"),),
        function="datasets",
        result="list",
        method="GET",
        result_type="DatasetDescriptor",
    ),
    _command(
        "datasets files",
        "Wypisz pliki archiwów zbioru IMGW dla wybranych roczników (offline, bez "
        "pobierania).",
        (_ARCHIVE_DATASET, replace(_YEARS, required=True), _MONTHS, _PARAMS),
        function="archive_files",
        result="list",
        method="GET",
        result_type="ArchiveFile",
        rules=_ARCHIVE_RULES,
    ),
    _command(
        "datasets download",
        "Pobierz archiwa zbioru IMGW do katalogu odzwierciedlającego ścieżki serwera.",
        (_ARCHIVE_DATASET, replace(_YEARS, required=True), _MONTHS, _PARAMS, _OUTPUT),
        function="download_archives",
        check="check_command",
        result_type="DownloadReport",
        rules=_ARCHIVE_RULES,
    ),
    _command(
        "stations find",
        "Znajdź stacje IMGW po nazwie, rzece albo prefiksie kodu.",
        (
            replace(_FAMILY, help="Rodzaj stacji; brak = obie rodziny"),
            _option(
                "query",
                "str",
                "Fragment nazwy lub rzeki albo prefiks kodu",
                aliases=("-q",),
            ),
            _option(
                "source",
                "choice",
                "live: listy IMGW na żywo; store: zapisany magazyn",
                choices=("live", "store"),
                default="live",
            ),
            replace(
                _ROOT,
                required=False,
                help="Katalog magazynu (wymagany przy source=store)",
            ),
        ),
        function="find_stations",
        check="check_command",
        result="list",
        method="GET",
        result_type="StationListEntry",
        rules=("root jest wymagany przy source=store i niedozwolony przy source=live",),
    ),
    _command(
        "current hydro",
        "Pobierz bieżące dane hydrologiczne z API IMGW.",
        (
            replace(
                _STATION_OPTION, help="Kod stacji (9 cyfr); brak = wszystkie stacje"
            ),
        ),
        function="fetch_hydro_current",
        check="check_command",
        result="list",
        method="GET",
        result_type="HydroCurrentData",
    ),
    _command(
        "current meteo",
        "Pobierz bieżące dane meteorologiczne z API IMGW.",
        (
            replace(
                _STATION_OPTION, help="Kod stacji (9 cyfr); brak = wszystkie stacje"
            ),
        ),
        function="fetch_meteo_current",
        check="check_command",
        result="list",
        method="GET",
        result_type="MeteoCurrentData",
    ),
    _command(
        "current synop",
        "Pobierz bieżące dane synoptyczne z API IMGW.",
        (
            replace(
                _STATION_OPTION,
                help="Kod stacji synoptycznej (5 cyfr); brak = wszystkie stacje",
                pattern=_SYNOP_STATION,
            ),
            _option(
                "station_name",
                "str",
                "Fragment nazwy stacji synoptycznej (bez wielkości liter)",
            ),
        ),
        function="fetch_synop",
        check="check_command",
        result="list",
        method="GET",
        result_type="SynopData",
    ),
    _command(
        "current warnings",
        "Pobierz bieżące ostrzeżenia hydrologiczne i meteorologiczne IMGW.",
        (replace(_FAMILY, help="Rodzaj ostrzeżeń: hydro albo meteo; brak = oba"),),
        function="fetch_warnings",
        check="check_command",
        result="list",
        method="GET",
        result_type="WarningData",
    ),
    _command(
        "current hydro-states",
        "Pobierz stany wód stacji hydrologicznych ze współrzędnymi (mapa "
        "hydro.imgw.pl).",
        (_option("main_only", "bool", "Tylko stacje główne", default=False),),
        function="fetch_hydro_states",
        check="check_command",
        result="list",
        method="GET",
        result_type="HydroState",
    ),
    _command(
        "pmaxtp fetch",
        "Pobierz opady maksymalne PMAXTP dla punktu (na żywo, bez zapisu).",
        (_LATITUDE, _LONGITUDE, _METHOD),
        function="fetch_pmaxtp",
        check="check_command",
        method="GET",
        result_type="PMaXTPResult",
    ),
    _command(
        "pmaxtp url",
        "Zbuduj adres URL API PMAXTP dla punktu (offline, bez pobierania).",
        (_LATITUDE, _LONGITUDE, _METHOD),
        function="build_pmaxtp_url",
        method="GET",
        result_type="str",
    ),
    _command(
        "pmaxtp check",
        "Sprawdź komórkę PMAXTP w magazynie bez pobierania danych.",
        (_ROOT, _LATITUDE, _LONGITUDE, _METHOD, _IND_X, _IND_Y),
        function="check_pmaxtp",
        method="GET",
        requires=_CELL_PAIR,
        result_type="StorePlan",
    ),
    _command(
        "pmaxtp sync",
        "Pobierz komórkę PMAXTP dla punktu i zapisz ją jako wersję w magazynie.",
        (_ROOT, _LATITUDE, _LONGITUDE, _METHOD, _IND_X, _IND_Y),
        function="sync_pmaxtp",
        check="check_pmaxtp",
        method="POST",
        requires=_CELL_PAIR,
        result_type="PMaXTPStoreResult",
    ),
    _command(
        "pmaxtp read",
        "Odczytaj zapisaną komórkę PMAXTP z magazynu (offline).",
        (
            _ROOT,
            replace(_IND_X, required=True, help="Indeks X komórki siatki PMAXTP"),
            replace(_IND_Y, required=True, help="Indeks Y komórki siatki PMAXTP"),
            _METHOD,
            _option(
                "version",
                "path",
                "Wersja komórki: katalog wersji albo cell.json; bezwzględna albo "
                "względna do root (domyślnie bieżąca)",
            ),
        ),
        function="read_pmaxtp",
        method="GET",
        result_type="PMaXTPResult",
    ),
    _command(
        "store init",
        "Utwórz pusty magazyn IMGW (znacznik imgw-store.json) we wskazanym katalogu.",
        (_ROOT,),
        function="init_store",
        check="check_command",
        result_type="StoreHandle",
    ),
    _command(
        "store info",
        "Pokaż stan magazynu IMGW i obsługiwane kontrakty (offline, bez zapisu).",
        (_ROOT,),
        function="store_info",
        method="GET",
        result_type="StoreInfo",
    ),
    _command(
        "store scan",
        "Wypisz wersje i problemy magazynu IMGW (offline, bez zapisu).",
        (
            _ROOT,
            _option(
                "kind",
                "choice",
                "Rodzaj wpisów: archive, series, catalog, pmaxtp albo problem; "
                "brak = wszystkie",
                choices=("archive", "series", "catalog", "pmaxtp", "problem"),
                aliases=("-k",),
            ),
        ),
        function="iter_store",
        result="list",
        method="GET",
        result_type="StoreEntry",
    ),
    _command(
        "store check",
        "Sprawdź aktualność archiwów IMGW (listing i HEAD, bez pobierania danych).",
        (
            _ROOT,
            replace(_DATASETS, required=True),
            replace(_YEARS, required=True),
            _MONTHS,
            _option(
                "plan",
                "path",
                "Plik planu imgw-plan/1 do zapisania poza magazynem",
                rest="local",
            ),
        ),
        function="check_store",
        method="GET",
        result_type="StorePlan",
        rules=(
            "roczniki nie wcześniejsze niż pierwszy rocznik każdego zbioru",
            "plan zapisywany wyłącznie poza magazynem, w istniejącym katalogu",
        ),
    ),
    _command(
        "store sync",
        "Pobierz nowe lub brakujące archiwa IMGW do magazynu według planu albo "
        "wyboru zbiorów.",
        (
            _ROOT,
            _option(
                "plan",
                "path",
                "Plik planu imgw-plan/1 z komendy store check (zamiast datasets, "
                "years i months)",
            ),
            _DATASETS,
            _YEARS,
            _MONTHS,
            _option(
                "series",
                "bool",
                "Buduj szeregi zbiorów po synchronizacji (--no-series wyłącza)",
                default=True,
            ),
        ),
        function="sync_store",
        check="check_store",
        method="POST",
        one_of=(("plan",), ("datasets", "years")),
        result_type="SyncReport",
        rules=(
            "plan wyklucza datasets, years i months",
            "roczniki nie wcześniejsze niż pierwszy rocznik każdego zbioru",
        ),
    ),
    _command(
        "store catalog",
        "Zbuduj wersjonowany katalog stacji stations.geojson.",
        (
            _ROOT,
            _option(
                "user_locations",
                "path",
                "Plik CSV UTF-8 użytkownika z kolumnami "
                "station_code,latitude,longitude[,source]",
            ),
        ),
        function="build_catalog",
        check="check_catalog",
        method="POST",
        result_type="CatalogReport",
    ),
    _command(
        "store export",
        "Wyeksportuj rekordy jednej wersji archiwum z magazynu jako CSV albo JSONL "
        "(offline, weryfikacja SHA-256).",
        (
            _option(
                "version",
                "path",
                "Wersja archiwum: katalog wersji, plik archiwum albo sidecar; "
                "bezwzględna albo względna do root",
                required=True,
            ),
            replace(_ROOT, required=False, help="Katalog magazynu: podstawa wersji"),
            _option(
                "format",
                "choice",
                "Format wyniku: csv albo jsonl",
                choices=("csv", "jsonl"),
                default="csv",
                aliases=("-f",),
            ),
            _PATH,
        ),
        function="export_archive",
        check="check_command",
        result="stream",
        method="GET",
        result_type="str",
        rules=("path wewnątrz magazynu jest niedozwolona",),
    ),
    _command(
        "series build",
        "Zbuduj szereg Parquet zbioru z bieżących wersji archiwów magazynu.",
        (_ROOT, replace(_SERIES_DATASET, required=True)),
        function="build_series",
        check="check_series",
        method="POST",
        result_type="SeriesReport",
    ),
    _command(
        "series select",
        "Wybierz stacje, zmienne i lata z bieżącego szeregu (bez zapisu; wejście "
        "projektu).",
        (
            _ROOT,
            replace(_SERIES_DATASET, required=True),
            replace(_STATIONS, required=True),
            _VARIABLES,
            replace(
                _YEARS,
                help="Roczniki: liczby lub zakresy (domyślnie wszystkie lata szeregu)",
            ),
            _YEAR_TYPE,
        ),
        function="select_series",
        method="GET",
        result_type="SeriesSelection",
        rules=(
            "variables wyłącznie ze zmiennych zbioru",
            "szereg półroczny wyłącznie z year_type=hydrological",
            "stacje i roczniki wyłącznie z bieżącego szeregu",
        ),
    ),
    _command(
        "series read",
        "Odczytaj wartości i flagi szeregu jednej stacji z magazynu.",
        (
            _SERIES_VERSION,
            _SERIES_ROOT,
            _SERIES_DATASET,
            replace(_STATION_OPTION, required=True),
            _VARIABLES,
            _START,
            _END,
        ),
        function="read_series",
        result="list",
        method="GET",
        one_of=_VERSION_OR_DATASET,
        result_type="NormalizedRecord",
        rules=(*_SERIES_RULES, "start nie później niż end"),
    ),
    _command(
        "series summary",
        "Pokaż pokrycie stacji i zmiennych szeregu ze spisu series.json (bez pyarrow).",
        (
            _SERIES_VERSION,
            _SERIES_ROOT,
            _SERIES_DATASET,
            replace(
                _STATIONS,
                help="Kody stacji (9 cyfr) rozdzielone przecinkami (domyślnie wszystkie)",
            ),
            _VARIABLES,
        ),
        function="summarize_series",
        result="list",
        method="GET",
        one_of=_VERSION_OR_DATASET,
        result_type="StationCoverage",
        rules=_SERIES_RULES,
    ),
    _command(
        "series export",
        "Wyeksportuj szereg jednej stacji jako CSV z atrybucją IMGW-PIB.",
        (
            _SERIES_VERSION,
            _SERIES_ROOT,
            _SERIES_DATASET,
            replace(_STATION_OPTION, required=True),
            _VARIABLES,
            _START,
            _END,
            _YEAR_TYPE,
            _option(
                "format",
                "choice",
                "Format eksportu (tylko csv)",
                choices=("csv",),
                default="csv",
                aliases=("-f",),
            ),
            _PATH,
        ),
        function="export_series",
        check="check_command",
        result="stream",
        method="GET",
        one_of=_VERSION_OR_DATASET,
        result_type="str",
        rules=(
            *_SERIES_RULES,
            "start nie później niż end",
            "szereg półroczny wyłącznie z year_type=hydrological",
            "path wewnątrz magazynu jest niedozwolona",
        ),
    ),
    _command(
        "project init",
        "Utwórz manifest projektu imgw-project.json wskazujący magazyn.",
        (_PROJECT_DIR, _STORE_DIR),
        function="init_project",
        check="check_command",
        result_type="Project",
    ),
    _command(
        "project add",
        "Dodaj zadanie do manifestu projektu.",
        (
            _PROJECT_DIR,
            _TASK_NAME_OPTION,
            _option(
                "command",
                "choice",
                "Komenda zadania z katalogu, np. series select",
                required=True,
                choices=_TASK_COMMANDS,
                rest="local",
            ),
            _option(
                "options",
                "object",
                "Opcje komendy zadania jako obiekt JSON (bez root: magazyn wynika z "
                "projektu)",
                required=True,
                rest="local",
            ),
            _option(
                "geometry",
                "path",
                "Plik GeoJSON obszaru wyboru stacji w katalogu projektu (tylko "
                "series select)",
                rest="local",
            ),
        ),
        function="add_project_task",
        check="check_command",
        result_type="Project",
        rules=(
            "geometry wyłącznie dla zadań series select",
            "zadanie series select wymaga jawnej opcji years",
        ),
    ),
    _command(
        "project remove",
        "Usuń zadanie z manifestu projektu.",
        (
            _PROJECT_DIR,
            replace(_TASK_NAME_OPTION, help="Nazwa usuwanego zadania"),
        ),
        function="remove_project_task",
        check="check_command",
        result_type="Project",
    ),
    _command(
        "project set-store",
        "Wskaż nowy katalog magazynu projektu po weryfikacji przypiętych plików.",
        (_PROJECT_DIR, replace(_STORE_DIR, help="Nowy katalog magazynu IMGW projektu")),
        function="set_project_store",
        check="check_command",
        result_type="Project",
    ),
    _command(
        "project download",
        "Pobierz i przypnij dane zadań projektu.",
        (
            _PROJECT_DIR,
            _TASKS,
            _option(
                "plan",
                "path",
                "Plik planu imgw-plan/1 z komendy project check",
                rest="local",
            ),
            _option(
                "update",
                "choice",
                "Tryb: pinned (odtwórz przypięte wersje) albo upgrade (zmień piny)",
                choices=("pinned", "upgrade"),
                default="pinned",
                rest="local",
            ),
        ),
        function="download_project",
        check="check_project",
        result_type="ProjectReport",
    ),
    _command(
        "project check",
        "Sprawdź aktualność danych zadań projektu bez zapisu do magazynu.",
        (
            _PROJECT_DIR,
            _TASKS,
            _option(
                "plan",
                "path",
                "Plik planu imgw-plan/1 do zapisania poza magazynem",
                rest="local",
            ),
        ),
        function="check_project",
        result_type="StorePlan",
    ),
    _command(
        "project status",
        "Pokaż stan przypiętych plików zadań projektu (offline).",
        (_PROJECT_DIR, _TASKS),
        function="get_project_status",
        result_type="ProjectReport",
    ),
    _command(
        "project verify",
        "Zweryfikuj sumy SHA-256 przypiętych plików projektu (offline).",
        (_PROJECT_DIR, _TASKS),
        function="verify_project",
        result_type="ProjectReport",
    ),
)
_CATALOG += (
    _command(
        "commands schema",
        "Pokaż schemat JSON opcji komendy albo cały katalog komend imgw-commands/1.",
        (
            _option(
                "command",
                "choice",
                "Nazwa komendy katalogu; brak = cały katalog imgw-commands/1",
                choices=(*(command.name for command, _ in _CATALOG), "commands schema"),
            ),
        ),
        function="command_schema",
        method="GET",
        result_type="dict",
    ),
)
_COMMANDS = tuple(command for command, _ in _CATALOG)
_BY_NAME = {command.name: command for command in _COMMANDS}
_RESULT_TYPES = {command.name: result_type for command, result_type in _CATALOG}


def data_commands() -> tuple[DataCommand, ...]:
    """
    Return the catalog of all 35 data commands.

    Returns
    -------
    tuple of DataCommand
        Commands in catalog order (groups ``datasets``, ``stations``,
        ``current``, ``pmaxtp``, ``store``, ``series``, ``project``,
        ``commands``) with their options, the public function they call,
        the check twin, the result shape, the REST method and the
        validation rules; texts for humans are in Polish.
    """
    return _COMMANDS


# --- walidacja -------------------------------------------------------------------------------


def _shown(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _fail(
    message: str, *, option: str, value: object = None, **details: object
) -> NoReturn:
    payload: dict[str, object] = {"option": option}
    if value is not None:
        payload["value"] = _shown(value)
    payload.update(details)
    raise IMGWValidationError(message, details=payload)


def _spec(command: object) -> DataCommand:
    spec = _BY_NAME.get(command) if isinstance(command, str) else None
    if spec is None:
        _fail(
            f"Nieznana komenda {command!r}; dostępne: {', '.join(_BY_NAME)}",
            option="command",
            value=command,
            allowed=list(_BY_NAME),
        )
    return spec


def _boolean(option: CommandOption, value: object) -> bool | None:
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        value = value.strip().lower() == "true"
    if not isinstance(value, bool):
        _fail(
            f"Opcja {option.name} musi mieć wartość logiczną true albo false: {value!r}",
            option=option.name,
            value=value,
        )
    # Wartość domyślna nie jest podawana jawnie: CLI wyraża ją brakiem flagi.
    return None if value == option.default else value


def _bounds(option: CommandOption, number: int) -> int:
    if option.minimum is not None and number < option.minimum:
        _fail(
            f"Opcja {option.name} musi wynosić co najmniej {option.minimum:g}: {number}",
            option=option.name,
            value=number,
            minimum=option.minimum,
        )
    if option.maximum is not None and number > option.maximum:
        _fail(
            f"Opcja {option.name} musi wynosić co najwyżej {option.maximum:g}: {number}",
            option=option.name,
            value=number,
            maximum=option.maximum,
        )
    return number


def _integer(option: CommandOption, value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return _bounds(option, value)
    if isinstance(value, str) and _INTEGER.fullmatch(text := value.strip()):
        return _bounds(option, int(text))
    _fail(
        f"Opcja {option.name} musi być liczbą całkowitą: {value!r}",
        option=option.name,
        value=value,
    )


def _number(option: CommandOption, value: object) -> float:
    # Granice współrzędnych sprawdza walidator biblioteki (reguła komendy), nie typ.
    number = math.nan
    if isinstance(value, int | float | str) and not isinstance(value, bool):
        with suppress(ValueError):
            number = float(value)
    if not math.isfinite(number):
        _fail(
            f"Opcja {option.name} musi być skończoną liczbą: {value!r}",
            option=option.name,
            value=value,
        )
    return number


def _text(option: CommandOption, value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        _fail(
            f"Opcja {option.name} wymaga niepustego tekstu: {value!r}",
            option=option.name,
            value=value,
        )
    if option.pattern is not None and not re.search(option.pattern, text):
        expected = _PATTERN_TEXT.get(option.pattern, f"wzorzec {option.pattern}")
        _fail(
            f"Opcja {option.name}: oczekiwano {expected}: {text!r}",
            option=option.name,
            value=text,
            pattern=option.pattern,
        )
    return text


def _date(option: CommandOption, value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and _ISO_DATE.fullmatch(text := value.strip()):
        with suppress(ValueError):
            return date.fromisoformat(text)
    _fail(
        f"Opcja {option.name} wymaga daty ISO RRRR-MM-DD: {value!r}",
        option=option.name,
        value=value,
    )


def _path(option: CommandOption, value: object) -> Path:
    text = os.fspath(value) if isinstance(value, str | os.PathLike) else None
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        _fail(
            f"Opcja {option.name} wymaga ścieżki: {value!r}",
            option=option.name,
            value=value,
        )
    return Path(text).expanduser()


def _choice_text(option: CommandOption, text: str) -> str:
    if option.name in ("dataset", "datasets"):
        try:
            text = get_dataset(text).key
        except IMGWValidationError as exc:
            raise IMGWValidationError(
                exc.detail, details={**exc.details, "option": option.name}
            ) from exc
    if text not in option.choices:
        _fail(
            f"Nieprawidłowa wartość {text!r} opcji {option.name}; dozwolone: "
            f"{', '.join(option.choices)}",
            option=option.name,
            value=text,
            allowed=list(option.choices),
        )
    return text


def _choice(option: CommandOption, value: object) -> str:
    if not isinstance(value, str):
        _fail(
            f"Opcja {option.name} wymaga jednej z wartości "
            f"{', '.join(option.choices)}: {value!r}",
            option=option.name,
            value=value,
            allowed=list(option.choices),
        )
    return _choice_text(option, value.strip())


def _texts(option: CommandOption, value: object) -> list[str]:
    """Flatten a comma-separated text or a collection of texts into list items."""
    if isinstance(value, str):
        raw: list[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, bytes | Mapping):
        raw = list(value)
    else:
        _fail(
            f"Opcja {option.name} musi być listą wartości: {value!r}",
            option=option.name,
            value=value,
        )
    texts: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            _fail(
                f"Opcja {option.name} wymaga wartości tekstowych: {item!r}",
                option=option.name,
                value=item,
            )
        texts.extend(part.strip() for part in item.split(","))
    if not texts or "" in texts:
        _fail(
            f"Opcja {option.name} wymaga niepustej listy wartości",
            option=option.name,
            value=value,
        )
    return texts


def _list(option: CommandOption, value: object) -> tuple[object, ...]:
    if option.items == "year":
        return parse_years(cast(YearsArg, value), option=option.name)
    if option.name == "months":
        return parse_months(cast(MonthsArg, value), option=option.name)
    texts = _texts(option, value)
    if option.items == "choice":
        texts = [_choice_text(option, text) for text in texts]
    else:
        texts = [_text(option, text) for text in texts]
    return tuple(dict.fromkeys(texts))


def _object(option: CommandOption, value: object) -> dict[str, object]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            _fail(
                f"Opcja {option.name} musi być obiektem JSON: {exc}", option=option.name
            )
    if not isinstance(value, Mapping):
        _fail(
            f"Opcja {option.name} musi być obiektem JSON: {value!r}",
            option=option.name,
            value=value,
        )
    return dict(value)


_PARSERS: dict[str, Callable[[CommandOption, object], object]] = {
    "bool": _boolean,
    "int": _integer,
    "float": _number,
    "str": _text,
    "date": _date,
    "path": _path,
    "choice": _choice,
    "list": _list,
    "object": _object,
}


def _absolutize(options: Options) -> None:
    """Paths → absolute: ``version`` against ``root``, others against the CWD."""
    for name, value in list(options.items()):
        if isinstance(value, Path) and name not in ("version", *_PROJECT_PATHS):
            options[name] = value.absolute()
    version = options.get("version")
    if isinstance(version, Path) and not version.is_absolute():
        root = options.get("root")
        options["version"] = (
            root / version if isinstance(root, Path) else version.absolute()
        )


def _store_of(path: Path) -> Path | None:
    """Root of the IMGW store containing ``path`` (or being it), if any."""
    resolved = path.resolve()
    return next(
        (
            candidate
            for candidate in (resolved, *resolved.parents)
            if (candidate / _STORE_MARKER).is_file()
        ),
        None,
    )


def _store_root(version: Path) -> Path:
    return _store_of(version) or version.parent


def _outside_store(path: object) -> None:
    if isinstance(path, Path) and (store := _store_of(path)) is not None:
        _fail(
            f"Plik wyniku musi leżeć poza magazynem IMGW ({store}): {path}",
            option="path",
            value=path,
        )


def _half_year(descriptor: DatasetDescriptor, year_type: object) -> None:
    if descriptor.time_unit == "half_year" and year_type == "calendar":
        _fail(
            "Szereg półroczny obsługuje wyłącznie rok hydrologiczny",
            option="year_type",
            value=year_type,
        )


def _rules_archives(options: Options, task: bool) -> None:
    archive_files(
        options["dataset"],
        years=options["years"],
        months=options.get("months"),
        params=options.get("params"),
    )


def _rules_store_check(options: Options, task: bool) -> None:
    for dataset in options["datasets"]:
        archive_files(dataset, years=options["years"], months=options.get("months"))


def _rules_store_sync(options: Options, task: bool) -> None:
    if "plan" not in options:
        _rules_store_check(options, task)
        return
    given = [name for name in ("datasets", "years", "months") if name in options]
    if given:
        _fail(
            "Plan imgw-plan/1 wyklucza opcje datasets, years i months", option=given[0]
        )


def _rules_stations(options: Options, task: bool) -> None:
    _stations._search_kinds(
        options.get("kind"),
        options.get("query"),
        options.get("source", "live"),
        options.get("root"),
    )


def _rules_coordinates(options: Options, task: bool) -> None:
    _fetch._validate_poland_coords(options["latitude"], options["longitude"])


def _rules_series_select(options: Options, task: bool) -> None:
    descriptor = get_dataset(options["dataset"])
    if "variables" in options:
        _reader._variables(options["variables"], descriptor)
    _half_year(descriptor, options.get("year_type"))


def _rules_series(options: Options, task: bool) -> None:
    if "dataset" in options:
        descriptor = get_dataset(options["dataset"])
        if "variables" in options:
            _reader._variables(options["variables"], descriptor)
        _half_year(descriptor, options.get("year_type"))
    start, end = options.get("start"), options.get("end")
    if isinstance(start, date) and isinstance(end, date) and start > end:
        _fail(
            f"Początek zakresu {start} jest późniejszy niż koniec {end}",
            option="end",
            value=end.isoformat(),
        )
    if not task:
        _outside_store(options.get("path"))


def _rules_store_export(options: Options, task: bool) -> None:
    _outside_store(options.get("path"))


def _rules_project_add(options: Options, task: bool) -> None:
    command = options["command"]
    area = "geometry" in options
    if area and command != "series select":
        _fail(
            "Wybór obszarem (geometry) dotyczy wyłącznie zadań series select",
            option="geometry",
        )
    try:
        # Przy wyborze obszarem stacje materializuje add_project_task z katalogu stacji.
        nested = _validate(command, options["options"], task=True, area=area)
    except IMGWValidationError as exc:
        raise IMGWValidationError(
            f"Opcje zadania {command}: {exc.detail}",
            details={**exc.details, "option": "options"},
        ) from exc
    if command == "series select" and "years" not in nested:
        _fail(
            "Zadanie series select w projekcie wymaga jawnej opcji years",
            option="options",
        )
    options["options"] = nested


_RULES: dict[str, Rule] = {
    "datasets files": _rules_archives,
    "datasets download": _rules_archives,
    "stations find": _rules_stations,
    "pmaxtp fetch": _rules_coordinates,
    "pmaxtp url": _rules_coordinates,
    "pmaxtp check": _rules_coordinates,
    "pmaxtp sync": _rules_coordinates,
    "store check": _rules_store_check,
    "store sync": _rules_store_sync,
    "store export": _rules_store_export,
    "series select": _rules_series_select,
    "series read": _rules_series,
    "series summary": _rules_series,
    "series export": _rules_series,
    "project add": _rules_project_add,
}


def _validate(
    command: object, options: object, *, task: bool, area: bool = False
) -> Options:
    """
    Validate ``options`` of ``command``; ``task`` mode validates a project task.

    A task does not give ``root`` (it follows from the project store, so it
    counts as given in ``requires``/``one_of``) and keeps paths relative to
    the project; ``area`` makes ``stations`` optional (area selection).
    """
    spec = _spec(command)
    if not isinstance(options, Mapping):
        _fail(
            f"Opcje komendy {spec.name} muszą być mapowaniem nazwa → wartość",
            option="options",
        )
    known = {option.name: option for option in spec.options}
    for key in options:
        if key not in known:
            _fail(
                f"Nieznana opcja {key!r} komendy {spec.name}; dostępne: "
                f"{', '.join(known)}",
                option=str(key),
                allowed=list(known),
            )
    if task and "root" in options:
        _fail(
            "Zadanie projektu nie podaje root: magazyn wynika ze store_dir projektu",
            option="root",
        )
    result: Options = {}
    for option in spec.options:
        value = options.get(option.name)
        normalized = None if value is None else _PARSERS[option.type](option, value)
        if normalized is not None:
            result[option.name] = normalized
    present = set(result) | ({"root"} if task and "root" in known else set())
    for option in spec.options:
        if (
            option.required
            and option.name not in present
            and not (area and option.name == "stations")
        ):
            _fail(
                f"Brak wymaganej opcji {option.name} ({option.flag}) komendy "
                f"{spec.name}",
                option=option.name,
            )
    for key, needed in spec.requires.items():
        missing = [name for name in needed if name not in present]
        if key in present and missing:
            _fail(
                f"Opcja {key} komendy {spec.name} wymaga także {', '.join(missing)}",
                option=missing[0],
            )
    if spec.one_of:
        matched = [group for group in spec.one_of if present.issuperset(group)]
        if len(matched) != 1:
            groups = " albo ".join("+".join(group) for group in spec.one_of)
            _fail(
                f"Komenda {spec.name} wymaga dokładnie jednej grupy opcji: {groups}",
                option=(matched[1] if matched else spec.one_of[0])[0],
            )
    if not task:
        _absolutize(result)
    rule = _RULES.get(spec.name)
    if rule is not None:
        rule(result, task)
    return result


def validate_command(
    command: str, /, *, options: Mapping[str, object]
) -> dict[str, object]:
    """
    Normalize and validate command options without network access.

    Dataset aliases and slugs become keys, numeric text becomes ``int`` or
    ``float``, ISO text becomes ``date``, every form of ``years`` (``2024``,
    ``"2020-2023"``, ``"2020,2022"``, ``[2020, "2022-2023"]``) and ``months``
    becomes a sorted tuple of numbers, other lists become tuples without
    duplicates, and paths become absolute (``version`` against ``root``;
    ``store_dir`` and ``geometry`` stay relative to the project directory).
    ``None`` values and ``bool`` values equal to their default are omitted,
    so formatting the result with `format_command` and validating it again
    yields identical options. Coordinates are checked by the library
    validator of Poland's bounds.

    Parameters
    ----------
    command : str
        Catalog command name, e.g. ``"series select"``.
    options : Mapping[str, object]
        Option values keyed by option name (``snake_case``); ``limit`` and
        ``offset`` are options of list commands.

    Returns
    -------
    dict of {str : object}
        Normalized options in catalog order.

    Raises
    ------
    IMGWValidationError
        If the command, an option name, an option value or a combination of
        options is unknown or invalid, or a required option is missing;
        ``details.option`` names the offending option.
    """
    return _validate(command, options, task=False)


# --- formatowanie ----------------------------------------------------------------------------


def _option_json(value: object) -> object:
    """JSON value of a nested option; paths keep their given (relative) form."""
    if isinstance(value, Mapping):
        return {str(key): _option_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_option_json(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _argument(value: object) -> str:
    if isinstance(value, tuple):
        return ",".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(
            _option_json(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def format_command(command: str, /, *, options: Mapping[str, object]) -> str:
    """
    Format a command as a stable, ``shlex``-quoted CLI invocation.

    Only the given options are emitted, after normalization, with their
    canonical ``--kebab-case`` flags; ``bool`` options become ``--x`` or
    ``--no-x``. No hidden options are added.

    Parameters
    ----------
    command : str
        Catalog command name.
    options : Mapping[str, object]
        Option values keyed by option name.

    Returns
    -------
    str
        Command line starting with ``imgw``, e.g.
        ``imgw store info --root /data/imgw``.

    Raises
    ------
    IMGWValidationError
        If the command or its options are invalid (see `validate_command`).
    """
    normalized = validate_command(command, options=options)
    spec = _BY_NAME[command]
    words = ["imgw", *spec.name.split()]
    for option in spec.options:
        if option.name not in normalized:
            continue
        value = normalized[option.name]
        if option.type == "bool":
            words.append(option.flag if value else f"--no-{option.flag[2:]}")
        else:
            words += [option.flag, _argument(value)]
    return " ".join(shlex.quote(word) for word in words)


# --- dyspozytor ------------------------------------------------------------------------------


class _Notices:
    """Notice hook collecting distinct notices and forwarding every notice."""

    def __init__(self, hook: NoticeHook | None) -> None:
        self._hook = hook
        self._seen: dict[Notice, None] = {}

    def __call__(self, notice: Notice) -> None:
        self._seen.setdefault(notice)
        if self._hook is not None:
            self._hook(notice)

    def collected(self) -> tuple[Notice, ...]:
        return tuple(self._seen)


def _function(name: str) -> Callable[..., Any]:
    return getattr(importlib.import_module(_MODULES[name]), name)


def _call(name: str, options: Mapping[str, object], hooks: Mapping[str, object]) -> Any:
    """Call public function ``name``, binding options and hooks by parameter name."""
    function = _function(name)
    parameters = inspect.signature(function).parameters
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for key, value in options.items():
        parameter = parameters.get(key)
        if parameter is None:
            raise TypeError(f"Funkcja {name} nie ma parametru {key}")
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[key] = value
    kwargs.update((key, hook) for key, hook in hooks.items() if key in parameters)
    return function(*args, **kwargs)


def _outcome(cancelled: bool, failures: int, successes: int) -> Status:
    if cancelled:
        return "cancelled"
    if not failures:
        return "ok"
    return "partial" if successes else "failed"


def _status(result: object) -> Status:
    """Envelope status of a function result (spec §13.6)."""
    if isinstance(result, StorePlan):
        states = [item.status for item in result.items]
        states += [action.status for action in result.actions]
        failures = states.count("check_failed")
        return _outcome(result.cancelled, failures, len(states) - failures)
    if isinstance(result, SyncReport):
        items = [item.status for item in result.items]
        series = [report.status for report in result.series]
        return _outcome(
            result.cancelled,
            sum(s in ("failed", "stale_plan") for s in items) + series.count("failed"),
            sum(s in _DONE for s in (*items, *series)),
        )
    if isinstance(result, DownloadReport):
        items = [item.status for item in result.items]
        return _outcome(
            result.cancelled, items.count("failed"), items.count("downloaded")
        )
    if isinstance(result, ProjectReport):
        states = [*result.tasks.values(), *(file.status for file in result.files)]
        failures = sum(s in ("failed", "stale_plan") for s in states)
        return _outcome(
            result.cancelled,
            failures,
            len(states) - failures - states.count("cancelled"),
        )
    if isinstance(result, SeriesReport | CatalogReport | PMaXTPStoreResult):
        return _outcome(result.status == "cancelled", int(result.status == "failed"), 0)
    return "ok"


def _page(options: Options) -> tuple[int | None, int]:
    limit = cast(int | None, options.pop("limit", None))
    offset = cast(int, options.pop("offset", 0))
    return limit, offset


def run_command(
    command: str,
    /,
    *,
    options: Mapping[str, object],
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> CommandResult[object]:
    """
    Run a catalog command through exactly one public function.

    Options are validated with `validate_command` and bound to the function
    parameters of the same names; the hooks are passed to functions that
    accept them. List commands are paged here: ``total`` counts the items
    returned by the function, ``items`` is the slice
    ``[offset, offset + limit)`` (to the end without ``limit``). Stream
    commands (``store export``, ``series export`` without ``path``) return
    the iterator of text lines as ``result``; an error while iterating is
    raised from the iterator.

    Parameters
    ----------
    command : str
        Catalog command name.
    options : Mapping[str, object]
        Option values keyed by option name.
    on_progress : ProgressHook or None, optional
        Progress callback forwarded to the public function.
    on_notice : NoticeHook or None, optional
        Notice callback; it receives every notice, while the envelope keeps
        each distinct notice once.
    cancel : Cancel or None, optional
        Cancellation callback forwarded to the public function.

    Returns
    -------
    CommandResult
        Envelope with ``check=False``, the status computed from the result
        (``partial``/``failed`` for failed items of a report, ``cancelled``
        for a cancelled report or an `IMGWCancelledError` with
        ``result=None``), the result (a `Page` for list commands) and the
        distinct notices in order of first occurrence.

    Raises
    ------
    IMGWValidationError
        If the command or its options are invalid (see `validate_command`).
    IMGWError
        Other errors of the dispatched public function are propagated.
    """
    normalized = validate_command(command, options=options)
    spec = _BY_NAME[command]
    limit, offset = _page(normalized)
    notices = _Notices(on_notice)
    hooks = {"on_progress": on_progress, "on_notice": notices, "cancel": cancel}
    try:
        result = _call(spec.function, normalized, hooks)
        if spec.result == "list":
            items = tuple(result)
            end = None if limit is None else offset + limit
            result = Page(items[offset:end], len(items), limit, offset)
    except IMGWCancelledError:
        return CommandResult(spec.name, False, "cancelled", None, notices.collected())
    return CommandResult(spec.name, False, _status(result), result, notices.collected())


# --- sprawdzenia bez zapisu ------------------------------------------------------------------


def _plan(root: Path, actions: Iterable[PlanAction]) -> StorePlan:
    return StorePlan("imgw-plan/1", root, datetime.now(UTC), (), {}, tuple(actions))


def _reading(command: str, detail: str, root: Path | None = None) -> StorePlan:
    return _plan(root or Path.cwd(), [PlanAction(command, "current", detail)])


def _live(command: str, urls: Iterable[str]) -> StorePlan:
    return _plan(
        Path.cwd(),
        [
            PlanAction(
                command,
                "unverifiable",
                f"Odczyt na żywo {url} (bez zapisu; aktualność znana dopiero po pobraniu)",
            )
            for url in urls
        ],
    )


def _twin(name: str, *, without: tuple[str, ...] = ()) -> Checker:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        kept = {key: value for key, value in options.items() if key not in without}
        return _call(name, kept, hooks)

    return check


def _archives(options: Options) -> tuple[ArchiveFile, ...]:
    return archive_files(
        options["dataset"],
        years=options["years"],
        months=options.get("months"),
        params=options.get("params"),
    )


def _check_datasets_list(options: Options, hooks: Hooks) -> StorePlan:
    found = datasets(kind=options.get("kind"))
    return _reading("datasets list", f"Rejestr zbiorów IMGW (offline): {len(found)}")


def _check_datasets_files(options: Options, hooks: Hooks) -> StorePlan:
    files = _archives(options)
    return _reading(
        "datasets files",
        f"Pliki archiwów zbioru {options['dataset']} (offline, bez pobierania): "
        f"{len(files)}",
    )


def _check_download(options: Options, hooks: Hooks) -> StorePlan:
    output = cast(Path, options.get("output", _DEFAULT_OUTPUT.absolute()))
    actions = []
    for file in _archives(options):
        target = output.joinpath(*file.server_path.split("/"))
        exists = target.exists()
        actions.append(
            PlanAction(
                "datasets download",
                "unverifiable" if exists else "missing",
                f"{file.url} → {target}"
                + (" (istniejący plik zostanie zastąpiony)" if exists else ""),
            )
        )
    return _plan(output, actions)


def _check_stations(options: Options, hooks: Hooks) -> StorePlan:
    kinds, _ = _stations._search_kinds(
        options.get("kind"),
        options.get("query"),
        options.get("source", "live"),
        options.get("root"),
    )
    root = options.get("root")
    if not isinstance(root, Path):
        return _live(
            "stations find", (url for _, url in _stations._live_sources(kinds))
        )
    info = _store.store_info(root)
    action = (
        PlanAction("stations find", "current", f"Odczyt list stacji z magazynu {root}")
        if info.supported
        else PlanAction(
            "stations find",
            "check_failed",
            "; ".join(info.problems) or f"Katalog {root} nie jest magazynem IMGW",
        )
    )
    return _plan(root, [action])


def _check_current(endpoint: str) -> Checker:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        url = build_api_url(endpoint, station=options.get("station"))
        return _live(f"current {endpoint}", [url])

    return check


def _check_warnings(options: Options, hooks: Hooks) -> StorePlan:
    sources = _fetch._warning_sources(options.get("kind"))
    return _live("current warnings", (url for _, url in sources))


def _check_hydro_states(options: Options, hooks: Hooks) -> StorePlan:
    url = _stations._map_url(bool(options.get("main_only", False)))
    return _live("current hydro-states", [url])


def _pmaxtp_url(options: Options) -> str:
    return build_pmaxtp_url(
        options["latitude"], options["longitude"], method=options.get("method", "POT")
    )


def _check_pmaxtp_fetch(options: Options, hooks: Hooks) -> StorePlan:
    return _live("pmaxtp fetch", [_pmaxtp_url(options)])


def _check_pmaxtp_url(options: Options, hooks: Hooks) -> StorePlan:
    return _reading("pmaxtp url", f"Adres API PMAXTP (offline): {_pmaxtp_url(options)}")


def _check_pmaxtp_read(options: Options, hooks: Hooks) -> StorePlan:
    root = cast(Path, options["root"])
    cell = f"{options.get('method', 'POT')}/{options['ind_x']}_{options['ind_y']}"
    try:
        if "version" in options:
            version = cast(Path, options["version"])
            found = version if version.exists() else None
        else:
            entry = _store.current_version(root, slot=f"pmaxtp:pl.imgw.pmaxtp:{cell}")
            found = None if entry is None else entry.version
    except IMGWError as exc:
        action = PlanAction("pmaxtp read", "check_failed", str(exc))
    else:
        action = (
            PlanAction("pmaxtp read", "current", f"Odczyt komórki {cell} z {found}")
            if found is not None
            else PlanAction(
                "pmaxtp read", "missing", f"Brak zapisanej komórki PMAXTP {cell}"
            )
        )
    return _plan(root, [action])


def _check_store_init(options: Options, hooks: Hooks) -> StorePlan:
    root = cast(Path, options["root"])
    info = _store.store_info(root)
    if info.supported:
        action = PlanAction(
            "store init", "current", f"Magazyn IMGW już istnieje: {root}"
        )
    elif not root.exists() or (root.is_dir() and not any(root.iterdir())):
        action = PlanAction(
            "store init",
            "missing",
            f"Zostanie utworzony znacznik {_STORE_MARKER} w {root}",
        )
    else:
        action = PlanAction(
            "store init",
            "check_failed",
            "; ".join(info.problems)
            or f"Katalog {root} nie jest pustym magazynem IMGW",
        )
    return _plan(root, [action])


def _check_reading(command: str, key: str) -> Checker:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        root = cast(Path, options[key])
        return _reading(command, f"Operacja tylko do odczytu: {root}", root)

    return check


def _check_store_sync(options: Options, hooks: Hooks) -> StorePlan:
    root = cast(Path, options["root"])
    if "plan" not in options:
        selection = ("root", "datasets", "years", "months")
        return _call(
            "check_store", {k: v for k, v in options.items() if k in selection}, hooks
        )
    plan = StorePlan.from_json(options["plan"])
    if Path(plan.root).absolute() != root:
        _fail(
            f"Plan dotyczy innego magazynu: {plan.root}",
            option="plan",
            value=options["plan"],
        )
    return plan


def _export_action(command: str, what: str, path: object) -> PlanAction:
    if not isinstance(path, Path):
        return PlanAction(command, "current", f"Eksport {what} na standardowe wyjście")
    exists = path.exists()
    return PlanAction(
        command,
        "newer" if exists else "missing",
        f"Eksport {what} do {path}"
        + (" (istniejący plik zostanie zastąpiony)" if exists else ""),
    )


def _check_store_export(options: Options, hooks: Hooks) -> StorePlan:
    version = cast(Path, options["version"])
    try:
        _store.read_archive(version)
    except IMGWError as exc:
        action = PlanAction("store export", "check_failed", str(exc))
    else:
        what = f"rekordów {version} ({options.get('format', 'csv')})"
        action = _export_action("store export", what, options.get("path"))
    return _plan(options.get("root") or _store_root(version), [action])


def _check_select(options: Options, hooks: Hooks) -> StorePlan:
    try:
        selection = _call("select_series", options, {})
    except IMGWError as exc:
        status = "missing" if exc.code == "not_found" else "check_failed"
        action = PlanAction("series select", status, str(exc))
    else:
        action = PlanAction(
            "series select",
            "current",
            f"{selection.version}: stacje {', '.join(selection.stations)}; zmienne "
            f"{', '.join(selection.variables)}; lata "
            f"{', '.join(map(str, selection.years))} ({selection.year_type})",
        )
    return _plan(options["root"], [action])


def _check_series(command: str) -> Checker:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        root = options.get("root")
        try:
            path = _reader._series_path(
                options.get("version"), root=root, dataset=options.get("dataset")
            )
            index = _store.read_series_index(path)
            descriptor = get_dataset(index.dataset)
            codes = (options["station"],) if "station" in options else ()
            _reader._outside(options.get("stations", codes), index)
            _reader._variables(options.get("variables"), descriptor)
            _half_year(descriptor, options.get("year_type"))
        except IMGWError as exc:
            missing = exc.code == "not_found" and command != "series export"
            action = PlanAction(
                command, "missing" if missing else "check_failed", str(exc)
            )
        else:
            action = (
                _export_action(
                    command,
                    f"szeregu stacji {options['station']} z {path}",
                    options.get("path"),
                )
                if command == "series export"
                else PlanAction(command, "current", f"Odczyt szeregu {path} (offline)")
            )
        base = root if isinstance(root, Path) else _store_root(options["version"])
        return _plan(base, [action])

    return check


def _check_manifest(command: str) -> Checker:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        directory = cast(Path, options["project_dir"])
        manifest = directory / PROJECT_FILE
        if command == "project init":
            action = (
                PlanAction(
                    command, "current", f"Manifest projektu już istnieje: {manifest}"
                )
                if manifest.exists()
                else PlanAction(
                    command, "missing", f"Zostanie utworzony manifest {manifest}"
                )
            )
        elif manifest.is_file():
            action = PlanAction(
                command, "newer", f"Zostanie zaktualizowany manifest {manifest}"
            )
        else:
            action = PlanAction(
                command, "check_failed", f"Brak manifestu projektu {manifest}"
            )
        return _plan(directory, [action])

    return check


_CHECKS: dict[str, Checker] = {
    "datasets list": _check_datasets_list,
    "datasets files": _check_datasets_files,
    "datasets download": _check_download,
    "stations find": _check_stations,
    "current hydro": _check_current("hydro"),
    "current meteo": _check_current("meteo"),
    "current synop": _check_current("synop"),
    "current warnings": _check_warnings,
    "current hydro-states": _check_hydro_states,
    "pmaxtp fetch": _check_pmaxtp_fetch,
    "pmaxtp url": _check_pmaxtp_url,
    "pmaxtp check": _twin("check_pmaxtp"),
    "pmaxtp sync": _twin("check_pmaxtp"),
    "pmaxtp read": _check_pmaxtp_read,
    "store init": _check_store_init,
    "store info": _check_reading("store info", "root"),
    "store scan": _check_reading("store scan", "root"),
    "store check": _twin("check_store", without=("plan",)),
    "store sync": _check_store_sync,
    "store catalog": _twin("check_catalog"),
    "store export": _check_store_export,
    "series build": _twin("check_series"),
    "series select": _check_select,
    "series read": _check_series("series read"),
    "series summary": _check_series("series summary"),
    "series export": _check_series("series export"),
    "project init": _check_manifest("project init"),
    "project add": _check_manifest("project add"),
    "project remove": _check_manifest("project remove"),
    "project set-store": _check_manifest("project set-store"),
    "project download": _twin("check_project", without=("plan", "update")),
    "project check": _twin("check_project", without=("plan",)),
    "project status": _check_reading("project status", "project_dir"),
    "project verify": _check_reading("project verify", "project_dir"),
    "commands schema": lambda options, hooks: _reading(
        "commands schema", "Opis katalogu komend imgw-commands/1 (offline)"
    ),
}


def check_command(
    command: str,
    /,
    *,
    options: Mapping[str, object],
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> CommandResult[StorePlan]:
    """
    Plan a command without writing anything or downloading content.

    Commands with a check twin use it (``store sync`` → `check_store`,
    ``store catalog`` → `check_catalog`, ``series build`` → `check_series`,
    ``pmaxtp sync`` → `check_pmaxtp`, ``project download`` →
    `check_project`); commands that are checks themselves run without
    writing their plan file. Every other command gets a general plan of
    `PlanAction` items: validation, URLs and expected paths, without any
    request (read-only commands are reported ``current``, live reads
    ``unverifiable``).

    Parameters
    ----------
    command : str
        Catalog command name.
    options : Mapping[str, object]
        Option values, identical to those accepted by `run_command`
        (``limit`` and ``offset`` are ignored).
    on_progress : ProgressHook or None, optional
        Progress callback forwarded to the check twin.
    on_notice : NoticeHook or None, optional
        Notice callback; every notice is forwarded, the envelope keeps each
        distinct notice once.
    cancel : Cancel or None, optional
        Cancellation callback forwarded to the check twin.

    Returns
    -------
    CommandResult
        Envelope with ``check=True`` and the ``imgw-plan/1`` plan as
        ``result``; ``status`` is ``failed`` or ``partial`` when plan items
        or actions are ``check_failed`` and ``cancelled`` for a cancelled
        plan.

    Raises
    ------
    IMGWValidationError
        If the command or its options are invalid (see `validate_command`).
    IMGWError
        Other errors of the check twin are propagated.
    """
    normalized = validate_command(command, options=options)
    spec = _BY_NAME[command]
    _page(normalized)
    notices = _Notices(on_notice)
    hooks = {"on_progress": on_progress, "on_notice": notices, "cancel": cancel}
    try:
        plan = _CHECKS[spec.name](normalized, hooks)
    except IMGWCancelledError:
        return CommandResult(spec.name, True, "cancelled", None, notices.collected())
    return CommandResult(spec.name, True, _status(plan), plan, notices.collected())


# --- schemat JSON ----------------------------------------------------------------------------


def _value_schema(
    type_: str, option: CommandOption, *, item: bool = False
) -> dict[str, object]:
    if type_ in ("str", "int", "float"):
        schema: dict[str, object] = {
            "type": {"str": "string", "int": "integer", "float": "number"}[type_]
        }
        if type_ == "str":
            schema["minLength"] = 1
        for key in ("minimum", "maximum", "pattern"):
            if (value := getattr(option, key)) is not None:
                schema[key] = value
        return schema
    if type_ == "year":
        return {
            "anyOf": [
                _value_schema("int", option, item=True),
                {"type": "string", "pattern": _RANGE},
            ]
        }
    if type_ == "choice":
        return {"enum": list(option.choices)}
    if type_ == "list" and not item:
        items = _value_schema(option.items or "str", option, item=True)
        return {"type": "array", "items": items, "minItems": 1}
    simple: dict[str, dict[str, object]] = {
        "bool": {"type": "boolean"},
        "date": {"type": "string", "format": "date"},
        "path": {"type": "string", "x-imgw-type": "path"},
        "object": {"type": "object"},
    }
    return simple[type_]


def _property(option: CommandOption) -> dict[str, object]:
    schema = _value_schema(option.type, option)
    if option.default is not None:
        schema["default"] = option.default
    schema["description"] = option.help
    return schema


def _flags(option: CommandOption) -> list[str]:
    negative = [f"--no-{option.flag[2:]}"] if option.default is True else []
    return [option.flag, *option.aliases, *negative]


def _schema(spec: DataCommand) -> dict[str, object]:
    group, name = spec.name.split(" ", 1)
    schema: dict[str, object] = {
        "$schema": _DIALECT,
        "title": spec.name,
        "description": spec.description,
        "type": "object",
        "properties": {option.name: _property(option) for option in spec.options},
    }
    required = [option.name for option in spec.options if option.required]
    if required:
        schema["required"] = required
    if spec.requires:
        schema["dependentRequired"] = {
            key: list(names) for key, names in spec.requires.items()
        }
    if spec.one_of:
        schema["oneOf"] = [{"required": list(names)} for names in spec.one_of]
    schema["additionalProperties"] = False
    schema["x-imgw"] = {
        "command": spec.name,
        "group": group,
        "function": spec.function,
        "check": spec.check,
        "result": spec.result,
        "result_type": _RESULT_TYPES[spec.name],
        "cli": {
            "command": f"imgw {spec.name}",
            "flags": {option.name: _flags(option) for option in spec.options},
        },
        "rest": None
        if spec.method is None
        else {
            "method": spec.method,
            "path": f"/api/v1/{group}/{name}",
            "server_options": [o.name for o in spec.options if o.rest == "server"],
            "local_options": [o.name for o in spec.options if o.rest == "local"],
        },
        "rules": list(spec.rules),
    }
    return schema


def command_schema(command: str | None = None, /) -> dict[str, object]:
    """
    Describe the options of one command, or the whole catalog, as JSON Schema.

    Option types map to JSON Schema 2020-12: ``str`` → ``string``
    (``minLength`` 1), ``int`` → ``integer``, ``float`` → ``number``,
    ``bool`` → ``boolean``, ``date`` → ``string`` with ``format: date``,
    ``path`` → ``string`` with ``x-imgw-type: path``, ``choice`` → ``enum``
    (dataset enumerations list keys only), ``list`` → ``array`` of items
    (years: ``anyOf`` a number and the ``a-b`` range pattern),
    ``object`` → ``object``; ``help`` → ``description``, ``default``,
    ``minimum``, ``maximum`` and ``pattern`` unchanged, ``requires`` →
    ``dependentRequired``, ``one_of`` → ``oneOf`` of ``required`` groups and
    other rules → ``x-imgw.rules``. ``x-imgw`` also names the group, the
    function, the check twin, the result shape and type, the CLI flags and
    the REST route.

    Parameters
    ----------
    command : str or None, optional
        Catalog command name; ``None`` returns the whole catalog.

    Returns
    -------
    dict of {str : object}
        JSON Schema of the command options, or the ``imgw-commands/1``
        document with ``version``, ``result_schema``, ``groups``,
        ``commands`` (35 schemas), ``errors`` (the error code registry) and
        ``exit_codes`` of the envelope statuses.

    Raises
    ------
    IMGWValidationError
        If ``command`` is not a catalog command (``details.allowed`` lists
        the names).
    """
    if command is not None:
        return _schema(_spec(command))
    return {
        "schema": "imgw-commands/1",
        "version": __version__,
        "result_schema": "imgw-result/1",
        "groups": dict(_GROUPS),
        "commands": [_schema(spec) for spec in _COMMANDS],
        "errors": [
            {
                "code": spec.code,
                "title": spec.title,
                "exit_code": spec.exit_code,
                "http_status": spec.http_status,
            }
            for spec in ERROR_CODES.values()
        ],
        "exit_codes": dict(_EXIT_CODES),
    }
