from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.v2.domain.schemas import SourceMode, TreatmentPlanAggregate


class PlanModel(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)


class TreatmentPlanExportInput(PlanModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    plan_version_ids: tuple[Annotated[int, Field(strict=True, gt=0)], ...]
    source_mode: Literal["manual_upload", "alleva_rest_api"] | None = None


class TreatmentPlanListItemOut(PlanModel):
    full_name: str
    original_plan_reference: str
    service_date: str
    version_ordinal: int = Field(gt=0)
    last_updated: str
    is_current: bool
    plan_version_id: int = Field(gt=0)
    patient_record_id: int = Field(gt=0)
    patient_id: str
    patient_display_label: str
    treatment_plan_id: str
    current_level_of_care: str
    admission_date: str
    next_due_date: str
    status: str
    missing_criteria_count: int
    returned_criteria_count: int
    source_mode: str
    content_completeness_summary: dict[str, int]
    warnings: tuple[str, ...]


class TreatmentPlanListOut(PlanModel):
    items: tuple[TreatmentPlanListItemOut, ...]
    status_order: tuple[str, ...]


class TreatmentPlanDetailOut(TreatmentPlanAggregate):
    plan_version_id: int = Field(gt=0)
    patient_record_id: int = Field(gt=0)
    treatment_plan_id: str
    unassigned_manager_reviews: tuple[dict[str, JsonValue], ...] = ()


class PatientRosterTreatmentPlanOut(PlanModel):
    patient_record_id: int = Field(gt=0)
    plan_version_id: int = Field(gt=0)
    source_mode: SourceMode
    version_ordinal: int = Field(gt=0)
    original_plan_reference: str
    service_date: str
    treatment_plan_id: str
    last_updated: str


class PatientRosterItemOut(PlanModel):
    patient_record_id: int = Field(gt=0)
    mrn: str
    full_name: str
    source_mode: str
    lifecycle_state: str
    current_level_of_care: str
    treatment_plans: tuple[PatientRosterTreatmentPlanOut, ...]
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str


class PatientRosterOut(PlanModel):
    items: tuple[PatientRosterItemOut, ...]


class TreatmentPlanRosterItemOut(PlanModel):
    patient_record_id: int = Field(gt=0)
    plan_version_id: int = Field(gt=0)
    source_mode: SourceMode
    version_ordinal: int = Field(gt=0)
    original_plan_reference: str
    service_date: str
    treatment_plan_id: str
    mrn: str
    patient_key: str
    linked_to_mrn: bool
    full_name: str
    last_updated: str
    previous_treatment_plan_id: str
    initial_treatment_plan_id: str
    initial_treatment_plan_date: str


class TreatmentPlanRosterOut(PlanModel):
    items: tuple[TreatmentPlanRosterItemOut, ...]


class PatientRecordDetailOut(PlanModel):
    patient_record_id: int = Field(gt=0)
    mrn: str
    full_name: str
    source_mode: str
    lifecycle_state: str
    current_level_of_care: str
    source_last_updated: str
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str
    treatment_plans: tuple[PatientRosterTreatmentPlanOut, ...]
    patient_record: dict[str, JsonValue]


class ManagerActionInput(PlanModel):
    plan_version_id: int | None = Field(default=None, ge=1)
    patient_record_id: int | None = Field(default=None, ge=1)
    source_mode: SourceMode | None = None
    treatment_plan_id: str | None = None
    criterion_id: str
    action: Literal["approve", "return_for_correction", "override", "comment"]
    comment: str = ""
    override_reason: str = ""
    assigned_counselor_username: str = ""


class CorrectionSubmissionInput(PlanModel):
    plan_version_id: int | None = Field(default=None, ge=1)
    patient_record_id: int | None = Field(default=None, ge=1)
    source_mode: SourceMode | None = None
    treatment_plan_id: str | None = None
    work_item_id: int
    criterion_id: str
    comment: str = Field(min_length=1)


class CorrectionQueueItemOut(PlanModel):
    work_item_id: int
    plan_version_id: int = Field(gt=0)
    patient_record_id: int = Field(gt=0)
    source_mode: str
    treatment_plan_id: str
    patient_id: str
    patient_display_label: str
    criterion_id: str
    criterion_title: str
    return_comment: str
    returned_by_username: str
    returned_at: str


class CorrectionQueueOut(PlanModel):
    items: tuple[CorrectionQueueItemOut, ...]
