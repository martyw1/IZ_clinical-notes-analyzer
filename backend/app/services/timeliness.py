from __future__ import annotations

import json
from dataclasses import dataclass, replace
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
from app.services.treatment_plan_checklist import load_treatment_plan_checklist
from app.services.timezone import localize_datetime

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
DEFAULT_LOC_CHANGE_WINDOW_DAYS = 7
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
    current_date: str
    date_clock_anchor_date: str | None
    date_clock_anchor_source: str
    date_clock_due_date: str | None
    loc_change_due_date: str | None
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
    current_date: str
    last_valid_review_date: str | None
    rule_used: str
    evidence_summary: str
    last_checked_at: datetime
    rule_results: list[RuleResult]
    evidence_comparison: EvidenceComparison
    evidence_completeness_percent: int
    missing_evidence_fields: list[str]


@dataclass(frozen=True)
class TimelinessChecklistResult:
    step: int
    key: str
    title: str
    status: str
    result: str
    severity: str
    source_evidence: str
    finding_message: str
    evidence_fields_used: list[str]
    required_metadata: list[str]
    required_documents: list[str]
    checks: list[str]
    finding_examples: list[str]
    remediation_suggestions: list[str]
    reviewer_actions: list[str]
    manual_override_allowed: bool
    override_reason_required: bool
    audit_event: str
    export_fields: list[str]
    manager_status: str = 'Not Reviewed'
    manager_comment: str = ''
    manager_updated_by_id: int | None = None
    manager_updated_at: datetime | None = None


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


def _loc_change_window_days(app_settings: AppSetting) -> int:
    return app_settings.treatment_plan_loc_change_window_days if app_settings.treatment_plan_loc_change_window_days is not None else DEFAULT_LOC_CHANGE_WINDOW_DAYS


def _status_from_due_date(due_date: date | None, evaluation_date: date) -> tuple[str | None, int | None]:
    days_until = _days_until(due_date, evaluation_date)
    if days_until is None:
        return None, None
    if days_until < 0:
        return TimelinessStatus.overdue.value, days_until
    if days_until <= 1:
        return TimelinessStatus.urgent.value, days_until
    if days_until <= 7:
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


def _selected_current_plan(client: TreatmentPlanClient, plans: list[TreatmentPlanRecord]) -> tuple[TreatmentPlanRecord | None, bool]:
    current_id = getattr(client, 'current_plan_record_id', None)
    if current_id:
        current = next((plan for plan in plans if plan.id == current_id), None)
        if current is not None:
            return current, True
    fallback = _latest_plan(plans, TreatmentPlanKind.master) or _latest_plan(plans, TreatmentPlanKind.initial)
    return fallback, False


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
    date_clock_due: date | None,
    loc_change_due: date | None,
    date_clock_anchor: date | None,
    date_clock_anchor_source: str,
    loc_effective: date | None,
    interval_days: int | None,
    loc_change_window_days: int | None,
    loc_change_validated: bool,
) -> str:
    parts = []
    if document_due:
        parts.append(f'source document Next Review Due is {document_due.isoformat()}')
    else:
        parts.append('source document Next Review Due is not recorded')
    if date_clock_due:
        parts.append(
            f'date clock due date is {date_clock_due.isoformat()}'
            f' ({date_clock_anchor_source} {date_clock_anchor.isoformat()} + {interval_days} days)'
            if date_clock_anchor and interval_days
            else f'date clock due date is {date_clock_due.isoformat()}'
        )
    else:
        parts.append('date clock due date could not be calculated')
    if loc_change_due:
        parts.append(
            f'LOC-change due date is {loc_change_due.isoformat()}'
            f' ({loc_effective.isoformat()} + {loc_change_window_days} days)'
            if loc_effective and loc_change_window_days is not None
            else f'LOC-change due date is {loc_change_due.isoformat()}'
        )
    else:
        parts.append('LOC-change due date could not be calculated or no LOC change is recorded')
    if not loc_change_validated:
        parts.append('LOC-change window is still marked unvalidated in settings')
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
    current_plan: TreatmentPlanRecord | None,
    current_plan_selected: bool,
    latest_review: TreatmentPlanRecord | None,
    active_loc: LevelOfCareHistory | None,
    mapped_loc: str | None,
    interval_days: int | None,
    document_due: date | None,
) -> tuple[int, list[str]]:
    current_plan_is_alleva = bool(current_plan and ('Alleva REST' in current_plan.source_evidence or 'Alleva REST' in current_plan.source_section))
    checks = [
        ('Admission date', _date(client.admission_date) is not None),
        ('Current level of care', bool(mapped_loc and interval_days is not None)),
        ('Level-of-care effective date', bool(active_loc and _date(active_loc.effective_date))),
        ('Treatment Plan Review staff signature', bool(latest_review and _date(latest_review.staff_signature_date))),
        ('Treatment Plan Review source evidence', bool(latest_review and latest_review.source_evidence.strip())),
        ('Source-document Next Review Due', document_due is not None),
    ]
    if current_plan_is_alleva:
        checks.append(('Current treatment plan selected', current_plan_selected))
    if current_plan and (current_plan.detail_fetched or current_plan_is_alleva):
        if current_plan.detail_fetched:
            checks.extend(
                [
                    ('Treatment plan has diagnoses', current_plan.diagnosis_count > 0),
                    ('Treatment plan has problems', current_plan.problem_count > 0),
                    ('Treatment plan has goals', current_plan.goal_count > 0),
                    ('Treatment plan has objectives', current_plan.objective_count > 0),
                    ('Treatment plan has interventions', current_plan.intervention_count > 0),
                    ('Treatment plan marked complete in Alleva', current_plan.alleva_is_complete),
                ]
            )
        else:
            checks.append(('Treatment plan clinical detail fetched', False))
    complete = sum(1 for _label, is_complete in checks if is_complete)
    score = round((complete / len(checks)) * 100) if checks else 0
    missing = [label for label, is_complete in checks if not is_complete]
    return score, missing


def evaluate_client(client: TreatmentPlanClient, app_settings: AppSetting, *, evaluation_date: date | None = None) -> TimelinessEvaluation:
    checked_at = _utc_now()
    today = evaluation_date or localize_datetime(checked_at, app_settings.facility_timezone).date()
    plans = list(client.treatment_plans)
    loc_history = sorted(client.level_of_care_history, key=lambda item: _date(item.effective_date) or date.min)
    rule_results: list[RuleResult] = []

    admission = _date(client.admission_date)
    mapped_loc, interval_days = map_level_of_care(client.current_level_of_care)
    has_conflict = any(plan.conflict_note.strip() for plan in plans)
    latest_review = _latest_review_plan(plans)
    current_plan, current_plan_selected = _selected_current_plan(client, plans)
    active_loc = _active_level_of_care(loc_history)
    document_due = _date(latest_review.displayed_next_due_date) if latest_review else None
    staff_signature = _date(latest_review.staff_signature_date) if latest_review else None
    loc_effective = _date(active_loc.effective_date) if active_loc else None
    last_review = _valid_review_date(plans)
    current_plan_anchor = (
        _date(current_plan.alleva_start_date)
        or _date(current_plan.document_date)
        or _date(current_plan.alleva_last_modified)
        if current_plan is not None
        else None
    )
    date_clock_anchor = last_review or admission or current_plan_anchor
    if last_review:
        date_clock_anchor_source = 'last valid treatment-plan review/update date'
    elif admission:
        date_clock_anchor_source = 'admission date'
    else:
        date_clock_anchor_source = 'current treatment-plan start/modified date'
    signature_anchor_due = _add_days(date_clock_anchor, interval_days)
    loc_change_window_days = _loc_change_window_days(app_settings)
    loc_anchor_due = _add_days(loc_effective, loc_change_window_days) if len(loc_history) > 1 else None
    due_dates_for_comparison = {item for item in (document_due, signature_anchor_due, loc_anchor_due) if item is not None}
    comparison_explanation = _describe_due_date_comparison(
        document_due=document_due,
        date_clock_due=signature_anchor_due,
        loc_change_due=loc_anchor_due,
        date_clock_anchor=date_clock_anchor,
        date_clock_anchor_source=date_clock_anchor_source,
        loc_effective=loc_effective,
        interval_days=interval_days,
        loc_change_window_days=loc_change_window_days,
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

    if date_clock_anchor and interval_days:
        review_due = date.fromordinal(date_clock_anchor.toordinal() + interval_days)
        due_status, _ = _status_from_due_date(review_due, today)
        rule_results.append(
            _result(
                f'TP-REVIEW-{interval_days}',
                'Ongoing Treatment Plan Review',
                review_due,
                due_status or TimelinessStatus.compliant.value,
                f'Date clock used {date_clock_anchor_source} {date_clock_anchor.isoformat()} against current date {today.isoformat()} using {mapped_loc} {interval_days}-calendar-day recurrence.',
            )
        )
        if latest_review is not None and staff_signature is None:
            rule_results.append(
                _result(
                    'TP-REVIEW-SIGNATURE-MISSING',
                    'Treatment Plan Review signature',
                    review_due,
                    TimelinessStatus.needs_review.value,
                    'A treatment-plan review/update record exists, but no staff/therapist signature date was found for the date clock.',
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
        loc_due = _add_days(loc_effective, loc_change_window_days)
        if not app_settings.treatment_plan_loc_change_window_validated:
            rule_results.append(
                _result(
                    'TP-LOC-CHANGE-UNVALIDATED',
                    'Level-of-care change update',
                    loc_due,
                    TimelinessStatus.needs_review.value,
                    f'LOC-change update preset is {loc_change_window_days} calendar days, but settings still mark the rule unvalidated; manual review is required.',
                )
            )
        elif loc_due:
            loc_update = _latest_plan(plans, TreatmentPlanKind.loc_update)
            signed = _date(loc_update.staff_signature_date) if loc_update else None
            if signed and signed <= loc_due:
                rule_results.append(_result('TP-LOC-CHANGE', 'Level-of-care change update', loc_due, TimelinessStatus.compliant.value, 'LOC-change update was signed inside the configured window.'))
            else:
                due_status, _ = _status_from_due_date(loc_due, today)
                rule_results.append(_result('TP-LOC-CHANGE', 'Level-of-care change update', loc_due, due_status or TimelinessStatus.missing_data.value, 'LOC-change update is missing or outside the configured window.'))
        else:
            rule_results.append(
                _result(
                    'TP-LOC-CHANGE-MISSING-DATE',
                    'Level-of-care change update',
                    None,
                    TimelinessStatus.missing_data.value,
                    'A level-of-care change is present, but the effective date needed for the LOC-change clock is missing or unreadable.',
                )
            )

    if not rule_results:
        rule_results.append(_result('TP-MISSING-DATA', 'Treatment Plan Timeliness', None, TimelinessStatus.missing_data.value, 'Not enough source data to calculate timeliness.'))

    status, next_due_date, days_until_due, rule_used = _select_overall(rule_results, today)
    evidence_summary = '; '.join(result.evidence_summary for result in rule_results[:3])
    evidence_completeness_percent, missing_evidence_fields = _evidence_completeness(
        client,
        current_plan=current_plan,
        current_plan_selected=current_plan_selected,
        latest_review=latest_review,
        active_loc=active_loc,
        mapped_loc=mapped_loc,
        interval_days=interval_days,
        document_due=document_due,
    )
    if current_plan is not None and ('Alleva REST' in current_plan.source_evidence or 'Alleva REST' in current_plan.source_section) and not current_plan_selected:
        missing_evidence_fields.append('current_plan_not_selected')
    evidence_comparison = EvidenceComparison(
        document_next_due_date=_date_str(document_due),
        signature_anchor_due_date=_date_str(signature_anchor_due),
        loc_anchor_due_date=_date_str(loc_anchor_due),
        current_date=today.isoformat(),
        date_clock_anchor_date=_date_str(date_clock_anchor),
        date_clock_anchor_source=date_clock_anchor_source,
        date_clock_due_date=_date_str(signature_anchor_due),
        loc_change_due_date=_date_str(loc_anchor_due),
        final_status=status,
        conflict_explanation=comparison_explanation,
        source_evidence=_comparison_source_evidence(latest_review, active_loc),
        staff_signature_date=_date_str(staff_signature),
        loc_effective_date=_date_str(loc_effective),
        interval_days=interval_days,
        loc_change_window_days=loc_change_window_days,
        loc_change_rule_validated=app_settings.treatment_plan_loc_change_window_validated,
    )
    return TimelinessEvaluation(
        client=client,
        status=status,
        next_due_date=next_due_date,
        days_until_due=days_until_due,
        current_date=today.isoformat(),
        last_valid_review_date=_date_str(last_review),
        rule_used=rule_used,
        evidence_summary=evidence_summary,
        last_checked_at=checked_at,
        rule_results=rule_results,
        evidence_comparison=evidence_comparison,
        evidence_completeness_percent=evidence_completeness_percent,
        missing_evidence_fields=missing_evidence_fields,
    )


def _combined_evidence(*values: str | None) -> str:
    parts = [value.strip() for value in values if value and value.strip()]
    return '; '.join(dict.fromkeys(parts))


def _rule_result_by_id(rule_results: list[RuleResult], rule_id: str) -> RuleResult | None:
    return next((result for result in rule_results if result.rule_id == rule_id), None)


def _rule_result_by_prefix(rule_results: list[RuleResult], prefix: str) -> RuleResult | None:
    return next((result for result in rule_results if result.rule_id.startswith(prefix)), None)


def _plan_evidence(plan: TreatmentPlanRecord | None) -> str:
    if plan is None:
        return ''
    return _combined_evidence(plan.source_evidence, plan.source_section, plan.source_document_id)


def _plans_evidence(plans: list[TreatmentPlanRecord]) -> str:
    return _combined_evidence(*[_plan_evidence(plan) for plan in plans])


def _json_list_values(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return [value.strip()] if value.strip() else []
    if isinstance(payload, list):
        return [str(item) for item in payload if str(item).strip()]
    return []


def _status_for_presence(is_present: bool, *, missing_status: str = TimelinessStatus.missing_data.value) -> str:
    return 'Confirmed' if is_present else missing_status


def _status_for_rule(result: RuleResult | None, *, missing_status: str = TimelinessStatus.needs_review.value) -> str:
    return result.status if result is not None else missing_status


def _checklist_result(
    step: dict[str, Any],
    *,
    status: str,
    finding_message: str,
    source_evidence: str = '',
    evidence_fields_used: list[str] | None = None,
    severity: str | None = None,
) -> TimelinessChecklistResult:
    return TimelinessChecklistResult(
        step=int(step['step']),
        key=str(step['key']),
        title=str(step['title']),
        status=status,
        result=status,
        severity=severity or str(step.get('severity_default') or 'info'),
        source_evidence=source_evidence,
        finding_message=finding_message,
        evidence_fields_used=evidence_fields_used or [],
        required_metadata=[str(item) for item in step.get('required_metadata', [])],
        required_documents=[str(item) for item in step.get('required_documents', [])],
        checks=[str(item) for item in step.get('checks', [])],
        finding_examples=[str(item) for item in step.get('finding_examples', [])],
        remediation_suggestions=[str(item) for item in step.get('remediation_suggestions', [])],
        reviewer_actions=[str(item) for item in step.get('reviewer_actions', [])],
        manual_override_allowed=bool(step.get('manual_override')),
        override_reason_required=bool(step.get('override_reason_required')),
        audit_event=str(step.get('audit_event') or ''),
        export_fields=[str(item) for item in step.get('export_fields', [])],
    )


def build_checklist_results(evaluation: TimelinessEvaluation, audit_history: list[Any]) -> list[TimelinessChecklistResult]:
    client = evaluation.client
    plans = list(client.treatment_plans)
    loc_history = sorted(client.level_of_care_history, key=lambda item: _date(item.effective_date) or date.min)
    rule_results = evaluation.rule_results
    admission = _date(client.admission_date)
    mapped_loc, interval_days = map_level_of_care(client.current_level_of_care)
    active_loc = _active_level_of_care(loc_history)
    initial = _latest_plan(plans, TreatmentPlanKind.initial)
    master = _latest_plan(plans, TreatmentPlanKind.master)
    latest_review = _latest_review_plan(plans)
    loc_update = _latest_plan(plans, TreatmentPlanKind.loc_update)
    loc_change_present = len(loc_history) > 1
    source_evidence = _combined_evidence(client.source_evidence, evaluation.evidence_comparison.source_evidence)
    plans_source_evidence = _plans_evidence(plans)
    checklist = load_treatment_plan_checklist()
    steps_by_key = {step['key']: step for step in checklist['steps']}

    initial_rule = _rule_result_by_prefix(rule_results, 'TP-INITIAL')
    master_rule = _rule_result_by_prefix(rule_results, 'TP-MASTER')
    review_rule = _rule_result_by_prefix(rule_results, 'TP-REVIEW-')
    loc_change_rule = _rule_result_by_prefix(rule_results, 'TP-LOC-CHANGE')
    conflict_rule = _rule_result_by_id(rule_results, 'TP-DUE-DATE-CONFLICT') or _rule_result_by_id(rule_results, 'TP-CONFLICTING-EVIDENCE')

    def step(key: str, status: str, finding: str, evidence: str = '', fields: list[str] | None = None) -> TimelinessChecklistResult:
        return _checklist_result(
            steps_by_key[key],
            status=status,
            finding_message=finding,
            source_evidence=evidence or source_evidence,
            evidence_fields_used=fields or [],
        )

    results = [
        step(
            'confirm_correct_client_chart',
            _status_for_presence(bool(client.patient_id), missing_status=TimelinessStatus.missing_data.value),
            f'Selected treatment-plan client is keyed by patient ID {client.patient_id}.' if client.patient_id else 'No patient ID is available for this selected treatment-plan client.',
            client.source_evidence,
            ['patient_id', 'source_evidence'],
        ),
        step(
            'classify_new_or_update_review',
            'Confirmed' if client.source_note_set_id or client.last_imported_at else TimelinessStatus.needs_review.value,
            'The selected item has import/upload history for point-in-time review.' if client.source_note_set_id or client.last_imported_at else 'No import/upload timestamp is available; reviewer should confirm whether this is a new baseline or update.',
            client.source_evidence,
            ['source_note_set_id', 'last_imported_at'],
        ),
        step(
            'confirm_client_active',
            'Confirmed' if client.is_active else 'Not Applicable',
            'Client is in the active treatment-plan queue.' if client.is_active else 'Client is not marked active, so routine active-client tracking may not apply.',
            client.source_evidence,
            ['active_status'],
        ),
        step(
            'confirm_admission_date',
            _status_for_presence(admission is not None, missing_status=TimelinessStatus.missing_data.value),
            f'Admission date is {client.admission_date}.' if admission else 'Admission date is missing or unreadable.',
            client.source_evidence,
            ['admission_date'],
        ),
        step(
            'confirm_current_loc',
            _status_for_presence(bool(client.current_level_of_care.strip()), missing_status=TimelinessStatus.missing_data.value),
            f'Current LOC is {client.current_level_of_care}.' if client.current_level_of_care.strip() else 'Current LOC is missing.',
            _combined_evidence(client.source_evidence, active_loc.source_evidence if active_loc else ''),
            ['current_level_of_care'],
        ),
        step(
            'confirm_loc_rule_mapping',
            'Confirmed' if mapped_loc and interval_days is not None else (TimelinessStatus.missing_data.value if not client.current_level_of_care.strip() else TimelinessStatus.unable_to_evaluate.value),
            f'LOC {client.current_level_of_care} maps to {mapped_loc} with a {interval_days}-calendar-day review clock.' if mapped_loc and interval_days is not None else 'LOC is missing or does not map to a configured treatment-plan cadence.',
            _combined_evidence(client.source_evidence, active_loc.source_evidence if active_loc else ''),
            ['current_level_of_care', 'mapped_level_of_care', 'rules_version'],
        ),
        step(
            'capture_loc_history',
            'Confirmed' if loc_history and all(_date(item.effective_date) for item in loc_history) else (TimelinessStatus.missing_data.value if not loc_history else TimelinessStatus.needs_review.value),
            f'{len(loc_history)} LOC history row(s) are available.' if loc_history else 'No LOC history rows are available for the selected client.',
            _combined_evidence(*[item.source_evidence for item in loc_history]),
            ['loc_history', 'effective_date', 'discharge_date'],
        ),
        step(
            'classify_source_documents',
            'Confirmed' if plans else TimelinessStatus.missing_data.value,
            f'{len(plans)} treatment-plan evidence record(s) are classified for this selected client.' if plans else 'No treatment-plan source documents are loaded.',
            plans_source_evidence,
            ['document_type', 'source_document_id', 'source_section'],
        ),
        step(
            'confirm_document_dates',
            'Confirmed' if plans and all(_date(plan.document_date) or _date(plan.staff_signature_date) for plan in plans) else (TimelinessStatus.missing_data.value if not plans else TimelinessStatus.needs_review.value),
            'Loaded treatment-plan evidence has document or staff signature dates.' if plans and all(_date(plan.document_date) or _date(plan.staff_signature_date) for plan in plans) else 'One or more treatment-plan evidence records is missing a usable date.',
            plans_source_evidence,
            ['document_date', 'source_evidence'],
        ),
        step(
            'confirm_document_completion_status',
            'Confirmed' if plans and all(plan.is_valid and not plan.conflict_note.strip() for plan in plans) else (TimelinessStatus.missing_data.value if not plans else TimelinessStatus.needs_review.value),
            'Loaded treatment-plan records are marked valid with no conflict notes.' if plans and all(plan.is_valid and not plan.conflict_note.strip() for plan in plans) else 'At least one treatment-plan record is missing, invalid, incomplete, or flagged for conflict review.',
            plans_source_evidence,
            ['completion_status', 'source_evidence'],
        ),
        step(
            'confirm_staff_signature_status',
            'Confirmed' if plans and any(_date(plan.staff_signature_date) for plan in plans) else TimelinessStatus.missing_data.value,
            'At least one staff/therapist signature date is available.' if plans and any(_date(plan.staff_signature_date) for plan in plans) else 'No staff/therapist signature date is available.',
            plans_source_evidence,
            ['staff_signature_date'],
        ),
        step(
            'confirm_client_signature_status',
            'Confirmed' if plans and any(_date(plan.client_signature_date) for plan in plans) else TimelinessStatus.needs_review.value,
            'At least one client signature date is available.' if plans and any(_date(plan.client_signature_date) for plan in plans) else 'Client signature evidence is absent or optional for the loaded review evidence; reviewer should confirm applicability.',
            plans_source_evidence,
            ['client_signature_date'],
        ),
        step(
            'check_conflicting_evidence',
            conflict_rule.status if conflict_rule else 'Confirmed',
            conflict_rule.evidence_summary if conflict_rule else 'No conflicting evidence rule is currently blocking this selected client.',
            _combined_evidence(plans_source_evidence, evaluation.evidence_comparison.conflict_explanation),
            ['conflict_note', 'rule_used'],
        ),
        step(
            'initial_plan_exists',
            _status_for_presence(initial is not None, missing_status=TimelinessStatus.missing_data.value),
            'Initial Treatment Plan evidence is loaded.' if initial else 'Initial Treatment Plan evidence is missing.',
            _plan_evidence(initial),
            ['document_type', 'source_document_id'],
        ),
        step(
            'initial_plan_dated_correctly',
            _status_for_rule(initial_rule) if initial else TimelinessStatus.missing_data.value,
            initial_rule.evidence_summary if initial_rule else 'Initial Treatment Plan date cannot be verified because initial-plan evidence is missing.',
            _plan_evidence(initial),
            ['admission_date', 'document_date', 'staff_signature_date'],
        ),
        step(
            'initial_plan_required_signatures',
            _status_for_presence(_plan_has_required_signatures(initial), missing_status=TimelinessStatus.needs_review.value if initial else TimelinessStatus.missing_data.value),
            'Initial Treatment Plan has required staff and client signature dates.' if _plan_has_required_signatures(initial) else 'Initial Treatment Plan signatures are missing, incomplete, or require reviewer confirmation.',
            _plan_evidence(initial),
            ['staff_signature_date', 'client_signature_date'],
        ),
        step(
            'master_plan_exists',
            _status_for_presence(master is not None, missing_status=TimelinessStatus.missing_data.value),
            'Master Treatment Plan evidence is loaded.' if master else 'Master Treatment Plan evidence is missing.',
            _plan_evidence(master),
            ['document_type', 'source_document_id'],
        ),
        step(
            'master_plan_within_30_days',
            _status_for_rule(master_rule) if master or admission else TimelinessStatus.missing_data.value,
            master_rule.evidence_summary if master_rule else 'Master Treatment Plan 30-day timing cannot be verified from available evidence.',
            _plan_evidence(master),
            ['admission_date', 'document_date', 'staff_signature_date'],
        ),
        step(
            'master_plan_required_signatures',
            _status_for_presence(_plan_has_required_signatures(master), missing_status=TimelinessStatus.needs_review.value if master else TimelinessStatus.missing_data.value),
            'Master Treatment Plan has required staff and client signature dates.' if _plan_has_required_signatures(master) else 'Master Treatment Plan signatures are missing, incomplete, or require reviewer confirmation.',
            _plan_evidence(master),
            ['staff_signature_date', 'client_signature_date'],
        ),
        step(
            'latest_valid_review_identified',
            'Confirmed' if latest_review and evaluation.last_valid_review_date else TimelinessStatus.missing_data.value,
            f'Latest valid review/update date is {evaluation.last_valid_review_date}.' if latest_review and evaluation.last_valid_review_date else 'No latest valid treatment-plan review/update date is available.',
            _plan_evidence(latest_review),
            ['latest_valid_review_date', 'staff_signature_date'],
        ),
        step(
            'calculate_next_review_due_date',
            _status_for_rule(review_rule, missing_status=TimelinessStatus.missing_data.value),
            review_rule.evidence_summary if review_rule else 'Next review due date could not be calculated from admission/review and LOC evidence.',
            _combined_evidence(_plan_evidence(latest_review), evaluation.evidence_comparison.conflict_explanation),
            ['date_clock_anchor_date', 'interval_days', 'next_due_date'],
        ),
        step(
            'apply_php_timing_rule',
            _status_for_rule(review_rule) if mapped_loc == 'php' else 'Not Applicable',
            review_rule.evidence_summary if mapped_loc == 'php' and review_rule else 'PHP timing does not apply to the selected current LOC.' if mapped_loc != 'php' else 'PHP timing could not be evaluated.',
            source_evidence,
            ['current_level_of_care', 'interval_days'],
        ),
        step(
            'apply_iop_op_timing_rule',
            _status_for_rule(review_rule) if mapped_loc and mapped_loc != 'php' else 'Not Applicable',
            review_rule.evidence_summary if mapped_loc and mapped_loc != 'php' and review_rule else 'IOP/OP timing does not apply to the selected current LOC.' if mapped_loc == 'php' else 'IOP/OP timing could not be evaluated.',
            source_evidence,
            ['current_level_of_care', 'interval_days'],
        ),
        step(
            'mark_current_inside_window',
            'Confirmed' if evaluation.status == TimelinessStatus.compliant.value else 'Not Applicable',
            'Selected treatment plan is inside the allowed window.' if evaluation.status == TimelinessStatus.compliant.value else f'Selected treatment plan final status is {evaluation.status}, not current/compliant.',
            evaluation.evidence_summary,
            ['overall_status', 'next_due_date'],
        ),
        step(
            'mark_due_soon',
            evaluation.status if evaluation.status in {TimelinessStatus.due_soon.value, TimelinessStatus.urgent.value} else 'Not Applicable',
            f'Selected treatment plan is {evaluation.status.lower()} with next due date {evaluation.next_due_date}.' if evaluation.status in {TimelinessStatus.due_soon.value, TimelinessStatus.urgent.value} else 'Due-soon/urgent status does not apply to this selected treatment plan.',
            evaluation.evidence_summary,
            ['overall_status', 'days_until_due', 'next_due_date'],
        ),
        step(
            'mark_overdue',
            evaluation.status if evaluation.status == TimelinessStatus.overdue.value else 'Not Applicable',
            f'Selected treatment plan is overdue by {abs(evaluation.days_until_due or 0)} day(s).' if evaluation.status == TimelinessStatus.overdue.value else 'Overdue status does not apply to this selected treatment plan.',
            evaluation.evidence_summary,
            ['overall_status', 'days_until_due', 'next_due_date'],
        ),
        step(
            'check_php_individual_session_evidence',
            TimelinessStatus.needs_review.value if mapped_loc == 'php' else 'Not Applicable',
            'PHP individual-session evidence is not deterministically evaluated yet; reviewer should confirm if required.' if mapped_loc == 'php' else 'PHP individual-session evidence does not apply to the selected current LOC.',
            source_evidence,
            ['current_level_of_care'],
        ),
        step(
            'check_iop_op_individual_session_evidence',
            TimelinessStatus.needs_review.value if mapped_loc and mapped_loc != 'php' else 'Not Applicable',
            'IOP/OP individual-session evidence is not deterministically evaluated yet; reviewer should confirm if required.' if mapped_loc and mapped_loc != 'php' else 'IOP/OP individual-session evidence does not apply to the selected current LOC.',
            source_evidence,
            ['current_level_of_care'],
        ),
        step(
            'identify_loc_change',
            'Confirmed' if loc_change_present else 'Not Applicable',
            f'LOC history includes {len(loc_history)} rows, so an LOC change is present.' if loc_change_present else 'No LOC change is present in the loaded history.',
            _combined_evidence(*[item.source_evidence for item in loc_history]),
            ['previous_level_of_care', 'current_level_of_care', 'loc_effective_date'],
        ),
        step(
            'loc_change_update_document',
            _status_for_presence(loc_update is not None, missing_status=TimelinessStatus.missing_data.value) if loc_change_present else 'Not Applicable',
            'LOC-change update evidence is loaded.' if loc_update else 'LOC changed but no LOC-change update document is loaded.' if loc_change_present else 'No LOC change is present, so an LOC-change update document is not required.',
            _plan_evidence(loc_update),
            ['loc_change_document', 'loc_effective_date', 'source_evidence'],
        ),
        step(
            'loc_change_deadline_unresolved',
            loc_change_rule.status if loc_change_rule else ('Not Applicable' if not loc_change_present else 'Confirmed'),
            loc_change_rule.evidence_summary if loc_change_rule else 'No LOC-change deadline blocker applies to this selected client.' if not loc_change_present else 'LOC-change window is marked validated for this selected client calculation.',
            _combined_evidence(_plan_evidence(loc_update), evaluation.evidence_comparison.conflict_explanation),
            ['loc_change_window_days', 'loc_change_rule_validated', 'clock_start_source'],
        ),
        step(
            'flag_missing_data_not_compliance',
            TimelinessStatus.missing_data.value if evaluation.missing_evidence_fields else 'Confirmed',
            f'Missing evidence fields: {", ".join(evaluation.missing_evidence_fields)}.' if evaluation.missing_evidence_fields else 'No missing evidence fields passed silently in this deterministic calculation.',
            evaluation.evidence_summary,
            ['missing_evidence_fields', 'rule_used'],
        ),
        step(
            'allow_manual_reviewer_confirmation',
            TimelinessStatus.needs_review.value if evaluation.status in {TimelinessStatus.needs_review.value, TimelinessStatus.missing_data.value, TimelinessStatus.conflicting.value, TimelinessStatus.unable_to_evaluate.value} else 'Confirmed',
            'Manual reviewer confirmation is available for admin/manager review; counselors remain read-only for override decisions.' if evaluation.status in {TimelinessStatus.needs_review.value, TimelinessStatus.missing_data.value, TimelinessStatus.conflicting.value, TimelinessStatus.unable_to_evaluate.value} else 'No blocking manual confirmation is required by the current deterministic result.',
            evaluation.evidence_summary,
            ['reviewer', 'review_action', 'comment'],
        ),
        step(
            'require_manual_override_reason',
            'Confirmed' if client.overrides else 'Not Applicable',
            f'{len(client.overrides)} override(s) are recorded with required reasons.' if client.overrides else 'No manual override is recorded for this selected client.',
            _combined_evidence(*[override.affected_rule for override in client.overrides]),
            ['override_reason', 'affected_rule', 'created_by'],
        ),
        step(
            'produce_final_checklist_result',
            evaluation.status,
            f'Final selected-client result is {evaluation.status}; rule used: {evaluation.rule_used}.',
            evaluation.evidence_summary,
            ['overall_status', 'severity_counts', 'evidence_summary'],
        ),
        step(
            'update_status_worklist_after_review',
            'Confirmed',
            f'Worklist status for this selected client is {evaluation.status}.',
            evaluation.evidence_summary,
            ['worklist_status', 'last_status_change_at'],
        ),
        step(
            'route_chart_for_manager_review',
            TimelinessStatus.needs_review.value if evaluation.status in {TimelinessStatus.overdue.value, TimelinessStatus.urgent.value, TimelinessStatus.due_soon.value, TimelinessStatus.needs_review.value, TimelinessStatus.missing_data.value, TimelinessStatus.conflicting.value, TimelinessStatus.unable_to_evaluate.value} else 'Confirmed',
            'Manager/admin review path remains available for this selected-client result.' if evaluation.status != TimelinessStatus.compliant.value else 'Selected client is currently compliant; manager routing is available if final approval is needed.',
            evaluation.evidence_summary,
            ['manager_review_state', 'reviewer_role'],
        ),
        step(
            'return_chart_with_correction_comments',
            TimelinessStatus.needs_review.value if evaluation.status in {TimelinessStatus.overdue.value, TimelinessStatus.needs_review.value, TimelinessStatus.missing_data.value, TimelinessStatus.conflicting.value, TimelinessStatus.unable_to_evaluate.value} else 'Not Applicable',
            'If returned, manager comments must specify the missing, conflicting, or late evidence.' if evaluation.status != TimelinessStatus.compliant.value else 'No return-for-correction condition is currently indicated by this deterministic result.',
            evaluation.evidence_summary,
            ['correction_comment', 'returned_by', 'returned_at'],
        ),
        step(
            'approve_after_issues_resolved_or_accepted',
            'Confirmed' if evaluation.status in {TimelinessStatus.compliant.value, TimelinessStatus.approved.value} else TimelinessStatus.needs_review.value,
            'Selected client can proceed toward approval because deterministic timing is compliant or already approved.' if evaluation.status in {TimelinessStatus.compliant.value, TimelinessStatus.approved.value} else 'Approval should wait until blocking checklist findings are resolved or manually accepted with reason.',
            evaluation.evidence_summary,
            ['approval_state', 'accepted_issue_count', 'approved_by'],
        ),
        step(
            'preserve_review_history',
            'Confirmed' if audit_history else TimelinessStatus.needs_review.value,
            f'{len(audit_history)} audit event(s) are available in the selected-client detail payload.' if audit_history else 'No audit history is loaded for this selected client detail.',
            _combined_evidence(*[getattr(log, 'action', '') for log in audit_history[:5]]),
            ['audit_event_id', 'audit_action', 'timestamp'],
        ),
        step(
            'continue_periodic_api_monitoring',
            'Confirmed' if client.last_imported_at and 'Alleva REST' in client.source_evidence else TimelinessStatus.needs_review.value,
            'Selected client has Alleva REST import evidence; ongoing API monitoring remains subject to approval and settings.' if client.last_imported_at and 'Alleva REST' in client.source_evidence else 'Selected client is not proven to come from approved live API monitoring; use manual/upload workflow or approved API settings as applicable.',
            client.source_evidence,
            ['last_refresh_at', 'next_refresh_at', 'changed_item_count', 'error_count'],
        ),
        step(
            'use_synthetic_or_approved_non_phi_data',
            'Confirmed' if 'synthetic' in source_evidence.lower() or client.patient_id.upper().startswith(('PAT-', 'SYNTH-')) else TimelinessStatus.needs_review.value,
            'Selected-client evidence appears to be synthetic/non-production validation data.' if 'synthetic' in source_evidence.lower() or client.patient_id.upper().startswith(('PAT-', 'SYNTH-')) else 'Reviewer must confirm this selected-client evidence is approved for the current environment and not unsafe validation data.',
            source_evidence,
            ['validation_data_kind', 'artifact_path', 'redaction_status'],
        ),
    ]
    reviews_by_key = {review.criterion_key: review for review in client.criterion_reviews}
    enriched_results = []
    for result in results:
        review = reviews_by_key.get(result.key)
        if review is None:
            enriched_results.append(result)
            continue
        enriched_results.append(
            replace(
                result,
                manager_status=review.status or 'Not Reviewed',
                manager_comment=review.comment or '',
                manager_updated_by_id=review.updated_by_id,
                manager_updated_at=review.updated_at,
            )
        )
    return sorted(enriched_results, key=lambda item: item.step)


def _client_options():
    return (
        selectinload(TreatmentPlanClient.level_of_care_history),
        selectinload(TreatmentPlanClient.treatment_plans),
        selectinload(TreatmentPlanClient.current_plan_record),
        selectinload(TreatmentPlanClient.overrides),
        selectinload(TreatmentPlanClient.criterion_reviews),
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
    client.current_plan_record_id = None
    db.flush()

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
    db.flush()
    selected, _selected_by_id = _selected_current_plan(client, list(client.treatment_plans))
    if selected is not None:
        client.current_plan_record_id = selected.id
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


def _document_source_evidence(document: PatientNoteDocument, *, note_set_id: int) -> str:
    label = document.document_label or document.original_filename or 'Treatment plan document'
    parts = [f'{label} from note set {note_set_id}']
    if document.original_filename.lower().endswith('.pdf'):
        parts.append('manual upload page 1')
    if document.source_document_id.strip():
        parts.append(f'Alleva document ID {document.source_document_id.strip()}')
    if document.source_attachment_url.strip():
        parts.append(f'attachment {document.source_attachment_url.strip()}')
    return '; '.join(parts)


def sync_from_note_set(db: Session, note_set: PatientNoteSet) -> TreatmentPlanClient:
    client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == note_set.patient_id)).scalar_one_or_none()
    if client is None:
        client = TreatmentPlanClient(patient_id=note_set.patient_id)
        db.add(client)
        db.flush()

    client.permitted_name = client.permitted_name or display_name_for_patient_name_status(NAME_NOT_FOUND_STATUS, patient_id=note_set.patient_id)
    client.is_active = not bool(note_set.discharge_date.strip())
    client.current_level_of_care = note_set.level_of_care
    client.counselor_name = note_set.primary_clinician
    client.admission_date = note_set.admission_date
    client.source_note_set_id = note_set.id
    client.source_evidence = f'Patient note set {note_set.id} version {note_set.version}'
    client.last_imported_at = _utc_now()
    client.updated_at = _utc_now()
    client.current_plan_record_id = None
    db.flush()

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
                source_evidence=f'Upload metadata from note set {note_set.id}; manual upload page 1',
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
                source_evidence=_document_source_evidence(document, note_set_id=note_set.id),
                source_section=document.alleva_bucket.value,
                source_document_id=document.source_document_id or str(document.id),
                source_note_set_id=note_set.id,
                is_valid=document.completion_status.value == 'completed',
                conflict_note='' if document.completion_status.value == 'completed' else 'Document is not marked completed.',
            )
        )

    db.flush()
    selected, _selected_by_id = _selected_current_plan(client, list(client.treatment_plans))
    if selected is not None:
        client.current_plan_record_id = selected.id
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
        'current_date': evaluation.current_date,
        'status': evaluation.status,
        'rule_used': evaluation.rule_used,
        'evidence_summary': evaluation.evidence_summary,
        'evidence_completeness_percent': evaluation.evidence_completeness_percent,
        'missing_evidence_fields': evaluation.missing_evidence_fields,
        'last_checked_at': evaluation.last_checked_at,
        'last_imported_at': client.last_imported_at,
        'discharge_conflict': client.discharge_conflict,
        'data_quality_warnings': _json_list_values(client.data_quality_warnings),
        'id_join_confidence': client.id_join_confidence,
        'current_plan_record_id': client.current_plan_record_id,
    }


def detail_payload(evaluation: TimelinessEvaluation, audit_history: list[Any]) -> dict[str, Any]:
    client = evaluation.client
    checklist = load_treatment_plan_checklist()
    checklist_results = build_checklist_results(evaluation, audit_history)
    return {
        **summary_payload(evaluation),
        'is_active': client.is_active,
        'source_evidence': client.source_evidence,
        'alleva_lead_id': client.alleva_lead_id,
        'alleva_client_id': client.alleva_client_id,
        'alleva_unique_id': client.alleva_unique_id,
        'alleva_mrn': client.alleva_mrn,
        'alleva_source_id': client.alleva_source_id,
        'id_join_warnings': _json_list_values(client.id_join_warnings),
        'checklist_id': checklist['checklist_id'],
        'checklist_version': checklist['version'],
        'evidence_comparison': evaluation.evidence_comparison.__dict__,
        'rule_results': [result.__dict__ for result in evaluation.rule_results],
        'checklist_results': [result.__dict__ for result in checklist_results],
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
                'problem_count': item.problem_count,
                'diagnosis_count': item.diagnosis_count,
                'goal_count': item.goal_count,
                'objective_count': item.objective_count,
                'intervention_count': item.intervention_count,
                'has_guardian_signature': item.has_guardian_signature,
                'guardian_signature_date': item.guardian_signature_date,
                'alleva_is_active': item.alleva_is_active,
                'alleva_is_complete': item.alleva_is_complete,
                'alleva_is_initial_tp': item.alleva_is_initial_tp,
                'alleva_start_date': item.alleva_start_date,
                'alleva_end_date': item.alleva_end_date,
                'alleva_last_modified': item.alleva_last_modified,
                'detail_fetched': item.detail_fetched,
                'detail_fetched_at': item.detail_fetched_at,
                'content_source': item.content_source,
                'is_current': item.id == client.current_plan_record_id,
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


def treatment_plan_aggregate_payload(client: TreatmentPlanClient) -> dict[str, Any]:
    def plan_payload(item: TreatmentPlanRecord) -> dict[str, Any]:
        return {
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
            'problem_count': item.problem_count,
            'diagnosis_count': item.diagnosis_count,
            'goal_count': item.goal_count,
            'objective_count': item.objective_count,
            'intervention_count': item.intervention_count,
            'has_guardian_signature': item.has_guardian_signature,
            'guardian_signature_date': item.guardian_signature_date,
            'alleva_is_active': item.alleva_is_active,
            'alleva_is_complete': item.alleva_is_complete,
            'alleva_is_initial_tp': item.alleva_is_initial_tp,
            'alleva_start_date': item.alleva_start_date,
            'alleva_end_date': item.alleva_end_date,
            'alleva_last_modified': item.alleva_last_modified,
            'detail_fetched': item.detail_fetched,
            'detail_fetched_at': item.detail_fetched_at,
            'content_source': item.content_source,
            'is_current': item.id == client.current_plan_record_id,
        }

    plans = sorted(client.treatment_plans, key=lambda item: (_date(item.staff_signature_date) or _date(item.document_date) or date.min, item.id or 0), reverse=True)
    current = next((item for item in plans if item.id == client.current_plan_record_id), None)
    return {
        'patient_id': client.patient_id,
        'permitted_name': client.permitted_name,
        'is_active': client.is_active,
        'current_level_of_care': client.current_level_of_care,
        'counselor_name': client.counselor_name,
        'admission_date': client.admission_date,
        'alleva_ids': {
            'lead_id': client.alleva_lead_id,
            'client_id': client.alleva_client_id,
            'unique_id': client.alleva_unique_id,
            'mrn': client.alleva_mrn,
            'source_id': client.alleva_source_id,
        },
        'id_join_confidence': client.id_join_confidence,
        'id_join_warnings': _json_list_values(client.id_join_warnings),
        'data_quality_warnings': _json_list_values(client.data_quality_warnings),
        'discharge_conflict': client.discharge_conflict,
        'current_plan': plan_payload(current) if current is not None else None,
        'historical_plans': [plan_payload(item) for item in plans if item.plan_kind in {TreatmentPlanKind.initial, TreatmentPlanKind.master} and item.id != client.current_plan_record_id],
        'review_records': [plan_payload(item) for item in plans if item.plan_kind in {TreatmentPlanKind.review, TreatmentPlanKind.loc_update}],
    }
