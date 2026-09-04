from __future__ import annotations

from typing import assert_never

from app.v2.domain.schemas import ContentEvidenceRef, SourceMode, TreatmentPlanAggregate, TreatmentPlanCriterionResult
from app.v2.services.deterministic_evaluator import CriterionEvaluation, EvaluationBundle


def apply_evaluation(aggregate: TreatmentPlanAggregate, bundle: EvaluationBundle) -> TreatmentPlanAggregate:
    source_endpoint = _source_endpoint(aggregate.source_mode)
    criteria = tuple(_api_criterion(item, source_endpoint) for item in bundle.criteria)
    coverage = aggregate.evidence_coverage_summary.model_copy(update={
        "criteria_total": len(criteria),
        "criteria_with_evidence": sum(bool(item.observed_sources) for item in bundle.criteria),
        "criteria_missing_evidence": sum(item.result_status == "Missing Data" for item in criteria),
        "criteria_conflicting": sum(item.result_status == "Conflicting Evidence" for item in criteria),
    })
    return aggregate.model_copy(update={
        "mapped_level_of_care": bundle.mapped_level_of_care or "Unknown",
        "date_clock_anchor": bundle.recurring_anchor or "Unknown",
        "date_clock_due_date": bundle.calculated_due_date or "Unknown",
        "source_due_date": bundle.source_due_date or "Unknown",
        "loc_change_due_date": bundle.loc_change_candidate_date or "unvalidated_configurable",
        "overall_status": bundle.overall_status,
        "overall_status_reason": bundle.overall_explanation,
        "criteria_results": criteria,
        "evidence_coverage_summary": coverage,
        "checklist_version": bundle.checklist_version,
        "rules_version": bundle.rules_version,
        "evaluation_date": bundle.evaluation_date,
        "facility_timezone": bundle.facility_timezone,
    })


def _api_criterion(item: CriterionEvaluation, source_endpoint: str) -> TreatmentPlanCriterionResult:
    evidence = tuple(ContentEvidenceRef(
        ref_id=f"{item.criterion_id}:{index}", label=item.criterion_title, source_json_path=source.source_path,
        source_endpoint=source_endpoint,
        safe_preview="Observed source input. Its presence does not establish validity, completeness, or compliance.",
        redaction_status="safe_evidence_only",
    ) for index, source in enumerate(item.observed_sources))
    safe_statuses = {"Present", "Compliant", "Current/Compliant", "Not Applicable"}
    return TreatmentPlanCriterionResult(
        criterion_id=item.criterion_id, criterion_title=item.criterion_title, result_status=item.status,
        severity="info" if item.status in safe_statuses else "high", finding_message=item.explanation,
        content_considered=(item.normalized_path,), evidence_refs=evidence,
        missing_content_refs=(item.normalized_path,) if item.status == "Missing Data" else (),
        conflict_refs=(item.normalized_path,) if item.status == "Conflicting Evidence" else (),
        source_json_paths=(item.normalized_path,), source_endpoint=source_endpoint,
        redaction_status="safe_evidence_only",
        manager_action_options=("approve criterion", "return criterion for correction", "override with reason"),
    )


def _source_endpoint(source_mode: SourceMode) -> str:
    match source_mode:
        case "manual_upload":
            return "manual_upload://parsed-treatment-plan-file"
        case "alleva_rest_api":
            return "Alleva REST"
        case "synthetic_fixture":
            return "synthetic_fixture"
        case unreachable:
            assert_never(unreachable)
