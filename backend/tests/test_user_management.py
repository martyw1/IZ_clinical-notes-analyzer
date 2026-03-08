from fastapi.testclient import TestClient


BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
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
