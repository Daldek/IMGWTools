"""Pydantic models of the system routes outside the command catalog."""

from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Odpowiedź GET /health: stan serwera i wersja pakietu."""

    status: str = "ok"
    version: str = "1.0.0"
