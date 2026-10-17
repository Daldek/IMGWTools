"""Archive parsing independent of the retired database cache."""

from collections.abc import Iterator

from imgwtools._parsing.hydro import normalize_hydro_archive
from imgwtools._parsing.meteo import normalize_meteo_archive
from imgwtools.datasets import ArchiveFile
from imgwtools.exceptions import IMGWValidationError
from imgwtools.models import NormalizedRecord


def normalize_archive(archive: ArchiveFile, /, *, data: bytes) -> Iterator[NormalizedRecord]:
    """Normalize a physical IMGW archive using its registered dataset."""
    if archive.dataset in {"pl.imgw.hydro_daily", "pl.imgw.hydro_monthly", "pl.imgw.hydro_semiannual"}:
        yield from normalize_hydro_archive(archive.dataset, archive.server_path, data)
    elif archive.dataset in {"pl.imgw.meteo_climate_daily", "pl.imgw.meteo_precip_daily"}:
        yield from normalize_meteo_archive(archive.dataset, archive.server_path, data, year=archive.year, month=archive.month)
    else:
        raise IMGWValidationError(f"Brak parsera archiwum: {archive.dataset}")
