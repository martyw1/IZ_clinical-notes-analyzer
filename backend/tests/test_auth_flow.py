import importlib
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.models import Role, User

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def reload_app_with_env(tmp_path: Path, monkeypatch, **env_overrides):
    db_path = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')

    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)

    import app.core.config as config_module
    import app.db.session as session_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(session_module)
    importlib.reload(main_module)

    return main_module.app, session_module.SessionLocal


def test_health(app_with_sqlite):
    app, _ = app_with_sqlite
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.status_code == 200
        api_response = client.get('/api/health')
        assert api_response.status_code == 200


def test_login_and_me_flow(app_with_sqlite):
    app, _ = app_with_sqlite
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
        assert response.status_code == 200
        assert response.json()['must_reset_password'] is False
        token = response.json()['access_token']

        me = client.get('/api/users/me', headers={'Authorization': f'Bearer {token}'})
        assert me.status_code == 200
        assert me.json()['username'] == 'admin'
        assert me.json()['must_reset_password'] is False


def test_reset_password_flow_for_first_login_user(app_with_sqlite):
    app, session_local = app_with_sqlite
    username = f'test-user-{uuid.uuid4().hex[:8]}'
    original_password = 'original-pass-1234'
    replacement_password = 'replacement-pass-1234'

    with TestClient(app) as client:
        db = session_local()
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


def test_startup_restores_locked_bootstrap_admin(tmp_path: Path, monkeypatch):
    bootstrap_password = BOOTSTRAP_ADMIN_PASSWORD
    app, session_local = reload_app_with_env(
        tmp_path,
        monkeypatch,
        BOOTSTRAP_ADMIN_USERNAME='admin',
        BOOTSTRAP_ADMIN_PASSWORD=bootstrap_password,
        RESET_BOOTSTRAP_ADMIN_ON_STARTUP='true',
        ENVIRONMENT='development',
    )

    with TestClient(app):
        pass

    db = session_local()
    try:
        admin = db.execute(select(User).where(User.username == 'admin')).scalar_one()
        admin.password_hash = hash_password('wrong-pass-1234')
        admin.failed_login_attempts = 5
        admin.is_locked = True
        admin.must_reset_password = False
        db.commit()
    finally:
        db.close()

    app, session_local = reload_app_with_env(
        tmp_path,
        monkeypatch,
        BOOTSTRAP_ADMIN_USERNAME='admin',
        BOOTSTRAP_ADMIN_PASSWORD=bootstrap_password,
        RESET_BOOTSTRAP_ADMIN_ON_STARTUP='true',
        ENVIRONMENT='development',
    )

    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': bootstrap_password})
        assert login.status_code == 200
        assert login.json()['must_reset_password'] is False

    db = session_local()
    try:
        admin = db.execute(select(User).where(User.username == 'admin')).scalar_one()
        assert admin.failed_login_attempts == 0
        assert admin.is_locked is False
        assert admin.must_reset_password is False
    finally:
        db.close()


def test_bootstrap_admin_password_is_static_in_app(app_with_sqlite):
    app, _ = app_with_sqlite
    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
        assert login.status_code == 200

        token = login.json()['access_token']
        reset = client.post(
            '/api/auth/reset-password',
            json={'new_password': 'replacement-password-1234'},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert reset.status_code == 400
        assert 'fixed' in reset.json()['detail']
