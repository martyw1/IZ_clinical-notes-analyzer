from __future__ import annotations

import hashlib
from datetime import timezone
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.models import User, utc_now
from app.core.config import settings
from app.v2.services.clinical_snapshot_codec import ClinicalSnapshotCodec
from app.v2.services.clinical_evidence_store import persist_clinical_evidence
from app.v2.services.evaluation_store import PlanEvaluationTarget, persist_plan_evaluation
from app.v2.services.alleva_contracts import SyncImportProvenance
from app.v2.services.treatment_plan_types import (
    StoredTreatmentPlan,
    PlanVersionIdentity,
    TreatmentPlanSaveDisposition,
    TreatmentPlanSaveResult,
    signature_date,
    stored_plan,
)

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


from app.v2.services.treatment_plan_read_model import (
    list_treatment_plan_imports, list_treatment_plan_queue_items,
    treatment_plan_aggregate_for_patient, treatment_plan_aggregate_for_version,
)


def save_treatment_plan_aggregate(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    actor: User,
    sync_provenance: SyncImportProvenance | None = None,
    source_patient_id: str | None = None,
    lifecycle_state: str = "active",
    *,
    commit: bool = True,
) -> StoredTreatmentPlan:
    return save_treatment_plan_aggregate_with_disposition(
        db,
        aggregate,
        actor,
        sync_provenance=sync_provenance,
        source_patient_id=source_patient_id,
        lifecycle_state=lifecycle_state,
        commit=commit,
    ).stored_plan


def save_treatment_plan_aggregate_with_disposition(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    actor: User,
    sync_provenance: SyncImportProvenance | None = None,
    source_patient_id: str | None = None,
    lifecycle_state: str = "active",
    *,
    commit: bool = True,
) -> TreatmentPlanSaveResult:
    now = utc_now().astimezone(timezone.utc).isoformat()
    patient_display_label = (
        aggregate.patient_display_label
        if aggregate.patient_display_label == "Not linked to an MRN"
        else f"MRN {aggregate.patient_id}"
    )
    aggregate = aggregate.model_copy(update={"patient_display_label": patient_display_label, "patient_full_name": ""})
    payload_json = aggregate.model_dump_json()
    encrypted_payload = ClinicalSnapshotCodec(settings.effective_data_encryption_secret).encode_aggregate(aggregate)
    content_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    evidence_sha256 = hashlib.sha256(
        f"{aggregate.patient_id}:{aggregate.source_mode}:{aggregate.content_snapshot.plan_id}:{content_sha256}".encode("utf-8")
    ).hexdigest()
    facility_id = int(db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one())
    db.execute(
        text(
            """INSERT OR IGNORE INTO patients(
                facility_id,canonical_client_id,source_patient_id,source_system,lifecycle_state,first_seen_at,last_seen_at
            ) VALUES(:facility_id,:client_id,:source_patient_id,:source_system,:lifecycle_state,:seen_at,:seen_at)"""
        ),
        {
            "facility_id": facility_id,
            "client_id": aggregate.patient_id,
            "source_patient_id": source_patient_id,
            "source_system": aggregate.source_mode,
            "lifecycle_state": lifecycle_state,
            "seen_at": now,
        },
    )
    patient_id = int(
        db.execute(
            text(
                "SELECT id FROM patients WHERE facility_id=:facility_id AND source_system=:source_system AND canonical_client_id=:client_id"
            ),
            {"facility_id": facility_id, "source_system": aggregate.source_mode, "client_id": aggregate.patient_id},
        ).scalar_one()
    )
    db.execute(
        text(
            "UPDATE patients SET source_patient_id=COALESCE(source_patient_id,:source_patient_id),"
            "lifecycle_state=:lifecycle_state,last_seen_at=:seen_at WHERE id=:patient_id"
        ),
        {
            "patient_id": patient_id,
            "source_patient_id": source_patient_id,
            "lifecycle_state": lifecycle_state,
            "seen_at": now,
        },
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
        identity = PlanVersionIdentity(int(prior_same_plan[0]), patient_id, aggregate.patient_id, aggregate.source_mode, aggregate.content_snapshot.plan_id)
        return TreatmentPlanSaveResult(stored_plan(aggregate, identity=identity, last_updated=now), TreatmentPlanSaveDisposition.UNCHANGED)
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
            "plan_date": _source_plan_date(aggregate),
            "signature_date": signature_date(aggregate),
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
    if commit:
        db.commit()
    else:
        db.flush()
    identity = PlanVersionIdentity(plan_version_id, patient_id, aggregate.patient_id, aggregate.source_mode, aggregate.content_snapshot.plan_id)
    return TreatmentPlanSaveResult(stored_plan(evaluated, identity=identity, last_updated=now), disposition)


def _source_plan_date(aggregate: TreatmentPlanAggregate) -> str:
    for record in reversed(aggregate.treatment_plans):
        for key in ("plan_date", "startDate", "created_date", "createdDate"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return aggregate.date_clock_anchor




def _provenance_values(provenance: SyncImportProvenance | None) -> dict[str, int | str | None]:
    if provenance is None:
        return {"sync_job_id": None, "approval_record_id": None, "contract_version": None, "contract_sha256": None}
    return {
        "sync_job_id": provenance.sync_job_id,
        "approval_record_id": provenance.approval_record_id,
        "contract_version": provenance.contract_version,
        "contract_sha256": provenance.contract_sha256,
    }
