from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class AllevaPatientObservation:
    source_patient_id: str
    mrn: str
    lifecycle_state: str


@dataclass(frozen=True, slots=True)
class _PatientRow:
    id: int
    mrn: str
    source_patient_id: str | None


def reconcile_sync_patients(
    db: Session,
    external_job_id: str | None,
    observations: tuple[AllevaPatientObservation, ...],
    observed_source_patient_ids: frozenset[str],
    completed_snapshot: bool,
    reconciled_at: str,
) -> None:
    facility_id = int(db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one())
    existing_rows = tuple(
        _PatientRow(int(row[0]), str(row[1]), str(row[2]) if row[2] is not None else None)
        for row in db.execute(
            text(
                "SELECT id,canonical_client_id,source_patient_id FROM patients "
                "WHERE facility_id=:facility_id AND source_system='alleva_rest_api'"
            ),
            {"facility_id": facility_id},
        ).all()
    )
    actions = _preflight_identity_actions(existing_rows, observations)
    for observation, patient_row in actions:
        patient_id = _upsert_observation(db, facility_id, observation, patient_row, reconciled_at)
        if external_job_id is not None:
            _insert_reconciliation_outcome(
                db,
                external_job_id,
                patient_id,
                observation.source_patient_id,
                observation.lifecycle_state,
                reconciled_at,
            )
    if completed_snapshot:
        _mark_missing_patients(
            db,
            facility_id,
            external_job_id,
            observed_source_patient_ids,
            reconciled_at,
        )
    db.commit()


def _preflight_identity_actions(
    existing_rows: tuple[_PatientRow, ...],
    observations: tuple[AllevaPatientObservation, ...],
) -> tuple[tuple[AllevaPatientObservation, _PatientRow | None], ...]:
    source_to_mrn: dict[str, str] = {}
    mrn_to_source: dict[str, str] = {}
    for observation in observations:
        if not observation.source_patient_id or not observation.mrn:
            raise ValueError("Alleva patient identity requires both a source patient ID and MRN.")
        if source_to_mrn.get(observation.source_patient_id, observation.mrn) != observation.mrn:
            raise ValueError("Alleva patient identity conflict detected before reconciliation.")
        if mrn_to_source.get(observation.mrn, observation.source_patient_id) != observation.source_patient_id:
            raise ValueError("Alleva patient identity conflict detected before reconciliation.")
        source_to_mrn[observation.source_patient_id] = observation.mrn
        mrn_to_source[observation.mrn] = observation.source_patient_id

    by_mrn = {row.mrn: row for row in existing_rows}
    by_source = {row.source_patient_id: row for row in existing_rows if row.source_patient_id is not None}
    actions: list[tuple[AllevaPatientObservation, _PatientRow | None]] = []
    processed_pairs: set[tuple[str, str]] = set()
    for observation in observations:
        identity_pair = (observation.source_patient_id, observation.mrn)
        if identity_pair in processed_pairs:
            continue
        processed_pairs.add(identity_pair)
        source_row = by_source.get(observation.source_patient_id)
        mrn_row = by_mrn.get(observation.mrn)
        legacy_row = by_mrn.get(observation.source_patient_id)
        if legacy_row is not None and legacy_row.source_patient_id is not None:
            legacy_row = None
        candidates = {row.id: row for row in (source_row, mrn_row, legacy_row) if row is not None}
        if len(candidates) > 1:
            raise ValueError("Alleva patient identity conflict detected before reconciliation.")
        patient_row = next(iter(candidates.values()), None)
        if patient_row is not None:
            if patient_row.source_patient_id not in {None, observation.source_patient_id}:
                raise ValueError("Alleva source patient ID is already assigned to a different MRN.")
            if source_row is not None and source_row.mrn != observation.mrn:
                raise ValueError("Alleva source patient ID is already assigned to a different MRN.")
            by_mrn.pop(patient_row.mrn, None)
            if patient_row.source_patient_id is not None:
                by_source.pop(patient_row.source_patient_id, None)
        projected = _PatientRow(
            patient_row.id if patient_row is not None else -(len(actions) + 1),
            observation.mrn,
            observation.source_patient_id,
        )
        if observation.mrn in by_mrn or observation.source_patient_id in by_source:
            raise ValueError("Alleva patient identity conflict detected before reconciliation.")
        by_mrn[observation.mrn] = projected
        by_source[observation.source_patient_id] = projected
        actions.append((observation, patient_row))
    return tuple(actions)


def _upsert_observation(
    db: Session,
    facility_id: int,
    observation: AllevaPatientObservation,
    patient_row: _PatientRow | None,
    reconciled_at: str,
) -> int:
    if patient_row is None:
        result = db.execute(
            text(
                "INSERT INTO patients(facility_id,canonical_client_id,source_patient_id,source_system,"
                "lifecycle_state,first_seen_at,last_seen_at,reconciled_at) "
                "VALUES(:facility_id,:mrn,:source_patient_id,'alleva_rest_api',:lifecycle_state,"
                ":reconciled_at,:reconciled_at,:reconciled_at)"
            ),
            {
                "facility_id": facility_id,
                "mrn": observation.mrn,
                "source_patient_id": observation.source_patient_id,
                "lifecycle_state": observation.lifecycle_state,
                "reconciled_at": reconciled_at,
            },
        )
        return int(result.lastrowid)
    db.execute(
        text(
            "UPDATE patients SET canonical_client_id=:mrn,source_patient_id=:source_patient_id,"
            "lifecycle_state=:lifecycle_state,last_seen_at=:reconciled_at,reconciled_at=:reconciled_at "
            "WHERE id=:patient_id"
        ),
        {
            "patient_id": patient_row.id,
            "mrn": observation.mrn,
            "source_patient_id": observation.source_patient_id,
            "lifecycle_state": observation.lifecycle_state,
            "reconciled_at": reconciled_at,
        },
    )
    return patient_row.id


def _mark_missing_patients(
    db: Session,
    facility_id: int,
    external_job_id: str | None,
    observed_source_patient_ids: frozenset[str],
    reconciled_at: str,
) -> None:
    rows = db.execute(
        text(
            "SELECT id,canonical_client_id,source_patient_id FROM patients "
            "WHERE facility_id=:facility_id AND source_system='alleva_rest_api'"
        ),
        {"facility_id": facility_id},
    ).all()
    for row in rows:
        source_patient_id = str(row[2] or row[1])
        if source_patient_id in observed_source_patient_ids:
            continue
        db.execute(
            text("UPDATE patients SET lifecycle_state='missing',reconciled_at=:reconciled_at WHERE id=:patient_id"),
            {"patient_id": int(row[0]), "reconciled_at": reconciled_at},
        )
        if external_job_id is not None:
            _insert_reconciliation_outcome(
                db,
                external_job_id,
                int(row[0]),
                source_patient_id,
                "missing",
                reconciled_at,
            )


def _insert_reconciliation_outcome(
    db: Session,
    external_job_id: str,
    patient_id: int,
    source_patient_id: str,
    outcome: str,
    created_at: str,
) -> None:
    evidence_sha256 = hashlib.sha256(
        f"{external_job_id}:{source_patient_id}:{outcome}".encode("utf-8")
    ).hexdigest()
    db.execute(
        text(
            "INSERT OR IGNORE INTO reconciliation_outcomes("
            "job_id,patient_id,source_kind,source_record_id,outcome,evidence_sha256,created_at"
            ") SELECT id,:patient_id,'alleva_client',:source_record_id,:outcome,:evidence_sha256,:created_at "
            "FROM sync_jobs WHERE external_job_id=:job_id"
        ),
        {
            "job_id": external_job_id,
            "patient_id": patient_id,
            "source_record_id": source_patient_id,
            "outcome": outcome,
            "evidence_sha256": evidence_sha256,
            "created_at": created_at,
        },
    )
