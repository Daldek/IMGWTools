"""Offline fixture store for contract tests of IMGWTools consumers.

``build_fixture_store`` builds a small versioned store with the real public writers
(``init_store``, ``write_archive``, ``build_series``, ``build_catalog``) while every
HTTP request is answered from recordings shipped with the package. No request reaches
the network; an unrecorded request fails as a connection error.

Requires the ``pyarrow`` dependency of series building (``imgwtools[store]``).
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal, get_args

import httpx

from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWDataError, IMGWStoreError, IMGWValidationError
from imgwtools.fetch import download_hydro_data, download_meteo_data
from imgwtools.store import build_catalog, build_series, init_store, write_archive
from imgwtools.store import catalog as _store_catalog
from imgwtools.store.types import PathArg, StoreHandle
from imgwtools.store.writer import _canonical

__all__ = ["FixtureVariant", "build_fixture_store", "fixture_files"]

FixtureVariant = Literal["complete", "corrupt", "unknown_schema"]

_RECORDINGS = ("recordings.json", "builder_recordings.json")
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
# Recorder patching is process-global; serialize concurrent builders.
_HTTP_LOCK = threading.Lock()


def fixture_files() -> Traversable:
    """Packaged synthetic archives and recorded HTTP answers (``importlib.resources``).

    Layout: ``archives/<IMGW server path>``, ``variants/``, ``recordings.json`` and
    ``builder_recordings.json``. Data are short synthetic samples, not real yearbooks.
    """
    return files("imgwtools").joinpath("_data", "fixtures")


def _interactions() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in _RECORDINGS:
        document = json.loads(
            fixture_files().joinpath(name).read_text(encoding="utf-8")
        )
        for interaction in document["interactions"]:
            interaction.setdefault(
                "url", f"{document.get('base_url')}/{interaction.get('path')}"
            )
            result[interaction["case"]] = interaction
    return result


def _body(interaction: Mapping[str, Any]) -> tuple[bytes, dict[str, str]]:
    headers = dict(interaction.get("headers") or {})
    if "json" in interaction:
        headers.setdefault("Content-Type", "application/json")
        return json.dumps(interaction["json"], ensure_ascii=False).encode(
            "utf-8"
        ), headers
    if "archive" in interaction:
        resource = fixture_files().joinpath(
            "archives", *interaction["archive"].split("/")
        )
    elif "variant" in interaction:
        resource = fixture_files().joinpath(*interaction["variant"].split("/"))
    else:
        return b"", headers
    data = resource.read_bytes()
    expected = interaction.get("sha256")
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise IMGWDataError(
            f"Suma nagrania {interaction['case']} nie zgadza się z plikiem fixtury"
        )
    return data, headers


@contextmanager
def _recorded_http(cases: Iterator[str] | tuple[str, ...]) -> Iterator[None]:
    """Answer synchronous httpx requests from recordings, in the given order per URL."""
    recorded = _interactions()
    queues: dict[tuple[str, str], deque[Mapping[str, Any]]] = {}
    for case in cases:
        interaction = recorded[case]
        queues.setdefault((interaction["method"], interaction["url"]), deque()).append(
            interaction
        )

    def handle(
        transport: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        queue = queues.get((request.method, str(request.url)))
        if not queue:
            raise httpx.ConnectError(
                f"Brak nagranej odpowiedzi dla {request.method} {request.url}",
                request=request,
            )
        interaction = queue.popleft()
        content, headers = _body(interaction)
        return httpx.Response(
            interaction["status"], headers=headers, content=content, request=request
        )

    with _HTTP_LOCK:
        original = httpx.HTTPTransport.handle_request
        httpx.HTTPTransport.handle_request = handle  # pyright: ignore[reportAttributeAccessIssue]
        try:
            yield
        finally:
            httpx.HTTPTransport.handle_request = original  # pyright: ignore[reportAttributeAccessIssue]
    left = sorted(f"{method} {url}" for (method, url), queue in queues.items() if queue)
    if left:
        raise IMGWDataError(f"Nie wykorzystano nagranych odpowiedzi: {', '.join(left)}")


def _expect(step: str, status: str, expected: str) -> None:
    if status != expected:
        raise IMGWDataError(
            f"Fixtura: krok {step} zakończył się statusem {status}, oczekiwano {expected}"
        )


@contextmanager
def _without_reference_data() -> Iterator[None]:
    """Hide the local static locations file (``settings.data_dir``) from the catalog.

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


def build_fixture_store(
    root: PathArg, *, variant: FixtureVariant = "complete"
) -> StoreHandle:
    """Build an offline fixture store with the public writers in an empty ``root``.

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
    """
    if variant not in get_args(FixtureVariant):
        raise IMGWValidationError(
            f"Nieznany wariant fixtury: {variant!r}; dozwolone: {', '.join(get_args(FixtureVariant))}"
        )
    path = Path(root)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise IMGWStoreError(f"Magazyn fixtury wymaga pustego katalogu: {path}")
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
            "szereg hydro v1", build_series(handle, dataset=_HYDRO).status, "created"
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
            "szereg hydro v2", build_series(handle, dataset=_HYDRO).status, "created"
        )
        meteo = write_archive(
            handle,
            archive=meteo_2001,
            response=download_meteo_data("dobowe", "opad", 2001, 1),
        )
        _expect("2001_01_o", meteo.status, "created")
        _expect("szereg meteo", build_series(handle, dataset=_METEO).status, "created")
        late = write_archive(
            handle,
            archive=meteo_1995,
            response=download_meteo_data("dobowe", "opad", 1995),
        )
        _expect("1995_o", late.status, "created")
        with _without_reference_data():
            catalog = build_catalog(handle)
        _expect("katalog stacji", catalog.status, "created")
        if catalog.without_location == 0:
            raise IMGWDataError("Fixtura: katalog stacji bez stacji z geometry=null")
    if variant == "corrupt":
        sidecar = old.path.with_name(f"{old.path.name}.meta.json")
        sidecar.write_bytes(sidecar.read_bytes()[: sidecar.stat().st_size // 2])
    elif variant == "unknown_schema":
        _add_unknown_version(handle.root)
    return handle
