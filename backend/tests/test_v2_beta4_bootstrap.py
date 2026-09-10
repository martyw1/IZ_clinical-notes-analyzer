from pathlib import Path

from pytest import MonkeyPatch

from v2_test_runtime import configured_client, prepare_app


def test_default_desktop_password_requires_change_and_is_not_restored(
    tmp_path: Path, monkeypatch: MonkeyPatch,
) -> None:
    # Given: a fresh local desktop installation without a custom bootstrap password.
    prepare_app(tmp_path, monkeypatch)
    monkeypatch.delenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "local-client")
    client = configured_client()

    # When: the supplied starter password is used for first sign-in.
    login = client.post("/api/auth/login", json={"username": "admin", "password": "r3mar123ABC"})

    # Then: setup is mandatory, and restarting never restores the starter password.
    assert login.status_code == 200
    assert login.json()["must_reset_password"] is True
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v2/dashboard", headers=headers).status_code == 403
    changed = client.post("/api/users/me/change-password", headers=headers, json={
        "current_password": "r3mar123ABC", "new_password": "SyntheticChosenPassword456",
    })
    assert changed.status_code == 200
    from app.v2.db import init_database
    init_database()
    assert client.post("/api/auth/login", json={"username": "admin", "password": "r3mar123ABC"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "SyntheticChosenPassword456"}).status_code == 200
