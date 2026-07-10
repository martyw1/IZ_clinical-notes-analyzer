from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


class _OpenApiClient:
    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _OpenApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        assert url == "https://mock.invalid/openapi.json"
        assert headers["accept"] == "application/json"
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "openapi": "3.1.0",
                "info": {"title": "Mock Treatment Plan API"},
                "paths": {"/clients": {"get": {}, "post": {}}, "/health": {"get": {}}},
            },
        )


def test_openapi_pull_uses_saved_profile_and_records_safe_summary(tmp_path, monkeypatch) -> None:
    client: TestClient = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.openapi_definition_loader.httpx.Client", _OpenApiClient)

    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={"openapi_url": "https://mock.invalid/openapi.json", "timeout_seconds": 7},
    )
    assert saved.status_code == 200

    pulled = client.post("/api/api-configuration/pull-definitions", headers=headers)
    assert pulled.status_code == 200
    assert pulled.json()["definition_summary"] == {"title": "Mock Treatment Plan API", "operation_count": 3}

    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    event = next(item for item in audit if item["action"] == "api.openapi.definition.pulled")
    assert event["details"]["operation_count"] == 3
    assert "mock.invalid" not in str(event["details"])
