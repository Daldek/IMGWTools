"""
Unit tests for imgwtools.urls module (URL builders).
"""

import pytest

from imgwtools.urls import (
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    build_api_url,
    get_available_years,
    HydroInterval,
    MeteoInterval,
    MeteoSubtype,
    HydroParam,
    PMaXTPMethod,
    IMGW_PUBLIC_DATA_URL,
    IMGW_API_URL,
    IMGW_PMAXTP_URL,
)


class TestBuildHydroUrl:
    """Tests for build_hydro_url function."""

    def test_daily_url_2023(self):
        """Test daily hydro URL for 2023 (single yearly file)."""
        result = build_hydro_url(HydroInterval.DAILY, 2023)

        assert result.url == f"{IMGW_PUBLIC_DATA_URL}/dane_hydrologiczne/dobowe/2023/codz_2023.zip"
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
        result = build_hydro_url(
            HydroInterval.SEMI_ANNUAL, 2023, param=HydroParam.FLOW
        )

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

    def test_hourly_opad_url(self):
        """Test hourly meteo URL for precipitation data."""
        result = build_meteo_url(
            MeteoInterval.HOURLY, MeteoSubtype.PRECIPITATION, 2023, month=7
        )

        assert "terminowe" in result.url
        assert "opad" in result.url
        assert "2023_07_o.zip" in result.url

    def test_old_year_folder_structure(self):
        """Test URL generation for years 1951-2000 (5-year folders)."""
        result = build_meteo_url(MeteoInterval.DAILY, MeteoSubtype.SYNOP, 1975)

        # Should use 5-year range folder
        assert "1971_1975" in result.url

    def test_old_year_folder_1951(self):
        """Test URL for 1951."""
        result = build_meteo_url(MeteoInterval.DAILY, MeteoSubtype.CLIMATE, 1951)

        assert "1951_1955" in result.url


class TestBuildPmaxtpUrl:
    """Tests for build_pmaxtp_url function."""

    def test_pot_method(self):
        """Test PMAXTP URL with POT method."""
        result = build_pmaxtp_url(PMaXTPMethod.POT, 52.23, 21.01)

        assert IMGW_PMAXTP_URL in result
        assert "/P/" in result
        assert "52.2300" in result
        assert "21.0100" in result

    def test_amp_method(self):
        """Test PMAXTP URL with AMP method."""
        result = build_pmaxtp_url(PMaXTPMethod.AMP, 50.0, 19.0)

        assert "/A/" in result
        assert "50.0000" in result
        assert "19.0000" in result

    def test_coordinate_precision(self):
        """Test that coordinates have 4 decimal places."""
        result = build_pmaxtp_url(PMaXTPMethod.POT, 52.123456, 21.987654)

        assert "52.1235" in result  # Rounded to 4 decimals
        assert "21.9877" in result


class TestBuildApiUrl:
    """Tests for build_api_url function."""

    def test_hydro_endpoint(self):
        """Test hydro API endpoint URL."""
        result = build_api_url("hydro")

        assert result == f"{IMGW_API_URL}/hydro"

    def test_synop_endpoint(self):
        """Test synop API endpoint URL."""
        result = build_api_url("synop")

        assert result == f"{IMGW_API_URL}/synop"

    def test_with_station_id(self):
        """Test API URL with station ID."""
        result = build_api_url("hydro", station_id="150160180")

        assert result == f"{IMGW_API_URL}/hydro/id/150160180"

    def test_with_station_name(self):
        """Test API URL with station name."""
        result = build_api_url("synop", station_name="Warszawa")

        assert result == f"{IMGW_API_URL}/synop/station/Warszawa"

    def test_warnings_hydro(self):
        """Test warnings endpoint for hydro."""
        result = build_api_url("warnings/hydro")

        assert result == f"{IMGW_API_URL}/warnings/hydro"

    def test_warnings_meteo(self):
        """Test warnings endpoint for meteo."""
        result = build_api_url("warnings/meteo")

        assert result == f"{IMGW_API_URL}/warnings/meteo"


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
