from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.models import AppSetting

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert login.status_code == 200
    if login.json().get('must_reset_password'):
        reset = client.post(
            '/api/auth/reset-password',
            json={'new_password': password},
            headers={'Authorization': f"Bearer {login.json()['access_token']}"},
        )
        assert reset.status_code == 200
        login = client.post('/api/auth/login', json={'username': username, 'password': password})
        assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_admin_can_create_update_and_reset_managed_users(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)

        listed = client.get('/api/users', headers=headers)
        assert listed.status_code == 200
        assert any(user['username'] == 'admin' for user in listed.json())

        created = client.post(
            '/api/users',
            headers=headers,
            json={
                'username': 'manager-01',
                'full_name': 'Office Manager',
                'password': 'temporary-pass-1234',
                'role': 'manager',
            },
        )
        assert created.status_code == 200
        created_user = created.json()
        assert created_user['username'] == 'manager-01'
        assert created_user['must_reset_password'] is True

        updated = client.patch(
            f"/api/users/{created_user['id']}",
            headers=headers,
            json={'full_name': 'Office Manager Updated', 'is_locked': True},
        )
        assert updated.status_code == 200
        assert updated.json()['full_name'] == 'Office Manager Updated'
        assert updated.json()['is_locked'] is True

        reset = client.post(
            f"/api/users/{created_user['id']}/reset-password",
            headers=headers,
            json={'new_password': 'replacement-pass-1234', 'require_reset_on_login': False},
        )
        assert reset.status_code == 200
        assert reset.json()['is_locked'] is False
        assert reset.json()['must_reset_password'] is False

        login = client.post('/api/auth/login', json={'username': 'manager-01', 'password': 'replacement-pass-1234'})
        assert login.status_code == 200
        assert login.json()['must_reset_password'] is False


def test_bootstrap_admin_cannot_be_demoted_or_reset(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        listed = client.get('/api/users', headers=headers)
        assert listed.status_code == 200
        admin_id = next(user['id'] for user in listed.json() if user['username'] == 'admin')

        blocked_update = client.patch(
            f'/api/users/{admin_id}',
            headers=headers,
            json={'role': 'manager'},
        )
        assert blocked_update.status_code == 400

        blocked_reset = client.post(
            f'/api/users/{admin_id}/reset-password',
            headers=headers,
            json={'new_password': 'replacement-pass-1234', 'require_reset_on_login': False},
        )
        assert blocked_reset.status_code == 400


def test_user_can_manage_own_profile_and_password(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        created = client.post(
            '/api/users',
            headers=admin_headers,
            json={
                'username': 'counselor-01',
                'full_name': 'Counselor One',
                'password': 'temporary-pass-1234',
                'role': 'counselor',
            },
        )
        assert created.status_code == 200

        login = client.post('/api/auth/login', json={'username': 'counselor-01', 'password': 'temporary-pass-1234'})
        assert login.status_code == 200
        token = login.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        updated = client.patch('/api/users/me', headers=headers, json={'full_name': 'Counselor One Updated'})
        assert updated.status_code == 200
        assert updated.json()['full_name'] == 'Counselor One Updated'

        changed = client.post(
            '/api/users/me/change-password',
            headers=headers,
            json={'current_password': 'temporary-pass-1234', 'new_password': 'replacement-pass-1234'},
        )
        assert changed.status_code == 200

        relogin = client.post('/api/auth/login', json={'username': 'counselor-01', 'password': 'replacement-pass-1234'})
        assert relogin.status_code == 200


def test_managed_roles_can_sign_in_and_access_allowed_endpoints(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        created = []
        for username, full_name, role in [
            ('counselor-02', 'Counselor Two', 'counselor'),
            ('manager-02', 'Office Manager Two', 'manager'),
        ]:
            response = client.post(
                '/api/users',
                headers=admin_headers,
                json={
                    'username': username,
                    'full_name': full_name,
                    'password': 'temporary-pass-1234',
                    'role': role,
                },
            )
            assert response.status_code == 200
            created.append(response.json())

        for user in created:
            headers = _login_headers(client, user['username'], 'temporary-pass-1234')

            me = client.get('/api/users/me', headers=headers)
            assert me.status_code == 200
            assert me.json()['username'] == user['username']

            charts = client.get('/api/charts', headers=headers)
            assert charts.status_code == 200
            assert charts.json() == []

            note_sets = client.get('/api/patient-note-sets', headers=headers)
            assert note_sets.status_code == 200
            assert note_sets.json() == []

            directory = client.get('/api/users', headers=headers)
            if user['role'] == 'manager':
                assert directory.status_code == 200
            else:
                assert directory.status_code == 403


def test_manager_can_manage_counselors_but_not_privileged_accounts(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        manager = client.post(
            '/api/users',
            headers=admin_headers,
            json={
                'username': 'manager-user-crud',
                'full_name': 'Manager User CRUD',
                'password': 'temporary-pass-1234',
                'role': 'manager',
            },
        )
        assert manager.status_code == 200
        manager_headers = _login_headers(client, 'manager-user-crud', 'temporary-pass-1234')

        created = client.post(
            '/api/users',
            headers=manager_headers,
            json={
                'username': 'managed-counselor-01',
                'full_name': 'Managed Counselor',
                'password': 'temporary-pass-1234',
                'role': 'counselor',
            },
        )
        assert created.status_code == 200
        counselor = created.json()

        blocked_admin_create = client.post(
            '/api/users',
            headers=manager_headers,
            json={
                'username': 'blocked-admin',
                'full_name': 'Blocked Admin',
                'password': 'temporary-pass-1234',
                'role': 'admin',
            },
        )
        assert blocked_admin_create.status_code == 403

        updated = client.patch(
            f"/api/users/{counselor['id']}",
            headers=manager_headers,
            json={'full_name': 'Managed Counselor Updated', 'is_locked': True},
        )
        assert updated.status_code == 200
        assert updated.json()['full_name'] == 'Managed Counselor Updated'
        assert updated.json()['is_locked'] is True

        blocked_promotion = client.patch(f"/api/users/{counselor['id']}", headers=manager_headers, json={'role': 'admin'})
        assert blocked_promotion.status_code == 403

        reset = client.post(
            f"/api/users/{counselor['id']}/reset-password",
            headers=manager_headers,
            json={'new_password': 'replacement-pass-1234', 'require_reset_on_login': False},
        )
        assert reset.status_code == 200
        assert reset.json()['is_locked'] is False

        blocked_manager_update = client.patch(f"/api/users/{manager.json()['id']}", headers=manager_headers, json={'full_name': 'Self Edit'})
        assert blocked_manager_update.status_code == 403

        deleted = client.delete(f"/api/users/{counselor['id']}", headers=manager_headers)
        assert deleted.status_code == 200
        assert deleted.json()['status'] == 'deleted'


def test_admin_can_delete_unused_managed_user(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post(
            '/api/users',
            headers=headers,
            json={
                'username': 'temp-user-01',
                'full_name': 'Temporary User',
                'password': 'temporary-pass-1234',
                'role': 'counselor',
            },
        )
        assert created.status_code == 200
        created_user = created.json()

        deleted = client.delete(f"/api/users/{created_user['id']}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()['status'] == 'deleted'

        listed = client.get('/api/users', headers=headers)
        assert listed.status_code == 200
        assert all(user['username'] != 'temp-user-01' for user in listed.json())

        login = client.post('/api/auth/login', json={'username': 'temp-user-01', 'password': 'temporary-pass-1234'})
        assert login.status_code == 401


def test_admin_cannot_delete_user_with_audit_history(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        created = client.post(
            '/api/users',
            headers=admin_headers,
            json={
                'username': 'counselor-audit',
                'full_name': 'Counselor Audit',
                'password': 'temporary-pass-1234',
                'role': 'counselor',
            },
        )
        assert created.status_code == 200
        created_user = created.json()

        user_login = client.post('/api/auth/login', json={'username': 'counselor-audit', 'password': 'temporary-pass-1234'})
        assert user_login.status_code == 200

        deleted = client.delete(f"/api/users/{created_user['id']}", headers=admin_headers)
        assert deleted.status_code == 400
        assert 'related records exist' in deleted.json()['detail']
        assert 'forensic audit history' in deleted.json()['detail']


def test_admin_can_view_and_update_app_settings(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)

        current = client.get('/api/settings', headers=headers)
        assert current.status_code == 200
        assert current.json()['organization_name'] == 'R3 Recovery Services'
        assert current.json()['llm_api_key_configured'] is False

        updated = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'organization_name': 'R3 Recovery Services QA',
                'llm_enabled': True,
                'llm_provider_name': 'OpenAI-compatible',
                'llm_base_url': 'https://api.openai.com/v1',
                'llm_model': 'gpt-4.1-mini',
                'llm_api_key': 'sk-test-123',
                'llm_use_for_access_review': True,
                'llm_use_for_evaluation_gap_analysis': True,
                'access_intel_enabled': True,
                'access_lookup_timeout_seconds': 5,
            },
        )
        assert updated.status_code == 200
        payload = updated.json()
        assert payload['organization_name'] == 'R3 Recovery Services QA'
        assert payload['llm_enabled'] is True
        assert payload['llm_api_key_configured'] is True


def test_saved_llm_configuration_can_call_openai_compatible_json_endpoint(app_with_sqlite, monkeypatch):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        updated = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'llm_enabled': True,
                'llm_base_url': 'https://llm.example.test/v1',
                'llm_model': 'synthetic-model',
                'llm_api_key': 'sk-synthetic-llm',
                'access_lookup_timeout_seconds': 5,
            },
        )
        assert updated.status_code == 200
        assert updated.json()['llm_api_key_configured'] is True

    import app.services.llm_assist as llm_module

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'choices': [{'message': {'content': '{"status":"ok","missing":[]}'}}]}

    class FakeClient:
        def __init__(self, timeout):
            captured['timeout'] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, endpoint, *, json, headers):
            captured['endpoint'] = endpoint
            captured['payload'] = json
            captured['authorization'] = headers.get('Authorization')
            return FakeResponse()

    monkeypatch.setattr(llm_module.httpx, 'Client', FakeClient)

    db = session_local()
    try:
        app_settings = db.execute(select(AppSetting)).scalar_one()
        assert llm_module.llm_is_configured(app_settings) is True
        payload = llm_module.call_llm_json(app_settings, system_prompt='Return JSON.', user_prompt='Check synthetic note.')
        assert payload == {'status': 'ok', 'missing': []}
        assert captured['endpoint'] == 'https://llm.example.test/v1/chat/completions'
        assert captured['payload']['model'] == 'synthetic-model'
        assert captured['authorization'] == 'Bearer sk-synthetic-llm'
    finally:
        db.close()
