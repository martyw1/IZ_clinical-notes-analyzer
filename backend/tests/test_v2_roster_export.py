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


def test_patient_roster_uses_newest_plan_when_patient_has_multiple_plans(tmp_path, monkeypatch) -> None:
    # Given: a patient whose older and newer treatment plans are both retained.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    base = _aggregate("roster-842")
    older = base.model_copy(update={
        "content_snapshot": base.content_snapshot.model_copy(update={"plan_id": "plan-older"}),
    })
    newer = base.model_copy(update={
        "current_level_of_care": "PHP",
        "content_snapshot": base.content_snapshot.model_copy(update={"plan_id": "plan-newer"}),
    })
    assert client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=older.model_dump(mode="json"),
    ).status_code == 201
    assert client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=newer.model_dump(mode="json"),
    ).status_code == 201

    # When: the patient roster is loaded.
    response = client.get("/api/v2/patient-roster", headers=headers)

    # Then: the single patient row summarizes the most recently imported plan.
    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "patient_id": "roster-842",
            "source_mode": "manual_upload",
            "lifecycle_state": "active",
            "current_level_of_care": "PHP",
            "treatment_plan_id": "plan-newer",
            "treatment_plan_status": response.json()["items"][0]["treatment_plan_status"],
            "first_seen_at": response.json()["items"][0]["first_seen_at"],
            "last_seen_at": response.json()["items"][0]["last_seen_at"],
            "reconciled_at": "",
        }
    ]


def test_patient_roster_keeps_same_patient_id_separate_by_source(tmp_path, monkeypatch) -> None:
    # Given: manual and Alleva records share a canonical patient ID but have distinct plans.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    manual = _aggregate("roster-843")
    manual = manual.model_copy(update={
        "content_snapshot": manual.content_snapshot.model_copy(update={"plan_id": "plan-shared"}),
    })
    assert client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=manual.model_dump(mode="json"),
    ).status_code == 201

    from app.v2.db import SessionLocal
    from app.v2.domain.schemas import TreatmentPlanAggregate
    from app.v2.models import User
    from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

    alleva_payload = manual.model_dump(mode="json")
    alleva_payload.update({"source_mode": "alleva_rest_api", "current_level_of_care": "RTC"})
    alleva_payload["content_snapshot"].update({"plan_id": "plan-shared", "source_mode": "alleva_rest_api"})
    alleva = TreatmentPlanAggregate.model_validate(alleva_payload)
    with SessionLocal() as database:
        actor = database.get(User, 1)
        assert actor is not None
        save_treatment_plan_aggregate(database, alleva, actor)

    # When: the roster is loaded.
    response = client.get("/api/v2/patient-roster", headers=headers)

    # Then: each source row retains its own newest plan and provenance.
    assert response.status_code == 200
    items = response.json()["items"]
    matching = {item["source_mode"]: item for item in items if item["patient_id"] == "roster-843"}
    assert matching["manual_upload"]["treatment_plan_id"] == "plan-shared"
    assert matching["alleva_rest_api"]["treatment_plan_id"] == "plan-shared"
    assert matching["manual_upload"]["current_level_of_care"] != "RTC"
    assert matching["alleva_rest_api"]["current_level_of_care"] == "RTC"
    manual_detail = client.get(
        "/api/v2/treatment-plans/roster-843/plan-shared?source_mode=manual_upload",
        headers=headers,
    )
    alleva_detail = client.get(
        "/api/v2/treatment-plans/roster-843/plan-shared?source_mode=alleva_rest_api",
        headers=headers,
    )
    assert manual_detail.status_code == 200 and manual_detail.json()["source_mode"] == "manual_upload"
    assert alleva_detail.status_code == 200 and alleva_detail.json()["source_mode"] == "alleva_rest_api"
    assert alleva_detail.json()["current_level_of_care"] == "RTC"
    from app.v2.services.evaluation_store import latest_plan_target
    from sqlalchemy import text

    with SessionLocal() as database:
        expected_ids = dict(database.execute(
            text(
                "SELECT v.source_system,v.id FROM treatment_plan_versions v "
                "JOIN patients p ON p.id=v.patient_id WHERE p.canonical_client_id=:patient_id"
            ),
            {"patient_id": "roster-843"},
        ).all())
        manual_target = latest_plan_target(database, "roster-843", "plan-shared", "manual_upload")
        alleva_target = latest_plan_target(database, "roster-843", "plan-shared", "alleva_rest_api")
    assert manual_target is not None and manual_target.plan_version_id == expected_ids["manual_upload"]
    assert alleva_target is not None and alleva_target.plan_version_id == expected_ids["alleva_rest_api"]


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
