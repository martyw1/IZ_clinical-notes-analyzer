from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.v2.domain.schemas import (
    JsonValue,
    ReviewStatus,
    TreatmentPlanAggregate,
)
from app.v2.services.rule_package import ChecklistStep, DeterministicRulePackage

EvaluationStatus = Literal[
    "Present", "Missing Data", "Needs Review", "Conflicting Evidence", "Unable to Evaluate",
    "Compliant", "Not Applicable", "Urgent", "Due Soon", "Current/Compliant", "Overdue",
]
UNKNOWN_VALUES: Final = frozenset({"", "unknown", "unavailable", "unvalidated_configurable", "none", "null"})


@dataclass(frozen=True, slots=True)
class CriterionEvaluation:
    criterion_id: str
    criterion_title: str
    status: EvaluationStatus
    normalized_path: str
    safe_evidence: str
    explanation: str


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    overall_status: ReviewStatus
    overall_explanation: str
    recurring_anchor: str
    calculated_due_date: str
    source_due_date: str
    loc_change_candidate_date: str
    mapped_level_of_care: str
    checklist_version: str
    rules_version: str
    evaluation_date: str
    facility_timezone: str
    criteria: tuple[CriterionEvaluation, ...]


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    aggregate: TreatmentPlanAggregate
    admission: date | None
    signature: date | None
    anchor: date | None
    calculated_due: date | None
    source_due: date | None
    source_due_invalid: bool
    mapped_loc: str
    interval_days: int | None
    timing_status: EvaluationStatus
    conflict: bool
    loc_changed: bool
    loc_candidate: date | None


@dataclass(frozen=True, slots=True)
class FacilityTimezoneError(Exception):
    timezone_name: str

    def __str__(self) -> str:
        return f"Facility timezone is unavailable: {self.timezone_name}"


def facility_local_date(instant: datetime, facility_timezone: str) -> date:
    aware = instant if instant.tzinfo is not None else instant.replace(tzinfo=timezone.utc)
    if facility_timezone == "local_machine":
        return aware.astimezone().date()
    try:
        zone = ZoneInfo(facility_timezone)
    except ZoneInfoNotFoundError as exc:
        raise FacilityTimezoneError(facility_timezone) from exc
    return aware.astimezone(zone).date()


def evaluate_plan_version(
    aggregate: TreatmentPlanAggregate,
    package: DeterministicRulePackage,
    evaluation_date: date,
    facility_timezone: str,
) -> EvaluationBundle:
    context = _context(aggregate, package, evaluation_date)
    overall, explanation = _overall(context)
    criteria = tuple(_criterion(step, context, overall) for step in package.checklist.steps)
    return EvaluationBundle(
        overall_status=overall,
        overall_explanation=explanation,
        recurring_anchor=_iso(context.anchor),
        calculated_due_date=_iso(context.calculated_due),
        source_due_date=_iso(context.source_due) if not context.source_due_invalid else "invalid",
        loc_change_candidate_date=_iso(context.loc_candidate),
        mapped_level_of_care=context.mapped_loc,
        checklist_version=package.checklist.version,
        rules_version=package.rules.config_version,
        evaluation_date=evaluation_date.isoformat(),
        facility_timezone=facility_timezone,
        criteria=criteria,
    )


def _context(aggregate: TreatmentPlanAggregate, package: DeterministicRulePackage, today: date) -> EvaluationContext:
    admission = _parse_date(aggregate.admission_date)
    signature_dates = tuple(
        parsed
        for item in aggregate.content_snapshot.signatures
        if (parsed := _parse_date(item.signature_datetime)) is not None
    )
    signature = max(signature_dates, default=None)
    anchor = _latest_signed_review_date(aggregate) or admission
    mapped_loc, interval = _map_loc(aggregate.current_level_of_care, package)
    calculated_due = anchor + timedelta(days=interval) if anchor is not None and interval is not None else None
    source_due = _parse_date(aggregate.source_due_date)
    source_due_invalid = _known(aggregate.source_due_date) and source_due is None
    conflict = calculated_due is not None and source_due is not None and calculated_due != source_due
    loc_changed = len({_text(row, "level_of_care", "loc_code").casefold() for row in aggregate.loc_history if _text(row, "level_of_care", "loc_code")}) > 1
    loc_effective_dates = tuple(_parse_date(_text(row, "effective_date")) for row in aggregate.loc_history)
    latest_loc = max((item for item in loc_effective_dates if item is not None), default=None)
    loc_candidate = latest_loc + timedelta(days=package.rules.loc_change_blocker.default_preset_calendar_days) if loc_changed and latest_loc else None
    timing = _timing_status(calculated_due, today)
    return EvaluationContext(aggregate, admission, signature, anchor, calculated_due, source_due, source_due_invalid,
                             mapped_loc, interval, timing, conflict, loc_changed, loc_candidate)


def _overall(context: EvaluationContext) -> tuple[ReviewStatus, str]:
    if context.admission is None or context.signature is None:
        return "Missing Data", "Required admission or signature evidence is missing; compliance was not inferred."
    if context.source_due_invalid:
        return "Unable to Evaluate", "The source Next Review Due value is invalid; compliance was not inferred."
    if not context.mapped_loc or context.calculated_due is None:
        return "Unable to Evaluate", "The level of care or recurrence anchor is not configured; compliance was not inferred."
    if context.conflict:
        return "Conflicting Evidence", "Source Next Review Due disagrees with the calculated signed-review recurrence."
    if context.signature != context.admission:
        return "Needs Review", "Initial treatment-plan signature evidence is not on admission Day 1."
    if context.loc_changed:
        return "Needs Review", "The seven-day LOC-change candidate is display-only and unvalidated; the recurring rule remains active."
    return context.timing_status, f"Calculated recurring due date is {context.calculated_due.isoformat()}."


def _criterion(step: ChecklistStep, context: EvaluationContext, overall: ReviewStatus) -> CriterionEvaluation:
    default = CriterionEvaluation(step.key, step.title, "Needs Review", "manual_review", "review required",
                                  "This canonical checklist step requires deterministic workflow or human confirmation.")
    decisions = {
        "confirm_admission_date": _presence(step, "admission_date", context.admission),
        "confirm_current_loc": _presence(step, "current_level_of_care", context.aggregate.current_level_of_care),
        "confirm_loc_rule_mapping": _presence(step, "mapped_level_of_care", context.mapped_loc),
        "confirm_staff_signature_status": _presence(step, "content_snapshot.signatures[*].signature_datetime", context.signature),
        "initial_plan_exists": _presence(step, "treatment_plans", context.aggregate.treatment_plans),
        "initial_plan_dated_correctly": _day_one(step, context),
        "initial_plan_required_signatures": _day_one(step, context),
        "master_plan_exists": _presence(step, "treatment_plans", context.aggregate.treatment_plans),
        "master_plan_within_30_days": _master(step, context),
        "master_plan_required_signatures": _presence(step, "content_snapshot.signatures[*].signature_datetime", context.signature),
        "latest_valid_review_identified": _anchor(step, context),
        "calculate_next_review_due_date": _due(step, context),
        "apply_php_timing_rule": _interval(step, context, "PHP"),
        "apply_iop_op_timing_rule": _interval(step, context, "NON_PHP"),
        "mark_current_inside_window": _timing_criterion(step, context, "Current/Compliant"),
        "mark_due_soon": _timing_criterion(step, context, "Due Soon", "Urgent"),
        "mark_overdue": _timing_criterion(step, context, "Overdue"),
        "check_conflicting_evidence": _conflict(step, context),
        "identify_loc_change": _loc_change(step, context),
        "loc_change_update_document": _loc_change(step, context),
        "loc_change_deadline_unresolved": _loc_change(step, context),
        "flag_missing_data_not_compliance": replace(default, status="Compliant" if overall not in {"Missing Data", "Unable to Evaluate"} else overall,
                                                     normalized_path="evaluation.overall_status", safe_evidence=overall,
                                                     explanation="Missing or invalid evidence is never converted to compliance."),
        "produce_final_checklist_result": replace(default, status=overall, normalized_path="evaluation.overall_status",
                                                  safe_evidence=overall, explanation="Final deterministic result preserves evidence uncertainty."),
    }
    return decisions.get(step.key, default)


def _presence(step: ChecklistStep, path: str, value: str | date | tuple[dict[str, JsonValue], ...]) -> CriterionEvaluation:
    present = bool(value) and (not isinstance(value, str) or _known(value))
    return CriterionEvaluation(step.key, step.title, "Present" if present else "Missing Data", path,
                               _safe(value) if present else "missing", "Required evidence is present." if present else "Required evidence is missing.")


def _day_one(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    if context.admission is None or context.signature is None:
        return CriterionEvaluation(step.key, step.title, "Missing Data", "admission_date + signatures[*].signature_datetime", "missing", "Day-1 evidence is incomplete.")
    compliant = context.signature == context.admission
    return CriterionEvaluation(step.key, step.title, "Compliant" if compliant else "Needs Review",
                               "content_snapshot.signatures[*].signature_datetime", context.signature.isoformat(),
                               "Initial plan is signed on admission Day 1." if compliant else "Initial plan is not signed on admission Day 1.")


def _master(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    if context.admission is None or context.signature is None:
        return CriterionEvaluation(step.key, step.title, "Missing Data", "admission_date + signatures[*].signature_datetime", "missing", "Master-plan timing evidence is incomplete.")
    deadline = context.admission + timedelta(days=30)
    compliant = context.signature <= deadline
    return CriterionEvaluation(step.key, step.title, "Compliant" if compliant else "Overdue", "admission_date + 30 calendar days",
                               deadline.isoformat(), "Signed master-plan evidence is within 30 days." if compliant else "Signed master-plan evidence exceeds 30 days.")


def _anchor(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    return _presence(step, "treatment_reviews[*].review_date/signature_date or admission_date", context.anchor or "")


def _due(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    status: EvaluationStatus = "Conflicting Evidence" if context.conflict else context.timing_status
    if context.calculated_due is None:
        status = "Unable to Evaluate"
    return CriterionEvaluation(step.key, step.title, status, "signed_review_anchor + configured_interval_days",
                               _iso(context.calculated_due) or "unavailable", "Calculated due date is compared with source Next Review Due.")


def _interval(step: ChecklistStep, context: EvaluationContext, category: str) -> CriterionEvaluation:
    applies = context.mapped_loc == "PHP" if category == "PHP" else bool(context.mapped_loc and context.mapped_loc != "PHP")
    return CriterionEvaluation(step.key, step.title, context.timing_status if applies else "Not Applicable", "levels_of_care.*.treatment_plan_update_interval_days",
                               str(context.interval_days or "unavailable"), "Configured interval applied." if applies else "Rule is not applicable to this LOC.")


def _timing_criterion(step: ChecklistStep, context: EvaluationContext, *statuses: EvaluationStatus) -> CriterionEvaluation:
    applies = context.timing_status in statuses
    return CriterionEvaluation(step.key, step.title, context.timing_status if applies else "Not Applicable", "evaluation_date -> calculated_due_date",
                               _iso(context.calculated_due) or "unavailable", "Exact facility-local date boundary evaluated.")


def _conflict(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    return CriterionEvaluation(step.key, step.title, "Conflicting Evidence" if context.conflict else "Compliant",
                               "source_due_date vs calculated_due_date", f"source={_iso(context.source_due)}; calculated={_iso(context.calculated_due)}",
                               "Conflicting due-date evidence found." if context.conflict else "No due-date conflict found.")


def _loc_change(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    status: EvaluationStatus = "Needs Review" if context.loc_changed else "Not Applicable"
    return CriterionEvaluation(step.key, step.title, status, "loc_history[*].effective_date",
                               _iso(context.loc_candidate) or "no candidate", "The seven-day candidate is display-only and cannot activate compliance.")


def _map_loc(raw: str, package: DeterministicRulePackage) -> tuple[str, int | None]:
    normalized = raw.strip().casefold()
    for name, rule in package.rules.levels_of_care.items():
        if normalized in {alias.strip().casefold() for alias in rule.aliases} | {name.casefold()}:
            return name, rule.treatment_plan_update_interval_days
    return "", None


def _latest_signed_review_date(aggregate: TreatmentPlanAggregate) -> date | None:
    candidates = []
    for review in aggregate.treatment_reviews:
        review_date = _parse_date(_text(review, "review_date", "reviewDate", "updated_date", "date"))
        signature_date = _parse_date(_text(review, "signature_date", "signatureDate", "signed_at"))
        signed = bool(signature_date) or _text(review, "signed", "is_signed").casefold() in {"true", "yes", "1"}
        if signed and review_date is not None:
            candidates.append(review_date)
    return max(candidates, default=None)


def _timing_status(due: date | None, today: date) -> EvaluationStatus:
    if due is None:
        return "Unable to Evaluate"
    days = (due - today).days
    if days < 0:
        return "Overdue"
    if days <= 1:
        return "Urgent"
    if days <= 7:
        return "Due Soon"
    return "Current/Compliant"


def _parse_date(raw: str) -> date | None:
    if not _known(raw):
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _text(record: dict[str, JsonValue], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)):
            return str(value)
    return ""


def _known(raw: str) -> bool:
    return raw.strip().casefold() not in UNKNOWN_VALUES


def _iso(value: date | None) -> str:
    return value.isoformat() if value is not None else ""


def _safe(value: str | date | tuple[dict[str, JsonValue], ...]) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return f"{len(value)} record(s)"
    return value.strip()[:160]
