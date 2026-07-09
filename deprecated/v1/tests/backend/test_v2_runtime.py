from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _fresh_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(tmp_path / "app-data"))
    for module_name in tuple(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)
    from app.main import create_app

    return TestClient(create_app())


def test_version_endpoint_reports_v2_when_runtime_starts(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    response = client.get("/api/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "2.0.0-beta.1"
    assert payload["release_channel"] == "beta-local-desktop-v2"
    assert payload["active_runtime"] == "v2"


def test_readiness_endpoint_reports_v2_checks_when_runtime_starts(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    response = client.get("/api/readiness")

    assert response.status_code == 200
    payload = response.json()
    checks = {check["name"]: check for check in payload["checks"]}
    assert payload["status"] == "warn"
    assert payload["runtime"] == "v2"
    assert checks["build_channel"]["value"] == "beta-local-desktop-v2"
    assert checks["loc_change_blocker"]["status"] == "warn"


def test_navigation_contains_only_required_v2_labels(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    response = client.get("/api/v2/navigation")

    assert response.status_code == 200
    assert response.json()["items"] == [
        "Status Dashboard",
        "Treatment Plans",
        "Manual Upload",
        "API Testing Harness",
        "Users",
        "Forensic Logs",
        "Settings",
        "Help",
    ]


def test_treatment_plan_detail_has_42_criteria_and_no_patient_name(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    response = client.get("/api/v2/treatment-plans/307")

    assert response.status_code == 200
    payload = response.json()
    assert payload["patient_display_label"] == "Patient ID 307"
    assert len(payload["criteria_results"]) == 42
    assert "reason_for_admission" in payload["content_sections_present"]
    assert "Marleigh" not in response.text
    assert "clientName" not in response.text


def test_manager_override_requires_reason(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    blocked = client.post(
        "/api/v2/treatment-plans/307/manager-actions",
        json={"criterion_id": "criterion_01", "action": "override", "comment": "", "override_reason": ""},
    )
    saved = client.post(
        "/api/v2/treatment-plans/307/manager-actions",
        json={
            "criterion_id": "criterion_01",
            "action": "override",
            "comment": "Reviewed local evidence.",
            "override_reason": "Synthetic QA reason.",
        },
    )

    assert blocked.status_code == 400
    assert saved.status_code == 200
    assert saved.json()["status"] == "saved"


def test_api_configuration_harness_returns_redacted_v2_contract(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    saved = client.patch(
        "/api/api-configuration",
        json={
            "vendor_name": "Local Test API",
            "api_base_url": "http://127.0.0.1:8020",
            "api_key": "synthetic-secret-token",
            "timeout_seconds": 5,
            "api_enabled": False,
        },
    )
    sample = client.get("/api/api-configuration/sample-openapi.json")
    definition = client.post(
        "/api/api-configuration/pull-definitions",
        json={
            "swagger_ui_url": "http://127.0.0.1:8020/api/api-configuration/sample-openapi.json",
            "openapi_url": "http://127.0.0.1:8020/api/api-configuration/sample-openapi.json",
            "api_base_url": "http://127.0.0.1:8020",
            "use_saved_api_key": True,
            "api_key_header_name": "x-api-key",
            "client_id": "ClientId",
            "timeout_seconds": 5,
        },
    )

    assert saved.status_code == 200
    assert saved.json()["api_key_configured"] is True
    assert "synthetic-secret-token" not in saved.text
    assert sample.status_code == 200
    assert sample.json()["info"]["title"] == "Connectivity Test Definition"
    assert definition.status_code == 200
    assert definition.json()["definition_summary"]["title"] == "Connectivity Test Definition"
    assert "client_id" in definition.json()["request_keys"]


def test_large_api_job_returns_immediately_and_writes_bounded_artifacts(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)

    start = time.perf_counter()
    created = client.post("/api/v2/api-harness/jobs", json={"job_type": "pull_all_treatment_plans_all_fields"})
    elapsed = time.perf_counter() - start

    assert created.status_code == 200
    assert elapsed < 1
    job_id = created.json()["job_id"]

    final_payload = created.json()
    for _ in range(30):
        polled = client.get(f"/api/v2/api-harness/jobs/{job_id}")
        final_payload = polled.json()
        if final_payload["status"] in {"completed", "completed_with_warnings"}:
            break
        time.sleep(0.05)

    assert final_payload["status"] == "completed"
    artifacts = client.get(f"/api/v2/api-harness/jobs/{job_id}/artifacts").json()
    artifact_names = {artifact["name"] for artifact in artifacts}
    assert "all-treatment-plans.all-fields.redacted.jsonl" in artifact_names
    assert "all-treatment-plans.flattened-fields.tsv" in artifact_names
    assert "all-treatment-plans.observed-schema.json" in artifact_names

    preview = client.get(f"/api/v2/api-harness/jobs/{job_id}/preview").json()
    assert preview["max_records"] == 25
    assert preview["max_fields"] == 50
    assert len(preview["records"]) <= 25


def test_active_code_does_not_import_deprecated_runtime() -> None:
    active_files = [*Path("backend/app").rglob("*.py"), *Path("frontend/src").rglob("*.ts"), *Path("frontend/src").rglob("*.tsx")]

    offenders = [str(path) for path in active_files if "deprecated/v1" in path.read_text(encoding="utf-8")]

    assert offenders == []
