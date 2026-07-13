from __future__ import annotations

import csv
import io
import sqlite3

from test_v2_auth_rbac import _create_user
from test_v2_evaluation_persistence import PRIVACY_CANARY, _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_patient_roster_is_scoped_and_contains_no_patient_name_fields(tmp_path, monkeypatch) -> None:
    # Given: one patient with a current plan and one reconciled patient without a plan.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=_aggregate("roster-840").model_dump(mode="json"),
    )
    assert imported.status_code == 201
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        facility_id = database.execute("SELECT id FROM facilities WHERE facility_key='r3-default'").fetchone()[0]
        database.execute(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at) "
            "VALUES(?,?,'alleva_rest_api','inactive','2026-07-01T00:00:00+00:00','2026-07-12T00:00:00+00:00','2026-07-12T00:00:00+00:00')",
            (facility_id, "roster-841"),
        )
        database.commit()

    # When: an authorized administrator opens the roster.
    response = client.get("/api/v2/patient-roster", headers=headers)

    # Then: both authorized IDs appear, including the no-plan patient, with no name property or canary.
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["patient_id"] for item in items} == {"roster-840", "roster-841"}
    planned = next(item for item in items if item["patient_id"] == "roster-840")
    unplanned = next(item for item in items if item["patient_id"] == "roster-841")
    assert planned["treatment_plan_id"]
    assert planned["treatment_plan_status"]
    assert unplanned["treatment_plan_id"] == ""
    assert unplanned["treatment_plan_status"] == "No treatment plan"
    assert all("name" not in key for item in items for key in item)
    assert PRIVACY_CANARY not in response.text


def test_treatment_plan_list_export_is_manager_only_safe_and_audited(tmp_path, monkeypatch) -> None:
    # Given: a formula-like synthetic patient ID and both manager and counselor sessions.
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=admin_headers,
        json=_aggregate("=SYNTHETIC-842").model_dump(mode="json"),
    )
    assert imported.status_code == 201
    _, counselor_headers = _create_user(client, admin_headers, "roster-export-counselor", "counselor")

    # When: the manager exports the queue and a counselor attempts the same operation.
    exported = client.get("/api/v2/exports/treatment-plans.csv", headers=admin_headers)
    denied = client.get("/api/v2/exports/treatment-plans.csv", headers=counselor_headers)

    # Then: the CSV mirrors safe current queue fields, escapes formulas, and the denied role cannot export.
    assert exported.status_code == 200
    assert exported.headers["content-disposition"] == "attachment; filename=treatment-plans.csv"
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert list(rows[0]) == [
        "patient_id",
        "treatment_plan_id",
        "status",
        "current_level_of_care",
        "admission_date",
        "next_due_date",
        "source_mode",
        "missing_criteria_count",
        "returned_criteria_count",
    ]
    assert rows[0]["patient_id"] == "'=SYNTHETIC-842"
    assert rows[0]["treatment_plan_id"]
    assert rows[0]["status"]
    assert PRIVACY_CANARY not in exported.text
    assert denied.status_code == 403

    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    event = next(item for item in audit if item["action"] == "export.treatment_plan_list")
    assert event["details"] == {"treatment_plan_count": 1}
