"""Archive parsing for IMGW-PIB ZIP/CSV files and ČHMÚ JSON/CSV files."""

from collections.abc import Iterator

from imgwtools._parsing.chmi import parse_chmi_hydro_daily, parse_chmi_meteo_daily
from imgwtools._parsing.hydro import normalize_hydro_archive
from imgwtools._parsing.meteo import normalize_meteo_archive
from imgwtools.datasets import ArchiveFile
from imgwtools.exceptions import IMGWValidationError
from imgwtools.models import NormalizedRecord


def normalize_archive(
    archive: ArchiveFile, /, *, data: bytes
) -> Iterator[NormalizedRecord]:
    """
    Normalize a physical source archive using the parser of its dataset.

    IMGW-PIB hydrological datasets (``pl.imgw.hydro_daily``,
    ``pl.imgw.hydro_monthly``, ``pl.imgw.hydro_semiannual``), IMGW-PIB daily
    meteorological datasets (``pl.imgw.meteo_climate_daily``,
    ``pl.imgw.meteo_precip_daily``) and the ČHMÚ daily datasets
    (``cz.chmi.hydro_daily``, ``cz.chmi.meteo_daily``) are supported.
    Parsing is strict: malformed rows raise instead of being skipped.

    Parameters
    ----------
    archive : ArchiveFile
        Catalog entry of the archive; its ``dataset`` selects the parser,
        ``server_path`` names it in error messages (for ČHMÚ its file name
        also gives the station code and the year or element) and, for IMGW
        meteorological data, ``year``/``month`` define the expected period.
    data : bytes
        Archive content: a ZIP archive (IMGW-PIB) or the JSON/CSV file
        (ČHMÚ).

    Yields
    ------
    NormalizedRecord
        Normalized measurements with value/flag pairs; see
        ``normalize_hydro_archive``, ``normalize_meteo_archive``,
        ``parse_chmi_hydro_daily`` and ``parse_chmi_meteo_daily`` for the
        per-dataset record layout.

    Raises
    ------
    IMGWValidationError
        If no parser is registered for ``archive.dataset``, or a ČHMÚ
        ``server_path`` does not end with a file name of its dataset.
    IMGWDataError
        If the archive is unreadable or unsafe, or contains malformed or
        contradictory data.
    """
    if archive.dataset in {
        "pl.imgw.hydro_daily",
        "pl.imgw.hydro_monthly",
        "pl.imgw.hydro_semiannual",
    }:
        yield from normalize_hydro_archive(archive.dataset, archive.server_path, data)
    elif archive.dataset in {
        "pl.imgw.meteo_climate_daily",
        "pl.imgw.meteo_precip_daily",
    }:
        yield from normalize_meteo_archive(
            archive.dataset,
            archive.server_path,
            data,
            year=archive.year,
            month=archive.month,
        )
    elif archive.dataset == "cz.chmi.hydro_daily":
        yield from parse_chmi_hydro_daily(data, filename=archive.server_path)
    elif archive.dataset == "cz.chmi.meteo_daily":
        yield from parse_chmi_meteo_daily(data, filename=archive.server_path)
    else:
        raise IMGWValidationError(f"Brak parsera archiwum: {archive.dataset}")
