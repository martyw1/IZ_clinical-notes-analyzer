from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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
    last_updated: str = "2026-09-08"
    next_due_date: str = "2026-11-07"
    plan_version_id: int = 1


def test_metrics_use_latest_plan_deadlines_independently_of_review_status() -> None:
    # Given: eight already-authorized latest source plans across five rows and four MRNs.
    rows = (
        PlanFixture(101, "TEST-001", "Overdue", 2, "2026-08-01", "2026-09-30"),
        PlanFixture(101, "TEST-001", "Missing Data", 3, "2026-09-08", "2026-11-07"),
        PlanFixture(102, "TEST-001", "Missing Data", 5, "2026-08-01", "2026-09-30"),
        PlanFixture(103, "TEST-002", "Needs Review", 7, "2026-08-31", "2026-10-30"),
        PlanFixture(104, "TEST-003", "Conflicting Evidence", 11, "2026-08-17", "2026-10-16"),
        PlanFixture(105, "TEST-004", "Current/Compliant", 19, "invalid", "Unknown"),
    )
    # When
    result = dashboard_payload(rows, api_configured=False, api_client_id_configured=False, api_enabled=False,
                               sync_enabled=False, sync_authorized=False, loc_change_window_validated=False, evaluation_date=date(2026, 10, 16))
    # Then
    assert result["metrics"] == {"overdue_plans": 1, "due_soon_plans": 2}
    assert any("excluded from deadline counts" in value for value in result["blockers"])


def test_empty_population_is_not_inferred_as_active_or_compliant() -> None:
    # Given / When
    result = dashboard_payload((), api_configured=False, api_client_id_configured=False, api_enabled=False,
                               sync_enabled=False, sync_authorized=False, loc_change_window_validated=False, evaluation_date=date(2026, 10, 16))
    # Then
    assert result["metrics"] == {"overdue_plans": 0, "due_soon_plans": 0}
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
    assert response.json()["metrics"] == {"overdue_plans": 0, "due_soon_plans": 0}


def test_dashboard_counts_valid_open_historical_items_not_unassigned_legacy(scenario: CorrectionScenario) -> None:
    # Given
    _import_newer_plan(scenario)
    _seed_legacy_item(scenario, linked=False)
    # When
    response = scenario.client.get("/api/v2/dashboard", headers=scenario.admin)
    # Then
    assert response.status_code == 200
    assert "returned" not in response.json()["metrics"]


def test_dashboard_excludes_closed_correction_items(scenario: CorrectionScenario) -> None:
    # Given
    assert scenario.submit().status_code == 200
    # When
    response = scenario.client.get("/api/v2/dashboard", headers=scenario.admin)
    # Then
    assert response.status_code == 200
    assert "returned" not in response.json()["metrics"]


def test_ambiguous_latest_or_missing_deadline_is_explained_and_not_counted():
    rows = (PlanFixture(1, "TEST-001", "Overdue", 0, next_due_date="2026-10-01"),
            PlanFixture(1, "TEST-001", "Overdue", 0, next_due_date="2026-10-02"),
            PlanFixture(2, "TEST-002", "Overdue", 0, next_due_date="Unknown"))
    result = dashboard_payload(rows, api_configured=False, api_client_id_configured=False, api_enabled=False,
                               sync_enabled=False, sync_authorized=False, loc_change_window_validated=False,
                               evaluation_date=date(2026, 10, 16))
    assert result["metrics"] == {"overdue_plans": 0, "due_soon_plans": 0}
    assert any("latest plan cannot be determined" in item for item in result["blockers"])
    assert any("no computable update deadline" in item for item in result["blockers"])
