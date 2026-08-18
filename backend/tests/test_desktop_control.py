from __future__ import annotations

# noqa: SIZE_OK -- Task 4's middleware and exact stop-budget attack matrix is one security contract.

import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _Lease:
    def __init__(self, canonical_id: str) -> None:
        self.canonical_data_dir_id = canonical_id
        self.held = True
        self.native_identity_valid = True

    def is_held_by_current_process(self) -> bool:
        return self.held

    def validate_native_identity(self) -> bool:
        return self.held and self.native_identity_valid

    def release(self) -> None:
        self.held = False


class _IdentityProvider:
    def __init__(self, identity) -> None:
        self.identity = identity
        self.lookups: list[int] = []

    def identity_for_pid(self, pid: int):
        self.lookups.append(pid)
        return self.identity


class _Shutdown:
    def __init__(self) -> None:
        self.run_ids: list[str] = []

    def request_shutdown(self, run_id: str) -> None:
        self.run_ids.append(run_id)


class _Denials:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    def record(self, reason) -> None:
        self.reasons.append(reason.value)


def _identity():
    from app.desktop.process_identity import (
        DesktopPlatform,
        ExecutablePathPolicy,
        ProcessIdentity,
        normalize_executable_path,
    )

    platform = DesktopPlatform.WINDOWS if os.name == "nt" else DesktopPlatform.MACOS
    return ProcessIdentity(
        pid=os.getpid(),
        creation_time_epoch_ns=1_786_999_000_000_000_000,
        executable_path=normalize_executable_path(
            sys.executable,
            ExecutablePathPolicy(platform=platform, case_sensitive=False),
        ),
    )


def _state(
    *,
    token: str = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE",
    run_id: str = "12345678-1234-4234-9234-123456789abc",
):
    from app.desktop.runtime_state import DesktopRuntimeState

    identity = _identity()
    return DesktopRuntimeState(
        schema_version=1,
        data_dir_id="volume|synthetic-profile",
        run_id=run_id,
        control_token=token,
        pid=identity.pid,
        process_creation_time_epoch_ns=identity.creation_time_epoch_ns,
        executable_path=identity.executable_path,
        port=8123,
        started_at_epoch_ns=1_786_999_100_000_000_000,
        ready=True,
    )


@dataclass(frozen=True, slots=True)
class _Harness:
    state_box: list
    lease: _Lease
    identities: _IdentityProvider
    shutdown: _Shutdown
    denials: _Denials
    app: FastAPI


def _harness() -> _Harness:
    from app.desktop.control import DesktopControlContext, DesktopControlMiddleware

    state = _state()
    state_box = [state]
    lease = _Lease(state.data_dir_id)
    identities = _IdentityProvider(state.process_identity)
    shutdown = _Shutdown()
    denials = _Denials()
    context = DesktopControlContext(lambda: state_box[0], lease, identities, shutdown, denials)
    app = FastAPI()

    @app.get("/api/example")
    def example() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(DesktopControlMiddleware, context=context)
    return _Harness(state_box, lease, identities, shutdown, denials, app)


def _headers(state=None) -> dict[str, str]:
    active = state or _state()
    return {
        "Host": f"127.0.0.1:{active.port}",
        "Content-Type": "application/json",
        "X-IZ-Desktop-Control": active.control_token,
        "X-IZ-Data-Dir-ID": active.data_dir_id,
    }


def test_authenticated_loopback_status_and_stop_target_only_the_current_run() -> None:
    # Given: one live synthetic runtime behind middleware-only control paths.
    harness = _harness()
    state = harness.state_box[0]

    # When: an authenticated loopback caller requests status and stop.
    with TestClient(harness.app, client=("127.0.0.1", 50123)) as client:
        status = client.post("/_desktop/control/status", headers=_headers(state), json={})
        stop = client.post("/_desktop/control/stop", headers=_headers(state), json={})

    # Then: status is safe, stop is accepted once, and no token is returned.
    assert status.status_code == 200
    assert status.json()["run_id"] == state.run_id
    assert status.json()["data_dir_id"] == state.data_dir_id
    assert state.control_token not in status.text + stop.text
    assert stop.status_code == 202
    assert harness.shutdown.run_ids == [state.run_id]


def test_authenticated_control_works_over_a_real_loopback_socket() -> None:
    # Given: the middleware is served by a real ASGI listener bound only to loopback.
    import uvicorn

    harness = _harness()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    state = type(harness.state_box[0])(**{**harness.state_box[0].to_mapping(), "port": port})
    harness.state_box[0] = state
    server = uvicorn.Server(uvicorn.Config(harness.app, log_config=None, access_log=False, lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5.0
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)

    try:
        # When: a stdlib HTTP client sends authenticated status and stop requests through TCP.
        connection = HTTPConnection("127.0.0.1", port, timeout=2.0)
        connection.request("POST", "/_desktop/control/status", body=b"{}", headers=_headers(state))
        status = connection.getresponse()
        status_body = status.read().decode("utf-8")
        connection.request("POST", "/_desktop/control/stop", body=b"{}", headers=_headers(state))
        stop = connection.getresponse()
        stop_body = stop.read().decode("utf-8")
        connection.close()

        # Then: the live listener returns the current run, never echoes its token, and signals once.
        assert status.status == 200
        assert stop.status == 202
        assert state.run_id in status_body
        assert state.control_token not in status_body + stop_body
        assert harness.shutdown.run_ids == [state.run_id]
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
        listener.close()
    assert not thread.is_alive()


@pytest.mark.parametrize("token", (None, "wrong-token"), ids=("missing", "wrong"))
def test_wrong_token_is_denied_without_shutdown_or_secret_logging(token: str | None) -> None:
    # Given: a missing or incorrect control token.
    harness = _harness()
    state = harness.state_box[0]
    headers = _headers(state)
    if token is None:
        headers.pop("X-IZ-Desktop-Control")
    else:
        headers["X-IZ-Desktop-Control"] = token

    # When: the caller attempts stop.
    with TestClient(harness.app, client=("127.0.0.1", 50123)) as client:
        response = client.post("/_desktop/control/stop", headers=headers, json={})

    # Then: authentication fails safely and the observer receives only a fixed reason code.
    assert response.status_code == 401
    assert harness.shutdown.run_ids == []
    assert harness.denials.reasons == ["desktop_control_token_invalid"]
    assert state.control_token not in repr(harness.denials.reasons)


@pytest.mark.parametrize("data_dir_id", (None, "volume|other-profile"), ids=("missing", "cross-profile"))
def test_cross_data_dir_is_denied_before_shutdown(data_dir_id: str | None) -> None:
    # Given: a valid token replayed with a missing or different profile identity.
    harness = _harness()
    headers = _headers(harness.state_box[0])
    if data_dir_id is None:
        headers.pop("X-IZ-Data-Dir-ID")
    else:
        headers["X-IZ-Data-Dir-ID"] = data_dir_id

    # When: stop is attempted across profiles.
    with TestClient(harness.app, client=("127.0.0.1", 50123)) as client:
        response = client.post("/_desktop/control/stop", headers=headers, json={})

    # Then: the request is forbidden and no shutdown signal crosses the boundary.
    assert response.status_code == 403
    assert harness.shutdown.run_ids == []
    assert harness.denials.reasons == ["desktop_control_data_dir_mismatch"]


@pytest.mark.parametrize(
    ("method", "content_type", "body"),
    (
        ("GET", "application/json", b"{}"),
        ("POST", "application/x-www-form-urlencoded", b""),
        ("POST", "text/plain", b"{}"),
        ("POST", "application/json", b"x" * 1025),
        ("POST", "application/json", b'{"extra":true}'),
    ),
    ids=("get", "simple-form", "simple-text", "oversized", "non-empty-json"),
)
def test_simple_request_get_form_and_oversized_bodies_are_rejected(method: str, content_type: str, body: bytes) -> None:
    # Given: a CSRF-like/simple/malformed request shape.
    harness = _harness()
    headers = _headers(harness.state_box[0])
    headers["Content-Type"] = content_type

    # When: it targets the stop path.
    with TestClient(harness.app, client=("127.0.0.1", 50123)) as client:
        response = client.request(method, "/_desktop/control/stop", headers=headers, content=body)

    # Then: validation fails without signaling the coordinator.
    assert response.status_code == 400
    assert harness.shutdown.run_ids == []
    assert len(harness.denials.reasons) == 1


@pytest.mark.parametrize(
    ("client_address", "host"),
    (("203.0.113.9", "127.0.0.1:8123"), ("127.0.0.1", "127.0.0.1:9999"), ("127.0.0.1", "example.invalid:8123")),
    ids=("non-loopback", "wrong-port", "wrong-host"),
)
def test_non_loopback_or_wrong_host_is_forbidden(client_address: str, host: str) -> None:
    # Given: a non-loopback client or Host not bound to the active port.
    harness = _harness()
    headers = _headers(harness.state_box[0])
    headers["Host"] = host

    # When: the request reaches the ASGI middleware.
    with TestClient(harness.app, client=(client_address, 50123)) as client:
        response = client.post("/_desktop/control/status", headers=headers, json={})

    # Then: it is denied before runtime state is disclosed.
    assert response.status_code == 403
    assert "run_id" not in response.text


def test_stale_run_replay_and_pid_reuse_fail_closed_without_touching_process() -> None:
    # Given: a fresh run replaces the old token, then its PID is synthetically reused.
    from app.desktop.process_identity import ProcessIdentity

    harness = _harness()
    old_state = harness.state_box[0]
    fresh_state = _state(
        token="YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI",
        run_id="22345678-1234-4234-9234-123456789abc",
    )
    harness.state_box[0] = fresh_state
    old_headers = _headers(old_state)

    # When: the old request is replayed and then current credentials face a reused PID.
    with TestClient(harness.app, client=("127.0.0.1", 50123)) as client:
        replay_status = client.post("/_desktop/control/status", headers=old_headers, json={})
        replay_stop = client.post("/_desktop/control/stop", headers=old_headers, json={})
        harness.identities.identity = ProcessIdentity(
            fresh_state.pid,
            fresh_state.process_creation_time_epoch_ns + 1,
            fresh_state.executable_path,
        )
        reused = client.post("/_desktop/control/stop", headers=_headers(fresh_state), json={})

    # Then: neither request signals shutdown or trusts PID alone.
    assert (replay_status.status_code, replay_stop.status_code) == (401, 401)
    assert reused.status_code == 409
    assert harness.shutdown.run_ids == []


def test_native_lease_identity_loss_blocks_status_and_stop() -> None:
    # Given: the lease provider detects lock-file native identity replacement.
    harness = _harness()
    harness.lease.native_identity_valid = False

    # When: authenticated status and stop are requested.
    with TestClient(harness.app, client=("127.0.0.1", 50123)) as client:
        status = client.post("/_desktop/control/status", headers=_headers(harness.state_box[0]), json={})
        stop = client.post("/_desktop/control/stop", headers=_headers(harness.state_box[0]), json={})

    # Then: both conflict safely and no shutdown request is set.
    assert (status.status_code, stop.status_code) == (409, 409)
    assert harness.shutdown.run_ids == []


def test_control_paths_are_absent_from_business_routes_and_openapi() -> None:
    # Given: a business FastAPI application wrapped by the control middleware.
    harness = _harness()

    # When: route and OpenAPI surfaces are inspected.
    paths = {getattr(route, "path", "") for route in harness.app.routes}
    schema_paths = set(harness.app.openapi()["paths"])

    # Then: middleware control paths do not enter either business surface.
    assert not any(path.startswith("/_desktop/control/") for path in paths | schema_paths)
    assert "/api/example" in schema_paths


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class _Transport:
    def __init__(self, clock: _Clock, snapshot, *, status_code: int = 200) -> None:
        self.clock = clock
        self.snapshot = snapshot
        self.status_code = status_code
        self.status_times: list[float] = []
        self.stop_times: list[float] = []

    def status(self, request):
        from app.desktop.control import ControlHttpResponse

        self.status_times.append(self.clock.monotonic())
        return ControlHttpResponse(self.status_code, self.snapshot if self.status_code == 200 else None)

    def stop(self, request):
        from app.desktop.control import ControlHttpResponse

        self.stop_times.append(self.clock.monotonic())
        return ControlHttpResponse(202, self.snapshot)


class _Terminator:
    def __init__(self, clock: _Clock, identities: _IdentityProvider, *, kill_on_force: bool) -> None:
        self.clock = clock
        self.identities = identities
        self.kill_on_force = kill_on_force
        self.events: list[tuple[float, str]] = []

    def terminate_if_matches(self, identity, signal) -> bool:
        if self.identities.identity != identity:
            return False
        self.events.append((self.clock.monotonic(), signal.value))
        if self.kill_on_force and signal.value == "force":
            self.identities.identity = None
        return True


class _CooperativeTransport(_Transport):
    def __init__(self, clock: _Clock, snapshot, identities: _IdentityProvider) -> None:
        super().__init__(clock, snapshot)
        self.identities = identities

    def stop(self, request):
        response = super().stop(request)
        self.identities.identity = None
        return response


class _BudgetConsumingTransport(_Transport):
    def status(self, request):
        response = super().status(request)
        self.clock.value = 31.0
        return response


class _MemoryStateStore:
    def __init__(self, state) -> None:
        self.state = state
        self.removed_with_held_lease = False

    def read(self):
        return self.state

    def remove(self, lease) -> None:
        self.removed_with_held_lease = lease.is_held_by_current_process()
        self.state = None


class _Stores:
    def __init__(self, store: _MemoryStateStore) -> None:
        self.store = store

    def for_data_root(self, data_root: Path, canonical_data_dir_id: str):
        assert canonical_data_dir_id == self.store.state.data_dir_id
        return self.store


def _stop_client(platform, *, kill_on_force: bool = True, status_code: int = 200):
    from app.desktop.control import ControlStatusSnapshot, DesktopStopClient, StopClientDependencies

    state = _state()
    clock, identities = _Clock(), _IdentityProvider(state.process_identity)
    snapshot = ControlStatusSnapshot.from_state(state)
    transport = _Transport(clock, snapshot, status_code=status_code)
    terminator = _Terminator(clock, identities, kill_on_force=kill_on_force)
    client = DesktopStopClient(StopClientDependencies(transport, identities, terminator, clock, platform, 1.0))
    return state, clock, identities, transport, terminator, client


def test_windows_stop_client_revalidates_identity_at_second_twenty_before_force() -> None:
    # Given: a cooperative request whose synthetic Windows owner remains alive for 20 seconds.
    from app.desktop.process_identity import DesktopPlatform

    state, clock, _identities, transport, terminator, client = _stop_client(DesktopPlatform.WINDOWS)

    # When: the exact shared stop state machine runs.
    result = client.stop(state)

    # Then: request starts at zero, authenticated polling reaches 20, and force occurs only after revalidation.
    assert transport.stop_times == [0.0]
    assert transport.status_times[0] == 0.0
    assert 20.0 in transport.status_times
    assert terminator.events == [(20.0, "force")]
    assert result.outcome.value == "stopped"
    assert clock.monotonic() == 20.0


def test_macos_stop_client_uses_exact_twenty_twentyfive_and_thirty_second_boundaries() -> None:
    # Given: a synthetic macOS owner that survives both allowed signals.
    from app.desktop.process_identity import DesktopPlatform

    state, clock, _identities, transport, terminator, client = _stop_client(DesktopPlatform.MACOS, kill_on_force=False)

    # When: the one 30-second monotonic budget is exhausted.
    result = client.stop(state)

    # Then: SIGTERM-equivalent is at 20, force at 25, and exit confirmation ends exactly at 30.
    assert transport.stop_times == [0.0]
    assert 20.0 in transport.status_times
    assert terminator.events == [(20.0, "graceful"), (25.0, "force")]
    assert result.outcome.value == "timeout"
    assert result.elapsed_seconds == 30.0
    assert clock.monotonic() == 30.0


def test_pid_reuse_or_cross_run_status_prevents_stop_client_signals() -> None:
    # Given: stale process identity and cross-run authenticated status adversaries.
    from app.desktop.control import ControlStatusSnapshot
    from app.desktop.process_identity import DesktopPlatform, ProcessIdentity

    state, _clock, identities, transport, terminator, client = _stop_client(DesktopPlatform.WINDOWS)
    identities.identity = ProcessIdentity(state.pid, state.process_creation_time_epoch_ns + 1, state.executable_path)

    # When: stale PID reuse is evaluated before HTTP, then a cross-run response is evaluated.
    stale_result = client.stop(state)
    identities.identity = state.process_identity
    transport.snapshot = ControlStatusSnapshot.from_state(_state(run_id="32345678-1234-4234-9234-123456789abc"))
    cross_run_result = client.stop(state)

    # Then: neither path invokes termination or sends stop to an unrelated run.
    assert stale_result.outcome.value == "identity_mismatch"
    assert cross_run_result.outcome.value == "control_rejected"
    assert transport.stop_times == []
    assert terminator.events == []


def test_status_that_consumes_total_budget_never_sends_late_stop() -> None:
    # Given: initial authenticated status consumes more than the one total stop budget.
    from app.desktop.control import ControlStatusSnapshot, DesktopStopClient, StopClientDependencies
    from app.desktop.process_identity import DesktopPlatform

    state, clock = _state(), _Clock()
    identities = _IdentityProvider(state.process_identity)
    transport = _BudgetConsumingTransport(clock, ControlStatusSnapshot.from_state(state))
    terminator = _Terminator(clock, identities, kill_on_force=True)
    client = DesktopStopClient(
        StopClientDependencies(transport, identities, terminator, clock, DesktopPlatform.WINDOWS)
    )

    # When: the client accounts for elapsed transport time.
    result = client.stop(state)

    # Then: the expired budget blocks stop and native termination completely.
    assert result.outcome.value == "timeout"
    assert result.elapsed_seconds == 30.0
    assert transport.stop_times == []
    assert terminator.events == []


def test_unrelated_listener_remains_alive_when_runtime_state_identity_is_stale() -> None:
    # Given: a real test-owned loopback decoy plus stale state pointing at an unrelated identity.
    from app.desktop.process_identity import DesktopPlatform, ProcessIdentity

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        state, _clock, identities, transport, terminator, client = _stop_client(DesktopPlatform.WINDOWS)
        state = type(state)(**{**state.to_mapping(), "port": listener.getsockname()[1]})
        identities.identity = ProcessIdentity(
            state.pid,
            state.process_creation_time_epoch_ns + 1,
            state.executable_path,
        )

        # When: the control client evaluates the stale owner before contacting the decoy port.
        result = client.stop(state)
        probe = socket.create_connection(listener.getsockname(), timeout=1.0)
        accepted, _address = listener.accept()
        probe.close()
        accepted.close()

        # Then: the decoy is reachable and no transport/termination call was made.
        assert result.outcome.value == "identity_mismatch"
        assert transport.status_times == []
        assert terminator.events == []
    finally:
        listener.close()


def test_runtime_maintenance_stopper_authenticates_stop_and_removes_stale_state_only_with_lease(tmp_path: Path) -> None:
    # Given: a live state, authenticated control client, and provider-neutral state store.
    from app.desktop.control import (
        ControlStatusSnapshot,
        DesktopStopClient,
        RuntimeMaintenanceDependencies,
        RuntimeMaintenanceOwnerStopper,
        StopClientDependencies,
    )
    from app.desktop.instance_lock import MaintenanceOperation, MaintenanceStopRequest
    from app.desktop.process_identity import DesktopPlatform

    state, clock = _state(), _Clock()
    identities = _IdentityProvider(state.process_identity)
    transport = _CooperativeTransport(clock, ControlStatusSnapshot.from_state(state), identities)
    terminator = _Terminator(clock, identities, kill_on_force=True)
    client = DesktopStopClient(
        StopClientDependencies(transport, identities, terminator, clock, DesktopPlatform.WINDOWS)
    )
    store = _MemoryStateStore(state)
    stopper = RuntimeMaintenanceOwnerStopper(RuntimeMaintenanceDependencies(_Stores(store), identities, client))
    request = MaintenanceStopRequest(tmp_path / "profile", state.data_dir_id, MaintenanceOperation.RESTORE)

    # When: maintenance requests verified stop and later revalidates stale state under lease.
    stopped = stopper.ensure_owner_stopped(request)
    lease = _Lease(state.data_dir_id)
    revalidated = stopper.revalidate_stale_state(request, lease)

    # Then: authenticated status/stop happened at zero and removal observed the held lease.
    assert stopped and revalidated
    assert transport.status_times == [0.0]
    assert transport.stop_times == [0.0]
    assert store.state is None
    assert store.removed_with_held_lease


def test_runtime_maintenance_stopper_accepts_verified_exit_race() -> None:
    # Given: an owner exits after the first identity lookup but before the stop client begins.
    from app.desktop.control import (
        RuntimeMaintenanceDependencies,
        RuntimeMaintenanceOwnerStopper,
        StopOutcome,
        StopResult,
    )
    from app.desktop.instance_lock import MaintenanceOperation, MaintenanceStopRequest

    state = _state()
    identities = _IdentityProvider(state.process_identity)
    store = _MemoryStateStore(state)

    class ExitedOwnerClient:
        def stop(self, observed_state):
            assert observed_state == state
            identities.identity = None
            return StopResult(StopOutcome.IDENTITY_MISMATCH, 0.0)

    stopper = RuntimeMaintenanceOwnerStopper(
        RuntimeMaintenanceDependencies(_Stores(store), identities, ExitedOwnerClient())
    )
    request = MaintenanceStopRequest(Path("synthetic-profile"), state.data_dir_id, MaintenanceOperation.BACKUP)

    # When/Then: exact identity loss is accepted as verified owner exit, not a timeout.
    assert stopper.ensure_owner_stopped(request)
