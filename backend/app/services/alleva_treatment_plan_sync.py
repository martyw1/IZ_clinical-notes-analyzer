from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.models import AppSetting, LevelOfCareHistory, TreatmentPlanClient, TreatmentPlanKind, TreatmentPlanRecord, User
from app.services.api_connectivity import request_client_credentials_token
from app.services.audit import log_event
from app.services.patient_notes import NAME_NOT_FOUND_STATUS, display_name_for_patient_name_status
from app.services.secure_storage import decrypt_text_secret
from app.services.timeliness import evaluate_client
from app.services.workflow_definitions import current_treatment_plan_workflow_context

logger = logging.getLogger(__name__)

DEFAULT_ALLEVA_API_BASE_URL = 'https://api.allevasoft.com'
DEFAULT_ALLEVA_OPENAPI_URL = 'https://api.allevasoft.com/swagger/v1/swagger.json'
ALLEVA_REST_SOURCE = 'Alleva REST'
SYNC_ENDPOINTS = {
    'clients': '/clients',
    'treatment_plans': '/treatment-plans',
    'treatment_reviews': '/treatment-reviews',
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strip(value: Any) -> str:
    return str(value).strip() if value is not None else ''


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            nested = _first_text(value, 'clientFullName', 'fullName', 'name', 'preferred', 'first', 'last')
            if nested:
                return nested
            continue
        text = _strip(value)
        if text:
            return text
    return ''


def _date_text(value: Any) -> str:
    raw = _strip(value)
    if not raw:
        return ''
    if 'T' in raw:
        return raw.split('T', 1)[0]
    if ' ' in raw and raw[:10].count('-') == 2:
        return raw[:10]
    return raw


def _client_name(payload: dict[str, Any]) -> str:
    name = payload.get('name')
    if isinstance(name, dict):
        full = _first_text(name, 'clientFullName', 'preferred')
        if full:
            return full
        first = _first_text(name, 'first')
        last = _first_text(name, 'last')
        return ' '.join(part for part in [first, last] if part)
    return _first_text(payload, 'leadFullName', 'clientFullName', 'fullName', 'name')


def _client_aliases(payload: dict[str, Any]) -> list[str]:
    aliases = []
    for key in ('clientId', 'id', 'leadId', 'luin', 'uniqueId', 'mrn'):
        value = _strip(payload.get(key))
        if value:
            aliases.append(value)
    return list(dict.fromkeys(aliases))


def _patient_id_from_client(payload: dict[str, Any]) -> str:
    for key in ('clientId', 'id', 'leadId', 'uniqueId', 'mrn'):
        value = _strip(payload.get(key))
        if value:
            return value
    return ''


def _nested_client_aliases(payload: dict[str, Any]) -> list[str]:
    aliases = []
    for key in ('clientId', 'leadId', 'patientId'):
        value = _strip(payload.get(key))
        if value:
            aliases.append(value)
    client = payload.get('client')
    if isinstance(client, dict):
        aliases.extend(_client_aliases(client))
    return list(dict.fromkeys(aliases))


def _is_active_client(payload: dict[str, Any]) -> bool:
    if bool(payload.get('isDischarge')):
        return False
    if _strip(payload.get('dischargeDateTime')) or _strip(payload.get('actualSysDischargeDateTime')):
        return False
    status = _first_text(payload, 'status', 'statusName').lower()
    if status and any(word in status for word in ('discharge', 'inactive', 'closed', 'deceased')):
        return False
    return True


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('items', 'data', 'results', 'value', 'records'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _endpoint_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))


def _fetch_collection(
    *,
    base_url: str,
    path: str,
    bearer_token: str,
    api_version: str,
    limit: int,
    timeout_seconds: int,
    max_pages: int = 25,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor = 0
    page_size = max(1, min(limit, 500))
    url = _endpoint_url(base_url, path)
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {bearer_token}',
        'X-Version': api_version,
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        for _page in range(max_pages):
            params = {'Limit': page_size, 'Cursor': cursor, 'api-version': api_version}
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            page_records = _extract_records(response.json())
            records.extend(page_records)
            if len(page_records) < page_size or len(records) >= limit:
                break
            cursor += page_size
    return records[:limit]


def _missing_sync_configuration(settings_row: AppSetting, *, startup: bool) -> list[str]:
    missing = []
    if not settings_row.alleva_treatment_plan_sync_enabled:
        missing.append('Alleva treatment-plan sync enabled')
    if startup and not settings_row.alleva_treatment_plan_sync_on_startup:
        missing.append('sync on app startup')
    if not settings_row.alleva_treatment_plan_sync_approved:
        missing.append('R3/Alleva live treatment-plan sync approval')
    if not settings_row.alleva_treatment_plan_endpoint_mapping_validated:
        missing.append('validated Alleva treatment-plan endpoint mapping')
    if not settings_row.alleva_api_base_url.strip():
        missing.append('Alleva REST API base URL')
    if not settings_row.api_oauth_token_url.strip():
        missing.append('Alleva OAuth token URL')
    if not settings_row.api_client_id.strip():
        missing.append('Alleva API client ID')
    if not settings_row.api_client_secret:
        missing.append('Alleva API client secret')
    return missing


def _mark_status(db: Session, settings_row: AppSetting, *, status: str, message: str) -> None:
    now = _utc_now()
    settings_row.alleva_treatment_plan_sync_last_at = now
    settings_row.alleva_treatment_plan_sync_last_status = status
    settings_row.alleva_treatment_plan_sync_last_message = message[:1000]
    if status == 'ok':
        settings_row.alleva_treatment_plan_sync_last_success_at = now
    elif status in {'fail', 'blocked'}:
        settings_row.alleva_treatment_plan_sync_last_failure_at = now
    db.commit()


def _client_lookup(active_clients: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_alias: dict[str, str] = {}
    by_name: dict[str, str] = {}
    duplicate_names: set[str] = set()
    for raw in active_clients:
        patient_id = _patient_id_from_client(raw)
        if not patient_id:
            continue
        for alias in _client_aliases(raw):
            by_alias[alias] = patient_id
        name = _client_name(raw).strip().lower()
        if name:
            if name in by_name and by_name[name] != patient_id:
                duplicate_names.add(name)
            else:
                by_name[name] = patient_id
    for name in duplicate_names:
        by_name.pop(name, None)
    return by_alias, by_name


def _group_by_client(
    records: list[dict[str, Any]],
    *,
    by_alias: dict[str, str],
    by_name: dict[str, str],
    name_field: str = 'clientName',
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped = 0
    for record in records:
        patient_id = ''
        for alias in _nested_client_aliases(record):
            patient_id = by_alias.get(alias, '')
            if patient_id:
                break
        if not patient_id:
            name = _first_text(record, name_field).strip().lower()
            patient_id = by_name.get(name, '') if name else ''
        if patient_id:
            grouped[patient_id].append(record)
        else:
            unmapped += 1
    return dict(grouped), unmapped


def _plan_record_from_treatment_plan(raw: dict[str, Any]) -> TreatmentPlanRecord:
    is_initial = bool(raw.get('isInitialTP'))
    is_complete = bool(raw.get('isComplete'))
    client_signature = raw.get('clientSignature') if isinstance(raw.get('clientSignature'), dict) else {}
    staff_signature = raw.get('staffSignature') if isinstance(raw.get('staffSignature'), dict) else {}
    creator_signature = raw.get('creatorSignature') if isinstance(raw.get('creatorSignature'), dict) else {}
    signature_date = _date_text(client_signature.get('signatureDateTime')) if isinstance(client_signature, dict) else ''
    staff_signature_date = (
        _date_text(raw.get('staffSignatureDate') or raw.get('creatorSignatureDate') or raw.get('therapistSignatureDate'))
        or (_date_text(staff_signature.get('signatureDateTime')) if isinstance(staff_signature, dict) else '')
        or (_date_text(creator_signature.get('signatureDateTime')) if isinstance(creator_signature, dict) else '')
    )
    source_id = _first_text(raw, 'id', 'href')
    conflict = '' if is_complete else 'Alleva REST TreatmentPlan is not marked complete.'
    if is_complete and not signature_date:
        conflict = 'Alleva REST TreatmentPlan does not expose a client signature date in the mapped public schema.'
    if is_complete and signature_date and not staff_signature_date:
        conflict = 'Alleva REST TreatmentPlan does not expose a staff signature date in the mapped public schema.'
    return TreatmentPlanRecord(
        plan_kind=TreatmentPlanKind.initial if is_initial else TreatmentPlanKind.master,
        document_date=_date_text(raw.get('startDate') or raw.get('createdDate') or raw.get('lastModified')),
        staff_signature_date=staff_signature_date,
        client_signature_date=signature_date,
        reviewer_signature_date='',
        displayed_next_due_date='',
        source_evidence=f'{ALLEVA_REST_SOURCE} /treatment-plans record {source_id}',
        source_section=f'{ALLEVA_REST_SOURCE} treatment-plans',
        source_document_id=source_id,
        is_valid=is_complete,
        conflict_note=conflict,
    )


def _plan_record_from_treatment_review(raw: dict[str, Any]) -> TreatmentPlanRecord:
    source_id = _first_text(raw, 'id', 'treatmentPlanReviewId', 'href')
    return TreatmentPlanRecord(
        plan_kind=TreatmentPlanKind.review,
        document_date=_date_text(raw.get('createdDated') or raw.get('generatedDate')),
        staff_signature_date=_date_text(raw.get('creatorSignatureDate') or raw.get('ceratorSignatureDate')),
        client_signature_date=_date_text(raw.get('clientSignatureDate')),
        reviewer_signature_date=_date_text(raw.get('creatorSignatureDate') or raw.get('ceratorSignatureDate')),
        displayed_next_due_date=_date_text(raw.get('nextReviewDue')),
        source_evidence=f'{ALLEVA_REST_SOURCE} /treatment-reviews record {source_id}',
        source_section=f'{ALLEVA_REST_SOURCE} treatment-reviews',
        source_document_id=source_id,
        is_valid=bool(_date_text(raw.get('creatorSignatureDate') or raw.get('ceratorSignatureDate'))),
        conflict_note='' if _date_text(raw.get('creatorSignatureDate') or raw.get('ceratorSignatureDate')) else 'Alleva REST treatment review is missing creator signature date.',
    )


def sync_alleva_rest_payloads(
    db: Session,
    *,
    clients_payload: list[dict[str, Any]],
    treatment_plans_payload: list[dict[str, Any]],
    treatment_reviews_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    active_clients = [client for client in clients_payload if _is_active_client(client) and _patient_id_from_client(client)]
    by_alias, by_name = _client_lookup(active_clients)
    plans_by_client, unmapped_plans = _group_by_client(treatment_plans_payload, by_alias=by_alias, by_name=by_name, name_field='clientName')
    reviews_by_client, unmapped_reviews = _group_by_client(treatment_reviews_payload, by_alias=by_alias, by_name=by_name, name_field='clientName')

    touched_ids: list[int] = []
    for raw_client in active_clients:
        patient_id = _patient_id_from_client(raw_client)
        if not patient_id:
            continue
        client = (
            db.execute(
                select(TreatmentPlanClient)
                .options(selectinload(TreatmentPlanClient.level_of_care_history), selectinload(TreatmentPlanClient.treatment_plans))
                .where(TreatmentPlanClient.patient_id == patient_id)
            )
            .scalars()
            .unique()
            .one_or_none()
        )
        if client is None:
            client = TreatmentPlanClient(patient_id=patient_id)
            db.add(client)
            db.flush()

        display_name = _client_name(raw_client)
        client.permitted_name = display_name or display_name_for_patient_name_status(NAME_NOT_FOUND_STATUS, patient_id=patient_id)
        client.is_active = True
        client.current_level_of_care = _first_text(raw_client, 'levelOfCare')
        client.counselor_name = _first_text(raw_client, 'primaryClinicians', 'medicalProviders')
        client.admission_date = _date_text(raw_client.get('admissionDateTime') or raw_client.get('admissionDate'))
        client.source_note_set_id = None
        client.source_evidence = f'{ALLEVA_REST_SOURCE} /clients record {patient_id}'
        client.last_imported_at = _utc_now()
        client.updated_at = _utc_now()

        db.execute(delete(LevelOfCareHistory).where(LevelOfCareHistory.client_id == client.id, LevelOfCareHistory.source_evidence.like(f'{ALLEVA_REST_SOURCE}%')))
        db.execute(delete(TreatmentPlanRecord).where(TreatmentPlanRecord.client_id == client.id, TreatmentPlanRecord.source_section.like(f'{ALLEVA_REST_SOURCE}%')))
        db.flush()

        if client.current_level_of_care:
            client.level_of_care_history.append(
                LevelOfCareHistory(
                    level_of_care=client.current_level_of_care,
                    facility=_first_text(raw_client, 'facilityName'),
                    effective_date=client.admission_date,
                    discharge_date='',
                    source_evidence=f'{ALLEVA_REST_SOURCE} /clients levelOfCare record {patient_id}',
                )
            )

        for raw_plan in plans_by_client.get(patient_id, []):
            client.treatment_plans.append(_plan_record_from_treatment_plan(raw_plan))
        for raw_review in reviews_by_client.get(patient_id, []):
            client.treatment_plans.append(_plan_record_from_treatment_review(raw_review))
        touched_ids.append(client.id)

    return {
        'active_client_count': len(active_clients),
        'upserted_client_count': len(touched_ids),
        'treatment_plan_count': len(treatment_plans_payload),
        'treatment_review_count': len(treatment_reviews_payload),
        'unmapped_treatment_plan_count': unmapped_plans,
        'unmapped_treatment_review_count': unmapped_reviews,
        'client_ids': touched_ids,
    }


def run_alleva_treatment_plan_sync(
    db: Session,
    settings_row: AppSetting,
    *,
    actor: User | None = None,
    startup: bool = False,
) -> dict[str, Any]:
    if not settings_row.alleva_treatment_plan_sync_enabled:
        return {'status': 'skipped', 'message': 'Alleva treatment-plan REST sync is disabled.'}
    if startup and not settings_row.alleva_treatment_plan_sync_on_startup:
        return {'status': 'skipped', 'message': 'Alleva treatment-plan REST sync on startup is disabled.'}

    missing = _missing_sync_configuration(settings_row, startup=startup)
    if missing:
        status = 'blocked'
        message = f'Alleva treatment-plan REST sync {status}; missing {", ".join(missing)}.'
        _mark_status(db, settings_row, status=status, message=message)
        log_event(
            db,
            action='alleva.treatment_plan_sync.blocked' if status == 'blocked' else 'alleva.treatment_plan_sync.skipped',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details={'missing_fields': missing, 'startup': startup},
            outcome_status='failure' if status == 'blocked' else 'success',
            severity='warning' if status == 'blocked' else 'info',
            message=message,
        )
        return {'status': status, 'message': message, 'missing_fields': missing}

    client_secret = decrypt_text_secret(settings_row.api_client_secret)
    token_result, bearer_token = request_client_credentials_token(
        token_url=settings_row.api_oauth_token_url,
        client_id=settings_row.api_client_id,
        client_secret=client_secret,
        scope='',
        timeout_seconds=settings_row.emr_api_timeout_seconds,
        token_auth_style=settings_row.api_token_auth_style,
    )
    if not bearer_token:
        message = token_result.get('message') or 'Alleva token request failed.'
        _mark_status(db, settings_row, status='fail', message=message)
        log_event(
            db,
            action='alleva.treatment_plan_sync.auth_failed',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details={'startup': startup, 'token_status': token_result.get('status')},
            outcome_status='failure',
            severity='error',
            message=message,
        )
        return {'status': 'fail', 'message': message, 'token_result': token_result}

    try:
        limit = max(1, min(settings_row.alleva_treatment_plan_sync_limit or 250, 5000))
        base_url = settings_row.alleva_api_base_url.strip() or DEFAULT_ALLEVA_API_BASE_URL
        api_version = settings_row.alleva_api_version.strip() or '1.0'
        clients = _fetch_collection(base_url=base_url, path=SYNC_ENDPOINTS['clients'], bearer_token=bearer_token, api_version=api_version, limit=limit, timeout_seconds=settings_row.emr_api_timeout_seconds)
        treatment_plans = _fetch_collection(base_url=base_url, path=SYNC_ENDPOINTS['treatment_plans'], bearer_token=bearer_token, api_version=api_version, limit=limit, timeout_seconds=settings_row.emr_api_timeout_seconds)
        treatment_reviews = _fetch_collection(base_url=base_url, path=SYNC_ENDPOINTS['treatment_reviews'], bearer_token=bearer_token, api_version=api_version, limit=limit, timeout_seconds=settings_row.emr_api_timeout_seconds)
        summary = sync_alleva_rest_payloads(db, clients_payload=clients, treatment_plans_payload=treatment_plans, treatment_reviews_payload=treatment_reviews)
        db.commit()
        touched_clients = (
            db.execute(
                select(TreatmentPlanClient)
                .options(selectinload(TreatmentPlanClient.level_of_care_history), selectinload(TreatmentPlanClient.treatment_plans), selectinload(TreatmentPlanClient.overrides))
                .where(TreatmentPlanClient.id.in_(summary['client_ids']))
            )
            .scalars()
            .unique()
            .all()
            if summary['client_ids']
            else []
        )
        workflow_context = current_treatment_plan_workflow_context(db)
        for synced_client in touched_clients:
            evaluation = evaluate_client(synced_client, settings_row)
            log_event(
                db,
                action='alleva.treatment_plan_sync.analysis_result',
                actor=actor,
                event_category='workflow',
                target_entity=f'treatment_plan_client:{synced_client.id}',
                target_entity_type='treatment_plan_client',
                target_entity_id=str(synced_client.id),
                patient_id=synced_client.patient_id,
                details={
                    'status': evaluation.status,
                    'next_due_date': evaluation.next_due_date,
                    'rule_used': evaluation.rule_used,
                    'current_date': evaluation.current_date,
                    'workflow': workflow_context,
                    'startup': startup,
                },
                message='Alleva REST treatment-plan sync analyzed one active client with R3 compliance rules.',
            )
        message = (
            f'Alleva treatment-plan REST sync completed; {summary["upserted_client_count"]} active client(s) loaded, '
            f'{summary["treatment_plan_count"]} treatment plan record(s), {summary["treatment_review_count"]} review record(s).'
        )
        _mark_status(db, settings_row, status='ok', message=message)
        log_event(
            db,
            action='alleva.treatment_plan_sync.completed',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details={key: value for key, value in summary.items() if key != 'client_ids'} | {'startup': startup},
            message=message,
        )
        return {'status': 'ok', 'message': message, **{key: value for key, value in summary.items() if key != 'client_ids'}}
    except Exception as exc:
        message = f'Alleva treatment-plan REST sync failed: {exc.__class__.__name__}.'
        logger.warning('Alleva treatment-plan REST sync failed', exc_info=True)
        db.rollback()
        _mark_status(db, settings_row, status='fail', message=message)
        log_event(
            db,
            action='alleva.treatment_plan_sync.failed',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details={'startup': startup, 'exception_type': exc.__class__.__name__},
            outcome_status='failure',
            severity='error',
            message=message,
        )
        return {'status': 'fail', 'message': message, 'exception_type': exc.__class__.__name__}
