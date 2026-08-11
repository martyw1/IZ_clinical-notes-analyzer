from __future__ import annotations

import sqlite3

from test_v2_alleva_sync import JsonValue, _completed_sync, _mock_alleva_server
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_sync_uses_true_mrn_and_imports_every_global_plan_for_all_lifecycles(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items: list[dict[str, JsonValue]] = [
        {"id": "source-101", "mrn": "MRN-0042", "status": "Active"},
        {"id": "source-202", "mrn": "MRN-0099", "status": "Discharged"},
    ]
    plan_items: list[dict[str, JsonValue]] = [
        {
            "id": f"plan-{index}",
            "client": {
                "id": "source-101" if index <= 5 else "source-202",
                "route": f"/clients/{'source-101' if index <= 5 else 'source-202'}",
            },
            "lastModified": f"2026-07-{index:02d}T12:00:00Z",
        }
        for index in range(1, 9)
    ]

    with _mock_alleva_server(
        client_items=client_items,
        plan_items=plan_items,
        global_plan_collection=True,
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
    assert synced["records_written"] == 8
    plan_paths = [path for path in state.paths if path.startswith("/treatment-plans?")]
    assert plan_paths == [
        "/treatment-plans?Limit=3&Cursor=0&api-version=1.0&StartDate=2000-01-01T16%3A03",
        "/treatment-plans?Limit=3&Cursor=3&api-version=1.0&StartDate=2000-01-01T16%3A03",
        "/treatment-plans?Limit=3&Cursor=6&api-version=1.0&StartDate=2000-01-01T16%3A03",
    ]

    patient_roster = client.get("/api/v2/patient-roster", headers=headers).json()["items"]
    assert [(item["mrn"], len(item["treatment_plans"])) for item in patient_roster] == [
        ("MRN-0042", 5),
        ("MRN-0099", 3),
    ]
    plan_roster = client.get("/api/v2/treatment-plan-roster", headers=headers).json()["items"]
    assert len(plan_roster) == 8
    assert {item["mrn"] for item in plan_roster} == {"MRN-0042", "MRN-0099"}
    assert "source-101" not in str(patient_roster)
    assert "source-202" not in str(plan_roster)

    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        identities = database.execute(
            "SELECT canonical_client_id,source_patient_id FROM patients "
            "WHERE source_system='alleva_rest_api' ORDER BY canonical_client_id"
        ).fetchall()
    assert identities == [("MRN-0042", "source-101"), ("MRN-0099", "source-202")]


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
