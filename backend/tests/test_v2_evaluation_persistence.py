from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, NoReturn

import pytest

from app.v2.services.manual_file_aggregate import build_manual_aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client
from test_v2_timeliness import _parsed_fields

PRIVACY_CANARY = "SYNTHETIC-PATIENT-NAME-MUST-NOT-CROSS"


def _aggregate(patient_id: str = "942"):
    admission = date.today() - timedelta(days=20)
    return build_manual_aggregate(_parsed_fields(
        admission_date=admission.isoformat(), signature_datetime=admission.isoformat(),
        due_date=(admission + timedelta(days=30)).isoformat(),
    )).model_copy(update={"patient_id": patient_id, "patient_display_label": PRIVACY_CANARY})


def _database_path(tmp_path: Path) -> Path:
    return tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"


def test_import_persists_exact_versioned_criterion_provenance_and_refresh_is_idempotent(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When
    imported = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=_aggregate().model_dump(mode="json"))
    detail = client.get("/api/v2/treatment-plans/942", headers=headers)
    refreshed = client.post("/api/v2/treatment-plans/942/evaluations/refresh", headers=headers)

    # Then
    assert imported.status_code == 201
    assert detail.status_code == 200
    payload = detail.json()
    assert len(payload["criteria_results"]) == 42
    assert payload["checklist_version"] == "1.2.0"
    assert payload["rules_version"] == "1.2.0"
    assert payload["evaluation_date"] == date.today().isoformat()
    assert all(item["source_json_paths"] and item["finding_message"] for item in payload["criteria_results"])
    assert refreshed.status_code == 200
    assert refreshed.json()["versions_evaluated"] == 1
    with sqlite3.connect(_database_path(tmp_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM criterion_results").fetchone() == (42,)
        assert connection.execute("SELECT COUNT(DISTINCT source_record_version_id) FROM criterion_results").fetchone() == (1,)


def test_each_immutable_plan_version_gets_an_independent_evaluation(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    first = _aggregate("943")
    second = first.model_copy(update={"source_due_date": "2027-01-01", "date_clock_due_date": "2027-01-01"})

    # When
    first_response = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=first.model_dump(mode="json"))
    second_response = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=second.model_dump(mode="json"))

    # Then
    assert first_response.status_code == 201
    assert second_response.status_code == 201
    with sqlite3.connect(_database_path(tmp_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_versions").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM criterion_results").fetchone() == (84,)
        linked = connection.execute(
            "SELECT COUNT(DISTINCT source_record_version_id) FROM criterion_results"
        ).fetchone()
        assert linked == (2,)


def test_patient_name_canary_is_removed_before_api_ledger_and_audit_boundaries(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When
    response = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=_aggregate("944").model_dump(mode="json"))
    detail = client.get("/api/v2/treatment-plans/944", headers=headers)
    audit = client.get("/api/audit/logs", headers=headers)

    # Then
    assert response.status_code == 201
    assert PRIVACY_CANARY not in detail.text
    assert PRIVACY_CANARY not in audit.text
    database_bytes = _database_path(tmp_path).read_bytes()
    assert PRIVACY_CANARY.encode("utf-8") not in database_bytes
    with sqlite3.connect(_database_path(tmp_path)) as connection:
        rows = connection.execute(
            "SELECT evaluated_value_safe,explanation FROM criterion_results"
        ).fetchall()
        assert PRIVACY_CANARY not in repr(rows)


@pytest.mark.parametrize("trigger", ("startup", "migration", "rule_config", "loc_change", "new_review"))
def test_all_version_reevaluation_supports_system_triggers(
    tmp_path,
    monkeypatch,
    trigger: Literal["startup", "migration", "rule_config", "loc_change", "new_review"],
) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=_aggregate("945").model_dump(mode="json"),
    )
    assert imported.status_code == 201
    from sqlalchemy import text
    from app.v2.db import SessionLocal
    from app.v2.services.evaluation_store import reevaluate_all_plan_versions
    with SessionLocal() as db:
        db.execute(text("DELETE FROM criterion_results"))
        db.execute(text("DELETE FROM evaluation_runs"))
        db.commit()

        # When
        refreshed = reevaluate_all_plan_versions(db, trigger)

        # Then
        assert refreshed.versions_evaluated == 1
        assert db.execute(text("SELECT trigger_kind FROM evaluation_runs")).scalar_one() == trigger
        assert db.execute(text("SELECT COUNT(*) FROM criterion_results")).scalar_one() == 42


def test_date_rollover_appends_a_new_run_and_recomputes_status(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=_aggregate("946").model_dump(mode="json"),
    )
    assert imported.status_code == 201
    from sqlalchemy import text
    from app.v2.db import SessionLocal
    from app.v2.services.evaluation_store import latest_plan_target, persist_plan_evaluation
    from app.v2.services.treatment_plan_store import treatment_plan_aggregate_for_patient
    with SessionLocal() as db:
        aggregate = treatment_plan_aggregate_for_patient(db, "946")
        target = latest_plan_target(db, "946")
        assert aggregate is not None and target is not None

        # When
        rolled = persist_plan_evaluation(
            db, aggregate, target, "date_rollover", instant=datetime.now(timezone.utc) + timedelta(days=31),
        )

        # Then
        assert rolled.overall_status == "Overdue"
        assert db.execute(text("SELECT COUNT(*) FROM evaluation_runs")).scalar_one() == 2


def test_refresh_returns_failure_not_success_when_rules_are_malformed(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=_aggregate("947").model_dump(mode="json"),
    )
    assert imported.status_code == 201
    from app.v2.services import evaluation_store
    from app.v2.services.rule_package import RuleConfigurationError

    def reject_malformed_rules() -> NoReturn:
        raise RuleConfigurationError("rules.yaml", "synthetic malformed configuration")

    monkeypatch.setattr(evaluation_store, "load_rule_package", reject_malformed_rules)

    # When
    refreshed = client.post("/api/v2/treatment-plans/947/evaluations/refresh", headers=headers)

    # Then
    assert refreshed.status_code == 503
    assert refreshed.json()["detail"].startswith("Invalid deterministic rule configuration")
    audit = client.get("/api/audit/logs", headers=headers)
    assert "treatment_plan.evaluation.refreshed" not in audit.text


def test_loc_change_checkbox_cannot_activate_compliance(tmp_path, monkeypatch) -> None:
    # Given
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    settings_response = client.patch(
        "/api/settings", headers=headers, json={"treatment_plan_loc_change_window_validated": True},
    )
    assert settings_response.status_code == 200
    aggregate = _aggregate("948").model_copy(update={"loc_history": (
        {"level_of_care": "IOP", "effective_date": "2026-01-01"},
        {"level_of_care": "PHP", "effective_date": "2026-02-01"},
    )})

    # When
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=aggregate.model_dump(mode="json"),
    )
    detail = client.get("/api/v2/treatment-plans/948", headers=headers)

    # Then
    assert imported.status_code == 201
    assert detail.json()["overall_status"] == "Needs Review"
    assert detail.json()["loc_change_due_date"] != "unvalidated_configurable"
    criterion = next(
        item for item in detail.json()["criteria_results"] if item["criterion_id"] == "loc_change_deadline_unresolved"
    )
    assert criterion["result_status"] == "Needs Review"
