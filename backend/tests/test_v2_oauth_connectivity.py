from __future__ import annotations

import base64

import httpx
from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


class _TokenClient:
    calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _TokenClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def build_request(self, method: str, url: str, *, data: dict[str, str], headers: dict[str, str]) -> httpx.Request:
        self.calls.append((url, data, headers))
        return httpx.Request(method, url, data=data, headers=headers)

    def send(self, request: httpx.Request, *, stream: bool) -> httpx.Response:
        assert stream is True
        return httpx.Response(200, request=request, json={"access_token": "mock-token", "token_type": "Bearer", "expires_in": 3600})


class _RejectedTokenClient(_TokenClient):
    def send(self, request: httpx.Request, *, stream: bool) -> httpx.Response:
        assert stream is True
        return httpx.Response(401, request=request, json={"error": "synthetic-private-vendor-message"})


def test_saved_oauth_profile_uses_body_and_basic_styles_without_exposing_token(tmp_path, monkeypatch) -> None:
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.oauth_connectivity.httpx.Client", _TokenClient)
    _TokenClient.calls.clear()

    for style in ("body", "basic"):
        saved = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={"token_url": "https://mock.invalid/connect/token", "client_id": "mock-client", "client_secret": "mock-secret", "scopes": "plans.read", "token_auth_style": style},
        )
        assert saved.status_code == 200
        result = client.post("/api/api-configuration/test-connectivity", headers=headers)
        assert result.status_code == 200
        assert result.json()["status"] == "ok"
        assert "mock-token" not in result.text

    _, body_data, body_headers = _TokenClient.calls[0]
    assert body_data["client_id"] == "mock-client"
    assert body_data["client_secret"] == "mock-secret"
    assert "authorization" not in body_headers
    _, basic_data, basic_headers = _TokenClient.calls[1]
    assert "client_secret" not in basic_data
    assert basic_headers["authorization"] == f"Basic {base64.b64encode(b'mock-client:mock-secret').decode('ascii')}"

    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    event = next(item for item in audit if item["action"] == "api.oauth.connectivity.tested")
    assert event["details"]["credentials_verified"] is True
    assert "mock-secret" not in str(event)


def test_saved_oauth_failure_reports_safe_actionable_http_status(tmp_path, monkeypatch) -> None:
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.oauth_connectivity.httpx.Client", _RejectedTokenClient)
    client.patch(
        "/api/api-configuration",
        headers=headers,
        json={"token_url": "https://mock.invalid/connect/token", "client_id": "mock-client", "client_secret": "mock-secret"},
    )

    result = client.post("/api/api-configuration/test-connectivity", headers=headers)

    assert result.status_code == 200
    assert result.json()["status"] == "failure"
    assert "OAuth HTTP 401" in result.json()["message"]
    assert "mock-secret" not in result.text
    assert "synthetic-private-vendor-message" not in result.text
