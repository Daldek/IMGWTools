"""Application configuration using pydantic-settings."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="IMGW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    env: Literal["development", "production"] = "development"

    # API Server
    host: str = "0.0.0.0"
    port: int = 8000

    # API Keys
    api_keys_file: Path = Path("./api_keys.json")

    # Rate limiting (requests per hour, 0 = unlimited)
    rate_limit: int = 100

    # Data directory
    data_dir: Path = Path("./data")

    # Catalog REST routes of commands with a store root (spec §13.10). Unset
    # root: those routes answer 503 store_unavailable. Writes (POST without
    # ?check=true) need both flags below and the X-API-Key header; the token is
    # compared in constant time.
    store_root: Path | None = None
    store_writes_enabled: bool = False
    store_write_token: SecretStr | None = None
    # Server directory with user station-location CSVs offered to the catalog
    # route by file name only; unset disables the option (503).
    user_locations_dir: Path | None = None

    # Default and maximum page size of REST list commands (IMGW_API_MAX_LIMIT).
    api_max_limit: int = Field(default=1000, ge=1)

    # Language of the CLI help and of the --lang default (IMGW_LANG): "pl" or
    # "en"; checked where it is used, so a wrong value fails every imgw call
    # with validation_error instead of this module's import. REST ignores it.
    lang: str = "pl"

    # MCP over Streamable HTTP in imgw server (spec 2026-10-19 §6.2, §6.9): the
    # /mcp endpoint exists only with IMGW_MCP_ENABLED=true and the mcp extra;
    # it answers only the Host names of IMGW_MCP_ALLOWED_HOSTS (comma-separated,
    # each with or without a port).
    mcp_enabled: bool = False
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["127.0.0.1", "localhost"]

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == "production"

    @field_validator("mcp_allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        """Split the comma-separated text of ``IMGW_MCP_ALLOWED_HOSTS``."""
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value


# Global settings instance
settings = Settings()
