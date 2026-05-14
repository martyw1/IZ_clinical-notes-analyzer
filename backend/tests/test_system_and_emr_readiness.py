from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.models import AppSetting
from app.services.emr_fhir import map_document_reference_to_patient_note_metadata
from app.services.secure_storage import text_secret_is_encrypted

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_admin_can_view_runtime_readiness(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.get('/api/system/readiness', headers=_auth_headers(client))
        assert response.status_code == 200
        payload = response.json()
        assert payload['status'] in {'ok', 'warn'}
        assert any(check['name'] == 'data_encryption_key' for check in payload['checks'])


def test_emr_profile_and_import_plan_are_fhir_r4_oriented(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)
        db = session_local()
        try:
            settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
            settings_row.emr_fhir_base_url = 'https://ehr.example.test/fhir/R4'
            settings_row.emr_smart_client_id = 'client-id'
            db.commit()
        finally:
            db.close()

        profile = client.get('/api/emr/profile', headers=headers)
        assert profile.status_code == 200
        assert 'DocumentReference' in profile.json()['supported_resources']
        assert profile.json()['adapter_key'] == 'alleva-smart-fhir-document-manager'
        assert 'PDF' in profile.json()['supported_export_formats']
        assert any(section['key'] == 'custom_forms' for section in profile.json()['document_manager_sections'])
        assert profile.json()['client_id_configured'] is True

        plan = client.get('/api/emr/import-plan?patient_id=PAT-200', headers=headers)
        assert plan.status_code == 200
        payload = plan.json()
        assert payload['patient_id'] == 'PAT-200'
        assert payload['planned_requests'][0]['url'].endswith('/Patient?identifier=PAT-200')
        assert 'DocumentReference' in payload['planned_requests'][1]['url']
        assert 'PatientNoteDocument.alleva_bucket' in payload['document_mapping']
        assert 'Binary.contentType' in payload['attachment_handling']


def test_alleva_document_reference_mapping_preserves_source_traceability():
    mapped = map_document_reference_to_patient_note_metadata(
        {
            'resourceType': 'DocumentReference',
            'id': 'docref-123',
            'date': '2026-04-28T15:30:00Z',
            'description': 'Client Rights completed custom form',
            'type': {'text': 'Client Rights Form'},
            'content': [
                {
                    'attachment': {
                        'title': 'Client Rights.pdf',
                        'contentType': 'application/pdf',
                        'url': 'Binary/bin-123',
                    }
                }
            ],
        }
    )
    assert mapped['alleva_bucket'] == 'custom_forms'
    assert mapped['document_label'] == 'Client Rights.pdf'
    assert mapped['document_date'] == '2026-04-28'
    assert mapped['source_document_reference_id'] == 'docref-123'
    assert mapped['source_attachment_url'] == 'Binary/bin-123'


def test_emr_enablement_requires_minimum_alleva_smart_contract(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)
        missing = client.patch('/api/settings', headers=headers, json={'emr_api_enabled': True})
        assert missing.status_code == 400
        assert 'FHIR base URL is required' in missing.json()['detail']

        response = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'emr_api_enabled': True,
                'emr_fhir_base_url': 'https://alleva.example.test/fhir/R4/',
                'emr_smart_client_id': 'alleva-client',
                'emr_smart_client_secret': 'vendor-secret-value',
                'emr_smart_scopes': 'openid fhirUser launch/patient patient/Patient.rs patient/DocumentReference.rs patient/Binary.rs',
            },
        )
        assert response.status_code == 200
        assert response.json()['emr_smart_client_secret_configured'] is True

        db = session_local()
        try:
            settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
            assert settings_row.emr_fhir_base_url == 'https://alleva.example.test/fhir/R4'
            assert text_secret_is_encrypted(settings_row.emr_smart_client_secret)
        finally:
            db.close()


def test_version_endpoint_reports_repo_version(app_with_sqlite):
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get('/api/version')
        assert response.status_code == 200
        payload = response.json()
        assert payload['version'] == '0.4.0'
        assert payload['environment']
        assert payload['git_commit']
