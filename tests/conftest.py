"""
Shared pytest fixtures for IMGWTools tests.
"""

import pytest


# Sample PMAXTP API response
@pytest.fixture
def pmaxtp_api_response():
    """Sample response from PMAXTP API."""
    return {
        "data": {
            "ks": {
                "5": {"1": 8.5, "2": 7.2, "5": 5.8, "10": 4.9, "20": 4.0, "50": 2.9},
                "10": {"1": 12.1, "2": 10.3, "5": 8.3, "10": 7.0, "20": 5.7, "50": 4.1},
                "15": {"1": 14.8, "2": 12.6, "5": 10.2, "10": 8.6, "20": 7.0, "50": 5.1},
                "30": {"1": 20.5, "2": 17.5, "5": 14.1, "10": 11.9, "20": 9.7, "50": 7.0},
                "60": {"1": 28.4, "2": 24.2, "5": 19.5, "10": 16.5, "20": 13.4, "50": 9.7},
            },
            "sg": {
                "5": {"1": 9.0, "2": 7.6, "5": 6.1, "10": 5.2, "20": 4.2, "50": 3.1},
                "10": {"1": 12.8, "2": 10.9, "5": 8.8, "10": 7.4, "20": 6.0, "50": 4.4},
                "15": {"1": 15.6, "2": 13.3, "5": 10.8, "10": 9.1, "20": 7.4, "50": 5.4},
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
    return '"149180020","CHAŁUPKI","Odra (1)"\n"150160180","KŁODZKO","Nysa Kłodzka (1)"\n"151140030","PRZEWOŹNIKI","Skroda (1)"'


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
                "id": "149180020",
                "n": "Chałupki",
                "riverName": "Odra",
                "la": 49.9167,
                "lo": 18.3333,
                "s": "alarm",
            },
        ]
    }
