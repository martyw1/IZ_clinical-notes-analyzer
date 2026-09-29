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


def test_clinical_rule_settings_show_active_values_and_reject_unapproved_changes(tmp_path, monkeypatch) -> None:
    # Given: an isolated application with a saved settings profile.
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: an admin attempts to validate the provisional LOC rule or change an interval.
    loc_response = client.patch(
        "/api/settings", headers=headers, json={"treatment_plan_loc_change_window_validated": True},
    )
    interval_response = client.patch(
        "/api/settings", headers=headers, json={"treatment_plan_php_review_interval_days": 45},
    )
    settings = client.get("/api/settings", headers=headers)
    readiness = client.get("/api/readiness")
    dashboard = client.get("/api/v2/dashboard", headers=headers)

    # Then: the API reports the active versioned values and retains the unresolved blocker.
    assert loc_response.status_code == 409
    assert interval_response.status_code == 409
    assert settings.status_code == 200
    assert settings.json()["treatment_plan_php_review_interval_days"] == 30
    assert settings.json()["treatment_plan_iop_op_review_interval_days"] == 60
    assert settings.json()["treatment_plan_loc_change_window_validated"] is False
    assert next(check for check in readiness.json()["checks"] if check["name"] == "loc_change_blocker")["status"] == "warn"
    assert any("LOC-change" in blocker for blocker in dashboard.json()["blockers"])
