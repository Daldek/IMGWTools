"""Coverage is computed from measurements, not inferred unavailable archives."""

from datetime import date

from imgwtools.coverage import summarize_coverage
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store.types import StationCoverage


def row(dataset, when, measurements, *, station="123456789", period=None):
    return NormalizedRecord(station, dataset, when, when.year, period, measurements)


def value(amount, flag="value"):
    return Measurement(amount, flag)


def by_variable(records, dataset):
    return {
        (item.station, item.variable, item.period): item
        for item in summarize_coverage(records, dataset=dataset)
    }


def test_hydro_daily_separate_variables_leap_year_and_year_boundary():
    dataset = "pl.imgw.hydro_daily"
    records = [
        row(
            dataset,
            date(2023, 10, 31),
            {"Q": value(0), "H": value(100), "T": value(None, "missing")},
        ),
        row(
            dataset,
            date(2023, 11, 1),
            {"Q": value(None, "missing"), "H": value(99), "T": value(None, "missing")},
        ),
        row(
            dataset,
            date(2024, 2, 28),
            {"Q": value(2, "accumulated"), "H": value(None, "missing")},
        ),
        row(dataset, date(2024, 3, 1), {"Q": value(4), "H": value(101)}),
    ]
    coverage = by_variable(records, dataset)
    q = coverage["123456789", "Q", None]
    assert q.first == date(2023, 10, 31) and q.last == date(2024, 3, 1)
    assert q.with_value == 3 and q.accumulated == 1 and q.unit == "m3/s"
    assert q.gaps == (
        (date(2023, 11, 1), date(2023, 11, 30)),
        (date(2024, 2, 1), date(2024, 2, 27)),
        (date(2024, 2, 29), date(2024, 2, 29)),
    )
    h = coverage["123456789", "H", None]
    assert h.with_value == 3 and h.gaps == (
        (date(2023, 11, 2), date(2023, 11, 30)),
        (date(2024, 2, 1), date(2024, 2, 29)),
    )
    t = coverage["123456789", "T", None]
    assert t == StationCoverage("123456789", "T", "degC", None, None, None, 0, 0, ())


def test_meteo_daily_zero_and_accumulated_keep_missing_month_unknown():
    dataset = "pl.imgw.meteo_precip_daily"
    records = [
        row(
            dataset,
            date(2024, 1, 30),
            {"P": value(0, "no_phenomenon"), "fresh_snow": value(None, "missing")},
        ),
        row(dataset, date(2024, 2, 2), {"P": value(11, "accumulated")}),
        row(dataset, date(2024, 4, 1), {"P": value(3)}),
    ]
    coverage = by_variable(records, dataset)
    assert coverage["123456789", "P", None].gaps == (
        (date(2024, 1, 31), date(2024, 2, 1)),
        (date(2024, 2, 3), date(2024, 2, 29)),
    )
    assert coverage["123456789", "P", None].with_value == 3
    assert coverage["123456789", "P", None].accumulated == 1
    assert coverage["123456789", "fresh_snow", None].first is None
    assert coverage["123456789", "snow_cover", None].last is None


def test_monthly_explicit_missing_without_inventing_absent_archive_month():
    dataset = "pl.imgw.hydro_monthly"
    records = [
        row(dataset, date(2023, 11, 1), {"Q_mean": value(0)}),
        row(dataset, date(2023, 12, 1), {"Q_mean": value(None, "missing")}),
        row(dataset, date(2024, 2, 1), {"Q_mean": value(2)}),
    ]
    q = by_variable(records, dataset)["123456789", "Q_mean", None]
    assert q.gaps == ((date(2023, 12, 1), date(2023, 12, 1)),)
    assert q.with_value == 2


def test_hydro_half_year_periods_remain_distinct_with_empty_variables():
    dataset = "pl.imgw.hydro_semiannual"
    records = [
        row(dataset, date(2023, 11, 1), {"Q_min": value(2)}, period="winter"),
        row(
            dataset,
            date(2024, 5, 1),
            {"Q_min": value(None, "missing")},
            period="summer",
        ),
        row(dataset, date(2023, 11, 1), {"Q_min": value(3)}, period="annual"),
        row(dataset, date(2024, 11, 1), {"Q_min": value(4)}, period="winter"),
    ]
    coverage = by_variable(records, dataset)
    assert coverage["123456789", "Q_min", "winter"].with_value == 2
    assert coverage["123456789", "Q_min", "annual"].with_value == 1
    assert coverage["123456789", "Q_min", "summer"].with_value == 0
    assert coverage["123456789", "Q_min", "summer"].first is None
    assert coverage["123456789", "H_max", "annual"].last is None


def test_meteo_climate_tmax_and_precip_are_independent_across_february_29():
    dataset = "pl.imgw.meteo_climate_daily"
    records = [
        row(
            dataset, date(2024, 2, 28), {"Tmax": value(-2), "P": value(None, "missing")}
        ),
        row(
            dataset,
            date(2024, 2, 29),
            {"Tmax": value(None, "missing"), "P": value(0, "no_phenomenon")},
        ),
        row(
            dataset, date(2024, 3, 1), {"Tmax": value(3), "P": value(5, "accumulated")}
        ),
    ]
    coverage = by_variable(records, dataset)
    assert coverage["123456789", "Tmax", None].gaps == (
        (date(2024, 2, 29), date(2024, 2, 29)),
    )
    assert coverage["123456789", "Tmax", None].with_value == 2
    assert coverage["123456789", "P", None].first == date(2024, 2, 29)
    assert coverage["123456789", "P", None].with_value == 2
    assert coverage["123456789", "P", None].accumulated == 1


def test_half_year_gap_spans_missing_same_period_in_successive_years():
    dataset = "pl.imgw.hydro_semiannual"
    records = [
        row(dataset, date(2022, 11, 1), {"Q_max": value(1)}, period="winter"),
        row(
            dataset,
            date(2023, 11, 1),
            {"Q_max": value(None, "missing")},
            period="winter",
        ),
        row(dataset, date(2024, 11, 1), {"Q_max": value(2)}, period="winter"),
    ]
    q = by_variable(records, dataset)["123456789", "Q_max", "winter"]
    assert q.gaps == ((date(2023, 11, 1), date(2023, 11, 1)),)


def test_monthly_station_absent_from_published_months_has_gaps():
    dataset = "pl.imgw.hydro_monthly"
    hydrological_2022 = [date(2021, 11, 1), date(2021, 12, 1)] + [
        date(2022, month, 1) for month in range(1, 11)
    ]
    records = [
        row(dataset, date(2020, 11, 1), {"Q_mean": value(1)}),
        *(
            row(dataset, month, {"Q_mean": value(2)}, station="987654321")
            for month in hydrological_2022
        ),
        row(dataset, date(2022, 11, 1), {"Q_mean": value(3)}),
    ]
    q = by_variable(records, dataset)["123456789", "Q_mean", None]
    # Another station shows the HY2022 archive was published, so this station's
    # absence from it is a gap; XII 2020 – X 2021 has no record at all: unknown.
    assert q.gaps == ((date(2021, 11, 1), date(2022, 10, 1)),)
    assert q.with_value == 2


def test_half_year_gap_requires_the_parameter_published_that_year():
    dataset = "pl.imgw.hydro_semiannual"
    records = [
        row(
            dataset,
            date(2021, 11, 1),
            {"Q_max": value(1), "H_max": value(10)},
            period="winter",
        ),
        row(
            dataset,
            date(2023, 11, 1),
            {"Q_max": value(2), "H_max": value(12)},
            period="winter",
        ),
        # Only the Q archive of the winter in between is known (another station).
        row(
            dataset,
            date(2022, 11, 1),
            {"Q_max": value(5)},
            station="987654321",
            period="winter",
        ),
    ]
    coverage = by_variable(records, dataset)
    assert coverage["123456789", "Q_max", "winter"].gaps == (
        (date(2022, 11, 1), date(2022, 11, 1)),
    )
    assert coverage["123456789", "H_max", "winter"].gaps == ()
