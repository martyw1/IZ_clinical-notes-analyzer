from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO

import pytest
from sqlalchemy import text

from test_v2_evaluation_persistence import _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client
from fastapi.testclient import TestClient


@dataclass(frozen=True, slots=True)
class IdentityRuntime:
    client: TestClient = field(repr=False)
    headers: dict[str, str] = field(repr=False)

    def __iter__(self):
        return iter((self.client, self.headers))


class SyntheticAuditFailure(RuntimeError):
    pass


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    yield IdentityRuntime(client, _auth_headers(client))


def _import(runtime, plan_id="plan-a", marker="older", source="manual_upload"):
    client, headers = runtime
    payload = _aggregate("IDENTITY-001").model_dump(mode="json")
    payload["source_mode"] = source
    payload["content_snapshot"]["source_mode"] = source
    payload["content_snapshot"]["plan_id"] = plan_id
    payload["source_last_updated"] = marker
    if source == "manual_upload":
        response = client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=headers, json=payload)
        assert response.status_code == 201
    else:
        from app.v2.db import SessionLocal
        from app.v2.domain.schemas import TreatmentPlanAggregate
        from app.v2.models import User
        from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate
        with SessionLocal() as db:
            save_treatment_plan_aggregate(db, TreatmentPlanAggregate.model_validate(payload), db.get(User, 1))
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        row = db.execute(text("SELECT id,patient_id FROM treatment_plan_versions ORDER BY id DESC LIMIT 1")).one()
        return {"plan_version_id": int(row[0]), "patient_record_id": int(row[1]), "source_mode": source}


def _counts():
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        return {table: db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() for table in (
            "treatment_plan_manager_actions", "manager_dispositions", "correction_work_items", "evaluation_runs",
        )}


def test_selected_older_version_remains_exact_after_newer_import(runtime):
    # Given: an old selection, its replacement, and a sibling source plan.
    first = _import(runtime)
    _import(runtime, marker="newer")
    _import(runtime, plan_id="plan-b", marker="sibling")
    client, headers = runtime
    # When: the original immutable version is loaded.
    response = client.get("/api/v2/treatment-plans/IDENTITY-001/plan-a", params=first, headers=headers)
    # Then: neither subsequent import moves the selection.
    assert response.status_code == 200
    assert response.json()["source_last_updated"] == "older"
    assert response.json()["plan_version_id"] == first["plan_version_id"]
    assert response.json()["patient_record_id"] == first["patient_record_id"]


@pytest.mark.parametrize("path", [
    "/api/v2/treatment-plans/IDENTITY-001",
    "/api/v2/treatment-plans/IDENTITY-001/plan-a",
    "/api/v2/exports/IDENTITY-001/checklist-evidence.csv",
])
def test_legacy_read_and_export_reject_multiple_eligible_versions(runtime, path):
    # Given: more than one eligible immutable version.
    _import(runtime)
    _import(runtime, marker="newer")
    client, headers = runtime
    # When: the caller omits immutable identity.
    response = client.get(path, headers=headers)
    # Then: selection is required; latest is not inferred.
    assert response.status_code == 409
    assert response.json()["detail"] == "Select a specific treatment-plan version."


@pytest.mark.parametrize("selector", [{"source_mode": "alleva_rest_api"}, {"patient_record_id": 9999}, {"plan_version_id": 9999}])
def test_wrong_consistency_selector_fails_without_decryption(runtime, monkeypatch, selector):
    # Given: an existing version and an incompatible selector.
    selected = _import(runtime)
    client, headers = runtime
    def forbid_decode(*_args, **_kwargs):
        pytest.fail("Mismatched identity reached clinical decryption")
    monkeypatch.setattr("app.v2.services.clinical_snapshot_codec.ClinicalSnapshotCodec.decode_plan", forbid_decode)
    # When: the wrong identity is requested.
    response = client.get("/api/v2/treatment-plans/IDENTITY-001/plan-a", headers=headers, params=selected | selector)
    # Then: the mismatch is a safe not-found before any decrypt.
    assert response.status_code == 404


def test_selected_csv_includes_only_requested_immutable_identity(runtime):
    # Given: an older selected version and a newer sibling.
    first = _import(runtime)
    _import(runtime, plan_id="plan-b")
    client, headers = runtime
    # When: selected evidence is exported.
    response = client.get("/api/v2/exports/IDENTITY-001/checklist-evidence.csv", headers=headers, params=first)
    # Then: every row states the exact source/row/version and excludes names.
    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 42
    assert {row["plan_version_id"] for row in rows} == {str(first["plan_version_id"])}
    assert {row["patient_record_id"] for row in rows} == {str(first["patient_record_id"])}
    assert {row["source_mode"] for row in rows} == {"manual_upload"}
    assert "SYNTHETIC-PATIENT-NAME-MUST-NOT-CROSS" not in response.text


def test_ambiguous_write_and_refresh_make_no_changes(runtime):
    # Given: two versions and known ledger counts.
    _import(runtime)
    _import(runtime, marker="newer")
    client, headers = runtime
    before = _counts()
    # When: legacy mutation paths omit the required selection.
    action = client.post("/api/v2/treatment-plans/IDENTITY-001/manager-actions", headers=headers,
                         json={"criterion_id": "confirm_current_loc", "action": "comment"})
    refresh = client.post("/api/v2/treatment-plans/IDENTITY-001/evaluations/refresh", headers=headers)
    # Then: both fail closed with no history/evaluation effects.
    assert (action.status_code, refresh.status_code) == (409, 409)
    assert _counts() == before


@pytest.mark.parametrize("action", ["approve", "comment", "override"])
def test_manager_action_affects_only_selected_version(runtime, action):
    # Given: a selected old version and a newer version.
    first = _import(runtime)
    newer = _import(runtime, marker="newer")
    client, headers = runtime
    # When: the manager writes to the old immutable version.
    saved = client.post("/api/v2/treatment-plans/IDENTITY-001/manager-actions", headers=headers,
                        json=first | {"criterion_id": "confirm_current_loc", "action": action,
                                      "comment": "Synthetic selected comment", "override_reason": "Synthetic reason"})
    # Then: selected history and response link to it, not its replacement.
    assert saved.status_code == 200
    assert saved.json()["plan_version_id"] == first["plan_version_id"]
    older_detail = client.get("/api/v2/treatment-plans/IDENTITY-001", params=first, headers=headers).json()
    newer_detail = client.get("/api/v2/treatment-plans/IDENTITY-001", params=newer, headers=headers).json()
    assert [review["action"] for review in older_detail["manager_reviews"]] == [action]
    assert newer_detail["manager_reviews"] == []
    assert [review["comment"] for review in newer_detail["plan_comment_history"]] == ["Synthetic selected comment"]
    assert newer_detail["plan_comment_history"][0]["plan_version_id"] == first["plan_version_id"]
    assert newer_detail["overrides"] == []


def test_comments_survive_alleva_replacement_but_never_move_to_other_plans_or_sources(runtime):
    first = _import(runtime, source="alleva_rest_api", marker="2026-09-08")
    client, headers = runtime
    saved = client.post("/api/v2/treatment-plans/IDENTITY-001/manager-actions", headers=headers,
                        json=first | {"criterion_id": "confirm_current_loc", "action": "comment",
                                      "comment": "Synthetic persistent plan comment"})
    assert saved.status_code == 200
    newer = _import(runtime, source="alleva_rest_api", marker="2026-10-16")
    unchanged = _import(runtime, source="alleva_rest_api", marker="2026-10-16")
    assert unchanged["plan_version_id"] == newer["plan_version_id"]
    sibling = _import(runtime, source="alleva_rest_api", plan_id="plan-b")
    other_source = _import(runtime, source="manual_upload")
    detail = client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers, params=newer).json()
    assert len(detail["plan_comment_history"]) == 1
    assert detail["plan_comment_history"][0]["comment"] == "Synthetic persistent plan comment"
    assert detail["manager_reviews"] == []
    assert detail["overrides"] == []
    for selected in (sibling, other_source):
        assert client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers, params=selected).json()["plan_comment_history"] == []
    original = client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers, params=first).json()
    assert original["plan_comment_history"] == []
    assert original["manager_reviews"][0]["comment"] == "Synthetic persistent plan comment"


def test_saved_alleva_plan_uses_current_patient_loc_without_rewriting_history(runtime):
    first = _import(runtime, source="alleva_rest_api", marker="2026-09-01")
    latest = _import(runtime, source="alleva_rest_api", marker="2026-09-08")
    from app.v2.db import SessionLocal
    from app.v2.services.patient_snapshot_store import PatientSourceSnapshotInput, persist_patient_source_snapshots
    with SessionLocal() as db:
        persist_patient_source_snapshots(db, (PatientSourceSnapshotInput(
            mrn="IDENTITY-001", source_patient_id="IDENTITY-001", source_system="alleva_rest_api",
            source_last_updated="2026-10-16", record={"levelOfCare": {"name": "Outpatient"}},
            patient_record_id=latest["patient_record_id"],
        ),), "2026-10-16T12:00:00+00:00")
        db.commit()
    client, headers = runtime
    current = client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers, params=latest).json()
    assert current["current_level_of_care"] == "Outpatient"
    assert current["date_clock_due_date"] == "2026-11-07"
    original = client.get("/api/v2/treatment-plans/IDENTITY-001", headers=headers, params=first).json()
    assert original["current_level_of_care"] == "PHP"
    assert original["source_last_updated"] == "2026-09-01"


def test_selected_refresh_rolls_back_evaluation_on_audit_failure(runtime, monkeypatch):
    # Given: an exact version and an audit recorder that fails.
    first = _import(runtime)
    _import(runtime, marker="newer")
    client, headers = runtime
    before = _counts()
    def fail_audit(*_args, **_kwargs):
        raise SyntheticAuditFailure
    monkeypatch.setattr("app.v2.api.evaluation_routes.record_audit_event", fail_audit)
    # When: selected refresh cannot commit its audit.
    with pytest.raises(SyntheticAuditFailure):
        client.post("/api/v2/treatment-plans/IDENTITY-001/evaluations/refresh", params=first, headers=headers)
    # Then: no partial evaluation survived.
    assert _counts() == before
