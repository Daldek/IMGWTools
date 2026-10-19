"""Offline checks for source registry and physical archive enumeration."""

import importlib
import re
from datetime import date

import pytest

from imgwtools.datasets import (
    CATALOG_DATASET,
    DATASET_KEY_ALIASES,
    DATASET_KEY_PATTERN,
    archive_files,
    datasets,
    get_dataset,
    parse_months,
    parse_years,
    resolve_dataset_key,
    station_source_files,
)
from imgwtools.exceptions import IMGWValidationError
from imgwtools.urls import IMGW_PUBLIC_DATA_URL

# ``imgwtools.datasets`` as a module: the package attribute is the ``datasets`` function.
DATASETS_MODULE = importlib.import_module("imgwtools.datasets")
_BASE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"

# (key, kind, in_store, time_unit, year_type, first_year, legacy_alias) — spec §13.4.
_REGISTRY = [
    ("pl.imgw.hydro_daily", "hydro", True, "day", "hydrological", 1951, "hydro/dobowe"),
    (
        "pl.imgw.hydro_monthly",
        "hydro",
        True,
        "month",
        "hydrological",
        1951,
        "hydro/miesieczne",
    ),
    (
        "pl.imgw.hydro_semiannual",
        "hydro",
        True,
        "half_year",
        "hydrological",
        1951,
        "hydro/polroczne_i_roczne",
    ),
    (
        "pl.imgw.meteo_climate_daily",
        "meteo",
        True,
        "day",
        "calendar",
        1951,
        "meteo/dobowe/klimat",
    ),
    (
        "pl.imgw.meteo_precip_daily",
        "meteo",
        True,
        "day",
        "calendar",
        1950,
        "meteo/dobowe/opad",
    ),
    ("pl.imgw.hydro_stations", "hydro", True, "station_list", "none", None, None),
    ("pl.imgw.meteo_stations", "meteo", True, "station_list", "none", None, None),
    ("pl.imgw.pmaxtp", None, True, "cell", "none", None, None),
    ("pl.imgw.hydro_phenomena", "hydro", False, "day", "hydrological", 1951, None),
    (
        "pl.imgw.meteo_climate_monthly",
        "meteo",
        False,
        "month",
        "calendar",
        1951,
        "meteo/miesieczne/klimat",
    ),
    (
        "pl.imgw.meteo_precip_monthly",
        "meteo",
        False,
        "month",
        "calendar",
        1950,
        "meteo/miesieczne/opad",
    ),
    (
        "pl.imgw.meteo_synop_monthly",
        "meteo",
        False,
        "month",
        "calendar",
        1960,
        "meteo/miesieczne/synop",
    ),
    (
        "pl.imgw.meteo_climate_terms",
        "meteo",
        False,
        "term",
        "calendar",
        1951,
        "meteo/terminowe/klimat",
    ),
]
# ČHMÚ datasets after the 13 IMGW-PIB ones (spec 2026-10-18 §2.2).
_CHMI_KEYS = [
    "cz.chmi.hydro_daily",
    "cz.chmi.meteo_daily",
    "cz.chmi.hydro_stations",
    "cz.chmi.meteo_stations",
]


def test_registry_has_thirteen_imgw_descriptors_with_spec_fields():
    descriptors = datasets(provider="IMGW-PIB")
    assert [
        (
            d.key,
            d.kind,
            d.in_store,
            d.time_unit,
            d.year_type,
            d.first_year,
            d.legacy_alias,
        )
        for d in descriptors
    ] == _REGISTRY
    assert all(entry.key == f"pl.imgw.{entry.slug}" for entry in descriptors)
    assert all(entry.title and entry.license.id == "IMGW-PIB" for entry in descriptors)
    assert all(
        entry.parser is None and not entry.variables
        for entry in descriptors
        if not entry.in_store
    )


def test_datasets_kind_filter():
    meteo = datasets(kind="meteo")
    assert [d.key for d in meteo] == [
        row[0] for row in _REGISTRY if row[1] == "meteo"
    ] + ["cz.chmi.meteo_daily", "cz.chmi.meteo_stations"]
    assert [d.key for d in datasets(kind="hydro")] == [
        row[0] for row in _REGISTRY if row[1] == "hydro"
    ] + ["cz.chmi.hydro_daily", "cz.chmi.hydro_stations"]
    assert len(meteo) == 9
    with pytest.raises(IMGWValidationError) as exc:
        datasets(kind="pmaxtp")
    assert exc.value.code == "validation_error"


@pytest.mark.parametrize("key", [row[0] for row in _REGISTRY if row[-1] is not None])
def test_get_dataset_resolves_key_slug_and_legacy_alias(key):
    descriptor = get_dataset(key)
    assert get_dataset(descriptor.slug) is descriptor
    assert descriptor.legacy_alias is not None
    assert get_dataset(descriptor.legacy_alias) is descriptor
    assert descriptor.key == key


def test_get_dataset_unknown_lists_allowed_keys():
    with pytest.raises(IMGWValidationError) as exc:
        get_dataset("hydro/tygodniowe")
    assert exc.value.code == "validation_error"
    assert exc.value.details["allowed"] == [row[0] for row in _REGISTRY] + _CHMI_KEYS


def test_every_dataset_key_follows_the_key_convention():
    # IMGW-20 criterion 1: the consumer's pattern, checked on the whole registry.
    assert DATASET_KEY_PATTERN == r"^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$"
    keys = [d.key for d in datasets()] + [CATALOG_DATASET]
    for key in keys:
        assert re.fullmatch(DATASET_KEY_PATTERN, key), key
        assert resolve_dataset_key(key) == key
    for old, current in DATASET_KEY_ALIASES.items():
        assert re.fullmatch(DATASET_KEY_PATTERN, old), old
        assert old not in keys and current in keys, (old, current)


def test_renamed_key_resolves_to_the_current_key(monkeypatch):
    monkeypatch.setattr(
        DATASETS_MODULE,
        "DATASET_KEY_ALIASES",
        {"pl.imgw.hydro_day": "pl.imgw.hydro_daily"},
    )

    assert resolve_dataset_key("pl.imgw.hydro_day") == "pl.imgw.hydro_daily"
    assert get_dataset("pl.imgw.hydro_day") is get_dataset("pl.imgw.hydro_daily")
    assert resolve_dataset_key("pl.imgw.hydro_daily") == "pl.imgw.hydro_daily"
    # Unknown keys, slugs and legacy input words are not keys IMGWTools knows.
    for value in ("sk.shmu.hydro_daily", "hydro_daily", "hydro/dobowe"):
        assert resolve_dataset_key(value) is None


@pytest.mark.parametrize(
    ("alias", "reason"),
    [
        ("meteo/dobowe/synop", "per_station"),
        ("meteo/terminowe/synop", "per_station"),
        ("meteo/terminowe/opad", "not_published"),
    ],
)
def test_aliases_without_descriptor_explain_reason(alias, reason):
    with pytest.raises(IMGWValidationError) as exc:
        archive_files(alias, years=2023, months=1)
    assert exc.value.code == "validation_error"
    assert exc.value.details["reason"] == reason
    assert alias in str(exc.value)


# Golden URLs generated once from the removed build_hydro_url/build_meteo_url.
@pytest.mark.parametrize(
    ("dataset", "years", "months", "urls"),
    [
        (
            "pl.imgw.hydro_phenomena",
            2023,
            None,
            [f"{_BASE}/dane_hydrologiczne/dobowe/2023/zjaw_2023.zip"],
        ),
        (
            "meteo/miesieczne/klimat",
            [1955, 1995, 1991, 2023],
            None,
            [
                f"{_BASE}/dane_meteorologiczne/miesieczne/klimat/1951_1955/1951_1955_m_k.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/klimat/1991_1995/1991_1995_m_k.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/klimat/2023/2023_m_k.zip",
            ],
        ),
        (
            "meteo/miesieczne/opad",
            [1950, 1955, 1995, 2023],
            [2],
            [
                f"{_BASE}/dane_meteorologiczne/miesieczne/opad/1950_1955/1950_1955_m_o.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/opad/1991_1995/1991_1995_m_o.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/opad/2023/2023_m_o.zip",
            ],
        ),
        (
            "pl.imgw.meteo_synop_monthly",
            "1960-1966,1995,2023",
            None,
            [
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/1960_1965/1960_1965_m_s.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/1966_1970/1966_1970_m_s.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/1991_1995/1991_1995_m_s.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/2023/2023_m_s.zip",
            ],
        ),
        (
            "meteo/terminowe/klimat",
            [1995, 2001],
            [1],
            [
                f"{_BASE}/dane_meteorologiczne/terminowe/klimat/1991_1995/1995_k.zip",
                f"{_BASE}/dane_meteorologiczne/terminowe/klimat/2001/2001_01_k.zip",
            ],
        ),
    ],
)
def test_download_only_datasets_match_legacy_urls(dataset, years, months, urls):
    files = archive_files(dataset, years=years, months=months)
    assert [item.url for item in files] == urls
    assert {item.dataset for item in files} == {get_dataset(dataset).key}


def test_meteo_monthly_folder_archive_covers_whole_folder():
    (archive,) = archive_files("pl.imgw.meteo_climate_monthly", years="1996-2000")
    assert (archive.year, archive.month) == (1996, None)
    assert (archive.period_start, archive.period_end) == (
        date(1996, 1, 1),
        date(2000, 12, 31),
    )


def test_synop_monthly_starts_in_1960():
    with pytest.raises(IMGWValidationError) as exc:
        archive_files("pl.imgw.meteo_synop_monthly", years=1955)
    assert exc.value.details["minimum"] == 1960


@pytest.mark.parametrize(
    ("years", "expected"),
    [
        (2024, [2024]),
        ("2020-2023", [2020, 2021, 2022, 2023]),
        ("2020,2022", [2020, 2022]),
        ([2020, "2022-2023"], [2020, 2022, 2023]),
        ((2023, "2023", " 2021-2021 "), [2021, 2023]),
    ],
)
def test_years_forms_give_same_files_as_int_lists(years, expected):
    assert parse_years(years) == tuple(expected)
    assert archive_files("pl.imgw.hydro_monthly", years=years) == archive_files(
        "pl.imgw.hydro_monthly", years=expected
    )


@pytest.mark.parametrize(
    "years", [[], "", "2023-2020", "0", "10000", "20x", [True], 2023.0, [None], "2020,"]
)
def test_invalid_years_raise_validation_error(years):
    with pytest.raises(IMGWValidationError) as exc:
        parse_years(years)
    assert exc.value.details["option"] == "years"


def test_months_forms():
    assert parse_months("3,1,1") == (1, 3)
    assert parse_months([12, "2"]) == (2, 12)
    assert parse_months(5) == (5,)
    for bad in (0, "13", "1-3", [], [True]):
        with pytest.raises(IMGWValidationError):
            parse_months(bad)


def test_params_narrow_semiannual_and_are_rejected_elsewhere():
    files = archive_files(
        "hydro/polroczne_i_roczne", years=2020, params=["T", "Q", "Q"]
    )
    assert [item.param for item in files] == ["Q", "T"]
    assert [
        item.param
        for item in archive_files("pl.imgw.hydro_semiannual", years=2020, params="H")
    ] == ["H"]
    with pytest.raises(IMGWValidationError) as exc:
        archive_files("pl.imgw.hydro_monthly", years=2020, params=["H"])
    assert exc.value.details["option"] == "params"
    for bad in ([], ["X"]):
        with pytest.raises(IMGWValidationError):
            archive_files("pl.imgw.hydro_semiannual", years=2020, params=bad)


def test_hydro_monthly_physical_archive_count_and_calendar_boundaries():
    archives = archive_files(
        "pl.imgw.hydro_daily", years=[2022, 2022, 2024, 2024], months=[1, 3, 3, 12]
    )
    assert [item.server_path.split("/")[-1] for item in archives] == [
        "codz_2022_01.zip",
        "codz_2022_03.zip",
        "codz_2022_12.zip",
        "codz_2024.zip",
    ]
    assert (archives[0].period_start, archives[0].period_end) == (
        date(2021, 11, 1),
        date(2021, 11, 30),
    )
    assert (archives[1].period_start, archives[1].period_end) == (
        date(2022, 1, 1),
        date(2022, 1, 31),
    )
    assert (archives[-1].period_start, archives[-1].period_end) == (
        date(2023, 11, 1),
        date(2024, 10, 31),
    )
    assert len(archive_files("pl.imgw.hydro_daily", years=[2022])) == 12
    assert len(archive_files("pl.imgw.hydro_daily", years=[2024])) == 1


def test_hydro_monthly_and_semiannual_are_distinct_files():
    monthly = archive_files("pl.imgw.hydro_monthly", years=[2024], months=[1, 12])
    semiannual = archive_files("pl.imgw.hydro_semiannual", years=[2024], months=[1, 12])
    assert [item.server_path.split("/")[-1] for item in monthly] == ["mies_2024.zip"]
    assert [item.param for item in semiannual] == ["H", "Q", "T"]
    assert [item.server_path.split("/")[-1] for item in semiannual] == [
        "polr_H_2024.zip",
        "polr_Q_2024.zip",
        "polr_T_2024.zip",
    ]


@pytest.mark.parametrize(
    ("dataset", "year", "filename", "folder"),
    [
        ("meteo_climate_daily", 1951, "1951_k.zip", "1951_1955"),
        ("meteo_climate_daily", 2000, "2000_k.zip", "1996_2000"),
        ("meteo_precip_daily", 1950, "1950_o.zip", "1950_1955"),
        ("meteo_precip_daily", 1955, "1955_o.zip", "1950_1955"),
        ("meteo_precip_daily", 2000, "2000_o.zip", "1996_2000"),
        ("meteo_climate_daily", 2001, "2001_02_k.zip", "2001"),
        ("meteo_precip_daily", 2001, "2001_02_o.zip", "2001"),
    ],
)
def test_meteo_archive_layout(dataset, year, filename, folder):
    files = archive_files(f"pl.imgw.{dataset}", years=[year], months=[2, 2])
    assert len(files) == (1 if year <= 2000 else 1)
    assert files[0].server_path.endswith(f"/{folder}/{filename}")
    assert files[0].year_type == "calendar"


def test_calendar_leap_and_monthly_filter():
    files = archive_files("pl.imgw.meteo_precip_daily", years=[2004], months=[2])
    assert (files[0].period_start, files[0].period_end) == (
        date(2004, 2, 1),
        date(2004, 2, 29),
    )
    assert len(archive_files("pl.imgw.meteo_precip_daily", years=[2001])) == 12


def test_station_lists_are_real_csv_sources():
    hydro, meteo = station_source_files()
    assert hydro.server_path == "dane_hydrologiczne/lista_stacji_hydro.csv"
    assert meteo.server_path == "dane_meteorologiczne/wykaz_stacji.csv"
    for archive in (hydro, meteo):
        assert archive.year is archive.month is archive.param is None
        assert archive.year_type == "none"
        assert archive.period_start is archive.period_end is None
        assert archive.url == f"{IMGW_PUBLIC_DATA_URL}/{archive.server_path}"


@pytest.mark.parametrize(
    "dataset, years, months",
    [
        ("pl.imgw.meteo_stations", [2024], None),
        ("pl.imgw.pmaxtp", [2024], None),
        ("pl.imgw.hydro_daily", [1950], None),
        ("pl.imgw.meteo_climate_daily", [1950], None),
        ("pl.imgw.hydro_daily", [2022], [13]),
        ("pl.imgw.meteo_precip_daily", [2024], []),
        ("pl.imgw.hydro_phenomena", [1950], None),
    ],
)
def test_invalid_choices_raise_validation_error(dataset, years, months):
    with pytest.raises(IMGWValidationError):
        archive_files(dataset, years=years, months=months)
