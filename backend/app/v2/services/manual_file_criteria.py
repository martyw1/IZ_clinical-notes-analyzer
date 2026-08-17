from __future__ import annotations

import json
from typing import Final, Mapping

from app.core.config import RESOURCE_ROOT
from app.v2.domain.schemas import ContentEvidenceRef, JsonValue, ReviewStatus, TreatmentPlanCriterionResult
from app.v2.services.manual_file_types import ManualFileParseError, ParsedManualFields

SOURCE_ENDPOINT: Final = "manual_upload://parsed-treatment-plan-file"
UNKNOWN_VALUES: Final = {"", "unknown", "unavailable", "unvalidated_configurable"}


def criteria_from_parsed(parsed: ParsedManualFields) -> tuple[TreatmentPlanCriterionResult, ...]:
    steps = _load_checklist_steps()
    if len(steps) < 42:
        raise ManualFileParseError("Treatment Plan Checklist Version 1 must contain 42 steps.")
    return tuple(_criterion_result(index, step, parsed) for index, step in enumerate(steps[:42], start=1))


def evidence_ref(ref_id: str, label: str, path: str, safe_preview: str) -> ContentEvidenceRef:
    return ContentEvidenceRef(
        ref_id=ref_id,
        label=label,
        source_json_path=path,
        source_endpoint=SOURCE_ENDPOINT,
        safe_preview=safe_preview,
        redaction_status="redacted_safe_preview",
    )


def preview(value: str) -> str:
    return value.strip()[:160]


def present_sections(parsed: ParsedManualFields) -> tuple[str, ...]:
    candidates = (
        ("reason_for_admission", parsed.reason_for_admission),
        ("initial_client_needs", parsed.initial_client_needs),
        ("family_education_needs", parsed.family_education_needs),
        ("diagnoses", parsed.diagnosis_description),
        ("behavioral_definitions", parsed.behavioral_definition),
        ("goals", parsed.goal_description),
        ("objectives", parsed.objective_description),
        ("interventions", parsed.intervention_description),
        ("signatures_metadata", parsed.signature_datetime),
    )
    return tuple(name for name, value in candidates if _has_value(value))


def missing_sections(existing_sections: tuple[str, ...]) -> tuple[str, ...]:
    all_sections = (
        "reason_for_admission",
        "initial_client_needs",
        "family_education_needs",
        "diagnoses",
        "behavioral_definitions",
        "goals",
        "objectives",
        "interventions",
        "signatures_metadata",
        "trusted_nextReviewDue",
    )
    present = set(existing_sections)
    return tuple(section for section in all_sections if section not in present)


def _criterion_result(
    index: int,
    step: Mapping[str, JsonValue],
    parsed: ParsedManualFields,
) -> TreatmentPlanCriterionResult:
    key = _step_text(step, "key", f"criterion_{index}")
    title = _step_text(step, "title", f"Criterion {index}")
    path, value = _criterion_evidence_source(key, title, parsed)
    conflict_key = _conflict_key(path)
    conflict_refs: tuple[str, ...] = ()
    if parsed.parsed_source_count == 0:
        status: ReviewStatus = "Unable to Evaluate"
        evidence: tuple[ContentEvidenceRef, ...] = ()
    elif conflict_key in parsed.conflicting_fields:
        status = "Conflicting Evidence"
        evidence = ()
        conflict_refs = (path,)
    else:
        has_value = _has_value(value)
        evidence = (evidence_ref(key, title, path, preview(value)),) if has_value else ()
        status = "Compliant" if has_value else "Missing Data"
        if path == "manual_upload.raw_text" and parsed.raw_text.strip():
            status = "Needs Review"
            evidence = (
                evidence_ref(
                    key,
                    title,
                    path,
                    "Manual file text exists; parser could not map this criterion automatically.",
                ),
            )
    return TreatmentPlanCriterionResult(
        criterion_id=key,
        criterion_title=title,
        result_status=status,
        severity="info" if status == "Compliant" else "medium",
        finding_message=f"Criterion {index}: {status}; evaluated from parsed manual-upload fields.",
        content_considered=present_sections(parsed),
        evidence_refs=evidence,
        missing_content_refs=() if evidence else (path,),
        conflict_refs=conflict_refs,
        source_json_paths=(path,),
        source_endpoint=SOURCE_ENDPOINT,
        redaction_status="safe_preview_only",
        manager_action_options=("approve criterion", "return criterion for correction", "override with reason"),
    )


def _conflict_key(path: str) -> str:
    return {
        "admission_date": "admission_date",
        "current_level_of_care": "current_level_of_care",
        "date_clock_due_date": "date_clock_due_date",
        "content_snapshot.signatures[0].signature_datetime": "signature_datetime",
    }.get(path, "")


def _criterion_evidence_source(key: str, title: str, parsed: ParsedManualFields) -> tuple[str, str]:
    haystack = f"{key} {title}".lower()
    checks = (
        ("client", "patient_id", parsed.patient_id),
        ("active", "active_status", "active"),
        ("admission", "admission_date", parsed.admission_date),
        ("current loc", "current_level_of_care", parsed.level_of_care),
        ("loc", "current_level_of_care", parsed.level_of_care),
        ("signature", "content_snapshot.signatures[0].signature_datetime", parsed.signature_datetime),
        ("diagnos", "content_snapshot.problems[0].diagnoses[0].diagnosis_description", parsed.diagnosis_description),
        ("behavior", "content_snapshot.problems[0].behavioral_definitions[0].behavioral_definition", parsed.behavioral_definition),
        ("goal", "content_snapshot.problems[0].goals[0].goal_description", parsed.goal_description),
        ("objective", "content_snapshot.problems[0].goals[0].objectives[0].objective_description", parsed.objective_description),
        ("intervention", _intervention_path(), parsed.intervention_description),
        ("reason", "content_snapshot.reason_for_admission", parsed.reason_for_admission),
        ("need", "content_snapshot.initial_client_needs", parsed.initial_client_needs),
        ("family", "content_snapshot.family_education_needs", parsed.family_education_needs),
        ("date", "date_clock_due_date", parsed.due_date),
        ("timing", "date_clock_due_date", parsed.due_date),
        ("window", "date_clock_due_date", parsed.due_date),
        ("overdue", "date_clock_due_date", parsed.due_date),
    )
    for needle, path, value in checks:
        if needle in haystack:
            return path, value
    return "manual_upload.raw_text", parsed.raw_text


def _load_checklist_steps() -> tuple[Mapping[str, JsonValue], ...]:
    checklist_path = RESOURCE_ROOT / "config" / "checklists" / "treatment-plan-v1.json"
    payload = json.loads(checklist_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
        raise ManualFileParseError("Treatment Plan Checklist Version 1 could not be loaded.")
    return tuple(step for step in payload["steps"] if isinstance(step, dict))


def _step_text(step: Mapping[str, JsonValue], key: str, fallback: str) -> str:
    value = step.get(key)
    return value if isinstance(value, str) and value.strip() else fallback


def _has_value(value: str) -> bool:
    return value.strip().lower() not in UNKNOWN_VALUES


def _intervention_path() -> str:
    return "content_snapshot.problems[0].goals[0].objectives[0].interventions[0].intervention_description"
