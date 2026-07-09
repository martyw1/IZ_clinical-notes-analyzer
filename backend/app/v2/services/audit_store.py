from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.models import AuditLog, User

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

BLOCKED_DETAIL_FRAGMENTS = ("secret", "token", "authorization", "payload", "narrative", "client_name", "patient_name")


def redact_json(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if _is_blocked_key(key) else redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def record_audit_event(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    target_entity_type: str = "system",
    target_entity_id: str = "",
    outcome_status: str = "success",
    details: dict[str, JsonValue] | None = None,
) -> AuditLog:
    safe_details = redact_json(details or {})
    details_json = json.dumps(safe_details, sort_keys=True)
    prev_hash = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none() or ""
    event_id = uuid4().hex
    timestamp = datetime.now(timezone.utc)
    actor_id = str(actor.id) if actor else "system"
    actor_username = actor.username if actor else ""
    actor_role = actor.role if actor else "system"
    hash_payload = json.dumps(
        {
            "event_id": event_id,
            "timestamp_utc": timestamp.isoformat(),
            "actor_id": actor_id,
            "actor_username": actor_username,
            "actor_role": actor_role,
            "action": action,
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
            "outcome_status": outcome_status,
            "details_json": details_json,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
    )
    event_hash = hashlib.sha256(f"{prev_hash}|{hash_payload}".encode("utf-8")).hexdigest()
    row = AuditLog(
        event_id=event_id,
        timestamp_utc=timestamp,
        actor_id=actor_id,
        actor_username=actor_username,
        actor_role=actor_role,
        action=action,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        outcome_status=outcome_status,
        details_json=details_json,
        prev_hash=prev_hash,
        hash=event_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _is_blocked_key(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in BLOCKED_DETAIL_FRAGMENTS)


def _redact_text(value: str) -> str:
    lowered = value.lower()
    if any(fragment in lowered for fragment in ("secret", "bearer ", "password", "token")):
        return "[redacted]"
    return value
