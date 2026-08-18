from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import (
    _LifespanTestClient,
    _auth_headers,
    _fresh_client,
    _isolate_application_modules,
    _retain_client_lifespan,
)
from v2_migration_fixtures import (
    SYNTHETIC_SECRET,
    create_legacy_database,
    downgrade_to_pre_v2_schema,
    encrypted_text,
)
from app.v2.migrations.backup import read_backup
from app.v2.migrations.backfill_types import encrypt_bytes
from app.v2.migrations.schema_core import USER_EXTENSIONS
from app.v2.services.clinical_snapshot_codec import ClinicalSnapshotCodec, PlanRecordSnapshot, SnapshotCodecError

PRIVACY_CANARY = "MIGRATED-PATIENT-NAME-CANARY"


def test_manual_import_snapshot_contract_remains_http_compatible(tmp_path, monkeypatch) -> None:
    # Given: a fresh application using the existing manual-import path.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: a synthetic treatment plan is imported and read through both HTTP surfaces.
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "982"},
        files={"file": ("synthetic-baseline.txt", "Patient ID: 982\nIntervention: Synthetic baseline.", "text/plain")},
        headers=headers,
    )
    listed = client.get("/api/v2/treatment-plans", headers=headers)
    detail = client.get("/api/v2/treatment-plans/982", headers=headers)

    # Then: the established aggregate snapshot remains readable.
    assert imported.status_code == 201
    assert listed.status_code == 200
    assert detail.status_code == 200


def test_startup_migration_serves_multi_version_plan_and_review_records(tmp_path, monkeypatch) -> None:
    # Given: a synthetic legacy database with multiple plans, reviews, and nested identity aliases.
    client, _original_database_bytes = _migrated_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: the migrated patient is read through the real authenticated HTTP routes.
    listed = client.get("/api/v2/treatment-plans", headers=headers)
    detail = client.get("/api/v2/treatment-plans/synthetic-client-200", headers=headers)

    # Then: list and detail assemble every version without exposing patient names.
    assert listed.status_code == 200
    assert detail.status_code == 200
    assert listed.json()["items"][0]["patient_id"] == "synthetic-client-200"
    payload = detail.json()
    assert [plan["id"] for plan in payload["treatment_plans"]] == ["synthetic-plan-1", "synthetic-plan-2"]
    assert [review["id"] for review in payload["treatment_reviews"]] == ["synthetic-review-1", "synthetic-review-2"]
    assert PRIVACY_CANARY not in json.dumps(listed.json(), sort_keys=True)
    assert PRIVACY_CANARY not in json.dumps(payload, sort_keys=True)
    with closing(sqlite3.connect(tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3")) as connection:
        assert connection.execute("SELECT DISTINCT trigger_kind FROM evaluation_runs").fetchall() == [("migration",)]


def test_startup_migrates_legacy_user_and_settings_columns_before_orm_bootstrap(tmp_path, monkeypatch) -> None:
    # Given: a synthetic legacy database from before the v2 user and API settings columns existed.
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_USERNAME", "replacement-admin")
    client, original_database_bytes = _migrated_client(tmp_path, monkeypatch, use_legacy_schema=True)

    # When: the real application startup and readiness boundary run.
    readiness = client.get("/api/readiness")

    # Then: startup succeeds and the ordered migration restores every required user column.
    assert readiness.status_code == 200
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info('users')")}
        settings = connection.execute(
            "SELECT api_base_url,openapi_url,api_scopes,api_pagination_limit FROM app_settings"
        ).fetchone()
        replacement_admin = connection.execute(
            "SELECT auth_state FROM users WHERE username='replacement-admin'"
        ).fetchone()
    backup_path = next((tmp_path / "app-data" / "backups").glob("migration-0-to-*.izcnabackup"))
    backup = read_backup(backup_path, SYNTHETIC_SECRET)
    assert {name for name, _definition in USER_EXTENSIONS}.issubset(columns)
    assert settings == (
        "https://legacy-api.invalid",
        "https://legacy-api.invalid/openapi.json",
        "",
        100,
    )
    assert replacement_admin == ("bootstrap_required",)
    assert backup.database_bytes == original_database_bytes


def test_snapshot_codec_accepts_legacy_record_envelope_and_rejects_malformed_token() -> None:
    # Given: the compatibility envelope used by already-migrated record snapshots.
    codec = ClinicalSnapshotCodec(SYNTHETIC_SECRET)
    legacy = encrypt_bytes(b'{"id":"legacy-plan-1"}', SYNTHETIC_SECRET)

    # When: the legacy record and a malformed encrypted token cross the typed codec boundary.
    decoded = codec.decode_plan(legacy)

    # Then: the legacy record is typed and malformed ciphertext raises the codec-specific error.
    assert isinstance(decoded, PlanRecordSnapshot)
    assert decoded.record == {"id": "legacy-plan-1"}
    with pytest.raises(SnapshotCodecError, match="token"):
        codec.decode_plan(b"IZCNA1:not-a-valid-token")


def _migrated_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_legacy_schema: bool = False,
) -> tuple[TestClient, bytes]:
    app_data = tmp_path / "app-data"
    app_data.mkdir()
    monkeypatch.delenv("IZ_CNA_ENV_FILE", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(app_data))
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "StrongLocalPass1")
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "synthetic-http-secret")
    monkeypatch.setenv("IZ_CNA_DATA_ENCRYPTION_KEY", SYNTHETIC_SECRET)
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost,127.0.0.1,::1,testserver")
    _isolate_application_modules(monkeypatch)
    database_path = create_legacy_database(app_data)
    if use_legacy_schema:
        downgrade_to_pre_v2_schema(database_path)
    from app.v2.security import hash_password

    payload = {
        "patient_id": "synthetic-client-200",
        "source_mode": "manual_upload",
        "treatment_plans": [
            {"id": "synthetic-plan-1", "plan_date": "2026-06-01", "patient_full_name": PRIVACY_CANARY},
            {"id": "synthetic-plan-2", "plan_date": "2026-07-01", "nested": {"clientFullName": PRIVACY_CANARY}},
        ],
        "treatment_reviews": [
            {"id": "synthetic-review-1", "review_date": "2026-06-15", "patientName": PRIVACY_CANARY},
            {"id": "synthetic-review-2", "review_date": "2026-07-05", "client_full_name": PRIVACY_CANARY},
        ],
    }
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("UPDATE users SET password_hash=? WHERE username='admin'", (hash_password("StrongLocalPass1"),))
        connection.execute(
            "UPDATE treatment_plan_imports SET encrypted_payload=? WHERE patient_id='synthetic-client-200'",
            (encrypted_text(json.dumps(payload, sort_keys=True)),),
        )
        connection.commit()
    original_database_bytes = database_path.read_bytes()
    from app.main import create_app

    client = _LifespanTestClient(create_app(), raise_server_exceptions=False)
    return _retain_client_lifespan(client, monkeypatch), original_database_bytes
