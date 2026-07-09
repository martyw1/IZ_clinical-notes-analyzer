from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


BOOTSTRAP_PASSWORD = "StrongLocalPass1"
SECRET_VALUE = "saved-secret-should-be-encrypted"


def _fresh_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", BOOTSTRAP_PASSWORD)
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "test-secret-key-for-v2-foundation")
    monkeypatch.setenv("IZ_CNA_DATA_ENCRYPTION_KEY", "test-data-encryption-key-for-v2-foundation")
    for module_name in tuple(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)
    from app.main import create_app

    return TestClient(create_app())


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": BOOTSTRAP_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_auth_rejects_wrong_password_and_protects_routes(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    protected = client.get("/api/users/me")
    wrong_login = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
    headers = _admin_headers(client)
    profile = client.get("/api/users/me", headers=headers)

    assert protected.status_code == 401
    assert wrong_login.status_code == 401
    assert profile.status_code == 200
    assert profile.json()["username"] == "admin"


def test_non_admin_is_blocked_from_admin_routes(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _admin_headers(client)
    created = client.post(
        "/api/users",
        json={"username": "counselor1", "full_name": "Counselor One", "role": "counselor", "password": "CounselorPass1"},
        headers=admin_headers,
    )
    login = client.post("/api/auth/login", json={"username": "counselor1", "password": "CounselorPass1"})
    counselor_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    users_response = client.get("/api/users", headers=counselor_headers)
    settings_response = client.patch("/api/settings", json={"organization_name": "Blocked"}, headers=counselor_headers)

    assert created.status_code == 200
    assert login.status_code == 200
    assert users_response.status_code == 403
    assert settings_response.status_code == 403


def test_admin_can_create_update_deactivate_and_reset_users(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _admin_headers(client)
    created = client.post(
        "/api/users",
        json={"username": "manager1", "full_name": "Manager One", "role": "office_manager", "password": "ManagerPass1"},
        headers=headers,
    )
    user_id = created.json()["id"]
    updated = client.patch(f"/api/users/{user_id}", json={"full_name": "Manager Updated", "is_active": False}, headers=headers)
    reset = client.post(
        f"/api/users/{user_id}/reset-password",
        json={"new_password": "ResetPass123", "require_reset_on_login": True},
        headers=headers,
    )
    login = client.post("/api/auth/login", json={"username": "manager1", "password": "ResetPass123"})

    assert created.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False
    assert reset.status_code == 200
    assert login.status_code == 403


def test_settings_and_api_secret_persist_encrypted_across_restart(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _admin_headers(client)
    settings_saved = client.patch(
        "/api/settings",
        json={"organization_name": "R3 Recovery Services Test", "treatment_plan_loc_change_window_days": 9},
        headers=headers,
    )
    api_saved = client.patch(
        "/api/api-configuration",
        json={
            "vendor_name": "Alleva Test",
            "api_base_url": "https://api.example.test",
            "openapi_url": "https://api.example.test/swagger.json",
            "token_url": "https://authorization.example.test/connect/token",
            "client_id": "test-client",
            "client_secret": SECRET_VALUE,
            "token_auth_style": "body",
            "timeout_seconds": 7,
            "api_enabled": True,
        },
        headers=headers,
    )
    restarted = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _admin_headers(restarted)
    loaded_settings = restarted.get("/api/settings", headers=restarted_headers)
    loaded_api = restarted.get("/api/api-configuration", headers=restarted_headers)
    database_bytes = (tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3").read_bytes()

    assert settings_saved.status_code == 200
    assert api_saved.status_code == 200
    assert SECRET_VALUE not in api_saved.text
    assert loaded_settings.json()["organization_name"] == "R3 Recovery Services Test"
    assert loaded_settings.json()["treatment_plan_loc_change_window_days"] == 9
    assert loaded_api.json()["client_secret_configured"] is True
    assert SECRET_VALUE.encode("utf-8") not in database_bytes


def test_audit_log_endpoint_returns_real_redacted_events(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _admin_headers(client)
    client.patch(
        "/api/api-configuration",
        json={"vendor_name": "Audit Test", "client_secret": SECRET_VALUE, "api_enabled": False},
        headers=headers,
    )

    response = client.get("/api/audit/logs", headers=headers)
    payload = response.json()
    actions = {item["action"] for item in payload["items"]}

    assert response.status_code == 200
    assert "settings.api_profile.saved" in actions
    assert SECRET_VALUE not in response.text
