from __future__ import annotations

import sqlite3

import pytest

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _database_path(tmp_path) -> str:
    return str(tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3")


def test_api_configuration_rolls_back_when_required_audit_insert_fails(tmp_path, monkeypatch) -> None:
    # Given: a configured local database and an audit writer that cannot persist the required event.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    import app.v2.api.configuration_routes as configuration_routes

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("synthetic audit storage failure")

    monkeypatch.setattr(configuration_routes, "record_audit_event", fail_audit)

    # When: an administrator changes security-sensitive saved connection configuration.
    with pytest.raises(RuntimeError, match="synthetic audit storage failure"):
        client.patch(
            "/api/api-configuration",
            headers=headers,
            json={"api_base_url": "https://synthetic-changed.invalid"},
        )

    # Then: the configuration mutation was not committed without its tamper-evident audit event.
    with sqlite3.connect(_database_path(tmp_path)) as database:
        saved_url = database.execute("SELECT api_base_url FROM app_settings").fetchone()[0]
    assert saved_url != "https://synthetic-changed.invalid"


def test_facility_assignment_rolls_back_when_required_audit_insert_fails(tmp_path, monkeypatch) -> None:
    # Given: an administrator, a synthetic user, and an audit writer that cannot persist the assignment event.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-audit-counselor",
            "full_name": "Synthetic Audit Counselor",
            "role": "counselor",
            "password": "SyntheticTemporaryPass123",
        },
    )
    assert created.status_code == 200
    facilities = client.get("/api/facilities", headers=headers)
    assert facilities.status_code == 200
    facility_id = facilities.json()[0]["id"]

    import app.v2.api.access_admin_routes as access_admin_routes

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("synthetic audit storage failure")

    monkeypatch.setattr(access_admin_routes, "record_audit_event", fail_audit)

    # When: the administrator assigns the user to a facility.
    with pytest.raises(RuntimeError, match="synthetic audit storage failure"):
        client.put(f"/api/users/{created.json()['id']}/facilities/{facility_id}", headers=headers)

    # Then: the assignment was not committed without its required audit record.
    with sqlite3.connect(_database_path(tmp_path)) as database:
        count = database.execute(
            "SELECT COUNT(*) FROM user_facilities WHERE user_id=? AND facility_id=?",
            (created.json()["id"], facility_id),
        ).fetchone()[0]
    assert count == 0
