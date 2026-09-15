from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.types import ASGIApp, Receive, Scope, Send

GateState = Literal["open", "maintenance"]
ControlOperation = Literal["status", "drain", "shutdown", "commit"]
GUID_N = re.compile(r"^[0-9a-f]{32}$")
MAX_CONTROL_BYTES = 16_384
SAFE_PATHS = frozenset({"/", "/api/health", "/health", "/api/readiness", "/api/version"})


class ControlProtocolError(RuntimeError):
    pass


class RuntimeControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)

    schema_tag: Literal["iz-cna-runtime-control-v1"] = Field(alias="schema")
    request_id: str
    operation: ControlOperation
    transaction_id: str | None

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        if not GUID_N.fullmatch(value):
            raise ValueError("request_id")
        return value

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction_id(cls, value: str | None) -> str | None:
        if value is not None and not GUID_N.fullmatch(value):
            raise ValueError("transaction_id")
        return value


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    gate: GateState
    draining: bool
    active_business_requests: int


class RuntimeGate:
    def __init__(self, initial_gate: GateState) -> None:
        self._condition = threading.Condition()
        self._gate = initial_gate
        self._draining = False
        self._active_business_requests = 0

    def snapshot(self) -> GateSnapshot:
        with self._condition:
            return GateSnapshot(
                gate=self._gate,
                draining=self._draining,
                active_business_requests=self._active_business_requests,
            )

    def enter_business_request(self) -> bool:
        with self._condition:
            if self._gate != "open":
                return False
            self._active_business_requests += 1
            return True

    def leave_business_request(self) -> None:
        with self._condition:
            if self._active_business_requests <= 0:
                raise RuntimeError("business request counter underflow")
            self._active_business_requests -= 1
            self._condition.notify_all()

    def wait_until_closed(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while self._gate != "maintenance":
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def drain(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            self._gate = "maintenance"
            self._draining = True
            self._condition.notify_all()
            while self._active_business_requests:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def release(self) -> None:
        with self._condition:
            self._gate = "open"
            self._draining = False
            self._condition.notify_all()


def is_maintenance_safe_path(path: str) -> bool:
    return path in SAFE_PATHS or path.startswith("/assets/")


class MaintenanceGateMiddleware:
    def __init__(self, app: ASGIApp, gate: RuntimeGate) -> None:
        self._app = app
        self._gate = gate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path_value = scope.get("path", "")
        path = path_value if isinstance(path_value, str) else ""
        if is_maintenance_safe_path(path):
            await self._app(scope, receive, send)
            return
        if not self._gate.enter_business_request():
            body = b'{"detail":"maintenance_in_progress"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": ((b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())),
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        try:
            await self._app(scope, receive, send)
        finally:
            self._gate.leave_business_request()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ControlProtocolError("control_request_invalid")
        result[name] = value
    return result


def parse_control_request(message: bytes) -> RuntimeControlRequest:
    if not message.endswith(b"\n") or message.count(b"\n") != 1:
        raise ControlProtocolError("control_request_invalid")
    body = message[:-1]
    if not body or len(body) > MAX_CONTROL_BYTES or body.startswith(b"\xef\xbb\xbf"):
        raise ControlProtocolError("control_request_invalid")
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(value, dict):
            raise ControlProtocolError("control_request_invalid")
        return RuntimeControlRequest.model_validate(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ControlProtocolError("control_request_invalid") from exc
