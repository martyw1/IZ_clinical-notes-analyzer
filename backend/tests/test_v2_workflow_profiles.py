from __future__ import annotations

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_admin_can_create_and_publish_a_persisted_workflow_profile(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    created = client.post(
        "/api/workflow-definitions",
        headers=headers,
        json={"workflow_key": "timeliness_review", "display_name": "Timeliness Review", "description": "Synthetic workflow profile."},
    )
    assert created.status_code == 201
    profile = created.json()
    assert profile["current_version"] is None
    assert profile["versions"][0]["status"] == "draft"

    published = client.post(
        f"/api/workflow-definitions/{profile['id']}/versions/{profile['versions'][0]['id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["current_version"]["status"] == "published"

    audit = client.get("/api/audit/logs", headers=headers)
    assert audit.status_code == 200
    assert {item["action"] for item in audit.json()["items"]} >= {"workflow_profile.created", "workflow_profile.published"}

    listed = client.get("/api/workflow-definitions", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["workflow_key"] == "timeliness_review"
