from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from pytest import raises

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _audit_items(client: TestClient, headers: dict[str, str], action: str) -> list[dict[str, object]]:
    response = client.get("/api/audit/logs", headers=headers)
    assert response.status_code == 200
    return [item for item in response.json()["items"] if item["action"] == action]


def test_unknown_and_mismatched_credentials_are_generic_but_forensically_distinct(tmp_path, monkeypatch) -> None:
    # Given: an active administrator who can inspect the protected forensic log.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: an unknown account and a known account both submit invalid credentials.
    unknown = client.post(
        "/api/auth/login",
        json={"username": "untrusted-submitted-name", "password": "UntrustedSubmittedSecret1"},
    )
    mismatched = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "UntrustedSubmittedSecret2"},
    )

    # Then: public responses are indistinguishable while admin-only records preserve safe categories.
    assert (unknown.status_code, unknown.json()) == (401, {"detail": "Invalid credentials"})
    assert (mismatched.status_code, mismatched.json()) == (401, {"detail": "Invalid credentials"})
    failures = _audit_items(client, headers, "auth.login.failed")[:2]
    assert {item["details"]["reason"] for item in failures} == {"unknown_account", "credential_mismatch"}
    assert all(item["target_entity_id"] != "untrusted-submitted-name" for item in failures)
    assert all(len(str(item["details"]["attempt_id"])) == 32 for item in failures)
    assert len({item["details"]["attempt_id"] for item in failures}) == 2
    assert all(isinstance(item["details"]["elapsed_ms"], int) for item in failures)
    assert "UntrustedSubmittedSecret" not in str(failures)


def test_inactive_and_locked_accounts_keep_generic_login_response_and_diagnostic_state(tmp_path, monkeypatch) -> None:
    # Given: one inactive account and one active account that will reach the lockout threshold.
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    inactive = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "inactive-login-user", "full_name": "Synthetic Inactive Login User", "role": "viewer", "password": "SyntheticInactivePass1"},
    )
    assert inactive.status_code == 200
    assert client.patch(
        f"/api/users/{inactive.json()['id']}", headers=admin_headers, json={"is_active": False}
    ).status_code == 200
    lock_target = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "lockout-login-user", "full_name": "Synthetic Lockout Login User", "role": "viewer", "password": "SyntheticLockoutPass1"},
    )
    assert lock_target.status_code == 200
    started_at = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.v2.api.foundation_routes._utc_now", lambda: started_at)

    # When: inactive credentials are correct and the other account is locked by five failures.
    inactive_login = client.post(
        "/api/auth/login", json={"username": "inactive-login-user", "password": "SyntheticInactivePass1"}
    )
    for _ in range(5):
        response = client.post(
            "/api/auth/login", json={"username": "lockout-login-user", "password": "IncorrectSyntheticPass9"}
        )
        assert response.status_code == 401
    locked_login = client.post(
        "/api/auth/login", json={"username": "lockout-login-user", "password": "SyntheticLockoutPass1"}
    )

    # Then: neither state is disclosed to the client and both are visible to administrators.
    assert (inactive_login.status_code, inactive_login.json()) == (401, {"detail": "Invalid credentials"})
    assert (locked_login.status_code, locked_login.json()) == (401, {"detail": "Invalid credentials"})
    blocked = _audit_items(client, admin_headers, "auth.login.blocked")
    assert {item["details"]["reason"] for item in blocked} >= {"inactive_account", "active_lockout"}
    lockout = _audit_items(client, admin_headers, "auth.lockout.started")[0]
    assert lockout["details"]["reason"] == "failure_threshold_reached"
    assert lockout["details"]["failed_attempts"] == 5
    assert lockout["details"]["account_state"] == "locked_until"


def test_expired_lockout_clears_and_preserves_forced_change_state(tmp_path, monkeypatch) -> None:
    # Given: the bootstrap administrator is locked before completing the required credential change.
    client = _fresh_client(tmp_path, monkeypatch)
    started_at = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.v2.api.foundation_routes._utc_now", lambda: started_at)
    for _ in range(5):
        assert client.post(
            "/api/auth/login", json={"username": "admin", "password": "IncorrectSyntheticPass9"}
        ).status_code == 401

    # When: the exact lockout expiry arrives and the starter credential is supplied.
    monkeypatch.setattr("app.v2.api.foundation_routes._utc_now", lambda: started_at + timedelta(minutes=15))
    first = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"})

    # Then: login recovers into forced-change state with diagnostic state intact.
    assert first.status_code == 200
    assert first.json()["auth_state"] == "password_change_required"
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    changed = client.post(
        "/api/users/me/change-password",
        headers=headers,
        json={"current_password": "StrongLocalPass1", "new_password": "SyntheticPostBootstrapPass2"},
    )
    assert changed.status_code == 200
    active_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    success = _audit_items(client, active_headers, "auth.login.success")[0]
    assert success["details"]["account_state"] == "change_required"
    assert success["details"]["credential_change_required"] is True
    assert client.get("/api/users/me", headers=headers).status_code == 401
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"}
    ).status_code == 401


def test_bootstrap_transition_is_recorded_once_across_repeated_forced_change_logins(tmp_path, monkeypatch) -> None:
    # Given: a fresh bootstrap administrator.
    client = _fresh_client(tmp_path, monkeypatch)

    # When: the starter credential is accepted twice before the required change.
    first = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"})
    second = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"})
    assert first.status_code == second.status_code == 200
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    changed = client.post(
        "/api/users/me/change-password",
        headers=headers,
        json={"current_password": "StrongLocalPass1", "new_password": "SyntheticPostBootstrapPass2"},
    )
    assert changed.status_code == 200

    # Then: only the actual bootstrap-state transition has a completion record.
    active_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert len(_audit_items(client, active_headers, "auth.bootstrap.completed")) == 1


def test_local_admin_recovery_revokes_sessions_credentials_and_recovery_code(tmp_path, monkeypatch) -> None:
    # Given: an active administrator with a session and configured recovery code.
    client = _fresh_client(tmp_path, monkeypatch)
    active_headers = _auth_headers(client)
    generated = client.post(
        "/api/users/me/recovery-code",
        headers=active_headers,
        json={"current_password": "StrongLocalActivePass2"},
    )
    assert generated.status_code == 200

    # When: the local-only recovery boundary installs a temporary credential.
    from app.v2.local_admin_recovery import recover_local_admin

    recover_local_admin("SyntheticLocalRecoveryPass3")

    # Then: prior access paths are revoked and the replacement still requires a change.
    assert client.get("/api/users/me", headers=active_headers).status_code == 401
    for obsolete_password in ("StrongLocalPass1", "StrongLocalActivePass2"):
        assert client.post(
            "/api/auth/login", json={"username": "admin", "password": obsolete_password}
        ).status_code == 401
    old_code = client.post(
        "/api/auth/recover-password",
        json={
            "username": "admin",
            "recovery_code": generated.json()["recovery_code"],
            "new_password": "SyntheticRecoveredPass4",
        },
    )
    assert old_code.status_code == 400
    temporary_login = client.post(
        "/api/auth/login", json={"username": "admin", "password": "SyntheticLocalRecoveryPass3"}
    )
    assert temporary_login.status_code == 200
    assert temporary_login.json()["must_reset_password"] is True
    temporary_headers = {"Authorization": f"Bearer {temporary_login.json()['access_token']}"}
    changed = client.post(
        "/api/users/me/change-password",
        headers=temporary_headers,
        json={
            "current_password": "SyntheticLocalRecoveryPass3",
            "new_password": "SyntheticPostRecoveryPass4",
        },
    )
    assert changed.status_code == 200
    changed_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/users/me/recovery-code", headers=changed_headers).json() == {"configured": False}


def test_local_admin_recovery_rolls_back_when_audit_append_fails(tmp_path, monkeypatch) -> None:
    # Given: an active administrator and a forced audit-storage failure.
    client = _fresh_client(tmp_path, monkeypatch)
    active_headers = _auth_headers(client)
    generated = client.post(
        "/api/users/me/recovery-code",
        headers=active_headers,
        json={"current_password": "StrongLocalActivePass2"},
    )
    assert generated.status_code == 200
    from app.v2 import local_admin_recovery

    def fail_audit(*_args, **_kwargs) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(local_admin_recovery, "record_audit_event", fail_audit)

    # When: local recovery cannot append its forensic record.
    with raises(RuntimeError, match="synthetic audit failure"):
        local_admin_recovery.recover_local_admin("SyntheticLocalRecoveryPass3")

    # Then: the credential, session, and recovery-code state remain unchanged.
    assert client.get("/api/users/me", headers=active_headers).status_code == 200
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "StrongLocalActivePass2"}
    ).status_code == 200
    assert client.get("/api/users/me/recovery-code", headers=active_headers).json() == {"configured": True}
