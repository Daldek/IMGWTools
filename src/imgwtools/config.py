"""
Application configuration using pydantic-settings.
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Database settings (SQLite cache for hydro data)
    db_enabled: bool = False
    db_path: Path = Path("./data/imgw_hydro.db")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == "production"

    @property
    def hydro_stations_file(self) -> Path:
        """Path to hydrological stations CSV."""
        return self.data_dir / "hydro_stations_names.csv"

    @property
    def meteo_stations_file(self) -> Path:
        """Path to meteorological stations CSV."""
        return self.data_dir / "meteo_stations_names.csv"

    @property
    def hydro_stations_locations_file(self) -> Path:
        """Path to hydrological stations locations CSV."""
        return self.data_dir / "hydro_stations_locations.csv"

    @property
    def shapefile_path(self) -> Path:
        """Path to Poland shapefile."""
        return self.data_dir / "shp" / "polska.shp"


# Global settings instance
settings = Settings()
