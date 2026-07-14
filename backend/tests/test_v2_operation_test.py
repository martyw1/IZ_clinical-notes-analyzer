from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


class _OperationClient:
    operation_headers: dict[str, str] = {}

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _OperationClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("POST", url), json={"access_token": "operation-token"})

    def build_request(self, method: str, url: str, **kwargs: object) -> httpx.Request:
        return httpx.Request(
            method,
            url,
            data=kwargs.get("data"),
            headers=kwargs.get("headers"),
        )

    def send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        response = self.post(str(request.url))
        response.request = request
        return response

    def stream(self, method: str, url: str, *, headers: dict[str, str]):
        assert method == "GET"
        assert url == "https://mock.invalid/clients?active=true"
        type(self).operation_headers = headers
        return _StreamResponse()


class _StreamResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def __enter__(self) -> _StreamResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def iter_bytes(self):
        yield b'{"items":[{"id":"synthetic"}]}'


def test_saved_profile_read_only_operation_uses_in_memory_bearer_and_safe_result(tmp_path, monkeypatch) -> None:
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.oauth_connectivity.httpx.Client", _OperationClient)

    saved = client.patch(
        "/api/api-configuration", headers=headers,
        json={"api_base_url": "https://mock.invalid", "token_url": "https://mock.invalid/connect/token", "client_id": "mock-client", "client_secret": "mock-secret", "api_enabled": True},
    )
    assert saved.status_code == 200
    tested = client.post("/api/api-configuration/test-operation", headers=headers, json={"path": "/clients?active=true"})
    assert tested.status_code == 200
    assert tested.json() == {"status": "ok", "message": "Read-only operation completed.", "status_code": 200, "content_type": "application/json", "response_bytes": 30, "response_truncated": False}
    assert _OperationClient.operation_headers["authorization"] == "Bearer operation-token"
    assert "operation-token" not in tested.text
    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert any(item["action"] == "api.operation.read_only.tested" for item in audit)
    assert all("prev_hash" not in item and "hash" not in item for item in audit)
