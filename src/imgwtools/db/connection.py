"""
SQLite database connection management.

Provides context manager for database connections with proper
configuration (WAL mode, foreign keys, etc.).
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from imgwtools.config import settings


def db_exists() -> bool:
    """Check if database file exists."""
    return settings.db_path.exists()


def ensure_db_directory() -> None:
    """Create database directory if it doesn't exist."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db_connection(
    readonly: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Get SQLite database connection with proper configuration.

    Args:
        readonly: If True, open database in read-only mode.

    Yields:
        Configured SQLite connection.

    Raises:
        RuntimeError: If database is not enabled in settings.
        FileNotFoundError: If readonly=True and database doesn't exist.

    Example:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM hydro_stations")
            rows = cursor.fetchall()
    """
    if not settings.db_enabled:
        raise RuntimeError(
            "Database is not enabled. Set IMGW_DB_ENABLED=true "
            "in environment or .env file."
        )

    if readonly and not db_exists():
        raise FileNotFoundError(
            f"Database file not found: {settings.db_path}. "
            "Run 'imgw db init' to create it."
        )

    # Ensure directory exists for write operations
    if not readonly:
        ensure_db_directory()

    # Build connection URI
    db_path = str(settings.db_path.resolve())
    if readonly:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(db_path)

    try:
        # Configure connection
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        # Use WAL mode for better concurrency (only for write connections)
        if not readonly:
            conn.execute("PRAGMA journal_mode = WAL")

        # Set busy timeout to 30 seconds
        conn.execute("PRAGMA busy_timeout = 30000")

        yield conn

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_transaction() -> Generator[sqlite3.Connection, None, None]:
    """
    Get database connection with automatic transaction management.

    Commits on success, rolls back on exception.

    Yields:
        SQLite connection with active transaction.

    Example:
        with get_transaction() as conn:
            conn.execute("INSERT INTO ...")
            conn.execute("UPDATE ...")
            # Auto-commits if no exception
    """
    with get_db_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
