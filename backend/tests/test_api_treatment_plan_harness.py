from pathlib import Path
from urllib.parse import parse_qs, urlparse

from api_treatment_plan_harness_support import (
    TreatmentPlanHarnessHttpxClient,
    base_body,
    patch_outbound_httpx,
    saved_client_credentials_headers,
)


def test_api_configuration_treatment_plan_harness_saves_all_response_metadata(app_with_sqlite, monkeypatch):
    # Given: saved OAuth settings and a synthetic Alleva /treatment-plans response.
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AuditLog

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, TreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the admin runs the all-treatment-plans harness pull.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'all_treatment_plans'})

        # Then: metadata and saved paths appear without leaking treatment narrative or credentials.
        assert pulled.status_code == 200
        payload = pulled.json()
        parsed_url = urlparse(payload['url'])
        query = parse_qs(parsed_url.query)
        assert payload['status'] == 'ok'
        assert payload['source_operation'] == 'GET /treatment-plans'
        assert parsed_url.path.endswith('/treatment-plans')
        assert query['Limit'] == ['100']
        assert query['StartDate'] == ['2000-01-01T16:03']
        assert payload['response_truncated'] is False
        assert payload['response_capture_limit_bytes'] > 0
        assert payload['response_json_parse_status'] == 'ok'
        assert Path(payload['response_body_file']).exists()
        assert Path(payload['report_path']).exists()
        assert payload['report']['report_type'] == 'alleva_all_treatment_plans'
        assert payload['report']['result']['report'] == 'all_treatment_plans'
        assert payload['returned_count'] == 2
        assert payload['rows'][0]['description_present'] is True
        assert 'description' not in payload['rows'][0]
        assert payload['response_json_preview']['total_records_seen'] == 2
        assert payload['response_json_preview']['preview_omitted_reason'].startswith('clinical treatment-plan content is omitted')
        body_text = Path(payload['response_body_file']).read_text(encoding='utf-8')
        report_text = Path(payload['report_path']).read_text(encoding='utf-8')
        assert 'Synthetic treatment plan content' in body_text
        for secret in ('Synthetic treatment plan content', 'Synthetic reason', 'Synthetic need', 'Synthetic intervention', 'saved-secret', 'mock-access-token'):
            assert secret not in pulled.text
            assert secret not in report_text

    db = session_local()
    try:
        logs = db.execute(select(AuditLog).where(AuditLog.action == 'api_configuration.alleva_quick_pull')).scalars().all()
        serialized = ' '.join(f'{log.message} {log.details}' for log in logs)
        for secret in ('Synthetic treatment plan content', 'Synthetic reason', 'Synthetic need', 'Synthetic intervention', 'saved-secret', 'mock-access-token'):
            assert secret not in serialized
    finally:
        db.close()


def test_api_configuration_treatment_plan_harness_filters_single_patient_by_client_href(app_with_sqlite, monkeypatch):
    # Given: /treatment-plans has no direct patient filter, but records include client hrefs.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, TreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the admin requests one patient/client ID.
        pulled = client.post(
            '/api/api-configuration/alleva-quick-pull',
            headers=headers,
            json={**base_body(), 'report': 'single_treatment_plan', 'patient_id': 'PAT-HREF-001'},
        )

        # Then: the harness documents client-side fallback filtering and returns only the href match.
        payload = pulled.json()
        assert pulled.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['direct_patient_filter_supported'] is False
        assert payload['filtering_mode'] == 'client_side_by_client_reference'
        assert 'client-side filtering' in payload['filtering_explanation']
        assert payload['total_records_seen'] == 2
        assert payload['returned_count'] == 1
        assert payload['rows'][0]['treatment_plan_id'] == 'tp-101'
        assert 'description' not in payload['rows'][0]
        assert payload['matched_client_references'] == ['/clients/PAT-HREF-001']
        report_text = Path(payload['report_path']).read_text(encoding='utf-8')
        assert 'Other synthetic treatment plan content' not in pulled.text
        assert 'Other synthetic treatment plan content' not in report_text


def test_api_configuration_treatment_plan_harness_requires_patient_id_for_single_pull(app_with_sqlite, monkeypatch):
    # Given: the single-patient report is requested without an identifier.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, TreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: no patient/client ID is provided.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'single_treatment_plan', 'patient_id': '   '})

        # Then: the backend guard fails clearly before calling /treatment-plans.
        payload = pulled.json()
        assert pulled.status_code == 200
        assert payload['status'] == 'fail'
        assert payload['category'] == 'missing_patient_id'
        assert 'Patient / Client ID' in payload['message']
