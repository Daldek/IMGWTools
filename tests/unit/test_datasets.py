"""Offline checks for source registry and physical archive enumeration."""

from datetime import date

import pytest

from imgwtools.datasets import (
    archive_files,
    datasets,
    get_dataset,
    station_source_files,
)
from imgwtools.exceptions import IMGWValidationError
from imgwtools.urls import IMGW_PUBLIC_DATA_URL


def test_registry_namespaces_and_license():
    descriptors = datasets()
    assert len(descriptors) == 8
    assert len({entry.key for entry in descriptors}) == 8
    assert all(entry.key == f"pl.imgw.{entry.slug}" for entry in descriptors)
    assert get_dataset("pl.imgw.hydro_daily").license.id == "IMGW-PIB"
    with pytest.raises(IMGWValidationError):
        get_dataset("hydro_daily")


def test_hydro_monthly_physical_archive_count_and_calendar_boundaries():
    archives = archive_files("pl.imgw.hydro_daily", years=[2022, 2022, 2024, 2024], months=[1, 3, 3, 12])
    assert [item.server_path.split("/")[-1] for item in archives] == [
        "codz_2022_01.zip", "codz_2022_03.zip", "codz_2022_12.zip", "codz_2024.zip"
    ]
    assert (archives[0].period_start, archives[0].period_end) == (date(2021, 11, 1), date(2021, 11, 30))
    assert (archives[1].period_start, archives[1].period_end) == (date(2022, 1, 1), date(2022, 1, 31))
    assert (archives[-1].period_start, archives[-1].period_end) == (date(2023, 11, 1), date(2024, 10, 31))
    assert len(archive_files("pl.imgw.hydro_daily", years=[2022])) == 12
    assert len(archive_files("pl.imgw.hydro_daily", years=[2024])) == 1


def test_hydro_monthly_and_semiannual_are_distinct_files():
    monthly = archive_files("pl.imgw.hydro_monthly", years=[2024], months=[1, 12])
    semiannual = archive_files("pl.imgw.hydro_semiannual", years=[2024], months=[1, 12])
    assert [item.server_path.split("/")[-1] for item in monthly] == ["mies_2024.zip"]
    assert [item.param for item in semiannual] == ["H", "Q", "T"]
    assert [item.server_path.split("/")[-1] for item in semiannual] == [
        "polr_H_2024.zip", "polr_Q_2024.zip", "polr_T_2024.zip"
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
    assert (files[0].period_start, files[0].period_end) == (date(2004, 2, 1), date(2004, 2, 29))
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


@pytest.mark.parametrize("dataset, years, months", [
    ("pl.imgw.meteo_stations", [2024], None),
    ("pl.imgw.pmaxtp", [2024], None),
    ("pl.imgw.hydro_daily", [1950], None),
    ("pl.imgw.meteo_climate_daily", [1950], None),
    ("pl.imgw.hydro_daily", [2022], [13]),
    ("pl.imgw.meteo_precip_daily", [2024], []),
    ("hydro_daily", [2024], None),
])
def test_invalid_choices_raise_validation_error(dataset, years, months):
    with pytest.raises(IMGWValidationError):
        archive_files(dataset, years=years, months=months)
