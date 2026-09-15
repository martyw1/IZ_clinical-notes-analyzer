from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.desktop_identity import (
    PRODUCT_ID,
    current_user_sid,
    data_identity,
    install_identity_from_key,
    scope_id_from_keys,
    root_path_hash_from_key,
    windows_path_key,
)
from app.desktop_runtime_authority import (
    RuntimeAuthorityError,
    RuntimePaths,
    authorize_runtime,
    validate_candidate_commit,
)
from app.desktop_profile import ENVIRONMENT_NAMES

HEX_A = "a" * 64
HEX_B = "b" * 64
TX = "102030405060708090a0b0c0d0e0f001"
PRIOR_TX = "112030405060708090a0b0c0d0e0f001"


@pytest.fixture(autouse=True)
def clear_profile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


@dataclass(slots=True)
class RuntimeFixture:
    paths: RuntimePaths
    release: dict[str, object]
    journal: dict[str, object]
    receipt: dict[str, object]
    inventory: dict[str, object]

    def write_journal(self) -> None:
        write_json(self.paths.journal_path, self.journal)

    def write_receipt(self) -> None:
        write_json(self.paths.receipt_path, self.receipt)


def make_runtime_fixture(tmp_path: Path) -> RuntimeFixture:
    local = tmp_path / "LocalAppData"
    install = local / "Programs" / "IZ Clinical Notes Analyzer"
    data = local / "IZ Clinical Notes Analyzer"
    maintenance = local / "IZ Clinical Notes Analyzer Maintenance"
    state = maintenance / "state"
    executable = install / "runtime" / "IZClinicalNotesAnalyzer.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"synthetic-runtime")
    (install / "VERSION.json").write_text("{}", encoding="utf-8")
    data.mkdir(parents=True)
    (data / ".env").write_text(
        "IZ_CNA_LOCAL_SQLITE_DB_PATH=profile.sqlite3\nIZ_CNA_DATA_ENCRYPTION_KEY=synthetic-key\n",
        encoding="utf-8",
    )
    connection = sqlite3.connect(data / "profile.sqlite3")
    try:
        connection.execute("CREATE TABLE schema_migrations(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_migrations VALUES (12)")
        connection.commit()
    finally:
        connection.close()
    state.mkdir(parents=True)
    owner = current_user_sid()
    scope = scope_id_from_keys(owner, windows_path_key(install.resolve()), windows_path_key(data.resolve()))
    data_id = data_identity(owner, data, "profile.sqlite3")
    paths = RuntimePaths(
        install_root=install.resolve(),
        data_root=data.resolve(),
        maintenance_root=maintenance.resolve(),
        state_root=state.resolve(),
        journal_path=(state / "maintenance-journal.json").resolve(),
        receipt_path=(state / "install-receipt.json").resolve(),
        identity_path=(state / "runtime-identity.json").resolve(),
        executable_path=executable.resolve(),
    )
    release: dict[str, object] = {
        "version": "2.0.0-beta.4",
        "build": "2026.09.14.1",
        "installer_revision": 1,
        "payload_identity": HEX_A,
    }
    inventory_files = [
        {"path": "VERSION.json", "length": (install / "VERSION.json").stat().st_size, "sha256": sha256(install / "VERSION.json"), "owned": True},
        {"path": "runtime/IZClinicalNotesAnalyzer.exe", "length": executable.stat().st_size, "sha256": sha256(executable), "owned": True},
    ]
    inventory: dict[str, object] = {
        "schema": "iz-cna-program-inventory-v1",
        "product_id": PRODUCT_ID,
        "owner_sid": owner,
        "scope_id": scope,
        "transaction_id": TX,
        "role": "stage",
        "root_path_hash": root_path_hash_from_key(windows_path_key(install.parent / f"IZ Clinical Notes Analyzer.stage-{TX}")),
        "payload_identity": HEX_A,
        "files": inventory_files,
    }
    transaction_root = maintenance / "transactions" / TX
    inventory_path = transaction_root / "program-stage.json"
    write_json(inventory_path, inventory)
    program = {
        "stage_payload_identity": HEX_A,
        "stage_inventory_relative_path": "program-stage.json",
        "stage_inventory_sha256": sha256(inventory_path),
        "stage_marker_sha256": HEX_B,
        "previous_payload_identity": None,
        "previous_inventory_relative_path": None,
        "previous_inventory_sha256": None,
        "previous_marker_sha256": None,
        "active_payload_identity": HEX_A,
    }
    journal: dict[str, object] = {
        "schema": "iz-cna-maintenance-journal-v1",
        "product_id": PRODUCT_ID,
        "owner_sid": owner,
        "scope_id": scope,
        "transaction_id": TX,
        "action": "AutoInstall",
        "state": "NEW_MOVED",
        "sequence": 8,
        "created_utc": "2026-09-14T12:00:00Z",
        "updated_utc": "2026-09-14T12:01:00Z",
        "source_release": None,
        "target_release": release,
        "data_identity": data_id,
        "payload_identity": HEX_A,
        "prior_receipt_sha256": None,
        "snapshot": None,
        "program": program,
        "completed_steps": ["NEW_PROGRAM_MOVED"],
    }
    receipt: dict[str, object] = {
        "schema": "iz-cna-install-receipt-v1",
        "product_id": PRODUCT_ID,
        "owner_sid": owner,
        "scope_id": scope,
        "install_identity": install_identity_from_key(owner, windows_path_key(install)),
        "data_identity": data_id,
        **release,
        "owned_files": [
            {name: value for name, value in record.items() if name != "owned"}
            for record in inventory_files
        ],
        "owned_shortcuts": [],
        "last_committed_transaction": TX,
        "recovery_format": "IZCNABK2",
        "written_utc": "2026-09-14T12:02:00Z",
    }
    fixture = RuntimeFixture(paths, release, journal, receipt, inventory)
    fixture.write_journal()
    return fixture


def configure_rolled_back(fixture: RuntimeFixture) -> None:
    source_release = dict(fixture.release)
    source_release["payload_identity"] = HEX_B
    fixture.receipt["payload_identity"] = HEX_B
    fixture.receipt["last_committed_transaction"] = PRIOR_TX
    fixture.write_receipt()
    previous = dict(fixture.inventory)
    previous["role"] = "previous"
    previous["payload_identity"] = HEX_B
    previous_root = fixture.paths.install_root.parent / f"IZ Clinical Notes Analyzer.previous-{TX}"
    previous["root_path_hash"] = root_path_hash_from_key(windows_path_key(previous_root))
    previous_path = fixture.paths.maintenance_root / "transactions" / TX / "program-previous.json"
    write_json(previous_path, previous)
    program = dict(fixture.journal["program"])
    program.update(
        previous_payload_identity=HEX_B,
        previous_inventory_relative_path="program-previous.json",
        previous_inventory_sha256=sha256(previous_path),
        previous_marker_sha256=HEX_A,
        active_payload_identity=HEX_B,
    )
    fixture.journal.update(
        state="ROLLED_BACK",
        source_release=source_release,
        prior_receipt_sha256=sha256(fixture.paths.receipt_path),
        program=program,
        completed_steps=[
            "OLD_PROGRAM_MOVED",
            "OLD_PROGRAM_RESTORED",
            "OLD_RECEIPT_RESTORED",
            "ROLLBACK_VALIDATED",
        ],
    )
    fixture.write_journal()


def attach_rollback_snapshot(fixture: RuntimeFixture) -> Path:
    snapshot = fixture.paths.maintenance_root / "transactions" / TX / "snapshot" / "pre-change.izcnabackup"
    snapshot.parent.mkdir()
    snapshot.write_bytes(b"synthetic-encrypted-backup-envelope")
    fixture.journal["snapshot"] = {
        "format": "IZCNABK2",
        "relative_path": "snapshot/pre-change.izcnabackup",
        "length": snapshot.stat().st_size,
        "sha256": sha256(snapshot),
        "data_identity": fixture.journal["data_identity"],
        "source_identity_hash": HEX_A,
        "profile_snapshot_identity": HEX_B,
        "verified": True,
    }
    fixture.journal["completed_steps"] = [
        *fixture.journal["completed_steps"],
        "CANDIDATE_STARTED",
        "DATA_RESTORED",
    ]
    fixture.write_journal()
    return snapshot


def test_candidate_authority_validates_journal_and_active_program_before_import(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)

    authority = authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)

    assert authority.gate == "maintenance"
    assert authority.transaction_id == TX
    assert authority.release.model_dump() == fixture.release
    assert "app.main" not in __import__("sys").modules


@pytest.mark.parametrize("field", ["transaction_id", "scope_id", "data_identity", "payload_identity"])
def test_candidate_authority_fails_closed_on_identity_mismatch(tmp_path: Path, field: str) -> None:
    fixture = make_runtime_fixture(tmp_path)
    fixture.journal[field] = HEX_B if field != "transaction_id" else PRIOR_TX
    fixture.write_journal()

    with pytest.raises(RuntimeAuthorityError):
        authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)


def test_candidate_authority_rejects_modified_program_file(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    fixture.paths.executable_path.write_bytes(b"modified")

    with pytest.raises(RuntimeAuthorityError, match="program_inventory_mismatch"):
        authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)


def test_candidate_authority_rejects_inventory_bound_to_another_root(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    fixture.inventory["root_path_hash"] = HEX_B
    inventory_path = fixture.paths.maintenance_root / "transactions" / TX / "program-stage.json"
    write_json(inventory_path, fixture.inventory)
    program = fixture.journal["program"]
    assert isinstance(program, dict)
    program["stage_inventory_sha256"] = sha256(inventory_path)
    fixture.write_journal()

    with pytest.raises(RuntimeAuthorityError, match="program_inventory_mismatch"):
        authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)


def test_proven_fresh_candidate_allows_app_to_create_configured_database(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    (fixture.paths.data_root / "profile.sqlite3").unlink()

    authority = authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)

    assert authority.gate == "maintenance"
    assert not (fixture.paths.data_root / "profile.sqlite3").exists()


def test_missing_database_is_not_fresh_when_other_profile_content_exists(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    (fixture.paths.data_root / "profile.sqlite3").unlink()
    (fixture.paths.data_root / "existing-profile-sentinel").write_text("present", encoding="utf-8")

    with pytest.raises(RuntimeAuthorityError, match="database_missing"):
        authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)


def test_normal_launch_requires_committed_journal_and_matching_receipt(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    fixture.receipt["last_committed_transaction"] = TX
    fixture.write_receipt()
    fixture.journal["state"] = "COMMITTED"
    fixture.journal["completed_steps"] = ["NEW_PROGRAM_MOVED", "INSTALL_RECEIPT_WRITTEN", "COMMIT_RECORDED"]
    fixture.write_journal()

    authority = authorize_runtime(fixture.paths, mode="installed", transaction_id=None)

    assert authority.gate == "open"
    assert authority.transaction_id is None


def test_normal_launch_blocks_pending_journal(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    fixture.write_receipt()

    with pytest.raises(RuntimeAuthorityError, match="maintenance_pending"):
        authorize_runtime(fixture.paths, mode="installed", transaction_id=None)


def test_candidate_commit_rereads_durable_committed_state(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    authority = authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)
    with pytest.raises(RuntimeAuthorityError, match="commit_not_durable"):
        validate_candidate_commit(authority)
    fixture.write_receipt()
    fixture.journal["state"] = "COMMITTED"
    fixture.journal["completed_steps"] = ["NEW_PROGRAM_MOVED", "INSTALL_RECEIPT_WRITTEN", "COMMIT_RECORDED"]
    fixture.write_journal()

    release = validate_candidate_commit(authority)

    assert release.model_dump() == fixture.release


def test_rolled_back_launch_requires_prior_receipt_and_previous_inventory(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    configure_rolled_back(fixture)

    authority = authorize_runtime(fixture.paths, mode="installed", transaction_id=None)

    assert authority.release.payload_identity == HEX_B


@pytest.mark.parametrize("missing_step", ["OLD_PROGRAM_RESTORED", "OLD_RECEIPT_RESTORED"])
def test_rolled_back_launch_rejects_missing_restoration_step(tmp_path: Path, missing_step: str) -> None:
    fixture = make_runtime_fixture(tmp_path)
    configure_rolled_back(fixture)
    fixture.journal["completed_steps"] = [
        step for step in fixture.journal["completed_steps"] if step != missing_step
    ]
    fixture.write_journal()

    with pytest.raises(RuntimeAuthorityError, match="rollback_state_mismatch"):
        authorize_runtime(fixture.paths, mode="installed", transaction_id=None)


def test_rolled_back_launch_rejects_receipt_that_does_not_match_prior_hash(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    configure_rolled_back(fixture)
    fixture.journal["prior_receipt_sha256"] = HEX_A
    fixture.write_journal()

    with pytest.raises(RuntimeAuthorityError, match="rollback_state_mismatch"):
        authorize_runtime(fixture.paths, mode="installed", transaction_id=None)


def test_rolled_back_launch_rejects_candidate_started_without_restored_snapshot(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    configure_rolled_back(fixture)
    fixture.journal["completed_steps"] = [
        *fixture.journal["completed_steps"],
        "CANDIDATE_STARTED",
        "DATA_RESTORED",
    ]
    fixture.write_journal()

    with pytest.raises(RuntimeAuthorityError, match="rollback_state_mismatch"):
        authorize_runtime(fixture.paths, mode="installed", transaction_id=None)


def test_rolled_back_launch_accepts_verified_restored_snapshot(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    configure_rolled_back(fixture)
    attach_rollback_snapshot(fixture)

    authority = authorize_runtime(fixture.paths, mode="installed", transaction_id=None)

    assert authority.release.payload_identity == HEX_B


def test_rolled_back_launch_rejects_modified_snapshot_artifact(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    configure_rolled_back(fixture)
    snapshot = attach_rollback_snapshot(fixture)
    snapshot.write_bytes(b"modified")

    with pytest.raises(RuntimeAuthorityError, match="rollback_state_mismatch"):
        authorize_runtime(fixture.paths, mode="installed", transaction_id=None)


def test_duplicate_journal_key_is_rejected(tmp_path: Path) -> None:
    fixture = make_runtime_fixture(tmp_path)
    raw = fixture.paths.journal_path.read_text(encoding="utf-8")
    fixture.paths.journal_path.write_text(raw[:-1] + ',"state":"COMMITTED"}', encoding="utf-8")

    with pytest.raises(RuntimeAuthorityError, match="journal_invalid"):
        authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)
