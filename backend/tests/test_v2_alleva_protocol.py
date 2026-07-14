from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from app.v2.services.alleva_contracts import ApprovedAllevaContract, _builtin_contract_payload
from app.v2.models import AppSetting


class _CapturingDiagnosticClient:
    requests: list[httpx.Request] = []

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _CapturingDiagnosticClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def build_request(self, method: str, url: str, **kwargs: object) -> httpx.Request:
        return httpx.Request(
            method,
            url,
            params=kwargs.get("params"),
            headers=kwargs.get("headers"),
        )

    def send(self, request: httpx.Request, *, stream: bool) -> httpx.Response:
        assert stream is True
        self.requests.append(request)
        return httpx.Response(200, request=request, json={"items": [{"id": "synthetic-plan"}]})


def _built_in_contract() -> ApprovedAllevaContract:
    profile = AppSetting(
        api_base_url="https://api.allevasoft.com",
        api_oauth_token_url="https://authorization.allevasoft.com/connect/token",
        api_token_auth_style="body",
        api_scopes="",
        openapi_url="https://api.allevasoft.com/swagger/v1/swagger.json",
        alleva_api_version="1.0",
        alleva_treatment_plan_start_date="2000-01-01T16:03",
        api_pagination_limit=100,
        alleva_treatment_plan_sync_limit=250,
        api_requests_per_minute=600,
    )
    payload = _builtin_contract_payload(
        profile,
        contract_version="synthetic-built-in-contract",
        effective_at=datetime.now(timezone.utc),
    )
    return ApprovedAllevaContract(
        1,
        payload.contract_version,
        "a" * 64,
        payload.effective_at,
        payload.effective_at,
        payload,
    )


def test_diagnostic_treatment_plan_pull_uses_exact_published_v1_request(monkeypatch, tmp_path) -> None:
    from app.v2.services import job_runner

    monkeypatch.setattr(job_runner.httpx, "Client", _CapturingDiagnosticClient)
    monkeypatch.setattr(
        job_runner,
        "request_client_credentials",
        lambda **_: (SimpleNamespace(message="ok"), "synthetic-token"),
    )
    _CapturingDiagnosticClient.requests.clear()
    connection = SimpleNamespace(
        token_url="https://synthetic.invalid/token",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
        scope="synthetic.read",
        token_auth_style="body",
        timeout_seconds=5,
        api_base_url="https://synthetic.invalid",
        page_size=2,
        api_version="1.0",
        treatment_plan_start_date="2000-01-01T16:03",
    )

    result = job_runner.fetch_paged_records(
        job_id="synthetic-job",
        connection=connection,
        output_dir=tmp_path,
        is_cancelled=lambda: False,
        update=lambda **_: None,
    )

    assert result.status == "completed", result
    request = _CapturingDiagnosticClient.requests[0]
    assert dict(request.url.params) == {
        "Limit": "2",
        "Cursor": "0",
        "StartDate": "2000-01-01T16:03",
        "api-version": "1.0",
    }
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Authorization"] == "Bearer synthetic-token"
    assert request.headers["X-Version"] == "1.0"


def test_operational_collection_parameters_use_exact_v1_semantics() -> None:
    from app.v2.services.alleva_sync import _endpoint_request_parameters

    contract = _built_in_contract()

    assert _endpoint_request_parameters(
        contract,
        "clients",
        100,
        0,
        additional_parameters={"api_version": "1.0"},
    ) == {"Limit": 100, "Cursor": 0, "api-version": "1.0"}
    assert _endpoint_request_parameters(
        contract,
        "treatment_plans",
        100,
        0,
        additional_parameters={
            "api_version": "1.0",
            "start_date": "2000-01-01T16:03",
            "client_id": "912",
        },
    ) == {
        "Limit": 100,
        "Cursor": 0,
        "StartDate": "2000-01-01T16:03",
        "api-version": "1.0",
        "ClientId": "912",
    }


def test_operational_detail_uses_api_version_without_patient_query(monkeypatch) -> None:
    from app.v2.services.alleva_sync import ApprovedRequestRateLimiter, _endpoint_json

    captured: list[dict[str, str | int] | None] = []

    def capture_request(
        _client: httpx.Client,
        _url: str,
        params: dict[str, str | int] | None,
        _headers: dict[str, str],
        _is_cancelled,
        _retry_after_seconds: int,
        _rate_limiter,
        _maximum_response_bytes: int,
    ) -> httpx.Response:
        captured.append(params)
        return httpx.Response(200, request=httpx.Request("GET", "https://synthetic.invalid"), json={})

    monkeypatch.setattr("app.v2.services.alleva_sync._get_with_retry", capture_request)
    with httpx.Client() as client:
        _endpoint_json(
            client,
            "https://synthetic.invalid",
            _built_in_contract(),
            "treatment_plan_detail",
            {},
            lambda: False,
            ApprovedRequestRateLimiter(10_000),
            api_version="1.0",
            plan_id="plan-912",
        )

    assert captured == [{"api-version": "1.0"}]


def test_collection_response_wrappers_match_working_v1_harness() -> None:
    from app.v2.services.alleva_sync import _records

    expected = [{"id": "synthetic-plan"}]
    for wrapper in ("items", "data", "results", "value", "records"):
        assert _records({wrapper: expected}) == expected
    assert _records({"id": "single-record"}) == [{"id": "single-record"}]
