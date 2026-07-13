from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Final, assert_never
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.models import AppSetting, User
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields
from app.v2.services.alleva_contracts import (
    ApprovedAllevaContract,
    SyncCheckpointPage,
    SyncImportProvenance,
    load_sync_checkpoint_pages,
    reconcile_sync_patients,
    sync_import_provenance,
)
from app.v2.services.oauth_connectivity import request_client_credentials
from app.v2.services.secure_storage import decrypt_text_secret
from app.v2.services.treatment_plan_store import (
    TreatmentPlanSaveDisposition,
    save_treatment_plan_aggregate_with_disposition,
)

MAX_SYNC_ROWS: Final = 5_000
DEFAULT_ENDPOINT_FIELD_MAPPINGS: Final = {
    "clients": {
        "client_id": "clientId", "lifecycle_status": "status", "deleted": "isDeleted",
        "active": "isActive", "level_of_care": "levelOfCare", "admission_date": "admissionDate",
    },
    "treatment_plans": {"client_id": "clientId", "plan_id": "id", "due_date": "nextReviewDue"},
    "treatment_plan_detail": {
        "reason_for_admission": "reasonForAdmission", "initial_client_needs": "initialClientNeeds",
        "family_education_needs": "familyEducationNeeds", "signature_date": "staffSignatureDate",
        "last_modified": "lastModified", "problem_description": "problems.problemDescription",
        "diagnosis_description": "diagnoses.diagnosisDescription", "icd10_code": "diagnoses.icd10Code",
        "behavioral_definition": "behavioralDefinitions.behavioralDefinition", "goal_description": "goals.goalDescription",
        "objective_description": "objectives.objectiveDescription", "intervention_description": "interventions.interventionDescription",
    },
    "diagnoses": {"description": "diagnosisDescription", "icd10_code": "icd10Code"},
    "reviews": {"review_id": "id"},
    "review_detail": {"review_date": "reviewDate", "signature_date": "signatureDate"},
}


class AllevaSyncError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class AllevaSyncCancelled(AllevaSyncError):
    pass


@dataclass(slots=True)
class ApprovedRequestRateLimiter:
    requests_per_minute: int
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last_request_at: float | None = None

    def acquire(self, is_cancelled: Callable[[], bool]) -> None:
        interval = 60.0 / self.requests_per_minute
        if self._last_request_at is not None:
            deadline = self._last_request_at + interval
            while self.clock() < deadline:
                if is_cancelled():
                    raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled while waiting for the approved rate limit.")
                remaining_delay = deadline - self.clock()
                if remaining_delay > 0.0:
                    self.sleep(min(0.1, remaining_delay))
        self._last_request_at = self.clock()


@dataclass(frozen=True, slots=True)
class AllevaSyncResult:
    imported_patient_count: int
    skipped_plan_count: int
    created_treatment_plan_count: int
    updated_treatment_plan_count: int
    unchanged_treatment_plan_count: int
    updated_treatment_plan_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyncImportSummary:
    created_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    updated_plan_ids: tuple[str, ...]


def run_treatment_plan_sync(
    db: Session,
    profile: AppSetting,
    actor: User,
    contract: ApprovedAllevaContract,
    is_cancelled: Callable[[], bool] = lambda: False,
    on_page: Callable[[str, int, str, str, tuple[dict[str, object], ...]], None] | None = None,
    sync_job_id: str | None = None,
    resumed_from_job_id: str | None = None,
) -> AllevaSyncResult:
    if is_cancelled():
        raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled before it started.")
    token = _oauth_token(profile, contract, is_cancelled)
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=max(1, min(profile.emr_api_timeout_seconds, 60)), follow_redirects=True) as client:
            rate_limiter = ApprovedRequestRateLimiter(contract.payload.rate_limit.maximum_requests_per_minute)
            client_checkpoints = load_sync_checkpoint_pages(db, resumed_from_job_id, "clients") if resumed_from_job_id else ()
            plan_checkpoints = load_sync_checkpoint_pages(db, resumed_from_job_id, "treatment_plans") if resumed_from_job_id else ()
            clients = _paged_records(client, profile, contract, "clients", headers, is_cancelled, on_page, client_checkpoints, rate_limiter)
            plans = _paged_records(client, profile, contract, "treatment_plans", headers, is_cancelled, on_page, plan_checkpoints, rate_limiter)
            if sync_job_id:
                reconcile_sync_patients(
                    db,
                    sync_job_id,
                    _client_lifecycles(clients, contract),
                    len(clients) < min(contract.payload.pagination.maximum_records, MAX_SYNC_ROWS),
                    datetime.now(timezone.utc).isoformat(),
                )
            provenance = sync_import_provenance(db, sync_job_id) if sync_job_id else None
            summary = _save_client_aggregates(
                db, client, profile, actor, contract, clients, plans, headers, is_cancelled, provenance, rate_limiter,
            )
    except (httpx.HTTPError, ValueError) as exc:
        raise AllevaSyncError("Alleva read-only treatment-plan sync did not complete successfully.") from exc
    return AllevaSyncResult(
        imported_patient_count=summary.created_count + summary.updated_count + summary.unchanged_count,
        skipped_plan_count=summary.skipped_count,
        created_treatment_plan_count=summary.created_count,
        updated_treatment_plan_count=summary.updated_count,
        unchanged_treatment_plan_count=summary.unchanged_count,
        updated_treatment_plan_ids=summary.updated_plan_ids,
    )


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


def _paged_records(
    client: httpx.Client,
    profile: AppSetting,
    contract: ApprovedAllevaContract,
    endpoint_key: str,
    headers: dict[str, str],
    is_cancelled: Callable[[], bool],
    on_page: Callable[[str, int, str, str, tuple[dict[str, object], ...]], None] | None,
    checkpoint_pages: tuple[SyncCheckpointPage, ...] = (),
    rate_limiter: ApprovedRequestRateLimiter | None = None,
) -> tuple[dict[str, object], ...]:
    records = [record for checkpoint in checkpoint_pages for record in checkpoint.records]
    pagination = contract.payload.pagination
    page_size = pagination.maximum_page_size
    limit = min(pagination.maximum_records, MAX_SYNC_ROWS)
    seen_pages = {checkpoint.response_shape_sha256 for checkpoint in checkpoint_pages}
    offset = 0
    if checkpoint_pages:
        latest_checkpoint = checkpoint_pages[-1]
        if len(latest_checkpoint.records) < page_size:
            return tuple(records[:limit])
        offset = latest_checkpoint.page_number + len(latest_checkpoint.records)
    while len(records) < limit:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        response = _get_with_retry(
            client,
            urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, endpoint_key).lstrip("/")),
            _endpoint_request_parameters(contract, endpoint_key, min(page_size, limit - len(records)), offset),
            headers,
            is_cancelled,
            contract.payload.rate_limit.retry_after_seconds,
            rate_limiter,
            contract.payload.pagination.maximum_response_bytes,
        )
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
            on_page(endpoint_key, offset, hashlib.sha256(str(offset).encode("utf-8")).hexdigest(), page_hash, tuple(page))
        if len(page) < page_size:
            break
        offset += len(page)
    return tuple(records[:limit])


def _endpoint_request_parameters(
    contract: ApprovedAllevaContract,
    endpoint_key: str,
    limit: int,
    offset: int,
) -> dict[str, str | int]:
    endpoint_parameters = contract.payload.endpoints[endpoint_key].parameters
    request_parameters: dict[str, str | int] = {
        endpoint_parameters.get("limit", contract.payload.pagination.limit_parameter): limit,
        endpoint_parameters.get("offset", contract.payload.pagination.offset_parameter): offset,
    }
    request_parameters.update(
        {name: value for name, value in endpoint_parameters.items() if name not in {"limit", "offset"}}
    )
    return request_parameters


def _mapped_text(
    payload: dict[str, object],
    contract: ApprovedAllevaContract,
    endpoint_key: str,
    semantic_field: str,
) -> str:
    endpoint = contract.payload.endpoints[endpoint_key]
    default = DEFAULT_ENDPOINT_FIELD_MAPPINGS.get(endpoint_key, {}).get(semantic_field, semantic_field)
    value = payload.get(endpoint.field_mappings.get(semantic_field, default))
    return value.strip() if isinstance(value, str) else ""


def _mapped_nested_text(
    payload: dict[str, object], contract: ApprovedAllevaContract, endpoint_key: str, semantic_field: str,
) -> str:
    endpoint = contract.payload.endpoints[endpoint_key]
    default = DEFAULT_ENDPOINT_FIELD_MAPPINGS.get(endpoint_key, {}).get(semantic_field, semantic_field)
    path = endpoint.field_mappings.get(semantic_field, default).split(".")
    current: object = payload
    for part in path:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            current = next((item for item in current if isinstance(item, dict)), None)
            current = current.get(part) if isinstance(current, dict) else None
        else:
            return ""
    return current.strip() if isinstance(current, str) else ""


def _mapped_collection_text(
    payload: dict[str, object], contract: ApprovedAllevaContract, endpoint_key: str, semantic_field: str, collection: str,
) -> str:
    values = payload.get(collection)
    if not isinstance(values, list):
        return ""
    endpoint = contract.payload.endpoints[endpoint_key]
    default = DEFAULT_ENDPOINT_FIELD_MAPPINGS.get(endpoint_key, {}).get(semantic_field, semantic_field)
    field_name = endpoint.field_mappings.get(semantic_field, default)
    for item in values:
        if isinstance(item, dict):
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


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
    sync_provenance: SyncImportProvenance | None,
    rate_limiter: ApprovedRequestRateLimiter,
) -> SyncImportSummary:
    created = 0
    updated = 0
    unchanged = 0
    skipped = 0
    updated_plan_ids: list[str] = []
    for client_payload in clients:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        patient_id = _mapped_text(client_payload, contract, "clients", "client_id")
        if not patient_id or _client_lifecycle(client_payload, contract) != "active":
            continue
        patient_plans = _plans_for_patient(plans, patient_id, contract)
        if not patient_plans:
            skipped += 1
            continue
        for plan in patient_plans:
            plan_id = _mapped_text(plan, contract, "treatment_plans", "plan_id")
            detail = _plan_detail(client, profile, contract, plan_id, headers, is_cancelled, rate_limiter) if plan_id else plan
            aggregate = _aggregate_from_payload(patient_id, client_payload, plan, detail, plan_id, contract)
            saved = save_treatment_plan_aggregate_with_disposition(
                db,
                aggregate,
                actor,
                sync_provenance=sync_provenance,
            )
            match saved.disposition:
                case TreatmentPlanSaveDisposition.CREATED:
                    created += 1
                case TreatmentPlanSaveDisposition.UPDATED:
                    updated += 1
                    updated_plan_ids.append(saved.stored_plan.plan_id)
                case TreatmentPlanSaveDisposition.UNCHANGED:
                    unchanged += 1
                case unreachable:
                    assert_never(unreachable)
    return SyncImportSummary(created, updated, unchanged, skipped, tuple(updated_plan_ids))


def _client_lifecycles(clients: tuple[dict[str, object], ...], contract: ApprovedAllevaContract) -> dict[str, str]:
    return {
        patient_id: _client_lifecycle(payload, contract)
        for payload in clients
        if (patient_id := _mapped_text(payload, contract, "clients", "client_id"))
    }


def _client_lifecycle(payload: dict[str, object], contract: ApprovedAllevaContract) -> str:
    status = _mapped_text(payload, contract, "clients", "lifecycle_status").lower()
    deleted_key = contract.payload.endpoints["clients"].field_mappings.get("deleted", "isDeleted")
    active_key = contract.payload.endpoints["clients"].field_mappings.get("active", "isActive")
    if payload.get(deleted_key) is True or status == "deleted":
        return "deleted"
    if status in {"discharged", "closed"}:
        return "discharged"
    if payload.get(active_key) is False or status == "inactive":
        return "inactive"
    return "active"


def _plans_for_patient(
    plans: tuple[dict[str, object], ...], patient_id: str, contract: ApprovedAllevaContract,
) -> tuple[dict[str, object], ...]:
    return tuple(
        plan
        for plan in plans
        if patient_id == _mapped_text(plan, contract, "treatment_plans", "client_id")
    )


def _plan_detail(
    client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, plan_id: str, headers: dict[str, str],
    is_cancelled: Callable[[], bool], rate_limiter: ApprovedRequestRateLimiter,
) -> dict[str, object]:
    response = _get_with_retry(client, urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, "treatment_plan_detail", plan_id=plan_id).lstrip("/")), None, headers, is_cancelled, contract.payload.rate_limit.retry_after_seconds, rate_limiter)
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected an API treatment-plan detail object.")
    diagnoses = _endpoint_records(client, profile, contract, "diagnoses", headers, is_cancelled, rate_limiter, plan_id=plan_id)
    reviews = _endpoint_records(client, profile, contract, "reviews", headers, is_cancelled, rate_limiter, plan_id=plan_id)
    payload["diagnoses"] = diagnoses or payload.get("diagnoses", [])
    if reviews:
        review_id = _mapped_text(reviews[0], contract, "reviews", "review_id")
        if review_id:
            payload["review_detail"] = _endpoint_json(client, profile, contract, "review_detail", headers, is_cancelled, rate_limiter, plan_id=plan_id, review_id=review_id)
    return payload


def _endpoint_path(contract: ApprovedAllevaContract, endpoint_key: str, **values: str) -> str:
    return contract.payload.endpoints[endpoint_key].path.format(**values)


def _endpoint_json(
    client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str],
    is_cancelled: Callable[[], bool], rate_limiter: ApprovedRequestRateLimiter, **values: str,
) -> object:
    response = _get_with_retry(client, urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, endpoint_key, **values).lstrip("/")), None, headers, is_cancelled, contract.payload.rate_limit.retry_after_seconds, rate_limiter, contract.payload.pagination.maximum_response_bytes)
    return response.json()


def _get_with_retry(client: httpx.Client, url: str, params: dict[str, str | int] | None, headers: dict[str, str], is_cancelled: Callable[[], bool], retry_after_seconds: int, rate_limiter: ApprovedRequestRateLimiter | None = None, maximum_response_bytes: int = 5 * 1024 * 1024) -> httpx.Response:
    for attempt in range(3):
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        if rate_limiter:
            rate_limiter.acquire(is_cancelled)
        response = get_bounded(
            client,
            url,
            maximum_bytes=maximum_response_bytes,
            params=params,
            headers=headers,
        )
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


def _endpoint_records(
    client: httpx.Client, profile: AppSetting, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str],
    is_cancelled: Callable[[], bool], rate_limiter: ApprovedRequestRateLimiter, **values: str,
) -> list[dict[str, object]]:
    return _records(_endpoint_json(client, profile, contract, endpoint_key, headers, is_cancelled, rate_limiter, **values))


def _aggregate_from_payload(
    patient_id: str,
    client: dict[str, object],
    plan: dict[str, object],
    detail: dict[str, object],
    plan_id: str,
    contract: ApprovedAllevaContract,
) -> TreatmentPlanAggregate:
    parsed = ParsedManualFields(
        patient_id=patient_id,
        patient_id_correction_applied=False,
        level_of_care=_mapped_text(client, contract, "clients", "level_of_care") or "Unknown",
        admission_date=_mapped_text(client, contract, "clients", "admission_date") or "Unknown",
        due_date=_mapped_text(plan, contract, "treatment_plans", "due_date") or "Unknown",
        reason_for_admission=_mapped_text(detail, contract, "treatment_plan_detail", "reason_for_admission"),
        initial_client_needs=_mapped_text(detail, contract, "treatment_plan_detail", "initial_client_needs"),
        family_education_needs=_mapped_text(detail, contract, "treatment_plan_detail", "family_education_needs"),
        problem_description=_mapped_nested_text(detail, contract, "treatment_plan_detail", "problem_description"),
        diagnosis_description=_mapped_collection_text(detail, contract, "diagnoses", "description", "diagnoses"),
        icd10_code=_mapped_collection_text(detail, contract, "diagnoses", "icd10_code", "diagnoses"),
        behavioral_definition=_mapped_nested_text(detail, contract, "treatment_plan_detail", "behavioral_definition"),
        goal_description=_mapped_nested_text(detail, contract, "treatment_plan_detail", "goal_description"),
        objective_description=_mapped_nested_text(detail, contract, "treatment_plan_detail", "objective_description"),
        intervention_description=_mapped_nested_text(detail, contract, "treatment_plan_detail", "intervention_description"),
        signature_datetime=_mapped_text(detail, contract, "treatment_plan_detail", "signature_date"),
        raw_text=f"{patient_id}|{plan_id}|{_mapped_text(detail, contract, 'treatment_plan_detail', 'last_modified')}",
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
        "plan_id": plan_id,
        "source_mode": "alleva_rest_api",
        "observed_fields": tuple(field.model_copy(update={"source_endpoint": "Alleva REST"}) for field in aggregate.content_snapshot.observed_fields),
    })
    evidence_coverage = aggregate.evidence_coverage_summary.model_copy(update={"plan_id": plan_id})
    return aggregate.model_copy(
        update={
            "source_mode": "alleva_rest_api",
            "status_label": "Alleva REST sync",
            "treatment_plans": ({"plan_id": plan_id, "is_active": True, "source": "alleva_rest_api"},),
            "active_treatment_plans": ({"plan_id": plan_id, "is_active": True},),
            "latest_created_active_plan": {"plan_id": plan_id, "label": "Alleva REST treatment plan"},
            "current_plan_selection_reason": "Latest mapped active Alleva treatment plan",
            "treatment_review_data_status": "available" if isinstance(detail.get("review_detail"), dict) else "not_requested",
            "treatment_reviews": (detail["review_detail"],) if isinstance(detail.get("review_detail"), dict) else (),
            "source_evidence": evidence,
            "criteria_results": criteria,
            "content_snapshot": snapshot,
            "evidence_coverage_summary": evidence_coverage,
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
from app.v2.services.bounded_http import get_bounded
