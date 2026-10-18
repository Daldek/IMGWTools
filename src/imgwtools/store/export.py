"""Export of one station series to a self-describing CSV, published atomically."""

from __future__ import annotations

import csv
import os
import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from imgwtools.datasets import get_dataset
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.models import NormalizedRecord
from imgwtools.store.reader import read_series, read_series_index
from imgwtools.store.series import _PROCESSED
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    Progress,
    ProgressHook,
)
from imgwtools.store.writer import _fsync_dir

_FORMATS = ("csv",)
_YEAR_TYPES = ("hydrological", "calendar")
_PROGRESS_ROWS = 256
_CANCELLED = "Anulowano eksport szeregu; plik docelowy pozostaje nietknięty"


def _number(value: float) -> str:
    """Shortest round-trip decimal text with a dot and no exponent."""
    text = repr(float(value))
    return format(Decimal(text), "f") if "e" in text or "E" in text else text


def _timestamp(value: date | datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _cancelled(cancel: Cancel | None) -> bool:
    return cancel is not None and cancel()


def export_series(
    version: PathArg,
    /,
    *,
    station: str,
    path: PathArg,
    variables: Iterable[str],
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv"] = "csv",
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Path:
    """
    Write values, flags and both IMGW-PIB attribution formulas of one station to CSV.

    ``year_type=None`` uses the publication convention of ``series.json`` (hydro
    ``hydrological``, meteo ``calendar``). The target is replaced only by a fully
    written and fsynced ``.part`` file; cancellation or failure leaves it untouched.

    The CSV (UTF-8 without BOM, comma, dot decimal, CRLF rows) has a single
    header row ``date,year,<V> [<unit>],<V>_flag,…,attribution_source,
    attribution_processed``; half-year series add ``period`` and ``<V>_start`` /
    ``<V>_end`` extremum dates. Both attribution formulas appear only in the
    first data row. Missing values are empty cells flagged ``missing``.

    Parameters
    ----------
    version : str or os.PathLike
        Series version directory or its ``series.json`` file.
    station : str
        Nine-digit station code present in the series.
    path : str or os.PathLike
        Target CSV file; its parent directory must already exist.
    variables : Iterable[str]
        Non-empty collection of dataset variable names; duplicates are merged,
        column order follows this collection, a single string is rejected.
    year_type : {"hydrological", "calendar"} or None, optional
        Convention of the ``year`` column: ``hydro_year`` or the calendar year
        of ``date``. ``None`` uses ``series.json`` ``year_type``.
    format : {"csv"}, optional
        Output format.
    on_progress : ProgressHook or None, optional
        Called every 256 rows and once after the export with ``unit="row"``.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice after a successful export.
    cancel : Cancel or None, optional
        Polled before writing, every 256 rows and before replacing the target;
        returning ``True`` aborts the export.

    Returns
    -------
    pathlib.Path
        Path of the written CSV file.

    Raises
    ------
    IMGWValidationError
        If ``format`` or ``year_type`` is unsupported, ``variables`` is invalid,
        ``year_type="calendar"`` is requested for a half-year series, the
        target is a directory or its parent directory does not exist, or the
        arguments are rejected by :func:`read_series`.
    IMGWStoreError
        If the export is cancelled, or ``series.json`` or its sidecar does not
        exist.
    IMGWStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    IMGWDataError
        If the station series is empty or the series data is invalid.
    """
    if format not in _FORMATS:
        raise IMGWValidationError(
            f"Nieobsługiwany format eksportu {format!r}; dostępne: {', '.join(_FORMATS)}"
        )
    if year_type is not None and year_type not in _YEAR_TYPES:
        raise IMGWValidationError(
            f"Nieznany year_type {year_type!r}; dozwolone: {', '.join(_YEAR_TYPES)}"
        )
    if isinstance(variables, str):
        raise IMGWValidationError(
            "variables musi być listą nazw zmiennych, nie pojedynczym tekstem"
        )
    names = tuple(dict.fromkeys(variables))
    index = read_series_index(version)
    descriptor = get_dataset(index.dataset)
    half_year = descriptor.time_unit == "half_year"
    chosen = year_type or index.year_type
    if half_year and chosen == "calendar":
        raise IMGWValidationError(
            f"Charakterystyki półroczne i roczne ({index.dataset}) mają tylko lata hydrologiczne; year_type='calendar' niedozwolony"
        )
    target = Path(path).expanduser()
    if target.is_dir():
        raise IMGWValidationError(f"Ścieżka eksportu wskazuje katalog: {target}")
    if not target.parent.is_dir():
        raise IMGWValidationError(
            f"Katalog docelowy eksportu nie istnieje: {target.parent}"
        )
    records = read_series(version, station=station, variables=names)
    first = next(records, None)
    if first is None:
        raise IMGWDataError(
            f"Szereg stacji {station} w {index.dataset} jest pusty; eksport odrzucono, by nie utracić formuł atrybucji"
        )
    if _cancelled(cancel):
        raise IMGWStoreError(_CANCELLED)

    header = ["date", "year", *(["period"] if half_year else [])]
    for name in names:
        header += [f"{name} [{descriptor.variables[name]}]", f"{name}_flag"]
        if half_year:
            header += [f"{name}_start", f"{name}_end"]
    header += ["attribution_source", "attribution_processed"]
    attribution = [descriptor.license.attribution, _PROCESSED]
    total = index.stations[station].rows

    def row(record: NormalizedRecord) -> list[str]:
        year = record.hydro_year if chosen == "hydrological" else record.date.year
        cells = [
            record.date.isoformat(),
            str(year),
            *([record.period or ""] if half_year else []),
        ]
        for name in names:
            measurement = record.measurements[name]
            cells += [
                "" if measurement.value is None else _number(measurement.value),
                measurement.flag,
            ]
            if half_year:
                start, end = record.extrema_dates.get(name, (None, None))
                cells += [_timestamp(start), _timestamp(end)]
        return cells

    part = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    written = 0
    try:
        with part.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerow([*row(first), *attribution])
            written = 1
            for record in records:
                writer.writerow([*row(record), "", ""])
                written += 1
                if written % _PROGRESS_ROWS == 0:
                    if _cancelled(cancel):
                        raise IMGWStoreError(_CANCELLED)
                    if on_progress is not None:
                        on_progress(
                            Progress(
                                written,
                                total,
                                "row",
                                "written",
                                f"Stacja {station}: {written} wierszy",
                            )
                        )
            stream.flush()
            os.fsync(stream.fileno())
        if _cancelled(cancel):
            raise IMGWStoreError(_CANCELLED)
        os.replace(part, target)
        _fsync_dir(target.parent)
    finally:
        part.unlink(missing_ok=True)
    if on_progress is not None:
        on_progress(
            Progress(
                written,
                total,
                "row",
                "written",
                f"Wyeksportowano szereg stacji {station} do {target}",
            )
        )
    if on_notice is not None:
        on_notice(
            Notice(
                "info",
                "license_terms",
                (
                    f"{attribution[0]}. {attribution[1]}. Do użytku prywatnego i badawczego; inne zastosowania wymagają "
                    "sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości."
                ),
            )
        )
    return target
