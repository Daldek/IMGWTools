"""
User environment of IMGWTools: ``nogat.toml``, ``NOGAT_*`` variables, user directories.

Every setting comes from the first of: the command-line option, the environment
variable ``IMGW_<KEY>``, the shared variable ``NOGAT_<KEY>`` (only the shared
keys ``data_dir``, ``cache_dir`` and ``lang``), the section ``[imgw]`` of
``nogat.toml``, the section ``[nogat]`` of it (shared keys only) and the
built-in default (DEV-18.1, ECO-028). The file is ``nogat.toml`` in
``platformdirs.user_config_path("nogat")`` or the path in ``NOGAT_CONFIG``; it
is read with ``tomllib`` and its absence is no error. Credentials come from the
environment only, never from the file (DEV-18.4).

The library core needs neither ``pydantic-settings`` nor the ``nogat`` package:
it reads the reference-data directory through this module, while
`imgwtools.config.Settings` (extras ``api`` and ``cli``) adds ``.env`` files and
the typed settings of the servers on top of the same sources.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import platformdirs

APP = "nogat"
TOOL = "imgw"
PREFIX = "IMGW_"
SHARED_PREFIX = "NOGAT_"
CONFIG_ENV = "NOGAT_CONFIG"
CONFIG_FILENAME = "nogat.toml"
SHARED_KEYS: tuple[str, ...] = ("data_dir", "cache_dir", "lang")
"""Keys of ``[nogat]`` and ``NOGAT_<KEY>``: the same for every tool of the ecosystem."""
CREDENTIAL_KEYS: tuple[str, ...] = ("store_write_token",)
"""Settings that only the environment may give (DEV-18.4)."""


@dataclass(frozen=True)
class ConfigFile:
    """
    The user's ``nogat.toml``, read once.

    Attributes
    ----------
    path : pathlib.Path
        Location of the file.
    source : {"default", "NOGAT_CONFIG"}
        Whether ``path`` is the platform default or comes from ``NOGAT_CONFIG``.
    exists : bool
        Whether the file exists.
    sections : Mapping of str to Mapping of str to object
        The tables ``nogat`` and ``imgw`` (empty when the file is missing or
        unusable); the tables of other tools are not read.
    error : str or None
        Why the file cannot be used (unreadable, invalid TOML, a section that
        is not a table, or a missing file named by ``NOGAT_CONFIG``); None
        when it is usable or simply absent.
    """

    path: Path
    source: str
    exists: bool
    sections: Mapping[str, Mapping[str, Any]]
    error: str | None


@dataclass(frozen=True)
class Found:
    """
    A setting found outside the built-in default.

    Attributes
    ----------
    value : object
        The raw value (text of a variable, TOML value of a file).
    source : {"env", "file"}
        Where it was found.
    name : str
        The variable (``IMGW_DATA_DIR``) or the section (``[imgw]``).
    """

    value: Any
    source: str
    name: str


def default_data_dir() -> Path:
    """Default ``data_dir``: the user data directory of ``nogat`` (DEV-18.2)."""
    return platformdirs.user_data_path(APP)


def default_cache_dir() -> Path:
    """Default ``cache_dir``: the user cache directory of ``nogat`` (DEV-18.2)."""
    return platformdirs.user_cache_path(APP)


def config_file() -> ConfigFile:
    """Read ``nogat.toml`` (the file named by ``NOGAT_CONFIG`` or the default)."""
    explicit = os.environ.get(CONFIG_ENV)
    source = CONFIG_ENV if explicit else "default"
    path = (
        Path(explicit)
        if explicit
        else platformdirs.user_config_path(APP) / CONFIG_FILENAME
    )

    def unusable(error: str | None, *, exists: bool) -> ConfigFile:
        return ConfigFile(path, source, exists, {}, error)

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # A missing default file is the normal case; a named one is a mistake.
        return unusable("the file does not exist" if explicit else None, exists=False)
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) else "not UTF-8 text"
        return unusable(f"cannot read the file: {reason or exc}", exists=True)
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return unusable(f"invalid TOML: {exc}", exists=True)
    sections: dict[str, Mapping[str, Any]] = {}
    for name in (APP, TOOL):
        table = document.get(name, {})
        if not isinstance(table, dict):
            return unusable(f"[{name}] is not a table", exists=True)
        sections[name] = table
    return ConfigFile(path, source, True, sections, None)


def lookup(key: str) -> Found | None:
    """
    Find ``key`` in the environment and in ``nogat.toml``, in the order of DEV-18.1.

    ``.env`` files and command-line options are not consulted here; they belong
    to the layers above (`imgwtools.config.Settings`, the CLI).

    Parameters
    ----------
    key : str
        Setting name (``reference_dir``); the variables are ``IMGW_<KEY>`` and,
        for a shared key, ``NOGAT_<KEY>``.

    Returns
    -------
    Found or None
        The first layer that holds a non-empty value, or None for the default.
    """
    variables = [f"{PREFIX}{key.upper()}"]
    if key in SHARED_KEYS:
        variables.append(f"{SHARED_PREFIX}{key.upper()}")
    for variable in variables:
        if value := os.environ.get(variable):
            return Found(value, "env", variable)
    if key in CREDENTIAL_KEYS:
        return None
    sections = config_file().sections
    if key in sections.get(TOOL, {}):
        return Found(sections[TOOL][key], "file", f"[{TOOL}]")
    if key in SHARED_KEYS and key in sections.get(APP, {}):
        return Found(sections[APP][key], "file", f"[{APP}]")
    return None


def _directory(key: str, default: Path) -> Path:
    found = lookup(key)
    return Path(str(found.value)) if found is not None else default


def cache_dir() -> Path:
    """Directory of ``cache_dir`` as resolved now (``IMGW_CACHE_DIR`` first)."""
    return _directory("cache_dir", default_cache_dir())


def reference_dir() -> Path:
    """
    Directory of the IMGW-PIB reference data as resolved now.

    ``IMGW_REFERENCE_DIR``, ``[imgw] reference_dir``, else
    ``<cache_dir>/imgw/reference`` (the data is fetched again by
    ``python -m imgwtools.reference_data``).
    """
    return _directory("reference_dir", cache_dir() / TOOL / "reference")
