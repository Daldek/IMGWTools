"""The package built from this checkout works without any extra (core dependencies)."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Runs in the fresh venv: the installed wheel, one offline public function.
_SMOKE = """
import importlib
import imgwtools

assert "site-packages" in imgwtools.__file__, imgwtools.__file__
for extra_only in ("typer", "fastapi", "pyarrow", "pandas", "mcp"):
    try:
        importlib.import_module(extra_only)
    except ImportError:
        continue
    raise SystemExit(f"{extra_only} is installed: the venv is not extras-free")
summary = imgwtools.list_commands(lang="en")
assert summary["schema"] == "imgw-command-list/1", summary["schema"]
print("ok")
"""

# A consumer of the library: strict mypy must use the package's own types.
_CONSUMER = """
import imgwtools

summary: dict[str, object] = imgwtools.list_commands(lang="en")
print(summary["schema"])
"""

# Same call with a wrong annotation: the error proves mypy read the types
# (a package without py.typed is Any, and this line would pass).
_CONSUMER_WRONG = """
import imgwtools

summary: int = imgwtools.list_commands(lang="en")
"""


class _Installed(NamedTuple):
    wheel: Path
    python: Path
    work: Path


def _uv(*arguments: str | Path) -> None:
    result = subprocess.run(
        ["uv", *map(str, arguments)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> _Installed:
    """The wheel built from this checkout, installed alone into a fresh venv."""
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")
    work = tmp_path_factory.mktemp("library-install")
    wheels = work / "wheels"
    venv = work / "venv"
    _uv("build", "--offline", "--wheel", "--out-dir", wheels, ROOT)
    (wheel,) = wheels.glob("imgwtools-*.whl")
    _uv("venv", "--offline", "--python", sys.executable, venv)
    python = venv / "bin" / "python"
    if not python.exists():  # Windows layout
        python = venv / "Scripts" / "python.exe"
    _uv("pip", "install", "--offline", "--python", python, wheel)
    return _Installed(wheel, python, work)


@pytest.mark.slow
def test_wheel_imports_and_runs_without_extras(installed: _Installed) -> None:
    """``imgwtools`` without an extra is a working library (every import is a core dependency)."""
    result = subprocess.run(
        [installed.python, "-I", "-c", _SMOKE],
        capture_output=True,
        text=True,
        check=False,
        cwd=installed.work,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def _mypy(installed: _Installed, name: str, source: str) -> tuple[int, str]:
    """Type-check ``source`` against the installed package (no ignore_missing_imports)."""
    consumer = installed.work / name
    consumer.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--python-executable",
            str(installed.python),
            "--cache-dir",
            str(installed.work / ".mypy_cache"),
            "--config-file",
            "",
            str(consumer),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=installed.work,
        timeout=300,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.mark.slow
def test_wheel_ships_py_typed(installed: _Installed) -> None:
    """``Typing :: Typed`` (DEV-7.4) needs the PEP 561 marker inside the wheel."""
    with zipfile.ZipFile(installed.wheel) as archive:
        assert "imgwtools/py.typed" in archive.namelist()


@pytest.mark.slow
def test_consumer_type_checks_against_the_installed_package(
    installed: _Installed,
) -> None:
    """mypy reads the installed package's types, not ``Any`` and not a missing-stubs error."""
    code, output = _mypy(installed, "consumer_ok.py", _CONSUMER)
    assert code == 0, output

    code, output = _mypy(installed, "consumer_wrong.py", _CONSUMER_WRONG)
    assert code == 1, output
    assert "Incompatible types in assignment" in output, output
