from __future__ import annotations

import hashlib
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
from app.services.treatment_plan_content_safety import (
    content_item_has_value,
    content_items_json,
    normalized_content_items,
    safe_content_status,
    safe_content_text,
    safe_content_warning,
)
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
    patient_name_display_enabled: bool
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
    evaluated_values: list[dict[str, Any]]
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
    fallback = _latest_plan(plans, TreatmentPlanKind.master) or _latest_plan(plans, TreatmentPlanKind.initial) or _latest_review_plan(plans)
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


def _plan_content_items(plan: TreatmentPlanRecord | None) -> list[dict[str, Any]]:
    return normalized_content_items(plan.content_items_json) if plan else []


def _plan_has_content_value(plan: TreatmentPlanRecord | None, kind: str) -> bool:
    return any(item.get('kind') == kind and content_item_has_value(item) for item in _plan_content_items(plan))


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
    current_plan_items = _plan_content_items(current_plan)
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
    if current_plan and (current_plan.detail_fetched or current_plan_is_alleva or current_plan_items):
        checks.extend(
            [
                ('Treatment plan clinical content values captured', bool(current_plan_items)),
                ('Treatment plan has problem values', _plan_has_content_value(current_plan, 'problem')),
                ('Treatment plan has diagnosis values', _plan_has_content_value(current_plan, 'diagnosis')),
                ('Treatment plan has goal values', _plan_has_content_value(current_plan, 'goal')),
                ('Treatment plan has objective values', _plan_has_content_value(current_plan, 'objective')),
                ('Treatment plan has intervention values', _plan_has_content_value(current_plan, 'intervention')),
            ]
        )
        if current_plan.detail_fetched or current_plan_is_alleva:
            checks.append(('Treatment plan marked complete in Alleva', current_plan.alleva_is_complete))
    elif current_plan:
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
        patient_name_display_enabled=app_settings.alleva_treatment_plan_patient_name_import_enabled,
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


def _checklist_value_status(value: Any) -> str:
    if value is None:
        return 'missing'
    if isinstance(value, str) and not value.strip():
        return 'missing'
    if isinstance(value, (list, tuple, set, dict)) and not value:
        return 'missing'
    return 'present'


def _checklist_value(
    field: str,
    label: str,
    value: Any,
    *,
    source: str = '',
    status: str | None = None,
) -> dict[str, Any]:
    return {
        'field': field,
        'label': label,
        'value': value,
        'status': status or _checklist_value_status(value),
        'source': source,
    }


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


def _safe_content_scalar(value: Any, *, max_chars: int = 160) -> str:
    return safe_content_text(value, max_chars=max_chars)


def _normalized_content_items(value: Any) -> list[dict[str, Any]]:
    return normalized_content_items(value)


def _content_items_json(value: Any) -> str:
    return content_items_json(value)


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
    evaluated_values: list[dict[str, Any]] | None = None,
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
        evaluated_values=evaluated_values or [],
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

    def joined(values: list[str]) -> str:
        return ', '.join(dict.fromkeys([value.strip() for value in values if value and value.strip()]))

    def date_values(field_name: str) -> str:
        return joined([getattr(plan, field_name) for plan in plans])

    def plan_kind_values() -> str:
        return joined([plan.plan_kind.value for plan in plans])

    def document_id_values() -> str:
        return joined([plan.source_document_id for plan in plans])

    def source_section_values() -> str:
        return joined([plan.source_section for plan in plans])

    def loc_history_summary() -> str:
        parts = []
        for item in loc_history:
            state = f'effective {item.effective_date or "missing effective date"}'
            if item.discharge_date.strip():
                state += f', discharged {item.discharge_date}'
            parts.append(f'{item.level_of_care or "Missing LOC"} ({state})')
        return '; '.join(parts)

    def completion_summary() -> str:
        if not plans:
            return ''
        invalid = [plan for plan in plans if not plan.is_valid or plan.conflict_note.strip()]
        if invalid:
            return f'{len(invalid)} of {len(plans)} treatment-plan record(s) invalid, incomplete, or conflicted'
        return f'{len(plans)} treatment-plan record(s) valid with no conflict notes'

    def conflict_summary() -> str:
        conflicts = joined([plan.conflict_note for plan in plans])
        return conflicts or (conflict_rule.evidence_summary if conflict_rule else '')

    def initial_or_master_dates(plan: TreatmentPlanRecord | None, field_name: str) -> str:
        return getattr(plan, field_name) if plan is not None else ''

    def override_field_values(field_name: str) -> str:
        if field_name == 'reason':
            return f'{len(client.overrides)} override reason(s) recorded' if client.overrides else ''
        if field_name == 'created_by':
            return joined([str(override.created_by_id) for override in client.overrides])
        return joined([getattr(override, field_name) for override in client.overrides])

    def audit_values(field_name: str) -> str:
        if field_name == 'audit_event_id':
            return str(len(audit_history)) if audit_history else ''
        if field_name == 'audit_action':
            return joined([getattr(log, 'action', '') for log in audit_history[:5]])
        if field_name == 'timestamp':
            return joined([str(getattr(log, 'timestamp_utc', '') or getattr(log, 'timestamp', '')) for log in audit_history[:3]])
        return ''

    loc_change_window_status = 'present' if evaluation.evidence_comparison.loc_change_rule_validated else 'unknown'
    field_values = {
        'patient_id': _checklist_value('patient_id', 'Patient ID', client.patient_id, source=client.source_evidence),
        'source_evidence': _checklist_value('source_evidence', 'Source evidence', source_evidence),
        'source_note_set_id': _checklist_value('source_note_set_id', 'Uploaded binder ID', client.source_note_set_id, source=client.source_evidence),
        'last_imported_at': _checklist_value('last_imported_at', 'Last imported at', client.last_imported_at.isoformat() if client.last_imported_at else '', source=client.source_evidence),
        'active_status': _checklist_value('active_status', 'Active status', 'Active' if client.is_active else 'Inactive', source=client.source_evidence, status='present' if client.is_active else 'not_applicable'),
        'admission_date': _checklist_value('admission_date', 'Admission date', client.admission_date, source=client.source_evidence),
        'current_level_of_care': _checklist_value('current_level_of_care', 'Current LOC', client.current_level_of_care, source=_combined_evidence(client.source_evidence, active_loc.source_evidence if active_loc else '')),
        'mapped_level_of_care': _checklist_value('mapped_level_of_care', 'Mapped LOC rule category', mapped_loc, source='config/rules'),
        'rules_version': _checklist_value('rules_version', 'Rules version', 'configured deterministic rules', source='config/rules'),
        'loc_history': _checklist_value('loc_history', 'LOC history', loc_history_summary(), source=_combined_evidence(*[item.source_evidence for item in loc_history])),
        'effective_date': _checklist_value('effective_date', 'LOC effective dates', joined([item.effective_date for item in loc_history]), source=_combined_evidence(*[item.source_evidence for item in loc_history])),
        'discharge_date': _checklist_value('discharge_date', 'LOC discharge dates', joined([item.discharge_date for item in loc_history]) or 'No LOC discharge date recorded', source=_combined_evidence(*[item.source_evidence for item in loc_history]), status='present' if joined([item.discharge_date for item in loc_history]) else 'not_applicable'),
        'document_type': _checklist_value('document_type', 'Treatment-plan document types', plan_kind_values(), source=plans_source_evidence),
        'source_document_id': _checklist_value('source_document_id', 'Source document IDs', document_id_values(), source=plans_source_evidence),
        'source_section': _checklist_value('source_section', 'Source sections', source_section_values(), source=plans_source_evidence),
        'document_date': _checklist_value('document_date', 'Document dates', date_values('document_date'), source=plans_source_evidence),
        'completion_status': _checklist_value('completion_status', 'Completion/validity status', completion_summary(), source=plans_source_evidence),
        'staff_signature_date': _checklist_value('staff_signature_date', 'Staff signature dates', date_values('staff_signature_date'), source=plans_source_evidence),
        'client_signature_date': _checklist_value('client_signature_date', 'Client signature dates', date_values('client_signature_date'), source=plans_source_evidence),
        'conflict_note': _checklist_value('conflict_note', 'Conflict note', conflict_summary() or 'No conflict note recorded', source=_combined_evidence(plans_source_evidence, evaluation.evidence_comparison.conflict_explanation), status='conflicting' if conflict_rule or conflict_summary() else 'not_applicable'),
        'rule_used': _checklist_value('rule_used', 'Rule used', evaluation.rule_used, source=evaluation.evidence_summary),
        'latest_valid_review_date': _checklist_value('latest_valid_review_date', 'Latest valid review/update date', evaluation.last_valid_review_date, source=_plan_evidence(latest_review)),
        'date_clock_anchor_date': _checklist_value('date_clock_anchor_date', 'Date-clock anchor date', evaluation.evidence_comparison.date_clock_anchor_date, source=evaluation.evidence_comparison.date_clock_anchor_source),
        'document_next_due_date': _checklist_value('document_next_due_date', 'Source-document Next Review Due', evaluation.evidence_comparison.document_next_due_date, source=plans_source_evidence),
        'signature_anchor_due_date': _checklist_value('signature_anchor_due_date', 'Signature-anchor due date', evaluation.evidence_comparison.signature_anchor_due_date, source=evaluation.evidence_comparison.date_clock_anchor_source),
        'date_clock_due_date': _checklist_value('date_clock_due_date', 'Calculated date-clock due date', evaluation.evidence_comparison.date_clock_due_date, source=evaluation.evidence_comparison.date_clock_anchor_source),
        'loc_anchor_due_date': _checklist_value('loc_anchor_due_date', 'LOC effective-anchor due date', evaluation.evidence_comparison.loc_anchor_due_date, source=active_loc.source_evidence if active_loc else ''),
        'loc_change_due_date': _checklist_value('loc_change_due_date', 'LOC-change due date', evaluation.evidence_comparison.loc_change_due_date, source=active_loc.source_evidence if active_loc else ''),
        'interval_days': _checklist_value('interval_days', 'LOC cadence interval', interval_days, source='config/rules'),
        'next_due_date': _checklist_value('next_due_date', 'Next due date', evaluation.next_due_date, source=evaluation.evidence_summary),
        'overall_status': _checklist_value('overall_status', 'Overall status', evaluation.status, source=evaluation.evidence_summary),
        'days_until_due': _checklist_value('days_until_due', 'Days until due', evaluation.days_until_due, source=evaluation.evidence_summary),
        'previous_level_of_care': _checklist_value('previous_level_of_care', 'Previous LOC', loc_history[-2].level_of_care if loc_change_present else '', source=_combined_evidence(*[item.source_evidence for item in loc_history]), status='present' if loc_change_present else 'not_applicable'),
        'loc_effective_date': _checklist_value('loc_effective_date', 'Current LOC effective date', evaluation.evidence_comparison.loc_effective_date or (active_loc.effective_date if active_loc else ''), source=active_loc.source_evidence if active_loc else ''),
        'loc_change_document': _checklist_value('loc_change_document', 'LOC-change document', _plan_evidence(loc_update), source=_plan_evidence(loc_update), status='present' if loc_update else ('missing' if loc_change_present else 'not_applicable')),
        'loc_change_window_days': _checklist_value('loc_change_window_days', 'LOC-change window days', evaluation.evidence_comparison.loc_change_window_days, source='App settings', status=loc_change_window_status),
        'loc_change_rule_validated': _checklist_value('loc_change_rule_validated', 'LOC-change rule validated', evaluation.evidence_comparison.loc_change_rule_validated, source='App settings', status=loc_change_window_status),
        'clock_start_source': _checklist_value('clock_start_source', 'Clock start source', evaluation.evidence_comparison.date_clock_anchor_source, source=evaluation.evidence_comparison.source_evidence),
        'missing_evidence_fields': _checklist_value('missing_evidence_fields', 'Missing evidence fields', ', '.join(evaluation.missing_evidence_fields), source=evaluation.evidence_summary, status='missing' if evaluation.missing_evidence_fields else 'not_applicable'),
        'reviewer': _checklist_value('reviewer', 'Reviewer path', 'Admin/manager review available; counselor view is read-only for overrides', source='RBAC workflow'),
        'review_action': _checklist_value('review_action', 'Review action', 'Manual confirmation available when deterministic result is blocked', source='RBAC workflow'),
        'comment': _checklist_value('comment', 'Manager comment', 'Stored per checklist item when entered', source='criterion review state', status='unknown'),
        'override_reason': _checklist_value('override_reason', 'Override reason', override_field_values('reason'), source='manual overrides'),
        'affected_rule': _checklist_value('affected_rule', 'Affected override rules', override_field_values('affected_rule'), source='manual overrides'),
        'created_by': _checklist_value('created_by', 'Override creator IDs', override_field_values('created_by'), source='manual overrides'),
        'severity_counts': _checklist_value('severity_counts', 'Checklist severity/status counts', 'Computed from the 42 checklist rows in this response', source='checklist evaluation', status='unknown'),
        'evidence_summary': _checklist_value('evidence_summary', 'Evidence summary', evaluation.evidence_summary, source=source_evidence),
        'worklist_status': _checklist_value('worklist_status', 'Worklist status', evaluation.status, source=evaluation.evidence_summary),
        'last_status_change_at': _checklist_value('last_status_change_at', 'Last status/update timestamp', client.updated_at.isoformat() if client.updated_at else '', source='treatment_plan_clients.updated_at'),
        'manager_review_state': _checklist_value('manager_review_state', 'Manager review state', 'Available' if evaluation.status != TimelinessStatus.compliant.value else 'Optional', source='workflow routing'),
        'reviewer_role': _checklist_value('reviewer_role', 'Reviewer role', 'admin/manager', source='RBAC workflow'),
        'correction_comment': _checklist_value('correction_comment', 'Correction comment', 'Required if manager returns chart for correction', source='workflow routing', status='unknown'),
        'returned_by': _checklist_value('returned_by', 'Returned by', '', source='workflow routing', status='not_applicable'),
        'returned_at': _checklist_value('returned_at', 'Returned at', '', source='workflow routing', status='not_applicable'),
        'approval_state': _checklist_value('approval_state', 'Approval state', 'Ready only when deterministic result is compliant/approved or issues are accepted', source='workflow routing'),
        'accepted_issue_count': _checklist_value('accepted_issue_count', 'Accepted issue count', len(client.overrides), source='manual overrides'),
        'approved_by': _checklist_value('approved_by', 'Approved by', '', source='workflow routing', status='not_applicable'),
        'audit_event_id': _checklist_value('audit_event_id', 'Audit event count', audit_values('audit_event_id'), source='audit history'),
        'audit_action': _checklist_value('audit_action', 'Recent audit actions', audit_values('audit_action'), source='audit history'),
        'timestamp': _checklist_value('timestamp', 'Recent audit timestamps', audit_values('timestamp'), source='audit history'),
        'last_refresh_at': _checklist_value('last_refresh_at', 'Last API refresh/import timestamp', client.last_imported_at.isoformat() if client.last_imported_at else '', source=client.source_evidence),
        'next_refresh_at': _checklist_value('next_refresh_at', 'Next refresh timestamp', '', source='periodic API monitoring', status='unknown'),
        'changed_item_count': _checklist_value('changed_item_count', 'Changed item count', 'Not calculated in selected-client detail', source='periodic API monitoring', status='unknown'),
        'error_count': _checklist_value('error_count', 'API error count', 'Not calculated in selected-client detail', source='periodic API monitoring', status='unknown'),
        'validation_data_kind': _checklist_value('validation_data_kind', 'Validation data kind', 'synthetic/non-production' if 'synthetic' in source_evidence.lower() or client.patient_id.upper().startswith(('PAT-', 'SYNTH-')) else 'requires reviewer confirmation', source=source_evidence),
        'artifact_path': _checklist_value('artifact_path', 'Artifact path/source', source_evidence, source=source_evidence),
        'redaction_status': _checklist_value('redaction_status', 'Patient-name redaction status', 'Treatment Plans browser display and exports use Patient ID only', source='patient-name privacy setting'),
    }

    def evaluated_values_for(fields: list[str], evidence: str) -> list[dict[str, Any]]:
        values = []
        for field in fields:
            field_value = dict(field_values.get(field) or _checklist_value(field, field.replace('_', ' ').title(), '', status='unknown'))
            if not field_value.get('source'):
                field_value['source'] = evidence
            values.append(field_value)
        return values

    def step(key: str, status: str, finding: str, evidence: str = '', fields: list[str] | None = None) -> TimelinessChecklistResult:
        result_fields = fields or []
        result_evidence = evidence or source_evidence
        return _checklist_result(
            steps_by_key[key],
            status=status,
            finding_message=finding,
            source_evidence=result_evidence,
            evidence_fields_used=result_fields,
            evaluated_values=evaluated_values_for(result_fields, result_evidence),
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
            ['date_clock_anchor_date', 'interval_days', 'date_clock_due_date', 'document_next_due_date', 'signature_anchor_due_date', 'loc_anchor_due_date'],
        ),
        step(
            'apply_php_timing_rule',
            _status_for_rule(review_rule) if mapped_loc == 'php' else 'Not Applicable',
            review_rule.evidence_summary if mapped_loc == 'php' and review_rule else 'PHP timing does not apply to the selected current LOC.' if mapped_loc != 'php' else 'PHP timing could not be evaluated.',
            source_evidence,
            ['current_level_of_care', 'mapped_level_of_care', 'interval_days', 'date_clock_due_date'],
        ),
        step(
            'apply_iop_op_timing_rule',
            _status_for_rule(review_rule) if mapped_loc and mapped_loc != 'php' else 'Not Applicable',
            review_rule.evidence_summary if mapped_loc and mapped_loc != 'php' and review_rule else 'IOP/OP timing does not apply to the selected current LOC.' if mapped_loc == 'php' else 'IOP/OP timing could not be evaluated.',
            source_evidence,
            ['current_level_of_care', 'mapped_level_of_care', 'interval_days', 'date_clock_due_date'],
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

    client.permitted_name = display_name_for_patient_name_status(NAME_NOT_FOUND_STATUS, patient_id=patient_id)
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
            problem_count=max(0, int(item.problem_count or 0)),
            diagnosis_count=max(0, int(item.diagnosis_count or 0)),
            goal_count=max(0, int(item.goal_count or 0)),
            objective_count=max(0, int(item.objective_count or 0)),
            intervention_count=max(0, int(item.intervention_count or 0)),
            content_items_json=_content_items_json(item.content_items),
            content_capture_status=safe_content_status(item.content_capture_status),
            content_capture_warnings=safe_content_warning(item.content_capture_warnings),
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
    label = document.document_label or 'Treatment plan document'
    parts = [f'{label} from note set {note_set_id}']
    if document.original_filename.lower().endswith('.pdf'):
        parts.append('manual upload page 1')
    if document.source_document_id.strip():
        parts.append(f'Alleva document ID {document.source_document_id.strip()}')
    return '; '.join(parts)


def sync_from_note_set(db: Session, note_set: PatientNoteSet) -> TreatmentPlanClient:
    client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == note_set.patient_id)).scalar_one_or_none()
    if client is None:
        client = TreatmentPlanClient(patient_id=note_set.patient_id)
        db.add(client)
        db.flush()

    client.permitted_name = display_name_for_patient_name_status(NAME_NOT_FOUND_STATUS, patient_id=note_set.patient_id)
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


def _client_display_label(client: TreatmentPlanClient, *, patient_name_display_enabled: bool) -> str:
    if patient_name_display_enabled and client.permitted_name.strip():
        return client.permitted_name.strip()
    return client.patient_id


def summary_payload(evaluation: TimelinessEvaluation) -> dict[str, Any]:
    client = evaluation.client
    return {
        'id': client.id,
        'patient_id': client.patient_id,
        'permitted_name': _client_display_label(client, patient_name_display_enabled=evaluation.patient_name_display_enabled),
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
        'source_confidence': client.id_join_confidence or 'unknown',
        'source_endpoint_count': len({item['endpoint'] for item in _aggregate_raw_sources(client, list(client.treatment_plans))}),
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
                'content_items': _normalized_content_items(item.content_items_json),
                'content_capture_status': safe_content_status(item.content_capture_status),
                'content_capture_warnings': safe_content_warning(item.content_capture_warnings),
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


def treatment_plan_aggregate_payload(
    client: TreatmentPlanClient,
    *,
    patient_name_display_enabled: bool = False,
    evaluation: TimelinessEvaluation | None = None,
) -> dict[str, Any]:
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
            'source_record_id': item.source_document_id,
            'source_endpoint': '/treatment-reviews' if item.plan_kind in {TreatmentPlanKind.review, TreatmentPlanKind.loc_update} else '/treatment-plans',
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
            'content_items': _normalized_content_items(item.content_items_json),
            'content_capture_status': safe_content_status(item.content_capture_status),
            'content_capture_warnings': safe_content_warning(item.content_capture_warnings),
            'is_current': item.id == client.current_plan_record_id,
        }

    plans = sorted(client.treatment_plans, key=lambda item: (_date(item.staff_signature_date) or _date(item.document_date) or date.min, item.id or 0), reverse=True)
    current = next((item for item in plans if item.id == client.current_plan_record_id), None)
    legacy_current_plan = plan_payload(current) if current is not None else None
    legacy_historical_plans = [plan_payload(item) for item in plans if item.id != client.current_plan_record_id]
    legacy_review_records = [plan_payload(item) for item in plans if item.plan_kind in {TreatmentPlanKind.review, TreatmentPlanKind.loc_update}]
    structured_data_quality = _aggregate_data_quality(client, current=current, evaluation=evaluation)
    raw_sources = _aggregate_raw_sources(client, plans)
    payload = {
        'schema_version': 'patient-treatment-plan-aggregate-v1',
        'patient_key': _aggregate_patient_key(client),
        'patient': {
            'display_name': _client_display_label(client, patient_name_display_enabled=patient_name_display_enabled),
            'identifiers': {
                'patient_id': client.patient_id,
                'lead_id': client.alleva_lead_id,
                'client_id': client.alleva_client_id,
                'unique_id': client.alleva_unique_id,
                'mrn': client.alleva_mrn,
                'source_id': client.alleva_source_id,
            },
            'is_active': client.is_active,
            'source_system': 'Alleva REST API' if (client.source_evidence or '').startswith('Alleva REST') else 'Local Timeliness Tracker',
        },
        'episode': {
            'admission_date': client.admission_date,
            'level_of_care': client.current_level_of_care,
            'primary_clinician': client.counselor_name,
            'loc_history': [
                {
                    'level_of_care': item.level_of_care,
                    'facility': item.facility,
                    'effective_date': item.effective_date,
                    'discharge_date': item.discharge_date,
                    'source_evidence': item.source_evidence,
                }
                for item in sorted(client.level_of_care_history, key=lambda item: (_date(item.effective_date) or date.min, item.id or 0))
            ],
            'discharge_conflict': client.discharge_conflict,
        },
        'current_treatment_plan': legacy_current_plan,
        'treatment_plans': [plan_payload(item) for item in plans if item.plan_kind in {TreatmentPlanKind.initial, TreatmentPlanKind.master}],
        'treatment_reviews': legacy_review_records,
        'diagnoses': _aggregate_diagnoses(current),
        'advanced_form_captures': [],
        'computed_status': _aggregate_computed_status(evaluation, current=current),
        'data_quality': structured_data_quality,
        'raw_sources': raw_sources,
        'source_confidence': client.id_join_confidence or 'unknown',
        'source_endpoint_count': len({item['endpoint'] for item in raw_sources}),
        'patient_id': client.patient_id,
        'permitted_name': _client_display_label(client, patient_name_display_enabled=patient_name_display_enabled),
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
        'current_plan': legacy_current_plan,
        'historical_plans': legacy_historical_plans,
        'review_records': legacy_review_records,
    }
    return payload


def _aggregate_patient_key(client: TreatmentPlanClient) -> str:
    for prefix, value in (
        ('lead', client.alleva_lead_id),
        ('client', client.alleva_client_id),
        ('unique', client.alleva_unique_id),
        ('mrn', client.alleva_mrn),
        ('source', client.alleva_source_id),
        ('patient', client.patient_id),
    ):
        if value:
            return f'{prefix}:{value}'
    return f'client_row:{client.id}'


def _aggregate_data_quality(
    client: TreatmentPlanClient,
    *,
    current: TreatmentPlanRecord | None,
    evaluation: TimelinessEvaluation | None,
) -> list[dict[str, Any]]:
    issues = [
        {
            'code': str(value),
            'severity': 'medium',
            'message': str(value).replace('_', ' '),
            'source': 'timeliness_client',
        }
        for value in _json_list_values(client.data_quality_warnings)
    ]
    for value in _json_list_values(client.id_join_warnings):
        issues.append({'code': str(value), 'severity': 'medium', 'message': str(value).replace('_', ' '), 'source': 'identity_match'})
    if client.discharge_conflict:
        issues.append(
            {
                'code': 'active_patient_discharge_conflict',
                'severity': 'medium',
                'message': 'Active patient record includes discharge evidence and needs review.',
                'source': 'client',
            }
        )
    if current is None:
        issues.append(
            {
                'code': 'no_current_active_treatment_plan',
                'severity': 'high',
                'message': 'No current active treatment plan is selected for this patient.',
                'source': 'treatment_plans',
            }
        )
    elif current.conflict_note:
        issues.append({'code': 'current_plan_conflict', 'severity': 'high', 'message': current.conflict_note, 'source': current.source_section})
    if evaluation and evaluation.missing_evidence_fields:
        issues.append(
            {
                'code': 'missing_required_timeliness_evidence',
                'severity': 'high',
                'message': 'Required timeliness evidence is missing or conflicting.',
                'source': 'timeliness_rules',
                'fields': evaluation.missing_evidence_fields,
            }
        )
    return issues


def _aggregate_raw_sources(client: TreatmentPlanClient, plans: list[TreatmentPlanRecord]) -> list[dict[str, Any]]:
    sources = [_raw_source_ref('/clients', client.alleva_source_id or client.patient_id, client.source_evidence)]
    for item in plans:
        endpoint = '/treatment-reviews' if item.plan_kind in {TreatmentPlanKind.review, TreatmentPlanKind.loc_update} else '/treatment-plans'
        sources.append(_raw_source_ref(endpoint, item.source_document_id or str(item.id), item.source_evidence))
    seen: set[tuple[str, str]] = set()
    deduped = []
    for source in sources:
        key = (source['endpoint'], source['payload_hash'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _raw_source_ref(endpoint: str, source_record_id: str, evidence: str) -> dict[str, Any]:
    material = json.dumps({'endpoint': endpoint, 'source_record_id': source_record_id, 'evidence': evidence}, sort_keys=True)
    return {
        'endpoint': endpoint,
        'method': 'GET',
        'source_record_id': source_record_id,
        'payload_hash': hashlib.sha256(material.encode('utf-8')).hexdigest(),
        'source_record_count': 1,
        'source_version': 'unknown',
    }


def _aggregate_diagnoses(current: TreatmentPlanRecord | None) -> list[dict[str, Any]]:
    if current is None or current.diagnosis_count <= 0:
        return []
    return [
        {
            'source': 'current_treatment_plan',
            'source_record_id': current.source_document_id,
            'diagnosis_count': current.diagnosis_count,
            'present_in_current_plan': True,
        }
    ]


def _aggregate_computed_status(evaluation: TimelinessEvaluation | None, *, current: TreatmentPlanRecord | None) -> dict[str, Any]:
    if evaluation is None:
        return {
            'status': 'Unable to Evaluate',
            'next_review_due_selected': None,
            'next_review_due_api': current.displayed_next_due_date if current is not None else None,
            'next_review_due_computed': None,
            'missing_items': ['timeliness_evaluation'],
        }
    return {
        'status': evaluation.status,
        'as_of_date': evaluation.current_date,
        'next_review_due_selected': evaluation.next_due_date,
        'next_review_due_api': evaluation.evidence_comparison.document_next_due_date,
        'next_review_due_computed': evaluation.evidence_comparison.date_clock_due_date,
        'api_computed_due_date_disagreement': bool(evaluation.evidence_comparison.document_next_due_date and evaluation.evidence_comparison.conflict_explanation),
        'anchor_date': evaluation.evidence_comparison.date_clock_anchor_date,
        'interval_days': evaluation.evidence_comparison.interval_days,
        'completion_api': current.alleva_is_complete if current is not None else None,
        'completion_computed': current.is_valid if current is not None else None,
        'rule_used': evaluation.rule_used,
        'evidence_completeness_percent': evaluation.evidence_completeness_percent,
        'missing_items': evaluation.missing_evidence_fields,
    }
