import pytest
from sqlalchemy import text

from test_v2_evaluation_persistence import _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_staff_directory_and_explicit_primary_links_include_zero_caseload_and_remain_scoped(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    for patient in ("SYNTHETIC-CLINICIAN-A", "SYNTHETIC-CLINICIAN-B"):
        assert client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers,
                           json=_aggregate(patient).model_dump(mode="json")).status_code == 201
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_clinicians import persist_alleva_clinicians
    from app.v2.services.imported_counselors import primary_counselors_for_records
    clients = [{"id": 101, "facilityId": 10, "primaryClinician": {"id": 501, "route": "/users/501"}},
               {"id": 102, "facilityId": 20, "primaryClinician": {"id": 502, "route": "/users/502"}}]
    staff = [{"id": number, "name": {"first": "Synthetic", "last": name}, "facility": {"id": facility},
              "tenant": "synthetic-tenant", "role": "Clinician", "ssn": "DO-NOT-PERSIST-STAFF-SSN"}
             for number, name, facility in [(501, "Assigned", 10), (502, "Hidden", 20), (503, "ZeroCaseload", 10), (504, "Unmapped", 99)]]
    with SessionLocal() as db:
        hidden = db.execute(text("INSERT INTO facilities(facility_key,display_name,timezone,is_active,created_at,updated_at) "
            "VALUES('synthetic-hidden','Synthetic hidden','UTC',1,'2026-11-06','2026-11-06')")).lastrowid
        rows = db.execute(text("SELECT id FROM patients ORDER BY id")).all()
        a, b = (int(row[0]) for row in rows)
        db.execute(text("UPDATE patients SET source_system='alleva_rest_api',source_patient_id='101' WHERE id=:id"), {"id": a})
        db.execute(text("UPDATE patients SET source_system='alleva_rest_api',source_patient_id='102',facility_id=:facility WHERE id=:id"), {"id": b, "facility": hidden})
        counts = persist_alleva_clinicians(db, staff, clients, "2026-11-06T14:00:00Z", "synthetic-connection")
        assert counts["staff_returned"] == 4
        assert counts["staff_imported"] == 4
        assert counts["staff_unmapped_facility"] == 1
        db.commit()
        assert primary_counselors_for_records(db, (a,))[a][1] == "Synthetic Assigned"
        # Same import is idempotent and missing relationships explicitly clear assignment.
        persist_alleva_clinicians(db, staff, clients, "2026-11-06T14:00:00Z", "synthetic-connection")
        assert db.execute(text("SELECT COUNT(*) FROM imported_counselors")).scalar_one() == 4
        clients[0]["primaryClinician"] = {"id": 501, "route": "/users/999"}
        persist_alleva_clinicians(db, staff, clients, "2026-11-06T15:00:00Z", "synthetic-connection")
        assert a not in primary_counselors_for_records(db, (a,))
        db.commit()
    response = client.get("/api/v2/clinicians", headers=headers)
    assert response.status_code == 200
    assert response.json()["master_directory_connected"] is True
    assert {row["name"] for row in response.json()["items"]} == {"Synthetic Assigned", "Synthetic ZeroCaseload", "Synthetic Unmapped"}
    assert "DO-NOT-PERSIST" not in response.text



@pytest.mark.parametrize("loc,updated,created,expected", [
    ("PHP-5", "2026-07-12T12:00:00Z", "2026-07-01T12:00:00Z", "2026-08-11"),
    ("Evening IOP 4", "", "2026-09-01T12:00:00Z", "2026-10-31"),
])
def test_builtin_sync_pulls_documented_staff_and_computes_loc_deadline(tmp_path, monkeypatch, loc, updated, created, expected):
    from test_v2_alleva_sync import _mock_alleva_server, _completed_sync
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    with _mock_alleva_server(
        client_items=[{"id": "912", "mrn": "SYNTHETIC-912", "status": "Active", "facilityId": 10,
                       "levelOfCare": loc, "admissionDateTime": "2026-01-01", "primaryClinician": {"id": 501, "route": "/users/501"}}],
        plan_items=[{"id": "plan-912", "client": {"id": "912", "route": "/clients/912"}, "createdDate": created, "lastModified": updated}],
        staff_items=[{"id": 501, "name": {"first": "Synthetic", "last": "Clinician"}, "tenant": "synthetic",
                      "facility": {"id": 10}, "role": "Clinician"},
                     {"id": 502, "name": {"first": "Synthetic", "last": "Available"}, "tenant": "synthetic",
                      "facility": {"id": 10}, "role": "Clinician"}],
    ) as (base_url, state):
        configured = client.patch('/api/api-configuration', headers=headers, json={
            'api_base_url': base_url, 'token_url': f'{base_url}/token', 'client_id': 'mock-client',
            'client_secret': 'mock-secret', 'scopes': 'plans.read', 'api_enabled': True,
            'treatment_plan_sync_enabled': True, 'treatment_plan_sync_approved': True,
        })
        assert configured.status_code == 200
        job = _completed_sync(client, headers)
        assert job['status'] == 'completed', job
        assert '2 returned; 2 saved' in job['message']
    assert any(path.startswith('/users?') for path in state.paths)
    directory = client.get('/api/v2/clinicians', headers=headers).json()
    assert {row['name'] for row in directory['items']} == {'Synthetic Clinician', 'Synthetic Available'}
    roster = client.get('/api/v2/treatment-plan-roster', headers=headers).json()['items']
    assert roster[0]['primary_counselor_name'] == 'Synthetic Clinician'
    assert roster[0]['next_due_date'] == expected
    assert roster[0]['deadline_status'] == 'Overdue'
    assert client.get('/api/v2/dashboard', headers=headers).json()['metrics']['overdue_plans'] == 1

    selected = next(row['id'] for row in directory['items'] if row['name'] == 'Synthetic Clinician')
    scoped = client.get('/api/v2/treatment-plan-roster', headers=headers, params={'primary_clinician_id': selected}).json()['items']
    assert len(scoped) == 1
    assert client.get('/api/v2/treatment-plan-roster', headers=headers, params={'primary_clinician_id': 9999}).json()['items'] == []
    assert client.get('/api/v2/patient-roster', headers=headers, params={'primary_clinician_id': selected}).json()['items'][0]['primary_counselor_id'] == selected
    assert directory['last_import']['state'] == 'completed'
    assert directory['last_import']['summary']['staff_returned'] == 2
    assert directory['last_import']['summary']['staff_imported'] == 2
    assert directory['last_import']['summary']['assignments_linked'] == 1
    assert 'Synthetic Clinician' not in str(directory['last_import'])



def test_failed_staff_request_is_audited_and_never_reported_as_an_empty_success(tmp_path, monkeypatch):
    from test_v2_alleva_sync import _mock_alleva_server, _completed_sync
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    # Reload the module owned by this isolated test runtime.
    from app.v2.services import alleva_sync
    original = alleva_sync._paged_records
    def fail_staff(*args, **kwargs):
        if args[3] == 'clinicians':
            raise alleva_sync.AllevaSyncError('Synthetic staff access failure', endpoint_key='clinicians', http_status=403, failure_stage='collection_request')
        return original(*args, **kwargs)
    monkeypatch.setattr(alleva_sync, '_paged_records', fail_staff)
    with _mock_alleva_server() as (base_url, _):
        assert client.patch('/api/api-configuration', headers=headers, json={
            'api_base_url': base_url, 'token_url': f'{base_url}/token', 'client_id': 'mock-client',
            'client_secret': 'mock-secret', 'scopes': 'plans.read', 'api_enabled': True,
            'treatment_plan_sync_enabled': True, 'treatment_plan_sync_approved': True,
        }).status_code == 200
        job = _completed_sync(client, headers)
        assert job['status'] == 'failed'
    last = client.get('/api/v2/clinicians', headers=headers).json()['last_import']
    assert last['state'] == 'failed'
    assert last['summary']['http_status'] == 403
    assert last['summary']['endpoint_key'] == 'clinicians'
    assert 'mock-secret' not in str(last)



def test_clinician_only_button_job_never_fetches_or_writes_treatment_plans(tmp_path, monkeypatch):
    from test_v2_alleva_sync import _mock_alleva_server
    from time import sleep
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    assert client.post('/api/v2/clinicians/pull').status_code == 401
    assert client.post('/api/v2/clinicians/pull', headers=headers).status_code == 409
    assert client.post('/api/v2/manual-uploads/treatment-plan-aggregate', headers=headers,
        json=_aggregate('SYNTHETIC-ONLY-STAFF').model_dump(mode='json')).status_code == 201
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("UPDATE patients SET source_system='alleva_rest_api',source_patient_id='912'"))
        db.commit()
        before = db.execute(text('SELECT COUNT(*) FROM treatment_plan_versions')).scalar_one()
    with _mock_alleva_server(client_items=[{'id': '912', 'mrn': 'SYNTHETIC-ONLY-STAFF', 'facilityId': 10,
            'primaryClinician': {'id': 501, 'route': '/users/501'}}],
            staff_items=[{'id': 501, 'name': {'first': 'Synthetic', 'last': 'DirectPull'}, 'facility': {'id': 10}, 'tenant': 'synthetic', 'role': 'Clinician'}]) as (base, state):
        assert client.patch('/api/api-configuration', headers=headers, json={'api_base_url': base, 'token_url': f'{base}/token',
            'client_id': 'mock-client', 'client_secret': 'mock-secret', 'api_enabled': True,
            'treatment_plan_sync_enabled': True, 'treatment_plan_sync_approved': True}).status_code == 200
        started = client.post('/api/v2/clinicians/pull', headers=headers)
        assert started.status_code == 202
        job = started.json()
        for _ in range(100):
            job = client.get(f"/api/v2/clinicians/pull/jobs/{job['job_id']}", headers=headers).json()
            if job['status'] in {'failed', 'completed', 'completed_with_warnings'}:
                break
            sleep(.05)
        assert job['status'] == 'completed', job
        assert job['records_seen'] == job['records_written'] == 1
        assert '1 returned; 1 saved' in job['message']
        assert not any('treatment-plan' in path or 'treatment-review' in path for path in state.paths)
        assert any(path.startswith('/users?') for path in state.paths)
        assert client.get('/api/v2/clinicians/pull/latest', headers=headers).json()['job_id'] == job['job_id']
    with SessionLocal() as db:
        assert db.execute(text('SELECT COUNT(*) FROM treatment_plan_versions')).scalar_one() == before
    assert client.get('/api/v2/clinicians', headers=headers).json()['items'][0]['name'] == 'Synthetic DirectPull'


@pytest.mark.parametrize("facility,state", [(None,"missing"), ({},"missing"), ({"id":0},"missing"), ("","missing"), ({"id":999},"unmapped")])
def test_incomplete_staff_are_saved_without_inventing_facility_or_patient_links(tmp_path, monkeypatch, facility, state):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_clinicians import persist_alleva_clinicians
    staff = ({"id":501,"name":{"first":"Synthetic","last":"Incomplete"},"facility":facility,"role":"Clinician","tenant":"synthetic"},)
    with SessionLocal() as db:
        summary = persist_alleva_clinicians(db, staff, (), "2026-11-06T22:00:00Z", "synthetic:connection")
        db.commit()
        assert summary['staff_imported'] == 1
        assert summary['staff_unmapped_facility'] == 1
        assert db.execute(text('SELECT COUNT(*) FROM imported_clinician_facilities')).scalar_one() == 0
        assert db.execute(text('SELECT COUNT(*) FROM imported_primary_counselors')).scalar_one() == 0
    directory = client.get('/api/v2/clinicians', headers=headers).json()['items']
    assert len(directory) == 1
    assert directory[0]['name'] == 'Synthetic Incomplete'
    assert directory[0]['facility_status'] == state
    # Incomplete metadata never creates a facility membership for another role.
    from app.v2.api import roster_routes
    monkeypatch.setattr(roster_routes,'accessible_patient_record_ids',lambda *args:frozenset())
    with SessionLocal() as db:
        db.execute(text("UPDATE users SET role='viewer' WHERE username='admin'")); db.commit()
    response = client.get('/api/v2/clinicians', headers=headers)
    assert response.status_code == 200
    assert response.json()['items'] == []



def test_whole_directory_with_unmapped_facilities_is_retained(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_clinicians import persist_alleva_clinicians
    staff = tuple({"id":index,"name":{"first":"Synthetic","last":f"Staff{index}"},"facility":{"id":999},"role":"Clinician","tenant":"synthetic"} for index in range(1,35))
    with SessionLocal() as db:
        counts = persist_alleva_clinicians(db, staff, (), "2026-11-06T22:00:00Z", "synthetic:all-unmapped")
        db.commit()
        assert counts['staff_returned'] == counts['staff_imported'] == 34
        assert counts['staff_unmapped_facility'] == 34
        assert db.execute(text('SELECT COUNT(*) FROM imported_clinician_facilities')).scalar_one() == 0
    records = client.get('/api/v2/clinicians',headers=headers).json()['items']
    assert len(records) == 34
    assert {row['facility_status'] for row in records} == {'unmapped'}
