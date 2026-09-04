from __future__ import annotations

import csv
from io import StringIO

import pytest
from sqlalchemy import text

from test_v2_plan_version_actions import IdentityRuntime, _import, runtime
from test_v2_plan_version_authorization import _other_facility_version, _user


def _assert_exact_scope(user_id: int, record_id: int) -> None:
    from app.v2.authorization import accessible_patient_record_ids
    from app.v2.db import SessionLocal
    from app.v2.models import User
    with SessionLocal() as db:
        actor = db.get(User, user_id)
        assert actor is not None
        assert accessible_patient_record_ids(db, actor) == frozenset({record_id})


@pytest.mark.parametrize("source", [None, "manual_upload", "alleva_rest_api"])
def test_rosters_filter_exact_latest_source_identities(runtime: IdentityRuntime, source: str | None) -> None:
    # Given: two versions and a source collision sharing MRN and external plan ID.
    old = _import(runtime)
    current = _import(runtime, marker="newer")
    alleva = _import(runtime, source="alleva_rest_api")
    expected = {item["plan_version_id"] for item in (current, alleva) if source is None or item["source_mode"] == source}
    # When: the current roster is loaded with an optional source scope.
    response = runtime.client.get("/api/v2/treatment-plan-roster", headers=runtime.headers,
                                  params={} if source is None else {"source_mode": source})
    # Then: current exact IDs retain source and row identity without historic duplicates.
    assert response.status_code == 200
    rows = response.json()["items"]
    assert {row["plan_version_id"] for row in rows} == expected
    assert old["plan_version_id"] not in expected
    assert all(row["patient_record_id"] > 0 and row["version_ordinal"] > 0 for row in rows)


def test_history_query_lists_only_selected_record_source_and_external_plan(runtime: IdentityRuntime) -> None:
    # Given: saved history, a sibling plan, and a collision in another source.
    old = _import(runtime)
    current = _import(runtime, marker="newer")
    _import(runtime, plan_id="sibling")
    _import(runtime, source="alleva_rest_api")
    # When: history is explicitly requested for one exact plan lineage.
    response = runtime.client.get("/api/v2/treatment-plans", headers=runtime.headers, params={
        "include_history": "true", "patient_record_id": old["patient_record_id"],
        "source_mode": "manual_upload", "treatment_plan_id": "plan-a",
    })
    # Then: both versions are selectable and only the newest is current.
    assert response.status_code == 200
    assert {row["plan_version_id"]: row["is_current"] for row in response.json()["items"]} == {
        old["plan_version_id"]: False, current["plan_version_id"]: True,
    }


def test_patient_detail_requires_exact_row_when_sources_collide(runtime: IdentityRuntime) -> None:
    # Given: two eligible rows share an MRN.
    _import(runtime)
    _import(runtime, source="alleva_rest_api")
    # When: the caller omits source and exact row identity.
    response = runtime.client.get("/api/v2/patients/IDENTITY-001", headers=runtime.headers)
    # Then: the API does not guess a source row.
    assert response.status_code == 409


def test_exact_patient_detail_denies_other_facility_before_snapshot_read(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a same-MRN forbidden row and a sentinel at the snapshot boundary.
    selected = _import(runtime)
    user_id, headers = _user(runtime, "office_manager")
    forbidden = _other_facility_version(selected["plan_version_id"])
    _assert_exact_scope(user_id, selected["patient_record_id"])
    def reject_snapshot(*_args: int, **_kwargs: str) -> None:
        raise AssertionError("Unauthorized snapshot read")
    monkeypatch.setattr("app.v2.services.patient_record.patient_source_snapshot_for_record", reject_snapshot)
    # When: that exact patient row is requested.
    response = runtime.client.get("/api/v2/patients/IDENTITY-001", headers=headers, params=forbidden)
    # Then: exact-row authorization rejects without reading/decrypting.
    assert response.status_code == 403


def test_patient_roster_does_not_decrypt_or_disclose_forbidden_collision(runtime: IdentityRuntime) -> None:
    # Given: a visible and forbidden row with the same source and MRN.
    selected = _import(runtime)
    user_id, headers = _user(runtime, "office_manager")
    forbidden = _other_facility_version(selected["plan_version_id"])
    _assert_exact_scope(user_id, selected["patient_record_id"])
    from app.v2.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text(
            "INSERT INTO patient_snapshot_versions(patient_id,source_system,source_record_id,version_ordinal,"
            "source_last_updated,snapshot_schema_version,snapshot_encrypted,content_sha256,captured_at) "
            "VALUES(:patient,'manual_upload','IDENTITY-001',1,'',1,:invalid,'invalid','2026-09-04')"
        ), {"patient": forbidden["patient_record_id"], "invalid": b"must-not-decrypt"})
        db.commit()
    # When: an authorized roster is loaded.
    response = runtime.client.get("/api/v2/patient-roster", headers=headers)
    # Then: forbidden encrypted data is not decoded and the collision is absent.
    assert response.status_code == 200
    assert {row["patient_record_id"] for row in response.json()["items"]} == {selected["patient_record_id"]}


def test_filtered_export_includes_all_ids_beyond_one_viewport(runtime: IdentityRuntime) -> None:
    # Given: a bounded synthetic population larger than one visible viewport.
    identities = tuple(_import(runtime, plan_id=f"plan-{index:02}") for index in range(13))
    ids = [identity["plan_version_id"] for identity in identities]
    # When: all filtered-result IDs plus one duplicate are exported.
    response = runtime.client.post("/api/v2/exports/treatment-plans.csv", headers=runtime.headers,
                                   json={"plan_version_ids": ids + ids[:1], "source_mode": "manual_upload"})
    # Then: every selected ID appears once, with ordinal, without source search/name metadata.
    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert [int(row["plan_version_id"]) for row in rows] == ids
    assert all(int(row["version_ordinal"]) > 0 for row in rows)
    assert not {"full_name", "original_plan_reference", "search"} & set(rows[0])


def test_explicit_empty_export_remains_header_only(runtime: IdentityRuntime) -> None:
    # Given: an existing stored plan but an empty client search result.
    _import(runtime)
    # When: the empty explicit result is exported.
    response = runtime.client.post("/api/v2/exports/treatment-plans.csv", headers=runtime.headers,
                                   json={"plan_version_ids": []})
    # Then: it must not expand into an all-record export.
    assert response.status_code == 200
    assert len(response.text.splitlines()) == 1


@pytest.mark.parametrize("invalid", ["denied", "missing", "source"])
def test_filtered_export_rejects_entire_invalid_selection_before_decrypt(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, invalid: str) -> None:
    # Given: one valid ID followed by an inaccessible, absent, or wrong-source selection.
    selected = _import(runtime)
    user_id, headers = _user(runtime, "office_manager")
    forbidden = _other_facility_version(selected["plan_version_id"])
    _assert_exact_scope(user_id, selected["patient_record_id"])
    second = forbidden["plan_version_id"] if invalid == "denied" else 999999
    payload = {"plan_version_ids": [selected["plan_version_id"], second]}
    if invalid == "source":
        payload = {"plan_version_ids": [selected["plan_version_id"]], "source_mode": "alleva_rest_api"}
    def reject_decode(*_args: int, **_kwargs: str) -> None:
        raise AssertionError("Export decoded before all selections passed authorization")
    monkeypatch.setattr("app.v2.services.clinical_snapshot_codec.ClinicalSnapshotCodec.decode_plan", reject_decode)
    # When: the mixed selection is posted.
    response = runtime.client.post("/api/v2/exports/treatment-plans.csv", headers=headers, json=payload)
    # Then: no partial export or decryption takes place.
    assert response.status_code == (403 if invalid == "denied" else 404)
    assert "text/csv" not in response.headers["content-type"]
