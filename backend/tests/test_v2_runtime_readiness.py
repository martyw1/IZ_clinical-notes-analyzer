from __future__ import annotations

from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _card_status(payload: dict[str, object], label: str) -> str:
    cards = payload["source_cards"]
    assert isinstance(cards, list)
    card = next(item for item in cards if isinstance(item, dict) and item["label"] == label)
    return str(card["status"])


def test_dashboard_and_readiness_reflect_persisted_configuration_and_imports(tmp_path, monkeypatch) -> None:
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    initial_dashboard = client.get("/api/v2/dashboard", headers=headers)
    assert initial_dashboard.status_code == 200
    assert _card_status(initial_dashboard.json(), "Manual upload readiness") == "awaiting data"
    assert _card_status(initial_dashboard.json(), "API readiness") == "not configured"
    assert any("No normalized treatment-plan records" in blocker for blocker in initial_dashboard.json()["blockers"])

    initial_readiness = client.get("/api/readiness")
    assert initial_readiness.status_code == 200
    readiness_checks = {check["name"]: check["status"] for check in initial_readiness.json()["checks"]}
    assert readiness_checks["api_profile"] == "warn"

    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={"client_secret": "synthetic-api-secret", "api_enabled": True},
    )
    assert configured.status_code == 200
    assert configured.json()["client_secret_configured"] is True

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        headers=headers,
        data={"patient_id": "971"},
        files={"file": ("synthetic-readiness.txt", "Patient ID: 971\nIntervention: Synthetic readiness evidence.", "text/plain")},
    )
    assert imported.status_code == 201

    configured_dashboard = client.get("/api/v2/dashboard", headers=headers).json()
    assert _card_status(configured_dashboard, "Manual upload readiness") == "ready"
    assert _card_status(configured_dashboard, "API readiness") == "configured for testing"
    assert configured_dashboard["metrics"]["active_patient_ids"] == 1
    assert client.get("/api/readiness").json()["status"] == "warn"
