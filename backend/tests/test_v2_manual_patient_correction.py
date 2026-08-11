from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _fresh_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "StrongLocalPass1")
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "test-secret-key-for-v2-manual-correction")
    monkeypatch.setenv("IZ_CNA_DATA_ENCRYPTION_KEY", "test-data-encryption-key-for-v2-manual-correction")
    for module_name in tuple(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)
    from app.main import create_app

    return TestClient(create_app())


def _auth_headers(client: TestClient) -> dict[str, str]:
    password = "StrongLocalPass1"
    response = client.post("/api/auth/login", json={"username": "admin", "password": password})
    if response.status_code == 401:
        password = "StrongLocalActivePass2"
        response = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    if response.json().get("must_reset_password"):
        changed = client.post(
            "/api/users/me/change-password",
            headers=headers,
            json={"current_password": password, "new_password": "StrongLocalActivePass2"},
        )
        assert changed.status_code == 200
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "StrongLocalActivePass2"},
        )
        assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_manual_upload_patient_id_mismatch_requires_confirmed_correction(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    file_text = "\n".join(
        (
            "Patient ID: 931",
            "Current Level of Care: PHP",
            "Admission Date: 2026-06-02",
            "Intervention: Synthetic correction workflow intervention.",
        )
    )

    rejected = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "932", "confirm_patient_id_correction": "false"},
        files={"file": ("synthetic-patient-id-mismatch.txt", file_text, "text/plain")},
        headers=headers,
    )

    assert rejected.status_code == 409
    assert "confirmation" in rejected.json()["detail"].lower()
    assert client.get("/api/v2/treatment-plans", headers=headers).json()["items"] == []

    corrected = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "932", "confirm_patient_id_correction": "true"},
        files={"file": ("synthetic-patient-id-mismatch.txt", file_text, "text/plain")},
        headers=headers,
    )

    assert corrected.status_code == 201
    assert corrected.json()["patient_id"] == "932"
    assert corrected.json()["patient_id_correction_applied"] is True
    detail = client.get("/api/v2/treatment-plans/932", headers=headers)
    assert detail.status_code == 200
    assert any("MRN correction" in warning for warning in detail.json()["data_quality_warnings"])

    audit = client.get("/api/audit/logs", headers=headers)
    assert audit.status_code == 200
    correction_event = next(item for item in audit.json()["items"] if item["action"] == "manual_upload.patient_id.corrected")
    assert correction_event["target_entity_id"].isdigit()
    assert "932" not in str(correction_event)
    assert correction_event["details"]["patient_id_correction_applied"] is True
    assert "931" not in str(correction_event["details"])
    assert "synthetic-patient-id-mismatch" not in str(correction_event["details"])
