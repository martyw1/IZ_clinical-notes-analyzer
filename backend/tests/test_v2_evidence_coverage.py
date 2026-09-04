from __future__ import annotations

from datetime import date

import pytest

from app.v2.services.deterministic_evaluator import evaluate_plan_version
from app.v2.services.evaluation_projection import apply_evaluation
from app.v2.services.rule_package import load_rule_package
from task8_coverage_fixtures import CaseName, ORACLE, signature, source_fixture


@pytest.mark.parametrize(("case", "column"), (("empty", 1), ("partial", 2), ("full", 3)))
def test_clinical_statuses_match_literal_42_row_oracle(case: CaseName, column: int) -> None:
    # Given
    aggregate = source_fixture(case)
    # When
    bundle = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York")
    # Then
    assert tuple((item.criterion_id, item.status) for item in bundle.criteria) == tuple((row[0], row[column]) for row in ORACLE)
    assert bundle.calculated_due_date == ("2026-01-31" if case == "full" else "")


@pytest.mark.parametrize(("case", "observed", "missing"), (("empty", 0, 13), ("partial", 7, 11), ("full", 14, 0)))
def test_coverage_uses_literal_source_support_oracle(case: CaseName, observed: int, missing: int) -> None:
    # Given
    aggregate = source_fixture(case)
    bundle = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York")
    # When
    projected = apply_evaluation(aggregate, bundle)
    # Then
    assert projected.evidence_coverage_summary.criteria_with_evidence == observed
    assert projected.evidence_coverage_summary.criteria_missing_evidence == missing
    assert len(projected.criteria_results) == 42
    column = 4 if case == "partial" else 5
    expected = tuple((row[0], False if case == "empty" else row[column]) for row in ORACLE)
    assert tuple((item.criterion_id, bool(item.evidence_refs)) for item in projected.criteria_results) == expected


@pytest.mark.parametrize("value", ("", "missing", "Unknown", " unavailable ", "NONE", "null", "unvalidated_configurable"))
def test_placeholder_raw_values_do_not_become_source_evidence(value: str) -> None:
    # Given
    aggregate = source_fixture("empty").model_copy(update={"admission_date": value, "current_level_of_care": value, "source_due_date": value})
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    assert result.evidence_coverage_summary.criteria_with_evidence == 0


@pytest.mark.parametrize("raw", ("2026-01-01", "not-a-date"))
def test_partial_signature_remains_observed_when_admission_is_missing(raw: str) -> None:
    # Given
    aggregate = source_fixture("empty")
    aggregate = aggregate.model_copy(update={"content_snapshot": aggregate.content_snapshot.model_copy(update={"signatures": (signature("initial_plan", raw),)})})
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    item = next(item for item in result.criteria_results if item.criterion_id == "initial_plan_dated_correctly")
    assert item.result_status == "Missing Data"
    assert tuple(ref.source_json_path for ref in item.evidence_refs) == ("source.signatures.initial_plan",)


def test_generated_manual_plan_and_loc_wrappers_are_not_observed_source() -> None:
    # Given
    aggregate = source_fixture("empty").model_copy(update={
        "treatment_plans": ({"plan_id": "manual-generated", "is_active": True, "source": "manual_upload_file"},),
        "loc_history": ({"level_of_care": "Unknown", "effective_date": "Unknown", "source": "manual_upload_file"},),
    })
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    assert result.evidence_coverage_summary.criteria_with_evidence == 0
    assert next(item for item in result.criteria_results if item.criterion_id == "initial_plan_exists").result_status == "Present"


def test_config_and_derived_results_do_not_create_observed_references() -> None:
    # Given
    aggregate = source_fixture("full")
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    for key in ("apply_php_timing_rule", "apply_iop_op_timing_rule", "mark_current_inside_window", "flag_missing_data_not_compliance", "produce_final_checklist_result", "loc_change_deadline_unresolved"):
        assert next(item for item in result.criteria_results if item.criterion_id == key).evidence_refs == ()


@pytest.mark.parametrize(("due", "status"), (("not-a-date", "Unable to Evaluate"), ("2026-02-01", "Conflicting Evidence")))
def test_actual_invalid_or_conflicting_due_evidence_is_preserved(due: str, status: str) -> None:
    # Given
    aggregate = source_fixture("full").model_copy(update={"source_due_date": due})
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    assert result.overall_status == status
    comparison = next(item for item in result.criteria_results if item.criterion_id == "check_conflicting_evidence")
    assert "source_due_date" in {ref.source_json_path for ref in comparison.evidence_refs}
    assert due not in repr(comparison.evidence_refs)


def test_loc_history_refs_point_to_actual_fields_not_generated_paths() -> None:
    # Given
    aggregate = source_fixture("full")
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    item = next(item for item in result.criteria_results if item.criterion_id == "identify_loc_change")
    assert {ref.source_json_path for ref in item.evidence_refs} == {"loc_history[0].level_of_care", "loc_history[0].effective_date"}
    assert item.result_status == "Not Applicable"


def test_actual_loc_update_kind_is_referenced_without_claiming_compliance() -> None:
    # Given
    aggregate = source_fixture("full").model_copy(update={"treatment_plans": ({"plan_kind": "loc_change_update"},)})
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    item = next(item for item in result.criteria_results if item.criterion_id == "loc_change_update_document")
    assert tuple(ref.source_json_path for ref in item.evidence_refs) == ("treatment_plans[0].plan_kind",)
    assert item.result_status == "Not Applicable"


def test_untyped_signature_is_not_attributed_to_initial_or_master_role() -> None:
    # Given
    aggregate = source_fixture("empty")
    aggregate = aggregate.model_copy(update={"content_snapshot": aggregate.content_snapshot.model_copy(update={"signatures": (signature("unknown", "2026-01-01"),)})})
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    assert result.evidence_coverage_summary.criteria_with_evidence == 0


def test_unmapped_real_loc_is_observed_without_a_successful_mapping() -> None:
    # Given
    aggregate = source_fixture("empty").model_copy(update={"current_level_of_care": "Synthetic unmapped LOC"})
    # When
    result = apply_evaluation(aggregate, evaluate_plan_version(aggregate, load_rule_package(), date(2026, 1, 2), "America/New_York"))
    # Then
    item = next(item for item in result.criteria_results if item.criterion_id == "confirm_loc_rule_mapping")
    assert item.result_status == "Missing Data"
    assert tuple(ref.source_json_path for ref in item.evidence_refs) == ("current_level_of_care",)
