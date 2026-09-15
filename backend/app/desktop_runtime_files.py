from __future__ import annotations

import json
import msvcrt
import os
import uuid
from pathlib import Path
from typing import BinaryIO

from pydantic import ValidationError

from app.desktop_runtime_contracts import RuntimeIdentity


class RuntimeStateError(RuntimeError):
    pass


class RuntimeInstanceLock:
    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def close(self) -> None:
        if self._stream.closed:
            return
        self._stream.seek(0)
        try:
            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._stream.close()


def acquire_runtime_lock(state_root: Path, scope_id: str, data_identity: str) -> RuntimeInstanceLock:
    path = state_root / f"runtime-{scope_id[:16]}-{data_identity[:16]}.lock"
    stream = path.open("a+b", buffering=0)
    try:
        if path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
            os.fsync(stream.fileno())
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return RuntimeInstanceLock(stream)
    except OSError as exc:
        stream.close()
        raise RuntimeStateError("runtime_already_running") from exc


def write_runtime_identity(path: Path, identity: RuntimeIdentity) -> None:
    payload = identity.model_dump_json(by_alias=True, exclude_none=False).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise RuntimeStateError("runtime_identity_invalid")
        result[name] = value
    return result


def remove_runtime_identity(path: Path, instance_id: str) -> bool:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        identity = RuntimeIdentity.model_validate(value)
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, RuntimeStateError):
        return False
    if identity.instance_id != instance_id:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
