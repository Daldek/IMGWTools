"""Public versioned IMGW store API: writer, reader, sync, series, catalog, PMAXTP.

Importing this package never imports ``pyarrow``; Parquet paths load it lazily
and raise ``IMGWStoreDependencyError`` when the ``[store]`` extra is missing.
"""

from imgwtools.store.catalog import RootArg, build_catalog, check_catalog
from imgwtools.store.export import export_archive, export_series
from imgwtools.store.pmaxtp import check_pmaxtp, read_pmaxtp, sync_pmaxtp
from imgwtools.store.reader import (
    current_version,
    iter_store,
    read_archive,
    read_catalog,
    read_meta,
    read_series,
    read_series_index,
    read_station_list,
    select_series,
    store_info,
    summarize_series,
)
from imgwtools.store.series import build_series, check_series
from imgwtools.store.sync import check_store, sync_store
from imgwtools.store.types import (
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
)
from imgwtools.store.writer import init_store, open_store, write_archive

__all__ = [
    # Types
    "Cancel",
    "CatalogReport",
    "Meta",
    "Notice",
    "NoticeHook",
    "OperationResult",
    "PMaXTPStoreResult",
    "PathArg",
    "PlanAction",
    "PlanItem",
    "Progress",
    "ProgressHook",
    "RootArg",
    "SeriesIndex",
    "SeriesReport",
    "StationCoverage",
    "StationFeature",
    "StationSeriesIndex",
    "StoreEntry",
    "StoreHandle",
    "StoreInfo",
    "StorePlan",
    "SyncReport",
    "VersionResult",
    # Functions
    "build_catalog",
    "build_series",
    "check_catalog",
    "check_pmaxtp",
    "check_series",
    "check_store",
    "current_version",
    "export_archive",
    "export_series",
    "init_store",
    "iter_store",
    "open_store",
    "read_archive",
    "read_catalog",
    "read_meta",
    "read_pmaxtp",
    "read_series",
    "read_series_index",
    "read_station_list",
    "select_series",
    "store_info",
    "summarize_series",
    "sync_pmaxtp",
    "sync_store",
    "write_archive",
]
