from __future__ import annotations

import sqlite3

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _complete_contract() -> dict[str, object]:
    return {
        "contract_version": "synthetic-alleva-v1",
        "api_base_url": "https://vendor.invalid",
        "effective_at": "2026-07-10T00:00:00+00:00",
        "vendor_documentation_url": "https://vendor.invalid/docs/synthetic-alleva-v1",
        "test_population_reference": "synthetic-test-population-v1",
        "oauth": {"token_url": "https://vendor.invalid/token", "token_auth_style": "body", "scope": "treatment-plans.read"},
        "pagination": {"limit_parameter": "limit", "offset_parameter": "offset", "maximum_page_size": 100, "maximum_records": 100, "maximum_response_bytes": 1048576},
        "rate_limit": {"maximum_requests_per_minute": 60, "retry_after_seconds": 1},
        "attachments": {"mode": "metadata_only", "download_allowed": False},
        "endpoints": {
            "clients": {"path": "/clients", "parameters": {"limit": "limit", "offset": "offset"}, "field_mappings": {"client_id": "clientId"}},
            "treatment_plans": {"path": "/treatment-plans", "parameters": {"limit": "limit", "offset": "offset", "client_id": "ClientId"}, "field_mappings": {"client_id": "clientId", "plan_id": "id"}},
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
            "api_base_url": "https://vendor.invalid",
            "token_url": "https://vendor.invalid/token",
            "token_auth_style": "body",
            "scopes": "treatment-plans.read",
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
    approval_removed = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "treatment_plan_sync_approved": False,
            "treatment_plan_endpoint_mapping_validated": False,
        },
    )
    assert approval_removed.status_code == 200
    missing_external_gate = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert missing_external_gate.status_code == 409
    assert "R3/Alleva approval" in missing_external_gate.json()["detail"]
    restored = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert restored.status_code == 200
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


def test_contract_rejects_endpoint_paths_that_can_escape_the_approved_origin(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    contract = _complete_contract()
    contract["endpoints"]["clients"]["path"] = "/https://attacker.invalid/clients"

    response = client.post("/api/v2/alleva-sync/contracts", headers=headers, json=contract)

    assert response.status_code == 422


def test_contract_accepts_published_alleva_v1_review_paths(tmp_path, monkeypatch) -> None:
    # Given: the review paths published in Alleva's v1 Swagger definition.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    contract = _complete_contract()
    contract["endpoints"]["reviews"] = {
        "path": "/treatment-reviews",
        "parameters": {"limit": "Limit", "offset": "Cursor"},
        "field_mappings": {"review_id": "id"},
    }
    contract["endpoints"]["review_detail"] = {
        "path": "/treatment-reviews/{review_id}",
        "parameters": {},
        "field_mappings": {"review_date": "createdDated"},
    }

    # When: an administrator records the versioned contract.
    response = client.post("/api/v2/alleva-sync/contracts", headers=headers, json=contract)

    # Then: the official non-nested review routes are accepted.
    assert response.status_code == 201, response.text


def test_contract_rejects_lowercase_or_missing_treatment_plan_client_query(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    for invalid_parameters in (
        {"limit": "Limit", "offset": "Cursor"},
        {"limit": "Limit", "offset": "Cursor", "client_id": "clientId"},
    ):
        contract = _complete_contract()
        contract["contract_version"] = f"invalid-{len(invalid_parameters)}-{invalid_parameters.get('client_id', 'missing')}"
        contract["endpoints"]["treatment_plans"]["parameters"] = invalid_parameters

        response = client.post("/api/v2/alleva-sync/contracts", headers=headers, json=contract)

        assert response.status_code == 422
        assert response.json()["detail"] == "The Alleva contract is incomplete or invalid"


def test_corrupt_contract_is_redacted_and_safely_denied(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    approved = client.post("/api/v2/alleva-sync/contracts", headers=headers, json=_complete_contract())
    assert approved.status_code == 201
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute(
            "UPDATE alleva_contract_approvals SET encrypted_contract_json=? WHERE contract_version=?",
            (b"not-an-encrypted-contract-patient-name-canary", "synthetic-alleva-v1"),
        )
        database.commit()
    denied = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert denied.status_code == 409
    assert "contract" in denied.json()["detail"].lower()
    assert "patient-name-canary" not in denied.text
