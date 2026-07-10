from __future__ import annotations

import time

import httpx

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


class _HarnessClient:
    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _HarnessClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("POST", url), json={"access_token": "harness-token"})

    def get(self, url: str, *, params: dict[str, int], headers: dict[str, str]) -> httpx.Response:
        assert headers["authorization"] == "Bearer harness-token"
        assert params == {"limit": 100, "offset": 0}
        return httpx.Response(200, request=httpx.Request("GET", url), json={"items": [{"id": "TP-MOCK-1", "clientId": "CLIENT-MOCK-1"}]})


def test_harness_job_and_artifacts_survive_a_fresh_app_instance(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.oauth_connectivity.httpx.Client", _HarnessClient)
    saved = client.patch(
        "/api/api-configuration", headers=headers,
        json={"api_base_url": "https://mock.invalid", "token_url": "https://mock.invalid/connect/token", "client_id": "mock-client", "client_secret": "mock-secret", "api_enabled": True, "pagination_limit": 100},
    )
    assert saved.status_code == 200
    started = client.post("/api/v2/api-harness/jobs", headers=headers, json={"job_type": "pull_all_treatment_plans_all_fields"})
    assert started.status_code == 200
    job_id = started.json()["job_id"]
    for _ in range(30):
        current = client.get(f"/api/v2/api-harness/jobs/{job_id}", headers=headers).json()
        if current["status"] == "completed":
            break
        time.sleep(0.05)
    assert current["status"] == "completed"
    preview = client.get(f"/api/v2/api-harness/jobs/{job_id}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["records"][0]["record_id"] == "TP-MOCK-1"

    restarted_client = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _auth_headers(restarted_client)
    recovered = restarted_client.get(f"/api/v2/api-harness/jobs/{job_id}", headers=restarted_headers)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "completed"
    artifacts = restarted_client.get(f"/api/v2/api-harness/jobs/{job_id}/artifacts", headers=restarted_headers)
    assert artifacts.status_code == 200
    assert any(item["artifact_id"] == "run-summary.json" for item in artifacts.json())
