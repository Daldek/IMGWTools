"""Shared pieces of the offline contract suite: §11 schemas, recorded IMGW, snapshots.

Fixtures and recordings are read only through the public ``imgwtools.testing``
resources, the way a consumer of the store reads them.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import respx

from imgwtools import archive_files
from imgwtools.datasets import ArchiveFile
from imgwtools.testing import fixture_files

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
    for name in ("recordings.json", "builder_recordings.json"):
        document = _json(name)
        for row in document["interactions"]:
            row.setdefault("url", f"{document['base_url']}/{row.get('path')}")
            result[row["case"]] = row
    return result


RECORDINGS = _recordings()
SCHEMAS: dict[str, Any] = _json("contract_schemas.json")


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
        for case in ("hydro_current", "meteo_current"):
            row = RECORDINGS[case]
            self.router.get(row["url"]).mock(
                return_value=httpx.Response(200, json=row["json"])
            )

    def publish_pmaxtp(self, *cases: str) -> None:
        for case in cases:
            row = RECORDINGS[case]
            self.router.get(row["url"]).mock(
                return_value=httpx.Response(row["status"], json=row["json"])
            )

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
# JSON Schema Draft 2020-12: the keyword subset used by the §11 contracts
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


def _check(
    value: object, schema: dict, root: dict, path: str, errors: list[str]
) -> None:
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
    if "oneOf" in schema:
        matching = 0
        for option in schema["oneOf"]:
            problems: list[str] = []
            _check(value, option, root, path, problems)
            matching += not problems
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


def schema_errors(document: object, contract: str) -> list[str]:
    """Violations of the §11 JSON Schema ``contract`` (e.g. ``"imgw-meta/1"``)."""
    schema = SCHEMAS["schemas"][contract]
    errors: list[str] = []
    _check(document, schema, schema, "$", errors)
    return errors
