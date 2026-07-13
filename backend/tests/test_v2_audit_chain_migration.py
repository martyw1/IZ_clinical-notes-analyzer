from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.v2.db import Base
from app.v2.models import AuditLog
from app.v2.services.audit_store import (
    _event_hash,
    _timestamp_for_hash,
    record_audit_event,
    verify_audit_chain_details,
)


def _legacy_marker_columns(db) -> None:
    statements = (
        "ALTER TABLE audit_logs ADD COLUMN request_id TEXT NOT NULL DEFAULT 'no-request-id'",
        "ALTER TABLE audit_logs ADD COLUMN correlation_id TEXT NOT NULL DEFAULT 'no-correlation-id'",
        "ALTER TABLE audit_logs ADD COLUMN event_category TEXT NOT NULL DEFAULT 'application'",
        "ALTER TABLE audit_logs ADD COLUMN message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE audit_logs ADD COLUMN severity TEXT NOT NULL DEFAULT 'info'",
        "ALTER TABLE audit_logs ADD COLUMN cef_payload TEXT NOT NULL DEFAULT ''",
    )
    for statement in statements:
        db.execute(text(statement))


def test_migrated_legacy_prefix_is_reported_without_rewriting_history() -> None:
    # Given: a retained legacy event is followed by a current-format audit event.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        legacy = AuditLog(
            event_id="legacy-event",
            timestamp_utc=datetime.now(timezone.utc),
            actor_id="system",
            actor_username="",
            actor_role="system",
            action="legacy.event",
            target_entity_type="system",
            target_entity_id="",
            outcome_status="success",
            details_json="{}",
            prev_hash="",
            hash="legacy-retained-hash",
        )
        db.add(legacy)
        db.commit()
        _legacy_marker_columns(db)
        db.execute(
            text(
                "UPDATE audit_logs SET request_id='legacy-request', correlation_id='legacy-correlation', "
                "event_category='http_request', message='legacy message', cef_payload='legacy-cef' WHERE id=:id"
            ),
            {"id": legacy.id},
        )
        db.commit()

        # When: the active-format verifier checks the mixed history.
        record_audit_event(db, action="current.event")
        result = verify_audit_chain_details(db)

        # Then: it verifies the active segment and reports the retained legacy scope honestly.
        assert result.valid is True
        assert result.event_count == 2
        assert result.verified_event_count == 1
        assert result.legacy_event_count == 1
        assert result.verification_scope == "current_format_only"
        assert db.get(AuditLog, legacy.id).hash == "legacy-retained-hash"


def test_current_hash_normalizes_integer_actor_ids_from_migrated_sqlite() -> None:
    # Given: SQLite returns a legacy INTEGER actor column as an integer.
    timestamp = datetime.now(timezone.utc)
    row = AuditLog(
        event_id="current-event",
        timestamp_utc=timestamp,
        actor_id=1,
        actor_username="admin",
        actor_role="admin",
        action="current.event",
        target_entity_type="system",
        target_entity_id="",
        outcome_status="success",
        details_json="{}",
        prev_hash="",
        hash="",
    )
    payload = json.dumps(
        {
            "event_id": row.event_id,
            "timestamp_utc": _timestamp_for_hash(timestamp),
            "actor_id": "1",
            "actor_username": row.actor_username,
            "actor_role": row.actor_role,
            "action": row.action,
            "target_entity_type": row.target_entity_type,
            "target_entity_id": row.target_entity_id,
            "outcome_status": row.outcome_status,
            "details_json": row.details_json,
            "prev_hash": "",
        },
        sort_keys=True,
    )

    # When: the current-format hash is recomputed from the migrated row.
    actual = _event_hash(row, "")

    # Then: the value matches the original string actor representation used at write time.
    assert actual == hashlib.sha256(f"|{payload}".encode("utf-8")).hexdigest()
