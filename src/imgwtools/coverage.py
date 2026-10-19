"""Per-station coverage of normalized archive observations (no I/O)."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta

from imgwtools.datasets import DatasetDescriptor, get_dataset
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store.types import StationCoverage

_PERIODS = ("winter", "summer", "annual")

# Observations of one station: unit start date and half-year period (``None``
# outside semi-annual data) mapped to the measurements of that unit.
_StationValues = Mapping[tuple[date, str | None], Mapping[str, Measurement]]
# Closed range of days, both ends included.
_Span = tuple[date, date]


def _merge_spans(spans: Iterable[_Span]) -> tuple[_Span, ...]:
    """Union of closed date ranges, overlapping and adjacent ranges merged, sorted."""
    merged: list[list[date]] = []
    for start, end in sorted(set(spans)):
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


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


class _KnownSpans:
    """
    Known days of one station of a per-station dataset (ADR-003 D10).

    The days of the station's periods (its possessed files) are known; days
    outside them, e.g. a year whose file is not published, stay unknown and
    are never gaps.
    """

    def __init__(self, spans: Sequence[_Span]) -> None:
        self._spans = spans

    def missing(
        self,
        period: str | None,
        variable: str,
        values: Mapping[date, Measurement],
        first: date,
        last: date,
    ) -> list[date]:
        """Sorted known days between ``first`` and ``last`` without a value."""
        del period, variable  # every variable of a station shares its periods
        result: list[date] = []
        for start, end in self._spans:
            day, stop = max(first, start), min(last, end)
            while day <= stop:
                measurement = values.get(day)
                if measurement is None or measurement.value is None:
                    result.append(day)
                day += timedelta(days=1)
        return result


class _DerivedPeriods:
    """
    Known periods of each station derived from its records (ADR-003 D10).

    Station-year files (``station_year``) give every calendar year with a
    record of the station; station-element files (``station_element``) give
    the range from the first to the last record of each variable.
    """

    def __init__(self, archive_scope: str) -> None:
        self._by_year = archive_scope == "station_year"
        self._bounds: dict[str, dict[int | str, list[date]]] = defaultdict(dict)

    def add(self, record: NormalizedRecord) -> None:
        """Extend the periods of the record's station by the record."""
        bounds = self._bounds[record.station_code]
        day = record.date
        if self._by_year:
            bounds.setdefault(day.year, [date(day.year, 1, 1), date(day.year, 12, 31)])
            return
        for variable in record.measurements:
            span = bounds.setdefault(variable, [day, day])
            span[0], span[1] = min(span[0], day), max(span[1], day)

    def periods(self, station: str) -> tuple[_Span, ...]:
        """Merged known periods of ``station``."""
        return _merge_spans(
            (start, end) for start, end in self._bounds[station].values()
        )


def _is_day(value: object) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _given_periods(
    station_periods: Mapping[str, Sequence[tuple[date, date]]],
) -> dict[str, tuple[_Span, ...]]:
    """Validated ``station_periods`` of :func:`summarize_coverage`, merged per station."""
    if not isinstance(station_periods, Mapping):
        raise IMGWValidationError(
            "station_periods musi być słownikiem: kod stacji → przedziały dat",
            details={"option": "station_periods", "value": str(station_periods)},
        )
    result: dict[str, tuple[_Span, ...]] = {}
    for code, spans in station_periods.items():
        valid = isinstance(code, str) and (
            isinstance(spans, Iterable) and not isinstance(spans, str)
        )
        pairs: list[_Span] = []
        for span in spans if valid else ():
            if (
                isinstance(span, str)
                or not isinstance(span, Sequence)
                or len(span) != 2
                or not (_is_day(span[0]) and _is_day(span[1]))
                or span[0] > span[1]
            ):
                valid = False
                break
            pairs.append((span[0], span[1]))
        if not valid:
            raise IMGWValidationError(
                f"Nieprawidłowe okresy stacji {code!r} w station_periods: oczekiwano "
                "par (początek, koniec) typu datetime.date, z początkiem nie "
                "późniejszym niż koniec",
                details={"option": "station_periods", "value": str(code)},
            )
        result[code] = _merge_spans(pairs)
    return result


def _station_coverage(
    station: str,
    values: _StationValues,
    *,
    descriptor: DatasetDescriptor,
    known: _KnownUnits | _KnownSpans,
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
    records: Iterable[NormalizedRecord],
    /,
    *,
    dataset: str,
    station_periods: Mapping[str, Sequence[tuple[date, date]]] | None = None,
) -> list[StationCoverage]:
    """
    Summarize the coverage of each station and variable of a series dataset.

    Gaps are maximal runs of known units without a value between the first
    and last value of a variable (``no_phenomenon`` and ``accumulated`` count
    as values); units of unknown publication are never gaps. For datasets of
    country-wide archives (IMGW-PIB) the records show what is published: for
    daily and monthly data any record of the dataset in a calendar month
    publishes that month for every station, for semi-annual data (archives
    separate per parameter) a period of a year is published for a variable
    when some record carries that variable there. A station absent from a
    published unit has a gap there; units without any record (e.g. an archive
    that was not downloaded) stay unknown. For datasets of per-station files
    (ČHMÚ, ADR-003 D10) the known units are the days of each station's
    periods: ``station_periods`` when given (the series builder uses the
    periods of the possessed files), otherwise derived from the records —
    every calendar year with a record of the station for station-year files
    (``cz.chmi.hydro_daily``), the range from the first to the last record of
    each variable for station-element files (``cz.chmi.meteo_daily``). A year
    without a published file therefore stays unknown, not a gap.

    Parameters
    ----------
    records : Iterable[NormalizedRecord]
        Normalized records of a single dataset.
    dataset : str
        Dataset key with a ``day``, ``month`` or ``half_year`` time unit, e.g.
        ``"pl.imgw.hydro_daily"`` or ``"cz.chmi.hydro_daily"``.
    station_periods : Mapping of str to Sequence of tuple of (date, date), optional
        Known periods of the stations of a per-station dataset as closed date
        ranges keyed by station code, e.g. ``StationSeriesIndex.periods`` of
        a series; overlapping and adjacent ranges are merged. A station
        missing from the mapping gets the periods derived from its records.
        ``None`` (default) derives the periods of every station.

    Returns
    -------
    list of StationCoverage
        One entry per station, variable (and half-year period for semi-annual
        data), sorted by station: first and last date with a value, the number
        of values and accumulated values, and the gaps of known units without
        a value between them.

    Raises
    ------
    IMGWValidationError
        If the dataset is unknown or has no measurement series, a record
        belongs to another dataset, or ``station_periods`` is malformed or
        given for a dataset of country-wide archives (``details.option`` is
        ``"station_periods"``).
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
    per_station = descriptor.archive_scope != "country"
    if station_periods is not None and not per_station:
        raise IMGWValidationError(
            f"Zbiór {dataset} ma archiwa całego kraju; okresy stacji "
            "(station_periods) dotyczą wyłącznie zbiorów z plikami stacji",
            details={"option": "station_periods", "value": dataset},
        )
    given = {} if station_periods is None else _given_periods(station_periods)
    known = _KnownUnits(descriptor.time_unit)
    derived = _DerivedPeriods(descriptor.archive_scope)
    stations: dict[str, dict[tuple[date, str | None], dict[str, Measurement]]] = (
        defaultdict(dict)
    )
    for record in records:
        if record.dataset != dataset:
            raise IMGWValidationError(
                f"Rekord zbioru {record.dataset} nie należy do {dataset}"
            )
        if per_station:
            derived.add(record)
        else:
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
        units: _KnownUnits | _KnownSpans = known
        if per_station:
            spans = given.get(station)
            units = _KnownSpans(derived.periods(station) if spans is None else spans)
        result.extend(
            _station_coverage(
                station, stations[station], descriptor=descriptor, known=units
            )
        )
    return result
