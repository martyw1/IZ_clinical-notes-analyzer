from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

import httpx

from app.v2.services.bounded_http import ResponseTooLarge, get_bounded
from app.v2.services.job_artifacts import DiagnosticFailure, JsonValue, record, write_progress
from app.v2.services.oauth_connectivity import request_client_credentials
from app.v2.services.alleva_protocol import (
    AllevaReadProtocol,
    DEFAULT_ALLEVA_API_VERSION,
    DEFAULT_TREATMENT_PLAN_START_DATE,
    collection_parameters,
    collection_records,
    read_headers,
)

MAX_DIAGNOSTIC_PAGES = 100
MAX_DIAGNOSTIC_RECORDS = 10_000
MAX_DIAGNOSTIC_RESPONSE_BYTES = 5_000_000


@dataclass(frozen=True, slots=True)
class DiagnosticPullCompleted:
    rows: tuple[dict[str, JsonValue], ...]
    status: Literal["completed", "completed_with_warnings"]


@dataclass(frozen=True, slots=True)
class DiagnosticPullCancelled:
    rows: tuple[dict[str, JsonValue], ...]
    status: Literal["cancelled"]


@dataclass(frozen=True, slots=True)
class DiagnosticPullFailed:
    rows: tuple[dict[str, JsonValue], ...]
    status: Literal["failed"]
    failure: DiagnosticFailure


DiagnosticPullResult: TypeAlias = DiagnosticPullCompleted | DiagnosticPullCancelled | DiagnosticPullFailed


@dataclass(frozen=True, slots=True)
class FailureCause:
    error_class: str
    safe_message: str
    http_status: int | None = None


class DiagnosticConnection(Protocol):
    api_base_url: str
    token_url: str
    client_id: str
    client_secret: str
    scope: str
    token_auth_style: str
    timeout_seconds: int
    page_size: int
    api_version: str
    treatment_plan_start_date: str


def fetch_paged_records(*, job_id: str, connection: DiagnosticConnection, output_dir: Path, is_cancelled: Callable[[], bool], update: Callable[..., None]) -> DiagnosticPullResult:
    authentication, token = request_client_credentials(token_url=connection.token_url, client_id=connection.client_id, client_secret=connection.client_secret, scope=connection.scope, token_auth_style=connection.token_auth_style, timeout_seconds=connection.timeout_seconds)
    if not token:
        return DiagnosticPullFailed(
            rows=(),
            status="failed",
            failure=DiagnosticFailure("authentication", "OAuthAuthenticationFailure", authentication.message, None),
        )
    rows: list[dict[str, JsonValue]] = []
    page_signatures: set[str] = set()
    page = 0
    protocol = AllevaReadProtocol(
        getattr(connection, "api_version", DEFAULT_ALLEVA_API_VERSION),
        getattr(connection, "treatment_plan_start_date", DEFAULT_TREATMENT_PLAN_START_DATE),
    )
    try:
        with httpx.Client(timeout=max(1, min(connection.timeout_seconds, 60)), follow_redirects=True) as client, (output_dir / "all-treatment-plans.all-fields.redacted.jsonl").open("w", encoding="utf-8") as handle:
            offset = 0
            while True:
                if is_cancelled():
                    return DiagnosticPullCancelled(tuple(rows), "cancelled")
                if page >= MAX_DIAGNOSTIC_PAGES or len(rows) >= MAX_DIAGNOSTIC_RECORDS:
                    update(warnings_count=1, progress_percent=100)
                    return DiagnosticPullCompleted(tuple(rows), "completed_with_warnings")
                page += 1
                response = get_bounded(
                    client,
                    f"{connection.api_base_url.rstrip('/')}/treatment-plans",
                    maximum_bytes=MAX_DIAGNOSTIC_RESPONSE_BYTES,
                    params=collection_parameters(
                        endpoint_parameters={"limit": "Limit", "offset": "Cursor", "start_date": "StartDate"},
                        limit_parameter="Limit",
                        offset_parameter="Cursor",
                        limit=connection.page_size,
                        cursor=offset,
                        protocol=protocol,
                        include_start_date=True,
                    ),
                    headers=read_headers(bearer_token=token, protocol=protocol),
                )
                response.raise_for_status()
                records = _records(response.json())
                signature = hashlib.sha256(
                    json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                if records and signature in page_signatures:
                    update(
                        current_page=page,
                        current_cursor=f"offset-{offset}",
                        records_seen=len(rows),
                        records_written=len(rows),
                        warnings_count=1,
                        progress_percent=100,
                    )
                    return DiagnosticPullCompleted(tuple(rows), "completed_with_warnings")
                page_signatures.add(signature)
                remaining = MAX_DIAGNOSTIC_RECORDS - len(rows)
                bounded_records = records[:remaining]
                for payload in bounded_records:
                    row = record(job_id, len(rows) + 1, payload, endpoint="GET /treatment-plans", page=page)
                    rows.append(row)
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
                write_progress(output_dir, job_id, page, min(95, 5 + page * 15))
                update(current_page=page, current_cursor=f"offset-{offset}", records_seen=len(rows), records_written=len(rows), progress_percent=min(95, 5 + page * 15))
                if len(bounded_records) < len(records):
                    update(warnings_count=1, progress_percent=100)
                    return DiagnosticPullCompleted(tuple(rows), "completed_with_warnings")
                if len(records) < connection.page_size:
                    return DiagnosticPullCompleted(tuple(rows), "completed")
                offset += connection.page_size
    except httpx.HTTPStatusError as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor API returned an unsuccessful HTTP status.", exc.response.status_code))
    except httpx.TimeoutException as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor API request timed out."))
    except httpx.DecodingError as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor response compression could not be decoded."))
    except httpx.RequestError as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor API request failed."))
    except ResponseTooLarge as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor response exceeded the diagnostic byte limit."))
    except json.JSONDecodeError as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor response was not valid JSON."))
    except ValueError as exc:
        return _failed(rows, page, FailureCause(type(exc).__name__, "Vendor response did not contain the expected treatment-plan list."))


def _failed(
    rows: list[dict[str, JsonValue]],
    page: int,
    cause: FailureCause,
) -> DiagnosticPullFailed:
    stage = "first_page" if page <= 1 and not rows else "pagination"
    return DiagnosticPullFailed(
        rows=tuple(rows),
        status="failed",
        failure=DiagnosticFailure(stage, cause.error_class, cause.safe_message, cause.http_status),
    )


def _records(payload: object) -> list[dict[str, object]]:
    return collection_records(payload)
