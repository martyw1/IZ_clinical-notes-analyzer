from __future__ import annotations

import logging
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import quote, urljoin

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.models import AppSetting, LevelOfCareHistory, TreatmentPlanClient, TreatmentPlanKind, TreatmentPlanRecord, User
from app.services.api_connectivity import request_client_credentials_token, redact_url
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
    'treatment_plan_detail': '/treatment-plans/{id}',
    'treatment_plan_diagnosis': '/treatment-plans/{id}/diagnosis',
    'treatment_reviews': '/treatment-reviews',
    'treatment_review_detail': '/treatment-reviews/{id}',
}


class AllevaSyncExternalError(Exception):
    def __init__(
        self,
        public_message: str,
        *,
        stage: str,
        category: str,
        endpoint: str = '',
        status_code: int | None = None,
        status: str = 'fail',
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.stage = stage
        self.category = category
        self.endpoint = endpoint
        self.status_code = status_code
        self.status = status


@dataclass
class GroupByClientResult:
    records_by_client: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unmapped_count: int = 0
    unmapped_record_ids: list[dict[str, str]] = field(default_factory=list)
    confidence_by_client: dict[str, str] = field(default_factory=dict)
    name_fallback_count: int = 0


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


def _bool_value(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {'true', '1', 'yes', 'y', 'active', 'complete', 'completed'}:
        return True
    if text in {'false', '0', 'no', 'n', 'inactive', 'discharged', 'closed', 'deceased', 'incomplete'}:
        return False
    return default


def _date_text(value: Any) -> str:
    raw = _strip(value)
    if not raw:
        return ''
    if 'T' in raw:
        return raw.split('T', 1)[0]
    if ' ' in raw and raw[:10].count('-') == 2:
        return raw[:10]
    return raw


def _date_value(value: Any) -> date | None:
    raw = _date_text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _json_list(values: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(item for item in values if item)), separators=(',', ':'))


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


def _join_candidates(payload: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for key, confidence in (('clientId', 'clientId_match'), ('leadId', 'leadId_match'), ('patientId', 'id_match')):
        value = _strip(payload.get(key))
        if value:
            candidates.append((value, confidence))
    client = payload.get('client')
    if isinstance(client, dict):
        for key, confidence in (
            ('clientId', 'clientId_match'),
            ('leadId', 'leadId_match'),
            ('id', 'id_match'),
            ('uniqueId', 'id_match'),
            ('mrn', 'id_match'),
        ):
            value = _strip(client.get(key))
            if value:
                candidates.append((value, confidence))
    return list(dict.fromkeys(candidates))


def _confidence_rank(value: str) -> int:
    return {
        'clientId_match': 4,
        'leadId_match': 3,
        'id_match': 2,
        'name_fallback': 1,
        'unknown': 0,
    }.get(value, 0)


def _record_public_ids(record: dict[str, Any]) -> dict[str, str]:
    client = record.get('client') if isinstance(record.get('client'), dict) else {}
    return {
        'record_id': _first_text(record, 'id', 'treatmentPlanId', 'treatmentPlanReviewId', 'href'),
        'client_id': _first_text(record, 'clientId') or (_first_text(client, 'clientId') if isinstance(client, dict) else ''),
        'source_client_id': _first_text(record, 'patientId') or (_first_text(client, 'id') if isinstance(client, dict) else ''),
        'lead_id': _first_text(record, 'leadId') or (_first_text(client, 'leadId') if isinstance(client, dict) else ''),
    }


def _is_active_client(payload: dict[str, Any]) -> bool:
    status = _first_text(payload, 'status', 'statusName').lower()
    if status and any(word in status for word in ('discharge', 'inactive', 'closed', 'deceased')):
        return False
    status_is_active = bool(status and 'active' in status)
    if _bool_value(payload.get('isDischarge'), default=False) and not status_is_active:
        return False
    if not status and (_strip(payload.get('dischargeDateTime')) or _strip(payload.get('actualSysDischargeDateTime'))):
        return False
    if payload.get('isClient') is not None and not _bool_value(payload.get('isClient'), default=True) and not status_is_active:
        return False
    return True


def _active_client_warnings(payload: dict[str, Any]) -> tuple[list[str], bool]:
    warnings: list[str] = []
    status = _first_text(payload, 'status', 'statusName').lower()
    discharge_fields_present = bool(
        _strip(payload.get('dischargeDateTime'))
        or _strip(payload.get('actualSysDischargeDateTime'))
        or _bool_value(payload.get('isDischarge'), default=False)
    )
    discharge_conflict = bool(status and 'active' in status and discharge_fields_present)
    if discharge_conflict:
        warnings.append('active_status_discharge_field_conflict')
    return warnings, discharge_conflict


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


def _http_status_label(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = ''
    return f'HTTP {status_code}{f" {phrase}" if phrase else ""}'


def _endpoint_http_failure_message(*, path: str, status_code: int, api_version: str) -> tuple[str, str]:
    status_label = _http_status_label(status_code)
    if status_code == 401:
        return (
            'endpoint_authorization_failed',
            (
                f'The Alleva token request succeeded, but Alleva rejected access to GET {path} with {status_label}. '
                f'Ask R3/Alleva to confirm this client ID has tenant access and read permission for {path}, '
                f'that the token audience/scope is correct, and that API version {api_version} is approved for this endpoint.'
            ),
        )
    if status_code == 403:
        return (
            'endpoint_permission_denied',
            (
                f'The Alleva token request succeeded, but the saved credentials are not permitted to read GET {path} '
                f'({status_label}). Ask R3/Alleva to add the required read permission/scope for API version {api_version}.'
            ),
        )
    if status_code in {400, 404, 405}:
        return (
            'endpoint_mapping_or_version_failed',
            (
                f'Alleva rejected GET {path} with {status_label}. Confirm the endpoint path, Limit/Cursor/api-version '
                f'parameters, X-Version header, and API version {api_version} against the approved Alleva mapping.'
            ),
        )
    if status_code == 429:
        return (
            'endpoint_rate_limited',
            f'Alleva rate-limited GET {path} ({status_label}). Wait and try again, or ask Alleva about rate limits for this tenant.',
        )
    if 500 <= status_code <= 599:
        return (
            'endpoint_vendor_unavailable',
            f'Alleva returned {status_label} for GET {path}. This looks like a vendor-side or temporary service problem; try again later.',
        )
    return (
        'endpoint_request_failed',
        (
            f'Alleva returned {status_label} for GET {path}. Confirm the saved credentials, endpoint path, API version, '
            'and tenant permissions before running sync again.'
        ),
    )


def _raise_request_failure(*, path: str, api_version: str, exc: httpx.RequestError) -> None:
    if isinstance(exc, httpx.TimeoutException):
        raise AllevaSyncExternalError(
            f'Alleva did not respond before the configured timeout while reading GET {path}. Increase the timeout or try again when the network is stable.',
            stage='endpoint_request',
            category='network_timeout',
            endpoint=path,
        ) from exc
    raise AllevaSyncExternalError(
        f'The app could not reach Alleva GET {path}. Check internet access, the REST API base URL, and local firewall/proxy settings.',
        stage='endpoint_request',
        category='network_failure',
        endpoint=path,
    ) from exc


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
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for _page in range(max_pages):
            params = {'Limit': page_size, 'Cursor': cursor, 'api-version': api_version}
            try:
                response = client.get(url, headers=headers, params=params)
                response.read()
            except httpx.RequestError as exc:
                _raise_request_failure(path=path, api_version=api_version, exc=exc)
            if not 200 <= response.status_code < 300:
                category, message = _endpoint_http_failure_message(path=path, status_code=response.status_code, api_version=api_version)
                logger.warning('Alleva treatment-plan sync endpoint returned %s for %s url=%s', response.status_code, path, redact_url(str(response.url)))
                raise AllevaSyncExternalError(
                    message,
                    stage='endpoint_request',
                    category=category,
                    endpoint=path,
                    status_code=response.status_code,
                )
            try:
                page_records = _extract_records(response.json())
            except ValueError as exc:
                raise AllevaSyncExternalError(
                    f'Alleva GET {path} responded, but the response was not JSON. Confirm this endpoint path and API version {api_version}.',
                    stage='endpoint_response',
                    category='endpoint_non_json_response',
                    endpoint=path,
                    status_code=response.status_code,
                ) from exc
            records.extend(page_records)
            if len(page_records) < page_size or len(records) >= limit:
                break
            cursor += page_size
    return records[:limit]


def _fetch_detail(
    *,
    base_url: str,
    path: str,
    bearer_token: str,
    api_version: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    url = _endpoint_url(base_url, path)
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {bearer_token}',
        'X-Version': api_version,
    }
    params = {'api-version': api_version}
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        try:
            response = client.get(url, headers=headers, params=params)
            response.read()
        except httpx.RequestError as exc:
            _raise_request_failure(path=path, api_version=api_version, exc=exc)
        if not 200 <= response.status_code < 300:
            category, message = _endpoint_http_failure_message(path=path, status_code=response.status_code, api_version=api_version)
            logger.warning('Alleva treatment-plan sync detail endpoint returned %s for %s url=%s', response.status_code, path, redact_url(str(response.url)))
            raise AllevaSyncExternalError(
                message,
                stage='endpoint_request',
                category=category,
                endpoint=path,
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AllevaSyncExternalError(
                f'Alleva GET {path} responded, but the response was not JSON. Confirm this endpoint path and API version {api_version}.',
                stage='endpoint_response',
                category='endpoint_non_json_response',
                endpoint=path,
                status_code=response.status_code,
            ) from exc
    if isinstance(payload, dict):
        for key in ('data', 'result', 'record'):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        return payload
    if isinstance(payload, list):
        return {'items': [item for item in payload if isinstance(item, dict)]}
    raise AllevaSyncExternalError(
        f'Alleva GET {path} returned JSON, but not a resource object the app can map.',
        stage='endpoint_response',
        category='endpoint_unexpected_json_shape',
        endpoint=path,
        status_code=response.status_code,
    )


def _fetch_optional_collection(
    *,
    base_url: str,
    path: str,
    bearer_token: str,
    api_version: str,
    limit: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        return (
            _fetch_collection(
                base_url=base_url,
                path=path,
                bearer_token=bearer_token,
                api_version=api_version,
                limit=limit,
                timeout_seconds=timeout_seconds,
            ),
            None,
        )
    except AllevaSyncExternalError as exc:
        logger.warning(
            'Alleva treatment-plan sync optional endpoint skipped stage=%s category=%s endpoint=%s status_code=%s',
            exc.stage,
            exc.category,
            exc.endpoint,
            exc.status_code,
        )
        status_label = _http_status_label(exc.status_code) if exc.status_code is not None else exc.category.replace('_', ' ')
        return [], {
            'endpoint': exc.endpoint or path,
            'failure_stage': exc.stage,
            'category': exc.category,
            'status_code': exc.status_code,
            'message': (
                f'Optional Alleva treatment-review endpoint {path} could not be read ({status_label}). '
                'The app continued with /clients and /treatment-plans only.'
            ),
        }


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
    if status in {'ok', 'warn'}:
        settings_row.alleva_treatment_plan_sync_last_success_at = now
    elif status in {'fail', 'blocked'}:
        settings_row.alleva_treatment_plan_sync_last_failure_at = now
    db.commit()


def _client_lookup(active_clients: list[dict[str, Any]], *, include_names: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    by_alias: dict[str, str] = {}
    by_name: dict[str, str] = {}
    duplicate_names: set[str] = set()
    for raw in active_clients:
        patient_id = _patient_id_from_client(raw)
        if not patient_id:
            continue
        for alias in _client_aliases(raw):
            by_alias[alias] = patient_id
        if not include_names:
            continue
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
) -> GroupByClientResult:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped_record_ids: list[dict[str, str]] = []
    confidence_by_client: dict[str, str] = {}
    name_fallback_count = 0
    for record in records:
        patient_id = ''
        confidence = 'unknown'
        for alias, candidate_confidence in _join_candidates(record):
            patient_id = by_alias.get(alias, '')
            if patient_id:
                confidence = candidate_confidence
                break
        if not patient_id:
            name = _first_text(record, name_field).strip().lower()
            patient_id = by_name.get(name, '') if name else ''
            if patient_id:
                confidence = 'name_fallback'
                name_fallback_count += 1
        if patient_id:
            grouped[patient_id].append(record)
            previous = confidence_by_client.get(patient_id, 'unknown')
            if _confidence_rank(confidence) > _confidence_rank(previous):
                confidence_by_client[patient_id] = confidence
        else:
            unmapped_record_ids.append(_record_public_ids(record))
    return GroupByClientResult(
        records_by_client=dict(grouped),
        unmapped_count=len(unmapped_record_ids),
        unmapped_record_ids=unmapped_record_ids,
        confidence_by_client=confidence_by_client,
        name_fallback_count=name_fallback_count,
    )


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _content_counts(raw: dict[str, Any]) -> dict[str, int]:
    problems = [item for item in _list_value(raw.get('problems')) if isinstance(item, dict)]
    problem_count = len(problems)
    diagnosis_count = sum(len(_list_value(problem.get('diagnoses'))) for problem in problems)
    if not diagnosis_count:
        diagnosis_count = len(_list_value(raw.get('diagnoses'))) or len(_list_value(raw.get('diagnosis'))) or len(_list_value(raw.get('items')))
    goals = [goal for problem in problems for goal in _list_value(problem.get('goals')) if isinstance(goal, dict)]
    objectives = [objective for goal in goals for objective in _list_value(goal.get('objectives')) if isinstance(objective, dict)]
    interventions = [intervention for objective in objectives for intervention in _list_value(objective.get('interventions')) if isinstance(intervention, dict)]
    return {
        'problem_count': problem_count,
        'diagnosis_count': diagnosis_count,
        'goal_count': len(goals),
        'objective_count': len(objectives),
        'intervention_count': len(interventions),
    }


def _signature_date(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):
            date_value = _date_text(value.get('signatureDateTime') or value.get('signedAt') or value.get('date'))
        else:
            date_value = _date_text(value)
        if date_value:
            return date_value
    return ''


def _merge_plan_detail(raw_plan: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    if not detail:
        return raw_plan
    merged = {**raw_plan, **detail}
    merged['_detail_fetched'] = True
    merged['_content_source'] = 'detail'
    return merged


def _select_current_plan(plans: list[dict[str, Any]], *, today: date | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not plans:
        return None, []
    today = today or _utc_now().date()
    active = [plan for plan in plans if _bool_value(plan.get('isActive'), default=True)]
    if not active:
        return None, list(plans)

    def key(plan: dict[str, Any]) -> tuple[int, date, date, date, str]:
        end_date = _date_value(plan.get('endDate'))
        current_window = 1 if end_date is None or end_date >= today else 0
        return (
            current_window,
            _date_value(plan.get('startDate')) or date.min,
            _date_value(plan.get('lastModified')) or date.min,
            _date_value(plan.get('createdDate')) or date.min,
            _first_text(plan, 'id', 'href'),
        )

    current = sorted(active, key=key, reverse=True)[0]
    historical = [plan for plan in plans if plan is not current]
    return current, historical


def _plan_record_from_treatment_plan(raw: dict[str, Any]) -> TreatmentPlanRecord:
    is_initial = _bool_value(raw.get('isInitialTP'), default=False)
    is_complete = _bool_value(raw.get('isComplete'), default=False)
    is_active = _bool_value(raw.get('isActive'), default=True)
    client_signature = raw.get('clientSignature') if isinstance(raw.get('clientSignature'), dict) else {}
    staff_signature = raw.get('staffSignature') if isinstance(raw.get('staffSignature'), dict) else {}
    creator_signature = raw.get('creatorSignature') if isinstance(raw.get('creatorSignature'), dict) else {}
    guardian_signature = raw.get('guardianSignature') if isinstance(raw.get('guardianSignature'), dict) else {}
    signature_date = (
        _date_text(raw.get('clientSignatureDate'))
        or (_date_text(client_signature.get('signatureDateTime')) if isinstance(client_signature, dict) else '')
    )
    staff_signature_date = (
        _date_text(raw.get('staffSignatureDate') or raw.get('creatorSignatureDate') or raw.get('therapistSignatureDate'))
        or (_date_text(staff_signature.get('signatureDateTime')) if isinstance(staff_signature, dict) else '')
        or (_date_text(creator_signature.get('signatureDateTime')) if isinstance(creator_signature, dict) else '')
    )
    guardian_signature_date = _signature_date(raw, 'guardianSignatureDate', 'guardianSignature')
    source_id = _first_text(raw, 'id', 'href')
    counts = _content_counts(raw)
    detail_fetched = bool(raw.get('_detail_fetched'))
    conflict = '' if is_complete else 'Alleva REST TreatmentPlan is not marked complete.'
    if is_complete and not signature_date:
        conflict = 'Alleva REST TreatmentPlan does not expose a client signature date in the mapped public schema.'
    if is_complete and signature_date and not staff_signature_date:
        conflict = 'Alleva REST TreatmentPlan does not expose a staff signature date in the mapped public schema.'
    if is_complete and detail_fetched and not (counts['problem_count'] or counts['diagnosis_count']):
        conflict = 'Plan marked isComplete but has no documented problems or diagnoses.'
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
        problem_count=counts['problem_count'],
        diagnosis_count=counts['diagnosis_count'],
        goal_count=counts['goal_count'],
        objective_count=counts['objective_count'],
        intervention_count=counts['intervention_count'],
        has_guardian_signature=bool(guardian_signature_date or guardian_signature),
        guardian_signature_date=guardian_signature_date,
        alleva_is_active=is_active,
        alleva_is_complete=is_complete,
        alleva_is_initial_tp=is_initial,
        alleva_start_date=_date_text(raw.get('startDate')),
        alleva_end_date=_date_text(raw.get('endDate')),
        alleva_last_modified=_date_text(raw.get('lastModified')),
        detail_fetched=detail_fetched,
        detail_fetched_at=_utc_now() if detail_fetched else None,
        content_source=_first_text(raw, '_content_source') or ('detail' if detail_fetched else 'collection'),
    )


def _plan_record_from_treatment_review(raw: dict[str, Any]) -> TreatmentPlanRecord:
    source_id = _first_text(raw, 'id', 'treatmentPlanReviewId', 'href')
    document_date = _date_text(raw.get('createdDated') or raw.get('createdDate') or raw.get('generatedDate') or raw.get('documentDate'))
    staff_signature_date = _date_text(
        raw.get('creatorSignatureDate')
        or raw.get('ceratorSignatureDate')
        or raw.get('staffSignatureDate')
        or raw.get('therapistSignatureDate')
        or raw.get('reviewerSignatureDate')
    )
    return TreatmentPlanRecord(
        plan_kind=TreatmentPlanKind.review,
        document_date=document_date,
        staff_signature_date=staff_signature_date,
        client_signature_date=_date_text(raw.get('clientSignatureDate')),
        reviewer_signature_date=_date_text(raw.get('reviewerSignatureDate') or raw.get('creatorSignatureDate') or raw.get('ceratorSignatureDate')),
        displayed_next_due_date=_date_text(raw.get('nextReviewDue') or raw.get('nextReviewDueDate') or raw.get('displayedNextReviewDueDate')),
        source_evidence=f'{ALLEVA_REST_SOURCE} /treatment-reviews record {source_id}',
        source_section=f'{ALLEVA_REST_SOURCE} treatment-reviews',
        source_document_id=source_id,
        is_valid=bool(staff_signature_date),
        conflict_note='' if staff_signature_date else 'Alleva REST treatment review is missing creator/staff/reviewer signature date.',
    )


def sync_alleva_rest_payloads(
    db: Session,
    *,
    clients_payload: list[dict[str, Any]],
    treatment_plans_payload: list[dict[str, Any]],
    treatment_reviews_payload: list[dict[str, Any]],
    plan_detail_fetcher: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    detail_fetch_limit: int = 0,
    patient_name_import_enabled: bool = False,
    name_join_fallback_enabled: bool = False,
    actor: User | None = None,
) -> dict[str, Any]:
    active_clients = [client for client in clients_payload if _is_active_client(client) and _patient_id_from_client(client)]
    by_alias, by_name_for_matching = _client_lookup(active_clients, include_names=name_join_fallback_enabled)
    plans_group = _group_by_client(treatment_plans_payload, by_alias=by_alias, by_name=by_name_for_matching, name_field='clientName')
    reviews_group = _group_by_client(treatment_reviews_payload, by_alias=by_alias, by_name=by_name_for_matching, name_field='clientName')
    for record_ids in plans_group.unmapped_record_ids:
        log_event(
            db,
            action='alleva.treatment_plan_sync.unmapped_plan',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details=record_ids,
            outcome_status='failure',
            severity='warning',
            message='Alleva treatment plan record could not be matched to an active client by approved ID fields.',
        )
    for record_ids in reviews_group.unmapped_record_ids:
        log_event(
            db,
            action='alleva.treatment_plan_sync.unmapped_review',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details=record_ids,
            outcome_status='failure',
            severity='warning',
            message='Alleva treatment review record could not be matched to an active client by approved ID fields.',
        )

    touched_ids: list[int] = []
    detail_fetch_attempt_count = 0
    detail_fetch_success_count = 0
    detail_fetch_failed_count = 0
    current_plan_selected_count = 0
    current_plan_missing_count = 0
    detail_limit = max(0, detail_fetch_limit)
    for raw_client in active_clients:
        patient_id = _patient_id_from_client(raw_client)
        if not patient_id:
            continue
        client = (
            db.execute(
                select(TreatmentPlanClient)
                .options(selectinload(TreatmentPlanClient.level_of_care_history), selectinload(TreatmentPlanClient.treatment_plans), selectinload(TreatmentPlanClient.current_plan_record))
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

        warnings, discharge_conflict = _active_client_warnings(raw_client)
        display_name = _client_name(raw_client) if patient_name_import_enabled else ''
        client.permitted_name = display_name or display_name_for_patient_name_status(NAME_NOT_FOUND_STATUS, patient_id=patient_id)
        client.is_active = True
        client.current_level_of_care = _first_text(raw_client, 'levelOfCare')
        client.counselor_name = _first_text(raw_client, 'primaryClinicians', 'medicalProviders')
        client.admission_date = _date_text(raw_client.get('admissionDateTime') or raw_client.get('admissionDate'))
        client.source_note_set_id = None
        client.source_evidence = f'{ALLEVA_REST_SOURCE} /clients record {patient_id}'
        client.alleva_source_id = _first_text(raw_client, 'id')
        client.alleva_client_id = _first_text(raw_client, 'clientId')
        client.alleva_lead_id = _first_text(raw_client, 'leadId')
        client.alleva_unique_id = _first_text(raw_client, 'uniqueId')
        client.alleva_mrn = _first_text(raw_client, 'mrn')
        plan_confidence = plans_group.confidence_by_client.get(patient_id, '')
        review_confidence = reviews_group.confidence_by_client.get(patient_id, '')
        client.id_join_confidence = max([plan_confidence, review_confidence, 'unknown'], key=_confidence_rank)
        client.id_join_warnings = _json_list(['name_join_fallback_used'] if client.id_join_confidence == 'name_fallback' else [])
        client.discharge_conflict = discharge_conflict
        client.last_imported_at = _utc_now()
        client.updated_at = _utc_now()

        client.current_plan_record_id = None
        db.flush()
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

        current_plan, historical_plans = _select_current_plan(plans_group.records_by_client.get(patient_id, []))
        current_plan_record: TreatmentPlanRecord | None = None
        if current_plan is None:
            warnings.append('no_current_active_plan')
            current_plan_missing_count += 1
        else:
            current_plan_selected_count += 1
            if plan_detail_fetcher is not None and detail_limit and detail_fetch_attempt_count < detail_limit:
                detail_fetch_attempt_count += 1
                try:
                    current_plan = _merge_plan_detail(current_plan, plan_detail_fetcher(current_plan))
                    if current_plan.get('_detail_fetched'):
                        detail_fetch_success_count += 1
                except AllevaSyncExternalError as exc:
                    detail_fetch_failed_count += 1
                    warnings.append('current_plan_detail_fetch_failed')
                    log_event(
                        db,
                        action='alleva.treatment_plan_detail_fetch.failed',
                        actor=actor,
                        event_category='integration',
                        target_entity=f'treatment_plan:{_first_text(current_plan, "id", "href")}',
                        target_entity_type='alleva_treatment_plan',
                        details={
                            'treatment_plan_id': _first_text(current_plan, 'id', 'href'),
                            'endpoint': exc.endpoint,
                            'category': exc.category,
                            'status_code': exc.status_code,
                        },
                        outcome_status='failure',
                        severity='warning',
                        message='Alleva current treatment plan detail could not be fetched; collection-level plan data was retained.',
                    )
                except Exception as exc:
                    detail_fetch_failed_count += 1
                    warnings.append('current_plan_detail_fetch_failed')
                    logger.exception('Unexpected Alleva treatment-plan detail fetch failure for plan %s', _first_text(current_plan, 'id', 'href'))
                    log_event(
                        db,
                        action='alleva.treatment_plan_detail_fetch.failed',
                        actor=actor,
                        event_category='integration',
                        target_entity=f'treatment_plan:{_first_text(current_plan, "id", "href")}',
                        target_entity_type='alleva_treatment_plan',
                        details={'treatment_plan_id': _first_text(current_plan, 'id', 'href'), 'category': exc.__class__.__name__},
                        outcome_status='failure',
                        severity='warning',
                        message='Alleva current treatment plan detail fetch failed unexpectedly; collection-level plan data was retained.',
                    )

        for raw_plan in ([current_plan] if current_plan is not None else []) + historical_plans:
            record = _plan_record_from_treatment_plan(raw_plan)
            client.treatment_plans.append(record)
            if raw_plan is current_plan:
                current_plan_record = record
        for raw_review in reviews_group.records_by_client.get(patient_id, []):
            client.treatment_plans.append(_plan_record_from_treatment_review(raw_review))
        client.data_quality_warnings = _json_list(warnings)
        db.flush()
        if current_plan_record is not None:
            client.current_plan_record_id = current_plan_record.id
        touched_ids.append(client.id)

    return {
        'active_client_count': len(active_clients),
        'upserted_client_count': len(touched_ids),
        'treatment_plan_count': len(treatment_plans_payload),
        'treatment_review_count': len(treatment_reviews_payload),
        'unmapped_treatment_plan_count': plans_group.unmapped_count,
        'unmapped_treatment_review_count': reviews_group.unmapped_count,
        'unmapped_plan_ids': plans_group.unmapped_record_ids,
        'unmapped_review_ids': reviews_group.unmapped_record_ids,
        'name_join_fallback_count': plans_group.name_fallback_count + reviews_group.name_fallback_count,
        'current_plan_selected_count': current_plan_selected_count,
        'current_plan_missing_count': current_plan_missing_count,
        'detail_fetch_enabled': plan_detail_fetcher is not None and detail_limit > 0,
        'detail_fetch_attempt_count': detail_fetch_attempt_count,
        'detail_fetch_success_count': detail_fetch_success_count,
        'detail_fetch_failed_count': detail_fetch_failed_count,
        'detail_fetch_skipped_count': max(0, current_plan_selected_count - detail_fetch_attempt_count),
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
        message = 'Alleva treatment-plan sync is off in App Settings. Turn on Enable Alleva REST treatment-plan sync, save settings, then run again.'
        _mark_status(db, settings_row, status='skipped', message=message)
        return {'status': 'skipped', 'message': message}
    if startup and not settings_row.alleva_treatment_plan_sync_on_startup:
        message = 'Alleva treatment-plan sync on app startup is off in App Settings.'
        _mark_status(db, settings_row, status='skipped', message=message)
        return {'status': 'skipped', 'message': message}

    missing = _missing_sync_configuration(settings_row, startup=startup)
    if missing:
        status = 'blocked'
        message = f'Alleva treatment-plan sync is blocked until these App Settings are saved or confirmed: {", ".join(missing)}.'
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
        message = f"Alleva authentication failed before sync could read endpoints: {token_result.get('message') or 'token request did not return an access token.'}"
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
        return {'status': 'fail', 'message': message, 'failure_stage': 'token_request', 'category': 'token_request_failed', 'token_result': token_result}

    try:
        limit = max(1, min(settings_row.alleva_treatment_plan_sync_limit or 250, 5000))
        base_url = settings_row.alleva_api_base_url.strip() or DEFAULT_ALLEVA_API_BASE_URL
        api_version = settings_row.alleva_api_version.strip() or '1.0'
        clients = _fetch_collection(base_url=base_url, path=SYNC_ENDPOINTS['clients'], bearer_token=bearer_token, api_version=api_version, limit=limit, timeout_seconds=settings_row.emr_api_timeout_seconds)
        treatment_plans = _fetch_collection(base_url=base_url, path=SYNC_ENDPOINTS['treatment_plans'], bearer_token=bearer_token, api_version=api_version, limit=limit, timeout_seconds=settings_row.emr_api_timeout_seconds)
        treatment_reviews, optional_review_failure = _fetch_optional_collection(
            base_url=base_url,
            path=SYNC_ENDPOINTS['treatment_reviews'],
            bearer_token=bearer_token,
            api_version=api_version,
            limit=limit,
            timeout_seconds=settings_row.emr_api_timeout_seconds,
        )
        plan_detail_fetcher = None
        if settings_row.alleva_treatment_plan_detail_fetch_enabled:
            def plan_detail_fetcher(raw_plan: dict[str, Any]) -> dict[str, Any] | None:
                plan_id = _first_text(raw_plan, 'id', 'treatmentPlanId')
                if not plan_id:
                    raise AllevaSyncExternalError(
                        'Alleva treatment-plan detail fetch could not run because the selected current plan has no ID.',
                        stage='endpoint_request',
                        category='missing_treatment_plan_id',
                        endpoint=SYNC_ENDPOINTS['treatment_plan_detail'],
                        status='warn',
                    )
                encoded_id = quote(plan_id, safe='')
                detail_path = SYNC_ENDPOINTS['treatment_plan_detail'].format(id=encoded_id)
                log_event(
                    db,
                    action='alleva.treatment_plan_detail_fetch.attempted',
                    actor=actor,
                    event_category='integration',
                    target_entity=f'treatment_plan:{plan_id}',
                    target_entity_type='alleva_treatment_plan',
                    details={'treatment_plan_id': plan_id, 'endpoint': detail_path},
                    message='Fetching Alleva current treatment plan detail for nested clinical content.',
                )
                detail = _fetch_detail(
                    base_url=base_url,
                    path=detail_path,
                    bearer_token=bearer_token,
                    api_version=api_version,
                    timeout_seconds=settings_row.emr_api_timeout_seconds,
                )
                counts = _content_counts(detail)
                if counts['diagnosis_count'] == 0:
                    diagnosis_path = SYNC_ENDPOINTS['treatment_plan_diagnosis'].format(id=encoded_id)
                    try:
                        diagnosis_detail = _fetch_detail(
                            base_url=base_url,
                            path=diagnosis_path,
                            bearer_token=bearer_token,
                            api_version=api_version,
                            timeout_seconds=settings_row.emr_api_timeout_seconds,
                        )
                        diagnoses = _list_value(diagnosis_detail.get('items')) or _list_value(diagnosis_detail.get('diagnoses')) or _list_value(diagnosis_detail.get('diagnosis'))
                        if diagnoses:
                            detail = {**detail, 'diagnoses': diagnoses}
                    except AllevaSyncExternalError as exc:
                        log_event(
                            db,
                            action='alleva.treatment_plan_diagnosis_fetch.failed',
                            actor=actor,
                            event_category='integration',
                            target_entity=f'treatment_plan:{plan_id}',
                            target_entity_type='alleva_treatment_plan',
                            details={
                                'treatment_plan_id': plan_id,
                                'endpoint': exc.endpoint or diagnosis_path,
                                'category': exc.category,
                                'status_code': exc.status_code,
                            },
                            outcome_status='failure',
                            severity='warning',
                            message='Alleva treatment-plan diagnosis detail endpoint could not be read; nested treatment-plan detail was retained.',
                        )
                log_event(
                    db,
                    action='alleva.treatment_plan_detail_fetch.completed',
                    actor=actor,
                    event_category='integration',
                    target_entity=f'treatment_plan:{plan_id}',
                    target_entity_type='alleva_treatment_plan',
                    details={'treatment_plan_id': plan_id, 'endpoint': detail_path, **_content_counts(detail)},
                    message='Fetched Alleva current treatment plan detail for nested clinical content.',
                )
                return detail

        summary = sync_alleva_rest_payloads(
            db,
            clients_payload=clients,
            treatment_plans_payload=treatment_plans,
            treatment_reviews_payload=treatment_reviews,
            plan_detail_fetcher=plan_detail_fetcher,
            detail_fetch_limit=max(0, min(settings_row.alleva_treatment_plan_detail_fetch_limit or 0, 5000)),
            patient_name_import_enabled=settings_row.alleva_treatment_plan_patient_name_import_enabled,
            name_join_fallback_enabled=settings_row.alleva_treatment_plan_name_join_fallback_enabled,
            actor=actor,
        )
        db.commit()
        touched_clients = (
            db.execute(
                select(TreatmentPlanClient)
                .options(
                    selectinload(TreatmentPlanClient.level_of_care_history),
                    selectinload(TreatmentPlanClient.treatment_plans),
                    selectinload(TreatmentPlanClient.current_plan_record),
                    selectinload(TreatmentPlanClient.overrides),
                )
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
        warning_parts: list[str] = []
        if optional_review_failure:
            warning_parts.append(str(optional_review_failure['message']))
        if not clients and not treatment_plans and not treatment_reviews:
            warning_parts.append('Alleva returned no client, treatment-plan, or treatment-review records for the configured query.')
        elif summary['active_client_count'] == 0:
            warning_parts.append('Alleva returned records, but no active clients could be identified from the mapped status/discharge fields.')
        if summary['unmapped_treatment_plan_count']:
            warning_parts.append(f'{summary["unmapped_treatment_plan_count"]} treatment plan record(s) could not be matched to an active client.')
        if summary['unmapped_treatment_review_count']:
            warning_parts.append(f'{summary["unmapped_treatment_review_count"]} treatment review record(s) could not be matched to an active client.')
        if summary['name_join_fallback_count']:
            warning_parts.append(f'{summary["name_join_fallback_count"]} record(s) used the disabled-by-default name fallback; verify ID mapping before relying on these joins.')
        if summary['current_plan_missing_count']:
            warning_parts.append(f'{summary["current_plan_missing_count"]} active client(s) had no current active treatment plan selected.')
        if summary['detail_fetch_failed_count']:
            warning_parts.append(f'{summary["detail_fetch_failed_count"]} current treatment plan detail fetch(es) failed; collection-level plan data was retained.')
        if summary['detail_fetch_enabled'] and summary['detail_fetch_skipped_count']:
            warning_parts.append(f'{summary["detail_fetch_skipped_count"]} current treatment plan detail fetch(es) were skipped by the configured detail-fetch cap.')
        status = 'warn' if warning_parts else 'ok'
        message = (
            f'Alleva treatment-plan sync completed{" with warnings" if warning_parts else ""}; '
            f'{summary["upserted_client_count"]} active client(s) loaded, '
            f'{summary["treatment_plan_count"]} treatment plan record(s), {summary["treatment_review_count"]} review record(s).'
        )
        if warning_parts:
            message = f'{message} {" ".join(warning_parts)}'
        _mark_status(db, settings_row, status=status, message=message)
        log_event(
            db,
            action='alleva.treatment_plan_sync.completed' if status == 'ok' else 'alleva.treatment_plan_sync.completed_with_warnings',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details={key: value for key, value in summary.items() if key != 'client_ids'} | {'startup': startup, 'warnings': warning_parts},
            outcome_status='success',
            severity='info' if status == 'ok' else 'warning',
            message=message,
        )
        result = {'status': status, 'message': message, 'warnings': warning_parts, **{key: value for key, value in summary.items() if key != 'client_ids'}}
        if optional_review_failure:
            result['optional_endpoint_failures'] = [optional_review_failure]
        return result
    except AllevaSyncExternalError as exc:
        logger.warning(
            'Alleva treatment-plan sync external failure stage=%s category=%s endpoint=%s status_code=%s',
            exc.stage,
            exc.category,
            exc.endpoint,
            exc.status_code,
        )
        db.rollback()
        _mark_status(db, settings_row, status=exc.status, message=exc.public_message)
        log_event(
            db,
            action='alleva.treatment_plan_sync.failed',
            actor=actor,
            event_category='integration',
            target_entity='alleva_treatment_plan_sync',
            target_entity_type='integration_sync',
            details={
                'startup': startup,
                'failure_stage': exc.stage,
                'category': exc.category,
                'endpoint': exc.endpoint,
                'status_code': exc.status_code,
            },
            outcome_status='failure',
            severity='error',
            message=exc.public_message,
        )
        return {
            'status': exc.status,
            'message': exc.public_message,
            'failure_stage': exc.stage,
            'category': exc.category,
            'endpoint': exc.endpoint,
            'status_code': exc.status_code,
        }
    except Exception as exc:
        message = 'Alleva treatment-plan sync could not finish because the app hit an unexpected local error. No records were imported from this run; support can review the local logs for technical details.'
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
