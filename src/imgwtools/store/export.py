"""Export of stored archive records and station series as text lines or atomic files."""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, overload

from imgwtools._parsing.meteo import DATASET_ATTRIBUTES
from imgwtools.datasets import DatasetDescriptor, get_dataset
from imgwtools.exceptions import IMGWCancelledError, IMGWDataError, IMGWValidationError
from imgwtools.models import NormalizedRecord
from imgwtools.store.catalog import RootArg
from imgwtools.store.reader import (
    _archive_main,
    _open,
    _series_path,
    _variables,
    read_archive,
    read_meta,
    read_series,
    read_series_index,
)
from imgwtools.store.series import _PROCESSED
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    Progress,
    ProgressHook,
)
from imgwtools.store.writer import _MARKER, _fsync_dir

_SERIES_FORMATS = ("csv",)
_ARCHIVE_FORMATS = ("csv", "jsonl")
_YEAR_TYPES = ("hydrological", "calendar")
_PROGRESS_ROWS = 256
_CANCELLED = "Anulowano eksport; plik docelowy pozostaje nietknięty"
_TERMS = (
    "Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia "
    "warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości."
)


def _number(value: float) -> str:
    """Shortest round-trip decimal text with a dot and no exponent."""
    text = repr(float(value))
    return format(Decimal(text), "f") if "e" in text or "E" in text else text


def _timestamp(value: date | datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _check_cancel(cancel: Cancel | None) -> None:
    if cancel is not None and cancel():
        raise IMGWCancelledError(_CANCELLED)


def _format(value: object, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise IMGWValidationError(
            f"Nieobsługiwany format eksportu {value!r}; dostępne: {', '.join(allowed)}",
            details={"option": "format", "value": str(value), "allowed": list(allowed)},
        )


def _target(path: PathArg) -> Path:
    """Absolute export target: a file in an existing directory outside every IMGW store."""
    target = Path(path).expanduser().absolute()
    details = {"option": "path", "value": str(target)}
    if target.is_dir():
        raise IMGWValidationError(
            f"Ścieżka eksportu wskazuje katalog: {target}", details=details
        )
    if not target.parent.is_dir():
        raise IMGWValidationError(
            f"Katalog docelowy eksportu nie istnieje: {target.parent}", details=details
        )
    store = next(
        (item for item in target.resolve().parents if (item / _MARKER).is_file()), None
    )
    if store is not None:
        raise IMGWValidationError(
            f"Eksport musi być zapisany poza magazynem IMGW ({store}): {target}",
            details=details,
        )
    return target


def _license(dataset: str, on_notice: NoticeHook | None) -> None:
    if on_notice is not None:
        attribution = get_dataset(dataset).license.attribution
        on_notice(
            Notice("info", "license_terms", f"{attribution}. {_PROCESSED}. {_TERMS}")
        )


def _csv_lines(rows: Iterable[Sequence[str]]) -> Iterator[str]:
    """CSV text lines (comma, minimal quoting, CRLF) of cell rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for cells in rows:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(cells)
        yield buffer.getvalue()


def _csv_line(cells: Sequence[str]) -> str:
    return next(_csv_lines([cells]))


class _Lines:
    """Lines of one export: header lines, then data rows with cancellation and progress."""

    def __init__(
        self,
        head: tuple[str, ...],
        rows: Iterable[str],
        *,
        total: int | None,
        label: str,
        on_progress: ProgressHook | None,
        cancel: Cancel | None,
    ) -> None:
        self._head = head
        self._rows = rows
        self._total = total
        self._label = label
        self._on_progress = on_progress
        self._cancel = cancel
        self.written = 0

    def __iter__(self) -> Iterator[str]:
        yield from self._head
        for text in self._rows:
            yield text
            self.written += 1
            if self.written % _PROGRESS_ROWS == 0:
                _check_cancel(self._cancel)
                if self._total is not None and self._on_progress is not None:
                    self._on_progress(
                        Progress(
                            self.written,
                            self._total,
                            "row",
                            "written",
                            f"{self._label}: {self.written} wierszy",
                        )
                    )

    def finish(self, message: str) -> None:
        if self._on_progress is not None:
            total = self.written if self._total is None else self._total
            self._on_progress(Progress(self.written, total, "row", "written", message))


def _iterate(lines: _Lines, done: str) -> Iterator[str]:
    yield from lines
    lines.finish(done)


def _deliver(
    lines: _Lines, *, target: Path | None, cancel: Cancel | None, done: str
) -> Path | Iterator[str]:
    """
    Return the lazy lines, or publish them atomically to ``target``.

    The target is replaced only by a fully written and fsynced hidden unique
    ``.part`` file beside it; cancellation or failure removes the ``.part``
    and leaves the target untouched.
    """
    if target is None:
        return _iterate(lines, done)
    part = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    try:
        with part.open("x", encoding="utf-8", newline="") as stream:
            for text in lines:
                stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _check_cancel(cancel)
        os.replace(part, target)
        _fsync_dir(target.parent)
    finally:
        part.unlink(missing_ok=True)
    lines.finish(f"{done} do {target}")
    return target


def _record_json(record: NormalizedRecord) -> dict[str, object]:
    return {
        "station_code": record.station_code,
        "dataset": record.dataset,
        "date": record.date.isoformat(),
        "hydro_year": record.hydro_year,
        "period": record.period,
        "measurements": {
            name: {"value": measurement.value, "flag": measurement.flag}
            for name, measurement in record.measurements.items()
        },
        "attributes": dict(record.attributes),
        "extrema_dates": {
            name: [None if day is None else day.isoformat() for day in span]
            for name, span in record.extrema_dates.items()
        },
        "extrema_occurrences": dict(record.extrema_occurrences),
    }


def _extrema(record: NormalizedRecord, name: str) -> list[str]:
    """``<V>_start``, ``<V>_end`` and ``<V>_occurrences`` cells of a half-year record."""
    first, last = record.extrema_dates.get(name, (None, None))
    occurrences = record.extrema_occurrences.get(name)
    return [
        _timestamp(first),
        _timestamp(last),
        "" if occurrences is None else str(occurrences),
    ]


def _archive_row(
    record: NormalizedRecord,
    descriptor: DatasetDescriptor,
    attributes: tuple[str, ...],
) -> list[str]:
    unknown = sorted(
        {*record.measurements} - set(descriptor.variables)
        | {*record.attributes} - set(attributes)
    )
    if unknown:
        raise IMGWDataError(
            f"Rekord stacji {record.station_code} z {record.date} ma kolumny "
            f"spoza zbioru {record.dataset}: {', '.join(unknown)}"
        )
    half_year = descriptor.time_unit == "half_year"
    cells = [
        record.station_code,
        record.dataset,
        record.date.isoformat(),
        str(record.hydro_year),
        record.period or "",
    ]
    for name in descriptor.variables:
        measurement = record.measurements.get(name)
        if measurement is None:
            cells += ["", ""]
        else:
            cells += [
                "" if measurement.value is None else _number(measurement.value),
                measurement.flag,
            ]
        if half_year:
            cells += _extrema(record, name)
    cells += [record.attributes.get(key) or "" for key in attributes]
    return cells


def _archive_lines(
    records: Iterator[NormalizedRecord], format: str
) -> tuple[tuple[str, ...], Iterator[str]]:
    """Header lines and lazy data lines of archive records; no records give no lines."""
    first = next(records, None)
    if first is None:
        return (), iter(())

    def chained() -> Iterator[NormalizedRecord]:
        yield first
        yield from records

    if format == "jsonl":
        return (), (
            json.dumps(_record_json(record), ensure_ascii=False) + "\n"
            for record in chained()
        )
    descriptor = get_dataset(first.dataset)
    attributes = tuple(DATASET_ATTRIBUTES.get(first.dataset, ()))
    header = ["station_code", "dataset", "date", "hydro_year", "period"]
    for name, unit in descriptor.variables.items():
        header += [f"{name} [{unit}]", f"{name}_flag"]
        if descriptor.time_unit == "half_year":
            header += [f"{name}_start", f"{name}_end", f"{name}_occurrences"]
    header += attributes
    rows = (_archive_row(record, descriptor, attributes) for record in chained())
    return (_csv_line(header),), _csv_lines(rows)


@overload
def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    path: None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Iterator[str]: ...


@overload
def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    path: PathArg,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Path: ...


def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    path: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Path | Iterator[str]:
    """
    Export the normalized records of one stored archive version as CSV or JSONL.

    The stored bytes are verified against the sidecar (see
    :func:`read_archive`) before anything is returned or written. CSV (UTF-8
    without BOM, comma, CRLF rows) starts with the header ``station_code,
    dataset,date,hydro_year,period``, then ``<V> [<unit>],<V>_flag`` for every
    dataset variable (half-year datasets add ``<V>_start,<V>_end,
    <V>_occurrences``) and one column per qualitative attribute of the dataset
    (meteo ``precip_type`` etc.); a variable or attribute absent from a record
    gives empty cells. JSONL writes one object per record with the
    `NormalizedRecord` fields and LF line ends. An archive without records
    gives no lines.

    Parameters
    ----------
    version : str or os.PathLike
        Archive version directory, its main file or its sidecar; absolute or
        relative to ``root`` (to the working directory without ``root``).
    root : str, os.PathLike, StoreHandle or None, optional
        Store root, the base of a relative ``version``.
    format : {"csv", "jsonl"}, optional
        Output format.
    path : str, os.PathLike or None, optional
        Target file in an existing directory outside every IMGW store; written
        atomically through a hidden ``.part`` file. ``None`` (default) returns
        the lines instead, byte-identical to the file content.
    on_progress : ProgressHook or None, optional
        Called once after the export with ``unit="row"`` and the number of
        records.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice before the first line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 records and before replacing
        the target; returning ``True`` aborts the export.

    Returns
    -------
    pathlib.Path or Iterator[str]
        Absolute path of the written file when ``path`` is given, otherwise a
        lazy iterator of text lines with their line terminators.

    Raises
    ------
    IMGWValidationError
        If ``format`` is unsupported, ``version`` is not an archive version
        or is a station list version, or ``path`` is a directory, lies in a
        missing directory or inside an IMGW store.
    IMGWStoreError
        If the archive file or its sidecar does not exist (code
        ``not_found``) or ``root`` is not a supported store.
    IMGWCancelledError
        If ``cancel`` returns ``True``; the target stays untouched and no
        ``.part`` file remains. With ``path=None`` it may also be raised
        while iterating.
    IMGWDataError
        If the sidecar or the stored bytes are invalid; while iterating (or
        writing), if the archive content is malformed.
    OSError
        If the target cannot be written; the target stays untouched.
    """
    _format(format, _ARCHIVE_FORMATS)
    source = Path(version).expanduser()
    if root is not None:
        source = _open(root) / source
    records = read_archive(source)
    dataset = read_meta(_archive_main(source)).dataset
    target = None if path is None else _target(path)
    head, rows = _archive_lines(records, format)
    _check_cancel(cancel)
    _license(dataset, on_notice)
    lines = _Lines(
        head,
        rows,
        total=None,
        label=f"Archiwum {source}",
        on_progress=on_progress,
        cancel=cancel,
    )
    return _deliver(
        lines, target=target, cancel=cancel, done=f"Wyeksportowano archiwum {source}"
    )


@overload
def export_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv"] = "csv",
    path: None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Iterator[str]: ...


@overload
def export_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv"] = "csv",
    path: PathArg,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Path: ...


def export_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv"] = "csv",
    path: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Path | Iterator[str]:
    """
    Export values, flags and both IMGW-PIB attribution formulas of one station as CSV.

    ``year_type=None`` uses the publication convention of ``series.json`` (hydro
    ``hydrological``, meteo ``calendar``). Arguments and the station data are
    validated and read before anything is returned or written.

    The CSV (UTF-8 without BOM, comma, dot decimal, CRLF rows) has a single
    header row ``date,year,<V> [<unit>],<V>_flag,…,attribution_source,
    attribution_processed``; half-year series add ``period`` and ``<V>_start`` /
    ``<V>_end`` extremum dates with ``<V>_occurrences`` (number of merged IMGW
    rows). Both attribution formulas appear only in the first data row. Missing
    values are empty cells flagged ``missing``.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Series version directory, its ``series.json`` or its sidecar; absolute
        or relative to ``root`` (to the working directory without ``root``).
        Mutually exclusive with ``dataset``.
    root : str, os.PathLike, StoreHandle or None, optional
        Store root: the base of a relative ``version``, or with ``dataset``
        the store whose current series version is exported.
    dataset : str or None, optional
        Series dataset (key, slug or legacy alias) whose current version in
        ``root`` is exported.
    station : str
        Nine-digit station code present in the series.
    variables : Iterable[str] or None, optional
        Dataset variable names; duplicates are merged, column order follows
        this collection, a single string or an empty collection is rejected.
        ``None`` (default) means every variable of the dataset.
    start : datetime.date or None, optional
        First period start date to include (inclusive); ``None`` means no
        lower bound. Monthly and half-year periods are matched by their start.
    end : datetime.date or None, optional
        Last period start date to include (inclusive); ``None`` means no
        upper bound.
    year_type : {"hydrological", "calendar"} or None, optional
        Convention of the ``year`` column: ``hydro_year`` or the calendar year
        of ``date``. ``None`` uses ``series.json`` ``year_type``.
    format : {"csv"}, optional
        Output format.
    path : str, os.PathLike or None, optional
        Target CSV file in an existing directory outside every IMGW store;
        written atomically through a hidden ``.part`` file. ``None`` (default)
        returns the lines instead, byte-identical to the file content.
    on_progress : ProgressHook or None, optional
        Called every 256 rows and once after the export with ``unit="row"``.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice before the first line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 rows and before replacing the
        target; returning ``True`` aborts the export.

    Returns
    -------
    pathlib.Path or Iterator[str]
        Absolute path of the written CSV file when ``path`` is given,
        otherwise a lazy iterator of CSV lines ending with CRLF.

    Raises
    ------
    IMGWValidationError
        If ``format`` or ``year_type`` is unsupported, ``year_type="calendar"``
        is requested for a half-year series, ``path`` is a directory, lies in
        a missing directory or inside an IMGW store, or the arguments are
        rejected by :func:`read_series` (``version``/``dataset`` choice,
        station, ``variables``, ``start``/``end``).
    IMGWStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store.
    IMGWCancelledError
        If ``cancel`` returns ``True``; the target stays untouched and no
        ``.part`` file remains. With ``path=None`` it may also be raised
        while iterating.
    IMGWStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    IMGWDataError
        If the station series (within ``start``/``end``) is empty or the
        series data is invalid.
    OSError
        If the target cannot be written; the target stays untouched.
    """
    _format(format, _SERIES_FORMATS)
    if year_type is not None and year_type not in _YEAR_TYPES:
        raise IMGWValidationError(
            f"Nieznany year_type {year_type!r}; dozwolone: {', '.join(_YEAR_TYPES)}",
            details={
                "option": "year_type",
                "value": str(year_type),
                "allowed": list(_YEAR_TYPES),
            },
        )
    series = _series_path(version, root=root, dataset=dataset)
    index = read_series_index(series)
    descriptor = get_dataset(index.dataset)
    names = _variables(variables, descriptor)
    half_year = descriptor.time_unit == "half_year"
    chosen = year_type or index.year_type
    if half_year and chosen == "calendar":
        raise IMGWValidationError(
            f"Charakterystyki półroczne i roczne ({index.dataset}) mają tylko lata "
            "hydrologiczne; year_type='calendar' niedozwolony",
            details={"option": "year_type", "value": "calendar"},
        )
    target = None if path is None else _target(path)
    records = list(
        read_series(series, station=station, variables=names, start=start, end=end)
    )
    if not records:
        raise IMGWDataError(
            f"Szereg stacji {station} w {index.dataset} jest pusty w wybranym zakresie; "
            "eksport odrzucono, by nie utracić formuł atrybucji"
        )
    _check_cancel(cancel)
    _license(index.dataset, on_notice)

    header = ["date", "year", *(["period"] if half_year else [])]
    for name in names:
        header += [f"{name} [{descriptor.variables[name]}]", f"{name}_flag"]
        if half_year:
            header += [f"{name}_start", f"{name}_end", f"{name}_occurrences"]
    header += ["attribution_source", "attribution_processed"]
    attribution = (descriptor.license.attribution, _PROCESSED)

    def row(number: int, record: NormalizedRecord) -> list[str]:
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
                cells += _extrema(record, name)
        return [*cells, *(attribution if number == 0 else ("", ""))]

    lines = _Lines(
        (_csv_line(header),),
        _csv_lines(row(number, record) for number, record in enumerate(records)),
        total=len(records),
        label=f"Stacja {station}",
        on_progress=on_progress,
        cancel=cancel,
    )
    return _deliver(
        lines,
        target=target,
        cancel=cancel,
        done=f"Wyeksportowano szereg stacji {station}",
    )
