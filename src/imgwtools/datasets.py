"""Canonical IMGW dataset descriptors and offline archive enumeration."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from imgwtools.exceptions import IMGWValidationError
from imgwtools.urls import IMGW_PUBLIC_DATA_URL

YearsArg = int | str | Iterable[int | str]
"""Years: ``2024``, ``"2020-2023"``, ``"2020,2022"`` or ``[2020, "2022-2023"]``."""

MonthsArg = int | str | Iterable[int | str]
"""Months 1-12: ``3``, ``"3"``, ``"1,2"`` or ``[1, "2"]``."""

_YEAR = re.compile(r"([0-9]{1,4})(?:-([0-9]{1,4}))?")
_MONTH = re.compile(r"[0-9]{1,2}")
_PARAMS = ("H", "Q", "T")


@dataclass(frozen=True)
class License:
    """
    License and attribution terms of IMGW-PIB data.

    Attributes
    ----------
    id : {"IMGW-PIB"}
        License identifier.
    attribution : str
        Required attribution formula (in Polish).
    url : str
        URL of the IMGW-PIB terms of use.
    """

    id: Literal["IMGW-PIB"]
    attribution: str
    url: str


@dataclass(frozen=True)
class DatasetDescriptor:
    """
    Registry entry describing an IMGW dataset.

    Attributes
    ----------
    key : str
        Full namespaced dataset key, e.g. ``"pl.imgw.hydro_daily"``.
    slug : str
        Short name used only in store directory names, e.g. ``"hydro_daily"``.
    kind : {"hydro", "meteo"} or None
        Data family; None for PMAXTP.
    title : str
        Polish title of the dataset, e.g. ``"Dane hydrologiczne dobowe"``.
    server_dir : str or None
        Directory on the IMGW public data server, e.g.
        ``"dane_hydrologiczne/dobowe"``; None for PMAXTP.
    parser : str or None
        Name of the registered public parser function; None for PMAXTP and
        download-only datasets.
    variables : Mapping of str to str
        Variable codes mapped to their units, e.g. ``{"H": "cm"}``; empty for
        station lists and download-only datasets.
    time_unit : {"day", "month", "half_year", "term", "station_list", "cell"}
        Time resolution of a record, or the auxiliary source type.
    year_type : {"hydrological", "calendar", "none"}
        Year numbering of the archives.
    first_year : int or None
        Lowest year accepted by the offline generator (there is no upper
        bound); None for station lists and PMAXTP.
    update_signal : {"http", "none"}
        Whether freshness can be checked by HTTP headers.
    license : License
        License and attribution of the data.
    legacy_alias : str or None
        Pre-3.0 interval path accepted as input, e.g. ``"hydro/dobowe"``.
    in_store : bool
        Whether the dataset can be stored in the versioned store; False for
        datasets that can only be downloaded.
    """

    key: str
    slug: str
    kind: Literal["hydro", "meteo"] | None
    title: str
    server_dir: str | None
    parser: str | None
    variables: Mapping[str, str]
    time_unit: Literal["day", "month", "half_year", "term", "station_list", "cell"]
    year_type: Literal["hydrological", "calendar", "none"]
    first_year: int | None
    update_signal: Literal["http", "none"]
    license: License
    legacy_alias: str | None
    in_store: bool


@dataclass(frozen=True)
class ArchiveFile:
    """
    Single physical IMGW source file (ZIP archive or station CSV).

    Attributes
    ----------
    dataset : str
        Full key of the dataset the file belongs to.
    server_path : str
        File path relative to the IMGW public data root.
    url : str
        Full download URL.
    year : int or None
        Archive year (hydrological or calendar per ``year_type``); for a
        meteorological monthly archive covering a multi-year folder, the
        first year of the folder; None for station lists.
    month : int or None
        Month of a monthly file (for hydrological data 1 = November of the
        previous year, 12 = October); None for yearly files.
    param : str or None
        Parameter of a semi-annual archive (``"H"``, ``"Q"`` or ``"T"``),
        None otherwise.
    year_type : {"hydrological", "calendar", "none"}
        Year numbering of ``year``.
    period_start : date or None
        First calendar day covered by the file; None for station lists.
    period_end : date or None
        Last calendar day covered by the file; None for station lists.
    """

    dataset: str
    server_path: str
    url: str
    year: int | None
    month: int | None
    param: str | None
    year_type: Literal["hydrological", "calendar", "none"]
    period_start: date | None
    period_end: date | None


_LICENSE = License(
    "IMGW-PIB",
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy",
    "https://danepubliczne.imgw.pl/regulations",
)

_HYDRO_STATS = {
    f"{v}_{stat}": unit
    for v, unit in (("H", "cm"), ("Q", "m3/s"), ("T", "degC"))
    for stat in ("min", "mean", "max")
}

_DATASETS = (
    DatasetDescriptor(
        key="pl.imgw.hydro_daily",
        slug="hydro_daily",
        kind="hydro",
        title="Dane hydrologiczne dobowe",
        server_dir="dane_hydrologiczne/dobowe",
        parser="parse_daily_csv",
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="day",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="hydro/dobowe",
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_monthly",
        slug="hydro_monthly",
        kind="hydro",
        title="Dane hydrologiczne miesięczne",
        server_dir="dane_hydrologiczne/miesieczne",
        parser="parse_monthly_csv",
        variables=_HYDRO_STATS,
        time_unit="month",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="hydro/miesieczne",
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_semiannual",
        slug="hydro_semiannual",
        kind="hydro",
        title="Dane hydrologiczne półroczne i roczne",
        server_dir="dane_hydrologiczne/polroczne_i_roczne",
        parser="parse_semi_annual_csv",
        variables=_HYDRO_STATS,
        time_unit="half_year",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="hydro/polroczne_i_roczne",
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_climate_daily",
        slug="meteo_climate_daily",
        kind="meteo",
        title="Dane meteorologiczne dobowe ze stacji klimatycznych",
        server_dir="dane_meteorologiczne/dobowe/klimat",
        parser="parse_meteo_climate_daily",
        variables={
            "Tmax": "degC",
            "Tmin": "degC",
            "Tmean": "degC",
            "Tground": "degC",
            "P": "mm",
            "snow_cover": "cm",
        },
        time_unit="day",
        year_type="calendar",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/dobowe/klimat",
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_precip_daily",
        slug="meteo_precip_daily",
        kind="meteo",
        title="Dane meteorologiczne dobowe ze stacji opadowych",
        server_dir="dane_meteorologiczne/dobowe/opad",
        parser="parse_meteo_precip_daily",
        variables={"P": "mm", "snow_cover": "cm", "fresh_snow": "cm"},
        time_unit="day",
        year_type="calendar",
        first_year=1950,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/dobowe/opad",
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_stations",
        slug="hydro_stations",
        kind="hydro",
        title="Lista stacji hydrologicznych",
        server_dir="dane_hydrologiczne",
        parser="parse_stations_csv",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_stations",
        slug="meteo_stations",
        kind="meteo",
        title="Lista stacji meteorologicznych",
        server_dir="dane_meteorologiczne",
        parser="parse_stations_csv",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.pmaxtp",
        slug="pmaxtp",
        kind=None,
        title="Opady maksymalne prawdopodobne PMAXTP",
        server_dir=None,
        parser=None,
        variables={"ks": "mm", "sg": "mm", "rb": "mm"},
        time_unit="cell",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_phenomena",
        slug="hydro_phenomena",
        kind="hydro",
        title="Zjawiska hydrologiczne dobowe",
        server_dir="dane_hydrologiczne/dobowe",
        parser=None,
        variables={},
        time_unit="day",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_climate_monthly",
        slug="meteo_climate_monthly",
        kind="meteo",
        title="Dane meteorologiczne miesięczne ze stacji klimatycznych",
        server_dir="dane_meteorologiczne/miesieczne/klimat",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/miesieczne/klimat",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_precip_monthly",
        slug="meteo_precip_monthly",
        kind="meteo",
        title="Dane meteorologiczne miesięczne ze stacji opadowych",
        server_dir="dane_meteorologiczne/miesieczne/opad",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=1950,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/miesieczne/opad",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_synop_monthly",
        slug="meteo_synop_monthly",
        kind="meteo",
        title="Dane meteorologiczne miesięczne ze stacji synoptycznych",
        server_dir="dane_meteorologiczne/miesieczne/synop",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=1960,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/miesieczne/synop",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_climate_terms",
        slug="meteo_climate_terms",
        kind="meteo",
        title="Dane meteorologiczne terminowe ze stacji klimatycznych",
        server_dir="dane_meteorologiczne/terminowe/klimat",
        parser=None,
        variables={},
        time_unit="term",
        year_type="calendar",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/terminowe/klimat",
        in_store=False,
    ),
)
# Lookup order key → slug → legacy alias: later entries of the inner tuple win.
_BY_NAME = {
    name: descriptor
    for descriptor in _DATASETS
    for name in (descriptor.legacy_alias, descriptor.slug, descriptor.key)
    if name is not None
}
_ALLOWED = [descriptor.key for descriptor in _DATASETS]
_UNSUPPORTED = {
    "meteo/dobowe/synop": (
        "per_station",
        "Archiwa meteo/dobowe/synop są publikowane osobno dla każdej stacji i nie "
        "mają zbioru w rejestrze; użyj pl.imgw.meteo_synop_monthly",
    ),
    "meteo/terminowe/synop": (
        "per_station",
        "Archiwa meteo/terminowe/synop są publikowane osobno dla każdej stacji i "
        "nie mają zbioru w rejestrze; użyj pl.imgw.meteo_synop_monthly",
    ),
    "meteo/terminowe/opad": (
        "not_published",
        "Dane meteo/terminowe/opad nie istnieją na serwerach IMGW",
    ),
}
# Suffix of the file name and the last year of the first folder of the
# meteorological five-year grid (klimat 1951_1955, opad 1950_1955, synop
# 1960_1965); from 1966 all subtypes share the 1966_1970, ... grid.
_METEO_LAYOUT = {
    "pl.imgw.meteo_climate_daily": ("k", 1955),
    "pl.imgw.meteo_precip_daily": ("o", 1955),
    "pl.imgw.meteo_climate_monthly": ("k", 1955),
    "pl.imgw.meteo_precip_monthly": ("o", 1955),
    "pl.imgw.meteo_synop_monthly": ("s", 1965),
    "pl.imgw.meteo_climate_terms": ("k", 1955),
}


def datasets(
    *, kind: Literal["hydro", "meteo"] | None = None
) -> tuple[DatasetDescriptor, ...]:
    """
    Return the dataset registry, optionally limited to one data family.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Data family to keep; None returns all 13 descriptors (PMAXTP has no
        family and is returned only then).

    Returns
    -------
    tuple of DatasetDescriptor
        Descriptors in registry order: the eight datasets of the store
        (``in_store=True``), then the five download-only datasets.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is not ``"hydro"``, ``"meteo"`` or None.
    """
    if kind is None:
        return _DATASETS
    if kind not in ("hydro", "meteo"):
        raise IMGWValidationError(
            f"Nieprawidłowy rodzaj zbioru: {kind!r}; dozwolone: hydro, meteo",
            details={"option": "kind", "value": kind, "allowed": ["hydro", "meteo"]},
        )
    return tuple(descriptor for descriptor in _DATASETS if descriptor.kind == kind)


def get_dataset(dataset: str, /) -> DatasetDescriptor:
    """
    Find a dataset by its key, slug or legacy alias.

    Parameters
    ----------
    dataset : str
        Full key (``"pl.imgw.hydro_daily"``), slug (``"hydro_daily"``) or
        legacy alias (``"hydro/dobowe"``), tried in this order.

    Returns
    -------
    DatasetDescriptor
        Descriptor of the dataset; results always carry its full ``key``.

    Raises
    ------
    IMGWValidationError
        If the value names no dataset (``details.allowed`` lists the keys),
        or it is a legacy alias of an archive without a descriptor
        (per-station synop archives, nonexistent hourly precipitation;
        ``details.reason`` says why).
    """
    if isinstance(dataset, str):
        if (descriptor := _BY_NAME.get(dataset)) is not None:
            return descriptor
        if dataset in _UNSUPPORTED:
            reason, message = _UNSUPPORTED[dataset]
            raise IMGWValidationError(
                message,
                details={
                    "option": "dataset",
                    "value": dataset,
                    "reason": reason,
                    "allowed": _ALLOWED,
                },
            )
    raise IMGWValidationError(
        f"Nieznany zbiór IMGW: {dataset!r}; dozwolone klucze: {', '.join(_ALLOWED)}",
        details={
            "option": "dataset",
            "value": dataset if isinstance(dataset, str) else repr(dataset),
            "allowed": _ALLOWED,
        },
    )


def _items(value: object, option: str) -> list[int | str]:
    """Flatten a scalar, comma-separated text or iterable into list items."""
    if isinstance(value, int | str):
        raw: list[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, bytes | Mapping):
        raw = list(value)
    else:
        raise IMGWValidationError(
            f"Opcja {option} musi być liczbą, tekstem lub listą: {value!r}",
            details={"option": option, "value": repr(value)},
        )
    items: list[int | str] = []
    for item in raw:
        if isinstance(item, str):
            items.extend(part.strip() for part in item.split(","))
        elif isinstance(item, int) and not isinstance(item, bool):
            items.append(item)
        else:
            raise IMGWValidationError(
                f"Nieprawidłowa wartość opcji {option}: {item!r}",
                details={"option": option, "value": repr(item)},
            )
    if not items or "" in items:
        raise IMGWValidationError(
            f"Opcja {option} wymaga niepustej listy wartości",
            details={"option": option, "value": repr(value)},
        )
    return items


def parse_years(value: YearsArg, /, *, option: str = "years") -> tuple[int, ...]:
    """
    Expand a years argument into sorted, unique years.

    Parameters
    ----------
    value : YearsArg
        A year (``2024``), a range (``"2020-2023"``), comma-separated text
        (``"2020,2022"``) or an iterable mixing years and ranges
        (``[2020, "2022-2023"]``).
    option : str, optional
        Option name used in error messages and ``details.option``.

    Returns
    -------
    tuple of int
        Expanded years in ascending order, without duplicates.

    Raises
    ------
    IMGWValidationError
        If the value is empty, not a year or range, a range is reversed, or a
        year is outside 1-9999.
    """
    years: set[int] = set()
    for item in _items(value, option):
        if isinstance(item, int):
            start = end = item
        elif match := _YEAR.fullmatch(item):
            start = int(match.group(1))
            end = int(match.group(2) or start)
        else:
            raise IMGWValidationError(
                f"Nieprawidłowy rok lub zakres lat w opcji {option}: {item!r}",
                details={"option": option, "value": item},
            )
        if not 1 <= start <= end <= 9999:
            raise IMGWValidationError(
                f"Nieprawidłowy zakres lat w opcji {option}: {item!r}",
                details={"option": option, "value": item},
            )
        years.update(range(start, end + 1))
    return tuple(sorted(years))


def parse_months(value: MonthsArg, /, *, option: str = "months") -> tuple[int, ...]:
    """
    Normalize a months argument into sorted, unique months.

    Parameters
    ----------
    value : MonthsArg
        A month (``3``), comma-separated text (``"1,2"``) or an iterable of
        months as numbers or text.
    option : str, optional
        Option name used in error messages and ``details.option``.

    Returns
    -------
    tuple of int
        Months 1-12 in ascending order, without duplicates.

    Raises
    ------
    IMGWValidationError
        If the value is empty, not an integer, or a month is outside 1-12.
    """
    months: set[int] = set()
    for item in _items(value, option):
        if isinstance(item, str):
            if not _MONTH.fullmatch(item):
                raise IMGWValidationError(
                    f"Opcja {option} musi zawierać liczby całkowite: {item!r}",
                    details={"option": option, "value": item},
                )
            item = int(item)
        if not 1 <= item <= 12:
            raise IMGWValidationError(
                "Miesiące muszą należeć do zakresu 1–12",
                details={"option": option, "value": item},
            )
        months.add(item)
    return tuple(sorted(months))


def _parse_params(
    params: Iterable[Literal["H", "Q", "T"]], dataset: DatasetDescriptor
) -> tuple[str, ...]:
    if dataset.key != "pl.imgw.hydro_semiannual":
        raise IMGWValidationError(
            f"Opcja params dotyczy wyłącznie zbioru pl.imgw.hydro_semiannual, "
            f"nie {dataset.key}",
            details={"option": "params", "value": dataset.key},
        )
    items = [
        part.strip()
        for item in ([params] if isinstance(params, str) else params)
        for part in (item.split(",") if isinstance(item, str) else [item])
    ]
    if not items or any(item not in _PARAMS for item in items):
        raise IMGWValidationError(
            f"Nieprawidłowe parametry półroczne: {items!r}; dozwolone: H, Q, T",
            details={"option": "params", "value": items, "allowed": list(_PARAMS)},
        )
    return tuple(param for param in _PARAMS if param in items)


def _meteo_folder(year: int, *, first_year: int, first_folder_end: int) -> str:
    if year > 2000:
        return str(year)
    if year <= first_folder_end:
        return f"{first_year}_{first_folder_end}"
    start = 1951 + (year - 1951) // 5 * 5
    return f"{start}_{start + 4}"


def _period(year: int, month: int | None, *, hydrological: bool) -> tuple[date, date]:
    if month is None:
        start = date(year - 1, 11, 1) if hydrological else date(year, 1, 1)
        end = date(year, 10, 31) if hydrological else date(year, 12, 31)
    else:
        actual_year = year - 1 if hydrological and month <= 2 else year
        actual_month = ((month + 9) % 12) + 1 if hydrological else month
        start = date(actual_year, actual_month, 1)
        next_month = (
            date(actual_year + 1, 1, 1)
            if actual_month == 12
            else date(actual_year, actual_month + 1, 1)
        )
        end = next_month - timedelta(days=1)
    return start, end


def _archive(
    descriptor: DatasetDescriptor,
    path: str,
    year: int | None,
    month: int | None = None,
    param: str | None = None,
    *,
    last_year: int | None = None,
) -> ArchiveFile:
    if year is None:
        start, end = None, None
    else:
        start, end = _period(
            year, month, hydrological=descriptor.year_type == "hydrological"
        )
        if last_year is not None:
            end = date(last_year, 12, 31)
    return ArchiveFile(
        descriptor.key,
        path,
        f"{IMGW_PUBLIC_DATA_URL}/{path}",
        year,
        month,
        param,
        descriptor.year_type,
        start,
        end,
    )


def archive_files(
    dataset: str,
    /,
    *,
    years: YearsArg,
    months: MonthsArg | None = None,
    params: Iterable[Literal["H", "Q", "T"]] | None = None,
) -> tuple[ArchiveFile, ...]:
    """
    Enumerate distinct physical IMGW archives without accessing the network.

    Months select only physically monthly files (daily hydro before 2023,
    daily and hourly meteo from 2001); for yearly archives one file per year
    is returned, and a meteorological monthly archive is returned once per
    folder (five-year folders until 2000). Years are not limited by the
    current year; whether a file is published is decided by the server.

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of one of the ten archive datasets (all
        but the station lists and PMAXTP).
    years : YearsArg
        Archive years (hydrological or calendar per the dataset), also as
        ranges ``"a-b"``; at least ``first_year`` of the dataset.
    months : MonthsArg or None, optional
        Months 1-12 (for hydrological data 1 = November of the previous
        year); None selects all months.
    params : iterable of {"H", "Q", "T"} or None, optional
        Parameters of ``pl.imgw.hydro_semiannual`` to keep; None keeps all
        three. Rejected for other datasets.

    Returns
    -------
    tuple of ArchiveFile
        Archives ordered by year, then by month or parameter.

    Raises
    ------
    IMGWValidationError
        If the dataset is unknown or has no yearly archives (station lists,
        PMAXTP), the years or months are empty, malformed or out of range,
        or ``params`` is invalid or given for another dataset.
    """
    descriptor = get_dataset(dataset)
    key = descriptor.key
    if descriptor.first_year is None or descriptor.server_dir is None:
        raise IMGWValidationError(
            f"Zbiór {key} nie udostępnia archiwów rocznych",
            details={"option": "dataset", "value": key},
        )
    selected_years = parse_years(years)
    selected_months = (
        parse_months(months) if months is not None else tuple(range(1, 13))
    )
    selected_params = (
        _parse_params(params, descriptor) if params is not None else _PARAMS
    )
    if selected_years[0] < descriptor.first_year:
        raise IMGWValidationError(
            f"Nieprawidłowe roczniki zbioru {key}; minimalny rok: "
            f"{descriptor.first_year}",
            details={
                "option": "years",
                "value": list(selected_years),
                "minimum": descriptor.first_year,
            },
        )

    directory = descriptor.server_dir
    result: list[ArchiveFile] = []
    folders: set[str] = set()
    for year in selected_years:
        if key == "pl.imgw.hydro_daily":
            if year < 2023:
                for month in selected_months:
                    result.append(
                        _archive(
                            descriptor,
                            f"{directory}/{year}/codz_{year}_{month:02d}.zip",
                            year,
                            month,
                        )
                    )
            else:
                result.append(
                    _archive(descriptor, f"{directory}/{year}/codz_{year}.zip", year)
                )
        elif key == "pl.imgw.hydro_phenomena":
            result.append(
                _archive(descriptor, f"{directory}/{year}/zjaw_{year}.zip", year)
            )
        elif key == "pl.imgw.hydro_monthly":
            result.append(
                _archive(descriptor, f"{directory}/{year}/mies_{year}.zip", year)
            )
        elif key == "pl.imgw.hydro_semiannual":
            for param in selected_params:
                result.append(
                    _archive(
                        descriptor,
                        f"{directory}/{year}/polr_{param}_{year}.zip",
                        year,
                        param=param,
                    )
                )
        else:
            suffix, first_folder_end = _METEO_LAYOUT[key]
            folder = _meteo_folder(
                year,
                first_year=descriptor.first_year,
                first_folder_end=first_folder_end,
            )
            if descriptor.time_unit == "month":
                if folder in folders:
                    continue
                folders.add(folder)
                first, _, last = folder.partition("_")
                result.append(
                    _archive(
                        descriptor,
                        f"{directory}/{folder}/{folder}_m_{suffix}.zip",
                        int(first),
                        last_year=int(last or first),
                    )
                )
            elif year <= 2000:
                result.append(
                    _archive(
                        descriptor, f"{directory}/{folder}/{year}_{suffix}.zip", year
                    )
                )
            else:
                for month in selected_months:
                    result.append(
                        _archive(
                            descriptor,
                            f"{directory}/{folder}/{year}_{month:02d}_{suffix}.zip",
                            year,
                            month,
                        )
                    )
    return tuple(result)


def station_source_files() -> tuple[ArchiveFile, ArchiveFile]:
    """
    Return the two station CSV sources as archive descriptors.

    Returns
    -------
    tuple of (ArchiveFile, ArchiveFile)
        Hydrological (``lista_stacji_hydro.csv``) and meteorological
        (``wykaz_stacji.csv``) station lists, with ``year=None`` and
        ``year_type="none"``.
    """
    hydro = get_dataset("pl.imgw.hydro_stations")
    meteo = get_dataset("pl.imgw.meteo_stations")
    return (
        _archive(hydro, f"{hydro.server_dir}/lista_stacji_hydro.csv", None),
        _archive(meteo, f"{meteo.server_dir}/wykaz_stacji.csv", None),
    )
