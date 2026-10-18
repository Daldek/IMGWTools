"""Pydantic models of the system routes outside the command catalog."""

from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"
