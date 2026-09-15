from __future__ import annotations

import json
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_lifecycle import (
    ControlProtocolError,
    MaintenanceGateMiddleware,
    RuntimeControlRequest,
    RuntimeGate,
    is_maintenance_safe_path,
    parse_control_request,
)


@pytest.mark.parametrize(
    "path",
    ["/", "/assets/index.js", "/api/health", "/health", "/api/readiness", "/api/version"],
)
def test_candidate_allowlist_contains_static_and_status_paths(path: str) -> None:
    assert is_maintenance_safe_path(path)


@pytest.mark.parametrize(
    "path",
    ["/api/auth/login", "/api/v2/treatment-plans", "/api/v2/jobs", "/docs", "/openapi.json"],
)
def test_candidate_blocks_business_and_discovery_paths(path: str) -> None:
    assert not is_maintenance_safe_path(path)


def gated_app(gate: RuntimeGate) -> FastAPI:
    app = FastAPI()
    app.add_middleware(MaintenanceGateMiddleware, gate=gate)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/business")
    def business() -> dict[str, str]:
        return {"status": "business"}

    return app


def test_candidate_serves_health_and_rejects_business() -> None:
    gate = RuntimeGate(initial_gate="maintenance")

    with TestClient(gated_app(gate)) as client:
        assert client.get("/api/health").status_code == 200
        blocked = client.get("/api/business")

    assert blocked.status_code == 503
    assert blocked.json() == {"detail": "maintenance_in_progress"}
    assert gate.snapshot().active_business_requests == 0


def test_open_gate_counts_active_business_requests_until_completion() -> None:
    gate = RuntimeGate(initial_gate="open")
    entered = threading.Event()
    release = threading.Event()
    app = FastAPI()
    app.add_middleware(MaintenanceGateMiddleware, gate=gate)

    @app.get("/api/business")
    def business() -> dict[str, str]:
        entered.set()
        assert release.wait(5)
        return {"status": "business"}

    with TestClient(app) as client:
        response_status: list[int] = []

        def invoke() -> None:
            response_status.append(client.get("/api/business").status_code)

        request_thread = threading.Thread(target=invoke)
        request_thread.start()
        assert entered.wait(5)
        assert gate.snapshot().active_business_requests == 1
        release.set()
        request_thread.join(5)

    assert response_status == [200]
    assert gate.snapshot().active_business_requests == 0


def test_drain_closes_gate_before_waiting_for_active_request() -> None:
    gate = RuntimeGate(initial_gate="open")
    request_started = threading.Event()
    request_release = threading.Event()
    app = FastAPI()
    app.add_middleware(MaintenanceGateMiddleware, gate=gate)

    @app.get("/api/business")
    def business() -> dict[str, str]:
        request_started.set()
        assert request_release.wait(5)
        return {"status": "business"}

    with TestClient(app) as client:
        request_thread = threading.Thread(target=lambda: client.get("/api/business"))
        request_thread.start()
        assert request_started.wait(5)
        drained: list[bool] = []
        drain_thread = threading.Thread(target=lambda: drained.append(gate.drain(5)))
        drain_thread.start()
        assert gate.wait_until_closed(5)
        assert client.get("/api/business").status_code == 503
        snapshot = gate.snapshot()
        assert snapshot.gate == "maintenance"
        assert snapshot.draining
        assert snapshot.active_business_requests == 1
        request_release.set()
        request_thread.join(5)
        drain_thread.join(5)

    assert drained == [True]
    assert gate.snapshot().active_business_requests == 0


def test_control_request_accepts_exact_utf8_json_line() -> None:
    request_id = "102030405060708090a0b0c0d0e0f001"
    line = json.dumps(
        {
            "schema": "iz-cna-runtime-control-v1",
            "request_id": request_id,
            "operation": "status",
            "transaction_id": None,
        },
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"

    request = parse_control_request(line)

    assert request == RuntimeControlRequest(
        schema="iz-cna-runtime-control-v1",
        request_id=request_id,
        operation="status",
        transaction_id=None,
    )


@pytest.mark.parametrize(
    "line",
    [
        b"{}",
        b"{}\ntrailing",
        b"{not-json}\n",
        b'{"schema":"iz-cna-runtime-control-v1","request_id":"BAD","operation":"status","transaction_id":null}\n',
        b'{"schema":"iz-cna-runtime-control-v1","request_id":"102030405060708090a0b0c0d0e0f001","operation":"status","transaction_id":null,"extra":true}\n',
        b'{"schema":"iz-cna-runtime-control-v1","request_id":"102030405060708090a0b0c0d0e0f001","request_id":"102030405060708090a0b0c0d0e0f001","operation":"status","transaction_id":null}\n',
    ],
)
def test_control_request_rejects_malformed_or_non_exact_lines(line: bytes) -> None:
    with pytest.raises(ControlProtocolError):
        parse_control_request(line)


def test_control_request_rejects_oversize_message() -> None:
    with pytest.raises(ControlProtocolError):
        parse_control_request(b"x" * 16_385 + b"\n")
