from __future__ import annotations

from sqlalchemy import text

from test_v2_evaluation_persistence import _aggregate
from test_v2_manual_patient_correction import _fresh_client
from test_v2_sync_contract_runtime import _contract


def test_full_reconciliation_preserves_unlinked_placeholders_and_all_plans(tmp_path, monkeypatch) -> None:
    # Given: current and historically misclassified unlinked placeholders plus a genuine Alleva patient.
    _fresh_client(tmp_path, monkeypatch)
    from app.v2.db import SessionLocal
    from app.v2.domain.schemas import TreatmentPlanAggregate
    from app.v2.models import User
    from app.v2.services.alleva_patient_identity import reconcile_sync_patients
    from app.v2.services.patient_roster import list_patient_roster, list_treatment_plan_roster
    from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

    with SessionLocal() as db:
        actor = db.get(User, 1)
        assert actor is not None
        for patient_key, plan_id, source_mode, source_patient_id, lifecycle_state in (
            ("unlinked-plan-current", "plan-current", "alleva_rest_api", None, "unlinked"),
            ("unlinked-plan-historical", "plan-historical", "alleva_rest_api", None, "unlinked"),
            ("unlinked-plan-real-mrn", "plan-real-mrn", "alleva_rest_api", "source-real", "active"),
            ("unlinked-plan-manual", "plan-manual", "manual_upload", None, "active"),
        ):
            payload = _aggregate(patient_key).model_dump(mode="json")
            payload.update({
                "source_mode": source_mode,
                "patient_display_label": (
                    "Not linked to an MRN" if lifecycle_state == "unlinked" else f"MRN {patient_key}"
                ),
            })
            payload["content_snapshot"].update({
                "plan_id": plan_id,
                "source_mode": source_mode,
            })
            save_treatment_plan_aggregate(
                db,
                TreatmentPlanAggregate.model_validate(payload),
                actor,
                source_patient_id=source_patient_id,
                lifecycle_state=lifecycle_state,
            )
        facility_id = int(db.execute(text(
            "SELECT id FROM facilities WHERE facility_key='r3-default'"
        )).scalar_one())
        db.execute(text(
            "UPDATE patients SET lifecycle_state='missing' "
            "WHERE canonical_client_id='unlinked-plan-historical'"
        ))
        db.execute(
            text(
                "INSERT INTO patients(facility_id,canonical_client_id,source_patient_id,source_system,"
                "lifecycle_state,first_seen_at,last_seen_at) "
                "VALUES(:facility_id,'MRN-GENUINE','source-genuine','alleva_rest_api','active',"
                "'2026-09-01','2026-09-01')"
            ),
            {"facility_id": facility_id},
        )
        db.commit()
        plan_count_before = int(db.execute(text("SELECT COUNT(*) FROM treatment_plan_versions")).scalar_one())

        # When: a later complete client snapshot does not contain any of those identities.
        reconcile_sync_patients(db, None, (), frozenset(), True, "2026-09-21T00:00:00+00:00")

        # Then: placeholders stay out of the patient roster, genuine missing MRNs remain, and plans are untouched.
        lifecycles = dict(db.execute(text(
            "SELECT canonical_client_id,lifecycle_state FROM patients WHERE source_system='alleva_rest_api'"
        )).all())
        patient_roster = list_patient_roster(db)
        plan_roster = list_treatment_plan_roster(db)
        plan_count_after = int(db.execute(text("SELECT COUNT(*) FROM treatment_plan_versions")).scalar_one())

    assert lifecycles == {
        "MRN-GENUINE": "missing",
        "unlinked-plan-current": "unlinked",
        "unlinked-plan-historical": "missing",
        "unlinked-plan-real-mrn": "missing",
    }
    assert {(item.mrn, item.source_mode, item.lifecycle_state) for item in patient_roster} == {
        ("MRN-GENUINE", "alleva_rest_api", "missing"),
        ("unlinked-plan-real-mrn", "alleva_rest_api", "missing"),
        ("unlinked-plan-manual", "manual_upload", "active"),
    }
    plans = {item.treatment_plan_id: item for item in plan_roster}
    assert set(plans) == {"plan-current", "plan-historical", "plan-real-mrn", "plan-manual"}
    assert all(not plans[plan_id].linked_to_mrn and plans[plan_id].mrn == "" for plan_id in ("plan-current", "plan-historical"))
    assert plans["plan-real-mrn"].linked_to_mrn and plans["plan-real-mrn"].mrn == "unlinked-plan-real-mrn"
    assert plans["plan-manual"].linked_to_mrn and plans["plan-manual"].mrn == "unlinked-plan-manual"
    assert plan_count_before == plan_count_after == 4


def test_plan_import_preserves_observed_inactive_client_lifecycle(tmp_path, monkeypatch) -> None:
    # Given: reconciliation observed an inactive client that has one linked treatment plan.
    _fresh_client(tmp_path, monkeypatch)
    import httpx

    from app.v2.db import SessionLocal
    from app.v2.models import User
    from app.v2.services import alleva_sync
    from app.v2.services.alleva_patient_identity import AllevaPatientObservation, reconcile_sync_patients

    contract = _contract()
    client_payload = {
        "member_id": "source-inactive",
        "mrn": "MRN-INACTIVE",
        "status": "inactive",
    }
    plan_payload = {"owner_id": "source-inactive", "plan_key": "plan-inactive"}
    monkeypatch.setattr(alleva_sync, "_plan_detail", lambda *_args, **_kwargs: plan_payload)

    # When: the linked plan is saved after the source lifecycle reconciliation.
    with SessionLocal() as db, httpx.Client() as http_client:
        actor = db.get(User, 1)
        assert actor is not None
        reconcile_sync_patients(
            db,
            None,
            (AllevaPatientObservation("source-inactive", "MRN-INACTIVE", "inactive"),),
            frozenset({"source-inactive"}),
            True,
            "2026-09-21T00:00:00+00:00",
        )
        alleva_sync._save_client_aggregates(
            db,
            http_client,
            type("Profile", (), {"api_base_url": "https://synthetic.invalid", "alleva_api_version": "1.0"})(),
            actor,
            contract,
            (client_payload,),
            (plan_payload,),
            {},
            lambda: False,
            None,
            alleva_sync.ApprovedRequestRateLimiter(10_000),
        )
        lifecycle = db.execute(text(
            "SELECT lifecycle_state FROM patients WHERE canonical_client_id='MRN-INACTIVE'"
        )).scalar_one()
        plan_count = int(db.execute(text("SELECT COUNT(*) FROM treatment_plan_versions")).scalar_one())

    # Then: saving the plan cannot overwrite the authoritative inactive lifecycle.
    assert lifecycle == "inactive"
    assert plan_count == 1
