"""Parser of the IMGW hydrological and meteorological station list CSV files."""

import csv
import io
import re
from collections.abc import Iterator
from typing import Literal

from imgwtools._parsing.common import IMGW_ENCODING, _decode_content
from imgwtools.exceptions import IMGWValidationError
from imgwtools.models import StationListEntry

_RIVER = re.compile(r"^(.+?)\s*\((\d+)\)$")


def parse_stations_csv(
    content: str | bytes,
    /,
    *,
    kind: Literal["hydro", "meteo"],
    encoding: str = IMGW_ENCODING,
) -> Iterator[StationListEntry]:
    """
    Parse an IMGW station list CSV.

    Column layout depends on the list:

    - ``kind="hydro"`` (dataset ``pl.imgw.hydro_stations``): station code,
      name, river with the hydrographic code in parentheses (``"Odra (1)"``),
      optional fourth column kept as ``river_order``;
    - ``kind="meteo"`` (dataset ``pl.imgw.meteo_stations``): station code,
      name, optional third column kept as ``short_code``.

    Rows with fewer than two columns are skipped.

    Parameters
    ----------
    content : str or bytes
        CSV content.
    kind : {"hydro", "meteo"}
        Station family of the list; selects the column layout.
    encoding : str, optional
        Character encoding used when ``content`` is bytes without a UTF-8
        BOM (default CP1250).

    Yields
    ------
    StationListEntry
        Station parsed from a CSV row, with ``kind`` set.

    Raises
    ------
    IMGWValidationError
        If ``kind`` is neither ``"hydro"`` nor ``"meteo"``.
    """
    if kind not in ("hydro", "meteo"):
        raise IMGWValidationError(
            f"Nieznany rodzaj listy stacji: {kind!r}; dozwolone hydro, meteo"
        )
    text = content if isinstance(content, str) else _decode_content(content, encoding)
    for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        if len(row) < 2:
            continue
        cells = [cell.strip().strip('"').strip() for cell in row]
        code, name = cells[0], cells[1]
        if kind == "meteo":
            short = cells[2] if len(cells) > 2 else ""
            yield StationListEntry("meteo", code, name, short_code=short or None)
            continue
        raw_river = cells[2] if len(cells) > 2 else ""
        match = _RIVER.match(raw_river)
        order = cells[3] if len(cells) > 3 else ""
        yield StationListEntry(
            "hydro",
            code,
            name,
            river=match.group(1).strip() if match else raw_river or None,
            hydrographic_code=match.group(2) if match else None,
            river_order=int(order) if order.isdecimal() else None,
        )
