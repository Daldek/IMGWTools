"""Incremental scan of the store: ``iter_store(skip_versions=...)``, the versions a consumer knows."""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import respx

from imgwtools.exceptions import IMGWValidationError
from imgwtools.store import init_store, iter_store, sync_pmaxtp
from imgwtools.store import reader as reader_module
from imgwtools.testing import build_fixture_store
from tests.unit.test_store_reader import (
    DAILY,
    DAILY_2024,
    observe,
    record_catalog_sources,
    store_archives,
    with_content,
)


def known_versions(root, entries):
    """What a consumer keeps of a scan: the directory of each version and its file names."""
    return {
        entry.version.parent.relative_to(root).as_posix(): (entry.version.name,)
        for entry in entries
        if entry.meta is not None
    }


def skipped(entry):
    """The entry as a scan that knows its version gives it."""
    return replace(entry, meta=None, skipped=True) if entry.meta else entry


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    """Versions of every kind of both providers, an observation register and a PMAXTP cell."""
    root = build_fixture_store(
        tmp_path_factory.mktemp("skip") / "store", variant="complete_pl_cz"
    ).root
    with respx.mock(assert_all_called=False) as router:
        record_catalog_sources(router)
        sync_pmaxtp(root, method="POT", latitude=52.23, longitude=21.01)
    return root


class Seen:
    """The directories listed and the sidecars read during a scan."""

    def __init__(self):
        self.listed: set[Path] = set()
        self.read: set[Path] = set()

    def clear(self):
        self.listed.clear()
        self.read.clear()


@pytest.fixture
def spy(monkeypatch):
    seen = Seen()
    iterdir, load_meta = Path.iterdir, reader_module._load_meta

    def listing(self):
        seen.listed.add(self)
        return iterdir(self)

    def reading(sidecar):
        seen.read.add(sidecar)
        return load_meta(sidecar)

    monkeypatch.setattr(Path, "iterdir", listing)
    monkeypatch.setattr(reader_module, "_load_meta", reading)
    return seen


def test_a_scan_gives_the_known_versions_back_without_listing_or_reading_them(
    store, spy
):
    full = list(iter_store(store))
    known = known_versions(store, full)
    assert {entry.kind for entry in full if entry.meta} == {
        "archive",
        "series",
        "catalog",
        "pmaxtp",
    }
    assert {entry.provider for entry in full if entry.meta} == {"IMGW-PIB", "CHMI"}
    directories = {store / directory for directory in known}
    # A scan reads each version: its directory is listed and its sidecar loaded.
    assert directories <= spy.listed and spy.read
    spy.clear()

    incremental = list(iter_store(store, skip_versions=known))

    assert incremental == [skipped(entry) for entry in full]
    assert not directories & spy.listed
    # Only an observation reads the sidecar of the version it names (the content fields).
    observations = [entry for entry in full if entry.kind == "observation"]
    assert observations
    assert {sidecar.parent for sidecar in spy.read} == {
        entry.version.parent.parent / entry.observation.same_content_as
        for entry in observations
    }


def test_a_known_version_that_broke_since_is_not_seen_but_the_rest_is(tmp_path, store):
    root = tmp_path / "store"
    shutil.copytree(store, root)
    known = known_versions(root, iter_store(root))
    broken = next(e for e in iter_store(root, kind="archive") if e.slot == DAILY_2024)
    gone = next(iter_store(root, kind="series", provider="CHMI"))
    Path(f"{broken.version}.meta.json").write_text("{broken", encoding="utf-8")
    shutil.rmtree(gone.version.parent)
    unfinished = root / "stations" / "versions" / "2026-01-01_deadbeef"
    unfinished.mkdir()
    (new,) = store_archives(root, DAILY, [2023])

    full = list(iter_store(root))
    incremental = list(iter_store(root, skip_versions=known))

    by_path = {entry.version: entry for entry in incremental}
    # The scan that knows a version does not look at it; a full scan reports it.
    assert (by_path[broken.version].skipped, by_path[broken.version].problem_code) == (
        True,
        None,
    )
    assert {
        (entry.slot, entry.problem_code)
        for entry in full
        if entry.version == broken.version.parent
    } == {(DAILY_2024, "invalid_json")}
    # What it does not know is read as always: a new version and an unfinished one;
    # a known version that is gone is not reported.
    assert by_path[new.path].meta is not None and not by_path[new.path].skipped
    assert by_path[unfinished].problem_code == "missing_sidecar"
    assert gone.version not in by_path
    assert [entry for entry in incremental if entry.kind == "problem"] == [
        entry
        for entry in full
        if entry.kind == "problem" and entry.version != broken.version.parent
    ]


def test_an_observation_is_checked_against_the_version_it_names_though_it_is_skipped(
    tmp_path,
):
    root = init_store(tmp_path / "store").root
    (written,) = store_archives(root, DAILY, [2024])
    with_content(written.path)
    observe(written.path)
    full = list(iter_store(root))
    known = known_versions(root, full)

    assert [entry.kind for entry in full] == ["archive", "observation"]
    assert list(iter_store(root, skip_versions=known)) == [skipped(e) for e in full]

    # Observed content that differs from that of the version is a problem, as in a full scan.
    other = observe(written.path, etag='"v3"', content_sha256="3" * 64)
    incremental = list(iter_store(root, skip_versions=known))
    assert incremental == [skipped(entry) for entry in iter_store(root)]
    assert [(e.problem_code, e.version) for e in incremental if e.problem_code] == [
        ("invalid_meta", other)
    ]


def test_the_filters_apply_to_the_versions_that_are_skipped(store):
    known = known_versions(store, iter_store(store))
    everything = list(iter_store(store, skip_versions=known))

    for filters in ({"kind": "series"}, {"provider": "CHMI"}, {"kind": "catalog"}):
        wanted = list(iter_store(store, skip_versions=known, **filters))
        assert wanted == [
            entry
            for entry in everything
            if entry.kind == filters.get("kind", entry.kind)
            and entry.provider in (filters.get("provider", entry.provider), None)
        ]
        assert any(entry.skipped for entry in wanted)


def test_what_names_no_version_of_the_store_is_read_as_unknown(store):
    full = list(iter_store(store))
    version = next(entry for entry in full if entry.slot == DAILY_2024 and entry.meta)
    known = {
        "archives/versions": ("x.zip",),
        "archives/versions/dane_hydrologiczne/dobowe/2024": ("codz_2024.zip",),
        "series/versions/hydro_daily/2026-01-01_deadbeef": ("series.json",),
        "elsewhere/2026-01-01_deadbeef": ("codz_2024.zip",),
        # a version whose names lack its main file: the caller is not sure of it
        version.version.parent.relative_to(store).as_posix(): ("another.zip",),
    }

    assert list(iter_store(store, skip_versions=known)) == full


@pytest.mark.parametrize("known", [None, {}], ids=["none", "empty"])
def test_nothing_known_is_a_full_scan(store, known):
    assert list(iter_store(store, skip_versions=known)) == list(iter_store(store))


@pytest.mark.parametrize(
    "known",
    [
        ["archives/versions/a/2026-01-01_deadbeef"],
        "archives/versions/a/2026-01-01_deadbeef",
        {"archives/versions/a/2026-01-01_deadbeef": "codz_2024.zip"},
        {"archives/versions/a/2026-01-01_deadbeef": None},
        {"archives/versions/a/2026-01-01_deadbeef": [2024]},
        {"archives/versions/a/2026-01-01_deadbeef": ["a/codz_2024.zip"]},
        {"archives/versions/a/2026-01-01_deadbeef": [".."]},
        {"archives/versions/a/2026-01-01_deadbeef": ["codz_2024.zip.meta.json"]},
        {1: ["codz_2024.zip"]},
    ],
)
def test_skip_versions_must_map_directories_to_file_names(tmp_path, known):
    root = init_store(tmp_path / "store").root

    # Refused at the call, not at the first entry.
    with pytest.raises(IMGWValidationError) as error:
        iter_store(root, skip_versions=known)

    assert error.value.details == {"option": "skip_versions"}
