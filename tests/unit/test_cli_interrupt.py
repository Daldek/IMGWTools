"""SIGINT and SIGTERM during a real plain write (DEV-19.7, ADR-007 D3).

A plain write leaves no partial target and no staging directory when the
process is interrupted. These tests start the installed ``imgw`` command in its
own process (``interrupt_driver.py``: the command is real, its source stops in
the middle of a transfer), send the signal and look at the exit code and at what
is left on disk: ``datasets download --output-dir`` after the first file and
``store export --output`` while the file is written; both with ``--force`` over
files that already exist.

The first Ctrl+C asks the command to finish its current step and return what it
has; the second one, like SIGTERM, ends it at once.
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from imgwtools import current_version
from imgwtools.datasets import archive_files
from imgwtools.testing import build_fixture_store
from tests.unit.interrupt_driver import DATASET, payload

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX signals: SIGINT and SIGTERM"
)

DRIVER = Path(__file__).with_name("interrupt_driver.py")
LIMIT = 60.0
OLD = b"old content of the target\n"
ARCHIVE_SLOT = "archive:pl.imgw.hydro_daily:2024/codz_2024.zip"
STOPS_AT_ONCE = "Ctrl+C again stops at once"
EXIT = {"sigterm": 143, "sigint_twice": 130, "sigint_once": 130}


class Command:
    """The driver running ``imgw`` in a process of its own."""

    def __init__(self, tmp_path: Path, scenario: str, *arguments: object) -> None:
        self.ready, self.release = tmp_path / "ready", tmp_path / "release"
        self.stdout, self.stderr = tmp_path / "stdout", tmp_path / "stderr"
        (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
        dead = "http://127.0.0.1:9"
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("IMGW_ROOT", "IMGW_LANG")
        }
        env |= {
            "IMGW_LANG": "en",
            "IMGW_DATA_DIR": str(tmp_path / "data"),
            "NOGAT_CONFIG": str(tmp_path / "nogat.toml"),
            "HTTP_PROXY": dead,
            "HTTPS_PROXY": dead,
            "ALL_PROXY": dead,
            "NO_PROXY": "",
        }
        with self.stdout.open("wb") as out, self.stderr.open("wb") as err:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    str(DRIVER),
                    scenario,
                    str(self.ready),
                    str(self.release),
                    *map(str, arguments),
                ],
                stdout=out,
                stderr=err,
                env=env,
            )

    def errors(self) -> str:
        return self.stderr.read_text(encoding="utf-8")

    def printed(self) -> str:
        return self.stdout.read_text(encoding="utf-8")

    def until(self, done: Callable[[], bool], what: str) -> None:
        """Wait (a minute at most) until ``done()``; fail if the command ends first."""
        deadline = time.monotonic() + LIMIT
        while not done():
            ended = self.process.poll() is not None
            if ended or time.monotonic() > deadline:
                state = "ended before it could" if ended else "did not"
                raise AssertionError(f"imgw {state} {what}\nstderr:\n{self.errors()}")
            time.sleep(0.02)

    def interrupt(self) -> None:
        """First Ctrl+C: wait until the command has taken note of it."""
        self.process.send_signal(signal.SIGINT)
        self.until(
            lambda: STOPS_AT_ONCE in " ".join(self.errors().split()),
            "take note of Ctrl+C",
        )

    def interrupted(self, how: str) -> int:
        """Signal the command once its transfer is half done; its exit status."""
        self.until(self.ready.exists, "stop in the middle of the transfer")
        if how == "sigterm":
            self.process.send_signal(signal.SIGTERM)
        elif how == "sigint_twice":
            self.interrupt()
            self.process.send_signal(signal.SIGINT)
        else:  # sigint_once: the command finishes its step once it is let go
            self.interrupt()
            self.release.write_text("go", encoding="utf-8")
        try:
            return self.process.wait(timeout=LIMIT)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                f"imgw did not end\nstderr:\n{self.errors()}"
            ) from None

    def error_line(self) -> dict[str, object]:
        """The error document of the last line of stderr."""
        document: dict[str, object] = json.loads(self.errors().splitlines()[-1])
        return document


@pytest.fixture
def start(tmp_path):
    """Start the driver; a command still alive when the test ends is killed."""
    started: list[Command] = []

    def run(scenario: str, *arguments: object) -> Command:
        started.append(Command(tmp_path, scenario, *arguments))
        return started[-1]

    yield run
    for command in started:
        if command.process.poll() is None:
            command.process.kill()
        command.process.wait()


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory):
    return build_fixture_store(tmp_path_factory.mktemp("interrupt") / "store").root


@pytest.mark.parametrize("how", list(EXIT))
def test_an_interrupted_plain_download_leaves_no_staging_and_no_partial_target(
    start, tmp_path, how
):
    first, second, third = (
        tmp_path / "out" / archive.server_path
        for archive in archive_files(DATASET, years=2024)
    )
    second.parent.mkdir(parents=True)
    second.write_bytes(OLD)
    command = start(
        "download",
        *("datasets", "download", "--dataset", DATASET, "--years", 2024),
        *("--output-dir", tmp_path / "out", "--force"),
    )

    status = command.interrupted(how)

    complete = payload()
    assert status == EXIT[how], command.errors()
    assert not (tmp_path / "out" / ".imgw-incoming").exists()
    assert first.read_bytes() == complete  # the file before the stop is whole
    assert not third.exists()  # the file after it was never requested
    # the interrupted file is whole: the old one, or (once let go) the new one
    assert second.read_bytes() == (complete if how == "sigint_once" else OLD)
    assert sorted(path.name for path in second.parent.iterdir()) == sorted(
        path.name for path in (first, second)
    )
    if how == "sigint_once":
        document = json.loads(command.printed())
        assert document["status"] == "cancelled"
        assert [item["status"] for item in document["result"]["items"]] == [
            "downloaded",
            "downloaded",
            "cancelled",
        ]
        digest = hashlib.sha256(complete).hexdigest()
        assert [file["sha256"] for file in document["result"]["files"]] == [digest] * 2
    elif how == "sigint_twice":
        assert command.error_line()["code"] == "cancelled"
    assert "Traceback" not in command.errors()


@pytest.mark.parametrize("how", list(EXIT))
def test_an_interrupted_export_leaves_no_staging_and_the_old_file(
    start, tmp_path, fixture_root, how
):
    version = current_version(fixture_root, slot=ARCHIVE_SLOT).version
    target = tmp_path / "out" / "hydro.csv"
    target.parent.mkdir()
    target.write_bytes(OLD)
    command = start(
        "export",
        *("store", "export", "--version", version, "--output", target, "--force"),
    )

    status = command.interrupted(how)

    assert status == EXIT[how], command.errors()
    assert not (target.parent / ".imgw-incoming").exists()
    assert sorted(path.name for path in target.parent.iterdir()) == ["hydro.csv"]
    assert target.read_bytes() == OLD  # even once let go: the Ctrl+C asked to stop
    if how == "sigint_once":  # cancelled on request: the envelope without a result
        document = json.loads(command.printed())
        assert (document["status"], document["result"]) == ("cancelled", None)
    else:
        assert command.printed() == ""
    if how == "sigint_twice":
        assert command.error_line()["code"] == "cancelled"
    assert "Traceback" not in command.errors()
