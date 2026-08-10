from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.config import REPO_ROOT
from app.v2.domain.schemas import (
    ContentEvidenceRef,
    TreatmentPlanAggregate,
    TreatmentPlanContentSnapshot,
    TreatmentPlanCriterionResult,
    TreatmentPlanEvidenceCoverage,
    TreatmentPlanGoal,
    TreatmentPlanIntervention,
    TreatmentPlanObjective,
    TreatmentPlanObservedField,
    TreatmentPlanProblem,
    TreatmentPlanSignatureMetadata,
)

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def _load_checklist_steps() -> list[dict[str, JsonValue]]:
    checklist_path = REPO_ROOT / "config" / "checklists" / "treatment-plan-v1.json"
    payload = json.loads(checklist_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        return []
    return [step for step in raw_steps if isinstance(step, dict)]


def _text(value: JsonValue, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _int_text(value: JsonValue, fallback: int) -> str:
    return str(value) if isinstance(value, int) else str(fallback)


def _evidence(ref_id: str, label: str, path: str, preview: str) -> ContentEvidenceRef:
    return ContentEvidenceRef(
        ref_id=ref_id,
        label=label,
        source_json_path=path,
        source_endpoint="GET /treatment-plans?ClientId={patient_id}",
        safe_preview=preview,
        redaction_status="redacted_safe_preview",
    )


def content_snapshot() -> TreatmentPlanContentSnapshot:
    intervention = TreatmentPlanIntervention(
        intervention_number="1",
        intervention_description="Weekly CBT-based skills practice with progress review.",
        source_json_path="problems[0].goals[0].objectives[0].interventions[0].description",
    )
    objective = TreatmentPlanObjective(
        objective_number="1",
        objective_description="Identify three coping skills and practice them between sessions.",
        source_json_path="problems[0].goals[0].objectives[0].description",
        interventions=(intervention,),
    )
    goal = TreatmentPlanGoal(
        goal_number="1",
        goal_description="Improve recovery stability through measurable coping strategies.",
        source_json_path="problems[0].goals[0].description",
        objectives=(objective,),
    )
    problem = TreatmentPlanProblem(
        problem_number="1",
        problem_description="Substance-use recovery stabilization needs continued clinical support.",
        source_json_path="problems[0].description",
        diagnoses=(
            {
                "diagnosis_number": "1",
                "diagnosis_description": "Synthetic active diagnosis",
                "icd10_code": "F10.20",
                "is_primary": True,
                "is_active": True,
            },
        ),
        behavioral_definitions=(
            {
                "behavioral_definition_number": "1",
                "behavioral_definition": "Synthetic behavioral definition for treatment planning.",
                "source_json_path": "problems[0].behavioral_definitions[0].description",
            },
        ),
        goals=(goal,),
    )
    fields = (
        TreatmentPlanObservedField(
            field_path="reason_for_admission",
            value_type="string",
            state="present",
            sample_redacted_value="Clinical rationale present.",
            source_endpoint="GET /treatment-plans?ClientId={patient_id}",
            occurrence_count=1,
            used_by_checklist=True,
            mapped_app_field="content_snapshot.reason_for_admission",
        ),
        TreatmentPlanObservedField(
            field_path="signatures.staff.signatureData",
            value_type="string",
            state="redacted",
            sample_redacted_value="[signature image omitted]",
            source_endpoint="GET /treatment-plans/{id}",
            occurrence_count=1,
            used_by_checklist=False,
            mapped_app_field="signatures.has_signature_data",
        ),
    )
    hash_input = "PAT-307:TP-9001:synthetic-v2-content"
    return TreatmentPlanContentSnapshot(
        plan_id="TP-9001",
        patient_id="307",
        source_mode="synthetic_fixture",
        reason_for_admission="Synthetic clinical rationale is present for local validation.",
        initial_client_needs="Synthetic initial needs include stabilization and relapse prevention.",
        family_education_needs="Family education needs were reviewed as applicable.",
        redaction_status="patient_names_excluded",
        content_hash=hashlib.sha256(hash_input.encode("utf-8")).hexdigest(),
        problems=(problem,),
        signatures=(
            TreatmentPlanSignatureMetadata(
                signature_type="staff",
                has_signature_data=True,
                signer_role_or_type="clinician",
                signature_datetime="2026-07-01T15:30:00-04:00",
                signature_data_length=48291,
                signature_data_omitted_reason="signature image/base64 never returned in default browser payload",
            ),
        ),
        observed_fields=fields,
    )


def checklist_results() -> tuple[TreatmentPlanCriterionResult, ...]:
    steps = _load_checklist_steps()
    results: list[TreatmentPlanCriterionResult] = []
    for index, step in enumerate(steps[:42], start=1):
        step_number = _int_text(step.get("step"), index)
        key = _text(step.get("key"), f"criterion_{index}")
        title = _text(step.get("title"), f"Criterion {index}")
        path = "problems[0].goals[0].objectives[0].interventions[0].description"
        status = "Compliant"
        missing: tuple[str, ...] = ()
        evidence = (_evidence(key, title, path, "Nested treatment-plan content supports this criterion."),)
        if index in {8, 19, 27}:
            status = "Missing Data"
            missing = ("source_review_due_date",)
            evidence = ()
        if index == 12:
            status = "Needs Review"
        results.append(
            TreatmentPlanCriterionResult(
                criterion_id=key,
                criterion_title=title,
                result_status=status,
                severity="medium" if status != "Compliant" else "info",
                finding_message=f"Criterion {step_number}: {status}; evaluated from the V2 content graph.",
                content_considered=("diagnoses", "behavioral_definitions", "goals", "objectives", "interventions", "signatures"),
                evidence_refs=evidence,
                missing_content_refs=missing,
                conflict_refs=(),
                source_json_paths=(path,),
                source_endpoint="GET /treatment-plans?ClientId={patient_id}",
                redaction_status="safe_preview_only",
                manager_action_options=("approve criterion", "return criterion for correction", "override with reason"),
            )
        )
    return tuple(results)


def treatment_plan_aggregate() -> TreatmentPlanAggregate:
    snapshot = content_snapshot()
    criteria = checklist_results()
    present_sections = (
        "reason_for_admission",
        "initial_client_needs",
        "family_education_needs",
        "diagnoses",
        "behavioral_definitions",
        "goals",
        "objectives",
        "interventions",
        "signatures_metadata",
    )
    coverage = TreatmentPlanEvidenceCoverage(
        plan_id="TP-9001",
        patient_id="307",
        criteria_total=42,
        criteria_with_evidence=sum(1 for criterion in criteria if criterion.evidence_refs),
        criteria_missing_evidence=sum(1 for criterion in criteria if criterion.result_status == "Missing Data"),
        criteria_conflicting=0,
        content_sections_present=present_sections,
        content_sections_missing=("trusted_nextReviewDue",),
        unmapped_runtime_fields=("runtime_only.experimentalField",),
        unused_content_fields=("signatures.staff.signatureData",),
        swagger_only_fields=("TreatmentReview.nextReviewDue",),
        runtime_only_fields=("TreatmentPlan.runtimeNestedField",),
        warnings=("LOC-change update window remains unvalidated and configurable.",),
    )
    return TreatmentPlanAggregate(
        patient_id="307",
        patient_display_label="MRN 307",
        source_mode="synthetic_fixture",
        active_status="active",
        status_id=1049,
        status_label="Active",
        current_level_of_care="IOP",
        mapped_level_of_care="IOP",
        admission_date="2026-05-15",
        loc_history=({"level_of_care": "IOP", "effective_date": "2026-05-15", "source": "synthetic fixture"},),
        treatment_plans=({"plan_id": "TP-9001", "is_active": True, "is_complete": True},),
        active_treatment_plans=({"plan_id": "TP-9001", "is_active": True},),
        latest_created_active_plan={"plan_id": "TP-9001", "label": "latest-created active plan"},
        has_multiple_active_plans=False,
        current_plan_selection_reason="latest-created active plan from synthetic active set",
        treatment_review_data_status="unavailable_via_rest_without_known_review_id",
        next_review_due_source="unavailable",
        date_clock_anchor="2026-07-01",
        date_clock_due_date="2026-08-30",
        source_due_date="unavailable",
        loc_change_due_date="unvalidated_7_day_placeholder",
        overall_status="Needs Review",
        overall_status_reason="Synthetic plan has full content graph evidence and an unresolved LOC-change blocker.",
        data_quality_warnings=("nextReviewDue unavailable through REST without trusted review ID",),
        source_evidence=(_evidence("plan-client", "ClientId join", "client", "/clients/307 validated against ClientId=307"),),
        content_snapshot_summary={
            "problem_count": 1,
            "diagnosis_count": 1,
            "goal_count": 1,
            "objective_count": 1,
            "intervention_count": 1,
            "signature_metadata_count": 1,
        },
        content_sections_present=present_sections,
        content_sections_missing=("trusted_nextReviewDue",),
        criteria_results=criteria,
        manager_reviews=({"criterion_id": "confirm_current_loc", "manager_status": "Needs Review", "comment": "Synthetic LOC blocker visible."},),
        overrides=(),
        audit_refs=("api_harness.job.created", "treatment_plan.detail.viewed"),
        evidence_coverage_summary=coverage,
        content_snapshot=snapshot,
    )
