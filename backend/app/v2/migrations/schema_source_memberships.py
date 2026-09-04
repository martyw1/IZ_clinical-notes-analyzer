from __future__ import annotations

from typing import Final


SOURCE_MEMBERSHIP_STATEMENTS: Final = (
    """CREATE TABLE source_document_plan_memberships(
        source_document_id INTEGER NOT NULL REFERENCES source_documents(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        plan_version_id INTEGER NOT NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        attached_at TEXT NOT NULL,
        attached_by_user_id INTEGER NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        detached_at TEXT NULL,
        detached_by_user_id INTEGER NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        PRIMARY KEY(source_document_id,plan_version_id),
        CHECK((detached_at IS NULL) = (detached_by_user_id IS NULL))
    )""",
    "CREATE INDEX ix_source_membership_plan_active ON source_document_plan_memberships(plan_version_id,detached_at)",
    """CREATE TRIGGER source_membership_validate_insert BEFORE INSERT ON source_document_plan_memberships
        WHEN NOT EXISTS (
            SELECT 1 FROM source_documents d JOIN treatment_plan_versions v ON v.id=NEW.plan_version_id
            JOIN patients p ON p.id=d.patient_id
            WHERE d.id=NEW.source_document_id AND d.patient_id=v.patient_id
            AND d.source_kind='manual_treatment_plan_file' AND v.source_system='manual_upload'
            AND p.source_system='manual_upload'
        ) BEGIN SELECT RAISE(ABORT,'source membership requires an exact manual patient version'); END""",
    """CREATE TRIGGER source_membership_validate_update BEFORE UPDATE ON source_document_plan_memberships
        WHEN NEW.source_document_id IS NOT OLD.source_document_id OR NEW.plan_version_id IS NOT OLD.plan_version_id
        OR NEW.attached_at IS NOT OLD.attached_at OR NEW.attached_by_user_id IS NOT OLD.attached_by_user_id
        OR NOT EXISTS (
            SELECT 1 FROM source_documents d JOIN treatment_plan_versions v ON v.id=NEW.plan_version_id
            JOIN patients p ON p.id=d.patient_id
            WHERE d.id=NEW.source_document_id AND d.patient_id=v.patient_id
            AND d.source_kind='manual_treatment_plan_file' AND v.source_system='manual_upload'
            AND p.source_system='manual_upload'
        ) BEGIN SELECT RAISE(ABORT,'source membership provenance is immutable'); END""",
    """CREATE TRIGGER source_document_membership_provenance BEFORE UPDATE ON source_documents
        WHEN EXISTS (SELECT 1 FROM source_document_plan_memberships m WHERE m.source_document_id=OLD.id)
        AND (NEW.id IS NOT OLD.id OR NEW.patient_id IS NOT OLD.patient_id
        OR NEW.plan_version_id IS NOT OLD.plan_version_id OR NEW.review_version_id IS NOT OLD.review_version_id
        OR NEW.document_id IS NOT OLD.document_id OR NEW.source_kind IS NOT OLD.source_kind
        OR NEW.sha256 IS NOT OLD.sha256 OR NEW.encrypted_relative_path IS NOT OLD.encrypted_relative_path
        OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by_user_id IS NOT OLD.created_by_user_id)
        BEGIN SELECT RAISE(ABORT,'linked source provenance is immutable'); END""",
    """INSERT INTO source_document_plan_memberships(source_document_id,plan_version_id,attached_at,attached_by_user_id)
        SELECT d.id,d.plan_version_id,d.created_at,d.created_by_user_id
        FROM source_documents d JOIN treatment_plan_versions v ON v.id=d.plan_version_id
        JOIN patients p ON p.id=d.patient_id
        WHERE d.patient_id=v.patient_id AND d.source_kind='manual_treatment_plan_file'
        AND v.source_system='manual_upload' AND p.source_system='manual_upload'""",
)
