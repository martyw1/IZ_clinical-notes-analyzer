from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]

SourceMode = Literal["manual_upload", "alleva_rest_api", "synthetic_fixture"]
ReviewStatus = Literal[
    "Missing Data",
    "Needs Review",
    "Incomplete",
    "Within Window",
    "Late",
    "Conflicting Evidence",
    "Unable to Evaluate",
    "Compliant",
    "Approved",
    "Not Applicable",
]
JobStatus = Literal[
    "queued",
    "running",
    "writing",
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
    "stale_or_interrupted",
]


class V2Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class ContentEvidenceRef(V2Model):
    ref_id: str
    label: str
    source_json_path: str
    source_endpoint: str
    safe_preview: str
    redaction_status: str


class TreatmentPlanIntervention(V2Model):
    intervention_number: str
    intervention_description: str
    source_json_path: str
    is_wiley: bool = False
    is_evidence_based: bool = True


class TreatmentPlanObjective(V2Model):
    objective_number: str
    objective_description: str
    source_json_path: str
    interventions: tuple[TreatmentPlanIntervention, ...]


class TreatmentPlanGoal(V2Model):
    goal_number: str
    goal_description: str
    source_json_path: str
    objectives: tuple[TreatmentPlanObjective, ...]


class TreatmentPlanProblem(V2Model):
    problem_number: str
    problem_description: str
    source_json_path: str
    diagnoses: tuple[dict[str, JsonValue], ...]
    behavioral_definitions: tuple[dict[str, JsonValue], ...]
    goals: tuple[TreatmentPlanGoal, ...]


class TreatmentPlanSignatureMetadata(V2Model):
    signature_type: str
    has_signature_data: bool
    signer_role_or_type: str
    signature_datetime: str
    signature_data_length: int
    signature_data_omitted_reason: str


class TreatmentPlanObservedField(V2Model):
    field_path: str
    value_type: str
    state: str
    sample_redacted_value: str
    source_endpoint: str
    occurrence_count: int
    used_by_checklist: bool
    mapped_app_field: str


class TreatmentPlanContentSnapshot(V2Model):
    plan_id: str
    patient_id: str
    source_mode: SourceMode
    reason_for_admission: str
    initial_client_needs: str
    family_education_needs: str
    redaction_status: str
    content_hash: str
    problems: tuple[TreatmentPlanProblem, ...]
    signatures: tuple[TreatmentPlanSignatureMetadata, ...]
    observed_fields: tuple[TreatmentPlanObservedField, ...]


class TreatmentPlanCriterionResult(V2Model):
    criterion_id: str
    criterion_title: str
    result_status: ReviewStatus
    severity: str
    finding_message: str
    content_considered: tuple[str, ...]
    evidence_refs: tuple[ContentEvidenceRef, ...]
    missing_content_refs: tuple[str, ...]
    conflict_refs: tuple[str, ...]
    source_json_paths: tuple[str, ...]
    source_endpoint: str
    redaction_status: str
    manager_action_options: tuple[str, ...]


class TreatmentPlanEvidenceCoverage(V2Model):
    plan_id: str
    patient_id: str
    criteria_total: int
    criteria_with_evidence: int
    criteria_missing_evidence: int
    criteria_conflicting: int
    content_sections_present: tuple[str, ...]
    content_sections_missing: tuple[str, ...]
    unmapped_runtime_fields: tuple[str, ...]
    unused_content_fields: tuple[str, ...]
    swagger_only_fields: tuple[str, ...]
    runtime_only_fields: tuple[str, ...]
    warnings: tuple[str, ...]


class TreatmentPlanAggregate(V2Model):
    patient_id: str
    patient_display_label: str
    source_mode: SourceMode
    active_status: str
    status_id: int
    status_label: str
    current_level_of_care: str
    mapped_level_of_care: str
    admission_date: str
    loc_history: tuple[dict[str, JsonValue], ...]
    treatment_plans: tuple[dict[str, JsonValue], ...]
    active_treatment_plans: tuple[dict[str, JsonValue], ...]
    latest_created_active_plan: dict[str, JsonValue]
    has_multiple_active_plans: bool
    current_plan_selection_reason: str
    treatment_review_data_status: str
    next_review_due_source: str
    date_clock_anchor: str
    date_clock_due_date: str
    source_due_date: str
    loc_change_due_date: str
    overall_status: ReviewStatus
    overall_status_reason: str
    data_quality_warnings: tuple[str, ...]
    source_evidence: tuple[ContentEvidenceRef, ...]
    content_snapshot_summary: dict[str, JsonValue]
    content_sections_present: tuple[str, ...]
    content_sections_missing: tuple[str, ...]
    criteria_results: tuple[TreatmentPlanCriterionResult, ...] = Field(min_length=42, max_length=42)
    manager_reviews: tuple[dict[str, JsonValue], ...]
    overrides: tuple[dict[str, JsonValue], ...]
    audit_refs: tuple[str, ...]
    evidence_coverage_summary: TreatmentPlanEvidenceCoverage
    content_snapshot: TreatmentPlanContentSnapshot


class ApiHarnessArtifact(V2Model):
    artifact_id: str
    name: str
    media_type: str
    size_bytes: int
    redaction_mode: str


class ApiHarnessJob(V2Model):
    job_id: str
    job_type: str
    created_at: str
    started_at: str | None
    updated_at: str
    completed_at: str | None
    cancelled_at: str | None
    failed_at: str | None
    actor_id: str
    actor_role: str
    status: JobStatus
    progress_percent: int
    current_endpoint: str
    current_page: int
    current_cursor: str
    records_seen: int
    records_written: int
    records_failed: int
    warnings_count: int
    errors_count: int
    output_dir: str
    redaction_mode: str
    raw_sensitive_mode_used: bool
    cancel_requested: bool
    last_heartbeat_at: str
    artifacts: tuple[ApiHarnessArtifact, ...]


class JobPreview(V2Model):
    job_id: str
    max_records: int
    max_fields: int
    records: tuple[dict[str, JsonValue], ...]
    message: str
