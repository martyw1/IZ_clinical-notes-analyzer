import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import REPO_ROOT
from app.models.models import AppSetting, AuditLog, EmrEndpointProfile
from app.services.secure_storage import text_secret_is_encrypted

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'
OriginalHttpxClient = httpx.Client


class TreatmentReviewsUnauthorizedHttpxClient:
    def __init__(self, *args, **kwargs):
        self._client = OriginalHttpxClient(transport=httpx.MockTransport(self._handler), follow_redirects=True)

    def __enter__(self):
        return self._client

    def __exit__(self, exc_type, exc, tb):
        self._client.close()

    @staticmethod
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get('authorization') == 'Bearer synced-token'
        if request.url.path == '/clients':
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
                    }
                ],
            )
        if request.url.path == '/treatment-plans':
            return httpx.Response(
                200,
                json=[
                    {
                        'id': 301,
                        'client': {'clientId': 'PAT-ACTIVE-001'},
                        'isInitialTP': False,
                        'isComplete': True,
                        'startDate': '2026-04-02T00:00:00',
                        'staffSignatureDate': '2026-04-02',
                        'clientSignature': {'signatureDateTime': '2026-04-02T09:00:00'},
                    }
                ],
            )
        if request.url.path == '/treatment-reviews':
            return httpx.Response(401, json={'message': 'synthetic unauthorized'})
        return httpx.Response(404, text='not found')


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


def test_api_profile_is_rest_openapi_oriented_and_removed_routes_are_unreachable(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)
        db = session_local()
        try:
            settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
            settings_row.alleva_api_base_url = 'https://api.example.test'
            settings_row.alleva_openapi_url = 'https://api.example.test/openapi.json'
            settings_row.api_client_id = 'client-id'
            db.commit()
        finally:
            db.close()

        profile = client.get('/api/emr/profile', headers=headers)
        assert profile.status_code == 200
        assert profile.json()['api_base_url'] == 'https://api.example.test'
        assert profile.json()['openapi_url'] == 'https://api.example.test/openapi.json'
        assert profile.json()['adapter_key'] == 'alleva-rest-api'
        assert 'PDF' in profile.json()['supported_export_formats']
        assert any(section['key'] == 'custom_forms' for section in profile.json()['document_manager_sections'])
        assert profile.json()['client_id_configured'] is True

        discovery = client.post('/api/emr/discover', headers=headers, json={})
        assert discovery.status_code == 404
        plan = client.get('/api/emr/import-plan?patient_id=PAT-200', headers=headers)
        assert plan.status_code == 404


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
    assert payload['last_check_mode'] == 'manual_api_readiness_check'

    db = session_local()
    try:
        audit = db.execute(select(AuditLog).where(AuditLog.action == 'review_source.daily_check.run')).scalar_one()
        assert audit.outcome_status == 'success'
        assert 'live_import_enabled' in audit.details
    finally:
        db.close()


def test_api_enablement_uses_rest_credentials_without_legacy_endpoint_requirements(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)
        missing = client.patch('/api/settings', headers=headers, json={'emr_api_enabled': True})
        assert missing.status_code == 400
        missing_detail = missing.json()['detail']
        assert 'Missing required API setting(s)' in missing_detail
        assert 'Alleva REST API base URL' not in missing_detail
        assert 'OAuth token URL' not in missing_detail
        assert 'API client ID' in missing_detail
        assert 'API client secret' in missing_detail

        response = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'emr_api_enabled': True,
                'alleva_api_base_url': 'https://api.allevasoft.com',
                'alleva_openapi_url': 'https://api.allevasoft.com/swagger/v1/swagger.json',
                'api_oauth_token_url': 'https://authorization.allevasoft.com/connect/token',
                'api_client_id': 'alleva-client',
                'api_client_secret': 'vendor-secret-value',
            },
        )
        assert response.status_code == 200
        assert response.json()['api_client_secret_configured'] is True

        db = session_local()
        try:
            settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
            assert settings_row.alleva_api_base_url == 'https://api.allevasoft.com'
            assert text_secret_is_encrypted(settings_row.api_client_secret)
        finally:
            db.close()


def test_alleva_rest_treatment_plan_sync_uses_rest_settings(app_with_sqlite):
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
                'api_oauth_token_url': 'https://authorization.allevasoft.com/connect/token',
                'api_client_id': 'alleva-rest-client',
                'api_client_secret': 'alleva-rest-secret',
                'alleva_treatment_plan_sync_enabled': True,
                'alleva_treatment_plan_sync_on_startup': True,
                'alleva_treatment_plan_sync_approved': True,
                'alleva_treatment_plan_endpoint_mapping_validated': True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload['alleva_treatment_plan_sync_enabled'] is True
        assert payload['alleva_treatment_plan_sync_on_startup'] is True
        assert payload['api_client_id'] == 'alleva-rest-client'

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
        assert settings_row.alleva_api_base_url == 'https://api.allevasoft.com'
        assert text_secret_is_encrypted(settings_row.api_client_secret)
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


def test_manual_alleva_sync_warns_on_optional_treatment_reviews_unauthorized(app_with_sqlite, monkeypatch):
    monkeypatch.setattr(
        'app.services.alleva_treatment_plan_sync.request_client_credentials_token',
        lambda **_kwargs: ({'status': 'ok', 'message': 'Client-credentials token obtained.'}, 'synced-token'),
    )
    monkeypatch.setattr('app.services.alleva_treatment_plan_sync.httpx.Client', TreatmentReviewsUnauthorizedHttpxClient)
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        saved = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_api_base_url': 'https://api.example.test',
                'alleva_openapi_url': 'https://api.example.test/swagger/v1/swagger.json',
                'alleva_api_version': '1.0',
                'api_oauth_token_url': 'https://authorization.example.test/connect/token',
                'api_client_id': 'alleva-rest-client',
                'api_client_secret': 'alleva-rest-secret',
                'alleva_treatment_plan_sync_enabled': True,
                'alleva_treatment_plan_sync_approved': True,
                'alleva_treatment_plan_endpoint_mapping_validated': True,
            },
        )
        assert saved.status_code == 200

        response = client.post('/api/alleva/treatment-plan-sync/run', headers=headers)
        assert response.status_code == 200
        payload = response.json()
        result = payload['sync_result']
        assert result['status'] == 'warn'
        assert result['upserted_client_count'] == 1
        assert result['treatment_plan_count'] == 1
        assert result['treatment_review_count'] == 0
        assert result['optional_endpoint_failures'][0]['endpoint'] == '/treatment-reviews'
        assert result['optional_endpoint_failures'][0]['category'] == 'endpoint_authorization_failed'
        assert result['optional_endpoint_failures'][0]['status_code'] == 401
        assert 'Optional Alleva treatment-review endpoint /treatment-reviews could not be read' in result['message']
        assert 'HTTP 401 Unauthorized' in result['message']
        assert 'HTTPStatusError' not in result['message']

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert settings_row.alleva_treatment_plan_sync_last_status == 'warn'
        assert 'Optional Alleva treatment-review endpoint /treatment-reviews could not be read' in settings_row.alleva_treatment_plan_sync_last_message
        assert 'HTTPStatusError' not in settings_row.alleva_treatment_plan_sync_last_message
        from app.models.models import TreatmentPlanClient

        synced_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-ACTIVE-001')).scalar_one()
        assert synced_client.current_level_of_care == 'IOP'
        assert len(synced_client.treatment_plans) == 1
    finally:
        db.close()


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
                'display_name': 'Alleva REST sandbox',
                'vendor_name': 'Alleva REST API',
                'adapter_key': 'alleva-rest-api',
                'api_base_url': 'https://api.example.test',
                'openapi_url': 'https://api.example.test/openapi.json',
                'token_url': 'https://authorization.example.test/connect/token',
                'token_auth_style': 'basic',
                'client_id': 'future-client',
                'client_secret': 'future-secret',
                'timeout_seconds': 12,
                'is_default': False,
                'notes': 'Synthetic REST endpoint profile.',
            },
        )
        assert created.status_code == 200
        profile = created.json()
        assert profile['client_secret_configured'] is True
        assert 'future-secret' not in created.text

        activated = client.post(f"/api/emr/profiles/{profile['id']}/activate", headers=headers)
        assert activated.status_code == 200
        payload = activated.json()
        assert payload['emr_vendor_name'] == 'Alleva REST API'
        assert payload['alleva_api_base_url'] == 'https://api.example.test'
        assert payload['api_client_id'] == 'future-client'
        assert payload['api_client_secret_configured'] is True
        assert 'future-secret' not in activated.text

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting)).scalar_one()
        assert settings_row.emr_vendor_name == 'Alleva REST API'
        assert text_secret_is_encrypted(settings_row.api_client_secret)
        stored_profile = db.execute(select(EmrEndpointProfile).where(EmrEndpointProfile.profile_key == 'future_emr_sandbox')).scalar_one()
        assert stored_profile.is_default is True
        assert text_secret_is_encrypted(stored_profile.client_secret)
    finally:
        db.close()


def test_audit_logging_tolerates_detached_actor_after_commit(app_with_sqlite):
    app, session_local = app_with_sqlite
    from app.models.models import User
    from app.services.audit import log_event, set_actor_context

    with TestClient(app):
        pass

    db = session_local()
    try:
        user = db.execute(select(User).where(User.username == 'admin')).scalar_one()
        set_actor_context(user)
        db.commit()
    finally:
        db.close()

    log_event(
        action='audit.detached_actor.regression',
        actor=user,
        event_category='system',
        target_entity='audit_actor',
        target_entity_type='regression_test',
        message='Detached audit actor regression event.',
    )


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
