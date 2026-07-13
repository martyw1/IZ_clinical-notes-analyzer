from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import timezone
from enum import StrEnum
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.models import User, utc_now
from app.v2.services.manager_action_store import (
    manager_override_dicts_for_patient,
    manager_review_dicts_for_patient,
    open_correction_counts_by_patient,
)
from app.v2.services.manual_source_file_store import source_documents_for_patient
from app.core.config import settings
from app.v2.services.clinical_snapshot_codec import ClinicalSnapshotCodec
from app.v2.services.clinical_evidence_store import persist_clinical_evidence
from app.v2.services.evaluation_store import PlanEvaluationTarget, latest_evaluated_aggregate, persist_plan_evaluation
from app.v2.services.migrated_treatment_plan import assemble_treatment_plan_aggregate
from app.v2.services.alleva_contracts import SyncImportProvenance

TREATMENT_PLAN_STATUS_ORDER: Final = (
    "Missing Data",
    "Conflicting Evidence",
    "Unable to Evaluate",
    "Needs Review",
    "Overdue",
    "Urgent",
    "Due Soon",
    "Current/Compliant",
    "Incomplete",
)


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


def list_treatment_plan_imports(db: Session) -> tuple[StoredTreatmentPlan, ...]:
    rows = db.execute(
        text(
            "SELECT p.canonical_client_id,v.source_record_id,MAX(v.imported_at),MAX(v.id) FROM patients p "
            "JOIN treatment_plan_versions v ON v.patient_id=p.id "
            "GROUP BY p.id,p.canonical_client_id,v.source_system,v.source_record_id "
            "ORDER BY MAX(v.imported_at) DESC,MAX(v.id) DESC"
        )
    ).all()
    aggregates = tuple(
        assemble_treatment_plan_aggregate(db, str(row[0]), settings.effective_data_encryption_secret, str(row[1]))
        for row in rows
    )
    return tuple(_stored_plan(latest_evaluated_aggregate(db, aggregate)) for aggregate in aggregates if aggregate is not None)


def list_treatment_plan_queue_items(db: Session) -> tuple[TreatmentPlanQueueItem, ...]:
    correction_counts = open_correction_counts_by_patient(db)
    return tuple(_queue_item_from_import(row, correction_counts.get(row.patient_id, 0)) for row in list_treatment_plan_imports(db))


def save_treatment_plan_aggregate(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    actor: User,
    sync_provenance: SyncImportProvenance | None = None,
) -> StoredTreatmentPlan:
    return save_treatment_plan_aggregate_with_disposition(
        db,
        aggregate,
        actor,
        sync_provenance=sync_provenance,
    ).stored_plan


def save_treatment_plan_aggregate_with_disposition(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    actor: User,
    sync_provenance: SyncImportProvenance | None = None,
) -> TreatmentPlanSaveResult:
    aggregate = aggregate.model_copy(update={"patient_display_label": f"Patient ID {aggregate.patient_id}"})
    payload_json = aggregate.model_dump_json()
    encrypted_payload = ClinicalSnapshotCodec(settings.effective_data_encryption_secret).encode_aggregate(aggregate)
    content_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    evidence_sha256 = hashlib.sha256(
        f"{aggregate.patient_id}:{aggregate.source_mode}:{aggregate.content_snapshot.plan_id}:{content_sha256}".encode("utf-8")
    ).hexdigest()
    now = utc_now().astimezone(timezone.utc).isoformat()
    facility_id = int(db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one())
    db.execute(
        text(
            """INSERT OR IGNORE INTO patients(
                facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at
            ) VALUES(:facility_id,:client_id,:source_system,'active',:seen_at,:seen_at)"""
        ),
        {"facility_id": facility_id, "client_id": aggregate.patient_id, "source_system": aggregate.source_mode, "seen_at": now},
    )
    patient_id = int(
        db.execute(
            text(
                "SELECT id FROM patients WHERE facility_id=:facility_id AND source_system=:source_system AND canonical_client_id=:client_id"
            ),
            {"facility_id": facility_id, "source_system": aggregate.source_mode, "client_id": aggregate.patient_id},
        ).scalar_one()
    )
    latest = db.execute(
        text(
            "SELECT id,version_ordinal FROM treatment_plan_versions WHERE patient_id=:patient_id ORDER BY version_ordinal DESC,id DESC LIMIT 1"
        ),
        {"patient_id": patient_id},
    ).first()
    version_ordinal = int(latest[1]) + 1 if latest else 1
    prior_same_plan = db.execute(
        text(
            "SELECT id,content_sha256 FROM treatment_plan_versions "
            "WHERE patient_id=:patient_id AND source_system=:source_system AND source_record_id=:source_record_id "
            "ORDER BY version_ordinal DESC,id DESC LIMIT 1"
        ),
        {
            "patient_id": patient_id,
            "source_system": aggregate.source_mode,
            "source_record_id": aggregate.content_snapshot.plan_id,
        },
    ).first()
    if prior_same_plan is not None and str(prior_same_plan[1]) == content_sha256:
        return TreatmentPlanSaveResult(_stored_plan(aggregate), TreatmentPlanSaveDisposition.UNCHANGED)
    supersedes_version_id = int(prior_same_plan[0]) if prior_same_plan else None
    disposition = (
        TreatmentPlanSaveDisposition.UPDATED
        if prior_same_plan is not None
        else TreatmentPlanSaveDisposition.CREATED
    )
    db.execute(
        text(
            """INSERT OR IGNORE INTO treatment_plan_versions(
                patient_id,source_system,source_record_id,version_ordinal,plan_date,signature_date,admission_date,source_next_review_due,
                normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at,supersedes_version_id,
                sync_job_id,approval_record_id,contract_version,contract_sha256
            ) VALUES(:patient_id,:source_system,:source_record_id,:version_ordinal,:plan_date,:signature_date,:admission_date,:next_due,
                :payload,:content_sha256,:evidence_sha256,:imported_at,:supersedes_version_id,
                :sync_job_id,:approval_record_id,:contract_version,:contract_sha256)"""
        ),
        {
            "patient_id": patient_id,
            "source_system": aggregate.source_mode,
            "source_record_id": aggregate.content_snapshot.plan_id,
            "version_ordinal": version_ordinal,
            "plan_date": aggregate.date_clock_anchor,
            "signature_date": _signature_date(aggregate),
            "admission_date": aggregate.admission_date,
            "next_due": aggregate.date_clock_due_date,
            "payload": encrypted_payload,
            "content_sha256": content_sha256,
            "evidence_sha256": evidence_sha256,
            "imported_at": now,
            "supersedes_version_id": supersedes_version_id,
            **_provenance_values(sync_provenance),
        },
    )
    plan_version_id = int(db.execute(
        text(
            "SELECT id FROM treatment_plan_versions WHERE patient_id=:patient_id AND source_system=:source_system "
            "AND source_record_id=:source_record_id AND content_sha256=:content_sha256"
        ),
        {
            "patient_id": patient_id, "source_system": aggregate.source_mode,
            "source_record_id": aggregate.content_snapshot.plan_id, "content_sha256": content_sha256,
        },
    ).scalar_one())
    trigger = "sync" if aggregate.source_mode == "alleva_rest_api" else "import"
    evaluated = persist_plan_evaluation(db, aggregate, PlanEvaluationTarget(plan_version_id, evidence_sha256), trigger, sync_provenance=sync_provenance)
    events = persist_clinical_evidence(db, aggregate, patient_id, plan_version_id, now, sync_provenance)
    if events.loc_change:
        evaluated = persist_plan_evaluation(db, aggregate, PlanEvaluationTarget(plan_version_id, evidence_sha256), "loc_change", sync_provenance=sync_provenance)
    if events.new_review:
        evaluated = persist_plan_evaluation(db, aggregate, PlanEvaluationTarget(plan_version_id, evidence_sha256), "new_review", sync_provenance=sync_provenance)
    db.commit()
    return TreatmentPlanSaveResult(_stored_plan(evaluated), disposition)


def treatment_plan_aggregate_for_patient(
    db: Session,
    patient_id: str,
    treatment_plan_id: str | None = None,
) -> TreatmentPlanAggregate | None:
    aggregate = assemble_treatment_plan_aggregate(
        db,
        patient_id,
        settings.effective_data_encryption_secret,
        treatment_plan_id,
    )
    if aggregate is None:
        return None
    aggregate = latest_evaluated_aggregate(db, aggregate)
    source_documents = source_documents_for_patient(db, patient_id)
    persisted_reviews = manager_review_dicts_for_patient(db, patient_id)
    if not persisted_reviews and not source_documents:
        return aggregate
    return aggregate.model_copy(
        update={
            "manager_reviews": aggregate.manager_reviews + persisted_reviews,
            "overrides": aggregate.overrides + manager_override_dicts_for_patient(db, patient_id),
            "source_documents": source_documents,
        }
    )


def _queue_item_from_import(row: StoredTreatmentPlan, returned_criteria_count: int) -> TreatmentPlanQueueItem:
    return TreatmentPlanQueueItem(
        patient_id=row.patient_id,
        patient_display_label=row.patient_display_label,
        treatment_plan_id=row.plan_id,
        current_level_of_care=row.current_level_of_care,
        admission_date=row.admission_date,
        next_due_date=row.next_due_date,
        status=row.overall_status,
        missing_criteria_count=row.missing_criteria_count,
        returned_criteria_count=returned_criteria_count,
        source_mode=row.source_mode,
        content_completeness_summary=_int_map(row.content_summary_json),
        warnings=_string_tuple(row.warnings_json),
    )


def _returned_criteria_count(aggregate: TreatmentPlanAggregate) -> int:
    return sum(1 for review in aggregate.manager_reviews if review.get("manager_status") == "Returned")


def _content_summary_json(aggregate: TreatmentPlanAggregate) -> str:
    summary = {
        key: value
        for key, value in aggregate.content_snapshot_summary.items()
        if isinstance(value, int)
    }
    return json.dumps(summary, sort_keys=True)


def _int_map(raw_json: str) -> dict[str, int]:
    payload = json.loads(raw_json or "{}")
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, int)}


def _string_tuple(raw_json: str) -> tuple[str, ...]:
    payload = json.loads(raw_json or "[]")
    if not isinstance(payload, list):
        return ()
    return tuple(value for value in payload if isinstance(value, str))


def _stored_plan(aggregate: TreatmentPlanAggregate) -> StoredTreatmentPlan:
    return StoredTreatmentPlan(
        patient_id=aggregate.patient_id,
        patient_display_label=aggregate.patient_display_label,
        plan_id=aggregate.content_snapshot.plan_id,
        source_mode=aggregate.source_mode,
        current_level_of_care=aggregate.current_level_of_care,
        admission_date=aggregate.admission_date,
        next_due_date=aggregate.date_clock_due_date,
        overall_status=aggregate.overall_status,
        missing_criteria_count=aggregate.evidence_coverage_summary.criteria_missing_evidence,
        content_summary_json=_content_summary_json(aggregate),
        warnings_json=json.dumps(list(aggregate.data_quality_warnings), sort_keys=True),
    )


def _signature_date(aggregate: TreatmentPlanAggregate) -> str | None:
    dates = tuple(item.signature_datetime for item in aggregate.content_snapshot.signatures if item.signature_datetime.strip())
    return max(dates, default=None)


def _provenance_values(provenance: SyncImportProvenance | None) -> dict[str, int | str | None]:
    if provenance is None:
        return {"sync_job_id": None, "approval_record_id": None, "contract_version": None, "contract_sha256": None}
    return {
        "sync_job_id": provenance.sync_job_id,
        "approval_record_id": provenance.approval_record_id,
        "contract_version": provenance.contract_version,
        "contract_sha256": provenance.contract_sha256,
    }
