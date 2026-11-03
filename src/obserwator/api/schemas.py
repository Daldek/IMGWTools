"""Pydantic models of the system routes outside the command catalog."""

from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Answer of GET /health: the state of the server and the version of the package."""

    status: str = "ok"
    version: str = "1.0.0"
