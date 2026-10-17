"""Daily IMGW meteorological k_d and o_d CSV normalization."""

import calendar
import re
from collections.abc import Iterator
from datetime import date, timedelta

from imgwtools._parsing.common import _decode_content, _detect_delimiter, _iter_rows
from imgwtools.exceptions import IMGWDataError
from imgwtools.models import Measurement, NormalizedRecord


def _measurement(raw: str, status: str, *, filename: str, number: int) -> Measurement:
    status = status.strip()
    if status == "8":
        return Measurement(None, "missing")
    if status == "9":
        return Measurement(0.0, "no_phenomenon")
    if not raw.strip():
        return Measurement(None, "missing")
    try:
        return Measurement(float(raw.strip().replace(",", ".")), "value")
    except ValueError as exc:
        raise IMGWDataError(
            f"Błędna wartość w {filename}, wiersz {number}: {raw}"
        ) from exc


def _parse_daily(
    content: bytes | str,
    *,
    filename: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
) -> Iterator[NormalizedRecord]:
    text = _decode_content(content) if isinstance(content, bytes) else content
    text = text.lstrip("\ufeff")
    fields: dict[str, dict[date, NormalizedRecord]] = {}
    months: set[tuple[int, int]] = set()
    for number, row in enumerate(_iter_rows(text, _detect_delimiter(text)), 1):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < (18 if kind == "k_d" else 16):
            raise IMGWDataError(f"Za mało kolumn w {filename}, wiersz {number}")
        try:
            station = row[0].strip().strip('"')
            if not re.fullmatch(r"\d{9}", station):
                raise ValueError("Niepoprawny kod stacji")
            measured = date(int(row[2]), int(row[3]), int(row[4]))
            if year is not None and (
                measured.year != year or month is not None and measured.month != month
            ):
                raise ValueError("Data poza okresem archiwum")
            months.add((measured.year, measured.month))
            if kind == "k_d":
                values = {
                    key: _measurement(
                        row[offset], row[offset + 1], filename=filename, number=number
                    )
                    for key, offset in (
                        ("Tmax", 5),
                        ("Tmin", 7),
                        ("Tmean", 9),
                        ("Tground", 11),
                        ("P", 13),
                        ("snow_cover", 16),
                    )
                }
                attributes = {"precip_type": row[15].strip() or None}
            else:
                values = {
                    key: _measurement(
                        row[offset], row[offset + 1], filename=filename, number=number
                    )
                    for key, offset in (("P", 5), ("snow_cover", 8), ("fresh_snow", 10))
                }
                attributes = {
                    "precip_type": row[7].strip() or None,
                    "snow_species": row[12].strip() or None,
                    "snow_cover_type": row[14].strip() or None,
                }
            record = NormalizedRecord(
                station,
                "pl.imgw.meteo_climate_daily"
                if kind == "k_d"
                else "pl.imgw.meteo_precip_daily",
                measured,
                measured.year + (measured.month >= 11),
                None,
                values,
                attributes,
            )
            entries = fields.setdefault(station, {})
            if measured in entries:
                raise ValueError("Powtórzony dzień stacji")
            entries[measured] = record
        except (ValueError, IndexError) as exc:
            raise IMGWDataError(
                f"Błędny rekord w {filename}, wiersz {number}: {exc}"
            ) from exc
    if year is not None:
        months = {(year, month)} if month else {(year, i) for i in range(1, 13)}
    variables = (
        ("Tmax", "Tmin", "Tmean", "Tground", "P", "snow_cover")
        if kind == "k_d"
        else ("P", "snow_cover", "fresh_snow")
    )
    for station, entries in fields.items():
        present_months = {(day.year, day.month) for day in entries}
        previous_missing: date | None = None
        for y, m in sorted(months):
            for day in range(1, calendar.monthrange(y, m)[1] + 1):
                measured = date(y, m, day)
                record = entries.get(measured)
                if record is None:
                    flag = (
                        "no_phenomenon"
                        if kind == "o_d" and (y, m) in present_months
                        else "missing"
                    )
                    values = {
                        name: Measurement(
                            0.0 if name == "P" and flag == "no_phenomenon" else None,
                            flag if name == "P" else "missing",
                        )
                        for name in variables
                    }
                    record = NormalizedRecord(
                        station,
                        "pl.imgw.meteo_climate_daily"
                        if kind == "k_d"
                        else "pl.imgw.meteo_precip_daily",
                        measured,
                        y + (m >= 11),
                        None,
                        values,
                    )
                precip = record.measurements["P"]
                if (
                    kind == "o_d"
                    and previous_missing == measured - timedelta(days=1)
                    and precip.flag == "value"
                ):
                    values = dict(record.measurements)
                    values["P"] = Measurement(precip.value, "accumulated")
                    record = NormalizedRecord(
                        record.station_code,
                        record.dataset,
                        record.date,
                        record.hydro_year,
                        None,
                        values,
                        record.attributes,
                    )
                previous_missing = (
                    measured
                    if precip.flag == "missing" and measured in entries
                    else None
                )
                yield record


def _period_from_filename(filename: str, kind: str) -> tuple[int | None, int | None]:
    match = re.search(
        rf"(?:^|/){kind}_(\d{{4}})(?:_(\d{{2}}))?\.csv$", filename.lower()
    )
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


def parse_meteo_climate_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    year, month = _period_from_filename(filename, "k_d")
    yield from _parse_daily(
        content, filename=filename, kind="k_d", year=year, month=month
    )


def parse_meteo_precip_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    year, month = _period_from_filename(filename, "o_d")
    yield from _parse_daily(
        content, filename=filename, kind="o_d", year=year, month=month
    )


def normalize_meteo_archive(
    dataset: str, filename: str, data: bytes, *, year: int | None, month: int | None
) -> Iterator[NormalizedRecord]:
    from imgwtools._parsing.common import archive_csv_members

    kind = "k_d" if dataset == "pl.imgw.meteo_climate_daily" else "o_d"
    matched = False
    for member, content in archive_csv_members(data, filename=filename):
        if not re.search(rf"(?:^|[/_]){kind}(?:[/_.]|$)", member.lower()):
            continue
        matched = True
        yield from _parse_daily(
            content, filename=f"{filename}/{member}", kind=kind, year=year, month=month
        )
    if not matched:
        raise IMGWDataError(f"Brak pliku {kind} w {filename}")
