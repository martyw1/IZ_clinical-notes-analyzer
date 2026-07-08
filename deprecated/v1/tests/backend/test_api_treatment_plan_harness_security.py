from pathlib import Path

from api_treatment_plan_harness_support import (
    ApiKeyTreatmentPlanHarnessHttpxClient,
    ErrorTreatmentPlanHarnessHttpxClient,
    LargeTreatmentPlanHarnessHttpxClient,
    NetworkErrorTreatmentPlanHarnessHttpxClient,
    api_key_body,
    base_body,
    patch_outbound_httpx,
    saved_client_credentials_headers,
)


def test_api_configuration_treatment_plan_harness_supports_api_key_without_secret_leak(app_with_sqlite, monkeypatch):
    # Given: saved API-key settings instead of OAuth client credentials.
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AuditLog

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, ApiKeyTreatmentPlanHarnessHttpxClient)
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3!@analyzer#123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        saved = client.patch('/api/api-configuration', headers=headers, json={'vendor_name': 'Mock Alleva API', 'api_base_url': 'https://api.example.test', 'api_key': 'saved-api-key-secret'})
        assert saved.status_code == 200

        # When: the treatment-plan harness uses the saved API key.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**api_key_body(), 'report': 'all_treatment_plans'})

        # Then: API-key auth works, treatment-plan fields are visible, and secrets stay out of screen/report/audit metadata.
        payload = pulled.json()
        report_text = Path(payload['report_path']).read_text(encoding='utf-8')
        assert pulled.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['api_key_used'] is True
        assert payload['bearer_token_used'] is False
        assert payload['report']['request']['api_key'] == '[redacted]'
        assert 'API key synthetic treatment narrative' in pulled.text
        assert 'API key synthetic admission reason' in pulled.text
        assert 'API key synthetic treatment narrative' in report_text
        assert 'API key synthetic admission reason' in report_text
        for secret in ('saved-api-key-secret',):
            assert secret not in pulled.text
            assert secret not in report_text

    db = session_local()
    try:
        logs = db.execute(select(AuditLog).where(AuditLog.action == 'api_configuration.alleva_quick_pull')).scalars().all()
        serialized = ' '.join(f'{log.message} {log.details}' for log in logs)
        for secret in ('saved-api-key-secret', 'API key synthetic treatment narrative', 'API key synthetic admission reason'):
            assert secret not in serialized
    finally:
        db.close()


def test_api_configuration_treatment_plan_harness_parses_large_full_body_from_file(app_with_sqlite, monkeypatch):
    # Given: Alleva returns a response larger than the UI preview capture limit.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, LargeTreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the all-treatment-plans harness pull runs.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'all_treatment_plans'})

        # Then: the preview is marked truncated, but the full file is parsed and structured plan fields remain visible in the response.
        payload = pulled.json()
        body_file = Path(payload['response_body_file'])
        assert pulled.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['response_truncated'] is True
        assert payload['response_json_parse_status'] == 'ok'
        assert payload['returned_count'] == 260
        assert 'KEEP-FULL-BODY-MARKER-259' in body_file.read_text(encoding='utf-8')
        assert 'KEEP-FULL-BODY-MARKER-259' in pulled.text
        assert 'KEEP-FULL-BODY-MARKER-259' not in Path(payload['report_path']).read_text(encoding='utf-8')


def test_api_configuration_treatment_plan_harness_omits_error_body_from_browser(app_with_sqlite, monkeypatch):
    # Given: Alleva returns an upstream error containing PHI-like text.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, ErrorTreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the treatment-plan harness pull receives the error.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'all_treatment_plans'})

        # Then: metadata and the saved body path remain visible, but upstream text is not echoed.
        payload = pulled.json()
        assert pulled.status_code == 200
        assert payload['status'] == 'fail'
        assert payload['status_code'] == 500
        assert Path(payload['response_body_file']).exists()
        assert payload['response_body_preview'] == '[saved to response_body_file; preview omitted for upstream non-success response]'
        assert 'Alice Smith' not in pulled.text
        assert 'upstream treatment plan error narrative' not in pulled.text


def test_api_configuration_treatment_plan_harness_reports_network_failure(app_with_sqlite, monkeypatch):
    # Given: the outbound treatment-plan request cannot connect.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, NetworkErrorTreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the treatment-plan harness pull hits a network exception.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'all_treatment_plans'})

        # Then: the exception is redacted into a metadata-only failure response.
        payload = pulled.json()
        assert pulled.status_code == 200
        assert payload['status'] == 'fail'
        assert payload['category'] == 'network_failure'
        assert payload['rows'] == []
        assert payload['returned_count'] == 0
