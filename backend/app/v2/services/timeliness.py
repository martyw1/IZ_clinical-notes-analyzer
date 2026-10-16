from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, cast

from app.v2.domain.schemas import ReviewStatus, TreatmentPlanAggregate
from app.v2.services.deadline_calendar import deadline_status
from app.v2.services.evaluation_evidence import collect_evidence
from app.v2.services.rule_package import load_rule_package

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
            due_date="Unknown",
            reason=_missing_reason(missing_fields, rules),
            missing_fields=missing_fields,
        )
    if len(aggregate.loc_history) > 1 and not rules.loc_change_window_validated:
        return TimelinessEvaluation(
            status="Needs Review",
            due_date="Unknown",
            reason="LOC-change timing is configurable but unvalidated; do not determine compliance from the placeholder window.",
            missing_fields=(),
        )
    evidence = collect_evidence(aggregate, load_rule_package(), evaluation_date)
    if evidence.anchor is None or not evidence.mapped_loc:
        return TimelinessEvaluation("Unable to Evaluate", "Unknown", "The plan last updated date or LOC is invalid.", ())
    if evidence.anchor > evaluation_date:
        return TimelinessEvaluation("Needs Review", "Unknown", "The plan last updated date is in the future.", ())
    interval = rules.php_review_interval_days if evidence.mapped_loc == "PHP" else rules.iop_op_review_interval_days
    due_date = evidence.anchor + timedelta(days=interval)
    return TimelinessEvaluation(
        status=cast(ReviewStatus, deadline_status(due_date, evaluation_date)),
        due_date=due_date.isoformat(),
        reason="Next update due uses the plan last updated date plus the LOC calendar-day interval; Due Soon uses 10 business days.",
        missing_fields=(),
    )


def _missing_fields(aggregate: TreatmentPlanAggregate) -> tuple[str, ...]:
    candidates = (
        ("admission_date", aggregate.admission_date),
        ("current_level_of_care", aggregate.current_level_of_care),
        ("source_last_updated", aggregate.source_last_updated),
        ("signature_datetime", next((item.signature_datetime for item in aggregate.content_snapshot.signatures if item.signature_datetime.strip()), "")),
    )
    return tuple(name for name, value in candidates if value.strip().lower() in UNKNOWN_VALUES)


def _missing_reason(missing_fields: tuple[str, ...], rules: TimelinessRules) -> str:
    labels = ", ".join(missing_fields)
    return f"Cannot determine timeliness because required evidence is unavailable: {labels}. The configured master window is {rules.master_due_days} days."
