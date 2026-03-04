import hashlib
import json
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import AuditLog, User


def _compute_hash(payload: str, prev_hash: str | None) -> str:
    base = f'{prev_hash or "GENESIS"}|{payload}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def log_event(
    db: Session,
    request: Request,
    action: str,
    actor: User | None = None,
    target_entity: str | None = None,
    details: dict[str, Any] | None = None,
    outcome_status: str = 'success',
    severity: str = 'info',
) -> None:
    request_id = request.headers.get('x-request-id', 'no-request-id')
    source_ip = request.client.host if request.client else None
    user_agent = request.headers.get('user-agent')
    details_json = json.dumps(details or {}, default=str)

    prev_hash = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    event_payload = json.dumps(
        {
            'request_id': request_id,
            'action': action,
            'target_entity': target_entity,
            'details': details or {},
            'outcome_status': outcome_status,
            'severity': severity,
        },
        sort_keys=True,
        default=str,
    )
    event_hash = _compute_hash(event_payload, prev_hash)

    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_username=actor.username if actor else None,
            actor_role=actor.role.value if actor else None,
            source_ip=source_ip,
            user_agent=user_agent,
            request_id=request_id,
            action=action,
            target_entity=target_entity,
            details=details_json,
            outcome_status=outcome_status,
            severity=severity,
            prev_hash=prev_hash,
            hash=event_hash,
        )
    )
    db.commit()
