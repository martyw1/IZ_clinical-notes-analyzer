#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: with PYTHONPATH=backend, use the installed backend interpreter:
# python backend/tests/task8_coverage_fixtures.py <owned-evidence-output.json>
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Final, Literal

from app.v2.domain.schemas import TreatmentPlanAggregate, TreatmentPlanSignatureMetadata
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields

CaseName = Literal["empty", "partial", "full"]
# Literal input-derived oracle: key, empty/partial/full status, partial/full support.
# All empty-source support is false. No production extractor builds this table.
ORACLE: Final = (
    ("confirm_correct_client_chart", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("classify_new_or_update_review", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("confirm_client_active", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("confirm_admission_date", "Missing Data", "Present", "Present", True, True),
    ("confirm_current_loc", "Missing Data", "Missing Data", "Present", False, True),
    ("confirm_loc_rule_mapping", "Missing Data", "Missing Data", "Present", False, True),
    ("capture_loc_history", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("classify_source_documents", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("confirm_document_dates", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("confirm_document_completion_status", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("confirm_staff_signature_status", "Missing Data", "Missing Data", "Present", False, True),
    ("confirm_client_signature_status", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("check_conflicting_evidence", "Compliant", "Compliant", "Compliant", True, True),
    ("initial_plan_exists", "Missing Data", "Missing Data", "Present", False, True),
    ("initial_plan_dated_correctly", "Missing Data", "Missing Data", "Compliant", True, True),
    ("initial_plan_required_signatures", "Missing Data", "Missing Data", "Compliant", True, True),
    ("master_plan_exists", "Missing Data", "Missing Data", "Present", False, True),
    ("master_plan_within_30_days", "Missing Data", "Missing Data", "Compliant", True, True),
    ("master_plan_required_signatures", "Missing Data", "Missing Data", "Present", False, True),
    ("latest_valid_review_identified", "Missing Data", "Present", "Present", True, True),
    ("calculate_next_review_due_date", "Unable to Evaluate", "Unable to Evaluate", "Current/Compliant", True, True),
    ("apply_php_timing_rule", "Not Applicable", "Not Applicable", "Current/Compliant", False, False),
    ("apply_iop_op_timing_rule", "Not Applicable", "Not Applicable", "Not Applicable", False, False),
    ("mark_current_inside_window", "Not Applicable", "Not Applicable", "Current/Compliant", False, False),
    ("mark_due_soon", "Not Applicable", "Not Applicable", "Not Applicable", False, False),
    ("mark_overdue", "Not Applicable", "Not Applicable", "Not Applicable", False, False),
    ("check_php_individual_session_evidence", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("check_iop_op_individual_session_evidence", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("identify_loc_change", "Not Applicable", "Not Applicable", "Not Applicable", False, True),
    ("loc_change_update_document", "Not Applicable", "Not Applicable", "Not Applicable", False, False),
    ("loc_change_deadline_unresolved", "Not Applicable", "Not Applicable", "Not Applicable", False, False),
    ("flag_missing_data_not_compliance", "Missing Data", "Missing Data", "Compliant", False, False),
    ("allow_manual_reviewer_confirmation", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("require_manual_override_reason", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("produce_final_checklist_result", "Missing Data", "Missing Data", "Current/Compliant", False, False),
    ("update_status_worklist_after_review", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("route_chart_for_manager_review", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("return_chart_with_correction_comments", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("approve_after_issues_resolved_or_accepted", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("preserve_review_history", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("continue_periodic_api_monitoring", "Needs Review", "Needs Review", "Needs Review", False, False),
    ("use_synthetic_or_approved_non_phi_data", "Needs Review", "Needs Review", "Needs Review", False, False),
)


def signature(role: Literal["initial_plan", "master_plan", "review", "unknown"], raw: str) -> TreatmentPlanSignatureMetadata:
    return TreatmentPlanSignatureMetadata(
        signature_type=role, has_signature_data=bool(raw), signer_role_or_type="clinician",
        signature_datetime=raw, signature_data_length=0, signature_data_omitted_reason="synthetic metadata only",
        evidence_role=role, source_json_path=f"source.signatures.{role}",
    )


def source_fixture(case: CaseName) -> TreatmentPlanAggregate:
    supplied = case != "empty"
    full = case == "full"
    parsed = ParsedManualFields(
        patient_id="TEST-METRICS-001", patient_id_correction_applied=False,
        level_of_care="PHP" if full else "Unknown", admission_date="2026-01-01" if supplied else "",
        due_date="2026-01-31" if full else "", reason_for_admission="", initial_client_needs="",
        family_education_needs="", problem_description="", diagnosis_description="", icd10_code="",
        behavioral_definition="", goal_description="", objective_description="", intervention_description="",
        signature_datetime="", raw_text="Synthetic Task 8 source fixture.",
    )
    aggregate = build_manual_aggregate(parsed)
    plans = ({"plan_id": "source-plan", "plan_kind": "initial_plan", "plan_date": "2026-01-01"},) if full else ()
    signatures = (signature("initial_plan", "2026-01-01"), signature("master_plan", "2026-01-01")) if full else ()
    return aggregate.model_copy(update={
        "source_mode": "synthetic_fixture", "treatment_plans": plans, "active_treatment_plans": plans,
        "loc_history": ({"level_of_care": "PHP", "effective_date": "2026-01-01"},) if full else (),
        "source_evidence": (), "content_snapshot": aggregate.content_snapshot.model_copy(update={"signatures": signatures}),
    })


def capture_clinical(path: Path) -> None:
    """Capture legacy bundle fields, excluding only the newly added support metadata."""
    from app.v2.services.deterministic_evaluator import evaluate_plan_version
    from app.v2.services.rule_package import load_rule_package

    cases = {name: source_fixture(name) for name in ("empty", "partial", "full")}
    full = source_fixture("full")
    cases.update({
        "invalid_due": full.model_copy(update={"source_due_date": "not-a-date"}),
        "conflicting_due": full.model_copy(update={"source_due_date": "2026-02-01"}),
        "unknown_loc": full.model_copy(update={"current_level_of_care": "Unknown", "loc_history": ()}),
        "invalid_signature": full.model_copy(update={"content_snapshot": full.content_snapshot.model_copy(update={
            "signatures": (signature("initial_plan", "not-a-date"), signature("master_plan", "2026-01-01")),
        })}),
        "loc_change": full.model_copy(update={"loc_history": (
            {"level_of_care": "IOP", "effective_date": "2025-12-01"},
            {"level_of_care": "PHP", "effective_date": "2026-01-01"},
        )}),
        "future_review": full.model_copy(update={"treatment_reviews": ({"review_date": "2027-01-01", "signed": True},)}),
    })
    observations = {}
    for name, aggregate in cases.items():
        for day in (date(2026, 1, 2), date(2026, 1, 23), date(2026, 1, 24), date(2026, 1, 29),
                    date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1)):
            result = asdict(evaluate_plan_version(aggregate, load_rule_package(), day, "America/New_York"))
            for criterion in result["criteria"]:
                criterion.pop("observed_sources", None)
            observations[f"{name}:{day.isoformat()}"] = result
    path.write_text(json.dumps(observations, sort_keys=True, indent=2), encoding="utf-8")


if __name__ == "__main__":
    capture_clinical(Path(sys.argv[1]))
