from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.services.treatment_plan_store import StoredTreatmentPlan, list_treatment_plan_imports
from app.v2.services.patient_snapshot_store import (
    PatientSourceSnapshot,
    latest_patient_source_snapshots,
    patient_current_level_of_care,
)


@dataclass(frozen=True, slots=True)
class PatientRosterTreatmentPlan:
    treatment_plan_id: str
    last_updated: str


@dataclass(frozen=True, slots=True)
class PatientRosterItem:
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
    treatment_plan_id: str
    mrn: str
    patient_key: str
    linked_to_mrn: bool
    full_name: str
    last_updated: str
    previous_treatment_plan_id: str
    initial_treatment_plan_id: str
    initial_treatment_plan_date: str


def list_patient_roster(db: Session) -> tuple[PatientRosterItem, ...]:
    snapshots = latest_patient_source_snapshots(db)
    plans_by_patient: dict[tuple[str, str], list[StoredTreatmentPlan]] = {}
    for plan in list_treatment_plan_imports(db):
        plans_by_patient.setdefault((plan.patient_id, plan.source_mode), []).append(plan)
    rows = db.execute(
        text(
            "SELECT canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
            "FROM patients WHERE lifecycle_state<>'unlinked' "
            "ORDER BY lifecycle_state,canonical_client_id,source_system"
        )
    ).all()
    return tuple(
        _roster_item(
            mrn=str(row[0]),
            source_mode=str(row[1]),
            lifecycle_state=str(row[2]),
            first_seen_at=str(row[3]),
            last_seen_at=str(row[4]),
            reconciled_at=str(row[5] or ""),
            plans=tuple(plans_by_patient.get((str(row[0]), str(row[1])), ())),
            snapshot=snapshots.get((str(row[0]), str(row[1]))),
        )
        for row in rows
    )


def _roster_item(
    *,
    mrn: str,
    source_mode: str,
    lifecycle_state: str,
    first_seen_at: str,
    last_seen_at: str,
    reconciled_at: str,
    plans: tuple[StoredTreatmentPlan, ...],
    snapshot: PatientSourceSnapshot | None,
) -> PatientRosterItem:
    ordered_plans = plans_by_source_update(plans)
    newest_plan = ordered_plans[0] if ordered_plans else None
    return PatientRosterItem(
        mrn=mrn,
        full_name=snapshot.full_name if snapshot is not None else "",
        source_mode=source_mode,
        lifecycle_state=lifecycle_state,
        current_level_of_care=(
            newest_plan.current_level_of_care
            if newest_plan
            else patient_current_level_of_care(snapshot.record) if snapshot is not None else "Unknown"
        ) or "Unknown",
        treatment_plans=tuple(
            PatientRosterTreatmentPlan(treatment_plan_id=plan.plan_id, last_updated=plan.last_updated)
            for plan in ordered_plans
        ),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        reconciled_at=reconciled_at,
    )


def list_treatment_plan_roster(db: Session) -> tuple[TreatmentPlanRosterItem, ...]:
    snapshots = latest_patient_source_snapshots(db)
    plans_by_mrn: dict[str, list[StoredTreatmentPlan]] = {}
    for plan in list_treatment_plan_imports(db):
        if plan.source_mode == "alleva_rest_api":
            plans_by_mrn.setdefault(plan.patient_id, []).append(plan)
    items: list[TreatmentPlanRosterItem] = []
    for mrn, plans in plans_by_mrn.items():
        linked_to_mrn = not mrn.startswith("unlinked-")
        snapshot = snapshots.get((mrn, "alleva_rest_api")) if linked_to_mrn else None
        ordered = tuple(sorted(plans, key=_lineage_sort_key))
        initial = ordered[0]
        for index, plan in enumerate(ordered):
            items.append(TreatmentPlanRosterItem(
                treatment_plan_id=plan.plan_id,
                mrn=mrn if linked_to_mrn else "",
                patient_key=mrn,
                linked_to_mrn=linked_to_mrn,
                full_name=snapshot.full_name if snapshot is not None else "",
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


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
