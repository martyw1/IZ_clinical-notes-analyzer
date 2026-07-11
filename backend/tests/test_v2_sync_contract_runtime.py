from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

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
                "treatment_plans": {"path": "/plans", "parameters": {"limit": "page_size", "offset": "page_start"}, "field_mappings": {"client_id": "owner_id", "plan_id": "plan_key"}},
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
        "status": "active",
    }
    assert _mapped_text({"member_id": "client-912"}, contract, "clients", "client_id") == "client-912"


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
