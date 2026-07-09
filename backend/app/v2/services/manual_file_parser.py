from __future__ import annotations

import csv
import re
from io import StringIO
from pathlib import Path
from typing import Final, Mapping

from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_extractors import extract_manual_file
from app.v2.services.manual_file_types import (
    ManualFileAggregateSource,
    ManualFileParseError,
    ParsedManualFields,
)

MAX_UPLOAD_BYTES: Final = 512 * 1024
FIELD_ALIASES: Final[Mapping[str, str]] = {
    "patient_id": "patient_id",
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
) -> ManualFileAggregateSource:
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ManualFileParseError("Manual treatment-plan files are limited to 512 KiB for the local desktop beta.")
    suffix = Path(filename).suffix.lower()
    extracted = extract_manual_file(raw_bytes, filename)
    fields = _fields_from_text_like_file(extracted.raw_text, suffix)
    parsed = _parsed_fields(fields, fallback_patient_id.strip(), extracted.raw_text)
    return ManualFileAggregateSource(
        aggregate=build_manual_aggregate(parsed),
        source_format=extracted.source_format,
        parsed_fields_count=_non_empty_field_count(fields),
    )


def _fields_from_text_like_file(text: str, suffix: str) -> Mapping[str, str]:
    match suffix:
        case ".txt" | ".md" | ".pdf" | ".xlsx":
            return _key_value_lines(text)
        case ".csv":
            return _delimited_row(text, ",")
        case ".tsv":
            return _delimited_row(text, "\t")
        case _:
            raise ManualFileParseError("Supported manual treatment-plan files are .txt, .md, .csv, .tsv, .pdf, and .xlsx.")


def _key_value_lines(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        raw_key, raw_value = line.split(":", 1)
        key = _canonical_key(raw_key)
        if key:
            fields[key] = raw_value.strip()
    return fields


def _delimited_row(text: str, delimiter: str) -> dict[str, str]:
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    first_row = next(reader, None)
    if first_row is None:
        raise ManualFileParseError("Manual treatment-plan table must include one header row and one data row.")
    return {_canonical_key(key): value.strip() for key, value in first_row.items() if key and value}


def _canonical_key(raw_key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", raw_key.strip().lower()).strip("_")
    return FIELD_ALIASES.get(normalized, "")


def _parsed_fields(fields: Mapping[str, str], fallback_patient_id: str, raw_text: str) -> ParsedManualFields:
    patient_id = fields.get("patient_id", "").strip() or fallback_patient_id
    if not patient_id:
        raise ManualFileParseError("Patient ID is required in the file or the Patient ID override field.")
    return ParsedManualFields(
        patient_id=patient_id,
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
    )


def _non_empty_field_count(fields: Mapping[str, str]) -> int:
    return sum(1 for value in fields.values() if value.strip())
