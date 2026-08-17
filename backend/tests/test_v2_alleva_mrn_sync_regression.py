from __future__ import annotations

import sqlite3

from test_v2_auth_rbac import _create_user
from test_v2_alleva_sync import JsonValue, _completed_sync, _mock_alleva_server
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_sync_uses_true_mrn_and_imports_every_unpaged_global_plan_for_every_patient(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items: list[dict[str, JsonValue]] = [
        {"id": "source-101", "mrn": "MRN-0042", "name": {"clientFullName": "Alex Example"}, "status": "Active", "levelOfCare": "PHP", "email": "alex.synthetic@example.invalid"},
        {"id": "source-202", "mrn": "MRN-0099", "clientFullName": "Blair Example", "status": "Discharged"},
        {"id": "source-303", "mrn": "MRN-0123", "ClientFullName": "Casey Example", "status": "Inactive"},
        {"id": "source-404", "mrn": "MRN-0555", "firstName": "Devon", "lastName": "Example", "status": "Active", "levelOfCare": "IOP"},
    ]
    plan_counts = {"source-101": 6, "source-202": 8, "source-303": 2}
    plan_items: list[dict[str, JsonValue]] = []
    index = 0
    for source_patient_id, count in plan_counts.items():
        for _ in range(count):
            index += 1
            plan_items.append({
                "id": f"plan-{index}",
                "client": {"id": source_patient_id, "route": f"/clients/{source_patient_id}"},
                "startDate": f"2026-01-{index:02d}T09:00:00Z",
                "lastModified": f"2026-07-{index:02d}T12:00:00Z",
            })
    plan_items.append({
        "id": "plan-unlinked",
        "client": {"id": "source-not-returned", "route": "/clients/source-not-returned"},
        "startDate": "2025-12-01T09:00:00Z",
        "lastModified": "2026-07-17T12:00:00Z",
    })
    plan_items.append({
        "id": "plan-ownerless",
        "startDate": "2025-11-01T09:00:00Z",
        "lastModified": "2026-07-18T12:00:00Z",
    })

    with _mock_alleva_server(
        client_items=client_items,
        plan_items=plan_items,
        global_plan_collection=True,
        ignore_collection_cursor=True,
    ) as (base_url, state):
        configured = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={
                "api_base_url": base_url,
                "token_url": f"{base_url}/token",
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
                "scopes": "plans.read",
                "pagination_limit": 3,
                "sync_limit": 20,
                "requests_per_minute": 10_000,
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
            },
        )
        assert configured.status_code == 200
        synced = _completed_sync(client, headers)

    assert synced["status"] == "completed"
    assert synced["records_written"] == 18
    plan_paths = [path for path in state.paths if path.startswith("/treatment-plans?")]
    assert plan_paths == [
        "/treatment-plans?Limit=20&Cursor=0&api-version=1.0&StartDate=2000-01-01T16%3A03",
    ]

    patient_roster = client.get("/api/v2/patient-roster", headers=headers).json()["items"]
    assert {item["mrn"]: len(item["treatment_plans"]) for item in patient_roster} == {
        "MRN-0042": 6,
        "MRN-0555": 0,
        "MRN-0099": 8,
        "MRN-0123": 2,
    }
    assert {item["mrn"]: item["full_name"] for item in patient_roster} == {
        "MRN-0042": "Alex Example",
        "MRN-0555": "Devon Example",
        "MRN-0099": "Blair Example",
        "MRN-0123": "Casey Example",
    }
    plan_roster = client.get("/api/v2/treatment-plan-roster", headers=headers).json()["items"]
    assert len(plan_roster) == 18
    assert {item["mrn"] for item in plan_roster} == {"", "MRN-0042", "MRN-0099", "MRN-0123"}
    assert {item["full_name"] for item in plan_roster if item["mrn"] == "MRN-0042"} == {"Alex Example"}
    assert next(item for item in plan_roster if item["treatment_plan_id"] == "plan-1")["last_updated"] == "2026-07-01T12:00:00Z"
    assert next(item for item in plan_roster if item["mrn"] == "MRN-0042")["initial_treatment_plan_date"] == "2026-01-01T09:00:00Z"
    unlinked = next(item for item in plan_roster if item["treatment_plan_id"] == "plan-unlinked")
    assert unlinked["mrn"] == ""
    assert unlinked["linked_to_mrn"] is False
    assert unlinked["full_name"] == ""
    assert unlinked["patient_key"].startswith("unlinked-plan-")
    assert "source-not-returned" not in str(plan_roster)
    detail = client.get(
        f"/api/v2/treatment-plans/{unlinked['patient_key']}/plan-unlinked?source_mode=alleva_rest_api",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["patient_display_label"] == "Not linked to an MRN"
    ownerless = next(item for item in plan_roster if item["treatment_plan_id"] == "plan-ownerless")
    assert ownerless["mrn"] == ""
    assert ownerless["linked_to_mrn"] is False
    assert ownerless["patient_key"].startswith("unlinked-plan-")
    assert ownerless["patient_key"] != unlinked["patient_key"]
    linked_detail = client.get(
        "/api/v2/treatment-plans/MRN-0042/plan-1?source_mode=alleva_rest_api",
        headers=headers,
    )
    assert linked_detail.status_code == 200
    assert linked_detail.json()["patient_full_name"] == "Alex Example"
    patient_detail = client.get(
        "/api/v2/patients/MRN-0555?source_mode=alleva_rest_api",
        headers=headers,
    )
    assert patient_detail.status_code == 200
    assert patient_detail.json()["full_name"] == "Devon Example"
    assert patient_detail.json()["current_level_of_care"] == "IOP"
    assert patient_detail.json()["treatment_plans"] == []
    assert patient_detail.json()["patient_record"]["mrn"] == "MRN-0555"
    _, counselor_headers = _create_user(client, headers, "patient-detail-counselor", "counselor")
    denied = client.get("/api/v2/patients/MRN-0042?source_mode=alleva_rest_api", headers=counselor_headers)
    assert denied.status_code == 403
    assert "source-101" not in str(patient_roster)
    assert "source-202" not in str(plan_roster)

    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        identities = database.execute(
            "SELECT canonical_client_id,source_patient_id FROM patients "
            "WHERE source_system='alleva_rest_api' ORDER BY canonical_client_id"
        ).fetchall()
        encrypted_snapshots = database.execute(
            "SELECT snapshot_schema_version,snapshot_encrypted FROM patient_snapshot_versions ORDER BY id"
        ).fetchall()
    assert identities[:4] == [
        ("MRN-0042", "source-101"),
        ("MRN-0099", "source-202"),
        ("MRN-0123", "source-303"),
        ("MRN-0555", "source-404"),
    ]
    assert all(identity[0].startswith("unlinked-plan-") for identity in identities[4:])
    assert {identity[1] for identity in identities[4:]} == {None}
    assert len(encrypted_snapshots) == 4
    assert {row[0] for row in encrypted_snapshots} == {1}
    assert all(bytes(row[1]).startswith(b"IZCNA1:") for row in encrypted_snapshots)
    assert b"Alex Example" not in database_path.read_bytes()
    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert "Alex Example" not in str(audit)
    for protected_value in (
        "MRN-0042",
        "MRN-0099",
        "MRN-0123",
        "MRN-0555",
        "source-101",
        "source-202",
        "source-303",
        "source-404",
    ):
        assert protected_value not in str(audit)


def test_patient_full_name_uses_authoritative_fields_then_structured_name() -> None:
    from app.v2.services.patient_snapshot_store import patient_full_name

    assert patient_full_name({"name": {"clientFullName": "Nested Client Name"}, "fullName": "Ignored"}) == "Nested Client Name"
    assert patient_full_name({"clientFullName": "Direct Client Name", "fullName": "Ignored"}) == "Direct Client Name"
    assert patient_full_name({"ClientFullName": "Pascal Client Name", "fullName": "Ignored"}) == "Pascal Client Name"
    assert patient_full_name({"fullName": "Preferred Name", "firstName": "Ignored"}) == "Preferred Name"
    assert patient_full_name({"name": "Top Level Name", "firstName": "Ignored"}) == "Top Level Name"
    assert patient_full_name({
        "firstName": "Synthetic",
        "middleName": "Q",
        "lastName": "Patient",
        "suffix": "Jr.",
    }) == "Synthetic Q Patient Jr."
    assert patient_full_name({}) == "Name unavailable"


def test_reconciliation_rekeys_legacy_patient_without_changing_child_foreign_keys(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_patient_identity import (
        AllevaPatientObservation,
        reconcile_sync_patients,
    )

    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        facility_id = database.execute("SELECT id FROM facilities WHERE facility_key='r3-default'").fetchone()[0]
        database.execute(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(?, 'source-legacy', 'alleva_rest_api', 'active', '2026-07-01', '2026-07-01')",
            (facility_id,),
        )
        patient_id = database.execute(
            "SELECT id FROM patients WHERE canonical_client_id='source-legacy'"
        ).fetchone()[0]
        database.execute(
            "INSERT INTO treatment_plan_versions(patient_id,source_system,source_record_id,version_ordinal,"
            "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) "
            "VALUES(?, 'alleva_rest_api', 'legacy-plan', 1, X'00', 'a', 'b', '2026-07-01')",
            (patient_id,),
        )
        database.commit()

    with SessionLocal() as database:
        reconcile_sync_patients(
            database,
            None,
            (AllevaPatientObservation("source-legacy", "MRN-0700", "active"),),
            frozenset(("source-legacy",)),
            False,
            "2026-08-10T20:00:00+00:00",
        )

    with sqlite3.connect(database_path) as database:
        patient = database.execute(
            "SELECT id,canonical_client_id,source_patient_id FROM patients WHERE id=?",
            (patient_id,),
        ).fetchone()
        child_patient_id = database.execute(
            "SELECT patient_id FROM treatment_plan_versions WHERE source_record_id='legacy-plan'"
        ).fetchone()[0]
    assert patient == (patient_id, "MRN-0700", "source-legacy")
    assert child_patient_id == patient_id
