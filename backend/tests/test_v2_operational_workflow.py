from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

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
    assert payload["metrics"]["active_patient_ids"] == 1
    assert payload["refreshed_at"].endswith("+00:00")


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
