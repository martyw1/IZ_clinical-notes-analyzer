from __future__ import annotations

import base64
import hashlib
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from test_v2_manual_patient_correction import _auth_headers, _fresh_client
from v2_test_runtime import configured_client, prepare_app

DATA_KEY = "test-data-encryption-key-for-v2-manual-correction"
SYNTHETIC_CLIENT_ID = "synthetic-legacy-client-id"
SYNTHETIC_CLIENT_SECRET = "synthetic-legacy-client-secret"
DEFAULT_API_BASE = "https://api.allevasoft.com"
DEFAULT_TOKEN_URL = "https://authorization.allevasoft.com/connect/token"


def _legacy_database_path(tmp_path: Path) -> Path:
    return tmp_path / "app-data" / "clinical-notes-analyzer.sqlite3"


def _v2_database_path(tmp_path: Path) -> Path:
    return tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"


def _v1_encrypted_secret(value: str, key: str = DATA_KEY) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    token = Fernet(base64.urlsafe_b64encode(digest)).encrypt(value.encode("utf-8"))
    payload = base64.urlsafe_b64encode(b"IZCNA1\n" + token).decode("ascii")
    return f"IZCNA1-TEXT:{payload}"


def _create_legacy_settings(
    tmp_path: Path,
    *,
    client_id: str = SYNTHETIC_CLIENT_ID,
    client_secret: str | None = None,
    api_base_url: str = DEFAULT_API_BASE,
    token_url: str = DEFAULT_TOKEN_URL,
    token_auth_style: str = "body",
    api_version: str = "1.0",
    enabled: bool = True,
    sync_enabled: bool = True,
    sync_approved: bool = True,
    mapping_validated: bool = True,
) -> Path:
    database_path = _legacy_database_path(tmp_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    stored_secret = _v1_encrypted_secret(SYNTHETIC_CLIENT_SECRET) if client_secret is None else client_secret
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """CREATE TABLE app_settings(
                id INTEGER PRIMARY KEY,
                emr_vendor_name TEXT NOT NULL,
                emr_api_enabled INTEGER NOT NULL,
                api_client_id TEXT NOT NULL,
                api_client_secret TEXT NOT NULL,
                api_oauth_token_url TEXT NOT NULL,
                api_token_auth_style TEXT NOT NULL,
                emr_api_timeout_seconds INTEGER NOT NULL,
                alleva_api_base_url TEXT NOT NULL,
                alleva_openapi_url TEXT NOT NULL,
                alleva_api_version TEXT NOT NULL,
                alleva_treatment_plan_sync_enabled INTEGER NOT NULL,
                alleva_treatment_plan_sync_approved INTEGER NOT NULL,
                alleva_treatment_plan_endpoint_mapping_validated INTEGER NOT NULL,
                alleva_treatment_plan_sync_limit INTEGER NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO app_settings VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "Alleva REST API",
                int(enabled),
                client_id,
                stored_secret,
                token_url,
                token_auth_style,
                30,
                api_base_url,
                f"{api_base_url}/swagger/v1/swagger.json",
                api_version,
                int(sync_enabled),
                int(sync_approved),
                int(mapping_validated),
                250,
            ),
        )
        connection.commit()
    return database_path


def test_pristine_v2_migrates_v1_credentials_with_redacted_api_and_audit(tmp_path: Path, monkeypatch) -> None:
    # Given: a pristine V2 app-data directory and a valid synthetic V1 API profile.
    legacy_path = _create_legacy_settings(tmp_path)
    legacy_hash = hashlib.sha256(legacy_path.read_bytes()).hexdigest()

    # When: V2 starts and an administrator reads the saved API configuration.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    response = client.get("/api/api-configuration", headers=headers)

    # Then: credentials are V2-encrypted at rest while browser and audit payloads expose flags only.
    assert response.status_code == 200
    payload = response.json()
    assert "client_id" not in payload
    assert payload["client_id_configured"] is True
    assert payload["client_secret_configured"] is True
    assert payload["api_version"] == "1.0"
    assert payload["treatment_plan_start_date"] == "2000-01-01T16:03"
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT api_client_id,api_client_secret,legacy_api_settings_migration_state,"
            "alleva_treatment_plan_sync_enabled,alleva_treatment_plan_sync_approved,"
            "alleva_treatment_plan_endpoint_mapping_validated FROM app_settings"
        ).fetchone()
    assert row is not None
    assert str(row[0]).startswith("enc:v1:")
    assert str(row[1]).startswith("enc:v1:")
    from app.v2.services.secure_storage import decrypt_api_client_id, decrypt_text_secret

    assert decrypt_api_client_id(str(row[0])) == SYNTHETIC_CLIENT_ID
    assert decrypt_text_secret(str(row[1])) == SYNTHETIC_CLIENT_SECRET
    assert str(row[2]) in {"credentials_migrated_approval_pending", "completed"}
    if row[2] == "credentials_migrated_approval_pending":
        assert row[3:] == (0, 0, 0)
    audit = client.get("/api/audit/logs", headers=headers)
    assert audit.status_code == 200
    audit_text = audit.text
    assert "settings.legacy_api.migration" in audit_text
    assert SYNTHETIC_CLIENT_ID not in audit_text
    assert SYNTHETIC_CLIENT_SECRET not in audit_text
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest() == legacy_hash


@pytest.mark.parametrize(
    "stored_secret",
    (
        SYNTHETIC_CLIENT_SECRET,
        "IZCNA1-TEXT:not-valid-base64!",
        "enc:v1:foreign-v2-envelope",
    ),
)
def test_untrusted_v1_secret_never_becomes_v2_configuration(
    tmp_path: Path,
    monkeypatch,
    stored_secret: str,
) -> None:
    # Given: a V1 profile whose secret is plaintext, corrupt, or from a foreign envelope.
    _create_legacy_settings(tmp_path, client_secret=stored_secret)

    # When: V2 attempts its one-time migration.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # Then: the migration fails closed without configuring credentials or enabling sync gates.
    response = client.get("/api/api-configuration", headers=headers)
    assert response.status_code == 200
    assert response.json()["client_id_configured"] is False
    assert response.json()["client_secret_configured"] is False
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT legacy_api_settings_migration_state,alleva_treatment_plan_sync_enabled,"
            "alleva_treatment_plan_sync_approved,alleva_treatment_plan_endpoint_mapping_validated "
            "FROM app_settings"
        ).fetchone()
    assert row == ("legacy_source_rejected", 0, 0, 0)


def test_user_configured_v2_profile_is_preserved_instead_of_migrated(tmp_path: Path, monkeypatch) -> None:
    # Given: a V2 API profile saved by an administrator before a V1 source is discovered.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "api_base_url": "https://synthetic-v2.invalid",
            "client_id": "synthetic-v2-client-id",
            "client_secret": "synthetic-v2-client-secret",
        },
    )
    assert saved.status_code == 200
    _create_legacy_settings(tmp_path)

    # When: the application starts again with the legacy database present.
    restarted = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _auth_headers(restarted)
    response = restarted.get("/api/api-configuration", headers=restarted_headers)

    # Then: V2 configuration wins and remains redacted.
    assert response.status_code == 200
    assert response.json()["api_base_url"] == "https://synthetic-v2.invalid"
    assert "client_id" not in response.json()
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT api_client_id,legacy_api_settings_migration_state FROM app_settings"
        ).fetchone()
    assert row is not None
    from app.v2.services.secure_storage import decrypt_api_client_id

    assert decrypt_api_client_id(str(row[0])) == "synthetic-v2-client-id"
    assert row[1] == "v2_user_configured"


@pytest.mark.parametrize(
    ("legacy_override", "override_value"),
    (
        ("enabled", False),
        ("sync_enabled", False),
        ("sync_approved", False),
        ("mapping_validated", False),
        ("api_base_url", "https://synthetic-untrusted.invalid"),
        ("token_url", "https://synthetic-token.invalid/connect/token"),
        ("token_auth_style", "both"),
        ("api_version", "2.0"),
    ),
)
def test_every_untrusted_legacy_approval_edge_forces_all_sync_gates_false(
    tmp_path: Path,
    monkeypatch,
    legacy_override: str,
    override_value: str | bool,
) -> None:
    # Given: exactly one required legacy approval or connection predicate is untrusted.
    arguments: dict[str, str | bool] = {legacy_override: override_value}
    _create_legacy_settings(tmp_path, **arguments)

    # When: the one-time migration evaluates the synthetic profile.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # Then: credentials may be retained for correction, but no live-sync gate is inferred.
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT legacy_api_settings_migration_state,alleva_treatment_plan_sync_enabled,"
            "alleva_treatment_plan_sync_approved,alleva_treatment_plan_endpoint_mapping_validated "
            "FROM app_settings"
        ).fetchone()
    assert row == ("completed", 0, 0, 0)
    response = client.get("/api/api-configuration", headers=headers)
    assert response.status_code == 200
    assert response.json()["client_id_configured"] is True
    assert SYNTHETIC_CLIENT_ID not in response.text


def test_pending_approval_reconciles_once_corrected_contract_is_available(tmp_path: Path, monkeypatch) -> None:
    # Given: credentials were migrated while the built-in mapping compatibility check was pending.
    _create_legacy_settings(tmp_path)
    prepare_app(tmp_path, monkeypatch)
    import app.v2.services.legacy_settings_migration as migration

    monkeypatch.setattr(migration, "_builtin_contract_is_compatible", lambda _profile: False)
    client = configured_client()
    _auth_headers(client)
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        state = connection.execute(
            "SELECT legacy_api_settings_migration_state FROM app_settings"
        ).fetchone()[0]
    assert state == "credentials_migrated_approval_pending"
    from app.core.config import settings
    from app.v2.db import SessionLocal

    monkeypatch.setattr(migration, "_builtin_contract_is_compatible", lambda _profile: True)

    # When: startup reconciliation sees the corrected exact contract.
    with SessionLocal() as db:
        result = migration.migrate_legacy_api_settings(
            db,
            settings.legacy_sqlite_db_path,
            settings.effective_data_encryption_secret,
        )
        db.commit()

    # Then: the phased marker completes and all three gates become true atomically.
    assert result == "completed"
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT legacy_api_settings_migration_state,alleva_treatment_plan_sync_enabled,"
            "alleva_treatment_plan_sync_approved,alleva_treatment_plan_endpoint_mapping_validated "
            "FROM app_settings"
        ).fetchone()
    assert row == ("completed", 1, 1, 1)


def test_migration_marker_is_idempotent_and_never_reimports_changed_legacy_values(tmp_path: Path, monkeypatch) -> None:
    # Given: a first migration has durably stored a V2-encrypted client identifier.
    legacy_path = _create_legacy_settings(tmp_path)
    first = _fresh_client(tmp_path, monkeypatch)
    _auth_headers(first)
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        before = connection.execute("SELECT api_client_id FROM app_settings").fetchone()[0]
    with sqlite3.connect(legacy_path) as connection:
        connection.execute("UPDATE app_settings SET api_client_id='synthetic-changed-legacy-id'")
        connection.commit()

    # When: V2 starts again after the legacy source changes.
    restarted = _fresh_client(tmp_path, monkeypatch)
    _auth_headers(restarted)

    # Then: the migrated credential is not overwritten or silently approved.
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT api_client_id,legacy_api_settings_migration_state,"
            "alleva_treatment_plan_sync_approved FROM app_settings"
        ).fetchone()
    assert row[0] == before
    assert row[1] in {"completed", "v2_user_configured"}
    if row[1] == "v2_user_configured":
        assert row[2] == 0


def test_migration_rolls_back_settings_when_required_audit_write_fails(tmp_path: Path, monkeypatch) -> None:
    # Given: a pristine V2 row and a valid legacy profile, but unavailable audit persistence.
    _create_legacy_settings(tmp_path)
    client = _fresh_client(tmp_path, monkeypatch)
    _auth_headers(client)
    import app.v2.services.legacy_settings_migration as migration
    from app.core.config import settings
    from app.v2.db import SessionLocal

    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE app_settings SET api_client_id='',api_client_secret='',"
            "legacy_api_settings_migration_state='',alleva_treatment_plan_sync_enabled=0,"
            "alleva_treatment_plan_sync_approved=0,alleva_treatment_plan_endpoint_mapping_validated=0"
        )
        connection.execute("DELETE FROM audit_logs WHERE action='settings.legacy_api.migration'")
        connection.commit()

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("synthetic audit persistence failure")

    monkeypatch.setattr(migration, "record_audit_event", fail_audit)

    # When: migration cannot atomically write its required audit fact.
    with pytest.raises(RuntimeError, match="synthetic audit persistence failure"):
        with SessionLocal() as db:
            migration.migrate_legacy_api_settings(
                db,
                settings.legacy_sqlite_db_path,
                settings.effective_data_encryption_secret,
            )

    # Then: the session rollback leaves credentials and gates pristine.
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT api_client_id,api_client_secret,legacy_api_settings_migration_state,"
            "alleva_treatment_plan_sync_enabled,alleva_treatment_plan_sync_approved,"
            "alleva_treatment_plan_endpoint_mapping_validated FROM app_settings"
        ).fetchone()
    assert row == ("", "", "", 0, 0, 0)


@pytest.mark.parametrize(
    "payload",
    (
        {"api_version": "2.0"},
        {"treatment_plan_start_date": "2026-99-99T99:99"},
    ),
)
def test_api_rejects_unproven_protocol_settings(tmp_path: Path, monkeypatch, payload: dict[str, str]) -> None:
    # Given: an administrator is authenticated to a pristine V2 configuration.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: the administrator submits an unsupported API version or malformed StartDate.
    response = client.patch("/api/api-configuration", headers=headers, json=payload)

    # Then: boundary validation rejects it without mutating persisted defaults.
    assert response.status_code == 422
    with sqlite3.connect(_v2_database_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT alleva_api_version,alleva_treatment_plan_start_date FROM app_settings"
        ).fetchone()
    assert row == ("1.0", "2000-01-01T16:03")
