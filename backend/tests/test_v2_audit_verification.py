from __future__ import annotations

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_admin_can_verify_the_persisted_audit_hash_chain(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    verification = client.get("/api/audit/verify", headers=headers)
    assert verification.status_code == 200
    assert verification.json()["valid"] is True
    assert verification.json()["event_count"] >= 1
    assert verification.json()["first_invalid_id"] is None


def test_audit_verification_identifies_the_first_modified_record(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2.db import SessionLocal
    from app.v2.models import AuditLog

    with SessionLocal() as db:
        first_event = db.query(AuditLog).order_by(AuditLog.id.asc()).first()
        assert first_event is not None
        first_event_id = first_event.id
        first_event.action = "tampered.action"
        db.commit()

    verification = client.get("/api/audit/verify", headers=headers)
    assert verification.status_code == 200
    assert verification.json()["valid"] is False
    assert verification.json()["first_invalid_id"] == first_event_id
