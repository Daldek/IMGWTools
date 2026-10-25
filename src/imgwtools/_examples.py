"""
Example calls of the command catalog (AGI-2.2): a complete ``imgw`` line and an excerpt of its result.

Every call is the canonical line of `imgwtools.commands.format_command` (AGI-2.1):
`imgwtools.commands.parse_command` reads it into a call that ``format_command``
writes as the same line, and its options pass `imgwtools.commands.validate_command`.
Paths are absolute (``/data/imgw`` is the store of the examples), so the line is
the same in every working directory and under every default store root.

The result is an excerpt of the ``result`` of the ``imgw-result/1`` envelope in
its JSON form: some fields of the result object; for a list command some fields
of the first item of the ``Page`` with its ``total``; for a stream command the
start of the text, or the `imgwtools.output.OutputReport` of a written file.
Store paths are relative to the root, as in every result (``imgwtools._jsonable``).
`imgwtools.commands.command_schema` publishes the examples in ``x-imgw.examples``.
"""

from collections.abc import Mapping
from typing import NamedTuple

__all__ = ["EXAMPLES", "Example"]


class Example(NamedTuple):
    """An example call: the canonical command line and an excerpt of its result."""

    call: str
    result: object


_ROOT = "/data/imgw"
_DAILY_VERSION = (
    "archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/"
    "2026-10-19_b6a19f65/codz_2024.zip"
)
_SERIES_VERSION = "series/versions/hydro_daily/2026-10-19_9a64f921/series.json"
_CELL_VERSION = "pmaxtp/versions/POT/751_317/2026-10-25_3f9c2a71/cell.json"
_PROJECT = "/data/projekt-raba"
_PMAXTP = {"method": "POT", "latitude": 52.23, "longitude": 21.01}
_RABA_ITEM = {
    "kind": "hydro",
    "station_code": "149190310",
    "name": "Raba Górna",
    "river": "Raba",
    "provider": "IMGW-PIB",
}


def _page(item: Mapping[str, object], total: int) -> dict[str, object]:
    """The excerpt of a list result: its first item and the number of all items."""
    return {"items": [item], "total": total}


def _plan(item: Mapping[str, object]) -> dict[str, object]:
    """The excerpt of an ``imgw-plan/1`` plan of the store of the examples."""
    return {"schema": "imgw-plan/1", "root": _ROOT, "items": [item]}


_DAILY_PLAN = _plan(
    {
        "dataset": "pl.imgw.hydro_daily",
        "server_path": "dane_hydrologiczne/dobowe/2024/codz_2024.zip",
        "status": "unchanged",
        "local_path": _DAILY_VERSION,
    }
)
_DAILY_SYNC = {
    "items": [
        {
            "slot": "archive:pl.imgw.hydro_daily:2024/codz_2024.zip",
            "status": "unchanged",
            "version": _DAILY_VERSION,
        }
    ],
    "cancelled": False,
}
_PROJECT_RESULT = {"path": _PROJECT, "store_dir": "../imgw"}
_TASK = {
    "name": "raba-daily",
    "command": "series select",
    "options": {
        "dataset": "pl.imgw.hydro_daily",
        "stations": ["149190310"],
        "years": [2020, 2021, 2022, 2023],
    },
}

EXAMPLES: Mapping[str, tuple[Example, ...]] = {
    "datasets list": (
        Example(
            "imgw datasets list --kind hydro",
            _page(
                {
                    "key": "pl.imgw.hydro_daily",
                    "kind": "hydro",
                    "title": "Daily hydrological data",
                    "variables": {"H": "cm", "Q": "m3/s", "T": "degC"},
                    "first_year": 1951,
                    "provider": "IMGW-PIB",
                },
                7,
            ),
        ),
        Example(
            "imgw datasets list --provider CHMI",
            _page(
                {
                    "key": "cz.chmi.hydro_daily",
                    "kind": "hydro",
                    "year_type": "calendar",
                    "first_year": 1887,
                    "provider": "CHMI",
                },
                4,
            ),
        ),
    ),
    "datasets files": (
        Example(
            "imgw datasets files --dataset pl.imgw.hydro_daily --years 2022,2023",
            _page(
                {
                    "dataset": "pl.imgw.hydro_daily",
                    "server_path": "dane_hydrologiczne/dobowe/2022/codz_2022_01.zip",
                    "year": 2022,
                    "month": 1,
                    "period_start": "2021-11-01",
                    "period_end": "2021-11-30",
                },
                13,
            ),
        ),
        Example(
            "imgw datasets files --dataset cz.chmi.hydro_daily --years 2024 "
            "--stations 0-203-1-900001",
            _page(
                {
                    "dataset": "cz.chmi.hydro_daily",
                    "server_path": "hydrology/historical/data/daily/"
                    "H_0-203-1-900001_DQ_2024.json",
                    "year": 2024,
                    "station_code": "0-203-1-900001",
                },
                1,
            ),
        ),
    ),
    "datasets download": (
        Example(
            "imgw datasets download --dataset pl.imgw.hydro_daily --years 2024 "
            "--root /data/imgw",
            {
                "mode": "store",
                "root": _ROOT,
                "items": [
                    {
                        "slot": "archive:pl.imgw.hydro_daily:2024/codz_2024.zip",
                        "status": "new",
                        "path": _DAILY_VERSION,
                    }
                ],
                "cancelled": False,
            },
        ),
        Example(
            "imgw datasets download --dataset pl.imgw.hydro_daily --years 2024 "
            "--root /data/imgw --check",
            _DAILY_PLAN,
        ),
        Example(
            "imgw datasets download --dataset pl.imgw.meteo_synop_monthly "
            "--years 2023 --output-dir /data/pobrane",
            {
                "mode": "plain",
                "output_dir": "/data/pobrane",
                "files": [
                    {
                        "path": "/data/pobrane/dane_meteorologiczne/miesieczne/synop/"
                        "2023/2023_m_s.zip",
                        "status": "written",
                    }
                ],
            },
        ),
    ),
    "datasets providers": (
        Example(
            "imgw datasets providers",
            _page(
                {
                    "id": "IMGW-PIB",
                    "country": "PL",
                    "key_prefix": "pl.imgw",
                    "license": {"id": "IMGW-PIB"},
                },
                2,
            ),
        ),
    ),
    "stations find": (
        Example("imgw stations find --kind hydro --query raba", _page(_RABA_ITEM, 3)),
        Example(
            "imgw stations find --kind hydro --query spindleruv --provider CHMI",
            _page(
                {
                    "kind": "hydro",
                    "station_code": "0-203-1-001000",
                    "name": "Špindlerův Mlýn",
                    "river": "Labe",
                    "provider": "CHMI",
                },
                1,
            ),
        ),
    ),
    "current hydro": (
        Example(
            "imgw current hydro --station 149190310",
            _page(
                {
                    "station_code": "149190310",
                    "station_name": "Raba Górna",
                    "river": "Raba",
                    "water_level_cm": 162.0,
                    "water_level_date": "2026-10-25 08:00:00",
                },
                1,
            ),
        ),
    ),
    "current meteo": (
        Example(
            "imgw current meteo",
            _page(
                {
                    "station_code": "250180590",
                    "station_name": "Warszawa-Bielany",
                    "air_temp_c": 8.4,
                    "air_temp_date": "2026-10-25 08:00:00",
                },
                612,
            ),
        ),
    ),
    "current synop": (
        Example(
            "imgw current synop --station 12375",
            _page(
                {
                    "station_code": "12375",
                    "station_name": "Warszawa",
                    "measurement_date": "2026-10-25",
                    "measurement_hour": 8,
                    "temperature_c": 8.1,
                    "pressure_hpa": 1016.2,
                },
                1,
            ),
        ),
    ),
    "current warnings": (
        Example(
            "imgw current warnings --kind meteo",
            _page(
                {
                    "kind": "meteo",
                    "event": "Silny wiatr",
                    "level": 1,
                    "valid_from": "2026-10-25T10:00:00Z",
                    "valid_to": "2026-10-25T20:00:00Z",
                },
                3,
            ),
        ),
    ),
    "current hydro-states": (
        Example(
            "imgw current hydro-states --main-only",
            _page(
                {
                    "station_code": "149190310",
                    "name": "Raba Górna",
                    "river": "Raba",
                    "water_state": "normal",
                },
                286,
            ),
        ),
    ),
    "pmaxtp fetch": (
        Example(
            "imgw pmaxtp fetch --latitude 52.23 --longitude 21.01",
            {**_PMAXTP, "data": {"ks": {}, "sg": {}, "rb": {}}},
        ),
    ),
    "pmaxtp url": (
        Example(
            "imgw pmaxtp url --latitude 52.23 --longitude 21.01",
            "https://powietrze.imgw.pl/tpmax-api/point/P/KS/52.2300/21.0100",
        ),
    ),
    "pmaxtp check": (
        Example(
            "imgw pmaxtp check --root /data/imgw --latitude 52.23 --longitude 21.01",
            {
                "schema": "imgw-plan/1",
                "root": _ROOT,
                "actions": [{"command": "pmaxtp sync", "status": "unverifiable"}],
            },
        ),
    ),
    "pmaxtp sync": (
        Example(
            "imgw pmaxtp sync --root /data/imgw --latitude 52.23 --longitude 21.01",
            {
                "status": "new",
                "version": _CELL_VERSION,
                "ind_x": 751,
                "ind_y": 317,
            },
        ),
        Example(
            "imgw pmaxtp sync --root /data/imgw --latitude 52.23 --longitude 21.01 "
            "--check",
            {
                "schema": "imgw-plan/1",
                "root": _ROOT,
                "actions": [{"command": "pmaxtp sync", "status": "unverifiable"}],
            },
        ),
    ),
    "pmaxtp read": (
        Example("imgw pmaxtp read --root /data/imgw --ind-x 751 --ind-y 317", _PMAXTP),
    ),
    "store init": (
        Example(
            "imgw store init --root /data/imgw",
            {"root": _ROOT, "schema": "imgw-store/1"},
        ),
    ),
    "store info": (
        Example(
            "imgw store info --root /data/imgw",
            {
                "root": _ROOT,
                "exists": True,
                "schema": "imgw-store/1",
                "supported": True,
                "problems": [],
            },
        ),
    ),
    "store scan": (
        Example(
            "imgw store scan --root /data/imgw --kind problem",
            _page(
                {
                    "kind": "problem",
                    "version": _DAILY_VERSION,
                    "problem_code": "missing_sidecar",
                },
                1,
            ),
        ),
    ),
    "store check": (
        Example(
            "imgw store check --root /data/imgw --datasets pl.imgw.hydro_daily "
            "--years 2023,2024",
            _DAILY_PLAN,
        ),
        Example(
            "imgw store check --root /data/imgw --datasets pl.imgw.hydro_daily "
            "--years 2023,2024 --plan /data/plan.json",
            _DAILY_PLAN,
        ),
    ),
    "store sync": (
        Example(
            "imgw store sync --root /data/imgw --datasets pl.imgw.hydro_daily "
            "--years 2024",
            _DAILY_SYNC,
        ),
        Example(
            "imgw store sync --root /data/imgw --datasets pl.imgw.hydro_daily "
            "--years 2024 --check",
            _DAILY_PLAN,
        ),
        Example(
            "imgw store sync --root /data/imgw --plan /data/plan.json", _DAILY_SYNC
        ),
    ),
    "store catalog": (
        Example(
            "imgw store catalog --root /data/imgw",
            {
                "status": "new",
                "version": "stations/versions/2026-10-25_da58e6b7/stations.geojson",
                "station_count": 1705,
                "without_location": 37,
            },
        ),
    ),
    "store export": (
        Example(
            f"imgw store export --version /data/imgw/{_DAILY_VERSION} --root /data/imgw "
            "--format jsonl --output /data/codz_2024.jsonl",
            {
                "output": "/data/codz_2024.jsonl",
                "files": [{"path": "/data/codz_2024.jsonl", "status": "written"}],
            },
        ),
    ),
    "series build": (
        Example(
            "imgw series build --root /data/imgw --dataset pl.imgw.hydro_daily",
            {
                "status": "new",
                "version": _SERIES_VERSION,
                "stations": 2,
                "source_files": [_DAILY_VERSION],
            },
        ),
        Example(
            "imgw series build --root /data/imgw --dataset pl.imgw.hydro_daily --check",
            {
                "schema": "imgw-plan/1",
                "root": _ROOT,
                "series_state": {"hydro_daily": "current"},
                "actions": [{"command": "series build", "status": "current"}],
            },
        ),
    ),
    "series select": (
        Example(
            "imgw series select --root /data/imgw --dataset pl.imgw.hydro_daily "
            "--stations 149190310 --variables H,Q --years 2020,2021,2022,2023",
            {
                "dataset": "pl.imgw.hydro_daily",
                "version": _SERIES_VERSION,
                "stations": ["149190310"],
                "variables": ["H", "Q"],
                "years": [2020, 2021, 2022, 2023],
                "year_type": "hydrological",
            },
        ),
    ),
    "series read": (
        Example(
            "imgw series read --root /data/imgw --dataset pl.imgw.hydro_daily "
            "--station 149190310 --start 2024-01-01 --end 2024-01-31 --limit 10",
            _page(
                {
                    "station_code": "149190310",
                    "date": "2024-01-01",
                    "hydro_year": 2024,
                    "measurements": {"H": {"value": 158.0, "flag": "value"}},
                },
                31,
            ),
        ),
    ),
    "series summary": (
        Example(
            "imgw series summary --root /data/imgw --dataset pl.imgw.hydro_daily "
            "--stations 149190310",
            _page(
                {
                    "station_code": "149190310",
                    "variable": "H",
                    "unit": "cm",
                    "first": "2023-12-01",
                    "last": "2024-02-29",
                    "gaps": [["2023-12-02", "2023-12-31"]],
                },
                3,
            ),
        ),
    ),
    "series export": (
        Example(
            "imgw series export --root /data/imgw --dataset pl.imgw.hydro_daily "
            "--station 149190310 --format csv --output /data/raba.csv",
            {
                "output": "/data/raba.csv",
                "files": [{"path": "/data/raba.csv", "status": "written"}],
            },
        ),
    ),
    "project init": (
        Example(
            "imgw project init --project-dir /data/projekt-raba --store-dir ../imgw",
            {**_PROJECT_RESULT, "tasks": []},
        ),
    ),
    "project add": (
        Example(
            "imgw project add --project-dir /data/projekt-raba --name raba-daily "
            "--command 'series select' --options "
            '\'{"dataset":"pl.imgw.hydro_daily","stations":["149190310"],'
            '"years":[2020,2021,2022,2023]}\'',
            {**_PROJECT_RESULT, "tasks": [_TASK]},
        ),
    ),
    "project remove": (
        Example(
            "imgw project remove --project-dir /data/projekt-raba --name raba-daily",
            {**_PROJECT_RESULT, "tasks": []},
        ),
    ),
    "project set-store": (
        Example(
            "imgw project set-store --project-dir /data/projekt-raba "
            "--store-dir /data/imgw",
            {"path": _PROJECT, "store_dir": _ROOT},
        ),
    ),
    "project download": (
        Example(
            "imgw project download --project-dir /data/projekt-raba",
            {"tasks": {"raba-daily": "current"}, "cancelled": False},
        ),
        Example(
            "imgw project download --project-dir /data/projekt-raba --check",
            {
                "schema": "imgw-plan/1",
                "root": _ROOT,
                "actions": [{"command": "project download", "status": "missing"}],
            },
        ),
    ),
    "project check": (
        Example(
            "imgw project check --project-dir /data/projekt-raba --plan /data/plan.json",
            {
                "schema": "imgw-plan/1",
                "root": _ROOT,
                "actions": [{"command": "project download", "status": "missing"}],
            },
        ),
    ),
    "project status": (
        Example(
            "imgw project status --project-dir /data/projekt-raba",
            {"tasks": {"raba-daily": "unpinned"}},
        ),
    ),
    "project verify": (
        Example(
            "imgw project verify --project-dir /data/projekt-raba",
            {"tasks": {"raba-daily": "unpinned"}, "files": []},
        ),
    ),
    "commands list": (
        Example(
            "imgw commands list",
            {
                "schema": "imgw-command-list/1",
                "lang": "en",
                "commands": [
                    {
                        "command": "datasets list",
                        "operation_id": "imgw_datasets_list",
                        "group": "datasets",
                    }
                ],
            },
        ),
    ),
    "commands schema": (
        Example(
            "imgw commands schema --command 'store sync'",
            {"title": "store sync", "x-imgw": {"operation_id": "imgw_store_sync"}},
        ),
    ),
    "commands guide": (
        Example(
            "imgw commands guide",
            "# IMGWTools — guide for agents",
        ),
        Example(
            "imgw commands guide --format llms --output /data/llms.txt",
            {
                "output": "/data/llms.txt",
                "files": [{"path": "/data/llms.txt", "status": "written"}],
            },
        ),
    ),
}
