from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from sqlalchemy import inspect as sqlalchemy_inspect, select, text
from sqlalchemy.orm import Session

from app.v2.models import AuditLog, User

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

BLOCKED_DETAIL_FRAGMENTS = ("secret", "token", "authorization", "payload", "narrative", "client_name", "patient_name")
AUDIT_PRIVACY_MODE = "redacted_minimum_necessary"
AUDIT_RETENTION_HOOK = "local_policy_required"
_AUDIT_CHAIN_LOCK = RLock()


@dataclass(frozen=True, slots=True)
class AuditChainVerification:
    valid: bool
    event_count: int
    verified_event_count: int
    legacy_event_count: int
    first_invalid_id: int | None

    @property
    def verification_scope(self) -> str:
        return "all_events" if self.legacy_event_count == 0 else "current_format_only"


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
    commit: bool = True,
) -> AuditLog:
    with _AUDIT_CHAIN_LOCK:
        return _record_audit_event(
            db,
            action=action,
            actor=actor,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            outcome_status=outcome_status,
            details=details,
            commit=commit,
        )


def _record_audit_event(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    target_entity_type: str = "system",
    target_entity_id: str = "",
    outcome_status: str = "success",
    details: dict[str, JsonValue] | None = None,
    commit: bool = True,
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
            "timestamp_utc": _timestamp_for_hash(timestamp),
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
    db.flush()
    if commit:
        db.commit()
        db.refresh(row)
    return row


def verify_audit_chain(db: Session) -> tuple[bool, int, int | None]:
    result = verify_audit_chain_details(db)
    return result.valid, result.event_count, result.first_invalid_id


def verify_audit_chain_details(db: Session) -> AuditChainVerification:
    with _AUDIT_CHAIN_LOCK:
        rows = db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
        current_start = _current_format_start(db, rows)
        previous_hash = (rows[current_start - 1].hash or "") if current_start > 0 else ""
        for row in rows[current_start:]:
            expected = _event_hash(row, previous_hash)
            if (row.prev_hash or "") != previous_hash or row.hash != expected:
                return AuditChainVerification(
                    valid=False,
                    event_count=len(rows),
                    verified_event_count=len(rows) - current_start,
                    legacy_event_count=current_start,
                    first_invalid_id=row.id,
                )
            previous_hash = row.hash or ""
        return AuditChainVerification(
            valid=True,
            event_count=len(rows),
            verified_event_count=len(rows) - current_start,
            legacy_event_count=current_start,
            first_invalid_id=None,
        )


def audit_policy_metadata() -> tuple[str, str]:
    return AUDIT_PRIVACY_MODE, AUDIT_RETENTION_HOOK


def _is_blocked_key(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in BLOCKED_DETAIL_FRAGMENTS)


def _redact_text(value: str) -> str:
    lowered = value.lower()
    if any(fragment in lowered for fragment in ("secret", "bearer ", "password", "token")):
        return "[redacted]"
    return value


def _event_hash(row: AuditLog, previous_hash: str) -> str:
    hash_payload = json.dumps(
        {
            "event_id": row.event_id,
            "timestamp_utc": _timestamp_for_hash(row.timestamp_utc),
            "actor_id": str(row.actor_id),
            "actor_username": row.actor_username,
            "actor_role": row.actor_role,
            "action": row.action,
            "target_entity_type": row.target_entity_type,
            "target_entity_id": row.target_entity_id,
            "outcome_status": row.outcome_status,
            "details_json": row.details_json,
            "prev_hash": previous_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(f"{previous_hash}|{hash_payload}".encode("utf-8")).hexdigest()


def _current_format_start(db: Session, rows: list[AuditLog]) -> int:
    marker_columns = {
        "request_id",
        "correlation_id",
        "event_category",
        "message",
        "severity",
        "cef_payload",
    }
    bind = db.get_bind()
    available_columns = {column["name"] for column in sqlalchemy_inspect(bind).get_columns("audit_logs")}
    if not marker_columns.issubset(available_columns):
        return 0
    markers = db.execute(
        text(
            "SELECT id,request_id,correlation_id,event_category,message,severity,cef_payload "
            "FROM audit_logs ORDER BY id ASC"
        )
    ).mappings().all()
    start = len(markers)
    while start > 0 and _is_current_format_marker(markers[start - 1]):
        start -= 1
    return min(start, len(rows))


def _is_current_format_marker(row: Mapping[str, object]) -> bool:
    return (
        str(row.get("request_id") or "") in {"", "no-request-id"}
        and str(row.get("correlation_id") or "") in {"", "no-correlation-id"}
        and str(row.get("event_category") or "") in {"", "application"}
        and not str(row.get("message") or "")
        and str(row.get("severity") or "") in {"", "info"}
        and not str(row.get("cef_payload") or "")
    )


def _timestamp_for_hash(timestamp: datetime) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)
    return timestamp.isoformat()
