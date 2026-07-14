from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_extractors import extract_manual_file
from app.v2.services.manual_file_parser import fields_from_manual_text
from app.v2.services.manual_file_types import (
    ManualFileParseError,
    ManualFilePatientIdCorrectionRequired,
    ParsedManualFields,
)

STRICT_SCALAR_FIELDS: Final = frozenset(
    {"current_level_of_care", "admission_date", "date_clock_due_date", "signature_datetime"}
)
CONTENT_TYPE_BY_FORMAT: Final[Mapping[str, str]] = {
    "csv": "text/csv",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpeg": "image/jpeg",
    "markdown": "text/markdown",
    "pdf": "application/pdf",
    "png": "image/png",
    "rtf": "application/rtf",
    "text": "text/plain",
    "tsv": "text/tab-separated-values",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


@dataclass(frozen=True, slots=True)
class ManualBinderLimits:
    max_file_count: int = 40
    max_file_bytes: int = 50 * 1024 * 1024
    max_total_bytes: int = 250 * 1024 * 1024


DEFAULT_BINDER_LIMITS: Final = ManualBinderLimits()


@dataclass(frozen=True, slots=True)
class ManualBinderFile:
    raw_bytes: bytes
    filename: str


@dataclass(frozen=True, slots=True)
class ManualBinderRequest:
    files: tuple[ManualBinderFile, ...]
    fallback_patient_id: str
    confirm_patient_id_correction: bool
    limits: ManualBinderLimits = DEFAULT_BINDER_LIMITS


@dataclass(frozen=True, slots=True)
class ManualBinderSource:
    raw_bytes: bytes
    source_format: str
    content_type: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ManualBinderResult:
    aggregate: TreatmentPlanAggregate
    sources: tuple[ManualBinderSource, ...]
    parsed_fields_count: int
    patient_id_correction_applied: bool
    parsed_file_count: int
    opaque_file_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Contribution:
    sha256: str
    raw_text: str
    fields: Mapping[str, str]
    source: ManualBinderSource
    is_opaque: bool
    warning: str


def aggregate_from_manual_binder(request: ManualBinderRequest) -> ManualBinderResult:
    _validate_binder(request.files, request.limits)
    contributions = tuple(sorted((_contribution(item) for item in request.files), key=lambda item: item.sha256))
    field_values = _field_values(contributions)
    patient_id, correction_applied = _resolve_patient_id(
        field_values.get("patient_id", ()),
        request.fallback_patient_id.strip(),
        request.confirm_patient_id_correction,
    )
    merged, conflicting_fields = _merge_fields(field_values)
    merged["patient_id"] = patient_id
    parsed_count = sum(not item.is_opaque for item in contributions)
    opaque_count = len(contributions) - parsed_count
    warnings = _warnings(contributions, conflicting_fields, correction_applied)
    parsed = ParsedManualFields(
        patient_id=merged["patient_id"],
        patient_id_correction_applied=correction_applied,
        level_of_care=merged.get("current_level_of_care", "Unknown"),
        admission_date=merged.get("admission_date", "Unknown"),
        due_date=merged.get("date_clock_due_date", "Unknown"),
        reason_for_admission=merged.get("reason_for_admission", ""),
        initial_client_needs=merged.get("initial_client_needs", ""),
        family_education_needs=merged.get("family_education_needs", ""),
        problem_description=merged.get("problem_description", ""),
        diagnosis_description=merged.get("diagnosis_description", ""),
        icd10_code=merged.get("icd10_code", ""),
        behavioral_definition=merged.get("behavioral_definition", ""),
        goal_description=merged.get("goal_description", ""),
        objective_description=merged.get("objective_description", ""),
        intervention_description=merged.get("intervention_description", ""),
        signature_datetime=merged.get("signature_datetime", ""),
        raw_text=_merged_raw_text(contributions),
        conflicting_fields=conflicting_fields,
        data_quality_warnings=warnings,
        parsed_source_count=parsed_count,
        opaque_source_count=opaque_count,
    )
    aggregate = build_manual_aggregate(parsed)
    return ManualBinderResult(
        aggregate=aggregate,
        sources=tuple(item.source for item in contributions),
        parsed_fields_count=sum(bool(value.strip()) for value in merged.values()),
        patient_id_correction_applied=correction_applied,
        parsed_file_count=parsed_count,
        opaque_file_count=opaque_count,
        warnings=warnings,
    )


def _validate_binder(files: tuple[ManualBinderFile, ...], limits: ManualBinderLimits) -> None:
    if not files:
        raise ManualFileParseError("At least one manual treatment-plan source file is required.")
    if len(files) > limits.max_file_count:
        raise ManualFileParseError(f"Manual treatment-plan binders are limited to {limits.max_file_count} files.", 413)
    total = 0
    for item in files:
        size = len(item.raw_bytes)
        if size == 0:
            raise ManualFileParseError("Manual treatment-plan source files cannot be empty.")
        if size > limits.max_file_bytes:
            raise ManualFileParseError("One manual treatment-plan source exceeds the per-file limit.", 413)
        total += size
        if total > limits.max_total_bytes:
            raise ManualFileParseError("Manual treatment-plan binder exceeds the total upload limit.", 413)


def _contribution(item: ManualBinderFile) -> _Contribution:
    extracted = extract_manual_file(item.raw_bytes, item.filename)
    sha256 = hashlib.sha256(item.raw_bytes).hexdigest()
    fields = (
        {}
        if extracted.is_opaque
        else fields_from_manual_text(extracted.raw_text, Path(item.filename).suffix.lower())
    )
    source = ManualBinderSource(
        raw_bytes=item.raw_bytes,
        source_format=extracted.source_format,
        content_type=CONTENT_TYPE_BY_FORMAT[extracted.source_format],
        sha256=sha256,
    )
    return _Contribution(
        sha256=sha256,
        raw_text=extracted.raw_text,
        fields=fields,
        source=source,
        is_opaque=extracted.is_opaque,
        warning=extracted.warning,
    )


def _field_values(contributions: tuple[_Contribution, ...]) -> dict[str, tuple[str, ...]]:
    collected: dict[str, list[str]] = {}
    for contribution in contributions:
        for key, raw_value in contribution.fields.items():
            value = re.sub(r"\s+", " ", raw_value).strip()
            if value:
                collected.setdefault(key, []).append(value)
    return {key: _unique_values(values) for key, values in collected.items()}


def _unique_values(values: list[str]) -> tuple[str, ...]:
    unique = {value.casefold(): value for value in values}
    return tuple(unique[key] for key in sorted(unique))


def _resolve_patient_id(
    detected_values: tuple[str, ...],
    fallback: str,
    confirmed: bool,
) -> tuple[str, bool]:
    detected = _unique_values(list(detected_values))
    correction_needed = bool(detected and (len(detected) > 1 or (fallback and detected != (fallback,))))
    if correction_needed and not fallback:
        raise ManualFilePatientIdCorrectionRequired(
            "Patient ID correction confirmation is required because conflicting Patient IDs were detected across the binder."
        )
    if correction_needed and not confirmed:
        raise ManualFilePatientIdCorrectionRequired(
            "Patient ID correction confirmation is required because the binder Patient ID differs from the override."
        )
    patient_id = fallback if correction_needed else (detected[0] if detected else fallback)
    if not patient_id:
        raise ManualFileParseError("Patient ID is required in an extractable source or the Patient ID override field.")
    return patient_id, correction_needed


def _merge_fields(field_values: Mapping[str, tuple[str, ...]]) -> tuple[dict[str, str], tuple[str, ...]]:
    merged: dict[str, str] = {}
    conflicts: list[str] = []
    for key in sorted(field_values):
        if key == "patient_id":
            continue
        values = field_values[key]
        if key in STRICT_SCALAR_FIELDS and len(values) > 1:
            merged[key] = "Unknown"
            conflicts.append(key)
        else:
            merged[key] = "\n\n".join(values)
    return merged, tuple(conflicts)


def _merged_raw_text(contributions: tuple[_Contribution, ...]) -> str:
    unique = {item.sha256: item.raw_text.strip() for item in contributions if item.raw_text.strip()}
    return "\n\n".join(unique[key] for key in sorted(unique))


def _warnings(
    contributions: tuple[_Contribution, ...],
    conflicting_fields: tuple[str, ...],
    correction_applied: bool,
) -> tuple[str, ...]:
    warnings = {item.warning for item in contributions if item.warning}
    if conflicting_fields:
        warnings.add("Conflicting scalar evidence was preserved for manager review; no file-order value was selected.")
    if correction_applied:
        warnings.add("Patient ID correction was explicitly confirmed for this binder.")
    return tuple(sorted(warnings))
