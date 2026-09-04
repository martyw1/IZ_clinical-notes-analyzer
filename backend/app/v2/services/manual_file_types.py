from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Final

from app.v2.domain.schemas import TreatmentPlanAggregate

OPTIONAL_MANUAL_METADATA_FIELDS: Final = frozenset({"patient_full_name", "service_date", "original_plan_reference"})


def unique_manual_metadata_values(field: str, values: Iterable[str]) -> tuple[str, ...]:
    representatives: dict[str, str] = {}
    for value in values:
        normalized = " ".join(value.split()) if field == "patient_full_name" else value.strip()
        if normalized:
            key = normalized.casefold() if field == "patient_full_name" else normalized
            representatives[key] = min(representatives.get(key, normalized), normalized)
    return tuple(representatives[key] for key in sorted(representatives))


@dataclass(frozen=True, slots=True)
class ManualTextFields(Mapping[str, str]):
    data: Mapping[str, str]
    conflicting_fields: tuple[str, ...] = ()

    def __getitem__(self, key: str) -> str:
        return self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


class ManualFileParseError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ManualFilePatientIdCorrectionRequired(ManualFileParseError):
    pass


@dataclass(frozen=True, slots=True)
class ManualFileAggregateSource:
    aggregate: TreatmentPlanAggregate
    source_format: str
    parsed_fields_count: int
    patient_id_correction_applied: bool
    patient_full_name: str = ""


@dataclass(frozen=True, slots=True)
class ParsedManualFields:
    patient_id: str
    patient_id_correction_applied: bool
    level_of_care: str
    admission_date: str
    due_date: str
    reason_for_admission: str
    initial_client_needs: str
    family_education_needs: str
    problem_description: str
    diagnosis_description: str
    icd10_code: str
    behavioral_definition: str
    goal_description: str
    objective_description: str
    intervention_description: str
    signature_datetime: str
    raw_text: str
    patient_full_name: str = ""
    service_date: str = ""
    original_plan_reference: str = ""
    conflicting_fields: tuple[str, ...] = ()
    data_quality_warnings: tuple[str, ...] = ()
    parsed_source_count: int = 1
    opaque_source_count: int = 0
