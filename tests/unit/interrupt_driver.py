"""
One real ``imgw`` command in this process, against a source that stops mid-transfer.

Used by ``tests/unit/test_cli_interrupt.py``; it is not a test. Usage::

    python interrupt_driver.py download|export READY RELEASE IMGW_ARGUMENT...

The command is the installed one (``imgwtools.cli.main.app``, its argument
parsing, signal handlers, staging directory and exit codes); only its source
is replaced. ``download`` answers the HTTP requests for the three archives of
``pl.imgw.hydro_semiannual`` 2024 in this process, the second one in two
halves; ``export`` reads the records of the archive version in two halves.
Between the halves the source creates the file READY and waits until the file
RELEASE exists (at most a minute), so that the test knows when to send a
signal and when to let the command go on.
"""

import signal
import sys
import time
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from unittest import mock

import httpx
import respx

from imgwtools.cli.main import app
from imgwtools.datasets import archive_files
from imgwtools.models import NormalizedRecord
from imgwtools.store import export, read_archive

DATASET = "pl.imgw.hydro_semiannual"
# httpx hands over 64 KiB chunks: the first half reaches the staged file before the stop.
HALF = 1 << 17
LIMIT = 60.0


def payload() -> bytes:
    """A ZIP archive of 256 KiB: a plain download checks that a staged file is a ZIP."""
    buffer = BytesIO()
    entry = zipfile.ZipInfo("data.csv", date_time=(2024, 1, 1, 0, 0, 0))
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(entry, b"x" * (1 << 18))
    return buffer.getvalue()


def block(ready: Path, release: Path) -> None:
    """Tell the test that the transfer is half done and wait for its go-ahead."""
    ready.write_text("blocked", encoding="utf-8")
    deadline = time.monotonic() + LIMIT
    while not release.exists():
        if time.monotonic() > deadline:
            raise SystemExit("interrupt_driver: not released within a minute")
        time.sleep(0.02)


class HalfStream(httpx.SyncByteStream):
    """Body that stops after its first half."""

    def __init__(self, content: bytes, ready: Path, release: Path) -> None:
        self.content, self.ready, self.release = content, ready, release

    def __iter__(self) -> Iterator[bytes]:
        yield self.content[:HALF]
        block(self.ready, self.release)
        yield self.content[HALF:]


def run(arguments: list[str]) -> None:
    """Run ``imgw`` with a fresh process's signal handlers, as a shell would start it."""
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    sys.argv = ["imgw", *arguments]
    app()


def download(ready: Path, release: Path, arguments: list[str]) -> None:
    content = payload()
    with respx.mock(assert_all_called=False) as router:
        for index, archive in enumerate(archive_files(DATASET, years=2024)):
            body = (
                httpx.Response(200, stream=HalfStream(content, ready, release))
                if index == 1
                else httpx.Response(200, content=content)
            )
            router.get(archive.url).mock(return_value=body)
        run(arguments)


def export_records(ready: Path, release: Path, arguments: list[str]) -> None:
    def slow(version: Path, /) -> Iterator[NormalizedRecord]:
        yield from read_archive(version)
        block(ready, release)

    with mock.patch.object(export, "read_archive", slow):
        run(arguments)


if __name__ == "__main__":
    scenario, ready, release, *arguments = sys.argv[1:]
    {"download": download, "export": export_records}[scenario](
        Path(ready), Path(release), arguments
    )
