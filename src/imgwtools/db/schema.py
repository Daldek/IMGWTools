"""
Database schema definitions and migrations.

Contains SQL DDL for all tables and migration logic.
"""

import sqlite3
from datetime import UTC, datetime

from imgwtools.db.connection import db_exists, get_db_connection

# Current schema version
CURRENT_VERSION = 1

# Schema DDL statements
SCHEMA_V1 = """
-- Hydrological stations metadata
CREATE TABLE IF NOT EXISTS hydro_stations (
    station_code TEXT PRIMARY KEY,
    station_name TEXT NOT NULL,
    river_name TEXT,
    latitude REAL,
    longitude REAL,
    updated_at TEXT NOT NULL
);

-- Track cached data ranges (for lazy loading)
CREATE TABLE IF NOT EXISTS cached_ranges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interval TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER,
    param TEXT,
    source_file TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    record_count INTEGER,
    UNIQUE(interval, year, month, param)
);

-- Daily hydrological measurements
CREATE TABLE IF NOT EXISTS hydro_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_code TEXT NOT NULL,
    hydro_year INTEGER NOT NULL,
    hydro_month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    calendar_month INTEGER,
    water_level_cm REAL,
    flow_m3s REAL,
    water_temp_c REAL,
    measurement_date TEXT,
    UNIQUE(station_code, hydro_year, hydro_month, day)
);

-- Monthly hydrological measurements
CREATE TABLE IF NOT EXISTS hydro_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_code TEXT NOT NULL,
    hydro_year INTEGER NOT NULL,
    hydro_month INTEGER NOT NULL,
    calendar_month INTEGER,
    extremum TEXT NOT NULL,
    water_level_cm REAL,
    flow_m3s REAL,
    water_temp_c REAL,
    UNIQUE(station_code, hydro_year, hydro_month, extremum)
);

-- Semi-annual and annual hydrological measurements
CREATE TABLE IF NOT EXISTS hydro_semi_annual (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_code TEXT NOT NULL,
    hydro_year INTEGER NOT NULL,
    period TEXT NOT NULL,
    param TEXT NOT NULL,
    extremum TEXT NOT NULL,
    value REAL,
    extremum_start_date TEXT,
    extremum_end_date TEXT,
    UNIQUE(station_code, hydro_year, period, param, extremum)
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_daily_station ON hydro_daily(station_code);
CREATE INDEX IF NOT EXISTS idx_daily_year ON hydro_daily(hydro_year);
CREATE INDEX IF NOT EXISTS idx_daily_date ON hydro_daily(measurement_date);
CREATE INDEX IF NOT EXISTS idx_daily_station_year ON hydro_daily(station_code, hydro_year);
CREATE INDEX IF NOT EXISTS idx_monthly_station_year ON hydro_monthly(station_code, hydro_year);
CREATE INDEX IF NOT EXISTS idx_semi_station_year ON hydro_semi_annual(station_code, hydro_year);
CREATE INDEX IF NOT EXISTS idx_cached_lookup ON cached_ranges(interval, year, month, param);
"""


def init_db(force: bool = False) -> bool:
    """
    Initialize database schema.

    Creates all tables and indexes if they don't exist.

    Args:
        force: If True, drop existing tables and recreate.

    Returns:
        True if database was created/updated, False if already up-to-date.

    Raises:
        RuntimeError: If database is not enabled.
    """
    with get_db_connection() as conn:
        if force:
            # Drop all tables
            conn.executescript("""
                DROP TABLE IF EXISTS hydro_daily;
                DROP TABLE IF EXISTS hydro_monthly;
                DROP TABLE IF EXISTS hydro_semi_annual;
                DROP TABLE IF EXISTS hydro_stations;
                DROP TABLE IF EXISTS cached_ranges;
                DROP TABLE IF EXISTS schema_version;
            """)

        # Check current version
        current = get_schema_version(conn)

        if current >= CURRENT_VERSION and not force:
            return False

        # Apply schema
        conn.executescript(SCHEMA_V1)

        # Record version
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO schema_version (version, applied_at, description)
            VALUES (?, ?, ?)
            """,
            (CURRENT_VERSION, now, "Initial schema with hydro tables"),
        )
        conn.commit()

        return True


def get_schema_version(conn: sqlite3.Connection | None = None) -> int:
    """
    Get current schema version from database.

    Args:
        conn: Optional existing connection. If None, creates new connection.

    Returns:
        Schema version number, or 0 if schema_version table doesn't exist.
    """
    def _get_version(c: sqlite3.Connection) -> int:
        try:
            cursor = c.execute(
                "SELECT MAX(version) FROM schema_version"
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0
        except sqlite3.OperationalError:
            # Table doesn't exist
            return 0

    if conn is not None:
        return _get_version(conn)

    if not db_exists():
        return 0

    with get_db_connection(readonly=True) as c:
        return _get_version(c)


def get_table_counts() -> dict[str, int]:
    """
    Get record counts for all data tables.

    Returns:
        Dictionary mapping table names to record counts.
    """
    tables = [
        "hydro_stations",
        "hydro_daily",
        "hydro_monthly",
        "hydro_semi_annual",
        "cached_ranges",
    ]

    counts = {}

    with get_db_connection(readonly=True) as conn:
        for table in tables:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]

    return counts


def get_cached_years() -> dict[str, list[int]]:
    """
    Get years that have been cached for each interval.

    Returns:
        Dictionary mapping interval names to lists of cached years.
    """
    result: dict[str, list[int]] = {
        "dobowe": [],
        "miesieczne": [],
        "polroczne": [],
    }

    with get_db_connection(readonly=True) as conn:
        cursor = conn.execute(
            """
            SELECT DISTINCT interval, year
            FROM cached_ranges
            ORDER BY interval, year
            """
        )
        for row in cursor:
            interval = row["interval"]
            if interval in result:
                result[interval].append(row["year"])

    return result
