"""Provider registry, ČHMÚ descriptors and per-station files (spec 2026-10-18 §2)."""

import re
from datetime import date

import pytest

from imgwtools.datasets import (
    STATION_CODE_PATTERN,
    ArchiveFile,
    DatasetDescriptor,
    License,
    _archive_from_path,
    archive_files,
    datasets,
    get_dataset,
    get_provider,
    providers,
    station_source_files,
)
from imgwtools.exceptions import IMGWValidationError
from imgwtools.store.content import CONTENT_FORMS

HYDRO = "cz.chmi.hydro_daily"
METEO = "cz.chmi.meteo_daily"
# Fictional codes: no published ČHMÚ code starts with 0-203-1-9 or 0-203-0-9.
A, B = "0-203-1-900001", "0-203-1-CB900003"
M = "0-203-0-90001"
CHMI_KEYS = [HYDRO, METEO, "cz.chmi.hydro_stations", "cz.chmi.meteo_stations"]


def test_providers_follow_the_registry_table():
    imgw, chmi = providers()
    assert (imgw.id, imgw.short_name, imgw.country, imgw.key_prefix) == (
        "IMGW-PIB",
        "IMGW-PIB",
        "PL",
        "pl.imgw",
    )
    assert imgw.name == (
        "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy"
    )
    assert imgw.base_url == (
        "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    )
    assert imgw.license.id == "IMGW-PIB" and imgw.license.terms_url is None
    assert imgw.processed_attribution == (
        "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
        "Badawczego zostały przetworzone"
    )
    assert imgw.station_code_pattern == "^[0-9]{9}$"
    assert (chmi.id, chmi.short_name, chmi.country, chmi.key_prefix) == (
        "CHMI",
        "ČHMÚ",
        "CZ",
        "cz.chmi",
    )
    assert chmi.name == "Český hydrometeorologický ústav"
    assert chmi.base_url == "https://opendata.chmi.cz/"
    assert chmi.license == License(
        "CC-BY-4.0",
        "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), "
        "https://opendata.chmi.cz, licencja CC BY 4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        "https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti",
    )
    assert chmi.processed_attribution == (
        "Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)"
    )
    assert chmi.notice == (
        "The CC BY 4.0 licence permits copying, changes and commercial use provided "
        "that the author ČHMÚ is credited, the licence is given and the changes are "
        "marked."
    )
    assert chmi.notice.localized("pl") == (
        "Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany i użycie komercyjne pod "
        "warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian."
    )
    assert chmi.station_code_pattern == "^0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}$"
    assert chmi.datasets == tuple(CHMI_KEYS)
    assert len(imgw.datasets) == 13


def test_license_notice_is_the_attribution_then_the_notice_in_the_language_asked():
    chmi = get_provider("CHMI")

    notice = chmi.license_notice()
    processed = chmi.license_notice(f"{chmi.license.attribution}. Changed")

    assert notice == f"{chmi.license.attribution}. {chmi.notice}"
    assert processed == f"{chmi.license.attribution}. Changed. {chmi.notice}"
    # The attribution keeps its wording; only the provider's notice is translated.
    assert notice.localized("pl") == (
        f"{chmi.license.attribution}. Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany "
        "i użycie komercyjne pod warunkiem uznania autorstwa ČHMÚ, podania licencji i "
        "oznaczenia zmian."
    )


def test_provider_lookup_by_id_or_key_prefix():
    assert get_provider("cz.chmi") is get_provider("CHMI")
    assert get_provider("pl.imgw") is get_provider("IMGW-PIB")
    for unknown in ("ČHMÚ", "chmi", "sk.shmu", None):
        with pytest.raises(IMGWValidationError) as error:
            get_provider(unknown)
        assert error.value.details["option"] == "provider"
        assert error.value.details["allowed"] == ["IMGW-PIB", "CHMI"]


def test_registry_invariants_across_providers():
    registry = datasets()
    assert len(registry) == 17
    names = [
        name
        for item in registry
        for name in (item.key, item.slug, item.legacy_alias)
        if name is not None
    ]
    assert len(names) == len(set(names))
    by_provider = {provider.id: provider for provider in providers()}
    for item in registry:
        provider = by_provider[item.provider]
        assert item.key.startswith(provider.key_prefix + ".")
        assert item.license == provider.license
        assert item.key in provider.datasets
    assert [key for provider in providers() for key in provider.datasets] == [
        item.key for item in registry
    ]
    roots = {
        provider: {
            item.server_dir.split("/")[0]
            for item in registry
            if item.provider == provider and item.server_dir is not None
        }
        for provider in by_provider
    }
    assert roots == {
        "IMGW-PIB": {"dane_hydrologiczne", "dane_meteorologiczne"},
        "CHMI": {"hydrology", "meteorology"},
    }
    imgw, chmi = (re.compile(p.station_code_pattern) for p in providers())
    union = re.compile(STATION_CODE_PATTERN)
    for code in ("149190310", A, B, M, "0-20000-0-11406", "0-203-0-42106052001"):
        assert bool(imgw.fullmatch(code)) != bool(chmi.fullmatch(code)), code
        assert union.fullmatch(code)
    for code in ("12345678", "0-203-1-cb900003", "0-203-1-", "149190310 "):
        assert not union.fullmatch(code)
        assert not imgw.fullmatch(code) and not chmi.fullmatch(code)


def test_content_forms_only_for_the_three_chmi_json_datasets():
    for item in datasets():
        assert item.content_form is None or item.content_form in CONTENT_FORMS
        expected = (
            CONTENT_FORMS[item.content_form].volatile_fields
            if item.content_form
            else ()
        )
        assert item.volatile_fields == expected
    assert [item.key for item in datasets() if item.content_form] == [
        HYDRO,
        "cz.chmi.hydro_stations",
        "cz.chmi.meteo_stations",
    ]


def test_chmi_descriptors_follow_the_spec_table():
    assert [item.key for item in datasets(provider="CHMI")] == CHMI_KEYS
    assert [item.key for item in datasets(provider="cz.chmi", kind="meteo")] == [
        METEO,
        "cz.chmi.meteo_stations",
    ]
    hydro, meteo, hydro_list, meteo_list = datasets(provider="CHMI")
    assert (hydro.slug, hydro.server_dir, hydro.parser) == (
        "chmi_hydro_daily",
        "hydrology/historical/data/daily",
        "parse_chmi_hydro_daily",
    )
    assert hydro.variables == {"H": "cm", "Q": "m3/s", "T": "degC"}
    assert set(hydro.variable_notes) == set(hydro.variables)
    assert (hydro.time_unit, hydro.year_type, hydro.first_year) == (
        "day",
        "calendar",
        1887,
    )
    assert (hydro.archive_scope, hydro.update_signal, hydro.measurement_fields) == (
        "station_year",
        "listing",
        (),
    )
    assert (meteo.slug, meteo.server_dir, meteo.parser) == (
        "chmi_meteo_daily",
        "meteorology/climate/historical_csv/data/daily",
        "parse_chmi_meteo_daily",
    )
    assert meteo.variables == {
        "P": "mm",
        "Tmean": "degC",
        "Tmax": "degC",
        "Tmin": "degC",
    }
    assert set(meteo.variable_notes) == set(meteo.variables)
    assert (meteo.first_year, meteo.archive_scope, meteo.update_signal) == (
        None,
        "station_element",
        "listing",
    )
    assert meteo.measurement_fields == ("quality", "source_flag")
    for item, directory in (
        (hydro_list, "hydrology/historical/metadata"),
        (meteo_list, "meteorology/climate/historical/metadata"),
    ):
        assert (item.server_dir, item.parser, item.time_unit) == (
            directory,
            "parse_chmi_stations",
            "station_list",
        )
        assert (item.archive_scope, item.update_signal, item.in_store) == (
            "country",
            "http",
            True,
        )
    with pytest.raises(IMGWValidationError) as error:
        datasets(provider="SHMU")
    assert error.value.details["option"] == "provider"


def test_hydro_files_are_station_year_candidates_in_code_order():
    files = archive_files(HYDRO, stations=[B, A, A], years="2023-2024")
    assert [(item.station_code, item.year) for item in files] == [
        (A, 2023),
        (A, 2024),
        (B, 2023),
        (B, 2024),
    ]
    first = files[0]
    assert first == ArchiveFile(
        HYDRO,
        f"hydrology/historical/data/daily/H_{A}_DQ_2023.json",
        f"https://opendata.chmi.cz/hydrology/historical/data/daily/H_{A}_DQ_2023.json",
        2023,
        None,
        None,
        "calendar",
        date(2023, 1, 1),
        date(2023, 12, 31),
        A,
    )
    assert archive_files("chmi_hydro_daily", stations=[A], years=1887)[0].year == 1887


def test_meteo_files_are_four_elements_per_station():
    foreign = "0-20000-0-99903"
    files = archive_files(METEO, stations=[M, foreign])
    # Stations in code order ("0-20000-…" < "0-203-…"), elements SRA, T, TMA, TMI.
    assert [(item.station_code, item.param) for item in files] == [
        (foreign, "SRA"),
        (foreign, "T"),
        (foreign, "TMA"),
        (foreign, "TMI"),
        (M, "SRA"),
        (M, "T"),
        (M, "TMA"),
        (M, "TMI"),
    ]
    base = "meteorology/climate/historical_csv/data/daily"
    assert [item.server_path for item in files[4:]] == [
        f"{base}/precipitation/dly-{M}-SRA.csv",
        f"{base}/temperature/dly-{M}-T.csv",
        f"{base}/temperature/dly-{M}-TMA.csv",
        f"{base}/temperature/dly-{M}-TMI.csv",
    ]
    assert all(
        (item.year, item.month, item.year_type, item.period_start, item.period_end)
        == (None, None, "none", None, None)
        for item in files
    )
    assert (
        files[4].url == f"https://opendata.chmi.cz/{base}/precipitation/dly-{M}-SRA.csv"
    )


@pytest.mark.parametrize(
    ("dataset", "options", "option"),
    [
        (HYDRO, {"years": 2024}, "stations"),
        (HYDRO, {"stations": [A]}, "years"),
        (HYDRO, {"stations": [A], "years": 2024, "months": [1]}, "months"),
        (HYDRO, {"stations": [A], "years": 2024, "params": ["H"]}, "params"),
        (HYDRO, {"stations": [A], "years": 1886}, "years"),
        (HYDRO, {"stations": ["149190310"], "years": 2024}, "stations"),
        (HYDRO, {"stations": [], "years": 2024}, "stations"),
        (HYDRO, {"stations": A, "years": 2024}, "stations"),
        (HYDRO, {"stations": ["0-203-1-cb900003"], "years": 2024}, "stations"),
        (METEO, {}, "stations"),
        (METEO, {"stations": [M], "years": 2024}, "years"),
        (METEO, {"stations": [M], "months": 1}, "months"),
        ("pl.imgw.hydro_daily", {"years": 2024, "stations": [A]}, "stations"),
        ("pl.imgw.hydro_daily", {}, "years"),
        ("cz.chmi.hydro_stations", {"stations": [A]}, "dataset"),
    ],
)
def test_file_options_follow_the_provider_rules(dataset, options, option):
    with pytest.raises(IMGWValidationError) as error:
        archive_files(dataset, **options)
    assert error.value.details["option"] == option
    if options.get("years") == 1886:
        assert error.value.details["minimum"] == 1887


def test_station_code_errors_name_the_rejected_codes():
    with pytest.raises(IMGWValidationError) as error:
        archive_files(HYDRO, stations=[A, "149190310", "0-203-1-x"], years=2024)
    assert error.value.details["value"] == ["149190310", "0-203-1-x"]


def test_station_lists_of_each_provider():
    hydro, meteo = station_source_files(provider="CHMI")
    assert (hydro.dataset, hydro.server_path) == (
        "cz.chmi.hydro_stations",
        "hydrology/historical/metadata/meta1.json",
    )
    assert (meteo.dataset, meteo.url) == (
        "cz.chmi.meteo_stations",
        "https://opendata.chmi.cz/meteorology/climate/historical/metadata/meta1.json",
    )
    assert (hydro.year, hydro.year_type, hydro.station_code) == (None, "none", None)
    assert station_source_files() == station_source_files(provider="pl.imgw")
    with pytest.raises(IMGWValidationError):
        station_source_files(provider="SHMU")


def _every_file() -> list[ArchiveFile]:
    files: list[ArchiveFile] = []
    for item in datasets():
        if item.time_unit == "station_list":
            files += [
                file
                for file in station_source_files(provider=item.provider)
                if file.dataset == item.key
            ]
        elif item.server_dir is None:
            continue
        elif item.archive_scope == "station_year":
            files += archive_files(item.key, stations=[A, B], years=[1887, 2025])
        elif item.archive_scope == "station_element":
            files += archive_files(item.key, stations=[M, "0-20000-0-11406"])
        else:
            first = item.first_year or 1951
            files += archive_files(item.key, years=[first, 1995, 2000, 2001, 2024])
    return files


def test_reverse_mapping_recreates_every_file():
    files = _every_file()
    assert {file.dataset for file in files} == {
        item.key for item in datasets() if item.server_dir is not None
    }
    for file in files:
        assert _archive_from_path(file.dataset, file.server_path) == file


@pytest.mark.parametrize(
    ("dataset", "server_path"),
    [
        (HYDRO, f"hydrology/historical/data/daily/H_{A}_DQ_2023_2024.json"),
        (HYDRO, f"hydrology/historical/data/daily/H_{A}_DQ_1886.json"),
        (HYDRO, f"hydrology/historical/data/daily/sub/H_{A}_DQ_2023.json"),
        (HYDRO, "hydrology/historical/data/daily/H_0-203-1-cb1_DQ_2023.json"),
        (
            METEO,
            f"meteorology/climate/historical_csv/data/daily/precipitation/dly-{M}-API30.csv",
        ),
        (
            METEO,
            f"meteorology/climate/historical_csv/data/daily/temperature/dly-{M}-TMInoc.csv",
        ),
        (
            METEO,
            f"meteorology/climate/historical_csv/data/daily/temperature/dly-{M}-SRA.csv",
        ),
        ("cz.chmi.hydro_stations", "hydrology/historical/metadata/meta2.json"),
        ("pl.imgw.hydro_daily", "dane_hydrologiczne/dobowe/2023/zjaw_2023.zip"),
        ("pl.imgw.hydro_daily", "dane_hydrologiczne/dobowe/2023/codz_2023_01.zip"),
        (
            "pl.imgw.meteo_climate_daily",
            "dane_meteorologiczne/dobowe/klimat/1950_1955/1950_k.zip",
        ),
    ],
)
def test_reverse_mapping_rejects_other_names(dataset, server_path):
    assert _archive_from_path(dataset, server_path) is None


def test_new_fields_have_defaults_so_3_0_constructors_still_work():
    license_ = License("IMGW-PIB", "Źródło", "https://example.invalid")
    archive = ArchiveFile(
        "pl.imgw.hydro_daily",
        "a/b.zip",
        "https://x/a/b.zip",
        2024,
        None,
        None,
        "hydrological",
        None,
        None,
    )
    descriptor = DatasetDescriptor(
        "pl.imgw.x",
        "x",
        "hydro",
        "X",
        "x",
        None,
        {},
        "day",
        "calendar",
        None,
        "http",
        license_,
        None,
        False,
    )
    assert (license_.terms_url, archive.station_code) == (None, None)
    assert (descriptor.provider, descriptor.archive_scope) == ("IMGW-PIB", "country")
    assert (descriptor.variable_notes, descriptor.measurement_fields) == ({}, ())
    assert (descriptor.content_form, descriptor.volatile_fields) == (None, ())
    assert get_dataset("chmi_meteo_daily").key == METEO
