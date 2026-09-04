from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from test_v2_plan_version_actions import IdentityRuntime, _import, runtime


@pytest.mark.parametrize("protection", ["plan", "review", "active_membership", "tombstoned_membership"])
def test_each_retained_provenance_guard_precedes_path_resolution(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, protection: str) -> None:
    # Given: a source protected independently by plan FK, review FK, active link, or historical tombstone.
    selected = _import(runtime)
    from app.v2.db import SessionLocal
    from app.v2.services.manual_source_file_store import delete_manual_source_file
    with SessionLocal() as db:
        review_id = None
        if protection == "review":
            review_id = db.execute(text("INSERT INTO treatment_review_versions(patient_id,source_system,source_record_id,version_ordinal,"
                "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) "
                "SELECT patient_id,source_system,'synthetic-review',1,normalized_snapshot_encrypted,'review-hash',evidence_sha256,imported_at "
                "FROM treatment_plan_versions WHERE id=:version"), {"version": selected["plan_version_id"]}).lastrowid
        source_id = db.execute(text("INSERT INTO source_documents(patient_id,plan_version_id,review_version_id,document_id,source_kind,"
            "source_format,content_type,size_bytes,sha256,encrypted_relative_path,created_by_user_id,created_at) "
            "VALUES(:patient,:plan,:review,'synthetic-guard','manual_treatment_plan_file','text','text/plain',1,'guard-hash','manual-uploads/guard.izcna1',1,'2026-09-04')"),
            {"patient": selected["patient_record_id"], "plan": selected["plan_version_id"] if protection == "plan" else None, "review": review_id}).lastrowid
        if protection.endswith("membership"):
            db.execute(text("INSERT INTO source_document_plan_memberships(source_document_id,plan_version_id,attached_at,attached_by_user_id,detached_at,detached_by_user_id) "
                "VALUES(:source,:version,'2026-09-04',1,:detached,:actor)"),
                {"source": source_id, "version": selected["plan_version_id"], "detached": "2026-09-04" if protection == "tombstoned_membership" else None,
                 "actor": 1 if protection == "tombstoned_membership" else None})
        db.commit()
        before = tuple(db.execute(text("SELECT * FROM source_documents")).one())
    def reject_path(*_args, **_kwargs):
        raise AssertionError("Protected original reached path resolution")
    monkeypatch.setattr("app.v2.services.manual_source_file_store._stored_document_path", reject_path)
    # When: the physical-delete helper is invoked directly, independently of the HTTP membership resolver.
    with SessionLocal() as db, pytest.raises(HTTPException) as error:
        delete_manual_source_file(db, "IDENTITY-001", "synthetic-guard")
    # Then: policy-gated 409 happens before path access and leaves original provenance untouched.
    assert error.value.status_code == 409
    with SessionLocal() as db:
        assert tuple(db.execute(text("SELECT * FROM source_documents")).one()) == before
