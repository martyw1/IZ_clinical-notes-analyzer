from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.v2.models import Base, TreatmentPlanImport, TreatmentPlanManagerAction


def test_legacy_treatment_plan_import_is_one_mutable_row_per_patient(tmp_path) -> None:
    # Given: the current V2 SQLAlchemy metadata on an empty SQLite database.
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    Base.metadata.create_all(engine)

    # When: two plan imports use the same canonical patient identifier.
    with Session(engine) as session:
        session.add(
            TreatmentPlanImport(
                patient_id="synthetic-client-100",
                plan_id="synthetic-plan-a",
                content_hash="a" * 64,
                encrypted_payload="encrypted-a",
            )
        )
        session.commit()
        session.add(
            TreatmentPlanImport(
                patient_id="synthetic-client-100",
                plan_id="synthetic-plan-b",
                content_hash="b" * 64,
                encrypted_payload="encrypted-b",
            )
        )

        # Then: the legacy schema rejects version history for that patient.
        with pytest.raises(IntegrityError):
            session.commit()


def test_legacy_manager_action_has_no_plan_version_foreign_key(tmp_path) -> None:
    # Given: the current V2 SQLAlchemy metadata on an empty SQLite database.
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    Base.metadata.create_all(engine)

    # When: the manager-action table is inspected and an orphan action is written.
    columns = {column["name"] for column in inspect(engine).get_columns("treatment_plan_manager_actions")}
    with Session(engine) as session:
        session.add(
            TreatmentPlanManagerAction(
                patient_id="synthetic-client-404",
                criterion_id="criterion-1",
                action="review",
                actor_user_id="999",
                created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()
        stored = session.execute(select(TreatmentPlanManagerAction)).scalar_one()

    # Then: linkage is patient-only and the orphan row is accepted.
    assert "plan_version_id" not in columns
    assert stored.patient_id == "synthetic-client-404"
