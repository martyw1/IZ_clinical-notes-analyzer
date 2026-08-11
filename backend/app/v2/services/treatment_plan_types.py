from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from app.v2.domain.schemas import TreatmentPlanAggregate


@dataclass(frozen=True, slots=True)
class TreatmentPlanQueueItem:
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


@dataclass(frozen=True, slots=True)
class StoredTreatmentPlan:
    patient_id: str
    patient_display_label: str
    plan_id: str
    source_mode: str
    current_level_of_care: str
    admission_date: str
    plan_date: str
    last_updated: str
    next_due_date: str
    overall_status: str
    missing_criteria_count: int
    content_summary_json: str
    warnings_json: str


class TreatmentPlanSaveDisposition(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class TreatmentPlanSaveResult:
    stored_plan: StoredTreatmentPlan
    disposition: TreatmentPlanSaveDisposition


def stored_plan(
    aggregate: TreatmentPlanAggregate,
    *,
    last_updated: str = "",
    plan_date: str = "",
) -> StoredTreatmentPlan:
    summary = {
        key: value
        for key, value in aggregate.content_snapshot_summary.items()
        if isinstance(value, int)
    }
    return StoredTreatmentPlan(
        patient_id=aggregate.patient_id,
        patient_display_label=aggregate.patient_display_label,
        plan_id=aggregate.content_snapshot.plan_id,
        source_mode=aggregate.source_mode,
        current_level_of_care=aggregate.current_level_of_care,
        admission_date=aggregate.admission_date,
        plan_date=plan_date or aggregate.date_clock_anchor,
        last_updated=aggregate.source_last_updated,
        next_due_date=aggregate.date_clock_due_date,
        overall_status=aggregate.overall_status,
        missing_criteria_count=aggregate.evidence_coverage_summary.criteria_missing_evidence,
        content_summary_json=json.dumps(summary, sort_keys=True),
        warnings_json=json.dumps(list(aggregate.data_quality_warnings), sort_keys=True),
    )


def signature_date(aggregate: TreatmentPlanAggregate) -> str | None:
    dates = tuple(
        item.signature_datetime
        for item in aggregate.content_snapshot.signatures
        if item.signature_datetime.strip()
    )
    return max(dates, default=None)
