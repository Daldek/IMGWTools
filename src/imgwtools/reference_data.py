"""Fetch IMGW-PIB reference data into the ``data/`` directory.

After installing the package (``pip install -e .``), run it with no arguments:

    python -m imgwtools.reference_data

The module reuses the ``imgwtools.stations`` functions (it does not duplicate
IMGW URLs, parsing, or encoding). Output is written to ``settings.data_dir``
(defaults to ``./data``; override with the ``IMGW_DATA_DIR`` environment
variable).

All fetched data comes from IMGW-PIB and is subject to IMGW-PIB's terms of use.
Regulations and the exact attribution wording:
https://danepubliczne.imgw.pl/regulations
"""

import csv
import io
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx

from imgwtools.config import settings
from imgwtools.exceptions import IMGWError
from imgwtools.stations import fetch_hydro_states, find_stations

# Format-description files are not covered by imgwtools.stations, so their URLs
# are defined here (new resources, not a duplicate of the station-listing logic).
DESC_BASE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
HYDRO_DESC = [
    "dane_hydrologiczne/dobowe/CODZ_publiczne_format.txt",
    "dane_hydrologiczne/dobowe/ZJAW_publiczne_format.txt",
    "dane_hydrologiczne/miesieczne/MIES_publiczne_format.txt",
    "dane_hydrologiczne/polroczne_i_roczne/POLR_publiczne_format.txt",
]
METEO_INTERVALS = ["dobowe", "miesieczne", "terminowe"]
METEO_SUBTYPES = ["klimat", "opad", "synop"]

ATTRIBUTION = (
    "Zrodlem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej "
    "- Panstwowy Instytut Badawczy"
)


def _write_csv(path: Path, header: list[str], rows: Iterable[list[object]]) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    count = 0
    for row in rows:
        writer.writerow(row)
        count += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"  - {path} ({count} rows)")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  - {path} ({len(data):,} B)")


def fetch_stations(data_dir: Path) -> None:
    """Fetch station lists and coordinates via the library (no duplication)."""
    print("List of stations and coordinates:")
    _write_csv(
        data_dir / "hydro_stations_names.csv",
        ["id", "name", "river"],
        ([s.station_code, s.name, s.river or ""] for s in find_stations(kind="hydro")),
    )
    _write_csv(
        data_dir / "meteo_stations_names.csv",
        ["id", "name"],
        ([s.station_code, s.name] for s in find_stations(kind="meteo")),
    )
    _write_csv(
        data_dir / "hydro_stations_locations.csv",
        ["station_code", "latitude", "longitude"],
        (
            [s.station_code, s.latitude, s.longitude]
            for s in fetch_hydro_states()
            if s.longitude is not None and s.latitude is not None
        ),
    )


def _meteo_format_files(client: httpx.Client) -> Iterator[tuple[str, str]]:
    """Yield (filename, url) for every meteo *_format.txt found on the server."""
    seen: set[str] = set()
    for interval in METEO_INTERVALS:
        for subtype in METEO_SUBTYPES:
            base = f"{DESC_BASE}/dane_meteorologiczne/{interval}/{subtype}/"
            listing = client.get(base)
            if not listing.is_success:
                continue  # e.g. terminowe/opad does not exist
            for name in re.findall(r'href="([^"/]+_format\.txt)"', listing.text):
                if name not in seen:
                    seen.add(name)
                    yield name, base + name


def fetch_descriptions(data_dir: Path) -> None:
    """Fetch file-format description files (resources outside the library)."""
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        print("Format descriptions (hydro):")
        for rel in HYDRO_DESC:
            resp = client.get(f"{DESC_BASE}/{rel}")
            if resp.is_success:
                _write_bytes(
                    data_dir / "desc" / "dane_hydrologiczne" / Path(rel).name,
                    resp.content,
                )
            else:
                print(f"  skipped: {rel}: HTTP {resp.status_code}")

        print("Format descriptions (meteo):")
        for name, url in _meteo_format_files(client):
            resp = client.get(url)
            if resp.is_success:
                _write_bytes(
                    data_dir / "desc" / "dane_meteorologiczne" / name, resp.content
                )
            else:
                print(f"  skipped: {name}: HTTP {resp.status_code}")


def main() -> int:
    """Fetch all reference data into ``settings.data_dir``."""
    data_dir = settings.data_dir
    print(f"Fetching reference data into: {data_dir}")
    print("Data is subject to IMGW-PIB's terms of use.")
    print(f"Required attribution: {ATTRIBUTION}\n")

    try:
        fetch_stations(data_dir)
        fetch_descriptions(data_dir)
    except (IMGWError, httpx.HTTPError) as exc:
        print(f"Error fetching data: {exc}", file=sys.stderr)
        return 1

    print(f"\nDone. All data fetched from IMGW-PIB and written to {data_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
