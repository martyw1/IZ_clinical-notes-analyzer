from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from test_v2_plan_version_actions import IdentityRuntime, SyntheticAuditFailure, runtime
from test_v2_source_membership_failures import ADDITIONAL, COMMON, _state, _upload


@pytest.mark.parametrize("failure_stage", ["publication", "encryption"])
def test_final_path_collision_never_overwrites_or_cleans_an_existing_archive(runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_stage: str) -> None:
    # Given: a committed archive already owns the next generated final path.
    assert _upload(runtime, (COMMON,)).status_code == 201
    directory = tmp_path / "app-data" / "manual-uploads"
    existing = next(directory.glob("*.izcna1"))
    identifier = UUID(existing.stem)
    before = _state(directory)
    monkeypatch.setattr("app.v2.services.manual_source_batch.uuid4", lambda: identifier)
    attempted_publication = False
    original_replace = Path.replace
    def track_publication(path: Path, target: Path) -> Path:
        nonlocal attempted_publication
        attempted_publication = True
        return original_replace(path, target)
    monkeypatch.setattr(Path, "replace", track_publication)
    if failure_stage == "encryption":
        def fail_encrypt(_raw: bytes) -> bytes:
            raise SyntheticAuditFailure("Synthetic pre-publication encryption failure")
        monkeypatch.setattr("app.v2.services.manual_source_batch.encrypt_bytes", fail_encrypt)
    # When: a second import collides with that final filename.
    with pytest.raises((FileExistsError, IntegrityError, SyntheticAuditFailure)):
        _upload(runtime, (ADDITIONAL,))
    # Then: neither publication nor failure cleanup changes the unowned original archive.
    assert _state(directory) == before
    assert not attempted_publication
