from __future__ import annotations

import csv
from io import StringIO
from typing import Final

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import text

from app.v2.api.deps import DbSession, ManagerUser
from app.v2.api.plan_models import TreatmentPlanExportInput
from app.v2.authorization import PlanVersionSelector, accessible_patient_record_ids, resolve_plan_version
from app.v2.domain.schemas import SourceMode
from app.v2.services.audit_store import record_audit_event
from app.v2.services.treatment_plan_read_model import TreatmentPlanQuery
from app.v2.services.treatment_plan_store import list_treatment_plan_queue_items, treatment_plan_aggregate_for_version
from app.v2.services.treatment_plan_types import TreatmentPlanQueueItem

router = APIRouter()
SPREADSHEET_FORMULA_PREFIXES: Final = ("=", "+", "-", "@")


@router.get("/api/v2/exports/{patient_id}/checklist-evidence.csv")
def redacted_checklist_export(
    patient_id: str, user: ManagerUser, db: DbSession,
    plan_version_id: int | None = None, patient_record_id: int | None = None,
    source_mode: SourceMode | None = None, treatment_plan_id: str | None = None,
) -> Response:
    identity = resolve_plan_version(db, user, PlanVersionSelector(patient_id, plan_version_id, patient_record_id, source_mode, treatment_plan_id), manager=True)
    aggregate = treatment_plan_aggregate_for_version(db, identity.plan_version_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(("plan_version_id", "patient_record_id", "source_mode", "treatment_plan_id", "criterion", "status", "finding", "source_path", "safe_preview", "manager_action"))
    for criterion in aggregate.criteria_results:
        preview = criterion.evidence_refs[0].safe_preview if criterion.evidence_refs else ""
        path = criterion.source_json_paths[0] if criterion.source_json_paths else ""
        writer.writerow(tuple(_safe_csv_cell(value) for value in (str(identity.plan_version_id), str(identity.patient_record_id), identity.source_mode, identity.treatment_plan_id, criterion.criterion_id, criterion.result_status, criterion.finding_message, path, preview, "review")))
    record_audit_event(
        db,
        action="export.redacted_checklist_evidence",
        actor=user,
        target_entity_type="treatment_plan_version",
        target_entity_id=str(identity.plan_version_id),
        details={"patient_row_id": identity.patient_record_id},
    )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=redacted-checklist-evidence.csv"},
    )



@router.get("/api/v2/exports/treatment-plans.csv")
def treatment_plan_list_export(user: ManagerUser, db: DbSession) -> Response:
    return _export_response(list_treatment_plan_queue_items(db, accessible_patient_record_ids(db, user)), user, db)


@router.post("/api/v2/exports/treatment-plans.csv")
def treatment_plan_filtered_export(payload: TreatmentPlanExportInput, user: ManagerUser, db: DbSession) -> Response:
    ids = tuple(dict.fromkeys(payload.plan_version_ids))
    for version_id in ids:
        mrn = db.execute(text(
            "SELECT p.canonical_client_id FROM treatment_plan_versions v JOIN patients p ON p.id=v.patient_id WHERE v.id=:id"
        ), {"id": version_id}).scalar_one_or_none()
        if mrn is None:
            raise HTTPException(status_code=404, detail="Treatment plan not found")
        resolve_plan_version(db, user, PlanVersionSelector(str(mrn), plan_version_id=version_id,
                             source_mode=payload.source_mode), manager=True)
    query = TreatmentPlanQuery(source_mode=payload.source_mode, include_history=True, plan_version_ids=frozenset(ids))
    items = list_treatment_plan_queue_items(db, accessible_patient_record_ids(db, user), query)
    by_id = {item.plan_version_id: item for item in items}
    if set(by_id) != set(ids):
        raise HTTPException(status_code=404, detail="Treatment plan not found")
    return _export_response(tuple(by_id[version_id] for version_id in ids), user, db)


def _export_response(items: tuple[TreatmentPlanQueueItem, ...], user: ManagerUser, db: DbSession) -> Response:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        (
            "patient_id",
            "plan_version_id",
            "patient_record_id",
            "treatment_plan_id",
            "status",
            "current_level_of_care",
            "admission_date",
            "next_due_date",
            "source_mode",
            "version_ordinal",
            "missing_criteria_count",
            "returned_criteria_count",
        )
    )
    for item in items:
        writer.writerow(
            tuple(
                _safe_csv_cell(str(value))
                for value in (
                    item.patient_id,
                    item.plan_version_id,
                    item.patient_record_id,
                    item.treatment_plan_id,
                    item.status,
                    item.current_level_of_care,
                    item.admission_date,
                    item.next_due_date,
                    item.source_mode,
                    item.version_ordinal,
                    item.missing_criteria_count,
                    item.returned_criteria_count,
                )
            )
        )
    record_audit_event(
        db,
        action="export.treatment_plan_list",
        actor=user,
        target_entity_type="treatment_plan_queue",
        target_entity_id="current",
        details={"treatment_plan_count": len(items)},
    )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=treatment-plans.csv"},
    )


def _safe_csv_cell(value: str) -> str:
    if value.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return f"'{value}"
    return value
