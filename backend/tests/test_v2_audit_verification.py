from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from io import StringIO

from sqlalchemy import insert

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_audit_csv_exports_full_rolling_window_with_structured_details(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2.db import SessionLocal
    from app.v2.models import AuditLog

    now = datetime.now(timezone.utc)
    nested = {"results": [{"label": 'Synthetic, "quoted" café', "matched": True}]}
    events = [
        {
            "event_id": f"synthetic-{index}",
            "timestamp_utc": now - timedelta(hours=hours),
            "actor_id": "synthetic-actor",
            "actor_username": " =1+1",
            "action": "synthetic.event",
            "details_json": json.dumps({**nested, "access_token": "synthetic-secret"}),
            "hash": "synthetic-hash",
        }
        for index, hours in enumerate([25, -1] + [23] * 505 + [11])
    ]
    with SessionLocal() as db:
        db.execute(insert(AuditLog), events)
        db.commit()

    assert client.get("/api/audit/logs.csv").status_code == 401
    response = client.get("/api/audit/logs.csv", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "no-store"
    assert 'attachment; filename="forensic-logs-' in response.headers["content-disposition"]
    reader = csv.DictReader(StringIO(response.text))
    rows = {row["event_id"]: row for row in reader}
    assert set(rows).intersection(event["event_id"] for event in events) == {
        event["event_id"] for event in events[2:]
    }
    sample = rows["synthetic-2"]
    assert sample["actor_id"] == "synthetic-actor"
    assert sample["actor_username"] == "' =1+1"
    assert datetime.fromisoformat(sample["timestamp_utc"]) == now - timedelta(hours=23)
    assert json.loads(sample["details"]) == {**nested, "access_token": "[redacted]"}

    synthetic_ids = {event["event_id"] for event in events}
    for scope, expected in (("12h", {events[-1]["event_id"]}), ("all", synthetic_ids)):
        scoped = client.get("/api/audit/logs.csv", params={"scope": scope}, headers=headers)
        assert scoped.status_code == 200
        assert f'filename="forensic-logs-{scope}-' in scoped.headers["content-disposition"]
        exported_ids = {row["event_id"] for row in csv.DictReader(StringIO(scoped.text))}
        assert exported_ids & synthetic_ids == expected


def test_admin_can_verify_the_persisted_audit_hash_chain(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    verification = client.get("/api/audit/verify", headers=headers)
    assert verification.status_code == 200
    assert verification.json()["valid"] is True
    assert verification.json()["event_count"] >= 1
    assert verification.json()["first_invalid_id"] is None
    assert verification.json()["privacy_mode"] == "redacted_minimum_necessary"
    assert verification.json()["retention_hook"] == "local_policy_required"


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
