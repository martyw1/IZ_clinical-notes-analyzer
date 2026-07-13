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
