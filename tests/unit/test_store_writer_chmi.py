"""``write_archive`` for ČHMÚ files: registry sidecars and the §3.1 decision table.

Spec 2026-10-18 §3, §3.1, §3.2 (ADR-003 D6, D17, D18). Synthetic files only;
codes 0-203-1-9… and 0-203-0-9… are not published by ČHMÚ.
"""

import hashlib
import json
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools._version import __version__
from imgwtools.datasets import archive_files, get_provider, station_source_files
from imgwtools.exceptions import IMGWCancelledError, IMGWDataError
from imgwtools.fetch import DownloadResult
from imgwtools.store import (
    current_version,
    init_store,
    iter_store,
    read_meta,
    write_archive,
    writer,
)
from imgwtools.store.content import content_sha256
from imgwtools.store.pmaxtp import sync_pmaxtp
from imgwtools.testing import build_fixture_store
from tests.contract.support import schema_errors

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
FORM = "chmi-json/1"
CODE = "0-203-1-900001"
(HYDRO,) = archive_files("cz.chmi.hydro_daily", stations=[CODE], years=[2025])
SLOT = f"archive:cz.chmi.hydro_daily:H_{CODE}_DQ_2025.json"
SLOT_DIR = f"archives/versions/hydrology/historical/data/daily/H_{CODE}_DQ_2025"
SERIES = {
    "tsConID": "QD",
    "unit": "M3_S",
    "tsData": {
        "type": "DataCollection",
        "data": {
            "header": "DT,VAL",
            "values": [["2025-01-01T00:00:00Z", 12], ["2025-01-02T00:00:00Z", 0.419]],
        },
    },
}
# The file as published, the same data with the top-level keys swapped (other
# bytes of the same size), a second serialization (spaces, 12.0) and a correction.
FIRST = json.dumps({"objID": CODE, "tsList": [SERIES]}, separators=(",", ":")).encode()
SWAPPED = json.dumps(
    {"tsList": [SERIES], "objID": CODE}, separators=(",", ":")
).encode()
RESERIALIZED = (
    json.dumps({"objID": CODE, "tsList": [SERIES]}, indent=1)
    .replace(" 12\n", " 12.0\n")
    .encode()
)
CORRECTED = FIRST.replace(b"0.419", b"0.42")
PUBLISHED = datetime(2026, 5, 21, 11, 19, 3, tzinfo=UTC)
REGENERATED = datetime(2026, 10, 19, 3, 12, 44, tzinfo=UTC)
LATER = datetime(2026, 10, 20, 3, 0, 0, tzinfo=UTC)
FROZEN_AT = datetime(2026, 10, 20, 9, 0, 0, 123456, tzinfo=UTC)


def response(archive, data, moment):
    """GET answer of nginx: ETag ``"<hex mtime>-<hex size>"`` and Last-Modified."""
    etag = f'"{int(moment.timestamp()):x}-{len(data):x}"'
    modified = format_datetime(moment, usegmt=True)
    return DownloadResult(data, archive.url, etag, modified, len(data))


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def versions(root):
    return sorted(
        path.name for path in (root / SLOT_DIR).iterdir() if path.name != "observations"
    )


def register(root):
    path = root / SLOT_DIR / "observations"
    return sorted(item.name for item in path.iterdir()) if path.exists() else []


def leftovers(root):
    incoming = root / ".incoming"
    return list(incoming.iterdir()) if incoming.exists() else []


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    monkeypatch.setattr(writer, "datetime", Frozen)
    return FROZEN_AT


def test_chmi_sidecar_takes_country_provider_and_license_from_the_registry(root):
    notices = []
    written = write_archive(
        root,
        archive=HYDRO,
        response=response(HYDRO, FIRST, PUBLISHED),
        on_notice=notices.append,
    )
    assert written.status == "created"
    assert written.path.relative_to(root).as_posix() == (
        f"{SLOT_DIR}/2026-05-21_{written.sha256[:8]}/H_{CODE}_DQ_2025.json"
    )
    meta = sidecar(written.path)
    assert schema_errors(meta, "imgw-meta/1") == []
    chmi = get_provider("CHMI")
    etag = f'"{int(PUBLISHED.timestamp()):x}-{len(FIRST):x}"'
    assert meta == {
        "schema": "imgw-meta/1",
        "producer": "imgwtools",
        "producer_version": __version__,
        "dataset": "cz.chmi.hydro_daily",
        "country": "CZ",
        "provider": "CHMI",
        "request": {
            "server_path": HYDRO.server_path,
            "year": 2025,
            "month": None,
            "station_code": CODE,
            "param": None,
        },
        "license": {
            "id": "CC-BY-4.0",
            "attribution": chmi.license.attribution,
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "terms_url": chmi.license.terms_url,
        },
        "downloaded_at": meta["downloaded_at"],
        "sha256": hashlib.sha256(FIRST).hexdigest(),
        "size_bytes": len(FIRST),
        "content_sha256": content_sha256(FIRST, form=FORM),
        "content_form": FORM,
        "extra": {
            "version": {"label": "2026-05-21", "label_source": "last_modified"},
            "period": {
                "year": 2025,
                "month": None,
                "param": None,
                "year_type": "calendar",
                "start": "2025-01-01",
                "end": "2025-12-31",
                "station_code": CODE,
            },
            "http": {
                "url": HYDRO.url,
                "etag": etag,
                "last_modified": "Thu, 21 May 2026 11:19:03 GMT",
                "content_length": len(FIRST),
            },
        },
    }
    assert [(n.level, n.code, n.text) for n in notices] == [
        ("info", "license_terms", f"{chmi.license.attribution}. {chmi.notice}")
    ]
    read = read_meta(written.path)
    assert (read.provider, read.country, read.license.terms_url) == (
        "CHMI",
        "CZ",
        chmi.license.terms_url,
    )
    assert (read.content_sha256, read.content_form) == (meta["content_sha256"], FORM)
    entry = current_version(root, slot=SLOT)
    assert entry is not None and entry.version == written.path


def test_chmi_sidecar_with_another_origin_is_invalid(root):
    written = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    path = Path(f"{written.path}.meta.json")
    path.write_text(
        json.dumps({**sidecar(written.path), "country": "PL", "provider": "IMGW-PIB"}),
        encoding="utf-8",
    )
    assert [(e.kind, e.slot, e.problem_code) for e in iter_store(root)] == [
        ("problem", SLOT, "invalid_meta")
    ]


def test_same_canonical_content_records_one_observation_per_signal(root, frozen):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    notices = []
    second = write_archive(
        root,
        archive=HYDRO,
        response=response(HYDRO, RESERIALIZED, REGENERATED),
        on_notice=notices.append,
    )
    observed = hashlib.sha256(RESERIALIZED).hexdigest()
    assert (second.status, second.path, second.sha256, second.label) == (
        "unchanged",
        first.path,
        first.sha256,
        first.label,
    )
    assert second.observed_sha256 == observed
    seen = response(HYDRO, RESERIALIZED, REGENERATED)
    signal = json.dumps(
        {
            "etag": seen.etag,
            "last_modified": seen.last_modified,
            "size_bytes": len(RESERIALIZED),
            "url": HYDRO.url,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    name = f"2026-10-20_{hashlib.sha256(signal.encode()).hexdigest()[:8]}.json"
    assert second.observation == root / SLOT_DIR / "observations" / name
    document = json.loads(second.observation.read_text(encoding="utf-8"))
    assert schema_errors(document, "imgw-observation/1") == []
    assert document == {
        "schema": "imgw-observation/1",
        "producer": "imgwtools",
        "producer_version": __version__,
        "dataset": "cz.chmi.hydro_daily",
        "seen_at": "2026-10-20T09:00:00Z",
        "url": HYDRO.url,
        "last_modified": "Mon, 19 Oct 2026 03:12:44 GMT",
        "etag": seen.etag,
        "size_bytes": len(RESERIALIZED),
        "sha256": observed,
        "content_sha256": content_sha256(FIRST, form=FORM),
        "content_form": FORM,
        "same_content_as": first.path.parent.name,
    }
    assert versions(root) == [first.path.parent.name]
    ((level, code, text),) = [(n.level, n.code, n.text) for n in notices]
    assert (level, code) == ("info", "content_unchanged")
    for part in (
        SLOT,
        first.path.relative_to(root).as_posix(),
        first.sha256,
        observed,
        document["content_sha256"],
        second.observation.relative_to(root).as_posix(),
    ):
        assert part in text
    entries = list(iter_store(root))
    assert sorted((e.kind, e.slot) for e in entries) == [
        ("archive", SLOT),
        ("observation", SLOT),
    ]
    entry = current_version(root, slot=SLOT)
    assert entry is not None and entry.version == first.path

    # The same bytes under the same signal again: the reference observation.
    again = write_archive(
        root, archive=HYDRO, response=response(HYDRO, RESERIALIZED, REGENERATED)
    )
    assert (again.status, again.observation, again.observed_sha256) == (
        "unchanged",
        second.observation,
        observed,
    )
    assert register(root) == [name]
    # A further signal of the same content: a second observation, no version.
    third = write_archive(
        root, archive=HYDRO, response=response(HYDRO, RESERIALIZED, LATER)
    )
    assert third.status == "unchanged"
    assert third.observation is not None and third.observation.name != name
    assert len(register(root)) == 2
    assert versions(root) == [first.path.parent.name]


def test_bytes_under_the_signal_of_the_current_version_write_no_observation(root):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    notices = []
    result = write_archive(
        root,
        archive=HYDRO,
        response=response(HYDRO, SWAPPED, PUBLISHED),
        on_notice=notices.append,
    )
    assert SWAPPED != FIRST and len(SWAPPED) == len(FIRST)
    assert (result.status, result.path, result.observation) == (
        "unchanged",
        first.path,
        None,
    )
    assert result.observed_sha256 == hashlib.sha256(SWAPPED).hexdigest()
    assert [n.code for n in notices] == ["content_unchanged"]
    assert register(root) == []
    assert versions(root) == [first.path.parent.name]


def test_same_bytes_under_a_new_signal_are_relabeled_with_their_content_fields(root):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    # The copy keeps the fields of the stored bytes unchanged, whatever they are.
    stored = {"content_sha256": "3" * 64, "content_form": "chmi-json/0"}
    Path(f"{first.path}.meta.json").write_text(
        json.dumps({**sidecar(first.path), **stored}), encoding="utf-8"
    )
    relabeled = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, REGENERATED)
    )
    assert (relabeled.status, relabeled.observed_sha256, relabeled.observation) == (
        "relabeled",
        None,
        None,
    )
    assert relabeled.path.read_bytes() == FIRST
    copied = sidecar(relabeled.path)
    assert {key: copied[key] for key in stored} == stored
    assert register(root) == []
    unchanged = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, REGENERATED)
    )
    assert (unchanged.status, unchanged.path) == ("unchanged", relabeled.path)


def test_other_content_than_the_current_version_is_a_new_version(root):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    corrected = write_archive(
        root, archive=HYDRO, response=response(HYDRO, CORRECTED, REGENERATED)
    )
    assert (corrected.status, corrected.observation) == ("created", None)
    assert sidecar(corrected.path)["content_sha256"] == content_sha256(
        CORRECTED, form=FORM
    )
    entry = current_version(root, slot=SLOT)
    assert entry is not None and entry.version == corrected.path
    # The content of an older version is not the current content (§3.1).
    back = write_archive(
        root, archive=HYDRO, response=response(HYDRO, RESERIALIZED, LATER)
    )
    assert back.status == "created"
    assert len(versions(root)) == 3 and first.path.parent.name in versions(root)
    assert register(root) == []


@pytest.mark.parametrize(
    "stored",
    [{}, {"content_sha256": content_sha256(FIRST, form=FORM), "content_form": "x/9"}],
    ids=["without_content_fields", "unknown_form"],
)
def test_current_version_without_comparable_content_gives_a_new_version(root, stored):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    meta = sidecar(first.path)
    del meta["content_sha256"], meta["content_form"]
    Path(f"{first.path}.meta.json").write_text(
        json.dumps({**meta, **stored}), encoding="utf-8"
    )
    result = write_archive(
        root, archive=HYDRO, response=response(HYDRO, RESERIALIZED, REGENERATED)
    )
    assert (result.status, result.observation) == ("created", None)
    assert sidecar(result.path)["content_form"] == FORM
    assert register(root) == []


def test_meteo_csv_has_no_content_fields_and_other_bytes_are_a_version(root):
    station = "0-203-0-90001"
    sra = archive_files("cz.chmi.meteo_daily", stations=[station])[0]
    header = b"STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY,\n"
    rows = f"{station},SRA,06:00,2025-01-01T06:00Z,0.2,,0.0,\n".encode()
    first = write_archive(
        root, archive=sra, response=response(sra, header + rows, PUBLISHED)
    )
    second = write_archive(
        root, archive=sra, response=response(sra, header + rows * 2, REGENERATED)
    )
    assert (first.status, second.status, second.observation) == (
        "created",
        "created",
        None,
    )
    meta = sidecar(second.path)
    assert schema_errors(meta, "imgw-meta/1") == []
    assert "content_sha256" not in meta and "content_form" not in meta
    assert meta["request"] == {
        "server_path": sra.server_path,
        "year": None,
        "month": None,
        "station_code": station,
        "param": "SRA",
    }
    assert meta["extra"]["period"] == {
        "year": None,
        "month": None,
        "param": "SRA",
        "year_type": "none",
        "start": None,
        "end": None,
        "station_code": station,
    }
    slot = f"archive:cz.chmi.meteo_daily:precipitation/dly-{station}-SRA.csv"
    entry = current_version(root, slot=slot)
    assert entry is not None and entry.version == second.path
    assert not (second.path.parent.parent / "observations").exists()


@pytest.mark.parametrize(
    "data",
    [
        b'{"objID":"a","objID":"b"}',
        b'{"objID":NaN}',
        b'{"objID":"\xff"}',
        b"[1,2]",
        b'{"objID":"a"} {}',
    ],
    ids=["repeated_key", "nan", "utf8", "array", "trailing"],
)
def test_bytes_violating_the_form_are_a_data_error_without_traces(root, data):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    (other,) = archive_files("cz.chmi.hydro_daily", stations=[CODE], years=[2024])
    for archive in (HYDRO, other):
        with pytest.raises(IMGWDataError) as error:
            write_archive(
                root, archive=archive, response=response(archive, data, REGENERATED)
            )
        assert error.value.code == "data_error"
        assert archive.server_path in str(error.value)
    assert versions(root) == [first.path.parent.name]
    assert register(root) == []
    assert not (root / SLOT_DIR.replace("2025", "2024")).exists()
    assert leftovers(root) == []


def test_cancel_before_the_observation_is_published_leaves_no_trace(root):
    first = write_archive(
        root, archive=HYDRO, response=response(HYDRO, FIRST, PUBLISHED)
    )
    # Polled before staging (go on), then before the observation (stop).
    answers = iter([False, True])
    with pytest.raises(IMGWCancelledError):
        write_archive(
            root,
            archive=HYDRO,
            response=response(HYDRO, RESERIALIZED, REGENERATED),
            cancel=lambda: next(answers),
        )
    assert register(root) == []
    assert not (root / SLOT_DIR / "observations").exists()
    assert versions(root) == [first.path.parent.name]
    assert leftovers(root) == []


def test_new_envelope_of_a_station_list_is_unchanged_with_an_observation(root):
    hydro_list, _ = station_source_files(provider="CHMI")

    def meta1(record, created, version="1"):
        document = {
            "zaznamID": record,
            "datovyZdrojID": "H",
            "datovyTokID": "Open.Data.Metadata",
            "datumVytvoreni": created,
            "verzeDat": version,
            "data": {
                "type": "DataCollection",
                "data": {
                    "header": "objID,STATION_NAME",
                    "values": [[CODE, "Stanice"]],
                },
            },
        }
        return json.dumps(document, separators=(",", ":")).encode()

    first = write_archive(
        root,
        archive=hydro_list,
        response=response(hydro_list, meta1("a-1", "2026-02-06T10:00Z"), PUBLISHED),
    )
    second = write_archive(
        root,
        archive=hydro_list,
        response=response(hydro_list, meta1("b-2", "2026-10-17T02:03Z"), REGENERATED),
    )
    assert (second.status, second.path) == ("unchanged", first.path)
    assert second.observation is not None and second.observation.exists()
    entry = current_version(root, slot="archive:cz.chmi.hydro_stations:meta1.json")
    assert entry is not None and entry.version == first.path
    third = write_archive(
        root,
        archive=hydro_list,
        response=response(hydro_list, meta1("c-3", "2026-10-18T02:03Z", "2"), LATER),
    )
    assert third.status == "created"


def test_imgw_sidecars_carry_no_chmi_fields(tmp_path):
    root = build_fixture_store(tmp_path / "store").root
    recording = next(
        item
        for item in json.loads(
            (FIXTURES / "recordings.json").read_text(encoding="utf-8")
        )["interactions"]
        if item["case"] == "pmaxtp_pot_first"
    )
    with respx.mock as router:
        router.get(recording["url"]).mock(
            return_value=httpx.Response(200, json=recording["json"])
        )
        sync_pmaxtp(root, method="POT", latitude=52.23, longitude=21.01)
    sidecars = sorted(root.rglob("*.meta.json"))
    assert {path.relative_to(root).parts[0] for path in sidecars} == {
        "archives",
        "series",
        "stations",
        "pmaxtp",
    }
    for path in sidecars:
        meta = json.loads(path.read_text(encoding="utf-8"))
        assert (meta["country"], meta["provider"]) == ("PL", "IMGW-PIB"), path
        assert set(meta["license"]) == {"id", "attribution", "url"}, path
        assert "content_sha256" not in meta and "content_form" not in meta, path
        if path.relative_to(root).parts[0] == "archives":
            assert set(meta["request"]) == {"server_path", "year", "month"}
            assert set(meta["extra"]["period"]) == {
                "year",
                "month",
                "param",
                "year_type",
                "start",
                "end",
            }
