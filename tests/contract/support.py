"""Shared pieces of the offline contract suite: schemas, recorded IMGW, snapshots.

Fixtures and recordings are read only through the public ``imgwtools.testing``
resources, the way a consumer of the store reads them. The interface helpers
turn the JSON form of command options into ``imgw`` words and REST requests the
way a user of each interface writes them (spec §13.2, §13.10).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

import httpx
import respx

from imgwtools import archive_files, command_schema, current_version
from imgwtools.datasets import ArchiveFile
from imgwtools.messages import Lang
from imgwtools.testing import fixture_files

if TYPE_CHECKING:
    from mcp.types import CallToolResult

DAILY = "pl.imgw.hydro_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
RABA, BEZ_Q = "149190310", "149190311"  # fictional stations of the synthetic fixtures
SOURCE = (
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej"
    " – Państwowy Instytut Badawczy"
)
PROCESSED = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu"
    " Badawczego zostały przetworzone"
)
(H2023,) = archive_files(DAILY, years=[2023])
(H2024,) = archive_files(DAILY, years=[2024])
(O1995,) = archive_files(PRECIP, years=[1995])
(O2001,) = archive_files(PRECIP, years=[2001], months=[1])


def _json(name: str) -> Any:
    return json.loads(fixture_files().joinpath(name).read_text(encoding="utf-8"))


def _recordings() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in (
        "recordings.json",
        "builder_recordings.json",
        "contract_recordings.json",
    ):
        document = _json(name)
        for row in document["interactions"]:
            if "url" not in row:
                row["url"] = f"{document['base_url']}/{row['path']}"
            result[row["case"]] = row
    return result


RECORDINGS = _recordings()
SCHEMAS: dict[str, Any] = _json("contract_schemas.json")
# Recorded answers of every live endpoint (contract_recordings.json, recordings.json).
LIVE = (
    "hydro_current",
    "hydro_current_station",
    "meteo_current",
    "synop_current",
    "warnings_hydro",
    "warnings_meteo",
    "hydro_states",
    "hydro_states_main",
)


def signal(case: str) -> dict[str, str]:
    """ETag and Last-Modified of a recorded answer (Content-Length is per body)."""
    headers = RECORDINGS[case]["headers"]
    return {key: headers[key] for key in ("ETag", "Last-Modified")}


V1, V2, V3 = (
    signal("hydro_head"),
    signal("changed_after_check"),
    signal("new_bytes_head"),
)
# Same bytes as V3 republished under a new signal (relabel step of the scenario).
V4 = {"ETag": '"hydro-v4"', "Last-Modified": "Tue, 20 Oct 2026 12:00:00 GMT"}


def archive_bytes(archive: ArchiveFile) -> bytes:
    return (
        fixture_files()
        .joinpath("archives", *archive.server_path.split("/"))
        .read_bytes()
    )


OLD = archive_bytes(H2024)
NEW = fixture_files().joinpath("variants", "codz_2024_changed.zip").read_bytes()


def sha256(data: bytes | Path) -> str:
    return hashlib.sha256(
        data if isinstance(data, bytes) else data.read_bytes()
    ).hexdigest()


def snapshot(root: Path) -> dict[str, str | None]:
    """Relative POSIX path → SHA-256 of every file (``None`` for directories)."""
    return {
        path.relative_to(root).as_posix(): sha256(path) if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def stamps(root: Path) -> dict[str, int]:
    """Relative POSIX path → mtime of every entry, to prove that nothing was touched."""
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted([root, *root.rglob("*")])
    }


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def mcp_text(result: CallToolResult) -> str:
    """Text of the one text block of a tool result (MCP content is a union)."""
    from mcp.types import TextContent

    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


class FakeImgw:
    """IMGW answering from recordings: listings, HEAD/GET, station lists, live API, PMAXTP.

    Every URL that is not published answers through respx as "not mocked", so a
    request outside the recorded scenario fails the test instead of reaching the
    network.
    """

    def __init__(self, router: respx.Router) -> None:
        self.router = router
        self._listed: dict[str, set[str]] = {}

    def publish(
        self, archive: ArchiveFile, headers: dict[str, str], content: bytes
    ) -> None:
        """Publish ``content`` under ``headers``; the parent listing names the file."""
        directory, name = archive.url.rsplit("/", 1)
        names = self._listed.setdefault(directory, set())
        names.add(name)
        body = "".join(f'<a href="{item}">{item}</a>' for item in sorted(names))
        self.router.get(f"{directory}/").mock(
            return_value=httpx.Response(200, text=body)
        )
        sized = {**headers, "Content-Length": str(len(content))}
        self.router.head(archive.url).mock(
            return_value=httpx.Response(200, headers=sized)
        )
        self.router.get(archive.url).mock(
            return_value=httpx.Response(200, headers=sized, content=content)
        )

    def unpublished(self, *archives: ArchiveFile) -> None:
        """Parent directories of ``archives`` do not exist on the server (404)."""
        for archive in archives:
            directory = archive.url.rsplit("/", 1)[0]
            self.router.get(f"{directory}/").mock(return_value=httpx.Response(404))

    def publish_catalog_sources(self) -> None:
        """Both recorded station lists and the recorded live hydro/meteo answers."""
        for case in ("hydro_stations_get", "meteo_stations_get"):
            row = RECORDINGS[case]
            content = fixture_files().joinpath("archives", *row["archive"].split("/"))
            self.router.head(row["url"]).mock(
                return_value=httpx.Response(200, headers=row["headers"])
            )
            self.router.get(row["url"]).mock(
                return_value=httpx.Response(
                    200, headers=row["headers"], content=content.read_bytes()
                )
            )
        self.answer("hydro_current", "meteo_current")

    def publish_pmaxtp(self, *cases: str) -> None:
        self.answer(*cases)

    def publish_live(self) -> None:
        """Recorded answers of every live endpoint: current data, warnings, map."""
        self.answer(*LIVE)

    def answer(self, *cases: str) -> None:
        """GET of each recorded case answers its status and JSON body."""
        for case in cases:
            row = RECORDINGS[case]
            self.router.get(row["url"]).mock(
                return_value=httpx.Response(row["status"], json=row["json"])
            )

    def traffic(self, start: int = 0) -> list[tuple[str, str]]:
        """Method and URL of every request from call number ``start`` on."""
        return [
            (call.request.method, str(call.request.url))
            for call in self.router.calls[start:]
        ]

    def requests(self, method: str) -> list[str]:
        """URLs requested with ``method`` so far, in order."""
        return [
            str(call.request.url)
            for call in self.router.calls
            if call.request.method == method
        ]

    def downloads(self) -> list[str]:
        """Archive bodies fetched with GET (listings and live API excluded)."""
        return [url for url in self.requests("GET") if url.endswith((".zip", ".csv"))]


# --------------------------------------------------------------------------
# JSON Schema Draft 2020-12: the keyword subset used by the §11 contracts and
# by ``command_schema`` (§13.8: anyOf, oneOf, items, required,
# dependentRequired, additionalProperties, minimum/maximum)
# --------------------------------------------------------------------------

_TYPES = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: (
        isinstance(value, int | float) and not isinstance(value, bool)
    ),
}
_DATE_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})"
)


def _same(left: object, right: object) -> bool:
    """JSON equality: ``true`` is not ``1``."""
    return isinstance(left, bool) == isinstance(right, bool) and left == right


def _format_error(value: str, name: str) -> bool:
    if name == "date":
        try:
            date.fromisoformat(value)
        except ValueError:
            return True
        return len(value) != 10
    if name == "date-time":
        return _DATE_TIME.fullmatch(value) is None
    if name == "uri":
        parts = urlsplit(value)
        return not (parts.scheme and parts.netloc)
    return False


def _matches(
    value: object, schema: dict[str, Any] | bool, root: dict[str, Any], path: str
) -> bool:
    problems: list[str] = []
    _check(value, schema, root, path, problems)
    return not problems


def _check(
    value: object,
    schema: dict[str, Any] | bool,
    root: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if schema is True:
        return
    if schema is False:
        errors.append(f"{path}: schemat false nie dopuszcza wartości {value!r}")
        return
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        _check(value, target, root, path, errors)
    if "type" in schema:
        names = [schema["type"]] if isinstance(schema["type"], str) else schema["type"]
        if not any(_TYPES[name](value) for name in names):
            errors.append(f"{path}: {value!r} nie jest typu {schema['type']}")
            return
    if "const" in schema and not _same(value, schema["const"]):
        errors.append(f"{path}: {value!r} zamiast {schema['const']!r}")
    if "enum" in schema and not any(_same(value, item) for item in schema["enum"]):
        errors.append(f"{path}: {value!r} spoza {schema['enum']!r}")
    if "anyOf" in schema and not any(
        _matches(value, option, root, path) for option in schema["anyOf"]
    ):
        errors.append(f"{path}: {value!r} nie pasuje do żadnego wariantu anyOf")
    if "oneOf" in schema:
        matching = sum(
            _matches(value, option, root, path) for option in schema["oneOf"]
        )
        if matching != 1:
            errors.append(f"{path}: pasuje do {matching} wariantów oneOf zamiast 1")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} nie pasuje do {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: za krótki tekst")
        if "format" in schema and _format_error(value, schema["format"]):
            errors.append(f"{path}: {value!r} nie jest w formacie {schema['format']}")
    if _TYPES["number"](value) and value < schema.get("minimum", value):
        errors.append(f"{path}: {value!r} < {schema['minimum']}")
    if _TYPES["number"](value) and value > schema.get("maximum", value):
        errors.append(f"{path}: {value!r} > {schema['maximum']}")
    if isinstance(value, list):
        prefix = schema.get("prefixItems", [])
        for index, (item, option) in enumerate(zip(value, prefix, strict=False)):
            _check(item, option, root, f"{path}[{index}]", errors)
        if "items" in schema:
            for index in range(len(prefix), len(value)):
                _check(value[index], schema["items"], root, f"{path}[{index}]", errors)
        if (
            not schema.get("minItems", 0)
            <= len(value)
            <= schema.get("maxItems", len(value))
        ):
            errors.append(f"{path}: niedozwolona liczba elementów {len(value)}")
    if isinstance(value, dict):
        errors.extend(
            f"{path}: brak pola {key}"
            for key in schema.get("required", ())
            if key not in value
        )
        errors.extend(
            f"{path}: pole {key} wymaga pola {name}"
            for key, names in schema.get("dependentRequired", {}).items()
            if key in value
            for name in names
            if name not in value
        )
        if len(value) < schema.get("minProperties", 0):
            errors.append(f"{path}: za mało pól")
        properties = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        for key, item in value.items():
            matched = key in properties
            if matched:
                _check(item, properties[key], root, f"{path}.{key}", errors)
            for pattern, option in patterns.items():
                if re.search(pattern, key):
                    matched = True
                    _check(item, option, root, f"{path}.{key}", errors)
            additional = schema.get("additionalProperties", True)
            if not matched and additional is False:
                errors.append(f"{path}: niedozwolone pole {key}")
            elif not matched and isinstance(additional, dict):
                _check(item, additional, root, f"{path}.{key}", errors)


def command_document(
    command: str | None = None, /, *, lang: Lang = "pl"
) -> dict[str, Any]:
    """``command_schema`` as the JSON document it is (its values are ``Any``)."""
    return cast(dict[str, Any], command_schema(command, lang=lang))


def current_path(root: Path, slot: str) -> Path:
    """Main file (or observation file) of the current version of ``slot``."""
    entry = current_version(root, slot=slot)
    assert entry is not None
    assert entry.version is not None
    return entry.version


def schema_errors(document: object, contract: str) -> list[str]:
    """Violations of the JSON Schema ``contract`` (e.g. ``"imgw-meta/1"``)."""
    return violations(document, SCHEMAS["schemas"][contract])


def violations(document: object, schema: dict[str, Any]) -> list[str]:
    """Violations of any JSON Schema of the supported keyword subset."""
    errors: list[str] = []
    _check(document, schema, schema, "$", errors)
    return errors


def envelope_errors(document: Any) -> list[str]:
    """
    Violations of the ``imgw-result/1`` envelope (spec §13.6).

    The result of a list command must be a ``#/$defs/page`` and the result of
    a check (``check=true``) an ``imgw-plan/1`` plan.
    """
    schema = SCHEMAS["schemas"]["imgw-result/1"]
    errors = violations(document, schema)
    if errors or document["result"] is None:
        return errors
    if document["check"]:
        return schema_errors(document["result"], "imgw-plan/1")
    if command_document(document["command"])["x-imgw"]["result"] == "list":
        _check(document["result"], {"$ref": "#/$defs/page"}, schema, "$.result", errors)
    return errors


# --------------------------------------------------------------------------
# Interfaces: options in the JSON form → imgw words and REST requests
# --------------------------------------------------------------------------


def canonical(document: object) -> str:
    """Canonical JSON dump: sorted keys, compact; ``1``, ``1.0`` and ``true`` differ."""
    return json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def cli_words(command: str, options: Mapping[str, object]) -> list[str]:
    """
    ``imgw`` arguments of ``options`` given in their JSON form (spec §13.10).

    Every option takes its canonical flag from the catalog schema; a list is
    comma-separated text and a boolean is ``--x`` or ``--no-x``.
    """
    flags = command_document(command)["x-imgw"]["cli"]["flags"]
    words = command.split()
    for name, value in options.items():
        flag = flags[name][0]
        if isinstance(value, bool):
            words.append(flag if value else f"--no-{flag[2:]}")
        elif isinstance(value, list | tuple):
            words += [flag, ",".join(str(item) for item in value)]
        else:
            words += [flag, str(value)]
    return words


def _query(value: object) -> str | list[str]:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return str(value)


def rest_request(command: str, options: Mapping[str, object]) -> dict[str, Any]:
    """
    Keyword arguments of ``TestClient.request`` for ``options`` (spec §13.10).

    GET options are query parameters (a list repeats its parameter, a boolean
    is ``true``/``false``); POST options form the JSON body.
    """
    rest = command_document(command)["x-imgw"]["rest"]
    if rest["method"] == "POST":
        return {"method": "POST", "url": rest["path"], "json": dict(options)}
    params = {name: _query(value) for name, value in options.items()}
    return {"method": "GET", "url": rest["path"], "params": params}


def slots(value: object) -> Iterator[str]:
    """Every slot named in a JSON document (``null`` slots skipped)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "slot" and isinstance(item, str):
                yield item
            else:
                yield from slots(item)
    elif isinstance(value, list):
        for item in value:
            yield from slots(item)


def unversioned(value: object) -> Iterator[str]:
    """
    Slots of the result objects whose ``version`` is ``null``.

    Such a result names its slot without a version (an unpublished ČHMÚ file,
    a failed item): ``current_version`` rightly finds none (spec §13.7).
    """
    if isinstance(value, dict):
        if isinstance(value.get("slot"), str) and value.get("version", "") is None:
            yield value["slot"]
        for item in value.values():
            yield from unversioned(item)
    elif isinstance(value, list):
        for item in value:
            yield from unversioned(item)


def imgw_executable() -> list[str]:
    """Command line of the installed ``imgw`` script (module run as a fallback)."""
    script = Path(sys.executable).with_name("imgw")
    if script.exists():
        return [str(script)]
    return [sys.executable, "-m", "imgwtools.cli.main"]


def run_imgw(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    """The installed ``imgw`` in a separate process whose proxies lead nowhere."""
    dead = "http://127.0.0.1:9"
    env = {key: value for key, value in os.environ.items() if key != "IMGW_ROOT"}
    env |= {"HTTP_PROXY": dead, "HTTPS_PROXY": dead, "ALL_PROXY": dead, "NO_PROXY": ""}
    result = subprocess.run(
        [*imgw_executable(), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result
