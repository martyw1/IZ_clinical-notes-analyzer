#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic", "sqlalchemy"]
# ///
# How to run: scripts/test-office-manager-smoke.ps1 invokes this with the
# already installed backend/.venv/Scripts/python.exe and isolated environment.
# Do not run it against an existing app or install a separate dependency set.
from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Final

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from seed_contract import FailureFrame, FixtureContract, OwnershipMarker, PlanRef, SeedFailure, SeedFiles, UserRef

ROLES: Final = ("admin", "office_manager", "counselor", "viewer")
PATIENT_ONE: Final = "TEST-PATIENT-001"
PATIENT_TWO: Final = "TEST-PATIENT-002"


def plan_ref(db: Session, version_id: int) -> PlanRef:
    row = db.execute(text(
        "SELECT p.canonical_client_id AS patient_id,p.id AS patient_record_id,"
        "v.source_record_id AS plan_id,v.source_system AS source_mode,"
        "v.id AS plan_version_id,v.version_ordinal FROM treatment_plan_versions v "
        "JOIN patients p ON p.id=v.patient_id WHERE v.id=:id"
    ), {"id": version_id}).mappings().one()
    return PlanRef.model_validate(row)


def facility_collision(db: Session, source: PlanRef, secondary: int) -> PlanRef:
    """Create a genuinely separate patient/version, preserving the same synthetic MRN."""
    db.execute(text(
        "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
        "VALUES(:facility,:mrn,'manual_upload','active','2026-08-01T12:00:00+00:00','2026-08-01T12:00:00+00:00')"
    ), {"facility": secondary, "mrn": source.patient_id})
    patient_id = int(db.execute(text("SELECT last_insert_rowid()")).scalar_one())
    db.execute(text(
        "INSERT INTO treatment_plan_versions(patient_id,source_system,source_record_id,version_ordinal,"
        "plan_date,signature_date,admission_date,source_next_review_due,normalized_snapshot_encrypted,"
        "content_sha256,evidence_sha256,imported_at) "
        "SELECT :patient,source_system,source_record_id,1,plan_date,signature_date,admission_date,"
        "source_next_review_due,normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at "
        "FROM treatment_plan_versions WHERE id=:version"
    ), {"patient": patient_id, "version": source.plan_version_id})
    return plan_ref(db, int(db.execute(text("SELECT last_insert_rowid()")).scalar_one()))


def main() -> None:
    """Seed only a new, marker-owned OS-local database; emit no credentials."""
    runtime_dir = Path(os.environ["IZ_CNA_LOCAL_APP_DATA_DIR"]).resolve()
    owned_root = (Path(os.environ["LOCALAPPDATA"]) / "IZ-CNA-OfficeManager-Smoke").resolve()
    marker = OwnershipMarker.model_validate_json((runtime_dir / "owner.json").read_text(encoding="utf-8"))
    assert runtime_dir.parent == owned_root
    assert marker.runId == os.environ["IZ_OM_RUN_ID"] and Path(marker.dataDir).resolve() == runtime_dir
    assert not (runtime_dir / "clinical-notes-analyzer-v2.sqlite3").exists()

    from app.core.config import settings
    from app.v2.db import SessionLocal, engine, init_database
    from app.v2.models import AppSetting, User, utc_now
    from app.v2.security import hash_password
    from app.v2.services.manual_file_parser import aggregate_from_manual_file
    from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

    assert settings.sqlite_db_path.resolve().parent == runtime_dir
    init_database()
    users: dict[str, UserRef] = {}
    plans: dict[str, PlanRef] = {}
    binder = (
        f"MRN: {PATIENT_ONE}\nCurrent Level of Care: PHP\nAdmission Date: 2026-08-01\n"
        "Next Due Date: 2026-09-01\nSignature Date: 2026-08-02\n"
        "Reason for Admission: Synthetic QA source.\nProblem: Synthetic review required.\n"
        "Goal: Synthetic documented goal.\nObjective: Synthetic measurable objective.\n"
        "Intervention: Synthetic evidence-based intervention.\n"
    )
    aggregate = aggregate_from_manual_file(binder.encode(), PATIENT_ONE, "synthetic.txt").aggregate
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.username == os.environ["IZ_CNA_BOOTSTRAP_ADMIN_USERNAME"])).scalar_one()
        admin.must_reset_password = False
        admin.auth_state = "active"
        users["admin"] = UserRef(id=admin.id, username=admin.username)
        for role in ROLES[1:]:
            user = User(username=f"smoke_{role}", full_name=f"Synthetic {role}",
                        password_hash=hash_password(os.environ["IZ_OM_PASSWORD"]), role=role,
                        is_active=True, must_reset_password=False, auth_state="active")
            db.add(user)
            db.flush()
            users[role] = UserRef(id=user.id, username=user.username)
        settings_row = db.execute(select(AppSetting)).scalar_one()
        settings_row.facility_timezone = "America/New_York"
        primary = int(db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one())
        db.execute(text(
            "INSERT INTO facilities(facility_key,display_name,timezone,is_active,created_at,updated_at) "
            "VALUES('smoke-secondary','Synthetic secondary facility','America/New_York',1,:now,:now)"
        ), {"now": utc_now().isoformat()})
        secondary = int(db.execute(text("SELECT last_insert_rowid()")).scalar_one())
        for role, user_ref in users.items():
            for facility in ((primary, secondary) if role == "admin" else (primary,)):
                db.execute(text(
                    "INSERT OR IGNORE INTO user_facilities(user_id,facility_id,assigned_by_user_id,assigned_at) "
                    "VALUES(:user,:facility,:admin,:now)"
                ), {"user": user_ref.id, "facility": facility, "admin": admin.id, "now": utc_now().isoformat()})
        db.commit()
        for key, mrn, plan_id, stamp, source in (
            ("primaryV1", PATIENT_ONE, "smoke-primary", "2026-08-02T12:00:00+00:00", "manual_upload"),
            ("primaryV2", PATIENT_ONE, "smoke-primary", "2026-08-03T12:00:00+00:00", "manual_upload"),
            ("secondaryPlan", PATIENT_ONE, "smoke-secondary", "2026-08-04T12:00:00+00:00", "manual_upload"),
            ("patientTwo", PATIENT_TWO, "smoke-patient-two", "2026-08-05T12:00:00+00:00", "manual_upload"),
            ("sourceCollision", PATIENT_ONE, "smoke-primary", "2026-08-06T12:00:00+00:00", "alleva_rest_api"),
        ):
            snapshot = aggregate.content_snapshot.model_copy(update={"plan_id": plan_id, "patient_id": mrn, "source_mode": source})
            selected = aggregate.model_copy(update={
                "patient_id": mrn, "patient_display_label": f"MRN {mrn}", "source_mode": source,
                "source_last_updated": stamp, "content_snapshot": snapshot,
                "treatment_plans": ({"plan_id": plan_id, "plan_date": "2026-08-01", "is_active": True},),
            })
            save_treatment_plan_aggregate(db, selected, admin)
            version = int(db.execute(text("SELECT MAX(id) FROM treatment_plan_versions")).scalar_one())
            plans[key] = plan_ref(db, version)
        plans["facilityCollision"] = facility_collision(db, plans["primaryV2"], secondary)
        db.execute(text(
            "INSERT INTO patient_assignments(patient_id,counselor_user_id,assigned_by_user_id,assigned_at,is_active) "
            "VALUES(:patient,:counselor,:admin,:now,1)"
        ), {"patient": plans["primaryV1"].patient_record_id, "counselor": users["counselor"].id,
            "admin": admin.id, "now": utc_now().isoformat()})
        db.commit()
        files = SeedFiles(aggregate=str(runtime_dir / "synthetic-aggregate.json"), binder=str(runtime_dir / "synthetic-binder.txt"))
        Path(files.aggregate).write_text(aggregate.model_dump_json(), encoding="utf-8")
        Path(files.binder).write_text(binder, encoding="utf-8")
        contract = FixtureContract(
            run_id=marker.runId, physical_data_dir=str(runtime_dir), users=users, facilities={"primary": primary, "secondary": secondary},
            patients={"primary": plans["primaryV1"].patient_record_id, "secondary": plans["patientTwo"].patient_record_id,
                      "sourceCollision": plans["sourceCollision"].patient_record_id, "facilityCollision": plans["facilityCollision"].patient_record_id},
            plans=plans, files=files, schema_version=int(db.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar_one()),
            integrity_ok=db.execute(text("PRAGMA integrity_check")).scalar_one() == "ok",
            foreign_keys_ok=not db.execute(text("PRAGMA foreign_key_check")).all(),
        )
        assert contract.integrity_ok and contract.foreign_keys_ok
        (runtime_dir / "fixture-contract.json").write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BROAD_EXCEPT_OK - CLI boundary omits secret-bearing exception values.
        failure = SeedFailure(error_type=type(error).__name__, frames=tuple(
            FailureFrame(file=Path(frame.filename).name, line=frame.lineno, function=frame.name)
            for frame in traceback.extract_tb(error.__traceback__)
        ))
        (Path(os.environ["IZ_OM_EVIDENCE_DIR"]) / "seed-failure.json").write_text(failure.model_dump_json(indent=2), encoding="utf-8")
        raise SystemExit(1) from None
