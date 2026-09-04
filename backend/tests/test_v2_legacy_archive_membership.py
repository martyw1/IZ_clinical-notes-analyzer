from __future__ import annotations

import hashlib
from pathlib import Path

from test_v2_plan_version_actions import IdentityRuntime, _import, runtime


def test_legacy_archive_helper_retains_contract_and_valid_v12_state(runtime: IdentityRuntime, tmp_path: Path) -> None:
    # Given: a single unambiguous exact manual plan used by the retained standalone helper.
    _import(runtime)
    from app.v2.db import SessionLocal
    from app.v2.migrations.errors import MigrationStateError
    from app.v2.migrations.schema_verifier import verify_database
    from app.v2.services.manual_source_file_store import ManualSourceFileArchiveInput, archive_manual_source_file, download_manual_source_file
    raw = b"Synthetic standalone archive contract"
    with SessionLocal() as db:
        # When: the existing helper commits its encrypted archive using its unchanged signature.
        saved = archive_manual_source_file(db, ManualSourceFileArchiveInput(
            patient_id="IDENTITY-001", plan_id="plan-a", source_format="txt", content_type="text/plain",
            raw_bytes=raw, created_by_user_id="1"))
        assert download_manual_source_file(db, "IDENTITY-001", saved.document_id).raw_bytes == raw
    root = tmp_path / "app-data"
    archive = root / saved.encrypted_relative_path
    ciphertext = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Then: v12 verification accepts the committed original pair without changing archive bytes.
    try:
        verify_database(root / "clinical-notes-analyzer-v2.sqlite3", 12)
    except MigrationStateError as error:
        raise AssertionError(f"Committed legacy archive violates v12: {error}") from None
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == ciphertext
