from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

from app.core.config import settings
from app.services.alleva_retrieval import ALLEVA_TREATMENT_PLANS_PATH, query_and_headers
from app.services.alleva_treatment_plan_harness_models import StreamedBody, TreatmentPlanHarnessRequest
from app.services.api_connectivity import (
    MAX_RESPONSE_CAPTURE_BYTES,
    redact_sensitive_text,
    redact_url,
)


def _artifact_path(report: str, suffix: str) -> Path:
    target_dir = settings.local_app_data_dir / 'api-reports'
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_report = re.sub(r'[^a-zA-Z0-9_.-]+', '-', report).strip('-') or 'alleva-treatment-plan'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return target_dir / f'{stamp}-{safe_report}{suffix}'


def _headers_and_url(request: TreatmentPlanHarnessRequest) -> tuple[dict[str, str], str]:
    query, headers = query_and_headers(request.operation_parameters)
    if request.api_key:
        headers[request.api_key_header_name or 'x-api-key'] = request.api_key
    if request.bearer_token:
        headers['Authorization'] = f'Bearer {request.bearer_token}'
    url = urljoin(request.base_url.rstrip('/') + '/', ALLEVA_TREATMENT_PLANS_PATH.lstrip('/'))
    if query:
        url = f'{url}?{urlencode(query, doseq=True)}'
    return headers, url


def stream_body(request: TreatmentPlanHarnessRequest) -> StreamedBody:
    headers, url = _headers_and_url(request)
    body_path = _artifact_path(request.report, '.body.json')
    preview = bytearray()
    observed_bytes = 0
    started = time.perf_counter()
    timeout = max(1, min(int(request.timeout_seconds or 10), 60))
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        with client.stream('GET', url, headers=headers, timeout=timeout) as response, body_path.open('wb') as body_file:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                observed_bytes += len(chunk)
                body_file.write(chunk)
                remaining = MAX_RESPONSE_CAPTURE_BYTES - len(preview)
                if remaining > 0:
                    preview.extend(chunk[:remaining])
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return StreamedBody(
                status_code=response.status_code,
                content_type=response.headers.get('content-type', ''),
                elapsed_ms=elapsed_ms,
                url=redact_url(str(response.url)),
                body_file=str(body_path),
                preview=bytes(preview),
                observed_bytes=observed_bytes,
                truncated=observed_bytes > MAX_RESPONSE_CAPTURE_BYTES,
            )


def decode_preview(raw: bytes) -> str:
    for encoding in ('utf-8', 'utf-16', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='ignore')


def load_json_body(body_file: str) -> tuple[Any | None, str, str]:
    try:
        with Path(body_file).open(encoding='utf-8') as handle:
            return json.load(handle), 'ok', ''
    except UnicodeDecodeError as exc:
        return None, 'decode_failed', redact_sensitive_text(str(exc))
    except json.JSONDecodeError as exc:
        return None, 'parse_failed', redact_sensitive_text(str(exc))
