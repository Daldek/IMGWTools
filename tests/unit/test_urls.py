"""
Unit tests for imgwtools.urls module (URL builders).
"""

import pytest

from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWValidationError
from imgwtools.urls import (
    IMGW_API_URL,
    IMGW_PMAXTP_URL,
    IMGW_PUBLIC_DATA_URL,
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    build_api_url,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    get_available_years,
)


class TestBuildHydroUrl:
    """Tests for build_hydro_url function."""

    def test_daily_url_2023(self):
        """Test daily hydro URL for 2023 (single yearly file)."""
        result = build_hydro_url(HydroInterval.DAILY, 2023)

        assert (
            result.url
            == f"{IMGW_PUBLIC_DATA_URL}/dane_hydrologiczne/dobowe/2023/codz_2023.zip"
        )
        assert result.filename == "codz_2023.zip"
        assert result.data_type == "dane_hydrologiczne"  # Polish folder name
        assert result.interval == "dobowe"
        assert result.year == 2023
        assert result.month is None

    def test_daily_url_2022_with_month(self):
        """Test daily hydro URL for 2022 with month (monthly files)."""
        result = build_hydro_url(HydroInterval.DAILY, 2022, month=6)

        assert "codz_2022_06.zip" in result.url
        assert result.filename == "codz_2022_06.zip"
        assert result.month == 6

    def test_monthly_url(self):
        """Test monthly hydro URL."""
        result = build_hydro_url(HydroInterval.MONTHLY, 2023)

        assert "miesieczne" in result.url
        assert "mies_2023.zip" in result.url
        assert result.interval == "miesieczne"

    def test_semi_annual_url_with_param(self):
        """Test semi-annual hydro URL with parameter."""
        result = build_hydro_url(HydroInterval.SEMI_ANNUAL, 2023, param=HydroParam.FLOW)

        assert "polroczne_i_roczne" in result.url
        assert "polr_Q_2023.zip" in result.url

    def test_semi_annual_url_temperature_param(self):
        """Test semi-annual URL with temperature parameter."""
        result = build_hydro_url(
            HydroInterval.SEMI_ANNUAL, 2023, param=HydroParam.TEMPERATURE
        )

        assert "polr_T_2023.zip" in result.url

    def test_semi_annual_url_depth_param(self):
        """Test semi-annual URL with depth parameter."""
        result = build_hydro_url(
            HydroInterval.SEMI_ANNUAL, 2023, param=HydroParam.DEPTH
        )
        assert "polr_H_2023.zip" in result.url

    @pytest.mark.parametrize(
        "interval,dataset,year,month,param",
        [
            (HydroInterval.DAILY, "hydro_daily", 2022, 2, None),
            (HydroInterval.DAILY, "hydro_daily", 2024, 2, None),
            (HydroInterval.MONTHLY, "hydro_monthly", 2024, None, None),
            (
                HydroInterval.SEMI_ANNUAL,
                "hydro_semiannual",
                2024,
                None,
                HydroParam.FLOW,
            ),
        ],
    )
    def test_store_url_matches_registry(self, interval, dataset, year, month, param):
        archive = archive_files(
            f"pl.imgw.{dataset}", years=[year], months=[month] if month else None
        )
        if param:
            archive = tuple(item for item in archive if item.param == param.value)
        assert (
            build_hydro_url(interval, year, month=month, param=param).url
            == archive[0].url
        )

    def test_phenomena_legacy_url_remains_supported(self):
        assert (
            build_hydro_url(HydroInterval.DAILY, 2024, month=13).filename
            == "zjaw_2024.zip"
        )


class TestBuildMeteoUrl:
    """Tests for build_meteo_url function."""

    def test_monthly_synop_url(self):
        """Test monthly meteo URL for synop data."""
        result = build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 2023)

        assert "meteorologiczne" in result.url
        assert "miesieczne" in result.url
        assert "synop" in result.url
        assert "2023_m_s.zip" in result.url

    def test_daily_klimat_url_with_month(self):
        """Test daily meteo URL for klimat data with month."""
        result = build_meteo_url(
            MeteoInterval.DAILY, MeteoSubtype.CLIMATE, 2023, month=3
        )

        assert "dobowe" in result.url
        assert "klimat" in result.url
        assert "2023_03_k.zip" in result.url

    def test_hourly_klimat_url(self):
        """Test hourly meteo URL for climate data."""
        result = build_meteo_url(
            MeteoInterval.HOURLY, MeteoSubtype.CLIMATE, 2023, month=7
        )

        assert "terminowe" in result.url
        assert "klimat" in result.url
        assert "2023_07_k.zip" in result.url

    def test_hourly_opad_raises(self):
        """Hourly precipitation dataset does not exist on IMGW servers."""
        with pytest.raises(ValueError, match="does not exist"):
            build_meteo_url(
                MeteoInterval.HOURLY, MeteoSubtype.PRECIPITATION, 2023, month=7
            )

    def test_daily_synop_raises_per_station(self):
        """Daily synop archives are per-station files - not supported."""
        with pytest.raises(ValueError, match="per-station"):
            build_meteo_url(MeteoInterval.DAILY, MeteoSubtype.SYNOP, 2023, month=6)

    def test_old_year_folder_structure(self):
        """Test URL generation for years 1951-2000 (5-year folders)."""
        result = build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 1975)

        # Should use 5-year range folder with one file per folder
        assert "1971_1975/1971_1975_m_s.zip" in result.url

    def test_old_year_folder_1951(self):
        """Test URL for 1951."""
        result = build_meteo_url(MeteoInterval.DAILY, MeteoSubtype.CLIMATE, 1951)

        assert "1951_1955" in result.url
        assert "1951_k.zip" in result.url

    def test_monthly_old_year_one_file_per_folder(self):
        """Monthly archives before 2001 are one file per 5-year folder."""
        result = build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.CLIMATE, 1999)

        assert "1996_2000/1996_2000_m_k.zip" in result.url

    def test_opad_first_folder_is_1950_1955(self):
        """Precipitation grid starts at 1950_1955 (IMGW quirk)."""
        result = build_meteo_url(
            MeteoInterval.MONTHLY, MeteoSubtype.PRECIPITATION, 1952
        )

        assert "1950_1955/1950_1955_m_o.zip" in result.url

    def test_synop_first_folder_is_1960_1965(self):
        """Synop grid starts at the six-year 1960_1965 folder (IMGW quirk)."""
        result = build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 1962)

        assert "1960_1965/1960_1965_m_s.zip" in result.url

    def test_synop_before_1960_raises(self):
        """No synop archives exist before 1960."""
        with pytest.raises(ValueError, match="1960"):
            build_meteo_url(MeteoInterval.MONTHLY, MeteoSubtype.SYNOP, 1955)

    @pytest.mark.parametrize(
        "subtype,dataset",
        [
            (MeteoSubtype.CLIMATE, "meteo_climate_daily"),
            (MeteoSubtype.PRECIPITATION, "meteo_precip_daily"),
        ],
    )
    def test_daily_store_url_matches_registry(self, subtype, dataset):
        archive = archive_files(f"pl.imgw.{dataset}", years=[2004], months=[2])[0]
        assert build_meteo_url(MeteoInterval.DAILY, subtype, 2004, 2).url == archive.url


class TestBuildPmaxtpUrl:
    """Tests for build_pmaxtp_url function."""

    def test_amp_url_is_unchanged(self):
        """Golden URL recorded from the 2.1.1 ``build_pmaxtp_url(AMP, lat, lon)``."""
        assert (
            build_pmaxtp_url(52.23, 21.01, method="AMP")
            == f"{IMGW_PMAXTP_URL}/A/KS/52.2300/21.0100"
        )

    def test_method_defaults_to_pot(self):
        assert build_pmaxtp_url(50.0, 19.0) == f"{IMGW_PMAXTP_URL}/P/KS/50.0000/19.0000"

    def test_coordinate_precision(self):
        """Coordinates are rounded to 4 decimal places."""
        result = build_pmaxtp_url(52.123456, 21.987654, method="POT")

        assert result.endswith("/52.1235/21.9877")

    def test_method_is_keyword_only(self):
        with pytest.raises(TypeError):
            build_pmaxtp_url(52.23, 21.01, "AMP")  # type: ignore[misc]

    def test_unknown_method_is_validation_error(self):
        with pytest.raises(IMGWValidationError) as error:
            build_pmaxtp_url(52.23, 21.01, method="XYZ")  # type: ignore[arg-type]
        assert error.value.details == {"option": "method", "allowed": ["POT", "AMP"]}


class TestBuildApiUrl:
    """Tests for build_api_url function."""

    @pytest.mark.parametrize(
        "endpoint", ["hydro", "meteo", "synop", "warningshydro", "warningsmeteo"]
    )
    def test_endpoint_without_station(self, endpoint):
        assert build_api_url(endpoint) == f"{IMGW_API_URL}/{endpoint}"

    def test_with_station(self):
        result = build_api_url("hydro", station="150160180")

        assert result == f"{IMGW_API_URL}/hydro/id/150160180"

    def test_with_station_name(self):
        result = build_api_url("synop", station_name="Warszawa")

        assert result == f"{IMGW_API_URL}/synop/station/Warszawa"

    def test_station_takes_precedence_over_name(self):
        result = build_api_url("synop", station="12375", station_name="Warszawa")

        assert result == f"{IMGW_API_URL}/synop/id/12375"

    def test_station_is_keyword_only(self):
        with pytest.raises(TypeError):
            build_api_url("hydro", "150160180")  # type: ignore[misc]


class TestGetAvailableYears:
    """Tests for get_available_years function."""

    def test_hydro_daily_years(self):
        """Test available years for hydro daily data."""
        years = get_available_years("hydro", "dobowe")

        # Returns tuple (start_year, end_year)
        assert isinstance(years, tuple)
        assert years[0] == 1951
        assert years[1] >= 2023

    def test_meteo_years(self):
        """Test available years for meteo data."""
        years = get_available_years("meteo", "dobowe")

        assert isinstance(years, tuple)
        assert years[0] == 1951
