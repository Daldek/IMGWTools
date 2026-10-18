"""CLI downloads never confuse paths or publish partial archives."""

import json

from typer.testing import CliRunner

from imgwtools import commands
from imgwtools import fetch as public_fetch
from imgwtools.cli import fetch
from imgwtools.datasets import ArchiveFile
from imgwtools.fetch import DownloadResult

RUNNER = CliRunner()


def archive(server_path: str, dataset: str = "pl.imgw.hydro_daily") -> ArchiveFile:
    return ArchiveFile(
        dataset,
        server_path,
        f"https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/{server_path}",
        2024,
        None,
        None,
        "hydrological",
        None,
        None,
    )


def test_hydro_public_apis_and_same_basename_in_distinct_server_folders(
    tmp_path, monkeypatch
):
    left = archive("dane_hydrologiczne/dobowe/2024/same.zip")
    right = archive("dane_hydrologiczne/dobowe/2025/same.zip")
    seen = []

    def files(dataset, /, *, years, months=None):
        seen.append((dataset, list(years), months))
        return left, right

    def download(interval, year, month=None, param=None):
        seen.append((interval, year, month, param))
        data = bytes([len(seen)])
        return DownloadResult(data, left.url, None, None, len(data))

    monkeypatch.setattr(commands, "archive_files", files)
    monkeypatch.setattr(public_fetch, "download_hydro_data", download)
    result = RUNNER.invoke(
        fetch.app, ["hydro", "-i", "dobowe", "-y", "2024", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / left.server_path).is_file()
    assert (tmp_path / right.server_path).is_file()
    assert (tmp_path / left.server_path).read_bytes() != (
        tmp_path / right.server_path
    ).read_bytes()
    assert seen[0] == ("pl.imgw.hydro_daily", [2024], None)
    assert len([call for call in seen if call[0] == "dobowe"]) == 2


def test_failed_write_does_not_leave_complete_file_or_block_retry(
    tmp_path, monkeypatch
):
    item = archive("dane_hydrologiczne/dobowe/2024/a.zip")
    monkeypatch.setattr(commands, "archive_files", lambda *args, **kwargs: (item,))
    monkeypatch.setattr(
        public_fetch,
        "download_hydro_data",
        lambda *args: DownloadResult(b"archive", item.url, None, None, 7),
    )
    original = commands.os.replace

    def interrupted(source, destination):
        raise OSError("przerwany zapis")

    monkeypatch.setattr(commands.os, "replace", interrupted)
    failed = RUNNER.invoke(
        fetch.app, ["hydro", "-i", "dobowe", "-y", "2024", "-o", str(tmp_path)]
    )
    assert failed.exit_code == 1
    assert "Niepowodzenia: 1" in failed.stderr
    assert not (tmp_path / item.server_path).exists()
    assert not list(tmp_path.rglob("*.part"))
    monkeypatch.setattr(commands.os, "replace", original)
    passed = RUNNER.invoke(
        fetch.app, ["hydro", "-i", "dobowe", "-y", "2024", "-o", str(tmp_path)]
    )
    assert passed.exit_code == 0, passed.output
    assert (tmp_path / item.server_path).read_bytes() == b"archive"
    assert "już istnieje" not in passed.output


def test_meteo_daily_public_enumerator_and_legacy_monthly(tmp_path, monkeypatch):
    daily = archive(
        "dane_meteorologiczne/dobowe/klimat/2024/2024_01_k.zip",
        "pl.imgw.meteo_climate_daily",
    )
    seen = []

    def files(dataset, /, *, years, months=None):
        seen.append((dataset, tuple(years), months))
        return (daily,)

    monkeypatch.setattr(commands, "archive_files", files)
    monkeypatch.setattr(
        public_fetch,
        "download_meteo_data",
        lambda *args: DownloadResult(b"one", daily.url, None, None, 3),
    )
    result = RUNNER.invoke(
        fetch.app,
        [
            "meteo",
            "-i",
            "dobowe",
            "-s",
            "klimat",
            "-y",
            "2024",
            "-m",
            "1",
            "-o",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / daily.server_path).read_bytes() == b"one"
    assert set(seen) == {(daily.dataset, (2024,), (1,))}
    legacy_path = "dane_meteorologiczne/miesieczne/synop/2024/2024_m_s.zip"
    base = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
    monkeypatch.setattr(
        public_fetch,
        "download_meteo_data",
        lambda *args: DownloadResult(b"two", base + legacy_path, None, None, 3),
    )
    monthly = RUNNER.invoke(fetch.app, ["meteo", "-y", "2024", "-o", str(tmp_path)])
    assert monthly.exit_code == 0, monthly.output
    assert (tmp_path / legacy_path).read_bytes() == b"two"


def test_check_prints_only_the_plan_json_on_stdout(tmp_path, monkeypatch):
    item = archive("dane_hydrologiczne/miesieczne/2023/mies_2023.zip")
    monkeypatch.setattr(commands, "archive_files", lambda *args, **kwargs: (item,))

    def refuse(*args):
        raise AssertionError("--check nie pobiera danych")

    monkeypatch.setattr(public_fetch, "download_hydro_data", refuse)
    result = RUNNER.invoke(
        fetch.app,
        ["hydro", "-i", "miesieczne", "-y", "2023", "-o", str(tmp_path), "--check"],
    )
    assert result.exit_code == 0, result.output
    plan = json.loads(result.stdout)
    assert plan["schema"] == "imgw-plan/1"
    assert [action["status"] for action in plan["actions"]] == ["missing"]
    assert "Pobrano" not in result.output


def test_other_fetch_commands_remain_available():
    for command in ("current", "pmaxtp", "warnings"):
        result = RUNNER.invoke(fetch.app, [command, "--help"])
        assert result.exit_code == 0, (command, result.output)
