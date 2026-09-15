from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.desktop_runtime_contracts import RuntimeIdentity
from app.desktop_runtime_files import (
    RuntimeStateError,
    acquire_runtime_lock,
    remove_runtime_identity,
    write_runtime_identity,
)


def identity(path: Path, instance_id: str = "202030405060708090a0b0c0d0e0f001") -> RuntimeIdentity:
    return RuntimeIdentity(
        schema="iz-cna-runtime-identity-v1",
        product_id="r3.iz-clinical-notes-analyzer.desktop",
        owner_sid="S-1-5-21-1-2-3-1001",
        scope_id="a" * 64,
        data_identity="b" * 64,
        instance_id=instance_id,
        transaction_id=None,
        process_id=123,
        process_started_utc="2026-09-14T12:00:00Z",
        executable_path=str(path),
        executable_sha256="c" * 64,
        version="2.0.0-beta.4",
        build="2026.09.14.1",
        installer_revision=1,
        port=8123,
        pipe_name="iz-cna-runtime-v1-" + "a" * 32,
        gate="open",
        draining=False,
        created_utc="2026-09-14T12:00:01Z",
    )


def test_runtime_lock_excludes_second_instance_for_same_scope_and_data(tmp_path: Path) -> None:
    first = acquire_runtime_lock(tmp_path, "a" * 64, "b" * 64)
    try:
        with pytest.raises(RuntimeStateError, match="runtime_already_running"):
            acquire_runtime_lock(tmp_path, "a" * 64, "b" * 64)
    finally:
        first.close()


def test_identity_write_is_exact_and_cleanup_is_instance_guarded(tmp_path: Path) -> None:
    path = tmp_path / "runtime-identity.json"
    current = identity(path)

    write_runtime_identity(path, current)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {
        field.alias or name for name, field in RuntimeIdentity.model_fields.items()
    }
    assert raw["instance_id"] == current.instance_id
    assert not remove_runtime_identity(path, "f" * 32)
    assert path.exists()
    assert remove_runtime_identity(path, current.instance_id)
    assert not path.exists()
