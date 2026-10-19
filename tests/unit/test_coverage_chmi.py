"""Coverage of ČHMÚ per-station datasets: known periods, not published units.

Spec 2026-10-18 §6.4: gaps lie only on days of the station's periods (its
files), so an unpublished year is unknown, never a gap. Boundary cases on
synthetic records; the index comparison on the §13.2 fixture files.
"""

from datetime import date, datetime, timedelta

import pytest

from imgwtools.coverage import summarize_coverage
from imgwtools.exceptions import IMGWValidationError
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store import (
    build_series,
    init_store,
    read_archive,
    read_series_index,
    summarize_series,
)
from tests.unit.test_store_series_chmi import store_hydro, store_meteo
from tests.unit.test_store_sync_chmi import H1_2023, H1_2024, H2_2004, H2_2006

HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
GAUGE, NEIGHBOUR, CLIMATE = "0-203-1-900009", "0-203-1-900008", "0-203-0-90009"


def days(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def measurement(value, flag=None):
    return Measurement(value, flag or ("missing" if value is None else "value"))


def record(station, dataset, day, **values):
    return NormalizedRecord(
        station,
        dataset,
        day,
        day.year + (day.month >= 11),
        None,
        {name: measurement(value) for name, value in values.items()},
    )


def by_variable(records, dataset, **options):
    return {
        (item.station_code, item.variable): item
        for item in summarize_coverage(records, dataset=dataset, **options)
    }


def gauge_records():
    """Q from 2004 with H from 1 XI, no 2005 file, closed on 30 VI 2006."""
    rows = {}
    for day in days("2004-01-01", "2004-12-31") + days("2006-01-01", "2006-06-30"):
        values = {"Q": 2.0}
        if day >= date(2004, 11, 1):
            values["H"] = 50.0
        rows[day] = values
    # No rows 28 II-1 III 2004 (leap day inside) and in the whole of February
    # 2006; an explicit missing Q on both sides of the hydrological year boundary.
    for day in days("2004-02-28", "2004-03-01") + days("2006-02-01", "2006-02-28"):
        del rows[day]
    rows[date(2004, 10, 31)]["Q"] = None
    rows[date(2004, 11, 1)]["Q"] = None
    return [record(GAUGE, HYDRO, day, **values) for day, values in rows.items()]


def test_unpublished_year_is_unknown_and_gaps_stay_inside_the_station_files():
    # Another station published 2005: that says nothing about the gauge's files.
    neighbour = [
        record(NEIGHBOUR, HYDRO, day, Q=1.0) for day in days("2005-01-01", "2005-12-31")
    ]

    coverage = by_variable(gauge_records() + neighbour, HYDRO)

    q, h, t = (coverage[GAUGE, name] for name in ("Q", "H", "T"))
    assert (q.first, q.last) == (date(2004, 1, 1), date(2006, 6, 30))
    # 2005 has no record of the gauge, so no file: unknown, not a gap. February
    # 2006 lies in a possessed file: a gap although no row exists that month.
    # After the closure on 30 VI 2006 the days are known but follow the last value.
    assert q.gaps == (
        (date(2004, 2, 28), date(2004, 3, 1)),
        (date(2004, 10, 31), date(2004, 11, 1)),
        (date(2006, 2, 1), date(2006, 2, 28)),
    )
    assert q.with_value == 366 - 3 - 2 + 181 - 28
    assert (h.first, h.last, h.gaps, h.with_value) == (
        date(2004, 11, 1),
        date(2006, 6, 30),
        ((date(2006, 2, 1), date(2006, 2, 28)),),
        61 + 181 - 28,
    )
    assert (t.first, t.with_value, t.gaps) == (None, 0, ())
    assert coverage[NEIGHBOUR, "Q"].gaps == ()
    assert {item.accumulated for item in coverage.values()} == {0}


def test_station_periods_decide_which_days_are_known():
    records = gauge_records()
    published = {GAUGE: [(date(2004, 1, 1), date(2006, 12, 31))]}

    coverage = by_variable(records, HYDRO, station_periods=published)

    # The same records with 2005 declared published: the whole year is a gap.
    assert coverage[GAUGE, "Q"].gaps == (
        (date(2004, 2, 28), date(2004, 3, 1)),
        (date(2004, 10, 31), date(2004, 11, 1)),
        (date(2005, 1, 1), date(2005, 12, 31)),
        (date(2006, 2, 1), date(2006, 2, 28)),
    )
    assert coverage[GAUGE, "H"].gaps == (
        (date(2005, 1, 1), date(2005, 12, 31)),
        (date(2006, 2, 1), date(2006, 2, 28)),
    )
    # A station missing from the mapping keeps the periods of its records.
    other = by_variable(records, HYDRO, station_periods={NEIGHBOUR: []})
    assert other == by_variable(records, HYDRO)


def test_meteo_periods_span_each_element_file_and_no_phenomenon_is_a_value():
    # No row of any element in October: a block without rows inside the files.
    autumn = days("2023-09-25", "2023-09-30") + days("2023-11-01", "2023-11-05")
    records = [record(CLIMATE, METEO, day, P=0.5, Tmax=11.0) for day in autumn]
    records[2] = NormalizedRecord(
        CLIMATE,
        METEO,
        date(2023, 9, 27),
        2023,
        None,
        {"P": Measurement(0.0, "no_phenomenon"), "Tmax": measurement(11.0)},
    )
    # Tmin starts later: nothing before its first value is a gap.
    records += [
        record(CLIMATE, METEO, day, Tmin=1.0)
        for day in days("2023-11-02", "2023-11-05")
    ]

    coverage = by_variable(records, METEO)

    p, tmax, tmin = (coverage[CLIMATE, name] for name in ("P", "Tmax", "Tmin"))
    october = ((date(2023, 10, 1), date(2023, 10, 31)),)
    assert (p.with_value, p.gaps, p.accumulated) == (11, october, 0)
    assert (tmax.with_value, tmax.gaps) == (11, october)
    assert (tmin.first, tmin.gaps) == (date(2023, 11, 2), ())
    assert coverage[CLIMATE, "Tmean"].first is None


@pytest.mark.parametrize(
    ("dataset", "station_periods"),
    [
        ("pl.imgw.hydro_daily", {"149190310": [(date(2024, 1, 1), date(2024, 1, 31))]}),
        (HYDRO, {GAUGE: [(date(2024, 2, 1), date(2024, 1, 1))]}),
        (HYDRO, {GAUGE: [(datetime(2024, 1, 1), datetime(2024, 1, 2))]}),
        (HYDRO, {GAUGE: [(date(2024, 1, 1),)]}),
        (HYDRO, {GAUGE: "2024-01-01"}),
        (HYDRO, [(GAUGE, [])]),
    ],
)
def test_station_periods_are_validated_before_any_record(dataset, station_periods):
    def refused():
        raise AssertionError("rekordy nie mogą być czytane")
        yield

    with pytest.raises(IMGWValidationError) as error:
        summarize_coverage(refused(), dataset=dataset, station_periods=station_periods)
    assert error.value.details["option"] == "station_periods"


def test_coverage_with_and_without_station_periods_equals_the_series_index(tmp_path):
    root = init_store(tmp_path / "store").root
    inputs = {
        HYDRO: store_hydro(root, H1_2023, H1_2024, H2_2004, H2_2006),
        METEO: store_meteo(root),
    }
    for dataset, written in inputs.items():
        version = build_series(root, dataset=dataset).version
        index = read_series_index(version)
        records = [item for entry in written for item in read_archive(entry.path)]
        periods = {code: entry.periods for code, entry in index.stations.items()}

        derived = summarize_coverage(records, dataset=dataset)
        given = summarize_coverage(records, dataset=dataset, station_periods=periods)

        assert derived == given == list(summarize_series(version))
        assert all(entry.periods for entry in index.stations.values())
