from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

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
from app.services.secure_storage import decrypt_text_secret, encrypt_text_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api')
DEFAULT_API_KEY_HEADER_NAME = 'x-api-key'

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
