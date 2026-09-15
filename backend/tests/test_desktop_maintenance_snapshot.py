from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.desktop_identity import current_user_sid, root_path_hash
from app.desktop_maintenance import main as maintenance_main

from test_desktop_maintenance import (
    SUCCESS_KEYS,
    create_database,
    run_maintenance,
    write_environment,
    write_request,
)

TRANSACTION_ID = "102030405060708090a0b0c0d0e0f001"


@pytest.fixture(autouse=True)
def clear_snapshot_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    names = tuple(name for name in os.environ if name.startswith("IZ_CNA_"))
    names += ("LOCAL_SQLITE_DB_PATH", "DATA_ENCRYPTION_KEY", "SECRET_KEY")
    for name in names:
        monkeypatch.delenv(name, raising=False)


def transaction_root(parent: Path) -> Path:
    root = parent / "maintenance" / "transactions" / TRANSACTION_ID
    (root / "requests").mkdir(parents=True)
    (root / "results").mkdir()
    (root / "snapshot").mkdir()
    marker = {
        "schema": "iz-cna-owned-root-v1",
        "product_id": "r3.iz-clinical-notes-analyzer.desktop",
        "owner_sid": current_user_sid(),
        "scope_id": "a" * 64,
        "role": "transaction",
        "transaction_id": TRANSACTION_ID,
        "root_path_hash": root_path_hash(root),
        "created_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    (root / ".iz-cna-owned-root.json").write_text(
        json.dumps(marker, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return root


def snapshot_request(data_root: Path, environment_file: Path, owned_root: Path) -> dict[str, object]:
    return {
        "schema": "iz-cna-database-snapshot-request-v1",
        "data_root": str(data_root),
        "environment_file": str(environment_file),
        "source_database_path": str(data_root / "profile.sqlite3"),
        "owned_output_root": str(owned_root),
        "snapshot_database_path": str(owned_root / "snapshot" / "selected-database.sqlite3"),
    }


def verification_request(data_root: Path, environment_file: Path, expected: str = "") -> dict[str, object]:
    return {
        "schema": "iz-cna-data-verification-request-v1",
        "data_root": str(data_root),
        "environment_file": str(environment_file),
        "expected_database_path": expected,
    }


def test_snapshot_captures_committed_wal_and_verifies_portably(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root)
    writer = create_database(data_root / "profile.sqlite3", wal=True)
    writer.execute("INSERT INTO patients(synthetic_code) VALUES('SYNTHETIC-0002')")
    writer.commit()
    owned_root = transaction_root(tmp_path)
    request = owned_root / "requests" / "snapshot.json"
    result = owned_root / "results" / "snapshot.json"
    write_request(request, snapshot_request(data_root, environment_file, owned_root))

    code, payload = run_maintenance("snapshot-database", request, result)

    writer.close()
    snapshot = owned_root / "snapshot" / "selected-database.sqlite3"
    assert code == 0, payload
    assert set(payload) == SUCCESS_KEYS | {"snapshot_sha256"}
    assert payload["schema"] == "iz-cna-database-snapshot-v1"
    assert payload["snapshot_sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    with sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2

    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored_environment = restored_root / ".env"
    shutil.copyfile(environment_file, restored_environment)
    shutil.copyfile(snapshot, restored_root / "profile.sqlite3")
    verify_request = owned_root / "requests" / "verify.json"
    verify_result = owned_root / "results" / "verify.json"
    write_request(verify_request, verification_request(restored_root, restored_environment))

    verify_code, verified = run_maintenance("verify-data", verify_request, verify_result)

    assert verify_code == 0
    assert set(verified) == SUCCESS_KEYS
    assert verified["schema"] == "iz-cna-data-verification-v1"
    assert verified["source_identity_hash"] == payload["source_identity_hash"]
    assert verified["profile_snapshot_identity"] == payload["profile_snapshot_identity"]
    assert verified["database_sha256"] == payload["database_sha256"]
    assert verified["data_identity"] != payload["data_identity"]


def test_snapshot_requires_exact_selected_database_destination(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root)
    create_database(data_root / "profile.sqlite3").close()
    owned_root = transaction_root(tmp_path)
    request = owned_root / "requests" / "snapshot.json"
    result = owned_root / "results" / "snapshot.json"
    payload = snapshot_request(data_root, environment_file, owned_root)
    payload["snapshot_database_path"] = str(owned_root / "snapshot" / "other.sqlite3")
    write_request(request, payload)

    code, response = run_maintenance("snapshot-database", request, result)

    assert code == 20
    assert response["reason"] == "snapshot_path_invalid"
    assert not (owned_root / "snapshot" / "other.sqlite3").exists()


def test_snapshot_never_overwrites_existing_destination(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root)
    create_database(data_root / "profile.sqlite3").close()
    owned_root = transaction_root(tmp_path)
    destination = owned_root / "snapshot" / "selected-database.sqlite3"
    destination.write_bytes(b"sentinel")
    request = owned_root / "requests" / "snapshot.json"
    result = owned_root / "results" / "snapshot.json"
    write_request(request, snapshot_request(data_root, environment_file, owned_root))

    code, response = run_maintenance("snapshot-database", request, result)

    assert code == 20
    assert response["reason"] == "snapshot_exists"
    assert destination.read_bytes() == b"sentinel"


def test_verify_resolves_empty_expected_path_and_rejects_mismatch(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root)
    create_database(data_root / "profile.sqlite3").close()
    request = tmp_path / "verify-request.json"
    result = tmp_path / "verify-result.json"
    write_request(request, verification_request(data_root, environment_file))

    code, payload = run_maintenance("verify-data", request, result)

    assert code == 0
    assert payload["database_relative_path"] == "profile.sqlite3"
    mismatch_request = tmp_path / "mismatch-request.json"
    mismatch_result = tmp_path / "mismatch-result.json"
    write_request(
        mismatch_request,
        verification_request(data_root, environment_file, str(data_root / "other.sqlite3")),
    )
    mismatch_code, mismatch = run_maintenance("verify-data", mismatch_request, mismatch_result)
    assert mismatch_code == 20
    assert mismatch["reason"] == "database_path_mismatch"


def test_verify_rebases_absolute_preflight_paths_without_rewriting_environment(tmp_path: Path) -> None:
    source_root = tmp_path / "source-profile"
    source_root.mkdir()
    source_database = source_root / "profile.sqlite3"
    environment_file = source_root / ".env"
    environment_file.write_text(
        f"IZ_CNA_ENV_FILE={environment_file}\n"
        f"IZ_CNA_LOCAL_APP_DATA_DIR={source_root}\n"
        f"IZ_CNA_LOCAL_SQLITE_DB_PATH={source_database}\n"
        "DATA_ENCRYPTION_KEY=synthetic-maintenance-key-material-00000001\n",
        encoding="utf-8",
    )
    create_database(source_database).close()
    owned_root = transaction_root(tmp_path)
    snapshot_request_path = owned_root / "requests" / "snapshot.json"
    snapshot_result_path = owned_root / "results" / "snapshot.json"
    write_request(
        snapshot_request_path,
        snapshot_request(source_root, environment_file, owned_root),
    )
    snapshot_code, snapshot_payload = run_maintenance(
        "snapshot-database",
        snapshot_request_path,
        snapshot_result_path,
    )
    assert snapshot_code == 0, snapshot_payload

    restored_root = tmp_path / "restored-profile"
    restored_root.mkdir()
    restored_environment = restored_root / ".env"
    restored_environment.write_bytes(environment_file.read_bytes())
    shutil.copyfile(
        owned_root / "snapshot" / "selected-database.sqlite3",
        restored_root / "profile.sqlite3",
    )
    verify_request_path = owned_root / "requests" / "verify-absolute.json"
    verify_result_path = owned_root / "results" / "verify-absolute.json"
    write_request(
        verify_request_path,
        verification_request(restored_root, restored_environment),
    )

    verify_code, verified = run_maintenance(
        "verify-data",
        verify_request_path,
        verify_result_path,
    )

    assert verify_code == 0
    assert restored_environment.read_bytes() == environment_file.read_bytes()
    assert verified["database_relative_path"] == "profile.sqlite3"
    assert verified["source_identity_hash"] == snapshot_payload["source_identity_hash"]
    assert verified["profile_snapshot_identity"] == snapshot_payload["profile_snapshot_identity"]
