"""Export of stored archive records and station series as text lines or one plain file."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, overload

from imgwtools._parsing.meteo import DATASET_ATTRIBUTES
from imgwtools.datasets import DatasetDescriptor, get_dataset, get_provider
from imgwtools.exceptions import IMGWCancelledError, IMGWDataError, IMGWValidationError
from imgwtools.messages import message
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.output import OutputReport, Staging, plan_plain, refuse
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
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    Progress,
    ProgressHook,
)
from imgwtools.store.writer import _fsync_dir

_SERIES_FORMATS = ("csv",)
_ARCHIVE_FORMATS = ("csv", "jsonl")
_YEAR_TYPES = ("hydrological", "calendar")
_PROGRESS_ROWS = 256
_CANCELLED = message("export.cancelled")


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
            message(
                "export.unsupported_export_format_available",
                value=value,
                allowed=", ".join(allowed),
            ),
            details={"option": "format", "value": str(value), "allowed": list(allowed)},
        )


def _file(output: PathArg) -> Path:
    """Absolute path of the one output file of an export; a directory is no file."""
    target = Path(output).expanduser().absolute()
    if target.is_dir():
        raise IMGWValidationError(
            message("export.output_is_directory", target=target),
            details={"option": "output", "value": str(target)},
        )
    return target


def _target(output: PathArg | None, *, force: bool) -> Path | None:
    """
    Check the output of an export before anything is read for it (DEV-19.6).

    ``None`` streams the lines (and ``force`` then has nothing to replace). A
    file is checked like the target list of any plain write: an existing file
    without ``force`` and a file in a store are a ``conflict`` that lists the
    path; a missing directory is created by the write (DEV-19.8).
    """
    if output is None:
        if force:
            raise IMGWValidationError(
                message("export.force_needs_output"), details={"option": "output"}
            )
        return None
    target = _file(output)
    refuse(plan_plain(target.parent, [target.name], force=force), single=True)
    return target


def _attribution(descriptor: DatasetDescriptor) -> tuple[str, str]:
    """Source and processed-data attribution formulas of the dataset's provider."""
    processed = get_provider(descriptor.provider).processed_attribution
    return descriptor.license.attribution, processed


def _license(descriptor: DatasetDescriptor, on_notice: NoticeHook | None) -> None:
    if on_notice is not None:
        source, processed = _attribution(descriptor)
        provider = get_provider(descriptor.provider)
        on_notice(
            Notice(
                "info",
                "license_terms",
                provider.license_notice(f"{source}. {processed}"),
            )
        )


def _field_names(name: str, descriptor: DatasetDescriptor) -> list[str]:
    """``<V>_quality`` and ``<V>_source_flag`` columns of the dataset's extra fields."""
    return [f"{name}_{field}" for field in descriptor.measurement_fields]


def _measurement_cells(
    measurement: Measurement | None, descriptor: DatasetDescriptor
) -> list[str]:
    """Value, flag and extra field cells of one variable; empty without a measurement."""
    if measurement is None:
        return [""] * (2 + len(descriptor.measurement_fields))
    cells = [
        "" if measurement.value is None else _number(measurement.value),
        measurement.flag,
    ]
    for field in descriptor.measurement_fields:
        value = getattr(measurement, field)
        cells.append("" if value is None else str(value))
    return cells


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
                            message(
                                "export.rows_written",
                                label=self._label,
                                written=self.written,
                            ),
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
) -> OutputReport | Iterator[str]:
    """
    Return the lazy lines, or write them as the one plain file ``target``.

    The lines go to a staging directory beside the target
    (``<dir>/.imgw-incoming/<host>_<pid>_<token>/``), are hashed while they are
    written and fsynced, and the file is moved into place with ``os.replace``
    only when it is whole; cancellation, an error, SIGINT or SIGTERM leave the
    target as it was and remove the staging directory (DEV-19.7).
    """
    if target is None:
        return _iterate(lines, done)
    with Staging(target.parent) as staging:
        staged, size, sha256 = staging.write(text.encode("utf-8") for text in lines)
        _check_cancel(cancel)
        written = staging.commit(staged, target, size, sha256)
    _fsync_dir(target.parent)
    lines.finish(message("export.exported_to_file", done=done, target=target))
    return OutputReport(target, (written,))


def _record_json(
    record: NormalizedRecord, descriptor: DatasetDescriptor
) -> dict[str, object]:
    return {
        "station_code": record.station_code,
        "dataset": record.dataset,
        "date": record.date.isoformat(),
        "hydro_year": record.hydro_year,
        "period": record.period,
        "measurements": {
            name: {
                "value": measurement.value,
                "flag": measurement.flag,
                **{
                    field: getattr(measurement, field)
                    for field in descriptor.measurement_fields
                },
            }
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
            message(
                "export.record_station_from_has_columns",
                station_code=record.station_code,
                date=record.date,
                dataset=record.dataset,
                unknown=", ".join(unknown),
            )
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
        cells += _measurement_cells(record.measurements.get(name), descriptor)
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

    descriptor = get_dataset(first.dataset)
    if format == "jsonl":
        return (), (
            json.dumps(_record_json(record, descriptor), ensure_ascii=False) + "\n"
            for record in chained()
        )
    attributes = tuple(DATASET_ATTRIBUTES.get(first.dataset, ()))
    header = ["station_code", "dataset", "date", "hydro_year", "period"]
    for name, unit in descriptor.variables.items():
        header += [f"{name} [{unit}]", f"{name}_flag", *_field_names(name, descriptor)]
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
    output: None = None,
    force: bool = False,
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
    output: PathArg,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport: ...


def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    output: PathArg | None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport | Iterator[str]:
    """
    Export the normalized records of one stored archive version as CSV or JSONL.

    The stored bytes are verified against the sidecar (see
    :func:`read_archive`) before anything is returned or written. CSV (UTF-8
    without BOM, comma, CRLF rows) starts with the header ``station_code,
    dataset,date,hydro_year,period``, then ``<V> [<unit>],<V>_flag`` for every
    dataset variable (ČHMÚ meteo adds ``<V>_quality,<V>_source_flag``,
    half-year datasets ``<V>_start,<V>_end,<V>_occurrences``) and one column
    per qualitative attribute of the dataset (meteo ``precip_type`` etc.); a
    variable or attribute absent from a record gives empty cells. JSONL
    writes one object per record with the `NormalizedRecord` fields (the
    ``Measurement`` fields ``quality`` and ``source_flag`` only for datasets
    that fill them) and LF line ends. An archive without records gives no
    lines.

    Parameters
    ----------
    version : str or os.PathLike
        Archive version directory, its main file or its sidecar; absolute or
        relative to ``root`` (to the working directory without ``root``).
    root : str, os.PathLike, StoreHandle or None, optional
        Store root, the base of a relative ``version``.
    format : {"csv", "jsonl"}, optional
        Output format.
    output : str, os.PathLike or None, optional
        The one plain file to write (DEV-19.1): its directory is created when
        missing, the lines go through ``<dir>/.imgw-incoming/`` and the file is
        moved into place with ``os.replace``, so an interrupted export leaves
        no partial file. ``None`` (default) returns the lines instead,
        byte-identical to the file content.
    force : bool, optional
        Replace an existing ``output`` file; without it an existing file is a
        ``conflict``. Needs ``output``.
    on_progress : ProgressHook or None, optional
        Called once after the export with ``unit="row"`` and the number of
        records.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice of the dataset's provider
        (source and processed-data attribution, license note) before the first
        line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 records and before replacing
        the target; returning ``True`` aborts the export.

    Returns
    -------
    OutputReport or Iterator[str]
        With ``output``: the written file as ``output`` and ``files[]``
        (``written`` or ``replaced``, size and SHA-256 of the bytes written);
        otherwise a lazy iterator of text lines with their line terminators.

    Raises
    ------
    IMGWValidationError
        If ``format`` is unsupported, ``version`` is not an archive version
        or is a station list version, ``output`` is a directory, or ``force``
        is given without ``output``.
    IMGWError
        Code ``conflict`` before anything is written: ``output`` exists and
        ``force`` is not given (``details.reason="output_exists"``) or lies
        in a store of any tool (``"output_in_store"``); ``details.paths``
        names it.
    IMGWStoreError
        If the archive file or its sidecar does not exist (code
        ``not_found``) or ``root`` is not a supported store.
    IMGWCancelledError
        If ``cancel`` returns ``True``; the target stays untouched and no
        staging file remains. Without ``output`` it may also be raised while
        iterating.
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
    descriptor = get_dataset(read_meta(_archive_main(source)).dataset)
    target = _target(output, force=force)
    head, rows = _archive_lines(records, format)
    _check_cancel(cancel)
    _license(descriptor, on_notice)
    lines = _Lines(
        head,
        rows,
        total=None,
        label=message("export.archive_progress", source=source),
        on_progress=on_progress,
        cancel=cancel,
    )
    return _deliver(
        lines,
        target=target,
        cancel=cancel,
        done=message("export.archive_exported", source=source),
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
    output: None = None,
    force: bool = False,
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
    output: PathArg,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport: ...


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
    output: PathArg | None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport | Iterator[str]:
    """
    Export values, flags and both attribution formulas of one station as CSV.

    ``year_type=None`` uses the publication convention of ``series.json`` (IMGW
    hydro ``hydrological``, IMGW meteo and ČHMÚ ``calendar``). Arguments and
    the station data are validated and read before anything is returned or
    written.

    The CSV (UTF-8 without BOM, comma, dot decimal, CRLF rows) has a single
    header row ``date,year,<V> [<unit>],<V>_flag,…,attribution_source,
    attribution_processed``; ČHMÚ meteo series add ``<V>_quality`` and
    ``<V>_source_flag`` after the flag of every variable, half-year series add
    ``period`` and ``<V>_start`` / ``<V>_end`` extremum dates with
    ``<V>_occurrences`` (number of merged IMGW rows). The source attribution
    and the processed-data attribution of the dataset's provider appear only in
    the first data row. Missing values are empty cells flagged ``missing``.

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
        Station code (nine IMGW-PIB digits or a ČHMÚ WIGOS identifier)
        present in the series.
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
    output : str, os.PathLike or None, optional
        The one plain CSV file to write (DEV-19.1): its directory is created
        when missing, the lines go through ``<dir>/.imgw-incoming/`` and the
        file is moved into place with ``os.replace``, so an interrupted export
        leaves no partial file. ``None`` (default) returns the lines instead,
        byte-identical to the file content.
    force : bool, optional
        Replace an existing ``output`` file; without it an existing file is a
        ``conflict``. Needs ``output``.
    on_progress : ProgressHook or None, optional
        Called every 256 rows and once after the export with ``unit="row"``.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice of the dataset's provider
        before the first line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 rows and before replacing the
        target; returning ``True`` aborts the export.

    Returns
    -------
    OutputReport or Iterator[str]
        With ``output``: the written file as ``output`` and ``files[]``
        (``written`` or ``replaced``, size and SHA-256 of the bytes written);
        otherwise a lazy iterator of CSV lines ending with CRLF.

    Raises
    ------
    IMGWValidationError
        If ``format`` or ``year_type`` is unsupported, ``year_type="calendar"``
        is requested for a half-year series, ``output`` is a directory,
        ``force`` is given without ``output``, or the arguments are rejected
        by :func:`read_series` (``version``/``dataset`` choice, station,
        ``variables``, ``start``/``end``).
    IMGWError
        Code ``conflict`` before the station data is read: ``output`` exists
        and ``force`` is not given (``details.reason="output_exists"``) or
        lies in a store of any tool (``"output_in_store"``); ``details.paths``
        names it.
    IMGWStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store.
    IMGWCancelledError
        If ``cancel`` returns ``True``; the target stays untouched and no
        staging file remains. Without ``output`` it may also be raised while
        iterating.
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
            message(
                "export.unknown_year_type_allowed",
                year_type=year_type,
                year_types=", ".join(_YEAR_TYPES),
            ),
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
            message(
                "export.semi_annual_annual_characteristics_have", dataset=index.dataset
            ),
            details={"option": "year_type", "value": "calendar"},
        )
    target = _target(output, force=force)
    records = list(
        read_series(series, station=station, variables=names, start=start, end=end)
    )
    if not records:
        raise IMGWDataError(
            message(
                "export.series_station_empty_chosen_range",
                station=station,
                dataset=index.dataset,
            )
        )
    _check_cancel(cancel)
    _license(descriptor, on_notice)

    header = ["date", "year", *(["period"] if half_year else [])]
    for name in names:
        header += [
            f"{name} [{descriptor.variables[name]}]",
            f"{name}_flag",
            *_field_names(name, descriptor),
        ]
        if half_year:
            header += [f"{name}_start", f"{name}_end", f"{name}_occurrences"]
    header += ["attribution_source", "attribution_processed"]
    attribution = _attribution(descriptor)

    def row(number: int, record: NormalizedRecord) -> list[str]:
        year = record.hydro_year if chosen == "hydrological" else record.date.year
        cells = [
            record.date.isoformat(),
            str(year),
            *([record.period or ""] if half_year else []),
        ]
        for name in names:
            cells += _measurement_cells(record.measurements[name], descriptor)
            if half_year:
                cells += _extrema(record, name)
        return [*cells, *(attribution if number == 0 else ("", ""))]

    lines = _Lines(
        (_csv_line(header),),
        _csv_lines(row(number, record) for number, record in enumerate(records)),
        total=len(records),
        label=message("export.station_progress", station=station),
        on_progress=on_progress,
        cancel=cancel,
    )
    return _deliver(
        lines,
        target=target,
        cancel=cancel,
        done=message("export.series_exported", station=station),
    )
