from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Literal

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text

from test_v2_evaluation_persistence import _aggregate
from test_v2_plan_version_actions import IdentityRuntime, _import, runtime

SnapshotCase = Literal["missing", "blank", "different"]
AUTHORITATIVE_PLAN_ID = "stored-authoritative-plan"


def _stored_snapshot_case(runtime: IdentityRuntime, case: SnapshotCase) -> tuple[dict[str, int | str], bytes]:
    from app.core.config import settings
    from app.v2.db import SessionLocal
    from app.v2.services.clinical_snapshot_codec import ClinicalSnapshotCodec

    seed = _import(runtime, plan_id="snapshot-seed")
    codec = ClinicalSnapshotCodec(settings.effective_data_encryption_secret)
    if case == "missing":
        cipher = codec.encode_plan({"reason_for_admission": "Synthetic stored legacy record without a plan identifier"})
    else:
        from app.v2.domain.schemas import TreatmentPlanAggregate
        aggregate = _aggregate("IDENTITY-001")
        snapshot = aggregate.content_snapshot.model_copy(update={"plan_id": "" if case == "blank" else "clinical-snapshot-plan"})
        current_aggregate = TreatmentPlanAggregate.model_validate(
            aggregate.model_copy(update={"content_snapshot": snapshot}).model_dump(mode="json"))
        cipher = codec.encode_aggregate(current_aggregate)
    with SessionLocal() as db:
        version_id = db.execute(text(
            "INSERT INTO treatment_plan_versions(patient_id,source_system,source_record_id,version_ordinal,"
            "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) "
            "SELECT patient_id,source_system,:plan,2,:cipher,:hash,:hash,imported_at "
            "FROM treatment_plan_versions WHERE id=:seed"
        ), {"plan": AUTHORITATIVE_PLAN_ID, "cipher": cipher, "hash": hashlib.sha256(cipher).hexdigest(),
            "seed": seed["plan_version_id"]}).lastrowid
        assert version_id is not None
        db.commit()
    return {"plan_version_id": int(version_id), "patient_record_id": seed["patient_record_id"],
            "source_mode": "manual_upload"}, cipher


@pytest.mark.parametrize("case", ["missing", "blank", "different"])
@pytest.mark.parametrize("external_id_path", [False, True])
def test_detail_http_envelope_uses_resolved_database_plan_id(
    runtime: IdentityRuntime, case: SnapshotCase, external_id_path: bool,
    record_property: Callable[[str, object], None],
) -> None:
    # Given: immutable stored identity differs from or is absent in its clinical snapshot.
    selected, before = _stored_snapshot_case(runtime, case)
    path = "/api/v2/treatment-plans/IDENTITY-001"
    if external_id_path:
        path += f"/{AUTHORITATIVE_PLAN_ID}"
    # When: either real detail HTTP route serializes the authorized selected version.
    response = runtime.client.get(path, headers=runtime.headers, params=selected)
    assert response.status_code == 200
    payload = response.json()
    # Then: envelope identity comes from the database without rewriting clinical history.
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        after = db.execute(text("SELECT normalized_snapshot_encrypted FROM treatment_plan_versions WHERE id=:id"),
                           {"id": selected["plan_version_id"]}).scalar_one()
    assert after == before
    record_property("snapshot_before_sha256", hashlib.sha256(before).hexdigest())
    record_property("snapshot_after_sha256", hashlib.sha256(after).hexdigest())
    expected_snapshot = {"missing": AUTHORITATIVE_PLAN_ID, "blank": "", "different": "clinical-snapshot-plan"}[case]
    assert payload["content_snapshot"]["plan_id"] == expected_snapshot
    assert {key: payload[key] for key in selected} == selected
    assert payload.get("treatment_plan_id") == AUTHORITATIVE_PLAN_ID


def test_detail_dto_requires_authoritative_envelope_id() -> None:
    # Given: a clinical aggregate and valid numeric immutable identities.
    from app.v2.api.plan_models import TreatmentPlanDetailOut
    adapter = TypeAdapter(TreatmentPlanDetailOut)
    payload = _aggregate("IDENTITY-001").model_dump(mode="json") | {"plan_version_id": 7, "patient_record_id": 3}
    # When/Then: clinical snapshot content cannot satisfy the required envelope identity.
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)
    parsed = adapter.validate_python(payload | {"treatment_plan_id": AUTHORITATIVE_PLAN_ID})
    assert parsed.treatment_plan_id == AUTHORITATIVE_PLAN_ID


def test_existing_stored_synthetic_source_reads_remain_compatible(runtime: IdentityRuntime) -> None:
    # Given: an existing synthetic-source record is stored through the test fixture, not intake.
    selected = _import(runtime, source="synthetic_fixture")
    # When: list, rosters, exact patient and exact detail read that authorized stored identity.
    for source in (None, "synthetic_fixture"):
        params = {} if source is None else {"source_mode": source}
        for route in ("treatment-plans", "treatment-plan-roster", "patient-roster"):
            response = runtime.client.get(f"/api/v2/{route}", headers=runtime.headers, params=params)
            assert response.status_code == 200
            row = response.json()["items"][0]
            assert row["source_mode"] == "synthetic_fixture"
            if route == "patient-roster":
                row = row["treatment_plans"][0]
            assert {key: row[key] for key in selected} == selected
    detail = runtime.client.get("/api/v2/treatment-plans/IDENTITY-001", headers=runtime.headers, params=selected)
    patient = runtime.client.get("/api/v2/patients/IDENTITY-001", headers=runtime.headers,
                                 params={key: selected[key] for key in ("patient_record_id", "source_mode")})
    assert detail.status_code == patient.status_code == 200
    assert {key: detail.json()[key] for key in selected} == selected
    assert patient.json()["source_mode"] == "synthetic_fixture"
    # Then: stored-source read compatibility grants no new manual intake mode.
    aggregate = _aggregate("NEW-SYNTHETIC-INTAKE")
    rejected = runtime.client.post("/api/v2/manual-uploads/treatment-plan-aggregate", headers=runtime.headers,
        json=aggregate.model_copy(update={"source_mode": "synthetic_fixture"}).model_dump(mode="json"))
    assert rejected.status_code == 400
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        assert db.execute(text("SELECT COUNT(*) FROM treatment_plan_versions")).scalar_one() == 1
