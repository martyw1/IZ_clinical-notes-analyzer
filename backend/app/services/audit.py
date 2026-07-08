from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    timestamp: str
    actor_id: str
    actor_role: str
    action: str
    entity_type: str
    entity_reference: str
    outcome: str
    details: dict[str, JsonValue] = field(default_factory=dict)
    previous_hash: str = ""
    event_hash: str = ""


def _safe_details(details: dict[str, JsonValue]) -> dict[str, JsonValue]:
    blocked_fragments = ("secret", "token", "authorization", "payload", "narrative", "client_name", "patient_name")
    return {
        key: value
        for key, value in details.items()
        if not any(fragment in key.lower() for fragment in blocked_fragments)
    }


def _previous_hash(path: Path) -> str:
    if not path.exists():
        return ""
    last_line = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last_line = line
    if not last_line:
        return ""
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError:
        return ""
    value = payload.get("event_hash")
    return value if isinstance(value, str) else ""


def log_event(
    *,
    action: str,
    entity_type: str = "system",
    entity_reference: str = "v2",
    actor_id: str = "system",
    actor_role: str = "system",
    outcome: str = "success",
    details: dict[str, JsonValue] | None = None,
) -> AuditEvent:
    path = settings.audit_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    previous = _previous_hash(path)
    safe_details = _safe_details(details or {})
    event_id = hashlib.sha256(f"{timestamp}:{action}:{entity_reference}".encode("utf-8")).hexdigest()[:16]
    unsigned = AuditEvent(
        event_id=event_id,
        timestamp=timestamp,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_reference=entity_reference,
        outcome=outcome,
        details=safe_details,
        previous_hash=previous,
    )
    event_hash = hashlib.sha256(json.dumps(asdict(unsigned), sort_keys=True).encode("utf-8")).hexdigest()
    signed = AuditEvent(**{**asdict(unsigned), "event_hash": event_hash})
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(signed), sort_keys=True) + "\n")
    return signed
