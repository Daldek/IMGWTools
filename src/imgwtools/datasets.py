"""Canonical dataset and provider descriptors and offline archive enumeration."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import MappingProxyType
from typing import Literal

from imgwtools.exceptions import IMGWValidationError
from imgwtools.messages import message
from imgwtools.urls import IMGW_PUBLIC_DATA_URL

YearsArg = int | str | Iterable[int | str]
"""Years: ``2024``, ``"2020-2023"``, ``"2020,2022"`` or ``[2020, "2022-2023"]``."""

MonthsArg = int | str | Iterable[int | str]
"""Months 1-12: ``3``, ``"3"``, ``"1,2"`` or ``[1, "2"]``."""

STATION_CODE_PATTERN = r"^([0-9]{9}|0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16})$"
"""Station code of any provider: nine IMGW-PIB digits or a WIGOS identifier (ČHMÚ)."""

DATASET_KEY_PATTERN = r"^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$"
"""Dataset key ``<country>.<key prefix>.<name>[_<variant>]`` of any provider (IMGW-20)."""

CATALOG_DATASET = "pl.imgw.stations"
"""Derived dataset key of the IMGW-PIB station catalog ``stations.geojson`` (no descriptor)."""

# Derived dataset key of each provider's station catalog, by provider id (ADR-003 D5).
_CATALOG_DATASETS: Mapping[str, str] = MappingProxyType(
    {"IMGW-PIB": CATALOG_DATASET, "CHMI": "cz.chmi.stations"}
)

DATASET_KEY_ALIASES: Mapping[str, str] = MappingProxyType({})
"""
Renamed dataset keys: published key → current key (ADR-001, IMGW-20).

A key published in a release with the store never changes, and sidecars keep
their raw ``dataset`` forever; a renamed dataset adds its old key here, and the
entry is recorded in the changelog. Empty in 3.0.0. Unlike ``legacy_alias``
(pre-3.0 input words), entries are stored keys that `read_meta` resolves into
``Meta.dataset_key``.
"""

_YEAR = re.compile(r"([0-9]{1,4})(?:-([0-9]{1,4}))?")
_MONTH = re.compile(r"[0-9]{1,2}")
_PARAMS = ("H", "Q", "T")

# ČHMÚ station code: a WIGOS identifier exactly as in the source (ADR-003 D3).
_WIGOS_CODE = r"0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}"
# File names of the per-station ČHMÚ archives (spec 2026-10-18 §2.3); other
# names in a server listing are not files of the datasets.
_CHMI_HYDRO_FILE = re.compile(rf"^H_({_WIGOS_CODE})_DQ_([0-9]{{4}})\.json$")
_CHMI_METEO_FILE = re.compile(rf"^dly-({_WIGOS_CODE})-(SRA|T|TMA|TMI)\.csv$")
# Daily ČHMÚ elements in file order and the server directory of each.
_CHMI_ELEMENT_GROUPS: Mapping[str, str] = MappingProxyType(
    {
        "SRA": "precipitation",
        "T": "temperature",
        "TMA": "temperature",
        "TMI": "temperature",
    }
)
# Folder of a country archive: a year or a five-year range (IMGW-PIB layout).
_FOLDER = re.compile(r"([0-9]{4})(?:_([0-9]{4}))?")


@dataclass(frozen=True)
class License:
    """
    License and attribution terms of a dataset.

    Attributes
    ----------
    id : str
        License identifier, e.g. ``"IMGW-PIB"`` (IMGW-PIB terms of use) or
        ``"CC-BY-4.0"``.
    attribution : str
        Required attribution formula of the source files (in Polish).
    url : str
        URL of the license or terms of use.
    terms_url : str or None, optional
        URL of the provider's own page on licensing and liability; None when
        the provider has none (sidecars write the field only when set).
    """

    id: str
    attribution: str
    url: str
    terms_url: str | None = None


@dataclass(frozen=True)
class ProviderDescriptor:
    """
    Registry entry describing a data provider (ADR-003 D1).

    Attributes
    ----------
    id : str
        Value of the ``provider`` fields, ``"IMGW-PIB"`` or ``"CHMI"``.
    short_name : str
        Name shown in texts, ``"IMGW-PIB"`` or ``"ČHMÚ"``.
    name : str
        Full name of the institution.
    country : str
        ISO 3166-1 alpha-2 country code, ``"PL"`` or ``"CZ"``.
    key_prefix : str
        Prefix of the provider's dataset keys, ``"pl.imgw"`` or ``"cz.chmi"``.
    base_url : str
        Base URL of the ``server_path`` of the provider's files (with the
        trailing slash).
    license : License
        License and attribution of the provider's data.
    processed_attribution : str
        Formula marking processed forms (series, catalog, exports), without
        a final full stop.
    notice : str
        Text of the ``license_terms`` notice that follows the attribution.
    station_code_pattern : str
        Regular expression of the provider's station codes.
    datasets : tuple of str
        Keys of the provider's datasets in registry order.
    """

    id: str
    short_name: str
    name: str
    country: str
    key_prefix: str
    base_url: str
    license: License
    processed_attribution: str
    notice: str
    station_code_pattern: str
    datasets: tuple[str, ...]


@dataclass(frozen=True)
class DatasetDescriptor:
    """
    Registry entry describing a dataset of a provider.

    Attributes
    ----------
    key : str
        Full namespaced dataset key, e.g. ``"pl.imgw.hydro_daily"``.
    slug : str
        Short name used only in store directory names, e.g. ``"hydro_daily"``;
        unique across providers.
    kind : {"hydro", "meteo"} or None
        Data family; None for PMAXTP.
    title : str
        Polish title of the dataset, e.g. ``"Dane hydrologiczne dobowe"``.
    server_dir : str or None
        Directory on the provider's server, relative to its ``base_url``,
        e.g. ``"dane_hydrologiczne/dobowe"``; None for PMAXTP.
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
        bound); None for station lists, PMAXTP and files without a year.
    update_signal : {"http", "listing", "none"}
        Freshness signal: HTTP headers of the file, the server listing of its
        directory, or none.
    license : License
        License and attribution of the data.
    legacy_alias : str or None
        Pre-3.0 interval path accepted as input, e.g. ``"hydro/dobowe"``.
    in_store : bool
        Whether the dataset can be stored in the versioned store; False for
        datasets that can only be downloaded.
    provider : str, optional
        ``ProviderDescriptor.id`` of the dataset's provider.
    archive_scope : {"country", "station_year", "station_element"}, optional
        What one source file covers: the whole country, one station and
        year, or the whole history of one station and element.
    variable_notes : Mapping of str to str, optional
        Convention of each variable (in Polish), e.g. the day of a sum.
    measurement_fields : tuple of {"quality", "source_flag"}, optional
        Additional ``Measurement`` fields the dataset fills.
    content_form : str or None, optional
        Key of ``CONTENT_FORMS`` (``imgwtools.store.content``) of the
        dataset's files; None when only the bytes identify the content.
    volatile_fields : tuple of str, optional
        Volatile fields of ``content_form``; empty without a form.
    title_en : str, optional
        English title of the dataset, e.g. ``"Daily hydrological data"``.
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
    update_signal: Literal["http", "listing", "none"]
    license: License
    legacy_alias: str | None
    in_store: bool
    provider: str = "IMGW-PIB"
    archive_scope: Literal["country", "station_year", "station_element"] = "country"
    variable_notes: Mapping[str, str] = field(default_factory=dict)
    measurement_fields: tuple[Literal["quality", "source_flag"], ...] = ()
    content_form: str | None = None
    volatile_fields: tuple[str, ...] = ()
    title_en: str = ""


@dataclass(frozen=True)
class ArchiveFile:
    """
    Single physical source file (ZIP archive, CSV or JSON file).

    Attributes
    ----------
    dataset : str
        Full key of the dataset the file belongs to.
    server_path : str
        File path relative to the provider's ``base_url``.
    url : str
        Full download URL.
    year : int or None
        Archive year (hydrological or calendar per ``year_type``); for a
        meteorological monthly archive covering a multi-year folder, the
        first year of the folder; None for station lists and files without
        a year (ČHMÚ meteorological files cover the station's history).
    month : int or None
        Month of a monthly file (for hydrological data 1 = November of the
        previous year, 12 = October); None for yearly files.
    param : str or None
        Parameter of a semi-annual archive (``"H"``, ``"Q"`` or ``"T"``) or
        the element of a ČHMÚ meteorological file (``"SRA"``, ``"T"``,
        ``"TMA"``, ``"TMI"``), None otherwise.
    year_type : {"hydrological", "calendar", "none"}
        Year numbering of ``year``.
    period_start : date or None
        First calendar day covered by the file; None for station lists and
        files without a year.
    period_end : date or None
        Last calendar day covered by the file; None for station lists and
        files without a year.
    station_code : str or None, optional
        Station of a per-station file (WIGOS identifier), None for files
        covering the whole country.
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
    station_code: str | None = None


_LICENSE = License(
    "IMGW-PIB",
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy",
    "https://danepubliczne.imgw.pl/regulations",
)
_CHMI_LICENSE = License(
    "CC-BY-4.0",
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, "
    "licencja CC BY 4.0",
    "https://creativecommons.org/licenses/by/4.0/",
    "https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti",
)
# Canonical form of the ČHMÚ JSON files (envelope fields regenerated on every
# publication); equal to imgwtools.store.content.CONTENT_FORMS["chmi-json/1"].
_CHMI_JSON = "chmi-json/1"
_CHMI_VOLATILE = ("zaznamID", "datumVytvoreni")

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
        title_en="Daily hydrological data",
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
        title_en="Monthly hydrological data",
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
        title_en="Semi-annual and annual hydrological data",
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
        title_en="Daily meteorological data from climate stations",
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
        title_en="Daily meteorological data from precipitation stations",
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
        title_en="List of hydrological stations",
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
        title_en="List of meteorological stations",
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
        title_en="Probable maximum precipitation PMAXTP",
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
        title_en="Daily hydrological phenomena",
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
        title_en="Monthly meteorological data from climate stations",
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
        title_en="Monthly meteorological data from precipitation stations",
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
        title_en="Monthly meteorological data from synoptic stations",
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
        title_en="Meteorological data at observation times from climate stations",
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
    DatasetDescriptor(
        key="cz.chmi.hydro_daily",
        slug="chmi_hydro_daily",
        kind="hydro",
        title="ČHMÚ — dane hydrologiczne dobowe (H, Q, T)",
        title_en="ČHMÚ — daily hydrological data (H, Q, T)",
        server_dir="hydrology/historical/data/daily",
        parser="parse_chmi_hydro_daily",
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="day",
        year_type="calendar",
        first_year=1887,
        update_signal="listing",
        license=_CHMI_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMI",
        archive_scope="station_year",
        variable_notes={
            "H": "Średni dobowy stan wody (HD); data = dzień z DT (…T00:00:00Z)",
            "Q": "Średni dobowy przepływ (QD), równy średniej 24 przepływów "
            "godzinowych o etykietach 00–23Z tej daty (doba według etykiet Z; "
            "UTC albo stały SEČ — niepotwierdzone przez ČHMÚ)",
            "T": "Średnia dobowa temperatura wody (TD)",
        },
        content_form=_CHMI_JSON,
        volatile_fields=_CHMI_VOLATILE,
    ),
    DatasetDescriptor(
        key="cz.chmi.meteo_daily",
        slug="chmi_meteo_daily",
        kind="meteo",
        title="ČHMÚ — dane meteorologiczne dobowe (opad, temperatura powietrza)",
        title_en="ČHMÚ — daily meteorological data (precipitation, air temperature)",
        server_dir="meteorology/climate/historical_csv/data/daily",
        parser="parse_chmi_meteo_daily",
        variables={"P": "mm", "Tmean": "degC", "Tmax": "degC", "Tmin": "degC"},
        time_unit="day",
        year_type="calendar",
        first_year=None,
        update_signal="listing",
        license=_CHMI_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMI",
        archive_scope="station_element",
        variable_notes={
            "P": "Suma opadu (SRA) od terminu porannego (06:00Z) dnia D do terminu "
            "porannego dnia D+1, przypisana do D",
            "Tmean": "Średnia dobowa temperatura powietrza (T, AVG) = "
            "(T06 + T13 + 2·T20)/4 z terminów UTC dnia D",
            "Tmax": "Maksymalna temperatura powietrza (TMA) okresu "
            "(D−1 20:00, D 20:00] UTC, przypisana do D",
            "Tmin": "Minimalna temperatura powietrza (TMI) okresu "
            "(D−1 20:00, D 20:00] UTC, przypisana do D",
        },
        measurement_fields=("quality", "source_flag"),
    ),
    DatasetDescriptor(
        key="cz.chmi.hydro_stations",
        slug="chmi_hydro_stations",
        kind="hydro",
        title="ČHMÚ — wykaz stacji hydrologicznych",
        title_en="ČHMÚ — list of hydrological stations",
        server_dir="hydrology/historical/metadata",
        parser="parse_chmi_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_CHMI_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMI",
        content_form=_CHMI_JSON,
        volatile_fields=_CHMI_VOLATILE,
    ),
    DatasetDescriptor(
        key="cz.chmi.meteo_stations",
        slug="chmi_meteo_stations",
        kind="meteo",
        title="ČHMÚ — wykaz stacji meteorologicznych",
        title_en="ČHMÚ — list of meteorological stations",
        server_dir="meteorology/climate/historical/metadata",
        parser="parse_chmi_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_CHMI_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMI",
        content_form=_CHMI_JSON,
        volatile_fields=_CHMI_VOLATILE,
    ),
)
_PROVIDERS = (
    ProviderDescriptor(
        id="IMGW-PIB",
        short_name="IMGW-PIB",
        name="Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy",
        country="PL",
        key_prefix="pl.imgw",
        base_url=f"{IMGW_PUBLIC_DATA_URL}/",
        license=_LICENSE,
        processed_attribution="Dane Instytutu Meteorologii i Gospodarki Wodnej – "
        "Państwowego Instytutu Badawczego zostały przetworzone",
        notice="Do użytku prywatnego i badawczego; inne zastosowania wymagają "
        "sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.",
        station_code_pattern=r"^[0-9]{9}$",
        datasets=tuple(item.key for item in _DATASETS if item.provider == "IMGW-PIB"),
    ),
    ProviderDescriptor(
        id="CHMI",
        short_name="ČHMÚ",
        name="Český hydrometeorologický ústav",
        country="CZ",
        key_prefix="cz.chmi",
        base_url="https://opendata.chmi.cz/",
        license=_CHMI_LICENSE,
        processed_attribution="Dane ČHMÚ zostały przetworzone (normalizacja i "
        "zmiana formatu)",
        notice="Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany i użycie komercyjne "
        "pod warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian.",
        station_code_pattern=rf"^{_WIGOS_CODE}$",
        datasets=tuple(item.key for item in _DATASETS if item.provider == "CHMI"),
    ),
)
# Lookup by id and by key prefix.
_PROVIDER_BY_NAME = {
    name: provider
    for provider in _PROVIDERS
    for name in (provider.key_prefix, provider.id)
}
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
        message("datasets.meteo_dobowe_synop_archives_published"),
    ),
    "meteo/terminowe/synop": (
        "per_station",
        message("datasets.meteo_terminowe_synop_archives_published"),
    ),
    "meteo/terminowe/opad": (
        "not_published",
        message("datasets.meteo_terminowe_opad_data_do"),
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


def providers() -> tuple[ProviderDescriptor, ...]:
    """
    Return the provider registry.

    Returns
    -------
    tuple of ProviderDescriptor
        ``IMGW-PIB``, then ``CHMI`` (a fixed order).
    """
    return _PROVIDERS


def get_provider(provider: str, /) -> ProviderDescriptor:
    """
    Find a provider by its identifier or dataset key prefix.

    Parameters
    ----------
    provider : str
        Identifier (``"IMGW-PIB"``, ``"CHMI"``) or key prefix
        (``"pl.imgw"``, ``"cz.chmi"``).

    Returns
    -------
    ProviderDescriptor
        Descriptor of the provider.

    Raises
    ------
    IMGWValidationError
        If the value names no provider (``details.allowed`` lists the
        identifiers).
    """
    if isinstance(provider, str) and provider in _PROVIDER_BY_NAME:
        return _PROVIDER_BY_NAME[provider]
    allowed = [item.id for item in _PROVIDERS]
    raise IMGWValidationError(
        message(
            "datasets.unknown_data_provider_allowed",
            provider=provider,
            allowed=", ".join(allowed),
        ),
        details={
            "option": "provider",
            "value": provider if isinstance(provider, str) else repr(provider),
            "allowed": allowed,
        },
    )


def datasets(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    provider: str | None = None,
) -> tuple[DatasetDescriptor, ...]:
    """
    Return the dataset registry, optionally limited to a family and a provider.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Data family to keep; None keeps every family (PMAXTP has no family
        and is returned only then).
    provider : str or None, optional
        Provider identifier or key prefix to keep (see `get_provider`); None
        keeps all providers.

    Returns
    -------
    tuple of DatasetDescriptor
        Descriptors in registry order: the 13 IMGW-PIB datasets (the eight of
        the store, then the five download-only ones), then the four ČHMÚ
        datasets.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is not ``"hydro"``, ``"meteo"`` or None, or ``provider``
        names no provider.
    """
    if kind is not None and kind not in ("hydro", "meteo"):
        raise IMGWValidationError(
            message("datasets.invalid_kind_dataset_allowed_hydro", kind=kind),
            details={"option": "kind", "value": kind, "allowed": ["hydro", "meteo"]},
        )
    owner = None if provider is None else get_provider(provider).id
    if kind is None and owner is None:
        return _DATASETS
    return tuple(
        descriptor
        for descriptor in _DATASETS
        if (kind is None or descriptor.kind == kind)
        and (owner is None or descriptor.provider == owner)
    )


def get_dataset(dataset: str, /) -> DatasetDescriptor:
    """
    Find a dataset by its key, slug, legacy alias or renamed key.

    Parameters
    ----------
    dataset : str
        Full key (``"pl.imgw.hydro_daily"``), slug (``"hydro_daily"``) or
        legacy alias (``"hydro/dobowe"``), tried in this order, then a renamed
        key of ``DATASET_KEY_ALIASES``.

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
        if (
            descriptor := _BY_NAME.get(DATASET_KEY_ALIASES.get(dataset, ""))
        ) is not None:
            return descriptor
        if dataset in _UNSUPPORTED:
            reason, text = _UNSUPPORTED[dataset]
            raise IMGWValidationError(
                text,
                details={
                    "option": "dataset",
                    "value": dataset,
                    "reason": reason,
                    "allowed": _ALLOWED,
                },
            )
    raise IMGWValidationError(
        message(
            "datasets.unknown_imgw_dataset_allowed_keys",
            dataset=dataset,
            allowed=", ".join(_ALLOWED),
        ),
        details={
            "option": "dataset",
            "value": dataset if isinstance(dataset, str) else repr(dataset),
            "allowed": _ALLOWED,
        },
    )


def resolve_dataset_key(dataset: str, /) -> str | None:
    """
    Resolve a stored dataset key to its current key.

    Parameters
    ----------
    dataset : str
        Dataset key as written, e.g. the ``dataset`` field of a sidecar.

    Returns
    -------
    str or None
        The key itself if it is current (a registry key or the station
        catalog key of a provider, e.g. ``CATALOG_DATASET`` or
        ``"cz.chmi.stations"``), the current key of a renamed key from
        ``DATASET_KEY_ALIASES``, None for a key IMGWTools does not know
        (slugs and legacy aliases are not keys and give None too).
    """
    key = DATASET_KEY_ALIASES.get(dataset, dataset)
    if key in _CATALOG_DATASETS.values() or any(item.key == key for item in _DATASETS):
        return key
    return None


def _license_document(license_: License, /) -> dict[str, str]:
    """
    The ``license`` object of a sidecar.

    ``terms_url`` is written only when set, so IMGW-PIB sidecars keep the
    bytes they had before the field existed.

    Parameters
    ----------
    license_ : License
        License of a provider or dataset.

    Returns
    -------
    dict of str to str
        ``id``, ``attribution``, ``url`` and, when set, ``terms_url``.
    """
    document = {
        "id": license_.id,
        "attribution": license_.attribution,
        "url": license_.url,
    }
    if license_.terms_url is not None:
        document["terms_url"] = license_.terms_url
    return document


def _items(value: object, option: str) -> list[int | str]:
    """Flatten a scalar, comma-separated text or iterable into list items."""
    if isinstance(value, int | str):
        raw: list[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, bytes | Mapping):
        raw = list(value)
    else:
        raise IMGWValidationError(
            message(
                "datasets.option_must_number_text_list", option=option, value=value
            ),
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
                message("datasets.invalid_value_option", option=option, item=item),
                details={"option": option, "value": repr(item)},
            )
    if not items or "" in items:
        raise IMGWValidationError(
            message("datasets.option_needs_non_empty_list", option=option),
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
                message(
                    "datasets.invalid_year_range_years_option", option=option, item=item
                ),
                details={"option": option, "value": item},
            )
        if not 1 <= start <= end <= 9999:
            raise IMGWValidationError(
                message(
                    "datasets.invalid_range_years_option", option=option, item=item
                ),
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
                    message(
                        "datasets.option_must_contain_integers",
                        option=option,
                        item=item,
                    ),
                    details={"option": option, "value": item},
                )
            item = int(item)
        if not 1 <= item <= 12:
            raise IMGWValidationError(
                message("datasets.months_must_range_1_12"),
                details={"option": option, "value": item},
            )
        months.add(item)
    return tuple(sorted(months))


def _parse_params(
    params: Iterable[Literal["H", "Q", "T"]], dataset: DatasetDescriptor
) -> tuple[str, ...]:
    if dataset.key != "pl.imgw.hydro_semiannual":
        raise IMGWValidationError(
            message("datasets.option_params_applies_only_dataset", key=dataset.key),
            details={"option": "params", "value": dataset.key},
        )
    items = [
        part.strip()
        for item in ([params] if isinstance(params, str) else params)
        for part in (item.split(",") if isinstance(item, str) else [item])
    ]
    if not items or any(item not in _PARAMS for item in items):
        raise IMGWValidationError(
            message("datasets.invalid_semi_annual_parameters_allowed", items=items),
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
    station_code: str | None = None,
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
        get_provider(descriptor.provider).base_url + path,
        year,
        month,
        param,
        descriptor.year_type if year is not None else "none",
        start,
        end,
        station_code,
    )


def archive_files(
    dataset: str,
    /,
    *,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    params: Iterable[Literal["H", "Q", "T"]] | None = None,
    stations: Iterable[str] | None = None,
) -> tuple[ArchiveFile, ...]:
    """
    Enumerate distinct physical source files without accessing the network.

    IMGW-PIB archives cover the whole country: months select only physically
    monthly files (daily hydro before 2023, daily and hourly meteo from
    2001); for yearly archives one file per year is returned, and a
    meteorological monthly archive is returned once per folder (five-year
    folders until 2000). ČHMÚ files cover one station: one file per station
    and calendar year (``cz.chmi.hydro_daily``) or four files per station
    with its whole history, one per element SRA, T, TMA, TMI
    (``cz.chmi.meteo_daily``). Years are not limited by the current year;
    the result lists candidates, and whether a file is published is decided
    by the server (its listing or a 404 answer).

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of one of the twelve archive datasets (all
        but the station lists and PMAXTP).
    years : YearsArg or None, optional
        Archive years (hydrological or calendar per the dataset), also as
        ranges ``"a-b"``; at least ``first_year`` of the dataset. Required
        except for ``cz.chmi.meteo_daily``, which rejects it.
    months : MonthsArg or None, optional
        Months 1-12 (for hydrological data 1 = November of the previous
        year); None selects all months. Rejected for ČHMÚ datasets.
    params : iterable of {"H", "Q", "T"} or None, optional
        Parameters of ``pl.imgw.hydro_semiannual`` to keep; None keeps all
        three. Rejected for other datasets.
    stations : iterable of str or None, optional
        Station codes of the dataset's provider (duplicates are dropped).
        Required for ČHMÚ datasets, rejected for IMGW-PIB datasets.

    Returns
    -------
    tuple of ArchiveFile
        IMGW-PIB archives ordered by year, then by month or parameter; ČHMÚ
        files ordered by station code, then by year or element.

    Raises
    ------
    IMGWValidationError
        If the dataset is unknown or has no archives (station lists,
        PMAXTP), a required option is missing or a rejected one is given,
        the years or months are empty, malformed or out of range, a station
        code does not follow the provider's grammar, or ``params`` is
        invalid; ``details.option`` names the option.
    """
    descriptor = get_dataset(dataset)
    if descriptor.server_dir is None or descriptor.time_unit == "station_list":
        raise IMGWValidationError(
            message("datasets.dataset_has_no_annual_archives", key=descriptor.key),
            details={"option": "dataset", "value": descriptor.key},
        )
    if descriptor.archive_scope == "country":
        return _country_archives(
            descriptor, years=years, months=months, params=params, stations=stations
        )
    return _station_archives(
        descriptor, years=years, months=months, params=params, stations=stations
    )


def _minimum_year(years: tuple[int, ...], descriptor: DatasetDescriptor) -> None:
    """Reject years before ``first_year`` of the dataset (``details.minimum``)."""
    if descriptor.first_year is not None and years[0] < descriptor.first_year:
        raise IMGWValidationError(
            message(
                "datasets.invalid_years_dataset_first_year",
                key=descriptor.key,
                first_year=descriptor.first_year,
            ),
            details={
                "option": "years",
                "value": list(years),
                "minimum": descriptor.first_year,
            },
        )


def _country_archives(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[ArchiveFile, ...]:
    """Archives of an IMGW-PIB dataset covering the whole country."""
    key = descriptor.key
    if stations is not None:
        raise IMGWValidationError(
            message("datasets.archives_dataset_cover_whole_country", key=key),
            details={"option": "stations", "value": key},
        )
    if years is None:
        raise IMGWValidationError(
            message("datasets.dataset_needs_option_years_years", key=key),
            details={"option": "years", "value": None},
        )
    selected_years = parse_years(years)
    selected_months = (
        parse_months(months) if months is not None else tuple(range(1, 13))
    )
    selected_params = (
        _parse_params(params, descriptor) if params is not None else _PARAMS
    )
    _minimum_year(selected_years, descriptor)
    first_year = descriptor.first_year or selected_years[0]

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
                year, first_year=first_year, first_folder_end=first_folder_end
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


def _parse_stations(
    stations: Iterable[str], provider: ProviderDescriptor
) -> tuple[str, ...]:
    """Station codes of the provider's grammar, sorted, without duplicates."""
    if isinstance(stations, str) or not isinstance(stations, Iterable):
        raise IMGWValidationError(
            message("datasets.option_stations_must_list_station"),
            details={"option": "stations", "value": str(stations)},
        )
    items = list(stations)
    pattern = re.compile(provider.station_code_pattern)
    invalid = [
        str(item)
        for item in items
        if not isinstance(item, str) or not pattern.fullmatch(item)
    ]
    if not items or invalid:
        raise IMGWValidationError(
            message(
                "datasets.invalid_station_codes_expected_least",
                short_name=provider.short_name,
                codes=", ".join(invalid) or message("common.none"),
                station_code_pattern=provider.station_code_pattern,
            ),
            details={"option": "stations", "value": invalid},
        )
    return tuple(sorted(set(items)))


def _station_archives(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[ArchiveFile, ...]:
    """Per-station files of a ČHMÚ dataset (station × year or station × element)."""
    key = descriptor.key
    provider = get_provider(descriptor.provider)
    if months is not None:
        raise IMGWValidationError(
            message(
                "datasets.option_months_does_not_apply",
                key=key,
                short_name=provider.short_name,
            ),
            details={"option": "months", "value": key},
        )
    if params is not None:
        _parse_params(params, descriptor)
    if stations is None:
        raise IMGWValidationError(
            message(
                "datasets.dataset_needs_option_stations_station",
                key=key,
                short_name=provider.short_name,
            ),
            details={"option": "stations", "value": None},
        )
    codes = _parse_stations(stations, provider)
    directory = descriptor.server_dir
    if descriptor.archive_scope == "station_element":
        if years is not None:
            raise IMGWValidationError(
                message(
                    "datasets.files_dataset_cover_whole_history",
                    short_name=provider.short_name,
                    key=key,
                ),
                details={"option": "years", "value": key},
            )
        return tuple(
            _archive(
                descriptor,
                f"{directory}/{group}/dly-{code}-{element}.csv",
                None,
                param=element,
                station_code=code,
            )
            for code in codes
            for element, group in _CHMI_ELEMENT_GROUPS.items()
        )
    if years is None:
        raise IMGWValidationError(
            message("datasets.dataset_needs_option_years_without", key=key),
            details={"option": "years", "value": None},
        )
    selected_years = parse_years(years)
    _minimum_year(selected_years, descriptor)
    return tuple(
        _archive(
            descriptor,
            f"{directory}/H_{code}_DQ_{year}.json",
            year,
            station_code=code,
        )
        for code in codes
        for year in selected_years
    )


# Station list file of each station-list dataset.
_STATION_LIST_FILES = {
    "pl.imgw.hydro_stations": "lista_stacji_hydro.csv",
    "pl.imgw.meteo_stations": "wykaz_stacji.csv",
    "cz.chmi.hydro_stations": "meta1.json",
    "cz.chmi.meteo_stations": "meta1.json",
}


def station_source_files(
    *, provider: str = "IMGW-PIB"
) -> tuple[ArchiveFile, ArchiveFile]:
    """
    Return the two station list sources of a provider as archive descriptors.

    Parameters
    ----------
    provider : str, optional
        Provider identifier or key prefix (see `get_provider`).

    Returns
    -------
    tuple of (ArchiveFile, ArchiveFile)
        Hydrological and meteorological station lists, with ``year=None``
        and ``year_type="none"``: for IMGW-PIB ``lista_stacji_hydro.csv``
        and ``wykaz_stacji.csv``, for ČHMÚ the two ``historical`` metadata
        files ``meta1.json``.

    Raises
    ------
    IMGWValidationError
        If ``provider`` names no provider.
    """
    owner = get_provider(provider).id
    hydro, meteo = (
        next(
            item
            for item in _DATASETS
            if item.provider == owner
            and item.time_unit == "station_list"
            and item.kind == kind
        )
        for kind in ("hydro", "meteo")
    )
    return (
        _archive(hydro, f"{hydro.server_dir}/{_STATION_LIST_FILES[hydro.key]}", None),
        _archive(meteo, f"{meteo.server_dir}/{_STATION_LIST_FILES[meteo.key]}", None),
    )


def _archive_from_path(dataset: str, server_path: str, /) -> ArchiveFile | None:
    """
    Recreate the `ArchiveFile` of a server path offline (reverse of `archive_files`).

    Used for stored versions, plans and server listings: the descriptor equals
    the one `archive_files` (or `station_source_files`) gives for the path.

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of the dataset the path should belong to.
    server_path : str
        File path relative to the provider's ``base_url``.

    Returns
    -------
    ArchiveFile or None
        Descriptor of the file, or None if the path is no file of the
        dataset (e.g. another name in a listing).

    Raises
    ------
    IMGWValidationError
        If ``dataset`` names no dataset.
    """
    descriptor = get_dataset(dataset)
    directory, _, name = server_path.rpartition("/")
    if descriptor.time_unit == "station_list":
        return next(
            (
                item
                for item in station_source_files(provider=descriptor.provider)
                if item.dataset == descriptor.key and item.server_path == server_path
            ),
            None,
        )
    if descriptor.server_dir is None:
        return None
    if descriptor.archive_scope == "station_year":
        hydro = _CHMI_HYDRO_FILE.fullmatch(name)
        if hydro is None or directory != descriptor.server_dir:
            return None
        year = int(hydro[2])
        if descriptor.first_year is not None and year < descriptor.first_year:
            return None
        return archive_files(descriptor.key, stations=[hydro[1]], years=[year])[0]
    if descriptor.archive_scope == "station_element":
        meteo = _CHMI_METEO_FILE.fullmatch(name)
        if meteo is None or directory != (
            f"{descriptor.server_dir}/{_CHMI_ELEMENT_GROUPS[meteo[2]]}"
        ):
            return None
        return next(
            item
            for item in archive_files(descriptor.key, stations=[meteo[1]])
            if item.param == meteo[2]
        )
    parent, _, folder = directory.rpartition("/")
    years = _FOLDER.fullmatch(folder)
    if years is None or parent != descriptor.server_dir:
        return None
    first = max(int(years[1]), descriptor.first_year or 1)
    for year in range(first, int(years[2] or years[1]) + 1):
        for item in archive_files(descriptor.key, years=(year,)):
            if item.server_path == server_path:
                return item
    return None
