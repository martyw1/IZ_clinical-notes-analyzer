from __future__ import annotations

import base64
import binascii
import json
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, TypeAlias

from app.desktop.process_identity import NormalizedExecutablePath, ProcessIdentity, ProcessIdentityError


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


RUNTIME_STATE_SCHEMA_VERSION: Final = 1
MAX_RUNTIME_STATE_BYTES: Final = 16 * 1024
_STATE_FIELDS: Final = frozenset(
    {
        "schema_version",
        "data_dir_id",
        "run_id",
        "control_token",
        "pid",
        "process_creation_time_epoch_ns",
        "executable_path",
        "port",
        "started_at_epoch_ns",
        "ready",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeStateError(RuntimeError):
    reason_code: str

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class DesktopRuntimeState:
    schema_version: int
    data_dir_id: str
    run_id: str
    control_token: str = field(repr=False)
    pid: int
    process_creation_time_epoch_ns: int
    executable_path: NormalizedExecutablePath
    port: int
    started_at_epoch_ns: int
    ready: bool

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_STATE_SCHEMA_VERSION:
            raise RuntimeStateError("desktop_runtime_state_schema_unsupported")
        if not self.data_dir_id or len(self.data_dir_id) > 4096 or any(ord(char) < 32 for char in self.data_dir_id):
            raise RuntimeStateError("desktop_runtime_state_corrupt")
        try:
            parsed_run_id = uuid.UUID(self.run_id)
        except ValueError as exc:
            raise RuntimeStateError("desktop_runtime_state_corrupt") from exc
        if parsed_run_id.version != 4 or str(parsed_run_id) != self.run_id:
            raise RuntimeStateError("desktop_runtime_state_corrupt")
        if not _is_control_token(self.control_token):
            raise RuntimeStateError("desktop_runtime_state_corrupt")
        try:
            ProcessIdentity(self.pid, self.process_creation_time_epoch_ns, self.executable_path)
        except ProcessIdentityError as exc:
            raise RuntimeStateError("desktop_runtime_state_corrupt") from exc
        if not 1 <= self.port <= 65535 or self.started_at_epoch_ns <= 0 or type(self.ready) is not bool:
            raise RuntimeStateError("desktop_runtime_state_corrupt")

    @property
    def process_identity(self) -> ProcessIdentity:
        return ProcessIdentity(self.pid, self.process_creation_time_epoch_ns, self.executable_path)

    def to_mapping(self) -> dict[str, str | int | bool]:
        return {
            "schema_version": self.schema_version,
            "data_dir_id": self.data_dir_id,
            "run_id": self.run_id,
            "control_token": self.control_token,
            "pid": self.pid,
            "process_creation_time_epoch_ns": self.process_creation_time_epoch_ns,
            "executable_path": self.executable_path,
            "port": self.port,
            "started_at_epoch_ns": self.started_at_epoch_ns,
            "ready": self.ready,
        }

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, payload: bytes, expected_data_dir_id: str) -> DesktopRuntimeState:
        if len(payload) > MAX_RUNTIME_STATE_BYTES:
            raise RuntimeStateError("desktop_runtime_state_too_large")
        try:
            decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeStateError("desktop_runtime_state_corrupt") from exc
        match decoded:  # noqa: MATCH_OK -- untrusted JSON must reject variants outside the state object.
            case dict() as values:
                if frozenset(values) != _STATE_FIELDS:
                    raise RuntimeStateError("desktop_runtime_state_corrupt")
            case _:
                raise RuntimeStateError("desktop_runtime_state_corrupt")
        state = cls(
            schema_version=_integer(values["schema_version"]),
            data_dir_id=_string(values["data_dir_id"]),
            run_id=_string(values["run_id"]),
            control_token=_string(values["control_token"]),
            pid=_integer(values["pid"]),
            process_creation_time_epoch_ns=_integer(values["process_creation_time_epoch_ns"]),
            executable_path=NormalizedExecutablePath(_string(values["executable_path"])),
            port=_integer(values["port"]),
            started_at_epoch_ns=_integer(values["started_at_epoch_ns"]),
            ready=_boolean(values["ready"]),
        )
        if state.data_dir_id != expected_data_dir_id:
            raise RuntimeStateError("desktop_runtime_state_wrong_data_dir")
        return state


class RuntimeStateLease(Protocol):
    @property
    def canonical_data_dir_id(self) -> str: ...

    def is_held_by_current_process(self) -> bool: ...

    def validate_native_identity(self) -> bool: ...


class RuntimeStateStorage(Protocol):
    def prepare_private_runtime_directory(self, path: Path) -> None: ...

    def read_private_file(self, path: Path, max_bytes: int) -> bytes | None: ...

    def atomic_write_private_file(self, path: Path, payload: bytes) -> None: ...

    def remove_private_file(self, path: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeStateSeed:
    data_dir_id: str
    process_identity: ProcessIdentity
    port: int
    started_at_epoch_ns: int
    ready: bool = False


class RuntimeStateStore:
    def __init__(self, data_root: Path, data_dir_id: str, storage: RuntimeStateStorage) -> None:
        self.data_root = data_root.absolute()
        self.data_dir_id = data_dir_id
        self.storage = storage
        self.runtime_directory = self.data_root / "runtime"
        self.state_file = self.runtime_directory / "desktop-state.json"

    def read(self) -> DesktopRuntimeState | None:
        self._assert_path_contract()
        if not self.runtime_directory.exists():
            return None
        try:
            payload = self.storage.read_private_file(self.state_file, MAX_RUNTIME_STATE_BYTES)
        except RuntimeStateError:
            raise
        except OSError as exc:
            raise RuntimeStateError("desktop_runtime_state_unavailable") from exc
        if payload is None:
            return None
        return DesktopRuntimeState.from_bytes(payload, self.data_dir_id)

    def write(self, state: DesktopRuntimeState, lease: RuntimeStateLease) -> None:
        self._validate_lease(lease)
        if state.data_dir_id != self.data_dir_id:
            raise RuntimeStateError("desktop_runtime_state_wrong_data_dir")
        self._assert_path_contract()
        try:
            self.storage.prepare_private_runtime_directory(self.runtime_directory)
            self._assert_path_contract()
            self.storage.atomic_write_private_file(self.state_file, state.to_bytes())
        except RuntimeStateError:
            raise
        except OSError as exc:
            raise RuntimeStateError("desktop_runtime_state_unavailable") from exc

    def remove(self, lease: RuntimeStateLease) -> None:
        self._validate_lease(lease)
        self._assert_path_contract()
        if not self.runtime_directory.exists():
            return
        try:
            self.storage.remove_private_file(self.state_file)
        except RuntimeStateError:
            raise
        except OSError as exc:
            raise RuntimeStateError("desktop_runtime_state_unavailable") from exc

    def _validate_lease(self, lease: RuntimeStateLease) -> None:
        if (
            lease.canonical_data_dir_id != self.data_dir_id
            or not lease.is_held_by_current_process()
            or not lease.validate_native_identity()
        ):
            raise RuntimeStateError("desktop_data_dir_lease_invalid")

    def _assert_path_contract(self) -> None:
        if (
            self.data_root.is_symlink()
            or self.runtime_directory.is_symlink()
            or self.state_file.is_symlink()
            or self.runtime_directory.parent != self.data_root
            or self.state_file.parent != self.runtime_directory
        ):
            raise RuntimeStateError("desktop_runtime_state_symlink_rejected")


def create_runtime_state(seed: RuntimeStateSeed) -> DesktopRuntimeState:
    return DesktopRuntimeState(
        schema_version=RUNTIME_STATE_SCHEMA_VERSION,
        data_dir_id=seed.data_dir_id,
        run_id=str(uuid.uuid4()),
        control_token=secrets.token_urlsafe(32),
        pid=seed.process_identity.pid,
        process_creation_time_epoch_ns=seed.process_identity.creation_time_epoch_ns,
        executable_path=seed.process_identity.executable_path,
        port=seed.port,
        started_at_epoch_ns=seed.started_at_epoch_ns,
        ready=seed.ready,
    )


def _is_control_token(value: str) -> bool:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    if len(value) != 43 or any(char not in alphabet for char in value):
        return False
    try:
        decoded = base64.b64decode(value + "=", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(decoded) == 32


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    values: dict[str, JsonValue] = {}
    for name, value in pairs:
        if name in values:
            raise RuntimeStateError("desktop_runtime_state_corrupt")
        values[name] = value
    return values


def _integer(value: JsonValue) -> int:
    match value:  # noqa: MATCH_OK -- untrusted JSON primitives need a rejecting default.
        case bool():
            raise RuntimeStateError("desktop_runtime_state_corrupt")
        case int() as parsed:
            return parsed
        case _:
            raise RuntimeStateError("desktop_runtime_state_corrupt")


def _string(value: JsonValue) -> str:
    match value:  # noqa: MATCH_OK -- untrusted JSON primitives need a rejecting default.
        case str() as parsed:
            return parsed
        case _:
            raise RuntimeStateError("desktop_runtime_state_corrupt")


def _boolean(value: JsonValue) -> bool:
    match value:  # noqa: MATCH_OK -- untrusted JSON primitives need a rejecting default.
        case bool() as parsed:
            return parsed
        case _:
            raise RuntimeStateError("desktop_runtime_state_corrupt")
