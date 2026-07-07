from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from app.services.alleva_retrieval import DEFAULT_API_VERSION

TREATMENT_PLAN_HARNESS_REPORTS: Final = {
    'all_treatment_plans',
    'all_treatment_plans_all_pages',
    'single_treatment_plan',
    'treatment_plan_counts',
}
DEFAULT_TREATMENT_PLAN_LIMIT: Final = 100
DEFAULT_TREATMENT_PLAN_START_DATE: Final = '2000-01-01T16:03'
NON_SUCCESS_BODY_PREVIEW_OMITTED: Final = '[saved to response_body_file; preview omitted for upstream non-success response]'


@dataclass(frozen=True, slots=True)
class TreatmentPlanHarnessRequest:
    report: str
    base_url: str
    operation_parameters: dict[str, Any]
    api_key: str = ''
    bearer_token: str = ''
    api_key_header_name: str = 'x-api-key'
    timeout_seconds: int = 10
    patient_id: str = ''
    max_pages: int = 10


@dataclass(frozen=True, slots=True)
class StreamedBody:
    status_code: int
    content_type: str
    elapsed_ms: int
    url: str
    body_file: str
    preview: bytes
    observed_bytes: int
    truncated: bool


def treatment_plan_default_parameters(operation_parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = dict(operation_parameters or {})
    parameters.setdefault('Limit', DEFAULT_TREATMENT_PLAN_LIMIT)
    parameters.setdefault('Cursor', 0)
    parameters.setdefault('StartDate', DEFAULT_TREATMENT_PLAN_START_DATE)
    parameters.setdefault('api-version', DEFAULT_API_VERSION)
    parameters.setdefault('X-Version', DEFAULT_API_VERSION)
    return parameters
