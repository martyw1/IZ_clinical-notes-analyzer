from __future__ import annotations

import sqlite3
from contextlib import closing

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_manual_upload_surface_appends_plan_versions_without_legacy_mutation(tmp_path, monkeypatch) -> None:
    # Given: a fresh real application surface and two synthetic revisions for one patient.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    base = "\n".join(("Patient ID: 730", "Current Level of Care: PHP", "Admission Date: 2026-06-02"))

    # When: two distinct treatment-plan files are imported through the protected HTTP route.
    for revision in ("Synthetic intervention revision one.", "Synthetic intervention revision two."):
        response = client.post(
            "/api/v2/manual-uploads/treatment-plan-file",
            data={"patient_id": "730", "confirm_patient_id_correction": "false"},
            files={"file": ("synthetic.txt", f"{base}\nIntervention: {revision}", "text/plain")},
            headers=headers,
        )
        assert response.status_code == 201
    duplicate = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": "730", "confirm_patient_id_correction": "false"},
        files={"file": ("synthetic.txt", f"{base}\nIntervention: Synthetic intervention revision two.", "text/plain")},
        headers=headers,
    )
    assert duplicate.status_code == 201
    detail = client.get("/api/v2/treatment-plans/730", headers=headers)
    client.close()

    # Then: both immutable versions and source documents exist while legacy mutable tables remain empty.
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_versions").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM source_documents").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_imports").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM uploaded_documents").fetchone() == (0,)
    assert detail.status_code == 200
    assert detail.json()["patient_id"] == "730"
