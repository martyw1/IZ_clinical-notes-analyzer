from __future__ import annotations

from dataclasses import dataclass

from app.v2.services.dashboard_data import dashboard_payload
from test_v2_plan_version_actions import _import, runtime as runtime
from test_v2_plan_version_authorization import _other_facility_version, _user
from test_v2_plan_version_corrections import CorrectionScenario, _import_newer_plan, scenario as scenario
from test_v2_correction_lineage import _seed_legacy_item


@dataclass(frozen=True, slots=True)
class PlanFixture:
    patient_record_id: int
    patient_id: str
    overall_status: str
    missing_criteria_count: int


def test_metrics_use_patient_records_overall_statuses_and_distinct_units() -> None:
    # Given: eight already-authorized latest source plans across five rows and four MRNs.
    rows = (
        PlanFixture(101, "TEST-001", "Overdue", 2), PlanFixture(101, "TEST-001", "Urgent", 3),
        PlanFixture(102, "TEST-001", "Due Soon", 5), PlanFixture(103, "TEST-002", "Needs Review", 7),
        PlanFixture(103, "TEST-002", "Conflicting Evidence", 11), PlanFixture(104, "TEST-003", "Unable to Evaluate", 13),
        PlanFixture(104, "TEST-003", "Current/Compliant", 17), PlanFixture(105, "TEST-004", "Missing Data", 19),
    )
    # When
    result = dashboard_payload(rows, api_configured=False, api_client_id_configured=False, api_enabled=False,
                               sync_enabled=False, sync_authorized=False, loc_change_window_validated=False, returned_count=3)
    # Then
    assert result["metrics"] == {"active_patient_ids": 5, "overdue_plans": 1, "urgent_plans": 1, "due_soon_plans": 1,
                                 "needs_review": 1, "missing_data": 77, "returned": 3, "conflicting": 1, "unable": 1}


def test_empty_population_is_not_inferred_as_active_or_compliant() -> None:
    # Given / When
    result = dashboard_payload((), api_configured=False, api_client_id_configured=False, api_enabled=False,
                               sync_enabled=False, sync_authorized=False, loc_change_window_validated=False, returned_count=0)
    # Then
    assert result["metrics"] == {"active_patient_ids": 0, "overdue_plans": 0, "urgent_plans": 0, "due_soon_plans": 0,
                                 "needs_review": 0, "missing_data": 0, "returned": 0, "conflicting": 0, "unable": 0}
    assert result["blockers"]


def test_dashboard_api_counts_only_authorized_latest_source_versions(runtime) -> None:
    # Given
    first = _import(runtime)
    latest = _import(runtime, marker="newer")
    sibling = _import(runtime, plan_id="plan-b")
    collision = _import(runtime, source="alleva_rest_api")
    _, headers = _user(runtime, "office_manager")
    denied = _other_facility_version(first["plan_version_id"])
    client, _ = runtime
    rows = client.get("/api/v2/treatment-plans", headers=headers).json()["items"]
    assert {row["plan_version_id"] for row in rows} == {latest["plan_version_id"], sibling["plan_version_id"], collision["plan_version_id"]}
    assert denied["plan_version_id"] not in {row["plan_version_id"] for row in rows}
    # When
    response = client.get("/api/v2/dashboard", headers=headers)
    # Then
    assert response.status_code == 200
    assert response.json()["metrics"] == {"active_patient_ids": 2, "overdue_plans": 0, "urgent_plans": 0,
                                         "due_soon_plans": 0, "needs_review": 0, "missing_data": 21,
                                         "returned": 0, "conflicting": 0, "unable": 0}


def test_dashboard_counts_valid_open_historical_items_not_unassigned_legacy(scenario: CorrectionScenario) -> None:
    # Given
    _import_newer_plan(scenario)
    _seed_legacy_item(scenario, linked=False)
    # When
    response = scenario.client.get("/api/v2/dashboard", headers=scenario.admin)
    # Then
    assert response.status_code == 200
    assert response.json()["metrics"]["returned"] == 1


def test_dashboard_excludes_closed_correction_items(scenario: CorrectionScenario) -> None:
    # Given
    assert scenario.submit().status_code == 200
    # When
    response = scenario.client.get("/api/v2/dashboard", headers=scenario.admin)
    # Then
    assert response.status_code == 200
    assert response.json()["metrics"]["returned"] == 0
