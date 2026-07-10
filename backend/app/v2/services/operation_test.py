from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.v2.services.oauth_connectivity import request_client_credentials

MAX_RESPONSE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class OperationTestResult:
    status: str
    message: str
    status_code: int | None = None
    content_type: str = ""
    response_bytes: int = 0
    response_truncated: bool = False


def test_read_only_operation(*, api_base_url: str, path: str, token_url: str, client_id: str, client_secret: str, scope: str, token_auth_style: str, timeout_seconds: int) -> OperationTestResult:
    base = urlparse(api_base_url)
    if base.scheme not in {"http", "https"} or not base.netloc:
        return OperationTestResult("failure", "Saved API base URL must be an absolute HTTP or HTTPS URL.")
    if not path.startswith("/") or "//" in path or "://" in path:
        return OperationTestResult("failure", "Operation path must be a relative path beginning with one slash.")
    token_result, token = request_client_credentials(
        token_url=token_url, client_id=client_id, client_secret=client_secret, scope=scope,
        token_auth_style=token_auth_style, timeout_seconds=timeout_seconds,
    )
    if not token:
        return OperationTestResult("failure", "OAuth verification failed before the read-only operation could run.")
    try:
        with httpx.Client(timeout=max(1, min(timeout_seconds, 60)), follow_redirects=True) as client:
            with client.stream("GET", f"{api_base_url.rstrip('/')}{path}", headers={"accept": "application/json", "authorization": f"Bearer {token}"}) as response:
                observed = 0
                for chunk in response.iter_bytes():
                    observed += len(chunk)
                    if observed > MAX_RESPONSE_BYTES:
                        break
                return OperationTestResult(
                    "ok" if 200 <= response.status_code < 300 else "failure",
                    "Read-only operation completed." if 200 <= response.status_code < 300 else "Read-only operation returned a non-success HTTP status.",
                    response.status_code, response.headers.get("content-type", ""), observed, observed > MAX_RESPONSE_BYTES,
                )
    except httpx.HTTPError:
        return OperationTestResult("failure", "Read-only operation did not complete successfully.")
