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


def test_stored_path_traversal_is_rejected(app_with_sqlite):
    app, _session_local = app_with_sqlite
    with TestClient(app):
        try:
            resolve_storage_path('../outside.txt')
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError('Path traversal was not rejected')
