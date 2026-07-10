from __future__ import annotations

import sqlite3

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _complete_contract() -> dict[str, object]:
    return {
        "contract_version": "synthetic-alleva-v1",
        "effective_at": "2026-07-10T00:00:00+00:00",
        "vendor_documentation_url": "https://vendor.invalid/docs/synthetic-alleva-v1",
        "test_population_reference": "synthetic-test-population-v1",
        "oauth": {"token_auth_style": "body", "scope": "treatment-plans.read"},
        "pagination": {"limit_parameter": "limit", "offset_parameter": "offset", "maximum_page_size": 100},
        "rate_limit": {"maximum_requests_per_minute": 60, "retry_after_seconds": 1},
        "attachments": {"mode": "metadata_only", "download_allowed": False},
        "endpoints": {
            "clients": {"path": "/clients", "parameters": {"limit": "limit", "offset": "offset"}, "field_mappings": {"client_id": "clientId"}},
            "treatment_plans": {"path": "/treatment-plans", "parameters": {"limit": "limit", "offset": "offset"}, "field_mappings": {"client_id": "clientId", "plan_id": "id"}},
            "treatment_plan_detail": {"path": "/treatment-plans/{plan_id}", "parameters": {}, "field_mappings": {"signature_date": "staffSignatureDate"}},
            "diagnoses": {"path": "/treatment-plans/{plan_id}/diagnoses", "parameters": {}, "field_mappings": {"description": "diagnosisDescription"}},
            "reviews": {"path": "/treatment-plans/{plan_id}/reviews", "parameters": {}, "field_mappings": {"review_id": "id"}},
            "review_detail": {"path": "/treatment-plans/{plan_id}/reviews/{review_id}", "parameters": {}, "field_mappings": {"review_date": "reviewDate"}},
        },
    }


def test_contract_gate_blocks_mutable_checkbox_bypass_and_encrypts_approval(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_secret": "synthetic-contract-secret",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert saved.status_code == 200
    blocked = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert blocked.status_code == 409
    assert "approved versioned contract" in blocked.json()["detail"].lower()
    approved = client.post("/api/v2/alleva-sync/contracts", headers=headers, json=_complete_contract())
    assert approved.status_code == 201, approved.text
    assert approved.json()["contract_version"] == "synthetic-alleva-v1"
    assert approved.json()["contract_sha256"]
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        encrypted = database.execute(
            "SELECT encrypted_contract_json FROM alleva_contract_approvals WHERE contract_version=?",
            ("synthetic-alleva-v1",),
        ).fetchone()[0]
    assert b"synthetic-contract-secret" not in encrypted
    assert b"patient-name-canary" not in encrypted
    assert encrypted.startswith(b"IZCNA1:")
    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert "synthetic-contract-secret" not in str(audit)
    assert "patient-name-canary" not in str(audit)
