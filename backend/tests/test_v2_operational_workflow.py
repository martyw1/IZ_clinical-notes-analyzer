from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from test_v2_evaluation_persistence import _aggregate, _database_path
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _import_synthetic_plan(client: TestClient, headers: dict[str, str], patient_id: str) -> None:
    response = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        headers=headers,
        data={"patient_id": patient_id},
        files={
            "file": (
                "synthetic-operational-workflow.txt",
                f"Patient ID: {patient_id}\nCurrent Level of Care: PHP\nIntervention: Synthetic operational workflow intervention.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201, response.text


def test_dashboard_reports_the_real_refresh_timestamp(tmp_path, monkeypatch) -> None:
    # Given: an authenticated manager and a normalized synthetic plan.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    _import_synthetic_plan(client, headers, "975")

    # When: the status dashboard is loaded.
    dashboard = client.get("/api/v2/dashboard", headers=headers)

    # Then: counts are scoped to the accessible patient and the response says when it was built.
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["metrics"] == {"overdue_plans": 0, "due_soon_plans": 0}
    assert any("excluded from deadline counts" in message for message in payload["blockers"])
    assert payload["refreshed_at"].endswith("+00:00")


def test_dashboard_counts_latest_plan_once_per_patient_record(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    aggregate = _aggregate("975")
    for plan_id in ("plan-975-initial", "plan-975-followup"):
        payload = aggregate.model_dump(mode="json")
        payload["content_snapshot"]["plan_id"] = plan_id
        imported = client.post(
            "/api/v2/manual-uploads/treatment-plan-aggregate",
            headers=headers,
            json=payload,
        )
        assert imported.status_code == 201

    dashboard = client.get("/api/v2/dashboard", headers=headers)

    assert dashboard.status_code == 200
    assert dashboard.json()["metrics"] == {"overdue_plans": 0, "due_soon_plans": 1}
    assert dashboard.json()["active_clients"] == 1

    roster = client.get("/api/v2/treatment-plan-roster", headers=headers)
    assert roster.status_code == 200
    rows = roster.json()["items"]
    assert len(rows) == 2
    due_soon = [row for row in rows if row["deadline_status"] == "Due Soon"]
    assert len(due_soon) == dashboard.json()["metrics"]["due_soon_plans"]
    selected = due_soon[0]
    detail = client.get(
        f"/api/v2/treatment-plans/975/{selected['treatment_plan_id']}",
        headers=headers,
        params={key: selected[key] for key in ("plan_version_id", "patient_record_id", "source_mode")},
    )
    assert detail.status_code == 200
    assert detail.json()["plan_version_id"] == selected["plan_version_id"]
    assert detail.json()["tracking_exclusion_reason"] == ""

    older = next(row for row in rows if row["plan_version_id"] != selected["plan_version_id"])
    older_detail = client.get(
        f"/api/v2/treatment-plans/975/{older['treatment_plan_id']}",
        headers=headers,
        params={key: older[key] for key in ("plan_version_id", "patient_record_id", "source_mode")},
    )
    assert older_detail.json()["tracking_exclusion_reason"] == "A different saved plan was selected for current tracking."

    with create_engine(f"sqlite:///{_database_path(tmp_path)}").begin() as connection:
        connection.execute(text("UPDATE patients SET lifecycle_state='discharged' WHERE id=:id"), {
            "id": selected["patient_record_id"],
        })
    discharged_dashboard = client.get("/api/v2/dashboard", headers=headers).json()
    assert discharged_dashboard["active_clients"] == 0
    assert discharged_dashboard["metrics"] == {"overdue_plans": 0, "due_soon_plans": 0}
    retained = client.get("/api/v2/treatment-plan-roster", headers=headers).json()["items"]
    assert {row["plan_version_id"] for row in retained} == {row["plan_version_id"] for row in rows}
    assert all(row["deadline_status"] == "Outside current tracking" for row in retained)
    assert all(row["tracking_exclusion_reason"] == "The patient record is marked discharged." for row in retained)
    discharged_detail = client.get(
        f"/api/v2/treatment-plans/975/{selected['treatment_plan_id']}",
        headers=headers,
        params={key: selected[key] for key in ("plan_version_id", "patient_record_id", "source_mode")},
    ).json()
    assert discharged_detail["deadline_status"] == "Outside current tracking"
    assert discharged_detail["tracking_exclusion_reason"] == "The patient record is marked discharged."
    assert discharged_detail["computed_deadline_status"] == detail.json()["computed_deadline_status"]

    from app.v2.db import SessionLocal
    from app.v2.services.patient_snapshot_store import PatientSourceSnapshotInput, persist_patient_source_snapshots

    with SessionLocal() as db:
        db.execute(text("UPDATE patients SET lifecycle_state='active' WHERE id=:id"), {"id": selected["patient_record_id"]})
        db.execute(text(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "SELECT facility_id,'SYNTHETIC-NO-PLAN',source_system,'active',first_seen_at,last_seen_at FROM patients WHERE id=:id"
        ), {"id": selected["patient_record_id"]})
        persist_patient_source_snapshots(db, (PatientSourceSnapshotInput(
            mrn="975", source_patient_id="SYNTHETIC-975", source_system="manual_upload",
            source_last_updated="2026-09-04T12:00:00Z", record={"currentLevelOfCare": "Case Management"},
            patient_record_id=selected["patient_record_id"],
        ),), "2026-09-04T12:00:00Z")
        db.commit()
    case_management_dashboard = client.get("/api/v2/dashboard", headers=headers).json()
    assert case_management_dashboard["active_clients"] == 1
    assert case_management_dashboard["metrics"] == {"overdue_plans": 0, "due_soon_plans": 0}
    patients = client.get("/api/v2/patient-roster", headers=headers).json()["items"]
    assert next(row for row in patients if row["mrn"] == "975")["current_level_of_care"] == "Case Management"
    assert next(row for row in patients if row["mrn"] == "SYNTHETIC-NO-PLAN")["treatment_plans"] == []
    case_management_roster = client.get("/api/v2/treatment-plan-roster", headers=headers).json()["items"]
    assert all(row["tracking_exclusion_reason"] == "Patient in Case Management, no next due date" for row in case_management_roster)
    case_management_detail = client.get(
        f"/api/v2/treatment-plans/975/{selected['treatment_plan_id']}",
        headers=headers,
        params={key: selected[key] for key in ("plan_version_id", "patient_record_id", "source_mode")},
    ).json()
    assert case_management_detail["computed_deadline_status"] == "Patient in Case Management, no next due date"


def test_case_management_has_no_recurring_schedule(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _aggregate("SYNTHETIC-CM").model_dump(mode="json")
    payload["current_level_of_care"] = "Case Management"
    imported = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=payload)
    assert imported.status_code == 201
    row, = client.get("/api/v2/treatment-plan-roster", headers=headers).json()["items"]
    assert row["deadline_status"] == "Patient in Case Management, no next due date"
    detail = client.get(
        f"/api/v2/treatment-plans/SYNTHETIC-CM/{row['treatment_plan_id']}",
        headers=headers,
        params={key: row[key] for key in ("plan_version_id", "patient_record_id", "source_mode")},
    ).json()
    assert detail["computed_deadline_status"] == "Patient in Case Management, no next due date"
    assert detail["date_clock_due_date"] == "Unknown"


def test_manager_action_rolls_back_when_its_audit_event_cannot_be_written(tmp_path, monkeypatch) -> None:
    # Given: a plan and a recorder that fails before the request is committed.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    _import_synthetic_plan(client, headers, "976")

    def fail_audit(*_args, **_kwargs) -> None:
        raise RuntimeError("synthetic audit write failure")

    monkeypatch.setattr("app.v2.api.runtime_routes.record_audit_event", fail_audit)

    # When: the manager tries to save an override disposition.
    with pytest.raises(RuntimeError, match="synthetic audit write failure"):
        client.post(
            "/api/v2/treatment-plans/976/manager-actions",
            headers=headers,
            json={
                "criterion_id": "confirm_current_loc",
                "action": "override",
                "comment": "Synthetic manager override.",
                "override_reason": "Synthetic verification reason.",
            },
        )

    # Then: neither the manager disposition nor a correction work item persisted without its audit event.
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        action_count = db.execute(
            text(
                "SELECT COUNT(*) FROM treatment_plan_manager_actions WHERE patient_id='976'"
            )
        ).scalar_one()
    assert action_count == 0


def test_image_only_pdf_is_rejected_without_deterministic_text_evidence(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(pdf)

    response = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        headers=headers,
        data={"patient_id": "977"},
        files={"file": ("synthetic-image-only.pdf", pdf.getvalue(), "application/pdf")},
    )

    assert response.status_code == 400
    assert "extractable text" in response.json()["detail"]


def test_concurrent_audit_events_keep_a_verifiable_hash_chain(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    _auth_headers(client)
    from app.v2.db import SessionLocal
    from app.v2.services.audit_store import record_audit_event, verify_audit_chain

    def record_synthetic_event(index: int) -> None:
        with SessionLocal() as db:
            record_audit_event(
                db,
                action="synthetic.concurrent.audit",
                target_entity_type="verification",
                target_entity_id=str(index),
            )

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(record_synthetic_event, range(6)))

    with SessionLocal() as db:
        valid, event_count, failing_event_id = verify_audit_chain(db)
        concurrent_event_count = db.execute(
            text("SELECT COUNT(*) FROM audit_logs WHERE action='synthetic.concurrent.audit'")
        ).scalar_one()
    assert valid is True
    assert failing_event_id is None
    assert concurrent_event_count == 6
    assert event_count >= concurrent_event_count


def test_audit_event_writes_to_established_details_column(tmp_path) -> None:
    # Given: the established Windows audit table stores JSON in the physical `details` column.
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-audit.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE audit_logs("
                "id INTEGER PRIMARY KEY,event_id TEXT UNIQUE NOT NULL,timestamp_utc TEXT NOT NULL,"
                "actor_id TEXT,actor_username TEXT,actor_role TEXT,action TEXT NOT NULL,"
                "target_entity_type TEXT,target_entity_id TEXT,outcome_status TEXT NOT NULL,"
                "details TEXT NOT NULL DEFAULT '{}',prev_hash TEXT,hash TEXT NOT NULL)"
            )
        )

    # When: the V2 audit recorder writes the event used by the login route.
    from app.v2.services.audit_store import record_audit_event

    with Session(engine) as session:
        record_audit_event(
            session,
            action="auth.login.success",
            target_entity_type="user",
            target_entity_id="1",
        )

    # Then: the event is stored through the established physical column.
    with engine.connect() as connection:
        assert connection.execute(text("SELECT details FROM audit_logs")).scalar_one() == "{}"


def test_synthetic_primary_counselors_preserve_identity_and_unresolved_assignments(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    from app.v2.db import SessionLocal
    from app.v2.models import ImportedCounselor
    from app.v2.services.imported_counselors import PrimaryCounselorEvidence, save_primary_counselor
    from sqlalchemy import func, select

    headers = _auth_headers(client)
    for patient in ("SYNTHETIC-STAFF-A", "SYNTHETIC-STAFF-B"):
        response = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers,
                               json=_aggregate(patient).model_dump(mode="json"))
        assert response.status_code == 201

    def roster():
        response = client.get("/api/v2/patient-roster", headers=headers)
        assert response.status_code == 200
        return {row["mrn"]: row for row in response.json()["items"]}

    patient_a = roster()["SYNTHETIC-STAFF-A"]["patient_record_id"]
    patient_b = roster()["SYNTHETIC-STAFF-B"]["patient_record_id"]
    stamp = "2026-10-01T12:00:00Z"
    first = PrimaryCounselorEvidence("synthetic:facility", "staff-a", "Synthetic Counselor")
    second = PrimaryCounselorEvidence("synthetic:facility", "staff-b", "Synthetic Counselor")
    with SessionLocal() as db:
        save_primary_counselor(db, patient_a, first, stamp)
        save_primary_counselor(db, patient_a, first, stamp)
        save_primary_counselor(db, patient_b, second, stamp)
        db.commit()
        assert db.scalar(select(func.count()).select_from(ImportedCounselor)) == 2

    rows = roster()
    a, b = rows["SYNTHETIC-STAFF-A"], rows["SYNTHETIC-STAFF-B"]
    assert a["primary_counselor_name"] == b["primary_counselor_name"] == "Synthetic Counselor"
    assert a["primary_counselor_id"] != b["primary_counselor_id"]
    assert a["tracking_eligible"] and b["tracking_eligible"]

    with SessionLocal() as db:
        save_primary_counselor(db, patient_a, PrimaryCounselorEvidence(first.source_scope, "", ""), "2026-10-02T12:00:00Z")
        save_primary_counselor(db, patient_a, first, stamp)
        db.commit()
        assert db.scalar(select(func.count()).select_from(ImportedCounselor)) == 2
    assert roster()["SYNTHETIC-STAFF-A"]["primary_counselor_id"] is None
    directory = client.get("/api/v2/patient-roster", headers=headers).json()["counselors"]
    assert {row["id"] for row in directory} == {a["primary_counselor_id"], b["primary_counselor_id"]}
    # A lightweight directory must not evaluate every saved plan or bypass patient access.
    from app.v2.api import roster_routes
    monkeypatch.setattr(roster_routes, "list_patient_roster", lambda *args: (_ for _ in ()).throw(AssertionError("heavy roster called")))
    response = client.get("/api/v2/clinicians", headers=headers)
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["items"]} == {a["primary_counselor_id"], b["primary_counselor_id"]}
    assert response.json()["master_directory_connected"] is False
    assert client.get("/api/v2/clinicians").status_code == 401
    monkeypatch.setattr(roster_routes, "accessible_patient_record_ids", lambda *args: frozenset())
    assert client.get("/api/v2/clinicians", headers=headers).json()["items"] == []
