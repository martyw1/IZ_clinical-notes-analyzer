from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.audit_template import AUDIT_TEMPLATE, AUDIT_TEMPLATE_BY_KEY, audit_sections
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import AuditItemResponse, AuditLog, Chart, ComplianceStatus, Role, User, WorkflowState, WorkflowTransition
from app.schemas.schemas import (
    AuditLogOut,
    AuditTemplateSectionOut,
    ChartCreate,
    ChartDetailOut,
    ChartSummaryOut,
    ChartUpdate,
    LoginInput,
    PasswordResetInput,
    Token,
    TransitionInput,
    UserCreate,
    UserOut,
)
from app.services.audit import log_event

router = APIRouter(prefix='/api')


def _allowed_transition(role: Role, current: WorkflowState, target: WorkflowState) -> bool:
    allowed = {
        Role.counselor: {
            WorkflowState.draft: [WorkflowState.submitted],
            WorkflowState.returned: [WorkflowState.submitted],
        },
        Role.admin: {
            WorkflowState.submitted: [WorkflowState.in_progress, WorkflowState.returned],
            WorkflowState.in_progress: [WorkflowState.completed, WorkflowState.returned],
            WorkflowState.completed: [WorkflowState.verified],
        },
        Role.manager: {
            WorkflowState.completed: [WorkflowState.verified],
            WorkflowState.submitted: [WorkflowState.in_progress],
        },
    }
    return target in allowed.get(role, {}).get(current, [])


def _chart_stmt():
    return select(Chart).options(selectinload(Chart.audit_responses), selectinload(Chart.counselor))


def _ensure_chart_access(chart: Chart | None, user: User) -> Chart:
    if not chart:
        raise HTTPException(status_code=404, detail='Chart not found')
    if user.role == Role.counselor and chart.counselor_id != user.id:
        raise HTTPException(status_code=403, detail='Cannot access this chart')
    return chart


def _find_chart(chart_id: int, user: User, db: Session) -> Chart:
    chart = db.execute(_chart_stmt().where(Chart.id == chart_id)).scalar_one_or_none()
    return _ensure_chart_access(chart, user)


def _ensure_all_responses(chart: Chart) -> None:
    existing = {response.item_key for response in chart.audit_responses}
    for template_item in AUDIT_TEMPLATE:
        if template_item['key'] in existing:
            continue
        chart.audit_responses.append(AuditItemResponse(item_key=template_item['key']))


def _status_counts(chart: Chart) -> dict[ComplianceStatus, int]:
    counts = {
        ComplianceStatus.pending: 0,
        ComplianceStatus.yes: 0,
        ComplianceStatus.no: 0,
        ComplianceStatus.na: 0,
    }
    for response in chart.audit_responses:
        counts[response.status] += 1
    return counts


def _chart_summary(chart: Chart) -> dict[str, object]:
    _ensure_all_responses(chart)
    counts = _status_counts(chart)
    return {
        'id': chart.id,
        'client_name': chart.client_name,
        'level_of_care': chart.level_of_care,
        'admission_date': chart.admission_date,
        'discharge_date': chart.discharge_date,
        'primary_clinician': chart.primary_clinician,
        'auditor_name': chart.auditor_name,
        'other_details': chart.other_details,
        'counselor_id': chart.counselor_id,
        'state': chart.state,
        'notes': chart.notes,
        'pending_items': counts[ComplianceStatus.pending],
        'passed_items': counts[ComplianceStatus.yes],
        'failed_items': counts[ComplianceStatus.no],
        'not_applicable_items': counts[ComplianceStatus.na],
    }


def _chart_detail(chart: Chart) -> dict[str, object]:
    summary = _chart_summary(chart)
    responses_by_key = {response.item_key: response for response in chart.audit_responses}
    checklist_items = []

    for template_item in AUDIT_TEMPLATE:
        response = responses_by_key.get(template_item['key'])
        checklist_items.append(
            {
                'item_key': template_item['key'],
                'step': template_item['step'],
                'section': template_item['section'],
                'label': template_item['label'],
                'timeframe': template_item['timeframe'],
                'instructions': template_item['instructions'],
                'evidence_hint': template_item['evidence_hint'],
                'policy_note': template_item['policy_note'],
                'status': response.status if response else ComplianceStatus.pending,
                'notes': response.notes if response else '',
                'evidence_location': response.evidence_location if response else '',
                'evidence_date': response.evidence_date if response else '',
                'expiration_date': response.expiration_date if response else '',
            }
        )

    return {**summary, 'checklist_items': checklist_items}


def _apply_chart_updates(chart: Chart, payload: ChartUpdate | ChartCreate, db: Session) -> None:
    chart.client_name = payload.client_name.strip()
    chart.level_of_care = payload.level_of_care.strip()
    chart.admission_date = payload.admission_date.strip()
    chart.discharge_date = payload.discharge_date.strip()
    chart.primary_clinician = payload.primary_clinician.strip()
    chart.auditor_name = payload.auditor_name.strip()
    chart.other_details = payload.other_details.strip()
    chart.notes = payload.notes.strip()

    if not isinstance(payload, ChartUpdate):
        return

    existing = {response.item_key: response for response in chart.audit_responses}
    seen_keys: set[str] = set()
    for item in payload.checklist_items:
        if item.item_key not in AUDIT_TEMPLATE_BY_KEY:
            raise HTTPException(status_code=400, detail=f'Unknown checklist item: {item.item_key}')
        response = existing.get(item.item_key)
        if not response:
            response = AuditItemResponse(item_key=item.item_key)
            chart.audit_responses.append(response)
            existing[item.item_key] = response
        response.status = item.status
        response.notes = item.notes.strip()
        response.evidence_location = item.evidence_location.strip()
        response.evidence_date = item.evidence_date.strip()
        response.expiration_date = item.expiration_date.strip()
        response.updated_at = datetime.now(timezone.utc)
        seen_keys.add(item.item_key)

    missing_keys = [template_item['key'] for template_item in AUDIT_TEMPLATE if template_item['key'] not in seen_keys]
    if missing_keys:
        raise HTTPException(status_code=400, detail=f'Missing checklist items: {", ".join(missing_keys)}')


@router.post('/auth/login', response_model=Token)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.is_locked = True
            db.commit()
        log_event(
            db,
            request,
            'auth.login.failed',
            event_category='authentication',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=payload.username,
            details={'username': payload.username},
            outcome_status='failure',
            severity='warning',
            http_status_code=401,
            message=f'Login failed for username {payload.username}.',
        )
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if user.is_locked:
        log_event(
            db,
            request,
            'auth.login.blocked',
            actor=user,
            event_category='authentication',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username},
            outcome_status='failure',
            severity='warning',
            http_status_code=403,
            message=f'Login blocked for locked account {user.username}.',
        )
        raise HTTPException(status_code=403, detail='Account locked')
    user.failed_login_attempts = 0
    db.commit()
    token = create_access_token(user.username)
    log_event(
        db,
        request,
        'auth.login.success',
        actor=user,
        event_category='authentication',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        http_status_code=200,
        message=f'Login succeeded for {user.username}.',
    )
    return Token(access_token=token, must_reset_password=user.must_reset_password)


@router.post('/auth/reset-password')
def reset_password(payload: PasswordResetInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    db.commit()
    log_event(
        db,
        request,
        'auth.password.reset',
        actor=user,
        event_category='authentication',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Password reset completed for {user.username}.',
    )
    return {'status': 'ok'}


@router.get('/users/me', response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    log_event(
        action='user.profile.read',
        actor=user,
        event_category='data_access',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Profile viewed for {user.username}.',
    )
    return user


@router.post('/users', response_model=UserOut)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.admin))):
    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail='Username exists')
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role, must_reset_password=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event(
        db,
        request,
        'user.create',
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username, 'role': user.role.value},
        message=f'User {user.username} created with role {user.role.value}.',
    )
    return user


@router.get('/audit-template', response_model=list[AuditTemplateSectionOut])
def get_audit_template(_: User = Depends(get_current_user)):
    log_event(
        action='audit.template.read',
        event_category='data_access',
        target_entity='audit_template',
        target_entity_type='template',
        details={'section_count': len(audit_sections())},
        message='Audit checklist template viewed.',
    )
    return audit_sections()


@router.get('/charts', response_model=list[ChartSummaryOut])
def list_charts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = _chart_stmt()
    if user.role == Role.counselor:
        stmt = stmt.where(Chart.counselor_id == user.id)
    charts = list(db.execute(stmt.order_by(Chart.id.desc())).scalars().unique().all())
    log_event(
        action='chart.list.read',
        actor=user,
        event_category='data_access',
        target_entity='chart_queue',
        target_entity_type='chart_queue',
        details={'count': len(charts)},
        message=f'Chart queue viewed by {user.username}.',
    )
    return [_chart_summary(chart) for chart in charts]


@router.post('/charts', response_model=ChartDetailOut)
def create_chart(payload: ChartCreate, request: Request, user: User = Depends(require_roles(Role.counselor, Role.admin)), db: Session = Depends(get_db)):
    chart = Chart(
        client_name='',
        level_of_care='',
        admission_date='',
        discharge_date='',
        primary_clinician='',
        auditor_name=payload.auditor_name.strip() or user.username,
        other_details='',
        counselor_id=user.id,
        notes='',
    )
    _apply_chart_updates(chart, payload, db)
    chart.auditor_name = chart.auditor_name or user.username
    _ensure_all_responses(chart)
    db.add(chart)
    db.commit()
    chart = _find_chart(chart.id, user, db)
    log_event(
        db,
        request,
        'chart.create',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        details={'state': chart.state.value, 'client_name': chart.client_name},
        message=f'Chart audit {chart.id} created by {user.username}.',
    )
    return _chart_detail(chart)


@router.get('/charts/{chart_id}', response_model=ChartDetailOut)
def get_chart(chart_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    log_event(
        action='chart.read',
        actor=user,
        event_category='data_access',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        details={'state': chart.state.value},
        message=f'Chart audit {chart.id} viewed by {user.username}.',
    )
    return _chart_detail(chart)


@router.put('/charts/{chart_id}', response_model=ChartDetailOut)
def update_chart(chart_id: int, payload: ChartUpdate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    _apply_chart_updates(chart, payload, db)
    db.commit()
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.update',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        details={'state': chart.state.value, 'client_name': chart.client_name},
        message=f'Chart audit {chart.id} updated by {user.username}.',
    )
    return _chart_detail(chart)


@router.post('/charts/{chart_id}/transition', response_model=ChartDetailOut)
def transition_chart(chart_id: int, payload: TransitionInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    if not _allowed_transition(user.role, chart.state, payload.to_state):
        raise HTTPException(status_code=400, detail='Invalid transition for role/state')
    if payload.to_state == WorkflowState.returned and not payload.comment.strip():
        raise HTTPException(status_code=400, detail='Comment required for returns')
    old = chart.state
    chart.state = payload.to_state
    db.add(WorkflowTransition(chart_id=chart.id, actor_id=user.id, from_state=old.value, to_state=payload.to_state.value, comment=payload.comment))
    db.commit()
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.transition',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        details={'from': old.value, 'to': payload.to_state.value, 'comment': payload.comment},
        message=f'Chart audit {chart.id} transitioned from {old.value} to {payload.to_state.value}.',
    )
    return _chart_detail(chart)


@router.post('/uploads')
def upload_files(request: Request, files: list[UploadFile] = File(...), user: User = Depends(require_roles(Role.counselor, Role.admin)), db: Session = Depends(get_db)):
    accepted = []
    for f in files:
        accepted.append({'filename': f.filename, 'content_type': f.content_type})
    log_event(
        db,
        request,
        'file.upload',
        actor=user,
        event_category='file_activity',
        target_entity='batch-upload',
        target_entity_type='upload_batch',
        details={'count': len(accepted), 'files': accepted},
        message=f'{len(accepted)} file(s) uploaded by {user.username}.',
    )
    return {'uploaded': accepted}


@router.get('/audit/logs', response_model=list[AuditLogOut])
def audit_logs(_: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    logs = list(db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(500)).scalars().all())
    log_event(
        action='audit.logs.read',
        event_category='forensic_access',
        target_entity='audit_logs',
        target_entity_type='audit_log',
        details={'count': len(logs)},
        message='Forensic audit log list viewed.',
    )
    return logs
