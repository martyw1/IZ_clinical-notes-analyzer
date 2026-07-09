from __future__ import annotations

from dataclasses import dataclass

from app.v2.domain.schemas import TreatmentPlanAggregate


class ManualFileParseError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ManualFileAggregateSource:
    aggregate: TreatmentPlanAggregate
    source_format: str
    parsed_fields_count: int


@dataclass(frozen=True, slots=True)
class ParsedManualFields:
    patient_id: str
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
