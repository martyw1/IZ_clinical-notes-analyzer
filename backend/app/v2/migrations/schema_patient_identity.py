from __future__ import annotations


PATIENT_IDENTITY_STATEMENTS = (
    "ALTER TABLE patients ADD COLUMN source_patient_id TEXT NULL",
    "CREATE UNIQUE INDEX uq_patients_source_identity "
    "ON patients(facility_id,source_system,source_patient_id) "
    "WHERE source_patient_id IS NOT NULL",
)
