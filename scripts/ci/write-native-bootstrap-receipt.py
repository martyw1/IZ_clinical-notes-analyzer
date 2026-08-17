#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Run: uv run scripts/ci/write-native-bootstrap-receipt.py --help
# 3. Or: python scripts/ci/write-native-bootstrap-receipt.py --help
# ─────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence


REPOSITORY: Final = "martyw1/IZ_clinical-notes-analyzer"
REPOSITORY_ID: Final = 1172715348
REPOSITORY_NODE_ID: Final = "R_kgDOReY3VA"
WORKFLOW_PATH: Final = ".github/workflows/native-desktop-bootstrap.yml"
ACTION_PINS: Final = {
    "actions/checkout": "1af3b93b6815bc44a9784bd300feb67ff0d1eeb3",
    "actions/setup-python": "a309ff8b426b58ec0e2a45f0f869d46889d02405",
    "actions/upload-artifact": "bbbca2ddaa5d8feaa63e36b76fdaad77386f024f",
    "actions/download-artifact": "70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3",
}
MODE_TESTS: Final = {
    "contract": (
        "backend/tests/test_desktop_behavior_characterization.py", "backend/tests/test_v2_auth_rbac.py",
        "backend/tests/test_v2_runtime_readiness.py", "backend/tests/test_v2_alleva_contract_gate.py",
        "backend/tests/test_v2_deterministic_evaluator.py",
    ),
    "bootstrap": ("backend/tests/test_desktop_bootstrap.py", "backend/tests/test_v2_production_config.py"),
    "factory": ("backend/tests/test_application_factory.py", "backend/tests/test_v2_production_config.py"),
    "control": ("backend/tests/test_desktop_runtime_state.py", "backend/tests/test_desktop_control.py"),
    "jobs": ("backend/tests/test_desktop_job_shutdown.py", "backend/tests/test_v2_alleva_sync.py",
             "backend/tests/test_v2_distinct_alleva_jobs.py", "backend/tests/test_v2_harness_job_persistence.py"),
    "release-safety": ("backend/tests/test_release_safety_cross_platform.py",),
}
TASK1_MODES: Final = tuple(MODE_TESTS)


@dataclass(frozen=True, slots=True)
class NativeBootstrapReceiptError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ExpectedNativeReceipt:
    repository: str
    repository_id: int
    repository_node_id: str
    correlation_id: str
    target_sha: str
    trigger_sha: str
    workflow_blob_sha: str
    request_sha256: str
    mode: str
    target_os: str


def command_for_mode(mode: str) -> tuple[str, ...]:
    try:
        tests = MODE_TESTS[mode]
    except KeyError as exc:
        raise NativeBootstrapReceiptError(f"mode is not available: {mode}") from exc
    return (sys.executable, "-m", "pytest", *tests, "-q", "--junitxml=native-junit.xml")


def require_mode_files(repository_root: Path, mode: str) -> None:
    missing = [path for path in MODE_TESTS.get(mode, ()) if not (repository_root / path).is_file()]
    if mode not in MODE_TESTS or missing:
        raise NativeBootstrapReceiptError(f"mode is not available at this commit: {mode}")


def canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _is_hash(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _request_payload(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeBootstrapReceiptError("native request is unreadable or invalid") from exc
    if not isinstance(payload, dict):
        raise NativeBootstrapReceiptError("native request must be an object")
    expected_keys = {"schema", "repository", "repository_id", "repository_node_id", "correlation_id", "target_sha",
                     "workflow_path", "workflow_blob_sha", "mode", "nonce", "request_sha256"}
    if payload.keys() != expected_keys:
        raise NativeBootstrapReceiptError("native request fields differ")
    supplied = payload["request_sha256"]
    unhashed = {key: value for key, value in payload.items() if key != "request_sha256"}
    if not _is_hash(supplied, 64) or hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest() != supplied:
        raise NativeBootstrapReceiptError("native request hash differs")
    if payload["schema"] != "iz-native-bootstrap-request-v1" or payload["workflow_path"] != WORKFLOW_PATH:
        raise NativeBootstrapReceiptError("native request schema or workflow path differs")
    if payload["mode"] not in TASK1_MODES or not _is_hash(payload["target_sha"], 40) or not _is_hash(payload["workflow_blob_sha"], 40):
        raise NativeBootstrapReceiptError("native request mode or commit hashes differ")
    if not _is_hash(payload["correlation_id"], 32) or not _is_hash(payload["nonce"], 32):
        raise NativeBootstrapReceiptError("native request correlation or nonce differs")
    return payload


def _expected_values(expected: ExpectedNativeReceipt) -> dict[str, object]:
    return {
        "repository": expected.repository, "repository_id": expected.repository_id,
        "repository_node_id": expected.repository_node_id, "correlation_id": expected.correlation_id,
        "target_sha": expected.target_sha, "trigger_sha": expected.trigger_sha,
        "trigger_ref": f"refs/heads/codex-native/{expected.correlation_id}/trigger",
        "source_ref": f"refs/heads/codex-native/{expected.correlation_id}/source",
        "workflow_path": WORKFLOW_PATH, "workflow_blob_sha": expected.workflow_blob_sha,
        "request_sha256": expected.request_sha256, "mode": expected.mode,
    }


def validate_receipt(payload: dict[str, object], expected: ExpectedNativeReceipt) -> None:
    required = {"schema", "result", *_expected_values(expected), "action_pins", "runner", "command", "cleanup"}
    if payload.keys() != required or payload.get("schema") != "iz-native-bootstrap-receipt-v1" or payload.get("result") != "PASS":
        raise NativeBootstrapReceiptError("receipt schema, fields, or result differs")
    for key, value in _expected_values(expected).items():
        if payload.get(key) != value:
            raise NativeBootstrapReceiptError(f"receipt {key} differs")
    if payload.get("action_pins") != ACTION_PINS:
        raise NativeBootstrapReceiptError("receipt action pins differ")
    runner = payload.get("runner")
    architecture, label = (("x64", "windows-2022") if expected.target_os == "windows" else ("arm64", "macos-15"))
    if runner != {"target_os": expected.target_os, "architecture": architecture, "label": label}:
        raise NativeBootstrapReceiptError("receipt runner architecture or label differs")
    command = payload.get("command")
    if not isinstance(command, dict) or command.keys() != {"argv", "exit_code", "junit_sha256", "stdout_summary"}:
        raise NativeBootstrapReceiptError("receipt command fields differ")
    argv, expected_argv = command.get("argv"), command_for_mode(expected.mode)
    executable = str(argv[0]).replace("\\", "/").rsplit("/", 1)[-1].lower() if isinstance(argv, list) and argv else ""
    if not isinstance(argv, list) or tuple(argv[1:]) != expected_argv[1:] or executable not in {"python", "python.exe"}:
        raise NativeBootstrapReceiptError("receipt command is not the hardcoded mode command")
    if command.get("exit_code") != 0:
        raise NativeBootstrapReceiptError("receipt command exit status is nonzero")
    if not _is_hash(command.get("junit_sha256"), 64):
        raise NativeBootstrapReceiptError("receipt JUnit hash differs")
    if payload.get("cleanup") != {"runner_temp_removed": True}:
        raise NativeBootstrapReceiptError("receipt runner cleanup differs")


def write_private_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _request_phase(args: argparse.Namespace) -> None:
    payload = _request_payload(args.request)
    fixed = (payload["repository"] == args.repository == REPOSITORY
             and payload["repository_id"] == args.repository_id == REPOSITORY_ID
             and payload["repository_node_id"] == args.repository_node_id == REPOSITORY_NODE_ID)
    correlation = str(payload["correlation_id"])
    if not fixed or args.trigger_ref != f"refs/heads/codex-native/{correlation}/trigger" or payload["workflow_blob_sha"] != args.workflow_blob_sha:
        raise NativeBootstrapReceiptError("event, repository identity, or workflow blob differs from request")
    source_ref = f"refs/heads/codex-native/{correlation}/source"
    resolved = subprocess.run(("git", "ls-remote", "--refs", args.remote, source_ref), check=False, capture_output=True, text=True)
    if resolved.returncode != 0 or resolved.stdout.strip() != f"{payload['target_sha']}\t{source_ref}":
        raise NativeBootstrapReceiptError("source ref does not resolve to the requested target")
    with args.github_output.open("a", encoding="utf-8", newline="\n") as stream:
        for key in ("target_sha", "correlation_id", "request_sha256", "mode", "workflow_blob_sha"):
            stream.write(f"{key}={payload[key]}\n")


def _architecture(target_os: str) -> str:
    machine = platform.machine().lower()
    normalized = "x64" if machine in {"amd64", "x86_64"} else "arm64" if machine in {"arm64", "aarch64"} else machine
    required = "x64" if target_os == "windows" else "arm64"
    if normalized != required:
        raise NativeBootstrapReceiptError(f"runner architecture differs: expected {required}")
    return normalized


def _run_phase(args: argparse.Namespace) -> int:
    request = _request_payload(args.request)
    root = Path(__file__).resolve().parents[2]
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    if head != request["target_sha"]:
        raise NativeBootstrapReceiptError("test checkout does not match target SHA")
    mode, target_os = str(request["mode"]), args.target_os
    require_mode_files(root, mode)
    architecture = _architecture(target_os)
    command = command_for_mode(mode)
    completed = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True)
    request_path = args.request.resolve()
    request_path.unlink(missing_ok=True)
    junit = root / "native-junit.xml"
    receipt = {
        "schema": "iz-native-bootstrap-receipt-v1", "result": "PASS" if completed.returncode == 0 else "FAIL",
        "repository": request["repository"], "repository_id": request["repository_id"],
        "repository_node_id": request["repository_node_id"], "correlation_id": request["correlation_id"],
        "target_sha": request["target_sha"], "trigger_sha": args.trigger_sha,
        "trigger_ref": f"refs/heads/codex-native/{request['correlation_id']}/trigger",
        "source_ref": f"refs/heads/codex-native/{request['correlation_id']}/source",
        "workflow_path": WORKFLOW_PATH, "workflow_blob_sha": request["workflow_blob_sha"],
        "request_sha256": request["request_sha256"], "mode": mode, "action_pins": ACTION_PINS,
        "runner": {"target_os": target_os, "architecture": architecture, "label": args.runner_label},
        "command": {"argv": list(command), "exit_code": completed.returncode,
                    "junit_sha256": hashlib.sha256(junit.read_bytes()).hexdigest() if junit.is_file() else "",
                    "stdout_summary": f"pytest exited {completed.returncode}"},
        "cleanup": {"runner_temp_removed": not request_path.exists()},
    }
    write_private_receipt(args.receipt, receipt)
    if completed.returncode == 0:
        expected = ExpectedNativeReceipt(str(request["repository"]), int(request["repository_id"]),
                                         str(request["repository_node_id"]), str(request["correlation_id"]),
                                         str(request["target_sha"]), args.trigger_sha, str(request["workflow_blob_sha"]),
                                         str(request["request_sha256"]), mode, target_os)
        validate_receipt(receipt, expected)
    return completed.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate requests and write native bootstrap receipts")
    phases = parser.add_subparsers(dest="phase", required=True)
    request = phases.add_parser("request")
    for flag in ("repository", "repository-node-id", "remote", "trigger-ref", "workflow-blob-sha"):
        request.add_argument(f"--{flag}", required=True)
    request.add_argument("--repository-id", required=True, type=int)
    request.add_argument("--request", required=True, type=Path)
    request.add_argument("--github-output", required=True, type=Path)
    run = phases.add_parser("run")
    run.add_argument("--request", required=True, type=Path)
    run.add_argument("--trigger-sha", required=True)
    run.add_argument("--target-os", choices=("windows", "macos"), required=True)
    run.add_argument("--runner-label", choices=("windows-2022", "macos-15"), required=True)
    run.add_argument("--receipt", required=True, type=Path)
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        if args.phase == "request":
            _request_phase(args)
            return 0
        return _run_phase(args)
    except (NativeBootstrapReceiptError, OSError, subprocess.SubprocessError) as exc:
        print(f"Native bootstrap failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
