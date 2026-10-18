"""
Unit tests for imgwtools.urls module (URL builders).
"""

import pytest

from imgwtools.exceptions import IMGWValidationError
from imgwtools.urls import (
    IMGW_API_URL,
    IMGW_PMAXTP_URL,
    build_api_url,
    build_pmaxtp_url,
)


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
