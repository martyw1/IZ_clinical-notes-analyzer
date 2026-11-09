from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Final
from pydantic import BaseModel, ConfigDict

from sqlalchemy import select, text

from app.v2.models import OverduePlanAcknowledgement
from sqlalchemy.orm import Session

from app.v2.services.imported_counselors import primary_counselors_for_records
from app.v2.services.dashboard_data import latest_patient_plans
from app.v2.services.deadline_calendar import deadline_status
from app.v2.services.evaluation_evidence import parse_date
from app.v2.services.treatment_plan_store import StoredTreatmentPlan, list_treatment_plan_imports
from app.v2.services.treatment_plan_read_model import TreatmentPlanQuery
from app.v2.domain.schemas import SourceMode
from app.v2.services.patient_snapshot_store import (
    PatientSourceSnapshot,
    patient_source_snapshot_for_record,
    patient_current_level_of_care,
    patient_source_snapshots_for_records,
)

UNLINKED_PATIENT_KEY_PREFIX: Final = "unlinked-plan-"


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
    primary_counselor_id: int | None
    primary_counselor_name: str
    tracking_eligible: bool


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
    next_due_date: str
    deadline_status: str
    days_overdue: int | None
    reviewed_at_utc: str
    primary_counselor_id: int | None
    primary_counselor_name: str


class PatientRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    canonical_client_id: str
    source_patient_id: str | None = None
    source_system: SourceMode
    lifecycle_state: str
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str | None


def list_patient_roster(
    db: Session, allowed_patient_record_ids: frozenset[int] | None = None,
    source_mode: SourceMode | None = None,
) -> tuple[PatientRosterItem, ...]:
    rows = db.execute(text(
        "SELECT id,canonical_client_id,source_patient_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
        "FROM patients WHERE lifecycle_state<>'unlinked' AND (:source IS NULL OR source_system=:source) "
        "ORDER BY lifecycle_state,canonical_client_id,source_system,id"
    ), {"source": source_mode}).all()
    snapshots = patient_source_snapshots_for_records(db, tuple(
        int(row[0]) for row in rows if allowed_patient_record_ids is None or int(row[0]) in allowed_patient_record_ids
    ))
    counselors = primary_counselors_for_records(db, tuple(
        int(row[0]) for row in rows if allowed_patient_record_ids is None or int(row[0]) in allowed_patient_record_ids
    ))
    plans_by_patient: dict[int, list[StoredTreatmentPlan]] = {}
    for plan in list_treatment_plan_imports(db, allowed_patient_record_ids, TreatmentPlanQuery(source_mode=source_mode), snapshots):
        plans_by_patient.setdefault(plan.patient_record_id, []).append(plan)
    result: list[PatientRosterItem] = []
    for raw in rows:
        row = PatientRow.model_validate(raw._mapping)
        if allowed_patient_record_ids is not None and row.id not in allowed_patient_record_ids:
            continue
        if (
            row.source_system == "alleva_rest_api"
            and row.source_patient_id is None
            and row.canonical_client_id.startswith(UNLINKED_PATIENT_KEY_PREFIX)
        ):
            continue
        snapshot = snapshots.get(row.id)
        result.append(_roster_item(row, tuple(plans_by_patient.get(row.id, ())), snapshot, counselors.get(row.id)))
    return tuple(result)


def _roster_item(
    row: PatientRow,
    plans: tuple[StoredTreatmentPlan, ...],
    snapshot: PatientSourceSnapshot | None,
    counselor: tuple[int, str] | None,
) -> PatientRosterItem:
    ordered_plans = plans_by_source_update(plans)
    newest_plan = ordered_plans[0] if ordered_plans else None
    snapshot_loc = patient_current_level_of_care(snapshot.record) if snapshot is not None else ""
    return PatientRosterItem(
        patient_record_id=row.id,
        mrn=row.canonical_client_id,
        full_name=snapshot.full_name if snapshot is not None else "",
        source_mode=row.source_system,
        lifecycle_state=row.lifecycle_state,
        current_level_of_care=(
            snapshot_loc or (newest_plan.current_level_of_care if newest_plan else "") or "Unknown"
        ),
        treatment_plans=tuple(
            roster_plan(plan)
            for plan in ordered_plans
        ),
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        reconciled_at=row.reconciled_at or "",
        primary_counselor_id=counselor[0] if counselor else None,
        primary_counselor_name=counselor[1] if counselor else "",
        tracking_eligible=row.lifecycle_state == "active" and not _outside_current_tracking(row.lifecycle_state, snapshot),
    )


def _outside_current_tracking(lifecycle: str, snapshot: PatientSourceSnapshot | None) -> bool:
    return lifecycle in {"discharged", "deleted", "inactive", "unlinked"} or (
        snapshot is not None and patient_current_level_of_care(snapshot.record).strip().casefold() == "case management"
    )


def current_tracking_patients(
    db: Session, allowed_patient_record_ids: frozenset[int] | None,
) -> tuple[frozenset[int], int]:
    rows = {
        int(row.id): row.lifecycle_state
        for row in db.execute(text("SELECT id, lifecycle_state FROM patients"))
        if allowed_patient_record_ids is None or int(row.id) in allowed_patient_record_ids
    }
    snapshots = patient_source_snapshots_for_records(db, tuple(rows))
    excluded = frozenset(
        patient_id for patient_id, lifecycle in rows.items()
        if _outside_current_tracking(lifecycle, snapshots.get(patient_id))
    )
    return excluded, sum(rows[patient_id] == "active" for patient_id in rows.keys() - excluded)


def list_treatment_plan_roster(
    db: Session, allowed_patient_record_ids: frozenset[int] | None = None,
    source_mode: SourceMode | None = None,
    evaluation_date: date | None = None,
) -> tuple[TreatmentPlanRosterItem, ...]:
    plans_by_patient: dict[tuple[int, str], list[StoredTreatmentPlan]] = {}
    imports = list_treatment_plan_imports(db, allowed_patient_record_ids, TreatmentPlanQuery(source_mode=source_mode))
    current_versions: set[int] = set()
    if evaluation_date is not None:
        excluded, _ = current_tracking_patients(db, allowed_patient_record_ids)
        current, _ = latest_patient_plans([plan for plan in imports if plan.patient_record_id not in excluded])
        current_versions = {plan.plan_version_id for plan in current}
    for plan in imports:
        plans_by_patient.setdefault((plan.patient_record_id, plan.source_mode), []).append(plan)
    placeholder_patient_record_ids = frozenset(
        int(row[0])
        for row in db.execute(
            text(
                "SELECT id FROM patients WHERE source_system='alleva_rest_api' "
                "AND source_patient_id IS NULL "
                "AND substr(canonical_client_id,1,:prefix_length)=:prefix"
            ),
            {
                "prefix": UNLINKED_PATIENT_KEY_PREFIX,
                "prefix_length": len(UNLINKED_PATIENT_KEY_PREFIX),
            },
        ).all()
    )
    counselors = primary_counselors_for_records(db, tuple({plan.patient_record_id for plan in imports}))
    reviewed = {}
    version_ids = tuple(plan.plan_version_id for plan in imports)
    for start in range(0, len(version_ids), 400):
        reviewed.update(db.execute(select(
            OverduePlanAcknowledgement.plan_version_id,
            OverduePlanAcknowledgement.reviewed_at_utc,
        ).where(OverduePlanAcknowledgement.plan_version_id.in_(version_ids[start:start + 400]))).all())
    items: list[TreatmentPlanRosterItem] = []
    for plans in plans_by_patient.values():
        mrn = plans[0].patient_id
        linked_to_mrn = plans[0].patient_record_id not in placeholder_patient_record_ids
        ordered = tuple(sorted(plans, key=_lineage_sort_key))
        initial = ordered[0]
        for index, plan in enumerate(ordered):
            due = parse_date(plan.next_due_date)
            status = (
                deadline_status(due, evaluation_date)
                if evaluation_date is not None and plan.plan_version_id in current_versions
                else "Outside current tracking"
            )
            age = (evaluation_date - due).days if evaluation_date is not None and due is not None and status == "Overdue" else None
            counselor = counselors.get(plan.patient_record_id)
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
                next_due_date=due.isoformat() if due is not None else "",
                deadline_status=status,
                days_overdue=age,
                reviewed_at_utc=reviewed.get(plan.plan_version_id, ""),
                primary_counselor_id=counselor[0] if counselor else None,
                primary_counselor_name=counselor[1] if counselor else "",
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
