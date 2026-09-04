from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal, assert_never

import pytest

from test_v2_plan_version_corrections import CorrectionScenario, _workflow_state, scenario as scenario
from test_v2_evaluation_persistence import _aggregate


@pytest.fixture
def legacy_item(scenario: CorrectionScenario) -> int:
    return _seed_legacy_item(scenario, linked=False)


def _seed_legacy_item(scenario: CorrectionScenario, *, linked: bool) -> int:
    timestamp = "2000-01-01T00:00:00+00:00"
    with sqlite3.connect(scenario.database) as connection:
        if linked:
            existing_timestamp = connection.execute(
                "SELECT created_at FROM (SELECT created_at FROM manager_dispositions "
                "UNION ALL SELECT created_at FROM treatment_plan_manager_actions) "
                "ORDER BY julianday(created_at) LIMIT 1",
            ).fetchone()[0]
            timestamp = (
                datetime.fromisoformat(existing_timestamp).replace(tzinfo=timezone.utc) - timedelta(seconds=1)
            ).isoformat()
        action = connection.execute(
            "INSERT INTO treatment_plan_manager_actions(patient_id,criterion_id,action,comment,override_reason,"
            "actor_user_id,actor_username,actor_role,created_at) "
            "SELECT patient_id,criterion_id,action,'Synthetic unassigned return.','',actor_user_id,"
            "actor_username,actor_role,? FROM treatment_plan_manager_actions ORDER BY id LIMIT 1", (timestamp,),
        ).lastrowid
        connection.execute("INSERT INTO manager_action_plan_links(action_id,plan_version_id) VALUES(?,?)", (
            action, scenario.version_id if linked else None,
        ))
        disposition = connection.execute(
            "INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) "
            "SELECT plan_version_id,criterion_id,status,'Synthetic unassigned return.',actor_user_id,"
            "? FROM manager_dispositions ORDER BY id LIMIT 1", (timestamp,),
        ).lastrowid
        work_item = connection.execute(
            "INSERT INTO correction_work_items(plan_version_id,criterion_id,disposition_id,assigned_counselor_user_id,"
            "status,opened_at,idempotency_key) SELECT plan_version_id,criterion_id,?,assigned_counselor_user_id,"
            "'open',?,'legacy-unassigned' FROM correction_work_items ORDER BY id LIMIT 1",
            (disposition, timestamp),
        ).lastrowid
        assert work_item is not None
        return work_item


@pytest.mark.parametrize("later_exact_action", (False, True))
def test_unassigned_legacy_item_never_enters_selected_queue(
    scenario: CorrectionScenario, legacy_item: int, later_exact_action: bool,
) -> None:
    # Given: an old mechanically linked work item whose manager action remains unassigned.
    from sqlalchemy import select
    from app.v2.db import SessionLocal
    from app.v2.models import User
    from app.v2.services.manager_action_store import open_correction_counts_by_version, save_manager_action_record

    if later_exact_action:
        with SessionLocal() as db:
            actor = db.execute(select(User).where(User.username == "admin")).scalar_one()
            save_manager_action_record(
                db, patient_id="C-T3-001", plan_version_id=scenario.version_id, criterion_id="confirm_current_loc",
                action="return_for_correction", comment="Synthetic unassigned return.", override_reason="", actor=actor,
            )
    # When: the manager reads the current correction queue and exact-version counts.
    response = scenario.client.get("/api/v2/corrections", headers=scenario.admin)
    with SessionLocal() as db:
        counts = open_correction_counts_by_version(db)
    # Then: no later action revives the unassigned historical work item.
    assert response.status_code == 200
    assert legacy_item not in {item["work_item_id"] for item in response.json()["items"]}
    assert counts[scenario.version_id] == 1


def test_unassigned_legacy_item_cannot_be_submitted(scenario: CorrectionScenario, legacy_item: int) -> None:
    # Given: a synthetic legacy correction whose source action has no immutable attribution.
    before = _workflow_state(scenario)
    # When: its previously assigned counselor attempts submission.
    response = scenario.submit(work_item_id=legacy_item)
    # Then: unresolved lineage is not a selected-plan write target.
    assert response.status_code == 404
    assert _workflow_state(scenario) == before


def test_provable_legacy_item_preserves_its_exact_workflow(scenario: CorrectionScenario) -> None:
    # Given: a unique historical return event with an exact non-NULL version link.
    work_item_id = _seed_legacy_item(scenario, linked=True)
    # When: the assigned counselor submits the legacy work item.
    response = scenario.submit(work_item_id=work_item_id)
    # Then: proven legacy attribution remains usable without rewriting any historical row.
    assert response.status_code == 200
    assert response.json()["plan_version_id"] == scenario.version_id


def test_unassigned_legacy_item_does_not_grant_patient_access(scenario: CorrectionScenario, legacy_item: int) -> None:
    # Given: only an unassigned historical work item remains open for this counselor.
    with sqlite3.connect(scenario.database) as connection:
        connection.execute("UPDATE correction_work_items SET status='submitted' WHERE id=?", (scenario.work_item_id,))
    # When: the counselor attempts to read the purported work item's exact plan.
    response = scenario.client.get(
        "/api/v2/treatment-plans/C-T3-001", headers=scenario.counselor,
        params={"plan_version_id": scenario.version_id},
    )
    # Then: historical ambiguity grants no access to encrypted patient evidence.
    assert legacy_item != scenario.work_item_id
    assert response.status_code == 403


def test_concurrent_close_returns_conflict_before_decode(
    scenario: CorrectionScenario, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: another request closes the work item after this request reads its open snapshot.
    from app.v2.api import correction_routes

    loader = correction_routes.correction_work_item_for_id
    before = _workflow_state(scenario)
    def close_after_read(db, work_item_id):
        item = loader(db, work_item_id)
        with sqlite3.connect(scenario.database) as connection:
            connection.execute("UPDATE correction_work_items SET status='submitted' WHERE id=?", (work_item_id,))
        return item
    def reject_decode(*args):
        message = "closed correction decoded"
        raise AssertionError(message)
    monkeypatch.setattr(correction_routes, "correction_work_item_for_id", close_after_read)
    monkeypatch.setattr(correction_routes, "treatment_plan_aggregate_for_version", reject_decode)
    # When: the stale request tries to claim the work item.
    response = scenario.submit()
    # Then: conflict appends no history, disposition, evaluation, or correction audit.
    assert response.status_code == 409
    after = _workflow_state(scenario)
    assert after[:2] == before[:2]
    assert after[3:] == before[3:]


@pytest.mark.parametrize("assignment", ("wrong_facility", "different_source"))
def test_return_rejects_counselor_without_exact_patient_scope(
    scenario: CorrectionScenario, assignment: Literal["wrong_facility", "different_source"],
) -> None:
    # Given: an explicit counselor outside the facility, or an inferred assignment for another source row.
    from sqlalchemy import select, text
    from app.v2.db import SessionLocal
    from app.v2.domain.schemas import TreatmentPlanAggregate
    from app.v2.models import User
    from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

    with SessionLocal() as db:
        counselor = db.execute(select(User).where(User.username == "counselor")).scalar_one()
        match assignment:
            case "wrong_facility":
                db.execute(text("DELETE FROM user_facilities WHERE user_id=:id"), {"id": counselor.id})
                username = "counselor"
            case "different_source":
                actor = db.execute(select(User).where(User.username == "admin")).scalar_one()
                plan = TreatmentPlanAggregate.model_validate(_aggregate("C-T3-001").model_dump()).model_copy(
                    update={"source_mode": "alleva_rest_api"},
                )
                save_treatment_plan_aggregate(db, plan, actor, commit=False)
                db.execute(text(
                    "INSERT INTO patient_assignments(patient_id,counselor_user_id,assigned_by_user_id,assigned_at,is_active) "
                    "SELECT id,:counselor,:actor,:timestamp,1 FROM patients WHERE source_system='alleva_rest_api'"
                ), {"counselor": counselor.id, "actor": actor.id, "timestamp": datetime.now(timezone.utc).isoformat()})
                username = ""
            case unreachable:
                assert_never(unreachable)
        db.commit()
    before = _workflow_state(scenario)
    # When: the manager returns the exact manual-source version using that counselor selection.
    response = scenario.client.post(
        "/api/v2/treatment-plans/C-T3-001/manager-actions", headers=scenario.admin,
        json={"plan_version_id": scenario.version_id, "criterion_id": "confirm_current_loc", "action": "return_for_correction",
              "comment": "Synthetic scope rejection.", "assigned_counselor_username": username},
    )
    # Then: source or facility coincidence creates no action, link, disposition, or work item.
    assert response.status_code == 404
    assert _workflow_state(scenario) == before
