from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, assert_never

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.core.config import settings
from app.v2.models import AppSetting
from app.v2.services.clinical_snapshot_codec import AggregateSnapshot, ClinicalSnapshotCodec, PlanRecordSnapshot
from app.v2.services.deterministic_evaluator import EvaluationBundle, evaluate_plan_version, facility_local_date
from app.v2.services.evaluation_projection import apply_evaluation
from app.v2.services.rule_package import DeterministicRulePackage, load_rule_package
from app.v2.services.migrated_treatment_plan import PlanVersionRow, RecordAggregateSource, record_aggregate
from app.v2.services.alleva_contracts import SyncImportProvenance

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


def latest_plan_target(db: Session, patient_id: str) -> PlanEvaluationTarget | None:
    row = db.execute(
        text(
            "SELECT v.id,v.evidence_sha256 FROM treatment_plan_versions v "
            "JOIN patients p ON p.id=v.patient_id WHERE p.canonical_client_id=:patient_id "
            "ORDER BY v.version_ordinal DESC,v.id DESC LIMIT 1"
        ),
        {"patient_id": patient_id},
    ).first()
    return PlanEvaluationTarget(int(row[0]), str(row[1])) if row else None


def latest_evaluated_aggregate(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    trigger: EvaluationTrigger = "date_rollover",
) -> TreatmentPlanAggregate:
    target = latest_plan_target(db, aggregate.patient_id)
    if target is None:
        return aggregate
    evaluated = persist_plan_evaluation(db, aggregate, target, trigger)
    db.commit()
    return evaluated


def refresh_patient_version(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    trigger: EvaluationTrigger,
) -> EvaluationRefreshResult:
    target = latest_plan_target(db, aggregate.patient_id)
    if target is None:
        return EvaluationRefreshResult(0, "", "", "", "")
    evaluated = persist_plan_evaluation(db, aggregate, target, trigger)
    db.commit()
    return EvaluationRefreshResult(
        versions_evaluated=1,
        evaluation_date=evaluated.evaluation_date,
        facility_timezone=evaluated.facility_timezone,
        checklist_version=evaluated.checklist_version,
        rules_version=evaluated.rules_version,
    )


def reevaluate_all_plan_versions(db: Session, trigger: EvaluationTrigger) -> EvaluationRefreshResult:
    package = load_rule_package()
    app_settings = db.execute(select(AppSetting)).scalar_one()
    rows = db.execute(text(
        "SELECT v.id,p.canonical_client_id,v.source_system,v.source_record_id,v.version_ordinal,"
        "v.admission_date,v.source_next_review_due,v.normalized_snapshot_encrypted,v.evidence_sha256 "
        "FROM treatment_plan_versions v JOIN patients p ON p.id=v.patient_id ORDER BY v.id"
    )).all()
    codec = ClinicalSnapshotCodec(settings.effective_data_encryption_secret)
    evaluation_date = ""
    for row in rows:
        snapshot = codec.decode_plan(row[7])
        match snapshot:
            case AggregateSnapshot(aggregate=aggregate):
                version_aggregate = aggregate
            case PlanRecordSnapshot(record=record):
                version_row = PlanVersionRow(
                    str(row[2]), str(row[3]), int(row[4]), str(row[5] or "Unknown"), str(row[6] or "Unknown"), row[7],
                )
                version_aggregate = record_aggregate(RecordAggregateSource(str(row[1]), version_row, (record,), ()))
            case unreachable:
                assert_never(unreachable)
        evaluated = persist_plan_evaluation(
            db, version_aggregate, PlanEvaluationTarget(int(row[0]), str(row[8])), trigger, package=package,
        )
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
