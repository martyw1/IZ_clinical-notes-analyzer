from __future__ import annotations

from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _counselor_headers(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "username": "counselor",
            "full_name": "Synthetic Counselor",
            "role": "counselor",
            "password": "CounselorPass1",
        },
    )
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"username": "counselor", "password": "CounselorPass1"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = client.post("/api/users/me/change-password", headers=headers, json={"current_password": "CounselorPass1", "new_password": "UpdatedCounselorPass2"})
    assert changed.status_code == 200
    return headers


def _import_plan(client: TestClient, headers: dict[str, str]) -> None:
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        headers=headers,
        data={"patient_id": "951"},
        files={
            "file": (
                "synthetic-correction-queue.txt",
                "Patient ID: 951\nCurrent Level of Care: PHP\nIntervention: Synthetic correction queue intervention.",
                "text/plain",
            )
        },
    )
    assert imported.status_code == 201


def test_return_for_correction_creates_a_counselor_queue_item_and_submission_resolves_it(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    _import_plan(client, admin_headers)
    counselor_headers = _counselor_headers(client, admin_headers)

    returned = client.post(
        "/api/v2/treatment-plans/951/manager-actions",
        headers=admin_headers,
        json={"criterion_id": "confirm_current_loc", "action": "return_for_correction", "comment": "Confirm the current LOC source.", "override_reason": ""},
    )
    assert returned.status_code == 200

    open_queue = client.get("/api/v2/corrections", headers=counselor_headers)
    assert open_queue.status_code == 200
    assert open_queue.json()["items"] == [
        {
            "patient_id": "951",
            "patient_display_label": "Patient ID 951",
            "criterion_id": "confirm_current_loc",
            "criterion_title": "Confirm the current LOC",
            "return_comment": "Confirm the current LOC source.",
            "returned_by_username": "admin",
            "returned_at": open_queue.json()["items"][0]["returned_at"],
        }
    ]

    denied = client.post(
        "/api/v2/treatment-plans/951/manager-actions",
        headers=counselor_headers,
        json={"criterion_id": "confirm_current_loc", "action": "override", "comment": "", "override_reason": "Not permitted"},
    )
    assert denied.status_code == 403
    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    assert any(item["action"] == "manager.criterion.override.denied" and item["outcome_status"] == "denied" for item in audit)

    submitted = client.post(
        "/api/v2/treatment-plans/951/correction-submissions",
        headers=counselor_headers,
        json={"criterion_id": "confirm_current_loc", "comment": "Updated the source record and attached the corrected plan."},
    )
    assert submitted.status_code == 200
    assert client.get("/api/v2/corrections", headers=counselor_headers).json()["items"] == []

    detail = client.get("/api/v2/treatment-plans/951", headers=admin_headers).json()
    assert any(review["action"] == "correction_submitted" for review in detail["manager_reviews"])
