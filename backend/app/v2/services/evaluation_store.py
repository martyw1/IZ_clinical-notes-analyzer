from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, assert_never

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.core.config import settings
from app.v2.models import AppSetting
from app.v2.services.clinical_snapshot_codec import AggregateSnapshot, ClinicalSnapshotCodec, PlanRecordSnapshot
from app.v2.services.deterministic_evaluator import EvaluationBundle, evaluate_plan_version, facility_local_date
from app.v2.services.evaluation_projection import apply_evaluation
from app.v2.services.rule_package import DeterministicRulePackage, load_rule_package
from app.v2.services.migrated_treatment_plan import (
    PlanVersionRow,
    RecordAggregateSource,
    project_patient_identity,
    record_aggregate,
    assemble_treatment_plan_version,
)
from app.v2.services.alleva_contracts import SyncImportProvenance
from app.v2.services.patient_snapshot_store import patient_current_level_of_care, patient_source_snapshot_for_record
from app.v2.services.evaluation_evidence import known

EvaluationTrigger = Literal[
    "sync", "import", "correction", "rule_config", "loc_change", "new_review",
    "startup", "date_rollover", "migration", "authorized_refresh",
]


@dataclass(frozen=True, slots=True)
class PlanEvaluationTarget:
    plan_version_id: int
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class EvaluationRefreshResult:
    versions_evaluated: int
    evaluation_date: str
    facility_timezone: str
    checklist_version: str
    rules_version: str


def persist_plan_evaluation(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    target: PlanEvaluationTarget,
    trigger: EvaluationTrigger,
    *,
    instant: datetime | None = None,
    package: DeterministicRulePackage | None = None,
    sync_provenance: SyncImportProvenance | None = None,
) -> TreatmentPlanAggregate:
    loaded_package = package or load_rule_package()
    app_settings = db.execute(select(AppSetting)).scalar_one()
    evaluated_at = instant or datetime.now(timezone.utc)
    evaluation_date = facility_local_date(evaluated_at, app_settings.facility_timezone)
    bundle = evaluate_plan_version(aggregate, loaded_package, evaluation_date, app_settings.facility_timezone)
    run_id = _evaluation_run(db, target, bundle, trigger, evaluated_at, sync_provenance)
    _criterion_rows(db, run_id, target, bundle)
    db.flush()
    return apply_evaluation(aggregate, bundle)


def latest_plan_target(
    db: Session,
    patient_id: str,
    treatment_plan_id: str | None = None,
    source_system: str | None = None,
) -> PlanEvaluationTarget | None:
    rows = db.execute(
        text(
            "SELECT v.id,v.evidence_sha256 FROM treatment_plan_versions v "
            "JOIN patients p ON p.id=v.patient_id WHERE p.canonical_client_id=:patient_id "
            "AND (:treatment_plan_id IS NULL OR v.source_record_id=:treatment_plan_id) "
            "AND (:source_system IS NULL OR v.source_system=:source_system)"
        ),
        {
            "patient_id": patient_id,
            "treatment_plan_id": treatment_plan_id,
            "source_system": source_system,
        },
    ).all()
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail="Select a specific treatment-plan version.")
    return PlanEvaluationTarget(int(rows[0][0]), str(rows[0][1])) if rows else None


def evaluated_plan_version(
    db: Session, plan_version_id: int, trigger: EvaluationTrigger = "date_rollover",
) -> TreatmentPlanAggregate | None:
    aggregate = assemble_treatment_plan_version(db, plan_version_id, settings.effective_data_encryption_secret)
    if aggregate is None:
        return None
    evidence_sha256 = str(db.execute(text(
        "SELECT evidence_sha256 FROM treatment_plan_versions WHERE id=:id"
    ), {"id": plan_version_id}).scalar_one())
    identity = db.execute(text(
        "SELECT v.patient_id,NOT EXISTS (SELECT 1 FROM treatment_plan_versions n "
        "WHERE n.patient_id=v.patient_id AND n.source_system=v.source_system "
        "AND n.source_record_id=v.source_record_id AND n.version_ordinal>v.version_ordinal) "
        "FROM treatment_plan_versions v WHERE v.id=:id"
    ), {"id": plan_version_id}).one()
    if identity[1] and aggregate.source_mode == "alleva_rest_api":
        snapshot = patient_source_snapshot_for_record(db, int(identity[0]), aggregate.source_mode)
        loc = patient_current_level_of_care(snapshot.record) if snapshot is not None else ""
        if known(loc) and loc != aggregate.current_level_of_care:
            aggregate = aggregate.model_copy(update={"current_level_of_care": loc})
            # Derived evaluation evidence changes; the original encrypted plan remains immutable.
            evidence_sha256 = hashlib.sha256(f"{evidence_sha256}:patient-loc:{loc}".encode()).hexdigest()
    return persist_plan_evaluation(db, aggregate, PlanEvaluationTarget(plan_version_id, evidence_sha256), trigger)


def refresh_plan_version(
    db: Session, plan_version_id: int, trigger: EvaluationTrigger, *, commit: bool = True,
) -> EvaluationRefreshResult:
    evaluated = evaluated_plan_version(db, plan_version_id, trigger)
    if evaluated is None:
        return EvaluationRefreshResult(0, "", "", "", "")
    if commit:
        db.commit()
    return EvaluationRefreshResult(1, evaluated.evaluation_date, evaluated.facility_timezone, evaluated.checklist_version, evaluated.rules_version)


def reevaluate_all_plan_versions(db: Session, trigger: EvaluationTrigger) -> EvaluationRefreshResult:
    package = load_rule_package()
    app_settings = db.execute(select(AppSetting)).scalar_one()
    rows = db.execute(text("SELECT id FROM treatment_plan_versions ORDER BY id")).all()
    evaluation_date = ""
    for row in rows:
        evaluated = evaluated_plan_version(db, int(row[0]), trigger)
        if evaluated is not None:
            evaluation_date = evaluated.evaluation_date
    db.commit()
    return EvaluationRefreshResult(
        versions_evaluated=len(rows), evaluation_date=evaluation_date,
        facility_timezone=app_settings.facility_timezone, checklist_version=package.checklist.version,
        rules_version=package.rules.config_version,
    )


def _evaluation_run(
    db: Session,
    target: PlanEvaluationTarget,
    bundle: EvaluationBundle,
    trigger: EvaluationTrigger,
    evaluated_at: datetime,
    sync_provenance: SyncImportProvenance | None,
) -> int:
    parameters = {
        "plan_version_id": target.plan_version_id, "checklist_version": bundle.checklist_version,
        "rules_version": bundle.rules_version, "evaluation_date": bundle.evaluation_date,
        "facility_timezone": bundle.facility_timezone, "evidence_sha256": target.evidence_sha256,
        "trigger_kind": trigger, "created_at": evaluated_at.astimezone(timezone.utc).isoformat(),
        **_provenance_values(sync_provenance),
    }
    existing = db.execute(
        text(
            "SELECT id,trigger_kind FROM evaluation_runs WHERE plan_version_id=:plan_version_id AND checklist_version=:checklist_version "
            "AND rules_version=:rules_version AND evaluation_date=:evaluation_date AND evidence_sha256=:evidence_sha256 "
            "ORDER BY run_sequence DESC,id DESC LIMIT 1"
        ),
        parameters,
    ).first()
    if existing is not None and (trigger == "date_rollover" or (trigger == "startup" and existing[1] == "migration")):
        return int(existing[0])
    run_sequence = int(db.execute(
        text(
            "SELECT COALESCE(MAX(run_sequence),0)+1 FROM evaluation_runs "
            "WHERE plan_version_id=:plan_version_id AND checklist_version=:checklist_version "
            "AND rules_version=:rules_version AND evaluation_date=:evaluation_date AND evidence_sha256=:evidence_sha256"
        ),
        parameters,
    ).scalar_one())
    db.execute(
        text(
            """INSERT INTO evaluation_runs(
                plan_version_id,checklist_version,rules_version,evaluation_date,facility_timezone,
                evidence_sha256,trigger_kind,run_sequence,created_at,
                sync_job_id,approval_record_id,contract_version,contract_sha256
            ) VALUES(:plan_version_id,:checklist_version,:rules_version,:evaluation_date,:facility_timezone,
                :evidence_sha256,:trigger_kind,:run_sequence,:created_at,
                :sync_job_id,:approval_record_id,:contract_version,:contract_sha256)"""
        ),
        parameters | {"run_sequence": run_sequence},
    )
    return int(db.execute(
        text(
            "SELECT id FROM evaluation_runs WHERE plan_version_id=:plan_version_id AND checklist_version=:checklist_version "
            "AND rules_version=:rules_version AND evaluation_date=:evaluation_date AND evidence_sha256=:evidence_sha256 "
            "AND run_sequence=:run_sequence"
        ),
        parameters | {"run_sequence": run_sequence},
    ).scalar_one())


def _criterion_rows(db: Session, run_id: int, target: PlanEvaluationTarget, bundle: EvaluationBundle) -> None:
    existing_count = int(db.execute(
        text("SELECT COUNT(*) FROM criterion_results WHERE evaluation_run_id=:run_id"),
        {"run_id": run_id},
    ).scalar_one())
    if existing_count == len(bundle.criteria):
        return
    for criterion in bundle.criteria:
        result_hash = hashlib.sha256(
            f"{target.evidence_sha256}:{criterion.criterion_id}:{criterion.status}:{criterion.normalized_path}:{criterion.safe_evidence}".encode("utf-8")
        ).hexdigest()
        db.execute(
            text(
                """INSERT OR IGNORE INTO criterion_results(
                    evaluation_run_id,criterion_id,result_status,normalized_path,source_record_type,
                    source_record_version_id,evaluated_value_safe,explanation,evidence_sha256
                ) VALUES(:run_id,:criterion_id,:status,:path,'treatment_plan_version',
                    :version_id,:safe_evidence,:explanation,:evidence_sha256)"""
            ),
            {
                "run_id": run_id, "criterion_id": criterion.criterion_id, "status": criterion.status,
                "path": criterion.normalized_path, "version_id": target.plan_version_id,
                "safe_evidence": criterion.safe_evidence[:160], "explanation": criterion.explanation,
                "evidence_sha256": result_hash,
            },
        )


def _provenance_values(provenance: SyncImportProvenance | None) -> dict[str, int | str | None]:
    if provenance is None:
        return {"sync_job_id": None, "approval_record_id": None, "contract_version": None, "contract_sha256": None}
    return {
        "sync_job_id": provenance.sync_job_id,
        "approval_record_id": provenance.approval_record_id,
        "contract_version": provenance.contract_version,
        "contract_sha256": provenance.contract_sha256,
    }
