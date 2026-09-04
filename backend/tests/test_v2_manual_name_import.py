from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from test_v2_evaluation_persistence import _aggregate
from test_v2_plan_version_actions import IdentityRuntime, SyntheticAuditFailure, runtime

NAME = "SYNTHETIC NAME IMPORT CANARY"


@pytest.mark.parametrize("mode", ["aggregate", "binder"])
def test_explicit_name_import_projects_only_encrypted_exact_snapshot(runtime: IdentityRuntime, tmp_path: Path, mode: str) -> None:
    # Given: directly labeled name and plan-local metadata in a synthetic import.
    payload = _aggregate("IDENTITY-001").model_copy(update={"patient_full_name": NAME})
    # When: the manual import succeeds.
    if mode == "aggregate":
        response = runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
                                       json=payload.model_dump(mode="json"))
    else:
        response = runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
            files={"file": ("synthetic.txt", f"MRN: IDENTITY-001\nPatient Name: {NAME}\nService Date: 2026-09-01\nOriginal Plan Reference: REF-SYNTHETIC", "text/plain")})
    # Then: returned identity is exact, name is authorized UI only, and stored aggregate/columns exclude it.
    assert response.status_code == 201
    selected = response.json()
    assert selected["treatment_plan_id"] and selected["patient_record_id"] > 0 and selected["plan_version_id"] > 0
    detail = runtime.client.get("/api/v2/patients/IDENTITY-001", headers=runtime.headers,
        params={"patient_record_id": selected["patient_record_id"], "source_mode": "manual_upload"})
    assert detail.status_code == 200
    assert detail.json()["full_name"] == NAME
    from app.core.config import settings
    from app.v2.db import SessionLocal
    from app.v2.services.clinical_snapshot_codec import AggregateSnapshot, ClinicalSnapshotCodec
    with SessionLocal() as db:
        blob = db.execute(text("SELECT normalized_snapshot_encrypted FROM treatment_plan_versions WHERE id=:id"), {"id": selected["plan_version_id"]}).scalar_one()
        decoded = ClinicalSnapshotCodec(settings.effective_data_encryption_secret).decode_plan(blob)
        assert isinstance(decoded, AggregateSnapshot) and decoded.aggregate.patient_full_name == ""
        assert db.execute(text("SELECT COUNT(*) FROM patient_snapshot_versions")).scalar_one() == 1
    assert NAME.encode() not in (tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3").read_bytes()
    assert NAME not in runtime.client.get("/api/v2/exports/treatment-plans.csv", headers=runtime.headers).text
    assert NAME not in runtime.client.get("/api/audit/logs", headers=runtime.headers).text


def test_later_omitted_name_preserves_authorized_snapshot(runtime: IdentityRuntime) -> None:
    # Given: an earlier explicitly named manual import.
    payload = _aggregate("IDENTITY-001").model_copy(update={"patient_full_name": NAME})
    runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers, json=payload.model_dump(mode="json"))
    # When: a later source omits the name.
    runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
        json=_aggregate("IDENTITY-001").model_copy(update={"source_last_updated": "later"}).model_dump(mode="json"))
    # Then: name omission does not erase the exact snapshot.
    assert runtime.client.get("/api/v2/patient-roster", headers=runtime.headers).json()["items"][0]["full_name"] == NAME


@pytest.mark.parametrize("mode", ["aggregate", "binder"])
def test_name_plan_audit_failure_rolls_back_all_owned_state(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str) -> None:
    # Given: an audit boundary that fails outside the SQLAlchemy exception hierarchy.
    def fail_audit(*_args: int, **_kwargs: str) -> None:
        raise SyntheticAuditFailure("Synthetic boundary failure")
    module = "manual_upload_routes" if mode == "aggregate" else "manual_binder_routes"
    monkeypatch.setattr(f"app.v2.api.{module}.record_audit_event", fail_audit)
    # When: the named import reaches its audit commit boundary.
    with pytest.raises(SyntheticAuditFailure):
        if mode == "aggregate":
            runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
                json=_aggregate("IDENTITY-001").model_copy(update={"patient_full_name": NAME}).model_dump(mode="json"))
        else:
            runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
                files={"file": ("synthetic.txt", f"MRN: IDENTITY-001\nPatient Name: {NAME}", "text/plain")})
    # Then: plan/name/source mutations and newly staged paths are absent.
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        assert all(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0 for table in (
            "patients", "treatment_plan_versions", "patient_snapshot_versions", "source_documents",
        ))
    assert not tuple((tmp_path / "app-data" / "manual-uploads").glob("*"))
