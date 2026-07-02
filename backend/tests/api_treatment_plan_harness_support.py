import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

OriginalHttpxClient = httpx.Client


class TreatmentPlanHarnessHttpxClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._client = OriginalHttpxClient(transport=httpx.MockTransport(self._handler), follow_redirects=True)

    def __enter__(self) -> httpx.Client:
        return self._client

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._client.close()

    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == 'https://authorization.example.test/connect/token':
            return httpx.Response(200, json={'access_token': 'mock-access-token', 'token_type': 'Bearer', 'expires_in': 3600})
        if url.startswith('https://api.example.test/treatment-plans?'):
            assert request.headers.get('authorization') == 'Bearer mock-access-token'
            assert 'Limit=100' in url
            assert 'StartDate=2000-01-01T16%3A03' in url
            return httpx.Response(200, json=_synthetic_treatment_plans())
        return httpx.Response(404, text='not found')


class ApiKeyTreatmentPlanHarnessHttpxClient(TreatmentPlanHarnessHttpxClient):
    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == 'https://authorization.example.test/connect/token':
            raise AssertionError('API key treatment-plan harness path should not request OAuth tokens')
        if url.startswith('https://api.example.test/treatment-plans?'):
            assert request.headers.get('x-api-key') == 'saved-api-key-secret'
            return httpx.Response(200, json=[_api_key_treatment_plan()])
        return httpx.Response(404, text='not found')


class PatientCenteredTreatmentPlanHarnessHttpxClient(TreatmentPlanHarnessHttpxClient):
    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if url == 'https://authorization.example.test/connect/token':
            return httpx.Response(200, json={'access_token': 'mock-access-token', 'token_type': 'Bearer', 'expires_in': 3600})
        if parsed.scheme == 'https' and parsed.netloc == 'api.example.test' and parsed.path == '/clients':
            assert request.headers.get('authorization') == 'Bearer mock-access-token'
            return httpx.Response(200, json=_patient_centered_clients())
        if parsed.scheme == 'https' and parsed.netloc == 'api.example.test' and parsed.path == '/clients/307':
            assert request.headers.get('authorization') == 'Bearer mock-access-token'
            return httpx.Response(200, json=_patient_centered_clients()[0])
        if parsed.scheme == 'https' and parsed.netloc == 'api.example.test' and parsed.path == '/treatment-plans':
            assert request.headers.get('authorization') == 'Bearer mock-access-token'
            assert 'ClientId' in query
            assert 'clientId' not in query
            return httpx.Response(200, json=_patient_centered_plans(query['ClientId'][0]))
        return httpx.Response(404, text='not found')


class LargeTreatmentPlanHarnessHttpxClient(TreatmentPlanHarnessHttpxClient):
    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == 'https://authorization.example.test/connect/token':
            return httpx.Response(200, json={'access_token': 'mock-access-token', 'token_type': 'Bearer', 'expires_in': 3600})
        if url.startswith('https://api.example.test/treatment-plans?'):
            records = [_large_treatment_plan_record(index) for index in range(260)]
            return httpx.Response(200, content=json.dumps(records).encode('utf-8'), headers={'content-type': 'application/json'})
        return httpx.Response(404, text='not found')


class ErrorTreatmentPlanHarnessHttpxClient(TreatmentPlanHarnessHttpxClient):
    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == 'https://authorization.example.test/connect/token':
            return httpx.Response(200, json={'access_token': 'mock-access-token', 'token_type': 'Bearer', 'expires_in': 3600})
        if url.startswith('https://api.example.test/treatment-plans?'):
            return httpx.Response(500, text='Alice Smith upstream treatment plan error narrative')
        return httpx.Response(404, text='not found')


class NetworkErrorTreatmentPlanHarnessHttpxClient(TreatmentPlanHarnessHttpxClient):
    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == 'https://authorization.example.test/connect/token':
            return httpx.Response(200, json={'access_token': 'mock-access-token', 'token_type': 'Bearer', 'expires_in': 3600})
        if url.startswith('https://api.example.test/treatment-plans?'):
            raise httpx.ConnectError('synthetic treatment-plan connection failure', request=request)
        return httpx.Response(404, text='not found')


def saved_client_credentials_headers(client: Any) -> dict[str, str]:
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
    return headers


def base_body() -> dict[str, Any]:
    return {
        'swagger_ui_url': 'https://api.example.test/swagger/index.html',
        'api_base_url': 'https://api.example.test',
        'openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
        'auth_mode': 'client_credentials',
        'use_saved_client_credentials': True,
        'timeout_seconds': 5,
        'max_pages': 1,
        'operation_parameters': {'Limit': 100, 'Cursor': 0, 'StartDate': '2000-01-01T16:03', 'api-version': '1.0', 'X-Version': '1.0'},
    }


def api_key_body() -> dict[str, Any]:
    body = base_body()
    body.update({'auth_mode': 'api_key', 'use_saved_client_credentials': False, 'use_saved_api_key': True})
    return body


def patch_outbound_httpx(monkeypatch: Any, client_class: type[Any]) -> None:
    monkeypatch.setattr('app.services.api_connectivity.httpx.Client', client_class)
    monkeypatch.setattr('app.api.api_config_routes.httpx.Client', client_class)
    monkeypatch.setattr('app.services.alleva_treatment_plan_harness_streaming.httpx.Client', client_class)


def _synthetic_treatment_plans() -> list[dict[str, Any]]:
    return [
        {
            'id': 'tp-101',
            'client': {'href': '/clients/PAT-HREF-001', 'id': 'source-client-001'},
            'description': 'Synthetic treatment plan content',
            'startDate': '2026-01-01T00:00:00',
            'endDate': '2099-12-31T00:00:00',
            'isActive': True,
            'isComplete': True,
            'isInitialTP': False,
            'isWiley': True,
            'reasonForAdmission': 'Synthetic reason',
            'initialClientNeeds': 'Synthetic need',
            'familyEducationNeeds': 'Synthetic family education',
            'problems': [
                {
                    'description': 'synthetic substance use problem',
                    'behavioralDefinitions': [{'description': 'synthetic cravings and isolation pattern'}],
                    'goals': [{'description': 'sustain recovery goals', 'objectives': [{'description': 'complete weekly objectives', 'interventions': [{'description': 'Synthetic intervention'}]}]}],
                }
            ],
        },
        {'id': 'tp-102', 'client': {'href': '/clients/PAT-OTHER-002', 'id': 'source-client-002'}, 'description': 'Other synthetic treatment plan content', 'startDate': '2026-02-01T00:00:00', 'isActive': True},
    ]


def _patient_centered_clients() -> list[dict[str, Any]]:
    return [
        {
            'id': 307,
            'clientId': 'legacy-client-307',
            'chartId': 'CHART-307',
            'externalId': 'EXT-307',
            'mrn': 'MRN-307',
            'status': {'id': 1049, 'name': 'Active'},
            'admissionDate': '2026-01-02',
            'dischargeDate': '2026-08-01',
            'levelOfCare': 'IOP',
            'facilityName': 'Synthetic Facility',
            'primaryClinician': 'Synthetic Counselor',
            'firstContactDate': '2025-12-20',
        },
        {
            'id': 308,
            'clientId': 'legacy-client-308',
            'status': {'id': 1356, 'name': 'Discharged'},
            'admissionDate': '2025-01-02',
        },
        {
            'id': 309,
            'clientId': 'legacy-client-309',
            'status': 'InActive',
            'admissionDate': '2025-02-02',
        },
    ]


def _patient_centered_plans(patient_id: str) -> list[dict[str, Any]]:
    if patient_id != '307':
        return []
    return [
        {
            'id': 10,
            'client': '/clients/307',
            'startDate': '2026-01-02T00:00:00',
            'endDate': '2099-12-31T00:00:00',
            'createdDate': '2026-01-02T01:00:00',
            'lastModified': '2026-01-03T00:00:00',
            'isActive': True,
            'isComplete': True,
            'isInitialTP': True,
            'isWiley': False,
            'reasonForAdmission': 'Synthetic reason',
            'initialClientNeeds': 'Synthetic need',
            'familyEducationNeeds': 'Synthetic family education',
            'problems': [
                {
                    'diagnoses': [{'code': 'F10.20', 'status': 'Active'}],
                    'behavioralDefinitions': [{'description': 'synthetic behavioral definition'}],
                    'goals': [{'description': 'synthetic goal', 'objectives': [{'description': 'synthetic objective', 'interventions': [{'description': 'Synthetic intervention'}]}]}],
                }
            ],
        },
        {
            'id': 12,
            'client': '/clients/307',
            'startDate': '2026-02-02T00:00:00',
            'endDate': '2000-01-01T00:00:00',
            'createdDate': '2026-02-02T01:00:00',
            'isActive': True,
            'isComplete': False,
            'isInitialTP': False,
            'problems': [],
        },
        {
            'id': 20,
            'client': '/clients/307',
            'startDate': '2026-03-02T00:00:00',
            'isActive': False,
            'isComplete': True,
            'isInitialTP': False,
        },
    ]


def _api_key_treatment_plan() -> dict[str, Any]:
    return {
        'id': 'tp-api-key-001',
        'client': {'href': '/clients/API-KEY-PATIENT'},
        'description': 'API key synthetic treatment narrative',
        'reasonForAdmission': 'API key synthetic admission reason',
        'startDate': '2026-03-01T00:00:00',
        'isActive': True,
    }


def _large_treatment_plan_record(index: int) -> dict[str, Any]:
    return {
        'id': f'tp-{index}',
        'client': {'href': f'/clients/PAT-{index:03d}'},
        'description': f'KEEP-FULL-BODY-MARKER-{index} ' + ('x' * 1200),
        'startDate': '2026-01-01T00:00:00',
        'isActive': True,
        'problems': [{'goals': [{'objectives': [{'interventions': [{'description': 'Synthetic'}]}]}]}],
    }
