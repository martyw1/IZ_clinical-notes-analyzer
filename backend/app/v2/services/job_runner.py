from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from app.v2.services.job_artifacts import record, write_progress
from app.v2.services.oauth_connectivity import request_client_credentials


def fetch_paged_records(*, job_id: str, connection: Any, output_dir: Path, is_cancelled: Callable[[], bool], update: Callable[..., None]) -> tuple[list[dict[str, object]], str]:
    _, token = request_client_credentials(token_url=connection.token_url, client_id=connection.client_id, client_secret=connection.client_secret, scope=connection.scope, token_auth_style=connection.token_auth_style, timeout_seconds=connection.timeout_seconds)
    if not token:
        return [], "failed"
    rows: list[dict[str, object]] = []
    try:
        with httpx.Client(timeout=max(1, min(connection.timeout_seconds, 60)), follow_redirects=True) as client, (output_dir / "all-treatment-plans.all-fields.redacted.jsonl").open("w", encoding="utf-8") as handle:
            offset = 0
            page = 0
            while True:
                if is_cancelled():
                    return rows, "cancelled"
                page += 1
                response = client.get(f"{connection.api_base_url.rstrip('/')}/treatment-plans", params={"limit": connection.page_size, "offset": offset}, headers={"accept": "application/json", "authorization": f"Bearer {token}"})
                response.raise_for_status()
                records = _records(response.json())
                for payload in records:
                    row = record(job_id, len(rows) + 1, payload, endpoint="GET /treatment-plans", page=page)
                    rows.append(row)
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
                write_progress(output_dir, job_id, page, min(95, 5 + page * 15))
                update(current_page=page, current_cursor=f"offset-{offset}", records_seen=len(rows), records_written=len(rows), progress_percent=min(95, 5 + page * 15))
                if len(records) < connection.page_size:
                    return rows, "completed"
                offset += len(records)
    except (httpx.HTTPError, ValueError):
        return rows, "failed"


def _records(payload: object) -> list[dict[str, object]]:
    values = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("Treatment-plan response did not contain a list")
    return [item for item in values if isinstance(item, dict)]
