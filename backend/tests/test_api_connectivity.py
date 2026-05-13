import httpx

from app.services.api_connectivity import (
    candidate_definition_urls,
    extract_swagger_ui_definition_urls,
    pull_api_definitions,
)


class MockedHttpxClient:
    def __init__(self, *args, **kwargs):
        self._client = httpx.Client(transport=httpx.MockTransport(self._handler), follow_redirects=True)

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
        return httpx.Response(404, text='not found')


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
