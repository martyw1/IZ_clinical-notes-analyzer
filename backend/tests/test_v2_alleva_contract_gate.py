from __future__ import annotations

import sqlite3

import pytest

from app.v2.api.models import AllevaContractApprovalIn
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
            "clients": {"path": "/clients", "parameters": {"limit": "limit", "offset": "offset"}, "field_mappings": {"client_id": "clientId", "mrn": "mrn"}},
            "treatment_plans": {"path": "/treatment-plans", "parameters": {"limit": "limit", "offset": "offset", "client_id": "ClientId"}, "field_mappings": {"client_id": "clientId", "plan_id": "id"}},
            "treatment_plan_detail": {"path": "/treatment-plans/{plan_id}", "parameters": {}, "field_mappings": {"signature_date": "staffSignatureDate"}},
            "diagnoses": {"path": "/treatment-plans/{plan_id}/diagnoses", "parameters": {}, "field_mappings": {"description": "diagnosisDescription"}},
            "reviews": {"path": "/treatment-plans/{plan_id}/reviews", "parameters": {}, "field_mappings": {"review_id": "id"}},
            "review_detail": {"path": "/treatment-plans/{plan_id}/reviews/{review_id}", "parameters": {}, "field_mappings": {"review_date": "reviewDate"}},
        },
    }


def test_operational_sync_automatically_records_encrypted_builtin_mapping(tmp_path, monkeypatch) -> None:
    from app.v2.services.alleva_sync import AllevaSyncResult
    import app.v2.services.jobs as jobs

    monkeypatch.setattr(
        jobs,
        "run_treatment_plan_sync",
        lambda *_args, **_kwargs: AllevaSyncResult(0, 0, 0, 0, 0, ()),
    )
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_id": "synthetic-client-id",
            "client_secret": "synthetic-contract-secret",
            "api_base_url": "https://vendor.invalid",
            "token_url": "https://vendor.invalid/token",
            "token_auth_style": "body",
            "scopes": "treatment-plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
        },
    )
    assert saved.status_code == 200
    started = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert started.status_code == 202, started.text
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        version, encrypted = database.execute(
            "SELECT contract_version,encrypted_contract_json FROM alleva_contract_approvals ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert version.startswith("alleva-rest-v1-built-in-")
    assert b"synthetic-contract-secret" not in encrypted
    assert b"patient-name-canary" not in encrypted
    assert encrypted.startswith(b"IZCNA1:")
    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert any(item["action"] == "alleva.mapping.automatic" for item in audit)
    assert "synthetic-contract-secret" not in str(audit)
    assert "patient-name-canary" not in str(audit)


def test_contract_rejects_endpoint_paths_that_can_escape_the_approved_origin(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    contract = _complete_contract()
    contract["endpoints"]["clients"]["path"] = "/https://attacker.invalid/clients"

    with pytest.raises(ValueError):
        _store_contract(contract)


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

    _store_contract(contract)


def _store_contract(payload: dict[str, object]) -> None:
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_contracts import approve_contract

    with SessionLocal() as database:
        approve_contract(database, AllevaContractApprovalIn.model_validate(payload), 1)


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

        with pytest.raises(ValueError):
            _store_contract(contract)


def test_corrupt_manual_contract_is_redacted_and_replaced_by_builtin_mapping(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "api_base_url": "https://vendor.invalid",
            "token_url": "https://vendor.invalid/token",
            "scopes": "treatment-plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
        },
    )
    assert configured.status_code == 200
    _store_contract(_complete_contract())
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute(
            "UPDATE alleva_contract_approvals SET encrypted_contract_json=? WHERE contract_version=?",
            (b"not-an-encrypted-contract-patient-name-canary", "synthetic-alleva-v1"),
        )
        database.commit()
    captured_contracts = []

    def capture_without_starting(_actor_id, _actor_role, contract):
        captured_contracts.append(contract)
        raise ValueError("synthetic active job")

    import app.v2.api.alleva_sync_routes as alleva_sync_routes

    monkeypatch.setattr(alleva_sync_routes.job_service, "create_treatment_plan_sync_job", capture_without_starting)
    response = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert response.status_code == 409
    assert captured_contracts[0].contract_version.startswith("alleva-rest-v1-built-in-")
    assert "patient-name-canary" not in response.text


def test_sync_requires_client_id_before_mapping_or_job_creation(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_secret": "synthetic-secret",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
        },
    )
    assert saved.status_code == 200

    response = client.post("/api/v2/alleva-sync/run", headers=headers)

    assert response.status_code == 409
    assert "client ID" in response.json()["detail"]
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM alleva_contract_approvals").fetchone() == (0,)
        assert database.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)


def test_builtin_mapping_replaces_valid_custom_contract_and_refreshes_changed_limits(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "api_base_url": "https://vendor.invalid",
            "token_url": "https://vendor.invalid/token",
            "scopes": "treatment-plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "pagination_limit": 100,
            "sync_limit": 250,
            "requests_per_minute": 600,
        },
    )
    assert configured.status_code == 200
    custom = _complete_contract()
    custom["contract_version"] = "alleva-rest-v1-built-in-2026-07-13-spoof"
    _store_contract(custom)

    import app.v2.api.alleva_sync_routes as alleva_sync_routes

    captured_contracts = []

    def capture_without_starting(_actor_id, _actor_role, contract):
        captured_contracts.append(contract)
        raise ValueError("synthetic active job")

    monkeypatch.setattr(alleva_sync_routes.job_service, "create_treatment_plan_sync_job", capture_without_starting)
    assert client.post("/api/v2/alleva-sync/run", headers=headers).status_code == 409
    assert captured_contracts[-1].payload.endpoints["clients"].field_mappings["client_id"] == "id"
    assert captured_contracts[-1].contract_version != custom["contract_version"]

    changed = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={"pagination_limit": 25, "sync_limit": 75, "requests_per_minute": 900},
    )
    assert changed.status_code == 200
    assert client.post("/api/v2/alleva-sync/run", headers=headers).status_code == 409
    refreshed = captured_contracts[-1].payload
    assert refreshed.pagination.maximum_page_size == 75
    assert refreshed.pagination.maximum_records == 75
    assert refreshed.rate_limit.maximum_requests_per_minute == 900
