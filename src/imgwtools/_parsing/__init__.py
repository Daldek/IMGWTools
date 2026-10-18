"""Archive parsing for IMGW hydro and meteo ZIP/CSV files."""

from collections.abc import Iterator

from imgwtools._parsing.hydro import normalize_hydro_archive
from imgwtools._parsing.meteo import normalize_meteo_archive
from imgwtools.datasets import ArchiveFile
from imgwtools.exceptions import IMGWValidationError
from imgwtools.models import NormalizedRecord


def normalize_archive(
    archive: ArchiveFile, /, *, data: bytes
) -> Iterator[NormalizedRecord]:
    """
    Normalize a physical IMGW archive using the parser of its dataset.

    Hydrological datasets (``pl.imgw.hydro_daily``, ``pl.imgw.hydro_monthly``,
    ``pl.imgw.hydro_semiannual``) and daily meteorological datasets
    (``pl.imgw.meteo_climate_daily``, ``pl.imgw.meteo_precip_daily``) are
    supported. Parsing is strict: malformed rows raise instead of being
    skipped.

    Parameters
    ----------
    archive : ArchiveFile
        Catalog entry of the archive; its ``dataset`` selects the parser,
        ``server_path`` names it in error messages and, for meteorological
        data, ``year``/``month`` define the expected period.
    data : bytes
        ZIP archive content.

    Yields
    ------
    NormalizedRecord
        Normalized measurements with value/flag pairs; see
        ``normalize_hydro_archive`` and ``normalize_meteo_archive`` for the
        per-dataset record layout.

    Raises
    ------
    IMGWValidationError
        If no parser is registered for ``archive.dataset``.
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
    else:
        raise IMGWValidationError(f"Brak parsera archiwum: {archive.dataset}")
