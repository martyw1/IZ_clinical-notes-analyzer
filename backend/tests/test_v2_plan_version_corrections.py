from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, assert_never

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from test_v2_correction_queue import _counselor_headers
from test_v2_evaluation_persistence import _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


@dataclass(frozen=True, slots=True)
class CorrectionScenario:
    client: TestClient
    admin: dict[str, str] = field(repr=False)
    counselor: dict[str, str] = field(repr=False)
    database: Path
    work_item_id: int
    version_id: int
    patient_record_id: int

    def submit(self, **selectors: int | str) -> Response:
        return self.client.post(
            "/api/v2/treatment-plans/C-T3-001/correction-submissions",
            headers=self.counselor,
            json={"work_item_id": self.work_item_id, "criterion_id": "confirm_current_loc",
                  "comment": "Synthetic correction submitted.", **selectors},
        )


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CorrectionScenario]:
    client = _fresh_client(tmp_path, monkeypatch)
    admin = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate", headers=admin,
        json=_aggregate("C-T3-001").model_dump(mode="json"),
    )
    assert imported.status_code == 201
    counselor = _counselor_headers(client, admin)
    returned = client.post(
        "/api/v2/treatment-plans/C-T3-001/manager-actions", headers=admin,
        json={"criterion_id": "confirm_current_loc", "action": "return_for_correction",
              "comment": "Synthetic correction needed.", "assigned_counselor_username": "counselor"},
    )
    assert returned.status_code == 200, returned.text
    from app.core.config import settings

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        work_item, version, patient = connection.execute(
            "SELECT c.id,c.plan_version_id,v.patient_id FROM correction_work_items c "
            "JOIN treatment_plan_versions v ON v.id=c.plan_version_id"
        ).fetchone()
    yield CorrectionScenario(client, admin, counselor, settings.sqlite_db_path, work_item, version, patient)


def _import_newer_plan(scenario: CorrectionScenario) -> int:
    aggregate = _aggregate("C-T3-001").model_copy(update={"source_due_date": "2028-01-01"})
    imported = scenario.client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate", headers=scenario.admin,
        json=aggregate.model_dump(mode="json"),
    )
    assert imported.status_code == 201
    with sqlite3.connect(scenario.database) as connection:
        return connection.execute("SELECT max(id) FROM treatment_plan_versions").fetchone()[0]


def _workflow_state(scenario: CorrectionScenario) -> tuple[tuple[tuple[str | int | None, ...], ...], ...]:
    with sqlite3.connect(scenario.database) as connection:
        return tuple(tuple(connection.execute(sql).fetchall()) for sql in (
            "SELECT id,action FROM treatment_plan_manager_actions ORDER BY id",
            "SELECT action_id,plan_version_id FROM manager_action_plan_links ORDER BY action_id",
            "SELECT id,status,closed_at FROM correction_work_items ORDER BY id",
            "SELECT id,plan_version_id,status FROM manager_dispositions ORDER BY id",
            "SELECT id,plan_version_id FROM evaluation_runs ORDER BY id",
            "SELECT id,action FROM audit_logs WHERE action='correction.submitted' ORDER BY id",
        ))


def test_single_version_assigned_correction_submits(scenario: CorrectionScenario) -> None:
    # Given: an explicit work-item grant without a standing patient assignment.
    # When: the assigned counselor submits the only plan's correction.
    response = scenario.submit()
    # Then: the existing successful workflow remains available.
    assert response.status_code == 200
    with sqlite3.connect(scenario.database) as connection:
        assert connection.execute("SELECT status FROM correction_work_items").fetchone() == ("submitted",)


def test_correction_evaluates_work_item_version_after_new_import(scenario: CorrectionScenario) -> None:
    # Given: a returned old version while a newer version is imported during review.
    newer = _import_newer_plan(scenario)
    assert newer != scenario.version_id
    # When: the counselor submits the old work item without a client-side version hint.
    response = scenario.submit()
    # Then: only the old immutable version receives the correction evaluation.
    assert response.status_code == 200
    with sqlite3.connect(scenario.database) as connection:
        assert connection.execute(
            "SELECT plan_version_id FROM evaluation_runs WHERE trigger_kind='correction'"
        ).fetchall() == [(scenario.version_id,)]
        assert connection.execute(
            "SELECT l.plan_version_id FROM manager_action_plan_links l JOIN treatment_plan_manager_actions a "
            "ON a.id=l.action_id WHERE a.action='correction_submitted'"
        ).fetchall() == [(scenario.version_id,)]
        assert connection.execute(
            "SELECT plan_version_id FROM manager_dispositions WHERE status='correction_submitted'"
        ).fetchall() == [(scenario.version_id,)]


@pytest.mark.parametrize("selector", ("plan_version_id", "patient_record_id", "source_mode", "treatment_plan_id"))
def test_correction_rejects_mismatched_selector_without_mutation(
    scenario: CorrectionScenario, selector: str,
) -> None:
    # Given: an authorized work item and a conflicting supplied selector.
    before = _workflow_state(scenario)
    mismatch = 999999 if selector.endswith("_id") and selector != "treatment_plan_id" else "alleva_rest_api"
    # When: the conflicting immutable/source identity is submitted.
    response = scenario.submit(**{selector: mismatch})
    # Then: mismatch is not treated as a request for the patient's latest plan.
    assert response.status_code == 404
    assert _workflow_state(scenario) == before


def test_closed_correction_replay_returns_conflict_without_mutation(scenario: CorrectionScenario) -> None:
    # Given: a successfully submitted correction.
    assert scenario.submit().status_code == 200
    before = _workflow_state(scenario)
    # When: the same assigned counselor replays the work item.
    response = scenario.submit()
    # Then: replay appends no duplicate action, disposition, evaluation, or audit.
    assert response.status_code == 409
    assert _workflow_state(scenario) == before


def test_audit_failure_rolls_back_complete_correction(
    scenario: CorrectionScenario, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a pending correction and an unavailable audit writer.
    from app.v2.api import correction_routes

    before = _workflow_state(scenario)
    def fail_audit(*args, **kwargs) -> None:
        message = "synthetic audit unavailable"
        raise RuntimeError(message)
    monkeypatch.setattr(correction_routes, "record_audit_event", fail_audit)
    # When: submission cannot append its audit event.
    with pytest.raises(RuntimeError, match="synthetic audit unavailable"):
        scenario.submit()
    # Then: closing, history, disposition and evaluation all roll back.
    assert _workflow_state(scenario) == before


def test_queue_loads_work_item_version_after_new_import(
    scenario: CorrectionScenario, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a work item whose version is no longer latest.
    from app.v2.api import correction_routes

    _import_newer_plan(scenario)
    loaded_versions: list[int] = []
    exact_loader = correction_routes.treatment_plan_aggregate_for_version
    def capture_loader(db, version_id):
        loaded_versions.append(version_id)
        return exact_loader(db, version_id)
    monkeypatch.setattr(correction_routes, "treatment_plan_aggregate_for_version", capture_loader)
    # When: the assigned counselor opens the queue.
    response = scenario.client.get("/api/v2/corrections", headers=scenario.counselor)
    # Then: the title and displayed identity are loaded only from the work-item version.
    assert response.status_code == 200
    assert loaded_versions == [scenario.version_id]
    item = response.json()["items"][0]
    assert (item["plan_version_id"], item["patient_record_id"], item["source_mode"]) == (
        scenario.version_id, scenario.patient_record_id, "manual_upload",
    )


@pytest.mark.parametrize("access", ("admin", "other_counselor", "wrong_facility"))
def test_correction_denials_happen_before_decode(
    scenario: CorrectionScenario, monkeypatch: pytest.MonkeyPatch,
    access: Literal["admin", "other_counselor", "wrong_facility"],
) -> None:
    # Given: a caller who lacks the work item's role, assignee, or exact facility grant.
    from app.v2.api import correction_routes

    match access:
        case "admin":
            headers = scenario.admin
        case "other_counselor":
            headers = _counselor_headers(scenario.client, scenario.admin, username="other-counselor")
        case "wrong_facility":
            with sqlite3.connect(scenario.database) as connection:
                connection.execute("DELETE FROM user_facilities WHERE user_id=(SELECT id FROM users WHERE username='counselor')")
            headers = scenario.counselor
        case unreachable:
            assert_never(unreachable)
    before = _workflow_state(scenario)
    def reject_decode(*args):
        message = "unauthorized decode attempted"
        raise AssertionError(message)
    monkeypatch.setattr(correction_routes, "treatment_plan_aggregate_for_version", reject_decode)
    # When: the caller submits the otherwise correct work-item identity.
    response = scenario.client.post(
        "/api/v2/treatment-plans/C-T3-001/correction-submissions", headers=headers,
        json={"work_item_id": scenario.work_item_id, "criterion_id": "confirm_current_loc", "comment": "Synthetic denial."},
    )
    # Then: permission fails before any snapshot decode or workflow mutation.
    assert response.status_code == 403
    assert _workflow_state(scenario) == before


def test_unassigned_legacy_override_has_no_selected_version_effect(scenario: CorrectionScenario) -> None:
    # Given: a historical action with no proven immutable version identity.
    from sqlalchemy import select
    from app.v2.db import SessionLocal
    from app.v2.models import User
    from app.v2.services.manager_action_store import (
        manager_override_dicts_for_version, manager_review_dicts_for_version,
        save_manager_action_record, unassigned_manager_review_dicts_for_patient,
    )

    with SessionLocal() as db:
        actor = db.execute(select(User).where(User.username == "admin")).scalar_one()
        saved = save_manager_action_record(
            db, patient_id="C-T3-001", criterion_id="confirm_current_loc", action="override",
            comment="Synthetic legacy comment.", override_reason="Synthetic legacy reason.", actor=actor,
        )
        # When: exact-version workflow and unassigned historical views are read.
        selected = manager_review_dicts_for_version(db, scenario.version_id)
        overrides = manager_override_dicts_for_version(db, scenario.version_id)
        unassigned = unassigned_manager_review_dicts_for_patient(db, "C-T3-001")
        # Then: the legacy action is preserved only as explicitly unassigned history.
        assert saved.id not in {item["action_id"] for item in selected}
        assert overrides == ()
        assert [(item["action_id"], item["plan_version_id"], item["linkage_status"]) for item in unassigned] == [
            (saved.id, None, "unassigned"),
        ]
