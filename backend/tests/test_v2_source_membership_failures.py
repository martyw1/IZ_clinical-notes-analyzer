from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, text

from test_v2_plan_version_actions import IdentityRuntime, SyntheticAuditFailure, runtime

COMMON = b"MRN: IDENTITY-001\nAdmission Date: 2026-08-01"
ADDITIONAL = b"MRN: IDENTITY-001\nPatient Name: SYNTHETIC ROLLBACK NAME\nIntervention: Additional evidence"
TABLES = ("patients", "treatment_plan_imports", "treatment_plan_versions", "patient_snapshot_versions",
          "source_documents", "source_document_plan_memberships", "evaluation_runs", "audit_logs")


def _upload(runtime: IdentityRuntime, sources: tuple[bytes, ...]):
    return runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
        files=[("file", ("synthetic.txt", source, "text/plain")) for source in sources])


def _state(directory: Path) -> tuple[str, dict[str, str]]:
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        rows = tuple(tuple(db.execute(text(f"SELECT * FROM {table} ORDER BY 1")).all()) for table in TABLES)
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
    return hashlib.sha256(repr(rows).encode()).hexdigest(), files


@pytest.mark.parametrize("stage", ["encrypt", "replace", "plan", "name", "source", "membership", "audit"])
def test_mixed_reused_and_new_failure_preserves_all_committed_state(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stage: str) -> None:
    # Given: a reused committed archive and an unrelated path that this attempt does not own.
    assert _upload(runtime, (COMMON,)).status_code == 201
    directory = tmp_path / "app-data" / "manual-uploads"
    (directory / ".unowned.tmp").write_bytes(b"unowned synthetic sentinel")
    before = _state(directory)
    from app.v2.db import engine
    from app.v2.services import manual_source_batch
    def fail(*_args, **_kwargs):
        raise SyntheticAuditFailure("Synthetic staged boundary failure")
    if stage == "encrypt":
        original_encrypt = manual_source_batch.encrypt_bytes
        count = 0
        def fail_second_encrypt(raw: bytes) -> bytes:
            nonlocal count
            count += 1
            return original_encrypt(raw) if count == 1 else fail()
        monkeypatch.setattr(manual_source_batch, "encrypt_bytes", fail_second_encrypt)
    elif stage == "replace":
        original_replace = Path.replace
        count = 0
        def fail_second_replace(path: Path, target: Path) -> Path:
            nonlocal count
            count += 1
            return original_replace(path, target) if count == 1 else fail()
        monkeypatch.setattr(Path, "replace", fail_second_replace)
    elif stage in {"plan", "name", "audit"}:
        target = {"plan": "save_treatment_plan_aggregate", "name": "persist_manual_patient_name", "audit": "_record_binder_audit"}[stage]
        monkeypatch.setattr(f"app.v2.api.manual_binder_routes.{target}", fail)
    def fail_sql(_connection, _cursor, statement: str, _parameters, _context, _executemany: bool) -> None:
        target = "INSERT INTO source_documents" if stage == "source" else "INSERT INTO source_document_plan_memberships"
        if stage in {"source", "membership"} and target in statement:
            fail()
    event.listen(engine, "before_cursor_execute", fail_sql)
    try:
        # When: a mixed reused/new binder fails at the selected transaction or staging boundary.
        with pytest.raises(SyntheticAuditFailure):
            _upload(runtime, (COMMON, ADDITIONAL))
    finally:
        event.remove(engine, "before_cursor_execute", fail_sql)
    # Then: rollback preserves exact clinical/audit rows, original cipher bytes, and the unowned path.
    assert _state(directory) == before


def test_preexisting_temporary_path_is_never_claimed_or_removed(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: another attempt owns the exact temporary path before exclusive creation.
    assert _upload(runtime, (COMMON,)).status_code == 201
    directory = tmp_path / "app-data" / "manual-uploads"
    identifier = UUID("11111111-1111-1111-1111-111111111111")
    existing = directory / f".{identifier.hex}.tmp"
    existing.write_bytes(b"previous attempt owned bytes")
    before = _state(directory)
    monkeypatch.setattr("app.v2.services.manual_source_batch.uuid4", lambda: identifier)
    # When: exclusive staging cannot acquire ownership.
    with pytest.raises(FileExistsError):
        _upload(runtime, (ADDITIONAL,))
    # Then: no cleanup removes or overwrites the pre-existing path.
    assert _state(directory) == before


def test_explicit_reimport_reactivates_only_its_exact_pair(runtime: IdentityRuntime) -> None:
    # Given: a historical tombstone retained on a committed original pair.
    first = _upload(runtime, (COMMON,)).json()
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        original = tuple(db.execute(text("SELECT * FROM source_document_plan_memberships")).one())
        db.execute(text("UPDATE source_document_plan_memberships SET detached_at='2026-09-04',detached_by_user_id=1"))
        db.commit()
    # When: an explicit import supplies that same content again.
    repeated = _upload(runtime, (COMMON,))
    # Then: it reactivates without new version/archive rows or replacement of original attachment provenance.
    assert repeated.status_code == 201
    assert repeated.json()["plan_version_id"] == first["plan_version_id"]
    assert repeated.json()["source_file_ids"] == first["source_file_ids"]
    with SessionLocal() as db:
        assert tuple(db.execute(text("SELECT * FROM source_document_plan_memberships")).one()) == original
        assert db.execute(text("SELECT COUNT(*) FROM source_documents")).scalar_one() == 1
        assert db.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action='manual_upload.source_membership.reattached'")).scalar_one() == 1
