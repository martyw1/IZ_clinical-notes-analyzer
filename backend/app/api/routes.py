from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.audit_template import AUDIT_TEMPLATE, AUDIT_TEMPLATE_BY_KEY, audit_sections
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import (
    AppSetting,
    AuditItemResponse,
    AuditLog,
    Chart,
    ComplianceStatus,
    NoteSetStatus,
    NoteSetUploadMode,
    PatientNoteDocument,
    PatientNoteSet,
    Role,
    User,
    WorkflowState,
    WorkflowTransition,
)
from app.schemas.schemas import (
    AppSettingsOut,
    AppSettingsUpdate,
    AuditLogOut,
    AuditTemplateSectionOut,
    ChartCreate,
    ChartDetailOut,
    ChartSummaryOut,
    ChartUpdate,
    LoginInput,
    PasswordResetInput,
    PatientIdDetectionOut,
    PatientNoteDocumentUploadInput,
    PatientNoteSetDetailOut,
    PatientNoteSetSummaryOut,
    Token,
    TransitionInput,
    UserCreate,
    UserOut,
    UserPasswordChangeInput,
    UserPasswordResetAdmin,
    UserSelfUpdate,
    UserUpdate,
)
from app.services.audit import log_event
from app.services.app_settings import app_settings_public_payload, get_or_create_app_settings, touch_app_settings
from app.services.access_intel import lookup_access_intel
from app.services.evaluation import apply_report_to_chart, generate_evaluation_report
from app.services.patient_notes import detect_patient_id_from_uploads, remove_stored_paths, resolve_storage_path, store_upload_file

router = APIRouter(prefix='/api')
NOTE_SET_ROLES = (Role.admin, Role.counselor, Role.manager)
REVIEW_ROLES = (Role.admin, Role.manager)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_bootstrap_admin(user: User) -> bool:
    return user.username == settings.bootstrap_admin_username


def _allowed_transition(role: Role, current: WorkflowState, target: WorkflowState) -> bool:
    allowed = {
        Role.admin: {
            WorkflowState.draft: [WorkflowState.awaiting_manager_review],
            WorkflowState.awaiting_manager_review: [WorkflowState.manager_approved, WorkflowState.manager_rejected],
            WorkflowState.manager_rejected: [WorkflowState.awaiting_manager_review],
        },
        Role.manager: {
            WorkflowState.awaiting_manager_review: [WorkflowState.manager_approved, WorkflowState.manager_rejected],
        },
    }
    return target in allowed.get(role, {}).get(current, [])


def _chart_stmt():
    return select(Chart).options(
        selectinload(Chart.audit_responses),
        selectinload(Chart.counselor),
        selectinload(Chart.source_note_set),
        selectinload(Chart.reviewed_by),
    )


def _note_set_stmt():
    return select(PatientNoteSet).options(
        selectinload(PatientNoteSet.documents),
        selectinload(PatientNoteSet.uploaded_by),
        selectinload(PatientNoteSet.review_charts),
    )


def _ensure_chart_access(chart: Chart | None, user: User) -> Chart:
    if not chart:
        raise HTTPException(status_code=404, detail='Chart not found')
    if user.role == Role.counselor and chart.counselor_id != user.id:
        raise HTTPException(status_code=403, detail='Cannot access this chart')
    return chart


def _find_chart(chart_id: int, user: User, db: Session) -> Chart:
    chart = db.execute(_chart_stmt().where(Chart.id == chart_id)).scalar_one_or_none()
    return _ensure_chart_access(chart, user)


def _ensure_note_set_access(note_set: PatientNoteSet | None, user: User) -> PatientNoteSet:
    if not note_set:
        raise HTTPException(status_code=404, detail='Patient note set not found')
    if user.role == Role.counselor and note_set.uploaded_by_id != user.id:
        raise HTTPException(status_code=403, detail='Cannot access this patient note set')
    return note_set


def _find_note_set(note_set_id: int, user: User, db: Session) -> PatientNoteSet:
    note_set = db.execute(_note_set_stmt().where(PatientNoteSet.id == note_set_id)).scalar_one_or_none()
    return _ensure_note_set_access(note_set, user)


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


def _latest_review_chart_id(note_set: PatientNoteSet) -> int | None:
    if not note_set.review_charts:
        return None
    latest_chart = max(
        note_set.review_charts,
        key=lambda chart: (chart.created_at or datetime.min.replace(tzinfo=timezone.utc), chart.id),
    )
    return latest_chart.id


def _note_set_summary(note_set: PatientNoteSet) -> dict[str, object]:
    return {
        'id': note_set.id,
        'patient_id': note_set.patient_id,
        'review_chart_id': _latest_review_chart_id(note_set),
        'version': note_set.version,
        'status': note_set.status,
        'upload_mode': note_set.upload_mode,
        'source_system': note_set.source_system,
        'primary_clinician': note_set.primary_clinician,
        'level_of_care': note_set.level_of_care,
        'admission_date': note_set.admission_date,
        'discharge_date': note_set.discharge_date,
        'upload_notes': note_set.upload_notes,
        'created_at': note_set.created_at,
        'file_count': len(note_set.documents),
    }


def _note_set_detail(note_set: PatientNoteSet) -> dict[str, object]:
    documents = sorted(note_set.documents, key=lambda document: (document.document_date, document.id))
    return {
        **_note_set_summary(note_set),
        'documents': [
            {
                'id': document.id,
                'document_label': document.document_label,
                'original_filename': document.original_filename,
                'content_type': document.content_type,
                'size_bytes': document.size_bytes,
                'sha256': document.sha256,
                'alleva_bucket': document.alleva_bucket,
                'document_type': document.document_type,
                'completion_status': document.completion_status,
                'client_signed': document.client_signed,
                'staff_signed': document.staff_signed,
                'document_date': document.document_date,
                'description': document.description,
                'created_at': document.created_at,
            }
            for document in documents
        ],
    }


def _patient_id_detection_payload(patient_id: str | None, confidence: str, source_filename: str | None, source_kind: str | None, match_text: str | None, reason: str):
    return {
        'patient_id': patient_id,
        'confidence': confidence,
        'source_filename': source_filename,
        'source_kind': source_kind,
        'match_text': match_text,
        'reason': reason,
    }


def _settings_snapshot(settings_row: AppSetting) -> dict[str, object]:
    return {
        'organization_name': settings_row.organization_name,
        'access_intel_enabled': settings_row.access_intel_enabled,
        'access_geo_lookup_url': settings_row.access_geo_lookup_url,
        'access_reputation_url': settings_row.access_reputation_url,
        'access_reputation_api_key_configured': bool(settings_row.access_reputation_api_key),
        'access_lookup_timeout_seconds': settings_row.access_lookup_timeout_seconds,
        'llm_enabled': settings_row.llm_enabled,
        'llm_provider_name': settings_row.llm_provider_name,
        'llm_base_url': settings_row.llm_base_url,
        'llm_model': settings_row.llm_model,
        'llm_api_key_configured': bool(settings_row.llm_api_key),
        'llm_use_for_access_review': settings_row.llm_use_for_access_review,
        'llm_use_for_evaluation_gap_analysis': settings_row.llm_use_for_evaluation_gap_analysis,
        'llm_analysis_instructions': settings_row.llm_analysis_instructions,
        'updated_by_id': settings_row.updated_by_id,
    }


def _chart_summary(chart: Chart) -> dict[str, object]:
    _ensure_all_responses(chart)
    counts = _status_counts(chart)
    return {
        'id': chart.id,
        'source_note_set_id': chart.source_note_set_id,
        'patient_id': chart.patient_id,
        'client_name': chart.client_name,
        'level_of_care': chart.level_of_care,
        'admission_date': chart.admission_date,
        'discharge_date': chart.discharge_date,
        'primary_clinician': chart.primary_clinician,
        'auditor_name': chart.auditor_name,
        'other_details': chart.other_details,
        'counselor_id': chart.counselor_id,
        'state': chart.state,
        'system_score': chart.system_score,
        'system_summary': chart.system_summary,
        'manager_comment': chart.manager_comment,
        'reviewed_by_id': chart.reviewed_by_id,
        'system_generated_at': chart.system_generated_at,
        'reviewed_at': chart.reviewed_at,
        'created_at': chart.created_at,
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


def _normalized_chart_name(payload: ChartUpdate | ChartCreate) -> str:
    patient_id = payload.patient_id.strip()
    client_name = payload.client_name.strip()
    return client_name or patient_id


def _apply_chart_updates(chart: Chart, payload: ChartUpdate | ChartCreate) -> None:
    chart.patient_id = payload.patient_id.strip()
    chart.client_name = _normalized_chart_name(payload)
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
        response.updated_at = _utc_now()
        seen_keys.add(item.item_key)

    missing_keys = [template_item['key'] for template_item in AUDIT_TEMPLATE if template_item['key'] not in seen_keys]
    if missing_keys:
        raise HTTPException(status_code=400, detail=f'Missing checklist items: {", ".join(missing_keys)}')


def _parse_manifest(file_manifest: str, files: list[UploadFile]) -> list[PatientNoteDocumentUploadInput]:
    adapter = TypeAdapter(list[PatientNoteDocumentUploadInput])
    if file_manifest.strip():
        try:
            manifest = adapter.validate_json(file_manifest)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f'Invalid file manifest: {exc.errors()[0]["msg"]}') from exc
    else:
        manifest = []

    if not manifest:
        manifest = [PatientNoteDocumentUploadInput(client_file_name=file.filename or '') for file in files]

    if len(manifest) != len(files):
        raise HTTPException(status_code=400, detail='Uploaded file manifest must include exactly one entry per file')

    normalized: list[PatientNoteDocumentUploadInput] = []
    for metadata, upload in zip(manifest, files):
        expected_name = upload.filename or ''
        if metadata.client_file_name and metadata.client_file_name != expected_name:
            raise HTTPException(status_code=400, detail=f'File manifest mismatch for uploaded file {expected_name}')
        normalized.append(
            metadata.model_copy(
                update={
                    'client_file_name': expected_name,
                    'document_label': metadata.document_label.strip() or Path(expected_name or 'document').stem,
                    'document_type': metadata.document_type.strip() or 'clinical_note',
                    'description': metadata.description.strip(),
                    'document_date': metadata.document_date.strip(),
                }
            )
        )
    return normalized


def _active_admin_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(User).where(User.role == Role.admin, User.is_active.is_(True), User.is_locked.is_(False))
        ).scalar_one()
    )


def _assert_admin_safety(target: User, db: Session, *, new_role: Role | None = None, new_is_active: bool | None = None, new_is_locked: bool | None = None) -> None:
    if target.role != Role.admin:
        return

    admin_would_be_removed = new_role == Role.counselor or new_role == Role.manager or new_is_active is False or new_is_locked is True
    if admin_would_be_removed and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail='At least one active, unlocked admin account must remain')


def _user_snapshot(user: User) -> dict[str, object]:
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'role': user.role.value,
        'is_active': user.is_active,
        'is_locked': user.is_locked,
        'must_reset_password': user.must_reset_password,
        'last_login_at': user.last_login_at,
        'created_at': user.created_at,
    }


def _user_delete_blockers(user_id: int, db: Session) -> list[str]:
    blockers: list[str] = []

    relationship_checks = [
        ('assigned charts', select(Chart.id).where(Chart.counselor_id == user_id).limit(1)),
        ('reviewed charts', select(Chart.id).where(Chart.reviewed_by_id == user_id).limit(1)),
        ('uploaded patient note sets', select(PatientNoteSet.id).where(PatientNoteSet.uploaded_by_id == user_id).limit(1)),
        ('workflow transitions', select(WorkflowTransition.id).where(WorkflowTransition.actor_id == user_id).limit(1)),
        ('application settings updates', select(AppSetting.id).where(AppSetting.updated_by_id == user_id).limit(1)),
        ('forensic audit history', select(AuditLog.id).where(AuditLog.actor_id == user_id).limit(1)),
    ]

    for label, stmt in relationship_checks:
        if db.execute(stmt).scalar_one_or_none() is not None:
            blockers.append(label)

    return blockers


@router.post('/auth/login', response_model=Token)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    username = payload.username.strip()
    app_settings = get_or_create_app_settings(db)
    forwarded_for = request.headers.get('x-forwarded-for', '')
    source_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else '') or request.headers.get('x-real-ip') or (request.client.host if request.client else None)
    access_intel = lookup_access_intel(app_settings, source_ip)
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()

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
            event_category='access_attempt',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=username,
            details={'username': username, **access_intel.as_details()},
            outcome_status='failure',
            severity='warning',
            http_status_code=401,
            message=f'Login failed for username {username}. {access_intel.danger_summary}',
        )
        raise HTTPException(status_code=401, detail='Invalid credentials')

    if not user.is_active:
        log_event(
            db,
            request,
            'auth.login.blocked',
            actor=user,
            event_category='access_attempt',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'inactive', **access_intel.as_details()},
            outcome_status='failure',
            severity='warning',
            http_status_code=403,
            message=f'Login blocked for inactive account {user.username}. {access_intel.danger_summary}',
        )
        raise HTTPException(status_code=403, detail='Account inactive')

    if user.is_locked:
        log_event(
            db,
            request,
            'auth.login.blocked',
            actor=user,
            event_category='access_attempt',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'locked', **access_intel.as_details()},
            outcome_status='failure',
            severity='warning',
            http_status_code=403,
            message=f'Login blocked for locked account {user.username}. {access_intel.danger_summary}',
        )
        raise HTTPException(status_code=403, detail='Account locked')

    user.failed_login_attempts = 0
    user.last_login_at = _utc_now()
    if _is_bootstrap_admin(user):
        user.must_reset_password = False
    db.commit()

    token = create_access_token(user.username)
    log_event(
        db,
        request,
        'auth.login.success',
        actor=user,
        event_category='access_attempt',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username, **access_intel.as_details()},
        http_status_code=200,
        message=f'Login succeeded for {user.username}. {access_intel.danger_summary}',
    )
    return Token(access_token=token, must_reset_password=user.must_reset_password)


@router.post('/auth/reset-password')
def reset_password(payload: PasswordResetInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if _is_bootstrap_admin(user):
        log_event(
            db,
            request,
            'auth.password.reset.blocked',
            actor=user,
            event_category='authentication',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'bootstrap_admin_static_password'},
            outcome_status='failure',
            severity='warning',
            http_status_code=400,
            message='Static bootstrap admin password change was blocked.',
        )
        raise HTTPException(status_code=400, detail='The bootstrap admin password is fixed and cannot be changed in-app')

    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    user.is_locked = False
    user.failed_login_attempts = 0
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
def me(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log_event(
        db,
        request,
        'user.profile.read',
        actor=user,
        event_category='data_access',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Profile viewed for {user.username}.',
    )
    return user


@router.patch('/users/me', response_model=UserOut)
def update_my_profile(payload: UserSelfUpdate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.full_name = payload.full_name.strip() or user.username
    db.commit()
    db.refresh(user)
    log_event(
        db,
        request,
        'user.profile.update',
        actor=user,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username, 'full_name': user.full_name},
        message=f'Profile updated for {user.username}.',
    )
    return user


@router.post('/users/me/change-password')
def change_my_password(
    payload: UserPasswordChangeInput,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _is_bootstrap_admin(user):
        raise HTTPException(status_code=400, detail='The bootstrap admin password is fixed and cannot be changed in-app')
    if not verify_password(payload.current_password, user.password_hash):
        log_event(
            db,
            request,
            'auth.password.change.failed',
            actor=user,
            event_category='authentication',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'current_password_mismatch'},
            outcome_status='failure',
            severity='warning',
            http_status_code=400,
            message=f'Password change failed for {user.username}: current password mismatch.',
        )
        raise HTTPException(status_code=400, detail='Current password is incorrect')

    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    user.is_locked = False
    user.failed_login_attempts = 0
    db.commit()
    log_event(
        db,
        request,
        'auth.password.change',
        actor=user,
        event_category='authentication',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Password changed for {user.username}.',
    )
    return {'status': 'ok'}


@router.get('/users', response_model=list[UserOut])
def list_users(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    users = list(db.execute(select(User).order_by(User.role.asc(), User.username.asc())).scalars().all())
    log_event(
        db,
        request,
        'user.list.read',
        actor=user,
        event_category='user_management',
        target_entity='user_directory',
        target_entity_type='user',
        details={'count': len(users)},
        message=f'User directory viewed by {user.username}.',
    )
    return users


@router.post('/users', response_model=UserOut)
def create_user(payload: UserCreate, request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail='Username is required')
    exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail='Username exists')

    created = User(
        username=username,
        full_name=payload.full_name.strip() or username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        must_reset_password=True,
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    log_event(
        db,
        request,
        'user.create',
        actor=user,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(created.id),
        details={'username': created.username, 'role': created.role.value},
        message=f'User {created.username} created with role {created.role.value}.',
    )
    return created


@router.patch('/users/{user_id}', response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, actor: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')

    if _is_bootstrap_admin(target):
        disallowed = any(
            value is not None
            for value in [payload.role, payload.is_active, payload.is_locked, payload.must_reset_password]
        )
        if disallowed:
            raise HTTPException(status_code=400, detail='The bootstrap admin account cannot be deactivated, locked, or re-scoped')

    _assert_admin_safety(target, db, new_role=payload.role, new_is_active=payload.is_active, new_is_locked=payload.is_locked)

    if payload.full_name is not None:
        target.full_name = payload.full_name.strip() or target.username
    if payload.role is not None and not _is_bootstrap_admin(target):
        target.role = payload.role
    if payload.is_active is not None and not _is_bootstrap_admin(target):
        target.is_active = payload.is_active
    if payload.is_locked is not None and not _is_bootstrap_admin(target):
        target.is_locked = payload.is_locked
        if not target.is_locked:
            target.failed_login_attempts = 0
    if payload.must_reset_password is not None and not _is_bootstrap_admin(target):
        target.must_reset_password = payload.must_reset_password

    db.commit()
    db.refresh(target)
    log_event(
        db,
        request,
        'user.update',
        actor=actor,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(target.id),
        details={
            'username': target.username,
            'role': target.role.value,
            'is_active': target.is_active,
            'is_locked': target.is_locked,
            'must_reset_password': target.must_reset_password,
        },
        message=f'User {target.username} updated by {actor.username}.',
    )
    return target


@router.post('/users/{user_id}/reset-password', response_model=UserOut)
def admin_reset_password(
    user_id: int,
    payload: UserPasswordResetAdmin,
    request: Request,
    actor: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    if _is_bootstrap_admin(target):
        raise HTTPException(status_code=400, detail='The bootstrap admin password is fixed and cannot be changed in-app')

    target.password_hash = hash_password(payload.new_password)
    target.must_reset_password = payload.require_reset_on_login
    target.is_locked = False
    target.failed_login_attempts = 0
    db.commit()
    db.refresh(target)
    log_event(
        db,
        request,
        'user.password.reset.admin',
        actor=actor,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(target.id),
        details={'username': target.username, 'require_reset_on_login': payload.require_reset_on_login},
        message=f'Password reset by admin for {target.username}.',
    )
    return target


@router.delete('/users/{user_id}')
def delete_user(user_id: int, request: Request, actor: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail='You cannot delete your own account')
    if _is_bootstrap_admin(target):
        raise HTTPException(status_code=400, detail='The bootstrap admin account cannot be deleted')

    _assert_admin_safety(target, db, new_is_active=False)
    blockers = _user_delete_blockers(target.id, db)
    if blockers:
        blocker_summary = ', '.join(blockers)
        raise HTTPException(
            status_code=400,
            detail=f'User cannot be deleted because related records exist: {blocker_summary}. Deactivate the account instead.',
        )

    before_state = _user_snapshot(target)
    username = target.username
    target_id = target.id
    db.delete(target)
    db.commit()
    log_event(
        db,
        request,
        'user.delete',
        actor=actor,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(target_id),
        details={'username': username},
        before_state=before_state,
        diff_state=before_state,
        message=f'User {username} deleted by {actor.username}.',
    )
    return {'status': 'deleted'}


@router.get('/settings', response_model=AppSettingsOut)
def get_app_settings(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    settings_row = get_or_create_app_settings(db)
    log_event(
        db,
        request,
        'settings.read',
        actor=user,
        event_category='configuration',
        target_entity='app_settings',
        target_entity_type='app_setting',
        target_entity_id=str(settings_row.id),
        details=_settings_snapshot(settings_row),
        message='Application settings viewed.',
    )
    return app_settings_public_payload(settings_row)


@router.patch('/settings', response_model=AppSettingsOut)
def update_app_settings(
    payload: AppSettingsUpdate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    before_state = _settings_snapshot(settings_row)

    if payload.organization_name is not None:
        settings_row.organization_name = payload.organization_name.strip() or settings_row.organization_name
    if payload.access_intel_enabled is not None:
        settings_row.access_intel_enabled = payload.access_intel_enabled
    if payload.access_geo_lookup_url is not None:
        settings_row.access_geo_lookup_url = payload.access_geo_lookup_url.strip() or settings_row.access_geo_lookup_url
    if payload.access_reputation_url is not None:
        settings_row.access_reputation_url = payload.access_reputation_url.strip() or settings_row.access_reputation_url
    if payload.access_lookup_timeout_seconds is not None:
        settings_row.access_lookup_timeout_seconds = payload.access_lookup_timeout_seconds
    if payload.access_reputation_api_key is not None:
        settings_row.access_reputation_api_key = payload.access_reputation_api_key.strip()
    if payload.clear_access_reputation_api_key:
        settings_row.access_reputation_api_key = ''
    if payload.llm_enabled is not None:
        settings_row.llm_enabled = payload.llm_enabled
    if payload.llm_provider_name is not None:
        settings_row.llm_provider_name = payload.llm_provider_name.strip() or settings_row.llm_provider_name
    if payload.llm_base_url is not None:
        settings_row.llm_base_url = payload.llm_base_url.strip() or settings_row.llm_base_url
    if payload.llm_model is not None:
        settings_row.llm_model = payload.llm_model.strip() or settings_row.llm_model
    if payload.llm_api_key is not None:
        settings_row.llm_api_key = payload.llm_api_key.strip()
    if payload.clear_llm_api_key:
        settings_row.llm_api_key = ''
    if payload.llm_use_for_access_review is not None:
        settings_row.llm_use_for_access_review = payload.llm_use_for_access_review
    if payload.llm_use_for_evaluation_gap_analysis is not None:
        settings_row.llm_use_for_evaluation_gap_analysis = payload.llm_use_for_evaluation_gap_analysis
    if payload.llm_analysis_instructions is not None:
        settings_row.llm_analysis_instructions = payload.llm_analysis_instructions.strip()

    touch_app_settings(settings_row, actor=user)
    db.commit()
    db.refresh(settings_row)

    after_state = _settings_snapshot(settings_row)
    log_event(
        db,
        request,
        'settings.update',
        actor=user,
        event_category='configuration',
        target_entity='app_settings',
        target_entity_type='app_setting',
        target_entity_id=str(settings_row.id),
        details=after_state,
        before_state=before_state,
        after_state=after_state,
        diff_state={key: {'before': before_state.get(key), 'after': after_state.get(key)} for key in sorted(set(before_state) | set(after_state)) if before_state.get(key) != after_state.get(key)},
        message='Application settings updated.',
    )
    return app_settings_public_payload(settings_row)


@router.get('/audit-template', response_model=list[AuditTemplateSectionOut])
def get_audit_template(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sections = audit_sections()
    log_event(
        db,
        request,
        'audit.template.read',
        actor=user,
        event_category='data_access',
        target_entity='audit_template',
        target_entity_type='template',
        details={'section_count': len(sections)},
        message='Audit checklist template viewed.',
    )
    return sections


@router.get('/charts', response_model=list[ChartSummaryOut])
def list_charts(
    request: Request,
    patient_id: str | None = Query(default=None),
    state: WorkflowState | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = _chart_stmt()
    if user.role == Role.counselor:
        stmt = stmt.where(Chart.counselor_id == user.id)
    if patient_id and patient_id.strip():
        stmt = stmt.where(Chart.patient_id == patient_id.strip())
    if state:
        stmt = stmt.where(Chart.state == state)
    charts = list(db.execute(stmt.order_by(Chart.created_at.desc(), Chart.id.desc())).scalars().unique().all())
    log_event(
        db,
        request,
        'chart.list.read',
        actor=user,
        event_category='data_access',
        target_entity='chart_queue',
        target_entity_type='chart_queue',
        patient_id=patient_id.strip() if patient_id and patient_id.strip() else None,
        details={'count': len(charts), 'state': state.value if state else None},
        message=f'Chart queue viewed by {user.username}.',
    )
    return [_chart_summary(chart) for chart in charts]


@router.post('/charts', response_model=ChartDetailOut)
def create_chart(payload: ChartCreate, request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    chart = Chart(
        patient_id='',
        client_name='',
        level_of_care='',
        admission_date='',
        discharge_date='',
        primary_clinician='',
        auditor_name=payload.auditor_name.strip() or user.username,
        other_details='',
        counselor_id=user.id,
        notes='',
        state=WorkflowState.draft,
    )
    _apply_chart_updates(chart, payload)
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
        patient_id=chart.patient_id,
        details={'state': chart.state.value, 'patient_id': chart.patient_id},
        message=f'Manual chart audit {chart.id} created for patient {chart.patient_id or chart.id}.',
    )
    return _chart_detail(chart)


@router.get('/charts/{chart_id}', response_model=ChartDetailOut)
def get_chart(chart_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.read',
        actor=user,
        event_category='data_access',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        patient_id=chart.patient_id,
        details={'state': chart.state.value},
        message=f'Chart audit {chart.id} viewed by {user.username}.',
    )
    return _chart_detail(chart)


@router.put('/charts/{chart_id}', response_model=ChartDetailOut)
def update_chart(chart_id: int, payload: ChartUpdate, request: Request, user: User = Depends(require_roles(*REVIEW_ROLES)), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    _apply_chart_updates(chart, payload)
    if chart.source_note_set_id:
        chart.state = WorkflowState.awaiting_manager_review
        chart.reviewed_by_id = None
        chart.reviewed_at = None
        chart.manager_comment = ''
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
        patient_id=chart.patient_id,
        details={'state': chart.state.value, 'patient_id': chart.patient_id},
        message=f'Chart audit {chart.id} updated by {user.username}.',
    )
    return _chart_detail(chart)


@router.post('/charts/{chart_id}/transition', response_model=ChartDetailOut)
def transition_chart(chart_id: int, payload: TransitionInput, request: Request, user: User = Depends(require_roles(*REVIEW_ROLES)), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    if not _allowed_transition(user.role, chart.state, payload.to_state):
        raise HTTPException(status_code=400, detail='Invalid transition for role/state')
    if payload.to_state == WorkflowState.manager_rejected and not payload.comment.strip():
        raise HTTPException(status_code=400, detail='Comment required when returning a chart to the counselor')

    old = chart.state
    chart.state = payload.to_state
    chart.manager_comment = payload.comment.strip()
    chart.reviewed_by_id = user.id
    chart.reviewed_at = _utc_now()

    if payload.to_state == WorkflowState.awaiting_manager_review:
        chart.manager_comment = ''
        chart.reviewed_by_id = None
        chart.reviewed_at = None

    db.add(
        WorkflowTransition(
            chart_id=chart.id,
            actor_id=user.id,
            from_state=old.value,
            to_state=payload.to_state.value,
            comment=payload.comment.strip(),
        )
    )
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
        patient_id=chart.patient_id,
        details={'from': old.value, 'to': payload.to_state.value, 'comment': payload.comment.strip()},
        message=f'Chart audit {chart.id} transitioned from {old.value} to {payload.to_state.value}.',
    )
    return _chart_detail(chart)


@router.get('/patient-note-sets', response_model=list[PatientNoteSetSummaryOut])
def list_patient_note_sets(
    request: Request,
    patient_id: str | None = Query(default=None),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    stmt = _note_set_stmt().order_by(PatientNoteSet.created_at.desc(), PatientNoteSet.id.desc())
    if user.role == Role.counselor:
        stmt = stmt.where(PatientNoteSet.uploaded_by_id == user.id)
    if patient_id and patient_id.strip():
        stmt = stmt.where(PatientNoteSet.patient_id == patient_id.strip())
    note_sets = list(db.execute(stmt).scalars().unique().all())
    log_event(
        db,
        request,
        'patient_note_sets.list.read',
        actor=user,
        event_category='data_access',
        target_entity='patient_note_sets',
        target_entity_type='patient_note_set',
        patient_id=patient_id.strip() if patient_id and patient_id.strip() else None,
        details={'count': len(note_sets), 'patient_id': patient_id.strip() if patient_id and patient_id.strip() else None},
        message=f'Patient note set queue viewed by {user.username}.',
    )
    return [_note_set_summary(note_set) for note_set in note_sets]


@router.get('/patient-note-sets/{note_set_id}', response_model=PatientNoteSetDetailOut)
def get_patient_note_set(note_set_id: int, request: Request, user: User = Depends(require_roles(*NOTE_SET_ROLES)), db: Session = Depends(get_db)):
    note_set = _find_note_set(note_set_id, user, db)
    log_event(
        db,
        request,
        'patient_note_set.read',
        actor=user,
        event_category='data_access',
        target_entity=f'patient_note_set:{note_set.id}',
        target_entity_type='patient_note_set',
        target_entity_id=str(note_set.id),
        patient_id=note_set.patient_id,
        details={'version': note_set.version, 'document_count': len(note_set.documents)},
        message=f'Patient note set {note_set.id} viewed by {user.username}.',
    )
    return _note_set_detail(note_set)


@router.post('/patient-note-sets/detect-patient-id', response_model=PatientIdDetectionOut)
async def detect_patient_id_for_uploads(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
):
    if not files:
        raise HTTPException(status_code=400, detail='At least one clinical note file is required')

    detection = await detect_patient_id_from_uploads(files)
    action = 'patient_note_set.patient_id.detected' if detection.patient_id else 'patient_note_set.patient_id.not_detected'
    log_event(
        request=request,
        actor=user,
        action=action,
        event_category='file_activity',
        target_entity='patient_note_set_upload',
        target_entity_type='patient_note_set',
        patient_id=detection.patient_id,
        details={
            'file_count': len(files),
            'confidence': detection.confidence,
            'source_filename': detection.source_filename,
            'source_kind': detection.source_kind,
            'match_text': detection.match_text,
            'reason': detection.reason,
        },
        outcome_status='success' if detection.patient_id else 'failure',
        severity='info' if detection.patient_id else 'warning',
        message=detection.reason,
        http_status_code=200,
    )
    return _patient_id_detection_payload(
        detection.patient_id,
        detection.confidence,
        detection.source_filename,
        detection.source_kind,
        detection.match_text,
        detection.reason,
    )


@router.post('/patient-note-sets', response_model=PatientNoteSetDetailOut)
async def upload_patient_note_set(
    request: Request,
    patient_id: str = Form(''),
    upload_mode: NoteSetUploadMode = Form(NoteSetUploadMode.initial),
    level_of_care: str = Form(''),
    admission_date: str = Form(''),
    discharge_date: str = Form(''),
    primary_clinician: str = Form(''),
    upload_notes: str = Form(''),
    file_manifest: str = Form(''),
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail='At least one clinical note file is required')

    normalized_patient_id = patient_id.strip()
    detection = await detect_patient_id_from_uploads(files) if not normalized_patient_id else None
    if not normalized_patient_id and detection and detection.patient_id:
        normalized_patient_id = detection.patient_id
        log_event(
            request=request,
            actor=user,
            action='patient_note_set.upload.patient_id_autofilled',
            event_category='file_activity',
            target_entity='patient_note_set_upload',
            target_entity_type='patient_note_set',
            patient_id=normalized_patient_id,
            details={
                'confidence': detection.confidence,
                'source_filename': detection.source_filename,
                'source_kind': detection.source_kind,
                'match_text': detection.match_text,
            },
            message=f'Patient ID {normalized_patient_id} was auto-filled from the uploaded files during upload.',
            http_status_code=200,
        )
    if not normalized_patient_id:
        reason = detection.reason if detection is not None else 'Patient ID is required.'
        log_event(
            request=request,
            actor=user,
            action='patient_note_set.upload.patient_id_missing',
            event_category='file_activity',
            target_entity='patient_note_set_upload',
            target_entity_type='patient_note_set',
            details={'reason': reason, 'file_count': len(files)},
            outcome_status='failure',
            severity='warning',
            message='Patient note upload was blocked because no patient ID was supplied or detected.',
            http_status_code=400,
        )
        raise HTTPException(status_code=400, detail=f'Patient ID is required and could not be detected automatically. {reason}')

    manifest = _parse_manifest(file_manifest, files)
    existing_active = db.execute(
        _note_set_stmt().where(PatientNoteSet.patient_id == normalized_patient_id, PatientNoteSet.status == NoteSetStatus.active)
    ).scalar_one_or_none()
    if existing_active is not None:
        _ensure_note_set_access(existing_active, user)

    if upload_mode == NoteSetUploadMode.initial and existing_active:
        raise HTTPException(status_code=409, detail='A patient note set already exists for this patient ID; use update mode instead')
    if upload_mode == NoteSetUploadMode.update and not existing_active:
        raise HTTPException(status_code=404, detail='No active patient note set exists for this patient ID; use initial upload instead')

    next_version = (existing_active.version + 1) if existing_active else 1
    note_set = PatientNoteSet(
        patient_id=normalized_patient_id,
        version=next_version,
        status=NoteSetStatus.active,
        upload_mode=upload_mode,
        source_system='Alleva EMR',
        primary_clinician=primary_clinician.strip(),
        level_of_care=level_of_care.strip(),
        admission_date=admission_date.strip(),
        discharge_date=discharge_date.strip(),
        upload_notes=upload_notes.strip(),
        replaced_note_set_id=existing_active.id if existing_active else None,
        uploaded_by_id=user.id,
    )

    created_documents: list[PatientNoteDocument] = []
    stored_paths: list[str] = []
    try:
        if existing_active:
            existing_active.status = NoteSetStatus.superseded
        db.add(note_set)
        db.flush()

        for metadata in manifest:
            document = PatientNoteDocument(
                note_set_id=note_set.id,
                document_label=metadata.document_label,
                original_filename=metadata.client_file_name,
                storage_path='',
                content_type='application/octet-stream',
                size_bytes=0,
                sha256='',
                alleva_bucket=metadata.alleva_bucket,
                document_type=metadata.document_type,
                completion_status=metadata.completion_status,
                client_signed=metadata.client_signed,
                staff_signed=metadata.staff_signed,
                document_date=metadata.document_date,
                description=metadata.description,
            )
            db.add(document)
            created_documents.append(document)

        db.flush()

        for upload, document in zip(files, created_documents):
            stored = await store_upload_file(upload, patient_id=normalized_patient_id, note_set_id=note_set.id, document_id=document.id)
            document.storage_path = stored.storage_path
            document.content_type = stored.content_type
            document.size_bytes = stored.size_bytes
            document.sha256 = stored.sha256
            stored_paths.append(stored.storage_path)

        chart = Chart(
            source_note_set_id=note_set.id,
            patient_id=normalized_patient_id,
            client_name=normalized_patient_id,
            level_of_care=note_set.level_of_care,
            admission_date=note_set.admission_date,
            discharge_date=note_set.discharge_date,
            primary_clinician=note_set.primary_clinician,
            auditor_name=user.full_name or user.username,
            other_details='Auto-generated from uploaded clinical note binder.',
            counselor_id=user.id,
            notes=note_set.upload_notes,
            state=WorkflowState.draft,
        )
        db.add(chart)
        db.flush()

        note_set.documents[:] = created_documents
        report = generate_evaluation_report(note_set, app_settings=get_or_create_app_settings(db))
        apply_report_to_chart(chart, report)
        chart.notes = note_set.upload_notes
        db.add(
            WorkflowTransition(
                chart_id=chart.id,
                actor_id=user.id,
                from_state=WorkflowState.draft.value,
                to_state=chart.state.value,
                comment='System evaluation generated automatically from uploaded clinical notes.',
            )
        )

        db.commit()
    except Exception as exc:
        db.rollback()
        remove_stored_paths(stored_paths)
        log_event(
            db,
            request,
            'patient_note_set.upload.failed',
            actor=user,
            event_category='file_activity',
            target_entity='patient_note_set',
            target_entity_type='patient_note_set',
            patient_id=normalized_patient_id,
            details={'file_count': len(files), 'reason': exc.__class__.__name__},
            outcome_status='failure',
            severity='error',
            message=f'Patient note upload failed for {normalized_patient_id}.',
            http_status_code=500 if not isinstance(exc, HTTPException) else exc.status_code,
        )
        if isinstance(exc, HTTPException):
            raise
        raise

    note_set = _find_note_set(note_set.id, user, db)
    review_chart_id = _latest_review_chart_id(note_set)
    review_chart = _find_chart(review_chart_id, user, db) if review_chart_id is not None else None

    log_event(
        db,
        request,
        'patient_note_set.uploaded',
        actor=user,
        event_category='file_activity',
        target_entity=f'patient_note_set:{note_set.id}',
        target_entity_type='patient_note_set',
        target_entity_id=str(note_set.id),
        patient_id=note_set.patient_id,
        details={'version': note_set.version, 'file_count': len(note_set.documents), 'upload_mode': note_set.upload_mode.value},
        message=f'Patient note set {note_set.id} uploaded for patient {note_set.patient_id}.',
    )
    for document in note_set.documents:
        log_event(
            db,
            request,
            'patient_note.document.uploaded',
            actor=user,
            event_category='file_activity',
            target_entity=f'patient_note_document:{document.id}',
            target_entity_type='patient_note_document',
            target_entity_id=str(document.id),
            patient_id=note_set.patient_id,
            details={
                'note_set_id': note_set.id,
                'filename': document.original_filename,
                'sha256': document.sha256,
                'size_bytes': document.size_bytes,
                'alleva_bucket': document.alleva_bucket.value,
            },
            message=f'Clinical note document {document.id} stored for patient {note_set.patient_id}.',
        )
    if review_chart is not None:
        log_event(
            db,
            request,
            'chart.system_evaluated',
            actor=user,
            event_category='workflow',
            target_entity=f'chart:{review_chart.id}',
            target_entity_type='chart',
            target_entity_id=str(review_chart.id),
            patient_id=review_chart.patient_id,
            details={
                'source_note_set_id': note_set.id,
                'system_score': review_chart.system_score,
                'state': review_chart.state.value,
                'failed_items': _chart_summary(review_chart)['failed_items'],
                'pending_items': _chart_summary(review_chart)['pending_items'],
            },
            message=f'Automated evaluation completed for chart {review_chart.id}.',
        )
    return _note_set_detail(note_set)


@router.get('/patient-note-sets/{note_set_id}/documents/{document_id}/download')
def download_patient_note_document(
    note_set_id: int,
    document_id: int,
    request: Request,
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    note_set = _find_note_set(note_set_id, user, db)
    document = next((item for item in note_set.documents if item.id == document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail='Patient note document not found')

    file_path = resolve_storage_path(document.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='Stored patient note file is missing')

    log_event(
        db,
        request,
        'patient_note.document.download',
        actor=user,
        event_category='data_access',
        target_entity=f'patient_note_document:{document.id}',
        target_entity_type='patient_note_document',
        target_entity_id=str(document.id),
        patient_id=note_set.patient_id,
        details={'note_set_id': note_set.id, 'filename': document.original_filename},
        message=f'Clinical note document {document.id} downloaded by {user.username}.',
    )
    return FileResponse(file_path, filename=document.original_filename, media_type=document.content_type)


@router.get('/audit/logs', response_model=list[AuditLogOut])
def audit_logs(
    request: Request,
    limit: int = Query(default=200, ge=1, le=2000),
    action: str | None = Query(default=None),
    event_category: str | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    actor_username: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action and action.strip():
        stmt = stmt.where(AuditLog.action == action.strip())
    if event_category and event_category.strip():
        stmt = stmt.where(AuditLog.event_category == event_category.strip())
    if patient_id and patient_id.strip():
        stmt = stmt.where(AuditLog.patient_id == patient_id.strip())
    if actor_username and actor_username.strip():
        stmt = stmt.where(AuditLog.actor_username == actor_username.strip())
    if request_id and request_id.strip():
        stmt = stmt.where(AuditLog.request_id == request_id.strip())

    logs = list(db.execute(stmt).scalars().all())
    log_event(
        db,
        request,
        'audit.logs.read',
        actor=user,
        event_category='forensic_access',
        target_entity='audit_logs',
        target_entity_type='audit_log',
        details={
            'count': len(logs),
            'limit': limit,
            'action': action.strip() if action and action.strip() else None,
            'event_category': event_category.strip() if event_category and event_category.strip() else None,
            'patient_id': patient_id.strip() if patient_id and patient_id.strip() else None,
            'actor_username': actor_username.strip() if actor_username and actor_username.strip() else None,
            'request_id': request_id.strip() if request_id and request_id.strip() else None,
        },
        message='Forensic audit log list viewed.',
    )
    return logs
