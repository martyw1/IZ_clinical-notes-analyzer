from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from app.desktop_lifecycle import RuntimeGate
from app.desktop_runtime_authority import RuntimeAuthority, authorize_runtime
from app.desktop_runtime_contracts import RuntimeIdentity
from app.desktop_runtime_control import CONTROL_RESPONSE_KEYS, RuntimeController
from test_desktop_runtime_authority import (
    TX,
    RuntimeFixture,
    clear_profile_environment,
    make_runtime_fixture,
)


def identity_for(authority: RuntimeAuthority, transaction_id: str | None) -> RuntimeIdentity:
    return RuntimeIdentity(
        schema="iz-cna-runtime-identity-v1",
        product_id="r3.iz-clinical-notes-analyzer.desktop",
        owner_sid=authority.owner_sid,
        scope_id=authority.scope_id,
        data_identity=authority.data_identity,
        instance_id="202030405060708090a0b0c0d0e0f001",
        transaction_id=transaction_id,
        process_id=1234,
        process_started_utc="2026-09-14T12:00:00Z",
        executable_path=str(authority.paths.executable_path),
        executable_sha256="c" * 64,
        version=authority.release.version,
        build=authority.release.build,
        installer_revision=authority.release.installer_revision,
        port=8123,
        pipe_name="iz-cna-runtime-v1-" + authority.scope_id[:32],
        gate="maintenance" if transaction_id else "open",
        draining=False,
        created_utc="2026-09-14T12:00:01Z",
    )


def request(operation: str, transaction_id: str | None) -> bytes:
    return json.dumps(
        {
            "schema": "iz-cna-runtime-control-v1",
            "request_id": "302030405060708090a0b0c0d0e0f001",
            "operation": operation,
            "transaction_id": transaction_id,
        },
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def decode(response: bytes | None) -> dict[str, object]:
    assert response is not None and response.endswith(b"\n")
    value = json.loads(response)
    assert isinstance(value, dict)
    return value


def candidate_controller(tmp_path: Path) -> tuple[RuntimeFixture, RuntimeController, threading.Event]:
    fixture = make_runtime_fixture(tmp_path)
    authority = authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)
    shutdown = threading.Event()
    controller = RuntimeController(
        authority=authority,
        identity=identity_for(authority, TX),
        gate=RuntimeGate("maintenance"),
        request_shutdown=shutdown.set,
        drain_timeout_seconds=0.2,
    )
    return fixture, controller, shutdown


def test_status_response_has_exact_frozen_keys(tmp_path: Path) -> None:
    _, controller, _ = candidate_controller(tmp_path)

    response = decode(controller.handle_message(request("status", TX)))

    assert set(response) == CONTROL_RESPONSE_KEYS
    assert response["status"] == "ok"
    assert response["reason"] == "status"
    assert response["gate"] == "maintenance"
    assert response["active_business_requests"] == 0


def test_wrong_transaction_cannot_control_candidate(tmp_path: Path) -> None:
    _, controller, shutdown = candidate_controller(tmp_path)

    response = decode(controller.handle_message(request("shutdown", "f" * 32)))

    assert response["status"] == "blocked"
    assert response["reason"] == "transaction_mismatch"
    assert not shutdown.is_set()


def test_drain_closes_gate_and_waits_for_active_work(tmp_path: Path) -> None:
    _, controller, _ = candidate_controller(tmp_path)
    controller.gate.release()
    assert controller.gate.enter_business_request()
    response_holder: list[dict[str, object]] = []
    thread = threading.Thread(
        target=lambda: response_holder.append(decode(controller.handle_message(request("drain", TX))))
    )
    thread.start()
    assert controller.gate.wait_until_closed(2)
    controller.gate.leave_business_request()
    thread.join(2)

    assert response_holder[0]["status"] == "ok"
    assert response_holder[0]["reason"] == "drained"
    assert response_holder[0]["draining"] is True
    assert response_holder[0]["active_business_requests"] == 0


def test_shutdown_requests_uvicorn_exit_only_after_drain(tmp_path: Path) -> None:
    _, controller, shutdown = candidate_controller(tmp_path)

    response = decode(controller.handle_message(request("shutdown", TX)))

    assert response["status"] == "ok"
    assert response["reason"] == "shutdown_requested"
    assert shutdown.is_set()


def test_commit_releases_gate_only_after_durable_journal_and_receipt(tmp_path: Path) -> None:
    fixture, controller, _ = candidate_controller(tmp_path)
    blocked = decode(controller.handle_message(request("commit", TX)))
    assert blocked["status"] == "blocked"
    assert controller.gate.snapshot().gate == "maintenance"
    fixture.write_receipt()
    fixture.journal["state"] = "COMMITTED"
    fixture.journal["completed_steps"] = ["NEW_PROGRAM_MOVED", "INSTALL_RECEIPT_WRITTEN", "COMMIT_RECORDED"]
    fixture.write_journal()

    committed = decode(controller.handle_message(request("commit", TX)))

    assert committed["status"] == "ok", committed
    assert committed["reason"] == "committed"
    assert committed["gate"] == "open"
    assert committed["draining"] is False


@pytest.mark.parametrize("message", [b"not-json\n", b"{}", b"{}\n{}\n"])
def test_invalid_control_message_gets_no_response(tmp_path: Path, message: bytes) -> None:
    _, controller, _ = candidate_controller(tmp_path)

    assert controller.handle_message(message) is None
