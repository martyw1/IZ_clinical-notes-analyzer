from __future__ import annotations

from dataclasses import replace
from datetime import date

from test_v2_evaluation_persistence import PRIVACY_CANARY, _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _plan_metadata(version_id: int, record_id: int, source: str = "manual_upload", ordinal: int = 1) -> dict[str, int | str]:
    return {"plan_version_id": version_id, "patient_record_id": record_id, "source_mode": source,
            "version_ordinal": ordinal, "original_plan_reference": "", "service_date": ""}


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


def test_missing_source_timestamp_remains_blank_after_persistence(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _aggregate("MRN-NO-SOURCE-TIME").model_dump(mode="json")
    payload["source_last_updated"] = ""
    payload["content_snapshot"]["plan_id"] = "plan-no-source-time"

    saved = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=payload,
    )
    roster = client.get("/api/v2/patient-roster", headers=headers)

    assert saved.status_code == 201
    assert roster.status_code == 200
    assert roster.json()["items"][0]["treatment_plans"] == [
        {"treatment_plan_id": "plan-no-source-time", "last_updated": "",
         **_plan_metadata(saved.json()["plan_version_id"], saved.json()["patient_record_id"])}
    ]


def test_patient_roster_lists_every_plan_for_each_mrn_in_latest_updated_order(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    base = _aggregate("MRN-842")
    identities = {}
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
        identities[plan_id] = _plan_metadata(response.json()["plan_version_id"], response.json()["patient_record_id"], ordinal=len(identities) + 1)

    response = client.get("/api/v2/patient-roster", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "mrn": "MRN-842",
            "patient_record_id": identities["plan-newer"]["patient_record_id"],
            "full_name": "",
            "source_mode": "manual_upload",
            "lifecycle_state": "active",
            "primary_counselor_id": None,
            "primary_counselor_name": "",
            "tracking_eligible": True,
            "current_level_of_care": base.current_level_of_care,
            "treatment_plans": [
                {"treatment_plan_id": "plan-newer", "last_updated": "2026-07-09T17:45:00+00:00", **identities["plan-newer"]},
                {"treatment_plan_id": "plan-older", "last_updated": "2026-07-01T08:15:00+00:00", **identities["plan-older"]},
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
    identities = {}
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
            saved = save_treatment_plan_aggregate(database, TreatmentPlanAggregate.model_validate(payload), actor)
            identities[plan_id] = _plan_metadata(saved.plan_version_id, saved.patient_record_id, "alleva_rest_api", len(identities) + 1)

    monkeypatch.setattr("app.v2.api.roster_routes.facility_local_date", lambda *_: date(2026, 4, 1))
    response = client.get("/api/v2/treatment-plan-roster", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "treatment_plan_id": "alleva-followup",
            "primary_counselor_id": None,
            "primary_counselor_name": "",
            "next_due_date": "2026-03-10",
            "deadline_status": "Overdue",
            "tracking_exclusion_reason": "",
            "days_overdue": 22,
            "reviewed_at_utc": "",
            **identities["alleva-followup"],
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
            "primary_counselor_id": None,
            "primary_counselor_name": "",
            "next_due_date": "2026-02-03",
            "deadline_status": "Outside current tracking",
            "tracking_exclusion_reason": "A different saved plan was selected for current tracking.",
            "days_overdue": None,
            "reviewed_at_utc": "",
            **identities["alleva-initial"],
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


def test_alleva_filtered_treatment_plan_roster_excludes_manual_upload_plans(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    response = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=_aggregate("MRN-844").model_dump(mode="json"),
    )
    assert response.status_code == 201

    roster = client.get("/api/v2/treatment-plan-roster", headers=headers, params={"source_mode": "alleva_rest_api"})

    assert roster.status_code == 200
    assert roster.json() == {"items": []}

def test_gop_computed_due_matches_detail_and_roster(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _aggregate("MRN-GOP-DEADLINE").model_dump(mode="json")
    payload.update(current_level_of_care="Evening GOP", source_last_updated="2026-02-08T18:30:00Z")
    saved = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=payload)
    assert saved.status_code == 201
    version_id = saved.json()["plan_version_id"]

    detail = client.get(f"/api/v2/treatment-plans/MRN-GOP-DEADLINE?plan_version_id={version_id}", headers=headers)
    roster = client.get("/api/v2/treatment-plan-roster", headers=headers)

    assert detail.status_code == roster.status_code == 200
    row = next(item for item in roster.json()["items"] if item["plan_version_id"] == version_id)
    assert detail.json()["date_clock_due_date"] == row["next_due_date"] == "2026-04-09"
    assert "GOP using last updated: 2026-02-08 + 60 calendar days = 2026-04-09" in detail.json()["deadline_explanation"]
