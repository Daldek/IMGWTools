"""Public package exports: completeness, real implementations, R1 signatures."""

import ast
import dataclasses
import importlib
import inspect
import subprocess
import sys
import textwrap
from collections.abc import Callable
from typing import Any

import pytest

import imgwtools
import imgwtools.exceptions
import imgwtools.stations
import imgwtools.store
import imgwtools.urls

# Spec §2–10, §12 and §13.12 (and spec 2026-10-18 §9.1): every function, type and
# exception a consumer may need; new functions take keyword-only options after the
# first object.
SPEC_FUNCTIONS = (
    "providers",
    "get_provider",
    "datasets",
    "get_dataset",
    "archive_files",
    "station_source_files",
    "download_hydro_data",
    "download_hydro_data_async",
    "download_meteo_data",
    "download_meteo_data_async",
    "init_store",
    "open_store",
    "write_archive",
    "check_store",
    "sync_store",
    "parse_meteo_climate_daily",
    "parse_meteo_precip_daily",
    "normalize_archive",
    "parse_chmi_hydro_daily",
    "parse_chmi_meteo_daily",
    "parse_chmi_stations",
    "summarize_coverage",
    "check_series",
    "build_series",
    "check_catalog",
    "build_catalog",
    "store_info",
    "iter_store",
    "read_meta",
    "current_version",
    "read_catalog",
    "read_station_list",
    "read_archive",
    "read_series_index",
    "read_series",
    "export_series",
    "export_archive",
    "select_series",
    "summarize_series",
    "download_archives",
    "find_stations",
    "find_stations_async",
    "fetch_meteo_current",
    "fetch_meteo_current_async",
    "fetch_hydro_states",
    "fetch_hydro_states_async",
    "command_schema",
    "list_commands",
    "check_pmaxtp",
    "sync_pmaxtp",
    "read_pmaxtp",
    "data_commands",
    "validate_command",
    "format_command",
    "check_command",
    "run_command",
    "agent_guide",
    "init_project",
    "open_project",
    "set_project_store",
    "add_project_task",
    "remove_project_task",
    "check_project",
    "download_project",
    "get_project_status",
    "verify_project",
)
SPEC_TYPES = (
    "PathArg",
    "RootArg",
    "Progress",
    "Notice",
    "ProgressHook",
    "NoticeHook",
    "Cancel",
    "License",
    "ProviderDescriptor",
    "DatasetDescriptor",
    "ArchiveFile",
    "DownloadResult",
    "DownloadItem",
    "DownloadReport",
    "FileResult",
    "OutputReport",
    "StoreHandle",
    "StoreInfo",
    "VersionResult",
    "PlanItem",
    "PlanAction",
    "StorePlan",
    "OperationResult",
    "SyncReport",
    "Flag",
    "Measurement",
    "NormalizedRecord",
    "StationListEntry",
    "StationCoverage",
    "SeriesReport",
    "CatalogReport",
    "StoreEntry",
    "Meta",
    "StationFeature",
    "StationSeriesIndex",
    "SeriesIndex",
    "PMaXTPStoreResult",
    "CommandOption",
    "DataCommand",
    "CommandResult",
    "Page",
    "SeriesSelection",
    "ProjectFile",
    "ProjectTask",
    "ProjectReport",
    "Project",
    "ErrorSpec",
)
# Type aliases and constants.
SPEC_VALUES = (
    "__version__",
    "ErrorCode",
    "ERROR_CODES",
    "Flag",
    "STATION_CODE_PATTERN",
    "YearsArg",
    "MonthsArg",
    "IMGW_ENCODING",
    "IMGW_PUBLIC_DATA_URL",
    "IMGW_API_URL",
    "IMGW_PMAXTP_URL",
)
SPEC_EXCEPTIONS = (
    "IMGWError",
    "IMGWConnectionError",
    "IMGWDataError",
    "IMGWValidationError",
    "IMGWStoreError",
    "IMGWStoreConflictError",
    "IMGWStoreDependencyError",
    "IMGWCancelledError",
    "IMGWProjectError",
)
# 2.x names kept (signatures changed per spec §13.8 and §13.11).
LEGACY_NAMES = (
    "fetch_pmaxtp",
    "fetch_pmaxtp_async",
    "fetch_hydro_current",
    "fetch_hydro_current_async",
    "fetch_synop",
    "fetch_synop_async",
    "fetch_warnings",
    "fetch_warnings_async",
    "PMaXTPData",
    "PMaXTPResult",
    "HydroCurrentData",
    "MeteoCurrentData",
    "HydroState",
    "SynopData",
    "WarningData",
    "parse_daily_csv",
    "parse_monthly_csv",
    "parse_semi_annual_csv",
    "parse_zip_file",
    "parse_stations_csv",
    "build_pmaxtp_url",
    "build_api_url",
)
# Spec §13.12: removed without aliases, also from imgwtools.urls.
REMOVED_NAMES = (
    "IMGWPlanStaleError",
    "HydroStation",
    "MeteoStation",
    "list_hydro_stations",
    "list_hydro_stations_async",
    "list_meteo_stations",
    "list_meteo_stations_async",
    "get_hydro_stations_with_coords",
    "get_hydro_stations_with_coords_async",
    "build_hydro_url",
    "build_meteo_url",
    "get_available_years",
    "DownloadURL",
    "DataType",
    "HydroInterval",
    "HydroParam",
    "MeteoInterval",
    "MeteoSubtype",
    "PMaXTPMethod",
)
_MODULES = (
    imgwtools,
    imgwtools.urls,
    imgwtools.store,
    imgwtools.stations,
    imgwtools.exceptions,
)
# Legacy download_* keep their 2.x positional parameters (spec §2, D7).
LEGACY_POSITIONAL = {
    "download_hydro_data": ("interval", "year", "month", "param"),
    "download_hydro_data_async": ("interval", "year", "month", "param"),
    "download_meteo_data": ("interval", "subtype", "year", "month"),
    "download_meteo_data_async": ("interval", "subtype", "year", "month"),
}
_POSITIONAL = (
    inspect.Parameter.POSITIONAL_ONLY,
    inspect.Parameter.POSITIONAL_OR_KEYWORD,
    inspect.Parameter.VAR_POSITIONAL,
)


def _is_stub(function: Callable[..., Any]) -> bool:
    """Return True when the function body is only a docstring and a placeholder."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    node = tree.body[0]
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]
    if len(body) != 1:
        return False
    statement = body[0]
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
        return statement.value.value is Ellipsis
    if isinstance(statement, ast.Raise) and statement.exc is not None:
        raised = statement.exc
        target = raised.func if isinstance(raised, ast.Call) else raised
        return isinstance(target, ast.Name) and target.id == "NotImplementedError"
    return False


def test_all_is_exactly_the_spec_public_api() -> None:
    expected = {
        *SPEC_FUNCTIONS,
        *SPEC_TYPES,
        *SPEC_EXCEPTIONS,
        *SPEC_VALUES,
        *LEGACY_NAMES,
    }

    assert set(imgwtools.__all__) == expected
    assert len(imgwtools.__all__) == len(set(imgwtools.__all__))


@pytest.mark.parametrize("name", REMOVED_NAMES)
def test_removed_name_is_absent_from_public_modules(name: str) -> None:
    for module in _MODULES:
        assert not hasattr(module, name), f"{module.__name__}.{name}"


def test_legacy_url_builder_module_is_gone() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("imgwtools.core.url_builder")


def test_store_exports_are_the_same_objects_as_package_exports() -> None:
    assert set(imgwtools.store.__all__) <= set(imgwtools.__all__)
    for name in imgwtools.store.__all__:
        assert getattr(imgwtools.store, name) is getattr(imgwtools, name), name


@pytest.mark.parametrize("name", SPEC_FUNCTIONS)
def test_spec_function_is_real_implementation(name: str) -> None:
    function = getattr(imgwtools, name)

    assert inspect.isfunction(function)
    assert function.__module__ not in ("imgwtools", "imgwtools.store")
    assert not _is_stub(function), f"{name} jest zaślepką"


@pytest.mark.parametrize(
    "name", [n for n in SPEC_TYPES if inspect.isclass(getattr(imgwtools, n))]
)
def test_spec_dataclass_is_frozen(name: str) -> None:
    cls = getattr(imgwtools, name)
    params = cls.__dict__.get("__dataclass_params__")

    assert dataclasses.is_dataclass(cls)
    assert params is not None and params.frozen


@pytest.mark.parametrize(
    "name", [n for n in SPEC_FUNCTIONS if n not in LEGACY_POSITIONAL]
)
def test_new_functions_are_keyword_only_after_first_object(name: str) -> None:
    parameters = list(inspect.signature(getattr(imgwtools, name)).parameters.values())
    positional = [p for p in parameters if p.kind in _POSITIONAL]

    assert len(positional) <= 1, f"{name}: {[p.name for p in positional]}"
    assert all(p.kind is not inspect.Parameter.VAR_POSITIONAL for p in positional)


@pytest.mark.parametrize("name", sorted(LEGACY_POSITIONAL))
def test_legacy_downloads_keep_positional_parameters(name: str) -> None:
    parameters = inspect.signature(getattr(imgwtools, name)).parameters
    positional = tuple(n for n, p in parameters.items() if p.kind in _POSITIONAL)

    assert positional == LEGACY_POSITIONAL[name]
    assert parameters["timeout"].kind is inspect.Parameter.KEYWORD_ONLY


_BLOCKED_IMPORT = """
import importlib.abc
import sys


class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "pyarrow":
            raise ImportError(f"zablokowano {name}")
        return None


sys.meta_path.insert(0, _Block())
import imgwtools
from imgwtools import *  # noqa: F403

missing = [n for n in imgwtools.__all__ if n not in globals()]
assert not missing, missing
# click comes with httpx's optional CLI when installed, so it is not checked.
heavy = {"pyarrow", "fastapi", "starlette", "uvicorn", "typer"}
loaded = sorted(m for m in sys.modules if m.split(".")[0] in heavy)
assert not loaded, loaded
assert "imgwtools.testing" not in sys.modules
print("ok")
"""


def test_import_loads_no_optional_dependency() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _BLOCKED_IMPORT],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
