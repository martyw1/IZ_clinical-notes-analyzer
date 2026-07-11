from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.v2.services.deterministic_evaluator import evaluate_plan_version, facility_local_date
from app.v2.domain.schemas import TreatmentPlanSignatureMetadata
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields
from app.v2.services.rule_package import DeterministicRulePackage, LevelOfCareRule, RuleConfigurationError, load_rule_package


def _aggregate(*, loc: str = "PHP", admission: str = "2026-01-01", signature: str = "2026-01-01", due: str = "2026-01-31"):
    parsed = ParsedManualFields(
        patient_id="synthetic-42", patient_id_correction_applied=False, level_of_care=loc,
        admission_date=admission, due_date=due, reason_for_admission="Synthetic support.",
        initial_client_needs="Synthetic needs.", family_education_needs="Synthetic family needs.",
        problem_description="Synthetic problem.", diagnosis_description="Synthetic diagnosis.", icd10_code="F10.20",
        behavioral_definition="Synthetic behavior.", goal_description="Synthetic goal.",
        objective_description="Synthetic objective.", intervention_description="Synthetic intervention.",
        signature_datetime=signature, raw_text="Synthetic labeled treatment-plan evidence.",
    )
    aggregate = build_manual_aggregate(parsed)
    signatures = (
        _signature("initial_plan", signature, "treatment_plans.initial.signatures[0]"),
        _signature("master_plan", signature, "treatment_plans.master.signatures[0]"),
    )
    return aggregate.model_copy(update={
        "content_snapshot": aggregate.content_snapshot.model_copy(update={"signatures": signatures}),
    })


def _criterion_status(bundle, criterion_id: str) -> str:
    return next(item.status for item in bundle.criteria if item.criterion_id == criterion_id)


def _signature(role: str, signed_on: str, path: str) -> TreatmentPlanSignatureMetadata:
    return TreatmentPlanSignatureMetadata(
        signature_type=role, has_signature_data=True, signer_role_or_type="clinician",
        signature_datetime=signed_on, signature_data_length=0, signature_data_omitted_reason="synthetic metadata only",
        evidence_role=role, source_json_path=path,
    )


@pytest.mark.parametrize(
    ("evaluation_date", "expected"),
    ((date(2026, 2, 1), "Overdue"), (date(2026, 1, 31), "Urgent"), (date(2026, 1, 30), "Urgent"),
     (date(2026, 1, 29), "Due Soon"), (date(2026, 1, 24), "Due Soon"), (date(2026, 1, 23), "Current/Compliant")),
)
def test_exact_status_boundary_when_facility_date_changes(evaluation_date: date, expected: str) -> None:
    # Given
    package = load_rule_package()

    # When
    bundle = evaluate_plan_version(_aggregate(), package, evaluation_date, "America/New_York")

    # Then
    assert bundle.overall_status == expected


@pytest.mark.parametrize(
    ("loc", "interval"),
    (
        ("PHP", 30), ("Partial Hospitalization", 30), ("Partial Hospitalization Program", 30),
        ("IOP", 60), ("Intensive Outpatient", 60), ("Intensive Outpatient Program", 60),
        ("IOP-5", 60), ("IOP5", 60), ("IOP 5", 60), ("Intensive Outpatient 5", 60),
        ("IOP-19", 60), ("IOP19", 60), ("IOP 19", 60), ("Intensive Outpatient 19", 60),
        ("IOP-3", 60), ("IOP3", 60), ("IOP 3", 60), ("Intensive Outpatient 3", 60),
        ("Outpatient", 60), ("OUTPATIENT", 60), ("OP", 60), ("O/P", 60),
    ),
)
def test_every_configured_loc_alias_uses_its_versioned_recurrence(loc: str, interval: int) -> None:
    # Given
    package = load_rule_package()

    # When
    expected_due = "2026-01-31" if interval == 30 else "2026-03-02"
    bundle = evaluate_plan_version(_aggregate(loc=loc, due=expected_due), package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.calculated_due_date == expected_due


def test_configured_non_php_category_uses_sixty_day_recurrence() -> None:
    # Given
    package = load_rule_package()
    custom_levels = dict(package.rules.levels_of_care)
    custom_levels["RESIDENTIAL_STEP_DOWN"] = LevelOfCareRule(
        aliases=("Residential Step Down",), treatment_plan_update_interval_days=60,
    )
    custom_package = DeterministicRulePackage(
        package.checklist, package.rules.model_copy(update={"levels_of_care": custom_levels}),
    )

    # When
    bundle = evaluate_plan_version(
        _aggregate(loc="Residential Step Down", due="2026-03-02"), custom_package,
        date(2026, 1, 2), "America/New_York",
    )

    # Then
    assert bundle.mapped_level_of_care == "RESIDENTIAL_STEP_DOWN"
    assert bundle.calculated_due_date == "2026-03-02"


def test_latest_valid_signed_review_replaces_admission_anchor() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate(due="2026-03-16").model_copy(update={
        "treatment_reviews": (
            {"review_date": "2026-01-20", "signature_date": ""},
            {"review_date": "2026-02-14", "signature_date": "2026-02-14"},
        )
    })

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 2, 15), "America/New_York")

    # Then
    assert bundle.recurring_anchor == "2026-02-14"
    assert bundle.calculated_due_date == "2026-03-16"


def test_admission_is_anchor_when_no_valid_signed_review_exists() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate().model_copy(update={"treatment_reviews": ({"review_date": "2026-01-20", "signature_date": ""},)})

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.recurring_anchor == "2026-01-01"


@pytest.mark.parametrize(
    ("aggregate", "expected"),
    ((_aggregate(signature=""), "Missing Data"), (_aggregate(loc="Unknown"), "Unable to Evaluate"),
     (_aggregate(due="not-a-date"), "Unable to Evaluate"), (_aggregate(due="2026-02-01"), "Conflicting Evidence")),
)
def test_uncertain_or_conflicting_evidence_never_becomes_compliant(aggregate, expected: str) -> None:
    # Given
    package = load_rule_package()

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.overall_status == expected


def test_day_one_and_master_signature_criteria_are_deterministic() -> None:
    # Given
    package = load_rule_package()

    # When
    compliant = evaluate_plan_version(_aggregate(), package, date(2026, 1, 2), "America/New_York")
    late_signature = evaluate_plan_version(_aggregate(signature="2026-02-01", due="2026-01-31"), package, date(2026, 1, 2), "America/New_York")

    # Then
    assert _criterion_status(compliant, "initial_plan_dated_correctly") == "Compliant"
    assert _criterion_status(compliant, "master_plan_within_30_days") == "Compliant"
    assert _criterion_status(late_signature, "initial_plan_dated_correctly") == "Needs Review"
    assert _criterion_status(late_signature, "master_plan_within_30_days") == "Overdue"


def test_initial_and_master_signature_roles_are_evaluated_independently() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate().model_copy(update={"content_snapshot": _aggregate().content_snapshot.model_copy(update={
        "signatures": (
            _signature("initial_plan", "2026-01-01", "treatment_plans.initial.signatures[0]"),
            _signature("master_plan", "2026-01-21", "treatment_plans.master.signatures[0]"),
        )
    })})

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert _criterion_status(bundle, "initial_plan_dated_correctly") == "Compliant"
    assert _criterion_status(bundle, "master_plan_within_30_days") == "Compliant"


def test_untyped_signature_evidence_never_satisfies_initial_or_master_criteria() -> None:
    # Given
    package = load_rule_package()

    # When
    aggregate = _aggregate()
    untyped = tuple(item.model_copy(update={"evidence_role": "unknown"}) for item in aggregate.content_snapshot.signatures)
    aggregate = aggregate.model_copy(update={
        "content_snapshot": aggregate.content_snapshot.model_copy(update={"signatures": untyped}),
    })
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert _criterion_status(bundle, "initial_plan_required_signatures") in {"Missing Data", "Needs Review"}
    assert _criterion_status(bundle, "master_plan_required_signatures") in {"Missing Data", "Needs Review"}
    assert bundle.overall_status != "Current/Compliant"


def test_malformed_signature_mixed_with_valid_role_evidence_fails_closed() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate().model_copy(update={"content_snapshot": _aggregate().content_snapshot.model_copy(update={
        "signatures": (
            _signature("initial_plan", "2026-01-01", "treatment_plans.initial.signatures[0]"),
            _signature("master_plan", "2026-01-20", "treatment_plans.master.signatures[0]"),
            _signature("review", "not-a-date", "treatment_reviews[0].signatures[0]"),
        )
    })})

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.overall_status == "Conflicting Evidence"


def test_future_signed_review_fails_closed() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate(due="2027-02-01").model_copy(update={
        "treatment_reviews": ({"review_date": "2027-01-02", "signature_date": "2027-01-02"},)
    })

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.overall_status == "Needs Review"


def test_missing_source_due_and_absent_plan_records_fail_closed() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate(due="Unknown").model_copy(update={"treatment_plans": (), "active_treatment_plans": ()})

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.overall_status == "Missing Data"


def test_current_loc_conflicting_with_only_loc_history_fails_closed() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate(loc="PHP").model_copy(update={
        "loc_history": ({"level_of_care": "IOP", "effective_date": "2026-01-01"},)
    })

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert bundle.overall_status == "Conflicting Evidence"


def test_loc_change_candidate_is_display_only_and_recurring_due_remains_active() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate().model_copy(update={"loc_history": (
        {"level_of_care": "IOP", "effective_date": "2025-12-01"},
        {"level_of_care": "PHP", "effective_date": "2026-01-10"},
    )})

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 11), "America/New_York")

    # Then
    assert bundle.overall_status == "Needs Review"
    assert bundle.calculated_due_date == "2026-01-31"
    assert bundle.loc_change_candidate_date == "2026-01-17"
    assert _criterion_status(bundle, "loc_change_deadline_unresolved") == "Needs Review"


def test_canonical_count_versions_paths_and_privacy_are_preserved() -> None:
    # Given
    package = load_rule_package()
    aggregate = _aggregate().model_copy(update={"patient_display_label": "PRIVACY-CANARY-NAME"})

    # When
    bundle = evaluate_plan_version(aggregate, package, date(2026, 1, 2), "America/New_York")

    # Then
    assert len(bundle.criteria) == 42
    assert bundle.checklist_version == "1.2.0"
    assert bundle.rules_version == "1.2.0"
    assert all(item.normalized_path and item.explanation for item in bundle.criteria)
    assert "PRIVACY-CANARY-NAME" not in repr(bundle)


def test_facility_local_date_handles_dst_transition() -> None:
    # Given
    before_local_midnight = datetime(2026, 3, 8, 4, 30, tzinfo=timezone.utc)
    after_spring_forward = datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc)

    # When/Then
    assert facility_local_date(before_local_midnight, "America/New_York") == date(2026, 3, 7)
    assert facility_local_date(after_spring_forward, "America/New_York") == date(2026, 3, 8)


def test_local_machine_timezone_sentinel_uses_windows_local_date() -> None:
    # Given
    instant = datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc)

    # When/Then
    assert facility_local_date(instant, "local_machine") == instant.astimezone().date()


def test_malformed_rules_fail_closed_with_safe_error(tmp_path) -> None:
    # Given
    malformed = tmp_path / "rules.yaml"
    malformed.write_text("levels_of_care: [", encoding="utf-8")

    # When/Then
    with pytest.raises(RuleConfigurationError, match="rules.yaml"):
        load_rule_package(rules_path=malformed)
