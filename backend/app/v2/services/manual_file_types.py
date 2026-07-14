from __future__ import annotations

from dataclasses import dataclass

from app.v2.domain.schemas import TreatmentPlanAggregate


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
    conflicting_fields: tuple[str, ...] = ()
    data_quality_warnings: tuple[str, ...] = ()
    parsed_source_count: int = 1
    opaque_source_count: int = 0
