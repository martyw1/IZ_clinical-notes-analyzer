from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pydantic import BaseModel, ConfigDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.services.treatment_plan_store import StoredTreatmentPlan, list_treatment_plan_imports
from app.v2.services.treatment_plan_read_model import TreatmentPlanQuery
from app.v2.domain.schemas import SourceMode
from app.v2.services.patient_snapshot_store import (
    PatientSourceSnapshot,
    patient_source_snapshot_for_record,
    patient_current_level_of_care,
)


@dataclass(frozen=True, slots=True)
class PatientRosterTreatmentPlan:
    treatment_plan_id: str
    last_updated: str
    patient_record_id: int
    plan_version_id: int
    source_mode: str
    version_ordinal: int
    original_plan_reference: str
    service_date: str


@dataclass(frozen=True, slots=True)
class PatientRosterItem:
    patient_record_id: int
    mrn: str
    full_name: str
    source_mode: str
    lifecycle_state: str
    current_level_of_care: str
    treatment_plans: tuple[PatientRosterTreatmentPlan, ...]
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str


@dataclass(frozen=True, slots=True)
class TreatmentPlanRosterItem:
    patient_record_id: int
    plan_version_id: int
    source_mode: str
    version_ordinal: int
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


class PatientRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    canonical_client_id: str
    source_system: SourceMode
    lifecycle_state: str
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str | None


def list_patient_roster(
    db: Session, allowed_patient_record_ids: frozenset[int] | None = None,
    source_mode: SourceMode | None = None,
) -> tuple[PatientRosterItem, ...]:
    plans_by_patient: dict[int, list[StoredTreatmentPlan]] = {}
    for plan in list_treatment_plan_imports(db, allowed_patient_record_ids, TreatmentPlanQuery(source_mode=source_mode)):
        plans_by_patient.setdefault(plan.patient_record_id, []).append(plan)
    rows = db.execute(text(
        "SELECT id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
        "FROM patients WHERE lifecycle_state<>'unlinked' AND (:source IS NULL OR source_system=:source) "
        "ORDER BY lifecycle_state,canonical_client_id,source_system,id"
    ), {"source": source_mode}).all()
    result: list[PatientRosterItem] = []
    for raw in rows:
        row = PatientRow.model_validate(raw._mapping)
        if allowed_patient_record_ids is not None and row.id not in allowed_patient_record_ids:
            continue
        snapshot = patient_source_snapshot_for_record(db, row.id, row.source_system)
        result.append(_roster_item(row, tuple(plans_by_patient.get(row.id, ())), snapshot))
    return tuple(result)


def _roster_item(
    row: PatientRow,
    plans: tuple[StoredTreatmentPlan, ...],
    snapshot: PatientSourceSnapshot | None,
) -> PatientRosterItem:
    ordered_plans = plans_by_source_update(plans)
    newest_plan = ordered_plans[0] if ordered_plans else None
    return PatientRosterItem(
        patient_record_id=row.id,
        mrn=row.canonical_client_id,
        full_name=snapshot.full_name if snapshot is not None else "",
        source_mode=row.source_system,
        lifecycle_state=row.lifecycle_state,
        current_level_of_care=(
            newest_plan.current_level_of_care
            if newest_plan
            else patient_current_level_of_care(snapshot.record) if snapshot is not None else "Unknown"
        ) or "Unknown",
        treatment_plans=tuple(
            roster_plan(plan)
            for plan in ordered_plans
        ),
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        reconciled_at=row.reconciled_at or "",
    )


def list_treatment_plan_roster(
    db: Session, allowed_patient_record_ids: frozenset[int] | None = None,
    source_mode: SourceMode | None = None,
) -> tuple[TreatmentPlanRosterItem, ...]:
    plans_by_patient: dict[tuple[int, str], list[StoredTreatmentPlan]] = {}
    for plan in list_treatment_plan_imports(db, allowed_patient_record_ids, TreatmentPlanQuery(source_mode=source_mode)):
        plans_by_patient.setdefault((plan.patient_record_id, plan.source_mode), []).append(plan)
    items: list[TreatmentPlanRosterItem] = []
    for plans in plans_by_patient.values():
        mrn = plans[0].patient_id
        linked_to_mrn = not mrn.startswith("unlinked-")
        ordered = tuple(sorted(plans, key=_lineage_sort_key))
        initial = ordered[0]
        for index, plan in enumerate(ordered):
            items.append(TreatmentPlanRosterItem(
                patient_record_id=plan.patient_record_id,
                plan_version_id=plan.plan_version_id,
                source_mode=plan.source_mode,
                version_ordinal=plan.version_ordinal,
                original_plan_reference=plan.original_plan_reference,
                service_date=plan.service_date,
                treatment_plan_id=plan.plan_id,
                mrn=mrn if linked_to_mrn else "",
                patient_key=mrn,
                linked_to_mrn=linked_to_mrn,
                full_name=plan.full_name if linked_to_mrn else "",
                last_updated=plan.last_updated,
                previous_treatment_plan_id=ordered[index - 1].plan_id if index else "",
                initial_treatment_plan_id=initial.plan_id,
                initial_treatment_plan_date=initial.plan_date or initial.last_updated,
            ))
    return tuple(
        sorted(
            sorted(items, key=lambda item: (item.treatment_plan_id, item.patient_key)),
            key=lambda item: _timestamp(item.last_updated),
            reverse=True,
        )
    )


def plans_by_source_update(
    plans: tuple[StoredTreatmentPlan, ...],
) -> tuple[StoredTreatmentPlan, ...]:
    return tuple(
        sorted(
            sorted(plans, key=lambda plan: plan.plan_id),
            key=lambda plan: _timestamp(plan.last_updated),
            reverse=True,
        )
    )


def _lineage_sort_key(plan: StoredTreatmentPlan) -> tuple[datetime, datetime, str]:
    return _timestamp(plan.plan_date), _timestamp(plan.last_updated), plan.plan_id


def roster_plan(plan: StoredTreatmentPlan) -> PatientRosterTreatmentPlan:
    return PatientRosterTreatmentPlan(plan.plan_id, plan.last_updated, plan.patient_record_id,
        plan.plan_version_id, plan.source_mode, plan.version_ordinal, plan.original_plan_reference, plan.service_date)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
