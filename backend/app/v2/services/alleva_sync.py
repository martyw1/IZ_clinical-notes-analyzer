from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Final
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.models import AppSetting, User
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields
from app.v2.services.oauth_connectivity import request_client_credentials
from app.v2.services.secure_storage import decrypt_text_secret
from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

MAX_SYNC_ROWS: Final = 5_000


class AllevaSyncError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class AllevaSyncCancelled(AllevaSyncError):
    pass


@dataclass(frozen=True, slots=True)
class AllevaSyncResult:
    imported_patient_count: int
    skipped_plan_count: int


def run_treatment_plan_sync(db: Session, profile: AppSetting, actor: User, is_cancelled: Callable[[], bool] = lambda: False) -> AllevaSyncResult:
    if is_cancelled():
        raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled before it started.")
    token = _oauth_token(profile)
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=max(1, min(profile.emr_api_timeout_seconds, 60)), follow_redirects=True) as client:
            clients = _paged_records(client, profile, "/clients", headers, is_cancelled)
            plans = _paged_records(client, profile, "/treatment-plans", headers, is_cancelled)
            imported, skipped = _save_client_aggregates(db, client, profile, actor, clients, plans, headers, is_cancelled)
    except (httpx.HTTPError, ValueError) as exc:
        raise AllevaSyncError("Alleva read-only treatment-plan sync did not complete successfully.") from exc
    return AllevaSyncResult(imported_patient_count=imported, skipped_plan_count=skipped)


def _oauth_token(profile: AppSetting) -> str:
    if not profile.api_client_secret:
        raise AllevaSyncError("Encrypted Alleva client secret is not configured.")
    _, token = request_client_credentials(
        token_url=profile.api_oauth_token_url,
        client_id=profile.api_client_id,
        client_secret=decrypt_text_secret(profile.api_client_secret),
        scope=profile.api_scopes,
        token_auth_style=profile.api_token_auth_style,
        timeout_seconds=profile.emr_api_timeout_seconds,
    )
    if not token:
        raise AllevaSyncError("OAuth verification failed before treatment-plan sync could start.")
    return token


def _paged_records(client: httpx.Client, profile: AppSetting, path: str, headers: dict[str, str], is_cancelled: Callable[[], bool]) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    offset = 0
    page_size = max(1, min(profile.api_pagination_limit, 500))
    limit = max(1, min(profile.alleva_treatment_plan_sync_limit, MAX_SYNC_ROWS))
    while len(records) < limit:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        response = client.get(urljoin(f"{profile.api_base_url.rstrip('/')}/", path.lstrip("/")), params={"limit": min(page_size, limit - len(records)), "offset": offset}, headers=headers)
        response.raise_for_status()
        page = _records(response.json())
        records.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    return tuple(records[:limit])


def _records(payload: object) -> list[dict[str, object]]:
    values = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("Expected an API list response.")
    return [value for value in values if isinstance(value, dict)]


def _save_client_aggregates(
    db: Session,
    client: httpx.Client,
    profile: AppSetting,
    actor: User,
    clients: tuple[dict[str, object], ...],
    plans: tuple[dict[str, object], ...],
    headers: dict[str, str],
    is_cancelled: Callable[[], bool],
) -> tuple[int, int]:
    imported = 0
    skipped = 0
    for client_payload in clients:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        patient_id = _first_text(client_payload, "clientId", "id", "uniqueId", "mrn")
        if not patient_id or not _is_active(client_payload):
            continue
        plan = _plan_for_patient(plans, patient_id)
        if plan is None:
            skipped += 1
            continue
        plan_id = _first_text(plan, "id", "treatmentPlanId")
        detail = _plan_detail(client, profile, plan_id, headers) if plan_id else plan
        aggregate = _aggregate_from_payload(patient_id, client_payload, plan, detail, plan_id)
        save_treatment_plan_aggregate(db, aggregate, actor)
        imported += 1
    return imported, skipped


def _is_active(payload: dict[str, object]) -> bool:
    value = payload.get("isActive")
    return value is not False and str(value).strip().lower() not in {"false", "inactive", "discharged", "closed"}


def _plan_for_patient(plans: tuple[dict[str, object], ...], patient_id: str) -> dict[str, object] | None:
    for plan in plans:
        aliases = {_first_text(plan, "clientId", "client_id", "patientId", "patient_id")}
        if patient_id in aliases:
            return plan
    return None


def _plan_detail(client: httpx.Client, profile: AppSetting, plan_id: str, headers: dict[str, str]) -> dict[str, object]:
    response = client.get(urljoin(f"{profile.api_base_url.rstrip('/')}/", f"treatment-plans/{plan_id}"), headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected an API treatment-plan detail object.")
    return payload


def _aggregate_from_payload(
    patient_id: str,
    client: dict[str, object],
    plan: dict[str, object],
    detail: dict[str, object],
    plan_id: str,
) -> TreatmentPlanAggregate:
    parsed = ParsedManualFields(
        patient_id=patient_id,
        patient_id_correction_applied=False,
        level_of_care=_first_text(client, "levelOfCare", "currentLevelOfCare") or "Unknown",
        admission_date=_first_text(client, "admissionDate", "admissionDateTime") or "Unknown",
        due_date=_first_text(plan, "nextReviewDue", "nextReviewDueDate") or "Unknown",
        reason_for_admission=_first_text(detail, "reasonForAdmission"),
        initial_client_needs=_first_text(detail, "initialClientNeeds"),
        family_education_needs=_first_text(detail, "familyEducationNeeds"),
        problem_description=_nested_text(detail, "problems", "problemDescription", "description"),
        diagnosis_description=_nested_text(detail, "diagnoses", "diagnosisDescription", "description"),
        icd10_code=_nested_text(detail, "diagnoses", "icd10Code", "code"),
        behavioral_definition=_nested_text(detail, "behavioralDefinitions", "behavioralDefinition", "description"),
        goal_description=_nested_text(detail, "goals", "goalDescription", "description"),
        objective_description=_nested_text(detail, "objectives", "objectiveDescription", "description"),
        intervention_description=_nested_text(detail, "interventions", "interventionDescription", "description"),
        signature_datetime=_first_text(detail, "staffSignatureDate", "clientSignatureDate", "signatureDate"),
        raw_text=f"{patient_id}|{plan_id}|{_first_text(detail, 'lastModified', 'updatedAt')}",
    )
    aggregate = build_manual_aggregate(parsed)
    source_path = f"/treatment-plans/{plan_id}" if plan_id else "/treatment-plans"
    evidence = tuple(ref.model_copy(update={"source_endpoint": "Alleva REST", "source_json_path": source_path}) for ref in aggregate.source_evidence)
    criteria = tuple(
        criterion.model_copy(update={
            "source_endpoint": "Alleva REST",
            "finding_message": criterion.finding_message.replace("parsed manual-upload", "Alleva REST"),
            "evidence_refs": tuple(ref.model_copy(update={"source_endpoint": "Alleva REST"}) for ref in criterion.evidence_refs),
        })
        for criterion in aggregate.criteria_results
    )
    snapshot = aggregate.content_snapshot.model_copy(update={
        "source_mode": "alleva_rest_api",
        "observed_fields": tuple(field.model_copy(update={"source_endpoint": "Alleva REST"}) for field in aggregate.content_snapshot.observed_fields),
    })
    return aggregate.model_copy(
        update={
            "source_mode": "alleva_rest_api",
            "status_label": "Alleva REST sync",
            "treatment_plans": ({"plan_id": plan_id, "is_active": True, "source": "alleva_rest_api"},),
            "active_treatment_plans": ({"plan_id": plan_id, "is_active": True},),
            "latest_created_active_plan": {"plan_id": plan_id, "label": "Alleva REST treatment plan"},
            "current_plan_selection_reason": "Latest mapped active Alleva treatment plan",
            "treatment_review_data_status": "not_requested",
            "source_evidence": evidence,
            "criteria_results": criteria,
            "content_snapshot": snapshot,
            "data_quality_warnings": aggregate.data_quality_warnings + ("Alleva REST treatment-plan sync is read-only; source payload remains encrypted at rest.",),
            "audit_refs": ("alleva.treatment_plan_sync.completed",),
        }
    )


def _first_text(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_text(payload: dict[str, object], collection: str, *keys: str) -> str:
    value = payload.get(collection)
    if not isinstance(value, list):
        return ""
    for item in value:
        if isinstance(item, dict):
            text = _first_text(item, *keys)
            if text:
                return text
    return ""
