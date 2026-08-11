from __future__ import annotations

from dataclasses import replace

from test_v2_evaluation_persistence import PRIVACY_CANARY, _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_plan_source_update_order_uses_utc_instants_then_plan_id() -> None:
    from app.v2.services.patient_roster import plans_by_source_update
    from app.v2.services.treatment_plan_types import stored_plan

    base = stored_plan(_aggregate("MRN-SORT"))
    plans = (
        replace(base, plan_id="plan-b", last_updated="2026-07-01T08:00:00Z"),
        replace(base, plan_id="plan-missing", last_updated="not-a-source-timestamp"),
        replace(base, plan_id="plan-a", last_updated="2026-07-01T04:00:00-04:00"),
    )

    assert tuple(plan.plan_id for plan in plans_by_source_update(plans)) == (
        "plan-a",
        "plan-b",
        "plan-missing",
    )


def test_patient_roster_lists_every_plan_for_each_mrn_in_latest_updated_order(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    base = _aggregate("MRN-842")
    for plan_id, last_updated in (
        ("plan-older", "2026-07-01T08:15:00+00:00"),
        ("plan-newer", "2026-07-09T17:45:00+00:00"),
    ):
        payload = base.model_dump(mode="json")
        payload["source_last_updated"] = last_updated
        payload["content_snapshot"]["plan_id"] = plan_id
        response = client.post(
            "/api/v2/manual-uploads/treatment-plan-aggregate",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 201

    response = client.get("/api/v2/patient-roster", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "mrn": "MRN-842",
            "full_name": "",
            "source_mode": "manual_upload",
            "lifecycle_state": "active",
            "current_level_of_care": base.current_level_of_care,
            "treatment_plans": [
                {"treatment_plan_id": "plan-newer", "last_updated": "2026-07-09T17:45:00+00:00"},
                {"treatment_plan_id": "plan-older", "last_updated": "2026-07-01T08:15:00+00:00"},
            ],
            "first_seen_at": response.json()["items"][0]["first_seen_at"],
            "last_seen_at": response.json()["items"][0]["last_seen_at"],
            "reconciled_at": "",
        }
    ]
    assert "patient_id" not in response.text
    assert "treatment_plan_status" not in response.text
    assert PRIVACY_CANARY not in response.text


def test_treatment_plan_roster_returns_alleva_lineage_by_mrn(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    from app.v2.db import SessionLocal
    from app.v2.domain.schemas import TreatmentPlanAggregate
    from app.v2.models import User
    from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

    base = _aggregate("MRN-843")
    with SessionLocal() as database:
        actor = database.get(User, 1)
        assert actor is not None
        for plan_id, plan_date, last_updated in (
            ("alleva-initial", "2026-01-03", "2026-01-04T09:00:00+00:00"),
            ("alleva-followup", "2026-02-07", "2026-02-08T18:30:00+00:00"),
        ):
            payload = base.model_dump(mode="json")
            payload.update({
                "source_mode": "alleva_rest_api",
                "date_clock_anchor": plan_date,
                "source_last_updated": last_updated,
            })
            payload["content_snapshot"].update({
                "plan_id": plan_id,
                "source_mode": "alleva_rest_api",
            })
            save_treatment_plan_aggregate(database, TreatmentPlanAggregate.model_validate(payload), actor)

    response = client.get("/api/v2/treatment-plan-roster", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "treatment_plan_id": "alleva-followup",
            "mrn": "MRN-843",
            "patient_key": "MRN-843",
            "linked_to_mrn": True,
            "full_name": "",
            "last_updated": "2026-02-08T18:30:00+00:00",
            "previous_treatment_plan_id": "alleva-initial",
            "initial_treatment_plan_id": "alleva-initial",
            "initial_treatment_plan_date": "2026-01-03",
        },
        {
            "treatment_plan_id": "alleva-initial",
            "mrn": "MRN-843",
            "patient_key": "MRN-843",
            "linked_to_mrn": True,
            "full_name": "",
            "last_updated": "2026-01-04T09:00:00+00:00",
            "previous_treatment_plan_id": "",
            "initial_treatment_plan_id": "alleva-initial",
            "initial_treatment_plan_date": "2026-01-03",
        },
    ]


def test_treatment_plan_roster_excludes_manual_upload_plans(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    response = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=_aggregate("MRN-844").model_dump(mode="json"),
    )
    assert response.status_code == 201

    roster = client.get("/api/v2/treatment-plan-roster", headers=headers)

    assert roster.status_code == 200
    assert roster.json() == {"items": []}
