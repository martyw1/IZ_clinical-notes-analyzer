from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.patient_notes import resolve_storage_path

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_upload_rejects_unsupported_file_type(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets',
            headers=_auth_headers(client),
            data={'patient_id': 'PAT-SEC-1', 'upload_mode': 'initial'},
            files=[('files', ('malware.exe', b'not a note', 'application/octet-stream'))],
        )
        assert response.status_code == 400
        assert 'Unsupported file type' in response.json()['detail']


def test_patient_id_detection_rejects_unsupported_file_type(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets/detect-patient-id',
            headers=_auth_headers(client),
            files=[('files', ('malware.exe', b'not a note', 'application/octet-stream'))],
        )
        assert response.status_code == 400
        assert 'Unsupported file type' in response.json()['detail']


def test_upload_rejects_excessive_file_count(app_with_sqlite):
    app, _session_local = app_with_sqlite
    files = [('files', (f'note-{index}.txt', b'Patient ID: PAT-SEC-2\n', 'text/plain')) for index in range(41)]
    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets',
            headers=_auth_headers(client),
            data={'patient_id': 'PAT-SEC-2', 'upload_mode': 'initial'},
            files=files,
        )
        assert response.status_code == 413
        assert 'too many files' in response.json()['detail']


def test_upload_rejects_too_large_file(app_with_sqlite, monkeypatch):
    app, _session_local = app_with_sqlite
    import app.api.routes as routes_module

    monkeypatch.setattr(routes_module.settings, 'max_upload_file_bytes', 8)
    monkeypatch.setattr(routes_module.settings, 'max_upload_total_bytes', 100)

    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets',
            headers=_auth_headers(client),
            data={'patient_id': 'PAT-SEC-3', 'upload_mode': 'initial'},
            files=[('files', ('too-large.txt', b'Patient ID: PAT-SEC-3\n', 'text/plain'))],
        )
        assert response.status_code == 413
        assert 'per-file limit' in response.json()['detail']


def test_upload_rejects_binder_total_size(app_with_sqlite, monkeypatch):
    app, _session_local = app_with_sqlite
    import app.api.routes as routes_module

    monkeypatch.setattr(routes_module.settings, 'max_upload_file_bytes', 100)
    monkeypatch.setattr(routes_module.settings, 'max_upload_total_bytes', 18)

    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets',
            headers=_auth_headers(client),
            data={'patient_id': 'PAT-SEC-4', 'upload_mode': 'initial'},
            files=[
                ('files', ('one.txt', b'1234567890', 'text/plain')),
                ('files', ('two.txt', b'abcdefghij', 'text/plain')),
            ],
        )
        assert response.status_code == 413
        assert 'total binder limit' in response.json()['detail']


def test_upload_requires_patient_id_when_detection_fails(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets',
            headers=_auth_headers(client),
            data={'patient_id': '', 'upload_mode': 'initial'},
            files=[('files', ('unidentified.txt', b'No labeled chart identifier here.', 'text/plain'))],
        )
        assert response.status_code == 400
        assert 'Patient ID is required' in response.json()['detail']


def test_upload_rejects_conflicting_detected_patient_ids(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app) as client:
        response = client.post(
            '/api/patient-note-sets',
            headers=_auth_headers(client),
            data={'patient_id': '', 'upload_mode': 'initial'},
            files=[
                ('files', ('first.txt', b'Patient ID: PAT-CONFLICT-1', 'text/plain')),
                ('files', ('second.txt', b'Patient ID: PAT-CONFLICT-2', 'text/plain')),
            ],
        )
        assert response.status_code == 400
        assert 'Conflicting patient IDs' in response.json()['detail']


def test_stored_path_traversal_is_rejected(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app):
        try:
            resolve_storage_path('../outside.txt')
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError('Path traversal was not rejected')
