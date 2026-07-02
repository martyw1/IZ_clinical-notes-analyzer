from __future__ import annotations
# noqa: SIZE_OK - pre-existing centralized admin API harness route; new treatment-plan logic is extracted to services.

import logging
from datetime import date, datetime, timezone
from http import HTTPStatus
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.models import AppSetting, Role, User
from app.services.api_connectivity import (
    DEFAULT_ALLEVA_TOKEN_URL,
    DEFAULT_ALLEVA_SWAGGER_UI_URL,
    build_api_connectivity_report,
    execute_openapi_operation,
    persist_api_connectivity_report,
    pull_api_definitions,
    redact_url,
    request_client_credentials_token,
)
from app.services.app_settings import get_or_create_app_settings
from app.services.audit import log_event
from app.services.alleva_treatment_plan_aggregate import AggregateBuildOptions, build_patient_treatment_plan_aggregate_result
from app.services.alleva_treatment_plan_harness import (
    TREATMENT_PLAN_HARNESS_REPORTS,
    TreatmentPlanHarnessRequest,
    run_treatment_plan_harness_pull,
    treatment_plan_default_parameters,
)
from app.services.secure_storage import decrypt_text_secret, encrypt_text_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api')
DEFAULT_API_KEY_HEADER_NAME = 'x-api-key'
UPSTREAM_BODY_PREVIEW_OMITTED = '[omitted to avoid returning upstream patient data]'

SAMPLE_OPENAPI_DEFINITION: dict[str, Any] = {
    'openapi': '3.0.3',
    'info': {
        'title': 'IZ Clinical Notes Analyzer Connectivity Test Definition',
        'version': '1.0.0',
    },
    'paths': {
        '/api/health': {
            'get': {
                'summary': 'Health check',
                'responses': {'200': {'description': 'Application is healthy'}},
            }
        },
        '/api/api-configuration/pull-definitions': {
            'post': {
                'summary': 'Pull and summarize OpenAPI or Swagger definitions',
                'responses': {'200': {'description': 'Definition pull result'}},
            }
        },
        '/api/api-configuration/operation-test-target/{patient_id}': {
            'get': {
                'summary': 'Local operation test target',
                'parameters': [
                    {'name': 'patient_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}, 'description': 'Synthetic patient ID'},
                    {'name': 'include_documents', 'in': 'query', 'required': True, 'schema': {'type': 'boolean'}, 'description': 'Whether to include document metadata'},
                ],
                'responses': {'200': {'description': 'Synthetic target response'}},
            },
            'post': {
                'summary': 'Local operation test target with request body',
                'parameters': [
                    {'name': 'patient_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}, 'description': 'Synthetic patient ID'},
                ],
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'required': ['note_type'],
                                'properties': {
                                    'note_type': {'type': 'string', 'enum': ['progress_note', 'treatment_plan_tracking'], 'description': 'Synthetic note category'},
                                    'service_date': {'type': 'string', 'format': 'date', 'description': 'Service date to test'},
                                },
                            }
                        }
                    },
                },
                'responses': {'200': {'description': 'Synthetic target response'}},
            },
        },
    },
    'components': {
        'securitySchemes': {
            'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': DEFAULT_API_KEY_HEADER_NAME},
            'BearerAuth': {'type': 'http', 'scheme': 'bearer'},
        },
        'schemas': {
            'ConnectivityResult': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'message': {'type': 'string'},
                },
            }
        },
    },
}


class ApiConfigurationOut(BaseModel):
    vendor_name: str
    api_base_url: str
    swagger_ui_url: str
    openapi_url: str
    api_key_configured: bool
    client_id: str
    client_id_configured: bool
    client_secret_configured: bool
    token_url: str
    token_auth_style: str
    api_key_header_name: str
    timeout_seconds: int
    api_enabled: bool
    recommended_auth_mode: Literal['api_key', 'client_credentials', 'none']


class ApiConfigurationUpdate(BaseModel):
    vendor_name: str | None = Field(default=None, max_length=120)
    api_base_url: str | None = Field(default=None, max_length=255)
    openapi_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = None
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = None
    clear_client_secret: bool = False
    token_url: str | None = Field(default=None, max_length=500)
    token_auth_style: Literal['body', 'basic', 'basic_urlencoded', 'both', 'all'] | None = None
    clear_api_key: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    api_enabled: bool | None = None


class ApiDefinitionPullInput(BaseModel):
    swagger_ui_url: str | None = Field(default=DEFAULT_ALLEVA_SWAGGER_UI_URL, max_length=500)
    api_base_url: str | None = Field(default=None, max_length=500)
    openapi_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = None
    use_saved_api_key: bool = True
    api_key_header_name: str = Field(default=DEFAULT_API_KEY_HEADER_NAME, max_length=80)
    auth_mode: Literal['api_key', 'client_credentials', 'none'] = 'api_key'
    token_url: str | None = Field(default=None, max_length=500)
    token_auth_style: Literal['body', 'basic', 'basic_urlencoded', 'both', 'all'] = 'body'
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = None
    use_saved_client_credentials: bool = True
    scope: str | None = Field(default=None, max_length=500)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)


class ApiOperationTestInput(ApiDefinitionPullInput):
    definition: dict[str, Any] = Field(default_factory=dict)
    selected_definition_url: str | None = Field(default='', max_length=500)
    method: str = Field(max_length=12)
    path: str = Field(max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    request_body: Any | None = None


class AllevaQuickPullInput(ApiDefinitionPullInput):
    report: Literal[
        'all_patient_records',
        'active_treatment_plans',
        'overdue_treatment_plans',
        'inactive_treatment_plans',
        'active_patients',
        'patient_treatment_plan_aggregates',
        'all_treatment_plans',
        'single_treatment_plan',
    ]
    operation_parameters: dict[str, Any] = Field(default_factory=dict)
    max_pages: int = Field(default=10, ge=1, le=50)
    patient_id: str | None = Field(default=None, max_length=100)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strip(value: str | None) -> str:
    return (value or '').strip()


def _default_openapi_url(settings_row: AppSetting) -> str:
    if _strip(settings_row.alleva_openapi_url):
        return _strip(settings_row.alleva_openapi_url)
    base_url = _strip(settings_row.alleva_api_base_url).rstrip('/')
    if not base_url:
        return ''
    if base_url.endswith('/swagger/v1/swagger.json') or base_url.endswith('/openapi.json') or base_url.endswith('/swagger.json'):
        return base_url
    return f'{base_url}/swagger/v1/swagger.json'


def _configuration_out(settings_row: AppSetting) -> ApiConfigurationOut:
    has_client_credentials = bool(settings_row.api_client_id and settings_row.api_client_secret and settings_row.api_oauth_token_url)
    return ApiConfigurationOut(
        vendor_name=settings_row.emr_vendor_name or 'Alleva API',
        api_base_url=settings_row.alleva_api_base_url or '',
        swagger_ui_url=DEFAULT_ALLEVA_SWAGGER_UI_URL,
        openapi_url=_default_openapi_url(settings_row),
        api_key_configured=bool(settings_row.api_client_secret),
        client_id=settings_row.api_client_id or '',
        client_id_configured=bool(settings_row.api_client_id),
        client_secret_configured=bool(settings_row.api_client_secret),
        token_url=settings_row.api_oauth_token_url or DEFAULT_ALLEVA_TOKEN_URL,
        token_auth_style=getattr(settings_row, 'api_token_auth_style', 'body') or 'body',
        api_key_header_name=DEFAULT_API_KEY_HEADER_NAME,
        timeout_seconds=settings_row.emr_api_timeout_seconds,
        api_enabled=settings_row.emr_api_enabled,
        recommended_auth_mode='client_credentials' if has_client_credentials else ('api_key' if settings_row.api_client_secret else 'none'),
    )


def _snapshot(settings_row: AppSetting) -> dict[str, Any]:
    return _configuration_out(settings_row).model_dump()


def _saved_api_key(settings_row: AppSetting) -> str:
    if not settings_row.api_client_secret:
        return ''
    return decrypt_text_secret(settings_row.api_client_secret)


def _auth_context(
    payload: ApiDefinitionPullInput,
    settings_row: AppSetting,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    supplied_key = _strip(payload.api_key)
    saved_key = _saved_api_key(settings_row) if payload.use_saved_api_key else ''
    context: dict[str, Any] = {
        'auth_mode': payload.auth_mode,
        'api_key': '',
        'bearer_token': '',
        'api_key_source': 'none',
        'credential_source': 'none',
        'token_url': _strip(payload.token_url) or settings_row.api_oauth_token_url or DEFAULT_ALLEVA_TOKEN_URL,
        'token_auth_style': payload.token_auth_style or getattr(settings_row, 'api_token_auth_style', 'body') or 'body',
        'scope': _strip(payload.scope),
        'token_result': {},
    }
    if payload.auth_mode == 'none':
        return context
    if payload.auth_mode == 'api_key':
        context['api_key'] = supplied_key or saved_key
        context['api_key_source'] = 'inline' if supplied_key else ('saved' if saved_key else 'none')
        return context

    supplied_client_id = _strip(payload.client_id)
    supplied_client_secret = _strip(payload.client_secret)
    saved_client_id = settings_row.api_client_id.strip() if payload.use_saved_client_credentials else ''
    saved_client_secret = _saved_api_key(settings_row) if payload.use_saved_client_credentials else ''
    client_id = supplied_client_id or saved_client_id
    client_secret = supplied_client_secret or saved_client_secret
    context['credential_source'] = 'inline' if supplied_client_id or supplied_client_secret else ('saved' if saved_client_id and saved_client_secret else 'none')

    token_result, bearer_token = request_client_credentials_token(
        token_url=context['token_url'],
        client_id=client_id,
        client_secret=client_secret,
        scope=context['scope'],
        timeout_seconds=timeout_seconds,
        token_auth_style=context['token_auth_style'],
    )
    context['token_result'] = token_result
    context['bearer_token'] = bearer_token
    return context


def _auth_failure_result(*, auth_context: dict[str, Any], report_type: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    token_result = auth_context.get('token_result') if isinstance(auth_context.get('token_result'), dict) else {}
    result = {
        'status': 'fail',
        'message': token_result.get('message') or 'Authentication did not complete.',
        'selected_definition_url': '',
        'definition_summary': {},
        'definition': {},
        'operations': [],
        'probes': [],
        'api_key_used': False,
        'bearer_token_used': False,
        'auth_mode': auth_context.get('auth_mode') or 'client_credentials',
        'token_result': token_result,
    }
    result['report'] = build_api_connectivity_report(report_type=report_type, request=request_payload, result=result)
    result['report_path'] = persist_api_connectivity_report(result['report'])
    return result


def _list_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('items', 'data', 'results', 'value', 'records'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value).strip()


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = _first_text(value, 'clientId', 'id', 'uniqueId', 'mrn', 'leadId', 'href', 'status', 'statusName', 'admissionDateTime')
            if nested:
                return nested
            continue
        text = _text(value)
        if text:
            return text
    return ''


def _date_only(value: Any) -> str:
    text = _text(value)
    if not text:
        return ''
    if 'T' in text:
        return text.split('T', 1)[0]
    if len(text) >= 10 and text[4:5] == '-' and text[7:8] == '-':
        return text[:10]
    return text


def _parse_date(value: Any) -> date | None:
    text = _date_only(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


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


def _patient_id(payload: dict[str, Any]) -> str:
    client = payload.get('client')
    if isinstance(client, dict):
        nested = _first_text(client, 'clientId', 'id', 'uniqueId', 'mrn')
        if nested:
            return nested
    return _first_text(payload, 'clientId', 'id', 'uniqueId', 'mrn')


def _plan_client_id(payload: dict[str, Any]) -> str:
    client = payload.get('client')
    if isinstance(client, dict):
        nested = _first_text(client, 'clientId', 'id', 'uniqueId', 'mrn')
        if nested:
            return nested
    return _first_text(payload, 'clientId', 'patientId', 'leadId', 'id')


def _plan_summary(payload: dict[str, Any], *, today: date) -> dict[str, Any]:
    end_date = _parse_date(payload.get('endDate'))
    start_date = _parse_date(payload.get('startDate'))
    is_active = _bool_value(payload.get('isActive'), default=True)
    is_complete = _bool_value(payload.get('isComplete'), default=False)
    reasons: list[str] = []
    if is_active:
        reasons.append('isActive is true or not provided by Alleva')
    else:
        reasons.append('isActive is false')
    if end_date is None:
        reasons.append('endDate missing; due status needs review')
    elif end_date < today:
        reasons.append(f'endDate {end_date.isoformat()} is before {today.isoformat()}')
    else:
        reasons.append(f'endDate {end_date.isoformat()} is not overdue as of {today.isoformat()}')
    if not is_complete:
        reasons.append('isComplete is false or missing')
    problems = payload.get('problems') if isinstance(payload.get('problems'), list) else []
    goals = [goal for problem in problems if isinstance(problem, dict) for goal in (problem.get('goals') or []) if isinstance(goal, dict)]
    objectives = [objective for goal in goals for objective in (goal.get('objectives') or []) if isinstance(objective, dict)]
    interventions = [intervention for objective in objectives for intervention in (objective.get('interventions') or []) if isinstance(intervention, dict)]
    diagnosis_count = sum(len(problem.get('diagnoses') or []) for problem in problems if isinstance(problem, dict))
    if not diagnosis_count:
        diagnosis_count = len(payload.get('diagnoses') or []) if isinstance(payload.get('diagnoses'), list) else 0
    return {
        'treatment_plan_id': _first_text(payload, 'id'),
        'patient_id': _plan_client_id(payload),
        'description_present': bool(_text(payload.get('description'))),
        'description_length': len(_text(payload.get('description'))),
        'start_date': start_date.isoformat() if start_date else _date_only(payload.get('startDate')),
        'end_date': end_date.isoformat() if end_date else _date_only(payload.get('endDate')),
        'is_active': is_active,
        'is_complete': is_complete,
        'is_initial_tp': _bool_value(payload.get('isInitialTP'), default=False),
        'problem_count': len(problems),
        'diagnosis_count': diagnosis_count,
        'goal_count': len(goals),
        'objective_count': len(objectives),
        'intervention_count': len(interventions),
        'guardian_signature_date': _date_only((payload.get('guardianSignature') or {}).get('signatureDateTime')) if isinstance(payload.get('guardianSignature'), dict) else _date_only(payload.get('guardianSignatureDate')),
        'has_guardian_signature': bool(payload.get('guardianSignature') or payload.get('guardianSignatureDate')),
        'last_modified': _date_only(payload.get('lastModified')),
        'why': '; '.join(reasons),
    }


def _active_patient_summary(payload: dict[str, Any]) -> dict[str, Any]:
    discharge_date = _date_only(payload.get('dischargeDateTime') or payload.get('actualSysDischargeDateTime'))
    status = _first_text(payload, 'status')
    reasons = []
    if status and 'active' in status.lower() and discharge_date:
        reasons.append('status is Active; discharge date retained as data-quality warning')
    elif not discharge_date:
        reasons.append('no actual discharge date returned')
    if not status or not any(word in status.lower() for word in ('inactive', 'discharge', 'closed', 'deceased')):
        reasons.append('status is active-compatible')
    return {
        'patient_id': _patient_id(payload),
        'source_id': _first_text(payload, 'id', 'uniqueId', 'mrn'),
        'first_admitted': _date_only(payload.get('admissionDateTime') or payload.get('firstContactDate')),
        'status': status,
        'discharge_date': discharge_date,
        'discharge_conflict': bool(status and 'active' in status.lower() and (discharge_date or _bool_value(payload.get('isDischarge'), default=False))),
        'level_of_care': _first_text(payload, 'levelOfCare'),
        'facility': _first_text(payload, 'facilityName'),
        'why_active': '; '.join(reasons) or 'active-compatible fields returned',
    }


ALL_PATIENT_RECORD_COLUMNS = [
    'patient_id',
    'source_id',
    'admission_date',
    'status',
    'is_client',
    'discharge_date',
    'actual_sys_discharge_date',
    'is_discharge',
    'level_of_care',
    'facility',
    'primary_clinician',
    'first_contact_date',
]

ALL_PATIENT_RECORD_FIELDS = [
    'id',
    'clientId',
    'uniqueId',
    'mrn',
    'status',
    'isClient',
    'admissionDateTime',
    'firstContactDate',
    'dischargeDateTime',
    'actualSysDischargeDateTime',
    'isDischarge',
    'facilityName',
    'levelOfCare',
    'primaryClinician',
    'primaryClinicians',
]


def _all_patient_record_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        'patient_id': _patient_id(payload),
        'source_id': _first_text(payload, 'id', 'uniqueId', 'mrn'),
        'admission_date': _date_only(payload.get('admissionDateTime') or payload.get('admissionDate')),
        'status': _first_text(payload, 'status'),
        'is_client': _bool_value(payload.get('isClient'), default=True),
        'discharge_date': _date_only(payload.get('dischargeDateTime')),
        'actual_sys_discharge_date': _date_only(payload.get('actualSysDischargeDateTime')),
        'is_discharge': _bool_value(payload.get('isDischarge'), default=False),
        'level_of_care': _first_text(payload, 'levelOfCare'),
        'facility': _first_text(payload, 'facilityName'),
        'primary_clinician': _first_text(payload, 'primaryClinician', 'primaryClinicians'),
        'first_contact_date': _date_only(payload.get('firstContactDate')),
    }


def _tsv_value(value: Any) -> str:
    return _text(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')


def _rows_to_tsv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    return '\n'.join(['\t'.join(columns), *['\t'.join(_tsv_value(row.get(column)) for column in columns) for row in rows]])


def _is_active_patient(payload: dict[str, Any]) -> bool:
    status = _first_text(payload, 'status').lower()
    if status and any(word in status for word in ('inactive', 'discharge', 'closed', 'deceased')):
        return False
    status_is_active = bool(status and 'active' in status)
    if _bool_value(payload.get('isDischarge'), default=False) and not status_is_active:
        return False
    if not status and _text(payload.get('dischargeDateTime') or payload.get('actualSysDischargeDateTime')):
        return False
    if payload.get('isClient') is not None and not _bool_value(payload.get('isClient'), default=True):
        return False
    return True


def _quick_pull_path(report: str) -> str:
    return '/clients' if report in {'all_patient_records', 'active_patients', 'patient_treatment_plan_aggregates'} else '/treatment-plans'


def _http_status_label(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = ''
    return f'HTTP {status_code}{f" {phrase}" if phrase else ""}'


def _quick_pull_http_failure_message(*, path: str, status_code: int, api_version: str) -> tuple[str, str]:
    status_label = _http_status_label(status_code)
    if status_code == 401:
        return (
            'endpoint_authorization_failed',
            (
                f'Authentication reached Alleva, but Alleva rejected GET {path} with {status_label}. '
                f'Ask R3/Alleva to confirm this client ID has tenant access and read permission for {path}, '
                f'the correct token audience/scope, and API version {api_version}.'
            ),
        )
    if status_code == 403:
        return (
            'endpoint_permission_denied',
            f'Authentication worked, but the saved credentials are not permitted to read GET {path} ({status_label}). Ask Alleva to add the required read permission/scope.',
        )
    if status_code in {400, 404, 405}:
        return (
            'endpoint_mapping_or_version_failed',
            f'Alleva rejected GET {path} with {status_label}. Confirm the path, Limit/Cursor/api-version parameters, X-Version header, and approved API version.',
        )
    if status_code == 429:
        return ('endpoint_rate_limited', f'Alleva rate-limited GET {path} ({status_label}). Wait and try again, or ask Alleva about tenant rate limits.')
    if 500 <= status_code <= 599:
        return ('endpoint_vendor_unavailable', f'Alleva returned {status_label} for GET {path}. Try again later or confirm vendor availability.')
    return ('endpoint_request_failed', f'Alleva returned {status_label} for GET {path}. Confirm credentials, endpoint mapping, and API version.')


def _row_end_date_before(row: dict[str, Any], today: date) -> bool:
    try:
        return bool(row.get('end_date')) and date.fromisoformat(str(row['end_date'])[:10]) < today
    except ValueError:
        return False


def _query_and_headers(operation_parameters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    query: dict[str, Any] = {}
    headers = {'Accept': 'application/json'}
    for key, value in operation_parameters.items():
        if value in (None, ''):
            continue
        if key.lower() == 'x-version':
            headers['X-Version'] = str(value)
        else:
            query[key] = value
    api_version = _text(operation_parameters.get('api-version')) or _text(operation_parameters.get('X-Version')) or '1.0'
    query.setdefault('api-version', api_version)
    headers.setdefault('X-Version', api_version)
    return query, headers


def _fetch_alleva_collection(
    *,
    base_url: str,
    path: str,
    operation_parameters: dict[str, Any],
    api_key: str,
    bearer_token: str,
    api_key_header_name: str,
    timeout_seconds: int,
    max_pages: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    query, headers = _query_and_headers(operation_parameters)
    if api_key:
        headers[api_key_header_name or DEFAULT_API_KEY_HEADER_NAME] = api_key
    if bearer_token:
        headers['Authorization'] = f'Bearer {bearer_token}'
    try:
        limit = max(1, min(int(query.get('Limit') or 500), 5000))
    except (TypeError, ValueError):
        limit = 500
    try:
        cursor = max(0, int(query.get('Cursor') or 0))
    except (TypeError, ValueError):
        cursor = 0

    records: list[dict[str, Any]] = []
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for page_index in range(max_pages):
            page_query = dict(query)
            page_query['Limit'] = limit
            page_query['Cursor'] = cursor
            api_version = _text(page_query.get('api-version')) or _text(headers.get('X-Version')) or '1.0'
            try:
                response = client.get(url, params=page_query, headers=headers)
                response.read()
            except httpx.TimeoutException:
                return records, {
                    'category': 'network_timeout',
                    'message': f'Alleva did not respond before the configured timeout while reading GET {path}. Increase the timeout or try again when the network is stable.',
                    'page_index': page_index,
                    'url': redact_url(url),
                }
            except httpx.RequestError:
                return records, {
                    'category': 'network_failure',
                    'message': f'The app could not reach Alleva GET {path}. Check internet access, the REST API base URL, and local firewall/proxy settings.',
                    'page_index': page_index,
                    'url': redact_url(url),
                }
            if not 200 <= response.status_code < 300:
                category, message = _quick_pull_http_failure_message(path=path, status_code=response.status_code, api_version=api_version)
                return records, {
                    'category': category,
                    'status_code': response.status_code,
                    'message': message,
                    'response_body_preview': UPSTREAM_BODY_PREVIEW_OMITTED,
                    'page_index': page_index,
                    'url': redact_url(str(response.url)),
                }
            try:
                page_records = _list_records(response.json())
            except ValueError:
                return records, {
                    'category': 'endpoint_non_json_response',
                    'status_code': response.status_code,
                    'message': f'Alleva GET {path} responded, but the response was not JSON. Confirm this endpoint path and API version {api_version}.',
                    'response_body_preview': UPSTREAM_BODY_PREVIEW_OMITTED,
                    'page_index': page_index,
                    'url': redact_url(str(response.url)),
                }
            records.extend(page_records)
            if len(page_records) < limit:
                break
            cursor += limit
    return records, None


def _run_alleva_aggregate_quick_pull(
    *,
    base_url: str,
    operation_parameters: dict[str, Any],
    auth_context: dict[str, Any],
    payload: AllevaQuickPullInput,
    timeout_seconds: int,
    today: date,
) -> dict[str, Any]:
    collections: dict[str, list[dict[str, Any]]] = {}
    fetch_errors: list[dict[str, Any]] = []
    for label, path in (
        ('clients', '/clients'),
        ('treatment_plans', '/treatment-plans'),
        ('treatment_reviews', '/treatment-reviews'),
    ):
        records, fetch_error = _fetch_alleva_collection(
            base_url=base_url,
            path=path,
            operation_parameters=operation_parameters,
            api_key=auth_context['api_key'],
            bearer_token=auth_context['bearer_token'],
            api_key_header_name=payload.api_key_header_name or DEFAULT_API_KEY_HEADER_NAME,
            timeout_seconds=timeout_seconds,
            max_pages=payload.max_pages,
        )
        collections[label] = records
        if fetch_error:
            fetch_errors.append({'endpoint': path, **fetch_error})

    aggregate_result = build_patient_treatment_plan_aggregate_result(
        clients_payload=collections.get('clients', []),
        treatment_plans_payload=collections.get('treatment_plans', []),
        treatment_reviews_payload=collections.get('treatment_reviews', []),
        options=AggregateBuildOptions(today=today, include_patient_name=False, allow_name_fallback=False),
    )
    rows = aggregate_result.aggregates
    total_records_seen = sum(len(records) for records in collections.values())
    status = 'ok'
    if fetch_errors and not rows:
        status = 'fail'
    elif fetch_errors or not rows:
        status = 'warn'
    if status == 'ok':
        message = f'Alleva aggregate pull built {len(rows)} patient treatment-plan aggregate(s) from {total_records_seen} fetched record(s).'
    elif rows:
        message = f'Alleva aggregate pull built {len(rows)} aggregate(s), but one or more source endpoints could not finish.'
    else:
        message = 'Alleva aggregate pull did not produce patient treatment-plan aggregates. Confirm endpoint permissions and source data.'
    return {
        'status': status,
        'message': message,
        'rows': rows,
        'aggregates': rows,
        'returned_count': len(rows),
        'total_records_seen': total_records_seen,
        'fetch_errors': fetch_errors,
        'fetch_error': fetch_errors[0] if fetch_errors else None,
        'diagnostics': aggregate_result.diagnostics,
        'category': 'completed' if status == 'ok' else ('partial_source_failure' if rows else 'no_aggregates_returned'),
        'columns': [],
        'tsv': '',
        'copy_format': 'json',
    }


@router.get('/api-configuration/sample-openapi.json', include_in_schema=False)
def sample_openapi_definition():
    """Small local OpenAPI file used by the full-stack smoke test."""
    return SAMPLE_OPENAPI_DEFINITION


@router.get('/api-configuration/operation-test-target/{patient_id}', include_in_schema=False)
def sample_operation_test_target(patient_id: str, include_documents: bool):
    return {
        'patient_id': patient_id,
        'include_documents': include_documents,
        'documents': [{'id': 'doc-001', 'type': 'progress_note'}] if include_documents else [],
        'source': 'local sample operation target',
    }


@router.post('/api-configuration/operation-test-target/{patient_id}', include_in_schema=False)
async def sample_operation_post_target(patient_id: str, request: Request):
    body = await request.json()
    return {
        'patient_id': patient_id,
        'accepted': True,
        'received': body,
        'source': 'local sample operation target',
    }


@router.get('/api-configuration', response_model=ApiConfigurationOut)
def get_api_configuration(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    settings_row = get_or_create_app_settings(db)
    log_event(
        db,
        request,
        'api_configuration.read',
        actor=user,
        event_category='api_configuration',
        target_entity='api_configuration',
        target_entity_type='app_settings',
        target_entity_id=str(settings_row.id),
        details={'vendor_name': settings_row.emr_vendor_name, 'api_key_configured': bool(settings_row.api_client_secret)},
        message='API configuration viewed.',
    )
    return _configuration_out(settings_row)


@router.patch('/api-configuration', response_model=ApiConfigurationOut)
def update_api_configuration(
    payload: ApiConfigurationUpdate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    before = _snapshot(settings_row)
    api_key_changed = False
    api_key_cleared = False

    if payload.vendor_name is not None:
        settings_row.emr_vendor_name = _strip(payload.vendor_name) or 'Alleva API'
    if payload.api_base_url is not None:
        settings_row.alleva_api_base_url = _strip(payload.api_base_url) or 'https://api.allevasoft.com'
    if payload.openapi_url is not None:
        settings_row.alleva_openapi_url = _strip(payload.openapi_url) or 'https://api.allevasoft.com/swagger/v1/swagger.json'
    if payload.timeout_seconds is not None:
        settings_row.emr_api_timeout_seconds = payload.timeout_seconds
    if payload.api_enabled is not None:
        settings_row.emr_api_enabled = payload.api_enabled
    if payload.clear_api_key:
        settings_row.api_client_secret = ''
        api_key_cleared = True
    elif payload.api_key and payload.api_key.strip():
        settings_row.api_client_secret = encrypt_text_secret(payload.api_key.strip())
        api_key_changed = True
    if payload.client_id is not None:
        settings_row.api_client_id = _strip(payload.client_id)
    if payload.clear_client_secret:
        settings_row.api_client_secret = ''
        api_key_cleared = True
    elif payload.client_secret and payload.client_secret.strip():
        settings_row.api_client_secret = encrypt_text_secret(payload.client_secret.strip())
        api_key_changed = True
    if payload.token_url is not None:
        settings_row.api_oauth_token_url = _strip(payload.token_url) or DEFAULT_ALLEVA_TOKEN_URL
    if payload.token_auth_style is not None:
        settings_row.api_token_auth_style = payload.token_auth_style

    settings_row.updated_by_id = user.id
    settings_row.updated_at = _utc_now()
    db.commit()
    db.refresh(settings_row)
    after = _snapshot(settings_row)

    log_event(
        db,
        request,
        'api_configuration.update',
        actor=user,
        event_category='api_configuration',
        target_entity='api_configuration',
        target_entity_type='app_settings',
        target_entity_id=str(settings_row.id),
        details={
            'api_key_changed': api_key_changed,
            'api_key_cleared': api_key_cleared,
            'vendor_name': settings_row.emr_vendor_name,
            'api_base_url_configured': bool(settings_row.alleva_api_base_url),
            'client_id_configured': bool(settings_row.api_client_id),
            'token_url_configured': bool(settings_row.api_oauth_token_url),
            'token_auth_style': getattr(settings_row, 'api_token_auth_style', 'body'),
        },
        before_state=before,
        after_state=after,
        message='API configuration updated.',
    )
    return _configuration_out(settings_row)


@router.post('/api-configuration/pull-definitions')
def pull_api_configuration_definitions(
    payload: ApiDefinitionPullInput,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    api_base_url = _strip(payload.api_base_url) or settings_row.alleva_api_base_url
    swagger_ui_url = _strip(payload.swagger_ui_url) or DEFAULT_ALLEVA_SWAGGER_UI_URL
    openapi_url = _strip(payload.openapi_url) or _default_openapi_url(settings_row)
    timeout_seconds = payload.timeout_seconds or settings_row.emr_api_timeout_seconds
    auth_context = _auth_context(payload, settings_row, timeout_seconds=timeout_seconds)
    auth_request_payload = {
        'swagger_ui_url': swagger_ui_url,
        'api_base_url': api_base_url,
        'openapi_url': openapi_url,
        'api_key': auth_context['api_key'],
        'api_key_source': auth_context['api_key_source'],
        'auth_mode': auth_context['auth_mode'],
        'token_url': auth_context['token_url'],
        'token_auth_style': auth_context['token_auth_style'],
        'client_id_configured': bool(_strip(payload.client_id) or settings_row.api_client_id),
        'client_secret': _strip(payload.client_secret) or (_saved_api_key(settings_row) if payload.use_saved_client_credentials else ''),
        'credential_source': auth_context['credential_source'],
        'scope': auth_context['scope'],
        'bearer_token': auth_context['bearer_token'],
        'timeout_seconds': timeout_seconds,
    }
    if payload.auth_mode == 'client_credentials' and not auth_context['bearer_token']:
        result = _auth_failure_result(auth_context=auth_context, report_type='api_definition_pull', request_payload=auth_request_payload)
        status = result.get('status')
        log_event(
            db,
            request,
            'api_configuration.pull_definitions',
            actor=user,
            event_category='api_connectivity',
            target_entity='api_definition',
            target_entity_type='external_api',
            target_entity_id=redact_url(swagger_ui_url),
            details={
                'status': status,
                'vendor_name': settings_row.emr_vendor_name,
                'auth_mode': payload.auth_mode,
                'token_status': auth_context['token_result'].get('status') if isinstance(auth_context.get('token_result'), dict) else 'fail',
                'token_auth_style': auth_context['token_auth_style'],
                'credential_source': auth_context['credential_source'],
            },
            outcome_status='failure',
            severity='warning',
            message=f'API definition pull authentication failed with status {status}.',
        )
        return result

    result = pull_api_definitions(
        swagger_ui_url=swagger_ui_url,
        api_base_url=api_base_url,
        openapi_url=openapi_url,
        api_key=auth_context['api_key'],
        bearer_token=auth_context['bearer_token'],
        api_key_header_name=payload.api_key_header_name or DEFAULT_API_KEY_HEADER_NAME,
        timeout_seconds=timeout_seconds,
    )
    result['auth_mode'] = payload.auth_mode
    if auth_context['token_result']:
        result['token_result'] = auth_context['token_result']
    result['report'] = build_api_connectivity_report(
        report_type='api_definition_pull',
        request=auth_request_payload,
        result=result,
    )
    result['report_path'] = persist_api_connectivity_report(result['report'])
    status = result.get('status')
    log_event(
        db,
        request,
        'api_configuration.pull_definitions',
        actor=user,
        event_category='api_connectivity',
        target_entity='api_definition',
        target_entity_type='external_api',
        target_entity_id=redact_url(str(result.get('selected_definition_url') or swagger_ui_url)),
        details={
            'status': status,
            'vendor_name': settings_row.emr_vendor_name,
            'swagger_ui_url': redact_url(swagger_ui_url),
            'api_base_url': redact_url(api_base_url),
            'openapi_url': redact_url(openapi_url),
            'auth_mode': payload.auth_mode,
            'api_key_used': bool(auth_context['api_key']),
            'api_key_source': auth_context['api_key_source'],
            'bearer_token_used': bool(auth_context['bearer_token']),
            'credential_source': auth_context['credential_source'],
            'token_status': auth_context['token_result'].get('status') if isinstance(auth_context.get('token_result'), dict) else '',
            'token_auth_style': auth_context['token_auth_style'],
            'probe_count': len(result.get('probes', [])),
        },
        outcome_status='success' if status == 'ok' else 'failure',
        severity='info' if status == 'ok' else 'warning',
        message=f'API definition pull completed with status {status}.',
    )
    return result


@router.post('/api-configuration/test')
def test_api_configuration(
    payload: ApiDefinitionPullInput,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    """Compatibility alias for users who expect a named connectivity test action."""
    return pull_api_configuration_definitions(payload, request, user, db)


@router.post('/api-configuration/test-operation')
def test_api_configuration_operation(
    payload: ApiOperationTestInput,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    timeout_seconds = payload.timeout_seconds or settings_row.emr_api_timeout_seconds
    auth_context = _auth_context(payload, settings_row, timeout_seconds=timeout_seconds)
    auth_request_payload = {
        'method': payload.method.upper(),
        'path': payload.path,
        'api_base_url': _strip(payload.api_base_url) or settings_row.alleva_api_base_url,
        'selected_definition_url': _strip(payload.selected_definition_url),
        'api_key': auth_context['api_key'],
        'api_key_source': auth_context['api_key_source'],
        'auth_mode': auth_context['auth_mode'],
        'token_url': auth_context['token_url'],
        'token_auth_style': auth_context['token_auth_style'],
        'client_id_configured': bool(_strip(payload.client_id) or settings_row.api_client_id),
        'client_secret': _strip(payload.client_secret) or (_saved_api_key(settings_row) if payload.use_saved_client_credentials else ''),
        'credential_source': auth_context['credential_source'],
        'scope': auth_context['scope'],
        'bearer_token': auth_context['bearer_token'],
        'timeout_seconds': timeout_seconds,
        'parameters': payload.parameters,
        'request_body': payload.request_body,
    }
    if payload.auth_mode == 'client_credentials' and not auth_context['bearer_token']:
        result = _auth_failure_result(auth_context=auth_context, report_type='api_operation_test', request_payload=auth_request_payload)
        log_event(
            db,
            request,
            'api_configuration.test_operation',
            actor=user,
            event_category='api_connectivity',
            target_entity=f"{payload.method.upper()} {payload.path}",
            target_entity_type='external_api_operation',
            details={
                'status': 'fail',
                'method': payload.method.upper(),
                'path': payload.path,
                'auth_mode': payload.auth_mode,
                'credential_source': auth_context['credential_source'],
                'token_status': auth_context['token_result'].get('status') if isinstance(auth_context.get('token_result'), dict) else 'fail',
                'token_auth_style': auth_context['token_auth_style'],
            },
            outcome_status='failure',
            severity='warning',
            message=f"API operation test authentication failed for {payload.method.upper()} {payload.path}.",
        )
        return result

    result = execute_openapi_operation(
        definition=payload.definition,
        selected_definition_url=_strip(payload.selected_definition_url),
        api_base_url=_strip(payload.api_base_url) or settings_row.alleva_api_base_url,
        method=payload.method,
        path=payload.path,
        parameters=payload.parameters,
        request_body=payload.request_body,
        api_key=auth_context['api_key'],
        bearer_token=auth_context['bearer_token'],
        api_key_header_name=payload.api_key_header_name or DEFAULT_API_KEY_HEADER_NAME,
        timeout_seconds=timeout_seconds,
    )
    result['auth_mode'] = payload.auth_mode
    if auth_context['token_result']:
        result['token_result'] = auth_context['token_result']
    result['report'] = build_api_connectivity_report(
        report_type='api_operation_test',
        request=auth_request_payload,
        result=result,
    )
    result['report_path'] = persist_api_connectivity_report(result['report'])
    status = result.get('status')
    log_event(
        db,
        request,
        'api_configuration.test_operation',
        actor=user,
        event_category='api_connectivity',
        target_entity=f"{payload.method.upper()} {payload.path}",
        target_entity_type='external_api_operation',
        details={
            'status': status,
            'method': payload.method.upper(),
            'path': payload.path,
            'auth_mode': payload.auth_mode,
            'api_key_used': bool(auth_context['api_key']),
            'api_key_source': auth_context['api_key_source'],
            'bearer_token_used': bool(auth_context['bearer_token']),
            'credential_source': auth_context['credential_source'],
            'token_status': auth_context['token_result'].get('status') if isinstance(auth_context.get('token_result'), dict) else '',
            'token_auth_style': auth_context['token_auth_style'],
            'http_status': result.get('status_code'),
        },
        outcome_status='success' if status == 'ok' else 'failure',
        severity='info' if status == 'ok' else 'warning',
        message=f"API operation test completed for {payload.method.upper()} {payload.path} with status {status}.",
    )
    return result


@router.post('/api-configuration/alleva-quick-pull')
def run_alleva_quick_pull(
    payload: AllevaQuickPullInput,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    timeout_seconds = payload.timeout_seconds or settings_row.emr_api_timeout_seconds
    auth_context = _auth_context(payload, settings_row, timeout_seconds=timeout_seconds)
    operation_parameters = dict(payload.operation_parameters or {})
    if payload.report in TREATMENT_PLAN_HARNESS_REPORTS:
        operation_parameters = treatment_plan_default_parameters(operation_parameters)
    else:
        operation_parameters.setdefault('Limit', 500)
        operation_parameters.setdefault('Cursor', 0)
        operation_parameters.setdefault('api-version', '1.0')
        operation_parameters.setdefault('X-Version', '1.0')
    path = _quick_pull_path(payload.report)
    source_operation = (
        'GET /clients + GET /treatment-plans + GET /treatment-reviews'
        if payload.report == 'patient_treatment_plan_aggregates'
        else f'GET {path}'
    )
    if payload.report == 'all_patient_records':  # noqa: IF_VARIANT_OK - legacy quick-pull report routing, not a closed enum boundary.
        operation_parameters.setdefault('fields', ALL_PATIENT_RECORD_FIELDS)
    base_url = _strip(payload.api_base_url) or settings_row.alleva_api_base_url or 'https://api.allevasoft.com'
    quick_pull_request_payload = {
        'report': payload.report,
        'swagger_ui_url': _strip(payload.swagger_ui_url),
        'api_base_url': base_url,
        'openapi_url': _strip(payload.openapi_url) or _default_openapi_url(settings_row),
        'api_key': auth_context['api_key'],
        'api_key_source': auth_context['api_key_source'],
        'auth_mode': auth_context['auth_mode'],
        'token_url': auth_context['token_url'],
        'token_auth_style': auth_context['token_auth_style'],
        'client_id_configured': bool(_strip(payload.client_id) or settings_row.api_client_id),
        'client_secret_configured': bool(_strip(payload.client_secret) or (settings_row.api_client_secret if payload.use_saved_client_credentials else '')),
        'credential_source': auth_context['credential_source'],
        'scope': auth_context['scope'],
        'bearer_token': auth_context['bearer_token'],
        'timeout_seconds': timeout_seconds,
        'operation_parameters': operation_parameters,
        'patient_id': payload.patient_id,
    }

    if payload.auth_mode == 'client_credentials' and not auth_context['bearer_token']:
        token_result = auth_context.get('token_result') if isinstance(auth_context.get('token_result'), dict) else {}
        message = f"Authentication failed before the Alleva pull could run: {token_result.get('message') or 'token request did not return an access token.'}"
        result = {
            'status': 'fail',
            'message': message,
            'report': payload.report,
            'source_operation': source_operation,
            'operation_parameters': operation_parameters,
            'category': 'token_request_failed',
            'columns': ALL_PATIENT_RECORD_COLUMNS if payload.report == 'all_patient_records' else [],
            'tsv': _rows_to_tsv([], ALL_PATIENT_RECORD_COLUMNS) if payload.report == 'all_patient_records' else '',
            'copy_format': 'tsv' if payload.report == 'all_patient_records' else '',
            'rows': [],
            'total_records_seen': 0,
            'returned_count': 0,
            'token_result': token_result,
        }
        if payload.report in TREATMENT_PLAN_HARNESS_REPORTS:
            result['report'] = build_api_connectivity_report(
                report_type=f'alleva_{payload.report}',
                request=quick_pull_request_payload,
                result=result,
            )
            result['report_path'] = persist_api_connectivity_report(result['report'])
        log_event(
            db,
            request,
            'api_configuration.alleva_quick_pull',
            actor=user,
            event_category='api_connectivity',
            target_entity=source_operation,
            target_entity_type='external_api_operation',
            details={
                'status': result['status'],
                'report': payload.report,
                'auth_mode': payload.auth_mode,
                'credential_source': auth_context['credential_source'],
                'token_status': token_result.get('status'),
                'returned_count': 0,
            },
            outcome_status='failure',
            severity='warning',
            message=f'Alleva quick pull authentication failed for {payload.report}.',
        )
        return result

    if payload.report in TREATMENT_PLAN_HARNESS_REPORTS:
        harness_result = run_treatment_plan_harness_pull(
            TreatmentPlanHarnessRequest(
                report=payload.report,
                base_url=base_url,
                operation_parameters=operation_parameters,
                api_key=auth_context['api_key'],
                bearer_token=auth_context['bearer_token'],
                api_key_header_name=payload.api_key_header_name or DEFAULT_API_KEY_HEADER_NAME,
                timeout_seconds=timeout_seconds,
                patient_id=payload.patient_id or '',
            )
        )
        result = {
            'report': payload.report,
            'source_operation': source_operation,
            'operation_parameters': operation_parameters,
            'max_pages': payload.max_pages,
            'auth_mode': payload.auth_mode,
            'api_key_used': bool(auth_context['api_key']),
            'bearer_token_used': bool(auth_context['bearer_token']),
            'credential_source': auth_context['credential_source'],
            'token_result': auth_context['token_result'] if auth_context.get('token_result') else {},
            **harness_result,
        }
        result['report'] = build_api_connectivity_report(
            report_type=f'alleva_{payload.report}',
            request=quick_pull_request_payload,
            result=result,
        )
        result['report_path'] = persist_api_connectivity_report(result['report'])
        log_event(
            db,
            request,
            'api_configuration.alleva_quick_pull',
            actor=user,
            event_category='api_connectivity',
            target_entity=source_operation,
            target_entity_type='external_api_operation',
            details={
                'status': result['status'],
                'report': payload.report,
                'auth_mode': payload.auth_mode,
                'api_key_used': bool(auth_context['api_key']),
                'bearer_token_used': bool(auth_context['bearer_token']),
                'credential_source': auth_context['credential_source'],
                'http_status': result.get('status_code'),
                'response_truncated': result.get('response_truncated'),
                'total_records_seen': result['total_records_seen'],
                'returned_count': result['returned_count'],
            },
            outcome_status='failure' if result['status'] == 'fail' else 'success',
            severity='info' if result['status'] == 'ok' else 'warning',
            message=f'Alleva quick pull completed for {payload.report} with status {result["status"]}.',
        )
        return result

    if payload.report == 'patient_treatment_plan_aggregates':
        aggregate_result = _run_alleva_aggregate_quick_pull(
            base_url=base_url,
            operation_parameters=operation_parameters,
            auth_context=auth_context,
            payload=payload,
            timeout_seconds=timeout_seconds,
            today=_utc_now().date(),
        )
        result = {
            'report': payload.report,
            'source_operation': source_operation,
            'operation_parameters': operation_parameters,
            'max_pages': payload.max_pages,
            'auth_mode': payload.auth_mode,
            'api_key_used': bool(auth_context['api_key']),
            'bearer_token_used': bool(auth_context['bearer_token']),
            'credential_source': auth_context['credential_source'],
            'token_result': auth_context['token_result'] if auth_context.get('token_result') else {},
            **aggregate_result,
        }
        log_event(
            db,
            request,
            'api_configuration.alleva_quick_pull',
            actor=user,
            event_category='api_connectivity',
            target_entity=source_operation,
            target_entity_type='external_api_operation',
            details={
                'status': result['status'],
                'report': payload.report,
                'auth_mode': payload.auth_mode,
                'api_key_used': bool(auth_context['api_key']),
                'bearer_token_used': bool(auth_context['bearer_token']),
                'credential_source': auth_context['credential_source'],
                'total_records_seen': result['total_records_seen'],
                'returned_count': result['returned_count'],
                'fetch_error_count': len(result['fetch_errors']),
                'diagnostic_codes': result['diagnostics'].get('data_quality_codes', {}),
            },
            outcome_status='failure' if result['status'] == 'fail' else 'success',
            severity='info' if result['status'] == 'ok' else 'warning',
            message=f'Alleva quick pull completed for {payload.report} with status {result["status"]}.',
        )
        return result

    records, fetch_error = _fetch_alleva_collection(
        base_url=base_url,
        path=path,
        operation_parameters=operation_parameters,
        api_key=auth_context['api_key'],
        bearer_token=auth_context['bearer_token'],
        api_key_header_name=payload.api_key_header_name or DEFAULT_API_KEY_HEADER_NAME,
        timeout_seconds=timeout_seconds,
        max_pages=payload.max_pages,
    )

    today = _utc_now().date()
    columns: list[str] = []
    tsv = ''
    copy_format = ''
    if payload.report == 'all_patient_records':  # noqa: IF_VARIANT_OK - legacy quick-pull report routing, not a closed enum boundary.
        rows = [_all_patient_record_summary(item) for item in records]
        columns = ALL_PATIENT_RECORD_COLUMNS
        tsv = _rows_to_tsv(rows, columns)
        copy_format = 'tsv'
        message_subject = 'patient record(s)'
    elif payload.report == 'active_patients':
        rows = [_active_patient_summary(item) for item in records if _is_active_patient(item)]
        message_subject = 'active patient(s)'
    else:
        plan_rows = [_plan_summary(item, today=today) for item in records]
        if payload.report == 'active_treatment_plans':  # noqa: IF_VARIANT_OK - legacy quick-pull report routing, not a closed enum boundary.
            rows = [item for item in plan_rows if item['is_active']]
            message_subject = 'active treatment plan(s)'
        elif payload.report == 'overdue_treatment_plans':
            rows = [item for item in plan_rows if item['is_active'] and _row_end_date_before(item, today)]
            message_subject = 'overdue active treatment plan(s)'
        else:
            rows = [item for item in plan_rows if not item['is_active']]
            message_subject = 'inactive treatment plan(s)'

    if fetch_error:
        status = 'warn' if records else 'fail'
        message = (
            f'Alleva pull could not finish: {fetch_error["message"]} '
            f'Returned {len(rows)} row(s) from {len(records)} record(s) fetched before the stop.'
        )
    elif not rows:
        status = 'warn'
        message = f'Alleva pull reached {source_operation} but returned no {message_subject}. Confirm the tenant, date filters, and API permissions if records were expected.'
    elif payload.report == 'all_patient_records':
        status = 'ok'
        message = (
            f'ALL Patient Records pull returned {len(rows)} row(s) from {len(records)} fetched record(s). '
            'Copy the TSV output into Excel if needed.'
        )
    else:
        status = 'ok'
        message = f'Alleva quick pull found {len(rows)} {message_subject} from {len(records)} fetched record(s).'
    result = {
        'status': status,
        'message': message,
        'report': payload.report,
        'source_operation': source_operation,
        'operation_parameters': operation_parameters,
        'max_pages': payload.max_pages,
        'total_records_seen': len(records),
        'returned_count': len(rows),
        'columns': columns,
        'tsv': tsv,
        'copy_format': copy_format,
        'rows': rows,
        'fetch_error': fetch_error,
        'category': fetch_error.get('category') if fetch_error else ('no_records_returned' if not rows else 'completed'),
        'auth_mode': payload.auth_mode,
        'api_key_used': bool(auth_context['api_key']),
        'bearer_token_used': bool(auth_context['bearer_token']),
        'credential_source': auth_context['credential_source'],
        'token_result': auth_context['token_result'] if auth_context.get('token_result') else {},
    }
    log_event(
        db,
        request,
        'api_configuration.alleva_quick_pull',
        actor=user,
        event_category='api_connectivity',
        target_entity=source_operation,
        target_entity_type='external_api_operation',
        details={
            'status': status,
            'report': payload.report,
            'auth_mode': payload.auth_mode,
            'api_key_used': bool(auth_context['api_key']),
            'bearer_token_used': bool(auth_context['bearer_token']),
            'credential_source': auth_context['credential_source'],
            'total_records_seen': len(records),
            'returned_count': len(rows),
            'fetch_error_status_code': fetch_error.get('status_code') if fetch_error else None,
            'fetch_error_category': fetch_error.get('category') if fetch_error else '',
        },
        outcome_status='failure' if status == 'fail' else 'success',
        severity='info' if status == 'ok' else 'warning',
        message=f'Alleva quick pull completed for {payload.report} with status {status}.',
    )
    return result
