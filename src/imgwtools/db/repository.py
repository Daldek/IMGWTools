"""
Data access layer for hydrological data.

Provides repository pattern for querying cached IMGW data.
"""

import sqlite3
from datetime import UTC, datetime

from imgwtools.db.connection import get_db_connection, get_transaction
from imgwtools.db.models import (
    CachedRange,
    HydroDailyRecord,
    HydroMonthlyRecord,
    HydroSemiAnnualRecord,
    HydroStation,
)


class HydroRepository:
    """Repository for hydrological data access."""

    # --- Station methods ---

    def get_stations(
        self,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HydroStation]:
        """
        Get list of stations from cache.

        Args:
            search: Optional search term (filters by name or river).
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of HydroStation objects.
        """
        with get_db_connection(readonly=True) as conn:
            if search:
                cursor = conn.execute(
                    """
                    SELECT station_code, station_name, river_name, latitude, longitude
                    FROM hydro_stations
                    WHERE station_name LIKE ? OR river_name LIKE ?
                    ORDER BY station_name
                    LIMIT ? OFFSET ?
                    """,
                    (f"%{search}%", f"%{search}%", limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT station_code, station_name, river_name, latitude, longitude
                    FROM hydro_stations
                    ORDER BY station_name
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )

            return [
                HydroStation(
                    station_code=row["station_code"],
                    station_name=row["station_name"],
                    river_name=row["river_name"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                )
                for row in cursor
            ]

    def get_station(self, station_code: str) -> HydroStation | None:
        """Get single station by code."""
        with get_db_connection(readonly=True) as conn:
            cursor = conn.execute(
                """
                SELECT station_code, station_name, river_name, latitude, longitude
                FROM hydro_stations
                WHERE station_code = ?
                """,
                (station_code,),
            )
            row = cursor.fetchone()
            if row:
                return HydroStation(
                    station_code=row["station_code"],
                    station_name=row["station_name"],
                    river_name=row["river_name"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                )
            return None

    def upsert_station(self, station: HydroStation) -> None:
        """Insert or update station metadata."""
        now = datetime.now(UTC).isoformat()
        with get_transaction() as conn:
            conn.execute(
                """
                INSERT INTO hydro_stations
                    (station_code, station_name, river_name, latitude, longitude, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_code) DO UPDATE SET
                    station_name = excluded.station_name,
                    river_name = excluded.river_name,
                    latitude = COALESCE(excluded.latitude, latitude),
                    longitude = COALESCE(excluded.longitude, longitude),
                    updated_at = excluded.updated_at
                """,
                (
                    station.station_code,
                    station.station_name,
                    station.river_name,
                    station.latitude,
                    station.longitude,
                    now,
                ),
            )

    # --- Daily data methods ---

    def get_daily_data(
        self,
        station_code: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[HydroDailyRecord]:
        """
        Get daily measurements from cache.

        Args:
            station_code: Filter by station code.
            start_year: Start hydrological year (inclusive).
            end_year: End hydrological year (inclusive).
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            List of daily measurement records.
        """
        conditions = []
        params = []

        if station_code:
            conditions.append("d.station_code = ?")
            params.append(station_code)

        if start_year:
            conditions.append("d.hydro_year >= ?")
            params.append(start_year)

        if end_year:
            conditions.append("d.hydro_year <= ?")
            params.append(end_year)

        if start_date:
            conditions.append("d.measurement_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("d.measurement_date <= ?")
            params.append(end_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with get_db_connection(readonly=True) as conn:
            cursor = conn.execute(
                f"""
                SELECT
                    d.station_code, d.hydro_year, d.hydro_month, d.day,
                    d.calendar_month, d.water_level_cm, d.flow_m3s,
                    d.water_temp_c, d.measurement_date,
                    s.station_name, s.river_name
                FROM hydro_daily d
                LEFT JOIN hydro_stations s ON d.station_code = s.station_code
                WHERE {where_clause}
                ORDER BY d.station_code, d.measurement_date
                """,
                params,
            )

            return [
                HydroDailyRecord(
                    station_code=row["station_code"],
                    station_name=row["station_name"],
                    river_name=row["river_name"],
                    hydro_year=row["hydro_year"],
                    hydro_month=row["hydro_month"],
                    day=row["day"],
                    calendar_month=row["calendar_month"],
                    water_level_cm=row["water_level_cm"],
                    flow_m3s=row["flow_m3s"],
                    water_temp_c=row["water_temp_c"],
                    measurement_date=row["measurement_date"],
                )
                for row in cursor
            ]

    def insert_daily_batch(
        self,
        records: list[HydroDailyRecord],
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """
        Insert batch of daily records.

        Args:
            records: List of daily records to insert.
            conn: Optional existing connection (for transaction grouping).

        Returns:
            Number of records inserted.
        """
        if not records:
            return 0

        def _insert(c: sqlite3.Connection) -> int:
            c.executemany(
                """
                INSERT OR IGNORE INTO hydro_daily
                    (station_code, hydro_year, hydro_month, day, calendar_month,
                     water_level_cm, flow_m3s, water_temp_c, measurement_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.station_code,
                        r.hydro_year,
                        r.hydro_month,
                        r.day,
                        r.calendar_month,
                        r.water_level_cm,
                        r.flow_m3s,
                        r.water_temp_c,
                        r.measurement_date,
                    )
                    for r in records
                ],
            )
            return c.total_changes

        if conn:
            return _insert(conn)
        else:
            with get_transaction() as c:
                return _insert(c)

    # --- Monthly data methods ---

    def get_monthly_data(
        self,
        station_code: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        extremum: str | None = None,
    ) -> list[HydroMonthlyRecord]:
        """Get monthly measurements from cache."""
        conditions = []
        params = []

        if station_code:
            conditions.append("m.station_code = ?")
            params.append(station_code)

        if start_year:
            conditions.append("m.hydro_year >= ?")
            params.append(start_year)

        if end_year:
            conditions.append("m.hydro_year <= ?")
            params.append(end_year)

        if extremum:
            conditions.append("m.extremum = ?")
            params.append(extremum)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with get_db_connection(readonly=True) as conn:
            cursor = conn.execute(
                f"""
                SELECT
                    m.station_code, m.hydro_year, m.hydro_month, m.calendar_month,
                    m.extremum, m.water_level_cm, m.flow_m3s, m.water_temp_c,
                    s.station_name, s.river_name
                FROM hydro_monthly m
                LEFT JOIN hydro_stations s ON m.station_code = s.station_code
                WHERE {where_clause}
                ORDER BY m.station_code, m.hydro_year, m.hydro_month, m.extremum
                """,
                params,
            )

            return [
                HydroMonthlyRecord(
                    station_code=row["station_code"],
                    station_name=row["station_name"],
                    river_name=row["river_name"],
                    hydro_year=row["hydro_year"],
                    hydro_month=row["hydro_month"],
                    calendar_month=row["calendar_month"],
                    extremum=row["extremum"],
                    water_level_cm=row["water_level_cm"],
                    flow_m3s=row["flow_m3s"],
                    water_temp_c=row["water_temp_c"],
                )
                for row in cursor
            ]

    def insert_monthly_batch(
        self,
        records: list[HydroMonthlyRecord],
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Insert batch of monthly records."""
        if not records:
            return 0

        def _insert(c: sqlite3.Connection) -> int:
            c.executemany(
                """
                INSERT OR IGNORE INTO hydro_monthly
                    (station_code, hydro_year, hydro_month, calendar_month,
                     extremum, water_level_cm, flow_m3s, water_temp_c)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.station_code,
                        r.hydro_year,
                        r.hydro_month,
                        r.calendar_month,
                        r.extremum,
                        r.water_level_cm,
                        r.flow_m3s,
                        r.water_temp_c,
                    )
                    for r in records
                ],
            )
            return c.total_changes

        if conn:
            return _insert(conn)
        else:
            with get_transaction() as c:
                return _insert(c)

    # --- Semi-annual data methods ---

    def get_semi_annual_data(
        self,
        station_code: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        param: str | None = None,
        period: str | None = None,
    ) -> list[HydroSemiAnnualRecord]:
        """Get semi-annual measurements from cache."""
        conditions = []
        params_list = []

        if station_code:
            conditions.append("sa.station_code = ?")
            params_list.append(station_code)

        if start_year:
            conditions.append("sa.hydro_year >= ?")
            params_list.append(start_year)

        if end_year:
            conditions.append("sa.hydro_year <= ?")
            params_list.append(end_year)

        if param:
            conditions.append("sa.param = ?")
            params_list.append(param)

        if period:
            conditions.append("sa.period = ?")
            params_list.append(period)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with get_db_connection(readonly=True) as conn:
            cursor = conn.execute(
                f"""
                SELECT
                    sa.station_code, sa.hydro_year, sa.period, sa.param,
                    sa.extremum, sa.value, sa.extremum_start_date, sa.extremum_end_date,
                    s.station_name, s.river_name
                FROM hydro_semi_annual sa
                LEFT JOIN hydro_stations s ON sa.station_code = s.station_code
                WHERE {where_clause}
                ORDER BY sa.station_code, sa.hydro_year, sa.period, sa.param
                """,
                params_list,
            )

            return [
                HydroSemiAnnualRecord(
                    station_code=row["station_code"],
                    station_name=row["station_name"],
                    river_name=row["river_name"],
                    hydro_year=row["hydro_year"],
                    period=row["period"],
                    param=row["param"],
                    extremum=row["extremum"],
                    value=row["value"],
                    extremum_start_date=row["extremum_start_date"],
                    extremum_end_date=row["extremum_end_date"],
                )
                for row in cursor
            ]

    def insert_semi_annual_batch(
        self,
        records: list[HydroSemiAnnualRecord],
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Insert batch of semi-annual records."""
        if not records:
            return 0

        def _insert(c: sqlite3.Connection) -> int:
            c.executemany(
                """
                INSERT OR IGNORE INTO hydro_semi_annual
                    (station_code, hydro_year, period, param, extremum,
                     value, extremum_start_date, extremum_end_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.station_code,
                        r.hydro_year,
                        r.period,
                        r.param,
                        r.extremum,
                        r.value,
                        r.extremum_start_date,
                        r.extremum_end_date,
                    )
                    for r in records
                ],
            )
            return c.total_changes

        if conn:
            return _insert(conn)
        else:
            with get_transaction() as c:
                return _insert(c)

    # --- Cache management methods ---

    def is_range_cached(
        self,
        interval: str,
        year: int,
        month: int | None = None,
        param: str | None = None,
    ) -> bool:
        """Check if a data range is already cached."""
        with get_db_connection(readonly=True) as conn:
            if month is None and param is None:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM cached_ranges
                    WHERE interval = ? AND year = ? AND month IS NULL AND param IS NULL
                    """,
                    (interval, year),
                )
            elif month is not None and param is None:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM cached_ranges
                    WHERE interval = ? AND year = ? AND month = ?
                    """,
                    (interval, year, month),
                )
            elif month is None and param is not None:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM cached_ranges
                    WHERE interval = ? AND year = ? AND param = ?
                    """,
                    (interval, year, param),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM cached_ranges
                    WHERE interval = ? AND year = ? AND month = ? AND param = ?
                    """,
                    (interval, year, month, param),
                )

            return cursor.fetchone() is not None

    def mark_range_cached(
        self,
        interval: str,
        year: int,
        source_file: str,
        record_count: int,
        month: int | None = None,
        param: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Mark a data range as cached."""
        now = datetime.now(UTC).isoformat()

        def _insert(c: sqlite3.Connection) -> None:
            c.execute(
                """
                INSERT OR REPLACE INTO cached_ranges
                    (interval, year, month, param, source_file, cached_at, record_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (interval, year, month, param, source_file, now, record_count),
            )

        if conn:
            _insert(conn)
        else:
            with get_transaction() as c:
                _insert(c)

    def get_cached_ranges(self, interval: str | None = None) -> list[CachedRange]:
        """Get list of cached ranges."""
        with get_db_connection(readonly=True) as conn:
            if interval:
                cursor = conn.execute(
                    """
                    SELECT id, interval, year, month, param, source_file, cached_at, record_count
                    FROM cached_ranges
                    WHERE interval = ?
                    ORDER BY year, month, param
                    """,
                    (interval,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, interval, year, month, param, source_file, cached_at, record_count
                    FROM cached_ranges
                    ORDER BY interval, year, month, param
                    """
                )

            return [
                CachedRange(
                    id=row["id"],
                    interval=row["interval"],
                    year=row["year"],
                    month=row["month"],
                    param=row["param"],
                    source_file=row["source_file"],
                    cached_at=row["cached_at"],
                    record_count=row["record_count"],
                )
                for row in cursor
            ]

    def clear_cache(self, interval: str | None = None) -> int:
        """
        Clear cached data.

        Args:
            interval: If specified, only clear data for this interval.

        Returns:
            Number of records deleted.
        """
        with get_transaction() as conn:
            total = 0

            if interval:
                tables = {
                    "dobowe": "hydro_daily",
                    "miesieczne": "hydro_monthly",
                    "polroczne": "hydro_semi_annual",
                }
                table = tables.get(interval)
                if table:
                    conn.execute(f"DELETE FROM {table}")
                    total += conn.total_changes
                conn.execute("DELETE FROM cached_ranges WHERE interval = ?", (interval,))
                total += conn.total_changes
            else:
                conn.execute("DELETE FROM hydro_daily")
                total += conn.total_changes
                conn.execute("DELETE FROM hydro_monthly")
                total += conn.total_changes
                conn.execute("DELETE FROM hydro_semi_annual")
                total += conn.total_changes
                conn.execute("DELETE FROM cached_ranges")
                total += conn.total_changes

            return total


# Singleton repository instance
_repository: HydroRepository | None = None


def get_repository() -> HydroRepository:
    """Get singleton repository instance."""
    global _repository
    if _repository is None:
        _repository = HydroRepository()
    return _repository
