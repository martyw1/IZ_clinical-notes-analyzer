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

    def build_request(self, method: str, url: str, **kwargs: object) -> httpx.Request:
        return httpx.Request(
            method,
            url,
            data=kwargs.get("data"),
            params=kwargs.get("params"),
            headers=kwargs.get("headers"),
        )

    def send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        if request.method == "POST":
            response = self.post(str(request.url))
            response.request = request
            return response
        response = self.get(
            str(request.url).split("?", 1)[0],
            params={key: int(value) for key, value in request.url.params.items()},
            headers={"authorization": request.headers["authorization"]},
        )
        response.request = request
        return response


class _FailingHarnessClient(_HarnessClient):
    def get(self, url: str, *, params: dict[str, int], headers: dict[str, str]) -> httpx.Response:
        assert headers["authorization"] == "Bearer harness-token"
        assert params == {"limit": 100, "offset": 0}
        return httpx.Response(503, request=httpx.Request("GET", url), json={"detail": "synthetic failure"})


class _UnexpectedFailureHarnessClient(_HarnessClient):
    def send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        if request.method == "POST":
            return super().send(request, stream=stream)
        raise RuntimeError("synthetic sensitive internal detail")


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
    assert preview.json()["records"][0]["record_id"].startswith("hmac-sha256:")
    assert "TP-MOCK-1" not in preview.text

    restarted_client = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _auth_headers(restarted_client)
    recovered = restarted_client.get(f"/api/v2/api-harness/jobs/{job_id}", headers=restarted_headers)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "completed"
    artifacts = restarted_client.get(f"/api/v2/api-harness/jobs/{job_id}/artifacts", headers=restarted_headers)
    assert artifacts.status_code == 200
    assert any(item["artifact_id"] == "run-summary.json" for item in artifacts.json())


def test_failed_harness_job_writes_redacted_artifact_and_forensic_events(tmp_path, monkeypatch) -> None:
    # Given: OAuth succeeds but the first treatment-plan page returns a service failure.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.oauth_connectivity.httpx.Client", _FailingHarnessClient)
    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "api_base_url": "https://mock.invalid",
            "token_url": "https://mock.invalid/connect/token",
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "api_enabled": True,
            "pagination_limit": 100,
        },
    )
    assert saved.status_code == 200

    # When: the diagnostic pull reaches a terminal failure.
    started = client.post(
        "/api/v2/api-harness/jobs",
        headers=headers,
        json={"job_type": "pull_all_treatment_plans_all_fields"},
    )
    job_id = started.json()["job_id"]
    for _ in range(30):
        current = client.get(f"/api/v2/api-harness/jobs/{job_id}", headers=headers).json()
        if current["status"] == "failed":
            break
        time.sleep(0.05)

    # Then: the job exposes a safe error artifact and Forensic Logs contain its lifecycle.
    assert current["status"] == "failed"
    artifacts = client.get(f"/api/v2/api-harness/jobs/{job_id}/artifacts", headers=headers).json()
    assert any(item["artifact_id"] == "all-treatment-plans.error-log.jsonl" for item in artifacts)
    error_artifact = client.get(
        f"/api/v2/api-harness/jobs/{job_id}/artifacts/all-treatment-plans.error-log.jsonl",
        headers=headers,
    )
    assert error_artifact.status_code == 200
    assert "HTTPStatusError" in error_artifact.text
    assert "503" in error_artifact.text
    assert "mock-secret" not in error_artifact.text
    audit_items = client.get("/api/audit/logs", headers=headers).json()["items"]
    job_actions = [item for item in audit_items if item["target_entity_id"] == job_id]
    assert {item["action"] for item in job_actions} >= {
        "api_harness.job.created",
        "api_harness.job.started",
        "api_harness.job.failed",
    }
    failure = next(item for item in job_actions if item["action"] == "api_harness.job.failed")
    assert failure["outcome_status"] == "failure"
    assert failure["details"] == {
        "error_class": "HTTPStatusError",
        "failure_stage": "first_page",
        "http_status": 503,
    }


def test_unexpected_worker_error_reaches_safe_forensic_outputs(tmp_path, monkeypatch) -> None:
    # Given: an unexpected implementation error occurs after OAuth succeeds.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr("app.v2.services.oauth_connectivity.httpx.Client", _UnexpectedFailureHarnessClient)
    saved = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "api_base_url": "https://mock.invalid",
            "token_url": "https://mock.invalid/connect/token",
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "api_enabled": True,
            "pagination_limit": 100,
        },
    )
    assert saved.status_code == 200

    # When: the background worker exits through its outer safety boundary.
    started = client.post(
        "/api/v2/api-harness/jobs",
        headers=headers,
        json={"job_type": "pull_all_treatment_plans_all_fields"},
    )
    job_id = started.json()["job_id"]
    for _ in range(30):
        current = client.get(f"/api/v2/api-harness/jobs/{job_id}", headers=headers).json()
        if current["status"] == "failed":
            break
        time.sleep(0.05)

    # Then: the job terminates and captures only safe classification data.
    assert current["status"] == "failed"
    error_artifact = client.get(
        f"/api/v2/api-harness/jobs/{job_id}/artifacts/all-treatment-plans.error-log.jsonl",
        headers=headers,
    )
    assert error_artifact.status_code == 200
    assert "RuntimeError" in error_artifact.text
    assert "synthetic sensitive internal detail" not in error_artifact.text
    audit_items = client.get("/api/audit/logs", headers=headers).json()["items"]
    failure = next(
        item
        for item in audit_items
        if item["target_entity_id"] == job_id and item["action"] == "api_harness.job.failed"
    )
    assert failure["details"] == {
        "error_class": "RuntimeError",
        "failure_stage": "worker",
    }
