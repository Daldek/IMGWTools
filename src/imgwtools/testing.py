"""Offline fixture store for contract tests of IMGWTools consumers.

``build_fixture_store`` builds a small versioned store with the real public writers
(``init_store``, ``write_archive``, ``sync_store``, ``build_series``,
``build_catalog``) while every HTTP request is answered from recordings shipped with
the package. No request reaches the network; an unrecorded request fails as a
connection error.

Requires the ``pyarrow`` dependency of series building (``imgwtools[store]``).
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal, get_args
from unittest import mock

import httpx

from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.fetch import download_hydro_data, download_meteo_data
from imgwtools.messages import message
from imgwtools.store import (
    build_catalog,
    build_series,
    init_store,
    sync_store,
    write_archive,
)
from imgwtools.store import catalog as _store_catalog
from imgwtools.store.types import PathArg, StoreHandle
from imgwtools.store.writer import _canonical

__all__ = ["FixtureVariant", "build_fixture_store", "fixture_files"]

FixtureVariant = Literal["complete", "corrupt", "unknown_schema", "complete_pl_cz"]

_RECORDINGS = ("recordings.json", "builder_recordings.json")
_CHMI_RECORDINGS = ("chmi_builder_recordings.json",)
_HYDRO = "pl.imgw.hydro_daily"
_METEO = "pl.imgw.meteo_precip_daily"
_UNKNOWN_LABEL = "2026-10-20"
# Recorded answers in the order the scenario requests them; repeated URLs are queued.
_SCENARIO = (
    "hydro_get",
    "same_bytes_new_signal",
    "new_bytes_get",
    "meteo_get",
    "meteo_1995_get",
    "hydro_stations_get",
    "meteo_stations_get",
    "hydro_current",
    "meteo_current",
)
_CHMI_HYDRO = "cz.chmi.hydro_daily"
_CHMI_METEO = "cz.chmi.meteo_daily"
# Fictional ČHMÚ stations of the fixture files (spec 2026-10-18 §13.2).
_CHMI_FULL, _CHMI_GAP = "0-203-1-900001", "0-203-1-900002"
_CHMI_ELEMENTS, _CHMI_RAIN = "0-203-0-90001", "0-203-0-90000000002"
# ČHMÚ part of complete_pl_cz (spec 2026-10-18 §13.2 scenarios (1)-(3) and (8)):
# sync_store selectors with the expected statuses of the items and of the series.
_CHMI_STEPS: tuple[tuple[str, Mapping[str, Any], tuple[str, ...], str], ...] = (
    (
        "ČHMÚ hydro (1) first publication",
        {"datasets": (_CHMI_HYDRO,), "stations": (_CHMI_FULL, _CHMI_GAP)},
        ("created",) * 4,
        "created",
    ),
    (
        "ČHMÚ hydro (2) republication",
        {"datasets": (_CHMI_HYDRO,), "stations": (_CHMI_GAP,)},
        ("relabeled",) * 2,
        "reused",
    ),
    (
        "ČHMÚ hydro (3) correction",
        {"datasets": (_CHMI_HYDRO,), "stations": (_CHMI_FULL,), "years": (2024,)},
        ("created",),
        "created",
    ),
    (
        "ČHMÚ hydro (8) reserialization",
        {"datasets": (_CHMI_HYDRO,), "stations": (_CHMI_FULL,), "years": (2023,)},
        ("unchanged",),
        "reused",
    ),
    (
        "ČHMÚ meteo",
        {"datasets": (_CHMI_METEO,), "stations": (_CHMI_ELEMENTS, _CHMI_RAIN)},
        # The three temperature elements of the precipitation-only station are
        # not published: unchanged without a version.
        ("created",) * 5 + ("unchanged",) * 3,
        "created",
    ),
)
# Recorder patching is process-global; serialize concurrent builders.
_HTTP_LOCK = threading.Lock()


def fixture_files() -> Traversable:
    """
    Return the packaged fixture data directory.

    Layout: ``archives/<server path>`` (IMGW-PIB yearbooks and station lists,
    ČHMÚ station files and metadata), ``listings/`` (ČHMÚ directory
    listings), ``variants/``, recorded HTTP answers ``recordings.json``,
    ``builder_recordings.json``, ``chmi_recordings.json``,
    ``chmi_catalog_recordings.json``, ``chmi_builder_recordings.json`` and
    ``contract_recordings.json`` (live endpoints of the interface contract
    tests), and ``contract_schemas.json`` (JSON Schemas with examples of the
    store documents ``imgw-store/1`` ... ``imgw-pmaxtp/1``, the envelope
    ``imgw-result/1`` and the error documents ``problem+json`` and
    ``cli-error``). Data are short synthetic samples with fictional station
    codes, not real yearbooks.

    Returns
    -------
    importlib.resources.abc.Traversable
        Synthetic archives and recorded HTTP answers, read via
        ``importlib.resources``.
    """
    return files("imgwtools").joinpath("_data", "fixtures")


def _interactions(recordings: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Recorded interactions of the given files keyed by case, in file order."""
    result: dict[str, dict[str, Any]] = {}
    for name in recordings:
        document = json.loads(
            fixture_files().joinpath(name).read_text(encoding="utf-8")
        )
        base = str(document.get("base_url")).rstrip("/")
        for interaction in document["interactions"]:
            interaction.setdefault("url", f"{base}/{interaction.get('path')}")
            result[interaction["case"]] = interaction
    return result


def _body(interaction: Mapping[str, Any]) -> tuple[bytes, dict[str, str]]:
    headers = dict(interaction.get("headers") or {})
    if "json" in interaction:
        headers.setdefault("Content-Type", "application/json")
        return json.dumps(interaction["json"], ensure_ascii=False).encode(
            "utf-8"
        ), headers
    if "body" in interaction:
        return str(interaction["body"]).encode("utf-8"), headers
    if "archive" in interaction:
        resource = fixture_files().joinpath(
            "archives", *interaction["archive"].split("/")
        )
    elif "variant" in interaction or "listing" in interaction:
        relative = interaction.get("variant") or interaction["listing"]
        resource = fixture_files().joinpath(*relative.split("/"))
    else:
        return b"", headers
    data = resource.read_bytes()
    expected = interaction.get("sha256")
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise IMGWDataError(
            message(
                "testing.checksum_recording_does_not_match", case=interaction["case"]
            )
        )
    return data, headers


@contextmanager
def _recorded_http(
    cases: Iterable[str] | None, *, recordings: Iterable[str] = _RECORDINGS
) -> Iterator[None]:
    """
    Answer synchronous httpx requests from recordings, in the given order per URL.

    ``cases=None`` replays every interaction of ``recordings`` in file order.
    """
    recorded = _interactions(recordings)
    queues: dict[tuple[str, str], deque[Mapping[str, Any]]] = {}
    for case in recorded if cases is None else cases:
        interaction = recorded[case]
        queues.setdefault((interaction["method"], interaction["url"]), deque()).append(
            interaction
        )

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        queue = queues.get((request.method, str(request.url)))
        if not queue:
            raise httpx.ConnectError(
                message(
                    "testing.no_recorded_response",
                    method=request.method,
                    url=request.url,
                ),
                request=request,
            )
        interaction = queue.popleft()
        content, headers = _body(interaction)
        return httpx.Response(
            interaction["status"], headers=headers, content=content, request=request
        )

    with _HTTP_LOCK, mock.patch.object(httpx.HTTPTransport, "handle_request", handle):
        yield
    left = sorted(f"{method} {url}" for (method, url), queue in queues.items() if queue)
    if left:
        raise IMGWDataError(
            message("testing.recorded_responses_were_not_used", left=", ".join(left))
        )


def _expect(step: str, status: str, expected: str) -> None:
    if status != expected:
        raise IMGWDataError(
            message(
                "testing.fixture_step_ended_status_expected",
                step=step,
                status=status,
                expected=expected,
            )
        )


@contextmanager
def _without_reference_data() -> Iterator[None]:
    """Hide the local static locations file (``settings.reference_dir``) from the catalog.

    Fixture stores must not depend on reference data a user fetched with
    ``python -m imgwtools.reference_data``. Process-global: call under ``_HTTP_LOCK``.
    """
    original = _store_catalog._static_file
    _store_catalog._static_file = lambda: (Path(_store_catalog.STATIC_LOCATIONS), None)
    try:
        yield
    finally:
        _store_catalog._static_file = original


def _add_unknown_version(root: Path) -> None:
    """Series version of an unknown major schema, which writers refuse to produce."""
    data = _canonical({"schema": "imgw-series/2", "dataset": _HYDRO})
    sha = hashlib.sha256(data).hexdigest()
    target = (
        root / "series" / "versions" / "hydro_daily" / f"{_UNKNOWN_LABEL}_{sha[:8]}"
    )
    target.mkdir(parents=True)
    (target / "series.json").write_bytes(data)
    (target / "series.json.meta.json").write_bytes(
        _canonical(
            {
                "schema": "imgw-meta/2",
                "producer": "imgwtools",
                "dataset": _HYDRO,
                "sha256": sha,
                "size_bytes": len(data),
                "extra": {
                    "version": {"label": _UNKNOWN_LABEL, "label_source": "downloaded"}
                },
            }
        )
    )


def _add_chmi(handle: StoreHandle) -> None:
    """
    ČHMÚ part of ``complete_pl_cz``, replayed from ``chmi_builder_recordings.json``.

    Each step is one `sync_store` (listing, then HEAD and GET of every new or
    changed file, then the dataset's series); the ČHMÚ catalog is built last.
    """
    with _recorded_http(None, recordings=_CHMI_RECORDINGS):
        for step, selectors, items, built in _CHMI_STEPS:
            report = sync_store(handle, **selectors)
            _expect(
                step,
                ", ".join(sorted(item.status for item in report.items)),
                ", ".join(sorted(items)),
            )
            _expect(
                f"{step}: series",
                ", ".join(series.status for series in report.series),
                built,
            )
        catalog = build_catalog(handle, provider="CHMI")
        _expect("ČHMÚ station catalog", catalog.status, "created")


def build_fixture_store(
    root: PathArg, *, variant: FixtureVariant = "complete"
) -> StoreHandle:
    """
    Build an offline fixture store with the public writers in an empty ``root``.

    ``complete`` contains:

    * ``codz_2024.zip`` (``pl.imgw.hydro_daily``) in three versions: the old one, the
      same bytes relabeled under a newer HTTP signal and newer bytes (current);
    * two ``hydro_daily`` series: an older one built from the old archive and the
      current one built from the newer archive;
    * ``meteo_precip_daily`` series that is outdated (``1995_o.zip`` was stored after
      the series was built from ``2001_01_o.zip``);
    * both station lists and a ``stations.geojson`` catalog with stations whose
      ``geometry`` is ``null``, built without the local static locations file
      (recorded in its sidecar as ``available: false``).

    ``corrupt`` additionally truncates the sidecar of the old hydro archive version;
    ``unknown_schema`` additionally adds a ``hydro_daily`` series version with
    ``imgw-meta/2``/``imgw-series/2`` that readers must report without parsing.

    ``complete_pl_cz`` is ``complete`` plus the ČHMÚ provider (spec 2026-10-18
    §13.3), synchronized with `sync_store` from ``chmi_builder_recordings.json``
    (fictional station codes):

    * ``cz.chmi.hydro_daily`` files: ``H_0-203-1-900002_DQ_2004.json`` and
      ``…_2006.json`` in a first and a ``relabeled`` version (the same bytes
      republished), ``H_0-203-1-900001_DQ_2024.json`` in a first and a
      corrected version, and ``H_0-203-1-900001_DQ_2023.json`` in one version
      with an observation in ``observations/`` (re-serialized bytes with the
      same canonical content, ``content_unchanged``);
    * ``cz.chmi.meteo_daily`` CSV files of ``0-203-0-90001`` (SRA, T, TMA,
      TMI) and ``0-203-0-90000000002`` (SRA only);
    * the ``chmi_hydro_daily`` series in two versions (before and after the
      correction), the ``chmi_meteo_daily`` series, both ČHMÚ station lists
      and the ČHMÚ catalog ``stations/versions/chmi_stations/``.

    Parameters
    ----------
    root : str or os.PathLike
        Store directory; it must not exist or be an empty directory.
    variant : {"complete", "corrupt", "unknown_schema", "complete_pl_cz"}, optional
        Fixture variant to build.

    Returns
    -------
    StoreHandle
        Handle of the built store.

    Raises
    ------
    IMGWValidationError
        If ``variant`` is unknown.
    IMGWStoreError
        If ``root`` is not an empty directory.
    IMGWDataError
        If a build step ends with an unexpected status, a recording does not match
        its checksum or recorded answers are left unused.
    IMGWConnectionError
        If a request has no recorded answer.
    """
    if variant not in get_args(FixtureVariant):
        raise IMGWValidationError(
            message(
                "testing.unknown_fixture_variant_allowed",
                variant=variant,
                allowed=", ".join(get_args(FixtureVariant)),
            )
        )
    path = Path(root)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise IMGWStoreError(
            message("testing.fixture_store_needs_empty_directory", path=path)
        )
    handle = init_store(path)
    (hydro,) = archive_files(_HYDRO, years=(2024,))
    (meteo_2001,) = archive_files(_METEO, years=(2001,), months=(1,))
    (meteo_1995,) = archive_files(_METEO, years=(1995,))
    with _recorded_http(_SCENARIO):
        old = write_archive(
            handle, archive=hydro, response=download_hydro_data("dobowe", 2024)
        )
        _expect("codz_2024 v1", old.status, "created")
        _expect(
            "series hydro v1", build_series(handle, dataset=_HYDRO).status, "created"
        )
        relabeled = write_archive(
            handle, archive=hydro, response=download_hydro_data("dobowe", 2024)
        )
        _expect("codz_2024 v2", relabeled.status, "relabeled")
        newer = write_archive(
            handle, archive=hydro, response=download_hydro_data("dobowe", 2024)
        )
        _expect("codz_2024 v3", newer.status, "created")
        _expect(
            "series hydro v2", build_series(handle, dataset=_HYDRO).status, "created"
        )
        meteo = write_archive(
            handle,
            archive=meteo_2001,
            response=download_meteo_data("dobowe", "opad", 2001, 1),
        )
        _expect("2001_01_o", meteo.status, "created")
        _expect("series meteo", build_series(handle, dataset=_METEO).status, "created")
        late = write_archive(
            handle,
            archive=meteo_1995,
            response=download_meteo_data("dobowe", "opad", 1995),
        )
        _expect("1995_o", late.status, "created")
        with _without_reference_data():
            catalog = build_catalog(handle)
        _expect("station catalog", catalog.status, "created")
        if catalog.without_location == 0:
            raise IMGWDataError(message("testing.fixture_station_catalog_has_no"))
    if variant == "corrupt":
        sidecar = old.path.with_name(f"{old.path.name}.meta.json")
        sidecar.write_bytes(sidecar.read_bytes()[: sidecar.stat().st_size // 2])
    elif variant == "unknown_schema":
        _add_unknown_version(handle.root)
    elif variant == "complete_pl_cz":
        _add_chmi(handle)
    return handle
