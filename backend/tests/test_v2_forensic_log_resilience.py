from __future__ import annotations

from datetime import datetime, timezone

from app.v2.api.configuration_routes import _audit_item
from app.v2.models import AuditLog


def test_forensic_log_item_survives_malformed_legacy_details() -> None:
    row = AuditLog(
        event_id=99,
        timestamp_utc=datetime.now(timezone.utc),
        actor_id=7,
        actor_username="",
        actor_role="system",
        action="synthetic.legacy.event",
        target_entity_type="system",
        target_entity_id="",
        outcome_status="success",
        details_json="legacy-not-json",
        prev_hash="",
        hash="synthetic-hash",
    )

    item = _audit_item(row)

    assert item.action == "synthetic.legacy.event"
    assert item.event_id == "99"
    assert item.actor_id == "7"
    assert item.details == {}


def test_forensic_log_item_accepts_nested_redacted_json_details() -> None:
    row = AuditLog(
        event_id="nested-synthetic-event",
        timestamp_utc=datetime.now(timezone.utc),
        actor_id="system",
        actor_username="",
        actor_role="system",
        action="synthetic.nested.event",
        target_entity_type="system",
        target_entity_id="",
        outcome_status="success",
        details_json='{"sections":[{"key":"documents","fields":["status","count"]}]}',
        prev_hash="",
        hash="synthetic-hash",
    )

    item = _audit_item(row)

    assert item.details == {"sections": [{"key": "documents", "fields": ["status", "count"]}]}
