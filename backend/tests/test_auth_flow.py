from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.status_code == 200


def test_login_and_me_flow():
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3'})
        assert response.status_code == 200
        token = response.json()['access_token']

        me = client.get('/api/users/me', headers={'Authorization': f'Bearer {token}'})
        assert me.status_code == 200
        assert me.json()['username'] == 'admin'
