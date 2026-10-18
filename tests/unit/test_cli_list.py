"""``imgw list``: station lists from the data dir, datasets and intervals."""

from datetime import datetime

import pytest
from typer.testing import CliRunner

from imgwtools.cli.main import app

RUNNER = CliRunner()


@pytest.fixture
def hydro_csv(isolated_data_dir):
    path = isolated_data_dir / "hydro_stations_names.csv"
    path.write_text(
        "id,name,river\n"
        "149190310,SAN ESCOBAR (GÓRA),Ławica\n"
        "149190320,RABA GÓRNA,Raba\n"
        "149190330,DOLINA,Raba\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def meteo_csv(isolated_data_dir):
    path = isolated_data_dir / "meteo_stations_names.csv"
    path.write_text(
        "id,name\n249190310,SAN ESCOBAR-LOTNISKO\n249190320,ZŁOTA GÓRA\n",
        encoding="utf-8",
    )
    return path


def test_cli_list_stations_hydro_shows_all_rows_with_river(hydro_csv):
    result = RUNNER.invoke(app, ["list", "stations"])

    assert result.exit_code == 0, result.output
    assert "Stacje hydro" in result.output
    assert "Rzeka" in result.output
    row = next(line for line in result.output.splitlines() if "149190310" in line)
    assert "SAN ESCOBAR (GÓRA)" in row
    assert "Ławica" in row
    assert "RABA GÓRNA" in result.output
    assert "DOLINA" in result.output
    assert "Wyswietlono 3 z 50 wynikow" in result.output


def test_cli_list_stations_meteo_has_no_river_column(meteo_csv):
    result = RUNNER.invoke(app, ["list", "stations", "--type", "meteo"])

    assert result.exit_code == 0, result.output
    assert "Stacje meteo" in result.output
    assert "Rzeka" not in result.output
    assert "ZŁOTA GÓRA" in result.output
    assert "Wyswietlono 2 z 50 wynikow" in result.output


def test_cli_list_stations_search_is_case_insensitive(hydro_csv):
    result = RUNNER.invoke(app, ["list", "stations", "--search", "górna"])

    assert result.exit_code == 0, result.output
    assert "RABA GÓRNA" in result.output
    assert "SAN ESCOBAR" not in result.output
    assert "DOLINA" not in result.output
    assert "Wyswietlono 1 z 50 wynikow" in result.output


def test_cli_list_stations_search_treats_term_literally(hydro_csv):
    result = RUNNER.invoke(app, ["list", "stations", "-s", "ESCOBAR (GÓ"])

    assert result.exit_code == 0, result.output
    assert "SAN ESCOBAR (GÓRA)" in result.output
    assert "Wyswietlono 1 z 50 wynikow" in result.output


def test_cli_list_stations_search_without_match_shows_zero(hydro_csv):
    result = RUNNER.invoke(app, ["list", "stations", "-s", "Atlantyda"])

    assert result.exit_code == 0, result.output
    assert "149190" not in result.output
    assert "Wyswietlono 0 z 50 wynikow" in result.output


def test_cli_list_stations_limit_keeps_first_rows(hydro_csv):
    result = RUNNER.invoke(app, ["list", "stations", "--limit", "2"])

    assert result.exit_code == 0, result.output
    assert "149190310" in result.output
    assert "149190320" in result.output
    assert "149190330" not in result.output
    assert "Wyswietlono 2 z 2 wynikow" in result.output


def test_cli_list_stations_header_only_file_shows_zero(isolated_data_dir):
    (isolated_data_dir / "hydro_stations_names.csv").write_text(
        "id,name,river\n", encoding="utf-8"
    )

    result = RUNNER.invoke(app, ["list", "stations"])

    assert result.exit_code == 0, result.output
    assert "Wyswietlono 0 z 50 wynikow" in result.output


def test_cli_list_stations_missing_file_exits_1_with_hint(isolated_data_dir):
    result = RUNNER.invoke(app, ["list", "stations", "-t", "meteo"])

    assert result.exit_code == 1
    message = " ".join(result.output.split())
    assert "meteo_stations_names.csv nie istnieje" in message
    assert "IMGW_DATA_DIR" in message


def test_cli_list_stations_invalid_type_exits_1(hydro_csv):
    result = RUNNER.invoke(app, ["list", "stations", "--type", "klimat"])

    assert result.exit_code == 1
    assert "Nieprawidlowy typ: klimat" in result.output


def test_cli_list_stations_cp1250_file_exits_1_with_read_error(isolated_data_dir):
    (isolated_data_dir / "hydro_stations_names.csv").write_bytes(
        "id,name,river\n149190310,ŁAWICA,Raba Górna\n".encode("cp1250")
    )

    result = RUNNER.invoke(app, ["list", "stations"])

    assert result.exit_code == 1
    assert "Blad odczytu pliku" in result.output


def test_cli_list_datasets_shows_all_types_up_to_current_year():
    result = RUNNER.invoke(app, ["list", "datasets"])

    assert result.exit_code == 0, result.output
    year_range = f"1951-{datetime.now().year}"
    rows = [line for line in result.output.splitlines() if year_range in line]
    assert len(rows) == 6
    assert sum("hydro" in row for row in rows) == 3
    assert sum("meteo" in row for row in rows) == 3
    assert "polroczne_i_roczne" in result.output
    assert "terminowe" in result.output


def test_cli_list_datasets_type_filter_hides_other_type():
    result = RUNNER.invoke(app, ["list", "datasets", "--type", "hydro"])

    assert result.exit_code == 0, result.output
    assert "hydro" in result.output
    assert "meteo" not in result.output
    assert "terminowe" not in result.output


def test_cli_list_intervals_prints_hydro_meteo_and_subtypes():
    result = RUNNER.invoke(app, ["list", "intervals"])

    assert result.exit_code == 0, result.output
    output = result.output
    hydro = output.index("Interwaly danych hydrologicznych")
    meteo = output.index("Interwaly danych meteorologicznych")
    subtypes = output.index("Podtypy danych meteorologicznych")
    assert hydro < meteo < subtypes
    assert "polroczne_i_roczne" in output[hydro:meteo]
    assert "terminowe" in output[meteo:subtypes]
    for subtype in ("klimat", "opad", "synop"):
        assert f"- {subtype}:" in output[subtypes:]
