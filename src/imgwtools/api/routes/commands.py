"""
REST routes generated from the command catalog (spec §13.10, ADR-002 D10).

Every catalog command with a REST method gets one route
``/api/v1/<group>/<name>`` (method and path from `command_schema`). GET reads
the options from the query string (a list option as repeated parameters or
comma-separated text), POST from a JSON body checked by a model built with
`pydantic.create_model` (``extra="forbid"``, loose JSON kinds: text, number,
list, object). Values are normalized only by `validate_command`; the answer is
the ``imgw-result/1`` envelope of `run_command` (on POST with ``?check=true``
of `check_command`) with the store root written as ``"."``, or a text stream
for ``store export``, ``series export`` and ``commands guide``.

Server rules: the store root comes only from ``IMGW_STORE_ROOT`` (503
``store_unavailable`` when it is missing, relative or unsupported; ``store
info`` and ``store scan`` answer diagnostically for an unsupported root);
``version`` is a path relative to the root under the ``*/versions/`` directory
of the command; ``user_locations`` is a file name from
``IMGW_USER_LOCATIONS_DIR``; the ``store sync`` plan is an ``imgw-plan/1``
object. Server and local options in a request are refused. Writes (POST
without ``?check=true``) need ``IMGW_STORE_WRITES_ENABLED``, a configured
``IMGW_STORE_WRITE_TOKEN`` and a matching ``X-API-Key`` (constant-time
comparison) and are checked before the root; list commands page by ``limit``
(default and maximum ``IMGW_API_MAX_LIMIT``) and ``offset``. A command with a
``lang`` option takes it from ``Accept-Language`` when the request omits it
(``?lang=`` first, Polish by default; ``Content-Language`` and ``Vary``);
``operationId`` is ``x-imgw.operation_id`` of the catalog.
"""

import hmac
import inspect
import json
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, NoReturn, TypedDict, cast

from fastapi import APIRouter, Body, Depends, Request, Security
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    WithJsonSchema,
    create_model,
)

import imgwtools
from imgwtools._jsonable import jsonable
from imgwtools.api.errors import PROBLEM_RESPONSES, accept_language, hide_server_paths
from imgwtools.commands import (
    check_command,
    command_schema,
    data_commands,
    run_command,
    validate_command,
)
from imgwtools.config import settings
from imgwtools.datasets import ArchiveFile, License, ProviderDescriptor
from imgwtools.exceptions import (
    ErrorCode,
    IMGWDataError,
    IMGWError,
    IMGWStoreError,
    IMGWValidationError,
)
from imgwtools.messages import message
from imgwtools.models import PMaXTPResult
from imgwtools.store import store_info
from imgwtools.store.types import (
    CommandOption,
    CommandResult,
    DataCommand,
    Notice,
    Page,
    PlanAction,
    StorePlan,
)

__all__ = ["PlanDocument", "PlanItemDocument", "catalog_routes", "router"]

router = APIRouter()

_API_KEY = APIKeyHeader(
    name="X-API-Key",
    scheme_name="StoreWriteToken",
    description="Token zapisu magazynu (IMGW_STORE_WRITE_TOKEN serwera)",
    auto_error=False,
)
# Store directory of the versions accepted by the version option of each group.
_VERSION_DIRS = {"store": "archives", "series": "series", "pmaxtp": "pmaxtp"}
# Commands answering diagnostically also for an unsupported store root.
_DIAGNOSTIC = ("store info", "store scan")
_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "jsonl": "application/x-ndjson",
    "agents": "text/markdown; charset=utf-8",
    "llms": "text/markdown; charset=utf-8",
}
# File names of the guide streams of commands guide (spec 2026-10-19 §3.4).
_GUIDE_FILES = {"agents": "AGENTS.md", "llms": "llms.txt"}
# Option given in REST as an imgw-plan/1 object instead of a file (spec §13.2).
_PLAN = "plan"
# Option chosen by Accept-Language when the request omits it (spec 2026-10-19 §4.2).
_LANG = "lang"
# Loose JSON kinds of POST body fields; `validate_command` normalizes values.
_NUMBER = StrictInt | StrictFloat | StrictStr
_LOOSE_TYPES: dict[str, Any] = {
    "str": StrictStr,
    "choice": StrictStr,
    "path": StrictStr,
    "date": StrictStr,
    "int": _NUMBER,
    "float": _NUMBER,
    "bool": StrictBool | StrictStr,
    "list": list[StrictInt | StrictStr] | StrictStr | StrictInt,
    "object": dict[str, Any],
}
# Result dataclasses of imgwtools.store.types annotate these names only for type
# checkers; pydantic resolves them from here when it builds the OpenAPI schemas.
_ANNOTATIONS: dict[str, Any] = {
    "ArchiveFile": ArchiveFile,
    "ErrorCode": ErrorCode,
    "License": License,
    "PMaXTPResult": PMaXTPResult,
    "ProviderDescriptor": ProviderDescriptor,
}


class PlanItemDocument(TypedDict):
    """Archive of an ``imgw-plan/1`` plan (spec §11.5, spec 2026-10-18 §4.2)."""

    dataset: str
    server_path: str
    url: str
    year: int | None
    month: int | None
    param: str | None
    year_type: Literal["hydrological", "calendar", "none"]
    station_code: str | None
    status: Literal["current", "newer", "missing", "unverifiable", "check_failed"]
    signal: Literal["head", "listing"]
    local_path: str | None
    local_sha256: str | None
    local_observation: str | None
    remote_etag: str | None
    remote_last_modified: str | None
    remote_listed_at: str | None
    content_length: int | None
    error: str | None


class PlanDocument(TypedDict):
    """Plan ``imgw-plan/1`` (spec §11.5); ``root`` is ``"."`` in REST answers."""

    schema: Literal["imgw-plan/1"]
    root: str
    checked_at: datetime
    cancelled: bool
    items: list[PlanItemDocument]
    series_state: dict[str, Literal["current", "outdated", "missing"]]
    actions: list[PlanAction]
    requests: dict[str, int] | None


class _Envelope(BaseModel):
    """Envelope ``imgw-result/1`` of a catalog command (spec §13.6)."""

    schema_: Literal["imgw-result/1"] = Field(alias="schema")
    command: str = Field(description="Nazwa komendy katalogu")
    check: bool = Field(description="Czy wynik jest planem imgw-plan/1 (?check=true)")
    status: Literal["ok", "partial", "failed", "cancelled"] = Field(
        description="ok bez porażek, partial/failed przy nieudanych pozycjach raportu"
    )
    notices: list[Notice] = Field(
        description="Różne komunikaty w kolejności wystąpienia (np. license_terms)"
    )


@dataclass(frozen=True)
class _Route:
    """Catalog command served by one REST route."""

    spec: DataCommand
    group: str
    method: Literal["GET", "POST"]
    path: str
    result_type: str
    schema: Mapping[str, Any]

    @property
    def operation_id(self) -> str:
        return cast(str, self.schema["x-imgw"]["operation_id"])

    @property
    def params(self) -> tuple[CommandOption, ...]:
        return tuple(option for option in self.spec.options if option.rest == "param")


def _routes() -> tuple[_Route, ...]:
    specs = {spec.name: spec for spec in data_commands()}
    routes = []
    for schema in cast(list[dict[str, Any]], command_schema()["commands"]):
        meta = schema["x-imgw"]
        if meta["rest"] is not None:
            routes.append(
                _Route(
                    specs[meta["command"]],
                    meta["group"],
                    meta["rest"]["method"],
                    meta["rest"]["path"],
                    meta["result_type"],
                    schema,
                )
            )
    return tuple(routes)


def catalog_routes() -> list[dict[str, str]]:
    """
    List the REST routes of the command catalog.

    Returns
    -------
    list of dict of str to str
        ``command``, ``method`` and ``path`` of every catalog command with a
        REST route, in catalog order.
    """
    return [
        {"command": route.spec.name, "method": route.method, "path": route.path}
        for route in _ROUTES
    ]


# --------------------------------------------------------------------------
# Request options
# --------------------------------------------------------------------------


def _refuse(route: _Route, name: str) -> NoReturn:
    option = next((o for o in route.spec.options if o.name == name), None)
    details: dict[str, object] = {"option": name}
    if option is not None and option.rest == "server":
        detail = message("api.server_sets_option_imgw_store", name=name)
    elif option is not None and option.rest == "local":
        detail = message(
            "api.option_command_available_only_locally",
            name=name,
            name_2=route.spec.name,
        )
    elif route.method == "POST":
        detail = message(
            "api.unknown_query_parameter_options_command",
            name=name,
            name_2=route.spec.name,
        )
        details["allowed"] = ["check"]
    else:
        allowed = [option.name for option in route.params]
        detail = message(
            "api.unknown_parameter_command_available",
            name=name,
            name_2=route.spec.name,
            allowed=", ".join(allowed) or message("common.none"),
        )
        details["allowed"] = allowed
    raise IMGWValidationError(detail, details=details)


def _query_options(route: _Route, request: Request) -> dict[str, object]:
    """Options of a GET route: list options repeat, other options appear once."""
    params = {option.name: option for option in route.params}
    options: dict[str, object] = {}
    for name, value in request.query_params.multi_items():
        option = params.get(name)
        if option is None:
            _refuse(route, name)
        if option.type == "list":
            cast(list[str], options.setdefault(name, [])).append(value)
        elif name in options:
            raise IMGWValidationError(
                message("api.parameter_given_more_than_once", name=name),
                details={"option": name},
            )
        else:
            options[name] = value
    return options


def _check_flag(request: Request) -> bool:
    values = request.query_params.getlist("check")
    if not values:
        return False
    text = values[0].strip().lower()
    if len(values) > 1 or text not in ("true", "false"):
        raise IMGWValidationError(
            message("api.parameter_check_given_once_value", values=", ".join(values)),
            details={
                "option": "check",
                "value": values[0],
                "allowed": ["true", "false"],
            },
        )
    return text == "true"


def _forbidden(detail: str, reason: str) -> IMGWError:
    return IMGWError(detail, code="forbidden", details={"reason": reason})


def _write_access(request: Request, api_key: str | None = Security(_API_KEY)) -> bool:
    """``?check=true`` flag of a POST route; without it the write must be allowed."""
    check = _check_flag(request)
    if check:
        return True
    if not settings.store_writes_enabled:
        raise _forbidden(
            message("api.writing_store_over_rest_disabled"),
            "writes_disabled",
        )
    token = settings.store_write_token
    secret = token.get_secret_value() if token is not None else ""
    if not secret:
        raise _forbidden(
            message("api.writing_store_needs_configured_imgw"),
            "write_token_missing",
        )
    if api_key is None or not hmac.compare_digest(
        api_key.encode("utf-8"), secret.encode("utf-8")
    ):
        raise _forbidden(message("api.missing_invalid_x_api_key"), "invalid_api_key")
    return False


# --------------------------------------------------------------------------
# Server-side values: root, version, user locations, plan
# --------------------------------------------------------------------------


def _unavailable(detail: str, reason: str) -> IMGWStoreError:
    return IMGWStoreError(detail, details={"reason": reason})


def _server_root(route: _Route, options: Mapping[str, object]) -> Path | None:
    """``IMGW_STORE_ROOT`` for a command with a root; 503 when it is unusable."""
    if not any(option.name == "root" for option in route.spec.options):
        return None
    source = options.get("source")
    if route.spec.name == "stations find" and not (
        isinstance(source, str) and source.strip() == "store"
    ):
        return None
    root = settings.store_root
    if root is None:
        raise _unavailable(
            message("api.store_not_configured_set_imgw"),
            "not_configured",
        )
    if not root.is_absolute():
        raise _unavailable(message("api.imgw_store_root_must_absolute"), "root_invalid")
    try:
        info = store_info(root)
    except IMGWError as exc:
        raise _unavailable(
            message("api.invalid_imgw_store_root", detail=exc.detail), "root_invalid"
        ) from exc
    if not info.supported and route.spec.name not in _DIAGNOSTIC:
        raise _unavailable(
            message("api.store_unavailable", problems="; ".join(info.problems)),
            "unsupported",
        )
    return info.root


def _confine_version(route: _Route, root: Path, value: object) -> None:
    """``version`` relative to the root under the command's ``*/versions/``."""
    text = value if isinstance(value, str) else ""
    details = {"option": "version", "value": text}
    parts = text.split("/")
    if (
        "\\" in text
        or "\0" in text
        or PurePosixPath(text).is_absolute()
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise IMGWValidationError(
            message("api.version_must_path_relative_store", text=text),
            details=details,
        )
    kind = _VERSION_DIRS[route.group]
    if len(parts) < 3 or parts[:2] != [kind, "versions"]:
        raise IMGWValidationError(
            message(
                "api.version_command_must_lie_under",
                name=route.spec.name,
                kind=kind,
                text=text,
            ),
            details=details,
        )
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise IMGWValidationError(
                message("api.version_must_not_lead_through", text=text),
                details=details,
            )
        if not path.exists():
            raise IMGWStoreError(
                message("api.no_version_store", text=text),
                code="not_found",
                details=details,
            )


def _user_locations(value: object) -> Path:
    """File named by ``user_locations`` in ``IMGW_USER_LOCATIONS_DIR``."""
    directory = settings.user_locations_dir
    if directory is None or not directory.is_absolute() or not directory.is_dir():
        raise _unavailable(
            message("api.server_does_not_provide_user"),
            "user_locations_dir_invalid",
        )
    name = value if isinstance(value, str) else ""
    details = {"option": "user_locations", "value": name}
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise IMGWValidationError(
            message("api.give_only_name_location_file", name=name),
            details=details,
        )
    path = directory / name
    if path.is_symlink():
        raise IMGWValidationError(
            message("api.location_file_must_not_link", name=name), details=details
        )
    if not path.is_file():
        raise IMGWStoreError(
            message("api.no_location_file", name=name),
            code="not_found",
            details=details,
        )
    return path


def _scratch(root: Path) -> Path:
    """New private temporary directory outside the store."""
    base, store = Path(tempfile.gettempdir()).resolve(), root.resolve()
    if base == store or store in base.parents:
        raise IMGWError(message("api.temporary_directory_server_lies_imgw"))
    return Path(tempfile.mkdtemp(prefix="imgw-rest-"))


@contextmanager
def _plan_file(document: object, root: Path) -> Iterator[Path]:
    """``imgw-plan/1`` object of the request written for this root outside the store."""
    plan = cast(Mapping[str, object], document)
    if plan.get("root") not in (".", str(root)):
        raise IMGWValidationError(
            message("api.plan_concerns_another_store_than"),
            details={"option": "plan", "value": plan.get("root")},
        )
    directory = _scratch(root)
    try:
        path = directory / "plan.json"
        path.write_text(
            json.dumps({**plan, "root": str(root)}, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            StorePlan.from_json(path)
        except IMGWDataError as exc:
            raise IMGWValidationError(
                message("api.invalid_imgw_plan_1_plan", detail=exc.detail),
                details={"option": "plan"},
            ) from exc
        yield path
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------------
# Dispatch and answers
# --------------------------------------------------------------------------


def _paged(options: dict[str, object]) -> None:
    """REST page size: default and maximum ``IMGW_API_MAX_LIMIT``."""
    maximum = settings.api_max_limit
    limit = options.get("limit")
    if limit is None:
        options["limit"] = maximum
    elif cast(int, limit) > maximum:
        raise IMGWValidationError(
            message("api.option_limit_may_most_imgw", maximum=maximum, limit=limit),
            details={"option": "limit", "value": limit, "maximum": maximum},
        )


def _stream_format(route: _Route, options: Mapping[str, object]) -> str:
    """Format of a stream: the given option or its catalog default."""
    default = next(o.default for o in route.spec.options if o.name == "format")
    return cast(str, options.get("format", default))


def _attachment(route: _Route, options: Mapping[str, object]) -> str:
    """File name of an exported stream or of a guide."""
    format_ = _stream_format(route, options)
    if format_ in _GUIDE_FILES:
        return _GUIDE_FILES[format_]
    if route.spec.name == "series export":
        return f"{options['station']}.csv"
    version = cast(Path, options["version"])
    name = version.name.removesuffix(".meta.json")
    stem = version.parent.name if version.is_dir() else PurePosixPath(name).stem
    return f"{stem}.{format_}"


def _stream(
    route: _Route,
    envelope: CommandResult[object],
    options: Mapping[str, object],
    root: Path | None,
) -> StreamingResponse:
    lines = cast(Iterator[str], envelope.result)
    notices = hide_server_paths(jsonable(envelope.notices, root=root, server=True))
    return StreamingResponse(
        (line.encode("utf-8") for line in lines),
        media_type=_MEDIA_TYPES[_stream_format(route, options)],
        headers={
            "Content-Disposition": f'attachment; filename="{_attachment(route, options)}"',
            "X-IMGW-Status": envelope.status,
            "X-IMGW-Notices": json.dumps(
                notices, ensure_ascii=True, separators=(",", ":")
            ),
        },
    )


def _respond(route: _Route, options: dict[str, object], *, check: bool) -> Response:
    root = _server_root(route, options)
    if root is not None:
        options["root"] = root
        if "version" in options:
            _confine_version(route, root, options["version"])
    if "user_locations" in options:
        options["user_locations"] = _user_locations(options["user_locations"])
    with ExitStack() as stack:
        document = options.pop(_PLAN, None)
        if document is not None:
            # Only store sync takes a plan; its root option always yields a root.
            plan = _plan_file(document, cast(Path, root))
            options[_PLAN] = stack.enter_context(plan)
        normalized = validate_command(route.spec.name, options=options)
        if check:
            envelope: CommandResult[Any] = check_command(
                route.spec.name, options=normalized
            )
        else:
            if route.spec.result == "list":
                _paged(normalized)
            envelope = run_command(route.spec.name, options=normalized)
    if envelope.status == "cancelled":
        raise IMGWError(message("api.operation_was_interrupted_without_report"))
    if route.spec.result == "stream" and not check:
        response: Response = _stream(route, envelope, normalized, root)
    else:
        response = JSONResponse(
            hide_server_paths(envelope.to_json(root=root, server=True))
        )
    if _LANG in normalized:
        response.headers["Content-Language"] = cast(str, normalized[_LANG])
    return response


def _negotiated(route: _Route, options: dict[str, object], request: Request) -> bool:
    """Fill an absent ``lang`` option from ``Accept-Language``; True when filled."""
    if _LANG in options or all(option.name != _LANG for option in route.params):
        return False
    options[_LANG] = accept_language(request.headers.get("accept-language"))
    return True


class _Endpoint:
    """
    Endpoint of one catalog route; FastAPI reads the parameters from `__signature__`.

    GET routes take only the request; POST routes also take the generated
    body model and the ``?check=true`` flag resolved by the write guard. A
    command with a ``lang`` option absent from the request answers in the
    language of ``Accept-Language`` (``Vary: Accept-Language``).
    """

    def __init__(self, route: _Route, body: type[BaseModel] | None) -> None:
        self._route = route
        keyword = inspect.Parameter.KEYWORD_ONLY
        parameters = [inspect.Parameter("request", keyword, annotation=Request)]
        if body is not None:
            parameters += [
                # Optional body (no body = no options) documented as the model.
                inspect.Parameter(
                    "body", keyword, annotation=body, default=Body(default=None)
                ),
                inspect.Parameter(
                    "check", keyword, annotation=bool, default=Depends(_write_access)
                ),
            ]
        self.__signature__ = inspect.Signature(parameters)

    def __call__(
        self, *, request: Request, body: BaseModel | None = None, check: bool = False
    ) -> Response:
        route = self._route
        if route.method == "GET":
            options = _query_options(route, request)
        else:
            for name in request.query_params:
                if name != "check":
                    _refuse(route, name)
            options = {} if body is None else body.model_dump(exclude_unset=True)
        negotiated = _negotiated(route, options, request)
        response = _respond(route, options, check=check)
        if negotiated:
            response.headers.add_vary_header("Accept-Language")
        return response


# --------------------------------------------------------------------------
# Route generation and OpenAPI
# --------------------------------------------------------------------------


def _option_schema(route: _Route, option: CommandOption) -> dict[str, Any]:
    """JSON Schema of an option as the REST route accepts it."""
    schema = dict(route.schema["properties"][option.name])
    if option.name == "version":
        kind = _VERSION_DIRS[route.group]
        schema["description"] = (
            f"{schema['description']}. REST: wyłącznie ścieżka względna do magazynu "
            f"serwera pod {kind}/versions/"
        )
    elif option.name == "user_locations":
        schema = {
            "type": "string",
            "minLength": 1,
            "description": "Nazwa pliku CSV station_code,latitude,longitude[,source] "
            "z katalogu IMGW_USER_LOCATIONS_DIR serwera",
        }
    elif option.name == _PLAN:
        schema = {
            "type": "object",
            "description": "Plan imgw-plan/1 (result komendy store check albo "
            '?check=true) z root "." (zamiast datasets, years, months i stations)',
        }
    elif option.name == "limit":
        maximum = settings.api_max_limit
        schema.update(default=maximum, maximum=maximum)
        schema["description"] = (
            f"{schema['description']} (domyślnie i najwyżej IMGW_API_MAX_LIMIT)"
        )
    return schema


def _description(route: _Route) -> str:
    lines = [route.spec.description]
    if route.spec.rules:
        lines += ["", "Reguły:", *(f"- {rule}" for rule in route.spec.rules)]
    if route.method == "POST":
        lines += [
            "",
            "Zapis wymaga IMGW_STORE_WRITES_ENABLED, IMGW_STORE_WRITE_TOKEN i "
            "nagłówka X-API-Key; ?check=true zwraca plan imgw-plan/1 bez zapisu i "
            "bez tokenu.",
        ]
    return "\n".join(lines)


def _pascal(route: _Route) -> str:
    """Name of the OpenAPI component models of a route, from the command name."""
    words = route.spec.name.replace("-", " ").split()
    return "".join(word.capitalize() for word in words)


def _body_field(route: _Route, option: CommandOption) -> tuple[Any, None]:
    """Loose, optional body field documented by the catalog schema of the option."""
    loose = dict[str, Any] if option.name == _PLAN else _LOOSE_TYPES[option.type]
    return Annotated[loose | None, WithJsonSchema(_option_schema(route, option))], None


def _body_model(route: _Route) -> type[BaseModel]:
    names = [option.name for option in route.params]
    schema = route.schema
    extra: dict[str, Any] = {}
    required = [name for name in schema.get("required", ()) if name in names]
    if required:
        extra["required"] = required
    if "oneOf" in schema:
        extra["oneOf"] = [
            {"required": [name for name in group["required"] if name in names]}
            for group in schema["oneOf"]
        ]
    if "dependentRequired" in schema:
        extra["dependentRequired"] = schema["dependentRequired"]
    fields: dict[str, Any] = {
        option.name: _body_field(route, option) for option in route.params
    }
    return create_model(
        f"{_pascal(route)}Body",
        __config__=ConfigDict(extra="forbid", json_schema_extra=extra or None),
        __doc__=f"Ciało JSON komendy {route.spec.name}; serwer wstawia root.",
        **fields,
    )


def _result_type(route: _Route) -> Any:
    """Annotation of the envelope ``result`` (``None`` for a cancelled run)."""
    name = route.result_type
    if name == "StorePlan":
        result: Any = PlanDocument
    elif name == "str":
        result = str
    elif name == "dict":
        result = dict[str, Any]
    else:
        result = getattr(imgwtools, name)
    if route.spec.result == "list":
        result = cast(Any, Page)[result]
    if route.method == "POST":
        result = result | PlanDocument
    return result | None


def _response_model(route: _Route) -> type[BaseModel]:
    model = create_model(
        f"{_pascal(route)}Result",
        __base__=_Envelope,
        __doc__=f"Koperta imgw-result/1 komendy {route.spec.name}",
        result=(
            _result_type(route),
            Field(description=f"Wynik funkcji {route.spec.function}"),
        ),
    )
    model.model_rebuild(_types_namespace=_ANNOTATIONS)
    return model


def _parameters(route: _Route) -> list[dict[str, Any]]:
    required = route.schema.get("required", ())
    parameters = []
    for option in route.params:
        parameter: dict[str, Any] = {
            "name": option.name,
            "in": "query",
            "required": option.name in required,
            "schema": _option_schema(route, option),
        }
        if option.type == "list":
            parameter.update(style="form", explode=True)
        parameters.append(parameter)
    return parameters


def _add_route(route: _Route) -> None:
    responses = dict(PROBLEM_RESPONSES)
    extra: dict[str, Any] = {}
    body = None
    if route.method == "GET":
        extra["parameters"] = _parameters(route)
    else:
        body = _body_model(route)
    if route.spec.result == "stream":
        responses[200] = {
            "description": "Strumień danych (załącznik) z nagłówkami X-IMGW-Status "
            "i X-IMGW-Notices",
            "content": {
                _MEDIA_TYPES[name]: {"schema": {"type": "string"}}
                for name in route.schema["properties"]["format"]["enum"]
            },
        }
    router.add_api_route(
        route.path,
        _Endpoint(route, body),
        methods=[route.method],
        name=route.operation_id,
        operation_id=route.operation_id,
        tags=[route.group],
        summary=route.spec.name,
        description=_description(route),
        response_model=None
        if route.spec.result == "stream"
        else _response_model(route),
        response_class=StreamingResponse
        if route.spec.result == "stream"
        else JSONResponse,
        responses=responses,
        openapi_extra=extra or None,
    )


_ROUTES = _routes()
for _route in _ROUTES:
    _add_route(_route)
