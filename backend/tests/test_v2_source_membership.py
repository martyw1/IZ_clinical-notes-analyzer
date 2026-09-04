from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text

from test_v2_plan_version_actions import IdentityRuntime, runtime


def test_reused_binder_source_remains_available_on_every_exact_version(runtime: IdentityRuntime, tmp_path: Path) -> None:
    # Given: first import owns the unchanged original encrypted source.
    common = b"MRN: IDENTITY-001\nAdmission Date: 2026-08-01"
    first = runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
        files=[("file", ("first.txt", common, "text/plain"))])
    assert first.status_code == 201
    source_id = first.json()["source_file_id"]
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        original = tuple(db.execute(text("SELECT * FROM source_documents WHERE document_id=:id"), {"id": source_id}).one())
    archive = tuple((tmp_path / "app-data" / "manual-uploads").glob("*.izcna1"))[0]
    cipher_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    # When: a later binder legitimately reuses that file with additional evidence.
    second = runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
        files=[("file", ("again.txt", common, "text/plain")),
               ("file", ("additional.txt", b"MRN: IDENTITY-001\nIntervention: Synthetic additional evidence", "text/plain"))])
    assert second.status_code == 201
    selected = runtime.client.get("/api/v2/treatment-plans", headers=runtime.headers).json()["items"][0]
    params = {key: selected[key] for key in ("plan_version_id", "patient_record_id", "source_mode")}
    # Then: exact list/download includes the reused file and original provenance/bytes remain unchanged.
    detail = runtime.client.get("/api/v2/treatment-plans/IDENTITY-001", headers=runtime.headers, params=params)
    assert {item["source_file_id"] for item in detail.json()["source_documents"]} == set(second.json()["source_file_ids"])
    downloaded = runtime.client.get(f"/api/v2/treatment-plans/IDENTITY-001/source-documents/{source_id}/download", headers=runtime.headers, params=params)
    assert downloaded.status_code == 200 and downloaded.content == common
    with SessionLocal() as db:
        assert tuple(db.execute(text("SELECT * FROM source_documents WHERE document_id=:id"), {"id": source_id}).one()) == original
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == cipher_hash


def test_partial_temporary_write_failure_cleans_unregistered_staging(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: the first temporary file is written but replacing it fails.
    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError("Synthetic replace failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    # When: that source is staged through the actual binder import.
    with pytest.raises(OSError):
        runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
            files={"file": ("synthetic.txt", "MRN: IDENTITY-001", "text/plain")})
    # Then: no unregistered .tmp or final ciphertext survives the failed attempt.
    assert not tuple((tmp_path / "app-data" / "manual-uploads").iterdir())


def test_physical_delete_provenance_guard_runs_before_path_access(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a source linked to a committed treatment-plan version.
    imported = runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
        files={"file": ("synthetic.txt", "MRN: IDENTITY-001", "text/plain")})
    source_id = imported.json()["source_file_id"]
    from app.v2.db import SessionLocal
    from app.v2.services import manual_source_file_store
    from fastapi import HTTPException
    def forbid_path(*_args: str) -> Path:
        pytest.fail("Protected source reached filesystem path resolution")
    monkeypatch.setattr(manual_source_file_store, "_stored_document_path", forbid_path)
    # When: the retained physical-delete helper is called directly.
    with SessionLocal() as db, pytest.raises(HTTPException) as error:
        manual_source_file_store.delete_manual_source_file(db, "IDENTITY-001", source_id)
    # Then: pending retention policy fails closed before filesystem operations.
    assert error.value.status_code == 409
