import httpx

from app.services.api_connectivity import (
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
            assert request.headers.get('x-api-key') == 'test-key'
            assert request.headers.get('authorization') == 'Bearer test-key'
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
        if url == 'https://api.example.test/patients/PAT-001/notes':
            assert request.method == 'POST'
            assert request.headers.get('x-api-key') == 'test-key'
            return httpx.Response(201, json={'created': True, 'payload': {'accepted': True}})
        return httpx.Response(404, text='not found')


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


def test_api_configuration_boundary_states_are_non_secret(app_with_sqlite):
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

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
