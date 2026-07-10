from __future__ import annotations

from datetime import date, timedelta

from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields
from app.v2.services.timeliness import TimelinessRules, evaluate_treatment_plan_timing
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _parsed_fields(*, due_date: str, signature_datetime: str = "2026-06-02", admission_date: str = "2026-06-01") -> ParsedManualFields:
    return ParsedManualFields(
        patient_id="912",
        patient_id_correction_applied=False,
        level_of_care="PHP",
        admission_date=admission_date,
        due_date=due_date,
        reason_for_admission="Synthetic recovery support.",
        initial_client_needs="Synthetic initial needs.",
        family_education_needs="Synthetic family needs.",
        problem_description="Synthetic problem.",
        diagnosis_description="Synthetic diagnosis.",
        icd10_code="F10.20",
        behavioral_definition="Synthetic behavioral definition.",
        goal_description="Synthetic goal.",
        objective_description="Synthetic objective.",
        intervention_description="Synthetic intervention.",
        signature_datetime=signature_datetime,
        raw_text="Synthetic treatment-plan data.",
    )


def test_timing_is_overdue_when_required_evidence_exists_and_due_date_has_passed() -> None:
    # Given
    aggregate = build_manual_aggregate(_parsed_fields(due_date="2026-06-10"))

    # When
    evaluation = evaluate_treatment_plan_timing(aggregate, TimelinessRules(), date(2026, 6, 11))

    # Then
    assert evaluation.status == "Overdue"
    assert evaluation.due_date == "2026-06-10"


def test_timing_is_within_window_when_required_evidence_exists_and_due_date_has_not_passed() -> None:
    # Given
    aggregate = build_manual_aggregate(_parsed_fields(due_date="2026-06-10"))

    # When
    evaluation = evaluate_treatment_plan_timing(aggregate, TimelinessRules(), date(2026, 6, 10))

    # Then
    assert evaluation.status == "Urgent"


def test_timing_is_missing_data_when_signature_or_due_date_is_not_available() -> None:
    # Given
    aggregate = build_manual_aggregate(_parsed_fields(due_date="Unknown", signature_datetime=""))

    # When
    evaluation = evaluate_treatment_plan_timing(aggregate, TimelinessRules(), date(2026, 6, 10))

    # Then
    assert evaluation.status == "Missing Data"
    assert set(evaluation.missing_fields) == {"date_clock_due_date", "signature_datetime"}


def test_timing_needs_review_for_loc_change_while_window_is_unvalidated() -> None:
    # Given
    aggregate = build_manual_aggregate(_parsed_fields(due_date="2026-06-10")).model_copy(
        update={
            "loc_history": (
                {"level_of_care": "PHP", "effective_date": "2026-06-01", "source": "manual_upload_file"},
                {"level_of_care": "IOP", "effective_date": "2026-06-05", "source": "manual_upload_file"},
            )
        }
    )

    # When
    evaluation = evaluate_treatment_plan_timing(aggregate, TimelinessRules(loc_change_window_validated=False), date(2026, 6, 6))

    # Then
    assert evaluation.status == "Needs Review"
    assert "LOC-change" in evaluation.reason


def test_manual_aggregate_import_fails_closed_without_typed_plan_signatures(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    admission = date.today() - timedelta(days=31)
    aggregate = build_manual_aggregate(_parsed_fields(
        admission_date=admission.isoformat(),
        signature_datetime=admission.isoformat(),
        due_date=(admission + timedelta(days=30)).isoformat(),
    ))

    # When
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=aggregate.model_dump(mode="json"),
    )

    # Then
    assert imported.status_code == 201
    detail = client.get("/api/v2/treatment-plans/912", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["overall_status"] == "Missing Data"
    statuses = {
        item["criterion_id"]: item["result_status"]
        for item in detail.json()["criteria_results"]
    }
    assert statuses["initial_plan_required_signatures"] == "Missing Data"
    assert statuses["master_plan_required_signatures"] == "Missing Data"
