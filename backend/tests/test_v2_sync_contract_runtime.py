from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.v2.api.models import AllevaContractApprovalIn
from app.v2.services.alleva_contracts import ApprovedAllevaContract


def _contract() -> ApprovedAllevaContract:
    payload = AllevaContractApprovalIn.model_validate(
        {
            "contract_version": "synthetic-runtime-contract-v1",
            "api_base_url": "https://synthetic.invalid",
            "effective_at": "2026-07-10T00:00:00+00:00",
            "vendor_documentation_url": "https://vendor.invalid/docs/synthetic",
            "test_population_reference": "synthetic-population",
            "oauth": {"token_url": "https://synthetic.invalid/token", "token_auth_style": "body", "scope": "plans.read"},
            "pagination": {"limit_parameter": "limit", "offset_parameter": "offset", "maximum_page_size": 2, "maximum_records": 8, "maximum_response_bytes": 1048576},
            "rate_limit": {"maximum_requests_per_minute": 2, "retry_after_seconds": 1},
            "attachments": {"mode": "metadata_only", "download_allowed": False},
            "endpoints": {
                "clients": {"path": "/clients", "parameters": {"limit": "page_size", "offset": "page_start", "status": "active"}, "field_mappings": {"client_id": "member_id"}},
                "treatment_plans": {"path": "/plans", "parameters": {"limit": "page_size", "offset": "page_start", "client_id": "ClientId"}, "field_mappings": {"client_id": "owner_id", "client_reference": "owner_route", "plan_id": "plan_key"}},
                "treatment_plan_detail": {"path": "/plans/{plan_id}", "parameters": {}, "field_mappings": {"signature_date": "signed_at"}},
                "diagnoses": {"path": "/plans/{plan_id}/diagnoses", "parameters": {}, "field_mappings": {"description": "label"}},
                "reviews": {"path": "/plans/{plan_id}/reviews", "parameters": {}, "field_mappings": {"review_id": "review_key"}},
                "review_detail": {"path": "/plans/{plan_id}/reviews/{review_id}", "parameters": {}, "field_mappings": {"review_date": "reviewed_at"}},
            },
        }
    )
    return ApprovedAllevaContract(7, payload.contract_version, "a" * 64, datetime.now(timezone.utc), datetime.now(timezone.utc), payload)


def test_contract_parameter_and_field_mapping_drive_paged_requests() -> None:
    from app.v2.services.alleva_sync import _endpoint_request_parameters, _mapped_text

    contract = _contract()

    assert _endpoint_request_parameters(contract, "clients", limit=2, offset=4) == {
        "page_size": 2,
        "page_start": 4,
        "api-version": "1.0",
        "status": "active",
    }
    assert _endpoint_request_parameters(
        contract,
        "treatment_plans",
        limit=2,
        offset=4,
        additional_parameters={"client_id": "client-912"},
    ) == {
        "page_size": 2,
        "page_start": 4,
        "api-version": "1.0",
        "StartDate": "2000-01-01T16:03",
        "ClientId": "client-912",
    }
    assert _mapped_text({"member_id": "client-912"}, contract, "clients", "client_id") == "client-912"


def test_contract_field_mapping_reads_nested_numeric_alleva_ids() -> None:
    # Given: the nested numeric client link published for Alleva treatment plans.
    from app.v2.services.alleva_sync import _mapped_text

    payload = _contract().payload.model_copy(
        update={
            "endpoints": {
                **_contract().payload.endpoints,
                "treatment_plans": _contract().payload.endpoints["treatment_plans"].model_copy(
                    update={"field_mappings": {"client_id": "client.id", "plan_id": "id"}}
                ),
            }
        }
    )
    contract = ApprovedAllevaContract(
        7,
        payload.contract_version,
        "a" * 64,
        datetime.now(timezone.utc),
        datetime.now(timezone.utc),
        payload,
    )

    # When: the importer reads the plan-to-patient relationship and plan identifier.
    client_id = _mapped_text({"client": {"id": 912}, "id": 4815}, contract, "treatment_plans", "client_id")
    plan_id = _mapped_text({"client": {"id": 912}, "id": 4815}, contract, "treatment_plans", "plan_id")

    # Then: numeric identifiers are normalized to stable strings.
    assert client_id == "912"
    assert plan_id == "4815"


def test_plan_ownership_requires_returned_relationship_to_match_queried_patient() -> None:
    from app.v2.services.alleva_sync import _plan_belongs_to_patient

    contract = _contract()

    assert _plan_belongs_to_patient(
        {"owner_id": "client-912", "owner_route": "/clients/client-912"},
        "client-912",
        contract,
    )
    assert not _plan_belongs_to_patient(
        {"owner_id": "client-912", "owner_route": "/clients/client-999"},
        "client-912",
        contract,
    )
    assert not _plan_belongs_to_patient({}, "client-912", contract)


def test_contract_rate_ceiling_waits_before_exceeding_approved_request_rate() -> None:
    from app.v2.services.alleva_sync import ApprovedRequestRateLimiter

    current_time = [0.0]
    waits: list[float] = []

    def sleep_for(seconds: float) -> None:
        waits.append(seconds)
        current_time[0] += seconds

    limiter = ApprovedRequestRateLimiter(2, clock=lambda: current_time[0], sleep=sleep_for)
    limiter.acquire(lambda: False)
    limiter.acquire(lambda: False)

    assert round(sum(waits), 6) == 30.0
    assert max(waits) <= 0.1


def test_contract_rate_ceiling_never_sleeps_negative_when_clock_advances_between_reads() -> None:
    from app.v2.services.alleva_sync import ApprovedRequestRateLimiter

    timestamps = iter((0.0, 29.95, 30.01, 30.01, 30.01))
    waits: list[float] = []

    def sleep_for(seconds: float) -> None:
        waits.append(seconds)
        assert seconds >= 0.0

    limiter = ApprovedRequestRateLimiter(2, clock=lambda: next(timestamps), sleep=sleep_for)
    limiter.acquire(lambda: False)
    limiter.acquire(lambda: False)

    assert waits == []


def test_resumed_page_fetch_starts_after_persisted_checkpoint_without_offset_zero_replay() -> None:
    from app.v2.services.alleva_contracts import SyncCheckpointPage
    from app.v2.services.alleva_sync import _paged_records

    contract = _contract()
    requested_offsets: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_offsets.append(request.url.params["page_start"])
        return httpx.Response(200, json={"items": [{"member_id": "client-3"}]})

    checkpoints = (
        SyncCheckpointPage(
            endpoint_key="clients",
            page_number=0,
            cursor_hash="cursor-0",
            response_shape_sha256="shape-0",
            records=({"member_id": "client-1"}, {"member_id": "client-2"}),
        ),
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        records = _paged_records(
            http_client,
            SimpleNamespace(api_base_url="https://synthetic.invalid"),
            contract,
            "clients",
            {},
            lambda: False,
            None,
            checkpoints,
            None,
        )

    assert requested_offsets == ["2"]
    assert records == ({"member_id": "client-1"}, {"member_id": "client-2"}, {"member_id": "client-3"})


def test_retry_exhaustion_preserves_safe_endpoint_diagnostics_without_request_data() -> None:
    # Given: a protected collection endpoint that exhausts the existing three-attempt retry budget.
    from app.v2.services.alleva_sync import AllevaSyncError, _get_with_retry

    seen_requests: list[httpx.Request] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(503, request=request, text="secret=do-not-log&patient=private-id")

    # When: the bounded retry helper reaches its terminal response.
    with httpx.Client(transport=httpx.MockTransport(unavailable)) as http_client:
        with pytest.raises(AllevaSyncError) as captured:
            _get_with_retry(
                http_client,
                "https://synthetic.invalid/clients/private-id",
                {"patient": "private-id"},
                {"authorization": "Bearer do-not-log"},
                lambda: False,
                0,
                endpoint_key="clients",
                failure_stage="collection_request",
            )

    # Then: operators get the safe request stage/status/counts, without URL, IDs, headers, or body text.
    details = captured.value.audit_details()
    request_duration_ms = details.pop("request_duration_ms")
    assert isinstance(request_duration_ms, int) and request_duration_ms >= 0
    assert details == {
        "error_class": "AllevaSyncError",
        "failure_stage": "collection_request",
        "endpoint_key": "clients",
        "http_status": 503,
        "attempt_count": 3,
        "retry_count": 2,
        "retry_outcome": "exhausted",
    }
    assert len(seen_requests) == 3
    assert "private-id" not in str(details)
    assert "do-not-log" not in str(details)


def test_oauth_failure_is_distinct_from_protected_endpoint_failure(monkeypatch) -> None:
    # Given: the OAuth endpoint rejects a request whose inputs contain synthetic secrets.
    from app.v2.services import oauth_connectivity

    request = httpx.Request("POST", "https://synthetic.invalid/token/private-client")
    monkeypatch.setattr(
        oauth_connectivity,
        "post_bounded",
        lambda *_args, **_kwargs: httpx.Response(
            401,
            request=request,
            text="private-client private-secret patient-private",
        ),
    )

    # When: OAuth connectivity runs through the real response classifier.
    result, token = oauth_connectivity.request_client_credentials(
        token_url=str(request.url),
        client_id="private-client",
        client_secret="private-secret",
        scope="patient-private.read",
        token_auth_style="body",
        timeout_seconds=5,
    )

    # Then: its metadata identifies OAuth, and exposes no URL, secret, scope, or response body.
    assert token == ""
    assert result.failure_stage == "oauth_request"
    assert result.endpoint_key == "oauth"
    assert result.http_status == 401
    assert result.attempt_count == 1
    assert result.retry_count == 0
    assert result.retry_outcome == "not_attempted"
    assert result.cause_class == "HTTPStatusError"
    assert result.duration_ms is not None and result.duration_ms >= 0
    assert "private-client" not in repr(result)
    assert "private-secret" not in repr(result)
    assert "patient-private" not in repr(result)


def test_roster_pull_preserves_collection_failure_context(monkeypatch) -> None:
    # Given: roster OAuth succeeds and its first clients request has safe structured failure context.
    from app.v2.services import alleva_roster
    from app.v2.services.alleva_sync import AllevaSyncError

    failure = AllevaSyncError(
        "Safe collection failure.",
        failure_stage="collection_request",
        endpoint_key="clients",
        http_status=503,
        request_duration_ms=12,
        attempt_count=3,
        retry_count=2,
        retry_outcome="exhausted",
    )
    monkeypatch.setattr(alleva_roster, "_oauth_token", lambda *_args: "synthetic-token")
    monkeypatch.setattr(alleva_roster, "_get_with_retry", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))
    profile = SimpleNamespace(
        alleva_api_version="1.0",
        alleva_treatment_plan_start_date="2000-01-01T16:03",
        emr_api_timeout_seconds=5,
        api_base_url="https://synthetic.invalid",
    )

    # When: the roster service has no safe records to retain.
    with pytest.raises(AllevaSyncError) as captured:
        alleva_roster.run_roster_pull(
            None,
            profile,
            _contract(),
            "roster-synthetic",
            "2026-09-21T00:00:00+00:00",
        )

    # Then: the original collection stage, endpoint, status, and retry outcome remain available.
    assert captured.value is failure
    assert captured.value.audit_details()["failure_stage"] == "collection_request"
    assert captured.value.audit_details()["endpoint_key"] == "clients"
    assert captured.value.audit_details()["http_status"] == 503
    assert captured.value.audit_details()["retry_outcome"] == "exhausted"


def test_detail_request_failure_uses_endpoint_key_without_plan_or_secret(monkeypatch) -> None:
    # Given: a treatment-plan detail endpoint rejects a request containing a synthetic private plan ID.
    from app.v2.services.alleva_sync import AllevaSyncError, ApprovedRequestRateLimiter, _endpoint_json

    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request, text="private-plan secret-token clinical-private")

    # When: the detail helper classifies the protected response.
    with httpx.Client(transport=httpx.MockTransport(reject)) as http_client:
        with pytest.raises(AllevaSyncError) as captured:
            _endpoint_json(
                http_client,
                "https://synthetic.invalid",
                _contract(),
                "treatment_plan_detail",
                {"authorization": "Bearer secret-token"},
                lambda: False,
                ApprovedRequestRateLimiter(10_000),
                plan_id="private-plan",
            )

    # Then: the loggable fields identify the mapped endpoint, while excluding request and clinical content.
    details = captured.value.audit_details()
    assert details["failure_stage"] == "detail_request"
    assert details["endpoint_key"] == "treatment_plan_detail"
    assert details["http_status"] == 404
    assert details["attempt_count"] == 1
    assert details["retry_count"] == 0
    assert details["retry_outcome"] == "not_retryable"
    assert "private-plan" not in str(details)
    assert "secret-token" not in str(details)
    assert "clinical-private" not in str(details)
