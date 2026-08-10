from __future__ import annotations

from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _counselor_headers(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    username: str = "counselor",
    temporary_password: str = "CounselorPass1",
    active_password: str = "UpdatedCounselorPass2",
) -> dict[str, str]:
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "username": username,
            "full_name": "Synthetic Counselor",
            "role": "counselor",
            "password": temporary_password,
        },
    )
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"username": username, "password": temporary_password})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = client.post(
        "/api/users/me/change-password",
        headers=headers,
        json={"current_password": temporary_password, "new_password": active_password},
    )
    assert changed.status_code == 200
    active_login = client.post("/api/auth/login", json={"username": username, "password": active_password})
    assert active_login.status_code == 200
    return {"Authorization": f"Bearer {active_login.json()['access_token']}"}


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
        json={"criterion_id": "confirm_current_loc", "action": "return_for_correction", "comment": "Confirm the current LOC source.", "override_reason": "", "assigned_counselor_username": "counselor"},
    )
    assert returned.status_code == 200

    open_queue = client.get("/api/v2/corrections", headers=counselor_headers)
    assert open_queue.status_code == 200
    queue_item = open_queue.json()["items"][0]
    assert queue_item["patient_id"] == "951"
    assert queue_item["patient_display_label"] == "MRN 951"
    assert queue_item["criterion_id"] == "confirm_current_loc"
    assert queue_item["criterion_title"] == "Confirm the current LOC"
    assert queue_item["return_comment"] == "Confirm the current LOC source."
    assert queue_item["returned_by_username"] == "admin"
    assert isinstance(queue_item["work_item_id"], int)
    assert isinstance(queue_item["plan_version_id"], int)

    other = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "other-counselor", "full_name": "Other Synthetic Counselor", "role": "counselor", "password": "OtherCounselorPass1"},
    )
    assert other.status_code == 200
    other_login = client.post("/api/auth/login", json={"username": "other-counselor", "password": "OtherCounselorPass1"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    assert client.post(
        "/api/users/me/change-password",
        headers=other_headers,
        json={"current_password": "OtherCounselorPass1", "new_password": "OtherCounselorPass2"},
    ).status_code == 200
    other_login = client.post(
        "/api/auth/login",
        json={"username": "other-counselor", "password": "OtherCounselorPass2"},
    )
    assert other_login.status_code == 200
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    assert client.get("/api/v2/corrections", headers=other_headers).json()["items"] == []
    cross_counselor = client.post(
        "/api/v2/treatment-plans/951/correction-submissions",
        headers=other_headers,
        json={"work_item_id": queue_item["work_item_id"], "criterion_id": "confirm_current_loc", "comment": "Cross-counselor submission must fail."},
    )
    assert cross_counselor.status_code == 403

    denied = client.post(
        "/api/v2/treatment-plans/951/manager-actions",
        headers=counselor_headers,
        json={"criterion_id": "confirm_current_loc", "action": "override", "comment": "", "override_reason": "Not permitted"},
    )
    assert denied.status_code == 403
    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    assert any(item["action"] == "authorization.denied" and item["outcome_status"] == "denied" for item in audit)

    submitted = client.post(
        "/api/v2/treatment-plans/951/correction-submissions",
        headers=counselor_headers,
        json={"work_item_id": queue_item["work_item_id"], "criterion_id": "confirm_current_loc", "comment": "Updated the source record and attached the corrected plan."},
    )
    assert submitted.status_code == 200
    assert client.get("/api/v2/corrections", headers=counselor_headers).json()["items"] == []

    detail = client.get("/api/v2/treatment-plans/951", headers=admin_headers).json()
    assert any(review["action"] == "correction_submitted" for review in detail["manager_reviews"])


def test_correction_queue_and_submission_are_bound_to_exact_counselor_work_items(tmp_path, monkeypatch) -> None:
    # Given: one patient has two immutable correction items assigned to different counselors.
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    _import_plan(client, admin_headers)
    counselor_a = _counselor_headers(
        client,
        admin_headers,
        username="counselor-a",
        temporary_password="CounselorATemp1",
        active_password="CounselorAActive2",
    )
    counselor_b = _counselor_headers(
        client,
        admin_headers,
        username="counselor-b",
        temporary_password="CounselorBTemp1",
        active_password="CounselorBActive2",
    )
    for criterion_id, username in (
        ("confirm_current_loc", "counselor-a"),
        ("document_interventions", "counselor-b"),
    ):
        returned = client.post(
            "/api/v2/treatment-plans/951/manager-actions",
            headers=admin_headers,
            json={
                "criterion_id": criterion_id,
                "action": "return_for_correction",
                "comment": f"Synthetic return for {criterion_id}.",
                "override_reason": "",
                "assigned_counselor_username": username,
            },
        )
        assert returned.status_code == 200, returned.text

    # When: each counselor reads the queue.
    queue_a = client.get("/api/v2/corrections", headers=counselor_a)
    queue_b = client.get("/api/v2/corrections", headers=counselor_b)

    # Then: each sees only their exact plan-version and criterion work item.
    assert queue_a.status_code == 200
    assert queue_b.status_code == 200
    assert [item["criterion_id"] for item in queue_a.json()["items"]] == ["confirm_current_loc"]
    assert [item["criterion_id"] for item in queue_b.json()["items"]] == ["document_interventions"]
    item_a = queue_a.json()["items"][0]
    item_b = queue_b.json()["items"][0]
    assert item_a["plan_version_id"] == item_b["plan_version_id"]
    assert item_a["work_item_id"] != item_b["work_item_id"]

    # When: counselor B attempts to submit counselor A's exact work item.
    cross_counselor = client.post(
        "/api/v2/treatment-plans/951/correction-submissions",
        headers=counselor_b,
        json={
            "work_item_id": item_a["work_item_id"],
            "criterion_id": item_a["criterion_id"],
            "comment": "Cross-counselor submission must be denied.",
        },
    )

    # Then: the request is denied and audited without closing either work item.
    assert cross_counselor.status_code == 403
    assert len(client.get("/api/v2/corrections", headers=counselor_a).json()["items"]) == 1
    assert len(client.get("/api/v2/corrections", headers=counselor_b).json()["items"]) == 1
    audit = client.get("/api/audit/logs", headers=admin_headers).json()["items"]
    assert any(
        event["action"] == "authorization.denied"
        and event["details"].get("family") == "correction_submission"
        for event in audit
    )

    # When: counselor A submits the exact assigned work item.
    submitted = client.post(
        "/api/v2/treatment-plans/951/correction-submissions",
        headers=counselor_a,
        json={
            "work_item_id": item_a["work_item_id"],
            "criterion_id": item_a["criterion_id"],
            "comment": "Synthetic exact correction submission.",
        },
    )

    # Then: only counselor A's item closes and counselor B's item remains open.
    assert submitted.status_code == 200
    assert client.get("/api/v2/corrections", headers=counselor_a).json()["items"] == []
    remaining_b = client.get("/api/v2/corrections", headers=counselor_b).json()["items"]
    assert [item["work_item_id"] for item in remaining_b] == [item_b["work_item_id"]]
