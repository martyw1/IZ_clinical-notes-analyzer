import json
from sqlalchemy import text, select
from test_v2_evaluation_persistence import _aggregate
from test_v2_manual_patient_correction import _fresh_client, _auth_headers
from test_v2_plan_version_authorization import _user


def setup_case(tmp_path,monkeypatch):
    client=_fresh_client(tmp_path,monkeypatch);headers=_auth_headers(client)
    saved=client.post('/api/v2/manual-uploads/treatment-plan-aggregate',headers=headers,json=_aggregate('SYNTHETIC-LINK').model_dump(mode='json')).json()
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_clinicians import persist_alleva_clinicians
    with SessionLocal() as db:
        persist_alleva_clinicians(db, tuple({'id':i,'name':{'first':'Synthetic','last':name},'tenant':'synthetic','role':'Clinician'} for i,name in [(501,'Local'),(502,'Source')]), (), '2026-11-06T12:00:00Z','synthetic:assignments')
        db.commit()
        before=db.execute(text('SELECT id,content_sha256,evidence_sha256 FROM treatment_plan_versions ORDER BY id')).all()
    directory=client.get('/api/v2/clinicians',headers=headers).json()['items']
    ids={row['name']:row['id'] for row in directory}
    return client,headers,saved,ids,before


def test_local_assignment_controls_all_plan_views_and_survives_source_updates(tmp_path,monkeypatch):
    client,headers,saved,ids,before=setup_case(tmp_path,monkeypatch)
    patient=saved['patient_record_id'];url=f'/api/v2/patient-records/{patient}/clinician-assignment'
    from app.v2.db import SessionLocal
    from app.v2.models import ImportedCounselor
    from app.v2.services.imported_counselors import save_primary_counselor, PrimaryCounselorEvidence
    with SessionLocal() as db:
        source=db.get(ImportedCounselor,ids['Synthetic Source'])
        evidence=PrimaryCounselorEvidence(source.source_scope,source.staff_id,source.display_name)
        save_primary_counselor(db,patient,evidence,'2026-10-01T12:00:00Z');db.commit()
    original=client.get(url,headers=headers).json()
    assert original['origin']=='source' and original['revision']==0
    changed=client.put(url,headers=headers,json={'mode':'local','clinician_id':ids['Synthetic Local'],'expected_revision':0})
    assert changed.status_code==200,changed.text
    assert changed.json()['origin']=='local' and changed.json()['revision']==1
    with SessionLocal() as db:
        save_primary_counselor(db,patient,evidence,'2026-11-06T14:00:00Z');db.commit()
    assert client.get(url,headers=headers).json()['clinician_id']==ids['Synthetic Local']
    assert client.get('/api/v2/patient-roster',headers=headers).json()['items'][0]['primary_counselor_name']=='Synthetic Local'
    assert client.get('/api/v2/treatment-plan-roster',headers=headers).json()['items'][0]['primary_counselor_name']=='Synthetic Local'
    assert len(client.get('/api/v2/treatment-plan-roster',headers=headers,params={'primary_clinician_id':ids['Synthetic Local']}).json()['items'])==1
    assert client.put(url,headers=headers,json={'clinician_id':ids['Synthetic Source'],'expected_revision':0}).status_code==409
    cleared=client.put(url,headers=headers,json={'mode':'local','clinician_id':None,'expected_revision':1}).json()
    assert cleared['origin']=='local' and cleared['clinician_id'] is None
    assert client.get('/api/v2/treatment-plan-roster',headers=headers).json()['items'][0]['primary_counselor_id'] is None
    restored=client.put(url,headers=headers,json={'mode':'source','clinician_id':None,'expected_revision':2}).json()
    assert restored['origin']=='source' and restored['clinician_id']==ids['Synthetic Source']
    with SessionLocal() as db:
        assert db.execute(text('SELECT id,content_sha256,evidence_sha256 FROM treatment_plan_versions ORDER BY id')).all()==before
        assert db.execute(text('SELECT COUNT(*) FROM patient_assignments')).scalar_one()==0
        events=db.execute(text("SELECT details FROM audit_logs WHERE action LIKE 'clinician.assignment.%' ORDER BY id")).scalars().all()
        assert len(events)==3
        assert 'Synthetic Local' not in str(events) and 'SYNTHETIC-LINK' not in str(events)
        assert db.execute(text('SELECT assigned_at_utc FROM local_clinician_assignments')).scalar_one().endswith('+00:00')


def test_assignment_search_and_writes_enforce_exact_record_scope_and_role(tmp_path,monkeypatch):
    client,headers,saved,ids,_=setup_case(tmp_path,monkeypatch)
    patient=saved['patient_record_id'];url=f'/api/v2/patient-records/{patient}/clinician-assignment'
    assert client.put(url,json={'clinician_id':ids['Synthetic Local'],'expected_revision':0}).status_code==401
    _,viewer=_user((client,headers),'viewer')
    assert client.put(url,headers=viewer,json={'clinician_id':ids['Synthetic Local'],'expected_revision':0}).status_code==403
    assert client.post('/api/v2/clinician-assignment/patients/search',headers=viewer,json={'query':'SYNTHETIC'}).status_code==403
    assert client.put(url,headers=headers,json={'clinician_id':999999,'expected_revision':0}).status_code==403
    assert client.put(url,headers=headers,json={'clinician_id':ids['Synthetic Local'],'expected_revision':True}).status_code==422
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        primary=db.execute(text('SELECT facility_id FROM patients WHERE id=:id'),{'id':patient}).scalar_one()
        sibling=db.execute(text("INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) VALUES(:f,'SYNTHETIC-LINK','alleva_rest_api','active','2026-11-06','2026-11-06')"),{'f':primary}).lastrowid
        hidden=db.execute(text("INSERT INTO facilities(facility_key,display_name,timezone,is_active,created_at,updated_at) VALUES('link-hidden','Synthetic hidden','UTC',1,'2026-11-06','2026-11-06')")).lastrowid
        denied=db.execute(text("INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) VALUES(:f,'SYNTHETIC-HIDDEN','manual_upload','active','2026-11-06','2026-11-06')"),{'f':hidden}).lastrowid
        db.commit()
    found=client.post('/api/v2/clinician-assignment/patients/search',headers=headers,json={'query':'SYNTHETIC-LINK'}).json()['items']
    assert {row['patient_record_id'] for row in found}=={patient,sibling}
    assert client.put(f'/api/v2/patient-records/{denied}/clinician-assignment',headers=headers,json={'clinician_id':ids['Synthetic Local'],'expected_revision':0}).status_code==403
    assert client.put(url,headers=headers,json={'clinician_id':ids['Synthetic Local'],'expected_revision':0}).status_code==200
    assert client.get(f'/api/v2/patient-records/{sibling}/clinician-assignment',headers=headers).json()['clinician_id'] is None
    assert client.post('/api/v2/clinician-assignment/patients/search',headers=headers,json={'query':'SYNTHETIC-HIDDEN'}).json()['items']==[]
