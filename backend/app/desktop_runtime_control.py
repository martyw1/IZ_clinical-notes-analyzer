from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.desktop_identity import PRODUCT_ID
from app.desktop_lifecycle import (
    ControlProtocolError,
    GateSnapshot,
    RuntimeControlRequest,
    RuntimeGate,
    parse_control_request,
)
from app.desktop_runtime_authority import RuntimeAuthority, RuntimeAuthorityError, validate_candidate_commit
from app.desktop_runtime_contracts import RuntimeIdentity

CONTROL_RESPONSE_KEYS = frozenset(
    {
        "schema",
        "request_id",
        "operation",
        "status",
        "reason",
        "product_id",
        "owner_sid",
        "scope_id",
        "data_identity",
        "instance_id",
        "transaction_id",
        "process_id",
        "process_started_utc",
        "version",
        "build",
        "installer_revision",
        "port",
        "gate",
        "draining",
        "active_business_requests",
    }
)


class RuntimeControlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)

    schema_tag: Literal["iz-cna-runtime-control-v1"] = Field(alias="schema")
    request_id: str
    operation: Literal["status", "drain", "shutdown", "commit"]
    status: Literal["ok", "blocked"]
    reason: str
    product_id: Literal["r3.iz-clinical-notes-analyzer.desktop"]
    owner_sid: str
    scope_id: str
    data_identity: str
    instance_id: str
    transaction_id: str | None
    process_id: int
    process_started_utc: str
    version: str
    build: str
    installer_revision: int
    port: int
    gate: Literal["open", "maintenance"]
    draining: bool
    active_business_requests: int


class RuntimeController:
    def __init__(
        self,
        authority: RuntimeAuthority,
        identity: RuntimeIdentity,
        gate: RuntimeGate,
        request_shutdown: Callable[[], None],
        *,
        drain_timeout_seconds: float = 30.0,
        state_changed: Callable[[GateSnapshot], None] | None = None,
    ) -> None:
        self._authority = authority
        self._identity = identity
        self.gate = gate
        self._request_shutdown = request_shutdown
        self._drain_timeout_seconds = drain_timeout_seconds
        self._state_changed = state_changed
        self._committed = threading.Event()

    @property
    def committed(self) -> bool:
        return self._committed.is_set()

    def _notify_state(self, snapshot: GateSnapshot) -> None:
        if self._state_changed is not None:
            self._state_changed(snapshot)

    def _response(
        self,
        request: RuntimeControlRequest,
        status: Literal["ok", "blocked"],
        reason: str,
    ) -> RuntimeControlResponse:
        snapshot = self.gate.snapshot()
        return RuntimeControlResponse(
            schema="iz-cna-runtime-control-v1",
            request_id=request.request_id,
            operation=request.operation,
            status=status,
            reason=reason,
            product_id=PRODUCT_ID,
            owner_sid=self._identity.owner_sid,
            scope_id=self._identity.scope_id,
            data_identity=self._identity.data_identity,
            instance_id=self._identity.instance_id,
            transaction_id=self._identity.transaction_id,
            process_id=self._identity.process_id,
            process_started_utc=self._identity.process_started_utc,
            version=self._identity.version,
            build=self._identity.build,
            installer_revision=self._identity.installer_revision,
            port=self._identity.port,
            gate=snapshot.gate,
            draining=snapshot.draining,
            active_business_requests=snapshot.active_business_requests,
        )

    def _handle(self, request: RuntimeControlRequest) -> RuntimeControlResponse:
        if request.transaction_id != self._identity.transaction_id:
            return self._response(request, "blocked", "transaction_mismatch")
        if request.operation == "status":
            return self._response(request, "ok", "status")
        if request.operation in ("drain", "shutdown"):
            if not self.gate.drain(self._drain_timeout_seconds):
                snapshot = self.gate.snapshot()
                self._notify_state(snapshot)
                return self._response(request, "blocked", "drain_timeout")
            snapshot = self.gate.snapshot()
            self._notify_state(snapshot)
            if request.operation == "shutdown":
                self._request_shutdown()
                return self._response(request, "ok", "shutdown_requested")
            return self._response(request, "ok", "drained")
        try:
            validate_candidate_commit(self._authority)
        except RuntimeAuthorityError as exc:
            return self._response(request, "blocked", exc.reason)
        self._committed.set()
        self.gate.release()
        self._notify_state(self.gate.snapshot())
        return self._response(request, "ok", "committed")

    def handle_message(self, message: bytes) -> bytes | None:
        try:
            request = parse_control_request(message)
        except ControlProtocolError:
            return None
        response = self._handle(request)
        return response.model_dump_json(by_alias=True, exclude_none=False).encode("utf-8") + b"\n"
