from __future__ import annotations

from dataclasses import dataclass
from typing import Final, assert_never

from app.v2.domain.schemas import JsonValue, SignatureEvidenceRole, TreatmentPlanAggregate

PLACEHOLDERS: Final = frozenset({"", "missing", "unknown", "unavailable", "unvalidated_configurable", "none", "null"})
PLAN_FIELDS: Final = ("id", "plan_id", "planId", "plan_date", "planDate", "plan_kind", "document_type")
REVIEW_FIELDS: Final = ("review_date", "reviewDate", "updated_date", "date", "signature_date", "signatureDate", "signed_at", "signed", "is_signed")


@dataclass(frozen=True, slots=True)
class ObservedSource:
    source_path: str


def criterion_source_support(key: str, aggregate: TreatmentPlanAggregate) -> tuple[ObservedSource, ...]:
    admission = _observed("admission_date", aggregate.admission_date)
    loc = _observed("current_level_of_care", aggregate.current_level_of_care)
    initial = _signatures(aggregate, "initial_plan")
    master = _signatures(aggregate, "master_plan")
    anchors = admission + _records(aggregate.treatment_reviews, "treatment_reviews", REVIEW_FIELDS)
    match key:
        case "confirm_admission_date":
            return admission
        case "confirm_current_loc" | "confirm_loc_rule_mapping":
            return loc
        case "confirm_staff_signature_status":
            return initial
        case "initial_plan_exists" | "master_plan_exists":
            return _plans(aggregate)
        case "initial_plan_dated_correctly" | "initial_plan_required_signatures":
            return admission + initial
        case "master_plan_within_30_days":
            return admission + master
        case "master_plan_required_signatures":
            return master
        case "latest_valid_review_identified":
            return anchors
        case "calculate_next_review_due_date" | "check_conflicting_evidence":
            return anchors + loc + _observed("source_due_date", aggregate.source_due_date)
        case "identify_loc_change":
            return tuple(dict.fromkeys(source for index, row in enumerate(aggregate.loc_history)
                         for source in (loc if row.get("source") == "manual_upload_file" else tuple(
                             source for field in ("level_of_care", "loc_code", "effective_date")
                             for source in _observed(f"loc_history[{index}].{field}", row.get(field))))))
        case "loc_change_update_document":
            return tuple(source for index, row in enumerate(aggregate.treatment_plans)
                         if row.get("plan_kind") == "loc_change_update" or row.get("document_type") == "loc_change_update"
                         for field in ("plan_kind", "document_type")
                         for source in _observed(f"treatment_plans[{index}].{field}", row.get(field)))
        case _:
            return ()


def _observed(path: str, value: JsonValue) -> tuple[ObservedSource, ...]:
    match value:
        case str() as raw:
            return () if raw.strip().casefold() in PLACEHOLDERS else (ObservedSource(path),)
        case bool() | int() | float():
            return (ObservedSource(path),)
        case list() | dict() | None:
            return ()
        case unreachable:
            assert_never(unreachable)


def _signatures(aggregate: TreatmentPlanAggregate, role: SignatureEvidenceRole) -> tuple[ObservedSource, ...]:
    return tuple(source for item in aggregate.content_snapshot.signatures if item.evidence_role == role
                 for source in _observed(item.source_json_path, item.signature_datetime))


def _records(rows: tuple[dict[str, JsonValue], ...], path: str, fields: tuple[str, ...]) -> tuple[ObservedSource, ...]:
    return tuple(source for index, row in enumerate(rows) for field in fields
                 for source in _observed(f"{path}[{index}].{field}", row.get(field)))


def _plans(aggregate: TreatmentPlanAggregate) -> tuple[ObservedSource, ...]:
    return tuple(source for index, row in enumerate(aggregate.treatment_plans)
                 for field in (PLAN_FIELDS[3:] if row.get("source") == "manual_upload_file" else PLAN_FIELDS)
                 for source in _observed(f"treatment_plans[{index}].{field}", row.get(field)))
