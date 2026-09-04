from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from test_v2_plan_version_actions import IdentityRuntime, SyntheticAuditFailure, _import, runtime
from test_v2_plan_version_authorization import _user
from test_v2_source_membership_failures import _state


def _payload(identity: dict[str, int | str], actor_id: int = 1):
    from app.v2.services.manual_source_types import ManualSourceFileArchiveInput
    return ManualSourceFileArchiveInput(raw_bytes=b"Synthetic helper archive", patient_id="IDENTITY-001", plan_id="plan-a",
        source_format="text", content_type="text/plain", created_by_user_id=str(actor_id),
        plan_version_id=identity["plan_version_id"], patient_record_id=identity["patient_record_id"])


@pytest.mark.parametrize("case", ["ambiguous", "mismatch", "denied"])
def test_legacy_helper_resolves_authorized_exact_target_before_staging(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    # Given: an ambiguous, inconsistent, or forbidden target at the legacy helper boundary.
    selected = _import(runtime)
    payload = _payload(selected)
    expected = 404
    from app.v2.db import SessionLocal
    if case == "ambiguous":
        _import(runtime, marker="newer")
        payload = replace(payload, plan_version_id=None, patient_record_id=None)
        expected = 409
    elif case == "mismatch":
        payload = replace(payload, patient_record_id=999999)
    else:
        user_id, _ = _user(runtime, "office_manager")
        with SessionLocal() as db:
            db.execute(text("DELETE FROM user_facilities WHERE user_id=:id"), {"id": user_id})
            db.commit()
        payload = replace(payload, created_by_user_id=str(user_id))
        expected = 403
    def reject_staging(*_args, **_kwargs):
        raise AssertionError("Invalid legacy target reached file staging")
    monkeypatch.setattr("app.v2.services.manual_source_file_store.stage_manual_sources", reject_staging)
    from app.v2.services.manual_source_file_store import archive_manual_source_file
    # When: the preserved helper signature is used with that target.
    with SessionLocal() as db, pytest.raises(HTTPException) as error:
        archive_manual_source_file(db, payload)
    # Then: the intended identity or authorization failure occurs before any bytes are staged.
    assert error.value.status_code == expected


def test_legacy_helper_exact_reuse_preserves_original_and_attaches_selected_version(runtime: IdentityRuntime, tmp_path: Path) -> None:
    # Given: two exact versions and an archive originally committed for the older one.
    first = _import(runtime)
    second = _import(runtime, marker="newer")
    from app.v2.db import SessionLocal
    from app.v2.services.manual_source_file_store import archive_manual_source_file
    with SessionLocal() as db:
        original = archive_manual_source_file(db, _payload(first))
        before = tuple(db.execute(text("SELECT * FROM source_documents")).one())
    path = tmp_path / "app-data" / original.encrypted_relative_path
    ciphertext = path.read_bytes()
    # When: the same hash is explicitly imported for the newer selected version.
    with SessionLocal() as db:
        reused = archive_manual_source_file(db, _payload(second))
        # Then: only membership expands; the original row/ID/FK/cipher and return shape remain unchanged.
        assert reused == original
        assert tuple(db.execute(text("SELECT * FROM source_documents")).one()) == before
        assert db.execute(text("SELECT plan_version_id FROM source_document_plan_memberships ORDER BY plan_version_id")).scalars().all() == [first["plan_version_id"], second["plan_version_id"]]
    assert path.read_bytes() == ciphertext


@pytest.mark.parametrize("reuse", [False, True])
def test_legacy_helper_audit_failure_rolls_back_owned_memberships_and_paths(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, reuse: bool) -> None:
    # Given: a preserved committed source and a second version with no association yet.
    first = _import(runtime)
    second = _import(runtime, marker="newer")
    from app.v2.db import SessionLocal
    from app.v2.services.manual_source_file_store import archive_manual_source_file
    with SessionLocal() as db:
        archive_manual_source_file(db, _payload(first))
    directory = tmp_path / "app-data" / "manual-uploads"
    before = _state(directory)
    def fail_audit(*_args, **_kwargs):
        raise SyntheticAuditFailure("Synthetic legacy audit failure")
    monkeypatch.setattr("app.v2.services.manual_source_batch.record_audit_event", fail_audit)
    payload = _payload(second)
    if not reuse:
        payload = replace(payload, raw_bytes=b"Synthetic new helper archive")
    # When: an attached-membership audit fails outside database exception types.
    with SessionLocal() as db, pytest.raises(SyntheticAuditFailure):
        archive_manual_source_file(db, payload)
    # Then: exact prior rows and files survive and no attempt-owned residue remains.
    assert _state(directory) == before
