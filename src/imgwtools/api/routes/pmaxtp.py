"""
PMAXTP (Probabilistic Maximum Precipitation) routes.
"""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from imgwtools.api.schemas import PMaXTPRequest, PMaXTPMethodEnum
from imgwtools.core.url_builder import PMaXTPMethod, build_pmaxtp_url

router = APIRouter()


@router.get("/methods")
async def list_pmaxtp_methods():
    """
    Lista dostepnych metod obliczania opadow maksymalnych.
    """
    return {
        "methods": [
            {
                "id": "POT",
                "name": "Peak Over Threshold",
                "description": "Metoda przekroczen progu",
            },
            {
                "id": "AMP",
                "name": "Annual Max Precipitation",
                "description": "Roczne maksymalne opady",
            },
        ]
    }


@router.post("/url")
async def generate_pmaxtp_url(request: PMaXTPRequest):
    """
    Generuj URL do API PMAXTP.

    Zwraca URL do pobrania danych o opadach maksymalnych prawdopodobnych.
    """
    method = PMaXTPMethod(request.method.value)

    url = build_pmaxtp_url(
        method=method,
        latitude=request.latitude,
        longitude=request.longitude,
    )

    return {
        "url": url,
        "method": request.method.value,
        "latitude": request.latitude,
        "longitude": request.longitude,
    }


@router.post("/data")
async def fetch_pmaxtp_data(request: PMaXTPRequest) -> dict[str, Any]:
    """
    Pobierz dane PMAXTP.

    Pobiera dane bezposrednio z API IMGW i zwraca do klienta.
    Dane NIE sa przechowywane na serwerze.
    """
    method = PMaXTPMethod(request.method.value)

    url = build_pmaxtp_url(
        method=method,
        latitude=request.latitude,
        longitude=request.longitude,
    )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            return {
                "method": request.method.value,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "data": data,
            }

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="IMGW API timeout - sprobuj ponownie",
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"IMGW API error: {e.response.text}",
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502,
                detail=f"IMGW API connection error: {str(e)}",
            )
