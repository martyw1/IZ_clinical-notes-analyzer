from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import urljoin

import httpx

from app.services.api_connectivity import redact_sensitive_text, redact_url
from app.services.patient_identity_minimization import redacted_text, sanitize_patient_payload

ALLEVA_CLIENTS_PATH = '/clients'
ALLEVA_TREATMENT_PLANS_PATH = '/treatment-plans'
ALLEVA_TREATMENT_REVIEWS_PATH = '/treatment-reviews'
DEFAULT_API_VERSION = '1.0'

CLIENT_FIELD_REQUEST = [
    'id',
    'clientId',
    'uniqueId',
    'mrn',
    'status',
    'isClient',
    'admissionDateTime',
    'admissionDate',
    'firstContactDate',
    'dischargeDateTime',
    'actualSysDischargeDateTime',
    'isDischarge',
    'facilityName',
    'levelOfCare',
    'primaryClinician',
    'primaryClinicians',
    'medicalProviders',
]

PATIENT_RECORD_COLUMNS = [
    'patient_id',
    'source_id',
    'internal_client_id',
    'admission_date',
    'status',
    'status_scope',
    'is_client',
    'discharge_date',
    'level_of_care',
    'facility',
    'primary_clinician',
    'first_contact_date',
    'why_included',
]


def text_value(value: Any) -> str:
    return str(value).strip() if value is not None else ''


def first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            nested = first_text(value, 'clientId', 'id', 'leadId', 'uniqueId', 'mrn', 'href')
            if nested:
                return nested
            continue
        text = text_value(value)
        if text:
            return text
    return ''


def nested_first_text(payload: dict[str, Any], *paths: str) -> str:
    for path in paths:
        current: Any = payload
        for part in path.split('.'):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break
        if isinstance(current, dict):
            current = first_text(current, 'clientId', 'id', 'leadId', 'uniqueId', 'mrn', 'href')
        text = text_value(current)
        if text:
            return text
    return ''


def date_text(value: Any) -> str:
    raw = text_value(value)
    if not raw:
        return ''
    if 'T' in raw:
        return raw.split('T', 1)[0]
    if ' ' in raw and raw[:10].count('-') == 2:
        return raw[:10]
    if len(raw) >= 10 and raw[4:5] == '-' and raw[7:8] == '-':
        return raw[:10]
    return raw


def parse_date(value: Any) -> date | None:
    raw = date_text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def bool_value(value: Any, *, default: bool = False) -> bool:
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


def list_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('items', 'data', 'results', 'value', 'records'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def http_status_label(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = ''
    return f'HTTP {status_code}{f" {phrase}" if phrase else ""}'


def endpoint_failure_message(*, path: str, status_code: int, api_version: str) -> tuple[str, str]:
    status_label = http_status_label(status_code)
    if status_code == 401:
        return (
            'endpoint_authorization_failed',
            (
                f'Authentication reached Alleva, but Alleva rejected GET {path} with {status_label}. '
                f'Ask R3/Alleva to confirm tenant access, read permission for {path}, token audience/scope, and API version {api_version}.'
            ),
        )
    if status_code == 403:
        return ('endpoint_permission_denied', f'Authentication worked, but the credentials are not permitted to read GET {path} ({status_label}).')
    if status_code in {400, 404, 405}:
        return (
            'endpoint_mapping_or_version_failed',
            f'Alleva rejected GET {path} with {status_label}. Confirm the path, Limit/Cursor/api-version parameters, X-Version header, and approved API version.',
        )
    if status_code == 429:
        return ('endpoint_rate_limited', f'Alleva rate-limited GET {path} ({status_label}).')
    if 500 <= status_code <= 599:
        return ('endpoint_vendor_unavailable', f'Alleva returned {status_label} for GET {path}.')
    return ('endpoint_request_failed', f'Alleva returned {status_label} for GET {path}.')


def query_and_headers(operation_parameters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    query: dict[str, Any] = {}
    headers = {'Accept': 'application/json'}
    for key, value in operation_parameters.items():
        if value in (None, ''):
            continue
        if key.lower() == 'x-version':
            headers['X-Version'] = str(value)
        else:
            query[key] = value
    api_version = text_value(operation_parameters.get('api-version')) or text_value(operation_parameters.get('X-Version')) or DEFAULT_API_VERSION
    query.setdefault('api-version', api_version)
    headers.setdefault('X-Version', api_version)
    return query, headers


@dataclass
class AllevaPageDiagnostic:
    page_index: int
    cursor: int
    limit: int
    status_code: int
    record_count: int
    url: str


@dataclass
class AllevaCollectionResult:
    path: str
    method: str = 'GET'
    query_parameters: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    pages: list[AllevaPageDiagnostic] = field(default_factory=list)
    complete: bool = True
    error: dict[str, Any] | None = None
    warning: dict[str, Any] | None = None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def page_size(self) -> int:
        return self.pages[0].limit if self.pages else int(self.query_parameters.get('Limit') or 0)

    def diagnostics(self) -> dict[str, Any]:
        return {
            'endpoint': self.path,
            'http_method': self.method,
            'query_parameters': self.query_parameters,
            'page_count': self.page_count,
            'page_size': self.page_size,
            'record_count': len(self.records),
            'complete': self.complete,
            'pagination_strategy': 'Limit/Cursor offset pagination until a short page or configured max_pages.',
            'pages': [page.__dict__ for page in self.pages],
            'warning': self.warning,
            'error': self.error,
        }


def fetch_alleva_collection(
    *,
    base_url: str,
    path: str,
    operation_parameters: dict[str, Any],
    api_key: str = '',
    bearer_token: str = '',
    api_key_header_name: str = 'x-api-key',
    timeout_seconds: int = 10,
    max_pages: int = 10,
    max_page_size: int = 5000,
) -> AllevaCollectionResult:
    query, headers = query_and_headers(operation_parameters)
    if api_key:
        headers[api_key_header_name or 'x-api-key'] = api_key
    if bearer_token:
        headers['Authorization'] = f'Bearer {bearer_token}'
    try:
        limit = max(1, min(int(query.get('Limit') or 500), max_page_size))
    except (TypeError, ValueError):
        limit = 500
    try:
        cursor = max(0, int(query.get('Cursor') or 0))
    except (TypeError, ValueError):
        cursor = 0

    result = AllevaCollectionResult(path=path, query_parameters={**query, 'Limit': limit, 'Cursor': cursor})
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for page_index in range(max_pages):
            page_query = dict(query)
            page_query['Limit'] = limit
            page_query['Cursor'] = cursor
            api_version = text_value(page_query.get('api-version')) or text_value(headers.get('X-Version')) or DEFAULT_API_VERSION
            try:
                response = client.get(url, params=page_query, headers=headers)
                response.read()
            except httpx.TimeoutException:
                result.complete = False
                result.error = {
                    'category': 'network_timeout',
                    'message': f'Alleva did not respond before the configured timeout while reading GET {path}.',
                    'page_index': page_index,
                    'url': redact_url(url),
                }
                return result
            except httpx.RequestError:
                result.complete = False
                result.error = {
                    'category': 'network_failure',
                    'message': f'The app could not reach Alleva GET {path}. Check internet access, base URL, and local firewall/proxy settings.',
                    'page_index': page_index,
                    'url': redact_url(url),
                }
                return result
            if not 200 <= response.status_code < 300:
                category, message = endpoint_failure_message(path=path, status_code=response.status_code, api_version=api_version)
                result.complete = False
                result.error = {
                    'category': category,
                    'status_code': response.status_code,
                    'message': message,
                    'response_body_preview': redacted_text(redact_sensitive_text(response.text[:600])),
                    'page_index': page_index,
                    'url': redact_url(str(response.url)),
                }
                return result
            try:
                page_records = list_records(response.json())
            except ValueError:
                result.complete = False
                result.error = {
                    'category': 'endpoint_non_json_response',
                    'status_code': response.status_code,
                    'message': f'Alleva GET {path} responded, but the response was not JSON. Confirm this endpoint path and API version {api_version}.',
                    'response_body_preview': redacted_text(redact_sensitive_text(response.text[:600])),
                    'page_index': page_index,
                    'url': redact_url(str(response.url)),
                }
                return result
            result.records.extend(page_records)
            result.pages.append(
                AllevaPageDiagnostic(
                    page_index=page_index,
                    cursor=cursor,
                    limit=limit,
                    status_code=response.status_code,
                    record_count=len(page_records),
                    url=redact_url(str(response.url)),
                )
            )
            if len(page_records) < limit:
                return result
            cursor += limit
    result.complete = False
    result.warning = {
        'category': 'pagination_limit_reached',
        'message': f'GET {path} returned a full page through max_pages={max_pages}; the dataset may be partial.',
        'page_count': result.page_count,
    }
    return result


def patient_identifier_summary(payload: dict[str, Any]) -> dict[str, str]:
    safe = sanitize_patient_payload(payload)
    return {
        'app_patient_id': first_text(safe, 'clientId', 'id', 'leadId', 'uniqueId', 'mrn'),
        'client_id': first_text(safe, 'clientId'),
        'source_id': first_text(safe, 'id'),
        'lead_id': first_text(safe, 'leadId'),
        'unique_id': first_text(safe, 'uniqueId'),
        'mrn': first_text(safe, 'mrn'),
    }


def treatment_plan_identifier_summary(payload: dict[str, Any]) -> dict[str, str]:
    safe = sanitize_patient_payload(payload)
    return {
        'treatment_plan_id': first_text(safe, 'id', 'treatmentPlanId', 'treatmentPlanReviewId', 'href'),
        'app_patient_id': nested_first_text(safe, 'client.clientId', 'client.id', 'client.leadId') or first_text(safe, 'clientId', 'patientId', 'leadId'),
        'client_id': nested_first_text(safe, 'client.clientId') or first_text(safe, 'clientId'),
        'source_client_id': nested_first_text(safe, 'client.id') or first_text(safe, 'patientId'),
        'lead_id': nested_first_text(safe, 'client.leadId') or first_text(safe, 'leadId'),
    }


def review_identifier_summary(payload: dict[str, Any]) -> dict[str, str]:
    safe = sanitize_patient_payload(payload)
    return {
        'treatment_review_id': first_text(safe, 'id', 'treatmentPlanReviewId', 'href'),
        'treatment_plan_id': first_text(safe, 'treatmentPlanId'),
        'app_patient_id': nested_first_text(safe, 'client.clientId', 'client.id', 'client.leadId') or first_text(safe, 'clientId', 'patientId', 'leadId'),
        'client_id': nested_first_text(safe, 'client.clientId') or first_text(safe, 'clientId'),
        'source_client_id': nested_first_text(safe, 'client.id') or first_text(safe, 'patientId'),
        'lead_id': nested_first_text(safe, 'client.leadId') or first_text(safe, 'leadId'),
        'swagger_client_linkage': 'runtime ID fields preferred; Swagger documents clientName only for treatment reviews',
    }


def patient_status_scope(payload: dict[str, Any]) -> tuple[str, str]:
    safe = sanitize_patient_payload(payload)
    if bool_value(safe.get('isDischarge'), default=False):
        return 'discharged', 'isDischarge is true'
    if text_value(safe.get('dischargeDateTime') or safe.get('actualSysDischargeDateTime')):
        return 'discharged', 'discharge date is present'
    status = first_text(safe, 'status', 'statusName').lower()
    if any(word in status for word in ('discharge', 'closed', 'deceased')):
        return 'discharged', f'status is {status}'
    if any(word in status for word in ('inactive', 'prospect', 'lead')):
        return 'inactive', f'status is {status}'
    if safe.get('isClient') is not None and not bool_value(safe.get('isClient'), default=True):
        return 'inactive', 'isClient is false'
    return 'active', 'no discharge/inactive fields returned'


def treatment_plan_status_scope(payload: dict[str, Any]) -> tuple[str, str]:
    safe = sanitize_patient_payload(payload)
    status = first_text(safe, 'status', 'statusName').lower()
    if any(word in status for word in ('discharge', 'closed', 'deceased')):
        return 'discharged', f'status is {status}'
    if any(word in status for word in ('inactive', 'cancel', 'deleted')):
        return 'inactive', f'status is {status}'
    if safe.get('isActive') is not None and not bool_value(safe.get('isActive'), default=True):
        return 'inactive', 'isActive is false'
    return 'active', 'isActive is true or status is active-compatible'


def normalize_patient_row(payload: dict[str, Any]) -> dict[str, Any]:
    safe = sanitize_patient_payload(payload)
    ids = patient_identifier_summary(safe)
    scope, reason = patient_status_scope(safe)
    return {
        'patient_id': ids['app_patient_id'],
        'source_id': ids['source_id'] or ids['unique_id'] or ids['mrn'],
        'internal_client_id': ids['client_id'],
        'admission_date': date_text(safe.get('admissionDateTime') or safe.get('admissionDate')),
        'first_admitted': date_text(safe.get('admissionDateTime') or safe.get('admissionDate') or safe.get('firstContactDate')),
        'status': first_text(safe, 'status', 'statusName'),
        'status_scope': scope,
        'is_client': bool_value(safe.get('isClient'), default=True),
        'discharge_date': date_text(safe.get('dischargeDateTime') or safe.get('actualSysDischargeDateTime')),
        'level_of_care': first_text(safe, 'levelOfCare'),
        'facility': first_text(safe, 'facilityName'),
        'primary_clinician': first_text(safe, 'primaryClinician', 'primaryClinicians', 'medicalProviders'),
        'first_contact_date': date_text(safe.get('firstContactDate')),
        'why_included': reason,
    }


def normalize_treatment_plan_row(payload: dict[str, Any], *, today: date) -> dict[str, Any]:
    safe = sanitize_patient_payload(payload)
    ids = treatment_plan_identifier_summary(safe)
    scope, reason = treatment_plan_status_scope(safe)
    end_date = parse_date(safe.get('endDate'))
    start_date = parse_date(safe.get('startDate'))
    is_complete = bool_value(safe.get('isComplete'), default=False)
    reasons = [reason]
    if end_date is None:
        reasons.append('endDate missing; due status needs review')
    elif end_date < today:
        reasons.append(f'endDate {end_date.isoformat()} is before {today.isoformat()}')
    else:
        reasons.append(f'endDate {end_date.isoformat()} is not overdue as of {today.isoformat()}')
    if not is_complete:
        reasons.append('isComplete is false or missing')
    return {
        'treatment_plan_id': ids['treatment_plan_id'],
        'patient_id': ids['app_patient_id'],
        'client_id': ids['client_id'],
        'source_client_id': ids['source_client_id'],
        'description': first_text(safe, 'description'),
        'start_date': start_date.isoformat() if start_date else date_text(safe.get('startDate')),
        'end_date': end_date.isoformat() if end_date else date_text(safe.get('endDate')),
        'status_scope': scope,
        'is_active': scope == 'active',
        'is_complete': is_complete,
        'last_modified': date_text(safe.get('lastModified')),
        'why': '; '.join(reasons),
    }


def row_status_scope(report: str) -> str:
    if report.startswith('active_'):
        return 'active'
    if report.startswith('discharged_'):
        return 'discharged'
    if report.startswith('inactive_'):
        return 'inactive'
    return 'all'


def quick_pull_path(report: str) -> str:
    if report in {'all_patient_records', 'active_patients', 'discharged_patients', 'inactive_patients'}:
        return ALLEVA_CLIENTS_PATH
    return ALLEVA_TREATMENT_PLANS_PATH


def quick_pull_rows(report: str, records: list[dict[str, Any]], *, today: date) -> dict[str, Any]:
    scope = row_status_scope(report)
    excluded: list[dict[str, Any]] = []
    if report in {'all_patient_records', 'active_patients', 'discharged_patients', 'inactive_patients'}:
        normalized = [normalize_patient_row(item) for item in records]
        rows = [row for row in normalized if scope == 'all' or row['status_scope'] == scope]
        excluded = [
            {'patient_id': row['patient_id'], 'source_id': row['source_id'], 'status_scope': row['status_scope'], 'reason': f'excluded by {scope} status scope'}
            for row in normalized
            if row not in rows
        ]
        return {
            'rows': rows,
            'columns': PATIENT_RECORD_COLUMNS if report == 'all_patient_records' else [],
            'copy_format': 'tsv' if report == 'all_patient_records' else '',
            'message_subject': {'all': 'patient record(s)', 'active': 'active patient(s)', 'discharged': 'discharged patient(s)', 'inactive': 'inactive patient(s)'}[scope],
            'status_scope': scope,
            'excluded_records': excluded,
        }
    normalized = [normalize_treatment_plan_row(item, today=today) for item in records]
    if report == 'overdue_treatment_plans':
        rows = [row for row in normalized if row['status_scope'] == 'active' and row_end_date_before(row, today)]
        excluded = [
            {
                'patient_id': row['patient_id'],
                'treatment_plan_id': row['treatment_plan_id'],
                'status_scope': row['status_scope'],
                'reason': 'excluded because plan is not both active and overdue by endDate',
            }
            for row in normalized
            if row not in rows
        ]
        return {'rows': rows, 'columns': [], 'copy_format': '', 'message_subject': 'overdue active treatment plan(s)', 'status_scope': 'active_overdue', 'excluded_records': excluded}
    rows = [row for row in normalized if scope == 'all' or row['status_scope'] == scope]
    excluded = [
        {
            'patient_id': row['patient_id'],
            'treatment_plan_id': row['treatment_plan_id'],
            'status_scope': row['status_scope'],
            'reason': f'excluded by {scope} status scope',
        }
        for row in normalized
        if row not in rows
    ]
    return {
        'rows': rows,
        'columns': [],
        'copy_format': '',
        'message_subject': {'all': 'treatment plan(s)', 'active': 'active treatment plan(s)', 'discharged': 'discharged treatment plan(s)', 'inactive': 'inactive treatment plan(s)'}[scope],
        'status_scope': scope,
        'excluded_records': excluded,
    }


def row_end_date_before(row: dict[str, Any], today: date) -> bool:
    try:
        return bool(row.get('end_date')) and date.fromisoformat(str(row['end_date'])[:10]) < today
    except ValueError:
        return False


def rows_to_tsv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def tsv_value(value: Any) -> str:
        return text_value(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')

    return '\n'.join(['\t'.join(columns), *['\t'.join(tsv_value(row.get(column)) for column in columns) for row in rows]])


def id_mapping_summary(patient_records: list[dict[str, Any]], plan_records: list[dict[str, Any]], review_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    patient_ids = [patient_identifier_summary(item) for item in patient_records]
    plan_ids = [treatment_plan_identifier_summary(item) for item in plan_records]
    review_ids = [review_identifier_summary(item) for item in (review_records or [])]
    patient_aliases = {
        value
        for item in patient_ids
        for value in (item.get('app_patient_id'), item.get('client_id'), item.get('source_id'), item.get('lead_id'), item.get('unique_id'), item.get('mrn'))
        if value
    }
    mapped_plans = [item for item in plan_ids if any(value and value in patient_aliases for value in (item.get('app_patient_id'), item.get('client_id'), item.get('source_client_id'), item.get('lead_id')))]
    mapped_reviews = [item for item in review_ids if any(value and value in patient_aliases for value in (item.get('app_patient_id'), item.get('client_id'), item.get('source_client_id'), item.get('lead_id')))]
    return {
        'patient_record_count': len(patient_records),
        'treatment_plan_record_count': len(plan_records),
        'treatment_review_record_count': len(review_records or []),
        'patient_ids': patient_ids[:25],
        'treatment_plan_ids': plan_ids[:25],
        'treatment_review_ids': review_ids[:25],
        'mapped_treatment_plan_count': len(mapped_plans),
        'unmapped_treatment_plan_count': max(0, len(plan_ids) - len(mapped_plans)),
        'mapped_treatment_review_count': len(mapped_reviews),
        'unmapped_treatment_review_count': max(0, len(review_ids) - len(mapped_reviews)),
        'notes': [
            'app_patient_id prefers clientId when present, then id/leadId/uniqueId/mrn.',
            'source_id is the endpoint record id from /clients when present.',
            'Treatment reviews may require runtime verification because Swagger documents clientName but not a reliable client id field.',
        ],
    }


def source_coverage_summary(patient_records: list[dict[str, Any]], plan_records: list[dict[str, Any]], review_records: list[dict[str, Any]] | None = None, *, complete: bool = True) -> dict[str, Any]:
    normalized_patients = [normalize_patient_row(item) for item in patient_records]
    normalized_plans = [normalize_treatment_plan_row(item, today=date.today()) for item in plan_records]
    reviews = [review_identifier_summary(item) for item in (review_records or [])]
    required = {
        'active_patient_list_retrieved': bool(patient_records) and complete,
        'patient_status': any(row.get('status') or row.get('discharge_date') for row in normalized_patients),
        'admission_date': any(row.get('admission_date') for row in normalized_patients),
        'current_level_of_care': any(row.get('level_of_care') for row in normalized_patients),
        'treatment_plan_summary': bool(plan_records),
        'treatment_plan_detail_or_nested_content': any(item.get('problems') for item in [sanitize_patient_payload(record) for record in plan_records]),
        'treatment_plan_signatures': any(nested_first_text(sanitize_patient_payload(record), 'clientSignature.signatureDateTime', 'staffSignature.signatureDateTime', 'creatorSignature.signatureDateTime') for record in plan_records),
        'treatment_review_dates': any(date_text(sanitize_patient_payload(record).get('createdDated') or sanitize_patient_payload(record).get('createdDate') or sanitize_patient_payload(record).get('generatedDate')) for record in (review_records or [])),
        'next_review_due': any(date_text(sanitize_patient_payload(record).get('nextReviewDue') or sanitize_patient_payload(record).get('nextReviewDueDate')) for record in (review_records or [])),
    }
    unavailable = [
        'Swagger does not document counselor/manager content update markers for treatment-plan content.',
        'Swagger does not document a treatment-review client id field; runtime responses must be checked for client/clientId/leadId before trusting review linkage.',
    ]
    return {
        'complete_enough_for_full_evaluation': all(required.values()),
        'required_field_coverage': required,
        'missing_or_not_retrieved': [key for key, value in required.items() if not value],
        'not_exposed_by_swagger': unavailable,
        'normalized_patient_sample': normalized_patients[:3],
        'normalized_treatment_plan_sample': normalized_plans[:3],
        'normalized_review_id_sample': reviews[:3],
    }


def redacted_sample(records: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    return [sanitize_patient_payload(item, aggressive=True, omit_direct=False) for item in records[:limit]]
