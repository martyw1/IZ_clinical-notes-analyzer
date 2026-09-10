from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from pytest import MonkeyPatch, mark

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_recovery_consumes_code_and_revokes_sessions(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    generated = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'StrongLocalActivePass2'})
    assert generated.status_code == 200
    code = generated.json()['recovery_code']
    payload = {'username': 'admin', 'recovery_code': code, 'new_password': 'RecoveredSyntheticPass3'}
    recovered = client.post('/api/auth/recover-password', json=payload)
    assert recovered.status_code == 200
    assert client.get('/api/users/me', headers=headers).status_code == 401
    assert client.post('/api/auth/recover-password', json=payload).status_code == 400
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': payload['new_password']})
    assert login.status_code == 200
    assert login.json()['must_reset_password'] is False


def test_recovery_generation_requires_current_password_and_rotates(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    assert client.get('/api/users/me/recovery-code', headers=headers).json() == {'configured': False}
    assert client.post('/api/users/me/recovery-code', json={'current_password': 'StrongLocalActivePass2'}).status_code == 401
    assert client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'WrongPassword1'}).status_code == 400
    first = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'StrongLocalActivePass2'})
    second = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'StrongLocalActivePass2'})
    assert second.headers['cache-control'] == 'no-store'
    old_code = first.json()['recovery_code']
    code = second.json()['recovery_code']
    assert old_code != code
    assert client.get('/api/users/me/recovery-code', headers=headers).json() == {'configured': True}
    from app.v2.db import SessionLocal
    from app.v2.models import PasswordRecovery

    with SessionLocal() as db:
        stored = db.get(PasswordRecovery, 1)
        assert stored is not None
        assert stored.code_hash == sha256(code.encode()).hexdigest()
    assert code not in client.get('/api/audit/logs', headers=headers).text
    assert client.post('/api/auth/recover-password', json={'username': 'admin', 'recovery_code': old_code, 'new_password': 'RecoveredSyntheticPass3'}).status_code == 400


@mark.parametrize('account_state', ['disabled', 'manual_lock', 'temporary_lock'])
def test_recovery_only_clears_temporary_lock(tmp_path: Path, monkeypatch: MonkeyPatch, account_state: str) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    code = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'StrongLocalActivePass2'}).json()['recovery_code']
    from app.v2.db import SessionLocal
    from app.v2.models import User

    with SessionLocal() as db:
        user = db.get(User, 1)
        assert user is not None
        user.is_active = account_state != 'disabled'
        user.is_locked = account_state != 'disabled'
        if account_state == 'temporary_lock':
            user.auth_state = 'locked_until'
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()
    result = client.post('/api/auth/recover-password', json={'username': 'admin', 'recovery_code': code, 'new_password': 'RecoveredSyntheticPass3'})
    assert result.status_code == (200 if account_state == 'temporary_lock' else 400)
    if account_state == 'temporary_lock':
        assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'RecoveredSyntheticPass3'}).status_code == 200


def test_recovery_failure_is_generic_and_throttled(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    payload = {'username': 'missing', 'recovery_code': 'wrong-code', 'new_password': 'RecoveredSyntheticPass3'}
    unknown = client.post('/api/auth/recover-password', json=payload)
    known = client.post('/api/auth/recover-password', json={**payload, 'username': 'admin'})
    assert unknown.status_code == known.status_code == 400
    assert unknown.json() == known.json()
    for _ in range(18):
        assert client.post('/api/auth/recover-password', json=payload).status_code == 400
    limited = client.post('/api/auth/recover-password', json=payload)
    assert limited.status_code == 429
    assert limited.headers['retry-after'] == '900'
    from v2_test_runtime import configured_client, reset_app_modules

    reset_app_modules()
    restarted_client = configured_client()
    assert restarted_client.post('/api/auth/recover-password', json=payload).status_code == 429


@mark.parametrize('new_password', ['r3mar123ABC', 'short1', 'x' * 73 + '1', 'ä' * 37 + '1'])
def test_invalid_password_does_not_consume_code(tmp_path: Path, monkeypatch: MonkeyPatch, new_password: str) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    code = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'StrongLocalActivePass2'}).json()['recovery_code']
    result = client.post('/api/auth/recover-password', json={'username': 'admin', 'recovery_code': code, 'new_password': new_password})
    assert result.status_code == 400
    assert client.get('/api/users/me/recovery-code', headers=headers).json() == {'configured': True}


def test_recovery_is_atomic_for_simultaneous_requests(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    code = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'StrongLocalActivePass2'}).json()['recovery_code']

    def recover() -> int:
        return client.post('/api/auth/recover-password', json={'username': 'admin', 'recovery_code': code, 'new_password': 'RecoveredSyntheticPass3'}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: recover(), range(2)))
    assert sorted(results) == [200, 400]


def test_existing_database_gets_recovery_tables_without_password_reset(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    _auth_headers(client)
    from app.v2.db import engine
    from app.v2.models import PasswordRecovery, PasswordRecoveryThrottle
    from v2_test_runtime import configured_client, reset_app_modules

    PasswordRecovery.__table__.drop(engine)
    PasswordRecoveryThrottle.__table__.drop(engine)
    reset_app_modules()
    restarted_client = configured_client()
    login = restarted_client.post('/api/auth/login', json={'username': 'admin', 'password': 'StrongLocalActivePass2'})
    assert login.status_code == 200
    assert login.json()['must_reset_password'] is False
    headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
    assert restarted_client.get('/api/users/me/recovery-code', headers=headers).json() == {'configured': False}


def test_admin_reset_revokes_previous_recovery_code(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    admin = _auth_headers(client)
    created = client.post('/api/users', headers=admin, json={'username': 'synthetic', 'full_name': 'Synthetic User', 'role': 'counselor', 'password': 'InitialSyntheticPass1'})
    login = client.post('/api/auth/login', json={'username': 'synthetic', 'password': 'InitialSyntheticPass1'})
    forced_headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
    assert client.post('/api/users/me/recovery-code', headers=forced_headers, json={'current_password': 'InitialSyntheticPass1'}).status_code == 403
    changed = client.post('/api/users/me/change-password', headers=forced_headers, json={'current_password': 'InitialSyntheticPass1', 'new_password': 'ActiveSyntheticPass2'})
    headers = {'Authorization': f"Bearer {changed.json()['access_token']}"}
    code = client.post('/api/users/me/recovery-code', headers=headers, json={'current_password': 'ActiveSyntheticPass2'}).json()['recovery_code']
    reset = client.post(f"/api/users/{created.json()['id']}/reset-password", headers=admin, json={'new_password': 'AdminSyntheticPass3', 'require_reset_on_login': True})
    assert reset.status_code == 200
    assert client.post('/api/auth/recover-password', json={'username': 'synthetic', 'recovery_code': code, 'new_password': 'RecoveredSyntheticPass4'}).status_code == 400
