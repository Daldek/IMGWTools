"""
Database module for caching IMGW hydrological data.

This module provides SQLite-based caching for hydrological data
downloaded from IMGW public data servers.

Usage:
    Enable caching by setting IMGW_DB_ENABLED=true in environment
    or .env file. The database file location can be configured
    via IMGW_DB_PATH (default: ./data/imgw_hydro.db).

Example:
    from imgwtools.db import get_repository, init_db

    # Initialize database (creates tables if not exist)
    init_db()

    # Get repository for queries
    repo = get_repository()
    data = repo.get_daily_data("150160180", 2020, 2023)
"""

from imgwtools.db.cache_manager import HydroCacheManager, get_cache_manager
from imgwtools.db.connection import db_exists, get_db_connection
from imgwtools.db.repository import HydroRepository, get_repository
from imgwtools.db.schema import (
    get_cached_years,
    get_schema_version,
    get_table_counts,
    init_db,
)

__all__ = [
    "get_db_connection",
    "db_exists",
    "init_db",
    "get_schema_version",
    "get_table_counts",
    "get_cached_years",
    "HydroRepository",
    "get_repository",
    "HydroCacheManager",
    "get_cache_manager",
]
