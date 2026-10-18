"""
IMGWTools - Python library for accessing IMGW public data.

IMGW (Institute of Meteorology and Water Management) provides public
hydrological and meteorological data for Poland. This library provides
easy access to that data.

Quick Start:
    >>> from imgwtools import fetch_pmaxtp, list_hydro_stations
    >>>
    >>> # Get PMAXTP data for Warsaw
    >>> result = fetch_pmaxtp(latitude=52.23, longitude=21.01)
    >>> precip = result.data.get_precipitation(15, 50)
    >>> print(f"15-min precipitation, p=50%: {precip} mm")
    >>>
    >>> # List hydro stations
    >>> stations = list_hydro_stations()
    >>> print(f"Total stations: {len(stations)}")

Features:
    - PMAXTP data (probabilistic maximum precipitation)
    - Current hydrological data (water levels, flows)
    - Current synoptic data (temperature, wind, precipitation)
    - Weather and hydro warnings
    - Archive data download (daily, monthly, semi-annual)
    - Station listings with coordinates
    - Versioned local store of IMGW archives, Parquet series and station catalog
    - Data command catalog and ``imgw-project/1`` project manifests

Installation:
    pip install imgwtools           # Core library only
    pip install imgwtools[cli]      # With CLI
    pip install imgwtools[api]      # With REST API server
    pip install imgwtools[store]    # With Parquet versioned store (pyarrow)
    pip install imgwtools[pandas]   # With DataFrame export
    pip install imgwtools[full]     # All features

Importing ``imgwtools`` never imports ``pyarrow``; only Parquet paths of the
store load it on demand. Offline test fixtures live in ``imgwtools.testing``
and are intentionally not re-exported here.
"""

from imgwtools._version import __version__

# Data command catalog
from imgwtools.commands import (
    check_command,
    data_commands,
    format_command,
    run_command,
    validate_command,
)

# Coverage
from imgwtools.coverage import summarize_coverage

# Dataset registry
from imgwtools.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    License,
    archive_files,
    datasets,
    get_dataset,
    station_source_files,
)

# Exceptions
from imgwtools.exceptions import (
    ERROR_CODES,
    ErrorCode,
    ErrorSpec,
    IMGWCancelledError,
    IMGWConnectionError,
    IMGWDataError,
    IMGWError,
    IMGWProjectError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWStoreError,
    IMGWValidationError,
)

# Fetch functions
from imgwtools.fetch import (
    DownloadResult,
    download_hydro_data,
    download_hydro_data_async,
    download_meteo_data,
    download_meteo_data_async,
    fetch_hydro_current,
    fetch_hydro_current_async,
    fetch_pmaxtp,
    fetch_pmaxtp_async,
    fetch_synop,
    fetch_synop_async,
    fetch_warnings,
    fetch_warnings_async,
)

# Data models
from imgwtools.models import (
    Flag,
    HydroCurrentData,
    Measurement,
    NormalizedRecord,
    PMaXTPData,
    PMaXTPResult,
    StationListEntry,
    SynopData,
    WarningData,
)

# Parsers
from imgwtools.parsers import (
    IMGW_ENCODING,
    normalize_archive,
    parse_daily_csv,
    parse_meteo_climate_daily,
    parse_meteo_precip_daily,
    parse_monthly_csv,
    parse_semi_annual_csv,
    parse_stations_csv,
    parse_zip_file,
)

# Projects
from imgwtools.project import (
    add_project_task,
    check_project,
    download_project,
    get_project_status,
    init_project,
    open_project,
    remove_project_task,
    set_project_store,
    verify_project,
)

# Station functions
from imgwtools.stations import (
    HydroStation,
    MeteoStation,
    get_hydro_stations_with_coords,
    get_hydro_stations_with_coords_async,
    list_hydro_stations,
    list_hydro_stations_async,
    list_meteo_stations,
    list_meteo_stations_async,
)

# Versioned store
from imgwtools.store import (
    Cancel,
    CatalogReport,
    Meta,
    Notice,
    NoticeHook,
    OperationResult,
    PathArg,
    PlanAction,
    PlanItem,
    PMaXTPStoreResult,
    Progress,
    ProgressHook,
    RootArg,
    SeriesIndex,
    SeriesReport,
    StationCoverage,
    StationFeature,
    StationSeriesIndex,
    StoreEntry,
    StoreHandle,
    StoreInfo,
    StorePlan,
    SyncReport,
    VersionResult,
    build_catalog,
    build_series,
    check_catalog,
    check_pmaxtp,
    check_series,
    check_store,
    current_version,
    export_series,
    init_store,
    iter_store,
    open_store,
    read_archive,
    read_catalog,
    read_meta,
    read_pmaxtp,
    read_series,
    read_series_index,
    read_station_list,
    store_info,
    sync_pmaxtp,
    sync_store,
    write_archive,
)

# Command and project types
from imgwtools.store.types import (
    CommandOption,
    DataCommand,
    Project,
    ProjectFile,
    ProjectReport,
    ProjectTask,
    SeriesSelection,
)

# URL builders and types
from imgwtools.urls import (
    IMGW_API_URL,
    IMGW_PMAXTP_URL,
    IMGW_PUBLIC_DATA_URL,
    DataType,
    DownloadURL,
    HydroInterval,
    HydroParam,
    MeteoInterval,
    MeteoSubtype,
    PMaXTPMethod,
    build_api_url,
    build_hydro_url,
    build_meteo_url,
    build_pmaxtp_url,
    get_available_years,
)

__all__ = [
    # Version
    "__version__",
    # Exceptions
    "IMGWError",
    "IMGWConnectionError",
    "IMGWDataError",
    "IMGWValidationError",
    "IMGWStoreError",
    "IMGWStoreConflictError",
    "IMGWStoreDependencyError",
    "IMGWCancelledError",
    "ErrorCode",
    "ErrorSpec",
    "ERROR_CODES",
    "IMGWProjectError",
    # Models
    "PMaXTPData",
    "PMaXTPResult",
    "HydroCurrentData",
    "SynopData",
    "WarningData",
    "Flag",
    "Measurement",
    "NormalizedRecord",
    "StationListEntry",
    # URL builders
    "build_hydro_url",
    "build_meteo_url",
    "build_pmaxtp_url",
    "build_api_url",
    "get_available_years",
    # URL types and enums
    "DownloadURL",
    "DataType",
    "HydroInterval",
    "MeteoInterval",
    "MeteoSubtype",
    "HydroParam",
    "PMaXTPMethod",
    # URL constants
    "IMGW_PUBLIC_DATA_URL",
    "IMGW_API_URL",
    "IMGW_PMAXTP_URL",
    # Fetch functions (sync)
    "fetch_pmaxtp",
    "fetch_hydro_current",
    "fetch_synop",
    "fetch_warnings",
    "download_hydro_data",
    "download_meteo_data",
    # Fetch functions (async)
    "fetch_pmaxtp_async",
    "fetch_hydro_current_async",
    "fetch_synop_async",
    "fetch_warnings_async",
    "download_hydro_data_async",
    "download_meteo_data_async",
    # Fetch types
    "DownloadResult",
    # Station functions (sync)
    "list_hydro_stations",
    "list_meteo_stations",
    "get_hydro_stations_with_coords",
    # Station functions (async)
    "list_hydro_stations_async",
    "list_meteo_stations_async",
    "get_hydro_stations_with_coords_async",
    # Station types
    "HydroStation",
    "MeteoStation",
    # Parsers
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
    "parse_meteo_climate_daily",
    "parse_meteo_precip_daily",
    "normalize_archive",
    "IMGW_ENCODING",
    # Dataset registry
    "License",
    "DatasetDescriptor",
    "ArchiveFile",
    "datasets",
    "get_dataset",
    "archive_files",
    "station_source_files",
    # Coverage
    "summarize_coverage",
    # Store types
    "PathArg",
    "RootArg",
    "Progress",
    "Notice",
    "ProgressHook",
    "NoticeHook",
    "Cancel",
    "StoreHandle",
    "StoreInfo",
    "VersionResult",
    "PlanItem",
    "PlanAction",
    "StorePlan",
    "OperationResult",
    "SyncReport",
    "StationCoverage",
    "SeriesReport",
    "CatalogReport",
    "StoreEntry",
    "Meta",
    "StationFeature",
    "StationSeriesIndex",
    "SeriesIndex",
    "PMaXTPStoreResult",
    # Store functions
    "init_store",
    "open_store",
    "write_archive",
    "check_store",
    "sync_store",
    "check_series",
    "build_series",
    "check_catalog",
    "build_catalog",
    "store_info",
    "iter_store",
    "read_meta",
    "current_version",
    "read_catalog",
    "read_archive",
    "read_station_list",
    "read_series_index",
    "read_series",
    "export_series",
    "check_pmaxtp",
    "sync_pmaxtp",
    "read_pmaxtp",
    # Data command catalog
    "CommandOption",
    "DataCommand",
    "SeriesSelection",
    "data_commands",
    "validate_command",
    "format_command",
    "check_command",
    "run_command",
    # Projects
    "ProjectFile",
    "ProjectTask",
    "ProjectReport",
    "Project",
    "init_project",
    "open_project",
    "set_project_store",
    "add_project_task",
    "remove_project_task",
    "check_project",
    "download_project",
    "get_project_status",
    "verify_project",
]
