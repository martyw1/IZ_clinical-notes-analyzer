from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import json
from threading import Lock
import time
from datetime import datetime, timezone
from typing import Final, assert_never
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from sqlalchemy.orm import Session

from app.v2.domain.schemas import (
    JsonValue,
    TreatmentPlanAggregate,
    TreatmentPlanGoal,
    TreatmentPlanIntervention,
    TreatmentPlanObjective,
    TreatmentPlanObservedField,
    TreatmentPlanProblem,
    TreatmentPlanSignatureMetadata,
)
from app.v2.models import AppSetting, User
from app.v2.services.bounded_http import ResponseTooLarge
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields
from app.v2.services.alleva_contracts import (
    ApprovedAllevaContract,
    SyncCheckpointPage,
    SyncImportProvenance,
    load_sync_checkpoint_pages,
    sync_import_provenance,
)
from app.v2.services.alleva_patient_identity import (
    AllevaPatientObservation,
    reconcile_sync_patients,
)
from app.v2.services.oauth_connectivity import request_client_credentials
from app.v2.services.alleva_protocol import (
    DEFAULT_ALLEVA_API_VERSION,
    DEFAULT_TREATMENT_PLAN_START_DATE,
    AllevaReadProtocol,
    collection_parameters,
    collection_records,
    detail_parameters,
    read_headers,
)
from app.v2.services.secure_storage import decrypt_api_client_id, decrypt_text_secret
from app.v2.services.patient_snapshot_store import (
    PatientSourceSnapshotInput,
    persist_patient_source_snapshots,
)
from app.v2.services.treatment_plan_store import (
    TreatmentPlanSaveDisposition,
    save_treatment_plan_aggregate_with_disposition,
)

MAX_SYNC_ROWS: Final = 5_000
MAX_SYNC_HTTP_WORKERS: Final = 8
UNLINKED_PATIENT_KEY_PREFIX: Final = "unlinked-"
UNLINKED_PATIENT_LABEL: Final = "Not linked to an MRN"
DEFAULT_ENDPOINT_FIELD_MAPPINGS: Final = {
    "clients": {
        "client_id": "clientId", "mrn": "mrn", "lifecycle_status": "status", "deleted": "isDeleted",
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
    _lock: Lock = field(default_factory=Lock)

    def acquire(self, is_cancelled: Callable[[], bool]) -> None:
        with self._lock:
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
    failed_detail_count: int
    updated_treatment_plan_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyncImportSummary:
    created_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    failed_detail_count: int
    updated_plan_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlanImportCandidate:
    patient_id: str
    client_payload: dict[str, object]
    plan_payload: dict[str, object]
    plan_id: str
    source_patient_id: str | None
    linked_to_mrn: bool


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
    protocol = AllevaReadProtocol(
        profile.alleva_api_version,
        profile.alleva_treatment_plan_start_date,
    )
    headers = read_headers(bearer_token=token, protocol=protocol)
    try:
        with httpx.Client(timeout=max(1, min(profile.emr_api_timeout_seconds, 60)), follow_redirects=False) as client:
            rate_limiter = ApprovedRequestRateLimiter(contract.payload.rate_limit.maximum_requests_per_minute)
            client_checkpoints = load_sync_checkpoint_pages(db, resumed_from_job_id, "clients") if resumed_from_job_id else ()
            clients = _paged_records(client, profile, contract, "clients", headers, is_cancelled, on_page, client_checkpoints, rate_limiter)
            plan_checkpoints = (
                load_sync_checkpoint_pages(db, resumed_from_job_id, "treatment_plans")
                if resumed_from_job_id
                else ()
            )
            plans = _paged_records(
                client,
                profile,
                contract,
                "treatment_plans",
                headers,
                is_cancelled,
                on_page,
                plan_checkpoints,
                rate_limiter,
            )
            reconciled_at = datetime.now(timezone.utc).isoformat()
            reconcile_sync_patients(
                db,
                sync_job_id,
                _client_observations(clients, contract),
                _client_source_ids(clients, contract),
                len(clients) < min(contract.payload.pagination.maximum_records, MAX_SYNC_ROWS),
                reconciled_at,
            )
            provenance = sync_import_provenance(db, sync_job_id) if sync_job_id else None
            persist_patient_source_snapshots(
                db,
                _client_snapshot_inputs(clients, contract),
                reconciled_at,
                provenance,
            )
            db.commit()
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
        failed_detail_count=summary.failed_detail_count,
        updated_treatment_plan_ids=summary.updated_plan_ids,
    )


def _oauth_token(profile: AppSetting, contract: ApprovedAllevaContract, is_cancelled: Callable[[], bool]) -> str:
    if is_cancelled():
        raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled before OAuth.")
    if not profile.api_client_secret:
        raise AllevaSyncError("Encrypted Alleva client secret is not configured.")
    _, token = request_client_credentials(
        token_url=contract.payload.oauth.token_url,
        client_id=decrypt_api_client_id(profile.api_client_id),
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
    *,
    additional_parameters: dict[str, str | int] | None = None,
    checkpoint_endpoint_key: str | None = None,
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
        requested_page_size = min(page_size, limit - len(records))
        response = _get_with_retry(
            client,
            urljoin(f"{profile.api_base_url.rstrip('/')}/", _endpoint_path(contract, endpoint_key).lstrip("/")),
            _endpoint_request_parameters(
                contract,
                endpoint_key,
                requested_page_size,
                offset,
                protocol=AllevaReadProtocol(
                    getattr(profile, "alleva_api_version", DEFAULT_ALLEVA_API_VERSION),
                    getattr(
                        profile,
                        "alleva_treatment_plan_start_date",
                        DEFAULT_TREATMENT_PLAN_START_DATE,
                    ),
                ),
                additional_parameters=additional_parameters,
            ),
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
        vendor_exceeded_requested_page = len(page) > requested_page_size
        if vendor_exceeded_requested_page:
            if len(records) + len(page) > limit:
                raise ValueError("Approved endpoint returned more records than the bounded collection permits.")
        page_hash = hashlib.sha256(json.dumps(page, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if page_hash in seen_pages:
            raise ValueError("Approved endpoint returned a repeated page.")
        seen_pages.add(page_hash)
        records.extend(page)
        if on_page:
            on_page(checkpoint_endpoint_key or endpoint_key, offset, hashlib.sha256(str(offset).encode("utf-8")).hexdigest(), page_hash, tuple(page))
        if vendor_exceeded_requested_page:
            break
        if len(page) < requested_page_size:
            break
        offset += requested_page_size
    return tuple(records[:limit])


def _endpoint_request_parameters(
    contract: ApprovedAllevaContract,
    endpoint_key: str,
    limit: int,
    offset: int,
    additional_parameters: dict[str, str | int] | None = None,
    *,
    protocol: AllevaReadProtocol | None = None,
) -> dict[str, str | int]:
    endpoint_parameters = contract.payload.endpoints[endpoint_key].parameters
    additional = dict(additional_parameters or {})
    api_version = str(additional.pop("api_version", DEFAULT_ALLEVA_API_VERSION))
    treatment_plan_start_date = str(
        additional.pop("start_date", DEFAULT_TREATMENT_PLAN_START_DATE)
    )
    effective_protocol = protocol or AllevaReadProtocol(api_version, treatment_plan_start_date)
    client_id_value = additional.pop("client_id", None)
    request_parameters = collection_parameters(
        endpoint_parameters=endpoint_parameters,
        limit_parameter=contract.payload.pagination.limit_parameter,
        offset_parameter=contract.payload.pagination.offset_parameter,
        limit=limit,
        cursor=offset,
        protocol=effective_protocol,
        include_start_date=endpoint_key == "treatment_plans",
        client_id=str(client_id_value) if client_id_value is not None else None,
    )
    for semantic_name, value in additional.items():
        request_parameters[endpoint_parameters.get(semantic_name, semantic_name)] = value
    return request_parameters


def _mapped_text(
    payload: dict[str, object],
    contract: ApprovedAllevaContract,
    endpoint_key: str,
    semantic_field: str,
) -> str:
    endpoint = contract.payload.endpoints[endpoint_key]
    default = DEFAULT_ENDPOINT_FIELD_MAPPINGS.get(endpoint_key, {}).get(semantic_field, semantic_field)
    path = endpoint.field_mappings.get(semantic_field, default).split(".")
    value: object = payload
    for part in path:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


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
    return collection_records(payload)


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
    failed_details = 0
    updated_plan_ids: list[str] = []
    candidates: list[PlanImportCandidate] = []
    api_base_url = str(profile.api_base_url)
    clients_by_source = {
        source_patient_id: (mrn, client_payload)
        for client_payload in clients
        if (source_patient_id := _mapped_text(client_payload, contract, "clients", "client_id"))
        and (mrn := _mapped_text(client_payload, contract, "clients", "mrn"))
    }
    for plan in plans:
        if is_cancelled():
            raise AllevaSyncCancelled("Alleva treatment-plan sync was cancelled.")
        plan_id = _mapped_text(plan, contract, "treatment_plans", "plan_id")
        source_patient_id = _plan_source_patient_id(plan, contract)
        if not plan_id:
            skipped += 1
            continue
        if not source_patient_id:
            candidates.append(
                PlanImportCandidate(
                    _unlinked_patient_key(f"treatment-plan:{plan_id}"),
                    {},
                    plan,
                    plan_id,
                    None,
                    False,
                )
            )
            continue
        patient_identity = clients_by_source.get(source_patient_id)
        if patient_identity is None:
            candidates.append(
                PlanImportCandidate(
                    _unlinked_patient_key(source_patient_id),
                    {},
                    plan,
                    plan_id,
                    source_patient_id,
                    False,
                )
            )
            continue
        mrn, client_payload = patient_identity
        candidates.append(
            PlanImportCandidate(mrn, client_payload, plan, plan_id, source_patient_id, True)
        )

    def fetch_detail(candidate: PlanImportCandidate) -> dict[str, object]:
        return _plan_detail(
            client,
            api_base_url,
            contract,
            candidate.plan_id,
            headers,
            is_cancelled,
            rate_limiter,
            api_version=profile.alleva_api_version,
        )

    details: list[dict[str, object] | None] = [None] * len(candidates)
    if candidates:
        worker_count = min(MAX_SYNC_HTTP_WORKERS, len(candidates))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="alleva-plan-detail") as executor:
            futures = tuple(executor.submit(fetch_detail, candidate) for candidate in candidates)
            for index, future in enumerate(futures):
                try:
                    details[index] = future.result()
                except (httpx.HTTPError, json.JSONDecodeError, ValueError, ResponseTooLarge):
                    failed_details += 1

    for candidate, detail in zip(candidates, details, strict=True):
        if detail is None:
            detail = candidate.plan_payload
        detail_plan_id = _mapped_text(detail, contract, "treatment_plans", "plan_id")
        detail_source_patient_id = _plan_source_patient_id(detail, contract)
        list_source_patient_id = _plan_source_patient_id(candidate.plan_payload, contract)
        if (
            (detail_plan_id and detail_plan_id != candidate.plan_id)
            or (
                detail_source_patient_id
                and list_source_patient_id
                and detail_source_patient_id != list_source_patient_id
            )
        ):
            failed_details += 1
            continue
        effective_source_patient_id = list_source_patient_id or detail_source_patient_id
        if not list_source_patient_id and effective_source_patient_id:
            patient_identity = clients_by_source.get(effective_source_patient_id)
            if patient_identity is None:
                candidate = PlanImportCandidate(
                    _unlinked_patient_key(effective_source_patient_id),
                    {},
                    candidate.plan_payload,
                    candidate.plan_id,
                    effective_source_patient_id,
                    False,
                )
            else:
                mrn, client_payload = patient_identity
                candidate = PlanImportCandidate(
                    mrn,
                    client_payload,
                    candidate.plan_payload,
                    candidate.plan_id,
                    effective_source_patient_id,
                    True,
                )
        aggregate = _aggregate_from_payload(
            candidate.patient_id,
            candidate.client_payload,
            candidate.plan_payload,
            detail,
            candidate.plan_id,
            contract,
        )
        if not candidate.linked_to_mrn:
            aggregate = aggregate.model_copy(update={"patient_display_label": UNLINKED_PATIENT_LABEL})
        saved = save_treatment_plan_aggregate_with_disposition(
            db,
            aggregate,
            actor,
            sync_provenance=sync_provenance,
            source_patient_id=candidate.source_patient_id,
            lifecycle_state="active" if candidate.linked_to_mrn else "unlinked",
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
    return SyncImportSummary(created, updated, unchanged, skipped, failed_details, tuple(updated_plan_ids))


def _unlinked_patient_key(source_patient_id: str) -> str:
    digest = hashlib.sha256(source_patient_id.encode("utf-8")).hexdigest()[:24]
    return f"{UNLINKED_PATIENT_KEY_PREFIX}{digest}"


def _client_observations(
    clients: tuple[dict[str, object], ...],
    contract: ApprovedAllevaContract,
) -> tuple[AllevaPatientObservation, ...]:
    return tuple(
        AllevaPatientObservation(source_patient_id, mrn, _client_lifecycle(payload, contract))
        for payload in clients
        if (source_patient_id := _mapped_text(payload, contract, "clients", "client_id"))
        and (mrn := _mapped_text(payload, contract, "clients", "mrn"))
    )


def _client_snapshot_inputs(
    clients: tuple[dict[str, object], ...],
    contract: ApprovedAllevaContract,
) -> tuple[PatientSourceSnapshotInput, ...]:
    return tuple(
        PatientSourceSnapshotInput(
            mrn=mrn,
            source_patient_id=source_patient_id,
            source_system="alleva_rest_api",
            source_last_updated=_record_last_updated(payload),
            record=payload,
        )
        for payload in clients
        if (source_patient_id := _mapped_text(payload, contract, "clients", "client_id"))
        and (mrn := _mapped_text(payload, contract, "clients", "mrn"))
    )


def _client_source_ids(
    clients: tuple[dict[str, object], ...],
    contract: ApprovedAllevaContract,
) -> frozenset[str]:
    return frozenset(
        source_patient_id
        for payload in clients
        if (source_patient_id := _mapped_text(payload, contract, "clients", "client_id"))
    )


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


def _record_last_updated(payload: dict[str, object]) -> str:
    for key in (
        "updatedAt", "lastUpdated", "lastUpdatedDate", "modifiedAt", "modifiedDate",
        "dateUpdated", "createdAt",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _plan_belongs_to_patient(
    plan: dict[str, object],
    patient_id: str,
    contract: ApprovedAllevaContract,
) -> bool:
    return _plan_source_patient_id(plan, contract) == patient_id


def _plan_source_patient_id(
    plan: dict[str, object],
    contract: ApprovedAllevaContract,
) -> str:
    observed_ids: list[str] = []
    invalid_reference = False

    mapped_id = _mapped_text(plan, contract, "treatment_plans", "client_id")
    if mapped_id:
        observed_ids.append(mapped_id)
    mapped_reference = _mapped_text(plan, contract, "treatment_plans", "client_reference")
    if mapped_reference:
        reference_id = _patient_id_from_reference(mapped_reference)
        if reference_id:
            observed_ids.append(reference_id)
        else:
            invalid_reference = True

    raw_client = plan.get("client")
    if isinstance(raw_client, str) and raw_client.strip():
        reference_id = _patient_id_from_reference(raw_client)
        if reference_id:
            observed_ids.append(reference_id)
        else:
            invalid_reference = True
    elif isinstance(raw_client, dict):
        nested_id = _identifier_text(raw_client.get("id"))
        if nested_id:
            observed_ids.append(nested_id)
        for key in ("route", "href"):
            reference = raw_client.get(key)
            if isinstance(reference, str) and reference.strip():
                reference_id = _patient_id_from_reference(reference)
                if reference_id:
                    observed_ids.append(reference_id)
                else:
                    invalid_reference = True

    if not observed_ids or invalid_reference or any(value != observed_ids[0] for value in observed_ids):
        return ""
    return observed_ids[0]


def _identifier_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _patient_id_from_reference(reference: str) -> str:
    parsed = urlsplit(reference)
    parts = [unquote(part).strip() for part in parsed.path.strip("/").split("/") if part.strip()]
    if len(parts) >= 2 and parts[-2].lower() == "clients":
        return parts[-1]
    return ""


def _plan_detail(
    client: httpx.Client, api_base_url: str, contract: ApprovedAllevaContract, plan_id: str, headers: dict[str, str],
    is_cancelled: Callable[[], bool], rate_limiter: ApprovedRequestRateLimiter,
    *, api_version: str = DEFAULT_ALLEVA_API_VERSION,
) -> dict[str, object]:
    protocol = AllevaReadProtocol(api_version=api_version)
    response = _get_with_retry(
        client,
        urljoin(f"{api_base_url.rstrip('/')}/", _endpoint_path(contract, "treatment_plan_detail", plan_id=plan_id).lstrip("/")),
        detail_parameters(protocol),
        headers,
        is_cancelled,
        contract.payload.rate_limit.retry_after_seconds,
        rate_limiter,
        contract.payload.pagination.maximum_response_bytes,
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected an API treatment-plan detail object.")
    diagnoses = _endpoint_records(
        client, api_base_url, contract, "diagnoses", headers, is_cancelled, rate_limiter,
        api_version=api_version, plan_id=plan_id,
    )
    reviews_endpoint = contract.payload.endpoints["reviews"]
    reviews = []
    if "{plan_id}" in reviews_endpoint.path or "plan_id" in reviews_endpoint.field_mappings:
        reviews = _endpoint_records(
            client, api_base_url, contract, "reviews", headers, is_cancelled, rate_limiter,
            api_version=api_version, plan_id=plan_id,
        )
        if "{plan_id}" not in reviews_endpoint.path:
            reviews = [review for review in reviews if _mapped_text(review, contract, "reviews", "plan_id") == plan_id]
    payload["diagnoses"] = diagnoses or payload.get("diagnoses", [])
    if reviews:
        review_id = _mapped_text(reviews[0], contract, "reviews", "review_id")
        if review_id:
            payload["review_detail"] = _endpoint_json(
                client, api_base_url, contract, "review_detail", headers, is_cancelled, rate_limiter,
                api_version=api_version, plan_id=plan_id, review_id=review_id,
            )
    return payload


def _endpoint_path(contract: ApprovedAllevaContract, endpoint_key: str, **values: str) -> str:
    return contract.payload.endpoints[endpoint_key].path.format(**values)


def _endpoint_json(
    client: httpx.Client, api_base_url: str, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str],
    is_cancelled: Callable[[], bool], rate_limiter: ApprovedRequestRateLimiter,
    *, api_version: str = DEFAULT_ALLEVA_API_VERSION, **values: str,
) -> object:
    response = _get_with_retry(
        client,
        urljoin(f"{api_base_url.rstrip('/')}/", _endpoint_path(contract, endpoint_key, **values).lstrip("/")),
        detail_parameters(AllevaReadProtocol(api_version=api_version)),
        headers,
        is_cancelled,
        contract.payload.rate_limit.retry_after_seconds,
        rate_limiter,
        contract.payload.pagination.maximum_response_bytes,
    )
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
    client: httpx.Client, api_base_url: str, contract: ApprovedAllevaContract, endpoint_key: str, headers: dict[str, str],
    is_cancelled: Callable[[], bool], rate_limiter: ApprovedRequestRateLimiter,
    *, api_version: str = DEFAULT_ALLEVA_API_VERSION, **values: str,
) -> list[dict[str, object]]:
    return _records(
        _endpoint_json(
            client, api_base_url, contract, endpoint_key, headers, is_cancelled, rate_limiter,
            api_version=api_version, **values,
        )
    )


def _alleva_text(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    return ""


def _alleva_objects(payload: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _alleva_diagnoses(
    values: tuple[dict[str, object], ...],
    source_prefix: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        {
            "diagnosis_number": _alleva_text(value, "diagnosisNumber", "id") or str(index + 1),
            "diagnosis_description": _alleva_text(value, "description", "diagnosisDescription"),
            "icd10_code": _alleva_text(value, "icD10Code", "icd10Code", "code"),
            "is_primary": value.get("isPrimary") is True,
            "is_active": value.get("isActive") is not False,
            "source_json_path": f"{source_prefix}[{index}]",
        }
        for index, value in enumerate(values)
    )


def _alleva_interventions(
    values: tuple[dict[str, object], ...],
    source_prefix: str,
) -> tuple[TreatmentPlanIntervention, ...]:
    return tuple(
        TreatmentPlanIntervention(
            intervention_number=_alleva_text(value, "interventionNumber", "id") or str(index + 1),
            intervention_description=_alleva_text(value, "description", "interventionDescription"),
            source_json_path=f"{source_prefix}[{index}]",
            is_wiley=value.get("isWiley") is True,
            is_evidence_based=value.get("isEvidenceBased") is not False,
        )
        for index, value in enumerate(values)
    )


def _alleva_objectives(
    values: tuple[dict[str, object], ...],
    source_prefix: str,
) -> tuple[TreatmentPlanObjective, ...]:
    return tuple(
        TreatmentPlanObjective(
            objective_number=_alleva_text(value, "objectiveNumber", "id") or str(index + 1),
            objective_description=_alleva_text(value, "description", "objectiveDescription"),
            source_json_path=f"{source_prefix}[{index}]",
            interventions=_alleva_interventions(
                _alleva_objects(value, "interventions"),
                f"{source_prefix}[{index}].interventions",
            ),
        )
        for index, value in enumerate(values)
    )


def _alleva_goals(
    values: tuple[dict[str, object], ...],
    source_prefix: str,
) -> tuple[TreatmentPlanGoal, ...]:
    return tuple(
        TreatmentPlanGoal(
            goal_number=_alleva_text(value, "goalNumber", "id") or str(index + 1),
            goal_description=_alleva_text(value, "description", "goalDescription"),
            source_json_path=f"{source_prefix}[{index}]",
            objectives=_alleva_objectives(
                _alleva_objects(value, "objectives"),
                f"{source_prefix}[{index}].objectives",
            ),
        )
        for index, value in enumerate(values)
    )


def _alleva_problems(detail: dict[str, object]) -> tuple[TreatmentPlanProblem, ...]:
    problems: list[TreatmentPlanProblem] = []
    top_level_diagnoses = _alleva_objects(detail, "diagnoses")
    for index, value in enumerate(_alleva_objects(detail, "problems")):
        source_prefix = f"content_snapshot.problems[{index}]"
        diagnoses = _alleva_objects(value, "diagnoses")
        if index == 0 and not diagnoses:
            diagnoses = top_level_diagnoses
        behavioral_definitions = tuple(
            {
                "behavioral_definition_number": _alleva_text(item, "behavioralDefinitionNumber", "id")
                or str(definition_index + 1),
                "behavioral_definition": _alleva_text(item, "description", "behavioralDefinition"),
                "source_json_path": f"{source_prefix}.behavioral_definitions[{definition_index}]",
            }
            for definition_index, item in enumerate(_alleva_objects(value, "behavioralDefinitions"))
        )
        problems.append(
            TreatmentPlanProblem(
                problem_number=_alleva_text(value, "problemNumber", "id") or str(index + 1),
                problem_description=_alleva_text(value, "description", "problemDescription"),
                source_json_path=source_prefix,
                diagnoses=_alleva_diagnoses(diagnoses, f"{source_prefix}.diagnoses"),
                behavioral_definitions=behavioral_definitions,
                goals=_alleva_goals(_alleva_objects(value, "goals"), f"{source_prefix}.goals"),
            )
        )
    return tuple(problems)


def _alleva_signatures(
    detail: dict[str, object],
    contract: ApprovedAllevaContract,
) -> tuple[TreatmentPlanSignatureMetadata, ...]:
    signatures: list[TreatmentPlanSignatureMetadata] = []
    for field_name, value in detail.items():
        if not field_name.lower().endswith("signature") or not isinstance(value, dict):
            continue
        signature_data = value.get("data")
        signature_text = signature_data if isinstance(signature_data, str) else ""
        signature_role = field_name.removesuffix("Signature") or "unknown"
        signatures.append(
            TreatmentPlanSignatureMetadata(
                signature_type=field_name,
                has_signature_data=bool(signature_text),
                signer_role_or_type=_alleva_text(value, "type", "signerType", "role") or signature_role,
                signature_datetime=_alleva_text(
                    value,
                    "signatureDateTime",
                    "signatureDatetime",
                    "signedAt",
                    "date",
                ),
                signature_data_length=len(signature_text),
                signature_data_omitted_reason="Signature binary is excluded from the normalized clinical snapshot.",
                source_json_path=f"content_snapshot.{field_name}",
            )
        )
    if signatures:
        return tuple(signatures)
    legacy_date = _mapped_text(detail, contract, "treatment_plan_detail", "signature_date")
    if not legacy_date:
        return ()
    return (
        TreatmentPlanSignatureMetadata(
            signature_type="staffSignatureDate",
            has_signature_data=False,
            signer_role_or_type="staff",
            signature_datetime=legacy_date,
            signature_data_length=0,
            signature_data_omitted_reason="Only the source signature timestamp was returned.",
            source_json_path="content_snapshot.staffSignatureDate",
        ),
    )


def _alleva_observed_fields(detail: dict[str, object]) -> tuple[TreatmentPlanObservedField, ...]:
    observations: Counter[tuple[str, str, str]] = Counter()

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}" if path else key)
            return
        if isinstance(value, list):
            for child in value:
                visit(child, f"{path}[]")
            return
        if value is None:
            value_type = "null"
            state = "missing"
        elif isinstance(value, bool):
            value_type = "boolean"
            state = "present"
        elif isinstance(value, int | float):
            value_type = "number"
            state = "present"
        else:
            value_type = "string"
            state = "present" if isinstance(value, str) and value.strip() else "missing"
        observations[(path, value_type, state)] += 1

    visit(detail, "detail")
    checklist_fragments = (
        "reasonForAdmission",
        "initialClientNeeds",
        "familyEducationNeeds",
        ".description",
        "signatureDateTime",
    )
    return tuple(
        TreatmentPlanObservedField(
            field_path=path,
            value_type=value_type,
            state=state,
            sample_redacted_value="",
            source_endpoint="Alleva REST",
            occurrence_count=count,
            used_by_checklist=any(fragment in path for fragment in checklist_fragments),
            mapped_app_field="",
        )
        for (path, value_type, state), count in sorted(observations.items())
    )


def _alleva_snapshot_summary(problems: tuple[TreatmentPlanProblem, ...], signature_count: int) -> dict[str, JsonValue]:
    goals = tuple(goal for problem in problems for goal in problem.goals)
    objectives = tuple(objective for goal in goals for objective in goal.objectives)
    return {
        "problem_count": len(problems),
        "diagnosis_count": sum(len(problem.diagnoses) for problem in problems),
        "behavioral_definition_count": sum(len(problem.behavioral_definitions) for problem in problems),
        "goal_count": len(goals),
        "objective_count": len(objectives),
        "intervention_count": sum(len(objective.interventions) for objective in objectives),
        "signature_metadata_count": signature_count,
    }


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
    problems = _alleva_problems(detail)
    signatures = _alleva_signatures(detail, contract)
    snapshot = aggregate.content_snapshot.model_copy(update={
        "plan_id": plan_id,
        "source_mode": "alleva_rest_api",
        "content_hash": hashlib.sha256(
            json.dumps(detail, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "problems": problems,
        "signatures": signatures,
        "observed_fields": _alleva_observed_fields(detail),
    })
    evidence_coverage = aggregate.evidence_coverage_summary.model_copy(update={"plan_id": plan_id})
    plan_date = _alleva_text(detail, "startDate", "createdDate") or _alleva_text(plan, "startDate", "createdDate")
    created_date = _alleva_text(detail, "createdDate") or _alleva_text(plan, "createdDate")
    last_modified = (
        _mapped_text(detail, contract, "treatment_plan_detail", "last_modified")
        or _alleva_text(plan, "lastModified")
    )
    plan_record: dict[str, JsonValue] = {
        "plan_id": plan_id,
        "plan_date": plan_date,
        "created_date": created_date,
        "last_modified": last_modified,
        "is_active": True,
        "source": "alleva_rest_api",
    }
    return aggregate.model_copy(
        update={
            "source_mode": "alleva_rest_api",
            "source_last_updated": last_modified,
            "status_label": "Alleva REST sync",
            "treatment_plans": (plan_record,),
            "active_treatment_plans": (plan_record,),
            "latest_created_active_plan": plan_record,
            "current_plan_selection_reason": "Latest mapped active Alleva treatment plan",
            "treatment_review_data_status": "available" if isinstance(detail.get("review_detail"), dict) else "not_requested",
            "treatment_reviews": (detail["review_detail"],) if isinstance(detail.get("review_detail"), dict) else (),
            "source_evidence": evidence,
            "criteria_results": criteria,
            "content_snapshot_summary": _alleva_snapshot_summary(problems, len(signatures)),
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
