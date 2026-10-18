"""Katalog komend danych i jeden dispatcher publicznych API (spec §10).

``data_commands`` opisuje każdą komendę czytającą lub piszącą dane. CLI, REST i
projekt korzystają z ``validate_command``/``format_command``/``check_command``/
``run_command`` zamiast własnej walidacji i własnych żądań HTTP.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import shlex
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, NoReturn

from imgwtools import fetch as _fetch
from imgwtools import store as _store
from imgwtools.core.url_builder import (
    IMGW_PUBLIC_DATA_URL,
    MeteoInterval,
    MeteoSubtype,
    build_meteo_url,
)
from imgwtools.datasets import ArchiveFile, archive_files, datasets, get_dataset
from imgwtools.exceptions import IMGWError, IMGWStoreError, IMGWValidationError
from imgwtools.models import PMaXTPResult
from imgwtools.store.pmaxtp import _validate_point
from imgwtools.store.types import (
    Cancel,
    CatalogReport,
    CommandOption,
    DataCommand,
    Notice,
    NoticeHook,
    PathArg,
    PlanAction,
    PMaXTPStoreResult,
    Progress,
    ProgressHook,
    Project,
    ProjectReport,
    SeriesReport,
    SeriesSelection,
    StoreEntry,
    StoreHandle,
    StoreInfo,
    StorePlan,
    SyncReport,
)

__all__ = [
    "check_command",
    "data_commands",
    "format_command",
    "run_command",
    "validate_command",
]

PROJECT_FILE = "imgw-project.json"
_STORE_MARKER = "imgw-store.json"
_DEFAULT_OUTPUT = Path("./data/downloaded")
_SERIES_DATASETS = tuple(
    d.key for d in datasets() if d.time_unit in ("day", "month", "half_year")
)
_YEAR_TYPES = ("hydrological", "calendar")
_STATION = re.compile(r"[0-9]{9}")
_TASK_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_YEARS = re.compile(r"([0-9]{1,4})(?:-([0-9]{1,4}))?")
_INTEGER = re.compile(r"-?[0-9]+")
_HYDRO_INTERVALS = {
    "dobowe": "pl.imgw.hydro_daily",
    "miesieczne": "pl.imgw.hydro_monthly",
    "polroczne_i_roczne": "pl.imgw.hydro_semiannual",
}
# Komendy, które zadanie projektu może zapisać w manifeście (bez komend samego projektu).
_TASK_COMMANDS = (
    "store info",
    "store scan",
    "store check",
    "store sync",
    "store catalog",
    "series build",
    "series export",
    "series select",
    "pmaxtp check",
    "pmaxtp sync",
    "pmaxtp read",
    "fetch hydro",
    "fetch meteo",
)

Options = dict[str, Any]
Hooks = dict[str, Any]


def _opt(
    name: str,
    type_: Any,
    help_: str,
    *,
    required: bool = False,
    choices: Iterable[str] = (),
) -> CommandOption:
    return CommandOption(
        name, type_, required, "--" + name.replace("_", "-"), tuple(choices), help_
    )


_ROOT = _opt(
    "root",
    "path",
    "Katalog główny magazynu IMGW (jawna ścieżka, absolutyzowana na wejściu)",
    required=True,
)
_PROJECT_DIR = _opt(
    "project_dir",
    "path",
    "Katalog projektu z manifestem imgw-project.json",
    required=True,
)
_TASKS = _opt(
    "tasks",
    "list",
    "Nazwy zadań projektu rozdzielone przecinkami (domyślnie wszystkie)",
)
_METHOD = _opt(
    "method",
    "choice",
    "Metoda PMAXTP: POT albo AMP",
    required=True,
    choices=("POT", "AMP"),
)
_LAT = _opt(
    "lat",
    "str",
    "Szerokość geograficzna punktu (WGS84, stopnie dziesiętne)",
    required=True,
)
_LON = _opt(
    "lon",
    "str",
    "Długość geograficzna punktu (WGS84, stopnie dziesiętne)",
    required=True,
)
_IND_X = _opt("ind_x", "int", "Oczekiwany indeks X komórki siatki (razem z --ind-y)")
_IND_Y = _opt("ind_y", "int", "Oczekiwany indeks Y komórki siatki (razem z --ind-x)")
_YEAR_TYPE = _opt(
    "year_type",
    "choice",
    "Rodzaj roku: hydrological (XI–X) albo calendar; domyślnie wg spisu szeregu",
    choices=_YEAR_TYPES,
)
_SERIES_DATASET = _opt(
    "dataset",
    "choice",
    "Klucz zbioru, np. pl.imgw.hydro_daily",
    required=True,
    choices=_SERIES_DATASETS,
)
_DATASETS = _opt(
    "dataset",
    "list",
    "Klucze zbiorów rozdzielone przecinkami, np. pl.imgw.hydro_daily",
    choices=_SERIES_DATASETS,
)
_STORE_YEARS = _opt(
    "years", "list", "Roczniki: lista lub zakresy, np. 2023-2025 albo 2020,2022"
)
_MONTHS = _opt(
    "months", "list", "Miesiące 1–12 rozdzielone przecinkami (domyślnie wszystkie)"
)
_FETCH_YEAR = _opt(
    "year", "str", "Rok lub zakres lat, np. 2020 albo 2020-2023", required=True
)
_FETCH_MONTH = _opt("month", "int", "Miesiąc 1–12")
_OUTPUT = _opt(
    "output",
    "path",
    "Katalog wyjściowy odzwierciedlający ścieżki serwera (domyślnie ./data/downloaded)",
)

_COMMANDS = (
    DataCommand(
        "store init",
        "Utwórz pusty magazyn IMGW (znacznik imgw-store.json) we wskazanym katalogu.",
        (_ROOT,),
    ),
    DataCommand(
        "store info",
        "Pokaż stan magazynu IMGW i obsługiwane kontrakty (offline, bez zapisu).",
        (_ROOT,),
    ),
    DataCommand(
        "store scan",
        "Wypisz wersje i problemy magazynu IMGW (offline, bez zapisu).",
        (
            _ROOT,
            _opt(
                "kind",
                "choice",
                "Rodzaj wpisów: archive, series, catalog, pmaxtp albo problem",
                choices=("archive", "series", "catalog", "pmaxtp", "problem"),
            ),
        ),
    ),
    DataCommand(
        "store check",
        "Sprawdź aktualność archiwów IMGW (listing i HEAD, bez pobierania danych).",
        (
            _ROOT,
            replace(_DATASETS, required=True),
            replace(_STORE_YEARS, required=True),
            _MONTHS,
            _opt("plan", "path", "Plik planu imgw-plan/1 do zapisania poza magazynem"),
        ),
    ),
    DataCommand(
        "store sync",
        "Pobierz nowe lub brakujące archiwa IMGW do magazynu według planu albo wyboru zbiorów.",
        (
            _ROOT,
            _opt(
                "plan",
                "path",
                "Plik planu imgw-plan/1 z komendy store check (zamiast --dataset/--years)",
            ),
            _DATASETS,
            _STORE_YEARS,
            _MONTHS,
            _opt("no_series", "bool", "Nie buduj szeregów po synchronizacji"),
        ),
    ),
    DataCommand(
        "store catalog",
        "Zbuduj wersjonowany katalog stacji stations.geojson.",
        (
            _ROOT,
            _opt(
                "user_locations",
                "path",
                "Plik CSV UTF-8 użytkownika z kolumnami station_code,lon,lat,source",
            ),
        ),
    ),
    DataCommand(
        "store read",
        "Odczytaj rekordy jednej wersji archiwum z magazynu (offline, weryfikacja SHA-256).",
        (
            _opt(
                "version",
                "path",
                "Wersja archiwum: katalog wersji, plik archiwum albo jego sidecar",
                required=True,
            ),
            _opt(
                "format",
                "choice",
                "Format wyniku: csv albo jsonl (domyślnie csv)",
                choices=("csv", "jsonl"),
            ),
            _opt(
                "path",
                "path",
                "Plik wyniku poza magazynem (domyślnie standardowe wyjście)",
            ),
        ),
    ),
    DataCommand(
        "series build",
        "Zbuduj szereg Parquet zbioru z bieżących wersji archiwów magazynu.",
        (
            _ROOT,
            _SERIES_DATASET,
        ),
    ),
    DataCommand(
        "series export",
        "Wyeksportuj szereg jednej stacji do pliku CSV z atrybucją IMGW-PIB.",
        (
            _opt(
                "version",
                "path",
                "Wersja szeregu: katalog wersji albo plik series.json",
                required=True,
            ),
            _opt("station", "str", "Kod stacji (9 cyfr)", required=True),
            _opt("path", "path", "Docelowy plik CSV (poza magazynem)", required=True),
            _opt(
                "variables",
                "list",
                "Zmienne rozdzielone przecinkami, np. H,Q",
                required=True,
            ),
            _YEAR_TYPE,
            _opt("format", "choice", "Format eksportu (tylko csv)", choices=("csv",)),
        ),
    ),
    DataCommand(
        "series select",
        "Wybierz stacje, zmienne i lata z bieżącego szeregu (bez zapisu; wejście projektu).",
        (
            _ROOT,
            _SERIES_DATASET,
            _opt(
                "stations",
                "list",
                "Kody stacji (9 cyfr) rozdzielone przecinkami",
                required=True,
            ),
            _opt(
                "variables",
                "list",
                "Zmienne rozdzielone przecinkami (domyślnie wszystkie zmienne zbioru)",
            ),
            _opt(
                "years",
                "list",
                "Roczniki: lista lub zakresy, np. 2020-2023 (domyślnie wszystkie w szeregu)",
            ),
            _YEAR_TYPE,
        ),
    ),
    DataCommand(
        "pmaxtp check",
        "Sprawdź komórkę PMAXTP w magazynie bez pobierania danych.",
        (
            _ROOT,
            _METHOD,
            _LAT,
            _LON,
            _IND_X,
            _IND_Y,
        ),
    ),
    DataCommand(
        "pmaxtp sync",
        "Pobierz komórkę PMAXTP dla punktu i zapisz ją jako wersję w magazynie.",
        (
            _ROOT,
            _METHOD,
            _LAT,
            _LON,
            _IND_X,
            _IND_Y,
        ),
    ),
    DataCommand(
        "pmaxtp read",
        "Odczytaj zapisaną komórkę PMAXTP z magazynu (offline).",
        (
            _ROOT,
            _METHOD,
            replace(_IND_X, required=True, help="Indeks X komórki siatki"),
            replace(_IND_Y, required=True, help="Indeks Y komórki siatki"),
            _opt(
                "version",
                "path",
                "Wersja komórki: katalog wersji albo cell.json (domyślnie bieżąca)",
            ),
        ),
    ),
    DataCommand(
        "project init",
        "Utwórz manifest projektu imgw-project.json wskazujący magazyn.",
        (
            _PROJECT_DIR,
            _opt("store_dir", "path", "Katalog magazynu IMGW projektu", required=True),
        ),
    ),
    DataCommand(
        "project add",
        "Dodaj zadanie do manifestu projektu.",
        (
            _PROJECT_DIR,
            _opt(
                "name",
                "str",
                "Nazwa zadania: 1–64 znaki a-z, 0-9, _ lub -, na początku litera lub cyfra",
                required=True,
            ),
            _opt(
                "command",
                "choice",
                "Komenda zadania z katalogu, zwykle series select",
                required=True,
                choices=_TASK_COMMANDS,
            ),
            _opt(
                "options",
                "str",
                "Opcje komendy zadania jako obiekt JSON (bez root: magazyn wynika z projektu)",
                required=True,
            ),
            _opt(
                "geometry",
                "path",
                "Plik zapisanego wyboru obszaru (geometria) dla zadania",
            ),
        ),
    ),
    DataCommand(
        "project remove",
        "Usuń zadanie z manifestu projektu.",
        (
            _PROJECT_DIR,
            _opt("name", "str", "Nazwa usuwanego zadania", required=True),
        ),
    ),
    DataCommand(
        "project set-store",
        "Wskaż nowy katalog magazynu projektu po weryfikacji przypiętych plików.",
        (
            _PROJECT_DIR,
            _opt("store_dir", "path", "Nowy katalog magazynu IMGW", required=True),
        ),
    ),
    DataCommand(
        "project download",
        "Pobierz i przypnij dane zadań projektu.",
        (
            _PROJECT_DIR,
            _TASKS,
            _opt("plan", "path", "Plik planu imgw-plan/1 z komendy project check"),
            _opt(
                "update",
                "choice",
                "Tryb: pinned (odtwórz przypięte wersje) albo upgrade (zmień piny)",
                choices=("pinned", "upgrade"),
            ),
        ),
    ),
    DataCommand(
        "project check",
        "Sprawdź aktualność danych zadań projektu bez zapisu do magazynu.",
        (
            _PROJECT_DIR,
            _TASKS,
            _opt("plan", "path", "Plik planu imgw-plan/1 do zapisania poza magazynem"),
        ),
    ),
    DataCommand(
        "project status",
        "Pokaż stan przypiętych plików zadań projektu (offline).",
        (_PROJECT_DIR, _TASKS),
    ),
    DataCommand(
        "project verify",
        "Zweryfikuj sumy SHA-256 przypiętych plików projektu (offline).",
        (_PROJECT_DIR, _TASKS),
    ),
    DataCommand(
        "fetch hydro",
        "Pobierz archiwa hydrologiczne IMGW do katalogu odzwierciedlającego ścieżki serwera.",
        (
            _opt(
                "interval",
                "choice",
                "Interwał: dobowe, miesieczne albo polroczne_i_roczne (domyślnie polroczne_i_roczne)",
                choices=tuple(_HYDRO_INTERVALS),
            ),
            _FETCH_YEAR,
            _FETCH_MONTH,
            _opt(
                "param",
                "choice",
                "Parametr danych półrocznych: H, Q albo T",
                choices=("H", "Q", "T"),
            ),
            _OUTPUT,
        ),
    ),
    DataCommand(
        "fetch meteo",
        "Pobierz archiwa meteorologiczne IMGW do katalogu odzwierciedlającego ścieżki serwera.",
        (
            _opt(
                "interval",
                "choice",
                "Interwał: dobowe, miesieczne albo terminowe (domyślnie miesieczne)",
                choices=("dobowe", "miesieczne", "terminowe"),
            ),
            _opt(
                "subtype",
                "choice",
                "Podtyp: klimat, opad albo synop (domyślnie synop)",
                choices=("klimat", "opad", "synop"),
            ),
            _FETCH_YEAR,
            _FETCH_MONTH,
            _OUTPUT,
        ),
    ),
)
_BY_NAME = {command.name: command for command in _COMMANDS}


def data_commands() -> tuple[DataCommand, ...]:
    """
    Return the catalog of every command that reads or writes data.

    Returns
    -------
    tuple of DataCommand
        Commands with their options and Polish ``--help`` descriptions, in
        catalog order.
    """
    return _COMMANDS


# --- walidacja -----------------------------------------------------------------------------


def _fail(message: str) -> NoReturn:
    raise IMGWValidationError(message)


def _int(name: str, value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and _INTEGER.fullmatch(value.strip()):
        return int(value)
    return _fail(f"Opcja {name} musi być liczbą całkowitą: {value!r}")


def _year_range(name: str, value: object) -> range:
    if isinstance(value, int) and not isinstance(value, bool):
        start = end = value
    elif isinstance(value, str) and (match := _YEARS.fullmatch(value.strip())):
        start = int(match.group(1))
        end = int(match.group(2) or start)
    else:
        return _fail(f"Nieprawidłowy rok lub zakres lat w opcji {name}: {value!r}")
    if not 1 <= start <= end <= 9999:
        _fail(f"Nieprawidłowy zakres lat w opcji {name}: {value!r}")
    return range(start, end + 1)


def _items(name: str, value: object) -> list[object]:
    if isinstance(value, str):
        items: list[object] = [part.strip() for part in value.split(",")]
    elif isinstance(value, int) and not isinstance(value, bool):
        items = [value]
    elif isinstance(value, Iterable) and not isinstance(value, bytes | Mapping):
        items = list(value)
    else:
        return _fail(f"Opcja {name} musi być listą wartości: {value!r}")
    if not items or any(item == "" or item is None for item in items):
        _fail(f"Opcja {name} wymaga niepustej listy wartości")
    return items


def _list(option: CommandOption, value: object) -> tuple[object, ...]:
    name = option.name
    items = _items(name, value)
    if name == "years":
        return tuple(
            sorted({year for item in items for year in _year_range(name, item)})
        )
    if name == "months":
        months = {_int(name, item) for item in items}
        if any(not 1 <= month <= 12 for month in months):
            _fail("Miesiące muszą należeć do zakresu 1–12")
        return tuple(sorted(months))
    texts: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            _fail(f"Opcja {name} wymaga tekstowych wartości: {item!r}")
        text = item.strip()
        if option.choices and text not in option.choices:
            _fail(
                f"Nieprawidłowa wartość {text!r} opcji {name}; dozwolone: {', '.join(option.choices)}"
            )
        if name == "stations" and not _STATION.fullmatch(text):
            _fail(f"Kod stacji musi mieć dokładnie 9 cyfr: {text!r}")
        if name == "tasks" and not _TASK_NAME.fullmatch(text):
            _fail(f"Nieprawidłowa nazwa zadania projektu: {text!r}")
        texts.append(text)
    return tuple(dict.fromkeys(texts))


def _text(name: str, value: object) -> object:
    if name in ("lat", "lon"):
        try:
            if isinstance(value, bool) or not isinstance(value, int | float | str):
                raise ValueError
            number = float(value)
        except ValueError:
            return _fail(f"Opcja {name} musi być liczbą: {value!r}")
        if not math.isfinite(number):
            _fail(f"Opcja {name} musi być skończoną liczbą: {value!r}")
        return number
    if name == "year":
        if isinstance(value, str) and "," in value:
            _fail(f"Opcja year przyjmuje jeden rok albo zakres: {value!r}")
        years = _year_range(name, value)
        return str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"
    if name == "options":
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError as exc:
                raise IMGWValidationError(
                    f"Opcje zadania muszą być obiektem JSON: {exc}"
                ) from exc
        if not isinstance(value, Mapping):
            _fail("Opcje zadania muszą być obiektem JSON")
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return _fail(f"Opcja {name} wymaga niepustego tekstu: {value!r}")
    if name == "station" and not _STATION.fullmatch(value):
        _fail(f"Kod stacji musi mieć dokładnie 9 cyfr: {value!r}")
    if name == "name" and not _TASK_NAME.fullmatch(value):
        _fail(f"Nieprawidłowa nazwa zadania projektu: {value!r}")
    return value


def _value(option: CommandOption, value: object) -> object | None:
    name = option.name
    if option.type == "bool":
        if not isinstance(value, bool):
            _fail(f"Opcja {name} musi mieć wartość logiczną: {value!r}")
        return value or None
    if option.type == "int":
        number = _int(name, value)
        if name in ("ind_x", "ind_y") and number < 0:
            _fail(f"Indeks komórki {name} musi być nieujemny: {number}")
        if name == "month" and not 1 <= number <= 12:
            _fail(f"Miesiąc musi należeć do zakresu 1–12: {number}")
        return number
    if option.type == "path":
        text = os.fspath(value) if isinstance(value, str | os.PathLike) else None
        if not isinstance(text, str) or not text.strip() or "\0" in text:
            _fail(f"Opcja {name} wymaga ścieżki: {value!r}")
        return Path(text)
    if option.type == "choice":
        if not isinstance(value, str) or value not in option.choices:
            _fail(
                f"Nieprawidłowa wartość {value!r} opcji {name}; dozwolone: {', '.join(option.choices)}"
            )
        return value
    if option.type == "list":
        return _list(option, value)
    return _text(name, value)


def _absolute(path: PathArg) -> Path:
    return Path(os.fspath(path)).expanduser().absolute()


def _inside(child: Path, parent: Path) -> bool:
    child, parent = _absolute(child).resolve(), _absolute(parent).resolve()
    return child == parent or parent in child.parents


def _check_selectors(options: Options) -> None:
    for dataset in options["dataset"]:
        archive_files(dataset, years=options["years"], months=options.get("months"))


def _rules_store_check(options: Options) -> None:
    _check_selectors(options)
    if (
        "plan" in options
        and "root" in options
        and _inside(options["plan"], options["root"])
    ):
        _fail("Plan imgw-plan/1 musi być zapisany poza magazynem")


def _rules_store_sync(options: Options) -> None:
    selectors = [name for name in ("dataset", "years", "months") if name in options]
    if "plan" in options:
        if selectors:
            _fail("Podaj plan albo selektory dataset/years/months, nie oba naraz")
    elif "dataset" not in options or "years" not in options:
        _fail("Bez planu wymagane są opcje dataset i years")
    else:
        _check_selectors(options)


def _rules_store_read(options: Options) -> None:
    if "path" in options and _inside(options["path"], _store_root(options["version"])):
        _fail("Plik wyniku store read musi być zapisany poza magazynem")


def _rules_series_select(options: Options) -> None:
    descriptor = get_dataset(options["dataset"])
    unknown = [
        name
        for name in options.get("variables", ())
        if name not in descriptor.variables
    ]
    if unknown:
        _fail(
            f"Nieznane zmienne {', '.join(unknown)}; dostępne: {', '.join(descriptor.variables)}"
        )
    if descriptor.time_unit == "half_year" and options.get("year_type") == "calendar":
        _fail("Szereg półroczny obsługuje wyłącznie rok hydrologiczny")


def _rules_pmaxtp(options: Options) -> None:
    _validate_point(options["lat"], options["lon"])
    if ("ind_x" in options) != ("ind_y" in options):
        _fail("Podaj oba indeksy komórki ind_x i ind_y albo żaden")


def _rules_project_add(options: Options) -> None:
    command = options["command"]
    if "geometry" in options and command != "series select":
        _fail("Wybór obszarem (geometry) dotyczy wyłącznie zadań series select")
    # Przy wyborze obszarem stacje materializuje add_project_task z bieżącego katalogu stacji.
    task = _validate(command, options["options"], task=True, area="geometry" in options)
    if command == "series select" and "years" not in task:
        _fail("Zadanie series select w projekcie wymaga jawnej opcji years")
    options["options"] = task


def _rules_fetch_hydro(options: Options) -> None:
    if (
        "param" in options
        and options.get("interval", "polroczne_i_roczne") != "polroczne_i_roczne"
    ):
        _fail("Parametr H/Q/T dotyczy tylko interwału polroczne_i_roczne")
    _fetch_jobs("fetch hydro", options)


def _rules_fetch_meteo(options: Options) -> None:
    _fetch_jobs("fetch meteo", options)


_RULES: dict[str, Callable[[Options], None]] = {
    "store check": _rules_store_check,
    "store sync": _rules_store_sync,
    "store read": _rules_store_read,
    "series select": _rules_series_select,
    "pmaxtp check": _rules_pmaxtp,
    "pmaxtp sync": _rules_pmaxtp,
    "project add": _rules_project_add,
    "fetch hydro": _rules_fetch_hydro,
    "fetch meteo": _rules_fetch_meteo,
}


def _validate(
    command: object, options: object, *, task: bool, area: bool = False
) -> Options:
    spec = _BY_NAME.get(command) if isinstance(command, str) else None
    if spec is None:
        return _fail(f"Nieznana komenda {command!r}; dostępne: {', '.join(_BY_NAME)}")
    if not isinstance(options, Mapping):
        return _fail(f"Opcje komendy {spec.name} muszą być mapowaniem nazwa → wartość")
    known = {option.name for option in spec.options}
    unknown = [repr(key) for key in options if key not in known]
    if unknown:
        _fail(f"Nieznane opcje komendy {spec.name}: {', '.join(unknown)}")
    if task and "root" in options:
        _fail("Zadanie projektu nie podaje root: magazyn wynika ze store_dir projektu")
    result: Options = {}
    for option in spec.options:
        value = options.get(option.name)
        normalized = None if value is None else _value(option, value)
        if normalized is None:
            if option.required and not (
                task and (option.name == "root" or (area and option.name == "stations"))
            ):
                _fail(
                    f"Brak wymaganej opcji {option.name} ({option.flag}) komendy {spec.name}"
                )
            continue
        result[option.name] = normalized
    rules = _RULES.get(spec.name)
    if rules is not None:
        rules(result)
    return result


def validate_command(
    command: str, /, *, options: Mapping[str, object]
) -> dict[str, object]:
    """
    Normalize and validate command options without network access.

    ``list`` options accept comma-separated text, a sequence or a single number;
    years accept ``a-b`` ranges; ``lat``/``lon`` normalize to ``float``. ``None``
    values and false ``bool`` flags are omitted, so formatting the result with
    `format_command` and validating it again yields identical options.

    Parameters
    ----------
    command : str
        Catalog command name, e.g. ``"series select"``.
    options : Mapping[str, object]
        Option values keyed by their Python (``snake_case``) names.

    Returns
    -------
    dict of {str : object}
        Normalized options in catalog order (``Path`` objects, tuples, sorted
        years and months, de-duplicated stations and variables).

    Raises
    ------
    IMGWValidationError
        If the command, an option name or an option value is unknown or invalid,
        or a required option is missing.
    """
    return _validate(command, options, task=False)


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _argument(value: object) -> str:
    if isinstance(value, tuple):
        return ",".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(
            _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    if isinstance(value, float):
        return repr(value)
    return str(value)


def format_command(command: str, /, *, options: Mapping[str, object]) -> str:
    """
    Format a command as a stable, ``shlex``-quoted CLI invocation.

    Only the given options are emitted, after normalization; no hidden options
    are added.

    Parameters
    ----------
    command : str
        Catalog command name.
    options : Mapping[str, object]
        Option values keyed by their Python (``snake_case``) names.

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
    words = ["imgw", *command.split()]
    for option in _BY_NAME[command].options:
        if option.name not in normalized:
            continue
        words.append(option.flag)
        if option.type != "bool":
            words.append(_argument(normalized[option.name]))
    return " ".join(shlex.quote(word) for word in words)


# --- pobieranie archiwów (istniejące fetch hydro|meteo) ------------------------------------


def _server_path(url: str) -> str:
    prefix = IMGW_PUBLIC_DATA_URL + "/"
    if not url.startswith(prefix):
        _fail(f"Nieznana ścieżka IMGW: {url}")
    return url[len(prefix) :]


def _archive_download(
    command: str, interval: Any, subtype: Any, file: ArchiveFile
) -> Callable[[], Any]:
    """Public ``download_*`` call for one enumerated archive file."""
    year, param = file.year, file.param
    if year is None or (param is not None and param not in ("T", "Q", "H")):
        raise IMGWValidationError(f"Nieobsługiwane archiwum: {file.server_path}")
    if command == "fetch hydro":
        return partial(_fetch.download_hydro_data, interval, year, file.month, param)
    return partial(_fetch.download_meteo_data, interval, subtype, year, file.month)


def _fetch_jobs(
    command: str, options: Options
) -> list[tuple[str, str, Callable[[], Any]]]:
    """Pliki do pobrania wyliczone offline: (server_path, url, publiczne ``download_*``)."""
    years = _year_range("year", options["year"])
    month = options.get("month")
    months = (month,) if month is not None else None
    if command == "fetch hydro":
        interval = options.get("interval", "polroczne_i_roczne")
        files = archive_files(_HYDRO_INTERVALS[interval], years=years, months=months)
        if "param" in options:
            files = tuple(file for file in files if file.param == options["param"])
        return [
            (
                file.server_path,
                file.url,
                _archive_download(command, interval, None, file),
            )
            for file in files
        ]
    interval = options.get("interval", "miesieczne")
    subtype = options.get("subtype", "synop")
    if interval == "dobowe" and subtype in ("klimat", "opad"):
        key = f"pl.imgw.meteo_{'climate' if subtype == 'klimat' else 'precip'}_daily"
        return [
            (
                file.server_path,
                file.url,
                _archive_download(command, interval, subtype, file),
            )
            for file in archive_files(key, years=years, months=months)
        ]
    jobs: dict[str, tuple[str, str, Callable[[], Any]]] = {}
    for year in years:
        hourly = interval == "terminowe" and year >= 2001
        for selected in (
            (range(1, 13) if month is None else (month,)) if hourly else (None,)
        ):
            try:
                url = build_meteo_url(
                    MeteoInterval(interval), MeteoSubtype(subtype), year, selected
                ).url
            except ValueError as exc:
                raise IMGWValidationError(
                    f"Archiwum meteorologiczne {interval}/{subtype} {year} nie jest publikowane jako plik zbiorczy: {exc}"
                ) from exc
            jobs.setdefault(
                url,
                (
                    _server_path(url),
                    url,
                    partial(
                        _fetch.download_meteo_data, interval, subtype, year, selected
                    ),
                ),
            )
    return list(jobs.values())


def _destination(output: Path, server_path: str) -> Path:
    relative = PurePosixPath(server_path)
    if (
        relative.is_absolute()
        or relative.suffix != ".zip"
        or "\\" in server_path
        or any(part in (".", "..", "") for part in server_path.split("/"))
    ):
        _fail(f"Niebezpieczna ścieżka archiwum: {server_path}")
    return output.joinpath(*relative.parts)


def _save(destination: Path, data: bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    try:
        with part.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)
    return destination


def _run_fetch(command: str, options: Options, hooks: Hooks) -> Path:
    output = _absolute(options.get("output", _DEFAULT_OUTPUT))
    on_progress, on_notice, cancel = (
        hooks["on_progress"],
        hooks["on_notice"],
        hooks["cancel"],
    )
    jobs = _fetch_jobs(command, options)
    downloaded = 0
    for index, (server_path, _url, download) in enumerate(jobs, 1):
        if cancel is not None and cancel():
            if on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "cancelled",
                        f"Anulowano pobieranie; pominięto {len(jobs) - index + 1} plików",
                    )
                )
            break
        try:
            target = _save(_destination(output, server_path), download().data)
        except (IMGWError, OSError) as exc:
            if on_notice is not None:
                on_notice(
                    Notice(
                        "error", "download_failed", f"Nie pobrano {server_path}: {exc}"
                    )
                )
            if on_progress is not None:
                on_progress(
                    Progress(index, len(jobs), "archive", "failed", server_path)
                )
            continue
        downloaded += 1
        if on_progress is not None:
            on_progress(
                Progress(index, len(jobs), "archive", "downloaded", f"Pobrano {target}")
            )
    if downloaded and on_notice is not None:
        attribution = get_dataset(
            "pl.imgw.hydro_daily"
            if command == "fetch hydro"
            else "pl.imgw.meteo_climate_daily"
        ).license.attribution
        on_notice(
            Notice(
                "info",
                "license_terms",
                f"{attribution}. Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.",
            )
        )
    return output


def _check_fetch(command: str, options: Options, hooks: Hooks) -> StorePlan:
    output = _absolute(options.get("output", _DEFAULT_OUTPUT))
    actions = []
    for server_path, url, _download in _fetch_jobs(command, options):
        target = _destination(output, server_path)
        status = "unverifiable" if target.exists() else "missing"
        detail = f"{url} → {target}" + (
            " (istniejący plik zostanie zastąpiony)" if target.exists() else ""
        )
        actions.append(PlanAction(command, status, detail))
    return _plan(output, actions)


# --- dispatch ------------------------------------------------------------------------------


def _plan(root: PathArg, actions: Iterable[PlanAction]) -> StorePlan:
    return StorePlan(
        "imgw-plan/1", _absolute(root), datetime.now(UTC), (), {}, tuple(actions)
    )


def _project() -> ModuleType:
    return importlib.import_module("imgwtools.project")


def _cell(options: Options) -> Options:
    return {
        "method": options["method"],
        "latitude": options["lat"],
        "longitude": options["lon"],
        "ind_x": options.get("ind_x"),
        "ind_y": options.get("ind_y"),
    }


def _period_years(periods: Iterable[tuple[date, date]], year_type: str) -> set[int]:
    def year(day: date) -> int:
        return (
            day.year + 1
            if year_type == "hydrological" and day.month >= 11
            else day.year
        )

    return {
        number for start, end in periods for number in range(year(start), year(end) + 1)
    }


def _series_entry(options: Options) -> StoreEntry | None:
    slug = get_dataset(options["dataset"]).slug
    return _store.current_version(options["root"], slot=f"series:{slug}")


def _select(options: Options, entry: StoreEntry | None) -> SeriesSelection:
    dataset = options["dataset"]
    if entry is None or entry.version is None:
        raise IMGWStoreError(
            f"Brak szeregu {dataset} w magazynie; najpierw uruchom series build"
        )
    index = _store.read_series_index(entry.version)
    missing = [code for code in options["stations"] if code not in index.stations]
    if missing:
        _fail(f"Stacje spoza szeregu {dataset}: {', '.join(missing)}")
    year_type = options.get("year_type", index.year_type)
    available = _period_years(index.periods, year_type)
    years = options.get("years") or tuple(sorted(available))
    outside = [str(year) for year in years if year not in available]
    if outside:
        _fail(f"Lata spoza szeregu {dataset} ({year_type}): {', '.join(outside)}")
    variables = options.get("variables") or tuple(get_dataset(dataset).variables)
    return SeriesSelection(
        dataset, entry.version, options["stations"], variables, years, year_type
    )


def _check_select(options: Options, hooks: Hooks) -> StorePlan:
    try:
        entry = _series_entry(options)
        if entry is None:
            action = PlanAction(
                "series select",
                "missing",
                f"Brak szeregu {options['dataset']} w magazynie; najpierw series build",
            )
        else:
            selection = _select(options, entry)
            action = PlanAction(
                "series select",
                "current",
                (
                    f"{selection.version}: stacje {', '.join(selection.stations)}; zmienne {', '.join(selection.variables)}; "
                    f"lata {', '.join(map(str, selection.years))} ({selection.year_type})"
                ),
            )
    except IMGWError as exc:
        action = PlanAction("series select", "check_failed", str(exc))
    return _plan(options["root"], [action])


def _store_root(version: Path) -> Path:
    path = _absolute(version)
    for candidate in (path, *path.parents):
        if (candidate / _STORE_MARKER).is_file():
            return candidate
    return path.parent


def _run_store_read(options: Options, hooks: Hooks) -> Path | Iterator[str]:
    export = importlib.import_module("imgwtools.store.export")
    records = _store.read_archive(options["version"])
    lines = export._record_lines(records, format=options.get("format", "csv"))
    if "path" not in options:
        return lines
    return export._write_lines(options["path"], lines, cancel=hooks["cancel"])


def _check_store_read(options: Options, hooks: Hooks) -> StorePlan:
    version, format_ = options["version"], options.get("format", "csv")
    try:
        _store.read_archive(version)
    except IMGWError as exc:
        action = PlanAction("store read", "check_failed", str(exc))
    else:
        if "path" not in options:
            action = PlanAction(
                "store read",
                "current",
                f"Odczyt rekordów {version} ({format_}) na standardowe wyjście",
            )
        else:
            target = _absolute(options["path"])
            action = PlanAction(
                "store read",
                "newer" if target.exists() else "missing",
                f"Zapis rekordów {version} ({format_}) do {target}"
                + (" (istniejący plik zostanie zastąpiony)" if target.exists() else ""),
            )
    return _plan(_store_root(version), [action])


def _run_export(options: Options, hooks: Hooks) -> Path:
    export = importlib.import_module("imgwtools.store.export")
    return export.export_series(
        options["version"],
        station=options["station"],
        path=options["path"],
        variables=options["variables"],
        year_type=options.get("year_type"),
        format=options.get("format", "csv"),
        **hooks,
    )


def _check_export(options: Options, hooks: Hooks) -> StorePlan:
    target = _absolute(options["path"])
    variables = options["variables"]
    try:
        index = _store.read_series_index(options["version"])
        descriptor = get_dataset(index.dataset)
        if options["station"] not in index.stations:
            _fail(
                f"Stacja {options['station']} nie występuje w szeregu {index.dataset}"
            )
        unknown = [name for name in variables if name not in descriptor.variables]
        if unknown:
            _fail(
                f"Nieznane zmienne {', '.join(unknown)}; dostępne: {', '.join(descriptor.variables)}"
            )
        year_type = options.get("year_type", index.year_type)
        if descriptor.time_unit == "half_year" and year_type == "calendar":
            _fail("Szereg półroczny obsługuje wyłącznie rok hydrologiczny")
    except IMGWError as exc:
        action = PlanAction("series export", "check_failed", str(exc))
    else:
        action = PlanAction(
            "series export",
            "newer" if target.exists() else "missing",
            (
                f"Eksport CSV stacji {options['station']} ({', '.join(variables)}; rok {year_type}) do {target}"
                + (" (istniejący plik zostanie zastąpiony)" if target.exists() else "")
            ),
        )
    return _plan(_store_root(options["version"]), [action])


def _run_store_check(options: Options, hooks: Hooks) -> StorePlan:
    plan = _store.check_store(
        options["root"],
        datasets=options["dataset"],
        years=options["years"],
        months=options.get("months"),
        **hooks,
    )
    if "plan" in options:
        plan.to_json(options["plan"])
    return plan


def _check_store_sync(options: Options, hooks: Hooks) -> StorePlan:
    if "plan" not in options:
        return _store.check_store(
            options["root"],
            datasets=options["dataset"],
            years=options["years"],
            months=options.get("months"),
            **hooks,
        )
    plan = StorePlan.from_json(options["plan"])
    if _absolute(plan.root) != _absolute(options["root"]):
        _fail(f"Plan dotyczy innego magazynu: {plan.root}")
    return plan


def _check_store_init(options: Options, hooks: Hooks) -> StorePlan:
    root = _absolute(options["root"])
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


def _check_pmaxtp_read(options: Options, hooks: Hooks) -> StorePlan:
    root = _absolute(options["root"])
    cell = f"{options['method']}:{options['ind_x']}_{options['ind_y']}"
    try:
        if "version" in options:
            version = (
                options["version"]
                if options["version"].is_absolute()
                else root / options["version"]
            )
            found = version if version.exists() else None
        else:
            entry = _store.current_version(root, slot=f"pmaxtp:{cell}")
            found = entry.version if entry is not None else None
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


def _read_only(command: str, key: str) -> Callable[[Options, Hooks], StorePlan]:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        return _plan(
            options[key],
            [
                PlanAction(
                    command,
                    "current",
                    f"Operacja tylko do odczytu: {_absolute(options[key])}",
                )
            ],
        )

    return check


def _check_manifest(command: str) -> Callable[[Options, Hooks], StorePlan]:
    def check(options: Options, hooks: Hooks) -> StorePlan:
        manifest = _absolute(options["project_dir"]) / PROJECT_FILE
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
        return _plan(options["project_dir"], [action])

    return check


def _run_project_check(options: Options, hooks: Hooks) -> StorePlan:
    plan = _project().check_project(
        options["project_dir"], tasks=options.get("tasks"), **hooks
    )
    if "plan" in options:
        plan.to_json(options["plan"])
    return plan


def _check_project(options: Options, hooks: Hooks) -> StorePlan:
    return _project().check_project(
        options["project_dir"], tasks=options.get("tasks"), **hooks
    )


def _check_pmaxtp(options: Options, hooks: Hooks) -> StorePlan:
    return _store.check_pmaxtp(options["root"], **_cell(options), **hooks)


Runner = Callable[[Options, Hooks], Any]

_RUN: dict[str, Runner] = {
    "store init": lambda o, h: _store.init_store(o["root"]),
    "store info": lambda o, h: _store.store_info(o["root"]),
    "store scan": lambda o, h: tuple(_store.iter_store(o["root"], kind=o.get("kind"))),
    "store check": _run_store_check,
    "store sync": lambda o, h: _store.sync_store(
        o["root"],
        datasets=o.get("dataset"),
        years=o.get("years"),
        months=o.get("months"),
        plan=o.get("plan"),
        series=not o.get("no_series", False),
        **h,
    ),
    "store catalog": lambda o, h: _store.build_catalog(
        o["root"], user_locations=o.get("user_locations"), **h
    ),
    "store read": _run_store_read,
    "series build": lambda o, h: _store.build_series(
        o["root"], dataset=o["dataset"], **h
    ),
    "series export": _run_export,
    "series select": lambda o, h: _select(o, _series_entry(o)),
    "pmaxtp check": _check_pmaxtp,
    "pmaxtp sync": lambda o, h: _store.sync_pmaxtp(o["root"], **_cell(o), **h),
    "pmaxtp read": lambda o, h: _store.read_pmaxtp(
        o["root"],
        method=o["method"],
        ind_x=o["ind_x"],
        ind_y=o["ind_y"],
        version=o.get("version"),
    ),
    "project init": lambda o, h: _project().init_project(
        o["project_dir"], store_dir=o["store_dir"]
    ),
    "project add": lambda o, h: _project().add_project_task(
        o["project_dir"],
        name=o["name"],
        command=o["command"],
        options=o["options"],
        geometry=o.get("geometry"),
    ),
    "project remove": lambda o, h: _project().remove_project_task(
        o["project_dir"], name=o["name"]
    ),
    "project set-store": lambda o, h: _project().set_project_store(
        o["project_dir"], store_dir=o["store_dir"]
    ),
    "project download": lambda o, h: _project().download_project(
        o["project_dir"],
        tasks=o.get("tasks"),
        plan=o.get("plan"),
        update=o.get("update", "pinned"),
        **h,
    ),
    "project check": _run_project_check,
    "project status": lambda o, h: _project().get_project_status(
        o["project_dir"], tasks=o.get("tasks")
    ),
    "project verify": lambda o, h: _project().verify_project(
        o["project_dir"], tasks=o.get("tasks"), **h
    ),
    "fetch hydro": partial(_run_fetch, "fetch hydro"),
    "fetch meteo": partial(_run_fetch, "fetch meteo"),
}

_CHECK: dict[str, Runner] = {
    "store init": _check_store_init,
    "store info": _read_only("store info", "root"),
    "store scan": _read_only("store scan", "root"),
    "store check": lambda o, h: _store.check_store(
        o["root"], datasets=o["dataset"], years=o["years"], months=o.get("months"), **h
    ),
    "store sync": _check_store_sync,
    "store catalog": lambda o, h: _store.check_catalog(
        o["root"], user_locations=o.get("user_locations"), **h
    ),
    "store read": _check_store_read,
    "series build": lambda o, h: _store.check_series(
        o["root"], dataset=o["dataset"], **h
    ),
    "series export": _check_export,
    "series select": _check_select,
    "pmaxtp check": _check_pmaxtp,
    "pmaxtp sync": _check_pmaxtp,
    "pmaxtp read": _check_pmaxtp_read,
    "project init": _check_manifest("project init"),
    "project add": _check_manifest("project add"),
    "project remove": _check_manifest("project remove"),
    "project set-store": _check_manifest("project set-store"),
    "project download": _check_project,
    "project check": _check_project,
    "project status": _read_only("project status", "project_dir"),
    "project verify": _read_only("project verify", "project_dir"),
    "fetch hydro": partial(_check_fetch, "fetch hydro"),
    "fetch meteo": partial(_check_fetch, "fetch meteo"),
}


def _hooks(
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> Hooks:
    return {"on_progress": on_progress, "on_notice": on_notice, "cancel": cancel}


def check_command(
    command: str,
    /,
    *,
    options: Mapping[str, object],
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan a command without mutating anything or downloading content.

    Commands with their own check use it (e.g. ``store sync`` → `check_store`,
    ``series build`` → `check_series`, ``project download`` → `check_project`);
    the others return planned `PlanAction` items with the expected paths and
    validation results.

    Parameters
    ----------
    command : str
        Catalog command name.
    options : Mapping[str, object]
        Option values, identical to those accepted by `run_command`.
    on_progress : ProgressHook or None, optional
        Progress callback forwarded to the underlying check.
    on_notice : NoticeHook or None, optional
        Notice callback forwarded to the underlying check.
    cancel : Cancel or None, optional
        Cancellation callback forwarded to the underlying check.

    Returns
    -------
    StorePlan
        ``imgw-plan/1`` plan of the command.

    Raises
    ------
    IMGWValidationError
        If the command or its options are invalid (see `validate_command`).
    IMGWError
        Errors of the underlying public check function are propagated.
    """
    normalized = validate_command(command, options=options)
    return _CHECK[command](normalized, _hooks(on_progress, on_notice, cancel))


def run_command(
    command: str,
    /,
    *,
    options: Mapping[str, object],
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> (
    StoreHandle
    | StoreInfo
    | tuple[StoreEntry, ...]
    | StorePlan
    | SyncReport
    | SeriesReport
    | SeriesSelection
    | CatalogReport
    | PMaXTPStoreResult
    | PMaXTPResult
    | Project
    | ProjectReport
    | Path
    | Iterator[str]
):
    """
    Run a catalog command through exactly one public API function.

    Parameters
    ----------
    command : str
        Catalog command name.
    options : Mapping[str, object]
        Option values keyed by their Python (``snake_case``) names.
    on_progress : ProgressHook or None, optional
        Progress callback forwarded to the public function.
    on_notice : NoticeHook or None, optional
        Notice callback forwarded to the public function.
    cancel : Cancel or None, optional
        Cancellation callback forwarded to the public function.

    Returns
    -------
    object
        Result of the dispatched public function: `StoreHandle`, `StoreInfo`,
        tuple of `StoreEntry`, `StorePlan`, `SyncReport`, `SeriesReport`,
        `SeriesSelection`, `CatalogReport`, `PMaXTPStoreResult`, `PMaXTPResult`,
        `Project`, `ProjectReport` or `Path` (``fetch hydro|meteo`` return the
        output directory, ``store read`` with ``path`` the written file).
        ``store read`` without ``path`` returns an iterator of formatted text
        lines (CSV with header or JSONL, line terminators included); the
        archive is validated and verified before it is returned.

    Raises
    ------
    IMGWValidationError
        If the command or its options are invalid (see `validate_command`).
    IMGWError
        Errors of the dispatched public function are propagated.
    """
    normalized = validate_command(command, options=options)
    return _RUN[command](normalized, _hooks(on_progress, on_notice, cancel))
