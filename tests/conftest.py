"""
Shared pytest fixtures for IMGWTools tests.
"""

import errno
import os

import pytest

# Imported as ``sitecustomize`` by every subprocess (e.g. the installed ``imgw``) of a
# test whose ``publication`` has no renameat2; ``{links}`` keeps or refuses hard links.
_PORTABLE_SITE = '''\
"""Store publication without renameat2 in a test subprocess (tests/conftest.py)."""

import errno
import os

from imgwtools.store import writer


def _refuse_hard_links(*args, **kwargs):
    raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))


writer._libc_renameat2 = lambda: None
if not {links}:
    os.link = _refuse_hard_links
'''


def refuse_hard_links(*args, **kwargs):
    """``os.link`` on a file system without hard links (e.g. SMB, FAT)."""
    raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))


@pytest.fixture(params=["renameat2", "no_renameat2", "no_renameat2_no_links"])
def publication(request, monkeypatch, tmp_path_factory):
    """Publish store versions in each way of ``store/writer.py:_atomic_publish``.

    ``renameat2``: Linux ``renameat2(RENAME_NOREPLACE)``. ``no_renameat2``: a
    system whose C library or file system lacks it (macOS, NFS), i.e. the portable
    publication with hard links. ``no_renameat2_no_links``: the same on a file system
    without hard links (e.g. SMB, FAT). Without renameat2 the simulation also holds
    in every subprocess of the test (``sitecustomize`` on ``PYTHONPATH``).
    """
    from imgwtools.store import writer

    if request.param == "renameat2":
        if writer._libc_renameat2() is None:
            pytest.skip("biblioteka C nie ma renameat2")
        return request.param
    links = request.param == "no_renameat2"
    monkeypatch.setattr(writer, "_libc_renameat2", lambda: None)
    if not links:
        monkeypatch.setattr(writer.os, "link", refuse_hard_links)
    site = tmp_path_factory.mktemp("site")
    (site / "sitecustomize.py").write_text(
        _PORTABLE_SITE.format(links=links), encoding="utf-8"
    )
    paths = (str(site), os.environ.get("PYTHONPATH", ""))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(path for path in paths if path))
    return request.param


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path_factory, monkeypatch):
    """Point ``settings.data_dir`` at an empty directory for every test.

    Local IMGW-PIB reference data (``python -m imgwtools.reference_data``) must not
    leak into tests; a test that needs such a file writes it into this directory.
    """
    from imgwtools.config import settings

    data_dir = tmp_path_factory.mktemp("data")
    monkeypatch.setattr(settings, "data_dir", data_dir)
    return data_dir


# Sample PMAXTP API response
@pytest.fixture
def pmaxtp_api_response():
    """Sample response from PMAXTP API."""
    return {
        "data": {
            "ks": {
                "5": {"1": 8.5, "2": 7.2, "5": 5.8, "10": 4.9, "20": 4.0, "50": 2.9},
                "10": {"1": 12.1, "2": 10.3, "5": 8.3, "10": 7.0, "20": 5.7, "50": 4.1},
                "15": {
                    "1": 14.8,
                    "2": 12.6,
                    "5": 10.2,
                    "10": 8.6,
                    "20": 7.0,
                    "50": 5.1,
                },
                "30": {
                    "1": 20.5,
                    "2": 17.5,
                    "5": 14.1,
                    "10": 11.9,
                    "20": 9.7,
                    "50": 7.0,
                },
                "60": {
                    "1": 28.4,
                    "2": 24.2,
                    "5": 19.5,
                    "10": 16.5,
                    "20": 13.4,
                    "50": 9.7,
                },
            },
            "sg": {
                "5": {"1": 9.0, "2": 7.6, "5": 6.1, "10": 5.2, "20": 4.2, "50": 3.1},
                "10": {"1": 12.8, "2": 10.9, "5": 8.8, "10": 7.4, "20": 6.0, "50": 4.4},
                "15": {
                    "1": 15.6,
                    "2": 13.3,
                    "5": 10.8,
                    "10": 9.1,
                    "20": 7.4,
                    "50": 5.4,
                },
            },
            "rb": {
                "5": {"1": 0.5, "2": 0.4, "5": 0.3, "10": 0.3, "20": 0.2, "50": 0.2},
                "10": {"1": 0.7, "2": 0.6, "5": 0.5, "10": 0.4, "20": 0.3, "50": 0.3},
                "15": {"1": 0.8, "2": 0.7, "5": 0.6, "10": 0.5, "20": 0.4, "50": 0.3},
            },
        }
    }


# Sample hydro current API response
@pytest.fixture
def hydro_current_api_response():
    """Sample response from IMGW hydro API."""
    return [
        {
            "id_stacji": "150160180",
            "stacja": "Kłodzko",
            "rzeka": "Nysa Kłodzka",
            "województwo": "dolnośląskie",
            "stan_wody": "106",
            "stan_wody_data_pomiaru": "2024-01-15 12:00:00",
            "przeplyw": "5.2",
            "przeplyw_data_pomiaru": "2024-01-15 12:00:00",
            "temperatura_wody": "4.5",
            "temperatura_wody_data_pomiaru": "2024-01-15 06:00:00",
            "zjawisko_lodowe": "0",
            "zjawisko_zarastania": "0",
        },
        {
            "id_stacji": "151140030",
            "stacja": "Przewoźniki",
            "rzeka": "Skroda",
            "województwo": "lubuskie",
            "stan_wody": "230",
            "stan_wody_data_pomiaru": "2024-01-15 12:30:00",
            "przeplyw": None,
            "przeplyw_data_pomiaru": None,
            "temperatura_wody": None,
            "temperatura_wody_data_pomiaru": None,
            "zjawisko_lodowe": "0",
            "zjawisko_zarastania": "0",
        },
    ]


# Sample synop API response
@pytest.fixture
def synop_api_response():
    """Sample response from IMGW synop API."""
    return [
        {
            "id_stacji": "12375",
            "stacja": "Warszawa",
            "data_pomiaru": "2024-01-15",
            "godzina_pomiaru": "12",
            "temperatura": "2.5",
            "predkosc_wiatru": "3",
            "kierunek_wiatru": "180",
            "wilgotnosc_wzgledna": "75.5",
            "suma_opadu": "0.0",
            "cisnienie": "1015.2",
        },
        {
            "id_stacji": "12295",
            "stacja": "Białystok",
            "data_pomiaru": "2024-01-15",
            "godzina_pomiaru": "12",
            "temperatura": "-5.0",
            "predkosc_wiatru": "2",
            "kierunek_wiatru": "90",
            "wilgotnosc_wzgledna": "85.0",
            "suma_opadu": "0.5",
            "cisnienie": "1020.0",
        },
    ]


# Sample hydro stations CSV content
@pytest.fixture
def hydro_stations_csv():
    """Sample CSV content from IMGW hydro stations list."""
    return '"123456789","SAN ESCOBAR","Ławica (1)"\n"150160180","KŁODZKO","Nysa Kłodzka (1)"\n"151140030","PRZEWOŹNIKI","Skroda (1)"'


# Sample map stations API response
@pytest.fixture
def map_stations_api_response():
    """Sample response from hydro-back.imgw.pl map API."""
    return {
        "stations": [
            {
                "id": "150160180",
                "n": "Kłodzko",
                "riverName": "Nysa Kłodzka",
                "la": 50.4333,
                "lo": 16.6500,
                "s": "low",
            },
            {
                "id": "151140030",
                "n": "Przewoźniki",
                "riverName": "Skroda",
                "la": 51.5253,
                "lo": 14.8217,
                "s": "medium",
            },
            {
                "id": "123456789",
                "n": "San Escobar",
                "riverName": "Ławica",
                "la": 49.8765,
                "lo": 18.1234,
                "s": "alarm",
            },
        ]
    }
