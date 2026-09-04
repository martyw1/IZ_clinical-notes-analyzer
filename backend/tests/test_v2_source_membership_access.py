from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from test_v2_plan_version_actions import IdentityRuntime, _import, runtime
from test_v2_plan_version_authorization import _user
from test_v2_source_membership_failures import COMMON, _upload


def _selector(response: dict) -> dict:
    return {key: response[key] for key in ("plan_version_id", "patient_record_id", "source_mode")}


def test_four_binders_preserve_every_exact_source_and_original_cipher(runtime: IdentityRuntime, tmp_path: Path, record_property) -> None:
    # Given: four binders that legitimately reuse common and additional source bytes.
    extra = b"MRN: IDENTITY-001\nIntervention: Synthetic additional evidence"
    other = b"MRN: IDENTITY-001\nGoal: Synthetic second evidence"
    inputs = ((COMMON,), (COMMON, extra), (extra, other), (COMMON, other))
    phases = []
    original_rows = {}
    original_files = {}
    from app.v2.db import SessionLocal
    for sources in inputs:
        # When: each binder is imported and read through its exact returned immutable identity.
        saved = _upload(runtime, sources)
        assert saved.status_code == 201
        selected = _selector(saved.json())
        detail = runtime.client.get("/api/v2/treatment-plans/IDENTITY-001", headers=runtime.headers, params=selected)
        assert detail.status_code == 200
        refs = detail.json()["source_documents"]
        expected_hashes = {hashlib.sha256(raw).hexdigest() for raw in sources}
        assert {ref["sha256"] for ref in refs} == expected_hashes
        assert {ref["source_file_id"] for ref in refs} == set(saved.json()["source_file_ids"])
        for ref in refs:
            downloaded = runtime.client.get(ref["download_url"], headers=runtime.headers)
            assert downloaded.status_code == 200
            assert hashlib.sha256(downloaded.content).hexdigest() == ref["sha256"]
        with SessionLocal() as db:
            current_rows = {row[0]: tuple(row) for row in db.execute(text("SELECT * FROM source_documents")).all()}
        current_files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (tmp_path / "app-data" / "manual-uploads").iterdir()}
        # Then: all earlier IDs, original FKs, source rows, and cipher hashes are unchanged.
        assert all(current_rows[key] == value for key, value in original_rows.items())
        assert all(current_files[key] == value for key, value in original_files.items())
        original_rows, original_files = current_rows, current_files
        phases.append(selected | {"source_hashes": sorted(expected_hashes), "source_file_ids": sorted(saved.json()["source_file_ids"])})
    assert len(original_rows) == len(original_files) == 3
    for phase, sources in zip(phases, inputs, strict=True):
        detail = runtime.client.get("/api/v2/treatment-plans/IDENTITY-001", headers=runtime.headers, params=_selector(phase))
        assert {ref["sha256"] for ref in detail.json()["source_documents"]} == {hashlib.sha256(raw).hexdigest() for raw in sources}
    record_property("phase_identities", json.dumps(phases, sort_keys=True))
    record_property("cipher_fingerprints", json.dumps(original_files, sort_keys=True))


def test_active_membership_ambiguity_and_tombstone_never_guess(runtime: IdentityRuntime) -> None:
    # Given: one source actively belongs to two exact saved versions.
    first = _upload(runtime, (COMMON,)).json()
    second = _upload(runtime, (COMMON, b"MRN: IDENTITY-001\nIntervention: Extra")).json()
    url = f"/api/v2/treatment-plans/IDENTITY-001/source-documents/{first['source_file_id']}/download"
    # When: selectors are omitted, or one exact association is later tombstoned.
    assert runtime.client.get(url, headers=runtime.headers).status_code == 409
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("UPDATE source_document_plan_memberships SET detached_at='2026-09-04',detached_by_user_id=1 WHERE plan_version_id=:id"),
                   {"id": first["plan_version_id"]})
        db.commit()
    # Then: only the active selected version or the now-unique active omission can download.
    assert runtime.client.get(url, headers=runtime.headers, params=_selector(first)).status_code == 404
    assert runtime.client.get(url, headers=runtime.headers, params=_selector(second)).content == COMMON
    assert runtime.client.get(url, headers=runtime.headers).content == COMMON


@pytest.mark.parametrize("case", ["source", "row", "nonmember", "unauthorized", "protected_delete"])
def test_source_guard_rejects_before_path_or_bytes(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    # Given: one archive and a sentinel before path resolution or decryption.
    saved = _upload(runtime, (COMMON,)).json()
    selector = _selector(saved)
    headers = runtime.headers
    expected = 404
    if case == "source":
        selector["source_mode"] = "alleva_rest_api"
    elif case == "row":
        selector["patient_record_id"] = 999999
    elif case == "nonmember":
        selector = _import(runtime)
    elif case == "unauthorized":
        user_id, headers = _user(runtime, "office_manager")
        from app.v2.authorization import accessible_patient_record_ids
        from app.v2.db import SessionLocal
        from app.v2.models import User
        with SessionLocal() as db:
            db.execute(text("DELETE FROM user_facilities WHERE user_id=:id"), {"id": user_id})
            db.commit()
            assert accessible_patient_record_ids(db, db.get(User, user_id)) == frozenset()
        expected = 403
    else:
        expected = 409
    def forbid_archive(*_args, **_kwargs):
        raise AssertionError("Denied source reached archive path or bytes")
    monkeypatch.setattr("app.v2.services.manual_source_file_store._stored_document_path", forbid_archive)
    monkeypatch.setattr("app.v2.services.manual_source_file_store.decrypt_bytes", forbid_archive)
    url = f"/api/v2/treatment-plans/IDENTITY-001/source-documents/{saved['source_file_id']}"
    # When: a mismatched, unauthorized, or policy-gated request reaches the API.
    response = runtime.client.delete(url, headers=headers, params=selector) if case == "protected_delete" else runtime.client.get(url + "/download", headers=headers, params=selector)
    # Then: denial happens before any archive access, with the frozen status semantics.
    assert response.status_code == expected
