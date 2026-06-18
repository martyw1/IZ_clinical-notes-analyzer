from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import REPO_ROOT
from app.models.models import AppSetting, AuditLog, EmrEndpointProfile
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


def test_review_source_discovery_provides_mock_api_queue_without_live_import(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.get('/api/review-source-discovery', headers=_auth_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert payload['checklist_id'] == 'treatment-plan-v1'
    assert payload['checklist_version'] == '1.2.0'
    assert payload['live_import_enabled'] is False
    assert payload['live_import_status'] == 'disabled_until_vendor_credentials_mapping_and_compliance_approval'
    assert payload['api_mode'] == 'mock_stub'
    assert payload['api_mode_label'] == 'Mock/stub mode'
    assert payload['refresh_mode'] == 'daily_mock_simulation'
    assert payload['next_refresh_at'] > payload['last_refresh_at']
    assert payload['manual_review_cadence'] == 'monthly_compliance_check'
    assert 'monthly compliance-check' in payload['manual_mode_message']
    assert payload['notification_badge_count'] >= payload['changed_item_count']
    assert any(item['source_type'] == 'api' and item['patient_id'].startswith('SYNTH-') for item in payload['items'])
    assert 'Ready for Review' in payload['status_counts']


def test_daily_review_source_check_is_safe_and_audited(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.post('/api/review-source-discovery/run-daily-check', headers=_auth_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert payload['live_import_enabled'] is False
    assert payload['last_successful_check_at']
    assert payload['last_check_mode'] == 'manual_safe_mock_check'

    db = session_local()
    try:
        audit = db.execute(select(AuditLog).where(AuditLog.action == 'review_source.daily_check.run')).scalar_one()
        assert audit.outcome_status == 'success'
        assert 'live_import_enabled' in audit.details
    finally:
        db.close()


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
        missing_detail = missing.json()['detail']
        assert 'Missing required EMR API field(s)' in missing_detail
        assert 'FHIR base URL' in missing_detail
        assert 'OAuth/FHIR client ID' in missing_detail

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


def test_alleva_rest_treatment_plan_sync_does_not_require_fhir_base_url(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)
        response = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_api_base_url': 'https://api.allevasoft.com',
                'alleva_openapi_url': 'https://api.allevasoft.com/swagger/v1/swagger.json',
                'alleva_api_version': '1.0',
                'emr_smart_token_url': 'https://authorization.allevasoft.com/connect/token',
                'emr_smart_client_id': 'alleva-rest-client',
                'emr_smart_client_secret': 'alleva-rest-secret',
                'alleva_treatment_plan_sync_enabled': True,
                'alleva_treatment_plan_sync_on_startup': True,
                'alleva_treatment_plan_sync_approved': True,
                'alleva_treatment_plan_endpoint_mapping_validated': True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload['emr_fhir_base_url'] == ''
        assert payload['alleva_treatment_plan_sync_enabled'] is True
        assert payload['alleva_treatment_plan_sync_on_startup'] is True

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
        assert settings_row.emr_fhir_base_url == ''
        assert settings_row.alleva_api_base_url == 'https://api.allevasoft.com'
        assert text_secret_is_encrypted(settings_row.emr_smart_client_secret)
    finally:
        db.close()


def test_alleva_rest_sync_enablement_lists_missing_approval_and_mapping(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)
        response = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_treatment_plan_sync_enabled': True,
                'alleva_treatment_plan_sync_on_startup': True,
            },
        )
        assert response.status_code == 400
        detail = response.json()['detail']
        assert 'R3/Alleva live treatment-plan sync approval' in detail
        assert 'validated Alleva treatment-plan endpoint mapping' in detail
        assert 'Alleva API client secret' in detail
        assert 'FHIR base URL' not in detail


def test_admin_can_store_and_activate_multiple_emr_endpoint_profiles(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        listed = client.get('/api/emr/profiles', headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]['profile_key'] == 'alleva-default'
        assert listed.json()[0]['client_secret_configured'] is False

        created = client.post(
            '/api/emr/profiles',
            headers=headers,
            json={
                'profile_key': 'future_emr_sandbox',
                'display_name': 'Future EMR sandbox',
                'vendor_name': 'Future EMR',
                'adapter_key': 'future-fhir-document-manager',
                'fhir_base_url': 'https://future.example.test/fhir/R4',
                'openapi_url': 'https://future.example.test/openapi.json',
                'token_url': 'https://future.example.test/oauth/token',
                'token_auth_style': 'basic',
                'client_id': 'future-client',
                'client_secret': 'future-secret',
                'scopes': 'patient/Patient.rs patient/DocumentReference.rs patient/Binary.rs',
                'timeout_seconds': 12,
                'is_default': False,
                'notes': 'Synthetic future endpoint profile.',
            },
        )
        assert created.status_code == 200
        profile = created.json()
        assert profile['client_secret_configured'] is True
        assert 'future-secret' not in created.text

        activated = client.post(f"/api/emr/profiles/{profile['id']}/activate", headers=headers)
        assert activated.status_code == 200
        payload = activated.json()
        assert payload['emr_vendor_name'] == 'Future EMR'
        assert payload['emr_fhir_base_url'] == 'https://future.example.test/fhir/R4'
        assert payload['emr_smart_client_id'] == 'future-client'
        assert payload['emr_smart_client_secret_configured'] is True
        assert 'future-secret' not in activated.text

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert settings_row.emr_vendor_name == 'Future EMR'
        assert text_secret_is_encrypted(settings_row.emr_smart_client_secret)
        stored_profile = db.execute(select(EmrEndpointProfile).where(EmrEndpointProfile.profile_key == 'future_emr_sandbox')).scalar_one()
        assert stored_profile.is_default is True
        assert text_secret_is_encrypted(stored_profile.client_secret)
    finally:
        db.close()


def test_version_endpoint_reports_repo_version(app_with_sqlite):
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get('/api/version')
        assert response.status_code == 200
        payload = response.json()
        assert payload['version'] == (REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        assert payload['environment']
        assert payload['git_commit']
