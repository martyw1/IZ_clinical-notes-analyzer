from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.models import (
    AppSetting,
    LevelOfCareHistory,
    PatientNoteDocument,
    PatientNoteSet,
    TreatmentPlanClient,
    TreatmentPlanKind,
    TreatmentPlanOverride,
    TreatmentPlanRecord,
    TimelinessStatus,
    User,
)
from app.services.patient_notes import NAME_NOT_FOUND_STATUS, display_name_for_patient_name_status
from app.services.rules_engine import load_rules_config

STATUS_PRIORITY = [
    TimelinessStatus.overdue.value,
    TimelinessStatus.urgent.value,
    TimelinessStatus.due_soon.value,
    TimelinessStatus.returned.value,
    TimelinessStatus.needs_review.value,
    TimelinessStatus.missing_data.value,
    TimelinessStatus.conflicting.value,
    TimelinessStatus.unable_to_evaluate.value,
    TimelinessStatus.compliant.value,
    TimelinessStatus.approved.value,
]
PLAN_KIND_ALIASES = {
    'initial': TreatmentPlanKind.initial,
    'initial_treatment_plan': TreatmentPlanKind.initial,
    'master': TreatmentPlanKind.master,
    'master_treatment_plan': TreatmentPlanKind.master,
    'review': TreatmentPlanKind.review,
    'treatment_plan_review': TreatmentPlanKind.review,
    'ongoing': TreatmentPlanKind.review,
    'loc_update': TreatmentPlanKind.loc_update,
    'level_of_care_update': TreatmentPlanKind.loc_update,
}


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    label: str
    due_date: str | None
    status: str
    evidence_summary: str


@dataclass(frozen=True)
class EvidenceComparison:
    document_next_due_date: str | None
    signature_anchor_due_date: str | None
    loc_anchor_due_date: str | None
    final_status: str
    conflict_explanation: str
    source_evidence: str
    staff_signature_date: str | None
    loc_effective_date: str | None
    interval_days: int | None
    loc_change_window_days: int | None
    loc_change_rule_validated: bool


@dataclass(frozen=True)
class TimelinessEvaluation:
    client: TreatmentPlanClient
    status: str
    next_due_date: str | None
    days_until_due: int | None
    last_valid_review_date: str | None
    rule_used: str
    evidence_summary: str
    last_checked_at: datetime
    rule_results: list[RuleResult]
    evidence_comparison: EvidenceComparison
    evidence_completeness_percent: int
    missing_evidence_fields: list[str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _date_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _days_until(due_date: date | None, evaluation_date: date) -> int | None:
    if due_date is None:
        return None
    return (due_date - evaluation_date).days


def _add_days(anchor: date | None, days: int | None) -> date | None:
    if anchor is None or days is None:
        return None
    return date.fromordinal(anchor.toordinal() + days)


def _status_from_due_date(due_date: date | None, evaluation_date: date) -> tuple[str | None, int | None]:
    days_until = _days_until(due_date, evaluation_date)
    if days_until is None:
        return None, None
    if days_until <= 0:
        return TimelinessStatus.overdue.value, days_until
    if days_until <= 5:
        return TimelinessStatus.urgent.value, days_until
    if days_until <= 10:
        return TimelinessStatus.due_soon.value, days_until
    return TimelinessStatus.compliant.value, days_until


def _configured_levels() -> dict[str, dict[str, Any]]:
    config = load_rules_config()
    levels = config.get('levels_of_care')
    return levels if isinstance(levels, dict) else {}


def map_level_of_care(raw_value: str) -> tuple[str | None, int | None]:
    normalized = raw_value.strip().lower()
    if not normalized:
        return None, None
    for key, spec in _configured_levels().items():
        aliases = spec.get('aliases') if isinstance(spec, dict) else None
        candidates = [key, *(aliases if isinstance(aliases, list) else [])]
        if any(str(candidate).strip().lower() == normalized for candidate in candidates):
            interval = spec.get('treatment_plan_update_interval_days') if isinstance(spec, dict) else None
            return key, int(interval) if isinstance(interval, int) else None
    return None, None


def normalize_plan_kind(value: str) -> TreatmentPlanKind:
    normalized = value.strip().lower().replace('-', '_').replace(' ', '_')
    try:
        return PLAN_KIND_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f'Unknown treatment plan kind: {value}') from exc


def _latest_plan(plans: list[TreatmentPlanRecord], kind: TreatmentPlanKind) -> TreatmentPlanRecord | None:
    matching = [plan for plan in plans if plan.plan_kind == kind]
    matching.sort(key=lambda plan: (_date(plan.staff_signature_date) or _date(plan.document_date) or date.min, plan.id or 0), reverse=True)
    return matching[0] if matching else None


def _latest_review_plan(plans: list[TreatmentPlanRecord]) -> TreatmentPlanRecord | None:
    matching = [plan for plan in plans if plan.plan_kind in {TreatmentPlanKind.review, TreatmentPlanKind.loc_update}]
    matching.sort(
        key=lambda plan: (
            _date(plan.staff_signature_date) or _date(plan.document_date) or _date(plan.displayed_next_due_date) or date.min,
            plan.id or 0,
        ),
        reverse=True,
    )
    return matching[0] if matching else None


def _valid_review_date(plans: list[TreatmentPlanRecord]) -> date | None:
    candidates: list[date] = []
    for plan in plans:
        if plan.plan_kind not in {TreatmentPlanKind.review, TreatmentPlanKind.loc_update}:
            continue
        if not plan.is_valid or plan.conflict_note.strip():
            continue
        signed = _date(plan.staff_signature_date)
        if signed:
            candidates.append(signed)
    return max(candidates) if candidates else None


def _plan_has_required_signatures(plan: TreatmentPlanRecord | None) -> bool:
    return bool(plan and _date(plan.staff_signature_date) and _date(plan.client_signature_date) and plan.is_valid and not plan.conflict_note.strip())


def _result(rule_id: str, label: str, due_date: date | None, status: str, evidence: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, label=label, due_date=_date_str(due_date), status=status, evidence_summary=evidence)


def _select_overall(rule_results: list[RuleResult], evaluation_date: date) -> tuple[str, str | None, int | None, str]:
    blocking_conflict = next((result for result in rule_results if result.rule_id == 'TP-DUE-DATE-CONFLICT'), None)
    if blocking_conflict is not None:
        due = _date(blocking_conflict.due_date)
        return TimelinessStatus.needs_review.value, _date_str(due), _days_until(due, evaluation_date), blocking_conflict.rule_id

    due_candidates: list[tuple[date, int, RuleResult]] = []
    for result in rule_results:
        due = _date(result.due_date)
        days_until = _days_until(due, evaluation_date)
        if due is not None and days_until is not None:
            due_candidates.append((due, days_until, result))

    actionable_due_candidates = [
        item
        for item in due_candidates
        if item[2].status in {TimelinessStatus.overdue.value, TimelinessStatus.urgent.value, TimelinessStatus.due_soon.value}
    ]
    if actionable_due_candidates:
        due, days_until, selected = sorted(actionable_due_candidates, key=lambda item: (STATUS_PRIORITY.index(item[2].status), item[0]))[0]
        return selected.status, due.isoformat(), days_until, selected.rule_id

    ranked = sorted(rule_results, key=lambda item: STATUS_PRIORITY.index(item.status))
    selected = ranked[0]
    due = _date(selected.due_date)
    days_until = _days_until(due, evaluation_date)
    if selected.status == TimelinessStatus.compliant.value and due_candidates:
        future_due_candidates = [item for item in due_candidates if item[0] >= evaluation_date]
        if future_due_candidates:
            due, days_until, selected = sorted(future_due_candidates, key=lambda item: item[0])[0]
        else:
            due, days_until, selected = sorted(due_candidates, key=lambda item: item[0], reverse=True)[0]
    return selected.status, _date_str(due), days_until, selected.rule_id


def _active_level_of_care(loc_history: list[LevelOfCareHistory]) -> LevelOfCareHistory | None:
    if not loc_history:
        return None
    sorted_history = sorted(loc_history, key=lambda item: (_date(item.effective_date) or date.min, item.id or 0))
    active = [item for item in sorted_history if not item.discharge_date.strip()]
    return active[-1] if active else sorted_history[-1]


def _describe_due_date_comparison(
    *,
    document_due: date | None,
    signature_due: date | None,
    loc_due: date | None,
    staff_signature: date | None,
    loc_effective: date | None,
    interval_days: int | None,
    loc_change_validated: bool,
) -> str:
    parts = []
    if document_due:
        parts.append(f'source document Next Review Due is {document_due.isoformat()}')
    else:
        parts.append('source document Next Review Due is not recorded')
    if signature_due:
        parts.append(
            f'staff signature anchor is {signature_due.isoformat()}'
            f' ({staff_signature.isoformat()} + {interval_days} days)' if staff_signature and interval_days else f'staff signature anchor is {signature_due.isoformat()}'
        )
    else:
        parts.append('staff signature anchor could not be calculated')
    if loc_due:
        parts.append(
            f'LOC effective-date anchor is {loc_due.isoformat()}'
            f' ({loc_effective.isoformat()} + {interval_days} days)' if loc_effective and interval_days else f'LOC effective-date anchor is {loc_due.isoformat()}'
        )
    else:
        parts.append('LOC effective-date anchor could not be calculated')
    if not loc_change_validated:
        parts.append('LOC-change anchor/window is unvalidated by R3/Marleigh')
    return '; '.join(parts) + '.'


def _comparison_source_evidence(latest_review: TreatmentPlanRecord | None, active_loc: LevelOfCareHistory | None) -> str:
    sources = []
    if latest_review and latest_review.source_evidence.strip():
        sources.append(latest_review.source_evidence.strip())
    if active_loc and active_loc.source_evidence.strip():
        sources.append(active_loc.source_evidence.strip())
    return '; '.join(sources)


def _evidence_completeness(
    client: TreatmentPlanClient,
    *,
    latest_review: TreatmentPlanRecord | None,
    active_loc: LevelOfCareHistory | None,
    mapped_loc: str | None,
    interval_days: int | None,
    document_due: date | None,
) -> tuple[int, list[str]]:
    checks = [
        ('Admission date', _date(client.admission_date) is not None),
        ('Current level of care', bool(mapped_loc and interval_days is not None)),
        ('Level-of-care effective date', bool(active_loc and _date(active_loc.effective_date))),
        ('Treatment Plan Review staff signature', bool(latest_review and _date(latest_review.staff_signature_date))),
        ('Treatment Plan Review source evidence', bool(latest_review and latest_review.source_evidence.strip())),
        ('Source-document Next Review Due', document_due is not None),
    ]
    complete = sum(1 for _label, is_complete in checks if is_complete)
    score = round((complete / len(checks)) * 100) if checks else 0
    missing = [label for label, is_complete in checks if not is_complete]
    return score, missing


def evaluate_client(client: TreatmentPlanClient, app_settings: AppSetting, *, evaluation_date: date | None = None) -> TimelinessEvaluation:
    checked_at = _utc_now()
    today = evaluation_date or checked_at.date()
    plans = list(client.treatment_plans)
    loc_history = sorted(client.level_of_care_history, key=lambda item: _date(item.effective_date) or date.min)
    rule_results: list[RuleResult] = []

    admission = _date(client.admission_date)
    mapped_loc, interval_days = map_level_of_care(client.current_level_of_care)
    has_conflict = any(plan.conflict_note.strip() for plan in plans)
    latest_review = _latest_review_plan(plans)
    active_loc = _active_level_of_care(loc_history)
    document_due = _date(latest_review.displayed_next_due_date) if latest_review else None
    staff_signature = _date(latest_review.staff_signature_date) if latest_review else None
    loc_effective = _date(active_loc.effective_date) if active_loc else None
    signature_anchor_due = _add_days(staff_signature, interval_days)
    loc_anchor_due = _add_days(loc_effective, interval_days) if len(loc_history) > 1 else None
    due_dates_for_comparison = {item for item in (document_due, signature_anchor_due, loc_anchor_due) if item is not None}
    comparison_explanation = _describe_due_date_comparison(
        document_due=document_due,
        signature_due=signature_anchor_due,
        loc_due=loc_anchor_due,
        staff_signature=staff_signature,
        loc_effective=loc_effective,
        interval_days=interval_days,
        loc_change_validated=app_settings.treatment_plan_loc_change_window_validated,
    )

    if admission is None:
        rule_results.append(_result('TP-MISSING-ADMISSION', 'Admission date', None, TimelinessStatus.missing_data.value, 'Admission date is missing or unreadable.'))
    if not mapped_loc or interval_days is None:
        rule_results.append(
            _result('TP-MISSING-LOC', 'Current level of care', None, TimelinessStatus.missing_data.value, 'Current level of care is missing or not configured.')
        )
    if has_conflict:
        rule_results.append(
            _result('TP-CONFLICTING-EVIDENCE', 'Conflicting evidence', None, TimelinessStatus.needs_review.value, 'One or more treatment plan records has conflicting source evidence.')
        )

    initial = _latest_plan(plans, TreatmentPlanKind.initial)
    if admission:
        if _plan_has_required_signatures(initial) and _date(initial.staff_signature_date) == admission and _date(initial.client_signature_date) == admission:
            rule_results.append(_result('TP-INITIAL-ADMISSION', 'Initial Treatment Plan', admission, TimelinessStatus.compliant.value, 'Initial plan signatures match admission date.'))
        elif initial is None:
            due_status, _ = _status_from_due_date(admission, today)
            rule_results.append(
                _result('TP-INITIAL-ADMISSION', 'Initial Treatment Plan', admission, due_status or TimelinessStatus.missing_data.value, 'Initial Treatment Plan record is missing.')
            )
        else:
            rule_results.append(
                _result(
                    'TP-INITIAL-SIGNATURES',
                    'Initial Treatment Plan signatures',
                    admission,
                    TimelinessStatus.needs_review.value,
                    'Initial Treatment Plan signatures are missing, incomplete, or do not match admission date.',
                )
            )

    master = _latest_plan(plans, TreatmentPlanKind.master)
    master_due = admission.toordinal() if admission else None
    master_due_date = date.fromordinal(master_due + 30) if master_due is not None else None
    if master_due_date:
        if _plan_has_required_signatures(master) and (_date(master.staff_signature_date) or date.max) <= master_due_date and (_date(master.client_signature_date) or date.max) <= master_due_date:
            rule_results.append(_result('TP-MASTER-30', 'Master Treatment Plan', master_due_date, TimelinessStatus.compliant.value, 'Master Treatment Plan was signed within 30 calendar days of admission.'))
        elif master is None:
            due_status, _ = _status_from_due_date(master_due_date, today)
            rule_results.append(_result('TP-MASTER-30', 'Master Treatment Plan', master_due_date, due_status or TimelinessStatus.missing_data.value, 'Master Treatment Plan record is missing.'))
        else:
            rule_results.append(_result('TP-MASTER-SIGNATURES', 'Master Treatment Plan signatures', master_due_date, TimelinessStatus.needs_review.value, 'Master Treatment Plan signatures are missing, incomplete, or after the 30-day window.'))

    last_review = _valid_review_date(plans)
    if last_review and interval_days:
        review_due = date.fromordinal(last_review.toordinal() + interval_days)
        due_status, _ = _status_from_due_date(review_due, today)
        rule_results.append(
            _result(
                f'TP-REVIEW-{interval_days}',
                'Ongoing Treatment Plan Review',
                review_due,
                due_status or TimelinessStatus.compliant.value,
                f'Latest valid staff/therapist review signature was {last_review.isoformat()} using {mapped_loc} {interval_days}-day recurrence.',
            )
        )
    elif mapped_loc:
        rule_results.append(_result('TP-REVIEW-MISSING', 'Ongoing Treatment Plan Review', None, TimelinessStatus.missing_data.value, 'No valid staff/therapist review signature date was found.'))

    if len(due_dates_for_comparison) > 1:
        rule_results.append(
            _result(
                'TP-DUE-DATE-CONFLICT',
                'Displayed and calculated due dates',
                min(due_dates_for_comparison),
                TimelinessStatus.needs_review.value,
                f'Due-date evidence conflicts: {comparison_explanation}',
            )
        )

    if len(loc_history) > 1:
        latest_loc = loc_history[-1]
        loc_effective = _date(latest_loc.effective_date)
        if not app_settings.treatment_plan_loc_change_window_validated or app_settings.treatment_plan_loc_change_window_days is None:
            rule_results.append(
                _result(
                    'TP-LOC-CHANGE-UNVALIDATED',
                    'Level-of-care change update',
                    loc_effective,
                    TimelinessStatus.needs_review.value,
                    'LOC-change update window is not validated by R3/Marleigh; manual review is required.',
                )
            )
        elif loc_effective:
            loc_due = date.fromordinal(loc_effective.toordinal() + app_settings.treatment_plan_loc_change_window_days)
            loc_update = _latest_plan(plans, TreatmentPlanKind.loc_update)
            signed = _date(loc_update.staff_signature_date) if loc_update else None
            if signed and signed <= loc_due:
                rule_results.append(_result('TP-LOC-CHANGE', 'Level-of-care change update', loc_due, TimelinessStatus.compliant.value, 'LOC-change update was signed inside the configured window.'))
            else:
                due_status, _ = _status_from_due_date(loc_due, today)
                rule_results.append(_result('TP-LOC-CHANGE', 'Level-of-care change update', loc_due, due_status or TimelinessStatus.missing_data.value, 'LOC-change update is missing or outside the configured window.'))

    if not rule_results:
        rule_results.append(_result('TP-MISSING-DATA', 'Treatment Plan Timeliness', None, TimelinessStatus.missing_data.value, 'Not enough source data to calculate timeliness.'))

    status, next_due_date, days_until_due, rule_used = _select_overall(rule_results, today)
    evidence_summary = '; '.join(result.evidence_summary for result in rule_results[:3])
    evidence_completeness_percent, missing_evidence_fields = _evidence_completeness(
        client,
        latest_review=latest_review,
        active_loc=active_loc,
        mapped_loc=mapped_loc,
        interval_days=interval_days,
        document_due=document_due,
    )
    evidence_comparison = EvidenceComparison(
        document_next_due_date=_date_str(document_due),
        signature_anchor_due_date=_date_str(signature_anchor_due),
        loc_anchor_due_date=_date_str(loc_anchor_due),
        final_status=status,
        conflict_explanation=comparison_explanation,
        source_evidence=_comparison_source_evidence(latest_review, active_loc),
        staff_signature_date=_date_str(staff_signature),
        loc_effective_date=_date_str(loc_effective),
        interval_days=interval_days,
        loc_change_window_days=app_settings.treatment_plan_loc_change_window_days,
        loc_change_rule_validated=app_settings.treatment_plan_loc_change_window_validated,
    )
    return TimelinessEvaluation(
        client=client,
        status=status,
        next_due_date=next_due_date,
        days_until_due=days_until_due,
        last_valid_review_date=_date_str(last_review),
        rule_used=rule_used,
        evidence_summary=evidence_summary,
        last_checked_at=checked_at,
        rule_results=rule_results,
        evidence_comparison=evidence_comparison,
        evidence_completeness_percent=evidence_completeness_percent,
        missing_evidence_fields=missing_evidence_fields,
    )


def _client_options():
    return (
        selectinload(TreatmentPlanClient.level_of_care_history),
        selectinload(TreatmentPlanClient.treatment_plans),
        selectinload(TreatmentPlanClient.overrides),
    )


def list_clients(db: Session, *, active_only: bool = True) -> list[TreatmentPlanClient]:
    stmt = select(TreatmentPlanClient).options(*_client_options()).order_by(TreatmentPlanClient.patient_id.asc())
    if active_only:
        stmt = stmt.where(TreatmentPlanClient.is_active.is_(True))
    return list(db.execute(stmt).scalars().unique().all())


def get_client(db: Session, client_id: int) -> TreatmentPlanClient | None:
    return db.execute(select(TreatmentPlanClient).options(*_client_options()).where(TreatmentPlanClient.id == client_id)).scalars().unique().one_or_none()


def upsert_client(db: Session, payload: Any, *, source_note_set_id: int | None = None) -> TreatmentPlanClient:
    patient_id = payload.patient_id.strip()
    client = db.execute(select(TreatmentPlanClient).options(*_client_options()).where(TreatmentPlanClient.patient_id == patient_id)).scalars().unique().one_or_none()
    if client is None:
        client = TreatmentPlanClient(patient_id=patient_id)
        db.add(client)
        db.flush()

    client.permitted_name = payload.permitted_name.strip() or display_name_for_patient_name_status(NAME_NOT_FOUND_STATUS, patient_id=patient_id)
    client.is_active = payload.is_active
    client.current_level_of_care = payload.current_level_of_care.strip()
    client.counselor_name = payload.counselor_name.strip()
    client.admission_date = payload.admission_date.strip()
    client.source_evidence = payload.source_evidence.strip()
    client.source_note_set_id = source_note_set_id
    client.last_imported_at = _utc_now()
    client.updated_at = _utc_now()

    client.level_of_care_history[:] = [
        LevelOfCareHistory(
            level_of_care=item.level_of_care.strip(),
            facility=item.facility.strip(),
            effective_date=item.effective_date.strip(),
            discharge_date=item.discharge_date.strip(),
            source_evidence=item.source_evidence.strip(),
            source_note_set_id=source_note_set_id,
        )
        for item in payload.level_of_care_history
        if item.level_of_care.strip()
    ]
    client.treatment_plans[:] = [
        TreatmentPlanRecord(
            plan_kind=normalize_plan_kind(item.plan_kind),
            document_date=item.document_date.strip(),
            staff_signature_date=item.staff_signature_date.strip(),
            client_signature_date=item.client_signature_date.strip(),
            reviewer_signature_date=item.reviewer_signature_date.strip(),
            displayed_next_due_date=item.displayed_next_due_date.strip(),
            source_evidence=item.source_evidence.strip(),
            source_section=item.source_section.strip(),
            source_document_id=item.source_document_id.strip(),
            source_note_set_id=source_note_set_id,
            is_valid=item.is_valid,
            conflict_note=item.conflict_note.strip(),
        )
        for item in payload.treatment_plans
    ]
    return client


def add_override(db: Session, client: TreatmentPlanClient, payload: Any, *, actor: User) -> TreatmentPlanOverride:
    override = TreatmentPlanOverride(
        client_id=client.id,
        field_name=payload.field_name.strip(),
        original_value=payload.original_value.strip(),
        new_value=payload.new_value.strip(),
        reason=payload.reason.strip(),
        affected_rule=payload.affected_rule.strip(),
        created_by_id=actor.id,
    )
    db.add(override)
    return override


def _document_plan_kind(document: PatientNoteDocument) -> TreatmentPlanKind | None:
    haystack = f'{document.document_label} {document.document_type} {document.description}'.lower()
    if 'initial' in haystack and 'treatment' in haystack:
        return TreatmentPlanKind.initial
    if 'master' in haystack and 'treatment' in haystack:
        return TreatmentPlanKind.master
    if 'loc' in haystack or 'level of care' in haystack:
        return TreatmentPlanKind.loc_update
    if 'treatment' in haystack and ('review' in haystack or 'plan' in haystack):
        return TreatmentPlanKind.review
    return None


def sync_from_note_set(db: Session, note_set: PatientNoteSet) -> TreatmentPlanClient:
    client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == note_set.patient_id)).scalar_one_or_none()
    if client is None:
        client = TreatmentPlanClient(patient_id=note_set.patient_id)
        db.add(client)
        db.flush()

    client.permitted_name = client.permitted_name or note_set.patient_id
    client.is_active = not bool(note_set.discharge_date.strip())
    client.current_level_of_care = note_set.level_of_care
    client.counselor_name = note_set.primary_clinician
    client.admission_date = note_set.admission_date
    client.source_note_set_id = note_set.id
    client.source_evidence = f'Patient note set {note_set.id} version {note_set.version}'
    client.last_imported_at = _utc_now()
    client.updated_at = _utc_now()

    db.execute(delete(LevelOfCareHistory).where(LevelOfCareHistory.client_id == client.id, LevelOfCareHistory.source_note_set_id == note_set.id))
    db.execute(delete(TreatmentPlanRecord).where(TreatmentPlanRecord.client_id == client.id, TreatmentPlanRecord.source_note_set_id == note_set.id))
    db.flush()

    if note_set.level_of_care:
        client.level_of_care_history.append(
            LevelOfCareHistory(
                level_of_care=note_set.level_of_care,
                facility=note_set.source_system,
                effective_date=note_set.admission_date,
                discharge_date=note_set.discharge_date,
                source_evidence=f'Upload metadata from note set {note_set.id}',
                source_note_set_id=note_set.id,
            )
        )

    for document in note_set.documents:
        kind = _document_plan_kind(document)
        if kind is None:
            continue
        signature_date = document.document_date
        client.treatment_plans.append(
            TreatmentPlanRecord(
                plan_kind=kind,
                document_date=document.document_date,
                staff_signature_date=signature_date if document.staff_signed else '',
                client_signature_date=signature_date if document.client_signed else '',
                source_evidence=f'{document.document_label or document.original_filename} from note set {note_set.id}',
                source_section=document.alleva_bucket.value,
                source_document_id=document.source_document_id or document.source_document_reference_id or str(document.id),
                source_note_set_id=note_set.id,
                is_valid=document.completion_status.value == 'completed',
                conflict_note='' if document.completion_status.value == 'completed' else 'Document is not marked completed.',
            )
        )

    return client


def summary_payload(evaluation: TimelinessEvaluation) -> dict[str, Any]:
    client = evaluation.client
    return {
        'id': client.id,
        'patient_id': client.patient_id,
        'permitted_name': client.permitted_name,
        'current_level_of_care': client.current_level_of_care,
        'counselor_name': client.counselor_name,
        'admission_date': client.admission_date,
        'last_valid_review_date': evaluation.last_valid_review_date,
        'next_due_date': evaluation.next_due_date,
        'days_until_due': evaluation.days_until_due,
        'status': evaluation.status,
        'rule_used': evaluation.rule_used,
        'evidence_summary': evaluation.evidence_summary,
        'evidence_completeness_percent': evaluation.evidence_completeness_percent,
        'missing_evidence_fields': evaluation.missing_evidence_fields,
        'last_checked_at': evaluation.last_checked_at,
        'last_imported_at': client.last_imported_at,
    }


def detail_payload(evaluation: TimelinessEvaluation, audit_history: list[Any]) -> dict[str, Any]:
    client = evaluation.client
    return {
        **summary_payload(evaluation),
        'is_active': client.is_active,
        'source_evidence': client.source_evidence,
        'evidence_comparison': evaluation.evidence_comparison.__dict__,
        'rule_results': [result.__dict__ for result in evaluation.rule_results],
        'level_of_care_history': [
            {
                'id': item.id,
                'level_of_care': item.level_of_care,
                'facility': item.facility,
                'effective_date': item.effective_date,
                'discharge_date': item.discharge_date,
                'interval_days': map_level_of_care(item.level_of_care)[1],
                'is_current': item.id == (_active_level_of_care(list(client.level_of_care_history)).id if _active_level_of_care(list(client.level_of_care_history)) else None),
                'source_evidence': item.source_evidence,
            }
            for item in sorted(client.level_of_care_history, key=lambda item: _date(item.effective_date) or date.min)
        ],
        'treatment_plans': [
            {
                'id': item.id,
                'plan_kind': item.plan_kind.value,
                'document_date': item.document_date,
                'staff_signature_date': item.staff_signature_date,
                'client_signature_date': item.client_signature_date,
                'reviewer_signature_date': item.reviewer_signature_date,
                'displayed_next_due_date': item.displayed_next_due_date,
                'source_evidence': item.source_evidence,
                'source_section': item.source_section,
                'source_document_id': item.source_document_id,
                'is_valid': item.is_valid,
                'conflict_note': item.conflict_note,
            }
            for item in sorted(client.treatment_plans, key=lambda item: (_date(item.staff_signature_date) or _date(item.document_date) or date.min, item.id or 0), reverse=True)
        ],
        'overrides': [
            {
                'id': item.id,
                'field_name': item.field_name,
                'original_value': item.original_value,
                'new_value': item.new_value,
                'reason': item.reason,
                'affected_rule': item.affected_rule,
                'created_by_id': item.created_by_id,
                'created_at': item.created_at,
            }
            for item in sorted(client.overrides, key=lambda item: item.created_at, reverse=True)
        ],
        'audit_history': audit_history,
    }
