#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "fastapi==0.136.1", "SQLAlchemy==2.0.35", "python-jose[cryptography]==3.5.0",
#   "passlib[bcrypt]==1.7.4", "bcrypt==4.0.1", "python-multipart==0.0.27",
#   "pydantic-settings==2.5.2", "email-validator==2.2.0", "pypdf==6.10.2",
#   "cryptography==47.0.0", "PyYAML==6.0.2", "tzdata==2026.2", "httpx==0.28.1"
# ]
# ///
# ─── How to run ───
# Run from the repository root with PYTHONPATH=backend and installed repository dependencies:
# backend/.venv/Scripts/python.exe backend/tests/manual_metadata_probe.py --case happy --evidence-dir .omo/evidence/office-manager-production-fixes
# Use --case edge for omission/conflict/privacy checks. No user runtime or vendor service is accessed.
# Optional portable runner: install uv from https://docs.astral.sh/uv/ and use uv run with the same arguments.
# ──────────────────
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import secrets
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

ProbeCase = Literal["happy", "edge"]
SENTINEL: Final = "SYNTHETIC-NAME-PRIVATE-PROBE-7214"
MRN: Final = "META-PROBE-001"
CAPTURED_AT: Final = "2026-09-03T12:00:00+00:00"


class ProbeOptions(BaseModel):
    model_config = ConfigDict(frozen=True)
    case: ProbeCase
    evidence_dir: Path


class ProbeReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)
    case: ProbeCase
    checks: dict[str, bool]
    hashes: dict[str, str]
    error_type: str = ""


def _seed_collisions(db: Session) -> None:
    facility = db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one()
    db.execute(text(
        "INSERT INTO facilities(id,facility_key,display_name,timezone,is_active,created_at,updated_at) "
        "VALUES(902,'metadata-probe-902','Synthetic facility','UTC',1,:now,:now)"
    ), {"now": CAPTURED_AT})
    for row_id, source, source_id, facility_id in (
        (501, "manual_upload", "SOURCE-A", facility),
        (502, "manual_upload", "SOURCE-B", 902),
        (503, "alleva_rest_api", "SOURCE-A", facility),
    ):
        db.execute(text(
            "INSERT INTO patients(id,facility_id,canonical_client_id,source_system,source_patient_id,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(:id,:facility,:mrn,:source,:source_id,'active',:now,:now)"
        ), {"id": row_id, "facility": facility_id, "mrn": MRN, "source": source, "source_id": source_id, "now": CAPTURED_AT})
    db.commit()


def _run_probe(root: Path, probe_case: ProbeCase) -> ProbeReceipt:
    from app.core.config import settings
    from app.v2.authorization import require_patient_row_read
    from app.v2.db import SessionLocal, engine, init_database
    from app.v2.models import User
    from app.v2.services.audit_store import record_audit_event
    from app.v2.services.clinical_snapshot_codec import AggregateSnapshot, ClinicalSnapshotCodec
    from app.v2.services.manual_binder import ManualBinderFile, ManualBinderRequest, aggregate_from_manual_binder
    from app.v2.services.manual_patient_snapshot import ManualPatientNameInput, persist_manual_patient_name
    from app.v2.services.manual_source_file_store import ManualSourceFileArchiveInput, archive_manual_source_file, download_manual_source_file
    from app.v2.services.patient_snapshot_store import patient_source_snapshot_for_record
    from app.v2.services.secure_storage import encrypt_bytes
    from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

    assert settings.sqlite_db_path.resolve().is_relative_to(root.resolve())
    checks: dict[str, bool] = {}
    hashes: dict[str, str] = {}
    raw = (f"MRN: {MRN}\npatient_name: {SENTINEL}\nserviceDate: 2026-08-09\n"
           "original_plan_reference: ORIGINAL-2026-08-10\nCompletion/signature: completed 2026-08-11").encode()
    try:
        init_database()
        with SessionLocal() as db:
            _seed_collisions(db)
            actor = db.execute(select(User).where(User.username == "metadata-probe-admin")).scalar_one()
            scope = require_patient_row_read(db, actor, 501)
            result = aggregate_from_manual_binder(ManualBinderRequest((ManualBinderFile(raw, "synthetic.txt"),), "", False))
            saved = save_treatment_plan_aggregate(db, result.aggregate, actor, source_patient_id="SOURCE-A")
            archived = archive_manual_source_file(db, ManualSourceFileArchiveInput(
                raw, MRN, saved.plan_id, "text", "text/plain", str(actor.id)
            ))
            identity_rows = db.execute(text("SELECT id,facility_id,canonical_client_id,source_system,source_patient_id FROM patients ORDER BY id")).all()
            created = persist_manual_patient_name(db, ManualPatientNameInput(scope.patient_row_id, MRN, result.patient_full_name), CAPTURED_AT)
            record_audit_event(db, action="manual_metadata.probe", actor=actor, details={"created_count": created}, commit=False)
            db.commit()
            require_patient_row_read(db, actor, 501)
            recovered = patient_source_snapshot_for_record(db, 501, "manual_upload")
            checks["authorized_name_roundtrip"] = created == 1 and recovered is not None and recovered.full_name == SENTINEL
            checks["source_isolation"] = patient_source_snapshot_for_record(db, 503, "manual_upload") is None
            try:
                require_patient_row_read(db, actor, 502)
            except HTTPException as exc:
                checks["cross_facility_denied"] = exc.status_code == 403
            else:
                checks["cross_facility_denied"] = False
            checks["source_bytes_preserved"] = download_manual_source_file(db, MRN, archived.document_id).raw_bytes == raw
            hashes["source_sha256"] = hashlib.sha256(raw).hexdigest()
            checks["source_checksum_preserved"] = archived.sha256 == hashes["source_sha256"]
            checks["original_identity_preserved"] = identity_rows == db.execute(text(
                "SELECT id,facility_id,canonical_client_id,source_system,source_patient_id FROM patients ORDER BY id"
            )).all()
            checks["plan_identity_preserved"] = saved.plan_id == result.aggregate.content_snapshot.plan_id
            checks["name_excluded_from_aggregate"] = SENTINEL not in result.aggregate.model_dump_json()
            snapshot = result.aggregate.content_snapshot
            checks["metadata_separate_from_clinical_dates"] = (
                snapshot.service_date == "2026-08-09" and snapshot.original_plan_reference == "ORIGINAL-2026-08-10"
                and result.aggregate.admission_date == "Unknown" and result.aggregate.date_clock_anchor == "Unknown"
                and snapshot.signatures[0].signature_datetime == ""
            )
            if probe_case == "edge":
                before = db.execute(text("SELECT snapshot_encrypted FROM patient_snapshot_versions WHERE patient_id=501")).scalar_one()
                other = ManualBinderFile(f"MRN: {MRN}\npatient_full_name: SYNTHETIC-OTHER-PROBE\nservice_date: 2026-08-12".encode(), "other.txt")
                sources = (ManualBinderFile(raw, "synthetic.txt"), other)
                forward = aggregate_from_manual_binder(ManualBinderRequest(sources, "", False))
                reverse = aggregate_from_manual_binder(ManualBinderRequest(tuple(reversed(sources)), "", False))
                omitted = persist_manual_patient_name(db, ManualPatientNameInput(501, MRN, forward.patient_full_name), CAPTURED_AT)
                db.commit()
                after = db.execute(text("SELECT snapshot_encrypted FROM patient_snapshot_versions WHERE patient_id=501")).scalar_one()
                checks["conflict_has_no_order_winner"] = forward == reverse and forward.patient_full_name == "" and forward.aggregate.content_snapshot.service_date == ""
                checks["omission_preserves_ciphertext"] = omitted == 0 and before == after
                warnings = " ".join(forward.warnings)
                checks["warnings_redacted"] = SENTINEL not in warnings and "SYNTHETIC-OTHER-PROBE" not in warnings
                hashes["preserved_snapshot_sha256"] = hashlib.sha256(after).hexdigest()
            payload = result.aggregate.model_dump(mode="json")
            payload["content_snapshot"].pop("service_date")
            payload["content_snapshot"].pop("original_plan_reference")
            legacy = encrypt_bytes(json.dumps(payload).encode())
            decoded = ClinicalSnapshotCodec(settings.effective_data_encryption_secret).decode_plan(legacy)
            checks["old_payload_defaults"] = isinstance(decoded, AggregateSnapshot) and decoded.aggregate.content_snapshot.service_date == "" and decoded.aggregate.content_snapshot.original_plan_reference == ""
            checks["audit_redacted"] = SENTINEL not in str(db.execute(text("SELECT details FROM audit_logs")).all())
            checks["sqlite_integrity"] = db.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            checks["foreign_keys_valid"] = db.execute(text("PRAGMA foreign_key_check")).all() == []
        engine.dispose()
        checks["stored_bytes_redacted"] = all(SENTINEL.encode() not in path.read_bytes() for path in root.rglob("*") if path.is_file())
        hashes["database_sha256"] = hashlib.sha256(settings.sqlite_db_path.read_bytes()).hexdigest()
        return ProbeReceipt(case=probe_case, checks=checks, hashes=hashes)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated, synthetic manual-metadata SQLite/codec probe.")
    parser.add_argument("--case", choices=("happy", "edge"), required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    options = ProbeOptions.model_validate(vars(parser.parse_args()))
    output = StringIO()
    handler = logging.StreamHandler(output)
    logger = logging.getLogger()
    logger.addHandler(handler)
    try:
        with TemporaryDirectory(prefix="iz-cna-manual-metadata-") as temporary:
            root = Path(temporary)
            os.environ.update({
                "IZ_CNA_ENV_FILE": "", "ENVIRONMENT": "test", "IZ_CNA_LOCAL_APP_DATA_DIR": str(root),
                "IZ_CNA_LOCAL_SQLITE_DB_PATH": str(root / "metadata.sqlite3"),
                "IZ_CNA_SECRET_KEY": secrets.token_urlsafe(36), "IZ_CNA_DATA_ENCRYPTION_KEY": secrets.token_urlsafe(36),
                "IZ_CNA_BOOTSTRAP_ADMIN_USERNAME": "metadata-probe-admin", "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(36),
            })
            try:
                receipt = _run_probe(root, options.case)
            except (AssertionError, HTTPException, SQLAlchemyError, OSError) as exc:
                receipt = ProbeReceipt(case=options.case, checks={"runtime_completed": False}, hashes={}, error_type=type(exc).__name__)
        receipt.checks["logs_redacted"] = SENTINEL not in output.getvalue()
        receipt.checks["owned_runtime_cleaned"] = True
    finally:
        logger.removeHandler(handler)
    options.evidence_dir.mkdir(parents=True, exist_ok=True)
    filename = "task-4-storage.json" if options.case == "happy" else "task-4-metadata-error.txt"
    (options.evidence_dir / filename).write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    print(receipt.model_dump_json())
    return 0 if all(receipt.checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
