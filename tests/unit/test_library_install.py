"""The package built from this checkout works without any extra (core dependencies)."""

import shutil
import subprocess
import sys
from pathlib import Path

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


def _uv(*arguments: str | Path) -> None:
    result = subprocess.run(
        ["uv", *map(str, arguments)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_wheel_imports_and_runs_without_extras(tmp_path: Path) -> None:
    """``imgwtools`` without an extra is a working library (every import is a core dependency)."""
    wheels = tmp_path / "wheels"
    venv = tmp_path / "venv"
    _uv("build", "--offline", "--wheel", "--out-dir", wheels, ROOT)
    (wheel,) = wheels.glob("imgwtools-*.whl")
    _uv("venv", "--offline", "--python", sys.executable, venv)
    python = venv / "bin" / "python"
    if not python.exists():  # Windows layout
        python = venv / "Scripts" / "python.exe"
    _uv("pip", "install", "--offline", "--python", python, wheel)

    result = subprocess.run(
        [python, "-I", "-c", _SMOKE],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
