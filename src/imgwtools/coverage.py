"""Per-station coverage of normalized archive observations (no I/O)."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from imgwtools.datasets import DatasetDescriptor, get_dataset
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store.types import StationCoverage

_PERIODS = ("winter", "summer", "annual")

# Observations of one station: unit start date and half-year period (``None``
# outside semi-annual data) mapped to the measurements of that unit.
_StationValues = Mapping[tuple[date, str | None], Mapping[str, Measurement]]


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _gaps(missing: list[date], *, time_unit: str) -> tuple[tuple[date, date], ...]:
    """Coalesce adjacent known missing units, retaining inclusive boundaries."""
    if not missing:
        return ()
    spans: list[tuple[date, date]] = []
    start = end = missing[0]
    for current in missing[1:]:
        if time_unit == "day":
            next_unit = end + timedelta(days=1)
        elif time_unit == "month":
            next_unit = _next_month(end)
        else:
            next_unit = date(end.year + 1, end.month, end.day)
        if current == next_unit:
            end = current
        else:
            spans.append((start, end))
            start = end = current
    spans.append((start, end))
    return tuple(spans)


class _KnownUnits:
    """
    Units that the records of a dataset show to be published in a possessed archive.

    Daily and monthly archives carry every variable, so any record of any station
    in a calendar month marks that month as published. Semi-annual archives are
    separate per parameter, so a period of a hydrological year is published for
    a variable only when some record carries that variable there. Units without
    any record stay unknown and are never gaps.
    """

    def __init__(self, time_unit: str) -> None:
        self._time_unit = time_unit
        self._months: set[date] = set()
        self._ordered: list[date] = []
        self._half_years: dict[tuple[str | None, str], set[date]] = defaultdict(set)

    def add(self, record: NormalizedRecord) -> None:
        """Mark the units published according to one record."""
        if self._time_unit == "half_year":
            for variable in record.measurements:
                self._half_years[(record.period, variable)].add(record.date)
            return
        month = record.date.replace(day=1)
        if month not in self._months:
            self._months.add(month)
            self._ordered = []

    def missing(
        self,
        period: str | None,
        variable: str,
        values: Mapping[date, Measurement],
        first: date,
        last: date,
    ) -> list[date]:
        """Sorted published units between ``first`` and ``last`` without a value."""

        def absent(unit: date) -> bool:
            measurement = values.get(unit)
            return measurement is None or measurement.value is None

        if self._time_unit == "half_year":
            return sorted(
                unit
                for unit in self._half_years.get((period, variable), ())
                if first < unit < last and absent(unit)
            )
        if not self._ordered:
            self._ordered = sorted(self._months)
        months = self._ordered[
            bisect_left(self._ordered, first.replace(day=1)) : bisect_right(
                self._ordered, last
            )
        ]
        if self._time_unit == "month":
            return [month for month in months if first < month < last and absent(month)]
        result: list[date] = []
        for month in months:
            day = max(first, month)
            end = min(last, _next_month(month) - timedelta(days=1))
            while day <= end:
                if absent(day):
                    result.append(day)
                day += timedelta(days=1)
        return result


def _station_coverage(
    station: str,
    values: _StationValues,
    *,
    descriptor: DatasetDescriptor,
    known: _KnownUnits,
) -> list[StationCoverage]:
    """Coverage of every variable (and half-year period) of one station."""
    series: dict[tuple[str | None, str], dict[date, Measurement]] = defaultdict(dict)
    for (day, period), columns in values.items():
        for variable, measurement in columns.items():
            series[(period, variable)][day] = measurement
    result: list[StationCoverage] = []
    periods = _PERIODS if descriptor.time_unit == "half_year" else (None,)
    for period in periods:
        for variable, unit in descriptor.variables.items():
            observations = series.get((period, variable), {})
            observed = sorted(
                day
                for day, measurement in observations.items()
                if measurement.value is not None
            )
            first, last = (observed[0], observed[-1]) if observed else (None, None)
            missing = (
                known.missing(period, variable, observations, observed[0], observed[-1])
                if observed
                else []
            )
            result.append(
                StationCoverage(
                    station_code=station,
                    variable=variable,
                    unit=unit,
                    period=period,
                    first=first,
                    last=last,
                    with_value=len(observed),
                    accumulated=sum(
                        measurement.flag == "accumulated"
                        and measurement.value is not None
                        for measurement in observations.values()
                    ),
                    gaps=_gaps(missing, time_unit=descriptor.time_unit),
                )
            )
    return result


def summarize_coverage(
    records: Iterable[NormalizedRecord], /, *, dataset: str
) -> list[StationCoverage]:
    """
    Summarize the coverage of each station and variable of a series dataset.

    Gaps are units without a value between the first and last value that the
    records show to be published: for daily and monthly data any record of the
    dataset in a calendar month publishes that month for every station, for
    semi-annual data (archives separate per parameter) a period of a year is
    published for a variable when some record carries that variable there. A
    station absent from a published unit has a gap there; units without any
    record (e.g. an archive that was not downloaded) stay unknown rather than
    counted as gaps. The series builder computes the same coverage per station
    and determines its ``periods`` from the actual archive files.

    Parameters
    ----------
    records : Iterable[NormalizedRecord]
        Normalized records of a single dataset.
    dataset : str
        Dataset key with a ``day``, ``month`` or ``half_year`` time unit, e.g.
        ``"pl.imgw.hydro_daily"``.

    Returns
    -------
    list of StationCoverage
        One entry per station, variable (and half-year period for semi-annual
        data), sorted by station: first and last date with a value, the number
        of values and accumulated values, and the gaps of published units
        without a value between them.

    Raises
    ------
    IMGWValidationError
        If the dataset is unknown or has no measurement series, or a record
        belongs to another dataset.
    IMGWDataError
        If a record contains an unknown variable or conflicting values for the
        same station, variable and date.
    """
    descriptor = get_dataset(dataset)
    if not descriptor.in_store or descriptor.time_unit not in (
        "day",
        "month",
        "half_year",
    ):
        raise IMGWValidationError(f"Zbiór {dataset} nie zawiera szeregu pomiarowego")
    known = _KnownUnits(descriptor.time_unit)
    stations: dict[str, dict[tuple[date, str | None], dict[str, Measurement]]] = (
        defaultdict(dict)
    )
    for record in records:
        if record.dataset != dataset:
            raise IMGWValidationError(
                f"Rekord zbioru {record.dataset} nie należy do {dataset}"
            )
        known.add(record)
        period = record.period if descriptor.time_unit == "half_year" else None
        columns = stations[record.station_code].setdefault((record.date, period), {})
        for variable, measurement in record.measurements.items():
            if variable not in descriptor.variables:
                raise IMGWDataError(f"Nieznana zmienna {variable} w zbiorze {dataset}")
            previous = columns.get(variable)
            if previous is not None and previous != measurement:
                raise IMGWDataError(
                    f"Sprzeczne wartości {variable} stacji {record.station_code} z {record.date}"
                )
            columns[variable] = measurement
    result: list[StationCoverage] = []
    for station in sorted(stations):
        result.extend(
            _station_coverage(
                station, stations[station], descriptor=descriptor, known=known
            )
        )
    return result
