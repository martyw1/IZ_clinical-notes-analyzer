from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.v2.services.bounded_http import ResponseTooLarge, post_bounded

MAX_OAUTH_RESPONSE_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class OAuthConnectivityResult:
    status: str
    token_auth_style: str
    message: str
    token_type: str = ""
    expires_in: int | None = None


def test_client_credentials(
    *, token_url: str, client_id: str, client_secret: str, scope: str, token_auth_style: str, timeout_seconds: int,
) -> OAuthConnectivityResult:
    return request_client_credentials(
        token_url=token_url, client_id=client_id, client_secret=client_secret, scope=scope,
        token_auth_style=token_auth_style, timeout_seconds=timeout_seconds,
    )[0]


def request_client_credentials(
    *, token_url: str, client_id: str, client_secret: str, scope: str, token_auth_style: str, timeout_seconds: int,
) -> tuple[OAuthConnectivityResult, str]:
    parsed = urlparse(token_url)
    style = token_auth_style if token_auth_style in {"body", "basic"} else "body"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return OAuthConnectivityResult("failure", style, "Saved token URL must be an absolute HTTP or HTTPS URL."), ""
    if not client_id.strip() or not client_secret.strip():
        return OAuthConnectivityResult("failure", style, "Saved client ID and client secret are required for OAuth testing."), ""
    headers = {"accept": "application/json"}
    data = {"grant_type": "client_credentials"}
    if scope.strip():
        data["scope"] = scope.strip()
    if style == "body":
        data.update({"client_id": client_id, "client_secret": client_secret})
    else:
        encoded = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        headers["authorization"] = f"Basic {encoded}"
    try:
        with httpx.Client(timeout=max(1, min(timeout_seconds, 60)), follow_redirects=False) as client:
            response = post_bounded(
                client,
                token_url,
                maximum_bytes=MAX_OAUTH_RESPONSE_BYTES,
                data=data,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return OAuthConnectivityResult("failure", style, _safe_http_failure(exc.response.status_code)), ""
    except httpx.RequestError:
        return OAuthConnectivityResult(
            "failure", style,
            "Could not reach the saved OAuth token endpoint. Check the URL, network connection, and vendor availability.",
        ), ""
    except ResponseTooLarge:
        return OAuthConnectivityResult(
            "failure", style,
            "The OAuth token endpoint response exceeded the safe local size limit.",
        ), ""
    except ValueError:
        return OAuthConnectivityResult(
            "failure", style,
            "The OAuth token endpoint returned an unreadable response. Verify that the saved URL is the vendor token endpoint.",
        ), ""
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        return OAuthConnectivityResult("failure", style, "OAuth token response did not include an access token."), ""
    expires_in = payload.get("expires_in") if isinstance(payload, dict) else None
    return OAuthConnectivityResult(
        "ok", style, "OAuth client-credentials token obtained and discarded after verification.",
        str(payload.get("token_type") or "Bearer"), expires_in if isinstance(expires_in, int) else None,
    ), token.strip()


def _safe_http_failure(status_code: int) -> str:
    if status_code in {401, 403}:
        return f"OAuth HTTP {status_code}: the vendor rejected the saved client credentials or authentication style."
    if status_code == 404:
        return "OAuth HTTP 404: the saved token endpoint was not found. Verify the token URL in Settings."
    if status_code == 400:
        return "OAuth HTTP 400: the vendor rejected the token request. Verify scopes, client ID, secret, and authentication style."
    if status_code >= 500:
        return f"OAuth HTTP {status_code}: the vendor token service is currently unavailable."
    return f"OAuth HTTP {status_code}: the vendor did not accept the token request."
