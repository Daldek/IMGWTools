"""Shared IMGW CSV decoding, date conventions, and safe ZIP member iteration."""

import csv
import io
from collections.abc import Iterator
from datetime import date
from zipfile import BadZipFile, ZipFile

from imgwtools.exceptions import IMGWDataError

IMGW_ENCODING = "cp1250"
MISSING_WATER_LEVEL = 9999
MISSING_FLOW = 99999.999
MISSING_TEMP = 99.9
EXTREMUM_MAP = {1: "min", 2: "mean", 3: "max"}
PERIOD_MAP = {13: "winter", 14: "summer", 15: "annual"}
HYDRO_TO_CALENDAR_MONTH = {1: 11, 2: 12, **{index + 2: index for index in range(1, 11)}}


def hydro_to_calendar_date(hydro_year: int, hydro_month: int, day: int) -> date:
    return date(
        hydro_year - (hydro_month <= 2), HYDRO_TO_CALENDAR_MONTH[hydro_month], day
    )


def is_missing_value(value: float | None, value_type: str) -> bool:
    return value is None or (
        (value_type == "level" and value == MISSING_WATER_LEVEL)
        or (value_type == "flow" and abs(value - MISSING_FLOW) < 0.001)
        or (value_type == "temp" and abs(value - MISSING_TEMP) < 0.01)
    )


def _safe_float(value: str, missing_value: float) -> float | None:
    try:
        parsed = float(value.strip())
        return None if abs(parsed - missing_value) < 0.001 else parsed
    except ValueError:
        return None


def _safe_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def _decode_content(content: bytes, encoding: str = IMGW_ENCODING) -> str:
    if content.startswith(b"\xef\xbb\xbf"):
        return content.decode("utf-8-sig")
    try:
        return content.decode(encoding)
    except UnicodeDecodeError:
        return content.decode("utf-8")


def _detect_delimiter(content: str) -> str:
    first = next((line for line in content.splitlines() if line.strip()), "")
    return ";" if first.count(";") >= first.count(",") else ","


def _iter_rows(content: str, delimiter: str) -> Iterator[list[str]]:
    for row in csv.reader(io.StringIO(content), delimiter=delimiter):
        if len(row) == 1 and delimiter in row[0]:
            row = next(csv.reader(io.StringIO(row[0]), delimiter=delimiter))
        yield row


def archive_csv_members(
    data: bytes, *, kind: str | None = None, filename: str = "archiwum ZIP"
) -> Iterator[tuple[str, bytes]]:
    """Read CSV members without extracting paths, with compressed-bomb limits."""
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if (
                len(members) > 1000
                or sum(item.file_size for item in members) > 256 * 1024 * 1024
            ):
                raise IMGWDataError(f"Zbyt duże archiwum {filename}")
            for member in members:
                name = member.filename
                if name.startswith("/") or ".." in name.split("/") or "\\" in name:
                    raise IMGWDataError(f"Niedozwolona ścieżka w {filename}: {name}")
                if not name.lower().endswith(".csv") or (
                    kind and kind not in name.lower()
                ):
                    continue
                if member.file_size > 64 * 1024 * 1024:
                    raise IMGWDataError(f"Zbyt duży CSV w {filename}: {name}")
                yield name, archive.read(member)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise IMGWDataError(f"Nieczytelne archiwum {filename}: {exc}") from exc
