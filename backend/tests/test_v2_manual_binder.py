from __future__ import annotations

import sqlite3
from contextlib import closing
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy.exc import SQLAlchemyError

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def _binder_files(order: tuple[str, str]) -> list[tuple[str, tuple[str, bytes, str]]]:
    documents = {
        "identity": (
            "first-source.txt",
            b"MRN: 940\nCurrent Level of Care: PHP\nAdmission Date: 2026-06-02",
            "text/plain",
        ),
        "content": (
            "second-source.txt",
            b"MRN: 940\nIntervention: Synthetic binder skills practice.",
            "text/plain",
        ),
    }
    return [("file", documents[key]) for key in order]


def _docx(lines: tuple[str, ...]) -> bytes:
    output = BytesIO()
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in lines)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def _opaque_zip() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../../must-not-extract.txt", "synthetic opaque content")
    return output.getvalue()


def test_manual_binder_is_order_independent_and_archives_every_source(tmp_path: Path, monkeypatch) -> None:
    # Given: two app instances and the same synthetic binder in opposite order.
    observed: list[tuple[str, str]] = []
    for label, order in (("forward", ("identity", "content")), ("reverse", ("content", "identity"))):
        client = _fresh_client(tmp_path / label, monkeypatch)
        headers = _auth_headers(client)

        # When: both multipart parts use the backward-compatible `file` field.
        imported = client.post(
            "/api/v2/manual-uploads/treatment-plan-file",
            data={"patient_id": "", "confirm_patient_id_correction": "false"},
            files=_binder_files(order),
            headers=headers,
        )

        # Then: one aggregate references two encrypted generated sources.
        assert imported.status_code == 201
        assert imported.json()["source_file_ids"] and len(imported.json()["source_file_ids"]) == 2
        detail = client.get("/api/v2/treatment-plans/940", headers=headers)
        assert detail.status_code == 200
        assert len(detail.json()["source_documents"]) == 2
        snapshot = detail.json()["content_snapshot"]
        intervention = snapshot["problems"][0]["goals"][0]["objectives"][0]["interventions"][0]
        assert intervention["intervention_description"] == "Synthetic binder skills practice."
        observed.append((snapshot["plan_id"], snapshot["content_hash"]))
        stored = tuple((tmp_path / label / "app-data" / "manual-uploads").glob("*.izcna1"))
        assert len(stored) == 2
        assert all(path.read_bytes().startswith(b"IZCNA1:") for path in stored)
        assert all("first-source" not in path.name and "second-source" not in path.name for path in stored)
        client.close()
    assert observed[0] == observed[1]


def test_manual_binder_conflicts_require_id_confirmation_and_never_choose_a_date_by_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: two synthetic sources with conflicting IDs and clinical dates.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    files = [
        ("file", ("source-a.txt", b"Patient ID: 941\nAdmission Date: 2026-06-02", "text/plain")),
        ("file", ("source-b.txt", b"Patient ID: 942\nAdmission Date: 2026-06-03", "text/plain")),
    ]

    # When: an override is first submitted without, then with, explicit confirmation.
    rejected = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "943", "confirm_patient_id_correction": "false"},
        files=files,
        headers=headers,
    )
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "943", "confirm_patient_id_correction": "true"},
        files=files,
        headers=headers,
    )

    # Then: the ID correction is gated and the date is explicit conflicting evidence.
    assert rejected.status_code == 409
    assert imported.status_code == 201
    assert imported.json()["overall_status"] == "Conflicting Evidence"
    detail = client.get("/api/v2/treatment-plans/943", headers=headers).json()
    queue = client.get("/api/v2/treatment-plans", headers=headers).json()["items"]
    queue_item = next(item for item in queue if item["patient_id"] == "943")
    assert detail["admission_date"] == "Unknown"
    assert detail["overall_status"] == "Conflicting Evidence"
    assert queue_item["status"] == "Conflicting Evidence"
    assert any("Conflicting scalar evidence" in warning for warning in detail["data_quality_warnings"])


def test_manual_binder_supports_docx_rtf_and_keeps_zip_opaque(tmp_path: Path, monkeypatch) -> None:
    # Given: extractable DOCX/RTF evidence plus a ZIP containing a traversal name.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    files = [
        ("file", ("source.docx", _docx(("Patient ID: 944", "Current Level of Care: IOP")), "application/octet-stream")),
        ("file", ("source.rtf", b"{\\rtf1 Admission Date: 2026-06-04\\par Intervention: Synthetic RTF practice.}", "application/rtf")),
        ("file", ("opaque.zip", _opaque_zip(), "application/zip")),
    ]

    # When: the mixed binder is imported.
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "", "confirm_patient_id_correction": "false"},
        files=files,
        headers=headers,
    )

    # Then: extractable evidence is used, ZIP is archived with a safe warning, and never extracted.
    assert imported.status_code == 201
    assert imported.json()["status"] == "imported_with_warnings"
    assert imported.json()["opaque_file_count"] == 1
    detail = client.get("/api/v2/treatment-plans/944", headers=headers).json()
    assert detail["current_level_of_care"] == "IOP"
    assert len(detail["source_documents"]) == 3
    assert any("opaque" in warning.lower() for warning in detail["data_quality_warnings"])
    assert not (tmp_path / "must-not-extract.txt").exists()


def test_opaque_only_binder_is_explicitly_unable_to_evaluate(tmp_path: Path, monkeypatch) -> None:
    # Given: a patient override and only an opaque legacy document.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    # When: the binder is imported.
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "945", "confirm_patient_id_correction": "false"},
        files=[("file", ("opaque.doc", b"synthetic legacy bytes", "application/msword"))],
        headers=headers,
    )

    # Then: storage succeeds without claiming that clinical evidence was parsed.
    assert imported.status_code == 201
    assert imported.json()["status"] == "imported_with_warnings"
    assert imported.json()["overall_status"] == "Unable to Evaluate"
    detail = client.get("/api/v2/treatment-plans/945", headers=headers).json()
    queue = client.get("/api/v2/treatment-plans", headers=headers).json()["items"]
    queue_item = next(item for item in queue if item["patient_id"] == "945")
    assert len(detail["source_documents"]) == 1
    assert detail["overall_status"] == "Unable to Evaluate"
    assert queue_item["status"] == "Unable to Evaluate"


def test_manual_binder_rolls_back_plan_and_files_when_source_metadata_insert_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: a real database trigger that fails source-document persistence.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            "CREATE TRIGGER synthetic_source_failure BEFORE INSERT ON source_documents "
            "BEGIN SELECT RAISE(ABORT, 'synthetic source failure'); END"
        )

    # When: aggregate and source persistence are attempted.
    with pytest.raises(SQLAlchemyError):
        client.post(
            "/api/v2/manual-uploads/treatment-plan-file",
            data={"patient_id": "946", "confirm_patient_id_correction": "false"},
            files=[("file", ("source.txt", b"Patient ID: 946\nAdmission Date: 2026-06-05", "text/plain"))],
            headers=headers,
        )

    # Then: neither database records nor encrypted source residue remain.
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_versions").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM source_documents").fetchone() == (0,)
    upload_root = tmp_path / "app-data" / "manual-uploads"
    assert not upload_root.exists() or not tuple(upload_root.iterdir())


def test_manual_binder_enforces_file_count_before_writing(tmp_path: Path, monkeypatch) -> None:
    # Given: one more source than the bounded V1-grade binder count.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    files = [
        ("file", (f"source-{index}.txt", b"Patient ID: 947", "text/plain"))
        for index in range(41)
    ]

    # When: the oversized binder is submitted.
    response = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "947", "confirm_patient_id_correction": "false"},
        files=files,
        headers=headers,
    )

    # Then: validation rejects it before any encrypted file is written.
    assert response.status_code == 413
    upload_root = tmp_path / "app-data" / "manual-uploads"
    assert not upload_root.exists() or not tuple(upload_root.iterdir())
