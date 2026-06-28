from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.models import AuditLog, Role, TreatmentPlanClient, TreatmentPlanCriterionReview, User
from app.schemas.schemas import (
    TimelinessClientDetailOut,
    TimelinessCriterionReviewInput,
    TimelinessClientUpsert,
    TimelinessDashboardOut,
    TimelinessOverrideInput,
    TimelinessOverrideOut,
)
from app.services.audit import log_event
from app.services.app_settings import get_or_create_app_settings
from app.services.timeliness import (
    STATUS_PRIORITY as TIMELINESS_STATUS_PRIORITY,
    add_override,
    detail_payload as timeliness_detail_payload,
    evaluate_client,
    get_client as get_timeliness_client,
    list_clients as list_timeliness_clients,
    summary_payload as timeliness_summary_payload,
    treatment_plan_aggregate_payload,
    upsert_client as upsert_timeliness_client,
)
from app.services.treatment_plan_checklist import load_treatment_plan_checklist
from app.services.workflow_definitions import current_treatment_plan_workflow_context


router = APIRouter(prefix='/timeliness')
NOTE_SET_ROLES = (Role.admin, Role.counselor, Role.manager)
MANAGER_CRITERION_REVIEW_STATUSES = {'Not Reviewed', 'OK', 'Needs Review', 'Needs Update', 'Not Applicable'}


def _parse_evaluation_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), '%Y-%m-%d').date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='evaluation_date must use YYYY-MM-DD') from exc


def _log_timeliness_analysis_result(db: Session, request: Request, user: User, evaluation, workflow_context: dict[str, object]) -> None:
    client = evaluation.client
    log_event(
        db,
        request,
        'timeliness.analysis.result',
        actor=user,
        event_category='workflow',
        target_entity=f'treatment_plan_client:{client.id}',
        target_entity_type='treatment_plan_analysis',
        target_entity_id=str(client.id),
        patient_id=client.patient_id,
        details={
            'patient_id': client.patient_id,
            'status': evaluation.status,
            'next_due_date': evaluation.next_due_date,
            'days_until_due': evaluation.days_until_due,
            'current_date': evaluation.current_date,
            'rule_used': evaluation.rule_used,
            'workflow_key': workflow_context.get('workflow_key'),
            'workflow_version_id': workflow_context.get('workflow_version_id'),
            'workflow_version': workflow_context.get('workflow_version'),
            'checklist_version': workflow_context.get('checklist_version'),
        },
        message=f'Treatment Plan Timeliness analysis produced {evaluation.status} for {client.patient_id}.',
    )


@router.get('/dashboard', response_model=TimelinessDashboardOut)
def get_timeliness_dashboard(
    request: Request,
    evaluation_date: str | None = Query(default=None),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    app_settings = get_or_create_app_settings(db)
    as_of = _parse_evaluation_date(evaluation_date)
    evaluations = [evaluate_client(client, app_settings, evaluation_date=as_of) for client in list_timeliness_clients(db)]
    workflow_context = current_treatment_plan_workflow_context(db)
    for evaluation in evaluations:
        _log_timeliness_analysis_result(db, request, user, evaluation, workflow_context)
    status_counts = {status: 0 for status in TIMELINESS_STATUS_PRIORITY}
    for evaluation in evaluations:
        status_counts[evaluation.status] = status_counts.get(evaluation.status, 0) + 1
    total = len(evaluations)
    compliance_percentage = round((status_counts['Compliant'] / total) * 100, 1) if total else 0.0
    items = sorted(
        [timeliness_summary_payload(evaluation) for evaluation in evaluations],
        key=lambda item: (
            TIMELINESS_STATUS_PRIORITY.index(str(item['status'])) if str(item['status']) in TIMELINESS_STATUS_PRIORITY else len(TIMELINESS_STATUS_PRIORITY),
            item['next_due_date'] or '9999-12-31',
            item['patient_id'],
        ),
    )
    log_event(
        db,
        request,
        'timeliness.dashboard.read',
        actor=user,
        event_category='workflow',
        target_entity='treatment_plan_timeliness',
        target_entity_type='timeliness_dashboard',
        details={'count': total, 'evaluation_date': evaluation_date or ''},
        message='Treatment Plan Timeliness dashboard viewed.',
    )
    return {
        'total_active_clients': total,
        'compliant': status_counts['Compliant'],
        'due_soon': status_counts['Due Soon'],
        'urgent': status_counts['Urgent'],
        'overdue': status_counts['Overdue'],
        'returned': status_counts['Returned for Correction'],
        'needs_review': status_counts['Needs Review'],
        'missing_data': status_counts['Missing Data'],
        'conflicting_evidence': status_counts['Conflicting Evidence'],
        'unable_to_evaluate': status_counts['Unable to Evaluate'],
        'approved': status_counts['Approved'],
        'compliance_percentage': compliance_percentage,
        'loc_change_window_days': app_settings.treatment_plan_loc_change_window_days,
        'loc_change_window_validated': app_settings.treatment_plan_loc_change_window_validated,
        'items': items,
    }


@router.post('/clients', response_model=TimelinessClientDetailOut)
def upsert_timeliness_client_endpoint(
    payload: TimelinessClientUpsert,
    request: Request,
    user: User = Depends(require_roles(Role.admin, Role.manager)),
    db: Session = Depends(get_db),
):
    if not payload.patient_id.strip():
        raise HTTPException(status_code=400, detail='patient_id is required')
    before = None
    existing = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == payload.patient_id.strip())).scalar_one_or_none()
    if existing is not None:
        before = {'patient_id': existing.patient_id, 'current_level_of_care': existing.current_level_of_care, 'admission_date': existing.admission_date}
    client = upsert_timeliness_client(db, payload)
    db.commit()
    db.refresh(client)
    client = get_timeliness_client(db, client.id)
    app_settings = get_or_create_app_settings(db)
    evaluation = evaluate_client(client, app_settings)
    workflow_context = current_treatment_plan_workflow_context(db)
    _log_timeliness_analysis_result(db, request, user, evaluation, workflow_context)
    log_event(
        db,
        request,
        'timeliness.client.upsert',
        actor=user,
        event_category='workflow',
        target_entity=f'treatment_plan_client:{client.id}',
        target_entity_type='treatment_plan_client',
        target_entity_id=str(client.id),
        patient_id=client.patient_id,
        details={'patient_id': client.patient_id, 'has_before_state': before is not None},
        before_state=before,
        message=f'Treatment Plan Timeliness client {client.patient_id} saved.',
    )
    return timeliness_detail_payload(evaluation, [])


@router.get('/clients/{client_id}', response_model=TimelinessClientDetailOut)
def get_timeliness_client_detail(
    client_id: int,
    request: Request,
    evaluation_date: str | None = Query(default=None),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    client = get_timeliness_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail='Treatment Plan Timeliness client not found')
    app_settings = get_or_create_app_settings(db)
    evaluation = evaluate_client(client, app_settings, evaluation_date=_parse_evaluation_date(evaluation_date))
    workflow_context = current_treatment_plan_workflow_context(db)
    _log_timeliness_analysis_result(db, request, user, evaluation, workflow_context)
    audit_history = list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.patient_id == client.patient_id)
            .order_by(AuditLog.timestamp_utc.desc(), AuditLog.id.desc())
            .limit(25)
        ).scalars()
    )
    log_event(
        db,
        request,
        'timeliness.client.read',
        actor=user,
        event_category='data_access',
        target_entity=f'treatment_plan_client:{client.id}',
        target_entity_type='treatment_plan_client',
        target_entity_id=str(client.id),
        patient_id=client.patient_id,
        details={'patient_id': client.patient_id},
        message=f'Treatment Plan Timeliness client {client.patient_id} viewed.',
    )
    return timeliness_detail_payload(evaluation, audit_history)


@router.get('/clients/{client_id}/treatment-plan')
def get_timeliness_client_treatment_plan_aggregate(
    client_id: int,
    request: Request,
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    client = get_timeliness_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail='Treatment Plan Timeliness client not found')
    payload = treatment_plan_aggregate_payload(client)
    log_event(
        db,
        request,
        'timeliness.client.treatment_plan_aggregate.read',
        actor=user,
        event_category='data_access',
        target_entity=f'treatment_plan_client:{client.id}',
        target_entity_type='treatment_plan_aggregate',
        target_entity_id=str(client.id),
        patient_id=client.patient_id,
        details={'patient_id': client.patient_id, 'has_current_plan': payload['current_plan'] is not None},
        message=f'Treatment plan aggregate viewed for {client.patient_id}.',
    )
    return payload


@router.post('/clients/{client_id}/overrides', response_model=TimelinessOverrideOut)
def create_timeliness_override(
    client_id: int,
    payload: TimelinessOverrideInput,
    request: Request,
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    client = get_timeliness_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail='Treatment Plan Timeliness client not found')
    if user.role not in {Role.admin, Role.manager}:
        log_event(
            db,
            request,
            'timeliness.override.denied',
            actor=user,
            event_category='authorization',
            target_entity=f'treatment_plan_client:{client.id}',
            target_entity_type='treatment_plan_client',
            target_entity_id=str(client.id),
            patient_id=client.patient_id,
            details={'field_name': payload.field_name, 'affected_rule': payload.affected_rule},
            outcome_status='failure',
            severity='warning',
            http_status_code=403,
            message=f'Treatment Plan Timeliness override denied for {client.patient_id}.',
        )
        raise HTTPException(status_code=403, detail='Only administrators and office managers can create timeliness overrides')
    override = add_override(db, client, payload, actor=user)
    db.commit()
    db.refresh(override)
    log_event(
        db,
        request,
        'timeliness.override.created',
        actor=user,
        event_category='workflow',
        target_entity=f'treatment_plan_override:{override.id}',
        target_entity_type='treatment_plan_override',
        target_entity_id=str(override.id),
        patient_id=client.patient_id,
        details={'field_name': override.field_name, 'affected_rule': override.affected_rule},
        message=f'Treatment Plan Timeliness override {override.id} created.',
    )
    return override


@router.put('/clients/{client_id}/criterion-reviews', response_model=TimelinessClientDetailOut)
def update_timeliness_criterion_reviews(
    client_id: int,
    payload: list[TimelinessCriterionReviewInput],
    request: Request,
    user: User = Depends(require_roles(Role.admin, Role.manager)),
    db: Session = Depends(get_db),
):
    client = get_timeliness_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail='Treatment Plan Timeliness client not found')
    if not payload:
        raise HTTPException(status_code=400, detail='At least one criterion review is required')

    checklist = load_treatment_plan_checklist()
    valid_keys = {str(step['key']) for step in checklist['steps']}
    existing_by_key = {review.criterion_key: review for review in client.criterion_reviews}
    changed_count = 0
    now = datetime.now(timezone.utc)
    status_counts: Counter[str] = Counter()
    for item in payload:
        criterion_key = item.criterion_key.strip()
        status = item.status.strip() or 'Not Reviewed'
        comment = item.comment.strip()
        if criterion_key not in valid_keys:
            raise HTTPException(status_code=400, detail=f'Unknown treatment-plan criterion key: {criterion_key}')
        if status not in MANAGER_CRITERION_REVIEW_STATUSES:
            raise HTTPException(status_code=400, detail=f'Unknown criterion review status: {status}')
        review = existing_by_key.get(criterion_key)
        if review is None:
            review = TreatmentPlanCriterionReview(client_id=client.id, criterion_key=criterion_key)
            db.add(review)
            existing_by_key[criterion_key] = review
        if review.status != status or review.comment != comment:
            changed_count += 1
        review.status = status
        review.comment = comment
        review.updated_by_id = user.id
        review.updated_at = now
        status_counts[status] += 1

    db.commit()
    log_event(
        db,
        request,
        'timeliness.criterion_reviews.updated',
        actor=user,
        event_category='workflow',
        target_entity=f'treatment_plan_client:{client.id}',
        target_entity_type='treatment_plan_criterion_reviews',
        target_entity_id=str(client.id),
        patient_id=client.patient_id,
        details={
            'criterion_count': len(payload),
            'changed_count': changed_count,
            'statuses': dict(status_counts),
        },
        message=f'Treatment Plan criterion reviews updated for {client.patient_id}.',
    )

    client = get_timeliness_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail='Treatment Plan Timeliness client not found')
    app_settings = get_or_create_app_settings(db)
    evaluation = evaluate_client(client, app_settings, evaluation_date=_parse_evaluation_date(request.query_params.get('evaluation_date')))
    audit_history = list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.patient_id == client.patient_id)
            .order_by(AuditLog.timestamp_utc.desc(), AuditLog.id.desc())
            .limit(25)
        ).scalars()
    )
    return timeliness_detail_payload(evaluation, audit_history)
