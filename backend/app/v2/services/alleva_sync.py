from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Final
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.models import AppSetting, User
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields
from app.v2.services.alleva_contracts import ApprovedAllevaContract, reconcile_sync_patients
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


def run_treatment_plan_sync(
    db: Session,
    profile: AppSetting,
    actor: User,
    contract: ApprovedAllevaContract,
    is_cancelled: Callable[[], bool] = lambda: False,
    on_page: Callable[[str, int, str, str, int], None] | None = None,
    sync_job_id: str | None = None,
) -> AllevaSyncResult:
    if is_cancelled():
        raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled before it started.")
    token = _oauth_token(profile, contract, is_cancelled)
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=max(1, min(profile.emr_api_timeout_seconds, 60)), follow_redirects=True) as client:
            clients = _paged_records(client, profile, contract, "clients", headers, is_cancelled, on_page)
            plans = _paged_records(client, profile, contract, "treatment_plans", headers, is_cancelled, on_page)
            if sync_job_id:
                reconcile_sync_patients(
                    db,
                    sync_job_id,
                    _client_lifecycles(clients),
                    len(clients) < min(contract.payload.pagination.maximum_records, MAX_SYNC_ROWS),
                    datetime.now(timezone.utc).isoformat(),
                )
            imported, skipped = _save_client_aggregates(db, client, profile, actor, contract, clients, plans, headers, is_cancelled)
    except (httpx.HTTPError, ValueError) as exc:
        raise AllevaSyncError("Alleva read-only treatment-plan sync did not complete successfully.") from exc
    return AllevaSyncResult(imported_patient_count=imported, skipped_plan_count=skipped)


def _oauth_token(profile: AppSetting, contract: ApprovedAllevaContract, is_cancelled: Callable[[], bool]) -> str:
    if is_cancelled():
        raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled before OAuth.")
    if not profile.api_client_secret:
        raise AllevaSyncError("Encrypted Alleva client secret is not configured.")
    _, token = request_client_credentials(
        token_url=contract.payload.oauth.token_url,
        client_id=profile.api_client_id,
        client_secret=decrypt_text_secret(profile.api_client_secret),
        scope=contract.payload.oauth.scope,
        token_auth_style=contract.payload.oauth.token_auth_style,
        timeout_seconds=profile.emr_api_timeout_seconds,
    )
    if is_cancelled():
        raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled after OAuth.")
    if not token:
        raise AllevaSyncError("OAuth verification failed before treatment-plan sync could start.")
    return token


def _paged_records(client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str], is_cancelled: Callable[[], bool], on_page: Callable[[str, int, str, str, int], None] | None) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    offset = 0
    pagination = contract.payload.pagination
    page_size = pagination.maximum_page_size
    limit = min(pagination.maximum_records, MAX_SYNC_ROWS)
    seen_pages: set[str] = set()
    while len(records) < limit:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        response = _get_with_retry(client, urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, endpoint_key).lstrip("/")), {pagination.limit_parameter: min(page_size, limit - len(records)), pagination.offset_parameter: offset}, headers, is_cancelled, contract.payload.rate_limit.retry_after_seconds)
        response_size = int(response.headers.get("content-length", "0"))
        if response_size > pagination.maximum_response_bytes:
            raise ValueError("API page exceeded the approved response-size limit.")
        page = _records(response.json())
        page_hash = hashlib.sha256(json.dumps(page, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if page_hash in seen_pages:
            raise ValueError("Approved endpoint returned a repeated page.")
        seen_pages.add(page_hash)
        records.extend(page)
        if on_page:
            on_page(endpoint_key, offset, hashlib.sha256(str(offset).encode("utf-8")).hexdigest(), page_hash, len(page))
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
    contract: ApprovedAllevaContract,
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
        if not patient_id or _client_lifecycle(client_payload) != "active":
            continue
        plan = _plan_for_patient(plans, patient_id)
        if plan is None:
            skipped += 1
            continue
        plan_id = _first_text(plan, "id", "treatmentPlanId")
        detail = _plan_detail(client, profile, contract, plan_id, headers, is_cancelled) if plan_id else plan
        aggregate = _aggregate_from_payload(patient_id, client_payload, plan, detail, plan_id)
        save_treatment_plan_aggregate(db, aggregate, actor)
        imported += 1
    return imported, skipped


def _client_lifecycles(clients: tuple[dict[str, object], ...]) -> dict[str, str]:
    return {
        patient_id: _client_lifecycle(payload)
        for payload in clients
        if (patient_id := _first_text(payload, "clientId", "id", "uniqueId", "mrn"))
    }


def _client_lifecycle(payload: dict[str, object]) -> str:
    status = str(payload.get("status", "")).strip().lower()
    if payload.get("isDeleted") is True or status == "deleted":
        return "deleted"
    if status in {"discharged", "closed"}:
        return "discharged"
    if payload.get("isActive") is False or status == "inactive":
        return "inactive"
    return "active"


def _plan_for_patient(plans: tuple[dict[str, object], ...], patient_id: str) -> dict[str, object] | None:
    for plan in plans:
        aliases = {_first_text(plan, "clientId", "client_id", "patientId", "patient_id")}
        if patient_id in aliases:
            return plan
    return None


def _plan_detail(client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, plan_id: str, headers: dict[str, str], is_cancelled: Callable[[], bool]) -> dict[str, object]:
    response = _get_with_retry(client, urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, "treatment_plan_detail", plan_id=plan_id).lstrip("/")), None, headers, is_cancelled, contract.payload.rate_limit.retry_after_seconds)
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected an API treatment-plan detail object.")
    diagnoses = _endpoint_records(client, profile, contract, "diagnoses", headers, is_cancelled, plan_id=plan_id)
    reviews = _endpoint_records(client, profile, contract, "reviews", headers, is_cancelled, plan_id=plan_id)
    payload["diagnoses"] = diagnoses or payload.get("diagnoses", [])
    if reviews:
        review_id = _first_text(reviews[0], "id", "reviewId")
        if review_id:
            payload["review_detail"] = _endpoint_json(client, profile, contract, "review_detail", headers, is_cancelled, plan_id=plan_id, review_id=review_id)
    return payload


def _endpoint_path(contract: ApprovedAllevaContract, endpoint_key: str, **values: str) -> str:
    return contract.payload.endpoints[endpoint_key].path.format(**values)


def _endpoint_json(client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str], is_cancelled: Callable[[], bool], **values: str) -> object:
    response = _get_with_retry(client, urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, endpoint_key, **values).lstrip("/")), None, headers, is_cancelled, contract.payload.rate_limit.retry_after_seconds)
    return response.json()


def _get_with_retry(client: httpx.Client, url: str, params: dict[str, int] | None, headers: dict[str, str], is_cancelled: Callable[[], bool], retry_after_seconds: int) -> httpx.Response:
    for attempt in range(3):
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        response = client.get(url, params=params, headers=headers)
        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
            return response
        if attempt == 2:
            response.raise_for_status()
        _wait_for_retry(min(retry_after_seconds, 2), is_cancelled)
    raise AllevaSyncError("Approved API request retry budget was exhausted.")


def _wait_for_retry(delay_seconds: int, is_cancelled: Callable[[], bool]) -> None:
    deadline = time.monotonic() + max(delay_seconds, 0)
    while time.monotonic() < deadline:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled during retry backoff.")
        time.sleep(min(0.1, deadline - time.monotonic()))


def _endpoint_records(client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str], is_cancelled: Callable[[], bool], **values: str) -> list[dict[str, object]]:
    return _records(_endpoint_json(client, profile, contract, endpoint_key, headers, is_cancelled, **values))


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
