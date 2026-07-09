from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from backend.tests.test_v2_manual_upload import _auth_headers, _fresh_client


def test_manual_text_file_upload_archives_original_source_file_encrypted(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    file_text = "\n".join(
        (
            "Patient ID: 922",
            "Current Level of Care: PHP",
            "Admission Date: 2026-06-02",
            "Next Due Date: 2026-07-02",
            "Reason for Admission: Synthetic source archival rationale.",
            "Intervention: Source archival intervention should not appear in stored ciphertext.",
        )
    )

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={"file": ("source-filename-can-contain-phi.txt", file_text, "text/plain")},
        headers=headers,
    )

    assert imported.status_code == 201
    assert imported.json()["patient_id"] == "922"
    assert imported.json()["source_file_archived"] is True
    source_file_id = imported.json()["source_file_id"]

    from app.core.config import settings
    from app.v2.db import SessionLocal
    from app.v2.models import AuditLog, UploadedDocument
    from app.v2.services.secure_storage import decrypt_bytes

    with SessionLocal() as db:
        stored = db.execute(select(UploadedDocument).where(UploadedDocument.document_id == source_file_id)).scalar_one()
        audit_rows = db.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()

    encrypted_path = settings.local_app_data_dir / stored.storage_path
    encrypted_bytes = encrypted_path.read_bytes()
    assert encrypted_bytes.startswith(b"IZCNA1:")
    assert b"Source archival intervention" not in encrypted_bytes
    assert decrypt_bytes(encrypted_bytes).decode("utf-8") == file_text
    assert stored.patient_id == "922"
    assert stored.source_kind == "manual_treatment_plan_file"
    assert stored.source_format == "text"
    assert stored.size_bytes == len(file_text.encode("utf-8"))
    assert stored.sha256 == hashlib.sha256(file_text.encode("utf-8")).hexdigest()

    archived_audit = next(row for row in audit_rows if row.action == "manual_upload.source_file.archived")
    assert archived_audit.target_entity_id == "922"
    audit_details = json.loads(archived_audit.details_json)
    assert audit_details["source_file_id"] == source_file_id
    assert audit_details["source_format"] == "text"
    assert "source-filename-can-contain-phi" not in archived_audit.details_json
    assert "Source archival intervention" not in archived_audit.details_json


def test_archived_source_file_download_is_role_gated_safe_and_audited(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    file_text = "\n".join(
        (
            "Patient ID: 923",
            "Current Level of Care: PHP",
            "Admission Date: 2026-06-02",
            "Next Due Date: 2026-07-02",
            "Reason for Admission: Synthetic downloadable source rationale.",
            "Intervention: Downloaded source archive round trip.",
        )
    )

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={"file": ("original-name-must-not-return.txt", file_text, "text/plain")},
        headers=headers,
    )

    assert imported.status_code == 201
    source_file_id = imported.json()["source_file_id"]
    detail = client.get("/api/v2/treatment-plans/923", headers=headers)
    assert detail.status_code == 200
    source_documents = detail.json()["source_documents"]
    assert source_documents[0]["source_file_id"] == source_file_id
    assert source_documents[0]["source_format"] == "text"
    assert source_documents[0]["redaction_status"] == "encrypted_original_file"
    assert source_documents[0]["download_url"] == f"/api/v2/treatment-plans/923/source-documents/{source_file_id}/download"

    downloaded = client.get(source_documents[0]["download_url"], headers=headers)

    assert downloaded.status_code == 200
    assert downloaded.content == file_text.encode("utf-8")
    content_disposition = downloaded.headers["content-disposition"]
    assert "manual-treatment-plan-source-" in content_disposition
    assert "original-name-must-not-return" not in content_disposition

    missing = client.get(f"/api/v2/treatment-plans/923/source-documents/not-a-real-id/download", headers=headers)
    assert missing.status_code == 404

    create_counselor = client.post(
        "/api/users",
        json={
            "username": "counselor-download",
            "full_name": "Counselor Download",
            "role": "counselor",
            "password": "StrongCounselorPass1",
        },
        headers=headers,
    )
    assert create_counselor.status_code == 200
    counselor_login = client.post("/api/auth/login", json={"username": "counselor-download", "password": "StrongCounselorPass1"})
    assert counselor_login.status_code == 200
    counselor_headers = {"Authorization": f"Bearer {counselor_login.json()['access_token']}"}
    blocked = client.get(source_documents[0]["download_url"], headers=counselor_headers)
    assert blocked.status_code == 403

    audit = client.get("/api/audit/logs", headers=headers)
    assert audit.status_code == 200
    assert any(
        item["action"] == "manual_upload.source_file.downloaded"
        and item["target_entity_id"] == "923"
        and item["details"]["source_file_id"] == source_file_id
        for item in audit.json()["items"]
    )


def test_archived_source_file_delete_removes_bytes_metadata_and_audits(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    file_text = "\n".join(
        (
            "Patient ID: 924",
            "Current Level of Care: PHP",
            "Admission Date: 2026-06-02",
            "Next Due Date: 2026-07-02",
            "Reason for Admission: Synthetic delete lifecycle rationale.",
            "Intervention: Delete lifecycle source archive round trip.",
        )
    )

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={"file": ("delete-source-name-must-not-audit.txt", file_text, "text/plain")},
        headers=headers,
    )
    assert imported.status_code == 201
    source_file_id = imported.json()["source_file_id"]

    from app.core.config import settings
    from app.v2.db import SessionLocal
    from app.v2.models import UploadedDocument

    with SessionLocal() as db:
        stored = db.execute(select(UploadedDocument).where(UploadedDocument.document_id == source_file_id)).scalar_one()
    encrypted_path = settings.local_app_data_dir / stored.storage_path
    assert encrypted_path.exists()

    deleted = client.delete(f"/api/v2/treatment-plans/924/source-documents/{source_file_id}", headers=headers)

    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "source_file_id": source_file_id, "file_removed": True}
    assert not encrypted_path.exists()
    with SessionLocal() as db:
        assert db.execute(select(UploadedDocument).where(UploadedDocument.document_id == source_file_id)).scalar_one_or_none() is None

    detail = client.get("/api/v2/treatment-plans/924", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["source_documents"] == []

    missing_download = client.get(f"/api/v2/treatment-plans/924/source-documents/{source_file_id}/download", headers=headers)
    assert missing_download.status_code == 404

    audit = client.get("/api/audit/logs", headers=headers)
    assert audit.status_code == 200
    assert any(
        item["action"] == "manual_upload.source_file.deleted"
        and item["target_entity_id"] == "924"
        and item["details"]["source_file_id"] == source_file_id
        and item["details"]["file_removed"] is True
        and "delete-source-name-must-not-audit" not in json.dumps(item["details"])
        for item in audit.json()["items"]
    )


def test_archived_source_file_delete_is_manager_gated(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={"file": ("manager-gated-source.txt", "Patient ID: 925\nIntervention: Manager gated delete.", "text/plain")},
        headers=headers,
    )
    assert imported.status_code == 201
    source_file_id = imported.json()["source_file_id"]

    from app.core.config import settings
    from app.v2.db import SessionLocal
    from app.v2.models import UploadedDocument

    with SessionLocal() as db:
        stored = db.execute(select(UploadedDocument).where(UploadedDocument.document_id == source_file_id)).scalar_one()
    encrypted_path = settings.local_app_data_dir / stored.storage_path

    create_counselor = client.post(
        "/api/users",
        json={
            "username": "counselor-delete",
            "full_name": "Counselor Delete",
            "role": "counselor",
            "password": "StrongCounselorPass1",
        },
        headers=headers,
    )
    assert create_counselor.status_code == 200
    counselor_login = client.post("/api/auth/login", json={"username": "counselor-delete", "password": "StrongCounselorPass1"})
    assert counselor_login.status_code == 200
    counselor_headers = {"Authorization": f"Bearer {counselor_login.json()['access_token']}"}

    blocked = client.delete(f"/api/v2/treatment-plans/925/source-documents/{source_file_id}", headers=counselor_headers)

    assert blocked.status_code == 403
    assert encrypted_path.exists()
    detail = client.get("/api/v2/treatment-plans/925", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["source_documents"][0]["source_file_id"] == source_file_id
