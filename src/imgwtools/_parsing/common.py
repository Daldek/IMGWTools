"""Shared IMGW CSV decoding, date conventions, and safe ZIP member iteration."""

import csv
import io
import re
from collections.abc import Iterator
from datetime import date
from zipfile import BadZipFile, ZipFile

from imgwtools.exceptions import IMGWDataError
from imgwtools.messages import message, reason

IMGW_ENCODING = "cp1250"
MISSING_WATER_LEVEL = 9999
MISSING_FLOW = 99999.999
MISSING_TEMP = 99.9
EXTREMUM_MAP = {1: "min", 2: "mean", 3: "max"}
PERIOD_MAP = {13: "winter", 14: "summer", 15: "annual"}
HYDRO_TO_CALENDAR_MONTH = {1: 11, 2: 12, **{index + 2: index for index in range(1, 11)}}
_COLUMN_CODE = re.compile(r"[A-Za-z_]+")


def hydro_to_calendar_date(hydro_year: int, hydro_month: int, day: int) -> date:
    """
    Convert a hydrological-year date to a calendar date.

    The Polish hydrological year runs from November 1 to October 31, so
    hydrological months 1 and 2 (November, December) fall in the calendar
    year preceding ``hydro_year`` and months 3-12 map to January-October.

    Parameters
    ----------
    hydro_year : int
        Hydrological year.
    hydro_month : int
        Month index within the hydrological year (1 = November, 12 = October).
    day : int
        Day of the month.

    Returns
    -------
    datetime.date
        Corresponding calendar date.

    Raises
    ------
    KeyError
        If ``hydro_month`` is outside 1-12.
    ValueError
        If ``day`` does not exist in the resulting calendar month.
    """
    return date(
        hydro_year - (hydro_month <= 2), HYDRO_TO_CALENDAR_MONTH[hydro_month], day
    )


def is_missing_value(value: float | None, value_type: str) -> bool:
    """
    Check whether a hydrological value is missing.

    Parameters
    ----------
    value : float or None
        Parsed value; ``None`` is always treated as missing.
    value_type : {"level", "flow", "temp"}
        Kind of value, selecting the IMGW missing-data sentinel to compare
        against (``9999`` for water level, ``99999.999`` for flow, ``99.9``
        for water temperature). Any other string only treats ``None`` as
        missing.

    Returns
    -------
    bool
        True if the value is ``None`` or equals the sentinel for its type.
    """
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


def _is_header_row(row: list[str]) -> bool:
    """Whether every cell is a column code, e.g. ``kansp,kapost,dorok`` (IMGW 2024+)."""
    return bool(row) and all(
        _COLUMN_CODE.fullmatch(cell.strip().strip('"')) for cell in row
    )


def archive_csv_members(
    data: bytes, *, kind: str | None = None, filename: str = "archiwum ZIP"
) -> Iterator[tuple[str, bytes]]:
    """
    Iterate over CSV members of an IMGW ZIP archive without extracting it.

    Members are read into memory only; nothing is written to disk. Archive
    size limits guard against decompression bombs, and every member path is
    validated before that member is read.

    Parameters
    ----------
    data : bytes
        ZIP archive content.
    kind : str or None, optional
        If given, only members whose lowercase name contains this substring
        are yielded.
    filename : str, optional
        Archive name used in error messages.

    Yields
    ------
    tuple of (str, bytes)
        Member name and its uncompressed content, for every member whose name
        ends with ``.csv`` (case-insensitive) and matches ``kind``.

    Raises
    ------
    IMGWDataError
        If the archive has more than 1000 members or more than 256 MiB of
        uncompressed content, contains an absolute, ``..`` or backslash
        member path, contains a CSV member larger than 64 MiB, or cannot be
        read as a ZIP file.
    """
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if (
                len(members) > 1000
                or sum(item.file_size for item in members) > 256 * 1024 * 1024
            ):
                raise IMGWDataError(
                    message("parsing.archive_too_large", filename=filename)
                )
            for member in members:
                name = member.filename
                if name.startswith("/") or ".." in name.split("/") or "\\" in name:
                    raise IMGWDataError(
                        message(
                            "parsing.path_not_allowed", filename=filename, name=name
                        )
                    )
                if not name.lower().endswith(".csv") or (
                    kind and kind not in name.lower()
                ):
                    continue
                if member.file_size > 64 * 1024 * 1024:
                    raise IMGWDataError(
                        message("parsing.csv_too_large", filename=filename, name=name)
                    )
                yield name, archive.read(member)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise IMGWDataError(
            message("parsing.unreadable_archive", filename=filename, exc=reason(exc))
        ) from exc
