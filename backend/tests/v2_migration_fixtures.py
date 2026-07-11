from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.v2.models import (
    AppSetting,
    Base,
    TreatmentPlanImport,
    TreatmentPlanManagerAction,
    UploadedDocument,
    User,
)

SYNTHETIC_SECRET = "synthetic-migration-secret"


def encrypted_text(value: str, secret: str = SYNTHETIC_SECRET) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    token = Fernet(key).encrypt(value.encode("utf-8"))
    stored = b"IZCNA1:" + token
    return "enc:v1:" + base64.urlsafe_b64encode(stored).decode("ascii")


def create_legacy_database(root: Path, *, ambiguous_actions: bool = False) -> Path:
    database_path = root / "clinical-notes-analyzer-v2.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    created = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    payload = {
        "patient_id": "synthetic-client-200",
        "source_mode": "manual_upload",
        "admission_date": "2026-06-01",
        "content_snapshot": {
            "plan_id": "synthetic-plan-1",
            "content_hash": "1" * 64,
            "problems": [],
        },
        "treatment_plans": [
            {"id": "synthetic-plan-1", "plan_date": "2026-06-01", "content": "safe-one"},
            {"id": "synthetic-plan-2", "plan_date": "2026-07-01", "content": "safe-two"},
        ],
        "treatment_reviews": [
            {"id": "synthetic-review-1", "review_date": "2026-06-15", "content": "safe-review-one"},
            {"id": "synthetic-review-2", "review_date": "2026-07-05", "content": "safe-review-two"},
        ],
    }
    with Session(engine) as session:
        admin = User(
            username="admin",
            full_name="Synthetic Administrator",
            password_hash="synthetic-hash",
            role="admin",
            is_active=True,
        )
        manager = User(
            username="manager",
            full_name="Synthetic Manager",
            password_hash="synthetic-hash",
            role="manager",
            is_active=True,
        )
        session.add_all((admin, manager, AppSetting(facility_timezone="America/New_York")))
        session.flush()
        session.add(
            TreatmentPlanImport(
                patient_id="synthetic-client-200",
                plan_id="synthetic-plan-1",
                source_mode="manual_upload",
                content_hash="1" * 64,
                encrypted_payload=encrypted_text(json.dumps(payload, sort_keys=True)),
                created_by_user_id=str(admin.id),
                created_at=created,
                updated_at=created,
            )
        )
        session.add(
            UploadedDocument(
                document_id="synthetic-document-1",
                patient_id="synthetic-client-200",
                plan_id="synthetic-plan-1",
                source_kind="manual_treatment_plan_file",
                source_format="txt",
                content_type="text/plain",
                size_bytes=24,
                sha256="d" * 64,
                storage_path="uploads/synthetic-document.enc",
                created_by_user_id=str(admin.id),
                created_at=created,
            )
        )
        action_patient = "synthetic-client-200" if ambiguous_actions else "synthetic-client-404"
        session.add(
            TreatmentPlanManagerAction(
                patient_id=action_patient,
                criterion_id="criterion-1",
                action="review",
                comment="synthetic-safe-comment",
                actor_user_id=str(manager.id),
                actor_username="manager",
                actor_role="manager",
                created_at=created,
            )
        )
        session.commit()
    engine.dispose()
    return database_path
