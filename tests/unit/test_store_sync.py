"""Offline scenarios for check_store/sync_store and the imgw-plan/1 document."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from imgwtools.datasets import archive_files
from imgwtools.exceptions import IMGWStoreConflictError, IMGWValidationError
from imgwtools.fetch import DownloadResult
from imgwtools.store import init_store, write_archive
from imgwtools.store import sync as sync_module
from imgwtools.store.sync import check_store, sync_store
from imgwtools.store.types import SeriesReport, StorePlan
from imgwtools.urls import IMGW_PUBLIC_DATA_URL

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDINGS = {
    row["case"]: row
    for row in json.loads((FIXTURES / "recordings.json").read_text())["interactions"]
}
HYDRO = "pl.imgw.hydro_daily"
H2024 = archive_files(HYDRO, years=[2024])[0]
H2023 = archive_files(HYDRO, years=[2023])[0]
H2022_01, H2022_02, H2022_03 = archive_files(HYDRO, years=[2022], months=[1, 2, 3])
H2098 = archive_files(HYDRO, years=[2098])[0]
V1 = RECORDINGS["hydro_head"]["headers"]
V2 = RECORDINGS["changed_after_check"]["headers"]
V3 = RECORDINGS["new_bytes_head"]["headers"]


def data(archive):
    return (FIXTURES / "archives" / archive.server_path).read_bytes()


def listing(mock, directory, *names, status=200):
    body = "".join(f'<a href="{name}">{name}</a>' for name in names)
    return mock.get(f"{IMGW_PUBLIC_DATA_URL}/{directory}/").mock(
        return_value=httpx.Response(status, text=body)
    )


def head(mock, archive, headers, status=200):
    return mock.head(archive.url).mock(
        return_value=httpx.Response(status, headers=headers)
    )


def get(mock, archive, headers, content):
    return mock.get(archive.url).mock(
        return_value=httpx.Response(200, headers=headers, content=content)
    )


def store_local(root, archive, headers, content=None):
    content = data(archive) if content is None else content
    response = DownloadResult(
        content,
        archive.url,
        headers.get("ETag"),
        headers.get("Last-Modified"),
        len(content),
    )
    return write_archive(root, archive=archive, response=response)


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


def test_check_store_reports_all_statuses_with_listing_and_head_only(root, server):
    store_local(root, H2024, V1)
    store_local(root, H2023, {"ETag": '"y2023"'})
    store_local(root, H2022_01, {})
    before = tree(root)
    listing(server, "dane_hydrologiczne/dobowe/2024", "codz_2024.zip")
    listing(server, "dane_hydrologiczne/dobowe/2023", "codz_2023.zip")
    listing(
        server,
        "dane_hydrologiczne/dobowe/2022",
        "codz_2022_01.zip",
        "codz_2022_02.zip",
        "codz_2022_03.zip",
    )
    listing(server, "dane_hydrologiczne/dobowe/2098", status=404)
    head(server, H2024, V2)
    # Same ETag, different size: Content-Length never decides freshness.
    head(server, H2023, {"ETag": '"y2023"', "Content-Length": "999999"})
    head(server, H2022_01, RECORDINGS["no_headers"]["headers"])
    head(
        server,
        H2022_02,
        {"ETag": '"feb"', "Last-Modified": V1["Last-Modified"], "Content-Length": "10"},
    )
    server.head(H2022_03.url).mock(side_effect=httpx.ConnectTimeout("timeout"))
    gets = [
        server.get(archive.url)
        for archive in (H2024, H2023, H2022_01, H2022_02, H2022_03, H2098)
    ]
    notices = []

    plan = check_store(
        root,
        datasets=[HYDRO],
        years=[2022, 2023, 2024, 2098],
        months=[1, 2, 3],
        on_notice=notices.append,
    )

    by_path = {item.archive.server_path: item for item in plan.items}
    assert by_path[H2024.server_path].status == "newer"
    assert by_path[H2024.server_path].remote_etag == V2["ETag"]
    assert by_path[H2023.server_path].status == "current"
    assert by_path[H2023.server_path].content_length == 999999
    assert by_path[H2022_01.server_path].status == "unverifiable"
    assert "no comparable" in by_path[H2022_01.server_path].error
    assert by_path[H2022_02.server_path].status == "missing"
    assert by_path[H2022_02.server_path].local_path is None
    assert by_path[H2098.server_path].status == "unverifiable"
    assert by_path[H2098.server_path].error == "not published"
    assert by_path[H2022_03.server_path].status == "check_failed"
    assert "Timed out" in by_path[H2022_03.server_path].error
    assert (
        by_path[H2024.server_path]
        .local_path.as_posix()
        .startswith("archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/")
    )
    assert plan.series_state == {"hydro_daily": "missing"}
    assert not plan.cancelled
    assert all(not route.called for route in gets)
    assert tree(root) == before
    assert {notice.code for notice in notices} == {
        "source_unverifiable",
        "archive_failed",
    }


def test_plan_json_round_trip_including_cancellation(root, server, tmp_path):
    store_local(root, H2024, V1)
    listing(server, "dane_hydrologiczne/dobowe/2024", "codz_2024.zip")
    listing(server, "dane_hydrologiczne/dobowe/2023", "codz_2023.zip")
    head(server, H2024, V2)
    head(server, H2023, V1)
    calls = iter([False, True])
    plan = check_store(
        root, datasets=[HYDRO], years=[2023, 2024], cancel=lambda: next(calls)
    )
    assert plan.cancelled
    assert [(item.status, item.error) for item in plan.items] == [
        ("missing", None),
        ("unverifiable", "cancelled"),
    ]

    saved = plan.to_json(tmp_path / "plan.json")
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["schema"] == "imgw-plan/1" and payload["cancelled"] is True
    assert StorePlan.from_json(saved) == plan

    target = tmp_path / "full.json"
    full = check_store(root, datasets=["hydro/dobowe"], years="2024", plan=target)
    assert StorePlan.from_json(target) == full
    assert full.series_state == {"hydro_daily": "missing"}
    assert [item.archive.dataset for item in full.items] == [HYDRO]


def test_plan_file_inside_store_is_rejected_before_any_request(root, server, tmp_path):
    for target in (root / "plan.json", root / "archives" / "plan.json", root):
        with pytest.raises(IMGWValidationError) as error:
            check_store(root, datasets=[HYDRO], years=[2024], plan=target)
        assert error.value.details["option"] == "plan"
        assert not target.is_file()
    with pytest.raises(IMGWValidationError):
        check_store(
            root, datasets=[HYDRO], years=[2024], plan=tmp_path / "absent" / "p.json"
        )
    assert not server.calls


def test_changed_header_after_check_is_stale_plan_without_get(root, server, tmp_path):
    listing(server, "dane_hydrologiczne/dobowe/2024", "codz_2024.zip")
    route = head(server, H2024, V1)
    download = get(server, H2024, V1, data(H2024))
    plan_path = check_store(root, datasets=[HYDRO], years=[2024]).to_json(
        tmp_path / "plan.json"
    )
    route.mock(return_value=httpx.Response(200, headers=V2))
    notices = []

    report = sync_store(root, plan=plan_path, series=False, on_notice=notices.append)

    assert [item.status for item in report.items] == ["stale_plan"]
    assert report.items[0].slot == "archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
    assert report.items[0].error_code is None
    assert not download.called
    assert not (root / "archives/versions/dane_hydrologiczne/dobowe/2024").exists()
    assert "stale_plan" in {notice.code for notice in notices}


def test_new_hash_is_new_version_same_hash_new_signal_is_relabeled(root, server):
    listing(server, "dane_hydrologiczne/dobowe/2024", "codz_2024.zip")
    signal = head(server, H2024, V1)
    download = get(server, H2024, V1, data(H2024))

    first = sync_store(root, datasets=[HYDRO], years=[2024], series=False)
    assert [item.status for item in first.items] == ["new"]
    assert first.items[0].version.read_bytes() == data(H2024)

    download.reset()
    again = sync_store(root, datasets=[HYDRO], years=[2024], series=False)
    assert [item.status for item in again.items] == ["unchanged"]
    assert again.items[0].version == first.items[0].version
    assert not download.called

    signal.mock(return_value=httpx.Response(200, headers=V2))
    download.mock(return_value=httpx.Response(200, headers=V2, content=data(H2024)))
    relabeled = sync_store(root, datasets=[HYDRO], years=[2024], series=False)
    assert [item.status for item in relabeled.items] == ["relabeled"]
    assert relabeled.items[0].version != first.items[0].version
    assert relabeled.items[0].version.read_bytes() == data(H2024)

    changed = (FIXTURES / RECORDINGS["new_bytes_get"]["variant"]).read_bytes()
    signal.mock(return_value=httpx.Response(200, headers=V3))
    download.mock(return_value=httpx.Response(200, headers=V3, content=changed))
    created = sync_store(root, datasets=[HYDRO], years=[2024], series=False)
    assert [item.status for item in created.items] == ["new"]
    assert created.items[0].version.read_bytes() == changed
    slot = root / "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024"
    assert len(list(slot.iterdir())) == 3


def test_unverifiable_and_failed_items_are_not_downloaded_from_plan(
    root, server, tmp_path
):
    store_local(root, H2022_01, {})
    listing(server, "dane_hydrologiczne/dobowe/2022", "codz_2022_01.zip")
    listing(server, "dane_hydrologiczne/dobowe/2023", "codz_2023.zip")
    head(server, H2022_01, {})
    head(server, H2023, {"ETag": '"x"'}, status=500)
    downloads = [
        get(server, H2022_01, {}, data(H2022_01)),
        get(server, H2023, {}, data(H2023)),
    ]
    plan = check_store(root, datasets=[HYDRO], years="2022-2023", months="1")
    assert [item.status for item in plan.items] == ["unverifiable", "check_failed"]

    from_plan = sync_store(root, plan=plan, series=False)
    assert [item.status for item in from_plan.items] == ["unchanged", "failed"]
    assert [item.error_code for item in from_plan.items] == [
        None,
        "source_unavailable",
    ]
    assert [item.slot for item in from_plan.items] == [
        "archive:pl.imgw.hydro_daily:2022/codz_2022_01.zip",
        "archive:pl.imgw.hydro_daily:2023/codz_2023.zip",
    ]
    assert not any(route.called for route in downloads)

    notices = []
    explicit = sync_store(
        root,
        datasets=[HYDRO],
        years=[2022, 2023],
        months=[1],
        series=False,
        on_notice=notices.append,
    )
    # Deliberate sync without a plan downloads the unverifiable file and deduplicates by SHA.
    assert [item.status for item in explicit.items] == ["unchanged", "failed"]
    assert downloads[0].called and not downloads[1].called
    assert "source_unverifiable" in {notice.code for notice in notices}


def test_cancel_reports_completed_items_without_partial_version(
    root, server, monkeypatch
):
    built = []
    monkeypatch.setattr(
        sync_module, "build_series", lambda *args, **kwargs: built.append(kwargs)
    )
    for archive in (H2023, H2024):
        listing(
            server,
            f"dane_hydrologiczne/dobowe/{archive.year}",
            f"codz_{archive.year}.zip",
        )
        head(server, archive, V1)
        get(server, archive, V1, data(archive))
    first_slot = root / "archives/versions/dane_hydrologiczne/dobowe/2023/codz_2023"
    second_slot = root / "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024"

    report = sync_store(
        root, datasets=[HYDRO], years=[2023, 2024], cancel=first_slot.exists
    )

    assert report.cancelled
    assert [item.status for item in report.items] == ["new", "cancelled"]
    assert report.items[0].version.is_file()
    assert not second_slot.exists()
    assert [entry.status for entry in report.series] == ["cancelled"]
    assert built == []
    assert list((root / ".incoming").iterdir()) == []


def test_cancel_during_write_leaves_no_version(root, server):
    listing(server, "dane_hydrologiczne/dobowe/2024", "codz_2024.zip")
    head(server, H2024, V1)
    download = get(server, H2024, V1, data(H2024))

    report = sync_store(
        root,
        datasets=[HYDRO],
        years=[2024],
        series=False,
        cancel=lambda: download.called,
    )

    assert report.cancelled and [item.status for item in report.items] == ["cancelled"]
    slot = root / "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024"
    assert not slot.exists() or list(slot.iterdir()) == []
    assert not any((root / ".incoming").glob("*"))


def test_series_is_built_only_from_complete_inputs(root, server, monkeypatch):
    built = []

    def fake_build(store, /, **kwargs):
        built.append((store, kwargs["dataset"]))
        return SeriesReport("new", None, 1, (), ())

    monkeypatch.setattr(sync_module, "build_series", fake_build)
    for archive in (H2023, H2024):
        listing(
            server,
            f"dane_hydrologiczne/dobowe/{archive.year}",
            f"codz_{archive.year}.zip",
        )
        head(server, archive, V1)
    get(server, H2024, V1, data(H2024))
    broken = server.get(H2023.url).mock(return_value=httpx.Response(503))

    partial = sync_store(root, datasets=[HYDRO], years="2023-2024")
    assert [item.status for item in partial.items] == ["failed", "new"]
    assert "503" in partial.items[0].error
    assert [item.error_code for item in partial.items] == ["source_unavailable", None]
    assert built == []
    assert (
        partial.series[0].status == "failed"
        and "codz_2023" in partial.series[0].problems[0]
    )

    broken.mock(return_value=httpx.Response(200, headers=V1, content=data(H2023)))
    complete = sync_store(root, datasets=[HYDRO], years=[2023, 2024])
    assert [item.status for item in complete.items] == ["new", "unchanged"]
    assert built == [(root, HYDRO)]
    assert [entry.status for entry in complete.series] == ["new"]


def test_selector_validation(root, tmp_path):
    plan = StorePlan("imgw-plan/1", root, datetime.now(UTC), (), {})
    with pytest.raises(IMGWValidationError):
        sync_store(root, plan=plan, years=[2024])
    with pytest.raises(IMGWValidationError):
        sync_store(root, datasets=[HYDRO])
    with pytest.raises(IMGWValidationError):
        sync_store(
            root,
            plan=StorePlan("imgw-plan/1", tmp_path / "other", plan.checked_at, (), {}),
        )
    with pytest.raises(IMGWValidationError):
        check_store(root, datasets=["pl.imgw.hydro_stations"], years=[2024])
    (tmp_path / "foreign").mkdir()
    (tmp_path / "foreign" / "notes.txt").write_text("mine")
    # Not a store (foreign files, no layout): the plan lists a conflict, the run refuses it.
    (action,) = check_store(
        tmp_path / "foreign", datasets=[HYDRO], years=[2024]
    ).actions
    assert (action.action, action.reason) == ("conflict", "not_empty")
    with pytest.raises(IMGWStoreConflictError):
        sync_store(tmp_path / "foreign", datasets=[HYDRO], years=[2024])
