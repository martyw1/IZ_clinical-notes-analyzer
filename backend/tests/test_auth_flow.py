import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.models import Role, User


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


def test_reset_password_flow_for_first_login_user():
    username = f'test-user-{uuid.uuid4().hex[:8]}'
    original_password = 'original-pass-1234'
    replacement_password = 'replacement-pass-1234'

    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not existing:
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(original_password),
                    role=Role.counselor,
                    must_reset_password=True,
                )
            )
            db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': username, 'password': original_password})
        assert login.status_code == 200
        token = login.json()['access_token']
        assert login.json()['must_reset_password'] is True

        reset = client.post('/api/auth/reset-password', json={'new_password': replacement_password}, headers={'Authorization': f'Bearer {token}'})
        assert reset.status_code == 200

        relogin = client.post('/api/auth/login', json={'username': username, 'password': replacement_password})
        assert relogin.status_code == 200
        assert relogin.json()['must_reset_password'] is False

        me = client.get('/api/users/me', headers={'Authorization': f"Bearer {relogin.json()['access_token']}"})
        assert me.status_code == 200
        assert me.json()['must_reset_password'] is False
