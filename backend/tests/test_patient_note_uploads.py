import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import REPO_ROOT
from app.core.security import hash_password
from app.models.models import AuditLog, PatientNoteDocument, PatientNoteSet, Role, TreatmentPlanClient, User

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _login_headers(client: TestClient, username: str = 'admin', password: str = BOOTSTRAP_ADMIN_PASSWORD) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _auth_headers(client: TestClient) -> dict[str, str]:
    return _login_headers(client)


def _upload_payload(patient_id: str, *, upload_mode: str, file_name: str, label: str, content: bytes | None = None):
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
    files = [('files', (file_name, content or b'Intake packet completed and signed.\nPrimary clinician assigned.\n', 'text/plain'))]
    return data, files


def _redacted_pdf_payload(patient_id: str, pdf_path: Path, *, document_date: str):
    data = {
        'patient_id': patient_id,
        'upload_mode': 'initial',
        'level_of_care': '',
        'admission_date': '',
        'discharge_date': '',
        'primary_clinician': '',
        'upload_notes': 'Synthetic test upload from redacted example PDF.',
        'file_manifest': json.dumps(
            [
                {
                    'client_file_name': pdf_path.name,
                    'document_label': 'Treatment Plan Export',
                    'alleva_bucket': 'custom_forms',
                    'document_type': 'treatment_plan_review',
                    'completion_status': 'completed',
                    'client_signed': True,
                    'staff_signed': True,
                    'document_date': document_date,
                    'description': 'Redacted treatment plan export fixture.',
                }
            ]
        ),
    }
    files = [('files', (pdf_path.name, pdf_path.read_bytes(), 'application/pdf'))]
    return data, files


def test_detect_patient_id_from_uploaded_files(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        response = client.post(
            '/api/patient-note-sets/detect-patient-id',
            headers=headers,
            files=[('files', ('alleva-intake.txt', b'Patient ID: PAT-DETECT-100\nAdmission completed.\n', 'text/plain'))],
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload['patient_id'] == 'PAT-DETECT-100'
        assert payload['confidence'] == 'high'
        assert payload['source_filename'] == 'alleva-intake.txt'

    db = session_local()
    try:
        detection_log = db.execute(select(AuditLog).where(AuditLog.action == 'patient_note_set.patient_id.detected')).scalar_one_or_none()
        assert detection_log is not None
        assert detection_log.patient_id == 'PAT-DETECT-100'
    finally:
        db.close()


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
        assert payload['review_chart_id'] is not None
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
        assert download.content == b'Intake packet completed and signed.\nPrimary clinician assigned.\n'

        chart = client.get(f"/api/charts/{payload['review_chart_id']}", headers=headers)
        assert chart.status_code == 200
        assert chart.json()['source_note_set_id'] == payload['id']
        assert chart.json()['state'] == 'Awaiting Office Manager Review'
        assert chart.json()['system_summary']

    db = session_local()
    try:
        upload_log = db.execute(select(AuditLog).where(AuditLog.action == 'patient_note_set.uploaded')).scalar_one_or_none()
        assert upload_log is not None
        assert upload_log.patient_id == 'PAT-100'

        document = db.execute(select(PatientNoteDocument).where(PatientNoteDocument.note_set_id == payload['id'])).scalar_one()
        import app.services.patient_notes as patient_notes_module
        from app.services.secure_storage import ENCRYPTION_MAGIC

        stored_path = patient_notes_module.settings.upload_dir_path / document.storage_path
        stored_bytes = stored_path.read_bytes()
        assert stored_bytes.startswith(ENCRYPTION_MAGIC)
        assert b'Intake packet completed' not in stored_bytes

        document_log = db.execute(select(AuditLog).where(AuditLog.action == 'patient_note.document.download')).scalar_one_or_none()
        assert document_log is not None
        assert document_log.patient_id == 'PAT-100'

        eval_log = db.execute(select(AuditLog).where(AuditLog.action == 'chart.system_evaluated')).scalar_one_or_none()
        assert eval_log is not None
        assert eval_log.patient_id == 'PAT-100'

        for audit_log in db.execute(select(AuditLog)).scalars().all():
            serialized = f'{audit_log.message} {audit_log.details}'
            assert 'Intake packet completed' not in serialized
            assert 'Primary clinician assigned' not in serialized
            assert 'intake-packet.pdf' not in serialized
    finally:
        db.close()


def test_download_requires_access_to_note_set(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        data, files = _upload_payload('PAT-SECURE-DL', upload_mode='initial', file_name='secure-download.txt', label='Secure Download')
        uploaded = client.post('/api/patient-note-sets', headers=admin_headers, data=data, files=files)
        assert uploaded.status_code == 200

        db = session_local()
        try:
            db.add(
                User(
                    username='other-counselor',
                    full_name='Other Counselor',
                    password_hash=hash_password('other-counselor-pass-1234'),
                    role=Role.counselor,
                    is_active=True,
                    must_reset_password=False,
                )
            )
            db.commit()
        finally:
            db.close()

        counselor_headers = _login_headers(client, 'other-counselor', 'other-counselor-pass-1234')
        blocked = client.get(
            f"/api/patient-note-sets/{uploaded.json()['id']}/documents/{uploaded.json()['documents'][0]['id']}/download",
            headers=counselor_headers,
        )
        assert blocked.status_code == 403


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
        assert second_response.json()['review_chart_id'] != first_response.json()['review_chart_id']

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


def test_upload_uses_detected_patient_id_when_field_is_blank(app_with_sqlite):
    app, _session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        data, files = _upload_payload(
            '',
            upload_mode='initial',
            file_name='alleva-binder.txt',
            label='Admission Binder',
            content=b'Client ID: PAT-AUTO-200\nInitial binder import.\n',
        )
        uploaded = client.post('/api/patient-note-sets', headers=headers, data=data, files=files)

        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload['patient_id'] == 'PAT-AUTO-200'
        assert payload['review_chart_id'] is not None


def test_redacted_example_pdf_upload_extracts_clinician_loc_and_placeholder_name(app_with_sqlite):
    app, session_local = app_with_sqlite
    pdf_path = REPO_ROOT / 'example-treatment-plans' / 'JTXP.pdf'
    assert pdf_path.exists()

    with TestClient(app) as client:
        headers = _auth_headers(client)
        data, files = _redacted_pdf_payload('PAT-REDACTED-JTXP', pdf_path, document_date='2026-04-02')
        uploaded = client.post('/api/patient-note-sets', headers=headers, data=data, files=files)

        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload['primary_clinician']
        assert payload['level_of_care'] == 'GOP'
        assert payload['admission_date'] in {'04/02/2026', '2026-04-02'}
        assert payload['review_chart_id'] is not None

        chart = client.get(f"/api/charts/{payload['review_chart_id']}", headers=headers)
        assert chart.status_code == 200
        chart_payload = chart.json()
        assert chart_payload['primary_clinician'] == payload['primary_clinician']
        assert chart_payload['level_of_care'] == 'GOP'
        assert chart_payload['client_name'].startswith('Name Hidden ')
        assert 'redacted_hidden' in chart_payload['other_details']

    db = session_local()
    try:
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-REDACTED-JTXP')).scalar_one()
        assert stored_client.current_level_of_care == 'GOP'
        assert stored_client.permitted_name.startswith('Name Hidden ')

        upload_log = db.execute(select(AuditLog).where(AuditLog.action == 'patient_note_set.uploaded')).scalar_one()
        assert 'redacted_hidden' in upload_log.details
        assert 'metadata_extracted' in upload_log.details
        assert payload['primary_clinician'] not in upload_log.details
    finally:
        db.close()


def test_redacted_iop_example_pdf_upload_extracts_level_of_care(app_with_sqlite):
    app, _session_local = app_with_sqlite
    pdf_path = REPO_ROOT / 'example-treatment-plans' / 'XTXP.pdf'
    assert pdf_path.exists()

    with TestClient(app) as client:
        headers = _auth_headers(client)
        data, files = _redacted_pdf_payload('PAT-REDACTED-XTXP', pdf_path, document_date='2026-03-24')
        uploaded = client.post('/api/patient-note-sets', headers=headers, data=data, files=files)

        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload['primary_clinician']
        assert payload['level_of_care'] == 'IOP 5'
        assert payload['admission_date'] in {'02/25/2026', '2026-02-25'}
        assert payload['review_chart_id'] is not None


def test_reanalysis_preserves_operator_display_name_for_redacted_upload(app_with_sqlite):
    app, session_local = app_with_sqlite
    pdf_path = REPO_ROOT / 'example-treatment-plans' / 'JTXP.pdf'

    with TestClient(app) as client:
        headers = _auth_headers(client)
        data, files = _redacted_pdf_payload('PAT-REANALYZE-JTXP', pdf_path, document_date='2026-04-02')
        uploaded = client.post('/api/patient-note-sets', headers=headers, data=data, files=files)
        assert uploaded.status_code == 200
        chart_id = uploaded.json()['review_chart_id']

        chart = client.get(f'/api/charts/{chart_id}', headers=headers)
        assert chart.status_code == 200
        chart_payload = chart.json()
        update_payload = {
            'patient_id': chart_payload['patient_id'],
            'client_name': 'Synthetic Display Name',
            'level_of_care': chart_payload['level_of_care'],
            'admission_date': chart_payload['admission_date'],
            'discharge_date': chart_payload['discharge_date'],
            'primary_clinician': chart_payload['primary_clinician'],
            'auditor_name': chart_payload['auditor_name'],
            'other_details': chart_payload['other_details'],
            'notes': chart_payload['notes'],
            'checklist_items': [
                {
                    'item_key': item['item_key'],
                    'status': item['status'],
                    'notes': item['notes'],
                    'evidence_location': item['evidence_location'],
                    'evidence_date': item['evidence_date'],
                    'expiration_date': item['expiration_date'],
                }
                for item in chart_payload['checklist_items']
            ],
        }
        updated = client.put(f'/api/charts/{chart_id}', headers=headers, json=update_payload)
        assert updated.status_code == 200
        assert updated.json()['client_name'] == 'Synthetic Display Name'

        reanalyzed = client.post(f'/api/charts/{chart_id}/reanalyze', headers=headers)
        assert reanalyzed.status_code == 200
        assert reanalyzed.json()['client_name'] == 'Synthetic Display Name'

    db = session_local()
    try:
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-REANALYZE-JTXP')).scalar_one()
        assert stored_client.permitted_name == 'Synthetic Display Name'
        assert db.execute(select(AuditLog).where(AuditLog.action == 'chart.reanalyze')).scalar_one_or_none() is not None
    finally:
        db.close()
