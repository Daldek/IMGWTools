"""Canonical IMGW dataset descriptors and offline archive enumeration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from imgwtools.core.url_builder import IMGW_PUBLIC_DATA_URL
from imgwtools.exceptions import IMGWValidationError


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
    Registry entry describing a supported IMGW dataset.

    Attributes
    ----------
    key : str
        Full namespaced dataset key, e.g. ``"pl.imgw.hydro_daily"``.
    slug : str
        Short name used in series paths, e.g. ``"hydro_daily"``.
    server_dir : str or None
        Directory on the IMGW public data server, e.g.
        ``"dane_hydrologiczne/dobowe"``; None for PMAXTP.
    parser : str or None
        Name of the registered public parser function; None for PMAXTP.
    variables : Mapping of str to str
        Variable codes mapped to their units, e.g. ``{"H": "cm"}``.
    time_unit : {"day", "month", "half_year", "station_list", "cell"}
        Time resolution of a record, or the auxiliary source type.
    year_type : {"hydrological", "calendar", "none"}
        Year numbering of the archives.
    update_signal : {"http", "none"}
        Whether freshness can be checked by HTTP headers.
    license : License
        License and attribution of the data.
    """

    key: str
    slug: str
    server_dir: str | None
    parser: str | None
    variables: Mapping[str, str]
    time_unit: Literal["day", "month", "half_year", "station_list", "cell"]
    year_type: Literal["hydrological", "calendar", "none"]
    update_signal: Literal["http", "none"]
    license: License


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
        Archive year (hydrological or calendar per ``year_type``); None for
        station lists.
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

_DATASETS = (
    DatasetDescriptor(
        "pl.imgw.hydro_daily",
        "hydro_daily",
        "dane_hydrologiczne/dobowe",
        "parse_daily_csv",
        {"H": "cm", "Q": "m3/s", "T": "degC"},
        "day",
        "hydrological",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.hydro_monthly",
        "hydro_monthly",
        "dane_hydrologiczne/miesieczne",
        "parse_monthly_csv",
        {
            f"{v}_{stat}": unit
            for v, unit in (("H", "cm"), ("Q", "m3/s"), ("T", "degC"))
            for stat in ("min", "mean", "max")
        },
        "month",
        "hydrological",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.hydro_semiannual",
        "hydro_semiannual",
        "dane_hydrologiczne/polroczne_i_roczne",
        "parse_semi_annual_csv",
        {
            f"{v}_{stat}": unit
            for v, unit in (("H", "cm"), ("Q", "m3/s"), ("T", "degC"))
            for stat in ("min", "mean", "max")
        },
        "half_year",
        "hydrological",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.meteo_climate_daily",
        "meteo_climate_daily",
        "dane_meteorologiczne/dobowe/klimat",
        "parse_meteo_climate_daily",
        {
            "Tmax": "degC",
            "Tmin": "degC",
            "Tmean": "degC",
            "Tground": "degC",
            "P": "mm",
            "snow_cover": "cm",
        },
        "day",
        "calendar",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.meteo_precip_daily",
        "meteo_precip_daily",
        "dane_meteorologiczne/dobowe/opad",
        "parse_meteo_precip_daily",
        {"P": "mm", "snow_cover": "cm", "fresh_snow": "cm"},
        "day",
        "calendar",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.hydro_stations",
        "hydro_stations",
        "dane_hydrologiczne",
        "parse_stations_csv",
        {},
        "station_list",
        "none",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.meteo_stations",
        "meteo_stations",
        "dane_meteorologiczne",
        "parse_stations_csv",
        {},
        "station_list",
        "none",
        "http",
        _LICENSE,
    ),
    DatasetDescriptor(
        "pl.imgw.pmaxtp",
        "pmaxtp",
        None,
        None,
        {"ks": "mm", "sg": "mm", "rb": "mm"},
        "cell",
        "none",
        "none",
        _LICENSE,
    ),
)
_BY_KEY = {descriptor.key: descriptor for descriptor in _DATASETS}


def datasets() -> tuple[DatasetDescriptor, ...]:
    """
    Return all supported measurement and auxiliary source descriptors.

    Returns
    -------
    tuple of DatasetDescriptor
        Five measurement datasets, two station lists and PMAXTP.
    """
    return _DATASETS


def get_dataset(dataset: str, /) -> DatasetDescriptor:
    """
    Find a dataset by its full, namespaced key.

    Parameters
    ----------
    dataset : str
        Full dataset key, e.g. ``"pl.imgw.hydro_daily"``; slugs are not
        accepted.

    Returns
    -------
    DatasetDescriptor
        Descriptor of the dataset.

    Raises
    ------
    IMGWValidationError
        If the key is unknown.
    """
    try:
        return _BY_KEY[dataset]
    except (KeyError, TypeError) as exc:
        raise IMGWValidationError(f"Nieznany klucz zbioru IMGW: {dataset}") from exc


def _meteo_folder(year: int, *, precipitation: bool) -> str:
    if year > 2000:
        return str(year)
    if precipitation and year <= 1955:
        return "1950_1955"
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
) -> ArchiveFile:
    start, end = (
        _period(year, month, hydrological=descriptor.year_type == "hydrological")
        if year is not None
        else (None, None)
    )
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
    dataset: str, /, *, years: Iterable[int], months: Iterable[int] | None = None
) -> tuple[ArchiveFile, ...]:
    """
    Enumerate distinct physical IMGW archives without accessing the network.

    Years and months are deduplicated and sorted. Months select only
    physically monthly files (daily hydro before 2023, daily meteo from
    2001); for yearly archives one file per year is returned. Years are not
    limited by the current year; whether a file is published is decided by
    the server.

    Parameters
    ----------
    dataset : str
        Full dataset key of a measurement dataset.
    years : iterable of int
        Archive years (hydrological or calendar per the dataset); the
        minimum is 1951, or 1950 for ``pl.imgw.meteo_precip_daily``.
    months : iterable of int or None, optional
        Months 1-12 (for hydrological data 1 = November of the previous
        year); None selects all months.

    Returns
    -------
    tuple of ArchiveFile
        Archives ordered by year, then by month or parameter.

    Raises
    ------
    IMGWValidationError
        If the dataset key is unknown, the dataset has no yearly archives
        (station lists, PMAXTP), or the years or months are empty, not
        integers or out of range.
    """
    descriptor = get_dataset(dataset)
    if descriptor.time_unit in ("station_list", "cell"):
        raise IMGWValidationError(f"Zbiór {dataset} nie udostępnia archiwów rocznych")
    try:
        selected_years = sorted(set(years))
        selected_months = (
            sorted(set(months)) if months is not None else list(range(1, 13))
        )
    except TypeError as exc:
        raise IMGWValidationError(
            "Roczniki i miesiące muszą być liczbami całkowitymi"
        ) from exc
    first_year = 1950 if descriptor.slug == "meteo_precip_daily" else 1951
    if not selected_years or any(
        type(year) is not int or year < first_year or year > 9999
        for year in selected_years
    ):
        raise IMGWValidationError(
            f"Nieprawidłowe roczniki zbioru {dataset}; minimalny rok: {first_year}"
        )
    if (
        any(type(month) is not int or not 1 <= month <= 12 for month in selected_months)
        or not selected_months
    ):
        raise IMGWValidationError("Miesiące muszą należeć do zakresu 1–12")

    result: list[ArchiveFile] = []
    for year in selected_years:
        directory = descriptor.server_dir
        if descriptor.slug == "hydro_daily":
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
        elif descriptor.slug == "hydro_monthly":
            result.append(
                _archive(descriptor, f"{directory}/{year}/mies_{year}.zip", year)
            )
        elif descriptor.slug == "hydro_semiannual":
            for param in ("H", "Q", "T"):
                result.append(
                    _archive(
                        descriptor,
                        f"{directory}/{year}/polr_{param}_{year}.zip",
                        year,
                        param=param,
                    )
                )
        else:
            precipitation = descriptor.slug == "meteo_precip_daily"
            folder = _meteo_folder(year, precipitation=precipitation)
            suffix = "o" if precipitation else "k"
            if year <= 2000:
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
