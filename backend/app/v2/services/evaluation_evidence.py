from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from app.v2.domain.schemas import JsonValue, TreatmentPlanAggregate
from app.v2.services.rule_package import DeterministicRulePackage

UNKNOWN_VALUES: Final = frozenset({"", "unknown", "unavailable", "unvalidated_configurable", "none", "null"})


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    aggregate: TreatmentPlanAggregate
    admission: date | None
    initial_signature: date | None
    initial_signature_path: str
    master_signature: date | None
    master_signature_path: str
    anchor: date | None
    calculated_due: date | None
    source_due: date | None
    source_due_missing: bool
    source_due_invalid: bool
    mapped_loc: str
    interval_days: int | None
    due_conflict: bool
    malformed_signature: bool
    future_review: bool
    plans_missing: bool
    loc_changed: bool
    loc_conflict: bool
    loc_candidate: date | None


def collect_evidence(
    aggregate: TreatmentPlanAggregate,
    package: DeterministicRulePackage,
    today: date,
) -> EvaluationEvidence:
    admission = parse_date(aggregate.admission_date)
    initial, initial_path, initial_malformed = _role_signature(aggregate, "initial_plan")
    master, master_path, master_malformed = _role_signature(aggregate, "master_plan")
    any_malformed = initial_malformed or master_malformed or any(
        known(item.signature_datetime) and parse_date(item.signature_datetime) is None
        for item in aggregate.content_snapshot.signatures
    )
    review_anchor, future_review = _latest_signed_review(aggregate, today)
    anchor = review_anchor or admission
    mapped_loc, interval = _map_loc(aggregate.current_level_of_care, package)
    calculated_due = anchor + timedelta(days=interval) if anchor is not None and interval is not None else None
    source_due = parse_date(aggregate.source_due_date)
    source_due_missing = not known(aggregate.source_due_date)
    source_due_invalid = not source_due_missing and source_due is None
    due_conflict = calculated_due is not None and source_due is not None and calculated_due != source_due
    loc_values = {
        _text(row, "level_of_care", "loc_code").strip().casefold()
        for row in aggregate.loc_history
        if _text(row, "level_of_care", "loc_code").strip()
    }
    current_loc = aggregate.current_level_of_care.strip().casefold()
    loc_conflict = bool(loc_values) and current_loc not in loc_values
    loc_changed = len(loc_values) > 1
    effective_dates = tuple(parse_date(_text(row, "effective_date")) for row in aggregate.loc_history)
    latest_loc = max((item for item in effective_dates if item is not None), default=None)
    loc_candidate = (
        latest_loc + timedelta(days=package.rules.loc_change_blocker.default_preset_calendar_days)
        if loc_changed and latest_loc else None
    )
    return EvaluationEvidence(
        aggregate, admission, initial, initial_path, master, master_path, anchor, calculated_due,
        source_due, source_due_missing, source_due_invalid, mapped_loc, interval, due_conflict,
        any_malformed, future_review, not bool(aggregate.treatment_plans), loc_changed,
        loc_conflict, loc_candidate,
    )


def parse_date(raw: str) -> date | None:
    if not known(raw):
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def known(raw: str) -> bool:
    return raw.strip().casefold() not in UNKNOWN_VALUES


def record_text(record: dict[str, JsonValue], *keys: str) -> str:
    return _text(record, *keys)


def _role_signature(aggregate: TreatmentPlanAggregate, role: str) -> tuple[date | None, str, bool]:
    matches = tuple(item for item in aggregate.content_snapshot.signatures if item.evidence_role == role)
    parsed = tuple(parse_date(item.signature_datetime) for item in matches)
    valid = tuple(value for value in parsed if value is not None)
    path = matches[0].source_json_path if matches else f"content_snapshot.signatures[?(@.evidence_role='{role}')]"
    malformed = any(known(item.signature_datetime) and value is None for item, value in zip(matches, parsed, strict=True))
    return max(valid, default=None), path, malformed


def _latest_signed_review(aggregate: TreatmentPlanAggregate, today: date) -> tuple[date | None, bool]:
    candidates: list[date] = []
    future = False
    for review in aggregate.treatment_reviews:
        review_date = parse_date(_text(review, "review_date", "reviewDate", "updated_date", "date"))
        signature_date = parse_date(_text(review, "signature_date", "signatureDate", "signed_at"))
        signed = bool(signature_date) or _text(review, "signed", "is_signed").casefold() in {"true", "yes", "1"}
        if signed and review_date is not None:
            future = future or review_date > today or bool(signature_date and signature_date > today)
            if review_date <= today and (signature_date is None or signature_date <= today):
                candidates.append(review_date)
    return max(candidates, default=None), future


def _map_loc(raw: str, package: DeterministicRulePackage) -> tuple[str, int | None]:
    normalized = raw.strip().casefold()
    for name, rule in package.rules.levels_of_care.items():
        aliases = {alias.strip().casefold() for alias in rule.aliases} | {name.casefold()}
        if normalized in aliases:
            return name, rule.treatment_plan_update_interval_days
    return "", None


def _text(record: dict[str, JsonValue], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)):
            return str(value)
    return ""
