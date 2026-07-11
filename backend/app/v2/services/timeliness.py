from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

from app.v2.domain.schemas import ReviewStatus, TreatmentPlanAggregate

UNKNOWN_VALUES: Final = frozenset({"", "unknown", "unavailable", "unvalidated_configurable"})


@dataclass(frozen=True, slots=True)
class TimelinessRules:
    master_due_days: int = 30
    php_review_interval_days: int = 30
    iop_op_review_interval_days: int = 60
    loc_change_window_days: int | None = 7
    loc_change_window_validated: bool = False


@dataclass(frozen=True, slots=True)
class TimelinessEvaluation:
    status: ReviewStatus
    due_date: str
    reason: str
    missing_fields: tuple[str, ...]


def evaluate_treatment_plan_timing(
    aggregate: TreatmentPlanAggregate,
    rules: TimelinessRules,
    evaluation_date: date,
) -> TimelinessEvaluation:
    missing_fields = _missing_fields(aggregate)
    if missing_fields:
        return TimelinessEvaluation(
            status="Missing Data",
            due_date=aggregate.date_clock_due_date,
            reason=_missing_reason(missing_fields, rules),
            missing_fields=missing_fields,
        )
    if len(aggregate.loc_history) > 1 and not rules.loc_change_window_validated:
        return TimelinessEvaluation(
            status="Needs Review",
            due_date=aggregate.date_clock_due_date,
            reason="LOC-change timing is configurable but unvalidated; do not determine compliance from the placeholder window.",
            missing_fields=(),
        )
    try:
        due_date = date.fromisoformat(aggregate.date_clock_due_date)
    except ValueError:
        return TimelinessEvaluation(
            status="Unable to Evaluate",
            due_date=aggregate.date_clock_due_date,
            reason="The supplied next-review due date is not an ISO calendar date.",
            missing_fields=(),
        )
    days_until_due = (due_date - evaluation_date).days
    if days_until_due < 0:
        status: ReviewStatus = "Overdue"
    elif days_until_due <= 1:
        status = "Urgent"
    elif days_until_due <= 7:
        status = "Due Soon"
    else:
        status = "Current/Compliant"
    return TimelinessEvaluation(
        status=status,
        due_date=due_date.isoformat(),
        reason=f"The source due date is {days_until_due} facility-local calendar day(s) from evaluation.",
        missing_fields=(),
    )


def _missing_fields(aggregate: TreatmentPlanAggregate) -> tuple[str, ...]:
    candidates = (
        ("admission_date", aggregate.admission_date),
        ("current_level_of_care", aggregate.current_level_of_care),
        ("date_clock_due_date", aggregate.date_clock_due_date),
        ("signature_datetime", aggregate.content_snapshot.signatures[0].signature_datetime),
    )
    return tuple(name for name, value in candidates if value.strip().lower() in UNKNOWN_VALUES)


def _missing_reason(missing_fields: tuple[str, ...], rules: TimelinessRules) -> str:
    labels = ", ".join(missing_fields)
    return f"Cannot determine timeliness because required evidence is unavailable: {labels}. The configured master window is {rules.master_due_days} days."
