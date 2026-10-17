"""Per-station coverage of normalized archive observations (no I/O)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from imgwtools.datasets import get_dataset
from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store.types import StationCoverage

_PERIODS = ("winter", "summer", "annual")


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


def summarize_coverage(
    records: Iterable[NormalizedRecord], /, *, dataset: str
) -> list[StationCoverage]:
    """Summarize each station/variable; absent archive months stay unknown.

    Records identify observed months, not all possessed archive periods. The
    series builder determines its ``periods`` from the actual archive files.
    """
    descriptor = get_dataset(dataset)
    if descriptor.time_unit not in ("day", "month", "half_year"):
        raise IMGWValidationError(f"Zbiór {dataset} nie zawiera szeregu pomiarowego")
    observations: dict[tuple[str, str | None, str, date], Measurement] = {}
    stations: set[str] = set()
    known_months: set[tuple[int, int]] = set()
    for record in records:
        if record.dataset != dataset:
            raise IMGWValidationError(
                f"Rekord zbioru {record.dataset} nie należy do {dataset}"
            )
        stations.add(record.station_code)
        if descriptor.time_unit == "day":
            known_months.add((record.date.year, record.date.month))
        period = record.period if descriptor.time_unit == "half_year" else None
        for variable, measurement in record.measurements.items():
            if variable not in descriptor.variables:
                raise IMGWDataError(f"Nieznana zmienna {variable} w zbiorze {dataset}")
            key = (record.station_code, period, variable, record.date)
            if key in observations and observations[key] != measurement:
                raise IMGWDataError(
                    f"Sprzeczne wartości {variable} stacji {record.station_code} z {record.date}"
                )
            observations[key] = measurement

    per_variable: dict[tuple[str, str | None, str], dict[date, Measurement]] = (
        defaultdict(dict)
    )
    for (station, period, variable, day), measurement in observations.items():
        per_variable[(station, period, variable)][day] = measurement

    result: list[StationCoverage] = []
    periods = _PERIODS if descriptor.time_unit == "half_year" else (None,)
    available_months = sorted((date(year, month, 1) for year, month in known_months))
    for station in sorted(stations):
        for period in periods:
            for variable, unit in descriptor.variables.items():
                values = per_variable.get((station, period, variable), {})
                observed = sorted(
                    day
                    for day, measurement in values.items()
                    if measurement.value is not None
                )
                first, last = (observed[0], observed[-1]) if observed else (None, None)
                missing: list[date] = []
                if first is not None and last is not None:
                    if descriptor.time_unit == "day":
                        for month in available_months:
                            start = max(first, month)
                            end = min(last, _next_month(month) - timedelta(days=1))
                            day = start
                            while day <= end:
                                if day not in values or values[day].value is None:
                                    missing.append(day)
                                day += timedelta(days=1)
                    else:
                        missing = sorted(
                            day
                            for day, measurement in values.items()
                            if first < day < last and measurement.value is None
                        )
                result.append(
                    StationCoverage(
                        station=station,
                        variable=variable,
                        unit=unit,
                        period=period,
                        first=first,
                        last=last,
                        with_value=len(observed),
                        accumulated=sum(
                            measurement.flag == "accumulated"
                            and measurement.value is not None
                            for measurement in values.values()
                        ),
                        gaps=_gaps(missing, time_unit=descriptor.time_unit),
                    )
                )
    return result
