"""
URL builders for IMGW live services.

Archive file URLs come from the dataset registry
(``imgwtools.archive_files(dataset, years=...)[i].url``).

Examples
--------
>>> from imgwtools.urls import build_pmaxtp_url
>>> build_pmaxtp_url(52.23, 21.01, method="AMP")
'https://powietrze.imgw.pl/tpmax-api/point/A/KS/52.2300/21.0100'
"""

from typing import Literal

from imgwtools.exceptions import IMGWValidationError
from imgwtools.messages import message

IMGW_PUBLIC_DATA_URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
IMGW_API_URL = "https://danepubliczne.imgw.pl/api/data"
IMGW_PMAXTP_URL = "https://powietrze.imgw.pl/tpmax-api/point"
_PMAXTP_METHODS = ("POT", "AMP")


def build_pmaxtp_url(
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
) -> str:
    """
    Build URL for PMAXTP (probabilistic max precipitation) API.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees.
    longitude : float
        Longitude in decimal degrees.
    method : {"POT", "AMP"}, optional
        Calculation method: peaks over threshold (default) or annual maxima.

    Returns
    -------
    str
        URL for the PMAXTP API endpoint.

    Raises
    ------
    IMGWValidationError
        If ``method`` is not ``"POT"`` or ``"AMP"`` (``details`` ``option`` and
        ``allowed``).
    """
    if method not in _PMAXTP_METHODS:
        raise IMGWValidationError(
            message("urls.unknown_pmaxtp_method_allowed_pot", method=method),
            details={"option": "method", "allowed": list(_PMAXTP_METHODS)},
        )
    return f"{IMGW_PMAXTP_URL}/{method[0]}/KS/{latitude:.4f}/{longitude:.4f}"


def build_api_url(
    endpoint: str,
    /,
    *,
    station: str | None = None,
    station_name: str | None = None,
) -> str:
    """
    Build URL for IMGW real-time API.

    Parameters
    ----------
    endpoint : str
        API endpoint (``hydro``, ``meteo``, ``synop``, ``warningshydro``,
        ``warningsmeteo``).
    station : str or None, optional
        Station code; takes precedence over ``station_name``.
    station_name : str or None, optional
        Station name (for synop).

    Returns
    -------
    str
        URL for the IMGW API endpoint.
    """
    url = f"{IMGW_API_URL}/{endpoint}"

    if station:
        url += f"/id/{station}"
    elif station_name:
        url += f"/station/{station_name}"

    return url


__all__ = [
    "IMGW_PUBLIC_DATA_URL",
    "IMGW_API_URL",
    "IMGW_PMAXTP_URL",
    "build_pmaxtp_url",
    "build_api_url",
]
