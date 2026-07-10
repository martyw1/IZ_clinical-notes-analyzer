from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import text

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_user(client: TestClient, headers: dict[str, str], username: str, role: str) -> tuple[int, dict[str, str]]:
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": username,
            "full_name": f"Synthetic {role}",
            "role": role,
            "password": "SyntheticTemporaryPass123",
        },
    )
    assert created.status_code == 200, created.text
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "SyntheticTemporaryPass123"},
    )
    assert login.status_code == 200, login.text
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = client.post(
        "/api/users/me/change-password",
        headers=user_headers,
        json={"current_password": "SyntheticTemporaryPass123", "new_password": "SyntheticActivePass456"},
    )
    assert changed.status_code == 200, changed.text
    active_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "SyntheticActivePass456"},
    )
    assert active_login.status_code == 200, active_login.text
    return int(created.json()["id"]), {"Authorization": f"Bearer {active_login.json()['access_token']}"}


def test_first_run_transitions_bootstrap_to_password_change_to_active(tmp_path: Path, monkeypatch) -> None:
    # Given: a newly initialized local database.
    client = _fresh_client(tmp_path, monkeypatch)

    # When: the generated bootstrap credential is used for the first time.
    login = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"})

    # Then: the account enters password-change-required and cannot enter the workspace.
    assert login.status_code == 200
    assert login.json()["auth_state"] == "password_change_required"
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v2/dashboard", headers=headers).status_code == 403

    # When: the administrator replaces the generated credential.
    changed = client.post(
        "/api/users/me/change-password",
        headers=headers,
        json={"current_password": "StrongLocalPass1", "new_password": "SyntheticActivePass456"},
    )

    # Then: the account is active and both transitions are audited.
    assert changed.status_code == 200
    assert changed.json()["auth_state"] == "active"
    fresh = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "SyntheticActivePass456"},
    )
    assert fresh.status_code == 200
    active_headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert client.get("/api/v2/dashboard", headers=active_headers).status_code == 200
    audit = client.get("/api/audit/logs", headers=active_headers).json()["items"]
    actions = {item["action"] for item in audit}
    assert {"auth.bootstrap.completed", "user.password.changed"} <= actions


def test_five_failures_lock_for_exactly_fifteen_minutes_with_injected_clock(tmp_path: Path, monkeypatch) -> None:
    # Given: an active administrator and a deterministic clock.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    start = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.v2.api.foundation_routes._utc_now", lambda: start)

    # When: five consecutive invalid passwords are submitted.
    for _ in range(5):
        response = client.post("/api/auth/login", json={"username": "admin", "password": "IncorrectPass999"})
        assert response.status_code == 401

    # Then: the correct credential remains locked just before the boundary.
    monkeypatch.setattr("app.v2.api.foundation_routes._utc_now", lambda: start + timedelta(minutes=14, seconds=59))
    locked = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalActivePass2"})
    assert locked.status_code == 423
    assert locked.json()["detail"] == "Account temporarily locked"

    # When: the exact 15-minute boundary arrives.
    monkeypatch.setattr("app.v2.api.foundation_routes._utc_now", lambda: start + timedelta(minutes=15))
    unlocked = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalActivePass2"})

    # Then: sign-in succeeds and the lock state is cleared.
    assert unlocked.status_code == 200
    assert unlocked.json()["auth_state"] == "active"
    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert any(item["action"] == "auth.lockout.started" for item in audit)


def test_exact_roles_facility_and_patient_assignment_scope_all_route_outcomes(tmp_path: Path, monkeypatch) -> None:
    # Given: one imported patient, canonical roles, and a counselor without an assignment.
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    configured = client.patch(
        "/api/settings",
        headers=admin_headers,
        json={"facility_timezone": "America/New_York"},
    )
    assert configured.status_code == 200
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        headers=admin_headers,
        data={"patient_id": "synthetic-812", "confirm_patient_id_correction": "false"},
        files={
            "file": (
                "synthetic-812.txt",
                "Patient ID: synthetic-812\nCurrent Level of Care: PHP\nAdmission Date: 2026-07-01",
                "text/plain",
            )
        },
    )
    assert imported.status_code == 201, imported.text
    counselor_id, counselor_headers = _create_user(client, admin_headers, "counselor1", "counselor")
    _, viewer_headers = _create_user(client, admin_headers, "viewer1", "viewer")
    _, manager_headers = _create_user(client, admin_headers, "manager1", "office_manager")

    # When/Then: unassigned counselor and facility-unassigned viewer cannot enumerate or IDOR-read the patient.
    assert client.get("/api/v2/treatment-plans", headers=counselor_headers).json()["items"] == []
    assert client.get("/api/v2/treatment-plans/synthetic-812", headers=counselor_headers).status_code == 403
    assert client.get("/api/v2/treatment-plans", headers=viewer_headers).json()["items"] == []
    assert client.get("/api/v2/treatment-plans/synthetic-812", headers=viewer_headers).status_code == 403

    # When: the admin assigns the default facility and patient.
    facilities = client.get("/api/facilities", headers=admin_headers)
    assert facilities.status_code == 200
    facility_id = facilities.json()[0]["id"]
    assert client.put(f"/api/users/{counselor_id}/facilities/{facility_id}", headers=admin_headers).status_code == 200
    assignment = client.put(
        "/api/patient-assignments/synthetic-812/counselor1",
        headers=admin_headers,
    )
    assert assignment.status_code == 200, assignment.text

    # Then: the counselor can read assigned data but cannot mutate/download/export/administer.
    assert client.get("/api/v2/treatment-plans/synthetic-812", headers=counselor_headers).status_code == 200
    assert client.post(
        "/api/v2/treatment-plans/synthetic-812/manager-actions",
        headers=counselor_headers,
        json={"criterion_id": "criterion-1", "action": "comment", "comment": "safe", "override_reason": ""},
    ).status_code == 403
    assert client.get(
        "/api/v2/exports/synthetic-812/checklist-evidence.csv",
        headers=counselor_headers,
    ).status_code == 403
    assert client.get("/api/settings", headers=counselor_headers).status_code == 403

    # Then: facility-scoped office manager reads/acts only after facility assignment, while viewer stays read-only.
    manager = client.get("/api/users", headers=admin_headers).json()
    manager_id = next(row["id"] for row in manager if row["username"] == "manager1")
    viewer_id = next(row["id"] for row in manager if row["username"] == "viewer1")
    assert client.put(f"/api/users/{manager_id}/facilities/{facility_id}", headers=admin_headers).status_code == 200
    assert client.put(f"/api/users/{viewer_id}/facilities/{facility_id}", headers=admin_headers).status_code == 200
    assert client.get("/api/v2/treatment-plans/synthetic-812", headers=manager_headers).status_code == 200
    assert client.get("/api/v2/treatment-plans/synthetic-812", headers=viewer_headers).status_code == 200
    assert client.get("/api/v2/exports/synthetic-812/checklist-evidence.csv", headers=manager_headers).status_code == 200
    assert client.get("/api/v2/exports/synthetic-812/checklist-evidence.csv", headers=viewer_headers).status_code == 403
    assert client.post("/api/v2/api-harness/jobs", headers=manager_headers, json={"job_type": "pull_all_treatment_plans_all_fields"}).status_code == 403
    assert client.get("/api/audit/logs", headers=manager_headers).status_code == 403
    assert client.get("/api/workflow-definitions", headers=manager_headers).status_code == 403

    # Then: denied actions are audited without patient names or credentials.
    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    assert any(item["outcome_status"] == "denied" for item in audit)
    assert "Synthetic office_manager" not in str(audit)
    assert "SyntheticActivePass456" not in str(audit)


def test_legacy_manager_is_migrated_but_rejected_by_new_api_boundary(tmp_path: Path, monkeypatch) -> None:
    # Given: a current application database.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: a legacy role is sent to the current API.
    rejected = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "legacy-manager",
            "full_name": "Synthetic Legacy Role",
            "role": "manager",
            "password": "SyntheticTemporaryPass123",
        },
    )

    # Then: the boundary rejects it and the database permits only canonical roles.
    assert rejected.status_code == 422
    from app.v2.db import engine

    with engine.connect() as connection:
        roles = {row[0] for row in connection.execute(text("SELECT DISTINCT role FROM users"))}
    assert roles <= {"admin", "office_manager", "counselor", "viewer"}


def test_every_active_route_is_classified_and_unknown_routes_fail_closed(tmp_path: Path, monkeypatch) -> None:
    # Given: the complete active V2 application route table.
    client = _fresh_client(tmp_path, monkeypatch)
    from app.main import create_app
    from app.v2.route_registry import assert_routes_classified

    # When/Then: current routes are exhaustive.
    assert_routes_classified(create_app())

    # Given: a future route without an explicit family.
    unclassified = FastAPI(docs_url=None, openapi_url=None, redoc_url=None)

    @unclassified.get("/api/future-sensitive-route")
    def future_route() -> dict[str, str]:
        return {"status": "unsafe"}

    # When/Then: startup rejects it by default.
    try:
        assert_routes_classified(unclassified)
    except RuntimeError as exc:
        assert str(exc) == "Unclassified API route is denied by default"
    else:
        raise AssertionError("unclassified route was not denied")
    assert client.get("/api/readiness").json()["checks"][0].get("path") is None


def test_non_admin_is_denied_across_configuration_harness_sync_audit_and_workflow_routes(tmp_path: Path, monkeypatch) -> None:
    # Given: an active viewer session.
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    _, viewer_headers = _create_user(client, admin_headers, "routeviewer", "viewer")
    probes = (
        ("GET", "/api/users", None),
        ("POST", "/api/users", {"username": "blocked", "full_name": "Blocked", "role": "viewer", "password": "SyntheticTemporaryPass123"}),
        ("PATCH", "/api/users/1", {"full_name": "Blocked"}),
        ("POST", "/api/users/1/reset-password", {"new_password": "SyntheticTemporaryPass123"}),
        ("GET", "/api/settings", None),
        ("PATCH", "/api/settings", {"organization_name": "Blocked"}),
        ("GET", "/api/api-configuration", None),
        ("PATCH", "/api/api-configuration", {}),
        ("POST", "/api/api-configuration/pull-definitions", None),
        ("POST", "/api/api-configuration/test-connectivity", None),
        ("POST", "/api/api-configuration/test-operation", {"path": "/health"}),
        ("POST", "/api/v2/api-harness/jobs", {"job_type": "pull_all_treatment_plans_all_fields"}),
        ("GET", "/api/v2/api-harness/jobs", None),
        ("GET", "/api/v2/api-harness/jobs/missing", None),
        ("POST", "/api/v2/api-harness/jobs/missing/cancel", None),
        ("GET", "/api/v2/api-harness/jobs/missing/artifacts", None),
        ("GET", "/api/v2/api-harness/jobs/missing/artifacts/missing", None),
        ("GET", "/api/v2/api-harness/jobs/missing/preview", None),
        ("POST", "/api/v2/alleva-sync/run", None),
        ("GET", "/api/v2/alleva-sync/jobs/missing", None),
        ("GET", "/api/audit/logs", None),
        ("GET", "/api/audit/verify", None),
        ("GET", "/api/workflow-definitions", None),
        ("POST", "/api/workflow-definitions", {"workflow_key": "blocked", "display_name": "Blocked"}),
        ("POST", "/api/workflow-definitions/1/versions/1/publish", None),
    )

    # When/Then: every admin-only route denies before resource lookup or execution.
    for method, path, body in probes:
        response = client.request(method, path, headers=viewer_headers, json=body)
        assert response.status_code == 403, (method, path, response.text)

    # Then: the denial family is recorded without request bodies.
    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    denied = [item for item in audit if item["action"] == "authorization.denied"]
    assert len(denied) >= len(probes)
    assert "SyntheticTemporaryPass123" not in str(denied)


def test_local_recovery_unlocks_admin_and_requires_password_change(tmp_path: Path, monkeypatch) -> None:
    # Given: a locked administrator.
    client = _fresh_client(tmp_path, monkeypatch)
    _auth_headers(client)
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "admin", "password": "IncorrectPass999"})

    # When: the local recovery boundary resets the account.
    from app.v2.local_admin_recovery import recover_local_admin

    recover_local_admin("SyntheticRecoveryPass789")
    recovered = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "SyntheticRecoveryPass789"},
    )

    # Then: access is restored only in password-change-required state and recovery is audited.
    assert recovered.status_code == 200
    assert recovered.json()["auth_state"] == "password_change_required"
    headers = {"Authorization": f"Bearer {recovered.json()['access_token']}"}
    assert client.get("/api/v2/dashboard", headers=headers).status_code == 403
    from app.v2.db import SessionLocal
    from app.v2.models import AuditLog

    with SessionLocal() as db:
        assert db.query(AuditLog).filter(AuditLog.action == "auth.local_admin.recovered").count() == 1


def test_self_password_change_invalidates_the_pre_rotation_bearer(tmp_path: Path, monkeypatch) -> None:
    # Given: the bootstrap administrator has a bearer issued for the temporary password.
    client = _fresh_client(tmp_path, monkeypatch)
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "StrongLocalPass1"},
    )
    assert login.status_code == 200
    stale_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # When: the administrator changes the password.
    changed = client.post(
        "/api/users/me/change-password",
        headers=stale_headers,
        json={"current_password": "StrongLocalPass1", "new_password": "SyntheticRotatedPass456"},
    )
    assert changed.status_code == 200

    # Then: the pre-rotation bearer is rejected and a fresh login works.
    assert client.get("/api/users/me", headers=stale_headers).status_code == 401
    fresh = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "SyntheticRotatedPass456"},
    )
    assert fresh.status_code == 200
    fresh_headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert client.get("/api/users/me", headers=fresh_headers).status_code == 200
    assert "password_changed_at" not in fresh.json()
    assert "password_hash" not in fresh.json()


def test_admin_reset_and_local_recovery_invalidate_pre_rotation_bearers(tmp_path: Path, monkeypatch) -> None:
    # Given: active administrator and viewer sessions.
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    viewer_id, viewer_headers = _create_user(client, admin_headers, "rotation-viewer", "viewer")

    # When: an administrator resets the viewer password without requiring another reset.
    reset = client.post(
        f"/api/users/{viewer_id}/reset-password",
        headers=admin_headers,
        json={"new_password": "SyntheticAdminReset789", "require_reset_on_login": False},
    )
    assert reset.status_code == 200

    # Then: the old viewer bearer is invalid and the reset credential obtains a valid session.
    assert client.get("/api/users/me", headers=viewer_headers).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": "rotation-viewer", "password": "SyntheticAdminReset789"},
    ).status_code == 200

    # When: the local recovery boundary replaces the administrator password.
    from app.v2.local_admin_recovery import recover_local_admin

    recover_local_admin("SyntheticRecoveryRotate8")

    # Then: the old admin bearer is invalid and only a fresh recovery login succeeds.
    assert client.get("/api/users/me", headers=admin_headers).status_code == 401
    recovered = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "SyntheticRecoveryRotate8"},
    )
    assert recovered.status_code == 200
    assert recovered.json()["auth_state"] == "password_change_required"


def test_startup_and_rule_setting_updates_trigger_all_version_reevaluation(tmp_path: Path, monkeypatch) -> None:
    # Given: an initialized application with injected reevaluation observers.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2 import db as db_module
    from app.v2.api import foundation_routes

    startup_triggers: list[str] = []
    setting_triggers: list[str] = []
    monkeypatch.setattr(db_module, "reevaluate_all_plan_versions", lambda _db, trigger: startup_triggers.append(trigger))
    monkeypatch.setattr(
        foundation_routes,
        "reevaluate_all_plan_versions",
        lambda _db, trigger: setting_triggers.append(trigger),
    )

    # When: startup runs, a non-rule setting changes, and then a rule setting changes.
    db_module.init_database()
    assert client.patch("/api/settings", headers=headers, json={"organization_name": "Synthetic Organization"}).status_code == 200
    assert client.patch("/api/settings", headers=headers, json={"treatment_plan_master_due_days": 31}).status_code == 200

    # Then: startup and rule-config triggers run exactly at their owned boundaries.
    assert startup_triggers == ["startup"]
    assert setting_triggers == ["rule_config"]
