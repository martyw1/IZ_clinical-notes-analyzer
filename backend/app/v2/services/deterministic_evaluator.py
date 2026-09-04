from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.v2.domain.schemas import JsonValue, ReviewStatus, TreatmentPlanAggregate
from app.v2.services.criterion_source_support import ObservedSource, criterion_source_support
from app.v2.services.evaluation_evidence import EvaluationEvidence, collect_evidence, known
from app.v2.services.rule_package import ChecklistStep, DeterministicRulePackage

EvaluationStatus = Literal[
    "Present", "Missing Data", "Needs Review", "Conflicting Evidence", "Unable to Evaluate",
    "Compliant", "Not Applicable", "Urgent", "Due Soon", "Current/Compliant", "Overdue",
]


@dataclass(frozen=True, slots=True)
class CriterionEvaluation:
    criterion_id: str
    criterion_title: str
    status: EvaluationStatus
    normalized_path: str
    safe_evidence: str
    explanation: str
    observed_sources: tuple[ObservedSource, ...] = ()


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
    evidence = collect_evidence(aggregate, package, evaluation_date)
    context = EvaluationContext(evidence, _timing_status(evidence.calculated_due, evaluation_date))
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


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    evidence: EvaluationEvidence
    timing_status: EvaluationStatus

    def __getattr__(self, name: str):
        return getattr(self.evidence, name)


def _overall(context: EvaluationContext) -> tuple[ReviewStatus, str]:
    if context.source_uncertainty is not None:
        return context.source_uncertainty, context.source_uncertainty_reason
    if context.malformed_signature or context.loc_conflict:
        return "Conflicting Evidence", "Signature or level-of-care evidence is malformed or internally inconsistent."
    if context.future_review:
        return "Needs Review", "A signed review is future-dated relative to the facility evaluation date."
    if (context.admission is None or context.initial_signature is None or context.master_signature is None
            or context.source_due_missing or context.plans_missing):
        return "Missing Data", "Required typed plan, signature, admission, or due-date evidence is missing."
    if context.source_due_invalid:
        return "Unable to Evaluate", "The source Next Review Due value is invalid; compliance was not inferred."
    if not context.mapped_loc or context.calculated_due is None:
        return "Unable to Evaluate", "The level of care or recurrence anchor is not configured; compliance was not inferred."
    if context.due_conflict:
        return "Conflicting Evidence", "Source Next Review Due disagrees with the calculated signed-review recurrence."
    if context.initial_signature != context.admission:
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
        "confirm_staff_signature_status": _presence(step, context.initial_signature_path, context.initial_signature),
        "initial_plan_exists": _presence(step, "treatment_plans", context.aggregate.treatment_plans),
        "initial_plan_dated_correctly": _day_one(step, context),
        "initial_plan_required_signatures": _day_one(step, context),
        "master_plan_exists": _presence(step, "treatment_plans", context.aggregate.treatment_plans),
        "master_plan_within_30_days": _master(step, context),
        "master_plan_required_signatures": _presence(step, context.master_signature_path, context.master_signature),
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
    return replace(decisions.get(step.key, default), observed_sources=criterion_source_support(step.key, context.aggregate))


def _presence(step: ChecklistStep, path: str, value: str | date | tuple[dict[str, JsonValue], ...]) -> CriterionEvaluation:
    present = bool(value) and (not isinstance(value, str) or known(value))
    return CriterionEvaluation(step.key, step.title, "Present" if present else "Missing Data", path,
                               _safe(value) if present else "missing", "Required evidence is present." if present else "Required evidence is missing.")


def _day_one(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    if context.admission is None or context.initial_signature is None:
        return CriterionEvaluation(step.key, step.title, "Missing Data", "admission_date + signatures[*].signature_datetime", "missing", "Day-1 evidence is incomplete.")
    compliant = context.initial_signature == context.admission
    return CriterionEvaluation(step.key, step.title, "Compliant" if compliant else "Needs Review",
                               context.initial_signature_path, context.initial_signature.isoformat(),
                               "Initial plan is signed on admission Day 1." if compliant else "Initial plan is not signed on admission Day 1.")


def _master(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    if context.admission is None or context.master_signature is None:
        return CriterionEvaluation(step.key, step.title, "Missing Data", "admission_date + signatures[*].signature_datetime", "missing", "Master-plan timing evidence is incomplete.")
    deadline = context.admission + timedelta(days=30)
    compliant = context.master_signature <= deadline
    return CriterionEvaluation(step.key, step.title, "Compliant" if compliant else "Overdue", context.master_signature_path,
                               context.master_signature.isoformat(), "Signed master-plan evidence is within 30 days." if compliant else "Signed master-plan evidence exceeds 30 days.")


def _anchor(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    return _presence(step, "treatment_reviews[*].review_date/signature_date or admission_date", context.anchor or "")


def _due(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    status: EvaluationStatus = "Conflicting Evidence" if context.due_conflict else context.timing_status
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
    return CriterionEvaluation(step.key, step.title, "Conflicting Evidence" if context.due_conflict else "Compliant",
                               "source_due_date vs calculated_due_date", f"source={_iso(context.source_due)}; calculated={_iso(context.calculated_due)}",
                               "Conflicting due-date evidence found." if context.due_conflict else "No due-date conflict found.")


def _loc_change(step: ChecklistStep, context: EvaluationContext) -> CriterionEvaluation:
    status: EvaluationStatus = "Needs Review" if context.loc_changed else "Not Applicable"
    return CriterionEvaluation(step.key, step.title, status, "loc_history[*].effective_date",
                               _iso(context.loc_candidate) or "no candidate", "The seven-day candidate is display-only and cannot activate compliance.")


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


def _iso(value: date | None) -> str:
    return value.isoformat() if value is not None else ""


def _safe(value: str | date | tuple[dict[str, JsonValue], ...]) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return f"{len(value)} record(s)"
    return value.strip()[:160]
