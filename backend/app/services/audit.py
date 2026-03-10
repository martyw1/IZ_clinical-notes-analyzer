from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.models import AppSetting, AuditItemResponse, AuditLog, Chart, PatientNoteDocument, PatientNoteSet, User, WorkflowTransition

logger = logging.getLogger(__name__)

DEFAULT_DEVICE_VENDOR = 'OpenAI'
DEFAULT_DEVICE_PRODUCT = 'IZ Clinical Notes Analyzer'
DEFAULT_DEVICE_VERSION = '1'
FALLBACK_LOG_PATH = Path(__file__).resolve().parents[3] / 'logs' / 'forensic-audit-fallback.jsonl'
TRACKED_MODELS = (User, AppSetting, Chart, WorkflowTransition, AuditItemResponse, PatientNoteSet, PatientNoteDocument)
SENSITIVE_FIELDS: dict[str, set[str]] = {
    'User': {'password_hash'},
    'AppSetting': {'llm_api_key', 'access_reputation_api_key'},
}
_audit_context_var: ContextVar['AuditContext | None'] = ContextVar('audit_context', default=None)


@dataclass(frozen=True)
class AuditContext:
    request_id: str
    correlation_id: str
    actor_id: int | None = None
    actor_username: str | None = None
    actor_role: str | None = None
    actor_type: str = 'human'
    source_ip: str | None = None
    forwarded_for: str | None = None
    source_host: str | None = None
    source_port: int | None = None
    user_agent: str | None = None
    http_method: str | None = None
    request_path: str | None = None
    route_template: str | None = None
    query_string: str | None = None
    session_id: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=_serialize_scalar)


def _escape_cef(value: Any) -> str:
    text = '' if value is None else str(value)
    return text.replace('\\', '\\\\').replace('|', '\\|').replace('=', '\\=').replace('\n', '\\n').replace('\r', '')


def _first_forwarded_ip(header_value: str | None) -> str | None:
    if not header_value:
        return None
    return header_value.split(',')[0].strip() or None


def _extract_request_context(request: Request | None = None) -> AuditContext:
    if request is None:
        existing = _audit_context_var.get()
        if existing:
            return existing
        generated_id = uuid4().hex
        return AuditContext(request_id=generated_id, correlation_id=generated_id, actor_type='system')

    request_id = request.headers.get('x-request-id') or uuid4().hex
    correlation_id = request.headers.get('x-correlation-id') or request_id
    forwarded_for = request.headers.get('x-forwarded-for')
    source_ip = _first_forwarded_ip(forwarded_for) or request.headers.get('x-real-ip')
    if not source_ip and request.client:
        source_ip = request.client.host

    route = request.scope.get('route')
    route_template = getattr(route, 'path', None)
    return AuditContext(
        request_id=request_id,
        correlation_id=correlation_id,
        actor_type='human',
        source_ip=source_ip,
        forwarded_for=forwarded_for,
        source_host=request.headers.get('host'),
        source_port=request.client.port if request.client else None,
        user_agent=request.headers.get('user-agent'),
        http_method=request.method,
        request_path=request.url.path,
        route_template=route_template,
        query_string=request.url.query or None,
        session_id=request.headers.get('x-session-id'),
    )


def current_audit_context() -> AuditContext:
    existing = _audit_context_var.get()
    if existing:
        return existing
    generated_id = uuid4().hex
    return AuditContext(request_id=generated_id, correlation_id=generated_id, actor_type='system')


def bind_request_context(request: Request) -> Token:
    context = _extract_request_context(request)
    request.state.request_id = context.request_id
    request.state.correlation_id = context.correlation_id
    request.state.audit_actor = None
    return _audit_context_var.set(context)


def refresh_request_context(request: Request) -> None:
    current = current_audit_context()
    refreshed = _extract_request_context(request)
    _audit_context_var.set(
        replace(
            refreshed,
            actor_id=current.actor_id,
            actor_username=current.actor_username,
            actor_role=current.actor_role,
            actor_type=current.actor_type,
        )
    )
    request.state.request_id = refreshed.request_id
    request.state.correlation_id = refreshed.correlation_id


@contextmanager
def system_audit_context(
    *,
    actor_username: str = 'system',
    actor_role: str = 'system',
    source_ip: str | None = '127.0.0.1',
) -> Any:
    generated_id = uuid4().hex
    token = _audit_context_var.set(
        AuditContext(
            request_id=generated_id,
            correlation_id=generated_id,
            actor_username=actor_username,
            actor_role=actor_role,
            actor_type='system',
            source_ip=source_ip,
            source_host='localhost',
        )
    )
    try:
        yield
    finally:
        _audit_context_var.reset(token)


def reset_audit_context(token: Token) -> None:
    _audit_context_var.reset(token)


def set_actor_context(user: User, request: Request | None = None) -> None:
    current = _extract_request_context(request)
    updated = replace(
        current,
        actor_id=user.id,
        actor_username=user.username,
        actor_role=user.role.value,
        actor_type='human',
    )
    _audit_context_var.set(updated)
    if request is not None:
        request.state.audit_actor = user
        request.state.request_id = updated.request_id
        request.state.correlation_id = updated.correlation_id


def attach_audit_context(session: Session) -> None:
    if session.info.get('audit_context'):
        return
    session.info['audit_context'] = asdict(current_audit_context())


def refresh_session_audit_context(session: Session) -> None:
    session.info['audit_context'] = asdict(current_audit_context())


def _get_audit_context_from_session(session: Session) -> dict[str, Any]:
    attach_audit_context(session)
    return dict(session.info.get('audit_context') or {})


def _tracked_instance(instance: Any) -> bool:
    return isinstance(instance, TRACKED_MODELS) and not isinstance(instance, AuditLog)


def _snapshot_instance(instance: Any, *, use_previous_values: bool = False) -> dict[str, Any]:
    state = inspect(instance)
    snapshot: dict[str, Any] = {}
    hidden_fields = SENSITIVE_FIELDS.get(instance.__class__.__name__, set())
    for column in state.mapper.column_attrs:
        key = column.key
        if key in hidden_fields:
            continue
        value = getattr(instance, key, None)
        if use_previous_values:
            history = state.attrs[key].history
            if history.has_changes():
                if history.deleted:
                    value = history.deleted[0]
                elif key in state.committed_state:
                    value = state.committed_state[key]
        snapshot[key] = _serialize_scalar(value)
    return snapshot


def _diff_state(before_state: dict[str, Any] | None, after_state: dict[str, Any] | None) -> dict[str, Any]:
    before_state = before_state or {}
    after_state = after_state or {}
    diff: dict[str, Any] = {}
    keys = sorted(set(before_state) | set(after_state))
    for key in keys:
        before_value = before_state.get(key)
        after_value = after_state.get(key)
        if before_value != after_value:
            diff[key] = {'before': before_value, 'after': after_value}
    return diff


def _entity_type(instance: Any) -> str:
    return instance.__class__.__name__.lower()


def _entity_id_from_snapshot(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    identifier = snapshot.get('id')
    return None if identifier is None else str(identifier)


def _target_entity(entity_type: str, entity_id: str | None) -> str:
    return entity_type if not entity_id else f'{entity_type}:{entity_id}'


def _message_for_action(action: str, target_entity: str | None, outcome_status: str) -> str:
    entity = target_entity or 'application'
    return f'{action} on {entity} ({outcome_status})'


def _cef_severity(severity: str) -> int:
    return {
        'debug': 2,
        'info': 3,
        'notice': 4,
        'warning': 6,
        'error': 8,
        'critical': 10,
    }.get(severity, 5)


def _cef_extension(record: dict[str, Any]) -> str:
    parts = {
        'rt': _serialize_scalar(record['timestamp_utc']),
        'requestMethod': record.get('http_method'),
        'request': record.get('request_path'),
        'src': record.get('source_ip'),
        'dhost': record.get('source_host'),
        'suser': record.get('actor_username'),
        'outcome': record.get('outcome_status'),
        'msg': record.get('message'),
        'cs1Label': 'requestId',
        'cs1': record.get('request_id'),
        'cs2Label': 'correlationId',
        'cs2': record.get('correlation_id'),
        'cs3Label': 'targetEntity',
        'cs3': record.get('target_entity'),
        'cs4Label': 'patientId',
        'cs4': record.get('patient_id'),
        'deviceCustomString1Label': 'eventCategory',
        'deviceCustomString1': record.get('event_category'),
    }
    return ' '.join(f'{key}={_escape_cef(value)}' for key, value in parts.items() if value not in (None, ''))


def _fhir_action(action: str) -> str:
    if action.endswith('create') or action.endswith('insert.commit'):
        return 'C'
    if action.endswith('update') or action.endswith('update.commit'):
        return 'U'
    if action.endswith('delete') or action.endswith('delete.commit'):
        return 'D'
    if action.endswith('read') or action.endswith('list') or action.startswith('http.request'):
        return 'R'
    if action.endswith('login') or action.endswith('transition') or action.startswith('system.'):
        return 'E'
    return 'E'


def _fhir_outcome(outcome_status: str) -> str:
    return {
        'success': '0',
        'failure': '4',
        'rolled_back': '8',
    }.get(outcome_status, '12')


def _build_fhir_audit_event(record: dict[str, Any]) -> dict[str, Any]:
    entity: list[dict[str, Any]] = []
    if record.get('target_entity'):
        entity.append(
            {
                'name': record['target_entity'],
                'detail': [
                    {'type': 'beforeState', 'valueString': record['before_state'] or ''},
                    {'type': 'afterState', 'valueString': record['after_state'] or ''},
                    {'type': 'diffState', 'valueString': record['diff_state'] or ''},
                ],
            }
        )
    if record.get('patient_id'):
        entity.append({'name': f"patient:{record['patient_id']}"})

    return {
        'resourceType': 'AuditEvent',
        'id': record['event_id'],
        'type': {'code': record['event_category'], 'display': record['action']},
        'action': _fhir_action(record['action']),
        'recorded': _serialize_scalar(record['timestamp_utc']),
        'outcome': _fhir_outcome(record['outcome_status']),
        'outcomeDesc': record['message'],
        'agent': [
            {
                'requestor': record.get('actor_type') == 'human',
                'type': {'text': record.get('actor_type') or 'system'},
                'who': {'display': record.get('actor_username') or 'system'},
                'role': [{'text': record.get('actor_role') or 'system'}],
                'network': {'address': record.get('source_ip') or '', 'type': '2'},
            }
        ],
        'source': {'observer': {'display': settings.app_name}},
        'entity': entity,
    }


def _build_record(
    *,
    action: str,
    event_category: str,
    outcome_status: str = 'success',
    severity: str = 'info',
    target_entity: str | None = None,
    target_entity_type: str | None = None,
    target_entity_id: str | None = None,
    patient_id: str | None = None,
    details: dict[str, Any] | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    diff_state: dict[str, Any] | None = None,
    message: str | None = None,
    http_status_code: int | None = None,
    context: AuditContext | None = None,
) -> dict[str, Any]:
    current = context or current_audit_context()
    timestamp = _utc_now()
    record: dict[str, Any] = {
        'event_id': uuid4().hex,
        'timestamp_utc': timestamp,
        'actor_id': current.actor_id,
        'actor_username': current.actor_username,
        'actor_role': current.actor_role,
        'actor_type': current.actor_type,
        'source_ip': current.source_ip,
        'forwarded_for': current.forwarded_for,
        'source_host': current.source_host,
        'source_port': current.source_port,
        'user_agent': current.user_agent,
        'request_id': current.request_id,
        'correlation_id': current.correlation_id,
        'session_id': current.session_id,
        'http_method': current.http_method,
        'request_path': current.request_path,
        'route_template': current.route_template,
        'query_string': current.query_string,
        'http_status_code': http_status_code,
        'event_category': event_category,
        'action': action,
        'target_entity': target_entity,
        'target_entity_type': target_entity_type,
        'target_entity_id': target_entity_id,
        'patient_id': patient_id,
        'message': message or _message_for_action(action, target_entity, outcome_status),
        'details': _canonical_json(details or {}),
        'before_state': _canonical_json(before_state) if before_state is not None else None,
        'after_state': _canonical_json(after_state) if after_state is not None else None,
        'diff_state': _canonical_json(diff_state) if diff_state is not None else None,
        'outcome_status': outcome_status,
        'severity': severity,
        'cef_version': 0,
        'cef_device_vendor': DEFAULT_DEVICE_VENDOR,
        'cef_device_product': DEFAULT_DEVICE_PRODUCT,
        'cef_device_version': DEFAULT_DEVICE_VERSION,
        'cef_signature_id': action,
        'cef_name': action.replace('.', ' ').title(),
        'cef_severity': _cef_severity(severity),
        'cef_extension': '',
        'cef_payload': '',
        'fhir_audit_event': '',
    }
    record['cef_extension'] = _cef_extension(record)
    record['cef_payload'] = (
        f"CEF:{record['cef_version']}|{_escape_cef(record['cef_device_vendor'])}|"
        f"{_escape_cef(record['cef_device_product'])}|{_escape_cef(record['cef_device_version'])}|"
        f"{_escape_cef(record['cef_signature_id'])}|{_escape_cef(record['cef_name'])}|"
        f"{record['cef_severity']}|{record['cef_extension']}"
    )
    record['fhir_audit_event'] = _canonical_json(_build_fhir_audit_event(record))
    return record


def _compute_hash(payload: str, prev_hash: str | None) -> str:
    base = f'{prev_hash or "GENESIS"}|{payload}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def _write_fallback_records(records: list[dict[str, Any]], exc: Exception) -> None:
    FALLBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FALLBACK_LOG_PATH.open('a', encoding='utf-8') as handle:
        for record in records:
            payload = dict(record)
            payload['fallback_error'] = str(exc)
            payload['fallback_timestamp_utc'] = _serialize_scalar(_utc_now())
            handle.write(_canonical_json(payload))
            handle.write('\n')


def _persist_records(records: list[dict[str, Any]]) -> None:
    if not records:
        return

    db: Session | None = None
    try:
        from app.db.session import SessionLocal

        db = SessionLocal()
        db.info['skip_forensic_audit'] = True
        prev_hash = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
        for record in records:
            event_payload = _canonical_json({key: value for key, value in record.items() if key != 'hash'})
            event_hash = _compute_hash(event_payload, prev_hash)
            db.add(AuditLog(**record, prev_hash=prev_hash, hash=event_hash))
            prev_hash = event_hash
        db.commit()
    except Exception as exc:  # pragma: no cover - exercised indirectly in failure conditions
        logger.exception('Forensic audit persistence failed: %s', exc)
        _write_fallback_records(records, exc)
        if db is not None:
            db.rollback()
    finally:
        if db is not None:
            db.close()


def log_event(
    db: Session | None = None,
    request: Request | None = None,
    action: str = 'application.event',
    actor: User | None = None,
    target_entity: str | None = None,
    target_entity_type: str | None = None,
    target_entity_id: str | None = None,
    patient_id: str | None = None,
    details: dict[str, Any] | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    diff_state: dict[str, Any] | None = None,
    outcome_status: str = 'success',
    severity: str = 'info',
    event_category: str = 'application',
    message: str | None = None,
    http_status_code: int | None = None,
) -> None:
    if actor is not None:
        set_actor_context(actor, request)
    context = _extract_request_context(request) if request is not None else current_audit_context()
    if actor is not None:
        context = replace(context, actor_id=actor.id, actor_username=actor.username, actor_role=actor.role.value, actor_type='human')
    _persist_records(
        [
            _build_record(
                action=action,
                event_category=event_category,
                outcome_status=outcome_status,
                severity=severity,
                target_entity=target_entity,
                target_entity_type=target_entity_type,
                target_entity_id=target_entity_id,
                patient_id=patient_id,
                details=details,
                before_state=before_state,
                after_state=after_state,
                diff_state=diff_state,
                message=message,
                http_status_code=http_status_code,
                context=context,
            )
        ]
    )


def log_request_completed(request: Request, *, status_code: int, duration_ms: float, severity: str = 'info') -> None:
    actor = getattr(request.state, 'audit_actor', None)
    log_event(
        request=request,
        actor=actor,
        action='http.request.completed',
        event_category='http_request',
        outcome_status='success' if status_code < 400 else 'failure',
        severity='warning' if status_code >= 400 else severity,
        target_entity=request.url.path,
        target_entity_type='http_request',
        target_entity_id=getattr(request.state, 'request_id', None),
        details={'duration_ms': round(duration_ms, 3), 'status_code': status_code},
        message=f'HTTP {request.method} {request.url.path} completed with status {status_code}',
        http_status_code=status_code,
    )


def log_unhandled_exception(request: Request, exc: Exception, *, duration_ms: float) -> None:
    actor = getattr(request.state, 'audit_actor', None)
    log_event(
        request=request,
        actor=actor,
        action='http.request.exception',
        event_category='http_request',
        outcome_status='failure',
        severity='error',
        target_entity=request.url.path,
        target_entity_type='http_request',
        target_entity_id=getattr(request.state, 'request_id', None),
        details={'duration_ms': round(duration_ms, 3), 'exception_type': exc.__class__.__name__, 'exception_message': str(exc)},
        message=f'Unhandled exception during {request.method} {request.url.path}: {exc.__class__.__name__}',
        http_status_code=500,
    )


def _data_event_context(session: Session) -> AuditContext:
    context_dict = _get_audit_context_from_session(session)
    return AuditContext(**context_dict)


def _queue_data_event(
    session: Session,
    *,
    action: str,
    instance: Any,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    diff_state: dict[str, Any] | None,
    outcome_status: str,
) -> None:
    entity_type = _entity_type(instance)
    entity_id = _entity_id_from_snapshot(after_state) or _entity_id_from_snapshot(before_state)
    patient_id = None
    if after_state and 'patient_id' in after_state:
        patient_id = after_state.get('patient_id')
    elif before_state and 'patient_id' in before_state:
        patient_id = before_state.get('patient_id')
    record = _build_record(
        action=action,
        event_category='data_change',
        outcome_status=outcome_status,
        severity='warning' if outcome_status != 'success' else 'info',
        target_entity=_target_entity(entity_type, entity_id),
        target_entity_type=entity_type,
        target_entity_id=entity_id,
        patient_id=patient_id if isinstance(patient_id, str) else None,
        details={'table': getattr(instance, '__tablename__', entity_type)},
        before_state=before_state,
        after_state=after_state,
        diff_state=diff_state,
        message=f'{action} recorded for {_target_entity(entity_type, entity_id)}',
        context=_data_event_context(session),
    )
    session.info.setdefault('audit_pending_records', []).append(record)


def register_session_audit_events(session_factory: sessionmaker) -> None:
    @event.listens_for(session_factory, 'before_flush')
    def before_flush(session: Session, flush_context: Any, instances: Any) -> None:
        if session.info.get('skip_forensic_audit'):
            return
        attach_audit_context(session)
        preimages = session.info.setdefault('audit_preimages', {})
        for instance in list(session.dirty) + list(session.deleted):
            if not _tracked_instance(instance):
                continue
            key = id(instance)
            if key not in preimages:
                preimages[key] = _snapshot_instance(instance, use_previous_values=True)

    @event.listens_for(session_factory, 'after_flush')
    def after_flush(session: Session, flush_context: Any) -> None:
        if session.info.get('skip_forensic_audit'):
            return

        preimages: dict[int, dict[str, Any]] = session.info.setdefault('audit_preimages', {})
        for instance in session.new:
            if not _tracked_instance(instance):
                continue
            after_state = _snapshot_instance(instance)
            _queue_data_event(
                session,
                action='data.insert.commit',
                instance=instance,
                before_state=None,
                after_state=after_state,
                diff_state=after_state,
                outcome_status='success',
            )

        for instance in session.dirty:
            if instance in session.deleted or not _tracked_instance(instance):
                continue
            if not session.is_modified(instance, include_collections=False):
                continue
            before_state = preimages.get(id(instance)) or _snapshot_instance(instance, use_previous_values=True)
            after_state = _snapshot_instance(instance)
            diff_state = _diff_state(before_state, after_state)
            if not diff_state:
                continue
            _queue_data_event(
                session,
                action='data.update.commit',
                instance=instance,
                before_state=before_state,
                after_state=after_state,
                diff_state=diff_state,
                outcome_status='success',
            )

        for instance in session.deleted:
            if not _tracked_instance(instance):
                continue
            before_state = preimages.get(id(instance)) or _snapshot_instance(instance, use_previous_values=True)
            _queue_data_event(
                session,
                action='data.delete.commit',
                instance=instance,
                before_state=before_state,
                after_state=None,
                diff_state=before_state,
                outcome_status='success',
            )

    @event.listens_for(session_factory, 'after_commit')
    def after_commit(session: Session) -> None:
        if session.info.get('skip_forensic_audit'):
            return
        pending = list(session.info.pop('audit_pending_records', []))
        session.info.pop('audit_preimages', None)
        _persist_records(pending)

    @event.listens_for(session_factory, 'after_rollback')
    def after_rollback(session: Session) -> None:
        if session.info.get('skip_forensic_audit'):
            return
        pending = list(session.info.pop('audit_pending_records', []))
        session.info.pop('audit_preimages', None)
        if not pending:
            return
        rolled_back = []
        for record in pending:
            updated = dict(record)
            updated['action'] = record['action'].replace('.commit', '.rollback')
            updated['outcome_status'] = 'rolled_back'
            updated['severity'] = 'warning'
            updated['cef_signature_id'] = updated['action']
            updated['cef_name'] = updated['action'].replace('.', ' ').title()
            updated['cef_severity'] = _cef_severity(updated['severity'])
            updated['message'] = record['message'].replace('recorded', 'rolled back')
            updated['cef_extension'] = _cef_extension(updated)
            updated['cef_payload'] = (
                f"CEF:{updated['cef_version']}|{_escape_cef(updated['cef_device_vendor'])}|"
                f"{_escape_cef(updated['cef_device_product'])}|{_escape_cef(updated['cef_device_version'])}|"
                f"{_escape_cef(updated['cef_signature_id'])}|{_escape_cef(updated['cef_name'])}|"
                f"{updated['cef_severity']}|{updated['cef_extension']}"
            )
            updated['fhir_audit_event'] = _canonical_json(_build_fhir_audit_event(updated))
            rolled_back.append(updated)
        _persist_records(rolled_back)
