"""``imgw admin``: API key lifecycle against an isolated key file."""

import json
import re

import pytest
from typer.testing import CliRunner

from imgwtools.cli.main import app
from imgwtools.config import settings

RUNNER = CliRunner()

ALPHA_ID = "alphaKEY0000000000000000000000000000000000a"
BETA_ID = "betaKEY00000000000000000000000000000000000b"


@pytest.fixture
def keys_file(tmp_path, monkeypatch):
    path = tmp_path / "secrets" / "api_keys.json"
    monkeypatch.setattr(settings, "api_keys_file", path)
    return path


@pytest.fixture
def seeded_keys(keys_file):
    keys_file.parent.mkdir(parents=True)
    keys_file.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "id": ALPHA_ID,
                        "name": "Raba Górna",
                        "rate_limit": 100,
                        "created_at": "2026-01-02T03:04:05",
                        "active": True,
                        "request_count": 7,
                    },
                    {
                        "id": BETA_ID,
                        "name": "SAN ESCOBAR",
                        "rate_limit": 500,
                        "created_at": "2026-02-03T04:05:06",
                        "active": True,
                        "request_count": 42,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return keys_file


def stored_keys(path):
    return json.loads(path.read_text(encoding="utf-8"))["keys"]


def test_cli_admin_keys_without_key_file_reports_no_keys(keys_file):
    result = RUNNER.invoke(app, ["admin", "keys"])

    assert result.exit_code == 0, result.output
    assert "Brak zarejestrowanych kluczy API" in result.output
    assert not keys_file.exists()


def test_cli_admin_stats_without_key_file_reports_no_keys(keys_file):
    result = RUNNER.invoke(app, ["admin", "stats"])

    assert result.exit_code == 0, result.output
    assert "Brak zarejestrowanych kluczy API" in result.output


def test_cli_admin_create_writes_key_file_and_prints_stored_key(keys_file):
    result = RUNNER.invoke(app, ["admin", "create", "--name", "Raba Górna"])

    assert result.exit_code == 0, result.output
    [key] = stored_keys(keys_file)
    assert key["name"] == "Raba Górna"
    assert key["rate_limit"] == 100
    assert key["active"] is True
    assert key["request_count"] == 0
    assert len(key["id"]) >= 40
    assert f"Klucz: {key['id']}" in result.output
    assert "Limit: 100 zapytań/h" in result.output
    assert "Zapisz ten klucz" in result.output


def test_cli_admin_create_limit_option_is_stored(keys_file):
    result = RUNNER.invoke(app, ["admin", "create", "-n", "SAN ESCOBAR", "-l", "250"])

    assert result.exit_code == 0, result.output
    assert stored_keys(keys_file)[0]["rate_limit"] == 250
    assert "Limit: 250 zapytań/h" in result.output


def test_cli_admin_create_rejects_non_integer_limit(keys_file):
    result = RUNNER.invoke(app, ["admin", "create", "-n", "X", "--limit", "dużo"])

    assert result.exit_code == 2
    assert not keys_file.exists()


def test_cli_admin_create_requires_name(keys_file):
    result = RUNNER.invoke(app, ["admin", "create"])

    assert result.exit_code == 2
    assert not keys_file.exists()


def test_cli_admin_create_appends_to_existing_keys(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "create", "-n", "Trzeci"])

    assert result.exit_code == 0, result.output
    keys = stored_keys(seeded_keys)
    assert [key["name"] for key in keys] == ["Raba Górna", "SAN ESCOBAR", "Trzeci"]
    assert len({key["id"] for key in keys}) == 3


def test_cli_admin_keys_lists_truncated_ids_and_active_flag(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "keys"])

    assert result.exit_code == 0, result.output
    assert f"{ALPHA_ID[:8]}..." in result.output
    assert f"{BETA_ID[:8]}..." in result.output
    assert ALPHA_ID not in result.output
    assert "Raba Górna" in result.output
    assert "2026-01-02T03:04:05" in result.output
    assert result.output.count("Tak") == 2


def test_cli_admin_revoke_by_prefix_deactivates_only_matching_key(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "revoke", "betaKEY"])

    assert result.exit_code == 0, result.output
    assert "Klucz SAN ESCOBAR został unieważniony" in result.output
    alpha, beta = stored_keys(seeded_keys)
    assert alpha["active"] is True
    assert beta["active"] is False

    listing = RUNNER.invoke(app, ["admin", "keys"])
    assert listing.output.count("Tak") == 1
    assert listing.output.count("Nie") == 1


def test_cli_admin_revoke_unknown_key_exits_1_without_changes(seeded_keys):
    before = seeded_keys.read_text(encoding="utf-8")

    result = RUNNER.invoke(app, ["admin", "revoke", "brak"])

    assert result.exit_code == 1
    assert "Nie znaleziono klucza: brak" in result.output
    assert seeded_keys.read_text(encoding="utf-8") == before


def test_cli_admin_revoke_without_key_file_exits_1(keys_file):
    result = RUNNER.invoke(app, ["admin", "revoke", "alpha"])

    assert result.exit_code == 1
    assert "Nie znaleziono klucza: alpha" in result.output
    assert not keys_file.exists()


def test_cli_admin_delete_force_removes_only_matching_key(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "delete", "alpha", "--force"])

    assert result.exit_code == 0, result.output
    assert "Klucz Raba Górna został usunięty" in result.output
    assert [key["id"] for key in stored_keys(seeded_keys)] == [BETA_ID]


def test_cli_admin_delete_confirmed_removes_key(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "delete", "beta"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "Usunąć klucz SAN ESCOBAR?" in result.output
    assert [key["id"] for key in stored_keys(seeded_keys)] == [ALPHA_ID]


def test_cli_admin_delete_declined_aborts_and_keeps_key(seeded_keys):
    before = seeded_keys.read_text(encoding="utf-8")

    result = RUNNER.invoke(app, ["admin", "delete", "beta"], input="n\n")

    assert result.exit_code == 1
    assert "Przerwano." in result.output
    assert seeded_keys.read_text(encoding="utf-8") == before


def test_cli_admin_delete_unknown_key_exits_1_without_prompt(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "delete", "brak"])

    assert result.exit_code == 1
    assert "Nie znaleziono klucza: brak" in result.output
    assert "Usunąć" not in result.output
    assert len(stored_keys(seeded_keys)) == 2


def test_cli_admin_stats_shows_limits_counts_and_status(seeded_keys):
    RUNNER.invoke(app, ["admin", "revoke", "alpha"])

    result = RUNNER.invoke(app, ["admin", "stats"])

    assert result.exit_code == 0, result.output
    alpha_row = next(line for line in result.output.splitlines() if "Raba" in line)
    beta_row = next(line for line in result.output.splitlines() if "SAN" in line)
    assert re.search(r"100\D+7\D+Nieaktywny", alpha_row)
    assert re.search(r"500\D+42\D+Aktywny", beta_row)


def test_cli_admin_stats_prefix_filters_to_matching_key(seeded_keys):
    result = RUNNER.invoke(app, ["admin", "stats", "beta"])

    assert result.exit_code == 0, result.output
    assert "SAN ESCOBAR" in result.output
    assert "Raba Górna" not in result.output


def test_cli_admin_stats_fills_defaults_for_legacy_key_entries(keys_file):
    keys_file.parent.mkdir(parents=True)
    keys_file.write_text(
        json.dumps(
            {"keys": [{"id": ALPHA_ID, "name": "Stary", "created_at": "2020-01-01"}]}
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["admin", "stats"])

    assert result.exit_code == 0, result.output
    row = next(line for line in result.output.splitlines() if "Stary" in line)
    assert re.search(r"100\D+0\D+Aktywny", row)


def test_cli_admin_full_lifecycle_with_generated_key(keys_file):
    created = RUNNER.invoke(app, ["admin", "create", "-n", "Cykl", "-l", "5"])
    key_id = stored_keys(keys_file)[0]["id"]
    assert created.exit_code == 0, created.output

    # "--" keeps a generated id that starts with "-" from being parsed as option.
    revoked = RUNNER.invoke(app, ["admin", "revoke", "--", key_id[:10]])
    assert revoked.exit_code == 0, revoked.output
    assert stored_keys(keys_file)[0]["active"] is False

    deleted = RUNNER.invoke(app, ["admin", "delete", "--force", "--", key_id[:10]])
    assert deleted.exit_code == 0, deleted.output
    assert stored_keys(keys_file) == []

    listing = RUNNER.invoke(app, ["admin", "keys"])
    assert "Brak zarejestrowanych kluczy API" in listing.output
