"""PMAXTP store keyed by the grid cell reported by the IMGW API."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from imgwtools._version import __version__
from imgwtools.datasets import (
    ProviderDescriptor,
    _license_document,
    get_dataset,
    get_provider,
)
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWStoreError,
    IMGWValidationError,
    io_error,
)
from imgwtools.fetch import _check_pmaxtp_payload, _validate_poland_coords
from imgwtools.messages import message, reason
from imgwtools.models import PMaXTPData, PMaXTPResult
from imgwtools.store.catalog import (
    LICENSE_NOTICE,
    RootArg,
    _cancelled,
    _handle,
    _http,
    _newest_downloaded,
    _publish_version,
)
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    PlanAction,
    PMaXTPStoreResult,
    Progress,
    ProgressHook,
    StorePlan,
)
from imgwtools.store.writer import (
    _canonical,
    _check_kartograf,
    _existing,
    _utc,
    _validate_slot,
)
from imgwtools.urls import build_pmaxtp_url

CELL_FILE = "cell.json"
RESPONSE_FILE = "response.json"
CELL_SCHEMA = "imgw-pmaxtp/1"
PMAXTP_DATASET = "pl.imgw.pmaxtp"
_METHODS = ("POT", "AMP")
_TABLES = ("ks", "sg", "rb")

Method = Literal["POT", "AMP"]


def _validate_method(method: object) -> Method:
    if method not in _METHODS:
        raise IMGWValidationError(
            message("pmaxtp.unknown_pmaxtp_method_allowed_pot", method=method),
            details={"option": "method", "allowed": list(_METHODS)},
        )
    return cast(Method, method)


def _validate_index(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IMGWValidationError(
            message("pmaxtp.cell_index_must_non_negative", name=name, value=value),
            details={"option": name, "value": str(value)},
        )
    return value


def _validate_cell(ind_x: int | None, ind_y: int | None) -> tuple[int, int] | None:
    if ind_x is None and ind_y is None:
        return None
    if ind_x is None or ind_y is None:
        raise IMGWValidationError(
            message("pmaxtp.give_both_cell_indices_ind"),
            details={"option": "ind_y" if ind_y is None else "ind_x"},
        )
    return _validate_index("ind_x", ind_x), _validate_index("ind_y", ind_y)


def _slot(method: Method, ind_x: int, ind_y: int) -> str:
    return f"pmaxtp/versions/{method}/{ind_x}_{ind_y}"


def _table(name: str, value: object) -> dict[str, dict[str, float]]:
    if not isinstance(value, Mapping) or not value:
        raise IMGWDataError(
            message("pmaxtp.pmaxtp_response_empty_invalid_table", name=name)
        )
    table: dict[str, dict[str, float]] = {}
    for duration, row in value.items():
        if not isinstance(row, Mapping) or not row:
            raise IMGWDataError(
                message(
                    "pmaxtp.pmaxtp_response_empty_row", name=name, duration=duration
                )
            )
        values: dict[str, float] = {}
        for probability, number in row.items():
            if isinstance(number, bool) or not isinstance(number, int | float):
                raise IMGWDataError(
                    message(
                        "pmaxtp.pmaxtp_response_value_not_number",
                        name=name,
                        duration=duration,
                        probability=probability,
                    )
                )
            values[str(probability)] = number
        table[str(duration)] = values
    return table


def _cell_document(
    payload: object, method: Method, latitude: float, longitude: float
) -> dict[str, Any]:
    """Validate the API response and build the canonical cell document."""
    if not isinstance(payload, Mapping):
        raise IMGWDataError(message("pmaxtp.unexpected_format_pmaxtp_response"))
    _check_pmaxtp_payload(payload, latitude, longitude)
    point = payload.get("point")
    data = payload.get("data")
    if not isinstance(point, Mapping):
        raise IMGWDataError(message("pmaxtp.pmaxtp_response_has_no_description"))
    try:
        ind_x = _validate_index("indX", point["indX"])
        ind_y = _validate_index("indY", point["indY"])
    except (KeyError, IMGWValidationError) as exc:
        raise IMGWDataError(message("pmaxtp.pmaxtp_response_has_no_valid")) from exc
    center = {"lon": point.get("dataLon"), "lat": point.get("dataLat")}
    if any(
        isinstance(v, bool) or not isinstance(v, int | float) for v in center.values()
    ):
        raise IMGWDataError(message("pmaxtp.pmaxtp_response_has_no_cell"))
    if not isinstance(data, Mapping) or not data:
        raise IMGWDataError(message("pmaxtp.pmaxtp_response_has_no_data"))
    return {
        "schema": CELL_SCHEMA,
        "method": method,
        "ind_x": ind_x,
        "ind_y": ind_y,
        "center": center,
        "data": {name: _table(name, data.get(name)) for name in _TABLES},
    }


def _result(
    document: Mapping[str, Any], *, latitude: float, longitude: float
) -> PMaXTPResult:
    data = document["data"]
    return PMaXTPResult(
        method=document["method"],
        latitude=latitude,
        longitude=longitude,
        data=PMaXTPData(ks=data["ks"], sg=data["sg"], rb=data["rb"]),
    )


def _provider() -> ProviderDescriptor:
    return get_provider(get_dataset(PMAXTP_DATASET).provider)


def _license() -> dict[str, str]:
    license_ = _license_document(get_dataset(PMAXTP_DATASET).license)
    license_["attribution"] = (
        f"{license_['attribution']}. {_provider().processed_attribution}"
    )
    return license_


def _current_cell(
    root: Path, method: Method, ind_x: int, ind_y: int
) -> tuple[Path, dict[str, Any]] | None:
    slot = _validate_slot(root, _slot(method, ind_x, ind_y))
    return _newest_downloaded(_existing(slot, CELL_FILE))


def check_pmaxtp(
    root: RootArg,
    /,
    *,
    latitude: float,
    longitude: float,
    method: Literal["POT", "AMP"] = "POT",
    ind_x: int | None = None,
    ind_y: int | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Describe the planned PMAXTP sync without any HTTP request or write.

    The endpoint offers no update signal, so freshness is always ``unverifiable``; with
    indices the plan also reports whether the cell already exists locally.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    latitude : float
        Latitude of the point within Poland.
    longitude : float
        Longitude of the point within Poland.
    method : {"POT", "AMP"}, optional
        PMAXTP estimation method; default ``"POT"``.
    ind_x : int or None, optional
        Expected grid cell X index; must be given together with ``ind_y``.
    ind_y : int or None, optional
        Expected grid cell Y index; must be given together with ``ind_x``.
    on_progress : ProgressHook or None, optional
        Called once with an ``unverifiable`` progress event.
    on_notice : NoticeHook or None, optional
        Called once with a ``source_unverifiable`` warning.
    cancel : Cancel or None, optional
        Polled once before planning; returning ``True`` yields a cancelled plan.

    Returns
    -------
    StorePlan
        Plan with a single ``PlanAction("pmaxtp sync", "unverifiable", ...)``
        describing the local version, or a plan with ``cancelled=True``.

    Raises
    ------
    IMGWValidationError
        If the method, point or cell indices are invalid, or the root path
        contains ``..``.
    IMGWStoreError
        If the root is not a supported store or a path contains a symbolic
        link.
    IMGWStoreConflictError
        If a stored version of the cell is corrupted.
    """
    handle = _handle(root)
    method = _validate_method(method)
    _validate_poland_coords(latitude, longitude)
    cell = _validate_cell(ind_x, ind_y)
    now = datetime.now(UTC)
    if _cancelled(cancel):
        action = PlanAction("pmaxtp sync", "unverifiable", message("common.cancelled"))
        return StorePlan(
            "imgw-plan/1", handle.root, now, (), {}, (action,), cancelled=True
        )
    if cell is None:
        detail = message(
            "pmaxtp.cell_unknown_without_download",
            method=method,
            latitude=latitude,
            longitude=longitude,
        )
    else:
        current = _current_cell(handle.root, method, *cell)
        where = (
            message(
                "pmaxtp.local_version",
                current=current[0].relative_to(handle.root).as_posix(),
            )
            if current
            else message("pmaxtp.no_local_version")
        )
        detail = message(
            "pmaxtp.cell_cannot_check",
            method=method,
            cell=cell[0],
            cell_2=cell[1],
            where=where,
        )
    if on_notice is not None:
        on_notice(Notice("warning", "source_unverifiable", detail))
    if on_progress is not None:
        on_progress(Progress(1, 1, "cell", "unverifiable", detail))
    return StorePlan(
        schema="imgw-plan/1",
        root=handle.root,
        checked_at=now,
        items=(),
        series_state={},
        actions=(PlanAction("pmaxtp sync", "unverifiable", detail),),
    )


def sync_pmaxtp(
    root: RootArg,
    /,
    *,
    latitude: float,
    longitude: float,
    method: Literal["POT", "AMP"] = "POT",
    ind_x: int | None = None,
    ind_y: int | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> PMaXTPStoreResult:
    """
    Fetch PMAXTP once and store it under the cell indices returned by the API.

    Points in the same cell and method share one version; identical ``cell.json`` is
    ``unchanged`` and writes nothing. Given ``ind_x``/``ind_y`` must match the response
    or nothing is written. A new version also keeps the raw API response byte for byte
    as ``response.json``; its SHA-256 and size are recorded in the ``cell.json`` sidecar
    under ``extra.response`` (the version identity remains the ``cell.json`` SHA-256).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    latitude : float
        Latitude of the requested point within Poland.
    longitude : float
        Longitude of the requested point within Poland.
    method : {"POT", "AMP"}, optional
        PMAXTP estimation method; default ``"POT"``.
    ind_x : int or None, optional
        Expected grid cell X index; must be given together with ``ind_y``.
    ind_y : int or None, optional
        Expected grid cell Y index; must be given together with ``ind_x``.
    on_progress : ProgressHook or None, optional
        Called once with the ``new`` or ``unchanged`` progress event.
    on_notice : NoticeHook or None, optional
        Called with the license notice when a new version is created and with a
        ``leftover_incoming`` warning for every removed staging directory older
        than 24 hours.
    cancel : Cancel or None, optional
        Polled before the request and before writing; returning ``True``
        yields a ``cancelled`` result without writing.

    Returns
    -------
    PMaXTPStoreResult
        ``status`` is ``"new"``, ``"unchanged"`` or ``"cancelled"``;
        ``version`` is the ``cell.json`` path (``None`` when cancelled) and
        ``result`` holds the data for the requested point.

    Raises
    ------
    IMGWValidationError
        If the method, point or cell indices are invalid, the given indices
        differ from the API response, the API reports the point outside its
        grid (e.g. Kaliningrad, Lviv, the Baltic Sea), or the root path
        contains ``..``.
    IMGWConnectionError
        If the PMAXTP request fails.
    IMGWDataError
        If the response is not JSON, reports another error, lacks cell indices
        or centre, or has empty data tables.
    IMGWStoreError
        If the root is not a supported store, a path contains a symbolic link
        or the store overlaps a Kartograf store.
    IMGWStoreConflictError
        If a stored version is corrupted, the version directory collides with
        different content, or the file system cannot publish atomically.
    """
    handle = _handle(root)
    method = _validate_method(method)
    _validate_poland_coords(latitude, longitude)
    expected = _validate_cell(ind_x, ind_y)
    _check_kartograf(handle.root)
    if _cancelled(cancel):
        return PMaXTPStoreResult("cancelled", None, ind_x, ind_y, None)
    response = _http("GET", build_pmaxtp_url(latitude, longitude, method=method))
    try:
        payload = response.json()
    except ValueError as exc:
        raise IMGWDataError(
            message("pmaxtp.invalid_json_response_from_pmaxtp")
        ) from exc
    document = _cell_document(payload, method, latitude, longitude)
    cell = (document["ind_x"], document["ind_y"])
    if expected is not None and expected != cell:
        raise IMGWValidationError(
            message(
                "pmaxtp.given_cell_indices_differ_from",
                expected_x=expected[0],
                expected_y=expected[1],
                cell_x=cell[0],
                cell_y=cell[1],
            )
        )
    result = _result(document, latitude=latitude, longitude=longitude)
    if _cancelled(cancel):
        return PMaXTPStoreResult("cancelled", None, cell[0], cell[1], None)
    data = _canonical(document)
    sha = hashlib.sha256(data).hexdigest()
    current = _current_cell(handle.root, method, *cell)
    if current is not None and current[1]["sha256"] == sha:
        if on_progress is not None:
            on_progress(
                Progress(
                    1,
                    1,
                    "cell",
                    "unchanged",
                    message("pmaxtp.cell_unchanged", cell=cell[0], cell_2=cell[1]),
                )
            )
        return PMaXTPStoreResult("unchanged", current[0], cell[0], cell[1], result)
    now = datetime.now(UTC)
    label = now.date().isoformat()
    meta = {
        "schema": "imgw-meta/1",
        "producer": "imgwtools",
        "producer_version": __version__,
        "dataset": PMAXTP_DATASET,
        "country": "PL",
        "provider": "IMGW-PIB",
        "request": {
            "method": method,
            "ind_x": cell[0],
            "ind_y": cell[1],
            "latitude": latitude,
            "longitude": longitude,
            "url": str(response.url),
        },
        "license": _license(),
        "downloaded_at": _utc(now),
        "sha256": sha,
        "size_bytes": len(data),
        "extra": {
            "version": {"label": label, "label_source": "downloaded"},
            "derived": "pmaxtp",
            "response": {
                "name": RESPONSE_FILE,
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "size_bytes": len(response.content),
            },
        },
    }
    path, created = _publish_version(
        handle.root,
        slot=_slot(method, *cell),
        name=CELL_FILE,
        data=data,
        meta=meta,
        label=label,
        on_notice=on_notice,
        attachments={RESPONSE_FILE: response.content},
    )
    status: Literal["new", "unchanged"] = "new" if created else "unchanged"
    if on_progress is not None:
        on_progress(
            Progress(
                1,
                1,
                "cell",
                status,
                message(
                    "pmaxtp.cell_published",
                    cell=cell[0],
                    cell_2=cell[1],
                    name=path.parent.name,
                ),
            )
        )
    if created and on_notice is not None:
        on_notice(
            Notice(
                "info",
                LICENSE_NOTICE,
                _provider().license_notice(_license()["attribution"]),
            )
        )
    return PMaXTPStoreResult(status, path, cell[0], cell[1], result)


def read_pmaxtp(
    root: RootArg,
    /,
    *,
    ind_x: int,
    ind_y: int,
    method: Literal["POT", "AMP"] = "POT",
    version: PathArg | None = None,
) -> PMaXTPResult:
    """
    Read a stored cell offline; ``version`` selects a version directory or its ``cell.json``.

    ``latitude``/``longitude`` of the result are the cell centre (the stored document keeps
    no requested point). No network access and no pyarrow are needed.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Store root directory or an open store handle.
    ind_x : int
        Grid cell X index.
    ind_y : int
        Grid cell Y index.
    method : {"POT", "AMP"}, optional
        PMAXTP estimation method; default ``"POT"``.
    version : str, os.PathLike or None, optional
        Version directory or its ``cell.json``, absolute or relative to the
        root; ``None`` reads the current version of the cell.

    Returns
    -------
    PMaXTPResult
        Stored precipitation quantiles located at the cell centre.

    Raises
    ------
    IMGWValidationError
        If the method or indices are invalid, ``version`` does not belong to
        the cell, or the root path contains ``..``.
    IMGWStoreError
        If the root is not a supported store, no version of the cell (or the
        given version) is stored (code ``not_found``), or a path contains a
        symbolic link.
    IMGWStoreConflictError
        If a stored version of the cell is corrupted.
    IMGWDataError
        If the ``cell.json`` document is corrupted or inconsistent with its
        path; with code ``io_error`` (``details.path``) if the system cannot
        read a version of the cell.
    """
    handle = _handle(root)
    method = _validate_method(method)
    cell = (_validate_index("ind_x", ind_x), _validate_index("ind_y", ind_y))
    slot = _validate_slot(handle.root, _slot(method, *cell))
    if version is None:
        current = _current_cell(handle.root, method, *cell)
        if current is None:
            raise IMGWStoreError(
                message(
                    "pmaxtp.no_stored_pmaxtp_cell",
                    method=method,
                    cell_x=cell[0],
                    cell_y=cell[1],
                ),
                code="not_found",
            )
        path = current[0]
    else:
        given = Path(version)
        given = given if given.is_absolute() else handle.root / given
        given = given / CELL_FILE if given.name != CELL_FILE else given
        if given.parent.parent != slot:
            raise IMGWValidationError(
                message(
                    "pmaxtp.version_does_not_belong_cell",
                    version=version,
                    method=method,
                    cell_x=cell[0],
                    cell_y=cell[1],
                )
            )
        matches = [entry for entry in _existing(slot, CELL_FILE) if entry[0] == given]
        if not matches:
            raise IMGWStoreError(
                message("pmaxtp.no_version_pmaxtp_cell", version=version),
                code="not_found",
            )
        path = matches[0][0]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema") != CELL_SCHEMA:
            raise ValueError(
                message("pmaxtp.unsupported_schema", schema=document.get("schema"))
            )
        if (document["method"], document["ind_x"], document["ind_y"]) != (
            method,
            *cell,
        ):
            raise ValueError(message("pmaxtp.method_indices_do_not_match"))
        center = document["center"]
        return _result(
            document, latitude=float(center["lat"]), longitude=float(center["lon"])
        )
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise IMGWDataError(
            message("pmaxtp.corrupt_pmaxtp_cell", path=path, exc=reason(exc))
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc
