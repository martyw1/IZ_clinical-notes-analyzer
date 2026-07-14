from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from app.v2.models import AppSetting
from app.v2.services.alleva_contracts import ApprovedAllevaContract, reconcile_sync_patients
from app.v2.services.alleva_protocol import AllevaReadProtocol, read_headers
from app.v2.services.alleva_sync import (
    MAX_SYNC_ROWS,
    AllevaSyncCancelled,
    AllevaSyncError,
    ApprovedRequestRateLimiter,
    _client_lifecycles,
    _endpoint_path,
    _endpoint_request_parameters,
    _get_with_retry,
    _oauth_token,
    _records,
)

RosterTerminalStatus = Literal["completed", "completed_with_warnings"]
MAX_ROSTER_PAGES: Final = 5_000


@dataclass(frozen=True, slots=True)
class RosterPullResult:
    status: RosterTerminalStatus
    observed_count: int
    warning_count: int
    complete_snapshot: bool


def run_roster_pull(
    db: Session,
    profile: AppSetting,
    contract: ApprovedAllevaContract,
    external_job_id: str,
    reconciled_at: str,
    *,
    is_cancelled: Callable[[], bool] = lambda: False,
    on_page: Callable[[int, int, tuple[dict[str, object], ...]], None] | None = None,
) -> RosterPullResult:
    token = _oauth_token(profile, contract, is_cancelled)
    protocol = AllevaReadProtocol(profile.alleva_api_version, profile.alleva_treatment_plan_start_date)
    headers = read_headers(bearer_token=token, protocol=protocol)
    pagination = contract.payload.pagination
    page_size = pagination.maximum_page_size
    record_limit = min(pagination.maximum_records, MAX_SYNC_ROWS)
    rate_limiter = ApprovedRequestRateLimiter(contract.payload.rate_limit.maximum_requests_per_minute)
    records: list[dict[str, object]] = []
    seen_pages: set[str] = set()
    cursor = 0
    page_number = 0
    warning_count = 0
    complete_snapshot = False

    with httpx.Client(timeout=max(1, min(profile.emr_api_timeout_seconds, 60)), follow_redirects=False) as client:
        while len(records) < record_limit and page_number < MAX_ROSTER_PAGES:
            if is_cancelled():
                raise AllevaSyncCancelled("Alleva patient-roster pull was cancelled.")
            requested = min(page_size, record_limit - len(records))
            try:
                response = _get_with_retry(
                    client,
                    urljoin(
                        f"{profile.api_base_url.rstrip('/')}/",
                        _endpoint_path(contract, "clients").lstrip("/"),
                    ),
                    _endpoint_request_parameters(
                        contract,
                        "clients",
                        requested,
                        cursor,
                        protocol=protocol,
                    ),
                    headers,
                    is_cancelled,
                    0 if records else contract.payload.rate_limit.retry_after_seconds,
                    rate_limiter,
                    pagination.maximum_response_bytes,
                )
                page = _records(response.json())
                if len(page) > requested:
                    raise AllevaSyncError("Alleva roster response exceeded the approved page size.")
            except AllevaSyncCancelled:
                raise
            except (httpx.HTTPError, json.JSONDecodeError, ValueError, AllevaSyncError):
                if not records:
                    raise AllevaSyncError("Alleva patient-roster pull failed before any safe records were observed.") from None
                warning_count = 1
                break

            signature = hashlib.sha256(
                json.dumps(page, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if page and signature in seen_pages:
                warning_count = 1
                break
            seen_pages.add(signature)
            records.extend(page)
            if on_page is not None:
                on_page(page_number, cursor, tuple(page))
            page_number += 1
            if len(page) < requested:
                complete_snapshot = True
                break
            cursor += requested

    if not complete_snapshot:
        warning_count = 1
    reconcile_sync_patients(
        db,
        external_job_id,
        _client_lifecycles(tuple(records), contract),
        complete_snapshot,
        reconciled_at,
    )
    return RosterPullResult(
        status="completed" if complete_snapshot else "completed_with_warnings",
        observed_count=len(records),
        warning_count=warning_count,
        complete_snapshot=complete_snapshot,
    )
