import httpx
from pathlib import Path

from app.services.api_connectivity import (
    REDACTED,
    build_api_connectivity_report,
    candidate_definition_urls,
    execute_openapi_operation,
    extract_swagger_ui_definition_urls,
    extract_openapi_operations,
    pull_api_definitions,
    request_client_credentials_token,
)

OriginalHttpxClient = httpx.Client


class MockedHttpxClient:
    def __init__(self, *args, **kwargs):
        self._client = OriginalHttpxClient(transport=httpx.MockTransport(self._handler), follow_redirects=True)

    def __enter__(self):
        return self._client

    def __exit__(self, exc_type, exc, tb):
        self._client.close()

    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == 'https://authorization.example.test/connect/token':
            body = request.content.decode('utf-8')
            assert 'grant_type=client_credentials' in body
            if request.headers.get('authorization', '').startswith('Basic '):
                assert 'client_id=' not in body
                assert 'client_secret=' not in body
            else:
                assert 'client_id=mock-client' in body or 'client_id=saved-client' in body
                assert 'client_secret=mock-secret' in body or 'client_secret=saved-secret' in body
            return httpx.Response(
                200,
                json={
                    'access_token': 'mock-access-token',
                    'token_type': 'Bearer',
                    'expires_in': 3600,
                },
            )
        if url.endswith('/swagger/index.html'):
            return httpx.Response(200, text="SwaggerUIBundle({ url: '/swagger/v1/swagger.json' })")
        if url.endswith('/swagger/v1/swagger.json'):
            if request.headers.get('authorization') == 'Bearer mock-access-token':
                assert 'x-api-key' not in request.headers
            else:
                assert request.headers.get('x-api-key') in {'test-key', 'saved-secret-api-key'}
                assert request.headers.get('authorization') in {'Bearer test-key', 'Bearer saved-secret-api-key'}
            return httpx.Response(
                200,
                json={
                    'openapi': '3.0.3',
                    'info': {'title': 'Mock Alleva API', 'version': '1.0.0'},
                    'paths': {'/patients': {'get': {'responses': {'200': {'description': 'ok'}}}}},
                    'components': {
                        'schemas': {'Patient': {'type': 'object'}},
                        'securitySchemes': {'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': 'x-api-key'}},
                    },
                },
            )
        if url == 'https://api.example.test/patients/PAT-001?include_documents=True':
            return httpx.Response(200, json={'patient_id': 'PAT-001', 'include_documents': True})
        if url == 'https://api.example.test/patients/PAT-SECRET?include_documents=False':
            assert request.headers.get('x-api-key') == 'inline-secret-key'
            return httpx.Response(
                200,
                json={
                    'patient_id': 'PAT-SECRET',
                    'access_token': 'server-returned-token',
                    'nested': {'api_key': 'server-returned-api-key'},
                    'items': [{'client_secret': 'server-returned-client-secret'}],
                },
            )
        if url == 'https://api.example.test/patients/PAT-001/notes':
            assert request.method == 'POST'
            assert request.headers.get('x-api-key') == 'test-key'
            return httpx.Response(201, json={'created': True, 'payload': {'accepted': True}})
        if url == 'https://api.example.test/huge':
            return httpx.Response(200, json={'items': [{'row': index, 'text': 'x' * 2000} for index in range(200)]})
        if url.startswith('https://api.example.test/treatment-plans?'):
            assert request.headers.get('authorization') == 'Bearer mock-access-token'
            return httpx.Response(
                200,
                json=[
                    {
                        'id': 101,
                        'client': {'clientId': 'PAT-ACTIVE-001'},
                        'description': 'Current synthetic plan',
                        'startDate': '2026-01-01T00:00:00',
                        'endDate': '2099-12-31T00:00:00',
                        'isActive': True,
                        'isComplete': True,
                        'lastModified': '2026-01-02T00:00:00',
                    },
                    {
                        'id': 102,
                        'client': {'clientId': 'PAT-OVERDUE-001'},
                        'description': 'Overdue synthetic plan',
                        'startDate': '1999-01-01T00:00:00',
                        'endDate': '2000-01-01T00:00:00',
                        'isActive': True,
                        'isComplete': True,
                    },
                    {
                        'id': 103,
                        'client': {'clientId': 'PAT-INACTIVE-001'},
                        'description': 'Inactive synthetic plan',
                        'startDate': '2026-01-01T00:00:00',
                        'endDate': '2099-12-31T00:00:00',
                        'isActive': False,
                        'isComplete': True,
                    },
                ],
            )
        if url.startswith('https://api.example.test/clients?'):
            assert request.headers.get('authorization') == 'Bearer mock-access-token'
            return httpx.Response(
                200,
                json=[
                    {
                        'id': 201,
                        'clientId': 'PAT-ACTIVE-001',
                        'name': {'clientFullName': 'Synthetic Active Client'},
                        'status': 'Active',
                        'isClient': True,
                        'admissionDateTime': '2026-02-03T09:00:00',
                        'facilityName': 'Synthetic Facility',
                        'levelOfCare': 'IOP',
                    },
                    {
                        'id': 202,
                        'clientId': 'PAT-DISCHARGED-001',
                        'name': {'clientFullName': 'Synthetic Discharged Client'},
                        'status': 'Discharged',
                        'isClient': True,
                        'admissionDateTime': '2025-02-03T09:00:00',
                        'dischargeDateTime': '2025-03-03T09:00:00',
                    },
                ],
            )
        return httpx.Response(404, text='not found')


class TimeoutHttpxClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    @staticmethod
    def get(url: str, headers: dict[str, str] | None = None):
        raise httpx.TimeoutException('synthetic timeout', request=httpx.Request('GET', url))


OPERATION_DEFINITION = {
    'openapi': '3.0.3',
    'info': {'title': 'Operation Test API', 'version': '1.0.0'},
    'paths': {
        '/patients/{patient_id}': {
            'get': {
                'summary': 'Read patient',
                'parameters': [
                    {'name': 'patient_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}},
                    {'name': 'include_documents', 'in': 'query', 'required': True, 'schema': {'type': 'boolean'}},
                ],
                'responses': {'200': {'description': 'ok'}},
            }
        },
        '/patients/{patient_id}/notes': {
            'post': {
                'summary': 'Create note',
                'parameters': [{'name': 'patient_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'required': ['note_type'],
                                'properties': {
                                    'note_type': {'type': 'string', 'enum': ['progress_note', 'treatment_plan_tracking']},
                                    'service_date': {'type': 'string', 'format': 'date'},
                                },
                            }
                        }
                    },
                },
                'responses': {'201': {'description': 'created'}},
            }
        },
        '/huge': {
            'get': {
                'summary': 'Huge response',
                'responses': {'200': {'description': 'ok'}},
            }
        },
    },
}


def test_candidate_definition_urls_includes_common_swagger_and_openapi_locations():
    urls = candidate_definition_urls(
        swagger_ui_url='https://api.example.test/swagger/index.html',
        api_base_url='https://api.example.test',
        openapi_url='https://api.example.test/custom/openapi.json',
    )

    assert urls[0] == 'https://api.example.test/custom/openapi.json'
    assert 'https://api.example.test/swagger/v1/swagger.json' in urls
    assert 'https://api.example.test/openapi.json' in urls


def test_extract_swagger_ui_definition_urls_handles_relative_url():
    html = "SwaggerUIBundle({ url: '/swagger/v1/swagger.json' })"
    urls = extract_swagger_ui_definition_urls(html, 'https://api.example.test/swagger/index.html')
    assert urls == ['https://api.example.test/swagger/v1/swagger.json']


def test_pull_api_definitions_discovers_and_summarizes_swagger_json(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    result = pull_api_definitions(
        swagger_ui_url='https://api.example.test/swagger/index.html',
        api_key='test-key',
        api_key_header_name='x-api-key',
        timeout_seconds=5,
    )

    assert result['status'] == 'ok'
    assert result['selected_definition_url'] == 'https://api.example.test/swagger/v1/swagger.json'
    assert result['api_key_used'] is True
    assert result['definition_summary']['title'] == 'Mock Alleva API'
    assert result['definition_summary']['path_count'] == 1
    assert result['definition_summary']['schema_count'] == 1
    assert result['definition_summary']['security_scheme_names'] == ['ApiKeyAuth']
    assert result['definition_summary']['sample_paths'] == ['/patients']
    assert result['operations'][0]['method'] == 'GET'
    assert result['operations'][0]['path'] == '/patients'


def test_client_credentials_token_request_returns_redacted_public_result(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    public_result, access_token = request_client_credentials_token(
        token_url='https://authorization.example.test/connect/token',
        client_id='mock-client',
        client_secret='mock-secret',
        scope='connectivity.read',
        timeout_seconds=5,
    )

    assert access_token == 'mock-access-token'
    assert public_result['status'] == 'ok'
    assert public_result['access_token_configured'] is True
    assert public_result['token_type'] == 'Bearer'
    assert 'mock-secret' not in str(public_result)
    assert 'mock-access-token' not in str(public_result)


def test_client_credentials_token_request_supports_basic_auth_style(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    public_result, access_token = request_client_credentials_token(
        token_url='https://authorization.example.test/connect/token',
        client_id='mock-client',
        client_secret='mock-secret',
        scope='connectivity.read',
        timeout_seconds=5,
        token_auth_style='basic',
    )

    assert access_token == 'mock-access-token'
    assert public_result['status'] == 'ok'
    assert public_result['token_auth_style'] == 'basic'
    assert public_result['attempted_token_auth_styles'] == ['basic']


def test_pull_api_definitions_can_use_client_credentials_bearer_token(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    token_result, access_token = request_client_credentials_token(
        token_url='https://authorization.example.test/connect/token',
        client_id='mock-client',
        client_secret='mock-secret',
        scope='connectivity.read',
        timeout_seconds=5,
    )
    result = pull_api_definitions(
        swagger_ui_url='https://api.example.test/swagger/index.html',
        bearer_token=access_token,
        timeout_seconds=5,
    )

    assert token_result['status'] == 'ok'
    assert result['status'] == 'ok'
    assert result['bearer_token_used'] is True
    assert result['api_key_used'] is False
    assert 'mock-access-token' not in str(build_api_connectivity_report(report_type='unit', request={'bearer_token': access_token}, result=result))


def test_pull_api_definitions_handles_invalid_and_timeout_urls(monkeypatch):
    invalid = pull_api_definitions(swagger_ui_url='not-a-url', openapi_url='also-not-a-url', api_base_url='')
    assert invalid['status'] == 'fail'
    assert invalid['probes'] == []

    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', TimeoutHttpxClient)
    timed_out = pull_api_definitions(swagger_ui_url='https://api.example.test/swagger/index.html', timeout_seconds=1)
    assert timed_out['status'] == 'fail'
    assert 'TimeoutException' in timed_out['probes'][0]['message']


def test_build_api_connectivity_report_redacts_secret_inputs_and_results():
    report = build_api_connectivity_report(
        report_type='unit',
        request={'api_key': 'request-secret', 'url': 'https://api.example.test?token=query-secret'},
        result={'response_json': {'access_token': 'response-secret'}, 'response_body_preview': 'Authorization: Bearer body-secret'},
    )

    serialized = str(report)
    assert 'request-secret' not in serialized
    assert 'query-secret' not in serialized
    assert 'response-secret' not in serialized
    assert 'body-secret' not in serialized
    assert report['request']['api_key'] == REDACTED


def test_extract_openapi_operations_returns_required_form_fields():
    operations = extract_openapi_operations(OPERATION_DEFINITION, selected_definition_url='https://api.example.test/swagger.json')
    get_operation = next(item for item in operations if item['method'] == 'GET' and item['path'] == '/patients/{patient_id}')
    post_operation = next(item for item in operations if item['method'] == 'POST')

    assert get_operation['operation_key'] == 'GET /patients/{patient_id}'
    assert [field['name'] for field in get_operation['parameters']] == ['patient_id', 'include_documents']
    assert all(field['required'] for field in get_operation['parameters'])
    assert post_operation['request_body_required'] is True
    assert post_operation['request_body_content_type'] == 'application/json'
    assert post_operation['request_body_fields'][0]['name'] == 'note_type'
    assert post_operation['request_body_fields'][0]['enum'] == ['progress_note', 'treatment_plan_tracking']


def test_execute_openapi_operation_builds_request_from_selected_definition(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    result = execute_openapi_operation(
        definition=OPERATION_DEFINITION,
        selected_definition_url='https://api.example.test/swagger.json',
        method='GET',
        path='/patients/{patient_id}',
        parameters={'patient_id': 'PAT-001', 'include_documents': True},
        api_key='test-key',
        api_key_header_name='x-api-key',
    )

    assert result['status'] == 'ok'
    assert result['status_code'] == 200
    assert result['response_json']['patient_id'] == 'PAT-001'


def test_execute_openapi_operation_validates_required_inputs(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    result = execute_openapi_operation(
        definition=OPERATION_DEFINITION,
        selected_definition_url='https://api.example.test/swagger.json',
        method='POST',
        path='/patients/{patient_id}/notes',
        parameters={'patient_id': 'PAT-001'},
        request_body={'service_date': '2026-05-14'},
    )

    assert result['status'] == 'fail'
    assert 'note_type' in result['missing']


def test_execute_openapi_operation_redacts_secret_response_fields(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    result = execute_openapi_operation(
        definition=OPERATION_DEFINITION,
        selected_definition_url='https://api.example.test/swagger.json',
        method='GET',
        path='/patients/{patient_id}',
        parameters={'patient_id': 'PAT-SECRET', 'include_documents': False},
        api_key='inline-secret-key',
        api_key_header_name='x-api-key',
    )

    assert result['status'] == 'ok'
    assert result['response_json']['access_token'] == REDACTED
    assert result['response_json']['nested']['api_key'] == REDACTED
    assert result['response_json']['items'][0]['client_secret'] == REDACTED
    assert 'server-returned-token' not in str(result)
    assert 'inline-secret-key' not in str(result)


def test_execute_openapi_operation_caps_large_response_payloads(monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)

    result = execute_openapi_operation(
        definition=OPERATION_DEFINITION,
        selected_definition_url='https://api.example.test/swagger.json',
        method='GET',
        path='/huge',
        parameters={},
        api_key='test-key',
        api_key_header_name='x-api-key',
    )

    assert result['status'] == 'ok'
    assert result['response_truncated'] is True
    assert result['response_json'] is None
    assert len(result['response_body_preview']) <= 4000
    assert result['response_capture_limit_bytes'] == 200_000


def test_api_configuration_boundary_states_are_non_secret(app_with_sqlite):
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AppSetting
    from app.services.secure_storage import text_secret_is_encrypted

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        token = login.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        saved = client.patch(
            '/api/api-configuration',
            headers=headers,
            json={
                'vendor_name': 'Alleva API',
                'api_base_url': 'https://api.example.test',
                'openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
                'api_key': 'super-secret-api-key',
                'api_enabled': True,
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body['api_key_configured'] is True
        assert 'super-secret-api-key' not in saved.text

        config = client.get('/api/api-configuration', headers=headers)
        assert config.status_code == 200
        assert config.json()['api_key_configured'] is True
        assert config.json()['openapi_url'] == 'https://api.example.test/swagger/v1/swagger.json'
        assert 'super-secret-api-key' not in config.text

        sample = client.get('/api/api-configuration/sample-openapi.json')
        assert sample.status_code == 200
        assert 'securitySchemes' in sample.text
        assert 'super-secret-api-key' not in sample.text

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert text_secret_is_encrypted(settings_row.api_client_secret)
    finally:
        db.close()


def test_api_configuration_routes_redact_inline_and_saved_keys(app_with_sqlite, monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AuditLog

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        saved = client.patch(
            '/api/api-configuration',
            headers=headers,
            json={'vendor_name': 'Mock API', 'api_base_url': 'https://api.example.test', 'api_key': 'saved-secret-api-key'},
        )
        assert saved.status_code == 200

        pull = client.post(
            '/api/api-configuration/pull-definitions',
            headers=headers,
            json={
                'swagger_ui_url': 'https://api.example.test/swagger/index.html',
                'api_base_url': 'https://api.example.test',
                'use_saved_api_key': True,
                'timeout_seconds': 5,
            },
        )
        assert pull.status_code == 200
        assert pull.json()['status'] == 'ok'
        assert pull.json()['report']['request']['api_key'] == REDACTED
        assert Path(pull.json()['report_path']).exists()
        assert 'saved-secret-api-key' not in pull.text

        operation = client.post(
            '/api/api-configuration/test-operation',
            headers=headers,
            json={
                'definition': OPERATION_DEFINITION,
                'selected_definition_url': 'https://api.example.test/swagger.json',
                'api_base_url': 'https://api.example.test',
                'method': 'GET',
                'path': '/patients/{patient_id}',
                'parameters': {'patient_id': 'PAT-SECRET', 'include_documents': False},
                'api_key': 'inline-secret-key',
                'use_saved_api_key': False,
                'timeout_seconds': 5,
            },
        )
        assert operation.status_code == 200
        payload = operation.json()
        assert payload['response_json']['access_token'] == REDACTED
        assert payload['report']['request']['api_key'] == REDACTED
        assert Path(payload['report_path']).exists()
        assert 'inline-secret-key' not in operation.text
        assert 'server-returned-token' not in operation.text

    db = session_local()
    try:
        logs = db.execute(select(AuditLog).where(AuditLog.action.in_(['api_configuration.pull_definitions', 'api_configuration.test_operation']))).scalars().all()
        serialized = ' '.join(f'{log.message} {log.details}' for log in logs)
        assert 'saved-secret-api-key' not in serialized
        assert 'inline-secret-key' not in serialized
        assert 'server-returned-token' not in serialized
    finally:
        db.close()


def test_api_configuration_routes_support_saved_client_credentials_without_exposing_token(app_with_sqlite, monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AuditLog

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        saved = client.patch(
            '/api/api-configuration',
            headers=headers,
            json={
                'vendor_name': 'Mock API',
                'api_base_url': 'https://api.example.test',
                'client_id': 'saved-client',
                'client_secret': 'saved-secret',
                'token_url': 'https://authorization.example.test/connect/token',
            },
        )
        assert saved.status_code == 200
        assert saved.json()['client_id_configured'] is True
        assert saved.json()['client_secret_configured'] is True
        assert 'saved-secret' not in saved.text

        pull = client.post(
            '/api/api-configuration/pull-definitions',
            headers=headers,
            json={
                'swagger_ui_url': 'https://api.example.test/swagger/index.html',
                'api_base_url': 'https://api.example.test',
                'auth_mode': 'client_credentials',
                'use_saved_client_credentials': True,
                'timeout_seconds': 5,
            },
        )
        assert pull.status_code == 200
        payload = pull.json()
        assert payload['status'] == 'ok'
        assert payload['auth_mode'] == 'client_credentials'
        assert payload['token_result']['status'] == 'ok'
        assert payload['bearer_token_used'] is True
        assert payload['report']['request']['client_secret'] == REDACTED
        assert payload['report']['request']['bearer_token'] == REDACTED
        assert 'saved-secret' not in pull.text
        assert 'mock-access-token' not in pull.text

    db = session_local()
    try:
        logs = db.execute(select(AuditLog).where(AuditLog.action == 'api_configuration.pull_definitions')).scalars().all()
        serialized = ' '.join(f'{log.message} {log.details}' for log in logs)
        assert 'saved-secret' not in serialized
        assert 'mock-access-token' not in serialized
        assert 'client_credentials' in serialized
    finally:
        db.close()


def test_app_settings_save_reload_preserves_oauth_secret_and_harness_uses_oauth(app_with_sqlite):
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AppSetting
    from app.services.secure_storage import decrypt_text_secret

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}

        saved = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_api_base_url': 'https://api.example.test',
                'alleva_openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
                'api_oauth_token_url': 'https://authorization.example.test/connect/token',
                'api_token_auth_style': 'body',
                'api_client_id': 'persisted-client',
                'api_client_secret': 'persisted-secret',
                'emr_periodic_check_enabled': True,
                'emr_periodic_check_interval_minutes': 60,
            },
        )
        assert saved.status_code == 200
        assert saved.json()['api_client_secret_configured'] is True

        reloaded = client.get('/api/settings', headers=headers)
        assert reloaded.status_code == 200
        assert reloaded.json()['api_client_id'] == 'persisted-client'
        assert reloaded.json()['api_client_secret_configured'] is True

        second_save_without_secret = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'organization_name': 'R3 Recovery Services',
                'api_client_id': 'persisted-client',
                'api_oauth_token_url': 'https://authorization.example.test/connect/token',
                'emr_periodic_check_enabled': True,
                'emr_periodic_check_interval_minutes': 120,
            },
        )
        assert second_save_without_secret.status_code == 200
        assert second_save_without_secret.json()['api_client_secret_configured'] is True
        assert second_save_without_secret.json()['emr_periodic_check_interval_minutes'] == 120

        harness_config = client.get('/api/api-configuration', headers=headers)
        assert harness_config.status_code == 200
        assert harness_config.json()['client_id'] == 'persisted-client'
        assert harness_config.json()['client_secret_configured'] is True
        assert harness_config.json()['recommended_auth_mode'] == 'client_credentials'

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert decrypt_text_secret(settings_row.api_client_secret) == 'persisted-secret'
        assert settings_row.emr_periodic_check_interval_minutes == 120
    finally:
        db.close()


def test_api_configuration_alleva_quick_pull_computes_summaries_without_logging_rows(app_with_sqlite, monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)
    monkeypatch.setattr('app.api.api_config_routes.httpx.Client', MockedHttpxClient)
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AuditLog

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        saved = client.patch(
            '/api/api-configuration',
            headers=headers,
            json={
                'vendor_name': 'Mock Alleva API',
                'api_base_url': 'https://api.example.test',
                'client_id': 'saved-client',
                'client_secret': 'saved-secret',
                'token_url': 'https://authorization.example.test/connect/token',
                'token_auth_style': 'body',
            },
        )
        assert saved.status_code == 200

        base_body = {
            'swagger_ui_url': 'https://api.example.test/swagger/index.html',
            'api_base_url': 'https://api.example.test',
            'openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
            'auth_mode': 'client_credentials',
            'use_saved_client_credentials': True,
            'timeout_seconds': 5,
            'max_pages': 2,
            'operation_parameters': {'Limit': 500, 'Cursor': 0, 'api-version': '1.0', 'X-Version': '1.0'},
        }
        all_patients = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body, 'report': 'all_patient_records'})
        assert all_patients.status_code == 200
        all_payload = all_patients.json()
        assert all_payload['status'] == 'ok'
        assert all_payload['source_operation'] == 'GET /clients'
        assert all_payload['returned_count'] == 2
        assert all_payload['columns'][:4] == ['patient_id', 'source_id', 'client_name', 'admission_date']
        assert all_payload['rows'][0]['client_name'] == 'Synthetic Active Client'
        assert all_payload['tsv'].splitlines()[0].startswith('patient_id\tsource_id\tclient_name\tadmission_date')
        assert 'PAT-ACTIVE-001\t201\tSynthetic Active Client\t2026-02-03' in all_payload['tsv']

        active = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body, 'report': 'active_treatment_plans'})
        assert active.status_code == 200
        assert active.json()['returned_count'] == 2
        assert {row['patient_id'] for row in active.json()['rows']} == {'PAT-ACTIVE-001', 'PAT-OVERDUE-001'}

        overdue = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body, 'report': 'overdue_treatment_plans'})
        assert overdue.status_code == 200
        assert overdue.json()['returned_count'] == 1
        assert overdue.json()['rows'][0]['patient_id'] == 'PAT-OVERDUE-001'
        assert 'before' in overdue.json()['rows'][0]['why']

        inactive = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body, 'report': 'inactive_treatment_plans'})
        assert inactive.status_code == 200
        assert inactive.json()['returned_count'] == 1
        assert inactive.json()['rows'][0]['patient_id'] == 'PAT-INACTIVE-001'

        patients = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body, 'report': 'active_patients'})
        assert patients.status_code == 200
        assert patients.json()['returned_count'] == 1
        assert patients.json()['rows'][0]['patient_id'] == 'PAT-ACTIVE-001'
        assert patients.json()['rows'][0]['first_admitted'] == '2026-02-03'

    db = session_local()
    try:
        logs = db.execute(select(AuditLog).where(AuditLog.action == 'api_configuration.alleva_quick_pull')).scalars().all()
        serialized = ' '.join(f'{log.message} {log.details}' for log in logs)
        assert 'PAT-ACTIVE-001' not in serialized
        assert 'PAT-OVERDUE-001' not in serialized
        assert 'saved-secret' not in serialized
    finally:
        db.close()


def test_review_source_daily_check_runs_saved_periodic_api_check(app_with_sqlite, monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AppSetting

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        saved = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_api_base_url': 'https://api.example.test',
                'alleva_openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
                'api_client_id': 'saved-client',
                'api_client_secret': 'saved-secret',
                'api_oauth_token_url': 'https://authorization.example.test/connect/token',
                'api_token_auth_style': 'all',
                'emr_periodic_check_enabled': True,
                'emr_periodic_check_interval_minutes': 60,
            },
        )
        assert saved.status_code == 200
        assert saved.json()['emr_periodic_check_enabled'] is True
        assert 'saved-secret' not in saved.text

        checked = client.post('/api/review-source-discovery/run-daily-check', headers=headers)
        assert checked.status_code == 200
        payload = checked.json()
        assert payload['last_check_mode'] == 'manual_api_readiness_check'
        assert payload['daily_monitoring_enabled'] is True
        assert payload['last_successful_check_at']
        assert 'saved-secret' not in checked.text
        assert 'mock-access-token' not in checked.text

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert settings_row.emr_last_check_status == 'ok'
        assert settings_row.emr_last_successful_check_at is not None
    finally:
        db.close()


def test_review_source_daily_check_uses_saved_settings_when_scheduler_is_off(app_with_sqlite, monkeypatch):
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', MockedHttpxClient)
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AppSetting

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        saved = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_api_base_url': 'https://api.example.test',
                'alleva_openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
                'api_client_id': 'saved-client',
                'api_client_secret': 'saved-secret',
                'api_oauth_token_url': 'https://authorization.example.test/connect/token',
                'api_token_auth_style': 'all',
                'emr_periodic_check_enabled': False,
            },
        )
        assert saved.status_code == 200
        assert saved.json()['emr_periodic_check_enabled'] is False

        checked = client.post('/api/review-source-discovery/run-daily-check', headers=headers)
        assert checked.status_code == 200
        payload = checked.json()
        assert payload['last_check_mode'] == 'manual_api_readiness_check'
        assert payload['daily_monitoring_enabled'] is False
        assert payload['api_mode_label'] == 'Manual readiness check succeeded'
        assert 'active App settings connection' in payload['plain_english_status']
        assert 'saved-secret' not in checked.text
        assert 'mock-access-token' not in checked.text

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert settings_row.emr_last_check_status == 'ok'
        assert settings_row.emr_last_successful_check_at is not None
    finally:
        db.close()
