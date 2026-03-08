import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.models import AuditLog, PatientNoteSet


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3'})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _upload_payload(patient_id: str, *, upload_mode: str, file_name: str, label: str):
    data = {
        'patient_id': patient_id,
        'upload_mode': upload_mode,
        'level_of_care': 'Residential',
        'admission_date': '04/01/2025',
        'discharge_date': '09/10/2025',
        'primary_clinician': 'Clinician A',
        'upload_notes': 'Imported from Alleva Document Manager.',
        'file_manifest': json.dumps(
            [
                {
                    'client_file_name': file_name,
                    'document_label': label,
                    'alleva_bucket': 'custom_forms',
                    'document_type': 'clinical_note',
                    'completion_status': 'completed',
                    'client_signed': True,
                    'staff_signed': True,
                    'document_date': '04/01/2025',
                    'description': 'Admission packet document.',
                }
            ]
        ),
    }
    files = [('files', (file_name, b'patient note payload', 'application/pdf'))]
    return data, files


def test_initial_patient_note_upload_and_download(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        data, files = _upload_payload('PAT-100', upload_mode='initial', file_name='intake-packet.pdf', label='Intake Packet')
        uploaded = client.post('/api/patient-note-sets', headers=headers, data=data, files=files)

        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload['patient_id'] == 'PAT-100'
        assert payload['version'] == 1
        assert payload['status'] == 'active'
        assert payload['upload_mode'] == 'initial'
        assert payload['file_count'] == 1
        assert payload['documents'][0]['document_label'] == 'Intake Packet'
        assert payload['documents'][0]['client_signed'] is True
        assert len(payload['documents'][0]['sha256']) == 64

        detail = client.get(f"/api/patient-note-sets/{payload['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()['documents'][0]['original_filename'] == 'intake-packet.pdf'

        download = client.get(
            f"/api/patient-note-sets/{payload['id']}/documents/{payload['documents'][0]['id']}/download",
            headers=headers,
        )
        assert download.status_code == 200
        assert download.content == b'patient note payload'

    db = session_local()
    try:
        upload_log = db.execute(select(AuditLog).where(AuditLog.action == 'patient_note_set.uploaded')).scalar_one_or_none()
        assert upload_log is not None
        assert upload_log.patient_id == 'PAT-100'

        document_log = db.execute(select(AuditLog).where(AuditLog.action == 'patient_note.document.download')).scalar_one_or_none()
        assert document_log is not None
        assert document_log.patient_id == 'PAT-100'
    finally:
        db.close()


def test_patient_note_update_creates_new_version_and_supersedes_previous_set(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)

        first_data, first_files = _upload_payload('PAT-101', upload_mode='initial', file_name='week-1.pdf', label='Week 1 Note')
        first_response = client.post('/api/patient-note-sets', headers=headers, data=first_data, files=first_files)
        assert first_response.status_code == 200

        second_data, second_files = _upload_payload('PAT-101', upload_mode='update', file_name='week-2.pdf', label='Week 2 Note')
        second_response = client.post('/api/patient-note-sets', headers=headers, data=second_data, files=second_files)
        assert second_response.status_code == 200
        assert second_response.json()['version'] == 2
        assert second_response.json()['status'] == 'active'

        listing = client.get('/api/patient-note-sets?patient_id=PAT-101', headers=headers)
        assert listing.status_code == 200
        assert [item['version'] for item in listing.json()] == [2, 1]

    db = session_local()
    try:
        note_sets = list(
            db.execute(select(PatientNoteSet).where(PatientNoteSet.patient_id == 'PAT-101').order_by(PatientNoteSet.version.asc()))
            .scalars()
            .all()
        )
        assert len(note_sets) == 2
        assert note_sets[0].status.value == 'superseded'
        assert note_sets[1].status.value == 'active'
    finally:
        db.close()
