"""
Cache manager for lazy loading IMGW hydrological data.

Handles downloading data from IMGW servers and caching it in SQLite.
"""

from collections.abc import Callable

import httpx

from imgwtools.core.url_builder import (
    HydroInterval,
    HydroParam,
    build_hydro_url,
)
from imgwtools.db.connection import get_transaction
from imgwtools.db.models import (
    HydroDailyRecord,
    HydroMonthlyRecord,
    HydroSemiAnnualRecord,
    HydroStation,
)
from imgwtools.db.parsers import parse_stations_csv, parse_zip_file
from imgwtools.db.repository import get_repository

# IMGW station list URL
HYDRO_STATIONS_CSV_URL = (
    "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    "dane_hydrologiczne/lista_stacji_hydro.csv"
)

# Callback type for progress reporting
ProgressCallback = Callable[[str, int, int], None]


class HydroCacheManager:
    """
    Manager for caching IMGW hydrological data.

    Implements lazy loading: data is downloaded and cached only when
    first requested. Subsequent requests are served from the cache.
    """

    def __init__(self, timeout: float = 60.0):
        """
        Initialize cache manager.

        Args:
            timeout: HTTP request timeout in seconds.
        """
        self.timeout = timeout
        self.repo = get_repository()

    async def ensure_data_cached(
        self,
        interval: str,
        year: int,
        month: int | None = None,
        param: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> bool:
        """
        Ensure data for given range is cached.

        Downloads and caches data if not already present.

        Args:
            interval: Data interval ('dobowe', 'miesieczne', 'polroczne').
            year: Hydrological year.
            month: Month (for daily data before 2023).
            param: Parameter 'H', 'Q', or 'T' (for semi-annual data).
            progress_callback: Optional callback for progress updates.

        Returns:
            True if data was downloaded, False if already cached.

        Raises:
            ValueError: If invalid parameters.
            httpx.HTTPError: If download fails.
        """
        # Check if already cached
        if self.repo.is_range_cached(interval, year, month, param):
            return False

        # Map interval string to enum
        interval_map = {
            "dobowe": HydroInterval.DAILY,
            "miesieczne": HydroInterval.MONTHLY,
            "polroczne": HydroInterval.SEMI_ANNUAL,
            "polroczne_i_roczne": HydroInterval.SEMI_ANNUAL,
        }

        hydro_interval = interval_map.get(interval)
        if not hydro_interval:
            raise ValueError(f"Unknown interval: {interval}")

        # Build URL
        hydro_param = HydroParam(param) if param else None
        download_info = build_hydro_url(
            interval=hydro_interval,
            year=year,
            month=month,
            param=hydro_param,
        )

        if progress_callback:
            progress_callback(f"Downloading {download_info.filename}", 0, 1)

        # Download ZIP file
        async with httpx.AsyncClient() as client:
            response = await client.get(
                download_info.url,
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            zip_data = response.content

        if progress_callback:
            progress_callback(f"Parsing {download_info.filename}", 0, 1)

        # Parse and insert data
        record_count = self._import_zip_data(
            zip_data=zip_data,
            interval=interval,
            year=year,
            month=month,
            param=param,
            source_file=download_info.filename,
        )

        if progress_callback:
            progress_callback(f"Cached {record_count} records", 1, 1)

        return True

    def _import_zip_data(
        self,
        zip_data: bytes,
        interval: str,
        year: int,
        source_file: str,
        month: int | None = None,
        param: str | None = None,
    ) -> int:
        """
        Import data from ZIP file into database.

        Args:
            zip_data: ZIP file content.
            interval: Data interval.
            year: Hydrological year.
            source_file: Source filename for tracking.
            month: Month (optional).
            param: Parameter (optional).

        Returns:
            Number of records imported.
        """
        stations: dict[str, HydroStation] = {}
        daily_records: list[HydroDailyRecord] = []
        monthly_records: list[HydroMonthlyRecord] = []
        semi_annual_records: list[HydroSemiAnnualRecord] = []

        # Parse ZIP file
        for station, record in parse_zip_file(zip_data, interval):
            # Collect unique stations
            if station.station_code not in stations:
                stations[station.station_code] = station

            # Collect records by type
            if isinstance(record, HydroDailyRecord):
                daily_records.append(record)
            elif isinstance(record, HydroMonthlyRecord):
                monthly_records.append(record)
            elif isinstance(record, HydroSemiAnnualRecord):
                semi_annual_records.append(record)

        # Insert all data in a single transaction
        with get_transaction() as conn:
            # Insert stations
            for station in stations.values():
                self.repo.upsert_station(station)

            # Insert records
            record_count = 0

            if daily_records:
                record_count += self.repo.insert_daily_batch(daily_records, conn)
            if monthly_records:
                record_count += self.repo.insert_monthly_batch(monthly_records, conn)
            if semi_annual_records:
                record_count += self.repo.insert_semi_annual_batch(semi_annual_records, conn)

            # Mark range as cached
            self.repo.mark_range_cached(
                interval=interval,
                year=year,
                month=month,
                param=param,
                source_file=source_file,
                record_count=record_count,
                conn=conn,
            )

        return record_count

    async def cache_year_range(
        self,
        interval: str,
        start_year: int,
        end_year: int,
        param: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[int, int]:
        """
        Cache data for a range of years.

        Args:
            interval: Data interval.
            start_year: Start year (inclusive).
            end_year: End year (inclusive).
            param: Parameter for semi-annual data.
            progress_callback: Optional progress callback.

        Returns:
            Dictionary mapping year to record count.
        """
        results: dict[int, int] = {}

        total_years = end_year - start_year + 1
        current = 0

        for year in range(start_year, end_year + 1):
            if progress_callback:
                progress_callback(f"Processing year {year}", current, total_years)

            # Handle daily data - different file structure before/after 2023
            if interval == "dobowe" and year < 2023:
                # Before 2023: monthly files
                year_total = 0
                for month in range(1, 13):
                    if not self.repo.is_range_cached(interval, year, month):
                        try:
                            await self.ensure_data_cached(
                                interval=interval,
                                year=year,
                                month=month,
                            )
                            # Get record count from cached_ranges
                            ranges = self.repo.get_cached_ranges(interval)
                            for r in ranges:
                                if r.year == year and r.month == month:
                                    year_total += r.record_count or 0
                                    break
                        except Exception:
                            continue

                results[year] = year_total
            else:
                # Single file per year
                if not self.repo.is_range_cached(interval, year, param=param):
                    try:
                        await self.ensure_data_cached(
                            interval=interval,
                            year=year,
                            param=param,
                        )
                        # Get record count
                        ranges = self.repo.get_cached_ranges(interval)
                        for r in ranges:
                            if r.year == year and r.param == param:
                                results[year] = r.record_count or 0
                                break
                    except Exception:
                        results[year] = 0
                else:
                    results[year] = 0  # Already cached

            current += 1

        if progress_callback:
            progress_callback("Done", total_years, total_years)

        return results

    async def refresh_stations(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> int:
        """
        Refresh station list from IMGW.

        Downloads the station list CSV and updates the database.

        Args:
            progress_callback: Optional progress callback.

        Returns:
            Number of stations updated.
        """
        if progress_callback:
            progress_callback("Downloading station list", 0, 1)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                HYDRO_STATIONS_CSV_URL,
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.content

        if progress_callback:
            progress_callback("Parsing stations", 0, 1)

        count = 0
        for station in parse_stations_csv(content):
            self.repo.upsert_station(station)
            count += 1

        if progress_callback:
            progress_callback(f"Updated {count} stations", 1, 1)

        return count

    def get_daily_data(
        self,
        station_code: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> list[HydroDailyRecord]:
        """
        Get daily data from cache.

        Note: This does NOT trigger lazy loading. Call ensure_data_cached()
        first if you need to ensure data is available.

        Args:
            station_code: Filter by station.
            start_year: Start hydrological year.
            end_year: End hydrological year.

        Returns:
            List of daily records.
        """
        return self.repo.get_daily_data(
            station_code=station_code,
            start_year=start_year,
            end_year=end_year,
        )

    def get_monthly_data(
        self,
        station_code: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        extremum: str | None = None,
    ) -> list[HydroMonthlyRecord]:
        """Get monthly data from cache."""
        return self.repo.get_monthly_data(
            station_code=station_code,
            start_year=start_year,
            end_year=end_year,
            extremum=extremum,
        )

    def get_semi_annual_data(
        self,
        station_code: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        param: str | None = None,
        period: str | None = None,
    ) -> list[HydroSemiAnnualRecord]:
        """Get semi-annual data from cache."""
        return self.repo.get_semi_annual_data(
            station_code=station_code,
            start_year=start_year,
            end_year=end_year,
            param=param,
            period=period,
        )


# Singleton instance
_cache_manager: HydroCacheManager | None = None


def get_cache_manager() -> HydroCacheManager:
    """Get singleton cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = HydroCacheManager()
    return _cache_manager
