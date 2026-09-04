from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from test_v2_evaluation_persistence import _aggregate
from test_v2_plan_version_actions import IdentityRuntime, _import, runtime
from test_v2_plan_version_authorization import _user


def test_same_mrn_names_project_only_from_exact_source_snapshots(runtime: IdentityRuntime) -> None:
    # Given: one MRN exists in manual and Alleva sources with different encrypted names.
    manual = runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
        json=_aggregate("IDENTITY-001").model_copy(update={"patient_full_name": "SYNTHETIC MANUAL NAME"}).model_dump(mode="json")).json()
    alleva = _import(runtime, source="alleva_rest_api")
    from app.v2.db import SessionLocal
    from app.v2.services.patient_snapshot_store import PatientSourceSnapshotInput, persist_patient_source_snapshots
    with SessionLocal() as db:
        persist_patient_source_snapshots(db, (PatientSourceSnapshotInput(
            mrn="IDENTITY-001", source_patient_id="IDENTITY-001", source_system="alleva_rest_api", source_last_updated="",
            record={"patient_full_name": "SYNTHETIC ALLEVA NAME"}, patient_record_id=alleva["patient_record_id"],
        ),), "2026-09-04")
        db.commit()
    # When: both rosters and exact patient details are requested by an authorized manager.
    expected = {"manual_upload": "SYNTHETIC MANUAL NAME", "alleva_rest_api": "SYNTHETIC ALLEVA NAME"}
    for route in ("patient-roster", "treatment-plan-roster", "treatment-plans"):
        rows = runtime.client.get(f"/api/v2/{route}", headers=runtime.headers).json()["items"]
        assert {row["source_mode"]: row["full_name"] for row in rows} == expected
    # Then: same-MRN rows never borrow a sibling source's name.
    for identity in (manual, alleva):
        detail = runtime.client.get("/api/v2/patients/IDENTITY-001", headers=runtime.headers,
            params={"patient_record_id": identity["patient_record_id"], "source_mode": identity["source_mode"]})
        assert detail.status_code == 200 and detail.json()["full_name"] == expected[identity["source_mode"]]


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_binder_names_preserve_prior_exact_snapshot(runtime: IdentityRuntime, reverse: bool) -> None:
    # Given: an existing explicit name and two conflicting later name labels.
    runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
        json=_aggregate("IDENTITY-001").model_copy(update={"patient_full_name": "SYNTHETIC PRIOR NAME"}).model_dump(mode="json"))
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        before = db.execute(text("SELECT snapshot_encrypted FROM patient_snapshot_versions")).scalar_one()
    sources = ["MRN: IDENTITY-001\nPatient Name: SYNTHETIC FIRST", "MRN: IDENTITY-001\nPatient Name: SYNTHETIC SECOND"]
    if reverse:
        sources.reverse()
    # When: an otherwise valid binder imports conflicting optional metadata.
    imported = runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
        files=[("file", ("synthetic.txt", raw, "text/plain")) for raw in sources])
    # Then: warnings are value-free and no arbitrary name wins or replaces the prior snapshot.
    assert imported.status_code == 201
    assert "patient_full_name" in " ".join(imported.json()["warnings"])
    assert "SYNTHETIC FIRST" not in imported.text and "SYNTHETIC SECOND" not in imported.text
    with SessionLocal() as db:
        assert db.execute(text("SELECT snapshot_encrypted FROM patient_snapshot_versions")).scalar_one() == before
    assert runtime.client.get("/api/v2/patient-roster", headers=runtime.headers).json()["items"][0]["full_name"] == "SYNTHETIC PRIOR NAME"


def test_plan_local_metadata_survives_all_roster_boundaries(runtime: IdentityRuntime) -> None:
    # Given: a manual source with optional name/reference/service metadata but no clinical dates.
    imported = runtime.client.post("/api/v2/manual-uploads/treatment-plan-file", headers=runtime.headers,
        files={"file": ("synthetic.txt", "MRN: IDENTITY-001\nPatient Name: SYNTHETIC METADATA\nService Date: 2026-08-09\nOriginal Plan Reference: REF-SYNTHETIC", "text/plain")})
    assert imported.status_code == 201
    saved = imported.json()
    # When: latest queue, plan roster, and nested patient plan summaries are loaded.
    rows = [runtime.client.get(f"/api/v2/{route}", headers=runtime.headers).json()["items"][0]
            for route in ("treatment-plans", "treatment-plan-roster")]
    rows.append(runtime.client.get("/api/v2/patient-roster", headers=runtime.headers).json()["items"][0]["treatment_plans"][0])
    # Then: exact positive identities and metadata agree without substituting service date for clinical dates.
    for row in rows:
        assert row["plan_version_id"] == saved["plan_version_id"] > 0
        assert row["patient_record_id"] == saved["patient_record_id"] > 0
        assert row["version_ordinal"] == 1
        assert row["service_date"] == "2026-08-09" and row["original_plan_reference"] == "REF-SYNTHETIC"
    detail = runtime.client.get("/api/v2/treatment-plans/IDENTITY-001", headers=runtime.headers,
        params={key: saved[key] for key in ("plan_version_id", "patient_record_id", "source_mode")}).json()
    assert detail["admission_date"] == detail["date_clock_anchor"] == "Unknown"


def test_fresh_v12_and_exact_no_snapshot_patient_settle_successfully(runtime: IdentityRuntime, tmp_path: Path) -> None:
    # Given: a fresh v12 database and an authorized patient row with no snapshot or plan.
    from app.core.config import settings
    from app.v2.db import SessionLocal
    from app.v2.migrations.runner import MigrationRequest, run_migrations
    with SessionLocal() as db:
        assert db.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar_one() == 12
        record_id = db.execute(text("INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "SELECT id,'EMPTY-SYNTHETIC','manual_upload','active','2026-09-04','2026-09-04' FROM facilities WHERE facility_key='r3-default'")).lastrowid
        db.commit()
    # When: exact detail is loaded and current-schema startup verification is repeated.
    response = runtime.client.get("/api/v2/patients/EMPTY-SYNTHETIC", headers=runtime.headers,
                                  params={"patient_record_id": record_id, "source_mode": "manual_upload"})
    path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    request = MigrationRequest(path, path.parent, settings.effective_data_encryption_secret, "synthetic-repeat")
    assert run_migrations(request).applied_versions == ()
    before = path.read_bytes()
    assert run_migrations(request).applied_versions == ()
    # Then: empty is a successful settled representation and repeat verification changes no bytes.
    assert response.status_code == 200
    assert response.json()["full_name"] == "" and response.json()["patient_record"] == {} and response.json()["treatment_plans"] == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("role", ["anonymous", "counselor"])
def test_filtered_export_requires_manager_before_clinical_access(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    # Given: a valid exact plan selection without a manager session.
    selected = _import(runtime)
    headers = {} if role == "anonymous" else _user(runtime, role)[1]
    def reject_read(*_args, **_kwargs):
        raise AssertionError("Export role denial reached clinical access")
    monkeypatch.setattr("app.v2.api.plan_export_routes.list_treatment_plan_queue_items", reject_read)
    # When: the POST route is called without the required role.
    response = runtime.client.post("/api/v2/exports/treatment-plans.csv", headers=headers,
                                   json={"plan_version_ids": [selected["plan_version_id"]]})
    # Then: authentication/role denial precedes clinical data access.
    assert response.status_code == (401 if role == "anonymous" else 403)


def test_standalone_legacy_reviews_never_merge_into_selected_plan(runtime: IdentityRuntime) -> None:
    # Given: one embedded plan-local review and a same-MRN legacy review with no plan FK.
    embedded = {"id": "embedded-review", "review_date": "2026-08-03", "content": "Synthetic embedded review"}
    saved = runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
        json=_aggregate("IDENTITY-001").model_copy(update={"treatment_reviews": (embedded,)}).model_dump(mode="json")).json()
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("INSERT INTO treatment_review_versions(patient_id,source_system,source_record_id,version_ordinal,"
            "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) "
            "VALUES(:patient,'manual_upload','standalone-legacy',99,:cipher,'standalone-hash','standalone-evidence','2026-09-04')"),
            {"patient": saved["patient_record_id"], "cipher": b"must-not-decode-unlinked-legacy-review"})
        db.commit()
        before = tuple(db.execute(text("SELECT * FROM treatment_review_versions ORDER BY id")).all())
    # When: the exact selected plan is assembled.
    detail = runtime.client.get("/api/v2/treatment-plans/IDENTITY-001", headers=runtime.headers,
        params={key: saved[key] for key in ("plan_version_id", "patient_record_id", "source_mode")})
    # Then: only embedded plan-local reviews appear; the standalone history is neither decoded nor rewritten.
    assert detail.status_code == 200 and detail.json()["treatment_reviews"] == [embedded]
    with SessionLocal() as db:
        assert tuple(db.execute(text("SELECT * FROM treatment_review_versions ORDER BY id")).all()) == before
