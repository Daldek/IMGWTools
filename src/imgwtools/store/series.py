"""Per-station Parquet snapshots ``imgw-series/1`` built from current archive versions."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import tempfile
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from imgwtools._parsing import normalize_archive
from imgwtools._version import __version__
from imgwtools.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    archive_files,
    get_dataset,
)
from imgwtools.exceptions import (
    IMGWDataError,
    IMGWError,
    IMGWStoreConflictError,
    IMGWStoreDependencyError,
    IMGWValidationError,
)
from imgwtools.models import Measurement, NormalizedRecord
from imgwtools.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    PlanAction,
    PlanItem,
    Progress,
    ProgressHook,
    SeriesReport,
    StoreHandle,
    StorePlan,
)
from imgwtools.store.writer import (
    _atomic_publish,
    _canonical,
    _check_kartograf,
    _cleanup,
    _fsync_dir,
    _utc,
    _validate_slot,
    _write_json,
    open_store,
)

SERIES_SCHEMA = "imgw-series/1"
SeriesState = Literal["current", "outdated", "missing"]

_FLAGS = ("value", "missing", "no_phenomenon", "accumulated")
_PERIODS = ("winter", "summer", "annual")
_PROCESSED = "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone"
_CANCELLED = "anulowano"
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class _Version:
    """One immutable archive version read from its sidecar (contents not re-hashed)."""

    slot: str
    file: Path
    relative: str
    meta: Mapping[str, Any]

    @property
    def sha256(self) -> str:
        return self.meta["sha256"]

    @property
    def label(self) -> str:
        return self.meta["extra"]["version"]["label"]

    @property
    def http(self) -> Mapping[str, Any]:
        return self.meta["extra"].get("http") or {}


@dataclass(frozen=True)
class _Input:
    archive: ArchiveFile
    version: _Version


def _root(root: PathArg | StoreHandle) -> Path:
    return open_store(root.root if isinstance(root, StoreHandle) else root).root


def _series_descriptor(dataset: str) -> DatasetDescriptor:
    descriptor = get_dataset(dataset)
    if descriptor.time_unit not in ("day", "month", "half_year"):
        raise IMGWValidationError(f"Zbiór {dataset} nie tworzy szeregów pomiarowych")
    return descriptor


def _slot_of(archive: ArchiveFile) -> str:
    relative = PurePosixPath(archive.server_path)
    return f"archives/versions/{relative.parent.as_posix()}/{relative.stem}"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _downloaded(meta: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(meta["downloaded_at"]).replace("Z", "+00:00"))


def _read_versions(root: Path, slot: str, name: str) -> list[_Version]:
    """Read every sidecar of an archive slot; a broken version is an explicit error."""
    directory = _validate_slot(root, slot)
    if not directory.exists():
        return []
    versions = []
    for version_dir in sorted(directory.iterdir()):
        meta_path = version_dir / f"{name}.meta.json"
        main = version_dir / name
        try:
            if (
                version_dir.is_symlink()
                or not version_dir.is_dir()
                or main.is_symlink()
                or meta_path.is_symlink()
            ):
                raise ValueError("dowiązanie lub plik zamiast katalogu wersji")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["schema"] != "imgw-meta/1" or not main.is_file():
                raise ValueError("nieznany schemat lub brak pliku głównego")
            if not isinstance(meta["sha256"], str) or not isinstance(
                meta["extra"]["version"]["label"], str
            ):
                raise ValueError("brak sumy lub etykiety wersji")
            _downloaded(meta)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IMGWDataError(
                f"Uszkodzona wersja archiwum {version_dir.relative_to(root).as_posix()}: {exc}"
            ) from exc
        versions.append(_Version(slot, main, main.relative_to(root).as_posix(), meta))
    return versions


def _pick_current(versions: Iterable[_Version]) -> _Version | None:
    """Newest Last-Modified (fallback downloaded_at), then downloaded_at, then path."""

    def key(version: _Version) -> tuple[datetime, datetime, str]:
        downloaded = _downloaded(version.meta)
        return (
            _parse_time(version.http.get("last_modified")) or downloaded,
            downloaded,
            version.relative,
        )

    return max(versions, key=key, default=None)


def _current_version(root: Path, archive: ArchiveFile) -> _Version | None:
    return _pick_current(
        _read_versions(root, _slot_of(archive), PurePosixPath(archive.server_path).name)
    )


def _restore_archive(dataset: str, meta: Mapping[str, Any]) -> ArchiveFile:
    request = meta["request"]
    month = request.get("month")
    candidates = archive_files(
        dataset,
        years=(request["year"],),
        months=(month,) if month is not None else None,
    )
    for candidate in candidates:
        if candidate.server_path == request["server_path"]:
            return candidate
    raise ValueError(f"ścieżka {request['server_path']} nie należy do zbioru {dataset}")


def _scan_inputs(
    root: Path, descriptor: DatasetDescriptor
) -> tuple[list[_Input], list[str]]:
    """Current version of every archive slot of a dataset, plus unreadable slots."""
    assert descriptor.server_dir is not None
    base = root / "archives" / "versions" / PurePosixPath(descriptor.server_dir)
    if not base.exists():
        return [], []
    slots: dict[Path, str] = {}
    for sidecar in base.rglob("*.meta.json"):
        slots.setdefault(sidecar.parent.parent, sidecar.name.removesuffix(".meta.json"))
    inputs: list[_Input] = []
    problems: list[str] = []
    for slot_dir in sorted(slots):
        slot = slot_dir.relative_to(root).as_posix()
        try:
            current = _pick_current(_read_versions(root, slot, slots[slot_dir]))
            if current is None:
                continue
            if current.meta.get("dataset") != descriptor.key:
                raise IMGWDataError(
                    f"Wersja {current.relative} należy do innego zbioru"
                )
            archive = _restore_archive(descriptor.key, current.meta)
            if _slot_of(archive) != slot:
                raise IMGWDataError(
                    f"Wersja {current.relative} nie odpowiada slotowi {slot}"
                )
        except (IMGWError, ValueError, KeyError, TypeError) as exc:
            problems.append(str(exc))
            continue
        inputs.append(_Input(archive, current))
    inputs.sort(key=lambda item: item.version.slot)
    return inputs, problems


def _manifest(inputs: Iterable[_Input]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item.version.slot, item.version.sha256) for item in inputs))


@dataclass(frozen=True)
class _SeriesVersion:
    path: Path
    meta: Mapping[str, Any]
    manifest: tuple[tuple[str, str], ...]


def _series_versions(root: Path, descriptor: DatasetDescriptor) -> list[_SeriesVersion]:
    """Readable series versions of a dataset; unverifiable ones are never reused."""
    base = root / "series" / "versions" / descriptor.slug
    if not base.exists():
        return []
    result = []
    for directory in sorted(base.iterdir()):
        main = directory / "series.json"
        try:
            if directory.is_symlink() or main.is_symlink():
                continue
            meta = json.loads(
                (directory / "series.json.meta.json").read_text(encoding="utf-8")
            )
            extra = meta["extra"]
            if (
                meta["schema"] != "imgw-meta/1"
                or extra.get("series_schema") != SERIES_SCHEMA
                or hashlib.sha256(main.read_bytes()).hexdigest() != meta["sha256"]
            ):
                continue
            manifest = tuple(
                sorted(
                    (
                        PurePosixPath(source["file"]).parent.parent.as_posix(),
                        source["sha256"],
                    )
                    for source in extra["source_files"]
                )
            )
            _downloaded(meta)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        result.append(_SeriesVersion(main, meta, manifest))
    return result


def _series_state(
    root: Path,
    descriptor: DatasetDescriptor,
    inputs: list[_Input],
    *,
    reliable: bool = True,
) -> SeriesState:
    versions = _series_versions(root, descriptor)
    if not versions:
        return "missing"
    current = max(
        versions, key=lambda item: (_downloaded(item.meta), item.path.as_posix())
    )
    return (
        "current" if reliable and current.manifest == _manifest(inputs) else "outdated"
    )


def check_series(
    root: PathArg | StoreHandle,
    /,
    *,
    dataset: str,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """Offline twin of :func:`build_series`: inputs it would read and the series state."""
    path = _root(root)
    descriptor = _series_descriptor(dataset)
    inputs, problems = _scan_inputs(path, descriptor)
    items: list[PlanItem] = []
    cancelled = False
    for index, item in enumerate(inputs, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        http = item.version.http
        items.append(
            PlanItem(
                archive=item.archive,
                status="unverifiable" if cancelled else "current",
                local_path=Path(item.version.relative),
                local_sha256=item.version.sha256,
                remote_etag=http.get("etag"),
                remote_last_modified=http.get("last_modified"),
                content_length=http.get("content_length"),
                error=_CANCELLED if cancelled else None,
            )
        )
        if on_progress is not None and not cancelled:
            on_progress(
                Progress(
                    index,
                    len(inputs),
                    "archive",
                    "current",
                    f"Wejście szeregu {item.version.relative}",
                )
            )
    state = _series_state(path, descriptor, inputs, reliable=not problems)
    detail = {
        "current": f"Szereg {descriptor.slug} odpowiada bieżącym archiwom",
        "outdated": f"Szereg {descriptor.slug} wymaga przebudowy",
        "missing": f"Brak szeregu {descriptor.slug}",
    }[state]
    actions = [
        PlanAction(
            "series build",
            {"current": "current", "outdated": "newer", "missing": "missing"}[state],
            detail,
        )
    ]
    for problem in problems:
        actions.append(PlanAction("series build", "check_failed", problem))
        if on_notice is not None:
            on_notice(Notice("error", "archive_failed", problem))
    if not inputs:
        actions.append(
            PlanAction(
                "series build", "missing", f"Brak archiwów zbioru {dataset} w magazynie"
            )
        )
    return StorePlan(
        schema="imgw-plan/1",
        root=path,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state={descriptor.slug: state},
        actions=tuple(actions),
        cancelled=cancelled,
    )


def _pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as exc:
        raise IMGWStoreDependencyError(
            "Budowa szeregów Parquet wymaga pakietu pyarrow>=15. Zainstaluj dodatek: pip install imgwtools[store]"
        ) from exc
    if int(pyarrow.__version__.split(".")[0]) < 15:
        raise IMGWStoreDependencyError(
            f"Wymagany pyarrow>=15 (zainstalowano {pyarrow.__version__}). Zainstaluj dodatek: pip install imgwtools[store]"
        )
    return pyarrow, pyarrow.parquet


def _hydro_year(day: date) -> int:
    return day.year + 1 if day.month >= 11 else day.year


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _period_start(hydro_year: int, period: str) -> date:
    return date(hydro_year, 5, 1) if period == "summer" else date(hydro_year - 1, 11, 1)


_Key = tuple[date, str | None]


@dataclass
class _Station:
    values: dict[_Key, dict[str, Measurement]]
    extrema: dict[_Key, dict[str, tuple[datetime | None, datetime | None]]]
    hydro_years: set[int]


def _collect(
    stations: dict[str, _Station],
    record: NormalizedRecord,
    descriptor: DatasetDescriptor,
) -> None:
    if len(record.station_code) != 9 or not record.station_code.isdigit():
        raise IMGWDataError(f"Nieprawidłowy kod stacji: {record.station_code!r}")
    station = stations.setdefault(record.station_code, _Station({}, {}, set()))
    key = (record.date, record.period if descriptor.time_unit == "half_year" else None)
    columns = station.values.setdefault(key, {})
    for variable, measurement in record.measurements.items():
        if variable not in descriptor.variables:
            raise IMGWDataError(
                f"Nieznana zmienna {variable} w zbiorze {descriptor.key}"
            )
        if (measurement.value is None) != (
            measurement.flag == "missing"
        ) or measurement.flag not in _FLAGS:
            raise IMGWDataError(
                f"Niespójna flaga {measurement.flag} zmiennej {variable} stacji {record.station_code}"
            )
        previous = columns.get(variable)
        if previous is not None and previous != measurement:
            raise IMGWDataError(
                f"Sprzeczne wartości {variable} stacji {record.station_code} z {record.date}"
            )
        columns[variable] = measurement
    for variable, bounds in record.extrema_dates.items():
        previous_bounds = station.extrema.setdefault(key, {}).get(variable)
        if previous_bounds is not None and previous_bounds != bounds:
            raise IMGWDataError(
                f"Sprzeczne daty ekstremum {variable} stacji {record.station_code}"
            )
        station.extrema[key][variable] = bounds
    station.hydro_years.add(record.hydro_year)


def _row_keys(station: _Station, time_unit: str) -> list[tuple[_Key, int]]:
    """Every unit of the continuous station calendar, with its hydrological year."""
    if time_unit == "half_year":
        return [
            ((_period_start(year, period), period), year)
            for year in sorted(station.hydro_years)
            for period in _PERIODS
        ]
    days = sorted(day for day, _ in station.values)
    keys: list[tuple[_Key, int]] = []
    current, last = days[0], days[-1]
    while current <= last:
        keys.append(((current, None), _hydro_year(current)))
        current = (
            current + timedelta(days=1) if time_unit == "day" else _next_month(current)
        )
    return keys


def _station_table(pa: Any, station: _Station, descriptor: DatasetDescriptor) -> Any:
    keys = _row_keys(station, descriptor.time_unit)
    flags = pa.array(_FLAGS, pa.string())
    columns: dict[str, Any] = {
        "date": pa.array([key[0] for key, _ in keys], pa.date32()),
        "hydro_year": pa.array([year for _, year in keys], pa.int32()),
    }
    if descriptor.time_unit == "half_year":
        columns["period"] = pa.DictionaryArray.from_arrays(
            pa.array([_PERIODS.index(key[1]) for key, _ in keys], pa.int8()),
            pa.array(_PERIODS, pa.string()),
        )
    missing = Measurement(None, "missing")
    for variable in descriptor.variables:
        measurements = [
            station.values.get(key, {}).get(variable, missing) for key, _ in keys
        ]
        columns[f"{variable}_value"] = pa.array(
            [item.value for item in measurements], pa.float64()
        )
        columns[f"{variable}_flag"] = pa.DictionaryArray.from_arrays(
            pa.array([_FLAGS.index(item.flag) for item in measurements], pa.int8()),
            flags,
        )
        if descriptor.time_unit == "half_year":
            bounds = [
                station.extrema.get(key, {}).get(variable, (None, None))
                for key, _ in keys
            ]
            columns[f"{variable}_start"] = pa.array(
                [start for start, _ in bounds], pa.timestamp("us")
            )
            columns[f"{variable}_end"] = pa.array(
                [end for _, end in bounds], pa.timestamp("us")
            )
    metadata = {
        "imgw_schema": SERIES_SCHEMA,
        "dataset": descriptor.key,
        "units": _canonical(dict(descriptor.variables)).decode("utf-8").rstrip("\n"),
    }
    return pa.table(columns).replace_schema_metadata(metadata)


def _periods(inputs: Iterable[_Input]) -> list[list[str]]:
    """Union of exact publication periods of possessed archives, adjacent spans merged."""
    spans = sorted(
        {(item.archive.period_start, item.archive.period_end) for item in inputs}
    )
    merged: list[list[date]] = []
    for start, end in spans:
        assert start is not None and end is not None
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [[start.isoformat(), end.isoformat()] for start, end in merged]


def _copy_hashed(source: Path, target: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as reader, target.open("xb") as writer:
        for chunk in iter(lambda: reader.read(_CHUNK), b""):
            writer.write(chunk)
            digest.update(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return digest.hexdigest()


def _report(
    status: Literal["created", "reused", "cancelled", "failed"],
    *,
    version: Path | None = None,
    stations: int = 0,
    sources: Iterable[Path] = (),
    problems: Iterable[str] = (),
) -> SeriesReport:
    return SeriesReport(status, version, stations, tuple(sources), tuple(problems))


def build_series(
    root: PathArg | StoreHandle,
    /,
    *,
    dataset: str,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> SeriesReport:
    """Snapshot every station of the current archive versions as one series version."""
    path = _root(root)
    descriptor = _series_descriptor(dataset)
    pa, pq = _pyarrow()
    _check_kartograf(path)

    def cancelled() -> bool:
        return cancel is not None and cancel()

    if cancelled():
        return _report("cancelled")
    inputs, problems = _scan_inputs(path, descriptor)
    sources = [item.version.file for item in inputs]
    if problems:
        for problem in problems:
            if on_notice is not None:
                on_notice(Notice("error", "archive_failed", problem))
        return _report("failed", sources=sources, problems=problems)
    if not inputs:
        return _report(
            "failed", problems=[f"Brak archiwów zbioru {dataset} w magazynie"]
        )
    manifest = _manifest(inputs)
    for existing in sorted(
        _series_versions(path, descriptor),
        key=lambda item: (_downloaded(item.meta), item.path.as_posix()),
        reverse=True,
    ):
        if existing.manifest == manifest:
            series = json.loads(existing.path.read_text(encoding="utf-8"))
            recorded = [
                path / PurePosixPath(source["file"])
                for source in existing.meta["extra"]["source_files"]
            ]
            if on_progress is not None:
                on_progress(
                    Progress(
                        1,
                        1,
                        "series",
                        "reused",
                        f"Szereg {descriptor.slug} bez zmian wejść",
                    )
                )
            return _report(
                "reused",
                version=existing.path,
                stations=len(series["stations"]),
                sources=recorded,
            )

    stations: dict[str, _Station] = {}
    records: list[NormalizedRecord] = []
    try:
        for index, item in enumerate(inputs, start=1):
            if cancelled():
                return _report("cancelled", sources=sources)
            data = item.version.file.read_bytes()
            if hashlib.sha256(data).hexdigest() != item.version.sha256:
                raise IMGWDataError(
                    f"Suma kontrolna nie zgadza się z sidecarem: {item.version.relative}"
                )
            for record in normalize_archive(item.archive, data=data):
                _collect(stations, record, descriptor)
                records.append(record)
            if on_progress is not None:
                on_progress(
                    Progress(
                        index,
                        len(inputs),
                        "archive",
                        "parsed",
                        f"Odczytano {item.version.relative}",
                    )
                )
        # Lazy import: imgwtools.coverage imports store.types, which loads this package.
        from imgwtools.coverage import summarize_coverage

        coverage = summarize_coverage(records, dataset=dataset)
    except (IMGWDataError, IMGWValidationError, OSError) as exc:
        if on_notice is not None:
            on_notice(Notice("error", "archive_failed", str(exc)))
        return _report("failed", sources=sources, problems=[str(exc)])
    del records

    variables: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for entry in coverage:
        name = (
            entry.variable
            if entry.period is None
            else f"{entry.variable}@{entry.period}"
        )
        variables[entry.station][name] = {
            "unit": entry.unit,
            "first": entry.first.isoformat() if entry.first else None,
            "last": entry.last.isoformat() if entry.last else None,
            "with_value": entry.with_value,
            "accumulated": entry.accumulated,
            "gaps": [[start.isoformat(), end.isoformat()] for start, end in entry.gaps],
        }

    incoming = path / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    (staging / "stations").mkdir(parents=True)
    try:
        index_stations: dict[str, dict[str, Any]] = {}
        with tempfile.TemporaryDirectory(prefix="imgw-series-") as local:
            total = len(stations)
            for number, code in enumerate(sorted(stations), start=1):
                if cancelled():
                    return _report("cancelled", sources=sources)
                table = _station_table(pa, stations.pop(code), descriptor)
                built = Path(local) / f"{code}.parquet"
                pq.write_table(table, built)
                digest = _copy_hashed(built, staging / "stations" / f"{code}.parquet")
                built.unlink()
                index_stations[code] = {
                    "file": f"stations/{code}.parquet",
                    "sha256": digest,
                    "rows": table.num_rows,
                    "variables": variables[code],
                }
                if on_progress is not None:
                    on_progress(
                        Progress(number, total, "station", "written", f"Stacja {code}")
                    )
        _fsync_dir(staging / "stations")
        series = {
            "schema": SERIES_SCHEMA,
            "dataset": dataset,
            "year_type": descriptor.year_type,
            "periods": _periods(inputs),
            "stations": index_stations,
        }
        content = _canonical(series)
        sha = hashlib.sha256(content).hexdigest()
        _write_json(staging / "series.json", series)
        published = [
            moment
            for item in inputs
            if (moment := _parse_time(item.version.http.get("last_modified")))
        ]
        now = datetime.now(UTC)
        label = (
            max(published).date().isoformat() if published else now.date().isoformat()
        )
        license_info = asdict(descriptor.license)
        license_info["attribution"] = f"{descriptor.license.attribution}. {_PROCESSED}"
        source_files = [
            {
                "name": item.version.file.name,
                "file": item.version.relative,
                "sha256": item.version.sha256,
                "label": item.version.label,
            }
            for item in sorted(inputs, key=lambda entry: entry.version.relative)
        ]

        def sidecar(version_label: str) -> dict[str, Any]:
            return {
                "schema": "imgw-meta/1",
                "producer": "imgwtools",
                "producer_version": __version__,
                "dataset": dataset,
                "country": "PL",
                "provider": "IMGW-PIB",
                "request": {"dataset": dataset},
                "license": license_info,
                "downloaded_at": _utc(now),
                "sha256": sha,
                "size_bytes": len(content),
                "extra": {
                    "version": {"label": version_label, "label_source": "inputs"},
                    "derived": "series",
                    "series_schema": SERIES_SCHEMA,
                    "source_files": source_files,
                },
            }

        if cancelled():
            return _report("cancelled", sources=sources)
        parent = path / "series" / "versions" / descriptor.slug
        # Identical series.json from a different input manifest (e.g. re-zipped archive)
        # gets a stable manifest suffix instead of replacing the existing version.
        suffix = (
            "+"
            + hashlib.sha256(_canonical([list(pair) for pair in manifest])).hexdigest()[
                :8
            ]
        )
        for candidate in (label, label + suffix):
            target = _validate_slot(
                path, f"series/versions/{descriptor.slug}/{candidate}_{sha[:8]}"
            )
            meta_path = staging / "series.json.meta.json"
            meta_path.unlink(missing_ok=True)
            _write_json(meta_path, sidecar(candidate))
            _fsync_dir(staging)
            parent.mkdir(parents=True, exist_ok=True)
            try:
                _atomic_publish(staging, target)
            except FileExistsError:
                if any(
                    existing.path.parent == target and existing.manifest == manifest
                    for existing in _series_versions(path, descriptor)
                ):
                    return _report(
                        "reused",
                        version=target / "series.json",
                        stations=len(index_stations),
                        sources=sources,
                    )
                continue
            if on_notice is not None:
                on_notice(
                    Notice(
                        "info",
                        "license_terms",
                        f"{license_info['attribution']}. Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.",
                    )
                )
            return _report(
                "created",
                version=target / "series.json",
                stations=len(index_stations),
                sources=sources,
            )
        raise IMGWStoreConflictError(f"Kolizja katalogu wersji szeregu: {parent}")
    finally:
        if staging.exists():
            shutil.rmtree(staging)
