from __future__ import annotations

# noqa: SIZE_OK -- The authenticated middleware and its 30-second client are one control protocol.

import hmac
import ipaddress
import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, assert_never

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.desktop.instance_lock import InstanceLease, MaintenanceStopRequest
from app.desktop.process_identity import (
    DesktopPlatform,
    ProcessIdentity,
    ProcessIdentityProvider,
    process_identity_matches,
)
from app.desktop.runtime_state import DesktopRuntimeState, RuntimeStateLease, RuntimeStateStore


STATUS_PATH: Final = "/_desktop/control/status"
STOP_PATH: Final = "/_desktop/control/stop"
MAX_CONTROL_BODY_BYTES: Final = 1024
STOP_BUDGET_SECONDS: Final = 30.0
FORCE_BOUNDARY_SECONDS: Final = 20.0
MAC_FORCE_BOUNDARY_SECONDS: Final = 25.0


class ControlDenialReason(StrEnum):
    METHOD_INVALID = "desktop_control_method_invalid"
    CLIENT_NOT_LOOPBACK = "desktop_control_client_not_loopback"
    HOST_INVALID = "desktop_control_host_invalid"
    CONTENT_TYPE_INVALID = "desktop_control_content_type_invalid"
    BODY_INVALID = "desktop_control_body_invalid"
    TOKEN_INVALID = "desktop_control_token_invalid"
    DATA_DIR_MISMATCH = "desktop_control_data_dir_mismatch"
    RUNTIME_STALE = "desktop_control_runtime_stale"


class ShutdownRequester(Protocol):
    def request_shutdown(self, run_id: str) -> None: ...


class ControlDenialRecorder(Protocol):
    def record(self, reason: ControlDenialReason) -> None: ...


@dataclass(frozen=True, slots=True)
class DesktopControlContext:
    state_provider: Callable[[], DesktopRuntimeState]
    lease: RuntimeStateLease
    identity_provider: ProcessIdentityProvider
    shutdown_requester: ShutdownRequester
    denial_recorder: ControlDenialRecorder


@dataclass(frozen=True, slots=True)
class _ControlRequest:
    scope: Scope
    state: DesktopRuntimeState
    context: DesktopControlContext


@dataclass(frozen=True, slots=True)
class ControlStatusSnapshot:
    run_id: str
    data_dir_id: str
    pid: int
    process_creation_time_epoch_ns: int
    executable_path: str
    port: int
    started_at_epoch_ns: int
    ready: bool

    @classmethod
    def from_state(cls, state: DesktopRuntimeState) -> ControlStatusSnapshot:
        return cls(
            state.run_id,
            state.data_dir_id,
            state.pid,
            state.process_creation_time_epoch_ns,
            state.executable_path,
            state.port,
            state.started_at_epoch_ns,
            state.ready,
        )

    def matches_state(self, state: DesktopRuntimeState) -> bool:
        return self == ControlStatusSnapshot.from_state(state)

    def to_mapping(self) -> dict[str, str | int | bool]:
        return {
            "run_id": self.run_id,
            "data_dir_id": self.data_dir_id,
            "pid": self.pid,
            "process_creation_time_epoch_ns": self.process_creation_time_epoch_ns,
            "executable_path": self.executable_path,
            "port": self.port,
            "started_at_epoch_ns": self.started_at_epoch_ns,
            "ready": self.ready,
        }


class DesktopControlMiddleware:
    def __init__(self, app: ASGIApp, context: DesktopControlContext) -> None:
        self._app = app
        self._context = context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in {STATUS_PATH, STOP_PATH}:
            await self._app(scope, receive, send)
            return
        state = self._context.state_provider()
        request = _ControlRequest(scope, state, self._context)
        reason = _validate_scope(scope, state)
        if reason is None:
            body = await _read_body(receive)
            reason = _validate_body_and_authority(body, request)
        if reason is not None:
            self._context.denial_recorder.record(reason)
            await _send_json(send, _denial_status(reason), {"error": reason.value})
            return
        snapshot = ControlStatusSnapshot.from_state(state)
        if scope["path"] == STOP_PATH:
            self._context.shutdown_requester.request_shutdown(state.run_id)
            await _send_json(send, 202, snapshot.to_mapping())
            return
        await _send_json(send, 200, snapshot.to_mapping())


def _validate_scope(scope: Scope, state: DesktopRuntimeState) -> ControlDenialReason | None:
    if scope.get("method") != "POST":
        return ControlDenialReason.METHOD_INVALID
    match scope.get("client"):  # noqa: MATCH_OK -- the ASGI network boundary rejects malformed client tuples.
        case (str() as address, int()):
            try:
                if not ipaddress.ip_address(address).is_loopback:
                    return ControlDenialReason.CLIENT_NOT_LOOPBACK
            except ValueError:
                return ControlDenialReason.CLIENT_NOT_LOOPBACK
        case _:
            return ControlDenialReason.CLIENT_NOT_LOOPBACK
    headers = _headers(scope)
    if headers is None:
        return ControlDenialReason.BODY_INVALID
    allowed_hosts = {
        f"127.0.0.1:{state.port}",
        f"localhost:{state.port}",
        f"[::1]:{state.port}",
    }
    if headers.get("host", "").casefold() not in allowed_hosts:
        return ControlDenialReason.HOST_INVALID
    if headers.get("content-type", "").casefold() != "application/json":
        return ControlDenialReason.CONTENT_TYPE_INVALID
    content_length = headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_CONTROL_BODY_BYTES:
                return ControlDenialReason.BODY_INVALID
        except ValueError:
            return ControlDenialReason.BODY_INVALID
    return None


def _validate_body_and_authority(
    body: bytes | None,
    request: _ControlRequest,
) -> ControlDenialReason | None:
    if body is None:
        return ControlDenialReason.BODY_INVALID
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ControlDenialReason.BODY_INVALID
    if decoded != {}:
        return ControlDenialReason.BODY_INVALID
    headers = _headers(request.scope)
    if headers is None:
        return ControlDenialReason.BODY_INVALID
    if not hmac.compare_digest(headers.get("x-iz-data-dir-id", ""), request.state.data_dir_id):
        return ControlDenialReason.DATA_DIR_MISMATCH
    if not hmac.compare_digest(headers.get("x-iz-desktop-control", ""), request.state.control_token):
        return ControlDenialReason.TOKEN_INVALID
    if (
        request.context.lease.canonical_data_dir_id != request.state.data_dir_id
        or not request.context.lease.is_held_by_current_process()
        or not request.context.lease.validate_native_identity()
        or not process_identity_matches(request.context.identity_provider, request.state.process_identity)
    ):
        return ControlDenialReason.RUNTIME_STALE
    return None


def _headers(scope: Scope) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.decode("latin-1").casefold()
        if name in result:
            return None
        result[name] = raw_value.decode("latin-1")
    return result


async def _read_body(receive: Receive) -> bytes | None:
    body = bytearray()
    while True:
        message: Message = await receive()
        if message["type"] == "http.disconnect":
            return None
        if message["type"] != "http.request":
            return None
        body.extend(message.get("body", b""))
        if len(body) > MAX_CONTROL_BODY_BYTES:
            return None
        if not message.get("more_body", False):
            return bytes(body)


async def _send_json(send: Send, status_code: int, payload: dict[str, str | int | bool]) -> None:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": (
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ),
        }
    )
    await send({"type": "http.response.body", "body": body})


def _denial_status(reason: ControlDenialReason) -> int:
    match reason:
        case (
            ControlDenialReason.METHOD_INVALID
            | ControlDenialReason.CONTENT_TYPE_INVALID
            | ControlDenialReason.BODY_INVALID
        ):
            return 400
        case ControlDenialReason.TOKEN_INVALID:
            return 401
        case (
            ControlDenialReason.CLIENT_NOT_LOOPBACK
            | ControlDenialReason.HOST_INVALID
            | ControlDenialReason.DATA_DIR_MISMATCH
        ):
            return 403
        case ControlDenialReason.RUNTIME_STALE:
            return 409
        case unreachable:
            assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class ControlTransportRequest:
    state: DesktopRuntimeState
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ControlHttpResponse:
    status_code: int
    snapshot: ControlStatusSnapshot | None


class ControlTransport(Protocol):
    def status(self, request: ControlTransportRequest) -> ControlHttpResponse: ...

    def stop(self, request: ControlTransportRequest) -> ControlHttpResponse: ...


class MonotonicClock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class TerminationSignal(StrEnum):
    GRACEFUL = "graceful"
    FORCE = "force"


class ProcessTerminator(Protocol):
    def terminate_if_matches(self, identity: ProcessIdentity, signal: TerminationSignal) -> bool: ...


class StopOutcome(StrEnum):
    STOPPED = "stopped"
    IDENTITY_MISMATCH = "identity_mismatch"
    CONTROL_REJECTED = "control_rejected"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class StopResult:
    outcome: StopOutcome
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class StopClientDependencies:
    transport: ControlTransport
    identity_provider: ProcessIdentityProvider
    terminator: ProcessTerminator
    clock: MonotonicClock
    platform: DesktopPlatform
    poll_interval_seconds: float = 1.0


class DesktopStopClient:
    def __init__(self, dependencies: StopClientDependencies) -> None:
        self._dependencies = dependencies

    def stop(self, state: DesktopRuntimeState) -> StopResult:
        start = self._dependencies.clock.monotonic()
        if not process_identity_matches(self._dependencies.identity_provider, state.process_identity):
            return StopResult(StopOutcome.IDENTITY_MISMATCH, 0.0)
        if not self._status_is_current(state, start):
            return StopResult(StopOutcome.CONTROL_REJECTED, self._elapsed(start))
        if self._elapsed(start) >= STOP_BUDGET_SECONDS:
            return StopResult(StopOutcome.TIMEOUT, STOP_BUDGET_SECONDS)
        stop_reply = self._dependencies.transport.stop(self._request(state, start))
        if stop_reply.status_code != 202 or (
            stop_reply.snapshot is not None and not stop_reply.snapshot.matches_state(state)
        ):
            return StopResult(StopOutcome.CONTROL_REJECTED, self._elapsed(start))
        if self._elapsed(start) >= STOP_BUDGET_SECONDS:
            return StopResult(StopOutcome.TIMEOUT, STOP_BUDGET_SECONDS)
        last_status_at = 0.0
        graceful_sent = False
        force_sent = False
        while True:
            elapsed = self._elapsed(start)
            if not process_identity_matches(self._dependencies.identity_provider, state.process_identity):
                return StopResult(StopOutcome.STOPPED, elapsed)
            if elapsed >= STOP_BUDGET_SECONDS:
                return StopResult(StopOutcome.TIMEOUT, STOP_BUDGET_SECONDS)
            if elapsed <= FORCE_BOUNDARY_SECONDS and elapsed > last_status_at:
                if not self._status_is_current(state, start):
                    return StopResult(StopOutcome.CONTROL_REJECTED, self._elapsed(start))
                elapsed = self._elapsed(start)
                if elapsed >= STOP_BUDGET_SECONDS:
                    return StopResult(StopOutcome.TIMEOUT, STOP_BUDGET_SECONDS)
                last_status_at = elapsed
            match self._dependencies.platform:
                case DesktopPlatform.WINDOWS:
                    if elapsed >= FORCE_BOUNDARY_SECONDS and not force_sent:
                        self._terminate_revalidated(state, TerminationSignal.FORCE)
                        force_sent = True
                case DesktopPlatform.MACOS:
                    if elapsed >= FORCE_BOUNDARY_SECONDS and not graceful_sent:
                        self._terminate_revalidated(state, TerminationSignal.GRACEFUL)
                        graceful_sent = True
                    if elapsed >= MAC_FORCE_BOUNDARY_SECONDS and not force_sent:
                        self._terminate_revalidated(state, TerminationSignal.FORCE)
                        force_sent = True
                case unreachable:
                    assert_never(unreachable)
            if not process_identity_matches(self._dependencies.identity_provider, state.process_identity):
                return StopResult(StopOutcome.STOPPED, self._elapsed(start))
            boundary = _next_boundary(self._dependencies.platform, elapsed)
            sleep_seconds = min(self._dependencies.poll_interval_seconds, boundary - elapsed)
            if sleep_seconds <= 0:
                sleep_seconds = min(self._dependencies.poll_interval_seconds, STOP_BUDGET_SECONDS - elapsed)
            self._dependencies.clock.sleep(sleep_seconds)

    def _status_is_current(self, state: DesktopRuntimeState, start: float) -> bool:
        reply = self._dependencies.transport.status(self._request(state, start))
        return reply.status_code == 200 and reply.snapshot is not None and reply.snapshot.matches_state(state)

    def _request(self, state: DesktopRuntimeState, start: float) -> ControlTransportRequest:
        return ControlTransportRequest(state, max(0.0, STOP_BUDGET_SECONDS - self._elapsed(start)))

    def _terminate_revalidated(self, state: DesktopRuntimeState, signal: TerminationSignal) -> None:
        if process_identity_matches(self._dependencies.identity_provider, state.process_identity):
            self._dependencies.terminator.terminate_if_matches(state.process_identity, signal)

    def _elapsed(self, start: float) -> float:
        return min(STOP_BUDGET_SECONDS, max(0.0, self._dependencies.clock.monotonic() - start))


def _next_boundary(platform: DesktopPlatform, elapsed: float) -> float:
    if elapsed < FORCE_BOUNDARY_SECONDS:
        return FORCE_BOUNDARY_SECONDS
    match platform:
        case DesktopPlatform.WINDOWS:
            return STOP_BUDGET_SECONDS
        case DesktopPlatform.MACOS:
            return MAC_FORCE_BOUNDARY_SECONDS if elapsed < MAC_FORCE_BOUNDARY_SECONDS else STOP_BUDGET_SECONDS
        case unreachable:
            assert_never(unreachable)


class RuntimeStateStores(Protocol):
    def for_data_root(self, data_root: Path, canonical_data_dir_id: str) -> RuntimeStateStore: ...


class OwnerStopClient(Protocol):
    def stop(self, state: DesktopRuntimeState) -> StopResult: ...


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceDependencies:
    stores: RuntimeStateStores
    identity_provider: ProcessIdentityProvider
    stop_client: OwnerStopClient


class RuntimeMaintenanceOwnerStopper:
    def __init__(self, dependencies: RuntimeMaintenanceDependencies) -> None:
        self._dependencies = dependencies

    def ensure_owner_stopped(self, request: MaintenanceStopRequest) -> bool:
        store = self._dependencies.stores.for_data_root(request.data_root, request.canonical_data_dir_id)
        state = store.read()
        if state is None or not process_identity_matches(self._dependencies.identity_provider, state.process_identity):
            return True
        outcome = self._dependencies.stop_client.stop(state).outcome
        if outcome == StopOutcome.STOPPED:
            return True
        return outcome == StopOutcome.IDENTITY_MISMATCH and not process_identity_matches(
            self._dependencies.identity_provider,
            state.process_identity,
        )

    def revalidate_stale_state(self, request: MaintenanceStopRequest, lease: InstanceLease) -> bool:
        store = self._dependencies.stores.for_data_root(request.data_root, request.canonical_data_dir_id)
        state = store.read()
        if state is None:
            return True
        if process_identity_matches(self._dependencies.identity_provider, state.process_identity):
            return False
        store.remove(lease)
        return True
