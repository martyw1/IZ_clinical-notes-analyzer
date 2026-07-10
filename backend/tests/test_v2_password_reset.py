from __future__ import annotations

from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_must_reset_user_is_blocked_until_current_password_is_changed(tmp_path, monkeypatch) -> None:
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    created = client.post("/api/users", headers=admin_headers, json={"username": "resetuser", "full_name": "Synthetic Reset User", "role": "counselor", "password": "InitialResetPass1"})
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"username": "resetuser", "password": "InitialResetPass1"})
    assert login.status_code == 200
    assert login.json()["must_reset_password"] is True
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v2/dashboard", headers=headers).status_code == 403

    changed = client.post("/api/users/me/change-password", headers=headers, json={"current_password": "InitialResetPass1", "new_password": "UpdatedResetPass2"})
    assert changed.status_code == 200
    assert changed.json()["must_reset_password"] is False
    assert client.get("/api/v2/dashboard", headers=headers).status_code == 200
    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    assert any(item["action"] == "user.password.changed" for item in audit)
