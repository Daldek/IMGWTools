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

Note:
    This module requires the [db] extra: pip install imgwtools[db]
"""

# Lazy imports to avoid requiring pydantic_settings for core library
# These are only loaded when actually accessed


def __getattr__(name: str):
    """Lazy import for database components."""
    if name == "HydroCacheManager":
        from imgwtools.db.cache_manager import HydroCacheManager
        return HydroCacheManager
    elif name == "get_cache_manager":
        from imgwtools.db.cache_manager import get_cache_manager
        return get_cache_manager
    elif name == "get_db_connection":
        from imgwtools.db.connection import get_db_connection
        return get_db_connection
    elif name == "db_exists":
        from imgwtools.db.connection import db_exists
        return db_exists
    elif name == "HydroRepository":
        from imgwtools.db.repository import HydroRepository
        return HydroRepository
    elif name == "get_repository":
        from imgwtools.db.repository import get_repository
        return get_repository
    elif name == "init_db":
        from imgwtools.db.schema import init_db
        return init_db
    elif name == "get_schema_version":
        from imgwtools.db.schema import get_schema_version
        return get_schema_version
    elif name == "get_table_counts":
        from imgwtools.db.schema import get_table_counts
        return get_table_counts
    elif name == "get_cached_years":
        from imgwtools.db.schema import get_cached_years
        return get_cached_years
    raise AttributeError(f"module 'imgwtools.db' has no attribute '{name}'")


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
