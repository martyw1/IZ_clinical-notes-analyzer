from __future__ import annotations

import csv
import sys
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient


def _fresh_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "StrongLocalPass1")
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "test-secret-key-for-v2-manual-upload")
    monkeypatch.setenv("IZ_CNA_DATA_ENCRYPTION_KEY", "test-data-encryption-key-for-v2-manual-upload")
    for module_name in tuple(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)
    from app.main import create_app

    return TestClient(create_app())


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _manual_aggregate_payload(patient_id: str) -> dict:
    from app.v2.services.sample_data import treatment_plan_aggregate

    aggregate = treatment_plan_aggregate()
    snapshot = aggregate.content_snapshot.model_copy(update={"patient_id": patient_id, "source_mode": "manual_upload"})
    coverage = aggregate.evidence_coverage_summary.model_copy(update={"patient_id": patient_id})
    manual = aggregate.model_copy(
        update={
            "patient_id": patient_id,
            "patient_display_label": f"Patient ID {patient_id}",
            "source_mode": "manual_upload",
            "current_level_of_care": "PHP",
            "mapped_level_of_care": "PHP",
            "admission_date": "2026-06-01",
            "date_clock_due_date": "2026-07-15",
            "overall_status": "Needs Review",
            "content_snapshot": snapshot,
            "evidence_coverage_summary": coverage,
        }
    )
    return manual.model_dump(mode="json")


def test_treatment_plan_queue_is_empty_until_manual_aggregate_is_imported(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    empty_queue = client.get("/api/v2/treatment-plans", headers=headers)
    missing_detail = client.get("/api/v2/treatment-plans/812", headers=headers)

    assert empty_queue.status_code == 200
    assert empty_queue.json()["items"] == []
    assert missing_detail.status_code == 404


def test_manual_aggregate_upload_is_encrypted_persisted_and_returned_after_restart(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _manual_aggregate_payload("812")

    imported = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", json=payload, headers=headers)

    assert imported.status_code == 201
    assert imported.json()["patient_id"] == "812"
    assert imported.json()["source_mode"] == "manual_upload"

    queue = client.get("/api/v2/treatment-plans", headers=headers)
    assert queue.json()["items"][0]["patient_id"] == "812"
    assert queue.json()["items"][0]["source_mode"] == "manual_upload"

    detail = client.get("/api/v2/treatment-plans/812", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["source_mode"] == "manual_upload"
    assert len(detail.json()["criteria_results"]) == 42

    from sqlalchemy import select

    from app.v2.db import SessionLocal
    from app.v2.models import TreatmentPlanImport

    with SessionLocal() as db:
        stored = db.execute(select(TreatmentPlanImport).where(TreatmentPlanImport.patient_id == "812")).scalar_one()
        assert stored.encrypted_payload.startswith("enc:v1:")
        assert "Patient ID 812" not in stored.encrypted_payload

    client.close()
    restarted = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _auth_headers(restarted)
    restarted_queue = restarted.get("/api/v2/treatment-plans", headers=restarted_headers)

    assert restarted_queue.status_code == 200
    assert restarted_queue.json()["items"][0]["patient_id"] == "812"


def test_manager_actions_persist_audit_and_reload_in_treatment_plan_detail(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _manual_aggregate_payload("812")
    import_response = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", json=payload, headers=headers)
    assert import_response.status_code == 201

    saved = client.post(
        "/api/v2/treatment-plans/812/manager-actions",
        json={
            "criterion_id": "confirm_current_level_of_care",
            "action": "override",
            "comment": "Accepted after source review.",
            "override_reason": "Signed plan and LOC evidence match imported record.",
        },
        headers=headers,
    )

    assert saved.status_code == 200
    assert saved.json()["status"] == "saved"

    detail = client.get("/api/v2/treatment-plans/812", headers=headers)
    assert detail.status_code == 200
    reviews = detail.json()["manager_reviews"]
    assert any(
        review["criterion_id"] == "confirm_current_level_of_care"
        and review["action"] == "override"
        and review["manager_status"] == "Override"
        and review["override_reason"] == "Signed plan and LOC evidence match imported record."
        for review in reviews
    )
    assert any(
        override["criterion_id"] == "confirm_current_level_of_care"
        and override["override_reason"] == "Signed plan and LOC evidence match imported record."
        for override in detail.json()["overrides"]
    )

    audit = client.get("/api/audit/logs", headers=headers)
    assert audit.status_code == 200
    assert any(item["action"] == "manager.criterion.override" for item in audit.json()["items"])

    client.close()
    restarted = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _auth_headers(restarted)
    restarted_detail = restarted.get("/api/v2/treatment-plans/812", headers=restarted_headers)

    assert restarted_detail.status_code == 200
    assert any(
        review["criterion_id"] == "confirm_current_level_of_care"
        and review["actor_username"] == "admin"
        and review["override_reason"] == "Signed plan and LOC evidence match imported record."
        for review in restarted_detail.json()["manager_reviews"]
    )


def test_checklist_export_escapes_csv_and_neutralizes_spreadsheet_formulas(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _manual_aggregate_payload("812")
    first_criterion = payload["criteria_results"][0]
    first_criterion["finding_message"] = '=SUM(1,1), "quoted"\nsecond line'
    first_criterion["source_json_paths"] = ["client.plan,field"]
    first_criterion["evidence_refs"][0]["safe_preview"] = "+spreadsheet formula"
    imported = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", json=payload, headers=headers)
    assert imported.status_code == 201

    export = client.get("/api/v2/exports/812/checklist-evidence.csv", headers=headers)

    assert export.status_code == 200
    rows = list(csv.reader(StringIO(export.text)))
    assert rows[0] == ["criterion", "status", "finding", "source_path", "safe_preview", "manager_action"]
    assert rows[1][2] == '\'=SUM(1,1), "quoted"\nsecond line'
    assert rows[1][3] == "client.plan,field"
    assert rows[1][4] == "'+spreadsheet formula"


def test_manual_text_file_upload_parses_normalizes_encrypts_and_queues(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    file_text = "\n".join(
        (
            "Patient ID: 914",
            "Current Level of Care: PHP",
            "Admission Date: 2026-06-02",
            "Next Due Date: 2026-07-02",
            "Reason for Admission: Synthetic clinical rationale from uploaded text.",
            "Initial Client Needs: Stabilization and relapse prevention.",
            "Family Education Needs: Family education reviewed.",
            "Problem: Recovery stabilization requires continued support.",
            "Diagnosis: F10.20 Synthetic alcohol use disorder",
            "Behavioral Definition: Cravings increase relapse risk.",
            "Goal: Maintain recovery stability.",
            "Objective: Identify three coping skills.",
            "Intervention: Weekly CBT skills practice.",
            "Signature Date: 2026-06-03T10:00:00-04:00",
        )
    )

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={"file": ("synthetic-treatment-plan.txt", file_text, "text/plain")},
        headers=headers,
    )

    assert imported.status_code == 201
    assert imported.json()["patient_id"] == "914"
    assert imported.json()["criteria_total"] == 42

    detail = client.get("/api/v2/treatment-plans/914", headers=headers)
    assert detail.status_code == 200
    snapshot = detail.json()["content_snapshot"]
    assert snapshot["reason_for_admission"] == "Synthetic clinical rationale from uploaded text."
    assert snapshot["problems"][0]["goals"][0]["objectives"][0]["interventions"][0]["intervention_description"] == "Weekly CBT skills practice."
    assert any(criterion["result_status"] == "Compliant" for criterion in detail.json()["criteria_results"])

    from sqlalchemy import select

    from app.v2.db import SessionLocal
    from app.v2.models import TreatmentPlanImport

    with SessionLocal() as db:
        stored = db.execute(select(TreatmentPlanImport).where(TreatmentPlanImport.patient_id == "914")).scalar_one()
        assert stored.encrypted_payload.startswith("enc:v1:")
        assert "Weekly CBT skills practice" not in stored.encrypted_payload


def test_manual_tsv_file_upload_uses_patient_id_fallback(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    tsv_text = "\t".join(("current_level_of_care", "admission_date", "intervention_description")) + "\n" + "\t".join(("IOP", "2026-06-05", "Practice refusal skills."))

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "915"},
        files={"file": ("manual-treatment-plan.tsv", tsv_text, "text/tab-separated-values")},
        headers=headers,
    )

    assert imported.status_code == 201
    assert imported.json()["patient_id"] == "915"
    queue = client.get("/api/v2/treatment-plans", headers=headers)
    assert queue.json()["items"][0]["patient_id"] == "915"
