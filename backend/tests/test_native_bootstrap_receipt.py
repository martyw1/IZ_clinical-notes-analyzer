from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Sequence

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WRITER = REPOSITORY_ROOT / "scripts" / "ci" / "write-native-bootstrap-receipt.py"
DISPATCHER = REPOSITORY_ROOT / "scripts" / "ci" / "dispatch-native-bootstrap.py"
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "native-desktop-bootstrap.yml"
TARGET_SHA = "1" * 40
TRIGGER_SHA = "2" * 40
WORKFLOW_BLOB = "3" * 40
REQUEST_HASH = "4" * 64
CORRELATION_ID = "5" * 32


def _load_module(path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"native bootstrap boundary is not implemented: {path.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _expected(writer: ModuleType, target_os: str = "windows") -> object:
    return writer.ExpectedNativeReceipt(
        repository="martyw1/IZ_clinical-notes-analyzer",
        repository_id=1172715348,
        repository_node_id="R_kgDOReY3VA",
        correlation_id=CORRELATION_ID,
        target_sha=TARGET_SHA,
        trigger_sha=TRIGGER_SHA,
        workflow_blob_sha=WORKFLOW_BLOB,
        request_sha256=REQUEST_HASH,
        mode="contract",
        target_os=target_os,
    )


def _valid_payload(writer: ModuleType, target_os: str = "windows") -> dict[str, object]:
    architecture = "x64" if target_os == "windows" else "arm64"
    runner_label = "windows-2022" if target_os == "windows" else "macos-15"
    return {
        "schema": "iz-native-bootstrap-receipt-v1",
        "result": "PASS",
        "repository": "martyw1/IZ_clinical-notes-analyzer",
        "repository_id": 1172715348,
        "repository_node_id": "R_kgDOReY3VA",
        "correlation_id": CORRELATION_ID,
        "target_sha": TARGET_SHA,
        "trigger_sha": TRIGGER_SHA,
        "trigger_ref": f"refs/heads/codex-native/{CORRELATION_ID}/trigger",
        "source_ref": f"refs/heads/codex-native/{CORRELATION_ID}/source",
        "workflow_path": ".github/workflows/native-desktop-bootstrap.yml",
        "workflow_blob_sha": WORKFLOW_BLOB,
        "request_sha256": REQUEST_HASH,
        "mode": "contract",
        "action_pins": dict(writer.ACTION_PINS),
        "runner": {"target_os": target_os, "architecture": architecture, "label": runner_label},
        "command": {
            "argv": list(writer.command_for_mode("contract")),
            "exit_code": 0,
            "junit_sha256": "6" * 64,
            "stdout_summary": "tests completed",
        },
        "cleanup": {"runner_temp_removed": True},
    }


def test_contract_mode_rejects_arbitrary_command() -> None:
    # Given: an otherwise valid receipt whose command was caller-controlled.
    writer = _load_module(WRITER, "task1_native_arbitrary_command")
    payload = _valid_payload(writer)
    payload["command"]["argv"] = ["python", "-c", "print('PASS')"]

    # When/Then: only the hardcoded mode-to-pytest mapping is accepted.
    with pytest.raises(writer.NativeBootstrapReceiptError, match="command"):
        writer.validate_receipt(payload, _expected(writer))


def test_receipt_does_not_trust_pass_text_when_command_exits_nonzero() -> None:
    # Given: a forged PASS receipt that prints success while recording exit 23.
    writer = _load_module(WRITER, "task1_native_misleading_success")
    payload = _valid_payload(writer)
    payload["command"]["exit_code"] = 23
    payload["command"]["stdout_summary"] = "PASS"

    # When/Then: the numeric command outcome overrides presentation text.
    with pytest.raises(writer.NativeBootstrapReceiptError, match="exit"):
        writer.validate_receipt(payload, _expected(writer))


def test_stale_correlation_run_is_rejected() -> None:
    # Given: one newer-looking run with the wrong correlation and one exact run.
    dispatcher = _load_module(DISPATCHER, "task1_native_stale_run")
    runs = (
        dispatcher.WorkflowRun(91, 1172715348, TRIGGER_SHA, "codex-native/stale/trigger", "ci(native-bootstrap): stale"),
        dispatcher.WorkflowRun(90, 1172715348, TRIGGER_SHA, f"codex-native/{CORRELATION_ID}/trigger", f"ci(native-bootstrap): {CORRELATION_ID}"),
    )

    # When: selection binds repository, trigger SHA, branch, and correlation.
    selected = dispatcher.select_matching_run(runs, 1172715348, TRIGGER_SHA, CORRELATION_ID)

    # Then: latest-by-branch semantics cannot substitute the stale run.
    assert selected.run_id == 90


def test_cleanup_failure_cannot_produce_passing_collection() -> None:
    # Given: valid Windows/macOS receipts but an undeleted trigger ref.
    dispatcher = _load_module(DISPATCHER, "task1_native_cleanup")
    writer = _load_module(WRITER, "task1_native_cleanup_writer")
    windows = _valid_payload(writer, "windows")
    macos = _valid_payload(writer, "macos")
    cleanup = dispatcher.DispatchCleanup(source_ref_deleted=True, trigger_ref_deleted=False, worktree_removed=True)

    # When/Then: remote/worktree cleanup is part of success, not a warning.
    with pytest.raises(dispatcher.NativeBootstrapDispatchError, match="cleanup"):
        dispatcher.validate_collection((windows, macos), cleanup, _expected(writer))


def test_receipt_rejects_wrong_architecture_and_api_digest() -> None:
    # Given: a Windows receipt relabeled ARM64 and an artifact digest mismatch.
    writer = _load_module(WRITER, "task1_native_arch")
    dispatcher = _load_module(DISPATCHER, "task1_native_digest")
    payload = _valid_payload(writer)
    payload["runner"]["architecture"] = "arm64"

    # When/Then: native architecture and API artifact digest are independently bound.
    with pytest.raises(writer.NativeBootstrapReceiptError, match="architecture"):
        writer.validate_receipt(payload, _expected(writer))
    with pytest.raises(dispatcher.NativeBootstrapDispatchError, match="digest"):
        dispatcher.verify_artifact_digest("sha256:" + "a" * 64, bytes.fromhex("00"))


def test_all_task1_modes_are_closed_and_forward_files_fail(tmp_path: Path) -> None:
    # Given: the exact Task-1 mode inventory and files implemented through Task 3.
    writer = _load_module(WRITER, "task1_native_modes")

    # When: each hardcoded mode resolves its exact pytest modules.
    commands = {mode: writer.command_for_mode(mode) for mode in writer.TASK1_MODES}

    # Then: implemented modes resolve without arbitrary shell text.
    assert tuple(writer.TASK1_MODES) == ("contract", "bootstrap", "factory", "control", "jobs", "release-safety")
    assert all(command[:3] == (sys.executable, "-m", "pytest") for command in commands.values())
    for mode in ("contract", "bootstrap", "factory", "jobs", "release-safety"):
        writer.require_mode_files(REPOSITORY_ROOT, mode)

    # Then: a forward mode still fails closed when its mapped files are absent.
    with pytest.raises(writer.NativeBootstrapReceiptError, match="not available"):
        writer.require_mode_files(tmp_path, "control")


def test_dirty_worktree_is_rejected_before_publication() -> None:
    # Given: porcelain output containing one untracked synthetic path.
    dispatcher = _load_module(DISPATCHER, "task1_native_dirty_worktree")

    # When/Then: native publication refuses any dirty checkout state.
    with pytest.raises(dispatcher.NativeBootstrapDispatchError, match="dirty worktree"):
        dispatcher.require_clean_worktree("?? synthetic-only.tmp\n")


def test_cleanup_accepts_only_an_exact_worktree_removed_despite_git_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Git removes the exact task-owned checkout before failing on administrative metadata.
    dispatcher = _load_module(DISPATCHER, "task1_native_worktree_cleanup")
    temporary_root = tmp_path / "iz-native-bootstrap-synthetic"
    checkout = temporary_root / "checkout"
    checkout.mkdir(parents=True)

    def remove_then_fail(command: Sequence[str], *, cwd: Path = REPOSITORY_ROOT) -> str:
        del cwd
        assert tuple(command) == ("git", "worktree", "remove", "--force", str(checkout))
        checkout.rmdir()
        raise dispatcher.NativeBootstrapDispatchError("administrative metadata cleanup failed")

    monkeypatch.setattr(dispatcher, "_run", remove_then_fail)

    # When/Then: cleanup succeeds only after the checkout and its private root are both absent.
    assert dispatcher.remove_worktree(checkout, temporary_root) is True
    assert not temporary_root.exists()


def test_successful_dispatch_writes_the_validated_collection_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: both exact native artifacts validate and every cleanup boundary succeeds.
    dispatcher = _load_module(DISPATCHER, "task1_native_success_finalization")
    output_dir = tmp_path / "native-output"
    receipt_path = tmp_path / "collection.json"
    temporary_root = tmp_path / "native-root"
    temporary_root.mkdir()
    correlations = iter((CORRELATION_ID, "6" * 32, "7" * 16))

    def run(command: Sequence[str], *, cwd: Path = REPOSITORY_ROOT) -> str:
        if tuple(command[:3]) == ("git", "rev-parse", "HEAD"):
            return TRIGGER_SHA if cwd != REPOSITORY_ROOT else TARGET_SHA
        if tuple(command[:2]) == ("git", "rev-parse"):
            return WORKFLOW_BLOB
        return ""

    def remote_sha(remote: str, ref: str) -> str:
        del remote
        return TARGET_SHA if ref.endswith("/source") else TRIGGER_SHA

    def extract(repository: str, artifact: dict[str, object], destination: Path) -> tuple[dict[str, object], dict[str, object]]:
        del repository, artifact
        return {"runner": {"target_os": destination.name}}, {"artifact_id": 1}

    monkeypatch.setattr(dispatcher, "_run", run)
    monkeypatch.setattr(dispatcher, "_remote_sha", remote_sha)
    monkeypatch.setattr(dispatcher, "_preflight", lambda args, output: None)
    monkeypatch.setattr(dispatcher, "_wait_for_run", lambda *args: dispatcher.WorkflowRun(90, 1172715348, TRIGGER_SHA, f"codex-native/{CORRELATION_ID}/trigger", f"ci(native-bootstrap): {CORRELATION_ID}"))
    monkeypatch.setattr(dispatcher, "_api", lambda path: {"artifacts": [{"name": "native-bootstrap-windows", "expired": False}, {"name": "native-bootstrap-macos", "expired": False}]})
    monkeypatch.setattr(dispatcher, "_extract_artifact", extract)
    monkeypatch.setattr(dispatcher, "_delete_ref", lambda remote, ref: True)
    monkeypatch.setattr(dispatcher, "remove_worktree", lambda checkout, root: True)
    monkeypatch.setattr(dispatcher, "validate_collection", lambda receipts, cleanup, expected: None)
    monkeypatch.setattr(dispatcher.tempfile, "mkdtemp", lambda prefix: str(temporary_root))
    monkeypatch.setattr(dispatcher.secrets, "token_hex", lambda size: next(correlations))
    args = argparse.Namespace(commit=TARGET_SHA, repository="martyw1/IZ_clinical-notes-analyzer", repository_id=1172715348,
                              remote="origin", mode="contract", output_dir=output_dir, receipt=receipt_path)

    # When: the dispatcher finalizes the already validated successful collection.
    collection = dispatcher.dispatch(args)

    # Then: it returns PASS and atomically writes the identical machine-readable receipt.
    assert collection["result"] == "PASS"
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == collection


def test_workflow_is_push_only_native_and_fully_pinned() -> None:
    # Given: the Task-1 native bootstrap workflow source.
    text = WORKFLOW.read_text(encoding="utf-8")

    # When/Then: only the bounded push namespace and exact native/action identities are present.
    assert "workflow_dispatch" not in text
    assert '      - "codex-native/**"' in text
    assert "windows-2022" in text and "macos-15" in text
    assert 'python-version: "3.12.10"' in text
    pins = {
        "actions/checkout@1af3b93b6815bc44a9784bd300feb67ff0d1eeb3",
        "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
        "actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f",
        "actions/download-artifact@70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3",
    }
    assert {line.strip().removeprefix("uses: ") for line in text.splitlines() if line.strip().startswith("uses:")} == pins


def test_dispatcher_cli_accepts_exactly_declared_flags(tmp_path: Path) -> None:
    # Given: the exact public arguments plus one command-widening flag.
    command = [sys.executable, str(DISPATCHER), "--commit", TARGET_SHA, "--repository", "martyw1/IZ_clinical-notes-analyzer",
               "--repository-id", "1172715348", "--remote", "origin", "--mode", "contract",
               "--output-dir", str(tmp_path / "output"), "--receipt", str(tmp_path / "receipt.json"), "--command", "echo PASS"]

    # When: parsing occurs before repository or remote operations.
    completed = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False, capture_output=True, text=True)

    # Then: the undeclared command surface is rejected without a receipt.
    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
