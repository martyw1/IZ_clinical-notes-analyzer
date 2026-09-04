from __future__ import annotations

import pytest
from sqlalchemy import text

from test_v2_plan_version_actions import _counts, _import, runtime


def _user(runtime, role):
    client, admin_headers = runtime
    created = client.post("/api/users", headers=admin_headers, json={
        "username": f"identity-{role}", "password": "SyntheticTemporaryPass1", "role": role,
    })
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"username": f"identity-{role}", "password": "SyntheticTemporaryPass1"})
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = client.post("/api/users/me/change-password", headers=token, json={
        "current_password": "SyntheticTemporaryPass1", "new_password": "SyntheticActivePass2",
    })
    assert changed.status_code == 200
    login = client.post("/api/auth/login", json={"username": f"identity-{role}", "password": "SyntheticActivePass2"})
    return created.json()["id"], {"Authorization": f"Bearer {login.json()['access_token']}"}


def _other_facility_version(version_id):
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        facility = db.execute(text(
            "INSERT INTO facilities(facility_key,display_name,timezone,is_active,created_at,updated_at) "
            "VALUES('identity-other','Synthetic other','UTC',1,'2026-09-03','2026-09-03')"
        )).lastrowid
        patient = db.execute(text(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(:facility,'IDENTITY-001','manual_upload','active','2026-09-03','2026-09-03')"
        ), {"facility": facility}).lastrowid
        version = db.execute(text(
            "INSERT INTO treatment_plan_versions(patient_id,source_system,source_record_id,version_ordinal,"
            "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) "
            "SELECT :patient,source_system,source_record_id,1,normalized_snapshot_encrypted,content_sha256,"
            "evidence_sha256,imported_at FROM treatment_plan_versions WHERE id=:id"
        ), {"patient": patient, "id": version_id}).lastrowid
        db.commit()
        return {"plan_version_id": version, "patient_record_id": patient, "source_mode": "manual_upload"}


@pytest.mark.parametrize("operation", ["detail", "export", "action", "refresh"])
def test_same_mrn_allowed_row_does_not_authorize_other_facility(runtime, monkeypatch, operation):
    # Given: same MRN in allowed and denied facilities.
    first = _import(runtime)
    _, headers = _user(runtime, "office_manager")
    forbidden = _other_facility_version(first["plan_version_id"])
    client, _ = runtime
    before = _counts()
    def forbid_decode(*_args, **_kwargs):
        raise AssertionError("Unauthorized row reached decryption")
    monkeypatch.setattr("app.v2.services.clinical_snapshot_codec.ClinicalSnapshotCodec.decode_plan", forbid_decode)
    # When: a concrete disallowed row is targeted.
    if operation == "detail":
        response = client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers, params=forbidden)
    elif operation == "export":
        response = client.get("/api/v2/exports/IDENTITY-001/checklist-evidence.csv", headers=headers, params=forbidden)
    elif operation == "action":
        response = client.post("/api/v2/treatment-plans/IDENTITY-001/manager-actions", headers=headers,
                               json=forbidden | {"criterion_id": "confirm_current_loc", "action": "approve"})
    else:
        response = client.post("/api/v2/treatment-plans/IDENTITY-001/evaluations/refresh", headers=headers, params=forbidden)
    # Then: exact authorization rejects before decrypt or clinical writes.
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"
    assert _counts() == before


def test_list_returns_only_real_authorized_latest_version_ids(runtime):
    # Given: one old version, its replacement, sibling plan, and a denied row.
    first = _import(runtime)
    latest = _import(runtime, marker="newer")
    sibling = _import(runtime, plan_id="plan-b")
    _, headers = _user(runtime, "office_manager")
    forbidden = _other_facility_version(first["plan_version_id"])
    client, _ = runtime
    # When: current treatment-plan rows are listed.
    response = client.get("/api/v2/treatment-plans", headers=headers)
    # Then: latest identity is correlated, positive, and scoped to exact rows.
    assert response.status_code == 200
    rows = response.json()["items"]
    assert {row["plan_version_id"] for row in rows} == {latest["plan_version_id"], sibling["plan_version_id"]}
    assert all(row["patient_record_id"] == first["patient_record_id"] for row in rows)
    assert forbidden["plan_version_id"] not in {row["plan_version_id"] for row in rows}


def test_legacy_request_can_resolve_exactly_one_authorized_candidate(runtime):
    selected = _import(runtime)
    _, headers = _user(runtime, "office_manager")
    _other_facility_version(selected["plan_version_id"])
    client, _ = runtime
    response = client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers)
    assert response.status_code == 200
    assert response.json()["plan_version_id"] == selected["plan_version_id"]
    saved = client.post("/api/v2/treatment-plans/IDENTITY-001/manager-actions", headers=headers,
                        json={"criterion_id": "confirm_current_loc", "action": "comment"})
    assert saved.status_code == 200
    assert saved.json()["plan_version_id"] == selected["plan_version_id"]


def test_assignment_rejects_counselor_without_exact_facility_membership(runtime):
    # Given: an active counselor with no patient-facility membership.
    selected = _import(runtime)
    _user(runtime, "counselor")
    client, headers = runtime
    # When: an admin tries to assign the patient.
    response = client.put("/api/patient-assignments/IDENTITY-001/identity-counselor", headers=headers,
                          params={"patient_record_id": selected["patient_record_id"]})
    # Then: the API does not report a usable grant it cannot authorize.
    assert response.status_code == 409


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v2/treatment-plans/IDENTITY-001"),
    ("get", "/api/v2/exports/IDENTITY-001/checklist-evidence.csv"),
    ("post", "/api/v2/treatment-plans/IDENTITY-001/manager-actions"),
])
def test_unauthenticated_identity_routes_remain_unauthorized(runtime, method, path):
    # Given: a valid selected identity but no session.
    selected = _import(runtime)
    client, _ = runtime
    # When: a protected identity endpoint is called anonymously.
    response = getattr(client, method)(path, params=selected)
    # Then: authentication remains mandatory.
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["get", "delete"])
def test_source_document_mismatched_version_never_downloads_or_deletes(runtime, method):
    # Given: an archived source document and a different selected version.
    client, headers = runtime
    imported = client.post("/api/v2/manual-uploads/treatment-plan-file", headers=headers,
                           data={"patient_id": "IDENTITY-001"},
                           files={"file": ("synthetic.txt", "Patient ID: IDENTITY-001\nIntervention: Synthetic source.", "text/plain")})
    assert imported.status_code == 201
    source_id = imported.json()["source_file_id"]
    selected = _import(runtime)
    path = f"/api/v2/treatment-plans/IDENTITY-001/source-documents/{source_id}"
    if method == "get":
        path += "/download"
    # When: a caller combines the unrelated version and document identity.
    response = getattr(client, method)(path, params=selected, headers=headers)
    # Then: it is rejected before any source bytes or deletion effects.
    assert response.status_code == 404
    actual = client.get(f"/api/v2/treatment-plans/IDENTITY-001/source-documents/{source_id}/download", headers=headers)
    assert actual.status_code == 200
    assert actual.content == b"Patient ID: IDENTITY-001\nIntervention: Synthetic source."


def test_counselor_assignment_cannot_authorize_same_mrn_other_source(runtime, monkeypatch):
    # Given: only the manual-source patient row is assigned to this counselor.
    manual = _import(runtime)
    other = _import(runtime, source="alleva_rest_api")
    user_id, counselor_headers = _user(runtime, "counselor")
    client, admin_headers = runtime
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        facility = db.execute(text("SELECT facility_id FROM patients WHERE id=:id"), {"id": manual["patient_record_id"]}).scalar_one()
    assert client.put(f"/api/users/{user_id}/facilities/{facility}", headers=admin_headers).status_code == 200
    assigned = client.put("/api/patient-assignments/IDENTITY-001/identity-counselor", headers=admin_headers,
                          params={"patient_record_id": manual["patient_record_id"]})
    assert assigned.status_code == 200
    assert client.get("/api/v2/treatment-plans/IDENTITY-001", params=manual, headers=counselor_headers).status_code == 200
    def forbid_decode(*_args, **_kwargs):
        raise AssertionError("Cross-source counselor target reached decryption")
    monkeypatch.setattr("app.v2.services.clinical_snapshot_codec.ClinicalSnapshotCodec.decode_plan", forbid_decode)
    # When: the assigned counselor selects the other source row with the same MRN.
    denied = client.get("/api/v2/treatment-plans/IDENTITY-001", params=other, headers=counselor_headers)
    # Then: source collision does not carry the assignment across rows.
    assert denied.status_code == 403
