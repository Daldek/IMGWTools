"""
Settings of the servers and the CLI: environment, ``.env`` and ``nogat.toml`` (DEV-18).

A setting comes from the first of: the environment variable ``IMGW_<KEY>``, the
same key in a ``.env`` file of the working directory, the shared variable
``NOGAT_<KEY>`` (keys ``data_dir``, ``cache_dir``, ``lang``), the section
``[imgw]`` of ``nogat.toml``, the section ``[nogat]`` of it (shared keys), the
default; a command-line option goes before all of them. The store write token is
a credential: only the environment (and ``.env``) may give it, never the file
(DEV-18.4). `environment_report` is the document of ``imgw config show --json``
(DEV-18.6); `check_config` rejects an unusable ``nogat.toml``.
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from imgwtools import _environment as environment
from imgwtools._version import __version__
from imgwtools.exceptions import IMGWValidationError
from imgwtools.messages import LANGS, Lang, message

__all__ = [
    "Settings",
    "check_config",
    "default_root",
    "environment_report",
    "human_language",
    "settings",
]


class _NogatEnvSource(PydanticBaseSettingsSource):
    """The shared variables ``NOGAT_DATA_DIR``, ``NOGAT_CACHE_DIR``, ``NOGAT_LANG``."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Not used: `__call__` reads the shared keys at once."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Values of the shared variables that are set (non-empty)."""
        names = {
            key: f"{environment.SHARED_PREFIX}{key.upper()}"
            for key in environment.SHARED_KEYS
        }
        return {
            key: value for key, name in names.items() if (value := os.environ.get(name))
        }


class _FileSource(PydanticBaseSettingsSource):
    """One table of ``nogat.toml``: every setting in ``[imgw]``, shared keys in ``[nogat]``."""

    def __init__(self, settings_cls: type[BaseSettings], section: str) -> None:
        super().__init__(settings_cls)
        self.section = section

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Not used: `__call__` reads the table at once."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Settings of the table; credentials and unknown keys are left out."""
        table = environment.config_file().sections.get(self.section, {})
        known = (
            environment.SHARED_KEYS
            if self.section == environment.APP
            else tuple(self.settings_cls.model_fields)
        )
        return {
            key: value
            for key, value in table.items()
            if key in known and key not in environment.CREDENTIAL_KEYS
        }


def _file_sources(
    settings_cls: type[BaseSettings],
) -> tuple[PydanticBaseSettingsSource, ...]:
    """The sources below ``.env`` in the order of DEV-18.1."""
    return (
        _NogatEnvSource(settings_cls),
        _FileSource(settings_cls, environment.TOOL),
        _FileSource(settings_cls, environment.APP),
    )


class Settings(BaseSettings):
    """Settings loaded from the environment, ``.env`` and ``nogat.toml``."""

    model_config = SettingsConfigDict(
        env_prefix=environment.PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Environment
    env: Literal["development", "production"] = "development"

    # API Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Directories (DEV-18.2): stores live in <data_dir>/imgw, caches in
    # <cache_dir>/imgw. Neither is the working directory. The reference data of
    # IMGW-PIB (hydro_stations_locations.csv, desc/) is fetched again at will,
    # so it lives in the cache, and the state of the REST server (API keys) in
    # the data directory of the tool.
    data_dir: Path = Field(default_factory=environment.default_data_dir)
    cache_dir: Path = Field(default_factory=environment.default_cache_dir)
    reference_dir: Path = Field(
        default_factory=lambda data: data["cache_dir"] / environment.TOOL / "reference"
    )

    # API Keys
    api_keys_file: Path = Field(
        default_factory=lambda data: (
            data["data_dir"] / environment.TOOL / "api_keys.json"
        )
    )

    # Rate limiting (requests per hour, 0 = unlimited)
    rate_limit: int = 100

    # The store root of the REST server (IMGW_ROOT, [imgw] root; DEV-19.2): a
    # server writes only there, never to the default <data_dir>/imgw, and the
    # catalog routes of commands with a store root answer 503 store_unavailable
    # without it. The CLI, the library and the MCP server use `default_root`.
    # Writes (POST without ?check=true) need both flags below and the X-API-Key
    # header; the token is compared in constant time and is a credential:
    # environment only.
    root: Path | None = None
    store_writes_enabled: bool = False
    store_write_token: SecretStr | None = None
    # Server directory with user station-location CSVs offered to the catalog
    # route by file name only; unset disables the option (503).
    user_locations_dir: Path | None = None

    # Default and maximum page size of REST list commands (IMGW_API_MAX_LIMIT).
    api_max_limit: int = Field(default=1000, ge=1)

    # Language of the human-readable output of the CLI (IMGW_LANG): the help and the
    # progress and notice lines; "pl" or "en", checked where it is used (`human_language`),
    # so a wrong value fails every imgw call with validation_error instead of this
    # module's import. Machine output (JSON, the error line) is English whatever it is;
    # REST and MCP ignore it.
    lang: str = "pl"

    # MCP over Streamable HTTP in imgw server (spec 2026-10-19 §6.2, §6.9): the
    # /mcp endpoint exists only with IMGW_MCP_ENABLED=true and the mcp extra;
    # it answers only the Host names of IMGW_MCP_ALLOWED_HOSTS (comma-separated,
    # each with or without a port).
    mcp_enabled: bool = False
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["127.0.0.1", "localhost"]
    # `imgw mcp` starts in the write mode (IMGW_MCP_ALLOW_WRITES; --allow-writes).
    mcp_allow_writes: bool = False

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Order the sources: environment, ``.env``, ``NOGAT_*``, ``nogat.toml``."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            *_file_sources(settings_cls),
            file_secret_settings,
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == "production"

    @field_validator("mcp_allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        """Split the comma-separated text of ``IMGW_MCP_ALLOWED_HOSTS``."""
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value


# Global settings instance
settings = Settings()


def human_language() -> Lang | None:
    """
    Language of the human-readable output of the CLI (``IMGW_LANG``, ``pl`` by default).

    Returns
    -------
    {"pl", "en"} or None
        The language, or None when the setting is neither ``pl`` nor ``en``
        (the CLI then ends every call with ``validation_error``).
    """
    value = settings.lang.strip()
    return value if value in LANGS else None


def _root_of(current: Settings) -> Path:
    """The root of ``current``: the setting, else ``<data_dir>/imgw`` (DEV-19.2)."""
    chosen = (
        current.root
        if current.root is not None
        else current.data_dir / environment.TOOL
    )
    return chosen.expanduser().absolute()


def default_root() -> Path:
    """
    Store root of a command without ``--root`` (DEV-19.2, DEV-18.2).

    The first of ``IMGW_ROOT``, the same key in ``.env``, ``[imgw] root`` of
    ``nogat.toml`` and ``<data_dir>/imgw``, read now so that a later change of
    the environment counts. A server uses ``Settings.root`` only.

    Returns
    -------
    pathlib.Path
        Absolute root; the store need not exist yet.
    """
    return _root_of(Settings())


def check_config() -> None:
    """
    Reject a ``nogat.toml`` that exists but cannot be used.

    Raises
    ------
    IMGWValidationError
        If the file is unreadable, not UTF-8, not valid TOML, has a section that is
        not a table, or ``NOGAT_CONFIG`` names a file that does not exist. The
        message names the cause; ``details.reason`` is ``invalid_config`` (the
        same for every cause), ``details.option`` the variable or the file name
        and ``details.path`` the file.
    """
    file = environment.config_file()
    if file.error is not None:
        raise IMGWValidationError(
            message(
                "config.cannot_use_settings_file", path=file.path, error=file.error
            ),
            details={
                "option": environment.CONFIG_ENV
                if file.source == environment.CONFIG_ENV
                else environment.CONFIG_FILENAME,
                "path": str(file.path),
                "reason": "invalid_config",
            },
        )


def _plain(value: object) -> object:
    """A setting value as JSON (paths as text)."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _layers() -> list[tuple[str, Callable[[str], str], PydanticBaseSettingsSource]]:
    """The sources of `Settings` with the label of their kind and the name of a key in it."""

    def variable(prefix: str) -> Callable[[str], str]:
        return lambda key: f"{prefix}{key.upper()}"

    nogat_env, imgw_file, nogat_file = _file_sources(Settings)
    return [
        ("env", variable(environment.PREFIX), EnvSettingsSource(Settings)),
        ("dotenv", variable(environment.PREFIX), DotEnvSettingsSource(Settings)),
        ("env", variable(environment.SHARED_PREFIX), nogat_env),
        ("file", lambda key: f"[{environment.TOOL}]", imgw_file),
        ("file", lambda key: f"[{environment.APP}]", nogat_file),
    ]


def _origin(
    key: str, layers: list[tuple[str, Callable[[str], str], PydanticBaseSettingsSource]]
) -> dict[str, object]:
    for source, name, layer in layers:
        if key in layer():
            return {"source": source, "name": name(key)}
    return {"source": "default", "name": None}


def _tree_size(root: Path) -> int:
    """Bytes of the files below ``root``; a hard-linked file counts once."""
    total = 0
    seen: set[tuple[int, int]] = set()
    pending = [root]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        info = entry.stat(follow_symlinks=False)
                        if info.st_nlink > 1:
                            identity = (info.st_dev, info.st_ino)
                            if identity in seen:
                                continue
                            seen.add(identity)
                        total += info.st_size
        except OSError:
            continue  # a directory that vanished or cannot be listed
    return total


def environment_report() -> dict[str, object]:
    """
    Report the settings in force and where each comes from (DEV-18.6).

    Returns
    -------
    dict of {str : object}
        Document ``imgw-config/1`` with ``config_file`` (``path``, ``source``,
        ``exists``, ``error``, ``ignored`` keys of ``[imgw]`` that no setting
        uses and credentials found in the file), ``keys`` (every setting but
        the credentials: ``value``, ``source`` ``default``, ``env``, ``dotenv``
        or ``file`` and ``name``, the variable or the table), ``credentials``
        (each credential variable ``present`` or ``missing``; the value is never
        given) and ``store`` (the store root, its source, whether it exists and
        its size in bytes; hard-linked files counted once).
    """
    current = Settings()
    file = environment.config_file()
    layers = _layers()
    keys: dict[str, object] = {}
    credentials: dict[str, str] = {}
    for name in Settings.model_fields:
        value = getattr(current, name)
        if name in environment.CREDENTIAL_KEYS:
            variable = f"{environment.PREFIX}{name.upper()}"
            credentials[variable] = "present" if value is not None else "missing"
            continue
        keys[name] = {"value": _plain(value), **_origin(name, layers)}
    ignored = [
        {
            "key": key,
            "reason": "credential" if key in environment.CREDENTIAL_KEYS else "unknown",
        }
        for key in file.sections.get(environment.TOOL, {})
        if key not in Settings.model_fields or key in environment.CREDENTIAL_KEYS
    ]
    root = _root_of(current)
    return {
        "schema": "imgw-config/1",
        "tool": "imgw",
        "version": __version__,
        "config_file": {
            "path": str(file.path),
            "source": file.source,
            "exists": file.exists,
            "error": file.error,
            "ignored": ignored,
        },
        "keys": keys,
        "credentials": credentials,
        "store": {
            "root": str(root),
            **_origin("root", layers),
            "exists": root.is_dir(),
            "size_bytes": _tree_size(root) if root.is_dir() else None,
        },
    }
