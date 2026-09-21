from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest


def test_transport_timeout_retries_and_returns_success_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.v2.services.alleva_sync import _get_with_retry

    request_count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            raise httpx.ReadTimeout("synthetic-private-timeout", request=request)
        return httpx.Response(200, request=request, json={"items": []})

    monkeypatch.setattr("app.v2.services.alleva_sync._wait_for_retry", lambda *_args: None)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = _get_with_retry(
            client,
            "https://synthetic.invalid/treatment-plans",
            None,
            {},
            lambda: False,
            0,
            endpoint_key="treatment_plans",
        )

    assert request_count == 2
    assert response.extensions["alleva_attempt_count"] == 2
    assert response.extensions["alleva_retry_count"] == 1
    assert response.extensions["alleva_retry_outcome"] == "succeeded_after_retry"


def test_transport_timeout_exhaustion_records_safe_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.v2.services.alleva_sync import AllevaSyncError, _get_with_retry

    request_count = 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout("synthetic-private-token-and-plan-id", request=request)

    monkeypatch.setattr("app.v2.services.alleva_sync._wait_for_retry", lambda *_args: None)
    with httpx.Client(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(AllevaSyncError) as captured:
            _get_with_retry(
                client,
                "https://synthetic.invalid/treatment-plans/private-plan",
                None,
                {"authorization": "Bearer private-token"},
                lambda: False,
                0,
                endpoint_key="treatment_plans",
            )

    details = captured.value.audit_details()
    assert request_count == 3
    assert details["attempt_count"] == 3
    assert details["retry_count"] == 2
    assert details["retry_outcome"] == "exhausted"
    assert details["cause_class"] == "ReadTimeout"
    assert details["endpoint_key"] == "treatment_plans"
    assert "private-plan" not in str(details)
    assert "private-token" not in str(details)
    assert "synthetic-private" not in str(details)


def test_transport_retry_cancellation_remains_typed_and_stops_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.v2.services.alleva_sync import AllevaSyncCancelled, _get_with_retry

    request_count = 0
    cancelled = False

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout("synthetic-private-timeout", request=request)

    def cancel_during_delay(_delay_seconds: int, _is_cancelled: Callable[[], bool]) -> None:
        nonlocal cancelled
        cancelled = True
        raise AllevaSyncCancelled("Cancelled during synthetic retry delay.")

    monkeypatch.setattr(
        "app.v2.services.alleva_sync._wait_for_retry",
        cancel_during_delay,
    )
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(AllevaSyncCancelled) as captured:
            _get_with_retry(
                client,
                "https://synthetic.invalid/clients",
                None,
                {},
                lambda: cancelled,
                1,
                endpoint_key="clients",
            )

    details = captured.value.audit_details()
    assert request_count == 1
    assert details["failure_stage"] == "collection_request"
    assert details["endpoint_key"] == "clients"
    assert details["attempt_count"] == 1
    assert details["retry_count"] == 0
    assert details["retry_outcome"] == "cancelled"


def test_oversized_response_is_not_retried() -> None:
    from app.v2.services.alleva_sync import AllevaSyncError, _get_with_retry

    request_count = 0

    def oversized(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, request=request, content=b"oversized-private-payload")

    with httpx.Client(transport=httpx.MockTransport(oversized)) as client:
        with pytest.raises(AllevaSyncError) as captured:
            _get_with_retry(
                client,
                "https://synthetic.invalid/clients",
                None,
                {},
                lambda: False,
                0,
                maximum_response_bytes=4,
                endpoint_key="clients",
            )

    details = captured.value.audit_details()
    assert request_count == 1
    assert details["attempt_count"] == 1
    assert details["retry_count"] == 0
    assert details["retry_outcome"] == "not_retryable"
    assert details["cause_class"] == "ResponseTooLarge"
    assert "oversized-private-payload" not in str(details)


@pytest.mark.parametrize("url", ["not a URL", "http://"])
def test_permanent_url_errors_are_not_retried(url: str) -> None:
    from app.v2.services.alleva_sync import AllevaSyncError, _get_with_retry

    transport_calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(200, request=request, json={"items": []})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(AllevaSyncError) as captured:
            _get_with_retry(client, url, None, {}, lambda: False, 0)

    details = captured.value.audit_details()
    assert transport_calls == 1
    assert details["attempt_count"] == 1
    assert details["retry_count"] == 0
    assert details["retry_outcome"] == "not_retryable"
