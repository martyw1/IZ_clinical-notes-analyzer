import httpx

from app.services.api_connectivity import (
    REDACTED,
    build_api_connectivity_report,
    candidate_definition_urls,
    execute_openapi_operation,
    extract_swagger_ui_definition_urls,
    extract_openapi_operations,
    pull_api_definitions,
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
        if url.endswith('/swagger/index.html'):
            return httpx.Response(200, text="SwaggerUIBundle({ url: '/swagger/v1/swagger.json' })")
        if url.endswith('/swagger/v1/swagger.json'):
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
    get_operation = next(item for item in operations if item['method'] == 'GET')
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
        assert 'super-secret-api-key' not in config.text

        sample = client.get('/api/api-configuration/sample-openapi.json')
        assert sample.status_code == 200
        assert 'securitySchemes' in sample.text
        assert 'super-secret-api-key' not in sample.text

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert text_secret_is_encrypted(settings_row.emr_smart_client_secret)
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
