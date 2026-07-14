from __future__ import annotations

import hashlib

from app.v2.domain.schemas import (
    JsonValue,
    ReviewStatus,
    TreatmentPlanAggregate,
    TreatmentPlanContentSnapshot,
    TreatmentPlanEvidenceCoverage,
    TreatmentPlanGoal,
    TreatmentPlanIntervention,
    TreatmentPlanObjective,
    TreatmentPlanObservedField,
    TreatmentPlanProblem,
    TreatmentPlanSignatureMetadata,
)
from app.v2.services.manual_file_criteria import (
    criteria_from_parsed,
    evidence_ref,
    missing_sections,
    present_sections,
    preview,
)
from app.v2.services.manual_file_types import ParsedManualFields


def build_manual_aggregate(parsed: ParsedManualFields) -> TreatmentPlanAggregate:
    criteria = criteria_from_parsed(parsed)
    snapshot = _content_snapshot(parsed)
    sections_present = present_sections(parsed)
    coverage = TreatmentPlanEvidenceCoverage(
        plan_id=snapshot.plan_id,
        patient_id=parsed.patient_id,
        criteria_total=42,
        criteria_with_evidence=sum(1 for criterion in criteria if criterion.evidence_refs),
        criteria_missing_evidence=sum(1 for criterion in criteria if criterion.result_status == "Missing Data"),
        criteria_conflicting=sum(1 for criterion in criteria if criterion.result_status == "Conflicting Evidence"),
        content_sections_present=sections_present,
        content_sections_missing=missing_sections(sections_present),
        unmapped_runtime_fields=(),
        unused_content_fields=(),
        swagger_only_fields=("TreatmentReview.nextReviewDue",),
        runtime_only_fields=(),
        warnings=("LOC-change update window remains unvalidated and configurable.", *parsed.data_quality_warnings),
    )
    return TreatmentPlanAggregate(
        patient_id=parsed.patient_id,
        patient_display_label=f"Patient ID {parsed.patient_id}",
        source_mode="manual_upload",
        active_status="active",
        status_id=0,
        status_label="Manual upload",
        current_level_of_care=parsed.level_of_care,
        mapped_level_of_care=parsed.level_of_care,
        admission_date=parsed.admission_date,
        loc_history=(_source_row(parsed.level_of_care, parsed.admission_date),),
        treatment_plans=({"plan_id": snapshot.plan_id, "is_active": True, "source": "manual_upload_file"},),
        active_treatment_plans=({"plan_id": snapshot.plan_id, "is_active": True},),
        latest_created_active_plan={"plan_id": snapshot.plan_id, "label": "manual upload parsed file"},
        has_multiple_active_plans=False,
        current_plan_selection_reason="manual upload parsed treatment-plan file",
        treatment_review_data_status="manual_upload_parsed" if parsed.parsed_source_count else "manual_upload_opaque_only",
        next_review_due_source="manual_upload_file" if parsed.due_date != "Unknown" else "unavailable",
        date_clock_anchor=parsed.admission_date,
        date_clock_due_date=parsed.due_date,
        source_due_date=parsed.due_date,
        loc_change_due_date="unvalidated_configurable",
        overall_status=_overall_status(parsed),
        overall_status_reason=_overall_status_reason(parsed),
        data_quality_warnings=_data_quality_warnings(parsed),
        source_evidence=(
            evidence_ref(
                "manual-upload-binder",
                "Manual upload binder",
                "manual_upload",
                "Bounded manual source evidence was processed deterministically.",
            ),
        ),
        content_snapshot_summary=_snapshot_summary(parsed),
        content_sections_present=sections_present,
        content_sections_missing=missing_sections(sections_present),
        criteria_results=criteria,
        manager_reviews=(),
        overrides=(),
        audit_refs=("manual_upload.treatment_plan_file.imported",),
        evidence_coverage_summary=coverage,
        content_snapshot=snapshot,
    )


def _content_snapshot(parsed: ParsedManualFields) -> TreatmentPlanContentSnapshot:
    intervention = TreatmentPlanIntervention(
        intervention_number="1",
        intervention_description=parsed.intervention_description,
        source_json_path=_intervention_path(),
    )
    objective = TreatmentPlanObjective(
        objective_number="1",
        objective_description=parsed.objective_description,
        source_json_path="content_snapshot.problems[0].goals[0].objectives[0].objective_description",
        interventions=(intervention,),
    )
    goal = TreatmentPlanGoal(
        goal_number="1",
        goal_description=parsed.goal_description,
        source_json_path="content_snapshot.problems[0].goals[0].goal_description",
        objectives=(objective,),
    )
    problem = TreatmentPlanProblem(
        problem_number="1",
        problem_description=parsed.problem_description,
        source_json_path="content_snapshot.problems[0].problem_description",
        diagnoses=(_diagnosis(parsed),),
        behavioral_definitions=(_behavioral_definition(parsed),),
        goals=(goal,),
    )
    content_hash = hashlib.sha256(f"{parsed.patient_id}|{parsed.raw_text}".encode("utf-8")).hexdigest()
    return TreatmentPlanContentSnapshot(
        plan_id=f"manual-{parsed.patient_id}-{content_hash[:8]}",
        patient_id=parsed.patient_id,
        source_mode="manual_upload",
        reason_for_admission=parsed.reason_for_admission,
        initial_client_needs=parsed.initial_client_needs,
        family_education_needs=parsed.family_education_needs,
        redaction_status="patient_names_excluded",
        content_hash=content_hash,
        problems=(problem,),
        signatures=(_signature(parsed),),
        observed_fields=_observed_fields(parsed),
    )


def _observed_fields(parsed: ParsedManualFields) -> tuple[TreatmentPlanObservedField, ...]:
    rows = [
        ("reason_for_admission", parsed.reason_for_admission, "content_snapshot.reason_for_admission", True),
        ("initial_client_needs", parsed.initial_client_needs, "content_snapshot.initial_client_needs", True),
        ("family_education_needs", parsed.family_education_needs, "content_snapshot.family_education_needs", True),
        ("intervention_description", parsed.intervention_description, _intervention_path(), True),
        ("signature_datetime", parsed.signature_datetime, "content_snapshot.signatures[0].signature_datetime", True),
    ]
    if parsed.patient_id_correction_applied:
        rows.append(("patient_id_assignment", "Manual patient ID correction confirmed.", "patient_id", True))
    return tuple(
        TreatmentPlanObservedField(
            field_path=field_path,
            value_type="string",
            state="present" if value.strip() else "missing",
            sample_redacted_value=preview(value) if value.strip() else "",
            source_endpoint="manual_upload://parsed-treatment-plan-file",
            occurrence_count=1 if value.strip() else 0,
            used_by_checklist=used_by_checklist,
            mapped_app_field=mapped_app_field,
        )
        for field_path, value, mapped_app_field, used_by_checklist in rows
    )


def _data_quality_warnings(parsed: ParsedManualFields) -> tuple[str, ...]:
    parser_warning = "Manual parser accepts labeled fields only; unsupported content remains explicitly unevaluated."
    correction_warning = (
        ("Patient ID correction was confirmed before this manual binder was imported.",)
        if parsed.patient_id_correction_applied
        else ()
    )
    return tuple(dict.fromkeys((parser_warning, *parsed.data_quality_warnings, *correction_warning)))


def _overall_status(parsed: ParsedManualFields) -> ReviewStatus:
    if parsed.parsed_source_count == 0:
        return "Unable to Evaluate"
    if parsed.conflicting_fields:
        return "Conflicting Evidence"
    return "Needs Review"


def _overall_status_reason(parsed: ParsedManualFields) -> str:
    if parsed.parsed_source_count == 0:
        return "The binder contained only opaque sources; no clinical content was deterministically evaluated."
    if parsed.conflicting_fields:
        return "Conflicting scalar evidence requires manager resolution; file order was not used to select a value."
    return "Manual binder evidence was parsed into the V2 aggregate; manager review remains required."


def _snapshot_summary(parsed: ParsedManualFields) -> dict[str, JsonValue]:
    return {
        "problem_count": 1 if parsed.problem_description else 0,
        "diagnosis_count": 1 if parsed.diagnosis_description else 0,
        "goal_count": 1 if parsed.goal_description else 0,
        "objective_count": 1 if parsed.objective_description else 0,
        "intervention_count": 1 if parsed.intervention_description else 0,
        "signature_metadata_count": 1 if parsed.signature_datetime else 0,
    }


def _source_row(level_of_care: str, effective_date: str) -> dict[str, JsonValue]:
    return {"level_of_care": level_of_care, "effective_date": effective_date, "source": "manual_upload_file"}


def _diagnosis(parsed: ParsedManualFields) -> dict[str, JsonValue]:
    return {
        "diagnosis_number": "1",
        "diagnosis_description": parsed.diagnosis_description,
        "icd10_code": parsed.icd10_code,
        "is_primary": True,
        "is_active": True,
    }


def _behavioral_definition(parsed: ParsedManualFields) -> dict[str, JsonValue]:
    return {
        "behavioral_definition_number": "1",
        "behavioral_definition": parsed.behavioral_definition,
        "source_json_path": "content_snapshot.problems[0].behavioral_definitions[0].behavioral_definition",
    }


def _signature(parsed: ParsedManualFields) -> TreatmentPlanSignatureMetadata:
    return TreatmentPlanSignatureMetadata(
        signature_type="parsed_manual_signature",
        has_signature_data=bool(parsed.signature_datetime),
        signer_role_or_type="unknown",
        signature_datetime=parsed.signature_datetime,
        signature_data_length=0,
        signature_data_omitted_reason="manual upload parser stores signature timestamp only",
    )


def _intervention_path() -> str:
    return "content_snapshot.problems[0].goals[0].objectives[0].interventions[0].intervention_description"
