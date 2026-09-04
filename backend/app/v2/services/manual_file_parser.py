from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from typing import Final, Mapping

from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_extractors import extract_manual_file
from app.v2.services.manual_file_types import (
    ManualFileAggregateSource,
    ManualFileParseError,
    ManualFilePatientIdCorrectionRequired,
    ManualTextFields,
    OPTIONAL_MANUAL_METADATA_FIELDS,
    ParsedManualFields,
    unique_manual_metadata_values,
)

MAX_UPLOAD_BYTES: Final = 512 * 1024
FIELD_ALIASES: Final[Mapping[str, str]] = {
    "patient_id": "patient_id",
    "mrn": "patient_id",
    "patient_name": "patient_full_name",
    "patient_full_name": "patient_full_name",
    "service_date": "service_date",
    "servicedate": "service_date",
    "original_plan_reference": "original_plan_reference",
    "current_level_of_care": "current_level_of_care",
    "loc": "current_level_of_care",
    "admission_date": "admission_date",
    "next_due_date": "date_clock_due_date",
    "date_clock_due_date": "date_clock_due_date",
    "reason_for_admission": "reason_for_admission",
    "initial_client_needs": "initial_client_needs",
    "family_education_needs": "family_education_needs",
    "problem": "problem_description",
    "problem_description": "problem_description",
    "diagnosis": "diagnosis_description",
    "diagnosis_description": "diagnosis_description",
    "icd10_code": "icd10_code",
    "behavioral_definition": "behavioral_definition",
    "goal": "goal_description",
    "goal_description": "goal_description",
    "objective": "objective_description",
    "objective_description": "objective_description",
    "intervention": "intervention_description",
    "intervention_description": "intervention_description",
    "signature_date": "signature_datetime",
    "signature_datetime": "signature_datetime",
}


def aggregate_from_manual_file(
    raw_bytes: bytes,
    fallback_patient_id: str,
    filename: str,
    confirm_patient_id_correction: bool = False,
) -> ManualFileAggregateSource:
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ManualFileParseError("Manual treatment-plan files are limited to 512 KiB for the local desktop beta.")
    suffix = Path(filename).suffix.lower()
    extracted = extract_manual_file(raw_bytes, filename)
    if extracted.is_opaque:
        raise ManualFileParseError("Opaque manual treatment-plan sources require the multi-file binder workflow.")
    fields = fields_from_manual_text(extracted.raw_text, suffix)
    parsed = _parsed_fields(
        fields,
        fallback_patient_id.strip(),
        extracted.raw_text,
        confirm_patient_id_correction,
    )
    return ManualFileAggregateSource(
        aggregate=build_manual_aggregate(parsed),
        source_format=extracted.source_format,
        parsed_fields_count=_non_empty_field_count(fields),
        patient_id_correction_applied=parsed.patient_id_correction_applied,
        patient_full_name=parsed.patient_full_name,
    )


def fields_from_manual_text(text: str, suffix: str) -> ManualTextFields:
    match suffix:  # noqa: MATCH_OK - Parser suffixes are open strings with an explicit reject boundary.
        case ".txt" | ".md" | ".pdf" | ".xlsx" | ".docx" | ".rtf":
            return _key_value_lines(text)
        case ".csv":
            return _delimited_row(text, ",")
        case ".tsv":
            return _delimited_row(text, "\t")
        case _:
            raise ManualFileParseError("The selected source does not contain deterministically extractable treatment-plan text.")


def _key_value_lines(text: str) -> ManualTextFields:
    pairs = (line.split(":", 1) for line in text.splitlines() if ":" in line)
    return _labeled_fields((key, value) for key, value in pairs)


def _delimited_row(text: str, delimiter: str) -> ManualTextFields:
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    first_row = next(reader, None)
    if first_row is None:
        raise ManualFileParseError("Manual treatment-plan table must include one header row and one data row.")
    return _labeled_fields((key, value) for key, value in first_row.items() if key and value)


def _labeled_fields(pairs: Iterable[tuple[str, str]]) -> ManualTextFields:
    fields: dict[str, str] = {}
    metadata: dict[str, list[str]] = {}
    conflicts: set[str] = set()
    for raw_key, raw_value in pairs:
        key = _canonical_key(raw_key)
        value = raw_value.strip()
        if not key:
            continue
        if key in OPTIONAL_MANUAL_METADATA_FIELDS:
            metadata.setdefault(key, []).append(value)
        fields[key] = value
    for field, values in metadata.items():
        unique = unique_manual_metadata_values(field, values)
        if len(unique) > 1:
            conflicts.add(field)
        fields[field] = unique[0] if len(unique) == 1 else ""
    return ManualTextFields(fields, tuple(sorted(conflicts)))


def _canonical_key(raw_key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", raw_key.strip().lower()).strip("_")
    return FIELD_ALIASES.get(normalized, "")


def _parsed_fields(
    fields: ManualTextFields,
    fallback_patient_id: str,
    raw_text: str,
    confirm_patient_id_correction: bool,
) -> ParsedManualFields:
    detected_patient_id = fields.get("patient_id", "").strip()
    patient_id_correction_applied = bool(
        detected_patient_id
        and fallback_patient_id
        and detected_patient_id != fallback_patient_id
    )
    if patient_id_correction_applied and not confirm_patient_id_correction:
        raise ManualFilePatientIdCorrectionRequired(
            "MRN correction confirmation is required because the file MRN differs from the override."
        )
    patient_id = fallback_patient_id if patient_id_correction_applied else detected_patient_id or fallback_patient_id
    if not patient_id:
        raise ManualFileParseError("MRN is required in the file or the MRN override field.")
    return ParsedManualFields(
        patient_id=patient_id,
        patient_id_correction_applied=patient_id_correction_applied,
        level_of_care=fields.get("current_level_of_care", "Unknown"),
        admission_date=fields.get("admission_date", "Unknown"),
        due_date=fields.get("date_clock_due_date", "Unknown"),
        reason_for_admission=fields.get("reason_for_admission", ""),
        initial_client_needs=fields.get("initial_client_needs", ""),
        family_education_needs=fields.get("family_education_needs", ""),
        problem_description=fields.get("problem_description", ""),
        diagnosis_description=fields.get("diagnosis_description", ""),
        icd10_code=fields.get("icd10_code", ""),
        behavioral_definition=fields.get("behavioral_definition", ""),
        goal_description=fields.get("goal_description", ""),
        objective_description=fields.get("objective_description", ""),
        intervention_description=fields.get("intervention_description", ""),
        signature_datetime=fields.get("signature_datetime", ""),
        raw_text=raw_text,
        patient_full_name=fields.get("patient_full_name", ""),
        service_date=fields.get("service_date", ""),
        original_plan_reference=fields.get("original_plan_reference", ""),
        conflicting_fields=fields.conflicting_fields,
        data_quality_warnings=tuple(f"Conflicting manual metadata field: {field}." for field in fields.conflicting_fields),
    )


def _non_empty_field_count(fields: Mapping[str, str]) -> int:
    return sum(1 for value in fields.values() if value.strip())
