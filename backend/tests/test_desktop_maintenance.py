from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.desktop_maintenance import main as maintenance_main

SECRET = "synthetic-maintenance-key-material-00000001"
SUCCESS_KEYS = {
    "schema",
    "operation",
    "status",
    "reason",
    "data_identity",
    "source_identity_hash",
    "profile_snapshot_identity",
    "environment_sha256",
    "database_relative_path",
    "database_sha256",
    "sqlite_integrity",
    "foreign_key_violations",
    "schema_version",
    "safe_counts",
    "encrypted_payloads_checked",
    "encrypted_payloads_valid",
}


@pytest.fixture(autouse=True)
def clear_maintenance_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    names = tuple(name for name in os.environ if name.startswith("IZ_CNA_"))
    names += ("LOCAL_SQLITE_DB_PATH", "DATA_ENCRYPTION_KEY", "SECRET_KEY")
    for name in names:
        monkeypatch.delenv(name, raising=False)


def encrypted_payload(secret: str = SECRET) -> bytes:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return b"IZCNA1:" + Fernet(key).encrypt(b'{"fixture":"synthetic"}')


def create_database(path: Path, *, wal: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    if wal:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.executescript(
        "CREATE TABLE schema_migrations(version INTEGER NOT NULL);"
        "INSERT INTO schema_migrations(version) VALUES(12);"
        "CREATE TABLE patients(id INTEGER PRIMARY KEY, synthetic_code TEXT NOT NULL);"
        "INSERT INTO patients(synthetic_code) VALUES('SYNTHETIC-0001');"
        "CREATE TABLE treatment_plan_imports("
        "id INTEGER PRIMARY KEY, encrypted_payload BLOB NOT NULL);"
    )
    connection.execute(
        "INSERT INTO treatment_plan_imports(encrypted_payload) VALUES(?)",
        (encrypted_payload(),),
    )
    connection.commit()
    return connection


def write_environment(root: Path, database_value: str = "profile.sqlite3", secret: str = SECRET) -> Path:
    environment_file = root / ".env"
    environment_file.write_text(
        f"LOCAL_SQLITE_DB_PATH={database_value}\nDATA_ENCRYPTION_KEY={secret}\n",
        encoding="utf-8",
        newline="\n",
    )
    return environment_file


def write_request(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def run_maintenance(operation: str, request: Path, result: Path) -> tuple[int, dict[str, object]]:
    code = maintenance_main((operation, "--request", str(request), "--result", str(result)))
    return code, json.loads(result.read_text(encoding="utf-8"))


def inspection_request(root: Path, environment_file: Path, expected: str = "") -> dict[str, object]:
    return {
        "schema": "iz-cna-data-inspection-request-v1",
        "data_root": str(root),
        "environment_file": str(environment_file),
        "expected_database_path": expected,
    }


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_inspection_is_side_effect_free_and_emits_frozen_fields(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    scratch = tmp_path / "scratch"
    data_root.mkdir()
    scratch.mkdir()
    environment_file = write_environment(data_root)
    create_database(data_root / "profile.sqlite3").close()
    request = scratch / "request.json"
    result = scratch / "result.json"
    write_request(request, inspection_request(data_root, environment_file))
    before = tree_bytes(data_root)

    code, payload = run_maintenance("inspect-data", request, result)

    assert code == 0
    assert set(payload) == SUCCESS_KEYS
    assert payload["schema"] == "iz-cna-data-inspection-v1"
    assert payload["operation"] == "inspect-data"
    assert payload["status"] == "success"
    assert payload["reason"] == "ok"
    assert payload["database_relative_path"] == "profile.sqlite3"
    assert payload["sqlite_integrity"] == "ok"
    assert payload["foreign_key_violations"] == 0
    assert payload["schema_version"] == 12
    counts = payload["safe_counts"]
    assert isinstance(counts, dict)
    assert counts["patients"] == 1
    assert payload["encrypted_payloads_checked"] == 1
    assert payload["encrypted_payloads_valid"] == 1
    assert tree_bytes(data_root) == before
    assert SECRET not in result.read_text(encoding="utf-8")


def test_canonical_database_alias_precedes_generated_alias(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = data_root / ".env"
    environment_file.write_text(
        "LOCAL_SQLITE_DB_PATH=generated.sqlite3\n"
        "IZ_CNA_LOCAL_SQLITE_DB_PATH=canonical.sqlite3\n"
        f"DATA_ENCRYPTION_KEY={SECRET}\n",
        encoding="utf-8",
    )
    create_database(data_root / "canonical.sqlite3").close()
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    write_request(request, inspection_request(data_root, environment_file))

    code, payload = run_maintenance("inspect-data", request, result)

    assert code == 0
    assert payload["database_relative_path"] == "canonical.sqlite3"


def test_process_environment_precedes_file_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root, "file.sqlite3")
    create_database(data_root / "process.sqlite3").close()
    monkeypatch.setenv("IZ_CNA_LOCAL_SQLITE_DB_PATH", "process.sqlite3")
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    write_request(request, inspection_request(data_root, environment_file))

    code, payload = run_maintenance("inspect-data", request, result)

    assert code == 0
    assert payload["database_relative_path"] == "process.sqlite3"


@pytest.mark.parametrize(
    ("environment_value", "expected_reason"),
    [
        ("../outside.sqlite3", "database_outside_data_root"),
        ("missing.sqlite3", "database_missing"),
    ],
)
def test_unsafe_or_missing_database_fails_without_mutation(
    tmp_path: Path,
    environment_value: str,
    expected_reason: str,
) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root, environment_value)
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    write_request(request, inspection_request(data_root, environment_file))
    before = tree_bytes(data_root)

    code, payload = run_maintenance("inspect-data", request, result)

    assert code == 20
    assert payload == {
        "schema": "iz-cna-data-inspection-v1",
        "operation": "inspect-data",
        "status": "failed",
        "reason": expected_reason,
    }
    assert tree_bytes(data_root) == before


def test_wrong_encryption_key_fails_without_exposing_payload(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root, secret="different-synthetic-key-material-0002")
    create_database(data_root / "profile.sqlite3").close()
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    write_request(request, inspection_request(data_root, environment_file))

    code, payload = run_maintenance("inspect-data", request, result)

    assert code == 20
    assert payload["reason"] == "encrypted_payload_invalid"
    result_text = result.read_text(encoding="utf-8")
    assert "SYNTHETIC-0001" not in result_text
    assert "fixture" not in result_text


def test_request_with_unknown_field_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root)
    create_database(data_root / "profile.sqlite3").close()
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    payload = inspection_request(data_root, environment_file)
    payload["unknown"] = True
    write_request(request, payload)

    code, response = run_maintenance("inspect-data", request, result)

    assert code == 20
    assert response["reason"] == "request_invalid"


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(
        '{"schema":"iz-cna-data-inspection-request-v1",'
        '"schema":"iz-cna-data-inspection-request-v1",'
        '"data_root":"x","environment_file":"x","expected_database_path":""}',
        encoding="utf-8",
    )

    code, response = run_maintenance("inspect-data", request, result)

    assert code == 20
    assert response["reason"] == "request_invalid"


def test_existing_profile_without_explicit_encryption_key_is_blocked(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = data_root / ".env"
    environment_file.write_text("LOCAL_SQLITE_DB_PATH=profile.sqlite3\n", encoding="utf-8")
    create_database(data_root / "profile.sqlite3").close()
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    write_request(request, inspection_request(data_root, environment_file))

    code, response = run_maintenance("inspect-data", request, result)

    assert code == 20
    assert response["reason"] == "encryption_key_missing"
